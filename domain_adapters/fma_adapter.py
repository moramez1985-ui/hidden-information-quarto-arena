from __future__ import annotations

import csv
import hashlib
import io
import math
import random
import zipfile
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Any, Literal, Mapping, overload

from phase0_foundation import DomainCatalog, FeatureDefinition, InstanceSpec, PublicEntity

from .dataset_adapter import DatasetAdapter, DatasetAdapterFactory, DatasetDefinition, DatasetSourceData
from .instance_builder import InstanceGenerationResult


FMA_PILOT_ARCHIVE_SHA256 = "d9527a5297a65da31c5676484d5047c3e2b8a8060ce72a46e26158be736bf265"
FMA_PILOT_SAMPLE_SIZE = 25_000
FMA_PILOT_SAMPLE_SEED = 11
FMA_HOLDOUT_SAMPLE_SEED = 23
FMA_PILOT_SAMPLE_MEMBERSHIP_SHA256 = "d0e1496b677d2f5c7aa7bb2870ba4eb388cdfea2298b3dd3893a1d0942724610"
FMA_HOLDOUT_SAMPLE_MEMBERSHIP_SHA256 = "05a78b176c2eb2c703a63207506cc58468e32f9bdf1ac43835e82471a5de31a5"
FMA_FEATURE_POOL_SHA256 = "1f2f4b59f1edda91ac7cfacfd55bc383d9362167b668b02a57e96d090a5600be"
FMA_THRESHOLD_CONFIGURATION_SHA256 = "dfcc00b3b4e780e4271007ae6164792d51824b95a651647d7c3bf7502a9052a6"


@dataclass(frozen=True, slots=True)
class FMAFeature:
    feature_id: str
    family: str
    statistic: str
    coordinate: str
    threshold: float
    interpretation: str

    @property
    def source_column(self) -> tuple[str, str, str]:
        return (self.family, self.statistic, self.coordinate)


FMA_FROZEN_FEATURES = (
    FMAFeature("fma:chroma_cens:mean:01", "chroma_cens", "mean", "01", 0.25517144799232483, "CENS chroma-family audio descriptor; mean statistic for source coordinate 01"),
    FMAFeature("fma:chroma_cqt:median:11", "chroma_cqt", "median", "11", 0.4525887370109558, "constant-Q transform chroma-family audio descriptor; median statistic for source coordinate 11"),
    FMAFeature("fma:chroma_stft:skew:05", "chroma_stft", "skew", "05", 0.3928850293159485, "short-time Fourier transform chroma-family audio descriptor; skew statistic for source coordinate 05"),
    FMAFeature("fma:mfcc:kurtosis:08", "mfcc", "kurtosis", "08", 0.15643799304962158, "mel-frequency cepstral coefficient family; kurtosis statistic for source coordinate 08"),
    FMAFeature("fma:rmse:min:01", "rmse", "min", "01", 3.314237983431667e-05, "root-mean-square energy family; min statistic for source coordinate 01"),
    FMAFeature("fma:spectral_bandwidth:min:01", "spectral_bandwidth", "min", "01", 290.3798522949219, "spectral bandwidth family; min statistic for source coordinate 01"),
    FMAFeature("fma:spectral_centroid:kurtosis:01", "spectral_centroid", "kurtosis", "01", 6.258625030517578, "spectral centroid family; kurtosis statistic for source coordinate 01"),
    FMAFeature("fma:spectral_contrast:skew:07", "spectral_contrast", "skew", "07", -0.40135782957077026, "spectral contrast family; skew statistic for source coordinate 07"),
    FMAFeature("fma:spectral_rolloff:max:01", "spectral_rolloff", "max", "01", 9463.8427734375, "spectral rolloff family; max statistic for source coordinate 01"),
    FMAFeature("fma:tonnetz:skew:05", "tonnetz", "skew", "05", 0.015766769647598267, "tonal centroid (Tonnetz) family; skew statistic for source coordinate 05"),
    FMAFeature("fma:zcr:skew:01", "zcr", "skew", "01", 2.4203286170959473, "zero-crossing-rate family; skew statistic for source coordinate 01"),
    FMAFeature("fma:chroma_cens:kurtosis:12", "chroma_cens", "kurtosis", "12", -0.17919006943702698, "CENS chroma-family audio descriptor; kurtosis statistic for source coordinate 12"),
    FMAFeature("fma:chroma_cqt:kurtosis:08", "chroma_cqt", "kurtosis", "08", -0.7438324689865112, "constant-Q transform chroma-family audio descriptor; kurtosis statistic for source coordinate 08"),
    FMAFeature("fma:chroma_stft:std:09", "chroma_stft", "std", "09", 0.26742768287658691, "short-time Fourier transform chroma-family audio descriptor; std statistic for source coordinate 09"),
    FMAFeature("fma:mfcc:skew:15", "mfcc", "skew", "15", 0.003920631017535925, "mel-frequency cepstral coefficient family; skew statistic for source coordinate 15"),
    FMAFeature("fma:spectral_contrast:max:01", "spectral_contrast", "max", "01", 59.43647766113281, "spectral contrast family; max statistic for source coordinate 01"),
    FMAFeature("fma:tonnetz:skew:03", "tonnetz", "skew", "03", 0.020528830587863922, "tonal centroid (Tonnetz) family; skew statistic for source coordinate 03"),
    FMAFeature("fma:chroma_cens:skew:03", "chroma_cens", "skew", "03", 0.2518020570278168, "CENS chroma-family audio descriptor; skew statistic for source coordinate 03"),
)


