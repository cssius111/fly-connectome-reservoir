# M2.2: constrained learned dodge policy (first PPO training)

Status: **trained and benchmarked. Result: NO-GO for human testing.**

- All 5 preregistered training runs converged to a near-"no escape" policy.
- The frozen candidate is admissible (every constraint passes, no anti-cheat flag), but its
  one-shot EVAL hit probability is **0.738**, worse than the accepted N4B1C baseline
  (0.617), and it never escapes during a threat.
- **Failure class: optimisation, specifically premature exploration collapse under early
  Lagrangian pressure with sparse credit assignment.** It is not an information,
  action-space, capacity or benchmark limitation (section 9).
- The accepted runtime is unchanged and the learned policy was **not** integrated. Nothing
  was merged.

## 1. Frozen training protocol

`game/learning/m2_2_protocol.json`, sha256 `15350d0a...11c2`, committed and pushed as
`63dbeb6` **before any full training run**. Only a 3-iteration implementation smoke test
(TRAIN seeds) preceded it.

| Item | Value |
|---|---|
| Policy (deployed) | frozen M2.0 MLP 60 -> 32 tanh -> 11 logits, 2,315 parameters, fixed input scaling; categorical; **seeded stochastic sampling is part of the frozen policy** |
| Initialisation | NONE-action prior p = 0.97 (others 0.003 each), via the output bias |
| Critic (training only) | 60 -> 32 tanh -> 1, 1,985 parameters |
| Algorithm | PPO, clipped surrogate, numpy implementation (gradients checked by finite differences) |
| Optimizer | Adam (0.9, 0.999, 1e-8), learning rate 3e-4, policy and critic separate |
| gamma / GAE lambda | 0.99 / 0.95 (per 20 ms decision) |
| PPO clip / entropy / value coef. | 0.2 / 0.01 / 0.5 |
| Epochs / minibatch / gradient clip | 4 / 4096 / global norm 0.5 |
| Normalisation | advantages per batch; no reward normalisation |
| Rollout | per iteration 7 units of 1 background episode (M2.1 background family) + 3 threat trials (M2.1 threat families x attacker levels), about 25,000 decisions |
| Budget | 100 iterations per seed (about 2.2 million decisions); no early stopping |
| Reward | frozen M2.1 reward v2 (+1 miss, -1 hit per trial, effort 0, background price 0.00589 per unnecessary escape), sha256 `e5d9106b...` |
| Lagrangian | -lambda_u per unnecessary escape; +lambda_p per perch (touchdown) |
| Dual ascent | lambda <- clip(lambda + 0.05 x normalised violation, 0, max) on the exponential moving average (alpha 0.3) of background measurements. Targets: unnecessary <= 0.8 x 5.36 = 4.29 / min, perches >= 1.5 x 0.275 = 0.41 / min. lambda_u <= 10, lambda_p <= 5 |
| Constraints | frozen M2.1 constraints, sha256 `69c18997...` |
| Contracts | observation `a53b9639...`, action `8848a9c7...` (unchanged since M2.0) |
| Training seeds | 1, 2, 3, 4, 5 |
| Checkpoints | every 20 iterations (5 per seed, 25 in total) |
| Selection | TRAIN-VAL only (section 5) |

**Protocol freeze note.** The first smoke test showed that raw-difference dual updates were
strongly asymmetric: lambda_u rose about 0.6 per iteration but would have taken more than
100 iterations to fall. Before the freeze, the update was therefore normalised by the
target. This was an implementation-level choice made on TRAIN data. The reward and
constraints were never changed.

## 2. TRAIN / VAL / EVAL split

Split sha256 `48f5fe261c0e5ebd278e6e454623d49968a33dbc712d317915bac235cd4d091a`.

| Set | Seeds | Use |
|---|---|---|
| TRAIN-OPT | uniformly drawn from 20,000,000-24,999,999, excluding the M2.1 development seeds | gradient updates only |
| TRAIN-VAL | explicit list from 25,000,000-29,999,999 (excluding the M2.1 development seeds). 12 threat groups x 8 seeds = 96 trials; 4 background groups x 6 = 24 episodes (12 min) | checkpoint selection only |
| EVAL | the frozen M2.1 v2 set (3,800,000 + 1000 x group + k) | the frozen candidate, once |

No seed occurs in two sets. EVAL was not touched until after the candidate was frozen
(`2e454a9`).

## 3. Training runs (all 5 reported; none dropped)

