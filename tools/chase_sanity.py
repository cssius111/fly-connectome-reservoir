"""Scripted untrained BIO FLY chase diagnostics; human playtest remains the acceptance test.

    python tools/chase_sanity.py --label m1-3

Four fixed seeds: fresh episode, one second tracking from 300 units above,
then approach without clicking, click at 1.90 s, and observe the lethal window.
The controller may see coordinates because it represents the player, never
because those coordinates enter FlyLoop. No fitting or hit-rate optimization.
"""
from __future__ import annotations

import argparse
import json
import math
import os
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("NUMBA_NUM_THREADS", "4")

from game.session import Session, calibration_provenance, load_config
from game.world import StrikePhase

SEEDS = (101, 102, 103, 104)
APPROACH_TICK = 50
CLICK_TICK = 95
TICKS = 160


def chase(session: Session, seed: int) -> list[dict]:
    session.reset(seed)
    rows = []
    for tick in range(TICKS):
        w = session.world
        distance = 300.0 if tick < APPROACH_TICK else max(15.0, 300.0 - (tick - APPROACH_TICK) * 18.0)
        pointer = (w.fly.x, w.fly.y - distance)
        previous = (w.fly.x, w.fly.y)
        event = session.tick(pointer=pointer, strike=tick == CLICK_TICK)
        motor, action, retina = session.fly_loop.last_motor, session.fly_loop.last_action, session.last_retina
        rows.append({"tick": tick, "time_seconds": tick * session.tick_seconds,
                     "pointer": pointer, "phase": w.swatter.phase.value,
                     "alive": w.fly.alive, "hit": event.hit,
                     "position": [w.fly.x, w.fly.y], "heading": w.fly.heading,
                     "distance_moved": math.dist(previous, (w.fly.x, w.fly.y)),
                     "speed": math.hypot(w.fly.vx, w.fly.vy),
                     "theta": retina.theta, "theta_dot": retina.theta_dot,
                     "azimuth": retina.azimuth, "drive": session.encoder.last_drive,
                     "dnp01_left": motor.dnp01_left, "dnp01_right": motor.dnp01_right,
                     "turn": action.turn, "escape": action.escape,
                     "saccade_kind": w.saccades.kind, "saccade_request": action.saccade,
                     "strength": action.strength if action.escape else 0.0,
                     "state": session.policy_diagnostics.get("behavior_state")})
    return rows


def summarize(rows: list[dict], dt: float) -> dict:
    approach = [r for r in rows if APPROACH_TICK <= r["tick"] < CLICK_TICK]
    responses = [r for r in approach if r["escape"] or abs(r["turn"]) > 0.03]
    active = next(r for r in rows if r["phase"] == StrikePhase.ACTIVE.value)
    first = responses[0] if responses else None
    return {"click_seconds": CLICK_TICK * dt,
            "first_lethal_seconds": active["time_seconds"],
            "first_pre_click_evasion_seconds": None if first is None else first["time_seconds"],
            "pre_click_evasion": bool(responses),
            "lead_before_lethal_seconds": None if first is None else active["time_seconds"] - first["time_seconds"],
            "pre_click_peak_dnp01": max(r["dnp01_left"] + r["dnp01_right"] for r in approach),
            "path_before_click": sum(r["distance_moved"] for r in rows[:CLICK_TICK]),
            "max_step_distance": max(r["distance_moved"] for r in rows),
            "hit": any(r["hit"] for r in rows)}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--label", choices=("m1-2", "m1-3"), default="m1-3")
    args = parser.parse_args()
    started = time.perf_counter()
    config = load_config()
    session = Session(config)
    trials = []
    for seed in SEEDS:
        rows = chase(session, seed)
        summary = {"seed": seed, **summarize(rows, session.tick_seconds)}
        trials.append({**summary, "trace": rows})
        print(json.dumps(summary), flush=True)
    record = {"provenance": calibration_provenance(config),
              "scenario": "track far, approach at 1.00s, click at 1.90s; fixed seeds, no fitting",
              "limitation": "Scripted regression only; human playtest is the acceptance criterion. Outcomes are not a gameplay quality score.",
              "wall_seconds": time.perf_counter() - started, "trials": trials}
    full = ROOT / "artifacts" / args.label / "chase.json"
    full.parent.mkdir(parents=True, exist_ok=True)
    full.write_text(json.dumps(record, indent=2), encoding="utf-8")
    summary = {**record, "trials": [{k: v for k, v in t.items() if k != "trace"} for t in trials]}
    (ROOT / "results" / "game" / ("chase_" + args.label.replace("-", "_") + ".json")).write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    return 0 if all(t["pre_click_evasion"] for t in trials) else 1


if __name__ == "__main__":
    raise SystemExit(main())
