# M1.8-N4B7: long-timescale DNp01 slow-approach readout

Status: **research only; complete. The primary candidate L1 is NOT recommended as a runtime
candidate.**

- No runtime code, configuration, decoder, whitelist, Retina / encoder equation, MaleCNS
  parameter, brain noise, controller, geometry, physics or lifecycle was changed.
- The accepted runtime (M1.8-N4B5R, `feature/m1-8-n4b5r-geometry` @ `363a1a9`) was used
  read-only and stayed clean.

## Short answer

**A same-side 1 s DNp01 spike count recovers the 130 units/s controlled slow approach
completely.** It stays silent on the fixed fly and keeps direct strikes intact. **But in
free flight it fires on the fly's own flight toward the parked paddle, so it fails the
preregistered inappropriate-escape target.** Per the preregistered rule, L1 is not
recommended and nothing was tuned against the holdout.

Fresh holdout results for the primary candidate, N4B1C OR L1 (L1 = same-side >= 4 inferred
DNp01 spikes within 1.0 s):

| Check (fresh holdout) | N4B1C alone | N4B1C OR L1 | Criterion | Result |
|---|---|---|---|---|
| 130 units/s controlled approaches (A2, C2, C3; 96 new seeds each): timely detection | 6.9 % | **100 %** (median lead 1.42 s) | >= 70 % and +40 points; each >= 50 %; lead >= 0.25 s | **pass** |
| Fixed-fly N0, 336 min | 2 events | 3 events (0.009/min, upper 0.023) | upper < 0.1/min | **pass** |
| Stationary / receding controls + pre-holds, 77 min | 0 | 0 (upper 0.039) | upper < 0.1/min | **pass** |
| Free flight, 240 min, closed loop: **category B** | 2 (upper 0.026) | **44 (0.18/min, upper 0.24)** | upper < 0.1/min | **FAIL** |
| Free flight: category A | 1 | 4 (upper 0.038) | upper < 0.1/min | pass |
| Fresh committed strikes (N1 strong / medium, 60 each) | 60 / 60, 0.08 s; 60 / 60, 0.08 s | identical | coverage not lower, latency not > +0.02 s | **pass** |
| Repetition: >= 3 LONG escapes within 5 s in a run | - | 2 runs | none | **FAIL** |

- **Total free-flight escapes: 9 -> 167 in 240 min** (0.037 -> 0.70/min).
  - 162 of the 167 are LONG-only firings: B 42, D 102, mixed 15, A 3.
  - All happened while the fly was airborne.
- **What the B events look like:**
  - the fly flies toward the parked paddle: median closing speed 129 units/s at a median
    507 units horizontal distance;
  - it then passes it without coming within 310 units.
- That is the same Retina stimulus as the 130 units/s slow approach, produced by
  self-motion.
- The long-window readout cannot tell them apart. This is the same information limit that
  N4B3 found for DNp04: policy-observable neural signals do not separate self-generated
  from external looming in flight.

The controls are in section 5.3: stationary and receding paddles stay silent. The
stop-rotation transient (orbit control) gains 19 LONG responses: 27 -> 46 of 96 trials.

## 1. Goal and scope

N4B6 found that at 130 units/s:

- the sensory stage signals the approach in every seed;
- DNp01 raises its rate about tenfold;
- the N4B1C short-window rules fire in time in only 0-6 %.

N4B7 asks only whether a longer-timescale DNp01 readout, added beside the frozen N4B1C
paths, can recover that class safely. The 50 units/s case (a stimulus limit in N4B6) is out
of scope and plays no role in the decision.

## 2. Preregistered candidates

**Freeze record:**

- `tools/n4b7_candidates.py`, sha256
  `6b69a44795a6b09cd5676ccee3ca2d0e9a9a6b76f8166d4bd119c506639e0d4e`;
- committed and pushed as `8fee28a` **after** the development characterisation and
  **before any fresh holdout seed was simulated**;
- `artifacts/m1_8_n4b7/preregistration.json` (sha256 `b25493c2...c529`) also records the
  hashes of all development artifacts. Every holdout mode refuses to run if the module
  changes.

