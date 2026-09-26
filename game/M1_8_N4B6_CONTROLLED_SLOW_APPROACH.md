# M1.8-N4B6: controlled slow-approach characterization

Status: **research only; complete.** No runtime code, configuration, decoder, whitelist,
Retina / encoder equation, MaleCNS parameter, brain noise, physics, lifecycle or recorder
schema was changed. The accepted runtime (M1.8-N4B5R, `feature/m1-8-n4b5r-geometry` @
`363a1a9`: G3 geometry plus the unchanged N4B1C decoder) was imported read-only from its
worktree, which stayed clean at that commit.

## Short answer

**Yes. Under the accepted G3 + N4B1C system there is a reproducible slow-approach blind
spot under controlled, monotonic approach.** The previous complaint was not only the old
geometry.

- A hover-height approach at the human 25th-percentile closing speed (130 units/s, 900 to
  about 190 units) is detected in time in **0-6 % of 48 brain-noise seeds**. This holds
  frontally, obliquely on either side and laterally to 90 units.
- At the human median speed (300 units/s) detection is **marginal (29 %)**.
- At the human 75th percentile (800 units/s) it is **reliable (100 %, 0.36 s before
  closest approach)**.
- The stationary and receding controls are clean: **0 N4B1C responses in 14.7 stimulus
  minutes**, and 0 in 24 min of stationary pre-hold.

**The preregistered decision rule returns "mixed":**

| Speed | Attribution | Outcome |
|---|---|---|
| 130 units/s (A2, C1, C2, C3) | The encoder exceeds its N0 envelope at least 0.25 s before closest approach in 100 % of seeds, but N4B1C does not fire | **Outcome 2, REAL DNp01 SENSITIVITY LIMIT** |
| 50 units/s (A1, about human p10) | Encoder evidence appears in time in only 38 % of seeds | **Outcome 3, STIMULUS / RETINA LIMIT** |

Mechanism (exploratory supplement):

- The hover-height geometry itself limits the stimulus. A slow approach reaches at most
  0.087 rad/s of expansion, so the encoder's LPLC2 / LC4 response is weak and sporadic.
- The DNp01 cell does respond. In the 1 s before the response margin it fires 4 spikes
  (median) on the driven side, against a mean of 0.34 at baseline.
- **N4B1C's short coincidence windows (<= 60 ms, trace >= 2.1) do not see this
  low-rate, sustained rise.** In the stored 840-min N0 record, a per-side count of >= 4
  DNp01 spikes in 1 s occurs in only 11 sliding windows. The information exists in DNp01;
  the accepted decoder does not read it.

**DNp04 (offline only, not whitelisted):**

- It does not solve slow approach. At 130 units/s it fires in time in only 21-38 % of
  seeds, near arrival.
- It is clearly earlier at medium speed: 100 % in time at 300 units/s, 0.51 s before
  N4B1C.
- It remains non-specific:
  - 47 responses in 48 orbit-control trials, against 17 for N4B1C;
  - 0.31 free-flight escapes/min in N4B2.

**New side finding: a stop-rotation transient.** When the paddle stops after moving
sideways at constant range, the accepted physical controller rotates it by about 90 deg while
it corrects its overshoot. Through the accepted tilt term this produces 0.35 rad/s of
apparent expansion without any closing range. N4B1C responded to it in 17 / 48 orbit-control
trials, all in the post-hold. The preregistered rule counts these as control false
responses. Under the accepted N4B4 metric split they are **category C** (apparent-size /
tilt geometry) with a real Retina drive, not category A neural false escapes.

**Recommendation:** keep the runtime unchanged in this milestone. Further neural-readout
research on slow approach is justified (see section 9). Any readout that would reach the
runtime requires explicit approval: a new DNp01 temporal-integration path, or any DNp04 use.

## 1. Why N4B6

