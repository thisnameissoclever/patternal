#!/usr/bin/env python3
"""Render a deterministic studio preview of a generated avatar OBJ in Blender."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

import bpy
from mathutils import Vector

sys.path.insert(0, str(Path(__file__).resolve().parent))
from render_product_acceptance import configure_avatar


REPO_ROOT = Path(__file__).resolve().parents[1]


def blender_arguments() -> list[str]:
    return sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--avatar",
        type=Path,
        default=Path("PatternaUnreal/Saved/Patterna/MPFB/PatternaDefaultFemale.obj"),
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("PatternaUnreal/Saved/Patterna/MPFB/PatternaDefaultFemale.png"),
    )
    parser.add_argument("--avatar-manifest", type=Path, default=None)
    parser.add_argument("--hide-bra", action="store_true")
    parser.add_argument(
        "--view",
        choices=("front", "back", "left", "right", "oblique"),
        default="front",
    )
    parser.add_argument(
        "--source-up-axis",
        choices=("Y", "Z"),
        default="Z",
        help="Axis used as vertical in the source OBJ.",
    )
    return parser.parse_args(blender_arguments())


def resolve(path: Path) -> Path:
    return path.resolve() if path.is_absolute() else (REPO_ROOT / path).resolve()


def point_at(obj: bpy.types.Object, target: Vector) -> None:
    obj.rotation_euler = (target - obj.location).to_track_quat("-Z", "Y").to_euler()


def make_principled(name: str, color: tuple[float, float, float, float]):
    material = bpy.data.materials.new(name)
    material.diffuse_color = color
    material.use_nodes = True
    principled = material.node_tree.nodes.get("Principled BSDF")
    principled.inputs["Base Color"].default_value = color
    principled.inputs["Roughness"].default_value = 0.54
    principled.inputs["Subsurface Weight"].default_value = 0.08
    return material


def main() -> None:
    args = parse_args()
    avatar_path = resolve(args.avatar)
    avatar_manifest_path = resolve(args.avatar_manifest) if args.avatar_manifest else None
    output_path = resolve(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)
    if avatar_manifest_path is not None:
        avatar_objects, _ = configure_avatar(
            avatar_manifest_path,
            show_bra=not args.hide_bra,
        )
        avatar = avatar_objects["body"]
    else:
        if args.source_up_axis == "Y":
            bpy.ops.wm.obj_import(filepath=str(avatar_path))
        else:
            bpy.ops.wm.obj_import(
                filepath=str(avatar_path),
                forward_axis="NEGATIVE_Y",
                up_axis="Z",
            )
        avatar = bpy.context.selected_objects[0]
        avatar.name = "PatternaMeasuredAvatarPreview"
        avatar.data.materials.clear()
        avatar.data.materials.append(make_principled("Measured skin", (0.18, 0.055, 0.028, 1.0)))
        for polygon in avatar.data.polygons:
            polygon.use_smooth = True

    bpy.ops.mesh.primitive_plane_add(size=8.0, location=(0.0, 0.0, 0.0))
    floor = bpy.context.object
    floor.data.materials.append(make_principled("Studio floor", (0.055, 0.06, 0.07, 1.0)))

    camera_locations = {
        "front": (0.0, 3.1, 0.93),
        "back": (0.0, -3.1, 0.93),
        "left": (-3.1, 0.0, 0.93),
        "right": (3.1, 0.0, 0.93),
        "oblique": (2.2, 2.2, 1.02),
    }
    bpy.ops.object.camera_add(location=camera_locations[args.view])
    camera = bpy.context.object
    point_at(camera, Vector((0.0, 0.0, 0.86)))
    camera.data.lens = 67.0
    bpy.context.scene.camera = camera

    bpy.ops.object.light_add(type="AREA", location=(-1.8, -2.0, 2.7))
    key = bpy.context.object
    key.data.energy = 520.0
    key.data.shape = "DISK"
    key.data.size = 2.3
    point_at(key, Vector((0.0, 0.0, 0.95)))

    bpy.ops.object.light_add(type="AREA", location=(1.7, -0.8, 1.6))
    fill = bpy.context.object
    fill.data.energy = 280.0
    fill.data.size = 2.0
    point_at(fill, Vector((0.0, 0.0, 0.9)))

    bpy.ops.object.light_add(type="AREA", location=(0.3, 1.4, 2.3))
    rim = bpy.context.object
    rim.data.energy = 420.0
    rim.data.size = 1.5
    point_at(rim, Vector((0.0, 0.0, 1.05)))

    scene = bpy.context.scene
    scene.render.engine = "BLENDER_EEVEE_NEXT"
    scene.render.resolution_x = 720
    scene.render.resolution_y = 900
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.render.filepath = str(output_path)
    scene.render.film_transparent = False
    scene.world.color = (0.012, 0.014, 0.019)
    scene.view_settings.look = "AgX - Medium High Contrast"
    scene.render.image_settings.color_mode = "RGBA"
    scene.camera.data.dof.use_dof = False
    scene.render.resolution_percentage = 100
    bpy.ops.render.render(write_still=True)
    print(f"Rendered {output_path}")


if __name__ == "__main__":
    main()
