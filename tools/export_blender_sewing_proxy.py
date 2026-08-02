#!/usr/bin/env python3
"""Export independent garment panels plus explicit Blender sewing springs.

Unlike the legacy assembled OBJ, this sidecar keeps every panel's material
vertices independent. Corresponding boundary samples are connected by loose
edges, which Blender Cloth interprets as zero-length sewing springs.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
GARMENTCODE_ROOT = PROJECT_ROOT / "third_party" / "GarmentCode"
sys.path.insert(0, str(GARMENTCODE_ROOT))

from pygarment.meshgen.boxmeshgen import BoxMesh  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Export a panel-preserving Blender cloth sewing proxy."
    )
    parser.add_argument("pattern", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--resolution-cm", type=float, default=1.2)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.resolution_cm <= 0.0:
        raise ValueError("--resolution-cm must be positive")

    pattern_path = args.pattern.resolve()
    output_path = args.output.resolve()
    pattern_bytes = pattern_path.read_bytes()

    mesh = BoxMesh(str(pattern_path), args.resolution_cm)
    mesh.load_panels()
    mesh.gen_panel_meshes()

    vertices: list[list[float]] = []
    faces: list[list[int]] = []
    panels: list[dict[str, object]] = []
    offsets: dict[str, int] = {}
    material_edges: set[tuple[int, int]] = set()

    for panel_name in mesh.panelNames:
        panel = mesh.panels[panel_name]
        offsets[panel_name] = len(vertices)
        transformed = panel.rot_trans_panel(panel.panel_vertices)
        vertices.extend(
            [[float(point[0]), float(point[1]), float(point[2])] for point in transformed]
        )
        panel_faces = [
            [offsets[panel_name] + int(index) for index in face]
            for face in panel.panel_faces
        ]
        faces.extend(panel_faces)
        for face in panel_faces:
            for first, second in ((face[0], face[1]), (face[1], face[2]), (face[2], face[0])):
                material_edges.add(tuple(sorted((first, second))))
        panels.append(
            {
                "name": panel_name,
                "vertexStart": offsets[panel_name],
                "vertexCount": len(panel.panel_vertices),
                "faceCount": len(panel.panel_faces),
            }
        )

    sewing_edges: list[list[int]] = []
    seams: list[dict[str, object]] = []
    seen_sewing_edges: set[tuple[int, int]] = set()
    for stitch_index, stitch in enumerate(mesh.stitches):
        first_range, second_range = mesh._swap_stitch_ranges(stitch)
        stitch_edges: list[list[int]] = []
        for first_local, second_local in zip(first_range, second_range):
            first = offsets[stitch.panel_1] + int(first_local)
            second = offsets[stitch.panel_2] + int(second_local)
            pair = tuple(sorted((first, second)))
            if first == second or pair in seen_sewing_edges or pair in material_edges:
                continue
            seen_sewing_edges.add(pair)
            edge = [first, second]
            sewing_edges.append(edge)
            stitch_edges.append(edge)
        seams.append(
            {
                "index": stitch_index,
                "panelA": stitch.panel_1,
                "edgeA": int(stitch.edge_1),
                "panelB": stitch.panel_2,
                "edgeB": int(stitch.edge_2),
                "springCount": len(stitch_edges),
                "springs": stitch_edges,
            }
        )

    document = {
        "schemaVersion": "patterna.blender-sewing-proxy/1.0",
        "units": "centimeters",
        "sourcePattern": str(pattern_path),
        "sourcePatternSha256": hashlib.sha256(pattern_bytes).hexdigest(),
        "meshResolutionCm": args.resolution_cm,
        "generator": "GarmentCode BoxMesh independent panels with explicit sewing springs",
        "vertices": vertices,
        "faces": faces,
        "sewingEdges": sewing_edges,
        "panels": panels,
        "seams": seams,
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")
    print(
        f"Wrote {output_path} with {len(vertices)} vertices, {len(faces)} faces, "
        f"{len(panels)} panels, {len(seams)} seams, and {len(sewing_edges)} sewing springs."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
