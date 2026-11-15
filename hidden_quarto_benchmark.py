from __future__ import annotations

import csv
from dataclasses import dataclass, field
import hashlib
import itertools
import json
from pathlib import Path
import re
import secrets
import time
from collections.abc import Iterator, Mapping
from types import MappingProxyType
from typing import Literal

from quarto_engine import (
    GameResult,
    GameState,
    Mode,
    Player,
    legal_actions,
    new_game,
    place_piece,
    select_piece,
)


ROOT = Path(__file__).resolve().parent
DATA_DIRECTORY = ROOT / "data"
DATASET_CSV = DATA_DIRECTORY / "pubchem_periodic_table_2026-11-08.csv"
DATASET_METADATA = DATA_DIRECTORY / "pubchem_periodic_table_2026-11-08.metadata.json"
DATASET_VERSION = "pubchem-periodic-table-2026-11-08"
ATTRIBUTE_POOL_VERSION = "chemical-binary-attributes-v1"
DEFAULT_PUBLIC_SEED = 1729
ELEMENT_COUNT = 16
ATTRIBUTE_COUNT = 40
COMBINATION_COUNT = 91_390
DEFAULT_SEED_SEARCH_LIMIT = 1_024
MAX_SEED_SEARCH_LIMIT = 10_000
MIN_VALID_QUARTETS_FOR_AMBIGUITY = 2
PLAYERS = ("player_1", "player_2")
GROUP_BLOCKS = (
    "Actinide",
    "Alkali metal",
    "Alkaline earth metal",
    "Halogen",
    "Lanthanide",
    "Metalloid",
    "Noble gas",
    "Nonmetal",
    "Post-transition metal",
    "Transition metal",
)
STANDARD_STATES = (
    "Gas",
    "Liquid",
    "Solid",
    "Expected to be a Gas",
    "Expected to be a Solid",
)
OXIDATION_STATES = tuple(range(-4, 10))
PERIODS = tuple(range(1, 8))
BLOCKS = ("s", "p", "d", "f")
SOURCE_COLUMNS = (
    "AtomicNumber",
    "Symbol",
    "Name",
    "AtomicMass",
    "CPKHexColor",
    "ElectronConfiguration",
    "Electronegativity",
    "AtomicRadius",
    "IonizationEnergy",
    "ElectronAffinity",
    "OxidationStates",
    "StandardState",
    "MeltingPoint",
    "BoilingPoint",
    "Density",
    "GroupBlock",
    "YearDiscovered",
)

PlayerName = Literal["player_1", "player_2"]
Feedback = Literal["accepted", "rejected"]


class DatasetError(ValueError):
    pass


class InfeasibleSetupError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class AttributeDefinition:
    attribute_id: str
    label: str
    definition: str
    source_field: str
    units: str | None
    value_semantics: str

    def to_public_dict(self) -> dict[str, object]:
        return {
            "attribute_id": self.attribute_id,
            "label": self.label,
            "definition": self.definition,
            "source_field": self.source_field,
            "units": self.units,
            "value_semantics": self.value_semantics,
        }


@dataclass(frozen=True, slots=True)
class ElementRecord:
    atomic_number: int
    symbol: str
    name: str
    standard_state: str
    group_block: str
    oxidation_states: tuple[int, ...]
    electron_configuration: str
    attribute_values: Mapping[str, bool]

    def to_public_dict(self) -> dict[str, object]:
        return {
            "atomic_number": self.atomic_number,
            "symbol": self.symbol,
            "name": self.name,
            "attributes": dict(self.attribute_values),
        }


@dataclass(frozen=True, slots=True)
class ExcludedElement:
    atomic_number: int
    symbol: str
    reason: str


@dataclass(frozen=True, slots=True)
class FrozenDataset:
    version: str
    source_url: str
    retrieved_on: str
    sha256: str
    source_record_count: int
    elements: tuple[ElementRecord, ...]
    excluded_elements: tuple[ExcludedElement, ...]
    attribute_definitions: tuple[AttributeDefinition, ...]


@dataclass(frozen=True, slots=True)
class FeasibilityReport:
    combinations_examined: int
    valid_quartet_count: int
    mathematically_feasible: bool
    hidden_quartet_ambiguity: Literal["none", "unique", "multiple"]


@dataclass(frozen=True, slots=True)
class PreDraftAnalysis:
    report: FeasibilityReport
    _valid_quartets: tuple[tuple[str, ...], ...] = field(repr=False)


@dataclass(frozen=True, slots=True)
class SeedCandidateResult:
    seed: int
    selected_symbols: tuple[str, ...]
    combinations_examined: int
    valid_quartet_count: int
    classification: Literal["zero", "unique", "multiple"]


@dataclass(frozen=True, slots=True)
class SeedSearchReport:
    start_seed: int
    max_candidates: int
    minimum_valid_quartets: int
    candidates: tuple[SeedCandidateResult, ...]
    first_qualifying_candidate: SeedCandidateResult | None
    zero_quartet_candidates: int
    unique_quartet_candidates: int
    multiple_quartet_candidates: int


