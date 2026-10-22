"""Preregistered checks C2, C3 and C5 of M1.7.2 (game/M1_7_2_PADDLE_AXIS_DESIGN.md).

Diagnostic only; it writes under artifacts/m1_7_2/ (git-ignored). Every check runs the same
seeds and inputs under v26 (game_room_config.json at tag v1.0) and v27 (the working file) with
the same code. The invariant of section 4 is tested per tick: the first tick at which anything
recorded differs must not come before the first tick in which the v27 line axis folded its
steering error.

    python tools/m1_7_2_axis_checks.py calibration   # C2: the 56 calibration-protocol trials
    python tools/m1_7_2_axis_checks.py trace         # C2: the five ROOM trace scenarios
    python tools/m1_7_2_axis_checks.py turn          # C3 T1, world only
    python tools/m1_7_2_axis_checks.py controls      # C3 F3 and R1, 48 brain-noise seeds
    python tools/m1_7_2_axis_checks.py freeflight    # C5: seeds 9201-9210, 180 s, no player
"""
from __future__ import annotations

import argparse
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import time

os.environ.setdefault('NUMBA_NUM_THREADS', '4')
os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import numpy as np  # noqa: E402

from game.action import MotorState, NO_ACTION  # noqa: E402
from game.session import Session, build_policy, load_config  # noqa: E402
from tools.calibrate_escape import RecordingPolicy, _trial  # noqa: E402
import tools.n4b6_protocol as P  # noqa: E402

OUT = ROOT / 'artifacts/m1_7_2'
BASELINE_COMMIT = '57221665cfae656d5e3e367436ff32d2bbfc7473'   # tag v1.0
DT = 0.02
PARKED = (1920.0, 388.8)
SIZE_LIMIT = 0.1        # rad/s, C3 functional criterion for v27
SIZE_TRANSIENT = 0.2    # rad/s, C3 sanity condition for v26
ROTATION_LIMIT = 10.0   # degrees, C3 F3 hold criterion
RESPONSE_LIMIT = 2      # seeds of 48


def configs():
    v26 = json.loads(subprocess.check_output(['git', 'show', BASELINE_COMMIT + ':game_room_config.json'],
                                             cwd=ROOT, text=True))
    v27 = load_config(ROOT / 'game_room_config.json')
    assert v26['config_version'] == 26 and v27['config_version'] == 27
    return {'v26': v26, 'v27': v27}


def folded(world):
    ps = world.physical_swatter
    return bool(ps is not None and ps.line_axis_enabled and ps.line_axis_folded)


def first_difference(a, b):
    return next((t for t, (x, y) in enumerate(zip(a, b)) if x != y), None if len(a) == len(b) else min(len(a), len(b)))


def invariant(rows26, rows27, folds):
    """Rows are per-tick tuples of exact values; folds are the v27 per-tick fold flags."""
    diff = first_difference(rows26, rows27)
    fold = next((t for t, f in enumerate(folds) if f), None)
    holds = diff is None or (fold is not None and diff >= fold)
    return {'first_difference_tick': diff, 'first_fold_tick': fold, 'fold_ticks': int(sum(folds)),
            'bit_identical': diff is None, 'invariant_holds': holds}


def save(name, data):
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / name).write_text(json.dumps(data, indent=1) + '\n', encoding='utf-8')
    print('written', OUT / name)


# --------------------------------------------------------------------- C2 calibration ---
def calibration():
    """The calibration protocol's 28 no-loom and 28 loom trials, exactly as
    tools/calibrate_escape.py runs them; DNp01 traces compared between configurations."""
    traces, folds_by, brain = {}, {}, None
    for arm, config in configs().items():
        policy = RecordingPolicy()
        session = Session(config, policy=policy, root=ROOT, brain=brain)
        brain = session.brain
        session.world.collisions_enabled = False
        session.world.fly_motion_enabled = False
        folds = []
        tick = session.tick

        def counted(*a, **k):
            out = tick(*a, **k)
            folds.append(folded(session.world))
            return out
        session.tick = counted
        rng = np.random.default_rng(int(config['encoder']['encoder_seed']))
        rows, fold_rows = [], []
        for i in range(28):
            angle, radius = float(rng.uniform(0, 2*np.pi)), float(rng.uniform(30.0, 170.0))
            plan = [(4000 + i, (np.cos(angle)*radius, np.sin(angle)*radius), None)]
            side = -1.0 if i % 2 == 0 else 1.0
            plan.append((5000 + i, (side*float(rng.uniform(5.0, 55.0)), float(rng.uniform(-40.0, 40.0))), 20))
            for seed, offset, click in plan:
                folds.clear()
                t = _trial(session, policy, seed, offset, 90, click)
                rows.append([tuple(float(v).hex() for v in t[k]) for k in ('total', 'left', 'right')])
                fold_rows.append(int(sum(folds)))
        traces[arm], folds_by[arm] = rows, fold_rows
        session.close()
        print(arm, 'done', flush=True)
    identical = [a == b for a, b in zip(traces['v26'], traces['v27'])]
    data = {'check': 'C2 calibration trials', 'trials': len(identical),
            'bit_identical_trials': int(sum(identical)), 'folded_ticks': int(sum(folds_by['v27'])),
            'folded_trials': int(sum(1 for f in folds_by['v27'] if f)),
            'v26_folds_must_be_zero': int(sum(folds_by['v26'])),
            'invariant_holds': all(same or f for same, f in zip(identical, folds_by['v27']))}
    save('c2-calibration-trials.json', data)
    print(json.dumps(data))


