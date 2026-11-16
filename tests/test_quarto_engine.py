import json
from pathlib import Path
import subprocess
import sys
import textwrap
import unittest

from quarto_engine import (
    deserialize_state,
    legal_actions,
    new_game,
    place_piece,
    replay_game,
    select_piece,
    serialize_replay,
    serialize_state,
)


DRAW_PIECES_BY_CELL = (
    13,
    2,
    10,
    8,
    6,
    3,
    1,
    14,
    7,
    15,
    0,
    9,
    11,
    12,
    4,
    5,
)

LAST_MOVE_WIN_PIECES = (
    10,
    13,
    4,
    9,
    5,
    8,
    7,
    0,
    15,
    6,
    1,
    12,
    3,
    2,
    11,
)


def _play_placement(state, piece_id, cell):
    selected = select_piece(state, state.active_player, piece_id)
    return place_piece(selected, selected.active_player, cell)


class QuartoEngineTests(unittest.TestCase):
    def test_classic_starts_with_player_one_selecting_for_player_two(self):
        state = new_game("classic")

        self.assertEqual(state.active_player, "player_1")
        self.assertEqual(state.phase, "select")
        self.assertIsNone(state.selected_piece)
        self.assertEqual(len(legal_actions(state)["piece_ids"]), 16)

        state = select_piece(state, "player_1", 0)
        self.assertEqual(state.active_player, "player_2")
        self.assertEqual(state.phase, "place")
        self.assertEqual(state.selected_piece, 0)
        self.assertEqual(legal_actions(state)["player"], "player_2")

        state = place_piece(state, "player_2", 0)
        self.assertEqual(state.active_player, "player_2")
        self.assertEqual(state.phase, "select")
        self.assertIsNone(state.selected_piece)

        state = select_piece(state, "player_2", 1)
        self.assertEqual(state.active_player, "player_1")
        self.assertEqual(state.phase, "place")
        state = place_piece(state, "player_1", 1)
        self.assertEqual(state.active_player, "player_1")
        self.assertEqual(state.phase, "select")

    def test_self_selection_keeps_player_active_through_placement(self):
        state = new_game("self_selection")
        self.assertEqual(state.active_player, "player_1")

        state = select_piece(state, "player_1", 0)
        self.assertEqual(state.active_player, "player_1")
        self.assertEqual(state.phase, "place")
        self.assertEqual(state.selected_by, "player_1")

        state = place_piece(state, "player_1", 0)
        self.assertEqual(state.active_player, "player_2")
        self.assertEqual(state.phase, "select")

        state = select_piece(state, "player_2", 1)
        self.assertEqual(state.active_player, "player_2")
        self.assertEqual(state.phase, "place")
        state = place_piece(state, "player_2", 1)
        self.assertEqual(state.active_player, "player_1")
        self.assertEqual(state.phase, "select")

    def test_both_modes_apply_the_same_automatic_win_rule(self):
        for mode, players in (
            ("classic", ("player_2", "player_1", "player_2", "player_1")),
            (
                "self_selection",
                ("player_1", "player_2", "player_1", "player_2"),
            ),
        ):
            with self.subTest(mode=mode):
                state = new_game(mode)
                for piece_id, player, cell in zip(
                    (0, 2, 4, 6), players, (0, 1, 2, 3)
                ):
                    chooser = state.active_player
                    state = select_piece(state, chooser, piece_id)
                    state = place_piece(state, player, cell)

                self.assertTrue(state.is_terminal)
                self.assertEqual(state.result.outcome, "win")
                self.assertEqual(state.result.mode, mode)
                self.assertEqual(state.result.winner, players[-1])
                self.assertEqual(
                    state.result.winning_lines[0].shared_attributes,
                    ("cube", "solid"),
                )

    def test_actions_reject_wrong_player_wrong_phase_used_piece_and_occupied_cell(self):
        state = new_game("classic")
        with self.assertRaises(ValueError):
            select_piece(state, "player_2", 0)
        with self.assertRaises(ValueError):
            place_piece(state, "player_1", 0)

        state = select_piece(state, "player_1", 0)
        with self.assertRaises(ValueError):
            place_piece(state, "player_1", 0)
        state = place_piece(state, "player_2", 0)

        with self.assertRaises(ValueError):
            select_piece(state, "player_2", 0)
        state = select_piece(state, "player_2", 1)
        with self.assertRaises(ValueError):
            place_piece(state, "player_1", 0)

    def test_state_and_replay_round_trip_preserve_mode_and_actions(self):
        for mode in ("classic", "self_selection"):
            for starting_player in ("player_1", "player_2"):
                with self.subTest(mode=mode, starting_player=starting_player):
                    state = new_game(mode, starting_player=starting_player)
                    state = select_piece(state, state.active_player, 3)
                    state = place_piece(state, state.active_player, 5)

                    restored = deserialize_state(serialize_state(state))
                    replayed = replay_game(serialize_replay(state))

                    self.assertEqual(restored, state)
                    self.assertEqual(replayed, state)
                    self.assertEqual(replayed.mode, mode)
                    self.assertEqual(replayed.starting_player, starting_player)

    def test_legacy_state_and_replay_default_to_player_one(self):
        state = new_game("classic")
        serialized_state = json.loads(serialize_state(state))
        serialized_replay = json.loads(serialize_replay(state))
        serialized_state.pop("starting_player")
        serialized_replay.pop("starting_player")

        restored = deserialize_state(json.dumps(serialized_state))
        replayed = replay_game(json.dumps(serialized_replay))

        self.assertEqual(restored.starting_player, "player_1")
        self.assertEqual(replayed.starting_player, "player_1")

    def test_player_two_can_start_in_both_modes(self):
        for mode in ("classic", "self_selection"):
            with self.subTest(mode=mode):
                state = new_game(mode, starting_player="player_2")
                self.assertEqual(state.active_player, "player_2")
                selected = select_piece(state, "player_2", 3)
                expected_placer = "player_1" if mode == "classic" else "player_2"
                self.assertEqual(selected.active_player, expected_placer)
                placed = place_piece(selected, expected_placer, 5)
                expected_next = "player_1" if mode == "classic" else "player_1"
                self.assertEqual(placed.active_player, expected_next)

    def test_invalid_starting_player_is_rejected(self):
        with self.assertRaises(ValueError):
            new_game("classic", starting_player="player_3")

    def test_winning_lines_are_stable_complete_and_isolated(self):
        probe = textwrap.dedent(
            """
            import json

            from quarto_engine import (
                ATTRIBUTE_PAIRS,
                PIECE_COUNT,
                WINNING_LINES,
                find_winning_lines,
                new_game,
                place_piece,
                select_piece,
            )

            lines = tuple(tuple(line) for line in WINNING_LINES)
            empty_board = (None,) * PIECE_COUNT
            empty_results = [
                len(find_winning_lines(empty_board)) for _ in range(3)
            ]

            def play_one_piece(mode):
                state = new_game(mode)
                state = select_piece(state, state.active_player, 0)
                state = place_piece(state, state.active_player, 0)
                return state

            first_game = play_one_piece("classic")
            empty_after_game = len(find_winning_lines(empty_board))
            second_game = play_one_piece("self_selection")

            winning_cases = []
            balanced_patterns = (0b000, 0b011, 0b101, 0b110)
            for cells in lines:
                for attribute_index, pair in enumerate(ATTRIBUTE_PAIRS):
                    for value_index, attribute in enumerate(pair):
                        piece_ids = []
                        for pattern in balanced_patterns:
                            piece_id = 0
                            other_bit_index = 0
                            for bit_index in range(4):
                                if bit_index == attribute_index:
                                    bit_value = value_index
                                else:
                                    bit_value = (pattern >> other_bit_index) & 1
                                    other_bit_index += 1
                                piece_id |= bit_value << bit_index
                            piece_ids.append(piece_id)

                        board = [None] * PIECE_COUNT
                        for cell, piece_id in zip(cells, piece_ids):
                            board[cell] = piece_id
                        wins = find_winning_lines(board)
                        winning_cases.append(
                            len(wins) == 1
                            and wins[0].cells == cells
                            and wins[0].shared_attributes == (attribute,)
                        )

            dispersed_board = [None] * PIECE_COUNT
            for cell, piece_id in zip((0, 1, 2, 3), (0, 7, 9, 14)):
                dispersed_board[cell] = piece_id

            print(json.dumps({
                "lines": lines,
                "line_lengths": [len(line) for line in lines],
                "unique_line_count": len(set(lines)),
                "empty_results": empty_results,
                "empty_after_game": empty_after_game,
                "first_game_terminal": first_game.is_terminal,
                "second_game_terminal": second_game.is_terminal,
                "winning_case_count": len(winning_cases),
                "all_winning_cases_pass": all(winning_cases),
                "dispersed_board_has_no_win": not find_winning_lines(dispersed_board),
            }))
            """
        )
        completed = subprocess.run(
            [sys.executable, "-B", "-c", probe],
            cwd=Path(__file__).resolve().parents[1],
            check=True,
            capture_output=True,
            text=True,
        )
        result = json.loads(completed.stdout)
        expected_lines = [
            [0, 1, 2, 3],
            [4, 5, 6, 7],
            [8, 9, 10, 11],
            [12, 13, 14, 15],
            [0, 4, 8, 12],
            [1, 5, 9, 13],
            [2, 6, 10, 14],
            [3, 7, 11, 15],
            [0, 5, 10, 15],
            [3, 6, 9, 12],
        ]

        self.assertEqual(result["lines"], expected_lines)
        self.assertEqual(result["line_lengths"], [4] * 10)
        self.assertEqual(result["unique_line_count"], 10)
        self.assertEqual(result["empty_results"], [0, 0, 0])
        self.assertEqual(result["empty_after_game"], 0)
        self.assertFalse(result["first_game_terminal"])
        self.assertFalse(result["second_game_terminal"])
        self.assertEqual(result["winning_case_count"], 80)
        self.assertTrue(result["all_winning_cases_pass"])
        self.assertTrue(result["dispersed_board_has_no_win"])

    def test_multiple_turn_order_is_correct_in_both_modes(self):
        for mode in ("classic", "self_selection"):
            with self.subTest(mode=mode):
                state = new_game(mode)
                previous_placer = None

                for cell, piece_id in enumerate(DRAW_PIECES_BY_CELL[:6]):
                    chooser = state.active_player
                    if previous_placer is not None:
                        expected_chooser = (
                            previous_placer
                            if mode == "classic"
                            else (
                                "player_2"
                                if previous_placer == "player_1"
                                else "player_1"
                            )
                        )
                        self.assertEqual(chooser, expected_chooser)

                    selected = select_piece(state, chooser, piece_id)
                    expected_placer = (
                        "player_2" if chooser == "player_1" else "player_1"
                    ) if mode == "classic" else chooser
                    self.assertEqual(selected.active_player, expected_placer)

                    state = place_piece(selected, expected_placer, cell)
                    self.assertFalse(state.is_terminal)
                    self.assertEqual(state.board[cell], piece_id)
                    previous_placer = expected_placer

    def test_actions_preserve_input_state_for_valid_and_invalid_moves(self):
        state = new_game("classic")
        original = state

        selected = select_piece(state, "player_1", 0)
        self.assertEqual(state, original)
        self.assertIsNot(state, selected)

        place_phase_state = selected
        with self.assertRaises(ValueError):
            select_piece(place_phase_state, "player_2", 1)
        self.assertEqual(place_phase_state, selected)

        placed = place_piece(selected, "player_2", 0)
        self.assertEqual(selected, place_phase_state)
        self.assertIsNot(selected, placed)

        select_phase_state = placed
        with self.assertRaises(ValueError):
            place_piece(select_phase_state, "player_2", 1)
        self.assertEqual(select_phase_state, placed)

    def test_all_actions_are_rejected_after_a_legal_win(self):
        state = new_game("classic")
        for cell, piece_id in enumerate((0, 2, 4, 6)):
            state = _play_placement(state, piece_id, cell)

        self.assertTrue(state.is_terminal)
        terminal_state = state
        with self.assertRaises(ValueError):
            select_piece(state, state.active_player, 1)
        self.assertEqual(state, terminal_state)
        with self.assertRaises(ValueError):
            place_piece(state, state.active_player, 4)
        self.assertEqual(state, terminal_state)

    def test_one_placement_can_win_two_lines(self):
        state = new_game("self_selection")
        placements = (
            (0, 4),
            (2, 6),
            (4, 7),
            (6, 1),
            (8, 9),
            (10, 13),
            (12, 5),
        )
        for piece_id, cell in placements:
            state = _play_placement(state, piece_id, cell)

        self.assertTrue(state.is_terminal)
        self.assertEqual(state.result.outcome, "win")
        self.assertEqual(
            tuple(line.cells for line in state.result.winning_lines),
            ((4, 5, 6, 7), (1, 5, 9, 13)),
        )
        self.assertEqual(
            tuple(line.shared_attributes for line in state.result.winning_lines),
            (("cube",), ("cube",)),
        )

    def test_full_legal_game_without_winning_lines_is_a_draw(self):
        for mode in ("classic", "self_selection"):
            with self.subTest(mode=mode):
                state = new_game(mode)
                for cell, piece_id in enumerate(DRAW_PIECES_BY_CELL):
                    state = _play_placement(state, piece_id, cell)
                    if cell < 15:
                        self.assertFalse(state.is_terminal)

                self.assertTrue(state.is_terminal)
                self.assertEqual(state.result.outcome, "draw")
                self.assertEqual(state.result.reason, "board_full")
                self.assertEqual(state.result.winner, None)
                self.assertTrue(all(piece_id is not None for piece_id in state.board))

    def test_win_takes_priority_over_draw_on_the_final_placement(self):
        for mode in ("classic", "self_selection"):
            with self.subTest(mode=mode):
                state = new_game(mode)
                for cell, piece_id in enumerate(LAST_MOVE_WIN_PIECES):
                    state = _play_placement(state, piece_id, cell)
                    self.assertFalse(state.is_terminal)

                self.assertEqual(state.phase, "select")
                self.assertEqual(state.remaining_pieces, (14,))
                state = _play_placement(state, 14, 15)

                self.assertTrue(state.is_terminal)
                self.assertEqual(state.result.outcome, "win")
                self.assertEqual(state.result.reason, "quarto")
                self.assertEqual(state.result.winner, state.active_player)
                self.assertEqual(state.remaining_pieces, ())
                self.assertTrue(all(piece_id is not None for piece_id in state.board))

    def test_state_and_replay_round_trip_every_phase_and_consecutive_games(self):
        replay_inputs = []
        for mode in ("classic", "self_selection"):
            with self.subTest(mode=mode):
                select_state = new_game(mode)
                place_state = select_piece(
                    select_state, select_state.active_player, 13
                )

                win_state = new_game(mode)
                for cell, piece_id in enumerate((0, 2, 4, 6)):
                    win_state = _play_placement(win_state, piece_id, cell)

                draw_state = new_game(mode)
                for cell, piece_id in enumerate(DRAW_PIECES_BY_CELL):
                    draw_state = _play_placement(draw_state, piece_id, cell)

                for state in (
                    select_state,
                    place_state,
                    win_state,
                    draw_state,
                ):
                    self.assertEqual(deserialize_state(serialize_state(state)), state)
                    replay_inputs.append((serialize_replay(state), state))

        for serialized_replay, expected_state in replay_inputs:
            self.assertEqual(replay_game(serialized_replay), expected_state)




    def test_bit_owners_only_win_on_placer_owned_attributes(self) -> None:
        owners = {
            0: "player_1",  # cube / cylinder
            1: "player_2",  # light / dark
            2: "player_1",  # big / small
            3: "player_2",  # solid / hole
        }
        # Part 1: Completing an opponent-owned line does NOT win for the placer;
        # the owner wins on their subsequent placement turn.
        state = new_game(mode="self_selection", bit_owners=owners)
        state = select_piece(state, "player_1", 0)
        state = place_piece(state, "player_1", 0)
        state = select_piece(state, "player_2", 1)
        state = place_piece(state, "player_2", 12)
        state = select_piece(state, "player_1", 2)
        state = place_piece(state, "player_1", 1)
        state = select_piece(state, "player_2", 3)
        state = place_piece(state, "player_2", 13)
        state = select_piece(state, "player_1", 8)
        state = place_piece(state, "player_1", 2)
        # player_2 completes Row 0 (0, 1, 2, 3) with (0, 2, 8, 10) -> shares "cube" & "big" (both player_1)
        state = select_piece(state, "player_2", 10)
        state = place_piece(state, "player_2", 3)

        self.assertFalse(state.is_terminal)
        self.assertIsNone(state.result)
        self.assertEqual(state.active_player, "player_1")

        # On player_1's next placement, player_1 claims the completed player_1-owned line.
        state = select_piece(state, "player_1", 5)
        state = place_piece(state, "player_1", 14)

        self.assertTrue(state.is_terminal)
        assert state.result is not None
        self.assertEqual(state.result.outcome, "win")
        self.assertEqual(state.result.winner, "player_1")
        self.assertEqual(len(state.result.winning_lines), 1)
        self.assertEqual(state.result.winning_lines[0].cells, (0, 1, 2, 3))
        self.assertEqual(state.result.winning_lines[0].shared_attributes, ("cube", "big"))

        # Part 2: When a line shares attributes owned by BOTH players, only the placer's
        # owned attribute is recorded in winning_lines.shared_attributes.
        state2 = new_game(mode="self_selection", bit_owners=owners)
        state2 = select_piece(state2, "player_1", 0)
        state2 = place_piece(state2, "player_1", 0)
        state2 = select_piece(state2, "player_2", 1)
        state2 = place_piece(state2, "player_2", 12)
        state2 = select_piece(state2, "player_1", 2)
        state2 = place_piece(state2, "player_1", 1)
        state2 = select_piece(state2, "player_2", 3)
        state2 = place_piece(state2, "player_2", 13)
        state2 = select_piece(state2, "player_1", 4)
        state2 = place_piece(state2, "player_1", 6)
        state2 = select_piece(state2, "player_2", 5)
        state2 = place_piece(state2, "player_2", 14)
        state2 = select_piece(state2, "player_1", 6)
        state2 = place_piece(state2, "player_1", 7)
        # player_2 places piece 7 at cell 15 -> Row 3 (12, 13, 14, 15) has (1, 3, 5, 7)
        # sharing "cylinder" (bit 0=1, player_1) and "solid" (bit 3=0, player_2).
        state2 = select_piece(state2, "player_2", 7)
        state2 = place_piece(state2, "player_2", 15)

        self.assertTrue(state2.is_terminal)
        assert state2.result is not None
        self.assertEqual(state2.result.outcome, "win")
        self.assertEqual(state2.result.winner, "player_2")
        self.assertEqual(len(state2.result.winning_lines), 1)
        self.assertEqual(state2.result.winning_lines[0].cells, (12, 13, 14, 15))
        self.assertEqual(state2.result.winning_lines[0].shared_attributes, ("solid",))

        round_tripped_state = deserialize_state(serialize_state(state2))
        self.assertEqual(round_tripped_state, state2)
        replayed_state = replay_game(serialize_replay(state2))
        self.assertEqual(replayed_state, state2)

    def test_bit_owners_validation_rejects_incomplete_or_invalid_mappings(self) -> None:
        with self.assertRaises(ValueError):
            new_game(bit_owners={0: "player_1", 1: "player_2"})
        with self.assertRaises(ValueError):
            new_game(bit_owners={0: "player_1", 1: "player_2", 2: "player_1", 4: "player_2"})
        with self.assertRaises(ValueError):
            new_game(bit_owners={0: "player_1", 1: "player_2", 2: "player_1", 3: "player_3"})  # type: ignore[dict-item]


if __name__ == "__main__":
    unittest.main()
