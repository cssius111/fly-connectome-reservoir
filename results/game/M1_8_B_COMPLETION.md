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
