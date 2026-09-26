"""M2.1: exposure-controlled benchmark v2, reward v2, frozen contracts and seed discipline."""
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

import numpy as np

from game.learning import contracts, runmode, runner, trials
from game.learning.metrics import anti_cheat_v2
from game.learning.model import MLPPolicyModel
from game.learning.reward_v2 import RewardV2, derive, trial_score

ROOT = Path(__file__).parent
# Frozen at M2.0 (commit 20899c9); M2.1 must not change the observation or action contract.
OBSERVATION_SCHEMA_SHA256 = 'a53b963997c8207ddd1c53a5205f6b48b6bada28db933762f02d68454519b080'
ACTION_SCHEMA_SHA256 = '8848a9c7d4bf0e5377d71e85775717a4873fc41e2bc83478ae3e54b43937a6a0'


def sha(obj):
    return hashlib.sha256(json.dumps(obj, sort_keys=True).encode()).hexdigest()


class FrozenContracts(unittest.TestCase):
    def test_observation_and_action_contracts_unchanged_since_m2_0(self):
        self.assertEqual(sha(contracts.OBSERVATION_SCHEMA), OBSERVATION_SCHEMA_SHA256)
        self.assertEqual(sha(contracts.ACTION_SCHEMA), ACTION_SCHEMA_SHA256)


class QuickDirect(trials.DirectThreat):
    def draw_engage(self, rng):
        rng.uniform(1.5, 6.0)            # keep the draw order of the real family
        return 0.4


class QuickFallback(trials.PerchedOrFallbackThreat):
    def setup(self, session, rng, attacker_profile):
        super().setup(session, rng, attacker_profile)
        self.fallback_t = int(0.6 / trials.DT)
        self.engage_t = self.fallback_t


