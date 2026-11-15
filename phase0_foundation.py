from __future__ import annotations

import copy
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from itertools import combinations
from random import Random
import secrets
from types import MappingProxyType
from typing import Any, Protocol, runtime_checkable
from uuid import UUID, uuid4

from quarto_engine import (
    GameState,
    Mode,
    Player,
    legal_actions,
    new_game,
    place_piece,
    replay_game,
    select_piece,
    serialize_replay,
)


PUBLIC_ACTION_KIND_PROPOSE = "propose_feature"
PUBLIC_ACTION_KIND_SELECT = "select_entity"
PUBLIC_ACTION_KIND_PLACE = "place_entity"

PUBLIC_AUDIT_FIELDS = frozenset({
    "match_id",
    "mode",
    "starting_player",
    "phase",
    "current_player",
    "selected_entity",
    "board",
    "draft_history",
    "public_history",
    "result",
    "legal_actions",
})
_REQUIRED_RESTRICTED_AUDIT_FIELDS = frozenset({
    "entity_to_piece",
    "piece_to_entity",
    "feature_to_bit",
    "private_feature_ownership",
    "engine_replay",
    "engine_state_snapshot",
})
_RESTRICTED_AUDIT_FIELDS = _REQUIRED_RESTRICTED_AUDIT_FIELDS | {
    "instance_validation",
    "public_entity_to_source_id",
    "draft_history",
    "secret_bit_permutation",
}
_ENGINE_STATE_FIELDS = frozenset({
    "mode",
    "starting_player",
    "phase",
    "active_player",
    "board",
    "selected_piece",
    "selected_by",
    "remaining_pieces",
    "is_terminal",
    "result",
    "history",
})
_ENGINE_RESULT_FIELDS = frozenset({"mode", "outcome", "winner", "reason"})

CONTROLLER_PUBLIC_OBSERVATION_FIELDS = frozenset({
    "mode",
    "phase",
    "current_player",
    "public_entities",
    "feature_definitions",
    "board",
    "available_entities",
    "selected_entity",
    "legal_actions",
    "history",
    "terminal",
})
PUBLIC_PROMPT_OBSERVATION_FIELDS = (
    "mode",
    "phase",
    "current_player",
    "public_entities",
    "feature_definitions",
    "board",
    "available_entities",
    "selected_entity",
    "legal_actions",
    "history",
    "terminal",
)
PRIVATE_OBSERVATION_FIELDS = CONTROLLER_PUBLIC_OBSERVATION_FIELDS | {
    "requester",
    "private",
}
PRIVATE_PAYLOAD_FIELDS = frozenset({
    "owned_features",
    "proposal_feedback",
    "rejected_features",
})


def _is_opaque_entity_id(value: object) -> bool:
    if not isinstance(value, str) or len(value) != 32:
        return False
    try:
        parsed = UUID(hex=value)
    except ValueError:
        return False
    return parsed.version == 4 and parsed.hex == value


def _format_observation_field_names(fields: Iterable[object]) -> str:
    field_values = list(fields)
    names = sorted(field for field in field_values if isinstance(field, str))
    if len(names) < len(field_values):
        names.append("<non-string>")
    return ", ".join(names) if names else "none"


def _require_observation_fields(
    value: object,
    expected: frozenset[str] | set[str],
    location: str,
) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{location} must be an object.")
    actual = set(value)
    missing = expected - actual
    unexpected = actual - expected
    if missing or unexpected:
        details = []
        if missing:
            details.append(
                f"missing: {_format_observation_field_names(missing)}"
            )
        if unexpected:
            details.append("unexpected field(s)")
        raise ValueError(
            f"{location} has invalid fields ({'; '.join(details)})."
        )
    return value


def _require_public_entity_id(
    value: object,
    known_entity_ids: set[str],
    location: str,
) -> None:
    if not _is_opaque_entity_id(value) or value not in known_entity_ids:
        raise ValueError(f"{location} must reference a public entity ID.")