# -------------------------------------------------------------------------- C2 trace ---
TRACE_PLAN = [('room_quiet', 255, 1200, None, None), ('room_perched_threat', 255, 340, 240, None),
              ('room_approach_threat', 255, 120, 10, None), ('room_airborne_seed101', 101, 900, None, None),
              ('room_no_ecology', 255, 600, None, False)]


def trace():
    results, brain = [], None
    for name, seed, ticks, chase, ecology in TRACE_PLAN:
        rows, folds = {}, []
        for arm, config in configs().items():
            session = Session(config, brain=brain, seed=seed, mode='evaluation', ecology_enabled=ecology)
            brain, w, out = session.brain, session.world, []
            for t in range(ticks):
                fly = w.fly
                session.tick(pointer=(fly.x, fly.y) if chase is not None and t >= chase else PARKED)
                motor = session.fly_loop.last_motor
                out.append(tuple(float(v).hex() for v in (fly.x, fly.y, fly.vx, fly.vy, fly.heading,
                                                          0.0 if motor is None else motor.dnp01_total,
                                                          w.visual_half_size, w.swatter.x, w.swatter.y)))
                if arm == 'v27':
                    folds.append(folded(w))
            rows[arm] = out
            session.close()
        result = {'scenario': name, 'seed': seed, 'ticks': ticks, **invariant(rows['v26'], rows['v27'], folds)}
        results.append(result)
        print(json.dumps(result), flush=True)
    save('c2-trace.json', {'check': 'C2 trace scenarios', 'scenarios': results,
                           'invariant_holds': all(r['invariant_holds'] for r in results)})


# ------------------------------------------------------------------------------ C3 ---
def place(session, offsets, orientation):
    """As N4B6: the fly is held at FLY_POSE and the paddle rests at the start point, facing its
    first movement, for a world-only settle."""
    w = session.world
    fx, fy, fh = P.FLY_POSE
    w.fly.x, w.fly.y, w.fly.heading, w.fly.vx, w.fly.vy = fx, fy, fh, 0.0, 0.0
    sw = w.swatter
    x0, y0 = fx + offsets[0][0], fy + offsets[0][1]
    sw.x, sw.y, sw.vx, sw.vy = x0, y0, 0.0, 0.0
    w.set_pointer(x0, y0)
    sw.orientation = sw.attack_orientation = orientation
    sw.angular_velocity = 0.0
    for _ in range(P.PLACEMENT_SETTLE_TICKS):
        w.set_pointer(x0, y0)
        w.tick(DT, NO_ACTION)
    if math.hypot(sw.vx, sw.vy) > 1e-6 or abs(sw.orientation - orientation) > 1e-9:
        raise RuntimeError('paddle did not rest at the start point with the intended pose')
    session.projector.reset()


def arc(seconds_and_signs, radius, speed, az0_deg=10.0):
    """Offsets on a circle around the fly; each leg runs `seconds` in direction `sign`."""
    offs, az = [], az0_deg
    w = math.degrees(speed / radius * DT)
    for sign, seconds in seconds_and_signs:
        for _ in range(int(round(seconds / DT))):
            offs.append(P._polar(az, radius))
            az += sign * w
    return offs


