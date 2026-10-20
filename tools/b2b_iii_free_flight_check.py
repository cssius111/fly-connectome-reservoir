"""M1.8-B2b-iii acceptance check 5: paired no-player free flight, config 17 against 18.

Diagnostic only. No player acts, no runtime file changes, and no difficulty metric is
computed. Each fresh seed runs 180 s with the pointer parked far away under both the
accepted N4B5R ROOM configuration (config_version 17, read from commit 363a1a9) and the
B2b-iii candidate in the working tree (config_version 18). Both arms use the same code
and the same Numba thread count, so they differ only in ODOR_TRACK speed sampling.

Every policy escape is then classified with the N4B4 counterfactual method (ported from
tools/n4b4_replay.py and tools/n4b4_analysis.py on wip/m1-4-enclosure): the run is
replayed with that escape withheld for 2 s, the world receiving only the policy's smoothed
turn and ecology and lifecycle seeing ALERT instead of ESCAPE. Reporting categories, as
adopted in M1.8-N4B4 / N4B5:

* A: no LC4/LPLC2 drive in the 120 ms before the escape (a neural false escape);
* B: stimulus-driven, but without the escape the fly never comes within 310 units of the
  paddle centre in 1.5 s (inappropriate);
* C: stimulus-driven near pass whose expansion over the 120 ms before the escape comes
  mostly from apparent-size change rather than range change (foreshortening);
* D: stimulus-driven near pass driven mostly by range change (self-approach).

Seeds 9101-9180 are fresh: they appear in no report, tool or holdout list on any branch.

    NUMBA_NUM_THREADS=1 python tools/b2b_iii_free_flight_check.py run --arm v18 --lane 0 --lanes 4
    NUMBA_NUM_THREADS=1 python tools/b2b_iii_free_flight_check.py classify --lane 0 --lanes 4
    python tools/b2b_iii_free_flight_check.py summary
"""
from __future__ import annotations

import argparse
from collections import deque
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import time

os.environ.setdefault('NUMBA_NUM_THREADS', '1')
os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scipy.stats import chi2

from game.action import Action
from game.session import Session, build_policy, load_config

OUT = ROOT / 'artifacts/m1_8_b2b_iii/free_flight'
SEEDS = tuple(range(9101, 9181))
TICKS = 9000                  # 180 simulated seconds per run
DT = 0.02
PARKED = (1920.0, 388.8)
ACCEPTED_COMMIT = '363a1a94cf3f5e33efab08cb28594c24ca694a03'
LOOKBACK_TICKS = 6            # 120 ms before and including the escape tick
SUPPRESS_TICKS = 100          # 2 s: covers the 0.4 s refractory and any re-fire
HORIZON_TICKS = 75            # 1.5 s classification horizon (N4B4)
NEAR_PASS_UNITS = 310.0       # N4B4: twice the paddle-plus-body collision radius


def arm_config(arm):
    if arm == 'v17':
        return json.loads(subprocess.check_output(
            ['git', 'show', ACCEPTED_COMMIT + ':game_room_config.json'], cwd=ROOT, text=True))
    if arm == 'v18':
        return load_config(ROOT / 'game_room_config.json')
    raise ValueError(arm)


class Suppress:
    """Counterfactual wrapper: the policy runs unchanged; escapes in the window are withheld
    from the world, and its ESCAPE state is shown to ecology and lifecycle as ALERT."""

    def __init__(self, policy, ref, start, length):
        self._p, self._ref, self.start, self.end = policy, ref, start, start + length

    def __getattr__(self, name):
        return getattr(self._p, name)

    def _active(self):
        return self.start <= self._ref['tick'] < self.end

    def reset(self):
        return self._p.reset()

    def decide(self, motor):
        a = self._p.decide(motor)
        if a.escape and self._active():
            return Action(turn=a.turn)
        return a

    def diagnostics(self):
        d = dict(self._p.diagnostics())
        if self._active() and d.get('behavior_state') == 'ESCAPE':
            d['behavior_state'] = 'ALERT'
        return d


