# M1.8-N4B3: selective DNp04 threat readout

Status: **research only; complete; decision in section 10.** No runtime, configuration,
calibration, provenance, policy-whitelist, Retina, encoder, MaleCNS, brain-noise,
lifecycle, physics, escape-impulse or recorder change. The accepted M1.8-N4B1C runtime
(`feature/m1-8-n4b1c-runtime`, `e3c55b3`) is the frozen reference and was not modified.

Question: can the N4B2 DNp04 readout be made selective enough to keep its early slow-approach
detection while rejecting the visual expansion the fly generates itself in free flight?

Short answer: **No, not for a flying fly.**

- **No gate built from policy-observable signals rejects self-generated looming without
  also removing the airborne threats DNp04 was meant to catch.**
  - DNp01 coincidence gates remove almost nothing: the same LC4/LPLC2 volley drives both
    cells.
  - MotionState overlaps almost completely between free-flight self-motion events and real
    attacks.
- **The best form that keeps the slow-close detection** is N4B1C OR [DNp04 pair + DNp01
  coincidence + low yaw]. On the new holdout it produces 0.158 free-flight escapes/min
  (upper 0.232), against 0.100 for N4B1C. It keeps only about two thirds of DNp04's
  benefit on real airborne approaches.
- **The only clean gate restricts DNp04 to a stationary fly** (forward speed <= 100 units/s).
  - Free flight: 0 events in 192 min.
  - Fixed-fly N0: 0 events in 1190 min.
  - It speeds up and widens detection for a perched or stationary fly, but does nothing for
    the airborne slow-close case.
- **Classification: outcome 3**, with outcome 2 for in-flight use. The simulator, as
  observed by a policy, lacks the information needed to separate self-generated from
  external looming during flight. DNp04 remains too nonspecific in flight.
- **A second finding concerns the accepted runtime itself:** N4B1C produces 0.083 escapes
  per min in 240 min of no-player free flight (95 % upper 0.121/min). That is not below
  0.1/min at 95 % confidence on this background (section 8). It is reported, not re-tuned.

## 0. Inputs, tools and constraints

Every candidate reads only what a policy could legally observe:

- DNp01 spikes, already in the observation, inferred per side from the trace;
- DNp04 spikes, which would need a whitelist expansion;
- the whitelisted MotionState: `forward_speed`, `lateral_speed`, `yaw_rate`,
  `saccade_remaining`, and the policy's own history of them.

Paddle and mouse coordinates, distance, contact, raw Retina values and LC4/LPLC2 activity
are used offline only, to label events.

Tools (research only):

- `tools/n4b3_record.py`: no-player ROOM free flight under the live N4B1C runtime (detached
  worktree `e3c55b3`), recording the DN panel, the MotionState the policy observed and
  offline geometry; also the fixed-fly N0 holdout;
- `tools/n4b3_criteria.py`: the preregistered family and the frozen list;
- `tools/n4b3_analysis.py`: `dev`, `freeze` and `holdout` modes;
- `tools/n4b3_approach_bouts.py`: externally driven approach bouts in the human sessions
  (descriptive, development data).

N4B2 tools and data are reused unchanged (`tools/n4b2_analysis.py` provides the N4B1C
reference replay and the N0, N1 and human loaders).

Development data (selection only):

- N0, 630 min: original, N4B1 fresh, N4B1C holdout. The fly is fixed, so MotionState is
  exactly zero.
- **ROOM no-player free flight, 72 min, generated for N4B3 before the freeze** (seeds
  7301-7324, MotionState recorded), plus the N4B2 development ROOM runs (seeds 7101-7104,
  12 min; no MotionState, so neural gates only).
- N1 (fixed fly, MotionState zero) and both human sessions (MotionState from the recorded
  `policy_observations.jsonl`), including the episode-5 slow-close case.

The N4B2 holdouts (N0 seeds 310000-340149, ROOM seeds 7201-7212) were not used to design
anything here.

## 1. Preregistered candidate family

Every candidate is the N4B2 DNp04 readout (two same-side DNp04 spikes <= 60 ms apart) plus
one gate evaluated on the sample of the second spike. The runtime event semantics apply:
0.4 s refractory; evidence memory, gating spikes included, cleared on an event. Each form
is also scored as "N4B1C OR candidate".

