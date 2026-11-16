from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from tools.revision_bundle import (
    SOURCE_INPUT_ROLES,
    create_bundle,
    verify_bundle,
)


class RevisionBundleTests(unittest.TestCase):
    def write_recipe(self, root: Path, *, accepted: bool = False) -> Path:
        source = root / "source.txt"
        source.write_text("one exact revision\n", encoding="utf-8")
        tool = root / "worker.exe"
        tool.write_bytes(b"worker-v1")
        recipe = {
            "schemaVersion": "patterna.revision-bundle-recipe/1.2",
            "contract": {
                "garmentArchetype": "adaptive-female-crew-neck-v1",
                "pose": "neutral-a",
                "seed": 4127,
                "units": "cm",
                "supported3dControls": ["height", "chest"],
            },
            "claims": {
                "accepted": accepted,
                "arrangementAccepted": False,
                "avatarAccepted": False,
                "clothAccepted": False,
            },
            "inputs": {
                role: {"path": source.name}
                for role in sorted(SOURCE_INPUT_ROLES)
            },
            "tools": {
                "proofWorker": {"path": tool.name, "version": "1.0"},
            },
        }
        recipe_path = root / "recipe.json"
        recipe_path.write_text(json.dumps(recipe, indent=2) + "\n", encoding="utf-8")
        return recipe_path

    def test_create_and_verify_are_deterministic(self) -> None:
        with tempfile.TemporaryDirectory() as raw_root:
            root = Path(raw_root)
            recipe = self.write_recipe(root)
            first = create_bundle(recipe, root / "first")
            second = create_bundle(recipe, root / "second")

            self.assertEqual(first["bundleId"], second["bundleId"])
            self.assertEqual(first["bundleId"], verify_bundle(root / "first")["bundleId"])
            object_paths = {entry["bundlePath"] for entry in first["inputs"]}
            self.assertEqual(1, len(object_paths))
            self.assertRegex(object_paths.pop(), r"^objects/[0-9a-f]{64}\.txt$")

    def test_verify_rejects_tampered_content(self) -> None:
        with tempfile.TemporaryDirectory() as raw_root:
            root = Path(raw_root)
            recipe = self.write_recipe(root)
            manifest = create_bundle(recipe, root / "bundle")
            object_path = root / "bundle" / manifest["inputs"][0]["bundlePath"]
            object_path.write_text("tampered\n", encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "size changed|hash changed"):
                verify_bundle(root / "bundle")

    def test_verify_rejects_undeclared_files(self) -> None:
        with tempfile.TemporaryDirectory() as raw_root:
            root = Path(raw_root)
            recipe = self.write_recipe(root)
            create_bundle(recipe, root / "bundle")
            (root / "bundle" / "stale-output.txt").write_text("stale", encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "file set changed"):
                verify_bundle(root / "bundle")

    def test_create_rejects_acceptance_claims(self) -> None:
        with tempfile.TemporaryDirectory() as raw_root:
            root = Path(raw_root)
            recipe = self.write_recipe(root, accepted=True)

            with self.assertRaisesRegex(ValueError, "must begin rejected"):
                create_bundle(recipe, root / "bundle")

    def test_create_never_overwrites_an_existing_directory(self) -> None:
        with tempfile.TemporaryDirectory() as raw_root:
            root = Path(raw_root)
            recipe = self.write_recipe(root)
            output = root / "bundle"
            output.mkdir()

            with self.assertRaisesRegex(FileExistsError, "immutable"):
                create_bundle(recipe, output)

    def test_source_contract_rejects_arrangement_as_an_input(self) -> None:
        with tempfile.TemporaryDirectory() as raw_root:
            root = Path(raw_root)
            recipe_path = self.write_recipe(root)
            recipe = json.loads(recipe_path.read_text(encoding="utf-8"))
            recipe["inputs"]["arrangement"] = {"path": "source.txt"}
            recipe_path.write_text(json.dumps(recipe, indent=2) + "\n", encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "unknown arrangement"):
                create_bundle(recipe_path, root / "bundle")


if __name__ == "__main__":
    unittest.main()