def _geometry(world):
    fly, sw = world.fly, world.swatter
    horizontal = math.hypot(fly.x - sw.x, fly.y - sw.y)
    return horizontal, math.sqrt(horizontal*horizontal + sw.height*sw.height), float(world.visual_half_size)


def simulate(config, seed, brain=None, suppress=None, until=TICKS):
    """One run. Returns its escapes (factual) or the post-event distances (counterfactual)."""
    policy, _ = build_policy(config)
    ref = {'tick': 0}
    active = Suppress(policy, ref, suppress, SUPPRESS_TICKS) if suppress is not None else policy
    session = Session(config, brain=brain, policy=active, seed=seed, mode='evaluation')
    history = deque(maxlen=LOOKBACK_TICKS + 1)
    escapes, distances = [], []
    try:
        for tick in range(until):
            ref['tick'] = tick
            session.tick(pointer=PARKED)
            world = session.world
            horizontal, distance, half = _geometry(world)
            drive = sum(abs(float(v)) for v in session.fly_loop.encoder.last_drive.values())
            history.append((half, distance, drive))
            if suppress is not None and tick >= suppress and world.fly.alive:
                distances.append(horizontal)
            diag = policy.criterion_diagnostics()
            fired = (diag['escape_trigger_channel'] != 'NONE'
                     and policy.refractory_remaining == policy.refractory_ticks)
            if suppress is None and fired:
                window = list(history)
                size = rng = 0.0
                for (h0, r0, _), (h1, r1, _) in zip(window, window[1:]):
                    rng += 2*math.atan(h0/r1) - 2*math.atan(h0/r0)
                    size += 2*math.atan(h1/r1) - 2*math.atan(h0/r1)
                retina = session.last_retina
                life = world.lifecycle
                escapes.append({'tick': tick, 'channel': diag['escape_trigger_channel'],
                                'paths': diag.get('escape_trigger_paths'),
                                'lifecycle_mode': None if life is None else str(life.mode),
                                'ecology_state': None if session.ecology is None else session.ecology.state,
                                'theta': float(retina.theta), 'theta_dot': float(retina.theta_dot),
                                'horizontal_units': horizontal, 'distance_units': distance,
                                'drive_window': sum(d for _, _, d in window[1:]),
                                'range_expansion_rad': rng, 'size_expansion_rad': size})
            if not world.fly.alive and suppress is None:
                break
        draws = dict(session.world.kinematic_sampler.draws_by_context)
        alive_ticks = tick + 1
    finally:
        session.close()
    return {'escapes': escapes, 'distances': distances, 'alive_ticks': alive_ticks,
            'sampler_draws_by_context': draws}, session.brain


def lane_items(items, lane, lanes):
    return [x for i, x in enumerate(items) if i % lanes == lane]


def run(arm, lane, lanes):
    config = arm_config(arm)
    out = OUT / arm
    out.mkdir(parents=True, exist_ok=True)
    brain = None
    for seed in lane_items(SEEDS, lane, lanes):
        path = out / ('seed%d.json' % seed)
        if path.exists():
            continue
        started = time.perf_counter()
        result, brain = simulate(config, seed, brain)
        result.update({'arm': arm, 'seed': seed, 'ticks': TICKS, 'config_version': config['config_version'],
                       'numba_threads': int(os.environ['NUMBA_NUM_THREADS']),
                       'wall_seconds': time.perf_counter() - started})
        path.write_text(json.dumps(result) + '\n', encoding='utf-8')
        print(arm, seed, 'escapes', len(result['escapes']), 'draws', result['sampler_draws_by_context'],
              '%.0f s' % result['wall_seconds'], flush=True)


