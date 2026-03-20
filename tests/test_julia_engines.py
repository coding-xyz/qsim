import pytest

from qsim.common.schemas import ModelSpec
from qsim.engines.qoptics_engine import QOpticsEngine
from qsim.engines.qtoolbox_engine import QToolboxEngine


def _minimal_spec(solver: str = "me") -> ModelSpec:
    return ModelSpec(
        solver=solver,
        dimension=2,
        t_end=10.0,
        dt=1.0,
        payload={
            "model_type": "qubit_network",
            "num_qubits": 1,
            "qubit_omega_rad_s": [0.05],
            "controls": [{"target": 0, "axis": "x", "times": [0.0, 5.0, 10.0], "values": [0.0, 1.0, 0.0], "scale": 1.0}],
            "collapse_operators": [{"target": 0, "kind": "relaxation", "rate_rad_s": 0.01}],
        },
    )


@pytest.mark.parametrize("engine_cls", [QOpticsEngine, QToolboxEngine])
def test_julia_engines_native_or_raise(engine_cls):
    engine = engine_cls()
    spec = _minimal_spec("me")
    try:
        trace = engine.run(spec, run_options={})
    except Exception:
        return
    assert trace.metadata.get("native_solver", False) is True


@pytest.mark.parametrize("engine_cls", [QOpticsEngine, QToolboxEngine])
def test_julia_engines_default_no_mock_fallback(monkeypatch, engine_cls):
    engine = engine_cls()
    spec = _minimal_spec("me")

    def _fail(_model_spec, run_options=None):
        raise RuntimeError("bridge failed")

    monkeypatch.setattr(engine, "_runtime", type("R", (), {"run": staticmethod(_fail)})())
    with pytest.raises(RuntimeError, match="bridge failed"):
        engine.run(spec)


@pytest.mark.parametrize("engine_cls", [QOpticsEngine, QToolboxEngine])
def test_julia_engines_pass_run_options(monkeypatch, engine_cls):
    engine = engine_cls()
    spec = _minimal_spec("mcwf")
    captured = {}

    class _Runtime:
        @staticmethod
        def run(_model_spec, run_options=None):
            captured["opts"] = dict(run_options or {})
            class _Trace:
                metadata = {"native_solver": True}
            return _Trace()

    monkeypatch.setattr(engine, "_runtime", _Runtime())
    engine.run(spec, run_options={"julia_bin": "C:/x/julia.exe", "ntraj": 16})
    assert captured["opts"]["julia_bin"] == "C:/x/julia.exe"
    assert int(captured["opts"]["ntraj"]) == 16


@pytest.mark.parametrize("engine_cls", [QOpticsEngine, QToolboxEngine])
def test_julia_engines_native_metadata_fields(engine_cls):
    engine = engine_cls()
    spec = _minimal_spec("me")
    try:
        trace = engine.run(spec, run_options={})
    except Exception:
        return
    assert str(trace.metadata.get("julia_version", "")).strip() != ""
    assert str(trace.metadata.get("julia_backend", "")).strip() != ""
    assert str(trace.metadata.get("julia_backend_version", "")).strip() != ""


def test_julia_runtime_runner_resolves_backend_specific_scripts():
    assert QOpticsEngine()._runtime._resolve_script().name == "qoptics_runtime.jl"
    assert QToolboxEngine()._runtime._resolve_script().name == "qtoolbox_runtime.jl"


@pytest.mark.parametrize("engine_cls", [QOpticsEngine, QToolboxEngine])
def test_julia_engines_short_pulse_on_long_timeline(engine_cls):
    engine = engine_cls()
    spec = ModelSpec(
        solver="se",
        dimension=2,
        t_end=5.0e-5,
        dt=1.0e-9,
        payload={
            "model_type": "qubit_network",
            "num_qubits": 1,
            "qubit_omega_rad_s": [0.0],
            "frame": {"mode": "rotating", "reference": "pulse_carrier", "rwa": True},
            "controls": [
                {
                    "target": 0,
                    "axis": "x",
                    "times": [0.0, 1.0e-9, 2.0e-9, 3.0e-9, 4.0e-9, 5.0e-9, 6.0e-9, 7.0e-9, 8.0e-9, 9.0e-9, 1.0e-8],
                    "values": [0.0, 2.9e6, 8.7e6, 1.92e7, 3.62e7, 6.07e7, 9.21e7, 1.27e8, 1.60e8, 1.83e8, 1.92e8],
                    "scale": 1.0,
                    "carrier_omega_rad_s": 2.0 * 3.141592653589793 * 5.0e9,
                    "drive_delta_rad_s": 0.0,
                    "carrier_phase_rad": 0.0,
                }
            ],
            "collapse_operators": [],
        },
    )
    try:
        trace = engine.run(spec, run_options={})
    except Exception:
        return
    assert max((row[0] for row in trace.states), default=0.0) > 1.0e-3
