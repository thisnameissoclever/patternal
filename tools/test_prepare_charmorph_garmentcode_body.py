from __future__ import annotations

import unittest

import numpy as np

from tools.prepare_charmorph_garmentcode_body import (
    blender_obj_to_garmentcode,
    semantic_segmentation,
)


class PrepareCharMorphGarmentCodeBodyTests(unittest.TestCase):
    def test_coordinate_conversion_preserves_front_and_zeroes_floor(self) -> None:
        source = np.asarray([
            [-0.2, 0.1, -0.1],
            [0.2, 0.3, 1.6],
        ])
        converted = blender_obj_to_garmentcode(source)
        np.testing.assert_allclose(converted[0], [-0.2, 0.0, 0.1])
        np.testing.assert_allclose(converted[1], [0.2, 1.7, 0.3])

    def test_segmentation_keeps_torso_and_separates_limbs(self) -> None:
        vertices = np.asarray([
            [0.0, 1.1, 0.1],
            [-0.5, 1.1, 0.0],
            [0.5, 1.1, 0.0],
            [-0.1, 0.3, 0.0],
            [0.1, 0.3, 0.0],
            [0.0, 1.65, 0.0],
        ])
        segmentation = semantic_segmentation(vertices)
        self.assertEqual([0, 5], segmentation["body"])
        self.assertEqual([1], segmentation["left_arm"])
        self.assertEqual([2], segmentation["right_arm"])
        self.assertEqual([3], segmentation["left_leg"])
        self.assertEqual([4], segmentation["right_leg"])

    def test_lower_abdomen_remains_in_body_segment(self) -> None:
        vertices = np.asarray([
            [-0.1, 0.0, 0.0],
            [0.1, 0.80, 0.0],
            [0.1, 0.95, 0.0],
            [0.35, 1.25, 0.0],
            [0.0, 1.67, 0.0],
        ])
        segmentation = semantic_segmentation(vertices)
        self.assertIn(1, segmentation["left_leg"] + segmentation["right_leg"])
        self.assertIn(2, segmentation["body"])
        self.assertIn(3, segmentation["right_arm"])


if __name__ == "__main__":
    unittest.main()
