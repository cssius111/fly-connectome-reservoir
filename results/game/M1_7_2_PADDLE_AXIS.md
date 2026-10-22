# M1.7.2: line-symmetric paddle axis, validation

Status: **human-accepted on 2026-10-22 (section 5) and frozen in `AGENTS.md`.** The design,
invariant and pass criteria were preregistered in `game/M1_7_2_PADDLE_AXIS_DESIGN.md` (`657e681`,
amendment 1 in `9e32a5d`) before any code was written or any brain was simulated. The
implementation is `b570269`, plus the check tooling in `6237129`.

## 1. Summary

- **The defect is removed in the scripted controls.**
  - **F3, the N4B6 orbit stop.** After the stop the peak apparent-size expansion falls from
    0.352 to 0.001 rad/s. The paddle axis turns by 5.4 degrees in the hold instead of 101.6.
    N4B1C responds in 0 of 48 brain-noise seeds instead of 14.
  - **R1, a reversal on an arc.** The peak falls from 0.530 to 0.019 rad/s, and N4B1C responds
    in 0 of 48 seeds instead of 39.
- **Nothing else moves.**
  - Without the gate, the changed code reproduces every pre-change output bit-for-bit (C1).
  - With the gate, every run is bit-identical to v26 until the first tick in which the line axis
    folds (C2, C3 T1, C5, C6).
  - The paddle's motion, strikes, collision fixtures, lifecycle, recorder and replay are
    unchanged (C4, C6).
- **One preregistered criterion failed as written.** R1's line-axis rotation of at most 10
  degrees did not allow for the arc (amendment 1, recorded before any neural measurement). The
  measured 74.2 degrees is reported.
- **The calibration measurement is not reused exactly.** Every calibration trial folds while the
  paddle travels to its hover point, before the measured window (C2). The threshold is not
  re-derived, as preregistered.
  - The single-sample no-loom statistic is higher under v27 in all three seed sets examined.
  - The runtime N4B1C decoder escapes in none of those 84 no-loom trials under either
    configuration.

## 2. The change

Section 3 of the design note has the full rule.
- `PhysicalSwatter` keeps a world-only line axis next to the unchanged heading tracker
  `swatter.orientation`.
- The line axis takes the tracker's target, gain and limits. It folds a steering error above
  90 degrees to the opposite direction, and it holds its own value where the tracker holds its
  own.
- `World.paddle_axis` feeds the tilt term and the sprite.
- The gate is `swatter.directional.paddle_axis = line_symmetric_v1`, in ROOM only (ROOM
  `config_version` 27).
- The transfer record is `results/game/calibration_room_m1_7_2.json`, written by
  `tools/m1_7_2_axis_record.py`.

## 3. Results

All runs use the same code. v26 is the ROOM configuration at tag `v1.0`; v27 is the working
file. Outputs are under `artifacts/m1_7_2/` (git-ignored).

### C1. Code-only identity (pass)

These runs use the changed code with the v26 configuration, in a separate worktree. The
baselines are from the unchanged code at `657e681`.

| Check | Result |
|---|---|
| `tools/kinematics_trace.py`, 7 scenarios (ROOM, GAME, LAB) | bit-identical, random-stream states included |
| `tools/approach_sanity.py` controlled fixtures | equal to `results/game/approach_m1_7_1.json` |
| `tools/escape_cruise_study.py` | identical |
| `tools/session_sanity.py` | exact replay of 1200 ticks; every tick hash equal to the baseline recording |
| `tools/lifecycle_sanity.py` | three scenarios, exact replays |

### C2. Invariant (pass); calibration reuse not exact

`tools/m1_7_2_axis_checks.py trace` and `... calibration`:

| Run | First fold tick | First difference tick | Bit-identical | Invariant |
|---|---|---|---|---|
| room_quiet (paddle parked) | none | none | yes | holds |
| room_perched_threat (chase from tick 240) | 240 | 240 | no | holds |
| room_approach_threat (chase from tick 10) | 10 | 10 | no | holds |
| room_airborne_seed101 (paddle parked) | none | none | yes | holds |
| room_no_ecology (paddle parked) | none | none | yes | holds |
| calibration protocol, 56 trials | in all 56, always during the settle | 54 trials differ | 2 of 56 | holds |

In the calibration protocol the paddle travels from its reset position to the hover point.
The line axis starts at the tracker's 0 rad. On that travel it either takes the nearer line
direction or folds the stop overshoot. The settled axes then differ by 64.5 degrees, modulo 180.
- In the 28 no-loom trials the measured window and the last second of the settle carry no
  apparent expansion under either configuration: the Retina expansion is 0.000 rad/s. The
  encoder drive of a static paddle is zero under both, because `encoder.loom_size` is 0 and the
  chase channel is off.