def validate_public_observation(observation: Mapping[str, Any]) -> None:
    _require_observation_fields(
        observation,
        CONTROLLER_PUBLIC_OBSERVATION_FIELDS,
        "Public observation",
    )
    if observation["mode"] not in ("classic", "self_selection"):
        raise ValueError("Public observation mode is invalid.")
    if observation["phase"] not in ("draft", "select", "place", "terminal"):
        raise ValueError("Public observation phase is invalid.")
    if observation["current_player"] not in ("player_1", "player_2"):
        raise ValueError("Public observation current_player is invalid.")
    if type(observation["terminal"]) is not bool:
        raise ValueError("Public observation terminal must be a boolean.")
    if observation["terminal"] != (observation["phase"] == "terminal"):
        raise ValueError("Public observation phase and terminal flag are inconsistent.")

    feature_defs = observation["feature_definitions"]
    if not isinstance(feature_defs, list) or len(feature_defs) < 4:
        raise ValueError("Public observation feature_definitions must contain at least 4 entries.")
    known_feature_ids: list[str] = []
    for index, feat in enumerate(feature_defs):
        location = f"Public observation feature_definitions[{index}]"
        if not isinstance(feat, dict):
            raise ValueError(f"{location} must be an object.")
        _require_observation_fields(
            feat,
            {"feature_id", "name", "definition", "value_semantics"},
            location,
        )
        fid = feat["feature_id"]
        if not isinstance(fid, str) or not fid:
            raise ValueError(f"{location}.feature_id must be a non-empty string.")
        if not isinstance(feat["name"], str) or not feat["name"]:
            raise ValueError(f"{location}.name must be a non-empty string.")
        if not isinstance(feat["definition"], str) or not feat["definition"]:
            raise ValueError(f"{location}.definition must be a non-empty string.")
        if feat["value_semantics"] != "binary":
            raise ValueError(f"{location}.value_semantics must be 'binary'.")
        known_feature_ids.append(fid)
    expected_feature_set = set(known_feature_ids)
    if len(expected_feature_set) != len(known_feature_ids):
        raise ValueError("Public observation feature_definitions contains duplicate feature IDs.")

    entities = observation["public_entities"]
    if not isinstance(entities, list) or len(entities) != 16:
        raise ValueError("Public observation public_entities must contain 16 entries.")
    entity_ids: list[str] = []
    for index, entity in enumerate(entities):
        location = f"Public observation public_entities[{index}]"
        if not isinstance(entity, dict):
            raise ValueError(f"{location} must be an object.")
        _require_observation_fields(entity, {"entity_id", "label", "features"}, location)
        entity_id = entity["entity_id"]
        if not _is_opaque_entity_id(entity_id):
            raise ValueError(f"{location}.entity_id must be an opaque public UUID.")
        if not isinstance(entity["label"], str) or entity["label"] != entity_id:
            raise ValueError(f"{location}.label must equal its public entity ID.")
        features_map = entity["features"]
        if not isinstance(features_map, dict) or set(features_map) != expected_feature_set:
            raise ValueError(f"{location}.features must match feature_definitions keys exactly.")
        if any(type(val) is not bool for val in features_map.values()):
            raise ValueError(f"{location}.features values must be booleans.")
        entity_ids.append(entity_id)
    known_entity_ids = set(entity_ids)
    if len(known_entity_ids) != 16:
        raise ValueError("Public observation public entity IDs must be unique.")

    board = observation["board"]
    if not isinstance(board, list) or len(board) != 16:
        raise ValueError("Public observation board must contain 16 cells.")
    board_ids = [entity_id for entity_id in board if entity_id is not None]
    for index, entity_id in enumerate(board):
        if entity_id is not None:
            _require_public_entity_id(
                entity_id,
                known_entity_ids,
                f"Public observation board[{index}]",
            )
    if len(board_ids) != len(set(board_ids)):
        raise ValueError("Public observation board contains duplicate entity IDs.")

    available = observation["available_entities"]
    if not isinstance(available, list):
        raise ValueError("Public observation available_entities must be an array.")
    for index, entity_id in enumerate(available):
        _require_public_entity_id(
            entity_id,
            known_entity_ids,
            f"Public observation available_entities[{index}]",
        )
    available_ids = set(available)
    if len(available_ids) != len(available):
        raise ValueError("Public observation available_entities contains duplicates.")
    if set(board_ids) & available_ids:
        raise ValueError("Public observation board and available_entities overlap.")

    phase = observation["phase"]
    selected_entity = observation["selected_entity"]
    if selected_entity is not None:
        _require_public_entity_id(
            selected_entity,
            known_entity_ids,
            "Public observation selected_entity",
        )
    if phase == "draft":
        if selected_entity is not None:
            raise ValueError("Public observation selected_entity must be null in draft phase.")
        if board_ids or available_ids != known_entity_ids:
            raise ValueError("Public observation board must be empty and all entities available in draft phase.")
    elif phase == "select":
        if selected_entity is not None:
            raise ValueError("Public observation selected_entity must be null in select phase.")
        if set(board_ids) | available_ids != known_entity_ids:
            raise ValueError("Public observation entities do not partition the board and available set.")
    elif phase == "place":
        if selected_entity is None:
            raise ValueError("Public observation selected_entity is required in place phase.")
        if selected_entity not in available_ids:
            raise ValueError("Public observation selected_entity is not available for placement.")
        if set(board_ids) | available_ids != known_entity_ids:
            raise ValueError("Public observation entities do not partition the current state.")
    else:
        if selected_entity is not None:
            raise ValueError("Public observation selected_entity must be null when terminal.")
        if set(board_ids) | available_ids != known_entity_ids:
            raise ValueError("Public observation entities do not partition the terminal state.")

    legal_actions_obj = observation["legal_actions"]
    if not isinstance(legal_actions_obj, dict):
        raise ValueError("Public observation legal_actions must be an object.")
    expected_legal_keys = (
        {"kind", "feature_ids"}
        if phase == "draft"
        else {"kind", "entity_ids"}
        if phase == "select"
        else {"kind", "cells"}
        if phase == "place"
        else {"kind"}
    )
    legal = _require_observation_fields(
        legal_actions_obj,
        expected_legal_keys,
        "Public observation legal_actions",
    )
    if phase == "draft":
        if legal["kind"] != PUBLIC_ACTION_KIND_PROPOSE:
            raise ValueError("Public observation legal_actions.kind is invalid for draft phase.")
        legal_features = legal["feature_ids"]
        if not isinstance(legal_features, list) or len(legal_features) < 4:
            raise ValueError("Public observation legal_actions.feature_ids must list candidate features.")
        if any(not isinstance(fid, str) or fid not in expected_feature_set for fid in legal_features):
            raise ValueError("Public observation legal_actions.feature_ids contains unknown features.")
        if len(legal_features) != len(set(legal_features)):
            raise ValueError("Public observation legal feature IDs must be unique.")
    elif phase == "select":
        if legal["kind"] != PUBLIC_ACTION_KIND_SELECT:
            raise ValueError("Public observation legal_actions.kind is invalid for select phase.")
        legal_entities = legal["entity_ids"]
        if not isinstance(legal_entities, list):
            raise ValueError("Public observation legal_actions.entity_ids must be an array.")
        for index, entity_id in enumerate(legal_entities):
            _require_public_entity_id(
                entity_id,
                known_entity_ids,
                f"Public observation legal_actions.entity_ids[{index}]",
            )
        if len(legal_entities) != len(set(legal_entities)):
            raise ValueError("Public observation legal entity IDs must be unique.")
        if set(legal_entities) != available_ids:
            raise ValueError("Public observation legal entities do not match available entities.")
    elif phase == "place":
        if legal["kind"] != PUBLIC_ACTION_KIND_PLACE:
            raise ValueError("Public observation legal_actions.kind is invalid for place phase.")
        cells = legal["cells"]
        if not isinstance(cells, list) or any(
            type(cell) is not int or not 0 <= cell < 16 for cell in cells
        ):
            raise ValueError("Public observation legal_actions.cells must be valid cell indices.")
        if len(cells) != len(set(cells)):
            raise ValueError("Public observation legal_actions.cells contains duplicates.")
        if cells != [index for index, entity_id in enumerate(board) if entity_id is None]:
            raise ValueError("Public observation legal cells do not match the board.")
    elif legal["kind"] != "terminal":
        raise ValueError("Public observation legal_actions.kind must be terminal.")

    history = observation["history"]
    if not isinstance(history, list):
        raise ValueError("Public observation history must be an array.")
    for index, action in enumerate(history):
        location = f"Public observation history[{index}]"
        if not isinstance(action, dict):
            raise ValueError(f"{location} must be an object.")
        kind = action.get("kind")
        if kind == PUBLIC_ACTION_KIND_SELECT:
            action = _require_observation_fields(
                action,
                {"kind", "player", "entity_id"},
                location,
            )
            if action["player"] not in ("player_1", "player_2"):
                raise ValueError(f"{location}.player is invalid.")
            _require_public_entity_id(
                action["entity_id"],
                known_entity_ids,
                f"{location}.entity_id",
            )
        elif kind == PUBLIC_ACTION_KIND_PLACE:
            action = _require_observation_fields(
                action,
                {"kind", "player", "cell"},
                location,
            )
            if action["player"] not in ("player_1", "player_2"):
                raise ValueError(f"{location}.player is invalid.")
            cell = action["cell"]
            if type(cell) is not int or not 0 <= cell < 16:
                raise ValueError(f"{location}.cell must be a valid cell index.")
        else:
            raise ValueError(f"{location}.kind is invalid.")


def _project_validated_public_observation(
    observation: Mapping[str, Any],
) -> dict[str, Any]:
    base_fields = (
        "mode",
        "phase",
        "current_player",
        "board",
        "available_entities",
        "selected_entity",
        "legal_actions",
        "history",
        "terminal",
    )
    projected = {
        field: copy.deepcopy(observation[field])
        for field in base_fields
    }
    if "draft_history" in observation:
        for extra in ("public_entities", "feature_definitions"):
            if extra in observation:
                projected[extra] = copy.deepcopy(observation[extra])
    return projected


def project_public_observation(
    observation: Mapping[str, Any],
) -> dict[str, Any]:
    validate_public_observation(observation)
    return _project_validated_public_observation(observation)


