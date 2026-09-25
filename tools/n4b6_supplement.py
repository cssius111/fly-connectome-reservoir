"""M1.8-N4B6 exploratory supplement (not preregistered).

Research only. Reads the N4B6 trial records (artifacts/m1_8_n4b6/trials) and characterises
the processing stages behind the preregistered result. Nothing here changes the preregistered
classification or decision; it explains them.

1. Encoder transfer: driven-side LPLC2 + LC4 sensory spikes per tick against Retina theta_dot.
2. DNp01 and DNp04 per-side spike probability per tick against driven-side sensory spikes.
3. Time courses before closest approach (median over seeds).
4. The closing speed a hover-height approach needs to reach the encoder's N0-separable level.
5. Timing of control-trial responses (motion versus post-hold) and their Retina cause.
6. DNp01 / DNp04 per-side spike counts in a 1 s window ending 0.26 s before closest approach,
   against the per-side 1 s count envelope of the stored 840-min N0 record (N4B2 chunks).
   Descriptive only: it asks whether the information exists in the DN spike train, not how
   to read it out.

    python tools/n4b6_supplement.py
"""
from __future__ import annotations

import importlib.util
import json
import math
from pathlib import Path
import sys

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / 'artifacts/m1_8_n4b6'
spec = importlib.util.spec_from_file_location('n4b6_protocol', ROOT / 'tools/n4b6_protocol.py')
P = importlib.util.module_from_spec(spec)
spec.loader.exec_module(P)
DT, ON = P.DT, P.PRE_HOLD_TICKS
SENSORY_N0_MAX = 22


def load(tid):
    return [np.load(OUT / 'trials' / tid / ('%d.npz' % s)) for s in P.SEEDS]


def driven_side(z):
    """1 = right, 0 = left, from the Retina azimuth sign (the encoder's own side rule)."""
    return (z['retina'][:, 2] >= 0.0).astype(int)


def encoder_transfer(trials):
    td, sens, sp01, sp04, sens_all = [], [], [], [], []
    for z in trials:
        side = driven_side(z)
        s = z['sensory']
        per_side = np.stack([s[:, 0] + s[:, 1], s[:, 2] + s[:, 3]], 1)
        idx = np.arange(len(side))
        td.append(z['retina'][:, 1])
        sens.append(per_side[idx, side])
        sp01.append(z['spikes'][idx, side])          # DNp01 L, R are columns 0, 1
        sp04.append(z['spikes'][idx, 2 + side])      # DNp04 L, R are columns 2, 3
    td, sens, sp01, sp04 = map(np.concatenate, (td, sens, sp01, sp04))
    edges = [-1e-9, 1e-9, 0.02, 0.04, 0.06, 0.08, 0.10, 0.125, 0.15, 0.2, 0.25, 0.3, 0.4, 0.5, 0.75, 1.0, 2.0, 5.0]
    rows = []
    for a, b in zip(edges, edges[1:]):
        m = (td > a) & (td <= b)
        if m.sum() < 50:
            continue
        rows.append({'theta_dot_lo': a, 'theta_dot_hi': b, 'ticks': int(m.sum()),
                     'sensory_median': float(np.median(sens[m])), 'sensory_p95': float(np.percentile(sens[m], 95)),
                     'p_sensory_gt_n0max': float(np.mean(sens[m] > SENSORY_N0_MAX)),
                     'p_dnp01_spike_driven_side': float(sp01[m].mean()),
                     'p_dnp04_spike_driven_side': float(sp04[m].mean())})
    sedges = [-1, 5, 10, 15, 22, 30, 40, 60, 100, 1000]
    srows = []
    for a, b in zip(sedges, sedges[1:]):
        m = (sens > a) & (sens <= b)
        if m.sum() < 50:
            continue
        srows.append({'sensory_lo': a + 1, 'sensory_hi': b, 'ticks': int(m.sum()),
                      'p_dnp01_spike': float(sp01[m].mean()), 'p_dnp04_spike': float(sp04[m].mean())})
    return {'by_theta_dot': rows, 'by_sensory': srows}


