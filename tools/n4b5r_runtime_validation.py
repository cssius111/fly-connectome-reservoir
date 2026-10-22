"""M1.8-N4B5R runtime-candidate validation: elevation-aware paddle tilt geometry.

Validation only. It exercises the runtime code of this branch (game/world.py
`tilt_geometry`); the N4B1C decoder is unchanged and is run live (ROOM, recordings) or
replayed with the runtime FixedEscapePolicy on DNp01 traces (N1, N0, human sessions).
World geometry is used only to interpret recorded situations. Outputs go to
artifacts/m1_8_n4b5r/ (git-ignored).

Every mode that re-simulates old data also runs the accepted bearing_only_v0 geometry, which
must reproduce the original record exactly.

    python tools/n4b5r_runtime_validation.py geometry
    python tools/n4b5r_runtime_validation.py n1 --tilt elevation_aware_tilt_v1    (4 Numba threads; also --tilt bearing_only_v0)
    python tools/n4b5r_runtime_validation.py n0 --tilt elevation_aware_tilt_v1    (4 threads; also bearing_only_v0)
    python tools/n4b5r_runtime_validation.py human --tilt elevation_aware_tilt_v1 --noise-offset 0   (8 threads)
    python tools/n4b5r_runtime_validation.py room --source n4b3_holdout --seed 7401 [--suppress TICK]
    python tools/n4b5r_runtime_validation.py record                                (recorder schema + exact replay)
    python tools/n4b5r_runtime_validation.py replay --path results/game/sessions/<id>
    python tools/n4b5r_runtime_validation.py summary

The ROOM mode needs the stored N4B4 inventory and run records of the research branch
(`--research-root`, default: the main checkout three levels up).
"""
from __future__ import annotations

import argparse
from collections import Counter
import copy
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / 'artifacts/m1_8_n4b5r'
DT = 0.02
PARKED = (1920.0, 388.8)
FOOTPRINT, NEAR = 155.0, 310.0
SUPPRESS_TICKS, HORIZON_TICKS = 100, 150
SESSIONS = {'strict_n2': '20260923T005351.731330Z-38255ec8', 'n2b': '20260924T000111.561327Z-c337a721'}
N1_COMMIT = '76806f0'
N0_COMMIT = '3d41113'


def _args():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('mode', choices=('geometry', 'n1', 'n0', 'human', 'room', 'record', 'replay', 'summary'))
    p.add_argument('--tilt', default='elevation_aware_tilt_v1')
    p.add_argument('--noise-offset', type=int, default=0)
    p.add_argument('--source')
    p.add_argument('--seed', type=int)
    p.add_argument('--suppress', type=int)
    p.add_argument('--path')
    p.add_argument('--research-root', default=str(ROOT.parents[2]))
    return p.parse_args()


ARGS = _args() if __name__ == '__main__' else None
if ARGS is not None:
    os.environ.setdefault('NUMBA_NUM_THREADS', {'human': '8', 'n1': '4', 'n0': '4'}.get(ARGS.mode, '1'))
    os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')
sys.path.insert(0, str(ROOT))

import numpy as np  # noqa: E402


def room_config(tilt=None):
    from game.session import load_config
    cfg = load_config(ROOT / 'game_room_config.json')
    if tilt is not None:
        cfg['swatter']['directional']['tilt_geometry'] = tilt
    return cfg


def git_config(commit, tilt):
    cfg = json.loads(subprocess.check_output(['git', 'show', commit + ':game_room_config.json'], cwd=ROOT, text=True))
    cfg['swatter']['directional']['tilt_geometry'] = tilt
    return cfg


def runtime_policy():
    from game.session import build_policy
    return build_policy(room_config())[0]


def n4b1c_events(left, right):
    """Frozen decoder replay on DNp01 traces (fresh policy state); returns [(sample, paths)]."""
    from game.action import MotorState
    pol = runtime_policy()
    pol.reset()
    zero = np.zeros(1, np.float32)
    out = []
    for t in range(len(left)):
        a = pol.decide(MotorState(float(left[t]), float(right[t]), 0.0, 0.0, zero))
        if a.escape:
            out.append((t, pol.criterion_diagnostics()['escape_trigger_paths']))
    return out


