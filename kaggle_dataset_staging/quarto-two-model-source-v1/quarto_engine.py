from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
import json
from typing import Literal


Mode = Literal["classic", "self_selection"]
Player = Literal["player_1", "player_2"]
Phase = Literal["select", "place", "terminal"]
ActionKind = Literal["select_piece", "place_piece"]
Outcome = Literal["win", "draw"]
ResultReason = Literal["quarto", "board_full"]

MODES = ("classic", "self_selection")
PLAYERS = ("player_1", "player_2")
ATTRIBUTE_PAIRS = (
    ("cube", "cylinder"),
    ("light", "dark"),
    ("big", "small"),
    ("solid", "hole"),
)
ATTRIBUTE_VALUES = tuple(value for pair in ATTRIBUTE_PAIRS for value in pair)
ATTRIBUTE_TO_BIT = {
    value: bit for bit, pair in enumerate(ATTRIBUTE_PAIRS) for value in pair
}
BOARD_SIZE = 4
PIECE_COUNT = 16
BIT_COUNT = 4
STATE_SCHEMA_VERSION = 1
REPLAY_SCHEMA_VERSION = 1


@dataclass(frozen=True, slots=True)
class WinningLine:
    cells: tuple[int, ...]
    shared_attributes: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class GameResult:
    mode: Mode
    outcome: Outcome
    winner: Player | None
    reason: ResultReason
    winning_lines: tuple[WinningLine, ...]


@dataclass(frozen=True, slots=True)
class ActionRecord:
    kind: ActionKind
    player: Player
    piece_id: int | None = None
    cell: int | None = None


@dataclass(frozen=True, slots=True)
class GameState:
    mode: Mode
    starting_player: Player
    board: tuple[int | None, ...]
    remaining_pieces: tuple[int, ...]
    active_player: Player
    phase: Phase
    selected_piece: int | None
    selected_by: Player | None
    is_terminal: bool
    result: GameResult | None
    history: tuple[ActionRecord, ...]
    bit_owners: tuple[tuple[int, Player], ...] | None = None


WINNING_LINES = (
    (0, 1, 2, 3),
    (4, 5, 6, 7),
    (8, 9, 10, 11),
    (12, 13, 14, 15),
    (0, 4, 8, 12),
    (1, 5, 9, 13),
    (2, 6, 10, 14),
    (3, 7, 11, 15),
    (0, 5, 10, 15),
    (3, 6, 9, 12),
)


def new_game(
    mode: Mode = "classic",
    starting_player: Player = "player_1",
    bit_owners: Mapping[int, Player] | Sequence[tuple[int, Player]] | None = None,
) -> GameState:
    parsed_mode = _parse_mode(mode)
    parsed_starting_player = _parse_player(starting_player)
    parsed_bit_owners = _parse_bit_owners(bit_owners)
    state = GameState(
        mode=parsed_mode,
        starting_player=parsed_starting_player,
        board=(None,) * PIECE_COUNT,
        remaining_pieces=tuple(range(PIECE_COUNT)),
        active_player=parsed_starting_player,
        phase="select",
        selected_piece=None,
        selected_by=None,
        is_terminal=False,
        result=None,
        history=(),
        bit_owners=parsed_bit_owners,
    )
    _validate_state(state)
    return state


def piece_attributes(piece_id: int) -> tuple[str, ...]:
    _require_piece_id(piece_id)
    return tuple(
        pair[(piece_id >> bit) & 1] for bit, pair in enumerate(ATTRIBUTE_PAIRS)
    )


