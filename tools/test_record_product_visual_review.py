#!/usr/bin/env python3
"""Regression tests for exact, hash-bound product visual reviews."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from record_product_visual_review import REQUIRED_VIEWS, record_review


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class ProductVisualReviewTests(unittest.TestCase):
    def create_proof(self, root: Path) -> Path:
        renders: dict[str, dict[str, str]] = {}
        for view in REQUIRED_VIEWS:
            render_path = root / f"{view}.png"
            render_path.write_bytes(f"fixture {view}".encode("utf-8"))
            renders[view] = {
                "path": render_path.name,
                "sha256": sha256(render_path),
            }
        manifest_path = root / "manifest.json"
        manifest_path.write_text(
            json.dumps(
                {
                    "schema_version": "patterna.product-turntable/1.0",
                    "renders": renders,
                }
            ),
            encoding="utf-8",
        )
        return manifest_path

    def test_accept_binds_review_to_all_exact_view_hashes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            manifest_path = self.create_proof(Path(directory))
            record_review(manifest_path, accepted=True, issues=[])
            proof = json.loads(manifest_path.read_text(encoding="utf-8"))
            quality = proof["visual_quality"]
            self.assertTrue(quality["accepted"])
            self.assertFalse(quality["review_required"])
            self.assertEqual(
                quality["reviewed_render_sha256"],
                {view: proof["renders"][view]["sha256"] for view in REQUIRED_VIEWS},
            )

    def test_tampered_render_cannot_be_reviewed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manifest_path = self.create_proof(root)
            (root / "back.png").write_bytes(b"tampered")
            with self.assertRaisesRegex(ValueError, "does not match"):
                record_review(manifest_path, accepted=True, issues=[])

    def test_rejection_requires_a_concrete_issue(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            manifest_path = self.create_proof(Path(directory))
            with self.assertRaisesRegex(ValueError, "at least one concrete issue"):
                record_review(manifest_path, accepted=False, issues=[])

    def test_render_path_cannot_escape_proof_directory(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            proof_directory = root / "proof"
            proof_directory.mkdir()
            manifest_path = self.create_proof(proof_directory)
            outside = root / "outside.png"
            outside.write_bytes(b"outside")
            proof = json.loads(manifest_path.read_text(encoding="utf-8"))
            proof["renders"]["front"] = {
                "path": "../outside.png",
                "sha256": sha256(outside),
            }
            manifest_path.write_text(json.dumps(proof), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "escapes"):
                record_review(manifest_path, accepted=True, issues=[])


if __name__ == "__main__":
    unittest.main()
