# M2.4-A: threat-dense, strike-centric PPO

Status: **complete. Accepted by the human reviewer (2026-09-27) as GO for human testing, with a documented procedural deviation.**

The candidate met the preregistered EVAL-v3 success criterion (hit rate 0.552 vs N4B1C 0.640, absolute difference -0.088, paired McNemar p = 0.00026). A post-freeze multiprocessing / pickling repair was applied before EVAL. The complete formal amendment and the semantic-equivalence audit were completed after EVAL (see `game/M2_4_A_EVAL_EXECUTION_AMENDMENT.md`). Subsequent TRAIN-only audits demonstrated exact scientific-output equivalence between the old and repaired worker implementations. The run is therefore not procedurally perfect, and this is disclosed rather than corrected after the fact.

The runtime is
**not** replaced. The accepted runtime (`feature/m1-8-n4b5r-geometry` @ `363a1a9`, N4B1C decoder) is
unchanged, and no learned policy is integrated. The next step is a human test through the research launcher (section 13).

Branch `feature/m2-0-learning-infra` (worktree `artifacts/worktrees/m2-learning`). Key commits:

| Step | Commit |
|---|---|
| M2-EVAL-v3 seed manifest frozen (not run) | `660911a` |
| Strike-centric tooling, development rules | `a8ae3d1`, `d03d019` |
| Actor window locked; development rule revised before any C_window result | `adb9ca9` |
| Worker-allocation audit (identical samples) | `c67f5d2` |
| Official protocol frozen (B_strike) | `a4cb584` |
| Spawn-pool pickling fix (software only) | `bfd5c42` |
| Candidate frozen (before EVAL) | `497a990` |
| One-shot M2-EVAL-v3 run | from `497a990`; report `game/learning/m2_4_a/eval_v3_report.json` |

Unchanged throughout:
- the 50 Hz decision rate, the 11-maneuver action contract (`8848a9c7...`) and the observation contract (`a53b9639...`);
- reward v2 (`e5d9106b...`) and the constraints (`69c18997...`);
- attacker distributions, MaleCNS, Retina / encoder, physics, lifecycle and the accepted runtime;
- the M2.3 historical results;
- the PyTorch learner and the BC warm start (`c6c21c23...`).

Protected files: 20 / 20. Only `game/learning/` differs from `363a1a9` among game files. Tests: 513 / 513.

## 1. Starting point (M2.4-R0)

R0 (`12468bd`) kept 50 Hz. The M2.3 rollouts carried about 840 decisions per committed strike, with a lag-1
advantage autocorrelation of about 0.965 and about 0.8 effective independent advantage samples per strike. Only
about 3 % of decisions carried a substantial advantage, and lowering the decision rate did not add information.
M2.4-A therefore tests one hypothesis: **more independent strike outcomes per update, with correlated per-tick
samples prevented from dominating the actor gradient**. Only training data sampling and loss weighting change.

## 2. New final holdout: M2-EVAL-v3 (frozen before any training)

`game/learning/m2_eval_v3.json` (sha256 `a1e0fb41...`, `660911a`; generator `tools/m2_eval_v3.py`):

- **Seeds:** 3,900,000 + 1000 g + k. They are disjoint from TRAIN (20M-30M), EVAL v1 (3.1M-3.7M) and EVAL v2 (3.8M).
- **Design:** the M2.1 benchmark philosophy, with the 12 threat groups (4 families x easy / nominal / hard) x 40 = 480
  committed-threat trials and 4 background families x 20 = 80 background episodes.
- **Recorded hashes:** benchmark definition `127de798...`, attacker distribution `9d25f8f6...`, reward v2,
  constraints, trials code and generation code.
- **One-shot guard:** it is run only through `eval-final` after a frozen candidate exists, and it refuses a second run.

The M2.1 v2 EVAL set (used by M2.2 and M2.3) was not touched.

## 3. Sampling design (two streams, one policy)

Each iteration uses 7 CPU workers and collects:

- a **THREAT stream** of 98 discrete committed-threat trials (14 per worker):
  - family sampling shares direct 0.3 / hover 0.3 / wall 0.3 / perched_or_fallback 0.1;
  - the long perched family costs about 1,460 ticks per trial vs about 230-290 for the others;
  - attacker level uniform over easy / nominal / hard;
  - fresh TRAIN seeds from [20M, 25M) minus every development / validation seed.