N4B4 / N4B5 showed that the episode-5 "slow-close" case was dominated by the old overhead
foreshortening artifact: the range was receding and the expansion came from apparent size.
G3 (accepted in N4B5R) removed that artifact. So the product question "does the fly respond
appropriately when the paddle slowly approaches it?" had no clean evidence. N4B6 answers it
with a controlled, preregistered stimulus through the full accepted chain.

## 2. Protocol (preregistered before any neural simulation)

- **Preregistration:** `tools/n4b6_protocol.py`, sha256 `01d91ab8...74b7`, committed and
  pushed as `987b2a9` before any brain was run. `artifacts/m1_8_n4b6/preregistration.json`
  records the hash, and the runner refuses to simulate if the module changes.
- **Before the freeze** only the brain-free geometry characterisation was run. It was used
  to check the geometric conditions, not to choose trajectories by outcome.
- **Controlled state** (fixed-fly-v2, as in N1):
  - escape disabled (a recording policy), fly motion disabled, collisions disabled, ecology
    off;
  - the fly is held at the room centre (1920, 1080), heading 0 (+x); body right is +y.
- **Paddle:**
  - moved only through the accepted physical swatter, by a scripted pointer, at hover
    height 320, face 0 (edge-on);
  - **no click, so no strike phase exists** (verified every tick);
  - before the brain runs, the paddle is placed at rest at the start point, facing its first
    movement, and settles world-only for 50 ticks. Motion onset therefore does not rotate
    the paddle.
- **Trial timeline:** 2.0 s stationary pre-hold, then motion, then a 1.5 s stationary
  post-hold. The brain runs throughout.
- **Chain:** pointer -> physical swatter -> `World.visual_half_size` (G3) ->
  `RetinaProjector` -> `RetinalEncoder` (LC4 / LPLC2) -> MaleCNS -> DNp01 trace -> N4B1C
  replay with the runtime `FixedEscapePolicy`. Nothing is injected directly into any neural
  population.
- **DNp04:** cells 135203 (L) and 1052 (R) are read from the same brain step, offline only.
  They are scored with the frozen N4B2 research readouts: "DNp04 pair 60 ms" and "DNp04
  triple 200 ms" (`tools/n4b2_criteria.py`, sha256 `6175f124...`, unchanged).
- **Brain-noise seeds:** 500001-500048, a new range. The same 48 seeds are used for every
  trajectory (a paired design). The brain seed is seed + 977. **Every trajectory has an
  identical physical path across seeds:** the world is deterministic and seed-independent
  under these conditions.

### 2.1 Speed anchors (human stimulus statistics, not neural outcomes)

Paddle closing speed in the two recorded human sessions (approach phase, horizontal
distance <= 1000 units, closing speed > 5 units/s):

| Percentile | Closing speed (units/s) |
|---|---|
| p10 | 28-45 |
| p25 | 133-136 |
| median | 284-451 |
| p75 | 745-870 |

N4B6 uses 50 (about p10), 130 (about p25), 300 (about the median) and 800 (about p75)
units/s. One body length is 24 units.

### 2.2 Preregistered trajectory matrix and measured geometry

The values below are the actual paddle path (`artifacts/m1_8_n4b6/geometry.json`).

- The paddle overshoots the pointer end point by about 10 units at 130 units/s (about 60 at
  800 units/s). This is the accepted controller. "Closest" is the actual minimum.
- theta is in rad; theta_dot max is over onset to closest approach, in rad/s.
- **Size part:** the contribution of apparent-size change at fixed range (the N4B5
  decomposition).

