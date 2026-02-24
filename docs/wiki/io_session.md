# IO 与会话

## `run_workflow` 产物

典型输出：

- `circuit.json`
- `backend_config.json`
- `normalized_circuit.json`
- `compile_report.json`
- `pulse_ir.json`
- `pulse_samples.npz`
- `executable_model.json`
- `model_spec.json`
- `trace.h5`
- `observables.json`
- `report.json`
- `settings_report.json`
- `run_manifest.json`
- `timings.json`
- `timing_diagram.dxf`（可选）

## 会话存储

会话接口：

- `Session.open(path)`
- `Session.commit(kind, payload, ...)`
- `Session.get(rev_id)`

底层由 `ArtifactStore` 和 `SessionManifest` 负责版本化与索引。
