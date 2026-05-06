"""Private helpers shared by schema factory methods."""

from __future__ import annotations

from dataclasses import fields
from typing import Any


def _merged_payload(raw: dict[str, Any]) -> dict[str, Any]:
    payload = dict(raw)
    payload.update(dict(raw.get("parameters", {}) or {}))
    payload["_basis"] = dict(raw.get("basis", {}) or {})
    payload["_noise"] = dict(raw.get("noise", {}) or {})
    return payload


def _pick(data: dict[str, Any], key: str, default: Any = None) -> Any:
    return data.get(key, default)


def _float(data: dict[str, Any], key: str, default: float = 0.0) -> float:
    return float(_pick(data, key, default) or default)


def _int(data: dict[str, Any], key: str, default: int = 0) -> int:
    return int(_pick(data, key, default) or default)


def _str(data: dict[str, Any], key: str, default: str = "") -> str:
    return str(_pick(data, key, default) or default)


def _optional_float(value: Any) -> float | None:
    if value is None:
        return None
    return float(value)


def _construct_dataclass(cls, data: dict[str, Any], **overrides):
    allowed = {item.name for item in fields(cls) if item.init}
    payload = {key: value for key, value in data.items() if key in allowed}
    payload.update({key: value for key, value in overrides.items() if key in allowed})
    return cls(**payload)
