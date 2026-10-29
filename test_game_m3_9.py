"""M3.9: wall-evoked saccades of fixed amplitude (game/M3_9_WALL_SACCADE_DESIGN.md).

Flight-generator, configuration and record tests of the v33 candidate. v32 is read from commit
925427c; v33 is the working file. The gating tests run under any working configuration.
"""
import copy
import json
import math
import os
from pathlib import Path
import subprocess
import unittest

os.environ.setdefault('NUMBA_NUM_THREADS', '4')
os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')

from game.enclosure import WallCue
from game.flight import FreeFlightController
from game.session import calibration_provenance, load_config, resolve_escape_threshold
from tools.m3_9_record import ALLOWED_CHANGES, FLIGHT, RECORD, SOURCE_RECORD, build_record, value
from tools.n2_decoder_record import changed_paths

ROOT = Path(__file__).parent
V32 = json.loads(subprocess.check_output(['git', 'show', '925427c:game_room_config.json'], cwd=ROOT, text=True))
ROOM = load_config(ROOT / 'game_room_config.json')
WITH_AVOID_DEGREES = copy.deepcopy(V32)
WITH_AVOID_DEGREES['flight']['boundary'].update({'avoid_degrees': [60.0, 120.0],
                                                 'avoid_peak_rate_deg_per_second': [1200.0, 1500.0]})


class Recorder:
    """An actuator stand-in that accepts every request and records it."""

    enabled = True
    active = False
    duration = 0.0

    def __init__(self):
        self.requests = []

    def can_request(self, kind):
        return True

    def request(self, kind, angle, peak_rate):
        self.requests.append((kind, math.degrees(angle), math.degrees(peak_rate)))
        return True


def closing_cue(bearing_deg):
    """A wall being closed on at a time to contact of 0.3 s, its normal at this bearing."""
    b = math.radians(bearing_deg)
    return WallCue(expansion=1.0 / 0.3, contact_bearing=b, proximity=0.3, surface_bearing=b)


def avoid_request(config, bearing_deg, seed):
    flight = FreeFlightController(config['flight'], seed)
    actuator = Recorder()
    flight.update(0.02, closing_cue(bearing_deg), actuator)
    kinds = [r for r in actuator.requests if r[0] == 'AVOID']
    return flight, kinds[0] if kinds else None


class TestGating(unittest.TestCase):
    def test_without_the_key_the_tangent_rule_is_unchanged(self):
        for bearing in (-80.0, -40.0, -10.0, 10.0, 40.0, 80.0):
            _, (_, angle, peak) = avoid_request(V32, bearing, 3)
            self.assertAlmostEqual(abs(angle), 104.0 - abs(bearing), places=6)
            self.assertLess(angle * bearing, 0.0)
            self.assertTrue(700.0 <= peak <= 1300.0)

    def test_without_the_key_the_draws_are_unchanged(self):
        # The tangent path draws only the peak rate, so older configurations keep their streams.
        flight, _ = avoid_request(V32, 30.0, 9)
        reference = FreeFlightController(V32['flight'], 9)
        reference.rng.uniform(700.0, 1300.0)
        self.assertEqual(flight.rng.bit_generator.state, reference.rng.bit_generator.state)

    def test_lab_and_game_have_no_avoid_degrees(self):
        for name in ('game_config.json', 'game_play_config.json'):
            self.assertNotIn('avoid_degrees', load_config(ROOT / name)['flight']['boundary'])

    def test_invalid_intervals_are_refused(self):
        for bad in ([0.0, 90.0], [100.0, 60.0], [90.0]):
            config = copy.deepcopy(WITH_AVOID_DEGREES)
            config['flight']['boundary']['avoid_degrees'] = bad
            with self.assertRaises(ValueError):
                FreeFlightController(config['flight'], 1)


