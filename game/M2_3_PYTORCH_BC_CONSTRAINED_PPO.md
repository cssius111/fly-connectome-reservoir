# M2.3: PyTorch behaviour cloning + KL-anchored constrained PPO

Research milestone on `feature/m2-0-learning-infra` (worktree `artifacts/worktrees/m2-learning`).
Training method only: the observation / action contracts, reward v2, constraints, benchmark
v2, EVAL set and accepted runtime (N4B5R `363a1a9`) are unchanged. No runtime file was modified
and nothing was merged.

**Result: NO-GO for human testing.**

The PyTorch learner works as intended:

- BC passes its gate;
- PPO kept conditional escape in all 5 seeds;
- every constraint and hard anti-cheat gate passes on TRAIN-VAL and EVAL.

However, the one-shot EVAL does not show a meaningful improvement over N4B1C:

- candidate hit 0.592 vs N4B1C 0.617;
- paired difference -0.025, 95 % CI [-0.090, +0.040], McNemar p = 0.53.

Failure class **C**: PPO safely preserved the BC policy, but the improvement it produced is
small and not confirmed on EVAL. It is sample-limited by sparse strike credit (section 10).

## 1. Learner audit: NumPy vs PyTorch

Before this milestone the M2.3 learner was **not** PyTorch:

| Component | State at `7b28591` | Evidence |
|---|---|---|
| BC checkpoint `bc_checkpoint.npz` (sha `4cf390eb...`) | handwritten NumPy gradients | `game/learning/ppo.py::cross_entropy_loss_and_grads` + NumPy `Adam` / `clip_grads` in `tools/m2_3_bc_ppo.py bc-train` |
| PPO draft (`tools/m2_3_ppo.py`, then untracked) | handwritten NumPy gradients | `ppo_policy_loss_and_grads`, `kl_anchor_loss_and_grads`, `value_loss_and_grads`, `two_layer_grads` |
| Seed-101 20-iteration smoke | NumPy learner | `artifacts/m2_3/smoke_seed_101/` |

Actions taken (no published commit was rewritten):

- `7b28591` (NumPy BC) is kept as **development evidence only**. It cannot be the official
  parent checkpoint.
- `tools/m2_3_ppo.py` is committed with a header marking it as the NumPy development-smoke
  tool. Its freeze / train / select / eval modes are not used.
- The NumPy seed-101 smoke was allowed to finish (20 iterations) and is used for diagnosis
  only. No official protocol number is derived from it.
- The official M2.3 learner is PyTorch: `game/learning/torch_policy.py`, driven by
  `tools/m2_3_torch.py`, commit `f65c995`.

## 2. PyTorch / CUDA verification

| Item | Value |
|---|---|
| Interpreter | `D:\Projects\flybrain-lab\.venv\Scripts\python.exe`, Python 3.11.16 |
| PyTorch | 2.13.0+cu132 |
| CUDA runtime | 13.2; cuDNN 9.2.0 |
| Device | NVIDIA GeForce RTX 4060 Laptop GPU (compute 8.9, 8 GB) |
| Determinism | `torch.use_deterministic_algorithms(True, warn_only=True)`, `CUBLAS_WORKSPACE_CONFIG=:4096:8` |

Official learner components (all torch):

| Requirement | Implementation |
|---|---|
| model | `TorchPolicy(torch.nn.Module)`: 60 x fixed input scale -> Linear(60, 32) -> tanh -> Linear(32, 11); **2,315 trainable parameters** (identical to the frozen M2.0 MLP) |
| value head | separate training-only `TorchCritic` 60 -> 32 tanh -> 1 (1,985 parameters); see section 5.1 |
| BC loss | `torch.nn.functional.cross_entropy` + autograd |
| optimizer | `torch.optim.Adam` |
| policy distribution / entropy | `torch.distributions.Categorical` (`log_prob`, `entropy`) |
| KL anchor | `torch.distributions.kl_divergence(Categorical(current), Categorical(frozen BC))` |
| PPO surrogate / value loss | torch clipped surrogate; `0.5 * F.mse_loss` |
| gradient clipping | `torch.nn.utils.clip_grad_norm_` |
| checkpoints | `torch.save({'arch', 'state_dict', 'meta'})`; hash = sha256 over the sorted state_dict tensors |

