"""M1.8-N1 analysis: firing rates by stimulus class, temporal shape and joint tradeoff.

Analysis only; nothing is modified. Candidate decoders are evaluated offline using only
the DNp01 trace the policy already receives. No raw mouse or world data, no LC4/LPLC2
hard gate.

Terminology is deliberate. Only the committed-strike classes carry an independently
justified positive behavioural label, so for the other classes this tool reports a
**criterion firing rate** and a **miss relative to the legacy decoder** rather than a
detection rate or a false negative.

    python tools/loom_robustness_analysis.py
"""
from __future__ import annotations

import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import numpy as np  # noqa: E402
from scipy.stats import beta  # noqa: E402

OUT = ROOT / 'artifacts/m1_8_loom_robustness'
N0 = ROOT / 'artifacts/m1_8_no_loom_calibration'
DT = 0.02
PADDLE_RADIUS = 144.0
FLY_RADIUS = 11.0
LEVELS = (1.45, 1.6, 1.8, 2.0)
WINDOWS_MS = (60, 100, 200)

# Classes with an independently justified positive behavioural label: a committed strike
# is a genuine contact-course threat. The others are neural-sensitivity probes only.
LABELLED_POSITIVE = {'strong_direct', 'medium_committed'}

CANDIDATES = [
    ('A legacy', dict(kind='simple', thr=1.45, persist=1)),
    ('B threshold', dict(kind='simple', thr=1.8, persist=1)),
    ('B threshold', dict(kind='simple', thr=2.0, persist=1)),
    ('B threshold', dict(kind='simple', thr=2.05, persist=1)),
    ('B threshold', dict(kind='simple', thr=2.1, persist=1)),
    ('C persistence', dict(kind='simple', thr=1.45, persist=2)),
    ('C persistence', dict(kind='simple', thr=1.45, persist=3)),
    ('D combined', dict(kind='simple', thr=1.6, persist=2)),
    ('D combined', dict(kind='simple', thr=1.8, persist=2)),
    ('D combined', dict(kind='simple', thr=1.8, persist=3)),
    ('D combined', dict(kind='simple', thr=2.0, persist=2)),
    ('E hybrid', dict(kind='hybrid', high=2.2, low=1.45, persist=2)),
    ('E hybrid', dict(kind='hybrid', high=2.2, low=1.45, persist=3)),
    ('E hybrid', dict(kind='hybrid', high=2.4, low=1.6, persist=2)),
    ('E hybrid', dict(kind='hybrid', high=2.4, low=1.6, persist=3)),
]


def label(spec):
    if spec['kind'] == 'simple':
        return 'thr %.2f / N%d' % (spec['thr'], spec['persist'])
    return 'fast %.2f OR %.2f x N%d' % (spec['high'], spec['low'], spec['persist'])


def clopper_pearson(k, n, alpha=0.05):
    lo = beta.ppf(alpha / 2, k, n - k + 1) if k > 0 else 0.0
    hi = beta.ppf(1 - alpha / 2, k + 1, n - k) if k < n else 1.0
    return float(lo), float(hi)


def run_of(above, persist):
    ready = above.copy()
    for k in range(1, persist):
        shifted = np.zeros_like(above)
        shifted[k:] = above[:-k]
        ready &= shifted
    return ready


def criterion_ready(trace, spec):
    """Ticks at which the criterion is satisfied.

    persist=N means N consecutive samples at or above threshold INCLUDING the first
    crossing, so an uninterrupted run is satisfied on the Nth sample.
    """
    if spec['kind'] == 'simple':
        above = trace >= spec['thr']
        return above, run_of(above, spec['persist'])
    fast = trace >= spec['high']
    slow = run_of(trace >= spec['low'], spec['persist'])
    return (trace >= spec['low']), (fast | slow)


def longest_run(mask):
    best = cur = 0
    for v in mask:
        cur = cur + 1 if v else 0
        best = max(best, cur)
    return best


def window_max_integral(trace, ticks):
    if trace.size < ticks:
        return float(trace.sum())
    kernel = np.ones(ticks)
    return float(np.convolve(trace, kernel, mode='valid').max())


def temporal_shape(trace):
    out = {}
    for lvl in LEVELS:
        above = trace >= lvl
        out['seconds_above_%.2f' % lvl] = float(above.sum() * DT)
        out['longest_run_ticks_above_%.2f' % lvl] = int(longest_run(above))
    for ms in WINDOWS_MS:
        out['max_integral_%dms' % ms] = window_max_integral(trace, max(1, round(ms / 1000 / DT)))
    return out


