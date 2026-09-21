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
                             LIFECYCLE_OWNED_CONTEXTS, NEURAL_OVERRIDE_CONTEXTS,
                             SAMPLED_CONTEXTS, KinematicCaps, KinematicExecutor,
                             KinematicProfile, KinematicResolver, KinematicSampler)
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
                                                         effective_cap=cap, profile_cap=cap,
                                                         safety_ceiling=cap, clamp_speed=True), fly, DT)
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


class TestB2aSamplerAndScale(unittest.TestCase):
    """M1.8-B2a: an isolated, seeded, still-inert sampler and a no-op ROOM mapping."""

    def test_seed_offsets_are_pairwise_unique(self):
        from game.ecology import EcologicalController
        from game.flight import FreeFlightController
        # Offsets are literals in their own modules; assert they cannot collide.
        offsets = {'flight': 3907, 'ecology': 7013, 'spawn': 8191, 'lifecycle': 18001,
                   'kinematics': KinematicSampler.SEED_OFFSET}
        self.assertEqual(len(set(offsets.values())), len(offsets))
        seed = 255
        streams = {name: np.random.default_rng(seed+off).random() for name, off in offsets.items()}
        self.assertEqual(len(set(streams.values())), len(streams))

    def test_sampler_is_inert_and_takes_no_draw(self):
        sampler = KinematicSampler(255)
        self.assertTrue(sampler.untouched)
        command = EcologicalCommand('EXPLORE', 6.0, .1, 1.0)
        for threat in (False, True):
            self.assertIsNone(sampler.target_speed_bl_s(command, threat))
            self.assertIsNone(sampler.target_speed_bl_s(None, threat))
        self.assertTrue(sampler.untouched);self.assertEqual(sampler.draws, 0)

    def test_sampler_reseeds_deterministically_from_the_world_seed(self):
        a, b = KinematicSampler(255), KinematicSampler(255)
        self.assertEqual(a.rng.bit_generator.state, b.rng.bit_generator.state)
        self.assertNotEqual(a.rng.bit_generator.state, KinematicSampler(256).rng.bit_generator.state)
        a.rng.random();self.assertNotEqual(a.rng.bit_generator.state, b.rng.bit_generator.state)
        a.reset(255);self.assertEqual(a.rng.bit_generator.state, b.rng.bit_generator.state)

    def test_world_reset_reseeds_the_sampler_and_leaves_it_untouched(self):
        w = World(ROOM, 101)
        for _ in range(60):w.tick(DT, Action())
        self.assertTrue(w.kinematic_sampler.untouched)
        before = w.kinematic_sampler.rng.bit_generator.state
        w.reset(101)
        self.assertEqual(w.kinematic_sampler.rng.bit_generator.state, before)
        w.reset(102)
        self.assertNotEqual(w.kinematic_sampler.rng.bit_generator.state, before)

    def test_resolver_remains_pure_and_rng_free(self):
        r = resolver()
        self.assertFalse(any('rng' in name or 'sampler' in name for name in vars(r)))

    def test_room_kinematic_scale_is_one_and_maps_exactly(self):
        self.assertEqual(ROOM['kinematics']['room_kinematic_scale'], 1.0)
        r = resolver()
        self.assertEqual(r.room_kinematic_scale, 1.0)
        body = ROOM['fly']['body_length_px']
        for bl in (0.0, 1.5, 6.0, 9.0, 13.0, 1e6):
            self.assertEqual(r.ecological_units(bl), bl*body)

    def test_scale_is_wired_even_though_its_value_is_one(self):
        body = ROOM['fly']['body_length_px']
        scaled = KinematicResolver(216., 1e9, body, 3., 2.5)
        self.assertEqual(scaled.ecological_units(6.0), 6.0*body*2.5)
        command = EcologicalCommand('EXPLORE', 6.0, 0., 1.0)
        self.assertEqual(scaled.airborne(command, False).target_speed, 6.0*body*2.5)

    def test_invalid_scale_is_rejected(self):
        for bad in (0.0, -1.0, math.nan, math.inf):
            with self.assertRaises(ValueError):
                KinematicResolver(216., 1000., 24., 3., bad)

    def test_sampled_speed_hook_overrides_only_when_supplied(self):
        r, body = resolver(), ROOM['fly']['body_length_px']
        command = EcologicalCommand('EXPLORE', 6.0, 0., 1.0)
        self.assertEqual(r.airborne(command, False, None).target_speed, 6.0*body)
        self.assertEqual(r.airborne(command, False, 11.0).target_speed, 11.0*body)

    def test_threat_contexts_are_excluded_from_future_sampling(self):
        self.assertEqual(SAMPLED_CONTEXTS,
                         {'EXPLORE', 'TRANSIT', 'ODOR_TRACK', 'ODOR_SEARCH', 'RECOVER'})
        self.assertEqual(NEURAL_OVERRIDE_CONTEXTS, {'ALERT', 'ESCAPE'})
        self.assertEqual(LIFECYCLE_OWNED_CONTEXTS, {'LAND_OR_PERCH'})
        self.assertFalse(SAMPLED_CONTEXTS & NEURAL_OVERRIDE_CONTEXTS)
        self.assertFalse(SAMPLED_CONTEXTS & LIFECYCLE_OWNED_CONTEXTS)

    def test_threat_priority_still_bypasses_the_ecological_envelope(self):
        # Documents the currently non-authoritative ALERT/ESCAPE speed envelopes.
        r = resolver()
        for state in ('ALERT', 'ESCAPE'):
            command = EcologicalCommand(state, 18.0, .5, 0.0)
            p = r.airborne(command, True)
            self.assertEqual(p.context, 'neural_priority')
            self.assertEqual(p.target_speed, ROOM['fly']['baseline_speed'])
            self.assertNotEqual(p.target_speed, 18.0*ROOM['fly']['body_length_px'])

    def test_legacy_presets_default_to_unit_scale(self):
        for name in ('game_config.json', 'game_play_config.json'):
            config = load_config(ROOT/name)
            self.assertNotIn('kinematics', config)
            self.assertEqual(World(config, 5).kinematics.room_kinematic_scale, 1.0)


