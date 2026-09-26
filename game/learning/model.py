"""Proposed first learned model: a compact numpy MLP over the whitelisted observation.

Research / infrastructure only. No training is run in M2.0; `apply_update` exists so the
TRAIN / EVAL guard can be tested (EVAL must refuse it).

Architecture: observation (60) -> tanh hidden (32) -> maneuver logits (11); categorical
policy. 2,315 parameters. History is already in the observation (4 frames), so no recurrent
state is needed for the first model.
"""
from __future__ import annotations

import hashlib

import numpy as np

from .contracts import N_MANEUVERS, OBSERVATION_SIZE


class MLPPolicyModel:
    arch = 'mlp-60-32-11-tanh-softmax'

    def __init__(self, seed: int, hidden: int = 32, n_in: int = OBSERVATION_SIZE, n_out: int = N_MANEUVERS):
        rng = np.random.default_rng(seed)
        self.params = {
            'W1': rng.normal(0.0, 1.0 / np.sqrt(n_in), (hidden, n_in)),
            'b1': np.zeros(hidden),
            'W2': rng.normal(0.0, 0.01, (n_out, hidden)),
            'b2': np.zeros(n_out),
        }
        self.frozen = False
        # Fixed input scaling (documented constants, not fitted): DNp01 / DNa02 traces are O(1),
        # speeds are O(1000) units/s, yaw rate O(30) rad/s, saccade_remaining O(0.3) s.
        scale = np.ones(n_in)
        per = np.array([1.0, 1, 1, 1, 1, 1 / 1000, 1 / 1000, 1 / 30, 1 / 0.3, 1, 1, 1])
        for k in range(n_in // len(per)):
            scale[k * len(per):(k + 1) * len(per)] = per
        self.input_scale = scale

    @property
    def n_parameters(self) -> int:
        return int(sum(p.size for p in self.params.values()))

    def logits(self, obs: np.ndarray) -> np.ndarray:
        if not isinstance(obs, np.ndarray) or obs.shape != (OBSERVATION_SIZE,):
            raise TypeError('the model accepts only the fixed-size observation vector')
        h = np.tanh(self.params['W1'] @ (obs * self.input_scale) + self.params['b1'])
        return self.params['W2'] @ h + self.params['b2']

    def probabilities(self, obs):
        z = self.logits(obs)
        z = z - z.max()
        p = np.exp(z)
        return p / p.sum()

    def act(self, obs, rng, explore: bool):
        p = self.probabilities(obs)
        idx = int(rng.choice(len(p), p=p)) if explore else int(np.argmax(p))
        return idx, {'probabilities': p}

    def param_hash(self) -> str:
        h = hashlib.sha256()
        for k in sorted(self.params):
            h.update(k.encode())
            h.update(np.ascontiguousarray(self.params[k]).tobytes())
        return h.hexdigest()

    def apply_update(self, deltas: dict):
        if self.frozen:
            raise RuntimeError('parameter updates are forbidden in EVAL mode')
        for k, d in deltas.items():
            if self.params[k].shape != d.shape:
                raise ValueError('update shape mismatch for %s' % k)
            self.params[k] = self.params[k] + d

    def reinforce_gradients(self, obs_list, actions, advantages):
        """Score-function gradients of sum(advantage * log pi(a | obs)) (for the TRAIN smoke test)."""
        g = {k: np.zeros_like(v) for k, v in self.params.items()}
        for obs, a, adv in zip(obs_list, actions, advantages):
            x = obs * self.input_scale
            h = np.tanh(self.params['W1'] @ x + self.params['b1'])
            p = self.probabilities(obs)
            d_logits = -p
            d_logits[a] += 1.0
            d_logits *= adv
            g['W2'] += np.outer(d_logits, h)
            g['b2'] += d_logits
            dh = (self.params['W2'].T @ d_logits) * (1 - h ** 2)
            g['W1'] += np.outer(dh, x)
            g['b1'] += dh
        return g
