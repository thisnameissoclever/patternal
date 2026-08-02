#!/usr/bin/env python3
"""Inspect and optionally export the CharMorph female source mesh in Blender."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

import bpy


REPO_ROOT = Path(__file__).resolve().parents[1]


def blender_arguments() -> list[str]:
    return sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--object", default="mb_female")
    parser.add_argument("--output-dir", type=Path)
    return parser.parse_args(blender_arguments())


def resolve(path: Path) -> Path:
    return path.resolve() if path.is_absolute() else (REPO_ROOT / path).resolve()


def main() -> None:
    args = parse_args()
    mesh_objects = [obj for obj in bpy.data.objects if obj.type == "MESH"]
    if args.object not in bpy.data.objects:
        names = ", ".join(obj.name for obj in mesh_objects)
        raise RuntimeError(f"Object {args.object!r} not found. Mesh objects: {names}")

    body = bpy.data.objects[args.object]
    body_vertices = [body.matrix_world @ vertex.co for vertex in body.data.vertices]
    bounds = {
        axis: [
            min(vertex[index] for vertex in body_vertices),
            max(vertex[index] for vertex in body_vertices),
        ]
        for index, axis in enumerate(("x", "y", "z"))
    }
    report = {
        "object": body.name,
        "vertex_count": len(body.data.vertices),
        "polygon_count": len(body.data.polygons),
        "bounds_m": bounds,
        "dimensions_m": list(body.dimensions),
        "materials": [slot.material.name if slot.material else None for slot in body.material_slots],
        "face_count_by_material_index": {
            str(index): sum(1 for polygon in body.data.polygons if polygon.material_index == index)
            for index in sorted({polygon.material_index for polygon in body.data.polygons})
        },
        "shape_keys": list(body.data.shape_keys.key_blocks.keys()) if body.data.shape_keys else [],
        "mesh_objects": [
            {
                "name": obj.name,
                "vertices": len(obj.data.vertices),
                "polygons": len(obj.data.polygons),
                "parent": obj.parent.name if obj.parent else None,
            }
            for obj in mesh_objects
        ],
    }
    print(json.dumps(report, indent=2))

    if args.output_dir is None:
        return

    output_dir = resolve(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    report_path = output_dir / "source-report.json"
    report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")

    bpy.ops.object.select_all(action="DESELECT")
    body.select_set(True)
    bpy.context.view_layer.objects.active = body
    bpy.ops.wm.obj_export(
        filepath=str(output_dir / "body.obj"),
        export_selected_objects=True,
        export_materials=False,
        forward_axis="NEGATIVE_Y",
        up_axis="Z",
    )
    print(f"Exported {output_dir / 'body.obj'}")


if __name__ == "__main__":
    main()