class TestFixedAmplitude(unittest.TestCase):
    def test_amplitude_is_sampled_independent_of_the_approach_angle(self):
        by_bearing = {}
        for bearing in (-90.0, -60.0, -30.0, -5.0, 5.0, 30.0, 60.0, 90.0):
            amplitudes = []
            for seed in range(60):
                _, (_, angle, peak) = avoid_request(WITH_AVOID_DEGREES, bearing, seed)
                self.assertTrue(60.0 <= abs(angle) <= 120.0)
                self.assertTrue(1200.0 <= peak <= 1500.0)
                amplitudes.append(abs(angle))
            by_bearing[bearing] = sum(amplitudes) / len(amplitudes)
        # The same seeds give the same amplitudes at every bearing.
        self.assertEqual(len({round(v, 9) for v in by_bearing.values()}), 1)

    def test_every_turn_is_away_from_the_wall(self):
        for bearing in (-90.0, -45.0, -1.0, 1.0, 45.0, 90.0):
            for seed in range(20):
                _, (_, angle, _) = avoid_request(WITH_AVOID_DEGREES, bearing, seed)
                self.assertLess(angle * bearing, 0.0)

    def test_a_head_on_tie_keeps_the_seeded_side(self):
        for seed in range(20):
            flight = FreeFlightController(WITH_AVOID_DEGREES['flight'], seed)
            side = flight.wall_side
            actuator = Recorder()
            flight.update(0.02, closing_cue(0.0), actuator)
            self.assertEqual(math.copysign(1.0, actuator.requests[0][1]), side)
            self.assertEqual(flight.wall_side, side)

    def test_the_turn_fits_the_actuator(self):
        bounds = ROOM['saccades']
        self.assertLessEqual(FLIGHT['flight.boundary.avoid_degrees'][1], bounds['max_degrees'])
        self.assertLessEqual(FLIGHT['flight.boundary.avoid_peak_rate_deg_per_second'][1],
                             bounds['peak_rate_cap_deg_per_second'])


@unittest.skipUnless(ROOM['config_version'] == 33, 'the working ROOM configuration is not the M3.9 candidate')
class TestCandidate(unittest.TestCase):
    def test_only_the_preregistered_keys_change(self):
        self.assertEqual(set(changed_paths(V32, ROOM)) - ALLOWED_CHANGES, set())
        for key, expected in FLIGHT.items():
            self.assertEqual(value(ROOM, key), expected)
        self.assertIsNone(value(V32, 'flight.boundary.avoid_degrees', None))

    def test_the_m3_8_values_are_kept(self):
        flight = ROOM['flight']
        self.assertEqual(flight['correction']['probability'], 0.0)
        self.assertEqual(flight['saccade']['degrees'], [60.0, 120.0])
        self.assertEqual(flight['saccade']['peak_rate_deg_per_second'], [1200.0, 1500.0])
        self.assertEqual(ROOM['ecology']['spontaneous_clock_rate']['ODOR_TRACK'], 0.0)

    def test_the_session_resolves_the_m3_9_record(self):
        source = resolve_escape_threshold(ROOM, ROOT)
        self.assertEqual(source.origin, RECORD)
        record = load_config(ROOT / RECORD)
        v32_record = load_config(ROOT / SOURCE_RECORD)
        self.assertEqual(record['escape_threshold'], v32_record['escape_threshold'])
        self.assertEqual(record['escape_decoder'], v32_record['escape_decoder'])
        self.assertEqual(record['provenance'], calibration_provenance(ROOM))

    def test_the_record_is_reproducible(self):
        built = build_record(copy.deepcopy(ROOM))
        stored = load_config(ROOT / RECORD)
        self.assertEqual(json.loads(json.dumps(built)), stored)

    def test_the_record_writer_refuses_other_changes(self):
        bad = copy.deepcopy(ROOM)
        bad['flight']['boundary']['avoid_time_to_contact_seconds'] = 0.4
        with self.assertRaises(SystemExit):
            build_record(bad)
        bad = copy.deepcopy(ROOM)
        bad['flight']['boundary']['avoid_degrees'] = [80.0, 100.0]
        with self.assertRaises(SystemExit):
            build_record(bad)


if __name__ == '__main__':
    unittest.main()
