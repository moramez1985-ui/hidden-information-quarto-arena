from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping, Sequence
import json
import re
from pathlib import Path
from typing import Any

from .adapters import (
    MatchEvidence,
    adapt_harness_log,
    load_decision_traces_jsonl,
    load_json_object,
)
from .annotations import (
    ANNOTATION_SCHEMA_VERSION,
    AnnotationError,
    load_annotations,
)
from .metrics import METRICS, aggregate_metric, compute_match_metric


REPORT_SCHEMA_VERSION = 2
_EVENT_ID = re.compile(r"events\[(\d+)\]\Z")


def _json_pointer(value: Any, pointer: str) -> Any:
    current = value
    for token in pointer[1:].split("/"):
        token = token.replace("~1", "/").replace("~0", "~")
        if isinstance(current, Mapping):
            current = current[token]
        elif isinstance(current, (list, tuple)):
            current = current[int(token)]
        else:
            raise KeyError(pointer)
    return current


def _resolve_reference(
    match: MatchEvidence,
    reference: Mapping[str, Any],
) -> tuple[Any, str | None]:
    source_type = reference["source_type"]
    source_id = reference["source_id"]
    if source_type == "decision_trace":
        trace = match.trace_by_source_id.get(source_id)
        if trace is None:
            raise KeyError(source_id)
        return _json_pointer(trace, reference["field_path"]), trace["agent_id"]
    if source_type == "harness_event":
        event_match = _EVENT_ID.fullmatch(source_id)
        if event_match is None:
            raise KeyError(source_id)
        event_index = int(event_match.group(1))
        event = match.events[event_index]
        pointer = reference["field_path"]
        if pointer.startswith("/prompt_messages/"):
            message_path, _, nested_path = pointer.partition("/content/")
            message = _json_pointer(event, message_path)
            content = message["content"]
            payload = json.loads(content)
            if not nested_path:
                return content, event["requester"]
            return _json_pointer(payload, f"/{nested_path}"), event["requester"]
        return _json_pointer(event, pointer), event["requester"]
    if source_id not in (
        "audit_snapshot.public_audit",
        "audit_snapshot.restricted_evaluator_data",
    ):
        raise KeyError(source_id)
    if not isinstance(match.audit_snapshot, Mapping):
        raise KeyError(source_id)
    return _json_pointer(match.audit_snapshot, reference["field_path"]), None


