# M1.6 ecological ROOM foundation

ROOM is the primary PLAY environment; LAB remains the controlled experiment,
and the preserved M1.5 GAME preset remains selectable. M1.6 implements no
M1.5.1 universal-speed calibration, reinforcement learning or personalization.
The state names below are simulation abstractions, not literal neural modules.

## Launch, modes and reproducibility

```powershell
Set-Location D:\Projects\flybrain-lab
& .\.venv\Scripts\python.exe -m game.app
& .\.venv\Scripts\python.exe -m game.app --arena room --seed 101 --windowed
& .\.venv\Scripts\python.exe -m game.app --arena room --seed 101 --no-ecology --windowed
& .\.venv\Scripts\python.exe -m game.app --arena game --seed 101 --windowed
& .\.venv\Scripts\python.exe -m game.app --mode lab --windowed
```

Execution modes (PLAY/LAB/EVALUATION/TRAINING) and arena presets
(ROOM/GAME/LAB) remain separate. The LAB execution mode defaults to LAB;
other modes default to ROOM. All policies remain frozen. TRAINING means data
collection only. `--ecology`/`--no-ecology` override the ROOM controller without
rewriting the physical config; the actual override is recorded in each run.
Disabling ecology preserves room objects, perception geometry and collisions.
With a non-ROOM config the ecological layer is absent even if requested.

ROOM keeps the M1.5 arena dimensions, body/paddle scale and directional threat
geometry: 3840x2160 logical units, 24-unit body, 288-unit paddle diameter.
No monitor-pixel or physiological millimeter calibration is implied. H shows
the neural and ecological HUD. R/Enter restart, F11 toggles fullscreen, Space/P
pause. PLAY starts with a random base seed unless supplied; restarts advance
by 1000. Identical seed and tick inputs reproduce fields and motion.

## Strict multisensory architecture

```text
World swatter geometry -> Retina -> balanced LC4/LPLC2 -> frozen MaleCNS
                     -> descending activity -> FixedEscapePolicy -> Action

World food / wind / surfaces -> EcologicalProjector -> EcologicalSense
                     -> EcologicalController -> EcologicalCommand

Action + bounded ecological modulation -> existing flight controller / physics
```

Odor never drives LC4/LPLC2, the brain or the threat policy. Ecology cannot
produce Action or change neural state. Session derives a separate ThreatState
from the existing neural policy state/action and active neural pulse. ESCAPE
and ALERT override ecological steering and speed drive while the neural action
or pulse is active; the existing neural impulse and yaw controller remain in
charge. A small tonic turn alone is not labeled ecological ALERT. The old
world's neural-steering arbitration threshold remains unchanged.

The controller accepts only the exact frozen, slotted EcologicalSense class;
subclasses and arbitrary dictionaries/World objects are rejected. Its config
accepts only ecological parameters, not source/obstacle coordinates. The schema:

| Field | Meaning |
|---|---|
| odor | local nonnegative concentration, arbitrary units |
| odor_rate | filtered temporal difference along the fly trajectory |
| odor_bilateral | concentration at right sample minus left sample |
| wind_forward, wind_lateral | local ambient flow resolved into body axes |
| visual_left, visual_right, visual_front | normalized local obstacle angular occupancy |
| visual_contrast | local visual contrast availability, including textured floor |
| landing_affordance | aggregate forward apparent size of eligible surfaces |
| surface_expansion | filtered change of that local visual affordance |

There is no source position, range, object identity, waypoint, target vector,
absolute heading, mouse coordinate or click flag. Bilateral odor and odor_rate
are logged foundation observables; this controller uses concentration hysteresis
and local wind rather than following an exact spatial gradient.

The wind cue represents an ideal estimate of ambient flow in body coordinates,
not raw antennal airspeed or a modeled wind-estimation circuit. It is a local
sensory approximation; no global target bearing is supplied. Visual contrast
modulates orientation gain, but full optic-flow-based wind estimation is absent.

## Exact wind and odor field

No CFD, particle solver or physical wind force is used. Wind is spatially
uniform and smooth in time. Independent seeded phases p0..p3 are uniform in
[0,2*pi), generated from episode seed + 6011. Defaults:

```text
angle(t) = radians(0 + 12*sin(2*pi*t/45 + p0))
speed(t) = 45 * (1 + 0.15*sin(2*pi*t/31 + p1))
W(t) = speed(t) * (cos(angle(t)), sin(angle(t)))
```

The configurable source is at (1050,1120), radius 65, emission Q=3. All source
coordinates remain WORLD-side. Let u=W/|W|; s=(position-source) dot u is the
wind-aligned coordinate and q its perpendicular coordinate. Define:

```text
d = 60 * log(1 + exp(s/60))             # stable softplus
age = d / |W(t)|
z = t - age
width = 100 + 0.09*d
center = 45*d/(d+100) * sin(2*pi*z/11 + p2)
gate = (1 + tanh(s/60)) / 2
emission = 1 + 0.35*sin(2*pi*z/9 + p3)
C = 3 * gate * (100/width) * exp(-d/2400 - (q-center)^2/(2*width^2)) * emission
```

