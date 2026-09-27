"""M1.8-N4B7: long-timescale DNp01 slow-approach readout (research only).

No runtime code, configuration, decoder, whitelist, Retina / encoder equation, MaleCNS
parameter, brain noise, controller, geometry, physics or lifecycle is changed. The accepted
runtime (M1.8-N4B5R, `feature/m1-8-n4b5r-geometry` @ 363a1a9) is imported read-only from its
worktree, which must stay clean. The candidate family, semantics, holdout seeds and decision
rule live in `tools/n4b7_candidates.py`; `freeze` records its sha256 before any fresh holdout
seed is simulated, and every holdout mode refuses to run if it changed.

Development (already inspected data; characterisation only):

    python tools/n4b7_long_readout.py dev-n0 --worker K --workers 4
    python tools/n4b7_long_readout.py dev-controlled
    python tools/n4b7_long_readout.py dev-room
    python tools/n4b7_long_readout.py dev-n1
    python tools/n4b7_long_readout.py dev-human
    python tools/n4b7_long_readout.py dev-summary

Freeze, then fresh holdouts:

    python tools/n4b7_long_readout.py freeze
    python tools/n4b7_long_readout.py hold-n0 --worker K --workers 6
    python tools/n4b7_long_readout.py hold-room --worker K --workers 6
    python tools/n4b7_long_readout.py hold-controlled --worker K --workers 6
    python tools/n4b7_long_readout.py hold-n1 --worker K --workers 2
    python tools/n4b7_long_readout.py analyze

Outputs go to artifacts/m1_8_n4b7/ (git-ignored).
"""
from __future__ import annotations

import argparse
from collections import Counter
import copy
import glob
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / 'artifacts/m1_8_n4b7'
PREREG = OUT / 'preregistration.json'
CAND_FILE = ROOT / 'tools/n4b7_candidates.py'
N4B5R_ART = None      # set after the runtime path is known
DT = 0.02
PARKED = (1920.0, 388.8)
NEAR = 310.0
SUPPRESS_TICKS, HORIZON_TICKS = 100, 150


def _args():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('mode')
    p.add_argument('--worker', type=int, default=0)
    p.add_argument('--workers', type=int, default=1)
    p.add_argument('--noise-offset', type=int)
    p.add_argument('--reverse', action='store_true',
                   help='hold-room: process all seeds in reverse order (extra workers; existing results are skipped)')
    return p.parse_args()


ARGS = _args() if __name__ == '__main__' else None
os.environ.setdefault('NUMBA_NUM_THREADS', '1')
os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')

import numpy as np  # noqa: E402


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


C = load_module('n4b7_candidates', CAND_FILE)
N6 = load_module('n4b6_controlled_approach', ROOT / 'tools/n4b6_controlled_approach.py')
P6 = N6.P
RUNTIME = N6.RUNTIME
N4B5R_ART = RUNTIME / 'artifacts/m1_8_n4b5r'


def runtime():
    N6.check_runtime()
    if sys.path[0] != str(RUNTIME):
        sys.path.insert(0, str(RUNTIME))


def research_diag():
    """tools/n4_diagnosis.py of the research branch (stdlib + numpy only), loaded by path after
    the runtime `game` package is bound, so it cannot shadow it."""
    runtime()
    mod = load_module('n4_diagnosis_research', ROOT / 'tools/n4_diagnosis.py')
    while str(ROOT) in sys.path[:1]:
        sys.path.pop(0)
    sys.path.insert(0, str(RUNTIME))
    return mod


def write(name, obj):
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / name).write_text(json.dumps(obj, indent=1, default=float) + '\n', encoding='utf-8')


def read(name):
    return json.loads((OUT / name).read_text(encoding='utf-8'))


def poisson_upper(k, minutes):
    from scipy.stats import chi2
    return float(chi2.ppf(0.95, 2 * k + 2) / 2 / minutes) if minutes > 0 else None


def q(v, p):
    v = [x for x in v if x is not None]
    return None if not v else float(np.percentile(v, p))


def check_frozen():
    if not PREREG.exists():
        raise SystemExit('run `freeze` first: candidates must be frozen before any holdout run')
    reg = json.loads(PREREG.read_text(encoding='utf-8'))
    if sha256(CAND_FILE) != reg['candidates_sha256']:
        raise SystemExit('tools/n4b7_candidates.py changed after the freeze')
    if sha256(N6.PROTOCOL_FILE) != reg['n4b6_protocol_sha256']:
        raise SystemExit('tools/n4b6_protocol.py changed')
    return reg


# ================================================================== decoders ===
DECODERS = [('N4B1C', None, 'n4b1c')]
for _r in C.FAMILY:
    DECODERS += [('%s combined' % _r, _r, 'combined'), ('%s alone' % _r, _r, 'long_only')]
_POL = {}


def room_config():
    from game.session import load_config
    return load_config(RUNTIME / 'game_room_config.json')


def decoder(name):
    if name not in _POL:
        runtime()
        rule, mode = next((r, m) for n, r, m in DECODERS if n == name)
        _POL[name] = C.make_policy(room_config(), rule, mode, RUNTIME)
    return _POL[name]


def replay(name, left, right):
    """Events of one decoder on DNp01 traces, fresh state at sample 0."""
    from game.action import MotorState
    pol = decoder(name)
    pol.reset()
    zero = np.zeros(1, np.float32)
    out = []
    for t in range(len(left)):
        a = pol.decide(MotorState(float(left[t]), float(right[t]), 0.0, 0.0, zero))
        if a.escape:
            paths = pol.criterion_diagnostics()['escape_trigger_paths']
            info = getattr(pol, 'long_last_trigger', None)
            ev = {'t': t, 'paths': paths, 'lateral': float(a.lateral)}
            if 'LONG' in paths.split('+') and info is not None and info[0] == t:
                ev['long_sides'], ev['long_counts'] = info[1], info[2]
            out.append(ev)
    return out


def replay_all(left, right, names=None):
    return {n: replay(n, left, right) for n in (names or [d[0] for d in DECODERS])}


def traces_from_spikes(spk):
    d = np.float32(decoder('N4B1C').trace_decay)
    out = np.empty(spk.size, np.float32)
    t = np.float32(0.0)
    for i in range(spk.size):
        t = np.float32(t * d)
        if spk[i]:
            t = np.float32(t + np.float32(1.0))
        out[i] = t
    return out.astype(np.float64)


def long_only_added(ev_comb, ev_ref, t0=0):
    """Combined events whose firing sample qualified on LONG alone (no N4B1C path)."""
    return [e for e in ev_comb if e['t'] >= t0 and e['paths'] == 'LONG']


def max_long_in_5s(events):
    ts = [e['t'] for e in events if 'LONG' in e['paths'].split('+')]
    best = 0
    for i, t in enumerate(ts):
        best = max(best, sum(1 for u in ts[i:] if u - t < 250))
    return best


