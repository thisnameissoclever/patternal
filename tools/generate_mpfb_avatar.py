#!/usr/bin/env python3
"""Generate a measurement-fitted MPFB female avatar inside Blender."""

from __future__ import annotations

import argparse
import hashlib
import importlib
import json
import math
import numpy as np
from pathlib import Path
import shutil
import subprocess
import sys
from typing import Any
from dataclasses import asdict, dataclass

import bpy
from mathutils import Vector
from mathutils.bvhtree import BVHTree


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "tools"))

from mpfb_measurements import (  # noqa: E402
    DIRECT_TARGET_PAIRS,
    MEASUREMENT_VERTEX_CHAINS,
)
from mpfb_morph_controls import (  # noqa: E402
    DIRECT_RULER_SOURCE_KEYS,
    FEMALE_GENDER_MACRO,
    evaluate_morph_controls,
    macro_controls,
    mapped_measurement_keys,
)
from mpfb_local_deformations import (  # noqa: E402
    apply_local_deformations,
    local_deformation_keys,
)
from mpfb_fit_acceptance import evaluate_fit_acceptance  # noqa: E402
from mpfb_surface_constraints import (  # noqa: E402
    BustToHighChestSurfaceConstraintReport,
    HorizontalTorsoCircumferenceConstraintReport,
    LandmarkTapeConstraintReport,
    WaistSurfaceConstraintReport,
    enforce_horizontal_torso_circumference,
    enforce_landmark_tape_length,
    enforce_waist_to_underbust_surface,
)


HumanObjectProperties: Any = None
HumanService: Any = None
TargetService: Any = None
MPFB_MODULE_NAME = "bl_ext.user_default.mpfb"
BRA_DISPLAY_SURFACE_OFFSET_M = 0.00008
BRA_DISPLAY_STRAP_OFFSET_M = 0.00010
_BODY_SURFACE_FACE_CACHE: dict[int, tuple[tuple[int, ...], ...]] = {}
SURFACE_AUTHORITATIVE_RULERS = frozenset({
    "bust_circumference",
    "underbust_circumference",
})


@dataclass(frozen=True)
class AppliedAvatarDeformations:
    local: tuple[Any, ...]
    waist_surface: WaistSurfaceConstraintReport | None
    underbust_surface: LandmarkTapeConstraintReport | None
    bust_surface: HorizontalTorsoCircumferenceConstraintReport | None
    high_chest_surface: BustToHighChestSurfaceConstraintReport | None


PROFILE_TO_MPF_BASE: dict[str, tuple[str, float]] = {
    "bust": ("bust_circumference", 1.0),
    "underbust": ("underbust_circumference", 1.0),
    "waist": ("waist_circumference", 1.0),
    "hips": ("hip_circumference", 1.0),
    "neck_w": ("neck_circumference", 2.0),
    "arm_length": ("upper_arm_length", 0.47),
    "wrist": ("wrist_circumference", 1.0),
    "waist_over_bust_line": ("nape_to_waist", 1.0),
    "hips_line": ("waist_to_hip", 1.0),
    "leg_circ": ("thigh_circumference", 1.0),
}


def blender_arguments() -> list[str]:
    return sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--profile",
        type=Path,
        default=Path(
            "PatternaUnreal/SourceAssets/GarmentCode/PatternaDefaultFemale.body.json"
        ),
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("PatternaUnreal/Saved/Patterna/MPFB/PatternaDefaultFemale.obj"),
    )
    parser.add_argument("--max-target-weight", type=float, default=2.0)
    parser.add_argument("--fit-passes", type=int, default=30)
    parser.add_argument("--tolerance-cm", type=float, default=0.15)
    parser.add_argument(
        "--render-output-dir",
        type=Path,
        default=None,
    )
    parser.add_argument(
        "--render-asset-root",
        type=Path,
        default=Path(
            "third_party/MakeHumanAssets/makehuman_system_assets"
        ),
    )
    parser.add_argument(
        "--hair-style",
        choices=("afro01", "bob01", "bob02", "braid01", "long01", "ponytail01", "short01", "short02", "short03", "short04"),
        default="braid01",
    )
    return parser.parse_args(blender_arguments())


def resolve(value: Path) -> Path:
    return value.resolve() if value.is_absolute() else (REPO_ROOT / value).resolve()


def numeric_values(value: Any) -> dict[str, float]:
    if not isinstance(value, dict):
        return {}
    return {
        key: float(item)
        for key, item in value.items()
        if isinstance(key, str)
        and isinstance(item, (int, float))
        and math.isfinite(float(item))
    }


def string_values(value: Any) -> dict[str, str]:
    if not isinstance(value, dict):
        return {}
    return {
        key: item
        for key, item in value.items()
        if isinstance(key, str) and isinstance(item, str)
    }


def source_lists(value: Any) -> dict[str, list[str]]:
    if not isinstance(value, dict):
        return {}
    return {
        key: [item for item in items if isinstance(item, str)]
        for key, items in value.items()
        if isinstance(key, str) and isinstance(items, list)
    }


def profile_sections(
    profile_path: Path,
) -> tuple[
    dict[str, float],
    dict[str, float],
    dict[str, str],
    dict[str, list[str]],
]:
    payload = json.loads(profile_path.read_text(encoding="utf-8"))
    if not isinstance(payload.get("body"), dict):
        raise ValueError("Avatar profile must contain a body object.")
    return (
        numeric_values(payload["body"]),
        numeric_values(payload.get("measurements")),
        string_values(payload.get("measurementOrigins")),
        source_lists(payload.get("measurementSources")),
    )


def profile_body(profile_path: Path) -> dict[str, float]:
    body, measurements, _, _ = profile_sections(profile_path)
    result = dict(body)
    result.update(measurements)
    return result


def mixed_world_coordinates(basemesh: bpy.types.Object) -> list[Any]:
    depsgraph = bpy.context.evaluated_depsgraph_get()
    depsgraph.update()
    evaluated = basemesh.evaluated_get(depsgraph)
    if len(evaluated.data.vertices) != len(basemesh.data.vertices):
        raise RuntimeError(
            "Measurement evaluation changed MPFB vertex ordering. "
            "The fitter requires the stable hm08 topology."
        )
    matrix = evaluated.matrix_world
    return [matrix @ vertex.co for vertex in evaluated.data.vertices]


