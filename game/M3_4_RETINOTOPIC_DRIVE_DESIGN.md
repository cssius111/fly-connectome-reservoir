# M3.4: retinotopic LPLC2/LC4 drive (preregistration)

Status: **preregistered on 2026-10-23, before any implementation or run.**
Result: V2 and V8a failed, so the decision rule failed (`results/game/M3_4_RETINOTOPIC_DRIVE.md`).
The ROOM configuration stays v27; the v30 candidate is commit `10e12f6`.

**Authorization.**
- On 2026-10-23 the user read the M3.4 research note and authorized writing this
  preregistration.
- After reading it, the same day, they authorized its implementation as written: the
  `Retina.elevation` field, the `retinotopic_v1` mode, the receptive-field build tool, ROOM
  `config_version` 30, the calibration and every check.
- Acceptance remains the user's, after a playtest.

**Basis.**
- **Research note.** `game/M3_4_RETINOTOPIC_DRIVE_RESEARCH.md`.
- **Exploration.** The grid range in section 4 was chosen by `tools/m3_4_receptive_fields.py
  explore` on seeds 930001-930024 (section 4.1). No check below uses those seeds, the research
  seeds 920001-920012 and 920101-920124, or any earlier milestone's validation seeds.

## 1. Purpose

M3.3 (`results/game/M3_3_ESCAPE_DECISION.md`) failed V3 by 2.8 ms and showed two defects in the
threat matrix:
- fast frontal hover-height approaches were almost never escaped;
- a strong left-right asymmetry (C2 0.90 against C1 0.04).

The M3.4 research found that:
- The asymmetry is set off by the paddle's settling creep, which switches on the size-only
  LPLC2 term (M3.3 erratum, section 8).
- Every encoder so far drives all cells of one side with one scalar voltage. The decision
  therefore sits on a knife-edge of that scalar.
- MaleCNS gives each LPLC2 and LC4 cell's receptive field. The connectome's weights onto DNp01,
  DNp02 and DNp11 depend on field position, as Dombrovski et al. 2023 found.

M3.4 drives each cell by the part of the stimulus inside its receptive field:
- recruitment grows smoothly with the area the paddle covers;
- stimulus elevation and front/back position reach the network through the connectome's own
  gradients;
- LPLC2 responds only while the image edge expands at least as fast as the standard LPLC2
  looming stimulus, so the settling creep no longer drives it.

## 2. The change

ROOM only, `config_version` 30. LAB, GAME and every other configuration are unchanged.

### 2.1 Retina

`Retina` gains one field: `elevation`, the angle of the swatter centre above the fly's
horizontal plane, in radians.
- **Projector.** `RetinaProjector` computes it as `atan2(swatter.height, horizontal
  distance)`.
- **Default.** It defaults to 0.0, so every synthetic Retina built by the tools (protocol E, the
  calibration stimulus) stays valid and lies on the horizon.
- **Bottleneck.** It is a property of the same image as `theta` and `azimuth`. It carries no
  world position, pointer or phase, and the strict type checks stay.
- **Recording.** The recorder's per-tick `retina` record gains the key `elevation`. Recordings
  made before M3.4 have no such key and replay with 0.0. The strike summary keys are unchanged.
- **Other encoder modes.** `legacy_v0` and `ache2019_v1` ignore `elevation` and stay
  bit-identical.

### 2.2 Receptive-field data

`data/receptive_fields_v1.npz` holds every LPLC2 and LC4 cell's column weights and column
viewing directions.
- **Build.** A new tool, `tools/build_receptive_fields.py`, writes it with the method of the
  research note (section 2):
  - MaleCNS synapse `optic_column` values;
  - the Zhao et al. 2025 micro-CT eye map, matched by lattice position from the eye centre;
  - the left eye as the mirror image of the right-eye map.
- **Distribution.** The file is built locally, like `data/brain.npz`, and is not committed. The
  eye-map source repository is GPL-3.0, and no derived table enters git.
- **Verification.** The configuration holds the file's SHA256, and the encoder refuses a file
  that does not match.

### 2.3 Encoder

The new gated mode is `encoder.feature_model = retinotopic_v1`, with this block:

| Key | Value | Class | Basis |
|---|---|---|---|
| `scale_volts_per_mv` | calibrated (section 4) | calibrated | the only fitted constant |
| `acceptance_fwhm_deg` | 7.70 | A (measured) | the light-adapted acceptance angle of R1-R6 photoreceptors, the half-maximum width of a Gaussian fit to their receptive fields: 7.70 ± 1.27° (Juusola et al. 2017) |
| `lplc2_min_edge_speed_deg_s` | 10.0 | B | the edge speed of the standard constant-velocity looming stimulus of Klapoetke et al. 2017, to which LPLC2 responds strongly; the paper's text names no slower measured speed. The mode assumes no LPLC2 response below it (see D2). |
| `fields_file`, `fields_sha256` | `data/receptive_fields_v1.npz` and its hash | | provenance |

