# M3.3: size-tuned encoder and a same-side doublet decoder, results

Status: **measurement in progress (2026-10-23).**
- V1-V5 are complete. **V3 failed on one of its three l/v values**, so under the decision rule
  the v29 configuration is not a playtest candidate.
- V6a and V6b are still running.
- Nothing was tuned after the scale was calibrated.

**Sources:**
- Preregistration: `game/M3_3_ESCAPE_DECISION_DESIGN.md`
  - preregistered in `523ff2d`, with the seed correction `a71f25d`;
  - authorization in `0239aed`.
- Tools:
  - `tools/m3_3_escape_decision.py`: calibration and V1-V5;
  - `tools/m3_2_threat_matrix.py`: V6a;
  - `tools/paired_free_flight_check.py`: V6b.
- Configuration and record: `game_room_config.json` v29 and
  `results/game/calibration_room_m3_3.json`, on the working branch. `main` runs v27.
- Raw data: `artifacts/m3_3_run/` (git-ignored).

## 1. Summary

| Check | Result | Criterion | Outcome |
|---|---|---|---|
| Calibration | 0.30 V/mV, squared error 526 ms² | admissible at every l/v, smallest error | chosen |
| V1 primary: E2 | implied threshold 38.2° (v27: 18.6°, M3.2: 30.0°) | partial or match (34-74°) | **pass** (partial) |
| V1: E1 | 0.83 (real fly 0.82) | at least partial | **pass** (match) |
| V2 start size | spread 6.0°, 4.4° and 0.3° at l/v 40, 80 and 160 ms | within 10° | pass |
| V3 held-out l/v | 15 ms: 25 ms off; **30 ms: 32.8 ms off**; 60 ms: 13 ms off | within 30 ms | **fail** |
| V4 non-looming disks | 0 escapes in 120 trials | at most 1 | pass |
| V5 spontaneous | 0 in 768 s | none | pass |
| V6a threat matrix | running | descriptive | - |
| V6b no-player flight | 0 escapes against 9 in 240 minutes each | not more than baseline | **pass** |
| V7 tests | 534 of 534 pass | all pass | pass |

**What V3's miss means.**
- At l/v 30 ms the median escape time is 22.9 ms before collision. The GF model's peak is 55.7 ms
  before collision.
- The 30 ms tolerance is exceeded by 2.8 ms. That is a seventh of a 20 ms tick, which is the
  resolution of the model's escape times.
- The rule still applies: the result is recorded as a failure, and neither the tolerance nor the
  scale is changed.

## 2. Calibration

Grid 0.20-0.50 V/mV, seeds 600001-600024, the paper's 10-90° stimulus. Admissible values:

| Scale | Squared error (ms²) | l/v 10 ms | 20 ms | 40 ms | 80 ms |
|---|---|---|---|---|---|
| 0.29 | 1178 | 0.79, +6 ms | 0.67, -9 ms | 0.75, -57 ms | 1.00, -174 ms |
| **0.30** | **526** | 0.79, +6 | 0.79, -9 | 0.88, -77 | 1.00, -184 |
| 0.31 | 1463 | 0.75, +6 | 0.75, -9 | 0.96, -77 | 1.00, -214 |
| 0.32 | 1463 | 0.71, +6 | 0.88, -9 | 0.96, -77 | 1.00, -214 |
| 0.33 | 3087 | 0.75, +6 | 0.79, -9 | 0.96, -77 | 1.00, -234 |
| 0.34 | 3087 | 0.71, +6 | 0.83, -9 | 0.96, -77 | 1.00, -234 |
| 0.35 | 5511 | 0.62, +6 | 0.88, -9 | 1.00, -77 | 1.00, -254 |
| 0.36 | 5747 | 0.54, +6 | 0.88, -9 | 1.00, -97 | 1.00, -254 |
| 0.37 | 5747 | 0.50, +6 | 0.92, -9 | 1.00, -97 | 1.00, -254 |

Each cell gives the escape fraction and the median escape time relative to collision. The
targets are -2, -30, -81 and -184 ms.

