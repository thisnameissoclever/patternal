#!/usr/bin/env python3
"""Build and verify a rigged MHR display-avatar candidate in Blender."""

from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
import math
from pathlib import Path
import shutil
import sys
from typing import Any

import bpy
from mathutils import Vector
import numpy as np


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools.charmorph_anatomy import evaluate_avatar_anatomy
from tools.charmorph_pose import evaluate_avatar_pose


EXPECTED_VERTEX_COUNT = 18439
EXPECTED_TRIANGLE_COUNT = 36874
EXPECTED_JOINT_COUNT = 127
RIG_ALIGNMENT_LIMIT_M = 0.00001


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-fbx", type=Path, required=True)
    parser.add_argument("--fitted-obj", type=Path, required=True)
    parser.add_argument("--fit-report", type=Path, required=True)
    parser.add_argument("--rig-state", type=Path, required=True)
    parser.add_argument("--source-license", type=Path, required=True)
    parser.add_argument("--hair-obj", type=Path, required=True)
    parser.add_argument("--hair-texture", type=Path, required=True)
    parser.add_argument("--hair-style", required=True)
    parser.add_argument("--output-directory", type=Path, required=True)
    argv = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    return parser.parse_args(argv)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_obj(path: Path) -> tuple[np.ndarray, list[tuple[int, ...]]]:
    vertices: list[tuple[float, float, float]] = []
    faces: list[tuple[int, ...]] = []
    with path.open("r", encoding="utf-8") as source:
        for line in source:
            if line.startswith("v "):
                values = line.split()
                vertices.append(tuple(float(value) for value in values[1:4]))
            elif line.startswith("f "):
                faces.append(
                    tuple(int(token.split("/", 1)[0]) - 1 for token in line.split()[1:])
                )
    result = np.asarray(vertices, dtype=np.float64)
    if result.shape != (EXPECTED_VERTEX_COUNT, 3):
        raise ValueError(f"MHR fitted OBJ has unexpected vertex shape {result.shape}.")
    if len(faces) != EXPECTED_TRIANGLE_COUNT or any(len(face) != 3 for face in faces):
        raise ValueError("MHR fitted OBJ does not contain the expected triangle topology.")
    if not np.isfinite(result).all():
        raise ValueError("MHR fitted OBJ contains a non-finite coordinate.")
    return result, faces


def clear_scene() -> None:
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)
    for datablocks in (
        bpy.data.meshes,
        bpy.data.curves,
        bpy.data.materials,
        bpy.data.cameras,
        bpy.data.lights,
    ):
        for datablock in list(datablocks):
            if datablock.users == 0:
                datablocks.remove(datablock)


def find_source_objects() -> tuple[bpy.types.Object, bpy.types.Object]:
    meshes = [
        obj
        for obj in bpy.context.scene.objects
        if obj.type == "MESH" and len(obj.data.vertices) == EXPECTED_VERTEX_COUNT
    ]
    armatures = [obj for obj in bpy.context.scene.objects if obj.type == "ARMATURE"]
    if len(meshes) != 1 or len(armatures) != 1:
        raise ValueError(
            f"MHR FBX must contain one {EXPECTED_VERTEX_COUNT}-vertex body and one armature."
        )
    return meshes[0], armatures[0]


def body_world_vertices(body: bpy.types.Object) -> np.ndarray:
    return np.asarray(
        [tuple(body.matrix_world @ vertex.co) for vertex in body.data.vertices],
        dtype=np.float64,
    )


def replace_body_vertices(body: bpy.types.Object, target: np.ndarray) -> float:
    if body.data.shape_keys is not None:
        body.shape_key_clear()
    inverse = body.matrix_world.inverted()
    for vertex, coordinate in zip(body.data.vertices, target, strict=True):
        vertex.co = inverse @ Vector(coordinate)
    body.data.update()
    actual = body_world_vertices(body)
    return float(np.max(np.linalg.norm(actual - target, axis=1)))


