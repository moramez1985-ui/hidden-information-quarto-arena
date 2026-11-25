from contextlib import contextmanager, redirect_stdout
import importlib.util
from io import StringIO
import json
import os
from pathlib import Path
import sys
import tempfile
from types import ModuleType, SimpleNamespace
import unittest
from unittest.mock import patch
from uuid import uuid4


ROOT = Path(__file__).resolve().parents[1]
SNAPSHOT_ROOT = ROOT / "kaggle_dataset_staging" / "quarto-two-model-source-v1"
TASK_SOURCE = ROOT / "kaggle_task" / "quarto_two_model_match.py"
TASK_MODULE_NAME = "quarto_two_model_match_test_module"
PLAYER_1_MODEL = "google/gemini-3.8-flash"
PLAYER_2_KEY = "anthropic/claude-sonnet-4-6@default"
PLAYER_2_MODEL = PLAYER_2_KEY
FMA_ARCHIVE = ROOT / "data" / "fma_metadata.zip"


class _FakeChat:
    def __init__(self, name: str, orphan: bool) -> None:
        self.name = name
        self.orphan = orphan
        self.history: list[str] = []


class _FakeChatManager:
    def __init__(self) -> None:
        self.stack: list[_FakeChat] = []
        self.created: list[_FakeChat] = []

    @contextmanager
    def new(self, name: str = "Chat", orphan: bool = False):
        chat = _FakeChat(name, orphan)
        self.created.append(chat)
        self.stack.append(chat)
        try:
            yield chat
        finally:
            self.stack.pop()

    @property
    def current(self) -> _FakeChat | None:
        return self.stack[-1] if self.stack else None


class _FakeLLM:
    def __init__(
        self,
        model: str,
        chats: _FakeChatManager,
        *,
        malformed_response: bool = False,
    ) -> None:
        self.model = model
        self.name = model
        self.chats = chats
        self.malformed_response = malformed_response
        self.prompts: list[str] = []
        self.observations: list[dict[str, object]] = []
        self.chat_contexts: list[_FakeChat] = []
        self._proposed_features: set[str] = set()

    def prompt(self, prompt: str) -> str:
        chat = self.chats.current
        if chat is None:
            raise AssertionError("Model prompt was not isolated in a chat context.")
        if chat.history:
            raise AssertionError("A prior prompt leaked into this model context.")
        self.prompts.append(prompt)
        self.chat_contexts.append(chat)
        if self.malformed_response:
            return "not JSON"

        payload = json.loads(prompt.split("Observation JSON:\n", 1)[1])
        self.observations.append(payload)
        observation = payload["public_observation"]
        legal = observation["legal_actions"]
        if legal["kind"] == "propose_feature":
            candidates = (
                list(reversed(legal["feature_ids"]))
                if observation.get("current_player") == "player_2"
                else list(legal["feature_ids"])
            )
            next_feature = next(
                (fid for fid in candidates if fid not in self._proposed_features),
                candidates[0],
            )
            self._proposed_features.add(next_feature)
            action = {
                "kind": "propose_feature",
                "feature_id": next_feature,
            }
        elif legal["kind"] == "select_entity":
            action = {
                "kind": "select_entity",
                "entity_id": legal["entity_ids"][0],
            }
        elif legal["kind"] == "place_entity":
            action = {"kind": "place_entity", "cell": legal["cells"][0]}
        else:
            raise AssertionError(f"Unexpected legal-action kind: {legal['kind']!r}")

        response = json.dumps(action)
        chat.history.extend((prompt, response))
        return response


class _FakeTaskRun:
    def __init__(
        self,
        passed: bool,
        result: object = None,
        failure_message: str | None = None,
        stdout: str = "",
    ) -> None:
        self.passed = passed
        self.result = result
        self.failure_message = failure_message
        self.stdout = stdout


class _FakeTask:
    def __init__(self, function, options: dict[str, object]) -> None:
        self.function = function
        self.options = options
        self.run_calls: list[dict[str, object]] = []

    def run(self, **kwargs) -> _FakeTaskRun:
        self.run_calls.append(kwargs)
        stdout = StringIO()
        with redirect_stdout(stdout):
            try:
                result = self.function(**kwargs)
            except Exception as error:
                return _FakeTaskRun(
                    False,
                    failure_message=str(error),
                    stdout=stdout.getvalue(),
                )
        return _FakeTaskRun(
            isinstance(result, dict),
            result,
            stdout=stdout.getvalue(),
        )


