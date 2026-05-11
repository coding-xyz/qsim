# [NOISE-P0] Systematic Noise IR and Crosstalk Schema

## 0. Status
- Status: In Progress
- Owner: TBD
- Updated: 2026-05-07

## 1. Background and Goal
The current noise schema mixes several conceptual layers:

- `CollapseChannelSpec` and `PerQubitRateSpec` duplicate Markovian rate information.
- `StochasticChannelSpec` stores solver-ready expansion parameters, but does not represent the original non-Markovian noise process cleanly.
- Device-local component noise and device-level correlated/crosstalk noise are both expressed through a broad `noise` block.
- Cross-component noise channels are not first-class IR objects.

Goal: redesign noise as a layered, engine-neutral IR that can represent raw physical noise sources such as OU, 1/f, Lorentzian bumps, Markovian T1/Tphi, readout noise, and shared/correlated device noise, then lower those sources into solver-specific realizations such as Lindblad `c_ops`, stochastic traces, HEOM exponential baths, or Pauli/QEC approximations. Deterministic control crosstalk should be represented in the device schema, but it is a control-transfer effect rather than a stochastic noise source.

## 2. Proposed Direction
Split noise into three layers.

Layer 1: Device/Authored Noise

- Component-local noise lives under each device component, e.g. `device.components[].noise`.
- Device-level cross-component effects live as first-class peers of `device.components`, so all hardware-authored local and cross-component imperfections stay inside the device description.
- Use separate top-level device blocks for different physical mechanisms:
  - `device.shared_noise`: stochastic shared/common-mode noise sources, e.g. shared flux bias, substrate, global magnetic drift.
  - `device.control_crosstalk`: deterministic or noisy transfer between control channels, e.g. `XY_0` leaking into `XY_1`.
  - `device.readout_crosstalk`: measurement-chain crosstalk, shared readout noise, assignment correlations, or readout feedthrough.
- Existing top-level `noise:` remains temporarily as a compatibility alias during migration.

Layer 2: Engine-Neutral Noise IR

Use one canonical source-level record, `NoiseSourceSpec`, rather than parallel subclasses such as `ColoredNoiseSource` and `CorrelatedNoiseSource`.

Reason: “colored” and “correlated” describe different axes, not different object types.

- Time structure: white/Markovian, OU, 1/f, Lorentzian, tabulated PSD, nonstationary.
- Target structure: local, shared, pairwise correlated, matrix-correlated, channel leakage.
- Coupling structure: lowering, excitation, `sigma_z_over_2`, number, drive amplitude, readout offset.
- Realization: Lindblad, stochastic trace, HEOM exponential bath, Pauli approximation.

`NoiseSpec` is the container above all noise sources and derived solver realizations. It should not itself mean “one noise model”. It should contain:

- `sources`: canonical authored/engine-neutral `NoiseSourceSpec` records.
- `realizations`: optional derived solver-ready records, produced by lowering and normally present only in compiled plans, cached run specs, or serialized run summaries.
- `readout`: optional readout/SPAM-specific source group if needed.
- `warnings` / compatibility notes.

Authored YAML should stay source-oriented and should not expose solver realizations as normal user input. For clean hand-written files, component-local `noise:` and task-level `noise:` may be written directly as a list of source records. The loader normalizes that shorthand into IR `sources`. `realizations` should not be a second user-authored source of truth. If both sources and realizations appear, sources win unless an explicit compiled-plan mode is selected.

`NoiseSourceSpec` should carry:

- `id`: stable source id. Required for any source that may be enabled, disabled, overridden, swept, or referenced from a task/study. A missing id is allowed only for local defaults that cannot be task-overridden.
- `kind`: temporal/spectral process type, e.g. `markovian`, `ou`, `one_over_f`, `lorentzian`, `tabulated_psd`.
- `targets`: components, qubits, modes, pairs, or channels.
- `operator`: e.g. `sigma_z_over_2`, `number`, `lowering`, `drive_amplitude`, `frequency`.
- `amplitude` / `rate` / `spectrum`: model-specific physical parameters.
- `band_Hz`, `exponent`, `psd_convention`, etc. for spectral models.
- `correlation`: spatial/channel correlation, e.g. `independent`, `shared`, `matrix`, `kernel`.
- `units`: explicit source units and internal lowered units.
- `realization_hints`: optional non-binding preferences such as `prefer: heom` or `allow_sampling: true`.

`NoiseSourceSpec` is for stochastic or Markovian noise sources. Deterministic control leakage, such as a pulse on `XY_0` leaking into `XY_1`, should use a separate control crosstalk spec under `device.control_crosstalk` and lower into modified drive Hamiltonian terms, not into `c_ops`, stochastic traces, or HEOM baths.

`realization_hints` never decide the final solver path by themselves. The actual realization is selected by `run.solver_mode` and `run.backend_options`; the compiled plan or typed run summary records what was actually used.

Layer 3: Solver Realization

Lower sources into solver-ready forms:

- `LindbladRealizationSpec` for collapse operators / rates.
- `SampledProcessRealizationSpec` for stochastic traces.
- `ExponentialBathRealizationSpec` for HEOM `ck/vk` expansions.
- `PauliNoiseRealizationSpec` for QEC/Stim-like approximations.

`CollapseChannelSpec`, `StochasticChannelSpec`, and `PerQubitRateSpec` should either become compatibility realizations or be replaced by the realization specs above. `PerQubitRateSpec` should be derived metadata, not a second source of truth.

## 3. Scope
In Scope:

- Redesign `src/qsim/schemas/noise.py`.
- Add compatibility parsing for current `noise:` blocks and component-local `noise`.
- Add explicit shared noise, control crosstalk, and readout crosstalk schemas.
- Define lowering from source-level IR into current QuTiP Lindblad, SDE/stochastic, and HEOM paths.
- Update examples, especially `examples/noise_simulation_tests/task7`.
- Add docs for physical meaning, units, and solver-specific approximations.

Out of Scope:

- Perfect least-squares fitting for all spectral densities in the first implementation.
- Full calibration database integration.
- Rewriting all engines in one pass. Compatibility shims are acceptable.

## 4. Draft YAML Shape
Component-local noise, shared device noise, and crosstalk:

```yaml
device:
  components:
    - id: q0
      type: transmon
      parameters:
        freq_Hz: 5.0e9
      noise:
        - id: q0_T1
          kind: markovian
          operator: lowering
          rate:
            T1_s: 24.0e-6
        - id: q0_Tphi
          kind: markovian
          operator: sigma_z_over_2
          rate:
            Tphi_s: 30.0e-6
        - id: q0_flux_1overf
          kind: one_over_f
          operator: sigma_z_over_2
          amplitude:
            rms_Hz: 4.0e4
            definition: integrated_rms_over_band
          band_Hz: [5.0e3, 8.0e5]
          exponent: 1.0
          psd_convention: one_sided

  shared_noise:
    - id: shared_flux_bias
      kind: one_over_f
      targets: [q0, q1]
      operator: sigma_z_over_2
      amplitude:
        rms_Hz: 2.0e4
        definition: integrated_rms_over_band
      band_Hz: [10.0, 1.0e6]
      exponent: 1.0
      psd_convention: one_sided
      correlation:
        type: shared

  control_crosstalk:
    - id: drive_leakage_q0_to_q1
      kind: deterministic_control_transfer
      source_channel: XY_0
      target_channel: XY_1
      transfer:
        amplitude: 0.02
        phase_rad: 0.1

  readout_crosstalk:
    - id: ro_q0_to_q1_assignment
      kind: assignment_crosstalk
      source: q0
      target: q1
      probability:
        p_target_flip_when_source_excited: 0.03
```

Task or study-level noise override:

```yaml
noise:
  enabled_sources: [shared_flux_bias]
  overrides:
    shared_flux_bias:
      amplitude:
        rms_Hz: 5.0e4
```

Task or study-level source injection can also use the same clean list shorthand when no enable/disable/override controls are needed:

```yaml
noise:
  - id: q0_ou_case
    kind: ou
    targets: [q0]
    operator: sigma_z_over_2
    amplitude:
      sigma_Hz: 4.0e7
      tau_s: 1.2e-8
```

Override rules:

- `enabled_sources`, `disabled_sources`, and `overrides` refer to stable source ids across component-local and device-level sources.
- Sources without ids are treated as local defaults and cannot be selected or overridden from a task/study.
- `Tphi_s` means the physical off-diagonal pure-dephasing coherence time. Lowering code is responsible for choosing the collapse prefactor that is consistent with the chosen operator convention, e.g. `sigma_z`, `sigma_z_over_2`, or `number`.
- `amplitude.rms_Hz` for 1/f noise is the RMS of the physical frequency fluctuation `delta f` integrated over `band_Hz`, not the RMS of the already-lowered Hamiltonian coefficient. Lowering to angular-frequency Hamiltonian units uses `delta omega = 2*pi*delta f`; HEOM expansion coefficients for that process should normalize to `sum(ck) ~= (2*pi*rms_Hz)^2` before the coupling operator convention is applied.

Solver-specific HEOM realization:

```yaml
run:
  engine: qutip
  solver_mode: heom
  backend_options:
    heom:
      max_depth: 3
      max_ados: 5000
      max_dense_memory_mb: 512
      dephasing_coupling: auto
      bath_expansion:
        one_over_f:
          method: multi_lorentzian
          nterms: 8
          grid: log
        ou:
          method: direct_exponential
```

The source-level 1/f block defines the physical noise process. The HEOM block defines how that source is approximated for a particular solver. A supported first implementation can map `method: multi_lorentzian` and `grid: log` to the current finite OU/Lorentzian component approximation, while reserving later methods such as `least_squares_psd_fit`.

For the first HEOM implementation, `multi_lorentzian` should be documented as a finite OU/Lorentzian approximation to a classical colored dephasing process. It is not a claim that the bath is a unique or optimal quantum bath fit to the target PSD.