| Family | Member | Gate |
|---|---|---|
| reference | DNp04 pair (N4B2, ungated) | none |
| A. DNp04 + DNp01 coincidence | A1 | >= 1 ipsilateral DNp01 spike within the 60 ms pair window |
| B. DNp04 accelerates existing DNp01 evidence | B1 | >= 1 ipsilateral DNp01 spike in the preceding 0.5 s |
| | B2 | >= 2 ipsilateral DNp01 spikes in 0.5 s |
| | B3 | >= 2 DNp01 spikes, either side, in 0.5 s |
| C. internal-motion discount | C1 / C2 / C3 | forward_speed <= 50 / 100 / 150 units/s |
| | C4 | abs(yaw_rate) <= 1 rad/s over the last 0.5 s |
| | C5 | no saccade in the last 0.5 s |
| | C6 | planar speed <= 100 units/s |
| combinations | A1+C2 | A1 and C2 |
| | A1+C4 | A1 and C4 (added during development, before the freeze) |

## 2. Development results (all members)

Columns:

- N0: development N0, 630 min;
- ROOM: 72 min of N4B3 free flight, with the 95 % upper bound per min in brackets;
- N4B2 ROOM: the 12-min N4B2 development runs (neural gates only);
- slow-close: first firing with a clean start at tick 610;
- N1: weak / glancing / aborted detected of 60, and strong / medium median latency (s);
- hover / strike-phase: human escapes met, of 33 / 29;
- direct: human direct strikes fired / fired before the click, and the median latency
  after the click (s);
- episode: open-loop firings over 3.7 min of human play.

| Member | N0 | ROOM (95 % upper) | N4B2 ROOM | slow-close | N1 weak / glancing / aborted | N1 strong, medium | hover | strike-phase | direct | episode |
|---|---|---|---|---|---|---|---|---|---|---|
| **N4B1C (frozen runtime)** | 3 | 4 (0.127) | 1 | **668** | 33 / 30 / 49 | 0.08, 0.10 | 33 | 29 | 39/24, 0.10 | 82 |
| DNp04 pair, ungated | 0 | 18 (0.371) | 0 | **613** | 60 / 59 / 60 | 0.06, 0.06 | 32 | 29 | 39/32, 0.06 | 109 |
| A1 coincidence 60 ms | 0 | 16 (0.338) | 0 | 613 | 60 / 58 / 60 | 0.06, 0.06 | 32 | 29 | 39/32, 0.06 | 108 |
| B1 ipsilateral DNp01 in 0.5 s | 0 | 18 (0.371) | 0 | 613 | 60 / 59 / 60 | 0.06, 0.06 | 32 | 29 | 39/32, 0.06 | 109 |
| B2 2 ipsilateral DNp01 in 0.5 s | 0 | 17 (0.354) | 0 | 668 | 60 / 59 / 59 | 0.08, 0.10 | 30 | 28 | 39/27, 0.04 | 98 |
| B3 2 DNp01 in 0.5 s | 0 | 17 (0.354) | 0 | 668 | 60 / 59 / 59 | 0.08, 0.10 | 31 | 29 | 39/28, 0.04 | 101 |
| C1 forward <= 50 | 0 | 0 (0.042) | - | none | 60 / 59 / 60 | 0.06, 0.06 | 1 | 0 | 3/0, 0.20 | 3 |
| C2 forward <= 100 | 0 | **0 (0.042)** | - | **none** | 60 / 59 / 60 | 0.06, 0.06 | 1 | 2 | 6/0, 0.08 | 7 |
| C3 forward <= 150 | 0 | 0 (0.042) | - | none | 60 / 59 / 60 | 0.06, 0.06 | 3 | 2 | 7/2, 0.08 | 11 |
| C4 yaw <= 1 over 0.5 s | 0 | 12 (0.270) | - | 613 | 60 / 59 / 60 | 0.06, 0.06 | 20 | 23 | 29/23, 0.06 | 38 |
| C5 no saccade over 0.5 s | 0 | 13 (0.287) | - | 613 | 60 / 59 / 60 | 0.06, 0.06 | 20 | 24 | 30/24, 0.07 | 48 |
| C6 planar speed <= 100 | 0 | 0 (0.042) | - | none | 60 / 59 / 60 | 0.06, 0.06 | 1 | 0 | 3/0, 0.24 | 4 |
| A1+C2 | 0 | 0 (0.042) | - | none | 60 / 58 / 60 | 0.06, 0.06 | 1 | 2 | 6/0, 0.08 | 7 |
| **A1+C4** | 0 | **11 (0.253)** | - | **613** | 60 / 58 / 60 | 0.06, 0.06 | 20 | 23 | 29/23, 0.06 | 38 |
| N4B1C OR ungated pair | 3 | 19 (0.387) | 1 | 613 | 60 / 59 / 60 | 0.06, 0.06 | 33 | 29 | 39/32, 0.06 | 112 |
| N4B1C OR A1 | 3 | 17 (0.354) | 1 | 613 | 60 / 58 / 60 | 0.06, 0.06 | 33 | 29 | 39/32, 0.06 | 111 |
| N4B1C OR B1 | 3 | 19 (0.387) | 1 | 613 | 60 / 59 / 60 | 0.06, 0.06 | 33 | 29 | 39/32, 0.06 | 112 |
| N4B1C OR B2 / B3 | 3 | 18 (0.371) | 1 | 668 | 60 / 59 / 59 | 0.08, 0.08 | 33 | 29 | 39/30, 0.08 | 105 / 106 |
| N4B1C OR C1 / C2 / C3 / C6 / A1+C2 | 3 | **4 (0.127)** | - | 668 | 60 / 59 / 60 | 0.06, 0.06 | 33 | 29 | 39/24, 0.10 | 82 |
| N4B1C OR C4 | 3 | 13 (0.287) | - | 613 | 60 / 59 / 60 | 0.06, 0.06 | 33 | 29 | 39/29, 0.08 | 89 |
| N4B1C OR C5 | 3 | 14 (0.304) | - | 613 | 60 / 59 / 60 | 0.06, 0.06 | 33 | 29 | 39/29, 0.08 | 91 |
| N4B1C OR A1+C4 | 3 | 12 (0.270) | - | 613 | 60 / 58 / 60 | 0.06, 0.06 | 33 | 29 | 39/29, 0.08 | 89 |

