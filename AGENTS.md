# Repository instructions

All new or edited project content must be in clear technical English: documentation, comments, docstrings, config comments, UI labels, logs, diagnostics, test descriptions and commit/PR text.

Do not translate or modify frozen original experiment artifacts. Preserve all paths and hashes in `artifacts/m1-2/protected-before.json`; scientific reproducibility overrides language cleanup. Historical game result records also remain immutable unless an explicitly authorized recalibration updates the active record.

Keep mouse/swatter world data outside neural policy observations. Preserve the Retina bottleneck, restricted MotionState, frozen connectome and fixed baseline policy. Do not implement learning without explicit authorization.

M1.7.1 is human-accepted and frozen: preserve the physical approach controller, strike phases, swept collision, partial-offscreen geometry, recorder/replay interface and WORLD-versus-policy separation unless future recorded evidence demonstrates a real defect. Do not retune these systems merely to change difficulty.

M1.8-A is human-accepted and frozen: preserve the landing pipeline, touchdown/contact mechanics, perched physical state, feeding presentation overlay, voluntary takeoff path, neural escape takeoff path, lifecycle recorder schema and lifecycle/policy data isolation unless future recorded evidence demonstrates a real defect. Do not retune these to change difficulty. Escape takeoff must stay downstream of Retina, LC4/LPLC2, MaleCNS and the descending-neuron readout; no click or proximity shortcut.

M1.8-B1 through M1.8-B2b-iii are accepted and frozen (B2b-iii accepted 2026-10-21): preserve the kinematic resolver/profile/executor interface, the three separated speed caps at their accepted values, `room_kinematic_scale` = 1.0, and the episode-scoped EXPLORE and ODOR_TRACK speed sampling with their dedicated random streams, unless future recorded evidence demonstrates a real defect. Do not retune these to change difficulty. Every further M1.8-B stage, and any change to how the ecology consumes the policy's ALERT state (see `game/M1_8_ALERT_INTERRUPTION.md`), requires a subsequent explicit user request.
