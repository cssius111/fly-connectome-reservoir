"""Write the M1.8-N2 dual-path decoder provenance record.

This is NOT a scalar-threshold calibration and runs no new measurement. The legacy
`tools/calibrate_escape.py` selects one threshold under single-sample semantics; the N2
decoder has different semantics, so this record states explicitly what each parameter
rests on:

* sustained_threshold 1.45: inherited unchanged from the accepted scalar single-sample
  measurement, through the existing ROOM transfer chain;
* fast_threshold 2.20 and persistence_samples 3: Class C decoder parameters selected in
  M1.8-N1 from the N0 extended no-loom evidence and the N1 loom-robustness evidence;
* provenance: the N2 ROOM configuration hash, so the record loads only for that exact
  configuration, and `game.session.resolve_escape_threshold` additionally requires the
  identical `escape_decoder` block.

Evidence files are identified by SHA256. Historical calibration records are read, never
written.

    python tools/n2_decoder_record.py
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from game.session import calibration_provenance, escape_decoder_spec, load_config  # noqa: E402

CONFIG = ROOT / 'game_room_config.json'
SOURCE_RECORD = 'results/game/calibration_room_m1_8_b2b_ii.json'
ORIGINAL_MEASUREMENT = 'results/game/calibration_room_m1_7_1.json'
BASELINE_COMMIT = '76806f0'
N0_COMMIT = '3d41113'
CRITERION = 'fast 2.20 OR 1.45 x N3'
EVIDENCE = {
    'n0_extended_no_loom': {
        'commit': N0_COMMIT,
        'files': ['game/M1_8_NO_LOOM_CALIBRATION.md', 'tools/no_loom_calibration_study.py',
                  'tools/no_loom_continuous_arm.py', 'tools/no_loom_criterion_analysis.py',
                  'tools/no_loom_statistics.py', 'tools/no_loom_tail_model.py',
                  'artifacts/m1_8_no_loom_calibration/raw.npz',
                  'artifacts/m1_8_no_loom_calibration/study.json',
                  'artifacts/m1_8_no_loom_calibration/continuous.npz',
                  'artifacts/m1_8_no_loom_calibration/statistics.json']},
    'n1_loom_robustness': {
        'commit': BASELINE_COMMIT,
        'files': ['game/M1_8_LOOM_ROBUSTNESS.md', 'tools/loom_robustness_study.py',
                  'tools/loom_robustness_analysis.py',
                  'artifacts/m1_8_loom_robustness/trials.npz',
                  'artifacts/m1_8_loom_robustness/trials_meta.json',
                  'artifacts/m1_8_loom_robustness/analysis.json',
                  'artifacts/m1_8_loom_robustness/hybrid_no_loom.json']},
}


def sha256(path):
    return hashlib.sha256((ROOT / path).read_bytes()).hexdigest()


def changed_paths(before, after, prefix=''):
    """Dotted paths whose values differ between two JSON objects."""
    out = []
    for key in sorted(set(before) | set(after)):
        path = prefix + key
        a, b = before.get(key, None), after.get(key, None)
        if isinstance(a, dict) and isinstance(b, dict):
            out += changed_paths(a, b, path + '.')
        elif a != b or (key in before) != (key in after):
            out.append(path)
    return out


def build_record():
    config = load_config(CONFIG)
    decoder = escape_decoder_spec(config)
    if decoder is None:
        raise SystemExit('game_room_config.json has no policy.escape_decoder block')
    source = load_config(ROOT / SOURCE_RECORD)
    baseline = json.loads(subprocess.check_output(
        ['git', 'show', BASELINE_COMMIT + ':game_room_config.json'], cwd=ROOT, text=True))
    if source['provenance'] != calibration_provenance(baseline):
        raise SystemExit('source record does not match the N1 baseline ROOM configuration')
    if source['escape_threshold'] != decoder['sustained_threshold']:
        raise SystemExit('sustained_threshold must equal the inherited escape_threshold')
    # Only the decoder criterion may differ from the baseline ROOM configuration.
    changed = changed_paths(baseline, config)
    allowed = {'config_version', 'policy._comment', 'policy.calibration_paths'}
    unexpected = [p for p in changed if p not in allowed and not p.startswith('policy.escape_decoder')]
    if unexpected:
        raise SystemExit('configuration differs outside the decoder: ' + ', '.join(unexpected))

    analysis = load_config(ROOT / 'artifacts/m1_8_loom_robustness/analysis.json')
    hybrid = load_config(ROOT / 'artifacts/m1_8_loom_robustness/hybrid_no_loom.json')
    study = load_config(ROOT / 'artifacts/m1_8_no_loom_calibration/study.json')
    n1_rows = {r['class']: {'fired': r['fired'], 'trials': r['trials'],
                            'firing_rate': r['firing_rate'],
                            'has_positive_label': r['has_positive_label'],
                            'median_latency_from_click_s': r['median_latency_from_click_s']}
               for r in analysis['per_class_firing'] if r['criterion'] == CRITERION}
    n0_row = next(r for r in hybrid['rows'] if r['criterion'] == CRITERION)

    record = {
        'record_kind': 'dual-path-decoder-provenance-v1',
        'not_a_scalar_calibration': True,
        'rule': ('M1.8-N2 dual-path DNp01 decoder. FAST: one sample >= fast_threshold. '
                 'SUSTAINED: persistence_samples consecutive samples >= sustained_threshold, '
                 'counting the first qualifying sample. No new measurement was made; see '
                 'parameter_basis.'),
        'escape_threshold': decoder['sustained_threshold'],
        'escape_decoder': {**decoder,
                           'persistence_definition': (
                               'N consecutive samples at or above sustained_threshold '
                               'INCLUDING the first qualifying sample; satisfied on sample '
                               't + (N - 1) * tick_seconds'),
                           'structural_persistence_delay_seconds': round(
                               (decoder['persistence_samples'] - 1) * config['sim']['tick_seconds'], 9),
                           'streak_rule': ('counted on every sample including refractory samples; '
                                           'cleared by any sample below sustained_threshold and '
                                           'when an escape fires'),
                           'tie_rule': 'FAST is reported when both paths are satisfied',
                           'parameter_class': 'C'},
        'parameter_basis': {
            'sustained_threshold': {
                'value': decoder['sustained_threshold'],
                'basis': ('inherited unchanged: the scalar single-sample calibration value, '
                          'selected as the smallest grid value with zero false triggers over '
                          '2520 no-loom ticks; N0 showed that this exposure was too short to '
                          'bound the single-sample false-trigger rate, which is why the N2 '
                          'criterion adds persistence rather than relying on it alone'),
                'source_record': SOURCE_RECORD,
                'source_sha256': sha256(SOURCE_RECORD),
                'original_measurement': ORIGINAL_MEASUREMENT,
                'original_measurement_sha256': sha256(ORIGINAL_MEASUREMENT)},
            'fast_threshold': {
                'value': decoder['fast_threshold'], 'class': 'C',
                'basis': ('selected in M1.8-N1 above the N0 no-loom worst case of %.4f over '
                          '70 simulated minutes and below the weakest committed-strike peak '
                          'of %.3f in N0' % (study['no_loom']['max'], study['loom']['peak_min']))},
            'persistence_samples': {
                'value': decoder['persistence_samples'], 'class': 'C',
                'basis': ('selected in M1.8-N1: the N0 spontaneous worst case stays above '
                          '1.45 for at most 2 consecutive samples, committed strikes for a '
                          'median of 14-17')},
            'not_biological_constants': True},
        'evidence': {
            name: {'commit': spec['commit'],
                   'files': {path: sha256(path) for path in spec['files']}}
            for name, spec in EVIDENCE.items()},
        'evidence_summary_offline': {
            'criterion': CRITERION,
            'n0_no_loom_minutes': hybrid['minutes'],
            'n0_no_loom_events': n0_row['no_loom_events'],
            'n0_upper95_two_sided_per_minute': n0_row['upper95_per_minute'],
            'n1_per_class': n1_rows,
            'note': ('offline criterion evaluation from M1.8-N1; the exact runtime replay is '
                     'produced separately by tools/n2_decoder_replay.py')},
        'tick_seconds': config['sim']['tick_seconds'],
        'config_sha256': hashlib.sha256(CONFIG.read_bytes()).hexdigest(),
        'provenance': calibration_provenance(config),
        'measurement_conditions': copy.deepcopy(source['measurement_conditions']),
        'measurement_reuse': {
            'kind': 'dual-path decoder transfer; not a new measurement',
            'source_record': SOURCE_RECORD,
            'source_sha256': sha256(SOURCE_RECORD),
            'source_provenance': source['provenance'],
            'original_measurement': ORIGINAL_MEASUREMENT,
            'original_measurement_sha256': sha256(ORIGINAL_MEASUREMENT),
            'baseline_commit': BASELINE_COMMIT,
            'reason': ('Only the escape criterion changes. Retina, encoder, brain, ecology, '
                       'lifecycle, swatter and kinematics configuration are identical to the '
                       'N1 baseline, so the recorded DNp01 distributions still apply.'),
            'changed_config_paths': changed},
        'neurons': source['neurons'],
        'connections': source['connections'],
        'input_populations': source['input_populations'],
        'versions': source['versions'],
    }
    return config, record


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.parse_args()
    config, record = build_record()
    text = json.dumps(record, indent=2) + '\n'
    # Like the earlier M1.8 transfer records, only the committed summary path is
    # written; the git-ignored first path stays absent, so the committed record is the
    # one every checkout resolves.
    rel = config['policy']['calibration_paths'][1]
    path = ROOT / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(text.encode('utf-8'))
    print('written', rel, hashlib.sha256(path.read_bytes()).hexdigest())
    print('changed config paths:', record['measurement_reuse']['changed_config_paths'])


if __name__ == '__main__':
    main()
