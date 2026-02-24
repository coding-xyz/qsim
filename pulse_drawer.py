# timing_diagram_to_dxf_v6_4.py
# pip install ezdxf

from __future__ import annotations
from dataclasses import dataclass, field
from typing import List, Literal, Optional, Tuple, Union
import math
import ezdxf

# ============================================================
# Data model
# ============================================================
Point = Tuple[float, float]
Interval = Tuple[float, float]

BreakMarker = Literal["double_s", "ellipsis"]

@dataclass
class Break:
    t0: float
    t1: float
    marker: BreakMarker = "double_s"

BreakSpec = Union[Interval, Break]

@dataclass
class Carrier:
    frequency: float  # Carrier wave frequency
    phase: float      # Carrier wave phase

@dataclass
class Pulse:
    t0: float
    t1: float
    amp: float = 1.0
    kind: str = "rect"  # "rect" | "gaussian" | "readout" | "dc"
    carrier: Optional[Carrier] = None  # Optional carrier for RF pulses

@dataclass
class Channel:
    name: str
    pulses: List[Pulse] = field(default_factory=list)
    baseline: float = 0.0
    show_baseline: bool = True

@dataclass
class Sequence:
    title: str
    t_end: float
    channels: List[Channel]
    clk_mhz: Optional[float] = None
    breaks: List[BreakSpec] = field(default_factory=list)


# ============================================================
# DXF primitives
# ============================================================
def ensure_linetypes(doc: ezdxf.EzDxf):
    if "JIS_02_0.7" not in doc.linetypes:
        doc.linetypes.new(
            "JIS_02_0.7",
            dxfattribs={
                "description": "JIS short dash",
                "pattern": [1.4, 0.7, -0.7],
            },
        )
    if "DASHED" not in doc.linetypes:
        doc.linetypes.new(
            "DASHED",
            dxfattribs={
                "description": "Dashed _ _ _",
                "pattern": [1.6, 0.7, -0.7],
            },
        )

def polyline(msp, pts, *, layer="WAVE", closed=False, linetype: Optional[str] = None):
    if len(pts) < 2:
        return
    attribs = {"layer": layer, "closed": int(closed), "flags": 128}
    if linetype:
        attribs["linetype"] = linetype
    msp.add_lwpolyline(pts, dxfattribs=attribs)


def add_text(msp, x, y, s, *, h=2.5, layer="TEXT", style="TNR"):
    msp.add_text(s, dxfattribs={"height": h, "layer": layer, "style": style}).set_placement((x, y))


# ============================================================
# B茅zier break marker (double-S, vertical)
# ============================================================
def cubic_bezier(p0, p1, p2, p3, t: float):
    u = 1.0 - t
    x = (u**3) * p0[0] + 3 * (u**2) * t * p1[0] + 3 * u * (t**2) * p2[0] + (t**3) * p3[0]
    y = (u**3) * p0[1] + 3 * (u**2) * t * p1[1] + 3 * u * (t**2) * p2[1] + (t**3) * p3[1]
    return x, y


def sample_cubic_bezier(p0, p1, p2, p3, n=48):
    return [cubic_bezier(p0, p1, p2, p3, i / n) for i in range(n + 1)]


def draw_break_marker_doubleS_vertical_bezier(
    msp,
    x_center: float,
    y_center: float,
    *,
    height: float = 5.2,
    width: float = 1.8,
    gap: float = 2.0,
    n: int = 48,
    layer="WAVE",
):
    y0 = y_center - 0.5 * height
    y1 = y_center + 0.5 * height

    def one_S(xc: float):
        p0 = (xc, y0)
        p1 = (xc + width, y0 + 0.25 * height)
        p2 = (xc - width, y0 + 0.75 * height)
        p3 = (xc, y1)
        pts = sample_cubic_bezier(p0, p1, p2, p3, n=n)
        polyline(msp, pts, layer=layer, linetype=None)

    one_S(x_center - 0.5 * gap)
    one_S(x_center + 0.5 * gap)


