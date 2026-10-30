# M3.12: the upwind surge, a final test on a larger sample (preregistration)

Status: **preregistered 2026-10-30, before any M3.12 candidate data.**

**Authorization.** On 2026-10-30 the user chose the option "最后一次大样本重测（推荐）" (one last
retest on a large sample, recommended). The option read: M3.12 keeps the change and every
criterion of M3.11, does not relax P6, and only raises the P6 and P7 samples to 120 fresh seeds.
The preregistration states that this is the last test of the change, and that a failure ends the
line for good. The user's earlier explicit request to modify the ODOR_TRACK steering of the M1.8
ecology (game/M3_10_UPWIND_SURGE_DESIGN.md) covers the change.

**Why another test, stated openly.**
- **M3.11's result** (results/game/M3_11_UPWIND_SURGE_RETEST.md).
  - **What passed.** P1-P5 and P7. The surge's gains replicated.
  - **What failed.** P6 on 24 seeds: the near-wall share rose from 0.127 to 0.170, above the limit
    of 0.159.
- **The follow-up** (section 6 of that report, read-only).
  - **Pooled.** Over five paired seed sets (148 seeds), the surge changes the near-wall share by
    +0.008 [−0.002, +0.019].
  - **The sets disagree.** They disagree more than seed noise predicts (Cochran's Q 16.6 on 4
    degrees of freedom), so one 24-seed set does not estimate the effect reliably.
- **What this test is.**
  - **The history.** It is the third test of this change. The decision to run it was made after
    M3.11's failure and that pooled analysis.
  - **The criteria.** Unchanged from M3.11. M3.11's own baseline-relative P7 was itself chosen
    after the M3.10 failure.
  - **What changes.** Only the sample sizes of P6 and P7, and fresh seeds throughout.
- **What stands.** The M3.10 and M3.11 results are unchanged: each failed one check, and v32
  stayed.
- **This is the last test.** Whatever its result, no further test of the upwind surge follows.

## 1. The change

As in M3.10 and M3.11, unchanged. The ROOM configuration goes from v32 to v36. It is v35's
configuration with its own version number and record. The baseline is v32, read from commit
`a5ca216`.

| Key | v32 | v36 |
|---|---|---|
| `ecology.upwind_surge.delay_seconds` | absent | 0.07 |
| `ecology.upwind_surge.peak_rate_deg_per_second` | absent | [1200, 1500] |
| `ecology.upwind_surge._comment` | absent | as in v34 and v35 |

- **The rule and its gating.** Those of game/M3_10_UPWIND_SURGE_DESIGN.md, section 1. The code is
  already in place, unused.
- **Bookkeeping keys.** `config_version` (36), `policy._comment` and `policy.calibration_paths`.
- **The record.** `tools/m3_12_record.py` writes `results/game/calibration_room_m3_12.json`,
  carrying the v32 decoder and threshold over unchanged.

## 2. Checks

The baseline arm is v32 at `a5ca216`. Every seed is fresh. The criteria are those of
game/M3_11_UPWIND_SURGE_RETEST_DESIGN.md, section 2.

| Check | What | Pass |
|---|---|---|
| **P1** (primary) | Odor runs on seeds 978401-978440 (40 × 180 s): over airborne ODOR_TRACK entries more than 45° off upwind, the median time to come within 45° of upwind, counting a bout that never does as never | ≤ 0.5 s for the candidate |
| **P2** | The same runs: ODOR_TRACK upwind share | candidate ≥ baseline − 0.05 |
| **P3** | `tools/kinematics_sanity.py` pathology screen on its six seeds | no failure |
| **P4** | `tools/paired_free_flight_check.py`, seeds 978201-978280 (80 × 180 s) | the candidate's total escapes are not larger than the baseline's |
| **P5** | M3.0 protocol E, seeds 978301-978324, all 16 conditions | identical escapes in every trial |
| **P6** | Wall runs, seeds 978501-978620 (**120** × 180 s) | contact onsets ≤ max(2 × baseline, 0.5 per min); near-wall share ≤ 1.25 × baseline |
| **P7** | M3.0 protocol S, the same 120 seeds | clock-driven saccades ≥ baseline − 0.03 per s; S3 median 60-120° and ≤ 100 ms |

**The shared P6 and P7 sessions.**
- **The same protocol.** The wall runs (`tools/m3_9_checks.py`) and protocol S
  (`tools/m3_7_saccades.py`) run the same session: no player, pointer parked, 9,000 ticks. In
  M3.11 they used separate seed sets.
- **One runner.** Here `tools/m3_12_checks.py paired` runs each session once. It writes the
  wall-run file, the protocol-S file and the D3 factor file of `tools/m3_10_saccade_loss.py`, in
  their existing formats, so the existing summaries apply unchanged.
- **Its validation, before any M3.12 data.** On M3.11's baseline seeds 977101 and 977501, it must
  reproduce the separate tools' outputs exactly.

**The sample.**
- **M3.11's spread.** It puts the seed-bootstrap half-width of the near-wall difference on 120
  seeds at about ±0.012.
- **P6's margin.** About 0.04 (0.25 × baseline).
- **The caution.** Section 6 of the M3.11 report found that seed sets disagree more than that
  spread predicts.

**Descriptive.**
- **D1.** Surge requests and executions, the upwind share by time since entry, and bout outcomes.
- **D2.** The `kinematics_sanity` comparison.
- **D3.** The clock-driven saccade rate's factors on the 120 P7 seeds, as in
  `tools/m3_10_saccade_loss.py`.
- **D4.** The near-wall difference with its seed-bootstrap 95 % interval.

## 3. Decision rule

As in M3.7-M3.11.
- **If P1-P7 all pass.**
  - **The candidate stays.** v36 and its record become the working ROOM configuration as a
    candidate.
  - **Acceptance.** It goes to the user for a playtest; acceptance is the user's.
- **If any check fails.**
  - **Restore.** The working configuration returns to v32.
  - **Keep the record.** The candidate stays in git history, and the failure is reported.
  - **No adjustment.** Nothing is tuned or rerun with other values.
  - **The line ends.** The gated code stays unused, and no further test of the upwind surge is
    run.
- **Afterwards.** No parameter is adjusted toward hit rate, escape rate or any difficulty measure.