| ID | Family | Path | Start d / range | Closest d / range | Mean closing speed | Time to closest (s) | Azimuth start -> closest (deg) | Elevation start -> closest (deg) | theta start -> closest | theta_dot max | Size part |
|---|---|---|---|---|---|---|---|---|---|---|---|
| A1 | frontal slow | radial, az +10, 900 -> 200 at 50 | 900 / 955 | 198 / 377 | 41 | 14.06 | 10 -> 10 | 20 -> 58 | 0.195 -> 0.488 | 0.033 | 0 |
| A2 | frontal slow | radial, az +10, 900 -> 200 at 130 | 900 / 955 | 191 / 373 | 106 | 5.48 | 10 -> 10 | 20 -> 59 | 0.195 -> 0.492 | 0.087 | 0 |
| B1 | frontal medium | radial, az +10, 900 -> 200 at 300 | 900 / 955 | 176 / 365 | 240 | 2.46 | 10 -> 10 | 20 -> 61 | 0.195 -> 0.502 | 0.200 | 0 |
| B2 | fast reference | radial, az +10, 900 -> 200 at 800 | 900 / 955 | 138 / 348 | 607 | 1.00 | 10 -> 10 | 20 -> 67 | 0.195 -> 0.525 | 0.520 | 0 |
| C1 | oblique slow R | radial, az +60, 900 -> 200 at 130 | 900 / 955 | 191 / 373 | 106 | 5.48 | 60 -> 60 | 20 -> 59 | 0.195 -> 0.492 | 0.087 | 0 |
| C2 | oblique slow L | radial, az -60, 900 -> 200 at 130 | 900 / 955 | 191 / 373 | 106 | 5.48 | -60 -> -60 | 20 -> 59 | 0.195 -> 0.492 | 0.087 | 0 |
| C3 | lateral slow, close | radial, az +90, 900 -> 100 at 130 | 900 / 955 | 92 / 333 | 100 | 6.24 | 90 -> 90 | 20 -> 74 | 0.195 -> 0.548 | 0.087 | 0 |
| D1 | glancing slow | pass at miss 300 (right), s 900 -> -600 at 130 | 949 / 1001 | 301 / 439 | 84 | 6.72 | 18 -> 90 | 19 -> 47 | 0.173 -> 0.350 | 0.035 | <= 0 (shrinks) |
| D2 | glancing medium | same at 300 | 949 / 1001 | 301 / 439 | 192 | 2.92 | 18 -> 90 | 19 -> 47 | 0.173 -> 0.350 | 0.080 | <= 0 |
| D3 | glancing slow, near | miss 150, at 130 | 912 / 967 | 152 / 354 | 91 | 6.74 | 9 -> 90 | 19 -> 65 | 0.186 -> 0.464 | 0.060 | <= 0 |
| E1 | abort slow | radial 900 -> 400 -> 900 at 130 | 900 / 955 | 393 / 507 (reversal) | 114 | 3.92 | 10 | 20 -> 39 | 0.195 -> 0.365 | 0.070 | 0 |
| E2 | abort medium | radial 900 -> 300 -> 900 at 300 | 900 / 955 | 285 / 428 (reversal) | 253 | 2.08 | 10 | 20 -> 48 | 0.195 -> 0.430 | 0.191 | 0 |
| F1 | stationary control | az +10, d 200, 10 s | 200 / 377 | - | 0 | - | 10 | 58 | 0.486 | 0 | 0 |
| F2 | receding control | radial 200 -> 900 at 130 | 200 / 377 | - | -84 | - | 10 | 58 -> 20 | 0.486 -> 0.150 | 0.002 | - |
| F3 | constant-range control | orbit, radius 300, 130 tangential, 7 s | 300 / 439 | - | 0 | - | 10 -> 184 | 47 | 0.350 (0.409 after the stop) | 0.352 (post-hold) | 0.352 |

Geometric checks, all passed:

- The range decreases monotonically over every approach interval.
- No trajectory passes overhead: the minimum horizontal distance is 90 units (C3) and the
  maximum elevation is 74 deg.
- Approach-interval expansion is purely range-driven: the size part is 0 on radial paths
  and slightly negative on glancing paths.
- The stationary pre-hold has theta_dot exactly 0.

**Consequence of the encoder design:** the encoder uses the azimuth only for its sign. A2
and C1 (both on the right, same range history) therefore receive identical Retina input and
give **bit-identical neural results per seed**. That is a determinism check, not two
independent samples.

## 3. N4B1C detection table (48 seeds per trajectory)

- **In time** = an N4B1C trigger from onset up to and including the closest-approach tick
  (for aborts: the reversal).