@dataclass(frozen=True, slots=True)
class OwnedAttribute:
    attribute_id: str
    owner: PlayerName


@dataclass(frozen=True, slots=True)
class ProposalEvent:
    attempt: int
    proposer: PlayerName
    attribute_id: str
    feedback: Feedback
    elapsed_ms: float


@dataclass(frozen=True, slots=True)
class DraftSnapshot:
    accepted: tuple[OwnedAttribute, ...]
    current_player: PlayerName | None
    private_feedback: Mapping[PlayerName, Feedback | None]


@dataclass(frozen=True, slots=True)
class SecretMapping:
    attribute_to_bit: Mapping[str, int] = field(repr=False)
    element_to_piece_id: Mapping[str, int] = field(repr=False)
    permutation: tuple[int, int, int, int] = field(repr=False)


def _attribute_definitions() -> tuple[AttributeDefinition, ...]:
    definitions: list[AttributeDefinition] = []
    for group in GROUP_BLOCKS:
        definitions.append(
            AttributeDefinition(
                attribute_id=f"group_block:{group}",
                label=f"PubChem group block: {group}",
                definition=(
                    "The PubChem GroupBlock field equals this exact source "
                    "classification."
                ),
                source_field="GroupBlock",
                units=None,
                value_semantics="true iff the source field exactly matches the label",
            )
        )
    for state in STANDARD_STATES:
        definitions.append(
            AttributeDefinition(
                attribute_id=f"standard_state:{state}",
                label=f"PubChem standard state: {state}",
                definition=(
                    "The PubChem StandardState field equals this exact source "
                    "classification; 'Expected' labels remain explicitly expected."
                ),
                source_field="StandardState",
                units=None,
                value_semantics="true iff the source field exactly matches the label",
            )
        )
    for oxidation_state in OXIDATION_STATES:
        sign = f"{oxidation_state:+d}" if oxidation_state else "0"
        definitions.append(
            AttributeDefinition(
                attribute_id=f"oxidation_state:{sign}",
                label=f"Reported oxidation state {sign}",
                definition=(
                    "The PubChem OxidationStates field explicitly lists this "
                    "integer oxidation number."
                ),
                source_field="OxidationStates",
                units="oxidation number (dimensionless integer)",
                value_semantics="true iff the parsed source list contains this integer",
            )
        )
    for period in PERIODS:
        definitions.append(
            AttributeDefinition(
                attribute_id=f"period:{period}",
                label=f"Period {period}",
                definition=(
                    "The highest principal shell number in the source electron "
                    "configuration equals this period."
                ),
                source_field="ElectronConfiguration",
                units=None,
                value_semantics="true iff the highest parsed principal shell is this value",
            )
        )
    for block in BLOCKS:
        definitions.append(
            AttributeDefinition(
                attribute_id=f"block:{block}",
                label=f"{block}-block element",
                definition=(
                    "Periodic-table block derived from PubChem GroupBlock; helium "
                    "is assigned to the s-block."
                ),
                source_field="GroupBlock",
                units=None,
                value_semantics="true iff the documented block derivation equals this label",
            )
        )
    if len(definitions) != ATTRIBUTE_COUNT:
        raise RuntimeError("The fixed attribute pool must contain exactly 40 definitions.")
    if len({item.attribute_id for item in definitions}) != ATTRIBUTE_COUNT:
        raise RuntimeError("Attribute identifiers must be unique.")
    return tuple(definitions)


ATTRIBUTE_DEFINITIONS = _attribute_definitions()
ATTRIBUTE_IDS = tuple(item.attribute_id for item in ATTRIBUTE_DEFINITIONS)
_ATTRIBUTE_ID_SET = frozenset(ATTRIBUTE_IDS)
_ORBITAL_TOKEN = re.compile(r"(\d+)([spdf])(\d+)")


def _parse_oxidation_states(raw_value: str, symbol: str) -> tuple[int, ...]:
    if not raw_value.strip():
        raise DatasetError(f"{symbol} has no reported oxidation-state value.")
    values: set[int] = set()
    for raw_state in raw_value.split(","):
        token = raw_state.strip()
        try:
            values.add(int(token))
        except ValueError as error:
            raise DatasetError(
                f"{symbol} has an unrecognized oxidation-state token: {token!r}."
            ) from error
    return tuple(sorted(values))


def _period_from_configuration(configuration: str, symbol: str) -> int:
    tokens = _ORBITAL_TOKEN.findall(configuration)
    if not tokens:
        raise DatasetError(f"{symbol} has no parseable electron configuration.")
    period = max(int(principal_shell) for principal_shell, _, _ in tokens)
    if period not in PERIODS:
        raise DatasetError(
            f"{symbol} has an unsupported principal shell number: {period}."
        )
    return period


