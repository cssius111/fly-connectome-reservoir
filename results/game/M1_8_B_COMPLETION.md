# M1.8-B completion: validation of stages B2c to B5

Status: **accepted by the user on 2026-10-22** after the local checks and the playtest in
section 11. Design and
acceptance checks were preregistered in
[game/M1_8_B_COMPLETION_DESIGN.md](../../game/M1_8_B_COMPLETION_DESIGN.md) before any stage
changed code, under the authorization in [game/M1_8_B_PLAN.md](../../game/M1_8_B_PLAN.md)
section 14. Baseline: the accepted runtime `feature/m1-8-b3a` @ `6b43c0f` (ROOM
`config_version` 19). One combined human playtest follows the last stage.

## 1. B2c: evaluation metrics and the B3a baseline

`tools/kinematics_sanity.py` fixes the metrics before any behaviour changes. It is
deterministic: two runs of the same seed and thread count give identical output. Baseline on
the accepted B3a configuration, six seeds x 180 s, no player, one Numba thread
(`artifacts/m1_8_b2c/b3a`, 18.0 alive minutes):

| Measure | B3a baseline |
| --- | --- |
| Lifecycle: airborne / perched / feeding | 85.7 % / 14.3 % / 12.8 % of alive time |
| Ecology-driven share: EXPLORE / TRANSIT / ODOR_SEARCH / ODOR_TRACK / RECOVER | 42.4 / 23.8 / 16.7 / 16.6 / 0.4 % |
| Speed, mean (sd) BL/s: EXPLORE / TRANSIT / ODOR_TRACK / ODOR_SEARCH / RECOVER | 6.79 (0.89) / 9.69 (1.69) / 10.41 (0.95) / 6.37 (1.61) / 8.84 (1.47) |
| Acceleration p90 / deceleration p90, BL/s^2, EXPLORE | 1.46 / 4.35 |
| Settling time to within 0.5 BL/s of target, median s: EXPLORE / ODOR_TRACK / ODOR_SEARCH | 0.58 / 0.66 / 0.12 |
| Completed episodes, mean s: EXPLORE / TRANSIT / ODOR_TRACK / ODOR_SEARCH | 4.05 / 3.19 / 4.78 / 5.37 |
| ODOR_TRACK episodes ending at the 8 s timer | 17 of 58 |
| ODOR_SEARCH episodes ending at the 6 s timer | 23 of 27 |
| Transitions EXPLORE -> TRANSIT / TRANSIT -> EXPLORE | 65 / 53 |
| Turns per airborne minute: SACCADE / CORRECTION / AVOID / DEPART / ALERT | 10.6 / 11.0 / 5.4 / 1.9 / 1.4 |
| Spontaneous-turn interval, median (p90) | 1.68 s (6.90 s) |
| Drift yaw rate between pulses, mean absolute | 0.26 rad/s |
| Odor detected / encounters / upwind heading while tracking | 31.5 % of alive time / 2.0 per min / 60.6 % |
| Touchdowns: food / elsewhere | 12 / 2 (one seed never reached the food) |
| Flight bout / perch bout, median (complete bouts) | 38.8 s (9) / 9.6 s (14) |
| Visited share of the 10 BL grid / time near a wall | 52.3 % / 18.4 % of airborne time |
| Policy escape onsets | 0 |

## 2. B2d: ODOR_SEARCH and RECOVER speed sampling

Implementation: `game/kinematics.py` (the sampler keeps one stream per context: ODOR_SEARCH
+36263, RECOVER +42061), `game/world.py`, `game_room_config.json` (`config_version` 20, two
`kinematics` blocks, the record path), `results/game/calibration_room_m1_8_b2d.json` (written by
`tools/m1_8_b_stage_record.py`), `test_game_m1_8_b_completion.py` and
`test_game_m1_8_b_stages.py` (new); `test_game_b3a.py` is bound to the frozen B3a configuration.

**Check 1.** Code alone: bit-identical; combined SHA256 `6187dbef...` before and `6187dbef...` after; new streams: kinematics_odor_search, kinematics_recover. The new streams are present and untouched in every scenario.

**Check 2.** Every diverging scenario diverges first at its first ecology-driven ODOR_SEARCH or
RECOVER tick, that is the first such tick that is airborne, outside an ALERT or ESCAPE pulse and
not steered by the policy (`World._neural_active`, |turn| > 0.03):

| Scenario | Identical | First divergence | First ecology-driven ODOR_SEARCH / RECOVER tick |
| --- | --- | --- | --- |
| `room_quiet` | no | tick 972: x | 972 |
| `room_perched_threat` | no | tick 326: x | 326 |
| `room_approach_threat` | no | tick 109: x | 109 |
| `room_airborne_seed101` | no | tick 700: x | 700 |
| `room_no_ecology` | **yes** | none | None |
| `game_preset` | **yes** | none | None |
| `lab_preset` | **yes** | none | None |

Combined SHA256 `6187dbef...` -> `68231e29...`.

**Check 3.** `test_game_m1_8_b_completion.py` (B2d): the configured envelopes, one draw per
episode from the context's own stream and seed offset, 200,000 offline draws per context within
0.01 BL/s of the triangular mean (5.5 and 6.5) and standard deviation (0.612), every draw in its
support, the EXPLORE and ODOR_TRACK draw sequences unchanged, LAB, GAME and B3a configurations
unsampled, rejection of an invalid specification. `test_game_m1_8_b_stages.py`: scope, record
chain, provenance and stream offsets. Full suite: 465 tests; one B2b-iii provenance test assumed
that the current `kinematics` block equals B2b-iii's exactly and now checks that every B2b-iii
value is kept; it and the suite then pass.

**Checks 4 and 5.** Metrics, B3a -> B2d (six seeds x 180 s):

