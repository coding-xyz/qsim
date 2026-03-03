"""Engineering drawing adapters for pulse timing artifacts."""

from __future__ import annotations

from pathlib import Path

from qsim.common.schemas import Carrier, PulseIR


class EngineeringDrawer:
    """Adapter that exports ``PulseIR`` timing diagram to DXF."""

    @staticmethod
    def export_dxf(pulse_ir: PulseIR, path: str | Path, style: dict | None = None) -> Path:
        """Export pulse sequence as DXF using ``pulse_drawer`` backend."""
        try:
            from pulse_drawer import (
                Break as DrawerBreak,
                Carrier as DrawerCarrier,
                Channel as DrawerChannel,
                Pulse as DrawerPulse,
                Sequence as DrawerSequence,
                render_sequence_to_dxf,
            )
        except Exception as exc:
            raise RuntimeError("pulse_drawer.py 或其依赖不可用，无法导出 DXF") from exc

        style = style or {}
        channels = []
        for ch in pulse_ir.channels:
            pulses = []
            for p in ch.pulses:
                carrier = None
                if p.carrier:
                    carrier = DrawerCarrier(frequency=p.carrier.freq, phase=p.carrier.phase)
                kind = p.shape.lower()
                if kind == "drag":
                    kind = "gaussian"
                pulses.append(DrawerPulse(t0=p.t0, t1=p.t1, amp=p.amp, kind=kind, carrier=carrier))
            channels.append(DrawerChannel(name=ch.name, pulses=pulses))

        raw_breaks = style.get("breaks", [])
        drawer_breaks = []
        for b in raw_breaks:
            if isinstance(b, dict):
                t0 = float(b.get("t0", 0.0))
                t1 = float(b.get("t1", 0.0))
                marker = str(b.get("marker", "ellipsis"))
                drawer_breaks.append(DrawerBreak(t0=t0, t1=t1, marker=marker))
            elif isinstance(b, (list, tuple)) and len(b) >= 2:
                drawer_breaks.append((float(b[0]), float(b[1])))

        seq = DrawerSequence(
            title=style.get("title", "qsim timing"),
            t_end=pulse_ir.t_end,
            channels=channels,
            clk_mhz=style.get("clk_mhz"),
            breaks=drawer_breaks,
        )

        out = Path(path)
        out.parent.mkdir(parents=True, exist_ok=True)
        render_sequence_to_dxf(
            seq,
            str(out),
            **{k: v for k, v in style.items() if k not in {"title", "clk_mhz", "breaks"}},
        )
        return out
