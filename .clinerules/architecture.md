# Architecture Rules for Agents

This file defines the required architectural model for the `qsim` codebase.
Any agent editing this repository must follow these rules before adding fields,
moving objects, or introducing new abstractions.

The goal is to keep the program structurally stable:

- one concept has one authoritative home
- configuration, runtime state, IR, results, and analysis are separated
- temporary convenience structures must not become long-term architecture
- typed objects are preferred over raw dictionaries
- agents must not start with one structure and silently end with another

## 1. Architectural Intent

`qsim` is a layered quantum simulation workflow system.

The codebase should be understood as:

1. `schemas/`
Defines stable typed domain models and exchange boundaries.

2. `workflow/`
Composes configs, builds runtime tasks, executes runs, stores run-scoped
artifacts, and orchestrates analysis.

3. `backend/`
Compiles circuits and device descriptions into executable simulation models.

4. `engines/`
Numerical execution backends that consume engine-neutral model specs.

5. `analysis/`
Postprocessing of trajectories into metrics, readout analyses, IQ summaries,
reports, and derived observables.

6. `pulse/`
Pulse lowering, compilation, waveform generation, trajectory persistence, and
pulse-side visualization helpers.

7. `circuit/`
Circuit import, export, normalization, and gate-level manipulation.

8. `qec/`
Decoder, prior, syndrome, and logical error related processing.

9. `ui/` and `session/`
Presentation, notebook/CLI experience, and user-facing workflow entrypoints.

10. `common/`
Shared primitives, serialization helpers, generic dataclasses, and utility
schemas used across layers.

## 2. Layer Boundaries

Agents must preserve these boundaries:

- `schemas/` may define data structures but must not perform workflow
  orchestration.
- `workflow/` may orchestrate execution but should not become a dumping ground
  for untyped domain state.
- `backend/` may produce executable/intermediate artifacts but must not own the
  long-term user model container.
- `analysis/` consumes results and produces derived outputs; it must not mutate
  user configuration.
- `engines/` execute; they should not decide repository-wide storage structure.
- `ui/` must call stable workflow APIs instead of reimplementing pipeline logic.

If a change crosses multiple layers, the agent must preserve the directional
flow:

`config -> runtime contract -> compiled artifacts -> engine result -> analysis`

## 3. Canonical Program Structure

The whole program should converge on the following logical structure for the
workflow model.

```text
Model
|- config: ModelConfig
|  |- task: WorkflowTaskConfig
|  |- device: WorkflowDeviceConfig
|  |- pulse: WorkflowPulseConfig
|  |- solvers: dict[str, WorkflowSolverConfig]
|  `- analysers: dict[str, DefaultAnalyserConfig]
|- registry: ModelRegistry
|  `- metric_registry: MetricRegistry
|- state: ModelState
|  |- default_solver_id: str | None
|  |- default_analyser_id: str | None
|  |- last_run_id: str | None
|  `- out_dir: str | None
|- runs: dict[str, ModelRun]
|  `- <run_id>: ModelRun
|     |- identity: RunIdentity
|     |- runtime_task: WorkflowTask
|     |- artifacts: RunArtifacts
|     `- result: RunResult
|- analyses: dict[str, ModelAnalysis]
|  `- <analysis_id>: ModelAnalysis
|     |- analysis_id: str
|     |- analyser_id: str
|     |- input_run_ids: list[str]
|     |- scope: AnalysisScope
|     `- output: AnalysisOutput
`- manifest: ModelManifest
```

This is the target mental model even if legacy code has not fully converged yet.

The result-bearing part of the model must be understood as:

```text
Model
|- runs: dict[str, ModelRun]
|  `- <run_id>: ModelRun
|     |- identity: RunIdentity
|     |- runtime_task: WorkflowTask
|     |- artifacts: RunArtifacts
|     `- result: RunResult
`- runs: dict[str, ModelRun]
`- analyses: dict[str, ModelAnalysis]
   `- <analysis_id>: ModelAnalysis
      |- analyser_id
      |- input_run_ids
      |- scope
      `- output
```

The important ownership rule is:

- one run owns one factual execution result
- one analysis may depend on one or more runs
- analyses live at `Model` level as primary storage
- cross-run and single-run analyses use the same model-level analysis layer
  but must declare their input run set explicitly