# ================================================================== fixed-fly N0 ===
def n0_score(trials, minutes_per_trial):
    """trials: list of (label, left, right). Returns per-decoder event counts and details."""
    res = {}
    for name, _, _ in DECODERS:
        events, bursts = [], 0
        for label, l, r in trials:
            ev = replay(name, l, r)
            bursts = max(bursts, max_long_in_5s(ev))
            for e in ev:
                events.append(dict(e, trial=label))
        minutes = len(trials) * minutes_per_trial
        res[name] = {'events': len(events), 'minutes': minutes, 'per_min': len(events) / minutes,
                     'upper95_per_min': poisson_upper(len(events), minutes),
                     'long_path_events': sum('LONG' in e['paths'].split('+') for e in events),
                     'max_long_events_in_5s': bursts, 'list': events[:200]}
    return res


def dev_n0():
    runtime()
    crit = load_module('n4b2_criteria', ROOT / 'tools/n4b2_criteria.py')  # noqa: F841  (provenance only)
    meta = json.loads((ROOT / 'artifacts/m1_8_n4b2/connectome.json').read_text(encoding='utf-8'))
    idx = {}
    for j, r in enumerate(meta['panel']):
        idx.setdefault(r['type'], {})[r['side']] = j
    files = sorted(glob.glob(str(ROOT / 'artifacts/m1_8_n4b2/n0_*_chunk*.npz')))
    mine = [f for i, f in enumerate(files) if i % ARGS.workers == ARGS.worker]
    trials, tpt = [], None
    for f in mine:
        d = np.load(f)
        for i in range(d['spikes'].shape[0]):
            sp = d['spikes'][i]
            tpt = sp.shape[0]
            trials.append(('%s#%d' % (Path(f).stem, int(d['seeds'][i])),
                           traces_from_spikes(sp[:, idx['DNp01']['L']]), traces_from_spikes(sp[:, idx['DNp01']['R']])))
    res = n0_score(trials, tpt * DT / 60)
    res['files'] = [Path(f).name for f in mine]
    write('dev_n0_part%d.json' % ARGS.worker, res)
    print({k: (v['events'], round(v['minutes'])) for k, v in res.items() if k != 'files'})


# ================================================================== controlled ===
def controlled_trial(tid, z):
    """Per-decoder metrics of one N4B6-style trial record."""
    spec = P6.MATRIX[tid]
    on = P6.PRE_HOLD_TICKS
    geo, tr = z['geo'], z['dnp01_trace']
    hd, rng = geo[:, 5], geo[:, 6]
    c = N6.closest_tick(rng, on) if spec['role'] in ('approach', 'abort') else None
    out = {}
    for name, _, _ in DECODERS:
        ev = replay(name, tr[:, 0], tr[:, 1])
        post = [e for e in ev if e['t'] >= on]
        m = {'pre_onset': sum(1 for e in ev if e['t'] < on), 'after_onset': len(post),
             'max_long_in_5s': max_long_in_5s(ev)}
        if post:
            e = post[0]
            m.update(trigger=(e['t'] - on) * DT, paths=e['paths'], hdist=float(hd[e['t']]), range=float(rng[e['t']]),
                     long_sides=e.get('long_sides'), long_counts=e.get('long_counts'))
        if c is not None:
            m['closest'] = (c - on) * DT
            m['timely'] = bool(post) and post[0]['t'] <= c
            m['lead'] = (c - post[0]['t']) * DT if m['timely'] else None
            m['events_onset_to_closest'] = sum(1 for e in post if e['t'] <= c)
        out[name] = m
    return out


def controlled_summary(per):
    """per[tid] = list of controlled_trial dicts."""
    res = {}
    for tid, rows in per.items():
        role = P6.MATRIX[tid]['role']
        res[tid] = {}
        for name, _, _ in DECODERS:
            ms = [r[name] for r in rows]
            n = len(ms)
            t = {'n': n, 'pre_onset_events': sum(m['pre_onset'] for m in ms),
                 'max_long_in_5s': max(m['max_long_in_5s'] for m in ms)}
            if role in ('approach', 'abort'):
                tim = [m for m in ms if m['timely']]
                paths = Counter(m['paths'] for m in tim)
                t.update(p_timely=len(tim) / n, miss_rate=1 - len(tim) / n,
                         median_trigger_s=q([m['trigger'] for m in tim], 50),
                         p95_trigger_s=q([m['trigger'] for m in tim], 95),
                         median_lead_s=q([m['lead'] for m in tim], 50), p05_lead_s=q([m['lead'] for m in tim], 5),
                         median_hdist=q([m['hdist'] for m in tim], 50), median_range=q([m['range'] for m in tim], 50),
                         paths=dict(paths), closest_s=float(np.median([m['closest'] for m in ms])),
                         p_late_only=sum(1 for m in ms if not m['timely'] and m.get('trigger') is not None) / n,
                         mean_events_onset_to_closest=float(np.mean([m['events_onset_to_closest'] for m in ms])),
                         median_long_count=q([max(m['long_counts']) for m in tim if m.get('long_counts')], 50))
            else:
                minutes = n * (len_motion(tid) + P6.POST_HOLD_TICKS) * DT / 60
                k = sum(m['after_onset'] for m in ms)
                t.update(false_events=k, trials_with_event=sum(1 for m in ms if m['after_onset']),
                         minutes=minutes, per_min=k / minutes, upper95_per_min=poisson_upper(k, minutes),
                         median_trigger_s=q([m.get('trigger') for m in ms], 50),
                         paths=dict(Counter(m.get('paths') for m in ms if m.get('paths'))))
            res[tid][name] = t
    return res


def len_motion(tid):
    return P6.script(P6.MATRIX[tid]['geometry'])[1]


def dev_controlled():
    runtime()
    per = {}
    for tid in P6.MATRIX:
        per[tid] = [controlled_trial(tid, np.load(ROOT / 'artifacts/m1_8_n4b6/trials' / tid / ('%d.npz' % s)))
                    for s in P6.SEEDS]
    res = controlled_summary(per)
    write('dev_controlled.json', res)
    show_controlled(res)


def show_controlled(res):
    for tid, t in res.items():
        line = []
        for name in ('N4B1C', 'L1 combined', 'L1 alone', 'L2 combined', 'L3 combined'):
            x = t[name]
            if 'p_timely' in x:
                line.append('%s %.2f lead %s' % (name, x['p_timely'], None if x['median_lead_s'] is None else round(x['median_lead_s'], 2)))
            else:
                line.append('%s %d ev' % (name, x['false_events']))
        print(tid, ' | '.join(line))


# ================================================================== ROOM free flight ===
ROW_KEYS = ('theta', 'theta_dot', 'azimuth', 'drive', 'dl', 'dr', 'fx', 'fy', 'fvx', 'fvy',
            'px', 'py', 'ph', 'pvx', 'pvy', 'half', 'escape')