- Latencies are from motion onset.
- Paths are the trigger paths of the first trigger after onset (all seeds).

| ID | Class | In time | Miss rate | Median / p95 trigger (s) | Median lead before closest (s) | Median distance at trigger (horizontal / range) | Trigger paths | Late only |
|---|---|---|---|---|---|---|---|---|
| A1 frontal 50 | **undetected** | 0 / 48 | 1.00 | - | - | - | - | 0 |
| A2 frontal 130 | **undetected** | 2 / 48 (4 %) | 0.96 | 5.40 / 5.42 | 0.08 | 199 / 377 | FAST 2 | 0 |
| B1 frontal 300 | **marginal** | 14 / 48 (29 %) | 0.71 | 2.07 / 2.34 | 0.39 | 282 / 426 | FAST 8, SUSTAINED 5, LATERAL 1 | 0 |
| B2 frontal 800 | **reliable** | 48 / 48 | 0.00 | 0.64 / 0.82 | 0.36 | 389 / 504 | LATERAL 30, SUSTAINED 7, FAST 6, LATERAL+SUSTAINED 3, LATERAL+FAST 2 | 0 |
| C1 oblique R 130 | **undetected** | 2 / 48 (4 %) | 0.96 | 5.40 / 5.42 | 0.08 | 199 / 377 | FAST 2 | 0 |
| C2 oblique L 130 | **undetected** | 0 / 48 | 1.00 | - | - | - | - | 0 |
| C3 lateral 130, close | **undetected** | 3 / 48 (6 %) | 0.94 | 5.42 / 5.51 | 0.82 | 197 / 375 | FAST 3 | 0 |
| D1 glancing 130 | undetected | 0 / 48 | 1.00 | - | - | - | - | 0 |
| D2 glancing 300 | undetected | 0 / 48 | 1.00 | - | - | - | - | 0 |
| D3 glancing 130, miss 150 | undetected | 1 / 48 | 0.98 | 3.68 | 3.06 | 449 / 551 | LATERAL 1 | 0 |
| E1 abort 130 | undetected before reversal | 0 / 48 | 1.00 | - | - | - | - | 1 / 48 (after reversal, FAST) |
| E2 abort 300 | marginal before reversal | 8 / 48 (17 %) | 0.83 | 1.94 / 2.07 | 0.14 | 321 / 453 | FAST 5, SUSTAINED 2, LATERAL 1 | 0 |

Notes:

- No approach trajectory produced an N4B1C escape during its 2 s stationary pre-hold. Over
  the whole matrix that is 0 in 24.0 min (upper 0.125/min).
- The slow-approach detections that do occur come at the very end: about 5.4 s into a
  5.48 s approach, via FAST, 80 ms before closest approach.

### 3.1 Processing-level onsets (median over seeds, from motion onset)

- **Retina onset:** theta_dot > 0 at 0.04 s in every approach (one tick of controller lag).
- **Encoder onset:** first tick with driven-side LPLC2 + LC4 sensory spikes above the N0
  per-side maximum of 22.
- **Encoder evidence in time:** encoder onset at least 0.25 s before closest approach.
- **First DNp01 spike:** mostly the cell's spontaneous firing (N0 rate about 0.008 per tick
  per side), so it is not a stimulus onset for slow approaches.

| ID | Encoder onset: P / median (s) | Encoder evidence in time | First DNp01 spike, median (s) | Median of the per-trial maximum driven-side sensory count |
|---|---|---|---|---|
| A1 | 42 % / 12.92 | **38 %** | 0.78 | 20.5 |
| A2 = C1 | 100 % / 2.16 | **100 %** | 0.55 | 43.5 |
| C2 | 100 % / 0.46 | **100 %** | 0.42 | 49 |
| C3 | 100 % / 2.16 | **100 %** | 0.55 | 44 |
| B1 | 100 % / 0.28 | 100 % | 0.29 | 49 |
| B2 | 100 % / 0.16 | 100 % | 0.18 | 60 |
| D1 | 100 % / 8.77 | 50 % | 0.64 | 47 |
| D2 | 100 % / 0.34 | 100 % | 0.35 | 51 |
| D3 | 100 % / 2.77 | 100 % | 0.55 | 50 |
| E1 | 100 % / 2.16 | 100 % | 0.55 | 53.5 |
| E2 | 100 % / 0.28 | 100 % | 0.29 | 53 |

