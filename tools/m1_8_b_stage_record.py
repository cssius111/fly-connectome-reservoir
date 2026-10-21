"""Write the calibration transfer record of one M1.8-B completion stage (B2d onwards).

This is NOT a recalibration and runs no new measurement. Each stage changes only ecological
locomotion or ecological decisions, which fixed-fly-v2 disables (ecology, fly motion and
collisions are off during the measurement), so the accepted M1.8-N4B1C decoder under the
accepted M1.8-N4B5R geometry is carried over byte-for-byte from the previous stage's record.
Because a record's provenance fingerprints the whole ROOM configuration, every stage needs
its own record; the previous record is cited by content SHA256 and is not modified.

The tool refuses to write unless the configuration differs from the previous stage's
configuration (read from the stage's baseline commit) only in `config_version`,
`policy._comment`, `policy.calibration_paths` and the stage's own preregistered paths, and
unless the configured decoder equals the previous record's decoder block.

The stages and their preregistered paths are listed in STAGES and described in
game/M1_8_B_COMPLETION_DESIGN.md.

    python tools/m1_8_b_stage_record.py B2d
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
from tools.b2b_iii_record import content_sha256  # noqa: E402
from tools.n2_decoder_record import changed_paths  # noqa: E402

CONFIG = ROOT / 'game_room_config.json'
ORIGINAL_MEASUREMENT = 'results/game/calibration_room_m1_7_1.json'
DESIGN_NOTE = 'game/M1_8_B_COMPLETION_DESIGN.md'
ALWAYS_ALLOWED = ('config_version', 'policy._comment', 'policy.calibration_paths')

# One entry per stage, in order. `baseline_commit` holds the previous stage's final
# configuration; `paths` are the configuration paths the stage may change (a path also
# covers everything below it).
STAGES = {
    'B2d': {'config_version': 20, 'record': 'results/game/calibration_room_m1_8_b2d.json',
            'source_record': 'results/game/calibration_room_m1_8_b3a.json',
            'baseline_commit': '6b43c0fd2cf5537216bb5f663b4e606e0fac76f6',
            'paths': ('kinematics.odor_search_speed_bl_s', 'kinematics.recover_speed_bl_s'),
            'rule': ('ODOR_SEARCH and RECOVER speed: one symmetric triangular draw per ecological '
                     'episode on the accepted envelopes, each from its own random stream.')},
    'B2e': {'config_version': 21, 'record': 'results/game/calibration_room_m1_8_b2e.json',
            'source_record': 'results/game/calibration_room_m1_8_b2d.json',
            'baseline_commit': '066f7685ea47338a468c1c9ed862dc3a75d2e64f',
            'paths': ('kinematics.speed_relaxation_per_second',),
            'rule': ('Speed relaxation: one symmetric triangular damping-rate draw per ecological episode '
                     'of the sampled contexts, from its own random stream, mean held at the accepted 3.0 /s.')},
    'B3b': {'config_version': 22, 'record': 'results/game/calibration_room_m1_8_b3b.json',
            'source_record': 'results/game/calibration_room_m1_8_b2e.json',
            'baseline_commit': '72eb8e7f0c1abeeaeb22a2b8b39ed4b091b2a4aa',
            'paths': ('ecology.odor_history',),
            'rule': ('Odor timers replaced by an encounter history: weaker upwind response with history, '
                     'a plume-abandonment hazard with a short refractory, and a search give-up hazard after '
                     'a minimum search.')},
}


def stage_config(stage):
    """The stage's own configuration: the working file for the newest stage, otherwise the
    next stage's baseline commit."""
    names = list(STAGES)
    index = names.index(stage)
    if index + 1 < len(names):
        return read_commit(STAGES[names[index + 1]]['baseline_commit'])
    return load_config(CONFIG)


def read_commit(commit):
    return json.loads(subprocess.check_output(['git', 'show', commit + ':game_room_config.json'],
                                              cwd=ROOT, text=True))


def allowed(path, paths):
    return any(path == p or path.startswith(p + '.') for p in tuple(paths) + ALWAYS_ALLOWED)