class FMAAdapter:
    """Lazy FMA archive loader delegating catalog, generation, and validation to the core.

    Defaults use the seed-11 pilot configuration (25,000 tracks, seed 11). To
    reproduce the seed-23 holdout, use sample_size=25,000, sample_seed=23, and
    exclude_seed11_sample=True. Loading the catalog scans the archive members;
    constructing this adapter does not.
    """

    def __init__(
        self,
        archive_path: str | Path | None = None,
        *,
        sample_size: int = FMA_PILOT_SAMPLE_SIZE,
        sample_seed: int = FMA_PILOT_SAMPLE_SEED,
        exclude_seed11_sample: bool = False,
    ) -> None:
        if type(sample_size) is not int or sample_size < 1:
            raise ValueError("sample_size must be a positive integer.")
        if type(sample_seed) is not int:
            raise ValueError("sample_seed must be an integer.")
        if type(exclude_seed11_sample) is not bool:
            raise ValueError("exclude_seed11_sample must be a bool.")
        root = Path(__file__).resolve().parents[1]
        self.archive_path = (
            Path(archive_path) if archive_path is not None else root / "data" / "fma_metadata.zip"
        )
        self.sample_size = sample_size
        self.sample_seed = sample_seed
        self.exclude_seed11_sample = exclude_seed11_sample
        self.gameplay_feature_ids = tuple(feature.feature_id for feature in FMA_FROZEN_FEATURES)
        self.playable_feature_ids = self.gameplay_feature_ids
        self.requires_instance_validation = True
        self.dataset_definition: DatasetDefinition | None = None
        self.domain: DomainCatalog | None = None
        self.track_metadata: Mapping[str, Mapping[str, str | None]] = MappingProxyType({})
        self.provenance: Mapping[str, Any] = MappingProxyType({})
        self._core_adapter: DatasetAdapter | None = None

    @staticmethod
    def sample_track_ids(
        track_ids: list[int] | tuple[int, ...],
        sample_size: int,
        sample_seed: int,
        *,
        exclude_seed11_sample: bool = False,
    ) -> tuple[int, ...]:
        if type(sample_size) is not int or sample_size < 1:
            raise ValueError("sample_size must be a positive integer.")
        if type(sample_seed) is not int:
            raise ValueError("sample_seed must be an integer.")
        if any(type(track_id) is not int or track_id < 0 for track_id in track_ids):
            raise ValueError("FMA track IDs must be non-negative integers.")
        ordered_ids = sorted(track_ids)
        if len(ordered_ids) != len(set(ordered_ids)):
            raise ValueError("FMA track IDs must be unique.")

        if exclude_seed11_sample:
            if len(ordered_ids) < FMA_PILOT_SAMPLE_SIZE:
                raise ValueError(
                    "Cannot exclude the 25,000-track seed-11 sample from a smaller track pool."
                )
            pilot_ids = set(
                random.Random(FMA_PILOT_SAMPLE_SEED).sample(
                    ordered_ids,
                    FMA_PILOT_SAMPLE_SIZE,
                )
            )
            ordered_ids = [track_id for track_id in ordered_ids if track_id not in pilot_ids]
        if sample_size > len(ordered_ids):
            raise ValueError(
                f"Requested sample size {sample_size} exceeds the available track count {len(ordered_ids)}."
            )
        return tuple(sorted(random.Random(sample_seed).sample(ordered_ids, sample_size)))

    @staticmethod
    def _sha256_file(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as source:
            for block in iter(lambda: source.read(1024 * 1024), b""):
                digest.update(block)
        return digest.hexdigest()

    @staticmethod
    def _read_tracks(
        archive: zipfile.ZipFile,
    ) -> tuple[tuple[int, ...], dict[int, dict[str, str | None]]]:
        member = "fma_metadata/tracks.csv"
        if member not in archive.namelist():
            raise ValueError(f"FMA archive is missing required member {member!r}.")
        metadata_columns = {
            "album": ("album", "title"),
            "artist": ("artist", "name"),
            "title": ("track", "title"),
            "genre_top": ("track", "genre_top"),
            "genres": ("track", "genres"),
        }
        with archive.open(member) as binary:
            with io.TextIOWrapper(binary, encoding="utf-8-sig", newline="") as text:
                reader = csv.reader(text)
                try:
                    headers = [next(reader) for _ in range(3)]
                except StopIteration as error:
                    raise ValueError("FMA tracks.csv has an incomplete header.") from error
                if not all(len(row) == len(headers[0]) for row in headers):
                    raise ValueError("FMA tracks.csv header rows have inconsistent widths.")
                id_columns = [
                    index for index, value in enumerate(headers[2]) if value == "track_id"
                ]
                if len(id_columns) != 1:
                    raise ValueError("FMA tracks.csv must identify exactly one track_id index column.")
                id_index = id_columns[0]
                selected_columns: dict[str, int] = {}
                for name, label in metadata_columns.items():
                    matches = [
                        index for index, (group, field) in enumerate(zip(headers[0], headers[1]))
                        if (group, field) == label
                    ]
                    if len(matches) == 1:
                        selected_columns[name] = matches[0]

                metadata: dict[int, dict[str, str | None]] = {}
                for row_number, row in enumerate(reader, start=4):
                    if not row:
                        continue
                    if len(row) != len(headers[0]):
                        raise ValueError(f"Malformed FMA tracks.csv row {row_number}.")
                    raw_id = row[id_index].strip()
                    if not raw_id.isdecimal():
                        raise ValueError(f"Invalid numeric FMA track ID at row {row_number}: {raw_id!r}.")
                    track_id = int(raw_id)
                    if track_id in metadata:
                        raise ValueError(f"Duplicate FMA track ID {track_id} in tracks.csv.")
                    metadata[track_id] = {
                        name: row[index] if row[index] != "" else None
                        for name, index in selected_columns.items()
                    }
        return tuple(sorted(metadata)), metadata

    @staticmethod
    def _feature_column_indexes(headers: list[list[str]]) -> dict[str, int]:
        if len(headers) != 3 or any(len(row) != len(headers[0]) for row in headers):
            raise ValueError("FMA features.csv must have three consistent hierarchical header rows.")
        index: dict[tuple[str, str, str], list[int]] = {}
        for column in range(1, len(headers[0])):
            label = (headers[0][column], headers[1][column], headers[2][column])
            index.setdefault(label, []).append(column)
        columns: dict[str, int] = {}
        for feature in FMA_FROZEN_FEATURES:
            matches = index.get(feature.source_column, [])
            if len(matches) != 1:
                raise ValueError(
                    f"FMA feature column {feature.source_column!r} must occur exactly once; found {len(matches)}."
                )
            columns[feature.feature_id] = matches[0]
        return columns

    def _read_feature_values(
        self,
        archive: zipfile.ZipFile,
        track_ids: set[int],
        selected_ids: set[int],
    ) -> tuple[dict[int, dict[str, bool]], set[int]]:
        member = "fma_metadata/features.csv"
        if member not in archive.namelist():
            raise ValueError(f"FMA archive is missing required member {member!r}.")
        values_by_id: dict[int, dict[str, bool]] = {}
        feature_track_ids: set[int] = set()
        with archive.open(member) as binary:
            with io.TextIOWrapper(binary, encoding="utf-8-sig", newline="") as text:
                reader = csv.reader(text)
                try:
                    headers = [next(reader) for _ in range(3)]
                    index_name_row = next(reader)
                except StopIteration as error:
                    raise ValueError("FMA features.csv has an incomplete header.") from error
                if not index_name_row or index_name_row[0] != "track_id":
                    raise ValueError("FMA features.csv index name must be track_id.")
                if len(index_name_row) != len(headers[0]):
                    raise ValueError("FMA features.csv index-name row has an inconsistent width.")
                column_indexes = self._feature_column_indexes(headers)
                for row_number, row in enumerate(reader, start=5):
                    if not row:
                        continue
                    if len(row) != len(headers[0]):
                        raise ValueError(f"Malformed FMA features.csv row {row_number}.")
                    raw_id = row[0].strip()
                    if not raw_id.isdecimal():
                        raise ValueError(f"Invalid numeric FMA feature track ID at row {row_number}: {raw_id!r}.")
                    track_id = int(raw_id)
                    if track_id in feature_track_ids:
                        raise ValueError(f"Duplicate FMA track ID {track_id} in features.csv.")
                    feature_track_ids.add(track_id)
                    if track_id not in selected_ids:
                        continue
                    if track_id not in track_ids:
                        raise ValueError(f"FMA feature row has no matching track metadata: {track_id}.")
                    features: dict[str, bool] = {}
                    for feature in FMA_FROZEN_FEATURES:
                        raw_value = row[column_indexes[feature.feature_id]]
                        try:
                            value = float(raw_value)
                        except ValueError as error:
                            raise ValueError(
                                f"Missing or malformed FMA value for track {track_id}, "
                                f"feature {feature.feature_id}."
                            ) from error
                        if not math.isfinite(value):
                            raise ValueError(
                                f"Non-finite FMA value for track {track_id}, feature {feature.feature_id}."
                            )
                        features[feature.feature_id] = value > feature.threshold
                    values_by_id[track_id] = features
        return values_by_id, feature_track_ids

    def load_domain(self) -> DomainCatalog:
        if self._core_adapter is not None:
            return self._core_adapter.load_domain()

        actual_archive_hash = self._sha256_file(self.archive_path)
        if actual_archive_hash != FMA_PILOT_ARCHIVE_SHA256:
            raise ValueError(
                "FMA metadata archive SHA-256 does not match the recorded seed-11 pilot "
                f"({actual_archive_hash} != {FMA_PILOT_ARCHIVE_SHA256})."
            )

        with zipfile.ZipFile(self.archive_path, "r") as archive:
            all_track_ids, all_metadata = self._read_tracks(archive)
            sample_ids = self.sample_track_ids(
                all_track_ids,
                self.sample_size,
                self.sample_seed,
                exclude_seed11_sample=self.exclude_seed11_sample,
            )
            selected_id_set = set(sample_ids)
            source_values, feature_track_ids = self._read_feature_values(
                archive,
                set(all_track_ids),
                selected_id_set,
            )
        track_ids_set = set(all_track_ids)
        if feature_track_ids != track_ids_set:
            raise ValueError(
                "FMA tracks.csv and features.csv must contain identical numeric track ID sets."
            )
        if set(source_values) != selected_id_set:
            missing = sorted(selected_id_set - set(source_values))
            raise ValueError(f"FMA selected tracks are missing feature rows: {missing[:10]}.")

        provenance = {
            "source_name": "Free Music Archive metadata",
            "source_version": "fma_metadata.zip",
            "original_source_url": "https://github.com/mdeff/fma",
            "archive_path": str(self.archive_path),
            "archive_sha256": actual_archive_hash,
            "archive_sha256_verified": True,
            "feature_selection_source": (
                "reports/diagnostics/fma_feasibility_seed11_20261109_204633_336807.jsonl"
            ),
            "feature_pool_sha256": FMA_FEATURE_POOL_SHA256,
            "threshold_configuration_sha256": FMA_THRESHOLD_CONFIGURATION_SHA256,
            "threshold_source_seed": FMA_PILOT_SAMPLE_SEED,
            "threshold_rule": "value > frozen seed-11 sample median; ties are false",
            "sample_size": self.sample_size,
            "sample_seed": self.sample_seed,
            "sample_ids_sorted_numeric": True,
            "sample_membership_sha256": hashlib.sha256(
                "\n".join(str(track_id) for track_id in sample_ids).encode("utf-8")
            ).hexdigest(),
            "sampling_procedure": (
                "Sort numeric track IDs, random.Random(sample_seed).sample without "
                "replacement, then sort selected IDs numerically."
            ),
            "exclude_seed11_sample": self.exclude_seed11_sample,
            "excluded_seed11_sample_size": (
                FMA_PILOT_SAMPLE_SIZE if self.exclude_seed11_sample else 0
            ),
            "sample_design": (
                "seed-23 disjoint holdout"
                if self.exclude_seed11_sample
                and self.sample_seed == FMA_HOLDOUT_SAMPLE_SEED
                and self.sample_size == FMA_PILOT_SAMPLE_SIZE
                else "seed-11 pilot"
                if self.sample_seed == FMA_PILOT_SAMPLE_SEED
                and self.sample_size == FMA_PILOT_SAMPLE_SIZE
                and not self.exclude_seed11_sample
                else "custom seeded sample"
            ),
            "pilot_sample_membership_sha256": FMA_PILOT_SAMPLE_MEMBERSHIP_SHA256,
            "holdout_sample_membership_sha256": (
                FMA_HOLDOUT_SAMPLE_MEMBERSHIP_SHA256
                if self.exclude_seed11_sample
                and self.sample_seed == FMA_HOLDOUT_SAMPLE_SEED
                and self.sample_size == FMA_PILOT_SAMPLE_SIZE
                else None
            ),
            "metadata_member": "fma_metadata/tracks.csv",
            "feature_member": "fma_metadata/features.csv",
            "audio_files_used": False,
            "descriptive_metadata_used_as_features": False,
        }
        features = tuple(
            FeatureDefinition(
                feature_id=feature.feature_id,
                name=f"{feature.family} {feature.statistic} coordinate {feature.coordinate}",
                definition=feature.interpretation,
                value_semantics="binary",
            )
            for feature in FMA_FROZEN_FEATURES
        )
        entities = tuple(
            PublicEntity(entity_id=str(track_id), label=str(track_id))
            for track_id in sample_ids
        )
        definition = DatasetDefinition(
            dataset_id="fma",
            version="fma-metadata-seed11-frozen-features-v1",
            source_name="Free Music Archive metadata",
            source_version="fma_metadata.zip",
            original_source_url="https://github.com/mdeff/fma",
            entities=entities,
            features=features,
            gameplay_feature_ids=self.gameplay_feature_ids,
            source_feature_ids={
                feature.feature_id: "/".join(feature.source_column)
                for feature in FMA_FROZEN_FEATURES
            },
            missing_value_policy="reject",
            generation_policy="strict_quartet_validation",
            provenance=provenance,
            feature_families={
                feature.feature_id: feature.family for feature in FMA_FROZEN_FEATURES
            },
            transformations={
                feature.feature_id: {
                    "operation": "strictly_greater_than",
                    "threshold": feature.threshold,
                    "ties_are_false": True,
                    "threshold_sample_seed": FMA_PILOT_SAMPLE_SEED,
                }
                for feature in FMA_FROZEN_FEATURES
            },
            metadata={
                "sample_size": self.sample_size,
                "sample_seed": self.sample_seed,
                "sample_design": provenance["sample_design"],
                "features": {
                    feature.feature_id: {
                        "family": feature.family,
                        "statistic": feature.statistic,
                        "coordinate": feature.coordinate,
                        "source_column": list(feature.source_column),
                        "threshold": feature.threshold,
                    }
                    for feature in FMA_FROZEN_FEATURES
                },
            },
            archive_sha256_required=True,
        )
        domain_source_data = DatasetSourceData(
            values={
                str(track_id): source_values[track_id]
                for track_id in sample_ids
            }
        )
        self._core_adapter = DatasetAdapterFactory().create(definition, domain_source_data)
        self.dataset_definition = definition
        self.domain = self._core_adapter.load_domain()
        self.track_metadata = MappingProxyType({
            str(track_id): MappingProxyType(all_metadata[track_id])
            for track_id in sample_ids
        })
        self.provenance = MappingProxyType(provenance)
        return self.domain

    def _core(self) -> DatasetAdapter:
        if self._core_adapter is None:
            self.load_domain()
        if self._core_adapter is None:
            raise RuntimeError("FMA dataset loading did not create a core adapter.")
        return self._core_adapter

    @overload
    def build_instance(
        self,
        feature_ids: list[str] | tuple[str, ...] | None = None,
        *,
        seed: int | None = None,
        instance_id: str = "fma_instance_0",
        return_report: Literal[False] = False,
    ) -> InstanceSpec: ...

    @overload
    def build_instance(
        self,
        feature_ids: list[str] | tuple[str, ...] | None = None,
        *,
        seed: int | None = None,
        instance_id: str = "fma_instance_0",
        return_report: Literal[True],
    ) -> InstanceGenerationResult: ...

    @overload
    def build_instance(
        self,
        feature_ids: list[str] | tuple[str, ...] | None = None,
        *,
        seed: int | None = None,
        instance_id: str = "fma_instance_0",
        return_report: bool,
    ) -> InstanceSpec | InstanceGenerationResult: ...

    def build_instance(
        self,
        feature_ids: list[str] | tuple[str, ...] | None = None,
        *,
        seed: int | None = None,
        instance_id: str = "fma_instance_0",
        return_report: bool = False,
    ) -> InstanceSpec | InstanceGenerationResult:
        return self._core().build_instance(
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
        return self._core().validate_instance(domain, instance)


__all__ = [
    "FMAAdapter",
    "FMAFeature",
    "FMA_FROZEN_FEATURES",
    "FMA_HOLDOUT_SAMPLE_MEMBERSHIP_SHA256",
    "FMA_HOLDOUT_SAMPLE_SEED",
    "FMA_PILOT_ARCHIVE_SHA256",
    "FMA_PILOT_SAMPLE_MEMBERSHIP_SHA256",
    "FMA_PILOT_SAMPLE_SEED",
    "FMA_PILOT_SAMPLE_SIZE",
]
