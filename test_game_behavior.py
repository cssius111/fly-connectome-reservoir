"""M1.2 behavior regressions. These do not replace a human playtest."""
import os
import copy
import unittest
from unittest.mock import patch, Mock

os.environ.setdefault("NUMBA_NUM_THREADS", "4")
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import numpy as np
from game.action import Action, FixedEscapePolicy, MotorState
from game.perception import Retina
from game.session import Session
from game.world import World
from test_game import CONFIG, shared_brain
from tools.chase_sanity import chase, summarize, SEEDS, APPROACH_TICK, CLICK_TICK

DT = CONFIG["sim"]["tick_seconds"]


class TestTonicFlight(unittest.TestCase):
    @staticmethod
    def trajectory(seed, ticks=300, saccades=True):
        cfg = copy.deepcopy(CONFIG)
        cfg["saccades"]["enabled"] = saccades
        world = World(cfg, seed)
        rows = []
        for _ in range(ticks):
            world.tick(DT)
            f = world.fly
            rows.append([f.x, f.y, f.vx, f.vy, f.heading])
        return np.array(rows)

    def test_idle_fly_travels_without_any_policy_or_player_input(self):
        rows = self.trajectory(101)
        distance = np.linalg.norm(np.diff(rows[:, :2], axis=0), axis=1).sum()
        self.assertGreater(distance, 400.0)
        self.assertLess(distance, 550.0)
        self.assertGreater(np.linalg.norm(rows[-1, :2] - rows[0, :2]), 300.0)

    def test_cruise_is_deterministic_for_seed(self):
        np.testing.assert_array_equal(self.trajectory(17), self.trajectory(17))
        self.assertFalse(np.array_equal(self.trajectory(17), self.trajectory(18)))

    def test_cruise_has_smooth_velocity_and_heading(self):
        # Retain the M1.2 inter-saccade drift bound; M1.3 separately tests
        # the bounded heading pulses that deliberately exceed that drift rate.
        rows = self.trajectory(101, 200, saccades=False)
        acceleration = np.linalg.norm(np.diff(rows[:, 2:4], axis=0), axis=1) / DT
        heading_step = np.abs(np.diff(np.unwrap(rows[:, 4])))
        self.assertLess(acceleration.max(), 260.0)
        self.assertLess(heading_step.max(), 0.01)
        speed = np.linalg.norm(rows[:, 2:4], axis=1)
        self.assertLessEqual(speed.max(), CONFIG["fly"]["baseline_speed"] + 1e-6)
        self.assertLess(speed.max(), CONFIG["fly"]["escape_impulse"] * 0.2)

    def test_long_cruise_does_not_park_on_wall_or_teleport(self):
        rows = self.trajectory(101, 3000)
        speed = np.linalg.norm(rows[50:, 2:4], axis=1)
        self.assertGreater(speed.min(), 50.0)
        steps = np.linalg.norm(np.diff(rows[:, :2], axis=0), axis=1)
        self.assertLessEqual(steps.max(), CONFIG["fly"]["baseline_speed"] * DT + 1e-6)
        self.assertTrue(np.all(rows[:, 0] >= CONFIG["world"]["margin"]))
        self.assertTrue(np.all(rows[:, 0] <= CONFIG["world"]["width"] - CONFIG["world"]["margin"]))


class TestNeuralSteering(unittest.TestCase):
    @staticmethod
    def motor(left, right, steer_left=0, steer_right=0):
        return MotorState(left, right, steer_left, steer_right, np.zeros(1))

    def test_subthreshold_activity_causes_opposite_alert_turns(self):
        turns = []
        for side in (-1, 1):
            policy = FixedEscapePolicy(1.45, .4, DT)
            motor = self.motor(1.0 if side < 0 else 0.0, 1.0 if side > 0 else 0.0)
            actions = [policy.decide(motor) for _ in range(10)]
            self.assertFalse(any(a.escape for a in actions))
            self.assertEqual(policy.diagnostics()["behavior_state"], "ALERT")
            turns.append(actions[-1].turn)
        self.assertGreater(turns[0], 0)
        self.assertLess(turns[1], 0)
        self.assertAlmostEqual(turns[0], -turns[1])

    def test_neural_steering_does_not_jump_when_laterality_flips(self):
        policy = FixedEscapePolicy(1.45, .4, DT)
        actions = [policy.decide(self.motor(1, 0)) for _ in range(20)]
        before = actions[-1].turn
        after = policy.decide(self.motor(0, 1)).turn
        self.assertGreater(after, 0.0, "steering should smoothly pass through zero")
        self.assertLess(abs(after - before), 0.1)

    def test_dna02_alone_cannot_trigger_threat_behavior(self):
        policy = FixedEscapePolicy(1.45, .4, DT)
        for _ in range(20):
            action = policy.decide(self.motor(0, 0, 50, 0))
            self.assertFalse(action.escape)
            self.assertEqual(action.turn, 0.0)
            self.assertEqual(policy.diagnostics()["behavior_state"], "CALM")

    def test_one_contralateral_spike_does_not_reverse_developing_escape(self):
        policy = FixedEscapePolicy(1.45, .4, DT)
        alert = policy.decide(self.motor(1.0, 0.0))
        escape = policy.decide(self.motor(.82, 1.0))
        self.assertGreater(alert.turn, 0.0)
        self.assertTrue(escape.escape)
        self.assertGreater(escape.lateral, 0.0)

    def test_dna02_cannot_reverse_dnp01_away_turn(self):
        policy = FixedEscapePolicy(1.45, .4, DT)
        action = policy.decide(self.motor(1.0, .9, 0, 50))
        self.assertGreater(action.turn, 0.0)
        self.assertGreater(action.lateral, 0.0)

    def test_symmetric_escape_has_no_arbitrary_right_bias(self):
        policy = FixedEscapePolicy(1.45, .4, DT)
        action = policy.decide(self.motor(2, 2))
        self.assertTrue(action.escape)
        self.assertEqual(action.lateral, 0.0)
        self.assertEqual(action.turn, 0.0)
        self.assertGreater(action.forward, 0.0)

    def test_real_connectome_opposite_loom_sides_produce_opposite_turns(self):
        turns = []
        for side in (-.5, .5):
            session = Session(CONFIG, brain=shared_brain(), seed=101)
            actions = [session.fly_loop.step(Retina(.35, .8, side)) for _ in range(25)]
            turns.append(sum(a.turn for a in actions))
        self.assertGreater(turns[0], .1)
        self.assertLess(turns[1], -.1)


