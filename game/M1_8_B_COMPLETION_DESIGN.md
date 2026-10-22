# M1.8-B completion: preregistered design of stages B2c to B5

Status: **preregistered, then implemented and validated** (2026-10-22; deviations are listed in
the results report, section 9) and **accepted by the user on 2026-10-22**. Written on
2026-10-21 under the user's authorization recorded in
[M1_8_B_PLAN.md](M1_8_B_PLAN.md) section 14, before any of the stages below changed code.
Results are reported in [results/game/M1_8_B_COMPLETION.md](../results/game/M1_8_B_COMPLETION.md).

Baseline: the accepted runtime `feature/m1-8-b3a` @ `6b43c0f` (ROOM `config_version` 19).

## 1. Rules common to every stage

**Scope.** Each stage changes only ecological locomotion or ecological decisions. Unchanged
throughout: the Retina bottleneck, LC4/LPLC2 encoder, frozen MaleCNS, the N4B1C decoder,
the N4B5R geometry, the fixed policy and its observation whitelist, the M1.7.1 swatter,
the M1.8-A lifecycle (landing, contact, perching, feeding, both takeoff paths and their
threat input), the B3a ecology threat input, the three 1000 units/s caps,
`room_kinematic_scale` = 1.0, the arena, recorder schema 4, and **TRANSIT speed** (its
9-13 BL/s envelope and its legacy speed profile). No learning. Nothing is tuned toward hit
rate, survival or escape rate.

**Hold the magnitude, replace the mechanism.** No reviewed source supplies a matched
distribution for any quantity changed here (game/M1_8_EVIDENCE.md), so every new parameter
is class B or C. Where a stage replaces a fixed timer, oscillator or deterministic profile,
the replacement is parameterized so that, under the conditions in which the old mechanism
applied, its mean equals the accepted value: the stage changes the model, not the
magnitude. New evidence-gated modulations get explicit bounds and an ablation value.

**Configuration gating.** Every change is selected by a new ROOM configuration block or key.
Without it the accepted code path runs unchanged, so LAB, GAME, older ROOM configurations and
recordings replay exactly. Each stage bumps `config_version` by one and writes its own
calibration transfer record with `tools/m1_8_b_stage_record.py`; no recalibration is needed
because fixed-fly-v2 disables ecology, fly motion and collisions.

**Random streams.** Each new stochastic element draws from its own seeded stream, so no
accepted stream changes its call order:

| Stream | Offset | Stage |
| --- | --- | --- |
| ODOR_SEARCH speed | +36263 | B2d |
| RECOVER speed | +42061 | B2d |
| speed relaxation rate | +47933 | B2e |
| odor-history hazards | +53113 | B3b |
| EXPLORE / TRANSIT hazards | +59011 | B3c |
| casting half-periods | +64747 | B3d |
| curvature half-periods | +70001 | B3d |

They are distinct from the accepted offsets (world +0, brain noise +977, flight +3907, room
+6011, ecology +7013, spawn +8191, lifecycle +18001, EXPLORE speed +24593, ODOR_TRACK speed
+30011).

**Checks for every stage** (failure of any one fails the stage):

1. *Code alone is bit-identical.* With the stage's code and the previous configuration, all
   seven `tools/kinematics_trace.py` scenarios and every random stream equal the previous
   stage's capture (4 Numba threads).
2. *The first divergence is the intended one.* With the new configuration each diverging
   scenario diverges first where the stage says it should; `room_no_ecology`, `game_preset`
   and `lab_preset` stay bit-identical.
3. *Unit tests* for the new mechanism, its gating, its bounds and its provenance record.
4. *Metrics.* `tools/kinematics_sanity.py` (B2c) on six seeds, compared with the previous
   stage. The stage's hard checks (below) must hold; every other metric is reported, not
   targeted.
