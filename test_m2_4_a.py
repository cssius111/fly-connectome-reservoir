"""M2.4-A strike-centric PPO: loss weighting, credit windows, sampling and anti-leakage."""
import importlib.util
import json
import os
from pathlib import Path
import re
import unittest

import numpy as np

os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')
ROOT = Path(__file__).parent


def tool():
    spec = importlib.util.spec_from_file_location('m24a', ROOT / 'tools/m2_4_a_strike_ppo.py')
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


T = tool()


def fake_episode(kind, name, n, engage=-1, click=-1):
    return {'kind': kind, 'name': name, 'act': np.zeros(n, np.int16), 'obs': np.zeros((n, 60), np.float32),
            'engage_index': engage, 'click_index': click, 'resolved_index': -1}


class Weighting(unittest.TestCase):
    def setUp(self):
        self.C = T.cfg('B_strike')
        self.eps = [fake_episode('background', 'free_flight', 3000), fake_episode('background', 'hover_only', 1000),
                    fake_episode('threat', 'direct', 300, 100, 180), fake_episode('threat', 'wall', 900, 200, 700),
                    fake_episode('threat', 'perched_or_fallback', 1600, 1400, 1480)]

    def unit_totals(self, w):
        off = np.concatenate([[0], np.cumsum([len(e['act']) for e in self.eps])])
        return np.array([w[off[i]:off[i + 1]].sum() for i in range(len(self.eps))])

    def test_strike_balanced_totals(self):
        w, unit, mask = T.actor_weights(self.eps, self.C)
        self.assertAlmostEqual(w.sum(), 1.0, places=12)
        tot = self.unit_totals(w)
        rho = self.C['weighting']['background_actor_share']
        np.testing.assert_allclose(tot[:2], [rho / 2, rho / 2])
        imp = T.family_importance(self.C['sampling'])
        q = np.array([imp['direct'], imp['wall'], imp['perched_or_fallback']])
        np.testing.assert_allclose(tot[2:], (1 - rho) * q / q.sum())
        # a 900-tick trial does not weigh 3 x a 300-tick trial of the same family weight
        self.assertAlmostEqual(tot[2], tot[3])

    def test_uniform_reference(self):
        w, _, _ = T.actor_weights(self.eps, T.cfg('A_ref'))
        np.testing.assert_allclose(w, 1.0 / sum(len(e['act']) for e in self.eps))

    def test_window_restricts_actor_ticks_only_inside_threat_trials(self):
        C = dict(self.C, actor_window='click50')
        w, _, _ = T.actor_weights(self.eps, C)
        off = np.concatenate([[0], np.cumsum([len(e['act']) for e in self.eps])])
        d = w[off[2]:off[3]]
        self.assertTrue(np.all(d[:130] == 0) and np.all(d[130:] > 0))
        self.assertTrue(np.all(w[off[0]:off[2]] > 0))          # background: all ticks
        self.assertAlmostEqual(w.sum(), 1.0, places=12)

    def test_window_masks(self):
        e = fake_episode('threat', 'hover', 400, engage=120, click=250)
        self.assertEqual(int(np.argmax(T.window_mask(e, 'engage'))), 120)
        self.assertEqual(int(np.argmax(T.window_mask(e, 'click50'))), 200)
        self.assertEqual(int(np.argmax(T.window_mask(e, 'click25'))), 225)
        self.assertTrue(T.window_mask(e, 'full').all())
        self.assertTrue(T.window_mask(fake_episode('background', 'free_flight', 50), 'click25').all())

    def test_family_importance_restores_equal_family_weight(self):
        S = self.C['sampling']
        imp = T.family_importance(S)
        for f in T.FAMS:
            self.assertAlmostEqual(S['family_shares'][f] * imp[f], 0.25)


