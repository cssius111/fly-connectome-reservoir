# M3.8 result: saccades of about 90°, and no spontaneous turns while tracking an odor upwind

Status: **all checks P1-P6 passed, 2026-10-26.** The v32 candidate (commit `ce0c745`) stays the
working ROOM configuration as a candidate, with its record
`results/game/calibration_room_m3_8.json`. Acceptance is the user's, after a playtest. Nothing was
tuned or rerun.

**Preregistration.** `game/M3_8_SACCADE_ODOR_DESIGN.md` (commit `e87fa26`).
- **The change.** A configuration-only change of four class-B parameters, from v27 (`7483e51`):
  - `flight.correction.probability` from 0.42 to 0;
  - `flight.saccade.degrees` from [25, 105] to [60, 120];
  - `flight.saccade.peak_rate_deg_per_second` from [700, 1400] to [1200, 1500];
  - `ecology.spontaneous_clock_rate.ODOR_TRACK` from 0.35 to 0.
- **The record.** It carries the v27 decoder and threshold over unchanged.

**Tools.**
- `tools/m3_8_checks.py` for P1, P2, P5, P6, D1 and D3. It runs the M3.7 tools with M3.8's seeds,
  output directory and arms.
- `tools/kinematics_sanity.py` for P3 and D2.
- `tools/paired_free_flight_check.py` for P4.

Raw data are in `artifacts/m3_8/` (git-ignored).

## 1. Summary

| Check | Baseline v27 | Candidate v32 | Pass condition | Result |
|---|---|---|---|---|
| P1 clock-driven saccades | 0.186 per s | **0.307 per s** | 0.30-0.50 per s | pass |
| P2 S3, all spontaneous events | median 54.8° in 60 ms | **77.0° in 80 ms** | 60-120° and ≤ 100 ms | pass |
| P3 pathology screen | | no failure | no failure | pass |
| P4 no-player escapes, 240 min | 9 | **9** | not more than the baseline | pass |
| P5 fixed-fly escapes, 384 trials | | 384 identical, 0 differing | all identical | pass |
| P6 ODOR_TRACK upwind share, 40 × 180 s | 0.529 | **0.591** | ≥ 0.479 (baseline − 0.05) | pass |

- **What M3.7's saccade change keeps.** The protocol-S saccade metrics match the real fly as they
  did in M3.7:
  - the clock part lies within the band around Censi et al.'s baseline of about 0.4 per s;
  - saccades are about 80° in 80 ms.
- **What the ODOR_TRACK change adds.** The fly no longer turns spontaneously while it tracks an
  odor upwind, as in Budick and Dickinson 2006. In P6 its upwind share is no lower than v27's.
- **What it does not change.**
  - **No-player escapes.** They are equal to v27's in total.
  - **The escape decision.** Fixed-fly escapes are identical trial by trial.
- **The risk stated beforehand.** P1 lies 0.007 per s above the lower bound, as the read-only
  variant (0.311 per s) predicted.

## 2. Saccades (P1, P2, D1)

Protocol S of M3.0, unchanged, on seeds 973001-973020 (20 × 180 s), both arms:

| | Baseline v27 | Candidate v32 |
|---|---|---|
| Usable airborne time | 2,915 s | 2,909 s |
| S1, all spontaneous events (comparator 1.37 per s) | 0.339 per s | 0.432 per s |
| S2, interval mean / median (comparator 0.82 s) | 2.48 / 1.74 s | 1.99 / 1.38 s |
| S3, median amplitude and duration | 54.8°, 60 ms | 77.0°, 80 ms |
| SACCADE (clock) | 0.186 per s, 55° | 0.307 per s, 81° |
| AVOID (wall) | 0.117 per s, 60° | 0.096 per s, 67° |
| DEPART (wall) | 0.034 per s, 49° | 0.028 per s, 49° |
| CORRECTION | 0.002 per s | 0.000 per s |
| Mean airborne speed | 7.65 BL/s | 7.63 BL/s |

- **The baseline.** It reproduces M3.0 and M3.7 on fresh seeds: 0.186 clock saccades per s,
  against 0.192 and 0.183.
- **The clock rate.** It is 0.015 per s lower than M3.7's 0.322 on other seeds, as expected from
  stopping the ODOR_TRACK clock.
