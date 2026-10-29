"""Write the M3.8 saccade and odor-tracking transfer record (results/game/calibration_room_m3_8.json).

This is NOT a recalibration and runs no new measurement. The accepted M1.8-N4B1C decoder and its
threshold are carried over byte-for-byte from the v27 record (results/game/calibration_room_m1_7_2.json),
as M3.7 carried them over. The only behavioural change is four class-B parameters, preregistered in
game/M3_8_SACCADE_ODOR_DESIGN.md:
- flight.correction.probability: 0.42 -> 0.0;
- flight.saccade.degrees: [25, 105] -> [60, 120];
- flight.saccade.peak_rate_deg_per_second: [700, 1400] -> [1200, 1500];
- ecology.spontaneous_clock_rate.ODOR_TRACK: 0.35 -> 0.0.

**Why the carry-over is sound.** The escape calibration freezes position, heading, velocity and all
saccade timers (game/FLIGHT.md). Check P5 tests this on the fixed-fly protocol.

**The new record.** A record's provenance fingerprints the whole ROOM configuration, so v32 needs
its own record. The v27 record is cited by content SHA256 and is not modified.

**What the tool refuses.** It refuses to write unless:
- the configuration differs from the v27 ROOM configuration (commit 7483e51) only in
  config_version, policy._comment, policy.calibration_paths and the four preregistered keys;
- those keys hold the preregistered values;
- the configured decoder equals the v27 record's decoder block.

    python tools/m3_8_record.py
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
from tools.b2b_iii_record import content_sha256  # noqa: E402
from tools.n2_decoder_record import changed_paths  # noqa: E402

CONFIG = ROOT / 'game_room_config.json'
RECORD = 'results/game/calibration_room_m3_8.json'
LOCAL_RECORD = 'artifacts/game/calibration_room_m3_8.json'
SOURCE_RECORD = 'results/game/calibration_room_m1_7_2.json'
BASELINE_COMMIT = '7483e51'          # ROOM config_version 27, the accepted runtime
CONFIG_VERSION = 32
DESIGN_NOTE = 'game/M3_8_SACCADE_ODOR_DESIGN.md'
RESEARCH_NOTE = 'game/M3_7_SACCADE_RESEARCH.md'
FLIGHT = {'flight.correction.probability': 0.0,
          'flight.saccade.degrees': [60.0, 120.0],
          'flight.saccade.peak_rate_deg_per_second': [1200.0, 1500.0],
          'ecology.spontaneous_clock_rate.ODOR_TRACK': 0.0}
ALLOWED_CHANGES = {'config_version', 'policy._comment', 'policy.calibration_paths'} | set(FLIGHT)


def baseline_config():
    return json.loads(subprocess.check_output(
        ['git', 'show', BASELINE_COMMIT + ':game_room_config.json'], cwd=ROOT, text=True))


def value(config, dotted):
    node = config
    for key in dotted.split('.'):
        node = node[key]
    return node


def build_record(config=None):
    config = load_config(CONFIG) if config is None else config
    baseline = baseline_config()
    changed = changed_paths(baseline, config)
    unexpected = [p for p in changed if p not in ALLOWED_CHANGES]
    if unexpected:
        raise SystemExit('configuration differs from the v27 ROOM configuration outside the '
                         'preregistered keys: ' + ', '.join(unexpected))
    if config['config_version'] != CONFIG_VERSION:
        raise SystemExit('config_version must be %d' % CONFIG_VERSION)
    for key, expected in FLIGHT.items():
        if value(config, key) != expected:
            raise SystemExit('%s must be %s (game/M3_8_SACCADE_ODOR_DESIGN.md)' % (key, expected))
    if config['policy']['calibration_paths'] != [LOCAL_RECORD, RECORD]:
        raise SystemExit('policy.calibration_paths must be %s' % [LOCAL_RECORD, RECORD])
    source = load_config(ROOT / SOURCE_RECORD)
    if source['provenance'] != calibration_provenance(baseline):
        raise SystemExit('the v27 record does not match the v27 ROOM configuration')
    decoder = escape_decoder_spec(config)
    if escape_decoder_spec(baseline) != decoder:
        raise SystemExit('the configured decoder differs from the v27 configuration')
    if {k: source['escape_decoder'].get(k) for k in decoder} != decoder:
        raise SystemExit('the configured decoder differs from the v27 record decoder block')
    record = {
        'record_kind': 'm3-8-saccade-odor-transfer-provenance-v1',
        'stage': 'M3.8',
        'not_a_scalar_calibration': True,
        'not_a_decoder_recalibration': True,
        'decoder_unchanged': True,
        'flight_changed': True,
        'rule': ('The accepted M1.8-N4B1C decoder, unchanged, with four class-B parameters changed: '
                 'open-space clock events are all saccades, of 60-120 degrees at 1200-1500 degrees per '
                 'second, and the spontaneous clock stops while the fly tracks an odor upwind. The escape '
                 'calibration freezes all saccade timers.'),
        'escape_threshold': source['escape_threshold'],
        'escape_decoder': copy.deepcopy(source['escape_decoder']),
        'parameter_basis': copy.deepcopy(source['parameter_basis']),
        'geometry': copy.deepcopy(source['geometry']),
        'flight': {'changed_keys': {k: {'before': value(baseline, k), 'after': v} for k, v in FLIGHT.items()},
                   'basis': ('Frye and Dickinson 2004: "Between saccades, Drosophila tends to fly in a straight '
                             'line"; about 90 degrees per saccade (E10); Censi et al. 2013 baseline rate about '
                             '0.4 per s; Budick and Dickinson 2006: upwind heading maintained in odor ('
                             + RESEARCH_NOTE + ', sections 4-5)'),
                   'scope': 'ROOM configuration only; GAME and LAB configurations are unchanged'},
        'kinematics': copy.deepcopy(config.get('kinematics', {})),
        'ecology_threat_input': copy.deepcopy(config.get('ecology_threat_input')),
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
            'kind': 'free-flight and ecology-clock change; decoder transferred unchanged; not a new measurement',
            'source_record': SOURCE_RECORD,
            'source_sha256': content_sha256(SOURCE_RECORD),
            'baseline_commit': BASELINE_COMMIT,
            'reason': ('The threshold and decoder are not re-derived. The escape calibration freezes position, '
                       'heading, velocity and all saccade timers, so the free-flight generator cannot reach the '
                       'measurement; check P5 of the design note compares fixed-fly escapes of both '
                       'configurations trial by trial.'),
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
