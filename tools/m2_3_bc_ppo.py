"""M2.3 behaviour-cloned warm start + constrained PPO (training method only).

Phase A/B (behaviour cloning):
    python tools/m2_3_bc_ppo.py teacher-data          (TRAIN-OPT teacher dataset + TRAIN-VAL BC-validation set)
    python tools/m2_3_bc_ppo.py teacher-val           (mapped teacher on the TRAIN-VAL benchmark)
    python tools/m2_3_bc_ppo.py bc-train              (supervised cross-entropy; checkpoint by TRAIN-VAL loss)
    python tools/m2_3_bc_ppo.py bc-gate               (BC policy on the TRAIN-VAL benchmark; frozen gate)
Phase C (only if the BC gate passes):
    python tools/m2_3_bc_ppo.py ppo-smoke --seed K    (TRAIN-only development runs, before the freeze)
    python tools/m2_3_bc_ppo.py freeze
    python tools/m2_3_bc_ppo.py train --seed K
    python tools/m2_3_bc_ppo.py validate | select | compare | eval-final | report

Artifacts: artifacts/m2_3/ (git-ignored). Manifests, protocol, candidate record and the small
BC / candidate checkpoints are tracked.
"""
from __future__ import annotations

import argparse
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

from game.learning import bc, contracts, trials, training  # noqa: E402
from game.learning.contracts import MANEUVERS, N_MANEUVERS  # noqa: E402
from game.learning.model import MLPPolicyModel  # noqa: E402
from game.learning.ppo import Adam, clip_grads, cross_entropy_loss_and_grads  # noqa: E402

OUT = ROOT / 'artifacts/m2_3'
TRACK = ROOT / 'game/learning/m2_3'
WORKERS = 7
NONE = [m.name for m in MANEUVERS].index('NONE')
ESCAPES = [i for i, m in enumerate(MANEUVERS) if m.escape]


def m22():
    import importlib.util
    spec = importlib.util.spec_from_file_location('m2_2_train', ROOT / 'tools/m2_2_train.py')
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


M22 = m22()

# ----------------------------------------------------------------- BC configuration (fixed before BC training) ---
BC_CONFIG = {
    'dataset_train': 'TRAIN-OPT seeds: 12 threat groups (4 families x 3 attackers) x 50 trials + 4 background '
                     'families x 30 episodes; seeds drawn by numpy default_rng(2300 + group) from [20e6, 25e6) '
                     'excluding the M2.1 development seeds',
    'dataset_val': 'the M2.2 TRAIN-VAL specification (96 threat trials, 24 background episodes)',
    'teacher': 'accepted N4B1C FixedEscapePolicy mapped to the 11 maneuvers (game/learning/teacher.py); the mapped '
               'maneuver is executed',
    'none_keep_fraction': 0.05, 'none_subsample_seed': 2301,
    'prior_correction': 'log(1 / none_keep_fraction) added to the NONE logit (training loss uses it, so the '
                        'learned logits stay calibrated to the natural distribution)',
    'init_seed': 2303, 'optimizer': 'Adam (0.9, 0.999, 1e-8)', 'learning_rate': 1e-3, 'batch_size': 1024,
    'epochs': 40, 'shuffle_seed': 2304, 'grad_clip_norm': 1.0,
    'checkpoint_selection': 'epoch with the lowest cross-entropy on the natural-distribution TRAIN-VAL BC set',
}
BC_GATE = {
    'hit_probability_max': 'TRAIN-VAL N4B1C hit probability + 0.05',
    'unnecessary_escapes_per_min_max': 5.36, 'perches_per_min_min': 0.275, 'admissible': True,
    'threat_window_escape_min': '0.5 x the mapped teacher\'s TRAIN-VAL escape-in-window fraction',
    'no_collapse': 'escape probability at a strong one-sided DNp01 frame (L = 3, R = 0) >= 0.2 and >= 10 x the '
                   'escape probability at a quiet frame (L = R = 0)',
}


def dev_seeds():
    return M22.dev_seeds()


def teacher_specs():
    dev = dev_seeds()
    groups = [('threat', f.name, a, 50) for f in trials.THREAT_FAMILIES for a in trials.ATTACKERS] + \
             [('background', c.name, None, 30) for c in trials.BACKGROUND_FAMILIES]
    specs = []
    for g_i, (kind, name, level, n) in enumerate(groups):
        rng = np.random.default_rng(2300 + g_i)
        got = 0
        while got < n:
            s = int(rng.integers(20_000_000, 25_000_000))
            if s not in dev:
                specs.append((kind, name, level, s))
                got += 1
    return specs


