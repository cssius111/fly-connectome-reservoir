"""M1.3 pulse kinematics, causal separation, and internal-state boundary."""
import copy
from dataclasses import fields
import math
import unittest
from unittest.mock import patch

import numpy as np
from game.action import Action, MotionState, MotorState, FixedEscapePolicy
from game.perception import Retina
from game.saccade import Saccades
from game.session import Session, calibration_provenance, resolve_escape_threshold
from game.world import World
from test_game import CONFIG, shared_brain

DT = CONFIG["sim"]["tick_seconds"]


class TestSaccadePhysics(unittest.TestCase):
    def test_spontaneous_pulses_are_brief_bounded_and_separated(self):
        pulses = Saccades(CONFIG["saccades"], 101)
        bouts, current, quiet = [], [], 0
        quiet_gaps = []
        for _ in range(1500):
            delta = pulses.step(DT, Action())
            if pulses.kind == "SPONTANEOUS":
                if not current:
                    quiet_gaps.append(quiet * DT)
                    quiet = 0
                current.append(delta)
            else:
                if current:
                    bouts.append(current)
                    current = []
                quiet += 1
        self.assertGreaterEqual(len(bouts), 5)
        for bout in bouts:
            self.assertAlmostEqual(len(bout) * DT, .30, delta=DT)
            self.assertGreaterEqual(abs(sum(bout)), math.radians(16) - 1e-9)
            self.assertLessEqual(abs(sum(bout)), math.radians(24) + 1e-9)
            self.assertLess(abs(bout[0]), max(map(abs, bout)))
            self.assertLess(abs(bout[-1]), max(map(abs, bout)))
            self.assertTrue(all(np.sign(x) == np.sign(bout[0]) for x in bout))
        self.assertTrue(all(gap >= 2.5 - DT for gap in quiet_gaps))

    def test_pulse_sequence_is_seeded_and_resettable(self):
        pulses = Saccades(CONFIG["saccades"], 17)
        def run():
            return [pulses.step(DT, Action()) for _ in range(600)]
        first = run()
        pulses.reset(17)
        self.assertEqual(first, run())
        pulses.reset(18)
        self.assertNotEqual(first, run())

    def test_spontaneous_course_changes_keep_velocity_and_position_continuous(self):
        world = World(CONFIG, 101)
        steps, speeds, heading_steps = [], [], []
        pulses_seen = 0
        for _ in range(800):
            f = world.fly
            old = (f.x, f.y, f.heading)
            world.tick(DT)
            steps.append(math.dist(old[:2], (f.x, f.y)))
            speeds.append(math.hypot(f.vx, f.vy))
            heading_steps.append(abs((f.heading - old[2] + math.pi) % (2 * math.pi) - math.pi))
            pulses_seen += world.saccades.kind == "SPONTANEOUS"
        self.assertGreater(pulses_seen, 0)
        self.assertGreater(sum(steps), 1000)
        self.assertLessEqual(max(steps), CONFIG["fly"]["baseline_speed"] * DT + 1e-6)
        self.assertLessEqual(max(heading_steps), CONFIG["fly"]["max_yaw_rate"] * DT + 1e-6)
        self.assertLessEqual(max(speeds), CONFIG["fly"]["baseline_speed"] + 1e-6)

    def test_long_baseline_does_not_stick_or_oscillate_at_walls(self):
        for seed in (17, 101, 104):
            world = World(CONFIG, seed)
            contacts = 0
            for t in range(3000):
                world.tick(DT)
                f = world.fly
                contacts += min(f.x-world.margin, world.width-world.margin-f.x,
                                f.y-world.margin, world.height-world.margin-f.y) < 1.0
                if t > 50:
                    self.assertGreater(math.hypot(f.vx, f.vy), 40.0)
            self.assertLess(contacts, 10)

    def test_emergency_pulse_is_stronger_than_alert_and_rate_limited(self):
        results = []
        for emergency in (False, True):
            cfg = copy.deepcopy(CONFIG)
            cfg["fly"]["wander_turn_rate"] = 0
            world = World(cfg, 101)
            turns, speeds = [], []
            for t in range(20):
                action = Action(escape=emergency, lateral=1.0, saccade=1.0) if t == 0 else Action()
                world.tick(DT, action)
                turns.append(world.yaw_rate * DT)
                speeds.append(math.hypot(world.fly.vx, world.fly.vy))
                self.assertLessEqual(abs(world.yaw_rate), cfg["fly"]["max_yaw_rate"])
            results.append((sum(turns), max(speeds)))
        self.assertGreater(results[1][0], results[0][0])
        self.assertGreater(results[1][1], 4 * results[0][1])

    def test_emergency_preempts_baseline_without_instant_heading_jump(self):
        pulses = Saccades(CONFIG["saccades"], 101)
        pulses.wait = 0
        pulses.step(DT, Action())
        delta = pulses.step(DT, Action(escape=True, lateral=-1, saccade=-1))
        self.assertEqual(pulses.kind, "ESCAPE")
        self.assertLess(delta, 0)
        self.assertLess(abs(delta), math.radians(5))

    def test_repeated_request_does_not_restart_an_active_emergency_each_tick(self):
        pulses = Saccades(CONFIG["saccades"], 101)
        action = Action(escape=True, lateral=1, saccade=1)
        deltas = [pulses.step(DT, action) for _ in range(15)]
        self.assertAlmostEqual(sum(deltas), math.radians(60), places=6)
        self.assertAlmostEqual(pulses.remaining, 0)

    def test_zero_strength_escape_does_not_create_alert_pulse(self):
        pulses = Saccades(CONFIG["saccades"], 101)
        self.assertEqual(pulses.step(DT, Action(escape=True, saccade=1, strength=0)), 0)
        self.assertEqual(pulses.kind, "NONE")

    def test_motion_disabled_freezes_active_saccade_for_calibration(self):
        world = World(CONFIG, 101)
        world.tick(DT, Action(escape=True, lateral=1, saccade=1))
        world.fly_motion_enabled = False
        world.collisions_enabled = False
        snapshot = world.fly.x, world.fly.y, world.fly.heading, world.saccades.remaining
        for _ in range(100):
            world.tick(DT, Action(escape=True, lateral=-1, saccade=-1))
        self.assertEqual(snapshot, (world.fly.x, world.fly.y, world.fly.heading, world.saccades.remaining))
        self.assertEqual((world.fly.vx, world.fly.vy, world.yaw_rate), (0, 0, 0))

    def test_saccade_action_rejects_nonfinite_or_out_of_range_requests(self):
        for bad in (-1.01, 1.01, float("nan"), float("inf")):
            with self.assertRaises(ValueError):
                Action(saccade=bad)