Additional development check: an A1+C4 variant with a stricter yaw bound (0.5 rad/s) gave
9 ROOM events in 72 min (0.125/min), kept the slow-close detection, and met only 18 / 33
hover escapes.

The development result is already decisive in its structure:

- **A and B (DNp01 gates) remove almost nothing.** The same LC4/LPLC2 volley that fires the
  DNp04 pair usually fires ipsilateral DNp01 too. The coincidence is a property of the
  shared input, not a threat signature. Gates strict enough to matter (two DNp01 spikes)
  lose the slow-close detection (668, the N4B1C time).
- **C (motion) splits in two:**
  - Speed gates (C1-C3, C6) remove every free-flight event, but they also remove every
    airborne positive. The fly cruises at about 200 units/s whether or not a threat is
    present. They keep only stationary-fly detections (fixed-fly N1, perched).
  - Yaw and saccade gates (C4, C5) keep the slow-close detection but cut free-flight events
    by only a third. They also lose a third of the human hover and strike positives.
- **No member keeps the slow-close detection AND brings free flight below 0.1/min.** The
  best such member (A1+C4) is at 11 / 72 min.

## 3. Self-motion analysis (development ROOM vs human sessions)

These are every ungated DNp04 pair event in the 72 min of development free flight (18), and
every one in the two human sessions (109). WORLD geometry is used offline only.

| Quantity at the event (median [IQR]) | ROOM free flight, stationary paddle (18) | Human sessions (109) |
|---|---|---|
| forward_speed (units/s) | 201 [193-213] | 218 [193-291] |
| lateral_speed | 0.5 [-7.9-5.0] | -0.6 [-19.5-9.2] |
| yaw_rate (rad/s) | -0.07 [-0.18-0.34] | 0.04 [-0.30-0.32] |
| max abs(yaw_rate) over the last 0.5 s | 0.52 [0.31-6.0] | **10.4** [0.54-16.7] |
| saccade in the last 0.5 s | 6 / 18 | 70 / 109 |
| lifecycle | airborne 18 / 18 | airborne 109 / 109 |
| *offline:* theta (rad) | 0.42 [0.41-0.43] | 0.36 [0.28-0.49] |
| *offline:* theta_dot (rad/s) | **0.12** [0.11-0.15] | **0.47** [0.32-0.69] |
| *offline:* 3D range (units) | 376 [352-419] | 435 [352-573] |
| *offline:* range rate from fly motion (units/s) | -40 [-75 to -2] | +95 [+6 to +143] |
| *offline:* range rate from paddle motion (units/s) | 0 (paddle parked) | **-353** [-857 to -85] |
| *offline:* range closed mainly by | the fly (15 / 18 closing) | the paddle (88 / 109) |

Findings:

- **In free flight the expansion is self-generated by construction.** The paddle is
  stationary. In 15 of 18 events the fly's own flight closes the range. The other 3 are the
  fly moving past the tilted paddle, where foreshortening changes its apparent size
  (`World.visual_half_size`).
