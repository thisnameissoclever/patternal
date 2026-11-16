#!/usr/bin/env python3
"""Prepare a no-install libuipc contact-aware arrangement scene plan."""

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
import warp as wp

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from tools.exact_triangle_arrangement import (
    SUPPORTED_ARCHETYPE,
    build_constraints,
    role_path,
    source_placement_points,
)
from tools.libuipc_arrangement_contract import MANIFEST_SCHEMA, PLAN_SCHEMA
from tools.prefit_newton_style3d import find_intersection_edges
from tools.revision_bundle import canonical_json, sha256_file, verify_bundle
from tools.verify_exact_triangle_arrangement import read_obj


def write_obj(path: Path, vertices_m: np.ndarray, faces: np.ndarray) -> None:
    lines = [
        f"v {point[0]:.12g} {point[1]:.12g} {point[2]:.12g}"
        for point in vertices_m
    ]
    lines.extend(
        "f " + " ".join(str(int(index) + 1) for index in face)
        for face in faces
    )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def panel_pair_key(first: str, second: str) -> str:
    return "--".join(sorted((first, second)))


BODY_FRAME_STAGED_PANELS = {
    "left-sleeve-b-panel",
    "left-sleeve-f-panel",
    "right-sleeve-b-panel",
    "right-sleeve-f-panel",
    "sl-left-cuff-b-panel",
    "sl-left-cuff-f-panel",
    "sl-right-cuff-b-panel",
    "sl-right-cuff-f-panel",
}
ARM_FIT_BAND_CM = (26.0, 52.0)
ARM_BASE_STATION_CM = 24.5
SLEEVE_NORMAL_OFFSET_CM = 10.0
CUFF_STATION_BEYOND_SLEEVE_CM = 2.5
# Each mirrored collar half is authored coincident with its opposite at centre
# front and centre back, well inside any usable contact envelope. Contact
# between them therefore had to be disabled, and with a correctly stiff bending
# coefficient the two halves then crossed each other. Staging them apart lets
# contact stay enabled instead.
#
# The separation has to clear the contact envelope, not merely be non-zero: the
# solver's own surface-distance check runs before any contact policy applies
# and refuses a scene whose surfaces start closer than the envelope. At 0.05 cm
# the halves still began 0.075 cm apart against a 0.2 cm envelope, which passed
# only while the panels happened to be small enough to sit elsewhere. Half a
# millimetre past the envelope is a stable margin, and the seams close from it
# because their rest length is zero.
MIRROR_SEPARATION_CM = 0.25
# The torso panels were authored at a fixed depth that suited one body. A
# different body, or the same body in a different stance, puts its own surface
# somewhere else, so the front and back panels stage a declared distance beyond
# whatever this collider actually occupies across the panel's own height band.
TORSO_STANDOFF_CM = 8.0
DEPTH_STAGED_PANELS = {
    "front-torso-panel": 1.0,
    "back-torso-panel": -1.0,
    "left-collar-front-panel": 1.0,
    "right-collar-front-panel": 1.0,
    "left-collar-back-panel": -1.0,
    "right-collar-back-panel": -1.0,
}
# Anatomical left occupies positive x in this bundle's placement, so each
# half moves further onto its own side of centre front.
MIRROR_SEPARATED_PANELS = {
    "left-collar-front-panel": 1.0,
    "right-collar-front-panel": -1.0,
    "left-collar-back-panel": 1.0,
    "right-collar-back-panel": -1.0,
}


