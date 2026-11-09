import unittest
from dataclasses import replace
from types import MappingProxyType

from domain_adapters.instance_builder import (
    canonical_quartet_key,
    validate_instance_quartets,
)
from phase0_foundation import DomainCatalog, FeatureDefinition, InstanceSpec, PublicEntity


ENTITY_IDS = tuple(f"e{index:02d}" for index in range(16))
BASE_MASKS = {
    f"x{bit_index}": sum(
        1 << entity_index
        for entity_index in range(16)
        if (entity_index >> bit_index) & 1
    )
    for bit_index in range(4)
}
BASE_QUARTET = tuple(BASE_MASKS)


def make_domain_and_instance(feature_masks, selected_feature_ids=BASE_QUARTET):
    features = tuple(FeatureDefinition(feature_id, feature_id, feature_id) for feature_id in feature_masks)
    entities = tuple(PublicEntity(entity_id, entity_id) for entity_id in ENTITY_IDS)
    values = MappingProxyType({
        entity_id: MappingProxyType({
            feature_id: bool((mask >> entity_index) & 1)
            for feature_id, mask in feature_masks.items()
        })
        for entity_index, entity_id in enumerate(ENTITY_IDS)
    })
    domain = DomainCatalog(
        name="synthetic",
        version="test",
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
        instance_id="synthetic_instance",
        domain_name=domain.name,
        feature_ids=tuple(selected_feature_ids),
        entity_ids=ENTITY_IDS,
        signature_map=signature_map,
    )
    return domain, instance


def mask_xor(left, right):
    return left ^ right