def poisson_upper(k, minutes):
    from scipy.stats import chi2
    return float(chi2.ppf(0.95, 2 * k + 2) / 2 / minutes)


def write(name, obj):
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / name).write_text(json.dumps(obj, indent=1, default=float) + '\n', encoding='utf-8')


# ------------------------------------------------------------------ geometry ---
def geometry():
    from game.world import World
    out = {}
    for tilt in ('bearing_only_v0', 'elevation_aware_tilt_v1'):
        w = World(room_config(tilt), 1)
        res = {}
        for cross in (0, 45, 90):
            for off in (0.0, 2.0, 10.0, 25.0, 50.0, 100.0, 300.0):
                d = math.radians(cross)
                ux, uy = math.cos(d), math.sin(d)
                nx, ny = -uy, ux
                th, hs, rs = [], [], []
                for k in range(int(1200 / 200 / DT) + 1):
                    s = -600 + 200 * DT * k
                    w.fly.x, w.fly.y = 1900 + nx * off + ux * s, 1000 + ny * off + uy * s
                    sw = w.swatter
                    sw.x, sw.y, sw.height, sw.face, sw.orientation = 1900.0, 1000.0, 320.0, 0.0, 0.0
                    h = w.visual_half_size
                    r = math.sqrt((w.fly.x - 1900) ** 2 + (w.fly.y - 1000) ** 2 + 320 ** 2)
                    th.append(2 * math.atan(h / r)); hs.append(h); rs.append(r)
                td = np.diff(th) / DT
                size = [(2 * math.atan(hs[k + 1] / rs[k + 1]) - 2 * math.atan(hs[k] / rs[k + 1])) / DT for k in range(len(hs) - 1)]
                res['cross%d_offset%d' % (cross, off)] = {'max_theta_dot': float(td.max()), 'max_size_theta_dot': float(max(size))}
        strike = []
        for off in (30.0, 100.0, 170.0):
            th = []
            for k in range(26):
                q = k / 25
                w.fly.x, w.fly.y = 1900 + off, 1000.0
                sw = w.swatter
                sw.x, sw.y, sw.height, sw.face, sw.orientation = 1900.0, 1000.0, 320 - 296 * q, q, 0.0
                r = math.sqrt(off ** 2 + sw.height ** 2)
                th.append(2 * math.atan(w.visual_half_size / r))
            strike.append({'offset': off, 'theta_end': th[-1], 'max_theta_dot': float(np.max(np.diff(th)) / DT)})
        out[tilt] = {'passes': res, 'strike_like': strike}
    write('geometry.json', out)
    for tilt, r in out.items():
        print(tilt, 'cross90 max theta_dot by offset:',
              {k.split('offset')[1]: round(v['max_theta_dot'], 2) for k, v in r['passes'].items() if k.startswith('cross90')},
              '| strike', [(s['offset'], round(s['max_theta_dot'], 2)) for s in r['strike_like']])