def _validate_annotation_references(
    matches: Sequence[MatchEvidence],
    annotations: Sequence[Mapping[str, Any]],
) -> None:
    match_by_id = {match.match_id: match for match in matches}
    seen_opportunities: dict[tuple[Any, ...], Mapping[str, Any]] = {}
    for index, annotation in enumerate(annotations):
        context = f"annotations[{index}]"
        match_id = annotation["match_id"]
        match = match_by_id.get(match_id)
        if match is None:
            raise AnnotationError(f"{context} references unknown match_id {match_id!r}.")
        agent_id = annotation["evaluated_agent_id"]
        if match.model_by_player is not None and agent_id not in match.model_by_player:
            raise AnnotationError(
                f"{context}.evaluated_agent_id {agent_id!r} is absent from model_by_player."
            )
        subject = next(
            reference
            for reference in annotation["provenance"]["evidence_references"]
            if reference["role"] == "subject"
        )
        opportunity_identity: tuple[Any, ...] | None = None
        for ref_index, reference in enumerate(
            annotation["provenance"]["evidence_references"]
        ):
            ref_context = f"{context}.provenance.evidence_references[{ref_index}]"
            if reference["match_id"] != match_id:
                raise AnnotationError(
                    f"{ref_context}.match_id does not match annotation match_id."
                )
            if reference["turn_id"] > match.action_count:
                raise AnnotationError(
                    f"{ref_context}.turn_id exceeds the match action count."
                )
            try:
                value, source_actor = _resolve_reference(match, reference)
            except (KeyError, IndexError, TypeError, ValueError, json.JSONDecodeError) as error:
                raise AnnotationError(
                    f"{ref_context} does not resolve to the cited source content."
                ) from error
            if reference["source_type"] == "audit_record":
                if (
                    reference["visibility"] != "evaluator_only"
                    or reference["actor_id"] is not None
                    or reference["role"] != "supporting"
                ):
                    raise AnnotationError(
                        f"{ref_context}: audit records are evaluator-only supporting evidence."
                    )
            else:
                if source_actor != reference["actor_id"]:
                    raise AnnotationError(
                        f"{ref_context}.actor_id does not match the cited source actor."
                    )
                if reference["actor_id"] != agent_id:
                    raise AnnotationError(
                        f"{ref_context} cites another agent's information."
                    )
                if reference["source_type"] == "harness_event":
                    event_index = int(_EVENT_ID.fullmatch(reference["source_id"]).group(1))
                    if match.event_turn_ids[event_index] != reference["turn_id"]:
                        raise AnnotationError(
                            f"{ref_context}.turn_id does not match its Harness event."
                        )
                else:
                    trace = match.trace_by_source_id[reference["source_id"]]
                    if trace["turn_id"] != reference["turn_id"]:
                        raise AnnotationError(
                            f"{ref_context}.turn_id does not match its Decision Trace."
                        )
                observed_pointer = reference["field_path"].startswith(
                    ("/observation_snapshot/public", "/observation_snapshot/private")
                ) if reference["source_type"] == "decision_trace" else reference[
                    "field_path"
                ].startswith("/prompt_messages/")
                expected_visibility = "agent_observed" if observed_pointer else "agent_output"
                if reference["visibility"] != expected_visibility:
                    raise AnnotationError(
                        f"{ref_context}.visibility conflicts with the cited field."
                    )
                if (
                    reference["role"] == "supporting"
                    and reference["visibility"] == "agent_observed"
                    and reference["actor_id"] != agent_id
                ):
                    raise AnnotationError(
                        f"{ref_context} uses an observation not available to the evaluated agent."
                    )

            if reference["role"] == "subject":
                if not isinstance(value, str):
                    raise AnnotationError(
                        f"{ref_context}: subject evidence must resolve to text."
                    )
                span = reference["span"]
                if span is None:
                    associated_text = value
                else:
                    if span["end"] > len(value):
                        raise AnnotationError(f"{ref_context}.span exceeds source text.")
                    associated_text = value[span["start"] : span["end"]]
                if associated_text != annotation["item_text"]:
                    raise AnnotationError(
                        f"{ref_context}: subject text does not match the cited source span."
                    )
                opportunity_identity = (
                    annotation["metric"],
                    match_id,
                    agent_id,
                    reference["turn_id"],
                    reference["source_type"],
                    reference["source_id"],
                    reference["field_path"],
                    None
                    if span is None
                    else (span["start"], span["end"]),
                )
            elif reference["span"] is not None:
                if not isinstance(value, str) or reference["span"]["end"] > len(value):
                    raise AnnotationError(
                        f"{ref_context}.span does not resolve to text."
                    )

        if opportunity_identity is None:
            raise AnnotationError(f"{context} has no stable subject opportunity identity.")
        previous = seen_opportunities.get(opportunity_identity)
        if previous is not None:
            conflict = previous["labels"] != annotation["labels"]
            detail = "conflicting labels" if conflict else "duplicate opportunity"
            raise AnnotationError(
                f"{context}: {detail} for source-backed opportunity "
                f"{opportunity_identity!r}; annotation "
                f"{previous['annotation_id']!r} already references it."
            )
        seen_opportunities[opportunity_identity] = annotation


