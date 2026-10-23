# M3.3: size-tuned encoder and a same-side doublet decoder (preregistration)

Status: **preregistered on 2026-10-23, before any implementation or run.**

**Authorization.** The change replaces the frozen N4B1C decoder of the ROOM configuration.
- On 2026-10-23 the user authorized writing this preregistration.
- After reading it, the same day, they authorized its implementation as written: the decoder
  replacement in ROOM `config_version` 29, the calibration and every check.
- Acceptance remains the user's, after a playtest.

**Correction before any run (2026-10-23).** The first version (`523ff2d`) named seeds
800001-800024 for V2-V4. N4B7 (`tools/n4b7_candidates.py`) had already used them. They are
replaced by the unused seeds 810001-810024.

**Basis.** The read-only research note `game/M3_3_ESCAPE_DECISION_RESEARCH.md` (`3c9dfb2`). The
design was chosen there by exploration on seeds 700001-700024 and flight seeds 9701-9720. No
check below uses those seeds.

## 1. Purpose

M3.2 (`results/game/M3_2_ESCAPE_FEATURE_ROLES.md`) failed on two counts:
- **E2.** The implied threshold of 30° is still a gap.
- **No-player flight.** Escapes rose tenfold.

The research traced both to the decoder's summed N2b paths, FAST and SUSTAINED. They integrate
slow, bilateral DNp01 activity:
- they fired 63 of the 65 inappropriate M3.2 escapes;
- they pull the loom decision early.

M3.3 combines the M3.2 encoder with a decoder that escapes only on a same-side DNp01 doublet.

## 2. The change

ROOM only, `config_version` 29. LAB, GAME and every other configuration are unchanged.

**Encoder.**
- `encoder.feature_model = ache2019_v1`, the M3.2 mode, unchanged:
  - LPLC2 by the Gaussian of log size and LC4 linearly by angular velocity;
  - both only while the stimulus expands;
  - the published constants held in code.
- `encoder.ache2019.scale_volts_per_mv` is recalibrated (section 3).
- No motion gate.

**Decoder.** A new kind, `policy.escape_decoder.kind = same_side_doublet_v1`, with these keys:

| Key | Value | Role |
|---|---|---|
| `doublet_window_ms` | 40 | the two spikes of one side are at most 2 samples apart |
| `required_spikes` | 2 | only 2 is supported |
| `alert_reference_threshold` | 1.45 | the summed-trace level the unchanged alert, turn and strength logic is scaled by; it fires nothing |

**How the new decoder decides:**
- **Spikes.** Per-side spikes are inferred from that side's DNp01 trace exactly as the N4B1C
  LATERAL path does: `trace_t - decay * trace_{t-1} >= 0.5`.
- **Escape.** It fires when the current sample has a spike on one side and that side's previous
  spike was at most 2 samples earlier, outside the refractory period.
- **Memory.** Left and right are independent. Spike history is updated on every sample and is
  cleared when an escape fires.
- **No summed paths.** The summed FAST and SUSTAINED paths do not exist in this kind.

**What stays the same:**
- the refractory period (0.4 s);
- the alert threshold fraction, steering, alert saccades, the escape direction (DNp01 contrast
  plus the forward bias) and the escape strength (`min(1, total / (2 * 1.45))`);
- every existing decoder kind, which stays bit-identical for the configurations that use it.

**Why the decoder looks like this:**
- **Biology.** The giant fiber triggers escape with a single spike (Ache, Namiki et al. 2019)
  near the peak of its looming response (Ache et al. 2019).
- **Why not a single spike.** The model's DNp01 fires spontaneously at 0.30-0.45 Hz, so a
  single-spike rule would escape 0.75 times per second at rest.
- **Why a 40 ms doublet.** At rest no two spikes of one side are closer than 6 ticks. The
  same-side 40 ms doublet is therefore the strongest single-side event that noise never
  produces.
