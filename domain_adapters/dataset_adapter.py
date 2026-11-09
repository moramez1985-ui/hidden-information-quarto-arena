from __future__ import annotations

import hashlib
import math
import re
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any, Literal, Mapping, Protocol, overload

from phase0_foundation import DomainCatalog, FeatureDefinition, InstanceSpec, PublicEntity

from .instance_builder import (
    INSTANCE_QUARTET_VALIDATOR_VERSION,
    GenericInstanceBuilder,
    InstanceGenerationResult,
    validate_instance_quartets,
)


def _freeze(value: Any) -> Any:
    if isinstance(value, Mapping):
        return MappingProxyType({key: _freeze(item) for key, item in value.items()})
    if isinstance(value, (list, tuple)):
        return tuple(_freeze(item) for item in value)
    if isinstance(value, set):
        return frozenset(_freeze(item) for item in value)
    return value


def _validate_definition_data(value: Any, path: str) -> None:
    if value is None or isinstance(value, (str, bool, int)):
        return
    if isinstance(value, float) and math.isfinite(value):
        return
    if isinstance(value, Mapping):
        for key, item in value.items():
            if not isinstance(key, str):
                raise ValueError(f"{path} mapping keys must be strings.")
            _validate_definition_data(item, f"{path}.{key}")
        return
    if isinstance(value, (list, tuple)):
        for index, item in enumerate(value):
            _validate_definition_data(item, f"{path}[{index}]")
        return
    raise ValueError(f"{path} must contain only declarative data values.")


@dataclass(frozen=True, slots=True)
class DatasetDefinition:
    """Immutable dataset manifest; operation identifiers never execute definition data."""

    dataset_id: str
    version: str
    source_name: str
    source_version: str
    original_source_url: str | None
    entities: tuple[PublicEntity, ...]
    features: tuple[FeatureDefinition, ...]
    gameplay_feature_ids: tuple[str, ...]
    source_feature_ids: Mapping[str, str]
    missing_value_policy: Literal["reject"]
    generation_policy: Literal["standard", "strict_quartet_validation"]
    source_loader_id: str | None = None
    provenance: Mapping[str, Any] = field(default_factory=dict)
    feature_families: Mapping[str, str] = field(default_factory=dict)
    transformations: Mapping[str, Any] = field(default_factory=dict)
    metadata: Mapping[str, Any] = field(default_factory=dict)
    archive_sha256_required: bool = False

    def __post_init__(self) -> None:
        for field_name in ("entities", "features", "gameplay_feature_ids"):
            object.__setattr__(self, field_name, tuple(getattr(self, field_name)))
        for field_name in (
            "source_feature_ids",
            "provenance",
            "feature_families",
            "transformations",
            "metadata",
        ):
            value = getattr(self, field_name)
            if not isinstance(value, Mapping):
                raise ValueError(f"Dataset definition {field_name} must be a mapping.")
            object.__setattr__(self, field_name, _freeze(value))
        self.validate()

    def validate(self) -> None:
        for field_name in ("dataset_id", "version", "source_name", "source_version"):
            value = getattr(self, field_name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"Dataset definition {field_name} must be a non-empty string.")
        if self.original_source_url is not None and (
            not isinstance(self.original_source_url, str)
            or not self.original_source_url.strip()
        ):
            raise ValueError("Dataset definition original_source_url must be a string or None.")

        if any(not isinstance(entity, PublicEntity) for entity in self.entities):
            raise ValueError("Dataset entities must be PublicEntity records.")
        if any(not isinstance(feature, FeatureDefinition) for feature in self.features):
            raise ValueError("Dataset features must be FeatureDefinition records.")
        entity_ids = [entity.entity_id for entity in self.entities]
        if not entity_ids or any(
            not isinstance(value, str) or not value.strip() for value in entity_ids
        ):
            raise ValueError("Dataset definition requires entities with non-empty string IDs.")
        if any(not isinstance(entity.label, str) or not entity.label.strip() for entity in self.entities):
            raise ValueError("Dataset entity labels must be non-empty strings.")
        if len(entity_ids) != len(set(entity_ids)):
            raise ValueError("Dataset definition contains duplicate entity IDs.")

        feature_ids = [feature.feature_id for feature in self.features]
        if not feature_ids or any(
            not isinstance(value, str) or not value.strip() for value in feature_ids
        ):
            raise ValueError("Dataset definition requires features with non-empty string IDs.")
        if any(
            not isinstance(feature.name, str)
            or not feature.name.strip()
            or not isinstance(feature.definition, str)
            or not feature.definition.strip()
            for feature in self.features
        ):
            raise ValueError("Feature names and definitions must be non-empty strings.")
        if len(feature_ids) != len(set(feature_ids)):
            raise ValueError("Dataset definition contains duplicate feature IDs.")
        if any(feature.value_semantics != "binary" for feature in self.features):
            raise ValueError("Quarto dataset features must declare binary value semantics.")
        if len(self.gameplay_feature_ids) < 4 or len(set(self.gameplay_feature_ids)) != len(
            self.gameplay_feature_ids
        ):
            raise ValueError("Dataset definition requires at least four distinct gameplay features.")
        if any(not isinstance(value, str) or not value.strip() for value in self.gameplay_feature_ids):
            raise ValueError("Gameplay feature IDs must be non-empty strings.")
        if set(self.gameplay_feature_ids) - set(feature_ids):
            raise ValueError("Gameplay feature IDs must be defined in the dataset feature pool.")
        if set(self.source_feature_ids) != set(feature_ids):
            raise ValueError("Source feature mappings must match the defined feature IDs exactly.")
        if any(
            not isinstance(source_id, str) or not source_id.strip()
            for source_id in self.source_feature_ids.values()
        ):
            raise ValueError("Source feature mappings must contain non-empty source identifiers.")
        if set(self.feature_families) - set(feature_ids):
            raise ValueError("Feature family mappings may only reference defined feature IDs.")
        if any(not isinstance(value, str) or not value for value in self.feature_families.values()):
            raise ValueError("Feature family values must be non-empty strings.")
        for field_name in ("provenance", "feature_families", "transformations", "metadata"):
            _validate_definition_data(getattr(self, field_name), field_name)
        if self.missing_value_policy != "reject":
            raise ValueError("The core adapter currently supports only missing_value_policy='reject'.")
        if self.generation_policy not in ("standard", "strict_quartet_validation"):
            raise ValueError(f"Unsupported generation policy: {self.generation_policy!r}.")
        if self.source_loader_id is not None and (
            not isinstance(self.source_loader_id, str) or not self.source_loader_id.strip()
        ):
            raise ValueError("source_loader_id must be a non-empty string or None.")
        if not isinstance(self.archive_sha256_required, bool):
            raise ValueError("archive_sha256_required must be a bool.")


