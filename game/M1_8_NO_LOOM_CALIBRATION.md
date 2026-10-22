# M1.8-N0: extended no-loom false-escape calibration study

Status: **research only. Nothing implemented, nothing selected, nothing committed.** No
threshold, brain parameter, gate, calibration record, runtime code, recorder, lifecycle or
kinematic behaviour was changed. B2b-ii remains frozen at `0d8c254`.

Artifacts: `artifacts/m1_8_no_loom_calibration/` (`study.json`, `criteria.json`,
`model.json`, `robustness.json`, `statistics.json`, `continuous.json`, `raw.npz`,
`continuous.npz`). Reproduced by `tools/no_loom_calibration_study.py`,
`tools/no_loom_criterion_analysis.py`, `tools/no_loom_tail_model.py`,
`tools/no_loom_statistics.py` and `tools/no_loom_continuous_arm.py`.

## 1. Headline

The active threshold of **1.45 produces 1.30 false escapes per simulated minute** of
no-loom exposure. The legacy record's "zero false triggers" was a short-sample artifact:
2,520 ticks is 42 seconds, and the expected count at that exposure is under one.

The dominant failure mode is a **two-spike coincidence at level 2.000**, and the extended
exposure shows the no-loom distribution is **bounded at 2.0045** — below the weakest
genuine loom peak of **2.899**. Separation therefore exists, but "zero observed" at a
candidate threshold is not the same as "safe", and this study quantifies the difference.

**Two limits on what this run can conclude.** 70 minutes of zero-event exposure bounds a
rate at roughly **0.043 per minute**, so the **<0.01/min engineering target is not
demonstrated by this run** and appears below as a model estimate only. And 150/150 loom
detections is a point estimate: the exact binomial lower bound is **0.9757**, not 1.

## 2. Protocol and provenance

Accepted **fixed-fly-v2**, reused unmodified from `tools/calibrate_escape.py`: escape
disabled (`RecordingPolicy`), `fly_motion_enabled = False`, `collisions_enabled = False`,
and the paddle settled for the configured 6.0 s with the existing velocity assertion.
Config `game_room_config.json`, provenance recorded in `study.json`.

**Condition validity was verified, not assumed.** With the paddle properly settled,
`theta_dot` is exactly 0 and **all four LC4/LPLC2 channels are exactly 0.0000**, at both
53-146 units and 973-1316 units paddle distance, with static `theta` up to 0.4995 rad.
Both encoder channels are purely expansion-driven in this configuration, so a static
paddle at any tested distance produces no sensory drive. This is a genuine zero-stimulation
condition.

## 3. Extended no-loom exposure

| Quantity | Value |
| --- | --- |
| Ticks | **210,000** |
| Simulated time | **70.0 minutes** |
| Exposure vs legacy calibration | **83.3x** (legacy 2,520 ticks = 42 s) |
| Trials / seeds | 150 geometries, seeds 4000-4149 |
| Mean | 0.0841 |
| SD | 0.2073 |
| Median (p50) | 0.0003 |
| p95 | 0.5555 |
| p99 | 1.0000 |
| p99.9 | 1.3012 |
| p99.99 | 1.8201 |
| **Maximum** | **2.0045** |

p99.9 and p99.99 are both supported at this sample size (210,000 ticks).

## 3a. Reset and continuity limitation, with a continuous control arm

The accepted fixed-fly-v2 arm divides its 70 minutes across **150 reset trials**, not one
continuous brain trajectory. This matters because `Session.reset` calls
`fly_loop.reset`, which calls **`brain.reset(seed)`** and resets the DNp01 trace: each
trial is an independent MaleCNS initialisation, followed by a 300-tick (6.0 s) settle
before recording begins.

Two mechanisms could in principle distort the rare tail:

