#!/usr/bin/env python3
"""Refine an assembled Patterna garment with Blender's cloth solver.

This is a reversible architecture proof. It consumes the same measured display
avatar and assembled garment that the Windows product renders, settles the
garment with Blender cloth and collision, and emits a meter-space proof mesh,
a centimeter-space application mesh, a Blender scene, renders, and evidence.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
import sys
import time

import bmesh
import bpy
from mathutils import Vector
from mathutils.bvhtree import BVHTree


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_AVATAR_MANIFEST = Path("Patternal/Assets/Production/Avatar/manifest.json")
DEFAULT_GARMENT = Path("Patternal/Assets/Production/patterna-production-crew-neck.obj")
DEFAULT_SIMULATION_GARMENT = Path(
    "artifacts/full-panel-validation/warp-zero-contact-v3/"
    "PatternaFullPanel/PatternaFullPanel_sim.obj"
)
DEFAULT_SEWING_PROXY = Path(
    "artifacts/blender-cloth-vertical-slice/sewing-proxy/"
    "PatternaProductionCrewNeck.sewing-proxy.json"
)
DEFAULT_FABRIC = Path("third_party/GarmentCode/assets/img/fabric_texture.png")
DEFAULT_OUTPUT_DIRECTORY = Path("artifacts/blender-cloth-vertical-slice/current")
FABRIC_PRESETS = {
    "cotton-jersey": {
        "mass": 0.16,
        "air_damping": 5.0,
        "tension_stiffness": 40.0,
        "compression_stiffness": 40.0,
        "shear_stiffness": 15.0,
        "bending_stiffness": 0.08,
        "structural_damping": 10.0,
        "bending_damping": 3.0,
    },
    "cotton-poplin": {
        "mass": 0.14,
        "air_damping": 5.0,
        "tension_stiffness": 90.0,
        "compression_stiffness": 90.0,
        "shear_stiffness": 38.0,
        "bending_stiffness": 0.18,
        "structural_damping": 12.0,
        "bending_damping": 4.0,
    },
    "cotton-jersey-stable": {
        "mass": 0.14,
        "air_damping": 12.0,
        "tension_stiffness": 220.0,
        "compression_stiffness": 140.0,
        "shear_stiffness": 80.0,
        "bending_stiffness": 0.10,
        "structural_damping": 30.0,
        "bending_damping": 8.0,
    },
    "cotton-jersey-damped": {
        "mass": 0.16,
        "air_damping": 24.0,
        "tension_stiffness": 40.0,
        "compression_stiffness": 40.0,
        "shear_stiffness": 15.0,
        "bending_stiffness": 0.08,
        "structural_damping": 35.0,
        "bending_damping": 10.0,
    },
}


def blender_arguments() -> list[str]:
    return sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--avatar-manifest", type=Path, default=DEFAULT_AVATAR_MANIFEST)
    parser.add_argument("--garment", type=Path, default=DEFAULT_GARMENT)
    parser.add_argument(
        "--simulation-garment",
        type=Path,
        default=DEFAULT_SIMULATION_GARMENT,
    )
    parser.add_argument(
        "--simulation-source",
        choices=("remesh", "external", "sewing-proxy"),
        default="remesh",
    )
    parser.add_argument(
        "--external-edge-mode",
        choices=("surface-only", "sewing-springs"),
        default="surface-only",
        help=(
            "Interpret loose edges in an external simulation OBJ as either "
            "non-surface export artifacts or intentional Blender sewing springs."
        ),
    )
    parser.add_argument("--sewing-proxy", type=Path, default=DEFAULT_SEWING_PROXY)
    parser.add_argument(
        "--sewing-proxy-topology",
        choices=("explicit", "hybrid"),
        default="hybrid",
    )
    parser.add_argument("--simulation-target-faces", type=int, default=8000)
    parser.add_argument("--fabric", type=Path, default=DEFAULT_FABRIC)
    parser.add_argument("--output-directory", type=Path, default=DEFAULT_OUTPUT_DIRECTORY)
    parser.add_argument("--frames", type=int, default=120)
    parser.add_argument("--quality", type=int, default=8)
    parser.add_argument(
        "--fabric-preset",
        choices=tuple(FABRIC_PRESETS),
        default="cotton-jersey",
    )
    parser.add_argument("--resolution-x", type=int, default=720)
    parser.add_argument("--resolution-y", type=int, default=900)
    parser.add_argument(
        "--render-view-set",
        choices=("all", "front", "none"),
        default="all",
    )
    parser.add_argument("--disable-self-collision", action="store_true")
    parser.add_argument("--sewing-force-max", type=float, default=5.0)
    parser.add_argument(
        "--collision-start-horizontal-scale",
        type=float,
        default=1.0,
        help=(
            "Start the solver collider smaller in width and depth, then grow it "
            "to the exact avatar surface to release an intersecting dressed pose."
        ),
    )
    parser.add_argument("--collision-ramp-frames", type=int, default=0)
    parser.add_argument("--gravity-ramp-start-frame", type=int, default=1)
    parser.add_argument("--gravity-ramp-frames", type=int, default=0)
    return parser.parse_args(blender_arguments())


def resolve(path: Path) -> Path:
    return path.resolve() if path.is_absolute() else (REPO_ROOT / path).resolve()


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def point_at(obj: bpy.types.Object, target: Vector) -> None:
    obj.rotation_euler = (target - obj.location).to_track_quat("-Z", "Y").to_euler()


def import_single_obj(
    path: Path,
    name: str,
    *,
    scale: float = 1.0,
    forward_axis: str = "NEGATIVE_Y",
    up_axis: str = "Z",
) -> bpy.types.Object:
    before = set(bpy.context.scene.objects)
    bpy.ops.wm.obj_import(
        filepath=str(path),
        forward_axis=forward_axis,
        up_axis=up_axis,
    )
    imported = [obj for obj in bpy.context.scene.objects if obj not in before]
    meshes = [obj for obj in imported if obj.type == "MESH"]
    if len(meshes) != 1:
        raise RuntimeError(f"Expected one mesh in {path}, received {len(meshes)}")
    result = meshes[0]
    result.name = name
    result.scale = (scale, scale, scale)
    bpy.context.view_layer.objects.active = result
    result.select_set(True)
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    for polygon in result.data.polygons:
        polygon.use_smooth = True
    return result


def principled_material(
    name: str,
    color: tuple[float, float, float, float],
    roughness: float,
    texture_path: Path | None = None,
    subsurface_weight: float = 0.0,
    alpha_clip: bool = False,
) -> bpy.types.Material:
    material = bpy.data.materials.new(name)
    material.diffuse_color = color
    material.use_nodes = True
    nodes = material.node_tree.nodes
    links = material.node_tree.links
    principled = nodes.get("Principled BSDF")
    principled.inputs["Base Color"].default_value = color
    principled.inputs["Roughness"].default_value = roughness
    principled.inputs["Subsurface Weight"].default_value = subsurface_weight
    if texture_path:
        texture = nodes.new("ShaderNodeTexImage")
        texture.image = bpy.data.images.load(str(texture_path), check_existing=True)
        texture.interpolation = "Linear"
        links.new(texture.outputs["Color"], principled.inputs["Base Color"])
        if alpha_clip:
            links.new(texture.outputs["Alpha"], principled.inputs["Alpha"])
            if hasattr(material, "surface_render_method"):
                material.surface_render_method = "DITHERED"
    return material


def cloth_material(texture_path: Path) -> bpy.types.Material:
    material = principled_material(
        "Patterna refined cotton",
        (0.24, 0.018, 0.055, 1.0),
        0.74,
    )
    nodes = material.node_tree.nodes
    links = material.node_tree.links
    principled = nodes.get("Principled BSDF")
    principled.inputs["Sheen Weight"].default_value = 0.16

    texture = nodes.new("ShaderNodeTexImage")
    texture.image = bpy.data.images.load(str(texture_path), check_existing=True)
    texture.interpolation = "Linear"
    tint = nodes.new("ShaderNodeRGB")
    tint.outputs["Color"].default_value = (0.32, 0.025, 0.075, 1.0)
    multiply = nodes.new("ShaderNodeMixRGB")
    multiply.blend_type = "MULTIPLY"
    multiply.inputs["Fac"].default_value = 1.0
    links.new(texture.outputs["Color"], multiply.inputs[1])
    links.new(tint.outputs["Color"], multiply.inputs[2])
    links.new(multiply.outputs["Color"], principled.inputs["Base Color"])

    noise = nodes.new("ShaderNodeTexNoise")
    noise.inputs["Scale"].default_value = 520.0
    noise.inputs["Detail"].default_value = 2.0
    noise.inputs["Roughness"].default_value = 0.58
    bump = nodes.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value = 0.055
    bump.inputs["Distance"].default_value = 0.00008
    links.new(noise.outputs["Fac"], bump.inputs["Height"])
    links.new(bump.outputs["Normal"], principled.inputs["Normal"])
    return material


def configure_avatar(
    manifest_path: Path,
) -> tuple[dict[str, bpy.types.Object], dict[str, str]]:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("schema_version") != "patterna.display-avatar/1.0":
        raise RuntimeError("Unsupported display-avatar manifest schema")
    base = manifest_path.parent
    objects: dict[str, bpy.types.Object] = {}
    hashes: dict[str, str] = {"manifest": sha256(manifest_path)}
    settings = {
        "body": ((0.48, 0.25, 0.16, 1.0), 0.49, 0.075, False),
        "eyes": ((0.72, 0.72, 0.68, 1.0), 0.24, 0.0, False),
        "teeth": ((0.80, 0.78, 0.70, 1.0), 0.34, 0.0, False),
        "eyebrows": ((0.025, 0.018, 0.014, 1.0), 0.72, 0.0, True),
        "eyelashes": ((0.01, 0.008, 0.007, 1.0), 0.76, 0.0, True),
        "hair": ((0.018, 0.012, 0.009, 1.0), 0.68, 0.0, True),
        "bra": ((0.30, 0.12, 0.16, 1.0), 0.72, 0.0, False),
    }
    for asset_name, asset in manifest["assets"].items():
        geometry_path = base / asset["geometry"]
        texture_path = base / asset["texture"]
        color, roughness, subsurface_weight, alpha_clip = settings[asset_name]
        mesh = import_single_obj(
            geometry_path,
            f"PatternaAvatar_{asset_name}",
            forward_axis="NEGATIVE_Y",
            up_axis="Z",
        )
        mesh.data.materials.clear()
        mesh.data.materials.append(
            principled_material(
                f"Patterna {asset_name}",
                color,
                roughness,
                texture_path,
                subsurface_weight,
                alpha_clip,
            )
        )
        objects[asset_name] = mesh
        hashes[f"{asset_name}_geometry"] = sha256(geometry_path)
        hashes[f"{asset_name}_texture"] = sha256(texture_path)

    floor_offset_m = float(manifest.get("floor_offset_m", 0.0))
    for mesh in objects.values():
        mesh.location.z -= floor_offset_m
    return objects, hashes


def remove_non_surface_geometry(
    mesh_object: bpy.types.Object,
    *,
    preserve_sewing_edges: bool = False,
) -> dict[str, int]:
    before_vertices = len(mesh_object.data.vertices)
    before_edges = len(mesh_object.data.edges)
    before_faces = len(mesh_object.data.polygons)
    editable = bmesh.new()
    editable.from_mesh(mesh_object.data)
    if not preserve_sewing_edges:
        loose_edges = [edge for edge in editable.edges if not edge.link_faces]
        if loose_edges:
            bmesh.ops.delete(editable, geom=loose_edges, context="EDGES")
    loose_vertices = [vertex for vertex in editable.verts if not vertex.link_faces]
    if loose_vertices:
        bmesh.ops.delete(editable, geom=loose_vertices, context="VERTS")
    editable.normal_update()
    editable.to_mesh(mesh_object.data)
    editable.free()
    mesh_object.data.update()
    return {
        "vertices_removed": before_vertices - len(mesh_object.data.vertices),
        "edges_removed": before_edges - len(mesh_object.data.edges),
        "faces_removed": before_faces - len(mesh_object.data.polygons),
        "surface_vertices": len(mesh_object.data.vertices),
        "surface_edges": len(mesh_object.data.edges),
        "surface_faces": len(mesh_object.data.polygons),
    }


def remove_non_surface_edges(mesh_object: bpy.types.Object) -> int:
    editable = bmesh.new()
    editable.from_mesh(mesh_object.data)
    loose_edges = [edge for edge in editable.edges if not edge.link_faces]
    removed = len(loose_edges)
    if loose_edges:
        bmesh.ops.delete(editable, geom=loose_edges, context="EDGES")
    editable.normal_update()
    editable.to_mesh(mesh_object.data)
    editable.free()
    mesh_object.data.update()
    return removed


def mesh_bounds(mesh_object: bpy.types.Object) -> dict[str, list[float]]:
    points = [mesh_object.matrix_world @ vertex.co for vertex in mesh_object.data.vertices]
    return {
        "minimum": [min(point[axis] for point in points) for axis in range(3)],
        "maximum": [max(point[axis] for point in points) for axis in range(3)],
    }


def add_collision(body: bpy.types.Object) -> None:
    modifier = body.modifiers.new(name="Patterna body collision", type="COLLISION")
    if modifier is None:
        raise RuntimeError("Failed to create Blender collision modifier")
    settings = body.collision
    settings.use = True
    settings.thickness_outer = 0.0025
    settings.thickness_inner = 0.001
    settings.damping = 0.35
    settings.cloth_friction = 12.0


def create_solver_collider(
    display_body: bpy.types.Object,
    start_horizontal_scale: float,
    ramp_frames: int,
) -> bpy.types.Object:
    if start_horizontal_scale <= 0 or start_horizontal_scale > 1:
        raise ValueError("Collision start scale must be greater than zero through one")
    if ramp_frames < 0:
        raise ValueError("Collision ramp frames cannot be negative")
    collider = display_body.copy()
    collider.data = display_body.data.copy()
    collider.name = "PatternaSolverCollider"
    collider.data.name = "PatternaSolverColliderMesh"
    collider.hide_render = True
    bpy.context.collection.objects.link(collider)
    collider.scale = (
        start_horizontal_scale,
        start_horizontal_scale,
        1.0,
    )
    collider.keyframe_insert(data_path="scale", frame=1)
    if ramp_frames > 0 and start_horizontal_scale < 1:
        collider.scale = (1.0, 1.0, 1.0)
        collider.keyframe_insert(data_path="scale", frame=ramp_frames)
        if collider.animation_data and collider.animation_data.action:
            for curve in collider.animation_data.action.fcurves:
                for keyframe in curve.keyframe_points:
                    keyframe.interpolation = "LINEAR"
    add_collision(collider)
    return collider


def add_cloth(
    garment: bpy.types.Object,
    frames: int,
    quality: int,
    fabric_preset: str,
    use_self_collision: bool,
    sewing_force_max: float,
) -> bpy.types.Modifier:
    preset = FABRIC_PRESETS[fabric_preset]
    modifier = garment.modifiers.new(name="Patterna Blender cloth", type="CLOTH")
    settings = modifier.settings
    settings.quality = quality
    settings.mass = preset["mass"]
    settings.air_damping = preset["air_damping"]
    settings.tension_stiffness = preset["tension_stiffness"]
    settings.compression_stiffness = preset["compression_stiffness"]
    settings.shear_stiffness = preset["shear_stiffness"]
    settings.bending_stiffness = preset["bending_stiffness"]
    settings.tension_damping = preset["structural_damping"]
    settings.compression_damping = preset["structural_damping"]
    settings.shear_damping = preset["structural_damping"]
    settings.bending_damping = preset["bending_damping"]
    settings.use_sewing_springs = True
    settings.sewing_force_max = sewing_force_max
    settings.shrink_min = 0.0

    collision = modifier.collision_settings
    collision.use_collision = True
    collision.collision_quality = max(2, min(6, quality))
    collision.distance_min = 0.0022
    collision.use_self_collision = use_self_collision
    collision.self_distance_min = 0.0016
    collision.self_friction = 6.0

    cache = modifier.point_cache
    cache.frame_start = 1
    cache.frame_end = frames
    return modifier


def build_hybrid_seam_topology(
    vertices: list[tuple[float, float, float]],
    faces: list[tuple[int, int, int]],
    sewing_edges: list[tuple[int, int]],
    weld_distance_m: float = 0.025,
) -> tuple[
    list[tuple[float, float, float]],
    list[tuple[int, int, int]],
    list[tuple[int, int]],
    dict[str, int],
]:
    neighbors: dict[int, set[int]] = {}
    for first, second in sewing_edges:
        neighbors.setdefault(first, set()).add(second)
        neighbors.setdefault(second, set()).add(first)

    parent = list(range(len(vertices)))

    def find(index: int) -> int:
        root = index
        while parent[root] != root:
            root = parent[root]
        while parent[index] != index:
            next_index = parent[index]
            parent[index] = root
            index = next_index
        return root

    def union(first: int, second: int) -> None:
        first_root = find(first)
        second_root = find(second)
        if first_root != second_root:
            parent[second_root] = first_root

    welded_pairs = 0
    skipped_distant_pairs = 0
    for first, second in sewing_edges:
        distance = math.dist(vertices[first], vertices[second])
        if (
            len(neighbors[first]) == 1
            and len(neighbors[second]) == 1
            and distance <= weld_distance_m
        ):
            union(first, second)
            welded_pairs += 1
        elif len(neighbors[first]) == 1 and len(neighbors[second]) == 1:
            skipped_distant_pairs += 1

    groups: dict[int, list[int]] = {}
    for index in range(len(vertices)):
        groups.setdefault(find(index), []).append(index)
    remap: dict[int, int] = {}
    merged_vertices: list[tuple[float, float, float]] = []
    for members in groups.values():
        merged_index = len(merged_vertices)
        for member in members:
            remap[member] = merged_index
        merged_vertices.append(
            tuple(
                sum(vertices[member][axis] for member in members) / len(members)
                for axis in range(3)
            )
        )

    merged_faces: list[tuple[int, int, int]] = []
    for face in faces:
        mapped = tuple(remap[index] for index in face)
        if len(set(mapped)) != 3:
            raise RuntimeError("Hybrid seam welding produced a degenerate panel face")
        merged_faces.append(mapped)

    material_edges = {
        tuple(sorted((first, second)))
        for face in merged_faces
        for first, second in ((face[0], face[1]), (face[1], face[2]), (face[2], face[0]))
    }
    remaining_edges: list[tuple[int, int]] = []
    seen: set[tuple[int, int]] = set()
    for first, second in sewing_edges:
        pair = tuple(sorted((remap[first], remap[second])))
        if pair[0] == pair[1] or pair in material_edges or pair in seen:
            continue
        seen.add(pair)
        remaining_edges.append(pair)
    return merged_vertices, merged_faces, remaining_edges, {
        "source_vertex_count": len(vertices),
        "welded_pair_count": welded_pairs,
        "skipped_distant_pair_count": skipped_distant_pairs,
        "weld_distance_mm": weld_distance_m * 1000.0,
        "merged_vertex_count": len(merged_vertices),
        "remaining_sewing_spring_count": len(remaining_edges),
    }


def import_sewing_proxy(
    path: Path,
    topology: str,
) -> tuple[bpy.types.Object, dict[str, object]]:
    document = json.loads(path.read_text(encoding="utf-8"))
    if document.get("schemaVersion") != "patterna.blender-sewing-proxy/1.0":
        raise RuntimeError("Unsupported Blender sewing proxy schema")
    if document.get("units") != "centimeters":
        raise RuntimeError("Blender sewing proxy must use centimeters")

    # GarmentCode uses X horizontal, Y vertical, and Z depth. Blender uses X
    # horizontal, Z vertical, and negative Y as the anatomical front direction,
    # matching the OBJ import contract used by the product renderer.
    vertices = [None] * len(document["vertices"])
    arranged_panels: list[dict[str, object]] = []
    for panel in document["panels"]:
        name = str(panel["name"])
        start = int(panel["vertexStart"])
        count = int(panel["vertexCount"])
        source_points = document["vertices"][start : start + count]
        arrangement = "authored-rigid"
        if name in ("front_torso", "back_torso"):
            center_x_cm = 0.5 * (
                min(float(point[0]) for point in source_points)
                + max(float(point[0]) for point in source_points)
            )
            half_width_m = max(
                abs(float(point[0]) - center_x_cm) for point in source_points
            ) * 0.01
            radius_m = max(half_width_m / (0.5 * math.pi), 0.12)
            side_depth_m = -0.04
            front = name == "front_torso"
            for local_index, point in enumerate(source_points):
                arc_m = (float(point[0]) - center_x_cm) * 0.01
                angle = arc_m / radius_m
                depth_m = side_depth_m + (-1.0 if front else 1.0) * radius_m * math.cos(angle)
                vertices[start + local_index] = (
                    radius_m * math.sin(angle),
                    depth_m,
                    float(point[1]) * 0.01,
                )
            arrangement = "strain-free-torso-cylinder"
        else:
            if "sleeve_f" in name or "cuff_f" in name:
                depth_override_m = -0.07
            elif "sleeve_b" in name or "cuff_b" in name:
                depth_override_m = 0.03
            elif "collar_front" in name:
                depth_override_m = -0.035
            elif "collar_back" in name:
                depth_override_m = 0.015
            else:
                depth_override_m = None
            for local_index, point in enumerate(source_points):
                vertices[start + local_index] = (
                    float(point[0]) * 0.01,
                    depth_override_m if depth_override_m is not None else -float(point[2]) * 0.01,
                    float(point[1]) * 0.01,
                )
            if depth_override_m is not None:
                arrangement = "rigid-depth-placement"
        arranged_panels.append({"name": name, "arrangement": arrangement})
    if any(point is None for point in vertices):
        raise RuntimeError("Sewing proxy arrangement did not map every panel vertex")
    document["blenderArrangement"] = arranged_panels
    faces = [tuple(int(value) for value in face) for face in document["faces"]]
    sewing_edges = [tuple(int(value) for value in edge) for edge in document["sewingEdges"]]
    if topology == "hybrid":
        vertices, faces, sewing_edges, topology_evidence = build_hybrid_seam_topology(
            vertices,
            faces,
            sewing_edges,
        )
    else:
        topology_evidence = {
            "source_vertex_count": len(vertices),
            "welded_pair_count": 0,
            "merged_vertex_count": len(vertices),
            "remaining_sewing_spring_count": len(sewing_edges),
        }
    document["blenderTopology"] = {
        "mode": topology,
        **topology_evidence,
    }
    mesh = bpy.data.meshes.new("PatternaSewingSimulationMesh")
    mesh.from_pydata(vertices, sewing_edges, faces)
    mesh.validate(verbose=True)
    mesh.update(calc_edges=True)
    garment = bpy.data.objects.new("PatternaSourceSimulationGarment", mesh)
    bpy.context.collection.objects.link(garment)
    for polygon in garment.data.polygons:
        polygon.use_smooth = True
    return garment, document


def bind_render_surface(
    render_surface: bpy.types.Object,
    simulation_surface: bpy.types.Object,
) -> bpy.types.Modifier:
    modifier = render_surface.modifiers.new(
        name="Patterna simulation surface transfer",
        type="SURFACE_DEFORM",
    )
    modifier.target = simulation_surface
    bpy.ops.object.select_all(action="DESELECT")
    render_surface.select_set(True)
    bpy.context.view_layer.objects.active = render_surface
    bpy.ops.object.surfacedeform_bind(modifier=modifier.name)
    if not modifier.is_bound:
        raise RuntimeError("Blender could not bind the render mesh to the simulation mesh")
    return modifier


def weld_coincident_simulation_vertices(
    simulation_surface: bpy.types.Object,
    distance_m: float = 0.000001,
) -> dict[str, int | float]:
    """Collapse OBJ vertex splits that exist only to carry render UV seams."""
    source_vertices = len(simulation_surface.data.vertices)
    source_edges = len(simulation_surface.data.edges)
    source_faces = len(simulation_surface.data.polygons)
    editable = bmesh.new()
    editable.from_mesh(simulation_surface.data)
    bmesh.ops.remove_doubles(
        editable,
        verts=list(editable.verts),
        dist=distance_m,
    )
    editable.normal_update()
    editable.to_mesh(simulation_surface.data)
    editable.free()
    simulation_surface.data.validate(verbose=True)
    simulation_surface.data.update(calc_edges=True)
    return {
        "source_vertex_count": source_vertices,
        "source_edge_count": source_edges,
        "source_face_count": source_faces,
        "welded_vertex_count": len(simulation_surface.data.vertices),
        "welded_edge_count": len(simulation_surface.data.edges),
        "welded_face_count": len(simulation_surface.data.polygons),
        "removed_vertex_count": source_vertices - len(simulation_surface.data.vertices),
        "distance_mm": distance_m * 1000.0,
    }


def build_remeshed_simulation_surface(
    render_surface: bpy.types.Object,
    target_faces: int,
) -> tuple[bpy.types.Object, dict[str, int | float]]:
    if target_faces < 1000:
        raise ValueError("Simulation remesh target must be at least 1,000 faces")
    simulation_surface = render_surface.copy()
    simulation_surface.data = render_surface.data.copy()
    simulation_surface.name = "PatternaSourceSimulationGarment"
    simulation_surface.data.name = "PatternaSimulationMesh"
    simulation_surface.data.materials.clear()
    bpy.context.collection.objects.link(simulation_surface)
    position_weld = weld_coincident_simulation_vertices(simulation_surface)
    bpy.ops.object.select_all(action="DESELECT")
    simulation_surface.select_set(True)
    bpy.context.view_layer.objects.active = simulation_surface
    bpy.ops.object.quadriflow_remesh(
        use_mesh_symmetry=False,
        use_preserve_sharp=False,
        use_preserve_boundary=True,
        preserve_attributes=False,
        smooth_normals=True,
        mode="FACES",
        target_faces=target_faces,
        seed=0,
    )
    if len(simulation_surface.data.polygons) < target_faces * 0.5:
        raise RuntimeError(
            "Blender produced too few faces for the simulation remesh: "
            f"{len(simulation_surface.data.polygons)}"
        )
    editable = bmesh.new()
    editable.from_mesh(simulation_surface.data)
    bmesh.ops.triangulate(editable, faces=list(editable.faces))
    editable.normal_update()
    editable.to_mesh(simulation_surface.data)
    editable.free()
    simulation_surface.data.update()
    for polygon in simulation_surface.data.polygons:
        polygon.use_smooth = True
    return simulation_surface, position_weld


def mesh_quality_evidence(mesh_object: bpy.types.Object) -> dict[str, float | int]:
    points = [mesh_object.matrix_world @ vertex.co for vertex in mesh_object.data.vertices]
    lengths = sorted(
        (points[edge.vertices[0]] - points[edge.vertices[1]]).length
        for edge in mesh_object.data.edges
        if not edge.is_loose
    )
    return {
        "vertex_count": len(mesh_object.data.vertices),
        "edge_count": len(mesh_object.data.edges),
        "face_count": len(mesh_object.data.polygons),
        "sewing_spring_count": sum(edge.is_loose for edge in mesh_object.data.edges),
        "minimum_edge_length_mm": min(lengths, default=0.0) * 1000.0,
        "one_tenth_percentile_edge_length_mm": percentile(lengths, 0.001) * 1000.0,
        "median_edge_length_mm": percentile(lengths, 0.5) * 1000.0,
        "maximum_edge_length_mm": max(lengths, default=0.0) * 1000.0,
    }


def evaluated_copy(source: bpy.types.Object, name: str) -> bpy.types.Object:
    depsgraph = bpy.context.evaluated_depsgraph_get()
    evaluated = source.evaluated_get(depsgraph)
    result_mesh = bpy.data.meshes.new_from_object(
        evaluated,
        preserve_all_data_layers=True,
        depsgraph=depsgraph,
    )
    result = bpy.data.objects.new(name, result_mesh)
    bpy.context.collection.objects.link(result)
    result.matrix_world = source.matrix_world.copy()
    for polygon in result.data.polygons:
        polygon.use_smooth = True
    return result


def evaluated_world_positions(source: bpy.types.Object) -> list[Vector]:
    depsgraph = bpy.context.evaluated_depsgraph_get()
    evaluated = source.evaluated_get(depsgraph)
    return [evaluated.matrix_world @ vertex.co for vertex in evaluated.data.vertices]


def displacement_evidence(
    previous: list[Vector],
    current: list[Vector],
    frames_per_second: float,
) -> dict[str, float]:
    if len(previous) != len(current):
        raise RuntimeError("Cloth topology changed during Blender simulation")
    distances = [(right - left).length for left, right in zip(previous, current)]
    maximum_index = max(range(len(distances)), key=distances.__getitem__) if distances else None
    maximum = distances[maximum_index] if maximum_index is not None else 0.0
    mean = sum(distances) / len(distances) if distances else 0.0
    ordered = sorted(distances)
    return {
        "maximum_displacement_mm_per_frame": maximum * 1000.0,
        "mean_displacement_mm_per_frame": mean * 1000.0,
        "ninety_fifth_percentile_displacement_mm_per_frame": (
            percentile(ordered, 0.95) * 1000.0
        ),
        "ninety_ninth_point_ninth_percentile_displacement_mm_per_frame": (
            percentile(ordered, 0.999) * 1000.0
        ),
        "maximum_velocity_cm_per_second": maximum * frames_per_second * 100.0,
        "mean_velocity_cm_per_second": mean * frames_per_second * 100.0,
        "maximum_displacement_vertex_index": maximum_index,
        "maximum_displacement_previous_position_m": (
            list(previous[maximum_index]) if maximum_index is not None else None
        ),
        "maximum_displacement_current_position_m": (
            list(current[maximum_index]) if maximum_index is not None else None
        ),
    }


def percentile(sorted_values: list[float], quantile: float) -> float:
    if not sorted_values:
        return 0.0
    position = max(0.0, min(1.0, quantile)) * (len(sorted_values) - 1)
    lower = int(position)
    upper = min(lower + 1, len(sorted_values) - 1)
    fraction = position - lower
    return sorted_values[lower] * (1.0 - fraction) + sorted_values[upper] * fraction


def refinement_strain_evidence(
    source: bpy.types.Object,
    refined: bpy.types.Object,
) -> dict[str, object]:
    if len(source.data.vertices) != len(refined.data.vertices):
        raise RuntimeError("Refined cloth topology does not match its source surface")
    source_points = [source.matrix_world @ vertex.co for vertex in source.data.vertices]
    refined_points = [refined.matrix_world @ vertex.co for vertex in refined.data.vertices]
    samples: list[tuple[float, int, float, float, list[float]]] = []
    for edge_index, edge in enumerate(source.data.edges):
        if edge.is_loose:
            continue
        first, second = edge.vertices
        source_length = (source_points[first] - source_points[second]).length
        if source_length <= 1e-9:
            continue
        refined_length = (refined_points[first] - refined_points[second]).length
        midpoint = (source_points[first] + source_points[second]) * 0.5
        samples.append(
            (
                abs(refined_length / source_length - 1.0),
                edge_index,
                source_length,
                refined_length,
                [midpoint.x, midpoint.y, midpoint.z],
            )
        )
    samples.sort(key=lambda sample: sample[0])
    strains = [sample[0] for sample in samples]
    worst = list(reversed(samples[-10:]))
    strains.sort()
    return {
        "evaluated_edge_count": len(strains),
        "maximum_absolute_strain_ratio": max(strains, default=0.0),
        "ninety_fifth_percentile_absolute_strain_ratio": percentile(strains, 0.95),
        "ninety_ninth_point_ninth_percentile_absolute_strain_ratio": percentile(
            strains,
            0.999,
        ),
        "edges_over_40_percent": sum(value > 0.40 for value in strains),
        "edges_over_29_percent": sum(value > 0.29 for value in strains),
        "worst_edges": [
            {
                "edge_index": edge_index,
                "absolute_strain_ratio": strain,
                "source_length_cm": source_length * 100.0,
                "refined_length_cm": refined_length * 100.0,
                "source_midpoint_m": midpoint,
            }
            for strain, edge_index, source_length, refined_length, midpoint in worst
        ],
    }


def count_body_edge_intersections(
    garment: bpy.types.Object,
    body: bpy.types.Object,
) -> int:
    depsgraph = bpy.context.evaluated_depsgraph_get()
    body_tree = BVHTree.FromObject(body, depsgraph)
    intersections = 0
    for edge in garment.data.edges:
        if edge.is_loose:
            continue
        start = garment.matrix_world @ garment.data.vertices[edge.vertices[0]].co
        end = garment.matrix_world @ garment.data.vertices[edge.vertices[1]].co
        segment = end - start
        length = segment.length
        if length <= 1e-9:
            continue
        hit = body_tree.ray_cast(start, segment / length, length)
        if hit[0] is not None:
            intersections += 1
    return intersections


def export_selected_obj(mesh_object: bpy.types.Object, output_path: Path, scale: float) -> None:
    bpy.ops.object.select_all(action="DESELECT")
    mesh_object.select_set(True)
    bpy.context.view_layer.objects.active = mesh_object
    original_scale = mesh_object.scale.copy()
    mesh_object.scale = tuple(value * scale for value in original_scale)
    bpy.context.view_layer.update()
    bpy.ops.wm.obj_export(
        filepath=str(output_path),
        export_selected_objects=True,
        forward_axis="NEGATIVE_Z",
        up_axis="Y",
        export_materials=False,
    )
    mesh_object.scale = original_scale
    bpy.context.view_layer.update()


def add_studio() -> bpy.types.Object:
    floor_material = principled_material(
        "Patterna studio floor",
        (0.026, 0.030, 0.037, 1.0),
        0.82,
    )
    bpy.ops.mesh.primitive_plane_add(size=8.0, location=(0.0, 0.0, 0.0))
    floor = bpy.context.object
    floor.data.materials.append(floor_material)
    for location, energy, size in (
        ((-1.8, -2.1, 2.55), 920.0, 2.2),
        ((1.7, -0.6, 1.65), 430.0, 2.0),
        ((0.3, 1.7, 2.35), 720.0, 1.7),
    ):
        bpy.ops.object.light_add(type="AREA", location=location)
        light = bpy.context.object
        light.data.energy = energy
        light.data.shape = "DISK"
        light.data.size = size
        point_at(light, Vector((0.0, 0.0, 0.96)))
    bpy.ops.object.camera_add(location=(0.0, 3.05, 0.97))
    camera = bpy.context.object
    camera.data.lens = 67.0
    bpy.context.scene.camera = camera
    return camera


def render_views(
    camera: bpy.types.Object,
    output_directory: Path,
    resolution_x: int,
    resolution_y: int,
    view_set: str,
) -> dict[str, tuple[float, float, float]]:
    scene = bpy.context.scene
    scene.render.engine = "BLENDER_EEVEE_NEXT"
    scene.render.resolution_x = resolution_x
    scene.render.resolution_y = resolution_y
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.render.film_transparent = False
    scene.world.color = (0.007, 0.009, 0.013)
    scene.view_settings.look = "AgX - Medium High Contrast"
    views = {
        "front": (0.0, 3.05, 0.97),
        "front-oblique": (-2.15, 2.15, 1.0),
        "left": (-3.05, 0.0, 0.97),
        "back": (0.0, -3.05, 0.97),
        "back-oblique": (2.15, -2.15, 1.0),
        "right": (3.05, 0.0, 0.97),
    }
    if view_set == "front":
        views = {"front": views["front"]}
    elif view_set == "none":
        return {}
    for name, location in views.items():
        camera.location = location
        point_at(camera, Vector((0.0, 0.0, 0.88)))
        scene.render.filepath = str(output_directory / f"{name}.png")
        bpy.ops.render.render(write_still=True)
    return views


def main() -> None:
    args = parse_args()
    if args.frames < 2:
        raise ValueError("At least two simulation frames are required")
    if args.quality < 1:
        raise ValueError("Cloth quality must be positive")
    if args.gravity_ramp_start_frame < 1:
        raise ValueError("Gravity ramp start frame must be positive")
    if args.gravity_ramp_frames < 0:
        raise ValueError("Gravity ramp frames cannot be negative")

    manifest_path = resolve(args.avatar_manifest)
    garment_path = resolve(args.garment)
    simulation_garment_path = (
        resolve(args.simulation_garment)
        if args.simulation_source == "external"
        else None
    )
    sewing_proxy_path = (
        resolve(args.sewing_proxy)
        if args.simulation_source == "sewing-proxy"
        else None
    )
    fabric_path = resolve(args.fabric)
    output_directory = resolve(args.output_directory)
    output_directory.mkdir(parents=True, exist_ok=True)
    print("Patterna stage: reset scene", flush=True)

    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)

    avatar_objects, avatar_hashes = configure_avatar(manifest_path)
    body = avatar_objects["body"]
    collision_body = create_solver_collider(
        body,
        args.collision_start_horizontal_scale,
        args.collision_ramp_frames,
    )
    print("Patterna stage: avatar and collider ready", flush=True)

    proxy_document = None
    render_source = None
    if args.simulation_source == "sewing-proxy":
        if sewing_proxy_path is None:
            raise RuntimeError("Sewing proxy source has no input sidecar")
        simulation_source, proxy_document = import_sewing_proxy(
            sewing_proxy_path,
            args.sewing_proxy_topology,
        )
        print("Patterna stage: sewing proxy imported", flush=True)
        render_cleanup = {
            "vertices_removed": 0,
            "edges_removed": 0,
            "faces_removed": 0,
            "surface_vertices": len(simulation_source.data.vertices),
            "surface_edges": len(simulation_source.data.edges),
            "surface_faces": len(simulation_source.data.polygons),
        }
    else:
        render_source = import_single_obj(
            garment_path,
            "PatternaSourceRenderGarment",
            scale=0.01,
            forward_axis="NEGATIVE_Z",
            up_axis="Y",
        )
        render_cleanup = remove_non_surface_geometry(render_source)
        render_source.data.materials.clear()
        render_source.data.materials.append(cloth_material(fabric_path))

    position_weld = None
    if args.simulation_source == "remesh":
        if render_source is None:
            raise RuntimeError("Remesh simulation requires a render source")
        simulation_source, position_weld = build_remeshed_simulation_surface(
            render_source,
            args.simulation_target_faces,
        )
    elif args.simulation_source == "external":
        if simulation_garment_path is None:
            raise RuntimeError("External simulation source has no input mesh")
        simulation_source = import_single_obj(
            simulation_garment_path,
            "PatternaSourceSimulationGarment",
            scale=0.01,
            forward_axis="NEGATIVE_Z",
            up_axis="Y",
        )
        if args.external_edge_mode == "surface-only":
            position_weld = weld_coincident_simulation_vertices(simulation_source)
    simulation_cleanup = (
        {
            "vertices_removed": 0,
            "edges_removed": 0,
            "faces_removed": 0,
            "surface_vertices": len(simulation_source.data.vertices),
            "surface_edges": len(simulation_source.data.edges),
            "surface_faces": len(simulation_source.data.polygons),
        }
        if args.simulation_source == "sewing-proxy"
        else remove_non_surface_geometry(
            simulation_source,
            preserve_sewing_edges=(
                args.simulation_source == "external"
                and args.external_edge_mode == "sewing-springs"
            ),
        )
    )
    simulation_mesh_quality = mesh_quality_evidence(simulation_source)
    simulation_source.hide_render = True
    if render_source is not None:
        bind_render_surface(render_source, simulation_source)
        render_source.hide_set(True)

    before_bounds = mesh_bounds(simulation_source)
    render_before_bounds = (
        mesh_bounds(render_source) if render_source is not None else before_bounds
    )
    add_cloth(
        simulation_source,
        args.frames,
        args.quality,
        args.fabric_preset,
        not args.disable_self_collision,
        args.sewing_force_max,
    )
    print("Patterna stage: cloth modifier ready", flush=True)

    scene = bpy.context.scene
    scene.frame_start = 1
    scene.frame_end = args.frames
    scene.render.fps = 30
    if args.gravity_ramp_start_frame > 1 or args.gravity_ramp_frames > 0:
        scene.gravity = (0.0, 0.0, 0.0)
        scene.keyframe_insert(data_path="gravity", frame=1)
        scene.keyframe_insert(
            data_path="gravity",
            frame=args.gravity_ramp_start_frame,
        )
        scene.gravity = (0.0, 0.0, -9.81)
        scene.keyframe_insert(
            data_path="gravity",
            frame=args.gravity_ramp_start_frame + args.gravity_ramp_frames,
        )
        if scene.animation_data and scene.animation_data.action:
            for curve in scene.animation_data.action.fcurves:
                if curve.data_path == "gravity":
                    for keyframe in curve.keyframe_points:
                        keyframe.interpolation = "LINEAR"
    else:
        scene.gravity = (0.0, 0.0, -9.81)
    scene.frame_set(1)

    started = time.perf_counter()
    previous_positions: list[Vector] | None = None
    for frame in range(2, args.frames + 1):
        print(f"Patterna stage: evaluate frame {frame}/{args.frames}", flush=True)
        scene.frame_set(frame)
        if frame == args.frames - 1:
            previous_positions = evaluated_world_positions(simulation_source)
        if frame % 20 == 0 or frame == args.frames:
            print(f"Patterna Blender cloth frame {frame}/{args.frames}")
    solve_seconds = time.perf_counter() - started

    current_positions = evaluated_world_positions(simulation_source)
    if previous_positions is None:
        scene.frame_set(args.frames - 1)
        previous_positions = evaluated_world_positions(simulation_source)
        scene.frame_set(args.frames)
        current_positions = evaluated_world_positions(simulation_source)
    motion = displacement_evidence(previous_positions, current_positions, scene.render.fps)

    refined_simulation = evaluated_copy(
        simulation_source,
        "PatternaRefinedSimulationGarment",
    )
    print("Patterna stage: evaluated simulation copied", flush=True)
    refined_simulation.hide_render = True
    if render_source is None:
        refined = refined_simulation.copy()
        refined.data = refined_simulation.data.copy()
        refined.name = "PatternaRefinedGarment"
        bpy.context.collection.objects.link(refined)
        refined.hide_render = False
        refined.hide_set(False)
        removed_sewing_edges = remove_non_surface_edges(refined)
        refined.data.materials.clear()
        refined.data.materials.append(cloth_material(fabric_path))
        subdivision = refined.modifiers.new(name="Patterna render subdivision", type="SUBSURF")
        subdivision.subdivision_type = "CATMULL_CLARK"
        subdivision.levels = 1
        subdivision.render_levels = 1
    else:
        removed_sewing_edges = 0
        render_source.hide_set(False)
        scene.frame_set(args.frames)
        bpy.context.view_layer.update()
        refined = evaluated_copy(render_source, "PatternaRefinedGarment")
    simulation_source.hide_render = True
    simulation_source.hide_set(True)
    if render_source is not None:
        render_source.hide_render = True
        render_source.hide_set(True)
    after_bounds = mesh_bounds(refined_simulation)
    render_after_bounds = mesh_bounds(refined)

    conservative_body_ray_hits = count_body_edge_intersections(refined, body)
    refinement_strain = refinement_strain_evidence(
        simulation_source,
        refined_simulation,
    )
    print("Patterna stage: geometry evidence calculated", flush=True)

    simulation_meter_obj = output_directory / "garment-simulation-refined-m.obj"
    simulation_centimeter_obj = output_directory / "garment-simulation-refined-cm.obj"
    export_selected_obj(refined_simulation, simulation_meter_obj, 1.0)
    export_selected_obj(refined_simulation, simulation_centimeter_obj, 100.0)

    meter_obj = output_directory / "garment-refined-m.obj"
    centimeter_obj = output_directory / "garment-refined-cm.obj"
    export_selected_obj(refined, meter_obj, 1.0)
    export_selected_obj(refined, centimeter_obj, 100.0)
    print("Patterna stage: output meshes exported", flush=True)

    solidify = refined.modifiers.new(name="Physical fabric thickness", type="SOLIDIFY")
    solidify.thickness = 0.00034
    solidify.offset = 1.0
    solidify.use_even_offset = True

    camera = add_studio()
    views = render_views(
        camera,
        output_directory,
        args.resolution_x,
        args.resolution_y,
        args.render_view_set,
    )
    scene_path = output_directory / "blender-cloth-vertical-slice.blend"
    bpy.ops.wm.save_as_mainfile(filepath=str(scene_path))
    print("Patterna stage: scene saved", flush=True)

    evidence = {
        "schema_version": "patterna.blender-cloth-proof/1.0",
        "source_avatar_manifest": str(manifest_path),
        "source_avatar_hashes": avatar_hashes,
        "source_garment": str(garment_path),
        "source_garment_sha256": sha256(garment_path),
        "simulation_source": args.simulation_source,
        "simulation_target_faces": args.simulation_target_faces,
        "source_simulation_garment": (
            str(simulation_garment_path) if simulation_garment_path else None
        ),
        "source_simulation_garment_sha256": (
            sha256(simulation_garment_path) if simulation_garment_path else None
        ),
        "source_sewing_proxy": str(sewing_proxy_path) if sewing_proxy_path else None,
        "source_sewing_proxy_sha256": sha256(sewing_proxy_path) if sewing_proxy_path else None,
        "sewing_proxy_panel_count": len(proxy_document["panels"]) if proxy_document else None,
        "sewing_proxy_seam_count": len(proxy_document["seams"]) if proxy_document else None,
        "render_sewing_edges_removed": removed_sewing_edges,
        "fabric_texture": str(fabric_path),
        "fabric_texture_sha256": sha256(fabric_path),
        "solver": f"Blender Cloth {bpy.app.version_string}",
        "frames": args.frames,
        "quality": args.quality,
        "fabric_preset": args.fabric_preset,
        "fabric_solver_values": FABRIC_PRESETS[args.fabric_preset],
        "solve_seconds": solve_seconds,
        "render_cleanup": render_cleanup,
        "simulation_cleanup": simulation_cleanup,
        "simulation_position_weld": position_weld,
        "simulation_mesh_quality": simulation_mesh_quality,
        "before_bounds_m": before_bounds,
        "after_bounds_m": after_bounds,
        "render_before_bounds_m": render_before_bounds,
        "render_after_bounds_m": render_after_bounds,
        "motion": motion,
        "refinement_strain": refinement_strain,
        "conservative_body_ray_hits": conservative_body_ray_hits,
        "conservative_body_ray_hits_authoritative": False,
        "simulation_vertex_count": len(refined_simulation.data.vertices),
        "simulation_face_count": len(refined_simulation.data.polygons),
        "surface_vertex_count": len(refined.data.vertices),
        "surface_face_count": len(refined.data.polygons),
        "visual_thickness_mm": 0.34,
        "body_collision_envelope_mm": 2.5,
        "collision_body": collision_body.name,
        "collision_start_horizontal_scale": args.collision_start_horizontal_scale,
        "collision_ramp_frames": args.collision_ramp_frames,
        "self_collision_distance_mm": 1.6,
        "self_collision_enabled": not args.disable_self_collision,
        "sewing_force_max": args.sewing_force_max,
        "gravity_ramp_start_frame": args.gravity_ramp_start_frame,
        "gravity_ramp_frames": args.gravity_ramp_frames,
        "external_edge_mode": (
            args.external_edge_mode
            if args.simulation_source == "external"
            else None
        ),
        "sewing_proxy_arrangement": proxy_document.get("blenderArrangement") if proxy_document else None,
        "sewing_proxy_topology": proxy_document.get("blenderTopology") if proxy_document else None,
        "outputs": {
            "meter_obj": meter_obj.name,
            "meter_obj_sha256": sha256(meter_obj),
            "centimeter_obj": centimeter_obj.name,
            "centimeter_obj_sha256": sha256(centimeter_obj),
            "simulation_meter_obj": simulation_meter_obj.name,
            "simulation_meter_obj_sha256": sha256(simulation_meter_obj),
            "simulation_centimeter_obj": simulation_centimeter_obj.name,
            "simulation_centimeter_obj_sha256": sha256(
                simulation_centimeter_obj
            ),
            "blend": scene_path.name,
            "renders": {name: f"{name}.png" for name in views},
        },
    }
    (output_directory / "report.json").write_text(
        json.dumps(evidence, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"Rendered Blender cloth proof to {output_directory}")


if __name__ == "__main__":
    main()
