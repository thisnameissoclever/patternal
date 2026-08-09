#!/usr/bin/env python3

from __future__ import annotations

import unittest
from pathlib import Path
import sys

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from charmorph_character import load_character
from charmorph_morphs import apply_controls, load_packed_morphs


REPO_ROOT = Path(__file__).resolve().parents[1]
CHARACTERS = REPO_ROOT / "third_party" / "CharMorph-db" / "characters"


class CharMorphCharacterTests(unittest.TestCase):
    def test_resolves_antonia_cc_by_contract(self) -> None:
        descriptor = load_character(CHARACTERS / "antonia")
        self.assertEqual("cm_antonia", descriptor.object_name)
        self.assertEqual("Default", descriptor.basis_name)
        self.assertEqual("CC-BY 3.0", descriptor.license_name)
        self.assertEqual("Olaf Delgado-Friedrichs", descriptor.author)
        self.assertEqual("https://sites.google.com/site/antoniapolygon/", descriptor.source_url)
        self.assertEqual("L2.npz", descriptor.morph_pack_path.name)
        self.assertEqual(16, len(descriptor.material_names))
        self.assertEqual(("panties", "bra"), descriptor.underwear_names)
        self.assertGreaterEqual(len(descriptor.albedo_paths), 4)
        self.assertGreaterEqual(len(descriptor.texture_paths), 15)
        self.assertIsNone(descriptor.single_body_albedo)

    def test_resolves_mb_female_agpl_contract(self) -> None:
        descriptor = load_character(CHARACTERS / "mb_female")
        self.assertEqual("mb_female", descriptor.object_name)
        self.assertEqual("AGPL3", descriptor.license_name)
        self.assertEqual("__main__.npz", descriptor.morph_pack_path.name)
        self.assertEqual("albedo.png", descriptor.single_body_albedo.name)

    def test_rejects_reom_without_packaged_license_artifact(self) -> None:
        with self.assertRaisesRegex(FileNotFoundError, "character license not found"):
            load_character(CHARACTERS / "reom")

    def test_antonia_direct_morph_changes_real_character_geometry(self) -> None:
        descriptor = load_character(CHARACTERS / "antonia")
        basis = np.load(descriptor.basis_path)
        morphs = load_packed_morphs(descriptor.morph_pack_path)
        vertices, weights = apply_controls(basis, morphs, {"Breast big": 0.5})

        self.assertEqual({"Breast big": 0.5}, weights)
        self.assertGreater(float(np.max(np.abs(vertices - basis))), 0.0)


if __name__ == "__main__":
    unittest.main()