- **MotionState does not separate the classes.** Forward, lateral and yaw rates at the event
  overlap almost completely: the fly cruises at the same speed whether or not it is being
  attacked.
- **The one clear motion difference points the wrong way for a self-motion discount.** Real
  attacks come with more recent yaw and saccades (median peak 10.4 against 0.5 rad/s),
  because a chased fly is already maneuvering. A gate that discounts expansion during
  self-motion therefore suppresses real threats preferentially.
- **What does separate them is not observable at runtime:**
  - who is closing the range (world geometry);
  - the strength of the expansion (raw Retina theta_dot, 0.12 against 0.47 rad/s).
- **Even Retina theta_dot would not rescue the slow-close case.** At the DNp04 detection
  (612-613), theta_dot is 0.33 and 0.19 rad/s, inside the free-flight range (up to
  0.41 rad/s).
- **Why MotionState cannot predict self-generated expansion.** Predicting the expansion a
  translating fly generates needs the object's distance and bearing, and MotionState
  carries neither. A per-side DNp04 or DNp01 spike gives at most a left/right bit.

## 4. Externally driven approach bouts (human sessions, development)

These bouts are labelled offline by geometry:

- swatter phase 'approach';
- the paddle's own motion closes the 3D range at >= 100 units/s;
- range < 900 units;
- at least 0.2 s long;
- 62 bouts; median length 22 samples, starting range 611 units, fly forward speed
  236 units/s.

| Criterion | detected of 62 | median first firing (s from bout start) | earlier than N4B1C |
|---|---|---|---|
| N4B1C | 47 | 0.32 | - |
| DNp04 pair, ungated | 53 | 0.20 | 47 |
| A1 | 53 | 0.20 | 47 |
| A1+C4 | 39 | 0.18 | 35 |
| C2 | 3 | 0.64 | 0 |
| N4B1C OR A1 | 53 | 0.20 | 47 |
| N4B1C OR A1+C4 | 51 | 0.22 | 35 |
| N4B1C OR C2 | 47 | 0.32 | 0 |

So DNp04's benefit on real airborne approaches is not limited to the single slow-close
case: it fires about 0.12 s earlier on most externally driven approaches. Every motion gate
that reduces free-flight events also removes most of this benefit.

## 5. Slow-close case: correction of the N4B2 interpretation

Offline geometry for episode 5 (N2b session):

| Tick | 3D range | range rate: paddle / fly (units/s) | theta_dot | fly forward_speed | Event |
|---|---|---|---|---|---|
| 610 | 324 | +59 / +18 | +0.18 | 301 | clean start |
| 611 | 326 | +79 / +17 | +0.40 | 297 | 85-cell volley |
| 612 | 328 | +87 / +16 | +0.33 | 292 | DNp04 L, DNp01 L |
| **613** | 330 | +82 / +15 | +0.19 | 288 | **DNp04 pair: A1 and A1+C4 fire** |
| 623 | 320 | -9 / +9 | -0.11 | 261 | closest horizontal approach |
| 668 | 323 | +11 / +9 | +1.73 | 218 | N4B1C fires |
| 669 | 318 | - | +0.83 | - | click (strike commit) |

- **The paddle is not approaching at 613.** The 3D range grows (324 to 330 units) while the
  paddle hovers at 320 units of height. The positive theta_dot comes from foreshortening as
  the tilted paddle sweeps overhead. The range stays at 320-338 units until the strike at
  669.
- N4B2 stated that DNp04 fires "while the paddle is still approaching". That is corrected
  here and in the N4B2 report: DNp04 fires 1.1 s before N4B1C and before the strike, on
  foreshortening-driven expansion of an overhead hovering paddle.
- The fly is airborne and cruising (288 units/s forward, yaw about -0.2 rad/s, no saccade).
  **A gate that rejects expansion during forward flight must reject this case.** C1-C3 and
  C6 do. The yaw and saccade gates (C4, C5) keep it only because the fly was flying
  straight.

## 6. Biology and interpretation of an internal-motion discount

**A. Published evidence** (primary sources checked for this milestone; section 12):

- **Efference copy exists in fly vision, but for rotational optic flow.** HS and VS lobula
  plate tangential cells receive saccade-related motor signals during flight saccades.
  - The signals are sign-appropriate to cancel expected reafferent yaw responses and start
    before wing motion (Kim, Fitzgerald & Maimon 2015).
  - They are tuned to each cell's yaw sensitivity (Kim et al. 2017).
  - They are present in course-changing but not course-stabilizing turns (Fenk et al. 2021).
