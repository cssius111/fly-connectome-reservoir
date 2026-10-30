"""M3.10 follow-up: does the lower clock-driven saccade rate come from time spent tracking? (read-only)

Exploratory. No runtime file changes. M3.10 failed check P7: clock-driven saccades fell from 0.308
to 0.282 per usable airborne second. M3.8 stopped the spontaneous clock during ODOR_TRACK
(`ecology.spontaneous_clock_rate.ODOR_TRACK` = 0, frozen).
- **The hypothesis.** A fly that turns upwind sooner tracks longer, so it spends more airborne time
  in a state that never makes clock saccades.

**Runs.** P7's protocol-S sessions repeated: seeds 975501-975520, 180 s, no player, pointer
parked, under:
- baseline v32 (commit e113583);
- candidate v34 (commit 9c2b53d).

**Per tick it records:**
- airborne;
- the ecology state;
- the actuator kind.

**summary.** Per arm:
- the airborne time by ecology state;
- SACCADE starts per airborne second, overall and outside ODOR_TRACK;
- SACCADE starts per clock-weighted airborne second: each state's time multiplied by its
  `spontaneous_clock_rate`.

Outputs go to artifacts/m3_10/clock_time/ (git-ignored).

    NUMBA_NUM_THREADS=1 python tools/m3_10_clock_time.py run --arm baseline --lane K --lanes 2   (also candidate)
    python tools/m3_10_clock_time.py summary
"""
from __future__ import annotations

import argparse
import json
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

OUT = ROOT / 'artifacts/m3_10/clock_time'
COMMITS = {'baseline': 'e113583', 'candidate': '9c2b53d'}
SEEDS = tuple(range(975501, 975521))
STATES = ('EXPLORE', 'TRANSIT', 'ODOR_SEARCH', 'ODOR_TRACK', 'LAND_OR_PERCH', 'ALERT', 'ESCAPE', 'RECOVER')


def arm_config(arm):
    return json.loads(subprocess.check_output(['git', 'show', COMMITS[arm] + ':game_room_config.json'],
                                              cwd=ROOT, text=True))


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
        session = Session(config, brain=brain, root=ROOT, seed=seed, mode='evaluation')
        brain, w = session.brain, session.world
        rows = np.zeros((M.SACCADE_TICKS, 3), np.int16)
        for t in range(M.SACCADE_TICKS):
            session.tick(pointer=M.PARKED)
            airborne = w.fly.alive and not (w.lifecycle_active and w.lifecycle.stationary)
            state = session.ecology.state if session.ecology is not None else 'NONE'
            rows[t] = (int(airborne), STATES.index(state) if state in STATES else -1,
                       int(w.saccades.kind == 'SACCADE'))
        session.close()
        np.savez_compressed(path, rows=rows, dt=config['sim']['tick_seconds'])
        print('%s seed %d done' % (args.arm, seed), flush=True)


def summary(_args):
    result = {}
    for arm in COMMITS:
        clock = arm_config(arm)['ecology']['spontaneous_clock_rate']
        seconds = dict.fromkeys(STATES, 0.0)
        starts = dict.fromkeys(STATES, 0)
        for seed in SEEDS:
            z = np.load(OUT / arm / ('seed%d.npz' % seed))
            rows, dt = z['rows'], float(z['dt'])
            air, state, sac = rows[:, 0] > 0, rows[:, 1], rows[:, 2] > 0
            start = sac & ~np.concatenate([[False], sac[:-1]]) & air
            for k, name in enumerate(STATES):
                seconds[name] += float((air & (state == k)).sum()) * dt
                starts[name] += int((start & (state == k)).sum())
        airborne = sum(seconds.values())
        outside = airborne - seconds['ODOR_TRACK']
        weighted = sum(seconds[s] * clock[s] for s in STATES)
        total = sum(starts.values())
        result[arm] = {'airborne_s': airborne, 'seconds_by_state': seconds, 'saccade_starts_by_state': starts,
                       'starts_per_airborne_s': total / airborne,
                       'starts_per_airborne_s_outside_odor_track': (total - starts['ODOR_TRACK']) / outside,
                       'starts_per_clock_weighted_s': total / weighted}
        r = result[arm]
        print('== %s: %.0f airborne s; ODOR_TRACK %.0f s (%.3f); SACCADE starts %d' % (
            arm, airborne, seconds['ODOR_TRACK'], seconds['ODOR_TRACK'] / airborne, total))
        print('   per airborne s %.3f; outside ODOR_TRACK %.3f; per clock-weighted s %.3f' % (
            r['starts_per_airborne_s'], r['starts_per_airborne_s_outside_odor_track'],
            r['starts_per_clock_weighted_s']))
        print('   airborne s by state: ' + ', '.join('%s %.0f' % (s, seconds[s]) for s in STATES if seconds[s]))
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
