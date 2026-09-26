# M1.8-B2b-R0: escape / cruise compatibility study

Status: **design and research only. Nothing was modified.** No runtime behavior, no
configuration, no sampled distribution, no `room_kinematic_scale` change, no `max_speed`
change, no `escape_impulse` change, no M1.8-A reopening, no RL.

Baseline: `e504499`. Analysis is reproducible via `tools/escape_cruise_study.py`, which
also changes nothing (`artifacts/m1_8_b2b_r0/escape-cruise.json`).

**Central result.** The speed reduction identified in
[M1_8_B2B_CAPS.md](M1_8_B2B_CAPS.md) is real, is caused entirely by a Class-C engineering
ceiling, and is already worse than "a fast fly gets slower": above roughly 30 BL/s of
cruise the ceiling also **erases the graded neural escape strength** in the speed
dimension, and the evasive *lateral* displacement degrades as cruise rises. The
directional component of escape is untouched by the ceiling.

## 1. Current mechanic audit

The accepted escape path, read from `game/action.py` and `game/world.py`:

1. `FixedEscapePolicy.decide` fires when summed DNp01 crosses the calibrated threshold
   (ROOM 1.45) and the fly is outside its refractory window.
2. It emits **one** `Action` with `escape=True`,
   `strength = min(1, dnp01_total / (2*threshold))`, `lateral = ` smoothed DNp01 left/right
   asymmetry in [-1, 1], `forward = escape_forward_bias = 0.35`, and
   `saccade = asymmetry * strength`.
3. Refractory is 0.4 s (20 ticks). During it the behavior state remains `ESCAPE` but **no
   further impulse is applied**. The escape is a single-tick velocity increment.
4. `World._move_fly` converts `(lateral, forward)` to a world-frame unit vector and adds
   `escape_impulse * strength` = up to **880 units/s = 36.667 BL/s** to the velocity.
5. Because `action.escape` is set, `_neural_active` is true, so `threat_priority` holds and
   the profile is `neural_priority`: damping target reverts to `baseline_speed` (9 BL/s)
   and the executor clamps at `max_speed` = **41.667 BL/s**.
6. Heading change is delivered separately, by the saccade actuator responding to the
   `saccade` request. Sideslip then rescales velocity to the same magnitude, so it does
   not alter speed.

So translational escape and directional escape travel through **two different channels**:
an impulse on velocity, and a saccade pulse on heading. Only the first meets the ceiling.

## 2. Offline analysis

54 single-tick cases: pre-escape speed {10, 20, 30, 40, 60, 80} BL/s x direction
{forward-dominant (lat 0.0), combined (lat 0.5), lateral-dominant (lat 1.0)} x strength
{0.25, 0.50, 1.00}, all with `forward = 0.35`. The analytic model reproduced the real
`World` tick in **54/54** cases with zero wall or object contact, so the numbers below are
the accepted mechanics, not an approximation.

### 2.1 Speed, at full strength, lateral-dominant

| Pre-escape (BL/s) | Post-escape now (BL/s) | Post-escape uncapped (BL/s) | Change | Cap binds |
| --- | --- | --- | --- | --- |
| 10 | 38.90 | 38.90 | +289.0% | no |
| 20 | 41.67 | 44.75 | +108.3% | yes |
| 30 | 41.67 | 51.66 | +38.9% | yes |
| 40 | 41.67 | 59.25 | **+4.2%** | yes |
| 60 | 41.67 | 75.68 | **−30.6%** | yes |
| 80 | 41.67 | 93.00 | **−47.9%** | yes |

**Crossover is exactly the cap.** Any pre-escape speed above 41.667 BL/s is reduced by
entering ESCAPE, regardless of direction or strength. 18 of 54 cases already show a
reduction, the lowest at 60 BL/s pre-speed.

### 2.2 The ceiling erases the graded neural response

