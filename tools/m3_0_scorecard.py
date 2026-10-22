"""M3.0 fidelity scorecard: protocols E and S of game/M3_0_FIDELITY_SCORECARD_DESIGN.md.

Measurement only. No runtime file changes. Outputs go to artifacts/m3_0/ (git-ignored), one
file per condition or seed, so an interrupted run resumes where it stopped.

Protocol E feeds a synthetic Retina, a constant-l/v looming disk, to a fixed fly. The
projector's output is replaced once per tick; the encoder, MaleCNS, DNp01 and the runtime
decoder run unchanged.

    python tools/m3_0_scorecard.py escape      # protocol E
    python tools/m3_0_scorecard.py saccades    # protocol S
    python tools/m3_0_scorecard.py report      # metrics, bands and classes
"""
from __future__ import annotations

import argparse
import json
import math
import os
from pathlib import Path
import sys

os.environ.setdefault('NUMBA_NUM_THREADS', '4')
os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import numpy as np  # noqa: E402

from game.perception import Retina  # noqa: E402
from game.session import Session, load_config  # noqa: E402
import tools.n4b6_protocol as P  # noqa: E402

OUT = ROOT / 'artifacts/m3_0'
LV_MS = (10, 20, 40, 80)
AZIMUTHS = {'front': 0.0, 'right': 0.5, 'rear': 1.0, 'left': -0.5}
LATERAL = ('right', 'left')
THETA0 = math.radians(10.0)
PRE_S, WINDOW_AFTER_S, TAIL_S = 1.0, 0.2, 0.5
SACCADE_SEEDS = range(9501, 9521)
SACCADE_TICKS = 9000
PARKED = (1920.0, 388.8)
SACCADE_THRESHOLD = math.radians(450.0)      # rad/s, the E11 detector
POST_ESCAPE_S = 0.5


def config():
    c = load_config(ROOT / 'game_room_config.json')
    assert c['config_version'] == 27
    return c


# ---------------------------------------------------------------------------- protocol E ---
def stimulus(lv, azimuth, dt):
    """Per-tick synthetic Retinas, the onset index and the expansion time to collision."""
    t0 = lv / math.tan(THETA0 / 2)
    pre, tail = int(round(PRE_S / dt)), int(round(TAIL_S / dt))
    n = int(math.ceil((t0 + WINDOW_AFTER_S) / dt))
    thetas = [THETA0] * pre
    for k in range(1, n + 1):
        remaining = t0 - k * dt
        thetas.append(math.pi if remaining <= 0 else 2 * math.atan(lv / remaining))
    thetas += [math.pi] * tail
    retinas, previous = [], thetas[0]
    for theta in thetas:
        retinas.append(Retina(theta=theta, theta_dot=(theta - previous) / dt, azimuth=azimuth))
        previous = theta
    return retinas, pre, t0, thetas


def escape():
    cfg = config()
    dt = float(cfg['sim']['tick_seconds'])
    session = Session(cfg, root=ROOT, ecology_enabled=False)
    session.world.collisions_enabled = False
    session.world.fly_motion_enabled = False
    (OUT / 'escape').mkdir(parents=True, exist_ok=True)
    for lv_ms in LV_MS:
        lv = lv_ms / 1000.0
        for name, azimuth in AZIMUTHS.items():
            path = OUT / 'escape' / ('lv%03d_%s.json' % (lv_ms, name))
            if path.exists():
                continue
            retinas, pre, t0, thetas = stimulus(lv, azimuth, dt)
            last = pre + int(math.floor((t0 + WINDOW_AFTER_S) / dt + 1e-9)) - 1
            trials = []
            for seed in P.SEEDS:
                session.reset(seed)
                fly = session.world.fly
                fly.vx = fly.vy = 0.0                    # fixed-fly-v2: the velocity stays zero
                pose = (fly.x, fly.y, fly.heading)
                feed = iter(retinas)
                session.projector.project = lambda world, feed=feed: next(feed)
                escapes = []
                for i in range(len(retinas)):
                    session.tick()
                    a = session.fly_loop.last_action
                    if a.escape:
                        escapes.append((i, float(a.forward), float(a.lateral)))
                    if (fly.x, fly.y, fly.heading) != pose:
                        raise RuntimeError('the fly moved')
                first = next((e for e in escapes if pre <= e[0] <= last), None)
                trial = {'seed': seed, 'pre_stimulus_escapes': sum(1 for e in escapes if e[0] < pre),
                         'escaped': first is not None}
                if first is not None:
                    i, forward, lateral = first
                    trial.update({'tick': i, 't_before': t0 - (i - pre + 1) * dt,
                                  'theta_deg': math.degrees(thetas[i]),
                                  'direction_deg': math.degrees(math.atan2(lateral, forward))})
                trials.append(trial)
            del session.projector.project          # restore the class method
            path.write_text(json.dumps({'lv_ms': lv_ms, 'azimuth': name, 'azimuth_value': azimuth,
                                        't0': t0, 'onset_index': pre, 'last_window_index': last,
                                        'trials': trials}, indent=1) + '\n', encoding='utf-8')
            print('lv %d ms %s: %d of %d escaped' % (lv_ms, name, sum(t['escaped'] for t in trials), len(trials)),
                  flush=True)
    session.close()


