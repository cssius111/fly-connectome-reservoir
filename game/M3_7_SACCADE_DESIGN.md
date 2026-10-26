# M3.7: straight flight between saccades of about 90° (preregistration)

Status: **preregistered 2026-10-26, before any candidate data.**

Result: P4 failed (15 no-player escapes against 9), so the decision rule failed and v27 was restored (`results/game/M3_7_SACCADES.md`). P1, P2, P3 and P5 passed. The v31 candidate is commit `c10477d`.

**Authorization.** On 2026-10-26 the user gave a standing instruction to "follow the recommended
steps one by one" ("继续一步一步按照推荐的来"). The recommended step after the M3.7 research was
this preregistration, followed by its implementation. The instruction does not extend to the
frozen connectome or to any other frozen system, and this milestone touches none.

**Background.** game/M3_7_SACCADE_RESEARCH.md found:
- **The model.**
  - **The clock part.** It produces 0.19 detected saccades per s.
  - **Corrections.** In open space 42 % of the clock's events are 5-18° corrections, which the
    450°/s detector does not see.
  - **Size.** Saccades are 25-105° uniform, seen with a median of 59°.
- **The real fly.**
  - **The baseline.** Censi et al. 2013 bound the rate not explained by the visual stimulus at
    about 0.4 per s; their pooled 1.37 per s is mostly stimulus-driven.
  - **Kinematics.** Frye and Dickinson 2004: "During each saccade, the animal changes heading by
    90° over a period of ~50 ms".
  - **Between saccades.** Frye and Dickinson 2004: "Between saccades, Drosophila tends to fly in
    a straight line."

## 1. The change

**Configuration only, in the class-B `flight` block.** No code changes; the ROOM configuration
goes from v27 (commit `7483e51`) to v31. Versions 28-30 were used by the M3.2-M3.4 candidates.

| Key | v27 | v31 | Basis |
|---|---|---|---|
| `flight.correction.probability` | 0.42 | 0.0 | straight flight between saccades (Frye and Dickinson 2004) |
| `flight.saccade.degrees` | [25, 105] | [60, 120] | about 90° (E10; Frye and Dickinson 2004), spread kept |
| `flight.saccade.peak_rate_deg_per_second` | [700, 1400] | [1200, 1500] | about 90° in under 100 ms within the existing 1,500°/s actuator cap |

**Bookkeeping keys:**
- `config_version` becomes 31;
- `policy._comment` is updated;
- `policy.calibration_paths` points to the new record.

**Unchanged.**
- **The flight generator's other parts.**
  - The interval mixture.
  - The correction angles and peaks. Every event near a wall stays a correction.
  - The boundary behaviour (AVOID, DEPART).
- **The actuator bounds** (`saccades.*`, class C).
- **The ecology clock rates and every other ecology key.**
- **Kinematics, the lifecycle, the swatter, the encoder, the decoder and the brain.**

**Random streams.**
- **Same draw counts.** In open space the correction draw is still made, and an event still
  draws one magnitude, one sign and one peak, so the generator consumes the same draws per event.
- **Where divergence comes from.** Trajectories diverge only because pulse sizes and durations
  change, and the clock pauses while a pulse runs.

**Expected.**
- **Rate.** Open-space clock events all become saccades: about 0.19 / 0.58 ≈ 0.33 per s.
- **Size.** A 90° saccade at 1,400°/s lasts 101 ms and is seen as 85° in 80 ms.

## 2. The record

- **The rule.** A record's provenance fingerprints the whole configuration, so v31 needs its own
  record.
- **The tool.** `tools/m3_7_record.py` writes `results/game/calibration_room_m3_7.json`. It
  carries the escape threshold and decoder block of the v27 record
  (`results/game/calibration_room_m1_7_2.json`) over unchanged, and cites that record by content
  SHA256.
- **Why a carry-over is sound.** The escape calibration freezes position, heading, velocity and
  all saccade timers (game/FLIGHT.md). Check P5 tests this.
- **What the tool refuses.** It refuses to write unless the configuration differs from v27 only
  in the keys of section 1.

## 3. Checks

All seeds are fresh. Raw data go to `artifacts/m3_7/` (git-ignored), with the M3.0 provenance
guard. The baseline arm is v27 at `7483e51`.

| Check | What | Pass |
|---|---|---|
| **P1** (primary) | Protocol S of M3.0, unchanged (detector, exclusions, 180 s no-player ROOM runs), seeds 972001-972020. The rate of detected events produced by SACCADE requests (the clock part), per usable airborne second. | 0.30-0.50 per s: Censi et al.'s 0.4 per s within ±25 %, the M3.0 band width |
| **P2** (primary) | S3 of M3.0 on the same runs: all spontaneous events | median amplitude 60-120° and median duration ≤ 100 ms (M3.0's match band) |
| **P3** | The preregistered pathology screen of `tools/kinematics_sanity.py` (game/M1_8_B_COMPLETION_DESIGN.md, check 5): chatter, visited-cell share, touchdowns, perched share. Candidate against baseline on its six seeds. | no failure |
| **P4** | Paired no-player flight (`tools/paired_free_flight_check.py`), baseline v27 at `7483e51`, seeds 972201-972280 (80 × 180 s) | the candidate's total escapes are not larger than the baseline's (as V6b of M3.4) |
| **P5** | M3.0 protocol E (fixed fly, all 16 l/v × azimuth conditions), both arms, seeds 972301-972324 | identical escape ticks in every trial |

**Descriptive** (no pass/fail):
- **D1.** S1 and S2 of M3.0 for both arms on P1's seeds, and the events by kind.
  - **Expected.** S1 stays a gap: about 0.48 per s against 1.37, because that comparator is
    mostly stimulus-driven (research note, section 3).
- **D2.** The `kinematics_sanity` comparison, both arms:
  - state occupancy, speed by state, odor metrics;
  - lifecycle fractions and bouts, time near a wall.
- **D3.** The N4B6 threat matrix (`tools/m3_2_threat_matrix.py`), both arms. More frequent,
  larger turns may change escapes and hits; this is reported, never optimized.

## 4. Decision rule

- **If P1-P5 all pass.**
  - **The candidate stays.** v31 and its record remain the working ROOM configuration as a
    candidate.
  - **Acceptance.** It goes to the user for a playtest; acceptance is the user's.
  - **Tests.** Tests bound to the working configuration are updated to the candidate. Tests of
    frozen behaviour read their configuration from a commit, as before.
- **If any check fails.**
  - **Restore.** The working ROOM configuration returns to v27.
  - **Keep the record.** The candidate stays in git history, and the failure is reported.
  - **No adjustment.** Nothing is tuned and nothing is rerun with other values.
- **Afterwards.** No parameter is adjusted toward hit rate, escape rate or any difficulty
  measure, whatever the outcome.
