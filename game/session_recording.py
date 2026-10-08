"""Scientific human-session recording at fixed simulation ticks, not render FPS.

Analysis state and whitelisted policy observations live in separate files.
Only compact population/descending readouts are recorded, never the full brain.
"""
from collections import Counter, deque
from dataclasses import asdict
from datetime import datetime, timezone
from functools import lru_cache
import hashlib
import importlib.metadata
import json
import math
import numba
import platform
from pathlib import Path
import statistics
import subprocess
import time
import uuid
import zipfile
from .recording import observation_frame, policy_observation
from .edge_analysis import edge_diagnostics
from .lifecycle import LifecycleMetrics

SCHEMA_VERSION = 3


def canonical_hash(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()


@lru_cache(maxsize=8)
def _file_digest(path, size, modified_ns):
    digest=hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda:stream.read(1024*1024),b''):digest.update(block)
    return digest.hexdigest()


def dataset_hashes(root, config):
    folder=(root/config['brain']['data']).resolve()
    hashes={}
    for name in ('brain.npz','weights.npz'):
        path=folder/name;stat=path.stat()
        hashes[name]=_file_digest(str(path),stat.st_size,stat.st_mtime_ns)
    return hashes


def git_value(root,*args):
    try:return subprocess.check_output(['git',*args],cwd=root,text=True,stderr=subprocess.DEVNULL).strip()
    except (OSError,subprocess.CalledProcessError):return None