def geometry_at(a, i):
    dx, dy = a['px'][i] - a['fx'][i], a['py'][i] - a['fy'][i]
    dh = math.hypot(dx, dy)
    rng = math.sqrt(dh * dh + a['ph'][i] ** 2)
    rr = -(dx * (a['fvx'][i] - a['pvx'][i]) + dy * (a['fvy'][i] - a['pvy'][i])) / rng
    return dh, rng, rr, math.degrees(math.atan2(a['ph'][i], dh))


def classify(a, t, cf_min):
    """Accepted N4B4 / N4B5R category of an escape at tick t (same formulas as
    tools/n4b5r_runtime_validation.py room_summary)."""
    i = t
    drive = float(np.max(a['drive'][max(0, i - 9):i + 1]))
    pos_r = pos_s = 0.0
    for j in range(max(2, i - 9), i + 1):
        ra, rb = geometry_at(a, j - 2)[1], geometry_at(a, j - 1)[1]
        ha, hb = a['half'][j - 2], a['half'][j - 1]
        pos_r += max(2 * math.atan(ha / rb) - 2 * math.atan(ha / ra), 0.0)
        pos_s += max(2 * math.atan(hb / rb) - 2 * math.atan(ha / rb), 0.0)
    share = pos_s / (pos_r + pos_s) if pos_r + pos_s > 0 else None
    dh, rng, rr, elev = geometry_at(a, i - 1)
    if drive < 1e-6:
        cat = 'A'
    elif cf_min is not None and cf_min >= NEAR:
        cat = 'B'
    elif share is not None and share >= 0.6 and elev >= 60:
        cat = 'C'
    elif rr <= -40 and (share is None or share < 0.3):
        cat = 'D'
    else:
        cat = 'mixed'
    return {'category': cat, 'drive': drive, 'size_share': share, 'elevation_deg': elev, 'range_rate': rr,
            'horizontal': dh, 'counterfactual_min_horizontal': cf_min}


def n4b5r_room_runs():
    """The 83 N4B5R no-player runs (accepted runtime, G3) as arrays."""
    inv = json.loads((ROOT / 'artifacts/m1_8_n4b4/inventory.json').read_text(encoding='utf-8'))
    for r in inv['runs']:
        m = json.loads((N4B5R_ART / ('room_%s_seed%d.json' % (r['source'], r['seed']))).read_text(encoding='utf-8'))
        rows = m['rows']
        a = {k: np.array(v) for k, v in {
            'theta': [x['theta'] for x in rows], 'theta_dot': [x['theta_dot'] for x in rows],
            'azimuth': [x['azimuth'] for x in rows], 'drive': [x['drive'] for x in rows],
            'dl': [x['dnp01'][0] for x in rows], 'dr': [x['dnp01'][1] for x in rows],
            'fx': [x['fly'][0] for x in rows], 'fy': [x['fly'][1] for x in rows],
            'fvx': [x['fly'][2] for x in rows], 'fvy': [x['fly'][3] for x in rows],
            'px': [x['paddle'][0] for x in rows], 'py': [x['paddle'][1] for x in rows],
            'ph': [x['paddle'][2] for x in rows], 'pvx': [x['paddle'][3] for x in rows],
            'pvy': [x['paddle'][4] for x in rows], 'half': [x['half'] for x in rows],
            'escape': [x['escape'] for x in rows]}.items()}
        a['lifecycle'] = [x['lifecycle'] for x in rows]
        yield '%s_%d' % (r['source'], r['seed']), a


def shadow_room(label, a, names):
    """Shadow evaluation on a run recorded under the live N4B1C policy. Returns the reference
    check and every LONG-only firing of each combined candidate, classified with the recorded
    future as its no-escape counterfactual (valid when no recorded escape follows within 75 ticks)."""
    rec = [int(t) for t in np.flatnonzero(a['escape'])]
    ref = [e['t'] for e in replay('N4B1C', a['dl'], a['dr'])]
    out = {'label': label, 'ticks': len(a['dl']), 'recorded_escapes': rec, 'n4b1c_replay_equal': ref == rec, 'added': {}}
    for name in names:
        ev = replay(name, a['dl'], a['dr'])
        added = []
        for e in long_only_added(ev, None):
            t = e['t']
            clean = not any(t < u <= t + 75 for u in rec)
            cf_min = float(min(math.hypot(a['px'][j] - a['fx'][j], a['py'][j] - a['fy'][j])
                               for j in range(t + 1, min(len(a['dl']), t + 76)))) if clean and t + 1 < len(a['dl']) else None
            nxt = next((u for u in ref if u >= t), None)
            added.append(dict(e, **classify(a, t, cf_min), counterfactual_clean=clean,
                              max_drive_last_50=float(np.max(a['drive'][max(0, t - 49):t + 1])),
                              lifecycle=a['lifecycle'][t] if 'lifecycle' in a else None,
                              n4b1c_next_s=None if nxt is None else (nxt - t) * DT))
        out['added'][name] = added
        out.setdefault('combined_events', {})[name] = len(ev)
    return out


def room_rates(runs, names):
    minutes = sum(r['ticks'] for r in runs) / 3000
    res = {'minutes': minutes, 'runs': len(runs), 'n4b1c_replay_exact_runs': sum(r['n4b1c_replay_equal'] for r in runs),
           'recorded_n4b1c_escapes': sum(len(r['recorded_escapes']) for r in runs)}
    for name in names:
        ev = [dict(e, run=r['label']) for r in runs for e in r['added'][name]]
        cats = Counter(e['category'] for e in ev)
        res[name] = {'added_long_only': len(ev), 'per_min': len(ev) / minutes,
                     'upper95_per_min': poisson_upper(len(ev), minutes),
                     'categories': {c: {'events': cats.get(c, 0), 'per_min': cats.get(c, 0) / minutes,
                                        'upper95_per_min': poisson_upper(cats.get(c, 0), minutes)}
                                    for c in ('A', 'B', 'C', 'D', 'mixed')},
                     'before_an_n4b1c_escape_within_1s': sum(1 for e in ev if e['n4b1c_next_s'] is not None and e['n4b1c_next_s'] <= 1.0),
                     'lifecycle': dict(Counter(e['lifecycle'] for e in ev)), 'list': ev}
    return res


def dev_room():
    runtime()
    names = [n for n, r, m in DECODERS if m == 'combined']
    runs = [shadow_room(label, a, names) for label, a in n4b5r_room_runs()]
    res = room_rates(runs, names)
    write('dev_room.json', res)
    print('minutes %.0f, replay exact %d/%d' % (res['minutes'], res['n4b1c_replay_exact_runs'], res['runs']))
    for n in names:
        print(n, res[n]['added_long_only'], {c: v['events'] for c, v in res[n]['categories'].items()},
              'before N4B1C', res[n]['before_an_n4b1c_escape_within_1s'])


