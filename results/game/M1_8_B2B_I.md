# M1.8-B2b-i validation: cap separation, behaviorally no-op

Status: **accepted and committed.** B2b-i is frozen as the separated-cap baseline for M1.8-B2b-ii.

Baseline: `bea44d0`. Scope is B2b-i only. No speed is sampled, `room_kinematic_scale`
stays exactly 1.0, `fly.max_speed` stays 1000.0, `escape_impulse` stays 880.0, the legacy
escape clamp is **not** removed, M1.8-A is not reopened, and no RL exists.

**Headline result: bit-identical.** 7 deterministic scenarios and 4060 ticks reproduce
exactly, all pre-existing random streams end in identical states, the kinematics sampler
is still untouched, and the escape study reproduces its 54 cases and all bouts with
identical values. No tolerance was introduced anywhere.

## 1. Old overloaded cap semantics

A single configuration value, `fly.max_speed = 1000.0` units/s (41.667 BL/s), served
**five** unrelated purposes at once:

1. truncated the ecological locomotion target,
2. clamped baseline and threat-priority cruise,
3. clamped the neural escape impulse,
4. bounded the frozen M1.8-A lifecycle takeoff and landing targets,
5. defined the recorder's `speed_cap_exceeded` diagnostic and the `room_sanity`
   displacement assertion.

The M1.8-B2b-R0 study showed the cost of that overloading: because (1) and (3) share a
number, raising the ecological ceiling would silently widen the accepted neural escape
envelope, and because (3) binds at all, the ceiling erases the graded DNp01 escape
strength above roughly 30-40 BL/s of cruise.

## 2. New separated cap semantics

`KinematicCaps` holds three named ceilings. **All three are Class C** — numerical
stability and simulator protection. None is a species flight maximum and none is a
biological escape-speed constant.

| Cap | Meaning | B2b-i value |
| --- | --- | --- |
| `ecological` | truncates commanded, later sampled, ecological locomotion | 1000.0 |
| `legacy_accepted` | the accepted constraint on threat-priority cruise, the neural escape impulse and the frozen M1.8-A lifecycle bounds | 1000.0 |
| `safety_ceiling` | a global numerical guard applied last on every path; should never bind in normal play | 1000.0 |

The executor still performs exactly **one** clamp, against
`effective_cap = min(profile_cap, safety_ceiling)`. `KinematicProfile` now records
`profile_cap` and `safety_ceiling` alongside it, so the effective number is always
traceable to the ceiling that produced it. The overloaded field name `max_speed` is gone
from the profile; `World.max_speed` is retained as the legacy alias for callers outside
the kinematics layer.

A profile whose `effective_cap` exceeds `min(profile_cap, safety_ceiling)` is rejected at
construction, so the invariant cannot be violated silently.

## 3. Exact mapping of every old `max_speed` consumer

| Old consumer | New cap | Notes |
| --- | --- | --- |
| Ecological target truncation in `KinematicResolver.airborne` | `ecological` | the only cap B2b-ii will eventually change |
| Ecological executor clamp | `effective(ecological)` | |
| Baseline cruise profile | `legacy_accepted` | |
| Threat-priority profile (neural escape ticks) | `legacy_accepted` | reached whenever `Action.escape` is set |
| `KinematicResolver.landing_approach` target | `legacy_accepted` | frozen M1.8-A; `clamp_speed` still off |
| `KinematicResolver.lifecycle_direct` (stationary, launches) | `legacy_accepted` | frozen M1.8-A |
| `World._move_lifecycle` voluntary launch `min(self.max_speed, ...)` | unchanged legacy alias | left as-is; changing it would touch frozen M1.8-A code for no benefit |
| `game/recording.py` `speed_cap_exceeded` diagnostic | unchanged legacy alias | conceptually the safety ceiling; keeps the `+1e-6` tolerance for sideslip |
| `tools/room_sanity.py` displacement assertion | unchanged legacy alias | conceptually the safety ceiling |

