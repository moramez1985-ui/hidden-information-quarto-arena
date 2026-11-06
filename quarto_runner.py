from __future__ import annotations

import argparse
from dataclasses import dataclass
import json
from pathlib import Path
import sys

from quarto_engine import (
    GameState,
    MODES,
    PLAYERS,
    apply_action,
    new_game,
    serialize_replay,
)
from random_agent import RandomAgent


MAX_ACTIONS_PER_GAME = 32


@dataclass(frozen=True, slots=True)
class GameRun:
    state: GameState
    replay: str
    action_count: int


def run_game(mode: str, seed: int, game_index: int = 0) -> GameRun:
    state = new_game(mode)
    agents = {
        "player_1": RandomAgent(seed + game_index * 2),
        "player_2": RandomAgent(seed + game_index * 2 + 1),
    }
    action_count = 0

    while not state.is_terminal:
        if action_count >= MAX_ACTIONS_PER_GAME:
            raise RuntimeError(
                f"Game {game_index + 1} exceeded the "
                f"{MAX_ACTIONS_PER_GAME}-action safety limit."
            )

        player = state.active_player
        action = agents[player].choose_action(state)
        try:
            state = apply_action(state, action)
        except ValueError as error:
            raise RuntimeError(
                f"Game {game_index + 1} produced an invalid action "
                f"for {player}: {action!r}."
            ) from error
        action_count += 1

    return GameRun(
        state=state,
        replay=serialize_replay(state),
        action_count=action_count,
    )


def run_games(mode: str, seed: int, games: int) -> list[GameRun]:
    if type(games) is not int or games < 1:
        raise ValueError("The number of games must be a positive integer.")
    return [run_game(mode, seed, game_index) for game_index in range(games)]


def _save_replays(replay_dir: Path, runs: list[GameRun]) -> list[Path]:
    replay_dir.mkdir(parents=True, exist_ok=True)
    saved_paths = []
    for index, run in enumerate(runs, start=1):
        path = replay_dir / f"game-{index:04d}.json"
        try:
            with path.open("x", encoding="utf-8", newline="\n") as replay_file:
                replay_file.write(run.replay)
                replay_file.write("\n")
        except FileExistsError as error:
            raise FileExistsError(
                f"Replay file already exists; refusing to overwrite: {path}"
            ) from error
        saved_paths.append(path)
    return saved_paths


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Run local random-agent Quarto games. Replays use the project's "
            "local format and are not an official Kaggle format."
        )
    )
    parser.add_argument("--mode", choices=MODES, required=True)
    parser.add_argument("--seed", type=int, required=True)
    parser.add_argument("--games", type=int, required=True)
    parser.add_argument(
        "--replay-dir",
        type=Path,
        help="Optional directory for per-game local replay JSON files.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    if args.games < 1:
        parser.error("--games must be a positive integer.")

    try:
        runs = run_games(args.mode, args.seed, args.games)
        saved_paths = (
            _save_replays(args.replay_dir, runs) if args.replay_dir else []
        )
    except (OSError, RuntimeError, ValueError) as error:
        print(f"Execution error: {error}", file=sys.stderr)
        return 1

    wins = {player: 0 for player in PLAYERS}
    draws = 0
    for index, run in enumerate(runs, start=1):
        result = run.state.result
        if result is None:
            print("Execution error: terminal game has no result.", file=sys.stderr)
            return 1
        if result.outcome == "win":
            if result.winner is None:
                print(
                    "Execution error: winning result has no winner.",
                    file=sys.stderr,
                )
                return 1
            wins[result.winner] += 1
            outcome = f"winner={result.winner}"
        else:
            draws += 1
            outcome = "draw"

        print(
            f"Game {index}: {outcome}; "
            f"{run.action_count} actions; mode={args.mode}"
        )

    print(
        f"Summary: player_1={wins['player_1']}, "
        f"player_2={wins['player_2']}, draws={draws}"
    )
    if args.mode == "classic":
        print(
            "Classic roles: player_1 selects the first piece; "
            "player_2 places the first piece."
        )
    if saved_paths:
        print(
            "Replays saved in the project's local format "
            "(not an official Kaggle format):"
        )
        for path in saved_paths:
            print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