def fit_arm_axis(body_positions_cm: np.ndarray, side: str) -> dict[str, Any]:
    """Least-squares arm axis through collider section centroids.

    The authored bundle placement stages the sleeve panels along an arms-down
    direction about 54 degrees off this collider's near-horizontal arms, which
    put 52 seam-constraint chords through the arm before the first frame. The
    staged sleeve frame therefore derives from the collider itself.
    """
    sign = 1.0 if side == "left" else -1.0
    stations = np.arange(ARM_FIT_BAND_CM[0], ARM_FIT_BAND_CM[1] + 0.5, 2.0)
    centroids = []
    for station in stations:
        band = np.abs(sign * body_positions_cm[:, 0] - station) <= 1.0
        selected = body_positions_cm[band & (sign * body_positions_cm[:, 0] > 0.0)]
        if len(selected) >= 8:
            centroids.append(selected.mean(axis=0))
    if len(centroids) < 5:
        raise ValueError(f"The collider has too few {side}-arm sections to fit an axis.")
    points = np.asarray(centroids)
    xs = points[:, 0]
    slope_y, intercept_y = np.polyfit(xs, points[:, 1], 1)
    slope_z, intercept_z = np.polyfit(xs, points[:, 2], 1)
    direction = np.array([sign, slope_y * sign, slope_z * sign])
    direction /= np.linalg.norm(direction)
    base_x = sign * ARM_BASE_STATION_CM
    base = np.array(
        [base_x, slope_y * base_x + intercept_y, slope_z * base_x + intercept_z]
    )
    return {
        "side": side,
        "basePointCm": [float(value) for value in base],
        "outwardUnit": [float(value) for value in direction],
        "slopeY": float(slope_y),
        "interceptY": float(intercept_y),
        "slopeZ": float(slope_z),
        "interceptZ": float(intercept_z),
        "sectionCount": len(centroids),
    }


def body_frame_sleeve_points(
    material_cm: np.ndarray,
    axis: dict[str, Any],
    *,
    panel_id: str,
) -> np.ndarray:
    """Stage a sleeve half or cuff strip in the collider's arm frame."""
    side = axis["side"]
    outward = np.asarray(axis["outwardUnit"], dtype=np.float64)
    base = np.asarray(axis["basePointCm"], dtype=np.float64)
    world_up = np.array([0.0, 1.0, 0.0])
    around = world_up - np.dot(world_up, outward) * outward
    around /= np.linalg.norm(around)
    normal = np.cross(outward, around)
    normal /= np.linalg.norm(normal)
    if normal[2] < 0.0:
        normal = -normal
    front_half = panel_id.endswith("-f-panel")
    offset_sign = 1.0 if front_half else -1.0
    length_sign = 1.0 if side == "left" else -1.0

    material_x = material_cm[:, 0]
    material_y = material_cm[:, 2]
    is_cuff = panel_id.startswith("sl-")
    if is_cuff:
        length_axis = around
        around_axis = outward * length_sign
        origin_material = np.array(
            [
                0.5 * (material_x.min() + material_x.max()),
                0.0,
                0.5 * (material_y.min() + material_y.max()),
            ]
        )
        sleeve_length = axis["sleeveLengthCm"]
        origin_world = base + (sleeve_length + CUFF_STATION_BEYOND_SLEEVE_CM) * outward
    else:
        length_axis = outward * length_sign
        around_axis = around
        shoulder_x = material_x.min() if side == "left" else material_x.max()
        origin_material = np.array(
            [shoulder_x, 0.0, 0.5 * (material_y.min() + material_y.max())]
        )
        origin_world = base
    rotation = np.column_stack(
        [length_axis, np.cross(around_axis, length_axis), around_axis]
    )
    local = (material_cm - origin_material[None, :]) @ rotation.T
    return origin_world[None, :] + local + offset_sign * SLEEVE_NORMAL_OFFSET_CM * normal[None, :]


def torso_depth_translation(
    points_cm: np.ndarray,
    body_positions_cm: np.ndarray,
    direction: float,
) -> float:
    """Depth shift that clears this body across the panel's height band."""
    low = float(points_cm[:, 1].min())
    high = float(points_cm[:, 1].max())
    band = body_positions_cm[
        (body_positions_cm[:, 1] >= low) & (body_positions_cm[:, 1] <= high)
    ]
    if len(band) == 0:
        return 0.0
    if direction > 0.0:
        target = float(band[:, 2].max()) + TORSO_STANDOFF_CM
        return target - float(points_cm[:, 2].max())
    target = float(band[:, 2].min()) - TORSO_STANDOFF_CM
    return target - float(points_cm[:, 2].min())


