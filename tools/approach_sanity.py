"""Compare paddle mechanics on fixed human input; no outcome or neural counterfactual claim."""
import argparse
import copy
import json
import math
from pathlib import Path
import sys
import numpy as np
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from game.world import World


def distribution(values):
    a=np.asarray(values,dtype=float)
    return {'n':len(a),'mean':float(a.mean()) if len(a) else None,
            **{key:float(np.percentile(a,q)) if len(a) else None for key,q in
               [('p50',50),('p75',75),('p90',90),('max',100)]},
            'fraction_at_95pct_of_1800':float(np.mean(a>=1710)) if len(a) else None}


def compare(session, new_config=None):
    session=Path(session)
    manifest=json.loads((session/'manifest.json').read_text())
    old=manifest['config'];new=new_config if new_config is not None else json.loads((ROOT/'game_room_config.json').read_text())
    rows=[json.loads(line) for line in (session/'ticks.jsonl').open(encoding='utf-8')]
    traces=[[],[]];errors=[[],[]];paired=[[],[]];pointer_speeds=[];previous=None;worlds=None;index=0
    for line in (session/'inputs.jsonl').open(encoding='utf-8'):
        op=json.loads(line)
        if op['kind']=='reset':
            worlds=[World(c,op['seed']) for c in (old,new)]
            for w in worlds:w.collisions_enabled=False;w.fly_motion_enabled=False
            previous=None
        elif op['kind']=='request_strike':
            if op['accepted']:
                for w in worlds:assert w.request_strike()
        elif op['kind']=='tick':
            row=rows[index];index+=1
            for w in worlds:
                if op['pointer'] is not None:w.set_pointer(*op['pointer'])
                if op['strike'] and w.stats.strikes<row['stats']['strikes']:assert w.request_strike()
                w.tick(.02)
            sw=worlds[0].swatter
            for key in ('x','y','vx','vy','height','face','phase_elapsed','orientation'):
                assert getattr(sw,key)==row['swatter'][key],(index-1,key)
            assert sw.phase.value==row['swatter']['phase']
            if row['fly']['alive'] and row['swatter']['phase']=='approach':
                for i,w in enumerate(worlds):
                    traces[i].append(math.hypot(w.swatter.vx,w.swatter.vy))
                    errors[i].append(w.physical_swatter.target_error)
                target=(sw.target_x,sw.target_y)
                if previous is not None:
                    pointer_speeds.append(math.dist(target,previous)/.02)
                    for i,w in enumerate(worlds):paired[i].append(math.hypot(w.swatter.vx,w.swatter.vy))
            previous=(sw.target_x,sw.target_y)
    groups=[]
    for label,lo,hi in [('stationary',0,1),('slow',1,300),('moderate',300,900),('fast',900,1800),('above_cap',1800,float('inf'))]:
        mask=(np.asarray(pointer_speeds)>=lo)&(np.asarray(pointer_speeds)<hi)
        groups.append({'pointer_band':label,'n':int(mask.sum()),
                       'old_near_cap_fraction':float(np.mean(np.asarray(paired[0])[mask]>=1710)) if mask.any() else None,
                       'new_near_cap_fraction':float(np.mean(np.asarray(paired[1])[mask]>=1710)) if mask.any() else None})
    error_distributions=[distribution(e) for e in errors]
    for e in error_distributions:e.pop('fraction_at_95pct_of_1800')
    return {'source_session':session.name,'old_paddle_ticks_exact':index,
            'mask':'historical post-step-alive APPROACH ticks, identical for both controllers',
            'pointer_speed':distribution(pointer_speeds),
            'old_approach':distribution(traces[0]),'new_approach':distribution(traces[1]),
            'old_target_error':error_distributions[0],'new_target_error':error_distributions[1],'pointer_bands':groups,
            'scope':'paddle-only fixed consumed input and accepted-click schedule; historical masks; no new fly, neural or hit-rate prediction'}


def fixtures():
    cfg=json.loads((ROOT/'game_room_config.json').read_text());results={}
    for name,speed in [('slow',100),('moderate',600),('sudden_burst',2000)]:
        w=World(cfg,101);w.collisions_enabled=False;values=[];errors=[]
        for i in range(110):
            displacement=speed*min(max(i-30,0),35)*.02
            w.set_pointer(1920+displacement,388.8);w.tick(.02)
            if 30<=i<65:values.append(math.hypot(w.swatter.vx,w.swatter.vy));errors.append(w.physical_swatter.target_error)
        results[name]={'physical_speed':distribution(values),'maximum_target_error':max(errors)}
    w=World(cfg,101);w.collisions_enabled=False;values=[]
    for _ in range(160):
        w.set_pointer(500,1200);w.tick(.02);values.append(math.hypot(w.swatter.vx,w.swatter.vy))
    results['initial_large_error_stationary_target']={'physical_speed':distribution(values)}
    return results


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--session',type=Path)
    parser.add_argument('--report',type=Path,default=ROOT/'artifacts/m1-7-1/approach-sanity.json')
    args=parser.parse_args();result={'controlled_fixtures':fixtures()}
    if args.session:result['fixed_human_input']=compare(args.session)
    args.report.parent.mkdir(parents=True,exist_ok=True)
    args.report.write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(result,indent=2))


if __name__=='__main__':main()
