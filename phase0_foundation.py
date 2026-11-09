from __future__ import annotations

import copy
from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, Protocol, runtime_checkable
from uuid import uuid4

from quarto_engine import (
    GameState,
    Mode,
    Player,
    legal_actions,
    new_game,
    place_piece,
    serialize_replay,
    select_piece,
    replay_game,
)


PUBLIC_ACTION_KIND_SELECT = "select_entity"
PUBLIC_ACTION_KIND_PLACE = "place_entity"


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
            "QM9 instance failed per-instance Quartet validation"
            + (f": {reason_text}" if reason_text else ".")
        )


@dataclass(frozen=True, slots=True)
class AuditSnapshot:
    match_id: str
    public_audit: MappingProxyType[str, Any]
    restricted_evaluator_data: MappingProxyType[str, Any]

    def validate_replay(self) -> bool:
        replay = self.restricted_evaluator_data.get("engine_replay")
        state_snapshot = self.restricted_evaluator_data.get("engine_state_snapshot")
        if not isinstance(replay, str) or not isinstance(state_snapshot, MappingProxyType):
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
        if state_snapshot.get("mode") != encoded_snapshot["mode"]:
            return False
        if state_snapshot.get("starting_player", "player_1") != encoded_snapshot["starting_player"]:
            return False
        if state_snapshot.get("phase") != encoded_snapshot["phase"]:
            return False
        if state_snapshot.get("active_player") != encoded_snapshot["active_player"]:
            return False
        if tuple(state_snapshot.get("board", ())) != encoded_snapshot["board"]:
            return False
        if tuple(state_snapshot.get("remaining_pieces", ())) != encoded_snapshot["remaining_pieces"]:
            return False
        if state_snapshot.get("selected_piece") != encoded_snapshot["selected_piece"]:
            return False
        if state_snapshot.get("selected_by") != encoded_snapshot["selected_by"]:
            return False
        if state_snapshot.get("is_terminal") != encoded_snapshot["is_terminal"]:
            return False

        expected_result = state_snapshot.get("result")
        if expected_result is None and encoded_snapshot["result"] is not None:
            return False
        if expected_result is not None and encoded_snapshot["result"] is None:
            return False
        if expected_result is not None and dict(expected_result) != encoded_snapshot["result"]:
            return False

        if tuple(state_snapshot.get("history", ())) != encoded_snapshot["history"]:
            return False
        return True


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
    instance_validation = restricted.get("instance_validation")
    if instance_validation is not None:
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

    engine_state_snapshot = restricted.get("engine_state_snapshot")
    if not isinstance(engine_state_snapshot, Mapping):
        return False
    try:
        engine_state_snapshot = dict(engine_state_snapshot)
    except Exception:
        return False

    required_engine_fields = ("mode", "phase", "active_player", "board", "result")
    required_public_fields = (
        "mode",
        "phase",
        "current_player",
        "board",
        "result",
        "public_history",
    )
    for field_name in required_engine_fields:
        if field_name not in engine_state_snapshot:
            return False
    for field_name in required_public_fields:
        if field_name not in public_audit:
            return False
    if public_audit.get("starting_player", "player_1") != engine_state_snapshot.get(
        "starting_player", "player_1"
    ):
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

    try:
        if len(feature_to_bit) != 4:
            return False
        if len(set(feature_to_bit)) != 4:
            return False
        if any(not isinstance(feature_id, str) or not feature_id for feature_id in feature_to_bit):
            return False
        if set(feature_to_bit.values()) != {0, 1, 2, 3}:
            return False
    except Exception:
        return False

    try:
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
        try:
            if public_result != normalized:
                return False
        except Exception:
            return False

    return True