def _block_from_group_block(group_block: str, symbol: str) -> str:
    if symbol == "He":
        return "s"
    if group_block in {"Alkali metal", "Alkaline earth metal"}:
        return "s"
    if group_block == "Transition metal":
        return "d"
    if group_block in {"Actinide", "Lanthanide"}:
        return "f"
    if group_block in {
        "Halogen",
        "Metalloid",
        "Noble gas",
        "Nonmetal",
        "Post-transition metal",
    }:
        return "p"
    raise DatasetError(
        f"{symbol} has an unsupported PubChem GroupBlock value: {group_block!r}."
    )


def _element_from_source_row(row: dict[str, str]) -> ElementRecord:
    symbol = row["Symbol"]
    group_block = row["GroupBlock"]
    standard_state = row["StandardState"]
    if group_block not in GROUP_BLOCKS:
        raise DatasetError(
            f"{symbol} has an unsupported PubChem GroupBlock value: {group_block!r}."
        )
    if standard_state not in STANDARD_STATES:
        raise DatasetError(
            f"{symbol} has an unsupported PubChem StandardState value: "
            f"{standard_state!r}."
        )

    oxidation_states = _parse_oxidation_states(row["OxidationStates"], symbol)
    period = _period_from_configuration(row["ElectronConfiguration"], symbol)
    block = _block_from_group_block(group_block, symbol)
    values: dict[str, bool] = {}
    for group in GROUP_BLOCKS:
        values[f"group_block:{group}"] = group_block == group
    for state in STANDARD_STATES:
        values[f"standard_state:{state}"] = standard_state == state
    for oxidation_state in OXIDATION_STATES:
        sign = f"{oxidation_state:+d}" if oxidation_state else "0"
        values[f"oxidation_state:{sign}"] = oxidation_state in oxidation_states
    for selected_period in PERIODS:
        values[f"period:{selected_period}"] = period == selected_period
    for selected_block in BLOCKS:
        values[f"block:{selected_block}"] = block == selected_block
    if set(values) != _ATTRIBUTE_ID_SET or any(type(value) is not bool for value in values.values()):
        raise DatasetError(f"{symbol} does not have exactly 40 binary attributes.")

    return ElementRecord(
        atomic_number=int(row["AtomicNumber"]),
        symbol=symbol,
        name=row["Name"],
        standard_state=standard_state,
        group_block=group_block,
        oxidation_states=oxidation_states,
        electron_configuration=row["ElectronConfiguration"],
        attribute_values=MappingProxyType(values),
    )


def load_dataset(
    csv_path: Path = DATASET_CSV,
    metadata_path: Path = DATASET_METADATA,
) -> FrozenDataset:
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    csv_bytes = csv_path.read_bytes()
    actual_sha256 = hashlib.sha256(csv_bytes).hexdigest()
    if metadata.get("sha256") != actual_sha256:
        raise DatasetError("The frozen dataset SHA-256 does not match its metadata.")
    if metadata.get("record_count") != 118:
        raise DatasetError("The frozen PubChem snapshot must contain 118 records.")

    elements: list[ElementRecord] = []
    excluded: list[ExcludedElement] = []
    seen_symbols: set[str] = set()
    seen_numbers: set[int] = set()
    with csv_path.open(encoding="utf-8", newline="") as stream:
        reader = csv.DictReader(stream)
        if tuple(reader.fieldnames or ()) != SOURCE_COLUMNS:
            raise DatasetError("The frozen dataset columns do not match the schema.")
        for row in reader:
            if row is None:
                raise DatasetError("The dataset contains a malformed CSV row.")
            symbol = row["Symbol"]
            atomic_number = int(row["AtomicNumber"])
            if not symbol or symbol in seen_symbols or atomic_number in seen_numbers:
                raise DatasetError("Element symbols and atomic numbers must be unique.")
            seen_symbols.add(symbol)
            seen_numbers.add(atomic_number)
            if not row["OxidationStates"].strip():
                excluded.append(
                    ExcludedElement(
                        atomic_number=atomic_number,
                        symbol=symbol,
                        reason="source oxidation-state value is missing",
                    )
                )
                continue
            elements.append(_element_from_source_row(row))

    if len(seen_symbols) != 118 or len(seen_numbers) != 118:
        raise DatasetError("The snapshot must contain 118 distinct elements.")
    if len(elements) < ELEMENT_COUNT:
        raise DatasetError("Fewer than 16 complete elements are available.")
    return FrozenDataset(
        version=DATASET_VERSION,
        source_url=str(metadata["source_url"]),
        retrieved_on=str(metadata["retrieved_on"]),
        sha256=actual_sha256,
        source_record_count=len(seen_symbols),
        elements=tuple(elements),
        excluded_elements=tuple(excluded),
        attribute_definitions=ATTRIBUTE_DEFINITIONS,
    )


