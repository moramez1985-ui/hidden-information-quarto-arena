import json
import unittest
from dataclasses import replace
from types import MappingProxyType
from uuid import UUID

from phase0_foundation import (
    AuditSnapshot,
    DomainCatalog,
    MatchSession,
    Phase0Controller,
    SyntheticAdapter,
    validate_audit_snapshot,
)


def _to_plain(value):
    if isinstance(value, MappingProxyType):
        return {key: _to_plain(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_to_plain(item) for item in value]
    if isinstance(value, list):
        return [_to_plain(item) for item in value]
    if isinstance(value, dict):
        return {key: _to_plain(item) for key, item in value.items()}
    return value


class CountingSyntheticAdapter(SyntheticAdapter):
    def __init__(self):
        super().__init__()
        self.build_instance_calls = 0

    def build_instance(self, instance_id="synthetic_instance_0"):
        self.build_instance_calls += 1
        return super().build_instance(instance_id)


class Phase0FoundationTests(unittest.TestCase):
    def test_controller_builds_default_instance_when_instance_is_omitted(self):
        adapter = CountingSyntheticAdapter()

        controller = Phase0Controller(adapter)

        self.assertEqual(adapter.build_instance_calls, 1)
        self.assertEqual(controller.instance, SyntheticAdapter().build_instance())
        self.assertEqual(controller.session.instance, controller.instance)

    def test_controller_uses_supplied_instance_without_rebuilding(self):
        adapter = CountingSyntheticAdapter()
        instance = adapter.build_instance("provided_instance")
        build_calls_before_controller = adapter.build_instance_calls

        controller = Phase0Controller(adapter, instance=instance)

        self.assertEqual(adapter.build_instance_calls, build_calls_before_controller)
        self.assertIs(controller.instance, instance)
        self.assertIs(controller.session.instance, instance)

    def test_controller_rejects_incompatible_or_malformed_instances(self):
        adapter = SyntheticAdapter()
        instance = adapter.build_instance()
        malformed_instance = replace(instance, entity_ids=instance.entity_ids[:-1])
        incompatible_instance = replace(
            instance,
            feature_ids=("unknown_feature", *instance.feature_ids[1:]),
        )
        wrong_domain_instance = replace(instance, domain_name="another_domain")

        with self.assertRaises(ValueError):
            Phase0Controller(adapter, instance=malformed_instance)
        with self.assertRaises(ValueError):
            Phase0Controller(adapter, instance=incompatible_instance)
        with self.assertRaises(ValueError):
            Phase0Controller(adapter, instance=wrong_domain_instance)

    def test_controller_initializes_both_modes_with_supplied_instance(self):
        adapter = SyntheticAdapter()
        instance = adapter.build_instance()

        for mode in ("classic", "self_selection"):
            with self.subTest(mode=mode):
                controller = Phase0Controller(adapter, mode=mode, instance=instance)
                observation = controller.public_observation("player_1")

                self.assertIs(controller.instance, instance)
                self.assertEqual(observation["mode"], mode)
                self.assertEqual(observation["current_player"], "player_1")
                self.assertEqual(observation["phase"], "select")
                self.assertEqual(
                    controller.private_observation("player_1")["private"]["owned_features"],
                    list(instance.feature_ids[:2]),
                )

                selected_entity = observation["legal_actions"]["entity_ids"][0]
                selected = controller.submit_agent_action(
                    "player_1",
                    {"kind": "select_entity", "entity_id": selected_entity},
                )
                self.assertEqual(selected["phase"], "place")
                self.assertEqual(
                    selected["current_player"],
                    "player_2" if mode == "classic" else "player_1",
                )

    def test_controller_honors_player_two_start_without_changing_ownership(self):
        adapter = SyntheticAdapter()
        instance = adapter.build_instance()

        for mode in ("classic", "self_selection"):
            with self.subTest(mode=mode):
                controller = Phase0Controller(
                    adapter,
                    mode=mode,
                    instance=instance,
                    starting_player="player_2",
                )
                public1 = controller.public_observation("player_1")
                public2 = controller.public_observation("player_2")
                self.assertEqual(public1, public2)
                self.assertEqual(public1["current_player"], "player_2")
                self.assertEqual(
                    controller.private_observation("player_2")["private"]["owned_features"],
                    list(instance.feature_ids[2:4]),
                )

                entity_id = public2["legal_actions"]["entity_ids"][0]
                selected = controller.submit_agent_action(
                    "player_2",
                    {"kind": "select_entity", "entity_id": entity_id},
                )
                placer = "player_1" if mode == "classic" else "player_2"
                self.assertEqual(selected["current_player"], placer)
                placed = controller.submit_agent_action(
                    placer,
                    {"kind": "place_entity", "cell": 0},
                )
                self.assertEqual(placed["current_player"], "player_1")
                self.assertEqual(
                    controller.private_observation("player_1")["private"]["owned_features"],
                    list(instance.feature_ids[:2]),
                )

                snapshot = controller.get_read_only_audit_view()
                self.assertEqual(snapshot.public_audit["starting_player"], "player_2")
                self.assertEqual(
                    snapshot.restricted_evaluator_data["engine_state_snapshot"]["starting_player"],
                    "player_2",
                )
                self.assertTrue(validate_audit_snapshot(snapshot))

    def test_synthetic_adapter_generates_valid_16_entity_instance(self):
        adapter = SyntheticAdapter()
        instance = adapter.build_instance()
        self.assertEqual(len(instance.entity_ids), 16)
        self.assertEqual(len(instance.feature_ids), 4)
        self.assertEqual(set(instance.signature_map.values()), set(range(16)))
        self.assertEqual(len(set(instance.signature_map.values())), 16)

    def test_classic_mode_uses_explicit_requester_and_public_action_translation(self):
        controller = Phase0Controller(SyntheticAdapter(), mode="classic")
        obs = controller.public_observation("player_1")
        self.assertEqual(obs["phase"], "select")
        self.assertEqual(obs["current_player"], "player_1")
        self.assertEqual(obs["legal_actions"]["kind"], "select_entity")

        first_entity = obs["legal_actions"]["entity_ids"][0]
        next_obs = controller.submit_agent_action("player_1", {"kind": "select_entity", "entity_id": first_entity})
        self.assertEqual(next_obs["phase"], "place")
        self.assertEqual(next_obs["current_player"], "player_2")
        self.assertEqual(next_obs["selected_entity"], first_entity)

        next_obs = controller.submit_agent_action("player_2", {"kind": "place_entity", "cell": 0})
        self.assertEqual(next_obs["phase"], "select")
        self.assertEqual(next_obs["current_player"], "player_2")
        self.assertIsNone(next_obs["selected_entity"])

    def test_self_selection_mode_keeps_active_player_for_placement(self):
        controller = Phase0Controller(SyntheticAdapter(), mode="self_selection")
        obs = controller.public_observation("player_1")
        first_entity = obs["legal_actions"]["entity_ids"][0]

        next_obs = controller.submit_agent_action("player_1", {"kind": "select_entity", "entity_id": first_entity})
        self.assertEqual(next_obs["phase"], "place")
        self.assertEqual(next_obs["current_player"], "player_1")
        self.assertEqual(next_obs["selected_entity"], first_entity)

        next_obs = controller.submit_agent_action("player_1", {"kind": "place_entity", "cell": 1})
        self.assertEqual(next_obs["phase"], "select")
        self.assertEqual(next_obs["current_player"], "player_2")

    def test_explicit_requester_is_required_and_player_identity_is_rejected(self):
        controller = Phase0Controller(SyntheticAdapter(), mode="classic")
        with self.assertRaises(TypeError):
            controller.submit_agent_action()
        with self.assertRaises(TypeError):
            controller.submit_agent_action("player_1")
        with self.assertRaises(ValueError):
            controller.submit_agent_action("player_2", {"kind": "select_entity", "entity_id": "e00"})
        with self.assertRaises(ValueError):
            controller.submit_agent_action("player_1", {"kind": "select_entity", "entity_id": "e00", "player": "player_2"})
        with self.assertRaises(ValueError):
            controller.submit_agent_action("player_9", {"kind": "select_entity", "entity_id": "e00"})
        with self.assertRaises(ValueError):
            controller.submit_agent_action("player_1", {"kind": "place_entity", "cell": "bad"})

    def test_feature_matrix_validation_rejects_missing_and_invalid_values(self):
        adapter = SyntheticAdapter()
        base = adapter.load_domain()

        bad_values = dict(base.values)
        del bad_values["e00"]
        bad_domain = DomainCatalog(
            name=base.name,
            version=base.version,
            entities=base.entities,
            features=base.features,
            values=MappingProxyType(bad_values),
        )
        with self.assertRaises(ValueError):
            MatchSession(bad_domain, adapter.build_instance())

        bad_values = {entity_id: dict(values) for entity_id, values in base.values.items()}
        bad_values["e00"].pop("f0")
        bad_domain = DomainCatalog(
            name=base.name,
            version=base.version,
            entities=base.entities,
            features=base.features,
            values=MappingProxyType({entity_id: MappingProxyType(values) for entity_id, values in bad_values.items()}),
        )
        with self.assertRaises(ValueError):
            MatchSession(bad_domain, adapter.build_instance())

        bad_values = {entity_id: dict(values) for entity_id, values in base.values.items()}
        bad_values["e00"]["f0"] = 1
        bad_domain = DomainCatalog(
            name=base.name,
            version=base.version,
            entities=base.entities,
            features=base.features,
            values=MappingProxyType({entity_id: MappingProxyType(values) for entity_id, values in bad_values.items()}),
        )
        with self.assertRaises(ValueError):
            MatchSession(bad_domain, adapter.build_instance())

        instance = adapter.build_instance()
        signature_map = dict(instance.signature_map)
        signature_map["e00"] = 15
        bad_instance = type(instance)(
            instance_id=instance.instance_id,
            domain_name=instance.domain_name,
            feature_ids=instance.feature_ids,
            entity_ids=instance.entity_ids,
            signature_map=MappingProxyType(signature_map),
            public_seed=instance.public_seed,
        )
        with self.assertRaises(ValueError):
            MatchSession(base, bad_instance)

        duplicate_signature_map = dict(instance.signature_map)
        duplicate_signature_map["e01"] = duplicate_signature_map["e00"]
        dup_instance = type(instance)(
            instance_id=instance.instance_id,
            domain_name=instance.domain_name,
            feature_ids=instance.feature_ids,
            entity_ids=instance.entity_ids,
            signature_map=MappingProxyType(duplicate_signature_map),
            public_seed=instance.public_seed,
        )
        with self.assertRaises(ValueError):
            MatchSession(base, dup_instance)

        bad_entity = type(instance)(
            instance_id=instance.instance_id,
            domain_name=instance.domain_name,
            feature_ids=instance.feature_ids,
            entity_ids=("e00", "e01", "e02", "e03", "e04", "e05", "e06", "e07", "e08", "e09", "e10", "e11", "e12", "e13", "e14", "missing"),
            signature_map=MappingProxyType({entity_id: index for index, entity_id in enumerate(("e00", "e01", "e02", "e03", "e04", "e05", "e06", "e07", "e08", "e09", "e10", "e11", "e12", "e13", "e14", "missing"))}),
            public_seed=instance.public_seed,
        )
        with self.assertRaises(ValueError):
            MatchSession(base, bad_entity)

    def test_observation_mutation_does_not_affect_session_state(self):
        controller = Phase0Controller(SyntheticAdapter(), mode="classic")
        first_entity = controller.public_observation("player_1")["legal_actions"]["entity_ids"][0]
        controller.submit_agent_action("player_1", {"kind": "select_entity", "entity_id": first_entity})

        observation = controller.public_observation("player_2")
        observation["history"][0]["entity_id"] = "tampered"
        observation["board"][0] = "tampered"
        observation["legal_actions"]["cells"].append(123)

        current = controller.public_observation("player_2")
        self.assertEqual(current["history"][0]["entity_id"], first_entity)
        self.assertIsNone(current["board"][0])
        self.assertEqual(current["legal_actions"]["cells"], list(range(16)))

    def test_audit_snapshot_is_deeply_immutable_and_replay_verified(self):
        controller = Phase0Controller(SyntheticAdapter(), mode="classic")
        selected = controller.public_observation("player_1")["legal_actions"]["entity_ids"][0]
        controller.submit_agent_action("player_1", {"kind": "select_entity", "entity_id": selected})
        controller.submit_agent_action("player_2", {"kind": "place_entity", "cell": 0})
        snapshot = controller.get_read_only_audit_view()

        self.assertIsInstance(snapshot, AuditSnapshot)
        self.assertTrue(snapshot.validate_replay())
        self.assertTrue(validate_audit_snapshot(snapshot))

        with self.assertRaises(TypeError):
            entity_id = next(iter(snapshot.restricted_evaluator_data["entity_to_piece"]))
            snapshot.restricted_evaluator_data["entity_to_piece"][entity_id] = "tampered"
        with self.assertRaises(TypeError):
            snapshot.restricted_evaluator_data["engine_state_snapshot"]["history"][0]["kind"] = "tampered"
        with self.assertRaises(AttributeError):
            snapshot.public_audit["legal_actions"]["entity_ids"].append("tampered")

        before = _to_plain(snapshot.restricted_evaluator_data)
        controller.submit_agent_action("player_2", {"kind": "select_entity", "entity_id": controller.public_observation("player_2")["legal_actions"]["entity_ids"][0]})
        after = snapshot.restricted_evaluator_data
        self.assertEqual(before["engine_state_snapshot"]["phase"], after["engine_state_snapshot"]["phase"])
        self.assertEqual(tuple(before["engine_state_snapshot"]["board"]), tuple(after["engine_state_snapshot"]["board"]))

    def test_validate_replay_rejects_malformed_engine_state_snapshots(self):
        snapshot = Phase0Controller(SyntheticAdapter()).get_read_only_audit_view()
        original_state = dict(snapshot.restricted_evaluator_data["engine_state_snapshot"])

        def remove_starting_player(state):
            state.pop("starting_player")

        def remove_result(state):
            state.pop("result")

        def add_unexpected_field(state):
            state["internal_debug"] = "unexpected"

        def use_invalid_type(state):
            state["is_terminal"] = 1

        def use_invalid_board_piece_type(state):
            state["board"] = (False, *state["board"][1:])

        def make_phase_and_result_inconsistent(state):
            state["phase"] = "terminal"
            state["is_terminal"] = True

        mutations = (
            ("missing starting_player", remove_starting_player),
            ("missing result", remove_result),
            ("unexpected field", add_unexpected_field),
            ("invalid field type", use_invalid_type),
            ("invalid board piece type", use_invalid_board_piece_type),
            ("inconsistent phase/result", make_phase_and_result_inconsistent),
        )
        for label, mutate in mutations:
            with self.subTest(case=label):
                engine_state = dict(original_state)
                mutate(engine_state)
                restricted = dict(snapshot.restricted_evaluator_data)
                restricted["engine_state_snapshot"] = MappingProxyType(engine_state)
                malformed = replace(
                    snapshot,
                    restricted_evaluator_data=MappingProxyType(restricted),
                )

                self.assertFalse(malformed.validate_replay())
                self.assertFalse(validate_audit_snapshot(malformed))

    def test_validate_replay_accepts_valid_modes_starting_players_and_outcomes(self):
        draw_order = (12, 5, 0, 10, 6, 2, 13, 9, 15, 11, 7, 4, 1, 14, 3, 8)
        outcomes = (
            ("win", (0, 1, 2, 3)),
            ("draw", draw_order),
        )

        def assert_valid_snapshot(controller):
            audit_snapshot = controller.get_read_only_audit_view()
            self.assertTrue(audit_snapshot.validate_replay())
            self.assertTrue(validate_audit_snapshot(audit_snapshot))

        for mode in ("classic", "self_selection"):
            for starting_player in ("player_1", "player_2"):
                for expected_outcome, pieces in outcomes:
                    with self.subTest(
                        mode=mode,
                        starting_player=starting_player,
                        outcome=expected_outcome,
                    ):
                        controller = Phase0Controller(
                            SyntheticAdapter(),
                            mode=mode,
                            starting_player=starting_player,
                        )
                        assert_valid_snapshot(controller)

                        for cell, piece_id in enumerate(pieces):
                            active_player = controller.session.engine_state.active_player
                            public = controller.public_observation(active_player)
                            entity_id = controller.session.piece_to_entity[piece_id]
                            self.assertIn(
                                entity_id,
                                public["legal_actions"]["entity_ids"],
                            )
                            controller.submit_agent_action(
                                active_player,
                                {"kind": "select_entity", "entity_id": entity_id},
                            )
                            if cell == 0:
                                assert_valid_snapshot(controller)

                            placer = controller.session.engine_state.active_player
                            controller.submit_agent_action(
                                placer,
                                {"kind": "place_entity", "cell": cell},
                            )
                            if cell == 0:
                                assert_valid_snapshot(controller)

                        self.assertEqual(
                            controller.session.engine_state.result.outcome,
                            expected_outcome,
                        )
                        assert_valid_snapshot(controller)

    def test_match_entity_ids_are_opaque_unique_and_stable(self):
        adapter = SyntheticAdapter()
        instance = adapter.build_instance()
        controller = Phase0Controller(adapter, mode="classic", instance=instance)
        observation = controller.public_observation("player_1")
        public_ids = tuple(
            entity["entity_id"] for entity in observation["public_entities"]
        )

        self.assertEqual(len(public_ids), 16)
        self.assertEqual(len(set(public_ids)), 16)
        self.assertEqual(public_ids, tuple(sorted(public_ids)))
        self.assertTrue(all(UUID(hex=entity_id).version == 4 for entity_id in public_ids))
        self.assertTrue(set(public_ids).isdisjoint(instance.entity_ids))
        self.assertTrue(
            all(
                entity_id not in {str(signature) for signature in instance.signature_map.values()}
                for entity_id in public_ids
            )
        )
        self.assertEqual(
            tuple(observation["legal_actions"]["entity_ids"]),
            public_ids,
        )
        self.assertEqual(tuple(observation["available_entities"]), public_ids)
        self.assertEqual(
            {entity["label"] for entity in observation["public_entities"]},
            set(public_ids),
        )

        second_match = Phase0Controller(adapter, mode="classic", instance=instance)
        second_ids = {
            entity["entity_id"]
            for entity in second_match.public_observation("player_1")["public_entities"]
        }
        self.assertTrue(set(public_ids).isdisjoint(second_ids))

        entity_id = observation["legal_actions"]["entity_ids"][0]
        selected = controller.submit_agent_action(
            "player_1",
            {"kind": "select_entity", "entity_id": entity_id},
        )
        self.assertEqual(selected["selected_entity"], entity_id)
        self.assertEqual(selected["history"][0]["entity_id"], entity_id)
        placed = controller.submit_agent_action(
            "player_2",
            {"kind": "place_entity", "cell": 0},
        )
        self.assertEqual(placed["board"][0], entity_id)
        self.assertEqual(placed["history"][0]["entity_id"], entity_id)
        snapshot = controller.get_read_only_audit_view()
        self.assertEqual(snapshot.public_audit["board"][0], entity_id)
        self.assertEqual(
            snapshot.restricted_evaluator_data["piece_to_entity"][
                snapshot.restricted_evaluator_data["entity_to_piece"][entity_id]
            ],
            entity_id,
        )
        self.assertTrue(validate_audit_snapshot(snapshot))

    def test_source_id_crosswalk_is_restricted_and_audit_validated(self):
        adapter = SyntheticAdapter()
        instance = adapter.build_instance()
        restricted_source_ids = {
            entity_id: f"private-source-{index:02d}"
            for index, entity_id in enumerate(instance.entity_ids)
        }
        controller = Phase0Controller(
            adapter,
            instance=instance,
            restricted_source_ids=restricted_source_ids,
        )
        public_observation = controller.public_observation("player_1")
        snapshot = controller.get_read_only_audit_view()
        public_text = json.dumps(_to_plain(public_observation), sort_keys=True)
        public_audit_text = json.dumps(_to_plain(snapshot.public_audit), sort_keys=True)

        self.assertTrue(validate_audit_snapshot(snapshot))
        crosswalk = snapshot.restricted_evaluator_data["public_entity_to_source_id"]
        entity_to_piece = snapshot.restricted_evaluator_data["entity_to_piece"]
        source_to_entity = {
            source_id: entity_id
            for entity_id, source_id in restricted_source_ids.items()
        }
        self.assertEqual(set(crosswalk), set(entity_to_piece))
        for public_id, source_id in crosswalk.items():
            self.assertEqual(
                instance.signature_map[source_to_entity[source_id]],
                entity_to_piece[public_id],
            )
        for source_id in restricted_source_ids.values():
            self.assertNotIn(source_id, public_text)
            self.assertNotIn(source_id, public_audit_text)

        restricted = dict(snapshot.restricted_evaluator_data)
        crosswalk = dict(restricted["public_entity_to_source_id"])
        keys = list(crosswalk)
        crosswalk[keys[0]] = crosswalk[keys[1]]
        restricted["public_entity_to_source_id"] = MappingProxyType(crosswalk)
        malformed = replace(
            snapshot,
            restricted_evaluator_data=MappingProxyType(restricted),
        )
        self.assertFalse(validate_audit_snapshot(malformed))

    def test_controller_rejects_incomplete_or_duplicate_source_id_crosswalks(self):
        adapter = SyntheticAdapter()
        instance = adapter.build_instance()
        incomplete = {entity_id: entity_id for entity_id in instance.entity_ids[:-1]}
        duplicate = {
            entity_id: "duplicate-source-id"
            for entity_id in instance.entity_ids
        }

        with self.assertRaises(ValueError):
            Phase0Controller(adapter, instance=instance, restricted_source_ids=incomplete)
        with self.assertRaises(ValueError):
            Phase0Controller(adapter, instance=instance, restricted_source_ids=duplicate)

    def test_validate_audit_snapshot_rejects_unexpected_public_and_restricted_fields(self):
        controller = Phase0Controller(SyntheticAdapter(), mode="classic")
        snapshot = controller.get_read_only_audit_view()

        public_audit = dict(snapshot.public_audit)
        public_audit["restricted_evaluator_data"] = "RESTRICTED_SENTINEL"
        self.assertFalse(
            validate_audit_snapshot(
                replace(snapshot, public_audit=MappingProxyType(public_audit))
            )
        )

        restricted = dict(snapshot.restricted_evaluator_data)
        restricted["unrecognized_internal_value"] = "RESTRICTED_SENTINEL"
        self.assertFalse(
            validate_audit_snapshot(
                replace(
                    snapshot,
                    restricted_evaluator_data=MappingProxyType(restricted),
                )
            )
        )

    def test_validate_audit_snapshot_rejects_unexpected_nested_public_fields(self):
        controller = Phase0Controller(SyntheticAdapter(), mode="classic")
        controller.submit_agent_action(
            "player_1",
            {
                "kind": "select_entity",
                "entity_id": controller.public_observation("player_1")[
                    "legal_actions"
                ]["entity_ids"][0],
            },
        )
        controller.submit_agent_action("player_2", {"kind": "place_entity", "cell": 0})
        snapshot = controller.get_read_only_audit_view()

        public_audit = dict(snapshot.public_audit)
        legal_actions = dict(public_audit["legal_actions"])
        legal_actions["piece_id"] = 0
        public_audit["legal_actions"] = MappingProxyType(legal_actions)
        self.assertFalse(
            validate_audit_snapshot(
                replace(snapshot, public_audit=MappingProxyType(public_audit))
            )
        )

        public_audit = dict(snapshot.public_audit)
        history = [dict(action) for action in public_audit["public_history"]]
        history[0]["piece_id"] = 0
        public_audit["public_history"] = tuple(
            MappingProxyType(action) for action in history
        )
        self.assertFalse(
            validate_audit_snapshot(
                replace(snapshot, public_audit=MappingProxyType(public_audit))
            )
        )

    def test_restricted_identifier_sentinel_is_rejected_from_public_fields(self):
        controller = Phase0Controller(SyntheticAdapter(), mode="classic")
        snapshot = controller.get_read_only_audit_view()
        public_audit = dict(snapshot.public_audit)
        public_audit["selected_entity"] = "piece_to_entity"
        self.assertFalse(
            validate_audit_snapshot(
                replace(snapshot, public_audit=MappingProxyType(public_audit))
            )
        )

    def test_validate_audit_snapshot_accepts_exact_ownership_partition(self):
        controller = Phase0Controller(SyntheticAdapter(), mode="classic")
        snapshot = controller.get_read_only_audit_view()
        self.assertTrue(validate_audit_snapshot(snapshot))

        restricted = dict(snapshot.restricted_evaluator_data)
        restricted["private_feature_ownership"] = {
            "player_1": ("f0", "f1"),
            "player_2": ("f2", "f3"),
        }
        self.assertTrue(validate_audit_snapshot(replace(snapshot, restricted_evaluator_data=MappingProxyType(restricted))))

    def test_validate_audit_snapshot_rejects_invalid_ownership_partitions(self):
        controller = Phase0Controller(SyntheticAdapter(), mode="classic")
        snapshot = controller.get_read_only_audit_view()
        restricted = dict(snapshot.restricted_evaluator_data)

        invalids = [
            {"player_1": ("f0", "f1"), "player_2": ("f1", "f2")},
            {"player_1": ("f0", "f1", "f2"), "player_2": ("f3",)},
            {"player_1": ("f0",), "player_2": ("f2", "f3")},
            {"player_1": ("f0", "f9"), "player_2": ("f2", "f3")},
            {"player_1": ("f0", "f1"), "player_2": ("f2", "f3")},
        ]
        for invalid in invalids[:-1]:
            restricted["private_feature_ownership"] = invalid
            self.assertFalse(validate_audit_snapshot(replace(snapshot, restricted_evaluator_data=MappingProxyType(restricted))))
        restricted["private_feature_ownership"] = invalids[-1]
        self.assertTrue(validate_audit_snapshot(replace(snapshot, restricted_evaluator_data=MappingProxyType(restricted))))

    def test_validate_audit_snapshot_rejects_missing_and_malformed_required_internal_fields(self):
        controller = Phase0Controller(SyntheticAdapter(), mode="classic")
        snapshot = controller.get_read_only_audit_view()

        restricted = dict(snapshot.restricted_evaluator_data)
        engine_state = dict(restricted["engine_state_snapshot"])
        for missing_field in ("mode", "phase", "active_player", "result", "board"):
            broken = dict(engine_state)
            broken.pop(missing_field)
            restricted["engine_state_snapshot"] = MappingProxyType(broken)
            self.assertFalse(validate_audit_snapshot(replace(snapshot, restricted_evaluator_data=MappingProxyType(restricted))))
            restricted["engine_state_snapshot"] = MappingProxyType(engine_state)

        bad = dict(engine_state)
        bad["result"] = {"mode": "classic", "outcome": "winner"}
        restricted["engine_state_snapshot"] = MappingProxyType(bad)
        self.assertFalse(validate_audit_snapshot(replace(snapshot, restricted_evaluator_data=MappingProxyType(restricted))))

        malformed_ownership = {"player_1": ["f0", "f1", "f0"], "player_2": ["f2", "f3"]}
        restricted["engine_state_snapshot"] = MappingProxyType(engine_state)
        restricted["private_feature_ownership"] = malformed_ownership
        self.assertFalse(validate_audit_snapshot(replace(snapshot, restricted_evaluator_data=MappingProxyType(restricted))))

        bad_board = list(engine_state["board"])
        bad_board.pop()
        restricted["private_feature_ownership"] = {"player_1": ("f0", "f1"), "player_2": ("f2", "f3")}
        restricted["engine_state_snapshot"] = MappingProxyType({**engine_state, "board": tuple(bad_board)})
        self.assertFalse(validate_audit_snapshot(replace(snapshot, restricted_evaluator_data=MappingProxyType(restricted))))

    def test_validate_audit_snapshot_accepts_non_synthetic_feature_ids(self):
        controller = Phase0Controller(SyntheticAdapter(), mode="classic")
        snapshot = controller.get_read_only_audit_view()
        restricted = dict(snapshot.restricted_evaluator_data)
        restricted["feature_to_bit"] = {"alpha": 0, "beta": 1, "gamma": 2, "delta": 3}
        restricted["private_feature_ownership"] = {"player_1": ("alpha", "beta"), "player_2": ("gamma", "delta")}
        self.assertTrue(validate_audit_snapshot(replace(snapshot, restricted_evaluator_data=MappingProxyType(restricted))))

    def test_validate_audit_snapshot_rejects_tampering_in_multiple_ways(self):
        controller = Phase0Controller(SyntheticAdapter(), mode="classic")
        snapshot = controller.get_read_only_audit_view()

        restricted = dict(snapshot.restricted_evaluator_data)
        entity_to_piece = dict(restricted["entity_to_piece"])
        public_ids = list(entity_to_piece)
        entity_to_piece[public_ids[0]] = 1
        piece_to_entity = dict(restricted["piece_to_entity"])
        piece_to_entity[1] = public_ids[1]
        piece_to_entity[0] = public_ids[2]
        restricted["entity_to_piece"] = entity_to_piece
        restricted["piece_to_entity"] = piece_to_entity
        self.assertFalse(validate_audit_snapshot(replace(snapshot, restricted_evaluator_data=MappingProxyType(restricted))))

        restricted = dict(snapshot.restricted_evaluator_data)
        restricted["feature_to_bit"] = {"f0": 0, "f1": 0, "f2": 2, "f3": 3}
        self.assertFalse(validate_audit_snapshot(replace(snapshot, restricted_evaluator_data=MappingProxyType(restricted))))

        restricted = dict(snapshot.restricted_evaluator_data)
        public_audit = dict(snapshot.public_audit)
        public_audit["board"] = tuple(
            "not-an-entity" if index == 0 else value
            for index, value in enumerate(public_audit["board"])
        )
        restricted["engine_state_snapshot"] = dict(restricted["engine_state_snapshot"])
        restricted["engine_state_snapshot"]["board"] = tuple(None if index == 0 else piece_id for index, piece_id in enumerate(restricted["engine_state_snapshot"]["board"]))
        self.assertFalse(validate_audit_snapshot(replace(snapshot, public_audit=MappingProxyType(public_audit), restricted_evaluator_data=MappingProxyType(restricted))))

        restricted = dict(snapshot.restricted_evaluator_data)
        restricted["private_feature_ownership"] = {"player_1": ("f0", "f1"), "player_2": ("f1", "f2")}
        self.assertFalse(validate_audit_snapshot(replace(snapshot, restricted_evaluator_data=MappingProxyType(restricted))))

        restricted = dict(snapshot.restricted_evaluator_data)
        public_audit = dict(snapshot.public_audit)
        public_audit["mode"] = "self_selection"
        self.assertFalse(validate_audit_snapshot(replace(snapshot, public_audit=MappingProxyType(public_audit), restricted_evaluator_data=MappingProxyType(restricted))))

        restricted = dict(snapshot.restricted_evaluator_data)
        replay = restricted["engine_replay"]
        restricted["engine_replay"] = replay[:-1] + "0"
        self.assertFalse(validate_audit_snapshot(replace(snapshot, restricted_evaluator_data=MappingProxyType(restricted))))

    def test_public_and_private_observations_hide_sensitive_state_in_both_modes(self):
        for mode in ("classic", "self_selection"):
            adapter = SyntheticAdapter()
            instance = adapter.build_instance()
            controller = Phase0Controller(adapter, mode=mode, instance=instance)
            public1 = controller.public_observation("player_1")
            private1 = controller.private_observation("player_1")
            player_2_controller = Phase0Controller(
                adapter,
                mode=mode,
                instance=instance,
                starting_player="player_2",
            )
            public2 = player_2_controller.public_observation("player_2")
            private2 = player_2_controller.private_observation("player_2")

            self.assertEqual(private1["requester"], "player_1")
            self.assertEqual(private2["requester"], "player_2")
            with self.assertRaisesRegex(ValueError, "active player"):
                controller.private_observation("player_2")
            with self.assertRaisesRegex(ValueError, "active player"):
                controller.session.private_observation("player_2")
            for obs in (public1, public2, private1, private2):
                self.assertNotIn("entity_to_piece", obs)
                self.assertNotIn("piece_to_entity", obs)
                self.assertNotIn("feature_to_bit", obs)
                self.assertNotIn("private_feature_ownership", obs)
                self.assertNotIn("engine_replay", obs)
                self.assertNotIn("restricted_evaluator_data", obs)
                self.assertNotIn("selected_piece", obs)

            self.assertEqual(private1["private"]["owned_features"], ["f0", "f1"])
            self.assertEqual(private2["private"]["owned_features"], ["f2", "f3"])
            self.assertNotIn("private_feature_ownership", public1)
            self.assertNotIn("private_feature_ownership", public2)
            self.assertNotIn("private", public1)
            self.assertNotIn("private", public2)

            public_audit = controller.get_read_only_audit_view().public_audit
            self.assertNotIn("private_feature_ownership", public_audit)
            self.assertNotIn("owned_features", public_audit)
            self.assertNotIn("private", public_audit)

    def test_actual_engine_semantics_hold_for_two_cycles_in_each_mode(self):
        def assert_cycle(controller, active_player, selected_entity, board_cell):
            public_obs = controller.public_observation(active_player)
            self.assertEqual(public_obs["current_player"], active_player)
            self.assertEqual(public_obs["phase"], "select")
            self.assertIn(selected_entity, public_obs["legal_actions"]["entity_ids"])
            controller.submit_agent_action(active_player, {"kind": "select_entity", "entity_id": selected_entity})
            self.assertEqual(controller.session.engine_state.phase, "place")
            self.assertEqual(controller.session.engine_state.selected_by, active_player)
            self.assertEqual(controller.session.engine_state.active_player, "player_2" if active_player == "player_1" else "player_1")
            place_obs = controller.public_observation(controller.session.engine_state.active_player)
            self.assertEqual(place_obs["phase"], "place")
            self.assertEqual(place_obs["selected_entity"], selected_entity)
            controller.submit_agent_action(controller.session.engine_state.active_player, {"kind": "place_entity", "cell": board_cell})
            self.assertEqual(controller.session.public_observation(controller.session.engine_state.active_player)["board"][board_cell], selected_entity)

        controller = Phase0Controller(SyntheticAdapter(), mode="classic")
        assert_cycle(controller, "player_1", controller.public_observation("player_1")["legal_actions"]["entity_ids"][0], 0)
        controller.submit_agent_action("player_2", {"kind": "select_entity", "entity_id": controller.public_observation("player_2")["legal_actions"]["entity_ids"][0]})
        controller.submit_agent_action("player_1", {"kind": "place_entity", "cell": 1})

        controller = Phase0Controller(SyntheticAdapter(), mode="self_selection")
        first = controller.public_observation("player_1")["legal_actions"]["entity_ids"][0]
        controller.submit_agent_action("player_1", {"kind": "select_entity", "entity_id": first})
        controller.submit_agent_action("player_1", {"kind": "place_entity", "cell": 2})
        second = controller.public_observation("player_2")["legal_actions"]["entity_ids"][0]
        controller.submit_agent_action("player_2", {"kind": "select_entity", "entity_id": second})
        controller.submit_agent_action("player_2", {"kind": "place_entity", "cell": 3})

        self.assertEqual(controller.session.engine_state.active_player, "player_1")
        self.assertEqual(controller.session.engine_state.phase, "select")


if __name__ == "__main__":
    unittest.main()
