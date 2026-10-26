"""M3.8: saccades of about 90° and no spontaneous turns while tracking an odor upwind
(game/M3_8_SACCADE_ODOR_DESIGN.md).

Configuration and flight-generator tests of the v32 candidate and its transfer record. v27 is
read from commit 7483e51; v32 is the working file.
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
from game.saccade import SaccadeActuator
from game.session import calibration_provenance, load_config, resolve_escape_threshold
from tools.m3_8_record import ALLOWED_CHANGES, FLIGHT, RECORD, SOURCE_RECORD, build_record, value
from tools.n2_decoder_record import changed_paths

ROOT = Path(__file__).parent
V27 = json.loads(subprocess.check_output(['git', 'show', '7483e51:game_room_config.json'], cwd=ROOT, text=True))
ROOM = load_config(ROOT / 'game_room_config.json')
OPEN = WallCue()                                     # nothing near: open space
NEAR = WallCue(proximity=0.9, surface_bearing=1.2)   # a wall on the right, within sensing range


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


def spontaneous_events(config, cue, n, seed=11):
    flight = FreeFlightController(config['flight'], seed)
    actuator = Recorder()
    for _ in range(n):
        flight._spontaneous(cue, actuator, near=cue.proximity >= flight.perimeter_enter)
    return flight, actuator.requests


@unittest.skipUnless(ROOM['config_version'] == 32, 'the working ROOM configuration is not the M3.8 candidate')
class TestCandidate(unittest.TestCase):
    def test_only_the_preregistered_keys_change(self):
        self.assertEqual(set(changed_paths(V27, ROOM)) - ALLOWED_CHANGES, set())
        for key, expected in FLIGHT.items():
            self.assertEqual(value(ROOM, key), expected)
        self.assertEqual(value(V27, 'flight.correction.probability'), 0.42)
        self.assertEqual(value(V27, 'ecology.spontaneous_clock_rate.ODOR_TRACK'), 0.35)

    def test_only_odor_track_changes_among_the_clock_rates(self):
        before = V27['ecology']['spontaneous_clock_rate']
        after = ROOM['ecology']['spontaneous_clock_rate']
        self.assertEqual({k for k in before if before[k] != after[k]}, {'ODOR_TRACK'})
        self.assertEqual(after['ODOR_TRACK'], 0.0)
        self.assertEqual(after['ODOR_SEARCH'], 1.35)

    def test_a_stopped_clock_requests_no_spontaneous_turn(self):
        flight = FreeFlightController(ROOM['flight'], 5)
        actuator = SaccadeActuator(ROOM['saccades'])
        for _ in range(2000):
            flight.update(0.02, OPEN, actuator, spontaneous_clock_rate=0.0)
            actuator.step(0.02)
        self.assertEqual(flight.last_request, 'NONE')

    def test_the_actuator_bounds_are_unchanged(self):
        self.assertEqual(ROOM['saccades'], V27['saccades'])
        self.assertLessEqual(FLIGHT['flight.saccade.peak_rate_deg_per_second'][1],
                             ROOM['saccades']['peak_rate_cap_deg_per_second'])
        self.assertLessEqual(FLIGHT['flight.saccade.degrees'][1], ROOM['saccades']['max_degrees'])

    def test_lab_and_game_keep_the_corrections(self):
        for name in ('game_config.json', 'game_play_config.json'):
            flight = load_config(ROOT / name)['flight']
            self.assertEqual(flight['correction']['probability'], 0.42)
            self.assertEqual(flight['saccade']['degrees'], [25.0, 105.0])

    def test_open_space_events_are_all_saccades_of_60_to_120_degrees(self):
        _, requests = spontaneous_events(ROOM, OPEN, 400)
        self.assertEqual({k for k, _, _ in requests}, {'SACCADE'})
        self.assertTrue(all(60.0 <= abs(a) <= 120.0 for _, a, _ in requests))
        self.assertTrue(all(1200.0 <= p <= 1500.0 for _, _, p in requests))
        left = sum(1 for _, a, _ in requests if a < 0)
        self.assertGreater(left, 150)
        self.assertLess(left, 250)

    def test_near_a_wall_events_stay_corrections(self):
        for config in (V27, ROOM):
            _, requests = spontaneous_events(config, NEAR, 50)
            self.assertEqual({k for k, _, _ in requests}, {'CORRECTION'})
            self.assertTrue(all(5.0 <= abs(a) <= 18.0 for _, a, _ in requests))

    def test_each_event_consumes_the_same_draws_as_v27(self):
        for cue in (OPEN, NEAR):
            old, _ = spontaneous_events(V27, cue, 200)
            new, _ = spontaneous_events(ROOM, cue, 200)
            self.assertEqual(old.rng.bit_generator.state, new.rng.bit_generator.state)

    def test_a_90_degree_saccade_lasts_under_100_ms_at_1400_degrees_per_second(self):
        actuator = SaccadeActuator(ROOM['saccades'])
        self.assertTrue(actuator.request('SACCADE', math.radians(90.0), math.radians(1400.0)))
        self.assertAlmostEqual(actuator.duration, math.pi * 90.0 / (2 * 1400.0), places=6)
        self.assertLess(actuator.duration, 0.102)


@unittest.skipUnless(ROOM['config_version'] == 32, 'the working ROOM configuration is not the M3.8 candidate')
class TestRecord(unittest.TestCase):
    def test_the_session_resolves_the_m3_8_record(self):
        source = resolve_escape_threshold(ROOM, ROOT)
        self.assertEqual(source.origin, RECORD)
        record = load_config(ROOT / RECORD)
        v27_record = load_config(ROOT / SOURCE_RECORD)
        self.assertEqual(record['escape_threshold'], v27_record['escape_threshold'])
        self.assertEqual(record['escape_decoder'], v27_record['escape_decoder'])
        self.assertEqual(record['provenance'], calibration_provenance(ROOM))

    def test_the_record_is_reproducible(self):
        built = build_record(copy.deepcopy(ROOM))
        stored = load_config(ROOT / RECORD)
        self.assertEqual(json.loads(json.dumps(built)), stored)

    def test_the_record_writer_refuses_other_changes(self):
        bad = copy.deepcopy(ROOM)
        bad['flight']['interval']['short_probability'] = 0.3
        with self.assertRaises(SystemExit):
            build_record(bad)
        bad = copy.deepcopy(ROOM)
        bad['flight']['saccade']['degrees'] = [50.0, 120.0]
        with self.assertRaises(SystemExit):
            build_record(bad)


if __name__ == '__main__':
    unittest.main()