def fit_armature_rest_pose(
    armature: bpy.types.Object,
    ratio: float,
    rig_state: dict[str, Any],
) -> None:
    states = rig_state.get("jointStates")
    if not isinstance(states, list) or len(states) != EXPECTED_JOINT_COUNT:
        raise ValueError("MHR rig-state evidence does not contain 127 joints.")
    target_heads = {
        bone.name: armature.matrix_world.inverted() @ mhr_to_blender(states[index + 1][:3])
        for index, bone in enumerate(armature.data.bones)
    }
    bpy.context.view_layer.objects.active = armature
    armature.select_set(True)
    bpy.ops.object.mode_set(mode="EDIT")
    for bone in armature.data.edit_bones:
        rest_vector = (bone.tail - bone.head) * ratio
        bone.head = target_heads[bone.name]
        bone.tail = bone.head + rest_vector
    bpy.ops.object.mode_set(mode="OBJECT")


def mhr_to_blender(point_cm: list[float]) -> Vector:
    return Vector((point_cm[0] / 100.0, -point_cm[2] / 100.0, point_cm[1] / 100.0))


def verify_rig(
    body: bpy.types.Object,
    armature: bpy.types.Object,
    rig_state: dict[str, Any],
) -> dict[str, Any]:
    states = rig_state.get("jointStates")
    if not isinstance(states, list) or len(states) != EXPECTED_JOINT_COUNT:
        raise ValueError("MHR rig-state evidence does not contain 127 joints.")
    bones = list(armature.data.bones)
    if len(bones) != EXPECTED_JOINT_COUNT - 1:
        raise ValueError(f"MHR FBX contains {len(bones)} bones instead of 126.")
    errors = [
        float((armature.matrix_world @ bone.head_local - mhr_to_blender(states[index + 1][:3])).length)
        for index, bone in enumerate(bones)
    ]
    weight_sums: list[float] = []
    influence_counts: list[int] = []
    for vertex in body.data.vertices:
        weights = [group.weight for group in vertex.groups if group.weight > 0.0]
        weight_sums.append(sum(weights))
        influence_counts.append(len(weights))
    unweighted = sum(count == 0 for count in influence_counts)
    maximum_error = max(errors)
    accepted = (
        maximum_error <= RIG_ALIGNMENT_LIMIT_M
        and unweighted == 0
        and min(weight_sums) >= 0.999
        and max(weight_sums) <= 1.001
    )
    return {
        "schemaVersion": "patterna.mhr-rig-export/1.0",
        "accepted": accepted,
        "boneCount": len(bones),
        "vertexGroupCount": len(body.vertex_groups),
        "unweightedVertexCount": unweighted,
        "minimumWeightSum": min(weight_sums),
        "maximumWeightSum": max(weight_sums),
        "maximumInfluencesPerVertex": max(influence_counts),
        "maximumJointHeadErrorM": maximum_error,
        "jointHeadErrorLimitM": RIG_ALIGNMENT_LIMIT_M,
        "mapping": "joint state 0 is body_world; FBX bone order maps to joint states 1 through 126",
        "limitations": [
            "the exported GLB retains linear skinning but does not embed MHR pose-corrective inference",
            "the local measurement correction changes surface sections around the MHR rig and does not introduce new joint translations",
        ],
    }


def configure_material(
    name: str,
    color: tuple[float, float, float, float],
    *,
    roughness: float,
    texture: Path | None = None,
    alpha: bool = False,
) -> bpy.types.Material:
    material = bpy.data.materials.new(name)
    material.use_nodes = True
    nodes = material.node_tree.nodes
    links = material.node_tree.links
    nodes.clear()
    output = nodes.new("ShaderNodeOutputMaterial")
    principled = nodes.new("ShaderNodeBsdfPrincipled")
    principled.inputs["Base Color"].default_value = color
    principled.inputs["Roughness"].default_value = roughness
    if "Subsurface Weight" in principled.inputs and name == "Patterna MHR skin":
        principled.inputs["Subsurface Weight"].default_value = 0.08
    links.new(principled.outputs["BSDF"], output.inputs["Surface"])
    if texture is not None:
        image = bpy.data.images.load(str(texture), check_existing=True)
        image.colorspace_settings.name = "sRGB"
        image_node = nodes.new("ShaderNodeTexImage")
        image_node.image = image
        links.new(image_node.outputs["Color"], principled.inputs["Base Color"])
        if alpha:
            links.new(image_node.outputs["Alpha"], principled.inputs["Alpha"])
            material.surface_render_method = "DITHERED"
    material.diffuse_color = color
    return material