def control_paths():
    f3 = P.script(P.MATRIX['F3_orbit_constant_range']['geometry'])[0]
    r1 = arc([(1, 1.0), (-1, 1.0)], 300.0, 300.0)
    paths = {}
    for name, offs, reversal in (('F3', f3, None), ('R1', r1, P.PRE_HOLD_TICKS + 50)):
        path = [offs[0]] * P.PRE_HOLD_TICKS + list(offs) + [offs[-1]] * P.POST_HOLD_TICKS
        motion_end = P.PRE_HOLD_TICKS + len(offs)
        paths[name] = {'offsets': offs, 'path': path, 'onset': P.PRE_HOLD_TICKS, 'motion_end': motion_end,
                       'window_start': reversal if reversal is not None else motion_end,
                       'orientation': P.initial_orientation(offs)}
    return paths


def geometry_rows(session, spec):
    """Run one control path; per tick: tracker, paddle axis, half size, 3-D range, heading of
    the paddle velocity, fold flag, DNp01 left and right."""
    w, rows = session.world, []
    for ox, oy in spec['path']:
        session.tick(pointer=(P.FLY_POSE[0] + ox, P.FLY_POSE[1] + oy), strike=False)
        sw = w.swatter
        rng3 = math.sqrt((w.fly.x - sw.x)**2 + (w.fly.y - sw.y)**2 + sw.height**2)
        motor = session.fly_loop.last_motor
        rows.append((sw.orientation, w.paddle_axis, w.visual_half_size, rng3, math.atan2(sw.vy, sw.vx),
                     math.hypot(sw.vx, sw.vy), folded(w), motor.dnp01_left, motor.dnp01_right))
        if (w.fly.x, w.fly.y) != P.FLY_POSE[:2]:
            raise RuntimeError('the fly moved')
    return rows


def size_rate(rows, t):
    """Apparent-size-driven expansion between ticks t-1 and t, at the range of tick t."""
    h0, h1, r1 = rows[t - 1][2], rows[t][2], rows[t][3]
    return (2*math.atan(h1/r1) - 2*math.atan(h0/r1)) / DT


def line_deviation(axis, heading):
    d = (axis - heading) % math.pi
    return math.degrees(min(d, math.pi - d))


def control_metrics(rows, spec, axis_index):
    start = spec['window_start']
    turned = [r[axis_index] for r in rows[start:]]
    moving = [line_deviation(r[axis_index], r[4]) for r in rows[start:spec['motion_end']] if r[5] > 20]
    return {'peak_size_rate_after': max(size_rate(rows, t) for t in range(start, len(rows))),
            'peak_size_rate_motion': max(size_rate(rows, t) for t in range(spec['onset'] + 1, start)),
            'axis_rotation_after_degrees': math.degrees(max(turned) - min(turned)),
            'axis_rotation_hold_degrees': math.degrees(max(r[axis_index] for r in rows[spec['motion_end']:])
                                                       - min(r[axis_index] for r in rows[spec['motion_end']:])),
            'peak_line_deviation_moving_degrees': max(moving) if moving else None,
            'fold_ticks': int(sum(r[6] for r in rows))}


def controls():
    paths = control_paths()
    seeds = list(P.SEEDS)
    result, brain = {}, None
    for arm, config in configs().items():
        policy = RecordingPolicy()
        session = Session(config, policy=policy, root=ROOT, ecology_enabled=False, brain=brain)
        brain = session.brain
        session.world.collisions_enabled = False
        session.world.fly_motion_enabled = False
        decoder = build_policy(config, ROOT)[0]
        zero = np.zeros(1, np.float32)
        arm_out = {}
        for name, spec in paths.items():
            responses, geometry, started = [], None, time.time()
            for seed in seeds:
                session.reset(seed)
                place(session, spec['offsets'], spec['orientation'])
                policy.reset()
                rows = geometry_rows(session, spec)
                if geometry is None:
                    geometry = control_metrics(rows, spec, 0 if arm == 'v26' else 1)
                    geometry['tracker'] = control_metrics(rows, spec, 0)
                decoder.reset()
                fired = []
                for t, r in enumerate(rows):
                    if decoder.decide(MotorState(float(r[7]), float(r[8]), 0.0, 0.0, zero)).escape:
                        fired.append(t)
                responses.append({'seed': seed, 'escape_ticks': fired})
            during = sum(1 for r in responses if any(spec['onset'] <= t < spec['window_start'] for t in r['escape_ticks']))
            after = sum(1 for r in responses if any(t >= spec['window_start'] for t in r['escape_ticks']))
            pre = sum(1 for r in responses if any(t < spec['onset'] for t in r['escape_ticks']))
            arm_out[name] = {'geometry': geometry, 'seeds': len(seeds), 'responding_seeds_pre_hold': pre,
                             'responding_seeds_before_window': during, 'responding_seeds_after_window_start': after,
                             'responses': responses}
            print(arm, name, json.dumps({k: v for k, v in arm_out[name].items() if k != 'responses'}),
                  '(%.0f s)' % (time.time() - started), flush=True)
        result[arm] = arm_out
        session.close()
    verdict = {}
    for name in paths:
        g26, g27 = result['v26'][name]['geometry'], result['v27'][name]['geometry']
        verdict[name] = {
            'v26_reproduces_the_transient': g26['peak_size_rate_after'] >= SIZE_TRANSIENT,
            'v27_size_rate_after_within_limit': g27['peak_size_rate_after'] <= SIZE_LIMIT,
            'v27_responses_within_limit': result['v27'][name]['responding_seeds_after_window_start'] <= RESPONSE_LIMIT}
        if name == 'F3':
            verdict[name]['v27_hold_rotation_within_limit'] = g27['axis_rotation_hold_degrees'] <= ROTATION_LIMIT
        else:
            verdict[name]['v26_tracker_spins'] = g26['tracker']['axis_rotation_after_degrees'] >= 120.0
            verdict[name]['v27_rotation_after_within_10_degrees_as_written'] = g27['axis_rotation_after_degrees'] <= ROTATION_LIMIT
    save('c3-controls.json', {'check': 'C3 F3 and R1', 'verdict': verdict, 'result': result})
    print(json.dumps(verdict, indent=1))


