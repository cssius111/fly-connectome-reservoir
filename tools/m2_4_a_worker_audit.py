"""M2.4-A pre-freeze audit: rollout worker allocation must change throughput only.

The same fixed set of drawn TRAIN episodes (drawn by the unchanged `worker_specs` code path, fixed policy =
the accepted PyTorch BC parameters) is executed three ways:

    serial_1w        one worker, all episodes in drawing order
    balanced_7w      seven workers, longest-processing-time assignment (`balance_workers`, the M2.4-A setting)
    contiguous_7w    seven workers, the original contiguous assignment

Per episode (keyed by kind, family, level, seed) the audit compares:

- episode seed and the neural (brain-noise) reset seed actually passed to the brain;
- the scenario set-up (a hash of the initial world / attacker state right after family set-up, plus the
  attacker profile);
- the episode outcome (hit, resolution, engagement / click / resolution ticks, background seconds, perches,
  unnecessary escapes);
- trajectory hashes of the recorded observations and actions.

Any difference means worker scheduling changes scientific samples, and the protocol must not be frozen.

    python tools/m2_4_a_worker_audit.py
"""
from __future__ import annotations

import hashlib
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

from game.learning import strike_training, training, trials  # noqa: E402

AUDIT_RNG = 4242
SAMPLING_OVERRIDE = {'threat_per_worker': 3, 'background_per_worker': 1}


def _h(*arrays):
    h = hashlib.sha256()
    for a in arrays:
        h.update(np.ascontiguousarray(a).tobytes())
    return h.hexdigest()


def audit_worker_init():
    training.worker_init()
    s = training._W['session']
    brain = s.fly_loop.brain
    orig_reset = brain.reset
    training._W['audit'] = {}

    def reset(seed, *a, **k):
        training._W['audit']['brain_seed'] = int(seed)
        return orig_reset(seed, *a, **k)
    brain.reset = reset
    for cls in trials.THREAT_FAMILIES:
        orig = cls.setup

        def setup(self, session, rng, attacker_profile, _orig=orig):
            out = _orig(self, session, rng, attacker_profile)
            w = session.world
            fields = sorted((k, v) for k, v in vars(self).items() if isinstance(v, (int, float, str, bool, type(None))))
            training._W['audit']['setup'] = hashlib.sha256(json.dumps({
                'fly': [w.fly.x, w.fly.y, w.fly.vx, w.fly.vy], 'swatter': [w.swatter.x, w.swatter.y],
                'trial': fields, 'attacker': repr(trials.ATTACKERS[attacker_profile])}, default=str).encode()).hexdigest()
            return out
        cls.setup = setup


def audit_task(args):
    params, specs = args
    for k, v in params.items():
        training._W['model'].params[k] = np.array(v, dtype=np.float64)
    out = []
    for sp in specs:
        training._W['audit'] = {}
        e = strike_training._run_one(sp)
        out.append({'key': '%s:%s:%s:%d' % (e['kind'], e['name'], e['level'], e['seed']), 'seed': e['seed'],
                    'brain_seed': training._W['audit'].get('brain_seed'), 'setup': training._W['audit'].get('setup'),
                    'hit': e.get('hit'), 'seconds': e.get('seconds'), 'ticks': int(len(e['act'])),
                    'engage_index': e['engage_index'], 'click_index': e['click_index'],
                    'resolved_index': e['resolved_index'], 'task_sum': float(e['task'].sum()),
                    'perches': int(e['perch'].sum()), 'unnecessary': int(e['unnec'].sum()),
                    'escapes': int(e['escape'].sum()), 'obs_sha256': _h(e['obs']), 'act_sha256': _h(e['act']),
                    'context_sha256': _h(e['unnec'], e['perch'], e['task'], e['escape'], e['turn'], e['wall'], e['maxspd'])})
    return out


def main():
    import importlib.util
    spec = importlib.util.spec_from_file_location('m24a', ROOT / 'tools/m2_4_a_strike_ppo.py')
    A = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(A)
    S = dict(A.cfg('B_strike')['sampling'], **SAMPLING_OVERRIDE)
    dev_seeds = A.BCT.dev_seeds()
    bc_net, bc_meta = A.MT.load_bc()
    params = bc_net.to_numpy_model().params
    balanced = A.worker_specs(np.random.default_rng(AUDIT_RNG), dev_seeds, dict(S, balance_workers=True))
    contiguous = A.worker_specs(np.random.default_rng(AUDIT_RNG), dev_seeds, dict(S, balance_workers=False))
    serial = [[sp for w in contiguous for sp in w]]                     # drawing order
    assert sorted(sp for w in balanced for sp in w) == sorted(serial[0]), 'allocations draw different episodes'
    runs = {}
    for name, alloc in (('serial_1w', serial), ('balanced_7w', balanced), ('contiguous_7w', contiguous)):
        with mp.get_context('spawn').Pool(len(alloc), initializer=audit_worker_init) as pool:
            recs = [r for ch in pool.map(audit_task, [(params, w) for w in alloc]) for r in ch]
        runs[name] = {r['key']: r for r in recs}
        print(name, len(recs), 'episodes', flush=True)
    ref = runs['serial_1w']
    fields = [k for k in next(iter(ref.values())) if k != 'key']
    mism = []
    for name in ('balanced_7w', 'contiguous_7w'):
        if set(runs[name]) != set(ref):
            mism.append({'run': name, 'problem': 'different episode set'})
            continue
        for k, r in ref.items():
            for f in fields:
                if runs[name][k][f] != r[f]:
                    mism.append({'run': name, 'episode': k, 'field': f, 'serial': r[f], 'parallel': runs[name][k][f]})
    fam = {}
    for r in ref.values():
        fam[r['key'].split(':')[1]] = fam.get(r['key'].split(':')[1], 0) + 1
    res = {'label': 'M2.4-A worker-allocation audit (TRAIN seeds only; pre-freeze)',
           'policy': 'accepted PyTorch BC parameters (state_dict %s)' % bc_meta['checkpoint_state_dict_sha256'],
           'draw': {'rng': AUDIT_RNG, 'sampling': S, 'episodes': len(ref), 'families': fam},
           'worker_loads': {'balanced_7w': [len(w) for w in balanced], 'contiguous_7w': [len(w) for w in contiguous]},
           'compared_fields': fields, 'mismatches': mism, 'identical': not mism,
           'brain_seed_is_seed_plus_977': all(r['brain_seed'] == r['seed'] + 977 for r in ref.values()),
           'episodes': sorted(ref.values(), key=lambda r: r['key'])}
    track = ROOT / 'game/learning/m2_4_a'
    track.mkdir(parents=True, exist_ok=True)
    (track / 'worker_allocation_audit.json').write_text(json.dumps(res, indent=1, default=float) + '\n', encoding='utf-8')
    print('identical' if not mism else 'MISMATCH (%d fields)' % len(mism), 'families', fam,
          'brain seed = seed + 977:', res['brain_seed_is_seed_plus_977'])
    return 0 if not mism else 1


if __name__ == '__main__':
    raise SystemExit(main())
