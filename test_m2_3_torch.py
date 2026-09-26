"""M2.3 PyTorch learner: architecture, losses, optimizer, clipping and checkpoint correctness.

Scalar losses are compared against simple numpy reference formulas; finite differences check
autograd. These are tests only; the official learner uses torch autograd exclusively.
"""
import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

import numpy as np
import torch

from game.learning import contracts
from game.learning.model import MLPPolicyModel
from game.learning.ppo import cross_entropy_loss_and_grads
from game.learning.torch_policy import (TorchCritic, TorchPolicy, bc_loss, gae, init_critic, kl_to_reference,
                                        load_checkpoint, ppo_surrogate, save_checkpoint, state_dict_sha256, value_loss)

ROOT = Path(__file__).parent
torch.set_default_dtype(torch.float32)


def batch(n=64, seed=0):
    rng = np.random.default_rng(seed)
    X = rng.normal(0, 1, (n, 60)).astype(np.float32)
    X[:, 5::12] *= 300.0          # speeds are O(100) units / s in real observations
    return X


def np_softmax(z):
    z = z - z.max(1, keepdims=True)
    p = np.exp(z)
    return p / p.sum(1, keepdims=True)


class Architecture(unittest.TestCase):
    def test_parameter_counts(self):
        self.assertEqual(TorchPolicy().n_parameters, 2315)
        self.assertEqual(sum(p.numel() for p in TorchCritic().parameters()), 1985)
        self.assertEqual(TorchPolicy().n_parameters, MLPPolicyModel(seed=0).n_parameters)

    def test_shapes_and_deterministic_forward(self):
        net = TorchPolicy.from_numpy_model(MLPPolicyModel(seed=3))
        X = torch.as_tensor(batch())
        a, b = net(X), net(X)
        self.assertEqual(tuple(a.shape), (64, 11))
        self.assertTrue(torch.equal(a, b))
        self.assertEqual(tuple(init_critic(4)(X).shape), (64,))
        with self.assertRaises(ValueError):
            net(torch.zeros(3, 59))

    def test_numpy_export_parity(self):
        net = TorchPolicy.from_numpy_model(MLPPolicyModel(seed=5))
        with torch.no_grad():
            net.fc2.weight.mul_(50.0)          # make logits non-trivial
        m = net.to_numpy_model()
        X = batch(32, 1)
        Pt = torch.softmax(net(torch.as_tensor(X)), -1).detach().numpy()
        Pn = np.array([m.probabilities(x.astype(np.float64)) for x in X])
        self.assertLess(np.abs(Pt - Pn).max(), 1e-5)

    def test_initial_copy_from_numpy_is_exact(self):
        m = MLPPolicyModel(seed=2303)
        net = TorchPolicy.from_numpy_model(m)
        np.testing.assert_allclose(net.numpy_params()['W1'], m.params['W1'], rtol=1e-6, atol=1e-7)
        np.testing.assert_allclose(net.input_scale.numpy(), m.input_scale, rtol=1e-7)


