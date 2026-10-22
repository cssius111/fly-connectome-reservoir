"""Write the M1.7.2 paddle-axis transfer record (results/game/calibration_room_m1_7_2.json).

This is NOT a recalibration and runs no new measurement. The accepted M1.8-N4B1C decoder and
its threshold are carried over byte-for-byte from the M1.8-B4b transfer record, as M1.8-N4B5R
carried them over for its geometry change. The only behavioural change is the paddle axis of
the ROOM visual geometry: `swatter.directional.paddle_axis = line_symmetric_v1`. Its rule,
invariant and checks are preregistered in game/M1_7_2_PADDLE_AXIS_DESIGN.md.

Because a record's provenance fingerprints the whole ROOM configuration, the new configuration
needs its own record. The B4b record is cited by content SHA256 and is not modified.

The tool refuses to write unless the configuration differs from the v1.0 ROOM configuration
(commit 5722166, M1.8-B4b) only in config_version, policy._comment, policy.calibration_paths and
the two new swatter.directional paddle-axis keys, and unless the configured decoder equals the
B4b record's decoder block. The calibration-trial evidence of check C2 is read from
artifacts/m1_7_2/c2-calibration-trials.json and summarised in the record. The v27 session
needs the record to start, so the record is written once before C2 and again after it.

    python tools/m1_7_2_axis_record.py
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
from game.world import PADDLE_AXIS_HEADING, PADDLE_AXIS_LINE  # noqa: E402
from tools.b2b_iii_record import content_sha256  # noqa: E402
from tools.n2_decoder_record import changed_paths  # noqa: E402

CONFIG = ROOT / 'game_room_config.json'
RECORD = 'results/game/calibration_room_m1_7_2.json'
SOURCE_RECORD = 'results/game/calibration_room_m1_8_b4b.json'
ORIGINAL_MEASUREMENT = 'results/game/calibration_room_m1_7_1.json'
BASELINE_COMMIT = '57221665cfae656d5e3e367436ff32d2bbfc7473'   # tag v1.0, ROOM config_version 26
DESIGN_NOTE = 'game/M1_7_2_PADDLE_AXIS_DESIGN.md'
EVIDENCE_NOTE = 'results/game/M1_8_STOP_ROTATION_AUDIT.md'
C2_EVIDENCE = ROOT / 'artifacts/m1_7_2/c2-calibration-trials.json'
ALLOWED_CHANGES = {'config_version', 'policy._comment', 'policy.calibration_paths',
                   'swatter.directional.paddle_axis', 'swatter.directional._paddle_axis_comment'}


def baseline_config():
    return json.loads(subprocess.check_output(
        ['git', 'show', BASELINE_COMMIT + ':game_room_config.json'], cwd=ROOT, text=True))


def calibration_trial_evidence():
    """Summary of check C2 on the calibration protocol's trials, if it has been run."""
    if not C2_EVIDENCE.exists():
        return None
    data = json.loads(C2_EVIDENCE.read_text(encoding='utf-8'))
    return {'trials': data['trials'], 'folded_ticks': data['folded_ticks'],
            'folded_trials': data['folded_trials'], 'first_fold_in_settle_trials': data['first_fold_in_settle_trials'],
            'bit_identical_trials': data['bit_identical_trials'], 'invariant_holds': data['invariant_holds'],
            'exact_reuse': data['folded_ticks'] == 0 and data['bit_identical_trials'] == data['trials'],
            'descriptive_not_rederived': data['descriptive']}


def reuse_reason(evidence):
    text = ('The threshold and decoder are not re-derived. Until its first folded sub-step the line axis '
            'repeats the heading tracker exactly (check C2 of the design note). ')
    if evidence is None:
        return text + 'Check C2 has not been run yet.'
    if evidence['exact_reuse']:
        return text + 'No calibration trial folds, so the measurement sees an identical Retina input.'
    return text + ('In the calibration protocol the line axis folds in %d of %d trials, always while the paddle '
                   'travels to its hover point, so the reuse is not exact. The measured windows of the no-loom '
                   'trials carry no apparent expansion under either configuration, and the no-loom DNp01 '
                   'statistics differ by about as much as v26 differs between reset seeds '
                   '(results/game/M1_7_2_PADDLE_AXIS.md, section 3). As for M1.8-N4B5R, the decoder is '
                   'carried over unchanged.' % (evidence['folded_trials'], evidence['trials']))


