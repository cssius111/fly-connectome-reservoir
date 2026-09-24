"""M1.8-N4B1C lateral dual-path DNp01 escape decoder regressions.

Runtime candidate: escape when EITHER the same DNp01 side produces two inferred spikes
within 60 ms (LATERAL) OR the M1.8-N2b summed path qualifies (FAST 2.10, or current
sample >= 1.45 with >= 3 of the last 5). Unit tests inject MotorState directly; system
tests use the real chain only.
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
import tempfile
import unittest

os.environ.setdefault('NUMBA_NUM_THREADS', '4')
os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')

import numpy as np

from game.action import FixedEscapePolicy, MotorState
from game.session import (Session, build_policy, calibration_provenance, dnp01_trace_decay,
                          escape_decoder_spec, load_config, resolve_escape_threshold)
from test_game import shared_brain

ROOT = Path(__file__).parent
ROOM = load_config(ROOT/'game_room_config.json')
DT = 0.02
DECAY = dnp01_trace_decay(ROOM)
BASELINE = '76806f0'
RECORD = 'results/game/calibration_room_m1_8_n4b1c.json'
N2_RECORD = 'results/game/calibration_room_m1_8_n2.json'
N2B_RECORD = 'results/game/calibration_room_m1_8_n2b.json'
LEGACY_DIAGNOSTICS = {'escape_threshold', 'refractory_seconds', 'behavior_state', 'escape_strength'}
DECODER = {'kind': 'lateral_dual_path_v1', 'sustained_threshold': 1.45, 'summed_fast_threshold': 2.1,
           'sustained_window_samples': 5, 'sustained_required_samples': 3,
           'require_current_qualifying': True, 'lateral_same_side_window_ms': 60.0,
           'lateral_required_spikes': 2}


def content_sha256(path):
    """Committed-content hash (text CRLF normalised to LF), as the N4B1C record uses."""
    data = Path(path).read_bytes()
    if Path(path).suffix in ('.md', '.py', '.json', '.txt'):
        data = data.replace(b'\r\n', b'\n')
    return hashlib.sha256(data).hexdigest()


def lateral_policy():
    return FixedEscapePolicy(1.45, .4, DT, fast_threshold=2.1, persistence_samples=3,
                             sustained_window_samples=5, require_current_qualifying=True,
                             lateral_window_samples=3, trace_decay=DECAY)


def n2b_policy():
    return FixedEscapePolicy(1.45, .4, DT, fast_threshold=2.1, persistence_samples=3,
                             sustained_window_samples=5, require_current_qualifying=True)


def traces(left_spikes, right_spikes, n):
    """Per-side flybrain.Trace values (float32, x decay then +1 per spike)."""
    d = np.float32(DECAY)
    out = []
    tl = tr = np.float32(0.0)
    for t in range(n):
        tl = np.float32(tl * d)
        tr = np.float32(tr * d)
        if t in left_spikes:
            tl = np.float32(tl + np.float32(1.0))
        if t in right_spikes:
            tr = np.float32(tr + np.float32(1.0))
        out.append((float(tl), float(tr)))
    return out


def feed(policy, pairs):
    return [policy.decide(MotorState(l, r, 0.0, 0.0, np.zeros(1))) for l, r in pairs]


def fired(actions):
    return [i for i, a in enumerate(actions) if a.escape]


def reference_decisions(pairs, window=3, refractory=20):
    """Independent re-implementation of the frozen N4B1C semantics (firing ticks only)."""
    out, cooldown, flags = [], 0, []
    prev = {'L': None, 'R': None}
    last = {'L': None, 'R': None}
    for t, (lv, rv) in enumerate(pairs):
        total = lv + rv
        flags = (flags + [total >= 1.45])[-5:]
        now = {}
        for side, v in (('L', lv), ('R', rv)):
            spike = prev[side] is not None and v - DECAY * prev[side] >= 0.5
            now[side] = spike and last[side] is not None and t - last[side] <= window
            if spike:
                last[side] = t
            prev[side] = v
        if cooldown > 0:
            cooldown -= 1
            continue
        summed = total >= 2.1 or (total >= 1.45 and sum(flags) >= 3)
        if now['L'] or now['R'] or summed:
            out.append(t)
            cooldown = refractory
            flags = []
            last = {'L': None, 'R': None}
    return out


class TestLateralPath(unittest.TestCase):
    def test_same_side_two_spikes_two_samples_apart_fire_lateral(self):
        p = lateral_policy()
        self.assertEqual(fired(feed(p, traces({5, 7}, set(), 12))), [7])
        self.assertEqual(p.criterion_diagnostics()['escape_trigger_channel'], 'LATERAL')

    def test_60_ms_window_boundary(self):
        # 3 samples (60 ms) apart qualifies; 4 samples apart does not.
        self.assertEqual(fired(feed(lateral_policy(), traces({5, 8}, set(), 12))), [8])
        self.assertEqual(fired(feed(lateral_policy(), traces({5, 9}, set(), 14))), [])

    def test_left_then_right_is_not_same_side_evidence(self):
        for gap in (0, 1, 2, 3):
            acts = feed(lateral_policy(), traces({5}, {5 + gap}, 12))
            self.assertEqual(fired(acts), [], gap)

    def test_bilateral_same_tick_pair_needs_the_summed_path(self):
        # L+R in one sample sums to 2.0: below FAST 2.10, one qualifying sample only.
        self.assertEqual(fired(feed(lateral_policy(), traces({5}, {5}, 12))), [])

    def test_no_spike_is_inferred_on_the_first_sample_after_reset(self):
        # The first observed sample already holds a trace of 1.0; its predecessor is unknown.
        pairs = [(1.0, 0.0)] + traces({1}, set(), 6)[1:]
        pairs[1] = (float(np.float32(np.float32(1.0) * np.float32(DECAY)) + np.float32(1.0)), 0.0)
        p = lateral_policy()
        self.assertEqual(fired(feed(p, pairs[:2])), [])
        self.assertIsNone(lateral_policy().criterion_diagnostics()['escape_lateral_last_spike_left'])

    def test_reset_clears_spike_history_window_and_channel(self):
        p = lateral_policy()
        feed(p, traces({5, 7}, set(), 9))
        p.reset()
        d = p.criterion_diagnostics()
        self.assertEqual((d['escape_lateral_last_spike_left'], d['escape_lateral_last_spike_right'],
                          d['escape_window_qualifying'], d['escape_trigger_channel'],
                          d['escape_trigger_paths'], d['escape_sample_index']),
                         (None, None, 0, 'NONE', '', 0))

    def test_escape_clears_lateral_memory(self):
        # Spikes 5, 7 fire at 7. A spike at 8 (refractory) cannot pair with 7 or earlier.
        p = lateral_policy()
        acts = feed(p, traces({5, 7, 8}, set(), 40))
        self.assertEqual(fired(acts), [7])
        self.assertEqual(p.criterion_diagnostics()['escape_lateral_last_spike_left'], 8)

    def test_pair_completed_during_refractory_never_fires_later(self):
        # Escape at 7; pair 12/14 lies inside refractory (samples 8-27) and never fires.
        acts = feed(lateral_policy(), traces({5, 7, 12, 14}, set(), 60))
        self.assertEqual(fired(acts), [7])

    def test_fresh_pair_after_refractory_fires(self):
        # Refractory ends after sample 27; spikes 26 and 28: the qualifying spike (28) is
        # current and both spikes are after the escape, so this is fresh evidence.
        acts = feed(lateral_policy(), traces({5, 7, 26, 28}, set(), 60))
        self.assertEqual(fired(acts), [7, 28])

    def test_precedence_lateral_then_fast_then_sustained(self):
        def run(left, right, n):
            p = lateral_policy()
            f = fired(feed(p, traces(left, right, n)))
            d = p.criterion_diagnostics()
            return f, d['escape_trigger_channel'], d['escape_trigger_paths']
        # Left 5, 6 and right 6: summed 2.82 >= FAST and the left side qualifies.
        self.assertEqual(run({5, 6}, {6}, 10), ([6], 'LATERAL', 'LATERAL+FAST'))
        # Left 3, 7 (gap 4, not lateral) plus right 7: summed 2.45 >= FAST only.
        self.assertEqual(run({3, 7}, {7}, 10), ([7], 'FAST', 'FAST'))
        # Alternating sides every 3 samples (same-side gaps of 6): below FAST, and the
        # summed window reaches 3 qualifying samples at sample 11 (pattern H L L H H).
        self.assertEqual(run({4, 10}, {7, 13}, 12), ([11], 'SUSTAINED', 'SUSTAINED'))

    def test_summed_path_is_the_unchanged_n2b_rule(self):
        # Spikes alternating sides every 2 samples: never a same-side pair within 3,
        # but the summed window fills; N2b and the combined decoder fire identically.
        left, right = {4, 8, 12}, {6, 10, 14}
        pairs = traces(left, right, 20)
        self.assertEqual(fired(feed(lateral_policy(), pairs)), fired(feed(n2b_policy(), pairs)))
        self.assertTrue(fired(feed(n2b_policy(), pairs)))

    def test_motor_semantics_do_not_depend_on_the_path(self):
        # The lateral firing sample (total 1.549) is also the first legacy firing sample,
        # so both decoders produce exactly the same Action on the same state.
        pairs = traces({5, 8}, set(), 10)
        a = feed(lateral_policy(), pairs)
        b = feed(FixedEscapePolicy(1.45, .4, DT), pairs)
        self.assertEqual(fired(a), fired(b))
        self.assertEqual([dataclasses.astuple(x) for x in a], [dataclasses.astuple(x) for x in b])

    def test_random_sequences_match_an_independent_reference(self):
        rng = np.random.default_rng(20260924)
        for trial in range(60):
            n = 300
            rate = float(rng.choice([0.02, 0.1, 0.3, 0.5]))
            left = {t for t in range(n) if rng.random() < rate}
            right = {t for t in range(n) if rng.random() < rate}
            pairs = traces(left, right, n)
            self.assertEqual(fired(feed(lateral_policy(), pairs)), reference_decisions(pairs), trial)

    def test_constructor_rejects_incoherent_lateral_settings(self):
        for kw in ({'lateral_window_samples': 3},                          # no trace decay
                   {'lateral_window_samples': 0, 'trace_decay': DECAY},
                   {'lateral_window_samples': 3, 'trace_decay': 1.5},
                   {'lateral_window_samples': 3, 'trace_decay': DECAY, 'lateral_required_spikes': 3},
                   {'trace_decay': DECAY}):                                 # decay without lateral
            with self.assertRaises(ValueError, msg=kw):
                FixedEscapePolicy(1.45, .4, DT, fast_threshold=2.1, persistence_samples=3,
                                  sustained_window_samples=5, **kw)
        with self.assertRaises(ValueError):   # lateral only on top of the window criterion
            FixedEscapePolicy(1.45, .4, DT, fast_threshold=2.1, persistence_samples=3,
                              lateral_window_samples=3, trace_decay=DECAY)


class TestRecordedStateAndInputs(unittest.TestCase):
    def test_diagnostics_keep_the_frozen_recorded_key_set(self):
        p = lateral_policy()
        feed(p, traces({5, 7}, set(), 12))
        self.assertEqual(set(p.diagnostics()), LEGACY_DIAGNOSTICS)
        self.assertEqual(p.criterion_diagnostics()['escape_decoder'], 'lateral_dual_path_v1')

    def test_policy_state_is_scalar_neural_state_only(self):
        p = lateral_policy()
        feed(p, traces({5, 7}, {9}, 30))
        for name, value in vars(p).items():
            if name == '_window':
                self.assertTrue(all(type(v) is bool for v in value))
                continue
            self.assertIsInstance(value, (int, float, str, bool, type(None)), name)
        self.assertEqual(list(inspect.signature(FixedEscapePolicy.decide).parameters), ['self', 'motor'])
        for word in ('pointer', 'mouse', 'world', 'swatter', 'distance', 'contact', 'retina'):
            self.assertFalse(any(word in k for k in inspect.signature(FixedEscapePolicy.__init__).parameters))


class TestConfigAndProvenance(unittest.TestCase):
    def test_room_resolves_the_n4b1c_record(self):
        source = resolve_escape_threshold(ROOM)
        self.assertEqual(source.origin, RECORD)
        self.assertEqual(source.threshold, 1.45)
        self.assertEqual(source.decoder, DECODER)
        p, _ = build_policy(ROOM)
        self.assertEqual((p.threshold, p.fast_threshold, p.persistence_samples,
                          p.sustained_window_samples, p.lateral_window_samples, p.trace_decay),
                         (1.45, 2.1, 3, 5, 3, DECAY))
        self.assertEqual(p.refractory_ticks, 20)

    def test_decoder_block_validation(self):
        for key, value in (('lateral_same_side_window_ms', 0), ('lateral_same_side_window_ms', True),
                           ('lateral_required_spikes', 3), ('lateral_required_spikes', 2.0),
                           ('summed_fast_threshold', 1.45), ('require_current_qualifying', False),
                           ('sustained_required_samples', 6), ('fast_threshold', 2.1),
                           ('contact_gate', 1.0), ('swatter_distance', 1.0)):
            cfg = copy.deepcopy(ROOM)
            cfg['policy']['escape_decoder'][key] = value
            with self.assertRaises(ValueError, msg=(key, value)):
                escape_decoder_spec(cfg)
        for missing in ('lateral_same_side_window_ms', 'lateral_required_spikes', 'summed_fast_threshold'):
            cfg = copy.deepcopy(ROOM)
            cfg['policy']['escape_decoder'].pop(missing)
            with self.assertRaisesRegex(ValueError, 'Missing policy.escape_decoder keys'):
                escape_decoder_spec(cfg)

    def test_lateral_window_must_be_whole_ticks(self):
        from game.session import lateral_window_samples
        self.assertEqual(lateral_window_samples(DECODER, ROOM), 3)
        with self.assertRaisesRegex(ValueError, 'whole, positive number of ticks'):
            lateral_window_samples(dict(DECODER, lateral_same_side_window_ms=70.0), ROOM)

    def test_changing_a_decoder_parameter_invalidates_provenance(self):
        for key, value in (('lateral_same_side_window_ms', 80), ('summed_fast_threshold', 2.2),
                           ('sustained_window_samples', 4)):
            cfg = copy.deepcopy(ROOM)
            cfg['policy']['escape_decoder'][key] = value
            with self.assertRaisesRegex(ValueError, 'No matching'):
                resolve_escape_threshold(cfg)

    def test_older_records_cannot_load_the_lateral_config(self):
        for rel in (N2_RECORD, N2B_RECORD, 'results/game/calibration_room_m1_8_b2b_ii.json'):
            record = load_config(ROOT/rel)
            record['provenance'] = calibration_provenance(ROOM)   # even with matching provenance
            with tempfile.TemporaryDirectory() as folder:
                for path in ROOM['policy']['calibration_paths']:
                    target = Path(folder)/path
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_text(json.dumps(record))
                with self.assertRaisesRegex(ValueError, 'escape_decoder mismatch'):
                    resolve_escape_threshold(ROOM, Path(folder))

    def test_record_is_decoder_provenance_not_a_scalar_calibration(self):
        record = load_config(ROOT/RECORD)
        self.assertEqual(record['record_kind'], 'lateral-dual-path-decoder-provenance-v1')
        self.assertTrue(record['not_a_scalar_calibration'])
        self.assertEqual(record['provenance'], calibration_provenance(ROOM))
        self.assertEqual({k: record['escape_decoder'][k] for k in DECODER}, DECODER)
        self.assertEqual(record['escape_decoder']['lateral_window_samples'], 3)
        self.assertEqual(record['escape_decoder']['channel_precedence'], ['LATERAL', 'FAST', 'SUSTAINED'])
        self.assertEqual(record['escape_decoder']['parameter_class'], 'C')
        self.assertTrue(record['parameter_basis']['not_biological_constants'])
        self.assertEqual(set(record['evidence']),
                         {'n0_extended_no_loom', 'n1_loom_robustness', 'n3_neural_evidence_integration',
                          'n4a_sensory_descending_diagnosis', 'n4b1_lateralized_dnp01',
                          'n4b1c_combined_dnp01'})
        self.assertEqual(record['measurement_reuse']['changed_config_paths'],
                         ['config_version', 'policy._comment', 'policy.calibration_paths',
                          'policy.escape_decoder'])
        for name, rel in (('strict_n2', N2_RECORD), ('n2b', N2B_RECORD)):
            kept = record['preserved_records'][name]
            self.assertEqual(kept['record'], rel)
            self.assertEqual(kept['sha256'], content_sha256(ROOT/rel))
            self.assertFalse(kept['modified'])
        tracked = set(subprocess.check_output(['git', 'ls-files'], cwd=ROOT, text=True).split())
        checked = 0
        for group in record['evidence'].values():
            for rel, digest in group['files'].items():
                if rel in tracked:
                    self.assertEqual(content_sha256(ROOT/rel), digest, rel)
                    checked += 1
        self.assertGreaterEqual(checked, 20)

    def test_preserved_decoder_records_are_unchanged(self):
        self.assertEqual(content_sha256(ROOT/N2_RECORD),
                         '95d09955908c0d374623579b8aafb473c175cef377b109d866c280e0603c6adf')
        self.assertEqual(content_sha256(ROOT/N2B_RECORD),
                         load_config(ROOT/RECORD)['preserved_records']['n2b']['sha256'])
        committed = subprocess.check_output(['git', 'show', 'HEAD:' + N2B_RECORD], cwd=ROOT)
        self.assertEqual((ROOT/N2B_RECORD).read_bytes().replace(b'\r\n', b'\n'),
                         committed.replace(b'\r\n', b'\n'))

    def test_room_config_differs_from_the_baseline_only_in_the_decoder(self):
        before = json.loads(subprocess.check_output(['git', 'show', BASELINE + ':game_room_config.json'],
                                                    cwd=ROOT, text=True))
        after = copy.deepcopy(ROOM)
        # 13 at the N1 baseline; 14 strict N2; 15 rejected N2b; 16 this candidate.
        self.assertEqual(after['config_version'], before['config_version'] + 3)
        after['config_version'] = before['config_version']
        after['policy'].pop('escape_decoder')
        after['policy']['_comment'] = before['policy']['_comment']
        after['policy']['calibration_paths'] = before['policy']['calibration_paths']
        self.assertEqual(after, before)


class TestClosedLoopRoom(unittest.TestCase):
    """Real chain only: no DNp01, encoder or retinal value is injected."""

    def test_a_perched_committed_strike_launches_lateral_neural_takeoff(self):
        from tools.n2_closed_loop import scenario_a_perched_strike
        r = scenario_a_perched_strike(ROOM, build_policy(ROOM)[0], 255, shared_brain(), (0.0, 0.0))
        self.assertEqual(r['hold_zero_loom'], {'max_swatter_speed': 0.0, 'max_abs_theta_dot': 0.0,
                                               'max_encoder_drive': 0.0, 'clean': True})
        self.assertTrue(r['perched_at_click'])
        self.assertEqual(r['escapes_before_click'], 0)
        first = r['first_escape_after_click']
        self.assertEqual(first['channel'], 'LATERAL')
        self.assertEqual(first['lifecycle_mode'], 'TAKEOFF_ESCAPE')
        self.assertGreater(first['encoder_drive'], 0.0)
        self.assertAlmostEqual(r['first_escape_latency_from_click_s'], 0.08)

    def test_b_accepted_perched_threat_still_launches(self):
        from tools.n2_closed_loop import scenario_a_perched_hover
        r = scenario_a_perched_hover(ROOM, build_policy(ROOM)[0], 255, shared_brain())
        self.assertTrue(r['perched_before_threat'])
        self.assertEqual(r['strikes'], 0)
        self.assertEqual(r['escape_actions'], 1)
        self.assertEqual(len(r['escape_takeoffs']), 1)
        self.assertGreater(r['peak_theta_dot'], 0.0)

    def test_c_no_player_decisions_are_a_function_of_dnp01_alone(self):
        from test_game_n2_decoder import SpyPolicy
        spy = SpyPolicy(build_policy(ROOM)[0])
        s = Session(ROOM, brain=shared_brain(), policy=spy, seed=101, mode='evaluation')
        escapes = []
        try:
            for tick in range(600):
                s.tick(pointer=(1920, 388.8))
                if s.fly_loop.last_action.escape:
                    escapes.append(tick)
        finally:
            s.close()
        self.assertEqual(len(spy.inputs), 600)
        replayed = build_policy(ROOM)[0]
        self.assertEqual([i for i, m in enumerate(spy.inputs) if replayed.decide(m).escape], escapes)

    def test_d_recorder_schema_and_exact_replay(self):
        from game.session_recording import HumanSessionRecorder
        from game.replay import replay_session
        from tools.n2_closed_loop import PARKED
        with tempfile.TemporaryDirectory() as folder:
            rec = HumanSessionRecorder(folder, archive_source=False)
            s = Session(ROOM, brain=shared_brain(), seed=255, recorder=rec)
            for _ in range(170):
                s.tick(pointer=PARKED)
            for _ in range(80):
                s.tick(pointer=(s.world.fly.x, s.world.fly.y))
            s.close()
            manifest = load_config(rec.path/'manifest.json')
            self.assertEqual(manifest['recording_schema_version'], 4)
            self.assertEqual(set(manifest['calibration']), {'provenance', 'escape_threshold'})
            text = (rec.path/'ticks.jsonl').read_text()
            for key in ('escape_trigger_channel', 'escape_trigger_paths', 'escape_lateral',
                        'escape_sample_index', 'LATERAL'):
                self.assertNotIn(key, text)
            rows = [json.loads(line) for line in text.splitlines()]
            self.assertTrue(all(set(row['neural']['diagnostics']) == LEGACY_DIAGNOSTICS for row in rows))
            self.assertGreaterEqual(load_config(rec.path/'summary.json')['lifecycle']['events']['escape_takeoff'], 1)
            self.assertTrue(replay_session(rec.path, write_report=False)['exact'])


if __name__ == '__main__':
    unittest.main(verbosity=2)