def body_surface_faces(basemesh: bpy.types.Object) -> tuple[tuple[int, ...], ...]:
    cache_key = int(basemesh.as_pointer())
    cached = _BODY_SURFACE_FACE_CACHE.get(cache_key)
    if cached is not None:
        return cached
    body_group = basemesh.vertex_groups.get("body")
    if body_group is None:
        raise RuntimeError("MPFB basemesh has no body vertex group.")
    body_group_index = body_group.index
    body_vertices = {
        vertex.index
        for vertex in basemesh.data.vertices
        if any(
            group.group == body_group_index and group.weight > 0.0
            for group in vertex.groups
        )
    }
    faces = tuple(
        tuple(polygon.vertices)
        for polygon in basemesh.data.polygons
        if all(index in body_vertices for index in polygon.vertices)
    )
    if not faces:
        raise RuntimeError("MPFB basemesh has no measurable body surface faces.")
    _BODY_SURFACE_FACE_CACHE[cache_key] = faces
    return faces


def deformed_world_coordinates(
    basemesh: bpy.types.Object,
    profile: dict[str, float],
    *,
    apply_surface_constraints: bool = True,
) -> tuple[list[Any], AppliedAvatarDeformations]:
    raw = mixed_world_coordinates(basemesh)
    deformed, local_results = apply_local_deformations(
        [(coordinate.x, coordinate.y, coordinate.z) for coordinate in raw],
        profile,
    )
    waist_surface = None
    underbust_surface = None
    bust_surface = None
    high_chest_surface = None
    if not apply_surface_constraints:
        return [Vector(point) for point in deformed], AppliedAvatarDeformations(
            local=local_results,
            waist_surface=None,
            underbust_surface=None,
            bust_surface=None,
            high_chest_surface=None,
        )
    target_waist_cm = profile.get("waist")
    target_underbust_cm = profile.get("underbust", profile.get("underBust"))
    if (
        target_waist_cm is not None
        and target_underbust_cm is not None
        and math.isfinite(float(target_waist_cm))
        and math.isfinite(float(target_underbust_cm))
    ):
        deformed, waist_surface = enforce_waist_to_underbust_surface(
            deformed,
            body_surface_faces(basemesh),
            MEASUREMENT_VERTEX_CHAINS["waist_circumference"],
            MEASUREMENT_VERTEX_CHAINS["underbust_circumference"],
            target_waist_cm=float(target_waist_cm),
            target_underbust_cm=float(target_underbust_cm),
        )
        # The underbust tape follows the inframammary root and rib cage. It is
        # not a planar horizontal collider section on a large supported bust.
        # Fit its nonplanar landmark path with a broad radial field. Forcing
        # every vertex at one height through the tape value compressed torso
        # depth by more than 3 cm and carved a shelf below the breasts.
        deformed, underbust_surface = enforce_landmark_tape_length(
            deformed,
            MEASUREMENT_VERTEX_CHAINS["underbust_circumference"],
            target_length_cm=float(target_underbust_cm),
            name="underbust-inframammary-tape",
        )
    target_bust_cm = profile.get("bust")
    if target_bust_cm is not None and math.isfinite(float(target_bust_cm)):
        deformed, bust_surface = enforce_horizontal_torso_circumference(
            deformed,
            body_surface_faces(basemesh),
            MEASUREMENT_VERTEX_CHAINS["bust_circumference"],
            target_circumference_cm=float(target_bust_cm),
            name="full-bust-horizontal-circumference",
        )
    # highChestCirc is a high-bust tape measurement, not a horizontal closed
    # collider circuit. Forcing the complete cross section to that smaller
    # tape value compressed torso depth by almost 30 percent and created a
    # visible ledge across the upper chest. It remains an editable MPFB morph
    # input; closed upper-torso and underarm circuits are measured later from
    # the evaluated collider without replacing their local curvature.
    return [Vector(point) for point in deformed], AppliedAvatarDeformations(
        local=local_results,
        waist_surface=waist_surface,
        underbust_surface=underbust_surface,
        bust_surface=bust_surface,
        high_chest_surface=high_chest_surface,
    )


def ruler_measurement_cm(coordinates: list[Any], name: str) -> float:
    indices = MEASUREMENT_VERTEX_CHAINS[name]
    maximum = len(coordinates) - 1
    if any(index < 0 or index > maximum for index in indices):
        raise IndexError(f"Measurement {name} is incompatible with this MPFB topology.")
    distance_m = 0.0
    previous = indices[0]
    for current in indices:
        distance_m += (coordinates[previous] - coordinates[current]).length
        previous = current
    return distance_m * 100.0


def avatar_height_cm(coordinates: list[Any]) -> float:
    z_values = [coordinate.z for coordinate in coordinates[:13380]]
    return (max(z_values) - min(z_values)) * 100.0


def set_height(
    basemesh: bpy.types.Object,
    desired_cm: float,
    tolerance_cm: float,
) -> dict[str, float]:
    del tolerance_cm
    measured = avatar_height_cm(mixed_world_coordinates(basemesh))
    if measured <= 0.0:
        raise RuntimeError("MPFB avatar has a non-positive measured height.")
    scale_factor = desired_cm / measured
    basemesh.scale = tuple(component * scale_factor for component in basemesh.scale)
    bpy.context.view_layer.update()
    return {
        "target_cm": desired_cm,
        "measured_cm": avatar_height_cm(mixed_world_coordinates(basemesh)),
        "uniform_scale": float(basemesh.scale.x),
    }


def ensure_target_pair(basemesh: bpy.types.Object, measurement_name: str) -> None:
    for target_name in DIRECT_TARGET_PAIRS[measurement_name]:
        if TargetService.has_target(basemesh, target_name):
            continue
        target_path = TargetService.target_full_path(target_name)
        if not target_path:
            raise FileNotFoundError(f"MPFB target not found: {target_name}")
        TargetService.load_target(basemesh, target_path, weight=0.0, name=target_name)


def set_pair_weights(
    basemesh: bpy.types.Object,
    measurement_name: str,
    decreasing_weight: float,
    increasing_weight: float,
) -> None:
    decreasing, increasing = DIRECT_TARGET_PAIRS[measurement_name]
    TargetService.set_target_value(basemesh, decreasing, decreasing_weight)
    TargetService.set_target_value(basemesh, increasing, increasing_weight)


def ensure_detail_target(basemesh: bpy.types.Object, target_name: str) -> None:
    if TargetService.has_target(basemesh, target_name):
        return
    target_path = TargetService.target_full_path(target_name)
    if not target_path:
        raise FileNotFoundError(f"MPFB detail target not found: {target_name}")
    TargetService.load_target(basemesh, target_path, weight=0.0, name=target_name)


def apply_detail_morph_controls(
    basemesh: bpy.types.Object,
    profile: dict[str, float],
) -> list[dict[str, Any]]:
    evaluated = evaluate_morph_controls(profile)
    for control in evaluated:
        for target_name, weight in control.target_weights:
            ensure_detail_target(basemesh, target_name)
            shape_key = basemesh.data.shape_keys.key_blocks[target_name]
            shape_key.slider_max = max(shape_key.slider_max, max(1.0, weight))
            TargetService.set_target_value(basemesh, target_name, weight)
    bpy.context.view_layer.update()
    return [asdict(control) for control in evaluated]