def select_elements(dataset: FrozenDataset, public_seed: int) -> tuple[ElementRecord, ...]:
    if type(public_seed) is not int:
        raise ValueError("The public seed must be an integer.")
    if len(dataset.elements) < ELEMENT_COUNT:
        raise DatasetError("Fewer than 16 complete elements are available.")
    ranked = sorted(
        dataset.elements,
        key=lambda element: (
            hashlib.sha256(
                (
                    f"{dataset.version}|{public_seed}|"
                    f"{element.atomic_number}"
                ).encode("ascii")
            ).digest(),
            element.atomic_number,
        ),
    )
    return tuple(ranked[:ELEMENT_COUNT])


def _valid_quartets(
    elements: tuple[ElementRecord, ...],
    attribute_ids: tuple[str, ...],
) -> tuple[tuple[str, ...], ...]:
    return tuple(
        tuple(attribute_ids[index] for index in quartet)
        for quartet in _valid_quartet_indices(elements, attribute_ids)
    )


def _valid_quartet_indices(
    elements: tuple[ElementRecord, ...],
    attribute_ids: tuple[str, ...],
) -> Iterator[tuple[int, int, int, int]]:
    # Distinct signatures are equivalent to separating every pair of elements.
    pair_count = len(elements) * (len(elements) - 1) // 2
    complete_pair_mask = (1 << pair_count) - 1
    feature_pair_masks: list[int] = []
    for attribute_id in attribute_ids:
        pair_mask = 0
        pair_index = 0
        for left_index, left in enumerate(elements):
            left_value = left.attribute_values[attribute_id]
            for right in elements[left_index + 1 :]:
                if left_value != right.attribute_values[attribute_id]:
                    pair_mask |= 1 << pair_index
                pair_index += 1
        feature_pair_masks.append(pair_mask)

    for quartet in itertools.combinations(range(len(attribute_ids)), 4):
        pair_mask = (
            feature_pair_masks[quartet[0]]
            | feature_pair_masks[quartet[1]]
            | feature_pair_masks[quartet[2]]
            | feature_pair_masks[quartet[3]]
        )
        if pair_mask == complete_pair_mask:
            yield quartet


def _count_valid_quartets(
    elements: tuple[ElementRecord, ...],
    attribute_ids: tuple[str, ...],
) -> int:
    return sum(1 for _ in _valid_quartet_indices(elements, attribute_ids))


def _classify_valid_quartet_count(
    valid_quartet_count: int,
) -> Literal["zero", "unique", "multiple"]:
    if valid_quartet_count < 0:
        raise ValueError("A valid-quartet count cannot be negative.")
    if valid_quartet_count == 0:
        return "zero"
    if valid_quartet_count == 1:
        return "unique"
    return "multiple"


def analyze_pre_draft(
    elements: tuple[ElementRecord, ...],
    definitions: tuple[AttributeDefinition, ...] = ATTRIBUTE_DEFINITIONS,
) -> PreDraftAnalysis:
    if len(elements) != ELEMENT_COUNT:
        raise ValueError("Pre-draft analysis requires exactly 16 elements.")
    attribute_ids = tuple(definition.attribute_id for definition in definitions)
    if len(definitions) != ATTRIBUTE_COUNT or len(set(attribute_ids)) != ATTRIBUTE_COUNT:
        raise ValueError("Pre-draft analysis requires 40 unique attribute definitions.")
    for element in elements:
        if set(element.attribute_values) != set(attribute_ids):
            raise ValueError(
                f"{element.symbol} is missing one or more binary attribute values."
            )
        if any(type(value) is not bool for value in element.attribute_values.values()):
            raise ValueError(f"{element.symbol} contains a non-binary attribute value.")

    valid = _valid_quartets(elements, attribute_ids)
    count = len(valid)
    ambiguity: Literal["none", "unique", "multiple"]
    if count == 0:
        ambiguity = "none"
    elif count == 1:
        ambiguity = "unique"
    else:
        ambiguity = "multiple"
    return PreDraftAnalysis(
        report=FeasibilityReport(
            combinations_examined=COMBINATION_COUNT,
            valid_quartet_count=count,
            mathematically_feasible=count > 0,
            hidden_quartet_ambiguity=ambiguity,
        ),
        _valid_quartets=valid,
    )


