# M3.4: retinotopic LPLC2/LC4 drive, results

Status: **measurement complete on 2026-10-24. V2 failed at one of its three l/v values and V8a
at one of its four, so under the preregistered decision rule the v30 configuration is not a
playtest candidate.**
- **Configuration.** As the rule requires, the ROOM configuration is restored to v27. The tested
  v30 candidate stays in git history at `10e12f6`.
- **What is kept.** Its record, the `retinotopic_v1` encoder mode, `Retina.elevation` and the
  receptive-field build tool stay in the code. No configuration uses the mode, and the other
  modes ignore `elevation`.
- **Tuning.** Nothing was tuned after the scale was calibrated.

**Sources:**
- Preregistration: `game/M3_4_RETINOTOPIC_DRIVE_DESIGN.md`
  - preregistered in `790d6d4`;
  - authorization recorded in `a6c7e13`.
- Research note: `game/M3_4_RETINOTOPIC_DRIVE_RESEARCH.md`.
- Tools:
  - `tools/m3_4_retinotopic.py`: calibration, V1-V5, V8, D1 and D2;
  - `tools/m3_2_threat_matrix.py`: V6a;
  - `tools/paired_free_flight_check.py`: V6b;
  - `tools/build_receptive_fields.py`: the receptive-field table.
- Configuration and record: the v30 candidate `game_room_config.json` at `10e12f6` and
  `results/game/calibration_room_m3_4.json`. The working configuration is v27.
- Receptive-field table: `data/receptive_fields_v1.npz`, built locally, content digest
  `f75cfca9e565d254923dcbd4d3893605f1db7071171ef9ace482443f38da7c86`. A second build reproduced
  it exactly.
- Raw data: `artifacts/m3_4_run/` (git-ignored).

## 1. Summary

| Check | Result | Criterion | Outcome |
|---|---|---|---|
| Calibration | 71.3 V/mV, squared error 614 ms² | admissible at every l/v, smallest error | chosen |
| V1 primary: E2 | implied threshold **56.5°** (v27: 18.6°, M3.3: 38.2°, real fly 54°) | partial or match (34-74°) | **pass** (match) |
| V1: E1 | 0.94 (real fly 0.82) | at least partial | **pass** (partial) |
| V2 start size | **l/v 40 ms: spread 64.8°**; 80 ms: 3.9°; 160 ms: 3.0° | within 10° | **fail** |
| V3 held-out l/v | 15 ms: 24.9 ms off; 30 ms: 12.8 ms off; 60 ms: 13.2 ms off | within 30 ms | pass |
| V4 non-looming disks | 0 escapes in 120 trials | at most 1 | pass |
| V5 spontaneous | 0 in 768 s | none | pass |
| V6a threat matrix | **no escape in any of the 15 trajectories** (720 trials); v27 escapes B2 in 1.00 | descriptive | see section 5 |
| V6b no-player flight | 0 escapes against 9 in 240 minutes each | not more than baseline | pass |
| V7 tests | 557 of 557 pass (556 on the v30 candidate) | all pass | pass |
| V8a left-right, V1 | 10 ms: **right 42, left 31 of 48 (0.23)**; 20, 40, 80 ms: equal | at most 0.20 | **fail** |
| V8b left-right, calibration stimulus | 0.13, 0.04 and 0.00 at l/v 20, 40 and 80 ms | at most 0.20 | pass |

**Outcome.**
- **What passed.** M3.4 brings the timing law into the real fly's band: an implied threshold of
  56.5° against 54°, with alpha 1.86 against 2.0. It passes V3, which M3.3 failed.
- **What failed.** It fails twice, both at a single l/v:
  - the start-size invariance at l/v 40 ms (V2);
  - the left-right symmetry of the fastest loom, l/v 10 ms (V8a), by 0.03 beyond the tolerance.

## 2. Calibration

