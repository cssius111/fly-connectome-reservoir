# M3.5: escapes from strikes under v27 and the M3.3 and M3.4 candidates (read-only research)

Status: **research note, 2026-10-24.** No runtime code, configuration, record or frozen system
changed.

**Why.** M3.4 (`results/game/M3_4_RETINOTOPIC_DRIVE.md`) found that a fly deciding by angular
size never escapes a hovering paddle. The N4B6 threat matrix has no strike, so whether such a fly
escapes the descending paddle was unknown. The M3.4 report named this as the first next step.

**Method.** All measurements are in `tools/m3_5_strike_escapes.py`; raw data are in
`artifacts/m3_5/strikes/` (git-ignored). The results are exploratory.
- **Protocol.** The fixed-fly strike of `tools/calibrate_escape.py`, with the runtime decoder
  live:
  - collisions, fly motion and wander are disabled;
  - the paddle settles in hover, then one strike is launched and observed for 60 ticks.
- **Positions.** The paddle hovers overhead, or 40, 80 or 150 units away at the fly's front,
  right, rear or left. The paddle radius is 144 units.
- **Seeds.** 950001-950024, 24 per position.
- **Arms.** Each uses its own committed record:
  - v27, the working ROOM configuration;
  - v29, the M3.3 candidate `9830757`;
  - v30, the M3.4 candidate `10e12f6`.

## 1. The strike as the fly sees it

Overhead strike, seed 950001. One tick is 20 ms. The click is tick 0, and contact (ACTIVE_CONTACT)
starts at tick 10 in every trial.

| Tick | 0 | 2 | 4 | 6 | 7 | 8 | 9 | 10 (contact) | 12 | 14 |
|---|---|---|---|---|---|---|---|---|---|---|
| Phase | commit | commit | fast swing | fast swing | fast swing | fast swing | fast swing | active contact | active contact | active contact |
| Height | 315 | 288 | 270 | 223 | 180 | 137 | 103 | 90 | 67 | 31 |
| θ | 33° | 35° | 40° | 44° | 52° | 66° | 85° | 103° | 114° | 131° |
| θ̇ (°/s) | 0 | 97 | 113 | 146 | 422 | 703 | 935 | 900 | 145 | 441 |

- **Commit phase.** The image grows slowly at first: 33-40° over the 100 ms commit phase.
- **Fast swing.** Most of the growth comes in the last 100 ms before contact, at 400-900°/s, like
  the end of a fast loom.
- **The size rule's timing.** A fly that decides at about 55° (the real fly's E2 threshold, and
  v30's 56.5°) reaches that size near tick 7-8. With a decision delay of a few tens of
  milliseconds it decides at or just before contact.

## 2. Results

Escape fraction, fraction decided before contact, and the median decision tick and image size:

| Position | v27 | v29 (M3.3) | v30 (M3.4) |
|---|---|---|---|
| overhead | 1.00, 1.00, tick 4, 40° | 1.00, 0.75, 8, 66° | 0.83, **0.00**, 13, 122° |
| front 40 | 1.00, 1.00, 4, 39° | 0.88, 0.12, 52, 32° | 1.00, **0.00**, 12, 116° |
| right 40 | 1.00, 1.00, 4, 40° | 0.88, 0.00, 42, 32° | 1.00, **0.00**, 12, 112° |
| rear 40 | 1.00, 1.00, 4, 39° | 0.96, 0.12, 45, 31° | 0.29, **0.00**, 14, 112° |
| left 40 | 1.00, 1.00, 4, 40° | 0.96, 0.54, 7, 41° | 1.00, **0.00**, 13, 112° |
| front 80 | 1.00, 1.00, 5, 37° | 0.83, 0.58, 8, 39° | 0.96, **0.00**, 13, 92° |
| right 80 | 1.00, 1.00, 4, 39° | 0.62, 0.33, 7, 32° | 1.00, 0.12, 12, 102° |
| rear 80 | 1.00, 1.00, 5, 37° | 0.83, 0.58, 8, 39° | **0.00** |
| left 80 | 1.00, 1.00, 4, 39° | 1.00, 0.71, 7, 45° | 1.00, 0.04, 12, 93° |
| front 150 | 1.00, 1.00, 7, 40° | 0.92, 0.75, 9, 59° | 0.21, **0.00**, 11, 68° |
| right 150 | 1.00, 1.00, 4, 36° | 0.92, 0.92, 6, 38° | 1.00, 0.08, 11, 78° |
| rear 150 | 1.00, 1.00, 7, 40° | 0.92, 0.75, 9, 59° | **0.00** |
| left 150 | 1.00, 1.00, 4, 36° | 1.00, 0.54, 7, 44° | 1.00, 0.08, 11, 72° |

What each arm does:
- **v27.**
  - It decides every strike at tick 4-7, at 36-40°, well before contact.
  - Its velocity-coded LPLC2 term fires on the slow commit-phase expansion. That is the same early
    decision M3.0 scored as an E2 gap (threshold 18.6°).
- **v29 (M3.3).**
  - It escapes most strikes, but only 0-92 % before contact, depending on the position.
  - At the 40-unit front, right and rear positions the median decision comes after the strike
    (ticks 42-52), from the paddle settling afterwards.
- **v30 (M3.4).**
  - It decides 0-12 % of strikes before contact, at tick 11-14, when the image is already
    92-122°.
  - Rear strikes are rarely escaped, because of the rear blind spot. The same holds for the
    frontal 150-unit strike, whose image stays small (68°).
  - Since v30 also escapes no hovering approach, a v30 fly in the game would be hit by almost
    every strike.

## 3. What this means

- **The strike is at the edge for a real fly too.** A size rule like the real fly's (about 54°
  plus a short delay) decides at about the moment of contact. The game's 200 ms strike is fast
  even for a real fly.
- **v30 decides too late even by its own law.** Its E2 fit (threshold 56.5°, delay -43 ms)
  predicts a decision at about tick 9-10. The measured ticks are 11-14.
- **The same late decision underlies the M3.4 failures.** Fast looms decide late in V1
  (l/v 10-20 ms after collision), V2 fails at l/v 40 ms, and V8a at l/v 10 ms. The latency of
  the decision to fast expansion is therefore the main defect to study next.
- **The left-right balance is a smaller part of it.** V8a's side difference appears only where
  this late decision is marginal.

## 4. Proposed order of the next steps

The M3.4 report listed four next steps. These results change their order:

1. **Fast-expansion decision latency.** Read-only research into why v30 decides fast looms and
   strikes late, split into its parts:
   - drive onset;
   - recruitment of covered cells, including near the zenith, where both eyes cover the disk
     only partly;
   - the network delay from LPLC2/LC4 spikes to a DNp01 doublet.
   This also covers V2 and V8a.
2. **Left-right balance by DNp01 input weight**, if it is still needed after step 1.
3. **E4**, reading DNp02 against DNp11 for the escape direction.
4. **Rear blind spot.** Whether the posterior blind spot matches the real eye's (about 50°;
   Zhao et al. 2025) for strikes from behind. This is descriptive.