def search_candidate_seeds(
    dataset: FrozenDataset,
    start_seed: int = DEFAULT_PUBLIC_SEED,
    max_candidates: int = DEFAULT_SEED_SEARCH_LIMIT,
) -> SeedSearchReport:
    """Count quartets for ascending public seeds without retaining quartet identities."""
    if type(start_seed) is not int:
        raise ValueError("The starting public seed must be an integer.")
    if type(max_candidates) is not int or not 1 <= max_candidates <= MAX_SEED_SEARCH_LIMIT:
        raise ValueError(
            f"The candidate search bound must be between 1 and {MAX_SEED_SEARCH_LIMIT}."
        )
    attribute_ids = tuple(
        definition.attribute_id for definition in dataset.attribute_definitions
    )
    if (
        len(attribute_ids) != ATTRIBUTE_COUNT
        or len(set(attribute_ids)) != ATTRIBUTE_COUNT
    ):
        raise DatasetError(
            "Candidate search requires 40 uniquely identified binary attributes."
        )
    candidates: list[SeedCandidateResult] = []
    first_qualifying: SeedCandidateResult | None = None
    zero_count = 0
    unique_count = 0
    multiple_count = 0
    for seed in range(start_seed, start_seed + max_candidates):
        selected = select_elements(dataset, seed)
        valid_count = _count_valid_quartets(selected, attribute_ids)
        classification = _classify_valid_quartet_count(valid_count)
        if classification == "zero":
            zero_count += 1
        elif classification == "unique":
            unique_count += 1
        else:
            multiple_count += 1
        candidate = SeedCandidateResult(
            seed=seed,
            selected_symbols=tuple(element.symbol for element in selected),
            combinations_examined=COMBINATION_COUNT,
            valid_quartet_count=valid_count,
            classification=classification,
        )
        candidates.append(candidate)
        if (
            first_qualifying is None
            and valid_count >= MIN_VALID_QUARTETS_FOR_AMBIGUITY
        ):
            first_qualifying = candidate
            break

    return SeedSearchReport(
        start_seed=start_seed,
        max_candidates=max_candidates,
        minimum_valid_quartets=MIN_VALID_QUARTETS_FOR_AMBIGUITY,
        candidates=tuple(candidates),
        first_qualifying_candidate=first_qualifying,
        zero_quartet_candidates=zero_count,
        unique_quartet_candidates=unique_count,
        multiple_quartet_candidates=multiple_count,
    )


def _validate_owned_state(
    accepted: tuple[OwnedAttribute, ...],
    proposer: str,
) -> PlayerName:
    if proposer == "player_1":
        owner: PlayerName = "player_1"
    elif proposer == "player_2":
        owner = "player_2"
    else:
        raise ValueError("Unknown draft owner.")
    identifiers = [item.attribute_id for item in accepted]
    if len(identifiers) != len(set(identifiers)):
        raise ValueError("Accepted attributes must be distinct.")
    counts = {player: 0 for player in PLAYERS}
    for item in accepted:
        if item.owner not in PLAYERS:
            raise ValueError("Accepted attributes must have a valid owner.")
        if item.attribute_id not in _ATTRIBUTE_ID_SET:
            raise ValueError("Accepted attributes must belong to the fixed pool.")
        counts[item.owner] += 1
    if len(accepted) > 4 or any(count > 2 for count in counts.values()):
        raise ValueError("Draft ownership exceeds the two-attributes-per-player limit.")
    if counts[owner] >= 2:
        raise ValueError("The proposer already owns two accepted attributes.")
    return owner


class OwnershipAwareValidator:
    def __init__(self, analysis: PreDraftAnalysis) -> None:
        self._valid_quartets = analysis._valid_quartets

    @property
    def is_feasible(self) -> bool:
        return bool(self._valid_quartets)

    def can_accept(
        self,
        accepted: tuple[OwnedAttribute, ...],
        attribute_id: str,
        proposer: str,
    ) -> bool:
        owner = _validate_owned_state(accepted, proposer)
        if attribute_id not in _ATTRIBUTE_ID_SET:
            return False
        if any(item.attribute_id == attribute_id for item in accepted):
            return False
        tentative = accepted + (OwnedAttribute(attribute_id, owner),)
        ownership_counts = {player: 0 for player in PLAYERS}
        for item in tentative:
            ownership_counts[item.owner] += 1
        for quartet in self._valid_quartets:
            if not all(item.attribute_id in quartet for item in tentative):
                continue
            remaining = set(quartet).difference(
                item.attribute_id for item in tentative
            )
            deficits = {
                player: 2 - ownership_counts[player] for player in PLAYERS
            }
            if sum(deficits.values()) == len(remaining) and all(
                deficit >= 0 for deficit in deficits.values()
            ):
                return True
        return False