def count_blocked_chords(
    positions_cm: np.ndarray,
    constraint_pairs: list[tuple[int, int]],
    body_positions_cm: np.ndarray,
    body_faces: np.ndarray,
) -> int:
    """Count seam-constraint chords that intersect the collider."""
    t0 = body_positions_cm[body_faces[:, 0]]
    edge1 = body_positions_cm[body_faces[:, 1]] - t0
    edge2 = body_positions_cm[body_faces[:, 2]] - t0
    lows = np.minimum(np.minimum(t0, t0 + edge1), t0 + edge2)
    highs = np.maximum(np.maximum(t0, t0 + edge1), t0 + edge2)
    blocked = 0
    for index_a, index_b in constraint_pairs:
        start = positions_cm[index_a]
        end = positions_cm[index_b]
        box_low = np.minimum(start, end) - 1.0e-6
        box_high = np.maximum(start, end) + 1.0e-6
        mask = np.all((highs >= box_low) & (lows <= box_high), axis=1)
        if not mask.any():
            continue
        candidates = np.flatnonzero(mask)
        origin = t0[candidates]
        e1 = edge1[candidates]
        e2 = edge2[candidates]
        direction = end - start
        p_vector = np.cross(direction, e2)
        determinant = np.einsum("ij,ij->i", e1, p_vector)
        valid = np.abs(determinant) > 1.0e-15
        inverse = np.zeros_like(determinant)
        inverse[valid] = 1.0 / determinant[valid]
        t_vector = start - origin
        u = np.einsum("ij,ij->i", t_vector, p_vector) * inverse
        q_vector = np.cross(t_vector, e1)
        v = np.einsum(
            "ij,ij->i", np.broadcast_to(direction, origin.shape), q_vector
        ) * inverse
        t = np.einsum("ij,ij->i", e2, q_vector) * inverse
        hits = (
            valid
            & (u >= -1.0e-9)
            & (v >= -1.0e-9)
            & (u + v <= 1.0 + 1.0e-9)
            & (t >= 1.0e-9)
            & (t <= 1.0 - 1.0e-9)
        )
        if hits.any():
            blocked += 1
    return blocked