def find_winning_lines(
    board: Sequence[int | None],
    *,
    bit_owners: Mapping[int, Player] | Sequence[tuple[int, Player]] | None = None,
    owner: Player | None = None,
) -> tuple[WinningLine, ...]:
    if len(board) != PIECE_COUNT:
        raise ValueError(f"Board must contain exactly {PIECE_COUNT} cells.")
    for piece_id in board:
        if piece_id is not None:
            _require_piece_id(piece_id)

    parsed_bit_owners = _parse_bit_owners(bit_owners)
    parsed_owner = _parse_optional_player(owner)
    owner_map = dict(parsed_bit_owners) if parsed_bit_owners is not None else None
    if owner_map is not None and parsed_owner is None:
        raise ValueError("owner must be provided when bit_owners is specified.")

    completed: list[WinningLine] = []
    for cells in WINNING_LINES:
        pieces_on_line = tuple(board[cell] for cell in cells)
        if any(piece_id is None for piece_id in pieces_on_line):
            continue
        attributes = tuple(
            attribute
            for attribute in ATTRIBUTE_VALUES
            if (
                owner_map is None
                or owner_map[ATTRIBUTE_TO_BIT[attribute]] == parsed_owner
            )
            and all(
                attribute in piece_attributes(piece_id) for piece_id in pieces_on_line
            )
        )
        if attributes:
            completed.append(WinningLine(cells=cells, shared_attributes=attributes))
    return tuple(completed)


def legal_actions(state: GameState) -> dict[str, object]:
    _validate_state(state)
    if state.phase == "select":
        return {
            "type": "select_piece",
            "player": state.active_player,
            "piece_ids": list(state.remaining_pieces),
            "piece_id": None,
            "cells": [],
        }
    if state.phase == "place":
        return {
            "type": "place_piece",
            "player": state.active_player,
            "piece_ids": [],
            "piece_id": state.selected_piece,
            "cells": [
                cell for cell, piece_id in enumerate(state.board) if piece_id is None
            ],
        }
    return {
        "type": "terminal",
        "player": state.active_player,
        "piece_ids": [],
        "piece_id": None,
        "cells": [],
    }


def select_piece(state: GameState, player: Player, piece_id: int) -> GameState:
    _validate_state(state)
    parsed_player = _parse_player(player)
    _require_piece_id(piece_id)
    if state.is_terminal:
        raise ValueError("Cannot select a piece after the game has ended.")
    if state.phase != "select":
        raise ValueError("A piece can only be selected during the select phase.")
    if parsed_player != state.active_player:
        raise ValueError("Only the active player may select a piece.")
    if piece_id not in state.remaining_pieces:
        raise ValueError("The selected piece has already been used.")

    placer = (
        _other_player(parsed_player) if state.mode == "classic" else parsed_player
    )
    next_state = replace(
        state,
        active_player=placer,
        phase="place",
        selected_piece=piece_id,
        selected_by=parsed_player,
        history=state.history
        + (ActionRecord(kind="select_piece", player=parsed_player, piece_id=piece_id),),
    )
    _validate_state(next_state)
    return next_state


def place_piece(state: GameState, player: Player, cell: int) -> GameState:
    _validate_state(state)
    parsed_player = _parse_player(player)
    _require_cell(cell)
    if state.is_terminal:
        raise ValueError("Cannot place a piece after the game has ended.")
    if state.phase != "place":
        raise ValueError("A piece can only be placed during the place phase.")
    if parsed_player != state.active_player:
        raise ValueError("Only the active player may place the selected piece.")
    if state.board[cell] is not None:
        raise ValueError("The selected cell is already occupied.")
    if state.selected_piece is None:
        raise ValueError("No piece is selected for placement.")

    piece_id = state.selected_piece
    board = list(state.board)
    board[cell] = piece_id
    remaining_pieces = tuple(
        available for available in state.remaining_pieces if available != piece_id
    )
    winner: Player | None = None
    if state.bit_owners is None:
        winning_lines = find_winning_lines(board)
        if winning_lines:
            winner = parsed_player
    else:
        winning_lines = find_winning_lines(
            board,
            bit_owners=state.bit_owners,
            owner=parsed_player,
        )
        if winning_lines:
            winner = parsed_player
        else:
            opponent = _other_player(parsed_player)
            opponent_lines = find_winning_lines(
                board,
                bit_owners=state.bit_owners,
                owner=opponent,
            )
            if opponent_lines:
                winning_lines = opponent_lines
                winner = opponent
    history = state.history + (
        ActionRecord(kind="place_piece", player=parsed_player, cell=cell),
    )

    if winning_lines and winner is not None:
        result = GameResult(
            mode=state.mode,
            outcome="win",
            winner=winner,
            reason="quarto",
            winning_lines=winning_lines,
        )
        next_state = replace(
            state,
            board=tuple(board),
            remaining_pieces=remaining_pieces,
            active_player=winner,
            phase="terminal",
            selected_piece=None,
            selected_by=None,
            is_terminal=True,
            result=result,
            history=history,
        )
    elif not remaining_pieces:
        result = GameResult(
            mode=state.mode,
            outcome="draw",
            winner=None,
            reason="board_full",
            winning_lines=(),
        )
        next_state = replace(
            state,
            board=tuple(board),
            remaining_pieces=remaining_pieces,
            phase="terminal",
            selected_piece=None,
            selected_by=None,
            is_terminal=True,
            result=result,
            history=history,
        )
    else:
        next_player = (
            parsed_player
            if state.mode == "classic"
            else _other_player(parsed_player)
        )
        next_state = replace(
            state,
            board=tuple(board),
            remaining_pieces=remaining_pieces,
            active_player=next_player,
            phase="select",
            selected_piece=None,
            selected_by=None,
            is_terminal=False,
            result=None,
            history=history,
        )

    _validate_state(next_state)
    return next_state


