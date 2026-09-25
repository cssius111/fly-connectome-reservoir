# Current project state (operational handoff)

This file is an operational handoff for future sessions. It is not a scientific result or
a runtime artifact. Evidence lives in the milestone reports listed below. Update it at the
end of every substantial milestone.

Last updated: 2026-09-24, at the end of M1.8-N4B4 (research complete; decision pending).

## Start of a new session

1. Read this file.
2. Read the current milestone report (below).
3. Run `git status`, `git branch -vv` and `git log --oneline -10`.

Do not ask the user to reconstruct old context unless the repository conflicts with this
file.

## Accepted and frozen runtime

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
| `wip/m1-4-enclosure` | the N4B4 research commit (see `git log -1`); N4B3 at `d09dac4`, N4B2 at `5be0aea` | research branch; research-only commits |
| `feature/m1-8-n4b1c-runtime` | `e3c55b3` | accepted runtime; **do not modify** |
| `archive/m1-8-n2b-rejected` | `2c306174d7bdb4e74b6c5517519ae695bd90cf44` | rejected N2b runtime snapshot; **never merge** |
| `main` | `309abd9` | untouched |
| PR #1 (`wip/m1-4-enclosure` -> `main`) | open | **unmerged; do not merge without explicit approval** |

Research worktrees (git-ignored, under `artifacts/worktrees/`): `n2b-rejected` (detached at
the archive commit), `n4b1c-runtime` (the feature branch), and `n4b1c-runtime-detached`
(detached at `e3c55b3`; used read-only by the N4B2-N4B4 tools). Each has a `data` junction to
`data/`.

## Current research milestone

**M1.8-N4B4: interpretation of the accepted N4B1C free-flight escapes** (research only):
**complete. Decision: keep N4B1C frozen and document a limitation. One separate modelling
question is pending for the user** (see "Next permitted actions").

- Report: `game/M1_8_N4B4_FREE_FLIGHT_ESCAPE_INTERPRETATION.md` (read the short answer,
  then sections 3, 6 and 9).
- Tools: `tools/n4b4_replay.py` (deterministic reconstruction and counterfactual replay),
  `tools/n4b4_analysis.py`, `tools/n4b4_figures.py`.
- Artifacts: `artifacts/m1_8_n4b4/` (git-ignored, including a figures review set).
- Previous milestones:
  - N4B3: `game/M1_8_N4B3_SELECTIVE_DNP04.md`;
  - N4B2: `game/M1_8_N4B2_ALTERNATIVE_DN_READOUT.md`.
- **Used data; never reuse for design:**
  - N4B3 holdout: N0 seeds 410000-440149, ROOM seeds 7401-7440;
  - N4B3 development ROOM: seeds 7301-7324;
  - N4B2 holdouts: N0 seeds 310000-340149, ROOM seeds 7201-7212.
  - N4B4 generated no new scenario data. It only re-simulated stored runs.

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
  - Proposed metric split:
    - no-loom neural false escapes (M1): N4B1C upper 0.0077/min;
    - inappropriate free-flight escapes (M2): upper 0.025/min;
    - visual-artifact escapes (M3) and legitimate self-approach escapes (M4): tracked.

## Known unresolved limitation

Slow or gradual approach is still detected too late: the N4B1C decoder fires at tick 668 in
the episode-5 slow-close case (N2b session). N4B4 showed that this case's early signal is
apparent-size change from bearing-only tilt foreshortening while the paddle hovers overhead,
not a closing approach. Documented N4B1C limitation: about 0.08 free-flight escapes/min,
about half from self-approach and about half from the same foreshortening effect.

## Do not reopen

- N4B1C tuning: the same-side <= 60 ms rule, summed FAST 2.10, the summed 3-of-5 rule, the
  refractory and the motor semantics. Reopen only if a future milestone demonstrates a
  defect.
- M1.7.1 swatter dynamics and M1.8-A lifecycle (see `AGENTS.md`).
- Frozen experiment artifacts in `artifacts/m1-2/protected-before.json`.
- The N4B2 and N4B3 frozen criteria, and the design of new criteria on any used holdout
  listed above.

## Next permitted actions (decision pending)

N4B4 decision: **keep N4B1C frozen and document the limitation** (no runtime change).
Pending user decisions, each needing explicit approval:

1. **Visual-geometry review milestone:** decide whether the bearing-only tilt foreshortening
   in `World.visual_half_size` (`swatter.directional.tilt_anisotropy`, from `58ffd60`) is a
   defect, for example whether it should fade with elevation. This is a Retina/World
   modelling change that may touch M1.7-era swatter geometry. It needs its own milestone
   with before/after validation of N0, N1, human replays and free flight.
2. **Adopt the proposed metric split (M1-M4)** for future acceptance reports. No threshold
   has changed yet.
3. **Narrow stationary-fly DNp04 path** (from N4B3). This is a whitelist expansion and is
   not recommended now.

Superseded: the N4B2 options, and the N4B3 option "characterize N4B1C's free-flight
escapes", which N4B4 has done.

## Permitted without asking

- Offline research tools, re-simulation, analysis and reports on `wip/m1-4-enclosure`.
- Research-only commits and pushes to `wip/m1-4-enclosure`.

## Requires explicit user approval

- Any runtime behaviour change (`game/action.py`, `game/session.py`, ROOM config,
  calibration records, recorder schema).
- **Expanding the policy observation whitelist** (for example adding DNp04).
- Changing biological model parameters, Retina or encoder equations, noise or physics.
- Merging branches or PRs, rewriting Git history, or modifying `feature/m1-8-n4b1c-runtime`.
- Choosing between materially different product or scientific directions.
