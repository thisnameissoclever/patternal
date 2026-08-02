#!/usr/bin/env python3
"""Export the compiler's welded render surface as an application OBJ asset."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

import bpy


REPO_ROOT = Path(__file__).resolve().parents[1]


def arguments() -> list[str]:
    return sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []


def resolve(path: Path) -> Path:
    return path.resolve() if path.is_absolute() else (REPO_ROOT / path).resolve()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("input", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args(arguments())
    input_path = resolve(args.input)
    output_path = resolve(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)
    bpy.ops.wm.usd_import(filepath=str(input_path), import_materials=False)
    render_surfaces = [
        obj for obj in bpy.context.scene.objects
        if obj.type == "MESH" and "RenderSurface" in obj.name
    ]
    if len(render_surfaces) != 1:
        names = [obj.name for obj in bpy.context.scene.objects if obj.type == "MESH"]
        raise RuntimeError(f"Expected one RenderSurface mesh, received {names}.")

    bpy.ops.object.select_all(action="DESELECT")
    render_surface = render_surfaces[0]
    render_surface.select_set(True)
    bpy.context.view_layer.objects.active = render_surface
    # Blender preserves the compiler's centimeter vertex values and places the
    # imported USD object at scale 0.01 for its meter-valued scene. Patterna's
    # OBJ contract is centimeters, matching direct Warp meshes, so clear only
    # that import-time object scale before export.
    render_surface.scale = (1.0, 1.0, 1.0)
    bpy.ops.wm.obj_export(
        filepath=str(output_path),
        export_selected_objects=True,
        export_materials=False,
        forward_axis="NEGATIVE_Z",
        up_axis="Y",
    )
    print(
        f"Exported {len(render_surface.data.vertices)} vertices and "
        f"{len(render_surface.data.polygons)} faces in centimeters to {output_path}"
    )


if __name__ == "__main__":
    main()
