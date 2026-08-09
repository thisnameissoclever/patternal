#!/usr/bin/env python3
"""Exercise regional display-to-collision registration inside Blender."""

from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import unittest

import bpy

sys.path.insert(0, str(Path(__file__).resolve().parent))
from charmorph_glb import evaluate_collision_registration, material_region


DISPLAY_VERTICES = [
    (-0.5, -0.5, 0.0),
    (0.5, -0.5, 0.0),
    (0.5, 0.5, 0.0),
    (-0.5, 0.5, 0.0),
    (-0.5, -0.5, 1.0),
    (0.5, -0.5, 1.0),
    (0.5, 0.5, 1.0),
    (-0.5, 0.5, 1.0),
]
DISPLAY_FACES = [
    (0, 3, 2, 1),
    (4, 5, 6, 7),
    (0, 1, 5, 4),
    (1, 2, 6, 5),
    (2, 3, 7, 6),
    (3, 0, 4, 7),
]


def make_display_body() -> bpy.types.Object:
    mesh = bpy.data.meshes.new("RegistrationDisplayMesh")
    mesh.from_pydata(DISPLAY_VERTICES, [], DISPLAY_FACES)
    mesh.update()
    body = bpy.data.objects.new("RegistrationDisplayBody", mesh)
    bpy.context.collection.objects.link(body)
    material = bpy.data.materials.new("cm_antonia_body")
    body.data.materials.append(material)
    for polygon in body.data.polygons:
        polygon.material_index = 0
    return body


def write_collision_cube(path: Path, *, x_offset: float = 0.0) -> None:
    vertices = [(x + x_offset, y, z) for x, y, z in DISPLAY_VERTICES]
    face_centers = [
        tuple(sum(vertices[index][axis] for index in face) / 4.0 for axis in range(3))
        for face in DISPLAY_FACES
    ]
    with path.open("w", encoding="utf-8", newline="\n") as output:
        for x, y, z in vertices + face_centers:
            output.write(f"v {-x:.9f} {-y:.9f} {z:.9f}\n")
        for face_index, face in enumerate(DISPLAY_FACES):
            center = len(vertices) + face_index + 1
            for index in range(4):
                first = face[index] + 1
                second = face[(index + 1) % 4] + 1
                output.write(f"f {first} {second} {center}\n")


class RegionalRegistrationTests(unittest.TestCase):
    def setUp(self) -> None:
        bpy.ops.wm.read_factory_settings(use_empty=True)
        self.body = make_display_body()
        self.temporary_directory = tempfile.TemporaryDirectory()

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def collision_path(self, name: str) -> Path:
        return Path(self.temporary_directory.name) / name

    def test_different_topology_on_the_same_surface_is_accepted(self) -> None:
        path = self.collision_path("same-surface.obj")
        write_collision_cube(path)
        report = evaluate_collision_registration(self.body, path)
        self.assertTrue(report["accepted"])
        self.assertFalse(report["bodyAndCollisionVertexCountMatch"])
        self.assertIsNone(report["maximumBodyToCollisionDistanceM"])
        self.assertLess(report["maximumSurfaceDistanceM"], 1e-7)
        self.assertTrue(report["regions"]["torso"]["accepted"])

    def test_region_distance_rejects_a_shifted_collision_surface(self) -> None:
        path = self.collision_path("shifted.obj")
        write_collision_cube(path, x_offset=0.02)
        report = evaluate_collision_registration(self.body, path)
        self.assertFalse(report["accepted"])
        self.assertFalse(report["regions"]["torso"]["accepted"])
        self.assertTrue(any("torso" in issue for issue in report["issues"]))

    def test_non_finite_collision_input_is_rejected(self) -> None:
        path = self.collision_path("non-finite.obj")
        write_collision_cube(path, x_offset=float("nan"))
        with self.assertRaisesRegex(ValueError, "non-finite vertex"):
            evaluate_collision_registration(self.body, path)

    def test_antonia_material_names_map_to_anatomical_regions(self) -> None:
        self.assertEqual("head", material_region("cm_antonia_iris"))
        self.assertEqual("arms", material_region("cm_antonia_nails"))
        self.assertEqual("torso", material_region("cm_antonia_body"))
        self.assertEqual("legs", material_region("cm_antonia_legs"))
        self.assertEqual("other", material_region("unclassified_surface"))


if __name__ == "__main__":
    unittest.main(argv=[sys.argv[0]])