# ================================================================== N1 (G3) ===
def run_n1_traces():
    runtime()
    from game.session import Session
    from tools.calibrate_escape import RecordingPolicy
    from tools.loom_robustness_study import run_trial, DT as LDT
    config = room_config()
    settle = max(40, round(config['swatter'].get('physical', {}).get('calibration_settle_seconds', 0.8) / LDT))
    policy = RecordingPolicy()
    session = Session(config, policy=policy, root=RUNTIME, ecology_enabled=False)
    session.world.collisions_enabled = False
    session.world.fly_motion_enabled = False
    rng = np.random.default_rng(int(config['encoder']['encoder_seed']) + 991)
    out = []
    for ci, kind in enumerate(('strong_direct', 'medium_committed', 'weak_approach', 'glancing_pass', 'aborted_approach')):
        for i in range(60):
            t = run_trial(session, policy, 6000 + ci * 1000 + i, kind, rng, settle)
            hist = policy.history[-t['ticks']:]
            out.append({'kind': kind, 'click': t['click_tick'], 'left': [h.dnp01_left for h in hist],
                        'right': [h.dnp01_right for h in hist], 'distance': t['distance'].tolist(),
                        'theta_dot': t['theta_dot'].tolist()})
    session.close()
    return out


def strike_cover(ev, click, end, lookback=20):
    e = next((x for x in ev if click - lookback <= x['t'] <= end), None)
    return None if e is None else (e['t'] - click) * DT


def dev_n1():
    trials = run_n1_traces()
    res = {}
    for kind in ('strong_direct', 'medium_committed'):
        tr = [t for t in trials if t['kind'] == kind]
        res[kind] = {}
        for name, _, _ in DECODERS:
            lat = [strike_cover(replay(name, t['left'], t['right']), t['click'], len(t['left']) - 1) for t in tr]
            got = [x for x in lat if x is not None]
            res[kind][name] = {'covered': len(got), 'n': len(tr), 'median_s': q(got, 50), 'p95_s': q(got, 95),
                               'before_click': sum(1 for x in got if x < 0)}
    for kind in ('weak_approach', 'glancing_pass', 'aborted_approach'):
        tr = [t for t in trials if t['kind'] == kind]
        res[kind] = {name: {'any_event': sum(1 for t in tr if replay(name, t['left'], t['right'])), 'n': len(tr)}
                     for name, _, _ in DECODERS}
    write('dev_n1.json', res)
    for k, v in res.items():
        print(k, {n: (x.get('covered', x.get('any_event')), x.get('median_s')) for n, x in v.items()})


# ================================================================== human sessions ===
SESSIONS = {'strict_n2': '20260923T005351.731330Z-38255ec8', 'n2b': '20260924T000111.561327Z-c337a721'}


def human_traces(noise_offset):
    """noise_offset None: the recorded DNp01 traces. Otherwise the N4B5R open-loop G3
    recomputation (Retina of row t from the state stored at row t-1), brain reset with
    episode seed + 977 + noise_offset. Also returns per-row G3 half size and drive."""
    runtime()
    from game.fly import build_brain
    from game.perception import Retina, RetinalEncoder
    from game.world import World
    out = {}
    for sess, name in SESSIONS.items():
        path = ROOT / 'results/game/sessions' / name
        manifest = json.loads((path / 'manifest.json').read_text(encoding='utf-8'))
        config = copy.deepcopy(manifest['config'])
        config['swatter']['directional']['tilt_geometry'] = 'elevation_aware_tilt_v1'
        w = World(config, 1)
        seeds = {json.loads(l)['episode']: json.loads(l)['seed'] for l in (path / 'episodes.jsonl').open(encoding='utf-8')}
        eps = {}
        for l in (path / 'ticks.jsonl').open(encoding='utf-8'):
            r = json.loads(l)
            eps.setdefault(r['episode'], []).append(r)

        def half_rng(row):
            f, s = row['fly'], row['swatter']
            w.fly.x, w.fly.y = f['x'], f['y']
            sw = w.swatter
            sw.x, sw.y, sw.height, sw.face, sw.orientation = s['x'], s['y'], s['height'], s['face'], s['orientation']
            return w.visual_half_size, math.sqrt((s['x'] - f['x']) ** 2 + (s['y'] - f['y']) ** 2 + s['height'] ** 2)
        if noise_offset is not None:
            brain = build_brain(config, RUNTIME)
            encoder = RetinalEncoder(brain, config)
            l_idx, r_idx = int(brain.groups['escape_L'][0]), int(brain.groups['escape_R'][0])
            decay = np.float32(np.exp(-DT / float(config['brain']['trace_tau_seconds'])))
        sess_out = {}
        for ep, er in eps.items():
            hr = [half_rng(r) for r in er]
            thetas = [er[0]['retina']['theta']] + [2.0 * math.atan(h / max(g, 1e-6)) for h, g in hr[:-1]]
            ticks, lefts, rights, rows = [], [], [], []
            if noise_offset is not None:
                brain.reset(int(seeds[ep]) + 977 + noise_offset)
            tl = tr = np.float32(0.0)
            for i, r in enumerate(er):
                if not r['neural']['brain_stepped']:
                    continue
                if noise_offset is None:
                    lv, rv = r['neural']['dnp01_left'], r['neural']['dnp01_right']
                    drive = sum(r['visual_input'][k] for k in ('loomL', 'loomR', 'threatL', 'threatR'))
                else:
                    td = 0.0 if i == 0 else (thetas[i] - thetas[i - 1]) / DT
                    fired = np.asarray(brain.step(inject=encoder.inject(Retina(thetas[i], td, r['retina']['azimuth']))))
                    dd = encoder.last_drive
                    drive = sum(dd.get(k, 0.0) for k in ('loomL', 'loomR', 'threatL', 'threatR'))
                    tl = np.float32(tl * decay)
                    tr = np.float32(tr * decay)
                    if np.any(fired == l_idx):
                        tl = np.float32(tl + np.float32(1.0))
                    if np.any(fired == r_idx):
                        tr = np.float32(tr + np.float32(1.0))
                    lv, rv = float(tl), float(tr)
                prev = er[i - 1] if i > 0 else r
                ticks.append(r['tick'])
                lefts.append(lv)
                rights.append(rv)
                rows.append({'fx': prev['fly']['x'], 'fy': prev['fly']['y'], 'fvx': prev['fly']['vx'], 'fvy': prev['fly']['vy'],
                             'px': prev['swatter']['x'], 'py': prev['swatter']['y'], 'ph': prev['swatter']['height'],
                             'pvx': prev['swatter']['vx'], 'pvy': prev['swatter']['vy'],
                             'half': hr[i - 1][0] if i > 0 else hr[0][0], 'drive': drive,
                             'phase': r['swatter']['phase'], 'lifecycle': r['lifecycle']['mode'],
                             'recorded_escape': r['action']['escape']})
            sess_out[ep] = {'ticks': ticks, 'left': lefts, 'right': rights, 'rows': rows}
        out[sess] = sess_out
    return out