## 4. Canonical Data Taxonomy

Every important object must be classified into exactly one category.

### 4.1 Config

Editable input definitions loaded from files, UI, or user code.

Representation rule:

- must be a class/dataclass/schema object

Examples:

- `WorkflowTaskConfig`
- `WorkflowDeviceConfig`
- `WorkflowPulseConfig`
- `WorkflowSolverConfig`
- `DefaultAnalyserConfig`

### 4.2 Runtime Contract

Structured objects passed between layers during execution.

Representation rule:

- must be a class/dataclass/schema object

Examples:

- `WorkflowTask`
- backend config objects

### 4.3 Domain Model

Engine-neutral semantic model of what is being simulated.

Representation rule:

- must be a typed schema/dataclass

Examples:

- `ModelSpec`

### 4.4 IR / Artifact

Intermediate products of parsing, normalization, lowering, compilation, or
execution preparation.

Representation rule:

- should be an IR class or named structured artifact container

Examples:

- parsed circuit
- normalized circuit
- pulse IR
- executable lowered model

### 4.5 Result

Objective outputs directly produced by execution.

Representation rule:

- must be a typed result class/dataclass

Examples:

- `Trajectory`
- `RunResult`

### 4.6 Derived Analysis

Postprocessed summaries and analysis products derived from results.

Representation rule:

- must be a typed analysis/result class

Examples:

- `AnalysisResult`
- `ReadoutAnalysis`
- `IQAnalysis`

### 4.7 Metadata

Non-primary annotations, debug notes, provenance helpers, or extension payloads.

Representation rule:

- leaf `dict` inside a typed parent is acceptable

Examples:

- `metadata`
- `extras`
- backend/engine option bags

## 5. Responsibilities of the Main Objects

### 5.1 Model

`Model` is the top-level user-facing workflow container.

`Model` must contain only:

- stable configuration
- stable registries
- lightweight session state
- run index / run collection
- optional metadata needed to navigate the model as a whole

`Model` must not directly own per-run compiled artifacts as top-level fields.

Bad examples:

- `model.circuit` when multiple runs may exist
- `model.normalized_circuit` as a global mutable singleton
- `model.spec` if the actual spec is run-scoped
- `model.out_dir` if it really means "last run output directory" without saying so

If legacy compatibility requires such fields, they must be clearly treated as
temporary compatibility fields and must not become the primary access path.

### 5.2 ModelConfig

Configuration belongs to the model-wide config layer:

- `task`
- `device`
- `pulse`
- `solvers`
- `analysers`

These are editable inputs, not execution outputs.

Agents must not mix runtime artifacts into config objects.

All first-class config categories must be typed.

Required target shape:

- `task: WorkflowTaskConfig`
- `device: WorkflowDeviceConfig`
- `pulse: WorkflowPulseConfig`
- `solvers: dict[str, WorkflowSolverConfig]`
- `analysers: dict[str, DefaultAnalyserConfig]`

### 5.3 ModelState

`ModelState` is lightweight session state only.

Allowed examples:

- selected/default solver
- selected/default analyser
- last executed run id
- current output directory pointer

Not allowed:

- full compiled models
- trajectories
- analysis payloads
- pulse IR

### 5.4 ModelRun

A run is the authoritative home for anything unique to one execution of one
solver/study combination.

`ModelRun` should logically contain:

- run identity
- runtime task
- compiled artifacts
- factual run result

If an object changes when `solver_id`, `study_name`, or `study_index` changes,
it almost certainly belongs under the run.

### 5.5 RunArtifacts

Compiled and intermediate artifacts must live together in a dedicated run-scoped
container.

Allowed examples:

- parsed circuit
- normalized circuit
- compile report
- pulse IR
- executable lowered model
- `ModelSpec`
- decoder outputs
- timings

These are not user config and not final analysis outputs.

Target internal shape:

```text
RunArtifacts
|- circuit
|- normalized_circuit
|- compile_report
|- pulse_ir
|- executable_model
|- model_spec: ModelSpec
|- decoder_outputs
`- timings
```

### 5.6 RunResult

`RunResult` stores factual execution output only.

Allowed examples:

- trajectory
- run provenance
- stable result identifier

`RunResult` should not be used as a general-purpose bag of unrelated execution
metadata.

Target internal shape:

```text
RunResult
|- result_id: str
|- trajectory: Trajectory
|- provenance: RunProvenance
`- schema_version: str
```

This object represents what the solver factually produced.
It is not the correct home for compile-stage artifacts or for arbitrary runtime
bags.

`Trajectory` should be treated as:

```text
Trajectory
|- schema_version: str
|- engine: str
|- times: list[float]
|- wave_function
|- density_matrix
|- classical
|- measurements
`- metadata
```

Where:

- `wave_function` and `density_matrix` are optional quantum-state payloads
- `classical` stores classical/readout-side time-dependent channels
- `measurements` stores measurement-side raw outputs or structured records
- `metadata` stores non-primary annotations and descriptions

`RunProvenance` should be treated as:

```text
RunProvenance
|- solver_id: str
|- study_name: str | None
|- study_index: int | None
|- spec_ref: str | None
`- plan_ref: str | None
```

### 5.7 ModelAnalysis

`ModelAnalysis` stores derived postprocessing output from one analyser applied
to one or more runs.

Analyses belong to the model-level analysis collection, not under `ModelRun`.

Storage shape:

```text
Model
`- analyses: dict[str, ModelAnalysis]
   `- <analysis_id>: ModelAnalysis
```

Target internal shape:

```text
ModelAnalysis
|- analysis_id: str
|- analyser_id: str
|- input_run_ids: list[str]
|- scope: AnalysisScope
|- output: AnalysisOutput
`- schema_version: str
```

`AnalysisOutput` should be treated as:

```text
AnalysisOutput
|- metrics: MetricsOutput | None
|- readout: ReadoutAnalysis | None
`- iq: IQAnalysis | None
```

`MetricsOutput` should be treated as:

```text
MetricsOutput
`- metric_items: dict[str, MetricSeries]
   `- <metric_name>: MetricSeries
      |- times: list[float]
      `- values: list[float]
```

`ReadoutAnalysis` should be treated as:

```text
ReadoutAnalysis
|- signals
|- demodulation
`- shots: list[ShotData]
```

`IQAnalysis` should be treated as:

```text
IQAnalysis
|- centroids: dict[str, complex]
|- confusion_matrix
|- assignment_fidelity: float
|- noise_sigma: float
`- snr: float
```

The ownership rule for analysis is:

- `ModelAnalysis` is derived from one or more `RunResult`s
- analysis storage is model-level because its dependency set may span runs
- even a single-run analysis should still declare `input_run_ids=[run_id]`
- analysis scope must be explicit rather than inferred from storage position

## 6. Canonical Home of Core Concepts

Agents must treat the following as hard placement rules.

### 6.1 ModelSpec

`ModelSpec` is the engine-neutral executable model description.

Its canonical home is:

`model.runs[run_id].artifacts.model_spec`

Rules:

- there must be exactly one authoritative runtime `ModelSpec` per run
- do not simultaneously treat `model.spec` and
  `runtime_metadata["model_spec"]` as co-equal sources of truth
- if compatibility requires duplicates during migration, one location must be
  explicitly marked as deprecated/read-only

### 6.2 WorkflowTask

`WorkflowTask` is the canonical run input contract.

Its canonical home is:

`model.runs[run_id].runtime_task`

It may be derived from model config, but after derivation it is run-scoped.

### 6.3 Circuit and Normalized Circuit

Parsed and normalized circuits are run artifacts.

Canonical home:

- `model.runs[run_id].artifacts.circuit`
- `model.runs[run_id].artifacts.normalized_circuit`

They must not be modeled as global truth for the entire `Model` when multiple
runs can exist.

### 6.4 Pulse Config, Pulse IR, and Pulse Outputs

Pulse must be split into three different architectural layers.

1. Pulse config
Typed workflow-level input config.

Canonical home:

`model.config.pulse: WorkflowPulseConfig`

2. Pulse IR
Typed intermediate representation generated during lowering.

Canonical home:

`model.runs[run_id].artifacts.pulse_ir`

3. Pulse-generated outputs
Run-scoped samples, waveforms, files, or derived artifacts.

Canonical home:

- typed artifact fields in `RunArtifacts` when needed in memory
- persisted artifact files under the run output directory when file-backed

Agents must not:

- use one raw dict shape to represent all three pulse layers
- store pulse config and pulse IR in the same container
- treat pulse IR as user-editable config

### 6.5 Executable Model

Lowered executable models are compile-stage artifacts, not top-level model
state.

Canonical home:

`model.runs[run_id].artifacts.executable_model`

### 6.6 Trajectory

Trajectory is factual solver output.

Canonical home:

`model.runs[run_id].result.trajectory`

### 6.7 Decoder Outputs

Decoder outputs belong to the same run that produced them.

Canonical home:

`model.runs[run_id].artifacts.decoder_outputs`

### 6.8 Analysis Outputs

Analyser outputs belong here:

`model.analyses[analysis_id]`

Each analysis must explicitly declare which runs it depends on:

- `input_run_ids: [run_id]` for single-run analysis
- `input_run_ids: [run_id_1, run_id_2, ...]` for multi-run analysis
- `scope` describing whether it is single-run, solver-level, study-level,
  aggregate, comparison, or another explicit analysis scope

Agents must make the distinction visible in the structure itself:

- factual execution output lives in `result`
- derived postprocessing lives in model-level `analyses`
- compile/lowering intermediates live in `artifacts`

## 7. ModelSpec Internal Structure

`ModelSpec` is the core domain model passed toward execution engines.

It should retain the following internal structure:

```text
ModelSpec
|- circuit
|- solver
|- time
|- frame
|- system
|- hamiltonian
|- noise
|- readout
|- analysis_request
|- study
`- metadata
```

