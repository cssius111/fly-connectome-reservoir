# Current project state (operational handoff)

This file is an operational handoff for future sessions. It is not a scientific result or
a runtime artifact. Evidence lives in the milestone reports listed below. Update it at the
end of every substantial milestone.

Last updated: 2026-09-25, at the end of M1.8-N4B5 (research complete; runtime approval pending).

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
| `wip/m1-4-enclosure` | the N4B5 research commit (see `git log -1`); N4B4 at `6b5c4ce`, N4B3 at `d09dac4`, N4B2 at `5be0aea` | research branch; research-only commits |
| `feature/m1-8-n4b1c-runtime` | `e3c55b3` | accepted runtime; **do not modify** |
| `archive/m1-8-n2b-rejected` | `2c306174d7bdb4e74b6c5517519ae695bd90cf44` | rejected N2b runtime snapshot; **never merge** |
| `main` | `309abd9` | untouched |
| PR #1 (`wip/m1-4-enclosure` -> `main`) | open | **unmerged; do not merge without explicit approval** |

Research worktrees (git-ignored, under `artifacts/worktrees/`): `n2b-rejected` (detached at
the archive commit), `n4b1c-runtime` (the feature branch), and `n4b1c-runtime-detached`
(detached at `e3c55b3`; used read-only by the N4B2-N4B5 tools). Each has a `data` junction to
`data/`.

## Reporting categories (adopted 2026-09-25, from N4B4)

| Category | Meaning | Criterion |
|---|---|---|
| A | fixed-fly / no-drive neural false escapes | < 0.1/min at 95 % |
| B | inappropriate free-flight escapes (visual input present, behaviourally inappropriate) | < 0.1/min at 95 %, a **provisional working engineering criterion** |
| C | foreshortening-driven escapes (apparent-size / tilt geometry) | tracked; not a failure by itself |
| D | genuine self-approach escapes | tracked; not a failure by itself |

Do not call C or D "false triggers".

## Current research milestone

**M1.8-N4B5: paddle visual geometry and overhead foreshortening** (research only):
**complete. Recommendation 3: a new geometry runtime candidate (G3). Waiting for explicit
user approval; nothing implemented.**

- Report: `game/M1_8_N4B5_PADDLE_VISUAL_GEOMETRY.md` (read the short answer, then sections
  6, 7 and 10).
- Tools: `tools/n4b5_geometry.py` (frozen candidate formulas), `tools/n4b5_analysis.py`,
  `tools/n4b5_resim.py` (in-process re-simulation with a patched `World.visual_half_size`;
  G0 is exact), `tools/n4b5_evaluate.py`.
- Artifacts: `artifacts/m1_8_n4b5/` (git-ignored). `frozen_geometry.json` has sha256
  `a11cafa0...`.
- Previous milestones:
  - N4B4: `game/M1_8_N4B4_FREE_FLIGHT_ESCAPE_INTERPRETATION.md`;
  - N4B3: `game/M1_8_N4B3_SELECTIVE_DNP04.md`;
  - N4B2: `game/M1_8_N4B2_ALTERNATIVE_DN_READOUT.md`.
- **Used data; never reuse for design:**
  - N4B3 holdout: N0 seeds 410000-440149, ROOM seeds 7401-7440;
  - N4B3 development ROOM: seeds 7301-7324;
  - N4B2 holdouts: N0 seeds 310000-340149, ROOM seeds 7201-7212.
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

## Known unresolved limitation

Slow or gradual approach is still detected too late: the N4B1C decoder fires at tick 668 in
the episode-5 slow-close case (N2b session). N4B4 and N4B5 showed that this case's early
signal is an artifact of the bearing-only tilt foreshortening, not a closing approach. Under
the corrected geometry (G3) it has no expansion at all. Documented N4B1C limitation: about
0.08 free-flight escapes/min, about 40 % of them from that artifact. The limitation is
resolved only if the G3 runtime candidate is approved and accepted.

## Do not reopen

- N4B1C tuning: the same-side <= 60 ms rule, summed FAST 2.10, the summed 3-of-5 rule, the
  refractory and the motor semantics. Reopen only if a future milestone demonstrates a
  defect.
- M1.7.1 swatter dynamics and M1.8-A lifecycle (see `AGENTS.md`).
- Frozen experiment artifacts in `artifacts/m1-2/protected-before.json`.
- The N4B2 and N4B3 frozen criteria, and the design of new criteria on any used holdout
  listed above.

## Next permitted actions (decision pending)

N4B5 recommends **3: a geometry runtime candidate G3** (elevation-aware tilt anisotropy):

    f  = edge_on_factor + (1 - edge_on_factor) * face
    f *= 1 - tilt_anisotropy * cos(elevation) * (1 - face) * abs(sin(bearing - orientation))

**It needs explicit user approval before any runtime change.** If approved, a runtime
milestone must:

- implement the change in `World.visual_half_size`, preferably behind an explicit ROOM
  config flag with a version bump;
- keep the N4B1C decoder frozen;
- update the tests that pin retinal geometry;
- re-verify the decoder record and provenance against the new config;
- repeat fixed-fly N0 and no-player free-flight checks at runtime;
- **get a human test of hover responsiveness.**

If not approved, keep G0 and document the artifact (category C is tracked, not failed).

Earlier options are superseded: the N4B2-N4B4 options and the stationary-fly DNp04 path.

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
