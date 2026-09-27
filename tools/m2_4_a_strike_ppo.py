"""M2.4-A: threat-dense, strike-centric PPO (training data weighting / sampling only).

Unchanged: 50 Hz decisions, the 11 maneuvers, the observation contract, reward v2, constraints,
attacker distributions, MaleCNS, Retina / encoder, physics, lifecycle, the accepted runtime, the
PyTorch learner (M2.3 torch_policy), the BC warm start, the KL anchor, entropy control, dual warm-up.

Changed (training only):
- two rollout streams per iteration: a THREAT stream of many short discrete committed-threat trials
  (family-stratified; the long perched_or_fallback family is sampled less and importance-weighted
  back to equal family weight) and a BACKGROUND stream of background episodes for constraint
  estimation;
- strike-balanced actor loss: every threat trial (one committed strike) receives equal total actor
  weight, split evenly over its actor-window ticks; background episodes share a fixed fraction of the
  actor weight; KL anchor and entropy are computed over all collected ticks;
- an actor credit window per threat trial (collector-side event times; never observed by the policy);
- strike-grouped actor minibatches, a critic trained on all ticks with extra critic-only epochs.

    python tools/m2_4_a_strike_ppo.py dev --variant A_ref|B_strike|C_window --seed 201 [--iters 20]
    python tools/m2_4_a_strike_ppo.py dev-eval --variant V --seed 201   (TRAIN-VAL of a finished dev run)
    python tools/m2_4_a_strike_ppo.py window-select      (TRAIN-only; preregistered rule)
    python tools/m2_4_a_strike_ppo.py dev-summary
    python tools/m2_4_a_strike_ppo.py freeze
    python tools/m2_4_a_strike_ppo.py train --seed K
    python tools/m2_4_a_strike_ppo.py screen | confirm | select | compare | eval-final
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import importlib.util
import json
import math
import multiprocessing as mp
import os
from pathlib import Path
import sys
import time

os.environ.setdefault('NUMBA_NUM_THREADS', '1')
os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')
os.environ.setdefault('CUBLAS_WORKSPACE_CONFIG', ':4096:8')
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import numpy as np  # noqa: E402
import torch  # noqa: E402
from torch.distributions import Categorical  # noqa: E402

from game.learning import baseline_eval, strike_training, training, trials  # noqa: E402
from game.learning.contracts import MANEUVERS, N_MANEUVERS  # noqa: E402
from game.learning.reward_v2 import RewardV2  # noqa: E402
from game.learning.torch_policy import (TorchPolicy, default_device, gae, init_critic, kl_to_reference,  # noqa: E402
                                        load_checkpoint, save_checkpoint, set_determinism, state_dict_sha256,
                                        value_loss)


def _load(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / ('tools/%s.py' % name))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


MT = _load('m2_3_torch')
BCT, M22 = MT.BCT, MT.M22
OUT = ROOT / 'artifacts/m2_4_a'
TRACK = ROOT / 'game/learning/m2_4_a'
PROTOCOL_FILE = TRACK / 'protocol.json'
CANDIDATE_FILE = TRACK / 'candidate.json'
CANDIDATE_CKPT = TRACK / 'candidate.pt'
CANDIDATE_NPZ = ROOT / 'game/learning/checkpoints/m2_4_a_candidate.npz'
WORKERS = 7
NONE = [m.name for m in MANEUVERS].index('NONE')
ESCAPES = [i for i, m in enumerate(MANEUVERS) if m.escape]
FAMS = [f.name for f in trials.THREAT_FAMILIES]
BGS = [c.name for c in trials.BACKGROUND_FAMILIES]
LEVELS = list(trials.ATTACKERS)
WINDOWS = ('full', 'engage', 'click50', 'click25')

# ----------------------------------------------------------------- configuration ---
COMMON = {
    'learner': 'PyTorch M2.3 learner (TorchPolicy 2,315 params + training-only TorchCritic), float32 CUDA updates',
    'init': 'accepted M2.3 PyTorch BC checkpoint (state_dict c6c21c23...), identical for every seed',
    'reference': 'frozen deep copy of the BC policy (KL anchor), never updated',
    'critic_init': 'init_critic(training seed + 1), as M2.3', 'critic_warmup_iterations': 3,
    'lr_policy': 3e-4, 'lr_critic': 1e-3, 'adam': [0.9, 0.999, 1e-8], 'gamma': 0.99, 'gae_lambda': 0.95,
    'ppo_clip': 0.2, 'grad_clip_norm': 0.5, 'update_epochs': 4,
    'kl_anchor': {'beta_start': 1.0, 'hold_until_iteration': 15, 'beta_end': 0.1, 'decay_until_iteration': 45},
    'entropy': {'target_fraction': 0.8, 'coef_init': 0.001, 'coef_min': 1e-4, 'coef_max': 0.05, 'gain': 0.5},
    'dual': {'min_warmup_iterations': 15, 'stable_iterations_required': 3,
             'conditional_escape_check': 'synthetic strong one-sided DNp01 escape probability >= 0.2 and >= 10 x quiet, '
                                         'and threat-trial escape fraction >= 0.5',
             'unnecessary_target_per_min': 0.9 * 5.36, 'perch_target_per_min': 1.5 * 0.275, 'step': 0.02,
             'ema_alpha': 0.3, 'lambda_u_max': 10.0, 'lambda_p_max': 5.0,
             'measurement': 'background stream only'},
    'reward': 'reward v2 unchanged (+1 miss / -1 hit at resolution; 0.005891 + lambda_u per unnecessary escape; '
              '+lambda_p per perch)',
    'iterations': 60, 'checkpoint_every': 10, 'rollout_seed_salt': 2410,
}
VARIANTS = {
    'A_ref': {'sampling': {'mode': 'm23', 'units': 7, 'background_per_unit': 1, 'threat_per_unit': 6,
                           'family_shares': 'uniform'},
              'weighting': {'mode': 'uniform'}, 'actor_window': 'full',
              'actor_minibatch': {'mode': 'random_ticks', 'size': 4096},
              'critic': {'epochs': 4, 'minibatch': 4096}, 'kl_entropy_samples': 'same minibatch'},
    'B_strike': {'sampling': {'mode': 'threat_dense', 'workers': 7, 'threat_per_worker': 14, 'background_per_worker': 1,
                              'family_shares': {'direct': 0.3, 'hover': 0.3, 'wall': 0.3, 'perched_or_fallback': 0.1},
                              'attacker': 'uniform', 'balance_workers': True},
                 'weighting': {'mode': 'strike_balanced', 'background_actor_share': 0.25, 'family_importance': True},
                 'actor_window': 'full', 'actor_minibatch': {'mode': 'unit_groups', 'groups': 4},
                 'critic': {'epochs': 8, 'minibatch': 4096}, 'kl_entropy_samples': 'uniform random 4096 of all ticks'},
}
VARIANTS['C_window'] = dict(copy.deepcopy(VARIANTS['B_strike']), actor_window='SELECTED')
WINDOW_RULE = ('TRAIN-only, from the B_strike development rollouts: among the candidate windows full, engage '
               '(engagement onset -> end), click50 (click - 1.0 s -> end), click25 (click - 0.5 s -> end), choose the '
               'window with the FEWEST retained ticks that captures >= 90 % of the within-trial |advantage| mass and '
               '>= 90 % of the within-trial escape actions; otherwise full')
DEV_RULE = ('revised before any C_window result was visible (window already frozen = engage from the B_strike '
            'TRAIN rollouts). A variant V in {B_strike, C_window} is ELIGIBLE if (i) no collapse over its development run '
            '(NONE share < 0.995 and synthetic strong-DNp01 escape probability >= 0.2 at every iteration); (ii) '
            'statistical efficiency vs A_ref: mean post-warm-up (iterations 4+) cross-half actor-gradient cosine >= that '
            'of A_ref AND mean effective strikes per update (Kish, actor weights) >= 2 x A_ref; (iii) its final policy on '
            'TRAIN-VAL is M2.1-admissible (unnecessary <= 5.36 / min, perches >= 0.275 / min, movement constraints, no '
            'anti-cheat flag) with threat-window escape >= 0.3. Choice: prefer the simpler B_strike when eligible; choose '
            'C_window instead only if C is eligible AND shows a clear advantage over B: (a) TRAIN-VAL hit lower than B '
            'with non-overlapping Wilson 95 % intervals, or (b) post-warm-up cross-half cosine >= B + 0.05 AND '
            'post-warm-up minibatch relative gradient variance <= 0.75 x B. If B is not eligible, C_window if eligible. '
            'If neither is eligible: development NO-GO, no official training budget is spent. Rollout hit rate and '
            'scalar reward are reported but never used for the choice.')


def cfg(variant):
    c = dict(copy.deepcopy(COMMON), **copy.deepcopy(VARIANTS[variant]))
    if c['actor_window'] == 'SELECTED':
        sel = TRACK / 'window_selection.json'
        c['actor_window'] = json.loads(sel.read_text(encoding='utf-8'))['selected'] if sel.exists() else 'engage'
    return c


# ----------------------------------------------------------------- sampling ---
def worker_specs(rng, dev_seeds, S):
    def seed():
        while True:
            s = int(rng.integers(20_000_000, 25_000_000))
            if s not in dev_seeds:
                return s
    out = []
    if S['mode'] == 'm23':
        for _ in range(S['units']):
            u = [('background', BGS[int(rng.integers(4))], None, seed()) for _ in range(S['background_per_unit'])]
            u += [('threat', FAMS[int(rng.integers(4))], LEVELS[int(rng.integers(3))], seed())
                  for _ in range(S['threat_per_unit'])]
            out.append(u)
    else:
        p = np.array([S['family_shares'][f] for f in FAMS])
        drawn = []
        for _ in range(S['workers']):
            drawn += [('background', BGS[int(rng.integers(4))], None, seed()) for _ in range(S['background_per_worker'])]
            drawn += [('threat', FAMS[int(rng.choice(4, p=p))], LEVELS[int(rng.integers(3))], seed())
                      for _ in range(S['threat_per_worker'])]
        if S.get('balance_workers'):
            # Longest-processing-time assignment of the SAME drawn episodes (throughput only; the sample is unchanged).
            load = [0.0] * S['workers']
            out = [[] for _ in range(S['workers'])]
            for sp in sorted(drawn, key=lambda x: -EXPECTED_TICKS[x[1]]):
                k = int(np.argmin(load))
                out[k].append(sp)
                load[k] += EXPECTED_TICKS[sp[1]]
        else:
            n = S['background_per_worker'] + S['threat_per_worker']
            out = [drawn[i * n:(i + 1) * n] for i in range(S['workers'])]
    return out


# Mean ticks per episode on the R0 development episodes (mapped teacher); used only to balance worker load.
EXPECTED_TICKS = {'direct': 289, 'hover': 284, 'wall': 231, 'perched_or_fallback': 1463, 'free_flight': 3000,
                  'glancing_pass': 1000, 'aborted_approach': 1000, 'hover_only': 1000}


def family_importance(S):
    if S.get('family_shares') == 'uniform':
        return {f: 1.0 for f in FAMS}
    return {f: 0.25 / S['family_shares'][f] for f in FAMS}


# ----------------------------------------------------------------- weighting ---
def window_mask(e, window):
    n = len(e['act'])
    m = np.ones(n, bool)
    if e['kind'] != 'threat' or window == 'full':
        return m
    t = np.arange(n)
    c, g = e['click_index'], e['engage_index']
    if window == 'engage':
        start = g if g >= 0 else 0
    elif window == 'click50':
        start = c - 50 if c >= 0 else (g if g >= 0 else 0)
    elif window == 'click25':
        start = c - 25 if c >= 0 else (g if g >= 0 else 0)
    else:
        raise ValueError(window)
    m = t >= max(0, start)
    if not m.any():
        m[-1] = True
    return m


def actor_weights(eps, C):
    """Per-tick actor weights (sum 1 over the batch) and unit ids.

    uniform:          w_t = 1 / N_ticks (M2.3 reference)
    strike_balanced:  threat trial i with actor-window ticks W_i:  w_t = (1 - rho_bg) * q_i / sum_j q_j / |W_i|
                      background episode b (all ticks):             w_t = rho_bg / B / n_b
                      q_i = family importance weight 0.25 / sampling share (1 for uniform family sampling)
    """
    W = C['weighting']
    n_tot = sum(len(e['act']) for e in eps)
    w, unit, mask = [], [], []
    thr = [e for e in eps if e['kind'] == 'threat']
    bg = [e for e in eps if e['kind'] == 'background']
    imp = family_importance(C['sampling'])
    qsum = sum(imp[e['name']] for e in thr)
    for u, e in enumerate(eps):
        n = len(e['act'])
        m = window_mask(e, C['actor_window'])
        if W['mode'] == 'uniform':
            wt = np.full(n, 1.0 / n_tot)
        elif e['kind'] == 'threat':
            wt = np.where(m, (1 - W['background_actor_share']) * imp[e['name']] / qsum / m.sum(), 0.0)
        else:
            wt = np.full(n, W['background_actor_share'] / len(bg) / n)
        w.append(wt)
        unit.append(np.full(n, u))
        mask.append(m if W['mode'] != 'uniform' else np.ones(n, bool))
    return np.concatenate(w), np.concatenate(unit), np.concatenate(mask)


# ----------------------------------------------------------------- diagnostics ---
def unit_gradients(policy, X, A, adv, w, unit, n_units, dev, chunk=8192):
    """Per-unit gradient of the weighted policy-gradient loss -sum_t w_t A_t log pi(a_t | x_t) at the
    current parameters (ratio 1). Returns (n_units, n_params)."""
    from torch.func import functional_call, grad, vmap
    params = {k: v.detach() for k, v in policy.named_parameters()}
    buffers = {k: v for k, v in policy.named_buffers()}

    def f(p, x, a, c):
        logits = functional_call(policy, (p, buffers), (x[None],))
        return -c * torch.log_softmax(logits, -1)[0].gather(0, a.unsqueeze(0))[0]
    G = torch.zeros(n_units, sum(v.numel() for v in params.values()), device=dev)
    idx = np.flatnonzero(w > 0)
    for s in range(0, len(idx), chunk):
        b = torch.as_tensor(idx[s:s + chunk], device=dev)
        coef = torch.as_tensor((w * adv)[idx[s:s + chunk]], dtype=torch.float32, device=dev)
        g = vmap(grad(f), in_dims=(None, 0, 0, 0))(params, X[b], A[b], coef)
        flat = torch.cat([g[k].flatten(1) for k in params], 1)
        G.index_add_(0, torch.as_tensor(unit[idx[s:s + chunk]], device=dev), flat)
    return G


def gradient_diagnostics(G, rng, is_threat, n_groups=8):
    norms = G.norm(dim=1).cpu().numpy()
    tot = G.sum(0)
    out = {'units': int(G.shape[0])}
    s = norms.sum()
    srt = np.sort(norms)[::-1]
    out['unit_grad_norm_share_max'] = float(srt[0] / s)
    out['unit_grad_norm_share_top10pct'] = float(srt[:max(1, len(srt) // 10)].sum() / s)
    out['effective_units_kish_grad'] = float(s ** 2 / (norms ** 2).sum())
    thr = np.flatnonzero(is_threat)
    tn = norms[thr]
    out['threat_unit_grad_norm'] = {'mean': float(tn.mean()), 'cv': float(tn.std() / tn.mean()),
                                    'p90_over_median': float(np.percentile(tn, 90) / np.median(tn))}
    out['effective_strikes_kish_grad'] = float(tn.sum() ** 2 / (tn ** 2).sum())
    cos = []
    for _ in range(5):
        perm = rng.permutation(G.shape[0])
        h1, h2 = G[perm[:len(perm) // 2]].sum(0), G[perm[len(perm) // 2:]].sum(0)
        cos.append(float(torch.nn.functional.cosine_similarity(h1, h2, dim=0)))
    out['cross_half_cosine'] = float(np.mean(cos))
    perm = rng.permutation(G.shape[0])
    groups = [G[perm[i::n_groups]].sum(0) * n_groups for i in range(n_groups)]
    gm = torch.stack(groups)
    out['minibatch_rel_variance'] = float(((gm - tot) ** 2).sum(1).mean() / (tot ** 2).sum())
    cs = [float(torch.nn.functional.cosine_similarity(gm[i], gm[j], dim=0)) for i in range(n_groups) for j in range(i + 1, n_groups)]
    out['minibatch_pairwise_cosine'] = float(np.mean(cs))
    return out


def window_stats(eps, ADV, off):
    res = {w: {'adv_mass': 0.0, 'ticks': 0, 'escapes': 0} for w in WINDOWS}
    tot_mass = tot_ticks = tot_esc = 0.0
    for i, e in enumerate(eps):
        if e['kind'] != 'threat':
            continue
        a = np.abs(ADV[off[i]:off[i + 1]])
        esc = np.isin(e['act'], ESCAPES)
        tot_mass += a.sum()
        tot_ticks += len(a)
        tot_esc += esc.sum()
        for w in WINDOWS:
            m = window_mask(e, w)
            res[w]['adv_mass'] += float(a[m].sum())
            res[w]['ticks'] += int(m.sum())
            res[w]['escapes'] += int(esc[m].sum())
    return {w: {'adv_mass_share': v['adv_mass'] / max(tot_mass, 1e-12), 'tick_share': v['ticks'] / max(tot_ticks, 1),
                'escape_share': v['escapes'] / max(tot_esc, 1)} for w, v in res.items()}


# ----------------------------------------------------------------- training ---
def ppo_protocol():
    if not PROTOCOL_FILE.exists():
        raise SystemExit('freeze the M2.4-A protocol first')
    p = json.loads(PROTOCOL_FILE.read_text(encoding='utf-8'))
    if p['ppo'] != json.loads(json.dumps(cfg(p['method']))):
        raise SystemExit('code differs from the frozen M2.4-A protocol')
    return p, MT.sha_file(PROTOCOL_FILE)


def train_run(train_seed, C, out, iterations=None, proto=None, proto_sha=None):
    iterations = iterations or C['iterations']
    out.mkdir(parents=True, exist_ok=True)
    dev = default_device()
    if dev.type != 'cuda':
        raise SystemExit('M2.4-A updates must run on CUDA')
    set_determinism(train_seed)
    bc_net, bc_meta = MT.load_bc()
    ref = copy.deepcopy(bc_net).to(dev).eval()
    for p in ref.parameters():
        p.requires_grad_(False)
    policy = copy.deepcopy(bc_net).to(dev)
    critic = init_critic(train_seed + 1).to(dev)
    b1, b2, eps_adam = C['adam']
    opt_p = torch.optim.Adam(policy.parameters(), lr=C['lr_policy'], betas=(b1, b2), eps=eps_adam)
    opt_v = torch.optim.Adam(critic.parameters(), lr=C['lr_critic'], betas=(b1, b2), eps=eps_adam)
    reward = RewardV2(**json.loads((ROOT / 'game/learning/benchmark_v2_frozen.json').read_text(encoding='utf-8'))['reward_v2'])
    D, K, E = C['dual'], C['kl_anchor'], C['entropy']
    lam_u = lam_p = 0.0
    ema_u = ema_p = None
    ent_coef, ent_target = E['coef_init'], None
    stable_run, dual_since = 0, None
    rng = np.random.default_rng([train_seed, C['rollout_seed_salt']])
    dev_seeds = BCT.dev_seeds()
    head = M22.git_head()
    log = (out / 'log.jsonl').open('a', encoding='utf-8')
    steps = strikes_seen = 0
    (out / 'run_info.json').write_text(json.dumps({'training_seed': train_seed, 'code_commit': head, 'config': C,
                                                   'protocol_sha256': proto_sha, 'environment': MT.env_info(),
                                                   'bc_parent_sha256': bc_meta['checkpoint_state_dict_sha256']},
                                                  indent=1) + '\n', encoding='utf-8')
    uniform = C['weighting']['mode'] == 'uniform'
    with mp.get_context('spawn').Pool(WORKERS, initializer=training.worker_init) as pool:
        for it in range(1, iterations + 1):
            t0 = time.time()
            specs = worker_specs(rng, dev_seeds, C['sampling'])
            eps = [e for ch in pool.map(strike_training.rollout_task, [(policy.numpy_params(), sp) for sp in specs]) for e in ch]
            t_roll = time.time() - t0
            thr = [e for e in eps if e['kind'] == 'threat']
            bg = [e for e in eps if e['kind'] == 'background']
            bg_min = sum(e['seconds'] for e in bg) / 60
            U = sum(int(e['unnec'].sum()) for e in bg) / bg_min
            Pr = sum(int(e['perch'].sum()) for e in bg) / bg_min
            ema_u = U if ema_u is None else (1 - D['ema_alpha']) * ema_u + D['ema_alpha'] * U
            ema_p = Pr if ema_p is None else (1 - D['ema_alpha']) * ema_p + D['ema_alpha'] * Pr
            X = np.concatenate([e['obs'] for e in eps]).astype(np.float32)
            Aa = np.concatenate([e['act'] for e in eps]).astype(np.int64)
            off = np.concatenate([[0], np.cumsum([len(e['act']) for e in eps])])
            Xt, At = torch.as_tensor(X, device=dev), torch.as_tensor(Aa, device=dev)
            with torch.no_grad():
                V = critic(Xt).double().cpu().numpy()
                lo = policy(Xt)
                logp_old = Categorical(logits=lo).log_prob(At)
                H_now = float(Categorical(logits=lo).entropy().mean())
                ref_logits = ref(Xt)
            ADV, RET = [], []
            for i, e in enumerate(eps):
                r = e['task'].astype(np.float64) - (reward.unnecessary + lam_u) * e['unnec'] + lam_p * e['perch']
                v = V[off[i]:off[i + 1]]
                d = np.zeros(len(r))
                if e['terminal']:
                    d[-1], last = 1.0, 0.0
                else:
                    last = float(v[-1])
                a, rt = gae(r, v, d, last, C['gamma'], C['gae_lambda'])
                ADV.append(a)
                RET.append(rt)
            ADV, RET = np.concatenate(ADV), np.concatenate(RET)
            w, unit, mask = actor_weights(eps, C)
            act_idx = np.flatnonzero(w > 0)
            mu = float((w * ADV).sum() / w.sum())
            sd = float(np.sqrt((w * (ADV - mu) ** 2).sum() / w.sum())) + 1e-8
            ADVn = (ADV - mu) / sd
            if ent_target is None:
                ent_target = E['target_fraction'] * H_now
            is_thr = np.array([e['kind'] == 'threat' for e in eps])
            committed = sum(1 for e in thr if e['click_index'] >= 0)
            # effective-sample report (pre-update)
            td = time.time()
            G = unit_gradients(policy, Xt, At, ADVn, w, unit, len(eps), dev)
            gdiag = gradient_diagnostics(G, rng, is_thr)
            del G
            px, py = [], []
            for i in range(len(eps)):
                sel = np.flatnonzero(mask[off[i]:off[i + 1]] & (w[off[i]:off[i + 1]] > 0))
                a = ADVn[off[i]:off[i + 1]][sel]
                if len(a) > 1:
                    px.append(a[:-1])
                    py.append(a[1:])
            rho = float(np.corrcoef(np.concatenate(px), np.concatenate(py))[0, 1])
            unit_w = np.array([w[off[i]:off[i + 1]].sum() for i in range(len(eps))])
            thr_w = unit_w[is_thr]
            win_ticks = np.array([int((w[off[i]:off[i + 1]] > 0).sum()) for i in range(len(eps))])
            eff = {'committed_strikes': committed, 'unique_strike_units': int(is_thr.sum()), 'background_episodes': len(bg),
                   'total_tick_samples': int(len(Aa)), 'actor_loss_tick_samples': int(len(act_idx)),
                   'mean_ticks_per_strike': float(np.mean([len(e['act']) for e in thr])),
                   'mean_actor_ticks_per_strike': float(win_ticks[is_thr].mean()),
                   'advantage_lag1_autocorrelation': rho,
                   'effective_independent_actor_samples': float(win_ticks[is_thr].sum() * (1 - rho) / (1 + rho)),
                   'effective_independent_actor_samples_per_strike': float(win_ticks[is_thr].mean() * (1 - rho) / (1 + rho)),
                   'actor_weight_per_strike': {'mean': float(thr_w.mean()), 'min': float(thr_w.min()), 'max': float(thr_w.max()),
                                               'total_threat_share': float(thr_w.sum())},
                   'effective_strikes_kish_weight': float(thr_w.sum() ** 2 / (thr_w ** 2).sum()),
                   'gradient': gdiag, 'diag_seconds': time.time() - td}
            wstats = window_stats(eps, ADV, off)
            beta = MT.beta_at(it, K)
            update_policy = it > C['critic_warmup_iterations']
            torch.cuda.synchronize()
            t2 = time.time()
            wt = torch.as_tensor(w, dtype=torch.float32, device=dev)
            An = torch.as_tensor(ADVn, dtype=torch.float32, device=dev)
            Rt = torch.as_tensor(RET, dtype=torch.float32, device=dev)
            stats = {k: [] for k in ('policy_loss', 'kl_bc', 'entropy', 'clipfrac', 'approx_kl', 'grad_norm_policy', 'value_loss')}
            nonfinite = 0
            N = len(Aa)
            if update_policy:
                for _ in range(C['update_epochs']):
                    if uniform:
                        perm = rng.permutation(N)
                        batches = [perm[s:s + C['actor_minibatch']['size']] for s in range(0, N, C['actor_minibatch']['size'])]
                    else:
                        tu = rng.permutation(np.flatnonzero(is_thr))
                        bu = rng.permutation(np.flatnonzero(~is_thr))
                        M = C['actor_minibatch']['groups']
                        batches = []
                        for m in range(M):
                            us = np.concatenate([tu[m::M], bu[m::M]])
                            batches.append(act_idx[np.isin(unit[act_idx], us)])
                    for bidx in batches:
                        b = torch.as_tensor(bidx, device=dev)
                        logits = policy(Xt[b])
                        dist = Categorical(logits=logits)
                        ratio = torch.exp(dist.log_prob(At[b]) - logp_old[b])
                        surr = torch.min(ratio * An[b], torch.clamp(ratio, 1 - C['ppo_clip'], 1 + C['ppo_clip']) * An[b])
                        pl = -(wt[b] * surr).sum() / wt[b].sum()
                        if uniform:
                            kl = kl_to_reference(logits, ref_logits[b]).mean()
                            ent = dist.entropy().mean()
                        else:
                            sub = torch.as_tensor(rng.integers(0, N, 4096), device=dev)
                            lg = policy(Xt[sub])
                            kl = kl_to_reference(lg, ref_logits[sub]).mean()
                            ent = Categorical(logits=lg).entropy().mean()
                        loss = pl - ent_coef * ent + beta * kl
                        opt_p.zero_grad(set_to_none=True)
                        loss.backward()
                        gn = torch.nn.utils.clip_grad_norm_(policy.parameters(), C['grad_clip_norm'])
                        if torch.isfinite(gn):
                            opt_p.step()
                        else:
                            nonfinite += 1
                        with torch.no_grad():
                            stats['clipfrac'].append(((ratio - 1).abs() > C['ppo_clip']).float().mean())
                            stats['approx_kl'].append((logp_old[b] - dist.log_prob(At[b])).mean())
                        for k, v in (('policy_loss', pl), ('kl_bc', kl), ('entropy', ent), ('grad_norm_policy', gn)):
                            stats[k].append(v.detach())
            for _ in range(C['critic']['epochs']):
                perm = torch.as_tensor(rng.permutation(N), device=dev)
                for s in range(0, N, C['critic']['minibatch']):
                    b = perm[s:s + C['critic']['minibatch']]
                    vl = value_loss(critic(Xt[b]), Rt[b])
                    opt_v.zero_grad(set_to_none=True)
                    vl.backward()
                    gv = torch.nn.utils.clip_grad_norm_(critic.parameters(), C['grad_clip_norm'])
                    if torch.isfinite(gv):
                        opt_v.step()
                    else:
                        nonfinite += 1
                    stats['value_loss'].append(vl.detach())
            torch.cuda.synchronize()
            t_gpu = time.time() - t2
            with torch.no_grad():
                P_new = torch.softmax(policy(Xt), -1)
                kl_roll = float(kl_to_reference(policy(Xt), ref_logits).mean())
                V_new = critic(Xt).double().cpu().numpy()
            smean = {k: (float(torch.stack(v).mean()) if v else None) for k, v in stats.items()}
            resp = BCT.escape_response(policy.to_numpy_model())
            cond = MT.conditional_escape(eps, P_new.double().cpu().numpy())
            thr_esc = float(np.mean([bool(e['escape'].any()) for e in thr]))
            cond_ok = resp['escape_prob_strong_left'] >= 0.2 and resp['escape_prob_strong_left'] >= 10 * resp['escape_prob_quiet'] \
                and thr_esc >= 0.5
            stable_run = stable_run + 1 if cond_ok else 0
            if dual_since is None and it >= D['min_warmup_iterations'] and stable_run >= D['stable_iterations_required']:
                dual_since = it
            if dual_since is not None and cond_ok:
                tu_, tp_ = D['unnecessary_target_per_min'], D['perch_target_per_min']
                lam_u = float(np.clip(lam_u + D['step'] * (ema_u - tu_) / tu_, 0, D['lambda_u_max']))
                lam_p = float(np.clip(lam_p + D['step'] * (tp_ - ema_p) / tp_, 0, D['lambda_p_max']))
            ent_coef = float(np.clip(ent_coef * np.exp(E['gain'] * (ent_target - H_now) / ent_target), E['coef_min'], E['coef_max']))
            steps += N
            strikes_seen += committed
            counts = np.bincount(Aa, minlength=N_MANEUVERS)
            row = {'iteration': it, 'env_steps': steps, 'committed_strikes_seen': strikes_seen, 'decisions': N,
                   'seconds': time.time() - t0, 'timing': {'rollout_s': t_roll, 'gpu_update_s': t_gpu},
                   'threat_trials': len(thr), 'family_counts': {f: sum(1 for e in thr if e['name'] == f) for f in FAMS},
                   'hit_rate': float(np.mean([e['hit'] for e in thr])), 'threat_trial_any_escape': thr_esc,
                   'background_minutes': bg_min, 'unnecessary_per_min': U, 'perch_per_min': Pr, 'ema_unnecessary': ema_u,
                   'ema_perch': ema_p, 'lambda_u': lam_u, 'lambda_p': lam_p, 'dual_active_since': dual_since,
                   'conditional_escape_ok': cond_ok, 'beta_kl': beta, 'kl_policy_bc_rollout': kl_roll,
                   'entropy_rollout_before_update': H_now, 'entropy_target': ent_target, 'entropy_coef_next': ent_coef,
                   'none_share': float(counts[NONE] / counts.sum()), 'escape_action_share': float(np.isin(Aa, ESCAPES).mean()),
                   'turn_fraction': float(np.mean(np.concatenate([e['turn'] for e in eps]))),
                   'wall_fraction': float(np.mean(np.concatenate([e['wall'] for e in eps]))),
                   'max_speed_fraction': float(np.mean(np.concatenate([e['maxspd'] for e in eps]))),
                   **smean, 'nonfinite_gradient_steps': nonfinite,
                   'explained_variance_after': float(1 - np.var(RET - V_new) / (np.var(RET) + 1e-12)),
                   'escape_response': resp, 'conditional_escape': cond, 'effective_samples': eff, 'window_stats': wstats}
            log.write(json.dumps(row, default=float) + '\n')
            log.flush()
            g = eff['gradient']
            print('seed %d it %2d hit %.2f U %.1f P %.2f lam_u %.3f KL %.5f H %.4f NONE %.4f esc@L3 %.2f | strikes %d '
                  'effS %.0f rho %.3f cos %.3f relvar %.2f topshare %.2f | roll %.0fs gpu %.1fs' % (
                      train_seed, it, row['hit_rate'], U, Pr, lam_u, kl_roll, H_now, row['none_share'],
                      resp['escape_prob_strong_left'], committed, eff['effective_strikes_kish_weight'], rho,
                      g['cross_half_cosine'], g['minibatch_rel_variance'], g['unit_grad_norm_share_top10pct'], t_roll, t_gpu),
                  flush=True)
            if proto is not None and (it % C['checkpoint_every'] == 0 or it == iterations):
                meta = {'training_seed': train_seed, 'iteration': it, 'env_steps': steps, 'committed_strikes_seen': strikes_seen,
                        'code_commit': head, 'protocol_sha256': proto_sha, 'bc_parent_sha256': bc_meta['checkpoint_state_dict_sha256'],
                        'observation_schema_sha256': proto['observation_schema_sha256'],
                        'action_schema_sha256': proto['action_schema_sha256'], 'reward_v2_sha256': proto['reward_v2_sha256'],
                        'constraints_sha256': proto['constraints_sha256'], 'lambda_u': lam_u, 'lambda_p': lam_p,
                        'beta_kl': beta, 'entropy_coef': ent_coef, 'torch': str(torch.__version__), 'cuda': str(torch.version.cuda)}
                meta['checkpoint_sha256'] = save_checkpoint(out / ('ckpt_it%03d.pt' % it), policy, meta)
                save_checkpoint(out / ('critic_it%03d.pt' % it), critic)
                (out / ('ckpt_it%03d.json' % it)).write_text(json.dumps(meta, indent=1) + '\n', encoding='utf-8')
    log.close()
    return policy


# ----------------------------------------------------------------- development ---
def dev(variant, seed, iters):
    C = cfg(variant)
    out = OUT / 'dev' / ('%s_seed_%d' % (variant, seed))
    if out.exists():
        import shutil
        shutil.rmtree(out)
    policy = train_run(seed, C, out, iterations=iters)
    save_checkpoint(out / 'final.pt', policy.cpu(), {'variant': variant, 'iterations': iters})
    dev_eval(variant, seed)


def dev_eval(variant, seed):
    """TRAIN-VAL evaluation of a finished development run's final policy (informational; not a dev-rule input)."""
    out = OUT / 'dev' / ('%s_seed_%d' % (variant, seed))
    policy, _ = load_checkpoint(out / 'final.pt', TorchPolicy)
    h = state_dict_sha256(policy)
    recs = BCT.eval_policy_on_val(policy.to_numpy_model().params)
    base = json.loads((ROOT / 'artifacts/m2_2/val/baselines.json').read_text(encoding='utf-8'))
    ev = M22.evaluate_records(recs, base)['candidate']
    s = BCT.summarize(ev)
    n = ev['threat']['trials']
    s['hit_wilson95'] = wilson(round(s['hit_probability'] * n), n)
    (out / 'trainval.json').write_text(json.dumps({'final_sha256': h, 'summary': s}, indent=1, default=float) + '\n',
                                       encoding='utf-8')
    print('dev %s TRAIN-VAL hit %.3f %s win %.2f U %.2f P %.2f adm %s' % (variant, s['hit_probability'], s['hit_wilson95'],
                                                                        s['escape_in_window'], s['unnecessary_per_min'],
                                                                        s['perches_per_min'] or 0.0, s['admissible']))


