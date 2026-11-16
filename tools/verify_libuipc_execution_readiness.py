#!/usr/bin/env python3
"""Assess whether an immutable arrangement plan is safe to execute."""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
import sys
from typing import Any

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from tools.verify_libuipc_arrangement_plan import PLAN_NAME, verify_plan


MAXIMUM_INITIAL_SEAM_SEPARATION_CM = 2.0


def assess_execution_readiness(plan: dict[str, Any]) -> dict[str, Any]:
    staging = plan.get("sourceStaging")
    if not isinstance(staging, dict):
        raise ValueError("The arrangement plan is missing source staging evidence.")
    staging_accepted = staging.get("acceptedForArrangementEngine")
    if staging_accepted is not True:
        return {
            "schemaVersion": "patterna.libuipc-execution-readiness/1.0",
            "sourceBundleId": plan.get("sourceBundleId"),
            "executionAuthorized": False,
            "gates": [
                {
                    "name": "sourceStagingAccepted",
                    "passed": False,
                    "actual": staging_accepted,
                    "required": "true",
                }
            ],
        }
    staging_gates = staging.get("gates")
    staging_gates_passed = (
        isinstance(staging_gates, list)
        and bool(staging_gates)
        and all(
            isinstance(gate, dict) and gate.get("passed") is True
            for gate in staging_gates
        )
    )
    if not staging_gates_passed:
        return {
            "schemaVersion": "patterna.libuipc-execution-readiness/1.0",
            "sourceBundleId": plan.get("sourceBundleId"),
            "executionAuthorized": False,
            "gates": [
                {
                    "name": "sourceStagingGatesPassed",
                    "passed": False,
                    "actual": False,
                    "required": "true",
                }
            ],
        }
    maximum = staging.get("maximumSeamSeparationCm")
    if (
        isinstance(maximum, bool)
        or not isinstance(maximum, (int, float))
        or not math.isfinite(maximum)
        or maximum < 0
    ):
        raise ValueError("Source staging is missing maximum seam separation.")
    passed = maximum <= MAXIMUM_INITIAL_SEAM_SEPARATION_CM
    return {
        "schemaVersion": "patterna.libuipc-execution-readiness/1.0",
        "sourceBundleId": plan.get("sourceBundleId"),
        "executionAuthorized": passed,
        "gates": [
            {
                "name": "maximumInitialSeamSeparationCm",
                "passed": passed,
                "actual": maximum,
                "required": f"<= {MAXIMUM_INITIAL_SEAM_SEPARATION_CM}",
            }
        ],
    }


def verify_execution_readiness(
    plan_directory: Path,
    source_bundle_directory: Path | None,
) -> dict[str, Any]:
    if source_bundle_directory is None:
        raise ValueError("Execution readiness requires the exact source bundle.")
    integrity = verify_plan(plan_directory, source_bundle_directory)
    plan_path = plan_directory.resolve(strict=True) / PLAN_NAME
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    result = assess_execution_readiness(plan)
    result["immutablePlanIntegrityVerified"] = integrity["accepted"]
    result["sourceBundleVerified"] = integrity["sourceBundleVerified"]
    result["planId"] = integrity["planId"]
    return result


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", required=True, type=Path)
    parser.add_argument("--source-bundle", required=True, type=Path)
    return parser.parse_args()


def main() -> int:
    arguments = parse_arguments()
    result = verify_execution_readiness(arguments.plan, arguments.source_bundle)
    print(json.dumps(result, indent=2))
    return 0 if result["executionAuthorized"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
