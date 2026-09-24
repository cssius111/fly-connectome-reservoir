"""M1.8-N2 / N2b dual-path DNp01 escape decoder regressions.

Unit tests inject MotorState directly. System tests use the real chain only:
physical swatter -> Retina -> LC4/LPLC2 -> MaleCNS -> DNp01 -> decoder -> Action.

The active ROOM decoder is now the M1.8-N4B1C `lateral_dual_path_v1` candidate
(test_game_n4b1c_decoder.py). The rejected N2b decoder stays supported for exact replay
of its recordings; its provenance and closed-loop regressions here use the archived
v15 ROOM configuration from archive/m1-8-n2b-rejected, whose N2b record is preserved.
"""
import copy
import dataclasses
import hashlib
import inspect
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import types
import unittest

os.environ.setdefault('NUMBA_NUM_THREADS', '4')
os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')

import numpy as np

from game.action import Action, FixedEscapePolicy, MotorState, MotionState
from game.session import (Session, build_policy, calibration_provenance, escape_decoder_spec,
                          load_config, resolve_escape_threshold)
from test_game import shared_brain

ROOT = Path(__file__).parent
ROOM = load_config(ROOT/'game_room_config.json')
LAB = load_config(ROOT/'game_config.json')
PLAY = load_config(ROOT/'game_play_config.json')
DT = 0.02
BASELINE = '76806f0'
N2_RECORD = 'results/game/calibration_room_m1_8_n2.json'   # superseded strict N2
N2B_RECORD = 'results/game/calibration_room_m1_8_n2b.json'
N2B_ARCHIVE = '2c306174d7bdb4e74b6c5517519ae695bd90cf44'   # archive/m1-8-n2b-rejected
LEGACY_DIAGNOSTICS = {'escape_threshold', 'refractory_seconds', 'behavior_state', 'escape_strength'}


def git_show(path):
    return subprocess.check_output(['git', 'show', BASELINE + ':' + path], cwd=ROOT, text=True)


def archived_n2b_room():
    """The rejected N2b ROOM v15 configuration, byte-exact from the archive commit."""
    try:
        return json.loads(subprocess.check_output(
            ['git', 'show', N2B_ARCHIVE + ':game_room_config.json'], cwd=ROOT, text=True,
            stderr=subprocess.DEVNULL))
    except (subprocess.CalledProcessError, OSError):
        return None


N2B_ROOM = archived_n2b_room()

def same_content(path, digest):
    """True when the file matches `digest` as stored or with CRLF normalised to LF.

    Records written from a Windows working copy hash whichever line endings the checkout
    had (core.autocrlf); the committed content is what must be unchanged."""
    data = Path(path).read_bytes()
    return digest in (hashlib.sha256(data).hexdigest(),
                      hashlib.sha256(data.replace(b'\r\n', b'\n')).hexdigest())



def require_archive(case):
    if N2B_ROOM is None:
        raise unittest.SkipTest('archive/m1-8-n2b-rejected (%s) is not available' % N2B_ARCHIVE[:7])


def n2_policy():
    return FixedEscapePolicy(1.45, .4, DT, fast_threshold=2.2, persistence_samples=3)


def motor(total, left_fraction=.5, dna02=(0.0, 0.0)):
    return MotorState(total*left_fraction, total*(1-left_fraction), dna02[0], dna02[1], np.zeros(1))


def feed(policy, totals, **kw):
    return [policy.decide(motor(t, **kw)) for t in totals]


def fired(actions):
    return [i for i, a in enumerate(actions) if a.escape]


