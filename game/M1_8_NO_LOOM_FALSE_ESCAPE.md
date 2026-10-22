# No-loom neural false escape: defect note

Status: **design and research only. Nothing implemented, no fix selected.** No threshold,
no brain parameter, no calibration, no runtime code and no configuration was changed.

Tracked separately from M1.8-B2b-ii, which did **not** introduce this. Evidence and the
full recorded windows are in
[results/game/M1_8_B2B_II.md](../results/game/M1_8_B2B_II.md) section 11a,
`artifacts/m1_8_b2b_ii/escape-provenance.json` and
`artifacts/m1_8_b2b_ii/perched-noise.json`.

## 1. The defect

A physically **PERCHED** fly, with a **stationary swatter**, **zero strikes**, constant
retinal `theta`, `theta_dot` exactly **0.00000** and **LC4/LPLC2 drive exactly 0.0000 on
all four channels**, can still cross the DNp01 escape threshold and emit
`TAKEOFF_ESCAPE`. The cause is spontaneous MaleCNS background activity accumulating in the
DNp01 trace.

This violates the simulator semantic that `TAKEOFF_ESCAPE` represents a **threat-triggered**
escape downstream of a real visual stimulus. It is a false positive, not a threat response,
and it must not be described or reported as one.

It is **pre-existing**: the identical signature occurs on the committed B2b-i baseline
(`924ccc3`) and on B2b-ii.

## 2. Mechanism, as measured

- DNp01 no-loom rises are exactly quantised at **1.0 per spontaneously firing DNp01
  neuron** (measured rises `[1.0, 1.0, 1.0, 2.0]` after removing decay).
- The trace decays by `exp(-0.02/0.1) = 0.818731` per tick, matching
  `brain.trace_tau_seconds = 0.1`.
- Spike source: `brain.noise_hz = 1.2`, `brain.noise_amp = 0.22`, `brain.tonic = 0.14`.
- Threshold **1.45** lies in the gap between the one-spike level (1.0) and the two-spike
  level (2.0).

A false trigger therefore needs either two DNp01 spikes in one tick, or one spike while
the residual trace is at least 0.45, i.e. within **0.0799 s (4 ticks)** of a previous
spike. Both observed cases match: 1.4616 (1.0 on a 0.4616 residual) and 2.0006 (a
two-spike coincidence).

## 3. Calibration context

The active record measured a no-loom maximum of **1.4493308663** over **2520** ticks and
the rule "smallest sweep-grid value with zero false triggers across all no-loom ticks"
selected **1.45** — a margin of **0.00067** above an observed near-miss of exactly this
class. The threshold is not wrong by construction; the *sample was too short* to see the
tail, and the acceptance criterion was "zero in 2520 ticks" rather than a stated rate.

## 4. Observed rate, with its limitation

Aggregated perched no-loom ticks with a static swatter, ten seeds per stage:

| | B2b-i | B2b-ii |
| --- | --- | --- |
| Perched no-loom ticks | 11,447 (228.9 s) | 5,712 (114.2 s) |
| Threshold crossings / `TAKEOFF_ESCAPE` | 3 / 3 | 1 / 1 |
| Per 10,000 perched ticks | 2.62 | 1.75 |
| Per simulated minute of perched time | 0.79 | 0.53 |
| Exact Poisson 95% CI on the rate (/1000 ticks) | [0.054, 0.766] | [0.004, 0.975] |

**Do not over-read this.** Three and one events respectively. The confidence intervals
overlap almost entirely, so the two stages are statistically indistinguishable and the
point estimates must not be presented as a difference. A purpose-built long no-loom
measurement is required before any rate is quoted as a property of the model.

## 5. Fix options (evaluated, none selected)

### A. Longer, statistically explicit no-loom calibration

- **Changes**: recalibration protocol only — much longer no-loom exposure, and an
  explicit acceptable false-trigger *rate* replacing "zero in 2520 ticks".
- **Scientific interpretation**: honest. Admits the threshold is a statistical decision
  boundary on a noisy trace, which is what it actually is.
- **Neural causal semantics**: unchanged. Retina -> LC4/LPLC2 -> MaleCNS -> DNp01 -> Action
  is untouched.
- **Calibration**: new record and a new transfer chain link; the threshold value would very
  likely rise, since a longer sample sees higher tails.
- **Loom sensitivity**: reduced in proportion to any threshold rise; must be quantified,
  not assumed.
- **M1.8-A re-acceptance**: **likely yes** if the threshold moves, because threat-takeoff
  feel is a human-accepted property.
- **Regression risk**: moderate. Every ROOM trace shifts.
- **Touches frozen systems**: the calibrated threshold is shared with the accepted M1.8-A
  escape path, so yes, indirectly.

### B. Higher DNp01 threshold

- **Changes**: one number. Placing it above 2.0 would reject both the one-spike-on-residual
  and two-spike-coincidence cases.
- **Scientific interpretation**: weak on its own. Without A's measurement it is an
  unjustified constant.