| Rule | Definition | Role |
|---|---|---|
| **L1** | same-side >= 4 inferred DNp01 spikes within the trailing 1.0 s (50 samples) | **primary; the only rule the decision uses** |
| L2 | same-side >= 5 spikes / 1.0 s (the smallest count outside the development N0 per-side 1 s envelope, max 4) | robustness comparison; reported only |
| L3 | same-side >= 4 spikes / 0.8 s (40 samples) | latency comparison; reported only |

Each rule is evaluated three ways: as **N4B1C OR LONG** ("combined"), as LONG alone, and
against N4B1C alone.

### 2.1 Semantics (frozen)

- **Spike inference:** exactly the N4B1C lateral inference, per side from that side's own
  DNp01 trace: `spike_t = trace_t - trace_decay * trace_{t-1} >= 0.5`. No spike is inferred
  on the first sample after reset. No new spike detector was introduced.
- **Sides are independent:** a left spike never counts toward the right window. Verified
  by a unit check: two left plus two right spikes within 1 s do not fire.
- **Trailing window:** the window at sample t holds samples t - W + 1 .. t inclusive,
  exactly W samples. Verified: 4 spikes spanning exactly 50 samples fire; spanning 51
  samples do not.
- **Firing:** the path fires on sample t for a side when that side has a spike ON sample t
  and at least k spikes in its window.
  - The qualifying spike must be current (as for LATERAL), so stale evidence cannot fire
    at refractory expiry.
- **Refractory:** evidence accumulates on every sample, refractory samples included. The
  path cannot fire during the shared 0.4 s refractory.
- **Trigger clearing:** when an escape fires on any path, both sides' long-window memories
  are cleared (as the lateral memory is). Reset clears them too.
- **Unchanged N4B1C:**
  - LATERAL, FAST, SUSTAINED, the thresholds, the refractory and the motor output are all
    the unchanged runtime code: the research policy is a subclass of the runtime
    `FixedEscapePolicy`;
  - whenever LONG does not fire alone, the combined decoder reproduces N4B1C sample for
    sample (unit check).
- **Diagnostic precedence:** LATERAL, FAST, SUSTAINED, then LONG.
- **Inputs:** only the DNp01 traces already in `MotorState`. No geometry, Retina, encoder
  output, paddle coordinate or world distance gates the path.

### 2.2 Preregistered decision rule (summary)

L1 is recommended only if all of the following hold on fresh data:

1. **130 units/s:** pooled A2 / C2 / C3 combined timely >= 0.70 and >= +0.40 over N4B1C;
   each >= 0.50; median lead >= 0.25 s.
2. **Fixed fly:** N0 (>= 280 min) combined upper 95 % < 0.1/min; stationary / receding
   controls and pre-holds < 0.1/min.
3. **Free flight** (N4B1C OR L1 live): categories B and A each < 0.1/min at 95 %.
4. **Direct strikes:** coverage not lower and median latency not more than +0.02 s later
   (fresh N1; development human replays).
5. **Repetition:** no run with >= 3 LONG escapes within 5 s.
6. **50 units/s:** not used.

## 3. Data

**Development (already inspected; characterisation only):**

- stored fixed-fly N0, 840 min (N4B2 chunks, per-side DNp01 spikes);
- N4B6 controlled trajectories (48 seeds);
- both human sessions (recorded traces, plus the G3 open-loop recomputation over five noise
  realizations);
- the 83 N4B5R no-player ROOM runs under the accepted runtime (249 min, per-tick DNp01
  traces), evaluated in shadow mode;
- N1 (G3, the N1 seeds).

**Fresh holdouts (new, non-overlapping seeds):**

| Holdout | Seeds | Size | Mode |
|---|---|---|---|
| A. fixed-fly N0 | 800001-800720 | 720 trials x 28 s = **336 min** | accepted ROOM config, ecology off, fixed fly, paddle hovering stationary at a per-trial offset (radius 30-170) |
| B. no-player ROOM free flight | 7601-7680 | 80 runs x 3 min = **240 min** | closed loop. Each seed is run with N4B1C live (reference; L1-L3 in shadow) and with **N4B1C OR L1 live**. Every live escape is re-run with the escape withheld for 2 s (category-B counterfactual) |
| C. controlled approaches | 700001-700096 | the 15 frozen N4B6 trajectories x **96 new seeds** | identical physical trajectories (N4B6 protocol sha256 `01d91ab8...`) |
| D. committed strikes | 900001-900120 | 60 strong_direct + 60 medium_committed | N1 script, per-trial rng, accepted config |

