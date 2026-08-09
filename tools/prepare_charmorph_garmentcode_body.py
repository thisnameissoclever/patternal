#!/usr/bin/env python3
"""Prepare one accepted CharMorph body for drafting and cloth collision."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys

import numpy as np
import trimesh
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
from charmorph_collision import build_collision_body
from fit_charmorph_profile import STATION_RATIOS
from mesh_torso_arcs import (
    back_fraction_from_across_measurements,
    lateral_extrema_depth_cm,
    measure_front_surface_ruler,
    measure_torso_arc_section,
)


REPO_ROOT = Path(__file__).resolve().parents[1]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--avatar-body", type=Path, required=True)
    parser.add_argument("--avatar-report", type=Path, required=True)
    parser.add_argument("--fit-report", type=Path, required=True)
    parser.add_argument("--profile", type=Path, required=True)
    parser.add_argument("--output-body", type=Path, required=True)
    return parser.parse_args()


def resolve(path: Path) -> Path:
    return path.resolve() if path.is_absolute() else (REPO_ROOT / path).resolve()


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_mesh(path: Path) -> trimesh.Trimesh:
    mesh = trimesh.load(path, process=False, maintain_order=True)
    if not isinstance(mesh, trimesh.Trimesh):
        raise TypeError(f"Expected one mesh in {path}, received {type(mesh).__name__}")
    return mesh


def blender_obj_to_garmentcode(vertices: np.ndarray) -> np.ndarray:
    """Convert exported OBJ X/right, Y/front, Z/up to GarmentCode Y/up."""
    converted = np.column_stack((vertices[:, 0], vertices[:, 2], vertices[:, 1]))
    converted[:, 1] -= float(converted[:, 1].min())
    return converted


def semantic_segmentation(vertices: np.ndarray) -> dict[str, list[int]]:
    """Separate limbs analytically without changing CharMorph's surface."""
    floor = float(vertices[:, 1].min())
    height = float(np.ptp(vertices[:, 1]))
    if height <= 0.0:
        raise ValueError("CharMorph collider has no positive height")
    result = {
        "body": [],
        "left_arm": [],
        "right_arm": [],
        "left_leg": [],
        "right_leg": [],
        "face_internal": [],
    }
    for index, vertex in enumerate(vertices):
        ratio = float((vertex[1] - floor) / height)
        x = float(vertex[0])
        # Preserve the pelvis, high hip, abdomen, and waist in the torso
        # segment. Compiler sections begin at 95 cm; a 0.58 split incorrectly
        # classified the lower abdomen of a 167 cm body as leg geometry.
        if ratio < 0.49:
            result["left_leg" if x < 0.0 else "right_leg"].append(index)
        elif ratio < 0.86 and abs(x) > (
            0.25 if ratio < 0.70 else 0.17 if ratio < 0.77 else 0.22
        ):
            result["left_arm" if x < 0.0 else "right_arm"].append(index)
        else:
            result["body"].append(index)
    return result


def station_heights_cm(
    mesh: trimesh.Trimesh,
    bust_apex_height_ratio: float,
) -> dict[str, float]:
    height_cm = float(np.ptp(mesh.vertices[:, 1]) * 100.0)
    if not 0.69 <= bust_apex_height_ratio <= 0.77:
        raise ValueError("CharMorph bust apex height ratio is outside the anatomical domain")
    return {
        "hip": STATION_RATIOS["hip"] * height_cm,
        "abdomen": STATION_RATIOS["abdomen"] * height_cm,
        "waist": STATION_RATIOS["waist"] * height_cm,
        "underbust": STATION_RATIOS["underbust"] * height_cm,
        "bust": bust_apex_height_ratio * height_cm,
        "upperTorsoCircuit": 0.740 * height_cm,
        "underarmCircuit": 0.754 * height_cm,
        "highBustTape": STATION_RATIOS["high_chest"] * height_cm,
    }


def averaged_measurement(measurements: dict[str, object], *names: str) -> float:
    values = [float(measurements[name]) for name in names if name in measurements]
    if not values or not np.isfinite(values).all() or min(values) <= 0.0:
        raise ValueError("Missing or invalid measurement: " + ", ".join(names))
    return float(np.mean(values))