def time_course(tid, trials):
    """Median over seeds of driven-side sensory spikes and DNp01 / DNp04 spike counts, in 0.5 s
    bins ending at the closest-approach tick."""
    out = []
    for z in trials:
        rng = z['geo'][:, 6]
        seg = rng[ON:]
        c = ON + int(np.flatnonzero(seg <= seg.min() + 1.0)[0])
        side = driven_side(z)
        idx = np.arange(len(side))
        s = z['sensory']
        sens = np.stack([s[:, 0] + s[:, 1], s[:, 2] + s[:, 3]], 1)[idx, side]
        bins = []
        for k in range(8, 0, -1):
            a, b = c - 25 * k, c - 25 * (k - 1)
            if a < ON:
                continue
            bins.append({'t_end_before_closest_s': 0.5 * (k - 1),
                         'theta_dot_mean': float(z['retina'][a:b, 1].mean()),
                         'sensory_mean': float(sens[a:b].mean()), 'sensory_max': int(sens[a:b].max()),
                         'dnp01_spikes': int(z['spikes'][a:b, side[a]].sum()),
                         'dnp04_spikes': int(z['spikes'][a:b, 2 + side[a]].sum())})
        out.append(bins)
    n = min(len(b) for b in out)
    agg = []
    for i in range(n):
        col = [b[len(b) - n + i] for b in out]
        agg.append({k: (col[0][k] if k == 't_end_before_closest_s' else float(np.median([c[k] for c in col])))
                    for k in col[0]})
    return agg


def required_speed(theta_dot_needed, d=200.0, h=P.HOVER_HEIGHT, half=144.0 * 0.65):
    """Horizontal closing speed at hover height giving theta_dot_needed at horizontal distance d
    (radial approach, edge-on paddle facing its motion, so the tilt term is zero)."""
    r = math.hypot(d, h)
    gain = 2 * half / (r * r + half * half) * (d / r)
    return theta_dot_needed / gain


def control_timing():
    res = {}
    for tid, spec_ in P.MATRIX.items():
        if spec_['role'] != 'control':
            continue
        per = json.loads((OUT / 'per_trial.json').read_text(encoding='utf-8'))[tid]
        offs, n, _ = P.script(spec_['geometry'])
        items = []
        for r, z in zip(per, load(tid)):
            if r['trigger'] is None:
                continue
            t = ON + r['trigger']
            half, rng = z['geo'][:, 8], z['geo'][:, 6]
            lo = max(1, t - 15)
            size_part = (2 * np.arctan(half[lo:t + 1] / rng[lo:t + 1]) - 2 * np.arctan(half[lo - 1:t] / rng[lo:t + 1])) / DT
            items.append({'seed': r['seed'], 'trigger_s': r['trigger'] * DT, 'phase': 'motion' if r['trigger'] < n else 'post-hold',
                          'path': r['trigger_path'],
                          'theta_dot_max_0_3s_before': float(z['retina'][lo:t + 1, 1].max()),
                          'size_part_theta_dot_max_0_3s_before': float(size_part.max())})
        res[tid] = items
    return res