# ------------------------------------------------------------------ N1 ---
def run_n1(tilt):
    from game.session import Session
    from tools.calibrate_escape import RecordingPolicy
    from tools.loom_robustness_study import run_trial, DT as LDT
    config = git_config(N1_COMMIT, tilt)
    data = np.load(Path(ARGS.research_root) / 'artifacts/m1_8_loom_robustness/trials.npz')
    meta = json.loads((Path(ARGS.research_root) / 'artifacts/m1_8_loom_robustness/trials_meta.json').read_text(encoding='utf-8'))
    settle = max(40, round(config['swatter'].get('physical', {}).get('calibration_settle_seconds', 0.8) / LDT))
    policy = RecordingPolicy()
    session = Session(config, policy=policy, root=ROOT)
    session.world.collisions_enabled = False
    session.world.fly_motion_enabled = False
    rng = np.random.default_rng(int(config['encoder']['encoder_seed']) + 991)
    classes = ('strong_direct', 'medium_committed', 'weak_approach', 'glancing_pass', 'aborted_approach')
    by, equal, idx = {}, 0, 0
    for ci, kind in enumerate(classes):
        for i in range(60):
            t = run_trial(session, policy, 6000 + ci * 1000 + i, kind, rng, settle)
            hist = policy.history[-t['ticks']:]
            equal += bool(np.array_equal(t['dnp01'], data['%d_dnp01' % idx]))
            m = meta['trials'][idx]
            onset = m['click_tick'] if m['click_tick'] is not None else m['window_start']
            ev = n4b1c_events([h.dnp01_left for h in hist], [h.dnp01_right for h in hist])
            f = next((s for s, _ in ev if s >= onset), None)
            by.setdefault(kind, []).append(None if f is None else f - onset)
            idx += 1
        print('  N1 %s %s done' % (tilt, kind), flush=True)
    session.close()
    res = {'tilt': tilt, 'config': 'git %s ROOM config with tilt_geometry=%s' % (N1_COMMIT, tilt),
           'dnp01_identical_to_recorded_trials': equal, 'classes': {}}
    for k, v in by.items():
        d = [x for x in v if x is not None]
        res['classes'][k] = {'detected': len(d), 'n': len(v), 'median_s': float(np.median(d)) * DT if d else None,
                             'p95_s': float(np.percentile(d, 95)) * DT if d else None}
    write('n1_%s.json' % tilt, res)
    print(json.dumps(res))


# ------------------------------------------------------------------ N0 ---
def run_n0(tilt):
    from game.session import Session
    from tools.calibrate_escape import RecordingPolicy, _trial
    config = git_config(N0_COMMIT, tilt)
    raw = np.load(Path(ARGS.research_root) / 'artifacts/m1_8_no_loom_calibration/raw.npz')['null']
    policy = RecordingPolicy()
    session = Session(config, policy=policy, root=ROOT)
    session.world.collisions_enabled = False
    session.world.fly_motion_enabled = False
    rng = np.random.default_rng(int(config['encoder']['encoder_seed']))
    events, equal, max_drive = [], 0, 0.0
    for i in range(150):
        angle = float(rng.uniform(0, 2 * np.pi))
        radius = float(rng.uniform(30.0, 170.0))
        t = _trial(session, policy, 4000 + i, (np.cos(angle) * radius, np.sin(angle) * radius), 1400, None)
        equal += bool(np.array_equal(t['total'], raw[i * 1400:(i + 1) * 1400]))
        for s, lab in n4b1c_events(t['left'], t['right']):
            events.append({'trial': i, 'sample': s, 'paths': lab})
    session.close()
    res = {'tilt': tilt, 'minutes': 70.0, 'events': len(events), 'upper95_per_min': poisson_upper(len(events), 70.0),
           'list': events, 'total_identical_to_recorded_trials': equal}
    write('n0_%s.json' % tilt, res)
    print(json.dumps({k: v for k, v in res.items() if k != 'list'}))


# ------------------------------------------------------------------ human ---
def human_windows(research_root):
    sys.path.insert(0, str(research_root))
    from tools import n4_diagnosis as D     # research branch module (read-only)
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
    win.append({'session': 'n2b', 'episode': 5, 'cls': 'slow_close', 't0': 610, 't1': 670, 'anchor': 610})
    win.append({'session': 'n2b', 'episode': 5, 'cls': 'chase_before_589', 't0': 570, 't1': 589, 'anchor': 570})
    eps, _ = D.session_rows(D.SESSIONS['strict_n2'])
    win.append({'session': 'strict_n2', 'episode': 1, 'cls': 'far_perched', 't0': eps[1][2434]['tick'],
                't1': eps[1][2528]['tick'], 'anchor': eps[1][2434]['tick']})
    eps, _ = D.session_rows(D.SESSIONS['n2b'])
    rows = eps[1]
    k = next(i for i, r in enumerate(rows) if any(e['type'] == 'voluntary_takeoff' for e in r['lifecycle']['events']))
    win.append({'session': 'n2b', 'episode': 1, 'cls': 'voluntary_takeoff', 't0': rows[k - 50]['tick'],
                't1': rows[min(len(rows) - 1, k + 25)]['tick'], 'anchor': rows[k]['tick']})
    return win


