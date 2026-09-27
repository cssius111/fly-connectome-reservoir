# M1.8-A local locomotor lifecycle

Status: human-accepted and frozen; see [validation and acceptance](../results/game/M1_8_A.md).
Biological authority:
[M1.8-R0 evidence baseline](M1_8_EVIDENCE.md). The neural reference organism is
**adult male Drosophila melanogaster**, because the connectivity is MaleCNS.
The behavioral papers do not all study males. Ecological motivation, landing,
perching, feeding and voluntary takeoff below are phenomenological controllers,
not validated olfactory, landing, central-complex or motivational neural circuits.

The runtime remains a MaleCNS-derived graph: `sensory_input=false` removes
incoming sensory-neuron edges. Original dataset: 25,582,938 connections; runtime:
approximately 25,088,107. Retina feeds engineered LC4/LPLC2 feature stimulation,
then the frozen graph, then DNp01/DNa02 readouts and the fixed policy. There is
no learning, complete eye/image pipeline or claim that the brain learned to land.

## Control architecture and information boundary

Each fixed 20-ms tick updates the real visual/neural threat pathway first.
Ecological sensing and motivation continue while the fly is alive, including
while perched. Ordinary ecological commands control airborne exploration.
The separate local lifecycle arbitrates physical approach and support:

```text
AIRBORNE -> LAND_APPROACH (ORIENT -> DECELERATE -> LEG_COMMIT)
         -> physical swept contact -> TOUCHDOWN -> PERCHED [optional FEEDING]
         -> TAKEOFF_VOLUNTARY -> AIRBORNE
PERCHED + nonzero neural Action.escape -> TAKEOFF_ESCAPE -> AIRBORNE/ESCAPE
LAND_APPROACH + neural ESCAPE -> abort -> neural airborne escape executor
LAND_APPROACH + visual cue loss/recession/timeout -> abort/fly-by -> AIRBORNE
```

Orientation and deceleration can overlap; leg commitment is a separate gate.
Elapsed time never guarantees contact. Approaches can lose the visual patch,
pass too fast or obliquely, or be interrupted by real neural escape. ALERT alone
neither launches a perched fly nor fabricates an escape. It suppresses new
approach eligibility and voluntary departure; an existing approach continues.

`LandingSense` contains only affordance, retinal bearing, angular extent,
angular expansion, local odor, support contact and food-contact affordance.
The strongest forward visible eligible disk is selected inside WORLD. Its
silhouette diameter is `theta = 2 asin(radius/distance)`. The analytic derivative
uses radial relative velocity: `theta_dot = 2*r*v_closing/(d*sqrt(d*d-r*r))`.
Rotation changes bearing and visibility but not a disk's extent. The legacy
`EcologicalSense.surface_expansion` remains an affordance derivative and is
**not** reused as true angular expansion. Inside a disk the angular extent
saturates at pi and expansion is zero. This ideal geometric projection has no
occlusion reconstruction, noisy depth estimator or identified visual circuit.

No source coordinates, surface identity, nearest-surface world vector,
destination or mouse/swatter state enters this controller. Its MotionState is
an explicit local copy with translational speeds converted to BL/s; neural
MotionState and the policy observation whitelist are unchanged. The ecological
controller's old LAND_OR_PERCH timer is disabled only when lifecycle is enabled.

With `q = theta/commit_angle + max(0,theta_dot)*expansion_braking_seconds`,
requested approach speed is `max(contact_speed, measured_speed/(1+q*q))`.
Body-relative visual bearing supplies bounded orientation. WORLD exponentially
relaxes velocity toward that drive. Curvature and spontaneous saccades are
suspended during controlled approach and stationary contact. Actual attachment
requires leg commitment, low speed and an outside-to-inside swept intersection
with a valid landable surface. No target-position snap or already-overlapping
attachment is permitted. The small residual contact velocity is constrained to
zero at the intersection; detailed leg compliance is not modeled. Pose and
heading are then fixed. The ordinary strike collision path still runs, so a
perched fly remains hittable and visibly alive until a genuine hit.