def drafting_body(
    collision_body: trimesh.Trimesh,
    profile: dict[str, object],
    bust_apex_height_ratio: float,
) -> tuple[dict[str, float], dict[str, object]]:
    source_body = profile.get("body")
    measurements = profile.get("measurements")
    if not isinstance(source_body, dict) or not isinstance(measurements, dict):
        raise ValueError("Avatar profile must contain body and measurements objects")
    body = {str(key): float(value) for key, value in source_body.items()}
    stations = station_heights_cm(collision_body, bust_apex_height_ratio)
    sections = {
        name: measure_torso_arc_section(collision_body, height)
        for name, height in stations.items()
        if name != "highBustTape"
    }
    high_bust_back_fraction = back_fraction_from_across_measurements(
        float(measurements["acrossFront"]),
        float(measurements["acrossBack"]),
    )
    bust_side_seam_depth_cm = float(np.mean([
        lateral_extrema_depth_cm(collision_body, stations["underbust"]),
        lateral_extrema_depth_cm(collision_body, stations["upperTorsoCircuit"]),
    ]))
    sections["bust"] = measure_torso_arc_section(
        collision_body,
        stations["bust"],
        side_seam_depth_cm=bust_side_seam_depth_cm,
    )
    body["high_bust"] = float(measurements["highChestCirc"])
    body["armscye_circumference"] = averaged_measurement(
        measurements,
        "armscyeCircL",
        "armscyeCircR",
    )
    body["patterna_requested_armhole_depth"] = averaged_measurement(
        measurements,
        "armholeDepthL",
        "armholeDepthR",
    )
    body["patterna_armscye_is_estimated"] = 1.0
    body["patterna_armhole_depth_is_estimated"] = 1.0
    body["back_width"] = float(body["bust"]) * sections["bust"].back_fraction
    body["waist_back_width"] = float(body["waist"]) * sections["waist"].back_fraction
    for station, key in (
        ("bust", "patterna_back_bust_fraction"),
        ("upperTorsoCircuit", "patterna_back_upper_torso_fraction"),
        ("underarmCircuit", "patterna_back_underarm_fraction"),
        ("underbust", "patterna_back_underbust_fraction"),
        ("waist", "patterna_back_waist_fraction"),
    ):
        body[key] = sections[station].back_fraction
    body["patterna_back_high_bust_tape_fraction"] = high_bust_back_fraction
    waist_height = stations["waist"]
    body["patterna_waist_level_world"] = waist_height
    body["patterna_side_seam_height_from_waist"] = stations["underarmCircuit"] - waist_height
    body["patterna_upper_torso_height_from_waist"] = stations["upperTorsoCircuit"] - waist_height
    body["patterna_high_bust_tape_height_from_waist"] = stations["highBustTape"] - waist_height
    body["patterna_bust_height_from_waist"] = stations["bust"] - waist_height
    body["patterna_underbust_height_from_waist"] = stations["underbust"] - waist_height
    body["patterna_full_bust_horizontal_circumference"] = sections["bust"].circumference_cm
    body["patterna_upper_torso_circumference"] = sections["upperTorsoCircuit"].circumference_cm
    body["patterna_underarm_circumference"] = sections["underarmCircuit"].circumference_cm

    bust_apex_half_cm = float(body["bust_points"]) / 2.0
    waist_princess_x_cm = bust_apex_half_cm * 0.78
    shoulder_half_cm = float(body["shoulder_w"]) / 2.0
    shoulder_princess_x_cm = min(
        shoulder_half_cm - max(2.5, shoulder_half_cm * 0.18),
        bust_apex_half_cm * 1.23,
    )
    shoulder_height_cm = float(np.ptp(collision_body.vertices[:, 1]) * 100.0) * 0.825
    body["patterna_front_princess_contour_length"] = measure_front_surface_ruler(
        collision_body,
        start_height_cm=waist_height,
        end_height_cm=stations["bust"],
        start_x_cm=waist_princess_x_cm,
        end_x_cm=bust_apex_half_cm,
    )
    body["patterna_front_princess_upper_contour_length"] = measure_front_surface_ruler(
        collision_body,
        start_height_cm=stations["bust"],
        end_height_cm=shoulder_height_cm,
        start_x_cm=bust_apex_half_cm,
        end_x_cm=shoulder_princess_x_cm,
    )
    return body, {
        "heightsCm": stations,
        "bustSideSeamDepthCm": bust_side_seam_depth_cm,
        "bustArcSplitMethod": "interpolated underbust-to-upper-torso side-seam depth",
        "highBustTapeDistribution": {
            "heightCm": stations["highBustTape"],
            "requestedCircumferenceCm": float(measurements["highChestCirc"]),
            "backFraction": high_bust_back_fraction,
            "source": "editable acrossFront and acrossBack measurements",
            "horizontalColliderSectionUsed": False,
        },
        "sections": {name: section.to_dict() for name, section in sections.items()},
    }