class TestSaccadeNeuralSource(unittest.TestCase):
    @staticmethod
    def motor(left, right):
        return MotorState(left, right, 0, 0, np.zeros(1))

    def test_sustained_subthreshold_dnp01_requests_alert_saccade(self):
        policy = FixedEscapePolicy(1.45, .4, DT)
        actions = [policy.decide(self.motor(1, 0)) for _ in range(15)]
        self.assertEqual([a.saccade for a in actions[:2]], [0, 0])
        self.assertGreater(actions[2].saccade, 0)
        self.assertFalse(any(a.escape for a in actions))
        self.assertEqual(sum(a.saccade != 0 for a in actions), 1)

    def test_left_right_neural_signals_request_opposite_pulses(self):
        results = []
        for left, right in ((3, 0), (0, 3)):
            policy = FixedEscapePolicy(1.45, .4, DT)
            results.append(policy.decide(self.motor(left, right)))
        self.assertGreater(results[0].saccade, 0)
        self.assertLess(results[1].saccade, 0)
        self.assertAlmostEqual(results[0].saccade, -results[1].saccade)
        self.assertTrue(all(a.escape for a in results))

    def test_single_noisy_frame_cannot_request_alert_saccade(self):
        policy = FixedEscapePolicy(1.45, .4, DT)
        actions = [policy.decide(self.motor(1, 0))]
        actions += [policy.decide(self.motor(0, 0)) for _ in range(15)]
        self.assertFalse(any(a.saccade for a in actions))

    def test_silenced_brain_preserves_only_tonic_motion_and_spontaneous_saccades(self):
        session = Session(CONFIG, brain=shared_brain(), seed=101)
        kinds = set()
        distance = 0
        with patch.object(session.brain, "step", return_value=np.empty(0, dtype=np.int64)):
            for t in range(500):
                f = session.world.fly
                before = (f.x, f.y)
                session.tick(pointer=(f.x, f.y-10) if t < 60 else None)
                distance += math.dist(before, (f.x, f.y))
                kinds.add(session.world.saccades.kind)
                a = session.fly_loop.last_action
                self.assertEqual((a.turn, a.saccade, a.escape), (0, 0, False))
        self.assertIn("SPONTANEOUS", kinds)
        self.assertNotIn("ALERT", kinds)
        self.assertNotIn("ESCAPE", kinds)
        self.assertGreater(distance, 600)


