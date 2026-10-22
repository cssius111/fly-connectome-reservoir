# M2.4-B: closing the blind human test at 13 of 30 sessions (amendment 4)

Status: **recorded on 2026-10-22, after session 13 and before session 14.** The participant
decided on 2026-10-22 to stop the blind test again. The tool's status read:

```text
Completed and rated: 13 / 30 sessions. Incomplete attempts: 0. Next: Session 14 / 30. Ratings locked: no.
```

Nothing has been unblinded. The assistant has not opened any file under `artifacts/m2_4_b/`.
Its only knowledge of the data is this status line, which the participant ran and pasted.

## 1. What happened

- Amendment 3 ([M2_4_B_REOPENING.md](M2_4_B_REOPENING.md)) reopened the test on 2026-10-22 to
  complete sessions 13-30 under the unchanged protocol.
- Session 13 was then played and rated.
- The participant judged that further sessions would add little and stopped. Session 13 is the
  first session of block 7, so blocks 1-6 are complete and block 7 holds one session of its
  pair.
- Amendment 3 had already recorded that the blind test runs the preregistered runtime (the
  accepted N4B1C runtime on the `363a1a9` base). It does not test the later M1.8-B runtime.

## 2. Decision

- **M2.4-B ends at 13 of 30 sessions.** It will not be revealed or analysed, and it gives no
  conclusion about A (N4B1C) against B (the frozen M2.4-A candidate). The early-stop deviation of
  amendment 2 stands, now at 13 sessions.
- The ratings are not locked, and the session identities stay sealed. The tools still refuse
  `reveal` and `analyze` on a partial set, and they are not changed.
- The learning line stays closed, as in amendment 2: no training, no runtime integration.

## 3. Data and records

- The private session files, ratings, recordings and key stay under `artifacts/m2_4_b/` in the
  M2 worktree. They are git-ignored and local only.
- They are not opened, and they are not used for any other analysis. That includes the swatter
  stop-rotation audit, which read no M2.4-B recording.
- Any future use of these data needs a new amendment recorded before unblinding. The amendment
  would define the analysis as exploratory, and the tools would need a change to accept a
  partial set. Reopening the test would follow the routes named in amendment 2.
- `feature/m2-0-learning-infra` is unchanged at `96fb8af`. Amendments 3 and 4 are on `main`.
  Amendment 3 planned to be copied into the M2 branch after the last session; with this closure,
  both notes stay on `main` unless a copy is requested.