def main() -> None:
    args = parse_args()
    avatar_body_path = resolve(args.avatar_body)
    avatar_report_path = resolve(args.avatar_report)
    fit_report_path = resolve(args.fit_report)
    profile_path = resolve(args.profile)
    output_body_path = resolve(args.output_body)
    avatar_report = json.loads(avatar_report_path.read_text(encoding="utf-8"))
    fit_report = json.loads(fit_report_path.read_text(encoding="utf-8"))
    profile = json.loads(profile_path.read_text(encoding="utf-8"))
    if (
        not avatar_report.get("accepted")
        or avatar_report.get("acceptanceScope") != "measurement-fit-and-geometry-export"
        or not fit_report.get("accepted")
    ):
        raise ValueError(
            "CharMorph body export and measurement fit must both be accepted for collision preparation"
        )
    if avatar_report.get("outputBodySha256") != sha256(avatar_body_path):
        raise ValueError("CharMorph avatar report does not match the body OBJ")
    if fit_report.get("sourceProfileSha256") != sha256(profile_path):
        raise ValueError("CharMorph fit report does not match the profile")
    if avatar_report.get("fitReportSha256") != sha256(fit_report_path):
        raise ValueError("CharMorph avatar report does not match the fit report")

    source = load_mesh(avatar_body_path)
    collider_z_up, cap_report = build_collision_body(source)
    converted_vertices = blender_obj_to_garmentcode(
        np.asarray(collider_z_up.vertices, dtype=float)
    )
    collision_body = trimesh.Trimesh(
        vertices=converted_vertices,
        faces=np.asarray(collider_z_up.faces, dtype=np.int64),
        process=False,
        maintain_order=True,
    )
    collision_body.fix_normals(multibody=False)
    if not collision_body.is_watertight:
        raise ValueError("Prepared CharMorph collision body is not watertight")
    components = collision_body.split(only_watertight=False)
    if len(components) != 1:
        raise ValueError("Prepared CharMorph collision body is not one component")

    segmentation = semantic_segmentation(np.asarray(collision_body.vertices, dtype=float))
    landmarks = fit_report.get("anatomicalLandmarks")
    if not isinstance(landmarks, dict):
        raise ValueError("CharMorph fit report has no anatomical landmark evidence")
    body_values, circuit_report = drafting_body(
        collision_body,
        profile,
        float(landmarks["bustApexHeightRatio"]),
    )
    output_body_path.parent.mkdir(parents=True, exist_ok=True)
    collision_body.export(output_body_path)
    segmentation_path = output_body_path.with_suffix(".segmentation.json")
    measurements_path = output_body_path.with_suffix(".yaml")
    report_path = output_body_path.with_suffix(".report.json")
    segmentation_path.write_text(json.dumps(segmentation, indent=2) + "\n", encoding="utf-8")
    measurements_path.write_text(
        yaml.safe_dump({"body": body_values}, sort_keys=True),
        encoding="utf-8",
    )
    height_cm = float(np.ptp(collision_body.vertices[:, 1]) * 100.0)
    requested_height_cm = float(profile["measurements"]["height"])
    report = {
        "schemaVersion": "patterna.charmorph-garmentcode-body/1.0",
        "sourceBody": str(avatar_body_path),
        "sourceBodySha256": sha256(avatar_body_path),
        "sourceAvatarReport": str(avatar_report_path),
        "sourceAvatarReportSha256": sha256(avatar_report_path),
        "sourceFitReport": str(fit_report_path),
        "sourceFitReportSha256": sha256(fit_report_path),
        "sourceProfile": str(profile_path),
        "sourceProfileSha256": sha256(profile_path),
        "outputBody": str(output_body_path),
        "outputBodySha256": sha256(output_body_path),
        "coordinateTransform": "exported OBJ x,y,z -> GarmentCode x,z,y; feet translated to y=0",
        "sourceVertexCount": int(len(source.vertices)),
        "sourceFaceCount": int(len(source.faces)),
        "vertexCount": int(len(collision_body.vertices)),
        "faceCount": int(len(collision_body.faces)),
        "watertight": bool(collision_body.is_watertight),
        "connectedComponents": len(components),
        "heightCm": height_cm,
        "requestedHeightCm": requested_height_cm,
        "heightResidualCm": height_cm - requested_height_cm,
        "segmentationCounts": {name: len(indices) for name, indices in segmentation.items()},
        "segmentationSource": "CharMorph coordinate-semantic regions",
        "boundaryCaps": {
            "loopCount": cap_report.loop_count,
            "loopVertexCounts": list(cap_report.loop_vertex_counts),
            "minimumLoopHeightRatio": cap_report.minimum_loop_height_ratio,
            "maximumLoopHeightRatio": cap_report.maximum_loop_height_ratio,
            "garmentContactSurfaceModified": False,
        },
        "anatomicalCircuits": circuit_report,
        "accepted": bool(abs(height_cm - requested_height_cm) <= 0.15),
    }
    report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    if not report["accepted"]:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
