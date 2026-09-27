"""M2.4-R0: temporal action abstraction feasibility (RESEARCH ONLY; no policy is trained).

    python tools/m2_4_r0_temporal.py freeze     (preregister seeds, cadences, tolerances, EVAL-v3 design)
    python tools/m2_4_r0_temporal.py record     (closed-loop per-tick streams: A-D and hypothetical cadences)
    python tools/m2_4_r0_temporal.py openloop   (teacher label streams of the frozen BC dataset, subsampled offline)
    python tools/m2_4_r0_temporal.py credit     (M2.3-candidate rollouts + frozen critic, re-aggregated per cadence)
    python tools/m2_4_r0_temporal.py analyze    (all statistics, tolerance checks -> game/learning/m2_4_r0/)

All environment episodes use TRAIN-range seeds only (a fresh R0 development pool from
[25e6, 30e6) excluding the M2.2 / M2.3 TRAIN-VAL list and the M2.1 development seeds). No EVAL
seed is used; M2-EVAL-v3 is only defined. The observation contract, the 11 maneuvers, reward v2,
attacker distributions and the runtime are unchanged.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import multiprocessing as mp
import os
from pathlib import Path
import sys
import time

os.environ.setdefault('NUMBA_NUM_THREADS', '1')
os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import numpy as np  # noqa: E402

from game.learning import temporal_r0, trials  # noqa: E402
from game.learning.contracts import MANEUVERS, N_MANEUVERS  # noqa: E402

OUT = ROOT / 'artifacts/m2_4_r0'
TRACK = ROOT / 'game/learning/m2_4_r0'
PROTOCOL = TRACK / 'r0_protocol.json'
WORKERS = 7
DT = 0.02
NAMES = [m.name for m in MANEUVERS]
NONE = NAMES.index('NONE')
ESC = [i for i, m in enumerate(MANEUVERS) if m.escape]
GROUP_OF = {i: ('NONE' if m.name == 'NONE' else 'TURN' if m.turn else 'SACCADE' if m.saccade and not m.escape
                else 'ESCAPE_HALF' if m.escape and m.strength < 1 else 'ESCAPE_FULL') for i, m in enumerate(MANEUVERS)}
GROUPS = ['NONE', 'TURN', 'SACCADE', 'ESCAPE_FULL', 'ESCAPE_HALF']


def _load(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / ('tools/%s.py' % name))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# ----------------------------------------------------------------- preregistration ---
CADENCES = [1, 2, 5, 10]                      # ticks: 20 / 40 / 100 / 200 ms
VARIANTS = ['sampled', 'latched']
TOLERANCES = {
    'reference': 'mapped N4B1C teacher at 50 Hz (period 1) on the same R0 development episodes (paired seeds)',
    'closed_loop': {
        'T1_threat_window_escape': 'escape-in-window fraction >= reference - 0.05',
        'T2_escape_latency': 'median escape latency after the click <= reference + 0.04 s',
        'T3_hit': 'hit probability <= reference + 0.05',
        'T4_unnecessary': '|unnecessary escapes / min - reference| <= max(1.0, 0.2 x reference)',
        'T5_perch': 'perches / min >= max(0.275, 0.8 x reference)',
        'T6_wall_speed': 'wall-contact fraction <= reference + 0.01 and max-speed fraction <= reference + 0.01',
        'T7_no_new_pathology': 'no M2.1 anti-cheat flag absent from the reference (anti-cheat reference = the accepted '
                               'N4B1C on the same episodes); turn-active fraction within +/- 20 % of the reference',
    },
    'open_loop': {
        'O1_escape_event_recall': 'fraction of teacher escape events reproduced (same side / strength) by the held stream '
                                  'within the decision interval that contains them >= 0.95',
        'O2_escape_delay': 'mean delay of reproduced escapes <= 0.04 s',
        'O3_turn_agreement': 'fraction of teacher TURN ticks where the held stream shows the same turn >= 0.80',
    },
    'selection': 'the COARSEST cadence for which one variant passes every T and O criterion is recommended (outcome B). '
                 'If none coarser than 20 ms passes: outcome C if the natural maneuver durations cluster into a small set, '
                 'otherwise outcome A (keep 50 Hz). Benchmark score is not a selection criterion.',
    'observation_constraint': 'the unchanged observation carries the current frame + 4 history frames (5 ticks = 100 ms); '
                              'a cadence coarser than 5 ticks leaves ticks that no decision observation contains. This is '
                              'reported, not used to relax any tolerance.',
}
EVAL_V3 = {
    'name': 'M2-EVAL-v3',
    'status': 'DEFINED ONLY in M2.4-R0; not generated, not run, never inspected during M2.4 hyperparameter selection',
    'philosophy': 'unchanged M2.1 benchmark v2: exposure-controlled threat trials (4 families x 3 attacker levels, frozen '
                  'attacker distributions, benchmark_definition sha256 127de798...) + background episodes (4 families); '
                  'same metrics, constraints, anti-cheat flags, reward v2',
    'seeds': 'threat group g (0..11, M2.1 order): 3_900_000 + 1000 x g + k, k = 1..40; background group g (12..15): '
             '3_900_000 + 1000 x g + k, k = 1..20 (inside the registered EVAL range (3e6, 4e6); disjoint from EVAL v1 '
             '3.1e6-3.7e6 and v2 3_800_001-3_815_020, including their brain-noise seeds seed + 977)',
    'size': '480 threat trials + 80 background episodes per policy (2 x the v2 threat count, for a paired 95 % CI of about '
            '+/- 0.045 instead of +/- 0.065 at the M2.3 effect size); the size increase is part of this preregistration',
    'baselines': 'accepted N4B1C, no_escape, fixed_maneuver, random_legal and the three probes run once on v3 when it is '
                 'frozen, before any M2.4 candidate exists',
    'freeze_rule': 'seed manifest + sha256 of the definition committed and pushed BEFORE M2.4 full training; the M2.4 '
                   'candidate is frozen (hash committed) before its single v3 run',
    'm2_1_eval_status': 'M2.1 v2 EVAL observed by M2.2 and M2.3: valid historical evidence, not a future holdout',
}


def dev_pool():
    m22 = _load('m2_2_train')
    used = set(m22.dev_seeds()) | {s for v in m22.split()['train_val'].values() for s in v}
    return m22, used


def dev_specs():
    m22, used = dev_pool()
    groups = [('threat', f.name, a, 16) for f in trials.THREAT_FAMILIES for a in trials.ATTACKERS] + \
             [('background', c.name, None, 12) for c in trials.BACKGROUND_FAMILIES]
    specs = []
    for g, (kind, name, level, n) in enumerate(groups):
        rng = np.random.default_rng(2400 + g)
        lst = []
        while len(lst) < n:
            s = int(rng.integers(25_000_000, 30_000_000))
            if s not in used and s not in lst:
                lst.append(s)
        specs += [(kind, name, level, s) for s in lst]
    return specs


def credit_units():
    m22, used = dev_pool()
    used |= {s for *_, s in dev_specs()}
    rng = np.random.default_rng(2450)
    fams = [f.name for f in trials.THREAT_FAMILIES]
    bgs = [c.name for c in trials.BACKGROUND_FAMILIES]

    def seed():
        while True:
            s = int(rng.integers(25_000_000, 30_000_000))
            if s not in used:
                used.add(s)
                return s
    units = []
    for _ in range(21):
        u = [('background', bgs[int(rng.integers(4))], None, seed())]
        u += [('threat', fams[int(rng.integers(4))], list(trials.ATTACKERS)[int(rng.integers(3))], seed()) for _ in range(6)]
        units.append(u)
    return units


def freeze():
    if PROTOCOL.exists():
        raise SystemExit('already frozen')
    TRACK.mkdir(parents=True, exist_ok=True)
    specs = dev_specs()
    units = credit_units()
    proto = {'label': 'M2.4-R0 temporal action abstraction feasibility: preregistration (research only)',
             'frozen_utc': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
             'question': 'does the 50 Hz per-tick decision create unnecessary temporal credit-assignment difficulty, and '
                         'what action-persistence timescale does the existing behaviour justify?',
             'policies': {'A': 'accepted N4B1C (FixedEscapePolicy, continuous Action; categorised by the teacher mapping)',
                          'B': 'mapped N4B1C teacher (11 maneuvers, 50 Hz)',
                          'C': 'frozen PyTorch BC policy (torch_bc_checkpoint.pt, stochastic)',
                          'D': 'selected M2.3 PPO candidate (torch_candidate.pt, stochastic)'},
             'cadences_ticks': CADENCES, 'variants': VARIANTS, 'tolerances': TOLERANCES,
             'dev_episodes': {'n_threat': sum(1 for s in specs if s[0] == 'threat'),
                              'n_background': sum(1 for s in specs if s[0] == 'background'),
                              'rule': 'TRAIN range [25e6, 30e6) minus M2.1 dev and M2.2/M2.3 TRAIN-VAL seeds; numpy '
                                      'default_rng(2400 + group); 16 per threat group, 12 per background family',
                              'sha256': hashlib.sha256(json.dumps(specs).encode()).hexdigest()},
             'credit_rollouts': {'rule': '21 units x (1 background + 6 threat), default_rng(2450), same pool, disjoint from '
                                         'the dev episodes; M2.3 candidate + its frozen seed-4 iteration-60 critic',
                                 'sha256': hashlib.sha256(json.dumps(units).encode()).hexdigest()},
             'windows': {'threat_response_window': 'click - 25 .. click + 25 ticks (+/- 0.5 s)',
                         'switch_horizons_ms': [20, 40, 60, 100, 150, 200, 300],
                         'contexts': 'exclusive precedence: threat_window > perched (TOUCHDOWN / PERCHED) > lifecycle '
                                     'transition > wall (contact or near-wall) > threat_other > background_flight'},
             'eval_v3_design': EVAL_V3,
             'unchanged': ['observation contract', '11 maneuvers', 'reward v2', 'attacker distributions', 'MaleCNS',
                           'Retina / encoder', 'physics', 'lifecycle', 'accepted runtime', 'M2.3 artifacts']}
    PROTOCOL.write_text(json.dumps(proto, indent=1) + '\n', encoding='utf-8')
    print('frozen', hashlib.sha256(PROTOCOL.read_bytes()).hexdigest())


def protocol():
    p = json.loads(PROTOCOL.read_text(encoding='utf-8'))
    if p['tolerances'] != json.loads(json.dumps(TOLERANCES)) or p['dev_episodes']['sha256'] != hashlib.sha256(
            json.dumps(dev_specs()).encode()).hexdigest():
        raise SystemExit('code differs from the R0 preregistration')
    return p


# ----------------------------------------------------------------- recording ---
def configs():
    import torch  # noqa: F401  (only for checkpoint loading in the main process)
    from game.learning.torch_policy import TorchPolicy, load_checkpoint
    bcm = json.loads((ROOT / 'game/learning/m2_3/torch_bc_metrics.json').read_text(encoding='utf-8'))
    cand = json.loads((ROOT / 'game/learning/m2_3/torch_candidate.json').read_text(encoding='utf-8'))
    bc, _ = load_checkpoint(ROOT / 'game/learning/m2_3/torch_bc_checkpoint.pt', TorchPolicy,
                            expected_sha256=bcm['checkpoint_state_dict_sha256'])
    cd, _ = load_checkpoint(ROOT / 'game/learning/m2_3/torch_candidate.pt', TorchPolicy, expected_sha256=cand['checkpoint_sha256'])
    cfg = {'A_accepted': {'kind': 'accepted'}, 'B_teacher_20ms': {'kind': 'teacher', 'period': 1, 'variant': 'sampled'},
           'C_bc': {'kind': 'mlp', 'params': bc.numpy_params()}, 'D_m23_candidate': {'kind': 'mlp', 'params': cd.numpy_params()}}
    for p in CADENCES[1:]:
        for v in VARIANTS:
            cfg['T_%dms_%s' % (p * 20, v)] = {'kind': 'teacher', 'period': p, 'variant': v}
    return cfg


def record():
    protocol()
    OUT.mkdir(parents=True, exist_ok=True)
    specs = dev_specs()
    cfg = configs()
    todo = [n for n in cfg if not (OUT / ('streams_%s.npz' % n)).exists()]
    chunks = [specs[i::WORKERS] for i in range(WORKERS)]
    with mp.get_context('spawn').Pool(WORKERS, initializer=temporal_r0.worker_init) as pool:
        for name in todo:
            t0 = time.time()
            res = [x for part in pool.map(temporal_r0.record_task, [(name, cfg[name], c) for c in chunks]) for x in part]
            recs = [r for r, _ in res]
            streams = [s for _, s in res]
            keys = [k for k in streams[0] if k != 'click_index']
            np.savez_compressed(OUT / ('streams_%s.npz' % name),
                                **{k: np.concatenate([s[k] for s in streams]) for k in keys},
                                lengths=np.array([len(s['exec']) for s in streams]),
                                click=np.array([s['click_index'] for s in streams]),
                                kind=np.array([1 if r['kind'] == 'threat' else 0 for r in recs], np.int8),
                                seed=np.array([r['seed'] for r in recs]))
            (OUT / ('records_%s.json' % name)).write_text(json.dumps(recs, default=float) + '\n', encoding='utf-8')
            print('recorded %-20s %d episodes %d ticks (%.0f s)' % (name, len(recs), sum(len(s['exec']) for s in streams),
                                                                    time.time() - t0), flush=True)


# ----------------------------------------------------------------- stream statistics ---
def episodes(z):
    off = np.concatenate([[0], np.cumsum(z['lengths'])])
    return [(off[i], off[i + 1]) for i in range(len(z['lengths']))]


def contexts(z):
    """Per-tick exclusive context code."""
    n = int(z['lengths'].sum())
    ctx = np.full(n, 'background_flight', dtype=object)
    for i, (a, b) in enumerate(episodes(z)):
        if z['kind'][i] == 1:
            ctx[a:b] = 'threat_other'
    wall = z['wall'] | z['near_wall']
    ctx[wall] = 'wall'
    ctx[z['life'] == 1] = 'lifecycle_transition'
    ctx[z['life'] == 2] = 'perched'
    for i, (a, b) in enumerate(episodes(z)):
        c = int(z['click'][i])
        if z['kind'][i] == 1 and c >= 0:
            ctx[a + max(0, c - 25):min(b, a + c + 26)] = 'threat_window'
    return ctx


def runs(seq):
    """(start, length, value) runs of a 1-D sequence."""
    if len(seq) == 0:
        return []
    change = np.flatnonzero(np.diff(seq)) + 1
    starts = np.concatenate([[0], change])
    lens = np.diff(np.concatenate([starts, [len(seq)]]))
    return list(zip(starts, lens, seq[starts]))


def pct(a, q):
    return float(np.percentile(a, q)) if len(a) else None


def dist(v):
    v = np.asarray(v, float)
    if not len(v):
        return {'n': 0}
    return {'n': int(len(v)), 'mean_ms': float(v.mean() * 20), 'median_ms': pct(v, 50) * 20, 'p10_ms': pct(v, 10) * 20,
            'p90_ms': pct(v, 90) * 20, 'max_ms': float(v.max() * 20)}


HORIZONS = {20: 1, 40: 2, 60: 3, 100: 5, 150: 8, 200: 10, 300: 15}


def stream_stats(z, key='chosen'):
    ctx = contexts(z)
    grp = np.array([GROUPS.index(GROUP_OF[int(i)]) for i in range(N_MANEUVERS)])
    out = {'ticks': int(len(ctx)), 'context_ticks': {c: int((ctx == c).sum()) for c in sorted(set(ctx))}}
    run_by = {}
    switch_any = {c: {h: [0, 0] for h in HORIZONS} for c in list(set(ctx)) + ['all']}
    autocorr = {}
    per_threat = []
    for i, (a, b) in enumerate(episodes(z)):
        s = z[key][a:b].astype(int)
        g = grp[s]
        cx = ctx[a:b]
        for st, ln, val in runs(s):
            run_by.setdefault((GROUP_OF[int(val)], cx[st]), []).append(ln)
            run_by.setdefault((GROUP_OF[int(val)], 'all'), []).append(ln)
        chg = np.concatenate([[0], np.cumsum(np.diff(s) != 0)])       # change counter
        for h_ms, h in HORIZONS.items():
            if len(s) <= h:
                continue
            anyc = (chg[h:] - chg[:-h]) > 0
            for c in set(cx[:-h]):
                m = cx[:-h] == c
                switch_any[c][h_ms][0] += int(anyc[m].sum())
                switch_any[c][h_ms][1] += int(m.sum())
            switch_any['all'][h_ms][0] += int(anyc.sum())
            switch_any['all'][h_ms][1] += len(anyc)
        if z['kind'][i] == 1:
            c = int(z['click'][i])
            w = (np.arange(len(s)) >= c - 25) & (np.arange(len(s)) <= c + 25) if c >= 0 else np.zeros(len(s), bool)
            sw = np.flatnonzero(np.diff(s) != 0) + 1
            per_threat.append({'decisions': len(s), 'changes': len(sw), 'changes_in_window': int(w[sw].sum()) if len(sw) else 0,
                               'distinct_in_window': int(len(set(s[w]))) if w.any() else 0,
                               'non_none_ticks_in_window': int((s[w] != NONE).sum())})
    allseq = z[key].astype(int)
    p = np.bincount(grp[allseq], minlength=5) / len(allseq)
    chance = float((p ** 2).sum())
    for lag in (1, 2, 5, 10, 25, 50):
        same, tot = 0, 0
        for a, b in episodes(z):
            gg = grp[z[key][a:b].astype(int)]
            if len(gg) > lag:
                same += int((gg[lag:] == gg[:-lag]).sum())
                tot += len(gg) - lag
        ps = same / tot
        nn = []
        for a, b in episodes(z):
            x = (z[key][a:b] != NONE).astype(float)
            if len(x) > lag and x.std() > 0:
                nn.append(np.corrcoef(x[lag:], x[:-lag])[0, 1])
        autocorr[lag * 20] = {'p_same_group': ps, 'kappa_vs_chance': (ps - chance) / (1 - chance),
                              'non_none_indicator_corr_mean': float(np.nanmean(nn)) if nn else None}
    out['group_share'] = dict(zip(GROUPS, p.round(5).tolist()))
    out['run_length'] = {'%s|%s' % k: dist(v) for k, v in sorted(run_by.items())}
    out['p_any_switch_within'] = {c: {h: (v[0] / v[1] if v[1] else None) for h, v in d.items()} for c, d in switch_any.items()}
    out['autocorrelation'] = autocorr
    pt = per_threat
    out['per_threat'] = {'trials': len(pt), 'decisions_mean': float(np.mean([x['decisions'] for x in pt])),
                         'changes_mean': float(np.mean([x['changes'] for x in pt])),
                         'changes_in_window_mean': float(np.mean([x['changes_in_window'] for x in pt])),
                         'changes_in_window_median': pct([x['changes_in_window'] for x in pt], 50),
                         'distinct_in_window_mean': float(np.mean([x['distinct_in_window'] for x in pt])),
                         'non_none_ticks_in_window_mean': float(np.mean([x['non_none_ticks_in_window'] for x in pt]))}
    return out


def bouts(z, key='chosen', gap=5):
    """Threat-response bouts: maximal non-NONE stretches (gaps <= gap ticks) containing an escape;
    turn sequences: runs of same-sign TURN allowing no gap."""
    dur_esc_bout, first_to_escape, turn_seq = [], [], []
    for a, b in episodes(z):
        s = z[key][a:b].astype(int)
        nz = np.flatnonzero(s != NONE)
        if len(nz):
            segs = np.split(nz, np.flatnonzero(np.diff(nz) > gap + 1) + 1)
            for sg in segs:
                vals = s[sg[0]:sg[-1] + 1]
                if np.isin(vals, ESC).any():
                    dur_esc_bout.append(sg[-1] - sg[0] + 1)
                    first_to_escape.append(int(np.flatnonzero(np.isin(vals, ESC))[0]))
        for st, ln, val in runs(s):
            if GROUP_OF[int(val)] == 'TURN':
                turn_seq.append(ln)
    return {'escape_bout_duration': dist(dur_esc_bout), 'bout_onset_to_escape': dist(first_to_escape),
            'turn_run': dist(turn_seq)}


# ----------------------------------------------------------------- open-loop subsampling ---
def hold(labels, period, variant):
    out = np.empty_like(labels)
    held, pending = NONE, None
    rank = np.array([temporal_r0.category_rank(i) for i in range(N_MANEUVERS)])
    for t, lab in enumerate(labels):
        if variant == 'latched' and (pending is None or rank[lab] > rank[pending]):
            pending = lab
        if t % period == 0:
            held = lab if variant == 'sampled' else pending
            pending = None
        out[t] = held
    return out


def openloop():
    d = dict(np.load(ROOT / 'artifacts/m2_3/bc_train.npz'))
    lab = d['label'].astype(int)
    seeds = d['ctx_seed']
    bounds = np.flatnonzero(np.diff(seeds) != 0) + 1
    eps = list(zip(np.concatenate([[0], bounds]), np.concatenate([bounds, [len(lab)]])))
    res = {}
    for p in CADENCES:
        for v in (VARIANTS if p > 1 else ['sampled']):
            held = np.concatenate([hold(lab[a:b], p, v) for a, b in eps])
            ev_total = ev_hit = 0
            delays = []
            for a, b in eps:
                L, Hh = lab[a:b], held[a:b]
                for t in np.flatnonzero(np.isin(L, ESC)):
                    ev_total += 1
                    k = (t // p) * p                                  # decision tick of the interval containing t
                    nxt = k if (v == 'sampled' and t == k) else k + p  # latched: executed at the next decision tick
                    if v == 'sampled':
                        if t == k:
                            ev_hit += 1
                            delays.append(0)
                    else:
                        tt = t if t % p == 0 else nxt
                        if tt < len(Hh) and Hh[tt] == L[t]:
                            ev_hit += 1
                            delays.append(tt - t)
            turn = np.isin(lab, [NAMES.index('TURN_LEFT'), NAMES.index('TURN_RIGHT')])
            win = d['ctx_threat_window']
            res['%dms_%s' % (p * 20, v)] = {
                'agreement_all': float(np.mean(held == lab)), 'agreement_threat_window': float(np.mean(held[win] == lab[win])),
                'agreement_non_none': float(np.mean(held[lab != NONE] == lab[lab != NONE])),
                'escape_events': ev_total, 'O1_escape_event_recall': ev_hit / max(1, ev_total),
                'O2_escape_delay_mean_s': float(np.mean(delays) * DT) if delays else None,
                'O3_turn_agreement': float(np.mean(held[turn] == lab[turn])),
                'saccade_agreement': float(np.mean(held[np.isin(lab, [3, 4])] == lab[np.isin(lab, [3, 4])]))}
            r = res['%dms_%s' % (p * 20, v)]
            r['open_loop_pass'] = bool(r['O1_escape_event_recall'] >= 0.95 and (r['O2_escape_delay_mean_s'] or 0) <= 0.04
                                       and r['O3_turn_agreement'] >= 0.80)
            print(p * 20, v, {k: (round(x, 4) if isinstance(x, float) else x) for k, x in r.items()}, flush=True)
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / 'openloop.json').write_text(json.dumps(res, indent=1) + '\n', encoding='utf-8')


# ----------------------------------------------------------------- credit assignment ---
def credit():
    import torch
    from game.learning import torch_training, training
    from game.learning.reward_v2 import RewardV2
    from game.learning.torch_policy import TorchCritic, TorchPolicy, load_checkpoint
    cand = json.loads((ROOT / 'game/learning/m2_3/torch_candidate.json').read_text(encoding='utf-8'))
    net, meta = load_checkpoint(ROOT / 'game/learning/m2_3/torch_candidate.pt', TorchPolicy, expected_sha256=cand['checkpoint_sha256'])
    critic, _ = load_checkpoint(ROOT / 'artifacts/m2_3/torch/runs/seed_4/critic_it060.pt', TorchCritic)
    reward = RewardV2(**json.loads((ROOT / 'game/learning/benchmark_v2_frozen.json').read_text(encoding='utf-8'))['reward_v2'])
    lam_u, lam_p = meta['lambda_u'], meta['lambda_p']
    units = credit_units()
    with mp.get_context('spawn').Pool(WORKERS, initializer=training.worker_init) as pool:
        eps = [e for ch in pool.map(torch_training.rollout_task, [(net.numpy_params(), u) for u in units]) for e in ch]
    gamma, lam = 0.99, 0.95
    res = {'lambda_u': lam_u, 'lambda_p': lam_p, 'episodes': len(eps),
           'strikes': int(sum(int((e['task'] != 0).sum()) for e in eps)), 'cadences': {}}
    with torch.no_grad():
        V_all = [critic(torch.as_tensor(e['obs'])).double().numpy() for e in eps]
    for p in CADENCES:
        A_list, act_list, win_list, runs_total, runs_hidden, per_run = [], [], [], 0, 0, []
        px, py = [], []
        redundant = pairs = 0
        for e, V in zip(eps, V_all):
            r = e['task'].astype(float) - (reward.unnecessary + lam_u) * e['unnec'] + lam_p * e['perch']
            n = len(r)
            dts = np.arange(0, n, p)
            R = np.array([sum(gamma ** i * r[t + i] for i in range(min(p, n - t))) for t in dts])
            Vd = V[dts]
            last = 0.0 if e['terminal'] else float(V[-1])
            nxt = np.append(Vd[1:], last)
            steps = np.array([min(p, n - t) for t in dts])
            delta = R + gamma ** steps * nxt - Vd
            A = np.zeros(len(dts))
            acc = 0.0
            for j in range(len(dts) - 1, -1, -1):
                acc = delta[j] + (gamma * lam) ** steps[j] * acc * (0.0 if (j == len(dts) - 1) else 1.0)
                A[j] = acc
            act = e['act'][dts].astype(int)
            c = e['click_index']
            win = (np.abs(dts - c) <= 25) if (e['kind'] == 'threat' and c >= 0) else np.zeros(len(dts), bool)
            A_list.append(A)
            act_list.append(act)
            win_list.append(win)
            if len(A) > 1:
                px.append(A[:-1])
                py.append(A[1:])
                same = act[1:] == act[:-1]
                strong = (np.abs(A[1:]) >= 0.05) & (np.abs(A[:-1]) >= 0.05) & (np.sign(A[1:]) == np.sign(A[:-1]))
                redundant += int((same & strong).sum())
                pairs += int(same.sum())
            for st, ln, val in runs(e['act'].astype(int)):
                if val == NONE:
                    continue
                runs_total += 1
                k = len(range(((st + p - 1) // p) * p, st + ln, p))     # decision ticks inside the run
                runs_hidden += int(k == 0)
                per_run.append(k)
        A = np.concatenate(A_list)
        win = np.concatenate(win_list)
        rho = float(np.corrcoef(np.concatenate(px), np.concatenate(py))[0, 1])
        strikes = res['strikes']
        res['cadences']['%dms' % (p * 20)] = {
            'decisions': int(len(A)), 'decisions_per_committed_strike': len(A) / strikes,
            'decisions_in_pm_0.5s_window_per_strike': float(win.sum()) / strikes,
            'frac_abs_adv_ge_0.2': float(np.mean(np.abs(A) >= 0.2)), 'frac_abs_adv_ge_0.05': float(np.mean(np.abs(A) >= 0.05)),
            'window_frac_abs_adv_ge_0.2': float(np.mean(np.abs(A[win]) >= 0.2)),
            'adv_lag1_autocorrelation': rho,
            'effective_window_samples_per_strike': float(win.sum()) / strikes * (1 - rho) / (1 + rho),
            'redundant_same_action_same_sign_pairs_frac': redundant / max(1, pairs),
            'non_none_maneuver_runs': runs_total, 'runs_with_no_decision_tick_frac': runs_hidden / max(1, runs_total),
            'decisions_per_non_none_run_mean': float(np.mean(per_run)) if per_run else None,
            'share_of_abs_adv_mass_in_window': float(np.abs(A[win]).sum() / np.abs(A).sum())}
        print(p * 20, {k: (round(v, 4) if isinstance(v, float) else v) for k, v in res['cadences']['%dms' % (p * 20)].items()},
              flush=True)
    (OUT / 'credit.json').write_text(json.dumps(res, indent=1) + '\n', encoding='utf-8')


# ----------------------------------------------------------------- analysis ---
def closed_loop_eval():
    m22 = _load('m2_2_train')
    rec = {n: json.loads((OUT / ('records_%s.json' % n)).read_text(encoding='utf-8')) for n in configs()}
    base = {'baseline_n4b1c': rec['A_accepted']}
    summ = {}
    for n, r in rec.items():
        ev = m22.evaluate_records(r, base)['candidate']
        z = np.load(OUT / ('streams_%s.npz' % n))
        s = {'hit': ev['threat']['hit_probability'], 'escape_in_window': ev['threat']['escape_in_window_fraction'],
             'median_escape_latency_s': ev['threat']['median_escape_latency_s'],
             'unnecessary_per_min': ev['background_unnecessary_per_min'],
             'perches_per_min': ev['background']['perches_per_min'] or 0.0,
             'wall_contact_fraction': ev['constraints']['wall_contact_fraction']['value'],
             'max_speed_fraction': ev['constraints']['max_speed_fraction']['value'],
             'turn_active_fraction': ev['constraints']['turn_active_fraction']['value'],
             'flags': sorted(k for k, f in ev['anti_cheat_flags'].items() if f), 'admissible': ev['admissible'],
             'hits_by_seed': {str(x['seed']): bool(x['hit']) for x in r if x['kind'] == 'threat'}}
        if 'label' in z.files:
            lab, ch = z['label'].astype(int), z['chosen'].astype(int)
            ctx = contexts(z)
            s['in_run_agreement_all'] = float(np.mean(lab == ch))
            s['in_run_agreement_threat_window'] = float(np.mean(lab[ctx == 'threat_window'] == ch[ctx == 'threat_window']))
            s['in_run_agreement_non_none'] = float(np.mean(lab[lab != NONE] == ch[lab != NONE]))
        summ[n] = s
    ref = summ['B_teacher_20ms']
    for n, s in summ.items():
        if not n.startswith('T_'):
            continue
        t = {'T1': s['escape_in_window'] >= ref['escape_in_window'] - 0.05,
             'T2': (s['median_escape_latency_s'] or 9) <= (ref['median_escape_latency_s'] or 0) + 0.04,
             'T3': s['hit'] <= ref['hit'] + 0.05,
             'T4': abs(s['unnecessary_per_min'] - ref['unnecessary_per_min']) <= max(1.0, 0.2 * ref['unnecessary_per_min']),
             'T5': s['perches_per_min'] >= max(0.275, 0.8 * ref['perches_per_min']),
             'T6': s['wall_contact_fraction'] <= ref['wall_contact_fraction'] + 0.01
             and s['max_speed_fraction'] <= ref['max_speed_fraction'] + 0.01,
             'T7': not (set(s['flags']) - set(ref['flags']))
             and abs(s['turn_active_fraction'] - ref['turn_active_fraction']) <= 0.2 * ref['turn_active_fraction']}
        s['tolerance_checks'] = t
        s['closed_loop_pass'] = all(t.values())
        keys = sorted(set(s['hits_by_seed']) & set(ref['hits_by_seed']))
        b = sum(ref['hits_by_seed'][k] and not s['hits_by_seed'][k] for k in keys)
        c = sum(s['hits_by_seed'][k] and not ref['hits_by_seed'][k] for k in keys)
        from scipy.stats import binomtest
        s['paired_vs_reference'] = {'n': len(keys), 'only_ref_hit': b, 'only_this_hit': c,
                                    'mcnemar_p': binomtest(c, b + c, 0.5).pvalue if b + c else 1.0}
    return summ


def analyze():
    proto = protocol()
    cfg = configs()
    streams = {n: dict(np.load(OUT / ('streams_%s.npz' % n))) for n in cfg}
    res = {'protocol_sha256': hashlib.sha256(PROTOCOL.read_bytes()).hexdigest(), 'dev_episodes': proto['dev_episodes']}
    res['stream_stats'] = {}
    for n in ('A_accepted', 'B_teacher_20ms', 'C_bc', 'D_m23_candidate'):
        z = streams[n]
        res['stream_stats'][n] = {'decision_stream': stream_stats(z, 'chosen'), 'executed_stream': stream_stats(z, 'exec'),
                                  'bouts_decision': bouts(z, 'chosen'), 'bouts_executed': bouts(z, 'exec')}
    res['closed_loop'] = closed_loop_eval()
    ol = json.loads((OUT / 'openloop.json').read_text(encoding='utf-8'))
    res['open_loop'] = ol
    res['credit'] = json.loads((OUT / 'credit.json').read_text(encoding='utf-8'))
    verdict = {}
    for p in CADENCES[1:]:
        for v in VARIANTS:
            key = '%dms_%s' % (p * 20, v)
            cl = res['closed_loop']['T_' + key]
            verdict[key] = {'closed_loop_pass': cl['closed_loop_pass'], 'open_loop_pass': ol[key]['open_loop_pass'],
                            'pass': cl['closed_loop_pass'] and ol[key]['open_loop_pass'],
                            'failed': [k for k, x in cl['tolerance_checks'].items() if not x] +
                                      [k for k in ('O1', 'O2', 'O3') if not {
                                          'O1': ol[key]['O1_escape_event_recall'] >= 0.95,
                                          'O2': (ol[key]['O2_escape_delay_mean_s'] or 0) <= 0.04,
                                          'O3': ol[key]['O3_turn_agreement'] >= 0.80}[k]]}
    passing = [int(k.split('ms')[0]) for k, v in verdict.items() if v['pass']]
    res['verdict_by_cadence'] = verdict
    res['coarsest_passing_ms'] = max(passing) if passing else None
    TRACK.mkdir(parents=True, exist_ok=True)
    (TRACK / 'r0_results.json').write_text(json.dumps(res, indent=1, default=float) + '\n', encoding='utf-8')
    for n, s in res['closed_loop'].items():
        print('%-20s hit %.3f win %.2f lat %s U %.2f P %.2f wall %.3f turn %.3f flags %s agree %s pass %s' % (
            n, s['hit'], s['escape_in_window'], s['median_escape_latency_s'], s['unnecessary_per_min'], s['perches_per_min'],
            s['wall_contact_fraction'], s['turn_active_fraction'], s['flags'], s.get('in_run_agreement_non_none'),
            s.get('closed_loop_pass')))
    print(json.dumps(verdict, indent=1))
    print('coarsest passing cadence (ms):', res['coarsest_passing_ms'])


if __name__ == '__main__':
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('mode')
    a = ap.parse_args()
    {'freeze': freeze, 'record': record, 'openloop': openloop, 'credit': credit, 'analyze': analyze}[a.mode]()
