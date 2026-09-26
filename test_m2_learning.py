"""M2.0 learning infrastructure: observation / action contracts, TRAIN / EVAL separation,
reward isolation, frozen benchmark suite and accepted-runtime preservation."""
import ast
import inspect
from pathlib import Path
import subprocess
import unittest


import numpy as np

from game.action import Action, MotionState, MotorState
from game.learning import contracts, model as model_mod, policies, runmode, runner
from game.learning.contracts import (BEHAVIOR_STATES, HISTORY_LENGTH, MANEUVERS, OBSERVATION_SIZE,
                                     ManeuverActuator, ObservationEncoder)
from game.learning.metrics import anti_cheat
from game.learning.reward import RewardSpec
from game.learning.scenarios import GlancingPass, SCENARIOS
from game.recording import observation_frame

ROOT = Path(__file__).parent
ACCEPTED_RUNTIME = '363a1a94cf3f5e33efab08cb28594c24ca694a03'
FROZEN_SUITE_SHA256 = '884de5832fdcad4694df101678995a7b10b835c4e32f02258a30c22bd72c7e1e'


def motor(l=0.1, r=0.2, al=0.3, ar=0.4, trace=None, motion=MotionState(10.0, -2.0, 0.5, 0.0)):
    return MotorState(l, r, al, ar, np.zeros(8) if trace is None else trace, motion)


class ShortGlance(GlancingPass):
    name = 'glancing_pass'
    seconds = 1.0


class ObservationContract(unittest.TestCase):
    def test_schema_size_and_fields(self):
        self.assertEqual(OBSERVATION_SIZE, 12 * (1 + HISTORY_LENGTH))
        self.assertEqual(len(contracts.OBSERVATION_FIELDS), OBSERVATION_SIZE)
        leaves = {f.split('.', 1)[1] for f in contracts.OBSERVATION_FIELDS}
        allowed = ({'valid'} | {'neural.' + k for k in ('dnp01_left', 'dnp01_right', 'dna02_left', 'dna02_right')}
                   | {'motion.' + k for k in ('forward_speed', 'lateral_speed', 'yaw_rate', 'saccade_remaining')}
                   | {'behavior_state.' + s for s in ('CALM', 'ALERT', 'ESCAPE')})
        self.assertEqual(leaves, allowed)
        self.assertEqual({f.split('.', 1)[0] for f in contracts.OBSERVATION_FIELDS},
                         {'t0', 't-1', 't-2', 't-3', 't-4'})

    def test_frame_equals_recorder_whitelist(self):
        enc = ObservationEncoder()
        m = motor()
        obs = enc.encode(m, 'ALERT')
        frame = observation_frame(m, 'ALERT')
        expect = [1.0] + list(frame['neural'].values()) + list(frame['motion'].values()) + [0.0, 1.0, 0.0]
        np.testing.assert_array_equal(obs[:12], np.array(expect))
        np.testing.assert_array_equal(obs[12:], np.zeros(48))            # no history yet

    def test_full_trace_is_not_observed(self):
        a, b = ObservationEncoder(), ObservationEncoder()
        oa = a.encode(motor(trace=np.zeros(500)), 'CALM')
        ob = b.encode(motor(trace=np.random.default_rng(1).normal(size=500) * 1e3), 'CALM')
        np.testing.assert_array_equal(oa, ob)

    def test_history_is_bounded_to_four_frames(self):
        enc = ObservationEncoder()
        for k in range(10):
            obs = enc.encode(motor(l=float(k)), 'CALM')
        # current frame k = 9; history holds 8, 7, 6, 5 (most recent first)
        self.assertEqual([obs[12 * i + 1] for i in range(5)], [9.0, 8.0, 7.0, 6.0, 5.0])
        self.assertEqual(len(enc.history), HISTORY_LENGTH)

    def test_only_motorstate_and_known_behavior_states(self):
        enc = ObservationEncoder()
        with self.assertRaises(TypeError):
            enc.encode({'dnp01_left': 1.0}, 'CALM')
        with self.assertRaises(ValueError):
            enc.encode(motor(), 'HIDDEN')
        self.assertEqual(set(BEHAVIOR_STATES), {'CALM', 'ALERT', 'ESCAPE'})

    def test_observation_is_read_only(self):
        obs = ObservationEncoder().encode(motor(), 'CALM')
        with self.assertRaises(ValueError):
            obs[0] = 5.0

    def test_policy_side_modules_cannot_import_world_state(self):
        allowed_internal = {'action', 'recording', 'contracts', 'model'}
        for mod in ('contracts', 'policies', 'model', 'runmode'):
            tree = ast.parse((ROOT / 'game/learning' / (mod + '.py')).read_text(encoding='utf-8'))
            for node in ast.walk(tree):
                if isinstance(node, ast.ImportFrom) and node.level > 0:
                    name = (node.module or '').split('.')[-1]
                    self.assertIn(name, allowed_internal, '%s imports %s' % (mod, node.module))
                elif isinstance(node, (ast.Import, ast.ImportFrom)):
                    names = [a.name for a in node.names] if isinstance(node, ast.Import) else [node.module]
                    for n in names:
                        self.assertTrue(n.split('.')[0] in ('numpy', 'collections', 'dataclasses', 'math', 'hashlib',
                                                            '__future__', 'typing'), '%s imports %s' % (mod, n))

    def test_decide_takes_only_the_motor_state(self):
        sig = inspect.signature(policies.ManeuverPolicy.decide)
        self.assertEqual(list(sig.parameters), ['self', 'motor'])
        with self.assertRaises(TypeError):
            policies.ManeuverPolicy(policies.NoEscapeModel(), 0.02, 0.4).decide({'fly_x': 1.0})


