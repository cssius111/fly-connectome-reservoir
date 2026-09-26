# M2.1: exposure-controlled benchmark v2 and reward v2

Status: **complete. Recommendation for M2.2 training: GO, with conditions** (section 13).

- Branch: `feature/m2-0-learning-infra`. Benchmark v2 / reward v2 frozen at `66b286e`,
  after development on TRAIN seeds only; the EVAL set was run once afterwards.
- Unchanged: the observation and action contracts (hashes pinned to M2.0) and the accepted
  runtime (N4B5R @ `363a1a9`). Nothing was trained and nothing was merged.

## 1. Short answer

| M2.1 GO criterion | Result (held-out EVAL) |
|---|---|
| 1. Threat exposure is policy-independent | **yes**. 240 / 240 trials exposed for every policy; engage time identical in 180 / 180 airborne encounters; attacker parameters identical in 240 / 240; fallback time identical in 60 / 60 |
| 2. Suppressing ecology cannot avoid evaluation | **yes**. The three never-perching probes get the matched airborne fallback threat in 60 / 60 perched-family trials and are flagged (`ecology_avoidance`, `lifecycle_suppression`) |
| 3. The baseline no longer loses to degenerate policies | **yes**. The baseline is admissible with J = -0.264. no_escape (admissible) scores J = -0.442. Every degenerate probe is inadmissible |
| 4. Anti-cheat probes are detected | **yes**. Every probe triggers its intended flags; the baseline, no_escape and fixed_maneuver trigger none |
| 5. Threat and background are separated | **yes**. Threat metrics come from per-strike trials, background metrics from separate episodes, and constraints apply to background only |
| 6. TRAIN / EVAL separation | **yes**. Coefficients were derived on TRAIN development seeds only; EVAL was run once after the freeze; the seed sets are disjoint (tested) |
| 7. No observation leakage | **yes**. The M2.0 leakage tests pass unchanged; the contract hashes are pinned |
| 8. M1 invariants intact | **yes**. 461 / 461 tests; protected files 20 / 20; `verify_results.py` passes; no accepted runtime file changed |

**Condition for M2.2:** the reward's unnecessary-escape price is small, because it is set by
the probe band. The behavioural budget must therefore be enforced as an explicit
**constraint** during training, for example with a Lagrange multiplier. Without that, a
policy would drift toward `fixed_maneuver`-like behaviour: lower hit probability but 2.2x the
unnecessary-escape budget.

## 2. The v1 failures (M2.0) and the fixes

| v1 defect | v2 fix |
|---|---|
| Threat exposure depended on the policy (the striker kept attacking until death; episode length varied) | One committed strike per trial. Engage time, attacker skill and every other encounter draw are fixed from the seed before the first tick. A forced click at engage + 4 s guarantees the strike |
| "Never perch" removed the perched attack | Perched-or-fallback family: a matched airborne threat at a predetermined fallback time (30-40 s) if the fly has not perched |
| Episode-level reward diluted each strike | Event-level scoring: +1 per avoided strike, -1 per hit, per trial |
| no_escape and constant turning outranked the baseline | Per-trial threat score plus separate background budgets. no_escape now loses on threat score; constant turning violates constraints |
| Raw survival as the objective | Hit probability per committed strike plus background constraints; no survival-time term |

## 3. Benchmark v2 architecture

Module: `game/learning/trials.py`. Definition sha256
`127de7988a17c1dc04c60feef39f80c1edd706cd4c3b0c1511e4906fce999dd0`.

**Family A: threat trials.** Each trial is a fresh `Session.reset(seed)`:

```
PRE-THREAT (free flight, paddle parked) -> ENGAGE (drawn at setup) -> APPROACH (attacker tracks the fly)
-> CLICK (trigger distance reached, or forced at engage + 4 s) -> RESPONSE WINDOW (to strike resolution)
-> OUTCOME (hit / miss) -> +0.5 s tail -> end of trial
```

