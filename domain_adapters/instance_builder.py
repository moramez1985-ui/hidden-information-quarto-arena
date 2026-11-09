from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from itertools import combinations
from random import Random
from types import MappingProxyType

from phase0_foundation import DomainCatalog, InstanceSpec


INSTANCE_QUARTET_VALIDATOR_VERSION = "1"


@dataclass(frozen=True, slots=True)
class QuartetFeasibilityReport:
    candidate_feature_ids: tuple[str, ...]
    quartets_evaluated: int
    feasible_quartets: tuple[tuple[str, ...], ...]
    constructive_instances: tuple[InstanceSpec, ...]
    unique_entity_sets: tuple[tuple[str, ...], ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "candidate_feature_ids": list(self.candidate_feature_ids),
            "quartets_evaluated": self.quartets_evaluated,
            "feasible_quartet_count": len(self.feasible_quartets),
            "feasible_quartets": [list(quartet) for quartet in self.feasible_quartets],
            "constructive_instance_count": len(self.constructive_instances),
            "unique_entity_set_count": len(self.unique_entity_sets),
            "unique_entity_sets": [list(entity_ids) for entity_ids in self.unique_entity_sets],
        }


@dataclass(frozen=True, slots=True)
class QuartetValidationRejection:
    code: str
    message: str


@dataclass(frozen=True, slots=True)
class QuartetStructuralClass:
    key: tuple[int, int, int, int]
    quartets: tuple[tuple[str, str, str, str], ...]


@dataclass(frozen=True, slots=True)
class InstanceQuartetValidation:
    instance_id: str
    entity_ids: tuple[str, ...]
    eligible_feature_ids: tuple[str, ...]
    selected_feature_ids: tuple[str, ...]
    selected_signature_coverage: tuple[int, ...]
    valid_quartets: tuple[tuple[str, str, str, str], ...]
    structural_classes: tuple[QuartetStructuralClass, ...]
    id_level_count: int
    structural_count: int
    accepted: bool
    rejection_reasons: tuple[QuartetValidationRejection, ...]


@dataclass(frozen=True, slots=True)
class InstanceGenerationReport:
    """Aggregate search results for one deterministic selection per feasible quartet."""

    candidate_quartets_total: int
    candidate_quartets_examined: int
    feasible_quartets_found: int
    validated_candidates: int
    rejection_counts: tuple[tuple[str, int], ...]


@dataclass(frozen=True, slots=True)
class InstanceGenerationResult:
    instance: InstanceSpec
    report: InstanceGenerationReport


class InstanceGenerationError(ValueError):
    def __init__(self, report: InstanceGenerationReport) -> None:
        self.report = report
        rejection_summary = ", ".join(
            f"{code}={count}" for code, count in report.rejection_counts
        ) or "none"
        super().__init__(
            "No instance was accepted among the candidates examined using one "
            "deterministic entity selection per feasible initial quartet "
            f"({report.candidate_quartets_examined} of {report.candidate_quartets_total} "
            "quartets examined, "
            f"{report.feasible_quartets_found} feasible, "
            f"{report.validated_candidates} validated); rejections: {rejection_summary}. "
            "This does not establish that no acceptable 16-entity subset exists."
        )


def canonical_quartet_key(feature_masks: Sequence[int]) -> tuple[int, int, int, int]:
    """Canonicalize four entity masks under coordinate permutation and complement."""
    masks = tuple(feature_masks)
    if len(masks) != 4:
        raise ValueError("A structural Quartet key requires exactly four feature masks.")
    if any(type(mask) is not int or not 0 <= mask <= 0xFFFF for mask in masks):
        raise ValueError("Feature masks must be integers in the range 0..65535.")
    return tuple(sorted(min(mask, mask ^ 0xFFFF) for mask in masks))


