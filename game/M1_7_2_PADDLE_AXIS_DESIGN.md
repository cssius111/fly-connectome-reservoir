# M1.7.2: a line-symmetric paddle axis (preregistration)

Status: **preregistered on 2026-10-22, before any implementation or measurement.** It changes
one input of the paddle's visual geometry in ROOM. The checks and pass criteria below are fixed
before any code is written.

**Accepted on 2026-10-22** after the checks and one human playtest; see
`results/game/M1_7_2_PADDLE_AXIS.md`.

## 1. Authorization and evidence

- The user requested this fix on 2026-10-22, after the stop-rotation audit.
- `AGENTS.md` keeps the M1.7.1 swatter frozen unless recorded evidence demonstrates a real
  defect. `results/game/M1_8_STOP_ROTATION_AUDIT.md` (with its erratum) is that evidence:
  - On the accepted runtime, reversal spins occur 2.23 times per hover minute.
  - They add about 0.35 escapes per hover minute over distance-matched hover (P = 0.009).
  - The earlier runtimes give 0.39 per hover minute (P = 0.0004).
- The N4B6 stop transient (`game/M1_8_N4B6_CONTROLLED_SLOW_APPROACH.md`, section 4) has the
  same cause. The overshoot correction after a stop reverses the paddle velocity, and the
  paddle is left about 90 degrees into a spin when its speed falls below 20 units/s.

## 2. The defect

In the approach phase, `game/physical_swatter.py` steers `swatter.orientation` towards the
360-degree heading of the paddle velocity whenever the paddle moves faster than 20 units/s.
The steering uses a gain of 8 /s and limits of 6 rad/s and 24 rad/s².

The tilt term in `game/world.py` uses `abs(sin(bearing - orientation))`, which is unchanged by
a turn of 180 degrees. A reversal of the motion therefore makes the paddle spin by up to 180
degrees, although the line it presents ends where it started. During the spin the fly sees the
projected paddle change size at constant range. The rendered sprite spins the same way.

`swatter.orientation` also has a second role, which must not change. It is the strike
direction of a slow commit (`attack_orientation = orientation` when the pointer moves slower
than 20 units/s), so it sets the sweep of slow strikes.

## 3. The change

A new world-only state, the **paddle line axis**, is kept by `PhysicalSwatter` next to the
unchanged heading tracker `swatter.orientation`.

- **Initial state.** The line axis and its angular velocity start from the tracker's
  values at the first sub-step after a reset.
- **Target.** Each sub-step, after the unchanged tracker update, the line axis takes the
  tracker's target with one exception:
  - in the approach phase above 20 units/s: the velocity heading, as for the tracker;
  - in the approach phase at or below 20 units/s: its own current value (hold), as the
    tracker holds its own value;
  - in strike phases: the tracker's `attack_orientation` after a fast commit. After a slow
    commit it takes the value the line axis had at the commit, which is what the tracker does
    with its own value.
- **Error, folded.** The error is computed with the tracker's formula,
  `e = (target - axis + pi) mod 2 pi - pi`. If `abs(e) > pi/2`, it is folded:
  `e -= copysign(pi, e)`. The axis then turns to the nearer of the target and its opposite.
- **Dynamics.** The same gain and limits as the tracker:
  - `omega_wanted = clip(8 e, +-angular_speed_limit)`;
  - `omega += clip(omega_wanted - omega, +-angular_acceleration_limit h)`;
  - `axis += omega h`.

  The change adds no parameter.

The line axis replaces `swatter.orientation` in exactly two places:
- the tilt term of `World.visual_half_size`, under both tilt geometries;
- the rendered paddle sprite, whose handle stays on the same side through a reversal.

Everything else is unchanged:
- the heading tracker, `attack_orientation`, swing speed, sweep and strike phases;
- the approach controller's translational dynamics, swept collision and partial-offscreen
  geometry;
- the recorded `swatter` fields, the policy observation and the WORLD-versus-policy
  separation;
- the N4B5R tilt formula, which keeps its form and only takes the new axis as input;
- the N4B1C decoder, the M1.8-A lifecycle and every M1.8-B mechanism.

**Gate.** The change is controlled by `swatter.directional.paddle_axis`:
- `heading_v0`, the default when the key is absent, is the accepted M1.7.1 behaviour;
- `line_symmetric_v1` requires `swatter.physical.enabled`, and any other value is an error.

**Scope.** Only the ROOM configuration changes, from `config_version` 26 to 27. GAME has no
physical or directional swatter, and LAB is unchanged.

**Recording.** The tick's `swatter_control` block gains `paddle_line_axis`,
`paddle_line_axis_velocity` and `paddle_line_axis_folded` (whether a sub-step of this tick
used the folded error). It gains them only when the gate is set, so configurations without it
record exactly as before. `tools/stop_rotation_audit.py` reads the line axis when it is
recorded.

**Record.** `tools/m1_7_2_axis_record.py` writes `results/game/calibration_room_m1_7_2.json`.
- It is a transfer record: the N4B1C decoder and threshold are carried over byte-for-byte from
  `results/game/calibration_room_m1_8_b4b.json`, as N4B5R carried them over for its geometry
  change.
- It marks the geometry as changed and cites check C2 for the calibration trials.
- The writer refuses any configuration that differs from v1.0 (`5722166`) outside
  `config_version`, `policy._comment`, `policy.calibration_paths` and the two new
  `swatter.directional` keys (`paddle_axis` and its comment).

## 4. The invariant

Take the same seed and inputs. While the line axis equals the tracker, the line update uses
exactly the tracker's arithmetic unless the folded branch is taken. A run under v27 is
therefore **bit-identical to v26 up to the first sub-step in which the line axis takes the
folded branch**. A run without such a sub-step is bit-identical throughout. Checks C2 to C5
rely on this property and test it.

