"""M3.1 research: trace the M3.0 protocol-E escape decision through every stage.

Read-only diagnosis. No runtime file changes. It replays the M3.0 synthetic looming disk
(tools/m3_0_scorecard.py) at the right azimuth and logs, per tick:
- the Retina (theta, theta_dot);
- the encoder's injected voltage per channel (LPLC2 = loom, LC4 = threat);
- how many of the driven LPLC2 and LC4 cells spiked;
- DNp01 spikes and the decoder's trigger path.

The variants exist only inside this tool, to attribute the decision to an input channel:
- runtime: the encoder unchanged;
- no_lc4: the LC4 injection is dropped;
- no_lplc2: the LPLC2 injection is dropped.

Two further read-only probes:
- onset: the runtime encoder with the disk starting at 5, 10, 20 or 30 degrees. If the decision
  followed an angular-size threshold, the size at escape would not depend on the start size.
- dose: the encoder is bypassed and a constant voltage is added every tick to all driven
  right-side LPLC2 or LC4 cells. This measures the frozen chain downstream of the encoder
  (MaleCNS, DNp01 and the decoder) as a function of input voltage.

    python tools/m3_1_escape_trace.py run       # writes artifacts/m3_1/*.json
    python tools/m3_1_escape_trace.py report    # prints the summary tables
"""
from __future__ import annotations

import argparse
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

import numpy as np  # noqa: E402

from game.perception import Retina  # noqa: E402
from game.session import Session  # noqa: E402
import tools.m3_0_scorecard as M  # noqa: E402
import tools.n4b6_protocol as P  # noqa: E402

OUT = ROOT / 'artifacts/m3_1'
SEEDS = P.SEEDS[:12]
VARIANTS = ('runtime', 'no_lc4', 'no_lplc2')
AZIMUTH = M.AZIMUTHS['right']
ONSET_LV_MS = (40, 80)
ONSET_THETA0_DEG = (5.0, 10.0, 20.0, 30.0)
DOSE_VOLTS = (0.02, 0.04, 0.06, 0.08, 0.12, 0.16, 0.2, 0.24, 0.28, 0.32, 0.4, 0.6, 0.8)
DOSE_PRE_TICKS, DOSE_TICKS = 25, 50


def drop_channel(encoder, channel):
    """Wrap encoder.inject so that the given channel's cells receive nothing."""
    original = encoder.inject

    def inject(retina):
        cells = encoder._fd.cells[channel]
        return [(c, a) for c, a in original(retina) if not any(c is cells[s] for s in 'LR')]
    return inject


def first_escape(session, retinas, pre, last):
    """Run one trial on a synthetic Retina feed; return the first escape index in the window."""
    feed = iter(retinas)
    session.projector.project = lambda world, feed=feed: next(feed)
    first = None
    for i in range(len(retinas)):
        session.tick()
        if first is None and pre <= i <= last and session.fly_loop.last_action.escape:
            first = i
    del session.projector.project
    return first


def run_onset(session, dt):
    path = OUT / 'onset.json'
    if path.exists():
        return
    rows = []
    for lv_ms in ONSET_LV_MS:
        for theta0_deg in ONSET_THETA0_DEG:
            M.THETA0 = math.radians(theta0_deg)
            retinas, pre, t0, thetas = M.stimulus(lv_ms / 1000.0, AZIMUTH, dt)
            last = pre + int(math.floor((t0 + M.WINDOW_AFTER_S) / dt + 1e-9)) - 1
            for seed in SEEDS:
                session.reset(seed)
                session.world.fly.vx = session.world.fly.vy = 0.0
                e = first_escape(session, retinas, pre, last)
                rows.append({'lv_ms': lv_ms, 'theta0_deg': theta0_deg, 'seed': seed,
                             'ticks_after_onset': None if e is None else e - pre + 1,
                             'theta_deg': None if e is None else math.degrees(thetas[e])})
            print('onset lv %d ms theta0 %.0f deg done' % (lv_ms, theta0_deg), flush=True)
    M.THETA0 = math.radians(10.0)
    path.write_text(json.dumps(rows) + '\n', encoding='utf-8')


