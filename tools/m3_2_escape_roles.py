"""M3.2: calibration and validation of the ache2019_v1 encoder (game/M3_2_ESCAPE_FEATURE_ROLES_DESIGN.md).

Protocol-E harness of tools/m3_0_scorecard.py: a fixed fly whose Retina is replaced once per
tick by a synthetic looming disk; the encoder, MaleCNS, DNp01 and the runtime decoder run
unchanged. Outputs go to artifacts/m3_2/ (git-ignored), one file per unit of work, with the
M3.0 provenance guard, so an interrupted run resumes where it stopped.

    python tools/m3_2_escape_roles.py calibrate   # section 4: the scale grid on seeds 600001-600024
    python tools/m3_2_escape_roles.py validate    # section 5: V1-V5, with the scale from the ROOM config
    python tools/m3_2_escape_roles.py report      # calibration choice and V1-V5 results

Calibration builds each grid configuration in memory from the ROOM configuration and runs it
with the decoder built from that configuration's own transfer record; only the encoder's
feature model and scale differ. Validation runs the ROOM configuration as the runtime loads it.
"""
from __future__ import annotations

import argparse
import copy
import json
import math
import os
from pathlib import Path
import statistics
import sys

os.environ.setdefault('NUMBA_NUM_THREADS', '4')
os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from game.fly import build_brain  # noqa: E402
from game.perception import FEATURE_MODEL_ACHE2019, Retina, encoder_feature_model  # noqa: E402
from game.session import Session, build_policy, load_config  # noqa: E402
import tools.m3_0_scorecard as M  # noqa: E402
import tools.m3_2_ache_targets as T  # noqa: E402
import tools.n4b6_protocol as P  # noqa: E402

OUT = ROOT / 'artifacts/m3_2'
CONFIG = ROOT / 'game_room_config.json'
CALIBRATION_SEEDS = tuple(range(600001, 600025))
GRID = tuple(round(0.04 + 0.01 * k, 2) for k in range(27))          # 0.04 ... 0.30 V/mV
ADMISSIBLE_FRACTION = 0.5
WINDOW_AFTER_TARGET_S = 0.3
RIGHT = M.AZIMUTHS['right']
START_LV_MS, START_DEG = (40, 80), (5.0, 10.0, 20.0)
START_SPREAD_DEG = 10.0
HELD_OUT_TOLERANCE_MS = 30.0
STATIC_DEG, STATIC_TICKS = (10.0, 30.0, 60.0, 90.0), 100
PRE_S = 1.0


# ------------------------------------------------------------------------------ stimuli ---
def looming(lv, dt, start_deg, stop_deg=None, end_after_collision_s=M.WINDOW_AFTER_S, tail_s=M.TAIL_S,
            azimuth=RIGHT):
    """Per-tick Retinas of a constant-l/v disk from start_deg, then held at stop_deg (or 180).

    Returns the Retinas, the onset index, the expansion time t0 to collision, the per-tick sizes
    and the last index of the escape window (end_after_collision_s after collision)."""
    t0 = lv / math.tan(math.radians(start_deg) / 2)
    stop = math.pi if stop_deg is None else math.radians(stop_deg)
    pre = int(round(PRE_S / dt))
    n = int(math.ceil((t0 + end_after_collision_s) / dt))
    thetas = [math.radians(start_deg)] * pre
    for k in range(1, n + 1):
        remaining = t0 - k * dt
        thetas.append(stop if remaining <= 0 else min(stop, 2 * math.atan(lv / remaining)))
    thetas += [thetas[-1]] * int(round(tail_s / dt))
    retinas, previous = [], thetas[0]
    for theta in thetas:
        retinas.append(Retina(theta=theta, theta_dot=(theta - previous) / dt, azimuth=azimuth))
        previous = theta
    last = pre + int(math.floor((t0 + end_after_collision_s) / dt + 1e-9)) - 1
    return retinas, pre, t0, thetas, last


def sequence(thetas, dt, azimuth=RIGHT):
    retinas, previous = [], thetas[0]
    for theta in thetas:
        retinas.append(Retina(theta=theta, theta_dot=(theta - previous) / dt, azimuth=azimuth))
        previous = theta
    return retinas


# ------------------------------------------------------------------------------ harness ---
def fixed_fly_session(config, brain=None, policy=None):
    session = Session(config, brain=brain, policy=policy, root=ROOT, ecology_enabled=False)
    session.world.collisions_enabled = False
    session.world.fly_motion_enabled = False
    return session


