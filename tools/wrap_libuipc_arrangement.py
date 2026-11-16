#!/usr/bin/env python3
"""Wrap a libuipc arrangement execution as an immutable arrangement artifact.

Consumes the exact source revision bundle, the immutable libuipc arrangement
plan, and one raw execution output from ``run_libuipc_arrangement.py``. It
verifies every identity in that chain, converts the Y-up meter positions back
to the bundle's Y-up centimeter convention in exact source panel order, and
writes the standard ``patterna.exact-triangle-arrangement/1.0`` artifact with
``claims.accepted`` fixed to false. Acceptance can come only from the
independent verifier.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
from typing import Any

import numpy as np

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from tools.exact_triangle_arrangement import (
    ARRANGEMENT_SCHEMA,
    MANIFEST_SCHEMA,
    SUPPORTED_ARCHETYPE,
    build_constraints,
    role_path,
)
from tools.revision_bundle import canonical_json, sha256_file, verify_bundle


EXECUTION_SCHEMA = "patterna.libuipc-arrangement-execution/1.0"
SETTLE_SCHEMA = "patterna.libuipc-gravity-settle/1.0"


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle", required=True, type=Path)
    parser.add_argument("--plan", required=True, type=Path)
    parser.add_argument("--execution", required=True, type=Path)
    parser.add_argument("--output-directory", required=True, type=Path)
    return parser.parse_args()


def report_path_for(execution_directory: Path) -> Path:
    candidate = execution_directory / "execution-report.json"
    return candidate if candidate.exists() else execution_directory / "settle-report.json"


def load_execution(execution_directory: Path) -> tuple[dict[str, Any], np.ndarray]:
    """Accept either an assembly execution report or a gravity settle report.

    Both produce one exact-topology position set per source vertex against the
    same plan, so both wrap into the same immutable arrangement artifact.
    """
    report_path = report_path_for(execution_directory)
    report = json.loads(report_path.read_text(encoding="utf-8"))
    schema = report.get("schemaVersion")
    if schema == EXECUTION_SCHEMA:
        expected_claims = {"acceptedArrangement": False, "acceptedCloth": False}
    elif schema == SETTLE_SCHEMA:
        expected_claims = {"acceptedCloth": False, "calibratedFabric": False}
    else:
        raise ValueError(f"Unsupported libuipc report schema: {schema}")
    if report.get("claims") != expected_claims:
        raise ValueError("The libuipc report must not claim acceptance.")
    positions_entry = report["finalPositions"]
    positions_path = execution_directory / positions_entry["path"]
    if positions_path.stat().st_size != positions_entry["byteLength"]:
        raise ValueError("Execution positions byte length changed.")
    if sha256_file(positions_path) != positions_entry["sha256"]:
        raise ValueError("Execution positions hash changed.")
    positions = np.load(positions_path, allow_pickle=False)
    if positions.ndim != 2 or positions.shape[1] != 3:
        raise ValueError("Execution positions must be an N x 3 array.")
    return report, positions


def main() -> int:
    arguments = parse_arguments()
    bundle_directory = arguments.bundle.resolve(strict=True)
    plan_directory = arguments.plan.resolve(strict=True)
    execution_directory = arguments.execution.resolve(strict=True)
    output_directory = arguments.output_directory.resolve()
    if output_directory.exists():
        raise FileExistsError(
            f"Arrangement artifacts are immutable; output already exists: {output_directory}"
        )

    source_manifest = verify_bundle(bundle_directory)
    if source_manifest["schemaVersion"] != "patterna.revision-bundle/1.2":
        raise ValueError("The libuipc arrangement requires a source-only revision bundle 1.2.")
    if source_manifest["contract"]["garmentArchetype"] != SUPPORTED_ARCHETYPE:
        raise ValueError(
            "Unsupported garment archetype: "
            + source_manifest["contract"]["garmentArchetype"]
        )

    plan_manifest = json.loads(
        (plan_directory / "scene-plan-manifest.json").read_text(encoding="utf-8")
    )
    report, positions_meters = load_execution(execution_directory)
    if "sourceBundleId" not in report:
        # A settle report inherits its source identity from the arrangement it
        # continued; the plan pins the same bundle, which is checked below.
        report["sourceBundleId"] = plan_manifest["sourceBundleId"]
    if "scheduleSha256" not in report:
        report["scheduleSha256"] = report.get("recipeSha256")
    if "totalFrames" not in report:
        report["totalFrames"] = report.get("framesRun")
    if "phases" not in report:
        report["phases"] = [
            {
                "framesRun": report.get("framesRun"),
                "finalGroupSeparationsMeters": {
                    "gravitySettle": report.get("finalMaximumVertexMotionMeters", 0.0)
                },
            }
        ]
    if report["planId"] != plan_manifest["planId"]:
        raise ValueError("The execution report does not target the given plan.")
    if report["sourceBundleId"] != source_manifest["bundleId"]:
        raise ValueError("The execution report does not target the given source bundle.")
    if plan_manifest["sourceBundleId"] != source_manifest["bundleId"]:
        raise ValueError("The plan does not target the given source bundle.")

    mesh_path = role_path(bundle_directory, source_manifest, "panelMesh")
    panels_path = role_path(bundle_directory, source_manifest, "panels")
    seams_path = role_path(bundle_directory, source_manifest, "seams")
    panel_index_map_path = role_path(bundle_directory, source_manifest, "panelIndexMap")
    mesh = json.loads(mesh_path.read_text(encoding="utf-8"))
    if mesh.get("schemaVersion") != "patterna.garmentcode-pattern-mesh/1.0":
        raise ValueError("Unsupported exact panel-mesh schema.")
    panels = mesh.get("panels")
    seams = mesh.get("seams")
    if not isinstance(panels, list) or len(panels) != 14 or not isinstance(seams, list):
        raise ValueError("The supported archetype requires exactly 14 panels and authored seams.")

    execution_order = [entry["panelId"] for entry in report["panelOrder"]]
    execution_counts = {
        entry["panelId"]: entry["vertexCount"] for entry in report["panelOrder"]
    }
    expected_total = sum(execution_counts.values())
    if positions_meters.shape[0] != expected_total:
        raise ValueError("Execution position count differs from the declared panel order.")
    execution_offsets: dict[str, int] = {}
    offset = 0
    for panel_id in execution_order:
        execution_offsets[panel_id] = offset
        offset += execution_counts[panel_id]

    arranged: list[np.ndarray] = []
    offsets: list[int] = []
    panel_records: list[dict[str, Any]] = []
    output_offset = 0
    for panel in panels:
        panel_id = str(panel["panelId"])
        count = len(panel["vertices"])
        if execution_counts.get(panel_id) != count:
            raise ValueError(f"Execution vertex count changed for {panel_id}.")
        start = execution_offsets[panel_id]
        points_cm = positions_meters[start : start + count] * 100.0
        if not np.isfinite(points_cm).all():
            raise ValueError(f"Panel {panel_id} has non-finite arranged positions.")
        arranged.append(points_cm)
        offsets.append(output_offset)
        material = [
            [float(vertex["x"]), float(vertex["y"])] for vertex in panel["vertices"]
        ]
        panel_records.append(
            {
                "panelId": panel_id,
                "pieceId": panel["pieceId"],
                "sourcePanelName": panel["sourcePanelName"],
                "vertexOffset": output_offset,
                "vertexCount": count,
                "triangleCount": len(panel["triangles"]),
                "triangles": panel["triangles"],
                "edgeVertexIndices": panel["edgeVertexIndices"],
                "materialPositionsCm": material,
                "sourceMap": {
                    "vertexIndices": list(range(count)),
                    "triangleIndices": list(range(len(panel["triangles"]))),
                },
            }
        )
        output_offset += count

    constraints = build_constraints(panels, seams, seams_path, panel_index_map_path)
    positions = np.concatenate(arranged, axis=0)

    document = {
        "schemaVersion": ARRANGEMENT_SCHEMA,
        "sourceBundleId": source_manifest["bundleId"],
        "sourcePanelMeshSha256": sha256_file(mesh_path),
        "sourcePanelsSha256": sha256_file(panels_path),
        "sourceSeamsSha256": sha256_file(seams_path),
        "sourcePanelIndexMapSha256": sha256_file(panel_index_map_path),
        "workerSha256": sha256_file(Path(__file__).resolve()),
        "garmentArchetype": SUPPORTED_ARCHETYPE,
        "units": "cm",
        "claims": {"accepted": False},
        "method": {
            "engine": (
                "libuipc-gravity-settle"
                if report["schemaVersion"] == SETTLE_SCHEMA
                else "libuipc-progressive-contact-aware-assembly"
            ),
            "planId": plan_manifest["planId"],
            "scheduleSha256": report["scheduleSha256"],
            "executionReportSha256": sha256_file(report_path_for(execution_directory)),
            "executorSha256": report.get("executorSha256") or report.get("settlerSha256"),
            "sourceArrangementId": report.get("sourceArrangementId"),
            "reachedEquilibrium": report.get("reachedEquilibrium"),
            "runtime": report.get("runtime"),
            "totalFrames": report["totalFrames"],
            "phaseFrames": [phase["framesRun"] for phase in report["phases"]],
            "finalActiveSeamSeparationsMeters": report["phases"][-1].get(
                "finalGroupSeparationsMeters"
            ),
        },
        "panels": panel_records,
        "constraints": constraints,
    }

    output_directory.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(
        tempfile.mkdtemp(prefix=f".{output_directory.name}-", dir=output_directory.parent)
    )
    try:
        positions_path = temporary / "positions.npy"
        np.save(positions_path, positions, allow_pickle=False)
        document_path = temporary / "arrangement.json"
        document_path.write_text(
            json.dumps(document, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        identity = {
            "schemaVersion": MANIFEST_SCHEMA,
            "sourceBundleId": source_manifest["bundleId"],
            "claims": {"accepted": False},
            "files": [
                {
                    "path": "arrangement.json",
                    "byteLength": document_path.stat().st_size,
                    "sha256": sha256_file(document_path),
                },
                {
                    "path": "positions.npy",
                    "byteLength": positions_path.stat().st_size,
                    "sha256": sha256_file(positions_path),
                },
            ],
        }
        arrangement_id = hashlib.sha256(canonical_json(identity)).hexdigest()
        manifest = {**identity, "arrangementId": arrangement_id}
        (temporary / "arrangement-manifest.json").write_text(
            json.dumps(manifest, indent=2) + "\n",
            encoding="utf-8",
        )
        os.replace(temporary, output_directory)
    except BaseException:
        shutil.rmtree(temporary, ignore_errors=True)
        raise
    print(json.dumps({"arrangementId": arrangement_id, "vertexCount": int(positions.shape[0])}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