def run_human(tilt, noise_offset):
    """Open-loop: Retina recomputed with the runtime World.visual_half_size from the recorded
    world states (Retina of row t from the state stored at row t-1), fed to the brain."""
    from game.fly import build_brain
    from game.perception import Retina, RetinalEncoder
    from game.world import World
    research = Path(ARGS.research_root)
    out, exact = {}, {}
    for sess, name in SESSIONS.items():
        path = research / 'results/game/sessions' / name
        manifest = json.loads((path / 'manifest.json').read_text(encoding='utf-8'))
        config = copy.deepcopy(manifest['config'])
        config['swatter']['directional']['tilt_geometry'] = tilt
        brain = build_brain(config, ROOT)
        encoder = RetinalEncoder(brain, config)
        w = World(config, 1)
        l_idx, r_idx = int(brain.groups['escape_L'][0]), int(brain.groups['escape_R'][0])
        decay = np.float32(np.exp(-DT / float(config['brain']['trace_tau_seconds'])))
        seeds = {json.loads(l)['episode']: json.loads(l)['seed'] for l in (path / 'episodes.jsonl').open(encoding='utf-8')}
        eps = {}
        for l in (path / 'ticks.jsonl').open(encoding='utf-8'):
            r = json.loads(l)
            eps.setdefault(r['episode'], []).append(r)

        def theta_of(row):
            f, s = row['fly'], row['swatter']
            w.fly.x, w.fly.y = f['x'], f['y']
            sw = w.swatter
            sw.x, sw.y, sw.height, sw.face, sw.orientation = s['x'], s['y'], s['height'], s['face'], s['orientation']
            rng = math.sqrt((s['x'] - f['x']) ** 2 + (s['y'] - f['y']) ** 2 + s['height'] ** 2)
            return 2.0 * math.atan(w.visual_half_size / max(rng, 1e-6))
        sess_out, eq, tot = {}, 0, 0
        for ep, er in eps.items():
            brain.reset(int(seeds[ep]) + 977 + noise_offset)
            thetas = []
            for i, r in enumerate(er):
                thetas.append(r['retina']['theta'] if i == 0 else theta_of(er[i - 1]))
            tl = tr = np.float32(0.0)
            ticks, lefts, rights = [], [], []
            for i, r in enumerate(er):
                if not r['neural']['brain_stepped']:
                    continue
                td = 0.0 if i == 0 else (thetas[i] - thetas[i - 1]) / DT
                fired = np.asarray(brain.step(inject=encoder.inject(Retina(thetas[i], td, r['retina']['azimuth']))))
                tl = np.float32(tl * decay); tr = np.float32(tr * decay)
                if np.any(fired == l_idx):
                    tl = np.float32(tl + np.float32(1.0))
                if np.any(fired == r_idx):
                    tr = np.float32(tr + np.float32(1.0))
                ticks.append(r['tick']); lefts.append(float(tl)); rights.append(float(tr))
                tot += 1
                eq += (float(tl) == r['neural']['dnp01_left'] and float(tr) == r['neural']['dnp01_right'])
            sess_out[str(ep)] = {'ticks': ticks, 'left': lefts, 'right': rights}
        out[sess] = sess_out
        exact[sess] = [eq, tot]
    # score
    res = {'tilt': tilt, 'noise_offset': noise_offset, 'dnp01_rows_equal_to_recorded': exact, 'classes': {}}
    total = sum(len(n4b1c_events(e['left'], e['right'])) for s in out.values() for e in s.values())
    res['open_loop_firings'] = total
    per = {}
    for wdw in human_windows(research):
        e = out[wdw['session']][str(wdw['episode'])]
        t = e['ticks']
        i0 = next(i for i, x in enumerate(t) if x >= wdw['t0'])
        i1 = max(i for i, x in enumerate(t) if x <= wdw['t1'])
        ev = n4b1c_events(e['left'][i0:i1 + 1], e['right'][i0:i1 + 1])
        per.setdefault(wdw['cls'], []).append((None if not ev else t[i0 + ev[0][0]], wdw['anchor']))
    ds = [(f, a) for f, a in per['direct_strike']]
    fired = [(f - a) * DT for f, a in ds if f is not None]
    after = [x for x in fired if x >= 0]
    res['classes']['direct_strikes'] = {'fired': len(fired), 'n': len(ds), 'before_click': sum(x < 0 for x in fired),
                                        'median_after_click_s': float(np.median(after)) if after else None}
    for cls in ('hover_escape', 'strike_escape'):
        res['classes'][cls] = {'met': sum(f is not None and f <= a for f, a in per[cls]), 'n': len(per[cls])}
    for cls in ('slow_close', 'chase_before_589', 'far_perched', 'voluntary_takeoff'):
        res['classes'][cls] = per[cls][0][0]
    write('human_%s_noise%d.json' % (tilt, noise_offset), res)
    print(json.dumps(res))


