from __future__ import annotations

from pathlib import Path
import re
import unittest

from tools.mpfb_local_deformations import (
    LOCAL_DEFORMATION_SPECS,
    apply_local_deformations,
    local_deformation_keys,
)
from tools.mpfb_morph_controls import (
    DIRECT_RULER_SOURCE_KEYS,
    mapped_measurement_keys,
)


REPO_ROOT = Path(__file__).resolve().parents[1]


def ui_measurement_keys() -> set[str]:
    source = (REPO_ROOT / "Patternal" / "MainPage.xaml.cs").read_text(encoding="utf-8")
    keys = set(re.findall(r'P\("([A-Za-z0-9]+)"', source))
    limb_prefixes = (
        "armLength", "shoulderElbow", "elbowWrist", "upperArmCirc",
        "bicepDepth", "elbowCirc", "forearmCirc", "wristCirc",
        "deltoidProminence", "upperArmSoftTissue",
        "handLength", "palmWidth", "palmCirc", "thumbBaseCirc",
        "armholeDepth", "armscyeCirc",
    )
    leg_prefixes = (
        "outseam", "inseam", "waistKnee", "crotchKnee",
        "thighUpperCirc", "thighMidCirc", "kneeCirc", "calfCirc",
        "ankleCirc", "kneeHeight", "lowerLegLength", "footLength",
        "footWidth", "ballGirth", "heelGirth", "archHeight", "legOffset",
    )
    for prefix in limb_prefixes + leg_prefixes:
        keys.update((f"{prefix}L", f"{prefix}R"))
    keys.update(("height", "chest", "waist", "hip", "shoulder", "torso"))
    return keys


def synthetic_body() -> list[tuple[float, float, float]]:
    return [
        (x, y, z)
        for x in (-0.35, -0.28, -0.18, -0.08, 0.08, 0.18, 0.28, 0.35)
        for y in (-0.12, -0.04, 0.04, 0.12)
        for z in (
            0.0, 0.05, 0.12, 0.30, 0.48, 0.62, 0.78, 0.88,
            1.0, 1.15, 1.28, 1.36, 1.52, 1.67,
        )
    ]


class MpfbLocalDeformationTests(unittest.TestCase):
    def default_profile(self) -> dict[str, float]:
        return {spec.source_key: spec.default for spec in LOCAL_DEFORMATION_SPECS}

    def test_defaults_preserve_every_vertex(self) -> None:
        source = synthetic_body()
        result, evidence = apply_local_deformations(source, self.default_profile())
        self.assertEqual(result, source)
        self.assertEqual(len(evidence), len(LOCAL_DEFORMATION_SPECS))
        self.assertTrue(all(item.affected_vertex_count == 0 for item in evidence))

    def test_every_local_control_changes_the_surface(self) -> None:
        source = synthetic_body()
        for spec in LOCAL_DEFORMATION_SPECS:
            with self.subTest(control=spec.name):
                profile = self.default_profile()
                profile[spec.source_key] = spec.maximum
                result, evidence = apply_local_deformations(source, profile)
                selected = next(item for item in evidence if item.name == spec.name)
                self.assertNotEqual(result, source)
                self.assertGreater(selected.affected_vertex_count, 0)
                self.assertGreater(selected.maximum_displacement_cm, 0)

    def test_supported_bust_control_is_bounded_and_distributed(self) -> None:
        source = [
            (0.0, 0.0, 0.0),
            (0.0, 0.0, 1.67),
            (0.10, 0.12, 1.22),
            (0.10, 0.12, 1.28),
            (0.10, 0.12, 1.34),
        ]
        profile = self.default_profile()
        profile["bustSupport"] = 100.0

        result, evidence = apply_local_deformations(source, profile)
        support = next(item for item in evidence if item.name == "supported-bust-shaping")

        self.assertLessEqual(support.maximum_displacement_cm, 2.6)
        self.assertGreater(result[2][2], source[2][2])
        self.assertGreater(result[3][2], source[3][2])
        self.assertGreater(result[4][2], source[4][2])
        self.assertLess(
            abs(result[2][1] - source[2][1]),
            0.003,
            "Support must not carve a deep shelf into the lower bust.",
        )

    def test_all_145_builtin_measurements_have_an_explicit_mesh_lane(self) -> None:
        ui_keys = ui_measurement_keys()
        covered = (
            set(DIRECT_RULER_SOURCE_KEYS)
            | mapped_measurement_keys()
            | local_deformation_keys()
        )
        self.assertEqual(len(ui_keys), 151)
        self.assertEqual(ui_keys - covered, set())

    def test_local_bindings_are_unique(self) -> None:
        keys = [spec.source_key for spec in LOCAL_DEFORMATION_SPECS]
        self.assertEqual(len(keys), len(set(keys)))


if __name__ == "__main__":
    unittest.main()
