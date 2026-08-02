#!/usr/bin/env python3
"""Render a deterministic inspection sheet for a GarmentCode pre-fit OBJ."""

from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from mpl_toolkits.mplot3d.art3d import Poly3DCollection
import numpy as np
import trimesh


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--cloth",
        type=Path,
        default=Path(
            "PatternaUnreal/Saved/Patterna/GarmentCodeWarp/PatternaFemaleCrewNeck/PatternaFemaleCrewNeck_sim.obj"
        ),
    )
    parser.add_argument(
        "--body",
        type=Path,
        default=Path("third_party/GarmentCode/assets/bodies/mean_female.obj"),
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(
            "PatternaUnreal/Saved/Patterna/GarmentCodeWarp/PatternaFemaleCrewNeck/PatternaFemaleCrewNeck_inspection.png"
        ),
    )
    return parser.parse_args()


def add_meshes(ax, body: trimesh.Trimesh, cloth: trimesh.Trimesh) -> None:
    body_vertices = np.column_stack((body.vertices[:, 0], body.vertices[:, 2], body.vertices[:, 1]))
    cloth_vertices = np.column_stack((cloth.vertices[:, 0], cloth.vertices[:, 2], cloth.vertices[:, 1]))
    body_triangles = body_vertices[body.faces]
    cloth_triangles = cloth_vertices[cloth.faces]
    triangles = np.concatenate((body_triangles, cloth_triangles), axis=0)
    colors = np.empty((len(triangles), 4), dtype=float)
    colors[: len(body_triangles)] = matplotlib.colors.to_rgba("#8b6c60", 1.0)
    colors[len(body_triangles) :] = matplotlib.colors.to_rgba("#7744d4", 0.98)
    collection = Poly3DCollection(
        triangles,
        facecolors=colors,
        shade=True,
        lightsource=matplotlib.colors.LightSource(azdeg=315, altdeg=45),
    )
    ax.add_collection3d(collection)


def set_view(ax, bounds: np.ndarray, azimuth: float, title: str) -> None:
    center = bounds.mean(axis=0)
    extents = bounds[1] - bounds[0]
    radius = max(extents[0], extents[2]) * 0.62
    ax.set_xlim(center[0] - radius, center[0] + radius)
    ax.set_ylim(center[2] - radius, center[2] + radius)
    ax.set_zlim(bounds[0, 1], bounds[1, 1])
    ax.set_box_aspect((1.0, 0.65, 2.15))
    ax.view_init(elev=2, azim=azimuth)
    ax.set_axis_off()
    ax.set_title(title, color="#e8e8ec", fontsize=12, pad=4)
    ax.set_facecolor("#111218")


def main() -> int:
    args = parse_args()
    repo_root = Path(__file__).resolve().parents[1]
    cloth_path = (repo_root / args.cloth).resolve() if not args.cloth.is_absolute() else args.cloth
    body_path = (repo_root / args.body).resolve() if not args.body.is_absolute() else args.body
    output_path = (repo_root / args.output).resolve() if not args.output.is_absolute() else args.output

    cloth = trimesh.load_mesh(cloth_path, process=False)
    body = trimesh.load_mesh(body_path, process=False)
    body.vertices *= 100.0
    minimum_y = float(body.vertices[:, 1].min())
    if minimum_y < 0.0:
        body.vertices[:, 1] -= minimum_y

    bounds = np.array(
        [
            np.minimum(cloth.bounds[0], body.bounds[0]),
            np.maximum(cloth.bounds[1], body.bounds[1]),
        ]
    )
    fig = plt.figure(figsize=(13.5, 6.5), dpi=160, facecolor="#111218")
    views = ((90, "Front"), (0, "Side"), (-90, "Back"))
    for index, (azimuth, title) in enumerate(views, start=1):
        ax = fig.add_subplot(1, 3, index, projection="3d")
        add_meshes(ax, body, cloth)
        set_view(ax, bounds, azimuth, title)

    fig.suptitle(
        "Patterna GarmentCode Warp pre-fit inspection",
        color="#f4f4f6",
        fontsize=15,
        y=0.98,
    )
    fig.subplots_adjust(left=0.01, right=0.99, bottom=0.01, top=0.92, wspace=0.0)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, facecolor=fig.get_facecolor(), bbox_inches="tight", pad_inches=0.08)
    plt.close(fig)
    print(output_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