def wilson(k, n, z=1.96):
    if n == 0:
        return None
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return [c - h, c + h]


def window_select():
    rows = [json.loads(line) for line in (OUT / 'dev' / 'B_strike_seed_201' / 'log.jsonl').open(encoding='utf-8')]
    agg = {w: {k: float(np.mean([r['window_stats'][w][k] for r in rows])) for k in ('adv_mass_share', 'tick_share', 'escape_share')}
           for w in WINDOWS}
    ok = [w for w in WINDOWS if agg[w]['adv_mass_share'] >= 0.9 and agg[w]['escape_share'] >= 0.9]
    sel = min(ok, key=lambda w: agg[w]['tick_share']) if ok else 'full'
    res = {'rule': WINDOW_RULE, 'source': 'dev/B_strike_seed_201 (TRAIN only), %d iterations' % len(rows), 'windows': agg,
           'selected': sel}
    (OUT / 'window_selection.json').write_text(json.dumps(res, indent=1) + '\n', encoding='utf-8')
    TRACK.mkdir(parents=True, exist_ok=True)
    (TRACK / 'window_selection.json').write_text(json.dumps(res, indent=1) + '\n', encoding='utf-8')
    print(json.dumps(res, indent=1))


def dev_summary():
    out = {'label': 'M2.4-A TRAIN-only development comparison (not official seeds; no EVAL touched)', 'rule': DEV_RULE, 'runs': {}}
    for d in sorted((OUT / 'dev').glob('*_seed_*')):
        rows = [json.loads(line) for line in (d / 'log.jsonl').open(encoding='utf-8')]
        if not rows:
            continue
        g = lambda k: [r['effective_samples']['gradient'][k] for r in rows]   # noqa: E731
        e = lambda k: [r['effective_samples'][k] for r in rows]               # noqa: E731
        tv = json.loads((d / 'trainval.json').read_text(encoding='utf-8'))['summary'] if (d / 'trainval.json').exists() else None
        out['runs'][d.name] = {
            'iterations': len(rows), 'strikes_per_iteration': float(np.mean(e('committed_strikes'))),
            'seconds_per_iteration': float(np.mean([r['seconds'] for r in rows])),
            'strikes_per_hour': float(np.mean(e('committed_strikes')) / np.mean([r['seconds'] for r in rows]) * 3600),
            'decisions_per_iteration': float(np.mean([r['decisions'] for r in rows])),
            'actor_ticks_per_iteration': float(np.mean(e('actor_loss_tick_samples'))),
            'effective_strikes_kish_weight': float(np.mean(e('effective_strikes_kish_weight'))),
            'effective_strikes_kish_grad': float(np.mean(g('effective_strikes_kish_grad'))),
            'cross_half_cosine_mean': float(np.mean(g('cross_half_cosine'))),
            'cross_half_cosine_after_warmup': float(np.mean(g('cross_half_cosine')[3:])),
            'minibatch_rel_variance_mean': float(np.mean(g('minibatch_rel_variance'))),
            'minibatch_rel_variance_after_warmup': float(np.mean(g('minibatch_rel_variance')[3:])),
            'cross_half_cosine_after_warmup_sd': float(np.std(g('cross_half_cosine')[3:], ddof=1)),
            'threat_trial_escape_min': min(r['threat_trial_any_escape'] for r in rows),
            'rollout_unnecessary_per_min_mean': float(np.mean([r['unnecessary_per_min'] for r in rows])),
            'rollout_perch_per_min_mean': float(np.mean([r['perch_per_min'] for r in rows])),
            'minibatch_pairwise_cosine_mean': float(np.mean(g('minibatch_pairwise_cosine'))),
            'unit_grad_share_top10pct_mean': float(np.mean(g('unit_grad_norm_share_top10pct'))),
            'advantage_lag1_autocorrelation_mean': float(np.mean(e('advantage_lag1_autocorrelation'))),
            'effective_independent_actor_samples_mean': float(np.mean(e('effective_independent_actor_samples'))),
            'none_share_max': max(r['none_share'] for r in rows), 'esc_L3_min': min(r['escape_response']['escape_prob_strong_left'] for r in rows),
            'esc_L3_end': rows[-1]['escape_response']['escape_prob_strong_left'], 'kl_bc_end': rows[-1]['kl_policy_bc_rollout'],
            'lambda_u_max': max(r['lambda_u'] for r in rows), 'nonfinite': sum(r['nonfinite_gradient_steps'] for r in rows),
            'rollout_hit_first5': float(np.mean([r['hit_rate'] for r in rows[:5]])),
            'rollout_hit_last5': float(np.mean([r['hit_rate'] for r in rows[-5:]])), 'trainval': tv}
    runs = out['runs']
    get = lambda v: next((x for k, x in runs.items() if k.startswith(v)), None)   # noqa: E731
    A, B, Cc = get('A_ref'), get('B_strike'), get('C_window')

    def checks(r):
        if r is None or A is None:
            return None
        tv = r['trainval'] or {}
        c = {'i_no_collapse': r['none_share_max'] < 0.995 and r['esc_L3_min'] >= 0.2,
             'ii_cosine_ge_A_ref': r['cross_half_cosine_after_warmup'] >= A['cross_half_cosine_after_warmup'],
             'ii_effective_strikes_ge_2x_A_ref': r['effective_strikes_kish_weight'] >= 2 * A['effective_strikes_kish_weight'],
             'iii_trainval_admissible': bool(tv.get('admissible')) and not tv.get('flags'),
             'iii_threat_window_escape_ge_0.3': (tv.get('escape_in_window') or 0) >= 0.3}
        c['eligible'] = all(c.values())
        return c
    cb, cc = checks(B), checks(Cc)
    adv = None
    if cb is not None and cc is not None:
        wb, wc = B['trainval']['hit_wilson95'], Cc['trainval']['hit_wilson95']
        adv = {'a_trainval_hit_non_overlapping_lower': wc[1] < wb[0],
               'b_cosine_plus_0.05': Cc['cross_half_cosine_after_warmup'] >= B['cross_half_cosine_after_warmup'] + 0.05,
               'b_relvar_le_0.75x': Cc['minibatch_rel_variance_after_warmup'] <= 0.75 * B['minibatch_rel_variance_after_warmup']}
        adv['clear_advantage'] = adv['a_trainval_hit_non_overlapping_lower'] or (adv['b_cosine_plus_0.05'] and adv['b_relvar_le_0.75x'])
    out['checks'] = {'B_strike': cb, 'C_window': cc, 'C_over_B': adv}
    if cb and cb['eligible']:
        out['method'] = 'C_window' if (cc and cc['eligible'] and adv and adv['clear_advantage']) else 'B_strike'
    elif cc and cc['eligible']:
        out['method'] = 'C_window'
    else:
        out['method'] = None
    TRACK.mkdir(parents=True, exist_ok=True)
    (TRACK / 'dev_summary.json').write_text(json.dumps(out, indent=1, default=float) + '\n', encoding='utf-8')
    for k, v in runs.items():
        print(k, {kk: (round(vv, 4) if isinstance(vv, float) else vv) for kk, vv in v.items() if kk != 'trainval'})
        t = v['trainval']
        if t:
            print('   TRAIN-VAL hit %.3f %s win %.2f U %.2f P %.2f admissible %s flags %s' % (
                t['hit_probability'], [round(x, 3) for x in t['hit_wilson95']], t['escape_in_window'],
                t['unnecessary_per_min'], t['perches_per_min'] or 0.0, t['admissible'], t['flags']))
    print(json.dumps(out['checks'], indent=1))
    print('method', out['method'])