5. *Pathology screen.* Against the previous stage, a stage fails if, pooled over the six
   seeds: any ecological state other than the stage's own target has a median completed
   episode below 0.5 s where it was at least 1 s (chatter); the visited-cell share falls
   below half; the lifecycle records no touchdown where it recorded some; or the perched
   share more than doubles. These are failure screens, not targets.
6. *Paired free flight.* `tools/paired_free_flight_check.py` on seeds 9201-9280 (180 s, no
   player, one Numba thread), candidate against the previous stage. The previous stage's
   arm is reused when check 1 holds. Criterion: **category B below 0.1/min at 95 %**; A, C
   and D reported.
7. *Frozen systems.* Full unit suite; M1.8-A lifecycle scenarios replay (event sets
   reported); recorder exact replay at schema 4; escape/cruise study; M1.7.1 swatter
   fixtures; calibration resolves 1.45 through the new record.

**Failure handling.** A stage that fails is not adopted: its configuration change is
reverted, the failure is reported, and later stages proceed on the last adopted
configuration where they do not depend on it. Nothing is retuned to make a failed stage
pass.

**Final check (B5).** One paired check on fresh seeds **9301-9380** between the accepted B3a
configuration and the final configuration, the metrics on both, the local Windows checks,
and the single human playtest.

## 2. B2c: evaluation metrics (no behaviour change)

`tools/kinematics_sanity.py` fixes the metrics of plan section 10 before any behaviour
changes. Six seeds (101, 255, 4242, 7, 1729, 31337), 180 s each, no player, pointer parked.
Per run and pooled: ecological occupancy (alive ticks) and its share among ecology-driven
ticks; lifecycle modes and fractions; speed by state on ecology-driven airborne ticks;
acceleration and deceleration magnitudes by state; settling time to within 0.5 BL/s of the
applied target after an episode starts; accepted actuator turns by kind, amplitude and rate;
intervals between spontaneous turns; drift yaw rate between pulses; completed and censored
ecological episodes and every transition; odor detection share, encounter rate, upwind
heading share (within 45 degrees) while tracking, touchdowns on food and elsewhere; flight
and perch bouts; visited share of a 10 BL grid and time near a wall; policy escape onsets.
The baseline is measured on the accepted B3a configuration. Hard check: none (no behaviour
change); the tool is deterministic for a fixed seed and thread count.

## 3. B2d: ODOR_SEARCH and RECOVER speed sampling

The B2b-ii/iii method for the last two ecological contexts whose speed still follows the
shared 8 s sinusoid (TRANSIT is locked; ALERT, ESCAPE and LAND_OR_PERCH are neural or
lifecycle paths). One draw per ecological episode, from its own stream:

| Parameter | Units | Class | Value | Reason |
| --- | --- | --- | --- | --- |
| `kinematics.odor_search_speed_bl_s` | BL/s | B (shape), C (support) | triangular_symmetric 4.0 / 5.5 / 7.0 | support and mean held at the accepted ODOR_SEARCH envelope |
| `kinematics.recover_speed_bl_s` | BL/s | B (shape), C (support) | triangular_symmetric 5.0 / 6.5 / 8.0 | support and mean held at the accepted RECOVER envelope |

Evidence: none matched (E02, E03 and E05 are different quantities and contexts); the shape
is phenomenological, as in B2b-ii. First divergence: the first ecology-driven ODOR_SEARCH or
RECOVER tick. Hard checks: every draw lies in its support; 200,000 offline draws give mean
and standard deviation within 0.01 BL/s of the triangular values; EXPLORE and ODOR_TRACK
draws are unchanged for the same seed.

## 4. B2e: sampled speed-transition time constant

Today every ecological speed change relaxes at one fixed rate, `fly.damping_per_second` =
3.0 /s (time constant 0.33 s), so acceleration is a deterministic function of the speed
error. B2e draws the relaxation rate once per ecological episode of the four sampled
contexts (EXPLORE, ODOR_TRACK, ODOR_SEARCH, RECOVER), from its own stream; the executor law
is unchanged.

