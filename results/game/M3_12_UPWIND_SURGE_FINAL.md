# M3.12 result: the upwind surge, a final test on a larger sample

Status: **all seven checks passed, 2026-10-30.**
- **The configuration.** v36 is the working ROOM configuration, as a candidate, with its record
  `results/game/calibration_room_m3_12.json`.
- **Acceptance.** It goes to the user for a ROOM playtest; acceptance is the user's. Until then,
  v32 stays the accepted configuration.

**Preregistration.** `game/M3_12_UPWIND_SURGE_FINAL_DESIGN.md` (commit `62b1faa`).
- **The change.** The M3.10 upwind surge, unchanged: `ecology.upwind_surge` at 0.07 s and
  1,200-1,500°/s. v36 is v34 and v35 with its own version number and record.
- **The criteria.** M3.11's, unchanged.
- **The samples.** P6 and P7 use 120 fresh seeds each, and share them. Every other check uses
  fresh seeds at M3.11's sample sizes.
- **The candidate.** Commit `2d4a833`.

**Tools.**
- `tools/m3_12_checks.py` for P1, P2, P5, P6, P7 and D1, D3, D4. Its `paired` mode runs each
  P6/P7 session once and writes the wall-run, protocol-S and factor files. Before any M3.12 data,
  `validate` showed that it reproduces M3.11's separate baseline outputs exactly.
- `tools/kinematics_sanity.py` for P3 and D2.
- `tools/paired_free_flight_check.py` for P4.

The baseline arm is v32 at `a5ca216`. Raw data are in `artifacts/m3_12/` (git-ignored).

## 1. Summary

| Check | Baseline v32 | Candidate v36 | Pass condition | Result |
|---|---|---|---|---|
| P1 time from an off-wind entry to within 45° of upwind, median | never (122 of 270 reach it; 1.5 s among those) | **0.16 s** (149 of 215 reach it; 0.14 s among those) | ≤ 0.5 s | pass |
| P2 ODOR_TRACK upwind share | 0.565 | **0.759** | ≥ 0.515 | pass |
| P3 pathology screen | | no failure | no failure | pass |
| P4 no-player escapes, 240 min | 11 | **6** | not more than the baseline | pass |
| P5 fixed-fly escapes, 384 trials | | 384 identical, 0 differing | all identical | pass |
| P6 wall contacts / near-wall share (120 seeds) | 0.090 per min / 0.155 | **0.085 per min / 0.154** | ≤ 0.5 per min / ≤ 0.194 | pass |
| P7 clock-driven saccades; S3 (120 seeds) | 0.299 per s; 76.5° in 80 ms | **0.308 per s**; 77.3° in 80 ms | ≥ 0.269 per s; 60-120°, ≤ 100 ms | pass |

**The two quantities behind the earlier failures**, on these 120 seeds:

| Difference, candidate minus v32 | Value (seed bootstrap 95 %) | Earlier failure |
|---|---|---|
| Near-wall share of airborne time (D4) | −0.001 [−0.013, +0.010] | M3.11 P6: +0.043 on 24 seeds |
| SACCADE requests per airborne second (D3) | +0.009 [−0.003, +0.021] | M3.10 P7: −0.026 on 20 seeds |

- **Neither recurs.** Both intervals exclude the earlier failures' values.
- **The margins.** Both checks pass well inside their limits: the near-wall share by 0.04, and the
  saccade rate by 0.04 per s.

## 2. How to read the pass

**The history.**
- **The tests.** This is the third test of the same change.
  - **M3.10** failed P7 against an absolute band.
  - **M3.11** used a baseline-relative P7, chosen after that failure. It failed P6.
  - **M3.12** was decided after M3.11's failure and its pooled analysis. It keeps M3.11's criteria
    and only enlarges P6 and P7.
- **The risk.** Repeating a test until it passes raises the chance of a false pass.

**What limits that risk here.**
- **The earlier failures did not recur.** Each earlier failure came from one secondary quantity
  on one small seed set. On 120 fresh seeds both quantities sit near zero, with intervals that
  exclude the earlier values (section 1).