## 4. Development results (inspected data; not validation)

| Development measure | N4B1C | L1 combined | L2 combined | L3 combined |
|---|---|---|---|---|
| Stored N0, 840 min: events (upper) | 3 (0.009) | 7 (0.016) | 3 (0.009) | 3 (0.009) |
| N4B6 A2 / C2 / C3 timely (48 seeds) | 4 / 0 / 6 % | **94 / 94 / 100 %** | 56 / 46 / 73 % | 79 / 77 / 90 % |
| N4B6 median lead, A2 / C2 / C3 (s) | 0.08 / - / 0.82 | 1.04 / 1.56 / 1.79 | 0.42 / 0.47 / 1.12 | 0.74 / 0.74 / 1.38 |
| N4B6 orbit control (stop rotation), responses / 48 | 17 | 27 | 18 | 22 |
| N4B5R free flight, 249 min, shadow: added LONG-only firings | - | **185** (B 43, D 104, C 5, mixed 33) | 66 (B 9) | 117 (B 21) |
| N1 (G3) strong / medium: covered, median | 60, 0.08 / 60, 0.10 | identical | identical | identical |

The development free-flight shadow evaluation **already predicted the holdout failure**:
43 B events in 249 min, upper about 0.22/min. **The candidates were not changed in
response.** L1 is the user-specified primary, and N4B7 was scoped to validate it on fresh
data, not to redesign it.

### 4.1 Human sessions (development evidence; open-loop replays)

The table shows the recorded traces and the G3 recomputation in five brain-noise
realizations.

| Realization | N4B1C firings | L1 combined firings | Added LONG-only (A / B / C / D / mixed) | Added before an N4B1C trigger (<= 1 s) | Direct strikes covered (N4B1C -> L1), median after click (s) | Hover bouts detected | Far perched / voluntary takeoff |
|---|---|---|---|---|---|---|---|
| recorded | 82 | 109 | 44 (3 / 4 / 0 / 21 / 16) | 34 | 39 -> 39, -0.02 -> -0.04 | 33 -> 33 | silent / silent |
| G3 noise 0 | 78 | 106 | 48 (1 / 5 / 0 / 27 / 15) | 37 | 38 -> 38, -0.03 -> -0.11 | 26 -> 29 | silent / silent |
| G3 noise 1 | 70 | 99 | 44 (1 / 3 / 1 / 25 / 14) | 34 | 39 -> 39, 0.06 -> -0.04 | 25 -> 26 | silent / silent |
| G3 noise 2 | 77 | 100 | 41 (0 / 3 / 1 / 25 / 12) | 32 | 38 -> 38, -0.01 -> -0.09 | 22 -> 25 | silent / silent |
| G3 noise 3 | 76 | 105 | 50 (5 / 2 / 0 / 29 / 14) | 37 | 38 -> 38, 0.00 -> -0.08 | 26 -> 28 | silent / silent |
| G3 noise 4 | 74 | 99 | 44 (0 / 4 / 0 / 26 / 14) | 33 | 38 -> 38, -0.02 -> -0.06 | 25 -> 28 | silent / silent |

- **Direct strikes are not damaged.** Coverage is equal. The median latency moves earlier
  (negative means before the click) because LONG often fires during the approach that
  precedes the click.
- **About 40-50 extra firings per replay (+55-70 %).**
  - Most occur during hover / approach phases with the paddle closing.
  - About three quarters precede an N4B1C trigger within 1 s, so they anticipate a response
    N4B1C would give anyway.
- **Classification caveats:**
  - Categories are applied with the accepted geometric rules.
  - "B" uses the recorded future as the no-escape counterfactual, which is approximate
    because the replay is open loop.
  - "A" uses the accepted 10-tick drive lookback. A 1 s integrator can fire after the drive
    ended more than 10 ticks earlier, so "A" here does not necessarily mean no visual
    input.

## 5. Fresh holdout results

### 5.1 Fixed-fly N0 (336 min, 720 trials)