@dataclass(frozen=True, slots=True)
class DatasetSourceData:
    values: Mapping[str, Mapping[str, bool]]

    def __post_init__(self) -> None:
        if not isinstance(self.values, Mapping):
            raise ValueError("Source values must map entity IDs to feature-value mappings.")
        object.__setattr__(self, "values", _freeze(self.values))


class DatasetSourceLoader(Protocol):
    """Trusted application code that converts a source into normalized feature values."""

    def load(self, definition: DatasetDefinition) -> DatasetSourceData: ...


class DatasetAdapter:
    """Reusable adapter behavior over a validated definition and normalized binary data."""

    def __init__(self, definition: DatasetDefinition, source_data: DatasetSourceData) -> None:
        if not isinstance(definition, DatasetDefinition):
            raise TypeError("definition must be a DatasetDefinition.")
        if not isinstance(source_data, DatasetSourceData):
            raise TypeError("source_data must be a DatasetSourceData.")
        definition.validate()
        self.definition = definition
        self.domain = self._build_domain(source_data)
        self.gameplay_feature_ids = definition.gameplay_feature_ids
        self.requires_instance_validation = (
            definition.generation_policy == "strict_quartet_validation"
        )

    def _build_domain(self, source_data: DatasetSourceData) -> DomainCatalog:
        entity_ids = {entity.entity_id for entity in self.definition.entities}
        if set(source_data.values) != entity_ids:
            raise ValueError("Source entity IDs must match the dataset definition exactly.")
        feature_ids = {feature.feature_id for feature in self.definition.features}
        copied_values: dict[str, MappingProxyType[str, bool]] = {}
        for entity_id, values in source_data.values.items():
            if not isinstance(values, Mapping):
                raise ValueError(f"Feature values for entity {entity_id!r} must be a mapping.")
            if set(values) != feature_ids:
                raise ValueError(
                    f"Feature IDs for entity {entity_id!r} must match the dataset definition exactly."
                )
            if not isinstance(values, MappingProxyType):
                raise ValueError(f"Feature values for entity {entity_id!r} must be immutable.")
            for feature_id, value in values.items():
                if type(value) is not bool:
                    raise ValueError(
                        f"Feature value for {entity_id}:{feature_id} must be a bool."
                    )
            copied_values[entity_id] = values
        return DomainCatalog(
            name=self.definition.dataset_id,
            version=self.definition.version,
            entities=self.definition.entities,
            features=self.definition.features,
            values=MappingProxyType(copied_values),
            gameplay_feature_ids=self.definition.gameplay_feature_ids,
        )

    def load_domain(self) -> DomainCatalog:
        return self.domain

    @overload
    def build_instance(
        self,
        feature_ids: list[str] | tuple[str, ...] | None = None,
        *,
        seed: int | None = None,
        instance_id: str = "dataset_instance_0",
        return_report: Literal[False] = False,
    ) -> InstanceSpec: ...

    @overload
    def build_instance(
        self,
        feature_ids: list[str] | tuple[str, ...] | None = None,
        *,
        seed: int | None = None,
        instance_id: str = "dataset_instance_0",
        return_report: Literal[True],
    ) -> InstanceGenerationResult: ...

    @overload
    def build_instance(
        self,
        feature_ids: list[str] | tuple[str, ...] | None = None,
        *,
        seed: int | None = None,
        instance_id: str = "dataset_instance_0",
        return_report: bool,
    ) -> InstanceSpec | InstanceGenerationResult: ...

    def build_instance(
        self,
        feature_ids: list[str] | tuple[str, ...] | None = None,
        *,
        seed: int | None = None,
        instance_id: str = "dataset_instance_0",
        return_report: bool = False,
    ) -> InstanceSpec | InstanceGenerationResult:
        if self.definition.generation_policy == "standard":
            return GenericInstanceBuilder.build_instance(
                self.domain,
                feature_ids=feature_ids,
                seed=seed,
                instance_id=instance_id,
            )

        preferred_quartet = None
        if feature_ids is not None:
            requested_feature_ids = tuple(dict.fromkeys(feature_ids))
            if len(requested_feature_ids) == 4:
                preferred_quartet = requested_feature_ids
            elif set(requested_feature_ids) != set(self.gameplay_feature_ids):
                raise ValueError(
                    "Strict instance generation requires the complete approved gameplay feature pool."
                )
        result = GenericInstanceBuilder.build_instance(
            self.domain,
            feature_ids=self.gameplay_feature_ids,
            seed=seed,
            instance_id=instance_id,
            strict_validation=True,
            eligible_feature_ids=self.gameplay_feature_ids,
            preferred_quartet=preferred_quartet,
            return_report=return_report,
        )
        if return_report and isinstance(result, InstanceGenerationResult):
            return result
        if not isinstance(result, InstanceSpec):
            raise TypeError("Dataset instance generation returned an invalid result.")
        return result

    def validate_instance(
        self,
        domain: DomainCatalog,
        instance: InstanceSpec,
    ) -> Mapping[str, Any]:
        if domain != self.domain:
            raise ValueError("Instance validation requires this dataset's domain catalog.")
        if instance.domain_name != self.definition.dataset_id:
            raise ValueError("Instance domain name must match the dataset definition.")

        archive_hash = self.definition.provenance.get("archive_sha256")
        if self.definition.archive_sha256_required and (
            not isinstance(archive_hash, str)
            or re.fullmatch(r"[0-9a-fA-F]{64}", archive_hash) is None
        ):
            raise ValueError(
                f"{self.definition.dataset_id} provenance must contain a recorded 64-character archive SHA-256."
            )
        result = validate_instance_quartets(
            domain,
            instance,
            self.gameplay_feature_ids,
        )
        pool_digest = hashlib.sha256(
            "\n".join(sorted(set(self.gameplay_feature_ids))).encode("utf-8")
        ).hexdigest()
        identity = {
            "domain_version": domain.version,
            "source_name": self.definition.source_name,
            "source_version": self.definition.source_version,
            "original_source_url": self.definition.original_source_url,
        }
        return _freeze({
            "instance_id": instance.instance_id,
            "dataset_identity": identity,
            "recorded_archive_sha256": archive_hash,
            "archive_hash_verified": (
                self.definition.provenance.get("archive_sha256_verified") is True
            ),
            "validator_version": INSTANCE_QUARTET_VALIDATOR_VERSION,
            "eligible_feature_pool_id": f"sha256:{pool_digest}",
            "quartet_validation": result,
            "id_level_count": result.id_level_count,
            "structural_count": result.structural_count,
            "accepted": result.accepted,
            "rejection_reasons": result.rejection_reasons,
            "structural_equivalence_classes": result.structural_classes,
            "alternative_quartets": result.valid_quartets,
            "selected_signature_coverage": result.selected_signature_coverage,
            "validation_status": "accepted" if result.accepted else "rejected",
        })


