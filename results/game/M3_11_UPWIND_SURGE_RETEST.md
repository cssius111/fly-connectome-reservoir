# M3.11 result: the upwind surge retested with a baseline-relative saccade check

Status: **failed check P6, 2026-10-30.** The working ROOM configuration is v32 again. The v35
candidate stays in git history at `6153e38`, with its record
`results/game/calibration_room_m3_11.json`. Nothing was tuned or rerun.

**Preregistration.** `game/M3_11_UPWIND_SURGE_RETEST_DESIGN.md` (commit `555ed34`).
- **The change.** The M3.10 upwind surge, unchanged (`ecology.upwind_surge`; v35 is v34 with its
  own version number and record).
- **The one revised check.** P7 is relative to the baseline: the candidate's clock-driven saccade
  rate may be at most 0.03 per s below it. The preregistration states that this criterion was
  chosen after the M3.10 failure.
- **Seeds.** Every check uses fresh seeds.

**Tools.**
- `tools/m3_11_checks.py` for P1, P2, P5, P6, P7, D1 and D3;
- `tools/kinematics_sanity.py` for P3 and D2;
- `tools/paired_free_flight_check.py` for P4.
The baseline arm is v32 at `a5ca216`. Raw data are in `artifacts/m3_11/` (git-ignored).

## 1. Summary

| Check | Baseline v32 | Candidate v35 | Pass condition | Result |
|---|---|---|---|---|
| P1 time from an off-wind entry to within 45° of upwind, median | never (106 of 265 reach it; 1.10 s among those) | **0.16 s** (134 of 201 reach it; 0.14 s among those) | ≤ 0.5 s | pass |
| P2 ODOR_TRACK upwind share | 0.537 | **0.710** | ≥ 0.487 | pass |
| P3 pathology screen | | no failure | no failure | pass |
| P4 no-player escapes, 240 min | 9 | **5** | not more than the baseline | pass |
| P5 fixed-fly escapes, 384 trials | | 384 identical, 0 differing | all identical | pass |
| P6 wall contacts / near-wall share | 0.036 per min / 0.127 | **0.144 per min / 0.170** | ≤ 0.5 per min / ≤ 0.159 | **fail** |
| P7 clock-driven saccades; S3 | 0.299 per s; 76.8° in 80 ms | **0.305 per s**; 76.5° in 80 ms | ≥ 0.269 per s; 60-120°, ≤ 100 ms | pass |

- **What replicated.**
  - **The upwind turn.** After an off-wind entry, the fly comes within 45° of upwind in a median
    0.16 s (M3.10: 0.18 s), against E16's 190 ± 75 ms. In the baseline most such bouts end first.
  - **Odor tracking.** The upwind share rose from 0.537 to 0.710 (M3.10: 0.543 to 0.733).
  - **Saccades.** The clock-driven saccade rate did not fall: 0.305 against 0.299 per s.
  - **Escapes.** Fixed-fly escapes are identical, and no-player escapes did not rise.
- **What failed.**
  - **Near-wall time on the wall runs.** The near-wall share of airborne time rose from 0.127 to
    0.170, above the limit of 1.25 × 0.127 = 0.159. Wall-contact onsets rose from 0.036 to 0.144
    per airborne minute, within their limit.
  - **The same quantity as M3.10's failure.** M3.10 failed P7 through more near-wall time on P7's
    seeds (game/M3_10_FOLLOWUP_RESEARCH.md). Here P7's seeds show no such rise, and the wall runs
    do.

## 2. Odor tracking (P1, P2, D1)

Odor runs on seeds 977401-977440 (40 × 180 s, no player, pointer parked):

| | Baseline v32 | Candidate v35 |
|---|---|---|
| ODOR_TRACK bout entries | 721 | 639 |
| Surge requests / executed | | 213 / 193 |
| Airborne entries more than 45° off upwind | 265 | 201 |
| … that reach 45° within the bout | 106 | 134 |
| Upwind share | 0.537 | 0.710 |
| Upwind share 0-0.5 s / 0.5-1 s / 1-2 s / 2-4 s / > 4 s after entry | 0.27 / 0.34 / 0.48 / 0.73 / 0.77 | 0.61 / 0.76 / 0.72 / 0.69 / 0.77 |
| Upwind share within 200 units of the food | 0.49 | 0.50 |
| Upwind share re-weighted to the baseline's distance to the food | | 0.734 |

- **The surge.** As in M3.10, it turns the fly upwind in the first second of a bout, where the
  baseline is furthest from upwind.
- **Requests that turn no pulse.** 20 of 213 requests were not executed, because a pulse of equal
  or higher priority was active or the policy was steering.

## 3. Escapes and walls (P4, P5, P6)

