"""Write the M1.8-B3a ecology threat-input transfer provenance record.

This is NOT a recalibration and runs no new measurement. The accepted M1.8-N4B1C decoder
under the accepted M1.8-N4B5R geometry and M1.8-B2b-iii kinematics is carried over
byte-for-byte from the B2b-iii record. The only behavioural change is the ThreatState the
ecology receives (`ecology_threat_input.mode = executed_response_v1`); the lifecycle keeps
the accepted threat.

Because the record's provenance fingerprints the whole ROOM configuration, the new
configuration needs its own record. The accepted B2b-iii record
(results/game/calibration_room_m1_8_b2b_iii.json) is cited by SHA256 and is not modified.
No recalibration is needed: fixed-fly-v2 disables ecology, fly motion and collisions, so the
ecology's threat input cannot reach the calibration's retinal or neural input.

The tool refuses to write unless:
* the configuration differs from the accepted B2b-iii ROOM configuration (commit c4f9b8f)
  only in config_version, policy._comment, policy.calibration_paths and the new
  ecology_threat_input block; and
* the configured decoder equals the accepted B2b-iii record's decoder block.

    python tools/b3a_record.py
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

from game.session import (ECOLOGY_THREAT_EXECUTED, calibration_provenance,  # noqa: E402
                          ecology_threat_mode, escape_decoder_spec, load_config)
from tools.b2b_iii_record import content_sha256  # noqa: E402
from tools.n2_decoder_record import changed_paths  # noqa: E402

CONFIG = ROOT / 'game_room_config.json'
SOURCE_RECORD = 'results/game/calibration_room_m1_8_b2b_iii.json'
ORIGINAL_MEASUREMENT = 'results/game/calibration_room_m1_7_1.json'
ACCEPTED_RUNTIME_COMMIT = 'c4f9b8f8f4a1fc69959e1d74e5d76b4cc5b6e87f'
DESIGN_NOTE = 'game/M1_8_B3A_DESIGN.md'
ALLOWED_CHANGES = {'config_version', 'policy._comment', 'policy.calibration_paths',
                   'ecology_threat_input'}


def build_record():
    config = load_config(CONFIG)
    accepted = json.loads(subprocess.check_output(
        ['git', 'show', ACCEPTED_RUNTIME_COMMIT + ':game_room_config.json'], cwd=ROOT, text=True))
    changed = changed_paths(accepted, config)
    unexpected = [p for p in changed if p not in ALLOWED_CHANGES]
    if unexpected:
        raise SystemExit('configuration differs from the accepted B2b-iii ROOM configuration outside '
                         'the ecology_threat_input block: ' + ', '.join(unexpected))
    if ecology_threat_mode(config) != ECOLOGY_THREAT_EXECUTED:
        raise SystemExit('game_room_config.json must set ecology_threat_input.mode = '
                         + ECOLOGY_THREAT_EXECUTED)
    source = load_config(ROOT / SOURCE_RECORD)
    if source['provenance'] != calibration_provenance(accepted):
        raise SystemExit('the B2b-iii record does not match the accepted B2b-iii ROOM configuration')
    decoder = escape_decoder_spec(config)
    if escape_decoder_spec(accepted) != decoder:
        raise SystemExit('the configured decoder differs from the accepted N4B1C decoder')
    if {k: source['escape_decoder'].get(k) for k in decoder} != decoder:
        raise SystemExit('the configured decoder differs from the B2b-iii record decoder block')
    record = {
        'record_kind': 'ecology-threat-input-transfer-provenance-v1',
        'stage': 'M1.8-B3a',
        'not_a_scalar_calibration': True,
        'not_a_decoder_recalibration': True,
        'decoder_unchanged': True,
        'geometry_unchanged': True,
        'kinematics_unchanged': True,
        'ecology_threat_input_changed': True,
        'rule': ('The accepted M1.8-N4B1C lateral dual-path decoder, unchanged, under the accepted '
                 'M1.8-N4B5R paddle geometry and M1.8-B2b-iii kinematics, with the ecology '
                 'receiving the executed-response threat input. Neither the Retina, the encoder, '
                 'MaleCNS, the decoder nor the lifecycle threat input changes.'),
        'escape_threshold': source['escape_threshold'],
        'escape_decoder': copy.deepcopy(source['escape_decoder']),
        'parameter_basis': copy.deepcopy(source['parameter_basis']),
        'geometry': copy.deepcopy(source['geometry']),
        'kinematics': copy.deepcopy(source['kinematics']),
        'ecology_threat_input': {
            'mode': ECOLOGY_THREAT_EXECUTED,
            'previous_mode': 'policy_state_v0',
            'rule': ('the policy ALERT state alone, with no saccade requested on the tick and no '
                     'ALERT saccade executing, reaches the ecology as CALM; ESCAPE and executed '
                     'alert responses pass unchanged; the lifecycle receives the accepted threat'),
            'design_note': DESIGN_NOTE,
            'parameter_class': 'C (interface choice, not a biological parameter)'},
        'hash_convention': ('source records: SHA256 of committed content with CRLF normalised to '
                            'LF; config_sha256: raw working-file bytes'),
        'source_record': {'record': SOURCE_RECORD, 'sha256': content_sha256(SOURCE_RECORD),
                          'provenance': source['provenance'], 'record_kind': source['record_kind'],
                          'modified': False,
                          'note': 'the accepted B2b-iii record; it continues to match the accepted '
                                  'B2b-iii ROOM configuration (commit c4f9b8f)'},
        'tick_seconds': config['sim']['tick_seconds'],
        'config_sha256': hashlib.sha256(CONFIG.read_bytes()).hexdigest(),
        'provenance': calibration_provenance(config),
        'measurement_conditions': copy.deepcopy(source['measurement_conditions']),
        'measurement_reuse': {
            'kind': ('ecology threat-input stage; decoder, geometry and kinematics transferred '
                     'unchanged; not a new measurement'),
            'source_record': SOURCE_RECORD,
            'source_sha256': content_sha256(SOURCE_RECORD),
            'original_measurement': ORIGINAL_MEASUREMENT,
            'original_measurement_sha256': content_sha256(ORIGINAL_MEASUREMENT),
            'accepted_runtime_commit': ACCEPTED_RUNTIME_COMMIT,
            'reason': ('The threshold and decoder are not re-derived. fixed-fly-v2 disables ecology, '
                       'fly motion and collisions, so the ecology threat input cannot change the '
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
        raise SystemExit('refusing to overwrite the accepted B2b-iii record')
    path = ROOT / rel
    if path.exists() and path.read_text(encoding='utf-8') != text:
        print('replacing', rel)
    path.write_bytes(text.encode('utf-8'))
    print('written', rel, hashlib.sha256(path.read_bytes()).hexdigest())
    print('changed config paths:', record['measurement_reuse']['changed_config_paths'])


if __name__ == '__main__':
    main()