def run_trial(session, retinas, seed):
    """All escape ticks of one trial, as (index, forward, lateral)."""
    session.reset(seed)
    fly = session.world.fly
    fly.vx = fly.vy = 0.0                    # fixed-fly-v2: the velocity stays zero
    pose = (fly.x, fly.y, fly.heading)
    feed = iter(retinas)
    session.projector.project = lambda world, feed=feed: next(feed)
    escapes = []
    try:
        for i in range(len(retinas)):
            session.tick()
            a = session.fly_loop.last_action
            if a.escape:
                escapes.append((i, float(a.forward), float(a.lateral)))
            if (fly.x, fly.y, fly.heading) != pose:
                raise RuntimeError('the fly moved')
    finally:
        del session.projector.project          # restore the class method
    return escapes


def timed_trials(session, lv, start_deg, stop_deg, end_after_collision_s, seeds, dt):
    """First escape in the window, as time relative to collision (s) and size (deg)."""
    retinas, pre, t0, thetas, last = looming(lv, dt, start_deg, stop_deg, end_after_collision_s)
    rows = []
    for seed in seeds:
        escapes = run_trial(session, retinas, seed)
        first = next((e for e in escapes if pre <= e[0] <= last), None)
        row = {'seed': seed, 'pre_stimulus_escapes': sum(1 for e in escapes if e[0] < pre),
               'escaped': first is not None}
        if first is not None:
            row.update({'tick': first[0], 't_rel_s': (first[0] - pre + 1) * dt - t0,
                        'theta_deg': math.degrees(thetas[first[0]])})
        rows.append(row)
    return rows


def median(values):
    values = list(values)
    return statistics.median(values) if values else None


# --------------------------------------------------------------------------- calibration ---
def base_config():
    return load_config(CONFIG)


def grid_config(base, scale):
    c = copy.deepcopy(base)
    c['encoder']['feature_model'] = FEATURE_MODEL_ACHE2019
    c['encoder']['ache2019'] = {'scale_volts_per_mv': scale}
    encoder_feature_model(c)
    return c


def calibrate():
    base = base_config()
    dt = float(base['sim']['tick_seconds'])
    targets = {r['lv_ms']: r['peak_time_ms'] / 1000.0 for r in T.targets(T.CALIBRATION_LV_MS)}
    policy, _ = build_policy(base, ROOT)          # the decoder exactly as the runtime builds it
    brain = build_brain(base, ROOT)
    out = OUT / 'calibration'
    M.check_provenance(out, 's*.json')
    for scale in GRID:
        path = out / ('s%.2f.json' % scale)
        if path.exists():
            continue
        session = fixed_fly_session(grid_config(base, scale), brain=brain, policy=policy)
        result = {'scale_volts_per_mv': scale, 'per_lv': {}}
        for lv_ms in T.CALIBRATION_LV_MS:
            rows = timed_trials(session, lv_ms / 1000.0, 10.0, 90.0,
                                targets[lv_ms] + WINDOW_AFTER_TARGET_S, CALIBRATION_SEEDS, dt)
            result['per_lv'][str(lv_ms)] = rows
        path.write_text(json.dumps(result) + '\n', encoding='utf-8')
        summary = ', '.join('%s ms %d/%d' % (lv, sum(r['escaped'] for r in rows), len(rows))
                            for lv, rows in result['per_lv'].items())
        print('scale %.2f: %s' % (scale, summary), flush=True)


