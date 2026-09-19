"""Deterministic M1.4 trajectory diagnostics, never a gameplay optimizer.

    python tools/flight_sanity.py

No brain is loaded: this isolates phenomenological locomotion and enclosure
physics. Neural chase/calibration are separate tools. Full traces stay ignored.
"""
from __future__ import annotations
import json
import math
import os
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault('MPLCONFIGDIR', str(ROOT / 'artifacts' / 'matplotlib'))
import numpy as np
from game.enclosure import WallCue
from game.flight import FreeFlightController
from game.saccade import SaccadeActuator
from game.session import calibration_provenance, load_config
from game.world import World

SEEDS = (17, 101, 102, 103, 104)


def distribution(values):
    a=np.asarray(values,dtype=float)
    return {'n':int(a.size), 'min':float(a.min()), 'p50':float(np.median(a)),
            'p95':float(np.percentile(a,95)), 'max':float(a.max()), 'mean':float(a.mean())} if a.size else {'n':0}


def longest_run(flags):
    longest=run=0
    for flag in flags:
        run=run+1 if flag else 0
        longest=max(run,longest)
    return longest


def observe_requests(actuator, clock):
    events=[]
    request=actuator.request
    def observed(kind,angle,peak):
        busy=actuator.active
        accepted=request(kind,angle,peak)
        if accepted:
            if busy and events:
                events[-1]['preempted']=True
            events.append({'time':clock[0], 'kind':kind,
                           'angle_degrees':math.degrees(actuator.angle),
                           'duration_seconds':actuator.duration,
                           'analytic_peak_deg_s':abs(math.degrees(actuator.angle))*math.pi/(2*actuator.duration),
                           'preempted':False})
        return accepted
    actuator.request=observed
    return events


def open_flight(config, seconds=600):
    """No walls: isolate quiet gaps and spontaneous angle distributions."""
    dt=config['sim']['tick_seconds']
    c=FreeFlightController(config['flight'],101)
    a=SaccadeActuator(config['saccades']);clock=[0.0]
    events=observe_requests(a,clock);yaw=[]
    for tick in range(round(seconds/dt)):
        clock[0]=tick*dt;c.update(dt,WallCue(),a);yaw.append(abs(a.step(dt)/dt))
    gaps=[b['time']-a['time']-a['duration_seconds'] for a,b in zip(events,events[1:])]
    by_kind={kind:{'angles_degrees':distribution([abs(e['angle_degrees']) for e in events if e['kind']==kind]),
                   'durations_seconds':distribution([e['duration_seconds'] for e in events if e['kind']==kind])}
             for kind in ('CORRECTION','SACCADE')}
    return {'seed':101,'seconds':seconds,'pulses':len(events), 'by_kind':by_kind,
            'quiet_gaps_seconds':distribution(gaps),
            'onset_intervals_seconds':distribution(np.diff([e['time'] for e in events])),
            'max_tick_yaw_rad_s':max(yaw)},events


def trajectory(config,seed,seconds=120,initial=None):
    w=World(config,seed);f=w.fly;dt=config['sim']['tick_seconds']
    if initial:
        f.x,f.y,f.heading=initial
        f.vx,f.vy=w.baseline_speed*math.cos(f.heading),w.baseline_speed*math.sin(f.heading)
    clock=[0.0];events=observe_requests(w.saccades,clock);rows=[]
    for tick in range(round(seconds/dt)):
        clock[0]=tick*dt;before=(f.x,f.y);w.tick(dt)
        rows.append([f.x,f.y,f.heading,math.hypot(f.vx,f.vy),w.yaw_rate,
                     w.wall_cue.proximity,int(w.wall_contact),math.dist(before,(f.x,f.y))])
    a=np.asarray(rows)
    near=a[:,5]>=config['flight']['boundary']['perimeter_enter_proximity']
    open_space=a[:,5]<=config['flight']['boundary']['perimeter_leave_proximity']
    returns=int(np.sum(open_space[1:] & ~open_space[:-1]))
    avoids=[e for e in events if e['kind']=='AVOID']
    fast_alternations=sum(b['time']-a['time']<.5 and a['angle_degrees']*b['angle_degrees']<0
                          for a,b in zip(avoids,avoids[1:]))
    summary={'seed':seed,'seconds':seconds,'initial':initial,
             'distance_px':float(a[:,7].sum()),'speed_px_s':distribution(a[:,3]),
             'max_step_px':float(a[:,7].max()),'max_actual_yaw_rad_s':float(np.abs(a[:,4]).max()),
             'constraint_ticks':int(a[:,6].sum()),'near_wall_fraction':float(near.mean()),
             'longest_near_wall_seconds':longest_run(near)*dt,
             'longest_below_40_px_s_seconds':longest_run(a[:,3]<40)*dt,
             'returns_to_open_space':returns,'ever_open':bool(open_space.any()),
             'rapid_opposite_avoid_pairs':fast_alternations,
             'requests':{kind:sum(e['kind']==kind for e in events) for kind in sorted({e['kind'] for e in events})}}
    assert summary['max_step_px'] <= w.baseline_speed*dt+1e-8
    assert summary['max_actual_yaw_rad_s'] <= w.max_yaw_rate+1e-8
    assert summary['ever_open']
    assert summary['longest_below_40_px_s_seconds'] < .5
    return summary,a,events


