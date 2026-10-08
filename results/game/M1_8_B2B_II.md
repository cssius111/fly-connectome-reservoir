# M1.8-B2b-ii validation: EXPLORE speed distribution

Status: **accepted and committed.**

Baseline: B2b-i accepted and frozen at `924ccc3`. This is the **first intentionally
non-bit-identical kinematic milestone**. Scope is EXPLORE only.

Unchanged: `room_kinematic_scale` = 1.0; all three caps = 1000.0 units/s;
`escape_impulse` = 880.0; `fly.max_speed` = 1000.0; the legacy escape clamp; TRANSIT,
ODOR_TRACK, ODOR_SEARCH, RECOVER, ALERT, ESCAPE, LAND_APPROACH and TAKEOFF. No RL.

Because EXPLORE spans 5-8 BL/s and the ecological cap is 41.667 BL/s, this milestone
does **not** activate the escape/cruise conflict: the cap never binds.

## 1. Evidence audit

Sources inspected: `game/M1_8_EVIDENCE.md`, `game/M1_8_B_PLAN.md`, the current
`EcologicalController` EXPLORE logic and its exact RNG semantics.

### 1.1 What the current model actually does

EXPLORE speed today is **not sampled at all**. It is a deterministic shared sinusoid:

```python
lo, hi = c['speed_bl_s'][self.state]              # EXPLORE: [5.0, 8.0]
target = lo + (hi-lo)*(0.5 + 0.5*sin(2*pi*self.time/8 + self.phase))
self.speed += (target-self.speed)*(1-exp(-dt/0.5))
```

The only randomness is `self.phase`, drawn **once at reset** from the ecology stream.
`self.time` is the global ecology clock, so one 8 s sinusoid is shared across every
state. M1.8-R0 lists this "shared 8 s speed sinusoid" first among "the strongest
examples of invented current timing".

Measured time-density of that target over one period: mean **6.500**, median 6.500,
sd **1.061**, support [5, 8] — and the shape is **arcsine (U-shaped)**, with 18.6% of
time in each outermost twelfth of the band and ~5.3% in each central twelfth. The
accepted model therefore spends most of its time near the extremes of the envelope.

A per-episode RNG draw does already exist: `explore_duration_seconds` uniform [3, 7] s
on `_enter('EXPLORE')`, from the ecology stream.

### 1.2 What the literature supports for EXPLORE

| Question | Answer from the accepted R0 lock |
| --- | --- |
| Speed central tendency | **Not usable.** E02 reports 26.7 cm/s (checkerboard) and 38.1 cm/s (horizontal stripes) as Table 1 summaries with **mean/median aggregation not explicitly labeled**; R0 grades this "M for aggregation metadata" and calls it "a conditional comparison, not a default". E03 gives ~0.15-0.20 m/s as a *range of condition means*, "not individual percentiles". |
| Spread | **Not reported** in usable form. No percentiles, no SD for free-flight speed. |
| Support / range | **No measured support.** |
| Distribution shape | **Never measured** in any reviewed source. |
| Persistence / bout duration | **Not measured for speed.** E11 gives intersaccadic intervals of 809/826 ms with aggregation unspecified — that is saccade timing, not speed-bout persistence. |
| Experimental context | 1 m diameter x 0.6 m cylinder (E02) and a 1.5 x 0.3 x 0.3 m tunnel (E03); food-deprived mated **females** aged 2-4 days. ROOM is a ~0.4 m horizontal slice and the neural reference is **male** (MaleCNS). |

R0 also states directly: "No matched evidence fixes the eight current state-speed
envelopes", and classes `ecology.speed_bl_s.EXPLORE [5.0, 8.0]` as **B** — "unfitted
BL/s target envelope; not measured percentiles or guaranteed actual speed".

**Conclusion: the literature constrains neither the magnitude for ROOM nor the
distribution shape.** Nothing here justifies a gamma, lognormal or beta family. Every
aspect of the new distribution is phenomenological, and is labelled as such.

