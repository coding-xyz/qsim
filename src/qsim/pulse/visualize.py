"""Pulse, trace, and report visualization helpers."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import csv
import json
import math
import re
import numpy as np
from matplotlib.collections import LineCollection

from qsim.backend.config import load_backend_config
from qsim.backend.lowering import DefaultLowering
from qsim.circuit.import_qasm import CircuitAdapter
from qsim.common.schemas import BackendConfig, ChannelSpec, Observables, PulseIR, Trace
from qsim.pulse.catalog import (
    DEFAULT_BREAK_KEEP_HEAD_NS,
    DEFAULT_BREAK_KEEP_TAIL_NS,
    pulse_break_window,
)
from qsim.pulse.sequence import PulseCompiler
from qsim.pulse.shapes import make_shape

# Common defaults used by examples and callers.
DEFAULT_XY_CARRIER_HZ = 5e9
DEFAULT_RO_CARRIER_HZ = 8e9
DEFAULT_CARRIER_PLOT_MAX_HZ = 0.5e9
DEFAULT_CLOCK_MHZ = 100.0
DEFAULT_READOUT_DUR_NS = 2000.0
DEFAULT_RO_BREAK_MIN_PULSE_NS = 1000.0
DEFAULT_RO_BREAK_KEEP_HEAD_NS = DEFAULT_BREAK_KEEP_HEAD_NS
DEFAULT_RO_BREAK_KEEP_TAIL_NS = DEFAULT_BREAK_KEEP_TAIL_NS
# Backward-compatible aliases. Prefer the BREAK names in new code.
DEFAULT_RO_FOLD_MIN_PULSE_NS = DEFAULT_RO_BREAK_MIN_PULSE_NS
DEFAULT_RO_FOLD_KEEP_HEAD_NS = DEFAULT_RO_BREAK_KEEP_HEAD_NS
DEFAULT_RO_FOLD_KEEP_TAIL_NS = DEFAULT_RO_BREAK_KEEP_TAIL_NS
DEFAULT_BREAK_DISPLAY_GAP_NS = 18.0
DEFAULT_CHANNEL_LABEL_FONTSIZE = 10
DEFAULT_TICK_FONTSIZE = 8
DEFAULT_TITLE_FONTSIZE = 10
DEFAULT_AXIS_LABEL_FONTSIZE = 10
DEFAULT_ENVELOPE_POINTS_PER_PULSE = 800
DEFAULT_CARRIER_SAMPLES_PER_CYCLE = 8
# Widen DXF horizontally to match timing readability with matplotlib output.
# Previous value 0.12 made engineering drawings too compressed.
DEFAULT_DXF_X_SCALE = 0.54
DEFAULT_DXF_ROW_GAP = 18.0
DEFAULT_DXF_AMP_SCALE = 6.0
# Convert matplotlib point size to mm for CAD text height: 1 pt = 0.352777... mm
DEFAULT_DXF_TEXT_SCALE = 0.35278
DEFAULT_POST_SEQUENCE_GAP_NS = 20.0

# Timing layout geometry constants.
DEFAULT_MIN_CHANNEL_AMP_DRAW = 1.0
DEFAULT_MIN_ROW_GAP = 2.6
DEFAULT_PULSE_LABEL_HEIGHT_SCALE = 0.10
DEFAULT_PULSE_LABEL_HEIGHT_OFFSET = 0.2
DEFAULT_PULSE_LABEL_EXTRA_OFFSET = 0.12
DEFAULT_AXIS_GAP_EXTRA = 0.0
DEFAULT_AXIS_BOTTOM_MARGIN = 0.55
DEFAULT_CHANNEL_LABEL_MARGIN_NS = 0.08
DEFAULT_XLABEL_PAD = 6
DEFAULT_TITLE_PAD = 14
DEFAULT_X_RIGHT_MARGIN_NS = 6.0
DEFAULT_TARGET_TICKS = 9
DEFAULT_TIMING_FIGURE_MIN_WIDTH = 8.0
DEFAULT_TIMING_FIGURE_BASE_WIDTH = 6.5
DEFAULT_TIMING_FIGURE_WIDTH_NS_PER_INCH = 100.0
DEFAULT_TIMING_FIGURE_MIN_HEIGHT = 3.8
DEFAULT_TIMING_FIGURE_BASE_HEIGHT = 1.8
DEFAULT_TIMING_FIGURE_ROW_HEIGHT = 0.72

# DXF text placement ratios against y-range.
DEFAULT_DXF_TITLE_OFFSET = 2.0
DEFAULT_DXF_XLABEL_OFFSET = -1.0
DEFAULT_DXF_YLABEL_OFFSET = -10.0

DEFAULT_TIMING_THEME: dict[str, float | int | bool | str] = {
    "font_family": "Times New Roman",
    "black_white": True,
    "uppercase": True,
    "channel_label_fontsize": DEFAULT_CHANNEL_LABEL_FONTSIZE,
    "tick_fontsize": DEFAULT_TICK_FONTSIZE,
    "title_fontsize": DEFAULT_TITLE_FONTSIZE,
    "axis_label_fontsize": DEFAULT_AXIS_LABEL_FONTSIZE,
    "break_display_gap_ns": DEFAULT_BREAK_DISPLAY_GAP_NS,
    "carrier_samples_per_cycle": DEFAULT_CARRIER_SAMPLES_PER_CYCLE,
    "envelope_points_per_pulse": DEFAULT_ENVELOPE_POINTS_PER_PULSE,
    "show_grid": False,
    "hide_top_right_spines": True,
    "dxf_x_scale": DEFAULT_DXF_X_SCALE,
    "dxf_row_gap": DEFAULT_DXF_ROW_GAP,
    "dxf_amp_scale": DEFAULT_DXF_AMP_SCALE,
    "dxf_text_scale": DEFAULT_DXF_TEXT_SCALE,
    "dxf_left_margin": 42.0,
    "dxf_top_margin": 22.0,
    "dxf_baseline_extend_mm": 8.0,
    "dxf_t0_line_top_extra_mm": 8.0,
    "dxf_edge_break_marker": "ellipsis",
}


@dataclass
class _DisplayRow:
    label: str
    channels: list[ChannelSpec]


def make_timing_theme(**overrides) -> dict[str, float | int | bool | str]:
    """Build timing-plot theme with optional overrides."""
    theme = dict(DEFAULT_TIMING_THEME)
    theme.update({k: v for k, v in overrides.items() if v is not None})
    return theme


@dataclass
class _TimeWarp:
    t_end: float
    breaks: list[tuple[float, float]]
    display_gap: float = 35.0

    def map_scalar(self, t_ns: float) -> float:
        t = float(t_ns)
        skipped = 0.0
        for b0, b1 in self.breaks:
            if t >= b1:
                skipped += (b1 - b0 - self.display_gap)
            elif b0 < t < b1:
                t = b0
                skipped += 0.0
            else:
                break
        return t - skipped

    def map_array(self, t_ns: np.ndarray) -> np.ndarray:
        raw = t_ns.astype(float)
        x = raw.copy()
        for b0, b1 in self.breaks:
            inside = (raw > b0) & (raw < b1)
            x[inside] = b0
            right = raw >= b1
            x[right] -= (b1 - b0 - self.display_gap)
        return x

    @property
    def x_end(self) -> float:
        return self.t_end - sum((b1 - b0 - self.display_gap) for b0, b1 in self.breaks)


def _merge_intervals(intervals: list[tuple[float, float]]) -> list[tuple[float, float]]:
    """Merge overlapping closed-open intervals sorted by start time."""
    if not intervals:
        return []
    intervals = sorted(intervals, key=lambda x: x[0])
    out = [intervals[0]]
    for a, b in intervals[1:]:
        la, lb = out[-1]
        if a <= lb:
            out[-1] = (la, max(lb, b))
        else:
            out.append((a, b))
    return out


def auto_break_idle_windows(
    pulse_ir: PulseIR,
    idle_threshold_ns: float = 50_000.0,
    keep_edge_ns: float = 1_500.0,
) -> list[tuple[float, float]]:
    """Auto-detect long idle windows shared by all channels for axis breaks."""
    active: list[tuple[float, float]] = []
    for ch in pulse_ir.channels:
        for p in ch.pulses:
            active.append((float(p.t0), float(p.t1)))
    active = _merge_intervals(active)

    idle: list[tuple[float, float]] = []
    cursor = 0.0
    for a, b in active:
        if a > cursor:
            idle.append((cursor, a))
        cursor = max(cursor, b)
    if cursor < pulse_ir.t_end:
        idle.append((cursor, pulse_ir.t_end))

    breaks: list[tuple[float, float]] = []
    for a, b in idle:
        if (b - a) <= idle_threshold_ns:
            continue
        t0 = a + keep_edge_ns
        t1 = b - keep_edge_ns
        if t1 > t0:
            breaks.append((t0, t1))
    return breaks


def auto_break_long_pulses(
    pulse_ir: PulseIR,
    channel_prefixes: tuple[str, ...] = ("RO",),
    min_pulse_ns: float = 1_000.0,
    keep_head_ns: float = 120.0,
    keep_tail_ns: float = 120.0,
) -> list[tuple[float, float]]:
    """
    Generate break windows from explicitly breakable long pulses only.

    Breakability is defined by lowering/catalog metadata on each pulse. The
    `channel_prefixes` argument is retained only for API compatibility and is
    ignored by the scheduling logic.
    """
    _ = channel_prefixes
    blocking_active: list[tuple[float, float]] = []
    for ch in pulse_ir.channels:
        is_break_target = any(bool((p.params or {}).get("breakable", False)) for p in ch.pulses)
        if is_break_target:
            continue
        for p in ch.pulses:
            blocking_active.append((float(p.t0), float(p.t1)))
    merged_blocking = _merge_intervals(blocking_active)

    breaks: list[tuple[float, float]] = []
    for ch in pulse_ir.channels:
        target_pulses = [p for p in ch.pulses if bool((p.params or {}).get("breakable", False))]
        for p in target_pulses:
            explicit_window = pulse_break_window(ch.name, p)
            if explicit_window is not None:
                b0, b1 = explicit_window
                if float(p.t1) - float(p.t0) < float(min_pulse_ns):
                    continue
                visible = _clip_interval(b0, b1, merged_blocking)
                if visible == [(b0, b1)]:
                    breaks.append((b0, b1))
                continue
            t0 = float(p.t0)
            t1 = float(p.t1)
            dur = t1 - t0
            if dur < float(min_pulse_ns):
                continue
            b0 = t0 + float(keep_head_ns)
            b1 = t1 - float(keep_tail_ns)
            if b1 > b0:
                visible = _clip_interval(b0, b1, merged_blocking)
                if visible == [(b0, b1)]:
                    breaks.append((b0, b1))
    return _merge_intervals(breaks)


def auto_fold_breaks(
    pulse_ir: PulseIR,
    idle_threshold_ns: float = 50_000.0,
    keep_edge_ns: float = 1_500.0,
) -> list[tuple[float, float]]:
    """Backward-compatible alias for `auto_break_idle_windows`."""
    return auto_break_idle_windows(
        pulse_ir,
        idle_threshold_ns=idle_threshold_ns,
        keep_edge_ns=keep_edge_ns,
    )


def auto_fold_long_pulses(
    pulse_ir: PulseIR,
    channel_prefixes: tuple[str, ...] = ("RO",),
    min_pulse_ns: float = 1_000.0,
    keep_head_ns: float = 120.0,
    keep_tail_ns: float = 120.0,
) -> list[tuple[float, float]]:
    """Backward-compatible alias for `auto_break_long_pulses`."""
    return auto_break_long_pulses(
        pulse_ir,
        channel_prefixes=channel_prefixes,
        min_pulse_ns=min_pulse_ns,
        keep_head_ns=keep_head_ns,
        keep_tail_ns=keep_tail_ns,
    )


def reorder_xy_z_channels(pulse_ir: PulseIR) -> PulseIR:
    """
    Reorder channels as XY_i, Z_i, XY_j, Z_j, ... while preserving other channels.
    """
    by_name: dict[str, ChannelSpec] = {ch.name: ch for ch in pulse_ir.channels}
    ordered: list[ChannelSpec] = []
    used: set[str] = set()

    # Pair by suffix in XY_*/Z_* naming convention.
    suffixes: set[str] = set()
    for name in by_name:
        up = name.upper()
        if up.startswith("XY_"):
            suffixes.add(name.split("_", 1)[1])
        elif up.startswith("Z_"):
            suffixes.add(name.split("_", 1)[1])

    def _sort_key(s: str):
        return (0, int(s)) if s.isdigit() else (1, s)

    for s in sorted(suffixes, key=_sort_key):
        xy_name = f"XY_{s}"
        z_name = f"Z_{s}"
        if xy_name in by_name:
            ordered.append(by_name[xy_name])
            used.add(xy_name)
        if z_name in by_name:
            ordered.append(by_name[z_name])
            used.add(z_name)

    remaining = [ch for ch in pulse_ir.channels if ch.name not in used]

    def _rest_group(name: str) -> tuple[int, int, str]:
        up = name.upper()
        m_tc = re.match(r"^TC_?(\d+)$", up)
        if m_tc:
            return (0, int(m_tc.group(1)), "")
        m_ro = re.match(r"^RO_?(\d+)$", up)
        if m_ro:
            return (1, int(m_ro.group(1)), "")
        return (2, 0, up)

    ordered.extend(sorted(remaining, key=lambda c: _rest_group(c.name)))

    return PulseIR(schema_version=pulse_ir.schema_version, t_end=pulse_ir.t_end, channels=ordered)


def canonicalize_channel_names(pulse_ir: PulseIR) -> PulseIR:
    """Normalize channel naming to `XY_i`, `Z_i`, `RO_i`, and `TC_i` forms.

    This helper keeps pulse content unchanged and only rewrites channel names
    to a consistent underscore style expected by timing plots.
    """
    out_channels: list[ChannelSpec] = []
    for ch in pulse_ir.channels:
        name = ch.name
        up = name.upper()
        m = re.match(r"^(XY|Z|RO|TC)_?(\d+)$", up)
        if m:
            name = f"{m.group(1)}_{int(m.group(2))}"
        out_channels.append(ChannelSpec(name=name, pulses=list(ch.pulses)))
    return PulseIR(schema_version=pulse_ir.schema_version, t_end=pulse_ir.t_end, channels=out_channels)


def ensure_z_channels(pulse_ir: PulseIR, num_qubits: int) -> PulseIR:
    """Ensure all `Z_i` channels exist, adding empty channels when missing."""
    existing = {ch.name.upper() for ch in pulse_ir.channels}
    channels = list(pulse_ir.channels)
    for i in range(max(0, int(num_qubits))):
        z_name = f"Z_{i}"
        if z_name.upper() not in existing:
            channels.append(ChannelSpec(name=z_name, pulses=[]))
    return PulseIR(schema_version=pulse_ir.schema_version, t_end=pulse_ir.t_end, channels=channels)


def _xy_z_suffix(channel_name: str) -> tuple[str, str] | None:
    """Return `(kind, suffix)` for XY/Z-style channel names."""
    m = re.match(r"^(XY|Z)_?(.+)$", str(channel_name).upper())
    if not m:
        return None
    return str(m.group(1)), str(m.group(2))


def _build_display_rows(pulse_ir: PulseIR, *, XYZ_line_combine: bool) -> list[_DisplayRow]:
    """Build timing-plot display rows without mutating the input PulseIR."""
    if not XYZ_line_combine:
        return [_DisplayRow(label=ch.name, channels=[ch]) for ch in pulse_ir.channels]

    by_name: dict[str, ChannelSpec] = {ch.name.upper(): ch for ch in pulse_ir.channels}
    consumed_xy_z: set[str] = set()
    rows: list[_DisplayRow] = []
    for ch in pulse_ir.channels:
        parsed = _xy_z_suffix(ch.name)
        up = ch.name.upper()
        if parsed is None:
            rows.append(_DisplayRow(label=ch.name, channels=[ch]))
            continue
        if up in consumed_xy_z:
            continue
        _kind, suffix = parsed
        xy = by_name.get(f"XY_{suffix}")
        z = by_name.get(f"Z_{suffix}")
        if xy is None and z is None:
            rows.append(_DisplayRow(label=ch.name, channels=[ch]))
            consumed_xy_z.add(up)
            continue
        rows.append(_DisplayRow(label=f"XYZ_{suffix}", channels=[item for item in (xy, z) if item is not None]))
        if xy is not None:
            consumed_xy_z.add(xy.name.upper())
        if z is not None:
            consumed_xy_z.add(z.name.upper())
    return rows


def pulse_ir_from_qasm(
    qasm_text: str,
    *,
    backend_config: BackendConfig | str | Path,
    hardware: dict | None = None,
    schedule_policy: str | None = None,
    reset_feedback_policy: str | None = None,
    canonicalize_names: bool = True,
    include_empty_z: bool = True,
) -> PulseIR:
    """Compile OpenQASM text into `PulseIR` for visualization.

    Parameters
    - `qasm_text`: OpenQASM 3 program string.
    - `backend_config`: Backend config object or YAML path.
    - `hardware`: Optional hardware knobs consumed by lowering.
    - `schedule_policy`: Optional lowering schedule policy: `serial|parallel|hybrid`.
    - `reset_feedback_policy`: Optional reset feedback policy: `parallel|serial_global`.
    - `canonicalize_names`: Convert channel names to underscore style.
    - `include_empty_z`: Add missing `Z_i` channels for all declared qubits.
    """
    cfg = load_backend_config(backend_config) if isinstance(backend_config, (str, Path)) else backend_config
    circuit = CircuitAdapter.from_qasm(qasm_text)
    lowering_hw = dict(hardware or {})
    if schedule_policy is not None:
        lowering_hw["schedule_policy"] = str(schedule_policy)
    if reset_feedback_policy is not None:
        lowering_hw["reset_feedback_policy"] = str(reset_feedback_policy)
    pulse_ir, _exe = DefaultLowering().lower(circuit, hw=lowering_hw, cfg=cfg)
    out = canonicalize_channel_names(pulse_ir) if canonicalize_names else pulse_ir
    if include_empty_z:
        out = ensure_z_channels(out, circuit.num_qubits)
    return out


def _channel_amp_unit(channel_name: str) -> str:
    """Return metadata amplitude unit by channel type."""
    up = channel_name.upper()
    if up.startswith("XY_") or up.startswith("RO_"):
        return "dBm"
    return "uA"


def _parse_breaks(
    breaks: list[tuple[float, float]] | list[dict] | None,
) -> list[tuple[float, float]]:
    """Normalize break specifications into sorted `(t0, t1)` tuples."""
    out: list[tuple[float, float]] = []
    if not breaks:
        return out
    for b in breaks:
        if isinstance(b, dict):
            t0 = float(b.get("t0", 0.0))
            t1 = float(b.get("t1", 0.0))
        else:
            t0 = float(b[0])
            t1 = float(b[1])
        if t1 > t0:
            out.append((t0, t1))
    return sorted(out, key=lambda x: x[0])


def _clip_interval(t0: float, t1: float, breaks: list[tuple[float, float]]) -> list[tuple[float, float]]:
    """Subtract break windows from `[t0, t1]` and return visible sub-intervals."""
    segs = [(float(t0), float(t1))]
    for b0, b1 in breaks:
        new: list[tuple[float, float]] = []
        for s0, s1 in segs:
            if s1 <= b0 or s0 >= b1:
                new.append((s0, s1))
                continue
            if s0 < b0:
                new.append((s0, b0))
            if s1 > b1:
                new.append((b1, s1))
        segs = new
        if not segs:
            break
    return [(a, b) for a, b in segs if b > a]


def _plot_clock(ax, warp: _TimeWarp, y0: float, t_start: float, t_end: float, clock_mhz: float) -> None:
    """Draw square-wave clock in a visible interval."""
    period_ns = 1000.0 / max(clock_mhz, 1e-12)
    half = period_ns * 0.5
    t = float(t_start)
    x0 = warp.map_scalar(t)
    level_high = (int(math.floor(t / half)) % 2) == 0
    x_pts = [x0, x0]
    y_pts = [y0, y0 + (0.8 if level_high else 0.0)]
    while t < t_end:
        t2 = min(t + half, t_end)
        x_pts.append(warp.map_scalar(t2))
        y_pts.append(y0 + (0.8 if level_high else 0.0))
        if t2 < t_end:
            x_pts.append(warp.map_scalar(t2))
            level_high = not level_high
            y_pts.append(y0 + (0.8 if level_high else 0.0))
        t = t2
    ax.plot(x_pts, y_pts, color="black", lw=0.9)


def _nice_tick_step(raw: float) -> float:
    """Round a raw step to 1/2/5*10^k major tick spacing."""
    if raw <= 0:
        return 1.0
    k = math.floor(math.log10(raw))
    base = raw / (10 ** k)
    if base <= 1.0:
        m = 1.0
    elif base <= 2.0:
        m = 2.0
    elif base <= 5.0:
        m = 5.0
    else:
        m = 10.0
    return m * (10 ** k)


def _in_break(t: float, breaks: list[tuple[float, float]]) -> bool:
    """Return whether a raw timestamp is inside any break segment."""
    for b0, b1 in breaks:
        if b0 < t < b1:
            return True
    return False


def _build_time_ticks(
    t_end: float,
    breaks: list[tuple[float, float]],
    target_ticks: int = 9,
) -> list[float]:
    """Build major ticks in raw time coordinates, skipping break windows."""
    visible_total = max(1e-9, t_end - sum((b1 - b0) for b0, b1 in breaks))
    step = _nice_tick_step(visible_total / max(1, target_ticks))
    ticks: list[float] = [0.0]
    t = step
    while t < t_end + 1e-9:
        if not _in_break(t, breaks):
            ticks.append(t)
        t += step
    if abs(ticks[-1] - t_end) > 0.5 * step and not _in_break(t_end, breaks):
        ticks.append(t_end)
    ticks = sorted(set(round(v, 6) for v in ticks))
    return ticks


def _plot_broken_hline(ax, warp: _TimeWarp, y: float, breaks: list[tuple[float, float]]) -> None:
    """Draw a baseline split around break windows with default style."""
    _plot_broken_hline_style(ax, warp, y, breaks, color="black", lw=0.6, alpha=0.55)


def _plot_broken_hline_style(
    ax,
    warp: _TimeWarp,
    y: float,
    breaks: list[tuple[float, float]],
    *,
    color: str,
    lw: float,
    alpha: float,
    t_end: float | None = None,
) -> None:
    """Draw a baseline split around break windows with caller-provided style."""
    tend = float(warp.t_end if t_end is None else t_end)
    seg_start = 0.0
    for b0, b1 in breaks:
        if b0 >= tend:
            break
        x0 = warp.map_scalar(seg_start)
        x1 = warp.map_scalar(min(b0, tend))
        if x1 > x0:
            ax.hlines(y, x0, x1, color=color, lw=lw, alpha=alpha, zorder=0)
        seg_start = b1
        if seg_start >= tend:
            break
    x0 = warp.map_scalar(min(seg_start, tend))
    x1 = warp.map_scalar(tend)
    if x1 > x0:
        ax.hlines(y, x0, x1, color=color, lw=lw, alpha=alpha, zorder=0)


def _plot_break_dotted_segments(
    ax,
    warp: _TimeWarp,
    y: float,
    breaks: list[tuple[float, float]],
    *,
    color: str,
    lw: float,
    alpha: float,
    t_end: float | None = None,
) -> None:
    """Draw dotted baseline segments inside break windows."""
    tend = float(warp.t_end if t_end is None else t_end)
    for b0, b1 in breaks:
        if b0 >= tend:
            break
        a = max(0.0, float(b0))
        b = min(tend, float(b1))
        if b <= a:
            continue
        x0 = warp.map_scalar(a)
        x1 = warp.map_scalar(b)
        if x1 > x0:
            ax.hlines(y, x0, x1, color=color, lw=lw, alpha=alpha, linestyles=":", zorder=1)


def _draw_time_axis_ticks(ax, warp: _TimeWarp, y_axis: float, raw_ticks: list[float], tick_fontsize: int) -> None:
    """Draw custom tick marks and labels on the dedicated timing axis row."""
    tick_len = 0.28
    for t in raw_ticks:
        x = warp.map_scalar(t)
        ax.vlines(x, y_axis - 0.5 * tick_len, y_axis + 0.5 * tick_len, color="black", lw=0.7)
        ax.text(x, y_axis - 0.38, str(int(round(t))), ha="center", va="top", fontsize=tick_fontsize, color="black")


def _plot_pulses_timing(
    pulse_ir: PulseIR,
    *,
    show_carrier: bool,
    title: str | None,
    breaks: list[tuple[float, float]],
    show_clock: bool,
    clock_mhz: float,
    carrier_plot_max_hz: float | None,
    carrier_samples_per_cycle: int,
    envelope_points_per_pulse: int,
    black_white: bool,
    uppercase: bool,
    channel_label_fontsize: int,
    tick_fontsize: int,
    title_fontsize: int,
    axis_label_fontsize: int,
    break_display_gap_ns: float,
    show_grid: bool,
    hide_top_right_spines: bool,
    font_family: str,
    annotate_pulses: bool,
    pulse_label_fontsize: int,
    post_sequence_gap_ns: float,
    target_ticks: int,
    XYZ_line_combine: bool,
):
    """Render timing-layout pulse plot with time breaks, clock lane, and custom axis."""
    import matplotlib.pyplot as plt
    from matplotlib.font_manager import FontProperties
    plt.rcParams["font.family"] = font_family

    display_rows = _build_display_rows(pulse_ir, XYZ_line_combine=XYZ_line_combine)

    max_amp = DEFAULT_MIN_CHANNEL_AMP_DRAW
    ch_amp_map: dict[str, float] = {}
    for ch in pulse_ir.channels:
        ch_amp = max([abs(float(p.amp)) for p in ch.pulses], default=0.0)
        ch_amp = max(DEFAULT_MIN_CHANNEL_AMP_DRAW, ch_amp)
        ch_amp_map[ch.name] = ch_amp
        max_amp = max(max_amp, ch_amp)
    pulse_label_height = (
        DEFAULT_PULSE_LABEL_HEIGHT_SCALE * max(6, int(pulse_label_fontsize)) + DEFAULT_PULSE_LABEL_HEIGHT_OFFSET
        if annotate_pulses
        else 0.0
    )
    # Keep labels clear of waveform by design: channel_gap ~= 2*amp + label_height.
    row_gap = max(DEFAULT_MIN_ROW_GAP, 2.0 * max_amp + pulse_label_height)
    last_pulse_t1 = 0.0
    for ch in pulse_ir.channels:
        for p in ch.pulses:
            last_pulse_t1 = max(last_pulse_t1, float(p.t1))
    plot_t_end = max(float(pulse_ir.t_end), max(0.0, last_pulse_t1) + max(0.0, float(post_sequence_gap_ns)))
    if plot_t_end <= 0.0:
        plot_t_end = float(pulse_ir.t_end)
    breaks = [(b0, b1) for b0, b1 in breaks if b0 < plot_t_end and b1 > 0.0]
    breaks = [(max(0.0, b0), min(plot_t_end, b1)) for b0, b1 in breaks if min(plot_t_end, b1) > max(0.0, b0)]
    warp = _TimeWarp(t_end=float(plot_t_end), breaks=breaks, display_gap=float(break_display_gap_ns))
    x_end_plot = warp.map_scalar(plot_t_end)
    n_rows = len(display_rows) + (1 if show_clock else 0)
    fig_w = max(
        DEFAULT_TIMING_FIGURE_MIN_WIDTH,
        DEFAULT_TIMING_FIGURE_BASE_WIDTH + x_end_plot / DEFAULT_TIMING_FIGURE_WIDTH_NS_PER_INCH,
    )
    fig_h = max(
        DEFAULT_TIMING_FIGURE_MIN_HEIGHT,
        DEFAULT_TIMING_FIGURE_BASE_HEIGHT + DEFAULT_TIMING_FIGURE_ROW_HEIGHT * max(1, n_rows),
    )
    fig, ax = plt.subplots(figsize=(fig_w, fig_h))
    baseline_color = "#808080"

    y_positions: list[float] = []
    y_labels: list[str] = []
    pulse_metadata: list[dict] = []
    pulse_idx = 1

    if show_clock:
        y_clk = len(display_rows) * row_gap
        _plot_broken_hline_style(ax, warp, y_clk, breaks, color=baseline_color, lw=0.8, alpha=1.0, t_end=plot_t_end)
        _plot_break_dotted_segments(ax, warp, y_clk, breaks, color=baseline_color, lw=0.8, alpha=1.0, t_end=plot_t_end)
        ax.hlines(y_clk, -1.0, warp.map_scalar(0.0), color=baseline_color, lw=0.8, alpha=1.0, zorder=0)
        ax.hlines(y_clk, -1.0, warp.map_scalar(0.0), color="black", lw=1.0, alpha=0.96, zorder=3)
        for a, b in _clip_interval(0.0, plot_t_end, breaks):
            _plot_clock(ax, warp, y_clk, a, b, clock_mhz)
        y_positions.append(y_clk)
        y_labels.append("CLK")

    for idx, row in enumerate(display_rows):
        y0 = (len(display_rows) - 1 - idx) * row_gap
        ch_amp = max([ch_amp_map.get(ch.name, DEFAULT_MIN_CHANNEL_AMP_DRAW) for ch in row.channels], default=1.0)
        env_color = "black" if black_white else f"C{idx % 10}"
        car_color = "black" if black_white else f"C{idx % 10}"
        _plot_broken_hline_style(ax, warp, y0, breaks, color=baseline_color, lw=0.7, alpha=1.0, t_end=plot_t_end)
        _plot_break_dotted_segments(ax, warp, y0, breaks, color=baseline_color, lw=0.7, alpha=1.0, t_end=plot_t_end)
        ax.hlines(y0, -1.0, warp.map_scalar(0.0), color=baseline_color, lw=0.7, alpha=1.0, zorder=0)
        ax.hlines(y0, -1.0, warp.map_scalar(0.0), color=car_color, lw=1.0, alpha=0.96, zorder=3)
        shaped_pulses = [
            (ch.name, p, make_shape(p.shape, p.params))
            for ch in row.channels
            for p in ch.pulses
        ]
        row_pulse_ids: list[str] = []
        for source_channel, p, _shape in shaped_pulses:
            p_params = dict(p.params or {})
            rise_ns = (
                float(p_params["rise_ns"])
                if "rise_ns" in p_params
                else (float(p_params["rise"]) if "rise" in p_params else 0.0)
            )
            fall_ns = (
                float(p_params["fall_ns"])
                if "fall_ns" in p_params
                else (float(p_params["fall"]) if "fall" in p_params else 0.0)
            )
            shape_name = "rect" if str(p.shape).lower() == "dc" else str(p.shape)
            amp_unit = _channel_amp_unit(source_channel)
            params_out = dict(p_params)
            params_out.pop("rise", None)
            params_out.pop("fall", None)
            pulse_id = f"P{pulse_idx}"
            if shape_name.lower() in {"rect", "readout"}:
                params_out["rise_ns"] = rise_ns
                params_out["fall_ns"] = fall_ns
            meta = {
                "id": pulse_id,
                "channel": source_channel,
                "t_start_ns": float(p.t0),
                "t_end_ns": float(p.t1),
                "duration_ns": float(p.t1) - float(p.t0),
                "shape": shape_name,
                "params": params_out,
            }
            if amp_unit == "dBm":
                meta["amp_dbm"] = float(p.amp)
            else:
                meta["amp_uA"] = float(p.amp)
            if p.carrier is not None:
                meta["carrier"] = {
                    "freq_hz": float(p.carrier.freq),
                    "phase_deg": float(p.carrier.phase) * 180.0 / math.pi,
                }
            pulse_metadata.append(meta)
            row_pulse_ids.append(pulse_id)
            pulse_idx += 1
        for a, b in _clip_interval(0.0, plot_t_end, breaks):
            dur = b - a
            n_env = max(120, int(envelope_points_per_pulse))
            max_freq = 0.0
            has_carrier_overlap = False
            if show_carrier:
                for _source_channel, p, _shape in shaped_pulses:
                    if p.t1 <= a or p.t0 >= b or p.carrier is None:
                        continue
                    has_carrier_overlap = True
                    f = float(p.carrier.freq)
                    if carrier_plot_max_hz is not None:
                        f = min(f, float(carrier_plot_max_hz))
                    max_freq = max(max_freq, f)
            if max_freq > 0.0:
                cycles = max(1.0, max_freq * dur * 1e-9)
                n_car = int(max(200, min(12_000, cycles * max(4, carrier_samples_per_cycle))))
                n = max(n_env, n_car)
            else:
                n = n_env

            t = np.linspace(a, b, n)
            env = np.zeros_like(t, dtype=float)
            env_carrier = np.zeros_like(t, dtype=float)
            car = np.zeros_like(t, dtype=float)
            for _source_channel, p, shape in shaped_pulses:
                if p.t1 <= a or p.t0 >= b:
                    continue
                penv = np.asarray([shape.sample(float(ti), p.t0, p.t1, p.amp) for ti in t], dtype=float)
                if show_carrier and p.carrier is not None:
                    env_carrier += penv
                else:
                    env += penv
                if show_carrier and p.carrier is not None:
                    freq = float(p.carrier.freq)
                    if carrier_plot_max_hz is not None:
                        freq = min(freq, float(carrier_plot_max_hz))
                    phase = float(p.carrier.phase)
                    car += penv * np.sin(2.0 * math.pi * freq * (t * 1e-9) + phase)
            body = env + car

            x = warp.map_array(t)
            if show_carrier and has_carrier_overlap:
                mask = env_carrier > 1e-12
                env_aux = np.where(mask, y0 + env_carrier, np.nan)
                ax.plot(x, env_aux, ls="--", lw=1.0, alpha=0.95, color=env_color, zorder=2)
            ax.plot(x, y0 + body, ls="-", lw=1.0, alpha=0.96, color=car_color, zorder=3)
        if annotate_pulses:
            for p_id, (_source_channel, p, _shape) in zip(row_pulse_ids, shaped_pulses):
                vis = _clip_interval(float(p.t0), float(p.t1), breaks)
                if not vis:
                    continue
                a0, b0 = vis[0]
                tx = warp.map_scalar(0.5 * (a0 + b0))
                ax.text(
                    tx,
                    y0 + ch_amp + DEFAULT_PULSE_LABEL_EXTRA_OFFSET,
                    p_id,
                    ha="center",
                    va="bottom",
                    fontsize=pulse_label_fontsize,
                    color="black",
                )
        y_positions.append(y0)
        y_labels.append(row.label.upper() if uppercase else row.label)

    y_axis_gap = max_amp + pulse_label_height + DEFAULT_AXIS_GAP_EXTRA
    y_axis = min(y_positions) - y_axis_gap if y_positions else -y_axis_gap
    _plot_broken_hline_style(ax, warp, y_axis, breaks, color="black", lw=1.0, alpha=1.0, t_end=plot_t_end)
    _plot_break_dotted_segments(ax, warp, y_axis, breaks, color="black", lw=1.0, alpha=1.0, t_end=plot_t_end)
    ax.hlines(y_axis, -1.0, warp.map_scalar(0.0), color="black", lw=1.0, alpha=1.0, zorder=0)
    y_top = (max(y_positions) + 1.1) if y_positions else 1.0
    x_zero = warp.map_scalar(0.0)
    ax.vlines(x_zero, y_axis, y_top, colors="#808080", linestyles="--", linewidth=0.9, zorder=0)

    if title is None:
        title = "Pulse Timing"
    ax.set_title(title.upper() if uppercase else title, fontsize=title_fontsize, pad=DEFAULT_TITLE_PAD)
    ax.set_xlabel("TIME (ns)" if uppercase else "Time (ns)", fontsize=axis_label_fontsize, labelpad=DEFAULT_XLABEL_PAD)
    ax.set_ylabel("")
    ax.set_xlim(-1.0, x_end_plot + DEFAULT_X_RIGHT_MARGIN_NS)
    raw_ticks = _build_time_ticks(plot_t_end, breaks, target_ticks=max(2, int(target_ticks)))
    _draw_time_axis_ticks(ax, warp, y_axis, raw_ticks, tick_fontsize)
    ax.set_xticks([])
    ax.set_xticklabels([])
    ax.set_yticks(y_positions)
    ax.set_yticklabels(["" for _ in y_positions])
    ax.tick_params(axis="y", length=0)
    y_bot = y_axis - (DEFAULT_AXIS_BOTTOM_MARGIN + pulse_label_height)
    ax.set_ylim(y_bot, y_top)
    if show_grid:
        ax.grid(True, alpha=0.16, color="black" if black_white else "gray")
    else:
        ax.grid(False)
    if hide_top_right_spines:
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)
    ax.spines["left"].set_visible(False)
    ax.spines["bottom"].set_visible(False)
    fig.canvas.draw()
    renderer = fig.canvas.get_renderer()
    bbox_px = ax.get_window_extent(renderer=renderer).width
    xr = max(1e-9, float(ax.get_xlim()[1] - ax.get_xlim()[0]))
    data_per_px = xr / max(1.0, float(bbox_px))
    fp = FontProperties(family=font_family, size=channel_label_fontsize)
    max_label_w_px = 0.0
    for s in y_labels:
        w, _h, _d = renderer.get_text_width_height_descent(s, fp, ismath=False)
        max_label_w_px = max(max_label_w_px, float(w))
    max_label_w_data = max_label_w_px * data_per_px
    x_baseline = -1.0
    x_label = x_baseline - max_label_w_data - DEFAULT_CHANNEL_LABEL_MARGIN_NS
    for yv, txt in zip(y_positions, y_labels):
        label_text = ax.text(
            x_label,
            yv,
            txt,
            ha="left",
            va="center",
            fontsize=channel_label_fontsize,
            color="black",
            clip_on=False,
        )
        label_text.set_gid("qsim_channel_label")
    fig.tight_layout()
    fig._qsim_pulse_metadata = pulse_metadata  # type: ignore[attr-defined]
    return fig


def _to_dxf_lineweight(linewidth: float) -> int:
    """Convert matplotlib linewidth (pt) into DXF lineweight (1/100 mm)."""
    # Approximate matplotlib linewidth (pt) to DXF lineweight (1/100 mm)
    mm = max(0.13, float(linewidth) * DEFAULT_DXF_TEXT_SCALE)
    return int(round(mm * 100.0))


def _split_nan_segments(x: np.ndarray, y: np.ndarray) -> list[np.ndarray]:
    """Split polyline points into contiguous finite-value segments."""
    pts = np.column_stack([x, y])
    finite = np.isfinite(pts).all(axis=1)
    out: list[np.ndarray] = []
    start = None
    for i, ok in enumerate(finite):
        if ok and start is None:
            start = i
        if (not ok) and start is not None:
            if i - start >= 2:
                out.append(pts[start:i])
            start = None
    if start is not None and len(pts) - start >= 2:
        out.append(pts[start:])
    return out


def _export_timing_figure_to_dxf(fig, out_path: str | Path) -> Path:
    """Export timing plot primitives from matplotlib figure directly to DXF."""
    import ezdxf
    from ezdxf.enums import TextEntityAlignment

    ax = fig.axes[0]
    xlim = ax.get_xlim()
    ylim = ax.get_ylim()
    xr = float(xlim[1] - xlim[0])
    yr = float(ylim[1] - ylim[0])
    # Match matplotlib apparent aspect ratio in DXF by converting data coordinates
    # into mm using the axes box size on the figure canvas.
    fig_w_in, fig_h_in = fig.get_size_inches()
    bbox = ax.get_position()
    ax_w_mm = float(fig_w_in * 25.4 * bbox.width)
    ax_h_mm = float(fig_h_in * 25.4 * bbox.height)
    sx = ax_w_mm / max(xr, 1e-9)
    sy = ax_h_mm / max(yr, 1e-9)

    def _map_xy(x: float, y: float) -> tuple[float, float]:
        return ((float(x) - float(xlim[0])) * sx, (float(y) - float(ylim[0])) * sy)

    def _align_from_ha_va(ha: str, va: str):
        ha_n = (ha or "left").lower()
        va_n = (va or "baseline").lower()
        table = {
            ("left", "bottom"): TextEntityAlignment.BOTTOM_LEFT,
            ("left", "baseline"): TextEntityAlignment.LEFT,
            ("left", "center"): TextEntityAlignment.MIDDLE_LEFT,
            ("left", "top"): TextEntityAlignment.TOP_LEFT,
            ("center", "bottom"): TextEntityAlignment.BOTTOM_CENTER,
            ("center", "baseline"): TextEntityAlignment.CENTER,
            ("center", "center"): TextEntityAlignment.MIDDLE_CENTER,
            ("center", "top"): TextEntityAlignment.TOP_CENTER,
            ("right", "bottom"): TextEntityAlignment.BOTTOM_RIGHT,
            ("right", "baseline"): TextEntityAlignment.RIGHT,
            ("right", "center"): TextEntityAlignment.MIDDLE_RIGHT,
            ("right", "top"): TextEntityAlignment.TOP_RIGHT,
        }
        if va_n == "center_baseline":
            va_n = "baseline"
        return table.get((ha_n, va_n), TextEntityAlignment.LEFT)

    doc = ezdxf.new("R2010")
    msp = doc.modelspace()
    if "JIS_02_0.7" not in doc.linetypes:
        doc.linetypes.new(
            "JIS_02_0.7",
            dxfattribs={"description": "JIS short dash", "pattern": [1.4, 0.7, -0.7]},
        )
    if "TNR" not in doc.styles:
        doc.styles.new("TNR", dxfattribs={"font": "Times New Roman.ttf"})
    doc.header["$TEXTSTYLE"] = "TNR"
    doc.header["$PLINEGEN"] = 1
    doc.layers.new("WAVE", dxfattribs={"color": 7, "lineweight": 35})
    doc.layers.new("BASE", dxfattribs={"color": 8, "lineweight": 25})
    doc.layers.new("TEXT", dxfattribs={"color": 7})

    def line_layer_and_color(color_obj):
        # Keep a simple black/gray mapping to match matplotlib styling intent.
        try:
            c = str(color_obj).lower()
            if "808080" in c or "gray" in c:
                return "BASE"
        except Exception:
            pass
        return "WAVE"

    # LineCollections (hlines/vlines/ticks)
    for coll in ax.collections:
        if not isinstance(coll, LineCollection):
            continue
        layer = "BASE"
        ltype = None
        if len(coll.get_linestyles()) > 0:
            ls = coll.get_linestyles()[0]
            if isinstance(ls, tuple) and len(ls) >= 2:
                dash_seq = ls[1]
                if dash_seq is not None and len(dash_seq) > 0:
                    ltype = "JIS_02_0.7"
        lws = coll.get_linewidths()
        lw = _to_dxf_lineweight(float(lws[0]) if len(lws) else 0.8)
        for seg in coll.get_segments():
            if len(seg) < 2:
                continue
            attribs = {"layer": layer, "lineweight": lw, "flags": 128}
            if ltype:
                attribs["linetype"] = ltype
            msp.add_lwpolyline([_map_xy(float(px), float(py)) for px, py in seg], dxfattribs=attribs)

    # Line2D objects
    for ln in ax.lines:
        x = np.asarray(ln.get_xdata(), dtype=float)
        y = np.asarray(ln.get_ydata(), dtype=float)
        segs = _split_nan_segments(x, y)
        if not segs:
            continue
        layer = line_layer_and_color(ln.get_color())
        lw = _to_dxf_lineweight(float(ln.get_linewidth()))
        ltype = "JIS_02_0.7" if str(ln.get_linestyle()) in {"--", "dashed"} else None
        for s in segs:
            attribs = {"layer": layer, "lineweight": lw, "flags": 128}
            if ltype:
                attribs["linetype"] = ltype
            msp.add_lwpolyline([_map_xy(float(px), float(py)) for px, py in s], dxfattribs=attribs)

    # Title and xlabel
    title = ax.get_title()
    fs_pt = float(ax.title.get_size())
    fs_mm = fs_pt * DEFAULT_DXF_TEXT_SCALE
    if title:
        msp.add_text(
            title,
            dxfattribs={"height": fs_mm, "layer": "TEXT", "style": "TNR"},
        ).set_placement(
            _map_xy(0.5 * (xlim[0] + xlim[1]), ylim[1] + DEFAULT_DXF_TITLE_OFFSET),
            align=TextEntityAlignment.MIDDLE_CENTER,
        )
    xlabel = ax.get_xlabel()
    fs_pt = float(ax.xaxis.get_label().get_size())
    fs_mm = fs_pt * DEFAULT_DXF_TEXT_SCALE
    if xlabel:
        msp.add_text(
            xlabel,
            dxfattribs={"height": fs_mm, "layer": "TEXT", "style": "TNR"},
        ).set_placement(
            _map_xy(0.5 * (xlim[0] + xlim[1]), ylim[0] + DEFAULT_DXF_XLABEL_OFFSET),
            align=TextEntityAlignment.MIDDLE_CENTER,
        )

    # Channel labels: read directly from tagged matplotlib Text artists.
    for t in ax.texts:
        if t.get_gid() != "qsim_channel_label":
            continue
        txt = t.get_text()
        if not txt:
            continue
        fs_pt = float(t.get_fontsize())
        fs_mm = fs_pt * DEFAULT_DXF_TEXT_SCALE
        x, y = t.get_position()
        msp.add_text(
            txt,
            dxfattribs={"height": fs_mm, "layer": "TEXT", "style": "TNR"},
        ).set_placement(
            _map_xy(float(x) + DEFAULT_DXF_YLABEL_OFFSET, float(y)),
            align=_align_from_ha_va(str(t.get_ha()), str(t.get_va())),
        )

    # Axes-added annotation texts (mainly tick labels).
    for t in ax.texts:
        if t.get_gid() == "qsim_channel_label":
            continue
        tr = t.get_transform()
        if tr != ax.transData:
            continue
        s = t.get_text()
        if not s:
            continue
        fs_pt = float(t.get_fontsize())
        fs_mm = fs_pt * DEFAULT_DXF_TEXT_SCALE
        x, y = t.get_position()
        msp.add_text(
            s,
            dxfattribs={"height": fs_mm, "layer": "TEXT", "style": "TNR"},
        ).set_placement(
            _map_xy(float(x), float(y)),
            align=_align_from_ha_va(str(t.get_ha()), str(t.get_va())),
        )

    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    doc.saveas(out)
    return out


def _build_dxf_style_from_theme(
    *,
    theme: dict[str, float | int | bool | str],
    title: str,
    show_clock: bool,
    clock_mhz: float,
    breaks: list[tuple[float, float]],
    carrier_plot_max_hz: float | None,
    dxf_style: dict | None,
    channel_label_fontsize: int,
    tick_fontsize: int,
    axis_label_fontsize: int,
    title_fontsize: int,
    carrier_samples_per_cycle: int,
    major_ticks: list[float] | None = None,
    target_ticks: int = DEFAULT_TARGET_TICKS,
) -> dict:
    """Build legacy drawer style from timing theme values."""
    text_scale = max(0.1, float(theme["dxf_text_scale"]))
    style = {
        "title": title,
        "clk_mhz": clock_mhz if show_clock else None,
        "breaks": [{"t0": float(a), "t1": float(b), "marker": "ellipsis"} for a, b in breaks],
        "x_scale": float(theme["dxf_x_scale"]),
        "row_gap": float(theme["dxf_row_gap"]),
        "amp_scale": float(theme["dxf_amp_scale"]),
        "left_margin": float(theme["dxf_left_margin"]),
        "top_margin": float(theme["dxf_top_margin"]),
        "baseline_extend_mm": float(theme["dxf_baseline_extend_mm"]),
        "channel_label_h": float(channel_label_fontsize) * text_scale,
        "tick_label_h": float(tick_fontsize) * text_scale,
        "axis_label_h": float(axis_label_fontsize) * text_scale,
        "title_h": float(title_fontsize) * text_scale,
        "carrier_plot_max_hz": carrier_plot_max_hz if carrier_plot_max_hz is not None else DEFAULT_CARRIER_PLOT_MAX_HZ,
        "samples_per_cycle": max(4, int(carrier_samples_per_cycle // 2)),
        "t0_line_top_extra_mm": float(theme["dxf_t0_line_top_extra_mm"]),
        "edge_break_marker": str(theme["dxf_edge_break_marker"]),
        "show_edge_break_markers": False,
        "target_ticks": max(2, int(target_ticks)),
        "minor_per_major": 1,
        "major_ticks": major_ticks if major_ticks is not None else [],
    }
    if dxf_style:
        style.update(dxf_style)
    return style


def plot_pulses(
    pulse_ir: PulseIR,
    sample_rate: float = 1.0,
    show_carrier: bool = True,
    carrier_undersample: int = 32,
    carrier_points_per_pulse: int = 800,
    timing_layout: bool = False,
    title: str | None = None,
    breaks: list[tuple[float, float]] | list[dict] | None = None,
    auto_break_idle: bool = False,
    auto_break_pulses: bool = False,
    auto_fold_idle: bool = False,
    auto_fold_breakable: bool = False,
    idle_threshold_ns: float = 50_000.0,
    keep_edge_ns: float = 1_500.0,
    show_clock: bool = False,
    clock_mhz: float = DEFAULT_CLOCK_MHZ,
    carrier_plot_max_hz: float | None = None,
    carrier_samples_per_cycle: int = DEFAULT_CARRIER_SAMPLES_PER_CYCLE,
    envelope_points_per_pulse: int = DEFAULT_ENVELOPE_POINTS_PER_PULSE,
    black_white: bool = False,
    uppercase: bool = False,
    channel_label_fontsize: int = DEFAULT_CHANNEL_LABEL_FONTSIZE,
    tick_fontsize: int = DEFAULT_TICK_FONTSIZE,
    title_fontsize: int = DEFAULT_TITLE_FONTSIZE,
    axis_label_fontsize: int = DEFAULT_AXIS_LABEL_FONTSIZE,
    break_display_gap_ns: float = DEFAULT_BREAK_DISPLAY_GAP_NS,
    show_grid: bool = False,
    hide_top_right_spines: bool = True,
    dxf_path: str | Path | None = None,
    png_path: str | Path | None = None,
    dxf_style: dict | None = None,
    theme: dict | None = None,
    dxf_from_figure: bool = True,
    annotate_pulses: bool = True,
    pulse_label_fontsize: int = 8,
    pulse_metadata_path: str | Path | None = None,
    post_sequence_gap_ns: float = DEFAULT_POST_SEQUENCE_GAP_NS,
    target_ticks: int = DEFAULT_TARGET_TICKS,
    XYZ_line_combine: bool = False,
):
    """
    Plot pulse waveforms and optionally export a DXF engineering drawing.

    This function supports two plotting modes:
    - `timing_layout=False`: legacy compact waveform view sampled at fixed `sample_rate`.
    - `timing_layout=True`: timing-diagram view with per-channel rows, optional time breaks,
      clock lane, custom typography/colors, and optional DXF export.

    Parameters
    - `pulse_ir`: Pulse schedule to visualize.
    - `sample_rate`: Fixed sample rate for legacy mode (`timing_layout=False`).
    - `show_carrier`: Whether to draw carrier components.
    - `carrier_undersample`: Legacy mode carrier decimation factor.
    - `carrier_points_per_pulse`: Legacy mode sampling points per pulse for carrier.
    - `timing_layout`: Enable timing-diagram style plot.
    - `title`: Figure title. If `None`, a default title is used.
    - `breaks`: Explicit break windows. Accepts `(t0, t1)` tuples or dicts with
      `t0/t1`.
    - `auto_break_idle`: Auto-generate break windows for long all-channel idle regions when
      `breaks` is not provided.
    - `auto_break_pulses`: Auto-generate break windows only from pulses explicitly marked
      as breakable by lowering/catalog metadata.
    - `auto_fold_idle`: Backward-compatible alias for `auto_break_idle`.
    - `auto_fold_breakable`: Backward-compatible alias for `auto_break_pulses`.
    - `idle_threshold_ns`: Minimum idle duration for `auto_break_idle`.
    - `keep_edge_ns`: Keep this amount near both sides when inserting idle breaks.
    - `show_clock`: Add top `CLK` lane in timing mode.
    - `clock_mhz`: Clock frequency for the `CLK` lane.
    - `carrier_plot_max_hz`: Visualization cap for carrier frequency to avoid over-dense lines.
    - `carrier_samples_per_cycle`: Samples per carrier cycle in timing mode.
    - `envelope_points_per_pulse`: Minimum envelope sample points per visible segment.
    - `black_white`: Use monochrome styling.
    - `uppercase`: Uppercase channel labels/title text.
    - `channel_label_fontsize`: Font size of channel row labels.
    - `tick_fontsize`: Font size of custom time tick labels.
    - `title_fontsize`: Plot title font size.
    - `axis_label_fontsize`: Time axis label font size.
    - `break_display_gap_ns`: Visual gap width for each break segment in timing mode.
    - `show_grid`: Whether to show background grid.
    - `hide_top_right_spines`: Hide matplotlib top/right frame spines.
    - `dxf_path`: If provided, export DXF using the same `pulse_ir` and break settings.
    - `png_path`: Optional output path to save the rendered matplotlib figure as PNG.
      If provided, `fig.savefig(png_path)` is executed inside this function.
    - `dxf_style`: Optional style overrides passed to DXF renderer.
    - `theme`: Unified timing theme dict that drives both matplotlib and DXF styles.
    - `dxf_from_figure`: If `True` in timing layout, export DXF by extracting primitives
      directly from the matplotlib figure for maximal visual consistency.
    - `annotate_pulses`: In timing layout, annotate each pulse with sequential ids
      (`p1`, `p2`, ...).
    - `pulse_label_fontsize`: Font size for pulse id annotations.
    - `pulse_metadata_path`: If set, write a JSON file containing all pulse metadata,
      including timing, amplitude, shape, params, and carrier values (if present).
    - `post_sequence_gap_ns`: Keep this zero-amplitude tail after the last pulse to
      indicate experiment end.
    - `target_ticks`: Target number of major ticks on time axis in timing layout.
    - `XYZ_line_combine`: If `True`, display `XY_i` and `Z_i` on a merged `XYZ_i`
      row in timing layout without changing the underlying metadata channels.

    Returns
    - `matplotlib.figure.Figure`: Generated figure object.

    Notes
    - Time-break markers use dotted lines in matplotlib output.
    """
    if timing_layout:
        resolved_theme = make_timing_theme(**(theme or {}))
        if theme is None:
            resolved_theme["black_white"] = black_white
            resolved_theme["uppercase"] = uppercase
            resolved_theme["channel_label_fontsize"] = channel_label_fontsize
            resolved_theme["tick_fontsize"] = tick_fontsize
            resolved_theme["title_fontsize"] = title_fontsize
            resolved_theme["axis_label_fontsize"] = axis_label_fontsize
            resolved_theme["break_display_gap_ns"] = break_display_gap_ns
            resolved_theme["carrier_samples_per_cycle"] = carrier_samples_per_cycle
            resolved_theme["envelope_points_per_pulse"] = envelope_points_per_pulse
            resolved_theme["show_grid"] = show_grid
            resolved_theme["hide_top_right_spines"] = hide_top_right_spines

        parsed_breaks = _parse_breaks(breaks)
        use_auto_break_idle = bool(auto_break_idle or auto_fold_idle)
        use_auto_break_pulses = bool(auto_break_pulses or auto_fold_breakable)
        if use_auto_break_idle:
            parsed_breaks.extend(
                auto_break_idle_windows(
                    pulse_ir,
                    idle_threshold_ns=idle_threshold_ns,
                    keep_edge_ns=keep_edge_ns,
                )
            )
        if use_auto_break_pulses:
            parsed_breaks.extend(auto_break_long_pulses(pulse_ir))
        parsed_breaks = _merge_intervals(parsed_breaks)
        # Keep DXF tick placement consistent with matplotlib timing axis.
        _last_t1 = 0.0
        for _ch in pulse_ir.channels:
            for _p in _ch.pulses:
                _last_t1 = max(_last_t1, float(_p.t1))
        _plot_t_end = min(float(pulse_ir.t_end), max(0.0, _last_t1))
        if _plot_t_end <= 0.0:
            _plot_t_end = float(pulse_ir.t_end)
        _ticks_for_dxf = _build_time_ticks(_plot_t_end, parsed_breaks, target_ticks=max(2, int(target_ticks)))
        fig = _plot_pulses_timing(
            pulse_ir,
            show_carrier=show_carrier,
            title=title,
            breaks=parsed_breaks,
            show_clock=show_clock,
            clock_mhz=clock_mhz,
            carrier_plot_max_hz=carrier_plot_max_hz,
            carrier_samples_per_cycle=int(resolved_theme["carrier_samples_per_cycle"]),
            envelope_points_per_pulse=int(resolved_theme["envelope_points_per_pulse"]),
            black_white=bool(resolved_theme["black_white"]),
            uppercase=bool(resolved_theme["uppercase"]),
            channel_label_fontsize=int(resolved_theme["channel_label_fontsize"]),
            tick_fontsize=int(resolved_theme["tick_fontsize"]),
            title_fontsize=int(resolved_theme["title_fontsize"]),
            axis_label_fontsize=int(resolved_theme["axis_label_fontsize"]),
            break_display_gap_ns=float(resolved_theme["break_display_gap_ns"]),
            show_grid=bool(resolved_theme["show_grid"]),
            hide_top_right_spines=bool(resolved_theme["hide_top_right_spines"]),
            font_family=str(resolved_theme["font_family"]),
            annotate_pulses=annotate_pulses,
            pulse_label_fontsize=int(pulse_label_fontsize),
            post_sequence_gap_ns=float(post_sequence_gap_ns),
            target_ticks=max(2, int(target_ticks)),
            XYZ_line_combine=bool(XYZ_line_combine),
        )
        if pulse_metadata_path is not None:
            payload = {
                "schema": "qsim.pulse-metadata.v1",
                "count": len(getattr(fig, "_qsim_pulse_metadata", [])),
                "pulses": list(getattr(fig, "_qsim_pulse_metadata", [])),
            }
            dump_json(pulse_metadata_path, payload)
        if dxf_path is not None:
            if dxf_from_figure:
                _export_timing_figure_to_dxf(fig, dxf_path)
            else:
                from qsim.pulse.drawer_adapter import EngineeringDrawer
                style = _build_dxf_style_from_theme(
                    theme=resolved_theme,
                    title=(title or "Pulse Timing"),
                    show_clock=show_clock,
                    clock_mhz=clock_mhz,
                    breaks=parsed_breaks,
                    carrier_plot_max_hz=carrier_plot_max_hz,
                    dxf_style=dxf_style,
                    channel_label_fontsize=int(resolved_theme["channel_label_fontsize"]),
                    tick_fontsize=int(resolved_theme["tick_fontsize"]),
                    axis_label_fontsize=int(resolved_theme["axis_label_fontsize"]),
                    title_fontsize=int(resolved_theme["title_fontsize"]),
                    carrier_samples_per_cycle=int(resolved_theme["carrier_samples_per_cycle"]),
                    major_ticks=_ticks_for_dxf,
                    target_ticks=max(2, int(target_ticks)),
                )
                EngineeringDrawer.export_dxf(pulse_ir, dxf_path, style=style)
        if png_path is not None:
            Path(png_path).parent.mkdir(parents=True, exist_ok=True)
            fig.savefig(png_path, dpi=180)
        return fig

    import matplotlib.pyplot as plt

    samples = PulseCompiler.compile(pulse_ir, sample_rate=sample_rate)
    fig, ax = plt.subplots(figsize=(10, 4))
    for name, payload in samples.items():
        ax.plot(payload["t"], payload["y"], label=f"{name} envelope")

    if show_carrier:
        us = max(1, int(carrier_undersample))
        carrier_labeled: set[str] = set()
        for ch in pulse_ir.channels:
            for p in ch.pulses:
                if p.carrier is None:
                    continue
                n = max(64, int(carrier_points_per_pulse))
                t = np.linspace(float(p.t0), float(p.t1), n)
                shape = make_shape(p.shape, p.params)
                env = np.asarray([shape.sample(float(ti), p.t0, p.t1, p.amp) for ti in t], dtype=float)
                freq = float(getattr(p.carrier, "freq", 0.0))
                phase = float(getattr(p.carrier, "phase", 0.0))
                sig = env * np.cos(2.0 * np.pi * freq * (t * 1e-9) + phase)
                idx = np.arange(0, n, us, dtype=int)
                label = f"{ch.name} carrier(us={us})" if ch.name not in carrier_labeled else None
                ax.plot(t[idx], sig[idx], alpha=0.45, lw=0.9, label=label)
                carrier_labeled.add(ch.name)

    title_text = "Pulse Waveforms"
    if show_carrier:
        title_text += f" (carrier undersample={max(1, int(carrier_undersample))})"
    ax.set_title(title_text)
    ax.set_xlabel("t")
    ax.set_ylabel("amp")
    ax.legend()
    fig.tight_layout()
    if dxf_path is not None:
        from qsim.pulse.drawer_adapter import EngineeringDrawer

        style = {
            "title": (title or "Pulse Waveforms"),
            "clk_mhz": None,
            "breaks": [],
            "x_scale": DEFAULT_DXF_X_SCALE,
            "row_gap": DEFAULT_DXF_ROW_GAP,
            "amp_scale": DEFAULT_DXF_AMP_SCALE,
            "edge_break_marker": "ellipsis",
        }
        if dxf_style:
            style.update(dxf_style)
        EngineeringDrawer.export_dxf(pulse_ir, dxf_path, style=style)
    if png_path is not None:
        Path(png_path).parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(png_path, dpi=180)
    return fig


def plot_trace(trace: Trace):
    """Plot trace state trajectories versus simulation time."""
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(figsize=(10, 4))
    if trace.states:
        for i in range(len(trace.states[0])):
            ax.plot(trace.times, [s[i] for s in trace.states], label=f"state[{i}]")
    ax.set_title(f"Trace ({trace.engine})")
    ax.set_xlabel("t")
    ax.legend()
    fig.tight_layout()
    return fig


def plot_report(report: dict):
    """Plot error budget bar chart from analysis report."""
    import matplotlib.pyplot as plt

    err = report.get("error_budget", {})
    labels = list(err.keys())
    vals = [err[k] for k in labels]
    fig, ax = plt.subplots(figsize=(8, 4))
    ax.bar(labels, vals)
    ax.set_title("Error Budget")
    fig.tight_layout()
    return fig


def save_observables_plot(observables: Observables, out_path: str | Path):
    """Save observables values as a bar chart image file."""
    import matplotlib.pyplot as plt

    labels = list(observables.values.keys())
    vals = [observables.values[k] for k in labels]
    fig, ax = plt.subplots(figsize=(8, 4))
    ax.bar(labels, vals)
    fig.tight_layout()
    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path)
    plt.close(fig)


def load_trace_h5(path: str | Path) -> Trace:
    """Load ``Trace`` from HDF5 file written by workflow artifacts."""
    import h5py

    with h5py.File(path, "r") as h5:
        times = h5["times"][:].tolist()
        states = h5["states"][:].tolist()
        engine = h5.attrs.get("engine", "unknown")
    return Trace(engine=engine, times=times, states=states)


def dump_json(path: str | Path, payload: dict):
    """Dump JSON payload with UTF-8 and pretty indentation."""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _flatten_row(prefix: str, value, out: dict[str, str]) -> None:
    """Flatten nested dict/list values into a single-level row map."""
    if isinstance(value, dict):
        for k, v in value.items():
            key = f"{prefix}.{k}" if prefix else str(k)
            _flatten_row(key, v, out)
        return
    if isinstance(value, list):
        out[prefix] = json.dumps(value, ensure_ascii=False)
        return
    out[prefix] = "" if value is None else str(value)


def export_json_table(
    json_path: str | Path,
    out_path: str | Path,
    *,
    rows_key: str | None = None,
) -> Path:
    """Export JSON rows into CSV or XLSX table.

    Auto-detect row source:
    - top-level list => rows
    - top-level dict with key `rows_key` (or `pulses` by default) as list => rows
    - otherwise => single-row table
    """
    src = Path(json_path)
    payload = json.loads(src.read_text(encoding="utf-8"))
    rows_raw = None
    if isinstance(payload, list):
        rows_raw = payload
    elif isinstance(payload, dict):
        key = str(rows_key) if rows_key else ("pulses" if isinstance(payload.get("pulses"), list) else None)
        if key is not None and isinstance(payload.get(key), list):
            rows_raw = payload.get(key)
        else:
            rows_raw = [payload]
    else:
        rows_raw = [{"value": payload}]

    rows: list[dict[str, str]] = []
    for item in rows_raw:
        flat: dict[str, str] = {}
        if isinstance(item, dict):
            _flatten_row("", item, flat)
        else:
            flat["value"] = str(item)
        rows.append(flat)

    headers: list[str] = []
    seen: set[str] = set()
    for r in rows:
        for k in r.keys():
            if k not in seen:
                seen.add(k)
                headers.append(k)

    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    suffix = out.suffix.lower()
    if suffix == ".csv":
        with out.open("w", newline="", encoding="utf-8-sig") as f:
            writer = csv.DictWriter(f, fieldnames=headers, extrasaction="ignore")
            writer.writeheader()
            for r in rows:
                writer.writerow({h: r.get(h, "") for h in headers})
        return out
    if suffix == ".xlsx":
        try:
            from openpyxl import Workbook
        except Exception as exc:
            raise RuntimeError("导出 xlsx 需要 openpyxl，请先安装。") from exc
        wb = Workbook()
        ws = wb.active
        ws.title = "table"
        ws.append(headers)
        for r in rows:
            ws.append([r.get(h, "") for h in headers])
        wb.save(out)
        return out
    raise ValueError("Unsupported output extension. Use .csv or .xlsx")