| State | Driving share | Speed mean BL/s | Episode mean s | Episode median s |
| --- | --- | --- | --- | --- |
| ALERT | 0.0 % -> 0.0 % | - -> - | 0.05 -> 0.06 | 0.06 -> 0.06 |
| EXPLORE | 42.4 % -> 46.0 % | 6.79 -> 6.87 | 4.05 -> 4.04 | 4.44 -> 4.14 |
| ODOR_SEARCH | 16.7 % -> 11.4 % | 6.37 -> 5.94 | 5.37 -> 5.18 | 6.02 -> 6.02 |
| ODOR_TRACK | 16.6 % -> 15.0 % | 10.41 -> 10.36 | 4.78 -> 5.45 | 4.92 -> 7.14 |
| RECOVER | 0.4 % -> 0.7 % | 8.84 -> 8.18 | 0.22 -> 0.22 | 0.22 -> 0.22 |
| TRANSIT | 23.8 % -> 26.9 % | 9.69 -> 9.69 | 3.19 -> 3.24 | 3.32 -> 3.32 |

Lifecycle airborne / perched / feeding: 85.7 / 14.3 / 12.8 % -> 81.0 / 19.0 / 18.4 %; touchdowns food+other 12+2 -> 14+2; visited cells 52.3 % -> 56.4 %; upwind share while tracking 60.6 % -> 60.0 %; escape onsets 0 -> 0. Pathology screen: pass. ODOR_SEARCH speed sd falls from 1.61 to 1.06 BL/s and RECOVER from 1.47 to 0.89 BL/s, as
the U-shaped sinusoid time density is replaced by one draw per episode.

**Check 6.** Paired free flight, seeds 9201-9280, the B3a arm reused (check 1 holds):

| | Previous stage | B2d |
| --- | --- | --- |
| Alive minutes | 240.0 | 240.0 |
| Escapes (rate, exact 95 % upper bound) | 10 (0.042/min, 0.071) | 11 (0.046/min, 0.076) |
| A | 1 (upper 0.020) | 0 (upper 0.012) |
| B | 1 (upper 0.020) | 2 (upper 0.026) |
| C | 0 (upper 0.012) | 0 (upper 0.012) |
| D | 8 (upper 0.060) | 9 (upper 0.065) |
| Perched escapes | 0 | 0 |

Seeds with identical escape ticks: 63. Category B criterion met: True. The two arms share the category B event of seed 9249 at tick 2042 (before any B2d
divergence in that seed); the other B2d category B event (seed 9219, tick 6212, 1,634 units from
the paddle) is new. The B3a category A event (seed 9232, tick 6485) does not recur because that
run diverges earlier.

**Check 7.** Lifecycle scenarios replay exactly with their accepted event sets (voluntary 1,200,
perched threat 340, approach threat 120 ticks); recorder exact replay (1,200 ticks, 1,212 input
operations, schema 4, `config_version` 20); escape/cruise study and M1.7.1 swatter fixtures
identical; ROOM resolves 1.45 through the B2d record.

**B2d passes and is adopted.**

## 3. B2e: sampled speed-transition time constant

Implementation (`72eb8e7`): `game/kinematics.py` (the sampler draws one damping rate per new
episode target from its own stream, +47933; the resolver applies it to ecological profiles
only), `game/world.py`, `game_room_config.json` (`config_version` 21,
`kinematics.speed_relaxation_per_second`), `results/game/calibration_room_m1_8_b2e.json`.

**Check 1.** Code alone: bit-identical; combined SHA256 `68231e29...` before and `68231e29...` after; new streams: kinematics_relaxation. The relaxation stream is untouched under `config_version` 20.

**Check 2.** Every ROOM scenario with ecology diverges at tick 0, its first ecology-driven
EXPLORE tick, where the first drawn rate replaces 3.0 /s:

| Scenario | Identical | First divergence | First ecology-driven EXPLORE / ODOR_TRACK / ODOR_SEARCH / RECOVER tick |
| --- | --- | --- | --- |
| `room_quiet` | no | tick 0: x | 0 |
| `room_perched_threat` | no | tick 0: x | 0 |
| `room_approach_threat` | no | tick 0: x | 0 |
| `room_airborne_seed101` | no | tick 0: x | 0 |
| `room_no_ecology` | **yes** | none | None |
| `game_preset` | **yes** | none | None |
| `lab_preset` | **yes** | none | None |

Combined SHA256 `68231e29...` -> `ad233ba0...`.

**Check 3.** B2e tests: the configured support, one rate per sampled episode from its own stream
and seed offset, the accepted rate kept for TRANSIT and threat-priority ticks, speed draws
unchanged by the new stream, the resolver applying the rate only to ecological profiles, a
300-tick World run with every drawn rate replaced by 3.0 equal to the B2d configuration, and
rejection of a degenerate support. **471 tests pass.**

**Checks 4 and 5.** Metrics, B2d -> B2e:

| State | Driving share | Speed mean BL/s | Episode mean s | Episode median s |
| --- | --- | --- | --- | --- |
| ALERT | 0.0 % -> 0.0 % | - -> - | 0.06 -> 0.05 | 0.06 -> 0.06 |
| ESCAPE | 0.0 % -> 0.0 % | - -> 16.94 | - -> 0.42 | - -> 0.42 |
| EXPLORE | 46.0 % -> 45.9 % | 6.87 -> 6.84 | 4.04 -> 4.37 | 4.14 -> 4.54 |
| ODOR_SEARCH | 11.4 % -> 13.8 % | 5.94 -> 5.95 | 5.18 -> 5.16 | 6.02 -> 6.02 |
| ODOR_TRACK | 15.0 % -> 12.5 % | 10.36 -> 10.52 | 5.45 -> 5.31 | 7.14 -> 5.66 |
| RECOVER | 0.7 % -> 0.6 % | 8.18 -> 8.78 | 0.22 -> 0.30 | 0.22 -> 0.22 |
| TRANSIT | 26.9 % -> 27.2 % | 9.69 -> 9.71 | 3.24 -> 3.17 | 3.32 -> 3.22 |

Lifecycle airborne / perched / feeding: 81.0 / 19.0 / 18.4 % -> 84.8 / 15.2 / 14.9 %; touchdowns food+other 14+2 -> 12+1; visited cells 56.4 % -> 52.2 %; upwind share while tracking 60.0 % -> 58.8 %; escape onsets 0 -> 2. Pathology screen: pass.

