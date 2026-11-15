from collections.abc import Mapping
import itertools
import unittest

from hidden_quarto_benchmark import (
    ATTRIBUTE_DEFINITIONS,
    ATTRIBUTE_IDS,
    COMBINATION_COUNT,
    DEFAULT_PUBLIC_SEED,
    MAX_SEED_SEARCH_LIMIT,
    DraftController,
    HiddenQuartoController,
    InfeasibleSetupError,
    OwnershipAwareValidator,
    OwnedAttribute,
    analyze_pre_draft,
    _classify_valid_quartet_count,
    load_dataset,
    permute_piece_id,
    search_candidate_seeds,
    sanitize_terminal_result,
    select_elements,
)
from quarto_engine import (
    find_winning_lines,
    new_game,
    place_piece,
    select_piece,
)


def _as_mapping(value: object) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise AssertionError("Expected a mapping.")
    return value


class HiddenQuartoBenchmarkTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dataset = load_dataset()
        cls.elements = select_elements(cls.dataset, DEFAULT_PUBLIC_SEED)
        cls.analysis = analyze_pre_draft(
            cls.elements,
            cls.dataset.attribute_definitions,
        )

    def test_frozen_dataset_and_binary_attribute_schema(self):
        self.assertEqual(self.dataset.source_record_count, 118)
        self.assertEqual(len(self.dataset.elements), 117)
        self.assertEqual(len(self.dataset.excluded_elements), 1)
        self.assertEqual(self.dataset.excluded_elements[0].symbol, "Nh")
        self.assertEqual(len(ATTRIBUTE_DEFINITIONS), 40)
        self.assertEqual(len(set(ATTRIBUTE_IDS)), 40)
        for element in self.dataset.elements:
            self.assertEqual(set(element.attribute_values), set(ATTRIBUTE_IDS))
            self.assertTrue(
                all(type(value) is bool for value in element.attribute_values.values())
            )

    def test_selection_is_seed_deterministic_and_selects_sixteen_elements(self):
        first = select_elements(self.dataset, DEFAULT_PUBLIC_SEED)
        second = select_elements(self.dataset, DEFAULT_PUBLIC_SEED)

        self.assertEqual(first, second)
        self.assertEqual(len(first), 16)
        self.assertEqual(len({element.symbol for element in first}), 16)

    def test_pre_draft_enumerates_every_combination_and_reports_actual_result(self):
        self.assertEqual(self.analysis.report.combinations_examined, COMBINATION_COUNT)
        self.assertEqual(COMBINATION_COUNT, 91_390)
        self.assertEqual(self.analysis.report.valid_quartet_count, 0)
        self.assertFalse(self.analysis.report.mathematically_feasible)
        self.assertEqual(self.analysis.report.hidden_quartet_ambiguity, "none")
        self.assertEqual(len(tuple(itertools.combinations(ATTRIBUTE_IDS, 4))), 91_390)

    def test_pair_coverage_count_matches_direct_signature_enumeration(self):
        direct_count = 0
        for quartet in itertools.combinations(ATTRIBUTE_IDS, 4):
            signatures = {
                sum(
                    int(element.attribute_values[attribute_id]) << bit
                    for bit, attribute_id in enumerate(quartet)
                )
                for element in self.elements
            }
            if len(signatures) == 16:
                direct_count += 1
        self.assertEqual(direct_count, self.analysis.report.valid_quartet_count)

    def test_bounded_seed_search_reports_exact_counts_and_public_samples(self):
        report = search_candidate_seeds(
            self.dataset,
            start_seed=DEFAULT_PUBLIC_SEED,
            max_candidates=3,
        )

        self.assertEqual(report.start_seed, DEFAULT_PUBLIC_SEED)
        self.assertEqual(report.max_candidates, 3)
        self.assertEqual(report.minimum_valid_quartets, 2)
        self.assertEqual([item.seed for item in report.candidates], [1729, 1730, 1731])
        self.assertEqual(
            report.zero_quartet_candidates
            + report.unique_quartet_candidates
            + report.multiple_quartet_candidates,
            3,
        )
        self.assertIsNone(report.first_qualifying_candidate)
        for candidate in report.candidates:
            self.assertEqual(candidate.combinations_examined, COMBINATION_COUNT)
            self.assertEqual(
                candidate.selected_symbols,
                tuple(item.symbol for item in select_elements(self.dataset, candidate.seed)),
            )
            self.assertEqual(
                candidate.classification,
                _classify_valid_quartet_count(candidate.valid_quartet_count),
            )
            self.assertFalse(hasattr(candidate, "valid_quartets"))
        self.assertEqual(_classify_valid_quartet_count(0), "zero")
        self.assertEqual(_classify_valid_quartet_count(1), "unique")
        self.assertEqual(_classify_valid_quartet_count(2), "multiple")

    def test_seed_search_rejects_unbounded_or_invalid_limits(self):
        with self.assertRaisesRegex(ValueError, "between 1 and"):
            search_candidate_seeds(
                self.dataset,
                max_candidates=MAX_SEED_SEARCH_LIMIT + 1,
            )
        with self.assertRaisesRegex(ValueError, "starting public seed"):
            search_candidate_seeds(self.dataset, start_seed=True, max_candidates=1)

    def test_infeasible_seed_blocks_gameplay_explicitly(self):
        attributes = tuple(
            OwnedAttribute(attribute_id, owner)
            for attribute_id, owner in zip(
                ATTRIBUTE_IDS[:4],
                ("player_1", "player_2", "player_1", "player_2"),
            )
        )
        with self.assertRaisesRegex(InfeasibleSetupError, "no valid"):
            HiddenQuartoController(
                self.dataset,
                self.elements,
                DEFAULT_PUBLIC_SEED,
                attributes,
            )

    def test_infeasible_analysis_blocks_draft_before_any_proposal(self):
        validator = OwnershipAwareValidator(self.analysis)
        self.assertFalse(validator.is_feasible)
        with self.assertRaisesRegex(InfeasibleSetupError, "draft cannot start"):
            DraftController(validator)

    def test_invalid_owner_and_duplicate_accepted_attributes_are_rejected(self):
        validator = OwnershipAwareValidator(self.analysis)
        with self.assertRaises(ValueError):
            validator.can_accept((), ATTRIBUTE_IDS[0], "player_3")
        with self.assertRaisesRegex(ValueError, "distinct"):
            validator.can_accept(
                (
                    OwnedAttribute(ATTRIBUTE_IDS[0], "player_1"),
                    OwnedAttribute(ATTRIBUTE_IDS[0], "player_2"),
                ),
                ATTRIBUTE_IDS[1],
                "player_1",
            )

    def test_missing_oxidation_state_is_not_imputed(self):
        from hidden_quarto_benchmark import _parse_oxidation_states

        with self.assertRaisesRegex(ValueError, "no reported"):
            _parse_oxidation_states("", "Nh")

    def test_bit_permutation_preserves_quarto_win_rule_for_all_permutations(self):
        line_cells = (0, 1, 2, 3)
        base_ids = (0, 2, 4, 6)
        for permutation in itertools.permutations(range(4)):
            typed_permutation = (
                permutation[0],
                permutation[1],
                permutation[2],
                permutation[3],
            )
            board: list[int | None] = [None] * 16
            for cell, piece_id in zip(
                line_cells,
                (
                    permute_piece_id(piece, typed_permutation)
                    for piece in base_ids
                ),
            ):
                board[cell] = piece_id
            winning_lines = find_winning_lines(board)
            self.assertEqual(len(winning_lines), 1)
            self.assertEqual(winning_lines[0].cells, line_cells)

    def test_terminal_sanitizer_removes_raw_engine_result_fields(self):
        state = new_game("classic")
        for cell, piece_id in enumerate((0, 2, 4, 6)):
            selected = select_piece(state, state.active_player, piece_id)
            state = place_piece(selected, selected.active_player, cell)

        terminal = sanitize_terminal_result(state.result)
        if terminal is None:
            raise AssertionError("A completed game must have a sanitized result.")

        self.assertEqual(terminal["outcome"], "win")
        self.assertEqual(terminal["winner"], "player_1")
        self.assertEqual(terminal["winning_lines"], [[0, 1, 2, 3]])
        self.assertEqual(
            set(terminal),
            {"outcome", "winner", "winning_lines"},
        )
        self.assertFalse(any(
            key in terminal for key in ("mode", "reason", "shared_attributes", "piece_id")
        ))

    def test_attribute_values_are_complete_for_selected_public_elements(self):
        public_elements = [element.to_public_dict() for element in self.elements]

        self.assertEqual(len(public_elements), 16)
        self.assertTrue(
            all(
                set(_as_mapping(element["attributes"])) == set(ATTRIBUTE_IDS)
                for element in public_elements
            )
        )
        self.assertTrue(
            all(
                type(value) is bool
                for element in public_elements
                for value in _as_mapping(element["attributes"]).values()
            )
        )


if __name__ == "__main__":
    unittest.main()