def run_dose(session):
    path = OUT / 'dose.json'
    if path.exists():
        return
    encoder = session.fly_loop.encoder
    static = Retina(theta=math.radians(10.0), theta_dot=0.0, azimuth=AZIMUTH)
    rows = []
    for channel, label in (('loom', 'LPLC2'), ('threat', 'LC4')):
        cells = encoder._fd.cells[channel]['R']
        for volts in DOSE_VOLTS:
            for seed in SEEDS:
                session.reset(seed)
                session.world.fly.vx = session.world.fly.vy = 0.0
                state = {'tick': 0}

                def inject(retina, cells=cells, volts=volts, state=state):
                    state['tick'] += 1
                    return [(cells, volts)] if state['tick'] > DOSE_PRE_TICKS else []
                encoder.inject = inject
                retinas = [static] * (DOSE_PRE_TICKS + DOSE_TICKS)
                e = first_escape(session, retinas, DOSE_PRE_TICKS, len(retinas) - 1)
                del encoder.inject
                rows.append({'channel': label, 'volts': volts, 'seed': seed,
                             'ticks_after_onset': None if e is None else e - DOSE_PRE_TICKS + 1})
            print('dose %s %.3f V done' % (label, volts), flush=True)
    path.write_text(json.dumps(rows) + '\n', encoding='utf-8')


def run():
    cfg = M.config()
    dt = float(cfg['sim']['tick_seconds'])
    session = Session(cfg, root=ROOT, ecology_enabled=False)
    session.world.collisions_enabled = False
    session.world.fly_motion_enabled = False
    loop, brain = session.fly_loop, session.brain
    encoder = loop.encoder
    dnp01 = {s: np.asarray(brain.groups['escape_' + s]) for s in 'LR'}
    driven = {(ch, s): encoder._fd.cells[ch][s] for ch in ('loom', 'threat') for s in 'LR'}
    OUT.mkdir(parents=True, exist_ok=True)
    for variant in VARIANTS:
        path = OUT / ('trace_%s.json' % variant)
        if path.exists():
            continue
        if variant == 'no_lc4':
            encoder.inject = drop_channel(encoder, 'threat')
        elif variant == 'no_lplc2':
            encoder.inject = drop_channel(encoder, 'loom')
        conditions = []
        for lv_ms in M.LV_MS:
            lv = lv_ms / 1000.0
            retinas, pre, t0, thetas = M.stimulus(lv, AZIMUTH, dt)
            last = pre + int(math.floor((t0 + M.WINDOW_AFTER_S) / dt + 1e-9)) - 1
            trials = []
            for seed in SEEDS:
                session.reset(seed)
                session.world.fly.vx = session.world.fly.vy = 0.0
                feed = iter(retinas)
                session.projector.project = lambda world, feed=feed: next(feed)
                ticks = []
                for i, r in enumerate(retinas):
                    session.tick()
                    fired = np.asarray(brain.fired)
                    drive = encoder.last_drive
                    if variant == 'no_lc4':
                        drive = dict(drive, threatL=0.0, threatR=0.0)
                    elif variant == 'no_lplc2':
                        drive = dict(drive, loomL=0.0, loomR=0.0)
                    action = loop.last_action
                    crit = loop.policy.criterion_diagnostics()
                    ticks.append({
                        'i': i, 'theta_deg': math.degrees(r.theta),
                        'theta_dot_deg_s': math.degrees(r.theta_dot),
                        'loom_R': drive['loomR'], 'threat_R': drive['threatR'],
                        'lplc2_R': int(np.isin(fired, driven[('loom', 'R')]).sum()),
                        'lc4_R': int(np.isin(fired, driven[('threat', 'R')]).sum()),
                        'dnp01_L_spike': bool(np.isin(fired, dnp01['L']).any()),
                        'dnp01_R_spike': bool(np.isin(fired, dnp01['R']).any()),
                        'dnp01_L_trace': loop.last_motor.dnp01_left,
                        'dnp01_R_trace': loop.last_motor.dnp01_right,
                        'escape': bool(action.escape),
                        'path': crit['escape_trigger_paths'] if action.escape else ''})
                del session.projector.project
                first = next((t for t in ticks if pre <= t['i'] <= last and t['escape']), None)
                trials.append({'seed': seed, 'first_escape_index': None if first is None else first['i'],
                               'ticks': ticks})
            conditions.append({'lv_ms': lv_ms, 't0': t0, 'onset_index': pre, 'last_window_index': last,
                               'n_lplc2_R': int(driven[('loom', 'R')].size),
                               'n_lc4_R': int(driven[('threat', 'R')].size), 'trials': trials})
            print('%s lv %d ms: %d of %d escaped' % (
                variant, lv_ms, sum(t['first_escape_index'] is not None for t in trials), len(trials)),
                flush=True)
        if variant != 'runtime':
            del encoder.inject                     # restore the class method
        path.write_text(json.dumps({'variant': variant, 'azimuth': AZIMUTH, 'seeds': list(SEEDS),
                                    'conditions': conditions}) + '\n', encoding='utf-8')
    run_onset(session, dt)
    run_dose(session)
    session.close()


def median(values):
    values = [v for v in values if v is not None]
    return statistics.median(values) if values else None


def fmt(value, spec='%.1f'):
    return '-' if value is None else spec % value


