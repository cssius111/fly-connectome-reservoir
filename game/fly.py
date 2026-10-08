"""The digital fly: MaleCNS connectome + descending-neuron trace + policy.

`FlyLoop.step` accepts a `Retina` plus optional body-frame `MotionState`.
Only Retina drives the brain; internal motion is appended to policy input.
It rejects any other type,
including subclasses of `Retina`, so a caller cannot smuggle mouse or world
state past the perceptual bottleneck by wrapping it in a lookalike.

The runtime graph is frozen after loading: no plasticity or training. With
sensory_input=False, incoming sensory-neuron edges are removed from the
MaleCNS-derived graph (currently 25,088,107 rather than 25,582,938 edges).
Milestone 1 reads DNp01 (looming escape)
and DNa02 (steering) out of `brain.groups` and hands them to an untrained
threshold policy. The full descending-neuron trace is carried along in
`MotorState` so a Milestone-2 trained policy needs no change here.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
from flybrain import FlyBrain, Trace

from .action import Action, MotorState, MotionState, Policy
from .perception import Retina, RetinalEncoder

ROOT = Path(__file__).resolve().parent.parent

# brain.groups entries this milestone reads.
ESCAPE_GROUPS = ("escape_L", "escape_R")     # DNp01
STEER_GROUPS = ("steer_L", "steer_R")        # DNa02


def build_brain(config: dict, root: Path = ROOT, warmup: bool = True) -> FlyBrain:
    """Construct the frozen connectome simulator from game_config.json."""
    b = config["brain"]
    brain = FlyBrain(data=root / b["data"], device=b["device"], seed=int(b["seed"]),
                     dt=float(b["dt_seconds"]), sensory_input=bool(b["sensory_input"]),
                     refractory=float(b["refractory_seconds"]))
    for key in ("gain", "tonic", "noise_hz", "noise_amp"):
        setattr(brain, key, float(b[key]))
    if warmup:
        brain.step()      # pay the numba JIT cost before anything is timed
    return brain


class FlyLoop:
    """Retina in, motor Action out. Knows nothing about the mouse or the world."""

    def __init__(self, brain: FlyBrain, encoder: RetinalEncoder, policy: Policy, config: dict):
        self.brain = brain
        self.encoder = encoder
        self.policy = policy
        tau = float(config["brain"]["trace_tau_seconds"])

        for name in ESCAPE_GROUPS + STEER_GROUPS:
            if name not in brain.groups:
                raise RuntimeError(f"brain.groups is missing {name!r}; run `flybrain build`")
        readout = np.union1d(brain.cells(["descending_neuron"]),
                             np.concatenate([brain.groups[n] for n in ESCAPE_GROUPS + STEER_GROUPS]))
        self.trace = Trace(brain, idx=readout, tau=tau)
        self._escape_slots = [self.trace.slot[brain.groups[n]] for n in ESCAPE_GROUPS]
        self._steer_slots = [self.trace.slot[brain.groups[n]] for n in STEER_GROUPS]
        assert all((s >= 0).all() for s in self._escape_slots + self._steer_slots)
        self.last_motor: MotorState | None = None
        self.last_action: Action = Action()

    def reset(self, seed: int) -> None:
        self.brain.reset(seed)
        self.trace.reset()
        self.policy.reset()
        self.last_motor = None
        self.last_action = Action()
        self.last_sensory_spikes = {k:0 for k in ("LC4_left","LC4_right","LPLC2_left","LPLC2_right")}

    def step(self, retina: Retina, motion: MotionState = MotionState()) -> Action:
        # Strict type check, not isinstance: a Retina subclass carrying extra
        # fields would defeat the whole point of the bottleneck.
        if type(retina) is not Retina:
            raise TypeError(
                f"FlyLoop.step accepts only a perception.Retina, got {type(retina).__name__}. "
                "Raw world or mouse state must never reach the brain.")
        if type(motion) is not MotionState:
            raise TypeError("FlyLoop motion feedback accepts only MotionState; no world or mouse state")
        inject = self.encoder.inject(retina)
        fired = self.brain.step(inject=inject)
        self.last_sensory_spikes = self.encoder.sensory_spikes(fired)
        features = self.trace.observe(fired)
        motor = MotorState(
            dnp01_left=float(features[self._escape_slots[0]].sum()),
            dnp01_right=float(features[self._escape_slots[1]].sum()),
            dna02_left=float(features[self._steer_slots[0]].sum()),
            dna02_right=float(features[self._steer_slots[1]].sum()),
            trace=features, motion=motion)
        action = self.policy.decide(motor)
        self.last_motor = motor
        self.last_action = action
        return action