| Parameter | Units | Class | Value | Bounds / sensitivity | Reason |
| --- | --- | --- | --- | --- | --- |
| `kinematics.speed_relaxation_per_second` | 1/s | C | triangular_symmetric 2.0 / 3.0 / 4.0 | support fixed; mean held at the accepted 3.0 | plan section 4: sample the transition time constant rather than fix it |

Unchanged: the neural-priority profile, the lifecycle profiles and TRANSIT keep 3.0 /s, so
escape impulses and threat-priority cruise decay exactly as before while the policy is
active. Separate acceleration and deceleration limits are **not** introduced: no evidence
supports an asymmetry or a magnitude, and an unbinding limit would add nothing. First
divergence: the first ecology-driven tick of a sampled context whose drawn rate is not 3.0.
Hard checks: every draw in [2, 4]; with the rate pinned to 3.0 the stage is bit-identical
to B2d; settling time by state is reported against B2d.

## 5. B3b: odor timers replaced by encounter history

Three timers go: the 8 s forced end of ODOR_TRACK (`odor_bout_seconds`), the 6 s end of
ODOR_SEARCH (`search_seconds`) and the 4 s odor-ignoring relocation that follows a forced
end (`relocation_seconds`). In the B3a baseline (B2c metrics) 17 of 58 completed ODOR_TRACK
episodes end at the 8 s timer and 23 of 27 ODOR_SEARCH episodes at the 6 s timer.

Replacement (`ecology.odor_history` block):

- An **encounter history** H in [0, 1] rises toward 1 while odor is detected (time constant
  `build_seconds`) and decays toward 0 otherwise (`recovery_seconds`). E17: later encounters
  elicit weaker upwind responses; no memory horizon is locked, so both constants are class C.
- **Weaker upwind response with history:** the ODOR_TRACK upwind steering gain is multiplied
  by 1 - `upwind_attenuation` x H.
- **Abandonment hazard:** while in ODOR_TRACK the ecology leaves the plume at rate
  H / `abandon_seconds` per second (one draw per tick from the B3b stream). Leaving enters
  TRANSIT with a `refractory_seconds` odor-ignoring refractory that only prevents immediate
  re-entry chatter.
- **Search ends by encounter or by giving up:** reacquisition still returns to ODOR_TRACK;
  otherwise, after a `search_min_seconds` minimum, ODOR_SEARCH gives up at a constant rate
  1 / `search_give_up_seconds` and enters EXPLORE.

| Parameter | Units | Class | Value | Bounds / sensitivity | Reason |
| --- | --- | --- | --- | --- | --- |
| `build_seconds` | s | C | 10.0 | 5-20 | with `abandon_seconds` 3.0, a naive fly in continuous odor tracks for 8.08 s on average, the accepted 8 s |
| `recovery_seconds` | s | C | 30.0 | 15-60 | history outlasts one plume contact; E17 locks no horizon |
| `upwind_attenuation` | 1 | C | 0.5 | 0 (ablation) - 0.75 | E17 direction only; 0 is the history-ablated control |
| `abandon_seconds` | s | C | 3.0 | 2-4.5 | see `build_seconds` |
| `refractory_seconds` | s | C | 1.0 | 0.5-2 | anti-chatter refractory, not a behaviour driver (plan section 7) |
| `search_min_seconds` | s | C | 1.0 | 0.5-2 | casting starts about 0.45 s after loss (E16); a search must last at least one cast |
| `search_give_up_seconds` | s | C | 5.0 | 2.5-10 | mean search 6.0 s, the accepted `search_seconds` |

