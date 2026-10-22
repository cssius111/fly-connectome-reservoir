# M3.2: escape feature roles after Ache et al. 2019 (preregistration)

Status: **preregistered on 2026-10-22, before any implementation or run.** Nothing is
implemented yet.

The user's explicit authorization is needed before implementation, because the change touches:
- the accepted encoder (ROOM `config_version` 27);
- the decoder's transfer record.

The parameter values come from the full text of Ache et al. 2019, which the user supplied on
2026-10-22. The PDF is not committed.

## 1. Purpose and scope

M3.0 found that the model escapes far too early: E2 has an implied threshold of 18.6° against
54°. M3.1 (`game/M3_1_ESCAPE_DECISION_RESEARCH.md`) traced the cause to the encoder:
- LPLC2 is driven by expansion velocity alone;
- LC4 is driven by size times velocity.

The literature has the opposite assignment, and the giant fiber (DNp01) sums the two.

M3.2 assigns the encoder's features as Ache et al. 2019 measured them (candidate C1 of M3.1).
- **Unchanged:** the Retina, the projector, MaleCNS, DNp01, the decoder's rules and constants,
  and every frozen M1.7.x and M1.8 mechanism.
- **Not touched:** the front-and-back and escape-mode gaps (E4, E5).

## 2. The source model

Ache et al. 2019, *Curr Biol* 29:1073-1081, doi:10.1016/j.cub.2019.01.079, STAR Methods
"GF Model", equations 3-7. Angles are in degrees, angular velocities in deg/s and potentials in
mV (Figure 3: GF Vm in mV against angular velocity in deg/s).

| Component | Equation | Constants |
|---|---|---|
| LC4, the velocity input | `V_LC4 = C1 * theta_dot(t - d1)` | C1 = 0.0002567, d1 = 0.019 s |
| LPLC2, the size input | `V_LPLC2 = C2 * exp(-(ln theta(t - d2) - ln C3)^2 / (2 C4^2))` | C2 = 1.7, C3 = 42, C4 = 0.52, d2 = 0.019 s |
| Tonic inhibition, independent of LC4 and LPLC2 | `V_i1 = C5 + C6 / (1 + exp(-(theta(t - d3) - C7) / C8))` | C5 = -0.53, C6 = 0.59, C7 = 66, C8 = -11, d3 = 0.0375 s |
| LC4-dependent inhibition | `V_i2 = C9 * exp(-(theta(t - d4) - C10)^2 / (2 C11^2))` | C9 = -0.52, C10 = 26, C11 = 7.8, d4 = 0.011 s |
| Giant fiber | `V_GF = W_LPLC2 V_LPLC2 + W_LC4 V_LC4 + W_i1 V_i1 + W_i2 V_i2`, smoothed over 2.5 ms | W_LPLC2 = 1.45, W_LC4 = 1.62, W_i1 = 2.27, W_i2 = 1 |

The paper ties the GF's peak to the escape: "their summation determines the GF peak response
time, when a spike driving the fly's escape jump is most likely to occur".

## 3. The change

A new encoder mode, set only in ROOM (`config_version` 28):
`encoder.feature_model = "ache2019_v1"`.
- Without the key, or with `"legacy_v0"`, the encoder is bit for bit the current one.
- LAB, GAME and the older configurations keep the legacy mode.

Per tick, from the current Retina alone, so the encoder stays a pure function of the Retina:

```
theta_deg     = degrees(retina.theta)
theta_dot_deg = degrees(retina.theta_dot)
expanding     = retina.theta_dot > 0
LPLC2 voltage = min(cap, s * W_LPLC2 * C2 * exp(-(ln(theta_deg / C3))^2 / (2 C4^2)))  if expanding, else 0
LC4 voltage   = min(cap, s * W_LC4 * C1 * theta_dot_deg)                              if expanding, else 0
```

**Fixed choices:**
- **Constants.** C1-C4, W_LPLC2 and W_LC4 are the published values. `cap` stays 0.8, the
  current per-channel maximum.
- **Expansion gate.** LPLC2 is driven only while the disk expands. Evidence:
  - real LPLC2 does not respond to receding or motion-free darkening stimuli (M3.1 Y5);
  - the paper finds the GF's static-disk response unchanged by silencing LPLC2 or LC4.
  - A static or hovering paddle therefore drives nothing, as now.
- **Delays.** The 19 ms delays d1 and d2 are represented by the network's own 20 ms step from
  LPLC2 and LC4 to DNp01. The encoder adds none.
- **Inhibition.** V_i1 and V_i2 are not encoded:
  - they are inputs to the GF, not LC4 or LPLC2 drive;
  - the source of V_i1 is unidentified;
  - MaleCNS's own inhibitory inputs to DNp01 are kept.
- **Unchanged encoder parts:**
  - the side rule (the sign of the azimuth);
  - the balanced populations (91 LPLC2 and 55 LC4 cells per side);
  - the equal voltage for every cell of a side;
  - the `last_drive` keys that the frozen recorder schema persists.
- **The one free constant** is the scale `s`, in volts per mV, which maps the paper's GF
  millivolts to encoder voltage. It is calibrated once, as fixed in section 4, before any
  validation run.

**Rejected alternatives:**
- **Two separate scales for LPLC2 and LC4.** A second free parameter, where the paper already
  fixes their ratio.
- **Fitting `s` to the behavioural threshold X15/X16.** That would make E2 a calibrated metric.
- **Encoding the inhibitory terms as negative drive.** That would inject inhibition into the
  excitatory projection neurons.

## 4. Calibration of `s` (electrophysiology target, not behaviour)

