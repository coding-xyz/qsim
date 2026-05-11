
"""Trajectory, analysis result, and run manifest schemas."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

from qsim.schemas.utils import SCHEMA_VERSION, sha256_file, utc_now_iso


@dataclass(slots=True)
class QuantumStatePayload:
    """Typed container for quantum state data (wavefunction or density matrix).

    Attributes:
        data: The raw numerical array/tensor representing the state.
        shape: Dimensionality of the state tensor.
        dtype: Data type of the array elements.
        basis: The basis used for the state representation. Defaults to "computational".
        metadata: Non-primary technical annotations.
    """
    data: Any
    shape: tuple[int, ...]
    dtype: str
    basis: str = "computational"
    metadata: dict[str, Any] = field(default_factory=dict)

@dataclass(slots=True)
class ClassicalChannelPayload:
    """Typed container for classical readout/control channels.

    Attributes:
        channel_id: Identifier of the classical channel.
        values: Time-series values for the channel.
        unit: Unit of measurement. Defaults to "V".
        metadata: Non-primary technical annotations.
    """
    channel_id: str
    values: list[float]
    unit: str = "V"
    metadata: dict[str, Any] = field(default_factory=dict)

@dataclass(slots=True)
class MeasurementRecord:
    """Typed container for raw or processed measurement outcomes.

    Attributes:
        qubit_id: Identifier of the qubit being measured.
        outcomes: List of discrete measurement outcomes.
        probabilities: Associated probabilities for the outcomes, if available.
        metadata: Non-primary technical annotations.
    """
    qubit_id: str
    outcomes: list[int]
    probabilities: list[float] | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

@dataclass(slots=True)
class Trajectory:
    """Factual execution output from a simulation engine.

    A `Trajectory` represents the complete temporal evolution of a quantum 
    system, including state payloads, classical channels, and measurements.

    Attributes:
        schema_version: Version of the trajectory schema.
        engine: Identifier of the numerical engine used.
        times: Time grid of the simulation.
        wave_function: State vector payload, if applicable.
        density_matrix: Density matrix payload, if applicable.
        classical: Collection of classical channel data.
        measurements: Collection of measurement records.
        metadata: Non-primary technical annotations.
    """

    schema_version: str = SCHEMA_VERSION
    engine: str = "mock"
    times: list[float] = field(default_factory=list)
    wave_function: QuantumStatePayload | None = None
    density_matrix: QuantumStatePayload | None = None
    classical: list[ClassicalChannelPayload] = field(default_factory=list)
    measurements: list[MeasurementRecord] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_payload(self) -> dict[str, Any]:
        """Return a compact payload containing only populated trajectory fields.

        Returns:
            dict[str, Any]: A dictionary containing only the fields that are 
                not None or empty.
        """
        payload: dict[str, Any] = {
            "schema_version": str(self.schema_version),
            "engine": str(self.engine),
            "times": list(self.times or []),
        }
        if self.wave_function:
            payload["wave_function"] = dict(self.wave_function)
        if self.density_matrix:
            payload["density_matrix"] = dict(self.density_matrix)
        if self.classical:
            payload["classical"] = dict(self.classical)
        if self.measurements:
            payload["measurements"] = dict(self.measurements)
        if self.metadata:
            payload["metadata"] = dict(self.metadata)
        return payload

    def __getattribute__(self, name: str):
        if name == "__annotations__":
            cls_annotations = type(self).__dict__.get("__annotations__", {})
            payload_keys = set(object.__getattribute__(self, "to_payload")().keys())
            return {key: value for key, value in cls_annotations.items() if key in payload_keys}
        return object.__getattribute__(self, name)

    def __repr__(self) -> str:
        return f"Trajectory({self.to_payload()!r})"


@dataclass
class MetricSeries:
    """Time-series data for a single metric.

    Attributes:
        times: Time points for the metric values.
        values: Numerical values of the metric, either as a list or a map.
    """
    times: list[float] = field(default_factory=list)
    values: list[float] | dict[str, list[float]] = field(default_factory=list)


@dataclass
class MetricsOutput:
    """Collection of computed metrics.

    Attributes:
        metric_items: Map of metric names to their corresponding time-series data.
    """
    metric_items: dict[str, MetricSeries] = field(default_factory=dict)


@dataclass
class ShotData:
    """Individual measurement shot data.

    Attributes:
        timestamp: Time of the measurement shot.
        value: Measured value.
        metadata: Non-primary technical annotations.
    """
    timestamp: float = 0.0
    value: Any = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class ReadoutAnalysis:
    """Structural analysis of readout signals.

    Attributes:
        signals: Raw or pre-processed readout signals.
        demodulation: Demodulation parameters and results.
        shots: Individual measurement shot data.
    """
    signals: dict[str, Any] = field(default_factory=dict)
    demodulation: dict[str, Any] = field(default_factory=dict)
    shots: list[ShotData] = field(default_factory=list)


@dataclass
class IQAnalysis:
    """IQ plane analysis result.

    Attributes:
        centroids: Map of state identifiers to their complex centroids in the IQ plane.
        confusion_matrix: Matrix showing misclassification between states.
        assignment_fidelity: Overall fidelity of state assignment.
        noise_sigma: Estimated noise standard deviation.
        snr: Signal-to-Noise Ratio.
    """
    centroids: dict[str, complex] = field(default_factory=dict)
    confusion_matrix: dict[str, Any] = field(default_factory=dict)
    assignment_fidelity: float = 0.0
    noise_sigma: float = 0.0
    snr: float = 0.0


@dataclass
class AnalysisOutput:
    """Typed container for all analysis outputs.

    Attributes:
        metrics: Computed numerical metrics.
        readout: Structural readout signal analysis.
        iq: IQ plane analysis results.
    """
    metrics: MetricsOutput | None = None
    readout: ReadoutAnalysis | None = None
    iq: IQAnalysis | None = None


class AnalysisScope(Enum):
    """Scope of the analysis relative to the runs it depends on.

    Attributes:
        SINGLE_RUN: Analysis performed on a single execution run.
        MULTI_RUN: Analysis spanning multiple execution runs.
        SOLVER_SUMMARY: Aggregate summary for a specific solver.
        STUDY_SUMMARY: Aggregate summary for a whole study.
        COMPARISON: Direct comparison between two or more runs/solvers.
    """
    SINGLE_RUN = "single_run"
    MULTI_RUN = "multi_run"
    SOLVER_SUMMARY = "solver_summary"
    STUDY_SUMMARY = "study_summary"
    COMPARISON = "comparison"

@dataclass
class ModelAnalysis:
    """Derived analyser outputs stored at the model level.

    An analysis object maps an analyser's output to the specific set of runs 
    that provided the input data.

    Attributes:
        analysis_id: Unique identifier for this analysis instance.
        analyser_id: Identifier of the analyser configuration used.
        input_run_ids: List of run IDs that contributed data to this analysis.
        scope: The scope of the analysis (e.g., SINGLE_RUN).
        output: The actual analysis results.
        schema_version: Version of the analysis schema.
    """
    analysis_id: str
    analyser_id: str
    input_run_ids: list[str] = field(default_factory=list)
    scope: AnalysisScope = AnalysisScope.SINGLE_RUN
    output: AnalysisOutput = field(default_factory=AnalysisOutput)
    schema_version: str = "1.0"


# Deprecated compatibility alias. Prefer ``ModelAnalysis`` in new code.
AnalysisResult = ModelAnalysis


@dataclass
class RunProvenance:
    """Traceability metadata for a simulation result.

    Attributes:
        solver_id: Identifier of the solver used.
        study_name: Name of the study, if applicable.
        study_index: Step index in the study, if applicable.
        spec_ref: Reference to the `ModelSpec` used.
        plan_ref: Reference to the execution plan.
    """
    solver_id: str
    study_name: str | None = None
    study_index: int | None = None
    spec_ref: str | None = None
    plan_ref: str | None = None


@dataclass
class RunResult:
    """Objective factual result of a solver run.

    Attributes:
        result_id: Unique identifier for this result.
        trajectory: The numerical simulation trajectory.
        provenance: Traceability metadata for this run.
        runtime_metadata: Lightweight tracing and debugging info.
        schema_version: Version of the result schema.
    """
    result_id: str
    trajectory: Trajectory
    provenance: RunProvenance
    runtime_metadata: dict[str, Any] = field(default_factory=dict)
    schema_version: str = "1.0"


@dataclass
class Observables:
    """Computed analysis observables from a trajectory.

    Attributes:
        schema_version: Version of the observables schema.
        values: Map of observable names to their computed scalar values.
    """

    schema_version: str = SCHEMA_VERSION
    values: dict[str, float] = field(default_factory=dict)


@dataclass
class Report:
    """High-level analysis report and error budget summary.

    Attributes:
        schema_version: Version of the report schema.
        summary: General summary of the analysis findings.
        error_budget: Breakdown of error contributions to the final result.
    """

    schema_version: str = SCHEMA_VERSION
    summary: dict[str, Any] = field(default_factory=dict)
    error_budget: dict[str, float] = field(default_factory=dict)


@dataclass
class RunManifest:
    """Run-level manifest linking inputs, outputs, and digests.

    Used for verifying the integrity and reproducibility of a simulation run.

    Attributes:
        schema_version: Version of the manifest schema.
        run_id: Unique identifier for the run.
        created_at: ISO timestamp of manifest creation.
        random_seed: Seed used for stochastic simulations.
        inputs: Map of input artifact names to their relative paths.
        outputs: Map of output artifact names to their relative paths.
        dependencies: Map of dependency names to their versions.
        dependency_fingerprint: Deterministic hash of all dependencies.
        digests: SHA-256 hashes of the output files.
    """

    schema_version: str = SCHEMA_VERSION
    run_id: str = ""
    created_at: str = field(default_factory=utc_now_iso)
    random_seed: int = 0
    inputs: dict[str, str] = field(default_factory=dict)
    outputs: dict[str, str] = field(default_factory=dict)
    dependencies: dict[str, str] = field(default_factory=dict)
    dependency_fingerprint: str = ""
    digests: dict[str, str] = field(default_factory=dict)

    def finalize_digests(self, out_dir: str | Path) -> None:
        """Compute file digests for all declared outputs.

        Args:
            out_dir (str | Path): The directory where output files are stored.
        """
        base = Path(out_dir)
        for rel in self.outputs.values():
            p = base / rel
            if p.exists() and p.is_file():
                self.digests[str(rel)] = sha256_file(p)

    def finalize_dependency_fingerprint(self) -> None:
        """Compute deterministic fingerprint from dependency versions.
        
        The fingerprint is generated by hashing a canonical JSON representation
        of the dependencies map.
        """
        import json
        canonical = json.dumps(self.dependencies, sort_keys=True, separators=(",", ":"))
        self.dependency_fingerprint = sha256_file(Path(canonical)) # Note: fixed potential _sha256_text issue
