# Current project state (operational handoff)

This file is an operational handoff for future sessions. It is not a scientific result or
a runtime artifact. Evidence lives in the milestone reports listed below. Update it at the
end of every substantial milestone.

Last updated: 2026-10-08. **The M2 learning line is closed by the user's decision: no further training, no further human sessions, no runtime integration.** M2.4-B stopped early at 12 of 30 blind sessions (not unblinded, not analysed, no conclusion). M2.4-A remains GO for human testing with a documented procedural deviation (EVAL-v3 hit 0.552 vs N4B1C 0.640, p = 0.00026), never followed by a completed human test. Runtime baseline: M1.8-N4B5R (`363a1a9`), unchanged. The M1 slow-approach line is closed.

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
| `feature/m2-0-learning-infra` | `a6c9b37` | M2 learning line (from `363a1a9`): M2.0 infrastructure (`b53f9a9`), M2.1 benchmark v2 / reward v2 (freeze `66b286e`), M2.2 PPO training (protocol `63dbeb6`, candidate `2e454a9`), M2.3 PyTorch BC + PPO (BC `f65c995`, protocol `76ad1f4`, candidate `5ce0095`, report `f723375`), M2.4-R0 temporal feasibility (preregistration `a671876`, report `12468bd`), M2.4-A strike-centric PPO (EVAL-v3 freeze `660911a`, protocol `a4cb584`, candidate `497a990`, report `8a5eb2b`, amendment `b1b34d3`), M2.4-B blind human test (preregistration `f048ba6`, blinding amendment `9201c24`, early termination `a6c9b37`); no accepted runtime file changed; pushed, not merged |
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

**Project status: M2 learning line closed (2026-10-08, user decision).** Nothing is in progress.

- **Final learned result:** M2.4-A candidate seed_2/ckpt_it060 (`497a990`), GO for human testing with a
  documented procedural deviation (see below and `game/M2_4_A_EVAL_EXECUTION_AMENDMENT.md`).
- **M2.4-B closed early:** 12 of 30 preregistered blind sessions (blocks 1-6, all complete) were played and
  rated; the participant then stopped. The data were **not unblinded and not analysed** (`reveal` not run,
  ratings not locked); there is no human-acceptance conclusion. Record: `game/M2_4_B_EARLY_TERMINATION.md`
  (`a6c9b37`). Private data stay in `artifacts/m2_4_b/` (git-ignored).
- **Runtime:** unchanged (`363a1a9`, default N4B1C); the learned policy is not integrated; nothing merged.
- **To reopen:** finish sessions 13-30 under the unchanged protocol, or amend before unblinding to define an
  exploratory 6-block analysis (the tools refuse `reveal` / `analyze` on a partial set).

**Previous milestone, M2.4-B: blind human gameplay acceptance** (human validation only; no training):
**closed early at 12 / 30 sessions; see above.** Original setup:

- **Protocol:** `game/M2_4_B_HUMAN_TEST_PROTOCOL.md` and `game/learning/m2_4_b/protocol.json` (sha256 `51f3974f...`).
  The randomisation manifest `game/learning/m2_4_b/randomization_manifest.json` (sha256 `67fcfa9a...`) was pushed
  in `f048ba6` before any session.
- **Design:**
  - A = N4B1C, B = the frozen M2.4-A candidate;
  - ROOM, 30 sessions = 15 blocks of 2 with the same world seed per block, order from HMAC(secret key);
  - 180 s of live-fly play per session;
  - neural HUD disabled;
  - **amendment 1 (`9201c24`, before any session): no per-session reveal.** The player sees only "Response saved. Policy identity remains blinded." After 30 / 30 rated sessions, `reveal` locks the ratings, verifies the key and commitments and decodes the assignments; `analyze` requires this. Game output goes to a private log. Blinding smoke test `tools/m2_4_b_blind_smoke.py`: 7 / 7 pass. Record: `game/M2_4_B_BLINDING_AMENDMENT.md`;
  - acceptance checks A-E preregistered.