class DraftController:
    def __init__(self, validator: OwnershipAwareValidator) -> None:
        if not validator.is_feasible:
            raise InfeasibleSetupError(
                "The pre-draft setup is infeasible; the attribute draft cannot start."
            )
        self._validator = validator
        self._accepted: list[OwnedAttribute] = []
        self._current_player: PlayerName | None = "player_1"
        self._feedback: dict[PlayerName, Feedback | None] = {
            "player_1": None,
            "player_2": None,
        }
        self._events: list[ProposalEvent] = []
        self._attempts = {player: 0 for player in PLAYERS}

    def submit_proposal(self, proposer: str, attribute_id: str) -> Feedback:
        if self._current_player is None:
            raise ValueError("The attribute draft has already completed.")
        if proposer != self._current_player:
            raise ValueError("Only the current proposer may submit an attribute.")
        if proposer == "player_1":
            player: PlayerName = "player_1"
        elif proposer == "player_2":
            player = "player_2"
        else:
            raise ValueError("Unknown draft owner.")
        self._attempts[player] += 1
        accepted = tuple(self._accepted)
        started = time.perf_counter_ns()
        is_accepted = self._validator.can_accept(
            accepted,
            attribute_id,
            player,
        )
        elapsed_ms = (time.perf_counter_ns() - started) / 1_000_000
        feedback: Feedback = "accepted" if is_accepted else "rejected"
        self._feedback[player] = feedback
        self._events.append(
            ProposalEvent(
                attempt=self._attempts[player],
                proposer=player,
                attribute_id=attribute_id,
                feedback=feedback,
                elapsed_ms=elapsed_ms,
            )
        )
        if is_accepted:
            self._accepted.append(OwnedAttribute(attribute_id, player))
            if len(self._accepted) == 4:
                self._current_player = None
            else:
                self._current_player = (
                    "player_2" if player == "player_1" else "player_1"
                )
        return feedback

    def private_snapshot(self, recipient: str) -> DraftSnapshot:
        if recipient == "player_1":
            player: PlayerName = "player_1"
        elif recipient == "player_2":
            player = "player_2"
        else:
            raise ValueError("Unknown private-observation recipient.")
        return DraftSnapshot(
            accepted=tuple(item for item in self._accepted if item.owner == player),
            current_player=self._current_player,
            private_feedback=MappingProxyType(
                {player: self._feedback[player]}
            ),
        )

    def public_draft_status(self) -> dict[str, object]:
        return {
            "phase": "draft",
            "current_player": self._current_player,
        }

    @property
    def is_complete(self) -> bool:
        return self._current_player is None and len(self._accepted) == 4

    def completed_attributes(self) -> tuple[OwnedAttribute, ...]:
        if not self.is_complete:
            raise ValueError("The draft has not accepted four attributes.")
        counts = {player: 0 for player in PLAYERS}
        for item in self._accepted:
            counts[item.owner] += 1
        if counts != {"player_1": 2, "player_2": 2}:
            raise ValueError("A completed draft must assign two attributes per player.")
        return tuple(self._accepted)

    def private_feedback_for(self, recipient: str) -> Feedback | None:
        if recipient == "player_1":
            player: PlayerName = "player_1"
        elif recipient == "player_2":
            player = "player_2"
        else:
            raise ValueError("Unknown private-observation recipient.")
        return self._feedback[player]

    def private_accepted_attributes(self, recipient: str) -> tuple[str, ...]:
        if recipient == "player_1":
            player: PlayerName = "player_1"
        elif recipient == "player_2":
            player = "player_2"
        else:
            raise ValueError("Unknown private-observation recipient.")
        return tuple(
            item.attribute_id for item in self._accepted if item.owner == player
        )

    def private_audit_record(self) -> dict[str, object]:
        return {
            "proposals": [
                {
                    "attempt": event.attempt,
                    "proposer": event.proposer,
                    "attribute_id": event.attribute_id,
                    "feedback": event.feedback,
                    "elapsed_ms": event.elapsed_ms,
                }
                for event in self._events
            ],
            "accepted_attributes": [
                {
                    "attribute_id": item.attribute_id,
                    "owner": item.owner,
                }
                for item in self._accepted
            ],
        }


def create_secret_mapping(
    elements: tuple[ElementRecord, ...],
    accepted_quartet: tuple[str, ...],
    permutation: tuple[int, int, int, int] | None = None,
) -> SecretMapping:
    if len(elements) != ELEMENT_COUNT:
        raise ValueError("A secret mapping requires exactly 16 elements.")
    if len(accepted_quartet) != 4 or len(set(accepted_quartet)) != 4:
        raise ValueError("A secret mapping requires four distinct attributes.")
    if any(attribute_id not in _ATTRIBUTE_ID_SET for attribute_id in accepted_quartet):
        raise ValueError("The quartet contains an attribute outside the fixed pool.")
    if permutation is None:
        sampled_bits = secrets.SystemRandom().sample(range(4), 4)
        permutation = (
            sampled_bits[0],
            sampled_bits[1],
            sampled_bits[2],
            sampled_bits[3],
        )
    if tuple(sorted(permutation)) != (0, 1, 2, 3):
        raise ValueError("The secret bit assignment must be a bijection of four bits.")
    attribute_to_bit = dict(zip(accepted_quartet, permutation))
    element_to_piece_id: dict[str, int] = {}
    for element in elements:
        piece_id = 0
        for attribute_id, bit_index in attribute_to_bit.items():
            if element.attribute_values[attribute_id]:
                piece_id |= 1 << bit_index
        if element.symbol in element_to_piece_id:
            raise ValueError("Public element identifiers must be unique.")
        element_to_piece_id[element.symbol] = piece_id
    if set(element_to_piece_id.values()) != set(range(16)):
        raise InfeasibleSetupError(
            "The accepted quartet does not map the 16 elements bijectively to pieces."
        )
    return SecretMapping(
        attribute_to_bit=MappingProxyType(attribute_to_bit),
        element_to_piece_id=MappingProxyType(element_to_piece_id),
        permutation=permutation,
    )


