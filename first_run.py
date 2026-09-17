"""Verify data integrity, then exercise the installed FlyBrain CPU API."""
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import time
import zipfile

os.environ.setdefault("NUMBA_NUM_THREADS", "4")
import numpy as np
from flybrain import FlyBrain
from flybrain.data import FILES

ROOT = Path(__file__).resolve().parent


def verify_data():
    result = {}
    for name, expected in FILES.items():
        path = ROOT / "data" / name
        with path.open("rb") as f:
            sha = hashlib.file_digest(f, "sha256").hexdigest()
        assert sha == expected, f"SHA256 mismatch: {name}"
        with zipfile.ZipFile(path) as z:
            assert z.testzip() is None, f"Corrupt NPZ: {name}"
        result[name] = {"bytes": path.stat().st_size, "sha256": sha}
    return result


def main():
    report = {"files": verify_data(), "versions": {}}
    for name in ("flybrain", "numpy", "scipy", "numba", "llvmlite"):
        report["versions"][name] = importlib.metadata.version(name)
    t = time.perf_counter()
    brain = FlyBrain(data=ROOT / "data", seed=64, device="cpu")
    report.update(neurons=brain.n, connections=len(brain.weights), load_seconds=time.perf_counter()-t)
    assert brain.n == 166700 and len(brain.weights) == 25582938
    assert np.isfinite(brain.weights).all()
    report["populations"] = {f"{ct}_{s}": len(brain.cells([ct], side=s))
        for ct in ("LC4", "LPLC2", "LC10a", "descending_neuron", "DNp01") for s in ("L", "R")}
    idx = brain.cells(["LC4", "LPLC2"], side="L")
    t = time.perf_counter()
    report["first_step_spikes"] = len(brain.step(inject=[(idx, 0.8)]))
    report["first_step_seconds_including_jit"] = time.perf_counter()-t
    t = time.perf_counter()
    counts = [len(brain.step(inject=[(idx, 0.8)])) for _ in range(50)]
    report["warm_step_ms"] = 1000*(time.perf_counter()-t)/50
    report["last_step_spikes"] = counts[-1]
    report["numba_threads"] = int(os.environ["NUMBA_NUM_THREADS"])
    # Same seed, same input, same spikes: meaningful check of trial reset.
    def replay():
        brain.reset(123)
        return [brain.step(inject=[(idx, 0.8)]).copy() for _ in range(12)]
    a, b = replay(), replay()
    assert all(np.array_equal(x, y) for x, y in zip(a, b))
    report["reset_replay_exact"] = True
    out = ROOT / "results"
    out.mkdir(exist_ok=True)
    (out / "smoke.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2), flush=True)


if __name__ == "__main__":
    main()