At pre-escape 40 BL/s, **all nine** direction/strength combinations produce the identical
post-escape speed of 41.6667 BL/s. At 30 BL/s six distinct values still survive
(32.62 to 41.67). So above roughly 30-40 BL/s of cruise the DNp01-derived `strength` and
the DNp01-derived direction asymmetry stop having *any* effect on resulting speed.

This is a more serious defect than the speed reduction itself: the graded descending-neuron
signal is real neural output, and the ceiling discards it.

### 2.3 Escape bouts (30 ticks, impulse on tick 0 only)

| Pre (BL/s) | lat | str | Peak (BL/s) | Heading change | Forward disp. (BL) | Lateral disp. (BL) |
| --- | --- | --- | --- | --- | --- | --- |
| 10 | 1.0 | 1.00 | 38.90 | 108.47 deg | 3.11 | **12.33** |
| 20 | 1.0 | 1.00 | 41.67 | 108.47 deg | 4.33 | **12.43** |
| 40 | 1.0 | 1.00 | 41.67 | 108.47 deg | 5.47 | 11.45 |
| 60 | 1.0 | 1.00 | 41.67 | 108.47 deg | 6.05 | 10.79 |
| 80 | 1.0 | 1.00 | 41.67 | 108.47 deg | 6.38 | **10.35** |
| 10 | 0.0 | 1.00 | 41.67 | −59.89 deg | 14.58 | −0.15 |
| 10 | 1.0 | 0.50 | 22.56 | 48.32 deg | 6.00 | 6.92 |

Two things stand out:

- **Heading change is completely independent of pre-escape speed** (108.47 deg at
  strength 1.0, 48.32 deg at 0.5, identical at every cruise speed). The directional
  channel is unaffected by the ceiling.
- **Lateral displacement degrades as cruise rises**, from 12.43 BL at 20 BL/s to 10.35 BL
  at 80 BL/s, while forward displacement grows. Under the ceiling, a faster fly evades
  *less* sideways — the dimension that actually matters for dodging a paddle — because its
  along-heading momentum dominates and the lateral impulse is clamped away.

## 3. Classification of each escape quantity

Using the requested axes: **A** directly constrained by the existing neural
implementation, **B** accepted human-session behavior, **C** literature-supported,
**D** purely simulator engineering. These are not mutually exclusive.

| Quantity | A | B | C | D | Notes |
| --- | --- | --- | --- | --- | --- |
| Direction of escape (side) | **yes** | yes | yes | — | DNp01 left/right asymmetry; the away-turn sign is an acknowledged decoder convention |
| Graded strength | **yes** | yes | — | — | `min(1, dnp01_total/(2*threshold))`; a real neural quantity |
| Trigger timing / threshold | **yes** | yes | — | partly | calibrated empirically; `policy.escape_threshold` is C provenance, not a biological voltage |
| Direction change magnitude | partly | yes | **yes** | yes | saccade amplitude/rate mapping is R0 class C; literature supports rapid reorientation |
| Delta-v / impulse magnitude | scaled by A | yes | — | **yes** | `fly.escape_impulse = 880` is R0 class **C**: "velocity-increment scale before damping/capping; not E09 takeoff speed" |
| Forward bias 0.35 | — | yes | — | **yes** | R0 class C, "engineered neural-action direction mapping" |
| Absolute translational speed | — | yes at 9-13 BL/s cruise | **no support** | **yes** | no matched measurement fixes an airborne escape speed for ROOM |
| Speed ceiling (41.667 BL/s) | — | not exercised | **no** | **yes** | R0 class C, "physical speed cap, not a species flight maximum" |
| Persistence / refractory 0.4 s | partly | yes | — | yes | refractory is a policy construct |
| Lateral / forward displacement | — | yes | — | **yes** | derived quantities, not parameters |

**Nothing in the escape kinematics is class A in the biological sense, and R0 already says
so.** The only genuinely frozen neural content is the *causal chain* (threshold crossing,
side, graded strength) and the accepted human-session behavior at today's cruise speeds.
The 41.667 BL/s ceiling has no biological standing whatsoever.

## 4. Literature

From the **accepted R0 lock** (unchanged, cited not re-derived):