def validate_instance_quartets(
    domain: DomainCatalog,
    instance: InstanceSpec,
    eligible_feature_ids: Sequence[str],
) -> InstanceQuartetValidation:
    """Count eligible Quartets valid for this exact instance and group structural aliases."""
    if not isinstance(domain, DomainCatalog):
        raise TypeError("A DomainCatalog is required to validate instance Quartets.")
    if not isinstance(instance, InstanceSpec):
        raise TypeError("An InstanceSpec is required to validate instance Quartets.")
    if instance.domain_name != domain.name:
        raise ValueError("Instance domain name must match the domain catalog.")

    entity_ids = tuple(instance.entity_ids)
    if len(entity_ids) != 16:
        raise ValueError("Instance Quartet validation requires exactly 16 entity IDs.")
    if any(not isinstance(entity_id, str) or not entity_id for entity_id in entity_ids):
        raise ValueError("Instance entity IDs must be non-empty strings.")
    if len(set(entity_ids)) != 16:
        raise ValueError("Instance entity IDs must be distinct.")
    normalized_entity_ids = tuple(sorted(entity_ids))

    domain_entity_ids = [entity.entity_id for entity in domain.entities]
    if len(domain_entity_ids) != len(set(domain_entity_ids)):
        raise ValueError("Domain entity IDs must be unique.")
    unknown_entity_ids = set(normalized_entity_ids) - set(domain_entity_ids)
    if unknown_entity_ids:
        raise ValueError(f"Instance contains unknown entity IDs: {sorted(unknown_entity_ids)}.")

    domain_feature_ids = [feature.feature_id for feature in domain.features]
    if len(domain_feature_ids) != len(set(domain_feature_ids)):
        raise ValueError("Domain feature IDs must be unique.")
    known_feature_ids = set(domain_feature_ids)

    supplied_selected_feature_ids = tuple(instance.feature_ids)
    if len(supplied_selected_feature_ids) != 4:
        raise ValueError("Instance must identify exactly four selected feature IDs.")
    if any(not isinstance(feature_id, str) or not feature_id for feature_id in supplied_selected_feature_ids):
        raise ValueError("Selected feature IDs must be non-empty strings.")
    if len(set(supplied_selected_feature_ids)) != 4:
        raise ValueError("Selected feature IDs must be distinct.")
    unknown_selected = set(supplied_selected_feature_ids) - known_feature_ids
    if unknown_selected:
        raise ValueError(f"Instance contains unknown selected feature IDs: {sorted(unknown_selected)}.")
    selected_feature_ids = tuple(sorted(supplied_selected_feature_ids))

    supplied_eligible_ids = tuple(eligible_feature_ids)
    if any(not isinstance(feature_id, str) or not feature_id for feature_id in supplied_eligible_ids):
        raise ValueError("Eligible feature IDs must be non-empty strings.")
    normalized_eligible_ids = tuple(sorted(set(supplied_eligible_ids)))
    if len(normalized_eligible_ids) < 4:
        raise ValueError("At least four distinct eligible feature IDs are required.")
    unknown_eligible = set(normalized_eligible_ids) - known_feature_ids
    if unknown_eligible:
        raise ValueError(f"Eligible feature IDs are unknown to the domain: {sorted(unknown_eligible)}.")
    if set(selected_feature_ids) - set(normalized_eligible_ids):
        raise ValueError("Selected feature IDs must belong to the eligible feature pool.")

    if not isinstance(domain.values, Mapping):
        raise ValueError("Domain values must map entity IDs to feature-value mappings.")
    feature_ids_to_check = set(selected_feature_ids) | set(normalized_eligible_ids)
    for entity_id in normalized_entity_ids:
        feature_values = domain.values.get(entity_id)
        if not isinstance(feature_values, Mapping):
            raise ValueError(f"Feature values for entity {entity_id!r} must be a mapping.")
        for feature_id in feature_ids_to_check:
            if feature_id not in feature_values:
                raise ValueError(f"Missing feature value for {entity_id}:{feature_id}.")
            if type(feature_values[feature_id]) is not bool:
                raise ValueError(f"Feature value for {entity_id}:{feature_id} must be a bool.")

    if set(instance.signature_map) != set(entity_ids):
        raise ValueError("Instance signature map keys must match its entity IDs.")
    for entity_id in entity_ids:
        signature = instance.signature_map[entity_id]
        if type(signature) is not int or not 0 <= signature <= 15:
            raise ValueError(f"Signature for {entity_id} must be an integer in 0..15.")
        expected_signature = sum(
            int(domain.values[entity_id][feature_id]) << bit_index
            for bit_index, feature_id in enumerate(instance.feature_ids)
        )
        if signature != expected_signature:
            raise ValueError(
                f"Signature for {entity_id} does not match instance.feature_ids order."
            )

    feature_masks: dict[str, int] = {}
    for feature_id in normalized_eligible_ids:
        mask = 0
        for entity_index, entity_id in enumerate(normalized_entity_ids):
            if domain.values[entity_id][feature_id]:
                mask |= 1 << entity_index
        feature_masks[feature_id] = mask

    selected_signature_coverage = [0] * 16
    for entity_id in normalized_entity_ids:
        signature = sum(
            int(domain.values[entity_id][feature_id]) << bit_index
            for bit_index, feature_id in enumerate(selected_feature_ids)
        )
        selected_signature_coverage[signature] += 1

    valid_quartets: list[tuple[str, str, str, str]] = []
    quartets_by_key: dict[tuple[int, int, int, int], list[tuple[str, str, str, str]]] = {}
    for quartet in combinations(normalized_eligible_ids, 4):
        signature_counts = [0] * 16
        for entity_index in range(16):
            signature = sum(
                ((feature_masks[feature_id] >> entity_index) & 1) << bit_index
                for bit_index, feature_id in enumerate(quartet)
            )
            signature_counts[signature] += 1
        if signature_counts != [1] * 16:
            continue

        valid_quartet = (quartet[0], quartet[1], quartet[2], quartet[3])
        valid_quartets.append(valid_quartet)
        key = canonical_quartet_key(tuple(feature_masks[feature_id] for feature_id in quartet))
        quartets_by_key.setdefault(key, []).append(valid_quartet)

    structural_classes = tuple(
        QuartetStructuralClass(key=key, quartets=tuple(quartets_by_key[key]))
        for key in sorted(quartets_by_key)
    )
    id_level_count = len(valid_quartets)
    structural_count = len(structural_classes)
    rejection_reasons: list[QuartetValidationRejection] = []
    if id_level_count == 0:
        rejection_reasons.append(QuartetValidationRejection(
            code="no_valid_id_level_quartets",
            message="No eligible four-feature combination covers all 16 signatures exactly once.",
        ))
    elif id_level_count == 1:
        rejection_reasons.append(QuartetValidationRejection(
            code="only_one_id_level_quartet",
            message="The instance has only one valid feature-ID Quartet.",
        ))
    if structural_count == 0:
        rejection_reasons.append(QuartetValidationRejection(
            code="no_structural_classes",
            message="No structurally valid Quartet class exists for the instance.",
        ))
    elif structural_count == 1:
        rejection_reasons.append(QuartetValidationRejection(
            code="only_one_structural_class",
            message="The valid feature-ID Quartets form only one structural class.",
        ))

    return InstanceQuartetValidation(
        instance_id=instance.instance_id,
        entity_ids=normalized_entity_ids,
        eligible_feature_ids=normalized_eligible_ids,
        selected_feature_ids=selected_feature_ids,
        selected_signature_coverage=tuple(selected_signature_coverage),
        valid_quartets=tuple(valid_quartets),
        structural_classes=structural_classes,
        id_level_count=id_level_count,
        structural_count=structural_count,
        accepted=id_level_count > 1 and structural_count > 1,
        rejection_reasons=tuple(rejection_reasons),
    )