GAE targets are computed in NumPy (no gradients flow through them).

Rollout inference: the CPU rollout workers keep the numpy `MLPPolicyModel` per-tick forward and
receive the torch parameters as float64 arrays before every rollout. The measured cost per
decision is:

- numpy: 23.5 us;
- torch on CPU: 85 us;
- torch on CUDA: 642 us.

Numpy export and torch forward agree to 3.7e-7 in probability on 5,000 TRAIN-VAL states.

**Tests** (`test_m2_3_torch.py`, 19 tests; the full suite has 492 tests and all pass) cover:

- deterministic forward and the logits / value shapes;
- Categorical log-prob and entropy against NumPy;
- KL to a frozen reference against NumPy;
- the PPO ratio and clipped surrogate against NumPy;
- the surrogate logit gradient against the analytic NumPy formula;
- BC loss against the NumPy reference, plus a finite-difference check;
- GAE against a hand-computed reference, including bootstrapping;
- value loss;
- an Adam step changes the parameters while the frozen reference stays unchanged and
  receives no gradient;
- gradient clipping;
- no NaN / Inf gradients at extreme logits;
- exact checkpoint save / load, and hash mismatch rejection;
- CPU loading of a CUDA-produced checkpoint;
- the frozen observation / action schema hashes;
- the torch module imports no world code.

## 3. PyTorch behaviour cloning

### 3.1 Data (reused, unchanged)

The frozen teacher dataset from `983b951` / `7b28591` is reused. Both arrays are re-hashed
against `game/learning/m2_3/bc_dataset_manifest.json` before training; there was no
recollection and no corruption.

- **TRAIN-OPT:** 522,651 samples from 720 episodes.
- **TRAIN-VAL BC set:** 85,550 samples from 120 episodes.
- NONE is 97.1 % (TRAIN-OPT) and 97.2 % (TRAIN-VAL) of the samples.
- There are 1,821 teacher escape labels in TRAIN-OPT, and no ESCAPE_BACKWARD label.
- The teacher mapping, observation encoding, split and BC gate are unchanged.

### 3.2 Configuration

The BC configuration is identical to the frozen `BC_CONFIG`:

- NONE kept at 5 % (subsampling seed 2301) with the log(0.05) prior correction, giving
  40,511 training samples;
- Adam (lr 1e-3, betas 0.9 / 0.999, eps 1e-8), batch 1,024, 40 epochs;
- the same shuffle order (seed 2304) and clip norm 1.0;
- selection by natural-distribution TRAIN-VAL cross-entropy.

The initial parameters are copied from `MLPPolicyModel(seed=2303)`, the NumPy initialisation.
Training runs in float32 on CUDA.

### 3.3 Result

| Item | Value |
|---|---|
| Model class | `game.learning.torch_policy.TorchPolicy`, 2,315 trainable parameters |
| Selected epoch | 40 (TRAIN-VAL CE 0.0431; NumPy BC: epoch 40, 0.0431) |
| Checkpoint | `game/learning/m2_3/torch_bc_checkpoint.pt`, state_dict sha256 `c6c21c23e639f89d6dcb7d98662b19320961f2ceb00cad610830a1e9a56dba4b`, file sha256 `ec0cdf40...` |
| Non-finite gradient steps | 0 |
| GPU | 2.7 s wall for 40 epochs; peak allocated 129 MiB; nvidia-smi utilisation mean 32 %, max 40 % |

Supervised TRAIN-VAL metrics (natural distribution; `torch_bc_metrics.json`):

- overall accuracy 0.982;
- **balanced accuracy 0.428** (over the 10 present classes);
- the NONE-only accuracy would be 0.972, so overall accuracy is not informative.