**P4.** Paired no-player flight on seeds 977201-977280 (80 × 180 s), N4B4 categories:

| Arm | Escapes | Per minute (95 % upper) | A | B | C | D |
|---|---|---|---|---|---|---|
| v32 | 9 | 0.037 (0.065) | 0 | 1 | 3 | 5 |
| v35 | 5 | 0.021 (0.044) | 0 | 0 | 2 | 3 |

- **Shared seeds.** 70 of 80 seeds have identical escape ticks.
- **The earlier standard.** The candidate meets the category-B standard.

**P5.** Protocol E on seeds 977301-977324: 384 of 384 trials identical.

**P6.** Wall runs on seeds 977101-977124 (24 × 180 s):

| | Baseline v32 | Candidate v35 |
|---|---|---|
| Airborne time | 3,318 s | 3,337 s |
| Near-wall share of airborne time | 0.127 | **0.170** |
| Wall-contact onsets per airborne minute | 0.036 | 0.144 |
| AVOID per airborne second | 0.085 | 0.111 |
| DEPART per airborne second | 0.025 | 0.033 |
| Seeds with a higher near-wall share in the candidate | | 17 of 24 |

- **The size of the rise.** The near-wall share difference is +0.043, with a seed-bootstrap 95 %
  interval of [+0.017, +0.069].
- **Not one seed.** The per-seed differences have a median of +0.032.

## 4. Saccades (P7, D3)

Protocol S on seeds 977501-977540 (40 × 180 s):

| | Baseline v32 | Candidate v35 |
|---|---|---|
| Usable airborne time | 5,524 s | 5,459 s |
| SACCADE (clock) | 0.299 per s, 81° | **0.305 per s**, 81° |
| AVOID | 0.100 per s | 0.095 per s |
| DEPART | 0.033 per s | 0.033 per s |
| SURGE | | 0.032 per s, median 83° in 80 ms |
| S1 all spontaneous events | 0.433 per s | 0.466 per s |
| S2 interval mean / median | 1.97 / 1.42 s | 1.91 / 1.47 s |
| S3 median amplitude and duration | 76.8°, 80 ms | 76.5°, 80 ms |

- **The baseline's own value.** v32 scores 0.299 here, below M3.10's absolute lower bound of 0.30.
- **D3, the factors** (`tools/m3_10_saccade_loss.py` on these seeds; candidate / baseline):

| Factor | Baseline v32 | Candidate v35 | Ratio |
|---|---|---|---|
| Clock seconds per airborne second | 0.601 | 0.605 | 1.007 |
| Clock events per clock second | 0.578 | 0.587 | 1.015 |
| SACCADE share of clock events | 0.861 | 0.860 | 0.999 |
| **SACCADE per airborne second** | **0.299** | **0.305** | **1.020** |
| Near-wall share of airborne time | 0.161 | 0.163 | |

- **Near-wall time on these seeds.** The difference is +0.001, with an interval of
  [−0.017, +0.020].

## 5. Flight and ecology (P3, D2)

`tools/kinematics_sanity.py`, six fixed seeds. The pathology screen reports no failure. These
values are identical to M3.10's: the seeds are fixed and the two candidates run the same
configuration.

| | Baseline v32 | Candidate v35 |
|---|---|---|
| Odor detected share of alive time | 0.238 | 0.276 |
| Odor encounters per alive minute | 1.44 | 1.33 |
| ODOR_TRACK share heading upwind | 0.471 | 0.738 |
| Food touchdowns / other touchdowns | 12 / 1 | 14 / 1 |
| Airborne / perched / feeding fractions | 0.869 / 0.131 / 0.128 | 0.811 / 0.189 / 0.186 |
| Visited share of the 10 BL grid | 0.457 | 0.420 |
| Near-wall share of airborne time | 0.145 | 0.159 |
| Escape onsets (no player) | 0 | 0 |

## 6. Near-wall time across seed sets (read-only, after the result)

Not preregistered. It does not change the decision.

**The comparison.** Every surge run so far that records the perimeter flag uses the same
no-player protocol. The near-wall share of airborne time, candidate minus v32, by set:

| Seed set | Seeds | v32 | Surge | Difference (seed bootstrap 95 %) |
|---|---|---|---|---|
| M3.10 P7 (975501-975520) | 20 | 0.157 | 0.190 | +0.033 [+0.011, +0.055] |
| M3.10 replication (976001-976040) | 40 | 0.153 | 0.151 | −0.003 [−0.022, +0.017] |
| M3.10 P6 walls (975101-975124) | 24 | 0.154 | 0.137 | −0.017 [−0.045, +0.011] |
| M3.11 P6 walls (977101-977124) | 24 | 0.127 | 0.170 | +0.043 [+0.017, +0.068] |
| M3.11 P7 (977501-977540) | 40 | 0.161 | 0.163 | +0.001 [−0.017, +0.020] |
| **All five** | **148** | **0.152** | **0.160** | **+0.008 [−0.002, +0.019]** |

