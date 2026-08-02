#!/usr/bin/env python3
"""Export GarmentCode's stitch-aware panel mesh for Patterna's Unreal compiler."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
GARMENTCODE_ROOT = PROJECT_ROOT / "third_party" / "GarmentCode"
sys.path.insert(0, str(GARMENTCODE_ROOT))

from pygarment.meshgen.boxmeshgen import BoxMesh  # noqa: E402


def slug(value: str) -> str:
    result = re.sub(r"[^a-z0-9]+", "-", value.strip().lower()).strip("-")
    return result or "panel"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate a constrained, stitch-matched Patterna mesh sidecar."
    )
    parser.add_argument("pattern", type=Path, help="GarmentCode specification JSON")
    parser.add_argument("output", type=Path, help="Patterna mesh sidecar JSON")
    parser.add_argument(
        "--resolution-cm",
        type=float,
        default=1.0,
        help="Approximate mesh edge length in centimeters",
    )
    return parser.parse_args()


def edge_ids_for_panel(
    pattern_document: dict[str, object], source_name: str, edge_count: int
) -> list[str]:
    fallback = [f"edge-{index}" for index in range(edge_count)]
    patterna = pattern_document.get("patterna")
    if not isinstance(patterna, dict):
        return fallback
    construction = patterna.get("construction_geometry")
    if not isinstance(construction, dict):
        return fallback
    metadata = construction.get(slug(source_name))
    if not isinstance(metadata, dict):
        return fallback
    boundary_ids = metadata.get("boundaryCurveIds")
    if (
        not isinstance(boundary_ids, list)
        or len(boundary_ids) != edge_count
        or any(not isinstance(edge_id, str) or not edge_id for edge_id in boundary_ids)
    ):
        raise ValueError(
            f"Patterna boundary IDs for {source_name} do not match its {edge_count} edges"
        )
    if len(set(boundary_ids)) != len(boundary_ids):
        raise ValueError(f"Patterna boundary IDs for {source_name} are not unique")
    return boundary_ids


def main() -> int:
    args = parse_args()
    pattern_path = args.pattern.resolve()
    output_path = args.output.resolve()
    if args.resolution_cm <= 0:
        raise ValueError("--resolution-cm must be positive")

    pattern_bytes = pattern_path.read_bytes()
    pattern_document = json.loads(pattern_bytes)
    mesh = BoxMesh(str(pattern_path), args.resolution_cm)
    mesh.load()

    panels = []
    edge_ids_by_panel: dict[str, list[str]] = {}
    for source_name in mesh.panelNames:
        panel = mesh.panels[source_name]
        edge_ids = edge_ids_for_panel(
            pattern_document, source_name, len(panel.edges)
        )
        edge_ids_by_panel[source_name] = edge_ids
        vertices = [[float(point[0]), float(point[1])] for point in panel.panel_vertices]
        minimum_x = min(point[0] for point in vertices)
        maximum_x = max(point[0] for point in vertices)
        minimum_y = min(point[1] for point in vertices)
        maximum_y = max(point[1] for point in vertices)
        width = max(maximum_x - minimum_x, 1e-9)
        height = max(maximum_y - minimum_y, 1e-9)
        panel_slug = slug(source_name)
        panels.append(
            {
                "sourcePanelName": source_name,
                "panelId": f"{panel_slug}-panel",
                "pieceId": panel_slug,
                "vertices": [
                    {
                        "x": point[0],
                        "y": point[1],
                        "u": (point[0] - minimum_x) / width,
                        "v": (point[1] - minimum_y) / height,
                    }
                    for point in vertices
                ],
                "triangles": [
                    [int(face[0]), int(face[1]), int(face[2])]
                    for face in panel.panel_faces
                ],
                "edgeVertexIndices": {
                    edge_ids[index]: [int(vertex) for vertex in edge.vertex_range]
                    for index, edge in enumerate(panel.edges)
                },
            }
        )

    seams = []
    for index, seam in enumerate(mesh.stitches):
        first = mesh.panels[seam.panel_1].edges[seam.edge_1].vertex_range
        second = mesh.panels[seam.panel_2].edges[seam.edge_2].vertex_range
        if len(first) != len(second):
            raise RuntimeError(
                f"GarmentCode stitch {index} has mismatched vertex counts: "
                f"{len(first)} and {len(second)}"
            )
        seams.append(
            {
                "seamId": f"stitch-{index}",
                "panelA": f"{slug(seam.panel_1)}-panel",
                "edgeA": edge_ids_by_panel[seam.panel_1][seam.edge_1],
                "panelB": f"{slug(seam.panel_2)}-panel",
                "edgeB": edge_ids_by_panel[seam.panel_2][seam.edge_2],
                "vertexCount": len(first),
            }
        )

    document = {
        "schemaVersion": "patterna.garmentcode-pattern-mesh/1.0",
        "sourcePatternSha256": hashlib.sha256(pattern_bytes).hexdigest(),
        "meshResolutionCm": args.resolution_cm,
        "generator": "GarmentCode BoxMesh constrained Delaunay triangulation",
        "panels": panels,
        "seams": seams,
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")
    print(
        f"Wrote {output_path} with {sum(len(panel['vertices']) for panel in panels)} "
        f"panel vertices, {sum(len(panel['triangles']) for panel in panels)} triangles, "
        f"and {len(seams)} stitch-matched seams."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
