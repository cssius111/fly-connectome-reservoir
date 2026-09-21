"""M1.8-B1 kinematic interface regressions.

B1 is a no-op refactor, so these assert exact equality with the accepted pre-B1
arithmetic rather than approximate agreement.
"""
import math
import os
from pathlib import Path
import unittest

import numpy as np
os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')
from game.action import Action
from game.ecology import EcologicalCommand
from game.kinematics import (DAMPED_CRUISE, DIRECT, EXPONENTIAL_APPROACH,
                             KinematicExecutor, KinematicProfile, KinematicResolver)
from game.session import load_config
from game.world import Fly, World

ROOT = Path(__file__).parent
ROOM = load_config(ROOT/'game_room_config.json')
DT = .02


def resolver(config=ROOM):
    f = config['fly']
    return KinematicResolver(f['baseline_speed'], f['max_speed'], f['body_length_px'],
                             f['damping_per_second'])


class TestKinematicProfile(unittest.TestCase):
    def test_rejects_invalid_requests(self):
        with self.assertRaises(ValueError):KinematicProfile('c', relaxation='teleport')
        with self.assertRaises(ValueError):KinematicProfile('')
        with self.assertRaises(ValueError):KinematicProfile('c', target_speed=math.nan)
        with self.assertRaises(ValueError):KinematicProfile('c', target_speed=-1)
        with self.assertRaises(ValueError):KinematicProfile('c', relaxation=EXPONENTIAL_APPROACH)
        with self.assertRaises(ValueError):KinematicProfile('c', speed_envelope_bl_s=(5, 1))

    def test_b2_hooks_are_inert_by_default(self):
        p = KinematicProfile('c')
        self.assertIsNone(p.speed_envelope_bl_s);self.assertIsNone(p.acceleration_limit)
        self.assertIsNone(p.deceleration_limit);self.assertIsNone(p.persistence_seconds)
        self.assertEqual(p.turn_gain, 1.0)

    def test_profile_is_immutable(self):
        p = KinematicProfile('c')
        with self.assertRaises(AttributeError):p.target_speed = 5.0


class TestResolver(unittest.TestCase):
    def test_no_command_requests_baseline_cruise(self):
        p = resolver().airborne(None, False)
        self.assertEqual(p.context, 'baseline_cruise')
        self.assertEqual(p.target_speed, ROOM['fly']['baseline_speed'])
        self.assertEqual(p.steering_rad_s, 0.0);self.assertEqual(p.spontaneous_clock_rate, 1.0)
        self.assertEqual(p.relaxation, DAMPED_CRUISE)

    def test_neural_priority_overrides_the_ecological_command(self):
        command = EcologicalCommand('ODOR_TRACK', 11.0, .4, .35)
        p = resolver().airborne(command, True)
        self.assertEqual(p.context, 'neural_priority')
        self.assertEqual(p.target_speed, ROOM['fly']['baseline_speed'])
        self.assertEqual(p.steering_rad_s, 0.0);self.assertEqual(p.spontaneous_clock_rate, 1.0)

    def test_ecological_command_is_converted_and_capped(self):
        body, cap = ROOM['fly']['body_length_px'], ROOM['fly']['max_speed']
        command = EcologicalCommand('EXPLORE', 6.0, -.25, 1.0)
        p = resolver().airborne(command, False)
        self.assertEqual(p.context, 'ecology_explore')
        self.assertEqual(p.target_speed, 6.0*body)
        self.assertEqual(p.steering_rad_s, -.25);self.assertEqual(p.spontaneous_clock_rate, 1.0)
        self.assertEqual(resolver().airborne(EcologicalCommand('TRANSIT', 1e6, 0, 1), False).target_speed, cap)

    def test_resolver_is_pure_and_has_no_random_stream(self):
        r = resolver()
        self.assertFalse(any('rng' in name for name in vars(r)))
        command = EcologicalCommand('EXPLORE', 6.0, -.25, 1.0)
        self.assertEqual(r.airborne(command, False), r.airborne(command, False))

    def test_landing_approach_profile_uses_the_exponential_law(self):
        p = resolver().landing_approach(2.0, .18, .3)
        self.assertEqual(p.context, 'lifecycle_visual_approach')
        self.assertEqual(p.relaxation, EXPONENTIAL_APPROACH)
        self.assertEqual(p.target_speed, 2.0*ROOM['fly']['body_length_px'])
        self.assertEqual(p.relaxation_rate, .18);self.assertFalse(p.clamp_speed)