- The DNp01 traces still differ. The brain ran through a settle with a different input, and its
  spike trains then diverge.
- The loom trials also fold inside the window, when the paddle returns after the strike.

Descriptive statistics of the calibration rule (not used to re-derive anything):

| | v26 | v27 |
|---|---|---|
| No-loom DNp01 peak | 1.376 | 2.074 |
| No-loom ticks at or above 1.45 | 0 | 2 |
| Loom trials detected at 1.45 | 28 of 28 | 28 of 28 |
| Median latency at 1.45 | 0.08 s | 0.08 s |
| Grid value the calibration rule would pick | 1.40 | 2.10 |

Under other reset seeds (exploratory, not preregistered) the geometry of these trials stays the
same and only the brain noise changes.

| No-loom trials | Peak | Ticks at or above 1.45 | N4B1C escapes |
|---|---|---|---|
| v26, calibration seeds 4000-4027 | 1.376 | 0 | 0 |
| v26, seeds 4100-4127 | 1.712 | 2 | 0 |
| v26, seeds 4200-4227 | 1.111 | 0 | 0 |
| v27, calibration seeds 4000-4027 | 2.074 | 2 | 0 |
| v27, seeds 4100-4127 | 2.002 | 2 | 0 |
| v27, seeds 4200-4227 | 2.000 | 4 | 0 |

- **The single-sample statistic.** v26 crosses 1.45 under one other seed set as well. v27 is
  higher in all three sets: 8 ticks against 2 in 84 trials, which is not significant on its own
  (one-sided P about 0.055) but consistent in direction. It is not a static-stimulus effect,
  because the settled paddle's mean apparent angle is 0.519 rad under v27 and 0.523 under v26,
  and its encoder drive is zero under both. It is carried by the brain state that the different
  settle leaves.
- **The runtime decoder.** The N4B1C decoder replayed on the same left and right traces escapes
  in none of the 84 no-loom trials under either configuration.

N0 measured 1.30 false escapes per minute at 1.45 under the single-sample criterion (Part III of
the technical report), which is why the runtime no longer uses it.

The record therefore states `exact_reuse: false`, and the threshold stays 1.45, carried over as
for N4B5R.

### C3. Scripted controls (functional criteria pass; one criterion failed as written)

These runs use fixed-fly-v2 with ecology off and the 48 N4B6 brain-noise seeds. The paddle
geometry is the same in every seed.

| | F3 v26 | F3 v27 | R1 v26 | R1 v27 |
|---|---|---|---|---|
| Peak size-driven expansion after the stop / reversal (rad/s) | 0.352 | **0.001** | 0.530 | **0.019** |
| Peak size-driven expansion before it (rad/s) | 0.001 | 0.001 | 0.004 | 0.004 |
| Axis rotation in the hold (degrees) | 101.6 | **5.4** | 169.3 | 19.0 |
| Axis rotation from the window start to the end (degrees) | 101.6 | 5.4 | 196.0 | 74.2 |
| Peak deviation of the axis from the motion line while moving (degrees) | - | - | 87.5 | 31.3 |
| Seeds with an N4B1C response after the window start | 14 / 48 | **0 / 48** | 39 / 48 | **0 / 48** |
| Seeds with a response before it or in the pre-hold | 0 / 48 | 0 / 48 | 0 / 48 | 0 / 48 |
| Folded ticks | 0 | 14 | 0 | 53 |

- **Sanity of v26.** F3 reproduces N4B6: 0.35 rad/s after the stop, and responses 0.46-0.64 s
  after it (N4B6: 17 of 48 seeds, 0.44-0.64 s). In R1 the tracker spins by 196 degrees after
  the reversal.
- **Tracker unchanged.** In v27 the heading tracker turns exactly as in v26 (101.6 and 196.0
  degrees), so the strike direction keeps its accepted behaviour.
- **Preregistered criteria.**
  - F3: size rate at most 0.1 rad/s, pass; hold rotation at most 10 degrees, pass; at most
    2 of 48 responses, pass.
  - R1: size rate, pass; responses, pass. Line-axis rotation at most 10 degrees, **failed as
    written** (74.2 degrees); amendment 1 explains it.
- **T1, a 60-degree turn without a stop** (world only): bit-identical over 100 ticks, with no
  folded sub-step. Pass.

### C4. Strikes (pass)

- The calibration loom trials and the session_sanity scenario (strikes at ticks 100 and 300)
  follow the invariant (C2 and C6).
- The loom detection statistics at 1.45 are unchanged: 28 of 28 detected, median 0.08 s.
- The approach_sanity fixtures are unchanged under v27 (C6), because the line axis does not feed
  back into the paddle's motion.