| Decoder | Events | Rate / upper 95 % (per min) | LONG-path events | Max LONG events in 5 s |
|---|---|---|---|---|
| N4B1C | 2 (FAST, FAST) | 0.006 / 0.019 | 0 | 0 |
| **N4B1C OR L1** | **3** | **0.009 / 0.023** | 1 (4 spikes, one side) | 1 |
| L1 alone | 1 | 0.003 / 0.014 | 1 | 1 |
| N4B1C OR L2 | 2 | 0.006 / 0.019 | 0 | 0 |
| N4B1C OR L3 | 2 | 0.006 / 0.019 | 0 | 0 |

**Category A (fixed-fly neural false escapes) passes clearly for every candidate.**

### 5.2 Controlled approaches (96 fresh seeds per trajectory)

Timely = a trigger at or before closest approach. Times are from motion onset. "Ev/appr" is
the mean number of escape events between onset and closest approach in open loop, where the
fly cannot move.

**130 units/s family (primary target):**

| Trajectory | Decoder | Timely | Miss | Median / p95 trigger (s) | Median lead (p05) (s) | Median distance at trigger (horizontal / range) | Paths | Ev/appr |
|---|---|---|---|---|---|---|---|---|
| A2 frontal (= C1) | N4B1C | 4.2 % | 0.96 | 4.64 / 5.14 | 0.84 (0.34) | 298 / 437 | FAST 4 | 0.04 |
| | L1 alone | **100 %** | 0.00 | 4.52 / 5.24 | 0.96 (0.24) | 314 / 448 | LONG 96 | 1.53 |
| | **N4B1C OR L1** | **100 %** | 0.00 | 4.52 / 5.24 | **0.96 (0.24)** | 314 / 448 | LONG 93, FAST 3 | 1.53 |
| C2 oblique left | N4B1C | 10.4 % | 0.90 | 5.10 / 5.27 | 0.38 (0.21) | 238 / 399 | FAST 9, LATERAL 1 | 0.10 |
| | L1 alone | **100 %** | 0.00 | 4.03 / 5.08 | 1.45 (0.40) | 377 / 495 | LONG 96 | 1.83 |
| | **N4B1C OR L1** | **100 %** | 0.00 | 4.01 / 5.08 | **1.47 (0.40)** | 380 / 497 | LONG 94, FAST 1, FAST+LONG 1 | 1.88 |
| C3 lateral, close | N4B1C | 6.2 % | 0.94 | 4.97 / 5.96 | 1.27 (0.29) | 255 / 410 | FAST 6 | 0.06 |
| | L1 alone | **100 %** | 0.00 | 4.52 / 5.24 | 1.72 (1.00) | 314 / 448 | LONG 96 | 2.15 |
| | **N4B1C OR L1** | **100 %** | 0.00 | 4.52 / 5.24 | **1.72 (1.00)** | 314 / 448 | LONG 93, FAST 3 | 2.17 |

- Pooled over A2 / C2 / C3: **100 % against 6.9 % for N4B1C**, median lead 1.42 s.
  Criterion 1 passes.
- Comparison rules on the same data:

  | Rule | A2 | C2 | C3 |
  |---|---|---|---|
  | L2 | 48 % | 57 % | 74 % |
  | L3 | 80 % | 83 % | 97 % |

**50 units/s (A1, not a decision input):** N4B1C 1 %, L1 combined 2 %. As expected, the
long window does not rescue the stimulus-limited case.

**Faster and other approaches (preservation):**

| Trajectory | N4B1C timely, median trigger, lead | N4B1C OR L1 timely, median trigger, lead | Note |
|---|---|---|---|
| B1 300 units/s | 31 %, 2.06 s, 0.40 s | **100 %, 1.07 s, 1.39 s** | fires at 582 units horizontal (664 range) |
| B2 800 units/s | 99 %, 0.60 s, 0.40 s | 100 %, 0.48 s, 0.52 s | earlier, not pathological: 521 units horizontal, 0 pre-hold events |
| D1 glancing 130, miss 300 | 0 % | 0 % | |
| D2 glancing 300, miss 300 | 1 % | **76 %** | passes at >= 439 range; arguably not a threat |
| D3 glancing 130, miss 150 | 0 % | 26 % | |
| E1 abort at 400 units | 1 % | 23 % (before reversal) | |
| E2 abort at 300 units | 17 % | 100 % (before reversal) | |

- **No pathological early firing:** 0 pre-hold events in all 15 x 96 trials, for every
  decoder.