def report():
    dt = 0.02
    for variant in VARIANTS:
        data = json.loads((OUT / ('trace_%s.json' % variant)).read_text(encoding='utf-8'))
        print('\n== %s' % variant)
        print('l/v | escaped | first LPLC2 spike | first LC4 spike | first DNp01-R spike | escape '
              '| size at escape | paths')
        for c in data['conditions']:
            pre, last = c['onset_index'], c['last_window_index']
            first_lplc2, first_lc4, first_dn, esc, size, paths = [], [], [], [], [], {}
            for trial in c['trials']:
                window = [t for t in trial['ticks'] if pre <= t['i'] <= last]
                first_lplc2.append(next((t['i'] - pre + 1 for t in window if t['lplc2_R'] > 0), None))
                first_lc4.append(next((t['i'] - pre + 1 for t in window if t['lc4_R'] > 0), None))
                first_dn.append(next((t['i'] - pre + 1 for t in window if t['dnp01_R_spike']), None))
                e = trial['first_escape_index']
                if e is not None:
                    tick = trial['ticks'][e]
                    esc.append(e - pre + 1)
                    size.append(tick['theta_deg'])
                    paths[tick['path']] = paths.get(tick['path'], 0) + 1
            print('%3d ms | %2d/%d | tick %s | tick %s | tick %s | tick %s | %s deg | %s' % (
                c['lv_ms'], len(esc), len(c['trials']), fmt(median(first_lplc2)), fmt(median(first_lc4)),
                fmt(median(first_dn)), fmt(median(esc)), fmt(median(size)), paths))
        if variant != 'runtime':
            continue
        print('\nPer-tick medians over seeds from onset (runtime), l/v 40 and 80 ms:')
        for c in data['conditions']:
            if c['lv_ms'] not in (40, 80):
                continue
            pre = c['onset_index']
            print('l/v %d ms (LPLC2 cells %d, LC4 cells %d per side)' % (c['lv_ms'], c['n_lplc2_R'],
                                                                         c['n_lc4_R']))
            print('  k | theta | theta_dot | loom V | threat V | LPLC2 spikes | LC4 spikes | DNp01-R spike frac')
            for k in range(-2, 14):
                rows = [trial['ticks'][pre + k - 1] for trial in c['trials']]
                print('  %2d | %5.1f | %6.1f | %.3f | %.3f | %5.1f | %5.1f | %.2f' % (
                    k, rows[0]['theta_deg'], rows[0]['theta_dot_deg_s'], rows[0]['loom_R'],
                    rows[0]['threat_R'], statistics.median(r['lplc2_R'] for r in rows),
                    statistics.median(r['lc4_R'] for r in rows),
                    sum(r['dnp01_R_spike'] for r in rows) / len(rows)))
    print('\nTick k = 1 is the first expanding Retina. dt = %.0f ms.' % (dt * 1000))

    onset = json.loads((OUT / 'onset.json').read_text(encoding='utf-8'))
    print('\n== onset: runtime encoder, start size varied')
    print('l/v | start | escaped | ticks after onset | size at escape (median, min-max)')
    for lv_ms in ONSET_LV_MS:
        for theta0 in ONSET_THETA0_DEG:
            rows = [r for r in onset if r['lv_ms'] == lv_ms and r['theta0_deg'] == theta0]
            hit = [r for r in rows if r['theta_deg'] is not None]
            sizes = [r['theta_deg'] for r in hit]
            print('%3d ms | %4.0f deg | %2d/%d | %s | %s deg (%s-%s)' % (
                lv_ms, theta0, len(hit), len(rows), fmt(median(r['ticks_after_onset'] for r in hit)),
                fmt(median(sizes)), fmt(min(sizes) if sizes else None), fmt(max(sizes) if sizes else None)))

    dose = json.loads((OUT / 'dose.json').read_text(encoding='utf-8'))
    print('\n== dose: constant voltage on all driven right-side cells of one channel, %d ticks'
          % DOSE_TICKS)
    print('channel | volts | escaped | ticks to escape (median, min-max)')
    for label in ('LPLC2', 'LC4'):
        for volts in DOSE_VOLTS:
            rows = [r for r in dose if r['channel'] == label and r['volts'] == volts]
            ticks = [r['ticks_after_onset'] for r in rows if r['ticks_after_onset'] is not None]
            print('%-5s | %.3f | %2d/%d | %s (%s-%s)' % (
                label, volts, len(ticks), len(rows), fmt(median(ticks)),
                fmt(min(ticks) if ticks else None, '%d'), fmt(max(ticks) if ticks else None, '%d')))


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('mode', choices=('run', 'report'))
    args = parser.parse_args()
    {'run': run, 'report': report}[args.mode]()


if __name__ == '__main__':
    main()
