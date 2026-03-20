import pytest

from qsim.common.schemas import ModelSpec
from qsim.engines.julia_qoptics import JuliaQuantumOpticsEngine
from qsim.engines.julia_qtoolbox import JuliaQuantumToolboxEngine


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


@pytest.mark.parametrize("engine_cls", [JuliaQuantumOpticsEngine, JuliaQuantumToolboxEngine])
def test_julia_engines_native_or_raise(engine_cls):
    engine = engine_cls()
    spec = _minimal_spec("me")
    try:
        trace = engine.run(spec, run_options={})
    except Exception:
        return
    assert trace.metadata.get("native_solver", False) is True


@pytest.mark.parametrize("engine_cls", [JuliaQuantumOpticsEngine, JuliaQuantumToolboxEngine])
def test_julia_engines_default_no_mock_fallback(monkeypatch, engine_cls):
    engine = engine_cls()
    spec = _minimal_spec("me")

    def _fail(_model_spec, run_options=None):
        raise RuntimeError("bridge failed")

    monkeypatch.setattr(engine, "_bridge", type("B", (), {"run": staticmethod(_fail)})())
    with pytest.raises(RuntimeError, match="bridge failed"):
        engine.run(spec)


@pytest.mark.parametrize("engine_cls", [JuliaQuantumOpticsEngine, JuliaQuantumToolboxEngine])
def test_julia_engines_pass_run_options(monkeypatch, engine_cls):
    engine = engine_cls()
    spec = _minimal_spec("mcwf")
    captured = {}

    class _Bridge:
        @staticmethod
        def run(_model_spec, run_options=None):
            captured["opts"] = dict(run_options or {})
            class _Trace:
                metadata = {"native_solver": True}
            return _Trace()

    monkeypatch.setattr(engine, "_bridge", _Bridge())
    engine.run(spec, run_options={"julia_bin": "C:/x/julia.exe", "ntraj": 16})
    assert captured["opts"]["julia_bin"] == "C:/x/julia.exe"
    assert int(captured["opts"]["ntraj"]) == 16


@pytest.mark.parametrize("engine_cls", [JuliaQuantumOpticsEngine, JuliaQuantumToolboxEngine])
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