- **Low end.** Below 0.29 the 40 and 80 ms looms rarely escape.
- **High end.** Above 0.37 the 10 ms loom escapes in fewer than half of the trials.
- **What the low end shows.** The doublet needs a strong drive, which the slow looms reach only
  near the LPLC2 term's peak.

## 3. V1: the M3.0 scorecard on v29

| Metric | v27 | M3.2 (v28) | M3.3 (v29) | Real fly | Class (v29) |
|---|---|---|---|---|---|
| E1 escape probability (lateral) | 1.00 | 0.96 | **0.83** (317 of 384) | 0.82 | **match** |
| E2 timing law | alpha 6.1, threshold 18.6° | alpha 3.73, threshold 30.0° | **alpha 2.89, delta -43 ms, threshold 38.2°** | alpha 2.0, -6 ms, 54° | **partial** |
| E3 escape before collision at l/v 10 ms | 100 % | 0 % | 0 % | 30 % short mode, 6 % long mode | - |
| E4 direction, side threats | -66.7° / +65.6° | -68.5° / +66.5° | -69.2° / +67.2° | ∓45° | match |
| E4 direction, front and rear | as right | as right | as right | backward / forward | gap |
| E6 spontaneous escapes | 0 | 0 | 0 | - | - |

Per l/v, lateral azimuths:

| l/v | Escaped | Mean size at escape | Escaped before collision |
|---|---|---|---|
| 10 ms | 71 of 96 (0.74) | after collision | 0 |
| 20 ms | 72 of 96 (0.75) | about 133° | 66 |
| 40 ms | 84 of 96 (0.88) | 61-66° | 84 |
| 80 ms | 90 of 96 (0.94) | 46-47° | 90 |

## 4. V2-V5

**V2, start-size invariance** (seeds 810001-810024). Median size at escape for starts of 5°,
10° and 20°:

| l/v | 5° | 10° | 20° | Spread |
|---|---|---|---|---|
| 40 ms | 55.4° | 54.8° | 49.5° | 6.0° |
| 80 ms | 45.2° | 49.3° | 44.9° | 4.4° |
| 160 ms | 39.6° | 39.2° | 39.4° | 0.3° |

The size at escape falls with l/v, from 55° to 39°. That is the pattern of a fixed decision size
plus a fixed delay.

**V3, held-out l/v** (seeds 810001-810024, the paper's 10-90° stimulus):

| l/v | Escaped | Median escape time | GF model peak | Difference | Within 30 ms |
|---|---|---|---|---|---|
| 15 ms | 9 of 24 | +8.5 ms | -16.4 ms | 24.9 ms | yes |
| 30 ms | 20 of 24 | -22.9 ms | -55.7 ms | 32.8 ms | **no** |
| 60 ms | 23 of 24 | -145.8 ms | -132.6 ms | 13.2 ms | yes |

**V4.** There were 0 escapes in 120 trials of static disks (10°, 30°, 60° and 90°) and a
receding disk.

**V5.** There were no escapes in V1's 768 pre-stimulus seconds.

## 5. V6

### V6b: paired no-player flight

Seeds 9801-9880, 180 s each, pointer parked far away.
- Baseline: v27 at `b5e6021`.
- Candidate: v29.
- Every escape was classified by the N4B4 counterfactual method.

| Arm | Escapes | Per minute (95 % upper bound) | A | B | C | D |
|---|---|---|---|---|---|---|
| baseline, v27 | 9 (8 FAST, 1 SUSTAINED) | 0.037 (0.065) | 1 | 2 | 1 | 5 |
| candidate, v29 | **0** | 0.000 (0.012) | 0 | 0 | 0 | 0 |

- **What changed.** Every baseline escape came through the summed N2b paths. M3.3 removes them.
- **What stayed the same.** In 71 of the 80 seeds both arms escape at exactly the same ticks;
  those seeds have no escape in either arm.
- **M3.2's failure is fixed.** M3.2's tenfold rise in no-player escapes (101 against 10) is gone.
  v29 escapes less than the v27 baseline.

### V6a: the N4B6 threat matrix

Running; filled in when complete.
