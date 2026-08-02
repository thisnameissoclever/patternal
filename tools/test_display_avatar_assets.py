#!/usr/bin/env python3
"""Validate the generated display avatar package without Blender."""

from __future__ import annotations

import json
import math
from pathlib import Path
import unittest


REPO_ROOT = Path(__file__).resolve().parents[1]
ASSET_ROOT = REPO_ROOT / "Patterna" / "Assets" / "Production" / "Avatar"
REQUIRED_ASSETS = {
    "body", "bra", "eyes", "teeth", "eyebrows", "eyelashes", "hair",
}


def parse_obj(path: Path) -> tuple[list[tuple[float, float, float]], int, int]:
    vertices: list[tuple[float, float, float]] = []
    uv_count = 0
    face_count = 0
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith("v "):
            vertex = tuple(float(value) for value in line.split()[1:4])
            if len(vertex) != 3 or not all(math.isfinite(value) for value in vertex):
                raise ValueError(f"Invalid vertex in {path}")
            vertices.append(vertex)
        elif line.startswith("vt "):
            uv_count += 1
        elif line.startswith("f "):
            corners = line.split()[1:]
            if len(corners) < 3:
                raise ValueError(f"Invalid face in {path}")
            for corner in corners:
                parts = corner.split("/")
                vertex_index = int(parts[0])
                uv_index = int(parts[1])
                if not 1 <= vertex_index <= len(vertices):
                    raise ValueError(f"Invalid vertex reference in {path}")
                if not 1 <= uv_index <= uv_count:
                    raise ValueError(f"Invalid UV reference in {path}")
            face_count += 1
    return vertices, uv_count, face_count


class DisplayAvatarAssetTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.manifest = json.loads(
            (ASSET_ROOT / "manifest.json").read_text(encoding="utf-8")
        )

    def test_manifest_declares_complete_display_stack(self) -> None:
        self.assertEqual("patterna.display-avatar/1.0", self.manifest["schema_version"])
        self.assertEqual("CC0", self.manifest["license"])
        self.assertEqual(REQUIRED_ASSETS, set(self.manifest["assets"]))

    def test_geometry_and_textures_are_complete(self) -> None:
        for key, asset in self.manifest["assets"].items():
            with self.subTest(asset=key):
                geometry_path = ASSET_ROOT / asset["geometry"]
                texture_path = ASSET_ROOT / asset["texture"]
                self.assertTrue(geometry_path.is_file())
                self.assertTrue(texture_path.is_file())
                self.assertEqual(b"\x89PNG\r\n\x1a\n", texture_path.read_bytes()[:8])
                vertices, uv_count, face_count = parse_obj(geometry_path)
                self.assertEqual(asset["vertex_count"], len(vertices))
                self.assertEqual(asset["uv_count"], uv_count)
                self.assertEqual(asset["face_count"], face_count)

    def test_bra_is_an_optional_contiguous_display_surface(self) -> None:
        bra = self.manifest["assets"]["bra"]
        self.assertIs(True, bra["display_optional"])
        self.assertGreaterEqual(bra["maximum_surface_offset_m"], 0.0)
        self.assertLessEqual(bra["maximum_surface_offset_m"], 0.0001)
        self.assertGreaterEqual(bra["vertex_count"], 1500)
        self.assertGreaterEqual(bra["face_count"], 1400)
        self.assertEqual(bra["vertex_count"], bra["uv_count"])

    def test_body_matches_collision_topology_and_height(self) -> None:
        vertices, _, _ = parse_obj(ASSET_ROOT / "body.obj")
        self.assertEqual(13380, len(vertices))
        z_values = [vertex[2] for vertex in vertices]
        self.assertAlmostEqual(
            min(z_values),
            self.manifest["floor_offset_m"],
            delta=0.000001,
        )
        self.assertAlmostEqual(0.0, min(z_values) - self.manifest["floor_offset_m"])
        self.assertAlmostEqual(1.67, max(z_values) - min(z_values), delta=0.0015)

    def test_face_and_hair_assets_remain_near_the_head(self) -> None:
        for key in ("eyes", "eyebrows", "eyelashes"):
            with self.subTest(asset=key):
                vertices, _, _ = parse_obj(ASSET_ROOT / f"{key}.obj")
                z_values = [vertex[2] for vertex in vertices]
                self.assertGreater(min(z_values), 1.40)
                self.assertLess(max(z_values), 1.75)

        hair_vertices, _, _ = parse_obj(ASSET_ROOT / "hair.obj")
        hair_z_values = [vertex[2] for vertex in hair_vertices]
        self.assertGreater(min(hair_z_values), 1.05)
        self.assertGreater(max(hair_z_values), 1.60)
        self.assertLess(max(hair_z_values), 1.75)


if __name__ == "__main__":
    unittest.main()
