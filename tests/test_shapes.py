import pytest

from qsim.common.schemas import Carrier, ChannelSpec, PulseIR, PulseSpec
from qsim.pulse.sequence import PulseCompiler
from qsim.pulse.shapes import DragShape, GaussianShape, RectShape


def test_rect_shape_nonzero_inside():
    shape = RectShape()
    assert shape.sample(5.0, 0.0, 10.0, 1.0) == 1.0
    assert shape.sample(-1.0, 0.0, 10.0, 1.0) == 0.0


def test_gaussian_shape_peak():
    shape = GaussianShape()
    center = shape.sample(5.0, 0.0, 10.0, 1.0)
    edge = shape.sample(0.0, 0.0, 10.0, 1.0)
    assert center > edge


def test_drag_shape_runs():
    shape = DragShape(beta=0.2)
    val = shape.sample(5.0, 0.0, 10.0, 1.0)
    assert isinstance(val, float)


def test_drag_shape_keeps_symmetric_i_and_antisymmetric_q():
    shape = DragShape(beta=0.4)
    i_left, q_left = shape.quadratures(4.0, 0.0, 10.0, 1.0)
    i_right, q_right = shape.quadratures(6.0, 0.0, 10.0, 1.0)

    assert i_left == pytest.approx(i_right)
    assert q_left == pytest.approx(-q_right)


def test_pulse_compiler_exports_drag_quadrature_separately():
    pulse_ir = PulseIR(
        t_end_s=10e-9,
        channels=[
            ChannelSpec(
                name="XY_0",
                pulses=[
                    PulseSpec(
                        t0_s=0.0,
                        t1_s=10e-9,
                        amp=1.0,
                        shape="drag",
                        params={"sigma_s": 2e-9, "beta": 0.3},
                        carrier=Carrier(freq=5.0e9, phase=0.0),
                    )
                ],
            )
        ],
    )

    samples = PulseCompiler.compile(pulse_ir, sample_rate_Hz=1.0e9)
    payload = samples["XY_0"]
    mid = len(payload["y"]) // 2

    assert "y_quadrature" in payload
    assert payload["y"][mid - 1] == pytest.approx(payload["y"][mid + 1], rel=1e-6)
    assert payload["y_quadrature"][mid - 1] == pytest.approx(-payload["y_quadrature"][mid + 1], rel=1e-6)
