"""Record and exactly replay a deterministic M1.7 interaction fixture; no learning."""
import argparse
import json
import os
from pathlib import Path
import sys
import time

os.environ.setdefault("NUMBA_NUM_THREADS", "4")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from game.session import Session, load_config
from game.session_recording import HumanSessionRecorder
from game.replay import replay_session


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--record-dir", type=Path, default=ROOT/"results/game/sessions")
    parser.add_argument("--report", type=Path, default=ROOT/"artifacts/m1-7/session-sanity.json")
    args = parser.parse_args()
    started = time.perf_counter()
    config_path = ROOT/"game_room_config.json"
    recorder = HumanSessionRecorder(args.record_dir, config_file=config_path)
    session = Session(load_config(config_path), seed=101, mode="evaluation", recorder=recorder)
    try:
        for episode, seed in enumerate((101, 1101, 2101)):
            if episode:
                session.reset(seed)
            for tick in range(400):
                if tick == 50:
                    session.record_control("pause", paused=True)
                    session.record_control("pause", paused=False)
                if tick == 225:
                    session.request_strike()  # Accepted/rejected between-tick input is retained.
                if episode == 0:
                    pointer = (550+5*tick, 750+tick)
                elif episode == 1:
                    fly = session.world.fly
                    pointer = (fly.x+fly.vx*.15, fly.y+fly.vy*.15)
                else:
                    pointer = (3250-5*tick, 1750-2*tick)
                session.tick(pointer=pointer, strike=tick in (100, 300))
    finally:
        session.close()
    result = {
        "fixture": "three deterministic 8-second episodes; sweeps, pursuit, pause and between-tick clicks",
        "session_directory": str(recorder.path),
        "replay": replay_session(recorder.path),
        "summary": json.loads((recorder.path/"summary.json").read_text(encoding="utf-8")),
        "elapsed_seconds": time.perf_counter()-started,
        "files_bytes": {p.name:p.stat().st_size for p in recorder.path.iterdir() if p.is_file()},
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(result, indent=2)+"\n", encoding="utf-8")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
