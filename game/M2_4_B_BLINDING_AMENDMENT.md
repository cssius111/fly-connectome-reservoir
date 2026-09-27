# M2.4-B protocol amendment 1: blinding (made before any human session)

Machine-readable record: `game/learning/m2_4_b/amendment_1.json`. Neither the original preregistration (`f048ba6`,
`protocol.json` sha256 `51f3974f...`) nor the randomisation manifest (sha256 `67fcfa9a...`) is rewritten.

## Status at the time of the amendment

**0 / 30 human sessions had been played.** `status` reported "Completed and rated: 0 / 30 sessions. Incomplete
attempts: 0." The private directory held only the key. This amendment is therefore a protocol change made before
data collection, not a change after data.

## Original rule and the flaw

The original launcher revealed each session's policy once that session's ratings were saved. Two problems:
- Every block holds exactly one A and one B session, so revealing the first session of a block makes the second
  session's identity logically known before it is played.
- Per-session feedback lets the player learn behavioural signatures and recognise the policies in later sessions.

## New rule

- **During the test:**
  - no identity is shown after individual sessions;
  - the per-session flow is: play, save objective metrics, collect ratings, save the response, then show only
    **"Response saved. Policy identity remains blinded."**, then continue or stop.
- **After session 30,** `python tools/m2_4_b_blind_ab.py reveal`:
  - locks the final ratings (sha256 of every session file in `ratings_lock.json`; files set read-only);
  - verifies the key against the public manifest (`key_sha256`) and every per-session commitment;
  - decodes the A / B assignments into `artifacts/m2_4_b/reveal.json`.

  It refuses while fewer than 30 sessions are complete and rated. `analyze` refuses to run before the lock and reveal
  exist, and checks the lock hashes.
- **Additional blinding hardening:**
  - all stdout / stderr of the game process goes to a private per-attempt log (Python and C level, including
    warnings and error text);
  - session files store only the commitment, never the policy;
  - labels are neutral ("Session 07 / 30");
  - the per-session strikes / hits summary and error details are no longer printed.

## Unchanged

- The 30-session manifest and its assignments (not regenerated); the 15 paired blocks with the same world seed per
  block; the secret-key assignment and the commitments.
- Policies A and B; the session length (180 s of live-fly play) and the completion rule.
- The objective metrics and their definitions, the rating items, the analysis plan and acceptance checks A-E.
- The privacy rule and the runtime boundary.

## Player-visible channel audit

| Channel | Finding |
|---|---|
| Window title | "MaleCNS fly-swatter" for both policies (recorded by the smoke test) |
| HUD | Gameplay HUD identical for both (time, strikes, hits, misses, escapes, rates, REC dot, key hints). The neural HUD is forced off by a read-only property; an injected H key leaves it off |
| Startup messages | Identical splash texts ("Loading MaleCNS connectome ...", "Compiling simulation kernels ...") |
| Terminal stdout / stderr | Game output goes to a private log; the launcher text is neutral and scanned for identity tokens |
| Checkpoint filename / path | Never printed |
| Policy class name | Never printed in the play flow |
| Recorder directory / file names | UTC timestamp + random uuid; fixed file names. The recorder manifest (which names the policy class) is a private artifact under `artifacts/m2_4_b/` |
| Session summary | Removed |
| Crash / error messages | Private log only; the player sees a neutral "ended early or an error occurred" message |
| Rating prompt, "continue?" prompt, `status` | Neutral; scanned |
| Inherent | The fly's behaviour itself, which is what is being evaluated |

Identity tokens scanned: N4B1C, FixedEscapePolicy, ManeuverPolicy, learned, baseline, checkpoint, candidate, .npz,
M2.4-A, m2_4_a, "policy A / B", seed_2, ckpt, and standalone "A" / "B".

## Final smoke test (`tools/m2_4_b_blind_smoke.py`)

The test runs in a temporary sandbox with a synthetic key and scripted synthetic inputs. It never uses the real
manifest, and no real human response is created. The real launcher runs as a subprocess. Sandbox block 1 holds one A
and one B session, so both policy paths were scanned.

| Check | Result |
|---|---|
| 1. Session 1 completes | pass |
| 2. Ratings can be saved | pass |
| 3. Assignment hidden afterwards (blinded message, no identity token, commitment only in the file) | pass |
| 4. Starting session 2 reveals neither session | pass |
| 5. Not exposed via the HUD (H key injected, neural HUD stays off, neutral caption) or the console; `status` neutral | pass |
| 6. `reveal` refuses before 30 completed sessions ("Reveal refused: 2 / 30") | pass |
| 7. `reveal` succeeds on a synthetic fully completed sandbox, verifies all commitments, decodes exactly the key's assignments; `play` then refuses | pass |

Code hashes after the amendment are listed in `amendment_1.json`.