Width, decay length, upwind softness, meander and emission modulation are
configurable. The downwind delay transports modulation; changing wind rotates
the plume. This is a quasi-steady analytic plume, not mass-conserving transport
with a full history of changing wind. It is continuous, non-radial and includes
slow spatial/temporal variation, but no realistic turbulent filaments, chemical
identity, receptor noise or concentration units have been fitted.

Body-relative wind is `(Wx*cos(h)+Wy*sin(h), -Wx*sin(h)+Wy*cos(h))`.
Bilateral odor samples are six logical units to either side. Odor and surface
derivatives use finite differences, then exponential filtering with tau=0.12 s
and clipping to +/-20 per second; the first sample after reset has zero rate.

## Local objects and landing foundation

The source is a non-solid eligible surface. A solid column is at (2480,780),
radius 95; a non-solid future perch is at (2850,1610), radius 75. These are world
objects, with schematic circles and labels. The fly receives no identifiers.

For each surface, apparent angular fraction is `2*atan2(radius,range)/pi`;
visibility is `contrast*exp(-range/450)`. Solid-object occupancy is distributed
between body-relative left/right by `(1 -/+ sin(bearing))/2`, with a forward
`max(0,cos(bearing))^4` term. Eligible-surface affordance uses forward cosine
squared. Aggregates are capped at 1. The floor supplies baseline contrast 0.6;
this models availability of visual structure, not reconstructed retinal images.

The column uses swept disk collision: stop at the earliest segment contact
and remove inward velocity. It never places the fly on a food/perch target.
Seeded spawning rejects solid-object overlap. Existing wall sensing and hard
containment are retained. Odor is not occluded by the column.

LAND_OR_PERCH means a **decelerating approach attempt only**. Full touchdown,
stationary perching, feeding and takeoff are deferred. Entry requires detected
odor plus forward eligible-surface affordance >=0.14 and positive expansion
for 0.16 s. A 0.9 s attempt, or odor loss, leads to relocation and an 8 s attempt
cooldown. This is not a successful-landing detector. Ground-plane source overlap
is a world analysis event, never proof of feeding or a policy feature.

## Behavioral state and speed mappings

All ranges are configurable gameplay mappings informed by behavioral classes,
not universal Drosophila speeds. A low-frequency within-range target is selected
by `low+(high-low)*(0.5+0.5*sin(2*pi*t/8+seeded_phase))`; a 0.5 s exponential
filter smooths transitions. Thus the smoothed command can temporarily lie
outside a new state's target interval while settling. Existing velocity inertia
and neural impulses determine actual speed.

| State | Target BL/s | Spontaneous clock multiplier | Entry / exit |
|---|---:|---:|---|
| EXPLORE | 5-8 | 1.0 | initial/default; after seeded 3-7 s -> TRANSIT |
| TRANSIT | 9-13 | 0.45 | seeded 2-5 s relocation -> EXPLORE, unless odor or threat intervenes |
| ODOR_SEARCH | 4-7 | 1.35 | odor lost after tracking; 6 s maximum, reacquire -> TRACK, otherwise EXPLORE |
| ODOR_TRACK | 9-13 | 0.35 | concentration >=0.10 for 0.12 s; loss <=0.065 for 0.45 s -> SEARCH |
| LAND_OR_PERCH | 1-3 | 0 | local forward surface/odor approach; timeout/loss -> TRANSIT |
| ALERT | 8-12 requested | 0 | only genuine policy alert/action or active alert pulse |
| ESCAPE | 12-18 requested | 0 | only genuine policy escape/action or active escape pulse |
| RECOVER | 5-8 | 0.7 | after ALERT/ESCAPE; then local odor or ordinary state resumes |

During genuine neural steering/pulses, ecological target/turn requests are
suppressed by world arbitration; the inherited 9 BL/s tonic drive and neural
impulse control motion. ALERT/ESCAPE rows are requested state targets, not
extra ecological escape acceleration. The HUD/logs distinguish requested
and applied speed drive. Ecological clock multipliers affect spontaneous
waiting only; wall safety timers and saccade pulse duration/rate are unchanged.

Brief ALERT recovery lasts 0.2 s; actual ESCAPE recovery lasts 1.2 s, retaining
that longer duration if the escape subsequently passes through ALERT. An early
diagnostic using 1.2 s after every short alert spent too much time in RECOVER;
severity-dependent recovery avoids turning every alert into a long interruption.
No threshold, original policy, LAB behavior or literature speed calibration
was changed to address that controller issue.

Tracking for 8 s triggers a 4 s exploratory relocation before accepting odor
again. This explicit anti-lock convention is not a measured habituation circuit.
The fly has no food target to circle and no memory of a source position.

## Orientation and free-flight integration

During ODOR_TRACK, desired heading change comes from the local upwind bearing
`atan2(-wind_lateral,-wind_forward)`. During ODOR_SEARCH, add a persistent
`1.05*sin(2*pi*search_elapsed/3.6+seeded_phase)` angular offset, then wrap the
error to [-pi,pi]. This is a modest oscillatory upwind search, not a full
biological crosswind casting model. Exactly downwind, a seeded side breaks the
turn-direction tie. Orientation gain is `1.3*(0.15+0.85*visual_contrast)`.