class TestDualPathCriterion(unittest.TestCase):
    def test_1_fast_path_fires_on_the_first_sample(self):
        for total in (2.2, 2.5, 6.0):
            p = n2_policy()
            a = p.decide(motor(total))
            self.assertTrue(a.escape)
            self.assertEqual(p.criterion_diagnostics()['escape_trigger_channel'], 'FAST')

    def test_2_two_sustained_samples_do_not_fire(self):
        for level in (1.45, 1.8, 2.19999):
            p = n2_policy()
            actions = feed(p, [level, level, 0.5, 0.5])
            self.assertEqual(fired(actions), [])
            self.assertEqual(p.criterion_diagnostics()['escape_trigger_channel'], 'NONE')

    def test_3_third_consecutive_sample_fires_sustained(self):
        p = n2_policy()
        actions = feed(p, [1.45, 2.0, 1.6])
        self.assertEqual(fired(actions), [2])
        self.assertEqual(p.criterion_diagnostics()['escape_trigger_channel'], 'SUSTAINED')

    def test_4_broken_streak_resets_completely(self):
        p = n2_policy()
        actions = feed(p, [1.6, 1.6, 1.44, 1.6, 1.6, 1.6])
        self.assertEqual(fired(actions), [5])
        p = n2_policy()
        self.assertEqual(fired(feed(p, [1.6, 1.6, 0.0, 1.6, 1.6, 0.0, 1.6, 1.6])), [])

    def test_5_persistence_three_is_forty_milliseconds(self):
        p = n2_policy()
        totals = [0.2, 0.3, 1.7, 1.7, 1.7, 1.7]
        first_qualifying = next(i for i, t in enumerate(totals) if t >= 1.45)
        actions = feed(p, totals)
        self.assertEqual(fired(actions), [4])
        delay = (fired(actions)[0] - first_qualifying) * DT
        self.assertAlmostEqual(delay, 0.04, places=12)
        self.assertNotAlmostEqual(delay, 0.06, places=6)
        self.assertEqual(p.persistence_samples - 1, 2)

    def test_6_fast_takes_precedence_when_both_paths_hold(self):
        p = n2_policy()
        actions = feed(p, [1.6, 1.6, 2.5])
        self.assertEqual(fired(actions), [2])
        self.assertEqual(p.criterion_diagnostics()['escape_trigger_channel'], 'FAST')

    def test_7_refractory_blocks_firing_and_sustained_evidence_fires_on_expiry(self):
        p = n2_policy()
        refractory = p.refractory_ticks
        self.assertEqual(refractory, 20)
        actions = feed(p, [3.0] + [1.6] * (refractory + 3))
        # Fired at sample 0; blocked for the refractory samples 1..20 even though the
        # streak reaches 3 at sample 3; fires on the first eligible sample, 21.
        self.assertEqual(fired(actions), [0, refractory + 1])
        self.assertEqual(p.criterion_diagnostics()['escape_trigger_channel'], 'SUSTAINED')
        self.assertTrue(all(not a.escape for a in actions[1:refractory + 1]))

    def test_7b_streak_restarts_after_an_escape(self):
        p = n2_policy()
        actions = feed(p, [1.6, 1.6, 1.6])
        self.assertEqual(fired(actions), [2])
        self.assertEqual(p.criterion_diagnostics()['escape_sustained_streak'], 0)
        p.decide(motor(1.6))
        self.assertEqual(p.criterion_diagnostics()['escape_sustained_streak'], 1)

    def test_8_signal_ending_during_refractory_cannot_fire_later(self):
        p = n2_policy()
        refractory = p.refractory_ticks
        totals = [3.0] + [1.6] * 8 + [0.5] * (refractory - 8) + [1.6, 1.6, 1.6]
        actions = feed(p, totals)
        first_eligible = refractory + 1
        self.assertEqual(fired(actions), [0, first_eligible + 2])
        self.assertFalse(actions[first_eligible].escape)
        self.assertFalse(actions[first_eligible + 1].escape)

    def test_8b_evidence_resuming_late_in_refractory_counts_its_own_samples(self):
        p = n2_policy()
        refractory = p.refractory_ticks
        totals = [3.0] + [0.5] * (refractory - 2) + [1.6] * 4
        actions = feed(p, totals)
        # Qualifying samples at 19, 20, 21: the third is also the first eligible one.
        self.assertEqual(fired(actions), [0, refractory + 1])

    def test_9_motor_semantics_match_the_legacy_calculation(self):
        # FAST on the first sample: the legacy decoder fires on the same sample, so
        # the whole Action must be identical.
        for left in (.5, .8, .2):
            legacy = FixedEscapePolicy(1.45, .4, DT)
            new = n2_policy()
            a, b = legacy.decide(motor(2.6, left)), new.decide(motor(2.6, left))
            self.assertTrue(a.escape and b.escape)
            self.assertEqual(a, b)
        # SUSTAINED on the third sample: the legacy decoder fired on the first sample,
        # so compare with its own side/steering state and strength formula at sample 3.
        seq = [(1.6, .8), (1.7, .7), (1.9, .75)]
        legacy, new = FixedEscapePolicy(1.45, .4, DT), n2_policy()
        for total, left in seq:
            a = legacy.decide(motor(total, left, (0.3, 0.1)))
            b = new.decide(motor(total, left, (0.3, 0.1)))
        self.assertTrue(b.escape)
        asym = (legacy._side_left - legacy._side_right) / (legacy._side_left + legacy._side_right)
        strength = min(1.0, 1.9 / (2 * 1.45))
        self.assertEqual(b.lateral, asym)
        self.assertEqual(b.turn, a.turn)
        self.assertEqual(b.strength, strength)
        self.assertEqual(b.saccade, asym * strength)
        self.assertEqual(b.forward, legacy.forward_bias)

    def test_9b_strength_is_not_rescaled_around_the_fast_threshold(self):
        p = n2_policy()
        self.assertAlmostEqual(p.decide(motor(2.2)).strength, 2.2 / 2.9)
        self.assertEqual(p.alert_threshold, 1.45 * .55)
        self.assertEqual(p.criterion_diagnostics()['escape_threshold'], 1.45)

    def test_sub_criterion_samples_behave_as_alert_not_escape(self):
        p = n2_policy()
        a = p.decide(motor(1.6, .9))
        self.assertFalse(a.escape)
        self.assertEqual(p.diagnostics()['behavior_state'], 'ALERT')
        self.assertGreater(a.turn, 0.0)

    def test_constructor_rejects_incoherent_criteria(self):
        for kw in ({'fast_threshold': 2.2}, {'persistence_samples': 3},
                   {'fast_threshold': 1.0, 'persistence_samples': 3},
                   {'fast_threshold': math.nan, 'persistence_samples': 3},
                   {'fast_threshold': 2.2, 'persistence_samples': 0},
                   {'fast_threshold': 2.2, 'persistence_samples': True},
                   {'fast_threshold': 2.2, 'persistence_samples': 3.0}):
            with self.assertRaises(ValueError):
                FixedEscapePolicy(1.45, .4, DT, **kw)

    def test_reset_clears_streak_and_channel(self):
        p = n2_policy()
        feed(p, [1.6, 1.6])
        p.reset()
        self.assertEqual(p.criterion_diagnostics()['escape_sustained_streak'], 0)
        self.assertEqual(fired(feed(p, [1.6, 1.6])), [])