class HumanSessionRecorder:
    def __init__(self, directory, config_file=None, archive_source=True):
        self.root=Path(directory);self.root.mkdir(parents=True,exist_ok=True)
        self.run_id=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S.%fZ')+'-'+uuid.uuid4().hex[:8]
        self.path=self.root/self.run_id;self.path.mkdir(exist_ok=False)
        self.config_file=Path(config_file).resolve() if config_file else None
        self.archive_source=archive_source
        self.files={key:(self.path/(key+'.jsonl')).open('w',encoding='utf-8') for key in
                    ('ticks','inputs','events','policy_observations','episodes')}
        self.lifecycle_metrics = LifecycleMetrics()
        self.active=False;self.closed=False;self.episode=0;self.global_tick=0;self.input_index=0
        self.started_wall=time.perf_counter();self.history=deque(maxlen=4)
        self.presentation={};self.control_flags=set();self.strikes=[];self.episode_summaries=[]
        self.threat_counts=Counter();self.ecology_counts=Counter();self.event_counts=Counter();self.speeds=[]
        self.alive_threat_counts=Counter();self.alive_ecology_counts=Counter()
        self.alive_tick_count=0;self.all_speeds=[];self.alive_speeds=[]
        self.approach_speeds=[];self.approach_pointer_speeds=[];self.approach_errors=[]
        self.wall_ticks=self.perimeter_ticks=self.contact_ticks=self.odor_encounters=0
        self.episode_ranges={};self.current_strike=None;self.paused=False;self.closed_manifest=None

    def emit(self, key, value):
        self.files[key].write(json.dumps(value,separators=(',',':'),allow_nan=False)+'\n')

    def input(self, session, kind, **payload):
        self.emit('inputs',{'sequence':self.input_index,'episode':self.episode,'next_tick':session.ticks,
                           'global_next_tick':self.global_tick,'wall_seconds':time.perf_counter()-self.started_wall,
                           'kind':kind,**payload})
        self.input_index+=1

    def control(self, session, name, **payload):
        self.input(session,'control',name=name,payload=payload)
        self.control_flags.add(name)
        if name=='pause':self.paused=bool(payload['paused'])
        self.emit('events',{'type':name,'episode':self.episode,'tick':session.ticks,
                           'global_tick':self.global_tick,'simulation_time':session.ticks*session.tick_seconds,
                           'wall_seconds':time.perf_counter()-self.started_wall,**payload})

    def set_presentation(self, **values):self.presentation.update(values)

    def start(self, session):
        from .session import calibration_provenance
        self.episode+=1;self.active=True;self.history.clear();self.control_flags.clear();self.paused=False
        self.prev_threat='CALM';self.prev_above=False;self.prev_alive=True;self.prev_odor=False
        self.last_threat_onset=None;self.last_threat_pose=None;self.last_escape_onset=None;self.seen_strikes=0;self.current_strike=None
        w=session.world;self.prev_fly_velocity=(w.fly.vx,w.fly.vy);self.prev_swatter=(w.swatter.x,w.swatter.y)
        self.episode_ranges[self.episode]=[self.global_tick,self.global_tick-1]
        self.episode_initial_seed=session.seed
        if self.episode==1:
            versions={p:importlib.metadata.version(p) for p in ('flybrain','numpy','scipy','numba')}
            source={str(p.relative_to(session.root)).replace('\\','/'):hashlib.sha256(p.read_bytes()).hexdigest()
                    for p in sorted((session.root/'game').glob('*.py'))}
            config=session.config
            calibration=None
            if session.threshold_source is not None:
                calibration=json.loads((session.root/session.threshold_source.origin).read_text(encoding='utf-8'))
                calibration={k:calibration[k] for k in ('provenance','escape_threshold')}
            self.manifest={'recording_schema_version':4 if w.lifecycle_active else SCHEMA_VERSION,'session_id':self.run_id,
                'created_utc':datetime.now(timezone.utc).isoformat(),'git_commit':git_value(session.root,'rev-parse','HEAD'),
                'git_branch':git_value(session.root,'branch','--show-current'),
                'git_dirty':bool(git_value(session.root,'status','--porcelain')),
                'source_sha256':source,'versions':versions,'python_version':platform.python_version(),
                'runtime':{'numba_threads':numba.get_num_threads(),'numba_threading_layer':numba.threading_layer()},
                'platform':platform.platform(),'config_file':str(self.config_file) if self.config_file else None,
                'config_file_sha256':hashlib.sha256(self.config_file.read_bytes()).hexdigest() if self.config_file and self.config_file.exists() else None,
                'config':config,'config_sha256':calibration_provenance(config)['game_config_sha256'],
                'config_version':config.get('config_version'),'calibration':calibration,'provenance':calibration_provenance(config),
                'arena':config.get('arena',{}).get('name','lab'),'mode':session.mode.name,'initial_seed':session.seed,
                'tick_seconds':session.tick_seconds,'sampling_hz':1/session.tick_seconds,
                'logical_arena':[w.width,w.height],'body_length':w.body_length,'ecology_enabled':session.ecology is not None,
                'policy_class':type(session.policy).__name__,'full_brain_recording':False,
                'dataset_sha256':dataset_hashes(session.root,config),
                'time_alignment':'retina/motor/internal observation pre-physics; fly/swatter/action outcomes post-physics; presentation is last UI sample',
                'replay_scope':'exact deterministic tick state and compact neural readouts; wall pause duration and render timing are excluded',
                'policy_observation_schema':'unchanged M1.5 whitelist; world/ecology debug is not policy input','closed_cleanly':False}
            (self.path/'manifest.json').write_text(json.dumps(self.manifest,indent=2)+'\n',encoding='utf-8')
            if self.archive_source:
                with zipfile.ZipFile(self.path/'source_snapshot.zip','w',zipfile.ZIP_DEFLATED) as archive:
                    for rel in source:archive.write(session.root/rel,rel)
        if self.episode>1:self.control_flags.add('restart')
        self.input(session,'reset',seed=session.seed)
        self.emit('events',{'type':'episode_start' if self.episode==1 else 'restart','episode':self.episode,
                           'tick':0,'global_tick':self.global_tick,'seed':session.seed,'spawn':dict(w.spawn_state)})

    def capture(self, session, events, before_state):
        if not self.active:return
        w=session.world;f=w.fly;sw=w.swatter;dt=session.tick_seconds;tick=session.ticks-1
        diag=session.policy_diagnostics;motor=session.fly_loop.last_motor;action=session.fly_loop.last_action
        neural_state=diag.get('behavior_state','UNSPECIFIED')
        dn_left=0.0 if motor is None else float(motor.dnp01_left)
        dn_right=0.0 if motor is None else float(motor.dnp01_right)
        total=dn_left+dn_right;threshold=diag.get('escape_threshold')
        above=threshold is not None and total>=threshold
        odor=bool(session.ecology and session.ecology.has_odor)
        speed=math.hypot(f.vx,f.vy);vheading=math.atan2(f.vy,f.vx) if speed>1e-12 else None
        slip=None if vheading is None else (vheading-f.heading+math.pi)%(2*math.pi)-math.pi
        started=events.strike_started or w.stats.strikes>self.seen_strikes
        flags={'threat_onset':neural_state in ('ALERT','ESCAPE') and self.prev_threat not in ('ALERT','ESCAPE'),
               'alert_onset':neural_state=='ALERT' and self.prev_threat!='ALERT',
               'escape_onset':neural_state=='ESCAPE' and self.prev_threat!='ESCAPE',
               'threshold_crossing':bool(above and not self.prev_above),'strike_start':started,
               'strike_active':w.lethal or bool(w.physical_swatter and any(seg[-1] for seg in w.physical_swatter.segments)),
               'hit':events.hit,'miss':events.strike_resolved and not events.hit and not w.stats.hits,
               'death':self.prev_alive and not f.alive,'restart':'restart' in self.control_flags,
               'pause':'pause' in self.control_flags,'odor_encounter':odor and not self.prev_odor}
        edge = edge_diagnostics(w, flags["hit"], flags["miss"])
        flags.update({key:edge[key] for key in ("hit_near_wall", "miss_near_wall")})
        # Hit scoring is per strike; earlier hits terminate a living episode.
        if flags['threat_onset']:
            self.last_threat_onset=tick
            self.last_threat_pose={'x':f.x,'y':f.y,'vx':f.vx,'vy':f.vy,'heading':f.heading}
        if flags['escape_onset']:self.last_escape_onset=tick
        if started:
            self.seen_strikes=w.stats.strikes
            onset=self.last_threat_onset if self.last_threat_onset is not None and tick-self.last_threat_onset<=round(1/dt) else None
            strike={'episode':self.episode,'strike_id':w.stats.strikes,'start_tick':tick,'start_global_tick':self.global_tick,
                    'strike_start_time':tick*dt,'threat_onset_tick':onset,'threat_onset_time':None if onset is None else onset*dt,
                    'strike_fly_state':{'x':f.x,'y':f.y,'vx':f.vx,'vy':f.vy,'heading':f.heading},
                    'onset_fly_state':self.last_threat_pose if onset is not None else None,
                    'attack_direction':sw.attack_orientation if w.physical_swatter else sw.orientation,
                    'attack_speed':sw.attack_speed,'attack_acceleration':sw.attack_acceleration,
                    'outcome':'incomplete','escape_tick':None,'escape_preexisting':self.prev_threat=='ESCAPE',
                    'requested_window_ticks':[max(0,tick-round(1/dt)),tick+round(2/dt)]}
            self.strikes.append(strike);self.current_strike=strike
        if self.current_strike is not None and tick<=self.current_strike['start_tick']+round(2/dt):
            st=self.current_strike
            if st['threat_onset_tick'] is None and flags['threat_onset']:
                st['threat_onset_tick']=tick;st['threat_onset_time']=tick*dt;st['onset_fly_state']=self.last_threat_pose
            if st['escape_tick'] is None and flags['escape_onset']:st['escape_tick']=tick
            if events.hit:st['outcome']='hit';st['resolved_tick']=tick
            elif events.strike_resolved and st['outcome']=='incomplete':st['outcome']='miss';st['resolved_tick']=tick
        for name,on in flags.items():
            if on and name!='strike_active':
                self.event_counts[name]+=1
                self.emit('events',{'type':name,'episode':self.episode,'tick':tick,'global_tick':self.global_tick,
                                   'simulation_time':tick*dt,'strike_id':w.stats.strikes if w.stats.strikes else None})
        swvx=(sw.x-self.prev_swatter[0])/dt;swvy=(sw.y-self.prev_swatter[1])/dt
        if w.physical_swatter is not None:swvx,swvy=sw.vx,sw.vy
        sense=None if session.last_ecological_sense is None else asdict(session.last_ecological_sense)
        snapshot={'global_tick':self.global_tick,'episode':self.episode,'tick':tick,'episode_seed':session.seed,
            'simulation_time':tick*dt,'post_step_time':(tick+1)*dt,'session_simulation_time':self.global_tick*dt,
            'config_sha256':self.manifest['config_sha256'],'config_version':self.manifest['config_version'],
            'fly':{'x':f.x,'y':f.y,'vx':f.vx,'vy':f.vy,'speed':speed,'speed_bl_s':speed/w.body_length,
                   'heading':f.heading,'velocity_heading':vheading,'heading_velocity_mismatch':slip,
                   'ax':(f.vx-self.prev_fly_velocity[0])/dt,'ay':(f.vy-self.prev_fly_velocity[1])/dt,'alive':f.alive},
            'retina':asdict(session.last_retina) if session.last_retina else None,
            'visual_input':dict(session.encoder.last_drive),'sensory_spikes':dict(session.fly_loop.last_sensory_spikes),
            'neural':{'dnp01_left':dn_left,'dnp01_right':dn_right,'dnp01_total':total,
                      'dna02_left':0.0 if motor is None else float(motor.dna02_left),
                      'dna02_right':0.0 if motor is None else float(motor.dna02_right),
                      'steering_decoder':action.turn,'threshold':threshold,'refractory_seconds':diag.get('refractory_seconds'),
                      'state':neural_state,'diagnostics':diag,'brain_stepped':self.prev_alive},
            'action':asdict(action),'saccade':{'type':w.saccades.kind,'remaining_seconds':w.saccades.remaining,
                    'angle':w.saccades.angle,'duration':w.saccades.duration,'yaw_rate':w.yaw_rate,'delta':w.saccades.last_delta},
            'ecology':{'sense':sense,'state':session.ecology.state if session.ecology else None,
                      'diagnostics':session.ecology.diagnostics() if session.ecology else None,
                      'requested_speed_bl_s':session.ecology.speed if session.ecology else None,
                      'applied_drive_bl_s':w.applied_target_speed/w.body_length,
                      'landing_perching':'approach_only' if session.ecology and session.ecology.state=='LAND_OR_PERCH' else 'airborne'},
            'wall':{'cue':asdict(w.wall_cue),'flight':w.flight.diagnostics(),'contact':w.wall_contact,'object_contact':w.object_contact},
            'swatter':{**asdict(sw),'phase':sw.phase.value,'vx':swvx,'vy':swvy,'speed':math.hypot(swvx,swvy),'strike_id':w.stats.strikes},
            'stats':asdict(w.stats),'event_flags':flags,'paused':self.paused,
            'room_world':w.room.debug(f,w.time_seconds) if w.room else None,
            'population':session.encoder.population,'edge_analysis':edge,
            'swatter_control':w.physical_swatter.diagnostics() if w.physical_swatter else None}
        if w.lifecycle_active:
            life = w.lifecycle
            snapshot['lifecycle'] = {**life.diagnostics(), 'contact_surface_id': w.contact_surface_id,
                                     'airborne': not life.stationary, 'attached': w.contact_surface_id is not None}
            snapshot['ecology']['landing_perching'] = life.mode
            snapshot['room_world']['contact_pose'] = w.contact_pose
            self.lifecycle_metrics.capture(life, f.alive, dt)
            for event in life.events:
                self.emit('events', {**event, 'episode': self.episode, 'tick': tick,
                           'global_tick': self.global_tick, 'simulation_time': tick*dt,
                           'contact_surface_id': event.get('contact_surface_id', w.contact_surface_id)})
        digest=canonical_hash(snapshot)
        self.emit('ticks',{**snapshot,'deterministic_sha256':digest,'presentation':dict(self.presentation)})
        if motor is not None and self.prev_alive:
            obs=policy_observation(motor,before_state,self.history)
            self.emit('policy_observations',{'episode':self.episode,'tick':tick,'global_tick':self.global_tick,
                        'observation':obs,'action':asdict(action),'outcome':{'hit':events.hit,'alive':f.alive}})
            self.history.append(observation_frame(motor,before_state))
        self.threat_counts[neural_state]+=1
        if session.ecology:self.ecology_counts[session.ecology.state]+=1
        if self.prev_alive:self.speeds.append(speed/w.body_length)
        self.all_speeds.append(speed/w.body_length)
        if f.alive:
            self.alive_tick_count+=1
            self.alive_speeds.append(speed/w.body_length)
            self.alive_threat_counts[neural_state]+=1
            if session.ecology:self.alive_ecology_counts[session.ecology.state]+=1
            if sw.phase.value=='approach':
                self.approach_speeds.append(math.hypot(swvx,swvy))
                control=snapshot['swatter_control']
                if control and control['pointer_sample_valid']:
                    self.approach_pointer_speeds.append(control['pointer_speed'])
                    self.approach_errors.append(control['target_error_before_step'])
        self.wall_ticks+=w.wall_cue.proximity>=.45
        self.perimeter_ticks+=w.flight.near_wall;self.contact_ticks+=w.wall_contact or w.object_contact
        self.odor_encounters+=flags['odor_encounter']
        self.prev_threat=neural_state;self.prev_above=above;self.prev_alive=f.alive;self.prev_odor=odor
        self.prev_fly_velocity=(f.vx,f.vy);self.prev_swatter=(sw.x,sw.y);self.control_flags.clear()
        self.episode_ranges[self.episode][1]=self.global_tick;self.global_tick+=1
        if self.global_tick%50==0:
            for file in self.files.values():file.flush()

    def finish(self, session, reason):
        if not self.active:return
        # A between-tick click can be followed by restart/quit before any
        # brain step. Preserve it as a censored event with an empty sample window.
        w=session.world;sw=w.swatter;tick=session.ticks;dt=session.tick_seconds
        if w.stats.strikes>self.seen_strikes:
            self.strikes.append({'episode':self.episode,'strike_id':w.stats.strikes,'start_tick':tick,
                'start_global_tick':self.global_tick,'strike_start_time':tick*dt,
                'threat_onset_tick':None,'threat_onset_time':None,'onset_fly_state':None,
                'strike_fly_state':{'x':w.fly.x,'y':w.fly.y,'vx':w.fly.vx,'vy':w.fly.vy,'heading':w.fly.heading},
                'attack_direction':sw.attack_orientation if w.physical_swatter else sw.orientation,
                'attack_speed':sw.attack_speed,'attack_acceleration':sw.attack_acceleration,
                'outcome':'incomplete','escape_tick':None,'escape_preexisting':False,'no_tick_sample':True,
                'requested_window_ticks':[max(0,tick-round(1/dt)),tick+round(2/dt)]})
            self.emit('events',{'type':'strike_start','episode':self.episode,'tick':tick,'global_tick':self.global_tick,
                               'simulation_time':tick*dt,'strike_id':w.stats.strikes,'no_tick_sample':True})
        row={'episode':self.episode,'seed':session.seed,'ticks':session.ticks,'stats':asdict(session.stats),
             'reason':reason,'alive':session.world.fly.alive,'landing_attempts':session.ecology.landing_attempts if session.ecology else 0}
        if w.lifecycle_active:self.lifecycle_metrics.end_episode()
        self.episode_summaries.append(row);self.emit('episodes',row);self.active=False
        for file in self.files.values():file.flush()

    def close(self, session):
        if self.closed:return
        self.finish(session,'quit')
        for file in self.files.values():file.close()
        dt=session.tick_seconds
        for strike in self.strikes:
            first,last=self.episode_ranges[strike['episode']]
            a,b=strike['requested_window_ticks'];end=max(-1,last-first)
            strike['window_ticks']=[a,min(b,end)]
            strike['window_global_ticks']=[first+a,first+min(b,end)]
            strike['window_truncated']=a!=strike['start_tick']-round(1/dt) or b>end
        (self.path/'strikes.json').write_text(json.dumps(self.strikes,indent=2)+'\n',encoding='utf-8')
        stats={key:sum(row['stats'][key] for row in self.episode_summaries) for key in ('strikes','hits','misses','escapes')}
        first_strikes=[st for st in self.strikes if st['strike_id']==1]
        latencies=[(st['escape_tick']-st['threat_onset_tick'])*dt for st in self.strikes
                   if not st.get('escape_preexisting',False) and st['escape_tick'] is not None and st['threat_onset_tick'] is not None and st['escape_tick']>=st['threat_onset_tick']]
        bins=Counter(int((math.degrees(st['attack_direction'])%360)//45)*45 for st in self.strikes)
        n=max(1,self.global_tick)
        def fractions(counts, count):
            return {k:v/count for k,v in sorted(counts.items())} if count else {}
        def distribution(values):
            import numpy as np
            return {'n':len(values),'mean':statistics.mean(values) if values else None,
                    **{name:float(np.percentile(values,q)) if values else None
                       for name,q in (('p50',50),('p75',75),('p90',90),('p95',95),('max',100))}}
        cap=session.config['swatter'].get('physical',{}).get('approach_speed_limit')
        summary={'schema_version':SCHEMA_VERSION,'session_id':self.run_id,'duration_simulation_seconds':self.global_tick*dt,
          'duration_wall_seconds':time.perf_counter()-self.started_wall,'episodes':len(self.episode_summaries),'ticks':self.global_tick,
          **stats,'hit_rate':stats['hits']/stats['strikes'] if stats['strikes'] else None,
          'first_strike_hit_rate':sum(st['outcome']=='hit' for st in first_strikes)/len(first_strikes) if first_strikes else None,
          'incomplete_strikes':sum(st['outcome']=='incomplete' for st in self.strikes),
          'edge_outcomes':{key:self.event_counts[key] for key in ('hit_near_wall','miss_near_wall')},
          'alert_count':self.event_counts['alert_onset'],'escape_count':self.event_counts['escape_onset'],
          'dnp01_threshold_crossings':self.event_counts['threshold_crossing'],
          'escape_latency_seconds':{'n':len(latencies),'mean':statistics.mean(latencies) if latencies else None,
                                    'median':statistics.median(latencies) if latencies else None,
                                    'definition':'first new ESCAPE within 2 s after strike start minus neural threat onset in the indexed window (1 s before to 2 s after); unavailable/preexisting escapes excluded'},
          'tick_populations':{'all':self.global_tick,'alive_post_step':self.alive_tick_count,
                              'definition':'alive means post-step fly.alive; fatal ticks excluded from alive-only statistics'},
          'threat_state_fraction_all':fractions(self.threat_counts,self.global_tick),
          'threat_state_fraction_alive':fractions(self.alive_threat_counts,self.alive_tick_count),
          'ecological_state_fraction_all':fractions(self.ecology_counts,self.global_tick),
          'ecological_state_fraction_alive':fractions(self.alive_ecology_counts,self.alive_tick_count),
          'speed_bl_s_all':distribution(self.all_speeds),'speed_bl_s_alive':distribution(self.alive_speeds),
          'alive_approach':{'physical_speed':distribution(self.approach_speeds),
              'pointer_speed':distribution(self.approach_pointer_speeds),
              'target_error':distribution(self.approach_errors),
              'speed_cap':cap,'fraction_at_95pct_cap':sum(v>=.95*cap for v in self.approach_speeds)/len(self.approach_speeds) if cap and self.approach_speeds else None},
          'speed_bl_s':{'mean':statistics.mean(self.speeds) if self.speeds else None,'peak':max(self.speeds) if self.speeds else None},
          'threat_state_fraction':{k:v/n for k,v in self.threat_counts.items()},'ecological_state_fraction':{k:v/n for k,v in self.ecology_counts.items()},
          'wall_time_seconds':self.wall_ticks*dt,'perimeter_time_seconds':self.perimeter_ticks*dt,'contact_time_seconds':self.contact_ticks*dt,
          'odor_encounters':self.odor_encounters,'landing_attempts':sum(e['landing_attempts'] for e in self.episode_summaries),
          'attack_direction_bins_degrees':dict(sorted(bins.items())),'full_brain_recorded':False,'learning_updates':0}
        if session.world.lifecycle_active:
            summary['schema_version'] = 4
            summary['lifecycle'] = self.lifecycle_metrics.report()
            summary['landing_attempts_status'] = ('legacy ecology LAND_OR_PERCH counter; the legacy timer is '
                'disabled while the lifecycle is active, so this is not the M1.8 landing count. '
                'Use lifecycle.events for authoritative landing behavior.')
        (self.path/'summary.json').write_text(json.dumps(summary,indent=2)+'\n',encoding='utf-8')
        def describe(values):
            if not values['n']:return 'n=0; no eligible samples'
            return ', '.join([f"n={values['n']}"]+[f"{key}={values[key]:.3f}" for key in ('mean','p50','p75','p90','max')])
        approach=summary['alive_approach']
        near_cap=approach['fraction_at_95pct_cap']
        near_cap_text='unavailable' if near_cap is None else f"{100*near_cap:.2f}%"
        # The legacy ecology counter is disabled while the lifecycle owns landing, so it
        # must not be presented as the milestone landing count.
        headline=[];legacy_landing=f"Odor encounters: {self.odor_encounters}; landing attempts: {summary['landing_attempts']}."
        if session.world.lifecycle_active:
            life=summary['lifecycle'];events=life['events'];fractions=life['fractions']
            percent=lambda v:'n/a' if v is None else f"{100*v:.2f}%"
            headline=[f"Lifecycle (authoritative for M1.8-A landing behavior): approach onsets {events['approach_onset']};"
              f" commits {events['approach_commit']}; aborts {events['approach_abort']};"
              f" touchdowns {events['touchdown']}; voluntary takeoffs {events['voluntary_takeoff']};"
              f" escape takeoffs {events['escape_takeoff']}."
              f" Alive airborne {percent(fractions['airborne'])}; perched {percent(fractions['perched'])};"
              f" feeding {percent(fractions['feeding'])}."]
            legacy_landing=(f"Odor encounters: {self.odor_encounters}; legacy ecology landing attempts:"
              f" {summary['landing_attempts']} (LAND_OR_PERCH timer disabled by the lifecycle;"
              " not the M1.8 landing count).")
        lines=['# Human session summary' ,'',f"Session: `{self.run_id}`",f"Arena: {self.manifest['arena']}; mode: {self.manifest['mode']}; fixed sampling: {1/dt:g} Hz.",'',
          f"Duration: {self.global_tick*dt:.2f} simulation seconds; episodes: {summary['episodes']}; ticks: {self.global_tick}.",
          *headline,
          f"Strikes: {stats['strikes']}; hits: {stats['hits']}; misses: {stats['misses']}; incomplete: {summary['incomplete_strikes']}.",
          f"Hit rate: {summary['hit_rate']}; first-strike hit rate: {summary['first_strike_hit_rate']}.",
          f"ALERT onsets: {summary['alert_count']}; ESCAPE onsets: {summary['escape_count']}; DNp01 crossings: {summary['dnp01_threshold_crossings']}.",
          f"Escape latency (s): {summary['escape_latency_seconds']}.",f"Speed all ticks (BL/s): {describe(summary['speed_bl_s_all'])}.",
          f"Speed alive ticks (BL/s): {describe(summary['speed_bl_s_alive'])}.",
          f"Tick populations: {summary['tick_populations']}.",
          f"Threat-state fractions all / alive: {summary['threat_state_fraction_all']} / {summary['threat_state_fraction_alive']}.",
          f"Ecological-state fractions all / alive: {summary['ecological_state_fraction_all']} / {summary['ecological_state_fraction_alive']}.",
          f"Alive APPROACH head speed (units/s): {describe(approach['physical_speed'])}.",
          f"Alive APPROACH pointer speed (units/s): {describe(approach['pointer_speed'])}; first episode samples excluded.",
          f"Alive APPROACH at >=95% of speed cap: {near_cap_text}; cap={cap} units/s.",
          f"Alive APPROACH target error (units): {describe(approach['target_error'])}.",
          f"Wall / perimeter / contact time (s): {self.wall_ticks*dt:.2f} / {self.perimeter_ticks*dt:.2f} / {self.contact_ticks*dt:.2f}.",
          legacy_landing,
          f"Near-wall outcomes: {summary['edge_outcomes']}.",
          f"Attack direction bins (degrees): {summary['attack_direction_bins_degrees']}.",'',
          'Tick logs contain offline WORLD data. Only policy_observations.jsonl contains the unchanged whitelisted observations.',
          'Statistics are descriptive, not learning or biological validation. All-tick fractions include dead ticks; alive-only fractions exclude them. Neural values are held after death. Legacy speed_bl_s uses pre-step alive ticks; prefer the explicit all/alive fields.',
          'Pause duration is wall time, not additional brain samples. Event windows are inclusive index ranges in strikes.json.',
          'No full-brain recording or policy learning occurred. See manifest.json for source snapshot hashes, configuration and calibration.']
        if session.world.lifecycle_active:
            lines += ['', 'Lifecycle simulator metrics (not real activity-budget estimates):',
                      json.dumps(summary['lifecycle'], indent=2)]
        (self.path/'REPORT.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
        profile_path=self.root/'profile.json'
        profile=json.loads(profile_path.read_text(encoding='utf-8')) if profile_path.exists() else {
            'schema_version':1,'episodes_played':0,'strikes_survived':0,'hits_received':0,'policy_checkpoint':None,'learning_updates':0}
        profile['episodes_played']+=len(self.episode_summaries)
        profile['strikes_survived']+=stats['misses'];profile['hits_received']+=stats['hits']
        temp=profile_path.with_suffix('.tmp');temp.write_text(json.dumps(profile,indent=2)+'\n',encoding='utf-8');temp.replace(profile_path)
        self.manifest['closed_cleanly']=True;self.manifest['tick_count']=self.global_tick
        (self.path/'manifest.json').write_text(json.dumps(self.manifest,indent=2)+'\n',encoding='utf-8')
        self.closed=True
