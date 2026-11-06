import random
from pathlib import Path
import tempfile
import unittest

from quarto_engine import MODES, PLAYERS, replay_game
from quarto_runner import (
    MAX_ACTIONS_PER_GAME,
    _save_replays,
    run_game,
    run_games,
)


class QuartoRunnerTests(unittest.TestCase):
    def test_seed_and_mode_repeat_game_history_and_result(self):
        for mode in MODES:
            with self.subTest(mode=mode):
                first = run_game(mode, seed=1729)
                second = run_game(mode, seed=1729)

                self.assertEqual(first.state.history, second.state.history)
                self.assertEqual(first.state.result, second.state.result)

    def test_games_use_legal_actions_and_reach_terminal(self):
        for mode in MODES:
            with self.subTest(mode=mode):
                runs = run_games(mode, seed=314159, games=20)

                self.assertEqual(len(runs), 20)
                for run in runs:
                    self.assertTrue(run.state.is_terminal)
                    self.assertLessEqual(run.action_count, MAX_ACTIONS_PER_GAME)
                    self.assertEqual(run.action_count, len(run.state.history))
                    self.assertTrue(
                        all(action.player in PLAYERS for action in run.state.history)
                    )
                    self.assertEqual(replay_game(run.replay), run.state)

    def test_saved_local_replays_restore_final_states(self):
        runs = run_games("classic", seed=2718, games=3)
        with tempfile.TemporaryDirectory() as temporary_directory:
            replay_dir = Path(temporary_directory) / "replays"
            saved_paths = _save_replays(replay_dir, runs)

            self.assertEqual(len(saved_paths), 3)
            for path, run in zip(saved_paths, runs):
                self.assertEqual(replay_game(path.read_text(encoding="utf-8")), run.state)

    def test_existing_replay_file_is_not_overwritten(self):
        run = run_game("self_selection", seed=1618)
        with tempfile.TemporaryDirectory() as temporary_directory:
            replay_dir = Path(temporary_directory)
            existing_path = replay_dir / "game-0001.json"
            existing_path.write_text("keep this file", encoding="utf-8")

            with self.assertRaises(FileExistsError):
                _save_replays(replay_dir, [run])

            self.assertEqual(
                existing_path.read_text(encoding="utf-8"), "keep this file"
            )

    def test_consecutive_games_do_not_interfere_with_each_other(self):
        for mode in MODES:
            with self.subTest(mode=mode):
                global_random_state = random.getstate()
                batch = run_games(mode, seed=57721, games=4)
                self.assertEqual(random.getstate(), global_random_state)

                individual = [
                    run_game(mode, seed=57721, game_index=index)
                    for index in range(4)
                ]
                self.assertEqual(
                    [run.state for run in batch],
                    [run.state for run in individual],
                )


if __name__ == "__main__":
    unittest.main()
