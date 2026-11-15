from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Protocol


@dataclass(frozen=True, slots=True)
class SemanticJudgeRequest:
    match_id: str
    item_id: str
    item_type: str
    claim_or_hypothesis: str
    evidence: Sequence[Mapping[str, Any]]


@dataclass(frozen=True, slots=True)
class SemanticJudgeSuggestion:
    suggested_label: str
    rationale: str
    provider: str
    model: str | None = None


class SemanticJudge(Protocol):
    """Provider-neutral suggestion interface; suggestions are never gold labels."""

    def suggest(self, request: SemanticJudgeRequest) -> SemanticJudgeSuggestion: ...

