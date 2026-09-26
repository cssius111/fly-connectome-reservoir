# M1.8-N1: loom robustness and stimulus generalisation study

Status: **accepted and frozen as a research result. Nothing implemented.** No runtime
code, configuration, threshold, brain parameter or calibration file was changed. The
decoder still fires on a single sample at 1.45. B2b-ii remains frozen at `0d8c254`;
N0 is committed at `3d41113`. The user decisions taken on this evidence are recorded in
section 13.

Artifacts: `artifacts/m1_8_loom_robustness/` (`trials.npz`, `trials_meta.json`,
`analysis.json`, `hybrid_no_loom.json`). Reproduced by `tools/loom_robustness_study.py`
and `tools/loom_robustness_analysis.py`.

## 1. Headline

Every candidate decoder tested fires on **60/60** trials of both committed-strike classes,
so no candidate endangers the strong positive reference.

The binding result is elsewhere. **At the single-event level, weak non-contact approaches
are not separable from spontaneous no-loom coincidences using DNp01 alone** - not by peak
amplitude, and not by short-window integration. Consequently *every* criterion that
suppresses the N0 false-trigger mechanism also suppresses a large fraction of
weak-approach firings. This is a property of the signal, not a tuning failure.

Whether that matters is a labelling question this study cannot settle: the weak classes
have **no independently justified positive behavioural label**, are **0% geometric contact
course**, and are **100% receding** after closest approach.

## 2. Terminology

Because a retinal looming stimulus is not automatically a ground-truth escape event, four
things are reported separately and never conflated:

| | Meaning | How it is established |
| --- | --- | --- |
| **A** physical / retinal stimulus | `theta_dot > 0` occurred | recorded retina |
| **B** neural response | non-zero LC4/LPLC2 drive and a DNp01 excursion | recorded encoder and trace |
| **C** criterion fired | candidate satisfied inside the response window | offline evaluation |
| **D** positive behavioural label | independently justified "must escape" | **only the committed-strike classes** |

For classes without **D**, this document reports a **criterion firing rate** and a **miss
relative to the legacy decoder**. It does not call a non-firing trial a false negative.

## 3. Stimulus matrix and physical provenance

All stimuli are delivered through the real chain: scripted pointer trajectory -> physical
swatter -> Retina -> encoder -> MaleCNS -> DNp01, on accepted fixed-fly-v2 conditions
(escape disabled, fly motion disabled, collisions disabled, paddle settled 6.0 s with the
existing velocity assertion, verified settled on 300/300 trials). **No direct LC4/LPLC2
injection is used anywhere**, not even as a secondary diagnostic.

`strong_direct` is the **exact accepted reference arm**: the accepted offset geometry
(lateral 5-55 units, vertical +/-40), 90 ticks, click at tick 20, unchanged.
`medium_committed` differs only in that the paddle starts further out, at a radius of
150-260 units, and is otherwise the same committed strike; it therefore has a longer
approach and a smaller peak expansion rate.

Class names are **engineering test categories, not biological categories**. 60 trials each.

| Class | Median peak theta | Median peak theta_dot | Median peak DNp01 | Min / max peak DNp01 |
| --- | --- | --- | --- | --- |
| strong_direct | — | 16.16 | 4.22 | 2.94 / 5.42 |
| medium_committed | — | 7.17 | 3.90 | 2.90 / 5.31 |
| weak_approach | — | 0.43 | 1.84 | 1.30 / 2.58 |
| glancing_pass | — | 0.45 | 1.84 | 1.20 / 2.46 |
| aborted_approach | — | 0.58 | 2.02 | 1.37 / 3.30 |

### 3.1 Physical geometry labels (diagnostic only, never exposed to the policy)

| Class | Median min paddle-centre distance | Median min edge clearance | Horizontal overlap | Descends to strike height | **Geometric contact course** |
| --- | --- | --- | --- | --- | --- |
| strong_direct | 29 | **-126** | 100% | 100% | **100%** |
| medium_committed | 197 | +42 | 17% | 100% | **17%** |
| weak_approach | 181 | +26 | 25% | 0% | **0%** |
| glancing_pass | 350 | +195 | 0% | 0% | **0%** |
| aborted_approach | 328 | +173 | 0% | 0% | **0%** |

All three non-committed classes are **100% receding** after closest approach.

Vertical clearance was verified rather than assumed: across a full non-committed approach
the paddle remains at hover height **320.0** with phase `approach` throughout, against an
`active_height` of 24.0, so contact is geometrically impossible for those classes. Only
committed strikes descend.