def draw_break_marker_doubleS_vertical_arcs(
    msp,
    x_center: float,
    y_center: float,
    *,
    height: float = 5.2,
    width: float = 1.8,
    gap: float = 2.0,
    layer="WAVE",
):
    # Draw each "S" by two arc entities to reduce sampled polyline density.
    def one_S(xc: float) -> None:
        r = max(0.01, 0.25 * height)
        y_up = y_center + r
        y_dn = y_center - r
        msp.add_arc((xc, y_up), r, start_angle=210.0, end_angle=30.0, dxfattribs={"layer": layer})
        msp.add_arc((xc, y_dn), r, start_angle=30.0, end_angle=210.0, dxfattribs={"layer": layer})

    one_S(x_center - 0.5 * gap)
    one_S(x_center + 0.5 * gap)


def draw_break_marker_ellipsis(
    msp,
    x_center: float,
    y_center: float,
    *,
    dot_diameter: float = 0.55,
    dot_gap: float = 0.65,
    layer="WAVE",
):
    # Draw filled round-ish dots as solid hatch polygons.
    r = max(0.01, 0.5 * dot_diameter)
    step = dot_diameter + dot_gap
    n = 14
    for dx in (-step, 0.0, step):
        c = (x_center + dx, y_center)
        verts = []
        for k in range(n):
            a = 2.0 * math.pi * k / n
            verts.append((c[0] + r * math.cos(a), c[1] + r * math.sin(a)))
        hatch = msp.add_hatch(color=7, dxfattribs={"layer": layer})
        hatch.set_solid_fill(color=7)
        hatch.paths.add_polyline_path(verts, is_closed=True)


# ============================================================
# Global time-warp
# ============================================================
def normalize_breaks(breaks: List[BreakSpec]) -> List[Break]:
    norm: List[Break] = []
    for b in breaks:
        if isinstance(b, Break):
            t0, t1 = float(b.t0), float(b.t1)
            marker = b.marker if b.marker in ("double_s", "ellipsis") else "ellipsis"
        else:
            t0, t1 = float(b[0]), float(b[1])
            marker = "ellipsis"
        if t1 > t0:
            norm.append(Break(t0=t0, t1=t1, marker=marker))
    norm.sort(key=lambda z: z.t0)
    return norm


class TimeWarp:
    def __init__(self, breaks: List[BreakSpec], x_scale: float):
        self.break_defs = normalize_breaks(breaks)
        self.breaks = [(b.t0, b.t1) for b in self.break_defs]
        self.x_scale = float(x_scale)

    def map_t_to_x(self, t_ns: float, left_margin: float) -> float:
        t = float(t_ns)
        skipped = 0.0
        for b0, b1 in self.breaks:
            if b0 < t < b1:
                raise ValueError(f"t={t}ns falls inside break [{b0},{b1})")
            if t >= b1:
                skipped += (b1 - b0)
            else:
                break
        eff = max(0.0, t - skipped)
        return left_margin + eff * self.x_scale


    def clip_interval(self, t0: float, t1: float) -> List[Interval]:
        """Remove time that falls inside breaks (so waveform is not drawn through skipped region)."""
        a, b = float(t0), float(t1)
        if b <= a:
            return []
        segs = [(a, b)]
        for b0, b1 in self.breaks:
            new = []
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
        return [(s0, s1) for s0, s1 in segs if s1 > s0]

    def break_spans_x(self, left_margin: float) -> List[Tuple[float, float, float]]:
        spans = []
        for b0, b1 in self.breaks:
            xL = self.map_t_to_x(b0, left_margin)
            xR = self.map_t_to_x(b1, left_margin)
            xC = 0.5 * (xL + xR)
            spans.append((xL, xC, xR))
        return spans


# ============================================================
# Break holes & polyline cutter
# ============================================================
def make_break_holes_from_centers(break_centers_x: List[float], gap_mm: float) -> List[Interval]:
    holes = [(xC - 0.5 * gap_mm, xC + 0.5 * gap_mm) for xC in break_centers_x]
    holes.sort()
    merged = []
    for a, b in holes:
        if not merged or a > merged[-1][1]:
            merged.append([a, b])
        else:
            merged[-1][1] = max(merged[-1][1], b)
    return [(a, b) for a, b in merged]


def lerp(p0, p1, t: float):
    return (p0[0] + (p1[0] - p0[0]) * t, p0[1] + (p1[1] - p0[1]) * t)

