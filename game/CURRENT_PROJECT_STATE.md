# Current project state (operational handoff)

This file is an operational handoff for future sessions. It is not a scientific result or
a runtime artifact. Evidence lives in the milestone reports listed below. Update it at the
end of every substantial milestone.

Last updated: 2026-09-26. **M2.1 exposure-controlled benchmark v2 and reward v2 complete; recommendation: GO for M2.2 training, with constrained optimisation.** Runtime baseline: M1.8-N4B5R (`363a1a9`), unchanged. The M1 slow-approach line is closed.

## Start of a new session

1. Read this file.
2. Read the current milestone report (below).
3. Run `git status`, `git branch -vv` and `git log --oneline -10`.

Do not ask the user to reconstruct old context unless the repository conflicts with this
file.

## Accepted and frozen runtime (current baseline)

| Item | Value |
|---|---|
| Milestone | **M1.8-N4B5R**, human-accepted and frozen (2026-09-25) |
| Branch | `feature/m1-8-n4b5r-geometry` (pushed; not merged) |
| Commit | `363a1a94cf3f5e33efab08cb28594c24ca694a03` (parent: N4B1C `e3c55b3`) |
| Geometry | ROOM-only `swatter.directional.tilt_geometry = elevation_aware_tilt_v1`: bearing-based tilt term x cos(elevation); ROOM config_version 17 |
| Decoder | N4B1C `lateral_dual_path_v1`, **unchanged** |
| Records | `results/game/calibration_room_m1_8_n4b5r.json` (active geometry provenance); N4B1C record unmodified |
| Validation at acceptance | 427 tests pass; protected files 20 / 20; `verify_results.py` passes; recorder schema 4 |
| Accepted | geometry, direct strikes, hover / chase tradeoff, overhead-foreshortening correction; no further tuning requested |
| Report | `game/M1_8_N4B5R_GEOMETRY_RUNTIME_CANDIDATE.md` (on the N4B5R branch) |

The N4B1C decoder layer inside it (frozen since the N4B1C acceptance):

| Item | Value |
|---|---|
| Milestone | **M1.8-N4B1C**, human-accepted and frozen |
| Branch | `feature/m1-8-n4b1c-runtime` |
| Commit | `e3c55b36084cd1d05e5f38d0b178aed0b9a59ddf` |
| Decoder | `lateral_dual_path_v1` |
| Lateral path | two inferred spikes on the same DNp01 side within <= 60 ms (3 samples) |
| Summed path (from rejected N2b) | FAST: L+R >= 2.10, OR current L+R >= 1.45 with >= 3 of the last 5 samples >= 1.45 |
| Refractory | 0.4 s shared |
| Validation at acceptance | 414 tests pass; protected files unchanged; `verify_results.py` passes; recorder schema 4; ROOM config v16 |
| Accepted | direct-strike latency, hover/chase responsiveness, escape direction |

Earlier frozen milestones (see `AGENTS.md`): M1.7.1 swatter dynamics and M1.8-A lifecycle.

## Branches

| Branch | HEAD | Role |
|---|---|---|
| `wip/m1-4-enclosure` | the N4B8 research commit (see `git log -1`); N4B8 freeze `ecb86d3`, N4B7 `c61dbd3` (freeze `8fee28a`), N4B6 `b203b46` (preregistration `987b2a9`), N4B5R state `81b213e`, N4B5 `0e9d2d9`, N4B4 `6b5c4ce`, N4B3 `d09dac4`, N4B2 `5be0aea` | research branch; research-only commits |
| `feature/m1-8-n4b5r-geometry` | `363a1a9` | **current accepted runtime** (N4B1C + G3 geometry); **do not modify** |
| `feature/m2-0-learning-infra` | `ec4db49` | M2 learning line (from `363a1a9`): M2.0 infrastructure (`b53f9a9`), M2.1 benchmark v2 / reward v2 (freeze `66b286e`); no accepted runtime file changed; pushed, not merged |
| `feature/m1-8-n4b1c-runtime` | `e3c55b3` | previous accepted runtime (decoder layer); **do not modify** |
| `archive/m1-8-n2b-rejected` | `2c306174d7bdb4e74b6c5517519ae695bd90cf44` | rejected N2b runtime snapshot; **never merge** |
| `main` | `309abd9` | untouched |
| PR #1 (`wip/m1-4-enclosure` -> `main`) | open | **unmerged; do not merge without explicit approval** |

