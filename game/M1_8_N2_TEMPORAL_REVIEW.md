# M1.8-N2: SUSTAINED temporal-rule review

Status: **research only. Runtime, configuration and the N2 provenance record are unchanged
(FAST 2.20, strict 1.45 x 3). Nothing is committed.**

Tool: `tools/n2_temporal_study.py`. Output: `artifacts/m1_8_n2/temporal_study.json` (log
`temporal_study.log`). Fixed for the principal comparison: FAST 2.10, low threshold 1.45.
Inputs are the exact recorded MotorState streams of N0 (210,000 ticks), N1 (300 trials) and
the human session `results/game/sessions/20260923T005351.731330Z-38255ec8`. The decoder is
neural-only throughout; world data are used only to interpret the human perched interval.

## 1. Headline

1. **The N0 data strongly support a gap-tolerant rule.** In 70 simulated minutes no
   spontaneous cluster ever put more than **2** qualifying samples into any 3-, 4- or
   5-sample window; every cluster was `H` (57) or `HH` (34). 3-of-4 and 3-of-5 keep 0 false
   escapes. 2-of-3 restores the defect: 34 events, 0.49/min, all `LLLHH`.
2. **A gap-tolerant rule does not improve N1 medium-committed latency** (median 0.14 s
   under every rule, legacy 0.08 s). FAST 2.10 already fires two samples after the first
   qualifying sample in most medium trials, sooner than any 3-sample window can.
3. **On the human attacks it helps, but not to legacy.** Mean latency from the click:
   strict 0.124 s, 3-of-4 0.118 s, 3-of-5 (current qualifies) 0.112 s, 3-of-5 0.101 s,
   legacy 0.076 s. Any rule that needs three qualifying samples has a structural floor two
   samples (40 ms) after the first qualifying sample, which legacy does not pay.
4. Gap tolerance also raises non-contact firing and pre-click escapes (sections 4 and 6).

## 2. Exact rule semantics (as implemented in the study tool)

- **Qualifying sample:** summed DNp01 trace >= 1.45.
- **Window:** the qualifying flags of the most recent n samples **including the current
  one**. One flag is appended on **every** sample, refractory samples included, which
  matches how the runtime strict streak counts during refractory.
- **Firing:** only when not refractory; FAST (total >= 2.10) wins ties; SUSTAINED when the
  window holds >= k flags. The `*` variants additionally require the current sample to
  qualify.
- **After an escape:** the window is cleared.
- **Stale evidence:** the window never holds more than n samples. After the 20-sample
  refractory period it can hold only flags from the last n samples (at most 80 ms) and
  never evidence from before the escape.
- **Consequence for 3-of-5 without `*`:** evidence collected in the last samples of the
  refractory period can fire on the first eligible sample even when that sample itself is
  below 1.45 (for example `HHHLL` at expiry). That fires on evidence 20-80 ms old after
  the signal has already dropped, which is exactly the stale post-refractory case to avoid.
  It happened once in N1 and in two human strikes. The `*` variant excludes it. For 3-of-4
  the variant changes nothing in any dataset.
- **Harness check:** the 3-of-3 window reproduces the runtime strict-3 decoder exactly on
  N0, N1 and the human session (all three checks true). Motor semantics (strength, side,
  steering, saccade, alert, refractory) are the unchanged runtime code via subclassing.

## 3. N0 false triggers (exact replay, 70.0 min)

| Rule (FAST 2.10 unless noted) | FAST | SUSTAINED | Total | Events/min | 95% one-sided upper bound | Patterns causing false events |
| --- | --- | --- | --- | --- | --- | --- |
| legacy single-sample | - | - | 91 | 1.300 | 1.547 | `LLLLH` (all 91) |
| strict-3, FAST 2.20 (current N2) | 0 | 0 | 0 | 0 | 0.043 | - |
| A strict-3 | 0 | 0 | 0 | 0 | 0.043 | - |
| B 3-of-4 (= B*) | 0 | 0 | 0 | 0 | 0.043 | - |
| C 3-of-5 (= C*) | 0 | 0 | 0 | 0 | 0.043 | - |
| **D 2-of-3 (negative control)** | 0 | **34** | **34** | **0.486** | 0.647 | **`LLLHH` (all 34): the documented two-spike coincidence** |

- **D is rejected.** A, B and C pass < 0.1/min at ~95% confidence on observed data.
- B still rejects the two-sample coincidence: the worst N0 window is `HH`, 2 of 4.
- A rough independent-cluster estimate, not demonstrated, uses the observed cluster rate
  (91 clusters in 70 min) and asks how often an `HH` cluster has another cluster within
  the window. It gives about 0.001/min for 3-of-4 and 0.001-0.003/min for 3-of-5. It
  ignores any correlation between spike clusters. < 0.01/min is not demonstrated for any
  rule.

## 4. N1 exact replay (300 trials)

