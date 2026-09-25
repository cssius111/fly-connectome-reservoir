# M1.8-N4B5R: elevation-aware paddle visual geometry (runtime candidate)

Status: **accepted and frozen after human review (2026-09-25).** Branch
`feature/m1-8-n4b5r-geometry`, created from the accepted N4B1C runtime
(`e3c55b36084cd1d05e5f38d0b178aed0b9a59ddf`). See section 8 for the acceptance record.

This milestone implements the G3 candidate of M1.8-N4B5 (research commit `0e9d2d9`,
`game/M1_8_N4B5_PADDLE_VISUAL_GEOMETRY.md` on `wip/m1-4-enclosure`). The accepted N4B1C
decoder (`lateral_dual_path_v1`) is unchanged:

- same-side <= 60 ms rule;
- summed FAST 2.10;
- sustained 3 of 5 at 1.45;
- 0.4 s refractory;
- unchanged motor semantics.

Not changed: whitelist, Retina timing, LC4/LPLC2 encoder, MaleCNS, brain noise, physics,
escape impulse, lifecycle and recorder schema.

## 1. The change

`game/world.py`, `World.visual_half_size`, gains a geometry mode read from
`swatter.directional.tilt_geometry`:

| Mode | Formula (face-dependent base `f = e + (1 - e) face` unchanged) |
|---|---|
| `bearing_only_v0` (**default when absent**; the accepted M1.5 / M1.7 formula) | `f *= 1 - tilt_anisotropy (1 - face) abs(sin(bearing - orientation))` |
| `elevation_aware_tilt_v1` (M1.8-N4B5R) | `f *= 1 - tilt_anisotropy cos(elevation) (1 - face) abs(sin(bearing - orientation))`, with `cos(elevation) = horizontal / 3-D fly-paddle distance` (0 when both are 0) |

- An unknown mode raises `ValueError` when the World is built.
- The mode affects only the Retina's paddle apparent size; nothing else reads
  `visual_half_size`.
- **Scope: ROOM only.**
  - `game_room_config.json` sets `elevation_aware_tilt_v1` (config_version 16 -> 17).
  - GAME (`game_play_config.json`) and LAB (`game_config.json`) carry no flag, so they keep
    `bearing_only_v0` bit-for-bit.
- `bearing_only_v0` stays available for regression comparison: set the flag in any
  configuration.

Files changed:

| File | Change |
|---|---|
| `game/world.py` | `TILT_*` constants, mode validation, the elevation-aware branch (+23 lines) |
| `game/session.py` | diagnostic hint only: a provenance mismatch under the new geometry names `tools/n4b5r_geometry_record.py` (+5 lines; no decoder or loading logic changed) |
| `game_room_config.json` | `config_version` 17; `swatter.directional.tilt_geometry` plus its comment; `policy.calibration_paths` and `policy._comment` point to the new record |
| `results/game/calibration_room_m1_8_n4b5r.json` | **new** geometry runtime-candidate provenance record |
| `tools/n4b5r_geometry_record.py` | new: builds that record, and refuses unless the config differs from the accepted N4B1C config only in the geometry flag and record path, and the decoder block is identical |
| `tools/n4b5r_runtime_validation.py` | new: runtime validation (below) |
| `test_game_n4b5r_geometry.py` | new: 13 tests (geometry invariants, ROOM-only scope, versioning, provenance) |
| `test_game_n4b1c_decoder.py`, `test_game_lifecycle.py` | 6 tests adapted, below |

## 2. Provenance

The N4B1C decoder record fingerprints the whole ROOM configuration, so the geometry
configuration needs its own record: `results/game/calibration_room_m1_8_n4b5r.json`
(`record_kind` `geometry-runtime-candidate-provenance-v1`). It states:

- `decoder_unchanged: true`, `not_a_decoder_recalibration: true`, `geometry_changed: true`;
- `escape_decoder` and `parameter_basis`: copied byte-for-byte from the N4B1C record;
- `geometry`: mode, formula, previous formula, ROOM-only scope, reason (correction of the
  overhead tilt-foreshortening artifact), research origin (M1.8-N4B5 G3, commit `0e9d2d9`,
  frozen-geometry hash, and content hashes of the research files at that commit);
- `decoder_record`: the N4B1C record path, its content sha256, and `modified: false`;
- `measurement_reuse.changed_config_paths` =
  `[config_version, policy._comment, policy.calibration_paths, swatter.directional._tilt_geometry_comment, swatter.directional.tilt_geometry]`.

**The N4B1C decoder record is not modified.** It still resolves for the accepted N4B1C ROOM
configuration (`git show e3c55b3:game_room_config.json`). Switching the ROOM geometry mode
back to `bearing_only_v0` invalidates the new record ("No matching"): the geometry mode is
bound into provenance.