- **Repeated firing (open loop):**
  - L1 fires about 1.5-2.8 times per approach, because the fixed fly keeps receiving the
    stimulus after each 0.4 s refractory.
  - In the game the first escape moves the fly. In free flight, repeated firing does occur
    (section 5.4).

### 5.3 Controls

| Control (96 seeds) | Stimulus min | N4B1C | N4B1C OR L1 | L1 alone | L2 comb. | L3 comb. |
|---|---|---|---|---|---|---|
| F1 stationary at 200 units | 18.4 | 0 | **0** | 0 | 0 | 0 |
| F2 receding 200 -> 900 | 11.1 | 0 | **0** | 0 | 0 | 0 |
| pre-trial stationary holds (15 x 96 x 2 s) | 48.0 | 0 | **0** | 0 | 0 | 0 |
| **F3 orbit, stop-rotation transient** | 13.6 | 27 / 96 trials | **46 / 96** (LONG 19, LONG+FAST 1) | 31 | 30 | 41 |

- **The long path reacts to the N4B6 stop-rotation transient.** When the orbiting paddle
  stops, the controller's overshoot correction rotates it. Through the accepted tilt term
  that gives 0.35 rad/s of apparent expansion at constant range.
- L1 adds 19 responses. They come shortly after the N4B1C ones (median 7.55 s against
  7.48 s from onset).
- This is reported, not filtered: no new context was added to hide it. It is category C
  (apparent-size / tilt geometry), as in N4B6.

### 5.4 Free flight (240 min, 80 runs, closed loop, accepted N4B4 metric split)

| Live decoder | Escapes | Per min | A | B | C | D | mixed | Paths |
|---|---|---|---|---|---|---|---|---|
| N4B1C (reference) | 9 | 0.037 | 1 | 2 (upper 0.026) | 0 | 6 | 0 | FAST 8, SUSTAINED 1 |
| **N4B1C OR L1** | **167** | **0.70** | 4 (upper 0.038) | **44 (0.18/min, upper 0.24)** | 0 | **103** | 16 | **LONG 162**, FAST 4, FAST+LONG 1 |

LONG-path escapes in the live L1 runs:

- **163 escapes in 69 of 80 runs**, all AIRBORNE; left 81, right 82; always exactly 4
  spikes at firing.
- **N4B1C would already have fired** in the same bout (N4B1C-alone replay on the same
  traces, within 1 s after the LONG firing) in **only 4 of 163**. The LONG escapes are
  almost entirely additions, not earlier versions of existing responses.
- **B events (42 LONG-only):**
  - the fly flies toward the parked paddle: median 507 units horizontal distance, median
    closing speed 129 units/s;
  - with the escape withheld it passes at a median of 362 units without coming within 310.
- **D events (102 LONG-only):** genuine self-approach, at a median 360 units horizontal and
  138 units/s closing.
- **A events (3 LONG-only):** no encoder drive over the whole 50-tick window, i.e. neural
  coincidences during flight. Upper 0.038/min, within target.
- **Repetition:**
  - 34 LONG escapes followed another escape in the same run within 5 s;
  - 2 runs contain 3 LONG escapes within 5 s (seeds 7644 and 7654, each while the fly kept
    closing on the parked paddle after escaping). Criterion 5 fails.

Shadow evaluation on the N4B1C reference runs of the same seeds (N4B1C replay exact in
80 / 80 runs). The added LONG-only firings, if they were escapes:

| Rule | Added | B (upper) | D | Before an N4B1C escape within 1 s |
|---|---|---|---|---|
| L1 | 209 | 53 (0.28) | 123 | 5 |
| L2 | 92 | 9 (0.065) | 59 | 1 |
| L3 | 141 | 22 (0.13) | 91 | 4 |

- Shadow and closed-loop L1 agree in magnitude.
- **L2 would pass the category-B criterion in shadow.** But it is a comparison rule; it
  detects only 48-74 % of the 130 units/s approaches; and it still adds about 0.38 LONG
  firings per minute of free flight. **Per the preregistered rule it is not promoted, and
  nothing is tuned toward it.**

### 5.5 Fresh committed strikes (N1 script, 60 + 60)