def main():
    started=time.perf_counter();config=load_config()
    output=ROOT/'artifacts'/'m1-4';output.mkdir(parents=True,exist_ok=True)
    free,free_events=open_flight(config)
    summaries=[];traces=[];full=[]
    for seed in SEEDS:
        summary,trace,events=trajectory(config,seed)
        summaries.append(summary);traces.append(trace);full.append({'summary':summary,'events':events,'trace':trace.tolist()})
    starts=((1200,360,0),(80,360,math.pi),(640,80,-math.pi/2),(640,640,math.pi/2),
            (1200,640,math.pi/4),(80,80,-3*math.pi/4),(80,640,3*math.pi/4),(1200,80,-math.pi/4))
    walls=[]
    for seed,initial in enumerate(starts,101):
        summary,trace,events=trajectory(config,seed,15,initial)
        walls.append(summary);full.append({'summary':summary,'events':events,'trace':trace.tolist()})
    record={'provenance':calibration_provenance(config),
            'scope':'No neural input; fixed seeds and predefined scenarios; no survival optimization or biological validation.',
            'tick_seconds':config['sim']['tick_seconds'],
            'body_length_px':config['fly']['body_length_px'],
            'cruise_px_s':config['fly']['baseline_speed'],
            'cruise_BL_s':config['fly']['baseline_speed']/config['fly']['body_length_px'],
            'max_configured_BL_s':config['fly']['max_speed']/config['fly']['body_length_px'],
            'open_flight':free,'enclosure_120s':summaries,'wall_starts_15s':walls,
            'wall_seconds':time.perf_counter()-started}
    (ROOT/'results'/'game'/'flight_m1_4.json').write_text(json.dumps(record,indent=2)+'\n',encoding='utf-8')
    (output/'flight_traces.json').write_text(json.dumps({'open_flight_events':free_events,'trajectories':full}),encoding='utf-8')
    plot(config,traces,free_events)
    print(json.dumps(record,indent=2))
    return 0


def plot(config,traces,events):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib.patches import Rectangle
    fig,axes=plt.subplots(1,3,figsize=(15,4.6))
    ax=axes[0];m=config['world']['margin']
    ax.add_patch(Rectangle((m,m),1280-2*m,720-2*m,fill=False,color='#646a75',lw=3))
    for seed,a in zip(SEEDS,traces): ax.plot(a[:,0],a[:,1],lw=.65,alpha=.7,label=str(seed))
    ax.set(xlim=(0,1280),ylim=(720,0),xlabel='x (px)',ylabel='y (px)',title='120 s / seed: no neural threat input')
    ax.set_aspect('equal');ax.legend(fontsize=7,ncol=5,loc='upper center')
    ax=axes[1]
    for kind in ('CORRECTION','SACCADE'):
        selected=[e for e in events if e['kind']==kind]
        ax.scatter([abs(e['angle_degrees']) for e in selected],
                   [e['duration_seconds'] for e in selected],s=9,alpha=.5,label=kind)
    ax.set(xlabel='Requested pulse angle (degrees)',ylabel='Analytic duration (s)',title='600 s open flight / seed 101');ax.legend(fontsize=8)
    gaps=[b['time']-a['time']-a['duration_seconds'] for a,b in zip(events,events[1:])]
    axes[2].hist(gaps,bins=np.arange(0,6.3,.2),color='#377c9e')
    axes[2].set(xlabel='Observed quiet gap after pulse (s)',ylabel='Count',title='Seeded mixture; 20 ms tick quantization')
    fig.suptitle('M1.4 phenomenological flight diagnostics — not biological validation')
    fig.tight_layout();fig.savefig(ROOT/'results'/'game'/'flight_m1_4.png',dpi=150);plt.close(fig)


if __name__=='__main__':
    raise SystemExit(main())
