"""Approved FMA Pilot and Arena Instance Loader with Strict Cryptographic and Structural Validation."""
from __future__ import annotations

from functools import lru_cache

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from dataclasses import dataclass, replace
from types import MappingProxyType
from typing import Any, Mapping

from domain_adapters.dataset_adapter import InstanceSpec
from domain_adapters.fma_adapter import (
    FMA_PILOT_ARCHIVE_SHA256 as FMA_PILOT_ARCHIVE_SHA256,
    FMA_FROZEN_FEATURES,
    FMAAdapter,
)
from domain_adapters.instance_builder import GenericInstanceBuilder

PILOT_INSTANCE_ID = "fma_seed11_candidate_ordinal_0003_v1"
PILOT_INSTANCE_PATH = Path(__file__).with_name("fma_pilot_instance.json")

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
        or not isinstance(artifact.get("candidate_id"), str)
        or not artifact["candidate_id"].startswith("fma_")
        or type(artifact.get("public_seed")) is not int
    ):
        raise ValueError("The FMA pilot artifact identity or schema is invalid.")

    source = artifact.get("source")
    required_source_keys = {
        "archive_sha256",
        "sample_size",
        "sample_seed",
        "candidate_report",
        "candidate_line",
        "quartet_ordinal",
    }
    if not isinstance(source, Mapping) or not required_source_keys.issubset(set(source)):
        raise ValueError("The FMA pilot artifact has no source provenance.")
    if (
        source.get("archive_sha256") != FMA_PILOT_ARCHIVE_SHA256
        or type(source.get("sample_size")) is not int
        or source.get("sample_size") < 16
        or type(source.get("sample_seed")) is not int
        or type(source.get("candidate_line")) is not int
        or type(source.get("quartet_ordinal")) is not int
    ):
        raise ValueError("The FMA pilot artifact source provenance is invalid.")

    feature_ids = artifact.get("feature_ids")
    thresholds = artifact.get("thresholds")
    entity_ids = artifact.get("entity_ids_signature_order")
    signatures = artifact.get("signature_values_signature_order")
    strict_validation = artifact.get("strict_validation")

    if (
        not isinstance(feature_ids, list)
        or len(feature_ids) != 4
        or not all(isinstance(f, str) for f in feature_ids)
        or not isinstance(thresholds, list)
        or len(thresholds) != 4
        or not isinstance(entity_ids, list)
        or len(entity_ids) != 16
        or not isinstance(signatures, list)
        or signatures != list(range(16))
        or not isinstance(strict_validation, dict)
        or strict_validation.get("accepted") is not True
        or int(strict_validation.get("id_level_count", 0)) <= 1
        or int(strict_validation.get("structural_count", 0)) <= 1
    ):
        raise ValueError("The FMA pilot artifact does not match the approved candidate requirements.")

    return artifact


def load_fma_pilot(
    archive_path: str | Path,
    *,
    instance_path: str | Path = PILOT_INSTANCE_PATH,
) -> FMAPilot:
    return _load_fma_pilot_cached(str(Path(archive_path).resolve()), str(Path(instance_path).resolve()))


@lru_cache(maxsize=16)
def _load_fma_pilot_cached(
    archive_path: str,
    instance_path: str,
) -> FMAPilot:
    """Load and revalidate any approved FMA pilot or Arena pool instance artifact."""
    artifact = _read_instance_artifact(Path(instance_path))
    cand_id = str(artifact["candidate_id"])
    pub_seed = int(artifact["public_seed"])
    feat_ids = tuple(str(x) for x in artifact["feature_ids"])
    art_thresholds = tuple(float(x) for x in artifact["thresholds"])
    
    src_meta = artifact.get("source", {})
    sample_seed = int(src_meta.get("sample_seed", 11))
    sample_size = int(src_meta.get("sample_size", 25000))

    feature_map = {f.feature_id: float(f.threshold) for f in FMA_FROZEN_FEATURES}
    expected_thresholds = tuple(feature_map[fid] for fid in feat_ids)
    if expected_thresholds != art_thresholds:
        raise ValueError("The FMA adapter thresholds differ from the approved candidate.")

    adapter = FMAAdapter(
        archive_path,
        sample_size=sample_size,
        sample_seed=sample_seed,
        exclude_seed11_sample=(sample_seed == 23),
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
        feature_ids=feat_ids,
        seed=pub_seed,
        instance_id=cand_id,
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
        or instance.public_seed != pub_seed
    ):
        raise ValueError("The generic builder did not reproduce the approved FMA candidate.")

    validation_record = adapter.validate_instance(domain, instance)
    quartet_validation = validation_record.get("quartet_validation")
    if (
        validation_record.get("instance_id") != cand_id
        or validation_record.get("accepted") is not True
        or getattr(quartet_validation, "accepted", False) is not True
        or int(getattr(quartet_validation, "id_level_count", 0) or 0) <= 1
        or int(getattr(quartet_validation, "structural_count", 0) or 0) <= 1
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
