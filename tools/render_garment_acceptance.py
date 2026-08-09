#!/usr/bin/env python3
"""Render hash-bound six-view diagnostics for one solver garment and body pair."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys

import bpy
from mathutils import Vector


REPO_ROOT = Path(__file__).resolve().parents[1]


def blender_arguments() -> list[str]:
    return sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--body", type=Path, required=True)
    parser.add_argument("--garment", type=Path, required=True)
    parser.add_argument("--solver-report", type=Path, required=True)
    parser.add_argument(
        "--output-directory",
        type=Path,
        default=Path("PatternaUnreal/Saved/Patterna/MPFB/DiagnosticGarment"),
    )
    return parser.parse_args(blender_arguments())


def resolve(path: Path) -> Path:
    return path.resolve() if path.is_absolute() else (REPO_ROOT / path).resolve()


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def validate_solver_identity(
    body_path: Path,
    garment_path: Path,
    solver_report_path: Path,
) -> dict[str, object]:
    report = json.loads(solver_report_path.read_text(encoding="utf-8"))
    expected_body_sha256 = str(report.get("body_mesh_sha256", ""))
    expected_garment_sha256 = str(report.get("output_mesh_sha256", ""))
    body_sha256 = sha256(body_path)
    garment_sha256 = sha256(garment_path)
    if body_sha256 != expected_body_sha256:
        raise RuntimeError(
            "Diagnostic body does not match the collider bound to the solver report."
        )
    if garment_sha256 != expected_garment_sha256:
        raise RuntimeError(
            "Diagnostic garment does not match the output bound to the solver report."
        )
    return report


def point_at(obj: bpy.types.Object, target: Vector) -> None:
    obj.rotation_euler = (target - obj.location).to_track_quat("-Z", "Y").to_euler()


def principled_material(
    name: str,
    color: tuple[float, float, float, float],
    roughness: float,
) -> bpy.types.Material:
    material = bpy.data.materials.new(name)
    material.diffuse_color = color
    material.use_nodes = True
    principled = material.node_tree.nodes.get("Principled BSDF")
    principled.inputs["Base Color"].default_value = color
    principled.inputs["Roughness"].default_value = roughness
    return material


def cloth_material() -> bpy.types.Material:
    material = principled_material("Woven cotton", (0.34, 0.025, 0.07, 1.0), 0.72)
    nodes = material.node_tree.nodes
    links = material.node_tree.links
    principled = nodes.get("Principled BSDF")
    principled.inputs["Sheen Weight"].default_value = 0.22
    noise = nodes.new("ShaderNodeTexNoise")
    noise.inputs["Scale"].default_value = 420.0
    noise.inputs["Detail"].default_value = 2.0
    noise.inputs["Roughness"].default_value = 0.65
    bump = nodes.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value = 0.11
    bump.inputs["Distance"].default_value = 0.00018
    links.new(noise.outputs["Fac"], bump.inputs["Height"])
    links.new(bump.outputs["Normal"], principled.inputs["Normal"])
    return material


def import_obj(path: Path) -> bpy.types.Object:
    before = set(bpy.context.scene.objects)
    bpy.ops.wm.obj_import(filepath=str(path))
    imported = [obj for obj in bpy.context.scene.objects if obj not in before]
    mesh_objects = [obj for obj in imported if obj.type == "MESH"]
    if len(mesh_objects) != 1:
        raise RuntimeError(f"Expected one mesh in {path}, received {len(mesh_objects)}")
    return mesh_objects[0]


def render_view(
    camera: bpy.types.Object,
    output_path: Path,
    camera_location: tuple[float, float, float],
) -> None:
    camera.location = camera_location
    point_at(camera, Vector((0.0, 0.0, 0.91)))
    bpy.context.scene.render.filepath = str(output_path)
    bpy.ops.render.render(write_still=True)


def main() -> None:
    args = parse_args()
    body_path = resolve(args.body)
    garment_path = resolve(args.garment)
    solver_report_path = resolve(args.solver_report)
    output_directory = resolve(args.output_directory)
    output_directory.mkdir(parents=True, exist_ok=True)
    solver_report = validate_solver_identity(
        body_path,
        garment_path,
        solver_report_path,
    )

    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)

    body = import_obj(body_path)
    body.name = "PatternaMeasuredBody"
    body.data.materials.clear()
    body.data.materials.append(
        principled_material("Measured avatar", (0.43, 0.19, 0.105, 1.0), 0.52)
    )
    for polygon in body.data.polygons:
        polygon.use_smooth = True

    garment = import_obj(garment_path)
    garment.name = "PatternaDiagnosticGarment"
    garment.scale = (0.01, 0.01, 0.01)
    garment.data.materials.clear()
    garment.data.materials.append(cloth_material())
    for polygon in garment.data.polygons:
        polygon.use_smooth = True

    bpy.ops.mesh.primitive_plane_add(size=8.0, location=(0.0, 0.0, 0.0))
    floor = bpy.context.object
    floor.data.materials.append(
        principled_material("Studio floor", (0.045, 0.05, 0.06, 1.0), 0.78)
    )

    bpy.ops.object.camera_add(location=(0.0, -3.1, 0.94))
    camera = bpy.context.object
    camera.data.lens = 68.0
    bpy.context.scene.camera = camera

    for location, energy, size in (
        ((-1.7, -2.0, 2.6), 1100.0, 2.2),
        ((1.8, -0.7, 1.7), 620.0, 2.0),
        ((0.4, 1.5, 2.35), 900.0, 1.6),
    ):
        bpy.ops.object.light_add(type="AREA", location=location)
        light = bpy.context.object
        light.data.energy = energy
        light.data.shape = "DISK"
        light.data.size = size
        point_at(light, Vector((0.0, 0.0, 0.95)))

    scene = bpy.context.scene
    scene.render.engine = "BLENDER_EEVEE_NEXT"
    scene.render.resolution_x = 720
    scene.render.resolution_y = 900
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.world.color = (0.012, 0.014, 0.019)
    scene.view_settings.look = "AgX - Medium High Contrast"
    # The Antonia and GarmentCode boundary faces toward negative depth after
    # OBJ import. Keep these names anatomical so diagnostic evidence uses the
    # same semantic contract as the packaged viewer.
    views = {
        "front": (0.0, -3.0, 0.94),
        "front-oblique": (2.15, -2.15, 0.94),
        "left": (3.0, 0.0, 0.94),
        "back": (0.0, 3.0, 0.94),
        "back-oblique": (-2.15, 2.15, 0.94),
        "right": (-3.0, 0.0, 0.94),
    }
    for name, location in views.items():
        render_view(camera, output_directory / f"{name}.png", location)
    manifest = {
        "schema_version": "patterna.garment-diagnostic-views/1.0",
        "solver_report": str(solver_report_path),
        "solver_report_sha256": sha256(solver_report_path),
        "solver_accepted": bool(solver_report.get("accepted", False)),
        "body": str(body_path),
        "body_sha256": sha256(body_path),
        "garment": str(garment_path),
        "garment_sha256": sha256(garment_path),
        "anatomical_front_axis": "negative depth after OBJ import",
        "views": {
            name: {
                "path": str((output_directory / f"{name}.png").resolve()),
                "sha256": sha256(output_directory / f"{name}.png"),
            }
            for name in views
        },
    }
    (output_directory / "manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"Rendered {output_directory}")


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(f"ERROR: {error}", file=sys.stderr)
        raise SystemExit(1) from error
