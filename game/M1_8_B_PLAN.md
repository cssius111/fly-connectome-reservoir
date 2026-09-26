# M1.8-B plan: activity budget and context-dependent flight kinematics

Status: **planning only.** Section 2 is decided (see section 2.1); B1 is authorized and
reported separately in [results/game/M1_8_B1.md](../results/game/M1_8_B1.md). B2 and
later stages are not authorized and require a subsequent explicit user request.

Baseline: M1.8-A accepted and committed (`bfbef04`). Biological authority remains the
accepted [M1.8-R0 evidence lock](M1_8_EVIDENCE.md) and
[results/game/M1_8_R0.md](../results/game/M1_8_R0.md). M1.8-B must not retune any frozen
M1.7.1 or M1.8-A system, and must not use flight kinematics to adjust game difficulty.

## 1. Goal and non-goals

Replace the single cruise speed plus eight hard state-speed envelopes with
context-dependent, evidence-classified kinematic distributions, and replace arbitrary
timer expiry with local-evidence-driven bout structure — without changing the landing,
perching, takeoff, neural threat or swatter systems.

Out of scope: RL, personalized learning, olfactory neural circuits, central-complex
navigation, wing aerodynamics, leg biomechanics, circadian/sleep, metabolism, vertical
flight, any change to Retina/LC4/LPLC2/MaleCNS/DNp01, and any change to the
lifecycle/policy information boundary.

## 2. The scale question that must be settled before any speed work

This is the single blocking decision, and R0 open question 2 already flags it. Making it
explicit with numbers:

ROOM uses `body_length_px = 24` logical units, a 3840 x 2160 world (160 x 90 BL), and
`baseline_speed = 216` units/s = **9 BL/s**. Applying R0's nominal 2.5 mm/BL convention
(2-3 mm sensitivity bracket) to the reviewed measurements:

| Quantity | Value | BL/s at 2.5 mm/BL | Bracket (3 mm / 2 mm) |
| --- | --- | --- | --- |
| ROOM cruise | 9 BL/s | 9 | — |
| ROOM TRANSIT envelope | 9-13 BL/s | 9-13 | — |
| ROOM absolute `max_speed` | 1000 units/s | 41.7 | — |
| E03 steady groundspeed | 0.15-0.20 m/s | 60-80 | 50-67 / 75-100 |
| E02 intersaccadic (two backgrounds) | 0.267 / 0.381 m/s | 107 / 152 | 89-127 / 134-191 |
| E06 landing approach at 10 cm | 0.37 m/s | 148 | 123 / 185 |
| E07 speed at first leg contact | 0.071 m/s | 28 | 24 / 36 |
| E05 airspeed near plume | 0.55-0.59 m/s | 220-236 | 183 / 275 |

ROOM is therefore roughly **5-15x slower than the reviewed free-flight measurements in
body-normalized terms**, consistently across cruise, landing approach and contact — and
ROOM's absolute speed ceiling (41.7 BL/s) sits below the lowest literature intersaccadic
estimate. At 2.5 mm/BL the arena is about 0.40 x 0.23 m.

Three honest readings, which M1.8-B must choose between rather than blend:

- **(a) Map literature magnitudes into ROOM through one explicit factor.** Adopt the
  *shape* and *context dependence* of the literature distributions and map their
  magnitudes through a single documented, explicitly phenomenological parameter.
  Simulation time is untouched: the 20 ms tick, MaleCNS temporal dynamics, recorder time
  semantics and the accepted M1.8-A timings all stay exactly as they are. The factor
  acts on ecological/kinematic magnitudes only; it does not redefine one simulated
  second.
- **(b) Confinement is the explanation.** The reviewed assays are not a 160 BL enclosure,
  and a confined fly need not fly at open-arena speeds. This is a genuine confound, not
  an excuse, but R0 provides no matched confined-arena distribution to substitute.
- **(c) Adopt body-normalized literature magnitudes directly.** This multiplies flight
  speed by roughly an order of magnitude, invalidates the accepted M1.8-A landing and
  takeoff timings, and materially changes difficulty. **Not recommended**, and it would
  violate the M1.8-A freeze and the standing instruction not to solve difficulty by
  multiplying cruise speed.

Recommendation: **(a)**.

### 2.1 Decision (accepted)

Reading **(a)** is accepted, with these binding constraints:

- **No universal speed constant.** `real_fly_speed = X` must never be created, and the
  current cruise must not be globally replaced by one literature number. The reviewed
  values keep their experimental context, as M1.8-R0 requires.
- **One explicit mapping parameter**, conceptually `room_kinematic_scale`, rather than
  separate arbitrary multipliers hidden across ecological states. Final naming may be
  improved during B2.
- **Class C — simulator/environment mapping.** It is not a measured biological constant
  and must never be described as one.
- **Its value is not chosen yet**, and it must not be optimized against player hit rate
  or escape rate.
- **Simulation time is not rescaled.** The fixed 20 ms simulation/neural tick, validated
  MaleCNS temporal dynamics, recorder time semantics and the M1.8-A takeoff/landing
  temporal interpretation are all preserved unchanged.

