# M1.8 proposal: Biologically Grounded Activity Budget and Flight-State Kinematics

Status: planning only, prepared after M1.7.1 human acceptance. No M1.8 behavior, parameters, neural wiring or training is implemented. Implementation requires a subsequent owner request. Primary-source research checked on 2026-09-21; numerical parameter extraction and matched activity-budget data remain prerequisites.

## Objective and frozen boundary

Give the fly context-dependent movement and genuine stationary periods: search, transit, odor-oriented flight, decelerating landing, touchdown, perching, feeding, spontaneous takeoff and visually triggered escape takeoff. The target is credible autonomous activity, not a chosen human hit rate or a universal cruise speed.

Keep the accepted M1.7.1 approach controller, strike phases, partial-offscreen head geometry, swept collision and recorder/replay contract frozen. Keep the legal fly area, original experiment, historical sessions and restricted WORLD/policy boundary. New landing mechanics must integrate on the fly/environment side without weakening contact tests, making perched flies invulnerable or creating an edge sanctuary. No RL, personalization, plasticity, reward optimizer or learned readout is in scope.

## What the current code actually does

`ecology.py` alternates EXPLORE and TRANSIT using uniform 3-7 s and 2-5 s timers. It varies the target speed using an eight-second sinusoid, then smooths speed with a 0.5 s time constant. Odor encounters/loss already use local sensory thresholds and hysteresis, but an eight-second odor bout forces relocation. LAND_OR_PERCH is a 0.9 s approach attempt, followed by departure; all ecological speed ranges are strictly positive. There is no contact-based stationary state, feeding or takeoff. These are explicit modeling conventions, not connectome-derived activity budgets.

The accepted human session has alive fly speed median 8.74 BL/s and p90 17.54 BL/s; RECOVER occupies 44.72% of alive ecological ticks. It is an attacked session with deaths/resets and zero landing attempts, not a quiet baseline or a natural time-budget sample. Investigate passive ROOM trajectories before concluding that the main problem is cruise speed. Distinguish requested ecological speed, applied drive, physical speed and body-relative forward/lateral velocity.

The rendered body length is 24 logical units. Conversion to m/s requires an explicit measured or assumed biological body length, with uncertainty. Current wind is a sensory cue with physical force disabled: current speed is ground-relative and must not be compared to airspeed without a separate model. Screen scaling must not change body-length-normalized kinematics.

## Primary evidence and what it does not establish

