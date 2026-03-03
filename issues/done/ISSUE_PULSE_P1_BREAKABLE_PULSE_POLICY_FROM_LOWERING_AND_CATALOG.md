# [PULSE-P1] Breakable Pulse Policy From Lowering and Catalog

## Status
- Status: Done
- Priority: P1
- Closed on: 2026-03-03

## Goal
Define pulse breakability in the semantic recipe layer instead of guessing it inside visualization code.

## Delivered
- Added breakability metadata in [catalog.py](/d:/超导量子计算机噪声抑制/qsim/src/qsim/pulse/catalog.py), including:
  - `breakable`
  - `break_keep_head_ns`
  - `break_keep_tail_ns`
  - `break_kind`
  - `break_stage`
- Propagated break hints through lowering into pulse instances used by visualization.
- Restricted automatic break generation in [visualize.py](/d:/超导量子计算机噪声抑制/qsim/src/qsim/pulse/visualize.py) to explicitly breakable pulses only.
- Kept gate pulses non-breakable by default.
- Constrained break windows to pulse interior segments using shared keep-head and keep-tail constants.
- Renamed user-facing terminology toward `break` while retaining compatibility aliases for older `fold` API names.
- Added regression coverage in [test_pulse_visualize.py](/d:/超导量子计算机噪声抑制/qsim/tests/test_pulse_visualize.py).

## Current Policy
- Breakable by default:
  - `measure` readout pulses
  - selected `reset` stages such as `reset_measure` and `reset_deplete`
- Not breakable by default:
  - single-qubit gate pulses
  - two-qubit gate pulses
  - any pulse without explicit breakability metadata
- A break window is valid only if:
  - it stays inside the pulse interior
  - head and tail keep regions are preserved
  - the candidate interval does not cover other non-breakable activity

## Acceptance
- Visualization no longer treats "long pulse" as equivalent to "breakable pulse".
- Breakability comes from lowering and catalog semantics.
- Gate timing is protected from accidental mid-pulse breaks.
- Multi-channel conflict checks prevent breaks that would hide other operations.

## Validation
- Command:
```bash
pytest -q -p no:cacheprovider tests/test_pulse_catalog.py tests/test_pulse_visualize.py
```
- Result at close: `17 passed`

## Notes
- Compatibility aliases remain for old `fold` names, but the preferred public terminology is now `break`.
- Future DD support can reuse the same semantic breakability mechanism without pushing more heuristics into visualization.
