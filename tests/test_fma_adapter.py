import csv
import hashlib
import tempfile
import unittest
import zipfile
import io
from pathlib import Path
from unittest.mock import patch

from domain_adapters import FMAAdapter, FMA_FROZEN_FEATURES
from phase0_foundation import Phase0Controller


EXPECTED_FROZEN_FEATURES = (
    ("fma:chroma_cens:mean:01", "chroma_cens", "mean", "01", 0.25517144799232483),
    ("fma:chroma_cqt:median:11", "chroma_cqt", "median", "11", 0.4525887370109558),
    ("fma:chroma_stft:skew:05", "chroma_stft", "skew", "05", 0.3928850293159485),
    ("fma:mfcc:kurtosis:08", "mfcc", "kurtosis", "08", 0.15643799304962158),
    ("fma:rmse:min:01", "rmse", "min", "01", 3.314237983431667e-05),
    ("fma:spectral_bandwidth:min:01", "spectral_bandwidth", "min", "01", 290.3798522949219),
    ("fma:spectral_centroid:kurtosis:01", "spectral_centroid", "kurtosis", "01", 6.258625030517578),
    ("fma:spectral_contrast:skew:07", "spectral_contrast", "skew", "07", -0.40135782957077026),
    ("fma:spectral_rolloff:max:01", "spectral_rolloff", "max", "01", 9463.8427734375),
    ("fma:tonnetz:skew:05", "tonnetz", "skew", "05", 0.015766769647598267),
    ("fma:zcr:skew:01", "zcr", "skew", "01", 2.4203286170959473),
    ("fma:chroma_cens:kurtosis:12", "chroma_cens", "kurtosis", "12", -0.17919006943702698),
    ("fma:chroma_cqt:kurtosis:08", "chroma_cqt", "kurtosis", "08", -0.7438324689865112),
    ("fma:chroma_stft:std:09", "chroma_stft", "std", "09", 0.26742768287658691),
    ("fma:mfcc:skew:15", "mfcc", "skew", "15", 0.003920631017535925),
    ("fma:spectral_contrast:max:01", "spectral_contrast", "max", "01", 59.43647766113281),
    ("fma:tonnetz:skew:03", "tonnetz", "skew", "03", 0.020528830587863922),
    ("fma:chroma_cens:skew:03", "chroma_cens", "skew", "03", 0.2518020570278168),
)

TRACK_METADATA_HEADERS = (
    ("", "", "track_id"),
    ("album", "title", ""),
    ("artist", "name", ""),
    ("track", "title", ""),
    ("track", "genre_top", ""),
    ("track", "genres", ""),
)


def _parity(value: int) -> bool:
    return value.bit_count() % 2 == 1


def make_archive(path: Path, track_ids: tuple[int, ...]) -> str:
    independent_forms = [1, 2, 4, 8]
    remaining_forms = [
        value for value in range(1, 16) if value not in independent_forms
    ]
    feature_forms = (independent_forms + remaining_forms + [1, 2, 3])[:len(FMA_FROZEN_FEATURES)]
    form_by_id = {
        feature.feature_id: form
        for feature, form in zip(FMA_FROZEN_FEATURES, feature_forms)
    }

    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        with archive.open("fma_metadata/tracks.csv", "w") as binary:
            text = io.TextIOWrapper(binary, encoding="utf-8", newline="")
            writer = csv.writer(text, lineterminator="\n")
            for level in range(3):
                writer.writerow([header[level] for header in TRACK_METADATA_HEADERS])
            for index, track_id in enumerate(track_ids):
                if index == 8:
                    writer.writerow([])
                writer.writerow([
                    str(track_id),
                    f"album-{track_id}",
                    f"artist-{track_id}",
                    f"title-{track_id}",
                    "rock",
                    "['rock']",
                ])
            text.flush()
            text.detach()

        with archive.open("fma_metadata/features.csv", "w") as binary:
            text = io.TextIOWrapper(binary, encoding="utf-8", newline="")
            writer = csv.writer(text, lineterminator="\n")
            writer.writerow(["feature", *[feature.family for feature in FMA_FROZEN_FEATURES]])
            writer.writerow(["statistics", *[feature.statistic for feature in FMA_FROZEN_FEATURES]])
            writer.writerow(["number", *[feature.coordinate for feature in FMA_FROZEN_FEATURES]])
            writer.writerow(["track_id", *("" for _ in FMA_FROZEN_FEATURES)])
            for index, track_id in enumerate(track_ids):
                if index == 8:
                    writer.writerow([])
                row = [str(track_id)]
                for feature in FMA_FROZEN_FEATURES:
                    is_true = _parity(index & form_by_id[feature.feature_id])
                    row.append(
                        repr(feature.threshold + 1.0)
                        if is_true
                        else repr(feature.threshold)
                    )
                writer.writerow(row)
            text.flush()
            text.detach()
    return hashlib.sha256(path.read_bytes()).hexdigest()