def sha_arrays(d):
    h = hashlib.sha256()
    for k in sorted(d):
        h.update(k.encode())
        h.update(np.ascontiguousarray(d[k]).tobytes())
    return h.hexdigest()


def teacher_data():
    OUT.mkdir(parents=True, exist_ok=True)
    val_specs = M22.val_specs()
    tr_specs = teacher_specs()
    eval_seeds = {s for v in M22.m21().seeds('eval').values() for s in v}
    assert not ({s for *_, s in tr_specs} & eval_seeds) and not ({s for *_, s in val_specs} & eval_seeds)
    with mp.get_context('spawn').Pool(WORKERS, initializer=bc.teacher_worker_init) as pool:
        for name, specs in (('train', tr_specs), ('val', val_specs)):
            parts = pool.map(bc.teacher_data_task, [(c, 'TRAIN') for c in M22.chunks(specs, WORKERS)])
            d = {k: np.concatenate([p[k] for p in parts]) for k in parts[0]}
            np.savez_compressed(OUT / ('bc_%s.npz' % name), **d)
            cnt = bc.class_counts(d['label'])
            print(name, len(d['label']), 'samples; class counts', cnt.tolist(), flush=True)
    manifest = {'label': 'M2.3 behaviour-cloning dataset manifest', 'config': BC_CONFIG,
                'mapping_rule': __import__('game.learning.teacher', fromlist=['MAPPING_RULE']).MAPPING_RULE}
    for name in ('train', 'val'):
        z = dict(np.load(OUT / ('bc_%s.npz' % name)))
        cnt = bc.class_counts(z['label'])
        win = z['ctx_threat_window']
        manifest[name] = {'samples': int(len(z['label'])), 'sha256': sha_arrays(z),
                          'class_counts': dict(zip([m.name for m in MANEUVERS], cnt.tolist())),
                          'threat_window_samples': int(win.sum()),
                          'threat_window_class_counts': bc.class_counts(z['label'][win]).tolist(),
                          'background_class_counts': bc.class_counts(z['label'][z['ctx_kind'] == 0]).tolist(),
                          'episodes': int(len(np.unique(z['ctx_seed']))),
                          'seed_range': [int(z['ctx_seed'].min()), int(z['ctx_seed'].max())]}
    TRACK.mkdir(parents=True, exist_ok=True)
    (TRACK / 'bc_dataset_manifest.json').write_text(json.dumps(manifest, indent=1) + '\n', encoding='utf-8')
    print(json.dumps({k: v for k, v in manifest.items() if k in ('train', 'val')}, indent=1))


def teacher_val():
    specs = M22.val_specs()
    with mp.get_context('spawn').Pool(WORKERS, initializer=bc.teacher_worker_init) as pool:
        recs = [r for c in pool.map(bc.teacher_eval_task, [(ch, 'TRAIN') for ch in M22.chunks(specs, WORKERS)]) for r in c]
    (OUT / 'val').mkdir(parents=True, exist_ok=True)
    (OUT / 'val' / 'teacher_mapped.json').write_text(json.dumps(recs, default=float) + '\n', encoding='utf-8')
    base = json.loads((ROOT / 'artifacts/m2_2/val/baselines.json').read_text(encoding='utf-8'))
    ev = M22.evaluate_records(recs, base)['candidate']
    print('teacher_mapped VAL hit %.3f esc_in_win %.2f unnec %.2f perch %.2f admissible %s flags %s' % (
        ev['threat']['hit_probability'], ev['threat']['escape_in_window_fraction'], ev['background_unnecessary_per_min'],
        ev['background']['perches_per_min'] or 0.0, ev['admissible'], [k for k, f in ev['anti_cheat_flags'].items() if f]))