# ------------------------------------------------------------------ ROOM ---
class Suppress:
    """Counterfactual: escapes of the unchanged runtime policy in the window are withheld from
    the world (only the smoothed turn is kept) and its ESCAPE state is shown as ALERT."""

    def __init__(self, policy, ref, start):
        self._p, self._r, self.start, self.end, self.suppressed = policy, ref, start, start + SUPPRESS_TICKS, []

    def __getattr__(self, name):
        return getattr(self._p, name)

    def reset(self):
        return self._p.reset()

    def decide(self, motor):
        a = self._p.decide(motor)
        if a.escape and self.start <= self._r['tick'] < self.end:
            from game.action import Action
            self.suppressed.append(self._r['tick'])
            return Action(turn=a.turn)
        return a

    def diagnostics(self):
        d = dict(self._p.diagnostics())
        if self.start <= self._r['tick'] < self.end and d.get('behavior_state') == 'ESCAPE':
            d['behavior_state'] = 'ALERT'
        return d


def run_room(source, seed, suppress=None):
    from game.session import Session, build_policy
    inv = json.loads((Path(ARGS.research_root) / 'artifacts/m1_8_n4b4/inventory.json').read_text(encoding='utf-8'))
    run = next(r for r in inv['runs'] if r['source'] == source and r['seed'] == seed)
    if int(os.environ['NUMBA_NUM_THREADS']) != run['threads']:
        raise SystemExit('run with NUMBA_NUM_THREADS=%d' % run['threads'])
    config = room_config()
    policy, _ = build_policy(config)
    ref = {'tick': 0}
    active = Suppress(policy, ref, suppress) if suppress is not None else policy
    s = Session(config, policy=active, seed=seed, mode='evaluation')
    until = run['ticks'] if suppress is None else min(run['ticks'], suppress + HORIZON_TICKS)
    rows = []
    for t in range(until):
        ref['tick'] = t
        s.tick(pointer=PARKED, strike=False)
        motor = s.fly_loop.last_motor
        fly, sw = s.world.fly, s.world.swatter
        r = s.last_retina
        d = s.encoder.last_drive or {}
        rows.append({'tick': t, 'theta': r.theta, 'theta_dot': r.theta_dot, 'azimuth': r.azimuth,
                     'escape': bool(policy.refractory_remaining == policy.refractory_ticks
                                    and policy.criterion_diagnostics()['escape_trigger_channel'] != 'NONE'),
                     'paths': policy.criterion_diagnostics()['escape_trigger_paths'],
                     'drive': sum(d.get(k, 0.0) for k in ('loomL', 'loomR', 'threatL', 'threatR')),
                     'lateral': None if not s.fly_loop.last_action.escape else s.fly_loop.last_action.lateral,
                     'dnp01': None if motor is None else [motor.dnp01_left, motor.dnp01_right],
                     'lifecycle': str(s.world.lifecycle.mode) if s.world.lifecycle else None,
                     'fly': [fly.x, fly.y, fly.vx, fly.vy], 'paddle': [sw.x, sw.y, sw.height, sw.vx, sw.vy],
                     'half': s.world.visual_half_size, 'hits': s.stats.hits, 'lethal': s.world.lethal})
    s.close()
    esc = [r['tick'] for r in rows if r['escape']]
    name = 'room_%s_seed%d%s.json' % (source, seed, '' if suppress is None else '_cf%d' % suppress)
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / name).write_text(json.dumps({'source': source, 'seed': seed, 'threads': run['threads'], 'ticks': run['ticks'],
                                        'suppress': suppress, 'escape_ticks': esc, 'rows': rows}) + '\n', encoding='utf-8')
    print(name, len(esc), esc)


