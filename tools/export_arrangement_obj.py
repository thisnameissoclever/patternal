#!/usr/bin/env python3
"""Export a libuipc arrangement execution as one merged garment OBJ.

Diagnostic-only convenience: writes the exact final vertex positions (Y-up
meters, matching the plan) with the plan's panel triangles merged into one
mesh. It accepts nothing and changes no artifact.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", required=True, type=Path)
    parser.add_argument("--execution", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    return parser.parse_args()


def read_obj_faces(path: Path) -> np.ndarray:
    faces = []
    for line in path.open():
        if line.startswith("f "):
            parts = line.split()
            faces.append([int(part.split("/")[0]) - 1 for part in parts[1:4]])
    return np.asarray(faces, dtype=np.int64)


def main() -> int:
    arguments = parse_arguments()
    plan = json.loads((arguments.plan / "scene-plan.json").read_text(encoding="utf-8"))
    report_path = arguments.execution / "execution-report.json"
    if not report_path.exists():
        report_path = arguments.execution / "settle-report.json"
    report = json.loads(report_path.read_text(encoding="utf-8"))
    positions = np.load(arguments.execution / "final-positions.npy", allow_pickle=False)

    offsets: dict[str, int] = {}
    start = 0
    for entry in report["panelOrder"]:
        offsets[entry["panelId"]] = start
        start += entry["vertexCount"]

    with arguments.output.open("w", encoding="utf-8", newline="\n") as stream:
        stream.write("# Patterna libuipc arrangement diagnostic export (Y-up meters)\n")
        for vertex in positions:
            stream.write(f"v {vertex[0]:.8f} {vertex[1]:.8f} {vertex[2]:.8f}\n")
        for panel in plan["scene"]["panels"]:
            faces = read_obj_faces(arguments.plan / panel["initialMesh"])
            base = offsets[panel["panelId"]]
            stream.write(f"g {panel['panelId']}\n")
            for face in faces:
                a, b, c = (int(index) + base + 1 for index in face)
                stream.write(f"f {a} {b} {c}\n")
    print(json.dumps({"vertices": int(positions.shape[0]), "output": str(arguments.output)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
