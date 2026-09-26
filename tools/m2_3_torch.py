"""M2.3 official learner (PyTorch): behaviour cloning + KL-anchored constrained PPO.

Reuses, unchanged, the M2.3 teacher dataset (artifacts/m2_3/bc_train.npz, bc_val.npz; manifest
game/learning/m2_3/bc_dataset_manifest.json), the fixed teacher mapping, the observation
encoding, the BC configuration and the BC acceptance gate of tools/m2_3_bc_ppo.py. Only the
learner changes: every gradient comes from torch autograd (game/learning/torch_policy.py).
The earlier numpy BC checkpoint (7b28591) stays documented as development evidence only.

    python tools/m2_3_torch.py env                  (torch / CUDA verification)
    python tools/m2_3_torch.py bc-train             (CUDA mini-batch BC on the frozen dataset)
    python tools/m2_3_torch.py bc-gate              (frozen BC gate on the TRAIN-VAL benchmark)
    python tools/m2_3_torch.py ppo-smoke --seed K --variant NAME [--iters N]   (TRAIN-only development)
    python tools/m2_3_torch.py freeze
    python tools/m2_3_torch.py train --seed K       (K in the frozen training seeds)
    python tools/m2_3_torch.py validate | select | compare | eval-final

Environment rollouts (MaleCNS + game simulation + per-tick numpy inference) run on 7 CPU
worker processes; the learner update runs on CUDA. Artifacts: artifacts/m2_3/torch/
(git-ignored). Protocol, gate, metrics, candidate record and small checkpoints are tracked in
game/learning/m2_3/.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import importlib.util
import json
import multiprocessing as mp
import os
from pathlib import Path
import subprocess
import sys
import threading
import time

os.environ.setdefault('NUMBA_NUM_THREADS', '1')
os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')
os.environ.setdefault('CUBLAS_WORKSPACE_CONFIG', ':4096:8')
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import numpy as np  # noqa: E402
import torch  # noqa: E402

from game.learning import contracts, torch_training, training, trials  # noqa: E402
from game.learning.contracts import MANEUVERS, N_MANEUVERS  # noqa: E402
from game.learning.model import MLPPolicyModel  # noqa: E402
from game.learning.reward_v2 import RewardV2  # noqa: E402
from game.learning.torch_policy import (TorchCritic, TorchPolicy, bc_loss, default_device, gae, init_critic,  # noqa: E402
                                        kl_to_reference, load_checkpoint, ppo_surrogate, save_checkpoint,
                                        set_determinism, state_dict_sha256, value_loss)

_spec = importlib.util.spec_from_file_location('m2_3_bc_ppo', ROOT / 'tools/m2_3_bc_ppo.py')
BCT = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(BCT)
M22, WORKERS, NONE, ESCAPES = BCT.M22, BCT.WORKERS, BCT.NONE, BCT.ESCAPES
DATA = ROOT / 'artifacts/m2_3'                      # frozen teacher dataset (shared with the numpy tool)
OUT = DATA / 'torch'
TRACK = ROOT / 'game/learning/m2_3'
BC_CKPT = TRACK / 'torch_bc_checkpoint.pt'
BC_METRICS = TRACK / 'torch_bc_metrics.json'
BC_GATE_FILE = TRACK / 'torch_bc_gate.json'
PROTOCOL_FILE = TRACK / 'torch_ppo_protocol.json'
CANDIDATE_FILE = TRACK / 'torch_candidate.json'
CANDIDATE_CKPT = TRACK / 'torch_candidate.pt'
CANDIDATE_NPZ = ROOT / 'game/learning/checkpoints/m2_3_candidate.npz'
NAMES = [m.name for m in MANEUVERS]

BC_TORCH = {
    'reuses': 'tools/m2_3_bc_ppo.py BC_CONFIG unchanged (same dataset, NONE subsampling mask, prior correction, '
              'learning rate, batch size, epochs, shuffle order, clipping and checkpoint-selection rule)',
    'model': 'TorchPolicy (torch.nn.Module), 60 -> 32 tanh -> 11, 2,315 trainable parameters',
    'init': 'parameters copied from MLPPolicyModel(seed = 2303), the numpy BC initialisation',
    'loss': 'torch.nn.functional.cross_entropy on logits + log(0.05) NONE offset (training); natural distribution '
            'for TRAIN-VAL selection',
    'optimizer': 'torch.optim.Adam(lr 1e-3, betas (0.9, 0.999), eps 1e-8)',
    'grad_clip': 'torch.nn.utils.clip_grad_norm_(max_norm = 1.0)', 'dtype': 'float32', 'device': 'cuda',
    'determinism': 'torch.use_deterministic_algorithms(True), CUBLAS_WORKSPACE_CONFIG=:4096:8',
}

# ----------------------------------------------------------------- PPO configuration ---
# The draft below is the numpy M2.3 draft translated to torch. Development smoke variants
# override individual entries; the protocol freezes one final dictionary.
PPO = {
    'learner': 'PyTorch (torch.nn.Module policy + separate critic, autograd, torch.optim.Adam, '
               'torch.distributions.Categorical, clip_grad_norm_), float32 on CUDA',
    'init': 'every training seed starts from the frozen PyTorch BC checkpoint (identical parameters)',
    'reference': 'a frozen deep copy of the BC policy (requires_grad False, never updated)',
    'critic_init': 'separate TorchCritic 60 -> 32 tanh -> 1, W1 ~ N(0, 1/sqrt(60)), W2 ~ N(0, 0.01), zero biases, '
                   'torch generator seed = training seed + 1; policy frozen during the critic warm-up',
    'critic_warmup_iterations': 3,
    'lr_policy': 3e-4, 'lr_critic': 1e-3,
    'development_choice': 'lr_policy 3e-4 chosen over 1e-4 from the TRAIN-only smokes (draft seed 101, lr3e-4 seed '
                          '102): at 1e-4 clipfrac stayed 0 and KL(policy || BC) ~1e-4 (updates too small to test '
                          'improvement); at 3e-4 KL rose to ~1e-3 with conditional escape, entropy and dual warm-up '
                          'intact. KL schedule, entropy control, dual warm-up and the 1 : 6 mixture unchanged.', 'adam': [0.9, 0.999, 1e-8],
    'gamma': 0.99, 'gae_lambda': 0.95, 'ppo_clip': 0.2, 'value_coef': 1.0,
    'update_epochs': 4, 'minibatch_size': 4096, 'grad_clip_norm': 0.5,
    'advantage_normalization': 'per batch (mean 0, std 1)', 'reward_normalization': 'none',
    'kl_anchor': {'beta_start': 1.0, 'hold_until_iteration': 15, 'beta_end': 0.1, 'decay_until_iteration': 45},
    'entropy': {'target_fraction': 0.8, 'coef_init': 0.001, 'coef_min': 1e-4, 'coef_max': 0.05, 'gain': 0.5},
    'dual': {'min_warmup_iterations': 15, 'stable_iterations_required': 3,
             'conditional_escape_check': 'synthetic strong one-sided DNp01 escape probability >= 0.2 and >= 10 x quiet, '
                                         'and threat-trial escape fraction >= 0.5',
             'unnecessary_target_per_min': 0.9 * 5.36, 'perch_target_per_min': 1.5 * 0.275, 'step': 0.02,
             'ema_alpha': 0.3, 'lambda_u_max': 10.0, 'lambda_p_max': 5.0},
    'mixture': {'background_per_unit': 1, 'threat_per_unit': 6},
    'rollout_units_per_iteration': WORKERS, 'iterations': 60, 'checkpoint_every': 10,
    'training_seeds': [1, 2, 3, 4, 5], 'rollout_seed_salt': 2306,
}
SMOKE_VARIANTS = {
    'draft': {},
    'lr3e-4': {'lr_policy': 3e-4},
}


def env_info():
    info = {'python': sys.version.split()[0], 'torch': torch.__version__, 'cuda_runtime': torch.version.cuda,
            'cuda_available': torch.cuda.is_available(), 'cudnn': torch.backends.cudnn.version()}
    if torch.cuda.is_available():
        info['device'] = torch.cuda.get_device_name(0)
        info['capability'] = list(torch.cuda.get_device_capability(0))
        info['device_memory_gb'] = round(torch.cuda.get_device_properties(0).total_memory / 2 ** 30, 2)
    return info


class GpuSampler:
    """Samples nvidia-smi utilisation / memory in a background thread (approximate)."""

    def __init__(self, period=0.5):
        self.period, self.rows, self._stop = period, [], threading.Event()

    def _run(self):
        while not self._stop.is_set():
            try:
                o = subprocess.run(['nvidia-smi', '--query-gpu=utilization.gpu,memory.used', '--format=csv,noheader,nounits'],
                                   capture_output=True, text=True, timeout=5).stdout.strip().split(',')
                self.rows.append((float(o[0]), float(o[1])))
            except Exception:                    # noqa: BLE001 - diagnostics only
                pass
            self._stop.wait(self.period)

    def __enter__(self):
        self._t = threading.Thread(target=self._run, daemon=True)
        self._t.start()
        return self

    def __exit__(self, *a):
        self._stop.set()
        self._t.join()

    def summary(self):
        if not self.rows:
            return None
        u = np.array([r[0] for r in self.rows])
        m = np.array([r[1] for r in self.rows])
        return {'samples': len(u), 'util_mean_pct': float(u.mean()), 'util_max_pct': float(u.max()),
                'memory_used_max_mib': float(m.max())}


def sha_file(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def load_dataset():
    man = json.loads((TRACK / 'bc_dataset_manifest.json').read_text(encoding='utf-8'))
    out = {}
    for name in ('train', 'val'):
        d = dict(np.load(DATA / ('bc_%s.npz' % name)))
        if BCT.sha_arrays(d) != man[name]['sha256']:
            raise SystemExit('dataset %s does not match the frozen manifest' % name)
        out[name] = d
    return out['train'], out['val'], man


def probs_torch(net, X, dev, batch=65536):
    net.eval()
    out = []
    with torch.no_grad():
        for s in range(0, len(X), batch):
            out.append(torch.softmax(net(torch.as_tensor(X[s:s + batch], device=dev)), -1).double().cpu().numpy())
    return np.concatenate(out)


def dnp01_bins(P, obs):
    """Escape probability by the current-frame max(DNp01 left, right) (t0 fields 1 and 2)."""
    d = np.maximum(obs[:, 1], obs[:, 2])
    esc = P[:, ESCAPES].sum(1)
    edges = [0.0, 0.25, 1.0, 2.0, np.inf]
    out = []
    for lo, hi in zip(edges[:-1], edges[1:]):
        m = (d >= lo) & (d < hi)
        out.append({'dnp01_max': [lo, None if np.isinf(hi) else hi], 'samples': int(m.sum()),
                    'mean_escape_prob': float(esc[m].mean()) if m.any() else None})
    return out


def extended_metrics(P, y, d):
    m = BCT.supervised_metrics(P, y, d)
    pred = P.argmax(1)
    rec = [v['recall'] for v in m['per_action'].values() if v['support'] > 0]
    esc_true = np.isin(y, ESCAPES)
    esc_prob = P[:, ESCAPES].sum(1)
    win, bg = d['ctx_threat_window'], d['ctx_kind'] == 0
    m['balanced_accuracy'] = float(np.mean(rec))
    m['frequencies'] = {'teacher': dict(zip(NAMES, np.bincount(y, minlength=N_MANEUVERS).tolist())),
                        'learner_argmax': dict(zip(NAMES, np.bincount(pred, minlength=N_MANEUVERS).tolist())),
                        'learner_expected': dict(zip(NAMES, P.sum(0).round(1).tolist()))}
    m['escape_recall'] = {'argmax_any_escape_on_teacher_escapes': float(np.isin(pred[esc_true], ESCAPES).mean()),
                          'argmax_exact_on_teacher_escapes': float((pred[esc_true] == y[esc_true]).mean()),
                          'argmax_escape_precision': float(np.isin(y[np.isin(pred, ESCAPES)], ESCAPES).mean())
                          if np.isin(pred, ESCAPES).any() else None}
    m['escape_probability'] = {'threat_window_all': float(esc_prob[win].mean()),
                               'threat_window_teacher_escape': float(esc_prob[win & esc_true].mean()),
                               'threat_window_teacher_no_escape': float(esc_prob[win & ~esc_true].mean()),
                               'background_all': float(esc_prob[bg].mean()),
                               'threat_outside_window': float(esc_prob[(d['ctx_kind'] == 1) & ~win].mean()),
                               'by_dnp01': dnp01_bins(P, d['obs'])}
    return m


# ----------------------------------------------------------------- behaviour cloning ---
def bc_train():
    C = BCT.BC_CONFIG
    tr, va, man = load_dataset()
    dev = default_device()
    if dev.type != 'cuda':
        raise SystemExit('official M2.3 BC must run on CUDA')
    set_determinism(C['init_seed'])
    rng = np.random.default_rng(C['none_subsample_seed'])
    keep = (tr['label'] != NONE) | (rng.random(len(tr['label'])) < C['none_keep_fraction'])
    X = torch.as_tensor(tr['obs'][keep], dtype=torch.float32, device=dev)
    y = torch.as_tensor(tr['label'][keep].astype(np.int64), device=dev)
    Xv = torch.as_tensor(va['obs'], dtype=torch.float32, device=dev)
    yv = torch.as_tensor(va['label'].astype(np.int64), device=dev)
    off = torch.zeros(N_MANEUVERS, device=dev)
    off[NONE] = float(np.log(C['none_keep_fraction']))
    net = TorchPolicy.from_numpy_model(MLPPolicyModel(seed=C['init_seed'])).to(dev)
    init_sha = state_dict_sha256(net)
    opt = torch.optim.Adam(net.parameters(), lr=C['learning_rate'], betas=(0.9, 0.999), eps=1e-8)
    sh = np.random.default_rng(C['shuffle_seed'])
    log, best, nonfinite = [], None, 0
    torch.cuda.reset_peak_memory_stats()
    t_total = time.time()
    with GpuSampler(0.25) as gs:
        for ep in range(1, C['epochs'] + 1):
            t0 = time.time()
            net.train()
            idx = torch.as_tensor(sh.permutation(len(y)), device=dev)
            losses, gnorms = [], []
            for s0 in range(0, len(idx), C['batch_size']):
                b = idx[s0:s0 + C['batch_size']]
                loss = bc_loss(net(X[b]), y[b], off)
                opt.zero_grad(set_to_none=True)
                loss.backward()
                gn = torch.nn.utils.clip_grad_norm_(net.parameters(), C['grad_clip_norm'])
                if not torch.isfinite(gn):
                    nonfinite += 1
                    continue
                opt.step()
                losses.append(loss.detach())
                gnorms.append(gn.detach())
            net.eval()
            with torch.no_grad():
                lv = net(Xv)
                vloss = float(bc_loss(lv, yv))
                vacc = float((lv.argmax(1) == yv).float().mean())
            torch.cuda.synchronize()
            row = {'epoch': ep, 'train_loss_subsampled': float(torch.stack(losses).mean()), 'val_loss': vloss,
                   'val_accuracy': vacc, 'grad_norm_mean': float(torch.stack(gnorms).mean()),
                   'seconds': time.time() - t0}
            log.append(row)
            print(row, flush=True)
            if best is None or vloss < best[0]:
                best = (vloss, ep, copy.deepcopy(net.state_dict()))
    wall = time.time() - t_total
    net.load_state_dict(best[2])
    net = net.cpu()
    h = save_checkpoint(BC_CKPT, net, {'selected_epoch': best[1], 'val_loss': best[0]})
    np_model = net.to_numpy_model()
    Pv = probs_torch(net, va['obs'], torch.device('cpu'))
    Pt = probs_torch(net, tr['obs'], torch.device('cpu'))
    Pv_np = np.array([np_model.probabilities(x.astype(np.float64)) for x in va['obs'][:5000]])
    old = json.loads((TRACK / 'bc_metrics.json').read_text(encoding='utf-8'))
    metrics = {'label': 'M2.3 PyTorch behaviour cloning (official BC parent)', 'environment': env_info(),
               'device_used': str(dev), 'config': C, 'torch_config': BC_TORCH, 'model_class': 'game.learning.torch_policy.TorchPolicy',
               'trainable_parameters': net.n_parameters, 'init_state_dict_sha256': init_sha,
               'dataset_manifest_sha256': sha_file(TRACK / 'bc_dataset_manifest.json'),
               'train_sha256': man['train']['sha256'], 'val_sha256': man['val']['sha256'],
               'bc_samples_after_none_subsampling': int(keep.sum()),
               'selected_epoch': best[1], 'val_loss': best[0], 'checkpoint_state_dict_sha256': h,
               'checkpoint_file_sha256': sha_file(BC_CKPT), 'nonfinite_gradient_steps': nonfinite,
               'gpu': {'wall_seconds': wall, 'peak_memory_allocated_mib': torch.cuda.max_memory_allocated() / 2 ** 20,
                       'nvidia_smi': gs.summary()},
               'numpy_export_parity_max_abs_prob_diff': float(np.abs(Pv_np - Pv[:5000]).max()),
               'numpy_bc_reference': {'selected_epoch': old['selected_epoch'], 'val_loss': old['val_loss'],
                                      'checkpoint_sha256': old['checkpoint_sha256'],
                                      'status': 'development evidence only (handwritten numpy gradients)'},
               'log': log, 'val': extended_metrics(Pv, va['label'].astype(int), va),
               'train': extended_metrics(Pt, tr['label'].astype(int), tr)}
    BC_METRICS.write_text(json.dumps(metrics, indent=1, default=float) + '\n', encoding='utf-8')
    print('torch BC epoch %d val loss %.4f sha %s params %d' % (best[1], best[0], h, net.n_parameters))


def load_bc():
    meta = json.loads(BC_METRICS.read_text(encoding='utf-8'))
    net, _ = load_checkpoint(BC_CKPT, TorchPolicy, expected_sha256=meta['checkpoint_state_dict_sha256'])
    return net, meta


def bc_gate():
    net, meta = load_bc()
    model = net.to_numpy_model()
    recs = BCT.eval_policy_on_val(model.params)
    (OUT / 'val').mkdir(parents=True, exist_ok=True)
    (OUT / 'val' / 'bc_policy.json').write_text(json.dumps(recs, default=float) + '\n', encoding='utf-8')
    base = json.loads((ROOT / 'artifacts/m2_2/val/baselines.json').read_text(encoding='utf-8'))
    teacher = json.loads((DATA / 'val' / 'teacher_mapped.json').read_text(encoding='utf-8'))
    ev = M22.evaluate_records(recs, base)['candidate']
    evt = M22.evaluate_records(teacher, base)['candidate']
    evb = M22.evaluate_records(base['baseline_n4b1c'], base)['candidate']
    resp = BCT.escape_response(model)
    checks = {
        'hit_close_to_n4b1c': ev['threat']['hit_probability'] <= evb['threat']['hit_probability'] + 0.05,
        'unnecessary_within_budget': ev['background_unnecessary_per_min'] <= 5.36,
        'perch_participation': (ev['background']['perches_per_min'] or 0.0) >= 0.275,
        'admissible_no_flags': ev['admissible'],
        'threat_window_escape': ev['threat']['escape_in_window_fraction'] >= 0.5 * evt['threat']['escape_in_window_fraction'],
        'no_collapse': resp['escape_prob_strong_left'] >= 0.2 and resp['escape_prob_strong_left'] >= 10 * resp['escape_prob_quiet'],
    }
    old = json.loads((TRACK / 'bc_gate.json').read_text(encoding='utf-8'))
    gate = {'label': 'M2.3 PyTorch BC gate (the frozen BC gate of tools/m2_3_bc_ppo.py)', 'gate': BCT.BC_GATE,
            'checks': checks, 'pass': all(checks.values()), 'bc_checkpoint_state_dict_sha256': meta['checkpoint_state_dict_sha256'],
            'bc_checkpoint_file_sha256': sha_file(BC_CKPT),
            'torch_bc': BCT.summarize(ev), 'teacher_mapped': BCT.summarize(evt), 'n4b1c': BCT.summarize(evb),
            'numpy_bc_development_evidence': old['bc'], 'escape_response': resp}
    BC_GATE_FILE.write_text(json.dumps(gate, indent=1, default=float) + '\n', encoding='utf-8')
    print(json.dumps({k: gate[k] for k in ('checks', 'pass', 'escape_response')}, indent=1, default=float))
    for n in ('n4b1c', 'teacher_mapped', 'torch_bc', 'numpy_bc_development_evidence'):
        print(n, gate[n])


# ----------------------------------------------------------------- PPO ---
def unit_specs(rng, dev_seeds, mix):
    fams = [f.name for f in trials.THREAT_FAMILIES]
    levels = list(trials.ATTACKERS)
    bgs = [c.name for c in trials.BACKGROUND_FAMILIES]

    def seed():
        while True:
            s = int(rng.integers(20_000_000, 25_000_000))
            if s not in dev_seeds:
                return s
    specs = [('background', bgs[int(rng.integers(len(bgs)))], None, seed()) for _ in range(mix['background_per_unit'])]
    for _ in range(mix['threat_per_unit']):
        specs.append(('threat', fams[int(rng.integers(len(fams)))], levels[int(rng.integers(len(levels)))], seed()))
    return specs


def beta_at(it, K):
    if it <= K['hold_until_iteration']:
        return K['beta_start']
    if it >= K['decay_until_iteration']:
        return K['beta_end']
    f = (it - K['hold_until_iteration']) / (K['decay_until_iteration'] - K['hold_until_iteration'])
    return K['beta_start'] + f * (K['beta_end'] - K['beta_start'])


def deep_update(base, over):
    out = copy.deepcopy(base)
    for k, v in over.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = deep_update(out[k], v)
        else:
            out[k] = v
    return out


def ppo_protocol():
    if not PROTOCOL_FILE.exists():
        raise SystemExit('freeze the PPO protocol first')
    p = json.loads(PROTOCOL_FILE.read_text(encoding='utf-8'))
    if p['ppo'] != json.loads(json.dumps(PPO)):
        raise SystemExit('code differs from the frozen PPO protocol')
    if p['bc_checkpoint_state_dict_sha256'] != json.loads(BC_METRICS.read_text(encoding='utf-8'))['checkpoint_state_dict_sha256']:
        raise SystemExit('BC checkpoint differs from the frozen protocol')
    return p, sha_file(PROTOCOL_FILE)


def per_sample_pg_norms(policy, X, A, ADV):
    """Per-sample gradient norms of -adv * log pi(a | x) with torch.func (diagnostic only)."""
    from torch.func import functional_call, grad, vmap
    params = {k: v.detach() for k, v in policy.named_parameters()}
    buffers = {k: v for k, v in policy.named_buffers()}

    def f(p, x, a, adv):
        logits = functional_call(policy, (p, buffers), (x[None],))
        return -adv * torch.log_softmax(logits, -1)[0].gather(0, a.unsqueeze(0))[0]
    g = vmap(grad(f), in_dims=(None, 0, 0, 0))(params, X, A, ADV)
    norms = torch.sqrt(sum(v.flatten(1).pow(2).sum(1) for v in g.values()))
    summed = torch.sqrt(sum(v.sum(0).pow(2).sum() for v in g.values()))
    return norms, summed


def credit_diagnostic(eps, ADV, ADVn, policy, Xt, At, ADVt, dev, rng):
    """Sparse temporal credit: decisions per strike, advantage mass around the click, PG magnitudes."""
    offs = np.cumsum([0] + [len(e['act']) for e in eps])
    thr = [i for i, e in enumerate(eps) if e['kind'] == 'threat']
    strikes = sum(int((e['task'] != 0).sum()) for e in eps)
    n_thr = sum(len(eps[i]['act']) for i in thr)
    bins = [(-10 ** 6, -100), (-100, -50), (-50, -25), (-25, 0), (0, 10), (10, 25), (25, 50), (50, 10 ** 6)]
    prof = {b: [] for b in bins}
    for i in thr:
        c = eps[i]['click_index']
        if c < 0:
            continue
        rel = np.arange(len(eps[i]['act'])) - c
        a = ADV[offs[i]:offs[i + 1]]
        for b in bins:
            m = (rel >= b[0]) & (rel < b[1])
            prof[b].extend(a[m].tolist())
    A = At.cpu().numpy()
    esc_idx = np.where(np.isin(A, ESCAPES))[0]
    none_idx = np.where(A == NONE)[0]
    none_idx = rng.choice(none_idx, size=min(len(none_idx), 4000), replace=False)
    n_esc, s_esc = per_sample_pg_norms(policy, Xt[esc_idx], At[esc_idx], ADVt[esc_idx]) if len(esc_idx) else (None, None)
    n_none, s_none = per_sample_pg_norms(policy, Xt[none_idx], At[none_idx], ADVt[none_idx])
    n_all_none = int((A == NONE).sum())
    return {'committed_strikes': strikes, 'decisions_total': int(len(ADV)), 'decisions_threat': int(n_thr),
            'decisions_per_committed_strike': len(ADV) / max(1, strikes),
            'threat_decisions_per_committed_strike': n_thr / max(1, strikes),
            'frac_abs_adv_raw_ge_0.05': float(np.mean(np.abs(ADV) >= 0.05)),
            'frac_abs_adv_raw_ge_0.2': float(np.mean(np.abs(ADV) >= 0.2)),
            'frac_abs_adv_norm_ge_1': float(np.mean(np.abs(ADVn) >= 1.0)),
            'adv_raw_std': float(ADV.std()),
            'advantage_by_ticks_from_click': [{'ticks': [b[0], b[1]], 'n': len(v), 'mean': float(np.mean(v)) if v else None,
                                               'mean_abs': float(np.mean(np.abs(v))) if v else None} for b, v in prof.items()],
            'pg_escape_actions': None if n_esc is None else {
                'samples': int(len(esc_idx)), 'mean_per_sample_norm': float(n_esc.mean()),
                'summed_norm_over_batch': float(s_esc) / len(ADV)},
            'pg_none_actions': {'samples_scored': int(len(none_idx)), 'samples_total': n_all_none,
                                'mean_per_sample_norm': float(n_none.mean()),
                                'summed_norm_over_batch_extrapolated': float(s_none) * n_all_none / len(none_idx) / len(ADV)}}


def conditional_escape(eps, P):
    """Escape probability on rollout states: threat window vs background, and by current DNp01."""
    offs = np.cumsum([0] + [len(e['act']) for e in eps])
    esc = P[:, ESCAPES].sum(1)
    win, bg = np.zeros(len(esc), bool), np.zeros(len(esc), bool)
    for i, e in enumerate(eps):
        if e['kind'] == 'background':
            bg[offs[i]:offs[i + 1]] = True
        elif e['click_index'] >= 0:
            c = offs[i] + e['click_index']
            win[max(offs[i], c - 50):min(offs[i + 1], c + 40)] = True
    X = np.concatenate([e['obs'] for e in eps])
    d = np.maximum(X[:, 1], X[:, 2])
    lo, hi = d < 0.25, d >= 2.0
    return {'threat_window': float(esc[win].mean()), 'background': float(esc[bg].mean()),
            'dnp01_low_lt_0.25': float(esc[lo].mean()) if lo.any() else None,
            'dnp01_high_ge_2': float(esc[hi].mean()) if hi.any() else None, 'n_high': int(hi.sum())}


def ppo_train(train_seed, H, out, iterations=None, proto=None, proto_sha=None):
    iterations = iterations or H['iterations']
    out.mkdir(parents=True, exist_ok=True)
    dev = default_device()
    if dev.type != 'cuda':
        raise SystemExit('official M2.3 PPO updates must run on CUDA')
    set_determinism(train_seed)
    bc_net, bc_meta = load_bc()
    ref = copy.deepcopy(bc_net).to(dev).eval()
    for p in ref.parameters():
        p.requires_grad_(False)
    ref_sha = state_dict_sha256(ref)
    policy = copy.deepcopy(bc_net).to(dev)
    critic = init_critic(train_seed + 1).to(dev)
    b1, b2, eps_adam = H['adam']
    opt_p = torch.optim.Adam(policy.parameters(), lr=H['lr_policy'], betas=(b1, b2), eps=eps_adam)
    opt_v = torch.optim.Adam(critic.parameters(), lr=H['lr_critic'], betas=(b1, b2), eps=eps_adam)
    reward = RewardV2(**json.loads((ROOT / 'game/learning/benchmark_v2_frozen.json').read_text(encoding='utf-8'))['reward_v2'])
    D, K, E = H['dual'], H['kl_anchor'], H['entropy']
    lam_u = lam_p = 0.0
    ema_u = ema_p = None
    ent_coef, ent_target = E['coef_init'], None
    stable_run, dual_active_since = 0, None
    rng = np.random.default_rng([train_seed, H['rollout_seed_salt']])
    dev_seeds = BCT.dev_seeds()
    head = M22.git_head()
    log = (out / 'log.jsonl').open('a', encoding='utf-8')
    steps = 0
    (out / 'run_info.json').write_text(json.dumps({'training_seed': train_seed, 'code_commit': head, 'ppo': H,
                                                   'environment': env_info(), 'protocol_sha256': proto_sha,
                                                   'bc_parent_sha256': bc_meta['checkpoint_state_dict_sha256'],
                                                   'reference_sha256': ref_sha}, indent=1) + '\n', encoding='utf-8')
    with mp.get_context('spawn').Pool(WORKERS, initializer=training.worker_init) as pool:
        for it in range(1, iterations + 1):
            t0 = time.time()
            specs = [unit_specs(rng, dev_seeds, H['mixture']) for _ in range(H['rollout_units_per_iteration'])]
            params = policy.numpy_params()
            eps = [e for ch in pool.map(torch_training.rollout_task, [(params, sp) for sp in specs]) for e in ch]
            t_roll = time.time() - t0
            t1 = time.time()
            thr = [e for e in eps if e['kind'] == 'threat']
            bg = [e for e in eps if e['kind'] == 'background']
            bg_min = sum(e['seconds'] for e in bg) / 60
            U = sum(int(e['unnec'].sum()) for e in bg) / bg_min
            Pr = sum(int(e['perch'].sum()) for e in bg) / bg_min
            ema_u = U if ema_u is None else (1 - D['ema_alpha']) * ema_u + D['ema_alpha'] * U
            ema_p = Pr if ema_p is None else (1 - D['ema_alpha']) * ema_p + D['ema_alpha'] * Pr
            X = np.concatenate([e['obs'] for e in eps]).astype(np.float32)
            A = np.concatenate([e['act'] for e in eps]).astype(np.int64)
            Xt = torch.as_tensor(X, device=dev)
            At = torch.as_tensor(A, device=dev)
            with torch.no_grad():
                V = critic(Xt).double().cpu().numpy()
                logits_old = policy(Xt)
                logp_old = torch.distributions.Categorical(logits=logits_old).log_prob(At)
                P_old = torch.softmax(logits_old, -1).double().cpu().numpy()
                H_now = float(torch.distributions.Categorical(logits=logits_old).entropy().mean())
                ref_logits = ref(Xt)
            ADV, RET, off = [], [], 0
            for e in eps:
                n = len(e['act'])
                r = e['task'].astype(np.float64) - (reward.unnecessary + lam_u) * e['unnec'] + lam_p * e['perch']
                v = V[off:off + n]
                dones = np.zeros(n)
                if e['terminal']:
                    dones[-1], last = 1.0, 0.0
                else:
                    last = float(v[-1])
                a, rt = gae(r, v, dones, last, H['gamma'], H['gae_lambda'])
                ADV.append(a)
                RET.append(rt)
                off += n
            ADV, RET = np.concatenate(ADV), np.concatenate(RET)
            ADVn = (ADV - ADV.mean()) / (ADV.std() + 1e-8)
            ADVt = torch.as_tensor(ADVn, dtype=torch.float32, device=dev)
            RETt = torch.as_tensor(RET, dtype=torch.float32, device=dev)
            if ent_target is None:
                ent_target = E['target_fraction'] * H_now
            t_prep = time.time() - t1
            credit = credit_diagnostic(eps, ADV, ADVn, policy, Xt, At, ADVt, dev, rng)
            beta = beta_at(it, K)
            update_policy = it > H['critic_warmup_iterations']
            torch.cuda.synchronize()
            t2 = time.time()
            stats = {k: [] for k in ('policy_loss', 'approx_kl', 'clipfrac', 'kl_bc', 'grad_norm_policy', 'value_loss',
                                     'grad_norm_value', 'entropy')}
            nonfinite = 0
            N = len(A)
            for _ in range(H['update_epochs']):
                perm = torch.as_tensor(rng.permutation(N), device=dev)
                for s0 in range(0, N, H['minibatch_size']):
                    b = perm[s0:s0 + H['minibatch_size']]
                    if update_policy:
                        logits = policy(Xt[b])
                        pl, st = ppo_surrogate(logits, At[b], logp_old[b], ADVt[b], H['ppo_clip'])
                        kl = kl_to_reference(logits, ref_logits[b]).mean()
                        ent = st['entropy'].mean()
                        loss = pl - ent_coef * ent + beta * kl
                        opt_p.zero_grad(set_to_none=True)
                        loss.backward()
                        gn = torch.nn.utils.clip_grad_norm_(policy.parameters(), H['grad_clip_norm'])
                        if torch.isfinite(gn):
                            opt_p.step()
                        else:
                            nonfinite += 1
                        for k, v in (('policy_loss', pl), ('approx_kl', st['approx_kl']), ('clipfrac', st['clipfrac']),
                                     ('kl_bc', kl), ('grad_norm_policy', gn), ('entropy', ent)):
                            stats[k].append(v.detach())
                    vl = H['value_coef'] * value_loss(critic(Xt[b]), RETt[b])
                    opt_v.zero_grad(set_to_none=True)
                    vl.backward()
                    gv = torch.nn.utils.clip_grad_norm_(critic.parameters(), H['grad_clip_norm'])
                    if torch.isfinite(gv):
                        opt_v.step()
                    else:
                        nonfinite += 1
                    stats['value_loss'].append(vl.detach())
                    stats['grad_norm_value'].append(gv.detach())
            torch.cuda.synchronize()
            t_gpu = time.time() - t2
            with torch.no_grad():
                P_new = torch.softmax(policy(Xt), -1)
                kl_roll = float(kl_to_reference(policy(Xt), ref_logits).mean())
                V_new = critic(Xt).double().cpu().numpy()
            smean = {k: (float(torch.stack(v).mean()) if v else None) for k, v in stats.items()}
            np_model = policy.to_numpy_model()
            resp = BCT.escape_response(np_model)
            cond = conditional_escape(eps, P_new.double().cpu().numpy())
            thr_esc = float(np.mean([bool(e['escape'].any()) for e in thr]))
            cond_ok = (resp['escape_prob_strong_left'] >= 0.2 and resp['escape_prob_strong_left'] >= 10 * resp['escape_prob_quiet']
                       and thr_esc >= 0.5)
            stable_run = stable_run + 1 if cond_ok else 0
            dual_updated = False
            if dual_active_since is None and it >= D['min_warmup_iterations'] and stable_run >= D['stable_iterations_required']:
                dual_active_since = it
            if dual_active_since is not None and cond_ok:
                tu, tp = D['unnecessary_target_per_min'], D['perch_target_per_min']
                lam_u = float(np.clip(lam_u + D['step'] * (ema_u - tu) / tu, 0, D['lambda_u_max']))
                lam_p = float(np.clip(lam_p + D['step'] * (tp - ema_p) / tp, 0, D['lambda_p_max']))
                dual_updated = True
            ent_coef = float(np.clip(ent_coef * np.exp(E['gain'] * (ent_target - H_now) / ent_target), E['coef_min'], E['coef_max']))
            steps += N
            counts = np.bincount(A, minlength=N_MANEUVERS)
            ev_old = 1 - np.var(RET - V) / (np.var(RET) + 1e-12)
            ev_new = 1 - np.var(RET - V_new) / (np.var(RET) + 1e-12)
            wall = time.time() - t0
            row = {'iteration': it, 'env_steps': steps, 'decisions': N, 'seconds': wall,
                   'timing': {'rollout_s': t_roll, 'prep_cpu_s': t_prep, 'gpu_update_s': t_gpu,
                              'samples_per_s_rollout': N / t_roll, 'samples_per_s_total': N / wall},
                   'threat_trials': len(thr), 'hit_rate': float(np.mean([e['hit'] for e in thr])),
                   'threat_trial_any_escape': thr_esc, 'background_minutes': bg_min, 'unnecessary_per_min': U,
                   'perch_per_min': Pr, 'ema_unnecessary': ema_u, 'ema_perch': ema_p, 'lambda_u': lam_u, 'lambda_p': lam_p,
                   'dual_active_since': dual_active_since, 'dual_updated': dual_updated, 'conditional_escape_ok': cond_ok,
                   'beta_kl': beta, 'kl_policy_bc_rollout': kl_roll, 'entropy_rollout_before_update': H_now,
                   'entropy_target': ent_target, 'entropy_coef_next': ent_coef,
                   'action_distribution_sampled': (counts / counts.sum()).round(5).tolist(),
                   'none_share': float(counts[NONE] / counts.sum()),
                   'escape_action_share': float(np.isin(A, ESCAPES).mean()),
                   'escape_executed_fraction': float(np.mean(np.concatenate([e['escape'] for e in eps]))),
                   'turn_fraction': float(np.mean(np.concatenate([e['turn'] for e in eps]))),
                   'wall_fraction': float(np.mean(np.concatenate([e['wall'] for e in eps]))),
                   'max_speed_fraction': float(np.mean(np.concatenate([e['maxspd'] for e in eps]))),
                   'policy_update': update_policy, **{k: smean[k] for k in smean},
                   'nonfinite_gradient_steps': nonfinite, 'explained_variance_before': float(ev_old),
                   'explained_variance_after': float(ev_new), 'escape_response': resp, 'conditional_escape': cond,
                   'credit': credit, 'gpu_peak_memory_mib': torch.cuda.max_memory_allocated() / 2 ** 20}
            log.write(json.dumps(row, default=float) + '\n')
            log.flush()
            print('seed %d it %2d hit %.2f anyesc %.2f U %.1f P %.2f lam_u %.3f lam_p %.3f beta %.2f KLbc %.5f H %.4f/%.4f '
                  'c %.4f NONE %.4f esc@L3 %.2f win %.3f bg %.4f EV %.2f roll %.0fs gpu %.2fs' % (
                      train_seed, it, row['hit_rate'], thr_esc, U, Pr, lam_u, lam_p, beta, kl_roll, H_now, ent_target,
                      ent_coef, row['none_share'], resp['escape_prob_strong_left'], cond['threat_window'], cond['background'],
                      ev_new, t_roll, t_gpu), flush=True)
            if proto is not None and (it % H['checkpoint_every'] == 0 or it == iterations):
                path = out / ('ckpt_it%03d.pt' % it)
                meta = {'training_seed': train_seed, 'iteration': it, 'env_steps': steps, 'code_commit': head,
                        'protocol_sha256': proto_sha, 'bc_parent_sha256': bc_meta['checkpoint_state_dict_sha256'],
                        'observation_schema_sha256': proto['observation_schema_sha256'],
                        'action_schema_sha256': proto['action_schema_sha256'], 'reward_v2_sha256': proto['reward_v2_sha256'],
                        'constraints_sha256': proto['constraints_sha256'], 'lambda_u': lam_u, 'lambda_p': lam_p,
                        'beta_kl': beta, 'entropy_coef': ent_coef, 'torch': torch.__version__, 'cuda': torch.version.cuda}
                meta['checkpoint_sha256'] = save_checkpoint(path, policy, meta)
                save_checkpoint(out / ('critic_it%03d.pt' % it), critic)
                (out / ('ckpt_it%03d.json' % it)).write_text(json.dumps(meta, indent=1) + '\n', encoding='utf-8')
    log.close()


def ppo_smoke(seed, variant, iters):
    H = deep_update(PPO, SMOKE_VARIANTS[variant])
    out = OUT / 'smoke' / ('%s_seed_%d' % (variant, seed))
    if out.exists():
        import shutil
        shutil.rmtree(out)
    ppo_train(seed, H, out, iterations=iters)


def summarize_log(rows):
    def col(k, f=lambda r, k: r.get(k)):
        return [f(r, k) for r in rows]
    last5 = rows[-5:]
    return {
        'iterations': len(rows),
        'hit_rate_first5_mean': float(np.mean([r['hit_rate'] for r in rows[:5]])),
        'hit_rate_last5_mean': float(np.mean([r['hit_rate'] for r in last5])),
        'none_share': col('none_share'),
        'entropy': col('entropy_rollout_before_update') if 'entropy_rollout_before_update' in rows[0] else col('entropy'),
        'entropy_coef': col('entropy_coef_next') if 'entropy_coef_next' in rows[0] else col('entropy_coef'),
        'kl_policy_bc': col('kl_policy_bc_rollout'), 'lambda_u': col('lambda_u'), 'lambda_p': col('lambda_p'),
        'unnecessary_per_min': col('unnecessary_per_min'), 'perch_per_min': col('perch_per_min'),
        'escape_prob_strong_left': [r['escape_response']['escape_prob_strong_left'] for r in rows],
        'escape_prob_quiet': [r['escape_response']['escape_prob_quiet'] for r in rows],
        'conditional_escape': [r.get('conditional_escape') for r in rows],
        'dual_active_since': rows[-1].get('dual_active_since'),
        'nonfinite_gradient_steps': int(sum(r.get('nonfinite_gradient_steps', 0) for r in rows)),
        'explained_variance': col('explained_variance_after') if 'explained_variance_after' in rows[0] else col('explained_variance'),
        'timing_mean': None if 'timing' not in rows[0] else {k: float(np.mean([r['timing'][k] for r in rows]))
                                                              for k in rows[0]['timing']},
        'credit_last': rows[-1].get('credit'),
        'credit_mean': None if 'credit' not in rows[0] else {
            k: float(np.mean([r['credit'][k] for r in rows])) for k in
            ('decisions_per_committed_strike', 'threat_decisions_per_committed_strike', 'frac_abs_adv_raw_ge_0.05',
             'frac_abs_adv_raw_ge_0.2', 'frac_abs_adv_norm_ge_1')},
    }


def smoke_summary():
    out = {'label': 'M2.3 TRAIN-only development smokes (not official seeds; EVAL never touched)',
           'environment': env_info(), 'variants': SMOKE_VARIANTS, 'runs': {}}
    npz = DATA / 'smoke_seed_101' / 'log.jsonl'
    if npz.exists():
        out['runs']['numpy_draft_seed_101 (handwritten gradients; diagnostic only)'] = summarize_log(
            [json.loads(line) for line in npz.open(encoding='utf-8')])
    for d in sorted((OUT / 'smoke').glob('*_seed_*')):
        f = d / 'log.jsonl'
        if f.exists():
            out['runs']['torch_' + d.name] = summarize_log([json.loads(line) for line in f.open(encoding='utf-8')])
    (TRACK / 'torch_smoke_summary.json').write_text(json.dumps(out, indent=1, default=float) + '\n', encoding='utf-8')
    for k, v in out['runs'].items():
        print(k, v['iterations'], 'hit %.3f -> %.3f' % (v['hit_rate_first5_mean'], v['hit_rate_last5_mean']),
              'esc@L3 %.3f -> %.3f' % (v['escape_prob_strong_left'][0], v['escape_prob_strong_left'][-1]),
              'KL %.5f' % v['kl_policy_bc'][-1], 'lam_u %.3f' % v['lambda_u'][-1], 'NONE %.4f' % v['none_share'][-1])


def freeze():
    if PROTOCOL_FILE.exists():
        raise SystemExit('already frozen')
    gate = json.loads(BC_GATE_FILE.read_text(encoding='utf-8'))
    if not gate['pass']:
        raise SystemExit('the PyTorch BC gate did not pass; PPO must not proceed')
    bcm = json.loads(BC_METRICS.read_text(encoding='utf-8'))
    p22 = json.loads((ROOT / 'game/learning/m2_2_protocol.json').read_text(encoding='utf-8'))
    smoke = TRACK / 'torch_smoke_summary.json'
    proto = {'label': 'M2.3 frozen PyTorch PPO protocol (KL-anchored constrained PPO from the PyTorch BC policy)',
             'frozen_utc': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()), 'environment': env_info(),
             'ppo': PPO, 'bc_torch_config': BC_TORCH, 'bc_config': BCT.BC_CONFIG,
             'bc_checkpoint_state_dict_sha256': bcm['checkpoint_state_dict_sha256'],
             'bc_checkpoint_file_sha256': sha_file(BC_CKPT),
             'bc_dataset_manifest_sha256': sha_file(TRACK / 'bc_dataset_manifest.json'),
             'bc_gate_sha256': sha_file(BC_GATE_FILE),
             'development_smoke_summary_sha256': sha_file(smoke) if smoke.exists() else None,
             'rollout_inference': 'per-tick numpy forward on the CPU rollout workers with parameters exported from the '
                                  'torch policy (measured 23.5 us / decision vs 85 us torch-CPU and 642 us torch-CUDA); '
                                  'MaleCNS and the game simulation stay on CPU; the PPO update runs on CUDA',
             'architecture': 'TorchPolicy 60 -> 32 tanh -> 11 (2,315 trainable parameters) + training-only TorchCritic '
                             '60 -> 32 tanh -> 1 (1,985); stochastic seeded sampling at deployment',
             'split': p22['split'], 'split_sha256': p22['split_sha256'],
             'reward_v2_sha256': p22['reward_v2_sha256'], 'constraints_sha256': p22['constraints_sha256'],
             'observation_schema_sha256': p22['observation_schema_sha256'],
             'action_schema_sha256': p22['action_schema_sha256'],
             'max_environment_steps': '%d iterations x about 33,000 decisions (7 units x (%d background + %d threat)); '
                                      'exact counts logged' % (PPO['iterations'], PPO['mixture']['background_per_unit'],
                                                               PPO['mixture']['threat_per_unit']),
             'checkpoint_cadence': 'every %d iterations' % PPO['checkpoint_every'],
             'eligibility': ELIGIBILITY, 'selection': SELECTION, 'eval': 'frozen M2.1 v2 EVAL set, exactly once, for the '
                                                                           'single selected checkpoint'}
    PROTOCOL_FILE.write_text(json.dumps(proto, indent=1) + '\n', encoding='utf-8')
    print('frozen', sha_file(PROTOCOL_FILE))


ELIGIBILITY = ('TRAIN-VAL: M2.1 admissible (unnecessary <= 5.36 / min, perches >= 0.275 / min, movement constraints, '
               'no hard anti-cheat flag) AND threat-window escape fraction >= 0.3 AND not no_escape-equivalent: '
               'synthetic strong one-sided DNp01 escape probability >= 0.2 and >= 10 x quiet, NONE share of TRAIN-VAL '
               'background decisions < 0.995 AND measurable neural conditioning on the TRAIN-VAL BC-dataset states: mean '
               'escape probability at max DNp01 >= 2 is >= 10 x that at max DNp01 < 0.25')
SELECTION = ('among eligible checkpoints (TRAIN-VAL only): lowest hit probability; then lower unnecessary escapes / min; '
             'then smaller mean KL(policy || BC) on the TRAIN-VAL BC-dataset states. Scalar reward is not used.')


def kl_to_bc(net, bc_net, X):
    with torch.no_grad():
        Xt = torch.as_tensor(X)
        return float(kl_to_reference(net(Xt), bc_net(Xt)).mean())


def neural_conditioning(net, va):
    P = probs_torch(net, va['obs'], torch.device('cpu'))
    bins = dnp01_bins(P, va['obs'])
    lo, hi = bins[0]['mean_escape_prob'], bins[3]['mean_escape_prob']
    return {'by_dnp01': bins, 'low': lo, 'high': hi, 'ratio': hi / max(lo, 1e-12), 'ok': hi >= 10 * lo}


def validate():
    ppo_protocol()
    base = json.loads((ROOT / 'artifacts/m2_2/val/baselines.json').read_text(encoding='utf-8'))
    path = OUT / 'val' / 'checkpoints.json'
    path.parent.mkdir(parents=True, exist_ok=True)
    results = json.loads(path.read_text(encoding='utf-8')) if path.exists() else {}
    bc_net, _ = load_bc()
    _, va, _ = load_dataset()
    specs = M22.val_specs()
    with mp.get_context('spawn').Pool(WORKERS, initializer=training.worker_init) as pool:
        for c in sorted((OUT / 'runs').glob('seed_*/ckpt_it*.pt')):
            key = '%s/%s' % (c.parent.name, c.stem)
            if key in results:
                continue
            meta = json.loads(c.with_suffix('.json').read_text(encoding='utf-8'))
            net, _ = load_checkpoint(c, TorchPolicy, expected_sha256=meta['checkpoint_sha256'])
            model = net.to_numpy_model()
            recs = [r for ch in pool.map(training.eval_task, [(model.params, cc, 'TRAIN') for cc in M22.chunks(specs, WORKERS)])
                    for r in ch]
            ev = M22.evaluate_records(recs, base)['candidate']
            resp = BCT.escape_response(model)
            cats = ev['background']['category_counts']
            none_share = cats.get('NONE', 0) / max(1, sum(cats.values()))
            nc = neural_conditioning(net, va)
            collapse_ok = (resp['escape_prob_strong_left'] >= 0.2 and resp['escape_prob_strong_left'] >= 10 * resp['escape_prob_quiet']
                           and none_share < 0.995)
            eligible = bool(ev['admissible'] and ev['threat']['escape_in_window_fraction'] >= 0.3 and collapse_ok and nc['ok'])
            results[key] = {'meta': meta, 'summary': BCT.summarize(ev), 'escape_response': resp,
                            'none_share_background': none_share, 'no_escape_collapse_diagnostic_ok': collapse_ok,
                            'neural_conditioning': nc, 'eligible': eligible,
                            'kl_to_bc_val_states': kl_to_bc(net, bc_net, va['obs']),
                            'threat_by_family': {f: x['hit_probability'] for f, x in ev['threat_by_family'].items()}}
            path.write_text(json.dumps(results, indent=1, default=float) + '\n', encoding='utf-8')
            s = results[key]['summary']
            print('val %s hit %.3f win %.2f unnec %.2f perch %.2f adm %s collapse_ok %s cond %.3f/%.4f eligible %s KLbc %.4f' % (
                key, s['hit_probability'], s['escape_in_window'], s['unnecessary_per_min'], s['perches_per_min'] or 0.0,
                s['admissible'], collapse_ok, nc['high'], nc['low'], eligible, results[key]['kl_to_bc_val_states']), flush=True)


def select():
    proto, proto_sha = ppo_protocol()
    if CANDIDATE_FILE.exists():
        raise SystemExit('candidate already frozen')
    res = json.loads((OUT / 'val' / 'checkpoints.json').read_text(encoding='utf-8'))
    el = {k: v for k, v in res.items() if v['eligible']}
    rec = {'label': 'M2.3 frozen PyTorch learned candidate', 'selected_utc': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
           'selection_rule': SELECTION, 'eligibility_rule': ELIGIBILITY, 'protocol_sha256': proto_sha,
           'n_checkpoints': len(res), 'n_eligible': len(el), 'eligible': sorted(el)}
    if not el:
        rec['candidate'] = None
        CANDIDATE_FILE.write_text(json.dumps(rec, indent=1) + '\n', encoding='utf-8')
        print('NO ELIGIBLE CHECKPOINT')
        return
    best = min(el, key=lambda k: (el[k]['summary']['hit_probability'], el[k]['summary']['unnecessary_per_min'],
                                  el[k]['kl_to_bc_val_states']))
    src = OUT / 'runs' / best.split('/')[0] / (best.split('/')[1] + '.pt')
    net, meta = load_checkpoint(src, TorchPolicy, expected_sha256=res[best]['meta']['checkpoint_sha256'])
    h = save_checkpoint(CANDIDATE_CKPT, net, meta)
    npz_sha = net.to_numpy_model().save(CANDIDATE_NPZ)
    rec.update({'candidate': best, 'checkpoint_sha256': h, 'checkpoint_file_sha256': sha_file(CANDIDATE_CKPT),
                'numpy_export': str(CANDIDATE_NPZ.relative_to(ROOT)).replace('\\', '/'), 'numpy_export_param_sha256': npz_sha,
                'bc_parent_sha256': proto['bc_checkpoint_state_dict_sha256'], 'training_seed': meta['training_seed'],
                'iteration': meta['iteration'], 'env_steps': meta['env_steps'], 'torch': meta['torch'], 'cuda': meta['cuda'],
                'reward_v2_sha256': proto['reward_v2_sha256'], 'constraints_sha256': proto['constraints_sha256'],
                'observation_schema_sha256': proto['observation_schema_sha256'],
                'action_schema_sha256': proto['action_schema_sha256'], 'selection_evidence': res[best]})
    CANDIDATE_FILE.write_text(json.dumps(rec, indent=1, default=float) + '\n', encoding='utf-8')
    print('selected', best, h)


def compare():
    base = json.loads((ROOT / 'artifacts/m2_2/val/baselines.json').read_text(encoding='utf-8'))
    rows = {}
    for name in ('baseline_n4b1c', 'no_escape', 'fixed_maneuver'):
        rows[name] = BCT.summarize(M22.evaluate_records(base[name], base)['candidate'])
    rows['teacher_mapped'] = BCT.summarize(M22.evaluate_records(
        json.loads((DATA / 'val' / 'teacher_mapped.json').read_text(encoding='utf-8')), base)['candidate'])
    rows['numpy_bc_dev_only'] = BCT.summarize(M22.evaluate_records(
        json.loads((DATA / 'val' / 'bc_policy.json').read_text(encoding='utf-8')), base)['candidate'])
    rows['torch_bc'] = BCT.summarize(M22.evaluate_records(
        json.loads((OUT / 'val' / 'bc_policy.json').read_text(encoding='utf-8')), base)['candidate'])
    c22 = json.loads((ROOT / 'game/learning/m2_2_candidate.json').read_text(encoding='utf-8'))
    v22 = json.loads((ROOT / 'artifacts/m2_2/val/checkpoints.json').read_text(encoding='utf-8'))[c22['candidate']]
    rows['m2_2_candidate'] = {'hit_probability': v22['hit_probability'], 'unnecessary_per_min': v22['unnecessary_per_min'],
                              'escape_in_window': v22['threat'].get('escape_in_window_fraction'),
                              'perches_per_min': v22['background'].get('perches_per_min'), 'admissible': v22['admissible']}
    res = json.loads((OUT / 'val' / 'checkpoints.json').read_text(encoding='utf-8'))
    for k, v in res.items():
        rows['m2_3/' + k] = dict(v['summary'], eligible=v['eligible'], kl_to_bc=v['kl_to_bc_val_states'],
                                 cond_high=v['neural_conditioning']['high'], cond_low=v['neural_conditioning']['low'])
    (OUT / 'val' / 'comparison.json').write_text(json.dumps(rows, indent=1, default=float) + '\n', encoding='utf-8')
    (TRACK / 'torch_val_comparison.json').write_text(json.dumps(rows, indent=1, default=float) + '\n', encoding='utf-8')
    for k, v in rows.items():
        print('%-28s hit %.3f win %s unnec %.2f perch %s adm %s %s' % (
            k, v['hit_probability'], None if v.get('escape_in_window') is None else round(v['escape_in_window'], 2),
            v['unnecessary_per_min'], None if v.get('perches_per_min') is None else round(v['perches_per_min'], 2),
            v['admissible'], '' if 'eligible' not in v else 'eligible=%s KL=%.4f' % (v['eligible'], v['kl_to_bc'])))


def eval_final():
    ppo_protocol()
    cand = json.loads(CANDIDATE_FILE.read_text(encoding='utf-8'))
    if cand['candidate'] is None:
        raise SystemExit('no candidate')
    done = OUT / 'eval' / 'records.json'
    if done.exists():
        raise SystemExit('the one-shot EVAL has already been run')
    net, _ = load_checkpoint(CANDIDATE_CKPT, TorchPolicy, expected_sha256=cand['checkpoint_sha256'])
    model = net.to_numpy_model()
    sd = M22.m21().seeds('eval')
    specs = [(g.split(':')[0], g.split(':')[1], g.split(':')[2] if g.startswith('threat') else None, s)
             for g, lst in sd.items() for s in lst]
    (OUT / 'eval').mkdir(parents=True, exist_ok=True)
    with mp.get_context('spawn').Pool(WORKERS, initializer=training.worker_init) as pool:
        recs = [r for ch in pool.map(training.eval_task, [(model.params, cc, 'EVAL') for cc in M22.chunks(specs, WORKERS)])
                for r in ch]
    done.write_text(json.dumps(recs, default=float) + '\n', encoding='utf-8')
    base = {}
    for f in sorted((ROOT / 'artifacts/m2_1/eval').glob('part_*.jsonl')):
        for line in f.open(encoding='utf-8'):
            r = json.loads(line)
            base.setdefault(r['policy'], []).append(r)
    ev = M22.evaluate_records(recs, base)
    rep = {'candidate': cand['candidate'], 'checkpoint_sha256': cand['checkpoint_sha256'], 'code_commit': M22.git_head(),
           'protocol_sha256': cand['protocol_sha256'], 'environment': env_info(), 'evaluation': ev,
           'candidate_summary': BCT.summarize(ev['candidate']), 'candidate_escape_response': BCT.escape_response(model)}
    (OUT / 'eval' / 'report.json').write_text(json.dumps(rep, indent=1, default=float) + '\n', encoding='utf-8')
    (TRACK / 'torch_eval_report.json').write_text(json.dumps(
        {k: rep[k] for k in ('candidate', 'checkpoint_sha256', 'code_commit', 'protocol_sha256', 'environment',
                             'candidate_summary', 'candidate_escape_response')} |
        {'policies': {p: BCT.summarize(v) for p, v in ev.items()}}, indent=1, default=float) + '\n', encoding='utf-8')
    for p, v in ev.items():
        print('%-20s hit %.3f %s win %.2f unnec %.2f perch %.2f adm %s flags %s' % (
            p, v['threat']['hit_probability'], {a: round(x['hit_probability'], 3) for a, x in v['threat_by_attacker'].items()},
            v['threat']['escape_in_window_fraction'] or 0.0, v['background_unnecessary_per_min'],
            v['background']['perches_per_min'] or 0.0, v['admissible'], [k for k, f in v['anti_cheat_flags'].items() if f]))


def train(seed):
    proto, proto_sha = ppo_protocol()
    if seed not in proto['ppo']['training_seeds']:
        raise SystemExit('not a preregistered training seed')
    out = OUT / 'runs' / ('seed_%d' % seed)
    if (out / 'log.jsonl').exists():
        raise SystemExit('run already exists; official runs are never restarted silently')
    ppo_train(seed, proto['ppo'], out, proto=proto, proto_sha=proto_sha)


if __name__ == '__main__':
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('mode')
    ap.add_argument('--seed', type=int)
    ap.add_argument('--variant', default='draft')
    ap.add_argument('--iters', type=int, default=25)
    a = ap.parse_args()
    {'env': lambda: print(json.dumps(env_info(), indent=1)), 'bc-train': bc_train, 'bc-gate': bc_gate,
     'ppo-smoke': lambda: ppo_smoke(a.seed, a.variant, a.iters), 'freeze': freeze, 'train': lambda: train(a.seed),
     'smoke-summary': smoke_summary, 'validate': validate, 'select': select, 'compare': compare,
     'eval-final': eval_final}[a.mode]()
