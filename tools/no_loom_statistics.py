"""M1.8-N0 final statistics: event accounting, detection intervals and resolvability.

Analysis only; nothing is modified. Three things the raw sweep does not make explicit:

  * raw above-threshold ticks, spike clusters and actual policy firings are counted
    separately, so one spike cluster is never reported as several false escapes;
  * loom detection is given with an exact binomial interval, because 150/150 does not
    mean the true detection probability is 1;
  * for zero-event cells, the rule-of-three upper bound is reported and each engineering
    target is marked resolvable or not at the exposure actually collected.

    python tools/no_loom_statistics.py
"""
from __future__ import annotations

import json
import math
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import numpy as np  # noqa: E402
from scipy.stats import beta, chi2  # noqa: E402

OUT = ROOT / 'artifacts/m1_8_no_loom_calibration'
DT = 0.02
TARGETS = (1.0, 0.1, 0.01)


def clopper_pearson(k, n, alpha=0.05):
    lo = beta.ppf(alpha/2, k, n-k+1) if k > 0 else 0.0
    hi = beta.ppf(1-alpha/2, k+1, n-k) if k < n else 1.0
    return float(lo), float(hi)


def zero_event_bounds(minutes):
    """Upper bounds when no event is observed."""
    return {'rule_of_three_one_sided_95': 3.0/minutes,
            'exact_poisson_one_sided_95': -math.log(0.05)/minutes,
            'exact_poisson_two_sided_95': (chi2.ppf(0.975, 2)/2)/minutes}


def count_modes(trace, threshold, persist, refractory_ticks):
    """Above-threshold ticks, contiguous clusters, and actual policy firings."""
    above = trace >= threshold
    ticks = int(above.sum())
    clusters = int(np.sum(above[1:] & ~above[:-1]) + (1 if above.size and above[0] else 0))
    ready = above.copy()
    if persist > 1:
        for k in range(1, persist):
            shifted = np.zeros_like(above)
            shifted[k:] = above[:-k]
            ready &= shifted
    firings, cooldown = 0, 0
    for ok in ready:
        if cooldown > 0:
            cooldown -= 1
            continue
        if ok:
            firings += 1
            cooldown = refractory_ticks
    return ticks, clusters, firings