- **Trace carryover.** `trace_tau_seconds = 0.1` is 5 ticks, and the burn-in is 300 ticks,
  60x that. Trace-level memory is fully washed out. The only visible consequence is one
  reconstruction artifact per trial at the first recorded tick, noted in section 4.
- **Recurrent network equilibration.** If spontaneous firing had not reached steady state
  within the 300-tick burn-in, the measured rate would be biased.

A **secondary continuous arm** was recorded to test this: one uninterrupted 30,000-tick
(10 minute) trajectory with no reset, same geometry family, same settle. It does not
replace the accepted protocol.

| | Reset-divided (70 min, 150 trials) | Continuous (10 min, 0 resets) |
| --- | --- | --- |
| Mean | 0.0841 | 0.0829 |
| SD | 0.2073 | 0.2064 |
| p95 | 0.5555 | 0.5513 |
| p99 | 1.0000 | 1.0000 |
| p99.9 | 1.3012 | 1.3675 |
| Maximum | 2.0045 | 2.0000 |
| Spike rate | 0.7643 Hz | 0.7517 Hz (**1.7% difference**) |
| Two-spike ticks | 17 / 210,000 = 8.10e-5 | 1 / 30,000 = 3.33e-5 |

Equilibration was also checked directly, by spike rate against position within a trial:

| Within-trial region | Spikes / ticks | Rate | Exact Poisson 95% CI |
| --- | --- | --- | --- |
| First 350 ticks (burn-in region) | 836 / 52,350 | 0.7985 Hz | [0.7453, 0.8545] |
| Remaining 1,050 ticks | 2,366 / 157,500 | 0.7511 Hz | [0.7211, 0.7820] |
| Continuous arm | 451 / 30,000 | 0.7517 Hz | — |

The two reset-arm regions overlap each other and the continuous arm, and there is no
monotonic equilibration trend across finer segments. **Assessment: reset boundaries do not
materially change the estimated rare tail at this exposure.** No correction is invented or
applied. The continuous arm also independently reconfirms the zero-stimulation condition:
max abs `theta_dot` 5.6e-12 and max abs encoder drive 2.2e-12, both numerically zero.

One genuine benefit of the reset-divided design is worth recording: 150 independent noise
realisations sample the tail better than a single trajectory of the same length would.

## 4. Noise mechanism, confirmed

| Property | Measured |
| --- | --- |
| Quantisation of trace rises | **exact**, max error 8.3e-8 |
| Decay per tick | 0.818731, matching `trace_tau_seconds = 0.1` |
| Spike ticks: 1 / 2 / 3 spikes | **3,168 / 17 / 0** |
| Total spikes | 3,210 = 0.01529 per tick = **0.764 Hz** |
| Inter-spike interval | median 46 ticks, p05 7, min 1 |
| P(>=2 spikes within 20 / 100 ms) | 8.10e-5 / 1.40e-3 |
| **P(>=3 spikes within 20-100 ms)** | **0 observed in every window** |

One caveat on the quantisation figure: a naive reconstruction reports a maximum error of
0.451, but that is exactly one artifact per trial — the recorded window begins with
residual trace carried over from the settle period, which has no prior sample. Excluding
those 150 boundary ticks, rises are exactly integral.

**Answer to the question in the brief:** the dominant failure mode is the two-spike
coincidence, and moving the threshold above 2.0 does suppress it. It does **not** move the
failure into an unreachable tail, because a two-spike coincidence landing on residual
trace from a recent prior spike still exceeds any threshold up to 3.0. A bare three-spike
tick has Poisson probability 5.86e-7, about **once per 9.5 hours**, and none occurred in
70 minutes.

## 4a. Event accounting: ticks, clusters and policy firings

Repeated above-threshold ticks from one spike cluster are **not** independent false
escapes. All three counts are reported separately (`statistics.json`).

