"""Backend configuration loading, validation, normalization, and persistence helpers."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
import json

import yaml

from qsim.common.schemas import BackendConfig
from qsim.common.unit_schema import (
    MODEL_HARDWARE_KEYS,
    NOISE_KEYS,
    reject_unknown_coupling_keys,
    reject_unknown_keys,
)


_ALLOWED_LEVEL = {"qubit", "nlevel", "cqed", "io"}
_ALLOWED_NOISE = {"deterministic", "lindblad", "sde", "tls", "hybrid"}
_ALLOWED_SOLVER = {"se", "me", "mcwf", "heom", "io"}


@dataclass(frozen=True)
class QubitConfig:
    """Normalized per-qubit hardware and local-noise values."""

    freq_Hz: float = 0.0
    anharmonicity_Hz: float = -0.2
    T1_s: float | None = None
    T2_s: float | None = None
    Tphi_s: float | None = None
    Tup_s: float | None = None
    gamma1_Hz: float | None = None
    gamma_phi_Hz: float | None = None
    gamma_up_Hz: float | None = None
    raw: dict[str, Any] = field(default_factory=dict)

    def value(self, key: str, default: float = 0.0) -> float:
        raw_value = getattr(self, key, None)
        return float(default if raw_value is None else raw_value)

    def to_dict(self) -> dict[str, Any]:
        data = dict(self.raw)
        data.setdefault("freq_Hz", self.freq_Hz)
        data.setdefault("anharmonicity_Hz", self.anharmonicity_Hz)
        for key in ("T1_s", "T2_s", "Tphi_s", "Tup_s", "gamma1_Hz", "gamma_phi_Hz", "gamma_up_Hz"):
            value = getattr(self, key)
            if value is not None:
                data[key] = value
        return data


@dataclass(frozen=True)
class ComponentConfig:
    """Normalized device component."""

    id: str = ""
    type: str = ""
    representation: str = "quantum"
    basis: dict[str, Any] = field(default_factory=dict)
    parameters: dict[str, Any] = field(default_factory=dict)
    noise: dict[str, Any] = field(default_factory=dict)
    description: str = ""
    raw: dict[str, Any] = field(default_factory=dict)

    def get(self, key: str, default: Any = None) -> Any:
        return self.to_dict().get(key, default)

    def to_dict(self) -> dict[str, Any]:
        data = dict(self.raw)
        data.update(
            {
                "id": self.id,
                "type": self.type,
                "representation": self.representation,
                "parameters": dict(self.parameters),
            }
        )
        if self.basis:
            data["basis"] = dict(self.basis)
        if self.noise:
            data["noise"] = dict(self.noise)
        if self.description:
            data["description"] = self.description
        return data


@dataclass(frozen=True)
class ConnectionConfig:
    """Normalized device connection."""

    id: str = ""
    type: str = ""
    a: str = ""
    b: str = ""
    via: str = ""
    parameters: dict[str, Any] = field(default_factory=dict)
    raw: dict[str, Any] = field(default_factory=dict)

    def get(self, key: str, default: Any = None) -> Any:
        return self.to_dict().get(key, default)

    def to_dict(self) -> dict[str, Any]:
        data = dict(self.raw)
        data.update({"id": self.id, "type": self.type, "a": self.a, "b": self.b, "parameters": dict(self.parameters)})
        if self.via:
            data["via"] = self.via
        return data


@dataclass(frozen=True)
class CouplingConfig:
    """Normalized qubit-qubit coupling."""

    i: int = 0
    j: int = 0
    g_Hz: float = 0.0
    kind: str = "xx+yy"
    raw: dict[str, Any] = field(default_factory=dict)

    @property
    def g_rad_s(self) -> float:
        return 2.0 * 3.141592653589793 * float(self.g_Hz)

    def get(self, key: str, default: Any = None) -> Any:
        return self.to_dict().get(key, default)

    def to_dict(self) -> dict[str, Any]:
        data = dict(self.raw)
        data.update({"i": self.i, "j": self.j, "g_Hz": self.g_Hz, "kind": self.kind})
        return data


@dataclass(frozen=True)
class DeviceConfig:
    """Normalized device configuration consumed by backend lowering."""

    data: dict[str, Any] = field(default_factory=dict)
    components: list[ComponentConfig] = field(default_factory=list)
    connections: list[ConnectionConfig] = field(default_factory=list)
    couplings: list[CouplingConfig] = field(default_factory=list)
    qubits: list[QubitConfig] = field(default_factory=list)
    simulation_level: str = "qubit"
    control_scale: float = 1.0
    qubit_freq_Hz: float = 0.0
    qubit_freqs_Hz: list[float] | None = None
    transmon_levels: int | None = None
    cavity_nmax: int | None = None
    cavity_freq_Hz: float | None = None
    dimension: int | None = None
    anharmonicity_Hz: list[float] | float | None = None
    g_cavity_Hz: list[float] | float | None = None
    gamma1_Hz: Any = None
    gamma_phi_Hz: Any = None
    gamma_up_Hz: Any = None
    T1_s: Any = None
    T2_s: Any = None
    Tphi_s: Any = None
    Tup_s: Any = None

    @property
    def component_dicts(self) -> list[dict[str, Any]]:
        return [item.to_dict() for item in self.components]

    @property
    def connection_dicts(self) -> list[dict[str, Any]]:
        return [item.to_dict() for item in self.connections]

    @property
    def coupling_dicts(self) -> list[dict[str, Any]]:
        return [item.to_dict() for item in self.couplings]

    @property
    def qubit_dicts(self) -> list[dict[str, Any]]:
        return [item.to_dict() for item in self.qubits]

    def get(self, key: str, default: Any = None) -> Any:
        return self.to_dict().get(key, default)

    def to_dict(self) -> dict[str, Any]:
        data = dict(self.data)
        data.update(
            {
                "components": self.component_dicts,
                "connections": self.connection_dicts,
                "couplings": self.coupling_dicts,
                "qubits": self.qubit_dicts,
                "simulation_level": self.simulation_level,
                "control_scale": self.control_scale,
            }
        )
        for key in (
            "qubit_freq_Hz",
            "qubit_freqs_Hz",
            "transmon_levels",
            "cavity_nmax",
            "cavity_freq_Hz",
            "dimension",
            "anharmonicity_Hz",
            "g_cavity_Hz",
            "gamma1_Hz",
            "gamma_phi_Hz",
            "gamma_up_Hz",
            "T1_s",
            "T2_s",
            "Tphi_s",
            "Tup_s",
        ):
            value = getattr(self, key)
            if value is not None:
                data[key] = value
        return data


@dataclass(frozen=True)
class LocalNoiseConfig:
    """Normalized local noise values before expansion to qubits."""

    gamma1_Hz: Any = None
    gamma_phi_Hz: Any = None
    gamma_up_Hz: Any = None
    T1_s: Any = None
    T2_s: Any = None
    Tphi_s: Any = None
    Tup_s: Any = None


@dataclass(frozen=True)
class StochasticNoiseConfig:
    """Normalized stochastic dephasing noise values."""

    one_over_f_amp_Hz: Any = 0.0
    one_over_f_fmin_Hz: Any = 1e-3
    one_over_f_fmax_Hz: Any = None
    one_over_f_exponent: Any = 1.0
    ou_sigma_Hz: Any = 0.0
    ou_tau_s: Any = 1.0


@dataclass(frozen=True)
class NoiseConfig:
    """Normalized noise configuration consumed by model lowering."""

    data: dict[str, Any] = field(default_factory=dict)
    model: str = "markovian_lindblad"
    local: LocalNoiseConfig = field(default_factory=LocalNoiseConfig)
    stochastic: StochasticNoiseConfig = field(default_factory=StochasticNoiseConfig)
    one_over_f: bool = False

    def get(self, key: str, default: Any = None) -> Any:
        return self.to_dict().get(key, default)

    def to_dict(self) -> dict[str, Any]:
        data = dict(self.data)
        data["model"] = self.model
        if self.one_over_f:
            data["one_over_f"] = True
        return data


@dataclass(frozen=True)
class SolverConfig:
    """Normalized solver runtime controls."""

    data: dict[str, Any] = field(default_factory=dict)
    dt_s: float | None = None
    t_end_s: float | None = None
    t_padding_s: float = 0.0
    seed: int | None = None
    ntraj: int | None = None

    def get(self, key: str, default: Any = None) -> Any:
        return self.data.get(key, default)

    def __getitem__(self, key: str) -> Any:
        return self.data[key]

    def to_dict(self) -> dict[str, Any]:
        return dict(self.data)


@dataclass(frozen=True)
class FrameConfig:
    """Normalized reference-frame request."""

    data: dict[str, Any] = field(default_factory=dict)
    mode: str = "rotating"
    reference: str = "pulse_carrier"
    rwa: bool = True
    qubit_reference_freqs_Hz: list[float] | None = None

    def get(self, key: str, default: Any = None) -> Any:
        return self.data.get(key, default)

    def to_dict(self) -> dict[str, Any]:
        return dict(self.data)


@dataclass(frozen=True)
class StudyConfig:
    """Normalized study configuration with selected primary step."""

    steps: list[dict[str, Any]] = field(default_factory=list)
    primary_step: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class AnalysisConfig:
    """Normalized analyser request."""

    data: dict[str, Any] = field(default_factory=dict)
    trajectory: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return dict(self.data)


@dataclass(frozen=True)
class ModelBuildConfig:
    """Normalized config bundle for ``DefaultModelBuilder``."""

    device: DeviceConfig
    noise: NoiseConfig
    solver: SolverConfig
    frame: FrameConfig
    study: StudyConfig
    analysis: AnalysisConfig


def _normalize_simulation_level(value: Any) -> str:
    level = str(value or "qubit").strip().lower()
    return level if level in {"qubit", "nlevel", "cqed"} else "qubit"


def _normalize_frame_reference(value: Any) -> str:
    reference = str(value or "pulse_carrier").strip().lower()
    if reference == "carrier":
        return "pulse_carrier"
    return reference if reference in {"pulse_carrier", "explicit", "none"} else "pulse_carrier"


def _normalize_noise_model(value: Any, *, one_over_f: bool = False) -> str:
    model = str(value or "markovian_lindblad").strip().lower()
    if one_over_f:
        return "one_over_f"
    if model in {"1/f", "one_over_f", "pink"}:
        return "one_over_f"
    if model in {"ou", "ornstein_uhlenbeck", "lorentzian"}:
        return "ou"
    return model or "markovian_lindblad"


def _optional_float(value: Any) -> float | None:
    return None if value is None else float(value)


def _normalize_qubit(raw: dict[str, Any]) -> QubitConfig:
    data = dict(raw or {})
    return QubitConfig(
        freq_Hz=float(data.get("freq_Hz", 0.0)),
        anharmonicity_Hz=float(data.get("anharmonicity_Hz", -0.2)),
        T1_s=_optional_float(data.get("T1_s")),
        T2_s=_optional_float(data.get("T2_s")),
        Tphi_s=_optional_float(data.get("Tphi_s")),
        Tup_s=_optional_float(data.get("Tup_s")),
        gamma1_Hz=_optional_float(data.get("gamma1_Hz")),
        gamma_phi_Hz=_optional_float(data.get("gamma_phi_Hz")),
        gamma_up_Hz=_optional_float(data.get("gamma_up_Hz")),
        raw=data,
    )


def _normalize_component(raw: dict[str, Any]) -> ComponentConfig:
    data = dict(raw or {})
    return ComponentConfig(
        id=str(data.get("id", "")),
        type=str(data.get("type", "")).strip().lower(),
        representation=str(data.get("representation", "quantum")).strip().lower(),
        basis=dict(data.get("basis", {}) or {}),
        parameters=dict(data.get("parameters", {}) or {}),
        noise=dict(data.get("noise", {}) or {}),
        description=str(data.get("description", "")),
        raw=data,
    )


def _normalize_connection(raw: dict[str, Any]) -> ConnectionConfig:
    data = dict(raw or {})
    return ConnectionConfig(
        id=str(data.get("id", "")),
        type=str(data.get("type", "")).strip().lower(),
        a=str(data.get("a", "")),
        b=str(data.get("b", "")),
        via=str(data.get("via", "")),
        parameters=dict(data.get("parameters", {}) or {}),
        raw=data,
    )


def _normalize_coupling(raw: dict[str, Any]) -> CouplingConfig:
    data = dict(raw or {})
    return CouplingConfig(
        i=int(data.get("i", 0)),
        j=int(data.get("j", 0)),
        g_Hz=float(data.get("g_Hz", 0.0)),
        kind=str(data.get("kind", "xx+yy")),
        raw=data,
    )


def normalize_device_config(raw: dict[str, Any] | DeviceConfig | None) -> DeviceConfig:
    """Normalize a raw device mapping into a stable backend config object."""
    if isinstance(raw, DeviceConfig):
        return raw
    data = dict(raw or {})
    reject_unknown_keys("device", data, MODEL_HARDWARE_KEYS)
    reject_unknown_coupling_keys(list(data.get("couplings", [])))

    components = [_normalize_component(comp) for comp in list(data.get("components", []) or []) if isinstance(comp, dict)]
    connections = [_normalize_connection(conn) for conn in list(data.get("connections", []) or []) if isinstance(conn, dict)]
    couplings = [_normalize_coupling(coupling) for coupling in list(data.get("couplings", []) or []) if isinstance(coupling, dict)]
    qubits = [_normalize_qubit(qubit) for qubit in list(data.get("qubits", []) or []) if isinstance(qubit, dict)]
    simulation_level = _normalize_simulation_level(data.get("simulation_level", "qubit"))
    normalized = {
        **data,
        "components": [item.to_dict() for item in components],
        "connections": [item.to_dict() for item in connections],
        "couplings": [item.to_dict() for item in couplings],
        "qubits": [item.to_dict() for item in qubits],
        "simulation_level": simulation_level,
        "control_scale": float(data.get("control_scale", 1.0)),
    }
    return DeviceConfig(
        data=normalized,
        components=components,
        connections=connections,
        couplings=couplings,
        qubits=qubits,
        simulation_level=simulation_level,
        control_scale=float(normalized["control_scale"]),
        qubit_freq_Hz=float(data.get("qubit_freq_Hz", 0.0)),
        qubit_freqs_Hz=[float(x) for x in list(data.get("qubit_freqs_Hz", []) or [])] if data.get("qubit_freqs_Hz") is not None else None,
        transmon_levels=None if data.get("transmon_levels") is None else int(data.get("transmon_levels")),
        cavity_nmax=None if data.get("cavity_nmax") is None else int(data.get("cavity_nmax")),
        cavity_freq_Hz=_optional_float(data.get("cavity_freq_Hz")),
        dimension=None if data.get("dimension") is None else int(data.get("dimension")),
        anharmonicity_Hz=data.get("anharmonicity_Hz"),
        g_cavity_Hz=data.get("g_cavity_Hz"),
        gamma1_Hz=data.get("gamma1_Hz"),
        gamma_phi_Hz=data.get("gamma_phi_Hz"),
        gamma_up_Hz=data.get("gamma_up_Hz"),
        T1_s=data.get("T1_s"),
        T2_s=data.get("T2_s"),
        Tphi_s=data.get("Tphi_s"),
        Tup_s=data.get("Tup_s"),
    )


def normalize_noise_config(raw: dict[str, Any] | NoiseConfig | None) -> NoiseConfig:
    """Normalize a raw noise mapping into a stable backend config object."""
    if isinstance(raw, NoiseConfig):
        return raw
    data = dict(raw or {})
    reject_unknown_keys("noise", data, NOISE_KEYS)
    model = _normalize_noise_model(data.get("model", data.get("type", "")), one_over_f=bool(data.get("one_over_f", False)))
    local = LocalNoiseConfig(
        gamma1_Hz=data.get("gamma1_per_qubit_Hz", data.get("gamma1_Hz")),
        gamma_phi_Hz=data.get("gamma_phi_per_qubit_Hz", data.get("gamma_phi_Hz")),
        gamma_up_Hz=data.get("gamma_up_per_qubit_Hz", data.get("gamma_up_Hz")),
        T1_s=data.get("T1_per_qubit_s", data.get("T1_s")),
        T2_s=data.get("T2_per_qubit_s", data.get("T2_s")),
        Tphi_s=data.get("Tphi_per_qubit_s", data.get("Tphi_s")),
        Tup_s=data.get("Tup_per_qubit_s", data.get("Tup_s")),
    )
    stochastic = StochasticNoiseConfig(
        one_over_f_amp_Hz=data.get("one_over_f_amp_Hz", 0.0),
        one_over_f_fmin_Hz=data.get("one_over_f_fmin_Hz", 1e-3),
        one_over_f_fmax_Hz=data.get("one_over_f_fmax_Hz"),
        one_over_f_exponent=data.get("one_over_f_exponent", 1.0),
        ou_sigma_Hz=data.get("ou_sigma_Hz", 0.0),
        ou_tau_s=data.get("ou_tau_s", 1.0),
    )
    return NoiseConfig(
        data={**data, "model": model},
        model=model,
        local=local,
        stochastic=stochastic,
        one_over_f=bool(data.get("one_over_f", False)),
    )


SolverRunConfig = SolverConfig


def normalize_solver_config(raw: dict[str, Any] | SolverConfig | None) -> SolverConfig:
    """Normalize solver runtime controls."""
    if isinstance(raw, SolverConfig):
        return raw
    data = dict(raw or {})
    reject_unknown_keys(
        "solver.run",
        data,
        {
            "dt_s",
            "t_end_s",
            "t_padding_s",
            "seed",
            "ntraj",
            "mcwf_ntraj",
            "qutip_options",
            "native_options",
            "backend_options",
            "one_over_f_components",
        },
    )
    dt_s = None if data.get("dt_s") is None else float(data["dt_s"])
    t_end_s = None if data.get("t_end_s") is None else float(data["t_end_s"])
    t_padding_s = max(0.0, 0.0 if data.get("t_padding_s") is None else float(data["t_padding_s"]))
    seed = None if data.get("seed") is None else int(data["seed"])
    ntraj_raw = data.get("ntraj", data.get("mcwf_ntraj", None))
    ntraj = None if ntraj_raw is None else int(max(1, int(ntraj_raw)))
    normalized: dict[str, Any] = {}
    if dt_s is not None:
        normalized["dt_s"] = dt_s
    if t_end_s is not None:
        normalized["t_end_s"] = t_end_s
    if t_padding_s > 0.0 or "t_padding_s" in data:
        normalized["t_padding_s"] = t_padding_s
    if seed is not None:
        normalized["seed"] = seed
    if ntraj is not None:
        normalized["ntraj"] = ntraj
    for key in ("qutip_options", "native_options", "backend_options", "one_over_f_components"):
        if key in data:
            normalized[key] = data[key]
    return SolverConfig(data=normalized, dt_s=dt_s, t_end_s=t_end_s, t_padding_s=t_padding_s, seed=seed, ntraj=ntraj)


def normalize_solver_run_config(raw: dict[str, Any] | SolverConfig | None) -> SolverConfig:
    """Backward-compatible alias for ``normalize_solver_config``."""
    return normalize_solver_config(raw)


def normalize_frame_config(raw: dict[str, Any] | FrameConfig | None) -> FrameConfig:
    """Normalize frame configuration."""
    if isinstance(raw, FrameConfig):
        return raw
    data = dict(raw or {})
    mode = str(data.get("mode", "rotating")).strip().lower()
    if mode not in {"rotating", "lab"}:
        mode = "rotating"
    reference = _normalize_frame_reference(data.get("reference", "pulse_carrier"))
    refs = data.get("qubit_reference_freqs_Hz")
    explicit_refs = None if refs is None else [float(x) for x in list(refs or [])]
    normalized = {
        "mode": mode,
        "reference": reference,
        "rwa": bool(data.get("rwa", True)),
    }
    if explicit_refs is not None:
        normalized["qubit_reference_freqs_Hz"] = explicit_refs
    return FrameConfig(
        data=normalized,
        mode=mode,
        reference=reference,
        rwa=bool(normalized["rwa"]),
        qubit_reference_freqs_Hz=explicit_refs,
    )


def normalize_study_config(
    study: list[dict[str, Any]] | StudyConfig | None,
    primary_step: dict[str, Any] | None = None,
) -> StudyConfig:
    """Normalize study steps and selected primary step."""
    if isinstance(study, StudyConfig):
        return study
    steps = [dict(step) for step in list(study or []) if isinstance(step, dict)]
    selected = dict(primary_step or {})
    return StudyConfig(steps=steps, primary_step=selected)


def normalize_analysis_config(raw: dict[str, Any] | AnalysisConfig | None) -> AnalysisConfig:
    """Normalize analyser request config."""
    if isinstance(raw, AnalysisConfig):
        return raw
    data = dict(raw or {})
    return AnalysisConfig(data=data, trajectory=dict(data.get("trajectory", {}) or {}))


def normalize_model_build_config(
    *,
    device: dict[str, Any] | DeviceConfig | None,
    noise: dict[str, Any] | NoiseConfig | None,
    solver_run: dict[str, Any] | SolverConfig | None,
    frame: dict[str, Any] | FrameConfig | None,
    analyser: dict[str, Any] | AnalysisConfig | None,
    study: list[dict[str, Any]] | StudyConfig | None,
    primary_step: dict[str, Any] | None,
) -> ModelBuildConfig:
    """Normalize all raw model-build config inputs at the backend boundary."""
    return ModelBuildConfig(
        device=normalize_device_config(device),
        noise=normalize_noise_config(noise),
        solver=normalize_solver_config(solver_run),
        frame=normalize_frame_config(frame),
        study=normalize_study_config(study, primary_step),
        analysis=normalize_analysis_config(analyser),
    )


def load_backend_config(yaml_path: str | Path) -> BackendConfig:
    """Load and validate backend config from YAML file."""
    raw = yaml.safe_load(Path(yaml_path).read_text(encoding="utf-8")) or {}
    cfg = BackendConfig(
        level=str(raw.get("level", "qubit")),
        noise=str(raw.get("noise", "deterministic")),
        solver=str(raw.get("solver", "se")),
        analysis_pipeline=str(raw.get("analysis", raw.get("analysis_pipeline", "default"))),
        truncation=dict(raw.get("truncation", {})),
        sweep=list(raw.get("sweep", [])),
        seed=int(raw.get("seed", 1234)),
    )
    validate_backend_config(cfg)
    return cfg


def validate_backend_config(cfg: BackendConfig) -> None:
    """Validate ``BackendConfig`` fields and value domains."""
    if cfg.level not in _ALLOWED_LEVEL:
        raise ValueError(f"Invalid level: {cfg.level}")
    if cfg.noise not in _ALLOWED_NOISE:
        raise ValueError(f"Invalid noise: {cfg.noise}")
    if cfg.solver not in _ALLOWED_SOLVER:
        raise ValueError(f"Invalid solver: {cfg.solver}")
    if not isinstance(cfg.truncation, dict):
        raise ValueError("truncation must be a mapping")


def dump_backend_config(cfg: BackendConfig, out_path: str | Path) -> Path:
    """Write ``BackendConfig`` as pretty JSON and return output path."""
    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(cfg.__dict__, ensure_ascii=False, indent=2), encoding="utf-8")
    return out
