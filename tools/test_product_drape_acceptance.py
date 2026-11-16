from __future__ import annotations

import unittest

from tools.product_drape_acceptance import evaluate_product_drape_acceptance


ARRANGEMENT_ID = "a" * 64
REVIEW_HASH = "b" * 64


def accepted_packaged_report() -> dict:
    return {
        "schemaVersion": "patterna.packaged-drape-assets/1.0",
        "arrangementId": ARRANGEMENT_ID,
        "claims": {
            "producerAccepted": True,
            "packagedVisualQualityAccepted": True,
            "calibratedFabric": True,
            "patternDraftedForThisBody": True,
        },
        "openGates": [],
        "visualReview": {
            "accepted": True,
            "sixViewManifestSha256": REVIEW_HASH,
        },
    }


def accepted_renderer_report() -> dict:
    return {
        "schemaVersion": "patterna.packaged-drape-asset-verification/1.0",
        "arrangementId": ARRANGEMENT_ID,
        "claims": {
            "accepted": True,
            "packagedVisualQualityAccepted": True,
        },
        "rendererWouldLoad": True,
        "issues": [],
    }


class ProductDrapeAcceptanceTests(unittest.TestCase):
    def test_accepts_only_a_closed_hash_bound_product_gate(self) -> None:
        result = evaluate_product_drape_acceptance(
            accepted_packaged_report(), accepted_renderer_report()
        )

        self.assertTrue(result["accepted"])
        self.assertEqual([], result["reasons"])

    def test_rejects_every_false_packaged_claim(self) -> None:
        packaged = accepted_packaged_report()
        for claim in packaged["claims"]:
            with self.subTest(claim=claim):
                candidate = accepted_packaged_report()
                candidate["claims"][claim] = False
                result = evaluate_product_drape_acceptance(
                    candidate, accepted_renderer_report()
                )
                self.assertFalse(result["accepted"])
                self.assertTrue(any(claim in reason for reason in result["reasons"]))

    def test_rejects_open_gates_and_unaccepted_visual_review(self) -> None:
        packaged = accepted_packaged_report()
        packaged["openGates"] = ["Fabric constants are estimated."]
        packaged["visualReview"]["accepted"] = False

        result = evaluate_product_drape_acceptance(
            packaged, accepted_renderer_report()
        )

        self.assertFalse(result["accepted"])
        self.assertTrue(any("openGates" in reason for reason in result["reasons"]))
        self.assertTrue(any("visualReview.accepted" in reason for reason in result["reasons"]))

    def test_rejects_missing_or_malformed_six_view_hash(self) -> None:
        for value in (None, "", "not-a-sha256"):
            with self.subTest(value=value):
                packaged = accepted_packaged_report()
                packaged["visualReview"]["sixViewManifestSha256"] = value
                result = evaluate_product_drape_acceptance(
                    packaged, accepted_renderer_report()
                )
                self.assertFalse(result["accepted"])
                self.assertTrue(
                    any("sixViewManifestSha256" in reason for reason in result["reasons"])
                )

    def test_rejects_renderer_failure_or_arrangement_mismatch(self) -> None:
        renderer = accepted_renderer_report()
        renderer["arrangementId"] = "c" * 64
        renderer["rendererWouldLoad"] = False
        renderer["issues"] = ["Missing texture coordinates."]
        renderer["claims"]["accepted"] = False

        result = evaluate_product_drape_acceptance(
            accepted_packaged_report(), renderer
        )

        self.assertFalse(result["accepted"])
        self.assertTrue(any("arrangementId" in reason for reason in result["reasons"]))
        self.assertTrue(any("rendererWouldLoad" in reason for reason in result["reasons"]))
        self.assertTrue(any("renderer issues" in reason for reason in result["reasons"]))
        self.assertTrue(any("claims.accepted" in reason for reason in result["reasons"]))

    def test_rejects_unknown_schemas(self) -> None:
        packaged = accepted_packaged_report()
        renderer = accepted_renderer_report()
        packaged["schemaVersion"] = "unknown"
        renderer["schemaVersion"] = "unknown"

        result = evaluate_product_drape_acceptance(packaged, renderer)

        self.assertFalse(result["accepted"])
        self.assertEqual(2, sum("schemaVersion" in reason for reason in result["reasons"]))


if __name__ == "__main__":
    unittest.main()