# ----------------------------------------------------------------- protocol ---
def confirm_specs():
    """Fresh TRAIN-CONFIRM set for stage-2 selection (never used before): 32 per threat group, 16 per background
    family, numpy default_rng(2500 + group) from [25e6, 30e6) minus every earlier TRAIN-VAL / dev / R0 seed."""
    r0 = _load('m2_4_r0_temporal')
    m22, used = r0.dev_pool()
    used |= {s for *_, s in r0.dev_specs()} | {s for u in r0.credit_units() for *_, s in u}
    groups = [('threat', f, a, 32) for f in FAMS for a in LEVELS] + [('background', b, None, 16) for b in BGS]
    out = []
    for g, (kind, name, level, n) in enumerate(groups):
        rng = np.random.default_rng(2500 + g)
        lst = []
        while len(lst) < n:
            s = int(rng.integers(25_000_000, 30_000_000))
            if s not in used and s not in lst:
                lst.append(s)
        out += [(kind, name, level, s) for s in lst]
    return out


SELECTION = {
    'eligibility': 'on the evaluation set used: M2.1 admissible (unnecessary <= 5.36 / min, perches >= 0.275 / min, movement '
                   'constraints, no hard anti-cheat flag incl. constant_turning / pre_emptive_perpetual_escape / '
                   'repeated_maneuver_cycling) AND threat-window escape >= 0.3 AND synthetic strong-DNp01 escape probability '
                   '>= 0.2 and >= 10 x quiet AND NONE share of background decisions < 0.995 AND neural conditioning (escape '
                   'probability at max DNp01 >= 2 >= 10 x that at < 0.25 on TRAIN-VAL BC states)',
    'stage1_screen': 'every checkpoint on the M2.2 TRAIN-VAL set (96 threat, 24 background episodes = 12 min); screen-eligible '
                     'checkpoints ranked by hit, then unnecessary escapes',
    'stage2_confirm': 'the 6 best screen-eligible checkpoints re-evaluated on the fresh TRAIN-CONFIRM set (384 threat trials, '
                      '64 background episodes = 32 min background >= the 30 min minimum exposure); references N4B1C, PyTorch '
                      'BC and the M2.3 candidate on the same set',
    'final': 'lowest TRAIN-CONFIRM hit among confirm-eligible checkpoints; if the best two differ by < 0.02, the one with fewer '
             'unnecessary escapes; Wilson 95 % intervals and paired differences vs BC / N4B1C recorded; the screen estimate is '
             'never used for the final ranking (winner\'s-curse control)',
    'min_background_minutes_for_approval': 30,
}
SUCCESS = ('GO for human testing only if on M2-EVAL-v3: constraints pass (unnecessary <= 5.36 / min, perches >= 0.275 / min, '
           'movement constraints), no anti-cheat flag, genuine conditional escape (threat-window escape >= 0.3, neural '
           'conditioning), AND candidate hit < N4B1C hit on the same 480 v3 threat trials with exact two-sided McNemar '
           'p < 0.05 (i.e. the paired 95 % CI of the difference lies below 0)')