def turn():
    """T1: a straight run at 300 units/s that turns by 60 degrees, with no stop, world only."""
    pts, x, y, h = [(0.0, -400.0)], 0.0, -400.0, 0.0
    for leg in range(2):
        for _ in range(50):
            x += 300.0*DT*math.cos(h)
            y += 300.0*DT*math.sin(h)
            pts.append((x, y))
        h += math.radians(60.0)
    rows, folds = {}, []
    for arm, config in configs().items():
        session = Session(config, policy=RecordingPolicy(), root=ROOT, ecology_enabled=False)
        session.world.collisions_enabled = False
        session.world.fly_motion_enabled = False
        session.reset(P.SEEDS[0])
        place(session, pts, 0.0)
        w, out = session.world, []
        for ox, oy in pts[1:]:
            w.set_pointer(P.FLY_POSE[0] + ox, P.FLY_POSE[1] + oy)
            w.tick(DT, NO_ACTION)
            out.append(tuple(float(v).hex() for v in (w.paddle_axis, w.visual_half_size, w.swatter.x, w.swatter.y)))
            if arm == 'v27':
                folds.append(folded(w))
        rows[arm] = out
        session.close()
    data = {'check': 'C3 T1 turn', 'ticks': len(pts) - 1, **invariant(rows['v26'], rows['v27'], folds)}
    data['pass'] = data['bit_identical'] and data['fold_ticks'] == 0
    save('c3-turn.json', data)
    print(json.dumps(data))


# ------------------------------------------------------------------------------ C5 ---
def freeflight():
    results, brain = [], None
    for seed in range(9201, 9211):
        rows, folds, onsets = {}, [], {}
        for arm, config in configs().items():
            policy = build_policy(config, ROOT)[0]
            session = Session(config, brain=brain, policy=policy, seed=seed, mode='evaluation')
            brain, w, out, esc = session.brain, session.world, [], []
            for t in range(9000):
                session.tick(pointer=PARKED)
                motor = session.fly_loop.last_motor
                out.append(tuple(float(v).hex() for v in (w.fly.x, w.fly.y, w.fly.vx, w.fly.vy,
                                                          0.0 if motor is None else motor.dnp01_total,
                                                          w.visual_half_size)))
                if session.fly_loop.last_action.escape:
                    esc.append(t)
                if arm == 'v27':
                    folds.append(folded(w))
            rows[arm], onsets[arm] = out, esc
            session.close()
        result = {'seed': seed, **invariant(rows['v26'], rows['v27'], folds),
                  'escape_ticks_v26': onsets['v26'], 'escape_ticks_v27': onsets['v27']}
        results.append(result)
        print(json.dumps({k: v for k, v in result.items() if not k.startswith('escape_ticks')}),
              'escapes', len(onsets['v26']), len(onsets['v27']), flush=True)
    save('c5-freeflight.json', {'check': 'C5 free flight', 'seeds': results,
                                'invariant_holds': all(r['invariant_holds'] for r in results)})


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('check', choices=('calibration', 'trace', 'turn', 'controls', 'freeflight'))
    {'calibration': calibration, 'trace': trace, 'turn': turn, 'controls': controls,
     'freeflight': freeflight}[parser.parse_args().check]()


if __name__ == '__main__':
    main()
