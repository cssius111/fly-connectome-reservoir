"""M2.3 PyTorch PPO: CPU rollout workers (training-side code; never part of a policy).

The workers are the M2.2 workers (`training.worker_init`): one unchanged `Session` per process
with a `ManeuverPolicy` wrapping the numpy `MLPPolicyModel` forward, sampling stochastically
from its seeded RNG. The learner (torch, CUDA) sends its parameters as float64 numpy arrays
before every rollout. MaleCNS, the game simulation and per-tick inference all stay on CPU.

Compared with the M2.2 rollout record, each episode additionally carries analysis-only fields
for the credit-assignment diagnostic: the committed-strike flag per tick and the click tick.
These come from the privileged tick hook and never reach the policy.
"""
from __future__ import annotations

import numpy as np

from . import runmode, trials, training


def _run_one(spec):
    kind, name, level, seed = spec
    s, pol = training._W['session'], training._W['policy']
    rec = {'unnec': [], 'perch': [], 'task': [], 'escape': [], 'turn': [], 'wall': [], 'maxspd': [], 'committed': []}
    w = s.world

    def hook(session, t, events, action, committed_before, horizontal, mode_before, resolved_now):
        esc = bool(action.escape and action.strength > 0)
        rec['escape'].append(esc)
        rec['unnec'].append(esc and not committed_before and horizontal > 310.0)
        mode_after = None if w.lifecycle is None else w.lifecycle.mode
        rec['perch'].append(mode_before != 'TOUCHDOWN' and mode_after == 'TOUCHDOWN')
        rec['task'].append(-1.0 if events.hit else (1.0 if resolved_now else 0.0))
        rec['turn'].append((abs(action.turn) >= 0.3) or bool(action.saccade))
        rec['wall'].append(bool(w.wall_contact or w.object_contact))
        rec['maxspd'].append(float(np.hypot(w.fly.vx, w.fly.vy)) >= 0.9 * w.max_speed)
        rec['committed'].append(bool(committed_before))

    pol.record = True
    click = -1
    if kind == 'threat':
        info = trials.run_threat_trial(s, training.FAMILIES[name], level, seed, runmode.TRAIN, tick_hook=hook)
        terminal = True
        if info.get('click_s') is not None:
            click = int(round(info['click_s'] / 0.02))
    else:
        r = trials.run_background(s, training.BACKGROUND[name], seed, runmode.TRAIN, tick_hook=hook)
        info = {'seconds': r['metrics']['seconds']}
        terminal = False
    obs = np.array([o for o, _ in pol.trajectory], dtype=np.float32)
    act = np.array([a for _, a in pol.trajectory], dtype=np.int16)
    if len(act) != len(rec['task']):
        raise RuntimeError('trajectory / hook misalignment (%d vs %d)' % (len(act), len(rec['task'])))
    out = {'kind': kind, 'name': name, 'level': level, 'seed': seed, 'obs': obs, 'act': act, 'terminal': terminal,
           'click_index': click,
           **{k: np.array(v, dtype=np.float32 if k == 'task' else bool) for k, v in rec.items()}}
    if kind == 'threat':
        out['hit'] = bool(info['hit'])
        out['exposed'] = bool(info['exposed'])
    else:
        out['seconds'] = info['seconds']
    return out


def rollout_task(args):
    params, specs = args
    for k, v in params.items():
        training._W['model'].params[k] = np.array(v, dtype=np.float64)
    return [_run_one(sp) for sp in specs]