| Threshold (persistence 1) | Above-threshold ticks | Contiguous clusters | Policy firings | Firings/min |
| --- | --- | --- | --- | --- |
| 1.45 | 125 | 91 | **91** | 1.3000 |
| 1.6 | 70 | 53 | **53** | 0.7571 |
| 1.8 | 34 | 34 | **34** | 0.4857 |
| 2.0 | 17 | 17 | **17** | 0.2429 |
| 2.05 | 0 | 0 | 0 | 0 |
| 2.2 | 0 | 0 | 0 | 0 |
| 2.6 | 0 | 0 | 0 | 0 |

At 1.45 the 125 above-threshold ticks resolve to **91** distinct clusters, because a
two-spike cluster sits above 1.45 for two consecutive ticks. Clusters and policy firings
coincide here because the 20-tick refractory always exceeds a cluster's length, so no
cluster is double-counted. Every rate quoted in this document is a **policy-firing** rate.

## 5. Threshold sweep

150 loom trials, accepted geometry, click at tick 20. Loom peaks: min **2.899**, median
4.194, max 5.476. Latency is measured exactly as the accepted tool measures it: first
crossing during the committed window, minus the click tick.

| Threshold | No-loom exceedance ticks | Trigger events | False/min | Detection | Missed | Median latency | p95 latency |
| --- | --- | --- | --- | --- | --- | --- | --- |
| **1.45 (active)** | 125 | **91** | **1.3000** | 1.000 | 0 | 0.080 s | 0.080 s |
| 1.6 | 70 | 53 | 0.7571 | 1.000 | 0 | 0.080 s | 0.080 s |
| 1.8 | 34 | 34 | 0.4857 | 1.000 | 0 | 0.100 s | 0.120 s |
| 2.0 | 17 | 17 | 0.2429 | 1.000 | 0 | 0.100 s | 0.151 s |
| 2.05 | **0** | **0** | 0.0000 | 1.000 | 0 | 0.100 s | 0.151 s |
| 2.1 | 0 | 0 | 0.0000 | 1.000 | 0 | 0.100 s | 0.151 s |
| 2.2 | 0 | 0 | 0.0000 | 1.000 | 0 | 0.100 s | 0.160 s |
| 2.4 | 0 | 0 | 0.0000 | 1.000 | 0 | 0.140 s | 0.160 s |
| 2.6 | 0 | 0 | 0.0000 | 1.000 | 0 | 0.160 s | 0.200 s |
| 2.8 | 0 | 0 | 0.0000 | 1.000 | 0 | 0.180 s | 0.220 s |
| 2.9 | 0 | 0 | 0.0000 | **0.993** | **1** | 0.180 s | 0.220 s |

Zero observed is *not* zero rate. For the zero-count cells at 70 minutes of exposure:

| Bound | Value |
| --- | --- |
| Rule of three, one-sided 95% (3 / minutes) | **0.0429 /min** |
| Exact Poisson, one-sided 95% | 0.0428 /min |
| Exact Poisson, two-sided 95% | 0.0527 /min |

Detection is discussed from trial-level data in section 5a, not inferred from peak
ordering.

## 5a. Loom detection from trial-level data

Detection is measured per trial from the recorded traces: a trial counts as detected only
if the criterion fires **inside the committed response window**, which is the same window
the accepted calibration uses. Peak ordering is never used to infer detection.

| Persistence | Threshold | Detected | Exact binomial 95% CI | Missed | Missed but crossed after the window closed |
| --- | --- | --- | --- | --- | --- |
| 1 | 1.45 | 150/150 | [0.9757, 1.0000] | 0 | 0 |
| 1 | 2.05 | 150/150 | [0.9757, 1.0000] | 0 | 0 |
| 1 | 2.6 | 150/150 | [0.9757, 1.0000] | 0 | 0 |
| 2 | 1.8 | 150/150 | [0.9757, 1.0000] | 0 | 0 |
| 3 | 1.45 | 150/150 | [0.9757, 1.0000] | 0 | 0 |
| 3 | 1.8 | 150/150 | [0.9757, 1.0000] | 0 | 0 |
| 3 | 2.0 | 150/150 | [0.9757, 1.0000] | 0 | 0 |
| 4 | 1.8 | 150/150 | [0.9757, 1.0000] | 0 | 0 |

