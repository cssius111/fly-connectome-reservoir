# M2.4-A: post-freeze execution amendment to the M2-EVAL-v3 runner

This record documents a post-freeze implementation amendment to the M2-EVAL-v3 execution runner (and to the M2.4-A
TRAIN-CONFIRM stage). It does not rewrite the M2-EVAL-v3 freeze: commit `660911a` and its seed manifest are
unchanged and no seed was regenerated.

## 1. Timeline and an ordering deviation (stated plainly)

| Time (2026-09-27, -04:00) | Event |
|---|---|
| 21:21 (09-26) | `660911a`: M2-EVAL-v3 seed manifest frozen (runner generation code sha256 `3fa6565c...`) |
| 05:09 | M2.4-A TRAIN-VAL screen completed (26 / 30 eligible). The first `confirm` run then failed at pool start-up (section 2) |
| 05:11 | `bfd5c42`: minimal fix + two unit tests, pushed |
| 05:11-06:03 | TRAIN-CONFIRM stage rerun cleanly from the beginning |
| 06:04 | `497a990`: candidate frozen and pushed |
| 06:04-06:39 | **One-shot M2-EVAL-v3 executed** with the amended runner (records `artifacts/m2_eval_v3/records.json`, sha256 `23e0c4bb...`) |
| 06:45 | `8a5eb2b`: M2.4-A report (GO) |
| later | This amendment and the full semantic-equivalence proof (sections 4-5) |

The request to write this amendment, and to prove full semantic equivalence, arrived after M2-EVAL-v3 had already run.
So the requested order was not followed: the amendment and full proof were to be committed before any EVAL-v3
episode.

Before the EVAL, only the following existed:
- the `bfd5c42` commit message, which described the defect, the scope and "software only";
- two tests, which passed:
  - (a) OLD vs NEW records identical for N4B1C and no_escape on 2 TRAIN threat trials;
  - (b) the NEW worker runs through a real Windows spawn pool.

The full proof below was produced after the EVAL. EVAL-v3 was not rerun, retried or partially re-executed, and
nothing in it was changed. This record exists so the evaluation can be judged with the ordering visible.

## 2. The defect

`confirm` (M2.4-A stage 2) and `m2_eval_v3.run_once` passed `m2_2_train._baseline_worker_init` as the initializer
of a `multiprocessing` spawn pool. `tools/m2_2_train.py` is a script loaded through `importlib` under a local module
object, so the function is not importable by name in a spawned worker. Pickling fails with:

```
_pickle.PicklingError: Can't pickle <function _baseline_worker_init ...>: it's not the same object as
m2_2_train._baseline_worker_init
```

The failure happened while the pool started, before any episode ran. No confirmation record was written: the
directory held only `screen.json`. In `run_once` the same failure would have occurred after the candidate / BC / M2.3
EVAL rollouts and before any record was written.

Classification: **multiprocessing / module identity / pickle only**. The scientific computation is unchanged
(sections 3-5).

## 3. The fix and its exact scope (`bfd5c42`)

- `game/learning/baseline_eval.py` (new, sha256 `83751654...`) holds a verbatim copy of `_baseline_worker_init` and
  `baseline_task` from `tools/m2_2_train.py` (file sha256 `f69270ca...`; function source sha256 `b8debc65...` /
  `ebbc60a3...`).
  - After normalising only the import path (`from game.learning import runner` -> `from . import runner`) and the
    initializer name, the function sources are identical (new source sha256 `26fdbbcc...` / `f474ed4a...`).
  - The module imports the same `runmode`, `trials` and `training` modules.
- `tools/m2_eval_v3.py`: 3 changed lines in `run_once`. The baseline pool initializer and task now reference
  `baseline_eval`, and the now-unused `m22 = _load('m2_2_train')` is removed. Seed generation (`seed_manifest`,
  `groups`, `specs`), `definition`, `check`, the one-shot guard and the candidate / MLP rollout path
  (`training.eval_task`) are unchanged.
- `tools/m2_4_a_strike_ppo.py::confirm`: the same substitution for the baseline pool.
- `test_m2_4_a.py`: two tests (`BaselineEvalCopy`).

Not changed: seed generation, scenario assignment, attacker parameters, brain-noise seeding, policy observations,
policy actions, reward, constraints, trial timing, metrics, benchmark definitions and checkpoint-selection rules.
The TRAIN-VAL screen used `training.eval_task` and never touched the faulty worker, so the screen results stand.

## 4. Hash provenance

