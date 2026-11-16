#!/usr/bin/env python3
"""Verify one canonical sewn seed without trusting its acceptance claims."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
import re
from typing import Any


SEED_SCHEMA = "patterna.canonical-sewn-seed/1.0"
MAP_SCHEMA = "patterna.sewn-source-map/1.0"
TURN_TABLE_SCHEMA = "patterna.product-turntable/1.0"
RESULT_SCHEMA = "patterna.canonical-sewn-seed-verification/1.0"
SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$", re.IGNORECASE)
VIEWS = ("front", "front-oblique", "left", "back", "back-oblique", "right")
REQUIRED_CLAIMS = (
    "seedAccepted",
    "sourceIdentityPreserved",
    "reversibleMapAccepted",
    "calibratedMaterial",
    "visualQualityAccepted",
)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _mapping(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _safe_file(
    root: Path,
    declaration: Any,
    label: str,
    reasons: list[str],
) -> Path | None:
    declared = _mapping(declaration)
    relative = declared.get("path")
    expected = declared.get("sha256")
    if not isinstance(relative, str) or not relative:
        reasons.append(f"files.{label}.path must be a nonempty relative path.")
        return None
    if not isinstance(expected, str) or not SHA256_PATTERN.fullmatch(expected):
        reasons.append(f"files.{label}.sha256 must be a SHA-256 value.")
        return None
    try:
        path = (root / relative).resolve(strict=True)
    except (FileNotFoundError, OSError):
        reasons.append(f"files.{label} is missing.")
        return None
    if root != path.parent and root not in path.parents:
        reasons.append(f"files.{label} escapes the seed directory.")
        return None
    if sha256(path) != expected:
        reasons.append(f"files.{label} hash does not match its declaration.")
    return path


def _verify_source_map(path: Path | None, reasons: list[str]) -> None:
    if path is None:
        return
    try:
        source_map = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        reasons.append("sourceMap must contain valid JSON.")
        return
    if not isinstance(source_map, dict):
        reasons.append("sourceMap must contain a JSON object.")
        return
    if source_map.get("schemaVersion") != MAP_SCHEMA:
        reasons.append(f"sourceMap schemaVersion must be {MAP_SCHEMA}.")

    source_count = source_map.get("sourceVertexCount")
    solver_count = source_map.get("solverVertexCount")
    forward = source_map.get("sourceToSolver")
    inverse = source_map.get("solverToSource")
    valid_counts = (
        isinstance(source_count, int)
        and not isinstance(source_count, bool)
        and source_count > 0
        and isinstance(solver_count, int)
        and not isinstance(solver_count, bool)
        and solver_count > 0
    )
    if not valid_counts:
        reasons.append("sourceMap vertex counts must be positive integers.")
        return
    if not isinstance(forward, list) or len(forward) != source_count:
        reasons.append("sourceToSolver must map every source vertex exactly once.")
        return
    if not isinstance(inverse, list) or len(inverse) != solver_count:
        reasons.append("solverToSource must name every solver vertex exactly once.")
        return

    if any(
        not isinstance(target, int)
        or isinstance(target, bool)
        or target < 0
        or target >= solver_count
        for target in forward
    ):
        reasons.append("sourceToSolver contains an invalid solver vertex index.")
        return

    inverse_members: list[int] = []
    inverse_valid = True
    for solver_vertex, members in enumerate(inverse):
        if not isinstance(members, list) or not members:
            inverse_valid = False
            continue
        for source_vertex in members:
            if (
                not isinstance(source_vertex, int)
                or isinstance(source_vertex, bool)
                or source_vertex < 0
                or source_vertex >= source_count
            ):
                inverse_valid = False
                continue
            inverse_members.append(source_vertex)
            if forward[source_vertex] != solver_vertex:
                inverse_valid = False
    if not inverse_valid or sorted(inverse_members) != list(range(source_count)):
        reasons.append(
            "solverToSource must be the exact complete inverse membership of sourceToSolver."
        )


def _verify_visual_review(root: Path, path: Path | None, reasons: list[str]) -> None:
    if path is None:
        return
    try:
        review = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        reasons.append("visual review must contain valid JSON.")
        return
    if not isinstance(review, dict):
        reasons.append("visual review must contain a JSON object.")
        return
    if review.get("schema_version") != TURN_TABLE_SCHEMA:
        reasons.append(f"visual review schema_version must be {TURN_TABLE_SCHEMA}.")

    quality = _mapping(review.get("visual_quality"))
    if quality.get("accepted") is not True:
        reasons.append("visual review must be accepted.")
    if quality.get("review_required") is not False:
        reasons.append("visual review must not remain pending.")
    if quality.get("issues") != []:
        reasons.append("visual review issues must be empty.")

    renders = _mapping(review.get("renders"))
    reviewed = _mapping(quality.get("reviewed_render_sha256"))
    for view in VIEWS:
        render = _mapping(renders.get(view))
        relative = render.get("path")
        expected = render.get("sha256")
        if not isinstance(relative, str) or not isinstance(expected, str):
            reasons.append(f"{view} render identity is missing from the visual review.")
            continue
        try:
            render_path = (root / relative).resolve(strict=True)
        except (FileNotFoundError, OSError):
            reasons.append(f"{view} render is missing.")
            continue
        if root != render_path.parent and root not in render_path.parents:
            reasons.append(f"{view} render escapes the seed directory.")
            continue
        actual = sha256(render_path)
        if actual != expected or reviewed.get(view) != expected:
            reasons.append(f"{view} render hash is not bound to the accepted review.")


def _finite_number(value: Any) -> bool:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(float(value))
    )


def _verify_metrics(metrics: dict[str, Any], reasons: list[str]) -> None:
    for name in ("bodyCollisions", "selfIntersections", "invertedTriangles"):
        if metrics.get(name) != 0 or isinstance(metrics.get(name), bool):
            reasons.append(f"metrics.{name} must be zero.")

    limits = {
        "maximumSeamSeparationCm": 0.2,
        "p95MaterialEdgeStrain": 0.25,
        "maximumMaterialEdgeStrain": 2.0,
    }
    for name, limit in limits.items():
        value = metrics.get(name)
        if not _finite_number(value) or float(value) < 0.0 or float(value) > limit:
            reasons.append(f"metrics.{name} must be finite and at most {limit}.")

    for name in (
        "staticEquilibriumReached",
        "anatomicalRegionGatesAccepted",
        "symmetryAndFoldFrequencyAccepted",
    ):
        if metrics.get(name) is not True:
            reasons.append(f"metrics.{name} must be true.")


def verify_canonical_seed(manifest_path: Path) -> dict[str, Any]:
    """Verify seed files, source mapping, physics gates, and exact visual review."""
    manifest_path = manifest_path.resolve(strict=True)
    root = manifest_path.parent
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if not isinstance(manifest, dict):
        raise ValueError("The canonical seed manifest must contain a JSON object.")
    reasons: list[str] = []

    if manifest.get("schemaVersion") != SEED_SCHEMA:
        reasons.append(f"schemaVersion must be {SEED_SCHEMA}.")
    claims = _mapping(manifest.get("claims"))
    for claim in REQUIRED_CLAIMS:
        if claims.get(claim) is not True:
            reasons.append(f"claims.{claim} must be true.")
    if manifest.get("openGates") != []:
        reasons.append("openGates must be an empty list.")

    source = _mapping(manifest.get("source"))
    for name in ("revisionBundleId", "patternSha256", "bodyColliderSha256"):
        value = source.get(name)
        if not isinstance(value, str) or not SHA256_PATTERN.fullmatch(value):
            reasons.append(f"source.{name} must be a SHA-256 value.")
    for name in ("garmentArchetype", "poseFamily"):
        if not isinstance(source.get(name), str) or not source[name].strip():
            reasons.append(f"source.{name} must be a nonempty string.")

    files = _mapping(manifest.get("files"))
    _safe_file(root, files.get("solverMesh"), "solverMesh", reasons)
    source_map_path = _safe_file(root, files.get("sourceMap"), "sourceMap", reasons)
    visual_review_path = _safe_file(
        root, files.get("visualReview"), "visualReview", reasons
    )
    _verify_source_map(source_map_path, reasons)
    _verify_visual_review(root, visual_review_path, reasons)

    workflow = _mapping(manifest.get("workflow"))
    if workflow.get("manualEditsAfterPublication") is not False:
        reasons.append("workflow.manualEditsAfterPublication must be false.")
    _verify_metrics(_mapping(manifest.get("metrics")), reasons)

    return {
        "schemaVersion": RESULT_SCHEMA,
        "accepted": not reasons,
        "manifestSha256": sha256(manifest_path),
        "reasons": reasons,
    }


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--report", type=Path)
    return parser.parse_args()


def main() -> int:
    arguments = parse_arguments()
    result = verify_canonical_seed(arguments.manifest)
    rendered = json.dumps(result, indent=2) + "\n"
    if arguments.report is not None:
        arguments.report.parent.mkdir(parents=True, exist_ok=True)
        arguments.report.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    return 0 if result["accepted"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
