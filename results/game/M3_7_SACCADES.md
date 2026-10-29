# M3.7 result: straight flight between saccades of about 90°

Status: **failed check P4, 2026-10-26.** The working ROOM configuration is v27 again. The v31
candidate stays in git history at `c10477d`, with its record
`results/game/calibration_room_m3_7.json`. Nothing was tuned or rerun.

**Preregistration.** `game/M3_7_SACCADE_DESIGN.md` (commit `bee4635`).
- **The change.** A configuration-only change of three class-B free-flight parameters:
  - `flight.correction.probability` from 0.42 to 0;
  - `flight.saccade.degrees` from [25, 105] to [60, 120];
  - `flight.saccade.peak_rate_deg_per_second` from [700, 1400] to [1200, 1500].
- **The record.** It carries the v27 decoder and threshold over unchanged.

**Tools.**
- `tools/m3_7_saccades.py` for P1, P2, P5 and D1;
- `tools/kinematics_sanity.py` for P3 and D2;
- `tools/paired_free_flight_check.py` for P4.
Raw data are in `artifacts/m3_7/` (git-ignored).

## 1. Summary

| Check | Baseline v27 | Candidate v31 | Pass condition | Result |
|---|---|---|---|---|
| P1 clock-driven saccades | 0.183 per s | **0.322 per s** | 0.30-0.50 per s | pass |
| P2 S3, all spontaneous events | median 58.4° in 80 ms | **77.6° in 80 ms** | 60-120° and ≤ 100 ms | pass |
| P3 pathology screen | | no failure | no failure | pass |
| P4 no-player escapes, 240 min | 9 | **15** | not more than the baseline | **fail** |
| P5 fixed-fly escapes, 384 trials | | 384 identical, 0 differing | all identical | pass |

- **What worked.**
  - **The saccades themselves.** For the first time a protocol-S metric matches the real fly.
    The clock part reaches Censi et al.'s baseline of about 0.4 per s within the band, and
    saccades are about 90° in under 100 ms.
  - **The escape decision.** It is untouched: P5 is identical trial by trial.
- **What failed.**
  - **No-player escapes.** They rose from 9 to 15 in 240 minutes.
  - **The noise.** The difference lies within Poisson noise: 95 % upper bounds 0.065 and 0.096
    per minute.
  - **The rule.** The preregistered criterion was "not larger".

## 2. Saccades (P1, P2, D1)

Protocol S of M3.0, unchanged, on seeds 972001-972020 (20 × 180 s), both arms:

| | Baseline v27 | Candidate v31 |
|---|---|---|
| Usable airborne time | 2,715 s | 2,633 s |
| S1, all spontaneous events (comparator 1.37 per s) | 0.323 per s | 0.426 per s |
| S2, interval mean / median (comparator 0.82 s) | 2.66 / 1.90 s | 2.03 / 1.50 s |
| S3, median amplitude and duration | 58.4°, 80 ms | 77.6°, 80 ms |
| SACCADE (clock) | 0.183 per s, 58° | 0.322 per s, 81° |
| AVOID (wall) | 0.105 per s, 67° | 0.080 per s, 68° |
| DEPART (wall) | 0.034 per s, 53° | 0.024 per s, 51° |
| CORRECTION | 0.001 per s | 0 |
| Mean airborne speed | 7.69 BL/s | 7.53 BL/s |

- **The baseline.** It reproduces M3.0 on fresh seeds: 0.183 clock saccades per s at 58°,
  against M3.0's 0.192 at 59°.
- **Fewer wall turns.** Wall-driven turns became less frequent (0.139 → 0.104 per s), because
  open-space saccades now redirect the fly before it reaches a wall.
- **S1 and S2 stay gaps.** As the design expected (about 0.48 per s), the M3.0 comparator is
  mostly stimulus-driven in a large, fast arena (game/M3_7_SACCADE_RESEARCH.md, section 3).

## 3. Escapes (P4, P5)

**P4.** Paired no-player flight on seeds 972201-972280 (80 × 180 s), baseline v27 at `7483e51`.
Escapes are classified by the N4B4 counterfactual method:
- **A.** A neural false escape: no LC4/LPLC2 drive in the 120 ms before it.
- **B.** Inappropriate: without the escape the fly never comes within 310 units of the paddle.
- **C.** A near pass in which apparent-size change dominates the expansion.
- **D.** A near pass in which range change dominates the expansion (self-approach).

| Arm | Escapes | Per minute (95 % upper) | A | B | C | D |
|---|---|---|---|---|---|---|
| v27 | 9 | 0.037 (0.065) | 0 | 0 | 0 | 9 |
| v31 | 15 | 0.062 (0.096) | 0 | 2 | 6 | 7 |

