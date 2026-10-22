# M3.2: escape feature roles after Ache et al. 2019, results

Status: **measurement complete on 2026-10-22. The preregistered primary criterion failed, so
the v28 configuration is not a playtest candidate under the decision rule.** Nothing was tuned
after the scale was calibrated.

**Decision.** On 2026-10-22 the user chose to record the failure and to restore the v27 ROOM
configuration.
- **The candidate.** The v28 configuration stays in git history at `408fbc0`. Its transfer
  record `results/game/calibration_room_m3_2.json` stays as the record of what was tested.
- **What is kept.** The gated `ache2019_v1` encoder mode, its tests and the M3.2 tools stay in
  the code. No configuration uses the mode.

- Preregistration: `game/M3_2_ESCAPE_FEATURE_ROLES_DESIGN.md` (`4a43cfb`, authorization `986c34e`,
  amendment 1 `2fe91d8`).
- Tools:
  - `tools/m3_2_escape_roles.py`: calibration and V1-V5;
  - `tools/paired_free_flight_check.py`: V6b;
  - `tools/m3_2_ache_targets.py`: the calibration targets.
- Configuration and record: the v28 candidate `game_room_config.json` at `408fbc0` and
  `results/game/calibration_room_m3_2.json`. The working configuration is v27 again.
- Raw data: `artifacts/m3_2/` (git-ignored).

## 1. Summary

| Check | Result | Criterion | Outcome |
|---|---|---|---|
| Calibration | scale 0.28 V/mV | admissible at every l/v, smallest timing error | chosen |
| V1 primary: E2 | implied threshold 30.0° (M3.0: 18.6°) | gap to partial or match (34-74°) | **fail**: still a gap |
| V2 start size | spread 8.1° at l/v 40 ms, 1.8° at 80 ms | within 10° | pass |
| V3 held-out l/v | within 13 ms of the GF model's peak at 15, 30 and 60 ms | within 30 ms | pass |
| V4 non-looming disks | 0 escapes in 120 trials | at most 1 | pass |
| V5 spontaneous | 0 in 768 s | none | pass |
| V6b no-player flight | 101 escapes against 10 in 240 minutes each | not larger than baseline | **fail** |
| V6a threat matrix | not run | descriptive | see section 7 |
| V7 tests | 522 of 522 pass | all pass | pass |

**The encoder change works as designed in the fixed-fly protocols:**
- the escape now follows angular size and no longer depends on where the disk starts (V2);
- static and receding disks drive nothing (V4);
- the timing on held-out l/v values matches the paper's GF model (V3).

**It fails for two reasons:**
- **Decision point.** The frozen chain decides on the rising side of the size term, near 30°,
  and acts about 60 ms later. That gives slow looms too small an escape size and fast looms
  no escape before collision (section 4).
- **The expansion gate.** It passes any expansion, however slow. In free flight the fly's own
  slow motion, and the paddle's slow apparent-size changes, then drive LPLC2 at its full size
  response (section 5).

## 2. Calibration

Grid 0.04-0.30 V/mV on seeds 600001-600024, at the right azimuth, on the paper's 10-90°
stimulus. Admissible values (at least 50 % escapes at every l/v):

| Scale | Squared error (ms²) | l/v 10 ms | 20 ms | 40 ms | 80 ms |
|---|---|---|---|---|---|
| 0.22 | 7226 | 0.92, +6 ms | 0.54, +11 ms | 0.92, -37 ms | 0.92, -124 ms |
| 0.24 | 3786 | 0.92, +6 | 0.67, +11 | 0.88, -37 | 0.79, -174 |
| 0.25 | 4468 | 0.92, +6 | 0.67, +11 | 0.92, -47 | 0.83, -144 |
| 0.26 | 4052 | 0.92, +6 | 0.75, +1 | 1.00, -57 | 0.92, -134 |
| 0.27 | 2454 | 0.96, +6 | 0.88, -9 | 1.00, -37 | 1.00, -184 |
| **0.28** | **1202** | 0.96, +6 | 0.92, -9 | 1.00, -57 | 1.00, -194 |
| 0.29 | 1463 | 0.96, +6 | 0.96, -9 | 1.00, -77 | 1.00, -214 |
| 0.30 | 3323 | 0.96, +6 | 0.96, -9 | 1.00, -97 | 1.00, -234 |

Each cell gives the escape fraction and the median escape time relative to collision. The
targets are -2, -30, -81 and -184 ms. Below 0.22 no value was admissible: the fastest and the
20 ms looms rarely escaped.

## 3. V1: the M3.0 scorecard on v28

| Metric | M3.0 (v27) | M3.2 (v28) | Real fly | Class (v28) |
|---|---|---|---|---|
| E1 escape probability (lateral) | 1.00 | 0.96 (367 of 384) | 0.82 | partial |
| E2 timing law | alpha 6.1, delta +14.7 ms, threshold 18.6° | alpha 3.73, delta -59 ms, threshold 30.0° | alpha 2.0, delta -6 ms, 54° | **gap** |
| E3 escape before collision at l/v 10 ms | 100 % | 0 % | 30 % short mode, 6 % long mode | - |
| E4 direction, side threats | -66.7° / +65.6° | -68.5° / +66.5° | ∓45° | match |
| E4 direction, front and rear | identical to the right side | identical to the right side | backward / forward | gap |
| E6 spontaneous escapes | 0 | 0 | - | - |

Mean angular size at escape, lateral azimuths:

| l/v | M3.0 | M3.2 | Escaped before collision (M3.2) |
|---|---|---|---|
| 10 ms | 32.0° | 180° (after collision) | 0 of 92 |
| 20 ms | 16.1° | about 125° | 60 of 83 |
| 40 ms | 14.5° | 54-65° | 96 of 96 |
| 80 ms | 19.5° | 38-40° | 96 of 96 |

