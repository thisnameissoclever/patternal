#!/usr/bin/env python3
"""Extract selected GarmentCode panels from a welded simulated OBJ."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "third_party" / "GarmentCode"))

from pygarment.meshgen.boxmeshgen import BoxMesh  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("pattern", type=Path)
    parser.add_argument("simulated_obj", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--resolution-cm", type=float, default=1.0)
    parser.add_argument("--panel", action="append", required=True)
    return parser.parse_args()


def read_vertices(path: Path) -> list[tuple[float, float, float]]:
    vertices = []
    for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        if line.startswith("v "):
            values = line.split()
            vertices.append(tuple(float(value) for value in values[1:4]))
    return vertices


def main() -> int:
    args = parse_args()
    pattern = args.pattern.resolve()
    simulated_obj = args.simulated_obj.resolve()
    output = args.output.resolve()
    selected = set(args.panel)

    mesh = BoxMesh(str(pattern), args.resolution_cm)
    mesh.load(topology_mode="welded-bootstrap")
    missing = selected.difference(mesh.panels)
    if missing:
        raise ValueError(f"Unknown panels: {sorted(missing)}")

    source_vertices = read_vertices(simulated_obj)
    if len(source_vertices) != len(mesh.vertices):
        raise RuntimeError(
            "Simulated OBJ topology does not match the welded GarmentCode mesh: "
            f"{len(source_vertices)} vertices versus {len(mesh.vertices)}"
        )

    selected_faces: list[tuple[str, list[int]]] = []
    used_vertices: set[int] = set()
    for panel_name in mesh.panelNames:
        if panel_name not in selected:
            continue
        panel = mesh.panels[panel_name]
        for face in panel.panel_faces:
            global_face = [int(index) for index in mesh._get_glob_ids(panel, face)]
            selected_faces.append((panel_name, global_face))
            used_vertices.update(global_face)

    ordered_vertices = sorted(used_vertices)
    remap = {source: index + 1 for index, source in enumerate(ordered_vertices)}
    lines = ["# Patterna welded GarmentCode panel subset"]
    for source_index in ordered_vertices:
        point = source_vertices[source_index]
        lines.append(f"v {point[0]:.9f} {point[1]:.9f} {point[2]:.9f}")
    active_panel = None
    for panel_name, face in selected_faces:
        if panel_name != active_panel:
            lines.append(f"g {panel_name}")
            active_panel = panel_name
        lines.append("f " + " ".join(str(remap[index]) for index in face))

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(
        f"Wrote {output} with {len(ordered_vertices)} vertices and "
        f"{len(selected_faces)} faces from {sorted(selected)}."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
