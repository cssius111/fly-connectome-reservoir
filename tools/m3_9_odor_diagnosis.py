"""M3.9 follow-up: why the v33 candidate heads upwind less while tracking an odor (read-only).

Exploratory. No runtime file changes. M3.9 failed check P6 (results/game/M3_9_WALL_SACCADES.md,
section 4): the ODOR_TRACK upwind share fell from 0.564 to 0.481 on seeds 974401-974440.
- **What is excluded.** Wall turns during tracking are rare in both arms.

**The ecology** (game/ecology.py). In ODOR_TRACK it steers by three terms:
- upwind;
- toward the antenna with the stronger concentration;
- away from visual obstacles.

The food is at x = 1050 with the wind along +x, so tracking means flying upwind (toward -x) to the
food.

**The hypothesis tested.** The candidate reaches the food more often (results, section 5). Near
the source the bilateral cue and the approach to landing turn the heading off the wind. Then a
better tracker would score a lower upwind share: a composition effect, not worse tracking within
any part of the plume.

**Runs.** The P6 runs repeated with more per-tick fields: 180 s no-player ROOM runs with the
pointer parked, seeds 974401-974440, under:
- baseline v32 (commit 925427c);
- candidate v33 (commit 7727397).

**Per alive tick it records:**
- the ecology state and airborne;
- the heading error to upwind;
- the along-wind and cross-wind offset of the fly from the food, in units;
- the clearance to the nearest wall, in body lengths.

**summary.** Upwind share in ODOR_TRACK by distance to the food, by time since the bout started and
by wall clearance; the bouts and what follows them; and the candidate's share re-weighted to the
baseline's distribution over distance to the food.

Outputs go to artifacts/m3_9/odor_diagnosis/ (git-ignored).

    NUMBA_NUM_THREADS=1 python tools/m3_9_odor_diagnosis.py run --arm baseline --lane K --lanes 2   (also candidate)
    python tools/m3_9_odor_diagnosis.py summary
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

from game.session import Session  # noqa: E402
import tools.m3_0_scorecard as M  # noqa: E402

OUT = ROOT / 'artifacts/m3_9/odor_diagnosis'
COMMITS = {'baseline': '925427c', 'candidate': '7727397'}
SEEDS = tuple(range(974401, 974441))
TICKS = 9000
UPWIND_DEG = 45.0
STATES = ('EXPLORE', 'TRANSIT', 'ODOR_SEARCH', 'ODOR_TRACK', 'LAND_OR_PERCH', 'ALERT', 'ESCAPE', 'RECOVER')
DIST_BINS = (0.0, 200.0, 400.0, 800.0, 1600.0, float('inf'))
SINCE_BINS = (0.0, 0.5, 1.0, 2.0, 4.0, float('inf'))
CLEAR_BINS = (0.0, 3.0, 6.0, float('inf'))


def arm_config(arm):
    return json.loads(subprocess.check_output(['git', 'show', COMMITS[arm] + ':game_room_config.json'],
                                              cwd=ROOT, text=True))


def wrap(a):
    return (a + math.pi) % (2 * math.pi) - math.pi


def run(args):
    config = arm_config(args.arm)
    out = OUT / args.arm
    M.check_provenance(out, 'seed*.npz')
    food = config['room']['food']
    brain = None
    for k, seed in enumerate(SEEDS):
        if k % args.lanes != args.lane:
            continue
        path = out / ('seed%d.npz' % seed)
        if path.exists():
            continue
        session = Session(config, brain=brain, root=ROOT, seed=seed, mode='evaluation')
        brain, w = session.brain, session.world
        body = w.body_length
        rows = np.full((TICKS, 6), np.nan)
        for t in range(TICKS):
            session.tick(pointer=M.PARKED)
            fly = w.fly
            if not fly.alive:
                break
            airborne = not (w.lifecycle_active and w.lifecycle.stationary)
            state = session.ecology.state if session.ecology is not None else 'NONE'
            wx, wy = w.room.wind(w.time_seconds)
            speed = math.hypot(wx, wy)
            ux, uy = wx / speed, wy / speed
            dx, dy = fly.x - food['x'], fly.y - food['y']
            upwind_error = abs(wrap(fly.heading - math.atan2(-wy, -wx)))
            clearance = min(c for _side, c, _n, _a in w.enclosure._walls(fly.x, fly.y))
            rows[t] = (STATES.index(state) if state in STATES else -1, float(airborne), math.degrees(upwind_error),
                       dx * ux + dy * uy, -dx * uy + dy * ux, clearance / body)
        session.close()
        np.savez_compressed(path, rows=rows, dt=config['sim']['tick_seconds'])
        print('%s seed %d done' % (args.arm, seed), flush=True)


def binned(values, up, bins):
    idx = np.searchsorted(bins, values, side='right') - 1
    return [(int((idx == b).sum()), float(up[idx == b].mean()) if (idx == b).any() else None)
            for b in range(len(bins) - 1)]


def summary(_args):
    result = {}
    for arm in COMMITS:
        paths = [OUT / arm / ('seed%d.npz' % s) for s in SEEDS]
        if not all(p.exists() for p in paths):
            sys.exit('%s incomplete' % arm)
        M.recorded_provenance(OUT / arm)
        dist, since, clear, up, outcomes, bout_s = [], [], [], [], {}, []
        for p in paths:
            z = np.load(p)
            rows, dt = z['rows'], float(z['dt'])
            rows = rows[~np.isnan(rows[:, 1])]
            state, air = rows[:, 0].astype(int), rows[:, 1] > 0
            track = state == STATES.index('ODOR_TRACK')
            start = None
            for i in range(len(rows)):
                if track[i] and (i == 0 or not track[i - 1]):
                    start = i
                if track[i] and air[i]:
                    dist.append(math.hypot(rows[i, 3], rows[i, 4]))
                    since.append((i - start) * dt)
                    clear.append(rows[i, 5])
                    up.append(rows[i, 2] <= UPWIND_DEG)
                if track[i] and (i + 1 == len(rows) or not track[i + 1]):
                    nxt = STATES[state[i + 1]] if i + 1 < len(rows) and state[i + 1] >= 0 else 'END'
                    outcomes[nxt] = outcomes.get(nxt, 0) + 1
                    bout_s.append((i - start + 1) * dt)
        dist, since, clear, up = map(np.asarray, (dist, since, clear, up))
        result[arm] = {'ticks': int(len(up)), 'upwind_share': float(up.mean()),
                       'by_distance_to_food': binned(dist, up, DIST_BINS),
                       'by_time_since_bout_start': binned(since, up, SINCE_BINS),
                       'by_wall_clearance_bl': binned(clear, up, CLEAR_BINS),
                       'bouts': len(bout_s), 'bout_seconds_mean': float(np.mean(bout_s)),
                       'bout_outcomes': dict(sorted(outcomes.items()))}
    b, c = result['baseline'], result['candidate']
    wb = np.array([n for n, _ in b['by_distance_to_food']], float)
    sc = np.array([s if s is not None else 0.0 for _, s in c['by_distance_to_food']])
    result['candidate_reweighted_to_baseline_distance'] = float((wb * sc).sum() / wb.sum())
    for arm in COMMITS:
        r = result[arm]
        print('== %s: %d ODOR_TRACK airborne ticks, upwind share %.3f; %d bouts, mean %.2f s; outcomes %s' % (
            arm, r['ticks'], r['upwind_share'], r['bouts'], r['bout_seconds_mean'], r['bout_outcomes']))
        for label, bins, key in (('distance to food (units)', DIST_BINS, 'by_distance_to_food'),
                                 ('time since bout start (s)', SINCE_BINS, 'by_time_since_bout_start'),
                                 ('wall clearance (BL)', CLEAR_BINS, 'by_wall_clearance_bl')):
            cells = ['%g-%g: %.3f of ticks, up %s' % (bins[i], bins[i + 1], n / r['ticks'],
                                                       '%.2f' % s if s is not None else '-')
                     for i, (n, s) in enumerate(r[key])]
            print('   %s: %s' % (label, '; '.join(cells)))
    print('candidate share re-weighted to the baseline distance distribution: %.3f (raw %.3f, baseline %.3f)' % (
        result['candidate_reweighted_to_baseline_distance'], c['upwind_share'], b['upwind_share']))
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