| Class | N4B1C | N4B1C OR L1 | L1 alone |
|---|---|---|---|
| strong_direct | 60 / 60, median 0.08 s, p95 0.08 | **60 / 60, 0.08 / 0.08** | 60 / 60, 0.14 / 0.16 |
| medium_committed | 60 / 60, 0.08 / 0.10 | **60 / 60, 0.08 / 0.10** | - |

Direct-strike behaviour is unchanged by the additional path. LONG alone would be too slow
for strikes, as expected, but it never replaces N4B1C.

## 6. Decision (preregistered, applied mechanically)

`tools/n4b7_long_readout.py analyze` -> `artifacts/m1_8_n4b7/holdout.json`, sha256
`b3b4f3dc...70c3`.

| Condition | Result |
|---|---|
| 1. 130 units/s material improvement | **pass** (100 % against 6.9 %, lead 1.42 s) |
| 2. Fixed fly (N0 336 min; controls and pre-holds 77 min) | **pass** (upper 0.023; 0.039) |
| 3. Free flight: B and A < 0.1/min at 95 % | **FAIL**: B 44 in 240 min, upper 0.24 (A passes, upper 0.038) |
| 4. Direct strikes | **pass** (fresh N1 identical; human replays equal coverage, earlier median) |
| 5. No pathological repetition | **FAIL** (2 free-flight runs with 3 LONG escapes in 5 s) |
| 6. No reliance on 50 units/s | satisfied |

**L1 is not recommended as a runtime candidate.** Nothing was tuned against the holdout.
The frozen alternative applies: keep the accepted runtime and document the slow-approach
limitation.

## 7. Interpretation

- **The information exists but is not specific.**
  - A fixed fly facing a slow approach and a flying fly closing on a stationary paddle at
    100-160 units/s receive the same Retina input: a slowly growing, range-driven
    expansion.
  - They therefore produce the same weak LPLC2 / LC4 drive and the same slow rise of DNp01
    rate.
  - Any DNp01-only readout sensitive enough to catch the first also catches the second.
- **This is the N4B3 result again, now for DNp01 on a long timescale.**
  - In flight, policy-observable neural signals cannot separate self-generated from
    external looming.
  - N4B3 already showed that the MotionState overlap prevents simple self-motion gates.
- **Why the accepted N4B1C is quiet in free flight:** its short coincidence windows need a
  burst, and only a fast (usually external) expansion produces one. That same property is
  what makes it miss slow external approaches. **With these inputs, the slow-approach blind
  spot and free-flight quietness are two sides of the same trade-off.**
- **Stationary settings are clean.** On the fixed fly (N0, stationary / receding
  controls) the long path is almost silent (1 event in 336 min). The false positives come
  from self-motion, not from neural noise.

## 8. Biological interpretation

**A. Direct biological evidence (primary literature):**

- DNp01 is the giant fiber (GF). Its looming input comes from the visual projection neurons
  LC4 and LPLC2. LC4 conveys expansion-velocity information and LPLC2 angular-size
  information, and the GF combines them.
  - von Reyn et al. 2017, *Neuron* 94:1190;
  - Ache et al. 2019, *Current Biology* 29:1073.
- GF output is sparse. A GF spike drives the fast "short-mode" takeoff through a reliable
  GF-to-motor-neuron pathway.
- Slower looming stimuli mostly elicit "long-mode" takeoffs, which can occur without any GF
  spike and are driven by parallel descending pathways. The relative timing of the GF spike
  selects between the two modes (von Reyn et al. 2014, *Nature Neuroscience* 17:962).
- Before takeoff, flies make direction-dependent postural adjustments (Card & Dickinson
  2008, *Current Biology* 18:1300).

**B. Literature-inspired interpretation:**

- In real flies, responses to slow approaches are plausibly carried by slower, GF-
  independent descending pathways, not by accumulating GF spikes.
- A longer-timescale readout resembles that biological channel only in its time scale.
- In this simulator, the non-GF DNs tested in N4B2 are either not earlier or not selective
  (DNp04). **The simulator has no validated long-mode channel.**

**C. Simulator engineering decoder:**

- L1 counts the inferred spikes of the simulator's DNp01 model over 1 s. That model is a
  noisy point neuron which, under weak drive, emits sustained low-rate trains; the real GF
  gives sparse output.
- **L1 is a Class C engineering decoder. It does not claim that a fly counts four DNp01
  spikes in one second.**
