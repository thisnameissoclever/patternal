from __future__ import annotations

from pathlib import Path
import unittest

from tools.named_shirt_arrangement_template import load_template, map_torso_half


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
TEMPLATE_PATH = (
    REPOSITORY_ROOT
    / "tools"
    / "fixtures"
    / "crew-neck-14-panel-arrangement-template-v1.json"
)
SOURCE_DOCUMENT = (
    REPOSITORY_ROOT
    / "artifacts"
    / "revision-anny-source-v2"
    / "bundle"
    / "objects"
    / "a92f9a87b3b89c4578b2468fcf9b68a04a544512be7ccaee75529c19c7bcf8e8.corrected.specification.json"
)


@unittest.skipUnless(SOURCE_DOCUMENT.is_file(), "ignored source document is unavailable")
class NamedShirtArrangementTemplateTests(unittest.TestCase):
    def test_exact_source_stitches_are_classified_once(self) -> None:
        template = load_template(TEMPLATE_PATH, SOURCE_DOCUMENT)

        roles = template["stitchRoles"]
        classified = [index for indices in roles.values() for index in indices]
        self.assertEqual(list(range(38)), sorted(classified))
        self.assertEqual(len(classified), len(set(classified)))
        self.assertIn(12, roles["shoulder"])
        self.assertIn(32, roles["bustDart"])
        self.assertIn(7, roles["armhole"])
        self.assertIn(13, roles["sideSeam"])

    def test_front_and_back_torso_halves_meet_at_body_sides(self) -> None:
        front_center = map_torso_half(0.0, 30.0, 20.0, 15.0, front=True)
        back_center = map_torso_half(0.0, 30.0, 20.0, 15.0, front=False)
        front_side = map_torso_half(1.0, 30.0, 20.0, 15.0, front=True)
        back_side = map_torso_half(1.0, 30.0, 20.0, 15.0, front=False)

        self.assertEqual((0.0, 20.0), front_center)
        self.assertEqual((0.0, -15.0), back_center)
        self.assertAlmostEqual(front_side[0], 30.0)
        self.assertAlmostEqual(front_side[1], 0.0)
        self.assertAlmostEqual(front_side[0], back_side[0])
        self.assertAlmostEqual(front_side[1], back_side[1])


if __name__ == "__main__":
    unittest.main()