**The stimulus on the eye.**
- **Direction.** The swatter is a disk centred at direction `u`, where azimuth = π × `Retina.azimuth`
  and elevation = `Retina.elevation`. Directions use the head frame of the eye map: +x forward,
  +y right, +z up.
- **Radius.** The disk has angular radius θ/2.

**Coverage.** For every driven cell i and each of its columns c, let α_c be the angle between
the column direction and `u`.
- **Per column.** Each column sees the disk through a Gaussian acceptance function with
  half-maximum width `acceptance_fwhm_deg`, so σ = 7.70° / 2.355 = 3.27°. The column's share of
  the disk is Φ((θ/2 − α_c) / σ), where Φ is the standard normal distribution function.
- **Per cell.** The coverage is

  `c_i = Σ_c w_ic Φ((θ/2 − α_c) / σ)`

  where w_ic are the cell's column weights, normalised to sum to 1.
- **Both eyes.** A cell is driven only through its own coverage, so a disk drives the cells of
  whichever eye or eyes it covers. A frontal disk drives both eyes. The `Retina.side` rule is
  not used.

**Drive per tick.** Both drives are zero unless θ̇ > 0. The features are the M3.2 published
Ache et al. 2019 terms, unchanged, in mV.

| Cell | Drive (V) | Extra condition |
|---|---|---|
| LC4 | `min(cap, scale × F_LC4(θ̇) × c_i)` | none |
| LPLC2 | `min(cap, scale × F_LPLC2(θ) × c_i)` | only while the edge speed θ̇/2 ≥ `lplc2_min_edge_speed_deg_s` |

- **Cap.** It is the encoder's existing cap, 0.8 V.
- **Effect of the edge-speed condition.**
  - The paddle's settling creep moves the edge at under 0.1°/s, so it drives no LPLC2.
  - On the l/v 10-80 ms calibration looms, the condition removes LPLC2 drive only below 13.6°
    (l/v 80 ms). There the LPLC2 term is under 10 % of its peak.

**Cells.** The same balanced subsets as now, chosen by `encoder_seed`: 91 LPLC2 and 55 LC4 per
side.
- The research note's tables describe exactly these subsets.
- 16 left LC4 cells stay undriven, as in every earlier mode.

**Why this rule and not a pure edge model.**
- **A pure edge model.** It would take LPLC2 size tuning from field geometry alone. Summed over
  the population, it gives a response that grows with the edge's circumference, not the measured
  peak at 42°.
- **This rule.** It uses the terms measured at the giant fiber (Ache et al. 2019) as the per-cell
  drive, distributes them over cells by coverage, and adds the motion requirement.
- **What it becomes in practice.** At the scales the exploration found (section 4.1) the 0.8 V
  cap binds for nearly every cell the disk touches, so in effect the rule recruits cells by
  covered area. The Ache terms still decide when each channel switches on and act on small
  images and slow expansions.
- **New constants.** None, except the sourced edge speed and the measured acceptance angle.

### 2.4 Decoder and everything else

- **Decoder.** M3.3's `same_side_doublet_v1`, unchanged: a doublet ≤ 40 ms, no summed paths,
  alert reference 1.45.
- **Unchanged:**
  - the alert, steering, escape direction and escape strength logic;
  - the refractory period and the brain;
  - the 20 ms tick;
  - every M1.7.x and M1.8 mechanism.
- **Readout.** The escape still runs from the Retina through LC4/LPLC2, MaleCNS and the DN
  readout (`AGENTS.md`).
- **E4.** The escape direction is still read from DNp01 only. E4, front/back, is out of scope.

## 3. Implementation

- **Encoder and data.**
  - `game/perception.py`: the `elevation` field, the projector change and the `retinotopic_v1`
    mode with its validation. The mode refuses a missing or mismatched fields file.
  - `tools/build_receptive_fields.py`: writes `data/receptive_fields_v1.npz`. Its extra
    dependencies are `mmh3` and `rdata`, needed only to build the file.
- **Configuration and record.**
  - `game_room_config.json` v30: the encoder block and the M3.3 decoder block.
  - `tools/m3_4_record.py` writes `results/game/calibration_room_m3_4.json`. It follows the M3.3
    record and also stores the fields file's SHA256 and build provenance.
- **Harnesses.** `tools/m3_4_retinotopic.py`: calibration, V1-V5 and V8, reusing the M3.2/M3.3
  harnesses unchanged except for the stimulus elevation.

## 4. Calibration of the scale