def assign_material(obj: bpy.types.Object, material: bpy.types.Material) -> None:
    obj.data.materials.clear()
    obj.data.materials.append(material)
    for polygon in obj.data.polygons:
        polygon.material_index = 0


def import_obj_component(path: Path, name: str) -> bpy.types.Object:
    before = set(bpy.context.scene.objects)
    bpy.ops.wm.obj_import(
        filepath=str(path),
        forward_axis="Y",
        up_axis="Z",
    )
    imported = [obj for obj in bpy.context.scene.objects if obj not in before and obj.type == "MESH"]
    if len(imported) != 1:
        raise ValueError(f"Expected one mesh in {path}, found {len(imported)}.")
    imported[0].name = name
    imported[0].data.name = f"{name}Mesh"
    return imported[0]


def build_eye_components(armature: bpy.types.Object) -> list[bpy.types.Object]:
    sclera_material = configure_material(
        "Patterna MHR sclera",
        (0.82, 0.80, 0.74, 1.0),
        roughness=0.24,
    )
    iris_material = configure_material(
        "Patterna MHR iris",
        (0.16, 0.055, 0.018, 1.0),
        roughness=0.32,
    )
    pupil_material = configure_material(
        "Patterna MHR pupil",
        (0.004, 0.003, 0.002, 1.0),
        roughness=0.18,
    )
    components: list[bpy.types.Object] = []
    for side_name, bone_name in (("Left", "l_eye"), ("Right", "r_eye")):
        center = armature.matrix_world @ armature.data.bones[bone_name].head_local
        for feature, offset_y, scale, material in (
            ("Sclera", -0.001, (0.0150, 0.0080, 0.0095), sclera_material),
            ("Iris", -0.016, (0.0058, 0.0022, 0.0058), iris_material),
            ("Pupil", -0.018, (0.0024, 0.0010, 0.0024), pupil_material),
        ):
            bpy.ops.mesh.primitive_uv_sphere_add(
                segments=32,
                ring_count=16,
                location=(center.x, center.y + offset_y, center.z),
            )
            obj = bpy.context.object
            obj.name = f"Patterna_MHR_{side_name}Eye{feature}"
            obj.data.name = f"{obj.name}Mesh"
            obj.scale = scale
            assign_material(obj, material)
            for polygon in obj.data.polygons:
                polygon.use_smooth = True
            components.append(obj)
    return components


def classify_bone(name: str) -> str:
    lowered = name.lower()
    if any(token in lowered for token in ("head", "jaw", "eye", "tongue", "teeth", "neck")):
        return "head"
    if lowered.startswith(("l_", "r_")) and any(
        token in lowered
        for token in ("uparm", "lowarm", "wrist", "thumb", "index", "middle", "ring", "pinky")
    ):
        return "arms"
    if lowered.startswith(("l_", "r_")) and any(
        token in lowered
        for token in ("upleg", "lowleg", "foot", "ball", "talar", "subtalar", "transversetarsal")
    ):
        return "legs"
    return "torso"


def body_vertex_regions(body: bpy.types.Object) -> list[str]:
    group_names = {group.index: group.name for group in body.vertex_groups}
    regions: list[str] = []
    for vertex in body.data.vertices:
        strongest = max(vertex.groups, key=lambda group: group.weight, default=None)
        regions.append(
            classify_bone(group_names.get(strongest.group, "root"))
            if strongest is not None
            else "torso"
        )
    return regions


