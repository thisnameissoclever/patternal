from __future__ import annotations

from pathlib import Path
import json
import subprocess
import sys
import unittest

from tools.verify_libuipc_execution_readiness import (
    assess_execution_readiness,
    verify_execution_readiness,
)


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
ANNY_PLAN = REPOSITORY_ROOT / "artifacts" / "libuipc-anny-plan-v2"
ANNY_SOURCE_BUNDLE = REPOSITORY_ROOT / "artifacts" / "revision-anny-source-v2" / "bundle"


class LibuipcExecutionReadinessTests(unittest.TestCase):
    def test_plan_with_sixty_five_centimeter_seam_span_is_refused_execution(self) -> None:
        plan = {
            "schemaVersion": "patterna.libuipc-arrangement-scene-plan/1.0",
            "sourceBundleId": "fixture-bundle",
            "sourceStaging": {
                "acceptedForArrangementEngine": True,
                "gates": [{"name": "finitePositions", "passed": True}],
                "maximumSeamSeparationCm": 65.09543638151202,
                "p95SeamSeparationCm": 64.7467385594419,
            },
        }

        result = assess_execution_readiness(plan)

        self.assertFalse(result["executionAuthorized"])
        self.assertEqual(
            {
                "name": "maximumInitialSeamSeparationCm",
                "passed": False,
                "actual": 65.09543638151202,
                "required": "<= 2.0",
            },
            result["gates"][0],
        )

    @unittest.skipUnless(
        ANNY_PLAN.is_dir() and ANNY_SOURCE_BUNDLE.is_dir(),
        "ignored exact Anny plan or source bundle is unavailable",
    )
    def test_exact_anny_plan_is_integrity_verified_but_not_authorized(self) -> None:
        result = verify_execution_readiness(ANNY_PLAN, ANNY_SOURCE_BUNDLE)

        self.assertTrue(result["immutablePlanIntegrityVerified"])
        self.assertFalse(result["executionAuthorized"])
        self.assertEqual(65.09543638151202, result["gates"][0]["actual"])

    @unittest.skipUnless(
        ANNY_PLAN.is_dir() and ANNY_SOURCE_BUNDLE.is_dir(),
        "ignored exact Anny plan or source bundle is unavailable",
    )
    def test_cli_returns_nonzero_for_unauthorized_plan(self) -> None:
        completed = subprocess.run(
            [
                sys.executable,
                str(REPOSITORY_ROOT / "tools" / "verify_libuipc_execution_readiness.py"),
                "--plan",
                str(ANNY_PLAN),
                "--source-bundle",
                str(ANNY_SOURCE_BUNDLE),
            ],
            cwd=REPOSITORY_ROOT,
            capture_output=True,
            text=True,
            check=False,
        )

        self.assertEqual(2, completed.returncode)
        self.assertFalse(json.loads(completed.stdout)["executionAuthorized"])

    @unittest.skipUnless(ANNY_PLAN.is_dir(), "ignored exact Anny plan is unavailable")
    def test_execution_readiness_requires_the_exact_source_bundle(self) -> None:
        with self.assertRaisesRegex(ValueError, "source bundle"):
            verify_execution_readiness(ANNY_PLAN, None)

    def test_plan_rejected_by_staging_cannot_be_authorized(self) -> None:
        plan = {
            "schemaVersion": "patterna.libuipc-arrangement-scene-plan/1.0",
            "sourceBundleId": "fixture-bundle",
            "sourceStaging": {
                "acceptedForArrangementEngine": False,
                "maximumSeamSeparationCm": 1.25,
                "p95SeamSeparationCm": 0.75,
            },
        }

        result = assess_execution_readiness(plan)

        self.assertFalse(result["executionAuthorized"])
        self.assertEqual(
            {
                "name": "sourceStagingAccepted",
                "passed": False,
                "actual": False,
                "required": "true",
            },
            result["gates"][0],
        )

    def test_boolean_seam_distance_is_rejected_as_malformed_evidence(self) -> None:
        plan = {
            "schemaVersion": "patterna.libuipc-arrangement-scene-plan/1.0",
            "sourceBundleId": "fixture-bundle",
            "sourceStaging": {
                "acceptedForArrangementEngine": True,
                "gates": [{"name": "finitePositions", "passed": True}],
                "maximumSeamSeparationCm": True,
                "p95SeamSeparationCm": 0.75,
            },
        }

        with self.assertRaisesRegex(ValueError, "maximum seam separation"):
            assess_execution_readiness(plan)

    def test_failed_staging_gate_cannot_hide_behind_an_accepted_flag(self) -> None:
        plan = {
            "schemaVersion": "patterna.libuipc-arrangement-scene-plan/1.0",
            "sourceBundleId": "fixture-bundle",
            "sourceStaging": {
                "acceptedForArrangementEngine": True,
                "gates": [{"name": "constraintChordClearance", "passed": False}],
                "maximumSeamSeparationCm": 1.25,
                "p95SeamSeparationCm": 0.75,
            },
        }

        result = assess_execution_readiness(plan)

        self.assertFalse(result["executionAuthorized"])
        self.assertEqual("sourceStagingGatesPassed", result["gates"][0]["name"])

    def test_negative_seam_distance_is_rejected_as_malformed_evidence(self) -> None:
        plan = {
            "schemaVersion": "patterna.libuipc-arrangement-scene-plan/1.0",
            "sourceBundleId": "fixture-bundle",
            "sourceStaging": {
                "acceptedForArrangementEngine": True,
                "gates": [{"name": "finitePositions", "passed": True}],
                "maximumSeamSeparationCm": -0.01,
                "p95SeamSeparationCm": 0.0,
            },
        }

        with self.assertRaisesRegex(ValueError, "maximum seam separation"):
            assess_execution_readiness(plan)


if __name__ == "__main__":
    unittest.main()
