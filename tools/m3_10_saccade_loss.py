"""M3.10 follow-up: where the candidate loses clock-driven saccades (read-only).

Exploratory. No runtime file changes. M3.10 failed check P7: clock-driven saccades fell from 0.308
to 0.282 per airborne second (results/game/M3_10_UPWIND_SURGE.md, section 4). More ODOR_TRACK time
is already excluded.

**The flight generator** (game/flight.py). Its clock `wait` counts down by `dt × clock rate`, and
only while the actuator is idle and the policy is not steering. When it runs out:
- **Away from a wall,** the event is a SACCADE (M3.8: correction probability 0).
- **Near a wall** (the perimeter flag), the event is a CORRECTION, and the next interval is 1.7
  times longer.
- **A DEPART** resets the countdown to a fresh interval.

**The candidates for the loss.**
- **Less effective clock time:** a busier actuator, more policy steering, or another state mix.
- **More of it near walls:** corrections instead of saccades, and longer intervals.
- **More DEPART resets.**

**Runs.** P7's protocol-S sessions repeated: seeds 975501-975520, 180 s, no player, pointer
parked, under:
- baseline v32 (commit e113583);
- candidate v34 (commit 9c2b53d).

**Recorded.**
- **Per airborne tick:** the clock rate, whether the clock could run (actuator idle at the start of
  the tick, policy not steering), the perimeter flag and the ecology state.
- **Every accepted turn request:** its kind and the perimeter flag.

**The replication set.** `--seed-set replication` runs the same measurement on 40 fresh seeds,
976001-976040. It checks whether the P7 drop recurs on seeds that played no part in M3.10. The M3.10
decision does not depend on it.

Outputs go to artifacts/m3_10/saccade_loss/ (git-ignored); the replication set goes to its
`replication/` subdirectory.

    NUMBA_NUM_THREADS=1 python tools/m3_10_saccade_loss.py run --arm baseline --lane K --lanes 2   (also candidate)
    python tools/m3_10_saccade_loss.py summary
    NUMBA_NUM_THREADS=1 python tools/m3_10_saccade_loss.py run --seed-set replication --arm baseline --lane K --lanes 2
    python tools/m3_10_saccade_loss.py summary --seed-set replication
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
from game.world import World  # noqa: E402
import tools.m3_0_scorecard as M  # noqa: E402

OUT = ROOT / 'artifacts/m3_10/saccade_loss'
COMMITS = {'baseline': 'e113583', 'candidate': '9c2b53d'}
SEED_SETS = {'p7': tuple(range(975501, 975521)), 'replication': tuple(range(976001, 976041))}
SEEDS = SEED_SETS['p7']
STATES = ('EXPLORE', 'TRANSIT', 'ODOR_SEARCH', 'ODOR_TRACK', 'LAND_OR_PERCH', 'ALERT', 'ESCAPE', 'RECOVER')
KINDS = ('CORRECTION', 'SACCADE', 'DEPART', 'AVOID', 'SURGE', 'ALERT', 'ESCAPE')


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
        rows = np.zeros((M.SACCADE_TICKS, 5), np.float32)
        requests = []
        request = w.saccades.request

        def logged(kind, angle, peak_rate):
            accepted = request(kind, angle, peak_rate)
            if accepted and kind in KINDS:
                requests.append((session.ticks, KINDS.index(kind), int(w.flight.near_wall)))
            return accepted

        w.saccades.request = logged
        for t in range(M.SACCADE_TICKS):
            idle = not w.saccades.active
            session.tick(pointer=M.PARKED)
            if not w.fly.alive:
                break
            airborne = not (w.lifecycle_active and w.lifecycle.stationary)
            if not airborne:
                continue
            state = session.ecology.state if session.ecology is not None else 'NONE'
            neural = World._neural_active(session.fly_loop.last_action)
            rows[t] = (1.0, w.kinematic_profile.spontaneous_clock_rate, float(idle and not neural),
                       float(w.flight.near_wall), STATES.index(state) if state in STATES else -1)
        session.close()
        np.savez_compressed(path, rows=rows, requests=np.array(requests, np.int32).reshape(-1, 3),
                            dt=config['sim']['tick_seconds'])
        print('%s seed %d done' % (args.arm, seed), flush=True)


def summary(_args):
    result = {}
    for arm in COMMITS:
        tot = {'airborne_s': 0.0, 'clock_s': 0.0, 'clock_s_near': 0.0, 'clock_possible_s': 0.0, 'near_s': 0.0}
        counts = {(k, near): 0 for k in KINDS for near in (0, 1)}
        for seed in SEEDS:
            z = np.load(OUT / arm / ('seed%d.npz' % seed))
            rows, req, dt = z['rows'], z['requests'], float(z['dt'])
            air = rows[:, 0] > 0
            rate, runs, near = rows[:, 1], rows[:, 2] > 0, rows[:, 3] > 0
            tot['airborne_s'] += float(air.sum()) * dt
            tot['near_s'] += float((air & near).sum()) * dt
            tot['clock_possible_s'] += float((air * rate).sum()) * dt
            tot['clock_s'] += float((air & runs) @ rate) * dt
            tot['clock_s_near'] += float((air & runs & near) @ rate) * dt
            for _tick, kind, n in req:
                counts[(KINDS[kind], int(n))] += 1
        a = tot['airborne_s']
        clock_events = sum(counts[(k, n)] for k in ('SACCADE', 'CORRECTION') for n in (0, 1))
        r = dict(tot)
        r.update({'requests': {'%s%s' % (k, '_near' if n else ''): v for (k, n), v in counts.items() if v},
                  'saccades_per_airborne_s': (counts[('SACCADE', 0)] + counts[('SACCADE', 1)]) / a,
                  'clock_s_per_airborne_s': tot['clock_s'] / a,
                  'near_share_of_clock_s': tot['clock_s_near'] / tot['clock_s'],
                  'clock_events_per_clock_s': clock_events / tot['clock_s'],
                  'saccade_share_of_clock_events': (counts[('SACCADE', 0)] + counts[('SACCADE', 1)]) / clock_events,
                  'departs_per_airborne_s': (counts[('DEPART', 0)] + counts[('DEPART', 1)]) / a,
                  'near_share_of_airborne': tot['near_s'] / a})
        result[arm] = r
        print('== %s: %.0f airborne s; SACCADE %.3f per airborne s' % (arm, a, r['saccades_per_airborne_s']))
        print('   clock seconds %.0f (%.3f per airborne s; %.3f possible); near-wall share of clock seconds %.3f' % (
            tot['clock_s'], r['clock_s_per_airborne_s'], tot['clock_possible_s'] / a, r['near_share_of_clock_s']))
        print('   clock events per clock second %.3f; SACCADE share of clock events %.3f; DEPART %.3f per airborne s' % (
            r['clock_events_per_clock_s'], r['saccade_share_of_clock_events'], r['departs_per_airborne_s']))
        print('   near-wall share of airborne time %.3f; requests %s' % (r['near_share_of_airborne'], r['requests']))
    b, c = result['baseline'], result['candidate']
    # The saccade rate per airborne second is the product of three factors.
    factors = ('clock_s_per_airborne_s', 'clock_events_per_clock_s', 'saccade_share_of_clock_events')
    result['factor_ratios'] = {f: c[f] / b[f] for f in factors}
    print('candidate / baseline: ' + ', '.join('%s %.3f' % (f, v) for f, v in result['factor_ratios'].items())
          + '; product %.3f, observed %.3f' % (np.prod(list(result['factor_ratios'].values())),
                                                c['saccades_per_airborne_s'] / b['saccades_per_airborne_s']))
    (OUT / 'summary.json').write_text(json.dumps(result, indent=1) + '\n', encoding='utf-8')


def main():
    global OUT, SEEDS
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('mode', choices=('run', 'summary'))
    parser.add_argument('--seed-set', choices=tuple(SEED_SETS), default='p7')
    parser.add_argument('--arm', choices=tuple(COMMITS))
    parser.add_argument('--lane', type=int, default=0)
    parser.add_argument('--lanes', type=int, default=1)
    args = parser.parse_args()
    SEEDS = SEED_SETS[args.seed_set]
    if args.seed_set != 'p7':
        OUT = OUT / args.seed_set
    if args.mode == 'run' and args.arm is None:
        parser.error('run needs --arm')
    {'run': run, 'summary': summary}[args.mode](args)


if __name__ == '__main__':
    main()
