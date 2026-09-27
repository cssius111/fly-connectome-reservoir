# M2.4-B: blind human gameplay acceptance: protocol

Status: **preregistered; infrastructure ready; no session played yet.** This is human validation only. Nothing is
trained, and neither policy is modified. The accepted runtime (`363a1a9`, default policy N4B1C) is not changed or
replaced, and nothing is merged. The results report will be `game/M2_4_B_HUMAN_GAMEPLAY_ACCEPTANCE.md`, written after
all sessions.

Background: M2.4-A was accepted as GO for human testing, with a documented procedural deviation. The candidate met
the preregistered EVAL-v3 success criterion (hit rate 0.552 vs N4B1C 0.640, -0.088, paired p = 0.00026). A post-freeze
multiprocessing / pickling repair was applied before EVAL. The complete formal amendment and semantic-equivalence
audit were completed after EVAL. Subsequent TRAIN-only audits demonstrated exact scientific-output equivalence between
the old and repaired worker implementations.

The question for M2.4-B: does the learned fly feel behaviourally credible and meaningfully harder to hit in real human
play?

## 1. Policies

| Code | Policy | How it is built |
|---|---|---|
| A | accepted N4B1C (`FixedEscapePolicy`, `lateral_dual_path_v1`) | the unchanged `Session(config)` default |
| B | frozen M2.4-A candidate seed_2/ckpt_it060 | `game/learning/checkpoints/m2_4_a_candidate.npz`, parameter sha256 `0692117a...` verified at load, in the unchanged `ManeuverPolicy` adapter; stochastic sampling seeded with world_seed + 104,729 |

The world, physics, lifecycle, MaleCNS, Retina / encoder and recorder are unchanged. The launcher only chooses the
policy object passed to `Session`.

## 2. Blinded randomisation (`game/learning/m2_4_b/randomization_manifest.json`)

- **Sessions:** 30 sessions in 15 blocks of 2. Each block has one A and one B session with the same world seed
  (41,000,000 + 1000 x block, disjoint from every M2 seed range).
- **Order:** within each block, the order is `AB` or `BA` from the parity of HMAC-SHA256(secret key, "block:b"). At
  most 2 consecutive sessions use the same policy.
- **Public manifest** (committed before any session): seeds, sha256(key) and one sha256(key | session | policy)
  commitment per session. It does not show assignments.
- **The key** lives in `artifacts/m2_4_b/blind_key.json` (git-ignored). **Do not open it or `artifacts/m2_4_b/`
  before the end.** It is published after all sessions, so every assignment can be regenerated and verified.
- **During play:**
  - no policy name is shown;
  - the neural HUD (H key) is disabled, because its diagnostics differ by policy class;
  - the gameplay HUD (time, strikes, hits, escapes) is the normal game HUD.
- **Reveal:** identity is shown only after that session's ratings are saved.
  - Consequence: the player learns the identity of every completed session. Later ratings may be influenced by cues
    learned this way. This is a limitation of per-session reveal, and the analysis reports order effects.

## 3. Session procedure

1. The launcher plays the next unplayed session in manifest order.
2. The ROOM game runs fullscreen. The session ends automatically after **180 s of play with a live fly**. Pauses and
   time after a splat do not count; R restarts after a splat.
3. If the attempt ends early (Esc before 90 % of the time, or a crash), it is logged but not counted, no identity is
   shown, and the same session is offered again.
4. After a complete session, the terminal asks for ratings (1-7):
   - difficulty to hit;
   - naturalness of movement;
   - apparent reaction to the swatter;
   - overly random / twitchy (higher = worse);
   - constant escaping for no reason (higher = worse);
   - then broken / stuck / exploitable (y / n) and an optional note.
5. Ratings are saved, then the identity is revealed. The launcher asks whether to continue; sessions can be spread
   over several sittings.
6. All 30 sessions are completed. There is no early stopping, and no tuning of either policy.

## 4. Objective metrics (per session, from the unchanged tick events)

- **Recorded per session:** policy, seed, active duration, recording path.
- **Strikes:**
  - committed strike: the swatter enters the committed strike phases;
  - hit / resolution: the unchanged `TickEvents.hit` / `strike_resolved`;
  - hit rate per resolved strike.
- **Escapes:**
  - successful escape: a missed strike with an escape during the strike;
  - escape latency;
  - unnecessary escape: an escape with no committed strike and horizontal distance > 310 units (the benchmark v2
    definition).
- **Movement and lifecycle:**
  - wall / object contacts;
  - perch events (entering TOUCHDOWN);
  - takeoffs;
  - lifecycle failures: airborne stalls >= 2 s below 5 % of cruise speed, and perch bouts >= 60 s;
  - deaths.
- **Actions:** action distribution, using the benchmark `metrics.category`.
- **Recordings:** the recorder schema and semantics are unchanged. Recordings go to `artifacts/m2_4_b/recordings/`.
  Learned-policy recordings cannot be verified by `game.replay`, which rebuilds N4B1C.

## 5. Analysis (`tools/m2_4_b_analyze.py`; refuses a partial set)

- **Pairing:** by block.
- **Objective:**
  - pooled per-strike rates with a block-cluster bootstrap 95 % CI of B - A;
  - session-level paired block differences with a bootstrap CI and an exact Wilcoxon signed-rank test;
  - order-aware checks: B - A in AB vs BA blocks, and a descriptive session-index (learning) trend.
- **Subjective:** paired block differences per item (mean, median, bootstrap CI, Wilcoxon).
- **Caveat:** one player and 30 sessions. The result is descriptive, with low power; it claims only whether human play
  is consistent with the M2-EVAL-v3 direction.

## 6. Preregistered acceptance (evaluated mechanically; full text in `protocol.json`)

- **A. Not broken or exploitative:**
  - B sessions flagged broken / exploitable <= the A flags + 2;
  - median naturalness (B) >= 3;
  - no B infrastructure error.
- **B. No major twitchiness or pathology:**
  - paired mean (B - A) twitchiness <= +1.0, and the same bound for needless escaping;
  - unnecessary escapes / min (B) <= 5.36, or <= A;
  - turning action fraction (B) <= A + 0.05;
  - wall contacts / min (B) <= 1.5 x A + 0.5.
- **C. No major lifecycle regression:**
  - perches / min (B) >= 0.5 x A;
  - lifecycle failures (B) <= A + 3.
- **D. Objective direction:** pooled human hit probability per resolved strike (B) <= A. The CI is reported;
  significance is not required.
- **E. Acceptable experience:** A-D pass, paired naturalness (B - A) >= -1.0, and paired responsiveness (B - A) >= -1.0.

**Recommendation:** GO for *optional* runtime integration only if A-E all pass; otherwise NO-GO. Even on GO, the
default policy is not replaced; runtime integration requires a separate explicit approval.

## 7. Privacy

Per-session results, ratings, notes, recordings, the analysis output and the key stay under `artifacts/m2_4_b/`
(git-ignored). They are not committed unless the user explicitly asks.

## 8. Commands (from the M2 worktree `artifacts/worktrees/m2-learning`)

```
python tools/m2_4_b_blind_ab.py play       # next unplayed session; ratings; then reveal; asks to continue
python tools/m2_4_b_blind_ab.py status     # progress only
python tools/m2_4_b_blind_ab.py analyze    # after all 30 sessions
python tools/m2_4_b_blind_ab.py smoke      # headless check of both policy paths (done: both pass, HUD blocked)
```