- a **BACKGROUND stream** of 7 background episodes (uniform over the four families; 30-60 s each). It estimates the
  unnecessary-escape and perch rates for the dual variables and the movement pathologies.

Episodes are assigned to workers by longest-processing-time on the expected tick count (throughput only; section 7).

**Budget in strikes:** 5,880 committed threat trials per seed (98 x 60 iterations), vs 2,520 in M2.3 (42 x 60).
The official runs used about 2.86-2.95 M environment decisions per seed.

## 4. Strike-balanced actor loss (loss weighting, not reward shaping)

The environment reward is unchanged: +1 miss / -1 hit at resolution, 0.005891 + lambda_u per unnecessary escape and
+lambda_p per perch. GAE uses gamma 0.99 and lambda 0.95. Only the weight of each tick in the PPO actor loss changes.

```
threat trial i with actor-window ticks W_i:   w_t = (1 - rho_bg) * q_i / sum_j q_j / |W_i|      (t in W_i)
background episode b with n_b ticks:          w_t = rho_bg / B / n_b
q_i = 0.25 / sampling share of family(i)       (importance weight back to equal family weight)
rho_bg = 0.25
actor loss = -sum_t w_t * clipped_surrogate_t / sum_t w_t      (per strike-grouped minibatch)
```

Every committed strike (for equal family) has the same total actor weight, however many ticks it lasts. A 1,500-tick
perched trial no longer counts about 6 times more than a 250-tick direct trial. Advantages are normalised with
the same weights.

- **Actor minibatches:** 4 per epoch, built from whole strikes, so a strike is never split across minibatches.
  There are 4 epochs.
- **KL anchor and entropy:** computed on a uniform random 4,096 ticks of the whole batch.
- **Critic:** trained on all ticks, 8 epochs with minibatch 4,096. There are no privileged inputs; it is the same
  architecture as M2.3.

## 5. Credit window (TRAIN only; locked before C_window results)

Candidate windows were measured on the B_strike development rollouts (20 iterations):

| window | ticks kept | abs(advantage) mass | escape actions |
|---|---|---|---|
| full | 1.000 | 1.000 | 1.000 |
| engage (approach onset -> end) | 0.321 | 0.908 | 0.984 |
| click - 1.0 s -> end | 0.189 | 0.862 | 0.867 |
| click - 0.5 s -> end | 0.125 | 0.790 | 0.726 |

The preregistered rule picks the fewest ticks with at least 90 % of the advantage mass and at least 90 % of the
escapes. It selected **engage**, which was committed (`adb9ca9`) before any C_window result existed and never
revisited. Event times are used only by the collector to choose which collected samples enter the loss.

**Anti-leakage:** the policy sees only the frozen 60-value encoder output. Event times, strike phase, world geometry
and attacker state never enter the observation, the network input or any checkpoint. Tests check this:
`test_m2_4_a.AntiLeakage`, which covers the observation and collector context, checkpoint keys, the training batch
built from observations only, and the frozen, unrun EVAL-v3 manifest.

## 6. Development comparison (TRAIN only; seed 201; 20 iterations each)

The rule was preregistered in `a8ae3d1` and revised in `adb9ca9`, before any C_window result existed. It prefers the
simpler B_strike, requires eligibility on collapse, statistical efficiency vs A_ref and TRAIN-VAL admissibility, and
switches to C_window only with a clear advantage. The full text is in `protocol.json` (`development_rule`).

| | A_ref (M2.3 sampling / weighting) | B_strike | C_window (engage) |
|---|---|---|---|
| committed strikes / update | 42 | 98 | 98 |
| effective strikes / update (Kish, actor weights) | 20.8 | **78.4** | 79.0 |
| effective strikes (Kish, gradient norms) | 36.0 | 76.0 | 51.8 |
| actor ticks / update | 35.7 k | 49.2 k | 23.0 k |
| lag-1 advantage autocorrelation | 0.970 | 0.967 | 0.967 |
| cross-half gradient cosine (it 4+) | -0.072 | -0.050 | +0.035 |
| minibatch relative gradient variance (it 4+) | 10.96 | 8.42 | 7.29 |
| NONE share max / strong-DNp01 escape min | 0.981 / 0.46 | 0.964 / 0.51 | 0.962 / 0.40 |
| TRAIN-VAL hit [Wilson 95 %] | 0.656 [0.557, 0.744] | 0.646 [0.546, 0.734] | 0.656 [0.557, 0.744] |
| TRAIN-VAL threat-window escape / unnecessary / perch | 0.82 / 4.33 / 0.50 | 0.80 / 4.33 / 0.58 | 0.79 / 4.42 / 0.50 |
| TRAIN-VAL admissible / flags | yes / none | yes / none | yes / none |

