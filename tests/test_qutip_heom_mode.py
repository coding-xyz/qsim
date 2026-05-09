import math

import pytest

from qsim.common.schemas import (
    AnalysisRequestSpec,
    CollapseChannelSpec,
    ExecutableModel,
    FrameSpec,
    HamiltonianSpec,
    ModelSpec,
    NoiseSpec,
    SolverSpec,
    StochasticChannelSpec,
    SystemQubitSpec,
    SystemSpec,
    TimeSpec,
)
from qsim.backend.model.build import DefaultModelBuilder
from qsim.engines.qutip import QuTiPEngine
from qsim.engines.qutip.modes.heom import _check_heom_size, _estimate_ado_count, _one_over_f_exponents


def test_qutip_heom_runs_one_over_f_bath():
    model = ModelSpec(
        solver=SolverSpec(
            mode="heom",
            engine="qutip",
            options={
                "backend_options": {
                    "heom": {
                        "max_depth": 1,
                        "bath_expansion": {"one_over_f": {"method": "multi_lorentzian", "nterms": 2, "grid": "log"}},
                    }
                },
                "qutip_options": {"store_states": True, "progress_bar": False},
            },
        ),
        time=TimeSpec(dt_s=2.0e-8, t_end_s=4.0e-8),
        frame=FrameSpec(mode="rotating", reference="carrier", rwa=True),
        system=SystemSpec(
            model_type="qubit_network",
            simulation_level="qubit",
            dimension=2,
            qubits=SystemQubitSpec(num_qubits=1, qubit_freqs_Hz=[0.0], qubit_omega_rad_s=[0.0]),
        ),
        hamiltonian=HamiltonianSpec(),
        noise=NoiseSpec(
            selected_model="one_over_f",
            stochastic_channels=[
                StochasticChannelSpec(
                    q=0,
                    one_over_f_amp_Hz=1.0e4,
                    one_over_f_amp_rad_s=2.0 * math.pi * 1.0e4,
                    one_over_f_fmin=1.0e3,
                    one_over_f_fmax=1.0e5,
                )
            ],
        ),
        analysis_request=AnalysisRequestSpec(
            config={"trajectory": {"quantum": "density_matrix", "save_times": "all", "save_final_state": True}}
        ),
    )

    trajectory = QuTiPEngine().run(model)

    assert trajectory.engine == "qutip"
    assert trajectory.metadata["solver"] == "heom"
    assert trajectory.metadata["heom"]["bath_count"] == 1
    assert trajectory.metadata["heom"]["baths"][0]["num_exponents"] == 2
    assert trajectory.metadata["heom"]["bath_expansion"]["one_over_f"]["nterms"] == 2
    assert trajectory.metadata["heom"]["baths"][0]["expansion_method"] == "multi_lorentzian"
    assert trajectory.metadata["heom"]["baths"][0]["coupling_operator"] == "0.5*sigma_z"
    assert trajectory.metadata["heom"]["approximation"].startswith("classical colored dephasing")
    assert trajectory.metadata["heom"]["fit_method"].startswith("heuristic log-bin")
    assert trajectory.metadata["heom"]["units"]["time_unit"] == "s"
    assert trajectory.metadata["heom"]["hilbert_dim"] == 2
    assert trajectory.metadata["heom"]["liouville_dim"] == 4
    assert len(trajectory.times) == 3


def test_qutip_heom_keeps_markovian_collapse_channels():
    model = ModelSpec(
        solver=SolverSpec(
            mode="heom",
            engine="qutip",
            options={
                "backend_options": {"heom": {"max_depth": 1, "nterms": 1}},
                "qutip_options": {"store_states": True, "progress_bar": False},
            },
        ),
        time=TimeSpec(dt_s=2.0e-8, t_end_s=4.0e-8),
        frame=FrameSpec(mode="rotating", reference="carrier", rwa=True),
        system=SystemSpec(
            model_type="qubit_network",
            simulation_level="qubit",
            dimension=2,
            qubits=SystemQubitSpec(num_qubits=1, qubit_freqs_Hz=[0.0], qubit_omega_rad_s=[0.0]),
        ),
        hamiltonian=HamiltonianSpec(),
        noise=NoiseSpec(
            selected_model="one_over_f",
            collapse_channels=[CollapseChannelSpec(target=0, kind="relaxation", rate_rad_s=1.0e5)],
            stochastic_channels=[
                StochasticChannelSpec(
                    q=0,
                    one_over_f_amp_rad_s=2.0 * math.pi * 1.0e4,
                    one_over_f_fmin=1.0e3,
                    one_over_f_fmax=1.0e5,
                )
            ],
        ),
        analysis_request=AnalysisRequestSpec(
            config={"trajectory": {"quantum": "density_matrix", "save_times": "all", "save_final_state": True}}
        ),
    )

    trajectory = QuTiPEngine().run(model)

    assert trajectory.metadata["heom"]["uses_liouvillian"] is True
    assert trajectory.metadata["heom"]["markovian_c_ops"] == 1


def test_one_over_f_log_bins_are_equal_for_alpha_one():
    ck, vk = _one_over_f_exponents(
        amp=2.0,
        fmin=1.0,
        fmax=100.0,
        exponent=1.0,
        nterms=4,
        t_end=1.0,
    )

    assert sum(ck) == pytest.approx(4.0)
    assert max(ck) - min(ck) < 1.0e-12
    assert len(vk) == 4