Responsibilities:

- `circuit`: normalized circuit-side description
- `solver`: engine-neutral solver request
- `time`: timestep/end-time grid
- `frame`: frame and rotating-wave choices
- `system`: qubits, resonators, couplings, structure
- `hamiltonian`: controls and coupling terms
- `noise`: selected noise model and channels
- `readout`: readout protocol and chain description
- `analysis_request`: analyser-relevant runtime analysis request
- `study`: step-level study context and selected primary step
- `metadata`: non-primary technical details that do not redefine domain meaning

Agents must not hollow out `ModelSpec` into an unstructured dict.

## 8. Type System Rules: Class vs Dataclass vs Dict vs IR

Agents must follow the type rules in this section whenever adding or changing
data structures.

### 8.1 Default Rule

Default to a typed object.

Do not default to `dict[str, Any]`.

Use:

- dataclass or schema class for stable domain/state/config objects
- typed IR class for compile/lowering/executable intermediate representations
- `dict` only for bounded extension points, external payload interop, or
  transitional compatibility layers

### 8.2 What Must Be Typed

The following categories must be represented by classes or dataclasses, not raw
dicts:

- model-wide configuration
- run identity and run state
- runtime task contracts
- engine-neutral domain models
- factual execution results
- user-facing analysis results
- compile/lowering artifacts that are used across subsystem boundaries
- persisted manifests and provenance objects

Concrete examples that must be typed:

- `Model`
- `ModelConfig`
- `ModelState`
- `ModelRun`
- `RunIdentity`
- `RunArtifacts`
- `WorkflowTaskConfig`
- `WorkflowDeviceConfig`
- `WorkflowPulseConfig`
- `WorkflowSolverConfig`
- `DefaultAnalyserConfig`
- `WorkflowTask`
- `ModelSpec`
- `Trajectory`
- `RunResult`
- `ModelAnalysis`
- `AnalysisOutput`
- manifest/provenance classes

### 8.3 What Kind of Type to Use

Use the following decision rules.

#### A. Use a schema/dataclass when:

- the object is part of the public or semi-public contract
- the object is persisted
- the object crosses layer boundaries
- the object has stable semantic fields
- the object represents a domain concept

Examples:

- `ModelSpec`
- `WorkflowTask`
- `Trajectory`
- `ModelAnalysis`

#### B. Use an IR class when:

- the object is an intermediate representation produced by compilation,
  lowering, or execution preparation
- the object has stage-specific structure not intended as a user config schema
- the object is rich enough that repeated dict access would be brittle

