"""Validated mechanistic false-trigger model for every (threshold, persistence) cell.

A criterion fires when the trace reaches an effective level L = thr / decay^(persist-1).
A tick carrying k spontaneous spikes reaches L if the residual left by recent history is
at least L-k. Residual is dominated by the most recent prior spike, so P(residual >= r)
is estimated from the measured inter-spike-interval distribution.

The model is validated against the four persistence-1 cells where false triggers were
actually observed, then used to estimate the cells where zero were observed.
"""
import json
import math
import pathlib

import numpy as np

OUT = pathlib.Path(__file__).resolve().parents[1] / 'artifacts/m1_8_no_loom_calibration'
d = json.loads((OUT / 'study.json').read_text(encoding='utf-8'))
crit = json.loads((OUT / 'criteria.json').read_text(encoding='utf-8'))
raw = np.load(OUT / 'raw.npz')
null = raw['null']
tt = d['no_loom']['ticks_per_trial']
decay = d['mechanism']['decay_per_tick']
minutes = d['no_loom']['minutes']
trials = [null[i:i + tt] for i in range(0, null.size, tt)]

counts = {1: 0, 2: 0, 3: 0}
spikes_by_trial = {}
for ti, t in enumerate(trials):
    prev = 0.0
    for i, v in enumerate(t):
        s = v - prev * decay
        if i > 0:
            k = int(round(s))
            if k >= 1:
                spikes_by_trial.setdefault(ti, []).append(i)
                counts[min(k, 3)] = counts.get(min(k, 3), 0) + 1
        prev = v
isi = np.concatenate([np.diff(sorted(v)) for v in spikes_by_trial.values() if len(v) > 1])
lam = d['mechanism']['spikes_per_tick']
p_three_tick = math.exp(-lam) * lam ** 3 / 6
three_per_min = p_three_tick * 60 / 0.02


def p_residual_at_least(r):
    """Probability the residual from the most recent prior spike is at least r."""
    if r <= 0:
        return 1.0
    if r >= 1.0:          # a single prior spike cannot supply this much
        return 0.0
    gap = math.log(r) / math.log(decay)
    return float((isi <= gap).mean())


def estimate(level):
    """Expected false triggers per minute at the given effective level."""
    rate = 0.0
    for k, n in ((1, counts[1]), (2, counts[2])):
        rate += n * p_residual_at_least(level - k) / minutes
    if level <= 3.0:      # a bare three-spike tick always suffices below 3.0
        rate += three_per_min
    return rate


print('spike-tick counts: 1-spike %d, 2-spike %d, 3-spike %d  |  ISI n=%d'
      % (counts[1], counts[2], counts.get(3, 0), isi.size))
print()
print('MODEL VALIDATION against cells with observed false triggers (persistence 1):')
print('%-8s %-12s %-12s %s' % ('thr', 'observed/min', 'model/min', 'ratio'))
for cell in crit['grid']:
    if cell['persistence_ticks'] == 1 and cell['false_events'] > 0:
        est = estimate(cell['threshold'])
        print('%-8s %-12.4f %-12.4f %.2f'
              % (cell['threshold'], cell['false_per_minute'], est,
                 est / cell['false_per_minute']))
print()
print('%-6s %-6s %-9s %-8s %-9s %-9s %-11s' % (
    'persN', 'thr', 'obs/min', 'detect', 'med lat', 'eff lvl', 'model/min'))
rows = []
for cell in crit['grid']:
    level = cell['threshold'] / decay ** (cell['persistence_ticks'] - 1)
    est = estimate(level)
    rows.append({**cell, 'effective_level': level, 'model_false_per_minute': est})
    if cell['detection_rate'] >= 1.0:
        print('%-6d %-6s %-9.4f %-8.3f %-9.3f %-9.3f %-11.5f' % (
            cell['persistence_ticks'], cell['threshold'], cell['false_per_minute'],
            cell['detection_rate'], cell['median_latency_s'], level, est))

base = next(r for r in rows if r['threshold'] == 1.45 and r['persistence_ticks'] == 1)
print()
for target in (1.0, 0.1, 0.01):
    ok = [r for r in rows if r['detection_rate'] >= 1.0
          and r['model_false_per_minute'] <= target]
    best = min(ok, key=lambda r: (r['median_latency_s'], r['persistence_ticks'],
                                  r['threshold'])) if ok else None
    if best:
        print('target <%-6g/min : thr %-5s persist %d  model %.5f/min  detect %.3f'
              '  latency %.3f s (+%.0f ms)' % (
                  target, best['threshold'], best['persistence_ticks'],
                  best['model_false_per_minute'], best['detection_rate'],
                  best['median_latency_s'],
                  1000 * (best['median_latency_s'] - base['median_latency_s'])))
    else:
        print('target <%-6g/min : not reachable on this grid with full detection' % target)

(OUT / 'model.json').write_text(json.dumps(
    {'label': 'validated mechanistic tail model; nothing implemented or changed',
     'spike_tick_counts': counts, 'isi_n': int(isi.size), 'minutes': minutes,
     'poisson_three_spike_per_minute': three_per_min,
     'validation': [{'threshold': c['threshold'], 'observed_per_minute': c['false_per_minute'],
                     'model_per_minute': estimate(c['threshold'])}
                    for c in crit['grid']
                    if c['persistence_ticks'] == 1 and c['false_events'] > 0],
     'rows': rows}, indent=1) + '\n', encoding='utf-8')
print()
print('written', OUT / 'model.json')