def freeze():
    if PROTOCOL_FILE.exists():
        raise SystemExit('already frozen')
    ds = json.loads((TRACK / 'dev_summary.json').read_text(encoding='utf-8'))
    if ds['method'] is None:
        raise SystemExit('development: strike-centric training invalid; stop')
    audit = TRACK / 'worker_allocation_audit.json'
    if not audit.exists() or not json.loads(audit.read_text(encoding='utf-8'))['identical']:
        raise SystemExit('worker-allocation audit missing or not identical; fix scheduling before freeze')
    gate = json.loads(MT.BC_GATE_FILE.read_text(encoding='utf-8'))
    p22 = json.loads((ROOT / 'game/learning/m2_2_protocol.json').read_text(encoding='utf-8'))
    C = cfg(ds['method'])
    per_iter = C['sampling']['workers'] * C['sampling']['threat_per_worker'] if C['sampling']['mode'] != 'm23' else \
        C['sampling']['units'] * C['sampling']['threat_per_unit']
    proto = {'label': 'M2.4-A frozen protocol: threat-dense strike-centric PPO (sampling / loss weighting only)',
             'frozen_utc': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()), 'environment': MT.env_info(),
             'method': ds['method'], 'ppo': C, 'training_seeds': [1, 2, 3, 4, 5],
             'budget': {'committed_threat_trials_per_seed': per_iter * C['iterations'], 'threat_trials_per_iteration': per_iter,
                        'background_episodes_per_iteration': C['sampling'].get('workers', 7) * C['sampling'].get(
                            'background_per_worker', 1), 'environment_decisions': 'logged exactly (about 48k per iteration)'},
             'window_selection': json.loads((TRACK / 'window_selection.json').read_text(encoding='utf-8')),
             'development_summary_sha256': MT.sha_file(TRACK / 'dev_summary.json'),
             'worker_allocation_audit_sha256': MT.sha_file(audit),
             'worker_allocation_audit_commit': 'c67f5d2',
             'window_selection_commit': 'adb9ca9 (engage locked from B_strike TRAIN rollouts before any C_window result; '
                                        'used only by C_window; the selected method uses its own actor_window)',
             'development_rule': DEV_RULE, 'development_rule_commit': 'adb9ca9',
             'bc_checkpoint_state_dict_sha256': gate['bc_checkpoint_state_dict_sha256'],
             'split': p22['split'], 'split_sha256': p22['split_sha256'],
             'train_confirm_sha256': hashlib.sha256(json.dumps(confirm_specs()).encode()).hexdigest(),
             'reward_v2_sha256': p22['reward_v2_sha256'], 'constraints_sha256': p22['constraints_sha256'],
             'observation_schema_sha256': p22['observation_schema_sha256'], 'action_schema_sha256': p22['action_schema_sha256'],
             'm2_eval_v3_manifest_sha256': MT.sha_file(ROOT / 'game/learning/m2_eval_v3.json'),
             'selection': SELECTION, 'success_criterion': SUCCESS,
             'anti_leakage': 'event times, strike phase, world geometry and attacker state are used only by the training collector '
                             '(sample inclusion, reward, grouping); never in the observation, network input or checkpoint'}
    PROTOCOL_FILE.write_text(json.dumps(proto, indent=1) + '\n', encoding='utf-8')
    print('frozen', MT.sha_file(PROTOCOL_FILE), ds['method'])