def calibration_choice():
    out = OUT / 'calibration'
    M.recorded_provenance(out)
    targets = {r['lv_ms']: r['peak_time_ms'] / 1000.0 for r in T.targets(T.CALIBRATION_LV_MS)}
    rows = []
    for scale in GRID:
        path = out / ('s%.2f.json' % scale)
        if not path.exists():
            raise SystemExit('calibration is incomplete: %s is missing' % path.name)
        data = json.loads(path.read_text(encoding='utf-8'))
        per = {}
        for lv_ms in T.CALIBRATION_LV_MS:
            trials = data['per_lv'][str(lv_ms)]
            if len(trials) != len(CALIBRATION_SEEDS):
                raise SystemExit('%s has %d trials at %d ms' % (path.name, len(trials), lv_ms))
            esc = [t for t in trials if t['escaped']]
            per[lv_ms] = {'fraction': len(esc) / len(trials),
                          'median_t_ms': None if not esc else 1000 * median(t['t_rel_s'] for t in esc),
                          'median_theta_deg': None if not esc else median(t['theta_deg'] for t in esc),
                          'target_ms': 1000 * targets[lv_ms]}
        admissible = all(p['fraction'] >= ADMISSIBLE_FRACTION for p in per.values())
        loss = (sum((p['median_t_ms'] - p['target_ms']) ** 2 for p in per.values())
                if admissible else None)
        rows.append({'scale_volts_per_mv': scale, 'admissible': admissible,
                     'loss_ms2': loss, 'per_lv': per})
    candidates = [r for r in rows if r['admissible']]
    chosen = min(candidates, key=lambda r: (r['loss_ms2'], r['scale_volts_per_mv'])) if candidates else None
    return {'grid': rows, 'chosen_scale_volts_per_mv': None if chosen is None else chosen['scale_volts_per_mv'],
            'stop_rule_triggered': chosen is None}


# ---------------------------------------------------------------------------- validation ---
def validation_config():
    c = base_config()
    if encoder_feature_model(c) != FEATURE_MODEL_ACHE2019:
        raise SystemExit('the ROOM configuration does not use the ache2019_v1 encoder yet')
    return c


def validate():
    cfg = validation_config()
    dt = float(cfg['sim']['tick_seconds'])
    session = fixed_fly_session(cfg)              # the runtime path: decoder from the v28 record
    # V1: the M3.0 protocol E, unchanged, in M3.0's file format.
    v1 = OUT / 'v1' / 'escape'
    M.check_provenance(v1, '*.json')
    for lv_ms in M.LV_MS:
        lv = lv_ms / 1000.0
        for name, azimuth in M.AZIMUTHS.items():
            path = v1 / ('lv%03d_%s.json' % (lv_ms, name))
            if path.exists():
                continue
            retinas, pre, t0, thetas = M.stimulus(lv, azimuth, dt)
            last = pre + int(math.floor((t0 + M.WINDOW_AFTER_S) / dt + 1e-9)) - 1
            trials = []
            for seed in P.SEEDS:
                escapes = run_trial(session, retinas, seed)
                first = next((e for e in escapes if pre <= e[0] <= last), None)
                trial = {'seed': seed, 'pre_stimulus_escapes': sum(1 for e in escapes if e[0] < pre),
                         'escaped': first is not None}
                if first is not None:
                    i, forward, lateral = first
                    trial.update({'tick': i, 't_before': t0 - (i - pre + 1) * dt,
                                  'theta_deg': math.degrees(thetas[i]),
                                  'direction_deg': math.degrees(math.atan2(lateral, forward))})
                trials.append(trial)
            path.write_text(json.dumps({'lv_ms': lv_ms, 'azimuth': name, 'azimuth_value': azimuth,
                                        't0': t0, 'onset_index': pre, 'last_window_index': last,
                                        'trials': trials}, indent=1) + '\n', encoding='utf-8')
            print('V1 lv %d ms %s: %d of %d escaped' % (lv_ms, name, sum(t['escaped'] for t in trials),
                                                       len(trials)), flush=True)
    other = OUT / 'v2_v4'
    M.check_provenance(other, '*.json')
    # V2: start-size invariance, to collision as in M3.0.
    path = other / 'v2_start_size.json'
    if not path.exists():
        rows = {}
        for lv_ms in START_LV_MS:
            for start in START_DEG:
                rows['%d_%g' % (lv_ms, start)] = timed_trials(
                    session, lv_ms / 1000.0, start, None, M.WINDOW_AFTER_S, CALIBRATION_SEEDS, dt)
                print('V2 lv %d ms start %g deg done' % (lv_ms, start), flush=True)
        path.write_text(json.dumps(rows) + '\n', encoding='utf-8')
    # V3: held-out l/v on the calibration stimulus.
    path = other / 'v3_held_out.json'
    if not path.exists():
        targets = {r['lv_ms']: r['peak_time_ms'] / 1000.0 for r in T.targets(T.HELD_OUT_LV_MS)}
        rows = {}
        for lv_ms in T.HELD_OUT_LV_MS:
            rows[str(lv_ms)] = timed_trials(session, lv_ms / 1000.0, 10.0, 90.0,
                                            targets[lv_ms] + WINDOW_AFTER_TARGET_S, CALIBRATION_SEEDS, dt)
            print('V3 lv %d ms done' % lv_ms, flush=True)
        path.write_text(json.dumps(rows) + '\n', encoding='utf-8')
    # V4: static disks and a receding disk.
    path = other / 'v4_non_looming.json'
    if not path.exists():
        rows = {}
        for size in STATIC_DEG:
            retinas = sequence([math.radians(size)] * STATIC_TICKS, dt)
            rows['static_%g' % size] = [len(run_trial(session, retinas, seed)) for seed in CALIBRATION_SEEDS]
        _, pre, _, thetas, _ = looming(0.040, dt, 10.0, 90.0, 0.0, tail_s=0.0)
        receding = thetas[pre:][::-1] + [math.radians(10.0)] * int(round(PRE_S / dt))
        retinas = sequence([receding[0]] * int(round(PRE_S / dt)) + receding, dt)
        rows['receding_lv40'] = [len(run_trial(session, retinas, seed)) for seed in CALIBRATION_SEEDS]
        path.write_text(json.dumps(rows) + '\n', encoding='utf-8')
        print('V4 done', flush=True)
    session.close()


