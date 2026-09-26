"""M2.3 official learner: PyTorch implementation of the frozen M2.0 policy architecture.

Training-side code. The architecture is unchanged from `MLPPolicyModel`:

    TorchPolicy   observation (60) * fixed input scale -> Linear(60, 32) -> tanh -> Linear(32, 11)
                  11 maneuver logits; 2,315 trainable parameters. The input scale is a
                  non-trainable buffer with the documented constants of MLPPolicyModel.
    TorchCritic   separate value network, 60 -> 32 tanh -> 1 (1,985 trainable parameters),
                  same fixed input scale. Training only; never part of a policy.

All gradients come from torch autograd (behaviour cloning: torch cross-entropy; PPO: clipped
surrogate on torch.distributions.Categorical log-probabilities, torch entropy, torch KL to a
frozen reference policy, torch value loss). Optimizer: torch.optim.Adam. Gradient clipping:
torch.nn.utils.clip_grad_norm_. Checkpoints: torch state_dict files.

Rollout inference: the CPU rollout workers keep the existing numpy `MLPPolicyModel` forward
(per-tick, 50 Hz, one observation at a time). `to_numpy_model` copies the float32 torch
parameters into it as float64; the tests check that both forwards agree.
"""
from __future__ import annotations

import hashlib
import os

import numpy as np
import torch
from torch import nn
from torch.distributions import Categorical, kl_divergence
import torch.nn.functional as F

from .contracts import N_MANEUVERS, OBSERVATION_SIZE
from .model import MLPPolicyModel

ARCH = 'torch-mlp-60-32-11-tanh-categorical'
CRITIC_ARCH = 'torch-mlp-60-32-1-tanh-value'


def set_determinism(seed: int):
    """Seed torch / numpy and request deterministic CUDA kernels."""
    os.environ.setdefault('CUBLAS_WORKSPACE_CONFIG', ':4096:8')
    torch.manual_seed(seed)
    torch.use_deterministic_algorithms(True, warn_only=True)
    torch.backends.cudnn.benchmark = False


def default_device():
    return torch.device('cuda' if torch.cuda.is_available() else 'cpu')


def _input_scale():
    return torch.tensor(MLPPolicyModel(seed=0).input_scale, dtype=torch.float32)


class TorchPolicy(nn.Module):
    arch = ARCH

    def __init__(self, hidden: int = 32):
        super().__init__()
        self.fc1 = nn.Linear(OBSERVATION_SIZE, hidden)
        self.fc2 = nn.Linear(hidden, N_MANEUVERS)
        self.register_buffer('input_scale', _input_scale())

    def forward(self, obs: torch.Tensor) -> torch.Tensor:
        if obs.dim() != 2 or obs.shape[1] != OBSERVATION_SIZE:
            raise ValueError('TorchPolicy accepts only (N, 60) observation batches')
        return self.fc2(torch.tanh(self.fc1(obs * self.input_scale)))

    def distribution(self, obs: torch.Tensor) -> Categorical:
        return Categorical(logits=self(obs))

    @property
    def n_parameters(self) -> int:
        return int(sum(p.numel() for p in self.parameters() if p.requires_grad))

    # ---- numpy interoperability (rollout workers, game loader) ---
    @classmethod
    def from_numpy_model(cls, m: MLPPolicyModel) -> 'TorchPolicy':
        net = cls(hidden=m.params['W1'].shape[0])
        with torch.no_grad():
            net.fc1.weight.copy_(torch.as_tensor(m.params['W1']))
            net.fc1.bias.copy_(torch.as_tensor(m.params['b1']))
            net.fc2.weight.copy_(torch.as_tensor(m.params['W2']))
            net.fc2.bias.copy_(torch.as_tensor(m.params['b2']))
        if not np.allclose(net.input_scale.numpy(), m.input_scale):
            raise ValueError('input scale mismatch')
        return net

    def numpy_params(self) -> dict:
        sd = {k: v.detach().cpu().double().numpy() for k, v in self.state_dict().items()}
        return {'W1': sd['fc1.weight'], 'b1': sd['fc1.bias'], 'W2': sd['fc2.weight'], 'b2': sd['fc2.bias']}

    def to_numpy_model(self) -> MLPPolicyModel:
        m = MLPPolicyModel(seed=0)
        for k, v in self.numpy_params().items():
            if v.shape != m.params[k].shape:
                raise ValueError('shape mismatch for %s' % k)
            m.params[k] = np.array(v, dtype=np.float64)
        return m


