"""Write the M1.8-N2b gap-tolerant dual-path decoder provenance record.

This is decoder provenance, NOT a scalar-threshold calibration, and runs no new
measurement. It states what each parameter of the `dual_path_window_v1` criterion rests on:

* sustained_threshold 1.45: inherited unchanged from the accepted scalar single-sample
  measurement, through the existing ROOM transfer chain;
* fast_threshold 2.10: Class C, selected in the M1.8-N2 FAST-threshold review;
* sustained_window_samples 5, sustained_required_samples 3, require_current_qualifying
  true: Class C, selected in the M1.8-N2 temporal-rule review from the N0 no-loom and N1
  loom-robustness evidence and one human-session counterfactual.

The superseded strict N2 record is cited by SHA256 and is not modified. Historical
calibration records are read, never written.

    python tools/n2b_decoder_record.py
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

from game.session import (WINDOW_DECODER, calibration_provenance, escape_decoder_spec,  # noqa: E402
                          load_config)
from tools.n2_decoder_record import EVIDENCE as N2_EVIDENCE, changed_paths, sha256  # noqa: E402

CONFIG = ROOT / 'game_room_config.json'
SOURCE_RECORD = 'results/game/calibration_room_m1_8_b2b_ii.json'
ORIGINAL_MEASUREMENT = 'results/game/calibration_room_m1_7_1.json'
SUPERSEDED_RECORD = 'results/game/calibration_room_m1_8_n2.json'
BASELINE_COMMIT = '76806f0'
RESEARCH_CRITERION = 'C* 3-of-5 + current qualifies, FAST 2.10'
EVIDENCE = {
    **N2_EVIDENCE,
    'n2_fast_threshold_review': {
        'commit': None,
        'files': ['game/M1_8_N2_FAST_THRESHOLD_REVIEW.md', 'tools/n2_fast_threshold_study.py',
                  'artifacts/m1_8_n2/fast_threshold_study.json']},
    'n2_temporal_rule_review': {
        'commit': None,
        'files': ['game/M1_8_N2_TEMPORAL_REVIEW.md', 'tools/n2_temporal_study.py',
                  'artifacts/m1_8_n2/temporal_study.json']},
}


def build_record():
    config = load_config(CONFIG)
    decoder = escape_decoder_spec(config)
    if decoder is None or decoder['kind'] != WINDOW_DECODER:
        raise SystemExit('game_room_config.json must configure a %s decoder' % WINDOW_DECODER)
    source = load_config(ROOT / SOURCE_RECORD)
    baseline = json.loads(subprocess.check_output(
        ['git', 'show', BASELINE_COMMIT + ':game_room_config.json'], cwd=ROOT, text=True))
    if source['provenance'] != calibration_provenance(baseline):
        raise SystemExit('source record does not match the N1 baseline ROOM configuration')
    if source['escape_threshold'] != decoder['sustained_threshold']:
        raise SystemExit('sustained_threshold must equal the inherited escape_threshold')
    changed = changed_paths(baseline, config)
    allowed = {'config_version', 'policy._comment', 'policy.calibration_paths'}
    unexpected = [p for p in changed if p not in allowed and not p.startswith('policy.escape_decoder')]
    if unexpected:
        raise SystemExit('configuration differs outside the decoder: ' + ', '.join(unexpected))

    temporal = load_config(ROOT / 'artifacts/m1_8_n2/temporal_study.json')
    research = temporal['candidates'][RESEARCH_CRITERION]
    human = temporal['human']['summary'][RESEARCH_CRITERION]
    n = decoder['sustained_window_samples']
    k = decoder['sustained_required_samples']
    dt = config['sim']['tick_seconds']
    record = {
        'record_kind': 'gap-tolerant-dual-path-decoder-provenance-v1',
        'not_a_scalar_calibration': True,
        'rule': ('M1.8-N2b gap-tolerant dual-path DNp01 decoder. FAST: one sample >= '
                 'fast_threshold. SUSTAINED: the current sample is >= sustained_threshold AND '
                 'at least sustained_required_samples of the most recent '
                 'sustained_window_samples samples, including the current one, are >= '
                 'sustained_threshold. No new measurement was made; see parameter_basis.'),
        'escape_threshold': decoder['sustained_threshold'],
        'escape_decoder': {
            **decoder,
            'window_rule': ('one qualification flag per sample, refractory samples included; '
                            'the window holds the most recent sustained_window_samples flags '
                            'including the current sample; cleared when an escape fires and '
                            'on reset'),
            'current_sample_rule': ('a current sample below sustained_threshold never fires '
                                    'SUSTAINED'),
            'minimum_structural_delay_seconds': round((k - 1) * dt, 9),
            'maximum_evidence_span_seconds': round((n - 1) * dt, 9),
            'tie_rule': 'FAST is reported when both paths are satisfied',
            'parameter_class': 'C'},
        'parameter_basis': {
            'sustained_threshold': {
                'value': decoder['sustained_threshold'],
                'basis': ('inherited unchanged: the scalar single-sample calibration value '
                          '(smallest grid value with zero false triggers over 2520 no-loom '
                          'ticks); used here only as the qualification level'),
                'source_record': SOURCE_RECORD, 'source_sha256': sha256(SOURCE_RECORD),
                'original_measurement': ORIGINAL_MEASUREMENT,
                'original_measurement_sha256': sha256(ORIGINAL_MEASUREMENT)},
            'fast_threshold': {
                'value': decoder['fast_threshold'], 'class': 'C',
                'basis': ('M1.8-N2 FAST-threshold review: lowest round value that passes N0, '
                          'catches the 2.1197 early-peak level of committed looms, and does '
                          'not fire on the recorded far perched human approach (peak 2.0557)')},
            'sustained_window': {
                'window_samples': n, 'required_samples': k,
                'require_current_qualifying': True, 'class': 'C',
                'basis': ('M1.8-N2 temporal-rule review: no N0 no-loom window of 3-5 samples '
                          'ever held more than 2 qualifying samples in 70 minutes, while '
                          'committed looms reach 3 qualifying samples within 5; the current-'
                          'qualifies condition excludes firing on a sub-threshold sample at '
                          'refractory expiry from evidence up to 80 ms old')},
            'not_biological_constants': True},
        'evidence': {
            name: {'commit': spec['commit'],
                   'files': {path: sha256(path) for path in spec['files']}}
            for name, spec in EVIDENCE.items()},
        'evidence_summary_research': {
            'criterion': RESEARCH_CRITERION,
            'n0_no_loom_minutes': research['n0']['minutes'],
            'n0_events': research['n0']['policy_firings'],
            'n0_upper95_one_sided_per_minute': research['n0']['upper95_one_sided_per_minute'],
            'n1_per_class': {c: {'fired': s['fired_in_window'], 'trials': s['trials'],
                                 'fast': s['fast_count'], 'sustained': s['sustained_count']}
                             for c, s in research['n1'].items()},
            'human_session_counterfactual': {key: human[key] for key in
                                             ('fired', 'strikes', 'median_s', 'mean_s', 'p95_s')},
            'note': ('research-subclass results; the exact runtime replay is produced '
                     'separately by tools/n2b_validation.py')},
        'supersedes': {'record': SUPERSEDED_RECORD, 'sha256': sha256(SUPERSEDED_RECORD),
                       'decoder': 'dual_path_v1, FAST 2.20, 3 consecutive samples',
                       'reason': 'human re-acceptance failed on escape latency',
                       'modified': False},
        'tick_seconds': dt,
        'config_sha256': hashlib.sha256(CONFIG.read_bytes()).hexdigest(),
        'provenance': calibration_provenance(config),
        'measurement_conditions': copy.deepcopy(source['measurement_conditions']),
        'measurement_reuse': {
            'kind': 'gap-tolerant dual-path decoder transfer; not a new measurement',
            'source_record': SOURCE_RECORD, 'source_sha256': sha256(SOURCE_RECORD),
            'source_provenance': source['provenance'],
            'original_measurement': ORIGINAL_MEASUREMENT,
            'original_measurement_sha256': sha256(ORIGINAL_MEASUREMENT),
            'baseline_commit': BASELINE_COMMIT,
            'reason': ('Only the escape criterion changes. Retina, encoder, brain, ecology, '
                       'lifecycle, swatter and kinematics configuration are identical to the '
                       'N1 baseline, so the recorded DNp01 distributions still apply.'),
            'changed_config_paths': changed},
        'neurons': source['neurons'], 'connections': source['connections'],
        'input_populations': source['input_populations'], 'versions': source['versions'],
    }
    return config, record


def main():
    config, record = build_record()
    text = json.dumps(record, indent=2) + '\n'
    rel = config['policy']['calibration_paths'][1]
    path = ROOT / rel
    if path.exists() and path.read_text(encoding='utf-8') != text:
        print('replacing', rel)
    path.write_bytes(text.encode('utf-8'))
    print('written', rel, hashlib.sha256(path.read_bytes()).hexdigest())
    print('changed config paths:', record['measurement_reuse']['changed_config_paths'])


if __name__ == '__main__':
    main()