## 3. Tests

- **427 / 427 pass:** the 414 existing tests plus 13 new ones.

Six existing tests pinned the accepted state that this candidate changes. They were adapted
without weakening them:

| Test | Adaptation |
|---|---|
| `test_game_n4b1c_decoder`: `test_room_resolves_the_n4b1c_record`, `test_record_is_decoder_provenance_not_a_scalar_calibration`, `test_room_config_differs_from_the_baseline_only_in_the_decoder` | now check the N4B1C record and diff against the **accepted N4B1C config** (`e3c55b3`), which is what they protected; the new geometry config is versioned in the new test file |
| `test_game_lifecycle`: `test_stale_ignored_calibration_cannot_override_matching_record` | uses ROOM's active record path, now the N4B5R record |
| `test_game_lifecycle`: `test_calibration_transfer_only_changes_inactive_protocol_fields` | also ignores the two new tilt-geometry keys (versioned elsewhere); additionally checks that the N4B5R record names the N4B1C record by content hash |
| `test_game_lifecycle`: `test_fixed_fly_protocol_neural_outputs_are_identical` | the lifecycle-invariance comparison now uses ROOM with `bearing_only_v0`. The new geometry legitimately changes the Retina for this nearly overhead strike (offset 18 units), which is exactly the case G3 corrects |

## 4. Automated validation

All runs use this branch's runtime code: `tools/n4b5r_runtime_validation.py`, outputs in
`artifacts/m1_8_n4b5r/`, git-ignored. The decoder is the live runtime `FixedEscapePolicy`,
or its exact replay on DNp01 traces.

**Regression anchor.** Every re-simulation of old data was also run with
`bearing_only_v0`, which must reproduce the original record exactly:

| Harness under `bearing_only_v0` | Result |
|---|---|
| N1 (300 trials, config 76806f0 + flag) | 300 / 300 DNp01 traces identical to the recorded N1 |
| fixed-fly N0 (150 x 1400 ticks) | 150 / 150 identical |
| both human sessions, open loop | 7025 / 7025 and 4130 / 4130 DNp01 rows identical |

| # | Check | Result |
|---|---|---|
| A | full test suite | **427 / 427 OK** |
| B | protected files (`artifacts/m1-2/protected-before.json`) | 20 / 20 match in the candidate worktree |
| C | `verify_results.py` | passes (frozen weights verified). The fresh worktree first checked out three protected source files with CRLF endings, which made the raw-byte check fail. They were re-checked out with LF (content identical to `e3c55b3`), and the git-ignored reference artifacts were linked in. |
| D | N1 (G3) | strong_direct **60 / 60, median 0.08 s, p95 0.08**; medium_committed **60 / 60, 0.10 / 0.10** (bearing-only: 0.08 / 0.10, identical). Descriptive: weak 30, glancing 36, aborted 44 of 60 (bearing-only 33 / 30 / 49) |
| E | fixed-fly N0, 70 min | **0 N4B1C events** (95 % upper 0.043/min) under G3, and 0 under bearing-only |
| F | all 83 no-player ROOM runs, 249 min, closed loop | see section 5 |
| G-K | both human recordings, open loop, 5 brain-noise realizations | direct strikes **38-39 / 39**, median after the click **0.08-0.10 s**; strike-phase escapes **28-29 / 29**; hover bouts **24-25 / 33**; far perched non-contact approach: **silent** in 5 / 5; voluntary takeoff: **silent** in 5 / 5 |
| L | recorder schema / exact replay | a new recording under this config: schema 4, config_version 17, `tilt_geometry` recorded in the manifest, recorded diagnostics keys unchanged (`behavior_state`, `escape_strength`, `escape_threshold`, `refractory_seconds`); **replay exact, 550 / 550 ticks**. Existing human recordings (config versions 14 and 15, no flag) replay **exactly** (9387 and 4791 ticks) |
| M | overhead synthetic passes (200 units/s under a parked paddle, crossing 90 deg) | peak theta_dot at offsets 0 / 2 / 10 / 25 / 50 units: bearing-only **6.86 / 6.13 / 2.52 / 1.07 / 0.53** rad/s; G3 **0.17 / 0.17 / 0.17 / 0.16 / 0.16**. Strike-like (face 0 to 1) peak theta_dot identical: 6.76 / 3.71 / 2.17 |
| N | seed 7201 | the accepted runtime's overhead escape (tick 3563, foreshortening-driven) no longer occurs. The run's only escape is a weak category-B event at tick 266 |
| O | episode 5 (N2b session), clean start at 610 | bearing-only fires at **668**, before the click, on the overhead-foreshortening "final loom". G3 fires at **674**, 0.10 s after the click at 669, on the real strike. The 610-613 "slow-close" signal no longer produces an escape |