class ActionContract(unittest.TestCase):
    def test_every_maneuver_maps_to_a_valid_body_frame_action(self):
        act = ManeuverActuator(0.02, 0.4)
        for i, m in enumerate(MANEUVERS):
            act.reset()
            a = act.act(i)
            self.assertIsInstance(a, Action)
            self.assertFalse(any(f in m.__dict__ for f in ('x', 'y', 'dx', 'dy', 'target_x', 'target_y')))
            self.assertLessEqual(abs(a.turn), 1.0)
            self.assertLessEqual(abs(a.saccade), 1.0)
            self.assertTrue(0.0 <= a.strength <= 1.0)

    def test_escape_refractory_is_enforced(self):
        act = ManeuverActuator(0.02, 0.4)
        idx = [m.name for m in MANEUVERS].index('ESCAPE_FORWARD')
        fired = [t for t in range(200) if act.act(idx).escape]
        self.assertEqual(fired[:3], [0, 20, 40])
        self.assertTrue(all(b - a == 20 for a, b in zip(fired, fired[1:])))
        self.assertGreater(act.suppressed, 0)

    def test_behavior_state_semantics(self):
        act = ManeuverActuator(0.02, 0.4)
        self.assertEqual(act.behavior_state, 'CALM')
        act.act([m.name for m in MANEUVERS].index('TURN_LEFT'))
        self.assertEqual(act.behavior_state, 'ALERT')
        act.act([m.name for m in MANEUVERS].index('ESCAPE_LEFT'))
        self.assertEqual(act.behavior_state, 'ESCAPE')

    def test_out_of_range_maneuver_rejected(self):
        with self.assertRaises(ValueError):
            ManeuverActuator(0.02, 0.4).act(len(MANEUVERS))


class TrainEvalSeparation(unittest.TestCase):
    def test_seed_sets_are_disjoint_and_outside_m1(self):
        ev = [s for x in runner.SUITE for s in x['eval_seeds']]
        tr = runmode.train_seeds(1, 5000)
        self.assertFalse(set(ev) & set(tr))
        self.assertEqual(len(ev), len(set(ev)))
        for s in ev + tr:
            self.assertGreater(s, 1_000_000)          # every M1 seed is below 1e6
            self.assertFalse(7101 <= s <= 7680)
        for s in ev:
            runmode.EVAL.check_seed(s)
            with self.assertRaises(ValueError):
                runmode.TRAIN.check_seed(s)
        for s in tr[:50]:
            runmode.TRAIN.check_seed(s)
            with self.assertRaises(ValueError):
                runmode.EVAL.check_seed(s)

    def test_eval_guard_blocks_updates_and_detects_changes(self):
        m = model_mod.MLPPolicyModel(seed=3)
        h = m.param_hash()
        with runmode.EvalGuard(m):
            with self.assertRaises(RuntimeError):
                m.apply_update({'b2': np.ones(len(MANEUVERS))})
        self.assertEqual(m.param_hash(), h)
        with self.assertRaises(RuntimeError):
            with runmode.EvalGuard(m):
                m.params['b2'] = m.params['b2'] + 1.0         # a direct write is caught on exit

    def test_model_is_small(self):
        self.assertLess(model_mod.MLPPolicyModel(seed=0).n_parameters, 5000)


