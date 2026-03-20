"""Subprocess runtime helper for Julia-backed simulation engines."""

from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
import json
import os
import shutil
import subprocess
import tempfile

from qsim.common.schemas import ModelSpec, Trace


class JuliaRuntimeRunner:
    """Dispatch ``ModelSpec`` payloads to a Julia runtime and normalize the response."""

    def __init__(self, engine_package: str):
        self.engine_package = str(engine_package).strip().lower()

    def _resolve_script(self) -> Path:
        here = Path(__file__).resolve().parent
        scripts = {
            "quantumoptics": here / "qoptics_runtime.jl",
            "quantumtoolbox": here / "qtoolbox_runtime.jl",
        }
        try:
            return scripts[self.engine_package]
        except KeyError as exc:
            raise RuntimeError(f"Unsupported Julia engine package: {self.engine_package}") from exc

    @staticmethod
    def _candidate_julia_bins() -> list[str]:
        home = Path.home()
        roots = [
            home / ".julia" / "juliaup",
            home / "AppData" / "Local" / "Programs",
            Path(r"C:\Program Files"),
            Path("C:\\"),
        ]
        out: list[str] = []
        for root in roots:
            if not root.exists():
                continue
            patterns = ["Julia-*/bin/julia.exe", "julia-*/bin/julia.exe"]
            for pat in patterns:
                for p in root.glob(pat):
                    out.append(str(p))
        return out

    @staticmethod
    def _resolve_julia_bin(run_options: dict) -> str:
        julia_bin = str(run_options.get("julia_bin", "julia"))
        resolved = shutil.which(julia_bin)
        if resolved and "windowsapps" in resolved.lower() and julia_bin.lower() in {"julia", "julia.exe"}:
            for cand in JuliaRuntimeRunner._candidate_julia_bins():
                if Path(cand).exists():
                    return cand
        if resolved is not None:
            return julia_bin
        for cand in JuliaRuntimeRunner._candidate_julia_bins():
            if Path(cand).exists():
                return cand
        if shutil.which(julia_bin) is None:
            raise RuntimeError(f"Julia executable not found: {julia_bin}")
        return julia_bin

    @staticmethod
    def _to_julia_literal(value) -> str:
        if value is None:
            return "nothing"
        if isinstance(value, bool):
            return "true" if value else "false"
        if isinstance(value, (int, float)):
            return repr(value)
        if isinstance(value, str):
            return json.dumps(value, ensure_ascii=False)
        if isinstance(value, (list, tuple)):
            inner = ", ".join(JuliaRuntimeRunner._to_julia_literal(v) for v in value)
            return f"Any[{inner}]"
        if isinstance(value, dict):
            items = []
            for k, v in value.items():
                key = JuliaRuntimeRunner._to_julia_literal(str(k))
                val = JuliaRuntimeRunner._to_julia_literal(v)
                items.append(f"{key} => {val}")
            return f"Dict({', '.join(items)})"
        return json.dumps(str(value), ensure_ascii=False)

    def run(self, model_spec: ModelSpec, run_options: dict | None = None) -> Trace:
        run_options = dict(run_options or {})
        script = self._resolve_script()
        if not script.exists():
            raise RuntimeError(f"Julia engine script not found: {script}")

        julia_bin = self._resolve_julia_bin(run_options)
        timeout_s = float(run_options.get("julia_timeout_s", 120.0))
        payload = {
            "schema_version": "1.0",
            "engine_package": self.engine_package,
            "solver_mode": str(run_options.get("solver_mode", model_spec.solver)).lower(),
            "model_spec": asdict(model_spec),
            "run_options": run_options,
        }

        with tempfile.TemporaryDirectory(prefix="qsim_julia_") as tmp:
            tmp_dir = Path(tmp)
            inp = tmp_dir / "request.jl"
            out = tmp_dir / "response.json"
            env = os.environ.copy()
            depot_opt = run_options.get("julia_depot_path", None)
            if depot_opt:
                depot = Path(str(depot_opt))
                depot.mkdir(parents=True, exist_ok=True)
                env["JULIA_DEPOT_PATH"] = str(depot)
            req_text = "\n".join(
                [
                    f"engine_package = {self._to_julia_literal(payload['engine_package'])}",
                    f"solver_mode = {self._to_julia_literal(payload['solver_mode'])}",
                    f"model_spec = {self._to_julia_literal(payload['model_spec'])}",
                    f"run_options = {self._to_julia_literal(payload['run_options'])}",
                    "",
                ]
            )
            inp.write_text(req_text, encoding="utf-8")
            cmd = [julia_bin, "--startup-file=no", str(script), str(inp), str(out)]
            proc = subprocess.run(
                cmd,
                check=False,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                env=env,
                timeout=timeout_s,
            )
            if proc.returncode != 0:
                stderr = (proc.stderr or "").strip()
                stdout = (proc.stdout or "").strip()
                msg = stderr or stdout or f"exit code {proc.returncode}"
                lower_msg = msg.lower()
                if "package pkg not found" in lower_msg or "package linearalgebra not found" in lower_msg:
                    msg = (
                        f"{msg}\nHint: the selected Julia runtime appears incomplete (missing stdlib). "
                        "Install a full Julia distribution and pass --julia-bin if needed."
                    )
                elif "package json3 not found" in lower_msg:
                    msg = (
                        f"{msg}\nHint: install Julia deps in an active depot/project: "
                        'using Pkg; Pkg.add(["JSON3","QuantumOptics","QuantumToolbox"]).'
                    )
                raise RuntimeError(f"Julia runtime failed: {msg}")
            if not out.exists():
                raise RuntimeError("Julia runtime did not produce a response file")
            response = json.loads(out.read_text(encoding="utf-8"))
            if isinstance(response, dict) and str(response.get("status", "ok")).lower() == "error":
                raise RuntimeError(str(response.get("error", "unknown Julia runtime error")))

        times = [float(x) for x in response.get("times", [])]
        states = [[float(v) for v in row] for row in response.get("states", [])]
        metadata = dict(response.get("metadata", {}))
        metadata["bridge"] = "subprocess_json"
        metadata["engine_package"] = self.engine_package
        default_engine = {"quantumoptics": "qoptics", "quantumtoolbox": "qtoolbox"}.get(
            self.engine_package,
            self.engine_package,
        )
        return Trace(
            engine=str(response.get("engine", default_engine)),
            times=times,
            states=states,
            metadata=metadata,
        )


__all__ = ["JuliaRuntimeRunner"]
