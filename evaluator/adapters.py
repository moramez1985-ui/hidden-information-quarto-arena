from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any

from decision_trace import DECISION_TRACE_SCHEMA_VERSION, DecisionTraceRecord


class EvaluatorInputError(ValueError):
    """Raised when an evaluation source is malformed or has an unsupported version."""


def _unique_json_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"Duplicate JSON object key: {key!r}.")
        result[key] = value
    return result


@dataclass(frozen=True, slots=True)
class MatchEvidence:
    match_id: str
    mode: str
    status: str
    action_count: int
    events: tuple[dict[str, Any], ...]
    decision_traces: tuple[dict[str, Any], ...]
    trace_source_ids: tuple[str, ...]
    decision_traces_field_present: bool
    audit_snapshot: Mapping[str, Any] | None
    integrity_qualified: bool
    exclusion_reasons: tuple[str, ...]
    source_ids: frozenset[tuple[str, str]]
    event_turn_ids: tuple[int, ...]
    trace_by_source_id: Mapping[str, dict[str, Any]]
    instance_id: str | None
    model_by_player: Mapping[str, str] | None
    starting_player: str | None
    run_id: str | None
    condition_id: str | None
    evaluation_condition: Mapping[str, Any] | None


def load_json_object(path: str | Path) -> dict[str, Any]:
    source_path = Path(path)
    try:
        value = json.loads(
            source_path.read_text(encoding="utf-8"),
            object_pairs_hook=_unique_json_object,
        )
    except (OSError, UnicodeError, ValueError) as error:
        raise EvaluatorInputError(f"Could not read JSON input {source_path}: {error}") from error
    if not isinstance(value, dict):
        raise EvaluatorInputError(f"JSON input {source_path} must contain an object.")
    return value


def load_decision_traces_jsonl(path: str | Path) -> list[dict[str, Any]]:
    source_path = Path(path)
    try:
        lines = source_path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeError) as error:
        raise EvaluatorInputError(
            f"Could not read Decision Trace JSONL {source_path}: {error}"
        ) from error

    records: list[dict[str, Any]] = []
    for line_number, line in enumerate(lines, start=1):
        if not line.strip():
            raise EvaluatorInputError(
                f"Decision Trace JSONL {source_path}, line {line_number}: blank lines are not supported."
            )
        try:
            data = json.loads(line, object_pairs_hook=_unique_json_object)
            record = DecisionTraceRecord.from_dict(data)
        except (json.JSONDecodeError, TypeError, ValueError) as error:
            raise EvaluatorInputError(
                f"Decision Trace JSONL {source_path}, line {line_number}: {error}"
            ) from error
        if record.schema_version != DECISION_TRACE_SCHEMA_VERSION:
            raise EvaluatorInputError(
                f"Decision Trace JSONL {source_path}, line {line_number}: "
                f"unsupported schema version {record.schema_version}."
            )
        records.append(record.to_dict())
    return records


def _require_nonempty_string(value: Any, field: str, context: str) -> str:
    if not isinstance(value, str) or not value:
        raise EvaluatorInputError(f"{context}: {field} must be a non-empty string.")
    return value


def _require_bool(value: Any, field: str, context: str) -> bool:
    if type(value) is not bool:
        raise EvaluatorInputError(f"{context}: {field} must be a boolean.")
    return value


