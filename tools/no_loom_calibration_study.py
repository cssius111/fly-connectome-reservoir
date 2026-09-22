"""M1.8-N0: extended no-loom and genuine-loom characterisation of the DNp01 decoder.

Research only. This tool changes no runtime code, configuration, threshold or brain
parameter, and it never writes to a calibration path -- all output goes to
artifacts/m1_8_no_loom_calibration/.

It reuses the accepted fixed-fly-v2 protocol from tools/calibrate_escape.py (escape
disabled, fly motion disabled, collisions disabled, paddle settled before recording) so
the measurement is provenance-comparable with the calibration it examines.

    python tools/no_loom_calibration_study.py --null-trials 150 --null-ticks 1400 \
                                              --loom-trials 150
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault('NUMBA_NUM_THREADS', '4')
os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')

import numpy as np  # noqa: E402

from game.session import Session, calibration_provenance, load_config  # noqa: E402
from tools.calibrate_escape import RecordingPolicy, _trial  # noqa: E402

OUT = ROOT / 'artifacts/m1_8_no_loom_calibration'
# Candidate thresholds requested for the sweep, plus the accepted grid step around 2.0.
CANDIDATES = (1.45, 1.6, 1.8, 2.0, 2.05, 2.1, 2.2, 2.4, 2.6, 2.8, 2.9)


def measure(config, null_trials, null_ticks, loom_trials, loom_ticks, click_tick):
    policy = RecordingPolicy()
    session = Session(config, policy=policy, root=ROOT)
    session.world.collisions_enabled = False
    session.world.fly_motion_enabled = False
    rng = np.random.default_rng(int(config['encoder']['encoder_seed']))
    nulls, looms = [], []
    started = time.perf_counter()
    for i in range(null_trials):
        angle = float(rng.uniform(0, 2*np.pi))
        radius = float(rng.uniform(30.0, 170.0))
        t = _trial(session, policy, 4000+i,
                   (np.cos(angle)*radius, np.sin(angle)*radius), null_ticks, None)
        nulls.append(t['total'])
        if (i+1) % 25 == 0:
            print('  null %d/%d  peak %.3f  %.0fs' % (i+1, null_trials, t['total'].max(),
                                                      time.perf_counter()-started), flush=True)
    for i in range(loom_trials):
        side = -1.0 if i % 2 == 0 else 1.0
        t = _trial(session, policy, 5000+i,
                   (side*float(rng.uniform(5.0, 55.0)), float(rng.uniform(-40.0, 40.0))),
                   loom_ticks, click_tick)
        looms.append({'total': t['total'], 'committed': t['committed'],
                      'click_tick': t['click_tick']})
        if (i+1) % 25 == 0:
            print('  loom %d/%d  peak %.3f  %.0fs' % (i+1, loom_trials, t['total'].max(),
                                                      time.perf_counter()-started), flush=True)
    session.close()
    return nulls, looms, time.perf_counter()-started


def poisson_ci(k, exposure):
    """Exact Poisson 95% interval on a rate, valid for k = 0."""
    from scipy.stats import chi2
    lo = chi2.ppf(0.025, 2*k)/2 if k > 0 else 0.0
    hi = chi2.ppf(0.975, 2*k+2)/2
    return lo/exposure, hi/exposure


def trigger_events(trace, threshold, refractory_ticks):
    """Distinct escapes the live policy would fire: a crossing, then a refractory hold."""
    events, cooldown = 0, 0
    for value in trace:
        if cooldown > 0:
            cooldown -= 1
            continue
        if value >= threshold:
            events += 1
            cooldown = refractory_ticks
    return events


def reconstruct_spikes(trace, decay):
    """DNp01 spikes per tick, from the decaying trace. Rises are quantised at 1.0."""
    prev = 0.0
    spikes = np.empty(trace.size, dtype=np.float64)
    for i, value in enumerate(trace):
        spikes[i] = value - prev*decay
        prev = value
    return spikes


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--config', type=Path, default=ROOT/'game_room_config.json')
    p.add_argument('--null-trials', type=int, default=150)
    p.add_argument('--null-ticks', type=int, default=1400)
    p.add_argument('--loom-trials', type=int, default=150)
    p.add_argument('--loom-ticks', type=int, default=90)
    p.add_argument('--click-tick', type=int, default=20)
    args = p.parse_args()

    config = load_config(args.config)
    dt = float(config['sim']['tick_seconds'])
    tau = float(config['brain']['trace_tau_seconds'])
    decay = float(np.exp(-dt/tau))
    refractory_ticks = int(round(float(config['policy']['refractory_seconds'])/dt))
    OUT.mkdir(parents=True, exist_ok=True)

    nulls, looms, elapsed = measure(config, args.null_trials, args.null_ticks,
                                    args.loom_trials, args.loom_ticks, args.click_tick)
    null_all = np.concatenate(nulls)
    np.savez_compressed(OUT/'raw.npz', null=null_all,
                        loom=np.stack([l['total'] for l in looms]),
                        committed=np.stack([l['committed'] for l in looms]))

    # ---- no-loom distribution -------------------------------------------------------
    n = null_all.size
    q = {name: float(np.percentile(null_all, val))
         for name, val in (('p50', 50), ('p95', 95), ('p99', 99),
                           ('p99_9', 99.9), ('p99_99', 99.99))}
    stats = {'ticks': int(n), 'seconds': n*dt, 'minutes': n*dt/60.0,
             'trials': len(nulls), 'ticks_per_trial': args.null_ticks,
             'seeds': [4000+i for i in range(len(nulls))],
             'max': float(null_all.max()), 'mean': float(null_all.mean()),
             'sd': float(null_all.std(ddof=1)), **q,
             'p99_9_supported': n >= 10000, 'p99_99_supported': n >= 100000}

    # ---- spike mechanism ------------------------------------------------------------
    spikes = np.concatenate([reconstruct_spikes(t, decay) for t in nulls])
    rounded = np.rint(spikes)
    quantisation_error = float(np.abs(spikes - rounded).max())
    counts = {int(v): int(c) for v, c in zip(*np.unique(rounded.astype(int),
                                                        return_counts=True))}
    spike_ticks = np.flatnonzero(rounded >= 1)
    isi = np.diff(spike_ticks)
    per_tick_rate = float(rounded.sum()/n)
    clusters = {}
    for window_ticks in (1, 2, 3, 4, 5):
        # Sliding window totals of spike counts.
        kernel = np.ones(window_ticks)
        totals = np.convolve(rounded, kernel, mode='valid')
        clusters['%dms' % (window_ticks*dt*1000)] = {
            'window_ticks': window_ticks,
            'p_at_least_2_spikes': float((totals >= 2).mean()),
            'p_at_least_3_spikes': float((totals >= 3).mean())}
    mechanism = {'trace_tau_seconds': tau, 'decay_per_tick': decay,
                 'max_abs_quantisation_error': quantisation_error,
                 'spike_count_histogram': counts,
                 'spikes_total': int(rounded.sum()),
                 'spikes_per_tick': per_tick_rate,
                 'spikes_per_second': per_tick_rate/dt,
                 'isi_ticks': {'n': int(isi.size),
                               'median': float(np.median(isi)) if isi.size else None,
                               'p05': float(np.percentile(isi, 5)) if isi.size else None,
                               'min': int(isi.min()) if isi.size else None},
                 'cluster_probabilities': clusters}

    # ---- threshold sweep ------------------------------------------------------------
    loom_peaks = np.array([l['total'][l['committed']].max() if l['committed'].any() else 0.0
                           for l in looms])
    sweep = []
    for thr in CANDIDATES:
        exceed_ticks = int((null_all >= thr).sum())
        events = sum(trigger_events(t, thr, refractory_ticks) for t in nulls)
        lo, hi = poisson_ci(events, n)
        detected, latencies, missed = 0, [], []
        for l, peak in zip(looms, loom_peaks):
            idx = np.flatnonzero((l['total'] >= thr) & l['committed'])
            if idx.size:
                detected += 1
                latencies.append((idx[0]-l['click_tick'])*dt)
            else:
                missed.append(float(peak))
        lat = np.array(latencies)
        sweep.append({
            'threshold': thr,
            'no_loom_exceedance_ticks': exceed_ticks,
            'no_loom_trigger_events': events,
            'false_per_10000_ticks': 10000.0*events/n,
            'false_per_simulated_minute': events/(n*dt/60.0),
            'false_rate_ci95_per_minute': [lo*60.0/dt, hi*60.0/dt],
            'loom_detection_rate': detected/len(looms),
            'loom_missed': len(missed),
            'weakest_detected_peak': float(min(
                (p for l, p in zip(looms, loom_peaks)
                 if np.flatnonzero((l['total'] >= thr) & l['committed']).size), default=float('nan'))),
            'weakest_missed_peak': float(min(missed)) if missed else None,
            'strongest_missed_peak': float(max(missed)) if missed else None,
            'median_latency_s': float(np.median(lat)) if lat.size else None,
            'p95_latency_s': float(np.percentile(lat, 95)) if lat.size else None,
            'max_latency_s': float(lat.max()) if lat.size else None,
        })

    result = {
        'label': 'research measurement only; no runtime, config, threshold or brain change',
        'protocol': 'fixed-fly-v2 (escape disabled, fly motion disabled, collisions disabled)',
        'config': str(args.config.name),
        'config_sha256': hashlib.sha256(args.config.read_bytes()).hexdigest(),
        'provenance': calibration_provenance(config),
        'active_threshold': 1.45,
        'legacy_calibration_ticks': 2520,
        'exposure_multiple_vs_legacy': n/2520.0,
        'refractory_ticks': refractory_ticks,
        'elapsed_seconds': elapsed,
        'no_loom': stats,
        'loom': {'trials': len(looms), 'ticks': args.loom_ticks,
                 'click_tick': args.click_tick,
                 'peak_min': float(loom_peaks.min()), 'peak_median': float(np.median(loom_peaks)),
                 'peak_max': float(loom_peaks.max()),
                 'peaks': [float(v) for v in loom_peaks]},
        'mechanism': mechanism,
        'sweep': sweep,
    }
    (OUT/'study.json').write_text(json.dumps(result, indent=1)+'\n', encoding='utf-8')
    print()
    print('no-loom ticks %d (%.1f min, %.1fx legacy)  max %.4f  p99 %.4f  p99.9 %.4f'
          % (n, stats['minutes'], result['exposure_multiple_vs_legacy'],
             stats['max'], stats['p99'], stats['p99_9']))
    print('loom peaks: min %.3f  median %.3f  max %.3f' % (
        result['loom']['peak_min'], result['loom']['peak_median'], result['loom']['peak_max']))
    print()
    print('%-7s %-9s %-8s %-11s %-9s %-7s %-10s %-10s' % (
        'thr', 'exc ticks', 'events', 'false/min', 'detect', 'missed', 'med lat', 'p95 lat'))
    for s in sweep:
        print('%-7s %-9d %-8d %-11.4f %-9.3f %-7d %-10s %-10s' % (
            s['threshold'], s['no_loom_exceedance_ticks'], s['no_loom_trigger_events'],
            s['false_per_simulated_minute'], s['loom_detection_rate'], s['loom_missed'],
            'n/a' if s['median_latency_s'] is None else '%.3f' % s['median_latency_s'],
            'n/a' if s['p95_latency_s'] is None else '%.3f' % s['p95_latency_s']))
    print()
    print('written', OUT/'study.json')


if __name__ == '__main__':
    main()