**Mechanical decision:**
- B_strike is eligible on (i) no collapse, (ii) cosine at least that of A_ref and at least 2x A_ref effective
  strikes, and (iii) TRAIN-VAL admissibility with threat-window escape at least 0.3.
- C_window is also eligible, but shows no clear advantage over B:
  - the Wilson intervals overlap;
  - cosine +0.085 passes, but the variance ratio 7.29 / 8.42 = 0.87 exceeds 0.75.

=> **B_strike** (full actor window).

Honest reading:
- The gain in statistical efficiency is in the number of effective strikes per update (about 3.8x) and a lower
  minibatch gradient variance (about -23 %).
- The cross-half cosine stays near 0 for every variant. A single update's actor gradient is still noise-dominated;
  relative variance is well above 1.
- Development rollout hit rates were not used.

## 7. Worker-allocation audit (`c67f5d2`)

`tools/m2_4_a_worker_audit.py` ran the same 28 fixed TRAIN episodes (21 threat across all four families and 7
background) with the BC policy three ways:
- 1-worker serial;
- 7-worker balanced (loads 1 / 1 / 4 / 4 / 5 / 7 / 6);
- 7-worker contiguous (4 each).

All 16 compared fields are **identical** per episode:
- episode seed and brain reset seed (always seed + 977);
- scenario set-up hash;
- hit, resolution and event ticks, perches, unnecessary escapes;
- observation, action and collector-context hashes.

Each episode resets the world, brain noise and policy sampler from its own seed. Scheduling changes throughput only.
`freeze` refuses to run without this audit.

## 8. Frozen protocol (`game/learning/m2_4_a/protocol.json`, sha256 `62795c25...`, pushed as `a4cb584`)

- **Method:** B_strike: sampling and weighting as in sections 3 and 4, full actor window, critic 8 epochs.
- **Common with M2.3:**
  - policy lr 3e-4, critic lr 1e-3, clip 0.2, gradient norm 0.5, critic warm-up of 3 iterations;
  - KL anchor to BC with beta 1.0 held to iteration 15, then linear to 0.1 at iteration 45;
  - adaptive entropy with target 0.8 x the initial entropy;
  - gated dual warm-up: at least 15 iterations, 3 stable conditional-escape iterations, targets 0.9 x 5.36 unnecessary
    escapes / min and 1.5 x 0.275 perches / min, step 0.02, EMA 0.3.
- **Seeds:** 1-5, all from the same BC checkpoint; 60 iterations = 5,880 committed threat trials per seed;
  checkpoints every 10 iterations.
- **Selection:** two-stage, section 10.
- **Success criterion:** section 11. It was written before training.
- **Recorded provenance:**
  - the window selection (`adb9ca9`) and the development summary hash;
  - the worker audit hash and commit (`c67f5d2`);
  - the TRAIN-CONFIRM set hash (`5307cc5f...`) and the EVAL-v3 manifest hash;
  - the reward, constraint, observation and action hashes.

## 9. Official runs (all 5 seeds recorded)

| seed | decisions | strikes | s / it | dual from | lambda_u max | NONE max | strong-DNp01 escape min / end | conditional-escape iterations | KL to BC end | cosine it 4+ | rel. var. it 4+ |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 2,945,919 | 5,880 | 51 | 15 | 0.040 | 0.968 | 0.18 / 0.20 | 56 / 60 | 0.0053 | 0.041 | 7.19 |
| 2 | 2,857,449 | 5,880 | 60 | 15 | 0.100 | 0.966 | 0.22 / 0.54 | 60 / 60 | 0.0061 | 0.037 | 7.80 |
| 3 | 2,936,310 | 5,880 | 43 | 15 | 0.088 | 0.966 | 0.17 / 0.24 | 56 / 60 | 0.0025 | -0.021 | 9.57 |
| 4 | 2,872,806 | 5,880 | 43 | 15 | 0.088 | 0.966 | 0.32 / 0.54 | 60 / 60 | 0.0059 | 0.029 | 8.43 |
| 5 | 2,919,345 | 5,880 | 45 | 15 | 0.029 | 0.968 | 0.31 / 0.62 | 60 / 60 | 0.0032 | 0.053 | 7.96 |

