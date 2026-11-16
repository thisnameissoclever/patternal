#!/usr/bin/env python3
"""Turn the Anny body's own measurements into pattern grading overrides.

The shirt in the packaged result was graded to the Antonia measurement set and
then worn by a different body, which is why its back hem drags, its sleeve
heads stand proud, and it sits short. Grading it to this body needs this body's
numbers, and those already exist: the avatar worker measured the mesh it built
and recorded, for every objective, the value it actually achieved alongside the
value it was aiming for.

This reads that report and emits the measurement overrides for
``Patternal.SimulationPipelineProof``, taking the achieved value rather than
the target, because the achieved value is what the garment has to fit. Each
objective names the bridge measurement keys it feeds, so the mapping is the
report's own and not a second opinion invented here.

Two grading inputs have no measured objective on this body: the armhole depth
and the armscye circumference. They are reported as carried over unchanged, so
the limitation travels with the result instead of being silently absorbed.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

SCHEMA_VERSION = "patterna.regrade-measurements/1.0"
MEASUREMENT_SCHEMA = "patterna.anny-worker-measurements/1.0"

# Grading inputs the drafter reads, and the objective that measures each one.
# Every objective listed here declares these keys in its own sourceKeys.
GRADING_OBJECTIVES = {
    "circumference|bust": ["chest"],
    "circumference|waist": ["waist"],
    "circumference|hip": ["hip"],
    "circumference|underbust": ["underBust"],
    "circumference|abdomen": ["abdomenCirc"],
    "circumference|neck-base": ["neckBaseCirc"],
    "circumference|mid-neck": ["neckCirc"],
    "circumference|upper-arm::L": ["upperArmCircL"],
    "circumference|upper-arm::R": ["upperArmCircR"],
    "distance|shoulder-breadth": ["shoulder"],
    "distance|bust-apex-separation": ["bustSeparation"],
    "height|nape-to-waist": ["torso", "backNeckWaist", "backWaistLength"],
    "height|bust-apex": ["bustHeightL", "bustHeightR"],
    "length|shoulder-to-wrist": ["armLengthL", "armLengthR"],
    "length|neck-to-shoulder-tip": ["shoulderLengthL", "shoulderLengthR"],
    "length|shoulder-to-elbow": ["shoulderElbowL", "shoulderElbowR"],
    "length|elbow-to-wrist": ["elbowWristL", "elbowWristR"],
    "projection|bust-apex": ["bustProjectionL", "bustProjectionR"],
    "stature|floor-to-crown": ["height"],
}

# Read by the drafter but never measured on this body.
CARRIED_OVER = ["armholeDepthL", "armholeDepthR", "armscyeCircL", "armscyeCircR"]


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--measurement-report", required=True, type=Path)
    parser.add_argument("--profile-bridge", required=True, type=Path)
    parser.add_argument("--report", required=True, type=Path)
    parser.add_argument("--arguments-file", required=True, type=Path)
    return parser.parse_args()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def bridge_measurements(document: object) -> list[dict]:
    """Find the measurement list wherever the bridge nests it."""
    if isinstance(document, dict):
        entries = document.get("measurements")
        if isinstance(entries, list):
            return entries
        for value in document.values():
            found = bridge_measurements(value)
            if found:
                return found
    if isinstance(document, list):
        for value in document:
            found = bridge_measurements(value)
            if found:
                return found
    return []


def main() -> int:
    arguments = parse_arguments()
    report_path = arguments.measurement_report.resolve(strict=True)
    measured = json.loads(report_path.read_text(encoding="utf-8"))
    if measured.get("schemaVersion") != MEASUREMENT_SCHEMA:
        raise ValueError("Unsupported avatar measurement report schema.")

    rows = {str(row["objective"]): row for row in measured["rows"]}
    bridge_path = arguments.profile_bridge.resolve(strict=True)
    existing = {
        str(entry["key"]): float(entry["value"])
        for entry in bridge_measurements(json.loads(bridge_path.read_text(encoding="utf-8")))
        if "key" in entry and "value" in entry
    }

    overrides: list[dict] = []
    for objective, keys in GRADING_OBJECTIVES.items():
        row = rows.get(objective)
        if row is None:
            raise ValueError(f"The report does not measure {objective}.")
        declared = [str(key) for key in row.get("sourceKeys", [])]
        achieved = round(float(row["predictedCm"]), 2)
        for key in keys:
            if key not in existing:
                # The bridge is the drafter's own input, so a key it does not
                # carry cannot be overridden and must not be invented.
                continue
            if key not in declared:
                raise ValueError(
                    f"{objective} does not declare {key} among its source keys."
                )
            overrides.append(
                {
                    "key": key,
                    "objective": objective,
                    "previousCm": existing[key],
                    "measuredCm": achieved,
                    "deltaCm": round(achieved - existing[key], 2),
                    "withinDeclaredTolerance": bool(row.get("withinTolerance")),
                    "targetCm": round(float(row["targetCm"]), 2),
                }
            )

    carried = [
        {"key": key, "carriedOverCm": existing[key]}
        for key in CARRIED_OVER
        if key in existing
    ]

    report = {
        "schemaVersion": SCHEMA_VERSION,
        "claims": {
            "accepted": False,
            "gradedForThisBody": False,
            "allGradingInputsMeasured": False,
        },
        "openGates": [
            "The armhole depth and armscye circumference have no measured objective on this body and are carried over from the previous grading, so the armhole is not yet this body's own.",
            "Grading a block to measurements is not the same as drafting a block for a body; this closes the measurement gap, not the drafting one.",
        ],
        "sourceMeasurementReport": {
            "path": str(report_path),
            "sha256": sha256_file(report_path),
            "bodyStateId": measured.get("bodyStateId"),
        },
        "profileBridge": {"path": str(bridge_path), "sha256": sha256_file(bridge_path)},
        "overrides": overrides,
        "carriedOver": carried,
        "largestChangeCm": max(
            (abs(entry["deltaCm"]) for entry in overrides), default=0.0
        ),
    }
    arguments.report.parent.mkdir(parents=True, exist_ok=True)
    arguments.report.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")

    lines = [f"--measurement {entry['key']}={entry['measuredCm']}" for entry in overrides]
    arguments.arguments_file.parent.mkdir(parents=True, exist_ok=True)
    arguments.arguments_file.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(
        json.dumps(
            {
                "overrides": len(overrides),
                "carriedOver": [entry["key"] for entry in carried],
                "largestChangeCm": report["largestChangeCm"],
            },
            indent=2,
        )
    )
    for entry in sorted(overrides, key=lambda item: -abs(item["deltaCm"]))[:10]:
        print(
            f"  {entry['key']:<18} {entry['previousCm']:>7.2f} -> "
            f"{entry['measuredCm']:>7.2f}  ({entry['deltaCm']:+.2f} cm)"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
