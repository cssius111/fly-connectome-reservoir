# M2.4-R0: Temporal action abstraction feasibility

Research only, on `feature/m2-0-learning-infra` (worktree `artifacts/worktrees/m2-learning`).
No policy was trained. The following are all unchanged:

- the observation contract and the 11 maneuvers;
- reward v2 and the attacker distributions;
- MaleCNS, the Retina / encoder, physics and lifecycle;
- the accepted runtime and every M2.3 artifact.

No EVAL seed was used.

**Recommendation: keep 50 Hz. NO-GO for an action-contract change.**

- No fixed lower cadence reproduces the teacher within the preregistered tolerances.
- More importantly, lowering the cadence does not increase the effective temporal-credit
  signal: each committed strike carries about one effective independent advantage sample at
  20, 40, 100 and 200 ms alike.
- The M2.3 limitation is the number of strike outcomes, not the number of decisions.

## 0. Preregistration

The following were fixed and pushed as `a671876` before any comparison:

- the tolerances;
- the cadences and hold variants;
- the fresh development episodes;
- the credit rollouts;
- the M2-EVAL-v3 design.

Protocol: `game/learning/m2_4_r0/r0_protocol.json`, sha256 `4f268fb8...`.

Development episodes:

- 192 threat trials (16 per family x attacker) and 48 background episodes (12 per family);
- TRAIN range [25e6, 30e6), excluding the M2.1 development and M2.2 / M2.3 TRAIN-VAL seeds;
- never used for any earlier selection.

Credit rollouts: 21 units x (1 background + 6 threat), from a disjoint seed list.

All results are in `game/learning/m2_4_r0/r0_results.json`. Tool:
`tools/m2_4_r0_temporal.py`; worker code: `game/learning/temporal_r0.py`; tests:
`test_m2_4_r0.py`.

## 1. M2.3 interpretation (conclusion unchanged)

M2.3 remains a valid NO-GO under its preregistered criterion. The candidate is recorded as a
**promising but unconfirmed improvement**:

- EVAL hit 0.592 vs N4B1C 0.617;
- paired difference -0.025, 95 % CI [-0.090, +0.040], McNemar p = 0.53;
- unnecessary escapes 5.15 -> 3.02 / min;
- threat-window escape (0.86) and lifecycle metrics healthy.

The success criterion is not redefined.

New descriptive evidence on the fresh R0 TRAIN-range episodes (paired, 192 threat trials; not
a holdout claim):

| Comparison | Hit difference | 95 % CI | McNemar p |
|---|---:|---|---:|
| M2.3 candidate vs accepted N4B1C | -0.062 | [-0.130, +0.005] | 0.10 |
| PyTorch BC vs accepted N4B1C | -0.052 | [-0.110, +0.005] | 0.11 |
| M2.3 candidate vs its BC parent | -0.010 | [-0.068, +0.047] | 0.86 |
| mapped teacher vs accepted N4B1C | -0.031 | [-0.094, +0.032] | 0.42 |

Two readings follow:

- Most of the candidate's apparent advantage over N4B1C is shared with the BC policy, and
  partly with the mapped teacher itself (discrete maneuvers, stochastic execution).
- The PPO fine-tuning adds little beyond BC on these episodes.

This is consistent with section 5: PPO receives about one effective credit sample per strike.

## 2. Action run-length and persistence (closed loop, 50 Hz)

The four policies ran on the same 240 R0 episodes (about 180k ticks each). The "decision
stream" is the maneuver selected each tick; for the accepted N4B1C it is the mapped category of
its continuous Action.

### 2.1 Action shares and run lengths (decision stream)

