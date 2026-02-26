from __future__ import annotations

from typing import Any
import hashlib
import math

from qsim.engines.qec_base import QECAnalysisEngine


class CirqQECAnalysisEngine(QECAnalysisEngine):
    """Cirq-backed Pauli+ analysis engine.

    Native path:
    - Builds a small noisy circuit (Hadamard + CZ + depolarizing noise).
    - Uses ``cirq.DensityMatrixSimulator`` sampling.
    - Estimates ``epsilon_d`` from odd-parity logical proxy events.

    Fallback path:
    - Uses a deterministic heuristic when ``cirq`` is unavailable or runtime
      execution fails.
    """

    name = "cirq_qec"

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
            import cirq  # type: ignore
            import numpy as np

            backend = "cirq"
            quality = "native"
            comp = model_spec.get("component_errors", {}) if isinstance(model_spec, dict) else {}
            scale = float(opts.get("error_scale", 1.0))
            total = max(0.0, sum(float(v) for v in comp.values()) * max(0.0, scale))
            p = min(0.25, max(1e-6, total))
            d = max(3, int(code_distance))
            rounds = max(3, int(opts.get("rounds", d)))

            qubits = cirq.LineQubit.range(d)
            circuit = cirq.Circuit()
            for _ in range(rounds):
                for q in qubits:
                    circuit.append(cirq.H(q))
                    circuit.append(cirq.depolarize(p).on(q))
                for i in range(d - 1):
                    circuit.append(cirq.CZ(qubits[i], qubits[i + 1]))
                    circuit.append(cirq.depolarize(min(0.25, 0.8 * p)).on(qubits[i]))
                    circuit.append(cirq.depolarize(min(0.25, 0.8 * p)).on(qubits[i + 1]))
            circuit.append(cirq.measure(*qubits, key="m"))

            sim = cirq.DensityMatrixSimulator(seed=int(seed))
            result = sim.run(circuit, repetitions=int(max(1, shots)))
            ms = result.measurements["m"]
            # Simple logical proxy: odd measurement parity is a logical failure.
            logical_fail = np.mod(np.sum(ms, axis=1), 2)
            eps = float(np.mean(logical_fail))
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
                    "num_qubits": int(d),
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