def train(seed):
    proto, proto_sha = ppo_protocol()
    if seed not in proto['training_seeds']:
        raise SystemExit('not a preregistered training seed')
    out = OUT / 'runs' / ('seed_%d' % seed)
    if (out / 'log.jsonl').exists():
        raise SystemExit('official runs are never restarted silently')
    train_run(seed, proto['ppo'], out, proto=proto, proto_sha=proto_sha)


# ----------------------------------------------------------------- validation / selection ---
def evaluate_policy_records(recs, base, net, va):
    ev = M22.evaluate_records(recs, base)['candidate']
    model = net.to_numpy_model()
    resp = BCT.escape_response(model)
    cats = ev['background']['category_counts']
    none_share = cats.get('NONE', 0) / max(1, sum(cats.values()))
    nc = MT.neural_conditioning(net, va)
    collapse_ok = resp['escape_prob_strong_left'] >= 0.2 and resp['escape_prob_strong_left'] >= 10 * resp['escape_prob_quiet'] \
        and none_share < 0.995
    s = BCT.summarize(ev)
    n = ev['threat']['trials']
    s['hit_wilson95'] = wilson(ev['threat']['hits'], n)
    s['background_minutes'] = ev['background'].get('minutes')
    eligible = bool(ev['admissible'] and (ev['threat']['escape_in_window_fraction'] or 0) >= 0.3 and collapse_ok and nc['ok'])
    return {'summary': s, 'escape_response': resp, 'none_share_background': none_share, 'collapse_ok': collapse_ok,
            'neural_conditioning': nc, 'eligible': eligible,
            'hits_by_seed': {'%s:%s' % (r['group'], r['seed']): bool(r['hit']) for r in recs if r['kind'] == 'threat'}}