Worth recording: `medium_committed` is only **17%** contact course yet fires 100% under
every criterion, so the current decoder already fires readily on committed strikes that
would physically miss.

## 4. Temporal shape: where genuine loom really differs

Per-trial medians, against the N0 no-loom worst case over 70 minutes:

| Class | Median peak DNp01 | Median longest run >= 1.45 | Median longest run >= 1.80 |
| --- | --- | --- | --- |
| strong_direct | 4.22 | **17 ticks** | **15 ticks** |
| medium_committed | 3.90 | **14 ticks** | **11 ticks** |
| weak_approach | 1.84 | 2 ticks | 1 tick |
| glancing_pass | 1.84 | 2 ticks | 1 tick |
| aborted_approach | 2.02 | 2 ticks | 1 tick |
| **N0 no-loom (worst case)** | **2.005** | **2 ticks** | **1 tick** |

This is the central structural fact. Committed strikes differ from spontaneous
coincidences far more in **duration** (14-17 ticks versus a worst case of 2) than in
**amplitude** (4.2 versus 2.0). The three weak classes match the no-loom worst case on
both duration measures.

## 5. Are the weak classes a real neural response?

Yes - as a population, though not distinguishable per event. Comparing against
**matched-length** no-loom blocks, which is the correct comparator:

| | Fraction of trials reaching DNp01 >= 1.45 |
| --- | --- |
| No-loom, 150-tick blocks (n=1400) | **6.5%** |
| weak_approach | **91.7%** |
| glancing_pass | **85.0%** |
| aborted_approach | **96.7%** |

Median peak is 1.75-1.95 for the weak classes against 1.00 for matched no-loom blocks, a
13-15x enrichment in crossing rate. So **(A) stimulus, (B) neural response and (C) legacy
firing are all genuinely present** in the weak classes; what is absent is **(D)**, and what
is impossible is per-event discrimination.

## 6. Peak thresholding versus short-window integration

Margin = class minimum minus the no-loom worst case; positive means perfectly separable.
Ratio is class-minimum / no-loom-worst-case.

| Class | Peak | 60 ms integral | 100 ms integral | 200 ms integral |
| --- | --- | --- | --- | --- |
| strong_direct | +0.89 (r 1.45) **sep** | +3.23 (r 1.65) **sep** | +6.38 (r 1.91) **sep** | +15.73 (r **2.62**) **sep** |
| medium_committed | +0.70 (r 1.35) **sep** | +3.06 (r 1.61) **sep** | +6.04 (r 1.86) **sep** | +13.76 (r **2.41**) **sep** |
| weak_approach | -0.70 (r 0.65) | -1.75 (r 0.65) | -2.45 (r 0.65) | -1.49 (r 0.85) |
| glancing_pass | -0.80 (r 0.60) | -2.00 (r 0.60) | -2.80 (r 0.60) | -3.14 (r 0.68) |
| aborted_approach | -1.01 (r 0.50) | -1.58 (r 0.68) | -2.22 (r 0.68) | -1.47 (r 0.85) |

**Answer to the question posed:** temporal integration separates genuine committed loom
from spontaneous coincidences substantially better than peak thresholding - the margin
ratio roughly doubles from 1.35-1.45 to 2.41-2.62 at a 200 ms window. It does **not** help
for the weak classes, whose ratios stay below 1 at every window. No cutoff is chosen here.

## 7. Latency accounting

`persist = N` means **N consecutive samples at or above threshold, including the first
crossing sample**, so the criterion is satisfied on the Nth sample and an uninterrupted
run costs exactly **(N-1) x 20 ms**.

Measured on `strong_direct`, latency from click:

| Threshold | N=1 | N=2 | N=3 | N=4 | Increase matches (N-1)x20 ms? | Median extra ticks after first crossing |
| --- | --- | --- | --- | --- | --- | --- |
| 1.45 | 0.080 | 0.100 | 0.120 | 0.140 | **yes, exactly** | 0, 1, 2, 3 |
| 1.60 | 0.080 | 0.100 | 0.120 | 0.140 | **yes, exactly** | 0, 1, 2, 3 |
| 1.80 | 0.100 | 0.120 | 0.140 | 0.160 | **yes, exactly** | 0, 1, 2, 3 |
| 2.00 | 0.100 | 0.160 | 0.180 | 0.200 | **no** (+60 not +20) | 0, **3**, 4, 5 |
| 2.05 | 0.100 | 0.160 | 0.180 | 0.200 | **no** (+60 not +20) | 0, **3**, 4, 5 |

