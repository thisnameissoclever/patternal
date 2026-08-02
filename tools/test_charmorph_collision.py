#!/usr/bin/env python3

from __future__ import annotations

from pathlib import Path
import sys
import unittest

import numpy as np
import trimesh

sys.path.insert(0, str(Path(__file__).resolve().parent))
from charmorph_collision import boundary_loops, cap_face_openings, largest_outer_component


class CharMorphCollisionTests(unittest.TestCase):
    def test_caps_one_high_face_opening(self) -> None:
        vertices = np.array([
            [-1.0, -1.0, 0.0],
            [1.0, -1.0, 0.0],
            [1.0, 1.0, 0.0],
            [-1.0, 1.0, 0.0],
            [0.0, 0.0, 1.0],
        ])
        faces = np.array([
            [0, 1, 2], [0, 2, 3],
            [0, 4, 1], [1, 4, 2], [2, 4, 3],
        ])
        mesh = trimesh.Trimesh(vertices=vertices, faces=faces, process=False)
        self.assertEqual(1, len(boundary_loops(mesh)))
        collider, report = cap_face_openings(mesh, minimum_height_ratio=-0.01)
        self.assertTrue(collider.is_watertight)
        self.assertEqual(1, report.loop_count)
        self.assertEqual((3,), report.loop_vertex_counts)

    def test_rejects_opening_on_clothing_contact_region(self) -> None:
        box = trimesh.creation.box()
        open_mesh = trimesh.Trimesh(
            vertices=box.vertices,
            faces=box.faces[:-2],
            process=False,
        )
        with self.assertRaisesRegex(ValueError, "garment-contact surface"):
            cap_face_openings(open_mesh, minimum_height_ratio=0.90)

    def test_selects_largest_component(self) -> None:
        body = trimesh.creation.icosphere(subdivisions=1)
        eye = trimesh.creation.icosphere(subdivisions=0, radius=0.1)
        combined = trimesh.util.concatenate((body, eye))
        selected = largest_outer_component(combined)
        self.assertEqual(len(body.faces), len(selected.faces))


if __name__ == "__main__":
    unittest.main()
