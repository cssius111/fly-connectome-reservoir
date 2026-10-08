"""M1.8-N2 research: SUSTAINED temporal-rule comparison on already-recorded data.

Research only. No runtime file, configuration or calibration record is changed.

Candidate rules are implemented here as a subclass of the runtime `FixedEscapePolicy`, so
strength, side, steering, saccades, alert state and the refractory rule are the unchanged
runtime code; only the SUSTAINED test differs.

Exact semantics of a k-of-n SUSTAINED rule:

* qualifying sample: summed DNp01 trace >= 1.45 (the runtime sustained threshold);
* the window holds the qualifying flags of the most recent n samples INCLUDING the
  current one; one flag is appended on every sample, refractory samples included;
* the policy may fire only when not refractory, on the FAST path (total >= FAST, which
  wins ties) or when the window holds >= k qualifying flags;
* when an escape fires, the window is cleared;
* the window never holds more than n samples, so evidence older than n samples cannot
  contribute. After the 20-sample refractory period, the window can only hold flags from
  the last n samples, which are recent neural evidence, and never evidence from before
  the escape.

Strict consecutive 3 is the runtime rule itself. The 3-of-3 window rule is replayed as
a harness check and must reproduce it exactly.

    python tools/n2_temporal_study.py --session results/game/sessions/<id>
"""
from __future__ import annotations

import argparse
from collections import Counter, deque
import copy
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import numpy as np  # noqa: E402

from game.action import FixedEscapePolicy  # noqa: E402
from game.session import build_policy, load_config  # noqa: E402
from tools.n2_decoder_replay import N0, N1, n0_loom, n1, no_loom, replay  # noqa: E402
from tools.n2_fast_threshold_study import legacy, load_session, motor_of  # noqa: E402

DT = 0.02
LOW = 1.45
FAST = 2.10


class WindowEscapePolicy(FixedEscapePolicy):
    """Research copy of the runtime decoder with a k-of-n SUSTAINED window.

    With require_current=True the current sample must also qualify (a stricter
    variant, reported separately).
    """

    def __init__(self, k, n, *args, require_current=False, **kwargs):
        self.k, self.n, self.require_current = int(k), int(n), bool(require_current)
        super().__init__(*args, **kwargs)

    def reset(self):
        super().reset()
        self._window = deque(maxlen=self.n)

    def _trigger_channel(self, total):
        if total >= self.fast_threshold:
            return 'FAST'
        if self.require_current and not total >= self.threshold:
            return None
        if sum(self._window) >= self.k:
            return 'SUSTAINED'
        return None

    def decide(self, motor):
        self._window.append(motor.dnp01_total >= self.threshold)
        action = super().decide(motor)
        if action.escape:
            self._window.clear()
        return action


def runtime_policy():
    return build_policy(load_config(ROOT / 'game_room_config.json'), ROOT)[0]


def make(spec):
    """Build a candidate from the runtime ROOM policy's own parameters."""
    base = runtime_policy()
    if spec['kind'] == 'legacy':
        return legacy()
    if spec['kind'] == 'strict':
        base.fast_threshold = spec['fast']
        return base
    p = WindowEscapePolicy(spec['k'], spec['n'], base.threshold, 0.4, DT,
                           require_current=spec.get('require_current', False),
                           fast_threshold=spec['fast'], persistence_samples=spec['k'])
    for name in ('refractory_ticks', 'tick_seconds', 'forward_bias', 'turn_gain',
                 'alert_threshold', 'steering_alpha', 'alert_saccade_strength',
                 'saccade_interval_ticks', 'alert_dwell_ticks'):
        setattr(p, name, getattr(base, name))
    return p