def classify(lane, lanes):
    events = []
    for arm in ('v17', 'v18'):
        for seed in SEEDS:
            data = json.loads((OUT / arm / ('seed%d.json' % seed)).read_text(encoding='utf-8'))
            events += [(arm, seed, e['tick']) for e in data['escapes']]
    configs = {arm: arm_config(arm) for arm in ('v17', 'v18')}
    out = OUT / 'counterfactual'
    out.mkdir(parents=True, exist_ok=True)
    brain = None
    for arm, seed, tick in lane_items(sorted(events), lane, lanes):
        path = out / ('%s_seed%d_tick%d.json' % (arm, seed, tick))
        if path.exists():
            continue
        result, brain = simulate(configs[arm], seed, brain, suppress=tick, until=tick + HORIZON_TICKS + 1)
        path.write_text(json.dumps({'arm': arm, 'seed': seed, 'tick': tick,
                                    'min_horizontal_units': min(result['distances'][:HORIZON_TICKS + 1]),
                                    'horizon_ticks': HORIZON_TICKS}) + '\n', encoding='utf-8')
        print('counterfactual', arm, seed, tick, flush=True)


def category(event, counterfactual):
    if event['drive_window'] == 0.0:
        return 'A'
    if counterfactual['min_horizontal_units'] > NEAR_PASS_UNITS:
        return 'B'
    return 'C' if event['size_expansion_rad'] > event['range_expansion_rad'] else 'D'


def poisson_upper(count, minutes):
    """Exact one-sided 95 % upper bound on a Poisson rate (Garwood)."""
    return chi2.ppf(0.95, 2*(count + 1))/2/minutes


def summary():
    report = {'seeds': [SEEDS[0], SEEDS[-1]], 'ticks_per_run': TICKS, 'arms': {}}
    per_seed = {}
    for arm in ('v17', 'v18'):
        counts = {'A': 0, 'B': 0, 'C': 0, 'D': 0}
        minutes, escapes, perched, draws = 0.0, [], 0, {}
        for seed in SEEDS:
            data = json.loads((OUT / arm / ('seed%d.json' % seed)).read_text(encoding='utf-8'))
            minutes += data['alive_ticks']*DT/60
            per_seed.setdefault(seed, {})[arm] = [e['tick'] for e in data['escapes']]
            for k, v in data['sampler_draws_by_context'].items():
                draws[k] = draws.get(k, 0) + v
            for e in data['escapes']:
                cf = json.loads((OUT / 'counterfactual' / ('%s_seed%d_tick%d.json' % (arm, seed, e['tick'])))
                                .read_text(encoding='utf-8'))
                e = dict(e, seed=seed, category=category(e, cf), cf_min_horizontal_units=cf['min_horizontal_units'])
                counts[e['category']] += 1
                perched += e['lifecycle_mode'] == 'PERCHED'
                escapes.append(e)
        total = sum(counts.values())
        report['arms'][arm] = {
            'minutes': minutes, 'escapes': total, 'per_min': total/minutes,
            'upper95_per_min': poisson_upper(total, minutes), 'perched_escapes': perched,
            'categories': {k: {'count': v, 'per_min': v/minutes, 'upper95_per_min': poisson_upper(v, minutes)}
                           for k, v in counts.items()},
            'sampler_draws_by_context': draws, 'events': escapes}
    shared = sum(1 for s in per_seed.values() if s['v17'] == s['v18'])
    report['seeds_with_identical_escape_ticks'] = shared
    report['category_b_criterion_met'] = report['arms']['v18']['categories']['B']['upper95_per_min'] < 0.1
    (OUT / 'summary.json').write_text(json.dumps(report, indent=1) + '\n', encoding='utf-8')
    for arm, a in report['arms'].items():
        print(arm, '%.1f min' % a['minutes'], 'escapes', a['escapes'],
              '%.3f/min (upper %.3f)' % (a['per_min'], a['upper95_per_min']),
              {k: v['count'] for k, v in a['categories'].items()}, 'perched', a['perched_escapes'])
    print('seeds with identical escape ticks in both arms:', shared, '/', len(SEEDS))
    print('category B criterion (< 0.1/min at 95 %) met for v18:', report['category_b_criterion_met'])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=('run', 'classify', 'summary'))
    parser.add_argument('--arm', choices=('v17', 'v18'))
    parser.add_argument('--lane', type=int, default=0)
    parser.add_argument('--lanes', type=int, default=1)
    args = parser.parse_args()
    if args.mode == 'run':
        run(args.arm, args.lane, args.lanes)
    elif args.mode == 'classify':
        classify(args.lane, args.lanes)
    else:
        summary()


if __name__ == '__main__':
    main()