| Threat family | Setup / timing |
|---|---|
| direct | engage U(1.5, 6.0) s; approach and strike |
| hover | engage U(1.5, 4.0) s; hover 150-260 units beside the fly for U(1, 3) s; then strike |
| wall | fly placed 1.5-3 BL from a wall or in a corner (experimenter setup); engage U(1.0, 3.0) s |
| perched_or_fallback | natural perch before fallback - 2 s -> engage at perch + U(1.0, 2.5) s; otherwise airborne engage at fallback U(30, 40) s. Lifecycle is never forced |

Encounter determinism:

- The setup RNG draws every encounter parameter before the first tick.
- The aim-error noise comes from a separate stream, advanced on every tick, so its sequence
  does not depend on the policy.
- The only policy-dependent parts are the fly's own position (what the attacker tracks) and
  the natural perch time.

Per-trial record:

- hit / miss;
- escape in the response window; escape latency; number of escapes in the window;
- escape in the 1 s before the click (pre-threat); ESCAPE state at the click;
- blind pre-click escape;
- wall-contact fraction; max-speed fraction; speed at the click;
- pre-threat turn / saccade fraction;
- click distance; forced-click flag;
- exposure type at the click (airborne / perched / airborne_fallback) and the perched branch;
- first escape time since reset.

**Family B: background / ecological episodes** (no strike), sharing the M2.0 runner:

- free flight, 60 s;
- glancing passes, 20 s;
- aborted approaches, 20 s;
- hover-only, 20 s (the paddle hovers 150-260 units away and never strikes).

## 4. Attacker distributions

Attacker sha256 `9d25f8f69a0a3f191d55f2725846aecd064caedaa13d22fe75b0b1149b5a3b16`. All three
levels are used in every threat family.

| Level | Tracking lag (s) | Aim-error s.d. (units) | Click trigger distance (units) |
|---|---|---|---|
| easy | U(0.20, 0.40) | U(40, 100) | U(150, 400) |
| nominal (M2.0 human-geometry calibration) | U(0.05, 0.30) | U(0, 80) | U(50, 350) |
| hard | U(0.00, 0.10) | U(0, 20) | U(30, 150) |

Hit probability per committed strike:

| Level | Baseline, dev (TRAIN) | Baseline, EVAL | no_escape, EVAL | fixed_maneuver, EVAL |
|---|---|---|---|---|
| easy | 0.39 | **0.375** | 0.50 | 0.30 |
| nominal | 0.56 | 0.56 | 0.66 | 0.425 |
| hard | 0.95 | 0.91 | 1.00 | 0.70 |

- The easy level sits close to the recorded human sessions (21 / 52 = 0.40) without having
  been tuned to it.
- The benchmark does not depend on one skill level: every level separates the policies.
- The hard level leaves little headroom (0.91 for the baseline), but a better policy can
  still improve on it: fixed_maneuver reaches 0.70.

## 5. Exposure-equivalence checks (EVAL)

| Check | Result |
|---|---|
| Trials with a committed strike | 240 / 240 for all 7 policies |
| Identical engage time across policies (airborne families) | 180 / 180 encounters |
| Identical attacker parameters across policies | 240 / 240 |
| Identical fallback time across policies (perched family) | 60 / 60 |
| Median click delay after engage (s) | 1.82-2.08 for every policy |
| Median click distance (units) | 142-154 for every policy |
| Forced clicks | 0-1.3 %, except always_escape at 5 % (it outruns the approach; still exposed) |

Perched family branches (60 trials per policy):

| Policy | perched / fallback | Perched at the click |
|---|---|---|
| baseline | 20 / 40 | 5 |
| no_escape | 21 / 39 | 23 |
| fixed_maneuver | 28 / 32 | 0 |
| random_legal | 0 / 60 | - |
| always_escape | 0 / 60 | - |
| constant_turn | 0 / 60 | - |
| clock_escape | 5 / 55 | 1 |

- Escaping policies usually take off (escape takeoff) during the approach, so they are
  airborne at the click.