- **E1.** The model now misses some fast looms: it escapes in 0.96 of l/v 10 ms trials and
  0.86 of 20 ms trials.
- **E4.** The front-and-back gap is unchanged, as declared: the encoder still uses only the
  side.

## 4. Why E2 stays a gap

**The decision point.**
- The fitted slope, 3.73, corresponds to a decision at about 30° of angular size.
- The escape follows that decision by a nearly fixed delay; the intercept is -59 ms.
- At 0.28 V/mV the LPLC2 drive is `0.69 V * G(theta)`, where `G` is the paper's Gaussian of
  log size. Before the drive peaks at 42°, it already exceeds the 0.26-0.3 V at which the
  frozen chain escapes (M3.1, section 4.4).
- The chain therefore decides on the rising side of the size term, not at its peak.

**The delay.** About three 20 ms ticks:
- LPLC2 spikes;
- DNp01 spikes;
- DNp01 spikes again, which the decoder's two-spike rule needs.

The real fly's neural delay to takeoff is 30-46 ms (X24).

**Consequences:**
- **Slow looms** escape at a smaller size than the real 54°.
- **The fastest looms** reach collision before the delay has passed.

**Why the calibration could not repair it.**
- The target was the paper's GF peak, and the four l/v values pull the scale in opposite
  directions:
  - a smaller scale makes slow looms decide later;
  - but it leaves fast looms without enough drive to escape at all.
- The peak times themselves imply only 42.3°, as predicted.

The decision point and the delay are properties of the frozen decoder and of the 20 ms tick,
not of the encoder.

## 5. V6b: escapes in no-player flight

| Arm | Seeds | Escapes | Seeds with an escape | Per hour |
|---|---|---|---|---|
| baseline, v27 (`d67808f`) | 9601-9680 | 10 | 9 | 2.5 |
| candidate, v28 | 9601-9680 | 101 | 50 | 25.2 |

Every escape was classified by the N4B4 counterfactual method (`tools/paired_free_flight_check.py`):
- **A:** no LC4 or LPLC2 drive in the 120 ms before the escape;
- **B:** stimulus-driven, but without the escape the fly would not have come within 310 units
  of the paddle in 1.5 s;
- **C:** a near pass whose expansion comes mostly from apparent-size change;
- **D:** a near pass driven mostly by the fly's own approach.

| Arm | A | B | C | D |
|---|---|---|---|---|
| baseline, v27 | 0 | 1 | 1 | 8 |
| candidate, v28 | 0 | **65** | 5 | 31 |

- **Rate bounds.** The candidate's rate is 0.42 per minute (95 % upper bound 0.50), against 0.04
  (upper 0.07). The earlier stages' bound for category B, below 0.1 per minute at 95 %, is not
  met.
- **No change at rest.** Neither arm has a category-A escape: nothing changed at rest.
- **What triggers the category-B escapes:**
  - a median angular size of 17° (11-22°);
  - a median expansion rate of only 2.4°/s (-1 to 6°/s at the escape tick);
  - a median horizontal distance of 460 units.
- **How they happen.** The fly drifts slowly towards the parked paddle, or the paddle's
  apparent size changes slowly. While `theta_dot` is positive, the LPLC2 term drives
  `0.69 V * G(17°)`, about 0.15 V, on every tick. The trace builds up until the FAST (36) or
  SUSTAINED (27) path fires.
- **Under the legacy encoder** the same situation drove LPLC2 with about `0.4 * theta_dot`,
  0.02 V, far below the 0.26-0.3 V the chain needs.
- **Category D.** Self-approach near passes also rose, from 8 to 31.

## 6. What the result means

- **The encoder's feature roles.** The paper's roles are now the encoder's roles: LPLC2 by
  size and LC4 by velocity. The fixed-fly checks that test them directly pass (V2-V5).
- **The escape threshold.** It did not reach the behavioural threshold: 30° against 54°. The
  remaining timing error sits in the frozen decoder's two-spike rule and the 20 ms tick.
- **The expansion gate.** "Any expansion" is too permissive for a freely moving fly. Real LPLC2
  needs coherent outward motion of some speed (Klapoetke et al. 2017; Ache et al. 2019 note
  that LPLC2 neurons "require looming motion to be active"). A slow apparent-size change of a
  parked paddle is not a loom.

## 7. Open decisions for the user

- **Keep or revert.** Decided: reverted to v27 (see Status).
- **V6a.** The N4B6 threat matrix (about two hours for both arms) was not run, because the
  decision rule had already failed. It can be run on request.
- **A follow-up.** Any follow-up is a new preregistered milestone. The two causes above point
  to:
  - a graded speed dependence of the LPLC2 term (encoder);
  - the decision delay (decoder and tick), which is frozen.

## 8. Reproduction

`validate` and `tools/m3_2_record.py` need the v28 candidate configuration. Check out
`game_room_config.json` from `408fbc0` first, and restore it afterwards.

```
python tools/m3_2_ache_targets.py
python tools/m3_2_escape_roles.py calibrate
python tools/m3_2_escape_roles.py validate
python tools/m3_2_escape_roles.py report
NUMBA_NUM_THREADS=1 python tools/paired_free_flight_check.py run --arm baseline --lane 0 --lanes 2 \
    --baseline-commit d67808f62bef6a11205f65be6aad827b48f4d82a --first-seed 9601 --last-seed 9680 \
    --out artifacts/m3_2/free_flight          (lanes 0 and 1; then --arm candidate)
NUMBA_NUM_THREADS=1 python tools/paired_free_flight_check.py classify --lane 0 --lanes 4 ...   (lanes 0-3)
python tools/paired_free_flight_check.py summary ...
```
