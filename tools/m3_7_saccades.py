"""M3.7 checks P1, P2, P5 and descriptive D1 (game/M3_7_SACCADE_DESIGN.md).

- **protocol-s.** M3.0's protocol S, unchanged (tools/m3_0_scorecard.py):
  - 180 s no-player ROOM runs with the pointer parked;
  - its 450°/s detector and threat exclusions.
  It is run under one arm on seeds 972001-972020. Per tick it records airborne, speed, yaw rate,
  escape and alive, and the actuator kind.
- **protocol-e.** M3.0's protocol E (fixed fly, all 16 l/v × azimuth conditions), under one arm
  on seeds 972301-972324. It records each trial's first escape.
- **summary.**
  - **P1.** The clock-driven rate: detected events produced by SACCADE requests, per usable
    airborne second. Pass: 0.30-0.50 per s.
  - **P2.** S3 on all spontaneous events. Pass: median amplitude 60-120° and median duration
    ≤ 100 ms.
  - **P5.** Identical fixed-fly escapes in every trial of both arms.
  - **D1.** S1, S2 and the events by kind for both arms.

**Arms.**
- **baseline.** v27 at commit 7483e51.
- **candidate.** The working ROOM configuration (v31).

Outputs go to artifacts/m3_7/ (git-ignored), with the M3.0 provenance guard.

    NUMBA_NUM_THREADS=1 python tools/m3_7_saccades.py protocol-s --arm candidate --lane 0 --lanes 2
    NUMBA_NUM_THREADS=1 python tools/m3_7_saccades.py protocol-e --arm baseline
    python tools/m3_7_saccades.py summary
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import json
import math
import os
from pathlib import Path
import subprocess
import sys

os.environ.setdefault('NUMBA_NUM_THREADS', '1')
os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import numpy as np  # noqa: E402

from game.session import Session, load_config  # noqa: E402
import tools.m3_0_scorecard as M  # noqa: E402

OUT = ROOT / 'artifacts/m3_7'
ARMS = ('baseline', 'candidate')
BASELINE_COMMIT = '7483e51'
S_SEEDS = tuple(range(972001, 972021))
E_SEEDS = tuple(range(972301, 972325))
P1_BAND = (0.30, 0.50)


def arm_config(arm):
    if arm == 'baseline':
        c = json.loads(subprocess.check_output(['git', 'show', BASELINE_COMMIT + ':game_room_config.json'],
                                               cwd=ROOT, text=True))
        assert c['config_version'] == 27
        return c
    c = load_config(ROOT / 'game_room_config.json')
    assert c['config_version'] == 31, 'the working ROOM configuration is not the M3.7 candidate'
    return c


def protocol_s(args):
    cfg = arm_config(args.arm)
    out = OUT / 'saccades' / args.arm
    M.check_provenance(out, 'seed*.npz')
    brain = None
    for k, seed in enumerate(S_SEEDS):
        if k % args.lanes != args.lane:
            continue
        path = out / ('seed%d.npz' % seed)
        if path.exists():
            continue
        session = Session(cfg, brain=brain, root=ROOT, seed=seed, mode='evaluation')
        brain, w = session.brain, session.world
        bl = w.body_length
        rows = np.zeros((M.SACCADE_TICKS, 5), np.float64)
        kinds = []
        for t in range(M.SACCADE_TICKS):
            session.tick(pointer=M.PARKED)
            airborne = w.fly.alive and not (w.lifecycle_active and w.lifecycle.stationary)
            rows[t] = (airborne, math.hypot(w.fly.vx, w.fly.vy) / bl, w.yaw_rate,
                       session.fly_loop.last_action.escape, w.fly.alive)
            kinds.append(w.saccades.kind)
        session.close()
        np.savez_compressed(path, rows=rows, kinds=np.array(kinds), dt=cfg['sim']['tick_seconds'])
        print('%s protocol S seed %d done' % (args.arm, seed), flush=True)


def protocol_e(args):
    cfg = arm_config(args.arm)
    out = OUT / 'escape' / args.arm
    M.check_provenance(out, '*.json')
    dt = float(cfg['sim']['tick_seconds'])
    session = Session(cfg, root=ROOT, ecology_enabled=False)
    session.world.collisions_enabled = False
    session.world.fly_motion_enabled = False
    for lv_ms in M.LV_MS:
        for name, azimuth in M.AZIMUTHS.items():
            path = out / ('lv%03d_%s.json' % (lv_ms, name))
            if path.exists():
                continue
            retinas, pre, t0, thetas = M.stimulus(lv_ms / 1000.0, azimuth, dt)
            trials = []
            for seed in E_SEEDS:
                session.reset(seed)
                fly = session.world.fly
                fly.vx = fly.vy = 0.0
                pose = (fly.x, fly.y, fly.heading)
                feed = iter(retinas)
                session.projector.project = lambda world, feed=feed: next(feed)
                escapes = []
                for i in range(len(retinas)):
                    session.tick()
                    a = session.fly_loop.last_action
                    if a.escape:
                        escapes.append([i, float(a.forward), float(a.lateral)])
                    if (fly.x, fly.y, fly.heading) != pose:
                        raise RuntimeError('the fly moved')
                del session.projector.project
                trials.append({'seed': seed, 'escapes': escapes})
            path.write_text(json.dumps({'lv_ms': lv_ms, 'azimuth': name, 'trials': trials}) + '\n', encoding='utf-8')
            print('%s protocol E lv %d %s done' % (args.arm, lv_ms, name), flush=True)
    session.close()


def events(arm):
    """M3.0's protocol-S detector, with each event's actuator kind."""
    paths = [OUT / 'saccades' / arm / ('seed%d.npz' % s) for s in S_SEEDS]
    missing = [p.name for p in paths if not p.exists()]
    if missing:
        raise SystemExit('%s protocol S is incomplete: %s' % (arm, missing))
    M.recorded_provenance(OUT / 'saccades' / arm)
    found, airborne_s, isis, speeds = [], 0.0, [], []
    for path in paths:
        z = np.load(path)
        rows, kinds, dt = z['rows'], z['kinds'], float(z['dt'])
        airborne, speed, yaw, esc = rows[:, 0] > 0, rows[:, 1], rows[:, 2], rows[:, 3] > 0
        post = np.zeros(len(rows), bool)
        for i in np.flatnonzero(esc):
            post[i:i + int(round(M.POST_ESCAPE_S / dt)) + 1] = True
        usable = airborne & ~post
        airborne_s += float(usable.sum()) * dt
        speeds.extend(speed[airborne].tolist())
        onsets, t, n = [], 0, len(rows)
        while t < n:
            if airborne[t] and abs(yaw[t]) >= M.SACCADE_THRESHOLD:
                start, sign = t, np.sign(yaw[t])
                while (t + 1 < n and airborne[t + 1] and abs(yaw[t + 1]) >= M.SACCADE_THRESHOLD
                       and np.sign(yaw[t + 1]) == sign):
                    t += 1
                ks = [str(k) for k in kinds[start:t + 1]]
                if not (any(k in ('ESCAPE', 'ALERT') for k in ks) or post[start]):
                    common = Counter(k for k in ks if k != 'NONE').most_common(1)
                    found.append({'kind': common[0][0] if common else 'NONE',
                                  'amplitude_deg': abs(math.degrees(float(yaw[start:t + 1].sum()) * dt)),
                                  'duration_s': (t - start + 1) * dt})
                    onsets.append(start)
            t += 1
        for a, b in zip(onsets, onsets[1:]):
            if usable[a:b + 1].all():
                isis.append((b - a) * dt)
    return found, airborne_s, isis, speeds


def summary(_args):
    result = {}
    for arm in ARMS:
        try:
            found, airborne_s, isis, speeds = events(arm)
        except SystemExit as e:
            print(e)
            continue
        by = defaultdict(list)
        for e in found:
            by[e['kind']].append(e)
        amp = float(np.median([e['amplitude_deg'] for e in found]))
        dur = float(np.median([e['duration_s'] for e in found]))
        clock = len(by['SACCADE']) / airborne_s
        result[arm] = {
            'airborne_s': airborne_s, 'events': len(found), 'S1_rate_per_s': len(found) / airborne_s,
            'S2_isi_mean_s': float(np.mean(isis)), 'S2_isi_median_s': float(np.median(isis)),
            'S3_amplitude_median_deg': amp, 'S3_duration_median_s': dur,
            'S3_match': 60.0 <= amp <= 120.0 and dur <= 0.100,
            'clock_saccade_rate_per_s': clock, 'P1_pass': P1_BAND[0] <= clock <= P1_BAND[1],
            'speed_mean_bl_s': float(np.mean(speeds)),
            'by_kind': {k: {'events': len(v), 'per_s': len(v) / airborne_s,
                            'amplitude_median_deg': float(np.median([e['amplitude_deg'] for e in v])),
                            'duration_median_ms': 1000 * float(np.median([e['duration_s'] for e in v]))}
                        for k, v in by.items()}}
        r = result[arm]
        print('== %s: %.0f usable airborne s, %d events' % (arm, airborne_s, len(found)))
        print('   clock-driven saccades %.3f per s (P1 band %.2f-%.2f: %s)' % (
            clock, *P1_BAND, 'pass' if r['P1_pass'] else 'FAIL'))
        print('   S3 median %.1f deg in %.0f ms (P2: %s)' % (amp, 1000 * dur, 'pass' if r['S3_match'] else 'FAIL'))
        print('   S1 %.3f per s; S2 mean %.2f s, median %.2f s; speed %.2f BL/s' % (
            r['S1_rate_per_s'], r['S2_isi_mean_s'], r['S2_isi_median_s'], r['speed_mean_bl_s']))
        for k, v in sorted(r['by_kind'].items(), key=lambda kv: -kv[1]['events']):
            print('   %-10s %4d events %.3f per s, median %.0f deg in %.0f ms' % (
                k, v['events'], v['per_s'], v['amplitude_median_deg'], v['duration_median_ms']))
    identical = differing = 0
    missing = []
    for lv_ms in M.LV_MS:
        for name in M.AZIMUTHS:
            paths = [OUT / 'escape' / arm / ('lv%03d_%s.json' % (lv_ms, name)) for arm in ARMS]
            if not all(p.exists() for p in paths):
                missing.append('%d_%s' % (lv_ms, name))
                continue
            a, b = (json.loads(p.read_text(encoding='utf-8'))['trials'] for p in paths)
            for x, y in zip(a, b):
                if x == y:
                    identical += 1
                else:
                    differing += 1
    if missing:
        print('P5 incomplete: %s' % missing)
    else:
        print('P5: %d identical and %d differing fixed-fly trials (%s)' % (
            identical, differing, 'pass' if differing == 0 else 'FAIL'))
        result['P5'] = {'identical': identical, 'differing': differing, 'pass': differing == 0}
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / 'summary.json').write_text(json.dumps(result, indent=1) + '\n', encoding='utf-8')


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('mode', choices=('protocol-s', 'protocol-e', 'summary'))
    parser.add_argument('--arm', choices=ARMS)
    parser.add_argument('--lane', type=int, default=0)
    parser.add_argument('--lanes', type=int, default=1)
    args = parser.parse_args()
    if args.mode != 'summary' and args.arm is None:
        parser.error('%s needs --arm' % args.mode)
    {'protocol-s': protocol_s, 'protocol-e': protocol_e, 'summary': summary}[args.mode](args)


if __name__ == '__main__':
    main()