Examples:

- pulse IR
- executable lowered model
- normalized circuit IR

#### C. Use a plain `dict` only when:

- the payload is intentionally extensible
- its schema is not owned by this layer
- it is leaf-level metadata, not a structural object

Examples:

- `metadata`
- `extras`
- backend-specific options
- engine-specific options
- decoder option bags

But even here, the containing object must still be typed.

### 8.4 Typed Container, Dict Leaves

A common acceptable pattern is:

- typed outer object
- small `dict` leaf fields for open-ended details

Example:

```text
WorkflowPulseConfig
|- acquisition: PulseAcquisitionConfig
|- timing: PulseTimingConfig
|- channels: dict[str, PulseChannelConfig]
`- extras: dict[str, Any] | None
```

This is acceptable because the structure is typed and only the intentionally
open extension leaf remains a dict.

The inverse pattern is not acceptable:

- raw dict outer object
- many convention-based nested sections pretending to be a schema

### 8.5 When Dict Is Allowed

`dict` is allowed only in these cases:

1. External config payload sections with genuinely open-ended keys
2. Metadata that is explicitly non-authoritative and non-core
3. Plugin or extension payloads whose schema is intentionally open
4. Transitional compatibility when migrating legacy structures
5. Small localized parameter bags at subsystem edges

If a `dict` becomes:

- read by multiple modules
- persisted as part of the main model contract
- validated by convention
- accessed via repeated hard-coded keys

it must be promoted to a typed structure.

### 8.6 Dict Leaves That Are Explicitly Acceptable

The following kinds of fields may remain dict-like when they are leaves inside a
typed container:

- `metadata`
- `extras`
- backend-specific options
- engine-specific options
- decoder option bags
- leaf parameter maps such as channel parameter dictionaries

These leaf dicts must satisfy all of the following:

- they are not the primary identity of the object
- they do not redefine the object's main structure
- callers can ignore them without losing the core meaning of the object

### 8.7 Signs That a Dict Must Be Promoted to a Class

If any of the following happens, the dict should become a class/dataclass:

- the same keys are read in three or more places
- validation logic appears around the dict
- defaults are repeatedly merged into the dict
- nested sections acquire stable names
- developers talk about it as a named object rather than a payload
- bugs arise from missing keys or shape ambiguity

## 9. Required Typing of Config, IR, and Result Layers

### 9.1 Config Objects

All first-class config categories must be classes/dataclasses.

Required target structure:

```text
ModelConfig
|- task: WorkflowTaskConfig
|- device: WorkflowDeviceConfig
|- pulse: WorkflowPulseConfig
|- solvers: dict[str, WorkflowSolverConfig]
`- analysers: dict[str, DefaultAnalyserConfig]
```

Important:

- `pulse` must not remain a top-level raw `dict[str, Any]` long term
- if a config object has named sections, those sections should become typed
  sub-configs unless they are truly open-ended

### 9.2 Runtime Contracts

Runtime input contracts must be typed.

Required examples:

- `WorkflowTask`
- `WorkflowInput`
- `WorkflowRunOptions`
- `WorkflowOutputOptions`
- backend config classes

### 9.3 IR Objects

The following objects should be treated as IR or structured artifacts rather
than loose dicts:

- parsed circuit
- normalized circuit
- pulse IR
- executable lowered model
- backend compile report if it becomes multi-consumer and semantically stable

If an IR object already exists as a class, reuse that class.
Do not convert it to dict just to make plumbing easier.

### 9.4 Results and Analysis Objects

Results and analyses must be typed.

Required examples:

- `Trajectory`
- `RunResult`
- `RunProvenance`
- `AnalysisOutput`
- `ModelAnalysis`
- `ReadoutAnalysis`
- `IQAnalysis`

## 10. What `runtime_metadata` Is Allowed to Be

`runtime_metadata` may exist for compatibility, but it is not the preferred home
for core program structure.

Allowed uses:

- lightweight tracing info
- debugging notes
- small execution provenance helpers
- references to already-owned structured objects

Disallowed uses:

- hiding the authoritative `ModelSpec`
- becoming the main storage for pulse IR, executable model, or circuit
- mixing config, result, and analysis into one untyped dictionary

