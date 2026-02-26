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
qsim run --qasm examples/bell.qasm --backend examples/backend.yaml --out runs/demo
```

## Complete QEC Demo (Python)

```python
from pathlib import Path
from qsim.ui.notebook import run_workflow

qasm = Path("examples/bell.qasm").read_text(encoding="utf-8")
result = run_workflow(
    qasm_text=qasm,
    backend_path="examples/backend.yaml",
    out_dir="runs/demo_qec_complete",
    persist_artifacts=True,
    export_dxf=False,
    prior_backend="stim",
    decoder="bp",
    decoder_options={"max_iter": 4, "damping": 0.4},
    decoder_eval=True,
    eval_decoders=["mwpm", "bp", "mock"],
    eval_seeds=[11, 12],
    eval_option_grid=[{}, {"max_iter": 2, "damping": 0.4}],
    eval_parallelism=2,
    eval_retries=1,
    eval_resume=True,
    pauli_plus_analysis=True,
    qec_engine="auto",
    pauli_plus_code_distances=[3, 5],
    pauli_plus_shots=1000,
)
print(result["out_dir"])
```

Expected key artifacts:

- `syndrome_frame.json`, `prior_model.json`, `decoder_output.json`, `logical_error.json`
- `decoder_eval_report.json`, `decoder_eval_table.csv`, `batch_manifest.json`, `resume_state.json`
- `scaling_report.json`, `error_budget_pauli_plus.json`, `component_ablation.csv`
- `error_budget_v2.json` (legacy compatibility)
- `run_manifest.json`

## Documentation

```bash
pip install -e .[docs]
mkdocs serve
```

- Wiki entry: `docs/WIKI.md`
- QEC chapter: `docs/wiki/qec_analysis.md`
- API reference: `docs/api/`

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