def segment_polyline_simple(pts: List[Point], holes: List[Interval]) -> List[List[Point]]:
    if len(pts) < 2:
        return []

    forbidden = sorted(holes)
    boundaries = [x for ab in forbidden for x in ab]
    boundaries = set(boundaries)

    def in_forbidden(x: float) -> bool:
        for a, b in forbidden:
            if a <= x <= b:
                return True
        return False

    def interp(p0: Point, p1: Point, x: float) -> Point:
        x0, y0 = p0
        x1, y1 = p1
        if abs(x1 - x0) < 1e-12:
            return (x, y0)
        t = (x - x0) / (x1 - x0)
        return (x, y0 + (y1 - y0) * t)

    segs: List[List[Point]] = []
    cur: List[Point] = []

    for i in range(len(pts) - 1):
        p0, p1 = pts[i], pts[i + 1]
        x0, _ = p0
        x1, _ = p1

        cuts = [x0, x1]
        lo, hi = (x0, x1) if x0 <= x1 else (x1, x0)
        for a, b in forbidden:
            if b < lo or a > hi:
                continue
            if lo <= a <= hi: cuts.append(a)
            if lo <= b <= hi: cuts.append(b)

        # 椤虹潃绾挎鏂瑰悜鎺掑簭锛堥伩鍏?x1<x0 鏃朵贡搴忥級
        cuts = sorted(set(cuts))
        if x1 < x0:
            cuts = list(reversed(cuts))

        for j in range(len(cuts) - 1):
            xa, xb = cuts[j], cuts[j + 1]
            xm = 0.5 * (xa + xb)
            if in_forbidden(xm):
                if len(cur) >= 2:
                    segs.append(cur)
                cur = []
                continue

            qa = interp(p0, p1, xa)
            qb = interp(p0, p1, xb)

            if (xa in boundaries or xb in boundaries) and abs(xb - xa) <= 1e-12:
                continue

            if not cur:
                cur.append(qa)
            else:
                if cur[-1] != qa:
                    cur.append(qa)
            cur.append(qb)

    if len(cur) >= 2:
        segs.append(cur)
    return segs

def draw_polyline_with_breaks(
    msp,
    pts: List[Point],
    *,
    holes: List[Interval],
    layer="WAVE",
    linetype: Optional[str] = None,
):
    segs = segment_polyline_simple(pts, holes)
    for s in segs:
        polyline(msp, s, layer=layer, linetype=linetype)


# ============================================================
# Waveform builders: build FULL channel polylines then cut+draw
# ============================================================
from typing import Callable

# 杩斿洖涓€涓嚱鏁?env01(t_ns)->[0,1]锛屽苟涓旇姹?env01(a)=env01(b)=0锛堟柟渚胯繛鎺?baseline锛?
EnvelopeFactory = Callable[[float, float], Callable[[float], float]]
# EnvelopeFactory(a_ns, b_ns) -> env01(t_ns)

def gaussian_env_factory(sigma_div: float = 6.0) -> EnvelopeFactory:
    def make(a: float, b: float):
        dur = b - a
        mu = 0.5 * (a + b)
        sigma = max(1e-12, dur / sigma_div)
        g0 = math.exp(-0.5 * ((a - mu) / sigma) ** 2)
        denom = max(1e-12, 1.0 - g0)

        def env01(t: float) -> float:
            g = math.exp(-0.5 * ((t - mu) / sigma) ** 2)
            return max(0.0, (g - g0) / denom)  # edges -> 0
        return env01
    return make

def rect_env_factory() -> EnvelopeFactory:
    def make(a: float, b: float):
        # 濡傛灉浣犲笇鏈涜竟鐣屼负0骞朵笖涓棿涓?锛岄偅灏卞仛涓€涓€滃甫杈规部鈥濈殑鏂规尝锛?
        # 杩欓噷缁欐渶绠€鍗曪細鍐呴儴=1锛岃竟鐣岀偣=0锛堜繚璇佽繛鎺?baseline锛夈€?
        def env01(t: float) -> float:
            if t <= a or t >= b:
                return 0.0
            return 1.0
        return env01
    return make