- Never perching yields the airborne fallback threat, not immunity.

## 6. Threat metrics (EVAL, 240 trials per policy)

| Policy | Hit probability | Escape in window | Median escape latency (s) | Pre-threat escape | Hit: direct / hover / wall / perched-or-fallback |
|---|---|---|---|---|---|
| **baseline_n4b1c** | **0.617** | 0.81 | 0.08 | 0.85 | 0.62 / 0.70 / 0.55 / 0.60 |
| no_escape | 0.721 | 0 | - | 0 | 0.73 / 0.85 / 0.65 / 0.65 |
| fixed_maneuver | **0.475** | 0.85 | 0.08 | 0.97 | 0.45 / 0.52 / 0.55 / 0.38 |
| random_legal | 0.646 | 0.68 | 0.12 | 1.00 | 0.68 / 0.72 / 0.53 / 0.65 |
| probe_always_escape | 0.625 | 0.71 | 0.10 | 1.00 | 0.62 / 0.62 / 0.55 / 0.72 |
| probe_constant_turn | 0.717 | 0 | - | 0 | 0.67 / 0.80 / 0.75 / 0.65 |
| probe_clock_escape | 0.667 | 0.09 | 0.14 | 0.31 | 0.72 / 0.70 / 0.65 / 0.60 |

- A pre-threat escape is common for the baseline (0.85), because the attacker's approach is
  a real looming stimulus.
- Escape spam (always-escape, random) does **not** buy a lower hit probability than the
  baseline on EVAL (0.625 and 0.646 against 0.617).
- Only `fixed_maneuver` is clearly better on threat, and it pays in background behaviour
  (section 7).

## 7. Background / ecological metrics (EVAL, 80 episodes per policy, 40 min)

| Policy | Unnecessary escapes / min | Wall contact | Max-speed fraction | Continuous-turn fraction | Perches / min | Action switches / s |
|---|---|---|---|---|---|---|
| **baseline_n4b1c** | **5.15** | 0.004 | 0.000 | 0.02 | 0.65 | 1.13 |
| no_escape | 0.00 | 0.000 | 0.000 | 0.00 | 0.97 | 0.00 |
| fixed_maneuver | **11.40** | 0.009 | 0.010 | 0.01 | 0.70 | 0.78 |
| random_legal | 112.9 | 0.029 | 0.054 | 0.40 | 0.00 | 29.9 |
| probe_always_escape | 116.1 | 0.004 | 0.147 | 0.00 | 0.00 | 4.96 |
| probe_constant_turn | 0.00 | 0.010 | 0.000 | 1.00 | 0.00 | 0.00 |
| probe_clock_escape | 15.6 | 0.001 | 0.014 | 0.00 | 0.17 | 0.65 |

## 8. Reward v2 (frozen)

Module: `game/learning/reward_v2.py`; sha256
`e5d9106b09219c601ad9e3e560375cb3be45ead2531d4832dcf6fbaa2460db1d`.

| Term | Coefficient | How set |
|---|---|---|
| per threat trial: avoided strike | **+1** | event-level objective (symmetric) |
| per threat trial: hit | **-1** | event-level objective |
| response effort, per escape in the response window beyond the first | **0** | derived: the baseline never repeats a response in the window (mean 0), so no data-supported value exists. The term stays in the definition |
| background unnecessary escape (price per escape per minute in J) | **0.00589** | derived: geometric mean of the probe band [0.00090, 0.0386] (below) |

Evaluation objective: J = mean trial score - 0.00589 x background unnecessary escapes per
minute.

**Band derivation** (development TRAIN seeds only):

| Bound | Constraint | Value |
|---|---|---|
| lower | always_escape, whose unpriced threat score beat the baseline on dev (-0.167 against -0.267), must lose once its 116 unnecessary escapes / min are priced | price > 0.00090 |
| upper | the baseline must beat no_escape and constant turning despite its own 4.75 unnecessary escapes / min | price < 0.0386 (no_escape) and < 0.0439 (constant turn) |