class _FakeKaggleBenchmarks(ModuleType):
    def __init__(self, *, selected_llm: _FakeLLM, opponent_llm: _FakeLLM) -> None:
        super().__init__("kaggle_benchmarks")
        self.llm = selected_llm
        self.llms = {PLAYER_2_KEY: opponent_llm}
        self.chats = selected_llm.chats
        self.results = SimpleNamespace(Dictionary=dict)

        def task(**options):
            return lambda function: _FakeTask(function, options)

        self.task = task


class QuartoTwoModelTaskTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.old_dont_write_bytecode = sys.dont_write_bytecode
        cls.chats = _FakeChatManager()
        cls.selected_llm = _FakeLLM(PLAYER_1_MODEL, cls.chats)
        cls.opponent_llm = _FakeLLM(PLAYER_2_MODEL, cls.chats)
        cls.fake_kbench = _FakeKaggleBenchmarks(
            selected_llm=cls.selected_llm,
            opponent_llm=cls.opponent_llm,
        )
        cls.original_kbench_module = sys.modules.get("kaggle_benchmarks")
        sys.modules["kaggle_benchmarks"] = cls.fake_kbench
        cls.original_source_root = os.environ.get("QUARTO_SOURCE_SNAPSHOT_ROOT")
        cls.original_fma_archive = os.environ.get("QUARTO_FMA_ARCHIVE_PATH")
        cls.original_fma_license_ack = os.environ.get("QUARTO_FMA_LICENSE_APPROVED")
        os.environ["QUARTO_SOURCE_SNAPSHOT_ROOT"] = str(SNAPSHOT_ROOT)
        os.environ["QUARTO_FMA_ARCHIVE_PATH"] = str(FMA_ARCHIVE)
        os.environ["QUARTO_FMA_LICENSE_APPROVED"] = "1"
        spec = importlib.util.spec_from_file_location(TASK_MODULE_NAME, TASK_SOURCE)
        if spec is None or spec.loader is None:
            raise RuntimeError("Could not load the Kaggle Task source for tests.")
        cls.task_module = importlib.util.module_from_spec(spec)
        sys.modules[TASK_MODULE_NAME] = cls.task_module
        spec.loader.exec_module(cls.task_module)
        cls.task = cls.task_module.run_quarto_two_model_match

    @classmethod
    def tearDownClass(cls) -> None:
        if cls.original_kbench_module is None:
            sys.modules.pop("kaggle_benchmarks", None)
        else:
            sys.modules["kaggle_benchmarks"] = cls.original_kbench_module
        sys.modules.pop(TASK_MODULE_NAME, None)
        if cls.original_source_root is None:
            os.environ.pop("QUARTO_SOURCE_SNAPSHOT_ROOT", None)
        else:
            os.environ["QUARTO_SOURCE_SNAPSHOT_ROOT"] = cls.original_source_root
        if cls.original_fma_archive is None:
            os.environ.pop("QUARTO_FMA_ARCHIVE_PATH", None)
        else:
            os.environ["QUARTO_FMA_ARCHIVE_PATH"] = cls.original_fma_archive
        if cls.original_fma_license_ack is None:
            os.environ.pop("QUARTO_FMA_LICENSE_APPROVED", None)
        else:
            os.environ["QUARTO_FMA_LICENSE_APPROVED"] = cls.original_fma_license_ack
        sys.dont_write_bytecode = cls.old_dont_write_bytecode

    def test_decorated_task_is_invoked_with_selected_task_llm(self) -> None:
        self.assertEqual(len(self.task.run_calls), 1)
        self.assertIs(self.task.run_calls[0]["llm"], self.selected_llm)
        self.assertEqual(self.task.options["name"], "Hidden information - Quarto Arena")
        self.assertIs(self.task.function.__annotations__["return"], dict)
        self.assertTrue(self.task_module._task_run.passed)
        self.assertEqual(self.task_module._task_run.result["status"], "passed")
        self.assertEqual(
            self.task_module._task_run.result["model_metadata"]["player_1"]["model"],
            PLAYER_1_MODEL,
        )
        self.assertEqual(
            self.task_module._task_run.result["model_metadata"]["player_2"]["model"],
            PLAYER_2_MODEL,
        )
        self.assertEqual(
            self.task_module._task_run.result["security_preflight"]["status"],
            "passed",
        )
        self.assertIn(
            self.task_module._task_run.result["match"]["instance_id"],
            ({p.stem for p in Path("fma_arena_pool").glob("fma_*arena*.json")} | {"fma_seed11_candidate_ordinal_0003_v1"}),
        )

    def test_exact_model_key_identity_and_distinct_handles_are_required(self) -> None:
        selected, opponent, metadata = self.task_module._resolve_models(
            self.selected_llm
        )
        self.assertIs(selected, self.selected_llm)
        self.assertIs(opponent, self.opponent_llm)
        self.assertNotEqual(selected.model, opponent.model)
        self.assertEqual(metadata["player_1"]["model"], PLAYER_1_MODEL)
        self.assertEqual(metadata["player_2"]["registry_key"], PLAYER_2_KEY)
        self.assertEqual(metadata["player_2"]["model"], PLAYER_2_MODEL)

        custom_model = _FakeLLM("unexpected/model", self.chats)
        sel_custom, opp_custom, meta_custom = self.task_module._resolve_models(custom_model)
        self.assertIs(sel_custom, custom_model)
        self.assertIs(opp_custom, self.opponent_llm)
        self.assertEqual(meta_custom["player_1"]["model"], "unexpected/model")
        self.assertEqual(custom_model.prompts, [])

        with patch.object(self.fake_kbench, "llms", {}):
            with self.assertRaisesRegex(RuntimeError, "Kaggle Benchmarks did not expose the kbench.llms registry."):
                self.task_module._resolve_models(self.selected_llm)

    def test_notebook_source_root_resolution_does_not_require_file(self) -> None:
        task_file = self.task_module.__file__
        del self.task_module.__file__
        try:
            with patch.dict(os.environ, {}, clear=True):
                with patch.object(
                    self.task_module, "DEFAULT_SOURCE_ROOT", SNAPSHOT_ROOT
                ):
                    self.assertEqual(
                        self.task_module._resolve_source_root(),
                        SNAPSHOT_ROOT.resolve(),
                    )
                    with self.assertRaisesRegex(
                        RuntimeError,
                        "Executing Task source identity is unverifiable",
                    ):
                        self.task_module._verify_task_source(SNAPSHOT_ROOT)
        finally:
            self.task_module.__file__ = task_file

    def test_unverifiable_notebook_source_fails_before_any_prompt(self) -> None:
        task_file = self.task_module.__file__
        prompt_count = len(self.selected_llm.prompts)
        del self.task_module.__file__
        try:
            failed_run = self.task.run(llm=self.selected_llm)
        finally:
            self.task_module.__file__ = task_file

        self.assertFalse(failed_run.passed)
        self.assertIn("source identity is unverifiable", failed_run.failure_message)
        self.assertEqual(len(self.selected_llm.prompts), prompt_count)

    def test_invalid_explicit_snapshot_root_does_not_fall_through(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            invalid_root = Path(temporary_directory) / "missing-snapshot"
            with patch.dict(
                os.environ,
                {"QUARTO_SOURCE_SNAPSHOT_ROOT": str(invalid_root)},
            ):
                with patch.object(
                    self.task_module,
                    "DEFAULT_SOURCE_ROOT",
                    SNAPSHOT_ROOT,
                ):
                    with self.assertRaisesRegex(
                        RuntimeError,
                        "Could not read the Quarto source snapshot manifest",
                    ):
                        self.task_module._resolve_source_root()

    def test_task_preflight_receives_validated_public_replay_projector(self) -> None:
        import tournament_harness

        captured: dict[str, object] = {}
        prompt_count = len(self.selected_llm.prompts)

        def fail_preflight(**options):
            captured.update(options)
            return {
                "status": "failed",
                "checks": [{"check": "forced_test_failure", "passed": False}],
            }

        with patch.object(tournament_harness, "run_security_audit", fail_preflight):
            with self.assertRaisesRegex(RuntimeError, "security preflight failed"):
                self.task_module._run_quarto_two_model_match(
                    self.selected_llm,
                    {},
                )

        self.assertIs(
            captured["public_replay_projector"],
            self.task_module._project_and_validate_public_replay,
        )
        self.assertEqual(len(self.selected_llm.prompts), prompt_count)

    def test_task_public_replay_projection_validates_terminal_phases(self) -> None:
        from phase0_foundation import SyntheticAdapter
        from tournament_harness import run_security_audit

        adapter = SyntheticAdapter()
        instance = adapter.build_instance()
        outcomes: list[str] = []
        task_projector = self.task_module._project_and_validate_public_replay

        def recording_projector(public_audit):
            projection = task_projector(public_audit)
            outcomes.append(projection["result"]["outcome"])
            return projection

        report = run_security_audit(
            adapter=adapter,
            instance=instance,
            public_replay_projector=recording_projector,
            enable_draft=True,
        )

        self.assertEqual(report["status"], "passed", report["checks"])
        self.assertEqual(outcomes, ["win", "draw"])

    def test_task_fails_closed_without_explicit_archive_and_license_approval(self) -> None:
        cases = (
            (
                {
                    "QUARTO_FMA_ARCHIVE_PATH": str(FMA_ARCHIVE),
                    "QUARTO_FMA_LICENSE_APPROVED": "",
                },
                "license must be explicitly approved",
            ),
            (
                {
                    "QUARTO_FMA_ARCHIVE_PATH": "",
                    "QUARTO_FMA_LICENSE_APPROVED": "1",
                },
                "mounted FMA metadata archive is required",
            ),
        )
        for environment, expected_message in cases:
            with self.subTest(expected_message=expected_message):
                prompt_count = len(self.selected_llm.prompts)
                with patch.dict(os.environ, environment):
                    failed_run = self.task.run(llm=self.selected_llm)
                self.assertFalse(failed_run.passed)
                self.assertIn(expected_message, failed_run.failure_message)
                self.assertEqual(len(self.selected_llm.prompts), prompt_count)

    def test_successful_match_requires_a_valid_terminal_result(self) -> None:
        self.assertTrue(
            self.task_module._is_valid_terminal_result(
                {
                    "mode": "classic",
                    "outcome": "win",
                    "winner": "player_1",
                    "reason": "quarto",
                }
            )
        )
        self.assertTrue(
            self.task_module._is_valid_terminal_result(
                {
                    "mode": "classic",
                    "outcome": "draw",
                    "winner": None,
                    "reason": "board_full",
                }
            )
        )
        self.assertFalse(
            self.task_module._is_valid_terminal_result(
                {
                    "mode": "classic",
                    "outcome": "win",
                    "winner": None,
                    "reason": "quarto",
                }
            )
        )

    def _failure_record(self, task_run: _FakeTaskRun) -> dict[str, object]:
        prefix = self.task_module._FAILURE_LOG_PREFIX
        records = [
            line[len(prefix):]
            for line in task_run.stdout.splitlines()
            if line.startswith(prefix)
        ]
        self.assertEqual(len(records), 1, task_run.stdout)
        record = json.loads(records[0])
        self.assertIsInstance(record, dict)
        return record

    def test_failed_match_fails_the_task_run(self) -> None:
        failed_opponent = _FakeLLM(
            PLAYER_2_MODEL,
            self.chats,
            malformed_response=True,
        )
        with patch.object(
            self.fake_kbench,
            "llms",
            {PLAYER_2_KEY: failed_opponent},
        ):
            failed_run = self.task.run(llm=self.selected_llm)

        self.assertFalse(failed_run.passed)
        self.assertIn(
            "Game 1 validation failed",
            failed_run.failure_message,
        )
        self.assertEqual(len(failed_opponent.prompts), 1)
        diagnostic = self._failure_record(failed_run)
        self.assertEqual(diagnostic["status"], "failed")
        self.assertFalse(diagnostic["passed"])
        self.assertEqual(diagnostic["failure_stage"], "match_validation")
        self.assertEqual(diagnostic["exception_class"], "RuntimeError")
        self.assertIn("match_id", diagnostic)
        self.assertIn("action_count", diagnostic)
        self.assertIn("audit_valid", diagnostic)
        self.assertIn("replay_valid", diagnostic)
        self.assertNotIn("failure", diagnostic)

    def test_model_resolution_failure_is_reported_without_match_fields(self) -> None:
        with patch.object(self.fake_kbench, "llms", {}):
            failed_run = self.task.run(llm=self.selected_llm)

        self.assertFalse(failed_run.passed)
        diagnostic = self._failure_record(failed_run)
        self.assertEqual(diagnostic["failure_stage"], "model_resolution")
        self.assertEqual(diagnostic["exception_class"], "RuntimeError")
        self.assertIn("elapsed_seconds", diagnostic)
        self.assertNotIn("match_id", diagnostic)
        self.assertNotIn("action_count", diagnostic)
        self.assertNotIn("audit_valid", diagnostic)
        self.assertNotIn("replay_valid", diagnostic)

    def test_failure_diagnostic_excludes_private_exception_text(self) -> None:
        private_sentinel = "PRIVATE_PROMPT_AND_AUDIT_SENTINEL"
        with patch.object(
            self.task_module,
            "_resolve_models",
            side_effect=RuntimeError(private_sentinel),
        ):
            failed_run = self.task.run(llm=self.selected_llm)

        diagnostic = self._failure_record(failed_run)
        self.assertFalse(failed_run.passed)
        self.assertNotIn(private_sentinel, failed_run.stdout)
        self.assertNotIn(private_sentinel, json.dumps(diagnostic))
        self.assertEqual(
            set(diagnostic),
            {
                "status",
                "passed",
                "failure_stage",
                "exception_class",
                "error_summary",
                "elapsed_seconds",
            },
        )
        self.assertFalse(
            {
                "private_observation",
                "prompt",
                "messages",
                "restricted_log",
                "audit_snapshot",
                "decision_traces",
                "credentials",
                "token",
            }.intersection(key.lower() for key in diagnostic)
        )

    def test_public_result_contains_no_private_decision_traces(self) -> None:
        result = self.task_module._task_run.result
        self.assertEqual(result["status"], "passed")
        self.assertTrue(result["passed"])
        self.assertEqual(result["private_trace_storage"]["status"], "not_emitted")
        self.assertTrue(result["match"]["public_replay_valid"])
        self.assertNotIn("research_only", result)
        self.assertNotIn("decision_traces", result)
        self.assertEqual(
            set(result["public_replay"]),
            {
                "match_id",
                "replay_schema_version",
                "mode",
                "starting_player",
                "board",
                "draft_history",
                "public_history",
                "result",
            },
        )
        self.assertTrue(
            self.task_module._validate_public_replay(result["public_replay"])
        )
        forbidden_fields = {
            "entity_to_piece",
            "piece_to_entity",
            "feature_to_bit",
            "private_feature_ownership",
            "engine_state_snapshot",
            "selected_piece",
            "private",
        }
        self.assertFalse(
            forbidden_fields.intersection(
                key.lower() for key in result["public_replay"]
            )
        )

    def test_public_replay_projection_rejects_unexpected_and_restricted_fields(self) -> None:
        entity_id = uuid4().hex
        public_audit = {
            "match_id": f"match:{uuid4()}",
            "mode": "classic",
            "starting_player": "player_1",
            "phase": "terminal",
            "current_player": "player_2",
            "selected_entity": None,
            "board": [entity_id, *([None] * 15)],
            "draft_history": [
                {"kind": "propose_attribute", "player": "player_1", "attribute_id": "f0", "accepted": True},
                {"kind": "propose_attribute", "player": "player_2", "attribute_id": "f2", "accepted": True},
                {"kind": "propose_attribute", "player": "player_1", "attribute_id": "f1", "accepted": True},
                {"kind": "propose_attribute", "player": "player_2", "attribute_id": "f3", "accepted": True},
            ],
            "public_history": [
                {
                    "kind": "select_entity",
                    "player": "player_1",
                    "entity_id": entity_id,
                },
                {"kind": "place_entity", "player": "player_2", "cell": 0},
            ],
            "result": {
                "mode": "classic",
                "outcome": "win",
                "winner": "player_2",
                "reason": "quarto",
            },
            "legal_actions": {"kind": "terminal"},
        }
        projection = self.task_module._project_public_replay(public_audit)
        self.assertEqual(
            set(projection),
            {
                "match_id",
                "replay_schema_version",
                "mode",
                "starting_player",
                "board",
                "draft_history",
                "public_history",
                "result",
            },
        )
        self.assertTrue(self.task_module._validate_public_replay(projection))

        invalid_board = dict(projection)
        invalid_board["board"] = [None] * 16
        self.assertFalse(self.task_module._validate_public_replay(invalid_board))

        with self.assertRaisesRegex(ValueError, "missing or unexpected fields"):
            self.task_module._project_public_replay({
                **public_audit,
                "restricted_evaluator_data": {
                    "private_feature_ownership": "RESTRICTED_SENTINEL",
                },
            })

        leaked_history = dict(public_audit)
        leaked_history["public_history"] = [
            {**public_audit["public_history"][0], "piece_id": 0},
            public_audit["public_history"][1],
        ]
        with self.assertRaisesRegex(ValueError, "missing or unexpected fields"):
            self.task_module._project_public_replay(leaked_history)


if __name__ == "__main__":
    unittest.main()
