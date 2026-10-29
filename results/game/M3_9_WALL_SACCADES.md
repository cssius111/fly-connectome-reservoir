# M3.9 result: wall-evoked saccades of fixed amplitude

Status: **failed check P6, 2026-10-29.** The working ROOM configuration is v32 again. The v33
candidate stays in git history at `7727397`, with its record
`results/game/calibration_room_m3_9.json`. Nothing was tuned or rerun.

**Preregistration.** `game/M3_9_WALL_SACCADE_DESIGN.md` (commit `f57e7d0`).
- **The change.**
  - `flight.boundary.avoid_degrees`, a new key, set to [60, 120]: an AVOID draws its amplitude from
    this interval, independent of the approach angle, and turns away from the wall.
  - `flight.boundary.avoid_peak_rate_deg_per_second`, from [700, 1300] to [1200, 1500].
- **The basis.** Tammero and Dickinson 2002 (game/M3_9_WALL_SACCADE_RESEARCH.md).
- **The gating.** The rule in `game/flight.py` applies only when the new key is present, so it stays
  in the code, unused by every current configuration. Without the key, its tests show the tangent
  rule and its random draws unchanged.

**Tools.**
- `tools/m3_9_checks.py` for P1, P2, P5, P6, P7, D1 and D3;
- `tools/kinematics_sanity.py` for P3 and D2;
- `tools/paired_free_flight_check.py` for P4.
The baseline arm is v32 at `925427c`. Raw data are in `artifacts/m3_9/` (git-ignored).

## 1. Summary

| Check | Baseline v32 | Candidate v33 | Pass condition | Result |
|---|---|---|---|---|
| P1 AVOID amplitude against approach angle | slope 1.00, r² 1.00 | **slopes 0.09 / 0.01, r² 0.015 / 0.000; median 87°; all away** | \|slope\| ≤ 0.2, r² ≤ 0.05, median 60-120°, all away | pass |
| P2 wall contacts / near-wall share | 0.129 per min / 0.145 | **0.072 per min / 0.114** | ≤ 0.5 per min / ≤ 0.181 | pass |
| P3 pathology screen | | no failure | no failure | pass |
| P4 no-player escapes, 240 min | 16 | **12** | not more than the baseline | pass |
| P5 fixed-fly escapes, 384 trials | | 384 identical, 0 differing | all identical | pass |
| P6 ODOR_TRACK upwind share, 40 × 180 s | 0.564 | **0.481** | ≥ 0.514 | **fail** |
| P7 clock-driven saccades, S3 | 0.300 per s, 76.5° in 80 ms | **0.312 per s, 80.0° in 80 ms** | 0.30-0.50 per s; 60-120°, ≤ 100 ms | pass |

- **What worked.**
  - **The wall saccades.** Their amplitude no longer depends on the approach angle, as in the real
    fly: the slopes and r² are those of Tammero and Dickinson 2002 (0.05 and 0.14, r² < 0.01).
  - **The walls.** The fly touches and hugs them less.
  - **The rest.** No-player escapes did not rise, fixed-fly escapes are identical, and the accepted
    saccade statistics hold.
- **What failed.** The upwind share during odor tracking fell from 0.564 to 0.481, below the
  preregistered tolerance of 0.05.

## 2. Wall turns (P1, P2, D1)

Wall runs on seeds 974101-974124 (24 × 180 s, no player, pointer parked):

| | Baseline v32 | Candidate v33 |
|---|---|---|
| Airborne time | 3,254 s | 3,331 s |
| AVOID per airborne s | 0.089 | 0.096 |
| AVOID amplitude, median (p10-p90) | 80° (39-98°) | 87° (66-113°) |
| Signed turn on signed approach angle, right / left turns | slope 1.00 / 1.00, r² 1.000 / 1.000 | slope 0.09 / 0.01, r² 0.015 / 0.000 |
| AVOID turning away from the wall | 100 % | 100 % |
| AVOID clearance, median | 3.3 BL | 3.2 BL |
| AVOIDs within 1 s of another | 38 | 47 |
| DEPART per airborne s | 0.028 | 0.015 |
| Wall-contact onsets per airborne minute | 0.129 | 0.072 |
| Near-wall share of airborne time | 0.145 | 0.114 |

- **Leaving walls.** A full saccade away from the wall takes the fly out of the perimeter zone. Fewer
  DEPARTs are needed, and the fly spends less time near walls.
- **The stated risk.** The risk of repeated AVOIDs after a 60° head-on turn did not lead to more
  contacts. AVOIDs within 1 s of another rose from 38 to 47, while contacts fell.

## 3. Escapes (P4, P5, D3)

**P4.** Paired no-player flight on seeds 974201-974280 (80 × 180 s), classified by the N4B4
counterfactual method (categories as in results/game/M3_8_SACCADE_ODOR.md, section 3):

| Arm | Escapes | Per minute (95 % upper) | A | B | C | D |
|---|---|---|---|---|---|---|
| v32 | 16 | 0.067 (0.101) | 0 | 1 | 4 | 11 |
| v33 | 12 | 0.050 (0.081) | 0 | 2 | 1 | 9 |

- **Shared seeds.** 62 of 80 seeds have identical escape ticks in both arms.
- **The earlier standard.** The candidate meets the category-B standard (under 0.1 per minute at
  95 %).
- **The baseline on these seeds.** v32 has 16 escapes here, against 9 on M3.8's seeds, which shows
  the seed-set variation of this count.

**P5.** Protocol E on seeds 974301-974324: 384 of 384 trials have identical escapes in both arms.