No coefficient was chosen on EVAL.

## 9. Behavioural constraints (constraint-first; frozen from development data)

| Constraint | Envelope | Basis |
|---|---|---|
| background unnecessary escapes / min | <= **5.36** | exact 95 % Poisson upper bound of the baseline development rate (a behavioural budget) |
| perch participation | >= **0.275 / min** | 0.5 x the baseline development perch rate |
| wall-contact fraction | <= 0.055 | baseline 95 % bootstrap upper bound + 0.05 (pathology margin) |
| max-speed fraction | <= 0.050 | baseline 95 % bootstrap upper bound + 0.05 (the M2.0 max_speed_flight margin) |
| continuous-turn fraction | <= 0.5 | the M2.0 constant_turning threshold (not tied to the baseline) |
| anti-cheat flags | none | section 11 |

**Design note, decided before the freeze and before any EVAL result:**

- A first derivation used "baseline upper bound + 0.02" for the three movement fractions.
  That would have excluded behaviour that merely differs from the baseline, for example
  more turning in order to dodge.
- Movement constraints therefore use the pathology margins of the frozen M2.0 anti-cheat
  thresholds.
- Only unnecessary escapes and perch participation are budgets relative to the baseline,
  as the milestone asked.
- A learned policy may lower hit probability and / or reduce unnecessary escapes, and may
  move differently, as long as it is not pathological.

## 10. Probe-policy results (EVAL, frozen parameters)

| Policy | J | Admissible | Violations | Flags |
|---|---|---|---|---|
| **baseline_n4b1c** | **-0.264** | **yes** | - | - |
| no_escape | -0.442 | yes | - | - |
| fixed_maneuver | -0.017 | no | unnecessary escapes (11.4 > 5.36) | - |
| random_legal | -0.956 | no | unnecessary, max-speed, perches | max_speed_flight, spawn_exploit, ecology_avoidance, fixed_timing_anticipation, repeated_maneuver_cycling, lifecycle_suppression |
| probe_always_escape | -0.934 | no | unnecessary, max-speed, perches | max_speed_flight, spawn_exploit, ecology_avoidance, fixed_timing_anticipation, lifecycle_suppression |
| probe_constant_turn | -0.433 | no | turn fraction, perches | constant_turning, ecology_avoidance, lifecycle_suppression |
| probe_clock_escape | -0.425 | no | unnecessary, perches | ecology_avoidance, fixed_timing_anticipation, lifecycle_suppression |

Acceptance (development and EVAL, identical):

| Criterion | Result |
|---|---|
| A. The baseline is preferred to clearly degenerate policies | pass |
| B. no_escape cannot win by avoiding escape costs | pass (J -0.442 against -0.264) |
| C. Always-turn cannot win through survival-time artifacts | pass |
| D. Always-escape cannot win through persistent high-speed evasion | pass |
| E. Avoiding ecological states cannot remove threat exposure | pass |
| Extra: the clock probe cannot win | pass |

**The benchmark does not make N4B1C automatically win.** `fixed_maneuver` has a much lower
hit probability (0.475) and a better J (-0.017). It is excluded only because it exceeds the
unnecessary-escape budget by 2.1x. A learned policy that reached its threat performance
within the budget would clearly beat the baseline.

## 11. Anti-cheat diagnostics

All M2.0 diagnostics are retained: wall hugging, max-speed flight, constant turning,
freezing, spawn exploitation, paddle-timing exploitation and ecology avoidance.

Added in M2.1:

| Flag | Rule |
|---|---|
| pre_emptive_perpetual_escape | threat trials: pre-threat escape in > max(0.5, baseline + 0.3) |
| fixed_timing_anticipation | > 50 % of first escapes in one 0.4 s bin of time since reset (a memorised clock) |
| repeated_maneuver_cycling | background action switches > max(5/s, 3 x baseline) |
| lifecycle_suppression | perched-branch fraction < 0.5 x baseline |

