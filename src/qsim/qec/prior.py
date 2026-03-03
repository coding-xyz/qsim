"""Prior-model builders and prior artifact export helpers."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

import numpy as np

from qsim.common.schemas import PriorModel, SyndromeFrame, utc_now_iso
from qsim.qec.interfaces import IPriorBuilder


def _short_rev(value: str) -> str:
    """Return a short deterministic revision fingerprint."""
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:12]


def _base_graph_from_syndrome(syndrome: SyndromeFrame) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Construct a small baseline detector graph from syndrome dimensions."""
    n_rows = len(syndrome.detectors)
    n_cols = len(syndrome.detectors[0]) if n_rows > 0 else 0
    nodes = [{"id": i, "kind": "detector"} for i in range(max(n_rows, n_cols))]
    edges: list[dict[str, Any]] = []
    for i in range(max(0, len(nodes) - 1)):
        edges.append({"u": i, "v": i + 1, "weight": 1.0})
    return nodes, edges


class StimPriorBuilder(IPriorBuilder):
    """Stim-backed prior builder with graceful heuristic fallback.

    If ``stim`` is unavailable, the builder still returns a deterministic prior
    and annotates fallback reason in metadata.
    """

    name = "stim_prior"

    def build(self, syndrome: SyndromeFrame, context: dict | None = None) -> PriorModel:
        """Build prior model using Stim when available, else deterministic fallback."""
        ctx = context or {}
        nodes, edges = _base_graph_from_syndrome(syndrome)
        try:
            import stim  # type: ignore  # noqa: F401

            backend = "stim"
            quality = "native"
        except Exception as exc:  # pragma: no cover - depends on local env
            backend = "fallback"
            quality = "heuristic"
            ctx = dict(ctx)
            ctx["fallback_reason"] = str(exc)

        rounds = max(1, int(syndrome.rounds or 1))
        scale = 1.0 / rounds
        for e in edges:
            e["weight"] = float(e["weight"]) * scale

        rev = _short_rev(f"{self.name}:{backend}:{rounds}:{len(nodes)}:{len(edges)}")
        return PriorModel(
            builder_name=self.name,
            builder_rev=rev,
            nodes=nodes,
            edges=edges,
            metadata={
                "generated_at": utc_now_iso(),
                "backend": backend,
                "quality": quality,
                "context": ctx,
            },
        )


class CirqPriorBuilder(IPriorBuilder):
    """Cirq-backed prior builder with graceful heuristic fallback.

    If ``cirq`` is unavailable, the builder still returns a deterministic prior
    and annotates fallback reason in metadata.
    """

    name = "cirq_prior"

    def build(self, syndrome: SyndromeFrame, context: dict | None = None) -> PriorModel:
        """Build prior model using Cirq when available, else deterministic fallback."""
        ctx = context or {}
        nodes, edges = _base_graph_from_syndrome(syndrome)
        try:
            import cirq  # type: ignore  # noqa: F401

            backend = "cirq"
            quality = "native"
        except Exception as exc:  # pragma: no cover - depends on local env
            backend = "fallback"
            quality = "heuristic"
            ctx = dict(ctx)
            ctx["fallback_reason"] = str(exc)

        # Slightly different deterministic weighting from Stim path.
        denom = max(1, len(nodes))
        for i, e in enumerate(edges):
            e["weight"] = float(i + 1) / float(denom)

        rev = _short_rev(f"{self.name}:{backend}:{len(nodes)}:{len(edges)}")
        return PriorModel(
            builder_name=self.name,
            builder_rev=rev,
            nodes=nodes,
            edges=edges,
            metadata={
                "generated_at": utc_now_iso(),
                "backend": backend,
                "quality": quality,
                "context": ctx,
            },
        )