class Losses(unittest.TestCase):
    def setUp(self):
        torch.manual_seed(0)
        self.net = TorchPolicy.from_numpy_model(MLPPolicyModel(seed=7))
        with torch.no_grad():
            self.net.fc2.weight.normal_(0, 0.5)
        self.X = torch.as_tensor(batch(40, 2))
        self.A = torch.as_tensor(np.random.default_rng(3).integers(0, 11, 40))

    def test_categorical_log_prob_and_entropy_match_numpy(self):
        L = self.net(self.X)
        d = torch.distributions.Categorical(logits=L)
        P = np_softmax(L.detach().double().numpy())
        np.testing.assert_allclose(d.log_prob(self.A).detach().numpy(), np.log(P[np.arange(40), self.A.numpy()]), atol=1e-5)
        np.testing.assert_allclose(d.entropy().detach().numpy(), -(P * np.log(P)).sum(1), atol=1e-5)

    def test_kl_to_frozen_reference_matches_numpy(self):
        ref = copy.deepcopy(self.net)
        with torch.no_grad():
            ref.fc2.bias.add_(torch.linspace(-1, 1, 11))
        L, R = self.net(self.X), ref(self.X)
        kl = kl_to_reference(L, R).detach().numpy()
        P, Q = np_softmax(L.detach().double().numpy()), np_softmax(R.detach().double().numpy())
        np.testing.assert_allclose(kl, (P * (np.log(P) - np.log(Q))).sum(1), atol=1e-5)
        self.assertTrue(np.all(kl >= -1e-7))
        self.assertLess(float(kl_to_reference(L, L).abs().max()), 1e-6)

    def test_ppo_ratio_and_clipped_surrogate_match_numpy(self):
        L = self.net(self.X)
        logp = torch.distributions.Categorical(logits=L).log_prob(self.A).detach()
        rng = np.random.default_rng(4)
        logp_old = logp + torch.as_tensor(rng.normal(0, 0.3, 40), dtype=torch.float32)
        adv = torch.as_tensor(rng.normal(0, 1, 40), dtype=torch.float32)
        loss, st = ppo_surrogate(L, self.A, logp_old, adv, 0.2)
        r = np.exp(logp.numpy().astype(np.float64) - logp_old.numpy())
        np.testing.assert_allclose(st['ratio'].detach().numpy(), r, rtol=1e-5)
        ref = -np.mean(np.minimum(r * adv.numpy(), np.clip(r, 0.8, 1.2) * adv.numpy()))
        self.assertAlmostEqual(float(loss), ref, places=5)
        self.assertAlmostEqual(float(st['clipfrac']), float(np.mean(np.abs(r - 1) > 0.2)), places=6)

    def test_surrogate_gradient_matches_numpy_handwritten_reference(self):
        # at ratio = 1 (on-policy), d(-mean(A * logp)) / d logits = -A (onehot - p) / N
        L = self.net(self.X)
        logp_old = torch.distributions.Categorical(logits=L).log_prob(self.A).detach()
        adv = torch.as_tensor(np.random.default_rng(5).normal(0, 1, 40), dtype=torch.float32)
        Ld = L.detach().requires_grad_(True)
        loss, _ = ppo_surrogate(Ld, self.A, logp_old, adv, 0.2)
        loss.backward()
        P = np_softmax(Ld.detach().double().numpy())
        onehot = np.eye(11)[self.A.numpy()]
        np.testing.assert_allclose(Ld.grad.numpy(), -(adv.numpy()[:, None] * (onehot - P)) / 40, atol=1e-6)

    def test_bc_loss_matches_numpy_and_finite_difference(self):
        m = MLPPolicyModel(seed=11)
        net = TorchPolicy.from_numpy_model(m).double()
        X = batch(30, 6).astype(np.float64)
        y = np.random.default_rng(7).integers(0, 11, 30)
        off = np.zeros(11)
        off[0] = np.log(0.05)
        loss_np, g_np, _ = cross_entropy_loss_and_grads(m, X, y, off)
        loss = bc_loss(net(torch.as_tensor(X)), torch.as_tensor(y), torch.as_tensor(off))
        loss.backward()
        self.assertAlmostEqual(float(loss), loss_np, places=8)   # float32 input-scale buffer
        np.testing.assert_allclose(net.fc1.weight.grad.numpy(), g_np["W1"], atol=1e-8)
        np.testing.assert_allclose(net.fc2.bias.grad.numpy(), g_np["b2"], atol=1e-8)
        # finite difference on one weight
        eps = 1e-6
        with torch.no_grad():
            w = net.fc2.weight
            w[3, 4] += eps
            up = float(bc_loss(net(torch.as_tensor(X)), torch.as_tensor(y), torch.as_tensor(off)))
            w[3, 4] -= 2 * eps
            dn = float(bc_loss(net(torch.as_tensor(X)), torch.as_tensor(y), torch.as_tensor(off)))
        self.assertAlmostEqual((up - dn) / (2 * eps), float(net.fc2.weight.grad[3, 4]), places=6)

    def test_value_loss(self):
        v = torch.tensor([0.1, -0.2, 0.3])
        r = torch.tensor([0.0, 0.5, 0.3])
        self.assertAlmostEqual(float(value_loss(v, r)), 0.5 * np.mean((v.numpy() - r.numpy()) ** 2), places=7)

    def test_gae_matches_reference(self):
        r = np.array([0.0, 0.0, 1.0])
        v = np.array([0.5, 0.4, 0.6])
        adv, ret = gae(r, v, np.array([0, 0, 1.0]), 0.0, 0.9, 0.8)
        d2 = 1.0 - 0.6
        d1 = 0.0 + 0.9 * 0.6 - 0.4
        d0 = 0.0 + 0.9 * 0.4 - 0.5
        a2, a1 = d2, d1 + 0.72 * d2
        np.testing.assert_allclose(adv, [d0 + 0.72 * a1, a1, a2])
        np.testing.assert_allclose(ret, adv + v)
        adv_b, _ = gae(np.zeros(2), np.array([0.1, 0.2]), np.zeros(2), 1.0, 0.5, 1.0)   # bootstrap
        np.testing.assert_allclose(adv_b, [0.5 * 0.2 - 0.1 + 0.5 * (0.5 * 1.0 - 0.2), 0.5 * 1.0 - 0.2])