| Action | Support | Precision | Recall |
|---|---:|---:|---:|
| NONE | 83,146 | 0.989 | 0.993 |
| TURN_LEFT / RIGHT | 879 / 904 | 0.72 / 0.69 | 0.72 / 0.68 |
| ALERT_SACCADE_L / R | 188 / 132 | 0.20 / 0.30 | 0.08 / 0.09 |
| ESCAPE_LEFT / RIGHT | 32 / 26 | 0.54 / 0.55 | 0.22 / 0.23 |
| ESCAPE_FORWARD | 35 | 0.33 | 0.03 |
| ESCAPE_LEFT_HALF / RIGHT_HALF | 115 / 93 | 0.79 / 0.73 | 0.64 / 0.60 |
| ESCAPE_BACKWARD | 0 | - | - |

Escape behaviour:

- **Recall.** Argmax predicts some escape on 60.5 % of teacher-escape samples, and the exact
  escape on 47.5 %. Argmax-escape precision is 0.92.
- **Probability mass.** The mean escape probability is 0.55 on teacher escapes and 0.0014
  elsewhere.
- **Conditional escape.** The mean escape probability is:
  - 0.026 in the threat window (0.59 where the teacher escapes, 0.010 where it does not);
  - 0.0022 in the background;
  - 0.0005 on threat-trial states outside the window.
- **By current max(DNp01).**

  | max(DNp01) | < 0.25 | 0.25-1 | 1-2 | >= 2 |
  |---|---:|---:|---:|---:|
  | mean escape probability | 1.8e-5 | 0.0022 | 0.035 | 0.063 |

- **Synthetic frames.** The escape probability is 2.1e-6 at a quiet frame and rises to 0.005,
  0.23, 0.57 and 0.84 for one-sided DNp01 of 1, 2, 3 and 4.

The learner's expected action frequencies track the teacher's:

- NONE 83,113 vs 83,146;
- escapes 280 vs 301.

It has not collapsed to NONE; its escape is conditional on the neural threat evidence.

### 3.4 Frozen BC gate on the TRAIN-VAL benchmark (`torch_bc_gate.json`)

| Policy | Hit | Threat-window escape | Unnecessary / min | Perches / min | Admissible |
|---|---:|---:|---:|---:|---|
| N4B1C (accepted) | 0.646 | 0.74 | 4.92 | 0.58 | yes |
| mapped N4B1C teacher | 0.677 | 0.75 | 5.67 | 1.08 | no (unnecessary) |
| **PyTorch BC** | **0.677** | **0.78** | **5.17** | **0.50** | **yes, no flags** |
| NumPy BC (development evidence) | 0.677 | 0.78 | 5.17 | 0.50 | yes |

All six gate checks pass:

- hit <= N4B1C + 0.05;
- unnecessary escapes <= 5.36 / min;
- perches >= 0.275 / min;
- admissible with no flags;
- threat-window escape >= 0.5 x the teacher's;
- no collapse (0.57 >= 0.2 and >= 10 x quiet).

The PyTorch and NumPy BC benchmark records are identical: the probabilities differ by about
1e-7, so the seeded sampling draws the same maneuvers. The PyTorch BC is the official parent
checkpoint.

## 4. Development smokes (TRAIN only; not official seeds; EVAL never touched)

Summary file: `game/learning/m2_3/torch_smoke_summary.json`.

| Run | Learner | Iterations | Hit (first 5 -> last 5) | esc@L3 (start -> end) | KL(pi \|\| BC) at end | lambda_u at end | NONE share at end |
|---|---|---:|---|---|---:|---:|---:|
| numpy draft, seed 101 | NumPy (diagnostic only) | 20 | 0.590 -> 0.571 | 0.574 -> 0.426 | 1.3e-4 | 0 | 0.976 |
| torch draft, seed 101 | PyTorch, lr 1e-4 | 25 | 0.624 -> 0.624 | 0.574 -> 0.449 | 1.2e-4 | 0.058 | 0.978 |
| torch lr3e-4, seed 102 | PyTorch, lr 3e-4 | 25 | 0.614 -> 0.638 | 0.574 -> 0.644 | 9.1e-4 | 0.033 | 0.962 |

None of the runs collapsed:

- NONE stayed at 0.96-0.98, which is BC-like and below the 0.995 collapse diagnostic;
- escape stayed conditional:
  - on rollout states, escape probability was 0.03 in the threat window vs 0.001-0.006 in
    the background;
  - it was about 0.1 at max DNp01 >= 2 vs 2e-5 at max DNp01 < 0.25;
