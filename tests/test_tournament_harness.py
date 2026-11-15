import json
from dataclasses import replace
import subprocess
import sys
import tempfile
import time
import unittest
import urllib.error
from pathlib import Path
from types import MappingProxyType, SimpleNamespace
from unittest.mock import patch
from uuid import UUID

from phase0_foundation import Phase0Controller, SyntheticAdapter, validate_audit_snapshot
from tournament_harness import (
    ActionProtocolError,
    AgentAdapter,
    ChatResult,
    DEESEEK_MODEL_TAG,
    GEMMA_MODEL_TAG,
    MODEL_TAGS,
    PILOT_MODEL_BY_PLAYER,
    MatchAgentFailure,
    OllamaChatClient,
    OllamaClientError,
    OpenCodeChatClient,
    OpenCodeClientError,
    TournamentRunner,
    _create_run_directory,
    _audit_replay_matches,
    model_connectivity_smoke_test,
    parse_action_response,
    _prompt_privacy_findings,
    project_public_observation,
    recursive_privacy_check,
    run_security_audit,
    write_pilot_artifacts,
)


class _Response:
    def __init__(self, body):
        self.body = body

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self, size=-1):
        return self.body[:size]


class _LegalActionClient:
    def __init__(self):
        self.messages = []

    def chat(self, messages, *, timeout=None):
        self.messages.append(messages)
        payload = json.loads(messages[1]["content"])
        legal = payload["public_observation"]["legal_actions"]
        if legal["kind"] == "select_entity":
            action = {"kind": "select_entity", "entity_id": legal["entity_ids"][0]}
        else:
            action = {"kind": "place_entity", "cell": legal["cells"][0]}
        content = json.dumps(action)
        return ChatResult(content, json.dumps({"message": {"content": content}}), 0.001)


class _FailingClient:
    def chat(self, messages, *, timeout=None):
        raise OllamaClientError("deliberate test failure", raw_response='{"error":"offline"}')


class _CountingSyntheticAdapter(SyntheticAdapter):
    def __init__(self):
        super().__init__()
        self.build_instance_calls = 0

    def build_instance(self, instance_id="synthetic_instance_0"):
        self.build_instance_calls += 1
        return super().build_instance(instance_id)


class TournamentHarnessTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.adapter = SyntheticAdapter()
        cls.instance = cls.adapter.build_instance()

    def test_action_parser_enforces_exact_schema(self):
        self.assertEqual(
            parse_action_response('{"kind":"select_entity","entity_id":"e01"}'),
            {"kind": "select_entity", "entity_id": "e01"},
        )
        for invalid in (
            "",
            "not json",
            '{"kind":"place_entity","cell":true}',
            '{"kind":"place_entity","cell":0,"player":"player_2"}',
            '{"kind":"place_entity","cell":0,"piece_id":3}',
            '{"kind":"place_entity","cell":0,"cell":1}',
        ):
            with self.subTest(invalid=invalid), self.assertRaises(ActionProtocolError):
                parse_action_response(invalid)

    def test_ollama_client_parses_bounded_non_streaming_response(self):
        body = b'{"message":{"content":"{\\"status\\":\\"ok\\"}"}}'
        captured = {}

        def opener(request, timeout):
            captured["body"] = request.data
            captured["timeout"] = timeout
            return _Response(body)

        client = OllamaChatClient(
            GEMMA_MODEL_TAG,
            opener=opener,
        )
        result = client.chat([{"role": "user", "content": "hello"}])
        request_payload = json.loads(captured["body"])
        self.assertEqual(result.content, '{"status":"ok"}')
        self.assertFalse(request_payload["stream"])
        self.assertEqual(request_payload["model"], GEMMA_MODEL_TAG)
        self.assertEqual(captured["timeout"], client.timeout)

    def test_ollama_client_reports_http_errors_and_response_overflow(self):
        def http_error_opener(request, timeout):
            raise urllib.error.HTTPError(
                request.full_url,
                404,
                "Not Found",
                {},
                None,
            )

        with self.assertRaisesRegex(OllamaClientError, "HTTP 404"):
            OllamaChatClient(GEMMA_MODEL_TAG, opener=http_error_opener).chat([])

        client = OllamaChatClient(
            GEMMA_MODEL_TAG,
            max_response_bytes=4,
            opener=lambda request, timeout: _Response(b"12345"),
        )
        with self.assertRaisesRegex(OllamaClientError, "size limit"):
            client.chat([])

    def test_ollama_client_reports_timeout_and_model_errors(self):
        def timeout_opener(request, timeout):
            raise urllib.error.URLError(TimeoutError("timed out"))

        with self.assertRaisesRegex(OllamaClientError, "request failed"):
            OllamaChatClient(GEMMA_MODEL_TAG, opener=timeout_opener).chat([])

        model_error = _Response(b'{"error":"model unavailable"}')
        with self.assertRaisesRegex(OllamaClientError, "model error"):
            OllamaChatClient(
                GEMMA_MODEL_TAG,
                opener=lambda request, timeout: model_error,
            ).chat([])

    def test_opencode_client_uses_fresh_tool_disabled_sessions(self):
        requests = []

        def process_runner(arguments, **kwargs):
            agent = Path(kwargs["cwd"]) / ".opencode" / "agents" / "quarto-player.md"
            agent_text = agent.read_text(encoding="utf-8")
            self.assertIn('action: "*"', agent_text)
            self.assertIn('resource: "*"', agent_text)
            self.assertIn("effect: deny", agent_text)
            self.assertEqual(arguments[1:8], [
                "run",
                "--standalone",
                "--model",
                DEESEEK_MODEL_TAG,
                "--agent",
                "quarto-player",
                "--format",
            ])
            self.assertNotEqual(Path(kwargs["cwd"]), Path.cwd())
            requests.append((arguments, kwargs["cwd"]))
            event = json.dumps({
                "type": "text",
                "part": {"type": "text", "text": '{"kind":"select_entity","entity_id":"e00"}'},
            })
            return SimpleNamespace(returncode=0, stdout=event, stderr="")

        client = OpenCodeChatClient(
            DEESEEK_MODEL_TAG,
            executable=sys.executable,
            process_runner=process_runner,
        )
        messages = [
            {"role": "system", "content": "No tools. Return a JSON action."},
            {"role": "user", "content": '{"owned_features":["f0","f1"]}'},
        ]
        first = client.chat(messages)
        second = client.chat(messages)

        self.assertEqual(first.content, '{"kind":"select_entity","entity_id":"e00"}')
        self.assertIsNotNone(first.session_id)
        first_session_id = requests[0][0][requests[0][0].index("--session") + 1]
        self.assertTrue(first_session_id.startswith("ses"))
        self.assertEqual(first_session_id, first.session_id)
        self.assertNotEqual(first.session_id, second.session_id)
        self.assertNotEqual(requests[0][1], requests[1][1])
        self.assertEqual(
            requests[0][0][requests[0][0].index("--session") + 1],
            first.session_id,
        )

    def test_opencode_client_preserves_structured_provider_errors(self):
        error_event = json.dumps({
            "type": "error",
            "error": {
                "type": "provider.free-limit",
                "status": 429,
                "message": "Free usage limit reached.",
            },
        })
        client = OpenCodeChatClient(
            DEESEEK_MODEL_TAG,
            executable=sys.executable,
            process_runner=lambda arguments, **kwargs: SimpleNamespace(
                returncode=1,
                stdout=error_event,
                stderr="",
            ),
        )

        with self.assertRaisesRegex(
            OpenCodeClientError,
            "provider.free-limit: 429: Free usage limit reached",
        ) as raised:
            client.chat([
                {"role": "system", "content": "Return JSON only."},
                {"role": "user", "content": '{"status":"ok"}'},
            ])

        self.assertEqual(raised.exception.raw_response, error_event)

    def test_opencode_client_reports_request_timeout(self):
        def timeout_runner(arguments, **kwargs):
            raise subprocess.TimeoutExpired(arguments, kwargs["timeout"], output="partial")

        client = OpenCodeChatClient(
            DEESEEK_MODEL_TAG,
            executable=sys.executable,
            process_runner=timeout_runner,
        )

        with self.assertRaisesRegex(OpenCodeClientError, "timed out") as raised:
            client.chat([
                {"role": "system", "content": "Return JSON only."},
                {"role": "user", "content": '{"status":"ok"}'},
            ])

        self.assertEqual(raised.exception.raw_response, "partial")

    def test_connectivity_smoke_uses_provider_message_contract(self):
        class SmokeClient:
            def __init__(self, provider):
                self.model_provider = provider
                self.messages = None

            def chat(self, messages):
                self.messages = messages
                return ChatResult(
                    '{"status":"ok"}',
                    '{"type":"text","part":{"text":"{\\"status\\":\\"ok\\"}"}}',
                    0.001,
                )

        clients = {
            DEESEEK_MODEL_TAG: SmokeClient("opencode"),
            GEMMA_MODEL_TAG: SmokeClient("ollama"),
        }
        report = model_connectivity_smoke_test(clients)

        self.assertEqual(report["status"], "passed")
        for index, (model, client) in enumerate(clients.items()):
            self.assertEqual(
                [message["role"] for message in client.messages],
                ["system", "user"],
            )
            self.assertNotIn("private", json.dumps(client.messages).lower())
            self.assertEqual(report["models"][index]["model"], model)
            self.assertEqual(
                report["models"][index]["provider"],
                "opencode" if model == DEESEEK_MODEL_TAG else "ollama",
            )

    def test_prompt_projection_and_private_payload_are_isolated(self):
        controller = Phase0Controller(self.adapter, mode="classic", instance=self.instance)
        public = controller.public_observation("player_1")
        player_1 = controller.private_observation("player_1")
        player_2_controller = Phase0Controller(
            self.adapter,
            mode="classic",
            instance=self.instance,
            starting_player="player_2",
        )
        player_2 = player_2_controller.private_observation("player_2")
        messages = AgentAdapter(_LegalActionClient()).build_messages(public, player_1)
        prompt = json.loads(messages[1]["content"])
        projected = prompt["public_observation"]

        self.assertEqual(set(projected), {
            "mode", "phase", "current_player", "board", "available_entities",
            "selected_entity", "legal_actions", "history", "terminal",
        })
        self.assertNotIn("public_entities", projected)
        self.assertEqual(
            prompt["requester_private_observation"],
            {"private": player_1["private"]},
        )
        self.assertFalse(
            set(player_1["private"]["owned_features"])
            & set(player_2["private"]["owned_features"])
        )
        self.assertEqual(project_public_observation(public), projected)

    def test_agent_adapter_rejects_an_action_for_the_wrong_phase(self):
        class WrongPhaseClient:
            def chat(self, messages, *, timeout=None):
                content = '{"kind":"place_entity","cell":0}'
                return ChatResult(content, content, 0.001)

        controller = Phase0Controller(self.adapter, mode="classic", instance=self.instance)
        with self.assertRaises(MatchAgentFailure):
            AgentAdapter(WrongPhaseClient(), correction_attempts=0).get_action(
                controller.public_observation("player_1"),
                controller.private_observation("player_1"),
                deadline=10**12,
                event_log=[],
            )

    def test_security_preflight_passes_synthetic_boundary_checks(self):
        report = run_security_audit()
        self.assertEqual(report["status"], "passed", report["checks"])
        self.assertTrue(all(check["passed"] for check in report["checks"]))
        check_names = {check["check"] for check in report["checks"]}
        self.assertTrue({
            "restricted_values_available",
            "public_audit_excludes_restricted_values",
            "player_1_prompt_excludes_restricted_values",
            "player_2_prompt_excludes_restricted_values",
        }.issubset(check_names))

    def test_privacy_check_respects_short_token_boundaries_inside_uuids(self):
        self.assertEqual(
            recursive_privacy_check(
                {"opaque_entity_id": UUID("f0" + "0" * 30, version=4).hex},
                forbidden_values=("f0",),
            ),
            [],
        )
        self.assertEqual(
            recursive_privacy_check(
                {"owned_features": ["f0"]},
                forbidden_values=("f0",),
            ),
            ["forbidden_value"],
        )
        self.assertEqual(
            recursive_privacy_check(
                {"note": "The private feature is f0."},
                forbidden_values=("f0",),
            ),
            ["forbidden_value"],
        )

    def test_privacy_check_detects_32_character_hex_secret_alone_and_in_text(self):
        secret = "deadbeefcafebabefeedface01234567"
        self.assertEqual(len(secret), 32)
        self.assertEqual(
            recursive_privacy_check(
                {"secret": secret},
                forbidden_values=(secret,),
            ),
            ["forbidden_value"],
        )
        self.assertEqual(
            recursive_privacy_check(
                {"note": f"prefix [{secret}] suffix"},
                forbidden_values=(secret,),
            ),
            ["forbidden_value"],
        )

    def test_privacy_check_matches_low_entropy_restricted_values_exactly(self):
        self.assertEqual(
            recursive_privacy_check(
                {"copied_signature": 11},
                forbidden_exact_values=(11,),
            ),
            ["forbidden_value"],
        )
        self.assertEqual(
            recursive_privacy_check(
                {"copied_signature": "11"},
                forbidden_exact_values=(11, "11"),
            ),
            ["forbidden_value"],
        )
        self.assertEqual(
            recursive_privacy_check(
                {"public_feature_id": "fma:chroma_cqt:median:11"},
                forbidden_exact_values=(11,),
            ),
            [],
        )

    def test_privacy_check_detects_source_id_inside_identifier_text(self):
        source_id = "53194"
        findings = recursive_privacy_check(
            {
                "nested": [
                    {"annotation": "track_53194_hidden"},
                ],
            },
            forbidden_values=(source_id,),
        )

        self.assertEqual(findings, ["forbidden_value"])
        self.assertNotIn(source_id, " ".join(findings))

    def test_privacy_check_scans_raw_serialized_prompt_representation(self):
        source_id = "53194"
        controller = Phase0Controller(self.adapter, mode="classic", instance=self.instance)
        public = controller.public_observation("player_1")
        private = controller.private_observation("player_1")
        messages = AgentAdapter(_LegalActionClient()).build_messages(public, private)
        content = messages[1]["content"]
        messages[1]["content"] = content.replace(
            '"phase":"select"',
            '"phase":"track_53194_hidden","phase":"select"',
            1,
        )

        findings = _prompt_privacy_findings(
            messages,
            forbidden_values=(source_id,),
        )

        self.assertEqual(findings, ["forbidden_value"])
        self.assertEqual(
            json.loads(messages[1]["content"])["public_observation"]["phase"],
            "select",
        )
        self.assertNotIn(source_id, " ".join(findings))

    def test_privacy_check_public_uuid_does_not_suppress_a_different_hex_secret(self):
        public_uuid = UUID("f0" + "0" * 30, version=4).hex
        secret = "00112233445566778899aabbccddeeff"
        self.assertNotEqual(public_uuid, secret)
        self.assertEqual(
            recursive_privacy_check(
                {
                    "public_uuid": public_uuid,
                    "secret": secret,
                },
                forbidden_values=("f0", secret),
            ),
            ["forbidden_value"],
        )

    def test_privacy_check_detects_restricted_values_in_allowed_and_nested_fields(self):
        secret = "private-sentinel-feature-7f38c9"
        controller = Phase0Controller(self.adapter, mode="classic", instance=self.instance)

        permitted_field = controller.public_observation("player_1")
        permitted_field["mode"] = secret
        self.assertEqual(
            recursive_privacy_check(permitted_field, forbidden_values=(secret,)),
            ["forbidden_value"],
        )

        nested_dictionary = controller.public_observation("player_1")
        nested_dictionary["history"] = [{"metadata": {"annotation": secret}}]
        self.assertEqual(
            recursive_privacy_check(nested_dictionary, forbidden_values=(secret,)),
            ["forbidden_value"],
        )

        nested_list = controller.public_observation("player_1")
        nested_list["history"] = [{"metadata": ["ordinary", secret]}]
        self.assertEqual(
            recursive_privacy_check(nested_list, forbidden_values=(secret,)),
            ["forbidden_value"],
        )

    def test_privacy_check_detects_restricted_values_in_public_audit_artifacts(self):
        secret = "53194"
        controller = Phase0Controller(self.adapter, mode="classic", instance=self.instance)
        public_audit = dict(controller.get_read_only_audit_view().public_audit)
        public_audit["metadata"] = {"label": "track_53194_hidden"}

        findings = recursive_privacy_check(public_audit, forbidden_values=(secret,))

        self.assertEqual(findings, ["forbidden_value"])
        self.assertNotIn(secret, " ".join(findings))

    def test_privacy_check_detects_copied_restricted_structures(self):
        restricted_mapping = {"opaque-entity": 7}
        findings = recursive_privacy_check(
            {"metadata": {"copied_mapping": dict(restricted_mapping)}},
            forbidden_structures=(restricted_mapping,),
        )

        self.assertEqual(findings, ["forbidden_structure"])

    def test_prompt_privacy_check_inspects_serialized_agent_payload(self):
        secret = "private-sentinel-prompt-c2d654"
        controller = Phase0Controller(self.adapter, mode="classic", instance=self.instance)
        public = controller.public_observation("player_1")
        private = controller.private_observation("player_1")
        messages = AgentAdapter(_LegalActionClient()).build_messages(public, private)
        payload = json.loads(messages[1]["content"])
        payload["public_observation"]["phase"] = secret
        messages[1]["content"] = json.dumps(payload, separators=(",", ":"))

        findings = _prompt_privacy_findings(messages, forbidden_values=(secret,))

        self.assertEqual(findings, ["forbidden_value"])
        self.assertNotIn(secret, " ".join(findings))

    def test_security_preflight_detects_restricted_values_in_actual_agent_prompt(self):
        original_build_messages = AgentAdapter.build_messages

        def leaking_build_messages(agent, public_observation, private_observation):
            messages = original_build_messages(agent, public_observation, private_observation)
            if private_observation["requester"] == "player_1":
                payload = json.loads(messages[1]["content"])
                payload["public_observation"]["phase"] = "f2"
                messages[1]["content"] = json.dumps(payload, separators=(",", ":"))
            return messages

        with patch.object(AgentAdapter, "build_messages", leaking_build_messages):
            report = run_security_audit()

        checks = {check["check"]: check["passed"] for check in report["checks"]}
        self.assertEqual(report["status"], "failed")
        self.assertFalse(checks["player_1_prompt_excludes_restricted_values"])
        self.assertNotIn("f2", json.dumps(report))

    def test_security_preflight_detects_restricted_value_in_actual_public_observation(self):
        original_build_messages = AgentAdapter.build_messages

        def leaking_build_messages(agent, public_observation, private_observation):
            messages = original_build_messages(agent, public_observation, private_observation)
            if private_observation["requester"] == "player_1":
                public_observation["phase"] = "f2"
            return messages

        with patch.object(AgentAdapter, "build_messages", leaking_build_messages):
            report = run_security_audit()

        checks = {check["check"]: check["passed"] for check in report["checks"]}
        self.assertEqual(report["status"], "failed")
        self.assertFalse(checks["public_observation_excludes_internal_state"])
        self.assertNotIn("f2", json.dumps(report))

    def test_security_preflight_detects_restricted_values_in_actual_public_audit(self):
        original_get_audit = Phase0Controller.get_read_only_audit_view

        def leaking_audit(controller):
            snapshot = original_get_audit(controller)
            public_audit = dict(snapshot.public_audit)
            public_audit["mode"] = "f2"
            return replace(
                snapshot,
                public_audit=MappingProxyType(public_audit),
            )

        with patch.object(Phase0Controller, "get_read_only_audit_view", leaking_audit):
            report = run_security_audit()

        checks = {check["check"]: check["passed"] for check in report["checks"]}
        self.assertEqual(report["status"], "failed")
        self.assertFalse(checks["public_audit_excludes_restricted_values"])
        self.assertNotIn("f2", json.dumps(report))

    def test_security_preflight_fails_closed_when_restricted_inputs_are_missing(self):
        original_get_audit = Phase0Controller.get_read_only_audit_view

        def missing_restricted_data(controller):
            snapshot = original_get_audit(controller)
            return replace(
                snapshot,
                restricted_evaluator_data=MappingProxyType({}),
            )

        with patch.object(
            Phase0Controller,
            "get_read_only_audit_view",
            missing_restricted_data,
        ):
            report = run_security_audit()

        checks = {check["check"]: check["passed"] for check in report["checks"]}
        self.assertEqual(report["status"], "failed")
        self.assertFalse(checks["restricted_values_available"])

    def test_valid_public_identifiers_metadata_and_placement_cells_are_not_leaks(self):
        controller = Phase0Controller(self.adapter, mode="classic", instance=self.instance)
        public = controller.public_observation("player_1")
        controller.submit_agent_action(
            "player_1",
            {"kind": "select_entity", "entity_id": public["legal_actions"]["entity_ids"][0]},
        )
        public = controller.public_observation("player_2")
        private = controller.private_observation("player_2")
        messages = AgentAdapter(_LegalActionClient()).build_messages(public, private)
        values = ("e00", "f0", "0", "1")

        self.assertEqual(recursive_privacy_check(public, forbidden_values=values), [])
        self.assertEqual(_prompt_privacy_findings(messages, forbidden_values=values), [])

    def test_public_cell_positions_are_not_signature_leaks(self):
        public_history = [
            {"kind": "place_entity", "player": "player_1", "cell": cell}
            for cell in range(16)
        ]
        public_data = {
            "history": public_history,
            "legal_actions": {"kind": "place_entity", "cells": list(range(16))},
            "replay_schema_version": 1,
            "public_id": UUID("12345678-1234-4234-8234-123456789abc").hex,
            "metadata": "ordinary public metadata",
        }

        self.assertEqual(
            recursive_privacy_check(
                public_data,
                forbidden_values=("53194",),
                forbidden_exact_values=tuple(range(16)),
            ),
            [],
        )
        self.assertEqual(
            recursive_privacy_check(
                {"signature": 11},
                forbidden_exact_values=(11,),
            ),
            ["forbidden_key", "forbidden_value"],
        )
        self.assertEqual(
            recursive_privacy_check(
                {"history": [{"cell": "11"}]},
                forbidden_exact_values=("11",),
            ),
            ["forbidden_value"],
        )

    def test_complete_match_validates_audit_and_replay(self):
        clients = {model: _LegalActionClient() for model in MODEL_TAGS}
        result = TournamentRunner(clients, wall_clock_timeout=20).run_match(
            self.adapter,
            self.instance,
            {"player_1": MODEL_TAGS[0], "player_2": MODEL_TAGS[1]},
        )
        self.assertEqual(result.status, "completed", result.failure)
        self.assertLessEqual(result.action_count, 32)
        self.assertIn(result.outcome, ("win", "draw"))
        self.assertTrue(result.audit_valid)
        self.assertTrue(result.replay_valid)
        self.assertIsNotNone(result.restricted_log["audit_snapshot"])
        for event in result.restricted_log["events"]:
            self.assertEqual(event["controller_validation"], "passed")

    def test_runner_rejects_deadline_expiring_before_action_submission(self):
        original_get_decision = AgentAdapter.get_decision

        def delayed_decision(agent, *args, deadline, **kwargs):
            decision = original_get_decision(
                agent,
                *args,
                deadline=deadline,
                **kwargs,
            )
            time.sleep(max(0.0, deadline - time.monotonic()) + 0.02)
            return decision

        clients = {model: _LegalActionClient() for model in MODEL_TAGS}
        runner = TournamentRunner(clients, wall_clock_timeout=0.25)
        with patch.object(AgentAdapter, "get_decision", delayed_decision):
            result = runner.run_match(
                self.adapter,
                self.instance,
                {"player_1": MODEL_TAGS[0], "player_2": MODEL_TAGS[1]},
            )

        self.assertEqual(result.status, "agent_failure")
        self.assertEqual(result.action_count, 0)
        self.assertFalse(result.audit_valid)
        self.assertFalse(result.replay_valid)
        self.assertEqual(
            result.restricted_log["events"][0]["controller_validation"],
            "deadline_expired",
        )

    def test_start_player_pair_keeps_model_identity_ownership_and_replay_fixed(self):
        clients = {model: _LegalActionClient() for model in MODEL_TAGS}
        adapter = _CountingSyntheticAdapter()
        instance = adapter.build_instance()
        build_calls = adapter.build_instance_calls
        results = TournamentRunner(clients, wall_clock_timeout=20).run_two_match_pilot(
            adapter,
            instance,
        )
        self.assertEqual([result.assignments for result in results], [PILOT_MODEL_BY_PLAYER] * 2)
        self.assertEqual(
            [result.public_dict()["starting_player"] for result in results],
            ["player_1", "player_2"],
        )
        self.assertEqual(adapter.build_instance_calls, build_calls)
        self.assertEqual(len({result.match_id for result in results}), 2)
        self.assertEqual({result.restricted_log["instance_id"] for result in results}, {instance.instance_id})
        self.assertTrue(all(result.status == "completed" for result in results))
        self.assertTrue(all(result.audit_valid and result.replay_valid for result in results))

        for result in results:
            audit = result.restricted_log["audit_snapshot"]
            ownership = audit["restricted_evaluator_data"]["private_feature_ownership"]
            self.assertEqual(
                ownership,
                {"player_1": ["f0", "f1"], "player_2": ["f2", "f3"]},
            )
        for model, owned, opponent_owned in (
            (DEESEEK_MODEL_TAG, {"f0", "f1"}, {"f2", "f3"}),
            (GEMMA_MODEL_TAG, {"f2", "f3"}, {"f0", "f1"}),
        ):
            self.assertTrue(clients[model].messages)
            for messages in clients[model].messages:
                prompt = json.loads(messages[1]["content"])
                self.assertEqual(
                    set(prompt["requester_private_observation"]["private"]["owned_features"]),
                    owned,
                )
                self.assertFalse(opponent_owned & set(json.dumps(prompt)))
                self.assertFalse({
                    "entity_to_piece",
                    "piece_to_entity",
                    "feature_to_bit",
                    "engine_state",
                    "engine_state_snapshot",
                    "restricted_evaluator_data",
                } & set(prompt["public_observation"]))

        failing_clients = {model: _FailingClient() for model in MODEL_TAGS}
        failed = TournamentRunner(failing_clients).run_match(
            self.adapter,
            self.instance,
            PILOT_MODEL_BY_PLAYER,
        )
        self.assertEqual(failed.status, "agent_failure")
        self.assertIsNone(failed.outcome)
        self.assertIsNone(failed.winner)
        self.assertIn("raw_response", failed.restricted_log["events"][0])

    def test_audit_rejects_public_history_tampering(self):
        controller = Phase0Controller(
            self.adapter,
            mode="classic",
            instance=self.instance,
            starting_player="player_2",
        )
        while not controller.session.engine_state.is_terminal:
            observation = controller.public_observation("player_1")
            requester = observation["current_player"]
            if observation["phase"] == "select":
                action = {
                    "kind": "select_entity",
                    "entity_id": observation["legal_actions"]["entity_ids"][0],
                }
            else:
                action = {
                    "kind": "place_entity",
                    "cell": observation["legal_actions"]["cells"][0],
                }
            controller.submit_agent_action(requester, action)

        snapshot = controller.get_read_only_audit_view()
        self.assertTrue(validate_audit_snapshot(snapshot))
        self.assertTrue(_audit_replay_matches(snapshot))

        public_audit = dict(snapshot.public_audit)
        public_history = [dict(event) for event in public_audit["public_history"]]
        public_history[0]["entity_id"] = "tampered_entity"
        public_audit["public_history"] = tuple(
            MappingProxyType(event) for event in public_history
        )
        tampered = replace(snapshot, public_audit=MappingProxyType(public_audit))

        self.assertFalse(validate_audit_snapshot(tampered))
        self.assertFalse(_audit_replay_matches(tampered))

    def test_artifacts_keep_restricted_logs_separate(self):
        results = []
        with tempfile.TemporaryDirectory() as output:
            write_pilot_artifacts(
                output,
                results,
                {"status": "passed", "checks": []},
                {"status": "passed", "models": []},
            )
            root = Path(output)
            public = json.loads((root / "public_report.json").read_text(encoding="utf-8"))
            restricted = json.loads((root / "restricted_match_log.json").read_text(encoding="utf-8"))
            self.assertEqual(public["connectivity_smoke_test"]["status"], "passed")
            self.assertNotIn("events", public)
            self.assertIn("handling", restricted)
            self.assertIn("may retain", public["privacy_policy"])
            self.assertNotIn("f0", json.dumps(public))

            with self.assertRaises(FileExistsError):
                write_pilot_artifacts(
                    output,
                    results,
                    {"status": "passed", "checks": []},
                    {"status": "passed", "models": []},
                )

    def test_each_pilot_run_gets_a_new_output_directory(self):
        with tempfile.TemporaryDirectory() as output:
            first = _create_run_directory(output)
            second = _create_run_directory(output)
            self.assertNotEqual(first, second)
            self.assertTrue(first.is_dir())
            self.assertTrue(second.is_dir())


if __name__ == "__main__":
    unittest.main()