- **Looming pathways show no such suppression.** No efference-copy input to LC4, LPLC2,
  the Giant Fiber or any looming DN was found in the literature. In walking flies, the
  loom-preferring lobula columnar glomeruli were not modulated by locomotion (Turner et al.
  2022; group membership extracted by a summarizer).
- **Behavioural state gates some looming DNs.** The landing DNs DNp07 and DNp10 are
  strongly suppressed when the fly is not flying (Ache, Namiki et al. 2019). Giant Fiber,
  LC4 and LPLC2 state dependence was not found.
- **Flies use self-generated expansion rather than discard it.** In free flight,
  expansion from the fly's own forward motion triggers saccades (Tammero & Dickinson
  2002a). Frontal expansion drives landing and lateral expansion drives avoidance
  (Tammero & Dickinson 2002b; van Breugel & Dickinson 2012).
- **No study was found** showing that fly looming neurons distinguish "object approaches
  fly" from "fly approaches stationary object".

**B. Literature-inspired interpretation:**

- A real fly near a stationary object is expected to respond to self-generated expansion,
  with avoidance or landing, not to ignore it. Escape versus avoidance is set by state and
  retinal position, not by the source of the expansion.
- A stationary-fly gate (C2-like) resembles the published state dependence of other
  visual DNs. This is an analogy only, not DNp04 evidence.

**C. Simulator engineering:**

- In this simulator the fly has no efference-copy or reafference pathway into the
  LC4/LPLC2 encoder.
- The policy cannot compute expected self-generated expansion, because MotionState has no
  object range or bearing.
- A stationary-fly gate is principled here for a narrow reason: a fly that is not moving
  cannot generate expansion itself.
- None of the gates tested here is biologically validated, and game behaviour cannot
  validate them.

## 7. Freeze

Frozen before any holdout sample existed:

- `artifacts/m1_8_n4b3/frozen_criteria.json`: sha256
  `1bed08c298f2e277c56a4d5e26251bd828dd723e64247f2cbe2a970a0ac54e82`;
- `tools/n4b3_criteria.py`: sha256
  `14f114c2bfb92785b64e8234bd4151d85839b22003182881161f1737f0dbe046`.

Every holdout file records the freeze hash, and the holdout tools refuse to run if the
criteria module changes.

| Frozen criterion | Why it was carried forward |
|---|---|
| N4B1C (frozen runtime) | reference; replicates its rates on new data |
| DNp04 pair, ungated | N4B2 readout; replication |
| A1 | best neural gate that keeps the slow-close detection |
| A1+C4 | fewest free-flight events of any member that keeps the slow-close detection |
| C2 | the only kind of gate with 0 development free-flight events (stationary fly only) |
| N4B1C OR A1, N4B1C OR A1+C4, N4B1C OR C2 | the corresponding runtime architectures |

Not carried forward:

- B1 is identical to the ungated pair.
- B2 and B3 lose the slow-close detection.
- C1, C3, C6 and A1+C2 are equivalent to C2.
- C4 and C5 alone are dominated by A1+C4.

## 8. Independent holdout (post-freeze)

Holdout data, generated after the freeze and never inspected before this evaluation:

- **Fixed fly, no loom:** 600 trials x 1400 ticks = **280 min**.
  - Seeds 410000-410149, 420000-420149, 430000-430149 and 440000-440149; offsets from
    `default_rng(encoder_seed + 818181 + chunk)`; config `3d41113`.
  - 600 / 600 trials exact against their own policy histories; maximum encoder drive 8.8e-12.
- **No-player ROOM free flight with a parked paddle:** 40 x 9000 ticks = **120 min**.
  - Seeds 7401-7440, under the live N4B1C runtime.
  - The replayed N4B1C matches the runtime's own escape ticks in all 40 runs.
  - Coverage: 26.3 min with the fly slow (forward_speed <= 100), mostly perched (20.7 min)
    or in landing approach (3.9 min).

Bounds are exact one-sided Poisson 95 %.