- entropy stayed at its target (about 0.04 nats);
- no non-finite gradients.

Dual warm-up worked as intended. The multipliers stayed exactly 0 until the stability gate
opened: iteration 15 for seed 101 and about 18 for seed 102. They then rose slowly
(lambda_u <= 0.06 after 10 updates).

Diagnosis at lr 1e-4:

- PPO updates were too small to test improvement: clipfrac 0 in every iteration, approx-KL
  about 1e-5 per update, and KL to BC about 1e-4;
- the synthetic strong-DNp01 escape probability drifted slowly downwards (0.57 -> 0.45), with
  the NumPy and PyTorch learners in agreement;
- the numbers are consistent with each other.

At lr 3e-4:

- the policy moved about 8 x further from BC;
- escape at the strong DNp01 frame was preserved (0.64).

Choice frozen for the official protocol: **lr_policy 3e-4**. All other settings are unchanged
from the draft:

- the KL schedule;
- the entropy scheme;
- the dual warm-up;
- the 1 : 6 mixture.

### 4.1 Credit-assignment diagnostic (torch draft smoke, means over 25 iterations)

| Quantity | Value |
|---|---|
| rollout decisions per committed strike | 829 (579 threat-trial decisions per strike) |
| samples with \|A_raw\| >= 0.05 / >= 0.2 | 8.0 % / 3.3 % |
| samples with \|A_normalized\| >= 1 | 4.9 % |

Mean \|A_raw\| by ticks from the click (50 Hz; strikes resolve about 10-25 ticks after the
click):

| Ticks from click | < -100 | -100 to -50 | -50 to -25 | -25 to 0 | 0 to 10 | 10 to 25 | 25 to 50 |
|---|---:|---:|---:|---:|---:|---:|---:|
| mean \|A_raw\| | 0.006 | 0.018 | 0.054 | 0.22 | 0.58 | 0.49 | 0.027 |

Per-sample policy-gradient norm \|grad(A_norm log pi(a \| s))\|:

| Group | Mean per-sample norm | Share of the batch gradient |
|---|---:|---:|
| escape actions (about 120 per iteration) | 17.4 | 0.011 |
| NONE actions | 0.21 | 0.040 (extrapolated) |

Critic explained variance was 0.02-0.2.

Interpretation:

- Advantage mass is concentrated in about +/- 0.5 s around the strike. The escape decision
  sits inside that window, so the credit horizon (gamma 0.99, lambda 0.95) reaches it.
- Each individual escape sample carries a large gradient because escape is rare and
  low-probability.
- In aggregate, NONE samples still contribute about 4 x more gradient than the escape samples,
  and that gradient is mostly critic noise.
- Sparse 50 Hz credit is therefore present but not blocking: the escape decision does receive
  signal. It is weak per iteration, with only about 42 strike outcomes, each worth +/- 1.

## 5. Frozen PyTorch PPO protocol

The protocol is frozen in `game/learning/m2_3/torch_ppo_protocol.json`, sha256
`3f56c198e13d1329bc44f4b518e7078e655260858614e048241bd9cb24cf1306`. It was committed and pushed
as `76ad1f4` **before any official seed ran**.