# ----------------------------------------------------------------- BC training ---
def bc_train():
    C = BC_CONFIG
    tr = dict(np.load(OUT / 'bc_train.npz'))
    va = dict(np.load(OUT / 'bc_val.npz'))
    rng = np.random.default_rng(C['none_subsample_seed'])
    keep = (tr['label'] != NONE) | (rng.random(len(tr['label'])) < C['none_keep_fraction'])
    X, y = tr['obs'][keep].astype(np.float64), tr['label'][keep].astype(int)
    Xv, yv = va['obs'].astype(np.float64), va['label'].astype(int)
    off = np.zeros(N_MANEUVERS)
    off[NONE] = np.log(C['none_keep_fraction'])          # training distribution: NONE thinned by f
    model = MLPPolicyModel(seed=C['init_seed'])
    opt = Adam(model.params, C['learning_rate'])
    sh = np.random.default_rng(C['shuffle_seed'])
    log, best = [], None
    for ep in range(1, C['epochs'] + 1):
        idx = sh.permutation(len(y))
        losses = []
        for s0 in range(0, len(idx), C['batch_size']):
            b = idx[s0:s0 + C['batch_size']]
            loss, g, _ = cross_entropy_loss_and_grads(model, X[b], y[b], off)
            g, _ = clip_grads(g, C['grad_clip_norm'])
            model.apply_update(opt.step(model.params, g))
            losses.append(loss)
        vloss, _, Pv = cross_entropy_loss_and_grads(model, Xv, yv)      # natural distribution, no offset
        row = {'epoch': ep, 'train_loss_subsampled': float(np.mean(losses)), 'val_loss': vloss,
               'val_accuracy': float(np.mean(Pv.argmax(1) == yv))}
        log.append(row)
        print(row, flush=True)
        if best is None or vloss < best[0]:
            best = (vloss, ep, {k: v.copy() for k, v in model.params.items()})
    model.params = best[2]
    TRACK.mkdir(parents=True, exist_ok=True)
    h = model.save(TRACK / 'bc_checkpoint.npz')
    _, _, Pv = cross_entropy_loss_and_grads(model, Xv, yv)
    _, _, Pt = cross_entropy_loss_and_grads(model, tr['obs'].astype(np.float64), tr['label'].astype(int))
    metrics = {'config': C, 'selected_epoch': best[1], 'val_loss': best[0], 'checkpoint_sha256': h,
               'checkpoint_file_sha256': hashlib.sha256((TRACK / 'bc_checkpoint.npz').read_bytes()).hexdigest(),
               'log': log, 'val': supervised_metrics(Pv, yv, va), 'train': supervised_metrics(Pt, tr['label'].astype(int), tr)}
    (TRACK / 'bc_metrics.json').write_text(json.dumps(metrics, indent=1, default=float) + '\n', encoding='utf-8')
    print('BC checkpoint epoch %d val loss %.4f sha %s' % (best[1], best[0], h))


def supervised_metrics(P, y, d):
    pred = P.argmax(1)
    names = [m.name for m in MANEUVERS]
    conf = np.zeros((N_MANEUVERS, N_MANEUVERS), int)
    np.add.at(conf, (y, pred), 1)
    per = {}
    for i, n in enumerate(names):
        tp = conf[i, i]
        per[n] = {'support': int(conf[i].sum()), 'precision': float(tp / conf[:, i].sum()) if conf[:, i].sum() else None,
                  'recall': float(tp / conf[i].sum()) if conf[i].sum() else None}
    esc_true = np.isin(y, ESCAPES)
    esc_prob = P[:, ESCAPES].sum(1)
    win = d['ctx_threat_window']
    bg = d['ctx_kind'] == 0

    def dist(mask):
        return {'teacher': (np.bincount(y[mask], minlength=N_MANEUVERS) / max(1, mask.sum())).round(5).tolist(),
                'learner_expected': P[mask].mean(0).round(5).tolist()}
    return {'accuracy': float(np.mean(pred == y)), 'per_action': per, 'confusion': conf.tolist(),
            'escape_detection': {'teacher_escape_samples': int(esc_true.sum()),
                                 'mean_escape_prob_on_teacher_escapes': float(esc_prob[esc_true].mean()) if esc_true.any() else None,
                                 'mean_escape_prob_elsewhere': float(esc_prob[~esc_true].mean())},
            'distribution_all': dist(np.ones(len(y), bool)), 'distribution_threat_window': dist(win),
            'distribution_background': dist(bg)}


