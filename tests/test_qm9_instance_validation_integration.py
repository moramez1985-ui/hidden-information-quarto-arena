import json
import unittest
from types import MappingProxyType
from unittest.mock import patch

from domain_adapters.dataset_adapter import (
    DatasetAdapterFactory,
    DatasetDefinition,
    DatasetSourceData,
)
from domain_adapters.qm9_adapter import QM9Adapter
from tournament_harness import _to_jsonable
from phase0_foundation import (
    DomainCatalog,
    FeatureDefinition,
    InstanceSpec,
    InstanceValidationError,
    MatchSession,
    Phase0Controller,
    PublicEntity,
    SyntheticAdapter,
    validate_audit_snapshot,
)


ENTITY_IDS = tuple(f"entity_{index:02d}" for index in range(16))
BASE_MASKS = {
    f"x{bit_index}": sum(
        1 << entity_index
        for entity_index in range(16)
        if (entity_index >> bit_index) & 1
    )
    for bit_index in range(4)
}


def make_domain_instance(masks, selected_feature_ids, instance_id="qm9_synthetic"):
    features = tuple(
        FeatureDefinition(feature_id, feature_id, feature_id)
        for feature_id in masks
    )
    entities = tuple(PublicEntity(entity_id, entity_id) for entity_id in ENTITY_IDS)
    values = MappingProxyType({
        entity_id: MappingProxyType({
            feature_id: bool((mask >> index) & 1)
            for feature_id, mask in masks.items()
        })
        for index, entity_id in enumerate(ENTITY_IDS)
    })
    domain = DomainCatalog(
        name="qm9",
        version="synthetic-fixture",
        entities=entities,
        features=features,
        values=values,
    )
    signature_map = MappingProxyType({
        entity_id: sum(
            int(values[entity_id][feature_id]) << bit_index
            for bit_index, feature_id in enumerate(selected_feature_ids)
        )
        for entity_id in ENTITY_IDS
    })
    instance = InstanceSpec(
        instance_id=instance_id,
        domain_name="qm9",
        feature_ids=tuple(selected_feature_ids),
        entity_ids=ENTITY_IDS,
        signature_map=signature_map,
        public_seed=12,
    )
    return domain, instance


class SyntheticQM9Adapter(QM9Adapter):
    def __init__(self, domain, instance, eligible_feature_ids):
        self.domain = domain
        self.instance = instance
        self.playable_feature_ids = tuple(eligible_feature_ids)
        self.provenance = {
            "source_name": "synthetic QM9 fixture",
            "source_version": "fixture-v1",
            "original_source_url": "https://example.invalid/qm9-fixture",
            "archive_sha256": "a" * 64,
        }
        feature_ids = tuple(feature.feature_id for feature in domain.features)
        self._core_adapter = DatasetAdapterFactory().create(
            DatasetDefinition(
                dataset_id="qm9",
                version=domain.version,
                source_name=self.provenance["source_name"],
                source_version=self.provenance["source_version"],
                original_source_url=self.provenance["original_source_url"],
                entities=domain.entities,
                features=domain.features,
                gameplay_feature_ids=tuple(eligible_feature_ids),
                source_feature_ids={feature_id: feature_id for feature_id in feature_ids},
                missing_value_policy="reject",
                generation_policy="strict_quartet_validation",
                provenance=self.provenance,
                archive_sha256_required=True,
            ),
            DatasetSourceData(values=domain.values),
        )
        self.domain = self._core_adapter.domain

    def load_domain(self):
        return self.domain

    def build_instance(self):
        return self.instance


class QM9AdapterWithoutValidation:
    def __init__(self, domain, instance):
        self.domain = domain
        self.instance = instance

    def load_domain(self):
        return self.domain

    def build_instance(self):
        return self.instance