def main():
    study = json.loads((OUT/'study.json').read_text(encoding='utf-8'))
    criteria = json.loads((OUT/'criteria.json').read_text(encoding='utf-8'))
    model = json.loads((OUT/'model.json').read_text(encoding='utf-8'))
    raw = np.load(OUT/'raw.npz')
    null, loom, committed = raw['null'], raw['loom'], raw['committed']
    tt = study['no_loom']['ticks_per_trial']
    trials = [null[i:i+tt] for i in range(0, null.size, tt)]
    minutes = study['no_loom']['minutes']
    refractory = study['refractory_ticks']
    click = study['loom']['click_tick']
    n_loom = loom.shape[0]

    # ---- event accounting ------------------------------------------------------------
    accounting = []
    for thr in (1.45, 1.6, 1.8, 2.0, 2.05, 2.2, 2.6):
        for persist in (1, 2, 3, 4):
            t = c = f = 0
            for tr in trials:
                a, b, d = count_modes(tr, thr, persist, refractory)
                t += a; c += b; f += d
            entry = {'threshold': thr, 'persistence_ticks': persist,
                     'above_threshold_ticks': t, 'contiguous_clusters': c,
                     'policy_firings': f, 'firings_per_minute': f/minutes}
            if f == 0:
                entry['zero_event_upper_bounds_per_minute'] = zero_event_bounds(minutes)
            accounting.append(entry)

    # ---- loom, trial level -----------------------------------------------------------
    loom_rows = []
    for i in range(n_loom):
        trace, mask = loom[i], committed[i]
        peak_window = float(trace[mask].max()) if mask.any() else None
        loom_rows.append({'trial': i, 'peak_in_committed_window': peak_window,
                          'peak_any_tick': float(trace.max()),
                          'committed_ticks': int(mask.sum()),
                          'committed_window': [int(np.flatnonzero(mask)[0]),
                                               int(np.flatnonzero(mask)[-1])] if mask.any() else None})
    detection = []
    for cell in criteria['grid']:
        thr, persist = cell['threshold'], cell['persistence_ticks']
        fired, late, latencies, missed_peaks = 0, 0, [], []
        for i in range(n_loom):
            trace, mask = loom[i], committed[i]
            above = trace >= thr
            ready = above.copy()
            if persist > 1:
                for k in range(1, persist):
                    shifted = np.zeros_like(above)
                    shifted[k:] = above[:-k]
                    ready &= shifted
            inside = np.flatnonzero(ready & mask)
            if inside.size:
                fired += 1
                latencies.append((inside[0]-click)*DT)
            else:
                missed_peaks.append(loom_rows[i]['peak_in_committed_window'])
                if np.flatnonzero(ready).size:
                    late += 1        # crossed, but only after the response window closed
        lo, hi = clopper_pearson(fired, n_loom)
        lat = np.asarray(latencies)
        detection.append({
            'threshold': thr, 'persistence_ticks': persist,
            'detected': fired, 'trials': n_loom,
            'detection_rate': fired/n_loom,
            'detection_ci95_clopper_pearson': [lo, hi],
            'missed': n_loom-fired,
            'missed_but_crossed_after_window': late,
            'weakest_missed_peak': float(min(missed_peaks)) if missed_peaks else None,
            'median_latency_s': float(np.median(lat)) if lat.size else None,
            'p95_latency_s': float(np.percentile(lat, 95)) if lat.size else None,
            'max_latency_s': float(lat.max()) if lat.size else None,
        })

    # ---- resolvability ---------------------------------------------------------------
    resolvability = []
    for target in TARGETS:
        need_min = 3.0/target
        resolvability.append({
            'target_per_minute': target,
            'resolvable_at_current_exposure': minutes >= need_min,
            'exposure_collected_minutes': minutes,
            'zero_event_exposure_needed_minutes_95': need_min,
            'zero_event_exposure_needed_ticks_95': int(round(need_min*60/DT)),
            'note': ('demonstrated by this run if zero events occurred'
                     if minutes >= need_min else
                     'NOT demonstrable at this exposure; model estimate only'),
        })

    result = {
        'label': 'final statistics for M1.8-N0; nothing implemented or changed',
        'no_loom_minutes': minutes, 'no_loom_ticks': int(null.size),
        'zero_event_upper_bounds_per_minute': zero_event_bounds(minutes),
        'loom_trials': n_loom,
        'loom_detection_note': ('150/150 gives a point estimate of 1.0; the exact binomial'
                                ' lower bound is what should be quoted'),
        'event_accounting': accounting,
        'loom_detection': detection,
        'loom_trials_detail': loom_rows,
        'target_resolvability': resolvability,
    }
    (OUT/'statistics.json').write_text(json.dumps(result, indent=1)+'\n', encoding='utf-8')

    b = result['zero_event_upper_bounds_per_minute']
    print('no-loom exposure %.1f min (%d ticks)' % (minutes, null.size))
    print('zero-event upper bounds: rule-of-three %.4f/min | exact 1-sided %.4f | exact 2-sided %.4f'
          % (b['rule_of_three_one_sided_95'], b['exact_poisson_one_sided_95'],
             b['exact_poisson_two_sided_95']))
    print()
    print('TARGET RESOLVABILITY')
    for r in resolvability:
        print('  <%-6g/min  resolvable now: %-5s  needs %.0f min (%d ticks) of zero-event exposure'
              % (r['target_per_minute'], r['resolvable_at_current_exposure'],
                 r['zero_event_exposure_needed_minutes_95'],
                 r['zero_event_exposure_needed_ticks_95']))
    print()
    print('EVENT ACCOUNTING (persistence 1)')
    print('%-7s %-14s %-11s %-9s %s' % ('thr', 'above ticks', 'clusters', 'firings', 'firings/min'))
    for e in accounting:
        if e['persistence_ticks'] == 1:
            print('%-7s %-14d %-11d %-9d %.4f' % (e['threshold'], e['above_threshold_ticks'],
                                                  e['contiguous_clusters'], e['policy_firings'],
                                                  e['firings_per_minute']))
    print()
    print('LOOM DETECTION with exact binomial interval (selected cells)')
    print('%-6s %-6s %-9s %-22s %-8s %-10s' % ('persN', 'thr', 'detected', 'CI95', 'missed', 'late-only'))
    for d in detection:
        if (d['persistence_ticks'], d['threshold']) in (
                (1, 1.45), (1, 2.05), (1, 2.6), (2, 1.8), (3, 1.45), (3, 1.8), (3, 2.0), (4, 1.8)):
            lo, hi = d['detection_ci95_clopper_pearson']
            print('%-6d %-6s %-9s [%.4f, %.4f]      %-8d %-10d'
                  % (d['persistence_ticks'], d['threshold'],
                     '%d/%d' % (d['detected'], d['trials']), lo, hi,
                     d['missed'], d['missed_but_crossed_after_window']))
    print()
    print('written', OUT/'statistics.json')


if __name__ == '__main__':
    main()