def semantic_landmarks(armature: bpy.types.Object) -> dict[str, np.ndarray]:
    bones = armature.data.bones

    def head(name: str) -> np.ndarray:
        return np.asarray(tuple(armature.matrix_world @ bones[name].head_local), dtype=np.float64)

    return {
        "joint_shoulder.L_tail": head("l_uparm"),
        "joint_upper_arm.L_tail": head("l_lowarm"),
        "joint_forearm.L_tail": head("l_wrist"),
        "joint_shin.L_tail": head("l_foot"),
        "joint_thigh.L_head": head("l_upleg"),
        "joint_shoulder.R_tail": head("r_uparm"),
        "joint_upper_arm.R_tail": head("r_lowarm"),
        "joint_forearm.R_tail": head("r_wrist"),
        "joint_shin.R_tail": head("r_foot"),
        "joint_thigh.R_head": head("r_upleg"),
        "joint_chin_tail": head("c_jaw_null"),
    }


def exact_registration(
    body: bpy.types.Object,
    fitted_vertices: np.ndarray,
    regions: list[str],
) -> dict[str, Any]:
    actual = body_world_vertices(body)
    distances = np.linalg.norm(actual - fitted_vertices, axis=1)
    by_region: dict[str, Any] = {}
    thresholds = {
        "head": {"maximum": 0.005, "p95": 0.0025},
        "torso": {"maximum": 0.005, "p95": 0.0025},
        "arms": {"maximum": 0.010, "p95": 0.004},
        "legs": {"maximum": 0.010, "p95": 0.004},
    }
    for region, limits in thresholds.items():
        values = distances[np.asarray([value == region for value in regions])]
        maximum = float(values.max()) if len(values) else None
        p95 = float(np.percentile(values, 95)) if len(values) else None
        by_region[region] = {
            "accepted": bool(len(values) and maximum <= limits["maximum"] and p95 <= limits["p95"]),
            "sampleCount": int(len(values)),
            "maximumDistanceM": maximum,
            "p95DistanceM": p95,
            "thresholdsM": limits,
        }
    maximum = float(distances.max())
    return {
        "schemaVersion": "patterna.avatar-surface-registration/1.0",
        "accepted": maximum <= 0.00001 and all(item["accepted"] for item in by_region.values()),
        "method": "exact fitted MHR display and collision vertex-order comparison with skin-weight anatomical regions",
        "maximumSurfaceDistanceM": maximum,
        "comparedDisplayVertexCount": len(actual),
        "comparedCollisionVertexCount": len(fitted_vertices),
        "floorDatumErrorM": abs(float(actual[:, 2].min() - fitted_vertices[:, 2].min())),
        "regions": by_region,
        "issues": [] if maximum <= 0.00001 else ["display and collision surfaces differ"],
    }


def build_surface_shell(
    body: bpy.types.Object,
    name: str,
    predicate: Any,
    material: bpy.types.Material,
    *,
    vertical_bounds: tuple[float, float],
    lateral_bound: float,
) -> bpy.types.Object:
    world_vertices = [body.matrix_world @ vertex.co for vertex in body.data.vertices]
    normal_matrix = body.matrix_world.to_3x3().inverted().transposed()
    world_normals = [(normal_matrix @ vertex.normal).normalized() for vertex in body.data.vertices]
    polygons = [
        tuple(polygon.vertices)
        for polygon in body.data.polygons
        if predicate(body.matrix_world @ polygon.center)
    ]
    used = sorted({index for polygon in polygons for index in polygon})
    if len(used) < 100 or len(polygons) < 100:
        raise ValueError(f"MHR modesty component {name} selected too little surface.")
    remap = {source: target for target, source in enumerate(used)}
    coordinates = []
    for index in used:
        coordinate = world_vertices[index] + world_normals[index] * 0.0025
        coordinates.append(coordinate)
    faces = [tuple(remap[index] for index in polygon) for polygon in polygons]
    mesh = bpy.data.meshes.new(f"{name}Mesh")
    mesh.from_pydata(coordinates, [], faces)
    mesh.update()
    for polygon in mesh.polygons:
        polygon.use_smooth = True
    result = bpy.data.objects.new(name, mesh)
    bpy.context.collection.objects.link(result)
    assign_material(result, material)
    solidify = result.modifiers.new("Patterna modesty thickness", "SOLIDIFY")
    solidify.thickness = 0.0012
    solidify.offset = 0.0
    return result


