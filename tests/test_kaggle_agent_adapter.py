import inspect
import json
import time
import unittest
from collections.abc import Mapping
from typing import Any
from uuid import UUID

from kaggle_agent_adapter import KaggleAgentAdapter
from phase0_foundation import Phase0Controller, SyntheticAdapter
from tournament_harness import (
    AgentAdapter,
    MODEL_TAGS,
    MatchAgentFailure,
    ModelClientError,
    TournamentRunner,
)


class _FakeKaggleLLM:
    def __init__(self, response: object = "", error: Exception | None = None) -> None:
        self.response = response
        self.error = error
        self.prompts: list[str] = []

    def prompt(self, prompt: str) -> str:
        self.prompts.append(prompt)
        if self.error is not None:
            raise self.error
        return self.response


class _ObservationDrivenKaggleLLM:
    def __init__(self) -> None:
        self.prompts: list[str] = []
        self.observations: list[dict[str, object]] = []

    def prompt(self, prompt: str) -> str:
        self.prompts.append(prompt)
        observation_json = prompt.split("Observation JSON:\n", 1)[1]
        payload = json.loads(observation_json)
        observation = payload["public_observation"]
        self.observations.append(payload)
        legal = observation["legal_actions"]
        if legal["kind"] == "select_entity":
            action = {
                "kind": "select_entity",
                "entity_id": legal["entity_ids"][0],
            }
        elif legal["kind"] == "place_entity":
            action = {
                "kind": "place_entity",
                "cell": legal["cells"][0],
            }
        else:
            raise AssertionError(f"Unexpected legal-action kind: {legal['kind']!r}")
        return json.dumps(action)