class SyntheticAdapter:
    """Minimal non-QM9 adapter used to validate Phase 0 contracts."""

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
    """Controller boundary enforcing the trusted host/player model."""

    def __init__(
        self,
        domain: DomainCatalog,
        instance: InstanceSpec,
        mode: Mode = "classic",
        starting_player: Player = "player_1",
        instance_validation: Mapping[str, Any] | None = None,
        require_instance_validation: bool = False,
    ) -> None:
        self._validate_domain(domain)
        self._validate_instance(domain, instance)
        if domain.name == "qm9" or require_instance_validation:
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
                message = (
                    "QM9 MatchSession requires an accepted per-instance Quartet validation record."
                    if domain.name == "qm9"
                    else "MatchSession requires an accepted per-instance Quartet validation record."
                )
                raise ValueError(
                    message
                )
        self.domain = domain
        self.instance = instance
        self.instance_validation = (
            None if instance_validation is None else _freeze_value(instance_validation)
        )
        self.mode = mode
        self.engine_state = new_game(mode, starting_player=starting_player)
        self.entity_to_piece = self._build_entity_to_piece(instance)
        self.piece_to_entity = {piece_id: entity_id for entity_id, piece_id in self.entity_to_piece.items()}
        self.selected_entity_id: str | None = None
        self.private_feature_ownership = {
            "player_1": tuple(instance.feature_ids[:2]),
            "player_2": tuple(instance.feature_ids[2:4]),
        }
        self.secret_bit_mapping = {feature_id: index for index, feature_id in enumerate(instance.feature_ids)}
        self.public_history: list[dict[str, Any]] = []
        self._public_feedback: dict[str, str | None] = {"player_1": None, "player_2": None}
        self.match_id = f"match:{uuid4()}"

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
    def _build_entity_to_piece(instance: InstanceSpec) -> dict[str, int]:
        entity_to_piece = {}
        for entity_id, signature in instance.signature_map.items():
            entity_to_piece[entity_id] = int(signature)
        return entity_to_piece

    @property
    def current_player(self) -> Player:
        return self.engine_state.active_player

    def _user_is_current_player(self, requester: str) -> bool:
        return requester == self.engine_state.active_player

    def public_observation(self, player: str) -> dict[str, Any]:
        if player not in ("player_1", "player_2"):
            raise ValueError("Unknown observation recipient.")
        legal = legal_actions(self.engine_state)
        if legal["type"] == "select_piece":
            public_actions = {
                "kind": PUBLIC_ACTION_KIND_SELECT,
                "entity_ids": [self.piece_to_entity[piece_id] for piece_id in legal["piece_ids"]],
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
            "public_entities": [
                {"entity_id": entity.entity_id, "label": entity.label}
                for entity in self.domain.entities
            ],
            "board": [None if piece_id is None else self.piece_to_entity[piece_id] for piece_id in self.engine_state.board],
            "available_entities": [self.piece_to_entity[piece_id] for piece_id in self.engine_state.remaining_pieces],
            "selected_entity": self.selected_entity_id,
            "legal_actions": public_actions,
            "history": copy.deepcopy(self.public_history),
            "terminal": self.engine_state.is_terminal,
        }
        return copy.deepcopy(observation)

    def private_observation(self, requester: str) -> dict[str, Any]:
        if requester not in ("player_1", "player_2"):
            raise ValueError("Unknown private-observation recipient.")
        observation = self.public_observation(requester)
        observation["private"] = {
            "owned_features": list(self.private_feature_ownership[requester]),
            "proposal_feedback": self._public_feedback[requester],
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
            "board": tuple(None if piece_id is None else self.piece_to_entity[piece_id] for piece_id in self.engine_state.board),
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

    def _public_action_metadata(self) -> dict[str, Any]:
        legal = legal_actions(self.engine_state)
        if legal["type"] == "select_piece":
            return {
                "kind": PUBLIC_ACTION_KIND_SELECT,
                "entity_ids": [self.piece_to_entity[piece_id] for piece_id in legal["piece_ids"]],
            }
        if legal["type"] == "place_piece":
            return {
                "kind": PUBLIC_ACTION_KIND_PLACE,
                "cells": list(legal["cells"]),
            }
        return {"kind": "terminal"}


class Phase0Controller:
    """Small controller boundary for the Phase 0 proof-of-concept.

    The trusted host must supply the requester identity. Agent code must not receive
    direct access to MatchSession or Phase0Controller internals. This API validates
    the supplied requester string and current turn ownership only; it does not provide
    cryptographic or external host authentication.
    """

    def __init__(
        self,
        adapter: DomainAdapter,
        mode: Mode = "classic",
        instance: InstanceSpec | None = None,
        starting_player: Player = "player_1",
    ) -> None:
        self.adapter = adapter
        self.domain = adapter.load_domain()
        if instance is not None and not isinstance(instance, InstanceSpec):
            raise TypeError("instance must be an InstanceSpec.")
        self.instance = adapter.build_instance() if instance is None else instance
        requires_validation = self.domain.name == "qm9" or getattr(
            adapter, "requires_instance_validation", False
        )
        if requires_validation:
            if not isinstance(adapter, InstanceValidationCapability):
                message = (
                    "QM9 domains require an adapter with instance validation capability."
                    if self.domain.name == "qm9"
                    else "This domain requires an adapter with instance validation capability."
                )
                raise TypeError(
                    message
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
        )

    def public_observation(self, player: str) -> dict[str, Any]:
        return self.session.public_observation(player)

    def private_observation(self, requester: str) -> dict[str, Any]:
        if requester not in ("player_1", "player_2"):
            raise ValueError("Unknown authenticated requester.")
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
]