## 5. Migration Plan
1. Add `NoiseSourceSpec` plus realization dataclasses while keeping current `NoiseSpec` fields during migration.
2. Implement compatibility parsing:
   - `T1_s`, `T2_s`, `gamma1_Hz`, `gamma_phi_Hz` become `NoiseSourceSpec(kind=markovian, ...)`.
   - current `one_over_f_*` and `ou_*` become `NoiseSourceSpec(kind=one_over_f/ou, ...)`.
   - current `collapse_channels`, `stochastic_channels`, `per_qubit_rates` remain emitted as derived fields for existing engines.
3. Update lowering in `src/qsim/backend/model/noise.py` to produce canonical `NoiseSourceSpec` records plus derived realization fields.
4. Update QuTiP HEOM to consume source-level colored noise where available, falling back to current stochastic fields.
5. Add typed HEOM configuration and summary dataclasses instead of ad-hoc metadata:
   - `HeomSolverOptions`
   - `BathExpansionOptions`
   - `HeomBathSummary`
   - `HeomRunSummary`
   Metadata may remain only as the serialized representation of these dataclasses.
6. Add device-level lowering for at least:
   - shared dephasing source across multiple qubits.
   - deterministic control transfer/leakage between pulse channels.
   - readout assignment/feedthrough crosstalk.
7. Update examples and docs.
8. Deprecate direct authoring of `PerQubitRateSpec` as a source of truth.

## 6. Acceptance Criteria
- [x] A single canonical `NoiseSourceSpec` schema can represent Markovian T1/Tphi, OU, 1/f, Lorentzian, and shared correlated dephasing through orthogonal fields rather than overlapping subclasses.
- [x] Deterministic control transfer/crosstalk is represented separately from stochastic noise sources and lowers into pulse/control Hamiltonian terms.
- [x] Existing examples continue to parse through compatibility shims.
- [x] `CollapseChannelSpec` and HEOM bath specs are derived realizations, not the only canonical noise model; authored `sources` are authoritative unless reading an explicit compiled plan.
- [x] `PerQubitRateSpec` is clearly derived metadata or removed from source-level authoring.
- [x] Component-local noise is represented under `device.components[].noise`; shared stochastic noise is represented under `device.shared_noise`; control-channel leakage is represented under `device.control_crosstalk`; readout-chain crosstalk is represented under `device.readout_crosstalk`.
- [x] Stable source ids are required for all sources that may be enabled, disabled, overridden, swept, or referenced from task/study YAML.
- [x] 1/f source config explicitly records amplitude definition and PSD convention, e.g. `amplitude.definition: integrated_rms_over_band` and `psd_convention: one_sided`.
- [x] 1/f lowering treats `rms_Hz` as frequency-noise RMS and converts to angular units with `2*pi`; HEOM coefficient normalization is tested against `(2*pi*rms_Hz)^2`.
- [x] Markovian pure-dephasing lowering defines `Tphi_s` as the physical coherence dephasing time and handles operator-dependent prefactors explicitly.
- [x] HEOM solver config supports source-specific bath expansion options such as `bath_expansion.one_over_f.method`, `nterms`, and `grid`.
- [x] HEOM options and run summaries are represented by typed dataclasses; free-form metadata is only a serialization boundary.
- [x] QuTiP ME/MCWF/HEOM tests cover the new lowering path.
- [x] Documentation explains raw source units, internal units, and solver realization choices.

## 7. Test Plan
- Unit tests for parsing new source-level noise YAML.
- Unit tests for compatibility conversion from current task YAML.
- Unit tests for shared noise, control crosstalk, and readout crosstalk lowering.
- QuTiP integration tests:
  - Markovian-only source lowers to `c_ops`.
  - Markovian `operator: sigma_z_over_2` plus `Tphi_s` produces a Ramsey envelope with the configured physical pure-dephasing time.
  - OU/1/f source lowers to stochastic or HEOM representation.
  - 1/f HEOM lowering satisfies integrated RMS normalization, `sum(ck) ~= (2*pi*rms_Hz)^2`, within tolerance for the configured band and convention.
  - Shared source produces correlated channels, not independent per-qubit copies; for HEOM this should be one shared bath coupled to `Q = Q0 + Q1`.
  - Deterministic control transfer modifies pulse/control Hamiltonian terms and is not emitted as a stochastic channel, HEOM bath, or Lindblad collapse operator.
- Regression tests for task1-task7 examples.

## 8. Risks
- Schema migration may break existing examples if compatibility is not broad enough.
- Crosstalk can mean multiple physical mechanisms; the first schema must avoid overfitting one experiment.
- HEOM, stochastic SDE, and Pauli/QEC approximations need different realizations from the same source. The IR must keep source semantics separate from solver implementation.

## 9. References
- `src/qsim/schemas/noise.py`
- `src/qsim/backend/model/noise.py`
- `src/qsim/engines/qutip/model/collapse.py`
- `src/qsim/engines/qutip/modes/heom.py`
- `examples/noise_simulation_tests/task7/device.yaml`
