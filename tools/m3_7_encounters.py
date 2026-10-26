"""M3.7 follow-up: why the M3.7 candidate escapes more in no-player flight (read-only).

Exploratory. No runtime file changes. M3.7 (results/game/M3_7_SACCADES.md) failed check P4: paired
no-player escapes rose from 9 to 15 in 240 minutes, all slow approaches to the hovering paddle.
It also lowered the share of odor-tracking time heading upwind from 0.66 to 0.41.

This tool separates two explanations:
- **More encounters.** The fly meets the paddle more often.
- **More escapes per encounter.** Each meeting more often ends in an escape.
It also measures how a saccade disturbs odor tracking.

**Runs.** 180 s no-player ROOM runs with the pointer parked, under:
- baseline v27 at commit 7483e51;
- candidate v31 at commit c10477d (read from git; the working file stays v27);
- variant: v31 with `ecology.spontaneous_clock_rate.ODOR_TRACK` = 0 in memory, so there are no
  spontaneous turns while the fly tracks an odor upwind. Its basis is Budick and Dickinson 2006:
  in an odor cloud flies "flew fast while maintaining an upwind heading" (summary). The
  parameter is class B in the M1.8-R0 lock and not frozen.
Seeds 972401-972440 for every arm (paired).

**Per tick it records:**
- alive and airborne;
- the horizontal distance to the paddle centre;
- the Retina θ;
- the policy's escape action;
- the ecology state and the actuator kind;
- the heading error to upwind.

**summary.**
- **Encounters.** Maximal airborne runs within 650 units of the paddle centre (every P4 escape
  came at 326-630 units). Reported: encounters per airborne minute, the share ending in an
  escape, and time spent within 650 units.
- **Odor tracking.**
  - the share of ODOR_TRACK airborne ticks heading within 45° of upwind, as in
    tools/kinematics_sanity.py;
  - SACCADE starts per ODOR_TRACK minute;
  - the upwind share by time since the last SACCADE start.

Outputs go to artifacts/m3_7/encounters/ (git-ignored).

    NUMBA_NUM_THREADS=1 python tools/m3_7_encounters.py run --arm baseline --lane K --lanes 2   (also candidate, variant)
    python tools/m3_7_encounters.py summary
"""
from __future__ import annotations

import argparse
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

from game.session import Session, build_policy  # noqa: E402
import tools.m3_0_scorecard as M  # noqa: E402

OUT = ROOT / 'artifacts/m3_7/encounters'
COMMITS = {'baseline': '7483e51', 'candidate': 'c10477d', 'variant': 'c10477d'}
SEEDS = tuple(range(972401, 972441))
TICKS = 9000
NEAR_UNITS = 650.0
UPWIND_DEG = 45.0
STATES = ('EXPLORE', 'TRANSIT', 'ODOR_SEARCH', 'ODOR_TRACK', 'LAND_OR_PERCH', 'ALERT', 'ESCAPE', 'RECOVER')
KINDS = ('NONE', 'CORRECTION', 'SACCADE', 'DEPART', 'AVOID', 'ALERT', 'ESCAPE')
SINCE_BINS = (0.0, 0.2, 0.5, 1.0, 2.0, float('inf'))


def arm_config(arm):
    config = json.loads(subprocess.check_output(['git', 'show', COMMITS[arm] + ':game_room_config.json'],
                                                cwd=ROOT, text=True))
    if arm == 'variant':
        config['ecology']['spontaneous_clock_rate']['ODOR_TRACK'] = 0.0
    return config


def wrap(a):
    return (a + math.pi) % (2 * math.pi) - math.pi


def run(args):
    config = arm_config(args.arm)
    out = OUT / args.arm
    M.check_provenance(out, 'seed*.npz')
    brain = None
    for k, seed in enumerate(SEEDS):
        if k % args.lanes != args.lane:
            continue
        path = out / ('seed%d.npz' % seed)
        if path.exists():
            continue
        # The variant has no record of its own; its decoder is v31's, so v31's record builds the policy.
        policy = build_policy(arm_config('candidate'), ROOT)[0] if args.arm == 'variant' else None
        session = Session(config, brain=brain, policy=policy, root=ROOT, seed=seed, mode='evaluation')
        brain, w = session.brain, session.world
        rows = np.full((TICKS, 7), np.nan)
        for t in range(TICKS):
            session.tick(pointer=M.PARKED)
            fly, sw = w.fly, w.swatter
            if not fly.alive:
                break                                    # rows from here on stay NaN
            airborne = not (w.lifecycle_active and w.lifecycle.stationary)
            state = session.ecology.state if session.ecology is not None else 'NONE'
            wx, wy = w.room.wind(w.time_seconds)
            upwind_error = abs(wrap(fly.heading - math.atan2(-wy, -wx))) if (wx or wy) else np.nan
            rows[t] = (KINDS.index(w.saccades.kind) if w.saccades.kind in KINDS else -1, float(airborne),
                       math.hypot(fly.x - sw.x, fly.y - sw.y), math.degrees(session.last_retina.theta),
                       float(session.fly_loop.last_action.escape), STATES.index(state) if state in STATES else -1,
                       math.degrees(upwind_error))
        session.close()
        np.savez_compressed(path, rows=rows, dt=config['sim']['tick_seconds'])
        print('%s seed %d done' % (args.arm, seed), flush=True)


