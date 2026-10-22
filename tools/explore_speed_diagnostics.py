"""M1.8-B2b-ii diagnostics: EXPLORE sampling distribution and long closed-loop ROOM runs.

Diagnostic only. This tool changes nothing and must never be used to tune toward hit
rate, survival, escape rate or player difficulty: no player acts in any run here.

    python tools/explore_speed_diagnostics.py --report artifacts/m1_8_b2b_ii/diagnostics.json
"""
import argparse
import json
import math
import os
from pathlib import Path
import statistics
import sys

os.environ.setdefault('NUMBA_NUM_THREADS', '4')
os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import numpy as np

from game.ecology import EcologicalCommand
from game.kinematics import KinematicSampler
from game.session import Session, load_config

DT = 0.02


def describe(values):
    if not values:
        return {'n': 0}
    a = np.asarray(values, dtype=float)
    q = np.percentile(a, [5, 25, 50, 75, 95])
    return {'n': int(a.size), 'min': float(a.min()), 'max': float(a.max()),
            'mean': float(a.mean()), 'median': float(q[2]), 'sd': float(a.std(ddof=1)) if a.size > 1 else 0.0,
            'p05': float(q[0]), 'p25': float(q[1]), 'p75': float(q[3]), 'p95': float(q[4]),
            'iqr': float(q[3]-q[1])}


def offline_distribution(config, samples=200000, seed=20260921):
    """Long seeded draw sequence straight from the sampler."""
    spec = config['kinematics']['explore_speed_bl_s']
    sampler = KinematicSampler(seed, spec)
    explore = EcologicalCommand('EXPLORE', 6.0, 0.0, 1.0)
    transit = EcologicalCommand('TRANSIT', 11.0, 0.0, 0.45)
    drawn = []
    for _ in range(samples):
        drawn.append(sampler.target_speed_bl_s(explore, False))
        sampler.target_speed_bl_s(transit, False)     # close the episode
    repeat = KinematicSampler(seed, spec)
    first = [repeat.target_speed_bl_s(explore, False) or 0.0
             for _ in range(1) ]
    low, high = spec['min_bl_s'], spec['max_bl_s']
    edges = np.linspace(low, high, 13)
    hist, _ = np.histogram(drawn, bins=edges)
    # The accepted pre-B2b-ii target: a deterministic 8 s sinusoid over the same band.
    t = np.linspace(0, 8, 200001)
    legacy = low + (high-low)*(0.5 + 0.5*np.sin(2*math.pi*t/8))
    legacy_hist, _ = np.histogram(legacy, bins=edges)
    return {'sampler_draws': sampler.draws, 'samples': samples,
            'seed_reproducible': first[0] == drawn[0],
            'distribution': describe(drawn),
            'accepted_legacy_sinusoid_time_density': describe(list(legacy)),
            'quantile_table_bl_s': {str(round(p)): float(np.percentile(drawn, p))
                                    for p in (1, 5, 10, 25, 50, 75, 90, 95, 99)},
            'histogram_bin_edges_bl_s': [float(e) for e in edges],
            'histogram_fraction_sampled': [float(v) for v in hist/hist.sum()],
            'histogram_fraction_legacy': [float(v) for v in legacy_hist/legacy_hist.sum()]}


def closed_loop(config, seed, ticks, brain=None):
    """A long ROOM run with no player: the pointer is parked far from the fly."""
    session = Session(config, brain=brain, seed=seed, mode='evaluation')
    body = session.world.body_length
    alive_speed_explore, requested_explore, accel, states = [], [], [], {}
    wall_ticks = 0
    prev_speed = None
    saccade_amplitudes, saccade_intervals = [], []
    last_saccade_tick, prev_kind = None, 'NONE'
    events = {}
    try:
        for tick in range(ticks):
            session.tick(pointer=(1920, 388.8))
            w = session.world
            if not w.fly.alive:
                prev_speed = None
                continue
            state = session.ecology.state
            states[state] = states.get(state, 0) + 1
            speed = w.body_lengths_per_second
            if prev_speed is not None:
                accel.append((speed-prev_speed)/DT)
            prev_speed = speed
            if state == 'EXPLORE' and not w.lifecycle.stationary:
                alive_speed_explore.append(speed)
                requested_explore.append(w.applied_target_speed/body)
            if w.wall_cue.proximity > 0.45:
                wall_ticks += 1
            kind = w.saccades.kind
            if kind != 'NONE' and prev_kind == 'NONE':
                if last_saccade_tick is not None:
                    saccade_intervals.append((tick-last_saccade_tick)*DT)
                last_saccade_tick = tick
                saccade_amplitudes.append(abs(w.saccades.remaining))
            prev_kind = kind
            for event in w.lifecycle.events:
                events[event['type']] = events.get(event['type'], 0) + 1
        alive = sum(states.values())
        result = {'seed': seed, 'ticks': ticks, 'alive_ticks': alive,
                  'sampler_draws': session.world.kinematic_sampler.draws,
                  'actual_speed_bl_s_while_explore': describe(alive_speed_explore),
                  'requested_target_bl_s_while_explore': describe(requested_explore),
                  'acceleration_bl_s2': describe(accel),
                  'wall_time_fraction': wall_ticks/alive if alive else None,
                  'saccade_interval_seconds': describe(saccade_intervals),
                  'saccade_amplitude_remaining': describe(saccade_amplitudes),
                  'ecology_state_occupancy': {k: v/alive for k, v in sorted(states.items())} if alive else {},
                  'lifecycle_events': dict(sorted(events.items()))}
    finally:
        session.close()
    return result, session.brain


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--report', type=Path,
                        default=ROOT/'artifacts/m1_8_b2b_ii/diagnostics.json')
    parser.add_argument('--ticks', type=int, default=9000)   # 180 simulated seconds
    args = parser.parse_args()
    config = load_config(ROOT/'game_room_config.json')
    offline = offline_distribution(config)
    print('offline distribution:', json.dumps(offline['distribution'], indent=1))
    runs, brain = [], None
    for seed in (101, 255, 4242):
        run, brain = closed_loop(config, seed, args.ticks, brain)
        runs.append(run)
        print('seed', seed, 'draws', run['sampler_draws'],
              'explore actual', round(run['actual_speed_bl_s_while_explore'].get('mean', 0), 3),
              'events', run['lifecycle_events'], flush=True)
    result = {'label': 'simulator diagnostics; no player acts and no difficulty metric is used',
              'accepted_envelope_bl_s': config['ecology']['speed_bl_s']['EXPLORE'],
              'specification': config['kinematics']['explore_speed_bl_s'],
              'offline': offline, 'closed_loop': runs}
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(result, indent=1)+'\n', encoding='utf-8')
    print('written', args.report)


if __name__ == '__main__':
    main()