def n2b_policy():
    return FixedEscapePolicy(1.45, .4, DT, fast_threshold=2.1, persistence_samples=3,
                             sustained_window_samples=5, require_current_qualifying=True)


H, L = 1.6, 1.0     # qualifying / non-qualifying samples, both below FAST 2.10


def pattern(text):
    return [H if c == 'H' else L for c in text]


class TestWindowCriterion(unittest.TestCase):
    """M1.8-N2b: FAST 2.10 OR (current >= 1.45 AND >= 3 of the last 5 >= 1.45)."""

    def fires(self, text, policy=None):
        p = policy or n2b_policy()
        return fired(feed(p, pattern(text))), p

    def test_hhh_fires_on_the_third_sample(self):
        self.assertEqual(self.fires('HHH')[0], [2])

    def test_hlhh_fires_on_the_final_sample(self):
        self.assertEqual(self.fires('HLHH')[0], [3])

    def test_hllhh_fires_on_the_final_sample(self):
        # Window at the last sample is H L L H H: 3 of 5, current H.
        self.assertEqual(self.fires('HLLHH')[0], [4])

    def test_hhllh_fires_on_the_final_sample(self):
        self.assertEqual(self.fires('HHLLH')[0], [4])

    def test_hhlll_never_fires(self):
        self.assertEqual(self.fires('HHLLL')[0], [])

    def test_llhh_waits_for_a_third_qualifying_sample(self):
        self.assertEqual(self.fires('LLHH')[0], [])
        self.assertEqual(self.fires('LLHHH')[0], [4])
        self.assertEqual(self.fires('LLHHLH')[0], [5])

    def test_old_evidence_outside_the_window_cannot_contribute(self):
        # H H L L L H H: the first two H have left the 5-sample window.
        self.assertEqual(self.fires('HHLLLHH')[0], [])
        self.assertEqual(self.fires('HHLLLHHH')[0], [7])

    def test_current_low_sample_can_never_fire_sustained(self):
        # Refractory ends exactly on the L sample after H H H: 3 of 5 but current L.
        p = n2b_policy()
        refractory = p.refractory_ticks
        totals = [3.0] + [L] * (refractory - 3) + [H, H, H] + [L, L]
        actions = feed(p, totals)
        first_eligible = refractory + 1
        self.assertEqual(pattern('HHHL'), totals[first_eligible - 3:first_eligible + 1])
        self.assertEqual(fired(actions), [0])

    def test_two_of_three_spontaneous_patterns_do_not_fire(self):
        for text in ('HH', 'LLLHH', 'HLH', 'HHL', 'HLLH', 'LHHLL'):
            self.assertEqual(self.fires(text)[0], [], text)

    def test_fast_fires_immediately_regardless_of_window(self):
        for prefix in ('', 'L', 'LLLL', 'HH', 'HLH'):
            p = n2b_policy()
            actions = feed(p, pattern(prefix) + [2.1])
            self.assertEqual(fired(actions), [len(prefix)])
            self.assertEqual(p.criterion_diagnostics()['escape_trigger_channel'], 'FAST')

    def test_fast_wins_the_channel_when_both_paths_hold(self):
        p = n2b_policy()
        actions = feed(p, [H, H, 2.5])
        self.assertEqual(fired(actions), [2])
        self.assertEqual(p.criterion_diagnostics()['escape_trigger_channel'], 'FAST')
        p = n2b_policy()
        feed(p, [H, L, H, H])
        self.assertEqual(p.criterion_diagnostics()['escape_trigger_channel'], 'SUSTAINED')

    def test_trigger_clears_the_window(self):
        p = n2b_policy()
        actions = feed(p, pattern('HHH'))
        self.assertEqual(fired(actions), [2])
        self.assertEqual(p.criterion_diagnostics()['escape_window_qualifying'], 0)
        p.decide(motor(H))
        self.assertEqual(p.criterion_diagnostics()['escape_window_qualifying'], 1)

    def test_reset_clears_the_window(self):
        p = n2b_policy()
        feed(p, pattern('HH'))
        self.assertEqual(p.criterion_diagnostics()['escape_window_qualifying'], 2)
        p.reset()
        self.assertEqual(p.criterion_diagnostics()['escape_window_qualifying'], 0)
        self.assertEqual(self.fires('H', p)[0], [])

    def test_refractory_expiry_with_current_high_and_recent_evidence_fires(self):
        p = n2b_policy()
        refractory = p.refractory_ticks
        # Window at the first eligible sample: H L H (refractory samples) + ... + H current.
        totals = [3.0] + [L] * (refractory - 3) + [H, L, H] + [H]
        actions = feed(p, totals)
        self.assertEqual(fired(actions), [0, refractory + 1])
        self.assertEqual(p.criterion_diagnostics()['escape_trigger_channel'], 'SUSTAINED')

    def test_refractory_blocks_and_evidence_before_the_escape_is_discarded(self):
        p = n2b_policy()
        refractory = p.refractory_ticks
        # H H before a FAST escape must not count afterwards.
        totals = [H, H, 3.0] + [L] * refractory + [H, H]
        actions = feed(p, totals)
        self.assertEqual(fired(actions), [2])
        self.assertTrue(all(not a.escape for a in actions[3:3 + refractory]))

    def test_sustained_evidence_through_refractory_fires_on_first_eligible_sample(self):
        p = n2b_policy()
        refractory = p.refractory_ticks
        actions = feed(p, [3.0] + [H] * (refractory + 2))
        self.assertEqual(fired(actions), [0, refractory + 1])

    def test_subthreshold_samples_keep_legacy_alert_and_steering(self):
        legacy = FixedEscapePolicy(1.45, .4, DT)
        new = n2b_policy()
        for total, left in ((1.0, .9), (1.2, .8), (0.5, .3), (1.4, .7)):
            a = legacy.decide(motor(total, left, (0.2, 0.1)))
            b = new.decide(motor(total, left, (0.2, 0.1)))
            self.assertEqual(a, b)
            self.assertEqual(legacy.diagnostics(), new.diagnostics())

    def test_window_trigger_motor_semantics_match_the_legacy_calculation(self):
        seq = [(1.6, .8), (1.0, .7), (1.7, .7), (1.9, .75)]    # H L H H
        legacy, new = FixedEscapePolicy(1.45, .4, DT), n2b_policy()
        for total, left in seq:
            a = legacy.decide(motor(total, left, (0.3, 0.1)))
            b = new.decide(motor(total, left, (0.3, 0.1)))
        self.assertTrue(b.escape)
        asym = (legacy._side_left - legacy._side_right) / (legacy._side_left + legacy._side_right)
        strength = min(1.0, 1.9 / (2 * 1.45))
        self.assertEqual((b.lateral, b.turn, b.strength, b.saccade, b.forward),
                         (asym, a.turn, strength, asym * strength, legacy.forward_bias))

    def test_plain_k_of_n_and_incoherent_windows_are_rejected(self):
        for kw in ({'require_current_qualifying': False},
                   {'sustained_window_samples': 2},
                   {'sustained_window_samples': 5.0},
                   {'sustained_window_samples': True}):
            args = dict(fast_threshold=2.1, persistence_samples=3, sustained_window_samples=5,
                        require_current_qualifying=True)
            args.update(kw)
            with self.assertRaises(ValueError, msg=kw):
                FixedEscapePolicy(1.45, .4, DT, **args)
        with self.assertRaises(ValueError):
            FixedEscapePolicy(1.45, .4, DT, sustained_window_samples=5)


