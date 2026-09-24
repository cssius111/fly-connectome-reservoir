"""Write the M1.8-N4B1C lateral dual-path decoder provenance record.

This is decoder provenance, NOT a scalar-threshold calibration, and runs no new
measurement. It states what each parameter of the `lateral_dual_path_v1` criterion rests
on and cites the research that selected it:

* sustained_threshold 1.45: inherited unchanged from the accepted scalar single-sample
  measurement, through the existing ROOM transfer chain;
* summed_fast_threshold 2.10, sustained window 5 / required 3 / current qualifies: the
  M1.8-N2b summed path, unchanged (Class C);
* lateral_same_side_window_ms 60, lateral_required_spikes 2: the M1.8-N4B1 frozen Rule A,
  combined with the N2b path in M1.8-N4B1C and validated on a new, pre-registered N0
  holdout (Class C, simulator-derived).

The historical scalar records, the strict N2 record and the rejected N2b record are cited
by SHA256 and are not modified.

    python tools/n4b1c_decoder_record.py
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

from game.session import (LATERAL_DECODER, calibration_provenance, escape_decoder_spec,  # noqa: E402
                          lateral_window_samples, load_config)
from tools.n2_decoder_record import EVIDENCE as N2_EVIDENCE, changed_paths, sha256  # noqa: E402

TEXT_SUFFIXES = {'.md', '.py', '.json', '.txt'}


def content_sha256(path):
    """SHA256 of a file's committed content: text files are hashed with CRLF normalised to
    LF, so the value does not depend on the checkout's line-ending conversion (Windows
    core.autocrlf). Binary files are hashed as stored."""
    data = (ROOT / path).read_bytes()
    if Path(path).suffix in TEXT_SUFFIXES:
        data = data.replace(b'\r\n', b'\n')
    return hashlib.sha256(data).hexdigest()

CONFIG = ROOT / 'game_room_config.json'
SOURCE_RECORD = 'results/game/calibration_room_m1_8_b2b_ii.json'
ORIGINAL_MEASUREMENT = 'results/game/calibration_room_m1_7_1.json'
STRICT_N2_RECORD = 'results/game/calibration_room_m1_8_n2.json'
N2B_RECORD = 'results/game/calibration_room_m1_8_n2b.json'
BASELINE_COMMIT = '76806f0'
N2B_ARCHIVE_COMMIT = '2c306174d7bdb4e74b6c5517519ae695bd90cf44'
RESEARCH_COMMIT_N2_N4B1 = '6fb0cc5'
RESEARCH_COMMIT_N4B1C = '07f4670'
RESEARCH_CANDIDATE = 'A OR N2b'
EVIDENCE = {
    'n0_extended_no_loom': N2_EVIDENCE['n0_extended_no_loom'],
    'n1_loom_robustness': N2_EVIDENCE['n1_loom_robustness'],
    'n3_neural_evidence_integration': {
        'commit': RESEARCH_COMMIT_N2_N4B1,
        'files': ['game/M1_8_N3_NEURAL_EVIDENCE_INTEGRATION.md', 'tools/n3_evidence_integration.py',
                  'artifacts/m1_8_n3/evidence_integration.json']},
    'n4a_sensory_descending_diagnosis': {
        'commit': RESEARCH_COMMIT_N2_N4B1,
        'files': ['game/M1_8_N4_SENSORY_DESCENDING_DIAGNOSIS.md', 'tools/n4_resimulate.py',
                  'tools/n4_diagnosis.py', 'artifacts/m1_8_n4/diagnosis.json']},
    'n4b1_lateralized_dnp01': {
        'commit': RESEARCH_COMMIT_N2_N4B1,
        'files': ['game/M1_8_N4B1_LATERALIZED_DNP01.md', 'tools/n4b1_lateral.py',
                  'tools/n4b1_analysis.py', 'artifacts/m1_8_n4b1/frozen_candidates.json',
                  'artifacts/m1_8_n4b1/mechanism.json', 'artifacts/m1_8_n4b1/evaluation.json',
                  'artifacts/m1_8_n4b1/closed_loop.json']},
    'n4b1c_combined_dnp01': {
        'commit': RESEARCH_COMMIT_N4B1C,
        'files': ['game/M1_8_N4B1C_COMBINED_DNP01.md', 'tools/n4b1c_candidates.py',
                  'tools/n4b1c_combined.py', 'artifacts/m1_8_n4b1c/frozen_candidates.json',
                  'artifacts/m1_8_n4b1c/evaluation.json', 'artifacts/m1_8_n4b1c/closed_loop.json']},
}


def build_record():
    config = load_config(CONFIG)
    decoder = escape_decoder_spec(config)
    if decoder is None or decoder['kind'] != LATERAL_DECODER:
        raise SystemExit('game_room_config.json must configure a %s decoder' % LATERAL_DECODER)
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

    research = load_config(ROOT / 'artifacts/m1_8_n4b1c/evaluation.json')
    frozen = research['frozen']
    cand = research['candidates'][RESEARCH_CANDIDATE]
    dt = config['sim']['tick_seconds']
    lateral = lateral_window_samples(decoder, config)
    record = {
        'record_kind': 'lateral-dual-path-decoder-provenance-v1',
        'not_a_scalar_calibration': True,
        'rule': ('M1.8-N4B1C combined DNp01 decoder. Escape when EITHER path qualifies outside '
                 'the shared refractory period. LATERAL: the same DNp01 side produces two '
                 'inferred spikes at most lateral_same_side_window_ms apart. Summed N2b path: '
                 'FAST when left + right >= summed_fast_threshold; SUSTAINED when the current '
                 'summed sample is >= sustained_threshold AND at least sustained_required_samples '
                 'of the most recent sustained_window_samples summed samples are >= '
                 'sustained_threshold. No new measurement was made; see parameter_basis.'),
        'escape_threshold': decoder['sustained_threshold'],
        'escape_decoder': {
            **decoder,
            'lateral_window_samples': lateral,
            'spike_inference_rule': ('per side: spike_t = trace_t - decay * trace_{t-1} >= 0.5, '
                                     'with decay = float32(exp(-tick_seconds / '
                                     'trace_tau_seconds)); no spike is inferred on the first '
                                     'sample after reset'),
            'lateral_rule': ('left and right tracked independently; the qualifying spike must be '
                             'on the current sample; the previous spike of the SAME side must be '
                             'at most lateral_window_samples samples earlier; a left spike '
                             'followed by a right spike never qualifies'),
            'window_rule': ('one summed qualification flag per sample, refractory samples '
                            'included; cleared when an escape fires and on reset'),
            'escape_clears': ['summed window and streak', 'lateral last-spike memory, both sides'],
            'reset_clears': ['summed window and streak', 'lateral spike history and previous '
                             'trace values', 'trigger channel and paths'],
            'channel_precedence': ['LATERAL', 'FAST', 'SUSTAINED'],
            'motor_semantics': ('unchanged: strength, side, steering, saccade, forward bias and '
                                'refractory do not depend on the path that fired'),
            'parameter_class': 'C'},
        'parameter_basis': {
            'sustained_threshold': {
                'value': decoder['sustained_threshold'],
                'basis': ('inherited unchanged from the scalar single-sample calibration, used '
                          'here only as the summed qualification level'),
                'source_record': SOURCE_RECORD, 'source_sha256': sha256(SOURCE_RECORD),
                'original_measurement': ORIGINAL_MEASUREMENT,
                'original_measurement_sha256': sha256(ORIGINAL_MEASUREMENT)},
            'summed_path': {
                'summed_fast_threshold': decoder['summed_fast_threshold'],
                'sustained_window_samples': decoder['sustained_window_samples'],
                'sustained_required_samples': decoder['sustained_required_samples'],
                'require_current_qualifying': True, 'class': 'C',
                'basis': ('the M1.8-N2b summed criterion, unchanged; N2b itself failed its second '
                          'human re-acceptance and is retained here only as the path that '
                          'keeps alternating-side hover evidence')},
            'lateral_path': {
                'lateral_same_side_window_ms': decoder['lateral_same_side_window_ms'],
                'lateral_required_spikes': decoder['lateral_required_spikes'], 'class': 'C',
                'basis': ('M1.8-N4A: spontaneous DNp01 spikes are noise driven and independent '
                          'per side, and the summed trace turns bilateral coincidences into '
                          'apparent multi-spike evidence; M1.8-N4B1: a same-side 60 ms rule '
                          '(frozen Rule A) restores legacy-level committed-strike timing with 0 '
                          'false events on a fresh 280-minute N0; M1.8-N4B1C: combined with the '
                          'N2b path it restores alternating-side hover coverage and passes a new '
                          'pre-registered 280-minute N0 holdout. The window is a simulator '
                          'property (LIF reset to 0 plus independent noise), not a biological '
                          'refractory constant.')},
            'not_biological_constants': True},
        'evidence': {
            name: {'commit': spec['commit'], 'files': {path: content_sha256(path) for path in spec['files']}}
            for name, spec in EVIDENCE.items()},
        'hash_convention': ('evidence and preserved_records: SHA256 of the committed content '
                            '(text files with CRLF normalised to LF); measurement_reuse and '
                            'parameter_basis source hashes: raw working-file bytes, as in the '
                            'earlier record chain'),
        'evidence_summary_research': {
            'candidate': RESEARCH_CANDIDATE,
            'frozen_candidates_sha256': research['frozen_sha256'],
            'candidates_module_sha256': frozen['candidates_module_sha256'],
            'n0_new_holdout': {k: cand['n0_holdout'][k] for k in
                               ('minutes', 'false_events', 'upper95_per_minute', 'paths')},
            'n0_all_minutes': cand['n0_all'],
            'n1_per_class': {c: {k: s[k] for k in ('fired', 'trials', 'median_s', 'p95_s')}
                             for c, s in cand['n1'].items()},
            'human_hover_escapes_met': {s: [cand['human'][s]['hover']['fired_no_later'],
                                            cand['human'][s]['hover']['n']]
                                        for s in cand['human']},
            'note': ('research-subclass results on the archived N2b runtime; the exact runtime '
                     'replay is produced separately by tools/n4b1c_runtime_validation.py')},
        'preserved_records': {
            'strict_n2': {'record': STRICT_N2_RECORD, 'sha256': content_sha256(STRICT_N2_RECORD),
                          'decoder': 'dual_path_v1, FAST 2.20, 3 consecutive samples',
                          'status': 'superseded; human re-acceptance failed', 'modified': False},
            'n2b': {'record': N2B_RECORD, 'sha256': content_sha256(N2B_RECORD),
                    'decoder': 'dual_path_window_v1, FAST 2.10, current-H + 3 of 5',
                    'status': 'rejected at the second human re-acceptance',
                    'runtime_archive': 'archive/m1-8-n2b-rejected @ ' + N2B_ARCHIVE_COMMIT,
                    'modified': False}},
        'tick_seconds': dt,
        'config_sha256': hashlib.sha256(CONFIG.read_bytes()).hexdigest(),
        'provenance': calibration_provenance(config),
        'measurement_conditions': copy.deepcopy(source['measurement_conditions']),
        'measurement_reuse': {
            'kind': 'lateral dual-path decoder transfer; not a new measurement',
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
    for preserved in (STRICT_N2_RECORD, N2B_RECORD, SOURCE_RECORD):
        if rel == preserved:
            raise SystemExit('refusing to overwrite a preserved record: ' + rel)
    if path.exists() and path.read_text(encoding='utf-8') != text:
        print('replacing', rel)
    path.write_bytes(text.encode('utf-8'))
    print('written', rel, hashlib.sha256(path.read_bytes()).hexdigest())
    print('changed config paths:', record['measurement_reuse']['changed_config_paths'])


if __name__ == '__main__':
    main()
