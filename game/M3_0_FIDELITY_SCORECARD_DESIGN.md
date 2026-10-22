# M3.0: biological fidelity scorecard (preregistration)

Status: **preregistered on 2026-10-22, before any measurement.** Measurement only. No runtime
code, configuration, record or frozen system changes.

## 1. Purpose and scope

On 2026-10-22 the user set the project's goal: the model fly should behave more like a real
fly. Difficulty is a consequence of that, not a target. M3.0 measures how far the accepted
runtime is from published *Drosophila* behaviour, so that later changes can be chosen by the
largest gaps.

The user chose the scope:
- looming-evoked **escape** (protocol E);
- spontaneous **flight saccades** (protocol S).

Comparators:
- escape: `game/M3_0_ESCAPE_EVIDENCE.md` (rows X..);
- saccades: the M1.8-R0 evidence lock, `game/M1_8_EVIDENCE.md` (rows E..).

Model under test: `main` @ `032e7cc`. That is ROOM `config_version` 27, with:
- the N4B1C decoder and the N4B5R geometry;
- M1.7.2;
- the M1.8-B stages.

## 2. Classification

Each scored metric gets one class:
- **match**: inside the band defined below;
- **partial**: inside the wider band;
- **gap**: outside both;
- **not represented**: the model has no mechanism for the behaviour;
- **not estimable**: the protocol produced too few events to compute the metric.

The bands are fixed here and are not changed after the data are seen.

## 3. Protocol E: a looming disk through the Retina

**Harness.** A research tool, `tools/m3_0_scorecard.py escape`, replaces the Retina that the
projector would produce from the world with a synthetic Retina, once per tick.
- The fly is fixed (fixed-fly-v2): fly motion, collisions and ecology are disabled, as in N4B6.
- The policy is the runtime `FixedEscapePolicy` (N4B1C) built from the configuration. Its escape
  actions are recorded every tick; the fly does not move.
- The synthetic Retina is what a screen looming disk gives a free-standing fly in the lab: a
  stimulus that only the Retina carries. Nothing else of the pipeline is bypassed (encoder,
  MaleCNS, DNp01, decoder).

**Stimulus.**
- **Profile.** Constant l/v, `theta(t) = 2 atan((l/v) / T(t))`, where `T(t)` is the time to
  collision.
- **Start.** It starts at 10°, so the expansion lasts `T0 = (l/v) / tan(5°)` before collision.
- **After collision.** `theta` is held at 180°.
- **Expansion rate.** `theta_dot` is the difference of consecutive ticks, as the projector
  computes it.
- **Pre-stimulus.** One second at the static 10° precedes the onset. A static disk drives the
  encoder with zero, because `encoder.loom_size` is 0.
- **Conditions.**
  - l/v of 10, 20, 40 and 80 ms (the FlyPEZ set, within the 5-80 ms range of S3);
  - azimuth 0 (front), +0.5 (right, 90°), +1.0 (rear) and -0.5 (left, 90°), in the Retina's
    units;
  - the 48 brain-noise seeds of N4B6 (500001-500048);
  - 768 trials in total.
- **Escape.** The first tick from onset to collision + 0.2 s at which the policy issues an
  escape. A trial ends at collision + 0.5 s.

**Metrics.**
- **E1. Escape probability.**
  - What is measured: the fraction of trials with an escape, at the lateral azimuths (+0.5 and
    -0.5), pooled over l/v. It is also reported per l/v.
  - Comparator: X13, 0.82 (pooled over l/v 5-80 ms, free-standing wild type).
  - Bands: match within 0.10 absolute; partial within 0.25.
- **E2. Timing law.**
  - What is measured: for lateral-azimuth escapes, `t_before = T_c - t_escape`, fitted by least
    squares as `t_before = alpha * (l/v) + delta`. The threshold size is
    `theta_th = 2 atan(1/alpha)`.
  - Comparator: X16 (takeoff slope 2.0, SD 0.2; intercept -6 ms, SD 11) and X15 (takeoff
    54°, SD 5°).
  - Bands: theta_th match within 2 SD (44-64°); partial within 4 SD (34-74°).
  - Also reported: delta, and the mean angular size at escape per l/v.
  - At least 3 of the 4 l/v values need 10 or more escapes, otherwise the metric is not
    estimable.