| Frozen criterion | N0 holdout, 280 min | **ROOM holdout, 120 min: events, /min, 95 % upper** | Holdout combined 400 min: 95 % upper | ROOM development + holdout 192 min: events, /min, upper |
|---|---|---|---|---|
| **N4B1C (frozen runtime)** | 1 (upper 0.0169) | **12, 0.100, 0.162** | 0.0517 | 16, 0.083, 0.127 |
| DNp04 pair, ungated | 0 (0.0107) | 34, 0.283, 0.377 | 0.1132 | 52, 0.271, 0.341 |
| A1 | 0 (0.0107) | 32, 0.267, 0.358 | 0.1075 | 48, 0.250, 0.318 |
| A1+C4 | 0 (0.0107) | 12, 0.100, 0.162 | 0.0486 | 23, 0.120, 0.170 |
| C2 (stationary fly only) | 0 (0.0107) | **0**, 0, 0.025 (armed 26.3 min: 0.114) | 0.0075 | 0, 0, 0.016 (armed 39.3 min: 0.076) |
| N4B1C OR A1 | 1 (0.0169) | 33, 0.275, 0.368 | 0.1132 | 50, 0.260, 0.330 |
| **N4B1C OR A1+C4** | 1 (0.0169) | **19, 0.158, 0.232** | 0.0727 | 31, 0.161, 0.218 |
| **N4B1C OR C2** | 1 (0.0169) | **12, 0.100, 0.162** (identical to N4B1C) | 0.0517 | 16, 0.083, 0.127 |

What the holdout ROOM events are (offline labels):

- Every event is airborne.
- **N4B1C (12):** 8 FAST, 2 LATERAL, 2 SUSTAINED.
  - Theta 0.29-0.55 rad, theta_dot +0.05 to +0.51 rad/s, 3D range 324-501 units.
  - The fly closes the range in 6 of 12. In the others, foreshortening of the tilted paddle
    as the fly flies past produces the expansion.
- **A1+C4 (12):** theta_dot +0.07 to +0.42 rad/s; the fly closes the range in 10 of 12;
  none within 0.5 s of a saccade (by construction).
- **Ungated DNp04 (34):** 27 with the fly closing the range; 22 within 0.5 s of a saccade.
- The development and holdout pictures agree. The ROOM rates of the ungated pair (0.25 and
  0.28/min) and of N4B1C (0.056 and 0.100/min) replicate within their uncertainty.

Against the acceptance target (< 0.1 false escapes/min at about 95 % confidence, free
flight mandatory):

- **Every in-flight DNp04 form fails on free flight.** The best (A1+C4 alone) has a
  95 % upper bound of 0.162/min on the holdout. As an addition to N4B1C it raises
  N4B1C's own rate from 0.100 to 0.158/min.
- **N4B1C OR C2 is identical to N4B1C in free flight.** Its free-flight rate is therefore
  N4B1C's own, whose 95 % upper bound (0.162 on the holdout, 0.121 over all 240 no-player
  minutes) is itself not below 0.1/min.
- **Fixed-fly N0 passes for every criterion.** The upper bounds are 0.011-0.017/min.

## 9. Comparison with N4B1C

Positives are development data (sections 2 and 4); background figures are from section 8.

| Measure | N4B1C | N4B1C OR A1 | N4B1C OR A1+C4 | N4B1C OR C2 |
|---|---|---|---|---|
| **Slow-close (clean start 610)** | 668 | **613** | **613** | 668 |
| N1 strong / medium median latency (s) | 0.08 / 0.10 | 0.06 / 0.06 | 0.06 / 0.06 | 0.06 / 0.06 |
| N1 weak / glancing / aborted detected of 60 | 33 / 30 / 49 | 60 / 58 / 60 | 60 / 58 / 60 | 60 / 59 / 60 |
| Human direct strikes: before click, median after click | 24, 0.10 s | 32, 0.06 s | 29, 0.08 s | 24, 0.10 s |
| Human hover / strike-phase escapes met | 33 / 29 | 33 / 29 | 33 / 29 | 33 / 29 |
| External airborne approach bouts: detected of 62, median, earlier than N4B1C | 47, 0.32 s, - | 53, 0.20 s, 47 | 51, 0.22 s, 35 | 47, 0.32 s, 0 |
| Open-loop firings, 3.7 min of human play | 82 | 111 | 89 | 82 |
| Fixed-fly N0 holdout, 280 min | 1 | 1 | 1 | 1 |
| **Free-flight ROOM holdout, 120 min** | **12 (0.100/min)** | 33 (0.275/min) | **19 (0.158/min)** | **12 (0.100/min)** |

Notes:

- N1 is a fixed-fly protocol with MotionState exactly zero. So C2's N1 gains (strong and
  medium 20-40 ms earlier; weak approaches 60 / 60) are stationary-fly gains. They say
  nothing about flight.
- Direct-strike latency and hover coverage never get worse under any "N4B1C OR" form: the
  first firing is never later than N4B1C's.

## 10. Decision