| Question | Verified primary evidence | Implication and unresolved measurement |
|---|---|---|
| Odor-oriented free flight | van Breugel & Dickinson (2014) report acceleration/upwind turning after odor entry and casting after odor loss, with response latencies around 190 +/-75 ms and 450 +/-165 ms in their assay. [Study](https://pubmed.ncbi.nlm.nih.gov/24440395/) | Use local encounter history and delays as candidate mechanisms. Extract context-conditioned speed/acceleration distributions; these latencies are not automatic ROOM constants and do not define a universal flight speed. |
| Sensory history | Pang et al. (2018) find weaker upwind turns at later plume crossings and concentration-dependent responses. Their tested theories do not capture every measured feature. [Study](https://journals.plos.org/ploscompbiol/article?id=10.1371/journal.pcbi.1005969) | Evaluate modest encounter-history dependence against a memoryless control. This does not justify giving the fly a source map or implementing an optimal planner. |
| Saccades plus curvature | Tammero & Dickinson (2002) observe rapid course changes, visual-context effects on translational velocity/saccade frequency, and gradual inter-saccadic turns. [Study](https://pubmed.ncbi.nlm.nih.gov/11854370/) | Retain discrete maneuvers and bounded intervening curvature. Extract duration, turn-angle, yaw-rate and inter-event distributions by assay, not just an average rate. |
| Acceleration separate from baseline speed | van Breugel, Suver & Dickinson (2014) report slower visual-motion-driven acceleration after octopamine-neuron inactivation despite nearly unchanged baseline speed. [Study](https://pubmed.ncbi.nlm.nih.gov/24526725/) | Measure acceleration response separately from preferred speed; this is not permission to invent neuromodulatory dynamics. The authors' [Dryad trajectories](https://datadryad.org/dataset/doi:10.5061/dryad.sp70n) are a concrete extraction candidate, including controls. |
| Landing | van Breugel & Dickinson (2012) separate target-directed turn, deceleration linked to target size/expansion, and leg extension before contact. In that assay, leg extension occurred near 60 degrees retinal size. [Study and supplements](https://authors.library.caltech.edu/records/ve6y5-s8h29/latest) | Separate approach intention from confirmed touchdown. Thresholds depend on target geometry and are not directly reusable for circular top-down ROOM objects. Include aborted landings and fly-bys. |
| Voluntary versus escape takeoff | Card & Dickinson (2008) find a speed/stability trade-off between initiation modes in unrestrained flies. [Study](https://pubmed.ncbi.nlm.nih.gov/18203989/) | Use distinct spontaneous and threat-triggered initiation profiles. Quantify latency and acceleration; a 2D model cannot validate roll/pitch stability or detailed leg/wing biomechanics. |
| Feeding and internal state | Itskov et al. (2014) show hunger/satiety effects on feeding microstructure using flyPAD. [Study](https://pubmed.ncbi.nlm.nih.gov/25087594/) | Model food contact, dwell and changing motivation separately. This feeding assay does not establish the fraction of a room-dwelling fly's life spent flying, perched or sleeping. |
| Anatomical candidates | The [MaleCNS resource](https://male-cns.janelia.org/) and [comparative descending/ascending-neuron study](https://www.nature.com/articles/s41586-025-08925-z) provide connectivity and type-level routes between sensory and motor systems. | Use anatomy to identify candidate populations and pathways, not to label arbitrary behavior-state timers as brain modules. Verify IDs, sex/dataset correspondence, function and modeled transfer dynamics before wiring a new controller. |

No defensible universal activity percentages or final per-context speed intervals are established by this initial research. Do not select them by increasing speed until the human finds the fly difficult to hit. No large source dataset has been downloaded or fit in this planning pass.

## Evidence gate before changing parameters

Create a compact extraction record per experiment: species, sex, age, body length, feeding state, circadian phase, temperature, arena size, wind, visual texture, free versus tethered flight, sampling/filtering, tracking losses, speed definition and available data. Keep D. melanogaster separate from other Drosophila species; keep laboratory free flight separate from long-range dispersal and tethered wingbeat proxies. Identify female-derived results before transferring them to a male-connectome model.

Recover distributions for quiet flight, search, transit, odor entry/loss, landing and takeoff. Report p10/p50/p90/p95, acceleration/deceleration, speed autocorrelation and bout duration, with uncertainty across flies/bouts rather than treating adjacent frames as independent animals. Use the same filtering when comparing derivatives. Maintain both 3D and horizontal-projection speeds where possible; the latter is the appropriate starting comparison for ROOM.

The Dryad speed-regulation dataset supplies trajectories and describes Kalman smoothing, but its visual perturbations and genotypes require stratification. Landing supplements and free-flight odor records are separate sources. They cannot simply be concatenated into one target histogram. Where raw data are unavailable, identify the figure/table and digitization uncertainty; missing body size must remain an explicit conversion assumption.

A separate ethogram dataset is needed for activity budgets: continuous observation with flight, stationary/perch, feeding and other actions distinguished; matched food access, deprivation, lighting and observation duration; censored bouts and deaths excluded or reported separately. A brief attacked game session, a feeding-contact sensor, or a low-height walking arena cannot by itself supply a free-flight/rest budget. If matched evidence remains unavailable, retain named provisional scenarios with sensitivity ranges and label them phenomenological. Do not equate immobility with sleep.

## Proposed architecture after evidence review

Separate three factors rather than extending one flat state enum indefinitely:

1. **Physical locomotor state:** AIRBORNE, LANDING_APPROACH, PERCHED, TAKEOFF; death remains the existing terminal state. FEEDING is an activity possible only with confirmed food contact, not an airborne speed regime.
2. **Ecological motivation/history:** encounter recency, odor-loss history, coarse hunger/satiety and recent rest/feeding. These are initially explicit phenomenological variables in ecology, not claims of simulated metabolism or neural motivation.
3. **Neural threat response:** keep the frozen retinal feature injection and descending readout. Threat can interrupt landing/feeding and request departure through a documented motor-state-dependent execution rule. No click, paddle phase, pointer derivative or global threat vector enters the policy.

The current `EcologicalSense` already provides local odor, wind axes, visual occupancy, landing affordance and surface expansion. New contact/taste observations, if later authorized, need a narrow typed body/local-surface interface. WORLD resolves whether contact actually occurred; ecology must not receive food coordinates, object IDs or teleport destinations. The existing `MotorState`/`MotionState` neural whitelist remains unchanged in the initial implementation scope. Keep ecological state separate from neural CALM/ALERT/ESCAPE in reports.

### Continuous flight kinematics

Fit context-conditioned preferred-speed variation and distinct acceleration/deceleration responses; avoid independent per-frame random speeds and a globally periodic speed waveform. A bounded stochastic process with evidence-supported temporal correlation is a candidate, not an established biological equation. Drive the existing inertial body continuously rather than resetting its velocity at a state transition. Keep safety caps separate from normal quantiles, and report time spent hitting those caps.

Search, relocation/transit and odor-oriented labels should summarize the realized behavior. Evaluate whether fewer continuous motivations plus sensory events explain trajectories as well as the current labels. Preserve discrete saccades with refractory motor constraints and modest sensory-driven curvature between them; test against always-curving and timer-only controls.

### Landing, stationary life and takeoff

Landing approach should use local surface expansion/affordance and deceleration. Touchdown requires contact with an eligible surface and an admissible relative velocity, not an elapsed approach timer or proximity alone. Permit aborts when contact is unsafe or neural threat intervenes. Confirmed perch has a stable surface attachment and zero translational velocity; internal sensory/neural updates continue. Feeding requires food contact and changes phenomenological satiety over time; perching alone is not feeding.

Spontaneous takeoff may depend on satiety, accumulated rest and sensory history. Threat-triggered takeoff may bypass the ordinary departure tendency with a separately specified latency/motor profile. Both must create continuous departure and clear contact without position jumps. Stationary flies remain subject to the same paddle collision and edge rules.

The horizontal ROOM needs an explicit representational decision before implementation: use an idealized contact state on visible landing patches for the first version, with no invented 3D biomechanical claim. Full altitude, leg articulation, roll/pitch and surface orientation are deferred. Define collision order and perched body clearance before coding so no new hiding place or obstacle immunity is introduced.

### Replace timer-driven alternation carefully

Compare the current fixed/uniform timers to seeded event-dependent transition hazards: odor evidence, encounter/loss recency, local landing opportunities and feeding/rest history can change the probability of departure or behavior change. Include minimum motor durations and safety timeouts where necessary, clearly labeled as engineering constraints. Timer removal is not inherently biological; retain durations supported by measurements, and reject hazards that merely reproduce another rigid cycle. No source-location oracle or learned policy is proposed.

## MaleCNS scope and scientific claims

Immediately retain the tested LC4/LPLC2 feature injection and DNp01/DNa02 fixed readout as the baseline threat pathway. It is a computational coupling with modeling assumptions, not proof that these two readouts specify all free-flight steering or perched escape. The runtime graph removes incoming sensory-neuron edges (`sensory_input=false`): 25,088,107 connections versus 25,582,938 in the original dataset. It is not an untouched whole-eye-to-muscle organism.

An anatomy audit can now identify annotated sensory/projection, descending and ascending candidates and inspect their connectivity without changing the runtime graph. Any later olfactory, gustatory, landing or takeoff neural addition needs functional evidence, input/output population definitions, sign/dynamics checks and a preregistered comparison to the current phenomenological controller. Anatomical reachability alone is not sufficient. Hunger, rest, feeding dwell, contact mechanics, state transitions and continuous motor actuation remain explicitly phenomenological until such evidence exists. Plasticity and human personalization remain deferred.

## Proposed staged work and acceptance gates

| Stage | Deliverable after explicit implementation approval | Gate |
|---|---|---|
| M1.8a evidence and passive baseline | Source/extraction ledger; quiet ROOM multi-seed trajectories; declared BL/s and horizontal-speed mapping | No new speed constants without traceable context and uncertainty; distinguish ecological requested/applied/actual speeds. |
| M1.8b context-dependent flight | Calibrated speed/acceleration distributions and sensory/history-driven transitions | Match selected distributional/time-course targets on held-out trajectories/seeds; avoid periodic alternation and saturation. |
| M1.8c contact and activity | Actual landing/perching, food-contact feeding, spontaneous/threat takeoff | Continuous contact/departure, interruptible feeding, nonzero quiet stationary bouts, unchanged collision reachability. |
| M1.8d validation and human inspection | Ethograms, bout-survival plots, context speed/acceleration distributions, exact replay and a short recorded passive/active playtest | Human sees autonomous activity; numerical regressions and observation isolation pass. Difficulty is reported descriptively, not optimized. |

Use paired seeds across preserved M1.7.1, new full model, constant-speed control, timer-only transition control, odor-off/reversed-wind conditions and food/perch availability controls. Separate no-threat observation, ordinary visual approach and controlled threat from airborne/perched states. Calibrate evidence-derived parameters on designated data; hold out animals/bouts/contexts as available. Do not select parameters on human hit rate.

Future metrics must include alive-time activity fractions, airborne-only speed quantiles, stationary-bout durations, takeoff/landing success and abort rates, contact speed, event-conditioned response latency, saccade/curvature statistics, and speed-cap occupancy. Report censored bouts and all/alive denominators. Preserve the accepted recorder/replay interface: first derive available metrics offline; any genuinely required new telemetry should be a separately versioned extension proposed explicitly, never a silent schema-3 change or an edit to old sessions.

All original experiment checks and frozen swatter/edge tests remain mandatory. Any new ROOM configuration requires exact matching versioned calibration; old records must not be overwritten. Include stationary-fly visual-response tests, landed-fly hit tests, no feeding off food, no hidden global-coordinate observation, no death counted as rest, and deterministic state transitions. No learning is required to pass these gates.

## Decision for this handoff

Freeze M1.7.1 after the accepted commit/push. Start neither M1.8 nor training now. The recommended first future action is M1.8a evidence extraction and passive activity measurement, followed by a bounded design decision on locomotor/contact state and empirical parameter ranges. Credible innate/ecological behavior should precede personalized human-in-the-loop learning.