Voluntary departure uses a seeded unit-exponential hazard threshold. After the
minimum perch dwell, integrated hazard grows at:

```text
rate = departure_rate * (1 + dwell/dwell_history) / (1 + odor_persistence*odor)
rate *= feeding_departure_fraction  # only with food contact and enough odor
```

Only CALM ticks accrue hazard; elapsed dwell still advances. Changing local
odor/feeding history changes departure with the same seed and dwell. No hunger,
energy, ingestion amount, sleep or calibrated meal-duration model is implied.
Feeding is a minimal labeled contact overlay, not a verified ingestion event.

Voluntary launch initializes 6 BL/s along the retained contact heading for one
tick. Escape launch detaches then uses the unchanged direction-normalized
`escape_impulse * Action.strength` path, with existing damping/cap and neural
saccade. The two causes and applied profiles are recorded separately. The first
2-ms 3-D takeoff values in R0 E08/E09 are **not** copied into 2-D cruise or launch
constants. **Sub-timestep takeoff dynamics are not explicitly resolved.**
Ordinary airborne speed envelopes, swatter physics and LAB/GAME are unchanged.
The horizontal model treats takeoff as lifting out of support; no vertical wing
or leg trajectory is computed. A launch can therefore fly across the non-solid
landing disk after detachment.

## Complete new parameter table

A = directly measured matching quantity/context; B = literature-inspired but
quantitatively phenomenological; C = engineering/game choice. No new number is
class A: even the approximate 60-degree leg cue is transferred to ideal disk
geometry and hence remains B. Evidence IDs refer to the accepted R0 document.
All paths below are under `lifecycle` in `game_room_config.json`.

| Parameter | Value | Module | Class | Evidence and reason for ROOM value |
| --- | --- | --- | --- | --- |
| enabled | true | Session/WORLD | C | Enable only ROOM lifecycle; legacy presets unchanged. |
| affordance_on | 0.075 | lifecycle | B | E13 local visual orientation; ideal contrast/extent threshold, phenomenological. |
| orientation_limit_degrees | 65 | lifecycle | B | E13 orientation; forward eligibility window, phenomenological. |
| orientation_dwell_seconds | 0.12 | lifecycle | C | Debounce transient cues; not sensory latency. |
| orientation_gain | 2 /s | lifecycle | B | E13 orientation; bounded proportional bearing steering, phenomenological. |
| orientation_cap_rad_s | 1.5 | lifecycle | C | Smooth alignment cap; no measured turn distribution claimed. |
| commit_extent_degrees | 60 | lifecycle | B | E13 approximate leg cue inspires this gate; geometry/context differ. |
| commit_bearing_degrees | 20 | lifecycle | B | E13 alignment before support; phenomenological tolerance. |
| commit_speed_bl_s | 6 | lifecycle | B | E07/E13 motivate slowing before contact; value fits existing ROOM speed scale, not measured contact speed. |
| expansion_braking_seconds | 0.35 | lifecycle | B | E13 size plus expansion control; phenomenological gain. |
| contact_speed_bl_s | 1.5 | lifecycle | B | E07/E13 controlled slow approach; lower legacy landing envelope, not E07 numeric transfer. |
| touchdown_max_speed_bl_s | 3 | WORLD | C | Capture-speed guard, allowing fast approaches to fly by. |
| approach_velocity_tau_seconds | 0.18 | WORLD | C | Smooth numerical actuator response; not a measured neural delay. |
| cue_loss_seconds | 0.16 | lifecycle | C | Debounce brief recession/visibility loss before abort. |
| approach_timeout_seconds | 10 | lifecycle | C | Safety escape from stalled approach; cannot cause landing. |
| retry_seconds | 4 | lifecycle | C | Prevent immediate repeated capture after abort/launch. |
| minimum_perch_seconds | 2 | lifecycle | C | Minimal meaningful support dwell, not a natural rest-duration estimate. |
| departure_rate_per_second | 0.12 | lifecycle | B | R0 motivated departure concept; phenomenological hazard. |
| dwell_history_seconds | 12 | lifecycle | B | R0 perch/departure history; phenomenological scale. |
| odor_persistence_gain | 0.5 | lifecycle | B | E17/E20 context dependence; phenomenological odor modulation. |
| feeding_odor_on | 0.1 | lifecycle | B | E20 local food interaction; existing arbitrary odor scale, not receptor threshold. |
| feeding_departure_fraction | 0.45 | lifecycle | B | E20 persistence during food contact; phenomenological, not measured feeding duration. |
| voluntary_launch_speed_bl_s | 6 | WORLD | B | E08/E09 distinguish launch causes; existing EXPLORE scale, not first-2-ms 3-D measurement. |