- **E3. Escape before collision at l/v 10 ms.** The fraction is reported descriptively. Its
  comparator, X25 (short mode 30 %, long mode 6 % at r/v 8 ms), is mode-specific.
- **E4. Escape direction.**
  - What is measured: per azimuth, the circular mean of
    `alpha_model = atan2(lateral, forward)` of the escape action. 0° is forward, +90° is the
    fly's right, 180° is backward.
  - Comparator: X04 and X05.

    | Threat | Target |
    |---|---|
    | Front | backward, 180° |
    | Rear | forward, 0° |
    | Right side | halfway between directly away (-90°) and forward: -45° |
    | Left side | +45° |

  - Bands: match within 45° of the target; otherwise gap.
- **E5. Short and long escape modes** (X21-X24). The model issues a single escape action, with no
  wing-raise phase. Its class is **not represented**, unless its escape timing shows two distinct
  modes whose share depends on l/v as in X22.
- **E6. Spontaneous escapes** in the pre-stimulus second. These are reported descriptively.

## 4. Protocol S: spontaneous flight saccades

**Runs.**
- Seeds 9501-9520 (unused elsewhere), 180 s each.
- ROOM at `032e7cc`, with the runtime policy, ecology and lifecycle.
- No player: the pointer is parked at (1920, 388.8), as in `tools/b2b_iii_free_flight_check.py`.

**Samples per tick:**
- alive;
- airborne (lifecycle);
- speed in body lengths per second;
- yaw rate in rad/s;
- the saccade kind;
- the policy's escape action.

**Saccade event.**
- **Definition.** A maximal run of airborne ticks with a yaw rate of at least 7.854 rad/s
  (450°/s, the E11 detector), all of the same sign.
- **Measures.** The amplitude is the absolute sum of yaw rate times dt over the run, in degrees.
  The duration is the run length times dt.
- **Threat-evoked events.** A run that overlaps an ESCAPE or ALERT saccade kind, or begins within
  0.5 s after an escape action, is excluded from the spontaneous set.

**Metrics.**
- **S1. Rate.**
  - What is measured: spontaneous events per airborne second, excluding the 0.5 s after each
    escape.
  - Comparator: E12, 1.37 per s.
  - Bands: match within 25 % (1.03-1.71); partial within a factor 2 (0.685-2.74).
- **S2. Intersaccadic interval.**
  - What is measured: the intervals between consecutive spontaneous onsets within one airborne
    bout; mean and median.
  - Comparator: E11, 809-826 ms, taken as 0.818 s.
  - Bands: on the mean, match within 25 % (0.613-1.022 s); partial within a factor 2
    (0.409-1.636 s).
- **S3. Amplitude and duration.**
  - Comparator: E10, about 90° in under 100 ms.
  - Bands: match if the median amplitude is 60-120° and the median duration is at most 100 ms;
    partial if only one holds; gap if neither.
- **C1. Context, not scored: flight speed.** The mean airborne speed in body lengths per second
  is reported against E02. 26.7 cm/s is 107 body lengths per second at the E01 body length of
  2.5 mm. ROOM's kinematic scale is frozen (`room_kinematic_scale` = 1.0, `AGENTS.md`).

## 5. Known comparability limits, declared before measurement

- **Tick.** The model's tick is 20 ms. At l/v 10 ms the expansion from 10° to collision lasts
  114 ms, which is about six ticks.
- **Takeoff.** The model takes off at its escape decision, with no motor delay. Real takeoffs
  follow wing raise by about 7-11 ms (X18).
- **Elevation.** The synthetic disk has no elevation. The lab disks were at 45-50°.
- **Azimuth.** The Retina passes on only the side of a stimulus, as the sign of the azimuth.
  Front, side and rear on the same side may therefore give identical inputs. This is measured,
  not assumed.
- **Saccade filter.** E12 kept only flight above 5 cm/s. ROOM's speeds lie below that, so no
  speed filter is applied.

## 6. Outputs and stop rules

**Outputs.**
- Raw data under `artifacts/m3_0/` (git-ignored).
- The report `results/game/M3_0_FIDELITY_SCORECARD.md`, with the gap table. Each gap is marked
  as structural (a missing mechanism) or parametric (a mechanism with values off).

**Stop rules.**
- Nothing is tuned.
- If a protocol cannot run as written, the report says so. A change to the protocol is recorded
  as an amendment before its data are read.
- The choice of which gap to address next is the user's.
