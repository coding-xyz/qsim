# [PULSE-P1] Lowering Scheduling Policy: Serial / Parallel / Hybrid

## Status
- Status: Done
- Priority: P1
- Closed on: 2026-03-03

## Goal
Turn scheduling from an implicit lowering implementation detail into an explicit user-selectable policy, with enough metadata to explain why operations do or do not overlap.

## Delivered
- Added scheduling engine in [scheduling.py](/d:/超导量子计算机噪声抑制/qsim/src/qsim/backend/scheduling.py).
- Added explicit policies:
  - `serial`
  - `parallel`
  - `hybrid`
- Added reset feedback scheduling control:
  - `parallel`
  - `serial_global`
- Exposed policy controls through:
  - [visualize.py](/d:/超导量子计算机噪声抑制/qsim/src/qsim/pulse/visualize.py)
  - [notebook.py](/d:/超导量子计算机噪声抑制/qsim/src/qsim/ui/notebook.py)
  - [cli.py](/d:/超导量子计算机噪声抑制/qsim/src/qsim/ui/cli.py)
- Added schedule debug metadata in [lowering.py](/d:/超导量子计算机噪声抑制/qsim/src/qsim/backend/lowering.py), including layer ids, timing, resource conflicts, and reset feedback mode.
- Added regression coverage in [test_pulse_catalog.py](/d:/超导量子计算机噪声抑制/qsim/tests/test_pulse_catalog.py) and [test_pulse_visualize.py](/d:/超导量子计算机噪声抑制/qsim/tests/test_pulse_visualize.py).

## Policy Semantics
- `serial`: preserves the previous simple serial scheduling behavior.
- `parallel`: overlaps resource-disjoint operations when qubit, coupler, and readout resources do not conflict.
- `hybrid`: parallelizes within compatible local regions while preserving a more conservative cross-family schedule.
- eset_feedback_policy=serial_global`: keeps reset measure/deplete aligned but serializes conditional feedback pulses globally.

## Acceptance
- Users can explicitly select scheduling behavior.
- Disjoint `CZ` operations can overlap under `parallel`.
- Shared-resource conflicts remain serialized and are explained in metadata.
- eset` feedback policy is configurable and externally reachable.
- Scheduling decisions are inspectable through exported metadata.

## Validation
- Command:
```bash
pytest -q -p no:cacheprovider tests/test_pulse_catalog.py tests/test_pulse_visualize.py
```
- Result at close: `17 passed`

## Notes
- The default path remains compatible with existing serial behavior unless the user opts into other policies.
- This issue stops short of a full hardware-controller microarchitecture model; it provides a practical scheduling layer for the current pulse stack.