- **Shared seeds.** 57 of 80 seeds have identical escape ticks in both arms.
- **What kind of escapes.** Every escape in both arms is a slow approach to the hovering paddle,
  of the kind seen before: 326-630 units, θ 14-32°, θ̇ 4-9°/s.
- **Where the extra ones come from.** The candidate's extra escapes are mostly size-dominated
  (C) and two inappropriate (B).
- **An earlier standard.** The candidate meets the category-B standard used before (under 0.1
  per minute at 95 %). It fails P4's preregistered total-escape criterion.

**P5.** M3.0's protocol E on seeds 972301-972324, all 16 l/v × azimuth conditions: 384 of 384
trials have identical escapes in both arms. The record's carry-over is therefore exact.

## 4. Flight and ecology (P3, D2)

`tools/kinematics_sanity.py`, six seeds, 180 s each. The pathology screen reports no failure.

| | Baseline v27 | Candidate v31 |
|---|---|---|
| Turn requests per airborne minute: SACCADE / CORRECTION / AVOID / DEPART | 10.6 / 9.2 / 6.3 / 1.6 | 19.4 / 3.1 / 5.8 / 1.5 |
| Occupancy: EXPLORE / TRANSIT / ODOR_SEARCH / ODOR_TRACK | 0.384 / 0.243 / 0.112 / 0.253 | 0.376 / 0.267 / 0.126 / 0.222 |
| Odor detected share of alive time | 0.306 | 0.270 |
| Odor encounters per alive minute | 1.89 | 1.67 |
| ODOR_TRACK share heading upwind | **0.661** | **0.407** |
| Food touchdowns / other touchdowns | 10 / 4 | 13 / 1 |
| Airborne / perched / feeding fractions | 0.850 / 0.150 / 0.119 | 0.837 / 0.163 / 0.160 |
| Visited share of the 10 BL grid | 0.534 | 0.447 |
| Near-wall share of airborne time | 0.165 | 0.148 |

- **Upwind heading during odor tracking.** It fell from 0.66 to 0.41. The frozen ODOR_TRACK
  clock rate (0.35) now issues 60-120° saccades where 42 % of its events were small corrections.
- **Feeding.** Food touchdowns and the feeding fraction rose.
- **Space.** The visited share fell by 16 %, within the screen's limit of one half.

**D3, not run.** The N4B6 threat matrix holds the fly fixed, so the flight generator cannot
change it, and P5 already shows fixed-fly escapes identical.

## 5. What the result means

- **The saccade targets are reachable with class-B parameters alone.** They need no change to any
  frozen system.
- **The failed criterion measures a consequence.**
  - **What P4 counts.** It counts escapes, not their cause.
  - **The likely cause.** More frequent, larger turns change where the fly goes and how it meets
    the hovering paddle.
  - **What is unknown.** Whether the extra near passes come from more encounters or from more
    escapes per encounter. The data here do not separate them.
- **The odor-tracking change is a real behavioural cost.**
  - **The model.** It holds an upwind course less well while tracking.
  - **The real fly.** It surges upwind on odor contact. Whether its saccades during plume
    tracking are smaller or rarer was not sourced in M3.7.
- **Decision under the rule.** v27 stays. Any next step is a new preregistered milestone.

## 6. Reproduction

Check out `game_room_config.json` from `c10477d` for the candidate arm, and restore it afterwards.

```
NUMBA_NUM_THREADS=1 python tools/m3_7_saccades.py protocol-s --arm baseline --lane K --lanes 2   (K = 0, 1; also --arm candidate)
NUMBA_NUM_THREADS=1 python tools/m3_7_saccades.py protocol-e --arm baseline                       (also --arm candidate)
python tools/m3_7_saccades.py summary
NUMBA_NUM_THREADS=1 python tools/kinematics_sanity.py run --commit 7483e51 --out artifacts/m3_7/kinematics/baseline
NUMBA_NUM_THREADS=1 python tools/kinematics_sanity.py run --out artifacts/m3_7/kinematics/candidate
python tools/kinematics_sanity.py compare --before artifacts/m3_7/kinematics/baseline --out artifacts/m3_7/kinematics/candidate
NUMBA_NUM_THREADS=1 python tools/paired_free_flight_check.py run --arm baseline --lane K --lanes 2 --baseline-commit 7483e51 \
    --first-seed 972201 --last-seed 972280 --out artifacts/m3_7/free_flight          (also --arm candidate)
NUMBA_NUM_THREADS=1 python tools/paired_free_flight_check.py classify --lane K --lanes 4 --baseline-commit 7483e51 \
    --first-seed 972201 --last-seed 972280 --out artifacts/m3_7/free_flight
python tools/paired_free_flight_check.py summary --baseline-commit 7483e51 --first-seed 972201 --last-seed 972280 \
    --out artifacts/m3_7/free_flight
```