def build_bandeau(
    body: bpy.types.Object,
    material: bpy.types.Material,
) -> bpy.types.Object:
    points = body_world_vertices(body)
    levels = np.linspace(1.08, 1.36, 15)
    ring_size = 72
    coordinates: list[tuple[float, float, float]] = []

    def cross(origin: tuple[float, float], first: tuple[float, float], second: tuple[float, float]) -> float:
        return (first[0] - origin[0]) * (second[1] - origin[1]) - (first[1] - origin[1]) * (second[0] - origin[0])

    def hull(values: np.ndarray) -> list[tuple[float, float]]:
        ordered = sorted({(float(point[0]), float(point[1])) for point in values})
        if len(ordered) < 3:
            raise ValueError("MHR bandeau section has no usable convex hull.")
        lower: list[tuple[float, float]] = []
        for point in ordered:
            while len(lower) >= 2 and cross(lower[-2], lower[-1], point) <= 0.0:
                lower.pop()
            lower.append(point)
        upper: list[tuple[float, float]] = []
        for point in reversed(ordered):
            while len(upper) >= 2 and cross(upper[-2], upper[-1], point) <= 0.0:
                upper.pop()
            upper.append(point)
        return lower[:-1] + upper[:-1]

    def resample(values: list[tuple[float, float]]) -> list[tuple[float, float]]:
        center = np.mean(np.asarray(values), axis=0)
        vectors = np.asarray(values) - center
        angles = np.mod(np.arctan2(vectors[:, 1], vectors[:, 0]), 2.0 * math.pi)
        radii = np.linalg.norm(vectors, axis=1) + 0.004
        order = np.argsort(angles)
        angles = angles[order]
        radii = radii[order]
        wrapped_angles = np.concatenate((angles[-1:] - 2.0 * math.pi, angles, angles[:1] + 2.0 * math.pi))
        wrapped_radii = np.concatenate((radii[-1:], radii, radii[:1]))
        result = []
        for sample in range(ring_size):
            angle = 2.0 * math.pi * sample / ring_size
            radius = float(np.interp(angle, wrapped_angles, wrapped_radii))
            result.append(tuple(center + radius * np.asarray((math.cos(angle), math.sin(angle)))))
        return result

    for z in levels:
        section = points[
            (np.abs(points[:, 2] - z) <= 0.018)
            & (np.abs(points[:, 0]) <= 0.25)
        ]
        if len(section) < 40:
            raise ValueError(f"MHR bandeau has too few body samples at {z:.3f} m.")
        for x, y in resample(hull(section[:, :2])):
            coordinates.append((x, y, float(z)))
    faces = []
    for level in range(len(levels) - 1):
        start = level * ring_size
        next_start = (level + 1) * ring_size
        for index in range(ring_size):
            following = (index + 1) % ring_size
            faces.append((start + index, start + following, next_start + following, next_start + index))
    mesh = bpy.data.meshes.new("Patterna_MHR_ModestyTopMesh")
    mesh.from_pydata(coordinates, [], faces)
    mesh.update()
    for polygon in mesh.polygons:
        polygon.use_smooth = True
    result = bpy.data.objects.new("Patterna_MHR_ModestyTop", mesh)
    bpy.context.collection.objects.link(result)
    assign_material(result, material)
    solidify = result.modifiers.new("Patterna modesty thickness", "SOLIDIFY")
    solidify.thickness = 0.0012
    solidify.offset = 0.0
    return result


def point_camera(camera: bpy.types.Object, target: Vector) -> None:
    camera.rotation_euler = (target - camera.location).to_track_quat("-Z", "Y").to_euler()


