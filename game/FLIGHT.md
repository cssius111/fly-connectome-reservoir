# M1.3 untrained BIO FLY: flight and playtest notes

M1.2 checkpoint: `85253f9abec36d01719fee548c4f7f7f869338e2`.
No learning, reinforcement learning, or synaptic plasticity is implemented.

## Biological motivation versus game conventions

Free-flight experiments describe straighter flight segments separated by rapid course changes ([Tammero & Dickinson, 2002](https://pubmed.ncbi.nlm.nih.gov/11854370/)). Looming can elicit visually directed evasive banked turns ([Muijres et al., 2014](https://pubmed.ncbi.nlm.nih.gov/24723606/)). These motivate the pattern, not the numeric parameters or this decoder. Neither study validates this MaleCNS-based decoder.

This game is a 2D abstraction with a 20 ms neural tick. It does not simulate wings, roll, pitch, lift, halteres, photoreceptors, or full retinal images. No claim is made that DNp01/DNa02 naturally implement this actuator or that these numbers reproduce real flight. All angles, intervals, gains, and caps below are human-readable gameplay choices, deliberately modest/slower than many measured fly maneuvers.

| Component | Source | Requested behavior |
|---|---|---|
| Cruise | Tonic game physics | 85 units/s forward target, damping 3/s, existing seeded drift and wall avoidance |
| Spontaneous saccade | Independent seeded physics RNG | 16–24 degrees in 0.30 s; wait 2.5–4.5 s of calm, wall-clear time between pulses |
| ALERT saccade | Sustained DNp01 gate and smoothed neural laterality | Up to 18 degrees in 0.26 s under the fixed policy; at least 0.06 s qualifying activity; request interval 0.8 s |
| ESCAPE saccade | Calibrated DNp01 emergency gate | Up to 60 degrees in 0.30 s, scaled by neural laterality and escape strength; existing 0.4 s refractory retained |
| Escape velocity impulse | Same neural policy | 880 × strength, with strength 0.5–1, before damping and speed cap |
| Total yaw | Actuator safety bound | At most 6 rad/s, including continuous neural steering, drift, walls, and pulse |

A half-sine angular-velocity profile integrates to each requested angle. There is no instantaneous heading assignment. Velocity retains inertia; heading and velocity need not align during a maneuver. Angle values describe the pulse component before total-yaw clipping, not the sum of pulse plus continuous steering. An emergency may interrupt a weaker pulse; an active emergency is not restarted every frame. Heading remains continuous at interruption, but this is not a full angular-inertia model. Walls suppress/cancel spontaneous pulses. Boundary containment and rebound remain game conventions.

Neural laterality retains the M1.2 0.12 s smoothing. A contralateral noise spike cannot immediately flip the stored side estimate. DNa02 can modulate turn magnitude by at most 15%, not override the DNp01-derived sign. ALERT pulses require sustained activity; an isolated subthreshold noise spike cannot request one. Neural noise, latency, and ambiguity still mean an occasional imperfect response is possible.

The chain remains world → Retina(theta, theta_dot, azimuth) → LC4/LPLC2 stimulation → MaleCNS-derived frozen runtime graph → descending activity → policy → physics. The runtime removes incoming sensory-neuron edges (`sensory_input=false`): 25,088,107 edges versus 25,582,938 in the original dataset. Tonic cruise, spontaneous saccades, and arena-wall handling do not originate in the connectome. Threat actions do. HUD LC4/LPLC2 bars show injection drive, not measured cell firing.

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

1. **Minute 0–1: no interaction.** Leave the swatter far away. The fly should keep cruising, occasionally make a short course change, then settle into smooth flight. Watch for jitter, stalls, long high-speed runs, or wall oscillation. SPONTANEOUS does not mean the brain detected a threat.
2. **Minutes 1–3: approach without clicking.** Move toward it gradually, then more quickly. Watch theta_dot, descending traces, and CALM/ALERT/ESCAPE. Evasion should sometimes begin before clicking; rapid approach may itself trigger ESCAPE. Repeat from both body-relative sides; azimuth sign helps distinguish body-left/right from screen-left/right.
3. **Minutes 3–5: strike and lead.** First try clicking at its current location, then aim slightly ahead. Both successful hits and misses should remain possible. Observe whether the wind-up creates a stronger response than a gentle approach. A good result requires anticipation without feeling impossible to follow.
4. **Minutes 5–7: inspect direction after misses.** Watch heading and trajectory through recovery. Short turns should have a discernible direction and preserve momentum, not jump or reverse instantly. Look for wrong-way reactions, repeated alternating turns, or escape that feels unrelated to the approach.
5. **Minutes 7–10: edges and presentation.** Follow near each edge/corner, then back away. Check it leaves the boundary rather than sticking or bouncing repeatedly. Toggle H and F11; pause/resume; use R for another seed. All HUD values should fit at 1280×720 and fullscreen.

Record the displayed seed, how you approached, whether you clicked, the observed state/saccade type, and what felt wrong. Short video is useful but not required. Automated tests and scripted chase outcomes are only regression evidence; human playtest is the acceptance criterion. Do not infer biological learning or a connectome advantage from success in this game.