The M3.3 procedure, unchanged except for the stimulus position and the grid:
- **Targets.** The Ache et al. 2019 GF-model peak times for l/v 10, 20, 40 and 80 ms:
  -2.3, -29.7, -81.3 and -183.8 ms.
- **Stimulus.** The paper's 10-90° disk at its electrophysiology position: azimuth 50°,
  elevation 11°, right eye.
- **Seeds.** 600001-600024, the M3.2/M3.3 calibration seeds.
- **Grid.** 31 values in geometric steps from 10 to 320 V/mV (ratio 32^(1/30)), rounded to
  three significant figures:
  10, 11.2, 12.6, 14.1, 15.9, 17.8, 20, 22.4, 25.2, 28.3, 31.7, 35.6, 40, 44.9, 50.4, 56.6,
  63.5, 71.3, 80, 89.8, 101, 113, 127, 143, 160, 180, 202, 226, 254, 285, 320.
- **Admissible values.** At least 50 % escapes at every l/v.
- **Choice.** The smallest summed squared error between the median escape time and the target.
  A tie goes to the smaller scale.
- **Stop rule.** If no value is admissible, the milestone stops and is reported. The grid is not
  extended without an amendment.

### 4.1 Exploration behind the grid

`tools/m3_4_receptive_fields.py explore` ran the calibration stimulus on seeds 930001-930024.
It used the rule of section 2.3 with the Gaussian acceptance edge, and the M3.3 doublet rule
decided each trial.

| Scale (V/mV) | l/v 10 ms | 20 ms | 40 ms | 80 ms | Summed squared error (ms²) |
|---|---|---|---|---|---|
| 5 | 0.83, +26 | 0.58, +11 | 0.92, -17 | 0.96, -74 | 18,661 |
| 10 | 0.79, +26 | 0.88, +11 | 0.83, -37 | 0.96, -94 | 12,501 |
| 20 | 0.83, +6 | 0.83, -9 | 1.00, -57 | 1.00, -134 | 3,581 |
| 40 | 0.88, +6 | 0.58, -9 | 1.00, -37 | 1.00, -174 | 2,541 |
| 80 | 0.67, +6 | 0.88, +11 | 1.00, -77 | 1.00, -214 | 2,661 |
| 160 | 0.83, -14 | 1.00, -9 | 1.00, -97 | 1.00, -234 | 3,341 |
| 320 | 0.79, -14 | 1.00, -9 | 1.00, -117 | 1.00, -214 | 2,781 |
| Target (GF model) | -2.3 | -29.7 | -81.3 | -183.8 | |

Each cell gives the escape fraction and the median escape time in ms relative to collision.

**What the exploration shows:**
- **The grid brackets the minimum.** The error falls steeply up to about 40 V/mV and stays
  near 2,500-3,300 from 40 to 320.
- **The choice may not be stable.** Times step in 20 ms ticks, so the error is lumpy and the
  choice within that plateau may vary from seed to seed.
- **The edge-speed condition barely matters here.** With the logistic edge of the research
  note, the condition changed no l/v 10-40 ms result at any scale from 1 to 30. At l/v 80 ms it
  moved the median by one tick at 2 of 8 scales.
- **The cap binds.** At these scales a cell needs only 2-3 % coverage for the LPLC2 term to
  reach the 0.8 V cap at any size from about 15° to 90°. LC4 reaches the cap at about
  25 % coverage during a fast loom.
  - In effect, the encoder recruits every cell whose field the disk overlaps, at full drive.
  - The Ache size and velocity terms then act mainly on small images and slow expansions.
  - The milestone therefore tests whether recruitment by covered area, read through the
    connectome's own weights, reproduces the escape timing.
- **Fast looms escape late.** At l/v 20 and 40 ms the medians fall 20-45 ms later than the GF
  model's peaks. Several escapes follow the end of the expansion at 90°. V3 (30 ms tolerance at
  l/v 15, 30 and 60 ms) is the check most at risk.

## 5. Validation, with the scale frozen

Seeds 940001-940024 for V2-V4 and V8b; flight seeds 9901-9980 for V6b. None was used before.

