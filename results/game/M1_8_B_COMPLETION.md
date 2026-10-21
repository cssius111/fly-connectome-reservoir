# M1.8-B completion: validation of stages B2c to B5

Status: **in progress.** Design and acceptance checks were preregistered in
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