**150/150 does not mean the detection probability is 1.** The Clopper-Pearson lower bound
is **0.9757**, so a true miss rate of up to about 2.4% is compatible with these data. Any
statement of "full detection" in this document means "no miss observed in 150 trials, with
that interval", not a proven certainty.

In no configuration did a trial cross only *after* the response window closed, so the
misses that do appear at high thresholds (2.9 at persistence 1; 2.4 and above at
persistence 3-4) are genuine non-detections rather than late detections.

## 6. Why "zero observed" is not "safe"

A criterion fires when the trace reaches an effective level `L = threshold / decay^(N-1)`
for persistence `N`. A tick carrying `k` spontaneous spikes reaches `L` if residual trace
from a recent prior spike supplies the remaining `L - k`.

All 17 observed two-spike ticks happened to land on near-zero residual (largest 0.0045,
giving the 2.0045 maximum). That is luck, not structure: **12.95%** of inter-spike
intervals are within the 15 ticks needed to supply the 0.05 residual that would defeat a
2.05 threshold, so roughly **2.2 defeating events were expected** in this sample and zero
occurred.

A mechanistic model built from the measured spike counts and ISI distribution reproduces
the observed rates closely, which is what licenses using it where the count is zero:

| Threshold (persistence 1) | Observed /min | Model /min | Ratio |
| --- | --- | --- | --- |
| 1.45 | 1.3000 | 1.2288 | 0.95 |
| 1.6 | 0.7571 | 0.7814 | 1.03 |
| 1.8 | 0.4857 | 0.4981 | 1.03 |
| 2.0 | 0.2429 | 0.2446 | 1.01 |

## 7. Fix-family comparison

Persistence `N` means DNp01 must remain at or above threshold for `N` consecutive ticks.
It uses only the DNp01 trace the policy already receives: no raw mouse or world data, and
no LC4/LPLC2 gate, as the brief requires. `N = 1` is the current rule exactly.

All cells below hold **detection = 1.000** unless noted.

| Family | Config | Observed /min | Model /min | Median latency | vs current | Defeated by |
| --- | --- | --- | --- | --- | --- | --- |
| current | 1.45, N=1 | 1.3000 | 1.2288 | 0.080 s | — | one spike on residual |
| **A** threshold only | 2.05, N=1 | 0 | 0.0332 | 0.100 s | +20 ms | 2 spikes within 15 ticks of a prior spike |
| **A** | 2.4, N=1 | 0 | 0.0090 | 0.140 s | +60 ms | 2 spikes within 4.6 ticks |
| **A** | 2.6, N=1 | 0 | 0.0046 | 0.160 s | +80 ms | 2 spikes within 2.6 ticks |
| **B** temporal only | 1.45, N=3 | 0 | 0.0184 | 0.120 s | +40 ms | 2 spikes within 9.1 ticks |
| **B** | 1.45, N=4 | 0 | 0.0046 | 0.140 s | +60 ms | 2 spikes within 2.2 ticks |
| **C** both | 1.6, N=3 | 0 | 0.0090 | 0.120 s | +40 ms | 2 spikes within 4.7 ticks |
| **C** | 2.05, N=2 | 0 | 0.0070 | 0.160 s | +80 ms | 2 spikes within 3.4 ticks |
| **C** | 1.8, N=3 | 0 | 0.0031 | 0.140 s | +60 ms | 2 spikes within 1.9 ticks |
| **C** | 2.0, N=3 | 0 | 0.0018 | 0.180 s | +100 ms | needs >=3 spikes |
| **C** | 1.8, N=4 | 0 | **0.0000** | 0.160 s | +80 ms | needs >=4 spikes (level 3.28 > 3.0) |
| **C** | 2.05, N=3 | 0 | **0.0000** | 0.180 s | +100 ms | needs >=4 spikes (level 3.06 > 3.0) |

