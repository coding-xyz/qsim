import math

from qsim.common.schemas import (
    AnalysisRequestSpec,
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
from qsim.engines.qutip import QuTiPEngine


def test_qutip_heom_runs_one_over_f_bath():
    model = ModelSpec(
        solver=SolverSpec(
            mode="heom",
            engine="qutip",
            options={
                "backend_options": {"heom": {"max_depth": 1, "nterms": 2}},
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
    assert len(trajectory.times) == 3
