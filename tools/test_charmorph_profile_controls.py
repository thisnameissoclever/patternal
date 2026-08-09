#!/usr/bin/env python3

from __future__ import annotations

import unittest
from pathlib import Path
import sys

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from charmorph_morphs import MorphDelta
from charmorph_profile_controls import FIT_CONTROL_NAMES, resolve_fit_control_contract


class CharMorphProfileControlTests(unittest.TestCase):
    def test_resolves_antonia_direct_morph_contract(self) -> None:
        empty = MorphDelta(indices=None, delta=np.zeros((1, 3)))
        names = {
            "Breast big",
            "Breast diameter",
            "Breast implant",
            "PBM-breasts-classic",
            "Breast move to outside",
            "Breast move to inside",
            "Breast hang forward",
            "Pear",
            "Hip narrow",
            "Belly flat",
            "Belly thick",
            "Waist narrow",
        }
        contract = resolve_fit_control_contract({name: empty for name in names})
        self.assertEqual("Antonia Polygon", contract.backend)
        self.assertEqual(2.0, contract.bust_separation_weight)
        self.assertEqual((0.35, 0.60), contract.fit_control_bounds["Breast big"])

    def test_rejects_backend_without_measurement_controls(self) -> None:
        empty = MorphDelta(indices=None, delta=np.zeros((1, 3)))
        with self.assertRaisesRegex(ValueError, "no supported Patterna"):
            resolve_fit_control_contract({"Smile": empty})

    def test_resolves_mb_signed_control_contract(self) -> None:
        empty = MorphDelta(indices=None, delta=np.zeros((1, 3)))
        raw = {
            f"{name}_max": empty
            for name in FIT_CONTROL_NAMES
        }
        raw.update({f"{name}_min": empty for name in FIT_CONTROL_NAMES})
        contract = resolve_fit_control_contract(raw)
        self.assertEqual("CharMorph MB female", contract.backend)
        self.assertEqual(1.0, contract.bust_separation_weight)


if __name__ == "__main__":
    unittest.main()
