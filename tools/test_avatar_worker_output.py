from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from tools.avatar_worker_output import (
    CONTROL_REPORT_SCHEMA,
    CONTROL_MAP_SCHEMA,
    PRODUCER_CLAIMS,
    RECIPE_SCHEMA,
    REJECTION_SCHEMA,
    REQUIRED_FILE_ROLES,
    create_output,
    verify_output,
)
from tools.test_avatar_worker_input import AvatarWorkerInputTests


class AvatarWorkerOutputTests(unittest.TestCase):
    def write_input(self, root: Path) -> Path:
        helper = AvatarWorkerInputTests()
        bundle = helper.write_source_bundle(root)
        bridge = helper.write_bridge(root)
        from tools.avatar_worker_input import create_input

        output = root / "input"
        create_input(bridge, bundle, output)
        return output

    def write_recipe(self, root: Path, input_directory: Path) -> Path:
        input_manifest = json.loads(
            (input_directory / "avatar-worker-input-manifest.json").read_text(
                encoding="utf-8"
            )
        )
        input_document = json.loads(
            (input_directory / "avatar-worker-input.json").read_text(encoding="utf-8")
        )
        identity = {
            "inputId": input_manifest["inputId"],
            "sourceRevisionBundleId": input_manifest["sourceRevisionBundleId"],
            "bodyStateId": input_manifest["bodyStateId"],
        }
        artifact_root = root / "candidate"
        artifact_root.mkdir()
        controls = []
        control_map_rows = []
        for source_kind, field in (("builtIn", "measurements"), ("custom", "customMeasurements")):
            for measurement in input_document["bodyState"][field]:
                controls.append(
                    {
                        "key": measurement["key"],
                        "sourceKind": source_kind,
                        "sourceValue": measurement["value"],
                        "sourceUnit": measurement["unit"],
                        "status": "unsupported",
                        "target": None,
                        "unsupportedReason": "No pinned-runtime mapping has been demonstrated.",
                    }
                )
                control_map_rows.append(
                    {
                        "key": measurement["key"],
                        "sourceKind": source_kind,
                        "sourceUnit": measurement["unit"],
                        "status": "unsupported",
                        "target": None,
                        "unsupportedReason": "No pinned-runtime mapping has been demonstrated.",
                    }
                )
        control_report = {
            "schemaVersion": CONTROL_REPORT_SCHEMA,
            **identity,
            "controls": controls,
        }
        rejection_list = {
            "schemaVersion": REJECTION_SCHEMA,
            **identity,
            "producerAccepted": False,
            "rejections": ["Independent numerical and visual review is pending."],
        }
        identity_document = {
            "schemaVersion": "patterna.avatar-worker-evidence/1.0",
            **identity,
        }
        files: dict[str, dict[str, str]] = {}
        for role in sorted(REQUIRED_FILE_ROLES):
            if role == "controlApplicationReport":
                document = control_report
                suffix = ".json"
            elif role == "rejectionList":
                document = rejection_list
                suffix = ".json"
            elif role in {
                "displayToColliderMap",
                "landmarks",
                "measurements",
                "colliderRegistration",
            }:
                document = identity_document
                suffix = ".json"
            else:
                document = None
                suffix = ".glb" if role == "displayMesh" else ".obj" if role == "collisionMesh" else ".png"
            path = artifact_root / f"{role}{suffix}"
            if document is None:
                path.write_bytes(f"test {role}\n".encode("utf-8"))
            else:
                path.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")
            files[role] = {"path": str(path.relative_to(root))}
        worker = root / "worker.py"
        worker.write_text("print('worker')\n", encoding="utf-8")
        control_map_identity = {
            "schemaVersion": CONTROL_MAP_SCHEMA,
            "candidate": {
                "backend": "Anny",
                "releaseVersion": "0.6.0",
                "wheelSha256": "050a0b24a3e7fdb89b46dc3581947ea84225305425ac9a1a97b65ea997fb2ad6",
                "topology": "anny",
                "rig": "anny-104-bone",
            },
            "claims": {"declaredComplete": True, "accepted": False},
            "controls": control_map_rows,
        }
        from tools.revision_bundle import canonical_json, sha256_bytes

        control_map = {
            **control_map_identity,
            "controlMapId": sha256_bytes(canonical_json(control_map_identity)),
        }
        control_map_path = root / "control-map.json"
        control_map_path.write_text(
            json.dumps(control_map, indent=2) + "\n",
            encoding="utf-8",
        )
        recipe = {
            "schemaVersion": RECIPE_SCHEMA,
            "configuration": {
                "topology": "anny",
                "rig": "anny-104-bone",
                "dtype": "float64",
                "device": "cuda:0",
                "seed": 4127,
                "offline": True,
                "implicitDownloadsAllowed": False,
            },
            "claims": PRODUCER_CLAIMS,
            "worker": {"path": worker.name, "version": "test-1"},
            "controlMap": {"path": control_map_path.name},
            "files": files,
        }
        recipe_path = root / "output-recipe.json"
        recipe_path.write_text(json.dumps(recipe, indent=2) + "\n", encoding="utf-8")
        return recipe_path

    def test_create_and_verify_are_deterministic_and_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as raw_root:
            root = Path(raw_root)
            input_directory = self.write_input(root)
            recipe = self.write_recipe(root, input_directory)
            first = create_output(recipe, input_directory, root / "first")
            second = create_output(recipe, input_directory, root / "second")
            self.assertEqual(first["outputId"], second["outputId"])
            self.assertEqual(first["claims"], PRODUCER_CLAIMS)
            self.assertEqual(
                first["outputId"],
                verify_output(root / "first", input_directory)["outputId"],
            )

    def test_producer_acceptance_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as raw_root:
            root = Path(raw_root)
            input_directory = self.write_input(root)
            recipe_path = self.write_recipe(root, input_directory)
            recipe = json.loads(recipe_path.read_text(encoding="utf-8"))
            recipe["claims"]["avatarAccepted"] = True
            recipe_path.write_text(json.dumps(recipe, indent=2) + "\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "every acceptance claim false"):
                create_output(recipe_path, input_directory, root / "output")

    def test_incomplete_control_report_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as raw_root:
            root = Path(raw_root)
            input_directory = self.write_input(root)
            recipe_path = self.write_recipe(root, input_directory)
            recipe = json.loads(recipe_path.read_text(encoding="utf-8"))
            report_path = root / recipe["files"]["controlApplicationReport"]["path"]
            report = json.loads(report_path.read_text(encoding="utf-8"))
            report["controls"].pop()
            report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "incomplete"):
                create_output(recipe_path, input_directory, root / "output")

    def test_incomplete_control_map_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as raw_root:
            root = Path(raw_root)
            input_directory = self.write_input(root)
            recipe_path = self.write_recipe(root, input_directory)
            recipe = json.loads(recipe_path.read_text(encoding="utf-8"))
            map_path = root / recipe["controlMap"]["path"]
            control_map = json.loads(map_path.read_text(encoding="utf-8"))
            control_map["controls"].pop()
            map_path.write_text(json.dumps(control_map, indent=2) + "\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "control map is incomplete"):
                create_output(recipe_path, input_directory, root / "output")

    def test_self_accepted_control_map_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as raw_root:
            root = Path(raw_root)
            input_directory = self.write_input(root)
            recipe_path = self.write_recipe(root, input_directory)
            recipe = json.loads(recipe_path.read_text(encoding="utf-8"))
            map_path = root / recipe["controlMap"]["path"]
            control_map = json.loads(map_path.read_text(encoding="utf-8"))
            control_map["claims"]["accepted"] = True
            map_path.write_text(json.dumps(control_map, indent=2) + "\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "remain unaccepted"):
                create_output(recipe_path, input_directory, root / "output")

    def test_tampered_output_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as raw_root:
            root = Path(raw_root)
            input_directory = self.write_input(root)
            recipe = self.write_recipe(root, input_directory)
            manifest = create_output(recipe, input_directory, root / "output")
            display = next(
                item for item in manifest["files"] if item["role"] == "displayMesh"
            )
            (root / "output" / display["bundlePath"]).write_bytes(b"tampered")
            with self.assertRaisesRegex(ValueError, "size changed|hash changed"):
                verify_output(root / "output", input_directory)

    def test_legacy_fit_report_cannot_satisfy_the_new_contract(self) -> None:
        with tempfile.TemporaryDirectory() as raw_root:
            root = Path(raw_root)
            input_directory = self.write_input(root)
            recipe_path = self.write_recipe(root, input_directory)
            recipe = json.loads(recipe_path.read_text(encoding="utf-8"))
            report_path = root / recipe["files"]["controlApplicationReport"]["path"]
            report_path.write_text(
                json.dumps(
                    {
                        "schemaVersion": "patterna.anny-profile-fit/1.0",
                        "backend": "Anny 0.5 default topology",
                        "accepted": True,
                    },
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "control report schema"):
                create_output(recipe_path, input_directory, root / "output")


if __name__ == "__main__":
    unittest.main()