Additional implementation constants are explicit: lifecycle RNG offset 18001
and unit-exponential sampling scale 1 are C stream isolation and B hazard-model
choices respectively; squared braking load is B, a phenomenological control
law; angular/contrast normalization, tiny denominator/intersection tolerances
(1e-6, 1e-7, 1e-9, 1e-18) are C numerical safeguards. Surface IDs `surface-N`
are C ordered scene identifiers held only in WORLD/recordings. Food contact
uses source surface 0. One-tick TOUCHDOWN/TAKEOFF labels are C event resolution,
not measured phase durations. Narrower folded wings, the green perch ring and
the amber feeding ring/label are C presentation cues, not anatomical measurements
or a feeding animation. Config version 10,
recording schema 4 and calibration file paths are C provenance metadata.

## Recorder, metrics and compatibility

Enabled ROOM recordings use schema 4; other presets and `--no-ecology` retain
schema 3. `lifecycle` adds mode, phase, commitment, contact/airborne state,
generic contact surface ID, feeding, reason, local pre-step observations,
motivation/hazard, requested and actually applied kinematic profiles, and events.
Approach onset/commit/abort, touchdown, perch start/end, feed start/end and both
launch causes are emitted into events.jsonl. Launch events retain the previous
contact ID. Coordinates and contact pose remain in WORLD/debug fields, never
policy_observations.jsonl. Death ends feed/perch events once; later dead ticks
have no new lifecycle events. Restart/quit right-censors unfinished bouts.

Alive-post-step simulator metrics report airborne/perched/feeding fractions,
approaches, commitments, touchdowns, aborts, voluntary and escape launches,
median completed perch and flight bouts, sample counts and explicit censored
bouts. Fatal ticks are excluded. Initial partial flight bouts are left-censored;
recording end/restart/death bouts are right-censored. Null medians mean no
complete eligible bout, not zero duration. Feeding overlaps perched time.
These are **simulator metrics**, not real activity-budget estimates.

Replay verifies full deterministic tick records including lifecycle fields,
local cues and kinematic profiles, plus archived inputs/configuration/source
hashes, data hashes and CPU threading runtime. Historical recordings still
require their archived source snapshot, as before. Source mismatch is not
silently ignored or rewritten.

## Calibration and frozen boundaries

Strict exact configuration/runtime provenance remains unchanged in Session.
The ROOM threshold is still 1.45, from the accepted M1.7.1 fixed-fly measurement.
`calibration_room_m1_8_a.json` explicitly reuses that measurement; it is not a
newly measured distribution. The record includes source SHA256/provenance and
the exhaustive configuration delta: lifecycle, config_version, calibration paths.
Fixed-fly-v2 bypasses ecology/lifecycle, so these changes leave its retinal and
neural inputs unchanged. A real shared-brain paired fixed-fly trial verifies
identical DNp01 arrays. Existing brain/encoder/world/swatter settings and source
files are unchanged. No threshold fitting or calibration rerun was justified.
Any subsequent config mutation, including a lifecycle parameter, still fails
closed unless an exact matching record exists. A stale ignored artifact cannot
override a matching record. If a future neural/input change requires measurement:

```powershell
python tools/calibrate_escape.py --config game_room_config.json --trials 28
```

R0 remains immutable. The original reservoir experiment and historical game
results remain byte-identical. M1.7.1 swatter mechanics, edge bounds, collision,
policy/encoder/brain implementation and LAB/GAME configs remain unchanged.