def fit_direct_measurement(
    basemesh: bpy.types.Object,
    measurement_name: str,
    desired_cm: float,
    max_target_weight: float,
    tolerance_cm: float,
) -> dict[str, Any]:
    ensure_target_pair(basemesh, measurement_name)
    for target_name in DIRECT_TARGET_PAIRS[measurement_name]:
        shape_key = basemesh.data.shape_keys.key_blocks[target_name]
        shape_key.slider_max = max(shape_key.slider_max, max_target_weight)
    set_pair_weights(basemesh, measurement_name, 0.0, 0.0)
    neutral = ruler_measurement_cm(mixed_world_coordinates(basemesh), measurement_name)
    direction_index = 1 if desired_cm >= neutral else 0

    def set_weight(weight: float) -> float:
        pair = [0.0, 0.0]
        pair[direction_index] = weight
        set_pair_weights(basemesh, measurement_name, pair[0], pair[1])
        return ruler_measurement_cm(mixed_world_coordinates(basemesh), measurement_name)

    endpoint = set_weight(max_target_weight)
    increases = endpoint > neutral
    desired_increases = desired_cm > neutral
    if increases != desired_increases and abs(desired_cm - neutral) > tolerance_cm:
        set_pair_weights(basemesh, measurement_name, 0.0, 0.0)
        raise RuntimeError(
            f"MPFB target direction for {measurement_name} is not monotonic: "
            f"neutral={neutral:.3f}, endpoint={endpoint:.3f}, desired={desired_cm:.3f}."
        )

    low = 0.0
    high = max_target_weight
    best_weight = 0.0
    best_measurement = neutral
    for _ in range(16):
        weight = (low + high) * 0.5
        measured = set_weight(weight)
        if abs(measured - desired_cm) < abs(best_measurement - desired_cm):
            best_weight = weight
            best_measurement = measured
        if (measured < desired_cm) == increases:
            low = weight
        else:
            high = weight
        if abs(measured - desired_cm) <= tolerance_cm:
            break
    set_weight(best_weight)
    final_measurement = ruler_measurement_cm(
        mixed_world_coordinates(basemesh), measurement_name
    )
    return {
        "target_cm": desired_cm,
        "measured_cm": final_measurement,
        "residual_cm": final_measurement - desired_cm,
        "direction": "increase" if direction_index else "decrease",
        "weight": best_weight,
        "reachable": (
            min(neutral, endpoint) - tolerance_cm
            <= desired_cm
            <= max(neutral, endpoint) + tolerance_cm
        ),
    }


def refine_coupled_direct_measurements(
    basemesh: bpy.types.Object,
    profile: dict[str, float],
    requested_measurements: dict[str, float],
    fit_results: dict[str, Any],
    max_target_weight: float,
    tolerance_cm: float,
) -> list[dict[str, Any]]:
    """Jointly refine ruler targets that perturb one another."""
    names = list(requested_measurements)
    active_targets = [
        DIRECT_TARGET_PAIRS[name][1 if fit_results[name]["direction"] == "increase" else 0]
        for name in names
    ]
    target_values = np.array(
        [requested_measurements[name] for name in names],
        dtype=float,
    )

    def weights() -> np.ndarray:
        return np.array(
            [
                float(basemesh.data.shape_keys.key_blocks[target_name].value)
                for target_name in active_targets
            ],
            dtype=float,
        )

    def set_weights(values: np.ndarray) -> None:
        for target_name, value in zip(active_targets, values):
            TargetService.set_target_value(
                basemesh,
                target_name,
                float(min(max(value, 0.0), max_target_weight)),
            )
        bpy.context.view_layer.update()

    def measured_values() -> np.ndarray:
        coordinates, _ = deformed_world_coordinates(
            basemesh,
            profile,
            apply_surface_constraints=False,
        )
        return np.array(
            [ruler_measurement_cm(coordinates, name) for name in names],
            dtype=float,
        )

    history: list[dict[str, Any]] = []
    for iteration in range(8):
        base_weights = weights()
        measured = measured_values()
        residual = measured - target_values
        starting_error = float(np.max(np.abs(residual)))
        if starting_error <= tolerance_cm * 0.5:
            history.append({
                "iteration": iteration + 1,
                "starting_max_error_cm": starting_error,
                "ending_max_error_cm": starting_error,
                "accepted": True,
            })
            break

        jacobian = np.zeros((len(names), len(active_targets)), dtype=float)
        for column, target_name in enumerate(active_targets):
            base = base_weights[column]
            step = 0.01 if base <= max_target_weight - 0.01 else -0.01
            TargetService.set_target_value(basemesh, target_name, float(base + step))
            bpy.context.view_layer.update()
            jacobian[:, column] = (measured_values() - measured) / step
            TargetService.set_target_value(basemesh, target_name, float(base))
        bpy.context.view_layer.update()

        normal_matrix = jacobian.T @ jacobian + np.eye(len(names)) * 1e-4
        gradient = -(jacobian.T @ residual)
        try:
            adjustment = np.linalg.solve(normal_matrix, gradient)
        except np.linalg.LinAlgError:
            adjustment = np.linalg.lstsq(jacobian, -residual, rcond=None)[0]
        adjustment = np.clip(adjustment, -0.18, 0.18)

        best_weights = base_weights
        best_error = starting_error
        for scale in (0.8, 0.4, 0.2, 0.1):
            candidate = np.clip(
                base_weights + adjustment * scale,
                0.0,
                max_target_weight,
            )
            set_weights(candidate)
            candidate_error = float(
                np.max(np.abs(measured_values() - target_values))
            )
            if candidate_error < best_error:
                best_weights = candidate
                best_error = candidate_error
                break
        set_weights(best_weights)
        history.append({
            "iteration": iteration + 1,
            "starting_max_error_cm": starting_error,
            "ending_max_error_cm": best_error,
            "accepted": best_error <= tolerance_cm,
        })
        if best_error >= starting_error - 1e-5:
            break
    return history