| Policy | NONE share | NONE run median (p10-p90) | TURN run median (p10-p90) | Saccade / escape runs |
|---|---:|---|---|---|
| A accepted N4B1C | 0.973 | 540 ms (60-4,700) | 100 ms (40-260) | always 1 tick (20 ms) |
| B mapped teacher | 0.971 | 520 ms (60-4,540) | 100 ms (40-260) | always 1 tick |
| C PyTorch BC | 0.972 | 100 ms (20-3,240) | 20 ms (20-100) | always 1 tick |
| D M2.3 candidate | 0.971 | 80 ms (20-3,400) | 20 ms (20-100) | always 1 tick |

### 2.2 Teacher persistence

**Teacher (A = B).** The teacher's behaviour is event-based:

- Every escape (full or half) and every alert saccade is a **single 20 ms command**. Their
  physical duration comes from the unchanged actuator: the escape impulse plus the 0.4 s
  refractory, and the half-sine saccade pulse.
- Turns are short holds, median 100 ms.
- NONE fills 97 % of ticks, in long, heavy-tailed runs.
- Escape bouts (non-NONE stretches containing an escape, gaps <= 100 ms) last a median of 120 ms
  (p90 about 420 ms). The escape is usually the bout's first command (median onset-to-escape
  0 ms, p90 120 ms).

**Learned policies (C, D).** They share the teacher's action frequencies but not its
persistence:

- Independent per-tick sampling fragments turns into 20 ms flickers.
- It roughly doubles maneuver changes in the threat window: 12.2-12.3 vs 5.8 per trial.

### 2.3 Probability of at least one action change within a horizon (decision stream)

| Context (policy) | 20 ms | 40 ms | 60 ms | 100 ms | 150 ms | 200 ms | 300 ms |
|---|---:|---:|---:|---:|---:|---:|---:|
| all ticks (B) | 0.017 | 0.027 | 0.036 | 0.052 | 0.073 | 0.084 | 0.110 |
| **threat window +/- 0.5 s (B)** | 0.135 | 0.215 | 0.287 | **0.414** | 0.565 | 0.639 | 0.778 |
| threat, outside the window (B) | 0.007 | 0.011 | 0.015 | 0.022 | 0.033 | 0.041 | 0.059 |
| background flight (B) | 0.020 | 0.030 | 0.041 | 0.059 | 0.082 | 0.096 | 0.129 |
| wall / near-wall (B) | 0.020 | 0.031 | 0.043 | 0.062 | 0.085 | 0.100 | 0.132 |
| perched (B) | 0.006 | 0.010 | 0.014 | 0.021 | 0.031 | 0.038 | 0.054 |
| lifecycle transition (B) | 0.010 | 0.016 | 0.021 | 0.030 | 0.042 | 0.050 | 0.065 |
| threat window (A, accepted) | 0.137 | 0.220 | 0.297 | 0.426 | 0.581 | 0.659 | 0.796 |
| threat window (C, BC) | 0.281 | 0.407 | 0.492 | 0.606 | 0.710 | 0.758 | 0.845 |
| threat window (D, M2.3) | 0.282 | 0.411 | 0.499 | 0.614 | 0.721 | 0.767 | 0.850 |

The redundancy is real but context-dependent:

- Outside the threat window, a 100-200 ms hold would coincide with a teacher action change in
  only 2-10 % of cases.
- Inside the +/- 0.5 s threat window, **41 % of 100 ms windows and 64 % of 200 ms windows
  contain a teacher action change**.
- The accepted N4B1C behaves the same way.

Action autocorrelation (the group identity kappa over chance) for the teacher is 0.69, 0.63,
0.47 and 0.31 at lags 20, 40, 100 and 200 ms, and 0.20-0.26 beyond 500 ms. It is lower for BC
and M2.3 (0.48-0.52 at 20 ms).

### 2.4 Per-threat decisions

| Policy | Decisions per threat trial | Maneuver changes per trial | Changes in +/- 0.5 s window (median) | Distinct maneuvers in window |
|---|---:|---:|---:|---:|
| A accepted | 578 | 10.0 | 5.8 (6) | 4.1 |
| B mapped teacher | 567 | 9.9 | 5.8 (6) | 4.0 |
| C BC | 559 | 17.8 | 12.2 (12) | 4.4 |
| D M2.3 | 568 | 16.9 | 12.3 (12.5) | 4.5 |