**Why the excess at 2.0 and above:** the first crossing of a high threshold is on the
rising edge and is **not sustained** - the trace dips back below before N consecutive
samples accumulate - so the criterion skips that crossing and waits for the next
qualifying run. The extra cost is signal shape, not the persistence rule.

Correcting the N0 summary: the "+60 ms" quoted there for **1.8 / N3** decomposes cleanly
as **+20 ms from raising the threshold 1.45 -> 1.8** and **+40 ms structural from N=3**.
All of it is accounted for; none is signal shape at that threshold.

## 8. Joint N0 + N1 decision table

N0 columns are **observed** over 70 minutes of no-loom exposure; zero-count cells carry a
95% upper bound of **<= 0.053/min** and are **not** demonstrated below that. N1 columns are
**observed** firing rates over 60 trials per class (exact binomial CIs in `analysis.json`).
Nothing here is model-estimated. The behavioural significance of the weak-class columns is
**unresolved**.

| Criterion | N0 false/min | strong | medium | weak | glance | abort | Strong latency | Misses vs legacy |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| **1.45 / N1 (legacy)** | **1.3000** | 1.00 | 1.00 | 0.92 | 0.85 | 0.97 | 0.080 s | 0 |
| 1.80 / N1 | 0.4857 | 1.00 | 1.00 | 0.62 | 0.48 | 0.77 | 0.100 s | 52 |
| 2.00 / N1 | 0.2429 | 1.00 | 1.00 | 0.43 | 0.30 | 0.45 | 0.100 s | 93 |
| 2.05 / N1 | 0 (<=0.053) | 1.00 | 1.00 | 0.43 | 0.25 | 0.38 | 0.100 s | 100 |
| 2.10 / N1 | 0 (<=0.053) | 1.00 | 1.00 | 0.33 | 0.22 | 0.37 | 0.100 s | 109 |
| 1.45 / N2 | 0.4857 | 1.00 | 1.00 | 0.67 | 0.48 | 0.78 | 0.100 s | 48 |
| 1.45 / N3 | 0 (<=0.053) | 1.00 | 1.00 | 0.27 | 0.15 | 0.32 | 0.120 s | 120 |
| 1.60 / N2 | 0.2429 | 1.00 | 1.00 | 0.43 | 0.32 | 0.43 | 0.100 s | 93 |
| 1.80 / N2 | 0 (<=0.053) | 1.00 | 1.00 | 0.22 | 0.12 | 0.30 | 0.120 s | 126 |
| 1.80 / N3 *(N0 pick)* | 0 (<=0.053) | 1.00 | 1.00 | **0.00** | **0.00** | 0.05 | 0.140 s | 161 |
| 2.00 / N2 | 0 (<=0.053) | 1.00 | 1.00 | 0.03 | 0.03 | 0.10 | 0.160 s | 154 |
| **fast 2.20 OR 1.45 x N2** | 0.4857 | 1.00 | 1.00 | 0.67 | 0.48 | 0.78 | 0.100 s | 48 |
| **fast 2.20 OR 1.45 x N3** | **0 (<=0.053)** | 1.00 | 1.00 | 0.27 | 0.15 | 0.32 | **0.100 s** | 120 |
| fast 2.40 OR 1.60 x N2 | 0.2429 | 1.00 | 1.00 | 0.43 | 0.32 | 0.43 | 0.100 s | 93 |
| fast 2.40 OR 1.60 x N3 | 0 (<=0.053) | 1.00 | 1.00 | 0.08 | 0.05 | 0.17 | 0.120 s | 146 |

## 9. Assessment against the decision rule

| Requirement | Best achievable | Comment |
| --- | --- | --- |
| Materially suppress the no-loom failure | **met** | 1.30/min -> 0 observed (<= 0.053/min) by several candidates |
| Preserve strong loom detection | **met** | 60/60 on both committed classes for every candidate tested |
| Preserve reasonable weaker-loom response | **not met by any candidate** | see below |
| Avoid unnecessary latency penalty | **met** | hybrid costs +20 ms; 1.8/N3 costs +60 ms |
| Neural-only causal semantics | **met** | DNp01 trace only |
| No raw mouse/world threat gate | **met** | none used |

**The third requirement is not satisfiable with a DNp01-only criterion**, and section 6
shows why: weak-class events overlap the no-loom distribution in peak (ratio 0.60-0.65)
and in every integration window (0.60-0.85). Any rule that removes 2-tick spontaneous
coincidences necessarily removes 2-tick weak-approach responses, because at the level of a
single event they are the same shape and size. Reporting this as a failure to find a good
criterion would be wrong; it is a limit of the signal.