def render_views(
    components: list[bpy.types.Object],
    output_directory: Path,
    floor_z: float,
) -> dict[str, str]:
    output_directory.mkdir(parents=True, exist_ok=True)
    scene = bpy.context.scene
    scene.render.engine = "BLENDER_EEVEE_NEXT"
    scene.render.resolution_x = 768
    scene.render.resolution_y = 900
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.render.film_transparent = False
    scene.world.color = (0.025, 0.028, 0.036)

    bpy.ops.mesh.primitive_plane_add(size=8.0, location=(0.0, 0.0, floor_z - 0.002))
    floor = bpy.context.object
    assign_material(
        floor,
        configure_material("Patterna studio floor", (0.06, 0.07, 0.09, 1.0), roughness=0.88),
    )
    for location, energy, size in (
        ((-2.8, -3.2, 4.2), 1150.0, 3.0),
        ((3.0, -1.4, 2.6), 850.0, 2.4),
        ((0.0, 3.1, 3.5), 950.0, 2.7),
    ):
        data = bpy.data.lights.new("Patterna area light", "AREA")
        data.energy = energy
        data.shape = "DISK"
        data.size = size
        light = bpy.data.objects.new("Patterna area light", data)
        bpy.context.collection.objects.link(light)
        light.location = location

    camera_data = bpy.data.cameras.new("Patterna MHR review camera")
    camera_data.type = "ORTHO"
    camera_data.ortho_scale = 1.92
    camera = bpy.data.objects.new("Patterna MHR review camera", camera_data)
    bpy.context.collection.objects.link(camera)
    scene.camera = camera
    target = Vector((0.0, -0.015, 0.84))
    views = {
        "front": (0.0, -4.0, 0.92),
        "rear": (0.0, 4.0, 0.92),
        "left": (-4.0, 0.0, 0.92),
        "right": (4.0, 0.0, 0.92),
        "front-left": (-3.0, -3.0, 0.92),
        "front-right": (3.0, -3.0, 0.92),
    }
    result: dict[str, str] = {}
    for name, location in views.items():
        camera.location = location
        point_camera(camera, target)
        path = output_directory / f"{name}.png"
        scene.render.filepath = str(path)
        bpy.ops.render.render(write_still=True)
        result[name] = sha256(path)
    return result


def glb_contract(path: Path) -> dict[str, Any]:
    payload = path.read_bytes()
    if payload[:4] != b"glTF" or len(payload) < 20:
        raise ValueError("MHR export is not a valid GLB file.")
    chunk_length = int.from_bytes(payload[12:16], "little")
    document = json.loads(payload[20 : 20 + chunk_length].decode("utf-8").rstrip("\x00 "))
    body_node = next(
        (node for node in document.get("nodes", []) if node.get("name") == "Patterna_MHR_Body"),
        None,
    )
    transformed_mesh_nodes = [
        node.get("name", f"node-{index}")
        for index, node in enumerate(document.get("nodes", []))
        if "mesh" in node
        and any(
            transform in node
            for transform in ("matrix", "translation", "rotation", "scale")
        )
    ]
    if transformed_mesh_nodes:
        raise ValueError(
            "MHR GLB contains mesh-node transforms unsupported by the packaged renderer: "
            + ", ".join(transformed_mesh_nodes)
        )
    if body_node is None or "skin" not in body_node:
        raise ValueError("MHR GLB body is not bound to an exported skin.")
    primitive = document["meshes"][body_node["mesh"]]["primitives"][0]
    attributes = primitive.get("attributes", {})
    if "JOINTS_0" not in attributes or "WEIGHTS_0" not in attributes:
        raise ValueError("MHR GLB body does not contain skinning attributes.")
    skins = document.get("skins", [])
    if len(skins) != 1 or len(skins[0].get("joints", [])) < 100:
        raise ValueError("MHR GLB does not contain the expected joint hierarchy.")
    return {
        "accepted": True,
        "nodeCount": len(document.get("nodes", [])),
        "meshCount": len(document.get("meshes", [])),
        "skinCount": len(skins),
        "exportedJointCount": len(skins[0]["joints"]),
        "bodyHasJoints0": True,
        "bodyHasWeights0": True,
        "meshNodesUseIdentityTransforms": True,
    }


