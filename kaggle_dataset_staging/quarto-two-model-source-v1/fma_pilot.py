from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass, replace
from pathlib import Path
from types import MappingProxyType
from typing import Any

from domain_adapters.fma_adapter import (
    FMAAdapter,
    FMA_FROZEN_FEATURES,
    FMA_PILOT_ARCHIVE_SHA256,
    FMA_PILOT_SAMPLE_SEED,
    FMA_PILOT_SAMPLE_SIZE,
)
from domain_adapters.instance_builder import GenericInstanceBuilder
from phase0_foundation import InstanceSpec


PILOT_INSTANCE_ID = "fma_seed11_candidate_ordinal_0003_v1"
PILOT_INSTANCE_PATH = Path(__file__).with_name("fma_pilot_instance.json")
_EXPECTED_FEATURE_IDS = (
    "fma:chroma_cens:mean:01",
    "fma:chroma_cqt:median:11",
    "fma:chroma_stft:skew:05",
    "fma:spectral_bandwidth:min:01",
)
_EXPECTED_THRESHOLDS = (
    0.25517144799232483,
    0.4525887370109558,
    0.3928850293159485,
    290.3798522949219,
)
_EXPECTED_SOURCE_IDS = (
    "53194",
    "104583",
    "74557",
    "111359",
    "112679",
    "10811",
    "139817",
    "149118",
    "70026",
    "107833",
    "47152",
    "151991",
    "36515",
    "69954",
    "134635",
    "43525",
)
_EXPECTED_SIGNATURES = tuple(range(16))
_EXPECTED_PUBLIC_SEED = int.from_bytes(
    hashlib.sha256(PILOT_INSTANCE_ID.encode("utf-8")).digest()[:4],
    "big",
)
_ARTIFACT_FIELDS = {
    "schema_version",
    "candidate_id",
    "public_seed",
    "source",
    "feature_ids",
    "thresholds",
    "entity_ids_signature_order",
    "signature_values_signature_order",
    "strict_validation",
}
_SOURCE_FIELDS = {
    "archive_sha256",
    "sample_size",
    "sample_seed",
    "candidate_report",
    "candidate_report_sha256",
    "candidate_line",
    "candidate_line_sha256",
    "candidate_type",
    "quartet_ordinal",
    "validator_call_number",
}


@dataclass(frozen=True, slots=True)
class FMAPilot:
    adapter: FMAAdapter
    instance: InstanceSpec
    restricted_source_ids: Mapping[str, str]
    validation_record: Mapping[str, Any]


def _read_instance_artifact(path: Path) -> dict[str, Any]:
    try:
        artifact = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise ValueError(f"Could not read the approved FMA pilot artifact: {error}") from error
    if not isinstance(artifact, dict):
        raise ValueError("The approved FMA pilot artifact must be a JSON object.")
    if (
        set(artifact) != _ARTIFACT_FIELDS
        or type(artifact.get("schema_version")) is not int
        or artifact.get("schema_version") != 1
        or artifact.get("candidate_id") != PILOT_INSTANCE_ID
        or type(artifact.get("public_seed")) is not int
        or artifact.get("public_seed") != _EXPECTED_PUBLIC_SEED
    ):
        raise ValueError("The FMA pilot artifact identity or schema is invalid.")

    source = artifact.get("source")
    if not isinstance(source, Mapping) or set(source) != _SOURCE_FIELDS:
        raise ValueError("The FMA pilot artifact has no source provenance.")
    if (
        source.get("archive_sha256") != FMA_PILOT_ARCHIVE_SHA256
        or type(source.get("sample_size")) is not int
        or source.get("sample_size") != FMA_PILOT_SAMPLE_SIZE
        or type(source.get("sample_seed")) is not int
        or source.get("sample_seed") != FMA_PILOT_SAMPLE_SEED
        or source.get("candidate_report")
        != "reports/diagnostics/fma_feasibility_seed11_20261109_204633_336807.jsonl"
        or source.get("candidate_report_sha256")
        != "a1aef3f4822235d949fc3923b10f8c1c0f90d727fce25fabd5242c846aa973f5"
        or source.get("candidate_line") != 4
        or source.get("candidate_line_sha256")
        != "46053e4522f8273202164cda88fdd7743021826c28e3a4312f4c5f4694017a85"
        or source.get("candidate_type") != "initial"
        or type(source.get("candidate_line")) is not int
        or source.get("quartet_ordinal") != 3
        or type(source.get("quartet_ordinal")) is not int
        or type(source.get("validator_call_number")) is not int
        or source.get("validator_call_number") != 3
    ):
        raise ValueError("The FMA pilot artifact source provenance is invalid.")

    feature_ids = artifact.get("feature_ids")
    thresholds = artifact.get("thresholds")
    entity_ids = artifact.get("entity_ids_signature_order")
    signatures = artifact.get("signature_values_signature_order")
    strict_validation = artifact.get("strict_validation")
    if (
        feature_ids != list(_EXPECTED_FEATURE_IDS)
        or thresholds != list(_EXPECTED_THRESHOLDS)
        or entity_ids != list(_EXPECTED_SOURCE_IDS)
        or signatures != list(_EXPECTED_SIGNATURES)
        or not isinstance(strict_validation, dict)
        or set(strict_validation) != {"accepted", "id_level_count", "structural_count"}
        or strict_validation
        != {"accepted": True, "id_level_count": 2, "structural_count": 2}
        or type(strict_validation.get("id_level_count")) is not int
        or type(strict_validation.get("structural_count")) is not int
    ):
        raise ValueError("The FMA pilot artifact does not match the approved candidate.")
    return artifact