Settling time to within 0.5 BL/s of the target, median (s), B2d -> B2e: EXPLORE 0.50 -> 0.58,
ODOR_TRACK 0.70 -> 0.78, ODOR_SEARCH 0.82 -> 0.80, RECOVER 0.00 -> 0.12. The 90th percentiles of
acceleration and deceleration move by at most a few tenths of a BL/s^2 except RECOVER
deceleration (9.7 -> 13.8 BL/s^2, 77 -> 274 samples in short post-escape episodes).

**Check 6.** Paired free flight, the B2d arm reused:

| | Previous stage | B2e |
| --- | --- | --- |
| Alive minutes | 240.0 | 240.0 |
| Escapes (rate, exact 95 % upper bound) | 11 (0.046/min, 0.076) | 14 (0.058/min, 0.091) |
| A | 0 (upper 0.012) | 0 (upper 0.012) |
| B | 2 (upper 0.026) | 2 (upper 0.026) |
| C | 0 (upper 0.012) | 1 (upper 0.020) |
| D | 9 (upper 0.065) | 11 (upper 0.076) |
| Perched escapes | 0 | 0 |

Seeds with identical escape ticks: 58. Category B criterion met: True. Category D rises from 9 to 11; individually these counts are within Poisson noise
(about 10 +/- 3), and B5 compares the whole chain with B3a on fresh seeds.

**Check 7.** Lifecycle scenarios replay exactly with their accepted event sets; recorder exact
replay (1,200 ticks, schema 4, `config_version` 21); escape/cruise study and swatter fixtures
identical; ROOM resolves 1.45 through the B2e record.

**B2e passes and is adopted.**

## 4. B3b: odor timers replaced by encounter history

Implementation (`bf04652`): `game/ecology.py` (the `odor_history` block, the history H, the
abandonment and give-up hazards on their own stream, +53113), `game_room_config.json`
(`config_version` 22), `results/game/calibration_room_m1_8_b3b.json`.

**Check 1.** Code alone: bit-identical; combined SHA256 `ad233ba0...` before and `ad233ba0...` after; new streams: odor_history. The odor-history stream is untouched under `config_version` 21.

**Check 2.** With `config_version` 22:

| Scenario | Identical | First divergence | First ecology-driven ODOR_TRACK tick |
| --- | --- | --- | --- |
| `room_quiet` | no | tick 196: label[15] | 908 |
| `room_perched_threat` | no | tick 196: label[15] | None |
| `room_approach_threat` | **yes** | none | None |
| `room_airborne_seed101` | no | tick 107: vx | 87 |
| `room_no_ecology` | **yes** | none | None |
| `game_preset` | **yes** | none | None |
| `lab_preset` | **yes** | none | None |

Combined SHA256 `ad233ba0...` -> `ef762a10...`.

- Seed 255 (`room_quiet`, `room_perched_threat`) diverges at tick 196 in the ecology label
  (ODOR_TRACK -> TRANSIT): an abandonment draw ends the plume episode, which the accepted 8 s
  timer would have ended at tick 405. Its earlier ODOR_TRACK ticks are lifecycle-owned (landing
  approach and perching), so their attenuated steering is not executed.
- Seed 101 diverges at tick 107. Its first ecology-driven ODOR_TRACK tick is 87, but the upwind
  steering target exceeds the 0.9 rad/s cap in both configurations until tick 106; a direct run
  shows the smoothed ecological steering first differing at tick 107, when the attenuated target
  falls below the cap.
- `room_approach_threat` keeps identical rows; it consumes hazard draws without an event.

**Check 3.** B3b tests: H rises in odor and decays outside, within [0, 1]; over 40 seeds of
alternating 8 s odor and no-odor blocks fewer than a tenth of the ODOR_TRACK bouts last
8.00 +/- 0.03 s and fewer than a tenth of the searches 6.00 +/- 0.03 s, and every search ended by
giving up lasts at least 1 s; abandonment enters TRANSIT with the 1 s refractory; history weakens
the upwind turn; the mechanism is gated by its block. Three accepted-timer tests now pin the
M1.6 mechanism on the ecology parameters without the completion blocks (`test_game_m1_6.py`,
`test_game_lifecycle.py`). **477 tests pass.**

**Checks 4 and 5.** Metrics, B2e -> B3b:

| State | Driving share | Speed mean BL/s | Episode mean s | Episode median s |
| --- | --- | --- | --- | --- |
| ALERT | 0.0 % -> 0.0 % | - -> - | 0.05 -> 0.06 | 0.06 -> 0.06 |
| ESCAPE | 0.0 % -> 0.0 % | 16.94 -> - | 0.42 -> - | 0.42 -> - |
| EXPLORE | 45.9 % -> 48.5 % | 6.84 -> 6.82 | 4.37 -> 3.67 | 4.54 -> 4.00 |
| ODOR_SEARCH | 13.8 % -> 12.5 % | 5.95 -> 6.06 | 5.16 -> 3.99 | 6.02 -> 2.82 |
| ODOR_TRACK | 12.5 % -> 12.9 % | 10.52 -> 10.38 | 5.31 -> 3.00 | 5.66 -> 2.02 |
| RECOVER | 0.6 % -> 0.7 % | 8.78 -> 7.92 | 0.30 -> 0.22 | 0.22 -> 0.22 |
| TRANSIT | 27.2 % -> 25.3 % | 9.71 -> 9.72 | 3.17 -> 2.09 | 3.22 -> 1.62 |

Lifecycle airborne / perched / feeding: 84.8 / 15.2 / 14.9 % -> 85.2 / 14.8 / 13.8 %; touchdowns food+other 12+1 -> 12+1; visited cells 52.2 % -> 55.0 %; upwind share while tracking 58.8 % -> 48.3 %; escape onsets 2 -> 0. Pathology screen: pass.