| ID | Content | Constraint |
| --- | --- | --- |
| E09 | Escape takeoff 0.48 +/- 0.01 m/s, first 2 ms airborne, 3-D COM, mean +/- SEM | R0 states explicitly this is **"not the airborne escape impulse parameter"** |
| E08 | Voluntary takeoff 0.28 +/- 0.02 m/s, same window | takeoff, not cruise or airborne escape |
| E10-E12 | ~90 deg turns in <100 ms; pooled saccade rate 1.37/s in a separate dataset | characteristic turn, not a joint distribution |
| E14 | Escape wing-to-leg interval median 1.00 ms vs voluntary 34.83 ms | preparation interval, not a response latency |
| E15 | Short and long escape sequences exist; no single latency imported | not every threat launch is one giant-fiber reflex |

**Reviewed additionally for this study** (flagged as *not* part of the accepted R0 lock,
and at the access depth noted):

| Source | Access | What it supports |
| --- | --- | --- |
| Muijres, Elzinga, Melis & Dickinson 2014, *Science* 344(6180):172, "Flies Evade Looming Targets by Executing Rapid Visually Directed Banked Turns" | abstract / secondary summaries only; no per-trial velocity table extracted | Airborne escape in *flying* Drosophila is a **rapid visually directed banked turn** — body rotation followed by active counter-rotation, produced by subtle wing changes over a few wingbeats, "substantially faster than steering maneuvers measured previously" |
| Muijres & Dickinson 2017, *Phil. Trans. R. Soc. B* 371:20150388 (PMC4992712), free-flight manoeuvre review | full text read | Characterises escape as **directional** — rotation about axes set by the angular position of the stimulus — and reports bank-to-counter-bank at **~25 ms (about five wingbeats)**. Contains **no** quantitative escape speed table |

Answering the four questions in the brief:

1. **Ordinary free flight versus visually triggered escape flight.** The reviewed sources
   characterise the difference as **reorientation rate and manoeuvre aggressiveness**, not
   as a large increase in absolute translational speed. No source reviewed gives a matched
   cruise-versus-escape speed pair for horizontal free flight.
2. **What characterises escape.** Predominantly **rapid directional maneuver** with high
   angular acceleration, plus stability sacrificed for speed of *reorientation*. Absolute
   speed increase is not the reported defining feature.
3. **Comparability to ROOM.** Poor. E08/E09 are 3-D centre-of-mass speeds in the first
   2 ms after liftoff — a different behavior (takeoff) in a different geometry from ROOM's
   horizontal airborne slice. The banked-turn work is 3-D with roll and counter-roll, which
   the 2-D model cannot represent at all (R0 already states this).
4. **Post-stimulus velocity trajectories.** Not obtained. The 2017 review points to Muijres
   et al. 2014 for empirical performance data, and that paper's per-trial velocity time
   courses were not accessible at abstract depth. **This is a genuine evidence gap**, and it
   is the measurement that would most directly constrain the question.

**Conclusion.** The literature gives **no** support for "escape must exceed cruise in
absolute speed", and equally **no** support for "escape reduces speed". The reduction in
the current model is an artifact with no evidential basis on either side. What the
literature does support is that the *directional* channel is the essential escape content
— and that channel is already unaffected by the ceiling.

## 5. Assessment of the proposed invariant

> "Entering ESCAPE must not reduce the fly's translational speed solely because a legacy
> engineering cap is below the current ecological flight speed."

| Compatibility with | Verdict | Reasoning |
| --- | --- | --- |
| Current neural semantics | **Compatible** | The invariant constrains only the post-impulse clamp. Threshold, side, graded strength, refractory, arbitration and the Retina -> LC4/LPLC2 -> MaleCNS -> DNp01 chain are untouched. It would *restore* graded strength that the ceiling currently discards (section 2.2). |
| M1.8-A acceptance | **Compatible today, by construction** | At the accepted cruise of 9-13 BL/s the invariant is already satisfied except at full strength from ~10 BL/s, where the cap truncates 44.41 to 41.67 BL/s. Any implementation must therefore be checked for bit-identity at the current scale, not assumed inert. |
| Literature | **Not contradicted; not required by it either** | No evidence supports a speed reduction. The invariant is best justified as removing a simulator artifact, not as a biological claim. |
| Numerical stability | **Needs an explicit guard** | Removing the effective ceiling from the escape path requires a separate absolute numerical ceiling, or a fast fly plus a full-strength impulse could reach speeds where the 20 ms tick under-resolves collision sweeps. The existing swept-collision code is robust to large steps, but the guard should be explicit rather than incidental. |

