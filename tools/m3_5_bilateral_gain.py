"""M3.5 research: how strong a commissural pathway the giant fibers would need (read-only).

Exploratory. Nothing in the runtime, the configuration or data/ changes: the gain is applied
to the in-memory weights of one research process only.

**The real fly.** Each giant fiber responds to looms seen by the contralateral eye like
ipsilateral ones: "We found the GF peak response magnitude was not significantly different
across stimulus locations" and "no significant difference in the peak latency" (Jang et al.
2023, looms at -45°, 0° and +45° on the horizon).

**The frozen network.** game/M3_5_STRIKE_ESCAPE_RESEARCH.md (section 8) found:
- each DNp01 receives 1-5 % of its ipsilateral input from the contralateral eye;
- the input comes through three chemical carrier types, each fed by its own eye and projecting
  to the opposite DNp01: PVLP151, AMMC-A1 (the GCI) and DNp11.
Section 15 found that frontal looms are decided 40-100 ms later than looms at 30-50°.

**This tool.**
- **The gain.** It multiplies the weights from those carriers onto the opposite DNp01 by a gain
  g: 1 (v30), 5, 10, 20 or 40.
- **Looms.** V2's loom from 10° at l/v 40 and 80 ms, decided by the v30 doublet decoder.
  - Positions: azimuth 0°, +45° and -45° on the horizon (the Jang et al. geometry); 90°/0°
    (V1/V2); 50°/11° (calibration); 90°/70° (a high paddle); 180°/50° (rear, elevated).
  - Recorded per tick: both DNp01s' spikes and synaptic input.
  - Seeds 970701-970724.
- **Rest.** A static 10° disk for 10 s, seeds 970801-970824. It counts the runtime decisions
  and DNp01's spontaneous spikes.

Outputs go to artifacts/m3_5/bilateral_gain/ (git-ignored). Needs scipy and
data/receptive_fields_v1.npz.

    NUMBA_NUM_THREADS=1 python tools/m3_5_bilateral_gain.py run --gain G     (G = 1, 5, 10, 20, 40)
    python tools/m3_5_bilateral_gain.py summary
"""
from __future__ import annotations

import argparse
import json
import math
import os
from pathlib import Path
import statistics
import sys

os.environ.setdefault('NUMBA_NUM_THREADS', '1')
os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import numpy as np  # noqa: E402

import tools.m3_0_scorecard as M  # noqa: E402
import tools.m3_2_escape_roles as R  # noqa: E402
import tools.m3_4_retinotopic as T  # noqa: E402
import tools.m3_5_side_balance as B  # noqa: E402

OUT = ROOT / 'artifacts/m3_5/bilateral_gain'
GAINS = (1.0, 5.0, 10.0, 20.0, 40.0)
CARRIERS = ('PVLP151', 'AMMC-A1', 'DNp11')
POSITIONS = {'front': (0.0, 0.0), 'right45': (45.0, 0.0), 'left45': (-45.0, 0.0), 'lateral': (90.0, 0.0),
             'calibration': (50.0, 11.0), 'high': (90.0, 70.0), 'rear50': (180.0, 50.0)}
LV_MS = (40, 80)
START_DEG = 10.0
LOOM_SEEDS = tuple(range(970701, 970725))
REST_SEEDS = tuple(range(970801, 970825))
REST_S = 10.0


def other(side):
    return 'R' if side == 'L' else 'L'


def apply_gain(brain, gain):
    """Scale carrier -> opposite DNp01 weights in the brain's in-memory CSC arrays.

    Returns the dense DNp01 rows as used after the change, and the number of entries scaled."""
    import tools.m3_4_receptive_fields as RF
    gf = {s: int(np.flatnonzero((brain.cell_type == 'DNp01') & (brain.side == s))[0]) for s in 'LR'}
    scaled = 0
    for s in 'LR':
        target = gf[other(s)]
        for c in np.flatnonzero(np.isin(brain.cell_type, CARRIERS) & (brain.side == s)):
            for e in range(brain.indptr[c], brain.indptr[c + 1]):
                if brain.indices[e] == target:
                    brain.weights[e] *= np.float32(gain)
                    scaled += 1
    W = RF.weights().tocsr()
    rows = {s: W[gf[s]].toarray().ravel().astype(np.float64) for s in 'LR'}
    for s in 'LR':
        carriers = np.flatnonzero(np.isin(brain.cell_type, CARRIERS) & (brain.side == other(s)))
        rows[s][carriers] *= gain
    return gf, rows, scaled


def record(session, retinas, seed, gf, rows):
    session.reset(seed)
    fly = session.world.fly
    fly.vx = fly.vy = 0.0
    feed = iter(retinas)
    session.projector.project = lambda world, feed=feed: next(feed)
    brain = session.brain
    original = brain.step
    ticks = []

    def step(*args, **kwargs):
        fired = original(*args, **kwargs)
        ticks.append({'spike_L': int(gf['L'] in fired), 'spike_R': int(gf['R'] in fired),
                      'input_L': float(brain.gain * rows['L'][fired].sum()),
                      'input_R': float(brain.gain * rows['R'][fired].sum())})
        return fired
    brain.step = step
    decisions = []
    try:
        for i in range(len(retinas)):
            session.tick()
            if session.fly_loop.last_action.escape:
                decisions.append(i)
    finally:
        del session.projector.project
        del brain.step
    return ticks, decisions