Hard checks: 1 of 87 completed ODOR_TRACK episodes lasts within one tick of 8.02 s (a hazard
coincidence; 17 of 58 at B3a) and none of 27 searches within one tick of 6.02 s (23 of 27 at
B3a); the 4 searches shorter than 1 s ended by reacquisition or a threat. The episode counts
show an emergent pattern the design did not anticipate: ODOR_TRACK -> TRANSIT (54) and
TRANSIT -> ODOR_TRACK (60) alternate while a habituated fly stays in the plume, because the 1 s
refractory rarely carries it out; median ODOR_TRACK and TRANSIT episodes fall to 2.0 s and 1.6 s.
Nothing is retuned for it.

Sensitivity (three seeds, 101 / 4242 / 1729, 180 s each; the stage value first):

| Variant | ODOR_TRACK mean / median s | Upwind share | Perched | Food touchdowns | Visited cells |
| --- | --- | --- | --- | --- | --- |
| stage (attenuation 0.5, abandon 3 s) | 3.02 / 1.86 | 41.0 % | 12.9 % | 6 | 56.7 % |
| `upwind_attenuation` 0 (ablation) | 2.81 / 1.98 | 65.1 % | 14.5 % | 9 | 46.5 % |
| `upwind_attenuation` 0.75 | 3.01 / 1.86 | 41.7 % | 21.3 % | 9 | 54.6 % |
| `abandon_seconds` 2 | 2.41 / 1.66 | 37.1 % | 23.2 % | 11 | 49.5 % |
| `abandon_seconds` 4.5 | 3.58 / 1.98 | 55.5 % | 11.4 % | 5 | 57.4 % |

Removing the attenuation restores the upwind share; abandonment time shifts bout length in the
expected direction. With three chaotic 180 s runs the perched and touchdown columns are noisy
and are not read as trends.

**Check 6.** Paired free flight, the B2e arm reused:

| | Previous stage | B3b |
| --- | --- | --- |
| Alive minutes | 240.0 | 240.0 |
| Escapes (rate, exact 95 % upper bound) | 14 (0.058/min, 0.091) | 10 (0.042/min, 0.071) |
| A | 0 (upper 0.012) | 0 (upper 0.012) |
| B | 2 (upper 0.026) | 2 (upper 0.026) |
| C | 1 (upper 0.020) | 3 (upper 0.032) |
| D | 11 (upper 0.076) | 5 (upper 0.044) |
| Perched escapes | 0 | 0 |

Seeds with identical escape ticks: 63. Category B criterion met: True.

**Check 7.** Lifecycle scenarios replay exactly with their accepted event sets; recorder exact
replay (schema 4, `config_version` 22); escape/cruise study and swatter fixtures identical; ROOM
resolves 1.45 through the B3b record.

**B3b passes and is adopted.**

## 5. B3c: EXPLORE and TRANSIT dwell timers replaced by evidence-gated hazards

Implementation (`ddd702d`): `game/ecology.py` (the `intent_hazards` block and its stream,
+59011), `game_room_config.json` (`config_version` 23), `results/game/calibration_room_m1_8_b3c.json`.

**Check 1.** Code alone: bit-identical; combined SHA256 `ef762a10...` before and `ef762a10...` after; new streams: intent.

**Check 2.** With `config_version` 23 the seven trace scenarios keep identical rows; only
`room_airborne_seed101` consumes hazard draws:

| Scenario | Identical | First divergence | First ecology-driven EXPLORE / TRANSIT tick |
| --- | --- | --- | --- |
| `room_quiet` | **yes** | none | 0 |
| `room_perched_threat` | **yes** | none | 0 |
| `room_approach_threat` | **yes** | none | 0 |
| `room_airborne_seed101` | **yes** | none | 0 |
| `room_no_ecology` | **yes** | none | None |
| `game_preset` | **yes** | none | None |
| `lab_preset` | **yes** | none | None |

None of the trace windows reaches an EXPLORE or TRANSIT dwell end, so the preregistered trace
check does not exercise this stage. Sequential 180 s runs of the B3b and B3c configurations
(seeds 101, 255, 4242) locate the first divergence instead: in every seed it is an EXPLORE /
TRANSIT switch decided differently by the hazard and by the accepted dwell, with identical
positions until then (seed 101, tick 983: the hazard ends EXPLORE after 2.06 s where the dwell
was 4.63 s; seed 255, tick 1494, and seed 4242, tick 315: the accepted dwell expires at 4.74 s
and 6.32 s while the hazard has not fired).

**Check 3.** B3c tests: over 60 seeds without structure every EXPLORE and TRANSIT episode lasts
at least the 1 s minimum dwell and the means are within 0.6 s of 5.0 s and 3.5 s; structure
prolongs EXPLORE and shortens TRANSIT; the hazard stream is untouched without the block.
**480 tests pass.**

**Checks 4 and 5.** Metrics, B3b -> B3c:

| State | Driving share | Speed mean BL/s | Episode mean s | Episode median s |
| --- | --- | --- | --- | --- |
| ALERT | 0.0 % -> 0.0 % | - -> - | 0.06 -> 0.06 | 0.06 -> 0.06 |
| ESCAPE | 0.0 % -> 0.0 % | - -> 16.25 | - -> 0.42 | - -> 0.42 |
| EXPLORE | 48.5 % -> 47.2 % | 6.82 -> 6.79 | 3.67 -> 3.61 | 4.00 -> 2.68 |
| ODOR_SEARCH | 12.5 % -> 14.5 % | 6.06 -> 6.05 | 3.99 -> 4.60 | 2.82 -> 4.18 |
| ODOR_TRACK | 12.9 % -> 9.8 % | 10.38 -> 10.44 | 3.00 -> 3.14 | 2.02 -> 1.86 |
| RECOVER | 0.7 % -> 1.2 % | 7.92 -> 8.17 | 0.22 -> 0.29 | 0.22 -> 0.22 |
| TRANSIT | 25.3 % -> 27.3 % | 9.72 -> 9.66 | 2.09 -> 2.04 | 1.62 -> 1.20 |