class TestPreStrikeBehavior(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        session = Session(CONFIG, brain=shared_brain())
        cls.trials = {seed: chase(session, seed) for seed in SEEDS}

    def test_approach_evades_before_click_and_before_first_lethal_frame(self):
        for seed, rows in self.trials.items():
            with self.subTest(seed=seed):
                summary = summarize(rows, DT)
                self.assertTrue(summary["pre_click_evasion"])
                self.assertGreater(summary["lead_before_lethal_seconds"], .3)
                self.assertGreater(summary["path_before_click"], 100.0)
                approach = rows[APPROACH_TICK:CLICK_TICK]
                self.assertTrue(all(r["phase"] == "idle" for r in approach))
                self.assertTrue(any(abs(r["turn"]) > .03 for r in approach))
                self.assertTrue(any(r["dnp01_left"] + r["dnp01_right"] > .8 for r in approach))

    def test_closed_loop_trajectory_is_continuous(self):
        for rows in self.trials.values():
            self.assertLessEqual(max(r["distance_moved"] for r in rows),
                                 CONFIG["fly"]["max_speed"] * DT + 1e-6)
            angles = np.unwrap([r["heading"] for r in rows])
            self.assertLess(np.abs(np.diff(angles)).max(), .14)

    def test_stationary_distant_swatter_has_no_emergency_in_six_seconds(self):
        for seed in SEEDS:
            with self.subTest(seed=seed):
                session = Session(CONFIG, brain=shared_brain(), seed=seed)
                escaped = []
                for _ in range(300):
                    session.tick()
                    escaped.append(session.fly_loop.last_action.escape)
                self.assertFalse(any(escaped))
                self.assertEqual(session.stats.strikes, 0)

    def test_silenced_connectome_removes_evasion_but_preserves_cruise(self):
        session = Session(CONFIG, brain=shared_brain(), seed=101)
        with patch.object(session.brain, "step", return_value=np.empty(0, dtype=np.int64)):
            rows = chase(session, 101)
        approach = rows[APPROACH_TICK:CLICK_TICK]
        self.assertGreater(max(r["theta_dot"] for r in approach), .5)
        self.assertTrue(all(r["turn"] == 0 and not r["escape"] for r in approach))
        self.assertGreater(sum(r["distance_moved"] for r in rows[:CLICK_TICK]), 100)

    def test_strike_is_stronger_than_ordinary_hover_approach(self):
        # Matched fixed-fly measurement isolates sensory strength from escape
        # motion; the moving-fly first-strike test above exercises real play.
        session = Session(CONFIG, brain=shared_brain(), seed=101)
        w = session.world
        w.fly_motion_enabled = False
        w.collisions_enabled = False
        w.swatter.x, w.swatter.y = w.fly.x, w.fly.y - 400
        w.set_pointer(w.swatter.x, w.swatter.y)
        rows = []
        for t in range(105):
            pointer = (w.fly.x, w.fly.y - (400 if t < 50 else 10))
            session.tick(pointer=pointer, strike=t == 85)
            d = session.encoder.last_drive
            rows.append([session.last_retina.theta_dot,
                         max(d["loomL"], d["loomR"]),
                         max(d["threatL"], d["threatR"]),
                         session.fly_loop.last_motor.dnp01_total])
        approach = np.max(rows[50:85], axis=0)
        strike = np.max(rows[85:100], axis=0)
        self.assertTrue(np.all(strike > approach), (approach, strike))

    def test_raw_mouse_state_is_still_rejected_during_chase(self):
        session = Session(CONFIG, brain=shared_brain())
        for value in ({"mouse_x": 640, "mouse_y": 360}, session.world, (640, 360)):
            with self.assertRaises(TypeError):
                session.fly_loop.step(value)


class TestBehaviorHUD(unittest.TestCase):
    def test_diagnostics_render_all_required_playtest_values_inside_panel(self):
        import pygame
        from game.app import App
        session = Session(CONFIG, brain=shared_brain())
        self.addCleanup(pygame.quit)
        with patch("game.app.Session", return_value=session):
            app = App(CONFIG)
        app._advance(.02, False)
        app.font_small = Mock(wraps=app.font_small)
        app._draw()
        strings = [c.args[0] for c in app.font_small.render.call_args_list]
        for label in ("state CALM", "retina theta", "d/dt", "cruise", "speed", "escape strength",
                      "LPLC2 loom L", "LC4 threat L", "DNp01 left", "DNp01 right",
                      "saccade", "DNa02 L/R", "seed"):
            self.assertTrue(any(label in s for s in strings), label)
        # All full-width information rows fit within the 380px panel padding.
        for text in strings:
            if text.startswith(("state", "retina", "cruise", "escape strength", "brain", "LC4 ", "threshold", "saccade", "DNa02", "seed")):
                self.assertLessEqual(app.font_small.size(text)[0], 356, text)
        app.show_neural = False
        app._draw()


if __name__ == "__main__":
    unittest.main(verbosity=2)
