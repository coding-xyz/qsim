"""Circuit-to-executable compile pipeline orchestration."""

from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
from typing import Protocol
import json

from qsim.circuit.normalize import normalize_circuit
from qsim.common.schemas import BackendConfig, CircuitIR


class ICircuitPass(Protocol):
    """Protocol for circuit transformation pass in compile pipeline."""

    def run(self, circuit: CircuitIR, ctx: dict) -> CircuitIR:
        ...


class NormalizePass:
    """Default pass that normalizes a circuit for later lowering."""

    def run(self, circuit: CircuitIR, ctx: dict) -> CircuitIR:
        return normalize_circuit(circuit)


class CompilePipeline:
    """Execute a list of circuit passes and emit compile report."""

    def __init__(self, passes: list[ICircuitPass] | None = None):
        self.passes = passes or [NormalizePass()]

    def run(self, circuit: CircuitIR, config: BackendConfig, hardware: dict | None = None) -> tuple[CircuitIR, dict]:
        """Run all passes and return normalized circuit plus report.

        Example:
            ```python
            from qsim.backend.compile_pipeline import CompilePipeline

            normalized, report = CompilePipeline().run(circuit, cfg, hardware={})
            print(report["final_gate_count"])
            ```
        """
        report = {
            "schema_version": "1.0",
            "initial_gate_count": len(circuit.gates),
            "passes": [],
            "hardware_used": bool(hardware),
        }
        current = circuit
        ctx = {"config": config, "hardware": hardware or {}}
        for p in self.passes:
            before = len(current.gates)
            current = p.run(current, ctx)
            after = len(current.gates)
            report["passes"].append({"name": p.__class__.__name__, "before": before, "after": after})
        report["final_gate_count"] = len(current.gates)
        return current, report

    @staticmethod
    def dump_compile_report(report: dict, out_path: str | Path) -> Path:
        """Persist compile report as JSON."""
        out = Path(out_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        return out