def build_env_x_polylines(
    *,
    warp: TimeWarp,
    left_margin: float,
    t_start: float,
    t_end: float,
    y_base: float,
    height: float,
    pulses: List[Pulse],
    envelope_factory: EnvelopeFactory,
    samples_per_pulse: int = 240,
) -> List[Point]:
    x0 = warp.map_t_to_x(t_start, left_margin)
    xE = warp.map_t_to_x(t_end, left_margin)

    pts: List[Point] = [(x0, y_base)]
    cur_x = x0

    ps = sorted(pulses, key=lambda p: p.t0)

    for p in ps:
        for a, b in warp.clip_interval(p.t0, p.t1):
            a = max(t_start, a)
            b = min(t_end, b)
            if b <= a:
                continue

            xL = warp.map_t_to_x(a, left_margin)
            xR = warp.map_t_to_x(b, left_margin)
            if xR <= xL + 1e-9:
                continue

            # baseline connect锛堝彧鍦ㄩ渶瑕佹椂锛?
            if xL > cur_x + 1e-12:
                pts.append((xL, y_base))
                cur_x = xL

            env01 = envelope_factory(a, b)
            dur = b - a
            n = int(max(2, samples_per_pulse))

            for i in range(n):
                t = a + dur * i / (n - 1)
                x = warp.map_t_to_x(t, left_margin)
                if pts and abs(x - pts[-1][0]) < 1e-12:
                    continue
                A_env = height * p.amp * float(env01(t))
                pts.append((x, y_base + A_env))

            # 鍥炲埌 baseline
            pts.append((xR, y_base))
            cur_x = xR

    if cur_x < xE - 1e-12:
        pts.append((xE, y_base))

    return pts

def build_env_and_carrier_x_polylines(
    *,
    warp: TimeWarp,
    left_margin: float,
    t_start: float,
    t_end: float,
    y_base: float,
    height: float,
    pulses: List[Pulse],
    envelope_factory: EnvelopeFactory,
    samples_per_cycle: int = 24,
    carrier_plot_max_hz: Optional[float] = None,
) -> Tuple[List[Point], List[Point]]:

    x0 = warp.map_t_to_x(t_start, left_margin)
    xE = warp.map_t_to_x(t_end, left_margin)

    env_pts: List[Point] = [(x0, y_base)]
    car_pts: List[Point] = [(x0, y_base)]
    cur_x = x0

    ps = sorted([p for p in pulses if p.carrier is not None], key=lambda p: p.t0)

    for p in ps:
        f = float(p.carrier.frequency)
        if carrier_plot_max_hz is not None:
            f = min(f, max(1.0, float(carrier_plot_max_hz)))
        phi = float(p.carrier.phase)

        for a, b in warp.clip_interval(p.t0, p.t1):
            a = max(t_start, a)
            b = min(t_end, b)
            if b <= a:
                continue

            xL = warp.map_t_to_x(a, left_margin)
            xR = warp.map_t_to_x(b, left_margin)
            if xR <= xL + 1e-9:
                continue

            if xL > cur_x + 1e-12:
                env_pts.append((xL, y_base))
                car_pts.append((xL, y_base))
                cur_x = xL

            env01 = envelope_factory(a, b)
            dur = b - a

            cycles = max(1.0, f * (dur * 1e-9))
            n = int(max(60, min(20000, math.ceil(cycles * samples_per_cycle) + 1)))

            for i in range(n):
                t = a + dur * i / (n - 1)
                x = warp.map_t_to_x(t, left_margin)
                if env_pts and abs(x - env_pts[-1][0]) < 1e-12:
                    continue

                A_env = height * p.amp * float(env01(t))
                env_pts.append((x, y_base + A_env))
                car_pts.append((x, y_base + A_env * math.sin(2 * math.pi * f * (t * 1e-9) + phi)))

            env_pts.append((xR, y_base))
            car_pts.append((xR, y_base))
            cur_x = xR

    if cur_x < xE - 1e-12:
        env_pts.append((xE, y_base))
        car_pts.append((xE, y_base))

    return env_pts, car_pts