| Item | Frozen value |
|---|---|
| Environment | torch 2.13.0+cu132, CUDA 13.2, RTX 4060 Laptop |
| BC parent | state_dict sha256 `c6c21c23...`; dataset manifest, gate and smoke-summary hashes recorded |
| Architecture | TorchPolicy 2,315 parameters + training-only TorchCritic 1,985 |
| Optimizer | Adam (0.9, 0.999, 1e-8); lr policy 3e-4, lr critic 1e-3 |
| PPO | gamma 0.99, GAE lambda 0.95, clip 0.2, value coefficient 1.0, 4 epochs, minibatch 4,096, clip-grad 0.5, per-batch advantage normalisation |
| Critic warm-up | 3 iterations (policy frozen) |
| KL anchor | KL(pi \|\| frozen BC), beta 1.0 through iteration 15, then linear to 0.1 at iteration 45 |
| Entropy | adaptive coefficient: coef <- clip(coef x exp(0.5 (H* - H) / H*), 1e-4, 0.05), H* = 0.8 x BC rollout entropy (iteration 1) |
| Dual warm-up | lambda_u = lambda_p = 0 until iteration >= 15 AND 3 consecutive conditional-escape passes (see below); afterwards updated (step 0.02 on the normalised EMA violation) only while the check passes |
| Constraints (unchanged) | unnecessary escapes <= 5.36 / min (dual target 0.9 x), perches >= 0.275 / min (dual target 1.5 x) |
| Mixture | 7 rollout units per iteration, each 1 background episode + 6 threat trials (TRAIN only; benchmark unchanged) |
| Budget | 60 iterations (about 2.1 M decisions) per seed; a checkpoint every 10 iterations |
| Seeds | 1, 2, 3, 4, 5 (rollout-seed salt 2306); each starts from the identical BC checkpoint |
| Split | M2.2 TRAIN-OPT / TRAIN-VAL (sha256 `48f5fe26...`) |

The conditional-escape check passes when all of these hold:

- the synthetic strong one-sided DNp01 escape probability is >= 0.2;
- it is >= 10 x the quiet-frame probability;
- the threat-trial escape fraction is >= 0.5.

**Eligibility** (TRAIN-VAL only). A checkpoint is eligible when all of these hold:

- it is M2.1 admissible:
  - unnecessary escapes <= 5.36 / min;
  - perches >= 0.275 / min;
  - movement constraints met;
  - no hard anti-cheat flag;
- its threat-window escape fraction is >= 0.3;
- it is not no_escape-equivalent:
  - the synthetic strong-DNp01 escape probability is >= 0.2 and >= 10 x the quiet frame;
  - the NONE share of background decisions is < 0.995;
- it shows measurable neural conditioning on the TRAIN-VAL BC-dataset states: the mean
  escape probability at max DNp01 >= 2 is >= 10 x that at max DNp01 < 0.25.

**Selection** among the eligible checkpoints, in order:

1. lowest TRAIN-VAL hit probability;
2. lower unnecessary escapes / min;
3. smaller KL(pi || BC) on the TRAIN-VAL BC states.

Scalar reward is not used.

## 6. Official runs (5 preregistered seeds, all recorded)

All seeds started from the identical PyTorch BC checkpoint, ran 60 iterations and completed
without error. Full logs are in `artifacts/m2_3/torch/runs/seed_K/log.jsonl`; the summary is
in `game/learning/m2_3/torch_training_summary.json`.

| Seed | Decisions | Wall | Rollout hit (it 1-10 -> 51-60) | Dual active from | max lambda_u / lambda_p | KL(pi \|\| BC) at end | NONE share (min-max) | Entropy min / target | esc@L3 min / end | Rollout escape probability: window / background | Non-finite gradient steps |
|---|---:|---:|---|---:|---|---:|---|---|---|---|---:|
| 1 | 2,053,211 | 43 min | 0.607 -> 0.605 | 15 | 0.108 / 0.037 | 0.0104 | 0.952-0.983 | 0.025 / 0.032 | 0.33 / 0.44 | 0.027 / 0.0025 | 0 |
| 2 | 2,072,518 | 43 min | 0.629 -> 0.569 | 15 | 0.070 / 0.007 | 0.0028 | 0.945-0.981 | 0.031 / 0.043 | 0.18 / 0.24 | 0.028 / 0.0025 | 0 |
| 3 | 2,097,625 | 45 min | 0.624 -> 0.593 | 15 | 0.044 / 0.069 | 0.0033 | 0.957-0.982 | 0.030 / 0.037 | 0.27 / 0.49 | 0.027 / 0.0022 | 0 |
| 4 | 1,991,346 | 45 min | 0.605 -> 0.574 | 15 | 0.090 / 0 | 0.0027 | 0.955-0.979 | 0.033 / 0.032 | 0.39 / 0.45 | 0.028 / 0.0025 | 0 |
| 5 | 2,020,049 | 45 min | 0.602 -> 0.571 | 15 | 0.097 / 0.006 | 0.0036 | 0.948-0.980 | 0.033 / 0.037 | 0.35 / 0.45 | 0.027 / 0.0028 | 0 |