## 2. Chosen distribution

**Symmetric triangular on the accepted support**, `triangular_symmetric(5.0, 6.5, 8.0)`
BL/s, at `kinematics.explore_speed_bl_s`.

Why this and not a "more biological" shape:

- Support is **exactly** the accepted EXPLORE envelope, so magnitude is preserved, as
  section 4 of the brief requires.
- The mode is constrained to the midpoint, so the mean is **6.5 BL/s — identical to the
  accepted sinusoid mean**. The sampler rejects a non-midpoint mode, so this cannot drift.
- Symmetry means **no skew was invented**. A lognormal or gamma would assert a right tail
  that no reviewed source measures.
- It is a genuine change of sampling model: arcsine/U-shaped in time becomes centrally
  peaked per episode.

The one honest consequence: **spread narrows**, sd 1.061 -> 0.612. The accepted sinusoid
concentrates time at the band edges; the triangular concentrates probability at the
centre. Mean and support are preserved; dispersion is not. No evidence favours either
dispersion, so this is a phenomenological change, not a correction.

## 3. Parameter classification

| Parameter | Value | Class | Justification |
| --- | --- | --- | --- |
| `distribution` | `triangular_symmetric` | **C** | No measured shape exists. Chosen to avoid inventing skew; an engineering choice. |
| `min_bl_s` | 5.0 | **B** | Inherited from the accepted class-B EXPLORE envelope. |
| `max_bl_s` | 8.0 | **B** | Inherited from the accepted class-B EXPLORE envelope. |
| `mode_bl_s` | 6.5 | **C** | Constrained to the midpoint so the mean matches the accepted sinusoid; not a measured modal speed. |
| Resample boundary | ecology EXPLORE episode entry | **C** | Reuses the existing accepted state machine; no new parameter. |
| Persistence | existing `explore_duration_seconds` [3, 7] s | **B** (unchanged) | Already class B: "uniform dwell draw, not an observed activity-budget distribution". |

**No parameter is class A.** Nothing here is a biological measurement.

## 4. Sampling boundary and persistence semantics

The brief asked whether the existing ecology state transition already provides an
appropriate resampling boundary. **It does**, and it is used:

```text
ecology enters EXPLORE  ->  one sampled target  ->  persists for the whole episode
                        ->  ecology leaves EXPLORE  ->  next entry resamples once
```

The sampler detects the transition from the `EcologicalCommand.state` it is already
handed; it does **not** read or advance the ecology RNG. Persistence therefore equals the
accepted `explore_duration_seconds` dwell of 3-7 s, so **no new persistence parameter was
invented**. There is no per-tick redraw and no high-frequency jitter: a 50-tick EXPLORE
episode receives one draw and 50 identical targets.

Verified: 20 alternating EXPLORE episodes produce exactly 20 draws serving 1000 ticks,
with 20 distinct values.

Note the dynamics consequence: the ecology's own 0.5 s speed lag is bypassed for EXPLORE,
so the target steps at episode onset and the WORLD damping (3.0/s) does the smoothing
instead. Actual speed is therefore still smooth; only the target is piecewise constant.

## 5. RNG behaviour

One stream, the dedicated `KinematicSampler` at offset **+24593** introduced in B2a.
`self.rng.triangular(...)` is the only draw.

Direct isolation proof (now a regression test): 2000 sampler calls across alternating
episodes advance the sampler stream and leave the `ecology`, `flight` and `world`
bit-generator states **byte-identical**.

In the closed-loop traces the comparator reports the `ecology`, `flight` and `world`
stream states as changed. That is **downstream feedback, not stream consumption**: a
different EXPLORE target changes the trajectory, which changes sensory input, which
changes how many draws those controllers make. Two independent arguments confirm it:

1. the isolation test above, where the trajectory cannot feed back; and
2. ordering — `ecology.step()` runs before the sampler is consulted within a tick, so
   tick-0 ecology behaviour is provably unaffected, and the tick-0 divergence appears in
   `applied_target_speed` and position, not in the ecological command.

`kinematics_sampler_untouched` is now `false` for ROOM scenarios, as intended, and
remains `true` for LAB, GAME and `room_no_ecology`.

## 6. Exact first divergence

| Field | Value |
| --- | --- |
| Scenario | `room_quiet` (and every ROOM scenario with ecology) |
| Tick | **0** |
| Column | `x` (first differing recorded field) |
| Cause | first EXPLORE episode sample replaces the legacy sinusoid target |
| Old target | 156.014952 units/s = **6.5006 BL/s** |
| New sampled target | 179.608908 units/s = **7.4837 BL/s** |
| Sampler draw index | **1** (the first draw of the run) |
| Context | `ecology_explore`, `threat_priority` false, lifecycle airborne |
| Position at tick 0 | 1086.945329191 -> 1086.948613804 |
| RNG evidence | `kinematics` stream advanced; `kinematics_sampler_drew` finding raised |

Ecology starts in EXPLORE at reset, so the first legitimate sample occurs on the very
first tick. **No subsystem diverges before that point**, and nothing diverges at all in
scenarios without ecology.

| Scenario | Ticks | Identical |
| --- | --- | --- |
| `room_quiet` | 1200 | no — diverges at tick 0 as intended |
| `room_perched_threat` | 340 | no — tick 0 |
| `room_approach_threat` | 120 | no — tick 0 |
| `room_airborne_seed101` | 900 | no — tick 0 |
| `room_no_ecology` | 600 | **yes** |
| `game_preset` | 500 | **yes** |
| `lab_preset` | 400 | **yes** |

Combined SHA256: `aee61cff38dc12f1...` -> `ea0d9747d387988a...`.

## 7. Offline distribution diagnostics

200,000 seeded draws (`tools/explore_speed_diagnostics.py`), seed reproducibility
confirmed.

| Statistic | Sampled (triangular) | Accepted legacy sinusoid |
| --- | --- | --- |
| n | 200000 | analytic over one period |
| min / max | 5.003 / 7.997 | 5.000 / 8.000 |
| mean | **6.498** | **6.500** |
| median | 6.500 | 6.500 |
| sd | **0.612** | **1.061** |
| p05 / p95 | 5.476 / 7.524 | 5.018 / 7.982 |
| IQR | 0.880 | ~2.12 |

Histogram, 12 equal bins over 5-8 BL/s:

```text
sampled : 0.014 0.041 0.071 0.098 0.124 0.152 0.154 0.125 0.097 0.069 0.042 0.014
legacy  : 0.186 0.081 0.066 0.058 0.055 0.053 0.053 0.055 0.058 0.066 0.081 0.186
```

Comparison against evidence: **none is possible.** No reviewed source supplies a
free-flight speed distribution to compare against, and E02/E03 magnitudes in BL/s
(60-150+) are an order of magnitude above ROOM at scale 1.0 — the gap documented in
`M1_8_B_PLAN.md` section 2 and deliberately untouched here. Simulator values and
biological measurements are kept separate throughout.

## 8. Closed-loop diagnostics

Three 9000-tick (180 simulated second) ROOM runs, **no player**, pointer parked far away.

| Seed | Draws | EXPLORE actual speed mean / sd | EXPLORE requested mean / sd | Wall fraction | Saccade interval median | Lifecycle events |
| --- | --- | --- | --- | --- | --- | --- |
| 101 | 93 | 6.690 / 0.577 | 6.589 / 0.613 | 0.197 | 1.35 s | touchdown 1, escape_takeoff 1, feed 1 |
| 255 | 80 | 6.484 / 0.970 | 6.421 / 0.955 | 0.122 | 1.33 s | touchdown 2, voluntary_takeoff 2, feed 2 |
| 4242 | 68 | 6.440 / 0.619 | 6.372 / 0.561 | 0.112 | 1.56 s | touchdown 1, voluntary_takeoff 1, feed 1 |