**Caveat on wording.** "Solely because of a legacy cap" is doing real work in that
sentence. Damping toward `baseline_speed` also reduces speed on an escape tick, and that is
a *different* mechanism which the invariant should not silently forbid. Any implementation
must distinguish "reduced by the clamp" from "reduced by damping toward the threat-priority
target". The current data separates them: the uncapped column in section 2.1 still includes
damping.

## 6. Architecture comparison

Renumbered 1-4 to avoid collision with the A/B/C/D evidence classes above.

### Architecture 1 — literal frozen neural cap (the brief's A)

Keep 1000 units/s absolute; constrain ecological speed below it.

- *Scientific interpretation*: treats a Class-C engineering number as a hard behavioral
  boundary. R0 explicitly denies it that status.
- *Engineering*: simplest; zero change.
- *M1.8-A re-acceptance*: not needed.
- *High-speed ecological flight*: caps `room_kinematic_scale` at about 3.21, reaching
  roughly 29-42 BL/s for TRANSIT — still well short of E03's 60-80 BL/s.
- *Failure modes*: B2b cannot approach literature magnitudes; the graded-strength erosion
  of section 2.2 begins inside the reachable range.
- *Complexity*: none.

### Architecture 2 — mapped neural ceiling (the brief's B)

The neural escape cap scales with `room_kinematic_scale`; causal semantics unchanged.

- *Scientific interpretation*: says the ceiling is a unit-system artifact of the ROOM
  mapping, which matches its Class-C status.
- *Engineering*: one multiplication; both caps stay in lockstep so their ratio never
  inverts.
- *M1.8-A re-acceptance*: **probably yes.** At scale 1.0 it is inert, but the accepted
  escape envelope is defined by a number that would now move, so the owner should re-accept
  the semantics even if no behavior changes today.
- *High-speed ecological flight*: fully supported.
- *Failure modes*: the escape *impulse* does not scale, so at high scale the impulse
  becomes a small perturbation relative to cruise (at scale 6.15 the cruise top is about
  2.18x the impulse). The escape would become weak in a way no evidence justifies.
- *Complexity*: low.

### Architecture 3 — delta-v / impulse preservation (the brief's C)

Preserve the accepted impulse structure; do not impose a lower absolute ceiling on an
already-faster fly; keep an independent global numerical safety ceiling.

- *Scientific interpretation*: the best match to both R0 and the reviewed literature.
  Escape is modelled as a graded delta-v plus reorientation, which is what the neural
  output actually encodes, and absolute speed is left as a consequence rather than a
  controlled quantity.
- *Engineering*: the escape clamp becomes `max(pre_escape_speed, neural_cap)` or is
  replaced by the global safety ceiling; the profile cap machinery from
  M1_8_B2B_CAPS.md already supports this.
- *M1.8-A re-acceptance*: **not required if it is bit-identical at current cruise.** That
  must be *proved*, not assumed — see section 5, the 10 BL/s full-strength case is already
  truncated today, so a naive implementation would change accepted behavior.
- *High-speed ecological flight*: fully supported, and section 2.2's graded-response
  erasure disappears.
- *Failure modes*: the impulse still does not scale with the mapping, so escape becomes
  relatively weaker at high cruise unless `escape_impulse` is revisited separately. Needs
  the explicit numerical guard.
- *Complexity*: moderate.

### Architecture 4 — context-relative escape envelope (the brief's D)

Express the escape constraint relative to pre-threat motion rather than an absolute
ceiling.

