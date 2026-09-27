"""M2-EVAL-v3: fresh one-shot holdout for M2.4 learned candidates (preregistered in M2.4-R0).

    python tools/m2_eval_v3.py freeze      (write + hash the seed manifest; runs NOTHING)
    python tools/m2_eval_v3.py check       (verify manifest, benchmark / attacker / code hashes)

The run is executed only by `tools/m2_4_a_strike_ppo.py eval-final`, which calls `run_once` after
the single M2.4-A candidate has been frozen and pushed. `run_once` refuses to run twice.

Design (unchanged M2.1 benchmark v2 philosophy):
- threat groups: the 12 M2.1 groups (4 threat families x 3 attacker levels, M2.1 order), frozen
  attacker distributions; seeds 3_900_000 + 1000 x g + k, k = 1..40;
- background groups: the 4 M2.1 background families (g = 12..15); seeds 3_900_000 + 1000 x g + k,
  k = 1..20;
- 480 threat trials + 80 background episodes per policy; same metrics, constraints and anti-cheat
  flags (M2.1 `evaluate`, anti-cheat reference = accepted N4B1C on the same v3 episodes).
Seeds lie inside the registered EVAL range (3e6, 4e6) and are disjoint from EVAL v1 (3.1e6-3.7e6)
and v2 (3_800_001-3_815_020), including brain-noise seeds (seed + 977).
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import multiprocessing as mp
import os
from pathlib import Path
import sys

os.environ.setdefault('NUMBA_NUM_THREADS', '1')
os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from game.learning import runmode, trials  # noqa: E402

MANIFEST = ROOT / 'game/learning/m2_eval_v3.json'
OUT = ROOT / 'artifacts/m2_eval_v3'
FROZEN_V2 = ROOT / 'game/learning/benchmark_v2_frozen.json'
THREAT_PER_GROUP, BACKGROUND_PER_GROUP, BASE = 40, 20, 3_900_000
WORKERS = 7


def _load(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / ('tools/%s.py' % name))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def groups():
    m21 = _load('m2_1_benchmark')
    return ['threat:%s:%s' % g for g in m21.THREAT_GROUPS] + ['background:%s' % b for b in m21.BG_GROUPS]


def seed_manifest():
    out = {}
    for g_i, g in enumerate(groups()):
        n = THREAT_PER_GROUP if g.startswith('threat') else BACKGROUND_PER_GROUP
        out[g] = [BASE + 1000 * g_i + k for k in range(1, n + 1)]
    flat = [s for v in out.values() for s in v]
    assert len(flat) == len(set(flat))
    for s in flat:
        runmode.EVAL.check_seed(s)
    return out


def definition():
    fz = json.loads(FROZEN_V2.read_text(encoding='utf-8'))
    seeds = seed_manifest()
    return {'name': 'M2-EVAL-v3', 'seeds': seeds, 'n_threat': sum(len(v) for g, v in seeds.items() if g.startswith('threat')),
            'n_background': sum(len(v) for g, v in seeds.items() if g.startswith('background')),
            'benchmark_definition_sha256': fz['benchmark_definition_sha256'],
            'attacker_distribution_sha256': fz['attacker_distribution_sha256'],
            'reward_v2_sha256': fz['reward_v2_sha256'],
            'constraints_sha256': hashlib.sha256(json.dumps(fz['constraints'], sort_keys=True).encode()).hexdigest(),
            'benchmark_v2_frozen_file_sha256': hashlib.sha256(FROZEN_V2.read_bytes()).hexdigest(),
            'trials_code_sha256': hashlib.sha256((ROOT / 'game/learning/trials.py').read_bytes()).hexdigest(),
            'generation_code_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            'seed_manifest_sha256': hashlib.sha256(json.dumps(seeds, sort_keys=True).encode()).hexdigest(),
            'disjoint_from': ['EVAL v1 3.1e6-3.7e6', 'EVAL v2 3_800_001-3_815_020', 'all TRAIN seeds (20e6-30e6)',
                              'brain-noise seeds (seed + 977) of v1 / v2'],
            'status': 'frozen; NOT run. Run exactly once, after the M2.4-A candidate freeze is pushed.'}


def freeze():
    if MANIFEST.exists():
        raise SystemExit('M2-EVAL-v3 already frozen')
    d = definition()
    MANIFEST.write_text(json.dumps(d, indent=1) + '\n', encoding='utf-8')
    print('frozen M2-EVAL-v3', hashlib.sha256(MANIFEST.read_bytes()).hexdigest(), d['n_threat'], d['n_background'])


def check():
    d = json.loads(MANIFEST.read_text(encoding='utf-8'))
    now = definition()
    for k in ('seed_manifest_sha256', 'benchmark_definition_sha256', 'attacker_distribution_sha256', 'reward_v2_sha256',
              'constraints_sha256', 'trials_code_sha256'):
        if d[k] != now[k]:
            raise SystemExit('M2-EVAL-v3 mismatch: %s' % k)
    return d


def specs():
    d = check()
    return [(g.split(':')[0], g.split(':')[1], g.split(':')[2] if g.startswith('threat') else None, s)
            for g, lst in d['seeds'].items() for s in lst]


def run_once(candidate_params, extra_mlp=None, baselines=('baseline_n4b1c', 'no_escape', 'fixed_maneuver')):
    """Candidate (+ optional extra frozen MLPs) and baselines on v3; refuses a second run."""
    from game.learning import training
    OUT.mkdir(parents=True, exist_ok=True)
    done = OUT / 'records.json'
    if done.exists():
        raise SystemExit('M2-EVAL-v3 has already been run')
    m22 = _load('m2_2_train')
    sp = specs()
    chunks = [sp[i::WORKERS] for i in range(WORKERS)]
    recs = {}
    with mp.get_context('spawn').Pool(WORKERS, initializer=training.worker_init) as pool:
        for name, params in [('candidate', candidate_params)] + list((extra_mlp or {}).items()):
            recs[name] = [r for ch in pool.map(training.eval_task, [(params, c, 'EVAL') for c in chunks]) for r in ch]
            print('v3', name, len(recs[name]), flush=True)
    with mp.get_context('spawn').Pool(WORKERS, initializer=m22._baseline_worker_init) as pool:
        for name in baselines:
            recs[name] = [r for ch in pool.map(m22.baseline_task, [(name, c, 'EVAL') for c in chunks]) for r in ch]
            print('v3', name, len(recs[name]), flush=True)
    done.write_text(json.dumps(recs, default=float) + '\n', encoding='utf-8')
    return recs


if __name__ == '__main__':
    mode = sys.argv[1] if len(sys.argv) > 1 else 'check'
    if mode == 'freeze':
        freeze()
    elif mode == 'check':
        print(json.dumps({k: v for k, v in check().items() if k != 'seeds'}, indent=1))
    else:
        raise SystemExit('unknown mode (the run is only reachable through the M2.4-A eval-final step)')