def apply_action(state: GameState, action: Mapping[str, object]) -> GameState:
    if not isinstance(action, Mapping):
        raise ValueError("An action must be an object.")
    kind = action.get("kind")
    player = _parse_player(action.get("player"))
    if kind == "select_piece":
        if action.get("cell") is not None:
            raise ValueError("A select_piece action cannot include a cell.")
        return select_piece(
            state, player, _require_piece_id(action.get("piece_id"))
        )
    if kind == "place_piece":
        if action.get("piece_id") is not None:
            raise ValueError("A place_piece action cannot include a piece_id.")
        return place_piece(state, player, _require_cell(action.get("cell")))
    raise ValueError(f"Unknown action kind: {kind!r}.")


def state_to_dict(state: GameState) -> dict[str, object]:
    _validate_state(state)
    payload: dict[str, object] = {
        "schema_version": STATE_SCHEMA_VERSION,
        "mode": state.mode,
        "starting_player": state.starting_player,
        "board": list(state.board),
        "remaining_pieces": list(state.remaining_pieces),
        "active_player": state.active_player,
        "phase": state.phase,
        "selected_piece": state.selected_piece,
        "selected_by": state.selected_by,
        "is_terminal": state.is_terminal,
        "result": _result_to_dict(state.result),
        "history": [_action_to_dict(action) for action in state.history],
    }
    if state.bit_owners is not None:
        payload["bit_owners"] = {
            str(bit): owner for bit, owner in state.bit_owners
        }
    return payload


def serialize_state(state: GameState) -> str:
    return json.dumps(state_to_dict(state), sort_keys=True, separators=(",", ":"))


def deserialize_state(serialized: str) -> GameState:
    data = json.loads(serialized)
    if not isinstance(data, Mapping):
        raise ValueError("Serialized state must contain a JSON object.")
    legacy_keys = {
        "schema_version",
        "mode",
        "board",
        "remaining_pieces",
        "active_player",
        "phase",
        "selected_piece",
        "selected_by",
        "is_terminal",
        "result",
        "history",
    }
    allowed_optional_keys = {"starting_player", "bit_owners"}
    actual_keys = set(data)
    if not legacy_keys.issubset(actual_keys) or not actual_keys.issubset(
        legacy_keys | allowed_optional_keys
    ):
        raise ValueError("Serialized state has missing or unexpected fields.")
    if data["schema_version"] != STATE_SCHEMA_VERSION:
        raise ValueError("Unsupported state schema version.")

    board_data = _require_list(data["board"], "board")
    remaining_data = _require_list(data["remaining_pieces"], "remaining_pieces")
    history_data = _require_list(data["history"], "history")
    state = GameState(
        mode=_parse_mode(data["mode"]),
        starting_player=_parse_player(data.get("starting_player", "player_1")),
        board=tuple(_parse_optional_piece(piece) for piece in board_data),
        remaining_pieces=tuple(_require_piece_id(piece) for piece in remaining_data),
        active_player=_parse_player(data["active_player"]),
        phase=_parse_phase(data["phase"]),
        selected_piece=_parse_optional_piece(data["selected_piece"]),
        selected_by=_parse_optional_player(data["selected_by"]),
        is_terminal=_require_bool(data["is_terminal"], "is_terminal"),
        result=_parse_result(data["result"]),
        history=tuple(_parse_action(action) for action in history_data),
        bit_owners=_parse_serialized_bit_owners(data.get("bit_owners")),
    )
    _validate_state(state)
    return state


