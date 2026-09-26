"""M2.3 behaviour cloning: teacher mapping, learner-input isolation, dataset seed discipline."""
import importlib.util
from pathlib import Path
import unittest

import numpy as np

from game.action import Action, MotionState, MotorState
from game.learning import bc, runmode
from game.learning.contracts import MANEUVERS, ObservationEncoder
from game.learning.runner import load_config
from game.learning.teacher import MappedTeacherPolicy, map_action
from game.session import build_policy

ROOT = Path(__file__).parent
IDX = {m.name: i for i, m in enumerate(MANEUVERS)}


def motor(l, r, speed=200.0):
    return MotorState(l, r, 0.1, 0.1, np.arange(40, dtype=float), MotionState(speed, 0.0, 0.0, 0.0))


class Mapping(unittest.TestCase):
    def test_mapping_rule(self):
        self.assertEqual(map_action(Action()), IDX['NONE'])
        self.assertEqual(map_action(Action(turn=0.1)), IDX['NONE'])
        self.assertEqual(map_action(Action(turn=-0.4)), IDX['TURN_LEFT'])
        self.assertEqual(map_action(Action(turn=0.4, saccade=0.3)), IDX['ALERT_SACCADE_RIGHT'])
        self.assertEqual(map_action(Action(escape=True, lateral=0.1, forward=0.35, strength=1.0)), IDX['ESCAPE_FORWARD'])
        self.assertEqual(map_action(Action(escape=True, lateral=-0.8, forward=0.35, strength=1.0)), IDX['ESCAPE_LEFT'])
        self.assertEqual(map_action(Action(escape=True, lateral=0.8, forward=0.35, strength=0.5)), IDX['ESCAPE_RIGHT_HALF'])
        self.assertEqual(map_action(Action(escape=True, lateral=0.8, forward=0.35, strength=0.0)), IDX['NONE'])


class LearnerInputIsolation(unittest.TestCase):
    def setUp(self):
        cfg = load_config()
        self.pol = MappedTeacherPolicy(build_policy(cfg)[0], 0.02, 0.4, record=True)

    def test_learner_observation_is_the_frozen_encoder_output(self):
        fresh = ObservationEncoder()
        from game.learning.contracts import ManeuverActuator
        act = ManeuverActuator(0.02, 0.4)
        stream = [motor(0.0, 0.0), motor(1.2, 0.1), motor(2.4, 0.3), motor(0.5, 0.0), motor(0.0, 0.0)] * 4
        for m in stream:
            state = act.behavior_state
            self.pol.decide(m)
            act.act(self.pol.last_index)
            np.testing.assert_array_equal(self.pol.samples[-1][0], fresh.encode(m, state))
        for obs, label in self.pol.samples:
            self.assertEqual(obs.shape, (60,))
            self.assertIsInstance(label, int)

    def test_teacher_internals_do_not_enter_the_observation(self):
        a = MappedTeacherPolicy(build_policy(load_config())[0], 0.02, 0.4, record=True)
        b = MappedTeacherPolicy(build_policy(load_config())[0], 0.02, 0.4, record=True)
        # Perturb only teacher-internal decoder state; the learner observation must not change.
        b.teacher._streak = 7
        b.teacher._side_left = 3.0
        b.teacher._lat_last_left = -1
        a.decide(motor(0.2, 0.1))
        b.decide(motor(0.2, 0.1))
        np.testing.assert_array_equal(a.samples[0][0], b.samples[0][0])

    def test_only_the_accepted_policy_can_teach(self):
        with self.assertRaises(TypeError):
            MappedTeacherPolicy(object(), 0.02, 0.4)


class DatasetDiscipline(unittest.TestCase):
    def test_teacher_data_refuses_eval_mode(self):
        with self.assertRaises(ValueError):
            bc.teacher_data_task(([('threat', 'direct', 'easy', 3_800_001)], 'EVAL'))

    def test_teacher_seeds_are_train_opt_only(self):
        spec = importlib.util.spec_from_file_location('m23', ROOT / 'tools/m2_3_bc_ppo.py')
        m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(m)
        seeds = [s for *_, s in m.teacher_specs()]
        dev = m.dev_seeds()
        ev = {s for v in m.M22.m21().seeds('eval').values() for s in v}
        val = {s for v in m.M22.split()['train_val'].values() for s in v}
        for s in seeds:
            self.assertTrue(20_000_000 <= s < 25_000_000)
            runmode.TRAIN.check_seed(s)
        self.assertFalse(set(seeds) & (dev | ev | val))


if __name__ == '__main__':
    unittest.main()
