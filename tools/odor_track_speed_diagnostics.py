"""M1.8-B2b-iii diagnostics: ODOR_TRACK sampling distribution and closed-loop ROOM runs.

Diagnostic only. This tool changes nothing and must never be used to tune toward hit
rate, survival, escape rate or player difficulty: no player acts in any run here.

    python tools/odor_track_speed_diagnostics.py --report artifacts/m1_8_b2b_iii/diagnostics.json
"""
import argparse
import json
import math
import os
from pathlib import Path
import sys

os.environ.setdefault('NUMBA_NUM_THREADS', '4')
os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import numpy as np

from game.ecology import EcologicalCommand
from game.kinematics import KinematicSampler
from game.session import Session, load_config
from tools.explore_speed_diagnostics import describe

DT = 0.02
PARKED_POINTER = (1920, 388.8)


def offline_distribution(config, samples=200000, seed=20261020):
    """Long seeded draw sequence straight from the sampler's ODOR_TRACK stream."""
    spec = config['kinematics']['odor_track_speed_bl_s']
    sampler = KinematicSampler(seed, None, spec)
    track = EcologicalCommand('ODOR_TRACK', 11.0, 0.0, 0.35)
    search = EcologicalCommand('ODOR_SEARCH', 5.5, 0.0, 1.35)
    drawn = []
    for _ in range(samples):
        drawn.append(sampler.target_speed_bl_s(track, False))
        sampler.target_speed_bl_s(search, False)     # close the episode
    repeat = KinematicSampler(seed, None, spec).target_speed_bl_s(track, False)
    low, high = spec['min_bl_s'], spec['max_bl_s']
    edges = np.linspace(low, high, 13)
    hist, _ = np.histogram(drawn, bins=edges)
    # The accepted pre-B2b-iii target: a deterministic 8 s sinusoid over the same band.
    t = np.linspace(0, 8, 200001)
    legacy = low + (high-low)*(0.5 + 0.5*np.sin(2*math.pi*t/8))
    legacy_hist, _ = np.histogram(legacy, bins=edges)
    return {'sampler_draws': sampler.draws, 'samples': samples,
            'explore_stream_untouched': sampler.rng.bit_generator.state == sampler.initial_state,
            'seed_reproducible': repeat == drawn[0],
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
    actual, requested, states, events = {}, {}, {}, {}
    saccade_intervals, last_saccade_tick, prev_kind = [], None, 'NONE'
    try:
        for tick in range(ticks):
            session.tick(pointer=PARKED_POINTER)
            w = session.world
            if not w.fly.alive:
                continue
            state = session.ecology.state
            states[state] = states.get(state, 0) + 1
            if state in ('EXPLORE', 'ODOR_TRACK') and not w.lifecycle.stationary \
                    and w.kinematic_profile.context == 'ecology_' + state.lower():
                actual.setdefault(state, []).append(w.body_lengths_per_second)
                requested.setdefault(state, []).append(w.applied_target_speed/body)
            kind = w.saccades.kind
            if kind != 'NONE' and prev_kind == 'NONE':
                if last_saccade_tick is not None:
                    saccade_intervals.append((tick-last_saccade_tick)*DT)
                last_saccade_tick = tick
            prev_kind = kind
            for event in w.lifecycle.events:
                events[event['type']] = events.get(event['type'], 0) + 1
        alive = sum(states.values())
        sampler = session.world.kinematic_sampler
        result = {'seed': seed, 'ticks': ticks, 'alive_ticks': alive,
                  'sampler_draws_by_context': dict(sorted(sampler.draws_by_context.items())),
                  'actual_speed_bl_s': {k: describe(v) for k, v in sorted(actual.items())},
                  'requested_target_bl_s': {k: describe(v) for k, v in sorted(requested.items())},
                  'saccade_interval_seconds': describe(saccade_intervals),
                  'ecology_state_occupancy': {k: v/alive for k, v in sorted(states.items())} if alive else {},
                  'lifecycle_events': dict(sorted(events.items()))}
    finally:
        session.close()
    return result, session.brain


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--report', type=Path,
                        default=ROOT/'artifacts/m1_8_b2b_iii/diagnostics.json')
    parser.add_argument('--ticks', type=int, default=9000)   # 180 simulated seconds
    args = parser.parse_args()
    config = load_config(ROOT/'game_room_config.json')
    offline = offline_distribution(config)
    print('offline distribution:', json.dumps(offline['distribution'], indent=1))
    runs, brain = [], None
    for seed in (101, 255, 4242):    # the B2b-ii closed-loop diagnostic seeds
        run, brain = closed_loop(config, seed, args.ticks, brain)
        runs.append(run)
        track = run['actual_speed_bl_s'].get('ODOR_TRACK', {})
        print('seed', seed, 'draws', run['sampler_draws_by_context'],
              'odor-track actual mean', round(track.get('mean', 0.0), 3),
              'events', run['lifecycle_events'], flush=True)
    result = {'label': 'simulator diagnostics; no player acts and no difficulty metric is used',
              'accepted_envelope_bl_s': config['ecology']['speed_bl_s']['ODOR_TRACK'],
              'specification': config['kinematics']['odor_track_speed_bl_s'],
              'offline': offline, 'closed_loop': runs}
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(result, indent=1)+'\n', encoding='utf-8')
    print('written', args.report)


if __name__ == '__main__':
    main()