Research worktrees (git-ignored, under `artifacts/worktrees/`): `n2b-rejected` (detached at
the archive commit), `n4b1c-runtime` (the feature branch), and `n4b1c-runtime-detached`
(detached at `e3c55b3`; used read-only by the N4B2-N4B5 tools), `n4b5r-geometry` (the
accepted N4B5R branch; used read-only by the N4B6-N4B8 tools, must stay clean), and
`m2-learning` (branch `feature/m2-0-learning-infra`; also has an `artifacts/results`
junction). Each has a `data`
junction to `data/`.

## M1.8-N4B5R acceptance summary

- Worktree: `artifacts/worktrees/n4b5r-geometry` (branch `feature/m1-8-n4b5r-geometry`, with
  `data` and `artifacts/results` junctions to the main checkout). Use it read-only for
  research that needs the accepted runtime code.
- Automated validation (report section 4):
  - N1 strong / medium 60 / 60 at 0.08 / 0.10 s; N0 0 events in 70 min.
  - Free flight (249 min): A 0, B 3, **C 8 -> 0**, D 5, mixed 4; total 12 (0.048/min).
  - Human replays: direct 38-39 / 39, strike-phase 28-29 / 29, hover 24-25 / 33; far perched
    and voluntary takeoff silent.
  - Recorder: schema 4, exact replay.
- Human test: accepted as-is on 2026-09-25; no further tuning requested.
- The human-test recording was written to `results/game/sessions、/` (the folder name
  contains a stray full-width comma from the launch command). It is untracked and left as is.

## Reporting categories (adopted 2026-09-25, from N4B4)

| Category | Meaning | Criterion |
|---|---|---|
| A | fixed-fly / no-drive neural false escapes | < 0.1/min at 95 % |
| B | inappropriate free-flight escapes (visual input present, behaviourally inappropriate) | < 0.1/min at 95 %, a **provisional working engineering criterion** |
| C | foreshortening-driven escapes (apparent-size / tilt geometry) | tracked; not a failure by itself |
| D | genuine self-approach escapes | tracked; not a failure by itself |

Do not call C or D "false triggers".

## Current milestone

**M2.1: exposure-controlled benchmark v2 and reward v2** (infrastructure / research only):
**complete. Recommendation for M2.2 training: GO, with conditions.**

- **Branch:** `feature/m2-0-learning-infra` @ `ec4db49`.
- **Report:** `game/M2_1_EXPOSURE_CONTROLLED_BENCHMARK.md` (read sections 1, 9, 10 and 13).
- **Benchmark v2:**
  - discrete threat trials (direct, hover, wall, perched-or-fallback) with one committed
    strike each;
  - every encounter parameter is fixed from the seed before the first tick;
  - a forced click at engage + 4 s;
  - a matched airborne fallback threat if the fly never perches;
  - easy / nominal / hard attacker distributions;
  - separate background families (free flight, glancing, aborted, hover-only).
- **Reward v2:** +1 per avoided strike, -1 per hit (per trial). The background
  unnecessary-escape price is 0.00589, the geometric mean of the probe band
  [0.00090, 0.0386] from TRAIN development data.
