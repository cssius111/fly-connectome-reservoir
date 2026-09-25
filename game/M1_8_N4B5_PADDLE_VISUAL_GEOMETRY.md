# M1.8-N4B5: paddle visual geometry and overhead foreshortening

Status: **research only; complete; decision in section 10.** No runtime, configuration,
Retina, World, encoder, brain, decoder, policy-whitelist, lifecycle, physics or recorder
change. N4B1C is not reopened or retuned, and DNp04 is not revisited. Candidate geometries
were evaluated only inside research processes, by replacing `World.visual_half_size` in
memory. No repository file of the runtime was modified.

Question: does `World.visual_half_size` with `tilt_anisotropy = 0.25` create an unrealistic
apparent-size transient when the paddle passes nearly overhead?

Short answer: **Yes. The overhead events are a clear artifact of the current tilt_anisotropy
formulation (answer C).**

- **The artifact.** The anisotropy depends only on the horizontal bearing, with no
  elevation weighting. When the fly passes beneath a paddle that is not moving at all, the
  bearing term alone produces 2.5-6.9 rad/s of expansion within 10 units of the footprint
  centre. That is committed-strike territory. The physically correct range-driven expansion
  there is 0.13 rad/s, and every 3D projection makes the bearing effect vanish overhead.
- **What it caused.** All 8 N4B4 overhead escapes came from this term, as did the human
  episode-5 "slow-close" signal and its pre-click "final loom".
- **The replacement.** A minimal geometric correction, G3, weights the anisotropy by
  cos(elevation). It:
  - removes every foreshortening-driven free-flight escape (8 to 0 in 249 min);
  - leaves committed-strike behaviour unchanged (N1 strong / medium 60 / 60, median
    0.08 / 0.10 s, as with G0);
  - keeps human direct-strike latency and strike-phase coverage within the noise-realization
    range of the current geometry.
  - Its cost: hover-bout coverage drops, but only on the bouts that were themselves driven by
    the artifact.
- **Decision: 3. Propose G3 as a runtime geometry candidate. Stopped for approval.** No
  runtime change has been made.

## 0. Reporting categories (adopted from N4B4)

| Category | Meaning | Criterion |
|---|---|---|
| A | fixed-fly / no-drive neural false escapes (spontaneous, no visual expansion) | < 0.1/min at 95 % (existing) |
| B | inappropriate free-flight escapes (visual input present, behaviourally inappropriate) | < 0.1/min at 95 %, a **provisional working engineering criterion**, not a calibrated biological constant |
| C | foreshortening-driven escapes (expansion mainly from the apparent-size / tilt geometry) | tracked; not a failure by itself |
| D | genuine self-approach escapes (the fly's own motion closes the range to the paddle) | tracked; not a failure by itself |

C and D are not called false triggers.

## 1. The current geometry, exactly

`game/world.py`, `World.visual_half_size`, is the only producer of the paddle size the Retina
sees (`RetinaProjector.project`: theta = 2 atan(half / R), with R the 3D fly-paddle distance):

    f    = edge_on_factor + (1 - edge_on_factor) * face                      # 0.65 .. 1.0
    f   *= 1 - tilt_anisotropy * (1 - face) * abs(sin(bearing - orientation))  # tilt_anisotropy 0.25
    half = paddle_radius * f                                                # paddle_radius 144

Conventions (from `game/world.py`, `game/physical_swatter.py`, `game/M1_5.md`):

- **Positions:**
  - the play plane is (x, y) in world units, with y growing downward on screen;
  - the fly lives in the plane (z = 0);
  - the paddle centre is at `height` above it: 320 while hovering, down to 24 at contact.
- **`face`** runs from 0 (edge-on, hovering) to 1 (face-on, striking). It is interpolated
  through the strike phases (0, 0.15, 0.85, 1.0, 0.85, 0.0).
- **`orientation`** is a world-plane angle: the paddle's handle / approach axis.
  - During approach it is steered toward the paddle's velocity direction (rate- and
    acceleration-limited).
  - During a strike it is latched to the attack direction.
  - A parked paddle keeps its last orientation.
