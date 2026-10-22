"""Read-only interaction recorder. World/debug data never enters observations.

Records are JSONL, with bounded in-memory pre-strike and internal-history buffers.
All modes currently use frozen policies; no checkpoint loading or update exists.
"""
from __future__ import annotations
from collections import deque
from dataclasses import asdict
import json
import math
from pathlib import Path
import time
import uuid

from .action import MotorState

NEURAL_FIELDS = ('dnp01_left', 'dnp01_right', 'dna02_left', 'dna02_right')


def observation_frame(motor: MotorState, behavior_state: str) -> dict:
    """Explicit future-policy whitelist: no retina, pose, pointer or phase."""
    if type(motor) is not MotorState:
        raise TypeError('policy observation requires MotorState')
    return {'neural': {k: float(getattr(motor,k)) for k in NEURAL_FIELDS},
            'motion': asdict(motor.motion), 'behavior_state': str(behavior_state)}


def policy_observation(motor, behavior_state, history=()):
    for item in history:
        if (set(item) != {"neural","motion","behavior_state"}
                or set(item["neural"]) != set(NEURAL_FIELDS)
                or set(item["motion"]) != {"forward_speed","lateral_speed","yaw_rate","saccade_remaining"}):
            raise ValueError("history must contain only whitelisted internal frames")
    frame=observation_frame(motor,behavior_state)
    # History is constructed by this recorder only, from the same whitelist.
    return {**frame, 'history': [json.loads(json.dumps(x)) for x in history]}


def summary(values):
    return {'min': min(values), 'max': max(values), 'mean': sum(values)/len(values)} if values else None