class Qm9InstanceValidationIntegrationTests(unittest.TestCase):
    def _adapter_for(self, masks, selected=tuple(BASE_MASKS)):
        domain, instance = make_domain_instance(masks, selected)
        return SyntheticQM9Adapter(domain, instance, tuple(masks)), instance

    def _assert_rejected_before_session_creation(self, adapter):
        with patch("phase0_foundation.MatchSession") as match_session:
            with self.assertRaises(InstanceValidationError) as raised:
                Phase0Controller(adapter)
        match_session.assert_not_called()
        self.assertIsNotNone(raised.exception.validation_record)
        return raised.exception.validation_record

    def test_zero_valid_quartets_cannot_create_a_match(self):
        constants = {f"constant_{index}": 0 for index in range(4)}
        adapter, _ = self._adapter_for(constants, tuple(constants))

        record = self._assert_rejected_before_session_creation(adapter)

        self.assertEqual(record["id_level_count"], 0)
        self.assertEqual(record["structural_count"], 0)

    def test_one_valid_quartet_cannot_create_a_match(self):
        adapter, _ = self._adapter_for(BASE_MASKS)

        record = self._assert_rejected_before_session_creation(adapter)

        self.assertEqual(record["id_level_count"], 1)
        self.assertEqual(record["structural_count"], 1)

    def test_multiple_ids_in_one_structural_class_cannot_create_a_match(self):
        masks = {**BASE_MASKS, "alias_x0": BASE_MASKS["x0"]}
        adapter, _ = self._adapter_for(masks)

        record = self._assert_rejected_before_session_creation(adapter)

        self.assertEqual(record["id_level_count"], 2)
        self.assertEqual(record["structural_count"], 1)

    def test_multiple_structural_classes_proceed_and_are_restricted_to_audit(self):
        masks = {
            **BASE_MASKS,
            "y0": BASE_MASKS["x0"] ^ BASE_MASKS["x1"],
            "y1": BASE_MASKS["x1"],
            "y2": BASE_MASKS["x2"],
            "y3": BASE_MASKS["x3"],
        }
        adapter, instance = self._adapter_for(masks)

        controller = Phase0Controller(adapter, instance=instance)
        snapshot = controller.get_read_only_audit_view()
        record = snapshot.restricted_evaluator_data["instance_validation"]

        self.assertEqual(record["match_id"], snapshot.match_id)
        self.assertEqual(record["instance_id"], instance.instance_id)
        self.assertEqual(record["recorded_archive_sha256"], "a" * 64)
        self.assertFalse(record["archive_hash_verified"])
        self.assertGreater(record["id_level_count"], 1)
        self.assertGreater(record["structural_count"], 1)
        self.assertTrue(record["accepted"])
        self.assertEqual(record["validation_status"], "accepted")
        self.assertEqual(
            record["eligible_feature_pool_id"],
            adapter.validate_instance(adapter.domain, instance)["eligible_feature_pool_id"],
        )
        self.assertGreater(len(record["alternative_quartets"]), 1)
        self.assertGreater(len(record["structural_equivalence_classes"]), 1)
        self.assertNotIn("instance_validation", snapshot.public_audit)
        self.assertNotIn("alternative_quartets", snapshot.public_audit)
        self.assertNotIn("structural_equivalence_classes", snapshot.public_audit)

        for player in ("player_1", "player_2"):
            for observation in (
                controller.public_observation(player),
                controller.private_observation(player),
            ):
                self.assertNotIn("instance_validation", observation)
                self.assertNotIn("alternative_quartets", observation)
                self.assertNotIn("structural_equivalence_classes", observation)
                self.assertNotIn("y0", repr(observation))
        self.assertTrue(validate_audit_snapshot(snapshot))
        self.assertIsInstance(record["alternative_quartets"], tuple)
        serialized = json.dumps(_to_jsonable(snapshot))
        self.assertIn('"instance_validation"', serialized)
        self.assertIn('"alternative_quartets"', serialized)
        with self.assertRaises(TypeError):
            record["id_level_count"] = 0

    def test_synthetic_domain_retains_existing_behavior(self):
        controller = Phase0Controller(SyntheticAdapter())

        self.assertIsNone(controller.session.instance_validation)
        self.assertNotIn(
            "instance_validation",
            controller.get_read_only_audit_view().restricted_evaluator_data,
        )

    def test_direct_qm9_match_session_cannot_skip_validation(self):
        adapter, instance = self._adapter_for(BASE_MASKS)

        with self.assertRaisesRegex(ValueError, "requires an accepted"):
            MatchSession(adapter.domain, instance)

    def test_qm9_adapter_without_validation_capability_is_rejected(self):
        adapter, instance = self._adapter_for(BASE_MASKS)
        incomplete_adapter = QM9AdapterWithoutValidation(adapter.domain, instance)

        with self.assertRaisesRegex(TypeError, "instance validation capability"):
            Phase0Controller(incomplete_adapter)


if __name__ == "__main__":
    unittest.main()
