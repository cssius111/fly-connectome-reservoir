# M3.1: why the model escapes early (read-only research)

Status: **research note, 2026-10-22.** No runtime code, configuration, record or frozen system
changed. On 2026-10-22 the user chose the escape decision (M3.0 group 1) as the first fidelity
gap. They asked for read-only research first:
- find out why the model escapes so early;
- find changes that are consistent with the connectome.

Any runtime change needs its own preregistration and the user's explicit authorization to change
the encoder and the decoder records.

Model: `main` @ `032e7cc` (ROOM `config_version` 27). Tool: `tools/m3_1_escape_trace.py`. Raw
data: `artifacts/m3_1/` (git-ignored). The comparators are in `game/M3_0_ESCAPE_EVIDENCE.md`.

## 1. Summary

- **The model's rule.** It escapes when the expansion rate reaches about 40°/s, after a pipeline
  delay of 3-5 ticks. The real fly escapes when the angular size reaches about 54° (X15, X16).
- **Why.** The encoder drives LPLC2 with expansion velocity only (`loom_size` = 0). It drives
  LC4 with the product of size and velocity. The literature assigns the features the other way:
  - LPLC2 provides the giant fiber's angular-size component;
  - LC4 provides its angular-velocity component;
  - the giant fiber sums the two.
- **No gain value fixes it.** At a fixed angular size the expansion rate scales as
  1/(l/v). No threshold on velocity, or on size times velocity, can give a size threshold that
  holds across l/v. The model needs a size term.
- **The connectome is not the cause.** In MaleCNS, LC4 and LPLC2 are the two largest
  excitatory inputs to DNp01, both from the same side only, as the EM literature reports.
  The cause is the hand-set visual front end that drives them.
- **Candidate fix.** C1 (section 6): LPLC2 is driven by angular size during expansion, and LC4
  linearly by angular velocity. MaleCNS, DNp01 and the decoder rules stay unchanged.

## 2. Literature: what LC4 and LPLC2 carry

| Row | Claim | Source | Quote |
|---|---|---|---|
| Y1 | LPLC2 provides the whole size component of the giant fiber's looming response; LC4 provides the velocity component. A sum of a linear function of velocity and a Gaussian function of size replicates the response | Ache et al. 2019, *Curr Biol* 29:1073, doi:10.1016/j.cub.2019.01.079, abstract | "LPLC2 ... provide the entire GF size component"; "A model summing a linear function of angular velocity (provided by LC4) and a Gaussian function of angular size (provided by LPLC2) replicates GF looming response dynamics and predicts the peak response time" |
| Y2 | LPLC2 and LC4 synapse directly onto the giant fiber. Silencing LPLC2 leaves only the velocity component | Ache et al. 2019, abstract | "LPLC2 and LC4 synapse directly onto the GF"; "LPLC2 silencing eliminates the size component of the GF looming response in patch-clamp recordings, leaving only the velocity component" |
| Y3 | LC4 encodes angular expansion velocity, other inputs encode size, and the giant fiber integrates both linearly | von Reyn et al. 2017, *Neuron* 94:1190, doi:10.1016/j.neuron.2017.05.036, abstract | "it encodes angular expansion velocity, whereas other input cell type(s) encode angular size. Motor program selection and timing emerge from linear integration of these two features within the GF" |
| Y4 | The velocity contribution grows as r/v falls; the size contribution stays constant | Jang et al. 2023, *J Exp Biol* 226:jeb244790, doi:10.1242/jeb.244790 (PMC10263144) | "LC4's angular velocity contribution to the GF response increases as r/v decreases (while LPLC2's angular size contribution remains constant; von Reyn et al., 2017)" |
| Y5 | LPLC2 is selective for looming: no response to receding looms, motion-free darkening or wide-field motion | Klapoetke et al. 2017, *Nature* 551:237, doi:10.1038/nature24626 (PMC7457385) | "LPLC2 neurons did not respond to dark receding looming or to luminance-matched motion-free darkening stimulus"; "60° as the upper bound for an individual LPLC2's receptive field size" |
| Y6 | Behaviour follows an angular-size threshold that does not change with r/v | von Reyn et al. 2014, *Nat Neurosci* 17:962, doi:10.1038/nn.3741 | "behavior is initiated at a fixed neural delay after a looming stimulus crosses an angular size threshold"; "an invariant angular threshold across r/v" |