- **Neural causal semantics**: unchanged in structure; the decision boundary moves.
- **Calibration**: invalidates the current record; requires a new measurement to remain
  honest.
- **Loom sensitivity**: directly reduced. The calibration reports loom peaks with
  `min_peak = 2.914`, so a threshold just above 2.0 would still sit below the weakest
  recorded loom peak — but detection *latency* would increase and must be measured.
- **M1.8-A re-acceptance**: **yes**, narrow human re-acceptance of threat-triggered takeoff.
- **Regression risk**: moderate to high.
- **Touches frozen systems**: yes, the accepted threshold.

### C. Temporal decision criterion

- **Changes**: require DNp01 to stay above threshold for more than one tick, or require a
  short integration window, inside `FixedEscapePolicy`.
- **Scientific interpretation**: reasonable. Real escape decisions are not single-sample,
  and the noise events are single-tick spikes on a 0.1 s decay, so a 2-tick persistence
  requirement would reject them while a genuine loom — which drives sustained input — would
  persist.
- **Neural causal semantics**: changes the *decoder*, not the connectome. Still downstream
  of real DNp01. Defensible, but it is a new decoder rule that needs its own classification.
- **Calibration**: the existing threshold might survive, but the criterion itself needs
  measurement against loom peaks.
- **Loom sensitivity**: adds at least one tick (20 ms) of latency. Must be measured against
  the accepted escape latency, which human sessions accepted at roughly 0.17-0.37 s.
- **M1.8-A re-acceptance**: **probably yes**, narrow, because latency changes feel.
- **Regression risk**: moderate; affects every escape.
- **Touches frozen systems**: the policy decoder, which is accepted but not connectome.

### D. Legitimate recent-threat evidence gate

- **Changes**: require some allowed neural or sensory-derived evidence of recent looming
  before an escape is authorised.
- **Scientific interpretation**: risky. It would make escape conditional on a second,
  hand-built detector, partly duplicating what DNp01 is supposed to represent.
- **Neural causal semantics**: weakens the claim that the escape is a pure descending-neuron
  readout.
- **Policy-observation boundary**: **compatible in principle** — retinal `theta_dot` and
  LC4/LPLC2 drive are already legitimate local sensory quantities and no mouse or world
  coordinate is involved — but it adds a non-connectome gate in front of a connectome
  decision.
- **Loom sensitivity**: could wrongly suppress legitimate neural persistence, for example a
  genuine escape decided slightly after the stimulus has passed.
- **M1.8-A re-acceptance**: yes.
- **Regression risk**: high; most conceptually invasive of the plausible options.
- **Touches frozen systems**: yes, the escape authorisation path.

### E. Brain-noise parameter change

- **Changes**: `brain.noise_hz`, `noise_amp` or `tonic`.
- **Scientific interpretation**: these set MaleCNS dynamics **globally**. Lowering noise to
  suppress a decoder artifact would be tuning the model to fix a threshold problem.
- **Neural causal semantics**: changes the network itself, not the readout.
- **Calibration**: fully invalidated.
- **Loom sensitivity**: changes everything, including the loom peaks the threshold is
  calibrated against.
- **M1.8-A re-acceptance**: yes, and arguably broader than narrow.
- **Regression risk**: **highest**. Affects every neural result in the game path.
- **Touches frozen systems**: yes — the brain configuration is shared with the protected
  experiment's parameter lineage. **Treat as high risk.**

### F. Reclassification as spontaneous takeoff

- **Changes**: nothing mechanical; relabels the event.
- **Scientific interpretation**: **not acceptable as stated.** M1.8-A already models
  voluntary takeoff through a separate, documented motivational hazard. Relabelling a
  decoder false positive as "spontaneous" would attach a biological name to a simulator
  artifact, which is exactly what the project's evidence policy forbids. R0 also notes that
  the voluntary initiator circuit remains open, so there is no modelled basis to claim
  DNp01 noise represents spontaneous takeoff.
- **Recommendation**: **reject**, unless someone can supply an explicit modelled biological
  basis for DNp01-noise-initiated departure, which no reviewed source currently provides.

## 6. Not decided

No option is selected. The natural pairing is **A** (measure properly) with either **B** or
**C**, but that is an observation, not a recommendation to act on.

Whatever is chosen must be measured before and after against: loom detection rate, escape
latency, the accepted M1.8-A `perched_threat` scenario, and a long no-loom exposure. A
narrow human re-acceptance of threat-triggered takeoff feel is likely required for any
option that moves the threshold or adds latency; per the accepted B2b-i decision, that does
**not** require reopening the whole M1.8-A lifecycle architecture.

## 7. Interim status

The defect is **documented and accepted as a known limitation**. It does not block
M1.8-B2b-ii, whose EXPLORE sampler does not touch the retina, encoder, brain, threshold or
escape path. It **should** be resolved before any later high-speed kinematic work, because
raising ecological speed increases the time the fly spends airborne near surfaces and
changes how often it perches, which changes exposure to this false trigger.
