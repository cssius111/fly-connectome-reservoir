"""Write the M1.8-N4B5R geometry runtime-candidate provenance record.

This is NOT a decoder recalibration and runs no new measurement. The accepted M1.8-N4B1C
decoder (`lateral_dual_path_v1`) is carried over byte-for-byte from its record. The only
behavioural change is the ROOM paddle apparent-size geometry:
`swatter.directional.tilt_geometry = elevation_aware_tilt_v1`, which weights the tilt
foreshortening term by cos(elevation) (the G3 candidate of the M1.8-N4B5 research,
research branch commit 0e9d2d9).

Because the decoder record's provenance fingerprints the whole ROOM configuration, the new
configuration needs its own record. The accepted N4B1C decoder record
(results/game/calibration_room_m1_8_n4b1c.json) is cited by SHA256 and is not modified.

The tool refuses to write unless:
* the configuration differs from the accepted N4B1C ROOM configuration (commit e3c55b3)
  only in config_version, policy._comment, policy.calibration_paths and the two new
  swatter.directional tilt-geometry keys; and
* the configured decoder equals the accepted N4B1C record's decoder block.

    python tools/n4b5r_geometry_record.py
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
from game.world import TILT_ELEVATION_AWARE  # noqa: E402
from tools.n2_decoder_record import changed_paths, sha256  # noqa: E402

CONFIG = ROOT / 'game_room_config.json'
DECODER_RECORD = 'results/game/calibration_room_m1_8_n4b1c.json'
ACCEPTED_RUNTIME_COMMIT = 'e3c55b36084cd1d05e5f38d0b178aed0b9a59ddf'
RESEARCH_COMMIT_N4B5 = '0e9d2d9'
RESEARCH_FILES = ['game/M1_8_N4B5_PADDLE_VISUAL_GEOMETRY.md', 'tools/n4b5_geometry.py',
                  'tools/n4b5_analysis.py', 'tools/n4b5_resim.py', 'tools/n4b5_evaluate.py',
                  'game/M1_8_N4B4_FREE_FLIGHT_ESCAPE_INTERPRETATION.md']
ALLOWED_CHANGES = {'config_version', 'policy._comment', 'policy.calibration_paths',
                   'swatter.directional.tilt_geometry', 'swatter.directional._tilt_geometry_comment'}
TEXT_SUFFIXES = {'.md', '.py', '.json', '.txt'}


def content_sha256(path):
    """SHA256 of committed content (CRLF normalised to LF for text files)."""
    data = (ROOT / path).read_bytes()
    if Path(path).suffix in TEXT_SUFFIXES:
        data = data.replace(b'\r\n', b'\n')
    return hashlib.sha256(data).hexdigest()


def committed_sha256(commit, path):
    """SHA256 of a file's content at a commit of this repository (LF as stored)."""
    data = subprocess.check_output(['git', 'show', '%s:%s' % (commit, path)], cwd=ROOT)
    return hashlib.sha256(data.replace(b'\r\n', b'\n')).hexdigest()


