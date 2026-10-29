"""M3.10: an upwind surge turn on odor entry (game/M3_10_UPWIND_SURGE_DESIGN.md).

Ecology, actuator, world, configuration and record tests of the v34 candidate. v32 is read from
commit e113583; v34 is the working file. The gating and mechanism tests run under any working
configuration.
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

from game.ecological_sense import EcologicalSense
from game.ecology import EcologicalController, ThreatState
from game.saccade import PRIORITY, SaccadeActuator
from game.session import calibration_provenance, load_config, resolve_escape_threshold
from tools.m3_10_record import ALLOWED_CHANGES, FLIGHT, RECORD, SOURCE_RECORD, build_record, value
from tools.n2_decoder_record import changed_paths

ROOT = Path(__file__).parent
V32 = json.loads(subprocess.check_output(['git', 'show', 'e113583:game_room_config.json'], cwd=ROOT, text=True))
ROOM = load_config(ROOT / 'game_room_config.json')
SURGE = {'_comment': 'test', 'delay_seconds': 0.07, 'peak_rate_deg_per_second': [1200.0, 1500.0]}
WITH_SURGE = copy.deepcopy(V32['ecology'])
WITH_SURGE['upwind_surge'] = SURGE
DT = 0.02


def eco_config(base):
    return {k: v for k, v in base.items() if k != 'enabled'}


def odor_sense(wind_forward=-45.0, wind_lateral=0.0, odor=1.0):
    """Odor above threshold in a wind; the default wind blows from straight behind the fly."""
    return EcologicalSense(odor=odor, wind_forward=wind_forward, wind_lateral=wind_lateral, visual_contrast=0.6)


def run(config, senses, threats=None, seed=4):
    eco = EcologicalController(eco_config(config), seed)
    out = []
    for k, sense in enumerate(senses):
        threat = ThreatState.CALM if threats is None else threats[k]
        command = eco.step(sense, threat, DT)
        out.append((eco.state, eco.elapsed, eco.pending_surge, command))
    return eco, out


class TestGating(unittest.TestCase):
    def test_without_the_block_no_surge_and_identical_commands(self):
        senses = [EcologicalSense()] * 20 + [odor_sense(wind_lateral=20.0)] * 200
        _, plain = run(V32['ecology'], senses)
        _, surged = run(WITH_SURGE, senses)
        self.assertTrue(all(p is None for _, _, p, _ in plain))
        self.assertEqual([(s, c) for s, _, _, c in plain], [(s, c) for s, _, _, c in surged])

    def test_lab_and_game_have_no_upwind_surge(self):
        for name in ('game_config.json', 'game_play_config.json'):
            self.assertNotIn('upwind_surge', load_config(ROOT / name).get('ecology', {}))

    def test_invalid_blocks_are_refused(self):
        for bad in ({'delay_seconds': 0.07}, dict(SURGE, delay_seconds=-0.1),
                    dict(SURGE, peak_rate_deg_per_second=[1500.0, 1200.0])):
            config = copy.deepcopy(WITH_SURGE)
            config['upwind_surge'] = bad
            with self.assertRaises(ValueError):
                EcologicalController(eco_config(config), 1)

    def test_surge_is_an_ordinary_saccade_priority(self):
        self.assertEqual(PRIORITY['SURGE'], PRIORITY['SACCADE'])
        actuator = SaccadeActuator(ROOM['saccades'])
        self.assertTrue(actuator.request('SURGE', math.radians(100.0), math.radians(1300.0)))
        self.assertFalse(actuator.can_request('SACCADE'))
        self.assertTrue(actuator.request('AVOID', math.radians(60.0), math.radians(1300.0)))


class TestSurge(unittest.TestCase):
    def test_one_surge_per_bout_after_the_delay(self):
        _, out = run(WITH_SURGE, [odor_sense()] * 100)
        requests = [(s, e) for s, e, p, _ in out if p is not None]
        self.assertEqual(len(requests), 1)
        state, elapsed = requests[0]
        self.assertEqual(state, 'ODOR_TRACK')
        self.assertGreaterEqual(elapsed, 0.07 - 1e-9)
        self.assertLess(elapsed, 0.07 + DT + 1e-9)
        entry = next(k for k, (s, _, _, _) in enumerate(out) if s == 'ODOR_TRACK')
        fired = next(k for k, (_, _, p, _) in enumerate(out) if p is not None)
        self.assertEqual(fired - entry, 4)

    def test_the_turn_is_the_sensed_upwind_bearing(self):
        for forward, lateral in ((-45.0, 1.0), (0.0, 45.0), (0.0, -45.0), (30.0, 30.0), (-30.0, -20.0)):
            _, out = run(WITH_SURGE, [odor_sense(forward, lateral)] * 40)
            angle, peak = next(p for _, _, p, _ in out if p is not None)
            self.assertAlmostEqual(angle, math.atan2(-lateral, -forward), places=12)
            self.assertTrue(math.radians(1200.0) <= peak <= math.radians(1500.0))

    def test_no_surge_under_a_threat(self):
        senses = [odor_sense()] * 60
        threats = [ThreatState.CALM] * 8 + [ThreatState.ALERT] * 52
        _, out = run(WITH_SURGE, senses, threats)
        entry = next(k for k, (s, _, _, _) in enumerate(out) if s == 'ODOR_TRACK')
        self.assertLess(entry, 8)
        fired = [k for k, (_, _, p, _) in enumerate(out) if p is not None]
        self.assertTrue(all(k < 8 for k in fired))

    def test_no_surge_without_reliable_wind(self):
        _, out = run(WITH_SURGE, [odor_sense(-3.0, 0.0)] * 60)
        self.assertTrue(any(s == 'ODOR_TRACK' for s, _, _, _ in out))
        self.assertTrue(all(p is None for _, _, p, _ in out))

    def test_a_new_bout_gets_a_new_surge(self):
        senses = [odor_sense()] * 40 + [EcologicalSense()] * 60 + [odor_sense()] * 40
        _, out = run(WITH_SURGE, senses)
        self.assertEqual(sum(1 for _, _, p, _ in out if p is not None), 2)


@unittest.skipUnless(ROOM['config_version'] == 34, 'the working ROOM configuration is not the M3.10 candidate')
class TestCandidate(unittest.TestCase):
    def test_only_the_preregistered_keys_change(self):
        self.assertEqual(set(changed_paths(V32, ROOM)) - ALLOWED_CHANGES, set())
        for key, expected in FLIGHT.items():
            self.assertEqual(value(ROOM, key), expected)
        self.assertEqual(set(ROOM['ecology']['upwind_surge']), set(SURGE))

    def test_the_frozen_values_are_kept(self):
        for key in ('steering_cap_rad_s', 'upwind_gain', 'odor_history', 'odor_cues', 'wind_reliability',
                    'intent_hazards', 'spontaneous_clock_rate', 'speed_bl_s'):
            self.assertEqual(ROOM['ecology'][key], V32['ecology'][key])
        self.assertEqual(ROOM['flight'], V32['flight'])

    def test_the_session_resolves_the_m3_10_record(self):
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
        bad = copy.deepcopy(ROOM)
        bad['ecology']['upwind_surge']['delay_seconds'] = 0.0
        with self.assertRaises(SystemExit):
            build_record(bad)


if __name__ == '__main__':
    unittest.main()
