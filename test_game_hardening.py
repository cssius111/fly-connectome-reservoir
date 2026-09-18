"""M1.1 regressions: policy independence, action magnitude and calibration."""
import copy
import json
import math
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

os.environ.setdefault("NUMBA_NUM_THREADS", "4")
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")

import numpy as np
from game.action import Action, FixedEscapePolicy, MotorState, Policy
from game.session import Session, calibration_provenance, resolve_escape_threshold
from game.world import World
from test_game import CONFIG, shared_brain


class BarePolicy:
    def reset(self):
        pass

    def decide(self, motor):
        return Action()


class TestActionStrength(unittest.TestCase):
    def delta(self, strength=1.0, lateral=1.0, forward=0.35, escape=True):
        cfg = copy.deepcopy(CONFIG)
        cfg["fly"].update(wander_speed=0.0, damping_per_second=0.0, max_speed=10000.0)
        world = World(cfg, 19)
        world.fly.vx, world.fly.vy = 4.0, -3.0
        before = np.array([world.fly.vx, world.fly.vy])
        world.tick(0.02, Action(escape=escape, lateral=lateral,
                               forward=forward, strength=strength))
        return np.array([world.fly.vx, world.fly.vy]) - before

    def test_zero_strength_has_no_escape_impulse(self):
        np.testing.assert_array_equal(self.delta(0.0), [0.0, 0.0])

    def test_strength_monotonically_scales_velocity_delta(self):
        lengths = [np.linalg.norm(self.delta(s)) for s in (0.25, 0.5, 1.0)]
        self.assertLess(lengths[0], lengths[1])
        self.assertLess(lengths[1], lengths[2])
        np.testing.assert_allclose(lengths, np.array([0.25, 0.5, 1.0]) *
                                   CONFIG["fly"]["escape_impulse"])

    def test_different_strengths_do_not_collapse(self):
        half, full = self.delta(0.5), self.delta(1.0)
        self.assertFalse(np.array_equal(half, full))
        np.testing.assert_allclose(half * 2, full)

    def test_direction_length_does_not_change_selected_strength(self):
        np.testing.assert_allclose(self.delta(0.5, 1.0, 0.35),
                                   self.delta(0.5, 2.0, 0.70))

    def test_full_strength_preserves_previous_impulse(self):
        expected = np.array([0.35, 1.0])
        expected *= CONFIG["fly"]["escape_impulse"] / np.linalg.norm(expected)
        np.testing.assert_allclose(self.delta(), expected)

    def test_strength_is_validated_not_silently_clipped(self):
        for bad in (-0.01, 1.01, float("nan"), float("inf"), -float("inf")):
            with self.subTest(strength=bad), self.assertRaises(ValueError):
                Action(strength=bad)
        for valid in (0.0, 0.25, 0.5, 1.0):
            self.assertEqual(Action(strength=valid).strength, valid)

    def test_zero_direction_or_no_escape_has_no_impulse(self):
        np.testing.assert_array_equal(self.delta(1.0, 0.0, 0.0), [0.0, 0.0])
        np.testing.assert_array_equal(self.delta(1.0, escape=False), [0.0, 0.0])

    def test_turn_is_independent_of_escape_strength(self):
        cfg = copy.deepcopy(CONFIG)
        cfg["fly"]["wander_speed"] = 0.0
        world = World(cfg, 19)
        world.tick(0.02, Action(escape=True, lateral=1.0, strength=0.0, turn=0.5))
        self.assertAlmostEqual(world.fly.heading, 0.5 * cfg["fly"]["turn_rate"] * 0.02)

    def test_fixed_policy_separates_direction_from_strength(self):
        actions = []
        for total in (1.0, 2.0):
            policy = FixedEscapePolicy(1.0, 0.4, 0.02)
            motor = MotorState(total, 0.0, 0.0, 0.0, np.zeros(1))
            actions.append(policy.decide(motor))
        self.assertEqual([a.strength for a in actions], [0.5, 1.0])
        self.assertEqual([a.lateral for a in actions], [1.0, 1.0])
        self.assertEqual([a.forward for a in actions], [0.35, 0.35])


