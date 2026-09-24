"""M1.8-N2: replay the recorded N0 and N1 DNp01 traces through the exact runtime policy.

This is not an offline approximation of the decoder. Each policy is constructed with
`game.session.build_policy` from a real configuration, so the same calibration
resolution, configuration parsing and `FixedEscapePolicy.decide` code that the game runs
are exercised sample by sample, including the refractory period.

Two policies are replayed on identical inputs:

* legacy: the pre-N2 ROOM configuration at the N1 baseline commit, which resolves the
  scalar single-sample decoder at 1.45;
* n2: the working-tree ROOM configuration, which resolves the dual-path decoder.

The recorded traces contain the summed DNp01 trace only. Each sample is presented as a
symmetric MotorState (left = right = total / 2, exact in binary floating point). Firing
depends only on the summed trace, so firing counts and latencies are exact; side and
steering are not characterised by this replay and are covered by unit tests instead.

    python tools/n2_decoder_replay.py --out artifacts/m1_8_n2/replay.json
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import numpy as np  # noqa: E402
from scipy.stats import beta, chi2  # noqa: E402

from game.action import MotorState  # noqa: E402
from game.session import build_policy, load_config  # noqa: E402

N0 = ROOT / 'artifacts/m1_8_no_loom_calibration'
N1 = ROOT / 'artifacts/m1_8_loom_robustness'
BASELINE_COMMIT = '76806f0'
DT = 0.02
LABELLED_POSITIVE = ('strong_direct', 'medium_committed')
ZERO = np.zeros(1)


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def baseline_room_config():
    text = subprocess.check_output(['git', 'show', BASELINE_COMMIT + ':game_room_config.json'],
                                   cwd=ROOT, text=True)
    return json.loads(text)


def replay(policy, trace):
    """Feed one trace through policy.decide; return (tick, channel, total) per escape."""
    policy.reset()
    fires = []
    for tick, total in enumerate(trace):
        half = float(total) / 2.0
        action = policy.decide(MotorState(half, half, 0.0, 0.0, ZERO))
        if action.escape:
            # criterion_diagnostics() does not exist in the pre-N2 source.
            accessor = getattr(policy, 'criterion_diagnostics', None)
            channel = accessor()['escape_trigger_channel'] if accessor else 'SINGLE_SAMPLE'
            fires.append((tick, channel, float(total)))
    return fires


def poisson_bounds(k, minutes):
    """Exact Poisson bounds on a rate per minute: one-sided 95% and two-sided 95%."""
    one_sided = chi2.ppf(0.95, 2 * k + 2) / 2 / minutes
    lo = chi2.ppf(0.025, 2 * k) / 2 / minutes if k > 0 else 0.0
    hi = chi2.ppf(0.975, 2 * k + 2) / 2 / minutes
    return float(one_sided), [float(lo), float(hi)]


def clopper_pearson(k, n, alpha=0.05):
    lo = beta.ppf(alpha / 2, k, n - k + 1) if k > 0 else 0.0
    hi = beta.ppf(1 - alpha / 2, k + 1, n - k) if k < n else 1.0
    return [float(lo), float(hi)]


def channel_counts(fires):
    out = {}
    for _, channel, _ in fires:
        out[channel] = out.get(channel, 0) + 1
    return out


def no_loom(policy, trials, label):
    fires = [replay(policy, t) for t in trials]
    flat = [f for trial in fires for f in trial]
    ticks = int(sum(t.size for t in trials))
    minutes = ticks * DT / 60.0
    k = len(flat)
    one_sided, two_sided = poisson_bounds(k, minutes)
    return {'arm': label, 'trials': len(trials), 'ticks': ticks, 'minutes': minutes,
            'policy_firings': k, 'by_channel': channel_counts(flat),
            'events_per_minute_observed': k / minutes,
            'upper95_one_sided_per_minute': one_sided,
            'ci95_two_sided_per_minute': two_sided,
            'observed_zero': k == 0,
            'note': ('observed count; a zero is a zero count, not a zero rate'
                     if k == 0 else 'observed count'),
            'firing_trace_values': sorted({round(f[2], 6) for f in flat})[:20]}


def n0_loom(policy, loom, committed):
    fired, latencies, channels = 0, [], {}
    for trace, mask in zip(loom, committed):
        inside = [f for f in replay(policy, trace) if mask[f[0]]]
        if inside:
            fired += 1
            channels[inside[0][1]] = channels.get(inside[0][1], 0) + 1
            latencies.append((inside[0][0] - 20) * DT)
    lat = np.asarray(latencies)
    return {'trials': len(loom), 'fired_in_committed_window': fired,
            'rate': fired / len(loom), 'rate_ci95': clopper_pearson(fired, len(loom)),
            'first_in_window_by_channel': channels,
            'median_latency_from_click_s': float(np.median(lat)) if lat.size else None,
            'p95_latency_from_click_s': float(np.percentile(lat, 95)) if lat.size else None}


def n1(policy, data, meta):
    per_class, per_trial = {}, []
    for t in meta['trials']:
        i, kind = t['index'], t['kind']
        trace = data['%d_dnp01' % i]
        window = data['%d_window' % i]
        fires = replay(policy, trace)
        inside = [f for f in fires if window[f[0]]]
        before = [f for f in fires if t['window_start'] is not None and f[0] < t['window_start']]
        row = {'index': i, 'kind': kind, 'fires': [[f[0], f[1], f[2]] for f in fires],
               'fired_in_window': bool(inside),
               'first_in_window_tick': inside[0][0] if inside else None,
               'first_in_window_channel': inside[0][1] if inside else None,
               'fires_before_window': len(before)}
        per_trial.append(row)
        c = per_class.setdefault(kind, {'trials': 0, 'fired': 0, 'channels': {},
                                        'click_latency': [], 'onset_latency': [],
                                        'fires_before_window': 0, 'total_policy_firings': 0})
        c['trials'] += 1
        c['total_policy_firings'] += len(fires)
        c['fires_before_window'] += len(before)
        if inside:
            c['fired'] += 1
            c['channels'][inside[0][1]] = c['channels'].get(inside[0][1], 0) + 1
            c['onset_latency'].append((inside[0][0] - t['window_start']) * DT)
            if t['click_tick'] is not None:
                c['click_latency'].append((inside[0][0] - t['click_tick']) * DT)
    summary = {}
    for kind, c in per_class.items():
        cl, ol = np.asarray(c['click_latency']), np.asarray(c['onset_latency'])
        summary[kind] = {
            'trials': c['trials'], 'fired_in_window': c['fired'],
            'firing_proportion': c['fired'] / c['trials'],
            'firing_proportion_ci95': clopper_pearson(c['fired'], c['trials']),
            'first_in_window_by_channel': c['channels'],
            'fast_count': c['channels'].get('FAST', 0),
            'sustained_count': c['channels'].get('SUSTAINED', 0),
            'total_policy_firings_whole_trace': c['total_policy_firings'],
            'firings_before_window': c['fires_before_window'],
            'has_positive_label': kind in LABELLED_POSITIVE,
            'median_latency_from_click_s': float(np.median(cl)) if cl.size else None,
            'p95_latency_from_click_s': float(np.percentile(cl, 95)) if cl.size else None,
            'median_latency_from_onset_s': float(np.median(ol)) if ol.size else None,
            'p95_latency_from_onset_s': float(np.percentile(ol, 95)) if ol.size else None}
    return summary, per_trial


def compare_offline(summary, analysis, criterion):
    """Differences against the accepted N1 offline analysis row for `criterion`."""
    rows = {r['class']: r for r in analysis['per_class_firing'] if r['criterion'] == criterion}
    out = {}
    for kind, s in summary.items():
        r = rows[kind]
        out[kind] = {
            'offline_fired': r['fired'], 'runtime_fired': s['fired_in_window'],
            'fired_matches': r['fired'] == s['fired_in_window'],
            'offline_median_click_s': r['median_latency_from_click_s'],
            'runtime_median_click_s': s['median_latency_from_click_s'],
            'offline_median_onset_s': r['median_latency_from_onset_s'],
            'runtime_median_onset_s': s['median_latency_from_onset_s'],
            'median_onset_matches': (r['median_latency_from_onset_s'] is None
                                     and s['median_latency_from_onset_s'] is None) or (
                r['median_latency_from_onset_s'] is not None
                and s['median_latency_from_onset_s'] is not None
                and math.isclose(r['median_latency_from_onset_s'],
                                 s['median_latency_from_onset_s'], abs_tol=1e-9))}
    return out


def explain_differences(legacy_trials, n2_trials, analysis, spec_label, data, meta):
    """For each trial whose runtime in-window outcome differs from the offline criterion,
    report why. The offline criterion has no refractory period and no pre-window state."""
    from tools.loom_robustness_analysis import criterion_ready
    spec = next(r['spec'] for r in analysis['per_class_firing'] if r['criterion'] == spec_label)
    notes = []
    for t, row in zip(meta['trials'], n2_trials):
        i = t['index']
        trace, window = data['%d_dnp01' % i], data['%d_window' % i]
        _, ready = criterion_ready(trace, spec)
        offline = bool((ready & window).any())
        if offline != row['fired_in_window']:
            notes.append({'index': i, 'kind': t['kind'], 'offline_fired': offline,
                          'runtime_fired': row['fired_in_window'],
                          'runtime_fires': row['fires'],
                          'window_start': t['window_start'], 'window_end': t['window_end']})
    return notes


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--out', type=Path, default=ROOT / 'artifacts/m1_8_n2/replay.json')
    p.add_argument('--legacy-only', action='store_true',
                   help='replay only the pre-N2 decoder (baseline capture)')
    args = p.parse_args()

    raw = np.load(N0 / 'raw.npz')
    study = json.loads((N0 / 'study.json').read_text(encoding='utf-8'))
    per = study['no_loom']['ticks_per_trial']
    null = raw['null']
    null_trials = [null[i:i + per] for i in range(0, null.size, per)]
    continuous = [np.load(N0 / 'continuous.npz')['trace']]
    data = np.load(N1 / 'trials.npz')
    meta = json.loads((N1 / 'trials_meta.json').read_text(encoding='utf-8'))
    analysis = json.loads((N1 / 'analysis.json').read_text(encoding='utf-8'))

    policies = {'legacy': (baseline_room_config(), 'thr 1.45 / N1')}
    if not args.legacy_only:
        policies['n2'] = (load_config(ROOT / 'game_room_config.json'), 'fast 2.20 OR 1.45 x N3')

    result = {
        'label': 'exact runtime replay of recorded N0/N1 DNp01 traces; no brain is run',
        'inputs': {name: {'path': str(path.relative_to(ROOT)).replace('\\', '/'),
                          'sha256': sha256(path)}
                   for name, path in (('n0_raw', N0 / 'raw.npz'), ('n0_study', N0 / 'study.json'),
                                      ('n0_continuous', N0 / 'continuous.npz'),
                                      ('n1_trials', N1 / 'trials.npz'),
                                      ('n1_meta', N1 / 'trials_meta.json'),
                                      ('n1_analysis', N1 / 'analysis.json'))},
        'baseline_commit': BASELINE_COMMIT,
        'symmetric_motor_note': ('left = right = total / 2; firing depends only on the summed '
                                 'trace, so counts and latencies are exact'),
        'policies': {}}
    trials_out = {}
    for name, (config, criterion) in policies.items():
        policy, source = build_policy(config, ROOT)
        diag = policy.diagnostics()
        accessor = getattr(policy, 'criterion_diagnostics', None)
        summary, per_trial = n1(policy, data, meta)
        trials_out[name] = per_trial
        entry = {
            'calibration_origin': source.origin,
            'escape_threshold': source.threshold,
            'decoder': getattr(source, 'decoder', None),
            'diagnostics_keys': sorted(diag),
            'criterion_diagnostics_initial': accessor() if accessor else None,
            'n0_no_loom_primary': no_loom(policy, null_trials, 'accepted 150 x 1400-tick arm'),
            'n0_no_loom_continuous': no_loom(policy, continuous,
                                             'secondary continuous 30000-tick arm'),
            'n0_loom_150': n0_loom(policy, raw['loom'], raw['committed']),
            'n1_per_class': summary,
            'n1_offline_criterion': criterion,
            'n1_vs_offline': compare_offline(summary, analysis, criterion),
            'n1_runtime_vs_offline_differences': explain_differences(
                None, per_trial, analysis, criterion, data, meta),
        }
        result['policies'][name] = entry
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=1) + '\n', encoding='utf-8')
    (args.out.parent / (args.out.stem + '_trials.json')).write_text(
        json.dumps(trials_out) + '\n', encoding='utf-8')

    for name, entry in result['policies'].items():
        a = entry['n0_no_loom_primary']
        print('[%s] origin %s' % (name, entry['calibration_origin']))
        print('  N0 no-loom: %d ticks (%.1f min), firings %d %s, %.4f/min, upper95 %.4f/min'
              % (a['ticks'], a['minutes'], a['policy_firings'], a['by_channel'],
                 a['events_per_minute_observed'], a['upper95_one_sided_per_minute']))
        c = entry['n0_no_loom_continuous']
        print('  N0 continuous: firings %d %s, upper95 %.4f/min'
              % (c['policy_firings'], c['by_channel'], c['upper95_one_sided_per_minute']))
        l = entry['n0_loom_150']
        print('  N0 loom: %d/%d %s median %.3f s' % (l['fired_in_committed_window'], l['trials'],
                                                    l['first_in_window_by_channel'],
                                                    l['median_latency_from_click_s']))
        for kind, s in entry['n1_per_class'].items():
            print('  %-17s %2d/%d  FAST %2d  SUST %2d  med(click) %s  med(onset) %s'
                  '  p95(onset) %s  before-window %d' % (
                      kind, s['fired_in_window'], s['trials'], s['fast_count'],
                      s['sustained_count'], s['median_latency_from_click_s'],
                      s['median_latency_from_onset_s'], s['p95_latency_from_onset_s'],
                      s['firings_before_window']))
        print('  differences vs offline:', len(entry['n1_runtime_vs_offline_differences']))
    print('written', args.out)


if __name__ == '__main__':
    main()
