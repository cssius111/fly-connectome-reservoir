"""M2.3 NumPy PPO draft (DEVELOPMENT EVIDENCE ONLY; superseded by tools/m2_3_torch.py).

This handwritten-gradient learner produced the TRAIN-only seed-101 development smoke
(artifacts/m2_3/smoke_seed_101). It is NOT the official M2.3 learner: official M2.3 BC and PPO use
PyTorch autograd (game/learning/torch_policy.py). Its freeze / train / select / eval modes must not be used.

Original description: constrained PPO fine-tuning from the frozen BC policy (training method only).

Runs only after the BC gate passed (tools/m2_3_bc_ppo.py bc-gate).

    python tools/m2_3_ppo.py ppo-smoke --seed K      (TRAIN-only development, before the freeze)
    python tools/m2_3_ppo.py freeze
    python tools/m2_3_ppo.py train --seed K          (K = 1..5)
    python tools/m2_3_ppo.py validate
    python tools/m2_3_ppo.py select
    python tools/m2_3_ppo.py eval-final
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

from game.learning import trials, training  # noqa: E402
from game.learning.contracts import N_MANEUVERS  # noqa: E402
from game.learning.model import MLPPolicyModel  # noqa: E402
from game.learning.ppo import (Adam, ValueModel, clip_grads, gae, kl_anchor_loss_and_grads,  # noqa: E402
                               policy_forward, ppo_policy_loss_and_grads, value_loss_and_grads)
from game.learning.reward_v2 import RewardV2  # noqa: E402

_spec = importlib.util.spec_from_file_location('m2_3_bc_ppo', ROOT / 'tools/m2_3_bc_ppo.py')
BC = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(BC)
M22, OUT, TRACK, WORKERS, NONE = BC.M22, BC.OUT, BC.TRACK, BC.WORKERS, BC.NONE
escape_response, summarize = BC.escape_response, BC.summarize

PROTOCOL_FILE = TRACK / 'ppo_protocol.json'
CANDIDATE_FILE = TRACK / 'candidate.json'
CANDIDATE_CKPT = TRACK / 'candidate.npz'
PPO = {
    'init': 'every training seed starts from the frozen BC checkpoint (identical parameters); only optimizer / '
            'rollout seeds differ',
    'critic_init': 'ValueModel 60 -> 32 tanh -> 1, random (seed = training seed + 1), same fixed input scaling; '
                   'the first 3 iterations update the critic only (policy frozen)',
    'critic_warmup_iterations': 3,
    'optimizer': 'Adam (0.9, 0.999, 1e-8)', 'learning_rate': 1e-4, 'gamma': 0.99, 'gae_lambda': 0.95,
    'ppo_clip': 0.2, 'value_coef': 0.5, 'update_epochs': 4, 'minibatch_size': 4096, 'grad_clip_norm': 0.5,
    'advantage_normalization': 'per batch', 'reward_normalization': 'none',
    'kl_anchor': {'reference': 'frozen BC policy', 'beta_start': 1.0, 'hold_until_iteration': 15,
                  'beta_end': 0.1, 'decay_until_iteration': 45,
                  'schedule': 'beta = 1.0 for iterations <= 15, linear to 0.1 at iteration 45, 0.1 afterwards'},
    'entropy': {'mode': 'adaptive coefficient (option A)',
                'target': '0.8 x the mean policy entropy on the iteration-1 rollouts (the BC policy)',
                'coef_init': 0.001, 'coef_min': 1e-4, 'coef_max': 0.05,
                'update': 'coef <- clip(coef * exp(0.5 * (target - H) / target), min, max) after each iteration'},
    'dual': {'warmup_iterations': 15, 'warmup': 'lambda_u = lambda_p = 0 and not updated during warmup',
             'unnecessary_target_per_min': 0.9 * 5.36, 'perch_target_per_min': 1.5 * 0.275, 'step': 0.02,
             'ema_alpha': 0.3, 'lambda_u_max': 10.0, 'lambda_p_max': 5.0,
             'update': 'after warmup: lambda <- clip(lambda + 0.02 x normalized violation, 0, max) on the EMA'},
    'mixture': 'per rollout unit: 1 background episode + 6 threat trials (training only; the benchmark is unchanged)',
    'rollout_units_per_iteration': WORKERS, 'iterations': 60, 'checkpoint_every': 10,
    'training_seeds': [1, 2, 3, 4, 5],
    'early_stopping': 'none; every checkpoint is validated on TRAIN-VAL',
    'eligibility': 'M2.1 admissible on TRAIN-VAL (unnecessary <= 5.36 / min, perches >= 0.275 / min, movement '
                   'constraints, no anti-cheat flag) AND threat-window escape fraction >= 0.3 AND the no_escape-collapse '
                   'diagnostic passes: escape probability at a strong one-sided DNp01 frame >= 0.2 and >= 10 x the quiet '
                   'frame, and NONE share of TRAIN-VAL background decisions < 0.995',
    'selection': 'among eligible checkpoints: lowest TRAIN-VAL hit probability; then lower unnecessary escapes / min; '
                 'then smaller mean KL(policy || BC) on the TRAIN-VAL BC dataset states',
}


def ppo_protocol():
    if not PROTOCOL_FILE.exists():
        raise SystemExit('freeze the PPO protocol first')
    p = json.loads(PROTOCOL_FILE.read_text(encoding='utf-8'))
    if p['ppo'] != json.loads(json.dumps(PPO)):
        raise SystemExit('code differs from the frozen PPO protocol')
    return p, hashlib.sha256(PROTOCOL_FILE.read_bytes()).hexdigest()


def unit_specs(rng, dev):
    fams = [f.name for f in trials.THREAT_FAMILIES]
    levels = list(trials.ATTACKERS)
    bgs = [c.name for c in trials.BACKGROUND_FAMILIES]

    def seed():
        while True:
            s = int(rng.integers(20_000_000, 25_000_000))
            if s not in dev:
                return s
    specs = [('background', bgs[int(rng.integers(len(bgs)))], None, seed())]
    for _ in range(6):
        specs.append(('threat', fams[int(rng.integers(len(fams)))], levels[int(rng.integers(len(levels)))], seed()))
    return specs


def beta_at(it, K):
    if it <= K['hold_until_iteration']:
        return K['beta_start']
    if it >= K['decay_until_iteration']:
        return K['beta_end']
    f = (it - K['hold_until_iteration']) / (K['decay_until_iteration'] - K['hold_until_iteration'])
    return K['beta_start'] + f * (K['beta_end'] - K['beta_start'])


def load_bc():
    meta = json.loads((TRACK / 'bc_metrics.json').read_text(encoding='utf-8'))
    return MLPPolicyModel.load(TRACK / 'bc_checkpoint.npz', expected_sha256=meta['checkpoint_sha256']), meta


def ppo_train(train_seed, iterations=None, out=None, frozen=True):
    if frozen:
        proto, proto_sha = ppo_protocol()
        H = proto['ppo']
    else:
        H, proto_sha, proto = json.loads(json.dumps(PPO)), None, None
    iterations = iterations or H['iterations']
    out = out or OUT / 'runs' / ('seed_%d' % train_seed)
    out.mkdir(parents=True, exist_ok=True)
    bc_model, bc_meta = load_bc()
    model, _ = load_bc()
    critic = ValueModel(seed=train_seed + 1, input_scale=model.input_scale)
    opt_p, opt_v = Adam(model.params, H['learning_rate']), Adam(critic.params, H['learning_rate'])
    reward = RewardV2(**json.loads((ROOT / 'game/learning/benchmark_v2_frozen.json').read_text(encoding='utf-8'))['reward_v2'])
    D, K, E = H['dual'], H['kl_anchor'], H['entropy']
    lam_u = lam_p = 0.0
    ema_u = ema_p = None
    ent_coef, ent_target = E['coef_init'], None
    rng = np.random.default_rng([train_seed, 2305])
    dev = BC.dev_seeds()
    head = M22.git_head()
    log = (out / 'log.jsonl').open('a', encoding='utf-8')
    steps = 0
    with mp.get_context('spawn').Pool(WORKERS, initializer=training.worker_init) as pool:
        for it in range(1, iterations + 1):
            t0 = time.time()
            specs = [unit_specs(rng, dev) for _ in range(WORKERS)]
            params = {k: v.copy() for k, v in model.params.items()}
            eps = [e for chunk in pool.map(training.rollout_task, [(params, sp) for sp in specs]) for e in chunk]
            thr = [e for e in eps if e['kind'] == 'threat']
            bg = [e for e in eps if e['kind'] == 'background']
            bg_min = sum(e['seconds'] for e in bg) / 60
            U = sum(int(e['unnec'].sum()) for e in bg) / bg_min
            P = sum(int(e['perch'].sum()) for e in bg) / bg_min
            ema_u = U if ema_u is None else (1 - D['ema_alpha']) * ema_u + D['ema_alpha'] * U
            ema_p = P if ema_p is None else (1 - D['ema_alpha']) * ema_p + D['ema_alpha'] * P
            X, A, ADV, RET, V_all = [], [], [], [], []
            for e in eps:
                x = e['obs'].astype(np.float64)
                r = e['task'] - (reward.unnecessary + lam_u) * e['unnec'] + lam_p * e['perch']
                v, _ = critic.forward(x)
                dones = np.zeros(len(r))
                if e['terminal']:
                    dones[-1] = 1.0
                    last = 0.0
                else:
                    last = float(v[-1])
                adv, ret = gae(r, v, dones, last, H['gamma'], H['gae_lambda'])
                X.append(x)
                A.append(e['act'].astype(int))
                ADV.append(adv)
                RET.append(ret)
                V_all.append(v)
            X, A, ADV, RET, V_all = map(np.concatenate, (X, A, ADV, RET, V_all))
            P_old, _ = policy_forward(model, X)
            logp_old = np.log(P_old[np.arange(len(A)), A] + 1e-12)
            H_now = float(-(P_old * np.log(P_old + 1e-12)).sum(1).mean())
            if ent_target is None:
                ent_target = 0.8 * H_now
            logQ = np.log(policy_forward(bc_model, X)[0] + 1e-12)
            ADVn = (ADV - ADV.mean()) / (ADV.std() + 1e-8)
            beta = beta_at(it, K)
            update_policy = it > H['critic_warmup_iterations']
            stats = []
            idx = np.arange(len(A))
            for _ in range(H['update_epochs']):
                rng.shuffle(idx)
                for s0 in range(0, len(idx), H['minibatch_size']):
                    b = idx[s0:s0 + H['minibatch_size']]
                    st = {}
                    if update_policy:
                        _, gp, st = ppo_policy_loss_and_grads(model, X[b], A[b], logp_old[b], ADVn[b], H['ppo_clip'], ent_coef)
                        _, gk, klv = kl_anchor_loss_and_grads(model, X[b], logQ[b], beta)
                        g = {k: gp[k] + gk[k] for k in gp}
                        g, gnp = clip_grads(g, H['grad_clip_norm'])
                        model.apply_update(opt_p.step(model.params, g))
                        st.update({'kl_bc': klv, 'grad_norm_policy': gnp})
                    lv, gv = value_loss_and_grads(critic, X[b], RET[b], H['value_coef'])
                    gv, gnv = clip_grads(gv, H['grad_clip_norm'])
                    for k, d in opt_v.step(critic.params, gv).items():
                        critic.params[k] = critic.params[k] + d
                    st.update({'value_loss': lv, 'grad_norm_value': gnv})
                    stats.append(st)
            if it > D['warmup_iterations']:
                tu, tp = D['unnecessary_target_per_min'], D['perch_target_per_min']
                lam_u = float(np.clip(lam_u + D['step'] * (ema_u - tu) / tu, 0, D['lambda_u_max']))
                lam_p = float(np.clip(lam_p + D['step'] * (tp - ema_p) / tp, 0, D['lambda_p_max']))
            ent_coef = float(np.clip(ent_coef * np.exp(0.5 * (ent_target - H_now) / ent_target), E['coef_min'], E['coef_max']))
            steps += len(A)
            counts = np.bincount(A, minlength=N_MANEUVERS)
            ev = 1 - np.var(RET - V_all) / (np.var(RET) + 1e-12)

            def mean(k):
                v = [s[k] for s in stats if k in s]
                return float(np.mean(v)) if v else None
            P_new, _ = policy_forward(model, X)
            row = {'iteration': it, 'env_steps': steps, 'seconds': time.time() - t0, 'threat_trials': len(thr),
                   'hit_rate': float(np.mean([e['hit'] for e in thr])),
                   'threat_trial_any_escape': float(np.mean([bool(e['escape'].any()) for e in thr])),
                   'background_minutes': bg_min, 'unnecessary_per_min': U, 'perch_per_min': P, 'ema_unnecessary': ema_u,
                   'ema_perch': ema_p, 'lambda_u': lam_u, 'lambda_p': lam_p, 'beta_kl': beta,
                   'kl_policy_bc_rollout': float((P_new * (np.log(P_new + 1e-12) - logQ)).sum(1).mean()),
                   'entropy': H_now, 'entropy_target': ent_target, 'entropy_coef': ent_coef,
                   'action_distribution': (counts / counts.sum()).round(5).tolist(),
                   'none_share': float(counts[NONE] / counts.sum()),
                   'escape_fraction': float(np.mean(np.concatenate([e['escape'] for e in eps]))),
                   'turn_fraction': float(np.mean(np.concatenate([e['turn'] for e in eps]))),
                   'wall_fraction': float(np.mean(np.concatenate([e['wall'] for e in eps]))),
                   'max_speed_fraction': float(np.mean(np.concatenate([e['maxspd'] for e in eps]))),
                   'policy_loss': mean('policy_loss'), 'approx_kl': mean('approx_kl'), 'clipfrac': mean('clipfrac'),
                   'value_loss': mean('value_loss'), 'explained_variance': float(ev),
                   'grad_norm_policy': mean('grad_norm_policy'), 'grad_norm_value': mean('grad_norm_value'),
                   'escape_response': escape_response(model)}
            log.write(json.dumps(row) + '\n')
            log.flush()
            print('seed %d it %2d hit %.2f anyesc %.2f U %.1f P %.2f lam_u %.2f beta %.2f KLbc %.4f H %.3f/%.3f c %.4f '
                  'NONE %.4f esc@L3 %.2f (%.0f s)' % (
                      train_seed, it, row['hit_rate'], row['threat_trial_any_escape'], U, P, lam_u, beta,
                      row['kl_policy_bc_rollout'], H_now, ent_target, ent_coef, row['none_share'],
                      row['escape_response']['escape_prob_strong_left'], row['seconds']), flush=True)
            if frozen and (it % H['checkpoint_every'] == 0 or it == iterations):
                path = out / ('ckpt_it%03d.npz' % it)
                h = model.save(path)
                np.savez(out / ('critic_it%03d.npz' % it), **critic.params)
                meta = {'training_seed': train_seed, 'iteration': it, 'env_steps': steps, 'code_commit': head,
                        'protocol_sha256': proto_sha, 'bc_parent_sha256': bc_meta['checkpoint_sha256'],
                        'observation_schema_sha256': proto['observation_schema_sha256'],
                        'action_schema_sha256': proto['action_schema_sha256'], 'reward_v2_sha256': proto['reward_v2_sha256'],
                        'constraints_sha256': proto['constraints_sha256'], 'checkpoint_sha256': h,
                        'lambda_u': lam_u, 'lambda_p': lam_p, 'beta_kl': beta, 'entropy_coef': ent_coef}
                (out / ('ckpt_it%03d.json' % it)).write_text(json.dumps(meta, indent=1) + '\n', encoding='utf-8')
    log.close()


def ppo_smoke(seed):
    out = OUT / ('smoke_seed_%d' % seed)
    if out.exists():
        import shutil
        shutil.rmtree(out)
    ppo_train(seed, iterations=int(os.environ.get('M23_SMOKE_ITERS', '12')), out=out, frozen=False)


def freeze():
    if PROTOCOL_FILE.exists():
        raise SystemExit('already frozen')
    gate = json.loads((TRACK / 'bc_gate.json').read_text(encoding='utf-8'))
    if not gate['pass']:
        raise SystemExit('the BC gate did not pass; PPO must not proceed')
    p22 = json.loads((ROOT / 'game/learning/m2_2_protocol.json').read_text(encoding='utf-8'))
    man = TRACK / 'bc_dataset_manifest.json'
    proto = {'label': 'M2.3 frozen PPO fine-tuning protocol (from the BC warm start)',
             'frozen_utc': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()), 'ppo': PPO,
             'bc_checkpoint_sha256': gate['bc_checkpoint_sha256'],
             'bc_checkpoint_file_sha256': hashlib.sha256((TRACK / 'bc_checkpoint.npz').read_bytes()).hexdigest(),
             'bc_dataset_manifest_sha256': hashlib.sha256(man.read_bytes()).hexdigest(),
             'bc_gate_sha256': hashlib.sha256((TRACK / 'bc_gate.json').read_bytes()).hexdigest(),
             'architecture': 'frozen M2.0 MLP 60 -> 32 tanh -> 11 (2,315 parameters); stochastic seeded sampling',
             'split': p22['split'], 'split_sha256': p22['split_sha256'],
             'reward_v2_sha256': p22['reward_v2_sha256'], 'constraints_sha256': p22['constraints_sha256'],
             'observation_schema_sha256': p22['observation_schema_sha256'],
             'action_schema_sha256': p22['action_schema_sha256'],
             'max_environment_steps': '60 iterations x about 30,000 decisions per training seed (logged exactly)'}
    PROTOCOL_FILE.write_text(json.dumps(proto, indent=1) + '\n', encoding='utf-8')
    print('frozen', hashlib.sha256(PROTOCOL_FILE.read_bytes()).hexdigest())


def kl_to_bc(model, bc_model, X):
    Pm, _ = policy_forward(model, X)
    Pq, _ = policy_forward(bc_model, X)
    return float((Pm * (np.log(Pm + 1e-12) - np.log(Pq + 1e-12))).sum(1).mean())


def validate():
    ppo_protocol()
    base = json.loads((ROOT / 'artifacts/m2_2/val/baselines.json').read_text(encoding='utf-8'))
    path = OUT / 'val' / 'checkpoints.json'
    results = json.loads(path.read_text(encoding='utf-8')) if path.exists() else {}
    bc_model, _ = load_bc()
    Xv = np.load(OUT / 'bc_val.npz')['obs'].astype(np.float64)
    specs = M22.val_specs()
    with mp.get_context('spawn').Pool(WORKERS, initializer=training.worker_init) as pool:
        for c in sorted((OUT / 'runs').glob('seed_*/ckpt_it*.npz')):
            key = '%s/%s' % (c.parent.name, c.stem)
            if key in results:
                continue
            meta = json.loads(c.with_suffix('.json').read_text(encoding='utf-8'))
            model = MLPPolicyModel.load(c, expected_sha256=meta['checkpoint_sha256'])
            recs = [r for ch in pool.map(training.eval_task, [(model.params, cc, 'TRAIN') for cc in M22.chunks(specs, WORKERS)])
                    for r in ch]
            ev = M22.evaluate_records(recs, base)['candidate']
            resp = escape_response(model)
            cats = ev['background']['category_counts']
            none_share = cats.get('NONE', 0) / max(1, sum(cats.values()))
            collapse_ok = (resp['escape_prob_strong_left'] >= 0.2
                           and resp['escape_prob_strong_left'] >= 10 * resp['escape_prob_quiet'] and none_share < 0.995)
            eligible = bool(ev['admissible'] and ev['threat']['escape_in_window_fraction'] >= 0.3 and collapse_ok)
            results[key] = {'meta': meta, 'summary': summarize(ev), 'escape_response': resp,
                            'none_share_background': none_share, 'no_escape_collapse_diagnostic_ok': collapse_ok,
                            'eligible': eligible, 'kl_to_bc_val_states': kl_to_bc(model, bc_model, Xv),
                            'threat_by_family': {f: x['hit_probability'] for f, x in ev['threat_by_family'].items()}}
            path.write_text(json.dumps(results, indent=1, default=float) + '\n', encoding='utf-8')
            s = results[key]['summary']
            print('val %s hit %.3f win %.2f unnec %.2f perch %.2f adm %s collapse_ok %s eligible %s KLbc %.4f' % (
                key, s['hit_probability'], s['escape_in_window'], s['unnecessary_per_min'], s['perches_per_min'] or 0.0,
                s['admissible'], collapse_ok, eligible, results[key]['kl_to_bc_val_states']), flush=True)


def select():
    proto, proto_sha = ppo_protocol()
    if CANDIDATE_FILE.exists():
        raise SystemExit('candidate already frozen')
    res = json.loads((OUT / 'val' / 'checkpoints.json').read_text(encoding='utf-8'))
    el = {k: v for k, v in res.items() if v['eligible']}
    rec = {'label': 'M2.3 frozen learned candidate', 'selected_utc': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
           'selection_rule': PPO['selection'], 'eligibility_rule': PPO['eligibility'], 'protocol_sha256': proto_sha,
           'n_checkpoints': len(res), 'n_eligible': len(el), 'eligible': sorted(el)}
    if not el:
        rec['candidate'] = None
        CANDIDATE_FILE.write_text(json.dumps(rec, indent=1) + '\n', encoding='utf-8')
        print('NO ELIGIBLE CHECKPOINT')
        return
    best = min(el, key=lambda k: (el[k]['summary']['hit_probability'], el[k]['summary']['unnecessary_per_min'],
                                  el[k]['kl_to_bc_val_states']))
    src = OUT / 'runs' / best.split('/')[0] / (best.split('/')[1] + '.npz')
    m = MLPPolicyModel.load(src, expected_sha256=res[best]['meta']['checkpoint_sha256'])
    h = m.save(CANDIDATE_CKPT)
    rec.update({'candidate': best, 'checkpoint_sha256': h,
                'checkpoint_file_sha256': hashlib.sha256(CANDIDATE_CKPT.read_bytes()).hexdigest(),
                'bc_parent_sha256': proto['bc_checkpoint_sha256'], 'training_seed': res[best]['meta']['training_seed'],
                'iteration': res[best]['meta']['iteration'], 'env_steps': res[best]['meta']['env_steps'],
                'reward_v2_sha256': proto['reward_v2_sha256'], 'constraints_sha256': proto['constraints_sha256'],
                'observation_schema_sha256': proto['observation_schema_sha256'],
                'action_schema_sha256': proto['action_schema_sha256'], 'selection_evidence': res[best]})
    CANDIDATE_FILE.write_text(json.dumps(rec, indent=1, default=float) + '\n', encoding='utf-8')
    print('selected', best, h)


def eval_final():
    ppo_protocol()
    cand = json.loads(CANDIDATE_FILE.read_text(encoding='utf-8'))
    if cand['candidate'] is None:
        raise SystemExit('no candidate')
    done = OUT / 'eval' / 'records.json'
    if done.exists():
        raise SystemExit('the one-shot EVAL has already been run')
    model = MLPPolicyModel.load(CANDIDATE_CKPT, expected_sha256=cand['checkpoint_sha256'])
    sd = M22.m21().seeds('eval')
    specs = [(g.split(':')[0], g.split(':')[1], g.split(':')[2] if g.startswith('threat') else None, s)
             for g, lst in sd.items() for s in lst]
    with mp.get_context('spawn').Pool(WORKERS, initializer=training.worker_init) as pool:
        recs = [r for ch in pool.map(training.eval_task, [(model.params, cc, 'EVAL') for cc in M22.chunks(specs, WORKERS)])
                for r in ch]
    (OUT / 'eval').mkdir(parents=True, exist_ok=True)
    done.write_text(json.dumps(recs, default=float) + '\n', encoding='utf-8')
    base = {}
    for f in sorted((ROOT / 'artifacts/m2_1/eval').glob('part_*.jsonl')):
        for l in f.open(encoding='utf-8'):
            r = json.loads(l)
            base.setdefault(r['policy'], []).append(r)
    ev = M22.evaluate_records(recs, base)
    rep = {'candidate': cand['candidate'], 'checkpoint_sha256': cand['checkpoint_sha256'], 'code_commit': M22.git_head(),
           'evaluation': ev, 'candidate_summary': summarize(ev['candidate']),
           'candidate_escape_response': escape_response(model)}
    (OUT / 'eval' / 'report.json').write_text(json.dumps(rep, indent=1, default=float) + '\n', encoding='utf-8')
    for p, v in ev.items():
        print('%-20s hit %.3f %s win %.2f unnec %.2f perch %.2f adm %s flags %s' % (
            p, v['threat']['hit_probability'], {a: round(x['hit_probability'], 3) for a, x in v['threat_by_attacker'].items()},
            v['threat']['escape_in_window_fraction'] or 0.0, v['background_unnecessary_per_min'],
            v['background']['perches_per_min'] or 0.0, v['admissible'], [k for k, f in v['anti_cheat_flags'].items() if f]))


if __name__ == '__main__':
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('mode')
    ap.add_argument('--seed', type=int)
    a = ap.parse_args()
    {'ppo-smoke': lambda: ppo_smoke(a.seed), 'freeze': freeze, 'train': lambda: ppo_train(a.seed),
     'validate': validate, 'select': select, 'eval-final': eval_final}[a.mode]()