class Optimisation(unittest.TestCase):
    def test_adam_step_changes_parameters_and_reference_stays_frozen(self):
        net = TorchPolicy.from_numpy_model(MLPPolicyModel(seed=1))
        ref = copy.deepcopy(net)
        for p in ref.parameters():
            p.requires_grad_(False)
        ref_sha = state_dict_sha256(ref)
        before = state_dict_sha256(net)
        opt = torch.optim.Adam(net.parameters(), lr=1e-3)
        X = torch.as_tensor(batch(16, 8))
        A = torch.randint(0, 11, (16,))
        L = net(X)
        loss, _ = ppo_surrogate(L, A, torch.distributions.Categorical(logits=L).log_prob(A).detach(), torch.randn(16), 0.2)
        loss = loss + 0.5 * kl_to_reference(L, ref(X)).mean()
        opt.zero_grad()
        loss.backward()
        for p in net.parameters():
            self.assertTrue(torch.isfinite(p.grad).all())
        opt.step()
        self.assertNotEqual(state_dict_sha256(net), before)
        self.assertEqual(state_dict_sha256(ref), ref_sha)
        self.assertTrue(all(p.grad is None for p in ref.parameters()))

    def test_gradient_clipping(self):
        net = TorchPolicy()
        X = torch.as_tensor(batch(8, 9))
        (net(X) ** 2).sum().mul(1e3).backward()
        pre = torch.nn.utils.clip_grad_norm_(net.parameters(), 0.5)
        post = torch.sqrt(sum(p.grad.pow(2).sum() for p in net.parameters()))
        self.assertGreater(float(pre), 0.5)
        self.assertAlmostEqual(float(post), 0.5, places=4)

    def test_no_nan_gradients_on_extreme_logits(self):
        net = TorchPolicy()
        with torch.no_grad():
            net.fc2.weight.mul_(1e4)
        X = torch.as_tensor(batch(32, 10))
        L = net(X)
        A = torch.randint(0, 11, (32,))
        loss, st = ppo_surrogate(L, A, torch.distributions.Categorical(logits=L).log_prob(A).detach(), torch.randn(32), 0.2)
        (loss - 0.01 * st['entropy'].mean() + kl_to_reference(L, L.detach() * 0.5).mean()).backward()
        for p in net.parameters():
            self.assertTrue(torch.isfinite(p.grad).all())


class Checkpoints(unittest.TestCase):
    def test_save_load_exact(self):
        net = TorchPolicy.from_numpy_model(MLPPolicyModel(seed=12))
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / 'c.pt'
            h = save_checkpoint(p, net, {'x': 1})
            m, meta = load_checkpoint(p, TorchPolicy, expected_sha256=h)
            self.assertEqual(meta, {'x': 1})
            for (k, a), (_, b) in zip(net.state_dict().items(), m.state_dict().items()):
                self.assertTrue(torch.equal(a, b), k)
            with self.assertRaises(ValueError):
                load_checkpoint(p, TorchPolicy, expected_sha256='0' * 64)
            with self.assertRaises(ValueError):
                load_checkpoint(p, TorchCritic)

    @unittest.skipUnless(torch.cuda.is_available(), 'CUDA not available')
    def test_cpu_loading_of_cuda_checkpoint(self):
        net = TorchPolicy.from_numpy_model(MLPPolicyModel(seed=13)).cuda()
        X = torch.as_tensor(batch(8, 11))
        with torch.no_grad():
            ref = net(X.cuda()).cpu()
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / 'c.pt'
            h = save_checkpoint(p, net)
            m, _ = load_checkpoint(p, TorchPolicy, expected_sha256=h, map_location='cpu')
            self.assertEqual(next(m.parameters()).device.type, 'cpu')
            with torch.no_grad():
                self.assertLess(float((m(X) - ref).abs().max()), 1e-5)

    def test_tracked_torch_bc_checkpoint_hash(self):
        mf = ROOT / 'game/learning/m2_3/torch_bc_metrics.json'
        if not mf.exists():
            self.skipTest('PyTorch BC not trained yet')
        meta = json.loads(mf.read_text(encoding='utf-8'))
        net, _ = load_checkpoint(ROOT / 'game/learning/m2_3/torch_bc_checkpoint.pt', TorchPolicy,
                                 expected_sha256=meta['checkpoint_state_dict_sha256'])
        self.assertEqual(net.n_parameters, 2315)


class FrozenContracts(unittest.TestCase):
    def test_observation_and_action_hashes_unchanged(self):
        p22 = json.loads((ROOT / 'game/learning/m2_2_protocol.json').read_text(encoding='utf-8'))
        obs = hashlib.sha256(json.dumps(contracts.OBSERVATION_SCHEMA, sort_keys=True).encode()).hexdigest()
        act = hashlib.sha256(json.dumps(contracts.ACTION_SCHEMA, sort_keys=True).encode()).hexdigest()
        self.assertEqual(obs, p22['observation_schema_sha256'])
        self.assertEqual(act, p22['action_schema_sha256'])
        self.assertEqual(contracts.OBSERVATION_SIZE, 60)
        self.assertEqual(contracts.N_MANEUVERS, 11)

    def test_torch_learner_module_imports_no_world_code(self):
        src = (ROOT / 'game/learning/torch_policy.py').read_text(encoding='utf-8')
        for forbidden in ('session', 'world', 'swatter', 'retina', 'lifecycle', 'room'):
            self.assertNotIn('import %s' % forbidden, src)
            self.assertNotIn('from ..%s' % forbidden, src)


if __name__ == '__main__':
    unittest.main()
