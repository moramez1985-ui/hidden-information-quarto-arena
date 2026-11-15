import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from fma_pilot import PILOT_INSTANCE_ID, load_fma_pilot
import tournament_harness
from tournament_harness import (
    AgentAdapter,
    ChatResult,
    TournamentRunner,
    recursive_privacy_check,
    run_security_audit,
)


ROOT = Path(__file__).resolve().parents[1]
ARCHIVE_PATH = ROOT / "data" / "fma_metadata.zip"
MODEL_TAGS = ("offline-fake-model-a", "offline-fake-model-b")


class _LegalActionClient:
    def __init__(self) -> None:
        self.messages: list[list[dict[str, str]]] = []

    def chat(self, messages, *, timeout=None):
        self.messages.append(messages)
        payload = json.loads(messages[1]["content"])
        legal = payload["public_observation"]["legal_actions"]
        if legal["kind"] == "select_entity":
            action = {
                "kind": "select_entity",
                "entity_id": legal["entity_ids"][0],
            }
        else:
            action = {"kind": "place_entity", "cell": legal["cells"][0]}
        content = json.dumps(action)
        return ChatResult(content, json.dumps({"message": {"content": content}}), 0.001)


class _WrongPhaseClient:
    def chat(self, messages, *, timeout=None):
        content = '{"kind":"place_entity","cell":0}'
        return ChatResult(content, content, 0.001)


class FMAPilotTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        if not ARCHIVE_PATH.is_file():
            raise unittest.SkipTest("The already-available local FMA archive is required.")
        cls.pilot = load_fma_pilot(ARCHIVE_PATH)

    def test_persisted_candidate_reloads_without_reselection(self) -> None:
        pilot = self.pilot
        validation = pilot.validation_record["quartet_validation"]

        self.assertEqual(pilot.instance.instance_id, PILOT_INSTANCE_ID)
        self.assertEqual(pilot.instance.signature_map, dict(zip(
            pilot.instance.entity_ids,
            range(16),
        )))
        self.assertEqual(validation.id_level_count, 2)
        self.assertEqual(validation.structural_count, 2)
        self.assertTrue(validation.accepted)
        self.assertEqual(
            dict(pilot.restricted_source_ids),
            {entity_id: entity_id for entity_id in pilot.instance.entity_ids},
        )

    def test_pinned_archive_hash_is_enforced(self) -> None:
        with TemporaryDirectory() as temporary_directory:
            wrong_archive = Path(temporary_directory) / "wrong.zip"
            wrong_archive.write_bytes(b"not the approved FMA archive")
            with self.assertRaisesRegex(ValueError, "SHA-256"):
                load_fma_pilot(wrong_archive)

    def test_instance_artifact_rejects_extended_and_wrongly_typed_schema(self) -> None:
        original_artifact = json.loads(
            (ROOT / "fma_pilot_instance.json").read_text(encoding="utf-8")
        )
        with TemporaryDirectory() as temporary_directory:
            artifact_path = Path(temporary_directory) / "pilot.json"
            for mutation in (
                lambda artifact: artifact.update({"unexpected": "value"}),
                lambda artifact: artifact.update({"schema_version": True}),
            ):
                mutated = dict(original_artifact)
                mutation(mutated)
                artifact_path.write_text(json.dumps(mutated), encoding="utf-8")
                with self.assertRaisesRegex(ValueError, "identity or schema"):
                    load_fma_pilot(ARCHIVE_PATH, instance_path=artifact_path)

    def test_actual_fma_preflight_and_two_starting_player_matches(self) -> None:
        projected_phases: list[str] = []
        prompted_phases: list[str] = []
        original_projection = tournament_harness.project_public_observation
        original_build_messages = AgentAdapter.build_messages

        def track_projection(observation):
            projected_phases.append(observation["phase"])
            return original_projection(observation)

        def track_prompt(agent, observation, private_observation):
            prompted_phases.append(observation["phase"])
            return original_build_messages(agent, observation, private_observation)

        with (
            patch.object(
                tournament_harness,
                "project_public_observation",
                track_projection,
            ),
            patch.object(AgentAdapter, "build_messages", track_prompt),
        ):
            report = run_security_audit(
                adapter=self.pilot.adapter,
                instance=self.pilot.instance,
                restricted_source_ids=self.pilot.restricted_source_ids,
            )
        self.assertEqual(report["status"], "passed", report["checks"])
        self.assertTrue(all(check["passed"] for check in report["checks"]))
        phase_check = next(
            check
            for check in report["checks"]
            if check["check"] == "all_game_phases_are_audited"
        )
        self.assertEqual(
            phase_check["phases"],
            [
                "initial_select",
                "post_selection_place",
                "post_placement_select",
                "win_terminal",
                "draw_terminal",
            ],
        )
        self.assertEqual(phase_check["terminal_outcomes"], ["win", "draw"])
        self.assertTrue(phase_check["draw_terminal_has_no_winning_line"])
        self.assertTrue(phase_check["win_terminal_has_winning_line"])
        self.assertEqual(set(prompted_phases), {"select", "place"})
        self.assertEqual(set(projected_phases), {"select", "place", "terminal"})

        clients = {tag: _LegalActionClient() for tag in MODEL_TAGS}
        runner = TournamentRunner(
            clients,
            model_tags=MODEL_TAGS,
            wall_clock_timeout=20,
        )
        results = runner.run_two_match_pilot(
            self.pilot.adapter,
            self.pilot.instance,
            restricted_source_ids=self.pilot.restricted_source_ids,
        )

        self.assertEqual(len(results), 2)
        self.assertEqual(
            [result.public_dict()["starting_player"] for result in results],
            ["player_1", "player_2"],
        )
        self.assertEqual(
            [result.assignments for result in results],
            [
                {"player_1": MODEL_TAGS[0], "player_2": MODEL_TAGS[1]},
                {"player_1": MODEL_TAGS[0], "player_2": MODEL_TAGS[1]},
            ],
        )
        self.assertEqual(
            {result.restricted_log["instance_id"] for result in results},
            {PILOT_INSTANCE_ID},
        )
        self.assertEqual(len({result.match_id for result in results}), 2)
        self.assertTrue(all(result.status == "completed" for result in results))
        self.assertTrue(all(result.audit_valid and result.replay_valid for result in results))

        public_ids_by_match = []
        for result in results:
            restricted = result.restricted_log["audit_snapshot"]["restricted_evaluator_data"]
            crosswalk = restricted["public_entity_to_source_id"]
            self.assertEqual(len(crosswalk), 16)
            self.assertEqual(
                set(crosswalk.values()),
                set(self.pilot.instance.entity_ids),
            )
            public_ids_by_match.append(set(crosswalk))
            self.assertEqual(
                recursive_privacy_check(
                    result.public_dict(),
                    forbidden_values=self.pilot.instance.entity_ids,
                ),
                [],
            )

        self.assertTrue(public_ids_by_match[0].isdisjoint(public_ids_by_match[1]))
        for client in clients.values():
            self.assertTrue(client.messages)
            for messages in client.messages:
                self.assertEqual(
                    recursive_privacy_check(
                        messages,
                        forbidden_values=self.pilot.instance.entity_ids,
                    ),
                    [],
                )

    def test_agent_failure_does_not_produce_a_winner(self) -> None:
        clients = {
            MODEL_TAGS[0]: _WrongPhaseClient(),
            MODEL_TAGS[1]: _LegalActionClient(),
        }
        runner = TournamentRunner(
            clients,
            model_tags=MODEL_TAGS,
            max_correction_attempts=0,
            wall_clock_timeout=20,
        )

        result = runner.run_match(
            self.pilot.adapter,
            self.pilot.instance,
            {"player_1": MODEL_TAGS[0], "player_2": MODEL_TAGS[1]},
            restricted_source_ids=self.pilot.restricted_source_ids,
        )

        self.assertEqual(result.status, "agent_failure")
        self.assertIsNone(result.outcome)
        self.assertIsNone(result.winner)
        self.assertFalse(result.audit_valid)
        self.assertFalse(result.replay_valid)


if __name__ == "__main__":
    unittest.main()
