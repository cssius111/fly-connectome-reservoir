"""Frozen MaleCNS-derived LIF reservoir; train only a linear activity readout.

No images or eye model. Direct voltage injection into LC4/LPLC2 feature cells.
All splits, amplitudes and noise seeds are generated before network simulation.
"""
import argparse
import csv
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import time

ROOT = Path(__file__).resolve().parent
os.environ.setdefault("NUMBA_NUM_THREADS", "4")
os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
import numba
import numpy as np
from scipy.linalg import solve
from flybrain import FlyBrain
from first_run import verify_data


def digest_arrays(*arrays):
    h = hashlib.sha256()
    for a in arrays:
        h.update(memoryview(np.ascontiguousarray(a)).cast("B"))
    return h.hexdigest()


def make_trials(cfg, task, seed):
    spec = cfg["tasks"][task]
    rows, drives = [], []
    task_id = list(cfg["tasks"]).index(task)
    for split_id, (split, n) in enumerate((("train", cfg["train_trials"]),
            ("validation", cfg["validation_trials"]), ("test", cfg["test_trials"]))):
        assert n % 2 == 0
        seeds = np.random.SeedSequence([seed, task_id, split_id]).spawn(3)
        label_rng, amp_rng, noise_rng = [np.random.default_rng(s) for s in seeds]
        labels = np.tile([0, 1], n//2)
        label_rng.shuffle(labels)
        for trial, label in enumerate(labels):
            amp = float(amp_rng.uniform(*cfg["stimulus_amplitude"]))
            noise_seed = int(noise_rng.integers(0, 2**63-1))
            drive = np.zeros((spec["steps"], 2), dtype=np.float32)
            a, b = spec["pulse1"]
            drive[a:b, label] = amp
            if task == "order":
                a, b = spec["pulse2"]
                drive[a:b, 1-label] = amp
            rows.append(dict(task=task, seed=seed, split=split, trial=trial,
                label=int(label), amplitude=amp, noise_seed=noise_seed))
            drives.append(drive)
    noise_seeds = [r["noise_seed"] for r in rows]
    assert len(set(noise_seeds)) == len(noise_seeds)
    return rows, np.stack(drives)


def fit_ridge(x, y, alpha):
    """Training-only scaling; dual ridge avoids a 1314 x 1314 solve."""
    mean = x.mean(axis=0, dtype=np.float64)
    scale = x.std(axis=0, dtype=np.float64)
    scale[scale < 1e-8] = 1.0
    z = (x-mean)/scale
    intercept = float(y.mean())
    kernel = z @ z.T
    kernel.flat[::len(kernel)+1] += alpha
    coef = z.T @ solve(kernel, y-intercept, assume_a="pos")
    return dict(mean=mean, scale=scale, coef=coef, intercept=intercept, alpha=alpha)


def predict(model, x):
    return (((x-model["mean"])/model["scale"]) @ model["coef"] + model["intercept"] >= 0.5).astype(int)


def select_fit(x, y, splits, alphas):
    tr, va = splits == "train", splits == "validation"
    # Alpha order is fixed before any result: prefer larger regularization on ties.
    scores = [np.mean(predict(fit_ridge(x[tr], y[tr], a), x[va]) == y[va]) for a in alphas]
    alpha = alphas[int(np.argmax(scores))]
    model = fit_ridge(x[tr | va], y[tr | va], alpha)
    return model, float(max(scores))


def wilson(correct, total):
    z = 1.95996398454
    p = correct/total
    den = 1+z*z/total
    center = (p+z*z/(2*total))/den
    half = z*np.sqrt(p*(1-p)/total+z*z/(4*total*total))/den
    return float(center-half), float(center+half)


def evaluate(x, rows, cfg, name, output, permute=False):
    y = np.array([r["label"] for r in rows])
    splits = np.array([r["split"] for r in rows])
    te = splits == "test"
    fit_y = y.copy()
    if permute:
        rng = np.random.default_rng(rows[0]["seed"] + 90000)
        for split in ("train", "validation"):
            idx = np.flatnonzero(splits == split)
            fit_y[idx] = rng.permutation(fit_y[idx])
    model, va = select_fit(x, fit_y, splits, cfg["ridge_alphas"])
    predictions = predict(model, x[te])
    correct = int(np.sum(predictions == y[te]))
    lo, hi = wilson(correct, int(te.sum()))
    task, seed = rows[0]["task"], rows[0]["seed"]
    np.savez_compressed(output / f"model_{task}_{seed}_{name}.npz", **model)
    return dict(task=task, seed=seed, method=name, accuracy=correct/int(te.sum()),
        correct=correct, n_test=int(te.sum()), wilson_low=lo, wilson_high=hi,
        alpha=model["alpha"], validation_accuracy=va,
        predictions=predictions.tolist(), test_labels=y[te].tolist())


def simulate(brain, rows, drives, cfg, task, inputs, readout, name):
    spec = cfg["tasks"][task]
    mapping = np.full(brain.n, -1, np.int32)
    mapping[readout] = np.arange(len(readout))
    x = np.zeros((len(rows), len(readout)), np.float32)
    # Mean descending-neuron response, by label and anatomical side, across TEST trials.
    traces = np.zeros((2, spec["steps"], 2), np.float64)
    test_counts = np.zeros(2, dtype=int)
    left_mask, right_mask = brain.side[readout] == "L", brain.side[readout] == "R"
    r0, r1 = spec["readout"]
    all_spike_sum = 0
    saturated_sum = 0
    t0 = time.perf_counter()
    for i, (row, drive) in enumerate(zip(rows, drives)):
        brain.reset(row["noise_seed"])
        for t, amplitudes in enumerate(drive):
            inject = [(inputs[s], float(amplitudes[s])) for s in range(2) if amplitudes[s] != 0]
            fired = brain.step(inject=inject)
            dn = mapping[fired]
            dn = dn[dn >= 0]
            all_spike_sum += len(fired)
            if r0 <= t < r1:
                x[i, dn] += 1
            if row["split"] == "test":
                traces[row["label"], t, 0] += left_mask[dn].sum()/left_mask.sum()/brain.dt
                traces[row["label"], t, 1] += right_mask[dn].sum()/right_mask.sum()/brain.dt
        if row["split"] == "test":
            test_counts[row["label"]] += 1
        saturated_sum += int(np.sum(x[i] == r1-r0))
        if (i+1) % 20 == 0:
            print(f"{task} {name} seed={row['seed']} trials={i+1}/{len(rows)} elapsed={time.perf_counter()-t0:.1f}s", flush=True)
    traces /= test_counts[:, None, None]
    x /= (r1-r0)*brain.dt
    assert np.isfinite(x).all()
    seconds = time.perf_counter()-t0
    return x, traces, dict(seconds=seconds, ms_per_step=1000*seconds/(len(rows)*spec["steps"]),
        mean_all_neuron_hz=all_spike_sum/(len(rows)*spec["steps"]*brain.dt*brain.n),
        readout_ceiling_fraction=saturated_sum/x.size,
        active_readout_fraction=float(np.mean(np.any(x > 0, axis=0))))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, default=ROOT/"config.json")
    parser.add_argument("--output", type=Path, default=ROOT/"results")
    args = parser.parse_args()
    cfg = json.loads(args.config.read_text(encoding="utf-8"))
    numba.set_num_threads(cfg["numba_threads"])
    args.output.mkdir(exist_ok=True)
    artifacts = ROOT/"artifacts"/args.output.name
    artifacts.mkdir(parents=True, exist_ok=True)
    started = time.perf_counter()
    manifest = dict(config=cfg, files=verify_data(), platform=platform.platform(),
        python=platform.python_version(), started_utc=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        versions={d.metadata["Name"]: d.version for d in importlib.metadata.distributions()},
        source_sha256={p.name: hashlib.sha256(p.read_bytes()).hexdigest()
            for p in (ROOT/"experiment.py", ROOT/"first_run.py", args.config)})
    brain = FlyBrain(data=ROOT/"data", device="cpu", seed=64,
        dt=cfg["dt_seconds"], sensory_input=cfg["sensory_input"], refractory=cfg["refractory_seconds"])
    for key in ("gain", "tonic", "noise_hz", "noise_amp"):
        setattr(brain, key, cfg[key])
    original = brain.indptr, brain.indices, brain.weights
    original_digest = digest_arrays(*original)
    rng = np.random.default_rng(cfg["encoder_seed"])
    inputs = [[], []]
    population = {}
    for ct in ("LC4", "LPLC2"):
        pools = [brain.cells([ct], side=s) for s in ("L", "R")]
        n = min(map(len, pools))
        population[ct] = {"available_L": len(pools[0]), "available_R": len(pools[1]), "used_per_side": n}
        for i in range(2):
            inputs[i].extend(rng.choice(pools[i], n, replace=False).tolist())
    inputs = [np.sort(np.array(i, dtype=np.int64)) for i in inputs]
    readout = brain.cells(["descending_neuron"])
    assert len(inputs[0]) == len(inputs[1]) and len(inputs[0]) > 0
    assert len(np.intersect1d(np.concatenate(inputs), readout)) == 0
    manifest.update(neurons=brain.n, connections=len(brain.weights),
        readout_neurons=len(readout), input_populations=population,
        original_network_sha256=original_digest, numba_threads=numba.get_num_threads())
    np.savez_compressed(artifacts/"neuron_indices.npz", left=inputs[0], right=inputs[1], readout=readout)
    # Exclude first JIT compilation from per-trial runtime measurements.
    brain.step()
    datasets = {}
    trial_rows = []
    for seed in cfg["seeds"]:
        for task in cfg["tasks"]:
            rows, drives = make_trials(cfg, task, seed)
            trial_rows.extend(rows)
            datasets[seed, task] = rows, drives
    with (args.output/"trials.csv").open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(trial_rows[0]))
        writer.writeheader()
        writer.writerows(trial_rows)
    records, runtimes, activity = [], [], {}
    # Evaluate raw input controls before any reservoir readouts are available.
    for (seed, task), (rows, drives) in datasets.items():
        raw = {"raw_history": drives.reshape(len(rows), -1), "raw_integrated": drives.sum(axis=1)}
        if task == "order":
            assert np.array_equal(raw["raw_integrated"][:, 0], raw["raw_integrated"][:, 1])
            a, b = cfg["tasks"][task]["readout"]
            assert not drives[:, a:b].any()
        for name, features in raw.items():
            records.append(evaluate(features, rows, cfg, name, artifacts))
    for seed in cfg["seeds"]:
        for name in ("connectome", "target_permutation", "no_connections"):
            brain.indptr, brain.indices, brain.weights = original
            if name == "target_permutation":
                # A global postsynaptic identity null, NOT per-neuron degree-preserving rewiring.
                permutation = np.random.default_rng(seed+70000).permutation(brain.n)
                brain.indices = permutation[original[1]].astype(original[1].dtype)
                assert len(np.unique(permutation)) == brain.n
                assert np.array_equal(np.sort(np.bincount(brain.indices, minlength=brain.n)),
                    np.sort(np.bincount(original[1], minlength=brain.n)))
            elif name == "no_connections":
                brain.indptr = np.zeros_like(original[0])
                brain.indices = np.empty(0, original[1].dtype)
                brain.weights = np.empty(0, original[2].dtype)
            before = digest_arrays(brain.indptr, brain.indices, brain.weights)
            for task in cfg["tasks"]:
                rows, drives = datasets[seed, task]
                x, traces, runtime = simulate(brain, rows, drives, cfg, task, inputs, readout, name)
                runtime.update(task=task, seed=seed, method=name, network_sha256=before)
                runtimes.append(runtime)
                np.savez_compressed(artifacts/f"activity_{task}_{seed}_{name}.npz", activity_hz=x, drive=drives)
                activity[f"{task}_{seed}_{name}"] = traces
                result = evaluate(x, rows, cfg, name, artifacts)
                records.append(result)
                print(f"RESULT {task} {name} seed={seed}: {result['correct']}/{result['n_test']} = {result['accuracy']:.3f}", flush=True)
                if name == "connectome":
                    records.append(evaluate(x, rows, cfg, "shuffled_labels", artifacts, permute=True))
                (args.output/"metrics.json").write_text(json.dumps(records, indent=2), encoding="utf-8")
            assert before == digest_arrays(brain.indptr, brain.indices, brain.weights), "Network mutated!"
    assert original_digest == digest_arrays(*original)
    manifest["frozen_network_verified"] = True
    manifest["total_seconds"] = time.perf_counter()-started
    manifest["runtimes"] = runtimes
    manifest["finished_utc"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    (args.output/"manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    np.savez_compressed(args.output/"population_traces.npz", **activity)
    # Full resolved environment; no local paths, credentials, data or virtualenv contents.
    (ROOT/"requirements-lock.txt").write_text("\n".join(f"{k}=={v}" for k, v in sorted(manifest["versions"].items()))+"\n", encoding="utf-8")
    print(f"COMPLETE: {manifest['total_seconds']:.1f}s; frozen network checks passed.", flush=True)


if __name__ == "__main__":
    main()