class TestB2biSeparatedCaps(unittest.TestCase):
    """M1.8-B2b-i: three named Class C ceilings replace one overloaded max_speed."""

    def test_config_holds_three_caps_at_the_legacy_value(self):
        legacy = ROOM['fly']['max_speed']
        k = ROOM['kinematics']
        for key in ('ecological_cap_units_s', 'legacy_accepted_cap_units_s',
                    'safety_ceiling_units_s'):
            self.assertEqual(k[key], legacy)

    def test_caps_default_to_the_legacy_ceiling_when_absent(self):
        for name in ('game_config.json', 'game_play_config.json'):
            config = load_config(ROOT/name)
            legacy = config['fly']['max_speed']
            caps = KinematicCaps.from_config(config, legacy)
            self.assertEqual((caps.ecological, caps.legacy_accepted, caps.safety_ceiling),
                             (legacy, legacy, legacy))

    def test_invalid_caps_are_rejected(self):
        for bad in ((0., 1., 1.), (1., -1., 1.), (1., 1., math.nan), (1., 1., math.inf)):
            with self.assertRaises(ValueError):KinematicCaps(*bad)

    def test_effective_cap_is_the_tighter_of_profile_and_ceiling(self):
        caps = KinematicCaps(900., 1000., 1200.)
        self.assertEqual(caps.effective(900.), 900.)
        self.assertEqual(caps.effective(1500.), 1200.)
        with self.assertRaises(ValueError):
            KinematicProfile('c', effective_cap=50., profile_cap=10., safety_ceiling=99.)

    def test_each_context_draws_its_own_ceiling(self):
        body = ROOM['fly']['body_length_px']
        r = KinematicResolver(216., 1000., body, 3., 1.0, KinematicCaps(700., 1000., 1200.))
        eco = r.airborne(EcologicalCommand('EXPLORE', 6., 0., 1.), False)
        self.assertEqual(eco.profile_cap, 700.);self.assertEqual(eco.effective_cap, 700.)
        for profile in (r.airborne(None, False),
                        r.airborne(EcologicalCommand('EXPLORE', 6., 0., 1.), True),
                        r.landing_approach(2., .18, 0.),
                        r.lifecycle_direct('lifecycle_stationary_contact')):
            self.assertEqual(profile.profile_cap, 1000.)
            self.assertEqual(profile.safety_ceiling, 1200.)

    def test_ecological_cap_does_not_reach_the_neural_escape_path(self):
        # An escape action always sets threat_priority, so the ecological ceiling is
        # never in scope on an escape tick. This pins the M1.8-B2b-R0 finding.
        body = ROOM['fly']['body_length_px']
        r = KinematicResolver(216., 1000., body, 3., 1.0, KinematicCaps(50., 1000., 1200.))
        self.assertTrue(World._neural_active(Action(escape=True, forward=1., strength=1.)))
        self.assertEqual(
            r.airborne(EcologicalCommand('EXPLORE', 6., 0., 1.), True).profile_cap, 1000.)

    def test_lifecycle_targets_use_the_legacy_cap_not_the_ecological_one(self):
        body = ROOM['fly']['body_length_px']
        r = KinematicResolver(216., 1000., body, 3., 1.0, KinematicCaps(24., 1000., 1200.))
        # 2 BL/s * 24 = 48 units/s, above a deliberately tiny ecological cap.
        self.assertEqual(r.landing_approach(2., .18, 0.).target_speed, 48.)

    def test_world_exposes_legacy_equivalent_caps(self):
        w = World(ROOM, 101)
        legacy = ROOM['fly']['max_speed']
        self.assertEqual(w.kinematic_caps, KinematicCaps(legacy, legacy, legacy))
        self.assertEqual(w.max_speed, legacy)
        w.tick(DT, Action())
        self.assertEqual(w.kinematic_profile.effective_cap, legacy)


if __name__ == '__main__':
    unittest.main(verbosity=2)