def validation_report():
    out = {}
    M.OUT = OUT / 'v1'
    v1 = M.escape_report()
    out['V1'] = v1
    out['V5'] = v1['E6']
    other = OUT / 'v2_v4'
    out['provenance_v2_v4'] = M.recorded_provenance(other)
    v2 = json.loads((other / 'v2_start_size.json').read_text(encoding='utf-8'))
    out['V2'] = {}
    for lv_ms in START_LV_MS:
        medians = {}
        for start in START_DEG:
            esc = [t for t in v2['%d_%g' % (lv_ms, start)] if t['escaped']]
            medians[start] = median(t['theta_deg'] for t in esc)
        values = [m for m in medians.values() if m is not None]
        spread = (max(values) - min(values)) if len(values) == len(START_DEG) else None
        out['V2'][lv_ms] = {'median_theta_by_start_deg': medians, 'spread_deg': spread,
                            'pass': spread is not None and spread <= START_SPREAD_DEG}
    v3 = json.loads((other / 'v3_held_out.json').read_text(encoding='utf-8'))
    targets = {r['lv_ms']: r['peak_time_ms'] for r in T.targets(T.HELD_OUT_LV_MS)}
    out['V3'] = {}
    for lv_ms in T.HELD_OUT_LV_MS:
        esc = [t for t in v3[str(lv_ms)] if t['escaped']]
        m = None if not esc else 1000 * median(t['t_rel_s'] for t in esc)
        out['V3'][lv_ms] = {'escaped': len(esc), 'trials': len(v3[str(lv_ms)]), 'median_t_ms': m,
                            'target_ms': targets[lv_ms],
                            'pass': m is not None and abs(m - targets[lv_ms]) <= HELD_OUT_TOLERANCE_MS}
    v4 = json.loads((other / 'v4_non_looming.json').read_text(encoding='utf-8'))
    total = sum(sum(v) for v in v4.values())
    out['V4'] = {'escapes_by_condition': {k: sum(v) for k, v in v4.items()},
                 'trials': sum(len(v) for v in v4.values()), 'total_escapes': total, 'pass': total <= 1}
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
        print('  %.2f %s loss %s | %s' % (r['scale_volts_per_mv'], 'ok' if r['admissible'] else '--',
                                          '-' if r['loss_ms2'] is None else '%.0f' % r['loss_ms2'], per))
    if 'validation' in out:
        v = out['validation']
        e = v['V1']
        print('V1: E1 %.2f (%s); E2 threshold %s deg, alpha %s, delta %s ms (%s); E3 %s' % (
            e['E1']['value'], e['E1']['class'], e['E2']['theta_threshold_deg'], e['E2']['alpha'],
            e['E2']['delta_ms'], e['E2']['class'], e['E3']['before_collision_fraction_lv10']))
        print('V1 E4:', {k: (round(x['circular_mean_deg'], 1) if x['circular_mean_deg'] is not None else None,
                             x['class']) for k, x in e['E4'].items()})
        print('V2:', v['V2'])
        print('V3:', v['V3'])
        print('V4:', v['V4'])
        print('V5:', v['V5'])


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('mode', choices=('calibrate', 'validate', 'report'))
    {'calibrate': calibrate, 'validate': validate, 'report': report}[parser.parse_args().mode]()


if __name__ == '__main__':
    main()
