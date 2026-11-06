from __future__ import annotations

import random
from typing import TypeAlias

from quarto_engine import GameState, legal_actions


Action: TypeAlias = dict[str, int | str | None]


class RandomAgent:
    def __init__(self, seed: int) -> None:
        self._random = random.Random(seed)

    def choose_action(self, state: GameState) -> Action:
        available = legal_actions(state)
        action_type = available["type"]
        player = available["player"]
        if not isinstance(action_type, str) or not isinstance(player, str):
            raise RuntimeError("Engine returned malformed legal action metadata.")

        if action_type == "select_piece":
            piece_ids = available["piece_ids"]
            if not isinstance(piece_ids, list) or not piece_ids:
                raise RuntimeError("Engine returned no legal piece selections.")
            piece_id = self._random.choice(piece_ids)
            if not isinstance(piece_id, int):
                raise RuntimeError("Engine returned an invalid legal piece id.")
            return {
                "kind": "select_piece",
                "player": player,
                "piece_id": piece_id,
                "cell": None,
            }

        if action_type == "place_piece":
            cells = available["cells"]
            piece_id = available["piece_id"]
            if not isinstance(cells, list) or not cells:
                raise RuntimeError("Engine returned no legal placement cells.")
            if not isinstance(piece_id, int):
                raise RuntimeError("Engine returned an invalid selected piece.")
            cell = self._random.choice(cells)
            if not isinstance(cell, int):
                raise RuntimeError("Engine returned an invalid legal cell.")
            return {
                "kind": "place_piece",
                "player": player,
                "piece_id": None,
                "cell": cell,
            }

        raise RuntimeError(f"No random action is available in phase {action_type!r}.")