| Seed | Code commit | Decisions | Training hit rate, first 10 -> last 20 iterations | Unnecessary / min, last 20 | Perches / min, last 20 | Final NONE share | Final entropy | Collapse flags |
|---|---|---|---|---|---|---|---|---|
| 1 | `63dbeb6` | 2,197,079 | 0.68 -> 0.73 | 0.09 | 0.97 | 0.996 | 0.036 | one action > 80 %, near-zero entropy |
| 2 | `fea943a` | 2,236,117 | 0.72 -> 0.73 | 0.06 | 0.73 | 0.997 | 0.023 | one action > 80 %, near-zero entropy |
| 3 | `fea943a` | 2,233,325 | 0.69 -> 0.73 | 0.11 | 0.73 | 0.999 | 0.011 | one action > 80 %, near-zero entropy |
| 4 | `fea943a` | 2,202,999 | 0.67 -> 0.72 | 0.24 | 0.75 | 0.958 | 0.258 | one action > 80 % |
| 5 | `fea943a` | 2,196,827 | 0.71 -> 0.75 | 0.07 | 0.79 | 0.993 | 0.043 | one action > 80 %, near-zero entropy |

- `fea943a` differs from `63dbeb6` only in the report mode and the play launcher; the
  training code is identical.
- Seeds 2-5 were relaunched after a syntax error in the new report mode stopped them at
  start-up. No run was partially trained or discarded.

**Learning and constraint curves** (seed 1; seeds 2-5 are qualitatively identical, see
`artifacts/m2_2/training_report.json`):

| Iteration | Hit | Unnecessary / min | Perches / min | lambda_u | lambda_p | Entropy | KL | Explained variance | NONE share | Escape fraction |
|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 0.76 | 24.0 | 0.00 | 0.23 | 0.05 | 0.206 | 1e-5 | -0.01 | 0.969 | 0.0134 |
| 5 | 0.62 | 14.5 | 0.46 | 1.16 | 0.18 | 0.113 | 7e-5 | 0.00 | 0.984 | 0.0065 |
| 10 | 0.76 | 3.7 | 0.69 | 1.71 | 0.12 | 0.041 | 9e-5 | -0.01 | 0.995 | 0.0016 |
| 20 | 0.90 | 1.2 | 1.38 | 1.57 | 0.00 | 0.014 | 3e-5 | 0.11 | 0.998 | 0.0004 |
| 50 | 0.81 | 0.0 | 1.00 | 0.14 | 0.00 | 0.006 | 0 | 0.24 | 0.999 | 0.0000 |
| 100 | 0.71 | 0.0 | 0.86 | 0.00 | 0.00 | 0.036 | 2e-5 | 0.14 | 0.996 | 0.0000 |

- lambda_u rose to 1.6-2.1 within 10 iterations in every seed; escapes were suppressed
  within 10-20 iterations.
- lambda_u returned to 0 by iteration 50-60, but by then policy entropy was about 0.005-0.02
  and the KL divergence and gradient norm were essentially 0. **The policy did not
  re-explore.**
- Seed 4's late entropy rise came from turn / alert-saccade actions (the entropy bonus). Its
  escape probability stayed at about 1e-4.
- **No conditioning was learned.** For every seed-1 checkpoint, the probability of an escape
  maneuver is about 1e-4 at any DNp01 level from 0 to 4; at initialisation it was 0.018.
  Escapes were suppressed uniformly instead of being gated by threat evidence.

## 4. TRAIN-VAL baselines

The same 96 trials and 24 background episodes as for the checkpoints:

| Policy | Hit probability | Unnecessary / min | Perches / min |
|---|---|---|---|
| **baseline_n4b1c** | **0.646** | 4.92 | 0.58 |
| no_escape | 0.698 | 0.00 | 0.50 |
| fixed_maneuver | 0.594 | 10.83 | 0.75 |
| random_legal | 0.635 | 113.6 | 0.00 |
| probe_always_escape | 0.615 | 117.8 | 0.00 |
| probe_constant_turn | 0.677 | 0.00 | 0.00 |
| probe_clock_escape | 0.688 | 15.4 | 0.25 |

## 5. Checkpoint selection (TRAIN-VAL only)

- **Rule (frozen):** eligible means unnecessary escapes <= 5.36 / min, perches >= 0.275 /
  min, all M2.1 movement constraints and no anti-cheat flag (the anti-cheat reference is the
  baseline on TRAIN-VAL). Among eligible checkpoints: the lowest hit probability; ties go to
  fewer unnecessary escapes, then the earlier checkpoint.