def run(args):
    out = OUT / ('g%02d' % args.gain)
    M.check_provenance(out, '*.json')
    T.check_fields(out)
    config, session = B.v30_session()
    gf, rows, scaled = apply_gain(session.brain, args.gain)
    print('gain %g: %d carrier -> DNp01 entries scaled' % (args.gain, scaled), flush=True)
    dt = float(config['sim']['tick_seconds'])
    for lv_ms in LV_MS:
        for name, (az, el) in POSITIONS.items():
            path = out / ('lv%03d_%s.json' % (lv_ms, name))
            if path.exists():
                continue
            retinas, pre, t0, thetas, last = R.looming(lv_ms / 1000.0, dt, START_DEG, None, M.WINDOW_AFTER_S)
            retinas = T.placed(retinas, az, el)
            trials = []
            for seed in LOOM_SEEDS:
                ticks, decisions = record(session, retinas, seed, gf, rows)
                first = next((i for i in decisions if pre <= i <= last), None)
                trials.append({'seed': seed, 'decision': first,
                               'pre_stimulus_escapes': sum(1 for i in decisions if i < pre),
                               'ticks': ticks[pre - 5:last + 1]})
            path.write_text(json.dumps({'lv_ms': lv_ms, 'position': name, 'azimuth_deg': az, 'elevation_deg': el,
                                        'onset': pre, 'last': last, 'first_recorded': pre - 5,
                                        'tau_ms': [1000 * (t0 - (i - pre + 1) * dt) for i in range(len(retinas))],
                                        'theta_deg': [math.degrees(t) for t in thetas], 'trials': trials}) + '\n',
                            encoding='utf-8')
            print('gain %g lv %d %s: %d of %d decided' % (args.gain, lv_ms, name,
                                                         sum(t['decision'] is not None for t in trials),
                                                         len(trials)), flush=True)
    path = out / 'rest.json'
    if not path.exists():
        n = int(round(REST_S / dt))
        retinas = T.placed(R.sequence([math.radians(START_DEG)] * n, dt), 90.0, 0.0)
        rest = []
        for seed in REST_SEEDS:
            ticks, decisions = record(session, retinas, seed, gf, rows)
            rest.append({'seed': seed, 'decisions': len(decisions),
                         'spikes_L': sum(t['spike_L'] for t in ticks), 'spikes_R': sum(t['spike_R'] for t in ticks)})
        path.write_text(json.dumps({'seconds': REST_S, 'trials': rest}) + '\n', encoding='utf-8')
        print('gain %g rest: %d decisions' % (args.gain, sum(t['decisions'] for t in rest)), flush=True)
    session.close()


def mean_input(d, side):
    """Mean synaptic input per recorded tick to one DNp01, over trials."""
    return np.mean([[t['input_' + side] for t in tr['ticks']] for tr in d['trials']], axis=0)


def summary(_args):
    for gain in GAINS:
        out = OUT / ('g%02d' % gain)
        if not (out / 'rest.json').exists():
            continue
        rest = json.loads((out / 'rest.json').read_text(encoding='utf-8'))
        total_s = rest['seconds'] * len(rest['trials'])
        print('== gain %g: rest %d decisions in %.0f s; DNp01 spontaneous L %.2f, R %.2f Hz' % (
            gain, sum(t['decisions'] for t in rest['trials']), total_s,
            sum(t['spikes_L'] for t in rest['trials']) / total_s, sum(t['spikes_R'] for t in rest['trials']) / total_s))
        for lv_ms in LV_MS:
            load = lambda name: json.loads((out / ('lv%03d_%s.json' % (lv_ms, name))).read_text(encoding='utf-8'))
            # Jang et al. geometry: the right DNp01 for an ipsilateral (+45) and a contralateral (-45) loom.
            ipsi, contra = load('right45'), load('left45')
            base = ipsi['first_recorded']
            tau = ipsi['tau_ms'][base:base + len(ipsi['trials'][0]['ticks'])]
            window = [k for k, t in enumerate(tau) if t >= 0]
            mi, mc = mean_input(ipsi, 'R'), mean_input(contra, 'R')
            ki, kc = max(window, key=lambda k: mi[k]), max(window, key=lambda k: mc[k])
            spikes_i = np.mean([sum(t['spike_R'] for t in tr['ticks'][window[0]:window[-1] + 1]) for tr in ipsi['trials']])
            spikes_c = np.mean([sum(t['spike_R'] for t in tr['ticks'][window[0]:window[-1] + 1]) for tr in contra['trials']])
            print('   l/v %d: right DNp01, ipsi +45 / contra -45: peak input %.2f / %.2f V (ratio %.2f) at tau %.0f / %.0f ms;'
                  ' spikes before collision %.1f / %.1f' % (lv_ms, mi[ki], mc[kc], mc[kc] / mi[ki], tau[ki], tau[kc],
                                                             spikes_i, spikes_c))
            cells = []
            for name in POSITIONS:
                d = load(name)
                dec = [tr['decision'] for tr in d['trials'] if tr['decision'] is not None]
                cells.append('%s %s (%d)' % (name, '%.0f' % statistics.median(d['tau_ms'][i] for i in dec)
                                             if dec else '-', len(dec)))
            print('   l/v %d: median decision time before collision, ms (decided of 24): %s' % (lv_ms, ', '.join(cells)))


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('mode', choices=('run', 'summary'))
    parser.add_argument('--gain', type=float, choices=GAINS)
    args = parser.parse_args()
    if args.mode == 'run' and args.gain is None:
        parser.error('run needs --gain')
    {'run': run, 'summary': summary}[args.mode](args)


if __name__ == '__main__':
    main()