def test_one_over_f_rms_hz_lowers_to_rad_s_correlation_normalization():
    rms_Hz = 4.0e4
    ck, _vk = _one_over_f_exponents(
        amp=2.0 * math.pi * rms_Hz,
        fmin=5.0e3,
        fmax=8.0e5,
        exponent=1.0,
        nterms=8,
        t_end=1.0e-6,
    )

    assert sum(ck) == pytest.approx((2.0 * math.pi * rms_Hz) ** 2)


def test_heom_ado_estimate_uses_hierarchy_combination_count():
    assert _estimate_ado_count(num_exponents=30, max_depth=3) == math.comb(33, 3)


def test_heom_size_estimate_includes_liouville_variables():
    class H0:
        shape = (8, 8)

    class System:
        H = [H0()]

    size = _check_heom_size(
        summaries=[{"num_exponents": 3}],
        max_depth=2,
        opts={"max_ados": 0},
        system=System(),
    )

    assert size["estimated_ados"] == math.comb(5, 2)
    assert size["hilbert_dim"] == 8
    assert size["liouville_dim"] == 64
    assert size["estimated_complex_variables"] == 640


def test_qutip_heom_accepts_explicit_dephasing_coupling_convention():
    model = ModelSpec(
        solver=SolverSpec(
            mode="heom",
            engine="qutip",
            options={
                "backend_options": {"heom": {"max_depth": 1, "nterms": 1, "dephasing_coupling": "sigma_z"}},
                "qutip_options": {"store_states": True, "progress_bar": False},
            },
        ),
        time=TimeSpec(dt_s=2.0e-8, t_end_s=4.0e-8),
        frame=FrameSpec(mode="rotating", reference="carrier", rwa=True),
        system=SystemSpec(
            model_type="qubit_network",
            simulation_level="qubit",
            dimension=2,
            qubits=SystemQubitSpec(num_qubits=1, qubit_freqs_Hz=[0.0], qubit_omega_rad_s=[0.0]),
        ),
        hamiltonian=HamiltonianSpec(),
        noise=NoiseSpec(
            selected_model="one_over_f",
            stochastic_channels=[
                StochasticChannelSpec(
                    q=0,
                    one_over_f_amp_rad_s=2.0 * math.pi * 1.0e4,
                    one_over_f_fmin=1.0e3,
                    one_over_f_fmax=1.0e5,
                )
            ],
        ),
        analysis_request=AnalysisRequestSpec(
            config={"trajectory": {"quantum": "density_matrix", "save_times": "all", "save_final_state": True}}
        ),
    )

    trajectory = QuTiPEngine().run(model)

    assert trajectory.metadata["heom"]["baths"][0]["coupling_operator"] == "sigma_z"


def test_qutip_heom_shared_source_uses_one_shared_bath():
    model = ModelSpec(
        solver=SolverSpec(
            mode="heom",
            engine="qutip",
            options={
                "backend_options": {"heom": {"max_depth": 1, "nterms": 1}},
                "qutip_options": {"store_states": True, "progress_bar": False},
            },
        ),
        time=TimeSpec(dt_s=2.0e-8, t_end_s=4.0e-8),
        frame=FrameSpec(mode="rotating", reference="carrier", rwa=True),
        system=SystemSpec(
            model_type="qubit_network",
            simulation_level="qubit",
            dimension=4,
            qubits=SystemQubitSpec(num_qubits=2, qubit_freqs_Hz=[0.0, 0.0], qubit_omega_rad_s=[0.0, 0.0]),
        ),
        hamiltonian=HamiltonianSpec(),
        noise=NoiseSpec(
            selected_model="source_ir",
            stochastic_channels=[
                StochasticChannelSpec(
                    q=0,
                    id="shared_flux_bias",
                    kind="one_over_f",
                    targets=[0, 1],
                    operator="sigma_z_over_2",
                    one_over_f_amp_rad_s=2.0 * math.pi * 1.0e4,
                    one_over_f_fmin=1.0e3,
                    one_over_f_fmax=1.0e5,
                    correlation={"type": "shared"},
                )
            ],
        ),
        analysis_request=AnalysisRequestSpec(
            config={"trajectory": {"quantum": "density_matrix", "save_times": "all", "save_final_state": True}}
        ),
    )

    trajectory = QuTiPEngine().run(model)

    assert trajectory.metadata["heom"]["bath_count"] == 1
    assert trajectory.metadata["heom"]["baths"][0]["source_id"] == "shared_flux_bias"
    assert trajectory.metadata["heom"]["baths"][0]["targets"] == [0, 1]


@pytest.mark.parametrize("solver", ["me", "mcwf"])
def test_qutip_me_and_mcwf_run_source_level_markovian_noise(solver):
    model = DefaultModelBuilder().build(
        ExecutableModel(solver=solver, metadata={"num_qubits": 1}),
        hw={
            "components": [
                {
                    "id": "q0",
                    "type": "transmon",
                    "parameters": {"freq_Hz": 0.0},
                    "noise": {
                        "sources": [
                            {
                                "id": "q0_T1",
                                "kind": "markovian",
                                "operator": "lowering",
                                "rate": {"T1_s": 1.0e-6},
                            }
                        ]
                    },
                }
            ]
        },
        noise={},
        pulse_samples={},
        solver_run={
            "t_end_s": 2.0e-9,
            "dt_s": 1.0e-9,
            "ntraj": 1,
            "qutip_options": {"store_states": True, "progress_bar": False},
        },
    )

    trajectory = QuTiPEngine().run(model)

    assert trajectory.metadata["solver"] == solver
    assert model.noise.sources[0].id == "q0_T1"
    assert len(model.noise.collapse_channels) == 1