Lifecycle airborne / perched / feeding: 85.2 / 14.8 / 13.8 % -> 81.8 / 18.2 / 17.9 %; touchdowns food+other 12+1 -> 15+1; visited cells 55.0 % -> 48.4 %; upwind share while tracking 48.3 % -> 53.8 %; escape onsets 0 -> 3. Pathology screen: pass. EXPLORE and TRANSIT episodes become more variable (EXPLORE up to 21 s, TRANSIT up to
11.6 s). Hard check, on the episode-end record of the final configuration (which contains B3c):
all 17 EXPLORE and TRANSIT episodes shorter than 1 s end in ALERT or ODOR_TRACK, none in an
EXPLORE/TRANSIT switch.

Sensitivity (seeds 101 / 4242 / 1729): `structure_gain` 0 (ablation), 0.5 and 1.0 give EXPLORE
means of 3.37, 3.45 and 3.45 s and TRANSIT means of 1.79, 1.92 and 1.92 s; the runs at 0.5 and
1.0 are identical. **The visual-structure gate is nearly inert in ROOM:** the local structure
u stays around 0.01 because the fly is rarely near an object, so at the preregistered reference
the hazards are close to constant rates after the minimum dwell. Nothing is retuned for it.

**Check 6.** Paired free flight, the B3b arm reused:

| | Previous stage | B3c |
| --- | --- | --- |
| Alive minutes | 240.0 | 240.0 |
| Escapes (rate, exact 95 % upper bound) | 10 (0.042/min, 0.071) | 8 (0.033/min, 0.060) |
| A | 0 (upper 0.012) | 0 (upper 0.012) |
| B | 2 (upper 0.026) | 2 (upper 0.026) |
| C | 3 (upper 0.032) | 2 (upper 0.026) |
| D | 5 (upper 0.044) | 4 (upper 0.038) |
| Perched escapes | 0 | 0 |

Seeds with identical escape ticks: 67. Category B criterion met: True.

**Check 7.** Lifecycle scenarios replay exactly with their accepted event sets; recorder exact
replay (schema 4, `config_version` 23); escape/cruise study and swatter fixtures identical; ROOM
resolves 1.45 through the B3c record.

**B3c passes and is adopted.**

## 6. B3d: fixed oscillators replaced by resampled-period oscillators

Implementation (`c488c17`): `game/ecology.py` (the `search_half_period_seconds` casting
oscillator and its stream, +64747), `game/world.py` (`fly.curvature.period_sampling` and the
drift stream, +70001), `game_room_config.json` (`config_version` 24),
`results/game/calibration_room_m1_8_b3d.json`.

**Check 1.** Code alone: bit-identical; combined SHA256 `ef762a10...` before and `ef762a10...` after; new streams: casting, curvature. The casting and drift streams are untouched under `config_version` 23.

**Check 2.** With `config_version` 24:

| Scenario | Identical | First divergence | First ecology-driven EXPLORE / TRANSIT / ODOR_TRACK / ODOR_SEARCH / RECOVER tick |
| --- | --- | --- | --- |
| `room_quiet` | no | tick 0: vx | 0 |
| `room_perched_threat` | no | tick 0: vx | 0 |
| `room_approach_threat` | no | tick 0: vx | 0 |
| `room_airborne_seed101` | no | tick 0: vx | 0 |
| `room_no_ecology` | no | tick 0: vx | None |
| `game_preset` | **yes** | none | None |
| `lab_preset` | **yes** | none | None |

Combined SHA256 `ef762a10...` -> `f73371d9...`.

Every ROOM scenario diverges at tick 0, the first airborne tick, through the resampled drift.
**Deviation from the common rule:** section 1 of the design expects `room_no_ecology` to stay
bit-identical, but the drift oscillator is ordinary ROOM flight in `game/world.py`, not
ecology, and section 7 places its first divergence at the first airborne tick; the no-ecology
ROOM scenario therefore diverges too. This is an inconsistency in the preregistration, not a
leak: GAME, which has its own fixed curvature, and LAB stay bit-identical. The casting change is
masked by the earlier drift divergence and is checked by unit tests.

**Check 3.** B3d tests: casting half-periods redrawn within 1.2-2.4 s with the phase restarting
on ODOR_SEARCH entry; drift half-periods redrawn within 0.25-0.75 times each period with the
drift bounded by the summed amplitudes; GAME and the B3c configuration unsampled. **483 tests
pass.**

**Checks 4 and 5.** Metrics, B3c -> B3d:

| State | Driving share | Speed mean BL/s | Episode mean s | Episode median s |
| --- | --- | --- | --- | --- |
| ALERT | 0.0 % -> 0.0 % | - -> - | 0.06 -> 0.06 | 0.06 -> 0.06 |
| ESCAPE | 0.0 % -> 0.0 % | 16.25 -> 21.51 | 0.42 -> 0.42 | 0.42 -> 0.42 |
| EXPLORE | 47.2 % -> 45.4 % | 6.79 -> 6.84 | 3.61 -> 3.60 | 2.68 -> 2.58 |
| ODOR_SEARCH | 14.5 % -> 15.8 % | 6.05 -> 5.87 | 4.60 -> 5.64 | 4.18 -> 4.36 |
| ODOR_TRACK | 9.8 % -> 11.1 % | 10.44 -> 10.17 | 3.14 -> 2.98 | 1.86 -> 1.86 |
| RECOVER | 1.2 % -> 0.8 % | 8.17 -> 8.51 | 0.29 -> 0.25 | 0.22 -> 0.22 |
| TRANSIT | 27.3 % -> 26.9 % | 9.66 -> 9.61 | 2.04 -> 2.10 | 1.20 -> 1.34 |

Lifecycle airborne / perched / feeding: 81.8 / 18.2 / 17.9 % -> 84.6 / 15.4 / 15.4 %; touchdowns food+other 15+1 -> 11+0; visited cells 48.4 % -> 51.2 %; upwind share while tracking 53.8 % -> 55.1 %; escape onsets 3 -> 1. Pathology screen: pass. The spontaneous-turn interval median moves from 1.70 s to 1.76 s and the mean absolute
drift yaw rate from 0.236 to 0.257 rad/s.

**Check 6.** Paired free flight, the B3c arm reused:

| | Previous stage | B3d |
| --- | --- | --- |
| Alive minutes | 240.0 | 240.0 |
| Escapes (rate, exact 95 % upper bound) | 8 (0.033/min, 0.060) | 11 (0.046/min, 0.076) |
| A | 0 (upper 0.012) | 0 (upper 0.012) |
| B | 2 (upper 0.026) | 2 (upper 0.026) |
| C | 2 (upper 0.026) | 0 (upper 0.012) |
| D | 4 (upper 0.038) | 9 (upper 0.065) |
| Perched escapes | 0 | 0 |

Seeds with identical escape ticks: 63. Category B criterion met: True.

**Check 7.** Lifecycle scenarios replay exactly with their accepted event sets; recorder exact
replay (schema 4, `config_version` 24); swatter fixtures identical; ROOM resolves 1.45 through
the B3d record. The escape/cruise study's conclusions are unchanged (54 cases, no analytic-model
mismatch, 18 cases that reduce speed, lowest reduced pre-escape speed 60 BL/s), but its per-case
values differ in the fifth significant digit: the study's one-tick and 30-tick World runs include
the ROOM drift turn, which B3d changes by design. The escape mechanics are unchanged.

**B3d passes and is adopted.**

## 7. B4a: the odor derivative and the bilateral difference

Implementation (`f00ca74`): `game/ecology.py` (the `odor_cues` block; no new random stream),
`game_room_config.json` (`config_version` 25), `results/game/calibration_room_m1_8_b4a.json`.

**Check 1.** Code alone: bit-identical; combined SHA256 `f73371d9...` before and `f73371d9...` after; new streams: none.

**Check 2.** With `config_version` 25:

| Scenario | Identical | First divergence | First ecology-driven ODOR_TRACK tick |
| --- | --- | --- | --- |
| `room_quiet` | no | tick 908: vx | 952 |
| `room_perched_threat` | **yes** | none | None |
| `room_approach_threat` | **yes** | none | None |
| `room_airborne_seed101` | no | tick 100: vx | 87 |
| `room_no_ecology` | **yes** | none | None |
| `game_preset` | **yes** | none | None |
| `lab_preset` | **yes** | none | None |

Combined SHA256 `f73371d9...` -> `679fd494...`.

- Seed 101 diverges at tick 100: its first ecology-driven ODOR_TRACK tick is 87, and as in B3b
  the upwind target exceeds the steering cap in both configurations until the turn has closed
  enough of the error.
- Seed 255 (`room_quiet`) diverges at tick 908, its first ecology-driven tick after takeoff,
  in TRANSIT. A direct run shows the smoothed ecological steering first differing at tick 246,
  in ODOR_TRACK while the fly is perched, where the command is not executed; the smoothed
  value carries into flight. The other seed-255 scenarios end before takeoff and stay identical.

**Check 3.** B4a tests: a bilateral difference turns toward the stronger side symmetrically;
rising odor strengthens and falling odor weakens an upwind turn below the cap; zero gains
reproduce B3d's commands exactly; steering stays within the cap under extreme cues. **487 tests
pass.**

**Checks 4 and 5.** Metrics, B3d -> B4a:

| State | Driving share | Speed mean BL/s | Episode mean s | Episode median s |
| --- | --- | --- | --- | --- |
| ALERT | 0.0 % -> 0.0 % | - -> - | 0.06 -> 0.06 | 0.06 -> 0.06 |
| ESCAPE | 0.0 % -> 0.0 % | 21.51 -> - | 0.42 -> - | 0.42 -> - |
| EXPLORE | 45.4 % -> 46.0 % | 6.84 -> 6.71 | 3.60 -> 4.05 | 2.58 -> 2.88 |
| ODOR_SEARCH | 15.8 % -> 12.6 % | 5.87 -> 5.96 | 5.64 -> 4.64 | 4.36 -> 3.40 |
| ODOR_TRACK | 11.1 % -> 15.5 % | 10.17 -> 9.54 | 2.98 -> 3.00 | 1.86 -> 2.46 |
| RECOVER | 0.8 % -> 0.6 % | 8.51 -> 8.22 | 0.25 -> 0.22 | 0.22 -> 0.22 |
| TRANSIT | 26.9 % -> 25.3 % | 9.61 -> 9.55 | 2.10 -> 1.90 | 1.34 -> 1.16 |

Lifecycle airborne / perched / feeding: 84.6 / 15.4 / 15.4 % -> 85.0 / 15.0 / 11.9 %; touchdowns food+other 11+0 -> 10+4; visited cells 51.2 % -> 53.4 %; upwind share while tracking 55.1 % -> 66.1 %; escape onsets 1 -> 0. Pathology screen: pass.

Sensitivity (seeds 101 / 4242 / 1729; the stage value is bilateral gain 0.3, rate gain 0.25):

| Variant | ODOR_TRACK mean / median s | Upwind share | Odor detected | Perched | Food touchdowns |
| --- | --- | --- | --- | --- | --- |
| stage | 3.26 / 2.56 | 68.1 % | 30.9 % | 11.8 % | 6 |
| `bilateral_gain` 0 (ablation) | 3.29 / 2.04 | 53.4 % | 38.3 % | 22.3 % | 10 |
| `bilateral_gain` 0.6 | 3.49 / 2.16 | 56.1 % | 39.4 % | 18.9 % | 9 |
| `rate_gain` 0 (ablation) | 3.27 / 1.86 | 54.4 % | 35.7 % | 21.2 % | 8 |
| `rate_gain` 0.5 | 3.06 / 2.30 | 53.8 % | 32.2 % | 16.2 % | 8 |

With three chaotic 180 s runs per variant these differences are within run-to-run variation
and are not read as effects of either gain.

**Check 6.** Paired free flight, the B3d arm reused:

| | Previous stage | B4a |
| --- | --- | --- |
| Alive minutes | 240.0 | 240.0 |
| Escapes (rate, exact 95 % upper bound) | 11 (0.046/min, 0.076) | 12 (0.050/min, 0.081) |
| A | 0 (upper 0.012) | 0 (upper 0.012) |
| B | 2 (upper 0.026) | 3 (upper 0.032) |
| C | 0 (upper 0.012) | 2 (upper 0.026) |
| D | 9 (upper 0.065) | 7 (upper 0.055) |
| Perched escapes | 0 | 0 |

