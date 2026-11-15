from __future__ import annotations

from collections.abc import Mapping, Sequence
import time
from typing import Protocol

from tournament_harness import AgentAdapter, ChatResult, ModelClientError


class KaggleLLM(Protocol):
    def prompt(self, prompt: str) -> str: ...


class _KagglePromptClient:
    model_provider = "kaggle"

    def __init__(self, llm: KaggleLLM) -> None:
        self.llm = llm
        model = getattr(llm, "model", None)
        if not isinstance(model, str) or not model:
            model = getattr(llm, "name", None)
        if isinstance(model, str) and model:
            self.model = model
        model_version = getattr(llm, "model_version", None)
        if isinstance(model_version, str) and model_version:
            self.model_version = model_version

    def chat(
        self,
        messages: Sequence[Mapping[str, str]],
        *,
        timeout: float | None = None,
    ) -> ChatResult:
        if (
            len(messages) != 2
            or messages[0].get("role") != "system"
            or messages[1].get("role") != "user"
            or not isinstance(messages[0].get("content"), str)
            or not isinstance(messages[1].get("content"), str)
        ):
            raise ModelClientError("Kaggle adapter received an invalid Agent prompt.")

        prompt = (
            f"{messages[0]['content']}\n\n"
            f"Observation JSON:\n{messages[1]['content']}"
        )
        started = time.monotonic()
        try:
            content = self.llm.prompt(prompt)
        except Exception as error:
            raise ModelClientError("Kaggle LLM invocation failed.") from error
        duration_seconds = time.monotonic() - started
        if not isinstance(content, str):
            raise ModelClientError("Kaggle LLM returned a non-text response.")
        return ChatResult(
            content=content,
            raw_response=content,
            duration_seconds=duration_seconds,
        )


class KaggleAgentAdapter(AgentAdapter):
    def __init__(self, llm: KaggleLLM) -> None:
        super().__init__(
            _KagglePromptClient(llm),
            correction_attempts=0,
        )
