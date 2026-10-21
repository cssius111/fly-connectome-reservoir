"""M1.8-B3a: the ecology receives the executed-response threat input.

The lifecycle keeps the accepted threat. These tests pin the mapping truth table, the
default, the session's split of the two inputs, the configuration versioning and the
provenance chain (game/M1_8_B3A_DESIGN.md).
"""
import copy
import json
import os
from pathlib import Path
import subprocess
import unittest

os.environ.setdefault('NUMBA_NUM_THREADS', '4')
os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')

from game.action import Action
from game.ecology import ThreatState
from game.session import (ECOLOGY_THREAT_EXECUTED, ECOLOGY_THREAT_POLICY_STATE, Session,
                          build_policy, calibration_provenance, ecological_threat,
                          ecology_threat_mode, load_config, resolve_escape_threshold)
from test_game import same_content, shared_brain

ROOT = Path(__file__).parent
ROOM = load_config(ROOT/'game_room_config.json')
GAME = load_config(ROOT/'game_play_config.json')
LAB = load_config(ROOT/'game_config.json')
B2B_III_COMMIT = 'c4f9b8f8f4a1fc69959e1d74e5d76b4cc5b6e87f'
B2B_III_ROOM = json.loads(subprocess.check_output(
    ['git', 'show', B2B_III_COMMIT + ':game_room_config.json'], cwd=ROOT, text=True))
RECORD = 'results/game/calibration_room_m1_8_b3a.json'
SOURCE = 'results/game/calibration_room_m1_8_b2b_iii.json'


class StubPolicy:
    """Reports a fixed behaviour state and returns a fixed action; no neural decision."""

    def __init__(self, state, action):
        self.state, self.action = state, action

    def reset(self):
        pass

    def decide(self, motor):
        return self.action

    def diagnostics(self):
        return {'behavior_state': self.state}


class TestMapping(unittest.TestCase):
    def test_truth_table(self):
        T = ThreatState
        cases = [  # threat, saccade requested, executing saccade kind, ecology under B3a
            (T.ALERT, False, 'NONE', T.CALM),          # the policy's ALERT state alone
            (T.ALERT, False, 'SPONTANEOUS', T.CALM),
            (T.ALERT, True, 'NONE', T.ALERT),          # an alert saccade requested
            (T.ALERT, False, 'ALERT', T.ALERT),        # an ALERT saccade executing
            (T.ESCAPE, False, 'NONE', T.ESCAPE),
            (T.ESCAPE, True, 'ESCAPE', T.ESCAPE),
            (T.CALM, False, 'NONE', T.CALM)]
        for threat, requested, kind, expected in cases:
            self.assertIs(ecological_threat(threat, ECOLOGY_THREAT_EXECUTED, requested, kind), expected)
            # The accepted mapping hands the ecology the lifecycle's threat unchanged.
            self.assertIs(ecological_threat(threat, ECOLOGY_THREAT_POLICY_STATE, requested, kind), threat)

    def test_modes_and_defaults(self):
        self.assertEqual(ecology_threat_mode(ROOM), ECOLOGY_THREAT_EXECUTED)
        for config in (GAME, LAB, B2B_III_ROOM):
            self.assertNotIn('ecology_threat_input', config)
            self.assertEqual(ecology_threat_mode(config), ECOLOGY_THREAT_POLICY_STATE)
        bad = copy.deepcopy(ROOM)
        bad['ecology_threat_input']['mode'] = 'executed_response_v2'
        with self.assertRaisesRegex(ValueError, 'unknown ecology_threat_input.mode'):
            ecology_threat_mode(bad)