Obstacle avoidance adds `2*(visual_left-visual_right)`, with a seeded turn side
for symmetric frontal occupancy. Total ecological yaw is capped at 0.9 rad/s
and filtered with tau=0.18 s. Threats suppress it. There is no frame-wise random
steering, position output, target velocity vector or emergency Action from ecology.

The M1.5 low-frequency curvature, half-sine discrete saccades, seeded timing,
80-degree sideslip cap and 0.28 s velocity realignment remain. This is a 2D
horizontal slice, without wings, roll/pitch/banking or aerodynamic lift.

## Recording and future-policy isolation

The M1.5 observation schema remains unchanged: four DNp01/DNa02 aggregates,
restricted MotionState, pre-action neural behavior_state and four earlier
whitelisted frames. Ecological cues are not automatically added to that future
learned-policy observation. A future multisensory policy requires an explicit,
versioned observation decision; it must still exclude hidden world geometry.

`world_debug.jsonl.room_analysis` contains:

- pre-physics local EcologicalSense;
- ecological state, elapsed time, transitions, target speed and landing attempts;
- ecological command and actual applied target drive;
- separate neural threat state;
- object contact and world-side source/objects/wind/source-overlap analysis.

Existing action, neural state and strike records remain separate. The manifest
records the actual ecological enable flag; episode summaries add food-overlap
ticks, object-contact ticks and landing attempts. Pre-action sense and post-step
world geometry share a tick index and are explicitly distinguished. Recorders
never feed their debug state back into either controller. Profile counters are
still statistics, with no learned checkpoint or updates.

## Calibration and reproducibility

```powershell
& .\.venv\Scripts\python.exe tools\calibrate_escape.py --config game_room_config.json --trials 28
& .\.venv\Scripts\python.exe -m unittest discover -v
& .\.venv\Scripts\python.exe tools\room_sanity.py
& .\.venv\Scripts\python.exe -m game.app --arena room --mode evaluation --seed 101 --smoke 3
```

ROOM has independent calibration_room.json artifacts/results. The full config
hash includes environmental/controller settings, conservatively rejecting any
mismatch. Recalibrate custom configs with the same `--config PATH` in tool/game.
Calibration disables flight and collision; ecology does not advance or affect
the visual measurement. LAB and GAME calibration records remain unchanged.

## Biological grounding and modeling assumptions

**A. Direct evidence:** existing MaleCNS anatomy/cell annotations; observed
odor-associated acceleration, upwind turns and a role for visual feedback in
freely flying Drosophila. These observations motivate behavioral classes, not
our exact state machine or parameter values. See van Breugel & Dickinson
(2014), [original study](https://pubmed.ncbi.nlm.nih.gov/24440395/), DOI
10.1016/j.cub.2013.12.023. Visual context affects localization in the experiments
and modeling of [Stewart et al. (2010)](https://journals.biologists.com/jeb/article/213/11/1886/9805/A-model-of-visual-olfactory-integration-for-odour).

**B. Phenomenological model:** analytic odor/wind, ideal local ambient-wind cue,
coarse visual occupancy, ecological states, hysteresis, upwind/search steering,
speed modulation, approach attempts, recovery and the inherited fly motion.
No olfactory connectome circuit has been implemented or validated.

**C. Engine convention:** room layout/scale, circles/hitboxes, swept contact,
rendering, profile counters, speed/yaw limits and anti-lock relocation timers.
No odor-source localization success, biological fidelity or connectome advantage
is established by passing implementation tests.

## Human acceptance: approximately ten minutes

1. 0-2 min: start ROOM with seed 101, park the swatter in a corner, press H.
   Observe exploration/relocation, speed changes and occasional odor encounters.
   Notice whether repeated short ALERT/RECOVER transitions still look robotic.
2. 2-4 min: follow without striking. Compare local odor and ODOR_TRACK/SEARCH
   labels to changes in course. The wind arrow describes flow; tracking should
   tend against it, without a straight-line teleport or source target lock.
3. 4-5 min: watch source/column/perch encounters. Approaches may decelerate;
   expect no implemented touchdown. Report persistent food orbit or obstacle sticking.
4. 5-7 min: attack from several directions. Neural ALERT/ESCAPE must take
   priority over odor behavior, then return through recovery to local activity.
5. 7-8 min: restart a few times. Judge whether the room supports varied ongoing
   activity without player input; note repetitive scripted-looking transitions.
6. 8-10 min: run the same seed with `--no-ecology` and compare. Check LAB still
   launches separately. Quit normally to flush logs; report seed and actions.

For a wind-direction comparison, copy the ROOM config to an ignored artifact,
change only room.wind.direction_degrees and calibration destinations, recalibrate
that custom file and launch with --config. The predefined diagnostic tool already
includes reversed-wind and zero-emission controls without modifying any preset.

Stop for owner playtesting. Do not commit final M1.6 or start learning yet.