class DatasetAdapterFactory:
    """Construct independent dataset adapters from explicit, non-executable definitions."""

    def __init__(
        self,
        *,
        source_loaders: Mapping[str, DatasetSourceLoader] | None = None,
    ) -> None:
        loaders = dict(source_loaders or {})
        for loader_id, loader in loaders.items():
            if not isinstance(loader_id, str) or not loader_id.strip():
                raise ValueError("Registered source loader IDs must be non-empty strings.")
            if not callable(getattr(loader, "load", None)):
                raise TypeError(f"Registered source loader {loader_id!r} must provide load().")
        self._source_loaders = MappingProxyType(loaders)

    def create(
        self,
        definition: DatasetDefinition,
        source_data: DatasetSourceData | None = None,
    ) -> DatasetAdapter:
        if not isinstance(definition, DatasetDefinition):
            raise TypeError("definition must be a DatasetDefinition.")
        definition.validate()
        if definition.source_loader_id is None:
            if source_data is None:
                raise ValueError("Dataset source data is required when no source loader is defined.")
        else:
            if source_data is not None:
                raise ValueError("Provide either source_data or a configured source loader, not both.")
            try:
                loader = self._source_loaders[definition.source_loader_id]
            except KeyError as error:
                raise ValueError(
                    f"Dataset source loader {definition.source_loader_id!r} is not approved by this factory."
                ) from error
            source_data = loader.load(definition)
            if not isinstance(source_data, DatasetSourceData):
                raise TypeError("A dataset source loader must return DatasetSourceData.")
        if not isinstance(source_data, DatasetSourceData):
            raise TypeError("source_data must be DatasetSourceData.")
        return DatasetAdapter(definition, source_data)