## 3. Context-dependent speed distributions

Replace `ecology.speed_bl_s` (eight uniform `[min, max]` envelopes) with a sampler keyed
on behavioral context, keeping the existing first-order speed relaxation as the actuator.
**No universal speed constant is introduced** (section 2.1).

Kinematic profiles should conceptually distinguish at least EXPLORE, TRANSIT,
odor-guided surge/tracking, ODOR_SEARCH/casting, LAND_APPROACH, TAKEOFF, ALERT and
ESCAPE. Not every label must become a literal enum or an independent distribution;
several may share a parameterized family, and LAND_APPROACH and TAKEOFF are supplied by
the frozen M1.8-A lifecycle rather than re-derived here.

- Sample from a **shaped distribution** (lognormal or gamma, seeded) rather than a
  uniform range, because the reviewed speed data are reported as means with spread, not
  as bounded uniform bands.
- Make context the conditioning variable — visual surround, odor state, proximity to
  boundary, recent saccade — rather than a state label alone. E02 is the one directly
  usable demonstration that intersaccadic speed differs with visual background; its
  aggregation caveat means the two values drive **shape and direction of the effect**,
  not two literal setpoints.
- Preserve the existing rule that WORLD may override an ecological target during neural
  actions; logged envelopes must continue to be distinguishable from applied and actual
  speed. M1.8-A already records requested, applied and actual separately — M1.8-B should
  extend, not bypass, that.
- Keep `LAND_OR_PERCH`-adjacent speeds out of scope entirely: approach and contact speeds
  belong to the frozen M1.8-A lifecycle.

## 4. Acceleration and deceleration

Currently a single `speed_tau_seconds = 0.5` first-order lag governs every transition, so
acceleration is a deterministic consequence of the speed error.

Proposal: introduce separate, bounded accel/decel limits with context-dependent
magnitude, and sample the transition time constant rather than fixing it. R0 supplies no
matched Drosophila acceleration distribution, so **every value here is class B or C** and
must be labelled as such. The useful constraints available are indirect: E10-E12's
approximately 90-degree turns in under 100 ms bound how fast heading can change, and E07
bounds the terminal approach speed the lifecycle already enforces.

Do not add a jerk model, wing aerodynamics or a force-based flight controller.

## 5. Flight-bout and perch-bout structure

M1.8-A already produces the right measurement substrate: `LifecycleMetrics` records
completed perch and flight bouts with explicit left/right censoring, and null medians
mean "no complete bout" rather than zero.

M1.8-B should:

- Model flight bouts and perch bouts as a **two-state alternating renewal structure**,
  with bout durations drawn from seeded hazard functions rather than uniform timers.
- Reuse the M1.8-A voluntary-departure hazard pattern (integrated seeded hazard shaped by
  dwell history and local context) for flight-bout termination, for consistency — without
  modifying the frozen perch-departure hazard itself.
- Treat the airborne/perched ratio as an **output to be measured and reported**, never as
  a target to be tuned. R0 is explicit that no evidence fixes a natural airborne-time
  percentage for ROOM, so any budget figure stays a simulator metric.

## 6. EXPLORE, TRANSIT and odor-guided flight

Keep the R0 distinction: EXPLORE and TRANSIT are **flight intent labels**;
ODOR_TRACK/SURGE/SEARCH are **navigation modules**; ALERT/ESCAPE remain an orthogonal
neural channel. Avoid proliferating timer states — prefer bounded continuous variables
(motivation, confidence, readiness) as R0 recommends.

Concretely:

- EXPLORE vs TRANSIT should be separated by *evidence* (local visual structure, boundary
  proximity, odor history) rather than by `explore_duration_seconds` / 
  `transit_duration_seconds` uniform draws.
- Odor-guided flight should finally consume the local odor derivative and bilateral
  difference that R0 found are computed but unused.
- E19 (still-air search, approximately 60-degree turns at 3-4 Hz) is a *different context*
  from wind-based casting and must not be applied to ordinary flight.
- Wind sensing should become uncertainty-aware (R0 open question 5): the current ideal
  local ambient-flow estimate should carry a reliability term, with a defined strategy
  when wind is unreliable.

## 7. Reducing arbitrary timer-driven behavior

R0 names the specific offenders. Target list for M1.8-B, all currently class B/C/D:

| Parameter | Value | Replace with |
| --- | --- | --- |
| `explore_duration_seconds` | [3, 7] s | evidence-gated intent transition |
| `transit_duration_seconds` | [2, 5] s | evidence-gated intent transition |
| `odor_bout_seconds` | 8 s forced expiry | odor-encounter history and loss hazard |
| `search_seconds` | 6 s | encounter-driven termination |
| `relocation_seconds` | 4 s odor ignoring | refractory only, not a behavior driver |
| `search_period_seconds` | 3.6 s sinusoid | sampled turn sequence, not a fixed oscillator |
| `fly.curvature.periods_seconds` | 7 / 13 s | sampled drift, not two fixed periods |

