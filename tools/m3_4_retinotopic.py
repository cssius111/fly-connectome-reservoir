"""M3.4: calibration and validation of the retinotopic_v1 encoder (game/M3_4_RETINOTOPIC_DRIVE_DESIGN.md).

The protocol-E harness of tools/m3_2_escape_roles.py, unchanged: a fixed fly whose Retina is
replaced once per tick by a synthetic looming disk, with the encoder, MaleCNS, DNp01 and the
runtime decoder unchanged. Outputs go to artifacts/m3_4_run/ (git-ignored), one file per unit of
work, with the M3.0 provenance guard, so an interrupted run resumes where it stopped.

    python tools/m3_4_retinotopic.py calibrate [--lane K --lanes N]   # section 4, seeds 600001-600024
    python tools/m3_4_retinotopic.py validate                         # section 5: V1-V5, V8, D1
    python tools/m3_4_retinotopic.py d2                               # D2: V6a with a 1 deg/s edge bound
    python tools/m3_4_retinotopic.py report

Stimulus positions:
- **Calibration, V3, V4 and V8b.** The calibration stimulus sits at the Ache et al. 2019
  electrophysiology position, azimuth 50 deg and elevation 11 deg (V8b mirrors it to -50 deg).
- **V1 and V2.** These keep M3.0's and M3.3's stimuli, which lie on the horizon (elevation 0).

Calibration builds each grid configuration in memory:
- the v27 ROOM configuration;
- the retinotopic_v1 block at the grid scale;
- the M3.3 same_side_doublet_v1 decoder, whose policy comes from game.session.policy_from_source.

Validation runs the v30 ROOM configuration as the runtime loads it. The receptive-field table
data/receptive_fields_v1.npz must be built first (tools/build_receptive_fields.py).

M3.4 failed checks V2 and V8a and the working configuration is v27 again
(results/game/M3_4_RETINOTOPIC_DRIVE.md). To rerun validate or d2, check out
game_room_config.json from the v30 candidate commit 10e12f6 first.
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

import numpy as np  # noqa: E402

from game.fly import build_brain  # noqa: E402
from game.perception import FEATURE_MODEL_RETINOTOPIC, Retina, encoder_feature_model, fields_digest  # noqa: E402
from game.session import (DOUBLET_DECODER, ThresholdSource, escape_decoder_spec,  # noqa: E402
                          load_config, policy_from_source)
import tools.m3_0_scorecard as M  # noqa: E402
import tools.m3_2_ache_targets as T  # noqa: E402
import tools.m3_2_escape_roles as R  # noqa: E402
import tools.n4b6_protocol as P  # noqa: E402

OUT = ROOT / 'artifacts/m3_4_run'
FIELDS_FILE = 'data/receptive_fields_v1.npz'
CALIBRATION_SEEDS = tuple(range(600001, 600025))
VALIDATION_SEEDS = tuple(range(940001, 940025))
GRID = tuple(float('%.3g' % (10.0 * 32.0 ** (k / 30.0))) for k in range(31))   # 10 ... 320 V/mV
ACHE_AZIMUTH_DEG, ACHE_ELEVATION_DEG = 50.0, 11.0
ACCEPTANCE_FWHM_DEG = 7.70
LPLC2_MIN_EDGE_SPEED_DEG_S = 10.0
DOUBLET = {'kind': DOUBLET_DECODER, 'alert_reference_threshold': 1.45, 'doublet_window_ms': 40,
           'required_spikes': 2}
START_LV_MS, START_DEG = (40, 80, 160), (5.0, 10.0, 20.0)
V8B_LV_MS = (20, 40, 80)
SYMMETRY_TOLERANCE = 0.20
D1_DNS = ('DNp02', 'DNp11')
D2_MIN_EDGE_SPEED_DEG_S = 1.0


def table_digest():
    path = ROOT / FIELDS_FILE
    if not path.exists():
        raise SystemExit('%s is missing; run python tools/build_receptive_fields.py first' % FIELDS_FILE)
    with np.load(path) as z:
        return fields_digest({k: z[k] for k in z.files})


def retinotopic_block(scale, min_edge=LPLC2_MIN_EDGE_SPEED_DEG_S):
    return {'scale_volts_per_mv': scale, 'acceptance_fwhm_deg': ACCEPTANCE_FWHM_DEG,
            'lplc2_min_edge_speed_deg_s': min_edge, 'fields_file': FIELDS_FILE,
            'fields_sha256': table_digest()}


def candidate_config(scale):
    """The v27 ROOM configuration with the retinotopic_v1 block and the M3.3 decoder."""
    c = copy.deepcopy(M.config())
    c['encoder']['feature_model'] = FEATURE_MODEL_RETINOTOPIC
    c['encoder']['retinotopic'] = retinotopic_block(scale)
    c['policy']['escape_decoder'] = dict(DOUBLET)
    encoder_feature_model(c)
    return c


def candidate_policy(config):
    decoder = escape_decoder_spec(config)
    return policy_from_source(config, ThresholdSource(decoder['alert_reference_threshold'],
                                                      'm3.4 calibration', decoder))


def placed(retinas, azimuth_deg=ACHE_AZIMUTH_DEG, elevation_deg=ACHE_ELEVATION_DEG):
    """The same disk sequence at another position on the eye."""
    return [Retina(theta=r.theta, theta_dot=r.theta_dot, azimuth=azimuth_deg / 180.0,
                   elevation=math.radians(elevation_deg)) for r in retinas]


def timed_trials(session, lv, start_deg, stop_deg, end_after_collision_s, seeds, dt,
                 azimuth_deg=ACHE_AZIMUTH_DEG):
    """tools/m3_2_escape_roles.timed_trials with the disk at the calibration position."""
    retinas, pre, t0, thetas, last = R.looming(lv, dt, start_deg, stop_deg, end_after_collision_s)
    retinas = placed(retinas, azimuth_deg)
    rows = []
    for seed in seeds:
        escapes = R.run_trial(session, retinas, seed)
        first = next((e for e in escapes if pre <= e[0] <= last), None)
        row = {'seed': seed, 'pre_stimulus_escapes': sum(1 for e in escapes if e[0] < pre),
               'escaped': first is not None}
        if first is not None:
            row.update({'tick': first[0], 't_rel_s': (first[0] - pre + 1) * dt - t0,
                        'theta_deg': math.degrees(thetas[first[0]])})
        rows.append(row)
    return rows


def targets(lvs):
    return {r['lv_ms']: r['peak_time_ms'] / 1000.0 for r in T.targets(lvs)}


# --------------------------------------------------------------------------- calibration ---
def calibrate(lane=0, lanes=1):
    base = M.config()
    dt = float(base['sim']['tick_seconds'])
    goal = targets(T.CALIBRATION_LV_MS)
    brain = build_brain(base, ROOT)
    out = OUT / 'calibration'
    M.check_provenance(out, 's*.json')
    for k, scale in enumerate(GRID):
        path = out / ('s%.2f.json' % scale)            # the file name tools/m3_2_escape_roles reads
        if k % lanes != lane or path.exists():
            continue
        config = candidate_config(scale)
        session = R.fixed_fly_session(config, brain=brain, policy=candidate_policy(config))
        result = {'scale_volts_per_mv': scale, 'per_lv': {}}
        for lv_ms in T.CALIBRATION_LV_MS:
            result['per_lv'][str(lv_ms)] = timed_trials(
                session, lv_ms / 1000.0, 10.0, 90.0, goal[lv_ms] + R.WINDOW_AFTER_TARGET_S,
                CALIBRATION_SEEDS, dt)
        session.close()
        path.write_text(json.dumps(result) + '\n', encoding='utf-8')
        print('scale %g: %s' % (scale, ', '.join(
            '%s ms %d/%d' % (lv, sum(r['escaped'] for r in rows), len(rows))
            for lv, rows in result['per_lv'].items())), flush=True)


def calibration_choice():
    saved = R.OUT, R.GRID
    R.OUT, R.GRID = OUT, GRID
    try:
        return R.calibration_choice()
    finally:
        R.OUT, R.GRID = saved


# ---------------------------------------------------------------------------- validation ---
def validation_config():
    c = load_config(ROOT / 'game_room_config.json')
    if encoder_feature_model(c) != FEATURE_MODEL_RETINOTOPIC:
        raise SystemExit('the ROOM configuration does not use the retinotopic_v1 encoder')
    if escape_decoder_spec(c)['kind'] != DOUBLET_DECODER:
        raise SystemExit('the ROOM configuration does not use the M3.3 decoder')
    return c


def dn_counter(session, cells):
    """Count per-tick spikes of the given cells by wrapping brain.step, which it does not change.

    Returns the per-cell tick lists and a function that restores the class method."""
    brain = session.brain
    original = brain.step
    counts = {name: [] for name in cells}

    def step(*args, **kwargs):
        fired = original(*args, **kwargs)
        for name, index in cells.items():
            counts[name].append(int(index in fired))
        return fired

    def undo():
        del brain.step
    brain.step = step
    return counts, undo


def validate():
    cfg = validation_config()
    dt = float(cfg['sim']['tick_seconds'])
    session = R.fixed_fly_session(cfg)              # the runtime path: decoder from the v30 record
    b = np.load(ROOT / 'data/brain.npz')
    dn = {'%s_%s' % (d, s): int(np.flatnonzero((b['cell_type'] == d) & (b['side'] == s))[0])
          for d in D1_DNS for s in 'LR'}
    # V1: the M3.0 protocol E, unchanged, in M3.0's file format; D1 counts DNp02/DNp11 spikes.
    v1, d1 = OUT / 'v1' / 'escape', OUT / 'd1'
    M.check_provenance(v1, '*.json')
    M.check_provenance(d1, '*.json')
    for lv_ms in M.LV_MS:
        lv = lv_ms / 1000.0
        for name, azimuth in M.AZIMUTHS.items():
            path = v1 / ('lv%03d_%s.json' % (lv_ms, name))
            if path.exists():
                continue
            retinas, pre, t0, thetas = M.stimulus(lv, azimuth, dt)
            last = pre + int(math.floor((t0 + M.WINDOW_AFTER_S) / dt + 1e-9)) - 1
            trials, spikes = [], []
            for seed in P.SEEDS:
                counts, undo = dn_counter(session, dn)
                try:
                    escapes = R.run_trial(session, retinas, seed)
                finally:
                    undo()
                spikes.append({k: sum(v[pre:last + 1]) for k, v in counts.items()})
                first = next((e for e in escapes if pre <= e[0] <= last), None)
                trial = {'seed': seed, 'pre_stimulus_escapes': sum(1 for e in escapes if e[0] < pre),
                         'escaped': first is not None}
                if first is not None:
                    i, forward, lateral = first
                    trial.update({'tick': i, 't_before': t0 - (i - pre + 1) * dt,
                                  'theta_deg': math.degrees(thetas[i]),
                                  'direction_deg': math.degrees(math.atan2(lateral, forward))})
                trials.append(trial)
            (d1 / ('lv%03d_%s.json' % (lv_ms, name))).write_text(
                json.dumps({'lv_ms': lv_ms, 'azimuth': name, 'spikes': spikes}) + '\n', encoding='utf-8')
            path.write_text(json.dumps({'lv_ms': lv_ms, 'azimuth': name, 'azimuth_value': azimuth,
                                        't0': t0, 'onset_index': pre, 'last_window_index': last,
                                        'trials': trials}, indent=1) + '\n', encoding='utf-8')
            print('V1 lv %d ms %s: %d of %d escaped' % (lv_ms, name, sum(t['escaped'] for t in trials),
                                                       len(trials)), flush=True)
    other = OUT / 'v2_v4'
    M.check_provenance(other, '*.json')
    # V2: start-size invariance, right azimuth on the horizon, to collision as in M3.0.
    path = other / 'v2_start_size.json'
    if not path.exists():
        rows = {}
        for lv_ms in START_LV_MS:
            for start in START_DEG:
                rows['%d_%g' % (lv_ms, start)] = R.timed_trials(
                    session, lv_ms / 1000.0, start, None, M.WINDOW_AFTER_S, VALIDATION_SEEDS, dt)
                print('V2 lv %d ms start %g deg done' % (lv_ms, start), flush=True)
        path.write_text(json.dumps(rows) + '\n', encoding='utf-8')
    # V3: held-out l/v on the calibration stimulus.
    path = other / 'v3_held_out.json'
    if not path.exists():
        goal = targets(T.HELD_OUT_LV_MS)
        rows = {}
        for lv_ms in T.HELD_OUT_LV_MS:
            rows[str(lv_ms)] = timed_trials(session, lv_ms / 1000.0, 10.0, 90.0,
                                            goal[lv_ms] + R.WINDOW_AFTER_TARGET_S, VALIDATION_SEEDS, dt)
            print('V3 lv %d ms done' % lv_ms, flush=True)
        path.write_text(json.dumps(rows) + '\n', encoding='utf-8')
    # V4: static disks and a receding disk at the calibration position.
    path = other / 'v4_non_looming.json'
    if not path.exists():
        rows = {}
        for size in R.STATIC_DEG:
            retinas = placed(R.sequence([math.radians(size)] * R.STATIC_TICKS, dt))
            rows['static_%g' % size] = [len(R.run_trial(session, retinas, seed)) for seed in VALIDATION_SEEDS]
        _, pre, _, thetas, _ = R.looming(0.040, dt, 10.0, 90.0, 0.0, tail_s=0.0)
        receding = thetas[pre:][::-1] + [math.radians(10.0)] * int(round(R.PRE_S / dt))
        retinas = placed(R.sequence([receding[0]] * int(round(R.PRE_S / dt)) + receding, dt))
        rows['receding_lv40'] = [len(R.run_trial(session, retinas, seed)) for seed in VALIDATION_SEEDS]
        path.write_text(json.dumps(rows) + '\n', encoding='utf-8')
        print('V4 done', flush=True)
    # V8b: the calibration stimulus mirrored, azimuth +50 and -50 deg.
    path = other / 'v8b_mirrored.json'
    if not path.exists():
        goal = targets(V8B_LV_MS)
        rows = {}
        for lv_ms in V8B_LV_MS:
            for side, az in (('right', ACHE_AZIMUTH_DEG), ('left', -ACHE_AZIMUTH_DEG)):
                rows['%d_%s' % (lv_ms, side)] = timed_trials(
                    session, lv_ms / 1000.0, 10.0, 90.0, goal[lv_ms] + R.WINDOW_AFTER_TARGET_S,
                    VALIDATION_SEEDS, dt, azimuth_deg=az)
            print('V8b lv %d ms done' % lv_ms, flush=True)
        path.write_text(json.dumps(rows) + '\n', encoding='utf-8')
    session.close()


def d2():
    """D2: the V6a threat matrix with lplc2_min_edge_speed_deg_s = 1.0 (descriptive only).

    tools/m3_2_threat_matrix.py runs it unchanged as its candidate arm, on the v30 configuration
    with that one value changed, so the decoder policy comes from policy_from_source instead of a
    record."""
    import tools.m3_2_threat_matrix as TM
    from game.session import Session
    config = copy.deepcopy(validation_config())
    config['encoder']['retinotopic']['lplc2_min_edge_speed_deg_s'] = D2_MIN_EDGE_SPEED_DEG_S
    encoder_feature_model(config)
    saved = TM.OUT, TM.arm_config, TM.Session
    TM.OUT = OUT / 'd2_threat_matrix'
    TM.arm_config = lambda arm: config
    TM.Session = lambda cfg, **kwargs: Session(cfg, policy=candidate_policy(cfg), **kwargs)
    try:
        TM.run('candidate')
    finally:
        TM.OUT, TM.arm_config, TM.Session = saved


def validation_report():
    saved = (R.OUT, R.START_LV_MS, R.START_DEG)
    R.OUT, R.START_LV_MS, R.START_DEG = OUT, START_LV_MS, START_DEG
    try:
        out = R.validation_report()
    finally:
        R.OUT, R.START_LV_MS, R.START_DEG = saved
    per = out['V1']['per_condition']
    out['V8a'] = {}
    for lv in M.LV_MS:
        right, left = per['%d right' % lv], per['%d left' % lv]
        diff = right['escaped'] / right['trials'] - left['escaped'] / left['trials']
        out['V8a'][lv] = {'right': right['escaped'], 'left': left['escaped'], 'trials': right['trials'],
                          'difference': diff, 'pass': abs(diff) <= SYMMETRY_TOLERANCE}
    v8b = json.loads((OUT / 'v2_v4' / 'v8b_mirrored.json').read_text(encoding='utf-8'))
    out['V8b'] = {}
    for lv in V8B_LV_MS:
        r, l = v8b['%d_right' % lv], v8b['%d_left' % lv]
        diff = sum(t['escaped'] for t in r) / len(r) - sum(t['escaped'] for t in l) / len(l)
        out['V8b'][lv] = {'right': sum(t['escaped'] for t in r), 'left': sum(t['escaped'] for t in l),
                          'trials': len(r), 'difference': diff, 'pass': abs(diff) <= SYMMETRY_TOLERANCE}
    out['D1'] = {}
    for p in sorted((OUT / 'd1').glob('lv*.json')):
        d = json.loads(p.read_text(encoding='utf-8'))
        if d['azimuth'] in ('front', 'rear'):
            out['D1']['%d %s' % (d['lv_ms'], d['azimuth'])] = {
                k: float(np.mean([s[k] for s in d['spikes']])) for k in d['spikes'][0]}
    return out


def report():
    out = {'calibration': calibration_choice()}
    if (OUT / 'v1' / 'escape' / 'provenance.json').exists():
        out['validation'] = validation_report()
    (OUT / 'report.json').write_text(json.dumps(out, indent=1, default=str) + '\n', encoding='utf-8')
    c = out['calibration']
    print('calibration: chosen scale %s V/mV' % c['chosen_scale_volts_per_mv'])
    for r in c['grid']:
        per = ' | '.join('%s ms %.2f %s' % (lv, p['fraction'], '-' if p['median_t_ms'] is None
                                             else '%+.0f/%+.0f ms' % (p['median_t_ms'], p['target_ms']))
                         for lv, p in r['per_lv'].items())
        print('  %6g %s loss %s | %s' % (r['scale_volts_per_mv'], 'ok' if r['admissible'] else '--',
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
        for key in ('V2', 'V3', 'V4', 'V5', 'V8a', 'V8b', 'D1'):
            print(key + ':', v[key])


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('mode', choices=('calibrate', 'validate', 'd2', 'report'))
    parser.add_argument('--lane', type=int, default=0)
    parser.add_argument('--lanes', type=int, default=1)
    args = parser.parse_args()
    if args.mode == 'calibrate':
        calibrate(args.lane, args.lanes)
    else:
        {'validate': validate, 'd2': d2, 'report': report}[args.mode]()


if __name__ == '__main__':
    main()