The grid ran from 10 to 320 V/mV in 31 geometric steps, on seeds 600001-600024, with the paper's
10-90° stimulus at azimuth 50°, elevation 11°. Every value was admissible. The values with the
smallest errors:

| Scale (V/mV) | Squared error (ms²) | l/v 10 ms | 20 ms | 40 ms | 80 ms |
|---|---|---|---|---|---|
| 31.7 | 1466 | 0.88, +6 | 0.83, -9 | 1.00, -57 | 1.00, -164 |
| 40 | 1438 | 0.83, +16 | 0.79, -9 | 1.00, -57 | 1.00, -174 |
| 63.5 | 1516 | 0.75, +26 | 0.79, -9 | 1.00, -67 | 1.00, -174 |
| **71.3** | **614** | 0.75, +6 | 0.79, -9 | 1.00, -77 | 1.00, -174 |
| 80 | 898 | 0.75, +16 | 0.88, -9 | 1.00, -77 | 1.00, -194 |
| 89.8 | 656 | 0.71, +6 | 0.96, -9 | 1.00, -87 | 1.00, -194 |

Each cell gives the escape fraction and the median escape time in ms relative to collision. The
targets are -2, -30, -81 and -184 ms.

- **Shape of the error.** As the exploration predicted (design section 4.1), the error falls
  steeply up to about 30 V/mV and is lumpy above it, because times step in 20 ms ticks. The
  minimum at 71.3 lies inside the grid.
- **The fast looms.** At l/v 10 and 20 ms the median escape falls at or just after the end of the
  expansion (90°), whatever the scale. The l/v 20 ms escape is always 21 ms later than the
  target.

## 3. V1: the M3.0 scorecard on v30

| Metric | v27 | M3.3 (v29) | M3.4 (v30) | Real fly | Class (v30) |
|---|---|---|---|---|---|
| E1 escape probability (lateral) | 1.00 | 0.83 | **0.94** (361 of 384) | 0.82 | partial |
| E2 timing law | alpha 6.1, threshold 18.6° | alpha 2.89, delta -43 ms, threshold 38.2° | **alpha 1.86, delta -43 ms, threshold 56.5°** | alpha 2.0, -6 ms, 54° | **match** |
| E3 escape before collision at l/v 10 ms | 100 % | 0 % | 0 % | 30 % short mode, 6 % long mode | - |
| E4 direction, side threats | -66.7° / +65.6° | -69.2° / +67.2° | -68.0° / +65.7° | ∓45° | match |
| E4 direction, front | as right | as right | +4.5° | backward, 180° | gap |
| E4 direction, rear | as right | as right | -11.5° (27 escapes) | forward, 0° | match |
| E6 spontaneous escapes | 0 | 0 | 0 | - | - |

Per condition (48 trials each; mean size at escape):

| l/v | Right | Left | Front | Rear |
|---|---|---|---|---|
| 10 ms | 42, after collision | 31, after collision | 43, after collision | 0 |
| 20 ms | 48, 149° (28 before collision) | 48, 178° (2) | 48, 178° (1) | 2, after collision |
| 40 ms | 48, 101° (47) | 48, 136° (35) | 48, 157° (24) | 9, after collision |
| 80 ms | 48, 67° (48) | 48, 86° (48) | 48, 109° (48) | 16, after collision |

- **The fit.** E2 fits the lateral trials. Left escapes come systematically later than right ones
  (86° against 67° at l/v 80 ms), and frontal ones later still.
- **The rear blind spot.** Rear looms escape rarely and only after collision. The disk straight
  behind enters the rearmost fields only when it is large (design section 7). E4's rear "match"
  rests on 27 late escapes.
- **Front.** The frontal direction is still read from the DNp01 contrast and stays a gap; D1
  shows what the DNp02/DNp11 readout would carry.

## 4. V2-V5 and V8

**V2, start-size invariance** (seeds 940001-940024, right azimuth, elevation 0). Median size at
escape for starts of 5°, 10° and 20°:

| l/v | 5° | 10° | 20° | Spread |
|---|---|---|---|---|
| **40 ms** | 95.8° | 133.5° | 160.6° | **64.8°** |
| 80 ms | 62.3° | 65.7° | 61.8° | 3.9° |
| 160 ms | 55.4° | 58.0° | 55.0° | 3.0° |

- **What happens at l/v 40 ms.** All 24 trials escape at every start, in two clusters:
  - an early one at 55-70°;
  - a late one at 130-180°, at or near collision.
- **Why the median moves.** The larger the start, the more trials fall in the late cluster: the
  median times are -36, -17 and -7 ms. The median size, the V2 statistic, swings with that
  share.
- **Slower looms.** At l/v 80 and 160 ms the escape size is start-invariant, at 55-66°.

**V3, held-out l/v** (seeds 940001-940024, the calibration stimulus):

| l/v | Escaped | Median escape time | GF model peak | Difference | Within 30 ms |
|---|---|---|---|---|---|
| 15 ms | 22 of 24 | +8.5 ms | -16.4 ms | 24.9 ms | yes |
| 30 ms | 24 of 24 | -42.9 ms | -55.7 ms | 12.8 ms | yes |
| 60 ms | 24 of 24 | -145.8 ms | -132.6 ms | 13.2 ms | yes |

**V4.** There were 0 escapes in 120 trials of static disks (10°, 30°, 60° and 90°) and a
receding disk, at the calibration position.

**V5.** There were no escapes in V1's 768 pre-stimulus seconds.

**V8a, left-right in V1** (48 trials per side):

| l/v | Right | Left | Difference | Within 0.20 |
|---|---|---|---|---|
| **10 ms** | 42 | 31 | **0.23** | **no** |
| 20 ms | 48 | 48 | 0.00 | yes |
| 40 ms | 48 | 48 | 0.00 | yes |
| 80 ms | 48 | 48 | 0.00 | yes |

**V8b, the calibration stimulus mirrored** (azimuth ±50°, elevation 11°, 24 trials per side):

| l/v | Right | Left | Difference | Within 0.20 |
|---|---|---|---|---|
| 20 ms | 18 | 15 | 0.13 | yes |
| 40 ms | 24 | 23 | 0.04 | yes |
| 80 ms | 24 | 24 | 0.00 | yes |

**Why the left side is weaker.**
- **In the direct weights.** The driven subsets reach more DNp01 weight on the right: research
  note section 5, about 1.2 times the left at mirrored positions (LC4 subsets 0.161 against
  0.144).
- **Where it shows.** It decides the outcome only where the drive is marginal: the 10 ms loom,
  whose expansion lasts about six ticks, and the timing (left escapes later at every l/v in V1).
- **Not the M3.3 mechanism.** It is a different asymmetry from M3.3's settling-creep one, whose
  creep no longer drives LPLC2 (V6a, section 5).

## 5. V6 and the descriptive checks

### V6a: the N4B6 threat matrix

The preregistered N4B6 trajectories, seeds 500001-500048, fixed fly, runtime decoder live
(`tools/m3_2_threat_matrix.py --out artifacts/m3_4_run/threat_matrix`). The paddle stays in its
approach phase, at hover height.

| Trajectory | Role | v27: escaped, size at first escape | v30: escaped | D2 (edge bound 1°/s): escaped |
|---|---|---|---|---|
| A1 frontal very slow | approach | 0.00 | 0.00 | 0.00 |
| A2 frontal slow | approach | 0.04, 27.9° | 0.00 | 0.00 |
| B1 frontal medium | approach | 0.29, 24.8° | 0.00 | 0.00 |
| **B2 frontal fast (reference)** | approach | **1.00**, 21.1° | **0.00** | 0.00 |
| C1 oblique slow, right | approach | 0.04, 27.9° | 0.00 | 0.00 |
| C2 oblique slow, left | approach | 0.00 | 0.00 | 0.00 |
| C3 lateral slow, close | approach | 0.06, 28.0° | 0.00 | 0.00 |
| D1-D3 glancing | approach | 0.00-0.02 | 0.00 | 0.00 |
| E1 abort slow | abort | 0.00 | 0.00 | 0.00 |
| E2 abort medium | abort | 0.17, 23.3° | 0.00 | 0.00 |
| F1-F3 stationary, receding, orbit | control | 0.00 | 0.00 | 0.00 |