CANDIDATES = [
    ('legacy single-sample', {'kind': 'legacy'}),
    ('strict-3, FAST 2.20 (current N2)', {'kind': 'strict', 'fast': 2.20}),
    ('A strict-3, FAST 2.10', {'kind': 'strict', 'fast': FAST}),
    ('check 3-of-3 window, FAST 2.10', {'kind': 'window', 'k': 3, 'n': 3, 'fast': FAST}),
    ('B 3-of-4, FAST 2.10', {'kind': 'window', 'k': 3, 'n': 4, 'fast': FAST}),
    ('B* 3-of-4 + current qualifies, FAST 2.10',
     {'kind': 'window', 'k': 3, 'n': 4, 'fast': FAST, 'require_current': True}),
    ('C 3-of-5, FAST 2.10', {'kind': 'window', 'k': 3, 'n': 5, 'fast': FAST}),
    ('C* 3-of-5 + current qualifies, FAST 2.10',
     {'kind': 'window', 'k': 3, 'n': 5, 'fast': FAST, 'require_current': True}),
    ('D 2-of-3 (negative control), FAST 2.10', {'kind': 'window', 'k': 2, 'n': 3, 'fast': FAST}),
]


def hl(trace, start, stop):
    return ''.join('H' if v >= LOW else 'L' for v in trace[max(0, start):stop])


# ------------------------------------------------------------------- N0 patterns ---
def n0_fire_patterns(policy, trials):
    out = []
    for ti, t in enumerate(trials):
        for tick, channel, total in replay(policy, t):
            out.append({'trial': ti, 'tick': tick, 'channel': channel,
                        'dnp01_total': round(total, 4),
                        'last_5_samples': hl(t, tick - 4, tick + 1)})
    return out


def n0_cluster_patterns(trials, join_gap=3):
    """Every group of qualifying samples whose gaps are at most join_gap samples."""
    patterns = Counter()
    window_max = {3: 0, 4: 0, 5: 0}
    for t in trials:
        h = t >= LOW
        idx = np.flatnonzero(h)
        if idx.size:
            start = prev = idx[0]
            for i in list(idx[1:]) + [None]:
                if i is not None and i - prev <= join_gap + 1:
                    prev = i
                    continue
                patterns[hl(t, start, prev + 1)] += 1
                if i is not None:
                    start = prev = i
        for n in window_max:
            if h.size >= n:
                window_max[n] = max(window_max[n],
                                    int(np.convolve(h.astype(int), np.ones(n, int), 'valid').max()))
    return {'cluster_patterns': dict(patterns.most_common()),
            'max_qualifying_in_any_window': window_max}


# --------------------------------------------------------------- loom patterns ---
def loom_patterns(data, meta, kind, span=6):
    first6, prefix4, satisfied = Counter(), Counter(), Counter()
    for m in meta['trials']:
        if m['kind'] != kind:
            continue
        tr, w = data['%d_dnp01' % m['index']], data['%d_window' % m['index']]
        idx = np.flatnonzero((tr >= LOW) & w)
        if not idx.size:
            continue
        t0 = int(idx[0])
        s = hl(tr, t0, t0 + span)
        first6[s] += 1
        prefix4[s[:4]] += 1
        for name, k, n in (('3 consecutive', 3, 3), ('3 of 4', 3, 4), ('3 of 5', 3, 5),
                           ('2 of 3', 2, 3)):
            if k == n:
                ok = 'H' * k in s
            else:
                ok = any(s[i:i + n].count('H') >= k for i in range(0, len(s) - n + 1))
            satisfied[name] += int(ok)
    return {'first_6_after_first_qualifying': dict(first6.most_common()),
            'first_4': dict(prefix4.most_common()),
            'trials_where_rule_is_satisfied_within_6_samples': dict(satisfied)}


def onset_delays(candidates, data, meta, kinds=('strong_direct', 'medium_committed')):
    """Samples from the first qualifying in-window sample to the first in-window firing."""
    out = {}
    for name, c in candidates.items():
        per = {}
        for t, m in zip(c['n1_trials'], meta['trials']):
            if m['kind'] not in kinds or t['first_in_window_tick'] is None:
                continue
            tr, w = data['%d_dnp01' % m['index']], data['%d_window' % m['index']]
            t0 = int(np.flatnonzero((tr >= LOW) & w)[0])
            per.setdefault(m['kind'], Counter())[t['first_in_window_tick'] - t0] += 1
        out[name] = {k: dict(sorted(v.items())) for k, v in per.items()}
    return out