The last three deliberately still read `World.max_speed`. Rewiring them would change
frozen M1.8-A code and the recorder for no behavioral benefit in a no-op stage; the report
records the intended mapping so B2b-ii can complete it if a value actually diverges.

## 4. Effective legacy-equivalent values

All three caps are configured at 1000.0 units/s, so every clamp reduces to the accepted
arithmetic:

- `min(1000.0, x)` is unchanged wherever the legacy ceiling appeared.
- `effective = min(1000.0, 1000.0) = 1000.0` exactly.
- No new multiply was introduced on the active path, so no new rounding is possible.

Presets without a `kinematics` block fall back to their own `fly.max_speed`, so LAB and
GAME are structurally identical and behaviorally unchanged.

## 5. Exact trace result

| Scenario | Ticks | Trace SHA256 (16) | Identical |
| --- | --- | --- | --- |
| `room_quiet` | 1200 | `0ce2de632d39a22b` | yes |
| `room_perched_threat` | 340 | `0e585ca27f52a4c6` | yes |
| `room_approach_threat` | 120 | `4a7520da22e19579` | yes |
| `room_airborne_seed101` | 900 | `db96124ef298a332` | yes |
| `room_no_ecology` | 600 | `ed4370a5755cfb59` | yes |
| `game_preset` | 500 | `9f93e048645ae73a` | yes |
| `lab_preset` | 400 | `acc4ca9a88daa0f2` | yes |

Combined SHA256 before and after:
**`aee61cff38dc12f16d2277ed987bbb07f98091ea9ac3ca7808210a5a958eaf34`** — unchanged since
the pre-B1 baseline, so B1, B2a and B2b-i together remain a single no-op.

```json
{"scenarios": 7, "total_ticks": 4060, "bit_identical": true,
 "existing_rng_streams_unchanged": true, "new_rng_streams": [],
 "kinematics_sampler_untouched": true, "findings": []}
```

**First divergence: none.** No tolerance was proposed or accepted.

## 6. RNG result and sampler status

`existing_rng_streams_unchanged: true` for `world`, `spawn`, `flight`, `ecology` and
`lifecycle`. `new_rng_streams: []` — B2b-i adds no stream. The `KinematicCaps` type is an
immutable value object with no randomness, and `KinematicResolver` remains pure and
RNG-free.

`kinematics_sampler_untouched: true` in all 7 scenarios: zero draws, and the
bit-generator state still equals its seed-time value. `KinematicSampler.target_speed_bl_s`
still returns `None` unconditionally.

## 7. Unchanged effective escape behavior

Re-running `tools/escape_cruise_study.py` after the separation reproduces the pre-change
results exactly:

```text
escape rows identical:   True    (54 cases)
escape bouts identical:  True    (18 bouts)
constants identical:     True
analytic model mismatches: 0
```

So the accepted escape behavior — including the currently-truncated full-strength case
near 10 BL/s cruise, which decision 3 classes as an artifact to be fixed *later* — is
preserved exactly. The artifact was **not** corrected in this stage, as instructed.

## 8. Full regression

| Check | Result |
| --- | --- |
| Full unit suite | **319 tests, OK** (311 after B2a, +8) |
| `git diff --check` | clean |
| 20 protected original files | SHA256 unchanged |
| 58-file frozen baseline | SHA256 unchanged |
| `verify_results.py` | 36 predictions, hashes match, 2/2 exact neuronal replays, frozen weights |
| M1.7.1 swatter fixtures | byte-identical to `approach_m1_7_1.json` |
| M1.8-A lifecycle scenarios | identical event counts; exact replay 1200 / 340 / 120 |
| Recorder exact replay | `exact: true`, 1200 ticks, schema 4 |
| Policy-observation isolation | `{neural, motion, behavior_state, history}` only, no leaks |
| Calibration provenance | LAB 1.45, GAME 1.35, ROOM 1.45 via the new B2b-i record |
| B2a vs B2b-i trace | bit-identical, 4060 ticks, no tolerance |

