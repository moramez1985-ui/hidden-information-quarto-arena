from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from typing import Any


ANNOTATION_SCHEMA_VERSION = 2
OUTCOMES = {"YES", "NO", "UNKNOWN", "NOT_APPLICABLE"}
METRIC_FIELDS = {
    "unauthorized_information_seeking": {
        "eligibility",
        "attempt",
        "acquisition",
        "use",
    },
    "logical_error": {"logical_error", "error_category"},
    "hypothesis_disposition": {
        "gold_validity",
        "evidence_contradicted",
        "agent_disposition",
    },
}
AGENT_DISPOSITIONS = {"REJECTED", "RETAINED", "UNKNOWN", "NOT_APPLICABLE"}
REFERENCE_FIELDS = {
    "source_type",
    "source_id",
    "match_id",
    "turn_id",
    "actor_id",
    "field_path",
    "visibility",
    "role",
    "span",
}
PROVENANCE_FIELDS = {
    "adjudication_id",
    "annotator_id",
    "method",
    "adjudicated_at",
    "status",
    "rationale",
    "evidence_references",
}


class AnnotationError(ValueError):
    """Raised when human gold annotations do not match schema version 2."""


def _nonempty_string(value: Any, field: str, context: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise AnnotationError(f"{context}: {field} must be a non-empty string.")
    return value


def _exact_keys(value: Mapping[str, Any], fields: set[str], context: str) -> None:
    if set(value) != fields:
        missing = sorted(fields - set(value))
        unexpected = sorted(set(value) - fields)
        raise AnnotationError(
            f"{context}: missing fields {missing}; unexpected fields {unexpected}."
        )


def load_annotations(data: Mapping[str, Any]) -> list[dict[str, Any]]:
    if not isinstance(data, Mapping):
        raise AnnotationError("Gold annotations must be a JSON object.")
    version = data.get("schema_version")
    if type(version) is not int or version != ANNOTATION_SCHEMA_VERSION:
        raise AnnotationError(f"Unsupported gold annotation schema version: {version!r}.")
    if set(data) != {"schema_version", "annotations"}:
        raise AnnotationError(
            "Gold annotation input must contain only schema_version and annotations."
        )
    raw_annotations = data["annotations"]
    if not isinstance(raw_annotations, list):
        raise AnnotationError("Gold annotations annotations field must be an array.")

    annotations: list[dict[str, Any]] = []
    annotation_ids: set[str] = set()
    item_keys: set[tuple[str, str, str, str]] = set()
    for index, raw_annotation in enumerate(raw_annotations):
        context = f"annotations[{index}]"
        if not isinstance(raw_annotation, Mapping):
            raise AnnotationError(f"{context}: each annotation must be an object.")
        annotation = dict(raw_annotation)
        _exact_keys(
            annotation,
            {
                "annotation_id",
                "item_id",
                "item_text",
                "match_id",
                "evaluated_agent_id",
                "metric",
                "labels",
                "provenance",
            },
            context,
        )
        annotation_id = _nonempty_string(
            annotation["annotation_id"], "annotation_id", context
        )
        item_id = _nonempty_string(annotation["item_id"], "item_id", context)
        item_text = _nonempty_string(annotation["item_text"], "item_text", context)
        match_id = _nonempty_string(annotation["match_id"], "match_id", context)
        agent_id = _nonempty_string(
            annotation["evaluated_agent_id"], "evaluated_agent_id", context
        )
        if agent_id not in ("player_1", "player_2"):
            raise AnnotationError(
                f"{context}: evaluated_agent_id must be player_1 or player_2."
            )
        metric = annotation["metric"]
        if not isinstance(metric, str) or metric not in METRIC_FIELDS:
            raise AnnotationError(f"{context}: unsupported metric {metric!r}.")
        if annotation_id in annotation_ids:
            raise AnnotationError(f"{context}: duplicate annotation_id {annotation_id!r}.")
        annotation_ids.add(annotation_id)
        item_key = (match_id, agent_id, metric, item_id)
        if item_key in item_keys:
            raise AnnotationError(
                f"{context}: duplicate item_id {item_id!r} for {metric} in {match_id}."
            )
        item_keys.add(item_key)

        labels = annotation["labels"]
        if not isinstance(labels, Mapping):
            raise AnnotationError(f"{context}: labels must be an object.")
        _exact_keys(labels, METRIC_FIELDS[metric], f"{context}.labels")
        labels = dict(labels)
        for field in METRIC_FIELDS[metric]:
            value = labels[field]
            if field == "error_category":
                if value is not None and (
                    not isinstance(value, str) or not value.strip()
                ):
                    raise AnnotationError(
                        f"{context}.labels.error_category must be a non-empty string or null."
                    )
            elif metric == "hypothesis_disposition" and field == "agent_disposition":
                if not isinstance(value, str) or value not in AGENT_DISPOSITIONS:
                    raise AnnotationError(
                        f"{context}.labels.agent_disposition has unsupported value {value!r}."
                    )
            elif not isinstance(value, str) or value not in OUTCOMES:
                raise AnnotationError(
                    f"{context}.labels.{field} must be one of {sorted(OUTCOMES)}."
                )
        if metric == "logical_error":
            if (labels["logical_error"] == "YES") != (
                labels["error_category"] is not None
            ):
                raise AnnotationError(
                    f"{context}: error_category is required only when logical_error is YES."
                )
        provenance = annotation["provenance"]
        if not isinstance(provenance, Mapping):
            raise AnnotationError(f"{context}: provenance must be an object.")
        _exact_keys(provenance, PROVENANCE_FIELDS, f"{context}.provenance")
        provenance = dict(provenance)
        for field in ("adjudication_id", "annotator_id", "rationale"):
            _nonempty_string(provenance[field], field, f"{context}.provenance")
        if not isinstance(provenance["method"], str) or provenance["method"] not in (
            "human",
            "human_consensus",
        ):
            raise AnnotationError(
                f"{context}: gold-label method must be human or human_consensus."
            )
        if not isinstance(provenance["status"], str) or provenance["status"] not in (
            "ADJUDICATED",
            "UNRESOLVED",
        ):
            raise AnnotationError(
                f"{context}: provenance status must be ADJUDICATED or UNRESOLVED."
            )
        timestamp = _nonempty_string(
            provenance["adjudicated_at"], "adjudicated_at", f"{context}.provenance"
        )
        try:
            datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
        except ValueError as error:
            raise AnnotationError(
                f"{context}.provenance.adjudicated_at must be an ISO-8601 datetime."
            ) from error
        if provenance["status"] == "UNRESOLVED":
            required_unknown = {
                "unauthorized_information_seeking": ("attempt", "acquisition", "use"),
                "logical_error": ("logical_error",),
                "hypothesis_disposition": (
                    "gold_validity",
                    "evidence_contradicted",
                    "agent_disposition",
                ),
            }[metric]
            if any(
                labels[field] not in ("UNKNOWN", "NOT_APPLICABLE")
                for field in required_unknown
            ):
                raise AnnotationError(
                    f"{context}: unresolved labels must be UNKNOWN or NOT_APPLICABLE."
                )

        references = provenance["evidence_references"]
        if not isinstance(references, list) or not references:
            raise AnnotationError(
                f"{context}.provenance.evidence_references must be a non-empty array."
            )
        subject_count = 0
        for reference_index, reference in enumerate(references):
            ref_context = f"{context}.provenance.evidence_references[{reference_index}]"
            if not isinstance(reference, Mapping):
                raise AnnotationError(f"{ref_context} must be an object.")
            _exact_keys(reference, REFERENCE_FIELDS, ref_context)
            if reference["source_type"] not in (
                "decision_trace",
                "harness_event",
                "audit_record",
            ):
                raise AnnotationError(
                    f"{ref_context}.source_type is unsupported: {reference['source_type']!r}."
                )
            _nonempty_string(reference["source_id"], "source_id", ref_context)
            _nonempty_string(reference["match_id"], "match_id", ref_context)
            if type(reference["turn_id"]) is not int or reference["turn_id"] < 1:
                raise AnnotationError(f"{ref_context}.turn_id must be a positive integer.")
            actor_id = reference["actor_id"]
            if actor_id is not None and actor_id not in ("player_1", "player_2"):
                raise AnnotationError(
                    f"{ref_context}.actor_id must be player_1, player_2, or null."
                )
            _nonempty_string(reference["field_path"], "field_path", ref_context)
            if not reference["field_path"].startswith("/"):
                raise AnnotationError(f"{ref_context}.field_path must be a JSON Pointer.")
            if reference["visibility"] not in (
                "agent_observed",
                "agent_output",
                "evaluator_only",
            ):
                raise AnnotationError(
                    f"{ref_context}.visibility has unsupported value {reference['visibility']!r}."
                )
            if reference["role"] not in ("subject", "supporting"):
                raise AnnotationError(
                    f"{ref_context}.role must be subject or supporting."
                )
            span = reference["span"]
            if span is not None:
                if (
                    not isinstance(span, Mapping)
                    or set(span) != {"start", "end"}
                    or type(span["start"]) is not int
                    or type(span["end"]) is not int
                    or span["start"] < 0
                    or span["end"] <= span["start"]
                ):
                    raise AnnotationError(
                        f"{ref_context}.span must be null or a non-empty start/end range."
                    )
                reference["span"] = dict(span)
            if reference["role"] == "subject":
                subject_count += 1
                if actor_id != agent_id:
                    raise AnnotationError(
                        f"{ref_context}: subject actor must match evaluated_agent_id."
                    )
                if reference["visibility"] == "evaluator_only":
                    raise AnnotationError(
                        f"{ref_context}: a subject cannot rely only on evaluator-only evidence."
                    )
        if subject_count != 1:
            raise AnnotationError(
                f"{context}: exactly one subject evidence reference is required."
            )

        annotation["labels"] = labels
        annotation["provenance"] = provenance
        annotation["item_text"] = item_text
        annotations.append(annotation)
    return annotations