class TorchCritic(nn.Module):
    arch = CRITIC_ARCH

    def __init__(self, hidden: int = 32):
        super().__init__()
        self.fc1 = nn.Linear(OBSERVATION_SIZE, hidden)
        self.fc2 = nn.Linear(hidden, 1)
        self.register_buffer('input_scale', _input_scale())

    def forward(self, obs: torch.Tensor) -> torch.Tensor:
        return self.fc2(torch.tanh(self.fc1(obs * self.input_scale)))[:, 0]


def init_critic(seed: int) -> TorchCritic:
    """Value network initialisation (documented): W1 ~ N(0, 1/sqrt(60)), W2 ~ N(0, 0.01), zero biases,
    drawn from a torch generator seeded with `seed` (the same scheme as the M2.2 numpy critic)."""
    g = torch.Generator().manual_seed(seed)
    c = TorchCritic()
    with torch.no_grad():
        c.fc1.weight.copy_(torch.randn(c.fc1.weight.shape, generator=g) / np.sqrt(OBSERVATION_SIZE))
        c.fc1.bias.zero_()
        c.fc2.weight.copy_(torch.randn(c.fc2.weight.shape, generator=g) * 0.01)
        c.fc2.bias.zero_()
    return c


# ----------------------------------------------------------------- losses (torch autograd) ---
def bc_loss(logits: torch.Tensor, labels: torch.Tensor, logit_offset: torch.Tensor | None = None) -> torch.Tensor:
    """Behaviour-cloning cross-entropy. logit_offset (11,) is added to the logits (NONE-subsampling
    prior correction during training; omitted on the natural distribution)."""
    if logit_offset is not None:
        logits = logits + logit_offset
    return F.cross_entropy(logits, labels)


def ppo_surrogate(logits, actions, logp_old, adv, clip):
    """Clipped PPO surrogate on torch Categorical log-probabilities. Returns (loss, stats tensors)."""
    dist = Categorical(logits=logits)
    logp = dist.log_prob(actions)
    ratio = torch.exp(logp - logp_old)
    surrogate = torch.min(ratio * adv, torch.clamp(ratio, 1 - clip, 1 + clip) * adv)
    entropy = dist.entropy()
    with torch.no_grad():
        approx_kl = (logp_old - logp).mean()
        clipfrac = ((ratio - 1).abs() > clip).float().mean()
    return -surrogate.mean(), {'entropy': entropy, 'approx_kl': approx_kl, 'clipfrac': clipfrac, 'ratio': ratio}


def kl_to_reference(logits, ref_logits):
    """Per-state KL(current || frozen reference) with torch distributions."""
    return kl_divergence(Categorical(logits=logits), Categorical(logits=ref_logits.detach()))


def value_loss(values, returns):
    return 0.5 * F.mse_loss(values, returns)


def gae(rewards, values, dones, last_value, gamma, lam):
    """Generalised advantage estimation over one episode segment (targets only; no gradients).
    dones[t] = 1 marks a terminal step (no bootstrap); last_value bootstraps after the final step."""
    T = len(rewards)
    adv = np.zeros(T)
    last = 0.0
    for t in range(T - 1, -1, -1):
        nxt = last_value if t == T - 1 else values[t + 1]
        nonterminal = 1.0 - dones[t]
        delta = rewards[t] + gamma * nxt * nonterminal - values[t]
        last = delta + gamma * lam * nonterminal * last
        adv[t] = last
    return adv, adv + values


# ----------------------------------------------------------------- checkpoints ---
def state_dict_sha256(module_or_sd) -> str:
    sd = module_or_sd.state_dict() if isinstance(module_or_sd, nn.Module) else module_or_sd
    h = hashlib.sha256()
    for k in sorted(sd):
        h.update(k.encode())
        h.update(np.ascontiguousarray(sd[k].detach().cpu().numpy()).tobytes())
    return h.hexdigest()


def save_checkpoint(path, module: nn.Module, meta: dict | None = None) -> str:
    """torch.save of {'arch', 'state_dict' (CPU tensors), 'meta'}; returns the state_dict sha256."""
    sd = {k: v.detach().cpu().clone() for k, v in module.state_dict().items()}
    torch.save({'arch': module.arch, 'state_dict': sd, 'meta': meta or {}}, path)
    return state_dict_sha256(sd)


def load_checkpoint(path, cls=TorchPolicy, expected_sha256=None, map_location='cpu'):
    blob = torch.load(path, map_location=map_location, weights_only=True)
    if blob['arch'] != cls.arch:
        raise ValueError('checkpoint architecture mismatch')
    m = cls()
    m.load_state_dict(blob['state_dict'])
    if expected_sha256 is not None and state_dict_sha256(m) != expected_sha256:
        raise ValueError('checkpoint hash mismatch')
    return m, blob['meta']
