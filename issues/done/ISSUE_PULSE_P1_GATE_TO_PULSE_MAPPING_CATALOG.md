# [PULSE-P1] Gate-to-Pulse Mapping Catalog

## Status
- Status: Done
- Priority: P1
- Closed on: 2026-03-03

## Goal
Make the mapping from logical operations to pulse recipes explicit, inspectable, exportable, and testable instead of leaving it only inside lowering code.

## Delivered
- Added shared recipe and mapping logic in [catalog.py](/d:/超导量子计算机噪声抑制/qsim/src/qsim/pulse/catalog.py).
- Switched lowering to consume the same catalog definitions instead of duplicating the mapping implicitly in [lowering.py](/d:/超导量子计算机噪声抑制/qsim/src/qsim/backend/lowering.py).
- Added export script [pulse_gate_map_report.py](/d:/超导量子计算机噪声抑制/qsim/scripts/pulse_gate_map_report.py).
- Added regression coverage in [test_pulse_catalog.py](/d:/超导量子计算机噪声抑制/qsim/tests/test_pulse_catalog.py).
- Added README entry for generating and inspecting the exported mapping in [README.md](/d:/超导量子计算机噪声抑制/qsim/README.md).

## Current Mapping Surface
- `x`, `sx`, `h`: `XY_*` pulse recipes.
- `z`, z`: `Z_*` pulse recipes.
- `cz`: `TC_*` pulse recipe.
- `cx`: combined `XY_*` and `TC_*` recipe.
- `measure`: O_*` readout recipe.
- eset`: staged recipe including eset_measure`, eset_deplete`, feedback latency, and eset_conditional_pi`.
- `barrier`: no-pulse, no-time-advance semantic entry.

## Acceptance
- Catalog output distinguishes operation semantics from pulse `shape`.
- `measure` and eset` stage structure is explicit.
- Shared recipes such as `x/sx/h` are visible in exported output instead of being hidden in code.
- Export is available as a standalone artifact.
- Tests fail if catalog and lowering drift apart.

## Validation
- Command:
```bash
pytest -q -p no:cacheprovider tests/test_pulse_catalog.py tests/test_pulse_visualize.py
```
- Result at close: `17 passed`

## Artifacts
- [pulse_gate_map.json](/d:/超导量子计算机噪声抑制/qsim/runs/tmp/pulse_gate_map.json)

## Notes
- This issue did not require a `PulseIR` schema redesign.
- The catalog is now the single practical source of truth for default gate-to-pulse mapping in the current stack.

