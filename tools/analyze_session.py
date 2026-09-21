"""Per-tick human input and approach analysis, with integrity and denominator checks."""
import argparse,hashlib,json,math,sys
from pathlib import Path
from collections import Counter,deque
import numpy as np
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from game.session_recording import canonical_hash
parser=argparse.ArgumentParser(description="Read-only fixed-tick human session diagnostics; derivatives are logical consumed inputs, not hand kinematics.")
parser.add_argument('session',type=Path)
parser.add_argument('--output-dir',type=Path)
args=parser.parse_args()
folder=args.session.resolve()
m=json.loads((folder/"manifest.json").read_text());dt=m["tick_seconds"];cap=m["config"]["swatter"]["physical"]["approach_speed_limit"]
out=(args.output_dir or ROOT/'artifacts/session-analysis'/folder.name).resolve()
if out.is_relative_to(folder):raise ValueError('analysis output must stay outside the immutable session directory')
out.mkdir(parents=True,exist_ok=True)
hashes={str(p.relative_to(folder)).replace("\\","/"):hashlib.sha256(p.read_bytes()).hexdigest() for p in folder.rglob("*") if p.is_file()}
(out/"human-before-hashes.json").write_text(json.dumps(hashes,indent=2),encoding="utf-8")
rows=[];prev=None;vels=deque(maxlen=5);allstates=Counter();alive_states=Counter();all_eco=Counter();alive_eco=Counter();edge=Counter();lookup={}
for i,line in enumerate((folder/"ticks.jsonl").open(encoding="utf-8")):
 r=json.loads(line);assert r["global_tick"]==i
 assert canonical_hash({k:v for k,v in r.items() if k not in ("presentation","deterministic_sha256")})==r["deterministic_sha256"]
 sw=r["swatter"];f=r["fly"];ns=r["neural"]["state"];e=r["edge_analysis"]
 allstates[ns]+=1;all_eco[r["ecology"]["state"]]+=1
 if f["alive"]:
  alive_states[ns]+=1;alive_eco[r["ecology"]["state"]]+=1;edge["alive_ticks"]+=1;edge["reachable_alive_ticks"]+=e["fly_geometrically_reachable"]
 for key in ("hit_near_wall","miss_near_wall"):edge[key]+=e[key]
 edge["offscreen_near_wall_hits"]+=e["hit_near_wall"] and e["swatter_head_outside_viewport"]
 if prev is None or r["episode"]!=prev["episode"]:
  assert r["tick"]==0;vels.clear();v=np.array([np.nan,np.nan]);acc=np.nan;err=np.nan
 else:
  assert r["tick"]==prev["tick"]+1
  v=(np.array([sw["target_x"],sw["target_y"]])-np.array([prev["swatter"]["target_x"],prev["swatter"]["target_y"]]))/dt
  acc=np.linalg.norm(v-vels[-1])/dt if vels else np.nan;vels.append(v)
  err=math.hypot(sw["target_x"]-prev["swatter"]["x"],sw["target_y"]-prev["swatter"]["y"])
 filtered=np.linalg.norm(np.mean(vels,axis=0)) if len(vels)==5 else np.nan
 rows.append([r["episode"],r["tick"],f["alive"],sw["phase"]=="approach",np.linalg.norm(v),acc,sw["speed"],err,r["retina"]["theta"],r["retina"]["theta_dot"],filtered,{"CALM":0,"ALERT":1,"ESCAPE":2}.get(ns,-1),f["speed_bl_s"]])
 lookup[(r["episode"],r["tick"])]=(ns,r["event_flags"]["threat_onset"])
 prev=r
x=np.array(rows);assert len(x)==m["tick_count"]
np.savez_compressed(out/"human-kinematics.npz",rows=x)
mask=(x[:,2]==1)&(x[:,3]==1)&np.isfinite(x[:,4])
def dist(a):
 a=a[np.isfinite(a)]
 return {"n":len(a),"mean":float(a.mean()) if len(a) else None,**{k:float(np.percentile(a,q)) if len(a) else None for k,q in [("p25",25),("p50",50),("p75",75),("p90",90),("p95",95),("max",100)]}}