- **The pass is not marginal.** Neither check passes at its limit.
- **The primary effect replicated in all three tests.**

| | Median time to 45° | Upwind share, v32 → surge |
|---|---|---|
| M3.10 | 0.18 s | 0.543 → 0.733 |
| M3.11 | 0.16 s | 0.537 → 0.710 |
| M3.12 | 0.16 s | 0.565 → 0.759 |

**What the decision rule does not settle.** Whether the flight looks like a real fly's is the
playtest's question, and acceptance is the user's.

## 3. Odor tracking (P1, P2, D1)

Odor runs on seeds 978401-978440 (40 × 180 s, no player, pointer parked):

| | Baseline v32 | Candidate v36 |
|---|---|---|
| ODOR_TRACK bout entries | 691 | 680 |
| Surge requests / executed | | 231 / 210 |
| Airborne entries more than 45° off upwind | 270 | 215 |
| … that reach 45° within the bout | 122 | 149 |
| Upwind share | 0.565 | 0.759 |
| Upwind share 0-0.5 s / 0.5-1 s / 1-2 s / 2-4 s / > 4 s after entry | 0.29 / 0.35 / 0.49 / 0.81 / 0.78 | 0.63 / 0.78 / 0.78 / 0.79 / 0.80 |
| Upwind share within 200 units of the food | 0.55 | 0.59 |
| Upwind share re-weighted to the baseline's distance to the food | | 0.800 |
| Bout outcomes: TRANSIT / ODOR_SEARCH / ALERT / ESCAPE / end of run | 472 / 158 / 48 / 1 / 12 | 494 / 144 / 33 / 2 / 7 |

- **The surge.** As in M3.10 and M3.11, it turns the fly upwind in the first second of a bout,
  where the baseline is furthest from upwind.
- **Requests that turn no pulse.** 21 of 231 requests were not executed, because a pulse of equal
  or higher priority was active or the policy was steering.

## 4. Escapes (P4, P5)

**P4.** Paired no-player flight on seeds 978201-978280 (80 × 180 s), N4B4 categories:

| Arm | Escapes | Per minute (95 % upper) | A | B | C | D |
|---|---|---|---|---|---|---|
| v32 | 11 | 0.046 (0.076) | 0 | 3 | 2 | 6 |
| v36 | 6 | 0.025 (0.049) | 0 | 2 | 0 | 4 |

- **Shared seeds.** 68 of 80 seeds have identical escape ticks.
- **The earlier standard.** The candidate meets the category-B standard.

**P5.** Protocol E on seeds 978301-978324: 384 of 384 trials identical.

## 5. Walls and saccades (P6, P7, D3, D4)

One no-player session per seed, 978501-978620 (120 × 180 s per arm).

**P6, the wall runs:**

| | Baseline v32 | Candidate v36 |
|---|---|---|
| Airborne time | 16,731 s | 16,317 s |
| Near-wall share of airborne time | 0.155 | **0.154** |
| Wall-contact onsets per airborne minute | 0.090 | 0.085 |
| AVOID per airborne second | 0.096 | 0.101 |
| DEPART per airborne second | 0.029 | 0.027 |
| Seeds with a higher near-wall share in the candidate | | 63 of 120 |

**P7, protocol S:**

| | Baseline v32 | Candidate v36 |
|---|---|---|
| Usable airborne time | 16,724 s | 16,312 s |
| SACCADE (clock) | 0.299 per s, 82° | **0.308 per s**, 82° |
| AVOID | 0.096 per s | 0.100 per s |
| DEPART | 0.029 per s | 0.027 per s |
| SURGE | | 0.031 per s, median 89° in 80 ms |
| S1 all spontaneous events | 0.423 per s | 0.466 per s |
| S2 interval mean / median | 1.99 / 1.46 s | 1.87 / 1.44 s |
| S3 median amplitude and duration | 76.5°, 80 ms | 77.3°, 80 ms |

**D3, the factors** (candidate / baseline):