def build_plan(bundle_directory: Path, output_directory: Path, device: str) -> dict[str, Any]:
    bundle_directory = bundle_directory.resolve(strict=True)
    output_directory = output_directory.resolve()
    if output_directory.exists():
        raise FileExistsError(f"Scene plans are immutable: {output_directory}")
    source_manifest = verify_bundle(bundle_directory)
    if source_manifest["schemaVersion"] != "patterna.revision-bundle/1.2":
        raise ValueError("The libuipc arrangement plan requires revision bundle 1.2.")
    if source_manifest["contract"]["garmentArchetype"] != SUPPORTED_ARCHETYPE:
        raise ValueError("The libuipc arrangement plan supports only the frozen shirt archetype.")

    mesh_path = role_path(bundle_directory, source_manifest, "panelMesh")
    panels_path = role_path(bundle_directory, source_manifest, "panels")
    seams_path = role_path(bundle_directory, source_manifest, "seams")
    panel_index_map_path = role_path(bundle_directory, source_manifest, "panelIndexMap")
    collider_path = role_path(bundle_directory, source_manifest, "collider")
    fabric_path = role_path(bundle_directory, source_manifest, "fabric")
    mesh = json.loads(mesh_path.read_text(encoding="utf-8"))
    source = json.loads(panels_path.read_text(encoding="utf-8"))
    panels = mesh.get("panels")
    seams = mesh.get("seams")
    placements = source.get("pattern", {}).get("panels")
    if not isinstance(panels, list) or len(panels) != 14:
        raise ValueError("The scene plan requires exactly 14 exact source panels.")
    if not isinstance(seams, list) or not isinstance(placements, dict):
        raise ValueError("The scene plan requires authored seams and placements.")
    constraints = build_constraints(
        panels,
        seams,
        seams_path,
        panel_index_map_path,
    )

    body_positions_for_staging, _body_faces_for_staging = read_obj(collider_path)
    arm_axes = {
        side: fit_arm_axis(body_positions_for_staging, side)
        for side in ("left", "right")
    }
    for side in ("left", "right"):
        sleeve_panel = next(
            panel for panel in panels
            if str(panel["panelId"]) == f"{side}-sleeve-b-panel"
        )
        xs = [float(vertex["x"]) for vertex in sleeve_panel["vertices"]]
        arm_axes[side]["sleeveLengthCm"] = float(max(xs) - min(xs))

    panel_positions_cm: list[np.ndarray] = []
    panel_faces: list[np.ndarray] = []
    offsets: dict[str, int] = {}
    offset = 0
    for panel in panels:
        panel_id = str(panel["panelId"])
        placement = placements.get(panel["sourcePanelName"])
        if not isinstance(placement, dict):
            raise ValueError(f"No authored placement exists for {panel['sourcePanelName']}.")
        if panel_id in BODY_FRAME_STAGED_PANELS:
            material_cm = np.asarray(
                [
                    [float(vertex["x"]), 0.0, float(vertex["y"])]
                    for vertex in panel["vertices"]
                ],
                dtype=np.float64,
            )
            side = "left" if "left" in panel_id else "right"
            points = body_frame_sleeve_points(
                material_cm, arm_axes[side], panel_id=panel_id
            )
        else:
            points = source_placement_points(
                panel["vertices"],
                placement.get("translation", []),
                placement.get("rotation", []),
            )
            if panel_id in MIRROR_SEPARATED_PANELS:
                points = points.copy()
                points[:, 0] += MIRROR_SEPARATED_PANELS[panel_id] * MIRROR_SEPARATION_CM
            if panel_id in DEPTH_STAGED_PANELS:
                points = points.copy()
                points[:, 2] += torso_depth_translation(
                    points,
                    body_positions_for_staging,
                    DEPTH_STAGED_PANELS[panel_id],
                )
        faces = np.asarray(panel["triangles"], dtype=np.int32)
        offsets[panel_id] = offset
        offset += len(points)
        panel_positions_cm.append(points)
        panel_faces.append(faces)
    positions_cm = np.concatenate(panel_positions_cm, axis=0)
    faces_global = np.concatenate(
        [faces + offsets[str(panel["panelId"])] for panel, faces in zip(panels, panel_faces)],
        axis=0,
    )
    body_positions_cm, body_faces = read_obj(collider_path)
    wp.init()
    body_edges, self_edges = find_intersection_edges(
        positions_cm * 0.01,
        faces_global,
        body_positions_cm * 0.01,
        body_faces,
        device,
    )
    triangle_cross = np.cross(
        positions_cm[faces_global[:, 1]] - positions_cm[faces_global[:, 0]],
        positions_cm[faces_global[:, 2]] - positions_cm[faces_global[:, 0]],
    )
    triangle_areas = np.linalg.norm(triangle_cross, axis=1) * 0.5

    constraints_by_pair: dict[str, list[dict[str, Any]]] = {}
    seam_gaps: list[float] = []
    constraint_index_pairs: list[tuple[int, int]] = []
    for constraint in constraints:
        side_a = constraint["sideA"]
        side_b = constraint["sideB"]
        index_a = offsets[str(side_a["panelId"])] + int(side_a["vertexIndex"])
        index_b = offsets[str(side_b["panelId"])] + int(side_b["vertexIndex"])
        constraint_index_pairs.append((index_a, index_b))
        seam_gaps.append(float(np.linalg.norm(positions_cm[index_a] - positions_cm[index_b])))
        key = panel_pair_key(str(side_a["panelId"]), str(side_b["panelId"]))
        constraints_by_pair.setdefault(key, []).append(constraint)
    blocked_chords = count_blocked_chords(
        positions_cm, constraint_index_pairs, body_positions_cm, body_faces
    )

    staging_gates = [
        {
            "name": "clothBodyIntersections",
            "passed": len(body_edges) == 0,
            "actual": len(body_edges),
            "required": "0",
        },
        {
            "name": "clothSelfIntersections",
            "passed": len(self_edges) == 0,
            "actual": len(self_edges),
            "required": "0",
        },
        {
            "name": "minimumTriangleAreaCm2",
            "passed": float(np.min(triangle_areas)) >= 0.001,
            "actual": float(np.min(triangle_areas)),
            "required": ">= 0.001",
        },
        {
            "name": "finitePositions",
            "passed": bool(np.isfinite(positions_cm).all()),
            "actual": bool(np.isfinite(positions_cm).all()),
            "required": "true",
        },
        {
            "name": "constraintChordClearance",
            "passed": blocked_chords == 0,
            "actual": blocked_chords,
            "required": "0",
        },
    ]
    staging_accepted = all(item["passed"] for item in staging_gates)
    if not staging_accepted:
        failed = [item["name"] for item in staging_gates if not item["passed"]]
        raise ValueError(
            "The staged arrangement fails its preflight gates and the plan"
            f" refuses to build: {', '.join(failed)}"
        )

    output_directory.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(
        tempfile.mkdtemp(prefix=f".{output_directory.name}-", dir=output_directory.parent)
    )
    try:
        panels_directory = temporary / "panels"
        panels_directory.mkdir()
        plan_panels: list[dict[str, Any]] = []
        for panel, initial_cm, faces in zip(panels, panel_positions_cm, panel_faces):
            panel_id = str(panel["panelId"])
            initial_name = f"panels/{panel_id}.initial.obj"
            rest_name = f"panels/{panel_id}.rest.obj"
            material_cm = np.asarray(
                [
                    [float(vertex["x"]), 0.0, float(vertex["y"])]
                    for vertex in panel["vertices"]
                ],
                dtype=np.float64,
            )
            write_obj(temporary / initial_name, initial_cm * 0.01, faces)
            write_obj(temporary / rest_name, material_cm * 0.01, faces)
            plan_panels.append(
                {
                    "panelId": panel_id,
                    "pieceId": panel["pieceId"],
                    "sourcePanelName": panel["sourcePanelName"],
                    "initialMesh": initial_name,
                    "restMesh": rest_name,
                    "vertexCount": len(initial_cm),
                    "triangleCount": len(faces),
                    "sourceVertexIndices": list(range(len(initial_cm))),
                    "sourceTriangleIndices": list(range(len(faces))),
                }
            )
        collider_output = temporary / "collider.obj"
        shutil.copyfile(collider_path, collider_output)

        stitch_groups = []
        for key, group in sorted(constraints_by_pair.items()):
            first_panel, second_panel = key.split("--", 1)
            stitch_groups.append(
                {
                    "groupId": key,
                    "constitution": "SoftVertexStitch",
                    "geometrySlots": [first_panel, second_panel],
                    "constraintIds": [item["constraintId"] for item in group],
                    "vertexPairs": [
                        [
                            int(
                                item["sideA"]["vertexIndex"]
                                if item["sideA"]["panelId"] == first_panel
                                else item["sideB"]["vertexIndex"]
                            ),
                            int(
                                item["sideB"]["vertexIndex"]
                                if item["sideB"]["panelId"] == second_panel
                                else item["sideA"]["vertexIndex"]
                            ),
                        ]
                        for item in group
                    ],
                    "sourceSeams": sorted({item["seamId"] for item in group}),
                }
            )

        plan = {
            "schemaVersion": PLAN_SCHEMA,
            "sourceBundleId": source_manifest["bundleId"],
            "claims": {
                "acceptedArrangement": False,
                "acceptedCloth": False,
                "executionAuthorized": False,
            },
            "runtimeTarget": {
                "package": "pyuipc",
                "version": "0.0.25",
                "python": "3.12",
                "platform": "win_amd64",
                "backend": "cuda",
                "wheelSha256": "b636a64689e1f63e58cef177dce6edd6cea2d454d534234d1f953d5b8ad5b074",
                "licenseEvidence": "Apache-2.0 LICENSE in exact v0.0.25 source tag",
                "metadataConflict": "PyPI classifier says GPLv3 while project license field names LICENSE",
            },
            "mode": "zero-gravity-progressive-contact-aware-arrangement",
            "coordinateSystem": "right-handed Y-up meters",
            "scene": {
                "dtSeconds": 1.0 / 120.0,
                "gravityMetersPerSecondSquared": [0.0, 0.0, 0.0],
                "contact": {
                    "constitution": "ipc",
                    "dHatMeters": 0.002,
                    "frictionCoefficient": 0.35,
                },
                "newton": {"maximumIterations": 1024, "velocityTolerance": 0.05},
                "cloth": {
                    "stretchConstitution": "StrainLimitingBaraffWitkinShell",
                    "bendingConstitution": "DiscreteShellBending",
                    "assemblyOnlyCalibration": {
                        "stretchYoungsPa": 60000.0,
                        "shearYoungsPa": 600.0,
                        "poissonRatio": 0.49,
                        "massDensityKgPerM3": 200.0,
                        "thicknessMeters": 0.001,
                        "bendingStiffness": 0.01,
                        "source": "libuipc official cloth_stack sample",
                        "notProductFabricAcceptance": True,
                    },
                },
                "collider": {
                    "mesh": "collider.obj",
                    "mode": "static-contact-surface",
                    "sourceSha256": sha256_file(collider_path),
                },
                "panels": plan_panels,
                "stitchGroups": stitch_groups,
                "progressiveStitchPolicy": {
                    "schedule": "fixed-before-run",
                    "targetDistanceMeters": 0.0,
                    "maximumScheduleCount": 1,
                    "visualRetuningAllowed": False,
                },
            },
            "stagingPolicy": {
                "authoredPlacement": sorted(
                    str(panel["panelId"]) for panel in panels
                    if str(panel["panelId"]) not in BODY_FRAME_STAGED_PANELS
                ),
                "bodyFrameStaged": sorted(BODY_FRAME_STAGED_PANELS),
                "reason": (
                    "The authored bundle placement stages the sleeve halves"
                    " about 54 degrees off the collider's near-horizontal arm"
                    " axes, which left 52 seam-constraint chords passing"
                    " through the arm before the first solver step. Sleeve and"
                    " cuff panels therefore stage in a frame derived from the"
                    " collider's own fitted arm axes; every other panel keeps"
                    " its exact authored placement."
                ),
                "depthStagedPanels": DEPTH_STAGED_PANELS,
                "torsoStandoffCm": TORSO_STANDOFF_CM,
                "mirrorSeparatedPanels": MIRROR_SEPARATED_PANELS,
                "mirrorSeparationCm": MIRROR_SEPARATION_CM,
                "armAxes": arm_axes,
                "sleeveNormalOffsetCm": SLEEVE_NORMAL_OFFSET_CM,
                "cuffStationBeyondSleeveCm": CUFF_STATION_BEYOND_SLEEVE_CM,
                "armFitBandCm": list(ARM_FIT_BAND_CM),
                "armBaseStationCm": ARM_BASE_STATION_CM,
            },
            "sourceStaging": {
                "acceptedForArrangementEngine": staging_accepted,
                "gates": staging_gates,
                "maximumSeamSeparationCm": max(seam_gaps),
                "p95SeamSeparationCm": float(np.percentile(seam_gaps, 95.0)),
                "constraintCount": len(constraints),
            },
            "requiredOutput": {
                "positions": "one Y-up meter position per exact source vertex",
                "sourceMap": "identity panel-local vertex and triangle maps",
                "independentVerification": "patterna.arrangement-verification/1.0",
            },
        }
        plan_path = temporary / "scene-plan.json"
        plan_path.write_text(json.dumps(plan, indent=2) + "\n", encoding="utf-8")
        declared_files = sorted(
            path.relative_to(temporary).as_posix()
            for path in temporary.rglob("*")
            if path.is_file()
        )
        files = [
            {
                "path": relative,
                "byteLength": (temporary / relative).stat().st_size,
                "sha256": sha256_file(temporary / relative),
            }
            for relative in declared_files
        ]
        identity = {
            "schemaVersion": MANIFEST_SCHEMA,
            "sourceBundleId": source_manifest["bundleId"],
            "claims": {"executionAuthorized": False},
            "files": files,
        }
        manifest = {
            **identity,
            "planId": hashlib.sha256(canonical_json(identity)).hexdigest(),
        }
        (temporary / "scene-plan-manifest.json").write_text(
            json.dumps(manifest, indent=2) + "\n",
            encoding="utf-8",
        )
        os.replace(temporary, output_directory)
    except BaseException:
        shutil.rmtree(temporary, ignore_errors=True)
        raise
    return manifest


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle", required=True, type=Path)
    parser.add_argument("--output-directory", required=True, type=Path)
    parser.add_argument("--device", default="cuda:0")
    return parser.parse_args()


def main() -> int:
    arguments = parse_arguments()
    manifest = build_plan(arguments.bundle, arguments.output_directory, arguments.device)
    print(json.dumps(manifest, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
