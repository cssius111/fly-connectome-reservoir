"""Measure DNp01 under loom vs no loom, then record an escape threshold.

Run before playing:

    python tools/calibrate_escape.py

The threshold is never hand-picked. It is chosen by a rule fixed before looking
at the numbers:

    threshold = the smallest value on the sweep grid that produces ZERO false
                triggers across every tick of every no-loom trial

which is the lowest (= fastest-reacting) threshold that a resting fly would
never cross on its own. Detection rate and trigger latency under a real strike
are then reported at that threshold, along with the full sweep, so the choice
is auditable rather than asserted.

Both conditions are driven through the *actual* game pipeline -- World ->
RetinaProjector -> RetinalEncoder -> connectome -> DNp01 trace -- with an
escape-disabled policy, so the fly holds still and the measurement reflects
sensory drive rather than its own motion.

Writes artifacts/game/calibration.json (full record, git-ignored),
artifacts/game/calibration.png, and results/game/calibration.json (the small
committed summary the game loads at startup).
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import os
import platform
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("NUMBA_NUM_THREADS", "4")
os.environ.setdefault("MPLCONFIGDIR", str(ROOT / "artifacts" / "matplotlib"))

import numpy as np  # noqa: E402

from game.action import Action, MotorState  # noqa: E402
from game.session import Session, load_config  # noqa: E402
from game.world import StrikePhase  # noqa: E402

# Sweep grid, fixed before measurement.
GRID = np.round(np.arange(0.05, 6.0001, 0.05), 4)
DETECTION_TARGET = 0.90


class RecordingPolicy:
    """Never escapes, so the fly stays put and we see pure sensory drive."""

    def __init__(self):
        self.history: list[MotorState] = []

    def reset(self) -> None:
        self.history = []

    def decide(self, motor: MotorState) -> Action:
        self.history.append(motor)
        return Action()


def _trial(session: Session, policy: RecordingPolicy, seed: int, offset: tuple[float, float],
           ticks: int, click_tick: int | None) -> dict:
    """One scripted trial. The swatter hovers `offset` from the fly; if
    `click_tick` is given, a strike is launched there."""
    session.reset(seed)
    policy.reset()
    fly = session.world.fly
    pointer = (fly.x + offset[0], fly.y + offset[1])
    # Let the swatter settle at the hover position before anything is recorded.
    for _ in range(40):
        session.tick(pointer=pointer, strike=False)
    settle = len(policy.history)
    phases = []
    for t in range(ticks):
        session.tick(pointer=pointer, strike=(click_tick is not None and t == click_tick))
        phases.append(session.world.swatter.phase)
    total = np.array([m.dnp01_total for m in policy.history[settle:]], dtype=np.float64)
    left = np.array([m.dnp01_left for m in policy.history[settle:]], dtype=np.float64)
    right = np.array([m.dnp01_right for m in policy.history[settle:]], dtype=np.float64)
    committed = np.array([p in (StrikePhase.WINDUP, StrikePhase.ACTIVE) for p in phases])
    return {"total": total, "left": left, "right": right, "committed": committed,
            "click_tick": click_tick}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--trials", type=int, default=16, help="trials per condition")
    parser.add_argument("--config", type=Path, default=ROOT / "game_config.json")
    args = parser.parse_args()

    config = load_config(args.config)
    tick = float(config["sim"]["tick_seconds"])
    started = time.perf_counter()
    policy = RecordingPolicy()
    session = Session(config, policy=policy, root=ROOT)
    # Observe the whole strike: with the kill enabled the fly would die
    # mid-window and truncate the measurement. Recorded in the artifact.
    session.world.collisions_enabled = False
    print(f"brain: {session.brain.n} neurons, {len(session.brain.weights)} connections, "
          f"sensory_input={config['brain']['sensory_input']}", flush=True)
    print(f"balanced input populations: {session.encoder.population}", flush=True)

    ticks = 90
    click_tick = 20
    null_trials, loom_trials = [], []
    rng = np.random.default_rng(int(config["encoder"]["encoder_seed"]))
    for i in range(args.trials):
        # No loom: the swatter hovers at a plausible aiming distance, no strike.
        angle = float(rng.uniform(0, 2 * np.pi))
        radius = float(rng.uniform(30.0, 170.0))
        null_trials.append(_trial(session, policy, 4000 + i,
                                  (np.cos(angle) * radius, np.sin(angle) * radius),
                                  ticks, None))
        # Loom: same geometry, but the player commits to a strike.
        side = -1.0 if i % 2 == 0 else 1.0
        loom_trials.append(_trial(session, policy, 5000 + i,
                                  (side * float(rng.uniform(5.0, 55.0)),
                                   float(rng.uniform(-40.0, 40.0))),
                                  ticks, click_tick))
        print(f"  trial {i+1}/{args.trials}: null peak {null_trials[-1]['total'].max():.3f}, "
              f"loom peak {loom_trials[-1]['total'].max():.3f}", flush=True)

    null_all = np.concatenate([t["total"] for t in null_trials])
    null_peaks = np.array([t["total"].max() for t in null_trials])
    loom_peaks = np.array([t["total"][t["committed"]].max() if t["committed"].any() else 0.0
                           for t in loom_trials])

    # Sweep. A "false trigger" is any no-loom tick at or above the threshold; a
    # "detection" is a crossing while the player is committed (wind-up or active).
    sweep = []
    for thr in GRID:
        false_ticks = int((null_all >= thr).sum())
        false_trials = int((null_peaks >= thr).sum())
        latencies = []
        detected = 0
        for t in loom_trials:
            idx = np.flatnonzero((t["total"] >= thr) & t["committed"])
            if len(idx):
                detected += 1
                latencies.append((idx[0] - t["click_tick"]) * tick)
        sweep.append({"threshold": float(thr),
                      "false_trigger_ticks": false_ticks,
                      "false_trigger_trials": false_trials,
                      "false_trigger_rate_per_tick": false_ticks / len(null_all),
                      "detection_rate": detected / len(loom_trials),
                      "median_latency_seconds": float(np.median(latencies)) if latencies else None})

    clean = [s for s in sweep if s["false_trigger_ticks"] == 0]
    if not clean:
        print("FAILED: every candidate threshold false-triggers without a loom.", file=sys.stderr)
        return 1
    chosen = clean[0]
    threshold = chosen["threshold"]
    rule = ("smallest sweep-grid value with zero false triggers across all no-loom ticks")

    # Side selectivity during the committed window, recorded for the report.
    side_rows = []
    for t in loom_trials:
        w = t["committed"]
        if w.any():
            side_rows.append((float(t["left"][w].max()), float(t["right"][w].max())))
    record = {
        "created_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "rule": rule,
        "measurement_conditions": {
            "collisions_enabled": False,
            "escape_disabled": True,
            "note": "the fly is held still and cannot be killed, so DNp01 reflects sensory drive only",
        },
        "escape_threshold": threshold,
        "detection_rate": chosen["detection_rate"],
        "median_latency_seconds": chosen["median_latency_seconds"],
        "false_trigger_ticks": chosen["false_trigger_ticks"],
        "detection_target": DETECTION_TARGET,
        "detection_target_met": chosen["detection_rate"] >= DETECTION_TARGET,
        "trials_per_condition": args.trials,
        "ticks_per_trial": ticks,
        "tick_seconds": tick,
        "no_loom": {"ticks": int(len(null_all)), "mean": float(null_all.mean()),
                    "p99": float(np.percentile(null_all, 99)), "max": float(null_all.max()),
                    "trial_peaks": null_peaks.tolist()},
        "loom": {"mean_peak": float(loom_peaks.mean()), "min_peak": float(loom_peaks.min()),
                 "max_peak": float(loom_peaks.max()), "trial_peaks": loom_peaks.tolist()},
        "side_peaks_during_strike": side_rows,
        "sweep": sweep,
        "config": config,
        "config_sha256": hashlib.sha256(args.config.read_bytes()).hexdigest(),
        "input_populations": session.encoder.population,
        "neurons": int(session.brain.n),
        "connections": int(len(session.brain.weights)),
        "platform": platform.platform(),
        "python": platform.python_version(),
        "versions": {n: importlib.metadata.version(n) for n in ("flybrain", "numpy", "scipy", "numba")},
        "wall_seconds": time.perf_counter() - started,
    }

    (ROOT / "artifacts" / "game").mkdir(parents=True, exist_ok=True)
    (ROOT / "results" / "game").mkdir(parents=True, exist_ok=True)
    (ROOT / "artifacts" / "game" / "calibration.json").write_text(
        json.dumps(record, indent=2), encoding="utf-8")
    summary = {k: record[k] for k in ("created_utc", "rule", "escape_threshold", "detection_rate",
                                      "median_latency_seconds", "false_trigger_ticks",
                                      "detection_target", "detection_target_met",
                                      "trials_per_condition", "tick_seconds", "no_loom", "loom",
                                      "config_sha256", "input_populations", "versions")}
    summary["no_loom"] = {k: v for k, v in record["no_loom"].items() if k != "trial_peaks"}
    summary["loom"] = {k: v for k, v in record["loom"].items() if k != "trial_peaks"}
    (ROOT / "results" / "game" / "calibration.json").write_text(
        json.dumps(summary, indent=2), encoding="utf-8")
    _plot(record, null_trials, loom_trials, tick)

    print("\n--- calibration ---")
    print(f"rule                : {rule}")
    print(f"escape_threshold    : {threshold:.3f}")
    print(f"no-loom  DNp01 trace: mean {null_all.mean():.4f}  p99 {np.percentile(null_all, 99):.3f}  "
          f"max {null_all.max():.3f}")
    print(f"loom     DNp01 peak : mean {loom_peaks.mean():.3f}  min {loom_peaks.min():.3f}  "
          f"max {loom_peaks.max():.3f}")
    print(f"detection rate      : {chosen['detection_rate']:.2f} "
          f"(target {DETECTION_TARGET}, met={chosen['detection_rate'] >= DETECTION_TARGET})")
    print(f"median latency      : {chosen['median_latency_seconds']} s after click")
    print(f"false triggers      : {chosen['false_trigger_ticks']} / {len(null_all)} no-loom ticks")
    print(f"wrote artifacts/game/calibration.json, artifacts/game/calibration.png, "
          f"results/game/calibration.json")
    if chosen["detection_rate"] < DETECTION_TARGET:
        print("WARNING: detection below target; the fly will often fail to react.", file=sys.stderr)
    return 0


def _plot(record, null_trials, loom_trials, tick) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    thr = record["escape_threshold"]
    fig, axes = plt.subplots(1, 3, figsize=(14, 4.2))
    ax = axes[0]
    for t in loom_trials:
        ax.plot(np.arange(len(t["total"])) * tick, t["total"], color="#235C91", alpha=0.45, lw=1)
    for t in null_trials:
        ax.plot(np.arange(len(t["total"])) * tick, t["total"], color="#787878", alpha=0.35, lw=1)
    ax.axhline(thr, color="#B22222", ls="--", lw=1.4, label=f"threshold {thr:.2f}")
    click = loom_trials[0]["click_tick"] * tick
    ax.axvline(click, color="#576B38", ls=":", lw=1.2, label="click")
    ax.set_xlabel("time in trial (s)")
    ax.set_ylabel("DNp01 trace (L+R)")
    ax.set_title("blue = strike, grey = no strike")
    ax.legend(fontsize=8)

    ax = axes[1]
    ax.hist(record["no_loom"]["trial_peaks"], bins=12, color="#787878", alpha=0.8, label="no loom")
    ax.hist(record["loom"]["trial_peaks"], bins=12, color="#235C91", alpha=0.8, label="loom")
    ax.axvline(thr, color="#B22222", ls="--", lw=1.4)
    ax.set_xlabel("peak DNp01 trace per trial")
    ax.set_ylabel("trials")
    ax.set_title("separation")
    ax.legend(fontsize=8)

    ax = axes[2]
    s = record["sweep"]
    g = [x["threshold"] for x in s]
    ax.plot(g, [x["detection_rate"] for x in s], color="#235C91", label="detection (loom)")
    ax.plot(g, [x["false_trigger_rate_per_tick"] for x in s], color="#B56827",
            label="false-trigger rate/tick")
    ax.axvline(thr, color="#B22222", ls="--", lw=1.4)
    ax.set_xlabel("candidate threshold")
    ax.set_ylabel("rate")
    ax.set_xlim(0, min(6.0, max(g)))
    ax.set_title("threshold sweep")
    ax.legend(fontsize=8)

    fig.suptitle("DNp01 escape-threshold calibration (untrained decoder)", fontsize=13)
    fig.tight_layout(rect=(0, 0, 1, 0.94))
    fig.savefig(ROOT / "artifacts" / "game" / "calibration.png", dpi=160)
    plt.close(fig)


if __name__ == "__main__":
    raise SystemExit(main())