## 3. Teacher under hypothetical decision cadences (closed loop; preregistered tolerances)

How the wrapper works:

- The mapped teacher still observes every tick; its decoder integrates DNp01 every 20 ms.
- A maneuver is selected only every 20 / 40 / 100 / 200 ms and held in between.
- At 20 ms the wrapper reproduces the mapped teacher bit-exactly (tested).

Two selection variants:

- **sampled:** the teacher's label at the decision tick;
- **latched:** the highest-priority label since the last decision (escape > saccade > turn >
  none). An escape is delayed to the next decision tick instead of being lost.

Holding uses the unchanged actuator: a held escape fires once and is then refractory, and a
held saccade does not restart its pulse.

| Cadence / variant | Hit | Threat-window escape | Median latency | Unnecessary / min | Perches / min | Wall contact | Turn-active | In-run agreement (non-NONE) | Failed checks |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---|
| 20 ms reference (B) | 0.568 | 0.80 | 0.08 s | 5.12 | 0.62 | 0.004 | 0.032 | 1.00 | - |
| 40 ms sampled | 0.656 | 0.41 | 0.08 | 2.38 | 0.83 | 0.001 | 0.035 | 0.85 | T1 T3 T4 O1 |
| **40 ms latched** | 0.573 | 0.78 | 0.08 | 5.08 | 0.58 | 0.005 | **0.041** | 0.79 | **T7 only** |
| 100 ms sampled | 0.677 | 0.15 | 0.08 | 1.00 | 0.58 | 0.001 | 0.036 | 0.71 | T1 T3 T4 O1 O3 |
| **100 ms latched** | 0.578 | 0.76 | 0.10 | 4.62 | 0.67 | 0.004 | **0.054** | 0.45 | **T7, O3** |
| 200 ms sampled | 0.693 | 0.08 | 0.15 | 0.67 | 0.58 | 0.001 | 0.034 | 0.58 | T1 T2 T3 T4 O1 O3 |
| 200 ms latched | 0.547 | 0.78 | 0.10 | 3.62 | 0.50 | 0.003 | 0.080 | 0.21 | T4 T7 O2 O3 |

Paired McNemar p against the reference:

- sampled: 0.009 (40 ms), 0.005 (100 ms), 0.0007 (200 ms), all with significantly *more* hits
  because escapes are lost;
- latched: 1.0 (40 ms), 0.86 (100 ms), 0.66 (200 ms).

No configuration raises an anti-cheat flag.

Open-loop replay of the 522,651 frozen teacher labels:

| Cadence / variant | Escape-event recall (O1) | Mean escape delay (O2) | Turn agreement (O3) | Saccade tick agreement |
|---|---:|---:|---:|---:|
| 40 ms sampled | 0.51 | 0 | 0.92 | 0.50 |
| 40 ms latched | 1.00 | 0.010 s | 0.87 | 0.50 |
| 100 ms sampled | 0.21 | 0 | 0.77 | 0.19 |
| 100 ms latched | 0.98 | 0.039 s | 0.55 | 0.19 |
| 200 ms sampled | 0.11 | 0 | 0.60 | 0.10 |
| 200 ms latched | 0.96 | 0.088 s | 0.28 | 0.10 |

Findings:

1. **Sampled cadences are invalid.** Escapes are single-tick events, so plain subsampling loses
   49 % (40 ms) to 89 % (200 ms) of them. The threat-window escape rate collapses, and the hit
   rate rises significantly.
2. **Latched cadences preserve threat-response performance up to 100 ms.**
   - At 40 ms and 100 ms, hit, threat-window escape, latency, unnecessary escapes, perch and
     wall behaviour stay within tolerance (T1-T6).
   - At 200 ms, the delay reaches 88 ms and the unnecessary-escape rate shifts by 29 %.