**Outcome 3: in flight, the simulator as seen by a policy lacks the information to
separate self-generated from external looming reliably. Consequently outcome 2 for
in-flight use: DNp04 remains too nonspecific, even with neural or motion context. Do not
add it for flying flies.**

Evidence:

1. **Neural context does not help.** The DNp01 coincidence (A1) and prior-evidence gates
   (B1) leave 89-100 % of free-flight DNp04 events, because DNp01 and DNp04 share the same
   LC4/LPLC2 volleys. Stricter DNp01 requirements (B2, B3) collapse to the N4B1C timing on
   the slow-close case (668).
2. **Motion context does not separate the classes.** Forward, lateral and yaw rates overlap
   between free-flight self-motion events and real attacks. The one difference, more recent
   yaw and saccades during attacks, points the wrong way. The yaw and saccade gates that keep
   the slow-close detection leave 0.10-0.16 free-flight events/min on the holdout and
   drop about a third of real airborne detections.
3. **The separating information is not policy-observable.** It exists only in world geometry
   (who closes the range) and, partly, in raw Retina expansion strength, which is excluded
   as a runtime gate and would not rescue the slow-close moment anyway (section 3).
   MotionState carries no object range or bearing, so expected self-generated expansion
   cannot be computed. The simulator has no reafference or efference-copy pathway in the
   visual input.
4. **Biology is consistent with this.** Published efference copy in flies addresses
   rotational optic flow in HS/VS cells, not looming pathways. No study was found in which
   fly looming neurons distinguish object approach from self-approach, and flies appear to
   *use* self-generated expansion for saccades and landing (section 6).
5. **The slow-close case is not a closing approach** (section 5). DNp04 detects an overhead
   hovering paddle's foreshortening transient. That transient is the same kind of stimulus
   the fly produces for itself in free flight.

**The narrow exception is a stationary-fly DNp04 path (C2: forward_speed <= 100 units/s).**

- It is principled: a fly that is not moving cannot generate expansion itself.
- It is clean on every background tested:
  - fixed-fly N0: 0 events in 1190 min (all development and holdout sets);
  - free flight: 0 events in 192 min, of which 39.3 min armed (95 % upper 0.076/min armed).
- As "N4B1C OR C2" it leaves the free-flight behaviour exactly N4B1C's.
- It improves stationary / perched detection: committed strikes 20-40 ms earlier, weak N1
  approaches 60 / 60 against 33 / 60.
- **It does not address the reported airborne slow-approach failure.** Its perched-case
  evidence is the fixed-fly N1 protocol; human-session perched threats are too few to
  evaluate here.
- It would still expand the policy whitelist (DNp04 L/R). So it is **promising only as a
  narrow, separately approved milestone**, and it is not a fix for slow approach in flight.

**Additional finding about the accepted runtime (reported, not acted on):**

- N4B1C produces 20 escapes in 240 min of no-player free flight (0.083/min, 95 % upper
  0.121/min). All are airborne, on self-generated expansion near the parked paddle.
- Its acceptance was based on fixed-fly N0, where it passes clearly (upper 0.017/min).
- This is recorded evidence relevant to the free-flight target. Per `AGENTS.md`, N4B1C is
  not retuned here. Whether this counts as a defect needing a future milestone is the
  user's decision.

**Nothing has been implemented.** Options requiring your approval:

- **Keep N4B1C unchanged** (recommended default). The airborne slow-approach limitation
  stays documented as a simulator-information limit.
- **A narrow runtime milestone "N4B1C OR stationary-fly DNp04 pair".** This is a whitelist
  expansion; it improves perched-fly threat detection only.
- **A modelling milestone.** The missing information would have to be added upstream. One
  route is a documented, literature-grounded change to how the Retina/encoder represents
  self-motion. That touches the Retina/encoder and needs explicit approval. A second is to
  accept free-flight self-motion escapes as avoidance behaviour and count them against a
  different target.
- **A research-only characterization of N4B1C's own free-flight escapes** (for example
  whether they look like plausible avoidance or like false alarms in human play).

## 11. Reproduction and validation

    .venv\Scripts\python.exe tools\n4b3_record.py room --set dev --seed 7301            (7301-7324, before the freeze)
    .venv\Scripts\python.exe tools\n4b3_analysis.py dev
    .venv\Scripts\python.exe tools\n4b3_approach_bouts.py
    .venv\Scripts\python.exe tools\n4b3_analysis.py freeze
    .venv\Scripts\python.exe tools\n4b3_record.py n0 --chunk 0                          (chunks 0-3, NUMBA_NUM_THREADS=2)
    .venv\Scripts\python.exe tools\n4b3_record.py room --set holdout --seed 7401        (7401-7440)
    .venv\Scripts\python.exe tools\n4b3_analysis.py holdout

