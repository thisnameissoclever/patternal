from __future__ import annotations

import unittest

from tools.mpfb_morph_controls import (
    FEMALE_GENDER_MACRO,
    MACRO_CONTROL_SOURCES,
    MORPH_CONTROL_SPECS,
    evaluate_morph_controls,
    macro_controls,
    mapped_measurement_keys,
    normalized_delta,
)


class MpfbMorphControlTests(unittest.TestCase):
    def test_default_gender_macro_is_female(self) -> None:
        self.assertLess(FEMALE_GENDER_MACRO, 0.5)

    def default_profile(self) -> dict[str, float]:
        profile: dict[str, float] = {}
        for spec in MORPH_CONTROL_SPECS:
            for key in spec.source_keys:
                profile[key] = spec.default
        for source_keys, default, _, _ in MACRO_CONTROL_SOURCES.values():
            for key in source_keys:
                profile[key] = default
        return profile

    def test_defaults_are_neutral(self) -> None:
        controls = evaluate_morph_controls(self.default_profile())
        self.assertGreaterEqual(len(controls), 30)
        self.assertTrue(all(control.weight == 0 for control in controls))
        self.assertEqual(
            macro_controls(self.default_profile()),
            {"muscle": 0.5, "weight": 0.5, "cupsize": 0.5, "firmness": 0.5},
        )

    def test_external_bust_support_does_not_create_maximum_tissue_firmness(self) -> None:
        profile = self.default_profile()
        profile["bustSupport"] = 100
        self.assertEqual(0.75, macro_controls(profile)["firmness"])
        profile["bustSupport"] = 0
        self.assertEqual(0.25, macro_controls(profile)["firmness"])

    def test_projection_detail_is_subordinate_to_cup_size(self) -> None:
        profile = self.default_profile()
        profile["bustProjectionL"] = 14
        profile["bustProjectionR"] = 14
        controls = {control.name: control for control in evaluate_morph_controls(profile)}
        self.assertEqual(0.25, controls["bust-projection"].weight)

    def test_larger_bust_height_moves_the_bust_down(self) -> None:
        profile = self.default_profile()
        profile["bustHeightL"] = 34
        profile["bustHeightR"] = 34
        controls = {control.name: control for control in evaluate_morph_controls(profile)}
        bust_height = controls["bust-height"]
        self.assertGreater(dict(bust_height.target_weights)["breast-trans-down"], 0)
        self.assertEqual(dict(bust_height.target_weights)["breast-trans-up"], 0)

    def test_side_specific_arm_control_does_not_change_partner(self) -> None:
        profile = self.default_profile()
        profile["bicepDepthL"] = 20
        controls = {control.name: control for control in evaluate_morph_controls(profile)}
        left = controls["left-upper-arm-depth"]
        right = controls["right-upper-arm-depth"]
        self.assertGreater(dict(left.target_weights)["l-upperarm-scale-depth-incr"], 0)
        self.assertEqual(dict(left.target_weights)["l-upperarm-scale-depth-decr"], 0)
        self.assertEqual(right.weight, 0)

    def test_deltoid_and_soft_tissue_are_not_driven_by_pattern_landmarks(self) -> None:
        profile = self.default_profile()
        profile["deltoidProminenceL"] = 0
        profile["upperArmSoftTissueL"] = 0
        controls = {control.name: control for control in evaluate_morph_controls(profile)}
        deltoid = controls["left-deltoid-prominence"]
        soft_tissue = controls["left-upper-arm-soft-tissue"]
        self.assertGreater(dict(deltoid.target_weights)["l-upperarm-shoulder-muscle-decr"], 0)
        self.assertGreater(dict(soft_tissue.target_weights)["l-upperarm-fat-decr"], 0)
        self.assertNotIn("armholeDepthL", deltoid.source_keys)
        self.assertNotIn("armscyeCircL", soft_tissue.source_keys)

    def test_signed_controls_choose_the_correct_target(self) -> None:
        profile = self.default_profile()
        profile["neckForward"] = -4
        controls = {control.name: control for control in evaluate_morph_controls(profile)}
        neck = controls["head-forward-offset"]
        self.assertEqual(neck.direction, "decrease")
        self.assertGreater(dict(neck.target_weights)["neck-trans-backward"], 0)
        self.assertEqual(dict(neck.target_weights)["neck-trans-forward"], 0)

    def test_normalization_clamps_to_declared_range(self) -> None:
        self.assertEqual(normalized_delta(1000, 5, 0, 10), 1)
        self.assertEqual(normalized_delta(-1000, 5, 0, 10), -1)
        self.assertEqual(normalized_delta(5, 5, 0, 10), 0)

    def test_mapping_has_material_coverage_and_unique_targets(self) -> None:
        self.assertGreaterEqual(len(mapped_measurement_keys()), 40)
        target_names = [
            target
            for spec in MORPH_CONTROL_SPECS
            for pair in spec.target_pairs
            for target in pair
        ]
        self.assertEqual(len(target_names), len(set(target_names)))


if __name__ == "__main__":
    unittest.main()