- **`bearing`** is `atan2(fly.y - paddle.y, fly.x - paddle.x)`, the **horizontal**
  direction from the paddle to the fly.
- `M1_5.md` describes the term as "up to 25% foreshortening while tilted, vanishing at
  face-on contact ... a simplified geometric projection".

Analytic properties:

- **Bearing only.** The anisotropy depends on the horizontal bearing alone. **It has no
  elevation dependence:** the same +/-25 % modulation applies with the paddle at 5 deg or
  89 deg above the horizon.
- **Rate grows without bound overhead.** d(half)/dt = r f0 a (1 - face) cos(b - o)
  sign(sin(b - o)) db/dt. For a stationary paddle, db/dt = v_perp / d_h, the fly's speed
  across the line to the paddle over the horizontal distance. As the fly passes beneath
  the paddle (d_h -> 0), db/dt, and with it the size-term theta_dot, grows without bound.
  The bearing turns through 180 deg in the time the fly needs to cross the footprint centre.
- **Kinks.** abs(sin) has a kink (a sign change of the derivative) whenever the bearing
  crosses the orientation axis. Directly overhead, a one-tick jump of the bearing produces
  a one-tick jump of size.
- **The range term is well behaved.** R >= height, and dR/dt ~ v d_h / R -> 0 overhead.
  So near overhead the size term dominates theta_dot completely.

These are properties of the formula. Whether they are unrealistic is measured below, against
a geometric reference.

## 2. Geometric reference and preregistered candidates

The game is a 2D plane plus a paddle height. It does not define a unique 3D paddle
orientation, so the reference makes its assumptions explicit (`tools/n4b5_geometry.py`):

- The paddle is a thin circular disk of radius 144, centred at (x, y, height).
- At face 0 its unit normal is horizontal, along `orientation`. This is the choice that
  reproduces the runtime's sign of anisotropy: largest when the fly lies along the
  orientation axis.
- The normal tilts to vertical, facing the fly plane, as face goes to 1 (tilt = face x
  90 deg).
- Perspective projection of a small disk gives an ellipse with semi-major axis r and
  semi-minor axis r abs(n . v), where v is the unit view direction.
- The reference reports the mean projected semi-axis, r (1 + abs(n . v)) / 2. That spans
  [0.5 r, r], the same range as the runtime's [0.49 r, r], with no fitted parameter.

The key geometric fact:

- For a plate seen from nearly straight below, v is almost vertical, so n . v -> 0 for a
  vertical plate, whatever the horizontal bearing.
- So in any 3D projection the bearing dependence fades as cos(elevation). The runtime term
  does not fade.

Candidates, frozen before the full evaluation (`artifacts/m1_8_n4b5/frozen_geometry.json`,
sha256 `a11cafa09750b50bf3cad6e032746336981cc99b481edcdbd45656ddaa830b49`;
`tools/n4b5_geometry.py` sha256 `c3884e644df5c51ee95489b8f204795e1eb36648d5da14415de3abe0f3d7066a`):

| Candidate | Formula | Rationale |
|---|---|---|
| G0 current | as above | reference |
| G1 isotropic | tilt_anisotropy = 0 | control: no bearing term |
| G2 reduced | tilt_anisotropy = 0.10 | the "reduced anisotropy" example |
| **G3 elevation-aware** (primary) | the anisotropy term multiplied by cos(elevation) = d_h / R | the minimal geometric correction: identical to G0 at low elevation; the bearing term fades overhead as in any 3D projection |
| G4 projected disk | r (1 + abs(n . v)) / 2, with the disk normal as above | explicit 3D reference |

The runtime-candidate criteria were also written into the freeze file before the full
evaluation (section 7).

## 3. Verification

G0, recomputed from recorded world state with the N4B4 alignment (the Retina of tick t is
projected from the state stored at tick t-1), reproduces every recorded theta:

- 43 N4B4 ROOM replays and both human sessions;
- maximum absolute error 4.4e-16.

Re-simulation with G0 inside the research harness reproduces the original records exactly:

- both human sessions, DNp01 on 7025 / 7025 and 4130 / 4130 stepped rows;
- N1 300 / 300 trials and fixed-fly N0 150 / 150 trials.