def geometry_row(row):
    fx, fy, fvx, fvy = row['fly']
    px, py, ph, pvx, pvy = row['paddle']
    dx, dy = px - fx, py - fy
    dh = math.hypot(dx, dy)
    rng = math.sqrt(dh * dh + ph * ph)
    return dh, rng, -(dx * (fvx - pvx) + dy * (fvy - pvy)) / rng, math.degrees(math.atan2(ph, dh))


def room_summary(research_root):
    inv = json.loads((Path(research_root) / 'artifacts/m1_8_n4b4/inventory.json').read_text(encoding='utf-8'))
    events, minutes, missing = [], 0.0, 0
    for r in inv['runs']:
        p = OUT / ('room_%s_seed%d.json' % (r['source'], r['seed']))
        if not p.exists():
            missing += 1
            continue
        m = json.loads(p.read_text(encoding='utf-8'))
        minutes += m['ticks'] / 3000
        rows = m['rows']
        for t in m['escape_ticks']:
            i = t
            drive = max(x['drive'] for x in rows[max(0, i - 9):i + 1])
            pos_r = pos_s = 0.0
            for j in range(max(2, i - 9), i + 1):
                a, b = rows[j - 2], rows[j - 1]
                ra, rb = geometry_row(a)[1], geometry_row(b)[1]
                pos_r += max(2 * math.atan(a['half'] / rb) - 2 * math.atan(a['half'] / ra), 0.0)
                pos_s += max(2 * math.atan(b['half'] / rb) - 2 * math.atan(a['half'] / rb), 0.0)
            share = pos_s / (pos_r + pos_s) if pos_r + pos_s > 0 else None
            dh, rng, rr, elev = geometry_row(rows[i - 1])
            cfp = OUT / ('room_%s_seed%d_cf%d.json' % (r['source'], r['seed'], t))
            cf_min = None
            if cfp.exists():
                cr = json.loads(cfp.read_text(encoding='utf-8'))['rows']
                cf_min = min(geometry_row(x)[0] for x in cr[t + 1:t + 76])
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
            events.append({'source': r['source'], 'seed': r['seed'], 'tick': t, 'paths': rows[i]['paths'],
                           'category': cat, 'drive': drive, 'elevation_deg': elev, 'range_rate': rr,
                           'size_share': share, 'counterfactual_min_horizontal': cf_min,
                           'counterfactual_available': cfp.exists(), 'lateral': rows[i]['lateral'],
                           'azimuth': rows[i]['azimuth'], 'lifecycle': rows[i]['lifecycle']})
    counts = Counter(e['category'] for e in events)
    rates = {c: {'events': counts.get(c, 0), 'per_min': counts.get(c, 0) / minutes if minutes else None,
                 'upper95_per_min': poisson_upper(counts.get(c, 0), minutes) if minutes else None}
             for c in ('A', 'B', 'C', 'D', 'mixed')}
    rates['all'] = {'events': len(events), 'per_min': len(events) / minutes if minutes else None,
                    'upper95_per_min': poisson_upper(len(events), minutes) if minutes else None}
    return {'minutes': minutes, 'missing_runs': missing, 'rates': rates, 'events': events,
            'counterfactuals_missing': sum(not e['counterfactual_available'] for e in events)}