def _validate_event(event: Any, context: str) -> dict[str, Any]:
    if not isinstance(event, Mapping):
        raise EvaluatorInputError(f"{context}: each harness event must be an object.")
    result = dict(event)
    attempt = result.get("attempt")
    if type(attempt) is not int or attempt < 1:
        raise EvaluatorInputError(f"{context}: event attempt must be a positive integer.")
    requester = _require_nonempty_string(result.get("requester"), "requester", context)
    if requester not in ("player_1", "player_2"):
        raise EvaluatorInputError(
            f"{context}: requester must be player_1 or player_2."
        )
    if not isinstance(result.get("prompt_messages"), list):
        raise EvaluatorInputError(f"{context}: event prompt_messages must be an array.")
    if len(result["prompt_messages"]) < 2 or any(
        not isinstance(message, Mapping)
        or not isinstance(message.get("role"), str)
        or not isinstance(message.get("content"), str)
        for message in result["prompt_messages"]
    ):
        raise EvaluatorInputError(
            f"{context}: prompt_messages must contain at least two role/content message objects."
        )
    if not isinstance(result.get("started_at"), str) or not result["started_at"]:
        raise EvaluatorInputError(f"{context}: event started_at must be a non-empty string.")
    validation = result.get("validation")
    if validation is not None and validation not in ("passed", "failed", "request_failed"):
        raise EvaluatorInputError(
            f"{context}: event validation has an unsupported value {validation!r}."
        )
    controller_validation = result.get("controller_validation")
    if controller_validation not in (None, "passed", "failed"):
        raise EvaluatorInputError(
            f"{context}: controller_validation has an unsupported value "
            f"{controller_validation!r}."
        )
    if result.get("controller_validation") == "passed":
        if not isinstance(result.get("parsed_action"), Mapping):
            raise EvaluatorInputError(
                f"{context}: an applied harness event must contain parsed_action."
            )
        if not isinstance(result.get("post_action_public_observation"), Mapping):
            raise EvaluatorInputError(
                f"{context}: an applied harness event must contain "
                "post_action_public_observation."
            )
    return result


def _validate_trace_records(
    match_id: str,
    traces: Sequence[Mapping[str, Any]],
    source_ids: Sequence[str],
    context: str,
) -> tuple[dict[int, dict[str, Any]], list[str]]:
    trace_by_turn: dict[int, dict[str, Any]] = {}
    reasons: list[str] = []
    if len(traces) != len(source_ids):
        raise EvaluatorInputError(f"{context}: trace source references are inconsistent.")
    for trace, source_id in zip(traces, source_ids):
        try:
            record = DecisionTraceRecord.from_dict(trace)
        except (TypeError, ValueError) as error:
            raise EvaluatorInputError(f"{context}: invalid Decision Trace record: {error}") from error
        if record.match_id != match_id:
            reasons.append(f"trace_match_id_mismatch:{source_id}")
        if record.turn_id in trace_by_turn:
            reasons.append(f"duplicate_trace_turn:{record.turn_id}")
        else:
            trace_by_turn[record.turn_id] = record.to_dict()
    return trace_by_turn, reasons


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


def _prompt_observation(event: Mapping[str, Any]) -> dict[str, Any] | None:
    messages = event.get("prompt_messages")
    if not isinstance(messages, list) or len(messages) < 2:
        return None
    try:
        payload = json.loads(messages[1]["content"])
    except (KeyError, TypeError, json.JSONDecodeError):
        return None
    if not isinstance(payload, Mapping):
        return None
    public = payload.get("public_observation")
    requester_private = payload.get("requester_private_observation")
    private = requester_private.get("private") if isinstance(requester_private, Mapping) else None
    if not isinstance(public, Mapping) or not isinstance(private, Mapping):
        return None
    return {"public": dict(public), "private": dict(private)}


def _result_agrees(left: Mapping[str, Any], right: Mapping[str, Any]) -> bool:
    return all(left.get(field) == right.get(field) for field in ("mode", "outcome", "winner", "reason"))


