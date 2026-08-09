#!/usr/bin/env python3
"""Round-trip a Patterna display-avatar GLB through a fresh Blender scene."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

import bpy
from mathutils import Vector

sys.path.insert(0, str(Path(__file__).resolve().parent))
from charmorph_glb import render_candidate_views, sha256


def blender_arguments() -> list[str]:
    return sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--glb", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--render-output-dir", type=Path, required=True)
    return parser.parse_args(blender_arguments())


def main() -> None:
    args = parse_args()
    glb_path = args.glb.resolve()
    output_path = args.output.resolve()
    render_output_directory = args.render_output_dir.resolve()
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.import_scene.gltf(filepath=str(glb_path))
    meshes = sorted(
        (obj for obj in bpy.context.scene.objects if obj.type == "MESH"),
        key=lambda obj: obj.name,
    )
    body = next((obj for obj in meshes if obj.name == "Patterna_Antonia_Body"), None)
    if body is None:
        raise ValueError("Round-tripped GLB does not contain Patterna_Antonia_Body")
    if len(meshes) != 3:
        raise ValueError(f"Round-tripped GLB contains {len(meshes)} mesh objects instead of 3")
    if len(body.material_slots) < 10:
        raise ValueError(
            f"Round-tripped Antonia body has {len(body.material_slots)} unique materials instead of at least 10"
        )
    if len(bpy.data.images) < 6:
        raise ValueError(
            f"Round-tripped Antonia GLB has {len(bpy.data.images)} images instead of at least 6"
        )
    world_points = [obj.matrix_world @ Vector(corner) for obj in meshes for corner in obj.bound_box]
    floor_offset_m = min(point.z for point in world_points)
    body_points = [body.matrix_world @ Vector(corner) for corner in body.bound_box]
    body_height_m = max(point.z for point in body_points) - min(point.z for point in body_points)
    if abs(body_height_m - 1.67) > 0.001:
        raise ValueError(
            f"Round-tripped Antonia body height is {body_height_m:.6f} m instead of 1.670 m"
        )
    render_evidence = render_candidate_views(
        meshes,
        render_output_directory,
        floor_offset_m,
        body_height_m,
    )
    report = {
        "schemaVersion": "patterna.display-avatar-glb-verification/1.0",
        "accepted": False,
        "structuralRoundTripAccepted": True,
        "visualReviewRequired": True,
        "geometry": str(glb_path),
        "geometrySha256": sha256(glb_path),
        "meshObjectCount": len(meshes),
        "imageCount": len(bpy.data.images),
        "bodyMaterialCount": len(body.material_slots),
        "bodyHeightCm": body_height_m * 100.0,
        "components": {
            obj.name: {
                "vertexCount": len(obj.data.vertices),
                "polygonCount": len(obj.data.polygons),
                "materialCount": len(obj.material_slots),
            }
            for obj in meshes
        },
        "renders": render_evidence,
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