Seeds with identical escape ticks: 60. Category B criterion met: True.

**Check 7.** Lifecycle scenarios replay exactly with their accepted event sets; recorder exact
replay (schema 4, `config_version` 25); escape/cruise study and swatter fixtures identical; ROOM
resolves 1.45 through the B4a record.

**B4a passes and is adopted.**

## 8. B4b: wind reliability and a still-air search

Implementation (`4fb5ef5`): `game/ecology.py` (the `wind_reliability` block),
`game_room_config.json` (`config_version` 26), `results/game/calibration_room_m1_8_b4b.json`.

**Checks 1 and 2.** With the new code and `config_version` 25 all seven trace scenarios are
bit-identical to the B4a capture (combined SHA256 `679fd494...`), and with `config_version` 26
they are bit-identical as well: ROOM wind never falls below 38.25 units/s, so the reliability
is 1 throughout and multiplying the upwind steering by it is exact. As preregistered, the
paired check is therefore not re-run for B4b.

**Check 3.** B4b tests: the reliability ramp (0 at or below 5 units/s, 0.5 at 12.5, 1 from
20), ROOM's minimum wind above the reliable threshold, a still-air ODOR_SEARCH that still
casts both ways without an upwind reference, and exact reproduction of B4a's commands in
reliable wind. **491 tests pass.**

**Low-wind control** (diagnostic only, not a runtime configuration: ROOM with wind speed 3
units/s, three seeds, 180 s each, the same code):

| Measure | B4a configuration | B4b configuration |
| --- | --- | --- |
| Reliability | not modelled (ideal wind) | 0 (still air) |
| ODOR_TRACK / ODOR_SEARCH share of ecology-driven ticks | 12.9 % / 14.9 % | 17.3 % / 14.3 % |
| Upwind heading share while tracking | 53.9 % | 16.1 % |
| Odor detected | 36.5 % of alive time | 24.7 % |
| Food touchdowns / perched share | 8 / 22.5 % | 3 / 5.3 % |
| Visited cells | 50.2 % | 66.9 % |

Under the ideal estimate the fly still steers upwind in a 3 units/s breeze it could not
reliably sense; with the reliability term it casts around its course, keeps tracking by the
bilateral cue only, and finds the food less often. This is the intended difference; the ROOM
runtime is unaffected.

**Check 7.** The ROOM traces are bit-identical to B4a, so the lifecycle, recorder, swatter and
escape/cruise results of B4a carry over; ROOM resolves 1.45 through the B4b record.

**B4b passes and is adopted.**

## 9. B5: combined validation of the completed chain

**Final paired check on fresh seeds 9301-9380** (absent from every earlier check): the accepted
B3a configuration (`6b43c0f`) against the final configuration (`config_version` 26), both run
with the final code (`4fb5ef5`), 80 x 180 s per arm, no player, the pointer parked, one Numba
thread; every escape classified with the N4B4 counterfactual.

| | B3a configuration | Final configuration |
| --- | --- | --- |
| Alive minutes | 240.0 | 240.0 |
| Escapes (rate, exact 95 % upper bound) | 7 (0.029/min, 0.055) | 8 (0.033/min, 0.060) |
| A: no LC4/LPLC2 drive in the 120 ms before | 0 | 0 |
| B: never within 310 units in 1.5 s without the escape | 1 (upper 0.020) | 2 (upper **0.026**) |
| C: near pass, mostly apparent-size expansion | 1 | 0 |
| D: near pass, mostly range expansion (self-approach) | 5 | 6 |
| Perched escapes | 0 | 0 |

The criterion holds for the whole chain: category B under the final configuration is 2 in
240 minutes, upper bound 0.026/min, below 0.1/min. Self-approach escapes, which rose from 2 to 8
when B3a was introduced (seeds 9201-9280), stay at 5 against 6 across the completion stages;
the per-stage counts on seeds 9201-9280 (8, 9, 11, 5, 4, 9, 7) vary within Poisson noise.

**Metrics, B3a -> final** (six seeds x 180 s; the B4a run, which the final configuration
reproduces bit for bit in ROOM):

| Measure | B3a | Final |
| --- | --- | --- |
| Share of ecology-driven ticks: EXPLORE / TRANSIT / ODOR_TRACK / ODOR_SEARCH | 42.4 / 23.8 / 16.6 / 16.7 % | 46.0 / 25.3 / 15.5 / 12.6 % |
| Episode median, s: EXPLORE / TRANSIT / ODOR_TRACK / ODOR_SEARCH | 4.44 / 3.32 / 4.92 / 6.02 | 2.88 / 1.16 / 2.46 / 3.40 |
| Episode mean, s: EXPLORE / TRANSIT / ODOR_TRACK / ODOR_SEARCH | 4.05 / 3.19 / 4.78 / 5.37 | 4.05 / 1.90 / 3.00 / 4.64 |
| ODOR_TRACK / ODOR_SEARCH episodes ending at a fixed timer | 17 of 58 / 23 of 27 | none by a timer |
| Speed mean (sd), BL/s: EXPLORE | 6.79 (0.89) | 6.71 (1.06) |
| TRANSIT | 9.69 (1.69) | 9.55 (2.15) |
| ODOR_TRACK | 10.41 (0.95) | 9.54 (2.99) |
| ODOR_SEARCH | 6.37 (1.61) | 5.96 (1.04) |
| RECOVER | 8.84 (1.47) | 8.22 (1.12) |
| Airborne / perched / feeding | 85.7 / 14.3 / 12.8 % | 85.0 / 15.0 / 11.9 % |
| Touchdowns: food / elsewhere | 12 / 2 | 10 / 4 |
| Upwind heading while tracking | 60.6 % | 66.1 % |
| Odor detected / encounters | 31.5 % / 2.00 per min | 30.6 % / 1.89 per min |
| Visited cells / near a wall | 52.3 % / 18.4 % | 53.4 % / 16.5 % |
| Spontaneous-turn interval median / drift mean absolute | 1.68 s / 0.26 rad/s | 1.88 s / 0.24 rad/s |
| Flight bout / perch bout median (complete bouts) | 38.8 s (9) / 9.6 s (14) | 59.2 s (8) / 11.0 s (12) |
| Policy escape onsets | 0 | 0 |