Pre-hold (stationary) maximum driven-side sensory count over all 720 trials: 17.

C2 (left) crosses the encoder's N0 envelope earlier than C1 (right) with identical geometry.
This is the left / right sensory asymmetry of the balanced LPLC2 / LC4 populations under
recurrent MaleCNS input. It does not change the N4B1C outcome (0 / 48 against 2 / 48).

## 4. Controls (false responses)

| Control | Stimulus minutes | N4B1C responses (trials) | Rate / upper 95 % | DNp04 pair 60 ms | DNp04 triple 200 ms |
|---|---|---|---|---|---|
| F1 stationary at 200 units | 9.2 | **0** | 0 / 0.33 per min | 0 | 0 |
| F2 receding 200 -> 900 | 5.5 | **0** | 0 / 0.54 per min | 0 | 0 |
| F3 orbit at constant range | 6.8 | **17 (17 / 48 trials)** | 2.5 / 3.75 per min | **47** | 48 |
| stationary pre-holds (all 15 trajectories) | 24.0 | 0 | 0 / 0.125 per min | 0 | 0 |

- **Stationary and receding controls are clean.** Slow recession produces no response.
- **The F3 responses are all in the post-hold,** 0.44-0.64 s after the orbit stops
  (median 7.48 s from onset; the motion ends at 7.0 s). Mechanism:
  - when the paddle stops after tangential motion, the accepted physical controller
    overshoots and corrects;
  - the correction velocity exceeds the 20 units/s orientation threshold, so the paddle
    rotates by about 94 deg toward it;
  - through the accepted tilt term, `abs(sin(bearing - orientation))` falls from 1.0 to
    0.07, and the apparent half size grows from 77.6 to 92.4 units at constant range;
  - result: theta_dot 0.35 rad/s, **100 % of it size-driven** (supplement, section 5).
- G3 does not remove this, because the paddle is not overhead (elevation 47 deg,
  cos(elevation) 0.68).
- **Interpretation.**
  - The preregistered rule counts F3 as control false responses. So
    `controls_within_category_a` is formally false, and the pooled control rate is 17 in
    21.5 min.
  - Under the accepted N4B4 metric split, these responses have real visual drive from the
    apparent-size / tilt geometry. That makes them **category C** (tracked; not a failure
    by itself), not category A (no-drive neural false escapes).
  - Category A evidence here is clean: 0 in 24 min of stationary pre-hold and 0 in the F1 /
    F2 controls.
- **Open question:** how often real play produces this stop-rotation transient near the fly
  is not known. It is the same class of issue as the old overhead artifact: apparent-size
  change without range change. It lives in the frozen M1.7.1 controller plus the accepted
  tilt term. Changing either needs explicit approval and evidence from recorded play.

## 5. DNp04 offline comparison (not whitelisted)

| ID | N4B1C in time | DNp04 pair 60 ms in time (median s) | DNp04 triple 200 ms in time (median s) | Median DNp04 advance over N4B1C where both fire (s) |
|---|---|---|---|---|
| A1 | 0 % | 0 % | 0 % | - |
| A2 / C1 | 4 % | 21 % (5.19) | 15 % (5.24) | 0.20 |
| C2 | 0 % | 33 % (5.24) | 35 % (5.36) | - |
| C3 | 6 % | 38 % (5.43) | 23 % (5.42) | 0.20 |
| B1 | 29 % | **100 % (1.59)** | 100 % (1.54) | **0.51** |
| B2 | 100 % | 100 % (0.32) | 100 % (0.32) | 0.30 |
| D1 / D2 / D3 | 0 / 0 / 2 % | 0 / 0 / 0 % | 0 / 0 / 0 % | - |
| E1 | 0 % | 0 % | 0 % | - |
| E2 | 17 % | **98 % (1.56)** | 100 % (1.54) | 0.47 |
| F3 orbit control | 17 responses | **47 responses** | 48 | - |