- No collapse, no non-finite gradient step, and lambda_u at most 0.10.
- Seeds 1 and 3 briefly dipped below the 0.2 strong-DNp01 escape check. The dual update pauses in those iterations,
  as preregistered.
- Rollout hit on the threat-dense mixture drifted from about 0.62 (first 10 iterations) to about 0.58 (last 10).
  This was not used for any decision.
- Wall time was about 45-60 min per seed; CPU rollouts dominate and the GPU update takes about 0.2-0.5 s.

## 10. Selection with winner's-curse control

- **Stage 1, TRAIN-VAL screen:** all 30 checkpoints on the M2.2 TRAIN-VAL set (96 threat + 24 background episodes).
  26 are eligible. The 4 failures:
  - seed_2/it010, unnecessary escapes 6.08 / min;
  - seed_4/it020, perches 0.25 / min;
  - seed_5/it030, unnecessary escapes 5.75 / min;
  - seed_5/it040, unnecessary escapes 5.17 / min and perches 0.17 / min.

  The screen hit rates span 0.490-0.708, each with a Wilson half-width of about 0.10. The screen only nominates
  the top 6.
- **Stage 2, fresh TRAIN-CONFIRM:** 384 threat trials (32 per group) and 64 background episodes (32 min, at least
  the 30-min minimum exposure). The seeds come from [25M, 30M) and were never used before. The final ranking uses
  only this stage.

| TRAIN-CONFIRM | hit [Wilson 95 %] | threat-window escape | unnecessary / min | perches / min | admissible |
|---|---|---|---|---|---|
| **seed_2/ckpt_it060 (selected)** | **0.529 [0.479, 0.578]** | 0.84 | 3.59 | 0.78 | yes |
| seed_1/ckpt_it060 | 0.534 [0.484, 0.583] | 0.83 | 3.94 | 0.88 | yes |
| seed_3/ckpt_it060 | 0.539 [0.489, 0.588] | 0.82 | 3.06 | 0.75 | yes |
| seed_5/ckpt_it060 | 0.552 [0.502, 0.601] | 0.82 | 4.41 | 0.81 | yes |
| seed_4/ckpt_it050 | 0.565 [0.515, 0.614] | 0.82 | 3.19 | 0.97 | yes |
| seed_2/ckpt_it040 | 0.568 [0.518, 0.616] | 0.84 | 3.50 | 0.91 | yes |
| M2.3 candidate | 0.549 [0.499, 0.599] | 0.82 | 3.06 | 1.00 | yes |
| PyTorch BC | 0.589 [0.539, 0.637] | 0.78 | 5.88 | 0.78 | no (unnecessary) |
| N4B1C (accepted) | 0.591 [0.541, 0.639] | 0.79 | 5.50 | 0.66 | no (unnecessary) |
| no_escape | 0.719 [0.672, 0.761] | 0 | 0 | 1.06 | yes |
| fixed_maneuver | 0.510 [0.461, 0.560] | 0.85 | 11.97 | 0.69 | no |

- **Rule:** lowest TRAIN-CONFIRM hit; if the best two differ by < 0.02, the one with fewer unnecessary escapes.
  seed_2/it060 (0.529) and seed_1/it060 (0.534) differ by 0.005. seed_2 has fewer unnecessary escapes, so it stays.
- **Paired TRAIN-CONFIRM:**
  - vs N4B1C: -0.063 [-0.114, -0.011], p = 0.024;
  - vs BC: -0.060, p = 0.019;
  - vs M2.3: -0.021 [-0.068, +0.027], p = 0.45.
- **Winner's curse:** seed_2/it060 went 0.490 (screen) -> 0.529 (confirm) -> 0.552 (EVAL-v3). In M2.3 the
  selection went 0.490 -> 0.592 on EVAL with no confirmation stage. All top-6 checkpoints (one or more from each of the 5 seeds)
  landed in 0.53-0.57 on the confirmation set, so the effect is not one lucky checkpoint.
- The TRAIN-VAL table for the other references (M2.2 TRAIN-VAL set) is in `game/learning/m2_4_a/comparison.json`:
  - N4B1C 0.646, mapped teacher 0.677, PyTorch BC 0.677, M2.3 candidate 0.490;
  - no_escape 0.698, fixed_maneuver 0.594.