# ============================================================
# Clock builder (unchanged approach: build in TIME->X then cut)
# ============================================================
def build_clock_step_polyline(
    warp,
    *,
    left_margin: float,
    y0: float,
    amp: float,
    mhz: float,
    t_end_ns: float,
    rising_edge_at_t0: bool = True,
) -> List[Point]:
    """
    Build clock in X-domain to avoid duplicated X inside break regions.
    The polyline will later be cut by holes (break markers), so we don't need
    to special-case break spans here.
    """
    if mhz <= 0:
        raise ValueError("mhz must be > 0")

    # half period in ns, then convert to mm via x_scale (mm/ns)
    half_ns = (1000.0 / mhz) / 2.0
    half_mm = half_ns * float(warp.x_scale)

    # x start/end already include break gaps via warp.map_t_to_x
    x0 = warp.map_t_to_x(0.0, left_margin)
    x_end = warp.map_t_to_x(t_end_ns, left_margin)

    pts: List[Point] = []

    # initial level and optional rising edge at t=0
    if rising_edge_at_t0:
        pts.append((x0, y0 + 0.0))
        pts.append((x0, y0 + amp))
        level = 1
    else:
        pts.append((x0, y0 + 0.0))
        level = 0

    # step along X with constant half period
    eps = 1e-9
    x_next = x0 + half_mm

    while x_next <= x_end + eps:
        x_t = min(x_next, x_end)

        # horizontal to next edge
        pts.append((x_t, y0 + (amp if level else 0.0)))

        # vertical toggle (avoid adding a zero-length vertical at the very end)
        if x_t < x_end - eps:
            level ^= 1
            pts.append((x_t, y0 + (amp if level else 0.0)))

        x_next += half_mm

    # ensure it ends exactly at x_end
    if pts[-1][0] != x_end:
        pts.append((x_end, y0 + (amp if level else 0.0)))

    return pts

# ============================================================
# Smarter time ticks (unchanged)
# ============================================================
def nice_step_1_2_5(raw_step: float) -> float:
    if raw_step <= 0:
        return 1.0
    k = math.floor(math.log10(raw_step))
    base = raw_step / (10 ** k)
    if base <= 1.0:
        m = 1.0
    elif base <= 2.0:
        m = 2.0
    elif base <= 5.0:
        m = 5.0
    else:
        m = 10.0
    return m * (10 ** k)


def choose_tick_step(t_end_ns: float, target_ticks: int = 12) -> float:
    raw = t_end_ns / max(target_ticks, 1)
    step = nice_step_1_2_5(raw)
    while t_end_ns / step < 7 and step > 1:
        step /= 2
    return step

# def format_time_label(ns: float) -> str:
#     if ns >= 1000:
#         us = ns / 1000.0
#         if abs(us - round(us)) < 1e-6:
#             return f"{int(round(us))}碌s"
#         if us < 10:
#             return f"{us:.1f}碌s"
#         return f"{us:.0f}碌s"
#     return f"{int(round(ns))}ns"

def format_time_label(t_ns: float) -> str:
    v = int(round(t_ns))
    return "0" if v == 0 else f"{v}"

def time_regions_excluding_breaks(t_end_ns: float, breaks: List[Interval]) -> List[Interval]:
    regions = [(0.0, t_end_ns)]
    for b0, b1 in breaks:
        new = []
        for a, b in regions:
            if b <= b0 or a >= b1:
                new.append((a, b))
            else:
                if a < b0:
                    new.append((a, b0))
                if b > b1:
                    new.append((b1, b))
        regions = new
        if not regions:
            break
    return [(a, b) for a, b in regions if b > a]