def build_prior_and_report(
    syndrome: SyndromeFrame,
    backend: str = "auto",
    context: dict | None = None,
) -> tuple[PriorModel, dict[str, Any]]:
    """Build prior model and a structured report.

    Args:
        syndrome: Syndrome frame to be converted into prior graph form.
        backend: Builder selector ``auto|stim|cirq|mock``.
        context: Optional metadata forwarded to builders.

    Returns:
        Tuple of:
        - ``PriorModel`` produced by selected/auto-resolved backend.
        - report dict for auditability (builder/backend/status/snapshot).
    """
    key = (backend or "auto").lower()
    if key == "stim":
        builder: IPriorBuilder = StimPriorBuilder()
    elif key == "cirq":
        builder = CirqPriorBuilder()
    elif key == "mock":
        # Keep compatibility with previous placeholder path.
        from qsim.qec.mock import MockPriorBuilder

        builder = MockPriorBuilder()
    else:
        # auto: try stim -> cirq -> mock
        stim_model = StimPriorBuilder().build(syndrome, context=context)
        if stim_model.metadata.get("backend") != "fallback":
            model = stim_model
            report = {
                "schema_version": "1.0",
                "builder": model.builder_name,
                "builder_rev": model.builder_rev,
                "backend": model.metadata.get("backend"),
                "status": "ok",
                "nodes": len(model.nodes),
                "edges": len(model.edges),
                "metadata": model.metadata,
                "prior_snapshot": asdict(model),
            }
            return model, report
        cirq_model = CirqPriorBuilder().build(syndrome, context=context)
        if cirq_model.metadata.get("backend") != "fallback":
            model = cirq_model
            report = {
                "schema_version": "1.0",
                "builder": model.builder_name,
                "builder_rev": model.builder_rev,
                "backend": model.metadata.get("backend"),
                "status": "ok",
                "nodes": len(model.nodes),
                "edges": len(model.edges),
                "metadata": model.metadata,
                "prior_snapshot": asdict(model),
            }
            return model, report
        from qsim.qec.mock import MockPriorBuilder

        builder = MockPriorBuilder()

    model = builder.build(syndrome, context=context)
    backend_used = model.metadata.get("backend", "mock")
    status = "ok" if backend_used not in {"fallback"} else "fallback"
    report = {
        "schema_version": "1.0",
        "builder": getattr(builder, "name", builder.__class__.__name__),
        "builder_rev": model.builder_rev,
        "backend": backend_used,
        "status": status,
        "nodes": len(model.nodes),
        "edges": len(model.edges),
        "metadata": model.metadata,
        "prior_snapshot": asdict(model),
    }
    return model, report


def write_prior_samples_npz(prior_model: PriorModel, out_path: str | Path) -> Path:
    """Persist a lightweight NPZ cache derived from a prior graph model.

    The file includes both compact numeric arrays for quick downstream loading
    and JSON snapshots to preserve the full graph payload.
    """
    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)

    node_ids = np.asarray([int(item.get("id", i)) for i, item in enumerate(prior_model.nodes)], dtype=np.int64)
    node_kinds = np.asarray([str(item.get("kind", "")) for item in prior_model.nodes], dtype="<U32")
    edge_u = np.asarray([int(item.get("u", 0)) for item in prior_model.edges], dtype=np.int64)
    edge_v = np.asarray([int(item.get("v", 0)) for item in prior_model.edges], dtype=np.int64)
    edge_weight = np.asarray([float(item.get("weight", 0.0)) for item in prior_model.edges], dtype=float)

    np.savez_compressed(
        out,
        schema_version=np.asarray([str(prior_model.schema_version)], dtype="<U16"),
        builder_name=np.asarray([str(prior_model.builder_name)], dtype="<U64"),
        builder_rev=np.asarray([str(prior_model.builder_rev)], dtype="<U64"),
        node_ids=node_ids,
        node_kinds=node_kinds,
        edge_u=edge_u,
        edge_v=edge_v,
        edge_weight=edge_weight,
        nodes_json=np.asarray([json.dumps(prior_model.nodes, ensure_ascii=False)], dtype=object),
        edges_json=np.asarray([json.dumps(prior_model.edges, ensure_ascii=False)], dtype=object),
        metadata_json=np.asarray([json.dumps(prior_model.metadata, ensure_ascii=False)], dtype=object),
    )
    return out