def main() -> None:
    args = parse_args()
    paths = {
        name: value.resolve()
        for name, value in vars(args).items()
        if isinstance(value, Path)
    }
    for name, path in paths.items():
        if name != "output_directory" and not path.is_file():
            raise FileNotFoundError(f"MHR export input is missing: {path}")

    fit_report = json.loads(paths["fit_report"].read_text(encoding="utf-8"))
    if fit_report.get("schemaVersion") != "patterna.mhr-local-fit/1.0" or fit_report.get("status") != "accepted":
        raise ValueError("MHR display export requires an accepted local-fit report.")
    if sha256(paths["fitted_obj"]) != fit_report["outputs"]["previewObjSha256"]:
        raise ValueError("MHR fitted OBJ hash does not match the local-fit report.")
    rig_state = json.loads(paths["rig_state"].read_text(encoding="utf-8"))
    if rig_state.get("schemaVersion") != "patterna.mhr-rig-state/1.0":
        raise ValueError("MHR rig-state schema is not supported.")

    fitted_vertices, fitted_faces = load_obj(paths["fitted_obj"])
    output_directory = paths["output_directory"]
    output_directory.mkdir(parents=True, exist_ok=True)
    clear_scene()
    bpy.ops.import_scene.fbx(filepath=str(paths["source_fbx"]))
    body, armature = find_source_objects()
    source_height_m = float(np.ptp(body_world_vertices(body)[:, 2]))
    target_height_m = float(np.ptp(fitted_vertices[:, 2]))
    scale_ratio = target_height_m / source_height_m
    fit_armature_rest_pose(armature, scale_ratio, rig_state)
    replacement_error = replace_body_vertices(body, fitted_vertices)
    body.name = "Patterna_MHR_Body"
    body.data.name = "Patterna_MHR_BodyMesh"
    armature.name = "Patterna_MHR_Rig"
    armature.data.name = "Patterna_MHR_RigData"

    source_faces = [tuple(polygon.vertices) for polygon in body.data.polygons]
    face_match = source_faces == fitted_faces
    if not face_match:
        raise ValueError("MHR FBX and fitted OBJ triangle ordering do not match.")

    skin = configure_material(
        "Patterna MHR skin",
        (0.46, 0.20, 0.105, 1.0),
        roughness=0.53,
    )
    assign_material(body, skin)
    eyes = build_eye_components(armature)
    hair = import_obj_component(paths["hair_obj"], "Patterna_MHR_Hair")
    hair.location.y += 0.050
    hair.location.z += 0.003
    assign_material(
        hair,
        configure_material(
            "Patterna MHR hair",
            (0.055, 0.022, 0.012, 1.0),
            roughness=0.72,
            texture=paths["hair_texture"],
            alpha=True,
        ),
    )
    modesty_material = configure_material(
        "Patterna MHR modesty",
        (0.055, 0.075, 0.13, 1.0),
        roughness=0.84,
    )
    top = build_bandeau(body, modesty_material)
    briefs = build_surface_shell(
        body,
        "Patterna_MHR_ModestyBriefs",
        lambda point: 0.70 <= point.z <= 0.96 and abs(point.x) <= 0.255,
        modesty_material,
        vertical_bounds=(0.70, 0.96),
        lateral_bound=0.255,
    )

    regions = body_vertex_regions(body)
    region_counts = Counter(regions)
    vertices = body_world_vertices(body)
    anatomy = evaluate_avatar_anatomy(vertices, regions, semantic_landmarks(armature))
    pose = evaluate_avatar_pose(vertices, regions, semantic_landmarks(armature))
    registration = exact_registration(body, fitted_vertices, regions)
    rig = verify_rig(body, armature, rig_state)
    for report_name, report in (
        ("anatomy", anatomy),
        ("pose", pose),
        ("registration", registration),
        ("rig", rig),
    ):
        if not report["accepted"]:
            raise ValueError(
                f"MHR {report_name} gate failed:\n{json.dumps(report, indent=2)}"
            )

    components = [body, *eyes, hair, top, briefs]
    bpy.ops.object.select_all(action="DESELECT")
    for component in components[1:]:
        component.select_set(True)
    bpy.context.view_layer.objects.active = components[1]
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
    bpy.ops.object.select_all(action="DESELECT")
    armature.select_set(True)
    for component in components:
        component.select_set(True)
    bpy.context.view_layer.objects.active = body
    glb_path = output_directory / "mhr.glb"
    bpy.ops.export_scene.gltf(
        filepath=str(glb_path),
        export_format="GLB",
        use_selection=True,
        export_apply=False,
        export_texcoords=True,
        export_normals=True,
        export_materials="EXPORT",
        export_cameras=False,
        export_lights=False,
        export_animations=False,
        export_skins=True,
        export_morph=False,
        export_yup=True,
    )
    glb_evidence = glb_contract(glb_path)
    render_hashes = render_views(
        components,
        output_directory / "renders",
        float(vertices[:, 2].min()),
    )

    license_path = output_directory / "license.txt"
    shutil.copy2(paths["source_license"], license_path)
    manifest_path = output_directory / "manifest.json"
    manifest = {
        "schemaVersion": "patterna.display-avatar-glb/1.0",
        "accepted": False,
        "candidateOnly": True,
        "displayMode": "mhr-candidate",
        "source": "Meta Momentum Human Rig",
        "sourceVersion": "1.0.1",
        "sourceUrl": "https://github.com/facebookresearch/MHR",
        "outputLicense": "Apache-2.0",
        "licenseFile": license_path.name,
        "licenseSha256": sha256(license_path),
        "geometry": glb_path.name,
        "geometrySha256": sha256(glb_path),
        "geometryBytes": glb_path.stat().st_size,
        "primaryBodyNode": "Patterna_MHR_Body",
        "primaryBodyMaterial": "Patterna MHR skin",
        "assetNodes": {
            "Patterna_MHR_LeftEyeSclera": "eyes",
            "Patterna_MHR_LeftEyeIris": "eyes",
            "Patterna_MHR_LeftEyePupil": "eyes",
            "Patterna_MHR_RightEyeSclera": "eyes",
            "Patterna_MHR_RightEyeIris": "eyes",
            "Patterna_MHR_RightEyePupil": "eyes",
            "Patterna_MHR_Hair": "hair",
            "Patterna_MHR_ModestyTop": "modesty-top",
            "Patterna_MHR_ModestyBriefs": "modesty-briefs",
        },
        "heightTargetCm": float(rig_state["heightTargetCm"]),
        "heightMeasuredCm": target_height_m * 100.0,
        "floorOffsetM": float(vertices[:, 2].min()),
        "displayYawDegrees": 180.0,
        "measurementFit": {
            "accepted": True,
            "reportSha256": sha256(paths["fit_report"]),
            "maximumAbsoluteResidualCm": max(
                item["absoluteErrorCm"]
                for item in fit_report["acceptance"]["measurements"].values()
            ),
        },
        "topology": {
            "vertexCount": len(body.data.vertices),
            "triangleCount": len(body.data.polygons),
            "uvLayerCount": len(body.data.uv_layers),
            "fbxAndFittedFaceOrderMatch": face_match,
            "maximumVertexReplacementErrorM": replacement_error,
        },
        "rig": rig,
        "glbContract": glb_evidence,
        "registration": registration,
        "anatomy": anatomy,
        "pose": pose,
        "regionVertexCounts": dict(region_counts),
        "appearance": {
            "skin": "neutral procedural PBR material",
            "eyes": "MHR-rig-positioned procedural PBR display eyes",
            "hair": f"MPFB-fitted MakeHuman Community CC0 {args.hair_style} display asset",
            "hairStyle": args.hair_style,
            "modesty": "body-conformed display shells, not sewing patterns or cloth simulation",
            "appearanceAssetLicense": "CC0",
        },
        "renders": render_hashes,
        "openGates": [
            "six-view host and packaged visual review is pending",
            "measurement edits do not yet rebuild this MHR family in the packaged app",
            "cloth has not been solved and accepted on this exact MHR body",
            "physical-GPU packaged acceptance is pending",
        ],
    }
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()