3. **Every latched cadence fails through turns (T7 / O3).** Holding a turn for the whole
   interval inflates turn activity by 28 % at 40 ms, 69 % at 100 ms and 150 % at 200 ms.
   Teacher turns (median 100 ms, p10 40 ms) do not align with fixed decision boundaries.
4. By the preregistered rule, **no cadence coarser than 20 ms passes**.

The observation constraint also bounds the design space. The unchanged observation shows the
current frame plus 4 history frames (100 ms). A learned policy deciding every 200 ms would never
see half of the ticks, and the latched variant's "remember the earliest escape trigger" is not
available to it.

## 4. Fixed cadence vs variable-duration (maneuver, duration) interface

Natural durations in the teacher streams (A / B, closed loop; open-loop identical):

| Maneuver | Decision-level duration | Physical duration (existing actuator) |
|---|---|---|
| full escape | always 1 tick | impulse + 0.4 s refractory |
| half escape | always 1 tick | impulse (strength 0.5) + 0.4 s refractory |
| alert saccade | always 1 tick | half-sine pulse (duration set by the angle and the peak-rate cap) |
| turn | median 100 ms, p10 40, p90 260, max 460 | yaw command while held |
| NONE | median 520-540 ms, p10 60 ms, p90 about 4.6 s | - |

There is a small, mechanically meaningful structure:

- one-shot events whose duration is already built into the actuator;
- turns of 40-260 ms;
- open-ended NONE.

A (maneuver, duration) interface could therefore represent the teacher with few decisions:

- events at duration 1;
- turns at about {40, 100, 200} ms;
- NONE at chosen hold lengths.

But the evidence does not justify it:

- **Events need 20 ms timing.** The value of a threat response lies in when the one-tick
  escape fires. Any committed NONE duration is a reaction delay, the same as the latched
  cadence: 40-100 ms of delay was tolerable, 200 ms was not. An interruptible NONE is simply
  the 50 Hz interface.
- **Durations would only coarsen turns and NONE.** Neither carries the credit that matters:
  77 % of the advantage mass lies in the +/- 0.5 s strike window around the escape decision
  (section 5).
- **The credit gain is negligible** (section 5).

A macro-duration interface would add a new learned head and a new action contract for no
demonstrated benefit. The one observed flaw it would cure, the learned policies' turn flicker
(20 ms runs), is a policy-quality issue. It is not what limited M2.3, and it can be addressed
later without changing the contract if it matters.

## 5. Credit-assignment analysis

Setup:

- the M2.3 candidate rolls out on the preregistered units: 147 episodes, 126 committed strikes;
- advantages come from the frozen seed-4 iteration-60 critic, gamma 0.99, GAE lambda 0.95;
- for a hypothetical cadence of k ticks, the same trajectories are re-aggregated into k-tick
  decisions using SMDP returns (sum of gamma^i r) and per-decision GAE with (gamma lambda)^k.

| Cadence | Decisions per strike | Decisions in +/- 0.5 s window per strike | Share with \|A\| >= 0.2 (all / window) | Lag-1 advantage autocorrelation | Effective independent window samples per strike | Non-NONE maneuver runs containing no decision tick | Share of \|A\| mass in window |
|---|---:|---:|---|---:|---:|---:|---:|
| 20 ms | 842 | 44.3 | 3.3 % / 62 % | 0.965 | **0.80** | 0 % | 77 % |
| 40 ms | 421 | 22.2 | 3.3 % / 62 % | 0.930 | **0.80** | 36 % | 77 % |
| 100 ms | 169 | 8.9 | 3.5 % / 67 % | 0.801 | **0.98** | 65 % | 77 % |
| 200 ms | 85 | 4.5 | 3.7 % / 69 % | 0.619 | **1.05** | 80 % | 77 % |

Findings:

- **Repeated actions receive highly redundant credit at 50 Hz.** Consecutive advantages
  correlate at 0.965, so the 44 window decisions per strike are worth about 0.8 independent
  samples.
- Coarsening removes the redundancy: 842 -> 85 decisions per strike, with the same share of
  informative decisions and the same advantage mass in the window.
- **Coarsening does not create signal.** The effective number of independent credit samples per
  strike stays at about 1 (0.80 -> 1.05) across a 10 x change in cadence.
- Meanwhile, 36-80 % of non-NONE maneuvers (mostly single-tick events) would fall between
  decisions under a fixed cadence.
- Same-action, same-sign strong advantage pairs are 3-5 % at every cadence, so there is no
  large block of repeated non-NONE actions double-counting credit. The redundancy sits in
  NONE runs.

**Conclusion.** Sparse temporal credit in M2.3 is a property of the task: about one +/- 1
outcome per strike. It is not an artifact of the decision frequency. A lower cadence would
reduce the sample count and compute per update, but it would not raise the information
available per strike. That is the quantity that limited M2.3's held-out gain.

## 6. M2-EVAL-v3 (defined only; not generated, not run)

The M2.1 v2 EVAL set has been observed by M2.2 and M2.3. It remains valid historical evidence,
but it is not a pristine future holdout. Any future M2.4 learned candidate must be evaluated on
**M2-EVAL-v3**, preregistered in `r0_protocol.json`:

- **Philosophy.** Unchanged benchmark v2:
  - 4 threat families x 3 attacker levels with the frozen attacker distributions
    (benchmark_definition `127de798...`);
  - 4 background families;
  - the same metrics, constraints, anti-cheat flags and reward v2.
- **Seeds.**
  - Threat group g (0-11): 3,900,000 + 1000 g + k, for k = 1..40.
  - Background group g (12-15): 3,900,000 + 1000 g + k, for k = 1..20.
  - All inside the registered EVAL range. They are disjoint from EVAL v1 (3.1-3.7 M) and v2
    (3,800,001-3,815,020), including their brain-noise seeds (seed + 977). This is tested.
- **Size.** 480 threat + 80 background episodes per policy. This doubles the threat count, for
  a paired 95 % CI of about +/- 0.045 at the M2.3 effect size.
- **Baselines.** Run once on v3 when it is frozen, before any M2.4 candidate exists.
- **Freeze rule.** The seed manifest and definition hash are committed and pushed before M2.4
  full training. v3 is never inspected during hyperparameter selection. The single candidate is
  frozen (hash committed) before its one v3 run.

## 7. Answer and recommendation

| Preregistered outcome | Evidence | Verdict |
|---|---|---|
| **A: 50 Hz justified; temporal abstraction would distort behaviour** | Escapes and saccades are single-tick events; sampled cadences lose them. Latched cadences distort turning (T7 / O3). A learned policy with the unchanged 100 ms observation cannot see all ticks beyond 100 ms. Abstraction does not raise effective credit per strike | **selected** |
| B: a lower fixed cadence preserves the teacher | 40 / 100 ms latched preserve threat behaviour (T1-T6), but no cadence passes all preregistered tolerances | not supported |
| C: macro durations cluster naturally | Durations do cluster (events 1 tick, turns 40-260 ms, NONE open-ended). But the only reducible redundancy is in NONE / turn holds, and the credit per strike is unchanged | clustering real; not justified as a contract change |

**GO / NO-GO for an action-contract change: NO-GO.** Keep the 50 Hz, 11-maneuver interface.

Implications for M2.4 (not implemented; each needs a user decision):

- The lever for held-out improvement is more strike outcomes per unit of learning, or a better
  per-strike signal, rather than fewer decisions. Options: a larger rollout budget with the
  threat mixture, a lower-variance critic / advantage estimate, or multi-seed averaging.
- Any M2.4 candidate must use M2-EVAL-v3.
- If action flicker in learned policies becomes a concern, it can be studied without an
  action-contract change.
