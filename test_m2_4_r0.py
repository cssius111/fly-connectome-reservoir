"""M2.4-R0 temporal-abstraction research tooling: cadence wrapper semantics and seed discipline."""
import importlib.util
import os
from pathlib import Path
import unittest

import numpy as np

os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')

from game.learning import runmode, runner, temporal_r0, trials  # noqa: E402
from game.learning.teacher import INDEX, MappedTeacherPolicy  # noqa: E402

ROOT = Path(__file__).parent


def tool():
    spec = importlib.util.spec_from_file_location('m24r0', ROOT / 'tools/m2_4_r0_temporal.py')
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


class HoldSemantics(unittest.TestCase):
    def setUp(self):
        self.t = tool()

    def test_period_one_is_identity(self):
        lab = np.array([0, 0, 5, 0, 1, 1, 2, 0, 3, 0])
        np.testing.assert_array_equal(self.t.hold(lab, 1, 'sampled'), lab)

    def test_sampled_loses_between_decision_escape(self):
        lab = np.array([0, 0, 5, 0, 0, 0])
        np.testing.assert_array_equal(self.t.hold(lab, 5, 'sampled'), [0, 0, 0, 0, 0, 0])

    def test_latched_delays_escape_to_next_decision(self):
        lab = np.array([0, 0, 5, 0, 0, 0, 0])
        held = self.t.hold(lab, 5, 'latched')
        self.assertEqual(held[5], 5)
        self.assertTrue(np.all(held[:5] == 0))

    def test_latched_priority_and_earliest_within_class(self):
        lab = np.array([0, 1, 3, 10, 6, 0])
        held = self.t.hold(lab, 5, 'latched')
        self.assertEqual(held[5], 10)          # first escape (right half) wins over the later full escape


class WrapperEquivalence(unittest.TestCase):
    def test_50hz_wrapper_reproduces_mapped_teacher_exactly(self):
        from game.session import Session, build_brain, build_policy
        cfg = runner.load_config()
        brain = build_brain(cfg, runner.ROOT)
        fam = trials.THREAT_FAMILIES[0]
        hashes = []
        for make in (lambda: MappedTeacherPolicy(build_policy(cfg, runner.ROOT)[0], 0.02, 0.4),
                     lambda: temporal_r0.HeldTeacherPolicy(build_policy(cfg, runner.ROOT)[0], 0.02, 0.4, 1, 'sampled')):
            s = Session(cfg, brain=brain, policy=make(), seed=runmode.EVAL_SEED_BASE + 1, mode='evaluation', root=runner.ROOT)
            rec = trials.run_threat_trial(s, fam, 'nominal', 25_000_017, runmode.TRAIN)
            hashes.append(rec['trajectory_sha256'])
        self.assertEqual(hashes[0], hashes[1])

    def test_invalid_cadence_rejected(self):
        with self.assertRaises(ValueError):
            temporal_r0.HeldTeacherPolicy(None, 0.02, 0.4, 0, 'sampled')


class SeedDiscipline(unittest.TestCase):
    def test_r0_episodes_are_fresh_train_seeds(self):
        t = tool()
        m22, used = t.dev_pool()
        specs = t.dev_specs()
        seeds = [s for *_, s in specs]
        self.assertEqual(len(seeds), len(set(seeds)))
        for s in seeds:
            runmode.TRAIN.check_seed(s)
        self.assertFalse(set(seeds) & used)
        cu = {s for u in t.credit_units() for *_, s in u}
        self.assertFalse(cu & set(seeds))
        self.assertFalse(cu & used)

    def test_eval_v3_seed_rule_is_disjoint_and_in_the_eval_range(self):
        v3 = [3_900_000 + 1000 * g + k for g in range(12) for k in range(1, 41)] + \
             [3_900_000 + 1000 * g + k for g in range(12, 16) for k in range(1, 21)]
        v2 = [3_800_000 + 1000 * g + k for g in range(16) for k in range(1, 21)]
        v1 = [s for i in range(7) for s in runmode.eval_seeds(i, 20)]
        for s in v3:
            runmode.EVAL.check_seed(s)
        brain = lambda xs: {x + 977 for x in xs}   # noqa: E731
        self.assertFalse(set(v3) & (set(v2) | set(v1) | brain(v2) | brain(v1)))
        self.assertFalse(brain(v3) & (set(v2) | set(v1)))


if __name__ == '__main__':
    unittest.main()
