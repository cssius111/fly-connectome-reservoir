"""M1.8-N4B6: controlled slow-approach characterization under the accepted runtime.

Research only. No runtime code, configuration, decoder, whitelist, Retina / encoder equation,
MaleCNS parameter, brain noise or physics is changed. The accepted runtime (M1.8-N4B5R,
`feature/m1-8-n4b5r-geometry` @ 363a1a9: G3 geometry + N4B1C decoder) is imported read-only
from its worktree, which must be clean at that commit. The preregistered stimulus matrix and
rules live in `tools/n4b6_protocol.py`; `freeze` records its sha256 and every simulation
refuses to run if it changed.

Chain (nothing bypassed, nothing injected): scripted pointer -> accepted physical swatter ->
World.visual_half_size (G3) -> RetinaProjector -> RetinalEncoder (LC4 / LPLC2) -> MaleCNS ->
DNp01 trace -> N4B1C decoder replay (runtime FixedEscapePolicy). DNp04 spikes are read from
the same brain step, offline only. Measurement conditions are fixed-fly-v2 (escape disabled,
fly motion disabled, collisions disabled) with ecology off, as in N1.

    python tools/n4b6_controlled_approach.py freeze
    python tools/n4b6_controlled_approach.py geometry                 (world only; no brain)
    python tools/n4b6_controlled_approach.py run --worker 0 --workers 8
    python tools/n4b6_controlled_approach.py analyze

Outputs go to artifacts/m1_8_n4b6/ (git-ignored).
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / 'artifacts/m1_8_n4b6'
RUNTIME = Path(os.environ.get('N4B5R_WORKTREE', ROOT / 'artifacts/worktrees/n4b5r-geometry')).resolve()
RUNTIME_COMMIT = '363a1a94cf3f5e33efab08cb28594c24ca694a03'
PROTOCOL_FILE = ROOT / 'tools/n4b6_protocol.py'
CRITERIA_FILE = ROOT / 'tools/n4b2_criteria.py'
CRITERIA_SHA = '6175f124b597f78847bb32061ab3876d1c4eb2b2d4698a05aac072d5c83d27a0'   # N4B2 frozen
PREREG = OUT / 'preregistration.json'
SENSORY_N0_MAX = 22          # N4A: LPLC2 + LC4 sensory spikes per side never exceed 22 in N0
DNP04 = {'L': 135203, 'R': 1052}                                  # N4B2 connectome panel
DNP04_READOUTS = {'DNp04 pair 60 ms': {'kind': 'same_side', 'k': 2, 'window': 3},
                  'DNp04 triple 200 ms': {'kind': 'same_side', 'k': 3, 'window': 10}}


def _args():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('mode', choices=('freeze', 'geometry', 'run', 'analyze'))
    p.add_argument('--worker', type=int, default=0)
    p.add_argument('--workers', type=int, default=1)
    p.add_argument('--only', help='comma-separated trajectory ids (default: all)')
    p.add_argument('--seeds', type=int, help='limit to the first N seeds (timing checks)')
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


P = load_module('n4b6_protocol', PROTOCOL_FILE)
DT = P.DT


def check_runtime():
    head = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=RUNTIME, text=True).strip()
    dirty = subprocess.check_output(['git', 'status', '--porcelain', '--untracked-files=no'], cwd=RUNTIME,
                                    text=True).strip()
    if head != RUNTIME_COMMIT or dirty:
        raise SystemExit('runtime worktree %s must be clean at %s (HEAD %s, dirty: %r)'
                         % (RUNTIME, RUNTIME_COMMIT, head, dirty))
    if str(RUNTIME) not in sys.path:
        sys.path.insert(0, str(RUNTIME))
    import game
    if Path(game.__file__).resolve().parent != RUNTIME / 'game':
        raise SystemExit('game package resolved outside the runtime worktree: %s' % game.__file__)


def check_frozen():
    if not PREREG.exists():
        raise SystemExit('run `freeze` first: the protocol must be preregistered before any simulation')
    reg = json.loads(PREREG.read_text(encoding='utf-8'))
    if sha256(PROTOCOL_FILE) != reg['protocol_sha256']:
        raise SystemExit('tools/n4b6_protocol.py changed after preregistration')
    if sha256(CRITERIA_FILE) != CRITERIA_SHA:
        raise SystemExit('tools/n4b2_criteria.py differs from the frozen N4B2 criteria module')
    return reg


def trajectories():
    ids = list(P.MATRIX)
    if ARGS is not None and ARGS.only:
        ids = [i for i in ids if i in ARGS.only.split(',')]
    return ids


# ------------------------------------------------------------------ freeze ---
def freeze():
    if PREREG.exists():
        raise SystemExit('already frozen: %s' % PREREG)
    OUT.mkdir(parents=True, exist_ok=True)
    matrix = {}
    for tid, spec in P.MATRIX.items():
        offs, n, marks = P.script(spec['geometry'])
        matrix[tid] = dict(spec, motion_ticks=n, intended=marks, start_offset=offs[0], end_offset=offs[-1])
    reg = {'label': 'M1.8-N4B6 preregistered controlled slow-approach protocol (research only)',
           'frozen_utc': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
           'frozen_before_any_neural_simulation': True,
           'protocol_module': 'tools/n4b6_protocol.py', 'protocol_sha256': sha256(PROTOCOL_FILE),
           'dnp04_criteria_module': 'tools/n4b2_criteria.py', 'dnp04_criteria_sha256': CRITERIA_SHA,
           'runtime_commit': RUNTIME_COMMIT, 'seeds': list(P.SEEDS), 'matrix': matrix,
           'metrics': P.METRICS, 'classification': P.CLASSIFICATION, 'decision_rule': P.DECISION_RULE}
    PREREG.write_text(json.dumps(reg, indent=1) + '\n', encoding='utf-8')
    print('frozen', reg['protocol_sha256'])


# ------------------------------------------------------------------ session ---
def make_session():
    check_runtime()
    from game.session import Session, load_config
    from tools.calibrate_escape import RecordingPolicy       # noqa: F401  (runtime worktree copy)
    config = load_config(RUNTIME / 'game_room_config.json')
    assert config['swatter']['directional']['tilt_geometry'] == 'elevation_aware_tilt_v1'
    assert int(config['config_version']) == 17
    policy = RecordingPolicy()
    session = Session(config, policy=policy, root=RUNTIME, ecology_enabled=False)
    session.world.collisions_enabled = False
    session.world.fly_motion_enabled = False
    return session, policy, config


def place(session, offsets):
    """Hold the fly at FLY_POSE; put the paddle at rest at the start point, facing its first
    movement; let the physical swatter settle world-only (no brain step)."""
    from game.action import NO_ACTION
    w = session.world
    fx, fy, fh = P.FLY_POSE
    w.fly.x, w.fly.y, w.fly.heading, w.fly.vx, w.fly.vy = fx, fy, fh, 0.0, 0.0
    sw = w.swatter
    x0, y0 = fx + offsets[0][0], fy + offsets[0][1]
    sw.x, sw.y, sw.vx, sw.vy = x0, y0, 0.0, 0.0
    w.set_pointer(x0, y0)
    ori = P.initial_orientation(offsets)
    sw.orientation = sw.attack_orientation = ori
    sw.angular_velocity = 0.0
    for _ in range(P.PLACEMENT_SETTLE_TICKS):
        w.set_pointer(x0, y0)
        w.tick(DT, NO_ACTION)
    if (math.hypot(sw.vx, sw.vy) > 1e-6 or math.hypot(sw.x - x0, sw.y - y0) > 1e-6
            or abs(sw.orientation - ori) > 1e-9 or abs(sw.height - P.HOVER_HEIGHT) > 1e-9 or sw.face != 0.0):
        raise RuntimeError('paddle did not rest at the start point with the preregistered pose')
    if (w.fly.x, w.fly.y, w.fly.heading) != P.FLY_POSE:
        raise RuntimeError('fly moved during placement')
    session.projector.reset()


def geometry_row(w):
    f, sw = w.fly, w.swatter
    dx, dy = sw.x - f.x, sw.y - f.y
    hd = math.hypot(dx, dy)
    rng = math.sqrt(hd * hd + sw.height * sw.height)
    return (sw.x, sw.y, sw.height, sw.face, sw.orientation, hd, rng, math.degrees(math.atan2(sw.height, hd)),
            w.visual_half_size, str(sw.phase))


def pointer_path(tid):
    offs, n, marks = P.script(P.MATRIX[tid]['geometry'])
    path = [offs[0]] * P.PRE_HOLD_TICKS + list(offs) + [offs[-1]] * P.POST_HOLD_TICKS
    return offs, path, marks


# ------------------------------------------------------------------ geometry ---
def geometry():
    """World-only stimulus characterisation (Retina computed exactly as the runtime does).
    Seed-independent and brain-free; may run before `freeze` (it uses no neural data)."""
    session, policy, config = make_session()
    from game.action import NO_ACTION
    from game.perception import RetinaProjector
    out = {}
    for tid in trajectories():
        offs, path, marks = pointer_path(tid)
        session.reset(P.SEEDS[0])
        place(session, offs)
        w, proj = session.world, RetinaProjector(DT)
        rows = []
        for k, (ox, oy) in enumerate(path):
            g = geometry_row(w)
            r = proj.project(w)
            rows.append(g[:9] + (r.theta, r.theta_dot, r.azimuth))
            w.set_pointer(P.FLY_POSE[0] + ox, P.FLY_POSE[1] + oy)
            w.tick(DT, NO_ACTION)
            if 'approach' not in str(w.swatter.phase).lower():
                raise RuntimeError('paddle left the approach phase')
        a = np.array(rows)
        out[tid] = summarize_geometry(tid, a, marks)
        OUT.mkdir(parents=True, exist_ok=True)
        np.save(OUT / ('geometry_%s.npy' % tid), a)
        print(tid, json.dumps({k: v for k, v in out[tid].items() if k in ('d0', 'closest_hdist', 'v_mean', 'theta_start', 'theta_closest', 'theta_dot_max', 'monotonic_range', 'min_hdist')}))
    (OUT / 'geometry.json').write_text(json.dumps(out, indent=1) + '\n', encoding='utf-8')
    session.close()


def closest_tick(rng, onset):
    seg = rng[onset:]
    return onset + int(np.flatnonzero(seg <= seg.min() + 1.0)[0])


def summarize_geometry(tid, a, marks):
    spec = P.MATRIX[tid]
    on = P.PRE_HOLD_TICKS
    hd, rng, elev, half, th, td, az = a[:, 5], a[:, 6], a[:, 7], a[:, 8], a[:, 9], a[:, 10], a[:, 11]
    role = spec['role']
    if role in ('approach', 'abort'):
        c = closest_tick(rng, on)
    else:
        c = None
    end = c if c is not None else len(rng) - 1
    # theta_dot decomposition (N4B5): range part at fixed half size, size part at fixed range.
    size_part = np.zeros_like(th)
    size_part[1:] = (2 * np.arctan(half[1:] / rng[1:]) - 2 * np.arctan(half[:-1] / rng[1:])) / DT
    seg = slice(on, end + 1)
    closing = -np.diff(rng[on:end + 1]) / DT
    mono = bool(np.all(np.diff(rng[on:end + 1]) <= 1e-6)) if role in ('approach', 'abort') else None
    pre_td = float(np.max(np.abs(td[:on])))
    res = {'family': spec['family'], 'role': role, 'geometry': spec['geometry'],
           'd0': float(hd[on]), 'range0': float(rng[on]), 'az0_deg': float(az[on] * 180),
           'elev0_deg': float(elev[on]), 'theta_start': float(th[on]),
           'closest_tick_from_onset': None if c is None else c - on,
           'time_to_closest_s': None if c is None else (c - on) * DT,
           'closest_hdist': float(hd[end]), 'closest_range': float(rng[end]),
           'closest_elev_deg': float(elev[end]), 'closest_az_deg': float(az[end] * 180),
           'theta_closest': float(th[end]),
           'v_mean': float(np.mean(closing)) if closing.size else 0.0,
           'closing_speed_max': float(np.max(closing)) if closing.size else 0.0,
           'theta_dot_max': float(np.max(td[seg])), 'theta_dot_mean': float(np.mean(td[seg])),
           'theta_dot_at_closest_minus_0_25s': float(td[max(on, end - 13)]),
           'size_part_theta_dot_max': float(np.max(size_part[seg])),
           'size_part_theta_dot_min': float(np.min(size_part[seg])),
           'monotonic_range': mono, 'min_hdist': float(np.min(hd[on:])),
           'max_elev_deg': float(np.max(elev[on:])), 'pre_hold_max_abs_theta_dot': pre_td,
           'whole_trial_theta_dot_max': float(np.max(td[on:])), 'ticks': int(len(rng))}
    if role == 'control':
        res['range_change_max'] = float(np.max(rng[on:]) - np.min(rng[on:]))
        res['closing_any'] = bool(np.any(np.diff(rng[on:]) < -1e-6))
    return res


# ------------------------------------------------------------------ run ---
def run():
    check_frozen()
    session, policy, config = make_session()
    from game.session import build_policy  # noqa: F401
    brain = session.brain
    esc = (int(brain.groups['escape_L'][0]), int(brain.groups['escape_R'][0]))
    assert esc == (6, 0), esc
    captured = []
    orig = brain.step

    def step(*a, **k):                       # observation only: record which cells fired
        fired = orig(*a, **k)
        captured.append(np.asarray(fired).copy())
        return fired
    brain.step = step
    seeds = list(P.SEEDS)[: ARGS.seeds] if ARGS.seeds else list(P.SEEDS)
    mine = [s for i, s in enumerate(seeds) if i % ARGS.workers == ARGS.worker]
    t_start = time.time()
    for tid in trajectories():
        d = OUT / 'trials' / tid
        d.mkdir(parents=True, exist_ok=True)
        offs, path, marks = pointer_path(tid)
        for seed in mine:
            f = d / ('%d.npz' % seed)
            if f.exists():
                continue
            session.reset(seed)
            place(session, offs)
            policy.reset()
            captured.clear()
            w = session.world
            geo, ret, sens, drive = [], [], [], []
            for ox, oy in path:
                geo.append(geometry_row(w)[:9])
                session.tick(pointer=(P.FLY_POSE[0] + ox, P.FLY_POSE[1] + oy), strike=False)
                r = session.last_retina
                ret.append((r.theta, r.theta_dot, r.azimuth))
                s = session.fly_loop.last_sensory_spikes
                sens.append((s['LPLC2_left'], s['LC4_left'], s['LPLC2_right'], s['LC4_right']))
                dr = session.encoder.last_drive
                drive.append((dr.get('loomL', 0.0), dr.get('threatL', 0.0), dr.get('loomR', 0.0), dr.get('threatR', 0.0)))
                if (w.fly.x, w.fly.y) != P.FLY_POSE[:2] or 'approach' not in str(w.swatter.phase).lower():
                    raise RuntimeError('controlled state violated')
            assert len(captured) == len(path) == len(policy.history)
            spk = np.zeros((len(path), 4), np.uint8)
            for t, fired in enumerate(captured):
                spk[t] = [np.any(fired == esc[0]), np.any(fired == esc[1]),
                          np.any(fired == DNP04['L']), np.any(fired == DNP04['R'])]
            np.savez_compressed(f, geo=np.array(geo, np.float64), retina=np.array(ret, np.float64),
                                sensory=np.array(sens, np.int32), drive=np.array(drive, np.float64),
                                dnp01_trace=np.array([(m.dnp01_left, m.dnp01_right) for m in policy.history], np.float64),
                                spikes=spk)
        print('worker %d %s done (%.0f s)' % (ARGS.worker, tid, time.time() - t_start), flush=True)
    session.close()


# ------------------------------------------------------------------ analysis ---
def n4b1c_replayer():
    check_runtime()
    from game.action import MotorState
    from game.session import build_policy, load_config
    pol = build_policy(load_config(RUNTIME / 'game_room_config.json'), RUNTIME)[0]
    zero = np.zeros(1, np.float32)

    def events(left, right):
        pol.reset()
        out = []
        for t in range(len(left)):
            a = pol.decide(MotorState(float(left[t]), float(right[t]), 0.0, 0.0, zero))
            if a.escape:
                out.append((t, str(pol.criterion_diagnostics()['escape_trigger_paths'])))
        return out
    return events


def first_at(mask, t0):
    k = np.flatnonzero(mask[t0:])
    return None if not k.size else t0 + int(k[0])


def poisson_upper(k, minutes):
    from scipy.stats import chi2
    return float(chi2.ppf(0.95, 2 * k + 2) / 2 / minutes)


def trial_metrics(tid, z, events_fn, crit):
    spec = P.MATRIX[tid]
    on = P.PRE_HOLD_TICKS
    geo, ret, sens, drive, tr, spk = z['geo'], z['retina'], z['sensory'], z['drive'], z['dnp01_trace'], z['spikes']
    n = len(ret)
    hd, rng = geo[:, 5], geo[:, 6]
    c = closest_tick(rng, on) if spec['role'] in ('approach', 'abort') else None
    ev = events_fn(tr[:, 0], tr[:, 1])
    pre = [e for e in ev if e[0] < on]
    post = [e for e in ev if e[0] >= on]
    trig = post[0] if post else None
    side_sens = np.maximum(sens[:, 0] + sens[:, 1], sens[:, 2] + sens[:, 3])
    m = {'seed': None, 'n_ticks': n, 'closest': None if c is None else c - on,
         'retina_onset': first_at(ret[:, 1] > 1e-9, on),
         'encoder_drive_onset': first_at(drive.sum(1) > 0, on),
         'encoder_onset': first_at(side_sens > SENSORY_N0_MAX, on),
         'first_dnp01_spike': first_at(spk[:, 0] | spk[:, 1], on),
         'trigger': None if trig is None else trig[0], 'trigger_path': None if trig is None else trig[1],
         'n_triggers_after_onset': len(post), 'pre_onset_events': len(pre),
         'max_side_sensory': int(side_sens[on:].max()), 'max_side_sensory_pre': int(side_sens[:on].max())}
    for k in ('retina_onset', 'encoder_drive_onset', 'encoder_onset', 'first_dnp01_spike', 'trigger'):
        if m[k] is not None:
            m[k] -= on
    if trig is not None:
        t = trig[0]
        m['trigger_hdist'], m['trigger_range'] = float(hd[t]), float(rng[t])
        m['trigger_theta'], m['trigger_theta_dot'] = float(ret[t, 0]), float(ret[t, 1])
        if c is not None:
            m['lead_before_closest_s'] = (c - t) * DT
            m['timely'] = t <= c
    else:
        m['timely'] = False if c is not None else None
    if c is not None:
        m['encoder_evidence_present'] = m['encoder_onset'] is not None and m['encoder_onset'] + on <= c - 13
    for name, rs in DNP04_READOUTS.items():
        e4 = crit.evaluate(rs, spk[:, 2].astype(bool), spk[:, 3].astype(bool))
        p4 = [e for e in e4 if e[0] >= on]
        m[name] = None if not p4 else p4[0][0] - on
        m[name + ' pre_onset'] = sum(1 for e in e4 if e[0] < on)
        m[name + ' after_onset'] = len(p4)
        if c is not None:
            m[name + ' timely'] = bool(p4) and p4[0][0] <= c
    return m


def q(v, p):
    v = [x for x in v if x is not None]
    return None if not v else float(np.percentile(v, p))


def analyze():
    reg = check_frozen()
    crit = load_module('n4b2_criteria_frozen', CRITERIA_FILE)
    events_fn = n4b1c_replayer()
    geo = json.loads((OUT / 'geometry.json').read_text(encoding='utf-8'))
    per, table = {}, {}
    for tid, spec in P.MATRIX.items():
        rows = []
        for seed in P.SEEDS:
            f = OUT / 'trials' / tid / ('%d.npz' % seed)
            if not f.exists():
                raise SystemExit('missing trial %s' % f)
            m = trial_metrics(tid, np.load(f), events_fn, crit)
            m['seed'] = seed
            rows.append(m)
        per[tid] = rows
        table[tid] = summarize(tid, spec, rows)
    decision = decide(table)
    res = {'label': 'M1.8-N4B6 results', 'preregistration_sha256': sha256(PREREG),
           'protocol_sha256': reg['protocol_sha256'], 'runtime_commit': RUNTIME_COMMIT,
           'n_seeds': len(P.SEEDS), 'geometry': geo, 'table': table, 'decision': decision}
    (OUT / 'results.json').write_text(json.dumps(res, indent=1, default=float) + '\n', encoding='utf-8')
    (OUT / 'per_trial.json').write_text(json.dumps(per, default=float) + '\n', encoding='utf-8')
    for tid, t in table.items():
        print(tid, json.dumps({k: t[k] for k in ('class', 'p_timely', 'median_trigger_s', 'p95_trigger_s', 'median_lead_s',
                                                  'p_encoder_evidence', 'paths', 'false_rate_per_min', 'dnp04_pair_p_timely',
                                                  'dnp04_pair_median_s') if k in t}, default=float))
    print(json.dumps(decision, indent=1))


def summarize(tid, spec, rows):
    n = len(rows)
    trig = [r['trigger'] for r in rows]
    paths = {}
    for r in rows:
        if r['trigger_path']:
            paths[r['trigger_path']] = paths.get(r['trigger_path'], 0) + 1
    t = {'family': spec['family'], 'role': spec['role'], 'n': n,
         'p_any_trigger_after_onset': sum(x is not None for x in trig) / n,
         'median_trigger_s': None if q(trig, 50) is None else q(trig, 50) * DT,
         'p95_trigger_s': None if q(trig, 95) is None else q(trig, 95) * DT,
         'paths': paths,
         'median_retina_onset_s': None if q([r['retina_onset'] for r in rows], 50) is None else q([r['retina_onset'] for r in rows], 50) * DT,
         'p_encoder_onset': sum(r['encoder_onset'] is not None for r in rows) / n,
         'median_encoder_onset_s': None if q([r['encoder_onset'] for r in rows], 50) is None else q([r['encoder_onset'] for r in rows], 50) * DT,
         'p_first_dnp01_spike': sum(r['first_dnp01_spike'] is not None for r in rows) / n,
         'median_first_dnp01_spike_s': None if q([r['first_dnp01_spike'] for r in rows], 50) is None else q([r['first_dnp01_spike'] for r in rows], 50) * DT,
         'pre_onset_events': sum(r['pre_onset_events'] for r in rows),
         'max_side_sensory_median': float(np.median([r['max_side_sensory'] for r in rows])),
         'max_side_sensory_pre_max': int(max(r['max_side_sensory_pre'] for r in rows))}
    if spec['role'] in ('approach', 'abort'):
        timely = [r for r in rows if r['timely']]
        t['closest_s_median'] = float(np.median([r['closest'] for r in rows])) * DT
        t['p_timely'] = len(timely) / n
        t['miss_rate'] = 1 - t['p_timely']
        t['p_late_only'] = sum(1 for r in rows if (not r['timely']) and r['trigger'] is not None) / n
        tt = [r['trigger'] for r in timely]
        t['median_timely_trigger_s'] = None if not tt else float(np.median(tt)) * DT
        t['p95_timely_trigger_s'] = None if not tt else float(np.percentile(tt, 95)) * DT
        leads = [r['lead_before_closest_s'] for r in timely]
        t['median_lead_s'] = None if not leads else float(np.median(leads))
        t['p05_lead_s'] = None if not leads else float(np.percentile(leads, 5))
        t['median_trigger_hdist'] = q([r.get('trigger_hdist') for r in timely], 50)
        t['median_trigger_range'] = q([r.get('trigger_range') for r in timely], 50)
        t['median_trigger_theta'] = q([r.get('trigger_theta') for r in timely], 50)
        t['p_encoder_evidence'] = sum(r['encoder_evidence_present'] for r in rows) / n
        p = t['p_timely']
        t['class'] = 'reliable' if p >= 0.9 else 'marginal' if p >= 0.1 else 'undetected'
        if spec['role'] == 'abort':
            t['p_trigger_before_reversal'] = p
            t['p_trigger_after_reversal_only'] = t['p_late_only']
        for name, key in (('DNp04 pair 60 ms', 'dnp04_pair'), ('DNp04 triple 200 ms', 'dnp04_triple')):
            v = [r[name] for r in rows if r[name + ' timely']]
            t[key + '_p_timely'] = len(v) / n
            t[key + '_median_s'] = None if not v else float(np.median(v)) * DT
            both = [(r[name], r['trigger']) for r in rows if r[name + ' timely'] and r['timely']]
            t[key + '_median_advance_over_n4b1c_s'] = None if not both else float(np.median([b - a for a, b in both])) * DT
            t[key + '_pre_onset_events'] = sum(r[name + ' pre_onset'] for r in rows)
    else:
        minutes = sum((r['n_ticks'] - P.PRE_HOLD_TICKS) for r in rows) * DT / 60
        k = sum(r['n_triggers_after_onset'] for r in rows)
        t['class'] = 'control'
        t['stimulus_minutes'] = minutes
        t['false_responses'] = k
        t['trials_with_false_response'] = sum(1 for r in rows if r['trigger'] is not None)
        t['false_rate_per_min'] = k / minutes
        t['false_rate_upper95_per_min'] = poisson_upper(k, minutes)
        for name, key in (('DNp04 pair 60 ms', 'dnp04_pair'), ('DNp04 triple 200 ms', 'dnp04_triple')):
            k4 = sum(r[name + ' after_onset'] for r in rows)
            t[key + '_false_responses'] = k4
            t[key + '_false_rate_per_min'] = k4 / minutes
            t[key + '_false_rate_upper95_per_min'] = poisson_upper(k4, minutes)
    # stationary pre-hold baseline across the whole matrix is aggregated in decide()
    return t


BLIND_SPOT_CANDIDATES = ('A1_frontal_very_slow', 'A2_frontal_slow', 'C1_oblique_slow_right',
                         'C2_oblique_slow_left', 'C3_lateral_slow_close')


def decide(table):
    """Apply the preregistered decision rule (tools/n4b6_protocol.py DECISION_RULE)."""
    blind = {}
    for tid in BLIND_SPOT_CANDIDATES:
        t = table[tid]
        late = t['class'] == 'reliable' and t['median_lead_s'] is not None and t['median_lead_s'] < 0.25
        if t['class'] in ('marginal', 'undetected') or late:
            pe = t['p_encoder_evidence']
            layer = ('STIMULUS / RETINA LIMIT' if pe < 0.5 else
                     'REAL DNp01 SENSITIVITY LIMIT' if pe >= 0.9 else 'mixed')
            blind[tid] = {'class': t['class'], 'p_timely': t['p_timely'], 'median_lead_s': t['median_lead_s'],
                          'p_encoder_evidence': pe, 'attribution': layer}
    controls = {tid: {'false_responses': t['false_responses'], 'rate': t['false_rate_per_min'],
                      'upper95': t['false_rate_upper95_per_min']}
                for tid, t in table.items() if t['role'] == 'control'}
    k = sum(c['false_responses'] for c in controls.values())
    minutes = sum(table[tid]['stimulus_minutes'] for tid in controls)
    pre_k = sum(t['pre_onset_events'] for t in table.values())
    pre_min = len(table) * len(P.SEEDS) * P.PRE_HOLD_TICKS * DT / 60
    controls_ok = poisson_upper(k, minutes) < 0.1 or (k / minutes) < 0.1
    if not blind:
        outcome = '1 NO MATERIAL PROBLEM' if controls_ok else 'no blind spot; controls exceed the category-A criterion'
    else:
        layers = {b['attribution'] for b in blind.values()}
        outcome = ({'REAL DNp01 SENSITIVITY LIMIT': '2 REAL DNp01 SENSITIVITY LIMIT',
                    'STIMULUS / RETINA LIMIT': '3 STIMULUS / RETINA LIMIT'}.get(layers.pop(), 'mixed')
                   if len(layers) == 1 else 'mixed')
    return {'blind_spot_trajectories': blind, 'controls': controls,
            'controls_pooled': {'false_responses': k, 'minutes': minutes, 'rate': k / minutes,
                                'upper95': poisson_upper(k, minutes)},
            'pre_hold_baseline': {'events': pre_k, 'minutes': pre_min, 'upper95': poisson_upper(pre_k, pre_min)},
            'controls_within_category_a': controls_ok, 'outcome': outcome}


if __name__ == '__main__':
    {'freeze': freeze, 'geometry': geometry, 'run': run, 'analyze': analyze}[ARGS.mode]()