**Frozen systems on the final configuration.** 491 tests pass. The M1.8-A lifecycle scenarios
replay exactly with their accepted event sets, the recorder replays exactly at schema 4, the
M1.7.1 swatter fixtures are identical, and ROOM resolves 1.45 through the B4b record. The
escape/cruise study's conclusions are unchanged at every stage (its per-case values move only
with B3d's drift, section 6).

**Findings and deviations, collected**

1. *TRANSIT speed.* Its envelope, sinusoid and lag are unchanged, as the user required. Its
   realized speeds are slightly lower and more variable (mean 9.69 -> 9.55 BL/s, sd 1.69 ->
   2.15) because TRANSIT episodes are shorter (median 3.32 -> 1.16 s) and start from other
   states' speeds. ODOR_TRACK shows the same effect more strongly (mean 10.41 -> 9.54, sd 0.95
   -> 2.99) because its episodes are shorter too.
2. *B3b.* A habituated fly that stays in the plume alternates short ODOR_TRACK and 1 s
   TRANSIT episodes (section 4), a consequence the design did not anticipate.
3. *B3c.* The visual-structure gate is nearly inert in ROOM at the preregistered reference
   (section 5); the seven trace scenarios do not reach a dwell end, so sequential runs located
   the first divergence instead.
4. *B3d.* The no-ecology ROOM scenario diverges, against the common preregistered
   expectation, because the drift is ordinary ROOM flight (section 6).
5. *Method.* Each stage reused the previous stage's paired arm, justified by its code-only bit
   identity; B5 ran both arms on fresh seeds. Sensitivity variants have no calibration record
   of their own, so the metrics tool built the stage's fixed policy explicitly (verified
   identical to the session-built policy); three-seed sensitivity runs are dominated by
   run-to-run variation and are not read as effects. A first version of the sequential
   divergence tool shared one brain between two interleaved sessions and was discarded before
   its output was used.
6. *Tests changed rather than behaviour.* The M1.6 timer tests now pin the accepted mechanism
   on the ecology parameters without the completion blocks; the perched HUD test keeps its B3a
   scenario beside a new current-intent test; the B3a and B2b-iii tests bind to their frozen
   configurations. One pre-written B4a test whose inputs saturated the steering cap was
   corrected before the stage commit.

Not done, deliberately: TRANSIT speed, flight-bout termination (owned by the frozen M1.8-A
lifecycle), crosswind casting, any recorder schema change, any learning.

## 10. Status and acceptance procedure

All preregistered automated checks pass for every stage, with the deviations above. **The user
accepted B2c-B4b on 2026-10-22** after the local checks and the playtest (section 11). The
accepted runtime branch is `feature/m1-8-b-complete`; `feature/m1-8-b3a` @ `6b43c0f` stays as the
previous accepted runtime. The acceptance procedure was:

1. **Local checks** in a fresh LF worktree of the session branch (safe removal of an old
   worktree: `results/game/M1_8_B2B_III.md` section 11): protected files 20 of 20,
   `verify_results.py`, the suite (491 tests), and `tools/approach_sanity.py` on the M1.7.1
   acceptance recording (old == new).
2. **Playtest.** `python -m game.app --arena room --seed 255 --record --windowed`. Leave the
   mouse still for a few minutes and watch for irregular rather than timed EXPLORE/TRANSIT
   switching, tracking in bursts with departures and returns, landings on the food, irregular
   search zigzags and no chattering or getting stuck; then play as usual. Summarize the
   recording with `tools/playtest_flight_summary.py`.
3. **Acceptance** is the user's decision.

## 11. Local checks and the human playtest

**Local Windows checks** (2026-10-22, the LF worktree of the session branch at `6fab5bb`):
protected files 20 of 20 byte-exact; `verify_results.py`: 36 prediction records, source hashes
match, 2 exact held-out replays, frozen weights; **491 tests OK** on Windows;
`tools/approach_sanity.py` reproduces all 6,911 paddle ticks of the M1.7.1 acceptance recording
with identical old and new statistics.

**Playtest** (`20261022T010423.651486Z-bbe82503`, seed 255, `config_version` 26, 8 Numba
threads; private and git-ignored; the dirty flag again comes from `requirements-lock.txt` and
`results/verification.json`, which the game does not read), summarized read-only with
`tools/playtest_flight_summary.py`:

| Measure | B3a playtest (2026-10-21) | Completion playtest |
| --- | --- | --- |
| Recorded / alive / airborne time | 219.1 / 213.8 / 180.2 s | 191.8 / 183.3 / 151.6 s |
| Lifecycle: airborne / perched / landing approach | 78.5 / 15.7 / 5.8 % | 80.1 / 17.3 / 2.6 % |
| Airborne ecology share: EXPLORE / TRANSIT / ODOR_TRACK / ODOR_SEARCH | 36.1 / 17.9 / 15.3 / 10.0 % | 42.2 / 21.1 / 12.7 / 14.5 % |
| Mean bout, s: EXPLORE / TRANSIT / ODOR_TRACK / ODOR_SEARCH | 2.33 / 3.23 / 2.29 / 3.01 | 3.05 / 2.29 / 2.41 / 5.50 |
| TRANSIT speed after 1 s in the bout, mean (p90) | 9.6 (12.2) BL/s | 10.0 (11.9) BL/s |
| Policy alert onsets / ecology ALERT entries / entries without an executed alert response | 226 / 32 / 0 | 158 / 13 / 0 |
| Escape onsets: paddle approaching / during a strike / size-dominated / fly-driven self-approach | 19 / 2 / 8 / 0 | 7 / 4 / 1 / 0 |
| Near passes within 310 units without a strike (fly-driven) | 15 (5) | 3 (0) |

The B3a property holds, no escape is a fly-driven self-approach, TRANSIT speed is unchanged and
no state chatters or locks. One three-minute session is evidence against gross defects only,
not a behavioural dataset. The user accepted the stages after it.
