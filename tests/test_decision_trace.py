import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from uuid import UUID

from decision_trace import (
    DECISION_TRACE_SCHEMA_VERSION,
    DecisionTraceRecord,
    JsonlDecisionTraceWriter,
)
from phase0_foundation import MatchSession, Phase0Controller, SyntheticAdapter
from tournament_harness import (
    AgentAdapter,
    ChatResult,
    MODEL_TAGS,
    TournamentRunner,
)


class _TraceClient:
    model_provider = "synthetic-provider"
    model = "synthetic-model"

    def __init__(self, *, explain=False):
        self.explain = explain
        self.messages = []

    def chat(self, messages, *, timeout=None):
        self.messages.append(messages)
        prompt = json.loads(messages[1]["content"])
        legal = prompt["public_observation"]["legal_actions"]
        if legal["kind"] == "select_entity":
            action = {"kind": "select_entity", "entity_id": legal["entity_ids"][0]}
        else:
            action = {"kind": "place_entity", "cell": legal["cells"][0]}
        if self.explain:
            content = json.dumps({
                "action": action,
                "candidate_hypotheses": ["candidate one"],
                "evidence_references": ["observation.board"],
                "decision_explanation": "Selected a legal candidate.",
                "declared_confidence": 0.75,
            })
        else:
            content = json.dumps(action)
        return ChatResult(
            content=content,
            raw_response=content,
            duration_seconds=0.001,
            input_tokens=12,
            output_tokens=4,
        )


class _FailingTraceWriter:
    def write(self, record):
        raise OSError("trace storage unavailable")


class DecisionTraceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.adapter = SyntheticAdapter()
        cls.instance = cls.adapter.build_instance()
        cls.assignments = {"player_1": MODEL_TAGS[0], "player_2": MODEL_TAGS[1]}

    def _clients(self, *, explain=False):
        return {
            model: _TraceClient(explain=explain)
            for model in MODEL_TAGS
        }

    def _run_match(self, clients, **kwargs):
        return TournamentRunner(clients, wall_clock_timeout=20).run_match(
            self.adapter,
            self.instance,
            self.assignments,
            **kwargs,
        )

    def test_action_only_agent_creates_trace_without_fabricated_explanation(self):
        result = self._run_match(self._clients())

        self.assertEqual(result.status, "completed", result.failure)
        traces = result.restricted_log["decision_traces"]
        self.assertTrue(traces)
        self.assertNotIn("decision_explanation", traces[0])
        self.assertNotIn("candidate_hypotheses", traces[0])
        self.assertNotIn("evidence_references", traces[0])
        self.assertNotIn("declared_confidence", traces[0])

    def test_existing_agent_adapter_action_interface_remains_action_only(self):
        controller = Phase0Controller(
            self.adapter,
            instance=self.instance,
        )
        action = AgentAdapter(_TraceClient()).get_action(
            controller.public_observation("player_1"),
            controller.private_observation("player_1"),
            deadline=10**12,
            event_log=[],
        )

        self.assertEqual(set(action), {"kind", "entity_id"})

    def test_structured_agent_explanation_is_captured_as_reported(self):
        result = self._run_match(self._clients(explain=True))

        trace = result.restricted_log["decision_traces"][0]
        self.assertEqual(trace["candidate_hypotheses"], ["candidate one"])
        self.assertEqual(trace["evidence_references"], ["observation.board"])
        self.assertEqual(trace["decision_explanation"], "Selected a legal candidate.")
        self.assertEqual(trace["declared_confidence"], 0.75)

    def test_records_associate_match_turn_agent_observation_and_feedback(self):
        result = self._run_match(self._clients())
        traces = result.restricted_log["decision_traces"]

        self.assertEqual(traces[0]["match_id"], result.match_id)
        self.assertEqual([trace["turn_id"] for trace in traces], list(range(1, len(traces) + 1)))
        self.assertEqual(
            {trace["agent_id"] for trace in traces},
            {"player_1", "player_2"},
        )
        self.assertEqual(
            traces[0]["observation_snapshot"]["public"]["current_player"],
            traces[0]["agent_id"],
        )
        self.assertEqual(traces[0]["received_feedback"]["controller_validation"], "passed")
        self.assertFalse(
            traces[0]["received_feedback"]["delivered_to_acting_agent"]
        )
        self.assertEqual(
            traces[0]["received_feedback"]["post_action_public_observation"],
            result.restricted_log["events"][0]["post_action_public_observation"],
        )
        self.assertEqual(traces[0]["model_provider"], "synthetic-provider")
        self.assertEqual(traces[0]["model_name"], "synthetic-model")
        self.assertEqual(traces[0]["input_tokens"], 12)
        self.assertEqual(traces[0]["output_tokens"], 4)

    def test_observation_is_exact_prompt_projection_and_private_data_is_recipient_only(self):
        clients = self._clients()
        result = self._run_match(clients)
        expected_private = {
            "player_1": list(self.instance.feature_ids[:2]),
            "player_2": list(self.instance.feature_ids[2:4]),
        }
        all_private_features = set(self.instance.feature_ids)

        for trace in result.restricted_log["decision_traces"]:
            player = trace["agent_id"]
            matching_client = clients[self.assignments[player]]
            snapshot = trace["observation_snapshot"]
            matching_prompts = [
                json.loads(messages[1]["content"])
                for messages in matching_client.messages
                if json.loads(messages[1]["content"])["public_observation"]["current_player"]
                == player
            ]
            self.assertIn(
                snapshot["public"],
                [prompt["public_observation"] for prompt in matching_prompts],
            )
            self.assertIn(
                snapshot["private"],
                [
                    prompt["requester_private_observation"]["private"]
                    for prompt in matching_prompts
                ],
            )
            self.assertEqual(
                snapshot["private"]["owned_features"],
                expected_private[player],
            )
            self.assertEqual(set(snapshot), {"public", "private"})
            trace_values = set()

            def collect_strings(value):
                if isinstance(value, dict):
                    for key, child in value.items():
                        trace_values.add(key)
                        collect_strings(child)
                elif isinstance(value, list):
                    for child in value:
                        collect_strings(child)
                elif isinstance(value, str):
                    trace_values.add(value)

            collect_strings(trace)
            for feature_id in all_private_features - set(expected_private[player]):
                self.assertNotIn(feature_id, trace_values)

    def test_trace_round_trip_and_missing_metadata(self):
        record = DecisionTraceRecord(
            match_id="match-1",
            turn_id=1,
            agent_id="player_1",
            observation_snapshot={"public": {"phase": "select"}, "private": {}},
            selected_action={"kind": "select_entity", "entity_id": "e0"},
            timestamp="2026-11-10T00:00:00+00:00",
        )

        encoded = record.to_json()
        restored = DecisionTraceRecord.from_json(encoded)

        self.assertEqual(restored.to_dict(), record.to_dict())
        self.assertEqual(restored.schema_version, DECISION_TRACE_SCHEMA_VERSION)
        self.assertNotIn("model_provider", restored.to_dict())
        self.assertNotIn("input_tokens", restored.to_dict())
        self.assertNotIn("decision_explanation", restored.to_dict())

    def test_jsonl_persistence_writes_machine_readable_records(self):
        clients = self._clients()
        with tempfile.TemporaryDirectory() as temporary_directory:
            trace_path = Path(temporary_directory) / "traces" / "match.jsonl"
            writer = JsonlDecisionTraceWriter(trace_path)
            result = self._run_match(clients, decision_trace_writer=writer)

            lines = trace_path.read_text(encoding="utf-8").splitlines()
            self.assertEqual(len(lines), result.action_count)
            restored = [DecisionTraceRecord.from_json(line) for line in lines]
            self.assertEqual(
                [record.match_id for record in restored],
                [result.match_id] * result.action_count,
            )
            self.assertTrue(
                all(event["trace_persistence"] == "written"
                    for event in result.restricted_log["events"])
            )

    def test_trace_write_failure_is_explicit_and_does_not_change_match_result(self):
        stable_test_ids = {
            entity_id: UUID(int=index + 1, version=4).hex
            for index, entity_id in enumerate(self.instance.entity_ids)
        }
        with patch.object(
            MatchSession,
            "_generate_public_entity_ids",
            staticmethod(lambda _entity_ids: stable_test_ids),
        ):
            baseline = self._run_match(self._clients())
            traced = self._run_match(
                self._clients(),
                decision_trace_writer=_FailingTraceWriter(),
            )

        self.assertEqual(traced.status, baseline.status)
        self.assertEqual(traced.outcome, baseline.outcome)
        self.assertEqual(traced.winner, baseline.winner)
        self.assertEqual(traced.action_count, baseline.action_count)
        self.assertEqual(
            traced.restricted_log["audit_snapshot"]["restricted_evaluator_data"]["engine_replay"],
            baseline.restricted_log["audit_snapshot"]["restricted_evaluator_data"]["engine_replay"],
        )
        self.assertEqual(
            len(traced.restricted_log["decision_trace_write_failures"]),
            traced.action_count,
        )
        self.assertTrue(
            all(
                event["trace_persistence"]["status"] == "failed"
                for event in traced.restricted_log["events"]
            )
        )


if __name__ == "__main__":
    unittest.main()