If an object becomes important enough to be read by multiple subsystems, it
deserves a typed field or a named structured container.

## 11. Rules to Prevent Structural Drift

Agents must follow these rules before and during implementation.

### 11.1 One Concept, One Home

If two fields represent the same semantic object, one must be primary and the
other must be removed, deprecated, or treated as a read-only mirror during
migration.

Never leave two active peer sources of truth.

### 11.2 No Silent Promotion

Do not take a run-scoped object and promote it to `Model` top level just because
it is convenient for one caller.

### 11.3 No Silent Demotion

Do not take a first-class typed object and hide it inside `dict[str, Any]`
without a strong architectural reason.

### 11.4 No Mixed Scope Containers

Do not store:

- per-run results and cross-run summaries in the same map
- config and output in the same object
- execution artifacts and final user-facing results in the same layer

### 11.5 No Expansion by Metadata Dumping

If a new feature needs a real object, add a real object.

Do not keep extending `runtime_metadata`, `extras`, or generic dict payloads as
the first solution.

### 11.6 No Untyped Core Layers

Do not leave any first-class architectural layer as a top-level raw dict once
its structure is known.

This especially applies to:

- pulse config
- run artifacts
- analysis outputs
- persisted manifests

## 12. Required Agent Workflow Before Editing

Before changing architecture-sensitive code, the agent must make an internal
structure decision using the following checklist:

1. What is the semantic object being introduced or changed?
2. Is it config, runtime contract, domain model, IR, factual result, derived
   analysis, or metadata?
3. What is its single authoritative home?
4. Must it be a typed class, an IR object, or only a leaf dict?
5. Does a competing home already exist in the code?
6. If yes, should the old location be removed, migrated, or marked deprecated?

If the agent cannot answer these questions clearly, it must not improvise a new
parallel structure.

## 13. Required Agent Self-Check Before Finishing

Before finalizing changes, the agent must verify:

1. Is `ModelSpec` stored in exactly one authoritative runtime location?
2. Did any per-run object leak into `Model` top level?
3. Did any core object get hidden inside `runtime_metadata` or a generic dict?
4. Did any map begin mixing run-level and aggregate-level semantics?
5. Did any stable config/result/IR object remain a raw dict without a clear
   reason?
6. Can another developer find the canonical home of each main object without
   reading multiple files?

If the answer to any item is "no", the change is structurally incomplete.

## 14. Migration Guidance for Legacy Code

This repository may temporarily contain legacy fields that do not fully match
the target structure.

When touching such code:

- prefer moving toward the canonical structure defined here
- avoid introducing new dependencies on legacy placements
- if full migration is too large, add small compatibility shims with comments
  explaining the target direction
- do not deepen legacy ambiguity for short-term convenience

## 15. Non-Negotiable Rules

Agents must not:

- treat `model.spec` and run-scoped `model_spec` as independent truths
- use `runtime_metadata` as a permanent architecture layer
- put multi-run truth into a field that only represents the last run
- mix configuration and execution outputs in the same object
- add a new top-level field to `Model` without proving it is global, stable, and
  not run-scoped
- leave a first-class config category as a top-level raw dict once its structure
  is known
- replace a typed IR object with a convenience dict
- use a raw dict as the primary definition of pulse config, run artifacts, or
  analysis outputs

Agents should prefer:

- typed structures over raw dictionaries
- typed outer containers with dict leaves only where extensibility is intended
- explicit containers over convenience scattering
- run-scoped ownership for execution artifacts
- narrow, named compatibility layers during migration

## 16. Short Agent Prompt Version

If an agent needs a concise rule summary, use this:

```text
Keep qsim architecture stable.

One concept has one authoritative home.
Global config stays on the model config layer.
Per-run inputs, artifacts, and factual results stay under the run.
Analyses live at model level and explicitly reference one or more runs.
ModelSpec is a run-scoped artifact, not a floating global object.
Use typed config/domain/result objects by default.
Use IR classes for compile/lowering artifacts.
Allow dicts only for bounded metadata, options, or extension leaves.
Do not hide important structure inside runtime_metadata or raw dicts.
Do not mix single-run data with aggregate summaries.
If you find legacy duplication, move toward one canonical structure instead of
adding a third place.
```