def build_record(stage, config=None):
    spec = STAGES[stage]
    config = load_config(CONFIG) if config is None else config
    baseline = read_commit(spec['baseline_commit'])
    changed = changed_paths(baseline, config)
    unexpected = [p for p in changed if not allowed(p, spec['paths'])]
    if unexpected:
        raise SystemExit(stage + ': configuration differs from the previous stage outside the '
                         'preregistered paths: ' + ', '.join(unexpected))
    if config['config_version'] != spec['config_version'] or \
            config['config_version'] != baseline['config_version'] + 1:
        raise SystemExit(stage + ': config_version must be %d' % spec['config_version'])
    if config['policy']['calibration_paths'][1] != spec['record']:
        raise SystemExit(stage + ': policy.calibration_paths must name ' + spec['record'])
    source = load_config(ROOT / spec['source_record'])
    if source['provenance'] != calibration_provenance(baseline):
        raise SystemExit(stage + ': the source record does not match the previous stage configuration')
    decoder = escape_decoder_spec(config)
    if escape_decoder_spec(baseline) != decoder:
        raise SystemExit(stage + ': the configured decoder differs from the previous stage')
    if {k: source['escape_decoder'].get(k) for k in decoder} != decoder:
        raise SystemExit(stage + ': the configured decoder differs from the source record decoder block')
    record = {
        'record_kind': 'm1-8-b-stage-transfer-provenance-v1',
        'stage': 'M1.8-' + stage,
        'not_a_scalar_calibration': True,
        'not_a_decoder_recalibration': True,
        'decoder_unchanged': True,
        'geometry_unchanged': True,
        'rule': spec['rule'],
        'escape_threshold': source['escape_threshold'],
        'escape_decoder': copy.deepcopy(source['escape_decoder']),
        'parameter_basis': copy.deepcopy(source['parameter_basis']),
        'geometry': copy.deepcopy(source['geometry']),
        'kinematics': copy.deepcopy(config.get('kinematics', {})),
        'ecology_threat_input': copy.deepcopy(config.get('ecology_threat_input')),
        'stage_paths': list(spec['paths']),
        'stage_values': {p: lookup(config, p) for p in spec['paths']},
        'design_note': DESIGN_NOTE,
        'hash_convention': ('source records: SHA256 of committed content with CRLF normalised to '
                            'LF; config_sha256: raw working-file bytes'),
        'source_record': {'record': spec['source_record'], 'sha256': content_sha256(spec['source_record']),
                          'provenance': source['provenance'], 'record_kind': source['record_kind'],
                          'modified': False},
        'tick_seconds': config['sim']['tick_seconds'],
        'config_sha256': hashlib.sha256(CONFIG.read_bytes()).hexdigest(),
        'provenance': calibration_provenance(config),
        'measurement_conditions': copy.deepcopy(source['measurement_conditions']),
        'measurement_reuse': {
            'kind': ('ecological stage; decoder and geometry transferred unchanged; not a new '
                     'measurement'),
            'source_record': spec['source_record'],
            'source_sha256': content_sha256(spec['source_record']),
            'original_measurement': ORIGINAL_MEASUREMENT,
            'original_measurement_sha256': content_sha256(ORIGINAL_MEASUREMENT),
            'baseline_commit': spec['baseline_commit'],
            'reason': ('The threshold and decoder are not re-derived. fixed-fly-v2 disables ecology, '
                       'fly motion and collisions, so this stage cannot change the retinal or neural '
                       'input of the measurement behind them.'),
            'changed_config_paths': changed},
        'neurons': source['neurons'], 'connections': source['connections'],
        'input_populations': source['input_populations'], 'versions': source['versions'],
    }
    return record


def lookup(config, path):
    value = config
    for key in path.split('.'):
        value = value.get(key) if isinstance(value, dict) else None
    return copy.deepcopy(value)


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('stage', choices=list(STAGES))
    args = parser.parse_args()
    if args.stage != list(STAGES)[-1]:
        raise SystemExit('only the newest stage can be written; earlier records are frozen')
    record = build_record(args.stage)
    rel = STAGES[args.stage]['record']
    if rel == STAGES[args.stage]['source_record']:
        raise SystemExit('refusing to overwrite the source record')
    text = json.dumps(record, indent=2) + '\n'
    path = ROOT / rel
    if path.exists() and path.read_text(encoding='utf-8') != text:
        print('replacing', rel)
    path.write_bytes(text.encode('utf-8'))
    print('written', rel, hashlib.sha256(path.read_bytes()).hexdigest())
    print('changed config paths:', record['measurement_reuse']['changed_config_paths'])


if __name__ == '__main__':
    main()
