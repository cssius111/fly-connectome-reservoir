# M3.9: wall-evoked saccades of fixed amplitude (preregistration)

Status: **preregistered 2026-10-29, before any M3.9 candidate data.**

Result: P6 failed (ODOR_TRACK upwind share 0.481 against 0.564), so the decision rule failed and v32 was restored (`results/game/M3_9_WALL_SACCADES.md`). P1-P5 and P7 passed. The v33 candidate is commit `7727397`.

**Authorization.** The user chose option A on 2026-10-29: preregister M3.9. This milestone touches
no frozen system: the AVOID parameters are class B or C in the M1.8-R0 evidence lock, and none is
named in `AGENTS.md`.

**Background** (game/M3_9_WALL_SACCADE_RESEARCH.md).
- **The real fly** (Tammero and Dickinson 2002).
  - **Amplitude.** Wall-evoked saccades are about ±90°. Within each turn direction, the
    regression of saccade angle on approach angle has a slope of 0.05 or 0.14, and r² < 0.01.
  - **Direction.** It depends on the approach angle.
  - **Trigger.** It is a large-field expansion threshold, not time to collision.
- **The model (v32).**
  - **Amplitude.** AVOID turns onto the wall tangent plus 14°, so its amplitude is
    104° − |approach angle| (r² 1.00).
  - **Trigger.** It fires at a time to contact of 0.54 s.
  - **Direction.** It always turns away from the wall.

## 1. The change

The ROOM configuration goes from v32 to v33. The baseline is v32, read from commit `925427c`; its
configuration is identical to the accepted `ce0c745`.

| Key | v32 | v33 | Basis |
|---|---|---|---|
| `flight.boundary.avoid_degrees` (new) | absent: the tangent rule | [60, 120] | W1: a fixed amplitude independent of the approach angle; the same interval as the accepted spontaneous saccades |
| `flight.boundary.avoid_peak_rate_deg_per_second` | [700, 1300] | [1200, 1500] | one stereotyped saccade program; the same interval as the accepted spontaneous saccades |

**The rule** in `game/flight.py`, gated by the new key:
- **With `avoid_degrees`.**
  - **Amplitude.** AVOID draws its amplitude uniformly from the interval, independent of the
    approach angle.
  - **Direction.** It turns away from the wall: the sign opposite to the wall's bearing. A head-on
    tie keeps the seeded side, as now.
- **Without it.** The tangent rule is unchanged: LAB, GAME and every older configuration run as
  before.

**Unchanged.**
- The time-to-contact trigger (0.55 s), now a declared world convention (W3), and the eligibility
  gate that uses `avoid_inward_degrees`.
- The refractory period, DEPART and the perimeter hysteresis.
- Every M3.8 value frozen in `AGENTS.md`, and every other system.

**Bookkeeping keys.** `config_version` (33), `policy._comment` and `policy.calibration_paths`.

**The record.** `tools/m3_9_record.py` writes `results/game/calibration_room_m3_9.json`, carrying the
v32 decoder and threshold over as M3.8 did. It refuses any other configuration change.

## 2. Checks

The baseline arm is v32. Every seed is fresh. The tools are `tools/m3_9_checks.py` (P1, P2, P5,
P6, P7 and D1, D3), `tools/kinematics_sanity.py` (P3, D2) and `tools/paired_free_flight_check.py`
(P4).

| Check | What | Pass |
|---|---|---|
| **P1** (primary) | Candidate AVOID requests on wall runs, seeds 974101-974124 (24 × 180 s, no player, pointer parked) | within each turn direction, signed turn on signed approach angle has \|slope\| ≤ 0.2 and r² ≤ 0.05; the median amplitude is within 60-120°; every AVOID turns away from the wall |
| **P2** | The same runs, both arms: wall-contact onsets (containment acting) per airborne minute, and the near-wall share of airborne time | contact onsets ≤ max(2 × baseline, 0.5 per min); near-wall share ≤ 1.25 × baseline |
| **P3** | `tools/kinematics_sanity.py` pathology screen, candidate against baseline, on its six seeds | no failure |
| **P4** | `tools/paired_free_flight_check.py`, seeds 974201-974280 (80 × 180 s) | the candidate's total escapes are not larger than the baseline's |
| **P5** | M3.0 protocol E, seeds 974301-974324, all 16 conditions | identical escapes in every trial |
| **P6** | `tools/m3_7_encounters.py` runs, seeds 974401-974440 (40 × 180 s): share of ODOR_TRACK airborne ticks heading within 45° of upwind | candidate ≥ baseline − 0.05 |
| **P7** | M3.0 protocol S, seeds 974501-974520: the accepted saccade statistics | clock-driven saccades 0.30-0.50 per s; S3 median 60-120° and ≤ 100 ms |

**Descriptive.**
- **D1.** From P1's runs, both arms:
  - wall-turn rates;
  - AVOID amplitude and clearance;
  - DEPART rate and repeated AVOIDs within 1 s.
- **D2.** The `kinematics_sanity` comparison, including the visited share and food touchdowns.
- **D3.** From P6's runs: encounters with the paddle, and the share ending in an escape.

**Risks stated beforehand.**
- **P2.** A head-on approach with a 60° turn still closes on the wall, at half the speed. More
  repeated AVOIDs and contacts are possible.
- **P4.** M3.7 failed this check within Poisson noise. Any change of where the fly flies can move
  its encounters with the hovering paddle.

## 3. Decision rule

As in M3.7 and M3.8.
- **If P1-P7 all pass.**
  - **The candidate stays.** v33 and its record become the working ROOM configuration as a
    candidate.
  - **Acceptance.** It goes to the user for a playtest; acceptance is the user's.
- **If any check fails.**
  - **Restore.** The working configuration returns to v32.
  - **Keep the record.** The candidate stays in git history, and the failure is reported.
  - **No adjustment.** Nothing is tuned or rerun with other values.
- **Afterwards.** No parameter is adjusted toward hit rate, escape rate or any difficulty measure.
