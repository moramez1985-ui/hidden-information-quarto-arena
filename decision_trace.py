from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime, timezone
import json
import math
from pathlib import Path
from typing import Any, Protocol


DECISION_TRACE_SCHEMA_VERSION = 1


def _utc_timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()


def _copy_json_value(value: Any) -> Any:
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("Trace values must not contain non-finite numbers.")
        return value
    if isinstance(value, Mapping):
        if any(not isinstance(key, str) for key in value):
            raise TypeError("Trace object keys must be strings.")
        return {key: _copy_json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_copy_json_value(item) for item in value]
    raise TypeError(f"Trace value of type {type(value).__name__} is not JSON-compatible.")


def _require_mapping(value: Any, field_name: str) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise TypeError(f"{field_name} must be an object.")
    copied = _copy_json_value(value)
    if not isinstance(copied, dict):
        raise TypeError(f"{field_name} must be an object.")
    return copied


def _parse_string_list(value: Any, field_name: str) -> tuple[str, ...] | None:
    if value is None:
        return None
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise ValueError(f"{field_name} must be an array of strings or null.")
    return tuple(value)


@dataclass(frozen=True, slots=True)
class DecisionTraceRecord:
    match_id: str
    turn_id: int
    agent_id: str
    observation_snapshot: Mapping[str, Any]
    selected_action: Mapping[str, Any]
    timestamp: str = field(default_factory=_utc_timestamp)
    model_provider: str | None = None
    model_name: str | None = None
    model_version: str | None = None
    candidate_hypotheses: tuple[str, ...] | None = None
    evidence_references: tuple[str, ...] | None = None
    decision_explanation: str | None = None
    declared_confidence: float | None = None
    received_feedback: Mapping[str, Any] | None = None
    latency_ms: float | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    schema_version: int = DECISION_TRACE_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if type(self.schema_version) is not int or self.schema_version != DECISION_TRACE_SCHEMA_VERSION:
            raise ValueError("Unsupported decision trace schema version.")
        for field_name in ("match_id", "agent_id", "timestamp"):
            value = getattr(self, field_name)
            if not isinstance(value, str) or not value:
                raise ValueError(f"{field_name} must be a non-empty string.")
        try:
            datetime.fromisoformat(self.timestamp.replace("Z", "+00:00"))
        except ValueError as error:
            raise ValueError("timestamp must be an ISO-8601 datetime.") from error
        if type(self.turn_id) is not int or self.turn_id < 1:
            raise ValueError("turn_id must be a positive integer.")

        snapshot = _require_mapping(self.observation_snapshot, "observation_snapshot")
        if set(snapshot) != {"public", "private"}:
            raise ValueError("observation_snapshot must separate public and private data.")
        if not isinstance(snapshot["public"], dict) or not isinstance(snapshot["private"], dict):
            raise ValueError("Public and private observation snapshots must be objects.")
        object.__setattr__(self, "observation_snapshot", snapshot)
        object.__setattr__(self, "selected_action", _require_mapping(self.selected_action, "selected_action"))
        if self.received_feedback is not None:
            object.__setattr__(
                self,
                "received_feedback",
                _require_mapping(self.received_feedback, "received_feedback"),
            )

        for field_name in ("model_provider", "model_name", "model_version", "decision_explanation"):
            value = getattr(self, field_name)
            if value is not None and not isinstance(value, str):
                raise TypeError(f"{field_name} must be a string or null.")
        for field_name in ("candidate_hypotheses", "evidence_references"):
            value = getattr(self, field_name)
            if value is not None:
                if not isinstance(value, (list, tuple)) or any(not isinstance(item, str) for item in value):
                    raise TypeError(f"{field_name} must be a sequence of strings or null.")
                object.__setattr__(self, field_name, tuple(value))
        if self.declared_confidence is not None:
            if (
                isinstance(self.declared_confidence, bool)
                or not isinstance(self.declared_confidence, (int, float))
                or not math.isfinite(self.declared_confidence)
                or not 0 <= self.declared_confidence <= 1
            ):
                raise ValueError("declared_confidence must be a finite number from 0 to 1.")
        if self.latency_ms is not None and (
            isinstance(self.latency_ms, bool)
            or not isinstance(self.latency_ms, (int, float))
            or not math.isfinite(self.latency_ms)
            or self.latency_ms < 0
        ):
            raise ValueError("latency_ms must be a finite non-negative number.")
        for field_name in ("input_tokens", "output_tokens"):
            value = getattr(self, field_name)
            if value is not None and (type(value) is not int or value < 0):
                raise ValueError(f"{field_name} must be a non-negative integer.")

    def to_dict(self) -> dict[str, Any]:
        record: dict[str, Any] = {
            "schema_version": self.schema_version,
            "match_id": self.match_id,
            "turn_id": self.turn_id,
            "agent_id": self.agent_id,
            "observation_snapshot": _copy_json_value(self.observation_snapshot),
            "selected_action": _copy_json_value(self.selected_action),
            "timestamp": self.timestamp,
        }
        optional_fields = (
            "model_provider",
            "model_name",
            "model_version",
            "candidate_hypotheses",
            "evidence_references",
            "decision_explanation",
            "declared_confidence",
            "received_feedback",
            "latency_ms",
            "input_tokens",
            "output_tokens",
        )
        for field_name in optional_fields:
            value = getattr(self, field_name)
            if value is not None:
                record[field_name] = (
                    list(value)
                    if field_name in ("candidate_hypotheses", "evidence_references")
                    else _copy_json_value(value)
                )
        return record

    def to_json(self) -> str:
        return json.dumps(
            self.to_dict(),
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        )

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> DecisionTraceRecord:
        if not isinstance(data, Mapping):
            raise TypeError("A decision trace must be a JSON object.")
        required_fields = {
            "schema_version",
            "match_id",
            "turn_id",
            "agent_id",
            "observation_snapshot",
            "selected_action",
            "timestamp",
        }
        optional_fields = {
            "model_provider",
            "model_name",
            "model_version",
            "candidate_hypotheses",
            "evidence_references",
            "decision_explanation",
            "declared_confidence",
            "received_feedback",
            "latency_ms",
            "input_tokens",
            "output_tokens",
        }
        if not required_fields.issubset(data) or set(data) - required_fields - optional_fields:
            raise ValueError("Decision trace has missing or unexpected fields.")
        if data["schema_version"] != DECISION_TRACE_SCHEMA_VERSION:
            raise ValueError("Unsupported decision trace schema version.")
        return cls(
            match_id=data["match_id"],
            turn_id=data["turn_id"],
            agent_id=data["agent_id"],
            observation_snapshot=data["observation_snapshot"],
            selected_action=data["selected_action"],
            timestamp=data["timestamp"],
            model_provider=data.get("model_provider"),
            model_name=data.get("model_name"),
            model_version=data.get("model_version"),
            candidate_hypotheses=_parse_string_list(
                data.get("candidate_hypotheses"), "candidate_hypotheses"
            ),
            evidence_references=_parse_string_list(
                data.get("evidence_references"), "evidence_references"
            ),
            decision_explanation=data.get("decision_explanation"),
            declared_confidence=data.get("declared_confidence"),
            received_feedback=data.get("received_feedback"),
            latency_ms=data.get("latency_ms"),
            input_tokens=data.get("input_tokens"),
            output_tokens=data.get("output_tokens"),
            schema_version=data["schema_version"],
        )

    @classmethod
    def from_json(cls, serialized: str) -> DecisionTraceRecord:
        data = json.loads(serialized)
        if not isinstance(data, Mapping):
            raise ValueError("A serialized decision trace must contain a JSON object.")
        return cls.from_dict(data)


class DecisionTraceSink(Protocol):
    def write(self, record: DecisionTraceRecord) -> None: ...


class JsonlDecisionTraceWriter:
    """Append one versioned, machine-readable decision record per line."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    def write(self, record: DecisionTraceRecord) -> None:
        serialized = record.to_json()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8", newline="\n") as output:
            output.write(serialized)
            output.write("\n")