## 11. Candidate freeze (`497a990`, pushed before EVAL)

`game/learning/m2_4_a/candidate.json` / `candidate.pt`:
- **Checkpoint:** seed_2 / ckpt_it060; state_dict sha256 `a8f78d39...`; BC parent `c6c21c23...`; protocol `62795c25...`.
- **Training exposure:** training seed 2; 5,880 committed strikes seen; 2,857,449 environment decisions.
- **Contract hashes:** observation `a53b9639...`; action `8848a9c7...`; reward v2 `e5d9106b...`; constraints `69c18997...`.
- **Numpy export (play launcher):** `game/learning/checkpoints/m2_4_a_candidate.npz`, parameter sha256
  `0692117a...`.

**Preregistered success criterion** (in the protocol before training). GO for human testing only if, on M2-EVAL-v3:

- constraints pass (unnecessary escapes <= 5.36 / min, perches >= 0.275 / min, movement constraints);
- no anti-cheat flag;
- conditional escape is genuine (threat-window escape >= 0.3 and neural conditioning);
- the candidate hit rate is lower than N4B1C on the same 480 trials, with exact two-sided McNemar p < 0.05 and the
  paired 95 % CI below 0.

## 12. One-shot M2-EVAL-v3 (run exactly once)

The run covered 480 committed-threat trials and 80 background episodes (40 min), identical for every policy.

| policy | hit [Wilson 95 %] | easy | nominal | hard | direct | hover | wall | perched / fallback | threat-window escape | unnecessary / min | perches / min | admissible / flags |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| **M2.4-A candidate** | **0.552 [0.507, 0.596]** | 0.294 | 0.475 | 0.887 | 0.592 | 0.583 | 0.500 | 0.533 | 0.84 | 3.48 | 0.68 | yes / none |
| N4B1C (accepted) | 0.640 [0.596, 0.681] | 0.375 | 0.569 | 0.975 | 0.608 | 0.708 | 0.617 | 0.625 | 0.78 | 4.97 | 0.55 | yes / none |
| PyTorch BC | 0.627 [0.583, 0.669] | 0.331 | 0.588 | 0.963 | 0.633 | 0.700 | 0.542 | 0.633 | 0.80 | 5.12 | 0.62 | yes / none |
| M2.3 candidate | 0.615 [0.570, 0.657] | 0.331 | 0.562 | 0.950 | 0.608 | 0.692 | 0.550 | 0.608 | 0.82 | 2.90 | 0.68 | yes / none |
| no_escape | 0.727 [0.686, 0.765] | 0.463 | 0.719 | 1.000 | 0.733 | 0.775 | 0.658 | 0.742 | 0 | 0 | 0.90 | yes / none |
| fixed_maneuver | 0.519 [0.474, 0.563] | 0.331 | 0.500 | 0.725 | 0.442 | 0.600 | 0.567 | 0.467 | 0.84 | 11.18 | 0.57 | no (unnecessary) |

Candidate movement metrics: wall contact 0.0024, max-speed fraction 0.0022, turn-active fraction 0.026 (N4B1C:
0.0039 / 0.0001 / 0.021). The median escape latency is 0.10 s (N4B1C 0.08 s).

Neural conditioning (per-tick escape probability on TRAIN-VAL BC states, binned by max DNp01):

| max DNp01 | < 0.25 | 0.25-1 | 1-2 | >= 2 |
|---|---|---|---|---|
| escape probability | 9.8e-6 | 1.3e-3 | 0.021 | 0.098 |

The ratio from high to low is about 10^4.

**Paired comparisons on the same 480 threat trials** (candidate minus reference; McNemar exact):

| reference | difference | 95 % CI | only candidate hit / only reference hit | p |
|---|---|---|---|---|
| **N4B1C** | **-0.0875** | **[-0.133, -0.042]** | 43 / 85 | **0.00026** |
| PyTorch BC | -0.075 | [-0.117, -0.033] | 35 / 71 | 0.00061 |
| M2.3 candidate | -0.0625 | [-0.098, -0.027] | 24 / 54 | 0.00090 |
| no_escape | -0.175 | [-0.219, -0.131] | 23 / 107 | 4e-14 |
| fixed_maneuver | +0.033 | [-0.021, +0.088] | 97 / 81 | 0.26 |

