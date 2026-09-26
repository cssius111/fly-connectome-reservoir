"""M2.2 training code: PPO gradients (finite differences), GAE, NONE prior, stochastic frozen policy."""
import unittest

import numpy as np

from game.learning import training
from game.learning.contracts import N_MANEUVERS, OBSERVATION_SIZE
from game.learning.model import MLPPolicyModel
from game.learning.policies import ModelDecision
from game.learning.ppo import ValueModel, gae, ppo_policy_loss_and_grads, value_loss_and_grads


def fd_check(testcase, params, loss_fn, grads, n=12, eps=1e-6, tol=1e-4):
    rng = np.random.default_rng(0)
    for k, g in grads.items():
        for _ in range(n):
            i = tuple(rng.integers(s) for s in g.shape)
            old = params[k][i]
            params[k][i] = old + eps
            up = loss_fn()
            params[k][i] = old - eps
            dn = loss_fn()
            params[k][i] = old
            num = (up - dn) / (2 * eps)
            testcase.assertAlmostEqual(num, g[i], delta=tol * max(1.0, abs(num)))


class PPOGradients(unittest.TestCase):
    def setUp(self):
        rng = np.random.default_rng(1)
        self.X = rng.normal(0, 1, (64, OBSERVATION_SIZE))
        self.model = MLPPolicyModel(seed=3)
        self.model.params['W2'] = rng.normal(0, 0.3, self.model.params['W2'].shape)
        self.model.input_scale = np.ones(OBSERVATION_SIZE)
        self.A = rng.integers(N_MANEUVERS, size=64)
        self.adv = rng.normal(0, 1, 64)
        from game.learning.ppo import policy_forward
        P, _ = policy_forward(self.model, self.X)
        # old log-probs slightly different so that some ratios are clipped
        self.logp_old = np.log(P[np.arange(64), self.A]) + rng.normal(0, 0.1, 64)

    def test_policy_gradient(self):
        def loss():
            return ppo_policy_loss_and_grads(self.model, self.X, self.A, self.logp_old, self.adv, 0.2, 0.01)[0]
        _, g, _ = ppo_policy_loss_and_grads(self.model, self.X, self.A, self.logp_old, self.adv, 0.2, 0.01)
        fd_check(self, self.model.params, loss, g)

    def test_value_gradient(self):
        v = ValueModel(seed=2)
        ret = np.random.default_rng(4).normal(0, 1, 64)

        def loss():
            return value_loss_and_grads(v, self.X, ret, 0.5)[0]
        _, g = value_loss_and_grads(v, self.X, ret, 0.5)
        fd_check(self, v.params, loss, g)


class GAEAndInit(unittest.TestCase):
    def test_gae_terminal_and_bootstrap(self):
        adv, ret = gae(np.array([0.0, 0.0, 1.0]), np.zeros(3), np.array([0, 0, 1.0]), 5.0, 0.5, 1.0)
        np.testing.assert_allclose(ret, [0.25, 0.5, 1.0])       # terminal: bootstrap ignored
        adv, ret = gae(np.array([0.0]), np.zeros(1), np.zeros(1), 2.0, 0.5, 1.0)
        np.testing.assert_allclose(ret, [1.0])                  # truncation: bootstraps

    def test_none_prior(self):
        m, c = training.init_models(1, 0.97)
        p = m.probabilities(np.zeros(OBSERVATION_SIZE))
        self.assertAlmostEqual(p[training.NONE_INDEX], 0.97, places=2)

    def test_stochastic_frozen_policy_samples_deterministically(self):
        m = MLPPolicyModel(seed=5)
        d = ModelDecision(m, stochastic=True)
        obs = np.zeros(OBSERVATION_SIZE)
        a = [d.act(obs, np.random.default_rng(9), explore=False)[0] for _ in range(3)]
        self.assertEqual(len(set(a)), 1)                        # same seed -> same action
        rng = np.random.default_rng(10)
        self.assertGreater(len({d.act(obs, rng, explore=False)[0] for _ in range(200)}), 1)


if __name__ == '__main__':
    unittest.main()


class M23Gradients(unittest.TestCase):
    def test_cross_entropy_and_kl_anchor_gradients(self):
        from game.learning.ppo import cross_entropy_loss_and_grads, kl_anchor_loss_and_grads, policy_forward
        rng = np.random.default_rng(7)
        X = rng.normal(0, 1, (48, OBSERVATION_SIZE))
        m = MLPPolicyModel(seed=8)
        m.params['W2'] = rng.normal(0, 0.3, m.params['W2'].shape)
        m.input_scale = np.ones(OBSERVATION_SIZE)
        y = rng.integers(N_MANEUVERS, size=48)
        off = np.zeros(N_MANEUVERS)
        off[0] = np.log(4.0)
        _, g, _ = cross_entropy_loss_and_grads(m, X, y, off)
        fd_check(self, m.params, lambda: cross_entropy_loss_and_grads(m, X, y, off)[0], g)
        ref = MLPPolicyModel(seed=9)
        ref.params['W2'] = rng.normal(0, 0.3, ref.params['W2'].shape)
        ref.input_scale = np.ones(OBSERVATION_SIZE)
        logQ = np.log(policy_forward(ref, X)[0])
        _, g2, _ = kl_anchor_loss_and_grads(m, X, logQ, 0.7)
        fd_check(self, m.params, lambda: kl_anchor_loss_and_grads(m, X, logQ, 0.7)[0], g2)