class TestExecutorMatchesLegacyArithmetic(unittest.TestCase):
    """Exact equality, including operand grouping, with the pre-B1 expressions."""

    def test_damped_cruise_is_bit_identical(self):
        damping, cap = ROOM['fly']['damping_per_second'], ROOM['fly']['max_speed']
        for target, vx, vy, heading in ((216., 30., -12., .7), (400., -260., 90., 2.9), (0., 5., 5., 0.)):
            fly = Fly(0, 0, vx, vy, heading)
            legacy_vx = vx + (damping*(target*math.cos(heading)-vx))*DT
            legacy_vy = vy + (damping*(target*math.sin(heading)-vy))*DT
            speed = math.hypot(legacy_vx, legacy_vy)
            if speed > cap:
                legacy_vx *= cap/speed;legacy_vy *= cap/speed
            KinematicExecutor.translate(KinematicProfile('c', DAMPED_CRUISE, target, damping,
                                                         max_speed=cap, clamp_speed=True), fly, DT)
            self.assertEqual((fly.vx, fly.vy), (legacy_vx, legacy_vy))

    def test_exponential_approach_is_bit_identical_and_unclamped(self):
        tau = ROOM['lifecycle']['approach_velocity_tau_seconds']
        for target, vx, vy, heading in ((48., 120., -30., 1.2), (36., -8., 2., 3.4)):
            fly = Fly(0, 0, vx, vy, heading)
            alpha = 1-math.exp(-DT/tau)
            legacy_vx = vx + alpha*(target*math.cos(heading)-vx)
            legacy_vy = vy + alpha*(target*math.sin(heading)-vy)
            KinematicExecutor.translate(KinematicProfile('c', EXPONENTIAL_APPROACH, target, tau), fly, DT)
            self.assertEqual((fly.vx, fly.vy), (legacy_vx, legacy_vy))

    def test_direct_relaxation_leaves_velocity_to_world(self):
        fly = Fly(0, 0, 7., -3., .4)
        KinematicExecutor.translate(KinematicProfile('c', DIRECT, 900.), fly, DT)
        self.assertEqual((fly.vx, fly.vy), (7., -3.))

    def test_yaw_composition_is_bit_identical_and_clipped(self):
        cap = ROOM['fly']['max_yaw_rate']
        for neural, drift, eco, pulse in ((.4, .03, -.21, .002), (0., 0., 0., 0.), (9., 9., 9., 9.)):
            legacy = float(np.clip(neural + drift + eco + pulse/DT, -cap, cap))
            got = KinematicExecutor.yaw_rate(KinematicProfile('c', steering_rad_s=eco),
                                             neural, drift, pulse, DT, cap)
            self.assertEqual(got, legacy)


class TestWorldIntegration(unittest.TestCase):
    def test_world_exposes_the_profile_and_tags_context(self):
        w = World(ROOM, 101)
        self.assertIsInstance(w.kinematics, KinematicResolver)
        w.tick(DT, Action())
        self.assertEqual(w.kinematic_profile.context, 'baseline_cruise')
        self.assertEqual(w.applied_target_speed, w.kinematic_profile.target_speed)

    def test_applied_target_speed_still_follows_the_profile(self):
        w = World(ROOM, 101)
        w.ecological_command = EcologicalCommand('EXPLORE', 7.0, .1, 1.0)
        w.tick(DT, Action())
        self.assertEqual(w.kinematic_profile.context, 'ecology_explore')
        self.assertEqual(w.applied_target_speed, 7.0*w.body_length)

    def test_lifecycle_contexts_are_labelled_without_changing_recorded_profiles(self):
        w = World(ROOM, 101)
        w.fly = Fly(1290, 1120, -216, 0, math.pi)
        from game.action import MotionState
        from game.ecology import ThreatState
        for _ in range(500):
            m = w.motion_state()
            w.lifecycle.step(w.room.landing_sense(w.fly, w.time_seconds, w.contact_surface_id),
                             MotionState(m.forward_speed/w.body_length, m.lateral_speed/w.body_length,
                                         m.yaw_rate, m.saccade_remaining), ThreatState.CALM, DT)
            w.tick(DT, Action())
            if w.lifecycle.stationary:
                break
        self.assertTrue(w.lifecycle.stationary)
        # Touchdown is detected inside the approach branch, so the stationary profile
        # is requested from the following tick onward.
        self.assertEqual(w.kinematic_profile.context, 'lifecycle_visual_approach')
        w.tick(DT, Action())
        self.assertEqual(w.kinematic_profile.context, 'lifecycle_stationary_contact')
        # The M1.8-A recorded profile keeps its accepted schema and values.
        self.assertEqual(w.lifecycle.applied_profile, {'name': 'stationary_contact', 'speed_bl_s': 0.0})

    def test_legacy_presets_use_the_same_interface(self):
        for name in ('game_config.json', 'game_play_config.json'):
            w = World(load_config(ROOT/name), 5)
            w.tick(DT, Action())
            self.assertEqual(w.kinematic_profile.context, 'baseline_cruise')
            self.assertIsNone(w.lifecycle)


if __name__ == '__main__':
    unittest.main(verbosity=2)
