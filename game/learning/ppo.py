"""Minimal numpy PPO (clipped surrogate, categorical actions) with a separate value network.

Training-only code. The deployed policy is the frozen M2.0 `MLPPolicyModel`
(60 -> 32 tanh -> 11 logits, 2,315 parameters). The critic (60 -> 32 tanh -> 1, 1,985
parameters) exists only during training and is never part of a policy.

Everything is vectorised over the batch; gradients are derived by hand for the two-layer
tanh networks and checked against finite differences in the tests.
"""
from __future__ import annotations

import numpy as np

from .model import MLPPolicyModel


class ValueModel:
    def __init__(self, seed, hidden=32, n_in=60, input_scale=None):
        rng = np.random.default_rng(seed)
        self.params = {'W1': rng.normal(0.0, 1.0 / np.sqrt(n_in), (hidden, n_in)), 'b1': np.zeros(hidden),
                       'W2': rng.normal(0.0, 0.01, (1, hidden)), 'b2': np.zeros(1)}
        self.input_scale = np.ones(n_in) if input_scale is None else input_scale

    def forward(self, X):
        Z = X * self.input_scale
        H = np.tanh(Z @ self.params['W1'].T + self.params['b1'])
        return (H @ self.params['W2'].T + self.params['b2'])[:, 0], (Z, H)


def policy_forward(model: MLPPolicyModel, X):
    Z = X * model.input_scale
    H = np.tanh(Z @ model.params['W1'].T + model.params['b1'])
    L = H @ model.params['W2'].T + model.params['b2']
    L = L - L.max(axis=1, keepdims=True)
    P = np.exp(L)
    P /= P.sum(axis=1, keepdims=True)
    return P, (Z, H)


def two_layer_grads(params, Z, H, d_out):
    """Backprop d_out (N, n_out) through out = tanh(Z W1^T + b1) W2^T + b2."""
    g = {'W2': d_out.T @ H, 'b2': d_out.sum(0)}
    dH = (d_out @ params['W2']) * (1 - H ** 2)
    g['W1'] = dH.T @ Z
    g['b1'] = dH.sum(0)
    return g


def ppo_policy_loss_and_grads(model, X, A, logp_old, adv, clip, ent_coef):
    """Loss = -mean(min(r A, clip(r) A)) - ent_coef * mean(entropy). Returns loss, grads, stats."""
    N = X.shape[0]
    P, (Z, H) = policy_forward(model, X)
    logP = np.log(P + 1e-12)
    logp = logP[np.arange(N), A]
    ratio = np.exp(logp - logp_old)
    unclipped = ratio * adv
    clipped = np.clip(ratio, 1 - clip, 1 + clip) * adv
    use_unclipped = unclipped <= clipped
    surrogate = np.where(use_unclipped, unclipped, clipped)
    entropy = -(P * logP).sum(1)
    loss = -surrogate.mean() - ent_coef * entropy.mean()
    # d(-surrogate)/d logits: only where the unclipped branch is active (else zero gradient)
    coef = np.where(use_unclipped, -ratio * adv, 0.0) / N              # d loss / d logp_a
    onehot = np.zeros_like(P)
    onehot[np.arange(N), A] = 1.0
    d_logits = coef[:, None] * (onehot - P)
    # entropy: dH/dlogit_j = -P_j (log P_j + H)
    d_ent = -P * (logP + entropy[:, None])
    d_logits += -ent_coef * d_ent / N
    grads = two_layer_grads(model.params, Z, H, d_logits)
    approx_kl = float(np.mean(logp_old - logp))
    clipfrac = float(np.mean(np.abs(ratio - 1) > clip))
    return loss, grads, {'entropy': float(entropy.mean()), 'approx_kl': approx_kl, 'clipfrac': clipfrac,
                         'policy_loss': float(-surrogate.mean())}


def value_loss_and_grads(vmodel, X, returns, vf_coef):
    N = X.shape[0]
    v, (Z, H) = vmodel.forward(X)
    err = v - returns
    loss = vf_coef * 0.5 * np.mean(err ** 2)
    d_out = (vf_coef * err / N)[:, None]
    return loss, two_layer_grads(vmodel.params, Z, H, d_out)


class Adam:
    def __init__(self, params, lr, b1=0.9, b2=0.999, eps=1e-8):
        self.lr, self.b1, self.b2, self.eps = lr, b1, b2, eps
        self.m = {k: np.zeros_like(v) for k, v in params.items()}
        self.v = {k: np.zeros_like(v) for k, v in params.items()}
        self.t = 0

    def step(self, params, grads):
        self.t += 1
        out = {}
        for k in params:
            self.m[k] = self.b1 * self.m[k] + (1 - self.b1) * grads[k]
            self.v[k] = self.b2 * self.v[k] + (1 - self.b2) * grads[k] ** 2
            mh = self.m[k] / (1 - self.b1 ** self.t)
            vh = self.v[k] / (1 - self.b2 ** self.t)
            out[k] = -self.lr * mh / (np.sqrt(vh) + self.eps)
        return out


def clip_grads(grads, max_norm):
    norm = float(np.sqrt(sum(float((g ** 2).sum()) for g in grads.values())))
    scale = min(1.0, max_norm / (norm + 1e-12))
    return {k: g * scale for k, g in grads.items()}, norm


def gae(rewards, values, dones, last_value, gamma, lam):
    """rewards, values, dones: arrays over one episode segment; dones[t] = 1 if t is terminal
    (no bootstrap). last_value: bootstrap value after the final step (0 if terminal)."""
    T = len(rewards)
    adv = np.zeros(T)
    last = 0.0
    for t in range(T - 1, -1, -1):
        nxt = last_value if t == T - 1 else values[t + 1]
        nonterminal = 1.0 - dones[t]
        delta = rewards[t] + gamma * nxt * nonterminal - values[t]
        last = delta + gamma * lam * nonterminal * last
        adv[t] = last
    return adv, adv + values