## 5. Preregistered checks

Configurations:
- **v26** is `game_room_config.json` at `5722166` (tag `v1.0`).
- **v27** is the working file.

The brain-noise seeds are the 48 seeds of `tools/n4b6_protocol.py`. Controls run under
fixed-fly-v2 with ecology off, as in N4B6. The pass criteria are fixed here.

- **C1. Code-only identity.** With v26, the changed code must reproduce:
  - the seven `tools/kinematics_trace.py` scenarios bit-for-bit, including the random
    streams;
  - the `tools/approach_sanity.py` controlled fixtures equal to
    `results/game/approach_m1_7_1.json`;
  - `tools/escape_cruise_study.py`, unchanged;
  - `tools/lifecycle_sanity.py`, which must pass;
  - an exact `tools/session_sanity.py` replay.

  The full test suite must also pass.
- **C2. Invariant.** Under v27, against v26:
  - The seven trace scenarios and the 56 trials of the calibration protocol
    (`tools/calibrate_escape.py`: settle plus trial, world only) are bit-identical up to their
    first folded sub-step, and throughout when there is none.
  - The number of folded sub-steps in the calibration trials is reported. If it is zero, the
    calibration measurement is reused exactly. Otherwise the record says that the reuse is not
    exact, as for N4B5R, and the threshold is not re-derived either way.
- **C3. Efficacy on scripted controls.**
  - **F3, orbit then hold.** The N4B6 F3 trajectory: a 2 s pre-hold, 7 s on the orbit at 300
    units and 130 units/s, then a 1.5 s post-hold.
    - v26 must show the transient: post-hold peak size-driven expansion of at least 0.2 rad/s.
    - v27 passes if:
      - the post-hold peak size-driven expansion is at most 0.1 rad/s;
      - the line axis turns by at most 10 degrees in the hold;
      - N4B1C responds in the post-hold in at most 2 of 48 seeds.
    - Responses during the orbit are reported for both configurations.
  - **R1, reversal on an arc.** The same arc at 300 units, at 300 units/s: a 2 s pre-hold,
    1.0 s one way, 1.0 s back on the same arc, then a 1.5 s hold.
    - v26 must spin: the tracker turns by at least 120 degrees after the reversal.
    - v27 passes if:
      - the line axis turns by at most 10 degrees from the reversal to the end;
      - the peak size-driven expansion after the reversal is at most 0.1 rad/s;
      - N4B1C responds after the reversal in at most 2 of 48 seeds.
  - **T1, turn** (world only). A straight run at 300 units/s that turns by 60 degrees must be
    bit-identical between v26 and v27, with no folded sub-step. Turns under 90 degrees keep
    the accepted behaviour.
- **C4. Strikes.**
  - The session_sanity scenario, which strikes at ticks 100 and 300, and the calibration loom
    trials follow C2.
  - The approach_sanity fixtures are identical under v27 too, because the line axis does not
    feed back into the paddle's motion.
- **C5. Free flight without a player.** Seeds 9201-9210, 180 s each, with the pointer parked
  far away as in `tools/b2b_iii_free_flight_check.py`,
  follow the invariant of section 4. The paddle travels once from its reset position to the
  parked pointer and then rests, so it can fold only during that travel. The folds are
  reported, and the escape onsets of both configurations are reported when a fold occurs.
- **C6. Frozen systems under v27.**
  - `tools/lifecycle_sanity.py` passes.
  - A `tools/session_sanity.py` recording under v27 replays exactly.
  - `tools/approach_sanity.py` and `tools/escape_cruise_study.py` are unchanged.
  - The full test suite passes.
- **C7. Human acceptance.** One ROOM playtest of at least 3 minutes under v27, recorded.
  - `tools/stop_rotation_audit.py` on that recording reports, descriptively, the transients
    per hover minute on the line axis and the escapes they add. Their earlier rate on the
    accepted runtime was 4.65 per hover minute.
  - The user judges the paddle's look and the fly's behaviour, and decides acceptance.

## 6. Stop rules

- A failure of C1, C2, C5 or C6 is an implementation defect. It is fixed and the check rerun;
  no criterion is changed.
- If v27 fails C3, the result is reported and the change is not proposed for acceptance. The
  rule has no free parameter to tune.
- If v26 fails its sanity condition in C3, the control does not reproduce the defect. That is
  reported before any v27 result is read.
- Nothing here retunes difficulty, the decoder, the Retina or the encoder.

## 7. Amendment 1 (2026-10-22, before any neural measurement)

A world-only geometry run of the scripted paths, made while the implementation was checked,
showed that one preregistered criterion was misspecified. No brain had been simulated for any
check.

- **R1 line-axis criterion, failed as written.** The criterion "the line axis turns by at most
  10 degrees from the reversal to the end" does not allow for the arc. On the return leg the
  motion line itself turns by about 57 degrees (300 units/s on a 300-unit arc for 1.0 s), and
  the line axis follows it. It turns by 75.2 degrees in total, against 197 degrees for the
  heading tracker. The criterion is reported as failed as written.
- **Replacement, descriptive only.** The deviation of the line axis from the motion line,
  modulo 180 degrees, is reported for both configurations. It gets no threshold, because the
  threshold would be set after seeing the rotation.
- **Unchanged.** R1's functional criteria stay as preregistered: the size-driven expansion
  after the reversal, and the N4B1C responses.
- **T1 needs no amendment.** In that run the first folded sub-step came at the stop after the
  turn, not at the turn. T1 as preregistered (a straight run that turns, with no stop) is
  compared up to the end of the run.
