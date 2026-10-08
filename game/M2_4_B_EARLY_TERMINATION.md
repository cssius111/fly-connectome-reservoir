# M2.4-B: early termination of the blind human test (amendment 2)

Status: **closed by the human participant's decision on 2026-10-08, after 12 of 30 preregistered
sessions. No result is drawn from it.** The learning line (M2) stops here: no further training,
no further sessions, no runtime integration.

## What was preregistered

- Protocol: `game/M2_4_B_HUMAN_TEST_PROTOCOL.md`, `game/learning/m2_4_b/protocol.json`
  (`f048ba6`), blinding amendment 1 (`9201c24`, before any session).
- 30 sessions in 15 blocks of 2 (one N4B1C session and one M2.4-A session per block, same world
  seed, order sealed by a secret key).
- No early stopping; the analysis tool refuses a partial set; identities stay sealed until all
  30 ratings are locked.

## What happened

- 12 sessions were completed and rated: sessions 01-12, which are blocks 1-6, each block
  complete. There were 0 incomplete attempts.
- The participant then decided to stop. This is a deviation from the preregistered "no early
  stopping" rule, recorded here rather than hidden.
- **The data were not unblinded and not analysed.** `reveal` was not run, the ratings are not
  locked, and the assignment of each session is still unknown to everyone.
- The private session files, ratings, recordings and the key remain in `artifacts/m2_4_b/`
  (git-ignored, local only). They are not committed.

## Consequences

- **No human-acceptance conclusion exists.** Checks A-E of the protocol were never evaluated.
  M2.4-B neither confirms nor contradicts the M2.4-A benchmark result.
- The M2.4-A conclusion is unchanged: GO for human testing with a documented procedural deviation
  (M2-EVAL-v3 hit rate 0.552 vs N4B1C 0.640, paired p = 0.00026; see
  `game/M2_4_A_STRIKE_CENTRIC_PPO.md` and `game/M2_4_A_EVAL_EXECUTION_AMENDMENT.md`). It was
  never followed by a completed human test.
- The accepted runtime (`363a1a9`, default policy N4B1C) is unchanged. The learned policy is not
  integrated, and nothing is merged.

## If the line is ever reopened

- Either complete sessions 13-30 under the unchanged protocol (the manifest and key are intact),
  or write a new amendment before unblinding that defines an exploratory analysis of the 6
  complete blocks. The tools refuse both `reveal` and `analyze` on a partial set, so the second
  route needs that amendment and a matching code change.
- Any 6-block result would be descriptive only (one player, 12 sessions, low power).