def sanitize_terminal_result(result: GameResult | None) -> dict[str, object] | None:
    if result is None:
        return None
    return {
        "outcome": result.outcome,
        "winner": result.winner,
        "winning_lines": [
            list(line.cells) for line in result.winning_lines
        ],
    }


def build_draft_public_observation(
    dataset: FrozenDataset,
    elements: tuple[ElementRecord, ...],
    public_seed: int,
    draft: DraftController,
) -> dict[str, object]:
    status = draft.public_draft_status()
    current_player = status["current_player"]
    return {
        "dataset_version": dataset.version,
        "attribute_pool_version": ATTRIBUTE_POOL_VERSION,
        "public_seed": public_seed,
        "elements": [element.to_public_dict() for element in elements],
        "attribute_definitions": [
            definition.to_public_dict()
            for definition in dataset.attribute_definitions
        ],
        "phase": status["phase"],
        "current_player": current_player,
        "legal_actions": (
            {
                "kind": "propose_attribute",
                "attribute_ids": list(ATTRIBUTE_IDS),
            }
            if current_player is not None
            else {"kind": "terminal"}
        ),
    }


def build_draft_private_observation(
    dataset: FrozenDataset,
    elements: tuple[ElementRecord, ...],
    public_seed: int,
    draft: DraftController,
    recipient: str,
) -> dict[str, object]:
    if recipient not in PLAYERS:
        raise ValueError("Unknown private-observation recipient.")
    observation = build_draft_public_observation(
        dataset,
        elements,
        public_seed,
        draft,
    )
    observation["private"] = {
        "accepted_attributes": list(
            draft.private_accepted_attributes(recipient)
        ),
        "proposal_feedback": draft.private_feedback_for(recipient),
    }
    return observation


def permute_piece_id(piece_id: int, permutation: tuple[int, int, int, int]) -> int:
    if type(piece_id) is not int or not 0 <= piece_id < 16:
        raise ValueError("A Quarto piece id must be in the range 0..15.")
    if tuple(sorted(permutation)) != (0, 1, 2, 3):
        raise ValueError("The bit permutation must be a bijection of 0..3.")
    result = 0
    for source_bit, target_bit in enumerate(permutation):
        if piece_id & (1 << source_bit):
            result |= 1 << target_bit
    return result