def escape_response(model):
    def frame(l, r):
        f = np.array([1, l, r, 0.1, 0.1, 200.0, 0, 0, 0, 1, 0, 0], float)
        x = np.zeros(contracts.OBSERVATION_SIZE)
        for k in range(5):
            x[12 * k:12 * k + 12] = f
        return x
    quiet = float(model.probabilities(frame(0.0, 0.0))[ESCAPES].sum())
    strong = float(model.probabilities(frame(3.0, 0.0))[ESCAPES].sum())
    return {'escape_prob_quiet': quiet, 'escape_prob_strong_left': strong,
            'escape_prob_by_dnp01_left': [float(model.probabilities(frame(v, 0.0))[ESCAPES].sum()) for v in (0, 1, 2, 3, 4)]}


def eval_policy_on_val(params):
    specs = M22.val_specs()
    with mp.get_context('spawn').Pool(WORKERS, initializer=training.worker_init) as pool:
        return [r for ch in pool.map(training.eval_task, [(params, cc, 'TRAIN') for cc in M22.chunks(specs, WORKERS)]) for r in ch]


def bc_gate():
    metrics = json.loads((TRACK / 'bc_metrics.json').read_text(encoding='utf-8'))
    model = MLPPolicyModel.load(TRACK / 'bc_checkpoint.npz', expected_sha256=metrics['checkpoint_sha256'])
    recs = eval_policy_on_val(model.params)
    (OUT / 'val').mkdir(parents=True, exist_ok=True)
    (OUT / 'val' / 'bc_policy.json').write_text(json.dumps(recs, default=float) + '\n', encoding='utf-8')
    base = json.loads((ROOT / 'artifacts/m2_2/val/baselines.json').read_text(encoding='utf-8'))
    teacher = json.loads((OUT / 'val' / 'teacher_mapped.json').read_text(encoding='utf-8'))
    ev = M22.evaluate_records(recs, base)['candidate']
    evt = M22.evaluate_records(teacher, base)['candidate']
    evb = M22.evaluate_records(base['baseline_n4b1c'], base)['candidate']
    resp = escape_response(model)
    checks = {
        'hit_close_to_n4b1c': ev['threat']['hit_probability'] <= evb['threat']['hit_probability'] + 0.05,
        'unnecessary_within_budget': ev['background_unnecessary_per_min'] <= 5.36,
        'perch_participation': (ev['background']['perches_per_min'] or 0.0) >= 0.275,
        'admissible_no_flags': ev['admissible'],
        'threat_window_escape': ev['threat']['escape_in_window_fraction'] >= 0.5 * evt['threat']['escape_in_window_fraction'],
        'no_collapse': resp['escape_prob_strong_left'] >= 0.2 and resp['escape_prob_strong_left'] >= 10 * resp['escape_prob_quiet'],
    }
    gate = {'gate': BC_GATE, 'checks': checks, 'pass': all(checks.values()), 'bc_checkpoint_sha256': metrics['checkpoint_sha256'],
            'bc': summarize(ev), 'teacher_mapped': summarize(evt), 'n4b1c': summarize(evb),
            'escape_response': resp}
    (TRACK / 'bc_gate.json').write_text(json.dumps(gate, indent=1, default=float) + '\n', encoding='utf-8')
    print(json.dumps({k: gate[k] for k in ('checks', 'pass', 'escape_response')}, indent=1, default=float))
    for n in ('n4b1c', 'teacher_mapped', 'bc'):
        print(n, gate[n])


def summarize(ev):
    return {'hit_probability': ev['threat']['hit_probability'],
            'hit_by_attacker': {a: x['hit_probability'] for a, x in ev['threat_by_attacker'].items()},
            'escape_in_window': ev['threat']['escape_in_window_fraction'],
            'median_escape_latency_s': ev['threat']['median_escape_latency_s'],
            'unnecessary_per_min': ev['background_unnecessary_per_min'],
            'perches_per_min': ev['background']['perches_per_min'], 'admissible': ev['admissible'],
            'flags': [k for k, f in ev['anti_cheat_flags'].items() if f],
            'violations': [k for k, c in ev['constraints'].items() if not c['ok']],
            'category_counts': ev['background']['category_counts']}


if __name__ == '__main__':
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('mode')
    ap.add_argument('--seed', type=int)
    a = ap.parse_args()
    {'teacher-data': teacher_data, 'teacher-val': teacher_val, 'bc-train': bc_train, 'bc-gate': bc_gate}[a.mode]()
