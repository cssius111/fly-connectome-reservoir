# M3.10 result: an upwind surge turn on odor entry

Status: **failed check P7, 2026-10-30.** The working ROOM configuration is v32 again. The v34
candidate stays in git history at `9c2b53d`, with its record
`results/game/calibration_room_m3_10.json`. Nothing was tuned or rerun.

**Preregistration.** `game/M3_10_UPWIND_SURGE_DESIGN.md` (commit `2a24b78`). The user explicitly
agreed to modify the ODOR_TRACK steering of the M1.8 ecology on 2026-10-29.
- **The change.** A new gated block, `ecology.upwind_surge`:
  - **The trigger.** Once per ODOR_TRACK bout, 0.07 s after entry (E16's 190 ms from plume entry
    less the 0.12 s debounce).
  - **The turn.** The ecology requests a turn of the sensed upwind bearing, which the world executes
    as a SURGE pulse at 1,200-1,500°/s.
- **The gating.** The code stays, unused by every current configuration. Without the block its
  tests show the commands unchanged.

**Tools.**
- `tools/m3_10_checks.py` for P1, P2, P5, P6, P7, D1 and D3;
- `tools/kinematics_sanity.py` for P3 and D2;
- `tools/paired_free_flight_check.py` for P4.
The baseline arm is v32 at `e113583`. Raw data are in `artifacts/m3_10/` (git-ignored).

## 1. Summary

| Check | Baseline v32 | Candidate v34 | Pass condition | Result |
|---|---|---|---|---|
| P1 time from an off-wind entry to within 45° of upwind, median | never (95 of 247 reach it; 1.48 s among those) | **0.18 s** (150 of 229 reach it; 0.16 s among those) | ≤ 0.5 s | pass |
| P2 ODOR_TRACK upwind share | 0.543 | **0.733** | ≥ 0.493 | pass |
| P3 pathology screen | | no failure | no failure | pass |
| P4 no-player escapes, 240 min | 12 | **7** | not more than the baseline | pass |
| P5 fixed-fly escapes, 384 trials | | 384 identical, 0 differing | all identical | pass |
| P6 wall contacts / near-wall share | 0.077 per min / 0.154 | **0.058 per min / 0.137** | ≤ 0.5 per min / ≤ 0.192 | pass |
| P7 clock-driven saccades; S3 | 0.308 per s; 75.9° in 80 ms | **0.282 per s**; 75.7° in 80 ms | 0.30-0.50 per s; 60-120°, ≤ 100 ms | **fail** |

- **What worked.**
  - **The upwind turn.** The fly turns upwind at the real fly's timescale. After an off-wind
    entry, it comes within 45° of upwind in a median 0.18 s, against E16's response at
    190 ± 75 ms. In the baseline most such bouts end first.
  - **Odor tracking.** The upwind share rose from 0.543 to 0.733.
  - **No regressions elsewhere.** Escapes did not rise, fixed-fly escapes are identical, and the
    fly touches and hugs walls less.
- **What failed.**
  - **The clock-driven saccade rate.** It fell from 0.308 to 0.282 per usable airborne second, below
    the preregistered lower bound of 0.30.
  - **How close the bound is.** The bound lies within 0.01 of the accepted runtime's own value:
    v32 measured 0.307 (M3.8 seeds), 0.300 (M3.9 seeds) and 0.308 (here).

## 2. Odor tracking (P1, P2, D1, D3)

Odor runs on seeds 975401-975440 (40 × 180 s, no player, pointer parked):

| | Baseline v32 | Candidate v34 |
|---|---|---|
| ODOR_TRACK bout entries | 669 | 739 |
| Surge requests / executed | | 257 / 233 |
| Airborne entries more than 45° off upwind | 247 | 229 |
| … that reach 45° within the bout | 95 | 150 |
| Upwind share | 0.543 | 0.733 |
| Upwind share 0-0.5 s / 0.5-1 s / 1-2 s / 2-4 s / > 4 s after entry | 0.29 / 0.33 / 0.48 / 0.76 / 0.80 | 0.61 / 0.76 / 0.78 / 0.78 / 0.71 |
| Upwind share within 200 units of the food | 0.52 | 0.53 |
| Upwind share re-weighted to the baseline's distance to the food | | 0.769 |

- **The surge.** It turns the fly upwind in the first second of a bout, where the baseline is
  furthest from upwind.
- **Near the food.** The share stays about 0.53 in both arms: there the bilateral cue and the
  approach to landing set the heading.
- **Requests that turn no pulse.** 24 of 257 requests were not executed, because a pulse of equal
  or higher priority was active or the policy was steering.

## 3. Escapes and walls (P4, P5, P6)

**P4.** Paired no-player flight on seeds 975201-975280 (80 × 180 s), N4B4 categories:

| Arm | Escapes | Per minute (95 % upper) | A | B | C | D |
|---|---|---|---|---|---|---|
| v32 | 12 | 0.050 (0.081) | 0 | 3 | 3 | 6 |
| v34 | 7 | 0.029 (0.055) | 1 | 0 | 1 | 5 |

- **Shared seeds.** 66 of 80 seeds have identical escape ticks.
- **The earlier standard.** The candidate meets the category-B standard.

**P5.** Protocol E on seeds 975301-975324: 384 of 384 trials identical.

**P6.** Wall runs on seeds 975101-975124: wall-contact onsets fell from 0.077 to 0.058 per airborne
minute, and the near-wall share from 0.154 to 0.137.

## 4. Saccades (P7)

Protocol S on seeds 975501-975520:

| | Baseline v32 | Candidate v34 |
|---|---|---|
| Usable airborne time | 2,900 s | 2,731 s |
| SACCADE (clock) | 0.308 per s, 80° | **0.282 per s**, 82° |
| AVOID | 0.092 per s | 0.115 per s |
| DEPART | 0.029 per s | 0.034 per s |
| SURGE | | 0.034 per s, median 98° in 100 ms |
| S1 all spontaneous events | 0.428 per s | 0.464 per s |
| S2 interval mean / median | 2.00 / 1.50 s | 1.85 / 1.50 s |
| S3 median amplitude and duration | 75.9°, 80 ms | 75.7°, 80 ms |

**A read-only look after the result** (`tools/m3_10_clock_time.py`, not preregistered). It repeats
these sessions and records the ecology state.
- **The hypothesis that fails.** The drop does not come from more time in ODOR_TRACK, where the
  clock is stopped.
  - **ODOR_TRACK time.** Its share of airborne time is 0.154 in the baseline and 0.148 in the
    candidate.
  - **Outside ODOR_TRACK.** The rate fell from 0.364 to 0.331 per airborne second.
  - **Per clock-weighted second.** Each state's time is weighted by its clock rate. The rate fell
    from 0.408 to 0.375, and 14 of 20 seeds are lower.
- **The size of the difference.** Resampling seeds, the difference per clock-weighted second is
  −0.033, with a 95 % bootstrap interval of [−0.063, −0.002]. It is small, and beyond seed noise
  at the edge.
- **What is unexplained.** These runs do not identify the mechanism.
  - **What changed.** The candidate also makes more AVOIDs and DEPARTs in these runs (0.149 against
    0.121 per s), and it perches more on the six kinematics seeds.
  - **A possible route.** More wall turns and near-wall time could convert clock events into
    corrections, which the flight generator issues instead of saccades near a wall.
  - **The status.** This is not tested.

## 5. Flight and ecology (P3, D2)

`tools/kinematics_sanity.py`, six fixed seeds. The pathology screen reports no failure.

| | Baseline v32 | Candidate v34 |
|---|---|---|
| Odor detected share of alive time | 0.238 | 0.276 |
| Odor encounters per alive minute | 1.44 | 1.33 |
| ODOR_TRACK share heading upwind | 0.471 | 0.738 |
| Food touchdowns / other touchdowns | 12 / 1 | 14 / 1 |
| Airborne / perched / feeding fractions | 0.869 / 0.131 / 0.128 | 0.811 / 0.189 / 0.186 |
| Visited share of the 10 BL grid | 0.457 | 0.420 |
| Near-wall share of airborne time | 0.145 | 0.159 |
| Escape onsets (no player) | 0 | 0 |

## 6. What the result means

- **The upwind surge closes gap O1.** It changes only one gated ecology block, and the fly now
  turns upwind on odor entry at the real fly's timescale. Odor tracking improves markedly.
- **It lowers the clock-driven saccade rate by about 8 %.** P7's absolute band starts just below the
  accepted runtime's own value, so a change of this size crosses it.
  - **Not the cause.** More tracking time.
  - **The cause.** Not identified.
- **Decision under the rule.** v32 stays.
- **What a retest would need.**
  - **Either an understanding of the drop,** with a design that avoids it.
  - **Or a P7 defined relative to the baseline,** for example "not more than 0.03 per s lower".
    That would be a criterion chosen after this failure. It would need its own preregistration and
    the user's agreement.

## 7. Reproduction

Check out `game_room_config.json` from `9c2b53d` for the candidate arm, and restore it afterwards.

```
NUMBA_NUM_THREADS=1 python tools/m3_10_checks.py odor --arm baseline --candidate-commit 9c2b53d --lane K --lanes 2   (K = 0, 1; also --arm candidate)
NUMBA_NUM_THREADS=1 python tools/m3_10_checks.py walls --arm baseline --lane K --lanes 2        (also --arm candidate)
NUMBA_NUM_THREADS=1 python tools/m3_10_checks.py protocol-s --arm baseline --lane K --lanes 2   (also --arm candidate)
NUMBA_NUM_THREADS=1 python tools/m3_10_checks.py protocol-e --arm baseline                       (also --arm candidate)
python tools/m3_10_checks.py summary --candidate-commit 9c2b53d
NUMBA_NUM_THREADS=1 python tools/kinematics_sanity.py run --commit e113583 --out artifacts/m3_10/kinematics/baseline
NUMBA_NUM_THREADS=1 python tools/kinematics_sanity.py run --out artifacts/m3_10/kinematics/candidate
python tools/kinematics_sanity.py compare --before artifacts/m3_10/kinematics/baseline --out artifacts/m3_10/kinematics/candidate
NUMBA_NUM_THREADS=1 python tools/paired_free_flight_check.py run --arm baseline --lane K --lanes 2 --baseline-commit e113583 \
    --first-seed 975201 --last-seed 975280 --out artifacts/m3_10/free_flight          (also --arm candidate)
NUMBA_NUM_THREADS=1 python tools/paired_free_flight_check.py classify --lane K --lanes 4 --baseline-commit e113583 \
    --first-seed 975201 --last-seed 975280 --out artifacts/m3_10/free_flight          (K = 0-3)
python tools/paired_free_flight_check.py summary --baseline-commit e113583 --first-seed 975201 --last-seed 975280 \
    --out artifacts/m3_10/free_flight
NUMBA_NUM_THREADS=1 python tools/m3_10_clock_time.py run --arm baseline --lane K --lanes 2   (also --arm candidate)
python tools/m3_10_clock_time.py summary
```