## 4. Measured behaviour: synthetic passes under a parked paddle

A fly flies straight at 200 units/s past a parked paddle (height 320, face 0), for several
closest horizontal offsets and crossing angles relative to the paddle axis. The table gives
peak theta_dot in rad/s on 20 ms samples, total and size-term only
(`artifacts/m1_8_n4b5/analytic.json`).

| Crossing 90 deg; offset (units) | 0 | 2 | 5 | 10 | 25 | 50 | 100 | 200 | 300 |
|---|---|---|---|---|---|---|---|---|---|
| **G0 current**: total / size term | **6.86 / 6.86** | 6.13 / 6.13 | 4.26 / 4.26 | 2.52 / 2.52 | 1.07 / 1.06 | 0.53 / 0.53 | 0.27 / 0.26 | 0.14 / 0.12 | 0.10 / 0.07 |
| G1 isotropic (pure range) | 0.13 / 0 | 0.13 / 0 | 0.13 / 0 | 0.13 / 0 | 0.13 / 0 | 0.13 / 0 | 0.12 / 0 | 0.10 / 0 | 0.07 / 0 |
| G2 reduced 0.10 | 2.72 / 2.72 | 2.43 | 1.69 | 1.01 | 0.43 | 0.22 | 0.12 | 0.10 | 0.08 |
| **G3 elevation-aware** | 0.17 / 0.08 | 0.17 / 0.08 | 0.17 / 0.08 | 0.17 / 0.08 | 0.16 / 0.08 | 0.16 / 0.08 | 0.15 / 0.08 | 0.12 / 0.06 | 0.09 / 0.05 |
| G4 projected disk | 0.10 / 0 | 0.11 / 0 | 0.11 / 0 | 0.11 / 0 | 0.12 / 0.01 | 0.13 / 0.01 | 0.14 / 0.02 | 0.14 / 0.03 | 0.12 / 0.03 |

Crossing 45 deg: G0 reaches 4.83 at offset 0 and 0.92 at 10; G3 at most 0.16. Crossing
0 deg, along the axis: G0 reaches 3.82 at offset 2 and 1.02 at 10.

Strike-like reference: face ramps 0 -> 1 while the height drops 320 -> 24 above a fixed fly
in 0.5 s, at offsets 30 / 100 / 170 units.

- Peak theta_dot is 6.76 / 3.71 / 2.17 rad/s, identical for G0, G1, G2 and G3 (the tilt
  term vanishes at face 1).
- G4 changes it: 5.54 / 3.03 / 2.16, and the end theta at offset 170 is 0.89 against 1.40.

**Result: a fly cruising under a stationary paddle receives, from the G0 size term alone,
2.5-6.9 rad/s of expansion within 10 units of the footprint centre.** That is the same range
as a committed strike (2.2-6.8 rad/s), while the physical range-driven expansion there is
0.13 rad/s: 20-50 times smaller. Every 3D projection makes the bearing effect vanish
overhead. G3 keeps the size term at 0.08 rad/s or below at every offset, without touching
low-elevation behaviour or the strike.

## 5. The known cases, decomposed

Theta change split into range, relative position (bearing and elevation), orientation and
face contributions (`tools/n4b5_geometry.decompose`; `artifacts/m1_8_n4b5/events.json`).

**N4B4 overhead events.** Peak theta_dot in the 12 samples before the escape, under each
candidate:

| Event | Elevation | G0 | G1 | G2 | G3 | G4 | G0, last 10 samples: range / bearing |
|---|---|---|---|---|---|---|---|
| N4B2 holdout 7201 @ 3563 | 83 | 0.51 | 0.04 | 0.21 | 0.10 | 0.15 | +0.003 / +0.052 |
| N4B2 holdout 7211 @ 3755 | 85 | 0.61 | 0.03 | 0.24 | 0.08 | 0.20 | +0.002 / +0.048 |
| N4B3 dev 7317 @ 1549 | 84 | 0.61 | 0.02 | 0.24 | 0.07 | 0.16 | +0.001 / +0.084 |
| N4B3 holdout 7405 @ 7866 | 78 | 0.41 | 0.03 | 0.16 | 0.11 | 0.09 | +0.000 / +0.072 |
| N4B3 holdout 7406 @ 7419 | 67 | 0.22 | 0.11 | 0.14 | 0.16 | 0.03 | +0.016 / +0.025 |
| N4B3 holdout 7412 @ 4713 | 74 | 0.26 | 0.07 | 0.12 | 0.14 | 0.10 | +0.005 / +0.044 |
| N4B3 holdout 7432 @ 6505 | 83 | 0.64 | 0.02 | 0.25 | 0.06 | 0.22 | -0.001 / +0.102 |
| N4B3 holdout 7438 @ 284 | 74 | 0.28 | 0.06 | 0.12 | 0.13 | 0.05 | +0.003 / +0.050 |

The N4B4 self-approach events are essentially unchanged by G1 and G3: 0.05-0.16 rad/s under
every candidate. Their expansion is range-driven. Orientation and face contribute nothing in
the ROOM events: the parked paddle has a fixed orientation and face 0.

**Human episode 5 (N2b session), theta_dot per candidate:**

| Ticks | Situation | Elevation | G0 (recorded) | G1 | G3 | G4 | G0 step decomposition |
|---|---|---|---|---|---|---|---|
| 610-613 | "slow close": the DNp04 pair of N4B2 fired at 613 | 78-83 | +0.18 to +0.40 | -0.07 to -0.16 | **-0.19 to -0.25** | +0.49 to +0.68 | range about -0.002 per step, bearing +0.004 to +0.009 |
| 624 | 144-cell saturated volley | 88 | **+4.38** | +0.06 | +0.48 | +0.69 | bearing **+0.076** in one tick, orientation +0.010 |
| 663-668 | pre-click "final loom"; N4B1C fired at 668 | 81-83 | +0.21 to +1.73 | about 0 | about +0.19 | +0.26 to +0.41 | bearing +0.004 to +0.031 per step; range about 0 |
| 670-679 | the actual strike (commit, fast swing, contact) | 83 to 26 | +0.75 to +8.19 | +0.62 to +7.39 | **+0.42 to +7.36** | -2.60 to +6.58 | range and face |

- **The slow-close signal and the pre-click "final loom" are both bearing foreshortening of
  a paddle hovering almost straight overhead.** Under G3 the slow-close interval shows no
  expansion at all.
- **The real strike is preserved by G3.**
- G4 distorts the strike: negative theta_dot at 679-680, while the paddle comes down at
  contact. As expected from its tilt assumption, it fails as a runtime candidate.

## 6. Critical question

**C. A clear artifact of the current tilt_anisotropy formulation.**

- **Not A (physically reasonable).** A perspective projection of a finite plate (section 2)
  makes the bearing effect vanish as cos(elevation). Under a stationary paddle, the real
  apparent-size change near overhead is at most 0.08 rad/s (G3) or about 0.0 rad/s (G4 at
  90 deg crossing). G0 gives 2.5-6.9 rad/s within 10 units (section 4): 20-50 times the
  physical range-driven expansion (0.13 rad/s). A stationary object cannot produce
  committed-strike-level looming by being flown under.
- **Not B (tolerable approximation).**
  - The artifact changes behaviour. All 8 N4B4 overhead escapes, 38 % of all N4B1C
    free-flight escapes, are produced by it (bearing term 90-100 % of their expansion).
  - It created the human episode-5 "slow-close" signal: 100 % of the 610-613 expansion
    (section 5) motivated two research milestones (N4B2, N4B3).
  - It created the pre-click "final loom" at 663-668, on which N4B1C fired.
  - It produces a one-tick +0.087 rad jump (theta_dot +4.4 rad/s, a saturated 144-cell
    volley) when the paddle is directly overhead.
- **C, for these quantitative reasons:**
  - the size-term rate scales as 1/(horizontal distance);
  - its magnitude is independent of elevation;
  - a correction that only adds the elevation weighting any projection has (G3) removes
    the effect while leaving low-elevation and strike stimuli unchanged (sections 4-5,
    and section 7 below).

## 7. Preservation tests (candidates re-simulated; N4B1C decoder unchanged)