The old keys stay in the configuration because the ecology's own landing path (disabled in
ROOM, where the lifecycle lands) still reads `relocation_seconds`; under `odor_history` the
ROOM ecology no longer reads `odor_bout_seconds` or `search_seconds`. Sensitivity: the
metrics on three seeds at `upwind_attenuation` 0 and 0.75 and at `abandon_seconds` 2 and 4.5,
reported. Hard checks: no ODOR_TRACK episode ends at a fixed 8.00 s and no ODOR_SEARCH
episode at a fixed 6.00 s unless by coincidence of a hazard draw (reported as a count of
episodes within one tick of those values); H stays in [0, 1]; with the block removed the
stage is bit-identical to B2e. First divergence: the first tick on which H changes the
upwind gain or a hazard fires, which is the first ODOR_TRACK tick after an odor detection.

## 6. B3c: EXPLORE and TRANSIT dwell timers replaced by evidence-gated hazards

Today EXPLORE lasts U[3, 7] s and TRANSIT U[2, 5] s, then they alternate. B3c replaces both
uniform timers with a minimum dwell followed by a hazard conditioned on local visual
structure (`ecology.intent_hazards` block). Local structure is u = min(1, (visual_left +
visual_right + landing_affordance) / `structure_reference`), built only from the existing
EcologicalSense fields. Rich structure prolongs EXPLORE and ends TRANSIT sooner:

- EXPLORE -> TRANSIT at rate (1 - beta u) / `explore_hazard_seconds` after `min_dwell_seconds`;
- TRANSIT -> EXPLORE at rate (1 + beta u) / `transit_hazard_seconds` after `min_dwell_seconds`.

| Parameter | Units | Class | Value | Bounds / sensitivity | Reason |
| --- | --- | --- | --- | --- | --- |
| `min_dwell_seconds` | s | C | 1.0 | 0.5-2 | anti-chatter minimum dwell (plan section 7) |
| `explore_hazard_seconds` | s | C | 4.0 | fixed by the mean | with no structure the mean EXPLORE episode is 5.0 s, the accepted U[3, 7] mean |
| `transit_hazard_seconds` | s | C | 2.5 | fixed by the mean | with no structure the mean TRANSIT episode is 3.5 s, the accepted U[2, 5] mean |
| `structure_reference` | 1 | C | 0.2 | 0.1-0.4 | the summed occupancy of a 95-unit column at about 200 units |
| `structure_gain` (beta) | 1 | C | 0.5 | 0 (ablation) - 1.0 | R0: EXPLORE vs TRANSIT separated by local visual structure; no magnitude locked |

TRANSIT speed is untouched; only when it starts and how long it lasts change, as the user
allowed. Durations become more variable (exponential tails instead of bounded uniforms).
Sensitivity: the metrics on three seeds at beta 0 and 1.0. Hard checks: no EXPLORE or TRANSIT
episode shorter than the minimum dwell unless ended by a threat, odor or landing; with
the block removed the stage is bit-identical to B3b. First divergence: the first EXPLORE or
TRANSIT tick at which the accepted dwell would have drawn its uniform duration.

## 7. B3d: fixed oscillators replaced by resampled-period oscillators

Two fixed oscillators remain: the ODOR_SEARCH casting offset A sin(2 pi t / 3.6 s + phase)
and the airborne drift turn sum of 0.16 sin(2 pi t / 7 s) and 0.06 sin(2 pi t / 13 s). B3d
keeps their amplitudes and replaces each fixed period with a phase oscillator whose
half-period is redrawn at every half-cycle, so the course is a sampled turn sequence rather
than a metronome.

| Parameter | Units | Class | Value | Reason |
| --- | --- | --- | --- | --- |
| `ecology.search_half_period_seconds` | s | C | triangular_symmetric 1.2 / 1.8 / 2.4 | mean half-period 1.8 s, the accepted 3.6 s period |
| `fly.curvature.period_sampling` | 1 | C | relative half-width 0.5 (each half-period triangular on 0.5-1.5 times the accepted half-period) | accepted mean periods 7 s and 13 s |

The casting stays centred on upwind with the accepted 1.05 rad amplitude (R0 notes it is not
a crosswind cast; changing that is not part of B3d). Hard checks: amplitudes unchanged;
every half-period within its support; with both keys removed the stage is bit-identical to
B3c. First divergence: the first airborne tick (drift) and the first ODOR_SEARCH tick
(casting).