class TestSessionSplitsTheThreat(unittest.TestCase):
    def threats(self, config, state, action, ticks=5):
        session = Session(config, brain=shared_brain(), policy=StubPolicy(state, action),
                          seed=255, mode='evaluation')
        seen = {'ecology': [], 'lifecycle': []}
        eco_step, life_step = session.ecology.step, session.world.lifecycle.step

        def ecology(sense, threat, dt):
            seen['ecology'].append(threat)
            return eco_step(sense, threat, dt)

        def lifecycle(sense, motion, threat, dt, authorized=False):
            seen['lifecycle'].append(threat)
            return life_step(sense, motion, threat, dt, authorized)

        session.ecology.step, session.world.lifecycle.step = ecology, lifecycle
        for _ in range(ticks):
            session.tick(pointer=(1920, 388.8))
        session.close()
        return seen

    def test_policy_alert_state_alone_reaches_only_the_lifecycle(self):
        seen = self.threats(ROOM, 'ALERT', Action())
        self.assertEqual(set(seen['ecology']), {ThreatState.CALM})
        self.assertEqual(set(seen['lifecycle']), {ThreatState.ALERT})

    def test_requested_alert_saccade_reaches_both(self):
        seen = self.threats(ROOM, 'ALERT', Action(saccade=0.6))
        self.assertEqual(set(seen['ecology']), {ThreatState.ALERT})
        self.assertEqual(set(seen['lifecycle']), {ThreatState.ALERT})

    def test_accepted_mapping_is_restored_without_the_block(self):
        seen = self.threats(B2B_III_ROOM, 'ALERT', Action())
        self.assertEqual(set(seen['ecology']), {ThreatState.ALERT})
        self.assertEqual(seen['ecology'], seen['lifecycle'])

    def test_unknown_mode_is_rejected_by_the_session(self):
        bad = copy.deepcopy(ROOM)
        bad['ecology_threat_input']['mode'] = 'unknown'
        with self.assertRaisesRegex(ValueError, 'unknown ecology_threat_input.mode'):
            Session(bad, brain=shared_brain(), policy=StubPolicy('CALM', Action()), seed=1)


class TestScopeAndVersioning(unittest.TestCase):
    def test_room_differs_from_the_accepted_b2b_iii_config_only_in_the_threat_input(self):
        self.assertEqual(ROOM['config_version'], B2B_III_ROOM['config_version'] + 1)
        after = copy.deepcopy(ROOM)
        after['config_version'] = B2B_III_ROOM['config_version']
        after.pop('ecology_threat_input')
        after['policy']['_comment'] = B2B_III_ROOM['policy']['_comment']
        after['policy']['calibration_paths'] = B2B_III_ROOM['policy']['calibration_paths']
        self.assertEqual(after, B2B_III_ROOM)


class TestProvenance(unittest.TestCase):
    def test_room_resolves_the_transfer_record_with_the_unchanged_decoder(self):
        source = resolve_escape_threshold(ROOM)
        self.assertEqual(source.origin, RECORD)
        self.assertEqual(source.threshold, 1.45)
        self.assertEqual(source.decoder, resolve_escape_threshold(B2B_III_ROOM).decoder)
        self.assertEqual(vars(build_policy(ROOM)[0]), vars(build_policy(B2B_III_ROOM)[0]))

    def test_record_states_the_threat_input_change_and_unchanged_decoder(self):
        record, source = load_config(ROOT/RECORD), load_config(ROOT/SOURCE)
        self.assertEqual(record['record_kind'], 'ecology-threat-input-transfer-provenance-v1')
        self.assertTrue(record['decoder_unchanged'] and record['geometry_unchanged']
                        and record['kinematics_unchanged'] and record['ecology_threat_input_changed'])
        self.assertEqual(record['provenance'], calibration_provenance(ROOM))
        for key in ('escape_threshold', 'escape_decoder', 'geometry', 'kinematics'):
            self.assertEqual(record[key], source[key], key)
        self.assertEqual(record['ecology_threat_input']['mode'], ECOLOGY_THREAT_EXECUTED)
        reuse = record['measurement_reuse']
        self.assertEqual(reuse['source_record'], SOURCE)
        self.assertTrue(same_content(ROOT/SOURCE, reuse['source_sha256']))
        self.assertTrue(same_content(ROOT/reuse['original_measurement'], reuse['original_measurement_sha256']))
        self.assertEqual(sorted(reuse['changed_config_paths']),
                         ['config_version', 'ecology_threat_input', 'policy._comment',
                          'policy.calibration_paths'])

    def test_b2b_iii_record_is_unmodified_and_still_bound_to_its_config(self):
        committed = subprocess.check_output(['git', 'show', B2B_III_COMMIT + ':' + SOURCE], cwd=ROOT)
        self.assertEqual((ROOT/SOURCE).read_bytes().replace(b'\r\n', b'\n'), committed.replace(b'\r\n', b'\n'))
        self.assertEqual(resolve_escape_threshold(B2B_III_ROOM).origin, SOURCE)

    def test_threat_input_mode_is_bound_into_provenance(self):
        cfg = copy.deepcopy(ROOM)
        cfg['ecology_threat_input']['mode'] = ECOLOGY_THREAT_POLICY_STATE
        with self.assertRaisesRegex(ValueError, 'No matching'):
            resolve_escape_threshold(cfg)


if __name__ == '__main__':
    unittest.main()