All candidates were re-simulated with the unchanged N4B1C decoder. With G0 the harness
reproduces every original record exactly:

- N1: 300 / 300 trials;
- N0: 150 / 150 trials;
- human sessions: every stepped row;
- ROOM: the N4B4 reconstructions.

**Noise-realization control (added after the freeze; offline only).** A candidate changes
the Retina and therefore the brain's noise realization, and single-run hover counts turned
out to be dominated by that. So both human sessions were re-simulated with four additional
brain-noise seeds (same input, `--noise-offset` 1-4) for G0, G1 and G3.

- **G0's own recorded realization meets 33 / 33 hover bouts by construction:** the bouts are
  defined by its recorded escapes.
- **With the same input and other noise seeds, G0 meets 24-28.**

**A / B. N1 committed strikes** (N4B1C first firing after the click; detected of 60, median
latency):

| | G0 | G1 | G2 | **G3** | G4 |
|---|---|---|---|---|---|
| strong_direct | 60, 0.08 s | 60, 0.08 | 60, 0.08 | **60, 0.08** | 60, 0.09 |
| medium_committed | 60, 0.10 s | 60, 0.08 | 60, 0.08 | **60, 0.10** | **59, 0.16** |

**C. N1 weak / glancing / aborted** (descriptive; detected of 60):

| | G0 | G1 | G2 | G3 | G4 |
|---|---|---|---|---|---|
| weak_approach | 33 | 23 | 27 | 30 | 60 |
| glancing_pass | 30 | 37 | 33 | 36 | 60 |
| aborted_approach | 49 | 24 | 39 | 44 | 60 |

G3 stays within a few trials of G0 (-3 / +6 / -5, single realization). G1 loses half the
aborted approaches. G4 fires on every weak stimulus.

**D / E / H. Human sessions** (open loop). The first figure in each cell is the frozen
realization; the bracket gives the noise-control range over five realizations.

| | G0 | G1 | **G3** | G4 |
|---|---|---|---|---|
| direct strikes fired / 39 | 39 [38-39] | 38 [38-39] | **38 [38-39]** | 39 |
| median latency after click (s) | 0.10 [0.08-0.10] | 0.08 [0.07-0.08] | **0.10 [0.08-0.10]** | 0.06 |
| strike-phase escapes met / 29 | 29 [28-29] | 29 [29] | **29 [28-29]** | 28 |
| hover bouts met / 33 | 33 (selection) [24-28 over noise 1-4] | 20 [20-21] | **26 [23-26]** | 29 |
| open-loop firings (3.7 min) | 82 [75-82] | 69 [66-70] | 78 [69-78] | 107 |

- The one direct strike G3 misses in the frozen realization (strict session, episode 4,
  click 583) is a marginal case even under G0: detected only at +0.20 s. G0 misses one
  strike in 3 of its 4 other realizations.

Hover coverage by what drove the bout under G0 (mean detection rate; G0 over noise seeds
1-4, G3 over seeds 0-4):

| Hover bouts | n | G0 | G3 |
|---|---|---|---|
| G0 expansion >= 60 % from apparent size | 11 | 0.91 | **0.58** |
| G0 expansion < 60 % from apparent size | 22 | 0.74 | **0.84** |

**G3 loses hover coverage only on bouts whose G0 signal was mainly the foreshortening
artifact, and holds or improves coverage on range-driven hover bouts.** Part of the hover
responsiveness accepted in the N4B1C human test was therefore produced by the artifact. A
human test would have to judge the difference.

**Special cases:**

- far perched non-contact approach: silent under every candidate;
- voluntary takeoff: silent under every candidate;
- chase before 589: 576 / 574 / 580 / 581 (G0 / G1 / G3 / G4);
- slow close: G0 668; G3 none in 3 of 5 realizations, 624 or 626 in 2 (the residual
  overhead volley at 624).

**F / J. No-player ROOM free flight** (closed loop under the live runtime; same 83 seeds and
thread counts; 249 min per candidate). Categories as in section 0, with category B from
counterfactual replays of every new escape:

| | all escapes (95 % upper /min) | A no-drive | B inappropriate (upper) | C foreshortening | D self-approach | mixed |
|---|---|---|---|---|---|---|
| G0 | 21, 0.084 (0.121) | 0 | 2 (0.025) | **8** | 8 | 3 |
| **G3** | **12, 0.048 (0.078)** | 0 | 3 (0.031) | **0** | 5 | 4 |
| G1 | 9, 0.036 (0.063) | 0 | 1 (0.019) | 0 | 8 | 0 |

- **G3's 12 escapes** are all at paddle elevation <= 72 deg, with drive 0.03-0.12. The
  largest apparent-size share is 0.70, in a mixed event at 57 deg.
- The three category-B events are weak (drive 0.03-0.06): long-range self-approaches whose
  closest point lies beyond the 1.5 s horizon.
- Category D, 8 against 5, is a difference of different closed-loop realizations. It is not
  a systematic loss: G1 has 8, and the self-approach expansion is range-driven, so G3
  leaves it essentially unchanged (section 5).

**I. Fixed-fly N0** (original arm, 150 x 1400 ticks, 70 min):

- 0 N4B1C events under G0, G1 and G3 (95 % upper 0.043/min).
- G0 is identical to the record, 150 / 150.
- G1 and G3 differ trace by trace because the paddle's settle move before each window is
  seen differently. Encoder drive inside the windows is zero for every candidate.

**Frozen runtime-candidate criteria, G3:**

| Criterion (frozen before the evaluation) | G3 | Result |
|---|---|---|
| size-term theta_dot <= 2 x range-only at every offset | at most 0.08 against 0.13 | pass |
| N1 strong / medium 60 / 60, median within +0.02 s | 60 / 60, 0.08 / 0.10 (G0 0.08 / 0.10) | pass |
| every human direct strike fires by resolution; median within +0.02 s | median 0.10 (G0 0.10); **38 / 39 in the frozen realization** | **median passes; count fails as written** (G0 itself is 38 / 39 in 3 of 4 other noise realizations) |
| far perched silent | silent | pass |
| fixed-fly N0 unchanged | 0 events (G0 0) | pass (statistical, not trace-identical; see above) |
| ROOM: C reduced, A unchanged, B < 0.1/min | C 8 to 0; A 0; B 3 in 249 min (upper 0.031) | pass |
| descriptive: weak N1, hover, self-approach | within noise; hover loss confined to artifact-driven bouts | reported |

Other candidates:

- **G1** (isotropic) also removes the artifact. But it discards the accepted low-elevation
  tilt cue, gives the largest hover loss (20-21 / 33), and loses half the aborted N1
  approaches.
- **G2** (0.10) keeps 2.7 rad/s overhead and fails criterion 1.
- **G4** (explicit disk) distorts the strike (medium 59 / 60 at 0.16 s) and fires on every
  weak stimulus.
- **All three are rejected.**

## 8. DNp04

DNp04 is not revisited and stays not approved for flight. For the record, the episode-5
slow-close expansion that motivated N4B2 and N4B3 does not exist under G3 (section 5). There
is therefore no evidence from that case for a slow-approach readout gap once the geometry is
corrected.

## 9. Biology and interpretation

- **A. Published evidence:** none is used or claimed here. The question is about rendering
  geometry, not fly biology.
- **B. Interpretation:** a physical fly seeing a large object pass overhead receives
  retinal size change only from real projection changes. Any perspective projection
  removes the horizontal-bearing effect as elevation approaches 90 deg.
- **C. Simulator engineering:**
  - G3 is a geometric correction to a Class C heuristic: the anisotropy is weighted by the
    horizontal component of the view direction.
  - It is not a biological parameter.
  - Its value at low elevation equals the accepted M1.5 / M1.7 behaviour.

## 10. Decision

**3. PROPOSE A NEW GEOMETRY RUNTIME CANDIDATE: G3, elevation-aware tilt anisotropy.**

    f   = edge_on_factor + (1 - edge_on_factor) * face
    f  *= 1 - tilt_anisotropy * cos(elevation) * (1 - face) * abs(sin(bearing - orientation))
    cos(elevation) = horizontal fly-paddle distance / 3D fly-paddle distance