- **Fewer wall turns.** As in M3.7, they become less frequent (0.151 → 0.124 per s), because
  open-space saccades redirect the fly before it reaches a wall.
- **S1 and S2 stay gaps.** As in M3.7: the M3.0 comparator is mostly stimulus-driven in a large,
  fast arena (game/M3_7_SACCADE_RESEARCH.md, section 3).

## 3. Escapes (P4, P5)

**P4.** Paired no-player flight on seeds 973201-973280 (80 × 180 s), baseline v27 at `7483e51`.
Escapes are classified by the N4B4 counterfactual method:
- **A.** A neural false escape: no LC4/LPLC2 drive in the 120 ms before it.
- **B.** Inappropriate: without the escape the fly never comes within 310 units of the paddle.
- **C.** A near pass in which apparent-size change dominates the expansion.
- **D.** A near pass in which range change dominates the expansion (self-approach).

| Arm | Escapes | Per minute (95 % upper) | A | B | C | D |
|---|---|---|---|---|---|---|
| v27 | 9 | 0.037 (0.065) | 0 | 2 | 3 | 4 |
| v32 | 9 | 0.037 (0.065) | 1 | 0 | 0 | 8 |

- **Shared seeds.** 64 of 80 seeds have identical escape ticks in both arms.
- **Near passes.** 15 of the 18 escapes are slow approaches to the hovering paddle, of the kind
  seen before: 359-546 units, θ 17-28°, θ̇ 4-9°/s.
- **Far escapes.** The other three occur 1,366-1,932 units from the paddle, at θ 5-6° with
  almost no drive:
  - v27 has two (category B, drive 0.03 and 0.05);
  - v32 has one (category A, drive 0).
  With drive at or near zero they are not responses to the paddle, and they are as rare in the
  candidate as in the baseline.
- **An earlier standard.** The candidate meets the category-B standard used before (under 0.1
  per minute at 95 %).

**P5.** M3.0's protocol E on seeds 973301-973324, all 16 l/v × azimuth conditions: 384 of 384
trials have identical escapes in both arms. The record's carry-over is therefore exact.

**D3, encounters with the paddle.** From P6's runs (40 × 180 s, pointer parked); an encounter is
a maximal airborne run within 650 units of the paddle centre.

| | Baseline v27 | Candidate v32 |
|---|---|---|
| Airborne minutes | 93.4 | 91.5 |
| Escapes | 6 | 6 |
| Encounters (per airborne minute) | 95 (1.02) | 83 (0.91) |
| Share of encounters ending in an escape | 0.053 | 0.072 |
| Share of airborne time within 650 units | 0.091 | 0.077 |

The candidate meets the paddle slightly less often, and slightly more of its encounters end in
an escape. Both differences rest on 6 escapes per arm and are within noise.

## 4. Odor tracking (P6)

From the same 40 × 180 s runs on seeds 973401-973440. The share counts ODOR_TRACK airborne ticks
heading within 45° of upwind.

| | Baseline v27 | Candidate v32 |
|---|---|---|
| ODOR_TRACK airborne minutes | 16.1 | 15.9 |
| Upwind share | 0.529 | **0.591** |
| SACCADE starts per ODOR_TRACK minute | 4.23 | 0.00 |
| Upwind share 2 s or more after the last saccade start | 0.56 | 0.63 |

- **The clock is stopped.** No SACCADE starts during ODOR_TRACK in the candidate.
- **The effect.** The upwind share rises by 0.06, not merely holding v27's level. In v27 a
  spontaneous turn during tracking turns the fly away from the wind for about 2 s (upwind share
  0.36-0.42 in the first 2 s after a saccade start).
- **The remaining short-interval ticks.** In the candidate these follow saccades made before the
  fly entered ODOR_TRACK.

## 5. Flight and ecology (P3, D2)

`tools/kinematics_sanity.py`, its six fixed seeds, 180 s each. The pathology screen reports no
failure.

