"""M1.8-N0 offline comparison of threshold-only versus temporal decision criteria.

Analysis only: it reads the recorded traces from tools/no_loom_calibration_study.py and
changes nothing. No runtime, threshold, brain parameter or gate is modified, and no raw
mouse or world data is used -- only the DNp01 trace the policy already sees.

    python tools/no_loom_criterion_analysis.py
"""
from __future__ import annotations

import argparse
import json
import math
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault('NUMBA_NUM_THREADS', '4')

import numpy as np  # noqa: E402

OUT = ROOT / 'artifacts/m1_8_no_loom_calibration'
DT = 0.02
THRESHOLDS = (1.45, 1.6, 1.8, 2.0, 2.05, 2.1, 2.2, 2.4, 2.6)
PERSISTENCE = (1, 2, 3, 4)
# Engineering comparison targets only. Class C; not biological requirements.
TARGETS = (1.0, 0.1, 0.01)


def poisson_ci(k, exposure):
    from scipy.stats import chi2
    lo = chi2.ppf(0.025, 2*k)/2 if k > 0 else 0.0
    hi = chi2.ppf(0.975, 2*k+2)/2
    return lo/exposure, hi/exposure


def fire_indices(trace, threshold, persist, refractory_ticks, mask=None):
    """Ticks at which the criterion fires, honouring the policy refractory.

    `persist` = 1 reproduces the current instantaneous rule exactly.
    """
    above = trace >= threshold
    if persist > 1:
        run = np.ones(trace.size, dtype=bool)
        for k in range(persist):
            shifted = np.zeros(trace.size, dtype=bool)
            if k == 0:
                shifted = above
            else:
                shifted[k:] = above[:-k]
            run &= shifted
        ready = run
    else:
        ready = above
    if mask is not None:
        ready = ready & mask
    out, cooldown = [], 0
    for i, ok in enumerate(ready):
        if cooldown > 0:
            cooldown -= 1
            continue
        if ok:
            out.append(i)
            cooldown = refractory_ticks
    return out


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--refractory-ticks', type=int, default=20)
    args = p.parse_args()
    raw = np.load(OUT/'raw.npz')
    study = json.loads((OUT/'study.json').read_text(encoding='utf-8'))
    null = raw['null']
    loom, committed = raw['loom'], raw['committed']
    click = study['loom']['click_tick']
    n = null.size
    minutes = n*DT/60.0
    trial_ticks = study['no_loom']['ticks_per_trial']
    nulls = [null[i:i+trial_ticks] for i in range(0, n, trial_ticks)]
    loom_peaks = np.array([t[c].max() if c.any() else 0.0 for t, c in zip(loom, committed)])

    rows = []
    for persist in PERSISTENCE:
        for thr in THRESHOLDS:
            events = sum(len(fire_indices(t, thr, persist, args.refractory_ticks))
                         for t in nulls)
            lo, hi = poisson_ci(events, minutes)
            detected, latencies, missed = 0, [], []
            for t, c, peak in zip(loom, committed, loom_peaks):
                idx = fire_indices(t, thr, persist, args.refractory_ticks, mask=c)
                if idx:
                    detected += 1
                    latencies.append((idx[0]-click)*DT)
                else:
                    missed.append(float(peak))
            lat = np.array(latencies)
            rows.append({
                'persistence_ticks': persist, 'persistence_ms': persist*DT*1000,
                'threshold': thr,
                'false_events': events,
                'false_per_minute': events/minutes,
                'false_per_minute_ci95': [lo, hi],
                'detection_rate': detected/len(loom), 'missed': len(missed),
                'weakest_missed_peak': float(min(missed)) if missed else None,
                'median_latency_s': float(np.median(lat)) if lat.size else None,
                'p95_latency_s': float(np.percentile(lat, 95)) if lat.size else None,
            })

    baseline = next(r for r in rows if r['persistence_ticks'] == 1 and r['threshold'] == 1.45)

    # Cheapest configuration reaching each engineering target with full detection.
    achievable = {}
    for target in TARGETS:
        ok = [r for r in rows
              if r['false_per_minute_ci95'][1] <= target and r['detection_rate'] >= 1.0]
        if not ok:
            ok = [r for r in rows if r['false_per_minute'] <= target
                  and r['detection_rate'] >= 1.0]
        best = min(ok, key=lambda r: (r['median_latency_s'] if r['median_latency_s'] is not None
                                      else 9e9, r['persistence_ticks'], r['threshold'])) if ok else None
        achievable['per_minute_%g' % target] = {
            'reachable_with_full_detection': best is not None,
            'cheapest_by_latency': best,
            'latency_cost_vs_current_s': (None if best is None or baseline['median_latency_s'] is None
                                          else best['median_latency_s']-baseline['median_latency_s']),
        }

    families = {
        'A_threshold_only': [r for r in rows if r['persistence_ticks'] == 1],
        'B_temporal_only': [r for r in rows if r['threshold'] == 1.45],
        'C_threshold_plus_temporal': [r for r in rows
                                      if r['persistence_ticks'] > 1 and r['threshold'] > 1.45],
    }
    summary = {}
    for name, sel in families.items():
        clean = [r for r in sel if r['false_events'] == 0 and r['detection_rate'] >= 1.0]
        best = min(clean, key=lambda r: r['median_latency_s']) if clean else None
        summary[name] = {
            'configurations_evaluated': len(sel),
            'zero_false_with_full_detection': len(clean),
            'best_by_latency': best,
        }

    result = {'label': 'offline criterion comparison; nothing implemented or changed',
              'no_loom_ticks': int(n), 'no_loom_minutes': minutes,
              'loom_trials': int(loom.shape[0]),
              'refractory_ticks': args.refractory_ticks,
              'current_rule': {'threshold': 1.45, 'persistence_ticks': 1,
                               **{k: baseline[k] for k in
                                  ('false_events', 'false_per_minute', 'detection_rate',
                                   'median_latency_s', 'p95_latency_s')}},
              'engineering_targets_class_c': achievable,
              'family_summary': summary,
              'grid': rows}
    (OUT/'criteria.json').write_text(json.dumps(result, indent=1)+'\n', encoding='utf-8')

    print('no-loom %d ticks (%.1f min), %d loom trials' % (n, minutes, loom.shape[0]))
    print()
    print('%-6s %-7s %-8s %-12s %-9s %-7s %-9s %-9s' % (
        'persN', 'thr', 'false', 'false/min', 'detect', 'missed', 'med lat', 'p95 lat'))
    for r in rows:
        print('%-6d %-7s %-8d %-12.4f %-9.3f %-7d %-9s %-9s' % (
            r['persistence_ticks'], r['threshold'], r['false_events'], r['false_per_minute'],
            r['detection_rate'], r['missed'],
            'n/a' if r['median_latency_s'] is None else '%.3f' % r['median_latency_s'],
            'n/a' if r['p95_latency_s'] is None else '%.3f' % r['p95_latency_s']))
    print()
    print(json.dumps({k: (v['best_by_latency'] or {}).get('threshold') for k, v in summary.items()},
                     indent=1))
    print('written', OUT/'criteria.json')


if __name__ == '__main__':
    main()