Per-family assessment:

- **A, threshold-only.** Simplest; one number; no decoder structure changes; keeps the
  instantaneous decision semantics intact. Cheapest useful point (2.05) buys a **37x**
  reduction for **+20 ms**. Weakness: it is a thin numeric margin — 2.05 sits 0.045 above
  the observed maximum — and pushing the model below 0.01/min costs +60 to +80 ms, at
  which point the margin to the weakest loom peak (2.899) starts to matter.
- **B, temporal-only.** Rejects the dominant mode *structurally* rather than numerically:
  a two-spike cluster is only above 1.45 for two ticks regardless of level, so `N=3`
  removes it whatever the residual. Keeps the accepted threshold, so the existing
  calibration value survives. Weakness: every escape pays the full persistence latency, and
  it does nothing about a hypothetical three-spike cluster.
- **C, both.** Dominates on the rate/latency frontier. `1.8, N=4` and `2.05, N=3` are the
  only configurations the model puts at zero, because their effective level exceeds 3.0 and
  so cannot be reached by any three-spike event. Weakness: two parameters to justify, and
  the largest latency cost.

## 8. Engineering acceptance targets (Class C)

These are **engineering comparison targets, not biological requirements**. No biological
false-trigger rate is claimed or invented.

### 8.1 What this run can and cannot resolve

With zero observed events, an exposure of `T` minutes supports a 95% upper bound of about
`3/T` per minute. Turning that around gives the exposure each target needs:

| Target | Resolvable at 70 min? | Zero-event exposure needed for 95% confidence | Ticks at 20 ms |
| --- | --- | --- | --- |
| < 1 per minute | **yes** | 3 min | 9,000 |
| < 0.1 per minute | **yes** | 30 min | 90,000 |
| < 0.01 per minute | **no** | **300 min** | **900,000** |

**The <0.01/min target is not demonstrated by this run and is not claimed to be.** At 70
minutes the tightest statement any zero-count cell supports is <= 0.043/min. Reaching
<0.01/min with observational confidence needs roughly 300 simulated minutes of zero-event
exposure, about 900,000 ticks, which is more than four times the exposure collected here.

### 8.2 Cost of each target

Cheapest configuration reaching each target, with the basis stated:

| Target | Configuration | Basis | Rate | Detection | Median latency | Cost vs current |
| --- | --- | --- | --- | --- | --- | --- |
| < 1 per minute | 1.6, N=1 | **observed** (53 events / 70 min) | 0.757 /min | 150/150 | 0.080 s | **+0 ms** |
| < 0.1 per minute | 2.05, N=1 | **observed zero**, bound <= 0.043 /min | 0 observed | 150/150 | 0.100 s | **+20 ms** |
| < 0.01 per minute | 1.6, N=3 | **model only** (0.0090 /min); not demonstrated | 0 observed | 150/150 | 0.120 s | +40 ms |
| effectively zero | 1.8, N=4 | **model only** (0.0000 /min); not demonstrated | 0 observed | 150/150 | 0.160 s | +80 ms |

The current configuration (1.45, N=1) meets none of these targets: its rate is measured,
not bounded, at 1.30/min.

## 9. Recommendation, with reasoning and uncertainty

**Recommended family: C, threshold recalibration plus a minimal temporal criterion.**
Preferred operating point: **threshold 1.8 with persistence 3** — zero false triggers
observed in 70 minutes (bound <= 0.043/min), model estimate 0.0031/min, detection 150/150
with binomial CI [0.9757, 1.0], median latency 0.140 s, +60 ms versus current.

Note the basis carefully: the *observed* claim is "zero in 70 minutes, so at most about
0.043/min". The 0.0031/min figure is the validated model's extrapolation and is **not**
demonstrated at this exposure.