class TestLegacyDecoderUnchanged(unittest.TestCase):
    """The single-sample decoder must be bit-identical to the N1 baseline source."""

    @classmethod
    def setUpClass(cls):
        module = types.ModuleType('baseline_action')
        sys.modules[module.__name__] = module
        try:
            exec(compile(git_show('game/action.py'), 'baseline_action.py', 'exec'), module.__dict__)
        finally:
            sys.modules.pop(module.__name__, None)
        cls.old = module

    def test_random_sequences_match_the_baseline_decoder(self):
        rng = np.random.default_rng(20260922)
        for trial in range(40):
            old = self.old.FixedEscapePolicy(1.45, .4, DT)
            new = FixedEscapePolicy(1.45, .4, DT)
            for _ in range(400):
                total = float(rng.choice([0.0, 0.5, 1.0, 1.44, 1.45, 1.6, 2.1, 2.3, 4.0])
                              * rng.uniform(.9, 1.1))
                left = total * float(rng.uniform(0, 1))
                m = MotorState(left, total - left, float(rng.uniform(0, 2)),
                               float(rng.uniform(0, 2)), np.zeros(1))
                a, b = old.decide(m), new.decide(m)
                self.assertEqual(dataclasses.astuple(a), dataclasses.astuple(b))
                self.assertEqual(old.diagnostics(), new.diagnostics())

    def test_recorded_diagnostics_keep_the_frozen_key_set(self):
        # diagnostics() is persisted by the recorder; N2 provenance lives elsewhere.
        for p in (FixedEscapePolicy(1.45, .4, DT), n2_policy()):
            feed(p, [3.0, 1.6, 1.6, 1.6])
            self.assertEqual(set(p.diagnostics()), LEGACY_DIAGNOSTICS)
        self.assertEqual(n2_policy().criterion_diagnostics()['escape_decoder'], 'dual_path_v1')
        self.assertEqual(FixedEscapePolicy(1.45, .4, DT).criterion_diagnostics()['escape_decoder'],
                         'single_sample')