# ---------------------------------------------------------------------------- protocol S ---
def saccades():
    cfg = config()
    (OUT / 'saccades').mkdir(parents=True, exist_ok=True)
    brain = None
    for seed in SACCADE_SEEDS:
        path = OUT / 'saccades' / ('seed%d.npz' % seed)
        if path.exists():
            continue
        session = Session(cfg, brain=brain, root=ROOT, seed=seed, mode='evaluation')
        brain, w = session.brain, session.world
        bl = w.body_length
        rows = np.zeros((SACCADE_TICKS, 5), np.float64)
        kinds = []
        for t in range(SACCADE_TICKS):
            session.tick(pointer=PARKED)
            airborne = w.fly.alive and not (w.lifecycle_active and w.lifecycle.stationary)
            rows[t] = (airborne, math.hypot(w.fly.vx, w.fly.vy) / bl, w.yaw_rate,
                       session.fly_loop.last_action.escape, w.fly.alive)
            kinds.append(w.saccades.kind)
        session.close()
        np.savez_compressed(path, rows=rows, kinds=np.array(kinds), dt=cfg['sim']['tick_seconds'])
        print('seed %d done' % seed, flush=True)


# -------------------------------------------------------------------------------- report ---
def classify(value, match, partial):
    if value is None:
        return 'not estimable'
    if match[0] <= value <= match[1]:
        return 'match'
    if partial[0] <= value <= partial[1]:
        return 'partial'
    return 'gap'


def circular_mean_deg(values):
    if not values:
        return None
    a = np.radians(values)
    return float(np.degrees(np.arctan2(np.sin(a).mean(), np.cos(a).mean())))


def angle_diff(a, b):
    return abs((a - b + 180.0) % 360.0 - 180.0)


def escape_report():
    data = {(d['lv_ms'], d['azimuth']): d for d in
            (json.loads(p.read_text(encoding='utf-8')) for p in sorted((OUT / 'escape').glob('*.json')))}
    out = {'per_condition': {}}
    for (lv, name), d in sorted(data.items()):
        esc = [t for t in d['trials'] if t['escaped']]
        out['per_condition']['%d %s' % (lv, name)] = {
            'escaped': len(esc), 'trials': len(d['trials']),
            'pre_stimulus_escapes': sum(t['pre_stimulus_escapes'] for t in d['trials']),
            'theta_at_escape_mean_deg': float(np.mean([t['theta_deg'] for t in esc])) if esc else None,
            'before_collision': sum(1 for t in esc if t['t_before'] > 0),
            'direction_circular_mean_deg': circular_mean_deg([t['direction_deg'] for t in esc])}
    lateral = [t for (lv, name), d in data.items() if name in LATERAL for t in d['trials']]
    p = sum(t['escaped'] for t in lateral) / len(lateral)
    out['E1'] = {'value': p, 'comparator': 0.82, 'class': classify(p, (0.72, 0.92), (0.57, 1.0)),
                 'per_lv': {lv: sum(t['escaped'] for name in LATERAL for t in data[(lv, name)]['trials'])
                            / sum(len(data[(lv, name)]['trials']) for name in LATERAL) for lv in LV_MS}}
    points = [(lv / 1000.0, t['t_before']) for (lv, name), d in data.items() if name in LATERAL
              for t in d['trials'] if t['escaped']]
    enough = sum(1 for lv in LV_MS if sum(1 for name in LATERAL for t in data[(lv, name)]['trials']
                                         if t['escaped']) >= 10) >= 3
    if enough:
        x, y = np.array(points).T
        alpha, delta = np.polyfit(x, y, 1)
        theta_th = math.degrees(2 * math.atan(1 / alpha)) if alpha > 0 else None
    else:
        alpha = delta = theta_th = None
    out['E2'] = {'alpha': None if alpha is None else float(alpha), 'delta_ms': None if delta is None else float(delta) * 1000,
                 'theta_threshold_deg': theta_th, 'comparator': {'alpha': 2.0, 'delta_ms': -6.0, 'theta_deg': 54.0},
                 'class': classify(theta_th, (44.0, 64.0), (34.0, 74.0)), 'escapes_fitted': len(points)}
    e10 = [t for name in LATERAL for t in data[(10, name)]['trials'] if t['escaped']]
    out['E3'] = {'before_collision_fraction_lv10': (sum(1 for t in e10 if t['t_before'] > 0) / len(e10)) if e10 else None}
    targets = {'front': 180.0, 'rear': 0.0, 'right': -45.0, 'left': 45.0}
    e4 = {}
    for name, target in targets.items():
        dirs = [t['direction_deg'] for lv in LV_MS for t in data[(lv, name)]['trials'] if t['escaped']]
        mean = circular_mean_deg(dirs)
        e4[name] = {'circular_mean_deg': mean, 'target_deg': target, 'n': len(dirs),
                    'class': 'not estimable' if mean is None else ('match' if angle_diff(mean, target) <= 45 else 'gap')}
    out['E4'] = e4
    same = {}
    for lv in LV_MS:
        rows = {name: [(t['escaped'], t.get('tick'), t.get('direction_deg')) for t in data[(lv, name)]['trials']]
                for name in ('front', 'right', 'rear')}
        same[lv] = rows['front'] == rows['right'] == rows['rear']
    out['identical_front_right_rear'] = same
    out['E5'] = {'class': 'not represented', 'note': 'single escape action without a wing-raise phase'}
    out['E6'] = {'pre_stimulus_escapes': sum(t['pre_stimulus_escapes'] for d in data.values() for t in d['trials']),
                 'trials': sum(len(d['trials']) for d in data.values())}
    return out