Minimum dwell and refractory timers may remain to prevent chatter, but a timer alone must
never be presented as biological decision making. Every retained timer should be labelled
C with that justification.

## 8. Preserving discrete saccades and local sensory constraints

Non-negotiable invariants for M1.8-B:

- Discrete saccadic course changes with quieter intersaccadic flight are **retained**.
  The existing three-component interval mixture (short / ordinary / long with
  probabilities) is already the right structure; M1.8-B may condition it on context but
  must not replace saccades with continuous steering.
- E10-E12's characteristic turn magnitude and pooled rate of 1.37/s are **not a joint
  distribution and not a periodic scheduler**. Saccade amplitude, duration and interval
  must not be fused into one fabricated joint law (R0 open question 6).
- The policy observation whitelist (`neural`, `motion`, `behavior_state`, `history`) is
  unchanged. No food coordinates, surface identity, pointer, click state or world vector
  enters any controller.
- The Retina bottleneck, restricted `MotionState`, frozen connectome and fixed baseline
  policy are unchanged. No learning.
- All M1.8-A frozen systems are untouched; M1.8-B is a kinematics layer beneath the
  existing intent and lifecycle arbitration.

## 9. Parameter evidence policy

Continue the M1.8-A table format: parameter, value, module, class, evidence, reason.
Classes A (direct matched measurement), B (literature-inspired phenomenology), C
(engineering/game). Expect **no class A parameters again** unless the scale question in
section 2 is resolved in a way that makes a measurement directly transferable — and say
so plainly rather than promoting B values.

Each adopted distribution must record: the source evidence ID, the raw reported statistic
and its error type, the assumed mm/BL conversion, the applied `room_kinematic_scale`
mapping, and why the distribution family was chosen.

## 10. Evaluating behavior without tuning for difficulty

This is the discipline that keeps M1.8-B honest.

- Define the evaluation metrics **before** implementation: speed distribution by context,
  accel/decel distributions, saccade interval and amplitude distributions, flight-bout and
  perch-bout survival curves, and airborne/perched/feeding fractions — all alive-only and
  censoring-aware, extending the existing `LifecycleMetrics` report.
- Add a `tools/kinematics_sanity.py` producing deterministic seeded distributions plus
  comparison plots against the cited references, in the style of `lifecycle_sanity.py`.
- **Hit rate, escape rate and time-to-first-hit are reported but explicitly excluded as
  optimization targets.** If a change improves behavioral realism and makes the fly easier
  or harder to swat, that is an outcome to record, not a reason to adjust a parameter.
- Any parameter changed after seeing a difficulty metric must be documented as such, with
  the justification, so the provenance of tuning pressure stays visible.
- Use recorded human sessions for distribution comparison only. Recordings are private and
  git-ignored; do not commit them.

## 11. Suggested sequencing

1. **B0 — decided.** See section 2.1: reading (a), one class-C `room_kinematic_scale`
   mapping on magnitudes only, value not yet chosen, simulation time unchanged.
2. **B1 — authorized.** Kinematic interface refactor: separate behavioral context ->
   kinematic profile request -> kinematic executor -> physics, with no behavior change.
   Effective values are exactly the current accepted values and no new stochastic draws
   are introduced. Acceptance is bit-identical replay, not a tolerance. Reported in
   [results/game/M1_8_B1.md](../results/game/M1_8_B1.md).
3. **B2** — context-dependent speed and accel/decel distributions, plus
   `tools/kinematics_sanity.py` and the evaluation metrics.
4. **B3** — bout structure and timer removal (section 7), one parameter group at a time.
5. **B4** — odor-guided flight modules and wind uncertainty.
6. **B5** — validation report, human playtest, acceptance.

B1 is deliberately a no-op refactor so that later behavioral changes are attributable.

## 12. Risks

- **Difficulty drift.** Any speed change alters swatter difficulty. Mitigated by section
  10 and by the standing instruction not to tune for difficulty.
- **Breaking the M1.8-A freeze by accident.** Landing approach, contact and takeoff speeds
  are lifecycle-owned. The kinematics layer must not be applied while the lifecycle owns
  the actuator; the existing `applied_profile` mechanism already identifies those ticks.
- **Replay determinism.** New seeded samplers need their own RNG stream offsets, as
  `lifecycle.py` does, or exact replay breaks.
- **Recorder schema churn.** Adding kinematic fields implies schema 5; `replay.py`
  currently accepts 3 and 4 and would need extending.
- **Overfitting to one human session.** Two accepted playtests are not a behavioral
  dataset.

## 13. Decisions needed from the user before B2

1. ~~Which reading in section 2?~~ **Answered: (a)**, under the constraints in section
   2.1. The remaining sub-decision is the eventual numeric value of
   `room_kinematic_scale`, which is deliberately deferred past B1.
2. Should the arena stay 160 x 90 BL, or is a physically larger room intended later? This
   changes what "activity budget" even means.
3. Is a recorder schema bump to 5 acceptable, given replay compatibility work?
4. Should M1.8-B target parity with a specific published assay, or explicitly remain
   phenomenological with cited inspiration?