def human_windows():
    D = research_diag()
    win = []
    for sess, name in D.SESSIONS.items():
        eps, strikes = D.session_rows(name)
        for s in strikes:
            rows = eps[s['episode']]
            idx = {r['tick']: k for k, r in enumerate(rows)}
            c, r = idx[s['start_tick']], idx[s['resolved_tick']]
            win.append({'session': sess, 'episode': s['episode'], 'cls': 'direct_strike',
                        't0': rows[max(0, c - 25)]['tick'], 't1': rows[r]['tick'], 'anchor': s['start_tick']})
        for ep, rows in eps.items():
            seg = 0
            for i, r in enumerate(rows):
                if not (r['action']['escape'] and r['neural']['brain_stepped']):
                    continue
                b = D.bout_start(rows, i, seg)
                if b is not None:
                    cls = 'strike_escape' if r['swatter']['phase'] in D.STRIKE_PHASES else 'hover_escape'
                    win.append({'session': sess, 'episode': ep, 'cls': cls, 't0': rows[b]['tick'], 't1': r['tick'],
                                'anchor': r['tick']})
                seg = i + 1
    eps, _ = D.session_rows(D.SESSIONS['strict_n2'])
    win.append({'session': 'strict_n2', 'episode': 1, 'cls': 'far_perched', 't0': eps[1][2434]['tick'],
                't1': eps[1][2528]['tick'], 'anchor': eps[1][2434]['tick']})
    eps, _ = D.session_rows(D.SESSIONS['n2b'])
    rows = eps[1]
    k = next(i for i, r in enumerate(rows) if any(e['type'] == 'voluntary_takeoff' for e in r['lifecycle']['events']))
    win.append({'session': 'n2b', 'episode': 1, 'cls': 'voluntary_takeoff', 't0': rows[k - 50]['tick'],
                't1': rows[min(len(rows) - 1, k + 25)]['tick'], 'anchor': rows[k]['tick']})
    return win


def human_score(tr, windows):
    names = [d[0] for d in DECODERS]
    ev = {sess: {ep: replay_all(e['left'], e['right'], names) for ep, e in s.items()} for sess, s in tr.items()}
    res = {'firings': {n: sum(len(ev[s][e][n]) for s in ev for e in ev[s]) for n in names}, 'classes': {}}
    for n in names:
        per = {}
        for w in windows:
            e = tr[w['session']][w['episode']]
            t = e['ticks']
            lo = w['anchor'] - 20 if w['cls'] == 'direct_strike' else w['t0']
            hit = next((x for x in ev[w['session']][w['episode']][n] if lo <= t[x['t']] <= w['t1']), None)
            per.setdefault(w['cls'], []).append(None if hit is None else (t[hit['t']] - w['anchor']) * DT)
        ds = per['direct_strike']
        got = [x for x in ds if x is not None]
        res['classes'][n] = {'direct_strike': {'covered': len(got), 'n': len(ds), 'before_click': sum(1 for x in got if x < 0),
                                               'median_s': q(got, 50)},
                             **{c: {'detected': sum(x is not None for x in per[c]), 'n': len(per[c])}
                                for c in ('hover_escape', 'strike_escape', 'far_perched', 'voluntary_takeoff')}}
    # LONG-only additions, with context (open-loop replay: the recorded future is the no-escape
    # counterfactual only where the recorded fly did not escape in the next 75 rows).
    for n in [d[0] for d in DECODERS if d[2] == 'combined']:
        adds = []
        for sess, s in ev.items():
            for ep, dd in s.items():
                rows = tr[sess][ep]['rows']
                a = {k: np.array([r[k] for r in rows]) for k in ('fx', 'fy', 'fvx', 'fvy', 'px', 'py', 'ph', 'pvx', 'pvy', 'half', 'drive')}
                refs = [x['t'] for x in dd['N4B1C']]
                for e in long_only_added(dd[n], None):
                    t = e['t']
                    if t < 2:
                        continue
                    clean = not any(rows[j]['recorded_escape'] for j in range(t + 1, min(len(rows), t + 76)))
                    cf = float(min(math.hypot(a['px'][j] - a['fx'][j], a['py'][j] - a['fy'][j]) for j in range(t + 1, min(len(rows), t + 76)))) \
                        if clean and t + 1 < len(rows) else None
                    nxt = next((u for u in refs if u >= t), None)
                    adds.append(dict(e, session=sess, episode=ep, tick=tr[sess][ep]['ticks'][t], phase=rows[t]['phase'],
                                     lifecycle=rows[t]['lifecycle'], **classify(a, t, cf),
                                     n4b1c_next_s=None if nxt is None else (nxt - t) * DT))
        res.setdefault('added', {})[n] = {'count': len(adds), 'categories': dict(Counter(x['category'] for x in adds)),
                                          'phases': dict(Counter(x['phase'] for x in adds)),
                                          'before_n4b1c_within_1s': sum(1 for x in adds if x['n4b1c_next_s'] is not None and x['n4b1c_next_s'] <= 1.0),
                                          'list': adds}
    return res


def dev_human():
    windows = human_windows()
    out = {'windows': len(windows)}
    for off in (None, 0, 1, 2, 3, 4):
        label = 'recorded' if off is None else 'g3_noise%d' % off
        out[label] = human_score(human_traces(off), windows)
        r = out[label]
        print(label, 'firings', r['firings'], 'direct', {n: (v['direct_strike']['covered'], v['direct_strike']['median_s']) for n, v in r['classes'].items()},
              'added', {n: v['count'] for n, v in r['added'].items()}, flush=True)
    write('dev_human.json', out)


def dev_summary():
    parts = [read(f.name) for f in sorted(OUT.glob('dev_n0_part*.json'))]
    n0 = {}
    for name, _, _ in DECODERS:
        k = sum(p[name]['events'] for p in parts)
        m = sum(p[name]['minutes'] for p in parts)
        n0[name] = {'events': k, 'minutes': m, 'per_min': k / m, 'upper95_per_min': poisson_upper(k, m),
                    'max_long_events_in_5s': max(p[name]['max_long_events_in_5s'] for p in parts),
                    'list': [e for p in parts for e in p[name]['list']][:50]}
    write('dev_n0.json', n0)
    for n, v in n0.items():
        print('dev N0', n, v['events'], round(v['minutes']), round(v['upper95_per_min'], 4))


# ================================================================== freeze ===
def freeze():
    if PREREG.exists():
        raise SystemExit('already frozen')
    for f in ('dev_n0.json', 'dev_controlled.json', 'dev_room.json', 'dev_n1.json', 'dev_human.json'):
        if not (OUT / f).exists():
            raise SystemExit('development characterisation incomplete: %s missing' % f)
    reg = {'label': 'M1.8-N4B7 frozen long-window DNp01 candidates (research only)',
           'frozen_utc': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
           'frozen_before_any_holdout_simulation': True,
           'candidates_module': 'tools/n4b7_candidates.py', 'candidates_sha256': sha256(CAND_FILE),
           'runner_sha256_at_freeze': sha256(Path(__file__)),
           'n4b6_protocol_sha256': sha256(N6.PROTOCOL_FILE), 'runtime_commit': N6.RUNTIME_COMMIT,
           'family': C.FAMILY, 'primary': C.PRIMARY, 'semantics': C.SEMANTICS, 'holdout': C.HOLDOUT,
           'categories': C.FREE_FLIGHT_CATEGORIES, 'decision_rule': C.DECISION_RULE,
           'development_artifacts_sha256': {f.name: sha256(f) for f in sorted(OUT.glob('dev_*.json'))}}
    write('preregistration.json', reg)
    print('frozen', reg['candidates_sha256'])


