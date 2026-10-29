"""Write the M3.10 upwind-surge transfer record (results/game/calibration_room_m3_10.json).

This is NOT a recalibration and runs no new measurement. The accepted M1.8-N4B1C decoder and its
threshold are carried over byte-for-byte from the v32 record (results/game/calibration_room_m3_8.json),
as M3.9 carried them over. The only behavioural change is the new class-B block
`ecology.upwind_surge`, preregistered in game/M3_10_UPWIND_SURGE_DESIGN.md:
- ecology.upwind_surge.delay_seconds: 0.07;
- ecology.upwind_surge.peak_rate_deg_per_second: [1200, 1500];
- ecology.upwind_surge._comment.

**Why the carry-over is sound.** The escape calibration runs with the ecology disabled and freezes
all saccade timers (game/FLIGHT.md), so no surge can occur during it. Check P5 tests this on the
fixed-fly protocol.

**The new record.** A record's provenance fingerprints the whole ROOM configuration, so v34 needs
its own record. The v32 record is cited by content SHA256 and is not modified.

**What the tool refuses.** It refuses to write unless:
- the configuration differs from the v32 ROOM configuration (commit e113583) only in
  config_version, policy._comment, policy.calibration_paths and the preregistered keys;
- those keys hold the preregistered values;
- the configured decoder equals the v32 record's decoder block.

    python tools/m3_10_record.py
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
RECORD = 'results/game/calibration_room_m3_10.json'
LOCAL_RECORD = 'artifacts/game/calibration_room_m3_10.json'
SOURCE_RECORD = 'results/game/calibration_room_m3_8.json'
BASELINE_COMMIT = 'e113583'          # ROOM config_version 32, the accepted runtime
CONFIG_VERSION = 34
DESIGN_NOTE = 'game/M3_10_UPWIND_SURGE_DESIGN.md'
RESEARCH_NOTE = 'game/M3_9_WALL_SACCADE_RESEARCH.md'
FLIGHT = {'ecology.upwind_surge.delay_seconds': 0.07,
          'ecology.upwind_surge.peak_rate_deg_per_second': [1200.0, 1500.0]}
# The whole new block is one changed path; its preregistered values are checked key by key.
ALLOWED_CHANGES = {'config_version', 'policy._comment', 'policy.calibration_paths', 'ecology.upwind_surge'}


def baseline_config():
    return json.loads(subprocess.check_output(
        ['git', 'show', BASELINE_COMMIT + ':game_room_config.json'], cwd=ROOT, text=True))


def value(config, dotted, default=KeyError):
    node = config
    for key in dotted.split('.'):
        if key not in node and default is not KeyError:
            return default
        node = node[key]
    return node


def build_record(config=None):
    config = load_config(CONFIG) if config is None else config
    baseline = baseline_config()
    changed = changed_paths(baseline, config)
    unexpected = [p for p in changed if p not in ALLOWED_CHANGES]
    if unexpected:
        raise SystemExit('configuration differs from the v32 ROOM configuration outside the '
                         'preregistered keys: ' + ', '.join(unexpected))
    if config['config_version'] != CONFIG_VERSION:
        raise SystemExit('config_version must be %d' % CONFIG_VERSION)
    for key, expected in FLIGHT.items():
        if value(config, key) != expected:
            raise SystemExit('%s must be %s (game/M3_10_UPWIND_SURGE_DESIGN.md)' % (key, expected))
    if config['policy']['calibration_paths'] != [LOCAL_RECORD, RECORD]:
        raise SystemExit('policy.calibration_paths must be %s' % [LOCAL_RECORD, RECORD])
    source = load_config(ROOT / SOURCE_RECORD)
    if source['provenance'] != calibration_provenance(baseline):
        raise SystemExit('the v32 record does not match the v32 ROOM configuration')
    decoder = escape_decoder_spec(config)
    if escape_decoder_spec(baseline) != decoder:
        raise SystemExit('the configured decoder differs from the v32 configuration')
    if {k: source['escape_decoder'].get(k) for k in decoder} != decoder:
        raise SystemExit('the configured decoder differs from the v32 record decoder block')
    record = {
        'record_kind': 'm3-10-upwind-surge-transfer-provenance-v1',
        'stage': 'M3.10',
        'not_a_scalar_calibration': True,
        'not_a_decoder_recalibration': True,
        'decoder_unchanged': True,
        'flight_changed': True,
        'rule': ('The accepted M1.8-N4B1C decoder, unchanged, with one class-B ecology block added: once per '
                 'ODOR_TRACK bout, 0.07 s after entry, a SURGE turn of the sensed upwind bearing at 1200-1500 '
                 'degrees per second. The escape calibration runs with the ecology disabled and freezes all '
                 'saccade timers.'),
        'escape_threshold': source['escape_threshold'],
        'escape_decoder': copy.deepcopy(source['escape_decoder']),
        'parameter_basis': copy.deepcopy(source['parameter_basis']),
        'geometry': copy.deepcopy(source['geometry']),
        'flight': {'changed_keys': {k: {'before': value(baseline, k, None), 'after': v} for k, v in FLIGHT.items()},
                   'basis': ('E16, van Breugel and Dickinson 2014: flies turn upwind 190 +- 75 ms after '
                             'encountering a plume; the model turned upwind with a median 1.6 s (' + RESEARCH_NOTE
                             + ', section 5); the accepted saccade peak rates'),
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
            'kind': 'ecology upwind-surge change; decoder transferred unchanged; not a new measurement',
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