def rate_separability():
    import glob
    meta = json.loads((ROOT / 'artifacts/m1_8_n4b2/connectome.json').read_text(encoding='utf-8'))
    idx = {}
    for j, r in enumerate(meta['panel']):
        idx.setdefault(r['type'], {})[r['side']] = j
    w = 50
    n0 = {t: np.zeros(64, np.int64) for t in ('DNp01', 'DNp04')}
    ticks = 0
    for f in sorted(glob.glob(str(ROOT / 'artifacts/m1_8_n4b2/n0_*_chunk*.npz'))):
        sp = np.load(f)['spikes']
        for i in range(sp.shape[0]):
            ticks += sp.shape[1]
            for t in n0:
                for side in 'LR':
                    c = np.convolve(sp[i][:, idx[t][side]].astype(int), np.ones(w, int), 'valid')
                    n0[t] += np.bincount(c, minlength=64)[:64]
    res = {'n0_minutes': ticks * DT / 60, 'n0_sliding_1s_windows_per_side': {
        t: {'max': int(np.flatnonzero(h)[-1]), '>=3': int(h[3:].sum()), '>=4': int(h[4:].sum()),
            '>=5': int(h[5:].sum()), 'total': int(h.sum())} for t, h in n0.items()}, 'trajectories': {}}
    for tid, sp_ in P.MATRIX.items():
        if sp_['role'] == 'control':
            continue
        v = {'DNp01': [], 'DNp04': []}
        for z in load(tid):
            rng = z['geo'][:, 6]
            seg = rng[ON:]
            c = ON + int(np.flatnonzero(seg <= seg.min() + 1.0)[0])
            side = int(z['retina'][c - 1, 2] >= 0.0)
            a = c - 13 - w
            if a < ON:
                continue
            v['DNp01'].append(int(z['spikes'][a:a + w, side].sum()))
            v['DNp04'].append(int(z['spikes'][a:a + w, 2 + side].sum()))
        if v['DNp01']:
            res['trajectories'][tid] = {t: {'median': float(np.median(x)), 'p_ge_3': float(np.mean(np.array(x) >= 3)),
                                            'p_ge_4': float(np.mean(np.array(x) >= 4)),
                                            'p_ge_5': float(np.mean(np.array(x) >= 5)), 'n': len(x)}
                                        for t, x in v.items()}
    return res


def main():
    table = json.loads((OUT / 'results.json').read_text(encoding='utf-8'))['table']
    approach = [tid for tid, s in P.MATRIX.items() if s['role'] in ('approach', 'abort')]
    all_trials = {tid: load(tid) for tid in P.MATRIX}
    transfer = encoder_transfer([z for tid in P.MATRIX for z in all_trials[tid]])
    first_sep = next((r for r in transfer['by_theta_dot'] if r['p_sensory_gt_n0max'] >= 0.5), None)
    res = {'label': 'M1.8-N4B6 exploratory supplement (not preregistered)',
           'encoder_transfer': transfer,
           'first_theta_dot_bin_with_majority_sensory_above_n0max': first_sep,
           'required_hover_closing_speed_units_per_s': None if first_sep is None else {
               'at_theta_dot': first_sep['theta_dot_lo'],
               'at_d_200': required_speed(first_sep['theta_dot_lo'], 200.0),
               'at_d_400': required_speed(first_sep['theta_dot_lo'], 400.0)},
           'hover_geometry_gain_theta_dot_per_unit_speed': {str(d): required_speed(1.0, d) ** -1
                                                            for d in (100, 200, 300, 400, 600, 900)},
           'time_courses': {tid: time_course(tid, all_trials[tid]) for tid in approach},
           'control_trigger_timing': control_timing(),
           'rate_separability': rate_separability()}
    (OUT / 'supplement.json').write_text(json.dumps(res, indent=1) + '\n', encoding='utf-8')
    for r in transfer['by_theta_dot']:
        print('theta_dot (%.3f, %.3f] n=%d sens med %.0f p95 %.0f P(>22) %.2f  P(DNp01) %.3f  P(DNp04) %.3f' % (
            r['theta_dot_lo'], r['theta_dot_hi'], r['ticks'], r['sensory_median'], r['sensory_p95'],
            r['p_sensory_gt_n0max'], r['p_dnp01_spike_driven_side'], r['p_dnp04_spike_driven_side']))
    for r in transfer['by_sensory']:
        print('sensory %d-%d n=%d P(DNp01) %.3f P(DNp04) %.3f' % (r['sensory_lo'], r['sensory_hi'], r['ticks'],
                                                                 r['p_dnp01_spike'], r['p_dnp04_spike']))
    print(json.dumps(res['required_hover_closing_speed_units_per_s']))
    print(json.dumps(res['hover_geometry_gain_theta_dot_per_unit_speed']))
    for tid in ('A2_frontal_slow', 'B1_frontal_medium', 'B2_frontal_fast_ref'):
        print(tid, json.dumps(res['time_courses'][tid]))
    print(json.dumps(res['rate_separability'], indent=1))


if __name__ == '__main__':
    main()