### C5. Free flight without a player

Seeds 9201-9210, 180 s each, with the pointer parked as in `tools/b2b_iii_free_flight_check.py`:
**all 10 seeds are bit-identical between v26 and v27, with no folded sub-step and no escape in
either configuration. Pass.**
- The pointer is parked at the paddle's reset position, so the paddle never travels and cannot
  fold. The four seeds completed before a container restart were carried over from the run log;
  each logged result is complete, and none had an escape.
- This check confirms that the change leaves no-player flight untouched. It is not an escape-rate
  measurement.

### C6. Frozen systems under v27 (pass)

| Check | Result |
|---|---|
| `tools/approach_sanity.py` controlled fixtures | equal to `results/game/approach_m1_7_1.json` |
| `tools/escape_cruise_study.py` | identical to the pre-change output |
| `tools/session_sanity.py` | v27 recording (schema 4, config 27) replays exactly over 1200 ticks |
| `tools/session_sanity.py`, v26 against v27 | first fold at tick 0, first difference at tick 1 (the Retina reads the previous tick), so the invariant holds; the line-axis keys appear only in the v27 recording |
| `tools/lifecycle_sanity.py` | three scenarios, exact replays |
| Test suite | 507 of 507 pass on Linux |

## 4. Deviations

1. **R1 line-axis rotation criterion.** The criterion was misspecified for an arc and failed as
   written. Amendment 1 recorded this before any neural measurement. The functional criteria are
   unchanged and pass.
2. **Calibration reuse.** The reuse is not exact, because every calibration trial folds during the
   settle. The preregistration allowed for this outcome, and the record says so.
3. **T1 in the first geometry run.** The world-only run that preceded the checks added a stop after
   the turn, and the first fold came at that stop. The check ran T1 as preregistered, without a
   stop.
4. **Check tooling.** The descriptive calibration statistics, the resampling of no-loom seeds and
   the N4B1C replay on them were added after the first C2 run had shown the folds. They are
   exploratory and descriptive only.
5. **Two scope tests rebound.** As was done for N4B5R, each now isolates its own change.
   - The lifecycle's fixed-fly comparison (`test_game_lifecycle.py`) also uses the heading axis.
   - The N4B5R scope test (`test_game_n4b5r_geometry.py`) drops the two paddle-axis keys.
   - The keys are versioned in `test_game_m1_7_2.py`.

## 5. C7, human acceptance (accepted 2026-10-22)

The user played one recorded ROOM session under v27: `20261022T155418.491485Z-0da3f079`
(commit `b10ba2c`, config 27, local Windows checkout).
- The play was aggressive: 160.5 s, 12 episodes, 21 strikes, 12 hits.
- The paddle was parked for only 8.9 s of the airborne time.
- The checkout was dirty only through the two local files noted in earlier playtests.

`tools/stop_rotation_audit.py` reads the recorded line axis.

| | This session (line axis) | Accepted runtime before M1.7.2 |
|---|---|---|
| Hover | 1.5 min | 5.4 min |
| Stop-rotation transients | 3 (2.01 per hover minute) | 25 (4.65 per hover minute) |
| Reversal spins | 0 | 12 (2.23 per hover minute) |
| Transients evaluated | 0: each fell within 1 s after an escape onset | 10 |
| Escapes added by transients over the matched baseline | 0.0 | 3.4 (0.63 per hover minute) |

`tools/playtest_flight_summary.py` labels the 59 escapes as follows. The one self-approach was a
weak stimulus (0.016 rad over 120 ms at 214 units, the paddle in its approach phase), and a
single case shows no pattern.

| Label | Escapes |
|---|---|
| The paddle moved toward the fly | 49 |
| Strike in progress | 8 |
| Size-dominated | 1 |
| Fly-driven self-approach | 1 |

**The user's judgement.**
- Moving the paddle sideways and reversing no longer turns it by half a circle, and the handle
  stays on the same side.
- The fly's reactions are reasonable.
- The difficulty is about the same as before.

The user accepted M1.7.2.

**Two further observations from the same playtest, outside M1.7.2.**
- **Escape direction line.** The green line drawn from the fly at an escape onset told the
  player the dash direction before the fly had moved. The user chose to remove the line and keep
  the ring that shows an escape fired (`game/app.py`). This is rendering only: no simulation
  state, recording or replay changes.
- **Swept strike corridor.** The lethal corridor is the paddle disc swept over the 0.1 s active
  contact, from about 1.3 body lengths of drag for a slow click to about 13 at the speed cap.
  It is the frozen M1.7.1 design, and the user chose to keep it frozen rather than change it for
  difficulty.