def serialize_replay(state: GameState) -> str:
    _validate_state(state)
    replay: dict[str, object] = {
        "schema_version": REPLAY_SCHEMA_VERSION,
        "mode": state.mode,
        "starting_player": state.starting_player,
        "actions": [_action_to_dict(action) for action in state.history],
        "result": _result_to_dict(state.result),
    }
    if state.bit_owners is not None:
        replay["bit_owners"] = {
            str(bit): owner for bit, owner in state.bit_owners
        }
    return json.dumps(replay, sort_keys=True, separators=(",", ":"))


def replay_game(serialized_replay: str) -> GameState:
    replay = json.loads(serialized_replay)
    if not isinstance(replay, Mapping):
        raise ValueError("Serialized replay must contain a JSON object.")
    legacy_keys = {"schema_version", "mode", "actions", "result"}
    allowed_optional_keys = {"starting_player", "bit_owners"}
    actual_keys = set(replay)
    if not legacy_keys.issubset(actual_keys) or not actual_keys.issubset(
        legacy_keys | allowed_optional_keys
    ):
        raise ValueError("Serialized replay has missing or unexpected fields.")
    if replay["schema_version"] != REPLAY_SCHEMA_VERSION:
        raise ValueError("Unsupported replay schema version.")

    mode = _parse_mode(replay["mode"])
    starting_player = _parse_player(replay.get("starting_player", "player_1"))
    bit_owners = _parse_serialized_bit_owners(replay.get("bit_owners"))
    actions = _require_list(replay["actions"], "actions")
    state = new_game(
        mode,
        starting_player=starting_player,
        bit_owners=bit_owners,
    )
    for action in actions:
        if not isinstance(action, Mapping):
            raise ValueError("Every replay action must be an object.")
        state = apply_action(state, action)
    expected_result = _result_to_dict(_parse_result(replay["result"]))
    if _result_to_dict(state.result) != expected_result:
        raise ValueError("Replay result does not match the actions.")
    return state


def _validate_state(state: GameState) -> None:
    _parse_mode(state.mode)
    _parse_player(state.starting_player)
    _parse_player(state.active_player)
    _parse_phase(state.phase)
    _parse_bit_owners(state.bit_owners)
    if len(state.board) != PIECE_COUNT:
        raise ValueError(f"Board must contain exactly {PIECE_COUNT} cells.")
    placed = [piece_id for piece_id in state.board if piece_id is not None]
    for piece_id in placed:
        _require_piece_id(piece_id)
    if len(set(placed)) != len(placed):
        raise ValueError("A piece cannot occupy more than one board cell.")
    if len(set(state.remaining_pieces)) != len(state.remaining_pieces):
        raise ValueError("Remaining pieces must be unique.")
    for piece_id in state.remaining_pieces:
        _require_piece_id(piece_id)
    if set(placed).intersection(state.remaining_pieces):
        raise ValueError("A placed piece cannot remain available.")
    if set(placed).union(state.remaining_pieces) != set(range(PIECE_COUNT)):
        raise ValueError("Placed and remaining pieces must account for all pieces.")

    if type(state.is_terminal) is not bool:
        raise ValueError("is_terminal must be a boolean.")
    if state.is_terminal != (state.phase == "terminal"):
        raise ValueError("Terminal status and phase do not match.")
    if state.phase == "select":
        if state.selected_piece is not None or state.selected_by is not None:
            raise ValueError("Select phase cannot have a selected piece.")
        if state.result is not None or not state.remaining_pieces:
            raise ValueError("A select-phase state must be nonterminal.")
    elif state.phase == "place":
        if state.selected_piece not in state.remaining_pieces:
            raise ValueError("Place phase must have an available selected piece.")
        selected_by = _parse_player(state.selected_by)
        if state.mode == "classic" and state.active_player == selected_by:
            raise ValueError("Classic mode selects a piece for the other player.")
        if state.mode == "self_selection" and state.active_player != selected_by:
            raise ValueError("Self-selection mode places the piece by its chooser.")
        if state.result is not None:
            raise ValueError("A nonterminal state cannot have a result.")
    else:
        if state.selected_piece is not None or state.selected_by is not None:
            raise ValueError("Terminal state cannot have a selected piece.")
        _validate_result(state)

    for action in state.history:
        _validate_action_record(action)
    if state.history and state.history[0].player != state.starting_player:
        raise ValueError("The first action must be made by the starting player.")


