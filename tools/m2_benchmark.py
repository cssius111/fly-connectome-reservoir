"""M2.0 frozen baseline benchmark (EVAL only; no learning, no parameter updates).

Runs every benchmark policy on every frozen scenario and EVAL seed through an unchanged
Session, then aggregates metrics, reward terms and anti-cheating diagnostics.

    python tools/m2_benchmark.py run --worker K --workers 7     (NUMBA_NUM_THREADS=1)
    python tools/m2_benchmark.py report

Outputs: artifacts/m2_0/benchmark/ (git-ignored): episodes_<policy>.jsonl, report.json,
manifest.json.
"""
from __future__ import annotations

import argparse
import hashlib
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

from game.learning import runmode, runner  # noqa: E402
from game.learning.metrics import ANTI_CHEAT, aggregate, anti_cheat  # noqa: E402
from game.learning.reward import RewardSpec  # noqa: E402
from game.learning.scenarios import SCENARIOS  # noqa: E402

OUT = ROOT / 'artifacts/m2_0/benchmark'
SCEN = {cls.name: cls for cls in SCENARIOS}


def jobs():
    return [(p, s['scenario'], seed) for p in runner.BENCHMARK_POLICIES for s in runner.SUITE for seed in s['eval_seeds']]


def run(worker, workers):
    if os.environ['NUMBA_NUM_THREADS'] != '1':
        raise SystemExit('the benchmark requires NUMBA_NUM_THREADS=1 (determinism)')
    OUT.mkdir(parents=True, exist_ok=True)
    config = runner.load_config()
    mine = [j for i, j in enumerate(jobs()) if i % workers == worker]
    sessions = {}
    done = set()
    part = OUT / ('part_%d.jsonl' % worker)
    if part.exists():
        for l in part.open(encoding='utf-8'):
            r = json.loads(l)
            done.add((r['policy'], r['scenario'], r['seed']))
    t0 = time.time()
    with part.open('a', encoding='utf-8') as fh:
        for k, (pol, scen, seed) in enumerate(mine):
            if (pol, scen, seed) in done:
                continue
            if pol not in sessions:
                policy = runner.make_policy(pol, config, mode=runmode.EVAL)
                sessions[pol] = runner.make_session(policy, config)
            with runmode.EvalGuard(None):
                r = runner.run_episode(sessions[pol], SCEN[scen], seed, runmode.EVAL, RewardSpec())
            r['policy'] = pol
            fh.write(json.dumps(r) + '\n')
            fh.flush()
            if k % 10 == 0:
                print('worker %d: %d/%d (%.0f s)' % (worker, k, len(mine), time.time() - t0), flush=True)
    print('worker %d done' % worker, flush=True)


def report():
    eps = [json.loads(l) for f in sorted(OUT.glob('part_*.jsonl')) for l in f.open(encoding='utf-8')]
    expected = set(jobs())
    got = {(e['policy'], e['scenario'], e['seed']) for e in eps}
    if got != expected:
        raise SystemExit('incomplete benchmark: %d of %d episodes' % (len(got & expected), len(expected)))
    by = {}
    for e in eps:
        by.setdefault(e['policy'], []).append(e)
    res = {'suite_version': runner.SUITE_VERSION, 'suite_sha256': runner.suite_hash(), 'policies': {}}
    for pol, E in by.items():
        pooled = aggregate([e['metrics'] for e in E])
        per = {}
        for s in runner.SUITE:
            Es = [e for e in E if e['scenario'] == s['scenario']]
            per[s['scenario']] = aggregate([e['metrics'] for e in Es])
            per[s['scenario']]['reward_mean'] = {k: float(np.mean([e['reward'][k] for e in Es])) for k in Es[0]['reward']}
            if s['scenario'] == 'perched_strike':
                reached = [e for e in Es if e['metrics']['scenario']['perch_reached']]
                per[s['scenario']]['perch_reached'] = len(reached)
                per[s['scenario']]['survival_when_exposed'] = (float(np.mean([not e['metrics']['died'] for e in reached]))
                                                               if reached else None)
            if s['scenario'] == 'wall_edge_strike':
                per[s['scenario']]['placements'] = dict(zip(*np.unique([e['metrics']['scenario']['placement'] for e in Es],
                                                                       return_counts=True)))
        exposed = [e for e in E if not (e['scenario'] == 'perched_strike' and not e['metrics']['scenario']['perch_reached'])]
        pooled['survival_fraction_exposed_only'] = float(np.mean([not e['metrics']['died'] for e in exposed])) if exposed else None
        pooled['perched_scenario_not_reached'] = sum(1 for e in E if e['scenario'] == 'perched_strike'
                                                     and not e['metrics']['scenario']['perch_reached'])
        res['policies'][pol] = {'pooled': pooled, 'per_scenario': per,
                                'reward_mean_total': float(np.mean([e['reward']['total'] for e in E])),
                                'trajectory_hashes': hashlib.sha256(''.join(sorted(e['trajectory_sha256'] for e in E)).encode()).hexdigest()}
    base = res['policies']['baseline_n4b1c']['pooled']
    for pol, v in res['policies'].items():
        v['anti_cheat_flags'] = anti_cheat(v['pooled'], base)
    res['anti_cheat_thresholds'] = ANTI_CHEAT
    res = json.loads(json.dumps(res, default=lambda o: o.item() if hasattr(o, 'item') else str(o)))
    (OUT / 'report.json').write_text(json.dumps(res, indent=1) + '\n', encoding='utf-8')
    config = runner.load_config()
    man = runner.run_manifest('m2.0-baseline-benchmark', runner.BENCHMARK_POLICIES,
                              [s for x in runner.SUITE for s in x['eval_seeds']], config, RewardSpec(),
                              metrics={p: v['pooled'] for p, v in res['policies'].items()},
                              extra={'report_sha256': hashlib.sha256((OUT / 'report.json').read_bytes()).hexdigest(),
                                     'episodes': len(eps)})
    (OUT / 'manifest.json').write_text(json.dumps(man, indent=1, default=str) + '\n', encoding='utf-8')
    for pol, v in res['policies'].items():
        p = v['pooled']
        print('%-20s surv %.2f hit/strike %s esc/min %.1f unnec/min %.1f wall %.3f near %.2f maxspd %.3f slow %.3f '
              'turn %.2f sacc/min %.1f perch/min %s entropy %.2f reward %.2f flags %s' % (
                  pol, p['survival_fraction'], None if p['hit_rate_per_strike'] is None else round(p['hit_rate_per_strike'], 3),
                  p['escapes_per_min'], p['unnecessary_escapes_per_min'], p['wall_contact_fraction'], p['near_wall_fraction'],
                  p['max_speed_fraction'], p['airborne_slow_fraction'], p['turn_active_fraction'], p['saccades_per_min'],
                  None if p['perches_per_min'] is None else round(p['perches_per_min'], 2), p['category_entropy_bits'],
                  v['reward_mean_total'], [k for k, f in v['anti_cheat_flags'].items() if f]))


if __name__ == '__main__':
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('mode', choices=('run', 'report'))
    ap.add_argument('--worker', type=int, default=0)
    ap.add_argument('--workers', type=int, default=1)
    a = ap.parse_args()
    run(a.worker, a.workers) if a.mode == 'run' else report()