- **Constraints:**
  - unnecessary escapes <= 5.36 / min (the baseline's 95 % upper bound);
  - perches >= 0.275 / min;
  - movement pathologies use the M2.0 anti-cheat margins;
  - no anti-cheat flag.
- **Frozen:** `game/learning/benchmark_v2_frozen.json` (sha256 `c06c5bc5...`) at `66b286e`,
  before EVAL. Definition `127de798...`, attackers `9d25f8f6...`, reward `e5d9106b...`.
- **EVAL** (run once; seeds 3,800,000 + 1000 x group + k):
  - every trial is exposed for every policy; the encounter is identical across policies;
  - baseline: hit 0.617, 5.15 unnecessary / min, admissible, J -0.264;
  - no_escape: hit 0.721, J -0.442;
  - fixed_maneuver: hit 0.475 but 11.4 unnecessary / min, inadmissible;
  - every degenerate probe is inadmissible and flagged.
  - Probe acceptance A-E passes.
- Tests: 461 / 461.
- **Conditions for M2.2:**
  - a Lagrangian / constrained objective on the unnecessary-escape budget and perch
    participation;
  - a validation split from the TRAIN range for checkpoint selection;
  - EVAL once per frozen candidate;
  - the frozen contracts and the 2,315-parameter MLP;
  - replacing the runtime policy needs explicit approval and a human test.

**Previous milestone:** M2.0, learning infrastructure (NO-GO because of reward v1 exploits);
report `game/M2_0_LEARNING_INFRASTRUCTURE.md`.

## Previous research milestone

**M1.8-N4B8: biological long-mode escape pathway feasibility** (research only): complete,
outcome C. It closes the M1 slow-approach line.

- Report: `game/M1_8_N4B8_LONG_MODE_PATHWAY_FEASIBILITY.md`.
- Tools: `tools/n4b8_*.py`.
- Previous milestones:
  - N4B7: `game/M1_8_N4B7_LONG_DNP01_READOUT.md` (L1 rejected; tools `tools/n4b7_*.py`);
  - N4B6: `game/M1_8_N4B6_CONTROLLED_SLOW_APPROACH.md` (tools `tools/n4b6_*.py`, artifacts
    `artifacts/m1_8_n4b6/`);
  - N4B5: `game/M1_8_N4B5_PADDLE_VISUAL_GEOMETRY.md` (tools `tools/n4b5_*.py`, artifacts
    `artifacts/m1_8_n4b5/`);
  - N4B4: `game/M1_8_N4B4_FREE_FLIGHT_ESCAPE_INTERPRETATION.md`;
  - N4B3: `game/M1_8_N4B3_SELECTIVE_DNP04.md`;
  - N4B2: `game/M1_8_N4B2_ALTERNATIVE_DN_READOUT.md`.
- **Used data; never reuse for design:**
  - N4B3 holdout: N0 seeds 410000-440149, ROOM seeds 7401-7440;
  - N4B3 development ROOM: seeds 7301-7324;
  - N4B2 holdouts: N0 seeds 310000-340149, ROOM seeds 7201-7212.
  - N4B6 brain-noise seeds 500001-500048 (fixed-fly controlled approaches);
  - N4B7 holdouts: controlled 700001-700096, fixed-fly N0 800001-800720, committed strikes
    900001-900120, ROOM free flight 7601-7680;
  - N4B4 and N4B5 generated no new seeds. They re-simulated stored runs, and N4B5 re-ran
    them under candidate geometries.

## Major conclusions so far

- N4A: threat is separable from N0 at the Retina and sensory-spike levels at onset. DNp01
  is a weak, slow readout (MaleCNS transfer, reset to zero, side splitting). Spontaneous
  DNp01 spikes are the cell's own noise kicks, and left and right are independent.
- N4B1 / N4B1C: reading DNp01 per side removes the summed-noise coincidence; A OR N2b
  restores direct-strike speed and hover sensitivity. Accepted as the runtime.
- Rejected: legacy single-sample 1.45 (N0 false triggers); strict N2 and N2b summed-only
  decoders (latency); pooled multi-DN readouts (N4A: held-out N0 events).
- N4B2: of 10 wiring-qualified DN types, **only DNp04** gives earlier slow-approach evidence.
  - Slow-close case: DNp04 pair <= 60 ms fires at tick 613, against 668 for N4B1C.
  - N1 weak approach: detected 60 / 60, against 33 / 60.
  - N0: 0 events in 910 min, including the new 280-min holdout.
  - **But DNp04 is non-selective.** Held-out no-player ROOM free flight gives 11 escapes in
    36 min (0.31/min, from the fly's own flight near the parked paddle), against 3 for
    N4B1C. That fails the < 0.1/min target there. It also adds about 30 firings in 3.7 min
    of human play.
  - The biology agrees: DNp04 is a location-blind loom-burst DN with a weak takeoff
    phenotype.
  - DNp02, DNg40, DNp11, DNp03, DNp05, DNpe056, DNp103 and DNpe025 do not help and are
    rejected. 500 ms integration windows fail on N0.
- N4B3: **no policy-observable gate makes DNp04 selective in flight.**
  - DNp01 coincidence removes almost nothing, because of the shared LC4/LPLC2 volley.
  - MotionState overlaps between self-motion and real attacks.
  - The best slow-close-preserving combination, N4B1C OR [DNp04 pair + DNp01 60 ms +
    abs(yaw) <= 1 over 0.5 s], gives 0.158 free-flight escapes/min on the holdout, against
    0.100 for N4B1C.
  - Classification: outcome 3 (in flight, the policy-observable information cannot
    separate self-generated from external looming), and therefore outcome 2 for in-flight
    DNp04.
  - **The only clean form is a stationary-fly DNp04 path** (forward_speed <= 100): 0
    events in 192 free-flight min and 1190 fixed-fly min. It helps perched / stationary
    detection only, not the airborne slow-close case.
  - The slow-close case (tick 613) is a hovering overhead paddle whose foreshortening
    transient DNp04 catches. The range is not closing.
- N4B3 side finding: the accepted N4B1C gives about 0.08 free-flight escapes/min.
- N4B4 interpreted all 21 no-player free-flight escapes of N4B1C (249 min; all
  reconstructions exact).
  - **None resembles a spontaneous neural false trigger:** all follow real volleys above the
    N0 envelope.
  - **Self-approach regime (9):** anticipatory responses to the fly flying toward the parked
    paddle.
  - **Overhead foreshortening regime (8):** escapes while passing beneath the paddle, where
    the Retina's bearing-only tilt foreshortening (`World.visual_half_size`,
    `tilt_anisotropy` 0.25) creates apparent expansion at constant range. This is likely a
    visual-geometry artifact.
  - Inappropriate escapes by the preregistered rule: 2 in 249 min (upper 0.025/min).
  - **The same foreshortening term produced the episode-5 slow-close signal** (610-613: all
    of the expansion from apparent size, with the range receding).
  - Metric split: adopted as categories A-D above.
- N4B8 (literature-first, preregistered candidate set):
  - biology supports a GF-independent long-mode takeoff via the LC4-glomerulus DNs
    (DNp02 / DNp04 / DNp11); in real flies, looming is routed to landing, evasion or takeoff
    by flight / locomotor state, not by a visual predator-versus-self code;
  - in MaleCNS the long-mode DNs share the fast pathway's LC4 input with lower gain;
  - the landing and evasion DNs lack modelled input;
  - a mirror test proves identical brain input for external and self-generated approach;
  - **no readout-level fix exists under the current representation.**
- N4B7 (preregistered, fresh holdouts): N4B1C OR [same-side >= 4 DNp01 spikes in 1 s]:
  - recovers 130 units/s approaches (100 %, lead 1.4 s);
  - fixed fly: silent (3 in 336 min);
  - strikes: unchanged;
  - **but in closed-loop free flight: 167 escapes in 240 min (N4B1C 9); 162 are LONG-only
    (B 42, D 102), all airborne, from the fly flying toward the parked paddle at about 130
    units/s;**
  - it also adds 19 / 96 stop-rotation responses.
  - **Conclusion:** with the current inputs, slow-approach sensitivity and free-flight
    quietness trade off directly for any DNp01-temporal readout. L2 / L3 are comparisons
    only and were not promoted.
- N4B6 (controlled, fixed-fly, 15 preregistered trajectories x 48 noise seeds, through
  G3 -> Retina -> encoder -> MaleCNS -> N4B1C):
  - **A real slow-approach blind spot exists under the accepted runtime.** It is not caused
    by the old geometry: radial approaches have no tilt term.
  - Detection by speed: 130 units/s 0-6 %; 300 units/s 29 %; 800 units/s 100 % (0.36 s
    before closest approach).
  - Controls: stationary / receding 0 responses; pre-holds 0 in 24 min.
  - Attribution: DNp01 readout limit at p25 speed; stimulus limit at p10 speed.
  - **DNp04:** no help at 130 units/s (21-38 %, only near arrival); clearly earlier at 300
    units/s (100 %, +0.5 s); non-specific (47 / 48 on the stop-rotation transient).
- N4B5: **the current `tilt_anisotropy` term is a clear artifact near overhead.**
  - It depends on the horizontal bearing only.
  - Under a stationary paddle it produces 2.5-6.9 rad/s of expansion within 10 units of the
    footprint centre, against 0.13 rad/s physically.
  - It caused all 8 N4B4 overhead escapes and the episode-5 slow-close and pre-click
    signals.
  - **G3 (anisotropy x cos(elevation))** removes the artifact:
    - free-flight category C goes from 8 to 0 in 249 min;
    - all free-flight escapes: 0.048/min, upper 0.078;
    - N1 strong / medium are unchanged at 60 / 60, 0.08 / 0.10 s;
    - human direct and strike-phase coverage stay within the current geometry's own
      noise range.
  - **Cost:** hover coverage drops only on bouts that were artifact-driven (0.91 to 0.58
    detection).
  - G1 (isotropic), G2 (0.10) and G4 (explicit disk) are rejected.
  - Caveat: the frozen "every direct strike fires" criterion failed as written (38 / 39).
    G0 itself is 38 / 39 in 3 of 4 other noise realizations.

## Accepted architectural limitation of M1 (closed research line)

**Slow / gradual approach ambiguity (accepted 2026-09-25; N4B6 -> N4B7 -> N4B8).**

- M1.8-N4B8 concludes:
  - external gradual approach and self-generated approach can be **input-identical** in the
    current sensory representation;
  - so **no decoder / readout-only fix is possible**.
- Evidence:
  - the Retina carries relative geometry only (theta, theta_dot, azimuth), and a
    self-motion mirror gives bit-identical brain input and identical spikes in every
    candidate DN;
  - N4B6: N4B1C detects 130 units/s approaches in time in 0-6 %;
  - N4B7: a 1 s DNp01 count recovers them but fails free flight;
  - N4B8: no literature-motivated DN (DNp02, DNp11, DNp03, DNp07, DNp10) is more selective.
- **This line is closed.** Per the user's decision, do NOT add:
  - new visual projection populations;
  - flight-state gating;
  - efference copy;
  - optic-flow channels;
  - new long-window DNp01 rules;
  - DNp04 runtime input.

Other known open item (not scheduled): **stop-rotation transient** (N4B6, category C).

- When the paddle stops after sideways motion, the accepted controller rotates it by about
  90 deg during overshoot correction.
- Through the tilt term this gives 0.35 rad/s of apparent expansion at constant range.
- N4B1C responded in 17 / 48 orbit-control trials.
- How often it happens in real play is unknown.
- Any change needs recorded-play evidence and explicit approval.

## Do not reopen

- N4B5R geometry (`elevation_aware_tilt_v1`, ROOM config_version 17). Reopen only if
  recorded evidence demonstrates a real defect.
- N4B1C tuning: the same-side <= 60 ms rule, summed FAST 2.10, the summed 3-of-5 rule, the
  refractory and the motor semantics. Reopen only if a future milestone demonstrates a
  defect.
- M1.7.1 swatter dynamics and M1.8-A lifecycle (see `AGENTS.md`).
- Frozen experiment artifacts in `artifacts/m1-2/protected-before.json`.
- The N4B2 and N4B3 frozen criteria, and the design of new criteria on any used holdout
  listed above.
- **The M1 slow-approach research line (N4B6-N4B8)**, and every channel excluded above.

## Next permitted actions

- **M2.2: first learned-policy training** (research only, on the M2 branch), when
  requested, under the M2.1 conditions:
  - constrained objective;
  - TRAIN seeds for training and a separate TRAIN-range validation split;
  - frozen benchmark v2 EVAL once per candidate;
  - the frozen contracts and the 2,315-parameter MLP.
- **Replacing the accepted runtime policy with a learned one requires explicit approval and
  a human test.**

The M1.8-B activity-budget and flight-kinematics work remains planning only.

## Permitted without asking

- Offline research tools, re-simulation, analysis and reports on `wip/m1-4-enclosure`.
- Research-only commits and pushes to `wip/m1-4-enclosure`.

## Requires explicit user approval

- Any runtime behaviour change (`game/action.py`, `game/session.py`, ROOM config,
  calibration records, recorder schema).
- **Expanding the policy observation whitelist** (for example adding DNp04).
- Changing biological model parameters, Retina or encoder equations, noise or physics.
- Merging branches or PRs, rewriting Git history, or modifying `feature/m1-8-n4b1c-runtime`
  or `feature/m1-8-n4b5r-geometry`.
- Choosing between materially different product or scientific directions.