Reasoning:

1. Neither mechanism alone carries the whole burden. The threshold rise removes the bare
   two-spike coincidence; the persistence requirement removes the residual-assisted
   variants that defeat a threshold-only fix.
2. It keeps a large margin to the weakest loom peak (1.8 versus 2.899), so loom detection
   is not traded away, unlike threshold-only points near 2.6-2.9.
3. +60 ms is a modest latency cost, and the persistence requirement is a decoder rule
   operating purely on DNp01 — it does not touch the connectome, the encoder, the retina
   or the escape impulse.
4. `1.8, N=4` or `2.05, N=3` are available if a model rate of exactly zero is wanted, at
   +80 to +100 ms.

**Uncertainty, stated plainly:**

- Every zero in this study is a zero *count*, not a zero rate. At 70 minutes the bound is
  about **0.043/min** one-sided (0.053 two-sided), so **no configuration here is shown to
  meet <0.01/min**. Those figures come from the mechanistic model, validated to within 5%
  on the four cells where events were observed — good evidence, not proof in the tail.
  Demonstrating <0.01/min observationally needs about 300 minutes (900,000 ticks) of
  zero-event exposure, more than four times what was collected.
- Detection is **150/150, binomial CI [0.9757, 1.0]**. A true miss rate up to about 2.4%
  is compatible with these data, so "full detection" is never a proven certainty here.
- The loom protocol tests only **committed strikes**. A brief or glancing loom might be
  rejected by a persistence criterion in a way these 150 trials cannot reveal. This is the
  main risk of families B and C and it is not measured here.
- Latency here is click-to-crossing under fixed-fly conditions. It is **not** the same
  quantity as the 0.169-0.369 s escape latencies recorded in accepted human sessions, and
  the two should not be compared directly.
- The three-spike rate is a Poisson extrapolation from the measured single-spike rate, not
  an observation. Spike times may not be independent.
- The measurement is ROOM config, one machine, `NUMBA_NUM_THREADS=4`.

## 10. Consistency with the earlier ROOM measurement

The B2b-ii diagnosis measured the same phenomenon in closed-loop ROOM with a perched fly:
3 events in 11,447 perched ticks (B2b-i) and 1 in 5,712 (B2b-ii), i.e. 0.53-0.79 per
minute with wide intervals. This study's fixed-fly figure of 1.30/min lies inside the
B2b-i interval, so the two measurements are consistent, and the fixed-fly number is the
better estimate by two orders of magnitude more exposure.

## 11. Human approval decisions still required

1. **Adopt an explicit Class-C false-trigger target?** The study offers <1, <0.1 and <0.01
   per minute with measured costs; none is adopted here. Note that only <1 and <0.1 are
   resolvable at the exposure collected.
2. **Extend the measurement to about 900,000 zero-event ticks** so a <0.01/min target could
   be demonstrated rather than modelled? Not started; the brief directs not to extend the
   run automatically.
3. **Which family — A, B or C?** Recommendation is C; not selected.
4. **Which operating point?** Recommendation is 1.8 with persistence 3; not selected.
5. **Is a persistence criterion acceptable as a decoder rule**, given it adds a
   non-connectome temporal gate on DNp01, or must the fix stay threshold-only to preserve
   the "pure descending-neuron readout" claim?
6. **Should the brief-loom case be measured first?** Families B and C carry an unmeasured
   risk of rejecting short genuine looms.
7. **Recalibration scope.** Any change requires a new calibration record and a new transfer
   chain link, and the threshold is shared with the accepted M1.8-A escape path.
8. **Narrow human re-acceptance of threat-triggered takeoff feel** is expected for any
   option that moves the threshold or adds latency; per the accepted B2b-i decision this
   does not require reopening the M1.8-A lifecycle architecture.

Nothing in this document is implemented.
