"""M3.8 follow-up: does the v32 candidate meet odor less often? (read-only)

Exploratory. No runtime file changes. On the six `tools/kinematics_sanity.py` seeds the M3.8
candidate (results/game/M3_8_SACCADE_ODOR.md, section 5) shows:
- a lower odor detected share of alive time (0.306 → 0.238);
- fewer odor encounters per alive minute (1.89 → 1.44);
- a lower ODOR_TRACK upwind share (0.661 → 0.471), against P6's rise from 0.529 to 0.591.
The six seeds disagree in sign: four go down, two go up. This tool repeats the measurement on
40 fresh paired seeds.

**Runs.** `kinematics_sanity.measure`, unchanged: 180 s no-player ROOM runs with the pointer
parked, on seeds 973501-973540 for both arms:
- baseline v27 at commit 7483e51;
- candidate v32 at commit ce0c745.

**Questions, fixed before the runs.**
- **Odor contact.** The pooled odor detected share of alive time and odor encounters per alive
  minute, per arm. Per-seed paired differences give a bootstrap 95 % interval and a sign count.
- **Upwind heading.** The pooled ODOR_TRACK upwind share, on a third seed set beside P6's.
- **Food.** Food touchdowns per arm, and the time to the first.
Nothing is tuned on the result.

Outputs go to artifacts/m3_8/odor_contact/ (git-ignored).

    NUMBA_NUM_THREADS=1 python tools/m3_8_odor_contact.py run --arm baseline --lane K --lanes 2   (also candidate)
    python tools/m3_8_odor_contact.py summary
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys
import time

os.environ.setdefault('NUMBA_NUM_THREADS', '1')
os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import numpy as np  # noqa: E402

import tools.kinematics_sanity as K  # noqa: E402

OUT = ROOT / 'artifacts/m3_8/odor_contact'
COMMITS = {'baseline': '7483e51', 'candidate': 'ce0c745'}
SEEDS = tuple(range(973501, 973541))
BOOTSTRAP = 10000


def run(args):
    config = K.load_arm(COMMITS[args.arm])
    out = OUT / args.arm
    out.mkdir(parents=True, exist_ok=True)
    brain = None
    for seed in SEEDS[args.lane::args.lanes]:
        path = out / ('seed%d.json' % seed)
        if path.exists():
            continue
        started = time.perf_counter()
        result, brain = K.measure(config, seed, K.TICKS, brain)
        path.write_text(json.dumps({'seed': seed, 'commit': COMMITS[args.arm],
                                    'config_version': result['config_version'], 'counts': result['counts'],
                                    'alive_minutes': result['alive_minutes'],
                                    'occupancy': result['occupancy'],
                                    'first_food_touchdown_seconds': result['first_food_touchdown_seconds']})
                        + '\n', encoding='utf-8')
        print('%s seed %d config %d %.0f s' % (args.arm, seed, result['config_version'],
                                              time.perf_counter() - started), flush=True)


def per_seed(arm):
    rows = {}
    for seed in SEEDS:
        r = json.loads((OUT / arm / ('seed%d.json' % seed)).read_text(encoding='utf-8'))
        assert r['commit'] == COMMITS[arm], 'a run comes from another commit'
        c = r['counts']
        rows[seed] = {'alive': c['alive'], 'detected': c.get('odor_detected', 0),
                      'encounters': c.get('odor_encounters', 0), 'track': c.get('odor_track_airborne', 0),
                      'up': c.get('odor_track_upwind', 0), 'food': c.get('touchdown_food', 0),
                      'first_food': r['first_food_touchdown_seconds'],
                      'occupancy': r['occupancy']}
    return rows


def pooled(rows):
    total = lambda key: sum(r[key] for r in rows.values())
    alive_min = total('alive') * K.DT / 60.0
    firsts = [r['first_food'] for r in rows.values() if r['first_food'] is not None]
    return {'alive_min': alive_min,
            'detected_share': total('detected') / total('alive'),
            'encounters_per_min': total('encounters') / alive_min,
            'odor_track_min': total('track') * K.DT / 60.0,
            'odor_track_upwind_share': total('up') / total('track') if total('track') else None,
            'food_touchdowns': total('food'),
            'runs_with_food': len(firsts),
            'first_food_median_s': float(np.median(firsts)) if firsts else None}


def paired(base, cand, metric):
    """Per-seed candidate minus baseline; bootstrap 95 % interval of the mean and a sign count."""
    d = np.array([metric(cand[s]) - metric(base[s]) for s in SEEDS])
    rng = np.random.default_rng(0)
    means = rng.choice(d, size=(BOOTSTRAP, len(d)), replace=True).mean(axis=1)
    return {'mean': float(d.mean()), 'ci95': [float(np.percentile(means, 2.5)), float(np.percentile(means, 97.5))],
            'lower': int((d < 0).sum()), 'higher': int((d > 0).sum()), 'equal': int((d == 0).sum())}


def summary(_args):
    missing = [arm for arm in COMMITS if not all((OUT / arm / ('seed%d.json' % s)).exists() for s in SEEDS)]
    if missing:
        sys.exit('incomplete: %s' % ', '.join(missing))
    base, cand = per_seed('baseline'), per_seed('candidate')
    result = {'baseline': pooled(base), 'candidate': pooled(cand), 'paired': {
        'detected_share': paired(base, cand, lambda r: r['detected'] / r['alive']),
        'encounters_per_min': paired(base, cand, lambda r: r['encounters'] / (r['alive'] * K.DT / 60.0)),
        'food_touchdowns': paired(base, cand, lambda r: r['food']),
        'odor_track_occupancy': paired(base, cand, lambda r: r['occupancy'].get('ODOR_TRACK', 0.0))}}
    for arm in COMMITS:
        r = result[arm]
        print('== %s: %.0f alive min; odor detected %.3f of alive time, %.2f encounters per min' % (
            arm, r['alive_min'], r['detected_share'], r['encounters_per_min']))
        print('   ODOR_TRACK %.1f airborne min, upwind share %.3f; %d food touchdowns, %d of %d runs, '
              'first median %s s' % (r['odor_track_min'], r['odor_track_upwind_share'], r['food_touchdowns'],
                                    r['runs_with_food'], len(SEEDS),
                                    '%.1f' % r['first_food_median_s'] if r['first_food_median_s'] else '-'))
    for key, p in result['paired'].items():
        print('paired %s: candidate - baseline %+.3f (95 %% %+.3f to %+.3f); lower in %d, higher in %d, '
              'equal in %d seeds' % (key, p['mean'], p['ci95'][0], p['ci95'][1], p['lower'], p['higher'], p['equal']))
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
