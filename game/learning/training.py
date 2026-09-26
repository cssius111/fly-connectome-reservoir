"""M2.2 constrained PPO training (training-side code; never part of a policy).

Rollout workers each hold one unchanged `Session` with a `ManeuverPolicy` wrapping the frozen
M2.0 MLP (stochastic sampling from its seeded RNG). A rollout unit is one background episode
(M2.1 background family) plus several threat trials (M2.1 threat families and attacker
levels), run through the frozen M2.1 trial / episode code with a per-tick hook that records
reward components from privileged state. Nothing from the hook reaches the policy.

Per-tick training reward:
    reward v2 (frozen): +1 on the tick a committed strike resolves as a miss, -1 on a hit
                        (effort coefficient 0); background price 0.00589 per unnecessary escape
    Lagrangian:         -lambda_u per unnecessary escape (escape while no strike is committed and
                        the paddle is > 310 units away), +lambda_p per perch (touchdown) event
Dual ascent on lambda_u (budget: unnecessary escapes / min in background episodes) and
lambda_p (minimum perch rate), using an exponential moving average of the per-iteration
background measurements.
"""
from __future__ import annotations

import os

import numpy as np

from . import runmode, runner, trials
from .contracts import MANEUVERS, N_MANEUVERS
from .model import MLPPolicyModel
from .policies import ManeuverPolicy, ModelDecision

NONE_INDEX = [m.name for m in MANEUVERS].index('NONE')
FAMILIES = {f.name: f for f in trials.THREAT_FAMILIES}
BACKGROUND = {c.name: c for c in trials.BACKGROUND_FAMILIES}

_W = {}


def worker_init():
    os.environ.setdefault('NUMBA_NUM_THREADS', '1')
    os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')
    config = runner.load_config()
    model = MLPPolicyModel(seed=0)
    policy = ManeuverPolicy(ModelDecision(model, stochastic=True), float(config['sim']['tick_seconds']),
                            float(config['policy']['refractory_seconds']), record=True)
    _W['model'] = model
    _W['policy'] = policy
    _W['session'] = runner.make_session(policy, config)


def _run_one(spec):
    kind, name, level, seed = spec
    s, pol = _W['session'], _W['policy']
    rec = {'unnec': [], 'perch': [], 'task': [], 'escape': [], 'turn': [], 'wall': [], 'maxspd': []}
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

    pol.record = True
    if kind == 'threat':
        info = trials.run_threat_trial(s, FAMILIES[name], level, seed, runmode.TRAIN, tick_hook=hook)
        terminal = True
    else:
        r = trials.run_background(s, BACKGROUND[name], seed, runmode.TRAIN, tick_hook=hook)
        info = {'seconds': r['metrics']['seconds']}
        terminal = False
    obs = np.array([o for o, _ in pol.trajectory], dtype=np.float32)
    act = np.array([a for _, a in pol.trajectory], dtype=np.int16)
    n = len(act)
    if n != len(rec['task']):
        raise RuntimeError('trajectory / hook misalignment (%d vs %d)' % (n, len(rec['task'])))
    out = {'kind': kind, 'name': name, 'level': level, 'seed': seed, 'obs': obs, 'act': act, 'terminal': terminal,
           **{k: np.array(v, dtype=np.float32 if k == 'task' else bool) for k, v in rec.items()}}
    if kind == 'threat':
        out['hit'] = bool(info['hit'])
        out['exposed'] = bool(info['exposed'])
        out['branch'] = info.get('branch')
    else:
        out['seconds'] = info['seconds']
    return out


def rollout_task(args):
    params, specs = args
    for k, v in params.items():
        _W['model'].params[k] = np.array(v, dtype=np.float64)
    return [_run_one(sp) for sp in specs]


def eval_task(args):
    """Validation / evaluation: frozen stochastic policy, M2.1 records (no training data)."""
    params, specs, mode_name = args
    for k, v in params.items():
        _W['model'].params[k] = np.array(v, dtype=np.float64)
    mode = runmode.EVAL if mode_name == 'EVAL' else runmode.TRAIN
    pol, s = _W['policy'], _W['session']
    pol.record = False
    out = []
    for kind, name, level, seed in specs:
        if kind == 'threat':
            r = trials.run_threat_trial(s, FAMILIES[name], level, seed, mode)
            r['group'] = 'threat:%s:%s' % (name, level)
        else:
            rr = trials.run_background(s, BACKGROUND[name], seed, mode)
            r = {'metrics': rr['metrics'], 'trajectory_sha256': rr['trajectory_sha256'], 'group': 'background:%s' % name}
        r.update({'kind': kind, 'seed': seed})
        out.append(r)
    pol.record = True
    return out


def init_models(train_seed, none_prior):
    """Policy with the NONE-action prior; critic with the same fixed input scaling."""
    from .ppo import ValueModel
    model = MLPPolicyModel(seed=train_seed)
    others = (1.0 - none_prior) / (N_MANEUVERS - 1)
    model.params['b2'] = np.full(N_MANEUVERS, np.log(others))
    model.params['b2'][NONE_INDEX] = np.log(none_prior)
    critic = ValueModel(seed=train_seed + 1, input_scale=model.input_scale)
    return model, critic