def build_record(config=None):
    config = load_config(CONFIG) if config is None else config
    baseline = baseline_config()
    changed = changed_paths(baseline, config)
    unexpected = [p for p in changed if p not in ALLOWED_CHANGES]
    if unexpected:
        raise SystemExit('configuration differs from the v1.0 ROOM configuration outside the '
                         'paddle-axis keys: ' + ', '.join(unexpected))
    if config['config_version'] != baseline['config_version'] + 1:
        raise SystemExit('config_version must be %d' % (baseline['config_version'] + 1))
    if config['swatter']['directional'].get('paddle_axis') != PADDLE_AXIS_LINE:
        raise SystemExit('game_room_config.json must set swatter.directional.paddle_axis = ' + PADDLE_AXIS_LINE)
    if config['policy']['calibration_paths'][1] != RECORD:
        raise SystemExit('policy.calibration_paths must name ' + RECORD)
    source = load_config(ROOT / SOURCE_RECORD)
    if source['provenance'] != calibration_provenance(baseline):
        raise SystemExit('the B4b record does not match the v1.0 ROOM configuration')
    decoder = escape_decoder_spec(config)
    if escape_decoder_spec(baseline) != decoder:
        raise SystemExit('the configured decoder differs from the v1.0 configuration')
    if {k: source['escape_decoder'].get(k) for k in decoder} != decoder:
        raise SystemExit('the configured decoder differs from the B4b record decoder block')
    evidence = calibration_trial_evidence()
    geometry = copy.deepcopy(source['geometry'])
    geometry.update({
        'paddle_axis': PADDLE_AXIS_LINE,
        'previous_paddle_axis': PADDLE_AXIS_HEADING,
        'axis_note': ('the tilt term reads the paddle line axis instead of swatter.orientation; the '
                      'line axis steers like the 360-degree heading tracker but folds an error above '
                      '90 degrees to the opposite direction, so a reversal no longer spins the paddle'),
        'axis_reason': ('reversal spins of the frozen M1.7.1 controller add about 0.35 escapes per hover '
                        'minute in recorded human play (' + EVIDENCE_NOTE + ')'),
        'axis_scope': 'ROOM configuration only; GAME and LAB configurations are unchanged'})
    record = {
        'record_kind': 'm1-7-2-paddle-axis-transfer-provenance-v1',
        'stage': 'M1.7.2',
        'not_a_scalar_calibration': True,
        'not_a_decoder_recalibration': True,
        'decoder_unchanged': True,
        'geometry_changed': True,
        'rule': ('The accepted M1.8-N4B1C decoder, unchanged, with the M1.7.2 paddle line axis in the '
                 'visual geometry. The Retina input changes only after the line axis first folds its '
                 'steering error, which needs a turn of the paddle velocity by more than 90 degrees.'),
        'escape_threshold': source['escape_threshold'],
        'escape_decoder': copy.deepcopy(source['escape_decoder']),
        'parameter_basis': copy.deepcopy(source['parameter_basis']),
        'geometry': geometry,
        'kinematics': copy.deepcopy(config.get('kinematics', {})),
        'ecology_threat_input': copy.deepcopy(config.get('ecology_threat_input')),
        'design_note': DESIGN_NOTE,
        'evidence_note': EVIDENCE_NOTE,
        'hash_convention': ('source records: SHA256 of committed content with CRLF normalised to '
                            'LF; config_sha256: raw working-file bytes'),
        'source_record': {'record': SOURCE_RECORD, 'sha256': content_sha256(SOURCE_RECORD),
                          'provenance': source['provenance'], 'record_kind': source['record_kind'],
                          'modified': False},
        'tick_seconds': config['sim']['tick_seconds'],
        'config_sha256': hashlib.sha256(CONFIG.read_bytes()).hexdigest(),
        'provenance': calibration_provenance(config),
        'measurement_conditions': copy.deepcopy(source['measurement_conditions']),
        'measurement_reuse': {
            'kind': 'paddle-axis geometry change; decoder transferred unchanged; not a new measurement',
            'source_record': SOURCE_RECORD,
            'source_sha256': content_sha256(SOURCE_RECORD),
            'original_measurement': ORIGINAL_MEASUREMENT,
            'original_measurement_sha256': content_sha256(ORIGINAL_MEASUREMENT),
            'baseline_commit': BASELINE_COMMIT,
            'reason': reuse_reason(evidence),
            'calibration_trials_c2': evidence,
            'changed_config_paths': changed},
        'neurons': source['neurons'], 'connections': source['connections'],
        'input_populations': source['input_populations'], 'versions': source['versions'],
    }
    return record


def main():
    record = build_record()
    text = json.dumps(record, indent=2) + '\n'
    path = ROOT / RECORD
    if path.exists() and path.read_text(encoding='utf-8') != text:
        print('replacing', RECORD)
    path.write_bytes(text.encode('utf-8'))
    print('wrote', RECORD)
    if record['measurement_reuse']['calibration_trials_c2'] is None:
        # The v27 session needs this record to start, so check C2 runs after a first write.
        print('check C2 has not been run: run python tools/m1_7_2_axis_checks.py calibration, '
              'then rerun this tool before committing the record')


if __name__ == '__main__':
    main()
