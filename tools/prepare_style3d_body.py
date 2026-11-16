#!/usr/bin/env python3
"""Convert an MPFB body into the convention the Style3D solver reads.

`generate_mpfb_avatar.py` writes the body the way Blender holds it, with Z up
and the feet wherever the fit left them. The solver and the packaged collision
body use Y up with the feet on zero. The packaged pair shows the relationship
exactly: `patterna-mpfb-female.source.obj` and `patterna-mpfb-female.obj` are
the same 13,380 vertices in the same order, differing only by that axis swap
and a shift of the floor to zero.

That conversion had no home in this repository. It lived in whichever process
produced the packaged assets, which is part of why those assets cannot be
reproduced here today.

The faces change as well. The MakeHuman base mesh is quads carrying texture
coordinates, and the solver reads triangles addressed by position alone, so
each quad is split on one diagonal and the texture indices are dropped. The
packaged pair shows the same thing: 13,378 quads become 26,756 triangles.

Vertex order is preserved, because everything downstream, the seam
constraints, the collision body and the morph basis alike, is indexed by it.
"""

from __future__ import annotations

import argparse
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    arguments = parser.parse_args()

    lines = arguments.input.read_text(encoding="utf-8").splitlines()
    vertices = [
        tuple(float(value) for value in line.split()[1:4])
        for line in lines
        if line.startswith("v ")
    ]
    if not vertices:
        raise SystemExit(f"No vertices in {arguments.input}")

    floor = min(vertex[2] for vertex in vertices)
    converted = iter(
        (vertex[0], vertex[2] - floor, vertex[1]) for vertex in vertices
    )

    triangles = 0
    arguments.output.parent.mkdir(parents=True, exist_ok=True)
    with arguments.output.open("w", encoding="utf-8", newline="\n") as output:
        output.write("# Patterna Style3D collision body, Y up with feet on zero\n")
        for x, y, z in converted:
            output.write(f"v {x:.9f} {y:.9f} {z:.9f}\n")
        for line in lines:
            if not line.startswith("f "):
                continue
            corners = [
                int(token.split("/")[0]) for token in line.split()[1:]
            ]
            # Fan from the first corner. The winding of each triangle follows
            # the polygon's, so the surface keeps facing the way it did.
            for index in range(1, len(corners) - 1):
                output.write(
                    f"f {corners[0]} {corners[index]} {corners[index + 1]}\n"
                )
                triangles += 1

    heights = [vertex[2] - floor for vertex in vertices]
    print(f"vertices: {len(vertices)}")
    print(f"triangles: {triangles}")
    print(f"floor removed: {floor * 100:.4f} cm")
    print(f"stature: {(max(heights) - min(heights)) * 100:.3f} cm")
    print(f"written to {arguments.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
