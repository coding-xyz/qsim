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