def human_strike_patterns(path):
    """H/L pattern of the first 6 samples after the first post-click qualifying sample."""
    episodes = load_session(path)
    first6, lead = Counter(), []
    for rows in episodes.values():
        click = None
        for i, row in enumerate(rows):
            f = row['event_flags']
            if f['strike_start']:
                click = i
            if click is not None and (f['hit'] or f['miss']):
                vals = [r['neural']['dnp01_total'] for r in rows[click:i + 1]
                        if r['neural']['brain_stepped']]
                idx = [j for j, v in enumerate(vals) if v >= LOW]
                if idx:
                    s = ''.join('H' if v >= LOW else 'L' for v in vals[idx[0]:idx[0] + 6])
                    first6[s] += 1
                    lead.append(idx[0] * DT)
                click = None
    return {'first_6_after_first_qualifying': dict(first6.most_common()),
            'click_to_first_qualifying_s': {'n': len(lead), 'median': float(np.median(lead)),
                                            'mean': float(np.mean(lead))}}


# ---------------------------------------------------------------- human session ---
def to_candidate(snapshot, spec, rows, index):
    """Candidate with the recorded policy's exact state at `index`; window rebuilt
    from the recorded stream (neural data only)."""
    if spec['kind'] == 'legacy':
        p = copy.deepcopy(snapshot)
        p.fast_threshold, p.persistence_samples, p.dual_path = None, 1, False
        return p
    if spec['kind'] == 'strict':
        p = copy.deepcopy(snapshot)
        p.fast_threshold = spec['fast']
        return p
    p = make(spec)
    state = copy.deepcopy(snapshot.__dict__)
    for key in ('fast_threshold', 'persistence_samples'):
        state.pop(key)
    p.__dict__.update(state)
    window = deque(maxlen=p.n)
    stepped = [i for i in range(index) if rows[i]['neural']['brain_stepped']]
    for i in stepped[-p.n:]:
        window.append(rows[i]['neural']['dnp01_total'] >= LOW)
    # The window since the recorded policy's last escape only: the recorded policy
    # cleared its evidence on every escape, and so would the candidate.
    last_escape = max((i for i in stepped if rows[i]['action']['escape']), default=-1)
    keep = sum(1 for i in stepped[-p.n:] if i > last_escape)
    p._window = deque(list(window)[len(window) - keep:], maxlen=p.n)
    return p


