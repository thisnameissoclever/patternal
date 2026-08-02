#!/usr/bin/env python3
"""Count exact cloth edge and triangle crossings with Patterna's Warp kernel."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import trimesh
import warp as wp
import warp.sim
from warp.sim.collide import count_self_intersections, mark_self_intersections


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_mesh(path: Path) -> tuple[trimesh.Trimesh, int]:
    loaded = trimesh.load(path, process=False)
    if not isinstance(loaded, trimesh.Trimesh):
        raise ValueError(f"Expected one triangle mesh at {path}.")
    if loaded.faces.shape[1] != 3:
        raise ValueError(f"Expected a triangulated mesh at {path}.")
    source_vertex_count = int(len(loaded.vertices))
    loaded.merge_vertices(merge_tex=True, merge_norm=True, digits_vertex=8)
    loaded.remove_unreferenced_vertices()
    return loaded, source_vertex_count


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cloth", required=True, type=Path)
    parser.add_argument("--device", default="auto")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--maximum-records", type=int, default=100)
    args = parser.parse_args()

    cloth_path = args.cloth.resolve()
    cloth, source_vertex_count = load_mesh(cloth_path)
    vertices = np.asarray(cloth.vertices, dtype=np.float32)
    faces = np.asarray(cloth.faces, dtype=np.int32)

    wp.init()
    device = "cuda:0" if args.device == "auto" and wp.is_cuda_available() else args.device
    if device == "auto":
        device = "cpu"

    builder = wp.sim.ModelBuilder(gravity=0.0)
    builder.add_cloth_mesh(
        pos=wp.vec3(0.0, 0.0, 0.0),
        rot=wp.quat_identity(),
        scale=1.0,
        vel=wp.vec3(0.0, 0.0, 0.0),
        vertices=vertices,
        indices=faces.reshape(-1),
        density=1.0,
        add_springs=True,
    )
    model = builder.finalize(device=device)
    model.particle_collision_topology_id = wp.array(
        np.arange(len(vertices), dtype=np.int32),
        dtype=wp.int32,
        device=device,
    )

    model.particle_self_intersection_count.zero_()
    wp.launch(
        kernel=count_self_intersections,
        dim=model.spring_count,
        inputs=[
            model.spring_indices,
            model.particle_shape_tri_indices,
            model.particle_collision_topology_id,
            model.particle_shape.id,
        ],
        outputs=[model.particle_self_intersection_count],
        device=device,
    )

    flags = wp.zeros(model.spring_count, dtype=int, device=device)
    hit_faces = wp.full(model.spring_count, -1, dtype=int, device=device)
    wp.launch(
        kernel=mark_self_intersections,
        dim=model.spring_count,
        inputs=[
            model.spring_indices,
            model.particle_shape_tri_indices,
            model.particle_collision_topology_id,
            model.particle_shape.id,
        ],
        outputs=[flags, hit_faces],
        device=device,
    )
    wp.synchronize_device(device)

    count = int(model.particle_self_intersection_count.numpy()[0])
    flag_values = flags.numpy()
    face_values = hit_faces.numpy()
    spring_vertices = model.spring_indices.numpy().reshape(-1, 2)
    records = []
    for index in np.flatnonzero(flag_values)[: args.maximum_records]:
        records.append(
            {
                "spring_index": int(index),
                "vertices": [int(value) for value in spring_vertices[index]],
                "face_index": int(face_values[index]),
            }
        )

    result = {
        "schema_version": "patterna.render-surface-self-intersections/1.0",
        "cloth_path": str(cloth_path),
        "cloth_sha256": sha256(cloth_path),
        "cloth_source_vertex_count": source_vertex_count,
        "cloth_vertex_count": int(len(vertices)),
        "cloth_triangle_count": int(len(faces)),
        "tested_spring_count": int(model.spring_count),
        "device": str(device),
        "count": count,
        "record_count": len(records),
        "records": records,
    }
    serialized = json.dumps(result, indent=2) + "\n"
    if args.output:
        output_path = args.output.resolve()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(serialized, encoding="utf-8")
        print(f"Wrote self-intersection evidence to {output_path}")
    else:
        print(serialized, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