class Exposure(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cfg = runner.load_config()
        cls.sessions = {p: runner.make_session(runner.make_policy(p, cfg), cfg)
                        for p in ('no_escape', 'probe_constant_turn')}

    def test_threat_exposure_is_policy_independent(self):
        seed = runmode.train_seeds(5, 1)[0]
        recs = {p: trials.run_threat_trial(s, QuickDirect, 'nominal', seed, runmode.TRAIN) for p, s in self.sessions.items()}
        for r in recs.values():
            self.assertTrue(r['exposed'])
            self.assertIsNotNone(r['click_s'])
        a, b = recs.values()
        self.assertEqual(a['engage_s'], b['engage_s'])
        self.assertEqual(a['attacker_params'], b['attacker_params'])

    def test_never_perching_still_receives_a_fallback_threat(self):
        seed = runmode.train_seeds(6, 1)[0]
        r = trials.run_threat_trial(self.sessions['probe_constant_turn'], QuickFallback, 'hard', seed, runmode.TRAIN)
        self.assertTrue(r['exposed'])
        self.assertEqual(r['branch'], 'airborne_fallback')
        self.assertEqual(r['exposure_type'], 'airborne_fallback')

    def test_eval_mode_refuses_train_seeds(self):
        with self.assertRaises(ValueError):
            trials.run_threat_trial(self.sessions['no_escape'], QuickDirect, 'easy', runmode.train_seeds(8, 1)[0],
                                    runmode.EVAL)


def trial(hit, n_esc=1, pre=False, first=None, family='direct', branch=None, blind=0, esc_total=1, blind_pre=False):
    return {'exposed': True, 'hit': hit, 'escapes_in_window': n_esc, 'escape_in_window': n_esc > 0,
            'escape_latency_s': 0.1 if n_esc else None, 'pre_threat_escape': pre, 'escape_state_at_click': False,
            'forced_click': False, 'first_escape_s': first, 'family': family, 'branch': branch,
            'escapes_total': esc_total, 'blind_escapes_total': blind, 'blind_pre_click_escape': blind_pre}


def bg(unnec, minutes=1.0, perches=1, wall=0.01, spd=0.0, turn=0.05):
    return {'unnecessary_escapes': unnec, 'seconds': minutes * 60, 'perches': perches, 'wall_contact_fraction': wall,
            'max_speed_fraction': spd, 'turn_active_fraction': turn}


class RewardV2Design(unittest.TestCase):
    def test_trial_score(self):
        spec = RewardV2(effort=0.05)
        self.assertEqual(trial_score(trial(False, 1), spec), 1.0)
        self.assertEqual(trial_score(trial(True, 0), spec), -1.0)
        self.assertAlmostEqual(trial_score(trial(False, 3), spec), 0.9)
        with self.assertRaises(ValueError):
            trial_score(dict(trial(False), exposed=False), spec)

    def test_derive_finds_a_band_between_probe_inequalities(self):
        dev = {'baseline_n4b1c': {'threat': [trial(i % 10 < 6) for i in range(100)], 'background': [bg(4)] * 10},
               'no_escape': {'threat': [trial(i % 10 < 7, 0) for i in range(100)], 'background': [bg(0)] * 10},
               'probe_constant_turn': {'threat': [trial(i % 10 < 8, 0) for i in range(100)], 'background': [bg(0)] * 10},
               'probe_always_escape': {'threat': [trial(i % 10 < 5) for i in range(100)], 'background': [bg(130)] * 10}}
        spec, cons, rec = derive(dev)
        self.assertTrue(rec['feasible'])
        lo, hi = rec['price_band']
        self.assertTrue(lo < spec.unnecessary < hi)
        self.assertIn('unnecessary_escapes_per_min', cons)

    def test_derive_reports_an_empty_band(self):
        dev = {'baseline_n4b1c': {'threat': [trial(i % 10 < 7) for i in range(100)], 'background': [bg(4)] * 10},
               'no_escape': {'threat': [trial(i % 10 < 6, 0) for i in range(100)], 'background': [bg(0)] * 10}}
        spec, cons, rec = derive(dev)
        self.assertFalse(rec['feasible'])


class AntiCheatV2(unittest.TestCase):
    def test_clock_and_pre_emptive_flags(self):
        base_bg = {'near_wall_fraction': 0.1, 'max_speed_fraction': 0.0, 'turn_active_fraction': 0.05,
                   'turn_sign_switches_per_s': 0.1, 'airborne_slow_fraction': 0.02, 'early_escape_fraction': 0.0,
                   'blind_escape_fraction': 0.0, 'pre_click_blind_per_strike': 0.0, 'perches_per_min': 0.8,
                   'category_switches_per_s': 0.5}
        base = [trial(False, first=1.0 + 0.37 * i) for i in range(20)]
        clock = [trial(False, pre=True, first=2.0, blind=1, esc_total=1, blind_pre=True) for _ in range(20)]
        f = anti_cheat_v2(clock, base_bg, base, base_bg)
        self.assertTrue(f['fixed_timing_anticipation'])
        self.assertTrue(f['pre_emptive_perpetual_escape'])
        self.assertTrue(f['paddle_timing_exploit'])
        self.assertFalse(any(anti_cheat_v2(base, base_bg, base, base_bg).values()))


class ModelCheckpoint(unittest.TestCase):
    def test_deterministic_forward_and_checkpoint_hash(self):
        a, b = MLPPolicyModel(seed=4), MLPPolicyModel(seed=4)
        obs = contracts.ObservationEncoder().encode(
            __import__('game.action', fromlist=['MotorState']).MotorState(0.5, 0.1, 0.2, 0.3, np.zeros(3)), 'CALM')
        np.testing.assert_array_equal(a.logits(obs), b.logits(obs))
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / 'ckpt.npz'
            h = a.save(p)
            m = MLPPolicyModel.load(p, expected_sha256=h)
            self.assertEqual(m.param_hash(), h)
            np.testing.assert_array_equal(m.logits(obs), a.logits(obs))
            with self.assertRaises(ValueError):
                MLPPolicyModel.load(p, expected_sha256='0' * 64)


class SeedDiscipline(unittest.TestCase):
    def test_dev_train_and_eval_seed_sets(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location('m21', ROOT / 'tools/m2_1_benchmark.py')
        m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(m)
        dev = [s for v in m.seeds('dev').values() for s in v]
        ev = [s for v in m.seeds('eval').values() for s in v]
        v1 = [s for x in runner.SUITE for s in x['eval_seeds']]
        self.assertFalse(set(dev) & set(ev))
        self.assertFalse(set(ev) & set(v1))
        for s in dev:
            runmode.TRAIN.check_seed(s)
        for s in ev:
            runmode.EVAL.check_seed(s)

    def test_frozen_definition_matches_code(self):
        path = ROOT / 'game/learning/benchmark_v2_frozen.json'
        if not path.exists():
            self.skipTest('benchmark v2 not frozen yet')
        fz = json.loads(path.read_text(encoding='utf-8'))
        self.assertEqual(fz['benchmark_definition_sha256'], trials.definition_sha256())
        self.assertEqual(fz['attacker_distribution_sha256'], trials.attacker_sha256())
        self.assertEqual(RewardV2(**fz['reward_v2']).sha256(), fz['reward_v2_sha256'])


if __name__ == '__main__':
    unittest.main()