def target_measurement_specs(
    profile: dict[str, float],
) -> dict[str, tuple[float, tuple[str, ...]]]:
    def average(left: str, right: str) -> tuple[float | None, tuple[str, ...]]:
        keys = tuple(key for key in (left, right) if key in profile)
        values = [profile[key] for key in keys]
        return (sum(values) / len(values), keys) if values else (None, ())

    targets: dict[str, tuple[float, tuple[str, ...]]] = {}
    for profile_key, (measurement_name, scale) in PROFILE_TO_MPF_BASE.items():
        value = profile.get(profile_key)
        if value is not None:
            targets[measurement_name] = (value * scale, (profile_key,))
    arm_length = profile.get("arm_length")
    upper_arm_length, upper_arm_sources = average("shoulderElbowL", "shoulderElbowR")
    lower_arm_length, lower_arm_sources = average("elbowWristL", "elbowWristR")
    if upper_arm_length is not None:
        targets["upper_arm_length"] = (upper_arm_length, upper_arm_sources)
    if lower_arm_length is not None:
        targets["lower_arm_length"] = (lower_arm_length, lower_arm_sources)
    elif arm_length is not None:
        targets["lower_arm_length"] = (arm_length * 0.53, ("arm_length",))
    neck_height, neck_height_sources = average("neckLengthFront", "neckLengthBack")
    if neck_height is not None:
        targets["neck_height"] = (neck_height, neck_height_sources)
    upper_arm_circumference, upper_arm_circumference_sources = average(
        "upperArmCircL", "upperArmCircR"
    )
    if upper_arm_circumference is not None:
        targets["upper_arm_circumference"] = (
            upper_arm_circumference,
            upper_arm_circumference_sources,
        )
    across_front = profile.get("acrossFront")
    if across_front is not None:
        targets["front_chest_distance"] = (across_front, ("acrossFront",))
    upper_leg_length, upper_leg_sources = average("crotchKneeL", "crotchKneeR")
    if upper_leg_length is not None:
        targets["upper_leg_length"] = (upper_leg_length, upper_leg_sources)
    lower_leg_length, lower_leg_sources = average(
        "lowerLegLengthL", "lowerLegLengthR"
    )
    if lower_leg_length is not None:
        targets["lower_leg_length"] = (lower_leg_length, lower_leg_sources)
    knee, knee_sources = average("kneeCircL", "kneeCircR")
    if knee is not None:
        targets["knee_circumference"] = (knee, knee_sources)
    calf, calf_sources = average("calfCircL", "calfCircR")
    if calf is not None:
        targets["calf_circumference"] = (calf, calf_sources)
    ankle, ankle_sources = average("ankleCircL", "ankleCircR")
    if ankle is not None:
        targets["ankle_circumference"] = (ankle, ankle_sources)
    shoulder_width = profile.get("shoulder_w")
    neck_half_circumference = profile.get("neck_w")
    if shoulder_width is not None and neck_half_circumference is not None:
        neck_circumference = neck_half_circumference * 2.0
        neck_diameter = neck_circumference / math.pi
        targets["shoulder_distance"] = (
            (shoulder_width - neck_diameter) * 0.5,
            ("shoulder_w", "neck_w"),
        )
    return targets


def target_measurements(profile: dict[str, float]) -> dict[str, float]:
    return {
        name: value
        for name, (value, _) in target_measurement_specs(profile).items()
    }


def target_measurement_source_keys(
    profile: dict[str, float],
) -> dict[str, tuple[str, ...]]:
    return {
        name: source_keys
        for name, (_, source_keys) in target_measurement_specs(profile).items()
    }


def write_body_obj(
    basemesh: bpy.types.Object,
    output_path: Path,
    coordinates: list[Any] | None = None,
) -> tuple[int, int]:
    coordinates = coordinates or mixed_world_coordinates(basemesh)
    body_group = basemesh.vertex_groups.get("body")
    if body_group is None:
        raise RuntimeError("MPFB basemesh has no body vertex group.")
    body_group_index = body_group.index
    body_vertices = {
        vertex.index
        for vertex in basemesh.data.vertices
        if any(
            group.group == body_group_index and group.weight > 0.0
            for group in vertex.groups
        )
    }
    faces = [
        tuple(polygon.vertices)
        for polygon in basemesh.data.polygons
        if all(index in body_vertices for index in polygon.vertices)
    ]
    used_vertices = sorted({index for face in faces for index in face})
    remap = {old: new for new, old in enumerate(used_vertices, start=1)}
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8", newline="\n") as output_file:
        output_file.write("# Patterna measurement-fitted MPFB hm08 body\n")
        for index in used_vertices:
            coordinate = coordinates[index]
            output_file.write(f"v {coordinate.x:.9f} {coordinate.y:.9f} {coordinate.z:.9f}\n")
        for face in faces:
            output_file.write("f " + " ".join(str(remap[index]) for index in face) + "\n")
    return len(used_vertices), len(faces)


def write_textured_body_obj(
    basemesh: bpy.types.Object,
    output_path: Path,
    coordinates: list[Any],
) -> tuple[int, int, int]:
    """Write the fitted collider body with the original MakeHuman UV layout."""
    body_group = basemesh.vertex_groups.get("body")
    if body_group is None:
        raise RuntimeError("MPFB basemesh has no body vertex group.")
    body_group_index = body_group.index
    body_vertices = {
        vertex.index
        for vertex in basemesh.data.vertices
        if any(
            group.group == body_group_index and group.weight > 0.0
            for group in vertex.groups
        )
    }
    polygons = [
        polygon
        for polygon in basemesh.data.polygons
        if all(index in body_vertices for index in polygon.vertices)
    ]
    used_vertices = sorted(
        {index for polygon in polygons for index in polygon.vertices}
    )
    remap = {old: new for new, old in enumerate(used_vertices, start=1)}
    uv_layer = basemesh.data.uv_layers.active
    if uv_layer is None:
        raise RuntimeError("MPFB basemesh has no active UV map.")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    uv_count = sum(len(polygon.loop_indices) for polygon in polygons)
    with output_path.open("w", encoding="utf-8", newline="\n") as output_file:
        output_file.write("# Patterna fitted MakeHuman display body with UVs\n")
        for index in used_vertices:
            coordinate = coordinates[index]
            output_file.write(
                f"v {coordinate.x:.9f} {coordinate.y:.9f} {coordinate.z:.9f}\n"
            )
        for polygon in polygons:
            for loop_index in polygon.loop_indices:
                uv = uv_layer.data[loop_index].uv
                output_file.write(f"vt {uv.x:.9f} {uv.y:.9f}\n")
        next_uv = 1
        for polygon in polygons:
            corners = []
            for vertex_index in polygon.vertices:
                corners.append(f"{remap[vertex_index]}/{next_uv}")
                next_uv += 1
            output_file.write("f " + " ".join(corners) + "\n")
    return len(used_vertices), len(polygons), uv_count