- **Private data:** the key, results, ratings and recordings are in `artifacts/m2_4_b/` (git-ignored; do not open
  before the end; do not commit without the user's permission).
- **Launch (PowerShell):**
  `Set-Location D:\Projects\flybrain-lab\artifacts\worktrees\m2-learning; & D:\Projects\flybrain-lab\.venv\Scripts\python.exe tools\m2_4_b_blind_ab.py play`
  Progress: `... tools\m2_4_b_blind_ab.py status`. After all 30 sessions: `reveal`, then `analyze`, then write
  `game/M2_4_B_HUMAN_GAMEPLAY_ACCEPTANCE.md`.
- **Boundary:** even on GO, the default policy is not replaced. Runtime integration needs a separate explicit approval.

**Previous milestone:** M2.4-A: threat-dense strike-centric PPO. **Accepted by the human as GO for human testing,
with a documented procedural deviation.** The candidate met the preregistered EVAL-v3 success criterion. A
post-freeze multiprocessing / pickling repair was applied before EVAL; the complete formal amendment and the
semantic-equivalence audit were completed after EVAL. Subsequent TRAIN-only audits demonstrated exact
scientific-output equivalence between the old and repaired worker implementations.

**M2.4-A: threat-dense, strike-centric PPO** (approved training; sampling / loss weighting only): **complete.
Result: GO for human testing. The runtime is not replaced.**

- **Report:** `game/M2_4_A_STRIKE_CENTRIC_PPO.md` (on `feature/m2-0-learning-infra`; read sections 6, 10, 12, 13).
- **Holdout:** M2-EVAL-v3, frozen before training (`660911a`, manifest `a1e0fb41...`: 480 threat + 80 background,
  seeds 3,900,000 + 1000 g + k). **It has now been used once** (by this candidate) and is no longer a future holdout.
  The M2.1 v2 EVAL set was not touched.
- **Development** (TRAIN only, seed 201):
  - A_ref / B_strike / C_window;
  - `engage` actor window locked in `adb9ca9` before any C_window result;
  - rule revised in the same commit;
  - worker-allocation audit `c67f5d2`: identical samples;
  - the locked rule chose **B_strike** (strike-balanced actor weights, 98 threat trials + 7 background episodes per
    iteration, full window).
- **Protocol:** `game/learning/m2_4_a/protocol.json`, sha256 `62795c25...` (`a4cb584`):
  - M2.3 learner / KL / entropy / dual;
  - 5,880 committed threat trials per seed; seeds 1-5; all runs healthy.
- **Selection:** a TRAIN-VAL screen (26 / 30 eligible), then the top 6 on a fresh TRAIN-CONFIRM set (384 threat
  trials); winner's-curse control. The candidate is **seed_2/ckpt_it060**:
  - state_dict `a8f78d39...`;
  - numpy export `game/learning/checkpoints/m2_4_a_candidate.npz`, parameter sha256 `0692117a...`;
  - frozen in `497a990`.
- **One-shot EVAL-v3:**
  - hit 0.552 [0.507, 0.596] vs N4B1C 0.640;
  - paired -0.0875 [-0.133, -0.042], p = 0.00026;
  - also below BC (-0.075) and M2.3 (-0.0625), both p < 0.001;
  - 3.48 unnecessary escapes / min, 0.68 perches / min, threat-window escape 0.84;
  - admissible, no flags;
  - largest gains on hover / wall / perched trials.
- **Caveats:**
  - strike budget (2.3x M2.3) and weighting are confounded;
  - the per-update gradient stays noise-dominated;
  - the easy-attacker hit rate is still 0.29.
- **Human test (next step; research launcher only; M2 worktree):**
  `python tools/m2_play_learned.py --checkpoint game/learning/checkpoints/m2_4_a_candidate.npz --expected-sha256 0692117af68e9a3d93ed0b2a966c9ab103c5b1d80f6a9f3cf2df900b555e2e66 --arena room --no-record`
- **Runner amendment:** `game/M2_4_A_EVAL_EXECUTION_AMENDMENT.md` (`b1b34d3`) documents a post-freeze pickling fix to the M2-EVAL-v3 baseline worker (`bfd5c42`), hash provenance A-E and a full OLD / NEW equivalence proof (identical on instrumented TRAIN episodes, via a spawn pool, and against the historical M2.2 records). The proof was completed after the one-shot EVAL had already run, and this ordering deviation is stated there. Acceptance of the GO given that deviation is a human decision.
- **Do not** integrate the learned policy into the runtime or merge anything without an explicit decision.
- Tests: 513 / 513; protected files 20 / 20.

**Previous milestone:** M2.4-R0: temporal action abstraction feasibility (research only; no training): complete.
Outcome A: keep 50 Hz; NO-GO for an action-contract change.

- **Report:** `game/M2_4_R0_TEMPORAL_ACTION_FEASIBILITY.md`.
- **Results:** `game/learning/m2_4_r0/r0_results.json`.
- **Preregistration:** `r0_protocol.json`, sha256 `4f268fb8...`, pushed as `a671876` before
  any comparison.
- **Data:** 240 fresh TRAIN-range episodes (192 threat + 48 background) for:
  - the accepted N4B1C;
  - the mapped teacher;
  - the PyTorch BC;
  - the M2.3 candidate;
  - the teacher at hypothetical 40 / 100 / 200 ms cadences (sampled / latched hold).
- **Findings:**
  - teacher escapes and saccades are single-tick events whose duration comes from the
    actuator; turns last a median of 100 ms (40-260); NONE runs are long;
  - sampled cadences lose 49-89 % of escapes;
  - latched 40 / 100 ms cadences preserve threat response (T1-T6) but inflate turning
    (T7 / O3);
  - no cadence passes the preregistered tolerances.
- **Credit:** the M2.3 rollouts carry about 1 effective independent advantage sample per
  strike at every cadence (0.80 at 20 ms, 1.05 at 200 ms). Abstraction removes redundancy but
  adds no signal: the limit is the strike count, not the decision rate.
- **M2.3 status (conclusion unchanged):** the candidate is a *promising but unconfirmed
  improvement*:
  - EVAL 0.592 vs 0.617, CI [-0.090, +0.040], p = 0.53;
  - unnecessary escapes 5.15 -> 3.02 / min;
  - on the R0 episodes it is only -0.010 below its BC parent (p = 0.86).
- **M2-EVAL-v3 is defined, not generated:**
  - seeds 3,900,000 + 1000 g + k (40 per threat group, 20 per background group);
  - it must be frozen before any M2.4 training;
  - the M2.1 v2 EVAL set is no longer a future holdout.
- Tests: 500 / 500.

**Earlier milestone:** M2.3: PyTorch behaviour cloning + KL-anchored constrained PPO** (approved training; research
only): **complete. Result: NO-GO for human testing (class C).**

- **Branch:** `feature/m2-0-learning-infra` @ `f723375` (worktree `artifacts/worktrees/m2-learning`).
- **Report:** `game/M2_3_PYTORCH_BC_CONSTRAINED_PPO.md` (read sections 1, 3, 6, 8, 10 and 11).
- **Learner audit:**
  - the BC and PPO draft at `7b28591` used handwritten NumPy gradients;
  - they are kept as development evidence only;
  - the official learner is PyTorch (`game/learning/torch_policy.py`, `tools/m2_3_torch.py`):
    torch 2.13.0+cu132, CUDA 13.2, RTX 4060 Laptop, the same 2,315-parameter MLP.
- **PyTorch BC** (`f65c995`):
  - retrained on CUDA from the unchanged teacher dataset;
  - state_dict sha256 `c6c21c23...`;
  - the frozen gate passes: TRAIN-VAL hit 0.677, threat-window escape 0.78, 5.17 unnecessary
    escapes / min, 0.50 perches / min;
  - balanced accuracy 0.43, and escape probability 2e-5 at low DNp01 vs 0.06 at high.
- **Frozen protocol:** `game/learning/m2_3/torch_ppo_protocol.json`, sha256 `3f56c198...`,
  pushed as `76ad1f4` before the official runs:
  - lr 3e-4, chosen from TRAIN-only smokes on seeds 101 / 102;
  - KL anchor to BC, beta 1.0 -> 0.1 between iterations 15 and 45;
  - an adaptive entropy target;
  - a gated dual warm-up;
  - a 1 : 6 background : threat mixture;
  - 60 iterations per seed; seeds 1-5.
- **Runs:**
  - all 5 seeds stayed conditional, with no collapse and no non-finite gradients;
  - lambda_u stayed <= 0.11;
  - 24 of 30 checkpoints are TRAIN-VAL eligible.
- **Selected candidate:** `seed_4/ckpt_it060` (sha256 `b545583e...`, TRAIN-VAL hit 0.490).
- **One-shot EVAL** (the second and last planned use of the M2.1 v2 EVAL set):
  - hit 0.592 (N4B1C 0.617, fixed_maneuver 0.475, no_escape 0.721);
  - threat-window escape 0.86, 3.02 unnecessary escapes / min, 0.78 perches / min;
  - admissible, no flags;
  - paired difference vs N4B1C -0.025, 95 % CI [-0.090, +0.040], p = 0.53. **Not
    meaningful, so NO-GO.**
- **Classification:** C, PPO preserved the BC policy safely but produced no confirmed
  improvement. Sparse strike credit limits sample efficiency: about 800 decisions per strike
  and about 3 % of samples with a meaningful advantage.
- **Timing:** rollout 43.6 s vs GPU update 0.37 s per iteration. The GPU does not accelerate
  MaleCNS or the game.
- **Inspection command (not a GO), in the M2 worktree:**
  `python tools/m2_play_learned.py --checkpoint game/learning/checkpoints/m2_3_candidate.npz --arena room --no-record`.
- Tests: 492 / 492.

**Previous milestones:**

- M2.2: first constrained PPO. NO-GO because of a no-escape collapse.
  - Report `game/M2_2_CONSTRAINED_LEARNED_POLICY.md`.
  - Candidate `2e454a9`: EVAL hit 0.738, never escapes.
- M2.0 / M2.1: infrastructure, and benchmark v2 / reward v2.

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

- **After M2.3 / M2.4-R0 (each option needs an explicit user decision; M2.4-R0 says keep the 50 Hz action contract):**
  1. The same M2.3 method with a much larger rollout budget. This needs a new preregistration
     and a **fresh EVAL set**, because the M2.1 v2 EVAL set has been used twice.
  2. (M2.4-R0: not recommended.) Temporal abstraction: a lower decision rate or macro-actions.
     R0 found no credit benefit.
  - Any future M2.4 candidate must use M2-EVAL-v3, frozen before training.
  3. A criterion change that would accept "hit equal to N4B1C with fewer unnecessary escapes".
  - Do not change the reward first.
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