# ================================================================== holdouts ===
def seeds_of(key):
    a, b = C.HOLDOUT[key]['seeds']
    return list(range(a, b + 1))


def hold_n0():
    check_frozen()
    runtime()
    from game.session import Session
    from tools.calibrate_escape import RecordingPolicy, _trial
    policy = RecordingPolicy()
    session = Session(room_config(), policy=policy, root=RUNTIME, ecology_enabled=False)
    session.world.collisions_enabled = False
    session.world.fly_motion_enabled = False
    mine = [s for i, s in enumerate(seeds_of('fixed_fly_n0')) if i % ARGS.workers == ARGS.worker]
    d = OUT / 'hold_n0'
    d.mkdir(parents=True, exist_ok=True)
    t0 = time.time()
    for k, seed in enumerate(mine):
        f = d / ('%d.npz' % seed)
        if f.exists():
            continue
        rng = np.random.default_rng(seed)
        angle, radius = float(rng.uniform(0, 2 * np.pi)), float(rng.uniform(30.0, 170.0))
        t = _trial(session, policy, seed, (math.cos(angle) * radius, math.sin(angle) * radius),
                   C.HOLDOUT['fixed_fly_n0']['ticks_per_trial'], None)
        np.savez_compressed(f, left=t['left'], right=t['right'], offset=np.array([angle, radius]))
        if k % 20 == 0:
            print('worker %d: %d/%d (%.0f s)' % (ARGS.worker, k, len(mine), time.time() - t0), flush=True)
    session.close()
    print('worker %d n0 done' % ARGS.worker, flush=True)


def hold_n1():
    check_frozen()
    runtime()
    from game.session import Session
    from tools.calibrate_escape import RecordingPolicy
    from tools.loom_robustness_study import run_trial, DT as LDT
    config = room_config()
    settle = max(40, round(config['swatter'].get('physical', {}).get('calibration_settle_seconds', 0.8) / LDT))
    policy = RecordingPolicy()
    session = Session(config, policy=policy, root=RUNTIME, ecology_enabled=False)
    session.world.collisions_enabled = False
    session.world.fly_motion_enabled = False
    seeds = seeds_of('n1_committed')
    mine = [s for i, s in enumerate(seeds) if i % ARGS.workers == ARGS.worker]
    out = []
    for seed in mine:
        kind = 'strong_direct' if seed - seeds[0] < 60 else 'medium_committed'
        t = run_trial(session, policy, seed, kind, np.random.default_rng(seed), settle)
        hist = policy.history[-t['ticks']:]
        out.append({'seed': seed, 'kind': kind, 'click': t['click_tick'], 'left': [h.dnp01_left for h in hist],
                    'right': [h.dnp01_right for h in hist]})
    session.close()
    write('hold_n1_part%d.json' % ARGS.worker, out)
    print('worker %d n1 done' % ARGS.worker, flush=True)


def n1_score(trials):
    res = {}
    for kind in ('strong_direct', 'medium_committed'):
        tr = [t for t in trials if t['kind'] == kind]
        res[kind] = {}
        for name, _, _ in DECODERS:
            lat = [strike_cover(replay(name, t['left'], t['right']), t['click'], len(t['left']) - 1) for t in tr]
            got = [x for x in lat if x is not None]
            res[kind][name] = {'covered': len(got), 'n': len(tr), 'median_s': q(got, 50), 'p95_s': q(got, 95),
                               'before_click': sum(1 for x in got if x < 0)}
    return res


class Suppress:
    """Counterfactual: escapes in [start, start + 100) are withheld from the world (only the
    smoothed turn is kept) and ESCAPE is shown as ALERT (as in N4B5R)."""

    def __init__(self, policy, ref, start):
        self._p, self._r, self.start, self.end = policy, ref, start, start + SUPPRESS_TICKS

    def __getattr__(self, name):
        return getattr(self._p, name)

    def reset(self):
        return self._p.reset()

    def decide(self, motor):
        a = self._p.decide(motor)
        if a.escape and self.start <= self._r['tick'] < self.end:
            from game.action import Action
            return Action(turn=a.turn)
        return a

    def diagnostics(self):
        d = dict(self._p.diagnostics())
        if self.start <= self._r['tick'] < self.end and d.get('behavior_state') == 'ESCAPE':
            d['behavior_state'] = 'ALERT'
        return d


def room_run(seed, live, suppress=None, until=None):
    """One no-player ROOM run under the accepted config with `live` in (N4B1C, L1 combined)."""
    from game.session import Session
    policy = C.make_policy(room_config(), None if live == 'N4B1C' else 'L1', 'n4b1c' if live == 'N4B1C' else 'combined', RUNTIME)
    ref = {'tick': 0}
    active = Suppress(policy, ref, suppress) if suppress is not None else policy
    s = Session(room_config(), policy=active, seed=seed, mode='evaluation', root=RUNTIME)
    n = until or C.HOLDOUT['room_free_flight']['ticks_per_run']
    a = {k: [] for k in ROW_KEYS}
    a['lifecycle'], events = [], []
    for t in range(n):
        ref['tick'] = t
        s.tick(pointer=PARKED, strike=False)
        m, fly, sw, r = s.fly_loop.last_motor, s.world.fly, s.world.swatter, s.last_retina
        d = s.encoder.last_drive or {}
        esc = bool(s.fly_loop.last_action.escape)
        for k, v in (('theta', r.theta), ('theta_dot', r.theta_dot), ('azimuth', r.azimuth),
                     ('drive', sum(d.get(x, 0.0) for x in ('loomL', 'loomR', 'threatL', 'threatR'))),
                     ('dl', 0.0 if m is None else m.dnp01_left), ('dr', 0.0 if m is None else m.dnp01_right),
                     ('fx', fly.x), ('fy', fly.y), ('fvx', fly.vx), ('fvy', fly.vy), ('px', sw.x), ('py', sw.y),
                     ('ph', sw.height), ('pvx', sw.vx), ('pvy', sw.vy), ('half', s.world.visual_half_size), ('escape', esc)):
            a[k].append(v)
        a['lifecycle'].append(str(s.world.lifecycle.mode) if s.world.lifecycle else None)
        if esc and (suppress is None or not (suppress <= t < suppress + SUPPRESS_TICKS)):
            cd = policy.criterion_diagnostics()
            info = getattr(policy, 'long_last_trigger', None)
            events.append({'t': t, 'paths': cd['escape_trigger_paths'], 'lateral': float(s.fly_loop.last_action.lateral),
                           'long': None if not (info and info[0] == policy._sample_index - 1) else [info[1], info[2]]})
    s.close()
    arr = {k: np.array(v) for k, v in a.items() if k != 'lifecycle'}
    arr['lifecycle'] = a['lifecycle']
    return arr, events