- **Class.** The window is a Class C simulator-derived constant, chosen in M3.3's exploration.

**Unchanged systems:**
- the Retina, the projector, MaleCNS and DNp01;
- the 20 ms tick and the brain noise;
- every M1.7.x and M1.8 mechanism.

The escape still runs from the Retina through LC4/LPLC2, MaleCNS and the DN readout (`AGENTS.md`).

## 3. Calibration of the scale

The M3.2 procedure, unchanged except for the decoder and the grid:
- **Targets.** The peak times of the Ache et al. 2019 GF model (`tools/m3_2_ache_targets.py`):
  -2.3, -29.7, -81.3 and -183.8 ms for l/v 10, 20, 40 and 80 ms.
- **Stimulus and seeds.** The paper's 10-90° stimulus, right azimuth, seeds 600001-600024.
- **Grid.** 0.20 to 0.50 V/mV in steps of 0.01 (31 values).
- **Admissible values.** At least 50 % escapes at every l/v.
- **Choice.** The smallest squared error between the median escape time and the target, summed
  over the four l/v values. A tie goes to the smaller scale.
- **Stop rule.** If no value is admissible, the milestone stops and is reported. The grid is not
  extended without an amendment.

## 4. Validation, with the scale frozen

| Check | What is run | Criterion |
|---|---|---|
| V1 | The M3.0 protocol E exactly: seeds 500001-500048, four azimuths, four l/v | **Primary: E2 is partial or match (implied threshold 34-74°).** Also E1 at least partial (0.57-1.00). E3-E6 reported. |
| V2 | Start-size invariance: l/v 40, 80 and 160 ms from 5°, 10° and 20°, seeds 810001-810024 | At each l/v the median sizes at escape lie within 10° of each other |
| V3 | Held-out l/v of 15, 30 and 60 ms on the calibration stimulus, seeds 810001-810024 | Median escape time within 30 ms of the GF model's peak (-16.4, -55.7, -132.6 ms) |
| V4 | Static disks (10°, 30°, 60°, 90°) and a receding disk, seeds 810001-810024 | At most one escape in total |
| V5 | Spontaneous escapes in V1's pre-stimulus seconds | None |
| V6a | The N4B6 threat matrix (`tools/m3_2_threat_matrix.py`), v27 against v29 | Descriptive |
| V6b | Paired no-player flight (`tools/paired_free_flight_check.py`), baseline v27 at `b5e6021`, fresh seeds 9801-9880 | The candidate's total escapes are not larger than the baseline's |
| V7 | Unit tests | All pass. New tests cover the new decoder kind: the doublet rule, independent sides, refractory, no summed paths, and that existing kinds are unchanged. |

**Predictions, declared now:**
- **E2:** partial, with a threshold of about 34-40°.
- **E1:** below 1, in the partial or match band.
- **V6b:** at or below the v27 baseline.
- **V6a:** fewer escapes for hovering and slow-approach trajectories than v27.

## 5. Decision rule

- **Playtest candidate.** If all of the following hold, the runtime goes to the user for a
  playtest:
  - V1's primary criterion and its E1 criterion;
  - V2, V3, V4, V5, V6b and V7.
  - Acceptance is the user's.
- **Acceptance.** It adds a freeze paragraph to `AGENTS.md` and replaces the N4B1C decoder in
  ROOM.
- **Failure.** If any of them fails, the result is reported and nothing is tuned. The ROOM
  configuration stays v27.

## 6. Declared consequences

- **Hovering paddle.** A paddle that hovers on alternating sides without expanding will rarely
  trigger escapes. N4B1C kept the summed paths for exactly that case. This is closer to the
  real fly, but it changes the accepted gameplay.
- **Fast strikes.** Some fast strikes will not be escaped, so E1 drops below 1. The fly is
  likely to be easier to hit.
- **ALERT.** ALERT turns are unchanged in mechanism, but less DNp01 activity changes how often
  they occur.