- **Pooled.** The pooled difference is +0.008, about 5 %, and its interval includes zero. The
  inverse-variance mean of the five sets is +0.011.
- **The sets disagree.**
  - **The pattern.** Two sets show a clear rise and one a fall.
  - **More than seed noise.** Cochran's Q, from the bootstrap standard errors, is 16.6 on 4
    degrees of freedom (p ≈ 0.002).
  - **The consequence.** A single 24-seed set does not estimate the effect reliably.
  - **Not a run artifact.** The runs are deterministic. Candidate wall seed 977121, run alone in a
    fresh process, reproduces its queued run exactly.
- **Where the time goes** (the odor runs, clearance under 3.4 BL as a stand-in for the flag).
  - **During and after tracking.** Near-wall time is about 0.001 of ODOR_TRACK time and about 0.01
    of the 5 s after a bout, in both arms.
  - **The rest.** Most near-wall time falls in EXPLORE and TRANSIT.
  - **The sign.** On the M3.11 odor seeds the difference is +0.007 [−0.010, +0.023], and on the
    M3.10 odor seeds −0.013 [−0.027, +0.000].
- **What is left.** No mechanism links the surge to the walls in these data. The surge is one
  pulse per bout. It changes the path after it, and the paired runs then diverge.

## 7. What the result means

- **The surge itself replicated.** Its gains on the upwind turn and odor tracking are the same on
  fresh seeds. The clock-driven saccade rate did not fall.
- **It failed a different check.** The near-wall share on the P6 wall runs rose above 1.25 times
  the baseline.
- **Twice, through the same quantity.** Both M3.10 and M3.11 failed through near-wall time on one
  seed set. On the other sets it is unchanged or lower.
- **Decision under the rule.** v32 stays. No further retest of this candidate follows from this
  result.
- **What another attempt would need.** A third test of the same change, under criteria adjusted
  after two failures, would weaken the preregistration. A further attempt would need either:
  - **a mechanism** that explains the near-wall rise, and a design that avoids it; or
  - **a check designed for this noise,** for example P6 on the pooled seed count of section 6,
    preregistered before any data.
  Either is the user's decision.

## 8. Reproduction

Check out `game_room_config.json` from `6153e38` for the candidate arm, and restore it afterwards.

```
NUMBA_NUM_THREADS=1 python tools/m3_11_checks.py odor --arm baseline --candidate-commit 6153e38 --lane K --lanes 2   (K = 0, 1; also --arm candidate)
NUMBA_NUM_THREADS=1 python tools/m3_11_checks.py protocol-s --arm baseline --lane K --lanes 2   (also --arm candidate)
NUMBA_NUM_THREADS=1 python tools/m3_11_checks.py walls --arm baseline --lane K --lanes 2        (also --arm candidate)
NUMBA_NUM_THREADS=1 python tools/m3_11_checks.py factors --arm baseline --candidate-commit 6153e38 --lane K --lanes 2   (also --arm candidate)
NUMBA_NUM_THREADS=1 python tools/m3_11_checks.py protocol-e --arm baseline                       (also --arm candidate)
python tools/m3_11_checks.py summary --candidate-commit 6153e38
NUMBA_NUM_THREADS=1 python tools/kinematics_sanity.py run --commit a5ca216 --out artifacts/m3_11/kinematics/baseline
NUMBA_NUM_THREADS=1 python tools/kinematics_sanity.py run --out artifacts/m3_11/kinematics/candidate
python tools/kinematics_sanity.py summary --out artifacts/m3_11/kinematics/baseline   (also candidate)
python tools/kinematics_sanity.py compare --before artifacts/m3_11/kinematics/baseline --out artifacts/m3_11/kinematics/candidate
NUMBA_NUM_THREADS=1 python tools/paired_free_flight_check.py run --arm baseline --lane K --lanes 2 --baseline-commit a5ca216 \
    --first-seed 977201 --last-seed 977280 --out artifacts/m3_11/free_flight          (also --arm candidate)
NUMBA_NUM_THREADS=1 python tools/paired_free_flight_check.py classify --lane K --lanes 4 --baseline-commit a5ca216 \
    --first-seed 977201 --last-seed 977280 --out artifacts/m3_11/free_flight          (K = 0-3)
python tools/paired_free_flight_check.py summary --baseline-commit a5ca216 --first-seed 977201 --last-seed 977280 \
    --out artifacts/m3_11/free_flight
python tools/m3_11_near_wall.py
```
