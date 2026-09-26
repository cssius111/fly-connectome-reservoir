"""M1.8-A reproducible lifecycle diagnostics, frozen neural weights and replay."""
import os
os.environ.setdefault('NUMBA_NUM_THREADS', '4')
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
import hashlib
import json
import math
import time
import numpy as np
from game.action import Action, MotionState
from game.ecology import ThreatState
from game.session import Session, load_config, resolve_escape_threshold
from game.session_recording import HumanSessionRecorder
from game.replay import replay_session
from game.world import World, Fly


def main():
    started=time.perf_counter()
    out=ROOT/'artifacts/m1_8_a';out.mkdir(exist_ok=True)
    config=load_config(ROOT/'game_room_config.json')
    records=[];traces=[];brain=None;weight_digest=None
    for scenario,ticks in (('voluntary',1200),('perched_threat',340),('approach_threat',120)):
        recorder=HumanSessionRecorder(out/'sessions',config_file=ROOT/'game_room_config.json')
        session=Session(config,brain=brain,seed=255,mode='evaluation',recorder=recorder)
        brain=session.brain
        digest=hashlib.sha256(np.ascontiguousarray(brain.weights).view(np.uint8)).hexdigest()
        if weight_digest is None:weight_digest=digest
        assert digest==weight_digest
        rows=[];events=[]
        try:
            for tick in range(ticks):
                f=session.world.fly
                chase=(scenario=='perched_threat' and tick>=240) or (scenario=='approach_threat' and tick>=10)
                pointer=(f.x,f.y) if chase else (1920,388.8)
                session.tick(pointer=pointer)
                life=session.world.lifecycle
                rows.append({'tick':tick,'time':(tick+1)*session.tick_seconds,
                             'speed_bl_s':session.world.body_lengths_per_second,'x':f.x,'y':f.y,
                             'mode':life.mode,'extent':life.last_sense.angular_extent,
                             'expansion':life.last_sense.angular_expansion,
                             'retinal_expansion':session.last_retina.theta_dot,
                             'dnp01':session.fly_loop.last_motor.dnp01_total})
                events.extend({'tick':tick,'post_step_seconds':(tick+1)*session.tick_seconds,**event,
                               'profile':dict(life.applied_profile)} for event in life.events)
        finally:session.close()
        assert hashlib.sha256(np.ascontiguousarray(brain.weights).view(np.uint8)).hexdigest()==weight_digest
        summary=load_config(recorder.path/'summary.json')
        replay=replay_session(recorder.path)
        kinds={e['type'] for e in events}
        if scenario=='voluntary':assert {'touchdown','voluntary_takeoff'}<=kinds
        if scenario=='perched_threat':assert 'escape_takeoff' in kinds
        if scenario=='approach_threat':assert any(e['type']=='approach_abort' and e['reason']=='neural_escape' for e in events)
        records.append({'scenario':scenario,'seed':255,'ticks':ticks,'events':events,
                        'simulator_metrics':summary['lifecycle'],'replay':replay,
                        'recording_directory':str(recorder.path),'strikes':summary['strikes']})
        traces.append((scenario,rows))
        print(scenario,summary['lifecycle']['events'],'exact replay',replay['ticks_verified'],flush=True)
    # A fast oblique fly-by: controller gets local cues, never a destination.
    world=World(config,101);world.fly=Fly(1220,1190,-600,0,math.pi)
    aborts=[]
    for tick in range(600):
        m=world.motion_state();life=world.lifecycle
        life.step(world.room.landing_sense(world.fly,world.time_seconds,world.contact_surface_id),
                  MotionState(m.forward_speed/world.body_length,m.lateral_speed/world.body_length,m.yaw_rate,m.saccade_remaining),
                  ThreatState.CALM,.02)
        world.tick(.02,Action())
        aborts.extend({'tick':tick,**e} for e in life.events)
    assert any(e['type']=='approach_abort' for e in aborts)
    result={'label':'simulator scenario diagnostics; not biological validation or natural activity budgets',
            'neural_reference':'adult male Drosophila melanogaster (MaleCNS)',
            'scenarios':records,'oblique_flyby_events':aborts,
            'runtime_weight_sha256_before_and_after':weight_digest,'frozen_weights':True,
            'calibrations':{arena:vars(resolve_escape_threshold(load_config(ROOT/path))) for arena,path in
                            (('lab','game_config.json'),('game','game_play_config.json'),('room','game_room_config.json'))},
            'elapsed_seconds':time.perf_counter()-started}
    (out/'lifecycle-diagnostics.json').write_text(json.dumps(result,indent=2)+'\n')
    os.environ.setdefault('MPLCONFIGDIR',str(ROOT/'artifacts/matplotlib'))
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    fig,axes=plt.subplots(3,2,figsize=(12,9),constrained_layout=True)
    for index,(name,rows) in enumerate(traces):
        t=[r['time'] for r in rows]
        axes[index,0].plot(t,[r['speed_bl_s'] for r in rows],label='Actual speed')
        axes[index,0].set(title=name.replace('_',' '),ylabel='Ground speed (BL/s)',xlabel='Simulation seconds')
        axes[index,1].plot(t,[r['dnp01'] for r in rows],label='DNp01 sum')
        axes[index,1].axhline(1.45,color='red',linestyle='--',label='Fixed threshold')
        axes[index,1].set(ylabel='DNp01 trace',xlabel='Simulation seconds')
        for event in records[index]['events']:
            if event['type'] in ('touchdown','voluntary_takeoff','escape_takeoff','approach_abort'):
                x=event['post_step_seconds'];axes[index,0].axvline(x,color='gray',alpha=.5)
                axes[index,0].annotate(event['type'].replace('_',' '),(x,0),rotation=90,va='bottom',fontsize=8)
        axes[index,1].legend(fontsize=8)
    fig.suptitle('M1.8-A: deterministic simulator scenarios, not measured fly activity budgets')
    fig.savefig(out/'lifecycle-diagnostics.png',dpi=150);plt.close(fig)
    print('elapsed',result['elapsed_seconds'],flush=True)


if __name__=='__main__':main()