def _eval_params(pool, params, specs, mode='TRAIN'):
    chunks = [specs[i::WORKERS] for i in range(WORKERS)]
    return [r for ch in pool.map(training.eval_task, [(params, c, mode) for c in chunks]) for r in ch]


def screen():
    ppo_protocol()
    base = json.loads((ROOT / 'artifacts/m2_2/val/baselines.json').read_text(encoding='utf-8'))
    path = OUT / 'val' / 'screen.json'
    path.parent.mkdir(parents=True, exist_ok=True)
    res = json.loads(path.read_text(encoding='utf-8')) if path.exists() else {}
    bc_net, _ = MT.load_bc()
    _, va, _ = MT.load_dataset()
    specs = M22.val_specs()
    with mp.get_context('spawn').Pool(WORKERS, initializer=training.worker_init) as pool:
        for c in sorted((OUT / 'runs').glob('seed_*/ckpt_it*.pt')):
            key = '%s/%s' % (c.parent.name, c.stem)
            if key in res:
                continue
            meta = json.loads(c.with_suffix('.json').read_text(encoding='utf-8'))
            net, _ = load_checkpoint(c, TorchPolicy, expected_sha256=meta['checkpoint_sha256'])
            recs = _eval_params(pool, net.to_numpy_model().params, specs)
            r = evaluate_policy_records(recs, base, net, va)
            r['meta'] = meta
            r['kl_to_bc_val_states'] = MT.kl_to_bc(net, bc_net, va['obs'])
            res[key] = r
            path.write_text(json.dumps(res, indent=1, default=float) + '\n', encoding='utf-8')
            s = r['summary']
            print('screen %s hit %.3f %s win %.2f U %.2f P %.2f adm %s eligible %s KL %.4f' % (
                key, s['hit_probability'], [round(x, 3) for x in s['hit_wilson95']], s['escape_in_window'],
                s['unnecessary_per_min'], s['perches_per_min'] or 0.0, s['admissible'], r['eligible'],
                r['kl_to_bc_val_states']), flush=True)