**D3.** Encounters with the paddle, from P6's runs: 97 against 90 (1.04 and 0.98 per airborne
minute). 0.052 and 0.033 of them end in an escape (6 and 4 escapes).

## 4. Odor tracking (P6)

Runs on seeds 974401-974440 (40 × 180 s):

| | Baseline v32 | Candidate v33 |
|---|---|---|
| ODOR_TRACK airborne minutes | 15.9 | 13.7 |
| Upwind share | 0.564 | **0.481** |
| AVOID starts during ODOR_TRACK | 4 (0.25 per min) | 1 (0.07 per min) |

**A read-only look after the result (not preregistered).**
- **The difference is not seed noise.** Resampling seeds, the candidate-minus-baseline difference is
  −0.083, with a 95 % bootstrap interval of [−0.135, −0.034].
- **It is not caused by AVOIDs during tracking.** Those are rare in both arms, and 96-97 % of the
  tracking ticks come more than 4 s after any AVOID. The lower share holds there too (0.564 against
  0.482).
- **What it must come from.** How tracking starts and proceeds, for example where the fly is when
  it meets an odor and from which side. It is not the turn executed during tracking.
- **What is unexplained.** These data do not identify the mechanism. This is the open question.

## 5. Flight and ecology (P3, D2)

`tools/kinematics_sanity.py`, six fixed seeds, 180 s each. The pathology screen reports no failure.

| | Baseline v32 | Candidate v33 |
|---|---|---|
| Turn requests per airborne minute: SACCADE / AVOID / DEPART / CORRECTION | 19.3 / 5.9 / 1.9 / 2.4 | 17.5 / 5.1 / 0.9 / 2.2 |
| Occupancy: EXPLORE / TRANSIT / ODOR_SEARCH / ODOR_TRACK | 0.404 / 0.281 / 0.108 / 0.201 | 0.339 / 0.226 / 0.125 / 0.297 |
| Odor detected share of alive time | 0.238 | 0.362 |
| Odor encounters per alive minute | 1.44 | 1.78 |
| ODOR_TRACK share heading upwind | 0.471 | 0.420 |
| Food touchdowns / other touchdowns | 12 / 1 | 17 / 0 |
| Airborne / perched / feeding fractions | 0.869 / 0.131 / 0.128 | 0.797 / 0.203 / 0.203 |
| Visited share of the 10 BL grid | 0.457 | 0.444 |
| Near-wall share of airborne time | 0.145 | 0.106 |
| Escape onsets (no player) | 0 | 2 |

- **More odor contact and more feeding.** On these seeds the candidate meets odor more often and
  lands on food more often. That could fit the open question in section 4: more tracking toward
  food, with less of it upwind.
- **The sample.** Six seeds; as in M3.8, this comparison is descriptive.

## 6. What the result means

- **The wall-turn amplitude can match the real fly.** It needs only class-B parameters and no
  frozen system, and P1 passed with margin.
- **It is not neutral for odor tracking.** The upwind share falls by about 0.08.
  - **What is excluded.** The cause is not the wall turns made during tracking.
  - **What is left.** It lies in how the fly's trajectories reach and follow odor, which the data
    here do not resolve.
- **The real fly gives no reason to expect this cost.** Its wall saccades are fixed-amplitude, and it
  tracks upwind in odor. So the drop points to an interaction inside the model's ecology rather
  than to a trade-off in the real fly.
- **Decision under the rule.** v32 stays. Any next step is a new preregistered milestone or
  read-only research.

## 7. Reproduction

Check out `game_room_config.json` from `7727397` for the candidate arm, and restore it afterwards.

```
NUMBA_NUM_THREADS=1 python tools/m3_9_checks.py walls --arm baseline --lane K --lanes 2        (K = 0, 1; also --arm candidate)
NUMBA_NUM_THREADS=1 python tools/m3_9_checks.py protocol-s --arm baseline --lane K --lanes 2   (also --arm candidate)
NUMBA_NUM_THREADS=1 python tools/m3_9_checks.py protocol-e --arm baseline                       (also --arm candidate)
NUMBA_NUM_THREADS=1 python tools/m3_9_checks.py encounters --arm baseline --candidate-commit 7727397 --lane K --lanes 2
NUMBA_NUM_THREADS=1 python tools/m3_9_checks.py encounters --arm candidate --candidate-commit 7727397 --lane K --lanes 2
python tools/m3_9_checks.py summary --candidate-commit 7727397
NUMBA_NUM_THREADS=1 python tools/kinematics_sanity.py run --commit 925427c --out artifacts/m3_9/kinematics/baseline
NUMBA_NUM_THREADS=1 python tools/kinematics_sanity.py run --out artifacts/m3_9/kinematics/candidate
python tools/kinematics_sanity.py compare --before artifacts/m3_9/kinematics/baseline --out artifacts/m3_9/kinematics/candidate
NUMBA_NUM_THREADS=1 python tools/paired_free_flight_check.py run --arm baseline --lane K --lanes 2 --baseline-commit 925427c \
    --first-seed 974201 --last-seed 974280 --out artifacts/m3_9/free_flight          (also --arm candidate)
NUMBA_NUM_THREADS=1 python tools/paired_free_flight_check.py classify --lane K --lanes 4 --baseline-commit 925427c \
    --first-seed 974201 --last-seed 974280 --out artifacts/m3_9/free_flight          (K = 0-3)
python tools/paired_free_flight_check.py summary --baseline-commit 925427c --first-seed 974201 --last-seed 974280 \
    --out artifacts/m3_9/free_flight
```