## 8. B4a: the odor derivative and the bilateral difference

`odor_rate` and `odor_bilateral` are computed by the projector and never used. B4a adds two
bounded terms to ODOR_TRACK steering (`ecology.odor_cues` block); relative quantities divide
by max(odor, `odor_on`):

- **Bilateral steering** (E18: bilateral input contributes to tracking; no transferable gain):
  `bilateral_gain` x tanh(relative bilateral / `bilateral_scale`), toward the stronger side.
- **Rate-modulated upwind gain** (E16: surge on encounter, cast on loss): the upwind gain is
  multiplied by 1 + `rate_gain` x tanh(relative rate / `rate_scale`), stronger while
  concentration rises and weaker while it falls.

| Parameter | Units | Class | Value | Bounds / sensitivity | Reason |
| --- | --- | --- | --- | --- | --- |
| `bilateral_gain` | rad/s | C | 0.3 | 0 (ablation) - 0.6 | at most a third of the 0.9 rad/s steering cap |
| `bilateral_scale` | 1 | C | 0.05 | fixed | of the order of the relative difference one plume width off-centre (0.06-0.12 with 12-unit antenna spacing) |
| `rate_gain` | 1 | C | 0.25 | 0 (ablation) - 0.5 | bounded modulation, never reversing the upwind response |
| `rate_scale` | 1/s | C | 2.0 | fixed | relative rate at which the modulation reaches 76 % |

The steering cap and the ESCAPE/ALERT override still apply. Sensitivity: the metrics on
three seeds with each gain at 0 and at its upper bound. Hard checks: with both gains 0 the
stage is bit-identical to B3d; steering stays within the cap. First divergence: the first
ODOR_TRACK tick.

## 9. B4b: wind reliability and a still-air strategy

The wind signal is an ideal ambient-flow estimate with no reliability (R0 open question 9).
B4b adds a reliability r = clip((|w| - `unreliable_below`) / (`reliable_above` -
`unreliable_below`), 0, 1) of the sensed wind speed (`ecology.wind_reliability` block). The
upwind steering in ODOR_TRACK and ODOR_SEARCH is scaled by r. When r is below 0.5, ODOR_SEARCH
casts around the heading held at odor loss instead of around upwind (E19: wind reliability
gates the search strategy; its still-air 60-degree turns at 3-4 Hz cannot be produced within
the 0.9 rad/s ecological steering cap and are not imported as a rate).

| Parameter | Units | Class | Value | Reason |
| --- | --- | --- | --- | --- |
| `unreliable_below` | units/s | C | 5.0 | about 0.2 BL/s, far below ROOM wind |
| `reliable_above` | units/s | C | 20.0 | below ROOM's minimum wind of 38.25 units/s |

ROOM's wind never falls below 38.25 units/s, so r = 1 throughout and **ROOM behaviour is
bit-identical to B4a by construction**; the stage adds the strategy for configurations with
weak wind. Checks: the ROOM traces equal B4a's (the paired check is therefore not re-run);
unit tests of r and of the still-air branch; a diagnostic low-wind control (wind 3 units/s,
not a runtime configuration) runs the metrics on three seeds and reports the still-air
search.

## 10. B5: combined validation and the human playtest

The final paired check on fresh seeds 9301-9380 (B3a configuration against the final one),
the metrics on both, the frozen-system checks, the local Windows checks (protected files,
`verify_results.py`, the suite, the swatter on the M1.7.1 recording) and one human playtest.
Acceptance is the user's decision.

## 11. Not part of this work

TRANSIT speed; flight-bout termination (owned by the frozen M1.8-A lifecycle); any change to
the policy, decoder, geometry, swatter, lifecycle, caps, scale, arena or recorder schema;
crosswind casting; any learning.
