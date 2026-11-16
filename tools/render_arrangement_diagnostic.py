#!/usr/bin/env python3
"""Render fixed diagnostic views of an arrangement result over its collider.

Runs inside Blender (``blender --background --factory-startup --python
render_arrangement_diagnostic.py -- ...``). Deterministic cameras derive from
the collider bounds. Diagnostic evidence only; it accepts nothing.
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
import sys

import bpy
from mathutils import Vector


def script_arguments() -> list[str]:
    return sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--garment", required=True, type=Path)
    parser.add_argument("--collider", required=True, type=Path)
    parser.add_argument("--output-directory", required=True, type=Path)
    parser.add_argument("--resolution", type=int, default=1400)
    return parser.parse_args(script_arguments())


VIEWS = {
    "front": 0.0,
    "front-oblique": 40.0,
    "left": 90.0,
    "back": 180.0,
    "right": -90.0,
    "rear-oblique": 140.0,
}


def import_obj(path: Path, name: str):
    bpy.ops.wm.obj_import(filepath=str(path), forward_axis="NEGATIVE_Z", up_axis="Y")
    imported = bpy.context.selected_objects[0]
    imported.name = name
    return imported


def main() -> int:
    args = parse_args()
    args.output_directory.mkdir(parents=True, exist_ok=True)
    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene = bpy.context.scene
    scene.render.engine = "BLENDER_EEVEE_NEXT"
    scene.render.resolution_x = args.resolution
    scene.render.resolution_y = args.resolution
    scene.view_settings.view_transform = "AgX"
    world = bpy.data.worlds.new("Studio")
    scene.world = world
    world.use_nodes = True
    world.node_tree.nodes["Background"].inputs[0].default_value = (0.9, 0.9, 0.92, 1.0)

    body = import_obj(args.collider, "Collider")
    body_material = bpy.data.materials.new("BodyReview")
    body_material.use_nodes = True
    body_bsdf = body_material.node_tree.nodes["Principled BSDF"]
    body_bsdf.inputs["Base Color"].default_value = (0.68, 0.56, 0.50, 1.0)
    body_bsdf.inputs["Roughness"].default_value = 0.6
    body.data.materials.clear()
    body.data.materials.append(body_material)

    garment = import_obj(args.garment, "Garment")
    cloth_material = bpy.data.materials.new("ClothReview")
    cloth_material.use_nodes = True
    cloth_bsdf = cloth_material.node_tree.nodes["Principled BSDF"]
    cloth_bsdf.inputs["Base Color"].default_value = (0.30, 0.42, 0.62, 1.0)
    cloth_bsdf.inputs["Roughness"].default_value = 0.7
    cloth_material.use_backface_culling = False
    garment.data.materials.clear()
    garment.data.materials.append(cloth_material)

    for name, energy, location in (
        ("Key", 800.0, (2.4, 2.4, 2.2)),
        ("Fill", 320.0, (-2.6, 1.6, 1.4)),
        ("Rim", 420.0, (0.3, 2.4, -2.6)),
    ):
        light_data = bpy.data.lights.new(name, type="AREA")
        light_data.energy = energy
        light_data.size = 2.2
        light = bpy.data.objects.new(name, light_data)
        light.location = location
        scene.collection.objects.link(light)
        direction = Vector((0.0, 0.0, 0.9)) - Vector(location)
        light.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()

    bounds = [body.matrix_world @ Vector(corner) for corner in body.bound_box]
    minimum = Vector((min(v[i] for v in bounds) for i in range(3)))
    maximum = Vector((max(v[i] for v in bounds) for i in range(3)))
    center = (minimum + maximum) / 2.0
    # Blender world is Z-up after the Y-up import conversion.
    height = maximum.z - minimum.z
    target = Vector((center.x, center.y, minimum.z + 0.58 * height))

    camera_data = bpy.data.cameras.new("DiagCamera")
    camera_data.lens = 62.0
    camera = bpy.data.objects.new("DiagCamera", camera_data)
    scene.collection.objects.link(camera)
    scene.camera = camera

    report = {}
    for view_name, yaw_degrees in VIEWS.items():
        yaw = math.radians(yaw_degrees)
        distance = height * 1.35
        offset = Vector(
            (math.sin(yaw) * distance, -math.cos(yaw) * distance, 0.10 * height)
        )
        camera.location = target + offset
        direction = target - camera.location
        camera.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()
        output = args.output_directory / f"arrangement-{view_name}.png"
        scene.render.filepath = str(output)
        bpy.ops.render.render(write_still=True)
        report[view_name] = output.name

    (args.output_directory / "diagnostic-render-report.json").write_text(
        json.dumps({"views": report, "claims": {"accepted": False}}, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({"renderedViews": len(report)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