class TestCalibrationValidation(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.cfg = copy.deepcopy(CONFIG)

    def record(self, rel, config=None, provenance=None, threshold=1.25):
        path = self.root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        data = {"escape_threshold": threshold,
                "provenance": calibration_provenance(config or self.cfg)}
        if provenance is not None:
            data["provenance"] = provenance
        path.write_text(json.dumps(data))
        return path

    def reject(self, config):
        with self.assertRaisesRegex(ValueError, "python tools/calibrate_escape.py --trials 28"):
            resolve_escape_threshold(config, self.root)

    def test_matching_calibration_is_accepted(self):
        self.record("results/game/calibration.json")
        source = resolve_escape_threshold(self.cfg, self.root)
        self.assertEqual(source.threshold, 1.25)
        self.assertEqual(source.origin, "results/game/calibration.json")

    def test_config_key_order_does_not_invalidate_semantic_match(self):
        self.record("results/game/calibration.json")
        reordered = dict(reversed(list(self.cfg.items())))
        self.assertEqual(resolve_escape_threshold(reordered, self.root).threshold, 1.25)

    def test_modified_brain_gain_is_rejected(self):
        self.record("results/game/calibration.json")
        self.cfg["brain"]["gain"] += 0.1
        self.reject(self.cfg)

    def test_modified_encoder_setting_is_rejected(self):
        self.record("results/game/calibration.json")
        self.cfg["encoder"]["loom_gain"] += 1
        self.reject(self.cfg)

    def test_stale_artifacts_do_not_override_matching_committed_record(self):
        stale = copy.deepcopy(self.cfg)
        stale["encoder"]["encoder_seed"] += 1
        self.record("artifacts/game/calibration.json", stale, threshold=99.0)
        self.record("results/game/calibration.json", threshold=1.25)
        source = resolve_escape_threshold(self.cfg, self.root)
        self.assertEqual(source.origin, "results/game/calibration.json")
        self.assertEqual(source.threshold, 1.25)

    def test_flybrain_version_mismatch_is_rejected(self):
        provenance = calibration_provenance(self.cfg)
        provenance["flybrain_version"] = "0.0.0"
        self.record("results/game/calibration.json", provenance=provenance)
        self.reject(self.cfg)

    def test_sensory_flag_or_time_step_change_is_rejected(self):
        self.record("results/game/calibration.json")
        for section, key, value in (("brain", "sensory_input", True),
                                     ("sim", "tick_seconds", 0.01)):
            changed = copy.deepcopy(self.cfg)
            changed[section][key] = value
            with self.subTest(key=key):
                self.reject(changed)

    def test_legacy_measurement_protocol_is_rejected(self):
        provenance = calibration_provenance(self.cfg)
        provenance["measurement_protocol"] = "wandering-fly-v1"
        self.record("results/game/calibration.json", provenance=provenance)
        self.reject(self.cfg)

    def test_missing_calibration_fails_with_command(self):
        self.reject(self.cfg)

    def test_session_rejects_mismatch_before_loading_brain(self):
        self.record("results/game/calibration.json")
        self.cfg["brain"]["gain"] += 1
        with patch("game.session.build_brain") as loader:
            with self.assertRaises(ValueError):
                Session(self.cfg, root=self.root)
            loader.assert_not_called()

    def test_time_step_must_match_brain(self):
        self.cfg["sim"]["tick_seconds"] = 0.01
        with self.assertRaisesRegex(ValueError, "must equal"):
            Session(self.cfg, policy=BarePolicy(), root=self.root)

    def test_raw_threshold_does_not_bypass_validation(self):
        self.cfg["policy"]["escape_threshold"] = 1.45
        self.reject(self.cfg)

    def test_invalid_artifact_falls_back_to_matching_record(self):
        path = self.record("artifacts/game/calibration.json")
        path.write_text("[]")
        self.record("results/game/calibration.json")
        self.assertEqual(resolve_escape_threshold(self.cfg, self.root).threshold, 1.25)


class TestFixedFlyCalibration(unittest.TestCase):
    def test_frozen_world_ignores_wander_escape_and_initial_velocity(self):
        world = World(CONFIG, 11)
        world.fly_motion_enabled = False
        world.collisions_enabled = False
        expected = world.fly.x, world.fly.y, world.fly.heading
        world.fly.vx, world.fly.vy = 100.0, -100.0
        world.swatter.x, world.swatter.y = world.fly.x, world.fly.y
        world.request_strike()
        for _ in range(130):
            world.tick(.02, Action(escape=True, lateral=1.0, strength=1.0, turn=1.0))
            self.assertEqual((world.fly.x, world.fly.y, world.fly.heading), expected)
            self.assertEqual((world.fly.vx, world.fly.vy), (0.0, 0.0))
        self.assertTrue(world.fly.alive)
        self.assertEqual(world._wander_timer, 0.0)
        world.reset(12)
        self.assertFalse(world.fly_motion_enabled)
        self.assertFalse(world.collisions_enabled)

    def test_real_calibration_trial_keeps_fly_fixed(self):
        from tools.calibrate_escape import RecordingPolicy, _trial
        policy = RecordingPolicy()
        session = Session(CONFIG, brain=shared_brain(), policy=policy)
        session.world.fly_motion_enabled = False
        session.world.collisions_enabled = False
        _trial(session, policy, 5000, (10.0, 10.0), 90, 20)
        fly = session.world.fly
        self.assertEqual((fly.x, fly.y), (CONFIG["world"]["width"] * .5,
                                          CONFIG["world"]["height"] * .62))
        self.assertEqual((fly.vx, fly.vy, fly.heading), (0.0, 0.0, 0.0))
        self.assertTrue(fly.alive)
        self.assertFalse(session.fly_loop.last_action.escape)


class TestOptionalPolicyHUD(unittest.TestCase):
    def make_app(self, policy):
        import pygame
        from game.app import App
        self.addCleanup(pygame.quit)
        session = Session(CONFIG, brain=shared_brain(), policy=policy)
        with patch("game.app.Session", return_value=session):
            app = App(CONFIG)
        app.font_small = Mock(wraps=app.font_small)
        return app

    def test_bare_policy_can_render_without_diagnostics(self):
        policy = BarePolicy()
        self.assertIsInstance(policy, Policy)
        app = self.make_app(policy)
        app._advance(0.02, False)
        app._draw()
        self.assertEqual(app.session.policy_diagnostics, {})
        strings = [call.args[0] for call in app.font_small.render.call_args_list]
        self.assertFalse(any("threshold" in s or "refractory" in s for s in strings))

    def test_partial_diagnostics_hide_only_missing_elements(self):
        class PartialPolicy(BarePolicy):
            def diagnostics(self):
                return {"refractory_seconds": 0.1}
        app = self.make_app(PartialPolicy())
        app._draw()
        strings = [call.args[0] for call in app.font_small.render.call_args_list]
        self.assertTrue(any("refractory" in s for s in strings))
        self.assertFalse(any("threshold" in s for s in strings))

    def test_fixed_policy_diagnostics_are_returned_as_a_copy(self):
        policy = FixedEscapePolicy(1.45, 0.4, 0.02)
        app = self.make_app(policy)
        diagnostics = app.session.policy_diagnostics
        self.assertEqual(diagnostics, {"escape_threshold": 1.45, "refractory_seconds": 0.0})
        diagnostics["escape_threshold"] = 99
        self.assertEqual(app.session.policy_diagnostics["escape_threshold"], 1.45)
        app._draw()


if __name__ == "__main__":
    unittest.main(verbosity=2)