class GenericInstanceBuilder:
    """Construct a valid 16-entity Quarto instance from a domain catalog."""

    @staticmethod
    def _validate_strict_domain_data(
        domain: DomainCatalog,
        eligible_feature_ids: Sequence[str],
    ) -> None:
        entity_ids: list[str] = []
        for entity in domain.entities:
            entity_id = getattr(entity, "entity_id", None)
            if not isinstance(entity_id, str) or not entity_id:
                raise ValueError("Domain entity records must have non-empty string IDs.")
            entity_ids.append(entity_id)
        if not entity_ids:
            raise ValueError("Strict instance generation requires domain entities.")
        if len(entity_ids) != len(set(entity_ids)):
            raise ValueError("Domain entity IDs must be unique.")

        feature_ids: list[str] = []
        for feature in domain.features:
            feature_id = getattr(feature, "feature_id", None)
            if not isinstance(feature_id, str) or not feature_id:
                raise ValueError("Domain feature records must have non-empty string IDs.")
            feature_ids.append(feature_id)
        if len(feature_ids) != len(set(feature_ids)):
            raise ValueError("Domain feature IDs must be unique.")

        if not isinstance(domain.values, Mapping):
            raise ValueError("Domain values must map entity IDs to feature-value mappings.")
        if set(domain.values) != set(entity_ids):
            raise ValueError("Domain value records must match the domain entity IDs exactly.")

        for entity_id in entity_ids:
            values = domain.values[entity_id]
            if not isinstance(values, Mapping):
                raise ValueError(f"Feature values for entity {entity_id!r} must be a mapping.")
            for feature_id in eligible_feature_ids:
                if feature_id not in values:
                    raise ValueError(f"Missing feature value for {entity_id}:{feature_id}.")
                if type(values[feature_id]) is not bool:
                    raise ValueError(
                        f"Feature value for {entity_id}:{feature_id} must be a bool."
                    )

    @staticmethod
    def _candidate_feature_ids(domain: DomainCatalog, feature_ids: Sequence[str] | None = None) -> tuple[str, ...]:
        if feature_ids is not None:
            candidates = tuple(feature_ids)
        else:
            gameplay_feature_ids = getattr(domain, "gameplay_feature_ids", None)
            if gameplay_feature_ids is not None:
                candidates = tuple(gameplay_feature_ids)
            else:
                candidates = tuple(feature.feature_id for feature in domain.features)
        unique = tuple(dict.fromkeys(candidates))
        if len(unique) < 4:
            raise ValueError("At least four distinct feature IDs are required to build an instance.")
        return unique

    @staticmethod
    def _signature_for_entity(domain: DomainCatalog, entity_id: str, feature_ids: Sequence[str]) -> int:
        signature = 0
        values = domain.values[entity_id]
        for bit_index, feature_id in enumerate(feature_ids):
            if values[feature_id]:
                signature |= 1 << bit_index
        return signature

    @classmethod
    def _signature_coverage(cls, domain: DomainCatalog, feature_ids: Sequence[str]) -> dict[int, list[str]] | None:
        if len(feature_ids) != 4 or len(set(feature_ids)) != 4:
            return None
        signatures: dict[int, list[str]] = {}
        for entity_id in [entity.entity_id for entity in domain.entities]:
            feature_values = domain.values.get(entity_id)
            if feature_values is None:
                return None
            for feature_id in feature_ids:
                if feature_id not in feature_values:
                    return None
                if not isinstance(feature_values[feature_id], bool):
                    return None
            signature = cls._signature_for_entity(domain, entity_id, feature_ids)
            signatures.setdefault(signature, []).append(entity_id)

        if set(signatures) != set(range(16)):
            return None
        return signatures

    @classmethod
    def _deterministic_quartet_instance(
        cls,
        domain: DomainCatalog,
        quartet: Sequence[str],
        *,
        instance_id: str,
        seed: int | None = None,
        rng: Random | None = None,
        signature_coverage: Mapping[int, Sequence[str]] | None = None,
    ) -> InstanceSpec:
        signatures = signature_coverage
        if signatures is None:
            signatures = cls._signature_coverage(domain, tuple(quartet))
        if signatures is None:
            raise ValueError(f"Quartet {tuple(quartet)!r} does not yield a valid 16-signature coverage.")

        chosen: dict[str, int] = {}
        for signature in range(16):
            available = sorted(signatures.get(signature, ()))
            if not available:
                raise ValueError(f"Quartet {tuple(quartet)!r} does not cover signature {signature}.")
            chosen[rng.choice(available) if rng is not None else available[0]] = signature

        ordered_signature_map = {
            entity_id: int(signature)
            for entity_id, signature in sorted(chosen.items(), key=lambda item: item[1])
        }
        if len(ordered_signature_map) != 16 or set(ordered_signature_map.values()) != set(range(16)):
            raise ValueError("Constructed instance must contain exactly one entity for each 4-bit signature.")

        return InstanceSpec(
            instance_id=instance_id,
            domain_name=domain.name,
            feature_ids=tuple(quartet),
            entity_ids=tuple(ordered_signature_map.keys()),
            signature_map=MappingProxyType(ordered_signature_map),
            public_seed=seed,
        )

    @classmethod
    def analyze_domain(
        cls,
        domain: DomainCatalog,
        feature_ids: Sequence[str] | None = None,
        *,
        instance_id_prefix: str = "quartet",
    ) -> QuartetFeasibilityReport:
        if not isinstance(domain, DomainCatalog):
            raise TypeError("A DomainCatalog is required to analyze feasible quartets.")

        candidate_feature_ids = cls._candidate_feature_ids(domain, feature_ids)
        if len(candidate_feature_ids) <= 4:
            quartet_candidates: Iterable[tuple[str, ...]] = (tuple(candidate_feature_ids),)
        else:
            quartet_candidates = combinations(candidate_feature_ids, 4)

        feasible_quartets: list[tuple[str, ...]] = []
        constructive_instances: list[InstanceSpec] = []
        unique_entity_sets: dict[frozenset[str], tuple[str, ...]] = {}

        for index, quartet in enumerate(quartet_candidates):
            signatures = cls._signature_coverage(domain, tuple(quartet))
            if signatures is None:
                continue
            feasible_quartets.append(tuple(quartet))
            instance = cls._deterministic_quartet_instance(
                domain,
                quartet,
                instance_id=f"{instance_id_prefix}_{index}",
            )
            constructive_instances.append(instance)
            unique_entity_sets[frozenset(instance.entity_ids)] = instance.entity_ids

        return QuartetFeasibilityReport(
            candidate_feature_ids=tuple(candidate_feature_ids),
            quartets_evaluated=len(tuple(combinations(candidate_feature_ids, 4))) if len(candidate_feature_ids) > 4 else 1,
            feasible_quartets=tuple(feasible_quartets),
            constructive_instances=tuple(constructive_instances),
            unique_entity_sets=tuple(unique_entity_sets.values()),
        )

    @classmethod
    def build_instance(
        cls,
        domain: DomainCatalog,
        feature_ids: Sequence[str] | None = None,
        * ,
        seed: int | None = None,
        instance_id: str = "instance_0",
        strict_validation: bool = False,
        eligible_feature_ids: Sequence[str] | None = None,
        preferred_quartet: Sequence[str] | None = None,
        return_report: bool = False,
    ) -> InstanceSpec | InstanceGenerationResult:
        if not isinstance(domain, DomainCatalog):
            raise TypeError("A DomainCatalog is required to build a Quarto instance.")

        if strict_validation:
            return cls._build_strict_instance(
                domain,
                feature_ids,
                eligible_feature_ids=eligible_feature_ids,
                preferred_quartet=preferred_quartet,
                seed=seed,
                instance_id=instance_id,
                return_report=return_report,
            )
        if (
            eligible_feature_ids is not None
            or preferred_quartet is not None
            or return_report
        ):
            raise ValueError(
                "eligible_feature_ids, preferred_quartet, and return_report require strict_validation=True."
            )

        candidate_feature_ids = cls._candidate_feature_ids(domain, feature_ids)
        feature_quartet: tuple[str, ...] | None = None
        quartet_candidates: Iterable[tuple[str, ...]]
        if len(candidate_feature_ids) == 4:
            quartet_candidates = (tuple(candidate_feature_ids),)
        else:
            quartet_candidates = combinations(tuple(candidate_feature_ids), 4)

        selected_signature_map: dict[str, int] | None = None
        selected_feature_ids: tuple[str, ...] | None = None

        for quartet in quartet_candidates:
            signatures = cls._signature_coverage(domain, quartet)
            if signatures is None:
                continue
            entity_ids_by_signature: dict[int, list[str]] = {}
            for signature, entity_ids in signatures.items():
                entity_ids_by_signature[signature] = sorted(entity_ids)
            chosen: dict[str, int] = {}
            rng = Random(seed) if seed is not None else None
            for signature in range(16):
                available = entity_ids_by_signature.get(signature, [])
                if not available:
                    chosen = {}
                    break
                if rng is None:
                    chosen[available[0]] = signature
                else:
                    chosen[rng.choice(available)] = signature
            if len(chosen) == 16:
                selected_signature_map = chosen
                selected_feature_ids = tuple(quartet)
                feature_quartet = tuple(quartet)
                break

        if selected_signature_map is None or selected_feature_ids is None:
            raise ValueError("No structurally valid 16-entity quartet was found for the supplied domain.")

        if feature_quartet is None:
            raise ValueError("No feature quartet selected.")

        entity_ids = tuple(selected_signature_map.keys())
        ordered_signature_map = {entity_id: int(signature) for entity_id, signature in sorted(selected_signature_map.items(), key=lambda item: item[1])}
        if len(ordered_signature_map) != 16 or set(ordered_signature_map.values()) != set(range(16)):
            raise ValueError("Constructed instance must contain exactly one entity for each 4-bit signature.")

        return InstanceSpec(
            instance_id=instance_id,
            domain_name=domain.name,
            feature_ids=selected_feature_ids,
            entity_ids=tuple(ordered_signature_map.keys()),
            signature_map=MappingProxyType(ordered_signature_map),
            public_seed=seed,
        )

    @classmethod
    def _build_strict_instance(
        cls,
        domain: DomainCatalog,
        feature_ids: Sequence[str] | None,
        *,
        eligible_feature_ids: Sequence[str] | None,
        preferred_quartet: Sequence[str] | None,
        seed: int | None,
        instance_id: str,
        return_report: bool,
    ) -> InstanceSpec | InstanceGenerationResult:
        if eligible_feature_ids is None:
            raise ValueError("Strict validation requires the complete eligible feature pool.")
        candidate_feature_ids = tuple(sorted(cls._candidate_feature_ids(domain, eligible_feature_ids)))
        if feature_ids is not None:
            supplied_candidate_ids = cls._candidate_feature_ids(domain, feature_ids)
            if set(supplied_candidate_ids) != set(candidate_feature_ids):
                raise ValueError(
                    "Strict validation must enumerate the complete eligible feature pool."
                )

        known_feature_ids = {feature.feature_id for feature in domain.features}
        unknown_feature_ids = set(candidate_feature_ids) - known_feature_ids
        if unknown_feature_ids:
            raise ValueError(
                f"Eligible feature IDs are unknown to the domain: {sorted(unknown_feature_ids)}."
            )
        cls._validate_strict_domain_data(domain, candidate_feature_ids)

        preferred: tuple[str, ...] | None = None
        if preferred_quartet is not None:
            supplied_preferred = tuple(preferred_quartet)
            if len(supplied_preferred) != 4 or len(set(supplied_preferred)) != 4:
                raise ValueError("preferred_quartet must contain exactly four distinct feature IDs.")
            if set(supplied_preferred) - set(candidate_feature_ids):
                raise ValueError("preferred_quartet must be a subset of the eligible feature pool.")
            preferred = tuple(sorted(supplied_preferred))

        quartets = list(combinations(candidate_feature_ids, 4))
        candidate_quartets_total = len(quartets)
        rng = Random(seed) if seed is not None else None
        if rng is not None:
            rng.shuffle(quartets)
        if preferred is not None:
            quartets.remove(preferred)
            quartets.insert(0, preferred)

        rejection_counts: dict[str, int] = {}
        candidate_quartets_examined = 0
        feasible_quartets_found = 0
        validated_candidates = 0

        for quartet in quartets:
            candidate_quartets_examined += 1
            signatures = cls._signature_coverage(domain, quartet)
            if signatures is None:
                rejection_counts["no_signature_coverage"] = (
                    rejection_counts.get("no_signature_coverage", 0) + 1
                )
                continue

            feasible_quartets_found += 1
            candidate = cls._deterministic_quartet_instance(
                domain,
                quartet,
                instance_id=instance_id,
                seed=seed,
                rng=rng,
                signature_coverage=signatures,
            )
            result = validate_instance_quartets(
                domain,
                candidate,
                candidate_feature_ids,
            )
            validated_candidates += 1
            if result.accepted and result.id_level_count > 1 and result.structural_count > 1:
                report = InstanceGenerationReport(
                    candidate_quartets_total=candidate_quartets_total,
                    candidate_quartets_examined=candidate_quartets_examined,
                    feasible_quartets_found=feasible_quartets_found,
                    validated_candidates=validated_candidates,
                    rejection_counts=tuple(sorted(rejection_counts.items())),
                )
                return (
                    InstanceGenerationResult(candidate, report)
                    if return_report
                    else candidate
                )

            reasons = tuple(reason.code for reason in result.rejection_reasons)
            if result.id_level_count <= 1 and not any(
                reason in ("no_valid_id_level_quartets", "only_one_id_level_quartet")
                for reason in reasons
            ):
                reasons += ("insufficient_id_level_quartets",)
            if result.structural_count <= 1 and not any(
                reason in ("no_structural_classes", "only_one_structural_class")
                for reason in reasons
            ):
                reasons += ("insufficient_structural_classes",)
            if not reasons:
                reasons = ("validator_rejected_candidate",)
            for reason in reasons:
                rejection_counts[reason] = rejection_counts.get(reason, 0) + 1

        report = InstanceGenerationReport(
            candidate_quartets_total=candidate_quartets_total,
            candidate_quartets_examined=candidate_quartets_examined,
            feasible_quartets_found=feasible_quartets_found,
            validated_candidates=validated_candidates,
            rejection_counts=tuple(sorted(rejection_counts.items())),
        )
        raise InstanceGenerationError(report)