Acceleration while alive: mean ~0.0 BL/s^2 with p05/p95 near -5 to +5 BL/s^2 (the large sd
is dominated by saccade and contact transients, not by EXPLORE sampling).

Ecology-state occupancy, seed 255: EXPLORE 0.534, ODOR_TRACK 0.173, RECOVER 0.174,
ALERT 0.087, ODOR_SEARCH 0.018, TRANSIT 0.007, ESCAPE 0.007.

The realized EXPLORE mean (6.44-6.69) sits close to the 6.5 target mean; the residual
spread differs from the offline draw distribution because episodes are finite, the world
damping lags the target, and threat interruptions truncate episodes.

**Landing, feeding, perching and both takeoff causes all still occur** across all three
seeds. No metric in this section was used to tune anything, and no hit rate, survival,
escape rate or difficulty measure was computed.

## 9. Frozen-system verification

| Check | Result |
| --- | --- |
| Full unit suite | **330 tests, OK** (319 after B2b-i, +11) |
| `git diff --check` | clean |
| 20 protected original files | SHA256 unchanged |
| 58-file frozen baseline | SHA256 unchanged |
| `verify_results.py` | 36 predictions, hashes match, 2/2 exact neuronal replays, frozen weights |
| M1.7.1 swatter fixtures | **byte-identical** to `approach_m1_7_1.json` |
| Neural escape mechanics | escape study reproduces all 54 cases, 18 bouts and constants **identically** |
| M1.8-A lifecycle scenarios | identical event counts; exact replay 1200 / 340 / 120 |
| Recorder exact replay | `exact: true`, 1200 ticks, schema 4 |
| Policy-observation isolation | `{neural, motion, behavior_state, history}` only, no leaks |
| Calibration provenance | LAB 1.45, GAME 1.35, ROOM 1.45 via the new B2b-ii record |
| LAB / GAME traces | **bit-identical** |
| B2b-i separated caps | untouched; all three still 1000.0 |

The M1.8-A lifecycle scenarios are worth noting: although the pre-landing trajectory
changed, all three still produce the **same event counts** and still replay exactly. The
mean-preserving distribution choice is the likely reason, but that outcome was observed,
not engineered.

No recorder schema bump was required, and no recorder diagnostic was extended: the
ecological profile cap never binds at these speeds, so there is nothing new to
distinguish. The three legacy aliases noted in the B2b-i report were left alone, including
the frozen lifecycle voluntary-launch consumer.

## 10. Calibration

`results/game/calibration_room_m1_8_b2b_ii.json` resolves to **1.45**, extending the chain
to four transfers: B2b-ii -> B2b-i -> B2a -> M1.8-A, with `original_measurement` still
naming `calibration_room_m1_7_1.json` and its SHA256. `changed_config_paths` is exactly
`kinematics.explore_speed_bl_s`, `config_version`, `policy.calibration_paths`.

No recalibration was justified: fixed-fly-v2 disables ecology, lifecycle, fly motion and
collisions, so EXPLORE sampling cannot reach the retinal or neural input distribution.
`config_version` 12 -> 13.

## 11. Known limitations

1. **Nothing about the distribution is evidence-based.** Shape, mode and the decision to
   sample per episode are phenomenological. Only the support is inherited, and it is
   itself class B.
2. **Dispersion changed without justification either way.** sd drops 1.061 -> 0.612. No
   evidence prefers either value.
3. **The 8 s sinusoid is only removed for EXPLORE.** Every other ecological state still
   rides the same shared global sinusoid, so the model is now internally inconsistent
   until TRANSIT and the odor states are converted.
4. **Ecology's 0.5 s speed lag is bypassed for EXPLORE**, so the requested target is now
   piecewise constant rather than continuously swept. Smoothing comes from WORLD damping.
