# M1.8-N2: FAST-threshold sensitivity review

Status: **research only. Runtime, configuration and the N2 record are unchanged
(FAST 2.20, 1.45 x 3). Nothing is committed.** The human re-acceptance of N2 failed on
subjective escape latency; this note measures whether lowering FAST can fix that.

Tool: `tools/n2_fast_threshold_study.py`. Output: `artifacts/m1_8_n2/fast_threshold_study.json`.
Every candidate is the exact runtime ROOM policy from `build_policy`, with only
`fast_threshold` overridden in memory. `sustained_threshold = 1.45` and
`persistence_samples = 3` are fixed. Persistence 2 was not tested: it would restore the
documented two-spike N0 failure.

## 1. Headline

**Lowering FAST within the range the false-trigger target allows does not remove the
latency the human noticed.**

- On the recorded human attacks, legacy fires at a median of **0.08 s** after the click and
  N2 2.20 at **0.14 s** (paired mean +64 ms).
- FAST 2.10 recovers only **5 ms** of that (median still 0.14 s).
- In N1, medium committed improves from 0.16 s to only 0.14 s (legacy 0.08 s).

The remaining latency comes from the sustained path being unable to form a streak on the
sawtooth rising edge, not from the FAST level. FAST cannot go below 2.05 without failing N0.

## 2. N0 false triggers (exact runtime replay, 70.0 min, 210,000 ticks)

No-loom maximum DNp01: **2.0045**.

| FAST | FAST events | SUSTAINED events | Total | Observed/min | 95% one-sided upper bound | No-loom samples >= FAST | Tail-model FAST-path estimate |
| --- | --- | --- | --- | --- | --- | --- | --- |
| legacy (1.45 x 1) | - | - | 91 | 1.300 | 1.547 | - | - |
| 2.00 | 17 | 0 | 17 | 0.243 | 0.364 | 17 | 0.245/min |
| 2.05 | 0 | 0 | 0 | 0 | 0.043 | 0 | 0.033/min (model) |
| 2.08 | 0 | 0 | 0 | 0 | 0.043 | 0 | not on model grid |
| 2.10 | 0 | 0 | 0 | 0 | 0.043 | 0 | 0.023/min (model) |
| 2.12 | 0 | 0 | 0 | 0 | 0.043 | 0 | not on model grid |
| 2.15 | 0 | 0 | 0 | 0 | 0.043 | 0 | not on model grid |
| 2.20 | 0 | 0 | 0 | 0 | 0.043 | 0 | 0.017/min (model) |

- **2.00 is rejected** (the two-spike coincidence at level 2.000).
- **Every candidate from 2.05 upward meets < 0.1/min at ~95% confidence** on observed data.
- All zeros are observed zero counts. The model column is the N0 mechanistic tail model
  (two spikes landing on residual trace), a model estimate, not an observation.
- < 0.01/min is not demonstrated for any candidate.

## 3. N1 exact runtime replay (300 trials)

Latency is from the click for committed classes and from expansion onset for the others.
There were no SUSTAINED firings in the committed classes for any candidate.

| FAST | strong fired (FAST) | strong median / p95 | medium fired (FAST) | medium median / p95 | weak | glancing | aborted |
| --- | --- | --- | --- | --- | --- | --- | --- |
| legacy | 60 | 0.08 / 0.08 | 60 | **0.08** / 0.10 | 55 | 51 | 58 |
| 2.05 | 60 (60) | 0.10 / **0.12** | 60 (60) | **0.14** / 0.18 | 26 | 15 | 23 |
| 2.08 | 60 (60) | 0.10 / 0.12 | 60 (60) | 0.14 / 0.18 | 21 | 14 | 23 |
| 2.10 | 60 (60) | 0.10 / 0.12 | 60 (60) | 0.14 / 0.18 | 20 | 13 | 22 |
| 2.12 | 60 (60) | 0.10 / 0.16 | 60 (60) | 0.16 / 0.18 | 16 | 11 | 20 |
| 2.15 | 60 (60) | 0.10 / 0.16 | 60 (60) | 0.16 / 0.18 | 16 | 9 | 20 |
| 2.20 (current) | 60 (60) | 0.10 / 0.16 | 60 (60) | **0.16** / 0.18 | 16 (13 F, 3 S) | 9 (6 F, 3 S) | 19 (18 F, 1 S) |

**Medium committed**, 2.10 against the references:

| Reference | Median change | p95 change |
| --- | --- | --- |
| vs current 2.20 | 0.16 -> 0.14 s (**-20 ms**) | 0.18 -> 0.18 s (0) |
| vs legacy | 0.08 -> 0.14 s (still **+60 ms**) | 0.10 -> 0.18 s (still +80 ms) |

**Strong committed**, 2.10: the median is unchanged at 0.10 s (legacy 0.08 s); p95
improves from 0.16 to 0.12 s. The N0 150-trial loom arm is 150/150 FAST for every
candidate; p95 is 0.151 s at 2.05-2.10 against 0.16 s at >= 2.12.

### 3.1 The 2.10 hypothesis: confirmed, and a discrete level

The early sawtooth peaks are not spread out. In strong and medium committed trials, 39 of
the in-window samples before the 2.20 crossing sit in a tight cluster at **2.1197** (range
2.11965-2.12040; 33 of them below 2.1200). That is consistent with a quantised three-spike
configuration: 1 + e^(-dt/tau) + e^(-6dt/tau) = 2.1199 for spikes at t, t-1 and t-6 ticks.
So the transition is a step:

- FAST <= 2.11965 catches the whole cluster (medium median 0.14 s);
- FAST 2.12 catches only its top 6 samples (medium median 0.16 s).

The only other early peaks in [2.0, 2.2) lie at 2.0000-2.0754 (8 samples) and above 2.12
(sparse). Therefore **every FAST value in (2.0754, 2.1196] gives identical committed-class
results**; 2.08, 2.10 and 2.11 cannot be told apart on N1 committed data.

## 4. Human-session counterfactual replay

Session `results/game/sessions/20260923T005351.731330Z-38255ec8`, recorded under N2 2.20
(dirty tree on `76806f0`): 9 episodes, 9387 ticks, 31 strikes, 2 perched intervals.

**Harness check:** the recorded 2.20 decoder, fed the recorded MotorState stream,
reproduces **all 7025 recorded brain-stepped actions exactly (0 mismatches)**.

### 4.1 Perched intervals

| Perch | Peak DNp01 | Swatter centre distance at peak | Longest run >= 1.45 | 2.00 | 2.05 | 2.08 | 2.10 | 2.12-2.20 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| ep 1, 2.5-18.3 s | 1.027 | 2962 | 0 | - | - | - | - | - |
| **ep 1, 38.0-52.5 s** | **2.0557 at 50.26 s** | **1805** (approach phase) | **2** | **FAST at 50.26 s** | **FAST at 50.26 s** | - | - | - |

The second perched approach is **not a must-escape case**: the swatter was far and not
striking. It is a useful discriminator:
- FAST 2.05 (and 2.00) would launch the perched fly as a FAST escape at 50.26 s;
- FAST >= 2.08 would not, because the peak is 0.024 below 2.08 and 0.044 below 2.10.

The recorded perch ended with a voluntary takeoff (local history motivation).

### 4.2 Strikes (synced counterfactual)

At each click, the recorded policy's complete internal state (refractory, streak, side and
steering memory) is copied and only the criterion is changed. Until the candidate's first
differing decision, the recorded neural stream is exactly what it would have received, so
each first firing time is exact. Pre-click hover segments are treated the same way, synced
at the previous resolution. Five strikes began while the recorded policy was refractory
from a pre-click escape, and no candidate fires in those.

| Criterion | Strikes fired | FAST / SUSTAINED | Median | p95 | Mean | Strikes earlier than 2.20 | Pre-click segments with an escape |
| --- | --- | --- | --- | --- | --- | --- | --- |
| legacy (1.45 x 1) | 26/31 | - | **0.08 s** | 0.185 s | 0.076 s | - | 27 |
| 2.00 | 24/31 | 24 / 0 | 0.13 s | 0.18 s | - | 8 | 18 |
| 2.05 | 24/31 | 24 / 0 | 0.14 s | 0.18 s | 0.123 s | 5 | 17 |
| 2.08 | 24/31 | 24 / 0 | 0.14 s | 0.18 s | - | 4 | 15 |
| 2.10 | 24/31 | 24 / 0 | 0.14 s | 0.18 s | 0.124 s | 4 | 14 |
| 2.12 | 24/31 | 24 / 0 | 0.14 s | 0.18 s | - | 3 | 13 |
| 2.15 | 24/31 | 24 / 0 | 0.14 s | 0.18 s | - | 3 | 12 |
| **2.20 (recorded)** | 24/31 | 22 / 2 | **0.14 s** | 0.18 s | 0.129 s | - | 12 |

