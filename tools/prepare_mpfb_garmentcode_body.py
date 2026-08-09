#!/usr/bin/env python3
"""Create a GarmentCode body from the accepted MPFB avatar artifact."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path

import numpy as np
import trimesh
import yaml

try:
    from .mesh_torso_arcs import (
        back_fraction_from_across_measurements,
        measure_front_surface_ruler,
        measure_torso_arc_section,
    )
    from .mpfb_measurements import MEASUREMENT_VERTEX_CHAINS
except ImportError:
    from mesh_torso_arcs import (
        back_fraction_from_across_measurements,
        measure_front_surface_ruler,
        measure_torso_arc_section,
    )
    from mpfb_measurements import MEASUREMENT_VERTEX_CHAINS


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--avatar-body",
        type=Path,
        default=Path("PatternaUnreal/Saved/Patterna/MPFB/PatternaDefaultFemale.obj"),
    )
    parser.add_argument(
        "--fit-report",
        type=Path,
        default=Path(
            "PatternaUnreal/Saved/Patterna/MPFB/PatternaDefaultFemale.fit-report.json"
        ),
    )
    parser.add_argument(
        "--profile",
        type=Path,
        default=Path(
            "PatternaUnreal/SourceAssets/GarmentCode/PatternaDefaultFemale.body.json"
        ),
    )
    parser.add_argument(
        "--pose-report",
        type=Path,
        default=None,
        help="Optional accepted pose report linking a posed body to the fitted source body.",
    )
    parser.add_argument(
        "--rig-weights",
        type=Path,
        default=Path(
            "third_party/MPFB2/src/mpfb/data/rigs/standard/weights.default.json"
        ),
    )
    parser.add_argument(
        "--output-body",
        type=Path,
        default=Path("third_party/GarmentCode/assets/bodies/patterna_mpfb_female.obj"),
    )
    return parser.parse_args()


def resolve(repo_root: Path, path: Path) -> Path:
    return path.resolve() if path.is_absolute() else (repo_root / path).resolve()


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_mesh(path: Path) -> trimesh.Trimesh:
    mesh = trimesh.load(path, process=False, maintain_order=True)
    if not isinstance(mesh, trimesh.Trimesh):
        raise TypeError(f"Expected one mesh in {path}, received {type(mesh).__name__}")
    return mesh


def blender_to_garmentcode(vertices: np.ndarray) -> np.ndarray:
    """Convert Blender X right, Y depth, Z up to GarmentCode X, Y up, Z depth."""
    converted = np.empty_like(vertices, dtype=float)
    converted[:, 0] = vertices[:, 0]
    converted[:, 1] = vertices[:, 2]
    converted[:, 2] = vertices[:, 1]
    converted[:, 1] -= float(np.min(converted[:, 1]))
    return converted


def measurement_height_cm(vertices: np.ndarray, ruler_name: str) -> float:
    indices = np.asarray(MEASUREMENT_VERTEX_CHAINS[ruler_name], dtype=int)
    if int(indices.max()) >= len(vertices):
        raise ValueError(f"Ruler {ruler_name} exceeds the stable MPFB topology.")
    return float(np.mean(vertices[indices, 1]) * 100.0)


def measurement_landmark_height_cm(
    vertices: np.ndarray,
    ruler_name: str,
    landmark_index: int,
) -> float:
    indices = MEASUREMENT_VERTEX_CHAINS[ruler_name]
    try:
        vertex_index = int(indices[landmark_index])
    except IndexError as error:
        raise ValueError(
            f"Ruler {ruler_name} has no landmark at index {landmark_index}."
        ) from error
    if vertex_index >= len(vertices):
        raise ValueError(f"Ruler {ruler_name} exceeds the stable MPFB topology.")
    return float(vertices[vertex_index, 1] * 100.0)


def averaged_profile_measurement_cm(
    profile_payload: dict[str, object],
    *keys: str,
) -> float:
    measurements = profile_payload.get("measurements")
    if not isinstance(measurements, dict):
        raise ValueError("Avatar profile has no detailed measurements object.")
    values = [
        float(measurements[key])
        for key in keys
        if key in measurements
    ]
    if not values:
        raise ValueError(
            "Avatar profile is missing every required measurement: "
            + ", ".join(keys)
        )
    if not np.isfinite(values).all() or min(values) <= 0.0:
        raise ValueError("Avatar profile contains an invalid detailed measurement.")
    return float(np.mean(values))


def torso_station_heights_cm(
    vertices: np.ndarray,
    profile_payload: dict[str, object],
) -> dict[str, float]:
    """Bind drafting stations to fitted-body landmarks.

    A high-chest tape runs above the bust and may cross the armscye opening.
    It is not the same thing as the closed torso circuit immediately below the
    side-seam endpoint. The old bridge treated both as ``highBust`` and then
    attempted to wrap the smaller tape value around the larger lower section.
    """

    waist_height_cm = measurement_height_cm(vertices, "waist_circumference")
    bust_height_cm = measurement_height_cm(vertices, "bust_circumference")
    nape_height_cm = measurement_landmark_height_cm(
        vertices,
        "nape_to_waist",
        0,
    )
    armscye_depth_cm = averaged_profile_measurement_cm(
        profile_payload,
        "armholeDepthL",
        "armholeDepthR",
    )
    side_seam_height_cm = nape_height_cm - armscye_depth_cm
    if side_seam_height_cm <= bust_height_cm:
        raise ValueError(
            "The fitted underarm landmark must be above the full-bust station."
        )
    upper_torso_height_cm = bust_height_cm + 0.65 * (
        side_seam_height_cm - bust_height_cm
    )
    high_bust_tape_height_cm = measurement_height_cm(
        vertices,
        "front_chest_distance",
    )
    if high_bust_tape_height_cm <= side_seam_height_cm:
        raise ValueError(
            "The high-chest tape landmark must be above the underarm endpoint."
        )
    return {
        "waist": waist_height_cm,
        "underbust": measurement_height_cm(
            vertices,
            "underbust_circumference",
        ),
        "bust": bust_height_cm,
        "upperTorsoCircuit": upper_torso_height_cm,
        "underarmCircuit": side_seam_height_cm,
        "highBustTape": high_bust_tape_height_cm,
    }


def semantic_label_for_bone(bone_name: str) -> str | None:
    lower_name = bone_name.lower()
    side = None
    if bone_name.endswith(".L"):
        side = "left"
    elif bone_name.endswith(".R"):
        side = "right"
    if side and any(
        token in lower_name
        for token in ("upperarm", "lowerarm", "wrist", "metacarpal", "finger")
    ):
        return f"{side}_arm"
    if side and any(
        token in lower_name
        for token in ("upperleg", "lowerleg", "foot", "toe")
    ):
        return f"{side}_leg"
    if "tongue" in lower_name:
        return "face_internal"
    return None


def segmentation_from_rig_weights(
    vertex_count: int,
    weight_payload: dict[str, object],
    threshold: float = 0.2,
) -> dict[str, list[int]]:
    labels = (
        "left_arm",
        "right_arm",
        "left_leg",
        "right_leg",
        "face_internal",
    )
    scores = {label: np.zeros(vertex_count, dtype=float) for label in labels}
    weights = weight_payload.get("weights")
    if not isinstance(weights, dict):
        raise ValueError("MPFB rig weight file has no weights object.")
    for bone_name, entries in weights.items():
        label = semantic_label_for_bone(str(bone_name))
        if label is None or not isinstance(entries, list):
            continue
        for entry in entries:
            if not isinstance(entry, list) or len(entry) != 2:
                continue
            vertex_index = int(entry[0])
            if 0 <= vertex_index < vertex_count:
                scores[label][vertex_index] += float(entry[1])

    segmentation = {label: [] for label in labels}
    segmentation["body"] = []
    for vertex_index in range(vertex_count):
        label = max(labels, key=lambda candidate: scores[candidate][vertex_index])
        if scores[label][vertex_index] >= threshold:
            segmentation[label].append(vertex_index)
        else:
            segmentation["body"].append(vertex_index)
    return segmentation


def main() -> None:
    args = parse_args()
    repo_root = Path(__file__).resolve().parents[1]
    avatar_path = resolve(repo_root, args.avatar_body)
    fit_report_path = resolve(repo_root, args.fit_report)
    pose_report_path = (
        resolve(repo_root, args.pose_report)
        if args.pose_report is not None
        else None
    )
    profile_path = resolve(repo_root, args.profile)
    rig_weights_path = resolve(repo_root, args.rig_weights)
    output_body_path = resolve(repo_root, args.output_body)

    fit_report = json.loads(fit_report_path.read_text(encoding="utf-8"))
    profile_payload = json.loads(profile_path.read_text(encoding="utf-8"))
    profile_body = profile_payload.get("body")
    if not fit_report.get("accepted"):
        raise ValueError("MPFB fit report is rejected.")
    if fit_report.get("source_profile_sha256") != sha256(profile_path):
        raise ValueError("MPFB fit report does not match the requested profile.")
    pose_report = None
    if pose_report_path is not None:
        pose_report = json.loads(pose_report_path.read_text(encoding="utf-8"))
        if not pose_report.get("accepted"):
            raise ValueError("MPFB pose report is rejected.")
        if pose_report.get("source_body_sha256") != fit_report.get("output_body_sha256"):
            raise ValueError("MPFB pose report does not match the fitted source body.")
        if pose_report.get("output_body_sha256") != sha256(avatar_path):
            raise ValueError("MPFB pose report does not match the posed avatar mesh.")
        if not pose_report.get("topology_preserved"):
            raise ValueError("MPFB pose report does not prove stable body topology.")
    elif fit_report.get("output_body_sha256") != sha256(avatar_path):
        raise ValueError("MPFB fit report does not match the avatar mesh.")
    if not isinstance(profile_body, dict) or not profile_body:
        raise ValueError("Avatar profile must contain a non-empty body object.")

    source_mesh = load_mesh(avatar_path)
    transformed_vertices = blender_to_garmentcode(
        np.asarray(source_mesh.vertices, dtype=float)
    )
    collision_body = trimesh.Trimesh(
        vertices=transformed_vertices,
        faces=np.asarray(source_mesh.faces, dtype=np.int64),
        process=False,
        maintain_order=True,
    )
    collision_body.remove_unreferenced_vertices()
    collision_body.fix_normals()
    if not collision_body.is_watertight:
        raise ValueError("MPFB collision body is not watertight.")
    components = collision_body.split(only_watertight=False)
    if len(components) != 1:
        raise ValueError(
            f"MPFB collision body has {len(components)} connected components."
        )

    transferred_segmentation = segmentation_from_rig_weights(
        len(collision_body.vertices),
        json.loads(rig_weights_path.read_text(encoding="utf-8")),
    )

    station_heights = torso_station_heights_cm(
        transformed_vertices,
        profile_payload,
    )
    torso_arc_sections = {
        name: measure_torso_arc_section(collision_body, height)
        for name, height in station_heights.items()
    }
    measurements = profile_payload.get("measurements")
    if not isinstance(measurements, dict):
        raise ValueError("Avatar profile has no detailed measurements object.")
    high_bust_tape_cm = float(measurements["highChestCirc"])
    if not np.isfinite(high_bust_tape_cm) or high_bust_tape_cm <= 0.0:
        raise ValueError("High-chest circumference must be positive and finite.")
    high_bust_back_fraction = back_fraction_from_across_measurements(
        float(measurements["acrossFront"]),
        float(measurements["acrossBack"]),
    )
    measurement_origins = profile_payload.get("measurementOrigins")
    high_bust_origin = (
        str(measurement_origins.get("highChestCirc", "unknown"))
        if isinstance(measurement_origins, dict)
        else "unknown"
    )
    armscye_circumference_cm = averaged_profile_measurement_cm(
        profile_payload,
        "armscyeCircL",
        "armscyeCircR",
    )
    armscye_origins = [
        str(measurement_origins.get(key, "unknown"))
        for key in ("armscyeCircL", "armscyeCircR")
    ] if isinstance(measurement_origins, dict) else ["unknown", "unknown"]
    armscye_is_estimated = all(
        origin.strip().casefold() == "estimated"
        for origin in armscye_origins
    )
    armhole_depth_cm = averaged_profile_measurement_cm(
        profile_payload,
        "armholeDepthL",
        "armholeDepthR",
    )
    armhole_depth_origins = [
        str(measurement_origins.get(key, "unknown"))
        for key in ("armholeDepthL", "armholeDepthR")
    ] if isinstance(measurement_origins, dict) else ["unknown", "unknown"]
    armhole_depth_is_estimated = all(
        origin.strip().casefold() == "estimated"
        for origin in armhole_depth_origins
    )
    profile_heights = sorted({
        *np.linspace(
            station_heights["bust"],
            station_heights["highBustTape"],
            49,
        ).tolist(),
        station_heights["upperTorsoCircuit"],
        station_heights["underarmCircuit"],
    })
    torso_station_profile = [
        measure_torso_arc_section(collision_body, height)
        for height in profile_heights
    ]
    bust_apex_half_cm = float(profile_body["bust_points"]) / 2.0
    waist_princess_x_cm = bust_apex_half_cm * 0.78
    shoulder_half_cm = float(profile_body["shoulder_w"]) / 2.0
    neck_half_cm = float(profile_body["neck_w"]) * 0.42
    shoulder_princess_x_cm = min(
        shoulder_half_cm - max(2.5, shoulder_half_cm * 0.18),
        bust_apex_half_cm * 1.23,
    )
    shoulder_drop_cm = math.tan(
        math.radians(
            float(
                profile_body.get(
                    "_shoulder_incl",
                    profile_body["shoulder_incl"],
                )
            )
        )
    ) * (shoulder_half_cm - neck_half_cm)
    shoulder_height_cm = (
        station_heights["waist"]
        + float(profile_body["waist_over_bust_line"])
        - shoulder_drop_cm * 0.45
    )
    front_princess_contour_length_cm = measure_front_surface_ruler(
        collision_body,
        start_height_cm=station_heights["waist"],
        end_height_cm=station_heights["bust"],
        start_x_cm=waist_princess_x_cm,
        end_x_cm=bust_apex_half_cm,
    )
    front_princess_upper_contour_length_cm = measure_front_surface_ruler(
        collision_body,
        start_height_cm=station_heights["bust"],
        end_height_cm=shoulder_height_cm,
        start_x_cm=bust_apex_half_cm,
        end_x_cm=shoulder_princess_x_cm,
    )
    drafting_body = dict(profile_body)
    drafting_body["high_bust"] = high_bust_tape_cm
    drafting_body["armscye_circumference"] = armscye_circumference_cm
    drafting_body["patterna_armscye_is_estimated"] = float(armscye_is_estimated)
    drafting_body["patterna_requested_armhole_depth"] = armhole_depth_cm
    drafting_body["patterna_armhole_depth_is_estimated"] = float(
        armhole_depth_is_estimated
    )
    drafting_body["back_width"] = (
        float(profile_body["bust"]) * torso_arc_sections["bust"].back_fraction
    )
    drafting_body["waist_back_width"] = (
        float(profile_body["waist"]) * torso_arc_sections["waist"].back_fraction
    )
    for station, key in (
        ("bust", "patterna_back_bust_fraction"),
        ("upperTorsoCircuit", "patterna_back_upper_torso_fraction"),
        ("underarmCircuit", "patterna_back_underarm_fraction"),
        ("underbust", "patterna_back_underbust_fraction"),
        ("waist", "patterna_back_waist_fraction"),
    ):
        drafting_body[key] = torso_arc_sections[station].back_fraction
    drafting_body["patterna_back_high_bust_tape_fraction"] = high_bust_back_fraction
    drafting_body["patterna_waist_level_world"] = station_heights["waist"]
    drafting_body["patterna_side_seam_height_from_waist"] = (
        station_heights["underarmCircuit"] - station_heights["waist"]
    )
    drafting_body["patterna_upper_torso_height_from_waist"] = (
        station_heights["upperTorsoCircuit"] - station_heights["waist"]
    )
    drafting_body["patterna_high_bust_tape_height_from_waist"] = (
        station_heights["highBustTape"] - station_heights["waist"]
    )
    drafting_body["patterna_bust_height_from_waist"] = (
        station_heights["bust"] - station_heights["waist"]
    )
    drafting_body["patterna_underbust_height_from_waist"] = (
        station_heights["underbust"] - station_heights["waist"]
    )
    drafting_body["patterna_front_princess_contour_length"] = (
        front_princess_contour_length_cm
    )
    drafting_body["patterna_front_princess_upper_contour_length"] = (
        front_princess_upper_contour_length_cm
    )
    drafting_body["patterna_full_bust_horizontal_circumference"] = (
        torso_arc_sections["bust"].circumference_cm
    )
    drafting_body["patterna_upper_torso_circumference"] = (
        torso_arc_sections["upperTorsoCircuit"].circumference_cm
    )
    drafting_body["patterna_underarm_circumference"] = (
        torso_arc_sections["underarmCircuit"].circumference_cm
    )
    drafting_body["patterna_torso_station_profile_count"] = float(
        len(torso_station_profile)
    )
    for index, section in enumerate(torso_station_profile):
        prefix = f"patterna_torso_station_{index:02d}"
        drafting_body[f"{prefix}_height_from_waist"] = (
            section.height_cm - station_heights["waist"]
        )
        drafting_body[f"{prefix}_circumference"] = section.circumference_cm
        drafting_body[f"{prefix}_back_fraction"] = section.back_fraction

    output_segmentation_path = output_body_path.with_suffix(".segmentation.json")
    output_measurements_path = output_body_path.with_suffix(".yaml")
    output_report_path = output_body_path.with_suffix(".report.json")
    output_body_path.parent.mkdir(parents=True, exist_ok=True)
    collision_body.export(output_body_path)
    output_segmentation_path.write_text(
        json.dumps(transferred_segmentation, indent=2) + "\n",
        encoding="utf-8",
    )
    output_measurements_path.write_text(
        yaml.safe_dump({"body": drafting_body}, sort_keys=True),
        encoding="utf-8",
    )

    body_height_cm = float(collision_body.bounds[1, 1] * 100.0)
    report = {
        "schemaVersion": "patterna.mpfb-garmentcode-body/1.0",
        "sourceBody": str(avatar_path),
        "sourceBodySha256": sha256(avatar_path),
        "sourceFitReport": str(fit_report_path),
        "sourceFitReportSha256": sha256(fit_report_path),
        "sourcePoseReport": str(pose_report_path) if pose_report_path else None,
        "sourcePoseReportSha256": sha256(pose_report_path) if pose_report_path else None,
        "pose": pose_report.get("pose") if pose_report else "source-rest-pose",
        "sourceProfile": str(profile_path),
        "sourceProfileSha256": sha256(profile_path),
        "sourceRigWeights": str(rig_weights_path),
        "sourceRigWeightsSha256": sha256(rig_weights_path),
        "outputBody": str(output_body_path),
        "outputBodySha256": sha256(output_body_path),
        "coordinateTransform": "x,y,z -> x,z,y; feet translated to y=0",
        "sourceVertexCount": int(len(source_mesh.vertices)),
        "sourceFaceCount": int(len(source_mesh.faces)),
        "vertexCount": int(len(collision_body.vertices)),
        "faceCount": int(len(collision_body.faces)),
        "watertight": bool(collision_body.is_watertight),
        "connectedComponents": int(len(components)),
        "boundsMeters": np.asarray(collision_body.bounds, dtype=float).tolist(),
        "heightCm": body_height_cm,
        "requestedHeightCm": float(profile_body["height"]),
        "heightResidualCm": body_height_cm - float(profile_body["height"]),
        "segmentationCounts": {
            key: len(value) for key, value in transferred_segmentation.items()
        },
        "segmentationSource": "MPFB default rig skin weights at stable hm08 indices",
        "measurementProfileCopiedFromSource": True,
        "anatomicalCircuitContract": {
            "highBustTape": {
                "source": "editable highChestCirc measurement",
                "requestedCircumferenceCm": high_bust_tape_cm,
                "measurementOrigin": high_bust_origin,
                "landmarkSource": "front_chest_distance MPFB ruler height",
                "heightCm": station_heights["highBustTape"],
                "colliderHorizontalCircumferenceCm": torso_arc_sections[
                    "highBustTape"
                ].circumference_cm,
                "backFraction": high_bust_back_fraction,
                "backFractionSource": "editable acrossFront and acrossBack measurements",
                "usedAsClosedGarmentCircuit": False,
            },
            "upperTorsoCircuit": {
                "source": (
                    "65 percent of the fitted bust-to-underarm landmark interval"
                ),
                "heightCm": station_heights["upperTorsoCircuit"],
                "circumferenceCm": torso_arc_sections[
                    "upperTorsoCircuit"
                ].circumference_cm,
                "backFraction": torso_arc_sections[
                    "upperTorsoCircuit"
                ].back_fraction,
                "usedAsClosedGarmentCircuit": True,
            },
            "underarmCircuit": {
                "source": "fitted nape landmark minus editable armhole depth",
                "heightCm": station_heights["underarmCircuit"],
                "circumferenceCm": torso_arc_sections[
                    "underarmCircuit"
                ].circumference_cm,
                "backFraction": torso_arc_sections[
                    "underarmCircuit"
                ].back_fraction,
                "usedAsClosedGarmentCircuit": True,
            },
            "armscye": {
                "requestedCircumferenceCm": armscye_circumference_cm,
                "measurementOrigins": armscye_origins,
                "estimatedValueMayExpandToBlockMinimum": armscye_is_estimated,
                "requestedDepthCm": armhole_depth_cm,
                "depthMeasurementOrigins": armhole_depth_origins,
                "estimatedDepthMayReconcileToManualCircumference": (
                    armhole_depth_is_estimated
                ),
            },
        },
        "torsoStationProfile": [
            {
                "heightFromWaistCm": section.height_cm - station_heights["waist"],
                "circumferenceCm": section.circumference_cm,
                "backFraction": section.back_fraction,
            }
            for section in torso_station_profile
        ],
        "torsoArcAllocation": {
            "source": "exact horizontal sections of outputBody",
            "frontDirection": "positive GarmentCode Z",
            "sections": {
                key: section.to_dict()
                for key, section in torso_arc_sections.items()
            },
            "draftingBackWidthCm": drafting_body["back_width"],
            "draftingWaistBackWidthCm": drafting_body["waist_back_width"],
        },
        "frontPrincessSurfaceRulers": {
            "source": "exact evaluated collider cross sections",
            "waistToBustCm": front_princess_contour_length_cm,
            "bustToShoulderCm": front_princess_upper_contour_length_cm,
            "waistHeightCm": station_heights["waist"],
            "bustHeightCm": station_heights["bust"],
            "shoulderHeightCm": shoulder_height_cm,
            "waistXFromCenterCm": waist_princess_x_cm,
            "bustApexXFromCenterCm": bust_apex_half_cm,
            "shoulderXFromCenterCm": shoulder_princess_x_cm,
            "neckHalfWidthCm": neck_half_cm,
            "shoulderDropCm": shoulder_drop_cm,
        },
        "accepted": bool(
            collision_body.is_watertight
            and len(components) == 1
            and abs(body_height_cm - float(profile_body["height"])) <= 0.15
        ),
    }
    output_report_path.write_text(
        json.dumps(report, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(report, indent=2))
    if not report["accepted"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
