"""M1.5 predefined encounter distribution and arena sanity, never policy fitting.

    python tools/encounter_sanity.py

Forty-eight conditions: two seeds, eight approach axes, three motion profiles.
World-side scripted player coordinates are never policy observations.
"""
from __future__ import annotations
import json
import math
import os
from pathlib import Path
import sys
import time

ROOT=Path(__file__).resolve().parent.parent
sys.path.insert(0,str(ROOT))
os.environ.setdefault('NUMBA_NUM_THREADS','4')
os.environ.setdefault('MPLCONFIGDIR',str(ROOT/'artifacts'/'matplotlib'))
import numpy as np
from game.session import Session,load_config,calibration_provenance
from game.recording import InteractionRecorder
from game.world import World


def main():
    started=time.perf_counter()
    config=load_config(ROOT/'game_play_config.json')
    out=ROOT/'artifacts'/'m1-5';out.mkdir(parents=True,exist_ok=True)
    recorder=InteractionRecorder(out/'encounters')
    session=Session(config,seed=101,mode='evaluation',recorder=recorder)
    trials=[];retinal_sequences=[]
    try:
        index=0
        for seed in (101,102):
            for angle in np.arange(8)*math.pi/4:
                for profile in ('linear','accelerating','leading'):
                    if index:session.reset(seed)
                    index+=1
                    values=[];hit=False;response=None;heading=session.world.fly.heading
                    for tick in range(150):
                        w=session.world;f=w.fly
                        progress=max(0,min(1,(tick-60)/45))
                        distance=700-660*(progress**2 if profile=='accelerating' else progress)
                        lead=.18 if profile=='leading' else 0
                        pointer=(f.x-math.cos(angle)*distance+f.vx*lead,
                                 f.y-math.sin(angle)*distance+f.vy*lead)
                        event=session.tick(pointer=pointer,strike=tick==108)
                        hit |= event.hit
                        if response is None and tick>=60 and (session.fly_loop.last_action.escape or abs(session.fly_loop.last_action.turn)>.03):response=tick*.02
                        r=session.last_retina;m=session.fly_loop.last_motor
                        values.append([r.theta,r.theta_dot,r.azimuth,m.dnp01_left,m.dnp01_right,
                                       m.dna02_left,m.dna02_right,w.yaw_rate,w.wall_contact])
                    a=np.asarray(values);retinal_sequences.append(a[60:121,:3])
                    trials.append({'seed':seed,'approach_degrees':float(math.degrees(angle)),
                                   'profile':profile,'initial_heading':heading,
                                   'actual_attack_angle':w.swatter.orientation,
                                   'hit':hit,'first_response_seconds':response,
                                   'theta_range':[float(a[:,0].min()),float(a[:,0].max())],
                                   'theta_dot_range':[float(a[:,1].min()),float(a[:,1].max())],
                                   'azimuth_range':[float(a[:,2].min()),float(a[:,2].max())],
                                   'dnp01_peak_LR':a[:,3:5].max(axis=0).tolist(),
                                   'dna02_peak_LR':a[:,5:7].max(axis=0).tolist(),
                                   'max_yaw_rad_s':float(abs(a[:,7]).max()),'constraint_ticks':int(a[:,8].sum())})
                    print(f'condition {index}/48 seed={seed} angle={math.degrees(angle):.0f} profile={profile} hit={hit}',flush=True)
    finally:session.close()
    arena=[];trajectory_arrays=[]
    for label,cfg in (('LAB',load_config()),('GAME',config)):
        summaries=[]
        for seed in (17,101,102,103,104):
            w=World(cfg,seed);rows=[];slow=longest_slow=near_run=longest_near=0
            for _ in range(6000):
                before=(w.fly.x,w.fly.y);w.tick(.02);f=w.fly
                speed=math.hypot(f.vx,f.vy)
                slip=(math.atan2(f.vy,f.vx)-f.heading+math.pi)%(2*math.pi)-math.pi if speed>1e-9 else 0
                slow=slow+1 if speed<40 else 0;longest_slow=max(longest_slow,slow)
                near_run=near_run+1 if w.wall_cue.proximity>=.45 else 0;longest_near=max(longest_near,near_run)
                rows.append([f.x,f.y,w.wall_cue.proximity,w.wall_contact,speed,slip,w.yaw_rate,math.dist(before,(f.x,f.y))])
            a=np.asarray(rows);trajectory_arrays.append((label,seed,a))
            summaries.append({'seed':seed,'near_wall_fraction':float((a[:,2]>=.45).mean()),
                              'constraint_ticks':int(a[:,3].sum()),'min_speed':float(a[:,4].min()),
                              'max_slip_degrees':float(np.degrees(abs(a[:,5]).max())),
                              'max_yaw_rad_s':float(abs(a[:,6]).max()),'max_step_px':float(a[:,7].max()),
                              'longest_below_40_seconds':longest_slow*.02,'longest_near_wall_seconds':longest_near*.02})
        arena.append({'arena':label,'seconds_per_seed':120,'trials':summaries,
                      'near_wall_fraction':sum(r['near_wall_fraction'] for r in summaries)/5})
    strike_records=[json.loads(line) for line in (recorder.path/'strikes.jsonl').read_text(encoding='utf-8').splitlines()]
    by_episode={r['episode']:r for r in strike_records}
    for i,trial in enumerate(trials,1):
        trial['actual_attack_angle']=by_episode[i]['approach_angle']
        trial['actual_attack_speed']=by_episode[i]['approach_speed']
    unique=len({np.round(a,7).tobytes() for a in retinal_sequences})
    result={'provenance':calibration_provenance(config),'scenario':'2 seeds x 8 approach axes x 3 pointer profiles; no tuning to hit rate',
            'trials':trials,'distinct_retinal_sequences_rounded_1e_7':unique,'hits':sum(r['hit'] for r in trials),
            'responses':sum(r['first_response_seconds'] is not None for r in trials),
            'arena_comparison':arena,'recording_run':str(recorder.path.relative_to(ROOT)),
            'wall_seconds':time.perf_counter()-started,
            'limitations':'Finite scripted conditions, not a population estimate or a human difficulty score. No optimizer or training.'}
    (ROOT/'results/game/encounters_m1_5.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    np.savez_compressed(out/'trajectories.npz',**{f'{label}_{seed}':a for label,seed,a in trajectory_arrays})
    plot(result,retinal_sequences,trajectory_arrays)
    print(json.dumps({'hits':result['hits'],'responses':result['responses'],'unique_retinas':unique,'arenas':arena},indent=2))
    assert unique>=40,'encounters unexpectedly collapsed to repeated retinal sequences'
    assert arena[1]['near_wall_fraction']<arena[0]['near_wall_fraction']
    return 0


def plot(result,sequences,trajectories):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    fig,axes=plt.subplots(1,3,figsize=(15,4.5))
    for label,seed,a in trajectories:
        if label=='GAME':axes[0].plot(a[:,0],a[:,1],lw=.6,alpha=.7,label=str(seed))
    axes[0].set(xlim=(0,3840),ylim=(2160,0),title='GAME: 120 s / seed, no neural threats',xlabel='logical x',ylabel='logical y')
    axes[0].set_aspect('equal');axes[0].legend(fontsize=7,ncol=3)
    for a in sequences:axes[1].plot(np.arange(len(a))*.02+1.2,a[:,1],alpha=.3,lw=.7)
    axes[1].axvline(2.16,color='black',ls='--',lw=.8)
    axes[1].set(title='48 scripted encounters; dashed = click',xlabel='simulation seconds',ylabel='retinal theta_dot (rad/s)')
    peak=np.array([r['dnp01_peak_LR'] for r in result['trials']])
    axes[2].scatter(peak[:,0],peak[:,1],c=[r['approach_degrees'] for r in result['trials']],cmap='hsv',s=25)
    axes[2].set(title='Descending response diversity',xlabel='peak DNp01 left',ylabel='peak DNp01 right')
    fig.suptitle('M1.5 environment diagnostics — no learning or biological validation')
    fig.tight_layout();fig.savefig(ROOT/'results/game/encounters_m1_5.png',dpi=150);plt.close(fig)


if __name__=='__main__':raise SystemExit(main())
