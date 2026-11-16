from __future__ import annotations

import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from tools.canonical_sewn_seed import verify_canonical_seed


VIEWS = ("front", "front-oblique", "left", "back", "back-oblique", "right")


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path: Path, value: dict) -> None:
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


def create_seed(root: Path) -> Path:
    mesh_path = root / "seed.obj"
    mesh_path.write_text("v 0 0 0\nv 1 0 0\nv 0 1 0\nf 1 2 3\n", encoding="utf-8")

    mapping_path = root / "source-map.json"
    write_json(
        mapping_path,
        {
            "schemaVersion": "patterna.sewn-source-map/1.0",
            "sourceVertexCount": 4,
            "solverVertexCount": 3,
            "sourceToSolver": [0, 1, 2, 2],
            "solverToSource": [[0], [1], [2, 3]],
        },
    )

    renders: dict[str, dict[str, str]] = {}
    reviewed: dict[str, str] = {}
    for index, view in enumerate(VIEWS):
        render_path = root / f"{view}.png"
        render_path.write_bytes(b"png-fixture-" + bytes([index]))
        digest = sha256(render_path)
        renders[view] = {"path": render_path.name, "sha256": digest}
        reviewed[view] = digest

    review_path = root / "visual-review.json"
    write_json(
        review_path,
        {
            "schema_version": "patterna.product-turntable/1.0",
            "renders": renders,
            "visual_quality": {
                "accepted": True,
                "review_required": False,
                "reviewed_render_sha256": reviewed,
                "issues": [],
            },
        },
    )

    manifest_path = root / "manifest.json"
    write_json(
        manifest_path,
        {
            "schemaVersion": "patterna.canonical-sewn-seed/1.0",
            "claims": {
                "seedAccepted": True,
                "sourceIdentityPreserved": True,
                "reversibleMapAccepted": True,
                "calibratedMaterial": True,
                "visualQualityAccepted": True,
            },
            "openGates": [],
            "source": {
                "revisionBundleId": "a" * 64,
                "patternSha256": "b" * 64,
                "bodyColliderSha256": "c" * 64,
                "garmentArchetype": "adaptive-female-crew-neck-14-panel-v1",
                "poseFamily": "shallow-a-pose-v1",
            },
            "files": {
                "solverMesh": {"path": mesh_path.name, "sha256": sha256(mesh_path)},
                "sourceMap": {
                    "path": mapping_path.name,
                    "sha256": sha256(mapping_path),
                },
                "visualReview": {
                    "path": review_path.name,
                    "sha256": sha256(review_path),
                },
            },
            "workflow": {"manualEditsAfterPublication": False},
            "metrics": {
                "bodyCollisions": 0,
                "selfIntersections": 0,
                "invertedTriangles": 0,
                "maximumSeamSeparationCm": 0.2,
                "p95MaterialEdgeStrain": 0.25,
                "maximumMaterialEdgeStrain": 2.0,
                "staticEquilibriumReached": True,
                "anatomicalRegionGatesAccepted": True,
                "symmetryAndFoldFrequencyAccepted": True,
            },
        },
    )
    return manifest_path


class CanonicalSewnSeedTests(unittest.TestCase):
    def test_accepts_complete_reversible_hash_bound_seed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            result = verify_canonical_seed(create_seed(Path(temporary)))

        self.assertTrue(result["accepted"])
        self.assertEqual([], result["reasons"])

    def test_rejects_mapping_that_loses_a_source_vertex(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            manifest_path = create_seed(root)
            mapping_path = root / "source-map.json"
            mapping = json.loads(mapping_path.read_text(encoding="utf-8"))
            mapping["sourceToSolver"] = [0, 1, 2]
            write_json(mapping_path, mapping)
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["files"]["sourceMap"]["sha256"] = sha256(mapping_path)
            write_json(manifest_path, manifest)

            result = verify_canonical_seed(manifest_path)

        self.assertFalse(result["accepted"])
        self.assertTrue(any("sourceToSolver" in reason for reason in result["reasons"]))

    def test_rejects_visual_review_or_render_hash_failure(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            manifest_path = create_seed(root)
            review_path = root / "visual-review.json"
            review = json.loads(review_path.read_text(encoding="utf-8"))
            review["visual_quality"]["accepted"] = False
            review["visual_quality"]["issues"] = ["Sleeve collapsed."]
            write_json(review_path, review)
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["files"]["visualReview"]["sha256"] = sha256(review_path)
            write_json(manifest_path, manifest)
            (root / "front.png").write_bytes(b"tampered")

            result = verify_canonical_seed(manifest_path)

        self.assertFalse(result["accepted"])
        self.assertTrue(any("visual review" in reason for reason in result["reasons"]))
        self.assertTrue(any("front render hash" in reason for reason in result["reasons"]))

    def test_rejects_failed_physical_gate_and_manual_repair(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            manifest_path = create_seed(root)
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["metrics"]["selfIntersections"] = 1
            manifest["metrics"]["p95MaterialEdgeStrain"] = 0.251
            manifest["workflow"]["manualEditsAfterPublication"] = True
            write_json(manifest_path, manifest)

            result = verify_canonical_seed(manifest_path)

        self.assertFalse(result["accepted"])
        self.assertTrue(any("selfIntersections" in reason for reason in result["reasons"]))
        self.assertTrue(any("p95MaterialEdgeStrain" in reason for reason in result["reasons"]))
        self.assertTrue(any("manualEditsAfterPublication" in reason for reason in result["reasons"]))

    def test_rejects_hash_tampering_and_false_claim(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            manifest_path = create_seed(root)
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["claims"]["seedAccepted"] = False
            write_json(manifest_path, manifest)
            (root / "seed.obj").write_text("tampered\n", encoding="utf-8")

            result = verify_canonical_seed(manifest_path)

        self.assertFalse(result["accepted"])
        self.assertTrue(any("claims.seedAccepted" in reason for reason in result["reasons"]))
        self.assertTrue(any("solverMesh hash" in reason for reason in result["reasons"]))


if __name__ == "__main__":
    unittest.main()
