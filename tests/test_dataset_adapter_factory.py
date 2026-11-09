import json
import unittest
from unittest.mock import patch

from domain_adapters import (
    DatasetAdapterFactory,
    DatasetDefinition,
    DatasetSourceData,
)
from phase0_foundation import FeatureDefinition, Phase0Controller, PublicEntity


ENTITY_IDS = tuple(f"entity_{index:02d}" for index in range(16))
BASE_MASKS = {
    f"x{bit_index}": sum(
        1 << entity_index
        for entity_index in range(16)
        if (entity_index >> bit_index) & 1
    )
    for bit_index in range(4)
}


def make_definition(dataset_id, feature_masks, *, strict=False, source_loader_id=None):
    features = tuple(
        FeatureDefinition(feature_id, feature_id, f"Definition for {feature_id}")
        for feature_id in feature_masks
    )
    return DatasetDefinition(
        dataset_id=dataset_id,
        version=f"{dataset_id}-v1",
        source_name=f"{dataset_id} fixture",
        source_version="fixture-v1",
        original_source_url=None,
        entities=tuple(PublicEntity(entity_id, entity_id) for entity_id in ENTITY_IDS),
        features=features,
        gameplay_feature_ids=tuple(feature_masks),
        source_feature_ids={
            feature_id: f"source_{feature_id}" for feature_id in feature_masks
        },
        missing_value_policy="reject",
        generation_policy=(
            "strict_quartet_validation" if strict else "standard"
        ),
        source_loader_id=source_loader_id,
    )


def make_source_data(feature_masks):
    return DatasetSourceData(
        values={
            entity_id: {
                feature_id: bool((mask >> entity_index) & 1)
                for feature_id, mask in feature_masks.items()
            }
            for entity_index, entity_id in enumerate(ENTITY_IDS)
        }
    )


class FixtureLoader:
    def __init__(self, feature_masks):
        self.feature_masks = feature_masks
        self.calls = 0

    def load(self, definition: DatasetDefinition) -> DatasetSourceData:
        self.calls += 1
        if definition.dataset_id != "loaded":
            raise ValueError("Unexpected dataset definition for fixture loader.")
        return make_source_data(self.feature_masks)