- Strikes that switch channel or timing at 2.10: the two SUSTAINED firings under 2.20
  (74.12 s and 77.92 s) become FAST at the same latency (0.10 s).
- Four strikes fire earlier: 71.94 s (0.16 -> 0.14), 95.56 s (0.14 -> 0.10), 108.64 s
  (0.16 -> 0.14) and 183.30 s (0.08 -> 0.04).
- Paired over the 24 strikes where legacy, 2.20 and 2.10 all fire: mean latency 0.065 /
  0.129 / 0.124 s.

Lower FAST also means more pre-click escapes during hover approaches: 12 segments at 2.20,
14 at 2.10, 17 at 2.05 and 27 under legacy. That is the weak-approach trade-off again, now
in human play.

## 5. Comparison of 2.05 / 2.10 / 2.15 / 2.20

| | 2.05 | 2.10 | 2.15 | 2.20 |
| --- | --- | --- | --- | --- |
| N0 < 0.1/min (observed) | pass | pass | pass | pass |
| N0 margin above the no-loom maximum 2.0045 | 0.046 | 0.096 | 0.146 | 0.196 |
| Tail-model FAST-path rate | 0.033/min | 0.023/min | - | 0.017/min |
| strong median / p95 | 0.10 / 0.12 | 0.10 / 0.12 | 0.10 / 0.16 | 0.10 / 0.16 |
| medium median / p95 | 0.14 / 0.18 | 0.14 / 0.18 | 0.16 / 0.18 | 0.16 / 0.18 |
| Catches the 2.1197 early-peak level | yes | yes (margin 0.020) | no | no |
| Human far perched approach (2.0557) | **fires FAST** | no (margin 0.044) | no | no |
| Human attacks, median / mean | 0.14 / 0.123 | 0.14 / 0.124 | 0.14 | 0.14 / 0.129 |

## 6. Recommendation

**If a FAST change is made, 2.10 is the value the evidence supports**, with 2.08-2.11
equivalent on all recorded committed data.

- **2.05** has the same attack latency as 2.10 but classifies the far, non-contact human
  perched approach as a FAST escape. By the selection rule, prefer the slightly higher value.
- **2.10** is the lowest round value that passes N0, keeps 60/60 committed firing, catches
  the 2.1197 level, and does not fire on the human perched approach. Strictly, the "lowest
  threshold" rule would pick about 2.08, but 2.08 and 2.10 are indistinguishable in N0, N1
  and the human session. 2.10 leaves more margin above the only human non-contact peak
  (0.044 against 0.024) and keeps 0.020 margin below the 2.1197 level.
- **2.12 and above** gain nothing over 2.20 on committed latency.

**This change is not expected to pass the failed human re-acceptance on its own.** It
improves medium committed latency by 20 ms (N1) and human attacks by about 5 ms on
average, against a 60-64 ms gap to legacy. Within the admissible range the FAST threshold
is not the dominant cause of the sluggishness. The dominant cause is that the sustained
path almost never completes on the sawtooth rising edge (54/60 medium trials break the
streak), so nearly every committed response waits for FAST.

Addressing that would change the sustained criterion itself (for example, how a
single-sample dip is treated). That is outside this study's authorised scope, was not
tested, and would need its own N0 analysis against the two-spike failure mechanism.

## 7. Uncertainty

- N0 zeros for 2.05-2.20 are observed zero counts over 70 min (bound 0.043/min). Model
  rates are model estimates.
- The 2.1197 level is exact in the recorded data. That it is a three-spike configuration is
  an inference from the decay constant.
- The human session is one session from one tester, 31 strikes. The synced counterfactual
  is exact for each first decision but does not predict the downstream trajectory (dodges,
  hits) after a counterfactual escape.
- Only one human non-contact perched approach was recorded; its 2.0557 peak is a single
  sample. Other far approaches may peak anywhere in 2.0-2.1.
- The human latency judgement concerns felt responsiveness. Click-to-decision latency is
  one component; takeoff kinematics were not changed and were not analysed here.

## 8. What would need another human re-test

- Any change of FAST (for example to 2.10) requires a new N2 record, the calibration and
  provenance tests updated, and a narrow human re-test of attack responsiveness. Based on
  this study, that re-test is likely to still report sluggishness.
- A change to the sustained criterion, if authorised, would need N0/N1/closed-loop
  validation first and then a human re-test.
- Perched behaviour at 2.10 is predicted unchanged for far approaches like the recorded
  one; a re-test should include one deliberate far and one near perched approach.