Latency is from the click (committed) or from expansion onset (others). Counts are of 60.

| Rule | strong fired (F/S) | strong median / p95 | medium fired (F/S) | medium median / p95 | weak (F/S) | glancing (F/S) | aborted (F/S) |
| --- | --- | --- | --- | --- | --- | --- | --- |
| legacy | 60 | 0.08 / 0.08 | 60 | **0.08 / 0.10** | 55 | 51 | 58 |
| strict-3, FAST 2.20 (current) | 60 (60/0) | 0.10 / 0.16 | 60 (60/0) | **0.16 / 0.18** | 16 (13/3) | 9 (6/3) | 19 (18/1) |
| A strict-3 | 60 (60/0) | 0.10 / 0.12 | 60 (60/0) | 0.14 / 0.18 | 20 (20/0) | 13 (13/0) | 22 (22/0) |
| B 3-of-4 | 60 (60/0) | 0.10 / 0.12 | 60 (57/3) | 0.14 / 0.18 | 21 (18/3) | 16 (12/4) | 29 (20/9) |
| C* 3-of-5, current qualifies | 60 (60/0) | 0.10 / 0.12 | 60 (55/5) | 0.14 / 0.18 | 29 (16/13) | 27 (11/16) | 44 (18/26) |
| D 2-of-3 | 60 (55/5) | 0.10 / 0.12 | 60 (51/9) | 0.14 / 0.18 | 40 (15/25) | 29 (10/19) | 47 (13/34) |

(C without `*` is identical to C* in all N1 counts and latencies.) The N0 150-trial loom arm
is 150/150 for every rule; p95 is 0.151 s for A and 0.14 s for B and C.

**Key question: does 3-of-4 restore medium latency without restoring N0 false escapes?**
It keeps N0 at zero, but **it does not restore medium latency**: 0.14 s against 0.08 s for
legacy and 0.16 s for the current N2. The improvement over current N2 comes entirely from
FAST 2.10.

Samples from the first qualifying in-window sample to firing, medium committed:

| Rule | +0 | +1 | +2 | +3 | +4 | +5 |
| --- | --- | --- | --- | --- | --- | --- |
| legacy | 59 | | | 1 | | |
| strict-3, FAST 2.20 | | 4 | 2 | 23 | 28 | 3 |
| A strict-3 | | 4 | 36 | 3 | 14 | 3 |
| B 3-of-4 | | 4 | 36 | 6 | 12 | 2 |
| C* 3-of-5 | | 4 | 36 | 6 | 14 | |

## 5. Temporal H/L patterns (H = total >= 1.45)

**N0 no-loom clusters** (qualifying samples joined when separated by at most 3 samples):
`H` 57 and `HH` 34. **No** `HLH`, `HLLH`, `HHH` or longer pattern occurred. The maximum
qualifying count in any window of 3, 4 or 5 samples was 2.

**Medium committed**, first 4 samples from the first qualifying sample: `HLHH` 37,
`HLLH` 15, `HHHH` 6, `HHLH` 2. First 6: `HLHHHH` 37, `HLLHHH` 15, `HHHHHH` 6, `HHLHHH` 2.

**Strong direct**, first 4: `HHHH` 35, `HLHH` 25.

**Human strikes**, first 6 after the first post-click qualifying sample (31 strikes):
`HHHHHH` 12, `HLHHHH` 6, `HLLHHH` 6, `HHLLHH` 2, and one each of `HHLHHH`, `HLHHLH`,
`HLLHHL`, `HLLLL` and `HLLLLL`. Click to first qualifying sample: median 0.06 s.

**Interpretation.**
- Legitimate loom reaches three qualifying samples within five samples in 60/60 committed
  trials of each class, usually with exactly one or two single-sample dips.
- Spontaneous no-loom activity never did, even once in 70 minutes: it produces one or two
  adjacent qualifying samples at most.

That is a genuine, measured separation and the engineering justification for gap tolerance.
It does not translate into lower medium latency in N1, because in the dominant `HLHH`
pattern the second `H` is the 2.1197 FAST level, so FAST 2.10 fires at +2 before any
3-sample window can.

## 6. Human-session counterfactual

Per strike, the recorded policy's complete state is copied at the click. The window is
rebuilt from the recorded neural stream since the recorded policy's last escape, and only
the criterion changes. Each first firing time is exact. Pre-click hover segments and
perched intervals are synced the same way. 31 strikes.