- **Slow approach (130 units/s): DNp04 is not materially earlier in a useful sense.**
  - It fires in time in 21-38 % of seeds, only in the last 0.1-0.3 s before closest
    approach.
  - At 50 units/s it never fires.
- **Medium approach (300 units/s): DNp04 is materially earlier.**
  - It fires in 98-100 % of seeds, about 0.5 s before N4B1C's median.
  - This matches N4B2 (N1 weak approach 60 / 60 against 33 / 60).
- **Non-specificity is confirmed again:** DNp04 fired on 47 / 48 stop-rotation transients.
- **Known free-flight non-specificity** (measured under the old bearing-only geometry):
  - N4B2: DNp04 pair gives 0.31 escapes/min in held-out no-player ROOM free flight, against
    0.083 for N4B1C;
  - N4B3: no policy-observable gate makes it selective in flight;
  - N4B3: only a stationary-fly DNp04 path is clean.
  - G3 removes the overhead part of that free-flight drive, but not the self-approach part,
    which is range-driven. So DNp04's in-flight specificity under G3 is untested but
    unlikely to become clean.
- DNp04 stays research-only. N4B6 is a fixed-fly protocol, which is exactly the regime of
  the N4B3 stationary-fly DNp04 path. **Even there, DNp04 does not rescue the 130 units/s
  approaches.**

## 6. Mechanism (exploratory supplement, not preregistered)

Tool: `tools/n4b6_supplement.py`; output: `artifacts/m1_8_n4b6/supplement.json`.

### 6.1 Stimulus ceiling at hover height

- A radial approach at hover height changes theta only from 0.195 (900 units) to about
  0.49 rad (190 units).
- Expansion per unit of closing speed peaks at about 6.6e-4 rad/s per unit/s near 200-300
  units horizontal distance.
- So 130 units/s gives at most about 0.087 rad/s, 50 units/s about 0.033, and 300 units/s
  about 0.20.
- The encoder's loom drive is 0.4 x theta_dot per tick. The threat term is negligible at
  these rates.

### 6.2 Encoder transfer (all 720 trials, driven side)

| theta_dot (rad/s) | Median sensory spikes | P(> 22, N0 max) | P(DNp01 spike per tick) | P(DNp04 spike per tick) |
|---|---|---|---|---|
| 0 (stationary) | 2 | 0.00 | 0.008 | 0.016 |
| 0.02-0.04 | 3 | 0.01 | 0.016 | 0.034 |
| 0.06-0.08 | 5 | 0.10 | 0.058 | 0.083 |
| 0.08-0.10 | 6 | 0.14 | 0.075 | 0.111 |
| 0.15-0.20 | 18 | 0.42 | 0.159 | 0.245 |
| 0.30-0.40 | 31 | 0.75 | 0.228 | 0.334 |
| 0.50-0.75 | 44 | 1.00 | 0.319 | 0.500 |

- The encoder's N0-separable level (a majority of ticks above 22) is reached only from
  about 0.25 rad/s.
- On a radial hover approach that needs a closing speed of about 380 units/s at 200 units,
  or about 460 units/s at 400 units.
- **At 130 units/s the encoder evidence is real but sporadic:** single ticks above 22
  (median per-trial maximum 44-49), on a mean of 5-10 spikes per tick.

### 6.3 The information exists in DNp01; N4B1C does not read it

Driven-side spike count in the 1 s window that ends 0.26 s before closest approach, against
the per-side 1 s envelope of the stored 840-min N0 record (N4B2 chunks; 4.86 million sliding
windows per DN):