class DatasetAdapterFactoryTests(unittest.TestCase):
    def test_strict_factory_dataset_completes_phase0_preparation_pipeline(self):
        feature_ids = ("f0", "f1", "f2", "f3", "f4")
        entity_ids = tuple(f"entity_{index:02d}" for index in range(16))
        features = tuple(
            FeatureDefinition(
                feature_id,
                feature_id,
                f"Synthetic binary feature {feature_id}.",
            )
            for feature_id in feature_ids
        )
        definition = DatasetDefinition(
            dataset_id="synthetic_pipeline",
            version="synthetic-v1",
            source_name="deterministic synthetic fixture",
            source_version="1",
            original_source_url=None,
            entities=tuple(PublicEntity(entity_id, entity_id) for entity_id in entity_ids),
            features=features,
            gameplay_feature_ids=feature_ids,
            source_feature_ids={feature_id: feature_id for feature_id in feature_ids},
            missing_value_policy="reject",
            generation_policy="strict_quartet_validation",
        )
        source_data = DatasetSourceData(
            values={
                entity_id: {
                    "f0": bool(index & 1),
                    "f1": bool((index >> 1) & 1),
                    "f2": bool((index >> 2) & 1),
                    "f3": bool((index >> 3) & 1),
                    "f4": bool(
                        ((index & 1) ^ ((index >> 1) & 1) ^ ((index >> 2) & 1))
                    ),
                }
                for index, entity_id in enumerate(entity_ids)
            }
        )
        adapter = DatasetAdapterFactory().create(definition, source_data)
        instance = adapter.build_instance(
            seed=23,
            instance_id="synthetic_pipeline_instance",
        )
        validation_record = adapter.validate_instance(adapter.domain, instance)

        self.assertEqual(len(instance.entity_ids), 16)
        self.assertEqual(len(set(instance.entity_ids)), 16)
        self.assertTrue(set(instance.feature_ids).issubset(set(feature_ids)))
        self.assertEqual(
            sorted(instance.signature_map.values()),
            list(range(16)),
        )
        quartet_validation = validation_record["quartet_validation"]
        self.assertEqual(quartet_validation.id_level_count, 4)
        self.assertEqual(quartet_validation.structural_count, 4)
        self.assertTrue(quartet_validation.accepted)
        self.assertTrue(adapter.requires_instance_validation)

        controller_validation_records = []
        adapter_validate_instance = adapter.validate_instance

        def capture_validation(domain, candidate):
            record = adapter_validate_instance(domain, candidate)
            controller_validation_records.append(record)
            return record

        with patch.object(
            adapter,
            "validate_instance",
            side_effect=capture_validation,
        ) as validate_instance:
            controller = Phase0Controller(adapter, instance=instance)

        validate_instance.assert_called_once_with(adapter.domain, instance)
        self.assertIs(controller.session.instance, instance)
        session_validation = controller.session.instance_validation
        if session_validation is None:
            self.fail("Phase0Controller did not preserve the instance validation record.")
        self.assertEqual(
            session_validation,
            controller_validation_records[0],
        )
        self.assertEqual(session_validation, validation_record)
        self.assertIs(
            session_validation["quartet_validation"],
            controller_validation_records[0]["quartet_validation"],
        )

    def test_factory_constructs_adapter_and_immutable_domain(self):
        source_values = {
            entity_id: dict(values)
            for entity_id, values in make_source_data(BASE_MASKS).values.items()
        }
        adapter = DatasetAdapterFactory().create(
            make_definition("alpha", BASE_MASKS),
            DatasetSourceData(values=source_values),
        )

        self.assertEqual(adapter.domain.name, "alpha")
        self.assertEqual(adapter.domain.gameplay_feature_ids, tuple(BASE_MASKS))
        self.assertEqual(len(adapter.domain.entities), 16)
        self.assertTrue(adapter.domain.values["entity_00"]["x0"] is False)
        source_values["entity_00"]["x0"] = True
        self.assertFalse(adapter.domain.values["entity_00"]["x0"])
        with self.assertRaises(TypeError):
            adapter.domain.values["entity_00"]["x0"] = True  # type: ignore[index]

    def test_same_factory_creates_independent_dataset_instances(self):
        other_masks = {f"other_{key}": value for key, value in BASE_MASKS.items()}
        factory = DatasetAdapterFactory()
        first = factory.create(
            make_definition("alpha", BASE_MASKS),
            make_source_data(BASE_MASKS),
        )
        second = factory.create(
            make_definition("beta", other_masks),
            make_source_data(other_masks),
        )

        self.assertEqual(first.domain.name, "alpha")
        self.assertEqual(second.domain.name, "beta")
        self.assertNotEqual(first.domain.features, second.domain.features)
        self.assertEqual(first.gameplay_feature_ids, tuple(BASE_MASKS))
        self.assertEqual(second.gameplay_feature_ids, tuple(other_masks))
        self.assertEqual(first.domain.values["entity_01"]["x0"], True)
        self.assertEqual(second.domain.values["entity_01"]["other_x0"], True)
        with self.assertRaises(KeyError):
            _ = first.domain.values["entity_00"]["other_x0"]

    def test_factory_uses_only_explicitly_registered_source_loaders(self):
        loader = FixtureLoader(BASE_MASKS)
        definition = make_definition(
            "loaded",
            BASE_MASKS,
            source_loader_id="fixture-loader",
        )
        factory = DatasetAdapterFactory(
            source_loaders={"fixture-loader": loader}
        )

        adapter = factory.create(definition)

        self.assertEqual(adapter.domain.name, "loaded")
        self.assertEqual(loader.calls, 1)
        with self.assertRaisesRegex(ValueError, "not approved"):
            DatasetAdapterFactory().create(definition)

    def test_definition_rejects_unknown_gameplay_and_inconsistent_source_mapping(self):
        with self.assertRaisesRegex(ValueError, "Gameplay feature IDs"):
            DatasetDefinition(
                dataset_id="invalid",
                version="v1",
                source_name="fixture",
                source_version="v1",
                original_source_url=None,
                entities=(PublicEntity("one", "one"),),
                features=tuple(
                    FeatureDefinition(key, key, key) for key in BASE_MASKS
                ),
                gameplay_feature_ids=("not-defined", "x1", "x2", "x3"),
                source_feature_ids={key: key for key in BASE_MASKS},
                missing_value_policy="reject",
                generation_policy="standard",
            )

    def test_definition_rejects_executable_transformation_configuration(self):
        with self.assertRaisesRegex(ValueError, "declarative data"):
            DatasetDefinition(
                dataset_id="invalid",
                version="v1",
                source_name="fixture",
                source_version="v1",
                original_source_url=None,
                entities=(PublicEntity("one", "one"),),
                features=tuple(
                    FeatureDefinition(key, key, key) for key in BASE_MASKS
                ),
                gameplay_feature_ids=tuple(BASE_MASKS),
                source_feature_ids={key: key for key in BASE_MASKS},
                missing_value_policy="reject",
                generation_policy="standard",
                transformations={"x0": lambda value: value},
            )

        with self.assertRaisesRegex(ValueError, "Source feature mappings"):
            DatasetDefinition(
                dataset_id="inconsistent",
                version="v1",
                source_name="fixture",
                source_version="v1",
                original_source_url=None,
                entities=(PublicEntity("one", "one"),),
                features=tuple(
                    FeatureDefinition(key, key, key) for key in BASE_MASKS
                ),
                gameplay_feature_ids=tuple(BASE_MASKS),
                source_feature_ids={"x0": "x0"},
                missing_value_policy="reject",
                generation_policy="standard",
            )

    def test_factory_rejects_missing_entities_features_and_non_boolean_values(self):
        factory = DatasetAdapterFactory()
        definition = make_definition("alpha", BASE_MASKS)
        valid = make_source_data(BASE_MASKS).values

        missing_feature = {key: dict(value) for key, value in valid.items()}
        del missing_feature["entity_00"]["x0"]
        with self.assertRaisesRegex(ValueError, "match the dataset definition"):
            factory.create(
                definition,
                DatasetSourceData(values=missing_feature),
            )

        malformed_value = json.loads(
            json.dumps({key: dict(value) for key, value in valid.items()})
        )
        malformed_value["entity_00"]["x0"] = 1
        with self.assertRaisesRegex(ValueError, "must be a bool"):
            factory.create(
                definition,
                DatasetSourceData(values=malformed_value),
            )

        missing_entity = dict(valid)
        del missing_entity["entity_00"]
        with self.assertRaisesRegex(ValueError, "entity IDs"):
            factory.create(
                definition,
                DatasetSourceData(values=missing_entity),
            )

    def test_generation_is_deterministic_and_uses_generic_builder(self):
        adapter = DatasetAdapterFactory().create(
            make_definition("alpha", BASE_MASKS),
            make_source_data(BASE_MASKS),
        )

        first = adapter.build_instance(seed=8, instance_id="same")
        second = adapter.build_instance(seed=8, instance_id="same")

        self.assertEqual(first, second)
        self.assertEqual(len(first.entity_ids), 16)
        self.assertEqual(set(first.signature_map.values()), set(range(16)))

    def test_strict_generation_and_validation_preserve_acceptance_rule(self):
        masks = {
            **BASE_MASKS,
            "y0": BASE_MASKS["x0"] ^ BASE_MASKS["x1"],
            "y1": BASE_MASKS["x1"],
            "y2": BASE_MASKS["x2"],
            "y3": BASE_MASKS["x3"],
        }
        adapter = DatasetAdapterFactory().create(
            make_definition("strict", masks, strict=True),
            make_source_data(masks),
        )

        instance = adapter.build_instance(instance_id="strict-instance")
        validation = adapter.validate_instance(adapter.domain, instance)

        self.assertTrue(validation["accepted"])
        self.assertGreater(validation["id_level_count"], 1)
        self.assertGreater(validation["structural_count"], 1)
        self.assertEqual(validation["validation_status"], "accepted")
        self.assertEqual(validation["dataset_identity"]["source_name"], "strict fixture")

    def test_validation_rejects_another_adapters_domain(self):
        factory = DatasetAdapterFactory()
        first = factory.create(
            make_definition("alpha", BASE_MASKS),
            make_source_data(BASE_MASKS),
        )
        second = factory.create(
            make_definition(
                "beta",
                {f"other_{key}": value for key, value in BASE_MASKS.items()},
            ),
            make_source_data(
                {f"other_{key}": value for key, value in BASE_MASKS.items()}
            ),
        )
        instance = first.build_instance()

        with self.assertRaisesRegex(ValueError, "this dataset"):
            first.validate_instance(second.domain, instance)


if __name__ == "__main__":
    unittest.main()