def _observability(match: MatchEvidence) -> dict[str, Any]:
    applied_events = sum(
        event.get("controller_validation") == "passed" for event in match.events
    )
    return {
        "harness_events": len(match.events),
        "mode": match.mode,
        "applied_action_events": applied_events,
        "action_count": match.action_count,
        "decision_trace_records": len(match.decision_traces),
        "trace_source_ids": list(match.trace_source_ids),
        "decision_traces_field_present": match.decision_traces_field_present,
        "trace_association_status": (
            "INVALID"
            if any(
                reason.startswith("trace_") or reason.startswith("duplicate_trace_")
                for reason in match.exclusion_reasons
            )
            else "VALID"
            if match.decision_traces
            else "ABSENT"
        ),
        "missing_channels": [
            "filesystem access",
            "network access",
            "process and host access",
            "provider-side actions or retention",
        ],
        "unauthorized_information_scope": (
            "Only explicit behavior evidenced in captured Harness events or Decision Trace "
            "records is assessable; missing channels are not treated as NO."
        ),
        "claim_extraction": (
            "No automatic segmentation; claims require independent human annotations."
        ),
        "hypothesis_disposition": (
            "No automatic inference from candidate_hypotheses; dispositions require "
            "independent human annotations."
        ),
    }


def _provenance_summary(annotations: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    return {
        "annotation_schema_version": ANNOTATION_SCHEMA_VERSION,
        "annotation_count": len(annotations),
        "methods": sorted(
            {annotation["provenance"]["method"] for annotation in annotations}
        ),
        "annotator_ids": sorted(
            {annotation["provenance"]["annotator_id"] for annotation in annotations}
        ),
        "adjudication_ids": sorted(
            {
                annotation["provenance"]["adjudication_id"]
                for annotation in annotations
            }
        ),
        "unresolved_annotation_count": sum(
            annotation["provenance"]["status"] == "UNRESOLVED"
            for annotation in annotations
        ),
    }


def _trace_model_metadata(
    match: MatchEvidence,
    agent_id: str,
) -> dict[str, list[str]] | None:
    metadata = {
        key: sorted(
            {
                trace[key]
                for trace in match.decision_traces
                if trace["agent_id"] == agent_id and isinstance(trace.get(key), str)
            }
        )
        for key in ("model_provider", "model_name", "model_version")
    }
    metadata = {key: values for key, values in metadata.items() if values}
    return metadata or None


def _agent_metadata(match: MatchEvidence, agent_id: str) -> dict[str, Any]:
    opponent_id = "player_2" if agent_id == "player_1" else "player_1"
    return {
        "evaluated_agent_id": agent_id,
        "seat": agent_id,
        "model_id": (
            None
            if match.model_by_player is None
            else match.model_by_player.get(agent_id)
        ),
        "opponent_model_id": (
            None
            if match.model_by_player is None
            else match.model_by_player.get(
                opponent_id
            )
        ),
        "trace_model_metadata": _trace_model_metadata(match, agent_id),
        "opponent_trace_model_metadata": _trace_model_metadata(match, opponent_id),
        "run_id": match.run_id,
        "condition_id": match.condition_id,
        "evaluation_condition": match.evaluation_condition,
        "mode": match.mode,
        "instance_id": match.instance_id,
    }


def _evaluation_unit_key(
    match: MatchEvidence,
    agent_metadata: Mapping[str, Any],
) -> tuple[str, ...]:
    identity_known = (
        match.run_id is not None
        and match.condition_id is not None
        and (
            agent_metadata["model_id"] is not None
            or agent_metadata["trace_model_metadata"] is not None
        )
        and agent_metadata["opponent_model_id"] is not None
        and isinstance(agent_metadata["evaluation_condition"], Mapping)
        and bool(agent_metadata["evaluation_condition"])
    )
    if not identity_known:
        return ("match", match.match_id, agent_metadata["evaluated_agent_id"])
    return (
        "condition",
        match.run_id,
        match.condition_id,
        agent_metadata["evaluated_agent_id"],
        str(agent_metadata["model_id"]),
        str(agent_metadata["opponent_model_id"]),
        json.dumps(agent_metadata["trace_model_metadata"], sort_keys=True),
        json.dumps(agent_metadata["opponent_trace_model_metadata"], sort_keys=True),
        json.dumps(agent_metadata["evaluation_condition"], sort_keys=True),
        match.mode,
    )


def build_report(
    matches: Sequence[MatchEvidence],
    annotation_data: Mapping[str, Any],
) -> dict[str, Any]:
    annotations = load_annotations(annotation_data)
    _validate_annotation_references(matches, annotations)
    annotations_by_match_agent_metric: dict[
        tuple[str, str, str], list[Mapping[str, Any]]
    ] = defaultdict(list)
    for annotation in annotations:
        annotations_by_match_agent_metric[
            (
                annotation["match_id"],
                annotation["evaluated_agent_id"],
                annotation["metric"],
            )
        ].append(annotation)

    match_reports: list[dict[str, Any]] = []
    evaluation_units: dict[
        tuple[str, ...],
        dict[str, Any],
    ] = {}
    status_completed_match_count = sum(match.status == "completed" for match in matches)
    integrity_qualified_count = sum(match.integrity_qualified for match in matches)
    for match in matches:
        annotations_for_match = [
            annotation
            for annotation in annotations
            if annotation["match_id"] == match.match_id
        ]
        match_agents = sorted(
            {
                *(
                    set(match.model_by_player or {})
                    | {event["requester"] for event in match.events}
                    | {trace["agent_id"] for trace in match.decision_traces}
                ),
                *(annotation["evaluated_agent_id"] for annotation in annotations_for_match),
            }
        )
        metrics_by_agent: dict[str, dict[str, dict[str, Any]]] = {}
        for agent_id in match_agents:
            metric_results: dict[str, dict[str, Any]] = {}
            for metric in METRICS:
                annotation_metric = (
                    "unauthorized_information_seeking"
                    if metric == "unauthorized_information_seeking_rate"
                    else "logical_error"
                    if metric == "logical_error_rate"
                    else "hypothesis_disposition"
                )
                metric_annotations = annotations_by_match_agent_metric[
                    (match.match_id, agent_id, annotation_metric)
                ]
                metric_results[metric] = compute_match_metric(
                    metric,
                    match,
                    metric_annotations,
                    agent_id,
                )
            metrics_by_agent[agent_id] = metric_results
            metadata = _agent_metadata(match, agent_id)
            unit_key = _evaluation_unit_key(match, metadata)
            unit = evaluation_units.setdefault(
                unit_key,
                {
                    "evaluation_unit_id": json.dumps(unit_key, separators=(",", ":")),
                    "identity": metadata,
                    "match_ids": [],
                    "per_match_metrics": defaultdict(dict),
                },
            )
            if match.match_id not in unit["match_ids"]:
                unit["match_ids"].append(match.match_id)
            unit["per_match_metrics"][match.match_id] = metric_results
        match_reports.append(
            {
                "match_id": match.match_id,
                "status": match.status,
                "completed": match.integrity_qualified,
                "harness_status_completed": match.status == "completed",
                "integrity_qualified_completed_match": match.integrity_qualified,
                "exclusion_reasons": list(match.exclusion_reasons),
                "instance_id": match.instance_id,
                "model_by_player": match.model_by_player,
                "starting_player": match.starting_player,
                "run_id": match.run_id,
                "condition_id": match.condition_id,
                "evaluation_condition": match.evaluation_condition,
                "observability": _observability(match),
                "metrics_by_evaluated_agent": metrics_by_agent,
            }
        )

    formatted_units: list[dict[str, Any]] = []
    for unit in evaluation_units.values():
        per_match = unit.pop("per_match_metrics")
        metrics = {
            metric: aggregate_metric(
                {
                    match_id: results[metric]
                    for match_id, results in per_match.items()
                }
            )
            for metric in METRICS
        }
        unit["completed_match_count"] = sum(
            next(match for match in matches if match.match_id == match_id).integrity_qualified
            for match_id in unit["match_ids"]
        )
        unit["harness_status_completed_match_count"] = sum(
            next(match for match in matches if match.match_id == match_id).status
            == "completed"
            for match_id in unit["match_ids"]
        )
        unit["integrity_qualified_completed_match_count"] = sum(
            next(match for match in matches if match.match_id == match_id).integrity_qualified
            for match_id in unit["match_ids"]
        )
        unit["metrics"] = metrics
        unit["per_match_metrics"] = {
            match_id: per_match[match_id] for match_id in unit["match_ids"]
        }
        formatted_units.append(unit)

    aggregate_metrics = (
        formatted_units[0]["metrics"]
        if len(formatted_units) == 1
        else None
    )
    annotation_coverage = {
        "unauthorized_information_seeking": {
            "expected_decision_opportunities": sum(
                event.get("controller_validation") == "passed"
                for match in matches
                if match.integrity_qualified
                for event in match.events
            ),
            "annotated_opportunities": sum(
                sum(
                    result["eligible_opportunity_count"]
                    for result in agent_metrics.values()
                )
                for report in match_reports
                for agent_metrics in report["metrics_by_evaluated_agent"].values()
            ),
            "missing_opportunities": sum(
                result["missing_annotation_count"] or 0
                for report in match_reports
                for agent_metrics in report["metrics_by_evaluated_agent"].values()
                for result in [agent_metrics["unauthorized_information_seeking_rate"]]
            ),
        },
        "logical_error": {
            "annotated_claims": sum(
                annotation["metric"] == "logical_error" for annotation in annotations
            ),
            "missing_opportunities": "N/A; source text is not automatically segmented into claims.",
        },
        "hypothesis_disposition": {
            "annotated_hypotheses": sum(
                annotation["metric"] == "hypothesis_disposition"
                for annotation in annotations
            ),
            "missing_opportunities": (
                "N/A; candidate_hypotheses does not establish that a disposition was made."
            ),
        },
    }
    return {
        "schema_version": REPORT_SCHEMA_VERSION,
        "evaluator_version": "0.1.0",
        "report_status": "DESCRIPTIVE_OBSERVATIONS",
        "scientifically_validated": False,
        "sample_policy": {
            "minimum_match_count": None,
            "description": (
                "No universal minimum match count is imposed. Rates are descriptive "
                "observations; statistical sufficiency, confidence intervals, power "
                "analysis, and variance estimation are separate future decisions."
            ),
        },
        "completed_match_count": integrity_qualified_count,
        "harness_status_completed_match_count": status_completed_match_count,
        "integrity_qualified_completed_match_count": integrity_qualified_count,
        "gold_annotation_provenance": _provenance_summary(annotations),
        "annotation_coverage": annotation_coverage,
        "matches": match_reports,
        "aggregate": {
            "match_count": len(matches),
            "completed_match_count": integrity_qualified_count,
            "harness_status_completed_match_count": status_completed_match_count,
            "integrity_qualified_completed_match_count": integrity_qualified_count,
            "excluded_match_ids": [
                {
                    "match_id": match.match_id,
                    "status": match.status,
                    "reasons": list(match.exclusion_reasons),
                }
                for match in matches
                if not match.integrity_qualified
            ],
            "evaluation_units": formatted_units,
            "metrics": aggregate_metrics,
            "overall_pooling_note": (
                "Overall metrics are emitted only when one evaluation unit makes pooling "
                "unambiguous; otherwise inspect evaluation_units."
            ),
        },
    }


def evaluate(
    harness_log: Mapping[str, Any],
    annotation_data: Mapping[str, Any],
    decision_traces: Sequence[Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    matches = adapt_harness_log(harness_log, decision_traces)
    return build_report(matches, annotation_data)


def report_to_json(report: Mapping[str, Any]) -> str:
    if report.get("schema_version") != REPORT_SCHEMA_VERSION:
        raise ValueError(
            f"Unsupported evaluator report schema version: {report.get('schema_version')!r}."
        )
    return json.dumps(
        report,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        indent=2,
    )


def evaluate_files(
    harness_path: str | Path,
    annotation_path: str | Path,
    trace_path: str | Path | None = None,
) -> dict[str, Any]:
    harness = load_json_object(harness_path)
    annotations = load_json_object(annotation_path)
    traces = None if trace_path is None else load_decision_traces_jsonl(trace_path)
    return evaluate(harness, annotations, traces)