def _reference_records(pool_mlp, specs, mode='TRAIN'):
    """N4B1C (accepted baseline) + PyTorch BC + M2.3 candidate records on `specs`."""
    m23 = json.loads((ROOT / 'game/learning/m2_3/torch_candidate.json').read_text(encoding='utf-8'))
    bc_net, _ = MT.load_bc()
    cand23, _ = load_checkpoint(ROOT / 'game/learning/m2_3/torch_candidate.pt', TorchPolicy, expected_sha256=m23['checkpoint_sha256'])
    refs = {'torch_bc': _eval_params(pool_mlp, bc_net.to_numpy_model().params, specs, mode),
            'm2_3_candidate': _eval_params(pool_mlp, cand23.to_numpy_model().params, specs, mode)}
    return refs, {'torch_bc': bc_net, 'm2_3_candidate': cand23}


def confirm():
    ppo_protocol()
    scr = json.loads((OUT / 'val' / 'screen.json').read_text(encoding='utf-8'))
    el = sorted([k for k, v in scr.items() if v['eligible']],
                key=lambda k: (scr[k]['summary']['hit_probability'], scr[k]['summary']['unnecessary_per_min']))
    top = el[:6]
    specs = confirm_specs()
    chunks = [specs[i::WORKERS] for i in range(WORKERS)]
    path = OUT / 'val' / 'confirm.json'
    res = json.loads(path.read_text(encoding='utf-8')) if path.exists() else {}
    _, va, _ = MT.load_dataset()
    if 'baseline_n4b1c' not in res.get('_records', {}):
        with mp.get_context('spawn').Pool(WORKERS, initializer=baseline_eval.worker_init) as pool:
            recs = {n: [r for ch in pool.map(baseline_eval.baseline_task, [(n, c, 'TRAIN') for c in chunks]) for r in ch]
                    for n in ('baseline_n4b1c', 'no_escape', 'fixed_maneuver')}
        res['_records'] = recs
        path.write_text(json.dumps(res, default=float) + '\n', encoding='utf-8')
    base = {'baseline_n4b1c': res['_records']['baseline_n4b1c']}
    with mp.get_context('spawn').Pool(WORKERS, initializer=training.worker_init) as pool:
        if 'torch_bc' not in res:
            refs, nets = _reference_records(pool, specs)
            for n, r in refs.items():
                res[n] = evaluate_policy_records(r, base, nets[n], va)
            path.write_text(json.dumps(res, default=float) + '\n', encoding='utf-8')
        for key in top:
            if key in res:
                continue
            seed, ck = key.split('/')
            c = OUT / 'runs' / seed / (ck + '.pt')
            meta = json.loads(c.with_suffix('.json').read_text(encoding='utf-8'))
            net, _ = load_checkpoint(c, TorchPolicy, expected_sha256=meta['checkpoint_sha256'])
            r = evaluate_policy_records(_eval_params(pool, net.to_numpy_model().params, specs), base, net, va)
            r['meta'] = meta
            res[key] = r
            path.write_text(json.dumps(res, default=float) + '\n', encoding='utf-8')
            s = r['summary']
            print('confirm %s hit %.3f %s U %.2f P %.2f bg_min %s eligible %s' % (
                key, s['hit_probability'], [round(x, 3) for x in s['hit_wilson95']], s['unnecessary_per_min'],
                s['perches_per_min'] or 0.0, s['background_minutes'], r['eligible']), flush=True)
    for n in ('baseline_n4b1c', 'no_escape', 'fixed_maneuver'):
        ev = M22.evaluate_records(res['_records'][n], base)['candidate']
        res['summary_' + n] = dict(BCT.summarize(ev), hit_wilson95=wilson(ev['threat']['hits'], ev['threat']['trials']),
                                   hits_by_seed={'%s:%s' % (r['group'], r['seed']): bool(r['hit'])
                                                 for r in res['_records'][n] if r['kind'] == 'threat'})
    res['_top6'] = top
    path.write_text(json.dumps(res, default=float) + '\n', encoding='utf-8')


def paired(a, b):
    from scipy.stats import binomtest
    k = sorted(set(a) & set(b))
    d = [a[x] - b[x] for x in k]
    n = len(d)
    m = sum(d) / n
    se = math.sqrt(sum((v - m) ** 2 for v in d) / (n - 1) / n)
    c1 = sum(a[x] and not b[x] for x in k)
    c2 = sum(b[x] and not a[x] for x in k)
    return {'n': n, 'difference': m, 'ci95': [m - 1.96 * se, m + 1.96 * se], 'only_first_hit': c1, 'only_second_hit': c2,
            'mcnemar_p': binomtest(c1, c1 + c2, 0.5).pvalue if c1 + c2 else 1.0}


