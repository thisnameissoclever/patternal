from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from tools.avatar_worker_input import (
    ANNY_RELEASE_TAG_COMMIT,
    ANNY_RELEASE_VERSION,
    ANNY_WHEEL_SHA256,
    create_input,
    verify_input,
)
from tools.revision_bundle import SOURCE_INPUT_ROLES, create_bundle


class AvatarWorkerInputTests(unittest.TestCase):
    def write_source_bundle(self, root: Path) -> Path:
        source = root / "source.txt"
        source.write_text("source\n", encoding="utf-8")
        tool = root / "tool.bin"
        tool.write_bytes(b"tool")
        recipe = {
            "schemaVersion": "patterna.revision-bundle-recipe/1.2",
            "contract": {
                "garmentArchetype": "adaptive-female-crew-neck-v1",
                "pose": "balanced-neutral-a",
                "seed": 4127,
                "units": "cm",
                "supported3dControls": [],
            },
            "claims": {
                "accepted": False,
                "avatarAccepted": False,
                "clothAccepted": False,
            },
            "inputs": {
                role: {"path": source.name} for role in sorted(SOURCE_INPUT_ROLES)
            },
            "tools": {"test": {"path": tool.name, "version": "1"}},
        }
        recipe_path = root / "recipe.json"
        recipe_path.write_text(json.dumps(recipe, indent=2) + "\n", encoding="utf-8")
        bundle = root / "bundle"
        create_bundle(recipe_path, bundle)
        return bundle

    def write_bridge(self, root: Path, count: int = 151) -> Path:
        primary = ["height", "chest", "waist", "hip", "shoulder", "torso"]
        keys = primary + [f"detail{index:03d}" for index in range(count - len(primary))]
        bridge = {
            "schemaVersion": "patterna.unreal-bridge/1.0",
            "generatedAtUtc": "2026-08-22T00:00:00Z",
            "body": {
                "units": "centimeters",
                "posture": "balanced",
                "bodyTemplate": "feminine",
                "linkedPhotoCount": 0,
                "measurements": [
                    {
                        "key": key,
                        "label": key,
                        "value": float(index + 1),
                        "unit": "cm",
                        "origin": "estimated",
                    }
                    for index, key in enumerate(keys)
                ],
                "customMeasurements": [
                    {"key": "custom_1", "name": "Custom", "value": 0.0, "unit": "cm"}
                ],
            },
            "garment": {
                "schemaVersion": "patterna.garment/1.1",
                "id": "shirt",
                "panels": [{}] * 14,
                "seams": [{}] * 38,
            },
            "patternTopology": {
                "schemaVersion": "patterna.topology/1.1",
                "isValid": True,
            },
        }
        path = root / "bridge.json"
        path.write_text(json.dumps(bridge, indent=2) + "\n", encoding="utf-8")
        return path

    def test_create_and_verify_complete_input(self) -> None:
        with tempfile.TemporaryDirectory() as raw_root:
            root = Path(raw_root)
            bundle = self.write_source_bundle(root)
            bridge = self.write_bridge(root)
            first = create_input(bridge, bundle, root / "first")
            second = create_input(bridge, bundle, root / "second")
            self.assertEqual(first["inputId"], second["inputId"])
            self.assertEqual(first["inputId"], verify_input(root / "first", bundle)["inputId"])
            document = json.loads(
                (root / "first" / "avatar-worker-input.json").read_text(encoding="utf-8")
            )
            self.assertEqual(document["candidate"]["releaseVersion"], ANNY_RELEASE_VERSION)
            self.assertEqual(document["candidate"]["releaseTagCommit"], ANNY_RELEASE_TAG_COMMIT)
            self.assertEqual(
                document["candidate"]["executionArtifact"]["sha256"],
                ANNY_WHEEL_SHA256,
            )
            self.assertFalse(document["candidate"]["postReleaseKeypointDeviceFixRequired"])

    def test_incomplete_control_state_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as raw_root:
            root = Path(raw_root)
            bundle = self.write_source_bundle(root)
            bridge = self.write_bridge(root, count=150)
            with self.assertRaisesRegex(ValueError, "exactly 151"):
                create_input(bridge, bundle, root / "input")

    def test_tampered_source_bridge_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as raw_root:
            root = Path(raw_root)
            bundle = self.write_source_bundle(root)
            bridge = self.write_bridge(root)
            create_input(bridge, bundle, root / "input")
            copied_bridge = root / "input" / "source-bridge.json"
            copied_bridge.write_text("{}\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "size changed|hash changed"):
                verify_input(root / "input")

    def test_execution_authorization_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as raw_root:
            root = Path(raw_root)
            bundle = self.write_source_bundle(root)
            bridge = self.write_bridge(root)
            create_input(bridge, bundle, root / "input")
            manifest_path = root / "input" / "avatar-worker-input-manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["claims"]["executionAuthorized"] = True
            manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "cannot authorize"):
                verify_input(root / "input")


if __name__ == "__main__":
    unittest.main()