class FMAAdapterTests(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary_directory.cleanup)
        self.archive_path = Path(self.temporary_directory.name) / "fma_fixture.zip"
        self.track_ids = tuple(range(100, 116))
        self.archive_hash = make_archive(self.archive_path, self.track_ids)

    def _adapter(self, *, sample_size=16, sample_seed=11, exclude_seed11_sample=False):
        return FMAAdapter(
            self.archive_path,
            sample_size=sample_size,
            sample_seed=sample_seed,
            exclude_seed11_sample=exclude_seed11_sample,
        )

    def test_archive_sha256_is_verified_and_mismatch_is_rejected(self):
        with patch(
            "domain_adapters.fma_adapter.FMA_PILOT_ARCHIVE_SHA256",
            self.archive_hash,
        ):
            adapter = self._adapter()
            adapter.load_domain()
            self.assertEqual(adapter.provenance["archive_sha256"], self.archive_hash)
            self.assertTrue(adapter.provenance["archive_sha256_verified"])

        with patch(
            "domain_adapters.fma_adapter.FMA_PILOT_ARCHIVE_SHA256",
            "0" * 64,
        ):
            with self.assertRaisesRegex(ValueError, "does not match"):
                self._adapter().load_domain()

    def test_frozen_features_threshold_ties_labels_and_metadata(self):
        with patch(
            "domain_adapters.fma_adapter.FMA_PILOT_ARCHIVE_SHA256",
            self.archive_hash,
        ):
            adapter = self._adapter()
            domain = adapter.load_domain()

        self.assertEqual(len(domain.features), 18)
        self.assertEqual(domain.name, "fma")
        self.assertEqual(
            domain.version,
            "fma-metadata-seed11-frozen-features-v1",
        )
        self.assertEqual(
            tuple(entity.entity_id for entity in domain.entities),
            tuple(str(track_id) for track_id in self.track_ids),
        )
        self.assertEqual(
            tuple(
                (
                    feature.feature_id,
                    feature.family,
                    feature.statistic,
                    feature.coordinate,
                    feature.threshold,
                )
                for feature in FMA_FROZEN_FEATURES
            ),
            EXPECTED_FROZEN_FEATURES,
        )
        self.assertEqual(domain.gameplay_feature_ids, adapter.gameplay_feature_ids)
        self.assertEqual(
            tuple(domain.gameplay_feature_ids),
            tuple(item[0] for item in EXPECTED_FROZEN_FEATURES),
        )
        self.assertEqual(
            dict(adapter.dataset_definition.source_feature_ids),
            {
                feature_id: f"{family}/{statistic}/{coordinate}"
                for feature_id, family, statistic, coordinate, _ in EXPECTED_FROZEN_FEATURES
            },
        )
        self.assertEqual(
            domain.features[0].name,
            "chroma_cens mean coordinate 01",
        )
        self.assertEqual(
            adapter.dataset_definition.source_feature_ids[
                "fma:chroma_cens:mean:01"
            ],
            "chroma_cens/mean/01",
        )
        self.assertEqual(
            adapter.dataset_definition.metadata["features"][
                "fma:chroma_cens:mean:01"
            ]["source_column"],
            ("chroma_cens", "mean", "01"),
        )
        self.assertFalse(domain.values[str(self.track_ids[0])]["fma:chroma_cens:mean:01"])
        self.assertTrue(domain.values[str(self.track_ids[1])]["fma:chroma_cens:mean:01"])
        self.assertEqual(
            adapter.track_metadata[str(self.track_ids[0])]["title"],
            f"title-{self.track_ids[0]}",
        )
        self.assertEqual(
            adapter.track_metadata[str(self.track_ids[0])]["artist"],
            f"artist-{self.track_ids[0]}",
        )
        self.assertEqual(
            adapter.track_metadata[str(self.track_ids[0])]["album"],
            f"album-{self.track_ids[0]}",
        )
        self.assertEqual(adapter.track_metadata[str(self.track_ids[0])]["genre_top"], "rock")
        self.assertNotIn("title", adapter.gameplay_feature_ids)
        self.assertNotIn("artist", adapter.gameplay_feature_ids)
        self.assertNotIn("genre_top", adapter.gameplay_feature_ids)
        self.assertNotIn("genres", adapter.gameplay_feature_ids)
        self.assertTrue(
            all(
                set(entity_values) == set(adapter.gameplay_feature_ids)
                and all(type(value) is bool for value in entity_values.values())
                for entity_values in domain.values.values()
            )
        )

    def test_sampling_is_deterministic_for_seed_and_changes_for_another_seed(self):
        track_ids = list(range(2, 102))

        first = FMAAdapter.sample_track_ids(track_ids, 25, 11)
        repeated = FMAAdapter.sample_track_ids(track_ids, 25, 11)
        different = FMAAdapter.sample_track_ids(track_ids, 25, 23)

        self.assertEqual(first, repeated)
        self.assertNotEqual(first, different)
        self.assertEqual(len(first), len(set(first)))
        self.assertEqual(len(different), len(set(different)))

    def test_holdout_sampling_excludes_original_pilot_sample(self):
        track_ids = list(range(25_010))
        pilot = set(
            FMAAdapter.sample_track_ids(
                track_ids,
                25_000,
                11,
            )
        )

        holdout = FMAAdapter.sample_track_ids(
            track_ids,
            10,
            23,
            exclude_seed11_sample=True,
        )

        self.assertEqual(len(holdout), 10)
        self.assertFalse(pilot.intersection(holdout))

    def test_full_pool_strict_generation_passes_phase0_validation(self):
        with patch(
            "domain_adapters.fma_adapter.FMA_PILOT_ARCHIVE_SHA256",
            self.archive_hash,
        ):
            adapter = self._adapter()
            domain = adapter.load_domain()
            instance = adapter.build_instance(
                seed=11,
                instance_id="fma_fixture_instance",
            )
            validation = adapter.validate_instance(domain, instance)

            self.assertEqual(len(adapter.gameplay_feature_ids), 18)
            self.assertEqual(set(adapter.gameplay_feature_ids), set(
                feature.feature_id for feature in FMA_FROZEN_FEATURES
            ))
            self.assertEqual(len(instance.entity_ids), 16)
            self.assertTrue(set(instance.feature_ids) <= set(adapter.gameplay_feature_ids))
            self.assertEqual(sorted(instance.signature_map.values()), list(range(16)))
            self.assertGreater(validation["id_level_count"], 1)
            self.assertGreater(validation["structural_count"], 1)
            self.assertTrue(validation["accepted"])
            self.assertTrue(validation["archive_hash_verified"])
            expected_pool_hash = hashlib.sha256(
                "\n".join(sorted(adapter.gameplay_feature_ids)).encode("utf-8")
            ).hexdigest()
            self.assertEqual(
                validation["eligible_feature_pool_id"],
                f"sha256:{expected_pool_hash}",
            )

            controller = Phase0Controller(adapter, instance=instance)

        self.assertIs(controller.session.instance, instance)
        self.assertEqual(controller.session.instance_validation, validation)
        self.assertTrue(
            controller.session.instance_validation["quartet_validation"].accepted
        )

    def test_constructor_is_lazy_and_does_not_read_archive(self):
        missing_archive = Path(self.temporary_directory.name) / "not_created.zip"
        adapter = FMAAdapter(missing_archive)

        self.assertIsNone(adapter.domain)
        self.assertEqual(len(adapter.gameplay_feature_ids), 18)
        with self.assertRaises(FileNotFoundError):
            adapter.load_domain()

if __name__ == "__main__":
    unittest.main()
