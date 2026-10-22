"""Reproducible M1.6 ecology diagnostics; no fitting, learning or difficulty score."""
import os
os.environ.setdefault('NUMBA_NUM_THREADS','4')
import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from collections import Counter
import copy
from dataclasses import asdict
import json
import math
import time
import numpy as np
from game.world import World
from game.ecology import EcologicalController, ThreatState
from game.room import EcologicalProjector
from game.session import Session, load_config, calibration_provenance
from game.recording import InteractionRecorder


def metrics(rows,states,wall,contact):
    a=np.asarray(rows)
    return {'state_seconds':{k:v*.02 for k,v in sorted(states.items())},
            'speed_bl_s_min_mean_max':[float(a[:,2].min()),float(a[:,2].mean()),float(a[:,2].max())],
            'odor_max':float(a[:,3].max()),'max_yaw_rad_s':float(abs(a[:,4]).max()),
            'near_wall_fraction':wall/len(a),'object_contact_ticks':contact,
            'path_length_units':float(np.linalg.norm(np.diff(a[:,:2],axis=0),axis=1).sum())}


def main():
    started=time.perf_counter();config=load_config(ROOT/'game_room_config.json')
    out=ROOT/'artifacts/m1-6';out.mkdir(exist_ok=True)
    control=[];arrays={}
    for variant in ('room','odor_off','wind_reversed'):
        cfg=copy.deepcopy(config)
        if variant=='odor_off':cfg['room']['food']['emission_strength']=0
        if variant=='wind_reversed':cfg['room']['wind']['direction_degrees']=180
        for seed in (101,102,103,104,105):
            w=World(cfg,seed);e=EcologicalController(cfg['ecology'],seed);p=EcologicalProjector(cfg['room']['sensing'])
            rows=[];states=Counter();wall=contacts=0
            for i in range(6000):
                sense=p.project(w.room,w.fly,w.time_seconds,.02)
                w.ecological_command=e.step(sense,ThreatState.CALM,.02)
                previous=(w.fly.x,w.fly.y);w.tick(.02)
                assert math.dist(previous,(w.fly.x,w.fly.y))<=w.max_speed*.02+1e-6
                assert abs(w.yaw_rate)<=w.max_yaw_rate
                rows.append([w.fly.x,w.fly.y,w.body_lengths_per_second,sense.odor,w.yaw_rate])
                states[e.state]+=1;wall+=w.wall_cue.proximity>=.45;contacts+=w.object_contact
            result={'variant':variant,'seed':seed,'seconds':120,'landing_attempts':e.landing_attempts,**metrics(rows,states,wall,contacts)}
            assert not ({'ALERT','ESCAPE'} & set(states))
            control.append(result);arrays[variant+'_'+str(seed)]=np.asarray(rows)
            print(variant,seed,result['state_seconds'],flush=True)
    # Real connectome idle-room traces: swatter parked in the corner, no clicks.
    # The ecological-only controls above intentionally do not step MaleCNS.
    recorder=InteractionRecorder(out/'idle-records')
    session=Session(config,seed=101,mode='evaluation',recorder=recorder)
    neural=[]
    try:
        for index,seed in enumerate((101,102,103)):
            if index:session.reset(seed)
            rows=[];states=Counter();threats=Counter();wall=contacts=0
            for i in range(3000):
                session.tick(pointer=(0,0));w=session.world;sense=session.last_ecological_sense
                rows.append([w.fly.x,w.fly.y,w.body_lengths_per_second,sense.odor,w.yaw_rate])
                states[session.ecology.state]+=1;threats[session.policy_diagnostics.get('behavior_state','UNSPECIFIED')]+=1
                wall+=w.wall_cue.proximity>=.45;contacts+=w.object_contact
            neural.append({'seed':seed,'seconds':60,'landing_attempts':session.ecology.landing_attempts,
                           'neural_state_seconds':{k:v*.02 for k,v in threats.items()},**metrics(rows,states,wall,contacts)})
            arrays['neural_'+str(seed)]=np.asarray(rows)
            print('neural idle',seed,neural[-1]['state_seconds'],flush=True)
        # Six reproducible actual visual encounters, independent of ecology-only tests.
        encounters=[]
        for angle in (0,60,120,180,240,300):
            session.reset(101+angle)
            responses=Counter();hit=False
            for tick in range(160):
                f=session.world.fly;distance=700-660*max(0,min(1,(tick-60)/45));a=math.radians(angle)
                event=session.tick(pointer=(f.x-math.cos(a)*distance,f.y-math.sin(a)*distance),strike=tick==108)
                responses[session.ecology.state]+=1;hit|=event.hit
                if event.hit:break
            encounters.append({'approach_degrees':angle,'hit':hit,'ecological_states':dict(responses),
                               'strikes':session.stats.strikes,'escapes':session.stats.escapes})
    finally:session.close()
    result={'provenance':calibration_provenance(config),'ecology_controls':control,'real_neural_idle':neural,
            'visual_encounters':encounters,'recording_run':str(recorder.path.relative_to(ROOT)),
            'wall_seconds':time.perf_counter()-started,
            'limitations':'Finite scripted diagnostics. No optimized parameters, odor localization success metric, learning or biological validation.'}
    (ROOT/'results/game/room_m1_6.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    np.savez_compressed(out/'room-trajectories.npz',**arrays)
    plot(config,arrays,control,neural)
    print(json.dumps({'runtime':result['wall_seconds'],'controls':len(control),'neural_idle':neural,'encounters':encounters},indent=2))


def plot(config,arrays,control,neural):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from game.room import RoomEnvironment
    room=RoomEnvironment(config['room'],101)
    fig,axes=plt.subplots(2,2,figsize=(12,8))
    xs=np.linspace(0,3840,100);ys=np.linspace(0,2160,60)
    z=np.array([[room.concentration(x,y,0) for x in xs] for y in ys])
    im=axes[0,0].imshow(z,extent=(0,3840,2160,0),cmap='YlGn',alpha=.7,vmin=0,vmax=1)
    for seed in (101,102,103):
        a=arrays['neural_'+str(seed)];axes[0,0].plot(a[:,0],a[:,1],lw=.6,label=str(seed))
    for o in room.surfaces():axes[0,0].add_patch(plt.Circle((o['x'],o['y']),o['radius'],fill=False,color='black'))
    axes[0,0].set(title='60 s idle ROOM: real neural loop; seed-101 plume at t=0',xlabel='logical x',ylabel='logical y')
    axes[0,0].legend(fontsize=7);fig.colorbar(im,ax=axes[0,0],label='local concentration (arbitrary units)',shrink=.6)
    a=arrays['neural_101'];t=np.arange(len(a))*.02
    axes[0,1].plot(t,a[:,2]);axes[0,1].set(title='Seed 101: actual speed',xlabel='simulation seconds',ylabel='body lengths / s')
    axes[1,0].plot(t,a[:,3],color='green');axes[1,0].axhline(config['ecology']['odor_on'],color='black',ls='--',lw=.8)
    axes[1,0].set(title='Same trajectory: local odor; dashed = on threshold',xlabel='simulation seconds',ylabel='concentration')
    variants=['room','odor_off','wind_reversed'];states=['EXPLORE','TRANSIT','ODOR_TRACK','ODOR_SEARCH','LAND_OR_PERCH']
    bottom=np.zeros(3)
    for state in states:
        values=np.array([sum(r['state_seconds'].get(state,0) for r in control if r['variant']==v)/600 for v in variants])
        axes[1,1].bar(variants,values,bottom=bottom,label=state);bottom+=values
    axes[1,1].set(title='Ecology-only controls: 5 seeds x 120 s each',ylabel='fraction of simulation time',ylim=(0,1))
    axes[1,1].legend(fontsize=7,loc='upper right')
    fig.suptitle('M1.6 ROOM diagnostics: environment and controller checks, no learning')
    fig.tight_layout();fig.savefig(ROOT/'results/game/room_m1_6.png',dpi=150);plt.close(fig)


if __name__=='__main__':main()
