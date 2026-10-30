"""M3.11: the upwind surge retested (game/M3_11_UPWIND_SURGE_RETEST_DESIGN.md).

Configuration and record tests of the v35 candidate. v32 is read from commit a5ca216 and v34, the
M3.10 candidate, from 9c2b53d. The surge mechanism is tested in test_game_m3_10.py.
"""
import copy
import json
import os
from pathlib import Path
import subprocess
import unittest

os.environ.setdefault('NUMBA_NUM_THREADS', '4')
os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')

from game.session import calibration_provenance, load_config, resolve_escape_threshold
from tools.m3_11_record import ALLOWED_CHANGES, FLIGHT, RECORD, SOURCE_RECORD, build_record, value
from tools.n2_decoder_record import changed_paths

ROOT = Path(__file__).parent
V32 = json.loads(subprocess.check_output(['git', 'show', 'a5ca216:game_room_config.json'], cwd=ROOT, text=True))
V34 = json.loads(subprocess.check_output(['git', 'show', '9c2b53d:game_room_config.json'], cwd=ROOT, text=True))
ROOM = load_config(ROOT / 'game_room_config.json')


@unittest.skipUnless(ROOM['config_version'] == 35, 'the working ROOM configuration is not the M3.11 candidate')
class TestCandidate(unittest.TestCase):
    def test_only_the_preregistered_keys_change(self):
        self.assertEqual(set(changed_paths(V32, ROOM)) - ALLOWED_CHANGES, set())
        for key, expected in FLIGHT.items():
            self.assertEqual(value(ROOM, key), expected)

    def test_the_behaviour_is_the_m3_10_candidate(self):
        # Apart from bookkeeping, v35 is v34.
        self.assertEqual(set(changed_paths(V34, ROOM)), {'config_version', 'policy._comment', 'policy.calibration_paths'})

    def test_the_session_resolves_the_m3_11_record(self):
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
        bad['ecology']['steering_cap_rad_s'] = 1.5
        with self.assertRaises(SystemExit):
            build_record(bad)


if __name__ == '__main__':
    unittest.main()