def load_fma_pilot(
    archive_path: str | Path,
    *,
    instance_path: str | Path = PILOT_INSTANCE_PATH,
) -> FMAPilot:
    """Load and revalidate the fixed seed-11 FMA candidate without reselection."""
    artifact = _read_instance_artifact(Path(instance_path))
    expected_thresholds = tuple(
        next(
            feature.threshold
            for feature in FMA_FROZEN_FEATURES
            if feature.feature_id == feature_id
        )
        for feature_id in _EXPECTED_FEATURE_IDS
    )
    if expected_thresholds != _EXPECTED_THRESHOLDS:
        raise ValueError("The FMA adapter thresholds differ from the approved candidate.")

    adapter = FMAAdapter(
        archive_path,
        sample_size=FMA_PILOT_SAMPLE_SIZE,
        sample_seed=FMA_PILOT_SAMPLE_SEED,
    )
    domain = adapter.load_domain()
    entity_ids = tuple(artifact["entity_ids_signature_order"])
    if set(entity_ids) - {entity.entity_id for entity in domain.entities}:
        raise ValueError("The approved FMA candidate is not present in the loaded domain.")

    candidate_domain = replace(
        domain,
        entities=tuple(
            next(entity for entity in domain.entities if entity.entity_id == entity_id)
            for entity_id in entity_ids
        ),
        values=MappingProxyType({
            entity_id: domain.values[entity_id]
            for entity_id in entity_ids
        }),
    )
    instance = GenericInstanceBuilder.build_instance(
        candidate_domain,
        feature_ids=_EXPECTED_FEATURE_IDS,
        seed=_EXPECTED_PUBLIC_SEED,
        instance_id=PILOT_INSTANCE_ID,
    )
    if not isinstance(instance, InstanceSpec):
        raise TypeError("The generic instance builder returned an unexpected result.")
    expected_signature_map = {
        entity_id: signature
        for entity_id, signature in zip(
            artifact["entity_ids_signature_order"],
            artifact["signature_values_signature_order"],
        )
    }
    if (
        instance.entity_ids != entity_ids
        or dict(instance.signature_map) != expected_signature_map
        or instance.public_seed != _EXPECTED_PUBLIC_SEED
    ):
        raise ValueError("The generic builder did not reproduce the approved FMA candidate.")

    validation_record = adapter.validate_instance(domain, instance)
    quartet_validation = validation_record.get("quartet_validation")
    if (
        validation_record.get("instance_id") != PILOT_INSTANCE_ID
        or validation_record.get("accepted") is not True
        or getattr(quartet_validation, "accepted", False) is not True
        or getattr(quartet_validation, "id_level_count", None) != 2
        or getattr(quartet_validation, "structural_count", None) != 2
    ):
        raise ValueError("The approved FMA candidate failed strict instance validation.")

    return FMAPilot(
        adapter=adapter,
        instance=instance,
        restricted_source_ids=MappingProxyType({
            entity_id: entity_id for entity_id in entity_ids
        }),
        validation_record=MappingProxyType(dict(validation_record)),
    )


__all__ = ["FMAPilot", "PILOT_INSTANCE_ID", "PILOT_INSTANCE_PATH", "load_fma_pilot"]
