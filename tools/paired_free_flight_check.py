"""Paired no-player free-flight check of a ROOM configuration change (from M1.8-B3a on).

Diagnostic only. No player acts, no runtime file changes, and no difficulty metric is
computed. Generalises tools/b2b_iii_free_flight_check.py, whose simulation, counterfactual
replay, categories and Poisson bound it reuses unchanged: each seed runs 180 s with the
pointer parked far away under the baseline configuration (read from a commit) and the
candidate configuration in the working tree, with the same code and the same Numba thread
count, and every policy escape is classified A-D by the N4B4 counterfactual method.

    NUMBA_NUM_THREADS=1 python tools/paired_free_flight_check.py run --arm baseline --lane 0 --lanes 2
    NUMBA_NUM_THREADS=1 python tools/paired_free_flight_check.py classify --lane 0 --lanes 4
    python tools/paired_free_flight_check.py summary

The defaults are the M1.8-B3a study (game/M1_8_B3A_DESIGN.md): baseline = the accepted
B2b-iii configuration at c4f9b8f, fresh seeds 9201-9280.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import time

os.environ.setdefault('NUMBA_NUM_THREADS', '1')
os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from game.session import load_config  # noqa: E402
from tools.b2b_iii_free_flight_check import (DT, HORIZON_TICKS, TICKS, category,  # noqa: E402
                                             lane_items, poisson_upper, simulate)

ARMS = ('baseline', 'candidate')


def arm_config(arm, baseline_commit):
    if arm == 'baseline':
        return json.loads(subprocess.check_output(
            ['git', 'show', baseline_commit + ':game_room_config.json'], cwd=ROOT, text=True))
    return load_config(ROOT / 'game_room_config.json')


def run(args):
    config = arm_config(args.arm, args.baseline_commit)
    out = args.out / args.arm
    out.mkdir(parents=True, exist_ok=True)
    brain = None
    for seed in lane_items(args.seeds, args.lane, args.lanes):
        path = out / ('seed%d.json' % seed)
        if path.exists():
            continue
        started = time.perf_counter()
        result, brain = simulate(config, seed, brain)
        result.update({'arm': args.arm, 'seed': seed, 'ticks': TICKS, 'config_version': config['config_version'],
                       'numba_threads': int(os.environ['NUMBA_NUM_THREADS']),
                       'wall_seconds': time.perf_counter() - started})
        path.write_text(json.dumps(result) + '\n', encoding='utf-8')
        print(args.arm, seed, 'escapes', len(result['escapes']), '%.0f s' % result['wall_seconds'], flush=True)


def classify(args):
    events = []
    for arm in ARMS:
        for seed in args.seeds:
            data = json.loads((args.out / arm / ('seed%d.json' % seed)).read_text(encoding='utf-8'))
            events += [(arm, seed, e['tick']) for e in data['escapes']]
    configs = {arm: arm_config(arm, args.baseline_commit) for arm in ARMS}
    out = args.out / 'counterfactual'
    out.mkdir(parents=True, exist_ok=True)
    brain = None
    for arm, seed, tick in lane_items(sorted(events), args.lane, args.lanes):
        path = out / ('%s_seed%d_tick%d.json' % (arm, seed, tick))
        if path.exists():
            continue
        result, brain = simulate(configs[arm], seed, brain, suppress=tick, until=tick + HORIZON_TICKS + 1)
        path.write_text(json.dumps({'arm': arm, 'seed': seed, 'tick': tick,
                                    'min_horizontal_units': min(result['distances'][:HORIZON_TICKS + 1]),
                                    'horizon_ticks': HORIZON_TICKS}) + '\n', encoding='utf-8')
        print('counterfactual', arm, seed, tick, flush=True)


def summary(args):
    report = {'baseline_commit': args.baseline_commit, 'seeds': [args.seeds[0], args.seeds[-1]],
              'ticks_per_run': TICKS, 'arms': {}}
    per_seed = {}
    for arm in ARMS:
        counts = {'A': 0, 'B': 0, 'C': 0, 'D': 0}
        minutes, escapes, perched, versions = 0.0, [], 0, set()
        for seed in args.seeds:
            data = json.loads((args.out / arm / ('seed%d.json' % seed)).read_text(encoding='utf-8'))
            minutes += data['alive_ticks']*DT/60
            versions.add(data['config_version'])
            per_seed.setdefault(seed, {})[arm] = [e['tick'] for e in data['escapes']]
            for e in data['escapes']:
                cf = json.loads((args.out / 'counterfactual' / ('%s_seed%d_tick%d.json' % (arm, seed, e['tick'])))
                                .read_text(encoding='utf-8'))
                e = dict(e, seed=seed, category=category(e, cf), cf_min_horizontal_units=cf['min_horizontal_units'])
                counts[e['category']] += 1
                perched += e['lifecycle_mode'] == 'PERCHED'
                escapes.append(e)
        total = sum(counts.values())
        report['arms'][arm] = {
            'config_versions': sorted(versions), 'minutes': minutes, 'escapes': total,
            'per_min': total/minutes, 'upper95_per_min': poisson_upper(total, minutes), 'perched_escapes': perched,
            'categories': {k: {'count': v, 'per_min': v/minutes, 'upper95_per_min': poisson_upper(v, minutes)}
                           for k, v in counts.items()},
            'events': escapes}
    report['seeds_with_identical_escape_ticks'] = sum(1 for s in per_seed.values() if s['baseline'] == s['candidate'])
    report['category_b_criterion_met'] = report['arms']['candidate']['categories']['B']['upper95_per_min'] < 0.1
    (args.out / 'summary.json').write_text(json.dumps(report, indent=1) + '\n', encoding='utf-8')
    for arm, a in report['arms'].items():
        print(arm, a['config_versions'], '%.1f min' % a['minutes'], 'escapes', a['escapes'],
              '%.3f/min (upper %.3f)' % (a['per_min'], a['upper95_per_min']),
              {k: v['count'] for k, v in a['categories'].items()}, 'perched', a['perched_escapes'])
    print('seeds with identical escape ticks in both arms:', report['seeds_with_identical_escape_ticks'],
          '/', len(args.seeds))
    print('category B criterion (< 0.1/min at 95 %) met for the candidate:', report['category_b_criterion_met'])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=('run', 'classify', 'summary'))
    parser.add_argument('--arm', choices=ARMS)
    parser.add_argument('--lane', type=int, default=0)
    parser.add_argument('--lanes', type=int, default=1)
    parser.add_argument('--baseline-commit', default='c4f9b8f8f4a1fc69959e1d74e5d76b4cc5b6e87f')
    parser.add_argument('--first-seed', type=int, default=9201)
    parser.add_argument('--last-seed', type=int, default=9280)
    parser.add_argument('--out', type=Path, default=ROOT / 'artifacts/m1_8_b3a/free_flight')
    args = parser.parse_args()
    args.seeds = tuple(range(args.first_seed, args.last_seed + 1))
    if args.mode == 'run':
        if args.arm is None:
            raise SystemExit('run needs --arm baseline or --arm candidate')
        run(args)
    elif args.mode == 'classify':
        classify(args)
    else:
        summary(args)


if __name__ == '__main__':
    main()