- *Scientific interpretation*: closest to "escape is a manoeuvre, not a speed", and it
  generalises naturally to the directional channel.
- *Engineering*: the cap becomes state-dependent, so the profile is no longer a pure
  function of context; it needs the pre-threat speed threaded through.
- *M1.8-A re-acceptance*: likely, because escape outcomes become history-dependent in a way
  the accepted sessions did not exercise.
- *High-speed ecological flight*: fully supported.
- *Failure modes*: hardest to reason about and to test; a state-dependent cap can interact
  with the refractory window and with repeated threats; hardest to prove bit-identical.
- *Complexity*: highest.

## 7. Compatibility with frozen M1.8-A

No architecture requires touching the landing pipeline, touchdown, PERCHED, the feeding
overlay, voluntary takeoff, the lifecycle recorder schema or lifecycle/policy isolation.
The perched neural escape takeoff pathway reaches the same `World` escape-impulse code, so
whichever architecture is chosen, the acceptance test must include the M1.8-A
`perched_threat` scenario remaining **bit-identical at the current scale**.

The one live risk is the full-strength case from about 10 BL/s cruise, where today's cap
already truncates 44.41 to 41.67 BL/s. That is inside the accepted human-session regime.
Any change to the escape clamp must therefore be verified bit-identical at scale 1.0 using
`tools/kinematics_diff.py` before it is considered M1.8-A-preserving.

## 8. Recommended technical interpretation, with uncertainty

**Recommendation: Architecture 3**, with the ceiling reinterpreted as a global numerical
safety guard rather than a behavioral bound, and with the escape treated as a graded
delta-v plus reorientation.

Reasons: it matches what R0 already says the parameters are (Class C engineering);
it matches the reviewed literature's characterisation of escape as a manoeuvre rather than
a speed; it removes an artifact that currently destroys real graded neural output; and it
is the only option that can be plausibly landed without reopening M1.8-A, provided
bit-identity at current cruise is demonstrated.

**Uncertainty, stated honestly:**

- The decisive measurement — post-stimulus airborne velocity trajectories in free flight —
  was **not obtained**. The recommendation rests on the absence of contrary evidence plus
  the Class-C status of the parameters, not on a positive measurement.
- Architecture 3 does not resolve the impulse-versus-cruise ratio. At high
  `room_kinematic_scale` a fixed 36.667 BL/s impulse is a small perturbation on cruise.
  Fixing that means revisiting `escape_impulse`, which is explicitly out of scope and
  would reopen M1.8-A.
- The 2-D horizontal model cannot represent banked turns, roll or counter-roll, which the
  literature identifies as the core of airborne escape. Any claim that ROOM's escape
  "matches" fly escape remains unsupportable regardless of which architecture is chosen.
- Whether the current 10 BL/s full-strength truncation should be preserved as accepted
  behavior or treated as the same artifact is a judgement call, and it decides whether
  Architecture 3 can be bit-identical at all.

## 9. Decisions requiring user approval

1. **Is the 41.667 BL/s ceiling behavioral or numerical?** Everything else follows. R0
   already classifies it C; this study finds no evidence for a behavioral reading.
2. **Which architecture (1-4)?** Recommendation is 3; not selected here.
3. **Is the existing full-strength truncation at ~10 BL/s cruise accepted behavior or the
   same artifact?** This determines whether Architecture 3 can be landed bit-identically or
   requires M1.8-A re-acceptance.
4. **Should `escape_impulse` scale with `room_kinematic_scale`?** Out of scope for this
   study and currently forbidden; but leaving it fixed makes escape progressively weaker
   relative to cruise as the mapping grows.
5. **Is the missing post-stimulus velocity-trajectory evidence worth a dedicated
   literature-acquisition pass** before B2b, or is proceeding on Class-C reasoning
   acceptable?
6. **What is the explicit global numerical safety ceiling**, and what test proves it never
   binds in normal play?

Nothing in this document has been implemented. No parameter, config value or runtime
behavior was changed.
