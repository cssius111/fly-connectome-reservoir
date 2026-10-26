# M3.8: saccades of about 90°, and no spontaneous turns while tracking an odor upwind (preregistration)

Status: **preregistered 2026-10-26, before any M3.8 candidate data.**

**Authorization.** Under the user's standing instruction of 2026-10-26 to follow the recommended
steps (game/M3_7_SACCADE_DESIGN.md). This milestone touches no frozen system.

**Background.**
- **M3.7** (results/game/M3_7_SACCADES.md) changed three class-B flight parameters.
  - **What passed.** The saccade checks: the clock-driven rate is 0.32 per s, and S3 matches.
  - **What failed.** P4: paired no-player escapes rose from 9 to 15 in 240 minutes.
  - **A noted cost.** The upwind share during odor tracking fell.
- **The follow-up** (game/M3_7_SACCADE_RESEARCH.md, section 5):
  - **Escapes.** Whether the change raises escapes at all is not established: pooled, one-sided
    p ≈ 0.09, and a variant had 3 escapes against v27's 4.
  - **Odor tracking.** The upwind loss comes from saccades during odor tracking.
  - **The variant.** With the ODOR_TRACK clock rate at 0 it restored v27's upwind share exactly,
    at a clock saccade rate of 0.31 per s.
- **The real fly.** Budick and Dickinson 2006: after odor contact flies surge upwind, and in an
  odor cloud they fly fast while maintaining an upwind heading.

## 1. The change

**Configuration only.** The ROOM configuration goes from v27 (commit `7483e51`) to v32.

| Key | v27 | v32 | Basis |
|---|---|---|---|
| `flight.correction.probability` | 0.42 | 0.0 | as M3.7 |
| `flight.saccade.degrees` | [25, 105] | [60, 120] | as M3.7 |
| `flight.saccade.peak_rate_deg_per_second` | [700, 1400] | [1200, 1500] | as M3.7 |
| `ecology.spontaneous_clock_rate.ODOR_TRACK` | 0.35 | 0.0 | straight upwind flight while tracking (Budick and Dickinson 2006); class B in the M1.8-R0 lock |

**Bookkeeping keys.** `config_version` (32), `policy._comment` and `policy.calibration_paths`.

**Unchanged.** Everything else, including every other clock rate. `ODOR_SEARCH` (casting) keeps
1.35.

**The record.** `tools/m3_8_record.py` writes `results/game/calibration_room_m3_8.json`, carrying
the v27 decoder and threshold over as M3.7 did. It refuses any other configuration change.

## 2. Checks

The baseline arm is v27 at `7483e51`. Every seed is fresh. Criteria P1-P5 are those of M3.7,
unchanged.

| Check | What | Pass |
|---|---|---|
| **P1** (primary) | M3.0 protocol S, seeds 973001-973020: detected events from SACCADE requests per usable airborne second | 0.30-0.50 per s |
| **P2** (primary) | M3.0 S3 on the same runs | median 60-120° and ≤ 100 ms |
| **P3** | `tools/kinematics_sanity.py` pathology screen, candidate against baseline, on its six seeds | no failure |
| **P4** | `tools/paired_free_flight_check.py`, seeds 973201-973280 (80 × 180 s) | the candidate's total escapes are not larger than the baseline's |
| **P5** | M3.0 protocol E, seeds 973301-973324, all 16 conditions | identical escapes in every trial |
| **P6** (new) | `tools/m3_7_encounters.py` runs, seeds 973401-973440 (40 × 180 s): share of ODOR_TRACK airborne ticks heading within 45° of upwind | candidate ≥ baseline − 0.05 |

**Descriptive.**
- **D1.** S1 and S2 of M3.0, and the events by kind, on P1's runs.
- **D2.** The `kinematics_sanity` comparison.
- **D3.** From P6's runs: encounters with the paddle and the share ending in an escape.

**The risk to P1, stated beforehand.** The read-only variant gave 0.311 per s, close to the 0.30
bound.

## 3. Decision rule

As in M3.7.
- **If P1-P6 all pass.**
  - **The candidate stays.** v32 and its record remain the working ROOM configuration as a
    candidate.
  - **Acceptance.** It goes to the user for a playtest; acceptance is the user's.
- **If any check fails.**
  - **Restore.** The working configuration returns to v27.
  - **Keep the record.** The candidate stays in git history, and the failure is reported.
  - **No adjustment.** Nothing is tuned or rerun with other values.
- **Afterwards.** No parameter is adjusted toward hit rate, escape rate or any difficulty measure.