def write_bra_shell_obj(
    basemesh: bpy.types.Object,
    output_path: Path,
    coordinates: list[Any],
    *,
    invert_output_y: bool = False,
    surface_offset_m: float = BRA_DISPLAY_SURFACE_OFFSET_M,
    strap_offset_m: float = BRA_DISPLAY_STRAP_OFFSET_M,
    maximum_torso_half_width_m: float | None = None,
) -> tuple[int, int, int]:
    """Write a smooth optional sports-bra shell fitted to the collision body."""
    body_group = basemesh.vertex_groups.get("body")
    if body_group is None:
        raise RuntimeError("MPFB basemesh has no body vertex group.")
    body_group_index = body_group.index
    body_vertices = {
        vertex.index
        for vertex in basemesh.data.vertices
        if any(
            group.group == body_group_index and group.weight > 0.0
            for group in vertex.groups
        )
    }
    body_z = [float(coordinates[index].z) for index in body_vertices]
    floor_z = min(body_z)
    height = max(body_z) - floor_z

    body_faces = [
        tuple(polygon.vertices)
        for polygon in basemesh.data.polygons
        if all(index in body_vertices for index in polygon.vertices)
        and (
            maximum_torso_half_width_m is None
            or all(
                abs(float(coordinates[index].x)) <= maximum_torso_half_width_m
                for index in polygon.vertices
            )
        )
    ]
    surface = BVHTree.FromPolygons(coordinates, body_faces, all_triangles=False)

    shell_vertices: list[Vector] = []
    shell_uvs: list[tuple[float, float]] = []
    shell_faces: list[tuple[int, int, int, int]] = []

    def fitted_point(
        theta: float,
        z_ratio: float,
        offset: float = surface_offset_m,
    ) -> Vector:
        direction = Vector((math.sin(theta), math.cos(theta), 0.0))
        origin = Vector((0.0, 0.0, floor_z + z_ratio * height))
        # Always cast inward from outside the body. A large supported bust is
        # concave at the inframammary fold, so an origin-outward ray can select
        # an inner fold wall and put the display bra behind the breast surface.
        exterior = origin + direction * 1.0
        location, normal, _face_index, _distance = surface.ray_cast(
            exterior,
            -direction,
            2.0,
        )
        if location is None or normal is None:
            raise RuntimeError(
                f"Could not fit bra shell at theta={theta:.4f}, z={z_ratio:.4f}."
            )
        if normal.dot(direction) < 0.0:
            normal.negate()
        normal.normalize()
        return location + normal * offset

    angular_segments = 96
    vertical_segments = 18
    lower_ratio = 0.676
    for angular_index in range(angular_segments):
        theta = 2.0 * math.pi * angular_index / angular_segments
        frontness = max(math.cos(theta), 0.0)
        cup_peak = math.exp(-((abs(math.sin(theta)) - 0.34) / 0.22) ** 2)
        upper_ratio = 0.748 + 0.024 * frontness + 0.030 * frontness * cup_peak
        for vertical_index in range(vertical_segments + 1):
            vertical_fraction = vertical_index / vertical_segments
            z_ratio = lower_ratio + (upper_ratio - lower_ratio) * vertical_fraction
            shell_vertices.append(fitted_point(theta, z_ratio))
            shell_uvs.append(
                (angular_index / angular_segments, vertical_fraction)
            )

    ring_stride = vertical_segments + 1
    for angular_index in range(angular_segments):
        next_angular = (angular_index + 1) % angular_segments
        for vertical_index in range(vertical_segments):
            shell_faces.append((
                angular_index * ring_stride + vertical_index,
                next_angular * ring_stride + vertical_index,
                next_angular * ring_stride + vertical_index + 1,
                angular_index * ring_stride + vertical_index + 1,
            ))

    # Wide, body-fitted straps complete the sports-bra silhouette without
    # changing the underlying supported bust or collision surface.
    strap_segments = 40
    strap_half_width = 0.040
    for side in (-1.0, 1.0):
        strap_start = len(shell_vertices)
        for path_index in range(strap_segments + 1):
            fraction = path_index / strap_segments
            front_theta = side * 0.36
            back_theta = side * (math.pi - 0.36)
            theta = front_theta + (back_theta - front_theta) * fraction
            endpoint_height = 0.790 * (1.0 - fraction) + 0.756 * fraction
            z_ratio = endpoint_height + 0.078 * math.sin(math.pi * fraction)
            for edge_index, edge_offset in enumerate((-strap_half_width, strap_half_width)):
                shell_vertices.append(
                    fitted_point(theta + edge_offset, z_ratio, strap_offset_m)
                )
                shell_uvs.append((float(edge_index), fraction))
        for path_index in range(strap_segments):
            row = strap_start + path_index * 2
            next_row = row + 2
            shell_faces.append((row, next_row, next_row + 1, row + 1))

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8", newline="\n") as output_file:
        output_file.write("# Patterna optional fitted sports-bra display shell\n")
        for coordinate in shell_vertices:
            output_y = -coordinate.y if invert_output_y else coordinate.y
            output_file.write(
                f"v {coordinate.x:.9f} {output_y:.9f} {coordinate.z:.9f}\n"
            )
        for u, v in shell_uvs:
            output_file.write(f"vt {u:.9f} {v:.9f}\n")
        for face in shell_faces:
            output_file.write(
                "f "
                + " ".join(f"{index + 1}/{index + 1}" for index in face)
                + "\n"
            )
    return len(shell_vertices), len(shell_faces), len(shell_uvs)


def write_solid_texture(
    output_path: Path,
    rgba: tuple[float, float, float, float],
) -> None:
    image = bpy.data.images.new("PatternaBraTexture", width=4, height=4, alpha=True)
    try:
        image.pixels = list(rgba) * 16
        image.filepath_raw = str(output_path)
        image.file_format = "PNG"
        image.save()
    finally:
        bpy.data.images.remove(image)


