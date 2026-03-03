"""OpenQASM 3 parsing and serialization helpers for CircuitIR."""

from __future__ import annotations

import ast
from dataclasses import asdict
import math
import re

from qsim.common.schemas import CircuitGate, CircuitIR


class CircuitAdapter:
    """Adapter between OpenQASM/Qiskit and ``CircuitIR``."""
    _HEADER_RE = re.compile(r"^OPENQASM\s+3(?:\.0)?\s*$", re.IGNORECASE)
    _DECL_QUBIT_RE = re.compile(r"^qubit\[(\d+)\]\s+([A-Za-z_]\w*)\s*$")
    _DECL_BIT_RE = re.compile(r"^bit\[(\d+)\]\s+([A-Za-z_]\w*)\s*$")
    _MEASURE_RE = re.compile(
        r"^measure\s+([A-Za-z_]\w*)\[(\d+)\]\s*->\s*([A-Za-z_]\w*)\[(\d+)\]\s*$",
        re.IGNORECASE,
    )
    _GATE_RE = re.compile(r"^([A-Za-z_]\w*)(?:\(([^)]*)\))?\s+(.+)\s*$", re.IGNORECASE)

    @staticmethod
    def _split_statements(qasm_text: str) -> list[str]:
        cleaned = []
        for idx, line in enumerate(qasm_text.splitlines()):
            if idx == 0:
                line = line.lstrip("\ufeff")
            line = line.split("//", 1)[0].strip()
            if line:
                cleaned.append(line)
        merged = " ".join(cleaned)
        return [s.strip() for s in merged.split(";") if s.strip()]

    @staticmethod
    def _parse_indexed_ref(token: str) -> tuple[str, int]:
        m = re.match(r"^([A-Za-z_]\w*)\[(\d+)\]$", token.strip())
        if not m:
            raise ValueError(f"Invalid indexed argument: {token}")
        return m.group(1), int(m.group(2))

    @staticmethod
    def _eval_param_expr(expr: str, bindings: dict[str, float] | None = None) -> float:
        """Evaluate a restricted numeric expression used in QASM gate parameters."""
        bindings = bindings or {}
        allowed_names = {"pi": math.pi, "tau": math.tau, "e": math.e}
        allowed_names.update({str(k): float(v) for k, v in bindings.items()})

        tree = ast.parse(expr, mode="eval")
        for node in ast.walk(tree):
            if isinstance(
                node,
                (
                    ast.Expression,
                    ast.BinOp,
                    ast.UnaryOp,
                    ast.Add,
                    ast.Sub,
                    ast.Mult,
                    ast.Div,
                    ast.Pow,
                    ast.USub,
                    ast.UAdd,
                    ast.Constant,
                    ast.Load,
                    ast.Name,
                ),
            ):
                continue
            raise ValueError(f"Unsupported parameter expression: {expr}")
        try:
            value = eval(compile(tree, "<qasm-param>", "eval"), {"__builtins__": {}}, allowed_names)
        except NameError as exc:
            raise ValueError(f"Unbound parameter in expression '{expr}': {exc}") from exc
        except Exception as exc:
            raise ValueError(f"Invalid parameter expression '{expr}': {exc}") from exc
        return float(value)

    @staticmethod
    def from_qasm(qasm_text: str, param_bindings: dict[str, float] | None = None) -> CircuitIR:
        """Parse a minimal OpenQASM 3 program into ``CircuitIR``.

        Example:
            ```python
            from qsim.circuit.import_qasm import CircuitAdapter

            qasm = "OPENQASM 3; qubit[1] q; x q[0];"
            cir = CircuitAdapter.from_qasm(qasm)
            print(cir.num_qubits, len(cir.gates))
            ```
        """
        statements = CircuitAdapter._split_statements(qasm_text)
        if not statements:
            raise ValueError("Empty QASM input")
        if not CircuitAdapter._HEADER_RE.match(statements[0]):
            raise ValueError("Only OpenQASM 3 is supported (missing 'OPENQASM 3;' header)")

        qregs: dict[str, tuple[int, int]] = {}
        cregs: dict[str, tuple[int, int]] = {}
        next_q = 0
        next_c = 0
        gates: list[CircuitGate] = []

        for st in statements[1:]:
            if st.lower().startswith("include "):
                continue

            qd = CircuitAdapter._DECL_QUBIT_RE.match(st)
            if qd:
                size = int(qd.group(1))
                name = qd.group(2)
                if name in qregs:
                    raise ValueError(f"Duplicate qubit register: {name}")
                qregs[name] = (next_q, size)
                next_q += size
                continue

            cd = CircuitAdapter._DECL_BIT_RE.match(st)
            if cd:
                size = int(cd.group(1))
                name = cd.group(2)
                if name in cregs:
                    raise ValueError(f"Duplicate bit register: {name}")
                cregs[name] = (next_c, size)
                next_c += size
                continue

            mm = CircuitAdapter._MEASURE_RE.match(st)
            if mm:
                qreg, qidx = mm.group(1), int(mm.group(2))
                creg, cidx = mm.group(3), int(mm.group(4))
                if qreg not in qregs:
                    raise ValueError(f"Unknown qubit register in measure: {qreg}")
                if creg not in cregs:
                    raise ValueError(f"Unknown bit register in measure: {creg}")
                qoff, qsize = qregs[qreg]
                coff, csize = cregs[creg]
                if qidx >= qsize:
                    raise ValueError(f"Qubit index out of range: {qreg}[{qidx}]")
                if cidx >= csize:
                    raise ValueError(f"Bit index out of range: {creg}[{cidx}]")
                gates.append(CircuitGate(name="measure", qubits=[qoff + qidx], clbits=[coff + cidx]))
                continue

            gm = CircuitAdapter._GATE_RE.match(st)
            if not gm:
                raise ValueError(f"Unsupported QASM statement: '{st};'")
            name = gm.group(1).lower()
            params_raw = (gm.group(2) or "").strip()
            args_raw = gm.group(3).strip()
            arg_tokens = [a.strip() for a in args_raw.split(",") if a.strip()]
            if not arg_tokens:
                raise ValueError(f"Gate statement has no qubit args: '{st};'")

            # Barrier is a compiler-directive in this project: keep no timing/evolution effect.
            if name == "barrier":
                continue

            qubits: list[int] = []
            for tok in arg_tokens:
                reg, idx = CircuitAdapter._parse_indexed_ref(tok)
                if reg not in qregs:
                    raise ValueError(f"Unknown qubit register in gate: {reg}")
                off, size = qregs[reg]
                if idx >= size:
                    raise ValueError(f"Qubit index out of range: {reg}[{idx}]")
                qubits.append(off + idx)

            params: list[float] = []
            if params_raw:
                for val in [x.strip() for x in params_raw.split(",") if x.strip()]:
                    params.append(CircuitAdapter._eval_param_expr(val, bindings=param_bindings))
            gates.append(CircuitGate(name=name, qubits=qubits, params=params))

        return CircuitIR(num_qubits=next_q, num_clbits=next_c, gates=gates, source_qasm=qasm_text)

    @staticmethod
    def from_qiskit(qc: object) -> CircuitIR:
        """Convert a Qiskit ``QuantumCircuit`` into ``CircuitIR``."""
        gates: list[CircuitGate] = []
        num_qubits = int(getattr(qc, "num_qubits"))
        num_clbits = int(getattr(qc, "num_clbits", 0))
        for inst in getattr(qc, "data", []):
            op = inst.operation
            if getattr(op, "name", "").lower() == "barrier":
                continue
            qargs = [qb._index for qb in inst.qubits]
            cargs = [cb._index for cb in inst.clbits]
            params = [float(p) for p in getattr(op, "params", [])]
            gates.append(CircuitGate(name=op.name, qubits=qargs, clbits=cargs, params=params))

        source_qasm = ""
        try:
            from qiskit import qasm3

            source_qasm = qasm3.dumps(qc)
        except Exception:
            source_qasm = ""

        return CircuitIR(num_qubits=num_qubits, num_clbits=num_clbits, gates=gates, source_qasm=source_qasm)

    @staticmethod
    def to_qasm(circuit: CircuitIR) -> str:
        """Serialize ``CircuitIR`` into OpenQASM 3 text."""
        lines = [
            "OPENQASM 3;",
            f"qubit[{circuit.num_qubits}] q;",
        ]
        if circuit.num_clbits:
            lines.append(f"bit[{circuit.num_clbits}] c;")

        for g in circuit.gates:
            if g.name == "barrier":
                continue
            qargs = ", ".join([f"q[{idx}]" for idx in g.qubits])
            if g.name == "measure" and g.clbits:
                lines.append(f"measure {qargs} -> c[{g.clbits[0]}];")
            else:
                if g.params:
                    p = ", ".join([str(x) for x in g.params])
                    lines.append(f"{g.name}({p}) {qargs};")
                else:
                    lines.append(f"{g.name} {qargs};")
        return "\n".join(lines) + "\n"

    @staticmethod
    def to_qiskit(circuit: CircuitIR) -> object:
        """Convert ``CircuitIR`` to Qiskit ``QuantumCircuit``.

        Raises:
            RuntimeError: If Qiskit is unavailable.
        """
        try:
            from qiskit.circuit import Gate, QuantumCircuit
        except Exception as exc:
            raise RuntimeError("qiskit is required for CircuitAdapter.to_qiskit") from exc

        qc = QuantumCircuit(circuit.num_qubits, circuit.num_clbits)
        standard_gate_map = {
            "x": qc.x,
            "sx": qc.sx,
            "h": qc.h,
            "z": qc.z,
            "rz": qc.rz,
            "cx": qc.cx,
            "cz": qc.cz,
            "id": qc.id,
        }
        for g in circuit.gates:
            if g.name == "barrier":
                continue
            if g.name == "measure":
                if len(g.qubits) != len(g.clbits):
                    raise ValueError("Measure gate must map qubits to clbits one-by-one")
                for q, c in zip(g.qubits, g.clbits):
                    qc.measure(q, c)
                continue

            if g.name in standard_gate_map:
                fn = standard_gate_map[g.name]
                if g.name == "rz":
                    if len(g.params) != 1 or len(g.qubits) != 1:
                        raise ValueError("rz requires exactly one parameter and one qubit")
                    fn(g.params[0], g.qubits[0])
                elif g.name in {"cx", "cz"}:
                    if len(g.qubits) != 2:
                        raise ValueError(f"{g.name} requires exactly two qubits")
                    fn(g.qubits[0], g.qubits[1])
                elif len(g.qubits) == 1:
                    fn(g.qubits[0])
                else:
                    raise ValueError(f"Unsupported arity for gate {g.name}")
                continue

            gate = Gate(name=g.name, num_qubits=len(g.qubits), params=list(g.params))
            qc.append(gate, qargs=g.qubits, cargs=[])

        return qc

    @staticmethod
    def to_json(circuit: CircuitIR) -> dict:
        """Convert ``CircuitIR`` dataclass to plain JSON-compatible dict."""
        return asdict(circuit)