def saccade_report():
    events, airborne_s, isis, speeds, excluded = [], 0.0, [], [], 0
    for path in sorted((OUT / 'saccades').glob('seed*.npz')):
        z = np.load(path)
        rows, kinds, dt = z['rows'], z['kinds'], float(z['dt'])
        airborne, speed, yaw, esc = rows[:, 0] > 0, rows[:, 1], rows[:, 2], rows[:, 3] > 0
        post = np.zeros(len(rows), bool)
        for i in np.flatnonzero(esc):
            post[i:i + int(round(POST_ESCAPE_S / dt)) + 1] = True
        usable = airborne & ~post
        airborne_s += float(usable.sum()) * dt
        speeds.extend(speed[airborne].tolist())
        onsets, t, n = [], 0, len(rows)
        while t < n:
            if airborne[t] and abs(yaw[t]) >= SACCADE_THRESHOLD:
                start, sign = t, np.sign(yaw[t])
                while t + 1 < n and airborne[t + 1] and abs(yaw[t + 1]) >= SACCADE_THRESHOLD and np.sign(yaw[t + 1]) == sign:
                    t += 1
                threat = any(k in ('ESCAPE', 'ALERT') for k in kinds[start:t + 1]) or post[start]
                if threat:
                    excluded += 1
                else:
                    events.append({'amplitude_deg': abs(math.degrees(float(yaw[start:t + 1].sum()) * dt)),
                                   'duration_s': (t - start + 1) * dt})
                    onsets.append(start)
            t += 1
        for a, b in zip(onsets, onsets[1:]):
            if usable[a:b + 1].all():
                isis.append((b - a) * dt)
    rate = len(events) / airborne_s if airborne_s else None
    isi_mean = float(np.mean(isis)) if isis else None
    amp = float(np.median([e['amplitude_deg'] for e in events])) if events else None
    dur = float(np.median([e['duration_s'] for e in events])) if events else None
    s3 = sum([amp is not None and 60.0 <= amp <= 120.0, dur is not None and dur <= 0.100])
    return {'S1': {'rate_per_s': rate, 'events': len(events), 'airborne_s': airborne_s, 'excluded_threat_events': excluded,
                   'comparator': 1.37, 'class': classify(rate, (1.03, 1.71), (0.685, 2.74))},
            'S2': {'isi_mean_s': isi_mean, 'isi_median_s': float(np.median(isis)) if isis else None, 'n': len(isis),
                   'comparator_s': 0.818, 'class': classify(isi_mean, (0.613, 1.022), (0.409, 1.636))},
            'S3': {'amplitude_median_deg': amp, 'duration_median_s': dur, 'comparator': 'about 90 deg in < 100 ms',
                   'class': {2: 'match', 1: 'partial', 0: 'gap'}[s3] if events else 'not estimable'},
            'C1': {'airborne_speed_mean_bl_s': float(np.mean(speeds)) if speeds else None,
                   'comparator_bl_s': 107.0, 'note': 'context only; room_kinematic_scale is frozen'}}


def report():
    out = {'escape': escape_report(), 'saccades': saccade_report()}
    (OUT / 'scorecard.json').write_text(json.dumps(out, indent=1, default=str) + '\n', encoding='utf-8')
    print(json.dumps(out, indent=1, default=str))


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('step', choices=('escape', 'saccades', 'report'))
    {'escape': escape, 'saccades': saccades, 'report': report}[parser.parse_args().step]()


if __name__ == '__main__':
    main()