def _validate_result(state: GameState) -> None:
    result = state.result
    if result is None:
        raise ValueError("A terminal state must have a result.")
    if result.mode != state.mode:
        raise ValueError("Result mode must match the game mode.")
    _parse_player(state.active_player)
    expected_lines = find_winning_lines(
        state.board,
        bit_owners=state.bit_owners,
        owner=state.active_player if state.bit_owners is not None else None,
    )
    if result.outcome == "win":
        if result.reason != "quarto" or result.winner != state.active_player:
            raise ValueError("Winning result must identify the active winning player.")
        if result.winning_lines != expected_lines:
            raise ValueError("Winning result lines must match the board.")
        if not result.winning_lines:
            raise ValueError("A winning result must include a winning line.")
    elif result.outcome == "draw":
        if result.reason != "board_full" or result.winner is not None:
            raise ValueError("Draw result must identify a full-board draw.")
        if any(piece_id is None for piece_id in state.board):
            raise ValueError("A draw requires a full board.")
        if result.winning_lines or expected_lines:
            raise ValueError("A full board with a winning line is not a draw.")
    else:
        raise ValueError("Unknown result outcome.")


def _validate_action_record(action: ActionRecord) -> None:
    _parse_player(action.player)
    if action.kind == "select_piece":
        if action.piece_id is None or action.cell is not None:
            raise ValueError("Invalid select_piece action record.")
        _require_piece_id(action.piece_id)
    elif action.kind == "place_piece":
        if action.piece_id is not None or action.cell is None:
            raise ValueError("Invalid place_piece action record.")
        _require_cell(action.cell)
    else:
        raise ValueError("Unknown action record kind.")


def _result_to_dict(result: GameResult | None) -> dict[str, object] | None:
    if result is None:
        return None
    return {
        "mode": result.mode,
        "outcome": result.outcome,
        "winner": result.winner,
        "reason": result.reason,
        "winning_lines": [
            {
                "cells": list(line.cells),
                "shared_attributes": list(line.shared_attributes),
            }
            for line in result.winning_lines
        ],
    }


def _parse_result(value: object) -> GameResult | None:
    if value is None:
        return None
    data = _require_mapping(value, "result")
    if set(data) != {"mode", "outcome", "winner", "reason", "winning_lines"}:
        raise ValueError("Result has missing or unexpected fields.")
    outcome = data["outcome"]
    reason = data["reason"]
    if outcome not in ("win", "draw"):
        raise ValueError("Unknown result outcome.")
    if reason not in ("quarto", "board_full"):
        raise ValueError("Unknown result reason.")
    winner = _parse_optional_player(data["winner"])
    lines_data = _require_list(data["winning_lines"], "winning_lines")
    lines: list[WinningLine] = []
    for line_value in lines_data:
        line = _require_mapping(line_value, "winning line")
        if set(line) != {"cells", "shared_attributes"}:
            raise ValueError("Winning line has missing or unexpected fields.")
        cells = tuple(
            _require_cell(cell)
            for cell in _require_list(line["cells"], "winning line cells")
        )
        attributes = tuple(
            _require_string(attribute, "shared attribute")
            for attribute in _require_list(
                line["shared_attributes"], "shared attributes"
            )
        )
        lines.append(WinningLine(cells=cells, shared_attributes=attributes))
    return GameResult(
        mode=_parse_mode(data["mode"]),
        outcome=outcome,
        winner=winner,
        reason=reason,
        winning_lines=tuple(lines),
    )


def _action_to_dict(action: ActionRecord) -> dict[str, object]:
    _validate_action_record(action)
    return {
        "kind": action.kind,
        "player": action.player,
        "piece_id": action.piece_id,
        "cell": action.cell,
    }


