#!/usr/bin/env python3
"""Sample centered horizontal torso circuits from a Z-up avatar OBJ."""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import trimesh

from mesh_torso_arcs import measure_torso_arc_section


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("mesh", type=Path)
    parser.add_argument("--start-cm", type=float, default=85.0)
    parser.add_argument("--end-cm", type=float, default=138.0)
    parser.add_argument("--step-cm", type=float, default=1.0)
    args = parser.parse_args()

    loaded = trimesh.load(args.mesh, process=False, maintain_order=True)
    body = max(loaded.split(only_watertight=False), key=lambda component: len(component.faces))
    source = np.asarray(body.vertices, dtype=float)
    floor = float(source[:, 2].min())
    vertices = np.column_stack((source[:, 0], source[:, 2] - floor, source[:, 1]))
    converted = trimesh.Trimesh(vertices=vertices, faces=body.faces, process=False)
    print("height_cm circumference_cm front_cm back_cm front_depth_cm back_depth_cm")
    for height in np.arange(args.start_cm, args.end_cm + args.step_cm * 0.5, args.step_cm):
        try:
            section = measure_torso_arc_section(converted, float(height))
        except RuntimeError:
            continue
        print(
            f"{height:.1f} {section.circumference_cm:.3f} "
            f"{section.front_arc_cm:.3f} {section.back_arc_cm:.3f} "
            f"{section.front_mean_depth_cm:.3f} {section.back_mean_depth_cm:.3f}"
        )


if __name__ == "__main__":
    main()
