#!/usr/bin/env python3
"""Render the exact packaged avatar and garment as a six-view review proof."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys
import traceback

import bpy
from mathutils import Vector

sys.path.insert(0, str(Path(__file__).resolve().parent))
from product_registration import evaluate_upper_body_registration


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_AVATAR_MANIFEST = Path("Patternal/Assets/Production/Avatar/manifest.json")
DEFAULT_GARMENT = Path("Patternal/Assets/Production/patterna-production-crew-neck.obj")
DEFAULT_FABRIC = Path("third_party/GarmentCode/assets/img/fabric_texture.png")
DEFAULT_OUTPUT_DIRECTORY = Path("artifacts/product-acceptance/current")


def blender_arguments() -> list[str]:
    return sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--avatar-manifest", type=Path, default=DEFAULT_AVATAR_MANIFEST)
    parser.add_argument("--garment", type=Path, default=DEFAULT_GARMENT)
    parser.add_argument("--fabric", type=Path, default=DEFAULT_FABRIC)
    parser.add_argument("--output-directory", type=Path, default=DEFAULT_OUTPUT_DIRECTORY)
    parser.add_argument("--resolution-x", type=int, default=720)
    parser.add_argument("--resolution-y", type=int, default=900)
    parser.add_argument("--garment-scale", type=float, default=0.01)
    parser.add_argument("--garment-z-up", action="store_true")
    parser.add_argument("--hide-bra", action="store_true")
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


def import_obj(
    path: Path,
    name: str,
    scale: float,
    *,
    forward_axis: str = "NEGATIVE_Z",
    up_axis: str = "Y",
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
    mesh = meshes[0]
    mesh.name = name
    mesh.scale = (scale, scale, scale)
    for polygon in mesh.data.polygons:
        polygon.use_smooth = True
    return mesh


def principled_material(
    name: str,
    color: tuple[float, float, float, float],
    roughness: float,
    texture_path: Path | None = None,
    subsurface_weight: float = 0.0,
    alpha_clip: bool = False,
    texture_tint: tuple[float, float, float, float] | None = None,
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
        if texture_tint is None:
            links.new(texture.outputs["Color"], principled.inputs["Base Color"])
        else:
            tint = nodes.new("ShaderNodeRGB")
            tint.outputs["Color"].default_value = texture_tint
            color_multiply = nodes.new("ShaderNodeMixRGB")
            color_multiply.blend_type = "MULTIPLY"
            color_multiply.inputs["Fac"].default_value = 1.0
            links.new(texture.outputs["Color"], color_multiply.inputs[1])
            links.new(tint.outputs["Color"], color_multiply.inputs[2])
            links.new(color_multiply.outputs["Color"], principled.inputs["Base Color"])
        if alpha_clip:
            links.new(texture.outputs["Alpha"], principled.inputs["Alpha"])
            material.diffuse_color = (*color[:3], 1.0)
            if hasattr(material, "surface_render_method"):
                material.surface_render_method = "DITHERED"
    return material


def cloth_material(texture_path: Path) -> bpy.types.Material:
    material = principled_material(
        "Patterna woven cotton",
        (0.34, 0.025, 0.07, 1.0),
        0.68,
        texture_path,
    )
    nodes = material.node_tree.nodes
    links = material.node_tree.links
    principled = nodes.get("Principled BSDF")
    principled.inputs["Sheen Weight"].default_value = 0.18
    texture = next(node for node in nodes if node.bl_idname == "ShaderNodeTexImage")
    for link in list(principled.inputs["Base Color"].links):
        links.remove(link)
    base_color = nodes.new("ShaderNodeRGB")
    base_color.outputs["Color"].default_value = (0.30, 0.025, 0.08, 1.0)
    color_multiply = nodes.new("ShaderNodeMixRGB")
    color_multiply.blend_type = "MULTIPLY"
    color_multiply.inputs["Fac"].default_value = 1.0
    links.new(texture.outputs["Color"], color_multiply.inputs[1])
    links.new(base_color.outputs["Color"], color_multiply.inputs[2])
    links.new(color_multiply.outputs["Color"], principled.inputs["Base Color"])
    noise = nodes.new("ShaderNodeTexNoise")
    noise.inputs["Scale"].default_value = 380.0
    noise.inputs["Detail"].default_value = 2.0
    noise.inputs["Roughness"].default_value = 0.64
    bump = nodes.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value = 0.08
    bump.inputs["Distance"].default_value = 0.00014
    links.new(noise.outputs["Fac"], bump.inputs["Height"])
    links.new(bump.outputs["Normal"], principled.inputs["Normal"])
    return material


def assign_material(mesh: bpy.types.Object, material: bpy.types.Material) -> None:
    mesh.data.materials.clear()
    mesh.data.materials.append(material)


def configure_glb_avatar(
    manifest_path: Path,
    manifest: dict[str, object],
    *,
    show_bra: bool,
) -> tuple[dict[str, bpy.types.Object], dict[str, str]]:
    base = manifest_path.parent
    geometry_path = base / str(manifest.get("geometry", ""))
    license_path = base / str(manifest.get("licenseFile", ""))
    if (
        not geometry_path.is_file()
        or geometry_path.stat().st_size != manifest.get("geometryBytes")
        or sha256(geometry_path) != manifest.get("geometrySha256")
    ):
        raise RuntimeError("Display avatar GLB does not match its manifest.")
    if not license_path.is_file() or sha256(license_path) != manifest.get("licenseSha256"):
        raise RuntimeError("Display avatar license does not match its manifest.")
    if manifest.get("measurementFit", {}).get("accepted") is not True:
        raise RuntimeError("Display avatar measurement fit is not accepted.")

    before = set(bpy.context.scene.objects)
    bpy.ops.import_scene.gltf(filepath=str(geometry_path))
    imported = [obj for obj in bpy.context.scene.objects if obj not in before]
    meshes = [obj for obj in imported if obj.type == "MESH"]
    if not meshes:
        raise RuntimeError("Display avatar GLB contains no mesh objects.")
    body = max(meshes, key=lambda obj: len(obj.data.vertices))
    if not show_bra:
        for mesh in list(meshes):
            if "bandeau" in mesh.name.lower() or "bra" in mesh.name.lower():
                bpy.data.objects.remove(mesh, do_unlink=True)
                meshes.remove(mesh)
    floor_offset_m = manifest.get("floorOffsetM")
    if not isinstance(floor_offset_m, (int, float)) or not -0.5 <= float(floor_offset_m) <= 0.5:
        raise RuntimeError(f"Display avatar floor offset is invalid: {floor_offset_m!r}")
    for mesh in meshes:
        mesh.location.z -= float(floor_offset_m)
    objects = {"body": body}
    for index, mesh in enumerate(mesh for mesh in meshes if mesh != body):
        objects[f"component_{index}"] = mesh
    return objects, {
        "manifest": sha256(manifest_path),
        "body_geometry": sha256(geometry_path),
        "avatar_license": sha256(license_path),
    }


def configure_avatar(
    manifest_path: Path,
    *,
    show_bra: bool = True,
) -> tuple[dict[str, bpy.types.Object], dict[str, str]]:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("schemaVersion") == "patterna.display-avatar-glb/1.0":
        return configure_glb_avatar(manifest_path, manifest, show_bra=show_bra)
    if manifest.get("schema_version") != "patterna.display-avatar/1.0":
        raise RuntimeError("Unsupported display-avatar manifest schema")
    base = manifest_path.parent
    objects: dict[str, bpy.types.Object] = {}
    hashes: dict[str, str] = {"manifest": sha256(manifest_path)}
    settings = {
        "body": ((0.48, 0.25, 0.16, 1.0), 0.48, 0.08, False),
        "eyes": ((0.72, 0.72, 0.68, 1.0), 0.24, 0.0, False),
        "teeth": ((0.80, 0.78, 0.70, 1.0), 0.34, 0.0, False),
        "eyebrows": ((0.025, 0.018, 0.014, 1.0), 0.72, 0.0, True),
        "eyelashes": ((0.01, 0.008, 0.007, 1.0), 0.76, 0.0, True),
        "hair": ((0.018, 0.012, 0.009, 1.0), 0.68, 0.0, True),
        "bra": ((0.018, 0.035, 0.055, 1.0), 0.72, 0.0, False),
    }
    for asset_name, asset in manifest["assets"].items():
        if asset_name == "bra" and not show_bra:
            continue
        geometry_path = base / asset["geometry"]
        texture_path = base / asset["texture"]
        color, roughness, subsurface_weight, alpha_clip = settings[asset_name]
        manifest_color = asset.get("color")
        texture_tint = None
        if manifest_color is not None:
            if (
                not isinstance(manifest_color, list)
                or len(manifest_color) != 3
                or not all(isinstance(component, (int, float)) for component in manifest_color)
                or not all(0.0 <= float(component) <= 1.0 for component in manifest_color)
            ):
                raise RuntimeError(f"Display avatar asset {asset_name} has an invalid color tint")
            texture_tint = tuple(float(component) for component in manifest_color) + (1.0,)
        mesh = import_obj(
            geometry_path,
            f"PatternaAvatar_{asset_name}",
            1.0,
            forward_axis="NEGATIVE_Y",
            up_axis="Z",
        )
        assign_material(
            mesh,
            principled_material(
                f"Patterna {asset_name}",
                color,
                roughness,
                texture_path,
                subsurface_weight,
                alpha_clip,
                texture_tint,
            ),
        )
        objects[asset_name] = mesh
        hashes[f"{asset_name}_geometry"] = sha256(geometry_path)
        hashes[f"{asset_name}_texture"] = sha256(texture_path)
    floor_offset_m = manifest.get("floor_offset_m")
    if not isinstance(floor_offset_m, (int, float)):
        body_coordinates = [
            objects["body"].matrix_world @ vertex.co
            for vertex in objects["body"].data.vertices
        ]
        floor_offset_m = min(point.z for point in body_coordinates)
    if not -0.5 <= float(floor_offset_m) <= 0.5:
        raise RuntimeError(
            f"Display avatar floor offset is invalid: {floor_offset_m!r}"
        )
    for mesh in objects.values():
        mesh.location.z -= float(floor_offset_m)
    return objects, hashes


def world_bounds(mesh: bpy.types.Object) -> dict[str, list[float]]:
    coordinates = [mesh.matrix_world @ vertex.co for vertex in mesh.data.vertices]
    minimum = [min(point[axis] for point in coordinates) for axis in range(3)]
    maximum = [max(point[axis] for point in coordinates) for axis in range(3)]
    return {"minimum": minimum, "maximum": maximum}


def validate_registration(
    body: bpy.types.Object,
    garment: bpy.types.Object,
) -> dict[str, object]:
    body_bounds = world_bounds(body)
    garment_bounds = world_bounds(garment)
    evidence = evaluate_upper_body_registration(body_bounds, garment_bounds)
    if not evidence["accepted"]:
        raise RuntimeError(
            "Product registration failed: "
            + " ".join(evidence["issues"])
            + " Evidence: "
            + json.dumps(evidence)
        )
    return evidence


def add_studio() -> bpy.types.Object:
    floor_material = principled_material(
        "Patterna studio floor",
        (0.035, 0.04, 0.05, 1.0),
        0.74,
    )
    bpy.ops.mesh.primitive_plane_add(size=8.0, location=(0.0, 0.0, 0.0))
    floor = bpy.context.object
    assign_material(floor, floor_material)
    for location, energy, size in (
        ((-1.7, -2.0, 2.6), 1050.0, 2.2),
        ((1.8, -0.7, 1.7), 560.0, 2.0),
        ((0.4, 1.5, 2.35), 820.0, 1.6),
    ):
        bpy.ops.object.light_add(type="AREA", location=location)
        light = bpy.context.object
        light.data.energy = energy
        light.data.shape = "DISK"
        light.data.size = size
        point_at(light, Vector((0.0, 0.0, 0.95)))
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
    *,
    anatomical_front_negative_y: bool = False,
) -> dict[str, tuple[float, float, float]]:
    scene = bpy.context.scene
    scene.render.engine = "BLENDER_EEVEE_NEXT"
    scene.render.resolution_x = resolution_x
    scene.render.resolution_y = resolution_y
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.world.color = (0.008, 0.010, 0.015)
    scene.view_settings.look = "AgX - Medium High Contrast"
    views = {
        "front": (0.0, -3.05 if anatomical_front_negative_y else 3.05, 0.97),
        "front-oblique": (
            2.15 if anatomical_front_negative_y else -2.15,
            -2.15 if anatomical_front_negative_y else 2.15,
            1.0,
        ),
        "left": (-3.05, 0.0, 0.97),
        "back": (0.0, 3.05 if anatomical_front_negative_y else -3.05, 0.97),
        "back-oblique": (
            -2.15 if anatomical_front_negative_y else 2.15,
            2.15 if anatomical_front_negative_y else -2.15,
            1.0,
        ),
        "right": (3.05, 0.0, 0.97),
    }
    for name, location in views.items():
        camera.location = location
        point_at(camera, Vector((0.0, 0.0, 0.88)))
        scene.render.filepath = str(output_directory / f"{name}.png")
        bpy.ops.render.render(write_still=True)
    return views


def main() -> None:
    args = parse_args()
    manifest_path = resolve(args.avatar_manifest)
    garment_path = resolve(args.garment)
    fabric_path = resolve(args.fabric)
    output_directory = resolve(args.output_directory)
    output_directory.mkdir(parents=True, exist_ok=True)

    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)

    show_bra = not args.hide_bra
    avatar_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    avatar_objects, hashes = configure_avatar(manifest_path, show_bra=show_bra)
    garment = import_obj(
        garment_path,
        "PatternaAcceptedGarment",
        args.garment_scale,
        forward_axis="NEGATIVE_Y" if args.garment_z_up else "NEGATIVE_Z",
        up_axis="Z" if args.garment_z_up else "Y",
    )
    if args.garment_z_up:
        floor_offset_m = avatar_manifest.get(
            "floor_offset_m",
            avatar_manifest.get("floorOffsetM", 0.0),
        )
        if not isinstance(floor_offset_m, (int, float)):
            raise RuntimeError("The avatar floor offset must be numeric.")
        garment.location.z -= float(floor_offset_m)
    assign_material(garment, cloth_material(fabric_path))
    bpy.context.view_layer.update()
    registration = validate_registration(avatar_objects["body"], garment)
    camera = add_studio()
    views = render_views(
        camera,
        output_directory,
        args.resolution_x,
        args.resolution_y,
        anatomical_front_negative_y=avatar_manifest.get("schemaVersion") == "patterna.display-avatar-glb/1.0",
    )
    renders = {
        name: {
            "path": f"{name}.png",
            "sha256": sha256(output_directory / f"{name}.png"),
            "byte_count": (output_directory / f"{name}.png").stat().st_size,
        }
        for name in views
    }
    visual_quality = {
        "accepted": False,
        "review_required": True,
        "reviewed_at_utc": None,
        "reviewed_render_sha256": {},
        "issues": ["The exact six-view turntable has not been visually reviewed."],
    }

    proof = {
        "schema_version": "patterna.product-turntable/1.0",
        "avatar_manifest": str(manifest_path),
        "garment": str(garment_path),
        "fabric": str(fabric_path),
        "avatar_object_count": len(avatar_objects),
        "show_bra": show_bra,
        "avatar_hashes": hashes,
        "garment_sha256": sha256(garment_path),
        "fabric_sha256": sha256(fabric_path),
        "registration": registration,
        "anatomical_front_axis": "-Y" if avatar_manifest.get("schemaVersion") == "patterna.display-avatar-glb/1.0" else "+Y",
        "render_engine": "BLENDER_EEVEE_NEXT",
        "resolution": [args.resolution_x, args.resolution_y],
        "views": {name: list(location) for name, location in views.items()},
        "renders": renders,
        "visual_quality": visual_quality,
    }
    (output_directory / "manifest.json").write_text(
        json.dumps(proof, indent=2) + "\n",
        encoding="utf-8",
    )
    (output_directory / "error.json").unlink(missing_ok=True)
    print(f"Rendered exact product turntable to {output_directory}")


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        try:
            diagnostic_directory = resolve(parse_args().output_directory)
        except Exception:
            diagnostic_directory = resolve(DEFAULT_OUTPUT_DIRECTORY)
        diagnostic_directory.mkdir(parents=True, exist_ok=True)
        (diagnostic_directory / "error.json").write_text(
            json.dumps(
                {
                    "error": str(error),
                    "traceback": traceback.format_exc(),
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        raise