The parameter values of the Y1 model (the Gaussian's centre and width, and the two weights) are
in the full text of Ache et al. 2019. No open copy was found: neither PMC nor Europe PMC holds
one, and no preprint was found.

## 3. The model as built

**Encoder** (`game/perception.py`, `flybrain.FeatureDetectors`, ROOM `encoder` block):
- **LPLC2.** The voltage is `min(0.8, 20 * dtheta per tick)`, which is `0.4 * theta_dot` in rad/s.
  `loom_size` is 0, so angular size adds nothing.
- **LC4.** The voltage is `0.8 * min(1, theta / 0.5 rad) * min(1, theta_dot / 2 rad/s)`.
- **Drive pattern.** Every driven cell of the stimulated side gets the same voltage each tick:
  91 LPLC2 and 55 LC4 cells per side.
- **Azimuth.** Only the sign of the Retina azimuth is used, as the side. The Retina itself
  carries the full bearing (`azimuth` = bearing / π).

**Connectome** (MaleCNS weights, per-neuron input normalization, `data/weights.npz`):
- **Inputs to DNp01.** For left DNp01, the left LC4 cells give 0.183 of its absolute input
  weight (28 % of its excitatory input). The left LPLC2 cells give 0.128 (20 %).
- **Other inputs.** The next-largest excitatory input is DNp70, at 5.5 %.
- **Connectivity.** Every LC4 and LPLC2 cell of the same side connects to DNp01, and none of
  the opposite side does. The right side is similar (LC4 0.161, LPLC2 0.138).
- **Agreement with the literature.** This matches Y2. The connectome already has the circuit
  that Y1 and Y3 describe.

**Neuron model and decoder:**
- **Neuron model.** Leaky integrate-and-fire with 20 ms steps. A silent cell rests at 0.772 and
  spikes at 1.0, then resets to 0 (`game/M1_8_N4_SENSORY_DESCENDING_DIAGNOSIS.md`).
- **Decoder.** N4B1C escapes on any of three paths:
  - LATERAL: two same-side DNp01 spikes within 60 ms;
  - FAST: a summed DNp01 trace of 2.1;
  - SUSTAINED: 3 of 5 samples at 1.45.

## 4. Diagnosis

All runs use protocol E of M3.0 at the right azimuth, with the first 12 brain-noise seeds
(500001-500012). The runtime variant reproduces the M3.0 escape tick in all 48 trials.

### 4.1 The decision starts at expansion onset

l/v 40 ms, medians over the seeds. Tick 1 is the first expanding Retina:

| Tick | Size | Expansion rate | LPLC2 voltage | LC4 voltage | LPLC2 cells spiking (of 91) | DNp01 spike share |
|---|---|---|---|---|---|---|
| 0 | 10.0° | 0°/s | 0 | 0 | 1 | 0.08 |
| 1 | 10.5° | 23°/s | 0.159 | 0.058 | 34 | 0.00 |
| 2 | 11.0° | 25°/s | 0.174 | 0.066 | 52 | 0.08 |
| 3 | 11.5° | 27°/s | 0.191 | 0.077 | 6 | 0.75 |
| 6 | 13.5° | 38°/s | 0.262 | 0.124 | 22 | 0.75 |

- **First tick.** Over a third of the LPLC2 population fires at the first expanding tick, at
  only 23°/s.
- **Then.** DNp01 fires two ticks later. The decoder's LATERAL path fires at tick 6, on the
  second DNp01 spike within 60 ms.
- **Paths.** LATERAL fired in 46 of 48 trials, 5 of them together with FAST. FAST alone fired
  in the other 2 trials, both at l/v 80 ms.

### 4.2 Which input channel decides

The tool removes one channel's injection. This variant exists only inside the tool.

| l/v | Runtime | Without LC4 | Without LPLC2 |
|---|---|---|---|
| 10 ms | 32.5° | 32.5° | 69.9° |
| 20 ms | 15.3° | 17.7° | 44.7° |
| 40 ms | 13.5° | 28.6° | 35.1° |
| 80 ms | 21.9° | 36.3° | 30.4° |

These are median sizes at escape; all 12 of 12 trials escape in every cell.

- **LPLC2 decides the early escape.** Without it, the model escapes later at every l/v.
- **LC4 alone does not give a fixed threshold.** Its size at escape falls from 70° to 30° as
  l/v grows. That is the signature of a size-times-velocity product, not of a size threshold.

### 4.3 The size at escape follows the start size

Runtime encoder, with the disk's start size varied:

| l/v | Start 5° | Start 10° | Start 20° | Start 30° |
|---|---|---|---|---|
| 40 ms | 14.9° | 13.5° | 30.5° | 48.3° |
| 80 ms | 18.2° | 21.9° | 25.5° | 37.1° |

- **Larger starts.** When the start size is large, the expansion rate at onset is already above
  the model's rate threshold. The fly then escapes 3-5 ticks after the disk starts to move,
  whatever its size.
- **Real fly.** A size threshold would give about the same size at escape for every start size
  below the threshold.

### 4.4 The frozen chain below the encoder

The tool bypasses the encoder and adds a constant voltage every tick to all 91 right-side LPLC2
cells (or all 55 LC4 cells) for 1 s.

| Voltage per tick | 0.02-0.16 | 0.20 | 0.24 | 0.28 | 0.32 | 0.40 | 0.60 | 0.80 |
|---|---|---|---|---|---|---|---|---|
| LPLC2: escaped of 12 | 0-2 | 8 | 5 | 9 | 12 | 12 | 12 | 12 |
| LC4: escaped of 12 | 0-2 | 4 | 4 | 10 | 10 | 12 | 12 | 12 |

- **Weak drive.** Every cell gets the same voltage, so the population fires in synchronous
  volleys, and weak drive spaces the volleys too far apart. DNp01 then fires once per volley,
  which rarely meets the decoder's two-spikes-in-60-ms rule.
- **Reliable escape.** The chain escapes reliably from about 0.3 V per tick on one channel. A
  rising looming drive does it from about 0.26 V (section 4.1).
- **The decoder's role.** The decoder therefore sets the voltage level at which the fly escapes.
  It cannot add a size dependence that its input lacks.

### 4.5 The model's effective rule

From all 96 lateral trials per l/v of M3.0:

| l/v | Expansion rate at escape (median) | LPLC2 voltage then | Expansion rate a real fly sees at 54° |
|---|---|---|---|
| 10 ms | 582°/s | 0.80 (cap) | 2362°/s |
| 20 ms | 90°/s | 0.63 | 1181°/s |
| 40 ms | 38°/s | 0.26 | 590°/s |
| 80 ms | 41°/s | 0.29 | 295°/s |

- **Slow looms (l/v 40 and 80 ms).** The model escapes once `0.4 * theta_dot` reaches about
  0.26-0.29 V, that is, at about 40°/s.
- **Fast looms (l/v 10 and 20 ms).** The drive passes that level at onset. Only the pipeline
  delay of 3-4 ticks sets the escape time.

**Why no gain value can work.** For a constant-l/v loom, `theta = 2 atan((l/v) / T)` gives
`theta_dot = 2 sin^2(theta / 2) / (l/v)`. At a fixed size, the expansion rate is inversely
proportional to l/v.
- At 54° it is 295°/s for l/v 80 ms and 2362°/s for l/v 10 ms, a factor of 8.
- A threshold on velocity, or on size times velocity, therefore puts the escape at a size that
  changes with l/v.
- Retuning `loom_gain` or `threat_max` would move the threshold, but it would still change with
  l/v. Only a term in angular size can give the invariant threshold of Y6, X15 and X16.

## 5. Changes that are ruled out

- **Retune `loom_gain`, the LC4 references or the decoder thresholds.**
  - These scale a velocity rule. Section 4.5 shows that no value gives a size threshold.
  - It would also be tuning to a target, which the project does not do.
- **Set `loom_size` > 0** (the existing upstream term, `theta * loom_size` added to LPLC2).
  - It would drive LPLC2 with a static or receding object, which real LPLC2 ignores (Y5).
  - A hovering paddle would then cause escapes.
- **Change the connectome or DNp01.** The connectome already integrates LC4 and LPLC2 as the
  literature describes (section 3).

## 6. Candidate changes

### C1. Feature roles after Ache et al. 2019 (recommended first)

- **LC4, the velocity channel.**
  - Rule: voltage = `min(cap, g_v * theta_dot)` for `theta_dot` > 0, and 0 otherwise.
  - Source: the linear velocity term of Y1 and Y3.
- **LPLC2, the size channel.**
  - Rule: voltage = `g_s * exp(-(theta - mu)^2 / (2 sigma^2))` while the disk expands
    (`theta_dot` > 0), and 0 otherwise.
  - Sources: the Gaussian size term of Y1, and the looming selectivity of Y5.
- **What stays unchanged:**
  - the Retina, the MaleCNS weights and DNp01;
  - the side rule;
  - the decoder's rules and constants.
- **Gating.** The change sits behind a new encoder mode, set only in ROOM. Configurations without
  it keep the current encoder bit for bit, as earlier gated stages did.
- **Free parameters.** `g_v`, `g_s`, `mu` and `sigma`. Two ways to fix them, in order of
  preference:
  1. **From Ache et al. 2019's fitted model**, which needs its full text. With these values the
     scorecard's E2 stays an independent test: the encoder comes from electrophysiology and the
     threshold is measured on behaviour.
  2. **Fitted to the timing law** X15/X16 on a calibration set of l/v values, then tested on
     held-out l/v values. E2 then becomes a calibrated metric, not evidence. The independent
     checks would be:
     - the held-out l/v values;
     - start-size invariance (section 4.3);
     - no escapes for static and receding disks;
     - the escape probability (E1);
     - the unchanged spontaneous escape rate.
- **Records to rebuild.**
  - The N4B1C decoder is unchanged, but its transfer record is bound to the ROOM configuration
    and must be rebuilt for the new configuration.
  - The M1.8-N4 and N4B6 escape checks need re-running, because the input statistics change.

### C2. Retinotopic drive (later, larger)

- **Idea.** Give each LPLC2 and LC4 cell a receptive field. Drive it by how much of that field
  the disk covers: real LPLC2 fields are at most 60° (Y5).
- **What it would give.** More cells are recruited as the disk grows, so size dependence
  emerges from the population. The drive is no longer the synchronous volley of section 4.4.
- **Front and back.** The encoder could use the full azimuth that the Retina already carries.
  This would also address the front-and-back gap of M3.0 (E4).
- **Blocker.** The data build keeps only soma positions for these cells, which say nothing
  about their receptive fields. C2 needs the optic-lobe column data of MaleCNS, a new data step.

### C3. Decoder changes (not recommended)

- **What it is.** The single-spike giant-fiber takeoff of the short mode (X26) would argue for
  a one-spike trigger.
- **Why not.** Section 4.4 shows the decoder only sets the voltage level at which the fly
  escapes. Without C1 or C2, no decoder change creates a size threshold.

## 7. Consequences to weigh before a preregistration

- **Game difficulty.** At the same approach, C1 makes the fly escape later. For a swat with
  l/v = 20 ms the escape would move from 143 ms before contact (M3.0) to about 34 ms
  (X16: 2.0 × 20 ms − 6 ms), so the fly becomes easier to hit.
  - In a real fly that late escape works because takeoff and flight are fast.
  - In ROOM, flight is about 14 times slower in body lengths per second (M3.0, C1). That is
    the frozen kinematic scale (`AGENTS.md`).
  - The user set realism as the goal, with difficulty as a consequence. They should decide
    knowing this.
- **What stays inside the constraints.**
  - The escape still runs from the Retina through LC4/LPLC2, MaleCNS and the DN readout, as
    `AGENTS.md` requires.
  - No learning is involved.
  - No frozen M1.7.x or M1.8 mechanism changes.
- **What needs authorization.**
  - The accepted encoder (config v27) changes.
  - The decoder's transfer record must be rebuilt.
  - The user asked to be asked before either.

## 8. Reproduction

```
python tools/m3_1_escape_trace.py run      # about 5 minutes on 4 threads
python tools/m3_1_escape_trace.py report
```

The connectome figures in section 3 come from `data/weights.npz`. The weights are signed synapse
counts, each divided by the postsynaptic neuron's total absolute input.