| | N0 (840 min) | A1 (50) | A2 / C1 (130) | C2 (130, L) | C3 (130) | B1 (300) |
|---|---|---|---|---|---|---|
| DNp01 median | mean 0.34 (N4B6 pre-hold windows) | 1 | 4 | 4 | 4 | 7 |
| DNp01 >= 4 in 1 s | **11 windows** (max 4) | 0 % | 67 % | 65 % | 75 % | 100 % |
| DNp04 median | - | 2 | 5 | 6 | 6 | 11 |
| DNp04 >= 5 in 1 s | **0 windows** (max 4) | 0 % | 90 % | 96 % | 100 % | 100 % |

- For 130 units/s approaches, DNp01 raises its driven-side rate about tenfold for seconds,
  but at about 4 spikes/s.
- N4B1C looks for two same-side spikes within 60 ms, or a trace >= 2.1 (three recent
  spikes). A 4 spikes/s train rarely satisfies either before arrival.
- A 1 s count of >= 4 on one side is almost absent from N0 (11 of 4.86 million windows,
  about one episode in 840 min).
- **This is descriptive only. It is not a decoder proposal and has no free-flight
  specificity evidence.** N3 showed that longer DNp01 windows cost latency on fast
  attacks. Self-motion looming in flight also raises DN rates (N4B2 / N4B3 / N4B4).

## 7. Failure-mode classification

| Class | Trajectories |
|---|---|
| Reliably detected | B2 (800 units/s, human p75) |
| Marginal | B1 (300 units/s, human median; 29 %); E2 (abort at 300; 17 % before reversal) |
| Consistently undetected, stimulus-level cause | A1 (50 units/s, human p10): encoder evidence in time in only 38 % of seeds |
| Consistently undetected, readout-level cause | A2, C1, C2, C3 (130 units/s, human p25): encoder evidence 100 %; DNp01 rate about 4/s; N4B1C 0-6 % |
| Undetected, arguably appropriate | D1-D3 glancing passes (closest range 354-439 units, no closing toward overhead); E1 abort at 400 units |
| False responses, stationary / receding | none (F1, F2, pre-holds) |
| Responses without range change (category C) | F3 stop-rotation transient: 17 / 48 N4B1C, 47 / 48 DNp04 |

## 8. Decision (preregistered rule)

Applied mechanically by `tools/n4b6_controlled_approach.py analyze`:

- **Blind spot:** yes. All five slow trajectories that bring the paddle to <= 200 units
  (A1, A2, C1, C2, C3) are undetected.
- **Attribution:**

  | Trajectory | Encoder evidence in time | Attribution |
  |---|---|---|
  | A1 | 38 % | **STIMULUS / RETINA LIMIT** |
  | A2, C1, C2, C3 | 100 % | **REAL DNp01 SENSITIVITY LIMIT** |

- **Overall outcome: "mixed"**, by the rule's literal aggregation. Substantively:
  - **outcome 2 at human-typical slow speeds (p25);**
  - **outcome 3 only at the slowest decile (p10).**
- **Controls:** stationary and receding controls, and the pre-holds, are clean. The
  preregistered control flag is false only because of the F3 category-C stop-rotation
  responses (section 4).

This answers the N4B6 question:

- **The accepted G3 + N4B1C system has a reproducible slow-approach sensitivity problem
  under controlled monotonic approach.**
- It is not caused by the old geometry. Radial approaches have no tilt term (the paddle
  faces its motion), so G0 and G3 give identical Retina input for them.
- At typical slow speeds it is primarily a DNp01-readout limit; at very slow speeds, a
  stimulus limit.

## 9. Recommendation

1. **Keep the runtime unchanged in this milestone.** Nothing in N4B6 is a runtime change.
2. **Neural-readout research on slow approach is justified (outcome 2).** The natural next
   research milestone would characterise an N0-safe, free-flight-specific DNp01 temporal-
   integration readout, for example per-side spike counts over about 1 s combined with the
   accepted N4B1C paths. It would need:
   - a preregistered N0 holdout (new seeds);
   - no-player free-flight evaluation under G3 (categories A-D);
   - fast-attack latency preservation (N1 strong / medium; human direct strikes).
   Any runtime adoption would need explicit approval and a human test.
