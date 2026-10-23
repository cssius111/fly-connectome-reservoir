"""M3.3: calibration and validation of the doublet decoder (game/M3_3_ESCAPE_DECISION_DESIGN.md).

The protocol-E harness of tools/m3_2_escape_roles.py, unchanged, with the M3.3 decoder. Outputs
go to artifacts/m3_3_run/ (git-ignored), one file per unit of work, with the M3.0 provenance
guard, so an interrupted run resumes where it stopped.

    python tools/m3_3_escape_decision.py calibrate   # section 3: the scale grid, seeds 600001-600024
    python tools/m3_3_escape_decision.py validate    # section 4: V1-V5 with the v29 ROOM configuration
    python tools/m3_3_escape_decision.py report

Calibration builds each grid configuration in memory: the v27 ROOM configuration with the
ache2019_v1 encoder at the grid scale and the same_side_doublet_v1 decoder. Its policy comes from
game.session.policy_from_source, exactly as the runtime maps a decoder block, so no record is
needed yet. Validation runs the v29 ROOM configuration as the runtime loads it, so it needs
the v29 candidate (commit 9830757) checked out; M3.3 failed check V3 and the working
configuration is v27 again.
"""
from __future__ import annotations

import argparse
import copy
import json
import math
import os
from pathlib import Path
import sys

os.environ.setdefault('NUMBA_NUM_THREADS', '4')
os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from game.fly import build_brain  # noqa: E402
from game.perception import FEATURE_MODEL_ACHE2019, encoder_feature_model  # noqa: E402
from game.session import (DOUBLET_DECODER, ThresholdSource, escape_decoder_spec,  # noqa: E402
                          load_config, policy_from_source)
import tools.m3_0_scorecard as M  # noqa: E402
import tools.m3_2_ache_targets as T  # noqa: E402
import tools.m3_2_escape_roles as R  # noqa: E402
import tools.n4b6_protocol as P  # noqa: E402

OUT = ROOT / 'artifacts/m3_3_run'
CALIBRATION_SEEDS = tuple(range(600001, 600025))
VALIDATION_SEEDS = tuple(range(810001, 810025))
GRID = tuple(round(0.20 + 0.01 * k, 2) for k in range(31))          # 0.20 ... 0.50 V/mV
DOUBLET = {'kind': DOUBLET_DECODER, 'alert_reference_threshold': 1.45, 'doublet_window_ms': 40,
           'required_spikes': 2}
START_LV_MS, START_DEG = (40, 80, 160), (5.0, 10.0, 20.0)


def base_config():
    """The v27 ROOM configuration (main after M3.2), whatever the working file holds."""
    return M.config()


def candidate_config(scale):
    c = copy.deepcopy(base_config())
    c['encoder']['feature_model'] = FEATURE_MODEL_ACHE2019
    c['encoder']['ache2019'] = {'scale_volts_per_mv': scale}
    c['policy']['escape_decoder'] = dict(DOUBLET)
    encoder_feature_model(c)
    return c


def candidate_policy(config):
    decoder = escape_decoder_spec(config)
    return policy_from_source(config, ThresholdSource(decoder['alert_reference_threshold'],
                                                      'm3.3 calibration', decoder))


def calibrate():
    base = base_config()
    dt = float(base['sim']['tick_seconds'])
    targets = {r['lv_ms']: r['peak_time_ms'] / 1000.0 for r in T.targets(T.CALIBRATION_LV_MS)}
    brain = build_brain(base, ROOT)
    out = OUT / 'calibration'
    M.check_provenance(out, 's*.json')
    for scale in GRID:
        path = out / ('s%.2f.json' % scale)
        if path.exists():
            continue
        config = candidate_config(scale)
        session = R.fixed_fly_session(config, brain=brain, policy=candidate_policy(config))
        result = {'scale_volts_per_mv': scale, 'per_lv': {}}
        for lv_ms in T.CALIBRATION_LV_MS:
            result['per_lv'][str(lv_ms)] = R.timed_trials(
                session, lv_ms / 1000.0, 10.0, 90.0, targets[lv_ms] + R.WINDOW_AFTER_TARGET_S,
                CALIBRATION_SEEDS, dt)
        path.write_text(json.dumps(result) + '\n', encoding='utf-8')
        print('scale %.2f: %s' % (scale, ', '.join(
            '%s ms %d/%d' % (lv, sum(r['escaped'] for r in rows), len(rows))
            for lv, rows in result['per_lv'].items())), flush=True)


def calibration_choice():
    saved = R.OUT, R.GRID
    R.OUT, R.GRID = OUT, GRID
    try:
        return R.calibration_choice()
    finally:
        R.OUT, R.GRID = saved


def validation_config():
    c = load_config(ROOT / 'game_room_config.json')
    if escape_decoder_spec(c)['kind'] != DOUBLET_DECODER:
        raise SystemExit('the ROOM configuration does not use the M3.3 decoder')
    return c


def validate():
    saved = (R.OUT, R.CALIBRATION_SEEDS, R.START_LV_MS, R.START_DEG, R.validation_config)
    R.OUT, R.CALIBRATION_SEEDS = OUT, VALIDATION_SEEDS
    R.START_LV_MS, R.START_DEG = START_LV_MS, START_DEG
    R.validation_config = validation_config
    try:
        R.validate()
    finally:
        R.OUT, R.CALIBRATION_SEEDS, R.START_LV_MS, R.START_DEG, R.validation_config = saved


def report():
    out = {'calibration': calibration_choice()}
    if (OUT / 'v1' / 'escape' / 'provenance.json').exists():
        saved = (R.OUT, R.START_LV_MS, R.START_DEG)
        R.OUT, R.START_LV_MS, R.START_DEG = OUT, START_LV_MS, START_DEG
        try:
            out['validation'] = R.validation_report()
        finally:
            R.OUT, R.START_LV_MS, R.START_DEG = saved
    (OUT / 'report.json').write_text(json.dumps(out, indent=1, default=str) + '\n', encoding='utf-8')
    c = out['calibration']
    print('calibration: chosen scale %s V/mV' % c['chosen_scale_volts_per_mv'])
    for r in c['grid']:
        per = ' | '.join('%s ms %.2f %s' % (lv, p['fraction'], '-' if p['median_t_ms'] is None
                                             else '%+.0f/%+.0f ms' % (p['median_t_ms'], p['target_ms']))
                         for lv, p in r['per_lv'].items())
        print('  %.2f %s loss %s | %s' % (r['scale_volts_per_mv'], 'ok' if r['admissible'] else '--',
                                          '-' if r['loss_ms2'] is None else '%.0f' % r['loss_ms2'], per))
    if 'validation' in out:
        v = out['validation']
        e = v['V1']
        print('V1: E1 %.3f (%s); E2 threshold %s deg, alpha %s, delta %s ms (%s); E3 %s' % (
            e['E1']['value'], e['E1']['class'], e['E2']['theta_threshold_deg'], e['E2']['alpha'],
            e['E2']['delta_ms'], e['E2']['class'], e['E3']['before_collision_fraction_lv10']))
        print('V1 E1 per l/v:', e['E1']['per_lv'])
        print('V1 E4:', {k: (None if x['circular_mean_deg'] is None else round(x['circular_mean_deg'], 1),
                             x['class']) for k, x in e['E4'].items()})
        for key in ('V2', 'V3', 'V4', 'V5'):
            print(key + ':', v[key])


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('mode', choices=('calibrate', 'validate', 'report'))
    {'calibrate': calibrate, 'validate': validate, 'report': report}[parser.parse_args().mode]()


if __name__ == '__main__':
    main()