- **Result:** 25 checkpoints, **23 eligible**. `seed_4/it060` and `seed_5/it020` were flagged
  `ecology_avoidance` (perches 0.25 / min against 0.5 x the baseline's 0.58, on 12
  background minutes).
- Hit probability of all 25 checkpoints: 0.667-0.729 (median 0.688), every one worse than
  the baseline's 0.646.
- **Selected:** `seed_2/ckpt_it100`, hit 0.667, 0.25 unnecessary / min, perches 0.33 / min.
  By attacker: easy 0.375, nominal 0.625, hard 1.00.

**Frozen candidate** (`game/learning/m2_2_candidate.json`, committed as `2e454a9` before
EVAL):

| Item | Value |
|---|---|
| Checkpoint | `game/learning/checkpoints/m2_2_candidate.npz` (archived, 2,315 parameters) |
| Parameter sha256 | `7297eef3b2f712a685b31d22f5917762f38d2a7023d3c5add1dc88511713c155` |
| File sha256 | `acafe52a99fe2c4d55a043e2bcee1f2e856159f6fbc16a1738e70643e0e345ae` |
| Model | `mlp-60-32-11-tanh-softmax`, stochastic policy, trained 100 iterations (2,236,117 decisions), lambda_u = lambda_p = 0 at the end |

## 6. One-shot EVAL (frozen M2.1 benchmark, run once)

Candidate: 240 threat trials, 80 background episodes. Baselines: frozen M2.1 EVAL records.

**Threat** (hit probability):

| Policy | Overall | Easy | Nominal | Hard | Direct | Hover | Wall / edge | Perched / fallback | Escape in window |
|---|---|---|---|---|---|---|---|---|---|
| **learned candidate** | **0.738** | 0.512 | 0.700 | 1.000 | 0.733 | 0.833 | 0.667 | 0.717 | **0.00** |
| N4B1C baseline | 0.617 | 0.375 | 0.562 | 0.912 | 0.617 | 0.700 | 0.550 | 0.600 | 0.81 |
| no_escape | 0.721 | 0.500 | 0.662 | 1.000 | 0.733 | 0.850 | 0.650 | 0.650 | 0 |
| fixed_maneuver (inadmissible) | 0.475 | 0.300 | 0.425 | 0.700 | 0.450 | 0.517 | 0.550 | 0.383 | 0.85 |

Candidate perched-family trials: 22 perched at the click (hit 0.68) and 39 airborne fallback
(hit 0.72).

**Background:**

| Policy | Unnecessary / min | Perches / min | Wall contact | Max-speed fraction | Continuous-turn fraction | Action switches / s |
|---|---|---|---|---|---|---|
| learned candidate | 0.05 | 0.90 | 0.000 | 0.000 | 0.002 | 0.25 |
| N4B1C baseline | 5.15 | 0.65 | 0.004 | 0.000 | 0.020 | 1.13 |

**Anti-cheat:** the candidate triggers no flag and passes every constraint (admissible).
Objective J = -0.475, against -0.264 for the baseline.

EVAL report `artifacts/m2_2/eval/report.json`, sha256 `bd65c2cb...8f74`; code `2e454a9`.

## 7. Success criteria (section 16 of the milestone)

| Criterion | Result |
|---|---|
| A. All frozen constraints pass | yes |
| B. All hard anti-cheat gates pass | yes |
| C. EVAL hit rate meaningfully below N4B1C | **no** (0.738 against 0.617) |
| D. No gain from exceeding the unnecessary-escape budget | n/a (no gain) |
| E. No suppression of perch / lifecycle behaviour | yes (0.90 perches / min) |
| F. No collapse into a known probe exploit | **no**: it collapsed into the `no_escape` control behaviour, a policy the benchmark already classifies as admissible but inferior |

**GO / NO-GO for human testing: NO-GO.**

- The candidate is a well-behaved but non-escaping policy. Playing against it would show a
  fly that never dodges.
- The command below is provided as requested, for inspection only.

    Set-Location D:\Projects\flybrain-lab\artifacts\worktrees\m2-learning
    & D:\Projects\flybrain-lab\.venv\Scripts\python.exe tools\m2_play_learned.py --arena room --record --record-dir D:\Projects\flybrain-lab\results\game\sessions