class KaggleAgentAdapterTests(unittest.TestCase):
    def setUp(self) -> None:
        self.domain_adapter = SyntheticAdapter()
        self.instance = self.domain_adapter.build_instance()
        self.controller = Phase0Controller(
            self.domain_adapter,
            mode="classic",
            instance=self.instance,
        )
        self.public_observation = self.controller.public_observation("player_1")
        self.player = self.public_observation["current_player"]
        self.private_observation = self.controller.private_observation(self.player)
        legal = self.public_observation["legal_actions"]
        if legal["kind"] == "select_entity":
            action = {
                "kind": "select_entity",
                "entity_id": legal["entity_ids"][0],
            }
            self.missing_field_response = {"kind": "select_entity"}
            self.invalid_value_response = {
                "kind": "select_entity",
                "entity_id": "NOT_A_LEGAL_ENTITY",
            }
            self.invalid_type_response = {
                "kind": "select_entity",
                "entity_id": 42,
            }
        else:
            action = {
                "kind": "place_entity",
                "cell": legal["cells"][0],
            }
            self.missing_field_response = {"kind": "place_entity"}
            self.invalid_value_response = {"kind": "place_entity", "cell": -1}
            self.invalid_type_response = {"kind": "place_entity", "cell": True}
        self.action = action
        self.valid_response = json.dumps(action)

    def _invoke(
        self,
        llm: _FakeKaggleLLM,
        *,
        public_observation: Mapping[str, object] | None = None,
        private_observation: Mapping[str, object] | None = None,
    ) -> dict[str, object]:
        return KaggleAgentAdapter(llm).get_action(
            self.public_observation
            if public_observation is None
            else public_observation,
            self.private_observation
            if private_observation is None
            else private_observation,
            deadline=time.monotonic() + 10,
            event_log=[],
        )

    def test_valid_json_returns_action_accepted_by_controller(self) -> None:
        llm = _FakeKaggleLLM(self.valid_response)

        action = self._invoke(llm)
        next_observation = self.controller.submit_agent_action(self.player, action)

        self.assertEqual(action, self.action)
        self.assertIsInstance(next_observation, dict)
        self.assertEqual(len(llm.prompts), 1)

    def test_provider_response_after_deadline_is_rejected(self) -> None:
        class DelayedLLM(_FakeKaggleLLM):
            def prompt(self, prompt: str) -> str:
                self.prompts.append(prompt)
                time.sleep(0.06)
                return self.response

        llm = DelayedLLM(self.valid_response)
        events: list[dict[str, object]] = []

        with self.assertRaisesRegex(
            MatchAgentFailure,
            "deadline expired after model response",
        ):
            KaggleAgentAdapter(llm).get_action(
                self.public_observation,
                self.private_observation,
                deadline=time.monotonic() + 0.02,
                event_log=events,
            )

        self.assertEqual(len(llm.prompts), 1)
        self.assertEqual(events[0]["validation"], "deadline_expired")
        self.assertNotIn("parsed_action", events[0])

    def test_tournament_runner_accepts_kaggle_clients_for_synthetic_self_play(self) -> None:
        llms = {
            "player_1": _ObservationDrivenKaggleLLM(),
            "player_2": _ObservationDrivenKaggleLLM(),
        }
        kaggle_client = KaggleAgentAdapter(llms["player_1"]).client
        clients = {
            MODEL_TAGS[0]: kaggle_client,
            MODEL_TAGS[1]: KaggleAgentAdapter(llms["player_2"]).client,
        }
        assignments = {
            "player_1": MODEL_TAGS[0],
            "player_2": MODEL_TAGS[1],
        }
        runner = TournamentRunner(
            clients,
            wall_clock_timeout=20,
            max_correction_attempts=0,
        )

        result = runner.run_match(
            self.domain_adapter,
            self.instance,
            assignments,
        )

        self.assertEqual(result.status, "completed", result.failure)
        self.assertEqual(result.assignments, assignments)
        self.assertGreater(result.action_count, 0)
        self.assertEqual(len(result.restricted_log["decision_traces"]), result.action_count)
        self.assertEqual(
            len(llms["player_1"].prompts) + len(llms["player_2"].prompts),
            result.action_count,
        )
        self.assertTrue(
            all(event["attempt"] == 1 for event in result.restricted_log["events"])
        )
        self.assertTrue(
            all(
                event["controller_validation"] == "passed"
                for event in result.restricted_log["events"]
            )
        )
        self.assertTrue(result.audit_valid)
        self.assertTrue(result.replay_valid)

        traces = result.restricted_log["decision_traces"]
        self.assertTrue(all(trace["model_provider"] == "kaggle" for trace in traces))
        self.assertTrue(all("model_name" not in trace for trace in traces))
        self.assertTrue(all("model_version" not in trace for trace in traces))
        self.assertEqual(
            len(traces),
            sum(len(llm.prompts) for llm in llms.values()),
        )

        allowed_public_fields = {
            "mode",
            "phase",
            "current_player",
            "board",
            "available_entities",
            "selected_entity",
            "legal_actions",
            "history",
            "terminal",
        }
        forbidden_prompt_fields = {
            "engine_state",
            "engine_state_snapshot",
            "entity_to_piece",
            "piece_to_entity",
            "feature_to_bit",
            "piece_id",
            "selected_piece",
            "audit_snapshot",
            "restricted_evaluator_data",
            "opponent_secret",
            "opponent_private",
        }
        for llm in llms.values():
            for payload in llm.observations:
                self.assertEqual(set(payload["public_observation"]), allowed_public_fields)
                self.assertEqual(
                    set(payload["requester_private_observation"]),
                    {"private"},
                )
                self.assertFalse(
                    forbidden_prompt_fields.intersection(
                        key.lower()
                        for item in payload.values()
                        if isinstance(item, dict)
                        for key in item
                    )
                )

    def test_invalid_json_is_rejected_without_retry(self) -> None:
        llm = _FakeKaggleLLM("not JSON")

        with self.assertRaisesRegex(MatchAgentFailure, "valid JSON"):
            self._invoke(llm)

        self.assertEqual(len(llm.prompts), 1)

    def test_missing_required_action_field_is_rejected(self) -> None:
        llm = _FakeKaggleLLM(json.dumps(self.missing_field_response))

        with self.assertRaises(MatchAgentFailure):
            self._invoke(llm)

    def test_unexpected_action_field_is_rejected(self) -> None:
        response = dict(self.action, player=self.player)

        with self.assertRaises(MatchAgentFailure):
            self._invoke(_FakeKaggleLLM(json.dumps(response)))

    def test_invalid_action_value_is_rejected(self) -> None:
        with self.assertRaisesRegex(MatchAgentFailure, "legal-action list"):
            self._invoke(_FakeKaggleLLM(json.dumps(self.invalid_value_response)))

    def test_invalid_action_data_type_is_rejected(self) -> None:
        with self.assertRaises(MatchAgentFailure):
            self._invoke(_FakeKaggleLLM(json.dumps(self.invalid_type_response)))

    def test_empty_response_is_rejected(self) -> None:
        with self.assertRaisesRegex(MatchAgentFailure, "empty action"):
            self._invoke(_FakeKaggleLLM(""))

    def test_model_invocation_error_is_preserved_as_model_failure(self) -> None:
        llm = _FakeKaggleLLM(error=RuntimeError("provider unavailable"))
        events: list[dict[str, object]] = []
        agent = KaggleAgentAdapter(llm)

        with self.assertRaisesRegex(ModelClientError, "invocation failed"):
            agent.get_action(
                self.public_observation,
                self.private_observation,
                deadline=time.monotonic() + 10,
                event_log=events,
            )

        self.assertEqual(len(llm.prompts), 1)
        self.assertEqual(events[0]["validation"], "request_failed")

    def test_existing_trace_explanation_fields_are_preserved(self) -> None:
        response = {
            "action": self.action,
            "decision_explanation": "Choose a currently legal entity.",
            "declared_confidence": 0.75,
        }
        llm = _FakeKaggleLLM(json.dumps(response))
        agent = KaggleAgentAdapter(llm)

        decision = agent.get_decision(
            self.public_observation,
            self.private_observation,
            deadline=time.monotonic() + 10,
            event_log=[],
        )

        self.assertEqual(decision.action, self.action)
        self.assertEqual(
            decision.decision_explanation,
            "Choose a currently legal entity.",
        )
        self.assertEqual(decision.declared_confidence, 0.75)

    def test_prompt_contains_only_the_sanitized_agent_observation(self) -> None:
        llm = _FakeKaggleLLM(self.valid_response)

        self._invoke(llm)
        prompt = llm.prompts[0]

        self.assertIn("Observation JSON:", prompt)
        prompt_observation = json.loads(prompt.split("Observation JSON:\n", 1)[1])
        self.assertEqual(
            set(prompt_observation["public_observation"]),
            {
                "mode",
                "phase",
                "current_player",
                "board",
                "available_entities",
                "selected_entity",
                "legal_actions",
                "history",
                "terminal",
            },
        )
        self.assertEqual(
            prompt_observation["requester_private_observation"]["private"],
            self.private_observation["private"],
        )
        self.assertEqual(len(llm.prompts), 1)

    def test_unexpected_public_fields_are_rejected_before_model_call(self) -> None:
        public = dict(self.public_observation)
        public["entity_to_piece"] = "PIECE_MAPPING_SENTINEL"
        llm = _FakeKaggleLLM(self.valid_response)

        with self.assertRaisesRegex(ValueError, "(?i)public observation"):
            self._invoke(llm, public_observation=public)

        self.assertEqual(llm.prompts, [])

    def test_unexpected_nested_public_field_is_rejected_before_model_call(self) -> None:
        public = dict(self.public_observation)
        public["legal_actions"] = dict(public["legal_actions"])
        public["legal_actions"]["piece_id"] = 0
        llm = _FakeKaggleLLM(self.valid_response)

        with self.assertRaisesRegex(ValueError, "legal_actions"):
            self._invoke(llm, public_observation=public)

        self.assertEqual(llm.prompts, [])

    def test_unexpected_private_field_is_rejected_before_model_call(self) -> None:
        private = dict(self.private_observation)
        private["private"] = dict(private["private"])
        private["private"]["opponent_secret"] = "PRIVATE_OPPONENT_SENTINEL"
        llm = _FakeKaggleLLM(self.valid_response)

        with self.assertRaisesRegex(ValueError, "(?i)private observation"):
            self._invoke(llm, private_observation=private)

        self.assertEqual(llm.prompts, [])

    def test_opponent_private_observation_is_rejected_before_model_call(self) -> None:
        opponent_controller = Phase0Controller(
            self.domain_adapter,
            mode="classic",
            instance=self.instance,
            starting_player="player_2",
        )
        opponent_private = opponent_controller.private_observation("player_2")
        llm = _FakeKaggleLLM(self.valid_response)

        with self.assertRaisesRegex(ValueError, "(?i)requester"):
            self._invoke(llm, private_observation=opponent_private)

        self.assertEqual(llm.prompts, [])

    def test_missing_or_mismatched_private_requester_is_rejected(self) -> None:
        missing_owner = dict(self.private_observation)
        missing_owner.pop("requester", None)
        mismatched_owner = dict(self.private_observation)
        mismatched_owner["requester"] = "player_2"

        for case, private in (
            ("missing", missing_owner),
            ("mismatched", mismatched_owner),
        ):
            with self.subTest(case=case):
                llm = _FakeKaggleLLM(self.valid_response)
                with self.assertRaisesRegex(ValueError, "(?i)requester"):
                    self._invoke(llm, private_observation=private)
                self.assertEqual(llm.prompts, [])

    def test_deterministic_public_uuid_is_accepted_in_final_prompt(self) -> None:
        public = dict(self.public_observation)
        private = dict(self.private_observation)
        replacements = {
            entry["entity_id"]: UUID(int=index + 1, version=4).hex
            for index, entry in enumerate(public["public_entities"])
        }

        def remap_observation_ids(observation: dict[str, Any]) -> None:
            entities = observation["public_entities"]
            for entity in entities:
                entity_id = replacements[entity["entity_id"]]
                entity["entity_id"] = entity_id
                entity["label"] = entity_id
            observation["board"] = [
                None if entity_id is None else replacements[entity_id]
                for entity_id in observation["board"]
            ]
            observation["available_entities"] = [
                replacements[entity_id]
                for entity_id in observation["available_entities"]
            ]
            if observation["selected_entity"] is not None:
                observation["selected_entity"] = replacements[
                    observation["selected_entity"]
                ]
            legal_actions = observation["legal_actions"]
            if legal_actions["kind"] == "select_entity":
                legal_actions["entity_ids"] = [
                    replacements[entity_id]
                    for entity_id in legal_actions["entity_ids"]
                ]
            for action in observation["history"]:
                if "entity_id" in action:
                    action["entity_id"] = replacements[action["entity_id"]]

        remap_observation_ids(public)
        remap_observation_ids(private)
        legal_entity_id = public["legal_actions"]["entity_ids"][0]
        llm = _FakeKaggleLLM(
            json.dumps({"kind": "select_entity", "entity_id": legal_entity_id})
        )

        action = self._invoke(
            llm,
            public_observation=public,
            private_observation=private,
        )

        prompt = llm.prompts[0]
        prompt_observation = json.loads(prompt.split("Observation JSON:\n", 1)[1])
        self.assertEqual(action["entity_id"], legal_entity_id)
        self.assertEqual(
            prompt_observation["public_observation"]["legal_actions"]["entity_ids"][0],
            legal_entity_id,
        )
        self.assertIn(legal_entity_id, prompt)
        self.assertEqual(len(llm.prompts), 1)

    def test_restricted_mapping_is_rejected_before_model_call(self) -> None:
        public = dict(self.public_observation)
        public.update(
            {
                "engine_state_snapshot": {"piece_id": 0},
                "entity_to_piece": {"opaque-id": 0},
                "feature_to_bit": {"f0": 0},
            }
        )
        llm = _FakeKaggleLLM(self.valid_response)

        with self.assertRaisesRegex(ValueError, "(?i)public observation"):
            self._invoke(llm, public_observation=public)

        self.assertEqual(llm.prompts, [])

    def test_existing_agent_interface_is_unchanged(self) -> None:
        self.assertIs(KaggleAgentAdapter.get_action, AgentAdapter.get_action)
        self.assertEqual(
            inspect.signature(KaggleAgentAdapter.get_action),
            inspect.signature(AgentAdapter.get_action),
        )
        self.assertEqual(
            tuple(inspect.signature(AgentAdapter.get_action).parameters),
            ("self", "public_observation", "private_observation", "deadline", "event_log"),
        )
        self.assertEqual(KaggleAgentAdapter(_FakeKaggleLLM()).correction_attempts, 0)


if __name__ == "__main__":
    unittest.main()