| | Baseline v27 | Candidate v32 |
|---|---|---|
| Turn requests per airborne minute: SACCADE / CORRECTION / AVOID / DEPART | 10.6 / 9.2 / 6.3 / 1.6 | 19.3 / 2.4 / 5.9 / 1.9 |
| Occupancy: EXPLORE / TRANSIT / ODOR_SEARCH / ODOR_TRACK | 0.384 / 0.243 / 0.112 / 0.253 | 0.404 / 0.281 / 0.108 / 0.201 |
| Odor detected share of alive time | 0.306 | 0.238 |
| Odor encounters per alive minute | 1.89 | 1.44 |
| ODOR_TRACK share heading upwind | 0.661 | 0.471 |
| Food touchdowns / other touchdowns | 10 / 4 | 12 / 1 |
| Airborne / perched / feeding fractions | 0.850 / 0.150 / 0.119 | 0.869 / 0.131 / 0.128 |
| Visited share of the 10 BL grid | 0.534 | 0.457 |
| Near-wall share of airborne time | 0.165 | 0.145 |

- **The upwind share here disagrees with P6.**
  - **The size of the sample.** These six seeds hold about 4.6 and 3.6 minutes of ODOR_TRACK,
    about a quarter of P6's 16 minutes per arm.
  - **Seed sets differ widely.** v27 itself gives 0.661 here and 0.529 in P6.
  - **Which result counts.** P6, the larger preregistered measurement, decides. This six-seed
    value is descriptive, and it is reported because it points the other way.
- **Odor contact.** The candidate detects odor less often on these seeds (0.306 → 0.238). Its
  ODOR_TRACK occupancy is lower and its TRANSIT occupancy higher.
- **Feeding.** Food touchdowns and the feeding fraction rose, as in M3.7.
- **Space.** The visited share fell by 14 %, within the screen's limit of one half.

## 6. What the result means

- **The saccade change and the odor-tracking change fit together.** Spontaneous saccades of
  about 90° in open flight, and straight upwind flight during odor tracking, are both reached
  with class-B parameters alone. No frozen system changes.
- **The M3.7 failure is resolved under its own criterion.** No-player escapes are equal (9 and
  9).
  - **What this shows.** It is consistent with the M3.7 follow-up, which did not establish that
    the saccade change raises escapes.
  - **What it does not show.** P4 does not show that the M3.7 change was harmless.
- **Remaining gaps.**
  - **S1 and S2** stay below the M3.0 comparator, for the reasons in game/M3_7_SACCADE_RESEARCH.md.
  - **Odor contact** on the six kinematics seeds is lower; whether that is a real effect is not
    established by six seeds.
- **Decision under the rule.** v32 stays the working ROOM configuration as a candidate. It goes
  to the user for a ROOM playtest, and acceptance is the user's. Until then v27 (`7483e51`)
  remains the last accepted configuration.

## 7. Reproduction

```
NUMBA_NUM_THREADS=1 python tools/m3_8_checks.py protocol-s --arm baseline --lane K --lanes 2    (K = 0, 1; also --arm candidate)
NUMBA_NUM_THREADS=1 python tools/m3_8_checks.py protocol-e --arm baseline                        (also --arm candidate)
NUMBA_NUM_THREADS=1 python tools/m3_8_checks.py encounters --arm baseline --lane K --lanes 2
NUMBA_NUM_THREADS=1 python tools/m3_8_checks.py encounters --arm candidate --candidate-commit ce0c745 --lane K --lanes 2
python tools/m3_8_checks.py summary --candidate-commit ce0c745
NUMBA_NUM_THREADS=1 python tools/kinematics_sanity.py run --commit 7483e51 --out artifacts/m3_8/kinematics/baseline
NUMBA_NUM_THREADS=1 python tools/kinematics_sanity.py run --out artifacts/m3_8/kinematics/candidate
python tools/kinematics_sanity.py compare --before artifacts/m3_8/kinematics/baseline --out artifacts/m3_8/kinematics/candidate
NUMBA_NUM_THREADS=1 python tools/paired_free_flight_check.py run --arm baseline --lane K --lanes 2 --baseline-commit 7483e51 \
    --first-seed 973201 --last-seed 973280 --out artifacts/m3_8/free_flight          (also --arm candidate)
NUMBA_NUM_THREADS=1 python tools/paired_free_flight_check.py classify --lane K --lanes 4 --baseline-commit 7483e51 \
    --first-seed 973201 --last-seed 973280 --out artifacts/m3_8/free_flight          (K = 0-3)
python tools/paired_free_flight_check.py summary --baseline-commit 7483e51 --first-seed 973201 --last-seed 973280 \
    --out artifacts/m3_8/free_flight
```
