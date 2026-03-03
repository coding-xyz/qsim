"""Stim-backed QEC analysis engine adapters."""

from __future__ import annotations

from typing import Any
import hashlib
import math

from qsim.engines.qec_base import QECAnalysisEngine


class StimQECAnalysisEngine(QECAnalysisEngine):
    """Stim-backed Pauli+ analysis engine.

    Native path:
    - Generates a noisy repetition-code memory circuit via ``stim.Circuit.generated``.
    - Samples detector/observable outcomes and estimates ``epsilon_d`` from
      observable flips.

    Fallback path:
    - Uses a deterministic heuristic when ``stim`` is unavailable or runtime
      execution fails.
    """

    name = "stim_qec"

    def run_pauli_plus(
        self,
        model_spec: dict[str, Any],
        *,
        code_distance: int,
        shots: int,
        seed: int,
        options: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        opts = options or {}
        try:
            import numpy as np
            import stim  # type: ignore

            backend = "stim"
            quality = "native"
            comp = model_spec.get("component_errors", {}) if isinstance(model_spec, dict) else {}
            scale = float(opts.get("error_scale", 1.0))
            total = max(0.0, sum(float(v) for v in comp.values()) * max(0.0, scale))
            # Map component error scale to a bounded physical noise probability.
            p = min(0.25, max(1e-6, total))
            d = max(3, int(code_distance))
            rounds = max(3, int(opts.get("rounds", d)))
            # Real Stim invocation: generated noisy memory repetition code circuit.
            circuit = stim.Circuit.generated(
                "repetition_code:memory",
                distance=d,
                rounds=rounds,
                after_clifford_depolarization=p,
                before_round_data_depolarization=min(0.25, 0.5 * p),
                before_measure_flip_probability=min(0.25, 0.8 * p),
                after_reset_flip_probability=min(0.25, 0.5 * p),
            )
            # Use detector sampler and read observable flips as logical failures.
            sampler = circuit.compile_detector_sampler(seed=int(seed))
            _det, obs = sampler.sample(int(max(1, shots)), separate_observables=True)
            eps = float(np.mean(np.any(obs, axis=1))) if getattr(obs, "size", 0) else float(min(0.49, p))
            rev = hashlib.sha256(f"{self.name}:{backend}:{d}:{rounds}:{seed}:{shots}".encode("utf-8")).hexdigest()[:12]
            return {
                "schema_version": "1.0",
                "engine": self.name,
                "engine_rev": rev,
                "backend": backend,
                "quality": quality,
                "code_distance": d,
                "shots": int(max(1, shots)),
                "epsilon_d": float(min(0.49, max(0.0, eps))),
                "metadata": {
                    "options": opts,
                    "physical_error_p": float(p),
                    "rounds": int(rounds),
                    "num_detectors": int(circuit.num_detectors),
                    "num_observables": int(circuit.num_observables),
                },
            }
        except Exception as exc:  # pragma: no cover - depends on local env
            backend = "fallback"
            quality = "heuristic"
            opts = dict(opts)
            opts["fallback_reason"] = str(exc)
        comp = model_spec.get("component_errors", {}) if isinstance(model_spec, dict) else {}
        scale = float(opts.get("error_scale", 1.0))
        total = sum(float(v) for v in comp.values()) * max(0.0, scale)
        d = max(3, int(code_distance))
        eps = min(0.49, max(1e-7, total / max(1.0, math.sqrt(d))))
        rev = hashlib.sha256(f"{self.name}:{backend}:{d}:{seed}:{shots}".encode("utf-8")).hexdigest()[:12]
        return {
            "schema_version": "1.0",
            "engine": self.name,
            "engine_rev": rev,
            "backend": backend,
            "quality": quality,
            "code_distance": d,
            "shots": int(max(1, shots)),
            "epsilon_d": float(eps),
            "metadata": {"options": opts},
        }
