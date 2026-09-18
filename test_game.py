"""Tests for the fly-swatter game components.

Run:  .venv\\Scripts\\python.exe test_game.py

The first six classes are the critical ones named in the milestone brief: the
perceptual bottleneck, encoder purity, escape laterality, loom dependence,
strike-window lethality, and fixed-timestep determinism.

Tests that need the connectome share one `FlyBrain` (loading and JIT are the
expensive part, ~2 s) and reset it per test, which is exactly how the game uses
it between runs.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import unittest
from pathlib import Path

os.environ.setdefault("NUMBA_NUM_THREADS", "4")

import numpy as np

from game.action import Action, FixedEscapePolicy, MotorState
from game.fly import ROOT, FlyLoop, build_brain
from game.perception import Retina, RetinaProjector, RetinalEncoder
from game.session import Session, load_config, resolve_escape_threshold
from game.world import StrikePhase, World

CONFIG = load_config(ROOT / "game_config.json")
_SHARED: dict = {}


def shared_brain():
    if "brain" not in _SHARED:
        _SHARED["brain"] = build_brain(CONFIG, ROOT)
    return _SHARED["brain"]


def shared_encoder():
    if "encoder" not in _SHARED:
        _SHARED["encoder"] = RetinalEncoder(shared_brain(), CONFIG)
    return _SHARED["encoder"]


def make_policy(threshold: float | None = None) -> FixedEscapePolicy:
    thr = resolve_escape_threshold(CONFIG, ROOT).threshold if threshold is None else threshold
    return FixedEscapePolicy(threshold=thr,
                             refractory_seconds=float(CONFIG["policy"]["refractory_seconds"]),
                             tick_seconds=float(CONFIG["sim"]["tick_seconds"]),
                             forward_bias=float(CONFIG["fly"]["escape_forward_bias"]),
                             turn_gain=float(CONFIG["policy"]["turn_gain"]))


def loop_with(threshold: float | None = None) -> FlyLoop:
    return FlyLoop(shared_brain(), shared_encoder(), make_policy(threshold), CONFIG)


def loom_sequence(azimuth: float, ticks: int = 20) -> list[Retina]:
    """A strong, sustained looming stimulus on one side."""
    return [Retina(theta=0.5 + 0.09 * t, theta_dot=9.0, azimuth=azimuth) for t in range(ticks)]


def still_sequence(azimuth: float, ticks: int = 20) -> list[Retina]:
    """Object present at the same angular size, not expanding: no loom."""
    return [Retina(theta=0.5, theta_dot=0.0, azimuth=azimuth) for t in range(ticks)]


# --- 1. the perceptual bottleneck -----------------------------------------
class TestRawStateCannotReachTheBrain(unittest.TestCase):
    def test_flyloop_rejects_non_retina_inputs(self):
        loop = loop_with()
        loop.reset(1)
        world = World(CONFIG, seed=1)
        for bad in (world, world.fly, world.swatter, (640.0, 360.0),
                    {"x": 640.0, "y": 360.0}, [0.1, 0.2, 0.3], 0.5, None):
            with self.subTest(bad=type(bad).__name__):
                with self.assertRaises(TypeError):
                    loop.step(bad)

    def test_flyloop_rejects_retina_subclass_carrying_mouse(self):
        """A lookalike with extra fields must not slip through isinstance."""
        class SneakyRetina(Retina):
            __slots__ = ()

        loop = loop_with()
        loop.reset(1)
        with self.assertRaises(TypeError):
            loop.step(SneakyRetina(theta=0.5, theta_dot=1.0, azimuth=0.2))

    def test_retina_is_frozen_and_slotted(self):
        r = Retina(theta=0.5, theta_dot=1.0, azimuth=0.2)
        with self.assertRaises(Exception):
            r.theta = 9.0                                  # frozen
        with self.assertRaises((AttributeError, TypeError)):
            r.mouse_x = 640.0                              # no new attributes
        self.assertFalse(hasattr(r, "__dict__"), "Retina must not carry an instance dict")
        self.assertEqual(set(Retina.__slots__), {"theta", "theta_dot", "azimuth"})
        self.assertEqual(set(Retina.__dataclass_fields__), {"theta", "theta_dot", "azimuth"})

    def test_flyloop_has_no_reference_to_world(self):
        loop = loop_with()
        for name, value in vars(loop).items():
            self.assertNotIsInstance(value, World, f"FlyLoop.{name} holds a World")


# --- 2. encoder purity -----------------------------------------------------
class TestEncoderIsPureFunctionOfRetina(unittest.TestCase):
    def _injection(self, enc, retina):
        return [(idx.tolist(), round(float(amount), 12)) for idx, amount in enc.inject(retina)]

    def test_equal_retina_gives_identical_injection(self):
        enc = shared_encoder()
        r = Retina(theta=0.8, theta_dot=6.0, azimuth=-0.3)
        first = self._injection(enc, r)
        # Drive the encoder through a completely different history, then repeat.
        for other in loom_sequence(+0.7) + still_sequence(-0.9):
            enc.inject(other)
        second = self._injection(enc, r)
        self.assertEqual(first, second)
        # And an independently constructed, equal Retina must agree too.
        third = self._injection(enc, Retina(theta=0.8, theta_dot=6.0, azimuth=-0.3))
        self.assertEqual(first, third)
        self.assertTrue(first, "expected a non-empty injection for a looming stimulus")

    def test_populations_are_balanced_left_right(self):
        enc = shared_encoder()
        for channel in ("loom", "threat"):
            pop = enc.population[channel]
            self.assertEqual(pop["used_per_side"], min(pop["available_L"], pop["available_R"]))
        self.assertEqual(enc.population["threat"]["used_per_side"], 55)   # LC4: 71 L / 55 R
        self.assertEqual(enc.population["loom"]["used_per_side"], 91)     # LPLC2: 94 L / 91 R

    def test_population_choice_is_deterministic(self):
        a = RetinalEncoder(shared_brain(), CONFIG)
        b = RetinalEncoder(shared_brain(), CONFIG)
        ra = Retina(theta=0.9, theta_dot=7.0, azimuth=0.4)
        for (ia, va), (ib, vb) in zip(a.inject(ra), b.inject(ra)):
            np.testing.assert_array_equal(ia, ib)
            self.assertAlmostEqual(float(va), float(vb), places=12)

    def test_threat_needs_both_size_and_expansion(self):
        enc = shared_encoder()
        self.assertGreater(enc.threat_level(Retina(1.2, 9.0, 0.1)), 0.5)
        self.assertEqual(enc.threat_level(Retina(1.2, 0.0, 0.1)), 0.0)   # big but not growing
        self.assertEqual(enc.threat_level(Retina(0.0, 9.0, 0.1)), 0.0)   # growing but tiny
        self.assertEqual(enc.threat_level(Retina(1.2, -9.0, 0.1)), 0.0)  # receding


# --- 3. escape laterality --------------------------------------------------
class TestEscapeDirection(unittest.TestCase):
    def _first_escape(self, azimuth):
        loop = loop_with()
        loop.reset(31)
        for retina in loom_sequence(azimuth, ticks=25):
            action = loop.step(retina)
            if action.escape:
                return action, loop.last_motor
        return None, loop.last_motor

    def test_left_and_right_loom_escape_in_opposite_directions(self):
        left_action, left_motor = self._first_escape(-0.5)
        right_action, right_motor = self._first_escape(+0.5)
        self.assertIsNotNone(left_action, "strong left loom failed to trigger an escape")
        self.assertIsNotNone(right_action, "strong right loom failed to trigger an escape")
        # DNp01 responds ipsilaterally to the looming side...
        self.assertGreater(left_motor.dnp01_left, left_motor.dnp01_right)
        self.assertGreater(right_motor.dnp01_right, right_motor.dnp01_left)
        # ...and the fly moves away from it: left threat -> to its own right.
        self.assertGreater(left_action.lateral, 0.0)
        self.assertLess(right_action.lateral, 0.0)
        self.assertEqual(np.sign(left_action.lateral), -np.sign(right_action.lateral))

    def test_world_turns_lateral_command_into_motion_away_from_threat(self):
        """+lateral must actually move the fly to its own right in world space."""
        world = World(CONFIG, seed=5)
        world.fly.heading = 0.0                     # facing +x, so its right is +y
        y0 = world.fly.y
        world.tick(0.02, Action(escape=True, lateral=1.0, forward=0.0))
        self.assertGreater(world.fly.vy, 0.0)
        self.assertGreater(world.fly.y, y0)


# --- 4. loom dependence ----------------------------------------------------
class TestEscapeRequiresLoom(unittest.TestCase):
    def _escape_count(self, sequence_fn, seeds=(41, 42, 43, 44)):
        total = 0
        for seed in seeds:
            loop = loop_with()
            loop.reset(seed)
            for retina in sequence_fn():
                total += int(loop.step(retina).escape)
        return total

    def test_no_loom_does_not_trigger_like_strong_loom(self):
        loom = self._escape_count(lambda: loom_sequence(-0.4, ticks=30))
        none = self._escape_count(lambda: [Retina(0.0, 0.0, 0.0) for _ in range(30)])
        still = self._escape_count(lambda: still_sequence(-0.4, ticks=30))
        self.assertGreater(loom, 0, "strong loom never triggered an escape")
        self.assertEqual(none, 0, f"escape fired {none} times with no stimulus at all")
        self.assertEqual(still, 0, f"escape fired {still} times for a non-expanding object")
        self.assertGreater(loom, still)

    def test_threshold_comes_from_a_recorded_calibration(self):
        self.assertIsNone(CONFIG["policy"]["escape_threshold"],
                          "threshold must not be hand-written into game_config.json")
        source = resolve_escape_threshold(CONFIG, ROOT)
        self.assertGreater(source.threshold, 0.0)
        record = json.loads((ROOT / source.origin).read_text(encoding="utf-8"))
        self.assertEqual(record["escape_threshold"], source.threshold)
        self.assertEqual(record["false_trigger_ticks"], 0)
        self.assertTrue(record["detection_target_met"])
        # The recorded distributions must actually separate.
        self.assertGreater(record["loom"]["min_peak"], record["no_loom"]["max"])
        self.assertGreater(source.threshold, record["no_loom"]["max"])
        self.assertLess(source.threshold, record["loom"]["min_peak"])

    def test_calibration_is_not_stale(self):
        """Retuning the config without recalibrating must not pass silently."""
        source = resolve_escape_threshold(CONFIG, ROOT)
        record = json.loads((ROOT / source.origin).read_text(encoding="utf-8"))
        current = hashlib.sha256((ROOT / "game_config.json").read_bytes()).hexdigest()
        self.assertEqual(record["config_sha256"], current,
                         "game_config.json changed since calibration; "
                         "re-run python tools/calibrate_escape.py")


# --- 5. strike-window lethality -------------------------------------------
class TestStrikeWindow(unittest.TestCase):
    def _world_with_fly_under_paddle(self):
        world = World(CONFIG, seed=7)
        world.swatter.x, world.swatter.y = world.fly.x, world.fly.y
        world.set_pointer(world.fly.x, world.fly.y)
        return world

    def test_collision_is_only_lethal_during_the_active_window(self):
        world = self._world_with_fly_under_paddle()
        dt = 0.02
        # Hovering on top of the fly, no strike: never lethal.
        for _ in range(40):
            world.tick(dt)
            world.fly.x, world.fly.y = world.swatter.x, world.swatter.y
        self.assertTrue(world.fly.alive)
        self.assertEqual(world.stats.hits, 0)

        self.assertTrue(world.request_strike())
        # Collision is resolved after the phase advances, so the phase that
        # matters is the one in effect once the tick has run.
        phases_seen, killed_in = set(), None
        for _ in range(60):
            world.fly.x, world.fly.y = world.swatter.x, world.swatter.y
            events = world.tick(dt)
            phases_seen.add(world.swatter.phase)
            if events.hit:
                killed_in = world.swatter.phase
                break
        self.assertIsNotNone(killed_in, "a centred strike never hit a stationary fly")
        self.assertIs(killed_in, StrikePhase.ACTIVE)
        self.assertIn(StrikePhase.WINDUP, phases_seen)
        self.assertFalse(world.fly.alive)
        self.assertEqual(world.stats.hits, 1)

    def test_windup_is_not_lethal(self):
        dt = 0.02
        world = self._world_with_fly_under_paddle()
        world.request_strike()
        windup_ticks = 0
        # Tick only while the *next* tick is guaranteed to stay in the wind-up.
        while world.swatter.phase_elapsed + dt < world.windup_seconds:
            world.fly.x, world.fly.y = world.swatter.x, world.swatter.y
            self.assertFalse(world.tick(dt).hit)
            self.assertIs(world.swatter.phase, StrikePhase.WINDUP)
            windup_ticks += 1
        self.assertGreater(windup_ticks, 0)
        self.assertTrue(world.fly.alive)
        self.assertEqual(world.stats.hits, 0)

    def test_cooldown_is_not_lethal(self):
        dt = 0.02
        world = self._world_with_fly_under_paddle()
        world.request_strike()
        # Stay well clear until the lethal window is over.
        while world.swatter.phase is not StrikePhase.COOLDOWN:
            world.fly.x, world.fly.y = 10.0, 10.0
            self.assertFalse(world.tick(dt).hit)
        cooldown_ticks = 0
        while world.swatter.phase is StrikePhase.COOLDOWN:
            world.fly.x, world.fly.y = world.swatter.x, world.swatter.y
            self.assertFalse(world.tick(dt).hit)
            cooldown_ticks += 1
        self.assertGreater(cooldown_ticks, 0)
        self.assertTrue(world.fly.alive)
        self.assertEqual(world.stats.hits, 0)

    def test_strike_phase_durations_match_the_brief(self):
        dt = 0.001
        world = World(CONFIG, seed=3)
        world.request_strike()
        counts = {p: 0 for p in StrikePhase}
        for _ in range(3000):
            counts[world.swatter.phase] += 1
            world.tick(dt)
            if world.swatter.phase is StrikePhase.IDLE and counts[StrikePhase.COOLDOWN]:
                break
        self.assertAlmostEqual(counts[StrikePhase.WINDUP] * dt, 0.15, delta=0.01)
        self.assertAlmostEqual(counts[StrikePhase.ACTIVE] * dt, 0.08, delta=0.01)
        self.assertAlmostEqual(counts[StrikePhase.COOLDOWN] * dt, 0.32, delta=0.01)
        self.assertTrue(0.12 <= counts[StrikePhase.WINDUP] * dt <= 0.18)
        self.assertTrue(0.06 <= counts[StrikePhase.ACTIVE] * dt <= 0.10)
        self.assertTrue(0.25 <= counts[StrikePhase.COOLDOWN] * dt <= 0.40)

    def test_a_hit_is_not_also_counted_as_a_miss(self):
        """strikes == hits + misses, and a kill scores no escape. The hit lands
        on an ACTIVE tick while the window closes later, so this is easy to get
        wrong."""
        world = self._world_with_fly_under_paddle()
        world.request_strike()
        for _ in range(80):
            if world.fly.alive:
                world.fly.x, world.fly.y = world.swatter.x, world.swatter.y
            world.tick(0.02)
        st = world.stats
        self.assertEqual(st.hits, 1)
        self.assertEqual(st.misses, 0)
        self.assertEqual(st.escapes, 0)
        self.assertEqual(st.strikes, st.hits + st.misses)
        self.assertEqual(st.hit_rate, 1.0)

    def test_strikes_always_equal_hits_plus_misses(self):
        world = World(CONFIG, seed=11)
        for t in range(1500):
            world.set_pointer(world.fly.x, world.fly.y)
            if t % 40 == 0:
                world.request_strike()
            world.tick(0.02, Action(escape=(t % 40 == 9), lateral=1.0, forward=0.3))
            if not world.fly.alive and world.splat_finished:
                break
        st = world.stats
        self.assertGreater(st.strikes, 0)
        self.assertEqual(st.strikes, st.hits + st.misses)
        self.assertLessEqual(st.escapes, st.misses)

    def test_strike_cannot_be_retriggered_before_cooldown_ends(self):
        world = World(CONFIG, seed=3)
        self.assertTrue(world.request_strike())
        for _ in range(20):
            self.assertFalse(world.request_strike())
            world.tick(0.02)
        self.assertEqual(world.stats.strikes, 1)


# --- 6. fixed-timestep determinism ----------------------------------------
class TestDeterminism(unittest.TestCase):
    @staticmethod
    def _recorded_input(ticks=150):
        rng = np.random.default_rng(2026)
        script = []
        for t in range(ticks):
            script.append(((640.0 + 300.0 * math.sin(t * 0.06), 360.0 + 180.0 * math.cos(t * 0.05)),
                           bool(rng.random() < 0.03)))
        return script

    def _run(self, session, script):
        session.reset(12345)
        states = []
        for pointer, strike in script:
            session.tick(pointer=pointer, strike=strike)
            states.append(session.state_vector())
        return np.array(states)

    def test_same_seed_and_input_gives_identical_trajectory(self):
        script = self._recorded_input()
        session = Session(CONFIG, brain=shared_brain(), policy=make_policy(), root=ROOT)
        first = self._run(session, script)
        second = self._run(session, script)
        np.testing.assert_array_equal(first, second)
        self.assertGreater(np.abs(np.diff(first[:, 6])).sum(), 0.0, "the fly never moved")

    def test_different_seed_diverges(self):
        script = self._recorded_input(80)
        session = Session(CONFIG, brain=shared_brain(), policy=make_policy(), root=ROOT)

        def trajectory(seed):
            session.reset(seed)
            out = []
            for pointer, strike in script:
                session.tick(pointer=pointer, strike=strike)
                out.append(session.state_vector())
            return np.array(out)

        self.assertFalse(np.array_equal(trajectory(12345), trajectory(999)))


# --- swatter and fly physics ----------------------------------------------
class TestPhysics(unittest.TestCase):
    def test_swatter_cannot_teleport(self):
        world = World(CONFIG, seed=2)
        dt = 0.02
        limit = world.max_tracking_speed * dt + 1e-9
        world.set_pointer(world.width, world.height)
        for _ in range(200):
            before = (world.swatter.x, world.swatter.y)
            world.tick(dt)
            moved = math.hypot(world.swatter.x - before[0], world.swatter.y - before[1])
            self.assertLessEqual(moved, limit)

    def test_swatter_eventually_reaches_the_pointer(self):
        world = World(CONFIG, seed=2)
        world.set_pointer(900.0, 500.0)
        for _ in range(200):
            world.tick(0.02)
        self.assertAlmostEqual(world.swatter.x, 900.0, delta=2.0)
        self.assertAlmostEqual(world.swatter.y, 500.0, delta=2.0)

    def test_escape_is_an_impulse_not_a_teleport(self):
        world = World(CONFIG, seed=2)
        before = (world.fly.x, world.fly.y)
        world.tick(0.02, Action(escape=True, lateral=1.0, forward=0.35))
        jump = math.hypot(world.fly.x - before[0], world.fly.y - before[1])
        self.assertLess(jump, world.max_speed * 0.02 + 1e-6)
        self.assertGreater(math.hypot(world.fly.vx, world.fly.vy), 0.0)

    def test_fly_stays_inside_the_playable_region(self):
        world = World(CONFIG, seed=2)
        for t in range(1200):
            action = Action(escape=(t % 7 == 0), lateral=1.0 if t % 14 else -1.0, forward=1.0)
            world.tick(0.02, action)
            self.assertTrue(world.margin <= world.fly.x <= world.width - world.margin)
            self.assertTrue(world.margin <= world.fly.y <= world.height - world.margin)

    def test_refractory_blocks_repeat_escapes(self):
        policy = make_policy(threshold=0.5)
        strong = MotorState(dnp01_left=5.0, dnp01_right=0.0, dna02_left=0.0,
                            dna02_right=0.0, trace=np.zeros(1))
        fired = [policy.decide(strong).escape for _ in range(30)]
        self.assertTrue(fired[0])
        expected = int(round(float(CONFIG["policy"]["refractory_seconds"])
                             / float(CONFIG["sim"]["tick_seconds"])))
        self.assertEqual(sum(fired[1:1 + expected]), 0)
        self.assertTrue(fired[1 + expected])


# --- projector -------------------------------------------------------------
class TestRetinaProjector(unittest.TestCase):
    def test_windup_is_visible_as_expansion_without_any_phase_flag(self):
        world = World(CONFIG, seed=9)
        world.swatter.x, world.swatter.y = world.fly.x, world.fly.y
        world.set_pointer(world.fly.x, world.fly.y)
        projector = RetinaProjector(0.02)
        for _ in range(5):
            hovering = projector.project(world)
            world.tick(0.02)
        world.request_strike()
        peak = -math.inf
        for _ in range(int(0.15 / 0.02) + 1):
            world.tick(0.02)
            peak = max(peak, projector.project(world).theta_dot)
        self.assertLess(abs(hovering.theta_dot), 0.5)
        self.assertGreater(peak, 3.0, "the wind-up produced no looming signal")

    def test_azimuth_is_egocentric(self):
        world = World(CONFIG, seed=9)
        projector = RetinaProjector(0.02)
        world.fly.x, world.fly.y, world.fly.heading = 640.0, 360.0, 0.0   # facing +x
        world.swatter.x, world.swatter.y = 640.0, 460.0                   # to its right (+y)
        self.assertGreater(projector.project(world).azimuth, 0.0)
        projector.reset()
        world.swatter.y = 260.0                                           # to its left
        self.assertLess(projector.project(world).azimuth, 0.0)
        projector.reset()
        world.fly.heading = math.pi                                       # turn around
        self.assertGreater(projector.project(world).azimuth, 0.0)

    def test_retina_is_invariant_to_absolute_position(self):
        """The strongest statement of the bottleneck: move the whole scene and
        the fly's input is byte-identical, so no absolute coordinate survives
        the projection."""
        def project_at(fly_xy, swatter_offset):
            world = World(CONFIG, seed=9)
            world.fly.x, world.fly.y, world.fly.heading = fly_xy[0], fly_xy[1], 0.4
            world.swatter.x = fly_xy[0] + swatter_offset[0]
            world.swatter.y = fly_xy[1] + swatter_offset[1]
            return RetinaProjector(0.02).project(world)

        offset = (70.0, -40.0)
        a = project_at((300.0, 200.0), offset)
        b = project_at((900.0, 520.0), offset)
        self.assertEqual((a.theta, a.theta_dot, a.azimuth), (b.theta, b.theta_dot, b.azimuth))
        # A different relative geometry must change what the fly sees.
        c = project_at((300.0, 200.0), (-70.0, 40.0))
        self.assertNotEqual(a.azimuth, c.azimuth)


if __name__ == "__main__":
    unittest.main(verbosity=2)