Every seed behaved as intended:

- no seed collapsed;
- the dual warm-up opened at iteration 15, and the multipliers stayed below 0.11 (M2.2
  overshot to about 2);
- NONE never exceeded 0.983;
- entropy stayed near its target;
- the conditional-escape check passed in 299 of 300 iterations (the one failure was seed 2,
  where esc@L3 briefly fell below 0.2);
- clipfrac averaged 0.0004 and approx-KL about 1e-4 per update, so the policy moved slowly
  and smoothly.

The one systematic drift across seeds: the synthetic strong-DNp01 escape probability fell
from 0.57 to 0.24-0.49. On real rollout states the escape probability stayed about 10 x higher
in the threat window than in the background.

## 7. TRAIN-VAL comparison and selection (TRAIN-VAL only)

The full table is in `game/learning/m2_3/torch_val_comparison.json`. There are 96 threat trials
and 24 background episodes.

| Policy | Hit | Threat-window escape | Unnecessary / min | Perches / min | Admissible |
|---|---:|---:|---:|---:|---|
| N4B1C (accepted runtime) | 0.646 | 0.74 | 4.92 | 0.58 | yes |
| mapped N4B1C teacher | 0.677 | 0.75 | 5.67 | 1.08 | no |
| PyTorch BC (parent) | 0.677 | 0.78 | 5.17 | 0.50 | yes |
| NumPy BC (development evidence) | 0.677 | 0.78 | 5.17 | 0.50 | yes |
| M2.2 failed candidate | 0.667 | 0.00 | 0.25 | 0.33 | yes (no_escape collapse) |
| no_escape | 0.698 | 0.00 | 0.00 | 0.50 | yes |
| fixed_maneuver | 0.594 | 0.89 | 10.83 | 0.75 | no |

M2.3 checkpoints, TRAIN-VAL hit by iteration (* = ineligible: unnecessary escapes > 5.36 / min):

| Seed | it 10 | it 20 | it 30 | it 40 | it 50 | it 60 |
|---|---:|---:|---:|---:|---:|---:|
| 1 | 0.677* | 0.646 | 0.625 | 0.552 | 0.552 | 0.562 |
| 2 | 0.677 | 0.698 | 0.646 | 0.708 | 0.625 | 0.562 |
| 3 | 0.646* | 0.677* | 0.667 | 0.667 | 0.542 | 0.604 |
| 4 | 0.635* | 0.635* | 0.635 | 0.635 | 0.583 | **0.490** |
| 5 | 0.656* | 0.698 | 0.625 | 0.604 | 0.635 | 0.594 |

Eligibility:

- 24 of 30 checkpoints are eligible.
- All 6 ineligible ones are early checkpoints (iterations 10-20) that exceed the
  unnecessary-escape budget, as the BC parent nearly does.
- Every checkpoint passes the no_escape-collapse diagnostic and neural conditioning.

Checkpoint trends:

- Later checkpoints lower both hit and unnecessary escapes (2.6-3.3 / min at iteration 60,
  against 5.17 for BC), and keep a threat-window escape of 0.78-0.88.
- The mean hit over the five iteration-60 checkpoints is 0.562, against BC 0.677.

Neural conditioning on the TRAIN-VAL BC states, for the selected checkpoint:

| max(DNp01) | < 0.25 | 0.25-1 | 1-2 | >= 2 |
|---|---:|---:|---:|---:|
| mean escape probability | 1.2e-5 | 0.0010 | 0.019 | 0.047 |

The synthetic one-sided frames give 1.1e-6, 0.002, 0.13, 0.45 and 0.76 for DNp01 of 0 to 4.

**Selected by the frozen rule:** `seed_4/ckpt_it060`.

- TRAIN-VAL hit 0.490 by attacker: easy 0.16, nominal 0.44, hard 0.88.
- Threat-window escape 0.78; 2.92 unnecessary escapes / min; 0.50 perches / min.
- Admissible with no flags; KL to BC 0.0019.

Frozen candidate record (`game/learning/m2_3/torch_candidate.json`, committed `5ce0095` before
EVAL):