5. **No comparison to biology is possible** at scale 1.0; ROOM remains 5-15x slower than
   the reviewed measurements in body-normalized terms.
6. Closed-loop statistics come from three seeds over 180 s each. That is a diagnostic
   sample, not a characterisation of the behavioral model.
7. Episode-scoped sampling means a long EXPLORE episode holds one speed for up to 7 s;
   within-episode speed variation now comes only from damping and saccade transients.
8. A **pre-existing** no-loom neural false trigger can launch a perched fly without any
   visual threat (section 11a). It is not caused by B2b-ii and is not fixed here.

## 11a. No-player escape-takeoff provenance

The closed-loop diagnostics in section 8 contain `escape_takeoff` events in runs with no
player. This section establishes their cause from recorded data. **It is a diagnosis: no
runtime code, configuration, parameter, threshold or recorder schema was changed.**

### Classification: pre-existing no-loom neural false trigger

This is **not** a legitimate threat response. It is a spontaneous DNp01 threshold crossing
with zero visual input, and the identical mechanism exists on the committed B2b-i baseline.

### Recorded evidence at the event

Window of 50 ticks before to 25 ticks after each event (`tools/escape_provenance.py`,
`artifacts/m1_8_b2b_ii/escape-provenance.json`). Seed 101, B2b-ii, t = 6.88 s:

| Quantity | Value throughout the window |
| --- | --- |
| Lifecycle state before launch | `PERCHED / CONTACT`, feeding, `contact_surface_id` set |
| Fly speed | 0.00 BL/s |
| Swatter phase | `approach` (never commanded to move) |
| Swatter velocity | **0.0**, max speed in window **0.0** |
| `strike_id` / strikes | **0** |
| Fly-to-swatter distance | constant 1158 units |
| Retinal `theta` | constant 0.1287 rad |
| Retinal `theta_dot` | **exactly 0.00000** |
| Retinal azimuth | constant |
| **LC4 / LPLC2 drive** | **exactly 0.0000 on all four channels** |
| Threshold | 1.45 |
| DNp01 at launch | **1.4616** -> `action.escape = True` -> `TAKEOFF_ESCAPE` |

The pointer is parked at (1920, 388.8), which is exactly the swatter's own spawn position,
so the paddle never receives a movement command. Cause C (scripted or moving swatter
input) is therefore excluded by the recorded swatter velocity and by `strikes = 0`.
Causes A and B (relative looming, or residual dynamics from a real looming event) are
excluded by `theta_dot` being exactly zero and the LC4/LPLC2 drive being exactly zero for
the entire window. The classification is **D: spontaneous threshold crossing without a
relevant visual threat**.

### Mechanism, measured

No-loom DNp01 rises are exactly quantised. Measured rises in the recorded windows, after
removing the known decay, were `[1.0, 1.0, 1.0, 2.0]` — **1.0 per spontaneously firing
DNp01 neuron**. The inter-spike decay is `exp(-dt/0.1) = 0.818731` per tick, matching
`brain.trace_tau_seconds = 0.1`. The source of the spikes is the background network
activity configured by `brain.noise_hz = 1.2`, `noise_amp = 0.22`, `tonic = 0.14`.

The threshold 1.45 sits in the gap between the one-spike level (1.0) and the two-spike
level (2.0). A false trigger therefore requires either two DNp01 spikes in the same tick,
or one spike arriving while the residual trace is at least 0.45 — that is, within
0.0799 s (4.0 ticks) of a previous spike. The two observed events are exactly these two
cases: seed 101 crossed at 1.4616 (a 1.0 rise on a 0.4616 residual) and seed 4242 crossed
at 2.0006 (a two-spike coincidence on a near-zero residual).

### Calibration margin