def pack(a):
    return {k: (v.tolist() if isinstance(v, np.ndarray) else v) for k, v in a.items()}


def hold_room():
    check_frozen()
    runtime()
    if os.environ['NUMBA_NUM_THREADS'] != '1':
        raise SystemExit('ROOM holdout runs require NUMBA_NUM_THREADS=1')
    d = OUT / 'hold_room'
    d.mkdir(parents=True, exist_ok=True)
    mine = [s for i, s in enumerate(seeds_of('room_free_flight')) if i % ARGS.workers == ARGS.worker]
    if ARGS.reverse:
        mine = seeds_of('room_free_flight')[::-1][ARGS.worker::ARGS.workers]
    t0 = time.time()
    for seed in mine:
        f = d / ('%d.json' % seed)
        if f.exists():
            continue
        rec = {'seed': seed}
        for live in ('N4B1C', 'L1 combined'):
            a, events = room_run(seed, live)
            cfs = {}
            for e in events:
                ca, _ = room_run(seed, live, suppress=e['t'], until=min(len(a['dl']), e['t'] + HORIZON_TICKS))
                cfs[str(e['t'])] = float(min(math.hypot(ca['px'][j] - ca['fx'][j], ca['py'][j] - ca['fy'][j])
                                             for j in range(e['t'] + 1, min(len(ca['dl']), e['t'] + 76))))
            rec[live] = {'events': events, 'cf_min_horizontal': cfs, 'rows': pack(a)}
        if f.exists():
            continue
        tmp = f.with_suffix('.tmp%d' % os.getpid())
        tmp.write_text(json.dumps(rec) + '\n', encoding='utf-8')
        os.replace(tmp, f)
        print('worker %d seed %d: N4B1C %d, L1 %d escapes (%.0f s)' % (ARGS.worker, seed, len(rec['N4B1C']['events']),
                                                                      len(rec['L1 combined']['events']), time.time() - t0), flush=True)
    print('worker %d room done' % ARGS.worker, flush=True)


def hold_controlled():
    """The frozen N4B6 trajectories with fresh noise seeds; same trial recorder as N4B6."""
    check_frozen()
    session, policy, config = N6.make_session()
    brain = session.brain
    esc = (int(brain.groups['escape_L'][0]), int(brain.groups['escape_R'][0]))
    captured = []
    orig = brain.step

    def step(*a, **k):
        fired = orig(*a, **k)
        captured.append(np.asarray(fired).copy())
        return fired
    brain.step = step
    mine = [s for i, s in enumerate(seeds_of('controlled_approach')) if i % ARGS.workers == ARGS.worker]
    t0 = time.time()
    for tid in P6.MATRIX:
        d = OUT / 'hold_controlled' / tid
        d.mkdir(parents=True, exist_ok=True)
        offs, path, marks = N6.pointer_path(tid)
        for seed in mine:
            f = d / ('%d.npz' % seed)
            if f.exists():
                continue
            session.reset(seed)
            N6.place(session, offs)
            policy.reset()
            captured.clear()
            w = session.world
            geo, ret, sens = [], [], []
            for ox, oy in path:
                geo.append(N6.geometry_row(w)[:9])
                session.tick(pointer=(P6.FLY_POSE[0] + ox, P6.FLY_POSE[1] + oy), strike=False)
                r = session.last_retina
                ret.append((r.theta, r.theta_dot, r.azimuth))
                s = session.fly_loop.last_sensory_spikes
                sens.append((s['LPLC2_left'], s['LC4_left'], s['LPLC2_right'], s['LC4_right']))
                if (w.fly.x, w.fly.y) != P6.FLY_POSE[:2] or 'approach' not in str(w.swatter.phase).lower():
                    raise RuntimeError('controlled state violated')
            spk = np.zeros((len(path), 4), np.uint8)
            for t, fired in enumerate(captured):
                spk[t] = [np.any(fired == esc[0]), np.any(fired == esc[1]),
                          np.any(fired == N6.DNP04['L']), np.any(fired == N6.DNP04['R'])]
            np.savez_compressed(f, geo=np.array(geo), retina=np.array(ret), sensory=np.array(sens, np.int32),
                                dnp01_trace=np.array([(m.dnp01_left, m.dnp01_right) for m in policy.history]), spikes=spk)
        print('worker %d %s done (%.0f s)' % (ARGS.worker, tid, time.time() - t0), flush=True)
    session.close()


# ================================================================== analysis ===
def analyze():
    reg = check_frozen()
    runtime()
    res = {'label': 'M1.8-N4B7 fresh-holdout results', 'preregistration_sha256': sha256(PREREG),
           'candidates_sha256': reg['candidates_sha256']}
    # A. fixed-fly N0 holdout
    files = sorted((OUT / 'hold_n0').glob('*.npz'))
    trials = [(f.stem, np.load(f)['left'], np.load(f)['right']) for f in files]
    res['fixed_fly_n0'] = n0_score(trials, C.HOLDOUT['fixed_fly_n0']['ticks_per_trial'] * DT / 60)
    res['fixed_fly_n0']['trials'] = len(trials)
    for n in ('N4B1C', 'L1 combined', 'L1 alone', 'L2 combined', 'L3 combined'):
        v = res['fixed_fly_n0'][n]
        print('hold N0', n, v['events'], round(v['minutes']), round(v['upper95_per_min'], 4), 'burst', v['max_long_events_in_5s'])
    # C. controlled
    per = {}
    for tid in P6.MATRIX:
        fs = sorted((OUT / 'hold_controlled' / tid).glob('*.npz'))
        per[tid] = [controlled_trial(tid, np.load(f)) for f in fs]
    res['controlled'] = controlled_summary(per)
    show_controlled(res['controlled'])
    # B. free flight (live L1 combined, and the N4B1C reference with shadow candidates)
    recs = [json.loads(f.read_text(encoding='utf-8')) for f in sorted((OUT / 'hold_room').glob('*.json'))]
    res['free_flight'] = room_holdout(recs)
    # D. fresh committed strikes
    n1 = [t for f in sorted(OUT.glob('hold_n1_part*.json')) for t in read(f.name)]
    res['n1_committed'] = n1_score(n1)
    print('hold N1', {k: {n: (x['covered'], x['median_s']) for n, x in v.items() if n in ('N4B1C', 'L1 combined')} for k, v in res['n1_committed'].items()})
    write('holdout.json', res)
    res['decision'] = decide(res)
    write('holdout.json', res)
    print(json.dumps(res['decision'], indent=1, default=float))


def arrays(rows):
    a = {k: np.array(v) for k, v in rows.items() if k != 'lifecycle'}
    a['lifecycle'] = rows['lifecycle']
    return a


