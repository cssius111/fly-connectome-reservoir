# M1.7.1 pre-tuning human-session diagnosis

Source: `results/game/sessions/20260920T200809.608987Z-32182677`, recorded at clean commit `e0f08ebe55ecefcab69cc7927668c0f2cef7f69c`, config 8, schema 2.
All 15,039 tick hashes and episode/global tick sequences were checked. No historical session or game parameter was changed for this diagnosis. Machine-readable evidence: [human_m1_7_analysis.json](human_m1_7_analysis.json).

## Sampling and denominators

The recording spans 300.78 simulation seconds, 65 episodes, 7,752 post-step-alive ticks and 5,270 alive APPROACH ticks. Pointer derivatives require the preceding tick in the same episode; excluding 65 episode-first ticks leaves 5,205 paired samples. Velocity is the consumed target difference / 0.02 s. Acceleration is the vector velocity difference / 0.02 s. Target error uses the current consumed target and previous post-step head position. State and physical speed refer to the current post-step state; retinal values refer to pre-physics geometry. No episode-boundary jump is interpreted as a hand motion.
Pointer coordinates are logical units. These derivatives are not measured physical hand motion: display-event coalescing, repeated targets and pause/resume affect them. A 100-ms mean-velocity-vector sensitivity check is included. Raw screen coordinates/window sizes are not archived, so scaling cannot be inverted from this recording alone. Existing conversion tests and code show correct letterboxing/scaling.

## Edge regression confirmed

112 strikes: 64 hits and 48 misses (57.14%). First-strike hit rate is 37/64 = 57.81%; one episode has no strike. There are 17 near-wall hits and 5 near-wall misses; 15 of the hits have partially offscreen heads. All 7,752 alive ticks are geometrically reachable. This supports retaining the edge repair, not further restricting the fly.

## Approach controller diagnosis

Across all 5,270 alive APPROACH ticks, physical speed p50/p75/p90 is 1672.64 / 1791.38 / 1798.88 units/s; 46.93% are >=95% of the 1800 cap. On the 5,205 derivative-valid paired ticks, this is 47.51%. Paired pointer speed p50/p75/p90 is 761.58 / 1615.55 / 2973.21 units/s. Target-error median is 291.50 units (12.15 BL); p90 is 741.77 units.
The old desired velocity is normalize(error) * min(1800, 12*|error|). It does not use pointer velocity in ordinary APPROACH. An error of 150 units (6.25 BL) already commands full approach speed. 67.34% of paired approach ticks exceed that error; 99.92% of near-cap ticks do. The 45-ms velocity relaxation and 18000-units/s^2 acceleration limit rapidly execute this request. They affect transients, but accumulated positional error and gain-driven saturation are the primary demonstrated mechanism. Lowering every speed cap would remove intentional bursts without addressing the distinction.

| Raw consumed pointer speed (units/s) | Ticks | Head >=95% cap | Median head speed | Median target error |
|---|---:|---:|---:|---:|
| stationary [0, 1] | 825 | 40.85% | 1587.32 | 332.05 |
| slow [1, 300] | 620 | 43.87% | 1609.97 | 246.60 |
| moderate [300, 900] | 1416 | 44.84% | 1611.91 | 175.43 |
| fast [900, 1800] | 1185 | 53.25% | 1742.31 | 280.88 |
| above_cap [1800, None] | 1159 | 51.60% | 1718.49 | 427.32 |

Bands are analysis conventions, not biological categories: stationary <1; slow 1-300; moderate 300-900; fast 900-1800; above-cap >=1800. The 100-ms sensitivity check still finds 46.99% near-cap head motion during slow pointer motion and 42.02% during moderate motion. The JSON retains speed, acceleration, theta, theta_dot, error and threat-state distributions by band. Thus raw event quantization alone does not explain the result.

## Pre-strike perception and descriptive outcomes

84 strikes began with preexisting ESCAPE: 43 hits (51.19%). The other 28 produced 21 hits (75%). For the indexed nearest threat onset within the strike window, a -0.1 to +0.1 s warning interval (click time minus onset time) gives 20/25 hits (80%); >0.1 to 0.5 s prior warning gives 27/59 hits (45.76%). These groups are not randomized; attack geometry, history, player behavior and selection differ. This is descriptive evidence that pre-click visual responses occur, not causal proof of warning-time efficacy. Do not conceal approach geometry from Retina.

## Dead-state reporting bias

All-recorded threat fractions are CALM 16.41%, ALERT 10.67%, ESCAPE 72.92%. Post-step-alive fractions are CALM 31.84%, ALERT 20.70%, ESCAPE 47.46%. Dead/splat ticks retain the last state and account for the difference. Future reports should publish both denominators explicitly, as well as all/alive ecology and speed statistics; historical reports must remain intact.

## Scoped controller change to test

Use consumed pointer velocity plus bounded positional correction for ordinary APPROACH, with a continuous filtered velocity command. Keep the 1800 approach and 3200 total caps, acceleration limits, edge reachability and committed-strike mapping. Cap error-driven catch-up separately so stationary or slow inputs do not alone command full speed. No fly-relative stalking flag, hidden threat input, ecology change or fly-speed change is needed. Fixed-trajectory tests and frozen-input comparisons can test this mechanism; a new human session remains necessary for responsiveness and difficulty acceptance.

Validation disposition: share with caveats. Counts and paired distributions are checked, but this is one player/session and does not establish biological fidelity, causality or a general difficulty estimate.

## Subsequent runtime verification

After the pre-tuning diagnosis, exact historical replay was verified for all 15,039 ticks using eight Numba threads and the original source. Four threads diverged at tick 278 because float32 propagation reduction order depends on the thread count omitted by schema 2. Eight is a verified compatible setting, not proof of the uniquely original setting. See [replay evidence](human_m1_7_replay.json) and the [M1.7.1 validation](M1_7_1.md). The historical recording remains byte-identical.
