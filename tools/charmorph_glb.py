#!/usr/bin/env python3
"""Build a licensed multi-material GLB candidate from a fitted CharMorph body."""

from __future__ import annotations

from collections import Counter
import hashlib
import json
import math
from pathlib import Path
from typing import Any

import bpy
from mathutils import Vector

from charmorph_character import CharacterDescriptor


SKIN_REGIONS = {
    "cm_antonia_arms": "arms",
    "cm_antonia_body": "body",
    "cm_antonia_head": "head",
    "cm_antonia_legs": "legs",
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def texture_by_stem(character: CharacterDescriptor, stem: str) -> Path | None:
    lowered = stem.lower()
    return next((path for path in character.texture_paths if path.stem.lower() == lowered), None)


def image_node(
    nodes: bpy.types.Nodes,
    path: Path,
    *,
    non_color: bool = False,
) -> bpy.types.ShaderNodeTexImage:
    image = bpy.data.images.load(str(path), check_existing=True)
    image.colorspace_settings.name = "Non-Color" if non_color else "sRGB"
    node = nodes.new("ShaderNodeTexImage")
    node.image = image
    node.label = path.name
    return node


def material_texture_stems(material_name: str) -> tuple[str | None, str | None, str | None]:
    region = SKIN_REGIONS.get(material_name)
    if region is not None:
        return f"{region}_albedo", f"{region}_bump", f"{region}_gloss"
    if material_name in {"cm_antonia_iris", "cm_antonia_sclera"}:
        return "eyes", None, None
    if material_name == "cm_antonia_mouth":
        return "mouth", None, None
    return None, None, None


def configure_character_material(
    material_name: str,
    character: CharacterDescriptor,
) -> tuple[bpy.types.Material, dict[str, str]]:
    material = bpy.data.materials.get(material_name) or bpy.data.materials.new(material_name)
    material.use_nodes = True
    nodes = material.node_tree.nodes
    links = material.node_tree.links
    nodes.clear()
    output = nodes.new("ShaderNodeOutputMaterial")
    principled = nodes.new("ShaderNodeBsdfPrincipled")
    links.new(principled.outputs["BSDF"], output.inputs["Surface"])
    principled.inputs["Metallic"].default_value = 0.0
    principled.inputs["Roughness"].default_value = 0.58
    source_textures: dict[str, str] = {}

    base_stem, bump_stem, gloss_stem = material_texture_stems(material_name)
    if base_stem:
        base_path = texture_by_stem(character, base_stem)
        if base_path is None:
            raise FileNotFoundError(f"Antonia material texture is missing: {base_stem}")
        base = image_node(nodes, base_path)
        links.new(base.outputs["Color"], principled.inputs["Base Color"])
        source_textures["baseColor"] = str(base_path)

    if bump_stem:
        bump_path = texture_by_stem(character, bump_stem)
        if bump_path is None:
            raise FileNotFoundError(f"Antonia height texture is missing: {bump_stem}")
        source_textures["height"] = str(bump_path)

    if gloss_stem:
        gloss_path = texture_by_stem(character, gloss_stem)
        if gloss_path is None:
            raise FileNotFoundError(f"Antonia gloss texture is missing: {gloss_stem}")
        source_textures["gloss"] = str(gloss_path)

    fallback_colors = {
        "cm_antonia_cornea": (1.0, 1.0, 1.0, 0.0),
        "charmorph_pupil": (0.008, 0.006, 0.005, 1.0),
        "cm_antonia_nails": (0.42, 0.18, 0.14, 1.0),
        "charmorph_eyelashes": (0.012, 0.008, 0.006, 1.0),
    }
    if material_name in fallback_colors:
        color = fallback_colors[material_name]
        principled.inputs["Base Color"].default_value = color
        principled.inputs["Alpha"].default_value = color[3]
    if material_name == "cm_antonia_cornea":
        principled.inputs["Roughness"].default_value = 0.08
        principled.inputs["Transmission Weight"].default_value = 0.0
        if hasattr(material, "surface_render_method"):
            material.surface_render_method = "DITHERED"
        elif hasattr(material, "blend_method"):
            material.blend_method = "BLEND"
    elif material_name in {"cm_antonia_iris", "cm_antonia_sclera", "charmorph_pupil"}:
        principled.inputs["Roughness"].default_value = 0.24
    elif material_name in {"cm_antonia_mouth", "cm_antonia_nails"}:
        principled.inputs["Roughness"].default_value = 0.38
    elif material_name == "charmorph_eyelashes":
        principled.inputs["Roughness"].default_value = 0.76

    material.diffuse_color = tuple(principled.inputs["Base Color"].default_value)
    return material, source_textures


def assign_character_materials(
    body: bpy.types.Object,
    character: CharacterDescriptor,
) -> dict[str, dict[str, str]]:
    if not character.material_names:
        raise ValueError(f"{character.title} has no configured material slots")
    highest_index = max((polygon.material_index for polygon in body.data.polygons), default=-1)
    if highest_index >= len(character.material_names):
        raise ValueError(
            f"{character.title} uses material index {highest_index} but declares only "
            f"{len(character.material_names)} slots"
        )
    polygon_material_indices = [polygon.material_index for polygon in body.data.polygons]
    body.data.materials.clear()
    cache: dict[str, bpy.types.Material] = {}
    evidence: dict[str, dict[str, str]] = {}
    for material_name in character.material_names:
        if material_name not in cache:
            material, textures = configure_character_material(material_name, character)
            cache[material_name] = material
            evidence[material_name] = textures
        body.data.materials.append(cache[material_name])
    for polygon, material_index in zip(body.data.polygons, polygon_material_indices):
        polygon.material_index = material_index
        polygon.use_smooth = True
    return evidence


def configure_underwear_material(
    material: bpy.types.Material,
    texture_path: Path,
) -> None:
    material.use_nodes = True
    nodes = material.node_tree.nodes
    links = material.node_tree.links
    nodes.clear()
    output = nodes.new("ShaderNodeOutputMaterial")
    principled = nodes.new("ShaderNodeBsdfPrincipled")
    principled.inputs["Roughness"].default_value = 0.72
    texture = image_node(nodes, texture_path)
    tint = nodes.new("ShaderNodeMixRGB")
    tint.blend_type = "MULTIPLY"
    tint.inputs[0].default_value = 1.0
    tint.inputs[2].default_value = (0.08, 0.16, 0.28, 1.0)
    links.new(texture.outputs["Color"], tint.inputs[1])
    links.new(tint.outputs["Color"], principled.inputs["Base Color"])
    links.new(principled.outputs["BSDF"], output.inputs["Surface"])


def configure_bandeau_material(material: bpy.types.Material) -> None:
    material.use_nodes = True
    nodes = material.node_tree.nodes
    links = material.node_tree.links
    nodes.clear()
    output = nodes.new("ShaderNodeOutputMaterial")
    principled = nodes.new("ShaderNodeBsdfPrincipled")
    principled.inputs["Base Color"].default_value = (0.055, 0.10, 0.18, 1.0)
    principled.inputs["Roughness"].default_value = 0.78
    links.new(principled.outputs["BSDF"], output.inputs["Surface"])


def build_modesty_bandeau(
    body: bpy.types.Object,
) -> bpy.types.Object:
    coordinates = [body.matrix_world @ vertex.co for vertex in body.data.vertices]
    floor_z = min(point.z for point in coordinates)
    height_m = max(point.z for point in coordinates) - floor_z
    angular_segments = 96
    vertical_segments = 12
    lower_ratio = 0.665
    upper_ratio = 0.760
    vertices: list[tuple[float, float, float]] = []
    faces: list[tuple[int, int, int, int]] = []
    for vertical_index in range(vertical_segments + 1):
        fraction = vertical_index / vertical_segments
        z = floor_z + (lower_ratio + (upper_ratio - lower_ratio) * fraction) * height_m
        half_band = 0.012 * height_m
        section = [
            point
            for point in coordinates
            if abs(point.z - z) <= half_band and abs(point.x) <= 0.24
        ]
        if len(section) < 24:
            raise RuntimeError(f"Could not sample Antonia bandeau section at z={z:.6f}")
        for angular_index in range(angular_segments):
            theta = 2.0 * math.pi * angular_index / angular_segments
            direction_x = math.sin(theta)
            direction_y = math.cos(theta)
            radius = max(
                point.x * direction_x + point.y * direction_y
                for point in section
            ) + 0.004
            vertices.append((direction_x * radius, direction_y * radius, z))
    ring_stride = angular_segments
    for vertical_index in range(vertical_segments):
        row = vertical_index * ring_stride
        next_row = row + ring_stride
        for angular_index in range(angular_segments):
            next_angular = (angular_index + 1) % angular_segments
            faces.append((
                row + angular_index,
                row + next_angular,
                next_row + next_angular,
                next_row + angular_index,
            ))
    mesh = bpy.data.meshes.new("Patterna_Antonia_BraMesh")
    mesh.from_pydata(vertices, [], faces)
    mesh.update()
    asset = bpy.data.objects.new("Patterna_Antonia_ModestyBandeau", mesh)
    bpy.context.collection.objects.link(asset)
    asset.name = "Patterna_Antonia_ModestyBandeau"
    asset.data.name = "Patterna_Antonia_ModestyBandeauMesh"
    for polygon in asset.data.polygons:
        polygon.use_smooth = True
    asset.data.materials.clear()
    material = bpy.data.materials.new("Patterna modesty bandeau")
    configure_bandeau_material(material)
    asset.data.materials.append(material)
    return asset


def append_underwear(
    character: CharacterDescriptor,
    name: str,
    height_scale: float,
    body: bpy.types.Object,
) -> bpy.types.Object:
    asset_path = character.directory / "assets" / f"{name}.blend"
    if not asset_path.is_file():
        raise FileNotFoundError(f"Antonia underwear source is missing: {asset_path}")
    with bpy.data.libraries.load(str(asset_path), link=False) as (available, requested):
        if name not in available.objects:
            raise ValueError(f"Antonia underwear object {name!r} is absent from {asset_path}")
        requested.objects = [name]
    asset = requested.objects[0]
    if asset is None or asset.type != "MESH":
        raise ValueError(f"Antonia underwear object {name!r} is not a mesh")
    bpy.context.collection.objects.link(asset)
    asset.name = f"Patterna_Antonia_{name.title()}"
    asset.scale = (height_scale, height_scale, height_scale)
    bpy.context.view_layer.objects.active = asset
    asset.select_set(True)
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    shrinkwrap = asset.modifiers.new(name="PatternaBodyFit", type="SHRINKWRAP")
    shrinkwrap.target = body
    shrinkwrap.wrap_method = "NEAREST_SURFACEPOINT"
    shrinkwrap.wrap_mode = "OUTSIDE_SURFACE"
    shrinkwrap.offset = 0.0025
    asset.modifiers.move(len(asset.modifiers) - 1, 0)
    bpy.ops.object.modifier_apply(modifier=shrinkwrap.name)
    for polygon in asset.data.polygons:
        polygon.use_smooth = True
    texture_path = character.directory / "assets" / "textures" / "underwear.png"
    if not texture_path.is_file():
        raise FileNotFoundError(f"Antonia underwear texture is missing: {texture_path}")
    if not asset.data.materials:
        asset.data.materials.append(bpy.data.materials.new(f"Patterna {name}"))
    for material in asset.data.materials:
        if material is not None:
            configure_underwear_material(material, texture_path)
    return asset


def point_at(obj: bpy.types.Object, target: Vector) -> None:
    obj.rotation_euler = (target - obj.location).to_track_quat("-Z", "Y").to_euler()


def render_candidate_views(
    objects: list[bpy.types.Object],
    output_directory: Path,
    floor_offset_m: float,
    height_m: float,
) -> dict[str, dict[str, Any]]:
    output_directory.mkdir(parents=True, exist_ok=True)
    bpy.ops.mesh.primitive_plane_add(size=7.0, location=(0.0, 0.0, floor_offset_m - 0.002))
    floor = bpy.context.object
    floor_material = bpy.data.materials.new("Patterna candidate studio floor")
    floor_material.diffuse_color = (0.035, 0.039, 0.048, 1.0)
    floor.data.materials.append(floor_material)

    target = Vector((0.0, 0.0, floor_offset_m + height_m * 0.52))
    for location, energy, size in (
        ((-1.7, -2.0, floor_offset_m + height_m * 1.55), 620.0, 2.2),
        ((1.8, -0.7, floor_offset_m + height_m * 1.05), 280.0, 2.0),
        ((0.4, 1.5, floor_offset_m + height_m * 1.42), 420.0, 1.6),
    ):
        bpy.ops.object.light_add(type="AREA", location=location)
        light = bpy.context.object
        light.data.energy = energy
        light.data.shape = "DISK"
        light.data.size = size
        point_at(light, target)

    distance = max(2.85, height_m * 1.82)
    camera_z = floor_offset_m + height_m * 0.56
    bpy.ops.object.camera_add(location=(0.0, distance, camera_z))
    camera = bpy.context.object
    camera.data.lens = 67.0
    bpy.context.scene.camera = camera
    views = {
        "front": (0.0, -distance, camera_z),
        "front-oblique": (distance * 0.71, -distance * 0.71, camera_z),
        "left": (-distance, 0.0, camera_z),
        "back": (0.0, distance, camera_z),
        "back-oblique": (-distance * 0.71, distance * 0.71, camera_z),
        "right": (distance, 0.0, camera_z),
    }
    scene = bpy.context.scene
    scene.render.engine = "BLENDER_EEVEE_NEXT"
    scene.render.resolution_x = 720
    scene.render.resolution_y = 900
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGBA"
    scene.render.film_transparent = False
    if scene.world is None:
        scene.world = bpy.data.worlds.new("Patterna candidate studio world")
    scene.world.color = (0.008, 0.010, 0.015)
    scene.view_settings.exposure = -1.0
    try:
        scene.view_settings.look = "AgX - Medium High Contrast"
    except TypeError:
        scene.view_settings.look = "Medium High Contrast"
    evidence: dict[str, dict[str, Any]] = {}
    for name, location in views.items():
        camera.location = location
        point_at(camera, target)
        output_path = output_directory / f"{name}.png"
        scene.render.filepath = str(output_path)
        bpy.ops.render.render(write_still=True)
        evidence[name] = {
            "path": output_path.name,
            "sha256": sha256(output_path),
            "byteCount": output_path.stat().st_size,
        }
    for obj in objects:
        obj.select_set(False)
    return evidence


def obj_vertices(path: Path) -> list[Vector]:
    vertices: list[Vector] = []
    with path.open("r", encoding="utf-8") as source:
        for line in source:
            if line.startswith("v "):
                _, x, y, z = line.split()
                vertices.append(Vector((float(x), float(y), float(z))))
    return vertices


def collision_registration(body: bpy.types.Object, collision_path: Path) -> dict[str, Any]:
    collision_vertices = [
        Vector((-vertex.x, -vertex.y, vertex.z))
        for vertex in obj_vertices(collision_path)
    ]
    body_vertices = [body.matrix_world @ vertex.co for vertex in body.data.vertices]
    if len(collision_vertices) != len(body_vertices):
        raise ValueError(
            f"Collision OBJ has {len(collision_vertices)} vertices but the display body has "
            f"{len(body_vertices)}"
        )
    maximum_distance = max(
        (display - collision).length
        for display, collision in zip(body_vertices, collision_vertices)
    )
    if not math.isfinite(maximum_distance) or maximum_distance > 0.00001:
        raise ValueError(
            f"Collision OBJ diverges from the fitted display body by {maximum_distance:.9f} m"
        )
    return {
        "method": "vertex-order comparison after OBJ negative-X and negative-Y decoding",
        "objToBlenderTransform": "(-x, -y, z)",
        "maximumBodyToCollisionDistanceM": maximum_distance,
        "bodyAndCollisionVertexCountMatch": True,
        "comparedVertexCount": len(body_vertices),
    }


def export_glb_candidate(
    body: bpy.types.Object,
    character: CharacterDescriptor,
    collision_path: Path,
    output_path: Path,
    render_output_directory: Path | None,
    height_scale: float,
    target_height_cm: float,
    fit_report: dict[str, Any] | None,
    fit_report_path: Path | None,
) -> dict[str, Any]:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    material_evidence = assign_character_materials(body, character)
    body.name = "Patterna_Antonia_Body"
    body.data.name = "Patterna_Antonia_BodyMesh"
    body_coordinates = [body.matrix_world @ vertex.co for vertex in body.data.vertices]
    floor_offset_m = min(point.z for point in body_coordinates)
    height_m = max(point.z for point in body_coordinates) - floor_offset_m
    components = [body]
    for name in character.underwear_names:
        if name == "bra":
            components.append(build_modesty_bandeau(body))
        else:
            components.append(append_underwear(character, name, height_scale, body))
    registration = collision_registration(body, collision_path)

    bpy.ops.object.select_all(action="DESELECT")
    for component in components:
        component.select_set(True)
    bpy.context.view_layer.objects.active = body
    bpy.ops.export_scene.gltf(
        filepath=str(output_path),
        export_format="GLB",
        use_selection=True,
        export_apply=True,
        export_texcoords=True,
        export_normals=True,
        export_materials="EXPORT",
        export_cameras=False,
        export_lights=False,
        export_animations=False,
        export_yup=True,
    )
    if not output_path.is_file() or output_path.stat().st_size < 1024:
        raise RuntimeError(f"Blender did not produce a usable GLB: {output_path}")

    render_evidence = (
        render_candidate_views(components, render_output_directory, floor_offset_m, height_m)
        if render_output_directory is not None
        else {}
    )
    polygon_counts = Counter(polygon.material_index for polygon in body.data.polygons)
    open_gates = [
        "underwear is body-conformed but not pattern-sized",
        "hair geometry is unavailable",
        "height maps have not been converted to tangent-space normal maps",
        "collision simplification and regional registration are not implemented",
        "packaged WinUI GLB loading is not implemented",
        "cloth has not been solved on this body",
    ]
    if fit_report is None or not fit_report.get("accepted"):
        open_gates.insert(0, "primary circumference fit is not yet accepted for Antonia")
    manifest = {
        "schemaVersion": "patterna.display-avatar-glb/1.0",
        "accepted": False,
        "candidateOnly": True,
        "source": character.title,
        "author": character.author,
        "additionalAuthors": character.additional_authors,
        "sourceUrl": character.source_url,
        "outputLicense": character.license_name,
        "licenseFile": str(character.license_path),
        "licenseSha256": sha256(character.license_path),
        "geometry": output_path.name,
        "geometrySha256": sha256(output_path),
        "geometryBytes": output_path.stat().st_size,
        "collisionGeometry": str(collision_path),
        "collisionGeometrySha256": sha256(collision_path),
        "heightTargetCm": target_height_cm,
        "heightMeasuredCm": height_m * 100.0,
        "heightErrorMm": abs(height_m * 100.0 - target_height_cm) * 10.0,
        "measurementFit": {
            "accepted": bool(fit_report and fit_report.get("accepted")),
            "report": str(fit_report_path) if fit_report_path else None,
            "reportSha256": sha256(fit_report_path) if fit_report_path else None,
            "maximumAbsoluteResidualCm": (
                fit_report.get("maximumAbsoluteResidualCm") if fit_report else None
            ),
            "bustSeparationResidualCm": (
                fit_report.get("bustSeparationResidualCm") if fit_report else None
            ),
        },
        "floorOffsetM": floor_offset_m,
        "bodyVertexCount": len(body.data.vertices),
        "bodyPolygonCount": len(body.data.polygons),
        "bodyUvLayers": [layer.name for layer in body.data.uv_layers],
        "materialSlots": list(character.material_names),
        "materialPolygonCounts": {str(index): count for index, count in sorted(polygon_counts.items())},
        "materialSourceTextures": material_evidence,
        "components": {
            component.name: {
                "vertexCount": len(component.data.vertices),
                "polygonCount": len(component.data.polygons),
            }
            for component in components
        },
        "registration": registration,
        "renders": render_evidence,
        "openGates": open_gates,
    }
    manifest_path = output_path.with_suffix(".manifest.json")
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return manifest
