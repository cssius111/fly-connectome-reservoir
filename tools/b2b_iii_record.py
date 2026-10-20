"""Write the M1.8-B2b-iii kinematics transfer provenance record.

This is NOT a recalibration and runs no new measurement. The accepted M1.8-N4B1C decoder
under the accepted M1.8-N4B5R geometry is carried over byte-for-byte from the N4B5R record.
The only behavioural change is ecological kinematics: one sampled ODOR_TRACK target per
ODOR_TRACK episode (`kinematics.odor_track_speed_bl_s`).

Because the record's provenance fingerprints the whole ROOM configuration, the new
configuration needs its own record. The accepted N4B5R record
(results/game/calibration_room_m1_8_n4b5r.json) is cited by SHA256 and is not modified.
No recalibration is needed: fixed-fly-v2 disables ecology, fly motion and collisions, so
ODOR_TRACK sampling cannot reach the calibration's retinal or neural input.

The tool refuses to write unless:
* the configuration differs from the accepted N4B5R ROOM configuration (commit 363a1a9)
  only in config_version, policy._comment, policy.calibration_paths and the new
  kinematics.odor_track_speed_bl_s block; and
* the configured decoder equals the accepted N4B5R record's decoder block.

    python tools/b2b_iii_record.py
"""
from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from game.session import calibration_provenance, escape_decoder_spec, load_config  # noqa: E402
from tools.n2_decoder_record import changed_paths  # noqa: E402

CONFIG = ROOT / 'game_room_config.json'
SOURCE_RECORD = 'results/game/calibration_room_m1_8_n4b5r.json'
ORIGINAL_MEASUREMENT = 'results/game/calibration_room_m1_7_1.json'
ACCEPTED_RUNTIME_COMMIT = '363a1a94cf3f5e33efab08cb28594c24ca694a03'
DESIGN_NOTE = 'game/M1_8_B2B_III_DESIGN.md'
ALLOWED_CHANGES = {'config_version', 'policy._comment', 'policy.calibration_paths',
                   'kinematics.odor_track_speed_bl_s'}
TEXT_SUFFIXES = {'.md', '.py', '.json', '.txt'}


def content_sha256(path):
    """SHA256 of committed content (CRLF normalised to LF for text files)."""
    data = (ROOT / path).read_bytes()
    if Path(path).suffix in TEXT_SUFFIXES:
        data = data.replace(b'\r\n', b'\n')
    return hashlib.sha256(data).hexdigest()


def build_record():
    config = load_config(CONFIG)
    accepted = json.loads(subprocess.check_output(
        ['git', 'show', ACCEPTED_RUNTIME_COMMIT + ':game_room_config.json'], cwd=ROOT, text=True))
    changed = changed_paths(accepted, config)
    unexpected = [p for p in changed if p not in ALLOWED_CHANGES]
    if unexpected:
        raise SystemExit('configuration differs from the accepted N4B5R ROOM configuration outside '
                         'the ODOR_TRACK sampling block: ' + ', '.join(unexpected))
    spec = config.get('kinematics', {}).get('odor_track_speed_bl_s')
    if not spec:
        raise SystemExit('game_room_config.json must define kinematics.odor_track_speed_bl_s')
    source = load_config(ROOT / SOURCE_RECORD)
    if source['provenance'] != calibration_provenance(accepted):
        raise SystemExit('the N4B5R record does not match the accepted N4B5R ROOM configuration')
    decoder = escape_decoder_spec(config)
    if escape_decoder_spec(accepted) != decoder:
        raise SystemExit('the configured decoder differs from the accepted N4B1C decoder')
    if {k: source['escape_decoder'].get(k) for k in decoder} != decoder:
        raise SystemExit('the configured decoder differs from the N4B5R record decoder block')
    envelope = config['ecology']['speed_bl_s']['ODOR_TRACK']
    record = {
        'record_kind': 'kinematics-transfer-provenance-v1',
        'stage': 'M1.8-B2b-iii',
        'not_a_scalar_calibration': True,
        'not_a_decoder_recalibration': True,
        'decoder_unchanged': True,
        'geometry_unchanged': True,
        'kinematics_changed': True,
        'rule': ('The accepted M1.8-N4B1C lateral dual-path decoder, unchanged, under the accepted '
                 'M1.8-N4B5R paddle geometry, with one sampled ODOR_TRACK speed target per '
                 'ecological ODOR_TRACK episode. Neither the Retina, the encoder, MaleCNS nor the '
                 'decoder changes.'),
        'escape_threshold': source['escape_threshold'],
        'escape_decoder': copy.deepcopy(source['escape_decoder']),
        'parameter_basis': copy.deepcopy(source['parameter_basis']),
        'geometry': copy.deepcopy(source['geometry']),
        'kinematics': {
            'context': 'ODOR_TRACK',
            'config_path': 'kinematics.odor_track_speed_bl_s',
            'distribution': spec['distribution'],
            'support_bl_s': [spec['min_bl_s'], spec['max_bl_s']],
            'mode_bl_s': spec['mode_bl_s'],
            'accepted_envelope_bl_s': envelope,
            'room_kinematic_scale': config['kinematics']['room_kinematic_scale'],
            'design_note': DESIGN_NOTE,
            'parameter_class': ('C for the shape and the mode, B inherited for the support; '
                                'phenomenological, not a biological measurement')},
        'hash_convention': ('source records: SHA256 of committed content with CRLF normalised to '
                            'LF; config_sha256: raw working-file bytes'),
        'source_record': {'record': SOURCE_RECORD, 'sha256': content_sha256(SOURCE_RECORD),
                          'provenance': source['provenance'], 'record_kind': source['record_kind'],
                          'modified': False,
                          'note': 'the accepted N4B5R record; it continues to match the accepted '
                                  'N4B5R ROOM configuration (commit 363a1a9)'},
        'tick_seconds': config['sim']['tick_seconds'],
        'config_sha256': hashlib.sha256(CONFIG.read_bytes()).hexdigest(),
        'provenance': calibration_provenance(config),
        'measurement_conditions': copy.deepcopy(source['measurement_conditions']),
        'measurement_reuse': {
            'kind': 'kinematics stage; decoder and geometry transferred unchanged; not a new measurement',
            'source_record': SOURCE_RECORD,
            'source_sha256': content_sha256(SOURCE_RECORD),
            'original_measurement': ORIGINAL_MEASUREMENT,
            'original_measurement_sha256': content_sha256(ORIGINAL_MEASUREMENT),
            'accepted_runtime_commit': ACCEPTED_RUNTIME_COMMIT,
            'reason': ('The threshold and decoder are not re-derived. fixed-fly-v2 disables ecology, '
                       'fly motion and collisions, so ODOR_TRACK speed sampling cannot change the '
                       'retinal or neural input of the measurement behind them.'),
            'changed_config_paths': changed},
        'neurons': source['neurons'], 'connections': source['connections'],
        'input_populations': source['input_populations'], 'versions': source['versions'],
    }
    return config, record


def main():
    config, record = build_record()
    text = json.dumps(record, indent=2) + '\n'
    rel = config['policy']['calibration_paths'][1]
    if rel == SOURCE_RECORD:
        raise SystemExit('refusing to overwrite the accepted N4B5R record')
    path = ROOT / rel
    if path.exists() and path.read_text(encoding='utf-8') != text:
        print('replacing', rel)
    path.write_bytes(text.encode('utf-8'))
    print('written', rel, hashlib.sha256(path.read_bytes()).hexdigest())
    print('changed config paths:', record['measurement_reuse']['changed_config_paths'])


if __name__ == '__main__':
    main()