class TestInternalMotionBoundary(unittest.TestCase):
    def test_motion_interface_is_frozen_slotted_and_body_frame_only(self):
        self.assertEqual({f.name for f in fields(MotionState)},
                         {"forward_speed", "lateral_speed", "yaw_rate", "saccade_remaining"})
        state = MotionState(85, 2, .3, .1)
        self.assertFalse(hasattr(state, "__dict__"))
        with self.assertRaises((AttributeError, TypeError)):
            state.mouse_x = 5
        with self.assertRaises(ValueError):
            MotionState(float("nan"))

    def test_world_feedback_transforms_velocity_without_absolute_heading_or_position(self):
        world = World(CONFIG, 101)
        world.fly.heading = math.pi / 2
        world.fly.vx, world.fly.vy = 3, 85
        feedback = world.motion_state()
        self.assertAlmostEqual(feedback.forward_speed, 85)
        self.assertAlmostEqual(feedback.lateral_speed, -3)

    def test_bad_motion_inputs_cannot_smuggle_world_into_policy(self):
        session = Session(CONFIG, brain=shared_brain())
        class SneakyMotion(MotionState):
            __slots__ = ()
        for value in (session.world, session.world.swatter, {"mouse_x": 10}, (1,2), SneakyMotion()):
            with self.assertRaises(TypeError):
                session.fly_loop.step(Retina(0,0,0), value)

    def test_motion_is_available_to_policy_but_never_drives_brain_input(self):
        class CapturePolicy:
            def reset(self): self.seen = None
            def decide(self, motor):
                self.seen = motor
                return Action()
        policy = CapturePolicy()
        session = Session(CONFIG, brain=shared_brain(), policy=policy)
        observations = []
        for motion in (MotionState(), MotionState(70, -5, .7, .12)):
            session.reset(101)
            session.fly_loop.step(Retina(.35,.8,-.5), motion)
            observations.append(policy.seen.trace.copy())
            self.assertEqual(policy.seen.motion, motion)
            self.assertFalse(hasattr(policy.seen, "world"))
        np.testing.assert_array_equal(*observations)

    def test_calibration_still_matches_and_rejects_changed_saccade_parameters(self):
        self.assertGreater(resolve_escape_threshold(CONFIG).threshold, 0)
        changed = copy.deepcopy(CONFIG)
        changed["saccades"]["escape_max_degrees"] += 1
        self.assertNotEqual(calibration_provenance(changed), calibration_provenance(CONFIG))
        with self.assertRaisesRegex(ValueError, "calibrate_escape"):
            resolve_escape_threshold(changed)


if __name__ == "__main__":
    unittest.main(verbosity=2)
