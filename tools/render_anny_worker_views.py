#!/usr/bin/env python3
"""Render the thirteen fixed avatar-worker review views of an Anny body OBJ.

Runs inside Blender (``blender --background --factory-startup --python
render_anny_worker_views.py -- ...``). Cameras are fixed functions of the mesh
bounds so two identical meshes always produce identical framing. The body
renders as an untextured neutral studio material; this evidence supports
anatomy review, not appearance acceptance.
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
    if "--" in sys.argv:
        return sys.argv[sys.argv.index("--") + 1 :]
    return []


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mesh", required=True, type=Path)
    parser.add_argument("--output-directory", required=True, type=Path)
    parser.add_argument("--landmarks", required=True, type=Path)
    parser.add_argument("--resolution", type=int, default=1600)
    return parser.parse_args(script_arguments())


VIEWS = {
    "front": {"yaw": 0.0, "pitch": 0.0, "frame": "body"},
    "back": {"yaw": 180.0, "pitch": 0.0, "frame": "body"},
    "left": {"yaw": 90.0, "pitch": 0.0, "frame": "body"},
    "right": {"yaw": -90.0, "pitch": 0.0, "frame": "body"},
    "front-oblique": {"yaw": 40.0, "pitch": 0.0, "frame": "body"},
    "rear-oblique": {"yaw": 140.0, "pitch": 0.0, "frame": "body"},
    "face": {"yaw": 0.0, "pitch": 0.0, "frame": "face"},
    "hands": {"yaw": 0.0, "pitch": -18.0, "frame": "hands"},
    "feet": {"yaw": 25.0, "pitch": -30.0, "frame": "feet"},
    "shoulder": {"yaw": 30.0, "pitch": 8.0, "frame": "shoulder"},
    "bust": {"yaw": 25.0, "pitch": 0.0, "frame": "bust"},
    "waist": {"yaw": 25.0, "pitch": 0.0, "frame": "waist"},
    "hip": {"yaw": 25.0, "pitch": 0.0, "frame": "hip"},
}


def main() -> int:
    args = parse_args()
    landmarks = json.loads(args.landmarks.read_text(encoding="utf-8"))
    args.output_directory.mkdir(parents=True, exist_ok=True)

    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene = bpy.context.scene
    scene.render.engine = "BLENDER_EEVEE_NEXT"
    scene.render.resolution_x = args.resolution
    scene.render.resolution_y = args.resolution
    scene.render.film_transparent = False
    scene.view_settings.view_transform = "AgX"
    scene.view_settings.look = "AgX - Medium High Contrast"
    world = bpy.data.worlds.new("Studio")
    scene.world = world
    world.use_nodes = True
    world.node_tree.nodes["Background"].inputs[0].default_value = (0.92, 0.92, 0.94, 1.0)
    world.node_tree.nodes["Background"].inputs[1].default_value = 1.0

    bpy.ops.wm.obj_import(filepath=str(args.mesh), forward_axis="Y", up_axis="Z")
    body = bpy.context.selected_objects[0]
    body.name = "AnnyWorkerBody"
    material = bpy.data.materials.new("NeutralSkinReview")
    material.use_nodes = True
    bsdf = material.node_tree.nodes["Principled BSDF"]
    bsdf.inputs["Base Color"].default_value = (0.52, 0.42, 0.37, 1.0)
    bsdf.inputs["Roughness"].default_value = 0.55
    body.data.materials.clear()
    body.data.materials.append(material)
    bpy.ops.object.shade_smooth()

    for name, energy, location in (
        ("Key", 520.0, (2.6, -2.4, 2.6)),
        ("Fill", 210.0, (-2.8, -1.8, 1.4)),
        ("Rim", 330.0, (0.4, 2.9, 2.2)),
    ):
        light_data = bpy.data.lights.new(name, type="AREA")
        light_data.energy = energy
        light_data.size = 2.4
        light = bpy.data.objects.new(name, light_data)
        light.location = location
        scene.collection.objects.link(light)
        direction = Vector((0.0, 0.0, 1.0)) - Vector(location)
        light.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()

    bounds = [body.matrix_world @ Vector(corner) for corner in body.bound_box]
    minimum = Vector((min(v[i] for v in bounds) for i in range(3)))
    maximum = Vector((max(v[i] for v in bounds) for i in range(3)))
    height = maximum.z - minimum.z
    center = (minimum + maximum) / 2.0

    marks = {key: Vector(value) for key, value in landmarks.items()}

    def frame_target(kind: str) -> tuple[Vector, float]:
        if kind == "body":
            return Vector((center.x, center.y, center.z)), height * 0.62
        if kind == "face":
            return marks["head"], height * 0.10
        if kind == "hands":
            middle = (marks["wrist.L"] + marks["wrist.R"]) / 2.0
            return middle, height * 0.22
        if kind == "feet":
            middle = (marks["foot.L"] + marks["foot.R"]) / 2.0
            return middle, height * 0.14
        if kind == "shoulder":
            middle = (marks["upperarm01.L"] + marks["upperarm01.R"]) / 2.0
            return middle, height * 0.20
        if kind == "bust":
            return marks["bust"], height * 0.18
        if kind == "waist":
            return marks["waist"], height * 0.18
        if kind == "hip":
            return marks["hip"], height * 0.18
        raise ValueError(f"Unknown frame kind: {kind}")

    camera_data = bpy.data.cameras.new("ReviewCamera")
    camera_data.lens = 62.0
    camera = bpy.data.objects.new("ReviewCamera", camera_data)
    scene.collection.objects.link(camera)
    scene.camera = camera

    report = {}
    for view_name, view in VIEWS.items():
        target, radius = frame_target(view["frame"])
        distance = radius * 3.1
        yaw = math.radians(view["yaw"])
        pitch = math.radians(view["pitch"])
        offset = Vector(
            (
                math.sin(yaw) * math.cos(pitch),
                -math.cos(yaw) * math.cos(pitch),
                math.sin(pitch),
            )
        ) * distance
        camera.location = target + offset
        direction = target - camera.location
        camera.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()
        output = args.output_directory / f"render-{view_name}.png"
        scene.render.filepath = str(output)
        bpy.ops.render.render(write_still=True)
        report[view_name] = output.name

    (args.output_directory / "render-report.json").write_text(
        json.dumps(
            {
                "schemaVersion": "patterna.anny-worker-renders/1.0",
                "views": report,
                "resolution": args.resolution,
                "meshFile": args.mesh.name,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    print(json.dumps({"renderedViews": len(report)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