def _parse_action(value: object) -> ActionRecord:
    data = _require_mapping(value, "action")
    if set(data) != {"kind", "player", "piece_id", "cell"}:
        raise ValueError("Action has missing or unexpected fields.")
    kind = data["kind"]
    if kind not in ("select_piece", "place_piece"):
        raise ValueError("Unknown action kind.")
    action = ActionRecord(
        kind=kind,
        player=_parse_player(data["player"]),
        piece_id=_parse_optional_piece(data["piece_id"]),
        cell=_parse_optional_cell(data["cell"]),
    )
    _validate_action_record(action)
    return action


def _parse_bit_owners(
    value: Mapping[int, Player] | Sequence[tuple[int, Player]] | None,
) -> tuple[tuple[int, Player], ...] | None:
    if value is None:
        return None
    if isinstance(value, Mapping):
        items = list(value.items())
    elif isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        items = list(value)
    else:
        raise ValueError("bit_owners must be a mapping or sequence of (bit, player) pairs.")

    if len(items) != BIT_COUNT:
        raise ValueError(f"bit_owners must specify all {BIT_COUNT} bits.")
    parsed: dict[int, Player] = {}
    for entry in items:
        if (
            not isinstance(entry, Sequence)
            or isinstance(entry, (str, bytes))
            or len(entry) != 2
        ):
            raise ValueError("Each bit_owners entry must be a (bit, player) pair.")
        bit, owner = entry
        if type(bit) is not int or not 0 <= bit < BIT_COUNT:
            raise ValueError(f"Bit index must be an integer from 0 to {BIT_COUNT - 1}.")
        if bit in parsed:
            raise ValueError("bit_owners cannot contain duplicate bit indices.")
        parsed[bit] = _parse_player(owner)
    return tuple((bit, parsed[bit]) for bit in range(BIT_COUNT))


def _parse_serialized_bit_owners(
    value: object,
) -> tuple[tuple[int, Player], ...] | None:
    if value is None:
        return None
    data = _require_mapping(value, "bit_owners")
    if set(data) != {str(bit) for bit in range(BIT_COUNT)}:
        raise ValueError("Serialized bit_owners must cover bits '0' through '3'.")
    return _parse_bit_owners(
        {int(bit_str): _parse_player(owner) for bit_str, owner in data.items()}
    )


def _parse_mode(value: object) -> Mode:
    if value == "classic":
        return "classic"
    if value == "self_selection":
        return "self_selection"
    raise ValueError(f"Unknown game mode: {value!r}.")


def _parse_player(value: object) -> Player:
    if value == "player_1":
        return "player_1"
    if value == "player_2":
        return "player_2"
    raise ValueError(f"Unknown player: {value!r}.")


def _parse_optional_player(value: object) -> Player | None:
    return None if value is None else _parse_player(value)


def _parse_phase(value: object) -> Phase:
    if value in ("select", "place", "terminal"):
        return value
    raise ValueError(f"Unknown game phase: {value!r}.")


def _parse_optional_piece(value: object) -> int | None:
    return None if value is None else _require_piece_id(value)


def _parse_optional_cell(value: object) -> int | None:
    return None if value is None else _require_cell(value)


def _require_piece_id(value: object) -> int:
    if type(value) is not int or not 0 <= value < PIECE_COUNT:
        raise ValueError(f"Piece id must be an integer from 0 to {PIECE_COUNT - 1}.")
    return value


def _require_cell(value: object) -> int:
    if type(value) is not int or not 0 <= value < PIECE_COUNT:
        raise ValueError(f"Cell must be an integer from 0 to {PIECE_COUNT - 1}.")
    return value


def _require_bool(value: object, field: str) -> bool:
    if type(value) is not bool:
        raise ValueError(f"{field} must be a boolean.")
    return value


def _require_string(value: object, field: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{field} must be a string.")
    return value


def _require_list(value: object, field: str) -> list[object]:
    if not isinstance(value, list):
        raise ValueError(f"{field} must be a list.")
    return value


def _require_mapping(value: object, field: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping) or any(
        not isinstance(key, str) for key in value
    ):
        raise ValueError(f"{field} must be an object with string keys.")
    return value


def _other_player(player: Player) -> Player:
    return "player_2" if player == "player_1" else "player_1"
