from __future__ import annotations

import unittest

from tools.mpfb_fit_acceptance import evaluate_fit_acceptance, resolve_source_keys


class MpfbFitAcceptanceTests(unittest.TestCase):
    def evaluate(
        self,
        *,
        measured: float,
        reachable: bool,
        origin: str | None,
    ) -> dict:
        origins = {} if origin is None else {"acrossFront": origin}
        return evaluate_fit_acceptance(
            requested_measurements={"front_chest_distance": 34.8},
            final_measurements={"front_chest_distance": measured},
            fit_results={"front_chest_distance": {"reachable": reachable}},
            tolerance_cm=0.15,
            target_source_keys={"front_chest_distance": ("acrossFront",)},
            measurement_sources={},
            measurement_origins=origins,
            height_result=None,
        )

    def test_accurate_measurement_is_accepted_for_every_origin(self) -> None:
        for origin in ("manual", "manual-or-baseline", "estimated", None):
            with self.subTest(origin=origin):
                result = self.evaluate(measured=34.7, reachable=True, origin=origin)
                self.assertTrue(result["accepted"])

    def test_unreachable_estimate_is_accepted_and_disclosed(self) -> None:
        result = self.evaluate(measured=31.7, reachable=False, origin="estimated")
        self.assertTrue(result["accepted"])
        self.assertEqual(
            result["accepted_estimated_unreachable"],
            ["front_chest_distance"],
        )
        self.assertEqual(
            result["targets"]["front_chest_distance"]["disposition"],
            "accepted-estimated-unreachable",
        )

    def test_unreachable_manual_measurement_remains_blocking(self) -> None:
        result = self.evaluate(measured=31.7, reachable=False, origin="manual")
        self.assertFalse(result["accepted"])
        self.assertEqual(result["blocking_failures"], ["front_chest_distance"])

    def test_reachable_estimate_outside_tolerance_remains_blocking(self) -> None:
        result = self.evaluate(measured=33.0, reachable=True, origin="estimated")
        self.assertFalse(result["accepted"])

    def test_missing_origin_remains_hard_for_legacy_profiles(self) -> None:
        result = self.evaluate(measured=31.7, reachable=False, origin=None)
        self.assertFalse(result["accepted"])

    def test_body_alias_resolves_to_editable_measurement_origin(self) -> None:
        self.assertEqual(
            resolve_source_keys(
                ("bust",),
                {"bust": ["chest"]},
            ),
            ["chest"],
        )
        result = evaluate_fit_acceptance(
            requested_measurements={"bust_circumference": 94.0},
            final_measurements={"bust_circumference": 90.0},
            fit_results={"bust_circumference": {"reachable": False}},
            tolerance_cm=0.15,
            target_source_keys={"bust_circumference": ("bust",)},
            measurement_sources={"bust": ["chest"]},
            measurement_origins={"chest": "manual-override"},
            height_result=None,
        )
        self.assertFalse(result["accepted"])
        self.assertEqual(
            result["targets"]["bust_circumference"]["source_origins"],
            {"chest": "manual-override"},
        )

    def test_height_is_always_a_hard_gate(self) -> None:
        result = evaluate_fit_acceptance(
            requested_measurements={},
            final_measurements={},
            fit_results={},
            tolerance_cm=0.15,
            target_source_keys={},
            measurement_sources={"height": ["height"]},
            measurement_origins={"height": "estimated"},
            height_result={"target_cm": 167.0, "measured_cm": 166.0},
        )
        self.assertFalse(result["accepted"])
        self.assertEqual(result["blocking_failures"], ["height"])


if __name__ == "__main__":
    unittest.main()