class TestNoWorldInformation(unittest.TestCase):
    def test_10_decoder_inputs_are_descending_neuron_state_only(self):
        self.assertEqual(list(inspect.signature(FixedEscapePolicy.decide).parameters),
                         ['self', 'motor'])
        self.assertEqual(set(MotorState.__dataclass_fields__),
                         {'dnp01_left', 'dnp01_right', 'dna02_left', 'dna02_right',
                          'trace', 'motion'})
        self.assertEqual(set(MotionState.__slots__),
                         {'forward_speed', 'lateral_speed', 'yaw_rate', 'saccade_remaining'})
        params = set(inspect.signature(FixedEscapePolicy.__init__).parameters)
        for word in ('pointer', 'mouse', 'world', 'swatter', 'distance', 'contact',
                     'geometry', 'position', 'label'):
            self.assertFalse(any(word in p for p in params), word)

    def test_10b_config_cannot_add_a_geometry_gate(self):
        for key in ('contact_gate', 'swatter_distance', 'geometric_contact_course',
                    'receding', 'pointer_speed'):
            cfg = copy.deepcopy(ROOM)
            cfg['policy']['escape_decoder'][key] = 1.0
            with self.assertRaisesRegex(ValueError, 'Unsupported policy.escape_decoder keys'):
                escape_decoder_spec(cfg)

    def test_10c_session_policy_state_holds_no_world_objects(self):
        s = Session(ROOM, brain=shared_brain(), seed=255, mode='evaluation')
        try:
            for _ in range(20):
                s.tick(pointer=(1920, 388.8))
            for name, value in vars(s.policy).items():
                if name == '_window':   # rolling qualification flags only
                    self.assertTrue(all(type(v) is bool for v in value))
                    continue
                self.assertIsInstance(value, (int, float, str, bool, type(None)), name)
        finally:
            s.close()


