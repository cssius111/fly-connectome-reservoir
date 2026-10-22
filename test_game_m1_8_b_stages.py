"""M1.8-B completion stages: configuration scope and the calibration provenance chain.

Every stage registered in tools/m1_8_b_stage_record.py must change only its preregistered
configuration paths relative to the previous stage, bump config_version by one, and carry a
transfer record bound to its own configuration that reuses the previous record and the
M1.7.1 measurement unchanged (game/M1_8_B_COMPLETION_DESIGN.md section 1).
"""
import copy
import os
from pathlib import Path
import subprocess
import unittest

os.environ.setdefault('NUMBA_NUM_THREADS', '4')
os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')

from game.kinematics import KinematicSampler
from game.session import calibration_provenance, load_config, resolve_escape_threshold
from test_game import same_content
from tools.m1_8_b_stage_record import FROZEN_AT, STAGES, allowed, build_record, lookup, read_commit, stage_config
from tools.n2_decoder_record import changed_paths

ROOT = Path(__file__).parent
B3A_COMMIT = '6b43c0fd2cf5537216bb5f663b4e606e0fac76f6'
B3A_RECORD = 'results/game/calibration_room_m1_8_b3a.json'
ORIGINAL = 'results/game/calibration_room_m1_7_1.json'


class TestStageScope(unittest.TestCase):
    def test_each_stage_changes_only_its_preregistered_paths(self):
        for stage, spec in STAGES.items():
            with self.subTest(stage=stage):
                before, after = read_commit(spec['baseline_commit']), stage_config(stage)
                self.assertEqual(after['config_version'], spec['config_version'])
                self.assertEqual(after['config_version'], before['config_version'] + 1)
                changed = changed_paths(before, after)
                self.assertTrue(changed)
                for path in changed:
                    self.assertTrue(allowed(path, spec['paths']), path)

    def test_stages_form_one_chain_from_the_accepted_b3a_runtime(self):
        names = list(STAGES)
        self.assertEqual(STAGES[names[0]]['baseline_commit'], B3A_COMMIT)
        self.assertEqual(STAGES[names[0]]['source_record'], B3A_RECORD)
        for previous, stage in zip(names, names[1:]):
            self.assertEqual(STAGES[stage]['source_record'], STAGES[previous]['record'])
            self.assertEqual(STAGES[stage]['config_version'], STAGES[previous]['config_version'] + 1)

    def test_the_newest_stage_is_frozen_at_v1_0(self):
        # B4b is the ROOM configuration of tag v1.0; M1.7.2 follows with its own record writer.
        newest = list(STAGES)[-1]
        room = stage_config(newest)
        self.assertEqual(room, read_commit(FROZEN_AT))
        self.assertEqual(room['config_version'], STAGES[newest]['config_version'])
        self.assertEqual(resolve_escape_threshold(room).origin, STAGES[newest]['record'])
        self.assertGreater(load_config(ROOT/'game_room_config.json')['config_version'], room['config_version'])

    def test_the_builder_rejects_a_change_outside_the_stage(self):
        newest = list(STAGES)[-1]
        config = copy.deepcopy(stage_config(newest))
        config['ecology']['speed_tau_seconds'] = 0.4
        with self.assertRaises(SystemExit):
            build_record(newest, config)


class TestStageRecords(unittest.TestCase):
    def test_each_record_is_bound_to_its_configuration_and_its_source(self):
        for stage, spec in STAGES.items():
            with self.subTest(stage=stage):
                config, record = stage_config(stage), load_config(ROOT/spec['record'])
                source = load_config(ROOT/spec['source_record'])
                self.assertEqual(record['record_kind'], 'm1-8-b-stage-transfer-provenance-v1')
                self.assertEqual(record['stage'], 'M1.8-' + stage)
                self.assertEqual(record['provenance'], calibration_provenance(config))
                resolved = resolve_escape_threshold(config)
                self.assertEqual(resolved.origin, spec['record'])
                self.assertEqual(resolved.threshold, 1.45)
                for key in ('escape_threshold', 'escape_decoder', 'geometry', 'parameter_basis'):
                    self.assertEqual(record[key], source[key], key)
                self.assertTrue(record['decoder_unchanged'] and record['geometry_unchanged'])
                self.assertTrue(same_content(ROOT/spec['source_record'], record['source_record']['sha256']))
                reuse = record['measurement_reuse']
                self.assertEqual(reuse['original_measurement'], ORIGINAL)
                self.assertTrue(same_content(ROOT/ORIGINAL, reuse['original_measurement_sha256']))
                self.assertEqual(reuse['baseline_commit'], spec['baseline_commit'])
                self.assertEqual(record['stage_values'], {p: lookup(config, p) for p in spec['paths']})

    def test_earlier_records_are_committed_unchanged(self):
        names = list(STAGES)
        for stage, following in zip(names, names[1:]):
            rel = STAGES[stage]['record']
            committed = subprocess.check_output(
                ['git', 'show', STAGES[following]['baseline_commit'] + ':' + rel], cwd=ROOT)
            self.assertEqual((ROOT/rel).read_bytes().replace(b'\r\n', b'\n'),
                             committed.replace(b'\r\n', b'\n'), rel)

    def test_the_accepted_b3a_record_still_resolves_for_its_configuration(self):
        self.assertEqual(resolve_escape_threshold(read_commit(B3A_COMMIT)).origin, B3A_RECORD)


class TestStreams(unittest.TestCase):
    def test_new_stream_offsets_are_unique(self):
        accepted = {0, 977, 3907, 6011, 7013, 8191, 18001,
                    KinematicSampler.SEED_OFFSET, KinematicSampler.ODOR_TRACK_SEED_OFFSET}
        new = [36263, 42061, 47933, 53113, 59011, 64747, 70001]
        self.assertEqual(len(set(new)), len(new))
        self.assertFalse(accepted & set(new))
        self.assertEqual(KinematicSampler.ODOR_SEARCH_SEED_OFFSET, 36263)
        self.assertEqual(KinematicSampler.RECOVER_SEED_OFFSET, 42061)


if __name__ == '__main__':
    unittest.main()
