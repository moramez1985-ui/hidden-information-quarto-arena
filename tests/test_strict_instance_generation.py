import unittest
from dataclasses import replace
from types import MappingProxyType
from unittest.mock import patch

from domain_adapters import GenericInstanceBuilder
from domain_adapters.dataset_adapter import (
    DatasetAdapterFactory,
    DatasetDefinition,
    DatasetSourceData,
)
from domain_adapters.instance_builder import (
    InstanceGenerationError,
    InstanceGenerationReport,
    InstanceGenerationResult,
    InstanceQuartetValidation,
    QuartetValidationRejection,
    validate_instance_quartets,
)
from domain_adapters.qm9_adapter import QM9Adapter
from phase0_foundation import DomainCatalog, FeatureDefinition, InstanceSpec, PublicEntity


BASE_MASKS = {
    f"x{bit_index}": sum(
        1 << entity_index
        for entity_index in range(16)
        if (entity_index >> bit_index) & 1
    )
    for bit_index in range(4)
}
BASE_QUARTET = tuple(BASE_MASKS)


def make_domain(feature_masks, *, copies=1, name="synthetic"):
    feature_ids = tuple(feature_masks)
    entities = []
    values = {}
    for entity_index in range(16):
        for copy_index in range(copies):
            entity_id = f"e{entity_index:02d}_{copy_index}"
            entities.append(PublicEntity(entity_id, entity_id))
            values[entity_id] = MappingProxyType({
                feature_id: bool((mask >> entity_index) & 1)
                for feature_id, mask in feature_masks.items()
            })
    return DomainCatalog(
        name=name,
        version="synthetic-v1",
        entities=tuple(entities),
        features=tuple(
            FeatureDefinition(feature_id, feature_id, feature_id)
            for feature_id in feature_ids
        ),
        values=MappingProxyType(values),
    )


def strict_build(domain, eligible_ids, **kwargs):
    return GenericInstanceBuilder.build_instance(
        domain,
        feature_ids=eligible_ids,
        eligible_feature_ids=eligible_ids,
        strict_validation=True,
        **kwargs,
    )


def rejected_result(instance_id, entity_ids, eligible_ids, selected_ids, id_count, structural_count):
    reasons = []
    if id_count == 0:
        reasons.append(QuartetValidationRejection("no_valid_id_level_quartets", "No valid quartets."))
    elif id_count == 1:
        reasons.append(QuartetValidationRejection("only_one_id_level_quartet", "Only one ID quartet."))
    if structural_count == 0:
        reasons.append(QuartetValidationRejection("no_structural_classes", "No structural classes."))
    elif structural_count == 1:
        reasons.append(QuartetValidationRejection("only_one_structural_class", "Only one structural class."))
    return InstanceQuartetValidation(
        instance_id=instance_id,
        entity_ids=tuple(entity_ids),
        eligible_feature_ids=tuple(eligible_ids),
        selected_feature_ids=tuple(sorted(selected_ids)),
        selected_signature_coverage=(1,) * 16,
        valid_quartets=(),
        structural_classes=(),
        id_level_count=id_count,
        structural_count=structural_count,
        accepted=False,
        rejection_reasons=tuple(reasons),
    )


