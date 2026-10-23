"""Write the M3.3 escape-decision record (results/game/calibration_room_m3_3.json).

M3.3 (game/M3_3_ESCAPE_DECISION_DESIGN.md) replaces the M1.8-N4B1C decoder of the ROOM
configuration by the same_side_doublet_v1 decoder and uses the M3.2 ache2019_v1 encoder with a
recalibrated scale. The alert reference threshold (1.45) is carried over from the M1.7.2 record,
whose decoder it replaces; the record cites that record by content SHA256 and does not modify it.

The tool refuses to write unless:
- the configuration differs from the v27 ROOM configuration (commit b5e6021) only in
  config_version, policy._comment, policy.calibration_paths, policy.escape_decoder and the
  encoder's feature-model keys;
- the configured decoder is the preregistered same_side_doublet_v1 block;
- the configured scale equals the one the preregistered calibration chose
  (artifacts/m3_3_run/report.json, written by tools/m3_3_escape_decision.py report).

    python tools/m3_3_record.py
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
from game.session import (DOUBLET_DECODER, calibration_provenance, escape_decoder_spec,  # noqa: E402
                          load_config)
from tools.b2b_iii_record import content_sha256  # noqa: E402
from tools.n2_decoder_record import changed_paths  # noqa: E402

CONFIG = ROOT / 'game_room_config.json'
RECORD = 'results/game/calibration_room_m3_3.json'
SOURCE_RECORD = 'results/game/calibration_room_m1_7_2.json'
BASELINE_COMMIT = 'b5e6021d6dc7d7636071a12a8b6eaa0952e327d4'   # main after M3.2, ROOM config_version 27
DESIGN_NOTE = 'game/M3_3_ESCAPE_DECISION_DESIGN.md'
RESEARCH_NOTE = 'game/M3_3_ESCAPE_DECISION_RESEARCH.md'
CALIBRATION_REPORT = ROOT / 'artifacts/m3_3_run/report.json'
PREREGISTERED_DECODER = {'kind': DOUBLET_DECODER, 'alert_reference_threshold': 1.45,
                         'doublet_window_ms': 40.0, 'required_spikes': 2}
ALLOWED_PREFIXES = ('policy.escape_decoder.',)
ALLOWED_CHANGES = {'config_version', 'policy._comment', 'policy.calibration_paths',
                   'encoder.feature_model', 'encoder._feature_model_comment', 'encoder.ache2019'}


def baseline_config():
    commit = subprocess.check_output(['git', 'rev-parse', BASELINE_COMMIT], cwd=ROOT, text=True).strip()
    return commit, json.loads(subprocess.check_output(
        ['git', 'show', commit + ':game_room_config.json'], cwd=ROOT, text=True))


def calibrated_scale():
    if not CALIBRATION_REPORT.exists():
        raise SystemExit('run python tools/m3_3_escape_decision.py report after the calibration first')
    calibration = json.loads(CALIBRATION_REPORT.read_text(encoding='utf-8'))['calibration']
    if calibration['chosen_scale_volts_per_mv'] is None:
        raise SystemExit('the preregistered calibration chose no scale (stop rule)')
    return calibration


def build_record(config=None):
    config = load_config(CONFIG) if config is None else config
    commit, baseline = baseline_config()
    changed = changed_paths(baseline, config)
    unexpected = [p for p in changed if p not in ALLOWED_CHANGES and not p.startswith(ALLOWED_PREFIXES)]
    if unexpected:
        raise SystemExit('configuration differs from the v27 ROOM configuration outside the M3.3 '
                         'encoder and decoder keys: ' + ', '.join(unexpected))
    if config['config_version'] != 29:
        raise SystemExit('config_version must be 29')
    if encoder_feature_model(config) != FEATURE_MODEL_ACHE2019:
        raise SystemExit('game_room_config.json must set encoder.feature_model = ' + FEATURE_MODEL_ACHE2019)
    decoder = escape_decoder_spec(config)
    if decoder != PREREGISTERED_DECODER:
        raise SystemExit('the configured decoder is not the preregistered same_side_doublet_v1 block')
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
    if source['escape_threshold'] != decoder['alert_reference_threshold']:
        raise SystemExit('the alert reference must equal the carried-over threshold')
    chosen = next(r for r in calibration['grid'] if r['scale_volts_per_mv'] == scale)
    return {
        'record_kind': 'm3-3-escape-decision-record-v1',
        'stage': 'M3.3',
        'not_a_scalar_calibration': True,
        'decoder_unchanged': False,
        'decoder_replaced': True,
        'encoder_changed': True,
        'geometry_changed': False,
        'rule': ('Escape only when one DNp01 side produces two inferred spikes at most 40 ms apart '
                 '(same_side_doublet_v1); the N2b summed paths of N4B1C do not exist. The encoder is '
                 'ache2019_v1: LPLC2 by a Gaussian of log angular size and LC4 linearly by angular '
                 'velocity, both only while the stimulus expands (Ache et al. 2019), times one '
                 'calibrated scale.'),
        'escape_threshold': decoder['alert_reference_threshold'],
        'escape_decoder': dict(decoder),
        'parameter_basis': {
            'alert_reference_threshold': {
                'value': decoder['alert_reference_threshold'],
                'basis': ('carried over unchanged from the M1.7.2 record; it scales the unchanged '
                          'alert, turn and strength logic and fires nothing'),
                'source_record': SOURCE_RECORD, 'source_sha256': content_sha256(SOURCE_RECORD)},
            'doublet_window_ms': {
                'value': decoder['doublet_window_ms'], 'class': 'C',
                'basis': ('M3.3 research: at rest no two DNp01 spikes of one side are closer than 6 '
                          'ticks, so a same-side doublet within 40 ms only occurs under strong '
                          'feedforward drive; chosen on exploration seeds 700001-700024 and validated '
                          'on unused seeds (' + RESEARCH_NOTE + ')')},
            'not_biological_constants': True},
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
                            '(tools/m3_2_ache_targets.py) on seeds 600001-600024 with the M3.3 '
                            'decoder, not against behaviour'),
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
            'kind': 'decoder replaced and encoder changed; alert reference carried over',
            'source_record': SOURCE_RECORD, 'source_sha256': content_sha256(SOURCE_RECORD),
            'baseline_commit': commit, 'changed_config_paths': changed},
        'neurons': source['neurons'], 'connections': source['connections'],
        'input_populations': source['input_populations'], 'versions': source['versions'],
    }


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