def write_textured_mesh_obj(
    mesh_object: bpy.types.Object,
    output_path: Path,
    upper_components_only: bool = False,
) -> tuple[int, int, int]:
    """Write a fitted MHCLO mesh in world coordinates with UVs preserved."""
    depsgraph = bpy.context.evaluated_depsgraph_get()
    depsgraph.update()
    evaluated = mesh_object.evaluated_get(depsgraph)
    mesh = evaluated.to_mesh()
    try:
        uv_layer = mesh.uv_layers.active
        if uv_layer is None:
            raise RuntimeError(f"Asset {mesh_object.name} has no active UV map.")
        matrix = evaluated.matrix_world
        polygons = list(mesh.polygons)
        if upper_components_only:
            adjacency: list[set[int]] = [set() for _ in mesh.vertices]
            for polygon in polygons:
                polygon_vertices = list(polygon.vertices)
                for index, vertex_id in enumerate(polygon_vertices):
                    adjacency[vertex_id].add(polygon_vertices[(index + 1) % len(polygon_vertices)])
                    adjacency[polygon_vertices[(index + 1) % len(polygon_vertices)]].add(vertex_id)
            component_ids = [-1] * len(mesh.vertices)
            component_vertices: list[list[int]] = []
            for seed in range(len(mesh.vertices)):
                if component_ids[seed] >= 0:
                    continue
                component_id = len(component_vertices)
                stack = [seed]
                component_ids[seed] = component_id
                vertices: list[int] = []
                while stack:
                    vertex_id = stack.pop()
                    vertices.append(vertex_id)
                    for neighbor in adjacency[vertex_id]:
                        if component_ids[neighbor] < 0:
                            component_ids[neighbor] = component_id
                            stack.append(neighbor)
                component_vertices.append(vertices)
            world_z = [float((matrix @ vertex.co).z) for vertex in mesh.vertices]
            minimum_z = min(world_z)
            maximum_z = max(world_z)
            upper_center_cutoff = minimum_z + (maximum_z - minimum_z) * 0.57
            upper_components = {
                component_id
                for component_id, vertices in enumerate(component_vertices)
                if sum(world_z[index] for index in vertices) / len(vertices)
                >= upper_center_cutoff
            }
            polygons = [
                polygon
                for polygon in polygons
                if component_ids[polygon.vertices[0]] in upper_components
            ]
            if not polygons:
                raise RuntimeError(f"Could not isolate the upper garment in {mesh_object.name}.")

        used_vertex_ids = sorted(
            {vertex_id for polygon in polygons for vertex_id in polygon.vertices}
        )
        vertex_remap = {
            vertex_id: index + 1
            for index, vertex_id in enumerate(used_vertex_ids)
        }
        output_path.parent.mkdir(parents=True, exist_ok=True)
        uv_count = sum(len(polygon.loop_indices) for polygon in polygons)
        with output_path.open("w", encoding="utf-8", newline="\n") as output_file:
            output_file.write(f"# Patterna fitted display asset: {mesh_object.name}\n")
            for vertex_id in used_vertex_ids:
                vertex = mesh.vertices[vertex_id]
                coordinate = matrix @ vertex.co
                output_file.write(
                    f"v {coordinate.x:.9f} {coordinate.y:.9f} {coordinate.z:.9f}\n"
                )
            for polygon in polygons:
                for loop_index in polygon.loop_indices:
                    uv = uv_layer.data[loop_index].uv
                    output_file.write(f"vt {uv.x:.9f} {uv.y:.9f}\n")
            next_uv = 1
            for polygon in polygons:
                corners = []
                for vertex_index in polygon.vertices:
                    corners.append(f"{vertex_remap[vertex_index]}/{next_uv}")
                    next_uv += 1
                output_file.write("f " + " ".join(corners) + "\n")
        return len(used_vertex_ids), len(polygons), uv_count
    finally:
        evaluated.to_mesh_clear()


def build_display_avatar(
    basemesh: bpy.types.Object,
    coordinates: list[Any],
    asset_root: Path,
    output_dir: Path,
    hair_style: str,
) -> dict[str, Any]:
    """Build the visual avatar while keeping the collision body unchanged."""
    if not asset_root.is_dir():
        raise FileNotFoundError(f"MakeHuman render asset root not found: {asset_root}")

    output_dir.mkdir(parents=True, exist_ok=True)
    body_group = basemesh.vertex_groups.get("body")
    if body_group is None:
        raise RuntimeError("MPFB basemesh has no body vertex group.")
    body_group_index = body_group.index
    body_vertex_ids = [
        vertex.index
        for vertex in basemesh.data.vertices
        if any(
            group.group == body_group_index and group.weight > 0.0
            for group in vertex.groups
        )
    ]
    floor_offset_m = min(float(coordinates[index].z) for index in body_vertex_ids)
    body_geometry = write_textured_body_obj(
        basemesh,
        output_dir / "body.obj",
        coordinates,
    )

    hair_directory = asset_root / "hair" / hair_style
    hair_material_path = hair_directory / f"{hair_style}.mhmat"
    if not hair_material_path.is_file():
        raise FileNotFoundError(f"Missing MakeHuman hair material: {hair_material_path}")
    diffuse_texture_name = next(
        (
            line.split(maxsplit=1)[1].strip()
            for line in hair_material_path.read_text(encoding="utf-8").splitlines()
            if line.strip().startswith("diffuseTexture ")
        ),
        None,
    )
    if not diffuse_texture_name:
        raise ValueError(
            f"MakeHuman hair material has no diffuseTexture entry: {hair_material_path}"
        )

    asset_definitions = [
        (
            "eyes",
            "Eyes",
            asset_root / "eyes" / "high-poly" / "high-poly.mhclo",
            asset_root / "eyes" / "materials" / "brown_eye.png",
        ),
        (
            "teeth",
            "Teeth",
            asset_root / "teeth" / "teeth_base" / "teeth_base.mhclo",
            asset_root / "teeth" / "teeth_base" / "teeth.png",
        ),
        (
            "eyebrows",
            "Eyebrows",
            asset_root / "eyebrows" / "eyebrow001" / "eyebrow001.mhclo",
            asset_root / "eyebrows" / "eyebrow001" / "eyebrow001.png",
        ),
        (
            "eyelashes",
            "Eyelashes",
            asset_root / "eyelashes" / "eyelashes01" / "eyelashes01.mhclo",
            asset_root / "eyelashes" / "eyelashes01" / "eyelashes01.png",
        ),
        (
            "hair",
            "Hair",
            hair_directory / f"{hair_style}.mhclo",
            hair_directory / diffuse_texture_name,
        ),
    ]

    copied_textures = {
        "body": asset_root
        / "skins"
        / "young_african_female"
        / "young_darkskinned_female_diffuse.png"
    }
    generated_assets: dict[str, Any] = {
        "body": {
            "geometry": "body.obj",
            "texture": "body.png",
            "vertex_count": body_geometry[0],
            "face_count": body_geometry[1],
            "uv_count": body_geometry[2],
        }
    }
    bra_geometry = write_bra_shell_obj(
        basemesh,
        output_dir / "bra.obj",
        coordinates,
    )
    write_solid_texture(output_dir / "bra.png", (0.018, 0.035, 0.055, 1.0))
    generated_assets["bra"] = {
        "geometry": "bra.obj",
        "texture": "bra.png",
        "vertex_count": bra_geometry[0],
        "face_count": bra_geometry[1],
        "uv_count": bra_geometry[2],
        "display_optional": True,
        "maximum_surface_offset_m": BRA_DISPLAY_STRAP_OFFSET_M,
    }

    for key, asset_type, mhclo_path, texture_path in asset_definitions:
        if not mhclo_path.is_file() or not texture_path.is_file():
            raise FileNotFoundError(f"Missing MakeHuman {key} source asset.")
        fitted_object = HumanService.add_mhclo_asset(
            str(mhclo_path),
            basemesh,
            asset_type=asset_type,
            subdiv_levels=0,
            material_type="GAMEENGINE",
            set_up_rigging=False,
            interpolate_weights=False,
            import_subrig=False,
            import_weights=False,
        )
        geometry = write_textured_mesh_obj(
            fitted_object,
            output_dir / f"{key}.obj",
        )
        copied_textures[key] = texture_path
        generated_assets[key] = {
            "geometry": f"{key}.obj",
            "texture": f"{key}.png",
            "vertex_count": geometry[0],
            "face_count": geometry[1],
            "uv_count": geometry[2],
        }

    garment_source = asset_root / "clothes" / "female_casualsuit02"
    garment_mhclo = garment_source / "female_casualsuit02.mhclo"
    garment_texture = garment_source / "female_casualsuit02_diffuse.png"
    if not garment_mhclo.is_file() or not garment_texture.is_file():
        raise FileNotFoundError("Missing MakeHuman female casual top source asset.")
    fitted_garment = HumanService.add_mhclo_asset(
        str(garment_mhclo),
        basemesh,
        asset_type="Clothes",
        subdiv_levels=1,
        material_type="GAMEENGINE",
        set_up_rigging=False,
        interpolate_weights=False,
        import_subrig=False,
        import_weights=False,
    )
    garment_geometry = write_textured_mesh_obj(
        fitted_garment,
        output_dir / "garment.obj",
        upper_components_only=True,
    )
    copied_textures["garment"] = garment_texture
    default_garment = {
        "geometry": "garment.obj",
        "texture": "garment.png",
        "vertex_count": garment_geometry[0],
        "face_count": garment_geometry[1],
        "uv_count": garment_geometry[2],
        "source": "female_casualsuit02 upper components",
    }

    for key, source_texture in copied_textures.items():
        if not source_texture.is_file():
            raise FileNotFoundError(f"Missing MakeHuman {key} texture: {source_texture}")
        shutil.copy2(source_texture, output_dir / f"{key}.png")

    manifest = {
        "schema_version": "patterna.display-avatar/1.0",
        "source": "MakeHuman Community system assets",
        "license": "CC0",
        "floor_offset_m": floor_offset_m,
        "collision_geometry": "../patterna-mpfb-female.obj",
        "hair_style": hair_style,
        "assets": generated_assets,
        "default_garment": default_garment,
    }
    (output_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n",
        encoding="utf-8",
    )
    return manifest