class InstanceQuartetValidatorTests(unittest.TestCase):
    def test_zero_valid_quartets_is_rejected(self):
        masks = {**BASE_MASKS, **{f"constant{index}": 0 for index in range(4)}}
        selected = tuple(f"constant{index}" for index in range(4))
        domain, instance = make_domain_and_instance(masks, selected)

        result = validate_instance_quartets(
            domain,
            instance,
            selected,
        )

        self.assertEqual(result.id_level_count, 0)
        self.assertEqual(result.structural_count, 0)
        self.assertFalse(result.accepted)
        self.assertEqual(
            {reason.code for reason in result.rejection_reasons},
            {"no_valid_id_level_quartets", "no_structural_classes"},
        )

    def test_exactly_one_valid_quartet_is_rejected(self):
        domain, instance = make_domain_and_instance(BASE_MASKS)

        result = validate_instance_quartets(domain, instance, BASE_QUARTET)

        self.assertEqual(result.id_level_count, 1)
        self.assertEqual(result.structural_count, 1)
        self.assertFalse(result.accepted)
        self.assertEqual(result.selected_signature_coverage, (1,) * 16)
        self.assertEqual(result.valid_quartets, (BASE_QUARTET,))
        self.assertEqual(
            {reason.code for reason in result.rejection_reasons},
            {"only_one_id_level_quartet", "only_one_structural_class"},
        )

    def test_multiple_id_level_quartets_in_one_structural_class_are_rejected(self):
        masks = {**BASE_MASKS, "alias_x0": BASE_MASKS["x0"]}
        domain, instance = make_domain_and_instance(masks)
        eligible = (*BASE_QUARTET, "alias_x0")

        result = validate_instance_quartets(domain, instance, eligible)

        self.assertEqual(result.id_level_count, 2)
        self.assertEqual(result.structural_count, 1)
        self.assertFalse(result.accepted)
        self.assertEqual(
            set(result.structural_classes[0].quartets),
            {BASE_QUARTET, ("alias_x0", "x1", "x2", "x3")},
        )
        self.assertEqual(
            {reason.code for reason in result.rejection_reasons},
            {"only_one_structural_class"},
        )

    def test_multiple_structural_classes_are_accepted(self):
        xor_mask = mask_xor(BASE_MASKS["x0"], BASE_MASKS["x1"])
        masks = {
            **BASE_MASKS,
            "y0": xor_mask,
            "y1": BASE_MASKS["x1"],
            "y2": BASE_MASKS["x2"],
            "y3": BASE_MASKS["x3"],
        }
        domain, instance = make_domain_and_instance(masks)
        y_quartet = ("y0", "y1", "y2", "y3")

        result = validate_instance_quartets(domain, instance, tuple(masks))

        self.assertIn(BASE_QUARTET, result.valid_quartets)
        self.assertIn(y_quartet, result.valid_quartets)
        self.assertGreater(result.id_level_count, 1)
        self.assertGreater(result.structural_count, 1)
        self.assertTrue(result.accepted)
        self.assertNotEqual(
            canonical_quartet_key(tuple(masks[feature_id] for feature_id in BASE_QUARTET)),
            canonical_quartet_key(tuple(masks[feature_id] for feature_id in y_quartet)),
        )

    def test_complemented_feature_mask_has_same_structural_key(self):
        masks = tuple(BASE_MASKS.values())
        complemented = (masks[0] ^ 0xFFFF, *masks[1:])

        self.assertEqual(canonical_quartet_key(masks), canonical_quartet_key(complemented))

    def test_coordinate_permutation_has_same_structural_key(self):
        masks = tuple(BASE_MASKS.values())

        self.assertEqual(
            canonical_quartet_key(masks),
            canonical_quartet_key((masks[2], masks[0], masks[3], masks[1])),
        )

    def test_reordered_entities_and_feature_pool_have_identical_output(self):
        masks = {
            **BASE_MASKS,
            "y0": mask_xor(BASE_MASKS["x0"], BASE_MASKS["x1"]),
            "y1": BASE_MASKS["x1"],
            "y2": BASE_MASKS["x2"],
            "y3": BASE_MASKS["x3"],
        }
        domain, instance = make_domain_and_instance(masks)
        _, permuted_instance = make_domain_and_instance(
            masks,
            tuple(reversed(BASE_QUARTET)),
        )
        reordered_domain = replace(domain, entities=tuple(reversed(domain.entities)))
        reordered_instance = replace(instance, entity_ids=tuple(reversed(instance.entity_ids)))
        reordered_instance = replace(
            reordered_instance,
            feature_ids=permuted_instance.feature_ids,
            signature_map=permuted_instance.signature_map,
        )

        result = validate_instance_quartets(domain, instance, tuple(masks))
        reordered = validate_instance_quartets(
            reordered_domain,
            reordered_instance,
            tuple(reversed(tuple(masks))),
        )

        self.assertEqual(result, reordered)

    def test_invalid_entity_count_and_duplicate_entity_ids_raise(self):
        domain, instance = make_domain_and_instance(BASE_MASKS)

        with self.assertRaisesRegex(ValueError, "exactly 16"):
            validate_instance_quartets(
                domain,
                replace(instance, entity_ids=instance.entity_ids[:-1]),
                BASE_QUARTET,
            )
        with self.assertRaisesRegex(ValueError, "distinct"):
            validate_instance_quartets(
                domain,
                replace(instance, entity_ids=(*instance.entity_ids[:-1], instance.entity_ids[0])),
                BASE_QUARTET,
            )

    def test_unknown_selected_or_eligible_features_raise(self):
        domain, instance = make_domain_and_instance(BASE_MASKS)

        with self.assertRaisesRegex(ValueError, "unknown selected feature"):
            validate_instance_quartets(
                domain,
                replace(instance, feature_ids=("unknown", *instance.feature_ids[1:])),
                BASE_QUARTET,
            )
        with self.assertRaisesRegex(ValueError, "unknown to the domain"):
            validate_instance_quartets(domain, instance, (*BASE_QUARTET[:3], "unknown"))

    def test_selected_features_must_be_in_eligible_pool(self):
        masks = {**BASE_MASKS, "alias_x0": BASE_MASKS["x0"]}
        domain, instance = make_domain_and_instance(masks)

        with self.assertRaisesRegex(ValueError, "belong to the eligible feature pool"):
            validate_instance_quartets(
                domain,
                instance,
                ("alias_x0", "x1", "x2", "x3"),
            )

    def test_signature_map_must_match_declared_feature_coordinate_order(self):
        domain, instance = make_domain_and_instance(BASE_MASKS)
        incorrect_signature_map = MappingProxyType({
            entity_id: 15 - signature
            for entity_id, signature in instance.signature_map.items()
        })

        with self.assertRaisesRegex(ValueError, "does not match instance.feature_ids order"):
            validate_instance_quartets(
                domain,
                replace(instance, signature_map=incorrect_signature_map),
                BASE_QUARTET,
            )

    def test_non_binary_feature_values_raise(self):
        domain, instance = make_domain_and_instance(BASE_MASKS)
        values = {
            entity_id: dict(feature_values)
            for entity_id, feature_values in domain.values.items()
        }
        values["e00"]["x0"] = 1
        invalid_domain = replace(
            domain,
            values=MappingProxyType({
                entity_id: MappingProxyType(feature_values)
                for entity_id, feature_values in values.items()
            }),
        )

        with self.assertRaisesRegex(ValueError, "must be a bool"):
            validate_instance_quartets(invalid_domain, instance, BASE_QUARTET)

    def test_validator_counts_from_full_eligible_pool(self):
        masks = {
            **BASE_MASKS,
            "y0": mask_xor(BASE_MASKS["x0"], BASE_MASKS["x1"]),
            "y1": BASE_MASKS["x1"],
            "y2": BASE_MASKS["x2"],
            "y3": BASE_MASKS["x3"],
        }
        domain, instance = make_domain_and_instance(masks)

        result = validate_instance_quartets(domain, instance, tuple(masks))

        self.assertGreater(result.id_level_count, 1)
        self.assertIn(("y0", "y1", "y2", "y3"), result.valid_quartets)
        self.assertEqual(result.selected_feature_ids, BASE_QUARTET)


if __name__ == "__main__":
    unittest.main()