class HiddenQuartoController:
    def __init__(
        self,
        dataset: FrozenDataset,
        elements: tuple[ElementRecord, ...],
        public_seed: int,
        accepted_attributes: tuple[OwnedAttribute, ...],
        mode: Mode = "classic",
        secret_permutation: tuple[int, int, int, int] | None = None,
        private_feedback: Mapping[Player, Feedback | None] | None = None,
    ) -> None:
        self._dataset = dataset
        self._elements = elements
        self._public_seed = public_seed
        self._analysis = analyze_pre_draft(elements, dataset.attribute_definitions)
        if not self._analysis.report.mathematically_feasible:
            raise InfeasibleSetupError(
                "The selected 16-element setup has no valid four-attribute "
                "quartet; gameplay cannot start."
            )
        if len(accepted_attributes) != 4:
            raise ValueError("The controller requires four accepted attributes.")
        counts = {player: 0 for player in PLAYERS}
        identifiers: set[str] = set()
        for item in accepted_attributes:
            if item.owner not in PLAYERS:
                raise ValueError("Accepted attributes must have a valid owner.")
            if item.attribute_id in identifiers or item.attribute_id not in _ATTRIBUTE_ID_SET:
                raise ValueError("Accepted attributes must be distinct pool members.")
            identifiers.add(item.attribute_id)
            counts[item.owner] += 1
        if counts != {"player_1": 2, "player_2": 2}:
            raise ValueError("Each player must own exactly two accepted attributes.")
        quartet = tuple(item.attribute_id for item in accepted_attributes)
        if not any(set(quartet) == set(valid) for valid in self._analysis._valid_quartets):
            raise InfeasibleSetupError(
                "The accepted attributes are not a valid quartet for this element set."
            )

        self._mapping = create_secret_mapping(
            elements,
            quartet,
            secret_permutation,
        )
        self._symbol_to_piece_id = self._mapping.element_to_piece_id
        self._piece_id_to_symbol = MappingProxyType(
            {piece_id: symbol for symbol, piece_id in self._symbol_to_piece_id.items()}
        )
        self._attribute_ownership = tuple(accepted_attributes)
        self._private_feedback: dict[PlayerName, Feedback | None] = {
            player: (
                None
                if private_feedback is None
                else private_feedback.get(player)
            )
            for player in PLAYERS
        }
        if any(
            feedback not in (None, "accepted", "rejected")
            for feedback in self._private_feedback.values()
        ):
            raise ValueError("Private proposal feedback must use the generic protocol.")
        self._state: GameState = new_game(mode)

    def public_observation(self) -> dict[str, object]:
        engine_actions = legal_actions(self._state)
        action_type = engine_actions.get("type")
        if action_type == "select_piece":
            piece_ids = engine_actions.get("piece_ids")
            if not isinstance(piece_ids, list) or any(
                type(piece_id) is not int for piece_id in piece_ids
            ):
                raise RuntimeError("Engine selection actions have an invalid shape.")
            legal_public_actions: dict[str, object] = {
                "kind": "select_element",
                "element_ids": [
                    self._piece_id_to_symbol[piece_id]
                    for piece_id in piece_ids
                ],
            }
        elif action_type == "place_piece":
            cells = engine_actions.get("cells")
            if not isinstance(cells, list) or any(
                type(cell) is not int for cell in cells
            ):
                raise RuntimeError("Engine placement actions have an invalid shape.")
            legal_public_actions = {
                "kind": "place_element",
                "cells": list(cells),
            }
        elif action_type == "terminal":
            legal_public_actions = {"kind": "terminal"}
        else:
            raise RuntimeError("Engine returned an unknown legal-action type.")

        result = self._state.result
        return {
            "dataset_version": self._dataset.version,
            "attribute_pool_version": ATTRIBUTE_POOL_VERSION,
            "public_seed": self._public_seed,
            "mode": self._state.mode,
            "elements": [element.to_public_dict() for element in self._elements],
            "attribute_definitions": [
                definition.to_public_dict()
                for definition in self._dataset.attribute_definitions
            ],
            "phase": self._state.phase,
            "current_player": self._state.active_player,
            "board": [
                None if piece_id is None else self._piece_id_to_symbol[piece_id]
                for piece_id in self._state.board
            ],
            "available_elements": [
                self._piece_id_to_symbol[piece_id]
                for piece_id in self._state.remaining_pieces
            ],
            "selected_element": (
                None
                if self._state.selected_piece is None
                else self._piece_id_to_symbol[self._state.selected_piece]
            ),
            "legal_actions": legal_public_actions,
            "history": self._public_history(),
            "terminal": sanitize_terminal_result(result),
        }

    def private_observation(self, recipient: str) -> dict[str, object]:
        if recipient == "player_1":
            player: PlayerName = "player_1"
        elif recipient == "player_2":
            player = "player_2"
        else:
            raise ValueError("Unknown private-observation recipient.")
        observation = self.public_observation()
        observation["private"] = {
            "accepted_attributes": [
                item.attribute_id
                for item in self._attribute_ownership
                if item.owner == player
            ],
            "proposal_feedback": self._private_feedback[player],
        }
        return observation

    def submit_action(self, player: str, action: dict[str, object]) -> None:
        if player == "player_1":
            acting_player: PlayerName = "player_1"
        elif player == "player_2":
            acting_player = "player_2"
        else:
            raise ValueError("Unknown action player.")
        if not isinstance(action, dict):
            raise ValueError("An agent action must be a dictionary.")
        kind = action.get("kind")
        if kind == "select_element":
            symbol = action.get("element_id")
            if not isinstance(symbol, str) or symbol not in self._symbol_to_piece_id:
                raise ValueError("Unknown public element identifier.")
            self._state = select_piece(
                self._state,
                acting_player,
                self._symbol_to_piece_id[symbol],
            )
            return
        if kind == "place_element":
            cell = action.get("cell")
            if type(cell) is not int:
                raise ValueError("A public placement action requires an integer cell.")
            self._state = place_piece(
                self._state,
                acting_player,
                cell,
            )
            return
        raise ValueError("Unknown public action kind.")

    def _public_history(self) -> list[dict[str, object]]:
        history: list[dict[str, object]] = []
        for action in self._state.history:
            if action.kind == "select_piece":
                if action.piece_id is None:
                    raise RuntimeError("Engine selection history is malformed.")
                history.append(
                    {
                        "kind": "select_element",
                        "player": action.player,
                        "element_id": self._piece_id_to_symbol[action.piece_id],
                    }
                )
            else:
                history.append(
                    {
                        "kind": "place_element",
                        "player": action.player,
                        "cell": action.cell,
                    }
                )
        return history


def local_experiment_summary(
    dataset: FrozenDataset,
    public_seed: int = DEFAULT_PUBLIC_SEED,
) -> dict[str, object]:
    selected = select_elements(dataset, public_seed)
    analysis = analyze_pre_draft(selected, dataset.attribute_definitions)
    return {
        "dataset_version": dataset.version,
        "public_seed": public_seed,
        "selection_algorithm": (
            "Sort eligible elements by SHA-256(dataset_version|seed|atomic_number); "
            "take the first 16, with atomic number as tie-breaker."
        ),
        "selected_elements": [element.symbol for element in selected],
        "combinations_examined": analysis.report.combinations_examined,
        "valid_quartet_count": analysis.report.valid_quartet_count,
        "mathematically_feasible": analysis.report.mathematically_feasible,
        "hidden_quartet_ambiguity": analysis.report.hidden_quartet_ambiguity,
    }
