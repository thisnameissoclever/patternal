#!/usr/bin/env python3
"""Verify an immutable no-install libuipc arrangement plan."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import sys
from typing import Any

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from tools.libuipc_arrangement_contract import MANIFEST_SCHEMA, PLAN_SCHEMA
from tools.revision_bundle import canonical_json, sha256_file, verify_bundle


MANIFEST_NAME = "scene-plan-manifest.json"
PLAN_NAME = "scene-plan.json"
EXPECTED_PACKAGE = "pyuipc"
EXPECTED_VERSION = "0.0.25"
EXPECTED_WHEEL_SHA256 = (
    "b636a64689e1f63e58cef177dce6edd6cea2d454d534234d1f953d5b8ad5b074"
)


def require_object(value: Any, name: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{name} must be an object.")
    return value


def require_list(value: Any, name: str) -> list[Any]:
    if not isinstance(value, list):
        raise ValueError(f"{name} must be an array.")
    return value


def safe_relative_path(raw_path: Any) -> PurePosixPath:
    if not isinstance(raw_path, str) or not raw_path:
        raise ValueError("Every declared file path must be a non-empty string.")
    path = PurePosixPath(raw_path)
    if path.is_absolute() or ".." in path.parts or "\\" in raw_path:
        raise ValueError(f"Unsafe declared file path: {raw_path}")
    return path


def count_obj(path: Path) -> tuple[int, int]:
    vertices = 0
    triangles = 0
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith("v "):
            vertices += 1
        elif line.startswith("f "):
            fields = line.split()
            if len(fields) != 4:
                raise ValueError(f"Only triangular OBJ faces are allowed: {path}")
            triangles += 1
    return vertices, triangles


def verify_plan(
    plan_directory: Path,
    source_bundle_directory: Path | None = None,
) -> dict[str, Any]:
    root = plan_directory.resolve(strict=True)
    if not root.is_dir():
        raise ValueError(f"Plan path is not a directory: {root}")
    manifest_path = root / MANIFEST_NAME
    plan_path = root / PLAN_NAME
    manifest = require_object(
        json.loads(manifest_path.read_text(encoding="utf-8")), "manifest"
    )
    if manifest.get("schemaVersion") != MANIFEST_SCHEMA:
        raise ValueError("Unsupported libuipc arrangement plan manifest schema.")
    claims = require_object(manifest.get("claims"), "manifest claims")
    if claims != {"executionAuthorized": False}:
        raise ValueError("A prepared plan must not authorize execution.")

    declared_entries = require_list(manifest.get("files"), "manifest files")
    declared_paths: set[str] = set()
    for entry_value in declared_entries:
        entry = require_object(entry_value, "manifest file entry")
        relative = safe_relative_path(entry.get("path"))
        relative_text = relative.as_posix()
        if relative_text in declared_paths:
            raise ValueError(f"Duplicate declared file: {relative_text}")
        declared_paths.add(relative_text)
        file_path = root.joinpath(*relative.parts)
        if file_path.is_symlink() or not file_path.is_file():
            raise ValueError(f"Declared file is missing or is a symlink: {relative_text}")
        if file_path.stat().st_size != entry.get("byteLength"):
            raise ValueError(f"Declared file size changed: {relative_text}")
        if sha256_file(file_path) != entry.get("sha256"):
            raise ValueError(f"Declared file hash changed: {relative_text}")

    actual_paths = {
        path.relative_to(root).as_posix()
        for path in root.rglob("*")
        if path.is_file() and path.name != MANIFEST_NAME
    }
    if actual_paths != declared_paths:
        raise ValueError("The immutable plan file set changed.")
    if PLAN_NAME not in declared_paths:
        raise ValueError("The plan manifest does not declare scene-plan.json.")

    identity = {
        "schemaVersion": manifest["schemaVersion"],
        "sourceBundleId": manifest.get("sourceBundleId"),
        "claims": claims,
        "files": declared_entries,
    }
    expected_plan_id = hashlib.sha256(canonical_json(identity)).hexdigest()
    if manifest.get("planId") != expected_plan_id:
        raise ValueError("The plan identity does not match its manifest.")

    plan = require_object(json.loads(plan_path.read_text(encoding="utf-8")), "plan")
    if plan.get("schemaVersion") != PLAN_SCHEMA:
        raise ValueError("Unsupported libuipc arrangement plan schema.")
    if plan.get("sourceBundleId") != manifest.get("sourceBundleId"):
        raise ValueError("The plan and manifest name different source bundles.")
    if require_object(plan.get("claims"), "plan claims") != {
        "acceptedArrangement": False,
        "acceptedCloth": False,
        "executionAuthorized": False,
    }:
        raise ValueError("A prepared plan must begin with every product claim rejected.")
    runtime = require_object(plan.get("runtimeTarget"), "runtime target")
    if (
        runtime.get("package") != EXPECTED_PACKAGE
        or runtime.get("version") != EXPECTED_VERSION
        or runtime.get("wheelSha256") != EXPECTED_WHEEL_SHA256
    ):
        raise ValueError("The runtime target is not the reviewed pyuipc wheel.")
    staging = require_object(plan.get("sourceStaging"), "source staging")
    gates = require_list(staging.get("gates"), "source staging gates")
    if not staging.get("acceptedForArrangementEngine") or not gates:
        raise ValueError("The source staging was not accepted for the arrangement engine.")
    if not all(require_object(gate, "source staging gate").get("passed") is True for gate in gates):
        raise ValueError("At least one source staging gate failed.")

    scene = require_object(plan.get("scene"), "scene")
    panels = require_list(scene.get("panels"), "scene panels")
    stitch_groups = require_list(scene.get("stitchGroups"), "stitch groups")
    if len(panels) != 14:
        raise ValueError("The frozen shirt plan requires exactly 14 panels.")
    panel_by_id: dict[str, dict[str, Any]] = {}
    for panel_value in panels:
        panel = require_object(panel_value, "panel")
        panel_id = panel.get("panelId")
        if not isinstance(panel_id, str) or panel_id in panel_by_id:
            raise ValueError("Panel IDs must be unique non-empty strings.")
        vertex_count = panel.get("vertexCount")
        triangle_count = panel.get("triangleCount")
        if not isinstance(vertex_count, int) or vertex_count <= 0:
            raise ValueError(f"Invalid vertex count for panel {panel_id}.")
        if not isinstance(triangle_count, int) or triangle_count <= 0:
            raise ValueError(f"Invalid triangle count for panel {panel_id}.")
        if panel.get("sourceVertexIndices") != list(range(vertex_count)):
            raise ValueError(f"Panel {panel_id} does not preserve exact vertex identity.")
        if panel.get("sourceTriangleIndices") != list(range(triangle_count)):
            raise ValueError(f"Panel {panel_id} does not preserve exact triangle identity.")
        for mesh_key in ("initialMesh", "restMesh"):
            relative = safe_relative_path(panel.get(mesh_key))
            mesh_path = root.joinpath(*relative.parts)
            if relative.as_posix() not in declared_paths:
                raise ValueError(f"Panel {panel_id} references an undeclared mesh.")
            if count_obj(mesh_path) != (vertex_count, triangle_count):
                raise ValueError(f"Panel {panel_id} mesh counts changed: {mesh_key}")
        panel_by_id[panel_id] = panel

    stitch_pair_count = 0
    group_ids: set[str] = set()
    for group_value in stitch_groups:
        group = require_object(group_value, "stitch group")
        group_id = group.get("groupId")
        if not isinstance(group_id, str) or group_id in group_ids:
            raise ValueError("Stitch group IDs must be unique non-empty strings.")
        group_ids.add(group_id)
        slots = require_list(group.get("geometrySlots"), "stitch geometry slots")
        if len(slots) != 2 or any(slot not in panel_by_id for slot in slots):
            raise ValueError(f"Stitch group {group_id} names unknown geometry slots.")
        pairs = require_list(group.get("vertexPairs"), "stitch vertex pairs")
        constraint_ids = require_list(group.get("constraintIds"), "stitch constraint IDs")
        if len(pairs) != len(constraint_ids):
            raise ValueError(f"Stitch group {group_id} lost constraint identity.")
        for pair in pairs:
            if not isinstance(pair, list) or len(pair) != 2:
                raise ValueError(f"Stitch group {group_id} has an invalid vertex pair.")
            if any(not isinstance(index, int) for index in pair):
                raise ValueError(f"Stitch group {group_id} has a non-integer vertex index.")
            if not 0 <= pair[0] < panel_by_id[slots[0]]["vertexCount"]:
                raise ValueError(f"Stitch group {group_id} exceeds its first panel.")
            if not 0 <= pair[1] < panel_by_id[slots[1]]["vertexCount"]:
                raise ValueError(f"Stitch group {group_id} exceeds its second panel.")
        stitch_pair_count += len(pairs)
    if stitch_pair_count != staging.get("constraintCount"):
        raise ValueError("The staged seam constraint count does not match the scene.")

    source_manifest = None
    if source_bundle_directory is not None:
        source_manifest = verify_bundle(source_bundle_directory)
        if source_manifest.get("bundleId") != plan.get("sourceBundleId"):
            raise ValueError("The supplied source bundle does not match the plan.")

    return {
        "schemaVersion": "patterna.libuipc-arrangement-plan-verification/1.0",
        "accepted": True,
        "scope": "immutable-plan-integrity-only",
        "planId": expected_plan_id,
        "sourceBundleId": plan["sourceBundleId"],
        "panelCount": len(panels),
        "stitchGroupCount": len(stitch_groups),
        "stitchConstraintCount": stitch_pair_count,
        "executionAuthorized": False,
        "arrangementAccepted": False,
        "clothAccepted": False,
        "sourceBundleVerified": source_manifest is not None,
    }


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", required=True, type=Path)
    parser.add_argument("--source-bundle", type=Path)
    return parser.parse_args()


def main() -> int:
    arguments = parse_arguments()
    result = verify_plan(arguments.plan, arguments.source_bundle)
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
