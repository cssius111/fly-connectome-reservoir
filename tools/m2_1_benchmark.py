"""M2.1 exposure-controlled benchmark v2 and reward v2 validation (no learning).

Development (TRAIN seeds only) -> derive coefficients / constraints -> freeze -> EVAL once.

    python tools/m2_1_benchmark.py run --set dev --worker K --workers 7     (NUMBA_NUM_THREADS=1)
    python tools/m2_1_benchmark.py derive                                   (dev data only; writes the frozen definition)
    python tools/m2_1_benchmark.py run --set eval --worker K --workers 7    (refuses unless frozen and unchanged)
    python tools/m2_1_benchmark.py report --set dev|eval

Frozen definition: game/learning/benchmark_v2_frozen.json (tracked). Outputs:
artifacts/m2_1/<set>/ (git-ignored).
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
import os
from pathlib import Path
import sys
import time

os.environ.setdefault('NUMBA_NUM_THREADS', '1')
os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import numpy as np  # noqa: E402

from game.learning import runmode, runner, trials  # noqa: E402
from game.learning.metrics import ANTI_CHEAT_V2, aggregate, anti_cheat_v2  # noqa: E402
from game.learning.reward_v2 import (DEGENERATE_PASSIVE, DEGENERATE_SPAM, RewardV2, constraint_check,  # noqa: E402
                                     derive, objective, threat_summary)

OUT = ROOT / 'artifacts/m2_1'
FROZEN = ROOT / 'game/learning/benchmark_v2_frozen.json'
POLICIES = ('baseline_n4b1c', 'no_escape', 'fixed_maneuver', 'random_legal', 'probe_always_escape',
            'probe_constant_turn', 'probe_clock_escape')
SEEDS_PER_GROUP = 20
THREAT_GROUPS = [(f.name, a) for f in trials.THREAT_FAMILIES for a in trials.ATTACKERS]
BG_GROUPS = [c.name for c in trials.BACKGROUND_FAMILIES]
FAM = {f.name: f for f in trials.THREAT_FAMILIES}
BGF = {c.name: c for c in trials.BACKGROUND_FAMILIES}


def seeds(which):
    groups = ['threat:%s:%s' % g for g in THREAT_GROUPS] + ['background:%s' % b for b in BG_GROUPS]
    out = {}
    for g_i, g in enumerate(groups):
        if which == 'dev':
            out[g] = runmode.train_seeds(2100 + g_i, SEEDS_PER_GROUP)
        else:
            out[g] = [3_800_000 + 1000 * g_i + k for k in range(1, SEEDS_PER_GROUP + 1)]
    flat = [s for v in out.values() for s in v]
    assert len(flat) == len(set(flat)), 'seed collision'
    return out


def jobs(which):
    sd = seeds(which)
    return [(p, g, s) for p in POLICIES for g, lst in sd.items() for s in lst]


def frozen_check():
    if not FROZEN.exists():
        raise SystemExit('benchmark v2 / reward v2 are not frozen: run derive and commit first')
    fz = json.loads(FROZEN.read_text(encoding='utf-8'))
    if fz['benchmark_definition_sha256'] != trials.definition_sha256():
        raise SystemExit('benchmark definition changed after the freeze')
    if fz['attacker_distribution_sha256'] != trials.attacker_sha256():
        raise SystemExit('attacker distributions changed after the freeze')
    if RewardV2(**{k: v for k, v in fz['reward_v2'].items()}).sha256() != fz['reward_v2_sha256']:
        raise SystemExit('reward definition inconsistent')
    return fz


def run(which, worker, workers):
    if os.environ['NUMBA_NUM_THREADS'] != '1':
        raise SystemExit('requires NUMBA_NUM_THREADS=1')
    if which == 'eval':
        frozen_check()
    mode = runmode.TRAIN if which == 'dev' else runmode.EVAL
    out = OUT / which
    out.mkdir(parents=True, exist_ok=True)
    part = out / ('part_%d.jsonl' % worker)
    done = set()
    if part.exists():
        for l in part.open(encoding='utf-8'):
            r = json.loads(l)
            done.add((r['policy'], r['group'], r['seed']))
    config = runner.load_config()
    mine = [j for i, j in enumerate(jobs(which)) if i % workers == worker]
    sessions = {}
    t0 = time.time()
    with part.open('a', encoding='utf-8') as fh:
        for k, (pol, group, seed) in enumerate(mine):
            if (pol, group, seed) in done:
                continue
            if pol not in sessions:
                # Dev uses TRAIN seeds, but these fixed policies never explore or update.
                p = runner.make_policy(pol, config, mode=runmode.EVAL)
                sessions[pol] = runner.make_session(p, config)
            kind, *rest = group.split(':')
            if kind == 'threat':
                r = trials.run_threat_trial(sessions[pol], FAM[rest[0]], rest[1], seed, mode)
            else:
                r = trials.run_background(sessions[pol], BGF[rest[0]], seed, mode)
                r = {'metrics': r['metrics'], 'trajectory_sha256': r['trajectory_sha256']}
            r.update({'policy': pol, 'group': group, 'seed': seed, 'kind': kind})
            fh.write(json.dumps(r, default=float) + '\n')
            fh.flush()
            if k % 25 == 0:
                print('worker %d: %d/%d (%.0f s)' % (worker, k, len(mine), time.time() - t0), flush=True)
    print('worker %d done' % worker, flush=True)


def load(which):
    recs = [json.loads(l) for f in sorted((OUT / which).glob('part_*.jsonl')) for l in f.open(encoding='utf-8')]
    exp = set(jobs(which))
    got = {(r['policy'], r['group'], r['seed']) for r in recs}
    if got != exp:
        raise SystemExit('incomplete %s set: %d of %d' % (which, len(got & exp), len(exp)))
    data = {p: {'threat': [], 'background': []} for p in POLICIES}
    for r in recs:
        if r['kind'] == 'threat':
            data[r['policy']]['threat'].append(r)
        else:
            m = dict(r['metrics'])
            m['group'] = r['group']
            data[r['policy']]['background'].append(m)
    return data, recs


def bg_aggregate(B):
    a = aggregate(B)
    a['category_switches_per_s'] = float(np.mean([e['category_switches_per_s'] for e in B]))
    a['speed_entropy_bits'] = float(np.mean([e['speed_entropy_bits'] for e in B]))
    return a


def exposure_checks(data):
    """Policy-independence of threat exposure."""
    res = {'all_trials_exposed': {p: all(t['exposed'] for t in d['threat']) for p, d in data.items()}}
    by_key = {}
    for p, d in data.items():
        for t in d['threat']:
            by_key.setdefault((t['group'], t['seed']), {})[p] = t
    airborne_equal = attacker_equal = fallback_equal = 0
    n_air = n_all = n_perch = 0
    for (g, s), per in by_key.items():
        vals = list(per.values())
        n_all += 1
        attacker_equal += len({json.dumps(v['attacker_params'], sort_keys=True) for v in vals}) == 1
        if 'perched_or_fallback' in g:
            n_perch += 1
            fallback_equal += len({v['fallback_time_s'] for v in vals}) == 1
        else:
            n_air += 1
            airborne_equal += len({v['engage_s'] for v in vals}) == 1
    res['identical_engage_time_airborne_families'] = [airborne_equal, n_air]
    res['identical_attacker_parameters'] = [attacker_equal, n_all]
    res['identical_fallback_time_perched_family'] = [fallback_equal, n_perch]
    res['perched_branch'] = {p: Counter(t.get('branch') for t in d['threat'] if t['family'] == 'perched_or_fallback')
                             for p, d in data.items()}
    res['click_delay_after_engage_s_median'] = {
        p: float(np.median([t['click_s'] - t['engage_s'] for t in d['threat']])) for p, d in data.items()}
    res['click_distance_median'] = {p: float(np.median([t['click_distance'] for t in d['threat']])) for p, d in data.items()}
    res['forced_click_fraction'] = {p: float(np.mean([t['forced_click'] for t in d['threat']])) for p, d in data.items()}
    return res


def evaluate(data, spec, constraints):
    base = data['baseline_n4b1c']
    base_bg = bg_aggregate(base['background'])
    res = {}
    for p, d in data.items():
        T, B = d['threat'], d['background']
        bg = bg_aggregate(B)
        J, s, u = objective(T, B, spec)
        cons = constraint_check(bg, constraints)
        flags = anti_cheat_v2(T, bg, base['threat'], base_bg)
        by_att = {a: threat_summary([t for t in T if t['attacker'] == a]) for a in trials.ATTACKERS}
        by_fam = {f: threat_summary([t for t in T if t['family'] == f]) for f in FAM}
        by_exp = {e: threat_summary([t for t in T if t.get('exposure_type') == e])
                  for e in ('airborne', 'perched', 'airborne_fallback')}
        res[p] = {'threat': threat_summary(T), 'threat_by_attacker': by_att, 'threat_by_family': by_fam,
                  'threat_by_exposure': by_exp, 'background': bg, 'objective_J': J, 'threat_score': s,
                  'background_unnecessary_per_min': u, 'constraints': cons,
                  'constraints_ok': all(c['ok'] for c in cons.values()), 'anti_cheat_flags': flags,
                  'admissible': all(c['ok'] for c in cons.values()) and not any(flags.values())}
    return res


def probe_acceptance(ev, exposure):
    b = ev['baseline_n4b1c']

    def loses(p):
        return (not ev[p]['admissible']) or ev[p]['objective_J'] < b['objective_J']
    return {
        'A_baseline_admissible_and_preferred_to_degenerate': b['admissible'] and all(loses(p) for p in DEGENERATE_SPAM + DEGENERATE_PASSIVE),
        'B_no_escape_cannot_win_by_avoiding_escape_costs': ev['no_escape']['objective_J'] < b['objective_J'],
        'C_always_turn_cannot_win': loses('probe_constant_turn') and exposure['all_trials_exposed']['probe_constant_turn'],
        'D_always_escape_cannot_win': loses('probe_always_escape'),
        'E_ecology_avoidance_cannot_remove_exposure': all(exposure['all_trials_exposed'].values()),
        'clock_probe_cannot_win': loses('probe_clock_escape'),
        'detail': {p: {'J': ev[p]['objective_J'], 'admissible': ev[p]['admissible'],
                       'violations': [k for k, c in ev[p]['constraints'].items() if not c['ok']],
                       'flags': [k for k, f in ev[p]['anti_cheat_flags'].items() if f]} for p in ev},
    }


def do_derive():
    data, recs = load('dev')
    spec, constraints, record = derive(data)
    ev = evaluate(data, spec, constraints)
    exp = exposure_checks(data)
    acc = probe_acceptance(ev, exp)
    dev_hash = hashlib.sha256(''.join(sorted(r['trajectory_sha256'] for r in recs)).encode()).hexdigest()
    frozen = {
        'label': 'M2.1 frozen benchmark v2, attacker distributions, reward v2 and constraints',
        'frozen_utc': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
        'derived_from': 'development set (TRAIN seeds only); no EVAL result existed at freeze time',
        'benchmark_definition': trials.definition(), 'benchmark_definition_sha256': trials.definition_sha256(),
        'attacker_distribution_sha256': trials.attacker_sha256(),
        'reward_v2': spec.as_dict(), 'reward_v2_sha256': spec.sha256(), 'constraints': constraints,
        'anti_cheat_v2': ANTI_CHEAT_V2, 'derivation': record, 'dev_probe_acceptance': acc,
        'policies': list(POLICIES), 'seeds_per_group': SEEDS_PER_GROUP,
        'dev_seeds': seeds('dev'), 'eval_seeds': seeds('eval'), 'dev_trajectory_digest': dev_hash,
    }
    FROZEN.write_text(json.dumps(frozen, indent=1, default=float) + '\n', encoding='utf-8')
    (OUT / 'dev').mkdir(parents=True, exist_ok=True)
    (OUT / 'dev' / 'report.json').write_text(json.dumps({'evaluation': ev, 'exposure': exp, 'acceptance': acc},
                                                        indent=1, default=float) + '\n', encoding='utf-8')
    print('reward v2', spec.as_dict())
    print('derivation', json.dumps(record, default=float))
    print('constraints', json.dumps(constraints, default=float))
    show(ev, exp, acc)


def do_report(which):
    fz = frozen_check()
    data, recs = load(which)
    spec = RewardV2(**fz['reward_v2'])
    ev = evaluate(data, spec, fz['constraints'])
    exp = exposure_checks(data)
    acc = probe_acceptance(ev, exp)
    rep = {'set': which, 'frozen_definition_sha256': hashlib.sha256(FROZEN.read_bytes()).hexdigest(),
           'evaluation': ev, 'exposure': exp, 'acceptance': acc,
           'trajectory_digest': hashlib.sha256(''.join(sorted(r['trajectory_sha256'] for r in recs)).encode()).hexdigest()}
    (OUT / which / 'report.json').write_text(json.dumps(rep, indent=1, default=float) + '\n', encoding='utf-8')
    config = runner.load_config()
    man = runner.run_manifest('m2.1-benchmark-v2-%s' % which, POLICIES, [s for v in seeds(which).values() for s in v],
                              config, spec, metrics={p: {'J': v['objective_J'], 'hit_probability': v['threat']['hit_probability'],
                                                         'admissible': v['admissible']} for p, v in ev.items()},
                              extra={'benchmark_definition_sha256': fz['benchmark_definition_sha256'],
                                     'attacker_distribution_sha256': fz['attacker_distribution_sha256'],
                                     'reward_v2_sha256': fz['reward_v2_sha256'],
                                     'frozen_file_sha256': rep['frozen_definition_sha256'],
                                     'report_sha256': hashlib.sha256((OUT / which / 'report.json').read_bytes()).hexdigest()})
    (OUT / which / 'manifest.json').write_text(json.dumps(man, indent=1, default=str) + '\n', encoding='utf-8')
    show(ev, exp, acc)


def show(ev, exp, acc):
    for p, v in ev.items():
        t, bg = v['threat'], v['background']
        print('%-20s hit %.3f esc_in_win %.2f lat %s | bg unnec %.2f/min wall %.3f maxspd %.3f turn %.2f perch %.2f/min '
              'switch %.2f/s | J %.3f adm %s viol %s flags %s' % (
                  p, t['hit_probability'], t['escape_in_window_fraction'], t['median_escape_latency_s'],
                  v['background_unnecessary_per_min'], bg['wall_contact_fraction'], bg['max_speed_fraction'],
                  bg['turn_active_fraction'], bg['perches_per_min'] or 0.0, bg['category_switches_per_s'],
                  v['objective_J'], v['admissible'], [k for k, c in v['constraints'].items() if not c['ok']],
                  [k for k, f in v['anti_cheat_flags'].items() if f]))
    print('exposure', json.dumps({k: v for k, v in exp.items() if k != 'perched_branch'}, default=float))
    print('perched branch', {p: dict(c) for p, c in exp['perched_branch'].items()})
    print('acceptance', json.dumps({k: v for k, v in acc.items() if k != 'detail'}))


if __name__ == '__main__':
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('mode', choices=('run', 'derive', 'report'))
    ap.add_argument('--set', default='dev', choices=('dev', 'eval'))
    ap.add_argument('--worker', type=int, default=0)
    ap.add_argument('--workers', type=int, default=1)
    a = ap.parse_args()
    if a.mode == 'run':
        run(a.set, a.worker, a.workers)
    elif a.mode == 'derive':
        do_derive()
    else:
        do_report(a.set)