- checkpoint state_dict sha256 `b545583eda9f58f89397c2095838e0cbb8ffcb5f5d39d7b14fe87f729f6400c2`;
- file sha256 `0ef41138...`;
- BC parent `c6c21c23...`;
- torch 2.13.0+cu132 / CUDA 13.2;
- protocol `3f56c198...`;
- reward v2 `e5d9106b...`, constraints `69c18997...`;
- observation schema `a53b9639...`, action schema `8848a9c7...`;
- training seed 4, iteration 60, 1,991,346 environment decisions.

The numpy export for the play launcher is `game/learning/checkpoints/m2_3_candidate.npz`
(parameter sha256 `4bb9fd32...`).

## 8. One-shot EVAL (frozen M2.1 v2 EVAL set, run exactly once)

The EVAL was run once at commit `5ce0095`. Records are in
`artifacts/m2_3/torch/eval/records.json`; the report is
`game/learning/m2_3/torch_eval_report.json`. There are 240 threat trials, 80 per attacker level.

| Policy | Hit (easy / nominal / hard) | Threat-window escape | Unnecessary / min | Perches / min | Admissible / flags |
|---|---|---:|---:|---:|---|
| N4B1C | 0.617 (0.375 / 0.562 / 0.912) | 0.81 | 5.15 | 0.65 | yes / none |
| **M2.3 candidate** | **0.592 (0.325 / 0.562 / 0.887)** | **0.86** | **3.02** | **0.78** | **yes / none** |
| fixed_maneuver | 0.475 (0.300 / 0.425 / 0.700) | 0.85 | 11.40 | 0.70 | no |
| no_escape | 0.721 (0.500 / 0.662 / 1.000) | 0.00 | 0.00 | 0.97 | yes |
| M2.2 failed candidate (M2.2 EVAL) | 0.738 | 0.00 | 0.05 | 0.90 | yes |

Paired comparison on the same 240 EVAL trials:

| Candidate vs | Difference in hit | 95 % CI | Discordant trials (candidate-only hit / reference-only hit) | McNemar exact p |
|---|---:|---|---|---:|
| N4B1C | -0.025 | [-0.090, +0.040] | 29 / 35 | 0.53 |
| fixed_maneuver | +0.117 | [+0.044, +0.189] | 55 / 27 | 0.003 |
| no_escape | -0.129 | [-0.188, -0.071] | 12 / 43 | < 0.001 |

The candidate:

- is conditional and not no_escape-equivalent;
- satisfies the constraints and is admissible with no flags;
- uses 41 % fewer unnecessary escapes than N4B1C and perches more.

Its hit rate is only 0.025 below N4B1C, which is within noise. The TRAIN-VAL 0.490 regressed
to 0.592 on EVAL: selecting the minimum of 24 noisy 96-trial estimates carried a
winner's-curse effect. This is the second and last planned use of the M2.1 v2 EVAL set (the
first was the M2.2 candidate).

## 9. GPU vs rollout timing

Means over the 300 official iterations:

| Stage | Hardware | Time per iteration (about 34k decisions) |
|---|---|---:|
| Environment rollout (MaleCNS + game simulation + per-tick numpy inference) | 7 CPU worker processes | 43.6 s |
| GAE / tensor preparation | CPU | 0.04 s |
| PPO + critic update (4 epochs, minibatch 4,096) | CUDA (RTX 4060 Laptop) | 0.37 s |

- Throughput: about 790 decisions / s end to end.
- GPU peak allocated memory: about 150 MiB.
- BC training: 2.7 s on CUDA (utilisation mean 32 %).
- Per-tick inference: numpy 23.5 us, torch CPU 85 us, torch CUDA 642 us per decision.

The GPU did **not** accelerate the MaleCNS simulator or the game. It accelerates only the
learner update, which was already under 1 % of wall time. Training is rollout-bound.

## 10. Credit-assignment findings (official runs)

Means over all official iterations:

| Quantity | Value |
|---|---|
| decisions per committed strike | 790-832 |
| samples with \|A_raw\| >= 0.2 | 3.3-3.5 % |
| critic explained variance | 0.11-0.12 |
| per-sample policy-gradient norm, escape actions vs NONE | 18-22 vs 0.21 |
| aggregate policy-gradient share, escape vs NONE | about 0.011 vs 0.043 |

