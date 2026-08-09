#!/usr/bin/env python3
"""Validate the packaged Antonia GLB candidate without Blender."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import struct
import unittest


REPO_ROOT = Path(__file__).resolve().parents[1]
ASSET_ROOT = REPO_ROOT / "Patternal" / "Assets" / "Candidate" / "Antonia"
SOURCE_LICENSE = (
    REPO_ROOT
    / "third_party"
    / "CharMorph-db"
    / "characters"
    / "antonia"
    / "license.txt"
)
PACKAGED_RENDERER = REPO_ROOT / "Patternal" / "Assets" / "avatar3d.html"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_glb(path: Path) -> tuple[dict[str, object], bytes]:
    payload = path.read_bytes()
    magic, version, declared_length = struct.unpack_from("<4sII", payload)
    if magic != b"glTF" or version != 2 or declared_length != len(payload):
        raise ValueError("Invalid GLB header")
    offset = 12
    document = None
    binary = None
    while offset < len(payload):
        length, chunk_type = struct.unpack_from("<II", payload, offset)
        offset += 8
        chunk = payload[offset : offset + length]
        offset += length
        if chunk_type == 0x4E4F534A:
            document = json.loads(chunk.decode("utf-8").rstrip("\x00 "))
        elif chunk_type == 0x004E4942:
            binary = chunk
    if not isinstance(document, dict) or binary is None:
        raise ValueError("GLB does not contain JSON and binary chunks")
    return document, binary


class CandidateAvatarAssetTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.manifest = json.loads((ASSET_ROOT / "manifest.json").read_text(encoding="utf-8"))
        cls.geometry_path = ASSET_ROOT / cls.manifest["geometry"]
        cls.document, cls.binary = read_glb(cls.geometry_path)

    def test_manifest_keeps_candidate_outside_production_acceptance(self) -> None:
        self.assertEqual("patterna.display-avatar-glb/1.0", self.manifest["schemaVersion"])
        self.assertIs(False, self.manifest["accepted"])
        self.assertIs(True, self.manifest["candidateOnly"])
        self.assertIs(True, self.manifest["measurementFit"]["accepted"])
        self.assertEqual(180.0, self.manifest["displayYawDegrees"])
        self.assertIn("cloth has not been solved on this body", self.manifest["openGates"])

    def test_registration_remains_explicitly_open_in_the_older_packaged_candidate(self) -> None:
        self.assertIn(
            "collision simplification and regional registration are not implemented",
            self.manifest["openGates"],
        )
        self.assertNotIn("schemaVersion", self.manifest["registration"])

    def test_geometry_and_license_match_the_manifest(self) -> None:
        self.assertEqual(self.manifest["geometryBytes"], self.geometry_path.stat().st_size)
        self.assertEqual(self.manifest["geometrySha256"], sha256(self.geometry_path))
        self.assertEqual(self.manifest["licenseSha256"], sha256(SOURCE_LICENSE))
        self.assertEqual("CC-BY 3.0", self.manifest["outputLicense"])
        self.assertEqual("Olaf Delgado-Friedrichs", self.manifest["author"])

    def test_glb_matches_the_narrow_packaged_loader_contract(self) -> None:
        self.assertEqual("2.0", self.document["asset"]["version"])
        self.assertEqual(0, self.document["scene"])
        self.assertEqual(3, len(self.document["scenes"][0]["nodes"]))
        nodes = self.document["nodes"]
        self.assertEqual(
            {
                "Patterna_Antonia_Body",
                "Patterna_Antonia_Panties",
                "Patterna_Antonia_ModestyBandeau",
            },
            {node["name"] for node in nodes},
        )
        for node in nodes:
            self.assertFalse({"matrix", "translation", "rotation", "scale"} & set(node))
        body_node = next(node for node in nodes if node["name"] == "Patterna_Antonia_Body")
        body_mesh = self.document["meshes"][body_node["mesh"]]
        self.assertEqual(15, len(body_mesh["primitives"]))
        material_names = {material["name"] for material in self.document["materials"]}
        self.assertIn("cm_antonia_body", material_names)
        self.assertGreaterEqual(len(self.document["images"]), 7)
        self.assertTrue(all("bufferView" in image for image in self.document["images"]))

    def test_all_binary_views_stay_inside_the_glb_chunk(self) -> None:
        for buffer_view in self.document["bufferViews"]:
            start = buffer_view.get("byteOffset", 0)
            self.assertLessEqual(start + buffer_view["byteLength"], len(self.binary))

    def test_packaged_renderer_uses_one_explicit_srgb_base_color_contract(self) -> None:
        renderer = PACKAGED_RENDERER.read_text(encoding="utf-8")
        self.assertIn("uniform float uSrgbBaseColor;", renderer)
        self.assertIn("vec3 srgbToLinear(vec3 value)", renderer)
        self.assertIn("vec3 linearToSrgb(vec3 value)", renderer)
        self.assertIn("gl.uniform1f(locations.srgbBaseColor,srgbBaseColor&&texture?1:0);", renderer)
        self.assertIn("state.displayBodyTexture,.66,.01,true", renderer)
        self.assertIn("loadTexture(objectUrl,{flipY:false,ignoreEmbeddedColorSpace:true})", renderer)
        self.assertIn("gl.UNPACK_COLORSPACE_CONVERSION_WEBGL", renderer)
        self.assertNotIn("gl.enable(gl.FRAMEBUFFER_SRGB)", renderer)

    def test_generator_scopes_stage_acceptance_away_from_product_acceptance(self) -> None:
        generator = (REPO_ROOT / "tools" / "generate_charmorph_avatar.py").read_text(
            encoding="utf-8"
        )
        preparation = (
            REPO_ROOT / "tools" / "prepare_charmorph_garmentcode_body.py"
        ).read_text(encoding="utf-8")
        self.assertIn(
            '"acceptanceScope": "measurement-fit-and-geometry-export"',
            generator,
        )
        self.assertIn('"productAccepted": False', generator)
        self.assertIn(
            '"productAcceptanceStatus": "candidate-pending-render-and-cloth-review"',
            generator,
        )
        self.assertIn("topology-eligible-pending-render-review", generator)
        self.assertNotIn("accepted-topology-pending-render-review", generator)
        self.assertIn(
            'avatar_report.get("acceptanceScope") != "measurement-fit-and-geometry-export"',
            preparation,
        )


if __name__ == "__main__":
    unittest.main()