class InteractionRecorder:
    """Single-writer profile counters plus unique run directory; no policy access."""
    def __init__(self, directory: Path, stride: int = 5):
        if stride < 1: raise ValueError('recorder stride must be positive')
        self.root=Path(directory);self.root.mkdir(parents=True,exist_ok=True)
        self.run_id=time.strftime('%Y%m%dT%H%M%S',time.gmtime())+'-'+uuid.uuid4().hex[:8]
        self.path=self.root/'runs'/self.run_id;self.path.mkdir(parents=True)
        self.files={key:(self.path/(key+'.jsonl')).open('w',encoding='utf-8')
                    for key in ('policy_samples','world_debug','strikes','episodes')}
        self.stride=stride;self.episode=0;self.active=False
        self.history=deque(maxlen=4);self.pre=deque(maxlen=25)
        self.pending=None;self.strike_summaries=[]
        self.closed=False

    def emit(self,key,value):
        self.files[key].write(json.dumps(value,allow_nan=False,separators=(',',':'))+'\n')

    def start(self, session):
        from .session import calibration_provenance
        self.episode+=1;self.active=True;self.history.clear();self.pre.clear()
        self.pending=None;self.strike_summaries=[];self.seen_strikes=0
        self.slow_ticks=self.contact_ticks=0
        self.food_contact_ticks=0;self.object_contact_ticks=0
        self.meta={'schema_version':1,'run_id':self.run_id,'episode':self.episode,
                   'episode_seed':session.seed,'mode':session.mode.name,
                   'policy_name':type(session.policy).__name__, 'updates_enabled':False,
                   'policy_checkpoint':None, 'ecology_enabled':session.ecology is not None, 'spawn':dict(session.world.spawn_state),
                   'tick_seconds':session.tick_seconds,'provenance':calibration_provenance(session.config)}
        if self.episode==1:
            (self.path/'manifest.json').write_text(json.dumps({**self.meta,
                'sample_stride':self.stride,'history_ticks':4,'config':session.config,
                'observation_schema':'neural[DNp01 L/R,DNa02 L/R], MotionState, pre-action behavior_state, four preceding whitelisted frames',
                'time_alignment':'observation and retina before action/physics; outcome and world pose after physics',
                'world_debug_is_not_policy_input':True,
                'sensory_activity':'fired-neuron counts in balanced driven populations per neural tick; injection drive logged separately'},indent=2),encoding='utf-8')

    def capture(self,session,events,before_state):
        if not self.active: return
        w=session.world;motor=session.fly_loop.last_motor
        if motor is None: return
        tick=session.ticks-1;dt=session.tick_seconds
        action=session.fly_loop.last_action
        obs=policy_observation(motor,before_state,self.history)
        self.history.append(observation_frame(motor,before_state))
        retina=asdict(session.last_retina)
        diag=session.policy_diagnostics
        sensory=dict(session.fly_loop.last_sensory_spikes)
        neural={k:float(getattr(motor,k)) for k in NEURAL_FIELDS}
        row={'tick':tick,'retina':retina,'neural':neural,'sensory_spikes':sensory,
             'injection_drive':session.encoder.last_drive,
             'steering':action.turn,'behavior_state':diag.get('behavior_state','UNSPECIFIED')}
        started=events.strike_started or w.stats.strikes>self.seen_strikes
        if started:
            self.pending={'strike':w.stats.strikes,'click_tick':tick,
                          'approach_angle':w.swatter.orientation,'approach_speed':w.swatter.attack_speed,
                          'rows':list(self.pre),'hit':False}
            self.seen_strikes=w.stats.strikes
        if self.pending:
            self.pending['rows'].append(row)
            self.pending['hit'] |= events.hit
            if events.hit or events.strike_resolved:
                self._resolve_strike(tick)
        self.pre.append(row)
        room_analysis = None
        if w.room is not None:
            room_analysis = {'sense':asdict(session.last_ecological_sense) if session.last_ecological_sense is not None else None,
                             'controller':session.ecology.diagnostics() if session.ecology is not None else None,
                             'command':asdict(w.ecological_command) if w.ecological_command is not None else None,
                             'applied_target_speed_bl_s':w.applied_target_speed/w.body_length,
                             'object_contact':w.object_contact,
                             'world':w.room.debug(w.fly,w.time_seconds)}
            self.food_contact_ticks += int(room_analysis['world']['food_surface_overlap'])
            self.object_contact_ticks += int(w.object_contact)
        speed=math.hypot(w.fly.vx,w.fly.vy)
        self.slow_ticks = self.slow_ticks+1 if w.fly.alive and speed < .15*(w.applied_target_speed if w.room is not None else w.baseline_speed) else 0
        self.contact_ticks = self.contact_ticks+1 if w.wall_contact else 0
        flags=[]
        if self.slow_ticks*dt >= .5: flags.append('sustained_stall')
        if self.contact_ticks*dt >= .5: flags.append('prolonged_wall_contact')
        if w.sideslip and speed>1e-9:
            slip=(math.atan2(w.fly.vy,w.fly.vx)-w.fly.heading+math.pi)%(2*math.pi)-math.pi
            if abs(slip)>math.radians(w.sideslip['max_degrees'])+1e-8: flags.append('sideslip_cap_exceeded')
        if not all(math.isfinite(v) for v in (w.fly.x,w.fly.y,speed,w.yaw_rate)): flags.append('nonfinite_motion')
        if speed>w.max_speed+1e-6: flags.append('speed_cap_exceeded')
        if abs(w.yaw_rate)>w.max_yaw_rate+1e-6: flags.append('yaw_cap_exceeded')
        if tick%self.stride==0 or started or events.hit or events.strike_resolved or action.escape or action.saccade or w.saccades.last_delta or w.wall_contact:
            key={'episode':self.episode,'tick':tick}
            self.emit('policy_samples',{**key,'observation':obs,'action':asdict(action),
                       'maneuver':w.saccades.kind,
                       'actuator':{'active_requested_angle_radians':w.saccades.angle,
                                   'pulse_duration_seconds':w.saccades.duration,
                                   'remaining_seconds':w.saccades.remaining,
                                   'tick_yaw_delta':w.saccades.last_delta,
                                   'total_yaw_rate':w.yaw_rate},
                       'outcome':{'hit':events.hit,'miss':events.strike_resolved and not self.pending and not events.hit,
                                  'alive':w.fly.alive,'survival_seconds':w.stats.survival_seconds,
                                  'wall_contact':w.wall_contact,'pathological_flags':flags}})
        self.emit('world_debug',{'episode':self.episode,'tick':tick,**row,'strike_started':started,'fly_pose':{'x':w.fly.x,'y':w.fly.y,'heading':w.fly.heading},
                       'pointer':{'x':w.swatter.target_x,'y':w.swatter.target_y},
                       'swatter':asdict(w.swatter)|{'phase':w.swatter.phase.value},'room_analysis':room_analysis})
        if tick%50==0:
            for file in self.files.values():file.flush()
        if events.hit:self.finish(session,'hit')

    def _resolve_strike(self,tick):
        strike=self.pending;rows=strike.pop('rows');strike['resolved_tick']=tick
        strike['outcome']='incomplete' if strike.get('incomplete') else 'hit' if strike['hit'] else 'miss'
        # Analysis-only onset rule; never supplied to the policy.
        onset=next((r['tick'] for r in rows if r['retina']['theta']>.1 and r['retina']['theta_dot']>.2),strike['click_tick'])
        strike['threat_onset_tick']=onset
        strike['onset_rule']='first theta>0.1 and theta_dot>0.2 in 0.5s pre-strike/strike window, otherwise click'
        strike['retina']={k:summary([r['retina'][k] for r in rows]) for k in ('theta','theta_dot','azimuth')}
        # Circular azimuth is also retained as a time sequence, avoiding a
        # misleading average across the -1/+1 bearing wrap.
        strike['retina_sequence']=[{'tick':r['tick'],**r['retina']} for r in rows]
        strike['neural']={k:summary([r['neural'][k] for r in rows]) for k in NEURAL_FIELDS}
        strike['sensory_spikes']={k:summary([r['sensory_spikes'][k] for r in rows]) for k in rows[0]['sensory_spikes']}
        strike['injection_drive']={k:summary([r['injection_drive'].get(k,0) for r in rows]) for k in rows[-1]['injection_drive']}
        strike['steering']=summary([r['steering'] for r in rows])
        self.strike_summaries.append(strike);self.pending=None

    def finish(self,session,reason):
        if not self.active:return
        if self.pending:
            self.pending['incomplete']=True
            self._resolve_strike(max(0,session.ticks-1))
        w=session.world;dt=session.tick_seconds
        for strike in self.strike_summaries:
            strike.update(episode=self.episode,episode_seed=session.seed,spawn=dict(w.spawn_state),
                          initial_heading=w.spawn_state['heading'],
                          survival_after_threat_seconds=max(0,w.stats.survival_seconds-strike['threat_onset_tick']*dt),
                          right_censored=w.fly.alive)
            self.emit('strikes',strike)
        self.emit('episodes',{**self.meta,'termination':reason,'stats':asdict(w.stats),
                              'right_censored':w.fly.alive,'ticks':session.ticks,
                              'ecology_summary':{'food_overlap_ticks':self.food_contact_ticks, 'object_contact_ticks':self.object_contact_ticks,
                              'landing_attempts':session.ecology.landing_attempts if session.ecology is not None else 0}})
        profile_path=self.root/'profile.json'
        profile=json.loads(profile_path.read_text(encoding='utf-8')) if profile_path.exists() else {
            'schema_version':1,'episodes_played':0,'strikes_survived':0,'hits_received':0,
            'policy_checkpoint':None,'learning_updates':0}
        profile['episodes_played']+=1;profile['strikes_survived']+=w.stats.misses;profile['hits_received']+=w.stats.hits
        temp=profile_path.with_suffix('.tmp');temp.write_text(json.dumps(profile,indent=2),encoding='utf-8');temp.replace(profile_path)
        self.active=False
        for file in self.files.values():file.flush()

    def close(self,session):
        if self.closed:return
        self.finish(session,'quit')
        for file in self.files.values():file.close()
        self.closed=True
