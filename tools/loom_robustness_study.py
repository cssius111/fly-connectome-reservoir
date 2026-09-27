"""M1.8-N1: loom robustness / stimulus generalisation study.

Research only. No runtime code, configuration, threshold, brain parameter or calibration
file is changed, and output goes only to artifacts/m1_8_loom_robustness/.

Every stimulus is delivered through the real chain -- scripted pointer trajectory ->
physical swatter -> Retina -> encoder -> MaleCNS -> DNp01 -- on the accepted fixed-fly-v2
measurement conditions (escape disabled, fly motion disabled, collisions disabled). No
direct LC4/LPLC2 injection is used anywhere in this tool.

Stimulus class names are engineering test categories, not biological categories.

    python tools/loom_robustness_study.py --per-class 40
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault('NUMBA_NUM_THREADS', '4')
os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')

import numpy as np  # noqa: E402

from game.session import Session, calibration_provenance, load_config  # noqa: E402
from game.world import StrikePhase  # noqa: E402
from tools.calibrate_escape import RecordingPolicy  # noqa: E402

OUT = ROOT / 'artifacts/m1_8_loom_robustness'
DT = 0.02
COMMITTED = (StrikePhase.WINDUP, StrikePhase.ACTIVE, StrikePhase.COMMIT,
             StrikePhase.FAST_SWING, StrikePhase.ACTIVE_CONTACT)


def make_script(kind, rng):
    """Return (initial_pointer_fn, script_fn, ticks, click_tick, description).

    All geometry is relative to the fixed fly. Pointer motion drives the physical
    swatter's own controller; nothing bypasses it.
    """
    angle = float(rng.uniform(0, 2 * math.pi))
    ca, sa = math.cos(angle), math.sin(angle)

    if kind == 'strong_direct':
        # Accepted reference geometry and timing, unchanged.
        side = -1.0 if rng.random() < 0.5 else 1.0
        dx = side * float(rng.uniform(5.0, 55.0))
        dy = float(rng.uniform(-40.0, 40.0))
        return (lambda f: (f.x + dx, f.y + dy),
                lambda t, f: ((f.x + dx, f.y + dy), t == 20), 90, 20,
                'committed strike from %.0f units' % math.hypot(dx, dy))

    if kind == 'medium_committed':
        r = float(rng.uniform(150.0, 260.0))
        dx, dy = ca * r, sa * r
        return (lambda f: (f.x + dx, f.y + dy),
                lambda t, f: ((f.x + dx, f.y + dy), t == 20), 90, 20,
                'committed strike from %.0f units' % r)

    if kind == 'weak_approach':
        # Slow radial approach at hover height, never committed.
        r0 = float(rng.uniform(600.0, 800.0))
        r1 = float(rng.uniform(150.0, 260.0))
        speed = float(rng.uniform(220.0, 420.0))          # pointer units/s
        ticks = 150
        def script(t, f, r0=r0, r1=r1, speed=speed, ca=ca, sa=sa):
            r = max(r1, r0 - speed * t * DT)
            return ((f.x + ca * r, f.y + sa * r), False)
        return (lambda f, r0=r0, ca=ca, sa=sa: (f.x + ca * r0, f.y + sa * r0),
                script, ticks, None,
                'radial approach %.0f->%.0f at %.0f u/s, no strike' % (r0, r1, speed))

    if kind == 'glancing_pass':
        # Fast lateral sweep passing the fly at a miss distance, never committed.
        miss = float(rng.uniform(250.0, 450.0))
        span = 900.0
        speed = float(rng.uniform(900.0, 1500.0))
        ticks = 150
        px, py = -sa, ca                                   # travel direction
        def script(t, f, miss=miss, span=span, speed=speed, ca=ca, sa=sa, px=px, py=py):
            s = -span + speed * t * DT
            s = min(s, span)
            return ((f.x + ca * miss + px * s, f.y + sa * miss + py * s), False)
        return (lambda f, miss=miss, span=span, ca=ca, sa=sa, px=px, py=py:
                (f.x + ca * miss - px * span, f.y + sa * miss - py * span),
                script, ticks, None,
                'glancing pass, miss %.0f at %.0f u/s' % (miss, speed))

    if kind == 'aborted_approach':
        # Approach then reverse before arriving; never committed.
        r0 = float(rng.uniform(600.0, 800.0))
        r_min = float(rng.uniform(300.0, 420.0))
        speed = float(rng.uniform(400.0, 700.0))
        ticks = 150
        turn = (r0 - r_min) / speed
        def script(t, f, r0=r0, r_min=r_min, speed=speed, turn=turn, ca=ca, sa=sa):
            s = t * DT
            r = r0 - speed * s if s <= turn else r_min + speed * (s - turn)
            r = min(max(r, r_min), r0)
            return ((f.x + ca * r, f.y + sa * r), False)
        return (lambda f, r0=r0, ca=ca, sa=sa: (f.x + ca * r0, f.y + sa * r0),
                script, ticks, None,
                'aborted approach %.0f->%.0f->out at %.0f u/s' % (r0, r_min, speed))

    raise ValueError('unknown stimulus class: ' + kind)


def run_trial(session, policy, seed, kind, rng, settle_ticks):
    initial, script, ticks, click_tick, description = make_script(kind, rng)
    session.reset(seed)
    policy.reset()
    fly = session.world.fly
    p0 = initial(fly)
    for _ in range(settle_ticks):
        session.tick(pointer=p0, strike=False)
    sw = session.world.swatter
    settled = math.hypot(sw.vx, sw.vy) < 0.1
    base = len(policy.history)
    theta, theta_dot, azimuth, dist, phases = [], [], [], [], []
    loom_l, loom_r, threat_l, threat_r = [], [], [], []
    for t in range(ticks):
        pointer, strike = script(t, fly)
        session.tick(pointer=pointer, strike=strike)
        r = session.last_retina
        d = session.encoder.last_drive or {}
        sw = session.world.swatter
        theta.append(0.0 if r is None else r.theta)
        theta_dot.append(0.0 if r is None else r.theta_dot)
        azimuth.append(0.0 if r is None else r.azimuth)
        dist.append(math.hypot(sw.x - fly.x, sw.y - fly.y))
        phases.append(sw.phase in COMMITTED)
        loom_l.append(d.get('loomL', 0.0)); loom_r.append(d.get('loomR', 0.0))
        threat_l.append(d.get('threatL', 0.0)); threat_r.append(d.get('threatR', 0.0))
    dnp01 = np.array([m.dnp01_total for m in policy.history[base:]], dtype=np.float64)
    return {'kind': kind, 'seed': seed, 'description': description, 'ticks': ticks,
            'click_tick': click_tick, 'paddle_settled_before_stimulus': settled,
            'theta': np.array(theta), 'theta_dot': np.array(theta_dot),
            'azimuth': np.array(azimuth), 'distance': np.array(dist),
            'committed': np.array(phases), 'dnp01': dnp01,
            'loomL': np.array(loom_l), 'loomR': np.array(loom_r),
            'threatL': np.array(threat_l), 'threatR': np.array(threat_r)}


def response_window(trial):
    """Ticks in which a firing counts as a detection.

    Committed strikes use the accepted strike-phase mask, unchanged. Non-committed
    approaches use onset of positive retinal expansion through closest approach, an
    explicit engineering definition: reacting after closest approach is too late.
    """
    if trial['committed'].any():
        return trial['committed'].copy(), 'accepted committed strike-phase mask'
    expanding = trial['theta_dot'] > 1e-9
    mask = np.zeros(trial['ticks'], dtype=bool)
    if not expanding.any():
        return mask, 'no positive expansion; no response window'
    start = int(np.flatnonzero(expanding)[0])
    end = int(np.argmin(trial['distance']))
    if end < start:
        end = trial['ticks'] - 1
    mask[start:end + 1] = True
    return mask, 'expansion onset to closest approach'


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--config', type=Path, default=ROOT / 'game_room_config.json')
    p.add_argument('--per-class', type=int, default=40)
    p.add_argument('--out', type=Path, default=OUT / 'trials.npz')
    args = p.parse_args()

    config = load_config(args.config)
    settle = max(40, round(config['swatter'].get('physical', {})
                           .get('calibration_settle_seconds', 0.8) / DT))
    policy = RecordingPolicy()
    session = Session(config, policy=policy, root=ROOT)
    session.world.collisions_enabled = False
    session.world.fly_motion_enabled = False
    rng = np.random.default_rng(int(config['encoder']['encoder_seed']) + 991)

    classes = ('strong_direct', 'medium_committed', 'weak_approach',
               'glancing_pass', 'aborted_approach')
    trials, started = [], time.perf_counter()
    for ci, kind in enumerate(classes):
        for i in range(args.per_class):
            trials.append(run_trial(session, policy, 6000 + ci * 1000 + i, kind, rng, settle))
        peaks = [t['dnp01'].max() for t in trials[-args.per_class:]]
        exp = [float(t['theta_dot'].max()) for t in trials[-args.per_class:]]
        print('  %-18s n=%d  peak DNp01 min %.3f med %.3f max %.3f | peak theta_dot med %.4f'
              '  %.0fs' % (kind, args.per_class, min(peaks), float(np.median(peaks)),
                           max(peaks), float(np.median(exp)), time.perf_counter() - started),
              flush=True)
    session.close()

    OUT.mkdir(parents=True, exist_ok=True)
    arrays, meta = {}, []
    for i, t in enumerate(trials):
        for key in ('theta', 'theta_dot', 'azimuth', 'distance', 'committed', 'dnp01',
                    'loomL', 'loomR', 'threatL', 'threatR'):
            arrays['%d_%s' % (i, key)] = t[key]
        mask, rule = response_window(t)
        arrays['%d_window' % i] = mask
        meta.append({'index': i, 'kind': t['kind'], 'seed': t['seed'],
                     'description': t['description'], 'ticks': t['ticks'],
                     'click_tick': t['click_tick'],
                     'paddle_settled_before_stimulus': t['paddle_settled_before_stimulus'],
                     'window_rule': rule, 'window_ticks': int(mask.sum()),
                     'window_start': int(np.flatnonzero(mask)[0]) if mask.any() else None,
                     'window_end': int(np.flatnonzero(mask)[-1]) if mask.any() else None})
    np.savez_compressed(args.out, **arrays)
    (OUT / 'trials_meta.json').write_text(json.dumps({
        'label': 'physical-retinal stimulus matrix; no direct encoder injection; nothing changed',
        'protocol': 'fixed-fly-v2, accepted measurement conditions',
        'config_sha256': hashlib.sha256(args.config.read_bytes()).hexdigest(),
        'provenance': calibration_provenance(config),
        'settle_ticks': settle, 'classes': list(classes), 'per_class': args.per_class,
        'class_note': 'engineering test categories, not biological categories',
        'trials': meta}, indent=1) + '\n', encoding='utf-8')
    print('written', args.out, 'and', OUT / 'trials_meta.json')


if __name__ == '__main__':
    main()
