"""M2.4-B analysis: blind human A/B gameplay (A = N4B1C, B = M2.4-A candidate). Run only after all sessions.

Unit of pairing: the block (one A and one B session with the same world seed, adjacent in time, order randomised).

- Objective:
  - pooled per-strike rates with a block-cluster bootstrap CI of B - A;
  - session-level rates with paired block differences (mean, bootstrap CI, exact Wilcoxon signed-rank);
  - order-aware checks: B - A by within-block order (AB vs BA blocks) and a session-index trend.
- Subjective: paired block differences per rating (mean, median, bootstrap CI, Wilcoxon).
- Acceptance: the preregistered checks in game/learning/m2_4_b/protocol.json, evaluated mechanically.

Outputs artifacts/m2_4_b/analysis.json (git-ignored; it contains aggregated subjective ratings and per-block
differences). Nothing here is committed unless the user asks.

    python tools/m2_4_b_analyze.py        (after `m2_4_b_blind_ab.py reveal`)
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
import sys

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
_spec = importlib.util.spec_from_file_location('m2_4_b_blind_ab', ROOT / 'tools/m2_4_b_blind_ab.py')
B = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(B)

BOOT = 20000
RNG = 2405
TURNING = ('TURN_LEFT', 'TURN_RIGHT', 'SACCADE')


def wilcoxon(d):
    from scipy.stats import wilcoxon as w
    d = [x for x in d if x != 0]
    if len(d) < 1:
        return None
    return float(w(d, zero_method='wilcox', alternative='two-sided', method='exact' if len(d) <= 25 else 'auto').pvalue)


def boot_ci(values, stat, rng):
    values = list(values)
    n = len(values)
    s = [stat([values[i] for i in rng.integers(0, n, n)]) for _ in range(BOOT)]
    return [float(np.percentile(s, 2.5)), float(np.percentile(s, 97.5))]


def pooled(sessions, num, den):
    n = sum(s['metrics'][num] for s in sessions)
    d = sum(s['metrics'][den] for s in sessions)
    return n / d if d else None


def per_min(sessions, key):
    return sum(s['metrics'][key] for s in sessions) / (sum(s['metrics']['active_seconds'] for s in sessions) / 60)


def main():
    man, key, rows = B.load_key_and_rows()
    done = B.completed_sessions()
    if len(done) != len(rows):
        raise SystemExit('analysis refuses a partial set: %d of %d sessions complete (no early stopping)' % (len(done), len(rows)))
    if not (B.LOCK_FILE.exists() and B.REVEAL_FILE.exists()):
        raise SystemExit('run reveal first (ratings lock + verified assignments)')
    lock = json.loads(B.LOCK_FILE.read_text(encoding='utf-8'))
    rev = json.loads(B.REVEAL_FILE.read_text(encoding='utf-8'))
    decoded = {x['session']: x['policy'] for x in rev['sessions']}
    for r in rows:
        f = B.SESSIONS / ('session_%02d.json' % r['session'])
        if hashlib.sha256(f.read_bytes()).hexdigest() != lock['files'][f.name]:
            raise SystemExit('session %d changed after the ratings lock' % r['session'])
        d = done[r['session']]
        if decoded[r['session']] != r['policy'] or d['commitment'] != B._commit(key, r['session'], r['policy'])                 or d['world_seed'] != r['world_seed']:
            raise SystemExit('session %d does not match the manifest' % r['session'])
        d['policy'] = r['policy']       # decoded only here, after the lock
    proto = json.loads(B.PROTOCOL.read_text(encoding='utf-8'))
    rng = np.random.default_rng(RNG)
    A_s = [done[r['session']] for r in rows if r['policy'] == 'A']
    B_s = [done[r['session']] for r in rows if r['policy'] == 'B']
    blocks = sorted({r['block'] for r in rows})
    pair = {b: {done[r['session']]['policy']: done[r['session']] for r in rows if r['block'] == b} for b in blocks}
    order = {b: ''.join(done[r['session']]['policy'] for r in sorted((r for r in rows if r['block'] == b),
                                                                      key=lambda r: r['position_in_block'])) for b in blocks}
    out = {'label': 'M2.4-B blind human A/B analysis', 'n_sessions': len(rows), 'n_blocks': len(blocks),
           'manifest_sha256': hashlib.sha256(B.MANIFEST.read_bytes()).hexdigest(),
           'protocol_sha256': hashlib.sha256(B.PROTOCOL.read_bytes()).hexdigest(),
           'incomplete_attempts': len(list(B.SESSIONS.glob('session_*_attempt_*.json')))}

    # ---- objective, pooled per strike with block-cluster bootstrap
    def pooled_diff(bl, num, den):
        a = pooled([pair[b]['A'] for b in bl], num, den)
        bb = pooled([pair[b]['B'] for b in bl], num, den)
        return None if a is None or bb is None else bb - a
    obj = {}
    for name, num, den in (('hit_probability_per_resolved_strike', 'hits', 'resolved_strikes'),
                           ('escape_success_per_resolved_strike', 'successful_escapes', 'resolved_strikes'),
                           ('strikes_with_escape_fraction', 'strikes_with_escape', 'resolved_strikes')):
        obj[name] = {'A': pooled(A_s, num, den), 'B': pooled(B_s, num, den), 'B_minus_A': pooled_diff(blocks, num, den),
                     'B_minus_A_ci95_block_bootstrap': boot_ci(blocks, lambda bl: pooled_diff(bl, num, den), rng)}
    for name in ('unnecessary_escapes', 'wall_contacts', 'perch_events', 'escapes'):
        def pm_diff(bl, k=name):
            return per_min([pair[b]['B'] for b in bl], k) - per_min([pair[b]['A'] for b in bl], k)
        obj[name + '_per_min'] = {'A': per_min(A_s, name), 'B': per_min(B_s, name), 'B_minus_A': pm_diff(blocks),
                                  'B_minus_A_ci95_block_bootstrap': boot_ci(blocks, pm_diff, rng)}
    for pol, ss in (('A', A_s), ('B', B_s)):
        cnt = {}
        for s in ss:
            for k, v in s['metrics']['action_counts'].items():
                cnt[k] = cnt.get(k, 0) + v
        n = sum(cnt.values())
        obj.setdefault('action_distribution', {})[pol] = {k: v / n for k, v in sorted(cnt.items())}
        obj.setdefault('turning_action_fraction', {})[pol] = sum(cnt.get(k, 0) for k in TURNING) / n
        lat = sorted(x for s in ss for x in s['metrics']['escape_latencies_s'])
        obj.setdefault('escape_latency_s_median', {})[pol] = lat[len(lat) // 2] if lat else None
        obj.setdefault('lifecycle_failures', {})[pol] = {
            k: sum(s['metrics']['lifecycle_failures'][k] for s in ss) for k in ('airborne_stalls_ge_2s', 'perch_bouts_ge_60s')}
        obj.setdefault('totals', {})[pol] = {k: sum(s['metrics'][k] for s in ss)
                                             for k in ('committed_strikes', 'resolved_strikes', 'hits', 'deaths', 'untracked_hits')}
        obj['totals'][pol]['active_minutes'] = sum(s['metrics']['active_seconds'] for s in ss) / 60
        obj['totals'][pol]['sessions_with_error'] = sum(1 for s in ss if s.get('error'))

    # ---- objective, session-level paired by block; order-aware
    def sess_hit(s):
        m = s['metrics']
        return m['hits'] / m['resolved_strikes'] if m['resolved_strikes'] else np.nan
    d = np.array([sess_hit(pair[b]['B']) - sess_hit(pair[b]['A']) for b in blocks])
    ok = ~np.isnan(d)
    obj['session_hit_rate_paired'] = {
        'blocks_used': int(ok.sum()), 'mean_B_minus_A': float(d[ok].mean()),
        'ci95_bootstrap': boot_ci(d[ok], np.mean, rng), 'wilcoxon_p': wilcoxon(d[ok].tolist()),
        'blocks_B_lower': int((d[ok] < 0).sum()), 'blocks_B_higher': int((d[ok] > 0).sum()),
        'by_order': {o: {'blocks': int(sum(1 for b, x in zip(blocks, d) if order[b] == o and not np.isnan(x))),
                         'mean_B_minus_A': float(np.nanmean([x for b, x in zip(blocks, d) if order[b] == o]))
                         if any(order[b] == o for b in blocks) else None} for o in ('AB', 'BA')}}
    idx = np.array([s['session'] for s in A_s + B_s], float)
    hr = np.array([sess_hit(s) for s in A_s + B_s])
    isb = np.array([0.0] * len(A_s) + [1.0] * len(B_s))
    m = ~np.isnan(hr)
    X = np.column_stack([np.ones(m.sum()), isb[m], (idx[m] - idx[m].mean()) / idx[m].std()])
    coef, *_ = np.linalg.lstsq(X, hr[m], rcond=None)
    obj['session_trend'] = {'model': 'session hit rate ~ 1 + policy_B + standardised session index (OLS; descriptive)',
                            'policy_B_coef': float(coef[1]), 'session_index_coef_per_sd': float(coef[2])}
    out['objective'] = obj

    # ---- subjective
    subj = {}
    for k, _ in B.RATINGS:
        dd = [pair[b]['B']['ratings'][k] - pair[b]['A']['ratings'][k] for b in blocks]
        subj[k] = {'A_mean': float(np.mean([s['ratings'][k] for s in A_s])), 'B_mean': float(np.mean([s['ratings'][k] for s in B_s])),
                   'A_median': float(np.median([s['ratings'][k] for s in A_s])), 'B_median': float(np.median([s['ratings'][k] for s in B_s])),
                   'paired_mean_B_minus_A': float(np.mean(dd)), 'paired_median_B_minus_A': float(np.median(dd)),
                   'ci95_bootstrap': boot_ci(dd, np.mean, rng), 'wilcoxon_p': wilcoxon(dd)}
    subj['broken_or_exploitable_flags'] = {'A': sum(s['ratings']['broken_or_exploitable'] for s in A_s),
                                           'B': sum(s['ratings']['broken_or_exploitable'] for s in B_s)}
    out['subjective'] = subj

    # ---- preregistered acceptance checks
    o, s_ = obj, subj
    lf = {p: sum(o['lifecycle_failures'][p].values()) for p in 'AB'}
    checks = {
        'A_not_broken_or_exploitative': (s_['broken_or_exploitable_flags']['B'] <= s_['broken_or_exploitable_flags']['A'] + 2
                                         and s_['naturalness']['B_median'] >= 3 and o['totals']['B']['sessions_with_error'] == 0),
        'B_no_major_twitchiness_or_pathology': (s_['twitchiness']['paired_mean_B_minus_A'] <= 1.0
                                                and s_['needless_escaping']['paired_mean_B_minus_A'] <= 1.0
                                                and (o['unnecessary_escapes_per_min']['B'] <= 5.36
                                                     or o['unnecessary_escapes_per_min']['B'] <= o['unnecessary_escapes_per_min']['A'])
                                                and o['turning_action_fraction']['B'] <= o['turning_action_fraction']['A'] + 0.05
                                                and o['wall_contacts_per_min']['B'] <= 1.5 * o['wall_contacts_per_min']['A'] + 0.5),
        'C_no_major_lifecycle_regression': (o['perch_events_per_min']['B'] >= 0.5 * o['perch_events_per_min']['A']
                                            and lf['B'] <= lf['A'] + 3),
        'D_objective_consistent_with_benchmark': (o['hit_probability_per_resolved_strike']['B']
                                                  <= o['hit_probability_per_resolved_strike']['A']),
    }
    checks['E_experience_acceptable'] = (all(checks.values()) and s_['naturalness']['paired_mean_B_minus_A'] >= -1.0
                                         and s_['responsiveness']['paired_mean_B_minus_A'] >= -1.0)
    out['acceptance_rule'] = proto['acceptance']
    out['checks'] = checks
    out['recommendation'] = ('GO for OPTIONAL runtime integration (subject to explicit human approval)' if all(checks.values())
                             else 'NO-GO for optional runtime integration')
    B.PRIVATE.mkdir(parents=True, exist_ok=True)
    (B.PRIVATE / 'analysis.json').write_text(json.dumps(out, indent=1, default=float) + '\n', encoding='utf-8')
    print(json.dumps({'objective': {k: v for k, v in obj.items() if k not in ('action_distribution',)},
                      'subjective': subj, 'checks': checks, 'recommendation': out['recommendation']}, indent=1, default=float))


if __name__ == '__main__':
    main()