# ------------------------------------------------------------------ recordings ---
def record():
    from game.replay import replay_session
    from game.session import Session
    from game.session_recording import HumanSessionRecorder
    OUT.mkdir(parents=True, exist_ok=True)
    rec = HumanSessionRecorder(OUT / 'recording')
    s = Session(room_config(), seed=255, recorder=rec)
    try:
        for _ in range(170):
            s.tick(pointer=PARKED)
        for _ in range(120):
            s.tick(pointer=(s.world.fly.x, s.world.fly.y))
        for t in range(260):
            fx, fy = s.world.fly.x, s.world.fly.y
            s.tick(pointer=(fx + 20.0, fy + 10.0), strike=(t == 180))
    finally:
        s.close()
    manifest = json.loads((rec.path / 'manifest.json').read_text(encoding='utf-8'))
    rows = [json.loads(l) for l in (rec.path / 'ticks.jsonl').open(encoding='utf-8')]
    result = replay_session(rec.path, write_report=False)
    out = {'path': str(rec.path), 'schema': manifest['recording_schema_version'],
           'config_version': manifest['config']['config_version'],
           'tilt_geometry': manifest['config']['swatter']['directional'].get('tilt_geometry'),
           'decoder': manifest['config']['policy']['escape_decoder']['kind'],
           'calibration_origin': manifest['calibration'].get('origin', manifest['calibration']),
           'recorded_diagnostics_keys': sorted({k for r in rows for k in r['neural']['diagnostics']}),
           'ticks': len(rows), 'escapes': sum(r['action']['escape'] for r in rows),
           'replay_exact': result['exact'], 'replay_ticks_verified': result.get('ticks_verified')}
    write('record.json', out)
    print(json.dumps(out, default=str))


def replay_existing(path):
    from game.replay import replay_session
    path = Path(path).resolve()
    result = replay_session(path, write_report=False, strict_source=False)
    manifest = json.loads((path / 'manifest.json').read_text(encoding='utf-8'))
    out = {'path': str(path), 'config_version': manifest['config'].get('config_version'),
           'tilt_geometry_in_recorded_config': (manifest['config']['swatter'].get('directional') or {}).get('tilt_geometry'),
           'exact': result['exact'], 'ticks_verified': result.get('ticks_verified'),
           'numba_threads': int(os.environ['NUMBA_NUM_THREADS'])}
    write('replay_%s.json' % path.name, out)
    print(json.dumps(out))


def summary():
    res = {'room': room_summary(ARGS.research_root)}
    for f in sorted(OUT.glob('*.json')):
        if f.name.startswith(('n1_', 'n0_', 'human_', 'geometry', 'record', 'replay_')):
            d = json.loads(f.read_text(encoding='utf-8'))
            res[f.stem] = {k: v for k, v in d.items() if k != 'list'} if isinstance(d, dict) else d
    write('summary.json', res)
    r = res['room']
    print('ROOM %.0f min (missing %d, cf missing %d):' % (r['minutes'], r['missing_runs'], r['counterfactuals_missing']),
          {k: (v['events'], round(v['per_min'] or 0, 4), round(v['upper95_per_min'] or 0, 4)) for k, v in r['rates'].items()})
    for k, v in res.items():
        if k != 'room':
            print(k, json.dumps(v)[:400])


if __name__ == '__main__':
    m = ARGS.mode
    if m == 'geometry':
        geometry()
    elif m == 'n1':
        run_n1(ARGS.tilt)
    elif m == 'n0':
        run_n0(ARGS.tilt)
    elif m == 'human':
        run_human(ARGS.tilt, ARGS.noise_offset)
    elif m == 'room':
        run_room(ARGS.source, ARGS.seed, ARGS.suppress)
    elif m == 'record':
        record()
    elif m == 'replay':
        replay_existing(ARGS.path)
    else:
        summary()