- **No approach is escaped.**
  - A hover-height paddle's image stays at 18-31°. The v27 escapes happen at those sizes.
  - Under v30 the decision needs about 50-56° (V1, V2).
  - The approach phase never makes the image that large.
- **The edge-speed bound is not the cause.** D2 lowers it from 10°/s to 1°/s and changes nothing.
- **Asymmetry.** M3.3's C1/C2 asymmetry is gone, but only because neither side escapes. V6a
  therefore says nothing about symmetry; V8 does.
- **Beyond the declaration.** The preregistration declared that most slow approaches would not
  be escaped (section 7). The fast frontal approach B2 and the abort E2 are not escaped either.
- **Not covered.** The matrix does not include strikes. Whether the v30 fly escapes the
  descending paddle of a strike was not measured.
- **Baseline differences.** The v27 baseline differs from M3.3's v27 run (`artifacts/m3_3_run`)
  by up to 0.06 per trajectory, because this run used one Numba thread and M3.3's two. Both
  runs record the thread count.

**A lifecycle consequence.**
- **The scenario.** The M1.8-A lifecycle test moves the paddle over a perched fly at hover height
  (`test_real_approaching_swatter_launches_perched_fly_without_click`, seed 255).
- **The result.** Under v30 it no longer launches the fly within 220 ticks; under v27 it does.
- **What it means.** The lifecycle mechanics are unchanged; since `10e12f6` the test reads v27
  from `7483e51`. The scenario simply never grows the image past the decision size.

### V6b: paired no-player flight

Seeds 9901-9980, 180 s each, pointer parked far away. The baseline is v27 at `7483e51`, the
candidate v30. Every escape was classified by the N4B4 counterfactual method.

| Arm | Escapes | Per minute (95 % upper bound) | A | B | C | D |
|---|---|---|---|---|---|---|
| baseline, v27 | 9 | 0.037 (0.065) | 0 | 2 | 2 | 5 |
| candidate, v30 | **0** | 0.000 (0.012) | 0 | 0 | 0 | 0 |

- **Identical seeds.** In 71 of the 80 seeds both arms escape at exactly the same ticks; those
  seeds have no escape in either arm.
- **The same result as M3.3.** M3.3's doublet decoder removes the summed-path escapes, and the
  retinotopic encoder adds none.

**D2.** The edge-speed bound of 1°/s changes no threat-matrix outcome (table above), so no V6a
result depends on the assumed bound.

**D1, DNp02 and DNp11 during V1 front and rear stimuli** (mean spikes per trial from onset to
the end of the window, 48 trials):

| l/v | Front: DNp02 L / R | Front: DNp11 L / R | Rear: DNp02 L / R | Rear: DNp11 L / R |
|---|---|---|---|---|
| 10 ms | 1.73 / 1.83 | 0.79 / 0.98 | 0.96 / 1.04 | 0.98 / 1.04 |
| 20 ms | 2.79 / 2.77 | 1.04 / 1.08 | 1.13 / 1.23 | 1.04 / 1.17 |
| 40 ms | 4.02 / 4.19 | 1.15 / 1.23 | 1.29 / 1.40 | 1.21 / 1.29 |
| 80 ms | 6.42 / 6.83 | 1.38 / 1.44 | 1.71 / 1.79 | 2.25 / 2.33 |

- **Frontal looms.** They drive DNp02, the backward-takeoff neuron, three to four times more than
  rear looms.