def git_head(path: Path) -> str:
    packaged_revisions = REPO_ROOT / "runtime-source-revisions.json"
    if packaged_revisions.exists():
        revisions = json.loads(packaged_revisions.read_text(encoding="utf-8"))
        packaged_revision = revisions.get(path.name)
        if (
            isinstance(packaged_revision, str)
            and len(packaged_revision) == 40
            and all(character in "0123456789abcdefABCDEF" for character in packaged_revision)
        ):
            return packaged_revision.lower()
    completed = subprocess.run(
        ["git", "-C", str(path), "rev-parse", "HEAD"],
        check=False,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    revision = completed.stdout.strip()
    if (
        completed.returncode != 0
        or len(revision) != 40
        or any(character not in "0123456789abcdefABCDEF" for character in revision)
    ):
        detail = completed.stderr.strip() or "no Git revision was returned"
        raise RuntimeError(
            f"Missing packaged source revision for {path.name}: {detail}"
        )
    return revision.lower()


def main() -> None:
    global HumanObjectProperties, HumanService, TargetService

    args = parse_args()
    if args.max_target_weight <= 0.0 or args.fit_passes <= 0:
        raise ValueError("Fit limits must be positive.")
    profile_path = resolve(args.profile)
    output_path = resolve(args.output)
    report_path = output_path.with_suffix(".fit-report.json")
    (
        internal_body_values,
        user_measurements,
        measurement_origins,
        measurement_sources,
    ) = profile_sections(profile_path)
    profile = dict(internal_body_values)
    profile.update(user_measurements)

    if MPFB_MODULE_NAME not in bpy.context.preferences.addons:
        raise RuntimeError(
            "MPFB is not enabled in Blender's user_default extension repository."
        )
    mpfb = importlib.import_module(MPFB_MODULE_NAME)
    properties_api = importlib.import_module(
        f"{MPFB_MODULE_NAME}.entities.objectproperties"
    ).HumanObjectProperties
    human_service_api = importlib.import_module(
        f"{MPFB_MODULE_NAME}.services.humanservice"
    ).HumanService
    target_service_api = importlib.import_module(
        f"{MPFB_MODULE_NAME}.services.targetservice"
    ).TargetService

    HumanObjectProperties = properties_api
    HumanService = human_service_api
    TargetService = target_service_api
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)

    macro = TargetService.get_default_macro_info_dict()
    macro["gender"] = FEMALE_GENDER_MACRO
    macro_control_values = macro_controls(profile)
    macro.update(macro_control_values)
    basemesh = HumanService.create_human(
        mask_helpers=False,
        detailed_helpers=True,
        extra_vertex_groups=True,
        feet_on_ground=True,
        scale=0.1,
        macro_detail_dict=macro,
    )
    basemesh.name = "PatternaMeasurementAvatar"

    height_result = None
    if "height" in profile:
        height_result = set_height(
            basemesh,
            profile["height"],
            args.tolerance_cm,
        )

    detail_morph_results = apply_detail_morph_controls(basemesh, profile)
    internal_fit_tolerance = min(args.tolerance_cm * 0.1, 0.02)

    requested_measurements = target_measurements(profile)
    requested_measurement_sources = target_measurement_source_keys(profile)
    fit_results: dict[str, Any] = {}
    for _ in range(args.fit_passes):
        for measurement_name, desired_cm in requested_measurements.items():
            fit_results[measurement_name] = fit_direct_measurement(
                basemesh,
                measurement_name,
                desired_cm,
                args.max_target_weight,
                internal_fit_tolerance,
            )
        if "height" in profile:
            height_result = set_height(
                basemesh,
                profile["height"],
                internal_fit_tolerance,
            )

    coupled_refinement = refine_coupled_direct_measurements(
        basemesh,
        profile,
        requested_measurements,
        fit_results,
        args.max_target_weight,
        args.tolerance_cm,
    )

    # Local surface and posture controls can perturb a hard ruler. Compensate
    # against the undeformed MPFB ruler target, except where a closed collision
    # surface is the measurement authority. Open MPFB bust chains remain useful
    # morph controls but must not fight the actual body tape circumference.
    local_compensation: list[dict[str, Any]] = []
    for pass_index in range(12):
        raw_coordinates = mixed_world_coordinates(basemesh)
        deformed_coordinates, _ = deformed_world_coordinates(basemesh, profile)
        compensated_targets: dict[str, float] = {}
        for measurement_name, desired_cm in requested_measurements.items():
            if measurement_name in SURFACE_AUTHORITATIVE_RULERS:
                continue
            raw_cm = ruler_measurement_cm(raw_coordinates, measurement_name)
            deformed_cm = ruler_measurement_cm(deformed_coordinates, measurement_name)
            compensated_targets[measurement_name] = desired_cm - (deformed_cm - raw_cm)
        for measurement_name, compensated_cm in compensated_targets.items():
            fit_direct_measurement(
                basemesh,
                measurement_name,
                compensated_cm,
                args.max_target_weight,
                internal_fit_tolerance,
            )
        if "height" in profile:
            raw_height = avatar_height_cm(mixed_world_coordinates(basemesh))
            deformed_height = avatar_height_cm(
                deformed_world_coordinates(
                    basemesh,
                    profile,
                    apply_surface_constraints=False,
                )[0]
            )
            set_height(
                basemesh,
                profile["height"] - (deformed_height - raw_height),
                args.tolerance_cm,
            )
        compensated_coordinates, _ = deformed_world_coordinates(basemesh, profile)
        compensated_errors = {
            measurement_name: abs(
                ruler_measurement_cm(compensated_coordinates, measurement_name)
                - desired_cm
            )
            for measurement_name, desired_cm in requested_measurements.items()
            if measurement_name not in SURFACE_AUTHORITATIVE_RULERS
        }
        local_compensation.append({
            "pass": pass_index + 1,
            "compensated_targets_cm": compensated_targets,
            "maximum_direct_ruler_error_cm": max(compensated_errors.values(), default=0.0),
        })
        if all(error <= args.tolerance_cm for error in compensated_errors.values()):
            break

    coordinates, deformation_evidence = deformed_world_coordinates(basemesh, profile)
    if height_result is not None:
        height_result["measured_cm"] = avatar_height_cm(coordinates)
    final_measurements = {
        name: ruler_measurement_cm(coordinates, name)
        for name in requested_measurements
    }
    if deformation_evidence.underbust_surface is not None:
        final_measurements["underbust_circumference"] = (
            deformation_evidence.underbust_surface.length_after_cm
        )
    if deformation_evidence.bust_surface is not None:
        final_measurements["bust_circumference"] = (
            deformation_evidence.bust_surface.circumference_after_cm
        )
    vertex_count, face_count = write_body_obj(basemesh, output_path, coordinates)
    display_avatar = (
        build_display_avatar(
            basemesh,
            coordinates,
            resolve(args.render_asset_root),
            resolve(args.render_output_dir),
            args.hair_style,
        )
        if args.render_output_dir is not None
        else None
    )
    profile_hash = hashlib.sha256(profile_path.read_bytes()).hexdigest()
    output_hash = hashlib.sha256(output_path.read_bytes()).hexdigest()
    z_values = [coordinate.z for coordinate in coordinates[:13380]]
    x_values = [coordinate.x for coordinate in coordinates[:13380]]
    y_values = [coordinate.y for coordinate in coordinates[:13380]]
    direct_source_keys = set(DIRECT_RULER_SOURCE_KEYS)
    approximate_source_keys = mapped_measurement_keys()
    local_source_keys = local_deformation_keys()
    mapped_source_keys = direct_source_keys | approximate_source_keys | local_source_keys
    fit_acceptance = evaluate_fit_acceptance(
        requested_measurements=requested_measurements,
        final_measurements=final_measurements,
        fit_results=fit_results,
        tolerance_cm=args.tolerance_cm,
        target_source_keys=requested_measurement_sources,
        measurement_sources=measurement_sources,
        measurement_origins=measurement_origins,
        height_result=height_result,
    )
    report = {
        "schema_version": "patterna.mpfb-avatar-fit/1.3",
        "source_profile": str(profile_path),
        "source_profile_sha256": profile_hash,
        "output_body": str(output_path),
        "output_body_sha256": output_hash,
        "mpfb_version": list(mpfb.VERSION),
        "mpfb_commit": git_head(REPO_ROOT / "third_party" / "MPFB2"),
        "blender_version": bpy.app.version_string,
        "gender": "female",
        "gender_macro": FEMALE_GENDER_MACRO,
        "vertex_count": vertex_count,
        "face_count": face_count,
        "display_avatar": display_avatar,
        "bounds_m": [
            [min(x_values), min(y_values), min(z_values)],
            [max(x_values), max(y_values), max(z_values)],
        ],
        "height": height_result,
        "macro_controls": macro_control_values,
        "detail_morph_controls": detail_morph_results,
        "local_deformation_controls": [
            asdict(result)
            for result in deformation_evidence.local
        ],
        "surface_constraints": {
            "waist_to_underbust": (
                asdict(deformation_evidence.waist_surface)
                if deformation_evidence.waist_surface is not None
                else None
            ),
            "underbust_circumference": (
                asdict(deformation_evidence.underbust_surface)
                if deformation_evidence.underbust_surface is not None
                else None
            ),
            "bust_circumference": (
                asdict(deformation_evidence.bust_surface)
                if deformation_evidence.bust_surface is not None
                else None
            ),
            "bust_to_high_chest": (
                asdict(deformation_evidence.high_chest_surface)
                if deformation_evidence.high_chest_surface is not None
                else None
            ),
        },
        "measurement_authority": {
            "bust_circumference": "closed-collision-surface-tape",
            "underbust_circumference": (
                "nonhorizontal-inframammary-landmark-tape"
            ),
            "high_chest_circumference": (
                "high-bust-tape-morph-control-not-closed-horizontal-surface"
            ),
            "other_direct_measurements": "mpfb-landmark-ruler",
        },
        "local_ruler_compensation": local_compensation,
        "coupled_ruler_refinement": coupled_refinement,
        "measurement_coverage": {
            "user_measurement_key_count": len(user_measurements),
            "internal_body_alias_keys": sorted(internal_body_values),
            "direct_ruler_source_keys": sorted(set(user_measurements) & direct_source_keys),
            "approximate_morph_source_keys": sorted(set(user_measurements) & approximate_source_keys),
            "local_deformation_source_keys": sorted(set(user_measurements) & local_source_keys),
            "mapped_source_key_count": len(set(user_measurements) & mapped_source_keys),
            "unmapped_source_keys": sorted(set(user_measurements) - mapped_source_keys),
            "measurement_origin_count": len(measurement_origins),
        },
        "fit_passes": args.fit_passes,
        "fit_tolerance_cm": args.tolerance_cm,
        "fit_results": fit_results,
        "final_measurements_cm": final_measurements,
        "fit_acceptance": fit_acceptance,
        "accepted": (
            fit_acceptance["accepted"]
            and (
                deformation_evidence.waist_surface is None
                or deformation_evidence.waist_surface.accepted
            )
            and (
                deformation_evidence.underbust_surface is None
                or deformation_evidence.underbust_surface.accepted
            )
            and (
                deformation_evidence.bust_surface is None
                or deformation_evidence.bust_surface.accepted
            )
            and (
                deformation_evidence.high_chest_surface is None
                or deformation_evidence.high_chest_surface.accepted
            )
        ),
    }
    report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    if not report["accepted"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