| Rule | Fired | FAST / SUSTAINED | Median | Mean | p95 | Earlier than current N2 | Pre-click segments with an escape | Far perched approach (peak 2.0557) |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| legacy | 26 | - | 0.08 | **0.076** | 0.185 | 24 | 27 | fires at 49.92 s (single-sample) |
| strict-3, FAST 2.20 (recorded) | 24 | 22 / 2 | 0.14 | 0.129 | 0.18 | - | 12 | no |
| A strict-3 | 24 | 24 / 0 | 0.14 | 0.124 | 0.18 | 4 | 14 | no |
| B 3-of-4 (= B*) | 24 | 20 / 4 | 0.13 | 0.118 | 0.18 | 8 | 18 | no |
| **C* 3-of-5, current qualifies** | 24 | 16 / 8 | **0.12** | **0.112** | 0.16 | 12 | 20 | **no** |
| C 3-of-5 | 24 | 14 / 10 | 0.11 | 0.101 | 0.16 | 14 | 20 | no |
| D 2-of-3 | 24 | 7 / 17 | 0.10 | 0.092 | 0.16 | 21 | 24 | **fires SUSTAINED at 50.28 s (`LLLHH`) - flagged** |

- No gap-tolerant rule fires in a strike where the current N2 does not.
- The far, non-contact perched approach (swatter about 1805 units away) triggers only
  legacy and D. **B, C and C\* do not create a new SUSTAINED escape there.**
- Gap tolerance increases pre-click escapes during human hover approaches (14 -> 18 for B,
  20 for C/C\*). This is the human-play counterpart of the higher non-contact firing in N1.

## 7. Comparison and recommendation

| | A strict-3 | B 3-of-4 | C* 3-of-5 (current qualifies) | D 2-of-3 |
| --- | --- | --- | --- | --- |
| N0 < 0.1/min | pass (0) | pass (0) | pass (0) | **fail (0.49/min)** |
| Rejects the two-spike `HH` coincidence | yes | yes | yes | no |
| N1 medium median / p95 | 0.14 / 0.18 | 0.14 / 0.18 | 0.14 / 0.18 | 0.14 / 0.18 |
| Human mean latency (legacy 0.076) | 0.124 | 0.118 | 0.112 | 0.092 |
| Human far perched approach | no fire | no fire | no fire | **fires** |
| Non-contact N1 firing (weak / glancing / aborted) | 20 / 13 / 22 | 21 / 16 / 29 | 29 / 27 / 44 | 40 / 29 / 47 |
| Human pre-click escapes | 14 | 18 | 20 | 24 |

**Recommendation, conditional:**
- **3-of-4** is safe on every test but gives almost nothing: 6 ms mean on human attacks,
  0 in N1 medium. It does not address the reported failure.
- **3-of-5 with "current sample qualifies" (C\*)** is the only tested rule that
  - passes N0 with a structural margin (the no-loom maximum is 2 of 5),
  - avoids stale post-refractory firing,
  - leaves the far perched approach alone, and
  - materially shortens human attack latency: mean -12 ms against strict-3 at 2.10 and
    -17 ms against the recorded N2; median 0.14 -> 0.12 s.

  Its cost is roughly doubled non-contact firing in N1 and more pre-click hover escapes.
- **Plain 3-of-5** is 11 ms faster on human attacks than C\*, but only by firing on
  sub-threshold samples at refractory expiry, which the stale-evidence requirement excludes.
- **2-of-3 is rejected.**

No rule tested closes the gap to legacy. Requiring three qualifying samples costs at least
two samples (40 ms) after the first qualifying sample, and the observed human remainder is
36 ms for C\*. If that remainder is itself perceptible, no neural-only 3-sample SUSTAINED
rule will pass the human test. Faster response would then have to come from the FAST path,
and FAST < 2.05 fails N0.

## 8. Uncertainty and limitations

- N0 zeros are observed zero counts over 70 minutes (bound 0.043/min). The independent-
  cluster estimates are rough and assume no correlation between clusters.
- One human session, one tester, 31 strikes. The synced counterfactual gives exact first
  decisions but not downstream outcomes. Only one far perched approach was recorded.
- N1 classes are scripted fixed-fly probes. Human strikes on a moving fly rise more slowly
  and with more dips (`HLLH…` 7/31) than N1 medium (`HLHH…` 37/60), which is why the rules
  separate on human data and not on N1.
- The rise to the first qualifying sample (median 0.06 s after the click in the human
  session) is outside the decoder and is shared by all rules including legacy.
- Only FAST 2.10 was studied for the gap-tolerant rules.
- The N1 non-contact classes and human pre-click escapes are not must-escape cases; their
  increase is a behavioural cost, not a failure.

## 9. Is another human re-test justified?

**Only for C\* (3-of-5, current sample qualifies, FAST 2.10), and only with the expectation
stated plainly.** It is predicted to shorten felt attack latency by about 12-17 ms (mean)
from the failed configuration, leaving about 36 ms above legacy, and to add some hover-
approach escapes.

If the recorded 0.129 s felt clearly sluggish against 0.076 s, a gain of about 17 ms may
not be enough; that is a human judgement this study cannot make. Implementing C\* would
require a new decoder kind, a new provenance record, new unit tests for the window and
refractory semantics above, and a full N0/N1/closed-loop re-validation before any re-test.
None of that has been done.