def summary(_args):
    result = {}
    for arm in COMMITS:
        paths = [OUT / arm / ('seed%d.npz' % s) for s in SEEDS]
        if not all(p.exists() for p in paths):
            print('%s incomplete' % arm)
            continue
        M.recorded_provenance(OUT / arm)
        airborne_s = near_s = 0.0
        encounters = escaped_encounters = escapes = 0
        track_ticks = track_up = 0
        saccade_starts_in_track = clock_starts = 0
        since_counts = np.zeros(len(SINCE_BINS) - 1)
        since_up = np.zeros(len(SINCE_BINS) - 1)
        for path in paths:
            z = np.load(path)
            rows, dt = z['rows'], float(z['dt'])
            alive = ~np.isnan(rows[:, 1])
            rows = rows[alive]
            kind = rows[:, 0].astype(int)
            airborne = rows[:, 1] > 0
            dist, esc, state, upwind = rows[:, 2], rows[:, 4] > 0, rows[:, 5].astype(int), rows[:, 6]
            airborne_s += airborne.sum() * dt
            near = airborne & (dist < NEAR_UNITS)
            near_s += near.sum() * dt
            onset = esc & ~np.concatenate([[False], esc[:-1]])
            escapes += int(onset.sum())
            t, n = 0, len(rows)
            while t < n:
                if near[t]:
                    start = t
                    while t + 1 < n and near[t + 1]:
                        t += 1
                    encounters += 1
                    escaped_encounters += int(onset[start:t + 1].any())
                t += 1
            saccade = kind == KINDS.index('SACCADE')
            starts = saccade & ~np.concatenate([[False], saccade[:-1]])
            clock_starts += int((starts & airborne).sum())
            last = -1e9
            track = state == STATES.index('ODOR_TRACK')
            for i in range(n):
                if starts[i]:
                    last = i
                    if track[i] and airborne[i]:
                        saccade_starts_in_track += 1
                if track[i] and airborne[i] and not np.isnan(upwind[i]):
                    up = upwind[i] <= UPWIND_DEG
                    track_ticks += 1
                    track_up += int(up)
                    since = (i - last) * dt
                    b = np.searchsorted(SINCE_BINS, since, side='right') - 1
                    since_counts[b] += 1
                    since_up[b] += int(up)
        minutes = airborne_s / 60.0
        clock_rate = clock_starts / airborne_s
        r = {'airborne_min': minutes, 'clock_saccade_starts_per_s': clock_rate,
             'escapes': escapes, 'escapes_per_min': escapes / minutes,
             'encounters': encounters, 'encounters_per_min': encounters / minutes,
             'escaped_encounter_share': escaped_encounters / encounters if encounters else None,
             'near_share_of_airborne': near_s / airborne_s,
             'odor_track_upwind_share': track_up / track_ticks if track_ticks else None,
             'odor_track_minutes': track_ticks * dt / 60.0,
             'saccade_starts_per_odor_track_min': saccade_starts_in_track / (track_ticks * dt / 60.0)
             if track_ticks else None,
             'upwind_share_by_time_since_saccade': {
                 '%g-%g s' % (SINCE_BINS[i], SINCE_BINS[i + 1]): (since_up[i] / since_counts[i] if since_counts[i] else None,
                                                                  int(since_counts[i]))
                 for i in range(len(SINCE_BINS) - 1)}}
        result[arm] = r
        print('== %s: %.1f airborne min, %d escapes (%.3f per min); clock saccade starts %.3f per airborne s' % (
            arm, minutes, escapes, r['escapes_per_min'], clock_rate))
        print('   encounters within %g units: %d (%.2f per min), %.3f end in an escape; %.3f of airborne time near' % (
            NEAR_UNITS, encounters, r['encounters_per_min'], r['escaped_encounter_share'], r['near_share_of_airborne']))
        print('   ODOR_TRACK: %.1f min, upwind share %.3f, %.2f saccade starts per min' % (
            r['odor_track_minutes'], r['odor_track_upwind_share'], r['saccade_starts_per_odor_track_min']))
        print('   upwind share by time since the last saccade start: %s' % ', '.join(
            '%s %.2f (n %d)' % (k, v[0], v[1]) for k, v in r['upwind_share_by_time_since_saccade'].items()
            if v[0] is not None))
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / 'summary.json').write_text(json.dumps(result, indent=1) + '\n', encoding='utf-8')


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('mode', choices=('run', 'summary'))
    parser.add_argument('--arm', choices=tuple(COMMITS))
    parser.add_argument('--lane', type=int, default=0)
    parser.add_argument('--lanes', type=int, default=1)
    args = parser.parse_args()
    if args.mode == 'run' and args.arm is None:
        parser.error('run needs --arm')
    {'run': run, 'summary': summary}[args.mode](args)


if __name__ == '__main__':
    main()