from ezdxf.enums import TextEntityAlignment
def draw_time_axis_ticks(
    msp,
    warp: TimeWarp,
    *,
    t_end_ns: float,
    left_margin: float,
    y: float,
    breaks: List[Interval],
    holes: List[Interval],          # NEW: 鐢?holes 鏉ラ伩寮€ break marker
    text_style="TNR",
    font_h: float = 3.0,
    target_ticks: int = 12,
    minor_per_major: int = 5,
    hole_pad_mm: float = 0.2,                  # NEW: hole 鍛ㄥ洿棰濆鐣欎竴鐐圭┖
    major_ticks: Optional[List[float]] = None,
):
    visible_total = max(1e-9, t_end_ns - sum((b1 - b0) for b0, b1 in breaks))
    major_step = nice_step_1_2_5(visible_total / max(target_ticks, 1))
    tick_h_major = 0.75 * font_h
    label_h = 1.00 * font_h

    regions = time_regions_excluding_breaks(t_end_ns, breaks)
    eps = 1e-9

    def x_in_hole(x: float) -> bool:
        for a, b in holes:
            if (a - hole_pad_mm) <= x <= (b + hole_pad_mm):
                return True
        return False

    def draw_major(t: float):
        x = warp.map_t_to_x(t, left_margin)
        if x_in_hole(x):
            return

        # tick line
        msp.add_line(
            (x, y - tick_h_major),
            (x, y + tick_h_major),
            dxfattribs={"layer": "BASE"},
        )

        # label 鈥斺€?灞呬腑瀵归綈
        txt = msp.add_text(
            format_time_label(t),
            dxfattribs={
                "height": label_h,
                "layer": "TEXT",
                "style": text_style,
            },
        )
        txt.set_placement(
            (x, y - 1.45 * font_h),
            align=TextEntityAlignment.TOP_CENTER,   # 姘村钩灞呬腑
        )

    # 0 鍜?t_end 鐨?label 淇濈暀锛屼絾涔熻閬垮紑 hole
    draw_major(0.0)

    # Build major ticks using the same rule as matplotlib timing view.
    if major_ticks is None:
        ticks = [0.0]
        t = major_step
        while t < t_end_ns + eps:
            in_break = any((b0 < t < b1) for b0, b1 in breaks)
            if not in_break:
                ticks.append(t)
            t += major_step
        if not any((b0 < t_end_ns < b1) for b0, b1 in breaks):
            if all(abs(tv - t_end_ns) > eps for tv in ticks):
                ticks.append(t_end_ns)
    else:
        ticks = [float(tv) for tv in major_ticks]

    for t in sorted(set(round(v, 6) for v in ticks)):
        if t > 0.0 + eps and t <= t_end_ns + eps:
            draw_major(float(t))


# ============================================================
# Baseline
# ============================================================
def draw_baseline_with_break_holes(
    msp,
    x_left: float,
    x_right: float,
    y: float,
    *,
    holes: List[Interval],
    layer="BASE",
):
    cur = x_left
    for a, b in holes:
        if b <= x_left or a >= x_right:
            continue
        aa = max(a, x_left)
        bb = min(b, x_right)
        if aa > cur:
            msp.add_line((cur, y), (aa, y), dxfattribs={"layer": layer})
        cur = max(cur, bb)
    if cur < x_right:
        msp.add_line((cur, y), (x_right, y), dxfattribs={"layer": layer})