| | Item | Value |
|---|---|---|
| A | frozen seed-manifest hash (`seed_manifest_sha256` in the manifest) | `c6d7d8d1c6a88638ad9fd27f72aab314646bd3c6d2bbb31c5cd65b63ce32dcd4` |
| A' | manifest file `game/learning/m2_eval_v3.json` (unchanged since `660911a`) | `a1e0fb418e1b27103ee184d2a2f3ab0577df71bedd90eefc337269904a2d4cce` |
| B | frozen benchmark-definition hash | `127de7988a17c1dc04c60feef39f80c1edd706cd4c3b0c1511e4906fce999dd0` |
| B' | frozen trials code hash (checked by `check()`) | `f24d74815e01d2317648153014fe5050e47d29769df8cda240d75648a7319767` |
| C | original generation-code hash (`tools/m2_eval_v3.py` at `660911a`, recorded as `generation_code_sha256`) | `3fa6565c1b444296d031af889f6b50e587fbb83be447e5cdc1abad4414914df5` |
| D | amended execution runner `tools/m2_eval_v3.py` (`bfd5c42`; identical at `497a990`, from which the EVAL ran) | `95e92353bbb140a3e10fe19e19c4ce42f6867ec1eb1e79cf288f5f36b5564d6c` |
| D' | new baseline worker `game/learning/baseline_eval.py` | `83751654b09aadf433b2363947239f6425e7b01aef3f6bc63c56e1998f2b4cab` |
| D'' | old baseline worker file `tools/m2_2_train.py` (unchanged since `fea943a`) | `f69270ca4f87eae207ab6a992297b5aef48bce5a41946c4fa868eef638e0576f` |
| E | semantic-equivalence report `game/learning/m2_4_a/baseline_worker_equivalence.json` | `a3b6bc5db9e022cf77133c97ed4821c307bbd9d0c091837d630985d0ed335beb` |
| E' | equivalence tool `tools/m2_4_a_baseline_worker_equivalence.py` | `c9cbdb609c7cbaabd8493ba44ef0fa01cc6082143b2e74e4c2358cf108ffead7` |

`check()` validates A, B, B', reward and constraints; it does not validate C. Because hash C therefore no longer
describes the file that executed the EVAL, it is recorded here explicitly alongside D.

## 5. Semantic-equivalence evidence (TRAIN seeds only)

`tools/m2_4_a_baseline_worker_equivalence.py` checks the three baselines the runner evaluates (`baseline_n4b1c`,
`no_escape`, `fixed_maneuver`).

**Part A: in-process OLD vs NEW, instrumented.**
- Fixed TRAIN set: `default_rng(4343)` over [20M, 25M), excluding development and TRAIN-VAL seeds. All 12 threat
  groups x 2 seeds + 1 episode per background family = 28 episodes. The seeds are listed in the report.
- Per episode, the full returned benchmark record is compared: seed, hit / miss, engage / click / resolution and
  first-escape times, exposure fields, escape counts, lifecycle and movement metrics, and trajectory hash.
- Instrumentation adds:
  - the neural reset seed passed to `FlyLoop.reset` (always seed + 977);
  - a scenario / attacker set-up hash;
  - a hash of every brain-loop input (Retina + MotionState), over about 19-20 k steps per policy;
  - a hash of every Action.
- **Result: 0 differences.**

**Part B: NEW through a real Windows spawn pool** (7 workers, start method `spawn`) on the same set. **0
differences** from Part A.

**Part C: historical cross-check.** The NEW worker ran through a spawn pool on the M2.2 TRAIN-VAL set (96 threat +
24 background episodes per policy). Its records were compared with the records the OLD worker produced in the M2.2
pipeline (`artifacts/m2_2/val/baselines.json`, 2026-09-26). The trials / training / runner / policies code has been
unchanged since `63dbeb6`, and game runtime files since `363a1a9`. **0 differences over 360 episode records.**

Conclusion: the amended runner computes exactly what the frozen runner would have computed wherever deterministic
replay applies. The observed defect was a pickle-only defect.

## 6. Confirmation stage and selection

- The failed `confirm` run wrote nothing. The rerun started from an empty confirmation state, used the preregistered
  TRAIN-CONFIRM seeds (hash `5307cc5f...` in the frozen protocol) and completed.
- Stage 2 followed the frozen protocol (`62795c25...`, `SELECTION.stage2_confirm`): **the 6 best screen-eligible
  checkpoints** of the 26 screen-eligible ones, plus the references, not all 26.
  - This follows the preregistered rule; the rule was not modified.
  - Re-confirming all 26 would be a different, un-preregistered procedure.
- The mechanical rule selected seed_2/ckpt_it060 (state_dict `a8f78d39...`). It was frozen and pushed (`497a990`)
  before any EVAL-v3 episode.

## 7. Status of the one-shot EVAL

M2-EVAL-v3 was executed exactly once, from `497a990`, with runner D. No EVAL-v3 episode was executed before the
candidate freeze was pushed, and none after the run completed. The result is in
`game/learning/m2_4_a/eval_v3_report.json` and `game/M2_4_A_STRIKE_CENTRIC_PPO.md`.

Whether the ordering deviation in section 1 affects acceptance of the M2.4-A GO is left to the human reviewer. The
equivalence evidence shows it did not change any computed value.