| Factor | Baseline v32 | Candidate v36 | Ratio |
|---|---|---|---|
| Clock seconds per airborne second | 0.613 | 0.618 | 1.009 |
| Clock events per clock second | 0.564 | 0.570 | 1.011 |
| SACCADE share of clock events | 0.865 | 0.874 | 1.010 |
| **SACCADE per airborne second** | **0.299** | **0.308** | **1.030** |
| Near-wall share of clock seconds | 0.178 | 0.172 | |

## 6. Flight and ecology (P3, D2)

`tools/kinematics_sanity.py`, six fixed seeds. The pathology screen reports no failure. The
comparison is identical to M3.10's and M3.11's: the seeds are fixed and the three candidates run
the same configuration.

| | Baseline v32 | Candidate v36 |
|---|---|---|
| Odor detected share of alive time | 0.238 | 0.276 |
| Odor encounters per alive minute | 1.44 | 1.33 |
| ODOR_TRACK share heading upwind | 0.471 | 0.738 |
| Food touchdowns / other touchdowns | 12 / 1 | 14 / 1 |
| Airborne / perched / feeding fractions | 0.869 / 0.131 / 0.128 | 0.811 / 0.189 / 0.186 |
| Visited share of the 10 BL grid | 0.457 | 0.420 |
| Near-wall share of airborne time | 0.145 | 0.159 |
| Escape onsets (no player) | 0 | 0 |

- **More perching and feeding.** The candidate touches down on the food 14 times against 12, and
  spends more time perched and feeding.
  - **Not earlier.** Its first food touchdown is not consistently earlier on these six seeds.
  - **Its status.** A consequence of the change, not a target.

## 7. The playtest

**What to look at.** Whether the flight looks like a real fly's, not difficulty:
- **On entering the odor plume.** One fast turn upwind within about 0.2 s, then straight upwind
  flight towards the food.
- **Elsewhere.** Straight flight broken by fast turns of about 90°, as under v32.
- **Escapes.** No unprompted escapes near a hovering paddle. Strike escapes as before.
- **No new pathologies.** No jitter, spinning or wall trapping.

**The decision.**
- **If the user accepts v36.** It becomes the accepted ROOM configuration, and the acceptance is
  recorded here.
- **If not.** The working configuration returns to v32, and the reason is recorded here.

## 8. Reproduction

```
NUMBA_NUM_THREADS=1 python tools/m3_12_checks.py validate
NUMBA_NUM_THREADS=1 python tools/m3_12_checks.py paired --arm baseline --lane K --lanes 2      (K = 0, 1; also --arm candidate)
NUMBA_NUM_THREADS=1 python tools/m3_12_checks.py odor --arm baseline --candidate-commit 2d4a833 --lane K --lanes 2   (also --arm candidate)
NUMBA_NUM_THREADS=1 python tools/m3_12_checks.py protocol-e --arm baseline                       (also --arm candidate)
python tools/m3_12_checks.py summary --candidate-commit 2d4a833
NUMBA_NUM_THREADS=1 python tools/kinematics_sanity.py run --commit a5ca216 --out artifacts/m3_12/kinematics/baseline
NUMBA_NUM_THREADS=1 python tools/kinematics_sanity.py run --out artifacts/m3_12/kinematics/candidate
python tools/kinematics_sanity.py summary --out artifacts/m3_12/kinematics/baseline   (also candidate)
python tools/kinematics_sanity.py compare --before artifacts/m3_12/kinematics/baseline --out artifacts/m3_12/kinematics/candidate
NUMBA_NUM_THREADS=1 python tools/paired_free_flight_check.py run --arm baseline --lane K --lanes 2 --baseline-commit a5ca216 \
    --first-seed 978201 --last-seed 978280 --out artifacts/m3_12/free_flight          (also --arm candidate)
NUMBA_NUM_THREADS=1 python tools/paired_free_flight_check.py classify --lane K --lanes 4 --baseline-commit a5ca216 \
    --first-seed 978201 --last-seed 978280 --out artifacts/m3_12/free_flight          (K = 0-3)
python tools/paired_free_flight_check.py summary --baseline-commit a5ca216 --first-seed 978201 --last-seed 978280 \
    --out artifacts/m3_12/free_flight
```
