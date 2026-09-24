"""M1.8-N2 research: FAST-threshold sensitivity on already-recorded data.

Research only. No runtime file, configuration or calibration record is changed. Each
candidate policy is the exact runtime ROOM policy from `build_policy` with only
`fast_threshold` overridden in memory; sustained_threshold 1.45 and persistence 3 stay
fixed.

Three recorded datasets are replayed sample by sample through `FixedEscapePolicy.decide`:

* N0: the accepted 210,000-tick no-loom arm (150 x 1400 ticks, reset per trial);
* N1: all 300 loom-robustness trials;
* one human ROOM session recorded under N2 FAST 2.20, using the recorded MotorState of
  every tick on which the brain stepped, with a policy reset per episode.

The human replay is open-loop: the recorded neural stream is exact only until a candidate
first decides differently from the recorded policy, because the world would then diverge.
Every per-event result is labelled exact or post-divergence accordingly.

    python tools/n2_fast_threshold_study.py --session results/game/sessions/<id>
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import numpy as np  # noqa: E402

from game.action import MotorState  # noqa: E402
from game.session import build_policy, load_config  # noqa: E402
from tools.n2_decoder_replay import (N0, N1, clopper_pearson, no_loom, n0_loom, n1,  # noqa: E402
                                     poisson_bounds, replay)

DT = 0.02
CANDIDATES = (2.00, 2.05, 2.08, 2.10, 2.12, 2.15, 2.20)
ZERO = np.zeros(1)


def candidate(fast):
    policy, _ = build_policy(load_config(ROOT / 'game_room_config.json'), ROOT)
    if fast is None:
        return policy
    if not fast > policy.threshold:
        raise ValueError('fast threshold must exceed the sustained threshold')
    policy.fast_threshold = float(fast)
    return policy


def legacy():
    import subprocess
    baseline = json.loads(subprocess.check_output(
        ['git', 'show', '76806f0:game_room_config.json'], cwd=ROOT, text=True))
    return build_policy(baseline, ROOT)[0]


def model_rates():
    rows = json.loads((N0 / 'model.json').read_text(encoding='utf-8'))['rows']
    return {r['threshold']: r['model_false_per_minute'] for r in rows
            if r['persistence_ticks'] == 1}


# ---------------------------------------------------------------- human session ---
def load_session(path):
    rows = [json.loads(line) for line in (path / 'ticks.jsonl').open(encoding='utf-8')]
    episodes = {}
    for row in rows:
        episodes.setdefault(row['episode'], []).append(row)
    return episodes


def motor_of(row):
    n = row['neural']
    return MotorState(n['dnp01_left'], n['dnp01_right'], n['dna02_left'], n['dna02_right'], ZERO)


def run_episode(policy, rows):
    """Decisions for every row on which the brain stepped (None where it did not)."""
    policy.reset()
    out = []
    for row in rows:
        if not row['neural']['brain_stepped']:
            out.append(None)
            continue
        action = policy.decide(motor_of(row))
        channel = policy.criterion_diagnostics()['escape_trigger_channel'] if action.escape else None
        out.append((action, channel))
    return out


def action_tuple(a):
    return (a.escape, a.lateral, a.forward, a.turn, a.strength, a.saccade)


def synced_strikes(episodes, strikes, recorded_fast, fasts):
    """Per-strike counterfactual with the candidate synced to the recorded policy state.

    The recorded policy is run along each episode. At the start of each pre-click
    segment (previous strike resolution or episode start) and again at the click, its
    complete internal state is copied and only fast_threshold is changed. Until the
    candidate's first differing decision, the recorded MotorState stream is exactly what
    the candidate would have received, so that first decision and its time are exact.
    """
    import copy
    out = []
    by_episode = {}
    for s in strikes:
        by_episode.setdefault(s['episode'], []).append(s)
    for ep, rows in episodes.items():
        marks = []
        prev = 0
        for s in by_episode.get(ep, []):
            marks.append((prev, s['click_index'], s))
            prev = s['resolve_index'] + 1
        snapshots = {}
        wanted = {m[0] for m in marks} | {m[1] for m in marks}
        rec = candidate(recorded_fast)
        rec.reset()
        for i, row in enumerate(rows):
            if i in wanted:
                snapshots[i] = copy.deepcopy(rec)
            if row['neural']['brain_stepped']:
                rec.decide(motor_of(row))

        def first_fire(policy, start, stop):
            for i in range(start, stop):
                if not rows[i]['neural']['brain_stepped']:
                    continue
                if policy.decide(motor_of(rows[i])).escape:
                    return i, policy.criterion_diagnostics()['escape_trigger_channel']
            return None

        for seg_start, click, s in marks:
            entry = {k: s[k] for k in ('episode', 'click_time_s', 'outcome')}
            entry['peak_dnp01_after_click'] = max(
                rows[i]['neural']['dnp01_total'] for i in range(click, s['resolve_index'] + 1))
            entry['refractory_ticks_at_click'] = snapshots[click].refractory_remaining
            def variant(snapshot, fast):
                p = copy.deepcopy(snapshot)
                if fast == 'legacy':
                    # Same state, single-sample criterion at the sustained threshold.
                    p.fast_threshold, p.persistence_samples, p.dual_path = None, 1, False
                else:
                    p.fast_threshold = fast
                return p
            for fast in ['legacy', recorded_fast] + [f for f in fasts if f != recorded_fast]:
                pre_fire = first_fire(variant(snapshots[seg_start], fast), seg_start, click)
                post_fire = first_fire(variant(snapshots[click], fast), click,
                                       s['resolve_index'] + 1)
                entry[str(fast)] = {
                    'pre_click_fire_s_before_click': (None if pre_fire is None
                                                      else round((click - pre_fire[0]) * DT, 6)),
                    'pre_click_channel': None if pre_fire is None else pre_fire[1],
                    'post_click_latency_s': (None if post_fire is None
                                             else round((post_fire[0] - click) * DT, 6)),
                    'post_click_channel': None if post_fire is None else post_fire[1],
                    'post_click_dnp01': (None if post_fire is None
                                         else rows[post_fire[0]]['neural']['dnp01_total'])}
            out.append(entry)
    return out


def session_analysis(path, fasts):
    manifest = json.loads((path / 'manifest.json').read_text(encoding='utf-8'))
    episodes = load_session(path)
    recorded_fast = manifest['config']['policy']['escape_decoder']['fast_threshold']

    # Harness check: the recorded decoder must reproduce every recorded action exactly.
    mismatches = 0
    checked = 0
    for rows in episodes.values():
        for row, d in zip(rows, run_episode(candidate(recorded_fast), rows)):
            if d is None:
                continue
            checked += 1
            rec = row['action']
            if action_tuple(d[0]) != (rec['escape'], rec['lateral'], rec['forward'], rec['turn'],
                                      rec['strength'], rec['saccade']):
                mismatches += 1

    strikes, perches = [], []
    for ep, rows in episodes.items():
        click = None
        for i, row in enumerate(rows):
            flags = row['event_flags']
            if flags['strike_start']:
                click = i
            if click is not None and (flags['hit'] or flags['miss']):
                strikes.append({'episode': ep, 'click_index': click, 'resolve_index': i,
                                'click_time_s': rows[click]['session_simulation_time'],
                                'outcome': 'hit' if flags['hit'] else 'miss'})
                click = None
        attached = [bool(r['lifecycle']['attached']) if r.get('lifecycle') else False for r in rows]
        i = 0
        while i < len(rows):
            if attached[i]:
                j = i
                while j + 1 < len(rows) and attached[j + 1]:
                    j += 1
                perches.append({'episode': ep, 'start_index': i, 'end_index': j,
                                'start_time_s': rows[i]['session_simulation_time'],
                                'end_time_s': rows[j]['session_simulation_time']})
                i = j + 1
            else:
                i += 1

    per_candidate = {}
    decisions = {}
    for fast in fasts:
        decisions[fast] = {ep: run_episode(candidate(fast), rows) for ep, rows in episodes.items()}
    recorded = decisions[recorded_fast] if recorded_fast in decisions else {
        ep: run_episode(candidate(recorded_fast), rows) for ep, rows in episodes.items()}

    def first_divergence(ep, fast):
        for i, (a, b) in enumerate(zip(decisions[fast][ep], recorded[ep])):
            if a is not None and b is not None and a[0].escape != b[0].escape:
                return i
        return None

    for fast in fasts:
        div = {ep: first_divergence(ep, fast) for ep in episodes}
        s_rows = []
        for s in strikes:
            ep, rows = s['episode'], episodes[s['episode']]
            window = range(s['click_index'], s['resolve_index'] + 1)

            def first_fire(dec):
                for i in window:
                    if dec[i] is not None and dec[i][0].escape:
                        return i, dec[i][1], rows[i]['neural']['dnp01_total']
                return None
            cand, rec = first_fire(decisions[fast][ep]), first_fire(recorded[ep])
            d = div[ep]
            exact = d is None or d >= s['click_index']
            s_rows.append({
                **s,
                'candidate_fire': None if cand is None else {
                    'latency_s': round((cand[0] - s['click_index']) * DT, 6),
                    'channel': cand[1], 'dnp01_total': cand[2]},
                'recorded_fire': None if rec is None else {
                    'latency_s': round((rec[0] - s['click_index']) * DT, 6),
                    'channel': rec[1], 'dnp01_total': rec[2]},
                'delta_vs_recorded_s': (None if cand is None or rec is None
                                        else round((cand[0] - rec[0]) * DT, 6)),
                'exact': exact,
                'peak_dnp01_in_window': max(rows[i]['neural']['dnp01_total'] for i in window)})
        p_rows = []
        for p in perches:
            ep, rows = p['episode'], episodes[p['episode']]
            idx = range(p['start_index'], p['end_index'] + 1)
            fires = [i for i in idx if decisions[fast][ep][i] is not None
                     and decisions[fast][ep][i][0].escape]
            peak_i = max(idx, key=lambda i: rows[i]['neural']['dnp01_total'])
            streak = best = 0
            for i in idx:
                streak = streak + 1 if rows[i]['neural']['dnp01_total'] >= 1.45 else 0
                best = max(best, streak)
            r = rows[peak_i]
            dist = math.hypot(r['swatter']['x'] - r['fly']['x'], r['swatter']['y'] - r['fly']['y'])
            d = div[ep]
            p_rows.append({
                **p, 'peak_dnp01': r['neural']['dnp01_total'],
                'peak_time_s': r['session_simulation_time'],
                'swatter_centre_distance_at_peak': dist,
                'swatter_phase_at_peak': r['swatter']['phase'],
                'longest_run_at_or_above_1_45': best,
                'candidate_fires': [{'time_s': rows[i]['session_simulation_time'],
                                     'channel': decisions[fast][ep][i][1],
                                     'dnp01_total': rows[i]['neural']['dnp01_total']}
                                    for i in fires],
                'exact': d is None or (fires and d >= fires[0]) or d > p['end_index'],
                'end_reason': rows[p['end_index']]['lifecycle']['mode']})
        per_candidate[fast] = {'first_divergence_by_episode': div, 'strikes': s_rows,
                               'perches': p_rows}
    synced = synced_strikes(episodes, strikes, recorded_fast, fasts)
    return {'session': path.resolve().relative_to(ROOT).as_posix(),
            'synced_strikes': synced,
            'recorded_git_commit': manifest['git_commit'], 'recorded_git_dirty': manifest['git_dirty'],
            'recorded_fast_threshold': recorded_fast,
            'harness_check': {'ticks_checked': checked, 'action_mismatches': mismatches},
            'strikes': len(strikes), 'perched_intervals': len(perches),
            'per_candidate': per_candidate}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--session', type=Path, required=True)
    p.add_argument('--fast', type=float, nargs='*', default=list(CANDIDATES))
    p.add_argument('--out', type=Path, default=ROOT / 'artifacts/m1_8_n2/fast_threshold_study.json')
    args = p.parse_args()

    raw = np.load(N0 / 'raw.npz')
    study = json.loads((N0 / 'study.json').read_text(encoding='utf-8'))
    per = study['no_loom']['ticks_per_trial']
    null = raw['null']
    null_trials = [null[i:i + per] for i in range(0, null.size, per)]
    data = np.load(N1 / 'trials.npz')
    meta = json.loads((N1 / 'trials_meta.json').read_text(encoding='utf-8'))
    models = model_rates()

    out = {'label': 'FAST-threshold sensitivity; research only; runtime unchanged',
           'fixed': {'sustained_threshold': 1.45, 'persistence_samples': 3},
           'no_loom_max_dnp01': float(null.max()), 'candidates': {}}
    arms = [('legacy', legacy())] + [(f, candidate(f)) for f in args.fast]
    for name, policy in arms:
        summary, _ = n1(policy, data, meta)
        n0 = no_loom(policy, null_trials, 'accepted 150 x 1400-tick arm')
        entry = {'n0': n0, 'n0_loom_150': n0_loom(policy, raw['loom'], raw['committed']),
                 'n0_single_sample_exceedances': (None if name == 'legacy' else
                                                  int((null >= name).sum())),
                 'n0_model_fast_path_per_minute': (None if name == 'legacy'
                                                   else models.get(round(name, 2))),
                 'n1': summary}
        out['candidates'][str(name)] = entry
        s, m = summary['strong_direct'], summary['medium_committed']
        print('%-7s N0 %3d %-26s upper95 %.4f | strong %d/60 F%d S%d med %.2f p95 %.3f |'
              ' medium %d/60 F%d S%d med %.2f p95 %.3f | weak %d glance %d abort %d' % (
                  name, n0['policy_firings'], n0['by_channel'], n0['upper95_one_sided_per_minute'],
                  s['fired_in_window'], s['fast_count'], s['sustained_count'],
                  s['median_latency_from_click_s'], s['p95_latency_from_click_s'],
                  m['fired_in_window'], m['fast_count'], m['sustained_count'],
                  m['median_latency_from_click_s'], m['p95_latency_from_click_s'],
                  summary['weak_approach']['fired_in_window'],
                  summary['glancing_pass']['fired_in_window'],
                  summary['aborted_approach']['fired_in_window']), flush=True)

    out['human_session'] = session_analysis(args.session, list(args.fast))
    h = out['human_session']
    print('human harness check', h['harness_check'], 'strikes', h['strikes'],
          'perched intervals', h['perched_intervals'])
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(out, indent=1, default=str) + '\n', encoding='utf-8')
    print('written', args.out)


if __name__ == '__main__':
    main()