**Criteria:**
- A: constraints pass. Yes.
- B: no anti-cheat flag. Yes.
- C: conditional escape is genuine (0.84 threat-window escape, neural conditioning ok). Yes.
- D: hit rate below N4B1C. Yes.
- E: paired difference significant (p = 0.00026, CI below 0). Yes.
- F: unnecessary escapes within budget (3.48 <= 5.36 / min). Yes.

**=> GO for human testing.**

Reading, stated conservatively:
- The candidate reduces the committed-strike hit rate by about 9 points against the accepted N4B1C and needs 30 %
  fewer unnecessary escapes.
- The gain is largest on hover (-0.125), wall (-0.117) and perched / fallback (-0.092) trials, and small on
  direct strikes (-0.017).
- It is also a reproducible improvement beyond BC and M2.3 on a fresh holdout, which M2.3 alone could not show.
- Only fixed_maneuver, an inadmissible control with 11 unnecessary escapes per minute, reaches a similar hit rate.
- **Limitation (confound):** M2.4-A changed both the per-seed strike budget (5,880 vs 2,520 threat trials) and the
  weighting. The official runs cannot separate the two. A_ref at the same strike budget was not run officially.
- The per-update gradient signal remains noise-dominated (cross-half cosine about 0). Improvement accumulates over
  many updates rather than per update.
- The easy-attacker hit rate (0.29) is still far from 0. The policy uses the same 11 maneuvers and the same
  bottlenecked observation, so it does not dodge perfectly.

## 13. Human test (not a runtime change)

The runtime policy is not replaced, and nothing is merged. From the M2 worktree:

```
python tools/m2_play_learned.py --checkpoint game/learning/checkpoints/m2_4_a_candidate.npz --expected-sha256 0692117af68e9a3d93ed0b2a966c9ab103c5b1d80f6a9f3cf2df900b555e2e66 --arena room --no-record
```

- The launcher substitutes only the policy object passed to `Session`. That object is the frozen candidate inside
  the training / evaluation `ManeuverPolicy` adapter.
- `--expected-sha256` now verifies the parameter hash; a wrong hash raises `checkpoint hash mismatch`.
- A headless `--smoke 3` check passes.
- Recordings made this way cannot be verified by `game.replay`, which rebuilds the accepted FixedEscapePolicy.

Adopting the learned policy in the runtime requires an explicit decision after the human test.

## 14. Reproduction

```
python tools/m2_eval_v3.py check
python tools/m2_4_a_strike_ppo.py dev --variant B_strike|A_ref|C_window --seed 201 --iters 20
python tools/m2_4_a_strike_ppo.py window-select ; python tools/m2_4_a_strike_ppo.py dev-summary
python tools/m2_4_a_worker_audit.py
python tools/m2_4_a_strike_ppo.py freeze
python tools/m2_4_a_strike_ppo.py train --seed K        (K = 1..5)
python tools/m2_4_a_strike_ppo.py screen ; ... confirm ; ... select ; ... compare
python tools/m2_4_a_strike_ppo.py eval-final            (refuses a second run)
```

Development and official logs and per-checkpoint records are under `artifacts/m2_4_a/` (git-ignored). The tracked
records are in `game/learning/m2_4_a/`.

Software incidents:
- The first A_ref development run was killed when the earlier session was stopped (Windows `DuplicateHandle`
  errors), and it was re-run from scratch.
- The first B_strike TRAIN-VAL pass was interrupted in the same way. It was completed with `dev-eval` from the saved
  final policy.
- `confirm` initially failed on a spawn-pool pickling defect. It was fixed in `bfd5c42` before any checkpoint
  confirmation; `m2_eval_v3.run_once` carried the same defect and was fixed before the one-shot EVAL.

**Post-freeze runner amendment:** `game/M2_4_A_EVAL_EXECUTION_AMENDMENT.md` documents the baseline-worker pickling
fix (`bfd5c42`) applied to the frozen M2-EVAL-v3 runner, with hash provenance A-E. It also records a full
semantic-equivalence proof, produced after the EVAL: OLD vs NEW worker identical on 3 x 28 instrumented TRAIN
episodes, through a spawn pool, and against the historical M2.2 OLD-worker records (360 episodes). The amendment and
the full proof were requested before EVAL execution but arrived after it; the ordering deviation is stated there.