**Human-replay reference, bearing-only, over five realizations (N4B5):**

- direct strikes 38-39 / 39, median 0.08-0.10 s;
- strike-phase escapes 28-29 / 29;
- hover bouts: 33 / 33 in the recorded realization (by construction), 24-28 in the other
  four.

The candidate's hover loss is confined to bouts whose recorded signal came mainly from the
overhead-foreshortening term (N4B5 section 7).

## 5. Free flight (accepted N4B4 metric split)

The same 83 seeds and thread counts as N4B4 / N4B5, 249 simulated minutes, under the live
runtime. Category B uses a counterfactual replay of every escape: escape withheld for 2 s.

| Category | Accepted runtime (bearing-only) | **Candidate (G3)** |
|---|---|---|
| A fixed-fly / no-drive neural false escapes | 0 | **0** |
| B inappropriate free-flight escapes (provisional < 0.1/min) | 2 (0.008/min, upper 0.025) | **3 (0.012/min, upper 0.031)** |
| C foreshortening-driven | **8** | **0** |
| D genuine self-approach | 8 | 5 |
| mixed | 3 | 4 |
| all | 21 (0.084/min, upper 0.121) | **12 (0.048/min, upper 0.078)** |

- The candidate's 12 escapes (seed and tick) are identical to the frozen research G3
  evaluation: the runtime implementation reproduces the research candidate.
- **C drops to zero, A does not worsen, B stays well inside the working criterion.**
- D (5 against 8) is a closed-loop realization difference: the self-approach expansion is
  range-driven and unchanged by G3 (N4B5 section 5).
- **Escape direction:** 11 / 12 candidate escapes move away from the paddle's side, by
  azimuth sign. The accepted runtime's free-flight escapes do so in 19 / 21. The one
  exception (seed 7437) is a weak category-B event whose DNp01 contrast pointed the other
  way. The direction logic is unchanged decoder code.

## 6. Launch command for the human test

From the candidate worktree, using the main virtual environment (PowerShell). The
recording goes to the usual session folder:

    Set-Location D:\Projects\flybrain-lab\artifacts\worktrees\n4b5r-geometry
    & D:\Projects\flybrain-lab\.venv\Scripts\python.exe -m game.app --arena room --record --record-dir D:\Projects\flybrain-lab\results\game\sessions

For a fixed seed or a window, add for example `--seed 255 --windowed`. A headless smoke run
(`--smoke 3 --no-record`) starts cleanly.

## 7. Human-test focus

1. Direct attacks still feel immediate.
2. Hover and chase still feel responsive enough.
3. Overhead passes no longer trigger obviously artificial escapes.
4. Escape direction is normal.
5. No unexplained new behaviour.

**The tradeoff to judge:** less artifact-driven hover responsiveness against more
physically plausible visual geometry.

- Offline, hover bouts whose recorded signal came mainly from the old overhead
  foreshortening are detected less often (N4B5: 0.91 to 0.58).
- Range-driven hover bouts are unchanged or better (0.74 to 0.84).
- A human test will feel this mainly as fewer escapes while the paddle hovers directly
  over the fly without moving closer.

No retuning after the human test unless there is a clear failure.

## 8. Human acceptance (2026-09-25)

The human test was completed and the candidate was **accepted as-is**:

- **Geometry candidate accepted:** `elevation_aware_tilt_v1` (the bearing-based tilt term
  multiplied by `cos(elevation)`), ROOM only, config_version 17.
- **No further tuning requested.** The geometry and all parameters are frozen at the values
  in this report.
- **Direct-strike behaviour accepted.**
- **Hover / chase tradeoff accepted:** fewer escapes while the paddle hovers over the fly
  without closing, in exchange for physically plausible visual geometry.
- **Overhead foreshortening artifact correction accepted.**
- **The N4B1C decoder (`lateral_dual_path_v1`) remained unchanged.** Its record
  `results/game/calibration_room_m1_8_n4b1c.json` is not modified.

Final pre-commit check, on the unchanged candidate files (no source file was modified after
the automated validation in section 4):

| Check | Result |
|---|---|
| full test suite | 427 / 427 OK |
| protected files (`artifacts/m1-2/protected-before.json`) | 20 / 20 match (working copies of four protected files had been re-expanded to CRLF by `core.autocrlf`; they were re-checked out with LF, committed content unchanged) |
| `verify_results.py` | passes (`frozen_weights_verified: true`) |
| headless smoke run (`--arena room --smoke 3 --no-record`) | starts and exits cleanly |

This milestone is now the accepted runtime baseline. Future changes to the geometry follow
the same rule as other frozen milestones: reopen only if recorded evidence demonstrates a
real defect.