def room_holdout(recs):
    minutes = sum(len(r['N4B1C']['rows']['dl']) for r in recs) / 3000
    out = {'runs': len(recs), 'minutes': minutes}
    for live in ('N4B1C', 'L1 combined'):
        evs, bursts = [], 0
        for r in recs:
            a = arrays(r[live]['rows'])
            ref_n4b1c = [e['t'] for e in replay('N4B1C', a['dl'], a['dr'])]
            bursts = max(bursts, max_long_in_5s(r[live]['events']))
            for e in r[live]['events']:
                cf = r[live]['cf_min_horizontal'].get(str(e['t']))
                x = dict(e, seed=r['seed'], **classify(a, e['t'], cf), lifecycle=a['lifecycle'][e['t']],
                         max_drive_last_50=float(np.max(a['drive'][max(0, e['t'] - 49):e['t'] + 1])))
                if 'LONG' in e['paths'].split('+'):
                    nxt = next((u for u in ref_n4b1c if u >= e['t']), None)
                    x['n4b1c_alone_replay_next_s'] = None if nxt is None else (nxt - e['t']) * DT
                evs.append(x)
        cats = Counter(e['category'] for e in evs)
        out[live] = {'escapes': len(evs), 'per_min': len(evs) / minutes, 'upper95_per_min': poisson_upper(len(evs), minutes),
                     'categories': {c: {'events': cats.get(c, 0), 'per_min': cats.get(c, 0) / minutes,
                                        'upper95_per_min': poisson_upper(cats.get(c, 0), minutes)}
                                    for c in ('A', 'B', 'C', 'D', 'mixed')},
                     'paths': dict(Counter(e['paths'] for e in evs)),
                     'long_path_escapes': sum('LONG' in e['paths'].split('+') for e in evs),
                     'long_only_escapes': sum(e['paths'] == 'LONG' for e in evs),
                     'long_only_categories': dict(Counter(e['category'] for e in evs if e['paths'] == 'LONG')),
                     'max_long_events_in_5s': bursts, 'list': evs}
    # Shadow candidates on the N4B1C reference runs.
    names = [n for n, r_, m in DECODERS if m == 'combined']
    runs = []
    for r in recs:
        a = arrays(r['N4B1C']['rows'])
        runs.append(shadow_room(str(r['seed']), a, names))
    out['shadow_on_reference'] = room_rates(runs, names)
    for live in ('N4B1C', 'L1 combined'):
        v = out[live]
        print('hold ROOM', live, v['escapes'], {c: x['events'] for c, x in v['categories'].items()}, 'LONG-only', v['long_only_escapes'])
    return out


def decide(res):
    """Mechanical application of tools/n4b7_candidates.py DECISION_RULE (conditions 1-3, 5;
    condition 4 uses the development direct-strike replays, which have no fresh counterpart:
    fresh direct strikes do not exist without a player; see the report)."""
    ctl = res['controlled']
    comb = [ctl[t]['L1 combined'] for t in C.SLOW_130]
    base = [ctl[t]['N4B1C'] for t in C.SLOW_130]
    n = sum(x['n'] for x in comb)
    pooled = sum(x['p_timely'] * x['n'] for x in comb) / n
    pooled_base = sum(x['p_timely'] * x['n'] for x in base) / n
    leads = []
    for tid in C.SLOW_130:
        fs = sorted((OUT / 'hold_controlled' / tid).glob('*.npz'))
        for f in fs:
            m = controlled_trial(tid, np.load(f))['L1 combined']
            if m['timely']:
                leads.append(m['lead'])
    c1 = (pooled >= C.MATERIAL_POOLED_TIMELY and pooled - pooled_base >= C.MATERIAL_GAIN_OVER_N4B1C
          and all(x['p_timely'] >= C.MATERIAL_PER_TRAJECTORY for x in comb)
          and bool(leads) and float(np.median(leads)) >= C.MATERIAL_MEDIAN_LEAD_S)
    n0 = res['fixed_fly_n0']['L1 combined']
    fixed_ctl = [ctl[t]['L1 combined'] for t in ('F1_stationary_near', 'F2_recede_slow')]
    k = sum(x['false_events'] for x in fixed_ctl) + sum(ctl[t]['L1 combined']['pre_onset_events'] for t in P6.MATRIX)
    mins = sum(x['minutes'] for x in fixed_ctl) + len(P6.MATRIX) * ctl['F1_stationary_near']['L1 combined']['n'] * P6.PRE_HOLD_TICKS * DT / 60
    c2 = n0['upper95_per_min'] < 0.1 and n0['minutes'] >= 280 and poisson_upper(k, mins) < 0.1
    ff = res['free_flight']['L1 combined']['categories']
    c3 = ff['B']['upper95_per_min'] < 0.1 and ff['A']['upper95_per_min'] < 0.1
    c5 = res['fixed_fly_n0']['L1 combined']['max_long_events_in_5s'] < 3 and res['free_flight']['L1 combined']['max_long_events_in_5s'] < 3
    return {'c1_slow_130': {'pass': c1, 'pooled_combined': pooled, 'pooled_n4b1c': pooled_base,
                            'per_trajectory': {t: ctl[t]['L1 combined']['p_timely'] for t in C.SLOW_130},
                            'median_lead_s': float(np.median(leads)) if leads else None},
            'c2_fixed_fly': {'pass': c2, 'n0_events': n0['events'], 'n0_minutes': n0['minutes'],
                             'n0_upper95': n0['upper95_per_min'], 'controls_and_preholds_events': k,
                             'controls_and_preholds_minutes': mins, 'controls_upper95': poisson_upper(k, mins)},
            'c3_free_flight': {'pass': c3, 'B': ff['B'], 'A': ff['A']},
            'c4_direct_strikes_fresh_n1': {'pass': all(
                res['n1_committed'][k]['L1 combined']['covered'] >= res['n1_committed'][k]['N4B1C']['covered']
                and res['n1_committed'][k]['L1 combined']['median_s'] <= res['n1_committed'][k]['N4B1C']['median_s'] + 0.02 + 1e-9
                for k in ('strong_direct', 'medium_committed')),
                'detail': {k: {n: res['n1_committed'][k][n] for n in ('N4B1C', 'L1 combined')} for k in res['n1_committed']},
                'note': 'the development N1 and human-replay parts of condition 4 are evaluated in the report'},
            'c5_no_pathological_repetition': {'pass': c5,
                                              'fixed_fly_max_long_in_5s': res['fixed_fly_n0']['L1 combined']['max_long_events_in_5s'],
                                              'free_flight_max_long_in_5s': res['free_flight']['L1 combined']['max_long_events_in_5s']}}


if __name__ == '__main__':
    {'dev-n0': dev_n0, 'dev-controlled': dev_controlled, 'dev-room': dev_room, 'dev-n1': dev_n1,
     'dev-human': dev_human, 'dev-summary': dev_summary, 'freeze': freeze, 'hold-n0': hold_n0,
     'hold-room': hold_room, 'hold-controlled': hold_controlled, 'hold-n1': hold_n1, 'analyze': analyze}[ARGS.mode]()