## 10. Recommendation, conditional and unimplemented

**No decoder is selected.** The choice depends on a labelling decision this study cannot
make.

*If* weak non-contact approaches need not trigger escape - defensible given they are 0%
geometric contact course, 100% receding, and carry no independent behavioural label -
then the best candidate on the evidence is:

> **fast 2.20 OR (1.45 sustained for 3 samples)**

It dominates the N0 pick of 1.8/N3 on three axes simultaneously: identical no-loom
suppression (0 observed, <= 0.053/min), **lower** latency on strong loom (0.100 s versus
0.140 s, because the fast path fires immediately on a genuine strike), and **fewer** misses
relative to the legacy decoder (120 versus 161, retaining 0.27/0.15/0.32 weak firing rather
than 0.00/0.00/0.05). It uses DNp01 only and adds no gate.

*If* weak-approach responsiveness must be preserved at anything like legacy levels, then
**no tested criterion is acceptable**, and the false-trigger problem would have to be
addressed outside the decoder - which means the high-risk brain-noise option from
`M1_8_NO_LOOM_FALSE_ESCAPE.md`, or accepting the 1.30/min rate.

## 11. Uncertainty

- Firing rates are 60 trials per class; exact binomial intervals are in `analysis.json`.
  A rate of 0.27 carries roughly +/-0.12 at 95%.
- The weak, glancing and aborted classes are **scripted engineering probes**, not a
  sampled distribution of real threats. Their firing rates should not be read as "the fly
  will miss 73% of real weak threats".
- N0 zero-count cells remain bounded at <= 0.053/min, not demonstrated below that; the
  <0.01/min target is still unresolved and would need about 900,000 zero-event ticks.
- The hybrid family was evaluated on the existing N0 traces and the N1 matrix; it has not
  been tested in closed loop, against a moving fly, or in ROOM.
- Latency here is click-to-firing under fixed-fly conditions and is not the same quantity
  as the 0.169-0.369 s escape latencies recorded in accepted human sessions.
- Only committed strikes were tested with the paddle descending. A slow descending
  approach that is neither a committed strike nor a hover-height pass was not measured.

## 12. Remaining approval decisions

1. **Do weak, non-contact, receding approaches need to trigger escape?** This is the
   blocking question. Everything else follows from it.
2. If no: adopt the hybrid family in principle, and choose its parameters?
3. If yes: accept 1.30 false escapes per minute, or open the high-risk brain-noise route?
4. Adopt an explicit Class-C false-trigger target, given only <1 and <0.1 per minute are
   resolvable at current exposure?
5. Is a dual-timescale criterion acceptable as a decoder rule, given it adds temporal
   structure to what is currently a single-sample readout?
6. Should the hybrid be validated in closed loop and in ROOM before any decision?
7. Recalibration scope and the new transfer-chain link, for any threshold change.
8. Narrow human re-acceptance of threat-triggered takeoff feel, expected for any change
   that moves the threshold or adds latency.

Nothing in this document is implemented.

## 13. Decision record (user, on acceptance of N1)

- **Decision 1 resolved: no.** Weak, non-contact, receding approaches are not required to
  trigger behavioural escape. This covers `weak_approach`, `glancing_pass` and
  `aborted_approach` only insofar as the recorded geometry establishes that they are
  non-contact, have zero geometric collision probability in the tested setup, and are
  already receding after closest approach.
- These stimuli remain legitimate retinal and neural stimuli. Retina, LC4/LPLC2 and
  MaleCNS responses to them are not removed; they are simply not positive ground-truth
  "must produce TAKEOFF_ESCAPE" cases.
- Geometry and contact information must not become a runtime gate. Runtime escape
  decisions remain neural-only.
- This is a simulator behavioural constraint under current evidence, not a claim that real
  Drosophila never escape from such stimuli.
- **Decision 2: the dual-path family is accepted as the preferred candidate** for the next
  corrective milestone, M1.8-N2: fire immediately when DNp01 >= 2.20, or when DNp01 >= 1.45
  for 3 consecutive samples. 2.20 and 3 samples are Class C decoder parameters chosen to
  separate the observed simulator noise process from sustained threat evidence; they are
  not biological constants.
- **Persistence semantics pinned:** persistence 3 means three consecutive qualifying
  samples including the first threshold-crossing sample (t, t + 20 ms, t + 40 ms), so the
  structural delay is 40 ms. Any larger measured latency is attributed to signal shape or
  threshold-crossing history.
- Decision 3 is moot given decision 1. Decisions 4-8 remain open and are carried into N2.
