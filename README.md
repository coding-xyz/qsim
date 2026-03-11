# qsim

qsim is a workflow-first quantum simulation project with reproducible artifacts, QEC pipeline integration, and documentation automation.

## What It Supports

- Circuit import/export (`OpenQASM`, optional Qiskit adapters)
- Compile + lowering pipeline (`CircuitIR -> PulseIR -> ExecutableModel -> ModelSpec`)
- Simulation engines (QuTiP and Julia placeholders)
- QEC pipeline:
  - syndrome extraction
  - prior builders (`stim|cirq|mock|auto`)
  - decoders (`mwpm|bp|mock`)
  - decoder sweep/eval (parallel, retry, resume)
- Analysis pipeline:
  - legacy budget (`error_budget_v2.json`)
  - Pauli+/Kraus-oriented outputs
    - `scaling_report.json`
    - `error_budget_pauli_plus.json`
    - `component_ablation.csv`

## Quick Start (CLI)

```bash
qsim run-task --task-config tasks/demo.json
```

Optional runtime overrides:

```bash
qsim run-task --task-config tasks/demo.json \
  --out runs/demo_override \
  --session-dir runs/session \
  --session-auto-commit \
  --session-kinds settings,timings,logical_error
```

## Complete QEC Demo (Python)

```python
from pathlib import Path

from qsim.workflow import (
    WorkflowFeatureFlags,
    WorkflowInput,
    WorkflowOutputOptions,
    WorkflowRunOptions,
    WorkflowTask,
    run_task,
)

qasm = Path("examples/bell.qasm").read_text(encoding="utf-8")
task = WorkflowTask(
    input=WorkflowInput(
        qasm_text=qasm,
        backend_path="examples/backend.yaml",
        out_dir="runs/demo_qec_complete",
    ),
    run=WorkflowRunOptions(
        prior_backend="stim",
        decoder="bp",
        decoder_options={"max_iter": 4, "damping": 0.4},
        qec_engine="auto",
    ),
    features=WorkflowFeatureFlags(
        decoder_eval=True,
        eval_decoders=["mwpm", "bp", "mock"],
        eval_seeds=[11, 12],
        eval_option_grid=[{}, {"max_iter": 2, "damping": 0.4}],
        eval_parallelism=2,
        eval_retries=1,
        eval_resume=True,
        pauli_plus_analysis=True,
        pauli_plus_code_distances=[3, 5],
        pauli_plus_shots=1000,
    ),
    output=WorkflowOutputOptions(
        persist_artifacts=True,
        export_dxf=False,
    ),
)
result = run_task(task)
print(result["runtime"]["out_dir"])
```

Expected key artifacts:

- `syndrome_frame.json`, `prior_model.json`, `prior_samples.npz`, `decoder_output.json`, `logical_error.json`
- `decoder_eval_report.json`, `decoder_eval_table.csv`, `figures/decoder_pareto.png`, `batch_manifest.json`, `resume_state.json`
- `figures/sensitivity_heatmap.png`
- `scaling_report.json`, `error_budget_pauli_plus.json`, `component_ablation.csv`
- `error_budget_v2.json` (legacy compatibility)
- `run_manifest.json`

## Documentation

```bash
pip install -e .[docs]
mkdocs serve
```

- Repository text encoding policy: use UTF-8 for source, docs, issues, and configuration files.
- Editor and Git normalization rules live in `.editorconfig` and `.gitattributes`.
- Markdown sources: `docs/src/`
- Wiki entry: `docs/src/WIKI.md`

## Text Encoding

- Use UTF-8 for all text files in the repository.
- Do not hand-edit generated site output under `docs/site/`.
- When code changes affect behavior or API, update related docstrings and `docs/` content in the same change.

## Pre-commit Checks

Install the development hook tooling:

```bash
pip install -e .[dev]
pre-commit install
```

Run all checks manually:

```bash
pre-commit run --all-files
```

Current automated checks cover:

- UTF-8 validation for common text files
- blocking accidental edits under `docs/site/`
- merge-conflict markers
- YAML validation
- final newline, trailing whitespace, and LF normalization
- QEC chapter: `docs/src/wiki/qec_analysis.md`
- Generated website: `docs/site/`
- API reference is generated from source docstrings during the MkDocs build

## Standard Update Workflow

Use the scripted process for synchronized code/doc updates:

- Script: `scripts/run_docs_update_workflow.ps1`
- Prompt template: `scripts/codex_prompt_docs_update.md`

## Issue Management

All issue markdown files are organized under:

- `issues/`
- index: `issues/README.md`

## Notes

- Current QEC support is **offline analysis only**.
- Real-time decoding (streaming syndrome -> control feedback) is **not online yet**.
- Current gate-to-pulse mapping catalog can be exported with `python scripts/pulse_gate_map_report.py --format json --out runs/tmp/pulse_gate_map.json`.
