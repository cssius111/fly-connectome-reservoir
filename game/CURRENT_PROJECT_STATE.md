# Current project state (operational handoff)

This file is an operational handoff for future sessions. It is not a scientific result or
a runtime artifact. Evidence lives in the milestone reports listed below. Update it at the
end of every substantial milestone.

Last updated: 2026-09-24, at the end of M1.8-N4B2 (research complete; decision pending).

## Start of a new session

1. Read this file.
2. Read the current milestone report (below).
3. Run `git status`, `git branch -vv` and `git log --oneline -10`.

Do not ask the user to reconstruct old context unless the repository conflicts with this
file.

## Accepted and frozen runtime

| Item | Value |
|---|---|
| Milestone | **M1.8-N4B1C**, human-accepted and frozen |
| Branch | `feature/m1-8-n4b1c-runtime` |
| Commit | `e3c55b36084cd1d05e5f38d0b178aed0b9a59ddf` |
| Decoder | `lateral_dual_path_v1` |
| Lateral path | two inferred spikes on the same DNp01 side within <= 60 ms (3 samples) |
| Summed path (from rejected N2b) | FAST: L+R >= 2.10, OR current L+R >= 1.45 with >= 3 of the last 5 samples >= 1.45 |
| Refractory | 0.4 s shared |
| Validation at acceptance | 414 tests pass; protected files unchanged; `verify_results.py` passes; recorder schema 4; ROOM config v16 |
| Accepted | direct-strike latency, hover/chase responsiveness, escape direction |

Earlier frozen milestones (see `AGENTS.md`): M1.7.1 swatter dynamics and M1.8-A lifecycle.

## Branches

| Branch | HEAD | Role |
|---|---|---|
| `wip/m1-4-enclosure` | the N4B2 research commit (see `git log -1`); based on `07f4670` | research branch; research-only commits |
| `feature/m1-8-n4b1c-runtime` | `e3c55b3` | accepted runtime; **do not modify** |
| `archive/m1-8-n2b-rejected` | `2c306174d7bdb4e74b6c5517519ae695bd90cf44` | rejected N2b runtime snapshot; **never merge** |
| `main` | `309abd9` | untouched |
| PR #1 (`wip/m1-4-enclosure` -> `main`) | open | **unmerged; do not merge without explicit approval** |

Research worktrees (git-ignored, under `artifacts/worktrees/`): `n2b-rejected` (detached at
the archive commit), `n4b1c-runtime` (the feature branch), and `n4b1c-runtime-detached`
(detached at `e3c55b3`; used read-only by N4B2 tools). Each has a `data` junction to
`data/`.

## Current research milestone

**M1.8-N4B2: alternative descending-neuron readout research** (research only): **complete.
A user decision is pending** (see "Next permitted actions").

- Report: `game/M1_8_N4B2_ALTERNATIVE_DN_READOUT.md` (read sections 8, 9, 10 and 12 first).
- Tools: `tools/n4b2_record.py`, `tools/n4b2_connectome.py`, `tools/n4b2_criteria.py`
  (frozen criteria), `tools/n4b2_analysis.py`.
- Artifacts: `artifacts/m1_8_n4b2/` (git-ignored). `frozen_criteria.json` has sha256
  `50720084...`. The new N0 holdout uses seeds 310000-340149, and the ROOM holdout uses
  seeds 7201-7212. **Both are now used and must not be reused to design new criteria.**

## Major conclusions so far

- N4A: threat is separable from N0 at the Retina and sensory-spike levels at onset. DNp01
  is a weak, slow readout (MaleCNS transfer, reset to zero, side splitting). Spontaneous
  DNp01 spikes are the cell's own noise kicks, and left and right are independent.
- N4B1 / N4B1C: reading DNp01 per side removes the summed-noise coincidence; A OR N2b
  restores direct-strike speed and hover sensitivity. Accepted as the runtime.
- Rejected: legacy single-sample 1.45 (N0 false triggers); strict N2 and N2b summed-only
  decoders (latency); pooled multi-DN readouts (N4A: held-out N0 events).
- N4B2: of 10 wiring-qualified DN types, **only DNp04** gives earlier slow-approach evidence.
  - Slow-close case: DNp04 pair <= 60 ms fires at tick 613, against 668 for N4B1C.
  - N1 weak approach: detected 60 / 60, against 33 / 60.
  - N0: 0 events in 910 min, including the new 280-min holdout.
  - **But DNp04 is non-selective.** Held-out no-player ROOM free flight gives 11 escapes in
    36 min (0.31/min, from the fly's own flight near the parked paddle), against 3 for
    N4B1C. That fails the < 0.1/min target there. It also adds about 30 firings in 3.7 min
    of human play.
  - The biology agrees: DNp04 is a location-blind loom-burst DN with a weak takeoff
    phenotype.
  - DNp02, DNg40, DNp11, DNp03, DNp05, DNpe056, DNp103 and DNpe025 do not help and are
    rejected. 500 ms integration windows fail on N0.

## Known unresolved limitation

Slow or gradual approach is still detected too late: the N4B1C decoder fires at tick 668 in
the episode-5 slow-close case (N2b session), 45 samples after the closest approach. N4B2
showed that a DNp04 readout fixes this only at a measured free-flight specificity cost. It is
unresolved until the user chooses option A, B or C below.

## Do not reopen

- N4B1C tuning: the same-side <= 60 ms rule, summed FAST 2.10, the summed 3-of-5 rule, the
  refractory and the motor semantics. Reopen only if a future milestone demonstrates a
  defect.
- M1.7.1 swatter dynamics and M1.8-A lifecycle (see `AGENTS.md`).
- Frozen experiment artifacts in `artifacts/m1-2/protected-before.json`.
- The N4B2 frozen criteria, and the design of new criteria on the used N4B2 holdouts.

## Next permitted actions (decision pending)

N4B2 recommends **A**, with **C** if slow-approach sensitivity remains a priority. The user
has not yet chosen.

- **A.** Keep N4B1C unchanged; no action needed.
- **B.** A runtime candidate "N4B1C OR DNp04 pair 60 ms". This **expands the policy
  whitelist** and must not start without explicit approval.
- **C.** Research-only N4B3: a more selective DNp04-based signal, for example with
  concurrent DNp01 evidence or a MotionState self-motion discount. Design it on development
  data only, and validate it on NEW N0 and ROOM seeds, not those used above.

## Permitted without asking

- Offline research tools, re-simulation, analysis and reports on `wip/m1-4-enclosure`.
- Research-only commits and pushes to `wip/m1-4-enclosure`.

## Requires explicit user approval

- Any runtime behaviour change (`game/action.py`, `game/session.py`, ROOM config,
  calibration records, recorder schema).
- **Expanding the policy observation whitelist** (for example adding DNp04).
- Changing biological model parameters, Retina or encoder equations, noise or physics.
- Merging branches or PRs, rewriting Git history, or modifying `feature/m1-8-n4b1c-runtime`.
- Choosing between materially different product or scientific directions.
