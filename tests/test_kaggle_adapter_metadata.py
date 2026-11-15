import unittest

from kaggle_agent_adapter import KaggleAgentAdapter


class _LLMWithMetadata:
    model = "provider/model"
    name = "provider/model"
    model_version = "2026-01"

    def prompt(self, prompt: str) -> str:
        raise AssertionError("This test must not invoke the model.")


class _LLMWithoutVersion:
    model = "provider/model"

    def prompt(self, prompt: str) -> str:
        raise AssertionError("This test must not invoke the model.")


class KaggleAdapterMetadataTests(unittest.TestCase):
    def test_adapter_preserves_available_model_metadata(self) -> None:
        client = KaggleAgentAdapter(_LLMWithMetadata()).client

        self.assertEqual(client.model_provider, "kaggle")
        self.assertEqual(client.model, "provider/model")
        self.assertEqual(client.model_version, "2026-01")

    def test_adapter_does_not_fabricate_an_unavailable_model_version(self) -> None:
        client = KaggleAgentAdapter(_LLMWithoutVersion()).client

        self.assertEqual(client.model, "provider/model")
        self.assertFalse(hasattr(client, "model_version"))


if __name__ == "__main__":
    unittest.main()