| Check | What is run | Criterion |
|---|---|---|
| V1 | The M3.0 protocol E exactly: seeds 500001-500048, four azimuths, four l/v, elevation 0 | **Primary: E2 partial or match (implied threshold 34-74°).** Also E1 at least partial (0.57-1.00). E3-E6 reported. |
| V2 | Start-size invariance: l/v 40, 80 and 160 ms from 5°, 10° and 20°, right azimuth, elevation 0 | At each l/v the median sizes at escape lie within 10° of each other |
| V3 | Held-out l/v of 15, 30 and 60 ms on the calibration stimulus | Median escape time within 30 ms of the GF-model peak (-16.4, -55.7, -132.6 ms) |
| V4 | Static disks (10°, 30°, 60°, 90°) and a receding disk at the calibration position | At most one escape in total |
| V5 | Spontaneous escapes in V1's pre-stimulus seconds | None |
| V6a | The N4B6 threat matrix (`tools/m3_2_threat_matrix.py`), v27 against v30 | Descriptive |
| V6b | Paired no-player flight (`tools/paired_free_flight_check.py`): baseline v27 at `7483e51`, seeds 9901-9980 | The candidate's total escapes are not larger than the baseline's |
| V7 | Unit tests | All pass. New tests are listed below. |
| V8a | Left-right symmetry in V1: E1 escape fraction, left against right azimuth, per l/v | \|difference\| ≤ 0.20 at every l/v |
| V8b | Left-right symmetry on the calibration stimulus mirrored (azimuth ±50°, elevation 11°), l/v 20, 40 and 80 ms | \|difference\| ≤ 0.20 in escape fraction at every l/v |

**Descriptive checks:**
- **D1.** DNp02 and DNp11 spike counts during the V1 front and rear stimuli, reported for a
  later E4 milestone.
- **D2.** V6a repeated with `lplc2_min_edge_speed_deg_s` = 1.0. It shows which threat-matrix
  outcomes depend on the assumed edge-speed bound. It decides nothing, and the frozen value
  stays 10.0.

**V7 tests:**
- `elevation`: its default, the projector's value, and that the recorder key is additive.
- Coverage:
  - monotonic in θ;
  - near 0 for a disk far from the field;
  - near 1 for a disk enclosing the field.
- The edge-speed condition on LPLC2 only.
- A frontal disk drives both eyes.
- Fields file: refusal on a hash mismatch, and validation of the mode's parameter block.
- `legacy_v0` and `ache2019_v1` stay bit-identical.
- The tests use a small synthetic fields file and need no network.

**Predictions, declared now:**
- **E2:** partial or match. Coverage recruitment delays the decision, so the decision size
  rises above M3.3's 38°.
- **V3:** the likeliest failure (section 4.1). The held-out medians are expected 20-35 ms later
  than the GF-model peaks at l/v 15 and 30 ms.
- **V8:** both pass; the creep no longer drives LPLC2.
- **V6a:**
  - the C1/C2 asymmetry disappears;
  - slow approaches and hovering drive almost no LPLC2;
  - fast frontal approaches drive both eyes.
- **V6b:** at or below the v27 baseline.

## 6. Decision rule

- **Playtest candidate.** If all of the following hold, the runtime goes to the user for a
  playtest:
  - V1's primary criterion and its E1 criterion;
  - V2, V3, V4, V5, V6b, V7 and V8.
  - Acceptance is the user's.
- **Acceptance.**
  - It adds a freeze paragraph to `AGENTS.md`.
  - It replaces the ROOM encoder and the N4B1C decoder.
  - It records the `Retina.elevation` change as part of the bottleneck.
- **Failure.** If any of them fails, the result is reported and nothing is tuned. The ROOM
  configuration stays v27.

## 7. Declared consequences

- **Posterior blind spot.** A disk straight behind is invisible until its radius reaches the
  rearmost fields (about 150-165°), so rear looms are seen late, as in the real eye. E1 counts
  lateral trials only.
- **Overhead paddle.** The paddle hovers 20-70° above the horizon, where LPLC2 → DNp01 weights
  are largest, so overhead strikes drive the giant fiber more than a horizontal disk of equal
  size.
- **Slow approaches.** Approaches and hovering whose image edge moves slower than 10°/s drive no
  LPLC2. Most slow threat-matrix approaches will therefore not be escaped. Under v27 the slow
  approaches A1, A2, C1, C2 and C3 were escaped in 0 to 2 of 48 trials each.
- **ALERT.** ALERT turns are unchanged in mechanism, but the different DNp01 activity changes
  how often they occur.
- **E4 stays a gap.** The front/back code reaches DNp02/DNp11, which the frozen policy does not
  read. Using them is a separate, explicitly authorized policy change.

## References

- Ache JM et al. (2019) Curr Biol 29:1073-1081. doi:10.1016/j.cub.2019.01.079
- Dombrovski M et al. (2023) Nature 613:534-542. doi:10.1038/s41586-022-05562-8
- Juusola M et al. (2017) Microsaccadic sampling of moving image information provides
  Drosophila hyperacute vision. eLife 6:e26117. doi:10.7554/eLife.26117
- Klapoetke NC et al. (2017) Nature 551:237-241.
- Zhao A et al. (2025) Nature 646:135-142. doi:10.1038/s41586-025-09276-5
