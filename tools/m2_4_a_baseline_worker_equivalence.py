"""Semantic equivalence of the amended baseline pool worker (TRAIN seeds only; never EVAL).

OLD = `_baseline_worker_init` / `baseline_task` in tools/m2_2_train.py (used for all baseline records up to M2.3).
NEW = `worker_init` / `baseline_task` in game/learning/baseline_eval.py (bfd5c42; used by the M2.4-A confirmation
stage and the M2-EVAL-v3 runner).

Part A  in-process, instrumented, OLD vs NEW on a fixed TRAIN set (all 12 threat groups x 2 seeds + 1 episode per
        background family) for baseline_n4b1c, no_escape and fixed_maneuver. Per episode it compares the full
        returned benchmark record (seed, hit, event times, exposure fields, lifecycle / movement metrics, trajectory
        hash) and, from instrumentation, the neural reset seed passed to FlyLoop.reset, a hash of the scenario /
        attacker set-up, a hash of every brain-loop input (Retina + MotionState) and a hash of every Action.
Part B  NEW through a real Windows spawn pool (7 workers) on the same set; records must equal Part A.
Part C  NEW through a spawn pool on the M2.2 TRAIN-VAL set; records must equal the stored OLD-worker records in
        artifacts/m2_2/val/baselines.json (generated 2026-09-26 by the M2.2 pipeline; trials / training / runner /
        policies code unchanged since 63dbeb6).

    python tools/m2_4_a_baseline_worker_equivalence.py
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

import numpy as np  # noqa: E402

from game.learning import baseline_eval, runmode, trials  # noqa: E402

POLICIES = ('baseline_n4b1c', 'no_escape', 'fixed_maneuver')
SET_RNG = 4343
WORKERS = 7


def _load(name, alias):
    spec = importlib.util.spec_from_file_location(alias, ROOT / ('tools/%s.py' % name))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _sha(obj):
    return hashlib.sha256(json.dumps(obj, sort_keys=True, default=float).encode()).hexdigest()


def fixed_set(exclude):
    rng = np.random.default_rng(SET_RNG)

    def seed():
        while True:
            s = int(rng.integers(20_000_000, 25_000_000))
            if s not in exclude:
                exclude.add(s)
                return s
    fams = [f.name for f in trials.THREAT_FAMILIES]
    bgs = [c.name for c in trials.BACKGROUND_FAMILIES]
    out = [('threat', f, a, seed()) for f in fams for a in trials.ATTACKERS for _ in range(2)]
    out += [('background', b, None, seed()) for b in bgs]
    for *_, s in out:
        runmode.TRAIN.check_seed(s)
    return out


class Instrument:
    """Class-level hooks shared by OLD and NEW (both call the same trials / Session code)."""

    def __init__(self):
        from game.fly import FlyLoop
        self.cur = None
        inst = self
        orig_reset, orig_step = FlyLoop.reset, FlyLoop.step

        def reset(self_, seed):
            if inst.cur is not None:
                inst.cur['neural_reset_seed'] = int(seed)
            return orig_reset(self_, seed)

        def step(self_, *a, **k):
            act = orig_step(self_, *a, **k)
            if inst.cur is not None:
                inst.cur['_in'].update(repr((a, sorted(k.items()))).encode())
                inst.cur['_act'].update(repr(act).encode())
                inst.cur['steps'] += 1
            return act
        FlyLoop.reset, FlyLoop.step = reset, step
        for cls in trials.THREAT_FAMILIES:
            orig = cls.setup

            def setup(self_, session, rng, attacker_profile, _orig=orig):
                out = _orig(self_, session, rng, attacker_profile)
                w = session.world
                fields = sorted((k, v) for k, v in vars(self_).items() if isinstance(v, (int, float, str, bool, type(None))))
                inst.cur['setup_sha256'] = _sha({'fly': [w.fly.x, w.fly.y, w.fly.vx, w.fly.vy],
                                                 'swatter': [w.swatter.x, w.swatter.y], 'trial': fields,
                                                 'attacker': repr(trials.ATTACKERS[attacker_profile])})
                return out
            cls.setup = setup

    def run(self, task, name, specs):
        recs, inst = [], []
        for sp in specs:
            self.cur = {'neural_reset_seed': None, 'setup_sha256': None, 'steps': 0,
                        '_in': hashlib.sha256(), '_act': hashlib.sha256()}
            r = task((name, [sp], 'TRAIN'))[0]
            c = self.cur
            inst.append({'neural_reset_seed': c['neural_reset_seed'], 'setup_sha256': c['setup_sha256'],
                         'brain_loop_steps': c['steps'], 'brain_input_sha256': c['_in'].hexdigest(),
                         'action_sha256': c['_act'].hexdigest()})
            recs.append(r)
        self.cur = None
        return recs, inst


def compare(a, b, label):
    diffs = []
    if len(a) != len(b):
        return [{'where': label, 'problem': 'length %d vs %d' % (len(a), len(b))}]
    for i, (x, y) in enumerate(zip(a, b)):
        jx, jy = json.dumps(x, sort_keys=True, default=float), json.dumps(y, sort_keys=True, default=float)
        if jx != jy:
            keys = sorted(set(x) | set(y))
            diffs.append({'where': label, 'episode': i, 'seed': x.get('seed'),
                          'fields': [k for k in keys if json.dumps(x.get(k), sort_keys=True, default=float)
                                     != json.dumps(y.get(k), sort_keys=True, default=float)]})
    return diffs


def pool_run(specs, names):
    chunks = [specs[i::WORKERS] for i in range(WORKERS)]
    out = {}
    with mp.get_context('spawn').Pool(WORKERS, initializer=baseline_eval.worker_init) as pool:
        for n in names:
            parts = pool.map(baseline_eval.baseline_task, [(n, c, 'TRAIN') for c in chunks])
            by_seed = {(r['kind'], r['seed']): r for ch in parts for r in ch}
            out[n] = [by_seed[(k, s)] for k, _, _, s in specs]
    return out


def main():
    m22 = _load('m2_2_train', 'm2_2_train_equivalence_old')
    bct = _load('m2_3_bc_ppo', 'm2_3_bc_ppo_equivalence')
    exclude = set(bct.dev_seeds()) | {s for v in m22.split()['train_val'].values() for s in v}
    specs = fixed_set(exclude)
    res = {'label': 'M2.4-A baseline pool worker amendment: semantic-equivalence evidence (TRAIN only)',
           'old_worker': 'tools/m2_2_train.py::_baseline_worker_init / baseline_task',
           'old_file_sha256': hashlib.sha256((ROOT / 'tools/m2_2_train.py').read_bytes()).hexdigest(),
           'new_worker': 'game/learning/baseline_eval.py::worker_init / baseline_task',
           'new_file_sha256': hashlib.sha256((ROOT / 'game/learning/baseline_eval.py').read_bytes()).hexdigest(),
           'policies': list(POLICIES), 'fixed_set_rng': SET_RNG, 'fixed_set': specs}
    # Part A
    ins = Instrument()
    m22._baseline_worker_init()
    baseline_eval.worker_init()
    diffs, part_a = [], {}
    for n in POLICIES:
        ro, io = ins.run(m22.baseline_task, n, specs)
        rn, inn = ins.run(baseline_eval.baseline_task, n, specs)
        diffs += compare(ro, rn, 'A:%s:record' % n) + compare(io, inn, 'A:%s:instrumentation' % n)
        part_a[n] = rn
        res.setdefault('part_a', {})[n] = {'episodes': len(rn), 'records_sha256': _sha(rn),
                                           'instrumentation_sha256': _sha(inn),
                                           'neural_seed_is_seed_plus_977': all(
                                               i['neural_reset_seed'] == s + 977 for i, (*_, s) in zip(inn, specs)),
                                           'setups_recorded': sum(i['setup_sha256'] is not None for i in inn),
                                           'brain_loop_steps': sum(i['brain_loop_steps'] for i in inn),
                                           'hits': sum(bool(r.get('hit')) for r in rn if r['kind'] == 'threat')}
        print('A', n, len(rn), 'diffs so far', len(diffs), flush=True)
    res['part_a_differences'] = diffs
    # Part B
    pb = pool_run(specs, POLICIES)
    db = []
    for n in POLICIES:
        db += compare(part_a[n], pb[n], 'B:%s' % n)
    res['part_b'] = {'spawn_pool_workers': WORKERS, 'start_method': 'spawn', 'differences': db,
                     'records_sha256': {n: _sha(pb[n]) for n in POLICIES}}
    print('B diffs', len(db), flush=True)
    # Part C
    old = json.loads((ROOT / 'artifacts/m2_2/val/baselines.json').read_text(encoding='utf-8'))
    vs = m22.val_specs()
    pc = pool_run(vs, POLICIES)
    dc = []
    for n in POLICIES:
        want = {(r['kind'], r['seed']): r for r in old[n]}
        dc += compare([want[(k, s)] for k, _, _, s in vs], pc[n], 'C:%s' % n)
    res['part_c'] = {'set': 'M2.2 TRAIN-VAL (96 threat + 24 background)', 'episodes_per_policy': len(vs),
                     'old_records_file_sha256': hashlib.sha256(
                         (ROOT / 'artifacts/m2_2/val/baselines.json').read_bytes()).hexdigest(),
                     'differences': dc}
    print('C diffs', len(dc), flush=True)
    res['identical'] = not (diffs or db or dc)
    out = ROOT / 'game/learning/m2_4_a/baseline_worker_equivalence.json'
    out.write_text(json.dumps(res, indent=1, default=float) + '\n', encoding='utf-8')
    print('IDENTICAL' if res['identical'] else 'DIFFERENT', hashlib.sha256(out.read_bytes()).hexdigest())
    return 0 if res['identical'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