New tests (8) pin the separation: the three config caps sit at the legacy value; absent
keys fall back to `fly.max_speed`; invalid caps are rejected; `effective` is the tighter of
profile and ceiling and an inconsistent profile raises; each context draws its own
ceiling; **the ecological cap cannot reach the neural escape path** (asserting that
`_neural_active` is true for any escape action, which pins the B2b-R0 finding); lifecycle
targets use the legacy cap even when the ecological cap is deliberately tiny; and `World`
exposes legacy-equivalent caps.

## 9. Calibration

Adding config keys changed the canonical hash, so provenance correctly failed closed.
`results/game/calibration_room_m1_8_b2b_i.json` resolves to **1.45** and extends the
chain to three transfers: source `calibration_room_m1_8_b2a.json` with its SHA256, and
`original_measurement` still naming `calibration_room_m1_7_1.json` with its SHA256, so the
single underlying fixed-fly-v2 measurement remains traceable. No recalibration was
performed or justified: fixed-fly-v2 disables ecology, lifecycle, fly motion and
collisions, and all three caps are legacy-equivalent.

`config_version` 11 -> 12.

## 10. Changed files

| File | Change |
| --- | --- |
| `game/kinematics.py` | +92/−13. `KinematicCaps`; profile `effective_cap`/`profile_cap`/`safety_ceiling` replacing `max_speed`; per-context cap routing. |
| `test_game_kinematics.py` | +72/−4. 8 new tests (36 total in the module). |
| `game_room_config.json` | +13/−5. Three cap keys at legacy values, `config_version` 12, calibration paths. |
| `test_game_lifecycle.py` | +16/−8. Calibration chain extended to the third transfer. |
| `game/world.py` | +9/−3. `KinematicCaps.from_config` wiring. |
| `results/game/calibration_room_m1_8_b2b_i.json` | **New.** Transfer record. |

## 11. Where escape behavior would intentionally diverge

Not in this stage, and not in B2b-ii either. The ordered points of intentional divergence
are:

1. **B2b-ii** — the first airborne EXPLORE tick where `KinematicSampler.target_speed_bl_s`
   returns a float instead of `None`. This diverges the *ecological* path only. The
   `perched_threat` lifecycle trace and the escape study must both still be identical,
   because neither reads the ecological cap.
2. **Later, TRANSIT/ODOR distributions and `room_kinematic_scale` > 1** — still ecological
   only, but the point at which `ecological_cap_units_s` must actually rise above
   `legacy_accepted_cap_units_s`. The moment it does, the M1.8-B2b-R0 conflict becomes
   live: a fly cruising above 41.667 BL/s would be clamped downward on entering ESCAPE.
3. **The escape clamp change itself** — removing or relaxing the legacy escape clamp so
   that invariants A and B hold. This is the first divergence in the **neural** path. Per
   the accepted decision it requires full automated regression, neural-path verification,
   exact documentation of the first intentional divergence, and a narrow human
   re-acceptance of threat-triggered takeoff feel. It does **not** require reopening the
   M1.8-A lifecycle architecture.

Because step 2 makes the conflict live before step 3 fixes it, the two should be ordered
deliberately rather than by convenience: raising the ecological cap past the legacy
accepted cap without first resolving the escape clamp would reintroduce the exact defect
the R0 study documented.

## 12. Status

B2b-i is accepted, committed and frozen.

Not done, deliberately: B2b-ii is not implemented; EXPLORE is not sampled;
`room_kinematic_scale` is 1.0; `escape_impulse` is 880.0; `fly.max_speed` is 1000.0; the
legacy escape clamp is intact; the ~10 BL/s full-strength truncation is preserved exactly
as accepted behavior for now. No RL, reward function, personalized learning or adaptive
opponent policy exists anywhere in the codebase.