def build_record():
    config = load_config(CONFIG)
    accepted = json.loads(subprocess.check_output(
        ['git', 'show', ACCEPTED_RUNTIME_COMMIT + ':game_room_config.json'], cwd=ROOT, text=True))
    changed = changed_paths(accepted, config)
    unexpected = [p for p in changed if p not in ALLOWED_CHANGES]
    if unexpected:
        raise SystemExit('configuration differs from the accepted N4B1C ROOM configuration outside '
                         'the geometry flag: ' + ', '.join(unexpected))
    if config['swatter']['directional'].get('tilt_geometry') != TILT_ELEVATION_AWARE:
        raise SystemExit('game_room_config.json must set swatter.directional.tilt_geometry = '
                         + TILT_ELEVATION_AWARE)
    source = load_config(ROOT / DECODER_RECORD)
    if source['provenance'] != calibration_provenance(accepted):
        raise SystemExit('the N4B1C decoder record does not match the accepted ROOM configuration')
    decoder = escape_decoder_spec(config)
    if escape_decoder_spec(accepted) != decoder:
        raise SystemExit('the configured decoder differs from the accepted N4B1C decoder')
    if {k: source['escape_decoder'].get(k) for k in decoder} != decoder:
        raise SystemExit('the configured decoder differs from the N4B1C record decoder block')
    d = config['swatter']['directional']
    record = {
        'record_kind': 'geometry-runtime-candidate-provenance-v1',
        'not_a_scalar_calibration': True,
        'not_a_decoder_recalibration': True,
        'decoder_unchanged': True,
        'geometry_changed': True,
        'status': 'M1.8-N4B5R runtime candidate; not yet human-accepted',
        'rule': ('The accepted M1.8-N4B1C lateral dual-path decoder, unchanged, under the '
                 'M1.8-N4B5R elevation-aware paddle tilt geometry. Only the Retina input changes, '
                 'and only while the paddle is tilted (face < 1) and seen at high elevation.'),
        'escape_threshold': source['escape_threshold'],
        'escape_decoder': copy.deepcopy(source['escape_decoder']),
        'parameter_basis': copy.deepcopy(source['parameter_basis']),
        'geometry': {
            'tilt_geometry': d['tilt_geometry'],
            'previous_tilt_geometry': 'bearing_only_v0',
            'tilt_anisotropy': d['tilt_anisotropy'],
            'formula': ('half = paddle_radius * (e + (1 - e) * face) * (1 - tilt_anisotropy * '
                        'cos(elevation) * (1 - face) * abs(sin(bearing - orientation))), with '
                        'cos(elevation) = horizontal fly-paddle distance / 3-D fly-paddle distance'),
            'previous_formula': ('half = paddle_radius * (e + (1 - e) * face) * (1 - tilt_anisotropy '
                                 '* (1 - face) * abs(sin(bearing - orientation)))'),
            'scope': 'ROOM configuration only; GAME and LAB configurations are unchanged',
            'reason': ('correction of the overhead tilt-foreshortening artifact: the bearing-only term '
                       'turns horizontal bearing rate into apparent expansion of up to 6.9 rad/s under '
                       'a stationary paddle (0.13 rad/s from range change), producing all overhead '
                       'free-flight escapes of M1.8-N4B4 and the episode-5 slow-close signal'),
            'research': {'milestone': 'M1.8-N4B5', 'candidate': 'G3_elevation_aware',
                         'research_commit': RESEARCH_COMMIT_N4B5,
                         'frozen_geometry_sha256': 'a11cafa09750b50bf3cad6e032746336981cc99b481edcdbd45656ddaa830b49',
                         'geometry_module_sha256_raw_worktree': 'c3884e644df5c51ee95489b8f204795e1eb36648d5da14415de3abe0f3d7066a',
                         'files': {p: committed_sha256(RESEARCH_COMMIT_N4B5, p) for p in RESEARCH_FILES}},
            'parameter_class': 'C (geometric rendering correction, not a biological parameter)'},
        'hash_convention': ('decoder_record and research files: SHA256 of committed content with CRLF '
                            'normalised to LF; config_sha256: raw working-file bytes'),
        'decoder_record': {'record': DECODER_RECORD, 'sha256': content_sha256(DECODER_RECORD),
                           'provenance': source['provenance'], 'record_kind': source['record_kind'],
                           'modified': False,
                           'note': 'the accepted N4B1C decoder record; it continues to match the '
                                   'accepted N4B1C ROOM configuration (commit e3c55b3)'},
        'tick_seconds': config['sim']['tick_seconds'],
        'config_sha256': hashlib.sha256(CONFIG.read_bytes()).hexdigest(),
        'provenance': calibration_provenance(config),
        'measurement_conditions': copy.deepcopy(source['measurement_conditions']),
        'measurement_reuse': {
            'kind': 'geometry runtime candidate; decoder transferred unchanged; not a new measurement',
            'decoder_source_record': DECODER_RECORD,
            'decoder_source_sha256': content_sha256(DECODER_RECORD),
            'accepted_runtime_commit': ACCEPTED_RUNTIME_COMMIT,
            'reason': ('The decoder parameters are not re-derived. The fixed-fly no-loom measurements '
                       'behind them see a settled, static paddle, whose encoder drive is zero under '
                       'either geometry; the geometry changes only the time course of the apparent '
                       'size of a tilted paddle seen at high elevation. Runtime validation of the '
                       'candidate is produced by tools/n4b5r_runtime_validation.py.'),
            'changed_config_paths': changed},
        'neurons': source['neurons'], 'connections': source['connections'],
        'input_populations': source['input_populations'], 'versions': source['versions'],
    }
    return config, record


def main():
    config, record = build_record()
    text = json.dumps(record, indent=2) + '\n'
    rel = config['policy']['calibration_paths'][1]
    if rel == DECODER_RECORD:
        raise SystemExit('refusing to overwrite the accepted N4B1C decoder record')
    path = ROOT / rel
    if path.exists() and path.read_text(encoding='utf-8') != text:
        print('replacing', rel)
    path.write_bytes(text.encode('utf-8'))
    print('written', rel, hashlib.sha256(path.read_bytes()).hexdigest())
    print('changed config paths:', record['measurement_reuse']['changed_config_paths'])


if __name__ == '__main__':
    main()
