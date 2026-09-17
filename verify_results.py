"""Audit saved predictions, splits, source hashes and an exact neuronal replay."""
import hashlib
import json
import numpy as np
from flybrain import FlyBrain
from experiment import ROOT, make_trials, predict, digest_arrays


def main():
    out = ROOT/"results"
    manifest = json.loads((out/"manifest.json").read_text())
    records = json.loads((out/"metrics.json").read_text())
    cfg = manifest["config"]
    for name, sha in manifest["source_sha256"].items():
        assert hashlib.sha256((ROOT/name).read_bytes()).hexdigest() == sha
    assert len(records) == 36
    for r in records:
        rows, drives = make_trials(cfg, r["task"], r["seed"])
        te = np.array([row["split"] == "test" for row in rows])
        y = np.array([row["label"] for row in rows])[te]
        np.testing.assert_array_equal(y, r["test_labels"])
        if r["method"] == "raw_history":
            x = drives.reshape(len(rows), -1)
        elif r["method"] == "raw_integrated":
            x = drives.sum(axis=1)
        else:
            network = "connectome" if r["method"] == "shuffled_labels" else r["method"]
            x = np.load(ROOT/"artifacts"/"results"/f"activity_{r['task']}_{r['seed']}_{network}.npz")["activity_hz"]
        model = dict(np.load(ROOT/"artifacts"/"results"/f"model_{r['task']}_{r['seed']}_{r['method']}.npz"))
        p = predict(model, x[te])
        np.testing.assert_array_equal(p, r["predictions"])
        assert int(np.sum(p == y)) == r["correct"]
        assert r["accuracy"] == r["correct"]/r["n_test"]
    # Re-run one held-out trial per task from scratch, independently of collector code.
    brain = FlyBrain(data=ROOT/"data", device="cpu", seed=64,
        dt=cfg["dt_seconds"], sensory_input=cfg["sensory_input"], refractory=cfg["refractory_seconds"])
    for k in ("gain", "tonic", "noise_hz", "noise_amp"):
        setattr(brain, k, cfg[k])
    indices = np.load(ROOT/"artifacts"/"results"/"neuron_indices.npz")
    readout = indices["readout"]
    initial = digest_arrays(brain.indptr, brain.indices, brain.weights)
    assert initial == manifest["original_network_sha256"]
    replayed = []
    for task in cfg["tasks"]:
        rows, d = make_trials(cfg, task, cfg["seeds"][0])
        i = next(i for i, r in enumerate(rows) if r["split"] == "test")
        brain.reset(rows[i]["noise_seed"])
        counts = np.zeros(brain.n, np.float32)
        a, b = cfg["tasks"][task]["readout"]
        for t, amp in enumerate(d[i]):
            fired = brain.step(inject=[(indices[side], float(amp[s])) for s, side in enumerate(("left", "right")) if amp[s] != 0])
            if a <= t < b:
                counts[fired] += 1
        replay = counts[readout]/((b-a)*brain.dt)
        saved = np.load(ROOT/"artifacts"/"results"/f"activity_{task}_{cfg['seeds'][0]}_connectome.npz")["activity_hz"][i]
        np.testing.assert_array_equal(replay, saved)
        replayed.append({"task": task, "seed": cfg["seeds"][0], "trial_index": i, "exact": True})
    assert initial == digest_arrays(brain.indptr, brain.indices, brain.weights)
    result = {"prediction_records_verified": len(records), "source_hashes_match": True,
        "held_out_neuronal_replays": replayed, "frozen_weights_verified": True}
    (out/"verification.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