The advantage mass sits within about +/- 0.5 s of the strike, so the escape decision does
receive signal: sparse 50 Hz credit is not blocking. It is thin, however:

- only about 42 strike outcomes per iteration, each worth +/- 1;
- a critic that explains about 12 % of the return variance;
- NONE-dominated noise gradients about 4 x larger in aggregate than the escape signal.

After about 2 M decisions per seed, the policies had moved only KL 0.003-0.01 from BC.

## 11. Classification and GO / NO-GO

| Criterion | Status |
|---|---|
| PyTorch BC succeeds | **pass** (section 3) |
| PPO remains conditional | **pass** (all seeds; neural conditioning > 1,000 x at every checkpoint) |
| Constraints | **pass** on TRAIN-VAL and EVAL (3.02 unnecessary / min, 0.78 perches / min) |
| Hard anti-cheat gates | **pass** (no flags) |
| Perch / lifecycle participation | **pass** |
| Not equivalent to a known exploit | **pass** |
| EVAL hit meaningfully < 0.617 | **fail**: 0.592, a paired difference of -0.025 [-0.090, +0.040], p = 0.53 |

**NO-GO for human testing.** The candidate is not integrated anywhere, and the runtime is
unchanged.

Failure classification: **C, PPO safely preserved the BC policy but produced no confirmed
improvement.** It is not:

- A: BC succeeded;
- B: PPO did not destroy BC;
- E: no instability and no non-finite gradients.

Sparse credit (D) is a contributing, sample-efficiency factor rather than a blocking one. The
policy does receive escape signal, but the per-iteration strike count and the critic quality
limit progress. The TRAIN-VAL trend (lower hit and fewer unnecessary escapes at later
iterations in all 5 seeds) is suggestive, but EVAL could not confirm it at the effect size
reached.

M2.3 is closed here. Reward, contracts and decision frequency were not changed.

Possible next steps (each needs an explicit user decision):

1. **The same M2.3 method with a much larger budget.** The runs are rollout-bound (about
   45 min per 2 M decisions), and KL was still growing slowly at iteration 60. This needs a new
   preregistration and **a fresh EVAL set**, because M2.1 v2 EVAL has now been used twice.
2. **M2.4 temporal abstraction:** a lower decision rate, action persistence or macro-actions,
   to concentrate the strike credit on fewer decisions. This changes the action contract and
   needs approval.
3. Accept that the learned policy matches N4B1C on hit rate with fewer unnecessary escapes.
   This is not a GO under the current criterion and would need an explicit criterion change.

Inspection only (not a GO; research launcher, runtime unchanged), in the M2 worktree:

```
python tools/m2_play_learned.py --checkpoint game/learning/checkpoints/m2_3_candidate.npz --arena room --no-record
```

## 12. Reproduction

```
python tools/m2_3_torch.py env
python tools/m2_3_torch.py bc-train && python tools/m2_3_torch.py bc-gate
python tools/m2_3_torch.py ppo-smoke --seed 101 --variant draft --iters 25
python tools/m2_3_torch.py ppo-smoke --seed 102 --variant lr3e-4 --iters 25
python tools/m2_3_torch.py smoke-summary && python tools/m2_3_torch.py freeze
python tools/m2_3_torch.py train --seed K        (K = 1..5)
python tools/m2_3_torch.py validate && python tools/m2_3_torch.py select && python tools/m2_3_torch.py compare
python tools/m2_3_torch.py eval-final            (refuses to run twice)
```

Commits on `feature/m2-0-learning-infra`:

| Commit | Content |
|---|---|
| `983b951` | teacher / data / leakage infrastructure |
| `7b28591` | NumPy BC freeze (development evidence) |
| `f65c995` | PyTorch BC replacement |
| `76ad1f4` | protocol freeze (pushed before the official runs) |
| `4f00d04` | TorchVersion metadata loading |
| `5ce0095` | candidate freeze (pushed before EVAL) |
| this report | EVAL and outcome |
