# M2.4-B: reopening the blind human test (amendment 3)

Status: **recorded on 2026-10-22, before session 13 is played.** The participant decided on
2026-10-22 to reopen M2.4-B and complete sessions 13-30. No session file, rating, recording or
key under `artifacts/m2_4_b/` has been opened, and nothing has been unblinded.

This note lives on the runtime session branch (`claude/gracious-galileo-mxnbs9`) rather than on
`feature/m2-0-learning-infra`, so that the M2 worktree used for the sessions keeps its checkout.
It is to be copied unchanged into the M2 branch after the last session.

## 1. Route

`game/M2_4_B_EARLY_TERMINATION.md` (amendment 2, on the M2 branch) names two ways to reopen the
line. This is the first: **complete sessions 13-30 under the unchanged protocol**
(`game/M2_4_B_HUMAN_TEST_PROTOCOL.md`, `game/learning/m2_4_b/protocol.json` at `f048ba6`, the
blinding amendment 1 at `9201c24`). The closure of the M2 line in amendment 2 ("no further
sessions") is lifted for these sessions only; there is still no training and no runtime
integration.

## 2. Unchanged

- The randomisation manifest, the key, the seeds, the block order and both policies (A: N4B1C,
  B: the frozen M2.4-A candidate).
- The code that runs the sessions. Between `9201c24` (the code of sessions 1-12) and the M2 branch
  head `96fb8af` only documentation, `requirements-learning.txt` and tests changed; no file under
  `game/`, no tool and no configuration changed, so either checkout runs the same sessions.
- The procedure (`python tools/m2_4_b_blind_ab.py play` from `artifacts/worktrees/m2-learning`),
  the ratings, the objective metrics, the analysis plan and checks A-E. Identities stay sealed
  until all 30 ratings are locked; the tools still refuse `reveal` and `analyze` on a partial set.
- No tuning of either policy.

## 3. Deviations, recorded before resuming

1. **Pause.** Sessions 1-12 were played by 2026-10-08; sessions 13-30 follow after a pause of
   at least 14 days, after the early stop of amendment 2. The preregistered analysis is unchanged;
   the results report will additionally state the pause and give the block-level differences of
   blocks 1-6 and blocks 7-15 descriptively, without a test.
2. **Practice in between.** During the pause the participant played the later ROOM runtime
   (M1.8-B2b-iii to B4b). The blind test still runs the runtime it was preregistered on (accepted
   N4B1C runtime, `363a1a9` base), so its result concerns that runtime only and says nothing about
   the M1.8-B behaviour; familiarity with ROOM may have changed between the two halves.
3. **Early stop.** The deviation from "no early stopping" recorded in amendment 2 stands; the
   test is completed rather than analysed on a partial set.

## 4. Data handling

The private session files, ratings, recordings and key stay under `artifacts/m2_4_b/` in the M2
worktree, git-ignored and local. The assistant does not open them, and recordings from these
sessions are not used for any other analysis (for example the swatter stop-rotation study)
before the reveal.