3. **Do not pursue DNp04 for slow approach.** It is materially earlier only at medium speed.
   It is still non-specific (orbit control, N4B2 free flight). Whitelisting it would need
   explicit approval, and N4B6 gives no new reason to request it.
4. **Treat the 50 units/s case as a stimulus limit.** Approaches this slow, at hover height,
   carry too little expansion for the encoder to separate from N0 before arrival. Fixing
   that would mean changing Retina / encoder equations or parameters, which is out of scope
   and needs explicit approval.
5. **Stop-rotation transient (category C):** track it. If recorded human play shows escapes
   when the paddle stops beside the fly, a separate geometry / controller review would be
   needed. That touches frozen M1.7.1 / N4B5R systems and needs explicit approval.

**Architectural approval boundary:** any of items 2 (runtime adoption), 3, 4 or 5 changes the
runtime, the whitelist or the Retina / encoder. N4B6 stops here.

## 10. Reproducibility

Commands, from the main checkout, using the main virtual environment:

    python tools/n4b6_controlled_approach.py freeze        (done once; refuses to re-freeze)
    python tools/n4b6_controlled_approach.py geometry      (brain-free, seconds)
    python tools/n4b6_controlled_approach.py run --worker K --workers 6    (K = 0..5; about 6 min in parallel)
    python tools/n4b6_controlled_approach.py analyze
    python tools/n4b6_supplement.py

The runner requires the N4B5R worktree (`artifacts/worktrees/n4b5r-geometry`, or
`N4B5R_WORKTREE`) to be clean at `363a1a94cf3f5e33efab08cb28594c24ca694a03`.

| Artifact (`artifacts/m1_8_n4b6/`, git-ignored) | sha256 |
|---|---|
| `preregistration.json` | `dde246eef402030a9d52af9287cc418e1842b8ce5dd669968879062c35e29625` |
| `geometry.json` | `8ff167ce715ba8ce7664523fac314f00765f0c5ba091e3f16648d98c5e830f64` |
| `results.json` | `8807cfffb7fdfa962dcc6b74522d3983db21fb093e62c94217810a8a52fd0401` |
| `per_trial.json` | `849cd8275ddb90cbeb05002c313a48e5438330051db04d246915a87dd677575b` |
| `supplement.json` | `84d4059d5d3fd1f24ca44747fd3e11ff09ce6210dc5210cf688898f96b1b49d6` |
| `trials/<id>/<seed>.npz` | 720 trial records (geometry, Retina, sensory, drive, DNp01 trace, DNp01 / DNp04 spikes) |

| Tool | sha256 |
|---|---|
| `tools/n4b6_protocol.py` (preregistered) | `01d91ab87a4df1b6273cc62b44dedcf8b04fe7c750ee733e27dd471b296674b7` |
| `tools/n4b6_controlled_approach.py` | `d6d5a366a2dd148d2856102bd257239d9332da20a6c40b03562ae5b57ffefd4d` |
| `tools/n4b6_supplement.py` | `ef1ebecc8b5b67ca7b155a0319c536f783c8c773edd88d1d4fc35821d597052e` |

Used seeds (never reuse for design): **N4B6 brain-noise seeds 500001-500048.**

## 11. Limitations

- **Fixed fly only.** Free-flight slow approaches combine this stimulus with self-motion
  looming, which N4B2-N4B4 showed is the main specificity problem for any more sensitive
  readout.
- **Hover height only.** The game has no slow descent outside strike phases, so slow
  approach means horizontal motion at 320 units. That caps theta at about 0.57 rad
  (overhead).
- **48 seeds per trajectory:** detection probabilities have about +/- 0.14 (95 %)
  resolution near 0.5. A2 and C1 are the same sample (azimuth sign only).
- **The 0.25 s response margin** (about one strike's commit plus fast-swing duration) is a
  preregistered product-level engineering margin, not a biological constant.