def frac(c):return {str(k):v/sum(c.values()) for k,v in sorted(c.items())}
def bands(col):
 result=[]
 for name,lo,hi in [("stationary",0,1),("slow",1,300),("moderate",300,900),("fast",900,1800),("above_cap",1800,float("inf"))]:
  sel=mask&(x[:,col]>=lo)&(x[:,col]<hi);values=x[sel]
  result.append({"pointer_band":name,"range_units_s":[lo,None if math.isinf(hi) else hi],"ticks":int(sel.sum()),"near_cap_fraction":float(np.mean(values[:,6]>=.95*cap)) if len(values) else None,"swatter_speed":dist(values[:,6]),"target_error":dist(values[:,7]),"theta":dist(values[:,8]),"theta_dot":dist(values[:,9]),"threat_state_fraction":frac(Counter(values[:,11].astype(int))) if len(values) else {}})
 return result
strikes=json.loads((folder/"strikes.json").read_text());episodes=[json.loads(line) for line in (folder/"episodes.jsonl").read_text().splitlines()]
assert len(strikes)==sum(e["stats"]["strikes"] for e in episodes)
pre={str(k):{"n":sum(st["escape_preexisting"]==k for st in strikes),"hits":sum(st["escape_preexisting"]==k and st["outcome"]=="hit" for st in strikes)} for k in (False,True)}
warning=[]
for label,lo,hi in [("within_0_to_100ms",-.1,.10000001),("prior_100_to_500ms",.10000001,.50000001),("prior_500_to_1000ms",.50000001,1.00000001)]:
 selected=[st for st in strikes if st["threat_onset_time"] is not None and lo<=st["strike_start_time"]-st["threat_onset_time"]<hi]
 warning.append({"definition":label,"n":len(selected),"hits":sum(st["outcome"]=="hit" for st in selected)})
near=mask&(x[:,6]>=.95*cap)
report={"session":folder.name,"source_hashes":hashes,"integrity":"all tick hashes and contiguous global/episode indices verified","sampling":{"dt":dt,"pointer_velocity":"consumed target finite differences per episode; first tick excluded","pointer_acceleration":"vector velocity finite difference, first two ticks excluded","smoothing_sensitivity":"100ms mean velocity vector; unavailable first 5 samples","target_error":"current consumed target minus previous post-step head; first tick excluded","alive":"post-step fly.alive"},"counts":{"ticks":len(x),"alive_ticks":int(x[:,2].sum()),"alive_approach_ticks":int(mask.sum()),"strikes":len(strikes),"hits":sum(st["outcome"]=="hit" for st in strikes)},"threat_all":frac(allstates),"threat_alive":frac(alive_states),"ecology_all":frac(all_eco),"ecology_alive":frac(alive_eco),"speed_bl_s_all":dist(x[:,12]),"speed_bl_s_alive":dist(x[x[:,2]==1,12]),"approach":{"pointer_speed":dist(x[mask,4]),"pointer_acceleration":dist(x[mask,5]),"physical_speed":dist(x[mask,6]),"target_error":dist(x[mask,7]),"theta":dist(x[mask,8]),"theta_dot":dist(x[mask,9]),"near_95pct_cap_fraction":float(near.sum()/mask.sum()),"target_error_above_150_fraction":float(np.mean(x[mask,7]>=150)),"near_cap_with_error_above_150_fraction":float(np.mean(x[near,7]>=150)),"raw_bands":bands(4),"smoothed_bands":bands(10)},"edge":dict(edge),"preexisting_escape":pre,"warning_strata":warning,"limitations":["One human session, descriptive observations; no causal hit-rate inference.","Logical input units, not hand kinematics. Render event coalescing and repeated targets affect raw derivatives.","No raw screen-coordinate or timestamp stream; pointer scaling correctness checked in code/tests, not inferred as human hand speed."]}
(out/"human-analysis.json").write_text(json.dumps(report,indent=2)+"\n",encoding="utf-8")
print(json.dumps({k:v for k,v in report.items() if k not in ("source_hashes","approach")},indent=2))
print(json.dumps(report["approach"],indent=2))
