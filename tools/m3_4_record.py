"""Write the M3.4 retinotopic-drive record (results/game/calibration_room_m3_4.json).

M3.4 (game/M3_4_RETINOTOPIC_DRIVE_DESIGN.md) gives the ROOM configuration the retinotopic_v1
encoder and the M3.3 same_side_doublet_v1 decoder. The alert reference threshold (1.45) is
carried over from the M1.7.2 record, whose N4B1C decoder M3.3's decoder replaces; the record cites
that record by content SHA256 and does not modify it.

The tool refuses to write unless:
- the configuration differs from the v27 ROOM configuration (commit 7483e51) only in
  config_version, policy._comment, policy.calibration_paths, policy.escape_decoder and the
  encoder's feature-model keys;
- the configured decoder is the preregistered same_side_doublet_v1 block;
- the encoder block holds the preregistered constants, the scale the preregistered calibration
  chose (artifacts/m3_4_run/report.json, written by tools/m3_4_retinotopic.py report), and the
  digest of the local data/receptive_fields_v1.npz.

    python tools/m3_4_record.py

M3.4 failed checks V2 and V8a and the ROOM configuration was restored to v27. The record describes
the v30 candidate at commit 10e12f6; run the tool with that configuration checked out.
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

from game.perception import ACHE2019, FEATURE_MODEL_RETINOTOPIC, encoder_feature_model  # noqa: E402
from game.session import (DOUBLET_DECODER, calibration_provenance, escape_decoder_spec,  # noqa: E402
                          load_config)
from tools.b2b_iii_record import content_sha256  # noqa: E402
import tools.build_receptive_fields as B  # noqa: E402
import tools.m3_4_retinotopic as H  # noqa: E402
from tools.n2_decoder_record import changed_paths  # noqa: E402

CONFIG = ROOT / 'game_room_config.json'
RECORD = 'results/game/calibration_room_m3_4.json'
SOURCE_RECORD = 'results/game/calibration_room_m1_7_2.json'
BASELINE_COMMIT = '7483e512d83ed07a74f5b5ca8b4e89f9ded9122b'   # main after M3.3, ROOM config_version 27
DESIGN_NOTE = 'game/M3_4_RETINOTOPIC_DRIVE_DESIGN.md'
RESEARCH_NOTE = 'game/M3_4_RETINOTOPIC_DRIVE_RESEARCH.md'
CALIBRATION_REPORT = ROOT / 'artifacts/m3_4_run/report.json'
PREREGISTERED_DECODER = {'kind': DOUBLET_DECODER, 'alert_reference_threshold': 1.45,
                         'doublet_window_ms': 40.0, 'required_spikes': 2}
PREREGISTERED_CONSTANTS = {'acceptance_fwhm_deg': H.ACCEPTANCE_FWHM_DEG,
                           'lplc2_min_edge_speed_deg_s': H.LPLC2_MIN_EDGE_SPEED_DEG_S,
                           'fields_file': H.FIELDS_FILE}
ALLOWED_PREFIXES = ('policy.escape_decoder.',)
ALLOWED_CHANGES = {'config_version', 'policy._comment', 'policy.calibration_paths',
                   'encoder.feature_model', 'encoder._feature_model_comment', 'encoder.retinotopic'}


def baseline_config():
    commit = subprocess.check_output(['git', 'rev-parse', BASELINE_COMMIT], cwd=ROOT, text=True).strip()
    return commit, json.loads(subprocess.check_output(
        ['git', 'show', commit + ':game_room_config.json'], cwd=ROOT, text=True))


def calibrated_scale():
    if not CALIBRATION_REPORT.exists():
        raise SystemExit('run python tools/m3_4_retinotopic.py report after the calibration first')
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
        raise SystemExit('configuration differs from the v27 ROOM configuration outside the M3.4 '
                         'encoder and decoder keys: ' + ', '.join(unexpected))
    if config['config_version'] != 30:
        raise SystemExit('config_version must be 30')
    if encoder_feature_model(config) != FEATURE_MODEL_RETINOTOPIC:
        raise SystemExit('game_room_config.json must set encoder.feature_model = ' + FEATURE_MODEL_RETINOTOPIC)
    decoder = escape_decoder_spec(config)
    if decoder != PREREGISTERED_DECODER:
        raise SystemExit('the configured decoder is not the preregistered same_side_doublet_v1 block')
    if config['policy']['calibration_paths'][1] != RECORD:
        raise SystemExit('policy.calibration_paths must name ' + RECORD)
    block = config['encoder']['retinotopic']
    for key, value in PREREGISTERED_CONSTANTS.items():
        if block[key] != value:
            raise SystemExit('encoder.retinotopic.%s is %r, not the preregistered %r' % (key, block[key], value))
    digest = H.table_digest()
    if block['fields_sha256'] != digest:
        raise SystemExit('encoder.retinotopic.fields_sha256 is not the digest of the local ' + H.FIELDS_FILE)
    calibration = calibrated_scale()
    if H.recorded_fields(H.OUT / 'calibration')['fields_sha256'] != block['fields_sha256']:
        raise SystemExit('the calibration was produced with a different receptive-field table')
    scale = block['scale_volts_per_mv']
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
        'record_kind': 'm3-4-retinotopic-drive-record-v1',
        'stage': 'M3.4',
        'not_a_scalar_calibration': True,
        'decoder_unchanged': False,
        'decoder_replaced': True,
        'encoder_changed': True,
        'retina_changed': True,
        'geometry_changed': False,
        'rule': ('Each LPLC2 and LC4 cell is driven by min(cap, scale * F * c), where F is its type\'s '
                 'Ache et al. 2019 term in mV and c the fraction of its MaleCNS receptive field '
                 'inside the swatter\'s disk, seen through Gaussian column acceptance functions; '
                 'LPLC2 only while the image edge expands at >= lplc2_min_edge_speed_deg_s. '
                 'Escape on a same-side DNp01 doublet within 40 ms (same_side_doublet_v1).'),
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
                'basis': 'the M3.3 decoder, unchanged (game/M3_3_ESCAPE_DECISION_DESIGN.md)'},
            'acceptance_fwhm_deg': {
                'value': block['acceptance_fwhm_deg'], 'class': 'A',
                'basis': ('light-adapted R1-R6 acceptance angle, 7.70 +- 1.27 deg (Juusola et al. '
                          '2017, eLife 6:e26117)')},
            'lplc2_min_edge_speed_deg_s': {
                'value': block['lplc2_min_edge_speed_deg_s'], 'class': 'B',
                'basis': ('edge speed of the standard constant-velocity looming stimulus of '
                          'Klapoetke et al. 2017, to which LPLC2 responds strongly; no LPLC2 '
                          'response is assumed below it')},
            'not_biological_constants': ['scale_volts_per_mv', 'doublet_window_ms']},
        'geometry': copy.deepcopy(source['geometry']),
        'kinematics': copy.deepcopy(config.get('kinematics', {})),
        'ecology_threat_input': copy.deepcopy(config.get('ecology_threat_input')),
        'encoder': {
            'feature_model': FEATURE_MODEL_RETINOTOPIC,
            'previous_feature_model': 'legacy_v0',
            'published_constants': dict(ACHE2019),
            'source': 'Ache et al. 2019, Curr Biol 29:1073-1081, doi:10.1016/j.cub.2019.01.079',
            'block': copy.deepcopy(block),
            'scale_basis': ('the only calibrated constant; chosen by the preregistered grid search '
                            'against the peak times of the paper\'s own GF model '
                            '(tools/m3_2_ache_targets.py) on seeds 600001-600024 with the disk at '
                            'azimuth 50 deg, elevation 11 deg, not against behaviour'),
            'calibration_at_chosen_scale': chosen,
            'receptive_fields': {
                'file': H.FIELDS_FILE, 'content_digest': digest,
                'digest_rule': 'game.perception.fields_digest (key, dtype, shape and bytes of every array)',
                'builder': 'tools/build_receptive_fields.py', 'synapses': B.SYNAPSES,
                'eye_map': B.EYE_MAP, 'committed': False},
            'scope': 'ROOM configuration only; GAME and LAB configurations keep legacy_v0'},
        'retina': {'added_field': 'elevation', 'default': 0.0,
                   'rule': 'atan2(swatter.height, horizontal distance), radians'},
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
