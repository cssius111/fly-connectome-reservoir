"""Quantify no-loom DNp01 excursions while physically perched, with a static swatter.

Diagnosis only; nothing is modified. Voluntary takeoff ends each perch, so a single
hold cannot provide a long window. This aggregates perched ticks across many seeds and
both stages instead, which samples the same stationary no-loom condition.

    python tools/perched_noise_study.py --report artifacts/m1_8_b2b_ii/perched-noise.json
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

from game.session import Session, load_config

DT = 0.02
PARKED_POINTER = (1920.0, 388.8)


def run(config, seed, ticks, sampling, brain):
    session = Session(config, brain=brain, seed=seed, mode='evaluation')
    if not sampling:
        session.world.kinematic_sampler.explore = None
    perched_dnp01, crossings, escapes = [], 0, 0
    perched_ticks = 0
    max_theta_dot_while_perched = 0.0
    threshold = session.policy_diagnostics.get('escape_threshold')
    try:
        for _ in range(ticks):
            w = session.world
            # Attribute the tick to the state the fly was in when the tick began. The
            # launch tick itself must count: by the time it ends the lifecycle has
            # already left the stationary state, and that is the tick that crosses.
            was_perched = w.fly.alive and w.lifecycle.stationary
            session.tick(pointer=PARKED_POINTER)
            if not was_perched:
                continue
            perched_ticks += 1
            motor = session.fly_loop.last_motor
            total = 0.0 if motor is None else motor.dnp01_total
            perched_dnp01.append(total)
            if session.last_retina is not None:
                max_theta_dot_while_perched = max(max_theta_dot_while_perched,
                                                  abs(session.last_retina.theta_dot))
            if total >= threshold:
                crossings += 1
            for e in w.lifecycle.events:
                if e['type'] == 'escape_takeoff':
                    escapes += 1
    finally:
        session.close()
    a = np.asarray(perched_dnp01) if perched_dnp01 else np.zeros(0)
    return {
        'seed': seed, 'stage': 'B2b-ii' if sampling else 'B2b-i', 'ticks': ticks,
        'perched_ticks': perched_ticks,
        'max_theta_dot_while_perched': max_theta_dot_while_perched,
        'dnp01_while_perched': {
            'n': int(a.size), 'mean': float(a.mean()) if a.size else None,
            'p99': float(np.percentile(a, 99)) if a.size else None,
            'max': float(a.max()) if a.size else None},
        'threshold': threshold,
        'threshold_crossings_while_perched': crossings,
        'escape_takeoffs_while_perched': escapes,
    }, session.brain


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--report', type=Path,
                        default=ROOT/'artifacts/m1_8_b2b_ii/perched-noise.json')
    parser.add_argument('--ticks', type=int, default=6000)
    parser.add_argument('--seeds', type=int, default=10)
    args = parser.parse_args()
    config = load_config(ROOT/'game_room_config.json')
    seeds = [101, 255, 4242, 7, 33, 512, 1024, 2048, 31337, 90210][:args.seeds]
    brain, rows = None, []
    for seed in seeds:
        for sampling in (True, False):
            row, brain = run(config, seed, args.ticks, sampling, brain)
            rows.append(row)
            print(row['stage'], 'seed', seed, 'perched', row['perched_ticks'],
                  'maxDNp01', None if row['dnp01_while_perched']['max'] is None
                  else round(row['dnp01_while_perched']['max'], 4),
                  'crossings', row['threshold_crossings_while_perched'],
                  'escapes', row['escape_takeoffs_while_perched'],
                  'max|theta_dot|', round(row['max_theta_dot_while_perched'], 8), flush=True)
    summary = {}
    for stage in ('B2b-i', 'B2b-ii'):
        sel = [r for r in rows if r['stage'] == stage]
        perched = sum(r['perched_ticks'] for r in sel)
        cross = sum(r['threshold_crossings_while_perched'] for r in sel)
        esc = sum(r['escape_takeoffs_while_perched'] for r in sel)
        maxes = [r['dnp01_while_perched']['max'] for r in sel
                 if r['dnp01_while_perched']['max'] is not None]
        summary[stage] = {
            'perched_ticks_total': perched,
            'perched_seconds_total': perched*DT,
            'threshold_crossings': cross, 'escape_takeoffs': esc,
            'crossings_per_1000_perched_ticks': 1000.0*cross/perched if perched else None,
            'max_dnp01_while_perched': max(maxes) if maxes else None,
            'max_theta_dot_while_perched': max(r['max_theta_dot_while_perched'] for r in sel),
        }
    result = {'label': 'diagnosis only; nothing modified. Static swatter, no player input.',
              'calibration_no_loom_max': 1.4493308663368225,
              'calibration_threshold': 1.45,
              'calibration_margin': 1.45-1.4493308663368225,
              'per_run': rows, 'summary': summary}
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(result, indent=1)+'\n', encoding='utf-8')
    print()
    print(json.dumps(summary, indent=1))


if __name__ == '__main__':
    main()