The launcher loads the frozen candidate (hash-checked) and substitutes it for the policy the
game's `Session` would otherwise build. The accepted runtime and its default
FixedEscapePolicy are untouched. Recordings made this way cannot be verified by
`game.replay`, which rebuilds FixedEscapePolicy.

## 8. What the benchmark says about the space of policies

- Better admissible policies exist within the same observation and action contracts. N4B1C
  (0.617 on EVAL, 5.15 unnecessary / min) is admissible and uses only DNp01 / DNa02 timing.
  `fixed_maneuver` (0.475) shows further headroom, although outside the budget.
- A threshold rule on the whitelisted DNp01 signal is exactly representable by the
  2,315-parameter MLP: one hidden unit on dnp01_left + dnp01_right, and an output bias.

## 9. Failure classification

| Candidate cause | Verdict | Evidence |
|---|---|---|
| **Optimisation instability / premature convergence** | **primary cause** | All 5 seeds collapse identically within 10-20 iterations, while lambda_u is high (1.6-2.1). Escape probability becomes independent of DNp01. Entropy, KL and gradient norm go to about 0, so the policy cannot recover when lambda_u returns to 0 (iteration 50-60). Credit assignment is sparse: one +/-1 outcome per trial, against about 400-1,800 decisions at 50 Hz, with about 21 trials per iteration |
| Constraint conflict | contributing, not fundamental | The early dual overshoot priced every escape at about 2 (twice a strike outcome) before any threat-conditioned escaping existed. But the feasible set contains better policies (N4B1C) |
| Insufficient observation information | no | N4B1C and the fixed rule reach 0.617 / 0.475 from the same whitelisted signals |
| Action-space limitation | no | The fixed rule uses the same 11 maneuvers |
| Architecture capacity | no | The threshold / away-escape rule is representable by the MLP |
| Reward / benchmark issue | no evidence | M2.1 probe validation holds; the reward ranks the baseline above the collapsed policy (J -0.264 against -0.475). The optimiser did not find better policies; the objective did not reward the collapse |

## 10. Proposed M2.3 (training method only; no reward, benchmark or contract change)

Each item is a new preregistered protocol (TRAIN / VAL only; EVAL once per frozen candidate).

1. **Start inside the feasible, non-trivial region.**
   - Behaviour-clone the accepted N4B1C baseline into the frozen MLP, mapping its Actions to
     the nearest maneuver on TRAIN-OPT rollouts.
   - Then run constrained PPO fine-tuning with a KL penalty toward the cloned policy.
   - This gives threat-conditioned escaping from iteration 0 instead of requiring it to be
     discovered.
2. **Dual-variable and exploration control:**
   - dual warm-up (lambda frozen at its initial value for the first iterations) and a lower
     or PID-type dual gain;
   - an adaptive entropy coefficient with a target entropy, or an escape-probability floor
     during early training, so that one constraint cannot extinguish exploration before
     the policy learns conditioning.
3. **Threat-dense rollouts:** a higher share of threat trials per unit, which changes the
   training distribution only (the benchmark is unchanged), to raise the rate of
   informative outcomes.
4. **Only if 1-3 fail:** a maneuver-persistence / decision-rate change to ease credit
   assignment. This would change the action contract's timing and needs explicit approval.

## 11. Reproducibility and artifacts

| Item | Location / sha256 |
|---|---|
| Protocol | `game/learning/m2_2_protocol.json`, `15350d0a...11c2` (`63dbeb6`) |
| Candidate record | `game/learning/m2_2_candidate.json`, `82b85bd3...f59f` (`2e454a9`) |
| Candidate checkpoint | `game/learning/checkpoints/m2_2_candidate.npz`, `acafe52a...45ae` |
| Training logs, checkpoints and critics | `artifacts/m2_2/runs/seed_{1..5}/` (git-ignored). Each checkpoint JSON records seed, iteration, environment steps, code commit, protocol / observation / action / reward / constraint hashes, checkpoint hash and lambdas |
| Training report | `artifacts/m2_2/training_report.json`, `d23a02aa...f427d` |
| TRAIN-VAL baselines / checkpoints | `artifacts/m2_2/val/baselines.json` `683dedcf...1e5c`; `checkpoints.json` `34db84fe...4832` |
| EVAL | `artifacts/m2_2/eval/records.json` `54dafc25...4dbd`; `report.json` `bd65c2cb...8f74` |
| Tools | `game/learning/{ppo,training}.py`, `tools/m2_2_train.py`, `tools/m2_play_learned.py`, `test_m2_2_training.py` |