class LiveSession(unittest.TestCase):
    """Short live episodes through the unchanged Session."""

    @classmethod
    def setUpClass(cls):
        cls.config = runner.load_config()
        cls.model = model_mod.MLPPolicyModel(seed=11)
        cls.mlp_policy = runner.make_policy('mlp', cls.config, model=cls.model, mode=runmode.EVAL)
        cls.session = runner.make_session(cls.mlp_policy, cls.config)

    def test_eval_is_deterministic_and_frozen(self):
        seed = runmode.eval_seeds(2, 1)[0]
        with runmode.EvalGuard(self.model):
            a = runner.run_episode(self.session, ShortGlance, seed, runmode.EVAL)
            b = runner.run_episode(self.session, ShortGlance, seed, runmode.EVAL)
        self.assertEqual(a['trajectory_sha256'], b['trajectory_sha256'])
        self.assertNotIn('trajectory', a)                 # EVAL never records training data

    def test_reward_cannot_change_an_eval_episode(self):
        seed = runmode.eval_seeds(2, 2)[1]
        with runmode.EvalGuard(self.model):
            a = runner.run_episode(self.session, ShortGlance, seed, runmode.EVAL, RewardSpec())
            b = runner.run_episode(self.session, ShortGlance, seed, runmode.EVAL,
                                   RewardSpec(death=-99.0, unnecessary_escape=5.0, speed_cost=3.0))
        self.assertEqual(a['trajectory_sha256'], b['trajectory_sha256'])
        self.assertNotEqual(a['reward'], None)

    def test_model_sees_only_whitelisted_observations(self):
        seen = []

        class Spy:
            def act(self, obs, rng, explore):
                seen.append(obs)
                return 0, {}
        pol = self.session.policy
        original = pol.model
        captured = []
        original_encode = pol.encoder.encode

        def encode(m, state):
            captured.append((m, state))
            return original_encode(m, state)
        pol.model, pol.encoder.encode = Spy(), encode
        try:
            runner.run_episode(self.session, ShortGlance, runmode.eval_seeds(2, 3)[2], runmode.EVAL)
        finally:
            pol.model = original
            del pol.encoder.encode
        self.assertEqual(len(seen), len(captured))
        fresh = ObservationEncoder()
        for obs, (m, state) in zip(seen, captured):
            self.assertIs(type(m), MotorState)
            self.assertIsInstance(obs, np.ndarray)
            self.assertEqual(obs.shape, (OBSERVATION_SIZE,))
            np.testing.assert_array_equal(obs, fresh.encode(m, state))

    def test_train_mode_collects_and_updates(self):
        seed = runmode.train_seeds(7, 1)[0]
        with self.assertRaises(ValueError):
            runner.run_episode(self.session, ShortGlance, seed, runmode.EVAL)
        pol = self.session.policy
        pol.record = True
        try:
            r = runner.run_episode(self.session, ShortGlance, seed, runmode.TRAIN)
        finally:
            pol.record = False
            pol.explore = False
        self.assertEqual(len(r['trajectory']), len(r['reward_per_tick']))
        obs, acts = zip(*r['trajectory'])
        ret = np.cumsum(np.array(r['reward_per_tick'])[::-1])[::-1]
        g = self.model.reinforce_gradients(obs, acts, ret - ret.mean() + 1e-3)
        h = self.model.param_hash()
        self.model.apply_update({k: 1e-3 * v for k, v in g.items()})
        self.assertNotEqual(self.model.param_hash(), h)


class BaselineAndRuntime(unittest.TestCase):
    def test_baseline_is_the_unchanged_accepted_policy(self):
        from game.action import FixedEscapePolicy
        p = runner.make_policy('baseline_n4b1c', runner.load_config())
        self.assertIs(type(p), FixedEscapePolicy)
        self.assertEqual(p.criterion_diagnostics()['escape_decoder'], 'lateral_dual_path_v1')

    def test_accepted_runtime_files_are_unchanged(self):
        changed = subprocess.check_output(['git', 'diff', '--name-only', ACCEPTED_RUNTIME, '--', 'game',
                                           'game_room_config.json', 'game_play_config.json', 'game_config.json',
                                           'results'], cwd=ROOT, text=True).split()
        changed += subprocess.check_output(['git', 'ls-files', '--others', '--exclude-standard', 'game'],
                                           cwd=ROOT, text=True).split()
        # Only the learning package and the M2 milestone reports may differ from the accepted runtime.
        self.assertEqual([c for c in changed if not c.startswith('game/learning/')
                          and not (c.startswith('game/M2_') and c.endswith('.md'))], [])

    def test_benchmark_suite_is_frozen(self):
        self.assertEqual(runner.suite_hash(), FROZEN_SUITE_SHA256)
        self.assertEqual([s['scenario'] for s in runner.SUITE], [c.name for c in SCENARIOS])

    def test_anti_cheat_flags(self):
        base = dict(near_wall_fraction=0.1, max_speed_fraction=0.01, turn_active_fraction=0.05,
                    turn_sign_switches_per_s=0.1, airborne_slow_fraction=0.02, early_escape_fraction=0.0,
                    blind_escape_fraction=0.1, pre_click_blind_per_strike=0.0, perches_per_min=0.8)
        self.assertFalse(any(anti_cheat(base, base).values()))
        cheat = dict(base, near_wall_fraction=0.5, max_speed_fraction=0.5, turn_active_fraction=0.9,
                     airborne_slow_fraction=0.5, early_escape_fraction=0.9, blind_escape_fraction=0.9,
                     pre_click_blind_per_strike=0.5, perches_per_min=0.0)
        self.assertTrue(all(anti_cheat(cheat, base).values()))


if __name__ == '__main__':
    unittest.main()