def main():
    meta = json.loads((OUT / 'trials_meta.json').read_text(encoding='utf-8'))
    data = np.load(OUT / 'trials.npz')
    trials, classes = meta['trials'], meta['classes']

    # ---- no-loom reference from N0 ---------------------------------------------------
    null = np.load(N0 / 'raw.npz')['null']
    null_study = json.loads((N0 / 'study.json').read_text(encoding='utf-8'))
    tt = null_study['no_loom']['ticks_per_trial']
    null_trials = [null[i:i + tt] for i in range(0, null.size, tt)]
    no_loom_shape = {'peak_max': float(null.max())}
    for lvl in LEVELS:
        runs = [longest_run(t >= lvl) for t in null_trials]
        no_loom_shape['longest_run_ticks_above_%.2f' % lvl] = int(max(runs))
        no_loom_shape['seconds_above_%.2f_total' % lvl] = float((null >= lvl).sum() * DT)
    for ms in WINDOWS_MS:
        ticks = max(1, round(ms / 1000 / DT))
        no_loom_shape['max_integral_%dms' % ms] = float(max(
            window_max_integral(t, ticks) for t in null_trials))

    # ---- per-trial annotation --------------------------------------------------------
    annotated = []
    for t in trials:
        i = t['index']
        trace = data['%d_dnp01' % i]
        dist = data['%d_distance' % i]
        window = data['%d_window' % i]
        theta_dot = data['%d_theta_dot' % i]
        drive = max(float(data['%d_%s' % (i, k)].max())
                    for k in ('loomL', 'loomR', 'threatL', 'threatR'))
        closest = int(np.argmin(dist))
        edge_clearance = float(dist.min() - PADDLE_RADIUS - FLY_RADIUS)
        committed = bool(data['%d_committed' % i].any())
        receding = bool(closest < dist.size - 1 and dist[closest + 1] >= dist[closest])
        annotated.append({
            **{k: t[k] for k in ('index', 'kind', 'seed', 'description', 'window_rule',
                                 'window_ticks', 'window_start', 'click_tick')},
            # (A) physical / retinal stimulus
            'stimulus_occurred': bool((theta_dot > 1e-9).any()),
            'peak_theta': float(data['%d_theta' % i].max()),
            'peak_theta_dot': float(theta_dot.max()),
            'positive_expansion_seconds': float((theta_dot > 1e-9).sum() * DT),
            'peak_abs_azimuth': float(np.abs(data['%d_azimuth' % i]).max()),
            # geometry, diagnostic labels only, never exposed to the policy
            'min_paddle_centre_distance': float(dist.min()),
            'min_paddle_edge_clearance': edge_clearance,
            'horizontal_overlap_at_closest': edge_clearance < 0.0,
            'paddle_descends_to_strike_height': committed,
            'geometric_contact_course': committed and edge_clearance < 0.0,
            'closest_approach_time_s': closest * DT,
            'receding_after_closest': receding,
            # (B) neural response
            'peak_encoder_drive': drive,
            'dnp01_response': bool(drive > 0.0),
            'peak_dnp01': float(trace.max()),
            'peak_dnp01_in_window': float(trace[window].max()) if window.any() else 0.0,
            # (D) behavioural label
            'independently_justified_positive_label': t['kind'] in LABELLED_POSITIVE,
            **temporal_shape(trace),
        })

    # ---- per-class, per-candidate firing ---------------------------------------------
    legacy = dict(kind='simple', thr=1.45, persist=1)
    rows = []
    for family, spec in CANDIDATES:
        for kind in classes:
            sel = [a for a in annotated if a['kind'] == kind]
            fired = miss_vs_legacy = legacy_fired = 0
            onset_lat, click_lat, extra, missed_peaks = [], [], [], []
            for a in sel:
                i = a['index']
                trace, window = data['%d_dnp01' % i], data['%d_window' % i]
                above, ready = criterion_ready(trace, spec)
                _, leg = criterion_ready(trace, legacy)
                inside = np.flatnonzero(ready & window)
                leg_in = np.flatnonzero(leg & window)
                cross = np.flatnonzero(above & window)
                if leg_in.size:
                    legacy_fired += 1
                if inside.size:
                    fired += 1
                    onset_lat.append((inside[0] - a['window_start']) * DT)
                    if a['click_tick'] is not None:
                        click_lat.append((inside[0] - a['click_tick']) * DT)
                    if cross.size:
                        extra.append(int(inside[0] - cross[0]))
                else:
                    missed_peaks.append(a['peak_dnp01_in_window'])
                    if leg_in.size:
                        miss_vs_legacy += 1
            n = len(sel)
            lo, hi = clopper_pearson(fired, n)
            ol, cl = np.asarray(onset_lat), np.asarray(click_lat)
            rows.append({
                'family': family, 'criterion': label(spec), 'spec': spec, 'class': kind,
                'has_positive_label': kind in LABELLED_POSITIVE,
                'trials': n, 'fired': fired, 'firing_rate': fired / n,
                'firing_rate_ci95': [lo, hi],
                'legacy_fired': legacy_fired,
                'miss_relative_to_legacy': miss_vs_legacy,
                'weakest_non_firing_peak': float(min(missed_peaks)) if missed_peaks else None,
                'strongest_non_firing_peak': float(max(missed_peaks)) if missed_peaks else None,
                'median_latency_from_onset_s': float(np.median(ol)) if ol.size else None,
                'p95_latency_from_onset_s': float(np.percentile(ol, 95)) if ol.size else None,
                'median_latency_from_click_s': float(np.median(cl)) if cl.size else None,
                'p95_latency_from_click_s': float(np.percentile(cl, 95)) if cl.size else None,
                'extra_ticks_after_first_crossing_median': (
                    float(np.median(extra)) if extra else None),
                'extra_ticks_after_first_crossing_max': int(max(extra)) if extra else None,
                'structural_extra_ticks': (spec.get('persist', 1) - 1),
            })

    # ---- separation: peak thresholding versus short-window integration ---------------
    separation = []
    for kind in classes:
        sel = [a for a in annotated if a['kind'] == kind]
        peak_min = min(a['peak_dnp01_in_window'] for a in sel)
        entry = {'class': kind,
                 'peak_no_loom_max': no_loom_shape['peak_max'],
                 'peak_loom_min': peak_min,
                 'peak_margin': peak_min - no_loom_shape['peak_max'],
                 'peak_separable': peak_min > no_loom_shape['peak_max']}
        for ms in WINDOWS_MS:
            key = 'max_integral_%dms' % ms
            loom_min = min(a[key] for a in sel)
            entry['integral_%dms_no_loom_max' % ms] = no_loom_shape[key]
            entry['integral_%dms_loom_min' % ms] = loom_min
            entry['integral_%dms_margin' % ms] = loom_min - no_loom_shape[key]
            entry['integral_%dms_separable' % ms] = loom_min > no_loom_shape[key]
            entry['integral_%dms_ratio' % ms] = loom_min / no_loom_shape[key] if no_loom_shape[key] else None
        entry['peak_ratio'] = peak_min / no_loom_shape['peak_max']
        separation.append(entry)

    # ---- latency decomposition, strong_direct ----------------------------------------
    decomposition = []
    for thr in (1.45, 1.6, 1.8, 2.0, 2.05):
        base = None
        for persist in (1, 2, 3, 4):
            lat, extra = [], []
            for a in [x for x in annotated if x['kind'] == 'strong_direct']:
                i = a['index']
                trace, window = data['%d_dnp01' % i], data['%d_window' % i]
                above, ready = criterion_ready(trace, dict(kind='simple', thr=thr, persist=persist))
                idx = np.flatnonzero(ready & window)
                cross = np.flatnonzero(above & window)
                if idx.size:
                    lat.append((idx[0] - a['click_tick']) * DT)
                    if cross.size:
                        extra.append(int(idx[0] - cross[0]))
            if not lat:
                continue
            med = float(np.median(lat))
            if persist == 1:
                base = med
            decomposition.append({
                'threshold': thr, 'persistence_ticks': persist,
                'median_latency_from_click_s': med,
                'increase_vs_persist1_s': None if base is None else round(med - base, 6),
                'structural_prediction_s': (persist - 1) * DT,
                'structural_explains_it': (None if base is None else
                                           abs((med - base) - (persist - 1) * DT) < 1e-9),
                'median_extra_ticks_after_first_crossing': (
                    float(np.median(extra)) if extra else None)})

    result = {
        'label': 'M1.8-N1 analysis; nothing implemented, selected or changed',
        'terminology': {
            'A_physical_retinal_stimulus': 'theta_dot > 0 occurred',
            'B_neural_response': 'non-zero LC4/LPLC2 drive and DNp01 excursion',
            'C_criterion_fired': 'candidate decoder satisfied inside the response window',
            'D_behavioural_label': ('only committed-strike classes carry an independently '
                                    'justified positive label; others are neural-sensitivity '
                                    'probes, so non-firing is reported as a criterion miss '
                                    'relative to the legacy decoder, not a false negative')},
        'geometry_note': 'diagnostic labels only; never exposed to the runtime policy',
        'persistence_definition': ('persist=N means N consecutive samples at or above '
                                   'threshold INCLUDING the first crossing sample'),
        'no_loom_reference': no_loom_shape,
        'trials': annotated,
        'per_class_firing': rows,
        'separation_peak_vs_integral': separation,
        'latency_decomposition_strong_direct': decomposition,
    }
    (OUT / 'analysis.json').write_text(json.dumps(result, indent=1) + '\n', encoding='utf-8')
    print('written', OUT / 'analysis.json')
    print()
    print('NO-LOOM REFERENCE (N0):', json.dumps(no_loom_shape, indent=1))


if __name__ == '__main__':
    main()