- **Rear looms.** They drive DNp11, the forward-takeoff neuron, more than frontal looms do, but
  weakly: the rear eye field is small.
- **What it means for E4.** The front/back code reaches the descending neurons, so an E4 milestone
  would have a signal to read.

## 6. What the result means

- **What worked.**
  - **The timing law.** For the first time in this project it matches the real fly: an implied
    threshold of 56.5° against 54°, and a slope alpha of 1.86 against 2.0. The fly now decides
    by angular size plus a delay.
  - **Timing on held-out looms.** V3 passes, which M3.3 failed.
  - **No inappropriate escapes:**
    - none to static or receding disks (V4);
    - none at rest (V5);
    - none in no-player flight (V6b).
  - **Front and back reach the descending neurons** (D1): frontal looms drive DNp02 three to
    four times more than rear looms.
- **What failed.** Both failures are at the fast end:
  - **V2, l/v 40 ms.** Decisions split between about 60° and collision, and the start size
    shifts the mix.
  - **V8a, l/v 10 ms.** The right side's larger driven DNp01 weight wins where the drive is
    marginal.
- **The common cause.**
  - **The frozen network needs mass recruitment.** DNp01 forms a doublet only when most of its
    LPLC2/LC4 input is active at once (design section 4.1: the cap binds).
  - **Fast looms fall on the threshold.** They grow so quickly that the drive crosses that
    threshold only at the end of the expansion, so the decision is marginal there.
  - **Slow looms pass.** They cross it well before collision, and they pass V2 and V8.
- **The gameplay consequence.**
  - Even if V2 and V8 had passed, v30 would have changed the accepted gameplay more than
    declared: a fly that decides by size like a real fly never escapes a hovering paddle,
    whose image stays below 31°.
  - The game's approach phase is therefore not a threat the size rule responds to; only strikes
    could be, and they were not measured.
  - Any acceptance would need a strike measurement and a playtest.
- **What a next step could address.** Each of these would be a new preregistered milestone,
  not tuning:
  - **Strike measurement.** Measure the v30 encoder on strikes before deciding whether the size
    rule suits the game's threat.
  - **Balancing by weight.** Balance the two sides by their DNp01 input weight rather than by
    cell count. The count rule leaves the right side 1.2 times stronger under retinotopic drive.
  - **Fast looms.** Examine the timing of fast looms, where V2 and V8 fail, for example the
    frontal and lateral weighting at the horizon.
  - **E4.** Read DNp02 against DNp11 for the escape direction, now that D1 shows the signal
    exists.

## 7. Reproduction

`validate`, `d2` and `tools/m3_4_record.py` need the v30 candidate configuration. Check out
`game_room_config.json` from `10e12f6` first, and restore it afterwards. All need the
receptive-field table.

```
git clone --depth 1 https://github.com/reiserlab/eyemap_T4 ../eyemap_T4
python tools/build_receptive_fields.py --eyemap ../eyemap_T4
NUMBA_NUM_THREADS=1 python tools/m3_4_retinotopic.py calibrate --lane K --lanes 4   (K = 0-3)
NUMBA_NUM_THREADS=1 python tools/m3_4_retinotopic.py validate
NUMBA_NUM_THREADS=1 python tools/m3_4_retinotopic.py d2
python tools/m3_4_retinotopic.py report
NUMBA_NUM_THREADS=1 python tools/m3_2_threat_matrix.py run --arm baseline --out artifacts/m3_4_run/threat_matrix
NUMBA_NUM_THREADS=1 python tools/m3_2_threat_matrix.py run --arm candidate --out artifacts/m3_4_run/threat_matrix
NUMBA_NUM_THREADS=1 python tools/paired_free_flight_check.py run --arm baseline --lane 0 --lanes 2 \
    --baseline-commit 7483e51 --first-seed 9901 --last-seed 9980 --out artifacts/m3_4_run/free_flight
    (lanes 0 and 1; then --arm candidate; then classify and summary with the same options)
```