class StrictInstanceGenerationTests(unittest.TestCase):
    def test_default_builder_behavior_is_unchanged(self):
        domain = make_domain(BASE_MASKS)

        with patch(
            "domain_adapters.instance_builder.validate_instance_quartets",
            side_effect=AssertionError("Default generation must not invoke strict validation."),
        ):
            instance = GenericInstanceBuilder.build_instance(
                domain,
                feature_ids=BASE_QUARTET,
                seed=17,
            )

        self.assertEqual(instance.feature_ids, BASE_QUARTET)
        self.assertEqual(set(instance.signature_map.values()), set(range(16)))
        self.assertEqual(instance.public_seed, 17)

    def test_strict_mode_rejects_validator_result_with_zero_valid_quartets(self):
        domain = make_domain(BASE_MASKS)
        fake_result = rejected_result(
            "instance_0",
            tuple(f"e{index:02d}_0" for index in range(16)),
            BASE_QUARTET,
            BASE_QUARTET,
            0,
            0,
        )

        with patch(
            "domain_adapters.instance_builder.validate_instance_quartets",
            return_value=fake_result,
        ):
            with self.assertRaises(InstanceGenerationError) as raised:
                strict_build(domain, BASE_QUARTET, return_report=True)

        self.assertEqual(raised.exception.report.validated_candidates, 1)
        self.assertEqual(
            dict(raised.exception.report.rejection_counts),
            {"no_structural_classes": 1, "no_valid_id_level_quartets": 1},
        )

    def test_strict_mode_rejects_exactly_one_valid_id_level_quartet(self):
        domain = make_domain(BASE_MASKS)

        with self.assertRaises(InstanceGenerationError) as raised:
            strict_build(domain, BASE_QUARTET, return_report=True)

        report = raised.exception.report
        self.assertEqual(report.candidate_quartets_total, 1)
        self.assertEqual(report.feasible_quartets_found, 1)
        self.assertEqual(report.validated_candidates, 1)
        self.assertEqual(dict(report.rejection_counts)["only_one_id_level_quartet"], 1)
        self.assertEqual(dict(report.rejection_counts)["only_one_structural_class"], 1)

    def test_strict_mode_rejects_multiple_ids_in_one_structural_class(self):
        masks = {**BASE_MASKS, "alias_x0": BASE_MASKS["x0"]}
        domain = make_domain(masks)

        with self.assertRaises(InstanceGenerationError) as raised:
            strict_build(domain, tuple(masks), return_report=True)

        self.assertEqual(raised.exception.report.feasible_quartets_found, 2)
        self.assertEqual(raised.exception.report.validated_candidates, 2)
        self.assertEqual(
            dict(raised.exception.report.rejection_counts),
            {"no_signature_coverage": 3, "only_one_structural_class": 2},
        )

    def test_strict_mode_uses_one_entity_selection_per_feasible_quartet(self):
        masks = {**BASE_MASKS, "alias_x0": BASE_MASKS["x0"]}
        domain = make_domain(masks, copies=2)
        rejected = rejected_result(
            "instance_0",
            (),
            tuple(masks),
            BASE_QUARTET,
            2,
            1,
        )
        observed_instances = []

        def capture_candidate(candidate_domain, candidate, candidate_feature_ids):
            observed_instances.append(candidate)
            self.assertEqual(len(candidate.entity_ids), 16)
            self.assertEqual(len(set(candidate.entity_ids)), 16)
            self.assertEqual(set(candidate.signature_map.values()), set(range(16)))
            return rejected

        with patch(
            "domain_adapters.instance_builder.validate_instance_quartets",
            side_effect=capture_candidate,
        ):
            with self.assertRaises(InstanceGenerationError) as raised:
                strict_build(domain, tuple(masks), return_report=True)

        self.assertEqual(raised.exception.report.feasible_quartets_found, 2)
        self.assertEqual(len(observed_instances), 2)
        self.assertEqual(len({candidate.feature_ids for candidate in observed_instances}), 2)
        self.assertEqual(
            {candidate.instance_id for candidate in observed_instances},
            {"instance_0"},
        )

    def test_strict_mode_accepts_only_with_multiple_ids_and_structural_classes(self):
        masks = {
            **BASE_MASKS,
            "y0": BASE_MASKS["x0"] ^ BASE_MASKS["x1"],
            "y1": BASE_MASKS["x1"],
            "y2": BASE_MASKS["x2"],
            "y3": BASE_MASKS["x3"],
        }
        domain = make_domain(masks)

        result = strict_build(domain, tuple(masks), return_report=True)

        self.assertIsInstance(result, InstanceGenerationResult)
        validation = validate_instance_quartets(domain, result.instance, tuple(masks))
        self.assertTrue(validation.accepted)
        self.assertGreater(validation.id_level_count, 1)
        self.assertGreater(validation.structural_count, 1)
        self.assertEqual(result.report.validated_candidates, 1)

    def test_strict_mode_continues_after_a_rejected_candidate(self):
        masks = {**BASE_MASKS, "alias_x0": BASE_MASKS["x0"]}
        domain = make_domain(masks)
        accepted_result = replace(
            rejected_result(
                "instance_0",
                (),
                tuple(masks),
                BASE_QUARTET,
                2,
                2,
            ),
            accepted=True,
            rejection_reasons=(),
        )
        rejected = rejected_result(
            "instance_0",
            (),
            tuple(masks),
            BASE_QUARTET,
            2,
            1,
        )

        with patch(
            "domain_adapters.instance_builder.validate_instance_quartets",
            side_effect=(rejected, accepted_result),
        ) as validator:
            result = strict_build(
                domain,
                tuple(masks),
                preferred_quartet=BASE_QUARTET,
                return_report=True,
            )

        self.assertEqual(validator.call_count, 2)
        self.assertTrue(result.report.candidate_quartets_examined >= 2)
        self.assertEqual(result.report.validated_candidates, 2)
        self.assertEqual(
            dict(result.report.rejection_counts),
            {"no_signature_coverage": 3, "only_one_structural_class": 1},
        )

    def test_exhaustion_reports_finite_search_without_fallback(self):
        constants = {f"constant_{index}": 0 for index in range(4)}
        domain = make_domain(constants)

        with patch(
            "domain_adapters.instance_builder.validate_instance_quartets",
            side_effect=AssertionError("No infeasible quartet should reach validation."),
        ):
            with self.assertRaises(InstanceGenerationError) as raised:
                strict_build(domain, tuple(constants), return_report=True)

        report = raised.exception.report
        self.assertEqual(report.candidate_quartets_total, 1)
        self.assertEqual(report.candidate_quartets_examined, 1)
        self.assertEqual(report.feasible_quartets_found, 0)
        self.assertEqual(report.validated_candidates, 0)
        self.assertEqual(dict(report.rejection_counts), {"no_signature_coverage": 1})
        self.assertIn("one deterministic entity selection per feasible initial quartet", str(raised.exception))
        self.assertIn("does not establish that no acceptable 16-entity subset exists", str(raised.exception))

    def test_strict_mode_raises_for_missing_feature_values(self):
        domain = make_domain(BASE_MASKS)
        broken_values = dict(domain.values)
        first_entity_id = next(iter(broken_values))
        first_entity_values = dict(broken_values[first_entity_id])
        del first_entity_values[BASE_QUARTET[0]]
        broken_values[first_entity_id] = MappingProxyType(first_entity_values)
        broken_domain = replace(domain, values=MappingProxyType(broken_values))

        with self.assertRaisesRegex(ValueError, "Missing feature value"):
            strict_build(broken_domain, BASE_QUARTET, return_report=True)

    def test_strict_mode_raises_for_non_boolean_feature_values(self):
        domain = make_domain(BASE_MASKS)
        broken_values = dict(domain.values)
        first_entity_id = next(iter(broken_values))
        first_entity_values = dict(broken_values[first_entity_id])
        first_entity_values[BASE_QUARTET[0]] = 1
        broken_values[first_entity_id] = MappingProxyType(first_entity_values)
        broken_domain = replace(domain, values=MappingProxyType(broken_values))

        with self.assertRaisesRegex(ValueError, "must be a bool"):
            strict_build(broken_domain, BASE_QUARTET, return_report=True)

    def test_strict_mode_counts_well_formed_missing_signature_as_rejection(self):
        masks = {**BASE_MASKS, "constant": 0}
        domain = make_domain(masks)

        with self.assertRaises(InstanceGenerationError) as raised:
            strict_build(domain, tuple(masks), return_report=True)

        report = raised.exception.report
        self.assertEqual(report.candidate_quartets_examined, 5)
        self.assertEqual(report.feasible_quartets_found, 1)
        self.assertEqual(report.validated_candidates, 1)
        self.assertEqual(dict(report.rejection_counts)["no_signature_coverage"], 4)

    def test_seed_reproduces_accepted_instance_and_search_report(self):
        masks = {
            **BASE_MASKS,
            "y0": BASE_MASKS["x0"] ^ BASE_MASKS["x1"],
            "y1": BASE_MASKS["x1"],
            "y2": BASE_MASKS["x2"],
            "y3": BASE_MASKS["x3"],
        }
        domain = make_domain(masks, copies=2)

        first = strict_build(domain, tuple(masks), seed=31, return_report=True)
        second = strict_build(domain, tuple(masks), seed=31, return_report=True)

        self.assertEqual(first, second)
        self.assertEqual(first.instance.public_seed, 31)

    def test_different_seeds_are_each_deterministic(self):
        masks = {
            **BASE_MASKS,
            "y0": BASE_MASKS["x0"] ^ BASE_MASKS["x1"],
            "y1": BASE_MASKS["x1"],
            "y2": BASE_MASKS["x2"],
            "y3": BASE_MASKS["x3"],
        }
        domain = make_domain(masks, copies=2)

        seed_one_first = strict_build(domain, tuple(masks), seed=7, return_report=True)
        seed_one_repeat = strict_build(domain, tuple(masks), seed=7, return_report=True)
        seed_two_first = strict_build(domain, tuple(masks), seed=8, return_report=True)
        seed_two_repeat = strict_build(domain, tuple(masks), seed=8, return_report=True)

        self.assertEqual(seed_one_first, seed_one_repeat)
        self.assertEqual(seed_two_first, seed_two_repeat)

    def test_qm9_adapter_passes_complete_pool_and_strict_mode(self):
        masks = {
            **BASE_MASKS,
            "y0": BASE_MASKS["x0"] ^ BASE_MASKS["x1"],
            "y1": BASE_MASKS["x1"],
            "y2": BASE_MASKS["x2"],
            "y3": BASE_MASKS["x3"],
        }
        pool = tuple(masks)
        domain = make_domain(masks, name="qm9")
        instance = InstanceSpec(
            instance_id="qm9_instance",
            domain_name="qm9",
            feature_ids=BASE_QUARTET,
            entity_ids=tuple(f"e{index:02d}_0" for index in range(16)),
            signature_map=MappingProxyType({
                f"e{index:02d}_0": index for index in range(16)
            }),
        )
        adapter = QM9Adapter.__new__(QM9Adapter)
        adapter.playable_feature_ids = pool
        adapter._core_adapter = DatasetAdapterFactory().create(
            DatasetDefinition(
                dataset_id="qm9",
                version=domain.version,
                source_name="synthetic QM9",
                source_version="fixture-v1",
                original_source_url=None,
                entities=domain.entities,
                features=domain.features,
                gameplay_feature_ids=pool,
                source_feature_ids={feature_id: feature_id for feature_id in pool},
                missing_value_policy="reject",
                generation_policy="strict_quartet_validation",
            ),
            DatasetSourceData(values=domain.values),
        )
        adapter.domain = adapter._core_adapter.domain
        generation_result = InstanceGenerationResult(
            instance,
            InstanceGenerationReport(70, 1, 1, 1, ()),
        )

        with patch(
            "domain_adapters.dataset_adapter.GenericInstanceBuilder.build_instance",
            return_value=generation_result,
        ) as builder:
            returned = adapter.build_instance(
                feature_ids=BASE_QUARTET,
                seed=4,
                return_report=True,
            )

        self.assertIs(returned, generation_result)
        kwargs = builder.call_args.kwargs
        self.assertTrue(kwargs["strict_validation"])
        self.assertTrue(kwargs["return_report"])
        self.assertEqual(tuple(kwargs["eligible_feature_ids"]), pool)
        self.assertEqual(tuple(kwargs["feature_ids"]), pool)
        self.assertEqual(tuple(kwargs["preferred_quartet"]), BASE_QUARTET)

    def test_strict_mode_requires_the_complete_feature_pool(self):
        masks = {**BASE_MASKS, "alias_x0": BASE_MASKS["x0"]}
        domain = make_domain(masks)

        with self.assertRaisesRegex(ValueError, "complete eligible feature pool"):
            GenericInstanceBuilder.build_instance(
                domain,
                feature_ids=BASE_QUARTET,
                strict_validation=True,
                eligible_feature_ids=tuple(masks),
            )


if __name__ == "__main__":
    unittest.main()