**Target.** The time of the peak of the paper's full GF model (equations 3-7), relative to
the virtual collision, on the paper's stimulus: a disk expanding from 10° to 90° at constant
l/v, then held. Computed by `tools/m3_2_ache_targets.py`:

| l/v | Peak time | Size at the peak | LPLC2 share at the peak |
|---|---|---|---|
| 10 ms | -2.3 ms | 90.0° | 0.73 |
| 20 ms | -29.7 ms | 67.9° | 0.88 |
| 40 ms | -81.3 ms | 52.4° | 0.94 |
| 80 ms | -183.8 ms | 47.0° | 0.97 |

**Harness.** The protocol-E harness of `tools/m3_0_scorecard.py`, in a new tool:
- a fixed fly, with the synthetic Retina replaced once per tick;
- the stimulus above, at the right azimuth (+0.5), with 1 s at 10° before onset;
- calibration seeds 600001-600024, new and disjoint from the validation seeds;
- provenance recorded as in M3.0.

**Escape time.** The first escape tick from onset, expressed as time relative to the
collision, as in M3.0's `t_before`. The window ends at the target plus 0.3 s.

**Grid and objective.**
- **Grid.** `s` from 0.04 to 0.30 V/mV in steps of 0.01 (27 values). At 0.30 the LPLC2 peak
  drive is 0.74 V, still below the cap.
- **Admissible values.** A value is admissible only if at least 50 % of trials escape within
  the window at every l/v.
- **Objective.** Minimise the sum over the four l/v values of (median escape time - target)².
  A tie goes to the smaller `s`.
- **Stop rule.** If no grid value is admissible, the milestone stops and is reported. The grid
  is not extended without a recorded amendment.

`s` is then frozen and written into the ROOM configuration.

## 5. Validation (with `s` frozen)

| Check | What is run | Criterion |
|---|---|---|
| V1 | The M3.0 protocol E exactly: seeds 500001-500048, 10° to collision, four azimuths, four l/v | E1-E6 are reported with the unchanged M3.0 bands. **Primary criterion: E2 improves from gap to partial or match.** |
| V2 | Start-size invariance: l/v 40 and 80 ms, starts of 5°, 10° and 20°, seeds 600001-600024 | At each l/v the median sizes at escape for the three starts lie within 10° of each other. The current runtime spans 17° at l/v 40 ms and 7° at 80 ms. |
| V3 | Held-out l/v of 15, 30 and 60 ms, on the calibration harness and seeds | The median escape time lies within 30 ms (1.5 ticks) of the GF model's peak: -16.4, -55.7 and -132.6 ms |
| V4 | Non-looming disks: static at 10°, 30°, 60° and 90° for 2 s; receding (90° to 10° at l/v 40 ms); seeds 600001-600024 | At most one escape across all trials, the spontaneous level |
| V5 | Spontaneous escapes in V1's pre-stimulus seconds | None, as in M3.0 (0 in 768 s). Both encoders inject nothing at rest, so this checks the implementation. |
| V6 | ROOM checks of the frozen systems, as their tools define them: the N4B6 threat matrix and the paired no-player free-flight escape check | Descriptive for threat-evoked escapes, which are meant to change. Escapes in no-player flight must not increase. |
| V7 | Unit tests | All existing tests pass unchanged (legacy mode bit-identical). New tests cover the ache2019_v1 mode: pure function; zero for static and receding input; LPLC2 peak at 42°; LC4 linear; cap. |

**Predictions, declared now:**
- **E2.** The calibration targets alone imply alpha = 2.58 and an implied threshold of 42.3°
  (`tools/m3_2_ache_targets.py`). A faithful transfer is therefore expected near 42°. That is
  **partial** against X15's 54° (match needs 44-64°), not match.
- **Why not match.** The paper's GF model peaks earlier than the behavioural takeoff threshold.
  M3.2 does not adjust for that.

## 6. Declared consequences

- **Later escapes.** About 42-50° at escape for slow looms, instead of 13-22°.
- **E3, escape before collision at l/v 10 ms.** It is expected to fall from 100 % towards 0 %.
  - At 42° and l/v 10 ms, 26 ms remain before collision.
  - The model's pipeline needs at least two 20 ms ticks after the drive rises.
- **ALERT.** Less subthreshold DNp01 activity, so less early ALERT turning. The frozen B3a
  mapping is unchanged, but its input changes with it.
- **Game difficulty.** The fly becomes easier to hit. Flight speed stays at the frozen
  kinematic scale, about 14 times slower than a real fly.
- **Decoder.**
  - Its constants separate spontaneous DNp01 coincidences from threat evidence.
  - At rest, both encoders inject nothing, so the spontaneous side is unchanged.
  - The new transfer record for `config_version` 28 carries the decoder block byte for byte, as
    earlier transfer records did. It notes that the threat side changed and that V1-V6 replace
    the calibration-trial check.

## 7. Outputs, decision and stop rules

**Outputs:**
- the calibration and validation data under `artifacts/m3_2/` (git-ignored);
- the report `results/game/M3_2_ESCAPE_FEATURE_ROLES.md`;
- the transfer record `results/game/calibration_room_m3_2.json`.

**Decision and stop rules:**
- **If V1's primary criterion and V2-V5 and V7 hold,** the runtime goes to the user as a
  playtest candidate. Acceptance is the user's, and acceptance adds a freeze paragraph to
  `AGENTS.md`.
- **If any of them fails,** the result is reported and nothing is tuned. Options go to the user.
- **Changes to this design.** Any change after this note is committed is recorded as an
  amendment before the data it affects are read.
- **What stays fixed.** `s` is the only calibrated constant. The Ache constants, the cap and the
  decoder are never adjusted.