# ============================================================
# Renderer (major change: build full tracks then cut+draw)
# ============================================================
def render_sequence_to_dxf(
    seq: Sequence,
    out_path: str,
    *,
    x_scale: float = 1.0,
    row_gap: float = 26.0,
    amp_scale: float = 10.0,
    left_margin: float = 35.0,
    top_margin: float = 25.0,
    font_h: float = 3.0,
    channel_label_h: float = 8.0,
    tick_label_h: float = 6.0,
    axis_label_h: float = 8.0,
    title_h: float = 10.0,
    baseline_extend_mm: float = 14.0,

    channel_label_offset: Point = (-30.0, 0.0),

    marker_height_mm: float = 5.2,
    marker_width_mm: float = 1.8,
    marker_gap_mm: float = 4.8,
    ellipsis_dot_diameter_mm: float = 0.36,
    ellipsis_dot_gap_mm: float = 0.85,

    wave_gap_mm: float = 8.0,

    readout_carrier_period_mm: float = 1.6,
    xy_carrier_period_mm: float = 1.6,
    samples_per_cycle: int = 24,
    carrier_plot_max_hz: Optional[float] = 1e9,
    t0_line_top_extra_mm: float = 8.0,

    target_ticks: int = 12,
    minor_per_major: int = 5,
    edge_break_marker: str = "ellipsis",
    show_edge_break_markers: bool = False,
    ellipsis_offset_mm: float = 0.0,
    major_ticks: Optional[List[float]] = None,
):
    doc = ezdxf.new("R2010")
    msp = doc.modelspace()

    # Use explicit lineweights so exported drawings are visually legible.
    doc.layers.new("WAVE", dxfattribs={"color": 7, "lineweight": 40})
    doc.layers.new("BASE", dxfattribs={"color": 8, "lineweight": 30})
    doc.layers.new("TEXT", dxfattribs={"color": 7})
    doc.layers.new("CLK", dxfattribs={"color": 7, "lineweight": 45})

    if "TNR" not in doc.styles:
        doc.styles.new("TNR", dxfattribs={"font": "Times New Roman.ttf"})
    doc.header["$TEXTSTYLE"] = "TNR"
    doc.header["$PLINEGEN"] = 1
    ensure_linetypes(doc)

    warp = TimeWarp(seq.breaks, x_scale=x_scale)
    break_spans = warp.break_spans_x(left_margin)

    x0_main = warp.map_t_to_x(0.0, left_margin)
    x1_main = warp.map_t_to_x(seq.t_end, left_margin)
    x_left = x0_main - baseline_extend_mm
    x_right = x1_main + baseline_extend_mm

    xC_left_end = x0_main - 0.5 * baseline_extend_mm
    xC_right_end = x1_main + 0.5 * baseline_extend_mm

    break_centers_internal = [xC for (_xL, xC, _xR) in break_spans]
    internal_break_markers = [b.marker for b in warp.break_defs]
    break_centers_for_markers = ([xC_left_end, xC_right_end] if show_edge_break_markers else []) + break_centers_internal
    holes_marker_all = make_break_holes_from_centers(break_centers_for_markers, marker_gap_mm)
    holes_wave_all = make_break_holes_from_centers(break_centers_for_markers, wave_gap_mm)

    holes_wave_clock = make_break_holes_from_centers(break_centers_internal, wave_gap_mm)

    chan_h = channel_label_h
    pulse_label_h = 0.85 * font_h

    add_text(
        msp,
        left_margin,
        top_margin + row_gap * (len(seq.channels) + 1),
        seq.title,
        h=title_h,
        style="TNR",
    )

    def draw_markers_at_y(y_line: float):
        if show_edge_break_markers:
            for xC in (xC_left_end, xC_right_end):
                if str(edge_break_marker).lower() == "double_s":
                    draw_break_marker_doubleS_vertical_arcs(
                        msp, xC, y_line,
                        height=marker_height_mm,
                        width=marker_width_mm,
                        gap=marker_gap_mm,
                        layer="WAVE",
                    )
                else:
                    draw_break_marker_ellipsis(
                        msp, xC, y_line + ellipsis_offset_mm,
                        dot_diameter=ellipsis_dot_diameter_mm,
                        dot_gap=ellipsis_dot_gap_mm,
                        layer="WAVE",
                    )
        for xC, marker in zip(break_centers_internal, internal_break_markers):
            if marker == "ellipsis":
                draw_break_marker_ellipsis(
                    msp, xC, y_line + ellipsis_offset_mm,
                    dot_diameter=ellipsis_dot_diameter_mm,
                    dot_gap=ellipsis_dot_gap_mm,
                    layer="WAVE",
                )
            else:
                draw_break_marker_doubleS_vertical_arcs(
                    msp, xC, y_line,
                    height=marker_height_mm,
                    width=marker_width_mm,
                    gap=marker_gap_mm,
                    layer="WAVE",
                )

    y = top_margin + row_gap * (len(seq.channels))

    # CLOCK
    if seq.clk_mhz is not None:
        add_text(
            msp,
            left_margin + channel_label_offset[0],
            y + channel_label_offset[1],
            "CLK",
            h=chan_h,
            style="TNR",
        )

        draw_baseline_with_break_holes(msp, x_left, x_right, y, holes=holes_marker_all, layer="BASE")
        draw_markers_at_y(y)

        clk_pts = build_clock_step_polyline(
            warp,
            left_margin=left_margin,
            y0=y,
            amp=amp_scale * 0.8,
            mhz=seq.clk_mhz,
            t_end_ns=seq.t_end,
            rising_edge_at_t0=True,
        )
        draw_polyline_with_breaks(msp, clk_pts, holes=holes_wave_clock, layer="CLK", linetype=None)

        y -= row_gap

    # CHANNELS
    for ch in seq.channels:
        add_text(
            msp,
            left_margin + channel_label_offset[0],
            y + channel_label_offset[1],
            ch.name,
            h=chan_h,
            style="TNR",
        )

        y_base = y + ch.baseline * amp_scale

        if ch.show_baseline:
            draw_baseline_with_break_holes(msp, x_left, x_right, y_base, holes=holes_marker_all, layer="BASE")
            draw_markers_at_y(y_base)

        # --- build full tracks by kind ---
        rect_pulses     = [p for p in ch.pulses if p.kind == "rect"]
        gaussian_pulses = [p for p in ch.pulses if p.kind == "gaussian"]
        dc_pulses       = [p for p in ch.pulses if p.kind == "dc"]
        read_pulses     = [p for p in ch.pulses if p.kind == "readout"]

        # (A) dc (Z): one continuous step outline
        if dc_pulses:
            env_factory = rect_env_factory()           # 鏂规尝 DC
            pts_env_x = build_env_x_polylines(
                warp=warp,
                left_margin=left_margin,
                t_start=0.0,
                t_end=seq.t_end,
                y_base=y_base,
                height=amp_scale,
                # segs=segs,
                pulses=dc_pulses,
                envelope_factory=env_factory,
                samples_per_pulse=200,   # 鏂规尝鍏跺疄寰堢渷锛?0~60澶熶簡锛涢珮鏂彲浠?200+
            )

            draw_polyline_with_breaks(msp, pts_env_x, holes=holes_wave_all, layer="WAVE", linetype=None)


        # (B) readout: envelope (upper half step, dashed) + carrier (solid)
        read_pulses = [p for p in read_pulses if p.carrier is not None]
        if read_pulses:
            env_factory = rect_env_factory()
            for rp in read_pulses:
                pts_env_x, pts_car_x = build_env_and_carrier_x_polylines(
                    warp=warp,
                    left_margin=left_margin,
                    t_start=rp.t0,
                    t_end=rp.t1,
                    y_base=y_base,
                    height=amp_scale,
                    pulses=[rp],
                    envelope_factory=env_factory,
                    samples_per_cycle=samples_per_cycle,
                    carrier_plot_max_hz=carrier_plot_max_hz,
                )
                draw_polyline_with_breaks(msp, pts_env_x, holes=holes_wave_all, layer="WAVE", linetype="JIS_02_0.7")
                draw_polyline_with_breaks(msp, pts_car_x, holes=holes_wave_all, layer="WAVE", linetype=None)

        # (C) Gaussian (XY): gaussian envelope (dashed) + carrier (solid), both continuous
        gaussian_pulses = [p for p in gaussian_pulses if p.carrier is not None]
        if gaussian_pulses:
            env_factory = gaussian_env_factory(sigma_div=6.0)
            for gp in gaussian_pulses:
                pts_env_x, pts_car_x = build_env_and_carrier_x_polylines(
                    warp=warp,
                    left_margin=left_margin,
                    t_start=gp.t0,
                    t_end=gp.t1,
                    y_base=y_base,
                    height=amp_scale,
                    pulses=[gp],
                    envelope_factory=env_factory,
                    samples_per_cycle=samples_per_cycle,
                    carrier_plot_max_hz=carrier_plot_max_hz,
                )
                draw_polyline_with_breaks(msp, pts_env_x, holes=holes_wave_all, layer="WAVE", linetype="JIS_02_0.7")
                draw_polyline_with_breaks(msp, pts_car_x, holes=holes_wave_all, layer="WAVE", linetype=None)

        y -= row_gap

    # t=0 dashed vertical marker: ONE single dashed line entity
    x_zero = warp.map_t_to_x(0.0, left_margin)
    y_top = top_margin + row_gap * (len(seq.channels) + (1 if seq.clk_mhz else 0)) + t0_line_top_extra_mm
    y_bot = top_margin - row_gap
    msp.add_line((x_zero, y_bot), (x_zero, y_top), dxfattribs={"layer": "BASE", "linetype": "DASHED"})

    # Bottom time axis
    axis_y = y + 4.0
    draw_baseline_with_break_holes(msp, x_left, x_right, axis_y, holes=holes_marker_all, layer="BASE")
    draw_markers_at_y(axis_y)
    add_text(
        msp,
        0.5 * (x_left + x_right),
        axis_y - 3.45 * tick_label_h,
        "TIME (ns)",
        h=axis_label_h,
        style="TNR",
    )

    draw_time_axis_ticks(
        msp,
        warp,
        t_end_ns=seq.t_end,
        left_margin=left_margin,
        y=axis_y,
        breaks=warp.breaks,
        holes=holes_wave_all,
        text_style="TNR",
        font_h=tick_label_h,
        target_ticks=target_ticks,
        minor_per_major=minor_per_major,
        major_ticks=major_ticks,
    )

    doc.saveas(out_path)
    return out_path

