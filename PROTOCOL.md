# Frozen-connectome experiment protocol v1.0

Written before the first classifier experiment. This is a simulation experiment, not a test of learning in a living fly. Code and configuration are hashed in the run manifest.

## Data and model

Use the FlyBrain 0.1.0 prebuilt MaleCNS v1.0-derived graph: 166,700 annotated neurons and 25,582,938 signed, normalized neuron-to-neuron edges. These are **edges, not individual synapses**. Verify both NPZ files against the SHA256 values embedded in the installed package. No synaptic learning or plasticity is enabled. All networks use the same point-neuron LIF parameters in `config.json`; defaults retain sensory feedback (`sensory_input=True`). This is a model assumption with known upstream concerns about sensory activity, not a validated physiological choice.

## Input and output

Direct voltage injection into LC4/LPLC2 visual feature cells. There is no camera image, photoreceptor simulation or complete eye processing. Sample 55 LC4 and 91 LPLC2 neurons on each side once, using encoder seed 20260917; this controls the number of driven neurons and total injected voltage. Sampling all of the smaller population and a subset of the larger one is a modeling choice, not an anatomical equivalence claim. Read out all annotated descending neurons, excluding every stimulated cell. The readout receives only per-neuron spike rates in the specified window; it never receives labels, stimulus amplitudes, random seeds or trial time.

## Tasks

Time step 20 ms. Every trial starts from zero voltages/spikes and an independent fixed noise seed, with 10 steps of unstimulated warm-up (200 ms). This is a reset transient protocol, not an equilibrated resting-state experiment.

* **Side**: label 0 = left, label 1 = right. Apply one 400 ms pulse; average descending activity in the final 200 ms of that pulse. This is a deliberately easy pipeline check.
* **Order**: label 0 = left then right; label 1 = right then left. Apply two 200 ms pulses, separated by 100 ms. Each trial uses exactly the same amplitude on its two sides, making integrated left/right input identical. After the second pulse, wait 100 ms, then read 200 ms of activity with no injected input. Readout-window centers occur 110–290 ms after the second pulse ends. Success may reflect the most recent side rather than genuine sequence computation: this is a short-delay recency/memory probe, not a demonstration of complex temporal reasoning.

Amplitudes are independently drawn from Uniform(0.55, 0.95), in simulator voltage units. Separate random streams generate balanced labels, amplitudes and neuronal noise seeds. No amplitude/delay/model search is planned after looking at the test set.

## Splits and readout

Three independent simulation/data replicates: 101, 202, 303. Each task in each replicate has 60 training, 20 validation and 60 test trials, exactly balanced within each split. Split unit is an entire reset trial, never a time frame. The same trial inputs and noise seeds are reused across network conditions for paired comparisons, but are distinct across training, validation and test. Replicates are stochastic repeats of one anatomical specimen, not three animals.

Standardize using only training data, then fit a linear ridge classifier. Choose alpha from [1000, 100, 10, 1, 0.1] by validation accuracy, preferring the larger value on ties. Refit scaling and coefficients on training plus validation data, and evaluate the held-out test once. This also applies to the raw-input baselines. Readout rank is at most the number of training observations; regularization is essential with many recorded neurons.

## Controls and interpretation

1. Balanced chance accuracy: 50%.
2. Linear classifier on the complete two-channel input history: an information-available baseline. It should solve these constructed tasks, so high reservoir accuracy alone cannot establish a computational advantage.
3. Linear classifier on time-integrated left/right input: solves Side, but deliberately discards the order needed for Order. Fluctuations around 50% on Order are finite-sample nuisance-amplitude correlations, not evidence that the totals encode order.
4. Global **postsynaptic target-label permutation**, one independent permutation per replicate. This preserves each source neuron's outgoing edge count, outgoing weights/signs, total edge count, the distribution of incoming degree and the distribution of signed/absolute row sums. It reassigns incoming rows to different neurons, so it does **not** preserve each named neuron's incoming degree, anatomy, type mixing, reciprocal motifs or stimulus-to-output alignment. It is a coarse disruption control, not a definitive test that biological topology beats a matched random network.
5. No connections: same point neurons, tonic current and noise, zero recurrent weights; stimulus and output populations remain disjoint. This checks direct leakage and decoder chance fluctuations.
6. One independently shuffled training/validation-label fit per replicate on true-network activities; test labels remain unchanged. This is a sanity control, not a formal permutation significance test.

Compare only matched tasks, trial counts, parameters and readout rules. Display each replicate, mean and sample SD; report per-replicate Wilson 95% binomial intervals, conditional on that fitted classifier. SD across three stochastic replicates is **not** a population confidence interval. Report paired connectome-minus-control differences descriptively, without claiming significance or generalization from three network nulls.

## Planned outputs and checks

Store data/source hashes, exact dependencies, selected alpha, trial-level seeds/splits/amplitudes, predictions, population traces, wall time and activity/saturation summaries. Assert weights are unchanged by simulation and fitting. Save larger feature matrices and trained readouts locally under ignored `artifacts/`; small results and plots can go to GitHub. Verify reset reproducibility in `first_run.py`.

CPU first. Consider a separate GPU benchmark only if CPU wall time makes larger experiments impractical; do not infer GPU speed or CPU/GPU numerical equivalence without measurement.

## Sources

* [FlyBrain implementation and documented limitations](https://github.com/alextitonis/fly.ai), specifically the **installed 0.1.0 code** for API behavior.
* [MaleCNS official download and attribution](https://male-cns.janelia.org/download/): MaleCNS v1.0, FlyEM/HHMI Janelia and collaborators; data licensed CC-BY. The simulator's NPZ files are a derivative signed/normalized representation, not a separately validated complete physiological model.