- **The current formula is demonstrably artifact-prone** (section 6).
- **G3 is the minimal geometric correction.**
  - It is identical at low elevation and during strikes.
  - It removes all foreshortening-driven free-flight escapes.
  - It preserves committed-strike detection and latency.
  - It keeps human direct-strike and strike-phase behaviour within the current geometry's
    own noise range.

What approval would cover, and what it would require (not done):

- **It is a Retina/World change** (`World.visual_half_size`, and possibly an explicit
  configuration flag with a ROOM config version bump). It touches M1.5 / M1.7-era swatter
  visual geometry. **It is not an N4B1C decoder change:** thresholds, windows and paths stay
  frozen.
- **It changes the visual input of the accepted N4B1C runtime.** N4B1C's human acceptance
  of hover responsiveness was judged under G0. The measured consequence is fewer escapes
  while the paddle sweeps nearly overhead: hover bouts that were artifact-driven drop from
  0.91 to 0.58 detection. A human test should confirm that the game still feels responsive.
- **Provenance.** A runtime milestone would need to:
  - regenerate the tests that pin the retinal geometry;
  - re-verify the N4B1C decoder record against the new ROOM config version;
  - repeat the fixed-fly N0 and free-flight checks at runtime.

Alternatives if approval is not given: keep G0 and document the artifact (outcome 2). The
N4B4 metric split already keeps it out of the acceptance categories: C is tracked, not
failed.

**STOPPED here for explicit approval before any runtime geometry change.**

## 11. Reproduction and validation

    python tools/n4b5_analysis.py verify
    python tools/n4b5_analysis.py analytic
    python tools/n4b5_analysis.py events
    python tools/n4b5_analysis.py freeze
    python tools/n4b5_resim.py all --cands G0_current,G1_isotropic,G2_reduced_0p10,G3_elevation_aware,G4_projected_disk --room-cands G3_elevation_aware,G1_isotropic
    python tools/n4b5_resim.py human --cand G3_elevation_aware --noise-offset 1            (noise control; offsets 1-4)
    python tools/n4b5_resim.py n0 --cand G3_elevation_aware
    python tools/n4b5_resim.py room --cand G3_elevation_aware --source n4b3_holdout --seed 7401 --suppress TICK   (counterfactuals)
    python tools/n4b5_evaluate.py

Artifacts (`artifacts/m1_8_n4b5/`, git-ignored):

- `frozen_geometry.json`, sha256 `a11cafa09750b50b`;
- `verify.json` `083f03a8d0eedcd2`;
- `analytic.json` `e7f3f5a28b8f0cf8`;
- `events.json` `c14e70b2e6fdab9c`;
- `evaluation.json` `1545aa49ab1e77f2`;
- per-candidate `human_*.json` (plus `_noise1..4`), `n1_*.json`, `n0_*.json`,
  `room_*_seed*.json/.npz` and `*_cf*.json/.npz`.

Validation:

- `tools/n4b5_geometry.py` is unchanged since the freeze.
- 330 / 330 tests pass.
- The 20 protected files match `artifacts/m1-2/protected-before.json`, and none differs from
  `76806f0`.
- `verify_results.py` passes.
- No file under `game/` other than the new report, and neither `game_room_config.json` nor
  `results/`, differs from `6b5c4ce`.
- `feature/m1-8-n4b1c-runtime` is still at `e3c55b3`, and both runtime worktrees are clean.
- The N4B2 and N4B3 frozen criteria modules are unchanged.

Process notes:

- **Noise control (after the freeze).** It was added once single-run hover counts proved
  noise-dominated. It does not change any candidate or criterion.
- **A harness bug, found and fixed.** A tool bug briefly overwrote the offset-0 human files
  with noise-control runs. It was detected before any result was used: the G0 exactness
  check failed. The files were regenerated, and G0 is exact again.
- **Scope limits.**
  - The geometric reference uses an explicit disk assumption, because the game does not
    define a unique 3D paddle orientation.
  - The human analyses are open loop, and the ROOM free-flight background is a parked
    paddle only.
  - There is one tester and two sessions.