class TestDecoderProvenance(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        require_archive(cls)

    N2B = {'kind': 'dual_path_window_v1', 'sustained_threshold': 1.45, 'fast_threshold': 2.1,
           'sustained_window_samples': 5, 'sustained_required_samples': 3,
           'require_current_qualifying': True}

    def test_room_resolves_the_window_decoder_record(self):
        source = resolve_escape_threshold(N2B_ROOM)
        self.assertEqual(source.origin, N2B_RECORD)
        self.assertEqual(source.threshold, 1.45)
        self.assertEqual(source.decoder, self.N2B)
        policy, _ = build_policy(N2B_ROOM)
        self.assertEqual((policy.threshold, policy.fast_threshold, policy.persistence_samples,
                          policy.sustained_window_samples), (1.45, 2.1, 3, 5))
        self.assertEqual(policy.criterion_diagnostics()['escape_decoder'], 'dual_path_window_v1')

    def test_lab_and_game_keep_the_single_sample_decoder(self):
        for config, threshold in ((LAB, 1.45), (PLAY, 1.35)):
            source = resolve_escape_threshold(config)
            self.assertIsNone(source.decoder)
            self.assertEqual(source.threshold, threshold)
            policy, _ = build_policy(config)
            self.assertFalse(policy.dual_path)
            self.assertIsNone(config['policy'].get('escape_decoder'))

    def sandbox(self, record, config=N2B_ROOM):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        root = Path(folder.name)
        for rel in config['policy']['calibration_paths']:
            p = root/rel
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(json.dumps(record))
        return root

    def test_a_scalar_record_cannot_load_the_dual_path_config(self):
        scalar = load_config(ROOT/'results/game/calibration_room_m1_8_b2b_ii.json')
        scalar['provenance'] = calibration_provenance(N2B_ROOM)   # even with matching provenance
        with self.assertRaisesRegex(ValueError, 'escape_decoder mismatch'):
            resolve_escape_threshold(N2B_ROOM, self.sandbox(scalar))

    def test_a_strict_n2_record_cannot_load_the_window_config(self):
        strict = load_config(ROOT/N2_RECORD)
        strict['provenance'] = calibration_provenance(N2B_ROOM)   # even with matching provenance
        with self.assertRaisesRegex(ValueError, 'escape_decoder mismatch'):
            resolve_escape_threshold(N2B_ROOM, self.sandbox(strict))

    def test_decoder_parameters_must_match_the_record(self):
        valid = load_config(ROOT/N2B_RECORD)
        for key, value in (('fast_threshold', 2.2), ('sustained_window_samples', 4),
                           ('sustained_required_samples', 2), ('sustained_threshold', 1.6),
                           ('require_current_qualifying', False), ('kind', 'dual_path_v1')):
            record = copy.deepcopy(valid)
            record['escape_decoder'][key] = value
            with self.assertRaisesRegex(ValueError, 'escape_decoder mismatch'):
                resolve_escape_threshold(N2B_ROOM, self.sandbox(record))
        record = copy.deepcopy(valid)
        record['escape_threshold'] = 1.5
        with self.assertRaisesRegex(ValueError, 'differs from sustained_threshold'):
            resolve_escape_threshold(N2B_ROOM, self.sandbox(record))
        self.assertEqual(resolve_escape_threshold(N2B_ROOM, self.sandbox(valid)).threshold, 1.45)

    def test_a_dual_path_record_cannot_load_a_single_sample_config(self):
        for rel in (N2_RECORD, N2B_RECORD):
            record = load_config(ROOT/'results/game/calibration.json')
            record['escape_decoder'] = load_config(ROOT/rel)['escape_decoder']
            with self.assertRaisesRegex(ValueError, 'dual-path record for a single-sample decoder'):
                resolve_escape_threshold(LAB, self.sandbox(record, LAB))

    def test_changing_a_decoder_parameter_invalidates_provenance(self):
        for key, value in (('fast_threshold', 2.2), ('sustained_window_samples', 4)):
            cfg = copy.deepcopy(N2B_ROOM)
            cfg['policy']['escape_decoder'][key] = value
            with self.assertRaisesRegex(ValueError, 'No matching'):
                resolve_escape_threshold(cfg)

    def test_decoder_block_validation(self):
        for key, value in (('kind', 'single_sample'), ('kind', 'dual_path_window_v2'),
                           ('require_current_qualifying', False),
                           ('require_current_qualifying', 1),
                           ('sustained_window_samples', 2), ('sustained_window_samples', 5.0),
                           ('sustained_required_samples', 1), ('sustained_required_samples', 6),
                           ('persistence_samples', 3), ('fast_threshold', 1.45),
                           ('fast_threshold', True), ('sustained_threshold', -1.0)):
            cfg = copy.deepcopy(N2B_ROOM)
            cfg['policy']['escape_decoder'][key] = value
            with self.assertRaises(ValueError, msg=(key, value)):
                escape_decoder_spec(cfg)
        for missing in ('sustained_window_samples', 'require_current_qualifying'):
            cfg = copy.deepcopy(N2B_ROOM)
            cfg['policy']['escape_decoder'].pop(missing)
            with self.assertRaisesRegex(ValueError, 'Missing policy.escape_decoder keys'):
                escape_decoder_spec(cfg)
        # The strict N2 kind keeps its own exact key set.
        strict = copy.deepcopy(N2B_ROOM)
        strict['policy']['escape_decoder'] = {'kind': 'dual_path_v1', 'sustained_threshold': 1.45,
                                              'fast_threshold': 2.2, 'persistence_samples': 3}
        self.assertEqual(escape_decoder_spec(strict)['persistence_samples'], 3)
        strict['policy']['escape_decoder']['sustained_window_samples'] = 5
        with self.assertRaisesRegex(ValueError, 'Unsupported policy.escape_decoder keys'):
            escape_decoder_spec(strict)

    def test_record_is_explicit_decoder_provenance_not_a_scalar_calibration(self):
        record = load_config(ROOT/N2B_RECORD)
        self.assertEqual(record['record_kind'], 'gap-tolerant-dual-path-decoder-provenance-v1')
        self.assertTrue(record['not_a_scalar_calibration'])
        self.assertEqual(record['provenance'], calibration_provenance(N2B_ROOM))
        d = record['escape_decoder']
        self.assertEqual({k: d[k] for k in self.N2B}, self.N2B)
        self.assertEqual(d['minimum_structural_delay_seconds'], 0.04)
        self.assertEqual(d['maximum_evidence_span_seconds'], 0.08)
        self.assertEqual(d['parameter_class'], 'C')
        self.assertNotIn('sweep', record)
        self.assertNotIn('detection_rate', record)
        reuse = record['measurement_reuse']
        b2bii = 'results/game/calibration_room_m1_8_b2b_ii.json'
        self.assertEqual(reuse['source_record'], b2bii)
        self.assertEqual(reuse['source_sha256'], hashlib.sha256((ROOT/b2bii).read_bytes()).hexdigest())
        original = ROOT/'results/game/calibration_room_m1_7_1.json'
        self.assertEqual(reuse['original_measurement_sha256'],
                         hashlib.sha256(original.read_bytes()).hexdigest())
        self.assertEqual(reuse['changed_config_paths'],
                         ['config_version', 'policy._comment', 'policy.calibration_paths',
                          'policy.escape_decoder'])
        self.assertEqual(record['supersedes']['record'], N2_RECORD)
        self.assertTrue(same_content(ROOT/N2_RECORD, record['supersedes']['sha256']))
        self.assertFalse(record['supersedes']['modified'])
        self.assertEqual(set(record['evidence']),
                         {'n0_extended_no_loom', 'n1_loom_robustness', 'n2_fast_threshold_review',
                          'n2_temporal_rule_review'})
        # Evidence files tracked in git must still have the recorded bytes.
        tracked = set(subprocess.check_output(['git', 'ls-files'], cwd=ROOT, text=True).split())
        checked = 0
        for group in record['evidence'].values():
            for rel, digest in group['files'].items():
                if rel in tracked:
                    self.assertTrue(same_content(ROOT/rel, digest), rel)
                    checked += 1
        self.assertGreaterEqual(checked, 9)

    def test_superseded_strict_n2_record_is_preserved(self):
        record = load_config(ROOT/N2_RECORD)
        # Committed content, independent of the checkout's CRLF conversion.
        self.assertEqual(hashlib.sha256((ROOT/N2_RECORD).read_bytes().replace(b'\r\n', b'\n')).hexdigest(),
                         '95d09955908c0d374623579b8aafb473c175cef377b109d866c280e0603c6adf')
        self.assertEqual(record['escape_decoder']['kind'], 'dual_path_v1')
        self.assertNotEqual(record['provenance'], calibration_provenance(N2B_ROOM))

    def test_room_config_differs_from_the_baseline_only_in_the_decoder(self):
        before = json.loads(git_show('game_room_config.json'))
        after = copy.deepcopy(N2B_ROOM)
        # Archived N2b config: 13 at the N1 baseline; 14 was the superseded strict N2 candidate.
        self.assertEqual(after['config_version'], before['config_version'] + 2)
        after['config_version'] = before['config_version']
        after['policy'].pop('escape_decoder')
        after['policy']['_comment'] = before['policy']['_comment']
        after['policy']['calibration_paths'] = before['policy']['calibration_paths']
        self.assertEqual(after, before)
        for path in ('game_config.json', 'game_play_config.json'):
            self.assertEqual(load_config(ROOT/path), json.loads(git_show(path)))

    def test_historical_calibration_records_are_unchanged(self):
        listed = subprocess.check_output(['git', 'ls-tree', '--name-only', BASELINE,
                                          'results/game/'], cwd=ROOT, text=True).split()
        records = [rel for rel in listed if Path(rel).name.startswith('calibration')]
        self.assertGreaterEqual(len(records), 10)
        for rel in records:
            self.assertEqual((ROOT/rel).read_text(encoding='utf-8'), git_show(rel), rel)


class SpyPolicy:
    """Records every decoder input; behaviour is exactly the wrapped policy's."""

    def __init__(self, inner):
        self.inner, self.inputs = inner, []

    def reset(self):
        self.inner.reset()

    def decide(self, m):
        self.inputs.append(m)
        return self.inner.decide(m)

    def diagnostics(self):
        return self.inner.diagnostics()


class TestClosedLoopRoom(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        require_archive(cls)

    """Real chain only: no DNp01, encoder or retinal value is injected."""

    @staticmethod
    def policy():
        return build_policy(N2B_ROOM)[0]

    def test_a_perched_committed_strike_launches_neural_takeoff(self):
        from tools.n2_closed_loop import scenario_a_perched_strike
        r = scenario_a_perched_strike(N2B_ROOM, self.policy(), 255, shared_brain(), (0.0, 0.0))
        # The settled fixture must be a genuine no-threat hold before the click.
        self.assertEqual(r['hold_zero_loom'], {'max_swatter_speed': 0.0, 'max_abs_theta_dot': 0.0,
                                               'max_encoder_drive': 0.0, 'clean': True})
        self.assertTrue(r['perched_at_click'])
        self.assertEqual(r['escapes_before_click'], 0)
        first = r['first_escape_after_click']
        self.assertEqual(first['channel'], 'FAST')
        self.assertEqual(first['lifecycle_mode'], 'TAKEOFF_ESCAPE')
        self.assertGreaterEqual(first['dnp01_total'], 2.1)
        self.assertGreater(first['encoder_drive'], 0.0)
        self.assertAlmostEqual(r['first_escape_latency_from_click_s'], 0.08)
        self.assertEqual([e['tick'] for e in r['escape_takeoffs']], [first['tick']])
        self.assertEqual(r['strikes'], 1)

    def test_b_airborne_committed_strike_escapes_only_on_neural_evidence(self):
        # The pre-click phase is a real hover-height chase of the airborne fly, so it is
        # legitimate retinal looming and does not isolate the click (M1.8-N2b diagnosis:
        # the seed-11 pre-click escape had theta_dot > 0 and LC4/LPLC2 drive > 0).
        from tools.n2_closed_loop import scenario_b_airborne_strike
        r = scenario_b_airborne_strike(N2B_ROOM, self.policy(), 11, shared_brain(), (20.0, 10.0))
        run_escapes = r['escape_actions']
        self.assertGreaterEqual(run_escapes, 1)
        self.assertEqual(r['escapes_before_click'], 1)
        first = r['first_escape_after_click']
        self.assertIsNotNone(first)
        self.assertGreater(first['encoder_drive'], 0.0)
        self.assertEqual(first['channel'], 'SUSTAINED')
        self.assertAlmostEqual(r['first_escape_latency_from_click_s'], 0.12)

    def test_c_accepted_perched_threat_uses_the_sustained_path(self):
        # The accepted M1.8-A perched-threat scenario: a real paddle moving over the
        # perched fly at hover height, with no click.
        from tools.n2_closed_loop import scenario_a_perched_hover
        r = scenario_a_perched_hover(N2B_ROOM, self.policy(), 255, shared_brain())
        self.assertTrue(r['perched_before_threat'])
        self.assertEqual(r['strikes'], 0)
        self.assertEqual(r['escape_actions'], 1)
        self.assertEqual(r['escape_channels'], {'SUSTAINED': 1})
        self.assertEqual(len(r['escape_takeoffs']), 1)
        self.assertGreater(r['peak_theta_dot'], 0.0)

    def test_d_no_player_decisions_are_a_function_of_dnp01_alone(self):
        spy = SpyPolicy(self.policy())
        s = Session(N2B_ROOM, brain=shared_brain(), policy=spy, seed=101, mode='evaluation')
        escapes, swatter_speed = [], 0.0
        try:
            for tick in range(600):
                s.tick(pointer=(1920, 388.8))
                swatter_speed = max(swatter_speed, math.hypot(s.world.swatter.vx, s.world.swatter.vy))
                if s.fly_loop.last_action.escape:
                    escapes.append(tick)
        finally:
            s.close()
        self.assertEqual(swatter_speed, 0.0)
        self.assertTrue(all(type(m) is MotorState for m in spy.inputs))
        # One decoder input per tick; replaying those inputs alone reproduces every
        # decision, so nothing outside the descending-neuron state can gate escape.
        self.assertEqual(len(spy.inputs), 600)
        replayed = self.policy()
        again = [i for i, m in enumerate(spy.inputs) if replayed.decide(m).escape]
        self.assertEqual(again, escapes)

    def test_recorder_schema_and_exact_replay_are_unchanged(self):
        from game.session_recording import HumanSessionRecorder
        from game.replay import replay_session
        from tools.n2_closed_loop import PARKED
        with tempfile.TemporaryDirectory() as folder:
            rec = HumanSessionRecorder(folder, archive_source=False)
            s = Session(N2B_ROOM, brain=shared_brain(), seed=255, recorder=rec)
            for _ in range(170):
                s.tick(pointer=PARKED)
            for _ in range(80):
                s.tick(pointer=(s.world.fly.x, s.world.fly.y))
            s.close()
            manifest = load_config(rec.path/'manifest.json')
            self.assertEqual(manifest['recording_schema_version'], 4)
            self.assertEqual(set(manifest['calibration']), {'provenance', 'escape_threshold'})
            text = (rec.path/'ticks.jsonl').read_text()
            for key in ('escape_trigger_channel', 'escape_sustained_streak', 'escape_fast_threshold'):
                self.assertNotIn(key, text)
            rows = [json.loads(line) for line in text.splitlines()]
            self.assertTrue(all(set(row['neural']['diagnostics']) == LEGACY_DIAGNOSTICS
                                for row in rows))
            self.assertEqual(load_config(rec.path/'summary.json')['lifecycle']['events']['escape_takeoff'], 1)
            self.assertTrue(replay_session(rec.path, write_report=False)['exact'])


if __name__ == '__main__':
    unittest.main(verbosity=2)