class Sampling(unittest.TestCase):
    def test_threat_dense_units_and_diversity(self):
        C = T.cfg('B_strike')
        specs = T.worker_specs(np.random.default_rng(0), set(), C['sampling'])
        flat = [s for u in specs for s in u]
        thr = [s for s in flat if s[0] == 'threat']
        self.assertEqual(len(thr), 98)
        self.assertEqual(len(flat) - len(thr), 7)
        self.assertEqual({s[1] for s in thr}, set(T.FAMS))
        self.assertEqual({s[2] for s in thr}, set(T.LEVELS))
        for s in flat:
            self.assertTrue(20_000_000 <= s[3] < 25_000_000)

    def test_confirm_set_is_fresh(self):
        r0 = importlib.util.spec_from_file_location('r0', ROOT / 'tools/m2_4_r0_temporal.py')
        m = importlib.util.module_from_spec(r0)
        r0.loader.exec_module(m)
        _, used = m.dev_pool()
        used |= {s for *_, s in m.dev_specs()} | {s for u in m.credit_units() for *_, s in u}
        cs = [s for *_, s in T.confirm_specs()]
        self.assertEqual(len(cs), 12 * 32 + 4 * 16)
        self.assertEqual(len(cs), len(set(cs)))
        self.assertFalse(set(cs) & used)


class AntiLeakage(unittest.TestCase):
    def test_collector_context_does_not_change_what_the_policy_sees(self):
        from game.learning import strike_training, training
        training.worker_init()
        m = T.MT.load_bc()[0].to_numpy_model()
        params = {k: v.copy() for k, v in m.params.items()}
        spec = ('threat', 'wall', 'hard', 25_000_031)
        a = strike_training.rollout_task((params, [spec]))[0]
        b = training.rollout_task((params, [spec]))[0]
        np.testing.assert_array_equal(a['obs'], b['obs'])
        np.testing.assert_array_equal(a['act'], b['act'])
        self.assertEqual(a['obs'].shape[1], 60)
        for k in ('engage_index', 'click_index', 'resolved_index'):
            self.assertIn(k, a)
            self.assertNotIn(k, b)

    def test_training_batch_is_built_from_observations_only(self):
        src = (ROOT / 'tools/m2_4_a_strike_ppo.py').read_text(encoding='utf-8')
        m = re.search(r"\n\s+X = (.+)\n", src)
        self.assertIn("e['obs']", m.group(1))
        for bad in ('click', 'engage', 'resolved', 'family', 'name', 'level'):
            self.assertNotIn(bad, m.group(1))

    def test_checkpoint_contains_only_policy_parameters(self):
        from game.learning.torch_policy import TorchPolicy
        net = TorchPolicy()
        self.assertEqual(set(net.state_dict()), {'fc1.weight', 'fc1.bias', 'fc2.weight', 'fc2.bias', 'input_scale'})
        with self.assertRaises(ValueError):
            import torch
            net(torch.zeros(2, 61))

    def test_eval_v3_manifest_frozen_and_unrun(self):
        man = json.loads((ROOT / 'game/learning/m2_eval_v3.json').read_text(encoding='utf-8'))
        self.assertEqual((man['n_threat'], man['n_background']), (480, 80))
        spec = importlib.util.spec_from_file_location('v3', ROOT / 'tools/m2_eval_v3.py')
        v3 = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(v3)
        v3.check()
        seeds = [s for v in man['seeds'].values() for s in v]
        self.assertTrue(all(3_900_000 < s < 3_916_000 for s in seeds))


if __name__ == '__main__':
    unittest.main()


class BaselineEvalCopy(unittest.TestCase):
    """game.learning.baseline_eval is a verbatim importable copy of the M2.2 baseline pool worker."""
    SPECS = [('threat', 'direct', 'nominal', 20_000_123), ('threat', 'wall', 'hard', 20_000_457)]

    def test_identical_records_to_the_m2_2_worker(self):
        import importlib.util
        from game.learning import baseline_eval
        spec = importlib.util.spec_from_file_location('m2_2_train_copycheck', ROOT / 'tools/m2_2_train.py')
        m22 = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(m22)
        m22._baseline_worker_init()
        baseline_eval.worker_init()
        for name in ('baseline_n4b1c', 'no_escape'):
            a = m22.baseline_task((name, self.SPECS, 'TRAIN'))
            b = baseline_eval.baseline_task((name, self.SPECS, 'TRAIN'))
            self.assertEqual(json.dumps(a, sort_keys=True, default=float), json.dumps(b, sort_keys=True, default=float))

    def test_spawn_pool_can_pickle_the_worker(self):
        import multiprocessing as mp
        from game.learning import baseline_eval
        with mp.get_context('spawn').Pool(1, initializer=baseline_eval.worker_init) as pool:
            r = pool.map(baseline_eval.baseline_task, [('no_escape', self.SPECS[:1], 'TRAIN')])
        self.assertEqual(r[0][0]['seed'], self.SPECS[0][3])
