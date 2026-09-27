"""Pool workers for fixed baseline policies on benchmark-v2 trials (evaluation-side code; never part of a policy).

This is a verbatim, importable copy of `_baseline_worker_init` / `baseline_task` from `tools/m2_2_train.py`.
Those functions live in a script that later tools load via importlib, and Windows `spawn` pools cannot pickle
initializers from such a module (it is not importable by name in the worker). The logic is unchanged;
`test_m2_4_a.BaselineEvalCopy` checks that both produce identical records.
"""
from __future__ import annotations

from . import runmode, trials, training

_B = {}


def worker_init():
    from . import runner
    _B['config'] = runner.load_config()
    _B['sessions'] = {}


def baseline_task(args):
    from . import runner
    name, specs, mode_name = args
    if name not in _B['sessions']:
        _B['sessions'][name] = runner.make_session(runner.make_policy(name, _B['config']), _B['config'])
    s = _B['sessions'][name]
    mode = runmode.EVAL if mode_name == 'EVAL' else runmode.TRAIN
    out = []
    for kind, fam, level, seed in specs:
        if kind == 'threat':
            r = trials.run_threat_trial(s, training.FAMILIES[fam], level, seed, mode)
            r['group'] = 'threat:%s:%s' % (fam, level)
        else:
            rr = trials.run_background(s, training.BACKGROUND[fam], seed, mode)
            r = {'metrics': rr['metrics'], 'trajectory_sha256': rr['trajectory_sha256'], 'group': 'background:%s' % fam}
        r.update({'kind': kind, 'seed': seed})
        out.append(r)
    return out