def project_agent_observations(
    public_observation: Mapping[str, Any],
    private_observation: Mapping[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    validate_public_observation(public_observation)
    private_observation = _require_observation_fields(
        private_observation,
        PRIVATE_OBSERVATION_FIELDS,
        "Private observation",
    )
    requester = private_observation["requester"]
    active_player = public_observation["current_player"]
    if requester not in ("player_1", "player_2") or requester != active_player:
        raise ValueError("Private observation requester does not match the active player.")

    embedded_public_observation = {
        field: private_observation[field]
        for field in CONTROLLER_PUBLIC_OBSERVATION_FIELDS
    }
    validate_public_observation(embedded_public_observation)
    if embedded_public_observation != dict(public_observation):
        raise ValueError("Private observation does not match the active public observation.")

    private_payload = private_observation["private"]
    if not isinstance(private_payload, dict):
        raise ValueError("Private observation private payload must be an object.")
    private = _require_observation_fields(
        private_payload,
        PRIVATE_PAYLOAD_FIELDS,
        "Private observation private payload",
    )
    phase = public_observation["phase"]
    owned_features = private["owned_features"]
    expected_owned_count = 2 if phase != "draft" else None
    if (
        not isinstance(owned_features, list)
        or len(owned_features) > 2
        or (expected_owned_count is not None and len(owned_features) != expected_owned_count)
        or any(not isinstance(feature_id, str) or not feature_id for feature_id in owned_features)
        or len(set(owned_features)) != len(owned_features)
    ):
        raise ValueError("Private observation owned_features is invalid for the current phase.")
    feedback = private["proposal_feedback"]
    if feedback is not None and not isinstance(feedback, str):
        raise ValueError("Private observation proposal_feedback must be a string or null.")
    rejected = private["rejected_features"]
    if (
        not isinstance(rejected, list)
        or any(not isinstance(fid, str) or not fid for fid in rejected)
        or len(set(rejected)) != len(rejected)
    ):
        raise ValueError("Private observation rejected_features must be a list of unique strings.")

    return (
        _project_validated_public_observation(public_observation),
        {"private": copy.deepcopy(dict(private))},
    )


def _is_match_id(value: object) -> bool:
    if not isinstance(value, str) or not value.startswith("match:"):
        return False
    try:
        parsed = UUID(value[len("match:"):])
    except ValueError:
        return False
    return parsed.version == 4


def _valid_public_audit_shape(
    public_audit: Mapping[str, Any],
    match_id: str,
    known_entity_ids: set[str],
) -> bool:
    if set(public_audit) != PUBLIC_AUDIT_FIELDS:
        return False
    if public_audit.get("match_id") != match_id or not _is_match_id(match_id):
        return False

    mode = public_audit.get("mode")
    starting_player = public_audit.get("starting_player")
    phase = public_audit.get("phase")
    current_player = public_audit.get("current_player")
    if mode not in ("classic", "self_selection"):
        return False
    if starting_player not in ("player_1", "player_2"):
        return False
    if current_player not in ("player_1", "player_2"):
        return False
    if phase not in ("draft", "select", "place", "terminal"):
        return False

    selected_entity = public_audit.get("selected_entity")
    if selected_entity is not None and (
        not _is_opaque_entity_id(selected_entity)
        or selected_entity not in known_entity_ids
    ):
        return False
    if (phase == "place") != (selected_entity is not None):
        return False

    board = public_audit.get("board")
    if not isinstance(board, (tuple, list)) or len(board) != 16:
        return False
    board_entities = [entity_id for entity_id in board if entity_id is not None]
    if any(
        not _is_opaque_entity_id(entity_id) or entity_id not in known_entity_ids
        for entity_id in board_entities
    ):
        return False
    if len(board_entities) != len(set(board_entities)):
        return False

    history = public_audit.get("public_history")
    if not isinstance(history, (tuple, list)):
        return False
    for action in history:
        if not isinstance(action, Mapping):
            return False
        if action.get("kind") == "select_entity":
            if set(action) != {"kind", "player", "entity_id"}:
                return False
            if action.get("player") not in ("player_1", "player_2"):
                return False
            entity_id = action.get("entity_id")
            if (
                not _is_opaque_entity_id(entity_id)
                or entity_id not in known_entity_ids
            ):
                return False
        elif action.get("kind") == "place_entity":
            if set(action) != {"kind", "player", "cell"}:
                return False
            if action.get("player") not in ("player_1", "player_2"):
                return False
            if type(action.get("cell")) is not int or not 0 <= action["cell"] < 16:
                return False
        else:
            return False

    result = public_audit.get("result")
    if result is None:
        if phase == "terminal":
            return False
    else:
        if not isinstance(result, Mapping) or set(result) != _ENGINE_RESULT_FIELDS:
            return False
        if result.get("mode") != mode:
            return False
        if result.get("outcome") == "win":
            if (
                result.get("winner") not in ("player_1", "player_2")
                or result.get("reason") != "quarto"
            ):
                return False
        elif result.get("outcome") == "draw":
            if result.get("winner") is not None or result.get("reason") != "board_full":
                return False
        else:
            return False
        if phase != "terminal":
            return False

    legal_actions_obj = public_audit.get("legal_actions")
    if not isinstance(legal_actions_obj, Mapping):
        return False
    action_kind = legal_actions_obj.get("kind")
    if phase == "draft":
        if set(legal_actions_obj) != {"kind", "feature_ids"} or action_kind != PUBLIC_ACTION_KIND_PROPOSE:
            return False
        feature_ids = legal_actions_obj.get("feature_ids")
        if not isinstance(feature_ids, (tuple, list)) or len(feature_ids) < 4:
            return False
        if any(not isinstance(fid, str) or not fid for fid in feature_ids):
            return False
        if len(feature_ids) != len(set(feature_ids)):
            return False
    elif phase == "select":
        if set(legal_actions_obj) != {"kind", "entity_ids"} or action_kind != "select_entity":
            return False
        entity_ids = legal_actions_obj.get("entity_ids")
        if not isinstance(entity_ids, (tuple, list)):
            return False
        if any(
            not _is_opaque_entity_id(entity_id)
            or entity_id not in known_entity_ids
            for entity_id in entity_ids
        ):
            return False
        if len(entity_ids) != len(set(entity_ids)):
            return False
    elif phase == "place":
        if set(legal_actions_obj) != {"kind", "cells"} or action_kind != "place_entity":
            return False
        cells = legal_actions_obj.get("cells")
        if not isinstance(cells, (tuple, list)):
            return False
        if any(type(cell) is not int or not 0 <= cell < 16 for cell in cells):
            return False
        if len(cells) != len(set(cells)):
            return False
    elif set(legal_actions_obj) != {"kind"} or action_kind != "terminal":
        return False
    return True


def _freeze_value(value: Any) -> Any:
    if isinstance(value, MappingProxyType):
        return MappingProxyType({key: _freeze_value(item) for key, item in value.items()})
    if isinstance(value, Mapping):
        return MappingProxyType({key: _freeze_value(item) for key, item in value.items()})
    if isinstance(value, list):
        return tuple(_freeze_value(item) for item in value)
    if isinstance(value, tuple):
        return tuple(_freeze_value(item) for item in value)
    if isinstance(value, set):
        return frozenset(_freeze_value(item) for item in value)
    return value


@dataclass(frozen=True, slots=True)
class FeatureDefinition:
    feature_id: str
    name: str
    definition: str
    value_semantics: str = "binary"


@dataclass(frozen=True, slots=True)
class PublicEntity:
    entity_id: str
    label: str


@dataclass(frozen=True, slots=True)
class DomainCatalog:
    name: str
    version: str
    entities: tuple[PublicEntity, ...]
    features: tuple[FeatureDefinition, ...]
    values: MappingProxyType[str, MappingProxyType[str, bool]]
    gameplay_feature_ids: tuple[str, ...] | None = None


@dataclass(frozen=True, slots=True)
class InstanceSpec:
    instance_id: str
    domain_name: str
    feature_ids: tuple[str, ...]
    entity_ids: tuple[str, ...]
    signature_map: MappingProxyType[str, int]
    public_seed: int | None = None


class DomainAdapter(Protocol):
    def load_domain(self) -> DomainCatalog: ...

    def build_instance(self) -> InstanceSpec: ...


@runtime_checkable
class InstanceValidationCapability(Protocol):
    def validate_instance(
        self,
        domain: DomainCatalog,
        instance: InstanceSpec,
    ) -> Mapping[str, Any]: ...


class InstanceValidationError(ValueError):
    def __init__(self, validation_record: Mapping[str, Any]) -> None:
        self.validation_record = _freeze_value(validation_record)
        result = validation_record.get("quartet_validation")
        reasons = getattr(result, "rejection_reasons", ())
        reason_text = "; ".join(
            getattr(reason, "message", str(reason)) for reason in reasons
        )
        super().__init__(
            "Instance failed per-instance Quartet validation"
            + (f": {reason_text}" if reason_text else ".")
        )


def _has_exact_engine_state_fields(snapshot: Any) -> bool:
    return isinstance(snapshot, Mapping) and set(snapshot) == _ENGINE_STATE_FIELDS


def _matches_replayed_snapshot(actual: Any, expected: Any) -> bool:
    if isinstance(expected, Mapping):
        return (
            isinstance(actual, Mapping)
            and set(actual) == set(expected)
            and all(
                _matches_replayed_snapshot(actual[key], value)
                for key, value in expected.items()
            )
        )
    if isinstance(expected, tuple):
        return (
            isinstance(actual, tuple)
            and len(actual) == len(expected)
            and all(
                _matches_replayed_snapshot(actual_value, expected_value)
                for actual_value, expected_value in zip(actual, expected)
            )
        )
    return type(actual) is type(expected) and actual == expected


@dataclass(frozen=True, slots=True)
class AuditSnapshot:
    match_id: str
    public_audit: MappingProxyType[str, Any]
    restricted_evaluator_data: MappingProxyType[str, Any]

    def validate_replay(self) -> bool:
        if not isinstance(self.restricted_evaluator_data, Mapping):
            return False
        if self.public_audit.get("phase") == "draft":
            return True
        replay = self.restricted_evaluator_data.get("engine_replay")
        state_snapshot = self.restricted_evaluator_data.get("engine_state_snapshot")
        if (
            not isinstance(replay, str)
            or not isinstance(state_snapshot, MappingProxyType)
            or not _has_exact_engine_state_fields(state_snapshot)
        ):
            return False
        try:
            replayed_state = replay_game(replay)
        except Exception:
            return False

        encoded_snapshot = {
            "mode": replayed_state.mode,
            "starting_player": replayed_state.starting_player,
            "phase": replayed_state.phase,
            "active_player": replayed_state.active_player,
            "board": tuple(replayed_state.board),
            "remaining_pieces": tuple(replayed_state.remaining_pieces),
            "selected_piece": replayed_state.selected_piece,
            "selected_by": replayed_state.selected_by,
            "is_terminal": replayed_state.is_terminal,
            "result": None if replayed_state.result is None else {
                "mode": replayed_state.result.mode,
                "outcome": replayed_state.result.outcome,
                "winner": replayed_state.result.winner,
                "reason": replayed_state.result.reason,
            },
            "history": tuple(
                {
                    "kind": record.kind,
                    "player": record.player,
                    "piece_id": record.piece_id,
                    "cell": record.cell,
                }
                for record in replayed_state.history
            ),
        }
        return _matches_replayed_snapshot(state_snapshot, encoded_snapshot)


def validate_audit_snapshot(snapshot: AuditSnapshot) -> bool:
    if not isinstance(snapshot, AuditSnapshot):
        return False

    for attr_name in ("public_audit", "restricted_evaluator_data"):
        value = getattr(snapshot, attr_name)
        if not isinstance(value, MappingProxyType):
            return False

    if not isinstance(snapshot.match_id, str) or not snapshot.match_id:
        return False

    if not snapshot.validate_replay():
        return False

    public_audit = dict(snapshot.public_audit)
    restricted = dict(snapshot.restricted_evaluator_data)
    if set(public_audit) != PUBLIC_AUDIT_FIELDS:
        return False
    if not _REQUIRED_RESTRICTED_AUDIT_FIELDS.issubset(restricted):
        return False
    if not set(restricted).issubset(_RESTRICTED_AUDIT_FIELDS):
        return False

    instance_validation = restricted.get("instance_validation")
    if "instance_validation" in restricted:
        if not isinstance(instance_validation, Mapping):
            return False
        quartet_validation = instance_validation.get("quartet_validation")
        if (
            instance_validation.get("match_id") != snapshot.match_id
            or not isinstance(instance_validation.get("instance_id"), str)
            or instance_validation.get("accepted") is not True
            or getattr(quartet_validation, "accepted", False) is not True
            or getattr(quartet_validation, "instance_id", None)
            != instance_validation.get("instance_id")
            or type(instance_validation.get("id_level_count")) is not int
            or instance_validation["id_level_count"]
            != getattr(quartet_validation, "id_level_count", None)
            or instance_validation["id_level_count"] <= 1
            or type(instance_validation.get("structural_count")) is not int
            or instance_validation["structural_count"]
            != getattr(quartet_validation, "structural_count", None)
            or instance_validation["structural_count"] <= 1
            or instance_validation.get("alternative_quartets")
            != getattr(quartet_validation, "valid_quartets", None)
            or instance_validation.get("structural_equivalence_classes")
            != getattr(quartet_validation, "structural_classes", None)
            or instance_validation.get("rejection_reasons")
            != getattr(quartet_validation, "rejection_reasons", None)
            or not isinstance(instance_validation.get("recorded_archive_sha256"), str)
            or not isinstance(instance_validation.get("eligible_feature_pool_id"), str)
            or not isinstance(instance_validation.get("validator_version"), str)
            or not isinstance(instance_validation.get("dataset_identity"), Mapping)
        ):
            return False
        if "instance_validation" in public_audit:
            return False

    if public_audit.get("phase") == "draft":
        known_ids = set(restricted.get("public_entity_to_source_id", {}).keys())
        if len(known_ids) != 16:
            return False
        return _valid_public_audit_shape(public_audit, snapshot.match_id, known_ids)

    engine_state_snapshot = restricted.get("engine_state_snapshot")
    if not isinstance(engine_state_snapshot, Mapping):
        return False
    try:
        engine_state_snapshot = dict(engine_state_snapshot)
    except Exception:
        return False
    if not _has_exact_engine_state_fields(engine_state_snapshot):
        return False

    if public_audit.get("starting_player") != engine_state_snapshot.get("starting_player"):
        return False

    entity_to_piece = restricted.get("entity_to_piece")
    piece_to_entity = restricted.get("piece_to_entity")
    feature_to_bit = restricted.get("feature_to_bit")
    private_feature_ownership = restricted.get("private_feature_ownership")
    if not isinstance(entity_to_piece, Mapping) or not isinstance(piece_to_entity, Mapping):
        return False
    if not isinstance(feature_to_bit, Mapping) or not isinstance(private_feature_ownership, Mapping):
        return False

    try:
        if any(not _is_opaque_entity_id(entity_id) for entity_id in entity_to_piece):
            return False
        if any(type(piece_id) is not int for piece_id in entity_to_piece.values()):
            return False
        if any(type(piece_id) is not int for piece_id in piece_to_entity):
            return False
        if any(not _is_opaque_entity_id(entity_id) for entity_id in piece_to_entity.values()):
            return False
        if set(entity_to_piece) != set(piece_to_entity.values()):
            return False
        if set(piece_to_entity) != set(range(16)):
            return False
        if len(entity_to_piece) != 16 or len(piece_to_entity) != 16:
            return False
        if set(entity_to_piece.values()) != set(range(16)):
            return False
        if {piece_id: entity_id for entity_id, piece_id in entity_to_piece.items()} != piece_to_entity:
            return False
        if {entity_id: piece_id for piece_id, entity_id in piece_to_entity.items()} != entity_to_piece:
            return False
    except Exception:
        return False

    if "public_entity_to_source_id" in restricted:
        public_entity_to_source_id = restricted["public_entity_to_source_id"]
        if not isinstance(public_entity_to_source_id, Mapping):
            return False
        try:
            source_ids = tuple(public_entity_to_source_id.values())
            if (
                set(public_entity_to_source_id) != set(entity_to_piece)
                or any(not isinstance(source_id, str) or not source_id for source_id in source_ids)
                or len(source_ids) != len(set(source_ids))
            ):
                return False
        except Exception:
            return False

    if not _valid_public_audit_shape(
        public_audit,
        snapshot.match_id,
        set(entity_to_piece),
    ):
        return False

    try:
        if len(feature_to_bit) != 4:
            return False
        if len(set(feature_to_bit)) != 4:
            return False
        if any(not isinstance(feature_id, str) or not feature_id for feature_id in feature_to_bit):
            return False
        if any(type(bit_index) is not int for bit_index in feature_to_bit.values()):
            return False
        if set(feature_to_bit.values()) != {0, 1, 2, 3}:
            return False
    except Exception:
        return False

    try:
        if set(private_feature_ownership) != {"player_1", "player_2"}:
            return False
        ownership = {}
        for owner in ("player_1", "player_2"):
            features = private_feature_ownership.get(owner)
            if not isinstance(features, (tuple, list, set, frozenset)):
                return False
            feature_set = set(features)
            if len(feature_set) != 2 or len(feature_set) != len(features):
                return False
            if not feature_set.issubset(set(feature_to_bit)):
                return False
            ownership[owner] = feature_set
    except Exception:
        return False

    if set(ownership) != {"player_1", "player_2"}:
        return False
    if ownership["player_1"] & ownership["player_2"]:
        return False
    if ownership["player_1"] | ownership["player_2"] != set(feature_to_bit):
        return False

    try:
        public_board = tuple(public_audit["board"])
        internal_board = tuple(engine_state_snapshot["board"])
    except Exception:
        return False
    if len(public_board) != 16 or len(internal_board) != 16:
        return False
    translated = tuple(
        None if piece_id is None else piece_to_entity.get(piece_id) for piece_id in internal_board
    )
    if public_board != translated:
        return False

    try:
        replayed_state = replay_game(restricted["engine_replay"])
        expected_public_history = []
        for action in replayed_state.history:
            if action.kind == "select_piece":
                entity_id = piece_to_entity.get(action.piece_id)
                if not isinstance(entity_id, str):
                    return False
                expected_public_history.append({
                    "kind": "select_entity",
                    "player": action.player,
                    "entity_id": entity_id,
                })
            else:
                expected_public_history.append({
                    "kind": "place_entity",
                    "player": action.player,
                    "cell": action.cell,
                })
        actual_public_history = tuple(
            dict(action) for action in public_audit["public_history"]
        )
    except (KeyError, TypeError, ValueError):
        return False
    if actual_public_history != tuple(expected_public_history):
        return False

    required_state_fields = (("mode", "mode"), ("phase", "phase"), ("current_player", "active_player"))
    for public_name, internal_name in required_state_fields:
        if public_audit.get(public_name) != engine_state_snapshot.get(internal_name):
            return False
    selected_piece = engine_state_snapshot.get("selected_piece")
    expected_selected_entity = (
        None if selected_piece is None else piece_to_entity.get(selected_piece)
    )
    if public_audit.get("selected_entity") != expected_selected_entity:
        return False

    legal = legal_actions(replayed_state)
    public_legal = public_audit["legal_actions"]
    if legal["type"] == "select_piece":
        expected_legal = tuple(
            piece_to_entity[piece_id] for piece_id in legal["piece_ids"]
        )
        if set(public_legal["entity_ids"]) != set(expected_legal):
            return False
    elif legal["type"] == "place_piece":
        if tuple(public_legal["cells"]) != tuple(legal["cells"]):
            return False
    elif public_legal["kind"] != "terminal":
        return False

    engine_result = engine_state_snapshot.get("result")
    public_result = public_audit.get("result")
    if engine_result is None:
        if public_result is not None:
            return False
    else:
        if not isinstance(engine_result, Mapping):
            return False
        try:
            normalized = {
                "mode": engine_result["mode"],
                "outcome": engine_result["outcome"],
                "winner": engine_result["winner"],
                "reason": engine_result["reason"],
            }
        except Exception:
            return False
        if not isinstance(public_result, Mapping):
            return False
        if set(engine_result) != _ENGINE_RESULT_FIELDS:
            return False
        try:
            if public_result != normalized:
                return False
        except Exception:
            return False

    return True


class SyntheticAdapter:
    """Minimal non-domain adapter used to validate Phase 0 contracts."""

    def __init__(self, domain_name: str = "synthetic_16bit") -> None:
        features = (
            FeatureDefinition("f0", "feature_0", "binary feature 0"),
            FeatureDefinition("f1", "feature_1", "binary feature 1"),
            FeatureDefinition("f2", "feature_2", "binary feature 2"),
            FeatureDefinition("f3", "feature_3", "binary feature 3"),
        )
        entity_values: dict[str, MappingProxyType[str, bool]] = {}
        entities: list[PublicEntity] = []
        for index in range(16):
            entity_id = f"e{index:02d}"
            entities.append(PublicEntity(entity_id=entity_id, label=f"entity_{index:02d}"))
            values: dict[str, bool] = {}
            for bit_index, feature in enumerate(features):
                values[feature.feature_id] = bool((index >> bit_index) & 1)
            entity_values[entity_id] = MappingProxyType(values)
        self.domain = DomainCatalog(
            name=domain_name,
            version="synthetic-v1",
            entities=tuple(entities),
            features=features,
            values=MappingProxyType(entity_values),
            gameplay_feature_ids=tuple(f.feature_id for f in features),
        )

    def load_domain(self) -> DomainCatalog:
        return self.domain

    def build_instance(self, instance_id: str = "synthetic_instance_0") -> InstanceSpec:
        entity_ids = tuple(entity.entity_id for entity in self.domain.entities)
        feature_ids = tuple(feature.feature_id for feature in self.domain.features)
        signature_map = {
            entity_id: int(entity_id[1:]) for entity_id in entity_ids
        }
        return InstanceSpec(
            instance_id=instance_id,
            domain_name=self.domain.name,
            feature_ids=feature_ids,
            entity_ids=entity_ids,
            signature_map=MappingProxyType(signature_map),
            public_seed=0,
        )


class MatchSession:
    """Controller boundary enforcing the trusted host/player model and two-phase draft+play."""

    def __init__(
        self,
        domain: DomainCatalog,
        instance: InstanceSpec,
        mode: Mode = "classic",
        starting_player: Player = "player_1",
        instance_validation: Mapping[str, Any] | None = None,
        require_instance_validation: bool = False,
        restricted_source_ids: Mapping[str, str] | None = None,
        enable_draft: bool = False,
        draft_permutation_seed: int | None = None,
        max_draft_proposals: int | None = None,
    ) -> None:
        self._validate_domain(domain)
        self._validate_instance(domain, instance)
        if starting_player not in ("player_1", "player_2"):
            raise ValueError("starting_player must be 'player_1' or 'player_2'.")
        if restricted_source_ids is not None:
            if not isinstance(restricted_source_ids, Mapping):
                raise TypeError("restricted_source_ids must be a mapping.")
            if set(restricted_source_ids) != set(instance.entity_ids):
                raise ValueError(
                    "Restricted source IDs must map every instance entity exactly once."
                )
            source_ids = tuple(restricted_source_ids.values())
            if (
                any(not isinstance(source_id, str) or not source_id for source_id in source_ids)
                or len(set(source_ids)) != len(source_ids)
            ):
                raise ValueError("Restricted source IDs must be unique non-empty strings.")
        if require_instance_validation:
            validation = (
                None
                if instance_validation is None
                else instance_validation.get("quartet_validation")
            )
            if (
                instance_validation is None
                or instance_validation.get("instance_id") != instance.instance_id
                or getattr(validation, "accepted", False) is not True
                or type(getattr(validation, "id_level_count", None)) is not int
                or validation.id_level_count <= 1
                or type(getattr(validation, "structural_count", None)) is not int
                or validation.structural_count <= 1
            ):
                raise ValueError(
                    "MatchSession requires an accepted per-instance Quartet validation record."
                )

        self.domain = domain
        self.instance = instance
        self.instance_validation = (
            None if instance_validation is None else _freeze_value(instance_validation)
        )
        self._restricted_source_ids = (
            None
            if restricted_source_ids is None
            else dict(restricted_source_ids)
        )
        self.mode = mode
        self.starting_player: Player = starting_player
        self.enable_draft = bool(enable_draft)
        self._draft_rng = (
            Random(draft_permutation_seed)
            if draft_permutation_seed is not None
            else secrets.SystemRandom()
        )

        # Eligible feature pool exposed publicly in the 16 x N feature matrix
        feature_def_by_id = {f.feature_id: f for f in domain.features}
        raw_eligible = (
            tuple(domain.gameplay_feature_ids)
            if domain.gameplay_feature_ids is not None
            else tuple(f.feature_id for f in domain.features)
        )
        self._eligible_feature_ids: tuple[str, ...] = tuple(dict.fromkeys(raw_eligible))
        if len(self._eligible_feature_ids) < 4:
            raise ValueError("At least four eligible features are required.")
        self._eligible_feature_set = set(self._eligible_feature_ids)
        self._eligible_feature_definitions: tuple[dict[str, str], ...] = tuple(
            {
                "feature_id": feature_def_by_id[fid].feature_id,
                "name": feature_def_by_id[fid].name,
                "definition": feature_def_by_id[fid].definition,
                "value_semantics": feature_def_by_id[fid].value_semantics,
            }
            for fid in self._eligible_feature_ids
        )

        # Verify all 16 instance entities have boolean values across all eligible features
        for source_id in instance.entity_ids:
            fvals = domain.values[source_id]
            for fid in self._eligible_feature_ids:
                if fid not in fvals or type(fvals[fid]) is not bool:
                    raise ValueError(f"Missing or non-boolean value for {source_id}:{fid}.")

        self._valid_quartets: tuple[tuple[str, str, str, str], ...] = self._compute_valid_quartets(
            instance.entity_ids,
            self._eligible_feature_ids,
            domain.values,
        )
        self._valid_quartet_sets: tuple[frozenset[str], ...] = tuple(
            frozenset(q) for q in self._valid_quartets
        )
        if not self._valid_quartet_sets:
            raise ValueError("Selected 16 entities have no valid 4-feature quartet in eligible pool.")

        # Opaque per-match public entity IDs (UUIDv4)
        self._source_to_public_entity_id = self._generate_public_entity_ids(
            instance.entity_ids
        )
        self._public_to_source_entity_id = {
            pub_id: src_id for src_id, pub_id in self._source_to_public_entity_id.items()
        }
        self._public_entity_order = tuple(sorted(self._public_to_source_entity_id))
        self._public_entity_features: dict[str, dict[str, bool]] = {
            pub_id: {
                fid: bool(domain.values[self._public_to_source_entity_id[pub_id]][fid])
                for fid in self._eligible_feature_ids
            }
            for pub_id in self._public_entity_order
        }

        self.max_draft_proposals = (
            max_draft_proposals
            if max_draft_proposals is not None
            else len(self._eligible_feature_ids) * 2
        )
        self._draft_owned: dict[Player, list[str]] = {"player_1": [], "player_2": []}
        self._draft_rejected_by_player: dict[Player, list[str]] = {"player_1": [], "player_2": []}
        self._draft_history: list[dict[str, Any]] = []
        self._draft_current_player: Player = starting_player
        self._draft_complete: bool = False
        self._secret_bit_permutation: tuple[int, int, int, int] = (0, 1, 2, 3)

        self.selected_entity_id: str | None = None
        self.public_history: list[dict[str, Any]] = []
        self._public_feedback: dict[Player, str | None] = {"player_1": None, "player_2": None}
        self.match_id = f"match:{uuid4()}"

        if self.enable_draft:
            self.engine_state = new_game(mode, starting_player=starting_player)
            self.entity_to_piece: dict[str, int] = {}
            self.piece_to_entity: dict[int, str] = {}
            self.private_feature_ownership: dict[Player, tuple[str, ...]] = {
                "player_1": (),
                "player_2": (),
            }
            self.secret_bit_mapping: dict[str, int] = {}
        else:
            self._draft_complete = True
            self.engine_state = new_game(mode, starting_player=starting_player)
            self.entity_to_piece = self._build_entity_to_piece(
                instance,
                self._source_to_public_entity_id,
            )
            self.piece_to_entity = {
                piece_id: entity_id for entity_id, piece_id in self.entity_to_piece.items()
            }
            self.private_feature_ownership = {
                "player_1": tuple(instance.feature_ids[:2]),
                "player_2": tuple(instance.feature_ids[2:4]),
            }
            self.secret_bit_mapping = {
                feature_id: index for index, feature_id in enumerate(instance.feature_ids)
            }

    @staticmethod
    def _compute_valid_quartets(
        entity_ids: tuple[str, ...],
        eligible_feature_ids: tuple[str, ...],
        values: Mapping[str, Mapping[str, bool]],
    ) -> tuple[tuple[str, str, str, str], ...]:
        masks: dict[str, int] = {}
        for fid in eligible_feature_ids:
            mask = 0
            for idx, eid in enumerate(entity_ids):
                if values[eid][fid]:
                    mask |= 1 << idx
            masks[fid] = mask

        valid: list[tuple[str, str, str, str]] = []
        for quartet in combinations(eligible_feature_ids, 4):
            m0, m1, m2, m3 = (
                masks[quartet[0]],
                masks[quartet[1]],
                masks[quartet[2]],
                masks[quartet[3]],
            )
            seen = 0
            ok = True
            for idx in range(16):
                sig = (
                    ((m0 >> idx) & 1)
                    | (((m1 >> idx) & 1) << 1)
                    | (((m2 >> idx) & 1) << 2)
                    | (((m3 >> idx) & 1) << 3)
                )
                bit = 1 << sig
                if seen & bit:
                    ok = False
                    break
                seen |= bit
            if ok and seen == 0xFFFF:
                valid.append((quartet[0], quartet[1], quartet[2], quartet[3]))
        return tuple(valid)

    @staticmethod
    def _validate_domain(domain: DomainCatalog) -> None:
        if not domain.entities or not domain.features:
            raise ValueError("Domain catalog must contain entities and features.")
        entity_ids = [entity.entity_id for entity in domain.entities]
        if len(entity_ids) != len(set(entity_ids)):
            raise ValueError("Entity IDs must be unique.")
        feature_ids = [feature.feature_id for feature in domain.features]
        if len(feature_ids) != len(set(feature_ids)):
            raise ValueError("Feature IDs must be unique.")

    @staticmethod
    def _validate_instance(domain: DomainCatalog, instance: InstanceSpec) -> None:
        if instance.domain_name != domain.name:
            raise ValueError("Instance domain name must match the domain catalog.")
        entity_ids = [entity.entity_id for entity in domain.entities]
        feature_ids = [feature.feature_id for feature in domain.features]
        if len(instance.entity_ids) != 16:
            raise ValueError("A valid Quarto instance requires exactly 16 entities.")
        if len(instance.feature_ids) != 4:
            raise ValueError("A valid Quarto instance requires exactly four feature IDs.")
        if len(set(instance.entity_ids)) != 16:
            raise ValueError("Instance entity IDs must be unique.")
        if len(set(instance.feature_ids)) != 4:
            raise ValueError("Instance feature IDs must be unique.")
        if set(instance.entity_ids) - set(entity_ids):
            raise ValueError("Instance entity IDs must exist in the domain catalog.")
        if set(instance.feature_ids) - set(feature_ids):
            raise ValueError("Instance feature IDs must exist in the domain catalog.")
        if not isinstance(domain.values, Mapping):
            raise ValueError("Domain values must be a mapping from entity IDs to feature-value mappings.")
        if set(instance.signature_map) != set(instance.entity_ids):
            raise ValueError("Signature map keys must match the instance entity IDs.")

        signature_values = set(instance.signature_map.values())
        if len(signature_values) != 16 or set(range(16)) != signature_values:
            raise ValueError("Instance signatures must cover each value 0..15 exactly once.")

        for entity_id in instance.entity_ids:
            if entity_id not in domain.values:
                raise ValueError(f"Missing entity value record for {entity_id}.")
            feature_values = domain.values[entity_id]
            if not isinstance(feature_values, Mapping):
                raise ValueError(f"Entity values for {entity_id} must be a mapping of feature IDs to booleans.")
            for feature_id in instance.feature_ids:
                if feature_id not in feature_values:
                    raise ValueError(f"Missing feature value for {entity_id}:{feature_id}.")
                value = feature_values[feature_id]
                if type(value) is not bool:
                    raise ValueError(f"Feature value for {entity_id}:{feature_id} must be a bool.")

            expected_signature = 0
            for bit_index, feature_id in enumerate(instance.feature_ids):
                if feature_values[feature_id]:
                    expected_signature |= 1 << bit_index
            if instance.signature_map[entity_id] != expected_signature:
                raise ValueError(
                    f"Signature for {entity_id} does not match the feature values in instance.feature_ids order."
                )

        for entity_id, signature in instance.signature_map.items():
            if type(signature) is not int or not (0 <= signature <= 15):
                raise ValueError(f"Signature for {entity_id} must be a valid integer in 0..15.")

    @staticmethod
    def _generate_public_entity_ids(entity_ids: tuple[str, ...]) -> dict[str, str]:
        generated: dict[str, str] = {}
        used: set[str] = set()
        for entity_id in entity_ids:
            public_id = uuid4().hex
            while public_id in used:
                public_id = uuid4().hex
            generated[entity_id] = public_id
            used.add(public_id)
        return generated

    @staticmethod
    def _build_entity_to_piece(
        instance: InstanceSpec,
        public_ids_by_source: Mapping[str, str],
    ) -> dict[str, int]:
        entity_to_piece = {}
        for entity_id, signature in instance.signature_map.items():
            entity_to_piece[public_ids_by_source[entity_id]] = int(signature)
        return entity_to_piece

    def _public_entity_ids_for_pieces(self, piece_ids: Iterable[int]) -> list[str]:
        available = {self.piece_to_entity[piece_id] for piece_id in piece_ids}
        return [
            entity_id
            for entity_id in self._public_entity_order
            if entity_id in available
        ]

    @property
    def current_player(self) -> Player:
        if not self._draft_complete:
            return self._draft_current_player
        return self.engine_state.active_player

    def _user_is_current_player(self, requester: str) -> bool:
        return requester == self.current_player

    def _can_accept_draft_feature(self, proposer: Player, feature_id: str) -> bool:
        if feature_id not in self._eligible_feature_set:
            return False
        if len(self._draft_owned[proposer]) >= 2:
            return False
        already_owned = set(self._draft_owned["player_1"]) | set(self._draft_owned["player_2"])
        if feature_id in already_owned:
            return False
        tentative = already_owned | {feature_id}
        return any(tentative.issubset(qset) for qset in self._valid_quartet_sets)

    def _finalize_draft(self) -> None:
        p1_feats = tuple(self._draft_owned["player_1"])
        p2_feats = tuple(self._draft_owned["player_2"])
        if len(p1_feats) != 2 or len(p2_feats) != 2:
            raise RuntimeError("Cannot finalize draft before both players own two features.")
        accepted_four = p1_feats + p2_feats
        if len(set(accepted_four)) != 4 or frozenset(accepted_four) not in self._valid_quartet_sets:
            raise RuntimeError("Finalized draft features do not form a valid quartet.")

        sampled = self._draft_rng.sample(range(4), 4)
        permutation = (sampled[0], sampled[1], sampled[2], sampled[3])
        self._secret_bit_permutation = permutation
        self.secret_bit_mapping = dict(zip(accepted_four, permutation))
        self.private_feature_ownership = {
            "player_1": p1_feats,
            "player_2": p2_feats,
        }

        entity_to_piece: dict[str, int] = {}
        for pub_id in self._public_entity_order:
            src_id = self._public_to_source_entity_id[pub_id]
            fvals = self.domain.values[src_id]
            piece_id = 0
            for fid, bit_idx in self.secret_bit_mapping.items():
                if fvals[fid]:
                    piece_id |= 1 << bit_idx
            entity_to_piece[pub_id] = piece_id

        if set(entity_to_piece.values()) != set(range(16)):
            raise RuntimeError("Finalized draft mapping failed 0..15 bijection check.")

        self.entity_to_piece = entity_to_piece
        self.piece_to_entity = {
            piece_id: entity_id for entity_id, piece_id in entity_to_piece.items()
        }
        self.engine_state = new_game(self.mode, starting_player=self.starting_player)
        self._draft_complete = True

    def _build_public_entities_payload(self) -> list[dict[str, Any]]:
        return [
            {
                "entity_id": entity_id,
                "label": entity_id,
                "features": copy.deepcopy(self._public_entity_features[entity_id]),
            }
            for entity_id in self._public_entity_order
        ]

    def public_observation(self, player: str) -> dict[str, Any]:
        if player not in ("player_1", "player_2"):
            raise ValueError("Unknown observation recipient.")

        if not self._draft_complete:
            observation = {
                "mode": self.mode,
                "phase": "draft",
                "current_player": self._draft_current_player,
                "public_entities": self._build_public_entities_payload(),
                "feature_definitions": copy.deepcopy(list(self._eligible_feature_definitions)),
                "board": [None] * 16,
                "available_entities": list(self._public_entity_order),
                "selected_entity": None,
                "legal_actions": {
                    "kind": PUBLIC_ACTION_KIND_PROPOSE,
                    "feature_ids": list(self._eligible_feature_ids),
                },
                "history": [],
                "terminal": False,
            }
            return copy.deepcopy(observation)

        legal = legal_actions(self.engine_state)
        if legal["type"] == "select_piece":
            public_actions = {
                "kind": PUBLIC_ACTION_KIND_SELECT,
                "entity_ids": self._public_entity_ids_for_pieces(legal["piece_ids"]),
            }
        elif legal["type"] == "place_piece":
            public_actions = {
                "kind": PUBLIC_ACTION_KIND_PLACE,
                "cells": list(legal["cells"]),
            }
        else:
            public_actions = {"kind": "terminal"}

        observation = {
            "mode": self.engine_state.mode,
            "phase": self.engine_state.phase,
            "current_player": self.engine_state.active_player,
            "public_entities": self._build_public_entities_payload(),
            "feature_definitions": copy.deepcopy(list(self._eligible_feature_definitions)),
            "board": [
                None if piece_id is None else self.piece_to_entity[piece_id]
                for piece_id in self.engine_state.board
            ],
            "available_entities": self._public_entity_ids_for_pieces(
                self.engine_state.remaining_pieces
            ),
            "selected_entity": self.selected_entity_id,
            "legal_actions": public_actions,
            "history": copy.deepcopy(self.public_history),
            "terminal": self.engine_state.is_terminal,
        }
        return copy.deepcopy(observation)

    def private_observation(self, requester: str) -> dict[str, Any]:
        """Return private state only when the requester is the active player."""
        if requester not in ("player_1", "player_2"):
            raise ValueError("Unknown private-observation recipient.")
        if requester != self.current_player:
            raise ValueError("Private observation requester is not the active player.")
        observation = self.public_observation(requester)
        observation["requester"] = requester
        owned = (
            list(self._draft_owned[requester])
            if not self._draft_complete
            else list(self.private_feature_ownership[requester])
        )
        observation["private"] = {
            "owned_features": owned,
            "proposal_feedback": self._public_feedback[requester],
            "rejected_features": list(self._draft_rejected_by_player[requester]),
        }
        return copy.deepcopy(observation)

    def handle_action(self, requester: str, action: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(action, dict):
            raise ValueError("Action must be a dictionary.")
        if requester not in ("player_1", "player_2"):
            raise ValueError("Unknown authenticated action requester.")
        if "player" in action:
            raise ValueError("Agent actions must not include a player identity.")
        if not self._user_is_current_player(requester):
            raise ValueError("The authenticated requester is not the active player.")

        kind = action.get("kind")

        if not self._draft_complete:
            if kind != PUBLIC_ACTION_KIND_PROPOSE:
                raise ValueError("Only propose_feature actions are valid during the draft phase.")
            feature_id = action.get("feature_id")
            if not isinstance(feature_id, str) or feature_id not in self._eligible_feature_set:
                raise ValueError("propose_feature requires a valid eligible feature_id.")
            if len(self._draft_history) >= self.max_draft_proposals:
                raise ValueError("Maximum draft proposal attempts exceeded.")

            accepted = self._can_accept_draft_feature(requester, feature_id)
            self._draft_history.append({
                "player": requester,
                "feature_id": feature_id,
                "accepted": accepted,
            })
            if accepted:
                self._draft_owned[requester].append(feature_id)
                self._public_feedback[requester] = "accepted"
                if (
                    len(self._draft_owned["player_1"]) == 2
                    and len(self._draft_owned["player_2"]) == 2
                ):
                    self._finalize_draft()
                else:
                    other: Player = "player_2" if requester == "player_1" else "player_1"
                    if len(self._draft_owned[other]) < 2:
                        self._draft_current_player = other
                    else:
                        self._draft_current_player = requester
            else:
                self._public_feedback[requester] = "rejected"
                if feature_id not in self._draft_rejected_by_player[requester]:
                    self._draft_rejected_by_player[requester].append(feature_id)
                if len(self._draft_history) >= self.max_draft_proposals:
                    raise ValueError("Maximum draft proposal attempts exceeded.")

            return self.public_observation(requester)

        if kind == PUBLIC_ACTION_KIND_SELECT:
            entity_id = action.get("entity_id")
            if not isinstance(entity_id, str):
                raise ValueError("select_entity requires a valid string entity_id.")
            if entity_id not in self.entity_to_piece:
                raise ValueError("Unknown public entity id.")
            if self.engine_state.phase != "select":
                raise ValueError("A selection action is only valid in the select phase.")
            piece_id = self.entity_to_piece[entity_id]
            if piece_id not in self.engine_state.remaining_pieces:
                raise ValueError("The selected entity is unavailable.")
            self.engine_state = select_piece(self.engine_state, requester, piece_id)
            self.selected_entity_id = entity_id
            self.public_history.append({
                "kind": PUBLIC_ACTION_KIND_SELECT,
                "player": requester,
                "entity_id": entity_id,
            })
            return self.public_observation(requester)

        if kind == PUBLIC_ACTION_KIND_PLACE:
            if self.engine_state.phase != "place":
                raise ValueError("A placement action is only valid in the place phase.")
            if self.selected_entity_id is None:
                raise ValueError("No entity is selected for placement.")
            cell = action.get("cell")
            if type(cell) is not int:
                raise ValueError("place_entity requires an integer cell.")
            if self.engine_state.active_player != requester:
                raise ValueError("The authenticated requester is not the active player.")
            self.engine_state = place_piece(self.engine_state, requester, cell)
            self.public_history.append({
                "kind": PUBLIC_ACTION_KIND_PLACE,
                "player": requester,
                "cell": cell,
            })
            self.selected_entity_id = None
            return self.public_observation(requester)

        raise ValueError("Unknown external action kind.")

    def get_read_only_audit_view(self) -> AuditSnapshot:
        public_history = tuple(_freeze_value(entry) for entry in self.public_history)
        if not self._draft_complete:
            public_audit = _freeze_value({
                "match_id": self.match_id,
                "mode": self.mode,
                "starting_player": self.starting_player,
                "phase": "draft",
                "current_player": self._draft_current_player,
                "selected_entity": None,
                "board": (None,) * 16,
                "draft_history": tuple(
                {
                    "kind": "propose_attribute",
                    "player": entry["player"],
                    "attribute_id": entry["feature_id"],
                    "accepted": bool(entry["accepted"]),
                }
                for entry in self._draft_history
            ),
                "public_history": (),
                "result": None,
                "legal_actions": {
                    "kind": PUBLIC_ACTION_KIND_PROPOSE,
                    "feature_ids": tuple(self._eligible_feature_ids),
                },
            })
            restricted = _freeze_value({
                "entity_to_piece": {},
                "piece_to_entity": {},
                "feature_to_bit": {},
                "private_feature_ownership": {
                    "player_1": tuple(self._draft_owned["player_1"]),
                    "player_2": tuple(self._draft_owned["player_2"]),
                },
                "draft_history": tuple(self._draft_history),
                "engine_replay": "",
                "engine_state_snapshot": {},
                "public_entity_to_source_id": (
                    {
                        self._source_to_public_entity_id[entity_id]: source_id
                        for entity_id, source_id in self._restricted_source_ids.items()
                    }
                    if self._restricted_source_ids is not None
                    else dict(self._public_to_source_entity_id)
                ),
                **(
                    {
                        "instance_validation": {
                            **dict(self.instance_validation),
                            "match_id": self.match_id,
                        }
                    }
                    if self.instance_validation is not None
                    else {}
                ),
            })
            return AuditSnapshot(
                match_id=self.match_id,
                public_audit=public_audit,
                restricted_evaluator_data=restricted,
            )

        result = (
            None
            if self.engine_state.result is None
            else _freeze_value({
                "mode": self.engine_state.result.mode,
                "outcome": self.engine_state.result.outcome,
                "winner": self.engine_state.result.winner,
                "reason": self.engine_state.result.reason,
            })
        )
        public_actions = _freeze_value(self._public_action_metadata())
        public_audit = _freeze_value({
            "match_id": self.match_id,
            "mode": self.engine_state.mode,
            "starting_player": self.engine_state.starting_player,
            "phase": self.engine_state.phase,
            "current_player": self.engine_state.active_player,
            "selected_entity": self.selected_entity_id,
            "board": tuple(
                None if piece_id is None else self.piece_to_entity[piece_id]
                for piece_id in self.engine_state.board
            ),
            "draft_history": tuple(
                {
                    "kind": "propose_attribute",
                    "player": entry["player"],
                    "attribute_id": entry["feature_id"],
                    "accepted": bool(entry["accepted"]),
                }
                for entry in self._draft_history
            ),
            "public_history": public_history,
            "result": result,
            "legal_actions": public_actions,
        })
        restricted = _freeze_value({
            "entity_to_piece": dict(self.entity_to_piece),
            "piece_to_entity": dict(self.piece_to_entity),
            "feature_to_bit": dict(self.secret_bit_mapping),
            "private_feature_ownership": dict(self.private_feature_ownership),
            "engine_replay": serialize_replay(self.engine_state),
            "engine_state_snapshot": {
                "mode": self.engine_state.mode,
                "starting_player": self.engine_state.starting_player,
                "phase": self.engine_state.phase,
                "active_player": self.engine_state.active_player,
                "board": tuple(self.engine_state.board),
                "selected_piece": self.engine_state.selected_piece,
                "selected_by": self.engine_state.selected_by,
                "remaining_pieces": tuple(self.engine_state.remaining_pieces),
                "is_terminal": self.engine_state.is_terminal,
                "result": None if self.engine_state.result is None else {
                    "mode": self.engine_state.result.mode,
                    "outcome": self.engine_state.result.outcome,
                    "winner": self.engine_state.result.winner,
                    "reason": self.engine_state.result.reason,
                },
                "history": tuple({
                    "kind": action.kind,
                    "player": action.player,
                    "piece_id": action.piece_id,
                    "cell": action.cell,
                } for action in self.engine_state.history),
            },
            **(
                {
                    "draft_history": tuple(self._draft_history),
                    "secret_bit_permutation": self._secret_bit_permutation,
                }
                if self.enable_draft
                else {}
            ),
            **(
                {
                    "instance_validation": {
                        **dict(self.instance_validation),
                        "match_id": self.match_id,
                    }
                }
                if self.instance_validation is not None
                else {}
            ),
            **(
                {
                    "public_entity_to_source_id": {
                        self._source_to_public_entity_id[entity_id]: source_id
                        for entity_id, source_id in self._restricted_source_ids.items()
                    }
                }
                if self._restricted_source_ids is not None
                else {}
            ),
        })
        return AuditSnapshot(
            match_id=self.match_id,
            public_audit=public_audit,
            restricted_evaluator_data=restricted,
        )

    def _public_action_metadata(self) -> dict[str, Any]:
        if not self._draft_complete:
            return {
                "kind": PUBLIC_ACTION_KIND_PROPOSE,
                "feature_ids": list(self._eligible_feature_ids),
            }
        legal = legal_actions(self.engine_state)
        if legal["type"] == "select_piece":
            return {
                "kind": PUBLIC_ACTION_KIND_SELECT,
                "entity_ids": self._public_entity_ids_for_pieces(legal["piece_ids"]),
            }
        if legal["type"] == "place_piece":
            return {
                "kind": PUBLIC_ACTION_KIND_PLACE,
                "cells": list(legal["cells"]),
            }
        return {"kind": "terminal"}


class Phase0Controller:
    """Small controller boundary for the Quarto Hidden-Information benchmark.

    The trusted host must supply the requester identity. Agent code must not receive
    direct access to MatchSession or Phase0Controller internals.
    """

    def __init__(
        self,
        adapter: DomainAdapter,
        mode: Mode = "classic",
        instance: InstanceSpec | None = None,
        starting_player: Player = "player_1",
        restricted_source_ids: Mapping[str, str] | None = None,
        enable_draft: bool = False,
        draft_permutation_seed: int | None = None,
        max_draft_proposals: int | None = None,
    ) -> None:
        self.adapter = adapter
        self.domain = adapter.load_domain()
        if instance is not None and not isinstance(instance, InstanceSpec):
            raise TypeError("instance must be an InstanceSpec.")
        self.instance = adapter.build_instance() if instance is None else instance
        requires_validation = getattr(
            adapter, "requires_instance_validation", False
        )
        if requires_validation:
            if not isinstance(adapter, InstanceValidationCapability):
                raise TypeError(
                    "This domain requires an adapter with instance validation capability."
                )
            validation_record = adapter.validate_instance(self.domain, self.instance)
            if not isinstance(validation_record, Mapping):
                raise TypeError("Adapter instance validation must return a mapping.")
            if validation_record.get("instance_id") != self.instance.instance_id:
                raise ValueError("Instance validation record does not match the selected instance.")
            quartet_validation = validation_record.get("quartet_validation")
            if (
                getattr(quartet_validation, "accepted", False) is not True
                or type(getattr(quartet_validation, "id_level_count", None)) is not int
                or quartet_validation.id_level_count <= 1
                or type(getattr(quartet_validation, "structural_count", None)) is not int
                or quartet_validation.structural_count <= 1
            ):
                raise InstanceValidationError(validation_record)
        else:
            validation_record = None
        self.session = MatchSession(
            self.domain,
            self.instance,
            mode=mode,
            starting_player=starting_player,
            instance_validation=validation_record,
            require_instance_validation=requires_validation,
            restricted_source_ids=restricted_source_ids,
            enable_draft=enable_draft,
            draft_permutation_seed=draft_permutation_seed,
            max_draft_proposals=max_draft_proposals,
        )

    def public_observation(self, player: str) -> dict[str, Any]:
        return self.session.public_observation(player)

    def private_observation(self, requester: str) -> dict[str, Any]:
        """Return the active player's private observation."""
        if requester not in ("player_1", "player_2"):
            raise ValueError("Unknown authenticated requester.")
        if requester != self.session.current_player:
            raise ValueError("Private observation requester is not the active player.")
        return self.session.private_observation(requester)

    def submit_agent_action(self, requester: str, action: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(action, dict):
            raise ValueError("Action must be a dictionary.")
        if requester not in ("player_1", "player_2"):
            raise ValueError("Unknown authenticated action requester.")
        return self.session.handle_action(requester, action)

    def get_read_only_audit_view(self) -> AuditSnapshot:
        return self.session.get_read_only_audit_view()


__all__ = [
    "AuditSnapshot",
    "DomainCatalog",
    "FeatureDefinition",
    "InstanceSpec",
    "MatchSession",
    "Phase0Controller",
    "PublicEntity",
    "SyntheticAdapter",
    "project_agent_observations",
    "project_public_observation",
    "validate_audit_snapshot",
    "validate_public_observation",
]