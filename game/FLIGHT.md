# M1.4 untrained BIO FLY: local enclosure and flight

Resumed from Claude's `182c5a9` checkpoint on `wip/m1-4-enclosure`, based on
stable M1.3 `85f987b279dbd2b1f725fa79aa299281259258ab`. This is the validated M1.4 baseline, with no M2, training, RL or plasticity.

## Scientific scope

The biological data are MaleCNS-derived connectivity and cell annotations.
The game uses frozen LIF dynamics with modeling assumptions and a fixed
DNp01/DNa02 decoder. With `sensory_input=false`, incoming sensory-neuron edges
are removed: **25,088,107 runtime connections**, compared with **25,582,938
connections in the original dataset**. The dataset and original reservoir
experiment/results remain unchanged.

Free-flight observations motivate coherent segments interrupted by rapid
course changes ([Tammero & Dickinson, 2002](https://pubmed.ncbi.nlm.nih.gov/11854370/));
looming-evoked evasive flight motivates the threat response pattern
([Muijres et al., 2014](https://pubmed.ncbi.nlm.nih.gov/24723606/)). These sources
are not validations of this model or its decoder. Wall exploration and all
numeric flight distributions below are phenomenological game choices, not
extracted MaleCNS dynamics or fitted animal measurements.

This is 2D, with a 20 ms tick and no wing mechanics, bank, roll, pitch, lift,
photoreceptors or full retinal images. LC4/LPLC2 are stimulated directly.
HUD bars show injection voltage, not measured cell firing.

## Scale and turn actuator

The drawn longitudinal body polygon is **24 px** before integer rasterization
(wings excluded), independent of its approximate 11 px collision radius.
Cruise target is **160 px/s = 6.667 body lengths/s**. The safety speed cap is
**1,000 px/s = 41.667 body lengths/s**, not a cruising target. There is no
px-to-mm physical calibration. Escape retains the 880 × strength velocity
impulse, followed by damping and speed limiting.

| Request | Angle magnitude | Requested peak rate | Source |
|---|---|---|---|
| CORRECTION | uniform 5–18° | uniform 250–600°/s | seeded flight controller |
| SACCADE | uniform 25–105° | uniform 700–1,400°/s | same controller |
| AVOID | local bearing to tangent + 14° inward | uniform 700–1,300°/s | local time-to-contact proxy |
| DEPART | uniform 40–85° away from surface | uniform 600–1,100°/s | perimeter residence |
| ALERT | up to 55° × signed policy request | 900°/s | sustained descending activity |
| ESCAPE | up to 110° × signed policy request | 1,350°/s | calibrated DNp01 emergency gate |

A half-sine yaw pulse is integrated analytically:
`delta(t) = angle * (1 - cos(pi*t/T)) / 2`.
`T = max(0.06 s, abs(angle)*pi/(2*min(requested_peak, rate_cap)))`.
Angle is capped at 120°, peak rate at 1,500°/s. A request requiring over
0.30 s at its requested peak raises before changing actuator state; duration
is never shortened to violate the rate. Minimum duration reduces the actual
peak of small requests. Completion is quantized to the 20 ms tick, while the
integrated pulse angle remains exact.

Priority: ESCAPE > AVOID = ALERT > SACCADE = DEPART > CORRECTION. Equal or
weaker requests cannot restart or interrupt an active pulse. Preemption
preserves heading, not yaw acceleration; this is not angular inertia.
Continuous neural steering and smooth drift add to pulse yaw. A final
31 rad/s safety cap leaves headroom under the shipped bounds; custom excessive
steering may be clipped. Translational velocity retains inertia, so broad
turns may briefly slow flight. There is no heading teleport, direct rotation
of the velocity vector or instantaneous 180° reversal.

## Event timing

Quiet eligible flight time after a pulse uses a seeded mixture:
28% uniform 0.3–0.7 s; 54% uniform 0.8–1.9 s; 18% uniform 2.6–6.0 s.
Near the perimeter, gaps are multiplied by 1.7 and spontaneous turns become
small corrections. The clock pauses during active pulses or neural steering;
rejected turns are not randomly resampled each frame. In open space,
CORRECTION probability is 0.42; otherwise the event is SACCADE.
World drift is a separate small angular target (±0.08 rad/s), drawn every
1.6 s with 0.8 s smoothing. These RNG streams are independent of brain noise.

## Four distinct mechanisms

A. **Local sensory geometry**, `enclosure.py`: frozen/slotted `WallCue` has
only `expansion` (inverse seconds), `contact_bearing` (body radians),
`proximity` (0–1), `surface_bearing` (body radians) and `open_ahead` (boolean).
The sensing horizon is 150 px. This is a direct geometry proxy, not wall
vision through the connectome. No position, wall identifier, map, exit
coordinate or waypoint is supplied to behavior.

B. **Phenomenological exploration**, `flight.py`: estimated contact within
0.55 s requests a tangent turn with 14° inward bias. The shorter turn preserves
course; a head-on tie retains a seeded side. An already inward heading is not
turned back toward the wall just because inertial velocity still points
outward. Avoidance waits for the pulse duration plus 0.2 s before retriggering.
Perimeter entry/leave uses proximity 0.45/0.2 hysteresis. After a seeded
1.2–4.5 s residence, DEPART turns inward; ordinary corrections are suppressed
until the fly leaves the zone, while safety avoidance remains available.
This is local perimeter-following and departure, not attraction to a global
destination. A boolean derived from Action pauses spontaneous turns during
neural steering; no brain values or swatter state enter this controller.

C. **Neural swatter response**: mouse/swatter → world geometry →
`Retina(theta, theta_dot, azimuth)` → balanced LC4/LPLC2 stimulation → frozen
MaleCNS-derived graph → descending activity → fixed policy → physics.
DNp01, DNa02, CALM/ALERT/ESCAPE and 0.12 s laterality smoothing are preserved.
DNa02 can modulate amplitude by 15%, but cannot reverse the DNp01 sign.

D. **Hard containment**: a final body-radius-aware clamp cancels only outward
velocity, retaining inward and tangential velocity. It does not bounce or set
heading. The visible solid rim shares the sensing surfaces. A contact means
predictive avoidance was insufficient, especially after large escape impulses
or an initial placement very close to a corner. This is reported game physics.

`Opening` reserves geometry for future gaps, but **no opening exists in the
shipped world**. Tests cover body clearance, screen-top orientation, local
visibility and solid-corner priority. There is no exit-seeking state or planner.

## Validation and limitations

Exact results are in [results/game/M1_4.md](../results/game/M1_4.md).
Run `python tools/flight_sanity.py` for isolated locomotion and
`python tools/chase_sanity.py --label m1-4` for neural pursuit. Full traces and
screenshots stay in ignored `artifacts/m1-4/`; small summaries and a figure are
in `results/game/`. Earlier M1.2/M1.3 chase summaries are preserved.

Fixed scenarios demonstrate reproducibility and regression properties, not
universal absence of wall contacts or optimized survival. Brief constraints
and inertial slowdowns remain, especially during neural escape near walls.
Difficulty, visibility of the smaller body, corner behavior under repeated
strikes and fairness of trajectory leading need human playtesting.

## Policy boundary for a future comparison

`Policy` still requires only `reset()` and `decide(MotorState)`. The fixed untrained implementation stays available. No learned-policy placeholder, trainer, reward, or optimization loop is added.

`MotorState` contains descending summaries/trace and a frozen, slotted `MotionState`: body-forward velocity, body-lateral velocity, yaw rate, remaining saccade time. This proprioceptive snapshot contains no absolute position, absolute heading, mouse/swatter coordinates, or threat vector. It is appended after the neural step, so it cannot affect retinal injection. Wrong types, including subclasses, are rejected at the FlyLoop boundary. A future policy may retain short history inside itself and clear it in `reset()`.

`Action.saccade` is a signed [-1,1] request: positive turns right in the body frame. It selects an ALERT pulse unless `escape=True`, which selects ESCAPE. Zero-strength escapes request no emergency pulse. Repeated requests do not restart an active emergency. `Action.strength`, direction, and continuous `turn` retain their prior meanings. A bare policy without diagnostics still renders.

Calibration freezes position, heading, velocity, and all saccade timers; collisions and policy actions are disabled. The full configuration hash includes the new parameters, so old calibration cannot silently match a new configuration. The committed calibration was rerun with `python tools/calibrate_escape.py --trials 28`.

## Controls and input robustness

Shortcuts are dispatched on the SDL **scancode** (the physical key) first and
on the translated keysym only as a fallback, so an active IME or a non-Latin
layout cannot swallow them. Text composition is switched off at startup and
again on `WINDOWFOCUSGAINED`, because an IME can re-arm it. Key repeat is
disabled and a restart is idempotent within one event batch, so a held key
does not stampede through seeds.

`R` (and `Enter`, as an explicit alternative) always produces a **running**
episode: it resets world, fly, statistics and interpolation state, and clears
pause. A left click batched with the restart belongs to the finished episode
and is dropped rather than opening a strike on the fresh one. `H`, `Space`/`P`,
`F11` and `Esc` keep their prior meanings. This is game input handling only;
nothing here touches perception, the connectome or the policy.

## Human acceptance: 5–10 minutes

Launch from the repository with `.\.venv\Scripts\python.exe -m game.app`. Use H for diagnostics; R starts the next reproducible episode seed. Fixed-seed replay is deterministic by design; course changes need not be predictable to a human who does not know the RNG state.

1. **Minute 0–1: no interaction.** Leave the swatter far away. The fly should keep cruising, occasionally make a short course change, then settle into smooth flight. Watch for jitter, stalls, long high-speed runs, or wall oscillation. CORRECTION / SACCADE / AVOID / DEPART are phenomenological, not brain-detected threats.
2. **Minutes 1–3: approach without clicking.** Move toward it gradually, then more quickly. Watch theta_dot, descending traces, and CALM/ALERT/ESCAPE. Evasion should sometimes begin before clicking; rapid approach may itself trigger ESCAPE. Repeat from both body-relative sides; azimuth sign helps distinguish body-left/right from screen-left/right.
3. **Minutes 3–5: strike and lead.** First try clicking at its current location, then aim slightly ahead. Both successful hits and misses should remain possible. Observe whether the wind-up creates a stronger response than a gentle approach. A good result requires anticipation without feeling impossible to follow.
4. **Minutes 5–7: inspect direction after misses.** Watch heading and trajectory through recovery. Short turns should have a discernible direction and preserve momentum, not jump or reverse instantly. Look for wrong-way reactions, repeated alternating turns, or escape that feels unrelated to the approach.
5. **Minutes 7–10: edges and presentation.** Follow near each edge/corner, then back away. Check it leaves the boundary rather than sticking or bouncing repeatedly. Toggle H and F11; pause/resume; use R for another seed. All HUD values should fit at 1280×720 and fullscreen.

Record the displayed seed, how you approached, whether you clicked, the observed state/saccade type, and what felt wrong. Short video is useful but not required. Automated tests and scripted chase outcomes are only regression evidence; human playtest is the acceptance criterion. Do not infer biological learning or a connectome advantage from success in this game.