def select():
    proto, proto_sha = ppo_protocol()
    if CANDIDATE_FILE.exists():
        raise SystemExit('candidate already frozen')
    res = json.loads((OUT / 'val' / 'confirm.json').read_text(encoding='utf-8'))
    top = res['_top6']
    el = [k for k in top if res[k]['eligible'] and (res[k]['summary']['background_minutes'] or 0) >= 30]
    rec = {'label': 'M2.4-A frozen candidate', 'selected_utc': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
           'selection': SELECTION, 'protocol_sha256': proto_sha, 'screen_top6': top, 'confirm_eligible': el}
    if not el:
        rec['candidate'] = None
        CANDIDATE_FILE.write_text(json.dumps(rec, indent=1) + '\n', encoding='utf-8')
        print('NO ELIGIBLE CHECKPOINT')
        return
    el.sort(key=lambda k: res[k]['summary']['hit_probability'])
    best = el[0]
    if len(el) > 1 and res[el[1]]['summary']['hit_probability'] - res[best]['summary']['hit_probability'] < 0.02 \
            and res[el[1]]['summary']['unnecessary_per_min'] < res[best]['summary']['unnecessary_per_min']:
        best = el[1]
    seed, ck = best.split('/')
    src = OUT / 'runs' / seed / (ck + '.pt')
    net, meta = load_checkpoint(src, TorchPolicy, expected_sha256=res[best]['meta']['checkpoint_sha256'])
    h = save_checkpoint(CANDIDATE_CKPT, net, meta)
    npz = net.to_numpy_model().save(CANDIDATE_NPZ)
    rec.update({'candidate': best, 'checkpoint_sha256': h, 'checkpoint_file_sha256': MT.sha_file(CANDIDATE_CKPT),
                'numpy_export': str(CANDIDATE_NPZ.relative_to(ROOT)).replace('\\', '/'), 'numpy_export_param_sha256': npz,
                'bc_parent_sha256': proto['bc_checkpoint_state_dict_sha256'], 'training_seed': meta['training_seed'],
                'iteration': meta['iteration'], 'env_steps': meta['env_steps'],
                'committed_strikes_seen': meta['committed_strikes_seen'], 'torch': meta['torch'], 'cuda': meta['cuda'],
                'observation_schema_sha256': proto['observation_schema_sha256'],
                'action_schema_sha256': proto['action_schema_sha256'], 'reward_v2_sha256': proto['reward_v2_sha256'],
                'constraints_sha256': proto['constraints_sha256'],
                'confirm_summary': res[best]['summary'],
                'confirm_paired_vs_n4b1c': paired(res[best]['hits_by_seed'], res['summary_baseline_n4b1c']['hits_by_seed']),
                'confirm_paired_vs_bc': paired(res[best]['hits_by_seed'], res['torch_bc']['hits_by_seed']),
                'confirm_paired_vs_m2_3': paired(res[best]['hits_by_seed'], res['m2_3_candidate']['hits_by_seed'])})
    CANDIDATE_FILE.write_text(json.dumps(rec, indent=1, default=float) + '\n', encoding='utf-8')
    print(json.dumps({k: rec[k] for k in ('candidate', 'checkpoint_sha256', 'confirm_summary', 'confirm_paired_vs_n4b1c',
                                          'confirm_paired_vs_bc', 'confirm_paired_vs_m2_3')}, indent=1, default=float))


def eval_final():
    ppo_protocol()
    cand = json.loads(CANDIDATE_FILE.read_text(encoding='utf-8'))
    if cand['candidate'] is None:
        raise SystemExit('no candidate')
    v3 = _load('m2_eval_v3')
    net, _ = load_checkpoint(CANDIDATE_CKPT, TorchPolicy, expected_sha256=cand['checkpoint_sha256'])
    bc_net, _ = MT.load_bc()
    m23 = json.loads((ROOT / 'game/learning/m2_3/torch_candidate.json').read_text(encoding='utf-8'))
    c23, _ = load_checkpoint(ROOT / 'game/learning/m2_3/torch_candidate.pt', TorchPolicy, expected_sha256=m23['checkpoint_sha256'])
    recs = v3.run_once(net.to_numpy_model().params, extra_mlp={'torch_bc': bc_net.to_numpy_model().params,
                                                               'm2_3_candidate': c23.to_numpy_model().params})
    base = {'baseline_n4b1c': recs['baseline_n4b1c']}
    _, va, _ = MT.load_dataset()
    rep = {'candidate': cand['candidate'], 'checkpoint_sha256': cand['checkpoint_sha256'], 'code_commit': M22.git_head(),
           'protocol_sha256': cand['protocol_sha256'], 'v3_manifest_sha256': MT.sha_file(ROOT / 'game/learning/m2_eval_v3.json'),
           'environment': MT.env_info(), 'policies': {}}
    hits = {}
    for name, r in recs.items():
        ev = M22.evaluate_records(r, base)['candidate']
        s = BCT.summarize(ev)
        s['hit_wilson95'] = wilson(ev['threat']['hits'], ev['threat']['trials'])
        s['hit_by_family'] = {f: x['hit_probability'] for f, x in ev['threat_by_family'].items()}
        s['constraint_values'] = {k: c['value'] for k, c in ev['constraints'].items()}
        rep['policies'][name] = s
        hits[name] = {'%s:%s' % (x['group'], x['seed']): bool(x['hit']) for x in r if x['kind'] == 'threat'}
    nc = MT.neural_conditioning(net, va)
    cs = rep['policies']['candidate']
    rep['candidate_neural_conditioning'] = nc
    rep['paired'] = {n: paired(hits['candidate'], hits[n]) for n in hits if n != 'candidate'}
    pv = rep['paired']['baseline_n4b1c']
    crit = {'A_constraints': not cs['violations'], 'B_no_anti_cheat': not cs['flags'],
            'C_conditional_escape': (cs['escape_in_window'] or 0) >= 0.3 and nc['ok'],
            'D_hit_lower_than_n4b1c': pv['difference'] < 0,
            'E_paired_significant': pv['difference'] < 0 and pv['mcnemar_p'] < 0.05 and pv['ci95'][1] < 0,
            'F_unnecessary_within_budget': cs['unnecessary_per_min'] <= 5.36}
    rep['success_criterion'] = SUCCESS
    rep['criteria'] = crit
    rep['GO'] = all(crit.values())
    (TRACK / 'eval_v3_report.json').write_text(json.dumps(rep, indent=1, default=float) + '\n', encoding='utf-8')
    for n, s in rep['policies'].items():
        print('%-16s hit %.3f %s %s win %s U %.2f P %.2f adm %s flags %s' % (
            n, s['hit_probability'], [round(x, 3) for x in s['hit_wilson95']], {a: round(v, 3) for a, v in s['hit_by_attacker'].items()},
            None if s['escape_in_window'] is None else round(s['escape_in_window'], 2), s['unnecessary_per_min'],
            s['perches_per_min'] or 0.0, s['admissible'], s['flags']))
    print(json.dumps(rep['paired'], indent=1, default=float))
    print('criteria', crit, 'GO', rep['GO'])


def compare():
    """TRAIN-VAL (screen set) + TRAIN-CONFIRM tables for all required references."""
    base = json.loads((ROOT / 'artifacts/m2_2/val/baselines.json').read_text(encoding='utf-8'))
    rows = {'train_val': {}, 'train_confirm': {}}
    for n in ('baseline_n4b1c', 'no_escape', 'fixed_maneuver'):
        rows['train_val'][n] = BCT.summarize(M22.evaluate_records(base[n], base)['candidate'])
    rows['train_val']['teacher_mapped'] = BCT.summarize(M22.evaluate_records(
        json.loads((ROOT / 'artifacts/m2_3/val/teacher_mapped.json').read_text(encoding='utf-8')), base)['candidate'])
    rows['train_val']['torch_bc'] = BCT.summarize(M22.evaluate_records(
        json.loads((ROOT / 'artifacts/m2_3/torch/val/bc_policy.json').read_text(encoding='utf-8')), base)['candidate'])
    v23 = json.loads((ROOT / 'artifacts/m2_3/torch/val/checkpoints.json').read_text(encoding='utf-8'))['seed_4/ckpt_it060']
    rows['train_val']['m2_3_candidate'] = v23['summary']
    scr = json.loads((OUT / 'val' / 'screen.json').read_text(encoding='utf-8'))
    for k, v in scr.items():
        rows['train_val']['m2_4_a/' + k] = dict(v['summary'], eligible=v['eligible'])
    con = json.loads((OUT / 'val' / 'confirm.json').read_text(encoding='utf-8'))
    for k, v in con.items():
        if k.startswith('summary_'):
            rows['train_confirm'][k[8:]] = {kk: vv for kk, vv in v.items() if kk != 'hits_by_seed'}
        elif not k.startswith('_'):
            rows['train_confirm'][k] = dict(v['summary'], eligible=v['eligible'])
    (TRACK / 'comparison.json').write_text(json.dumps(rows, indent=1, default=float) + '\n', encoding='utf-8')
    for part, d in rows.items():
        print('==', part)
        for k, v in d.items():
            print('%-28s hit %.3f win %s U %.2f P %s adm %s %s' % (
                k, v['hit_probability'], None if v.get('escape_in_window') is None else round(v['escape_in_window'], 2),
                v['unnecessary_per_min'], None if v.get('perches_per_min') is None else round(v['perches_per_min'], 2),
                v['admissible'], '' if 'eligible' not in v else 'eligible=%s' % v['eligible']))


if __name__ == '__main__':
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('mode')
    ap.add_argument('--seed', type=int)
    ap.add_argument('--variant', default='B_strike')
    ap.add_argument('--iters', type=int, default=20)
    a = ap.parse_args()
    {'dev': lambda: dev(a.variant, a.seed, a.iters), 'dev-eval': lambda: dev_eval(a.variant, a.seed), 'window-select': window_select, 'dev-summary': dev_summary,
     'freeze': freeze, 'train': lambda: train(a.seed), 'screen': screen, 'confirm': confirm, 'select': select,
     'compare': compare, 'eval-final': eval_final}[a.mode]()
