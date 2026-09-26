"""M2.3 behaviour-cloning data and training (training-side code; never part of a policy).

Teacher rollouts use `MappedTeacherPolicy` inside an unchanged Session, through the frozen
M2.1 trial / episode code. Per decision the dataset stores:

    obs    (60,) float32  frozen whitelisted observation (the ONLY learner input)
    label  int8           teacher maneuver (mapping rule in teacher.py; labels never altered)
    context               analysis only, stored in separate arrays: episode kind, family,
                          attacker, committed strike, paddle horizontal distance, lifecycle
                          stationary flag, threat-window flag, seed

Context never enters `obs`; the tests check this.
"""
from __future__ import annotations

import os

import numpy as np

from . import runmode, runner, trials
from .contracts import N_MANEUVERS
from .teacher import MappedTeacherPolicy

FAMILIES = {f.name: f for f in trials.THREAT_FAMILIES}
BACKGROUND = {c.name: c for c in trials.BACKGROUND_FAMILIES}
FAMILY_CODE = {n: i for i, n in enumerate(list(FAMILIES) + list(BACKGROUND))}
_T = {}


def teacher_worker_init():
    os.environ.setdefault('NUMBA_NUM_THREADS', '1')
    os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')
    from ..session import build_policy
    config = runner.load_config()
    teacher = build_policy(config, runner.ROOT)[0]
    pol = MappedTeacherPolicy(teacher, float(config['sim']['tick_seconds']), float(config['policy']['refractory_seconds']),
                              record=True)
    _T['policy'] = pol
    _T['session'] = runner.make_session(pol, config)


def _episode(kind, name, level, seed, mode, collect):
    s, pol = _T['session'], _T['policy']
    ctx = {'committed': [], 'horizontal': [], 'stationary': []}
    w = s.world

    def hook(session, t, events, action, committed_before, horizontal, mode_before, resolved_now):
        ctx['committed'].append(committed_before)
        ctx['horizontal'].append(horizontal)
        ctx['stationary'].append(bool(w.lifecycle is not None and w.lifecycle.stationary))

    pol.record = collect
    if kind == 'threat':
        rec = trials.run_threat_trial(s, FAMILIES[name], level, seed, mode, tick_hook=hook if collect else None)
        rec['group'] = 'threat:%s:%s' % (name, level)
    else:
        rr = trials.run_background(s, BACKGROUND[name], seed, mode, tick_hook=hook if collect else None)
        rec = {'metrics': rr['metrics'], 'trajectory_sha256': rr['trajectory_sha256'], 'group': 'background:%s' % name}
    rec.update({'kind': kind, 'seed': seed})
    if not collect:
        return rec, None
    obs = np.array([o for o, _ in pol.samples], dtype=np.float32)
    lab = np.array([l for _, l in pol.samples], dtype=np.int8)
    n = len(lab)
    if n != len(ctx['committed']):
        raise RuntimeError('sample / hook misalignment')
    window = np.zeros(n, bool)
    if kind == 'threat' and rec.get('click_s') is not None:
        c = int(round(rec['click_s'] / 0.02))
        window[max(0, c - 50):min(n, c + 40)] = True          # 1 s before the click to the response window
    data = {'obs': obs, 'label': lab, 'ctx_kind': np.full(n, 1 if kind == 'threat' else 0, np.int8),
            'ctx_family': np.full(n, FAMILY_CODE[name], np.int8),
            'ctx_attacker': np.full(n, -1 if level is None else list(trials.ATTACKERS).index(level), np.int8),
            'ctx_committed': np.array(ctx['committed'], bool), 'ctx_horizontal': np.array(ctx['horizontal'], np.float32),
            'ctx_stationary': np.array(ctx['stationary'], bool), 'ctx_threat_window': window,
            'ctx_seed': np.full(n, seed, np.int64)}
    return rec, data


def teacher_data_task(args):
    specs, mode_name = args
    mode = runmode.EVAL if mode_name == 'EVAL' else runmode.TRAIN
    if mode_name == 'EVAL':
        raise ValueError('behaviour-cloning data must never come from EVAL seeds')
    parts = []
    for kind, name, level, seed in specs:
        _, d = _episode(kind, name, level, seed, mode, True)
        parts.append(d)
    return {k: np.concatenate([p[k] for p in parts]) for k in parts[0]}


def teacher_eval_task(args):
    specs, mode_name = args
    mode = runmode.EVAL if mode_name == 'EVAL' else runmode.TRAIN
    return [_episode(kind, name, level, seed, mode, False)[0] for kind, name, level, seed in specs]


def class_counts(labels):
    return np.bincount(labels.astype(int), minlength=N_MANEUVERS)