The ROOM runs need the detached runtime worktree
(`git worktree add --detach artifacts/worktrees/n4b1c-runtime-detached e3c55b3...` plus a
`data` junction). The N4B3 ROOM runs used `NUMBA_NUM_THREADS=1`, and N0 chunks used 2.

Artifacts (`artifacts/m1_8_n4b3/`, git-ignored; sha256 prefixes):

| File | sha256 |
|---|---|
| `dev.json` | `62dbae843311c8a8` |
| `frozen_criteria.json` | `1bed08c298f2e277` |
| `holdout.json` | `53218663a664565d` |
| `approach_bouts.json` | `9bc00b52272fab8e` |
| `n0_holdout_chunk0..3.npz` | `1b21a7c98f1cbbdb`, `6749a3e0dc6e3486`, `f46464a86b345e03`, `ef7035b8afddc8aa` |
| `room_dev_seed7301..7324.npz` (concatenated in seed order) | `a1084d4e0d08b42e` |
| `room_holdout_seed7401..7440.npz` (concatenated in seed order) | `e4831c14abe76eca` |

Validation on the research branch:

- 330 / 330 tests pass.
- The 20 protected files match `artifacts/m1-2/protected-before.json` and none differs from
  `76806f0`.
- `verify_results.py` passes (frozen weights verified).
- No runtime file (`game/action.py`, `session.py`, `world.py`, `perception.py`, `fly.py`,
  `game_room_config.json`, `results/`) differs from `5be0aea`.
- `feature/m1-8-n4b1c-runtime` is still at `e3c55b3`, and both runtime worktrees are clean.
- The criteria module hash is unchanged since the freeze (`14f114c2...`).

Multiple-comparison and scope caveats:

- 14 gated members x 2 architectures were compared on development data, and all are
  reported in section 2. Six criteria were frozen.
- Free-flight backgrounds use a parked paddle only. The positives come from one tester and
  two human sessions, one slow-close episode, and scripted fixed-fly N1.
- The approach-bout labels use offline geometry, and the human analyses are open loop.
- A1+C4 was added to the family during development, before the freeze.

## 12. Bibliography (added for N4B3; N4B2 sources in its report)

- Kim AJ, Fitzgerald JK, Maimon G (2015). Cellular evidence for efference copy in
  *Drosophila* visuomotor processing. *Nat Neurosci* 18:1247-1255. doi:10.1038/nn.4083
- Kim AJ, Fenk LM, Lyu C, Maimon G (2017). Quantitative predictions orchestrate visual
  signaling in *Drosophila*. *Cell* 168:280-294. doi:10.1016/j.cell.2016.12.005
- Fenk LM, Kim AJ, Maimon G (2021). Suppression of motion vision during course-changing, but
  not course-stabilizing, navigational turns. *Curr Biol* 31:4608-4619.
  doi:10.1016/j.cub.2021.09.068 (abstract checked)
- Fischer PJ, Schnell B (2022). Multiple mechanisms mediate the suppression of motion vision
  during escape maneuvers in flying *Drosophila*. *iScience* 25:105143.
  doi:10.1016/j.isci.2022.105143
- Turner MH, Krieger A, Pang MM, Clandinin TR (2022). Visual and motor signatures of
  locomotion dynamically shape a population code for feature detection in *Drosophila*.
  *eLife* 11:e82587
- Ache JM, Namiki S, Lee A, Branson K, Card GM (2019). State-dependent decoupling of sensory
  and motor circuits underlies behavioral flexibility in *Drosophila*. *Nat Neurosci*
  22:1132-1139. doi:10.1038/s41593-019-0413-4
- Tammero LF, Dickinson MH (2002a). The influence of visual landscape on the free flight
  behavior of the fruit fly *Drosophila melanogaster*. *J Exp Biol* 205:327-343
  (abstract checked)
- Tammero LF, Dickinson MH (2002b). Collision-avoidance and landing responses are mediated by
  separate pathways in the fruit fly. *J Exp Biol* 205:2785-2798 (abstract checked)
- van Breugel F, Dickinson MH (2012). The visual control of landing and obstacle avoidance in
  the fruit fly. *J Exp Biol* 215:1783-1798 (abstract checked)
- Klapoetke NC, et al. (2017). Ultra-selective looming detection from radial motion opponency.
  *Nature* 551:237-241. doi:10.1038/nature24626
