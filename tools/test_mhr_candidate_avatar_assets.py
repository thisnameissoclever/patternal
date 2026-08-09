#!/usr/bin/env python3
"""Validate the packaged MHR display-avatar candidate without Blender."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import struct
import unittest


REPO_ROOT = Path(__file__).resolve().parents[1]
ASSET_ROOT = REPO_ROOT / "Patternal" / "Assets" / "Candidate" / "MHR"
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


class MhrCandidateAvatarAssetTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.manifest = json.loads((ASSET_ROOT / "manifest.json").read_text(encoding="utf-8"))
        cls.geometry_path = ASSET_ROOT / cls.manifest["geometry"]
        cls.license_path = ASSET_ROOT / cls.manifest["licenseFile"]
        cls.document, cls.binary = read_glb(cls.geometry_path)

    def test_manifest_keeps_product_acceptance_open(self) -> None:
        self.assertEqual("patterna.display-avatar-glb/1.0", self.manifest["schemaVersion"])
        self.assertIs(False, self.manifest["accepted"])
        self.assertIs(True, self.manifest["candidateOnly"])
        self.assertEqual("mhr-candidate", self.manifest["displayMode"])
        self.assertEqual(180.0, self.manifest["displayYawDegrees"])
        self.assertIn("six-view host and packaged visual review is pending", self.manifest["openGates"])
        self.assertIn("cloth has not been solved and accepted on this exact MHR body", self.manifest["openGates"])
        self.assertIn("measurement edits do not yet rebuild this MHR family in the packaged app", self.manifest["openGates"])

    def test_hash_bound_assets_match_the_manifest(self) -> None:
        self.assertEqual(self.manifest["geometryBytes"], self.geometry_path.stat().st_size)
        self.assertEqual(self.manifest["geometrySha256"], sha256(self.geometry_path))
        self.assertEqual(self.manifest["licenseSha256"], sha256(self.license_path))
        self.assertEqual("Apache-2.0", self.manifest["outputLicense"])

    def test_numerical_avatar_gates_are_accepted(self) -> None:
        self.assertIs(True, self.manifest["measurementFit"]["accepted"])
        self.assertIs(True, self.manifest["rig"]["accepted"])
        self.assertIs(True, self.manifest["registration"]["accepted"])
        self.assertIs(True, self.manifest["anatomy"]["accepted"])
        self.assertIs(True, self.manifest["pose"]["accepted"])
        self.assertEqual(0, self.manifest["rig"]["unweightedVertexCount"])
        self.assertEqual(126, self.manifest["rig"]["boneCount"])
        self.assertLess(self.manifest["registration"]["maximumSurfaceDistanceM"], 0.00001)

    def test_glb_matches_the_packaged_loader_contract(self) -> None:
        self.assertEqual("2.0", self.document["asset"]["version"])
        nodes = self.document["nodes"]
        mesh_nodes = [node for node in nodes if "mesh" in node]
        self.assertEqual(10, len(mesh_nodes))
        for node in mesh_nodes:
            self.assertFalse({"matrix", "translation", "rotation", "scale"} & set(node))
        body_node = next(node for node in nodes if node.get("name") == self.manifest["primaryBodyNode"])
        self.assertIn("skin", body_node)
        primitive = self.document["meshes"][body_node["mesh"]]["primitives"][0]
        self.assertIn("JOINTS_0", primitive["attributes"])
        self.assertIn("WEIGHTS_0", primitive["attributes"])
        self.assertEqual(1, len(self.document["skins"]))
        self.assertEqual(126, len(self.document["skins"][0]["joints"]))
        material_names = {material["name"] for material in self.document["materials"]}
        self.assertIn(self.manifest["primaryBodyMaterial"], material_names)
        node_names = {node.get("name") for node in mesh_nodes}
        self.assertTrue(set(self.manifest["assetNodes"]).issubset(node_names))

    def test_all_binary_views_stay_inside_the_glb_chunk(self) -> None:
        for buffer_view in self.document["bufferViews"]:
            start = buffer_view.get("byteOffset", 0)
            self.assertLessEqual(start + buffer_view["byteLength"], len(self.binary))

    def test_renderer_loads_the_mhr_candidate_by_manifest_contract(self) -> None:
        renderer = PACKAGED_RENDERER.read_text(encoding="utf-8")
        self.assertIn("loadCandidateDisplayAvatar(baseUrl='Candidate/MHR/')", renderer)
        self.assertIn("manifest.primaryBodyNode", renderer)
        self.assertIn("manifest.primaryBodyMaterial", renderer)
        self.assertIn("manifest.assetNodes", renderer)
        self.assertIn("mode:String(manifest.displayMode", renderer)
        self.assertIn("mesh node ${node.name||nodeIndex} has an unsupported transform", renderer)
        self.assertIn("mhrCandidate?'fitted-mhr-candidate'", renderer)


if __name__ == "__main__":
    unittest.main()