def _verify_completed_evidence(
    *,
    match_id: str,
    mode: str,
    action_count: int,
    events: Sequence[Mapping[str, Any]],
    audit: Any,
) -> list[str]:
    reasons: list[str] = []
    if not isinstance(audit, Mapping):
        return ["missing_audit_snapshot"]
    public_audit = audit.get("public_audit")
    restricted = audit.get("restricted_evaluator_data")
    if audit.get("match_id") != match_id:
        reasons.append("audit_match_id_mismatch")
    if not isinstance(public_audit, Mapping):
        return [*reasons, "missing_public_audit"]
    result = public_audit.get("result")
    if (
        public_audit.get("match_id") != match_id
        or public_audit.get("mode") != mode
        or not isinstance(result, Mapping)
        or result.get("mode") != mode
        or result.get("outcome") not in ("win", "draw")
    ):
        reasons.append("invalid_authoritative_terminal_result")
    elif (
        result.get("outcome") == "win"
        and result.get("winner") not in ("player_1", "player_2")
    ) or (
        result.get("outcome") == "draw"
        and result.get("winner") is not None
    ):
        reasons.append("inconsistent_authoritative_result")
    if not isinstance(restricted, Mapping):
        return [*reasons, "missing_restricted_replay_evidence"]

    raw_replay = restricted.get("engine_replay")
    try:
        replay = json.loads(raw_replay) if isinstance(raw_replay, str) else raw_replay
    except json.JSONDecodeError:
        replay = None
    state = restricted.get("engine_state_snapshot")
    entity_map = restricted.get("piece_to_entity")
    if (
        not isinstance(replay, Mapping)
        or type(replay.get("schema_version")) is not int
        or replay.get("schema_version") != 1
        or replay.get("mode") != mode
        or not isinstance(replay.get("actions"), list)
        or not isinstance(replay.get("result"), Mapping)
        or not isinstance(state, Mapping)
        or not isinstance(entity_map, Mapping)
    ):
        return [*reasons, "missing_or_malformed_replay_evidence"]
    replay_result = replay["result"]
    if (
        len(replay["actions"]) != action_count
        or replay_result.get("mode") != mode
        or not isinstance(result, Mapping)
        or not _result_agrees(result, replay_result)
        or not state.get("is_terminal")
        or state.get("mode") != mode
        or state.get("history") != replay["actions"]
        or not isinstance(state.get("result"), Mapping)
        or not _result_agrees(state["result"], replay_result)
    ):
        reasons.append("replay_audit_state_mismatch")

    public_history = public_audit.get("public_history")
    board = public_audit.get("board")
    state_board = state.get("board")
    if (
        not isinstance(public_history, list)
        or not isinstance(board, list)
        or len(board) != 16
        or not isinstance(state_board, list)
        or len(state_board) != 16
        or len(public_history) != action_count
        or len(replay["actions"]) != action_count
    ):
        reasons.append("incomplete_audit_history_or_board")
        return reasons

    applied_events = [
        event for event in events if event.get("controller_validation") == "passed"
    ]
    if len(applied_events) != action_count:
        reasons.append("applied_event_count_mismatch")
    piece_to_entity = {str(key): value for key, value in entity_map.items()}
    entity_to_piece = restricted.get("entity_to_piece")
    if not isinstance(entity_to_piece, Mapping):
        reasons.append("missing_entity_piece_mapping")
        entity_to_piece = {}
    for index, (action, public_action) in enumerate(
        zip(replay["actions"], public_history)
    ):
        if not isinstance(action, Mapping) or not isinstance(public_action, Mapping):
            reasons.append(f"invalid_audit_action:{index}")
            continue
        kind = action.get("kind")
        if kind == "select_piece":
            expected_public = {
                "kind": "select_entity",
                "player": action.get("player"),
                "entity_id": piece_to_entity.get(str(action.get("piece_id"))),
            }
        elif kind == "place_piece":
            expected_public = {
                "kind": "place_entity",
                "player": action.get("player"),
                "cell": action.get("cell"),
            }
        else:
            reasons.append(f"unsupported_replay_action:{index}")
            continue
        if dict(public_action) != expected_public:
            reasons.append(f"public_history_replay_mismatch:{index}")
        if index < len(applied_events):
            event = applied_events[index]
            parsed = event.get("parsed_action")
            expected_event = (
                {"kind": "select_entity", "entity_id": expected_public["entity_id"]}
                if kind == "select_piece"
                else {"kind": "place_entity", "cell": action.get("cell")}
            )
            if (
                not isinstance(parsed, Mapping)
                or dict(parsed) != expected_event
                or event.get("requester") != action.get("player")
            ):
                reasons.append(f"event_replay_mismatch:{index}")

    expected_board = [
        None if piece is None else piece_to_entity.get(str(piece))
        for piece in state_board
    ]
    if expected_board != board:
        reasons.append("audit_board_state_mismatch")
    if any(
        entity_to_piece.get(entity) != int(piece)
        for piece, entity in piece_to_entity.items()
        if isinstance(entity, str) and piece.isdigit()
    ):
        reasons.append("inconsistent_entity_piece_mapping")
    return reasons


