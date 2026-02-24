from __future__ import annotations

from dataclasses import dataclass
import math


class PulseShape:
    """Base interface for pulse envelope shapes."""

    def sample(self, t: float, t0: float, t1: float, amp: float) -> float:
        raise NotImplementedError


@dataclass
class RectShape(PulseShape):
    """Piecewise-constant pulse with optional linear rise/fall edges."""

    rise: float = 0.0
    fall: float = 0.0

    def sample(self, t: float, t0: float, t1: float, amp: float) -> float:
        if t < t0 or t > t1:
            return 0.0
        width = max(t1 - t0, 1e-12)
        tr = min(self.rise, width / 2)
        tf = min(self.fall, width / 2)
        if tr > 0 and t < t0 + tr:
            return amp * (t - t0) / tr
        if tf > 0 and t > t1 - tf:
            return amp * (t1 - t) / tf
        return amp


@dataclass
class GaussianShape(PulseShape):
    """Truncated Gaussian envelope normalized to pulse amplitude."""

    sigma: float | None = None

    def sample(self, t: float, t0: float, t1: float, amp: float) -> float:
        if t < t0 or t > t1:
            return 0.0
        dur = max(t1 - t0, 1e-12)
        sigma = self.sigma if self.sigma else dur / 6.0
        mu = 0.5 * (t0 + t1)
        g = math.exp(-0.5 * ((t - mu) / sigma) ** 2)
        edge = math.exp(-0.5 * ((t0 - mu) / sigma) ** 2)
        return amp * max(0.0, (g - edge) / max(1e-12, 1.0 - edge))


@dataclass
class DragShape(PulseShape):
    """DRAG-like envelope using Gaussian plus derivative component."""

    beta: float = 0.3
    sigma: float | None = None

    def sample(self, t: float, t0: float, t1: float, amp: float) -> float:
        if t < t0 or t > t1:
            return 0.0
        dur = max(t1 - t0, 1e-12)
        sigma = self.sigma if self.sigma else dur / 6.0
        mu = 0.5 * (t0 + t1)
        x = (t - mu) / sigma
        g = math.exp(-0.5 * x * x)
        dg = -x * g / sigma
        edge = math.exp(-0.5 * ((t0 - mu) / sigma) ** 2)
        g_norm = max(0.0, (g - edge) / max(1e-12, 1.0 - edge))
        return amp * (g_norm + self.beta * dg)


@dataclass
class ReadoutShape(PulseShape):
    """Readout envelope, currently identical to rectangular pulse."""

    rise: float = 0.0
    fall: float = 0.0

    def sample(self, t: float, t0: float, t1: float, amp: float) -> float:
        return RectShape(rise=self.rise, fall=self.fall).sample(t, t0, t1, amp)


def make_shape(name: str, params: dict) -> PulseShape:
    """Factory returning pulse-shape implementation by shape name."""
    lname = name.lower()
    rise = float(params.get("rise_ns", params.get("rise", 0.0)))
    fall = float(params.get("fall_ns", params.get("fall", 0.0)))
    if lname in ("rect", "dc"):
        return RectShape(rise=rise, fall=fall)
    if lname == "gaussian":
        sigma = params.get("sigma")
        return GaussianShape(sigma=float(sigma) if sigma is not None else None)
    if lname == "drag":
        sigma = params.get("sigma")
        return DragShape(beta=float(params.get("beta", 0.3)), sigma=float(sigma) if sigma is not None else None)
    if lname == "readout":
        return ReadoutShape(rise=rise, fall=fall)
    raise ValueError(f"Unsupported shape: {name}")