def human(path, specs):
    episodes = load_session(path)
    manifest = json.loads((path / 'manifest.json').read_text(encoding='utf-8'))
    recorded_fast = manifest['config']['policy']['escape_decoder']['fast_threshold']
    strikes, perches = [], []
    for ep, rows in episodes.items():
        prev, click = 0, None
        for i, row in enumerate(rows):
            f = row['event_flags']
            if f['strike_start']:
                click = i
            if click is not None and (f['hit'] or f['miss']):
                strikes.append((ep, prev, click, i, f['hit']))
                prev, click = i + 1, None
        attached = [bool(r['lifecycle']['attached']) for r in rows]
        i = 0
        while i < len(rows):
            if attached[i]:
                j = i
                while j + 1 < len(rows) and attached[j + 1]:
                    j += 1
                perches.append((ep, i, j))
                i = j + 1
            else:
                i += 1

    def snapshots(ep, wanted):
        rows = episodes[ep]
        rec = runtime_policy()
        rec.fast_threshold = recorded_fast
        rec.reset()
        out = {}
        for i, row in enumerate(rows):
            if i in wanted:
                out[i] = copy.deepcopy(rec)
            if row['neural']['brain_stepped']:
                rec.decide(motor_of(row))
        return out

    wanted = {}
    for ep, seg, click, _, _ in strikes:
        wanted.setdefault(ep, set()).update({seg, click})
    for ep, a, _ in perches:
        wanted.setdefault(ep, set()).add(a)
    snaps = {ep: snapshots(ep, w) for ep, w in wanted.items()}

    def first_fire(policy, rows, start, stop):
        for i in range(start, stop):
            if rows[i]['neural']['brain_stepped'] and policy.decide(motor_of(rows[i])).escape:
                return i, policy.criterion_diagnostics()['escape_trigger_channel'] \
                    if hasattr(policy, 'criterion_diagnostics') else 'SINGLE_SAMPLE'
        return None

    result = {}
    for name, spec in specs:
        s_rows = []
        for ep, seg, click, resolve, hit in strikes:
            rows = episodes[ep]
            post = first_fire(to_candidate(snaps[ep][click], spec, rows, click), rows, click,
                              resolve + 1)
            pre = first_fire(to_candidate(snaps[ep][seg], spec, rows, seg), rows, seg, click)
            s_rows.append({'episode': ep, 'click_time_s': rows[click]['session_simulation_time'],
                           'hit': hit,
                           'latency_s': None if post is None else round((post[0] - click) * DT, 6),
                           'channel': None if post is None else post[1],
                           'pre_click_escape': pre is not None})
        p_rows = []
        for ep, a, b in perches:
            rows = episodes[ep]
            fire = first_fire(to_candidate(snaps[ep][a], spec, rows, a), rows, a, b + 1)
            p_rows.append({'episode': ep, 'start_s': rows[a]['session_simulation_time'],
                           'end_s': rows[b]['session_simulation_time'],
                           'fire': None if fire is None else {
                               'time_s': rows[fire[0]]['session_simulation_time'],
                               'channel': fire[1],
                               'dnp01_total': rows[fire[0]]['neural']['dnp01_total'],
                               'last_5_samples': ''.join(
                                   'H' if rows[i]['neural']['dnp01_total'] >= LOW else 'L'
                                   for i in range(max(a, fire[0] - 4), fire[0] + 1))}})
        result[name] = {'strikes': s_rows, 'perches': p_rows}
    return result