def _adapt_match(
    raw_match: Any,
    *,
    external_traces: Sequence[tuple[int, dict[str, Any]]],
    external_trace_input: bool,
    inherited_run_id: str | None,
    inherited_condition_id: str | None,
    context: str,
) -> MatchEvidence:
    if not isinstance(raw_match, Mapping):
        raise EvaluatorInputError(f"{context}: each match must be an object.")
    match = dict(raw_match)
    if "schema_version" in match:
        raise EvaluatorInputError(
            f"{context}: the supported Tournament Harness restricted-log format is "
            "unversioned; a schema_version field is not supported."
        )
    match_id = _require_nonempty_string(match.get("match_id"), "match_id", context)
    mode = _require_nonempty_string(match.get("mode"), "mode", context)
    status = _require_nonempty_string(match.get("status"), "status", context)
    action_count = match.get("action_count")
    if type(action_count) is not int or action_count < 0:
        raise EvaluatorInputError(f"{context}: action_count must be a non-negative integer.")
    audit_valid = _require_bool(match.get("audit_valid"), "audit_valid", context)
    replay_valid = _require_bool(match.get("replay_valid"), "replay_valid", context)
    raw_events = match.get("events")
    trace_field_present = "decision_traces" in match
    raw_traces = match.get("decision_traces", [])
    if not isinstance(raw_events, list):
        raise EvaluatorInputError(f"{context}: events must be an array.")
    if not isinstance(raw_traces, list):
        raise EvaluatorInputError(f"{context}: decision_traces must be an array.")

    events = tuple(
        _validate_event(event, f"{context}, events[{index}]")
        for index, event in enumerate(raw_events)
    )
    embedded: list[tuple[str, dict[str, Any]]] = []
    for index, raw_trace in enumerate(raw_traces):
        try:
            trace = DecisionTraceRecord.from_dict(raw_trace).to_dict()
        except (TypeError, ValueError) as error:
            raise EvaluatorInputError(
                f"{context}, decision_traces[{index}]: {error}"
            ) from error
        embedded.append((f"decision_traces[{index}]", trace))
    if embedded and external_traces:
        raise EvaluatorInputError(
            f"{context}: both embedded and JSONL traces were supplied for match {match_id}."
        )
    trace_pairs = embedded or [
        (f"decision_trace_lines[{line_index}]", trace)
        for line_index, trace in external_traces
    ]
    traces = tuple(trace for _, trace in trace_pairs)
    trace_source_ids = tuple(source_id for source_id, _ in trace_pairs)
    trace_by_turn, trace_reasons = _validate_trace_records(
        match_id,
        traces,
        trace_source_ids,
        context,
    )

    reasons: list[str] = []
    if mode != "classic":
        reasons.append(f"unsupported_game_mode:{mode}")
    if status != "completed":
        reasons.append(f"status_not_completed:{status}")
    if status == "completed" and not audit_valid:
        reasons.append("audit_invalid")
    if status == "completed" and not replay_valid:
        reasons.append("replay_invalid")
    applied_events = [
        (index, event)
        for index, event in enumerate(events)
        if event.get("controller_validation") == "passed"
    ]
    event_turn_ids: list[int] = []
    current_turn = 1
    expected_attempt = 1
    for index, event in enumerate(events):
        event_turn_ids.append(current_turn)
        if event["attempt"] != expected_attempt:
            reasons.append(f"response_attempt_sequence_invalid:{index}")
        if event.get("controller_validation") == "passed":
            current_turn += 1
            expected_attempt = 1
        else:
            expected_attempt += 1
    if status == "completed":
        if action_count < 1:
            reasons.append("no_applied_actions")
        if len(applied_events) != action_count:
            reasons.append("applied_event_count_mismatch")
        for index, event in enumerate(events):
            if (
                not isinstance(event.get("response_content"), str)
                or not isinstance(event.get("raw_response"), str)
                or not isinstance(event.get("completed_at"), str)
                or event.get("validation") not in ("passed", "failed")
            ):
                reasons.append(f"incomplete_event:{index}")
                break
            if (
                event.get("controller_validation") == "passed"
                and event.get("validation") != "passed"
            ):
                reasons.append(f"applied_event_validation_mismatch:{index}")
        reasons.extend(
            _verify_completed_evidence(
                match_id=match_id,
                mode=mode,
                action_count=action_count,
                events=events,
                audit=match.get("audit_snapshot"),
            )
        )
        if not traces and (trace_field_present or external_trace_input):
            reasons.append("trace_turn_coverage_mismatch")

    reasons.extend(trace_reasons)
    if traces:
        if len(trace_by_turn) != action_count or set(trace_by_turn) != set(
            range(1, action_count + 1)
        ):
            reasons.append("trace_turn_coverage_mismatch")
        for turn_id, (_, event) in enumerate(applied_events, start=1):
            trace = trace_by_turn.get(turn_id)
            if trace is None:
                continue
            if trace["agent_id"] != event["requester"]:
                reasons.append(f"trace_agent_mismatch:{turn_id}")
            if trace["selected_action"] != event.get("parsed_action"):
                reasons.append(f"trace_action_mismatch:{turn_id}")
            turn_events = [
                candidate
                for candidate_index, candidate in enumerate(events)
                if event_turn_ids[candidate_index] == turn_id
            ]
            prompt = _prompt_observation(turn_events[0]) if turn_events else None
            if prompt is None or trace["observation_snapshot"] != prompt:
                reasons.append(f"trace_observation_mismatch:{turn_id}")

    source_ids: set[tuple[str, str]] = {
        ("harness_event", f"events[{index}]")
        for index in range(len(events))
    }
    source_ids.update(
        ("decision_trace", source_id)
        for source_id in trace_source_ids
    )
    if isinstance(match.get("audit_snapshot"), Mapping):
        source_ids.add(("audit_record", "audit_snapshot.public_audit"))
        if "restricted_evaluator_data" in match["audit_snapshot"]:
            source_ids.add(("audit_record", "audit_snapshot.restricted_evaluator_data"))

    model_by_player = match.get("model_by_player")
    if model_by_player is not None:
        if not isinstance(model_by_player, Mapping) or any(
            actor not in ("player_1", "player_2") or not isinstance(model, str)
            for actor, model in model_by_player.items()
        ):
            raise EvaluatorInputError(
                f"{context}: model_by_player must map player seats to model identifiers."
            )
        model_by_player = dict(model_by_player)
    else:
        model_by_player = None
    starting_player = match.get("starting_player")
    if starting_player is not None and starting_player not in ("player_1", "player_2"):
        raise EvaluatorInputError(
            f"{context}: starting_player must be player_1 or player_2."
        )
    instance_id = match.get("instance_id")
    if instance_id is not None and not isinstance(instance_id, str):
        raise EvaluatorInputError(f"{context}: instance_id must be a string when present.")
    run_id = match.get("run_id", inherited_run_id)
    condition_id = match.get(
        "condition_id",
        match.get("evaluation_condition_id", inherited_condition_id),
    )
    evaluation_condition = match.get("evaluation_condition")
    if run_id is not None and not isinstance(run_id, str):
        raise EvaluatorInputError(f"{context}: run_id must be a string when present.")
    if condition_id is not None and not isinstance(condition_id, str):
        raise EvaluatorInputError(
            f"{context}: condition_id must be a string when present."
        )
    if evaluation_condition is not None and not isinstance(evaluation_condition, Mapping):
        raise EvaluatorInputError(
            f"{context}: evaluation_condition must be an object when present."
        )
    trace_by_source_id = {
        source_id: trace for source_id, trace in trace_pairs
    }

    return MatchEvidence(
        match_id=match_id,
        mode=mode,
        status=status,
        action_count=action_count,
        events=events,
        decision_traces=traces,
        trace_source_ids=trace_source_ids,
        decision_traces_field_present=trace_field_present,
        audit_snapshot=match.get("audit_snapshot"),
        integrity_qualified=not reasons,
        exclusion_reasons=tuple(dict.fromkeys(reasons)),
        source_ids=frozenset(source_ids),
        event_turn_ids=tuple(event_turn_ids),
        trace_by_source_id=trace_by_source_id,
        instance_id=instance_id,
        model_by_player=model_by_player,
        starting_player=starting_player,
        run_id=run_id,
        condition_id=condition_id,
        evaluation_condition=evaluation_condition,
    )


