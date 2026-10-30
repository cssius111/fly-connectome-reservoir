# M3.11: the upwind surge retested with a baseline-relative saccade check (preregistration)

Status: **preregistered 2026-10-30, before any M3.11 candidate data.**

**Authorization.** On 2026-10-30 the user chose to retest the M3.10 upwind surge with the revised
check P7 described here. The user's earlier explicit request to modify the ODOR_TRACK steering of
the M1.8 ecology (game/M3_10_UPWIND_SURGE_DESIGN.md) covers the change.

**Why a retest, stated openly.**
- **M3.10's result.** M3.10 (results/game/M3_10_UPWIND_SURGE.md) passed P1-P6 and failed P7: its
  clock-driven saccade rate was 0.282 per s, against an absolute lower bound of 0.30.
- **The follow-up** (game/M3_10_FOLLOWUP_RESEARCH.md).
  - **The cause.** That drop came from more near-wall time on P7's seed set.
  - **The replication.** It does not recur on 40 fresh seeds: −0.006 per s, seed-bootstrap interval
    [−0.024, +0.012].
  - **The band.** v32 itself scores 0.300-0.308 on four seed sets, so the absolute band cannot tell
    no effect from a small drop.
- **The new criterion was chosen after that failure.**
  - **Against M3.10's data.** Its 0.03 per s tolerance would have passed M3.10's own P7 seeds
    (−0.026).
  - **What stands.** The M3.10 result is unchanged: P7 failed there, and v32 stayed.
  - **What M3.11 is.** A new test on fresh seeds. Nothing else changes from M3.10.

## 1. The change

As in M3.10, unchanged. The ROOM configuration goes from v32 to v35. It is v34's configuration with
its own version number and record. The baseline is v32, read from commit `a5ca216`.

| Key | v32 | v35 |
|---|---|---|
| `ecology.upwind_surge.delay_seconds` | absent | 0.07 |
| `ecology.upwind_surge.peak_rate_deg_per_second` | absent | [1200, 1500] |
| `ecology.upwind_surge._comment` | absent | as in v34 |

- **The rule and its gating.** Those of game/M3_10_UPWIND_SURGE_DESIGN.md, section 1. The code is
  already in place, unused.
- **Bookkeeping keys.** `config_version` (35), `policy._comment` and `policy.calibration_paths`.
- **The record.** `tools/m3_11_record.py` writes `results/game/calibration_room_m3_11.json`,
  carrying the v32 decoder and threshold over unchanged.

## 2. Checks

The baseline arm is v32 at `a5ca216`. Every seed is fresh. `tools/m3_11_checks.py` runs the M3.10
tools with M3.11's seeds, output directory and arms. P3 uses `tools/kinematics_sanity.py`, and P4
`tools/paired_free_flight_check.py`.

| Check | What | Pass |
|---|---|---|
| **P1** (primary) | Odor runs on seeds 977401-977440 (40 × 180 s): over airborne ODOR_TRACK entries more than 45° off upwind, the median time to come within 45° of upwind, counting a bout that never does as never | ≤ 0.5 s for the candidate |
| **P2** | The same runs: ODOR_TRACK upwind share | candidate ≥ baseline − 0.05 |
| **P3** | `tools/kinematics_sanity.py` pathology screen on its six seeds | no failure |
| **P4** | `tools/paired_free_flight_check.py`, seeds 977201-977280 (80 × 180 s) | the candidate's total escapes are not larger than the baseline's |
| **P5** | M3.0 protocol E, seeds 977301-977324, all 16 conditions | identical escapes in every trial |
| **P6** | Wall runs, seeds 977101-977124 (24 × 180 s) | contact onsets ≤ max(2 × baseline, 0.5 per min); near-wall share ≤ 1.25 × baseline |
| **P7** (revised) | M3.0 protocol S, seeds 977501-977540 (40 × 180 s, twice M3.10's sample) | clock-driven saccades ≥ baseline − 0.03 per s; S3 median 60-120° and ≤ 100 ms |

**Descriptive.**
- **D1.** Surge requests and executions, the upwind share by time since entry, and bout outcomes.
- **D2.** The `kinematics_sanity` comparison.
- **D3.** The clock-driven saccade rate's factors, as in `tools/m3_10_saccade_loss.py`:
  - clock seconds;
  - events per clock second;
  - the SACCADE share;
  - near-wall time.

## 3. Decision rule

As in M3.7-M3.10.
- **If P1-P7 all pass.**
  - **The candidate stays.** v35 and its record become the working ROOM configuration as a
    candidate.
  - **Acceptance.** It goes to the user for a playtest; acceptance is the user's.
- **If any check fails.**
  - **Restore.** The working configuration returns to v32.
  - **Keep the record.** The candidate stays in git history, and the failure is reported.
  - **No adjustment.** Nothing is tuned or rerun with other values.
- **Afterwards.** No parameter is adjusted toward hit rate, escape rate or any difficulty measure.