def summarise_strikes(result, reference='strict-3, FAST 2.20 (current N2)'):
    ref = {i: r['latency_s'] for i, r in enumerate(result[reference]['strikes'])}
    out = {}
    for name, r in result.items():
        lat = [x['latency_s'] for x in r['strikes'] if x['latency_s'] is not None]
        ch = Counter(x['channel'] for x in r['strikes'] if x['channel'])
        earlier = sum(1 for i, x in enumerate(r['strikes'])
                      if x['latency_s'] is not None and ref[i] is not None and x['latency_s'] < ref[i])
        new_fire = sum(1 for i, x in enumerate(r['strikes'])
                       if x['latency_s'] is not None and ref[i] is None)
        out[name] = {'fired': len(lat), 'strikes': len(r['strikes']),
                     'median_s': float(np.median(lat)), 'mean_s': float(np.mean(lat)),
                     'p95_s': float(np.percentile(lat, 95)), 'channels': dict(ch),
                     'earlier_than_current_n2': earlier,
                     'fires_where_current_n2_does_not': new_fire,
                     'pre_click_segments_with_escape': sum(x['pre_click_escape']
                                                           for x in r['strikes']),
                     'perch_fires': [p['fire'] for p in r['perches']]}
    return out


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--session', type=Path, required=True)
    p.add_argument('--out', type=Path, default=ROOT / 'artifacts/m1_8_n2/temporal_study.json')
    args = p.parse_args()

    raw = np.load(N0 / 'raw.npz')
    per = json.loads((N0 / 'study.json').read_text(encoding='utf-8'))['no_loom']['ticks_per_trial']
    null = raw['null']
    null_trials = [null[i:i + per] for i in range(0, null.size, per)]
    data = np.load(N1 / 'trials.npz')
    meta = json.loads((N1 / 'trials_meta.json').read_text(encoding='utf-8'))

    out = {'label': 'SUSTAINED temporal-rule comparison; research only; runtime unchanged',
           'low_threshold': LOW, 'fast_threshold': FAST,
           'semantics': __doc__.split('Exact semantics of a k-of-n SUSTAINED rule:')[1]
           .split('Strict consecutive')[0].strip(),
           'candidates': {}}
    for name, spec in CANDIDATES:
        policy = make(spec)
        n0 = no_loom(policy, null_trials, 'accepted 150 x 1400-tick arm')
        fires = n0_fire_patterns(make(spec), null_trials)
        summary, per_trial = n1(make(spec), data, meta)
        low_fires = sum(1 for t in per_trial for f in t['fires']
                        if f[1] == 'SUSTAINED' and f[2] < LOW)
        out['candidates'][name] = {'spec': spec, 'n0': n0, 'n0_false_events': fires,
                                   'n0_loom_150': n0_loom(make(spec), raw['loom'], raw['committed']),
                                   'n1': summary, 'n1_trials': per_trial,
                                   'n1_sustained_fires_on_subthreshold_sample': low_fires}
        s, m = summary['strong_direct'], summary['medium_committed']
        print('%-44s N0 %3d %-30s up95 %.4f | strong F%2d S%2d med %.2f p95 %.3f | '
              'medium F%2d S%2d med %.2f p95 %.3f | weak %2d glance %2d abort %2d' % (
                  name, n0['policy_firings'], n0['by_channel'], n0['upper95_one_sided_per_minute'],
                  s['fast_count'], s['sustained_count'], s['median_latency_from_click_s'],
                  s['p95_latency_from_click_s'], m['fast_count'], m['sustained_count'],
                  m['median_latency_from_click_s'], m['p95_latency_from_click_s'],
                  summary['weak_approach']['fired_in_window'],
                  summary['glancing_pass']['fired_in_window'],
                  summary['aborted_approach']['fired_in_window']), flush=True)

    strict = out['candidates']['A strict-3, FAST 2.10']['n1_trials']
    check = out['candidates']['check 3-of-3 window, FAST 2.10']['n1_trials']
    out['harness_check_n1_3of3_equals_strict'] = (
        [t['fires'] for t in strict] == [t['fires'] for t in check])
    out['harness_check_n0_3of3_equals_strict'] = (
        out['candidates']['A strict-3, FAST 2.10']['n0_false_events']
        == out['candidates']['check 3-of-3 window, FAST 2.10']['n0_false_events'])
    out['patterns'] = {'n0': n0_cluster_patterns(null_trials),
                       'medium_committed': loom_patterns(data, meta, 'medium_committed'),
                       'strong_direct': loom_patterns(data, meta, 'strong_direct'),
                       'human_strikes': human_strike_patterns(args.session)}
    out['n1_samples_from_first_qualifying_to_firing'] = onset_delays(out['candidates'], data, meta)
    h = human(args.session, CANDIDATES)
    out['human'] = {'per_candidate': h, 'summary': summarise_strikes(h)}
    out['human_harness_check_3of3_equals_strict'] = (
        h['A strict-3, FAST 2.10'] == h['check 3-of-3 window, FAST 2.10'])
    print('harness checks: N1', out['harness_check_n1_3of3_equals_strict'],
          'N0', out['harness_check_n0_3of3_equals_strict'],
          'human', out['human_harness_check_3of3_equals_strict'])
    for name, s in out['human']['summary'].items():
        print('%-44s human fired %d/%d med %.3f mean %.4f p95 %.3f %s earlier %d new %d pre %d perch %s'
              % (name, s['fired'], s['strikes'], s['median_s'], s['mean_s'], s['p95_s'],
                 s['channels'], s['earlier_than_current_n2'],
                 s['fires_where_current_n2_does_not'], s['pre_click_segments_with_escape'],
                 s['perch_fires']))
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(out, indent=1, default=str) + '\n', encoding='utf-8')
    print('written', args.out)


if __name__ == '__main__':
    main()
