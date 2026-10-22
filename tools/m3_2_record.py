"""Write the M3.2 escape-feature-roles transfer record (results/game/calibration_room_m3_2.json).

This is NOT a decoder recalibration. The accepted M1.8-N4B1C decoder and its threshold are
carried over byte for byte from the M1.7.2 transfer record. The behavioural change is the
encoder's feature model: `encoder.feature_model = ache2019_v1` with the calibrated
`encoder.ache2019.scale_volts_per_mv`. Its rule, calibration and checks are preregistered in
game/M3_2_ESCAPE_FEATURE_ROLES_DESIGN.md.

Because a record's provenance fingerprints the whole ROOM configuration, the new configuration
needs its own record. The M1.7.2 record is cited by content SHA256 and is not modified.

The tool refuses to write unless:
- the configuration differs from the v27 ROOM configuration (commit d67808f) only in
  config_version, policy._comment, policy.calibration_paths and the new encoder keys;
- the configured decoder equals the M1.7.2 record's decoder block;
- the configured scale equals the one the preregistered calibration chose
  (artifacts/m3_2/report.json, written by tools/m3_2_escape_roles.py report).

    python tools/m3_2_record.py
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

from game.perception import ACHE2019, FEATURE_MODEL_ACHE2019, encoder_feature_model  # noqa: E402
from game.session import calibration_provenance, escape_decoder_spec, load_config  # noqa: E402
from tools.b2b_iii_record import content_sha256  # noqa: E402
from tools.n2_decoder_record import changed_paths  # noqa: E402

CONFIG = ROOT / 'game_room_config.json'
RECORD = 'results/game/calibration_room_m3_2.json'
SOURCE_RECORD = 'results/game/calibration_room_m1_7_2.json'
BASELINE_COMMIT = 'd67808f62bef6a11205f65be6aad827b48f4d82a'   # main after M3.0, ROOM config_version 27
DESIGN_NOTE = 'game/M3_2_ESCAPE_FEATURE_ROLES_DESIGN.md'
RESEARCH_NOTE = 'game/M3_1_ESCAPE_DECISION_RESEARCH.md'
CALIBRATION_REPORT = ROOT / 'artifacts/m3_2/report.json'
ALLOWED_CHANGES = {'config_version', 'policy._comment', 'policy.calibration_paths',
                   'encoder.feature_model', 'encoder._feature_model_comment',
                   'encoder.ache2019'}


def baseline_config():
    return json.loads(subprocess.check_output(
        ['git', 'show', BASELINE_COMMIT + ':game_room_config.json'], cwd=ROOT, text=True))


def calibrated_scale():
    if not CALIBRATION_REPORT.exists():
        raise SystemExit('run python tools/m3_2_escape_roles.py report after the calibration first')
    calibration = json.loads(CALIBRATION_REPORT.read_text(encoding='utf-8'))['calibration']
    if calibration['chosen_scale_volts_per_mv'] is None:
        raise SystemExit('the preregistered calibration chose no scale (stop rule)')
    return calibration


def build_record(config=None):
    config = load_config(CONFIG) if config is None else config
    baseline = baseline_config()
    changed = changed_paths(baseline, config)
    unexpected = [p for p in changed if p not in ALLOWED_CHANGES]
    if unexpected:
        raise SystemExit('configuration differs from the v27 ROOM configuration outside the '
                         'M3.2 encoder keys: ' + ', '.join(unexpected))
    if config['config_version'] != baseline['config_version'] + 1:
        raise SystemExit('config_version must be %d' % (baseline['config_version'] + 1))
    if encoder_feature_model(config) != FEATURE_MODEL_ACHE2019:
        raise SystemExit('game_room_config.json must set encoder.feature_model = ' + FEATURE_MODEL_ACHE2019)
    if config['policy']['calibration_paths'][1] != RECORD:
        raise SystemExit('policy.calibration_paths must name ' + RECORD)
    calibration = calibrated_scale()
    scale = config['encoder']['ache2019']['scale_volts_per_mv']
    if scale != calibration['chosen_scale_volts_per_mv']:
        raise SystemExit('the configured scale %r is not the calibrated %r'
                         % (scale, calibration['chosen_scale_volts_per_mv']))
    source = load_config(ROOT / SOURCE_RECORD)
    if source['provenance'] != calibration_provenance(baseline):
        raise SystemExit('the M1.7.2 record does not match the v27 ROOM configuration')
    decoder = escape_decoder_spec(config)
    if escape_decoder_spec(baseline) != decoder:
        raise SystemExit('the configured decoder differs from the v27 configuration')
    if {k: source['escape_decoder'].get(k) for k in decoder} != decoder:
        raise SystemExit('the configured decoder differs from the M1.7.2 record decoder block')
    chosen = next(r for r in calibration['grid'] if r['scale_volts_per_mv'] == scale)
    record = {
        'record_kind': 'm3-2-encoder-feature-roles-transfer-provenance-v1',
        'stage': 'M3.2',
        'not_a_scalar_calibration': True,
        'not_a_decoder_recalibration': True,
        'decoder_unchanged': True,
        'geometry_changed': False,
        'encoder_changed': True,
        'rule': ('The accepted M1.8-N4B1C decoder, unchanged, with the ache2019_v1 encoder: LPLC2 is '
                 'driven by a Gaussian of log angular size and LC4 linearly by angular velocity, '
                 'both only while the stimulus expands (Ache et al. 2019, STAR Methods eqs. 3, 4 '
                 'and 7), times one scale from GF millivolts to volts.'),
        'escape_threshold': source['escape_threshold'],
        'escape_decoder': copy.deepcopy(source['escape_decoder']),
        'parameter_basis': copy.deepcopy(source['parameter_basis']),
        'geometry': copy.deepcopy(source['geometry']),
        'kinematics': copy.deepcopy(config.get('kinematics', {})),
        'ecology_threat_input': copy.deepcopy(config.get('ecology_threat_input')),
        'encoder': {
            'feature_model': FEATURE_MODEL_ACHE2019,
            'previous_feature_model': 'legacy_v0',
            'published_constants': dict(ACHE2019),
            'source': 'Ache et al. 2019, Curr Biol 29:1073-1081, doi:10.1016/j.cub.2019.01.079',
            'scale_volts_per_mv': scale,
            'scale_basis': ('the only calibrated constant; chosen by the preregistered grid search '
                            'against the peak times of the paper\'s own GF model '
                            '(tools/m3_2_ache_targets.py) on seeds 600001-600024, not against '
                            'behaviour'),
            'calibration_at_chosen_scale': chosen,
            'scope': 'ROOM configuration only; GAME and LAB configurations keep legacy_v0'},
        'design_note': DESIGN_NOTE,
        'research_note': RESEARCH_NOTE,
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
            'kind': 'encoder feature-model change; decoder transferred unchanged; not a new measurement',
            'source_record': SOURCE_RECORD,
            'source_sha256': content_sha256(SOURCE_RECORD),
            'baseline_commit': BASELINE_COMMIT,
            'reason': ('The decoder constants are Class C values that separate spontaneous DNp01 '
                       'coincidences from threat evidence. At rest both encoders inject nothing, so '
                       'the spontaneous side is unchanged. The threat side changes by design; the '
                       'preregistered checks V1-V6 replace a calibration-trial check.'),
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


if __name__ == '__main__':
    main()