def adapt_harness_log(
    data: Mapping[str, Any],
    decision_traces: Sequence[Mapping[str, Any]] | None = None,
) -> list[MatchEvidence]:
    """Validate a restricted Harness log and optional Decision Trace v1 JSONL rows."""
    if not isinstance(data, Mapping):
        raise EvaluatorInputError("Tournament Harness input must be an object.")
    if "schema_version" in data:
        raise EvaluatorInputError(
            "The supported Tournament Harness restricted-log format is unversioned; "
            "a schema_version field is not supported."
        )
    if "matches" in data:
        raw_matches = data["matches"]
        if not isinstance(raw_matches, list):
            raise EvaluatorInputError("Tournament Harness matches must be an array.")
    elif "match_id" in data:
        raw_matches = [data]
    else:
        raise EvaluatorInputError(
            "Expected a restricted Harness log with matches, or one restricted match record."
        )

    external_trace_input = decision_traces is not None
    inherited_run_id = data.get("run_id", data.get("evaluation_run_id"))
    inherited_condition_id = data.get(
        "condition_id", data.get("evaluation_condition_id")
    )
    external_by_match: dict[str, list[tuple[int, dict[str, Any]]]] = {}
    for line_index, raw_trace in enumerate(decision_traces or ()):
        try:
            trace = DecisionTraceRecord.from_dict(raw_trace).to_dict()
        except (TypeError, ValueError) as error:
            raise EvaluatorInputError(
                f"External Decision Trace JSONL row {line_index}: {error}"
            ) from error
        external_by_match.setdefault(trace["match_id"], []).append((line_index, trace))

    matches: list[MatchEvidence] = []
    seen_match_ids: set[str] = set()
    for index, raw_match in enumerate(raw_matches):
        context = f"matches[{index}]"
        if not isinstance(raw_match, Mapping):
            raise EvaluatorInputError(f"{context}: each match must be an object.")
        raw_id = raw_match.get("match_id")
        if not isinstance(raw_id, str) or not raw_id:
            raise EvaluatorInputError(f"{context}: match_id must be a non-empty string.")
        if raw_id in seen_match_ids:
            raise EvaluatorInputError(f"{context}: duplicate match_id {raw_id!r}.")
        seen_match_ids.add(raw_id)
        matches.append(
            _adapt_match(
                raw_match,
                external_traces=external_by_match.pop(raw_id, ()),
                external_trace_input=external_trace_input,
                inherited_run_id=inherited_run_id,
                inherited_condition_id=inherited_condition_id,
                context=context,
            )
        )
    if external_by_match:
        unmatched = sorted(external_by_match)
        raise EvaluatorInputError(
            f"Decision Trace records refer to matches absent from the Harness log: {unmatched}."
        )
    return matches