- The randomized engage times (1-6 s by family; 30-40 s fallback) defeat the clock probe.
  Its escapes land at fixed times and hit the threat window in only 9 % of trials, and it
  is flagged.
- The baseline, no_escape and fixed_maneuver trigger no flag.
- `pre_emptive_perpetual_escape` is not triggered by the escape-spam probes, because the
  baseline itself escapes pre-threat in 85 % of trials, which leaves no margin.
  - Those probes are caught by the unnecessary-escape budget and by the max-speed,
    spawn-exploit and timing flags instead.
  - This limitation of the flag is noted for M2.2.

## 12. Seed discipline and frozen hashes

| Set | Seeds | Use |
|---|---|---|
| Development | TRAIN range; `train_seeds(2100 + group, 20)` for 16 groups (12 threat = 4 families x 3 attackers; 4 background) | coefficient / constraint derivation, probe acceptance |
| EVAL (v2) | `3,800,000 + 1000 x group + k`, k = 1..20 | run once after the freeze |
| EVAL (v1, M2.0) | 3,1xx,xxx-3,7xx,xxx | not reused |

- The development and EVAL sets are disjoint; EVAL is disjoint from v1. Both are tested.
- Every list is stored in the frozen file.

| Item | sha256 |
|---|---|
| frozen definition file `game/learning/benchmark_v2_frozen.json` (commit `66b286e`) | `c06c5bc5539c481e977352dcc2abd47e8028fa509745d3de694097bbbf200bec` |
| benchmark v2 definition | `127de7988a17c1dc04c60feef39f80c1edd706cd4c3b0c1511e4906fce999dd0` |
| attacker distributions | `9d25f8f69a0a3f191d55f2725846aecd064caedaa13d22fe75b0b1149b5a3b16` |
| reward v2 | `e5d9106b09219c601ad9e3e560375cb3be45ead2531d4832dcf6fbaa2460db1d` |
| EVAL report `artifacts/m2_1/eval/report.json` | `6e56bfb1525323965f9acadb413096fc8672f0084ac2e7736d8a279c64c8906c` |
| EVAL manifest (code `66b286e`, clean tree, NUMBA threads 1) | `2ec47f04b0f62a76df051ff45cf74468428610fc7ba29ed55ed9d04a02cb5348` |
| development report | `cc499b8099cd935d326edae9dd04e71b48aa7b67812a83477d8f996cffa69851` |
| observation contract (unchanged since M2.0) | `a53b9639...b080` |
| action contract (unchanged since M2.0) | `8848a9c7...a6a0` |

**First model:** the 60 -> 32 -> 11 MLP (2,315 parameters) remains available. Only these
were done; no optimisation was run:

- deterministic forward pass: tested;
- checkpoint save / load with sha256 verification, including rejection on a mismatch:
  tested;
- TRAIN / EVAL update guards: tested.

## 13. GO / NO-GO for M2.2 training

**GO**, subject to these conditions:

1. **Constrained optimisation:**
   - optimise the per-trial threat objective (+1 / -1) subject to the frozen background
     constraints;
   - use a Lagrangian on at least unnecessary escapes / min (budget 5.36) and perch
     participation, and keep the movement-pathology constraints and anti-cheat flags as
     hard acceptance gates;
   - the scalar reward alone, with its small derived price, is not sufficient.
2. **Seed discipline:**
   - train on TRAIN seeds only;
   - select checkpoints on a separate validation split drawn from the TRAIN range (not the
     development seeds above);
   - evaluate each frozen candidate on the v2 EVAL set **once**;
   - never tune on EVAL.
3. **Contracts unchanged:** the frozen observation / action contracts and the 2,315-parameter
   MLP as the first model.
4. **Acceptance of a learned policy:** admissible (all constraints satisfied, no flag), and
   compared with the baseline by threat performance per attacker level and family, with the
   full background table reported next to it.
5. **Runtime:** any replacement of the accepted runtime policy requires explicit approval
   and a human test.