- Its failure mode, responding to self-generated looming, is a property of the simulator's
  information content. It is not evidence about real flies.

## 9. Recommendation

1. **Do not adopt L1** (or L2 / L3). Keep the accepted runtime (N4B5R) unchanged and keep
   the slow-approach limitation documented (N4B6).
2. **Do not tune on this holdout.** The seeds 700001-700096, 800001-800720, 900001-900120
   and ROOM 7601-7680 are now used.
3. **What N4B7 establishes for any future slow-approach work:** a purely DNp01-temporal
   readout cannot be both sensitive to 130 units/s approaches and specific in free flight.
   Plausible directions all cross an architectural boundary and need explicit approval.
   Listed for completeness, not recommended here:
   - a stationary-fly-restricted long path, analogous to the N4B3 stationary-fly DNp04
     path. It uses MotionState, which is already policy-observable, but it is a new
     candidate and would help only a stationary or perched fly;
   - a policy-observable self-motion signal specific enough to cancel self-generated
     expansion. N4B3 found none in the current MotionState;
   - a biological long-mode pathway model (new descending-neuron channels or encoder
     changes).

## 10. Reproducibility

Commands (main checkout, main virtual environment; outputs in `artifacts/m1_8_n4b7/`,
git-ignored):

    python tools/n4b7_long_readout.py dev-n0 --worker K --workers 4      (K = 0..3)
    python tools/n4b7_long_readout.py dev-controlled | dev-room | dev-n1 | dev-human
    python tools/n4b7_long_readout.py dev-summary
    python tools/n4b7_long_readout.py freeze                              (done once, before holdouts)
    python tools/n4b7_long_readout.py hold-n0 --worker K --workers 2
    python tools/n4b7_long_readout.py hold-room --worker K --workers 3    (NUMBA_NUM_THREADS=1; optional extra workers with --reverse)
    python tools/n4b7_long_readout.py hold-controlled --worker K --workers 2
    python tools/n4b7_long_readout.py hold-n1 --worker K --workers 2
    python tools/n4b7_long_readout.py analyze

| File | sha256 |
|---|---|
| `tools/n4b7_candidates.py` (frozen) | `6b69a44795a6b09cd5676ccee3ca2d0e9a9a6b76f8166d4bd119c506639e0d4e` |
| `tools/n4b7_long_readout.py` (final) | `b409d022f938b2485d42a1e379ff03a7fe3d8b305ef352e4e7177bcf9250cbd5` |
| `preregistration.json` | `b25493c2e675a29402511061ff2de9553126aab18516ada34016b29ccbe7c529` |
| `holdout.json` | `b3b4f3dcd79c3b09ba3e6c2bd391c677ffab9043bf8e8e9425476c03ee5070c3` |
| `dev_n0.json` | `32ca2f9165edfa84162dbb0d3891b26c886bba1c3729218c15afd6da1fd08e14` |
| `dev_controlled.json` | `c511e82328ea40a5ac05decfb85f53f5cffad69113c629a32f09cfc228c5f228` |
| `dev_room.json` | `62efda6a9e7df8cdeca88c92dd81c2c3dcbc2dcbcff45871b15d4503f7d5307c` |
| `dev_n1.json` | `c8b5362c22791f7713abcba33635ca9bf088889391f765295358d89f95c85a63` |
| `dev_human.json` | `d36c5d2320382109ab5928d8d2f302455bc8cc455d3b993d44ebe49b315fb243` |

Runner changes after the freeze were infrastructure only:

- a `--reverse` option so extra ROOM workers could share the queue;
- atomic result writes;
- an extra `max_drive_last_50` field on LONG event records.

The candidate module, and therefore the rules, did not change (checked by hash on every
holdout run).

## 11. Limitations

- **Fixed-fly controlled approaches:** in the game, a slow approach toward a flying fly
  combines both stimuli. L1 would detect it, but it would equally fire on the fly's own
  approaches.
- **Free-flight categories:** they use the accepted geometric rules and the 2 s
  counterfactual. D events (genuine self-approach) are tracked, not failures, but at
  0.43/min they would visibly change behaviour.
- **Human-session evidence is development-only** and open loop.
- **Literature statements in section 8** are summarised at the level of well-established
  findings. They are not used for any decision.