The active calibration record measured, over 2520 no-loom ticks, a maximum of
**1.4493308663** against the chosen threshold of **1.45** — a margin of **0.00067**. The
calibration rule is "smallest sweep-grid value with zero false triggers across all no-loom
ticks", so the threshold was placed immediately above an observed near-miss **of exactly
this class**. Longer exposure crosses it. This is a property of the calibration procedure
and sample length, not of anything introduced by B2b-ii.

### The same mechanism exists in B2b-i

Seed 4242, **B2b-i**, t = 98.96 s: perched, `theta_dot` exactly 0.00000, swatter
stationary, strikes 0, DNp01 rising 0.0007 -> **2.0006** in a single tick, then
`TAKEOFF_ESCAPE`. The signature is identical.

### Rate study

`tools/perched_noise_study.py` aggregates perched ticks with a static swatter across ten
seeds and both stages (6000 ticks per run). Voluntary takeoff ends every perch, so a
single long hold is impossible without modifying runtime; aggregating many perches samples
the same stationary no-loom condition instead. A tick is attributed to the state the fly
was in when the tick **began**, so the launch tick itself is counted — an earlier version
of this diagnostic silently reported zero because the lifecycle has already left the
stationary state by the time the tick ends.

| | B2b-i | B2b-ii |
| --- | --- | --- |
| Perched no-loom ticks | 11,447 (228.9 s) | 5,712 (114.2 s) |
| DNp01 threshold crossings | **3** | **1** |
| `TAKEOFF_ESCAPE` events | **3** | **1** |
| Crossings per 10,000 perched ticks | 2.62 | 1.75 |
| Events per simulated minute of perched time | 0.79 | 0.53 |
| Seeds with events | 4242, 7, 33 | 101 |
| Maximum no-loom DNp01 while perched | 2.0006 | 1.4616 |
| Maximum abs(`theta_dot`) while perched | 0.0045 | 0.0023 |

Every crossing produced a takeoff, which is consistent with the lifecycle semantics: a
perched fly launches on any authorised escape action.

**Statistical limitation, stated explicitly.** These are rare-event estimates from **3 and
1 events respectively**. Exact Poisson 95% confidence intervals on the counts are
[0.62, 8.77] for B2b-i and [0.03, 5.57] for B2b-ii, giving rate intervals of
[0.054, 0.766] and [0.004, 0.975] per 1000 perched ticks. **These intervals overlap almost
entirely.** The point estimates must not be read as showing that B2b-ii reduces the rate,
nor that the two differ at all. The sample is far too small to separate them, and the
perched-tick totals themselves differ (11,447 vs 5,712) only because the trajectories
differ. Any future claim about this rate needs a purpose-built long no-loom measurement,
not these diagnostics.

### Conclusion for B2b-ii acceptance

The mechanism is intrinsic to the frozen neural configuration and the calibrated
threshold. It is present on the committed B2b-i baseline, it is driven by spontaneous
MaleCNS activity with **zero** visual drive, and nothing in the EXPLORE sampler touches
the retina, the encoder, the brain, the threshold or the escape path. EXPLORE sampling
changes which trajectory the fly follows, and therefore which seeds and times show an
event, but there is no evidence that it changes the underlying false-trigger probability.

This is tracked separately as a genuine semantic defect in
[game/M1_8_NO_LOOM_FALSE_ESCAPE.md](../../game/M1_8_NO_LOOM_FALSE_ESCAPE.md). It is **not**
fixed here, and no fix was selected.

## 12. Status

B2b-ii is accepted and committed. The no-player escape takeoffs investigated in
section 11a are a pre-existing no-loom neural false trigger, tracked separately in
[game/M1_8_NO_LOOM_FALSE_ESCAPE.md](../../game/M1_8_NO_LOOM_FALSE_ESCAPE.md) and not
introduced by this milestone.

Not done, deliberately: no TRANSIT sampling, no odor speed distributions, no
`room_kinematic_scale` change, no cap value change, no escape clamp change, no
acceleration or deceleration model, and no RL, reward function, personalized learning or
adaptive opponent policy anywhere in the codebase.
