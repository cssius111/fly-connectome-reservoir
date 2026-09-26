"""M2.2 constrained learned dodge policy: protocol, training, validation, selection, one-shot EVAL.

    python tools/m2_2_train.py smoke                     (implementation check, before the freeze)
    python tools/m2_2_train.py freeze                    (writes game/learning/m2_2_protocol.json)
    python tools/m2_2_train.py train --seed K            (K = 1..5; uses 7 rollout workers)
    python tools/m2_2_train.py val-baselines             (TRAIN-VAL, non-learning policies)
    python tools/m2_2_train.py validate                  (every checkpoint on TRAIN-VAL)
    python tools/m2_2_train.py select                    (frozen rule; writes the candidate record)
    python tools/m2_2_train.py eval-final                (the frozen candidate, once, on the M2.1 EVAL set)
    python tools/m2_2_train.py report

Artifacts: artifacts/m2_2/ (git-ignored). The protocol, the candidate record and the small
candidate checkpoint are tracked.
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
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

from game.learning import contracts, runmode, trials, training  # noqa: E402
from game.learning.model import MLPPolicyModel  # noqa: E402
from game.learning.ppo import (Adam, ValueModel, clip_grads, gae, policy_forward,  # noqa: E402
                               ppo_policy_loss_and_grads, value_loss_and_grads)
from game.learning.reward_v2 import RewardV2  # noqa: E402

OUT = ROOT / 'artifacts/m2_2'
PROTOCOL_FILE = ROOT / 'game/learning/m2_2_protocol.json'
CANDIDATE_FILE = ROOT / 'game/learning/m2_2_candidate.json'
CANDIDATE_CKPT = ROOT / 'game/learning/checkpoints/m2_2_candidate.npz'
FROZEN_V2 = ROOT / 'game/learning/benchmark_v2_frozen.json'
WORKERS = 7
BASELINES = ('baseline_n4b1c', 'no_escape', 'fixed_maneuver', 'random_legal', 'probe_always_escape',
             'probe_constant_turn', 'probe_clock_escape')

HYPER = {
    'model': 'frozen M2.0 MLPPolicyModel 60 -> 32 tanh -> 11 logits (2,315 parameters), fixed input scaling; '
             'categorical policy; stochastic sampling from the policy\'s seeded RNG is part of the frozen policy',
    'critic': 'training-only ValueModel 60 -> 32 tanh -> 1 (1,985 parameters), same fixed input scaling',
    'init_none_prior': 0.97,
    'optimizer': 'Adam (beta1 0.9, beta2 0.999, eps 1e-8), separate for policy and critic',
    'learning_rate': 3e-4, 'gamma': 0.99, 'gae_lambda': 0.95, 'ppo_clip': 0.2, 'entropy_coef': 0.01,
    'value_coef': 0.5, 'update_epochs': 4, 'minibatch_size': 4096, 'grad_clip_norm': 0.5,
    'advantage_normalization': 'per batch (mean 0, s.d. 1)', 'reward_normalization': 'none',
    'rollout_units_per_iteration': WORKERS, 'unit': '1 background episode + 3 threat trials',
    'iterations': 100, 'checkpoint_every': 20,
    'dual': {'unnecessary_target_per_min': 0.8 * 5.36, 'unnecessary_step': 0.05,
             'perch_target_per_min': 1.5 * 0.275, 'perch_step': 0.05, 'ema_alpha': 0.3,
             'lambda_u_max': 10.0, 'lambda_p_max': 5.0, 'lambda_init': 0.0,
             'update': 'lambda <- clip(lambda + step * normalized violation, 0, max); normalized violation = '
                       '(ema_u - target_u) / target_u for unnecessary escapes and (target_p - ema_p) / target_p for '
                       'perches; targets carry a safety margin (0.8 x budget, 1.5 x minimum)'},
    'training_seeds': [1, 2, 3, 4, 5],
    'early_stopping': 'none: fixed budget of 100 iterations per training seed; every checkpoint is validated',
    'selection': 'TRAIN-VAL only. Eligible: unnecessary escapes / min <= 5.36, perches / min >= 0.275, all M2.1 '
                 'movement constraints, and no anti-cheat flag (M2.1 admissibility, anti-cheat reference = the '
                 'baseline on TRAIN-VAL). Among eligible checkpoints: lowest committed-strike hit probability; '
                 'ties: lower unnecessary escapes / min, then earlier checkpoint. Scalar reward is not used.',
}


def dev_seeds():
    fz = json.loads(FROZEN_V2.read_text(encoding='utf-8'))
    return {s for v in fz['dev_seeds'].values() for s in v}


def split():
    """TRAIN-OPT: episode seeds drawn from [20e6, 25e6) minus M2.1 development seeds.
    TRAIN-VAL: an explicit list from [25e6, 30e6) minus M2.1 development seeds."""
    dev = dev_seeds()
    groups = ['threat:%s:%s' % (f.name, a) for f in trials.THREAT_FAMILIES for a in trials.ATTACKERS] + \
             ['background:%s' % c.name for c in trials.BACKGROUND_FAMILIES]
    val = {}
    for g_i, g in enumerate(groups):
        rng = np.random.default_rng(2200 + g_i)
        n = 8 if g.startswith('threat') else 6
        lst = []
        while len(lst) < n:
            s = int(rng.integers(25_000_000, 30_000_000))
            if s not in dev and s not in lst:
                lst.append(s)
        val[g] = lst
    flat = [s for v in val.values() for s in v]
    assert len(flat) == len(set(flat))
    return {'train_opt': {'range': [20_000_000, 24_999_999], 'excluded': 'M2.1 development seeds'},
            'train_val': val}


def split_sha(sp):
    return hashlib.sha256(json.dumps(sp, sort_keys=True).encode()).hexdigest()


def freeze():
    if PROTOCOL_FILE.exists():
        raise SystemExit('protocol already frozen')
    fz = json.loads(FROZEN_V2.read_text(encoding='utf-8'))
    sp = split()
    proto = {'label': 'M2.2 frozen training protocol (constrained PPO)', 'frozen_utc': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
             'hyperparameters': HYPER, 'reward_v2': fz['reward_v2'], 'reward_v2_sha256': fz['reward_v2_sha256'],
             'constraints': fz['constraints'],
             'constraints_sha256': hashlib.sha256(json.dumps(fz['constraints'], sort_keys=True).encode()).hexdigest(),
             'benchmark_v2_frozen_sha256': hashlib.sha256(FROZEN_V2.read_bytes()).hexdigest(),
             'observation_schema_sha256': hashlib.sha256(json.dumps(contracts.OBSERVATION_SCHEMA, sort_keys=True).encode()).hexdigest(),
             'action_schema_sha256': hashlib.sha256(json.dumps(contracts.ACTION_SCHEMA, sort_keys=True).encode()).hexdigest(),
             'split': sp, 'split_sha256': split_sha(sp),
             'max_environment_steps': 'iterations x rollout (about 2.5 million policy decisions per training seed; '
                                      'the exact count is logged)',
             'evaluation_cadence': 'every %d iterations and at the end' % HYPER['checkpoint_every']}
    PROTOCOL_FILE.write_text(json.dumps(proto, indent=1) + '\n', encoding='utf-8')
    print('frozen protocol', hashlib.sha256(PROTOCOL_FILE.read_bytes()).hexdigest())


def protocol():
    if not PROTOCOL_FILE.exists():
        raise SystemExit('freeze the protocol first')
    p = json.loads(PROTOCOL_FILE.read_text(encoding='utf-8'))
    if p['hyperparameters'] != json.loads(json.dumps(HYPER)) or p['split_sha256'] != split_sha(split()):
        raise SystemExit('the code differs from the frozen protocol')
    return p, hashlib.sha256(PROTOCOL_FILE.read_bytes()).hexdigest()


def git_head():
    import subprocess
    return subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()


# ----------------------------------------------------------------- training ---
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
    for _ in range(3):
        specs.append(('threat', fams[int(rng.integers(len(fams)))], levels[int(rng.integers(len(levels)))], seed()))
    return specs


def train(train_seed, iterations=None, workers=WORKERS, out=None, frozen=True):
    if frozen:
        proto, proto_sha = protocol()
        H = proto['hyperparameters']
    else:
        H, proto_sha = json.loads(json.dumps(HYPER)), None
    iterations = iterations or H['iterations']
    out = out or OUT / 'runs' / ('seed_%d' % train_seed)
    out.mkdir(parents=True, exist_ok=True)
    reward = RewardV2(**json.loads(FROZEN_V2.read_text(encoding='utf-8'))['reward_v2'])
    model, critic = training.init_models(train_seed, H['init_none_prior'])
    opt_p, opt_v = Adam(model.params, H['learning_rate']), Adam(critic.params, H['learning_rate'])
    D = H['dual']
    lam_u = lam_p = D['lambda_init']
    ema_u = ema_p = None
    rng = np.random.default_rng([train_seed, 2202])
    dev = dev_seeds()
    head = git_head()
    log = (out / 'log.jsonl').open('a', encoding='utf-8')
    steps = 0
    with mp.get_context('spawn').Pool(workers, initializer=training.worker_init) as pool:
        for it in range(1, iterations + 1):
            t0 = time.time()
            specs = [unit_specs(rng, dev) for _ in range(workers)]
            params = {k: v.copy() for k, v in model.params.items()}
            eps = [e for chunk in pool.map(training.rollout_task, [(params, sp) for sp in specs]) for e in chunk]
            # ---- measurements
            thr = [e for e in eps if e['kind'] == 'threat']
            bg = [e for e in eps if e['kind'] == 'background']
            bg_min = sum(e['seconds'] for e in bg) / 60
            U = sum(int(e['unnec'].sum()) for e in bg) / bg_min
            P = sum(int(e['perch'].sum()) for e in bg) / bg_min
            ema_u = U if ema_u is None else (1 - D['ema_alpha']) * ema_u + D['ema_alpha'] * U
            ema_p = P if ema_p is None else (1 - D['ema_alpha']) * ema_p + D['ema_alpha'] * P
            # ---- advantages
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
                X.append(x); A.append(e['act'].astype(int)); ADV.append(adv); RET.append(ret); V_all.append(v)
            X, A, ADV, RET, V_all = map(np.concatenate, (X, A, ADV, RET, V_all))
            P_old, _ = policy_forward(model, X)
            logp_old = np.log(P_old[np.arange(len(A)), A] + 1e-12)
            ADVn = (ADV - ADV.mean()) / (ADV.std() + 1e-8)
            stats = []
            idx = np.arange(len(A))
            for _ in range(H['update_epochs']):
                rng.shuffle(idx)
                for s0 in range(0, len(idx), H['minibatch_size']):
                    b = idx[s0:s0 + H['minibatch_size']]
                    lp, gp, st = ppo_policy_loss_and_grads(model, X[b], A[b], logp_old[b], ADVn[b], H['ppo_clip'], H['entropy_coef'])
                    gp, gnp = clip_grads(gp, H['grad_clip_norm'])
                    model.apply_update(opt_p.step(model.params, gp))
                    lv, gv = value_loss_and_grads(critic, X[b], RET[b], H['value_coef'])
                    gv, gnv = clip_grads(gv, H['grad_clip_norm'])
                    for k, d in opt_v.step(critic.params, gv).items():
                        critic.params[k] = critic.params[k] + d
                    stats.append({**st, 'value_loss': lv, 'grad_norm_policy': gnp, 'grad_norm_value': gnv})
            # ---- dual ascent
            tu, tp = D['unnecessary_target_per_min'], D['perch_target_per_min']
            lam_u = float(np.clip(lam_u + D['unnecessary_step'] * (ema_u - tu) / tu, 0, D['lambda_u_max']))
            lam_p = float(np.clip(lam_p + D['perch_step'] * (tp - ema_p) / tp, 0, D['lambda_p_max']))
            steps += len(A)
            counts = np.bincount(A, minlength=len(contracts.MANEUVERS))
            ev = 1 - np.var(RET - V_all) / (np.var(RET) + 1e-12)
            row = {'iteration': it, 'env_steps': steps, 'seconds': time.time() - t0,
                   'threat_trials': len(thr), 'hit_rate': float(np.mean([e['hit'] for e in thr])),
                   'avoidance_rate': 1 - float(np.mean([e['hit'] for e in thr])),
                   'background_minutes': bg_min, 'unnecessary_per_min': U, 'perch_per_min': P,
                   'ema_unnecessary': ema_u, 'ema_perch': ema_p, 'lambda_u': lam_u, 'lambda_p': lam_p,
                   'wall_fraction': float(np.mean(np.concatenate([e['wall'] for e in eps]))),
                   'max_speed_fraction': float(np.mean(np.concatenate([e['maxspd'] for e in eps]))),
                   'turn_fraction': float(np.mean(np.concatenate([e['turn'] for e in eps]))),
                   'escape_fraction': float(np.mean(np.concatenate([e['escape'] for e in eps]))),
                   'action_distribution': (counts / counts.sum()).round(4).tolist(),
                   'max_action_share': float(counts.max() / counts.sum()),
                   'policy_entropy': float(np.mean([s['entropy'] for s in stats])),
                   'policy_loss': float(np.mean([s['policy_loss'] for s in stats])),
                   'value_loss': float(np.mean([s['value_loss'] for s in stats])),
                   'approx_kl': float(np.mean([s['approx_kl'] for s in stats])),
                   'clipfrac': float(np.mean([s['clipfrac'] for s in stats])),
                   'explained_variance': float(ev),
                   'grad_norm_policy': float(np.mean([s['grad_norm_policy'] for s in stats])),
                   'grad_norm_value': float(np.mean([s['grad_norm_value'] for s in stats]))}
            log.write(json.dumps(row) + '\n')
            log.flush()
            print('seed %d it %3d steps %8d hit %.2f U %.1f P %.2f lam_u %.3f lam_p %.3f H %.3f kl %.4f ev %.2f (%.0f s)' % (
                train_seed, it, steps, row['hit_rate'], U, P, lam_u, lam_p, row['policy_entropy'], row['approx_kl'],
                row['explained_variance'], row['seconds']), flush=True)
            if frozen and (it % H['checkpoint_every'] == 0 or it == iterations):
                path = out / ('ckpt_it%03d.npz' % it)
                h = model.save(path)
                np.savez(out / ('critic_it%03d.npz' % it), **critic.params)
                meta = {'training_seed': train_seed, 'iteration': it, 'env_steps': steps, 'code_commit': head,
                        'protocol_sha256': proto_sha, 'observation_schema_sha256': proto['observation_schema_sha256'],
                        'action_schema_sha256': proto['action_schema_sha256'], 'reward_v2_sha256': proto['reward_v2_sha256'],
                        'constraints_sha256': proto['constraints_sha256'], 'checkpoint_sha256': h,
                        'lambda_u': lam_u, 'lambda_p': lam_p}
                (out / ('ckpt_it%03d.json' % it)).write_text(json.dumps(meta, indent=1) + '\n', encoding='utf-8')
    log.close()
    return model


def smoke():
    out = OUT / 'smoke'
    if out.exists():
        import shutil
        shutil.rmtree(out)
    train(99, iterations=3, workers=WORKERS, out=out, frozen=False)


# ----------------------------------------------------------------- validation ---
_B = {}


def _baseline_worker_init():
    from game.learning import runner
    _B['config'] = runner.load_config()
    _B['sessions'] = {}


def baseline_task(args):
    from game.learning import runner
    name, specs, mode_name = args
    if name not in _B['sessions']:
        _B['sessions'][name] = runner.make_session(runner.make_policy(name, _B['config']), _B['config'])
    s = _B['sessions'][name]
    mode = runmode.EVAL if mode_name == 'EVAL' else runmode.TRAIN
    out = []
    for kind, fam, level, seed in specs:
        if kind == 'threat':
            r = trials.run_threat_trial(s, training.FAMILIES[fam], level, seed, mode)
            r['group'] = 'threat:%s:%s' % (fam, level)
        else:
            rr = trials.run_background(s, training.BACKGROUND[fam], seed, mode)
            r = {'metrics': rr['metrics'], 'trajectory_sha256': rr['trajectory_sha256'], 'group': 'background:%s' % fam}
        r.update({'kind': kind, 'seed': seed})
        out.append(r)
    return out


def val_specs():
    out = []
    for g, lst in split()['train_val'].items():
        kind, *rest = g.split(':')
        for s in lst:
            out.append((kind, rest[0], rest[1] if kind == 'threat' else None, s))
    return out


def chunks(lst, n):
    return [lst[i::n] for i in range(n)]


def val_baselines():
    protocol()
    specs = val_specs()
    res = {}
    with mp.get_context('spawn').Pool(WORKERS, initializer=_baseline_worker_init) as pool:
        for name in BASELINES:
            recs = [r for c in pool.map(baseline_task, [(name, c, 'TRAIN') for c in chunks(specs, WORKERS)]) for r in c]
            res[name] = recs
            print('val baseline', name, len(recs), flush=True)
    (OUT / 'val').mkdir(parents=True, exist_ok=True)
    (OUT / 'val' / 'baselines.json').write_text(json.dumps(res, default=float) + '\n', encoding='utf-8')


def to_data(recs):
    d = {'threat': [], 'background': []}
    for r in recs:
        if r['kind'] == 'threat':
            d['threat'].append(r)
        else:
            m = dict(r['metrics'])
            m['group'] = r['group']
            d['background'].append(m)
    return d


def m21():
    import importlib.util
    spec = importlib.util.spec_from_file_location('m2_1_benchmark', ROOT / 'tools/m2_1_benchmark.py')
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def evaluate_records(policy_recs, baseline_recs_by_name):
    M = m21()
    fz = json.loads(FROZEN_V2.read_text(encoding='utf-8'))
    data = {n: to_data(r) for n, r in baseline_recs_by_name.items()}
    data['candidate'] = to_data(policy_recs)
    ev = M.evaluate(data, RewardV2(**fz['reward_v2']), fz['constraints'])
    return ev


def validate():
    protocol()
    base = json.loads((OUT / 'val' / 'baselines.json').read_text(encoding='utf-8'))
    specs = val_specs()
    results = {}
    path = OUT / 'val' / 'checkpoints.json'
    if path.exists():
        results = json.loads(path.read_text(encoding='utf-8'))
    ckpts = sorted((OUT / 'runs').glob('seed_*/ckpt_it*.npz'))
    with mp.get_context('spawn').Pool(WORKERS, initializer=training.worker_init) as pool:
        for c in ckpts:
            key = '%s/%s' % (c.parent.name, c.stem)
            if key in results:
                continue
            meta = json.loads(c.with_suffix('.json').read_text(encoding='utf-8'))
            model = MLPPolicyModel.load(c, expected_sha256=meta['checkpoint_sha256'])
            recs = [r for ch in pool.map(training.eval_task, [(model.params, cc, 'TRAIN') for cc in chunks(specs, WORKERS)]) for r in ch]
            ev = evaluate_records(recs, base)
            cand = ev['candidate']
            results[key] = {'meta': meta, 'hit_probability': cand['threat']['hit_probability'],
                            'threat': cand['threat'], 'threat_by_attacker': cand['threat_by_attacker'],
                            'background': cand['background'], 'constraints': cand['constraints'],
                            'anti_cheat_flags': cand['anti_cheat_flags'], 'admissible': cand['admissible'],
                            'objective_J': cand['objective_J'],
                            'unnecessary_per_min': cand['background_unnecessary_per_min']}
            path.write_text(json.dumps(results, indent=1, default=float) + '\n', encoding='utf-8')
            print('val %s hit %.3f unnec %.2f perch %.2f admissible %s flags %s' % (
                key, cand['threat']['hit_probability'], cand['background_unnecessary_per_min'],
                cand['background']['perches_per_min'] or 0.0, cand['admissible'],
                [k for k, f in cand['anti_cheat_flags'].items() if f]), flush=True)
    base_ev = evaluate_records(base['baseline_n4b1c'], base)
    (OUT / 'val' / 'baseline_eval.json').write_text(json.dumps(base_ev, indent=1, default=float) + '\n', encoding='utf-8')


def select():
    proto, proto_sha = protocol()
    if CANDIDATE_FILE.exists():
        raise SystemExit('candidate already frozen')
    res = json.loads((OUT / 'val' / 'checkpoints.json').read_text(encoding='utf-8'))
    eligible = {k: v for k, v in res.items() if v['admissible']}
    record = {'label': 'M2.2 frozen learned candidate', 'selected_utc': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
              'selection_rule': proto['hyperparameters']['selection'], 'protocol_sha256': proto_sha,
              'n_checkpoints': len(res), 'n_eligible': len(eligible), 'eligible': sorted(eligible)}
    if not eligible:
        record['candidate'] = None
        CANDIDATE_FILE.write_text(json.dumps(record, indent=1) + '\n', encoding='utf-8')
        print('NO ELIGIBLE CHECKPOINT')
        return
    best = min(eligible, key=lambda k: (eligible[k]['hit_probability'], eligible[k]['unnecessary_per_min'],
                                        eligible[k]['meta']['iteration']))
    src = OUT / 'runs' / (best.split('/')[0]) / (best.split('/')[1] + '.npz')
    m = MLPPolicyModel.load(src, expected_sha256=res[best]['meta']['checkpoint_sha256'])
    CANDIDATE_CKPT.parent.mkdir(parents=True, exist_ok=True)
    h = m.save(CANDIDATE_CKPT)
    record.update({'candidate': best, 'checkpoint_sha256': h, 'checkpoint_file': str(CANDIDATE_CKPT.relative_to(ROOT)),
                   'checkpoint_file_sha256': hashlib.sha256(CANDIDATE_CKPT.read_bytes()).hexdigest(),
                   'model': {'arch': m.arch, 'n_parameters': m.n_parameters, 'stochastic_policy': True},
                   'selection_evidence': res[best]})
    CANDIDATE_FILE.write_text(json.dumps(record, indent=1, default=float) + '\n', encoding='utf-8')
    print('selected', best, h)


def eval_final():
    protocol()
    cand = json.loads(CANDIDATE_FILE.read_text(encoding='utf-8'))
    if cand['candidate'] is None:
        raise SystemExit('no candidate')
    done = OUT / 'eval' / 'records.json'
    if done.exists():
        raise SystemExit('the one-shot EVAL has already been run')
    model = MLPPolicyModel.load(CANDIDATE_CKPT, expected_sha256=cand['checkpoint_sha256'])
    M = m21()
    sd = M.seeds('eval')
    specs = []
    for g, lst in sd.items():
        kind, *rest = g.split(':')
        for s in lst:
            specs.append((kind, rest[0], rest[1] if kind == 'threat' else None, s))
    with mp.get_context('spawn').Pool(WORKERS, initializer=training.worker_init) as pool:
        recs = [r for ch in pool.map(training.eval_task, [(model.params, cc, 'EVAL') for cc in chunks(specs, WORKERS)]) for r in ch]
    (OUT / 'eval').mkdir(parents=True, exist_ok=True)
    done.write_text(json.dumps(recs, default=float) + '\n', encoding='utf-8')
    # frozen M2.1 EVAL records of the non-learning policies (anti-cheat reference and comparison)
    base = {}
    for f in sorted((ROOT / 'artifacts/m2_1/eval').glob('part_*.jsonl')):
        for l in f.open(encoding='utf-8'):
            r = json.loads(l)
            base.setdefault(r['policy'], []).append(r)
    ev = evaluate_records(recs, base)
    rep = {'candidate': cand['candidate'], 'checkpoint_sha256': cand['checkpoint_sha256'], 'evaluation': ev,
           'code_commit': git_head()}
    (OUT / 'eval' / 'report.json').write_text(json.dumps(rep, indent=1, default=float) + '\n', encoding='utf-8')
    for p, v in ev.items():
        print('%-20s hit %.3f %s unnec %.2f perch %.2f adm %s flags %s' % (
            p, v['threat']['hit_probability'], {a: round(x['hit_probability'], 3) for a, x in v['threat_by_attacker'].items()},
            v['background_unnecessary_per_min'], v['background']['perches_per_min'] or 0.0, v['admissible'],
            [k for k, f in v['anti_cheat_flags'].items() if f]))


def report():
    """Learning / constraint curves and mode-collapse diagnostics per training seed."""
    out = {}
    for d in sorted((OUT / 'runs').glob('seed_*')):
        rows = [json.loads(l) for l in (d / 'log.jsonl').open(encoding='utf-8')]
        snaps = [r for r in rows if r['iteration'] in (1, 5, 10, 20, 30, 40, 50, 60, 70, 80, 90, 100)]

        def window(k, a, b):
            v = [r[k] for r in rows if a <= r['iteration'] <= b]
            return float(np.mean(v)) if v else None
        last = rows[-1]
        collapse = {'one_action_over_80pct': last['max_action_share'] > 0.8,
                    'permanent_escape': last['escape_fraction'] > 0.5,
                    'permanent_turn': last['turn_fraction'] > 0.5,
                    'near_zero_entropy': last['policy_entropy'] < 0.05}
        out[d.name] = {'iterations': len(rows), 'env_steps': last['env_steps'],
                       'snapshots': [{k: r[k] for k in ('iteration', 'env_steps', 'hit_rate', 'unnecessary_per_min',
                                                        'perch_per_min', 'lambda_u', 'lambda_p', 'policy_entropy',
                                                        'approx_kl', 'explained_variance', 'max_action_share',
                                                        'escape_fraction', 'turn_fraction', 'wall_fraction',
                                                        'max_speed_fraction', 'policy_loss', 'value_loss',
                                                        'grad_norm_policy', 'clipfrac')} for r in snaps],
                       'hit_rate_first10': window('hit_rate', 1, 10), 'hit_rate_last20': window('hit_rate', 81, 100),
                       'unnecessary_last20': window('unnecessary_per_min', 81, 100),
                       'perch_last20': window('perch_per_min', 81, 100),
                       'final_action_distribution': last['action_distribution'], 'collapse_flags': collapse}
    (OUT / 'training_report.json').write_text(json.dumps(out, indent=1) + '\n', encoding='utf-8')
    for k, v in out.items():
        print(k, 'steps', v['env_steps'], 'hit first10 %.3f last20 %.3f' % (v['hit_rate_first10'], v['hit_rate_last20'] or -1),
              'U last20 %.2f P last20 %.2f' % (v['unnecessary_last20'] or -1, v['perch_last20'] or -1), 'collapse', v['collapse_flags'])


if __name__ == '__main__':
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('mode', choices=('smoke', 'freeze', 'train', 'val-baselines', 'validate', 'select', 'eval-final', 'report'))
    ap.add_argument('--seed', type=int)
    a = ap.parse_args()
    {'smoke': smoke, 'freeze': freeze, 'train': lambda: train(a.seed), 'val-baselines': val_baselines,
     'validate': validate, 'select': select, 'eval-final': eval_final, 'report': report}[a.mode]()
