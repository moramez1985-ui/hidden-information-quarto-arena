from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any, Literal, Mapping, overload

from phase0_foundation import DomainCatalog, FeatureDefinition, InstanceSpec, PublicEntity

from .dataset_adapter import DatasetAdapter, DatasetAdapterFactory, DatasetDefinition, DatasetSourceData
from .instance_builder import InstanceGenerationResult


class QM9Adapter:
    """Load the frozen local QM9 experiment artifacts into the Phase 0 domain model."""

    def __init__(self, data_dir: str | Path | None = None) -> None:
        root = Path(data_dir) if data_dir is not None else Path(__file__).resolve().parents[1] / "experiments" / "qm9_quarto"
        self.data_dir = Path(root)
        self.provenance = self._read_json(self.data_dir / "dataset_provenance.json")
        self.preprocessing_config = self._read_json(self.data_dir / "preprocessing_config.json")
        self.global_feasibility = self._read_json(self.data_dir / "global_feasibility_results.json")
        self.validation_report = self._read_json(self.data_dir / "validation_report.json")
        self.playable_feature_ids = tuple(self._read_json(self.data_dir / "playable_candidate_features.json")["candidate_feature_ids"])
        self.domain = self.load_domain()

    @staticmethod
    def _read_json(path: Path) -> dict[str, Any]:
        with path.open("r", encoding="utf-8") as handle:
            return json.load(handle)

    @staticmethod
    def _bool_value(value: str) -> bool:
        if isinstance(value, bool):
            return value
        normalized = str(value).strip().lower()
        if normalized == "true":
            return True
        if normalized == "false":
            return False
        raise ValueError(f"Expected a boolean literal, got {value!r}.")

    @staticmethod
    def _as_bool(value: Any) -> bool:
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            normalized = value.strip().lower()
            if normalized == "true":
                return True
            if normalized == "false":
                return False
        raise ValueError(f"Expected a boolean-like value, got {value!r}.")

    def _validate_registry_rows(self, rows: list[dict[str, str]]) -> tuple[str, ...]:
        if not rows:
            raise ValueError("Feature registry is empty.")

        feature_ids = [str(row["feature_id"]).strip() for row in rows]
        if len(feature_ids) != len(set(feature_ids)):
            raise ValueError("Feature registry contains duplicate feature IDs.")
        if len(feature_ids) != 20:
            raise ValueError(f"Expected 20 registry rows; found {len(feature_ids)}.")

        scientific_valid_ids = [
            str(row["feature_id"]).strip()
            for row in rows
            if self._as_bool(row.get("scientifically_valid"))
        ]
        if len(scientific_valid_ids) != 20:
            raise ValueError(
                "Expected exactly 20 scientifically valid registry features; "
                f"found {len(scientific_valid_ids)}."
            )

        gameplay_eligible_ids = [
            str(row["feature_id"]).strip()
            for row in rows
            if self._as_bool(row.get("eligible_for_gameplay"))
        ]
        if len(gameplay_eligible_ids) != 18:
            raise ValueError(
                "Expected exactly 18 gameplay-eligible QM9 features; "
                f"found {len(gameplay_eligible_ids)}."
            )

        constant_ids = [
            str(row["feature_id"]).strip()
            for row in rows
            if self._as_bool(row.get("constant_in_population"))
        ]
        expected_constant_ids = {"contains_carboxylic_acid", "formal_charge_nonzero"}
        if set(constant_ids) != expected_constant_ids:
            raise ValueError(
                "Expected the constant gameplay-excluded feature IDs to be "
                f"{sorted(expected_constant_ids)}, found {sorted(constant_ids)}."
            )

        if set(gameplay_eligible_ids) & set(constant_ids):
            raise ValueError("Gameplay-eligible features must exclude constant features.")

        candidate_ids = tuple(self.playable_feature_ids)
        expected_candidates = tuple(gameplay_eligible_ids)
        if candidate_ids != expected_candidates:
            raise ValueError(
                "playable_candidate_features.json does not match the registry's eligible-for-gameplay list."
            )

        return tuple(feature_ids)

    def _validate_feature_matrix(self, feature_ids: tuple[str, ...], rows: list[dict[str, str]]) -> None:
        if not rows:
            raise ValueError("Feature matrix is empty.")

        header = list(rows[0].keys())
        expected_columns = ["source_id", *feature_ids]
        if set(expected_columns) - set(header):
            raise ValueError("Feature matrix is missing required feature columns.")
        if len(rows) != self.provenance.get("parsed_entity_count"):
            raise ValueError(
                "Feature matrix entity count does not match provenance: "
                f"{len(rows)} != {self.provenance.get('parsed_entity_count')}"
            )

        seen_ids: set[str] = set()
        for row in rows:
            entity_id = str(row.get("source_id", "")).strip()
            if not entity_id:
                raise ValueError("Encountered an empty source_id in the feature matrix.")
            if entity_id in seen_ids:
                raise ValueError(f"Duplicate entity_id found in feature matrix: {entity_id}")
            seen_ids.add(entity_id)

            for feature_id in feature_ids:
                if feature_id not in row:
                    raise ValueError(f"Missing feature column {feature_id!r} for entity {entity_id!r}.")
                self._bool_value(row[feature_id])

    def load_domain(self) -> DomainCatalog:
        feature_registry_path = self.data_dir / "feature_registry.csv"
        feature_matrix_path = self.data_dir / "feature_matrix.csv"

        with feature_registry_path.open("r", encoding="utf-8", newline="") as handle:
            registry_rows = list(csv.DictReader(handle))
        feature_ids = self._validate_registry_rows(registry_rows)

        feature_definitions: list[FeatureDefinition] = []
        for row in registry_rows:
            feature_id = row["feature_id"].strip()
            feature_definitions.append(
                FeatureDefinition(
                    feature_id=feature_id,
                    name=row["name"].strip(),
                    definition=row["definition"].strip(),
                    value_semantics="binary",
                )
            )

        with feature_matrix_path.open("r", encoding="utf-8", newline="") as handle:
            matrix_rows = list(csv.DictReader(handle))
        self._validate_feature_matrix(feature_ids, matrix_rows)

        entity_values: dict[str, dict[str, bool]] = {}
        entities: list[PublicEntity] = []
        for row in matrix_rows:
            entity_id = row["source_id"].strip()
            values: dict[str, bool] = {}
            for feature_id in feature_ids:
                values[feature_id] = self._bool_value(row[feature_id])
            entity_values[entity_id] = values
            entities.append(PublicEntity(entity_id=entity_id, label=entity_id))

        if len(entity_values) != self.provenance.get("parsed_entity_count"):
            raise ValueError(
                "Feature matrix entity count does not match the provenance record count: "
                f"{len(entity_values)} != {self.provenance.get('parsed_entity_count')}"
            )

        definition = DatasetDefinition(
            dataset_id="qm9",
            version=str(self.provenance.get("original_source_url", "qm9-v1")),
            source_name=str(self.provenance.get("source_name", "QM9")),
            source_version=str(self.provenance.get("source_version", "unknown")),
            original_source_url=self.provenance.get("original_source_url"),
            entities=tuple(entities),
            features=tuple(feature_definitions),
            gameplay_feature_ids=self.playable_feature_ids,
            source_feature_ids={feature_id: feature_id for feature_id in feature_ids},
            missing_value_policy="reject",
            generation_policy="strict_quartet_validation",
            provenance=self.provenance,
            metadata={
                "preprocessing_config": self.preprocessing_config,
                "global_feasibility": self.global_feasibility,
                "validation_report": self.validation_report,
            },
            archive_sha256_required=True,
        )
        self.dataset_definition = definition
        self._core_adapter: DatasetAdapter = DatasetAdapterFactory().create(
            definition,
            DatasetSourceData(values=entity_values),
        )
        return self._core_adapter.load_domain()

    @overload
    def build_instance(
        self,
        feature_ids: list[str] | tuple[str, ...] | None = None,
        *,
        seed: int | None = None,
        instance_id: str = "qm9_instance_0",
        return_report: Literal[False] = False,
    ) -> InstanceSpec: ...

    @overload
    def build_instance(
        self,
        feature_ids: list[str] | tuple[str, ...] | None = None,
        *,
        seed: int | None = None,
        instance_id: str = "qm9_instance_0",
        return_report: Literal[True],
    ) -> InstanceGenerationResult: ...

    @overload
    def build_instance(
        self,
        feature_ids: list[str] | tuple[str, ...] | None = None,
        *,
        seed: int | None = None,
        instance_id: str = "qm9_instance_0",
        return_report: bool,
    ) -> InstanceSpec | InstanceGenerationResult: ...

    def build_instance(
        self,
        feature_ids: list[str] | tuple[str, ...] | None = None,
        *,
        seed: int | None = None,
        instance_id: str = "qm9_instance_0",
        return_report: bool = False,
    ) -> InstanceSpec | InstanceGenerationResult:
        return self._core_adapter.build_instance(
            feature_ids=feature_ids,
            seed=seed,
            instance_id=instance_id,
            return_report=return_report,
        )

    def validate_instance(
        self,
        domain: DomainCatalog,
        instance: InstanceSpec,
    ) -> Mapping[str, Any]:
        return self._core_adapter.validate_instance(domain, instance)
