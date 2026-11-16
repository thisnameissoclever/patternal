#!/usr/bin/env python3
"""Create and verify an immutable avatar-worker input from a packaged bridge."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from pathlib import Path, PurePosixPath
import shutil
import sys
import tempfile
from typing import Any

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from tools.revision_bundle import canonical_json, sha256_file, verify_bundle


INPUT_SCHEMA = "patterna.avatar-worker-input/1.0"
MANIFEST_SCHEMA = "patterna.avatar-worker-input-manifest/1.0"
BRIDGE_SCHEMA = "patterna.unreal-bridge/1.0"
EXPECTED_BUILT_IN_CONTROL_COUNT = 151
PRIMARY_CONTROL_KEYS = {"height", "chest", "waist", "hip", "shoulder", "torso"}
ALLOWED_ORIGINS = {"manual-or-baseline", "manual", "estimated"}
ANNY_RELEASE_VERSION = "0.6.0"
ANNY_RELEASE_TAG_COMMIT = "72104cac8242d1735ec06433b65bec5e26953ce7"
ANNY_REVIEWED_COMMIT = "81ca83e202273b306205c1cc15f33734be31e48c"
ANNY_WHEEL_FILENAME = "anny-0.6.0-py3-none-any.whl"
ANNY_WHEEL_SHA256 = "050a0b24a3e7fdb89b46dc3581947ea84225305425ac9a1a97b65ea997fb2ad6"
ANNY_WHEEL_BYTE_LENGTH = 47_705_473
ANNY_DATA_FILE_COUNT = 1_559
ANNY_DATA_UNCOMPRESSED_BYTES = 107_825_068


def require_object(value: Any, name: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{name} must be an object.")
    return value


def require_list(value: Any, name: str) -> list[Any]:
    if not isinstance(value, list):
        raise ValueError(f"{name} must be an array.")
    return value


def normalized_measurements(bridge: dict[str, Any]) -> list[dict[str, Any]]:
    body = require_object(bridge.get("body"), "bridge body")
    raw_measurements = require_list(body.get("measurements"), "bridge measurements")
    if len(raw_measurements) != EXPECTED_BUILT_IN_CONTROL_COUNT:
        raise ValueError(
            "The avatar worker requires exactly "
            f"{EXPECTED_BUILT_IN_CONTROL_COUNT} built-in controls; "
            f"received {len(raw_measurements)}."
        )
    normalized: list[dict[str, Any]] = []
    seen: set[str] = set()
    for raw in raw_measurements:
        measurement = require_object(raw, "bridge measurement")
        key = measurement.get("key")
        label = measurement.get("label")
        unit = measurement.get("unit")
        origin = measurement.get("origin")
        value = measurement.get("value")
        if not isinstance(key, str) or not key or key in seen:
            raise ValueError("Every built-in avatar control needs a unique non-empty key.")
        if not isinstance(label, str) or not label:
            raise ValueError(f"Avatar control {key} has no label.")
        if not isinstance(unit, str) or not unit:
            raise ValueError(f"Avatar control {key} has no unit.")
        if origin not in ALLOWED_ORIGINS:
            raise ValueError(f"Avatar control {key} has an unsupported origin: {origin}")
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
            raise ValueError(f"Avatar control {key} must have a finite numeric value.")
        seen.add(key)
        normalized.append(
            {
                "key": key,
                "label": label,
                "value": float(value),
                "unit": unit,
                "origin": origin,
            }
        )
    missing_primary = sorted(PRIMARY_CONTROL_KEYS - seen)
    if missing_primary:
        raise ValueError("The bridge is missing primary controls: " + ", ".join(missing_primary))
    return sorted(normalized, key=lambda item: item["key"])


def normalized_custom_measurements(bridge: dict[str, Any]) -> list[dict[str, Any]]:
    body = require_object(bridge.get("body"), "bridge body")
    raw_custom = require_list(body.get("customMeasurements"), "custom measurements")
    normalized: list[dict[str, Any]] = []
    seen: set[str] = set()
    for raw in raw_custom:
        measurement = require_object(raw, "custom measurement")
        key = measurement.get("key")
        name = measurement.get("name")
        unit = measurement.get("unit")
        value = measurement.get("value")
        if not isinstance(key, str) or not key or key in seen:
            raise ValueError("Every custom measurement needs a unique non-empty key.")
        if not isinstance(name, str) or not name:
            raise ValueError(f"Custom measurement {key} has no name.")
        if not isinstance(unit, str) or not unit:
            raise ValueError(f"Custom measurement {key} has no unit.")
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
            raise ValueError(f"Custom measurement {key} must have a finite numeric value.")
        seen.add(key)
        normalized.append(
            {"key": key, "name": name, "value": float(value), "unit": unit}
        )
    return sorted(normalized, key=lambda item: item["key"])


def build_input_document(
    bridge: dict[str, Any],
    bridge_sha256: str,
    source_bundle_id: str,
) -> dict[str, Any]:
    if bridge.get("schemaVersion") != BRIDGE_SCHEMA:
        raise ValueError("The avatar worker requires patterna.unreal-bridge/1.0 input.")
    body = require_object(bridge.get("body"), "bridge body")
    garment = require_object(bridge.get("garment"), "bridge garment")
    topology = require_object(bridge.get("patternTopology"), "pattern topology")
    measurements = normalized_measurements(bridge)
    custom_measurements = normalized_custom_measurements(bridge)
    if body.get("units") != "centimeters":
        raise ValueError("The avatar-worker bridge must use centimeters.")
    if not isinstance(body.get("posture"), str) or not body["posture"]:
        raise ValueError("The avatar-worker bridge has no posture.")
    if not isinstance(body.get("bodyTemplate"), str) or not body["bodyTemplate"]:
        raise ValueError("The avatar-worker bridge has no body template.")
    if topology.get("isValid") is not True:
        raise ValueError("The packaged bridge reports invalid pattern topology.")

    body_state = {
        "units": body["units"],
        "posture": body["posture"],
        "bodyTemplate": body["bodyTemplate"],
        "linkedPhotoCount": int(body.get("linkedPhotoCount", 0)),
        "measurements": measurements,
        "customMeasurements": custom_measurements,
    }
    body_state_id = hashlib.sha256(canonical_json(body_state)).hexdigest()
    return {
        "schemaVersion": INPUT_SCHEMA,
        "sourceRevisionBundleId": source_bundle_id,
        "sourceBridge": {
            "path": "source-bridge.json",
            "sha256": bridge_sha256,
            "schemaVersion": BRIDGE_SCHEMA,
            "generatedAtUtc": bridge.get("generatedAtUtc"),
        },
        "bodyStateId": body_state_id,
        "bodyState": body_state,
        "sourceGarment": {
            "id": garment.get("id"),
            "schemaVersion": garment.get("schemaVersion"),
            "panelCount": len(require_list(garment.get("panels"), "garment panels")),
            "seamCount": len(require_list(garment.get("seams"), "garment seams")),
            "topologySchemaVersion": topology.get("schemaVersion"),
        },
        "candidate": {
            "backend": "Anny",
            "releaseVersion": ANNY_RELEASE_VERSION,
            "releaseTagCommit": ANNY_RELEASE_TAG_COMMIT,
            "reviewedPostReleaseCommit": ANNY_REVIEWED_COMMIT,
            "executionArtifact": {
                "filename": ANNY_WHEEL_FILENAME,
                "byteLength": ANNY_WHEEL_BYTE_LENGTH,
                "sha256": ANNY_WHEEL_SHA256,
                "nativeDataFileCount": ANNY_DATA_FILE_COUNT,
                "nativeDataUncompressedBytes": ANNY_DATA_UNCOMPRESSED_BYTES,
            },
            "postReleaseKeypointDeviceFixRequired": False,
            "topology": "anny",
            "rig": "anny-104-bone",
            "implicitDownloadsAllowed": False,
            "restrictedModelFamiliesAllowed": [],
        },
        "claims": {
            "executionAuthorized": False,
            "mappingComplete": False,
            "avatarAccepted": False,
            "displayAccepted": False,
            "colliderAccepted": False,
            "productAccepted": False,
        },
        "requiredMapping": {
            "builtInControlCount": len(measurements),
            "controlKeys": [item["key"] for item in measurements],
            "customMeasurementCount": len(custom_measurements),
            "unsupportedControlsMustFailClosed": True,
        },
    }


def create_input(
    bridge_path: Path,
    source_bundle_directory: Path,
    output_directory: Path,
) -> dict[str, Any]:
    bridge_path = bridge_path.resolve(strict=True)
    source_manifest = verify_bundle(source_bundle_directory.resolve(strict=True))
    output_directory = output_directory.resolve()
    if output_directory.exists():
        raise FileExistsError(f"Avatar-worker inputs are immutable: {output_directory}")
    bridge_sha256 = sha256_file(bridge_path)
    bridge = require_object(json.loads(bridge_path.read_text(encoding="utf-8")), "bridge")
    document = build_input_document(bridge, bridge_sha256, source_manifest["bundleId"])

    output_directory.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(
        tempfile.mkdtemp(prefix=f".{output_directory.name}-", dir=output_directory.parent)
    )
    try:
        shutil.copyfile(bridge_path, temporary / "source-bridge.json")
        document_path = temporary / "avatar-worker-input.json"
        document_path.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")
        file_paths = sorted(
            path.relative_to(temporary).as_posix()
            for path in temporary.rglob("*")
            if path.is_file()
        )
        files = [
            {
                "path": relative,
                "byteLength": (temporary / relative).stat().st_size,
                "sha256": sha256_file(temporary / relative),
            }
            for relative in file_paths
        ]
        identity = {
            "schemaVersion": MANIFEST_SCHEMA,
            "sourceRevisionBundleId": source_manifest["bundleId"],
            "bodyStateId": document["bodyStateId"],
            "claims": {"executionAuthorized": False, "accepted": False},
            "files": files,
        }
        manifest = {
            **identity,
            "inputId": hashlib.sha256(canonical_json(identity)).hexdigest(),
        }
        (temporary / "avatar-worker-input-manifest.json").write_text(
            json.dumps(manifest, indent=2) + "\n",
            encoding="utf-8",
        )
        os.replace(temporary, output_directory)
    except BaseException:
        shutil.rmtree(temporary, ignore_errors=True)
        raise
    return manifest


def safe_relative_path(raw_path: Any) -> PurePosixPath:
    if not isinstance(raw_path, str) or not raw_path:
        raise ValueError("Every input file path must be a non-empty string.")
    path = PurePosixPath(raw_path)
    if path.is_absolute() or ".." in path.parts or "\\" in raw_path:
        raise ValueError(f"Unsafe input file path: {raw_path}")
    return path


def verify_input(
    input_directory: Path,
    source_bundle_directory: Path | None = None,
) -> dict[str, Any]:
    root = input_directory.resolve(strict=True)
    manifest_path = root / "avatar-worker-input-manifest.json"
    manifest = require_object(
        json.loads(manifest_path.read_text(encoding="utf-8")), "input manifest"
    )
    if manifest.get("schemaVersion") != MANIFEST_SCHEMA:
        raise ValueError("Unsupported avatar-worker input manifest schema.")
    if manifest.get("claims") != {"executionAuthorized": False, "accepted": False}:
        raise ValueError("An avatar-worker input cannot authorize or accept itself.")
    files = require_list(manifest.get("files"), "input manifest files")
    declared: set[str] = set()
    for raw_entry in files:
        entry = require_object(raw_entry, "input manifest file")
        relative = safe_relative_path(entry.get("path"))
        relative_text = relative.as_posix()
        if relative_text in declared:
            raise ValueError(f"Duplicate declared input file: {relative_text}")
        declared.add(relative_text)
        path = root.joinpath(*relative.parts)
        if path.is_symlink() or not path.is_file():
            raise ValueError(f"Declared input file is missing or is a symlink: {relative_text}")
        if path.stat().st_size != entry.get("byteLength"):
            raise ValueError(f"Avatar-worker input file size changed: {relative_text}")
        if sha256_file(path) != entry.get("sha256"):
            raise ValueError(f"Avatar-worker input file hash changed: {relative_text}")
    actual = {
        path.relative_to(root).as_posix()
        for path in root.rglob("*")
        if path.is_file() and path.name != manifest_path.name
    }
    if actual != declared:
        raise ValueError("The immutable avatar-worker input file set changed.")
    identity = {
        "schemaVersion": manifest["schemaVersion"],
        "sourceRevisionBundleId": manifest.get("sourceRevisionBundleId"),
        "bodyStateId": manifest.get("bodyStateId"),
        "claims": manifest["claims"],
        "files": files,
    }
    expected_input_id = hashlib.sha256(canonical_json(identity)).hexdigest()
    if manifest.get("inputId") != expected_input_id:
        raise ValueError("The avatar-worker input identity does not match its manifest.")

    document = require_object(
        json.loads((root / "avatar-worker-input.json").read_text(encoding="utf-8")),
        "avatar-worker input",
    )
    if document.get("schemaVersion") != INPUT_SCHEMA:
        raise ValueError("Unsupported avatar-worker input schema.")
    if document.get("claims", {}).get("executionAuthorized") is not False:
        raise ValueError("The avatar-worker input document authorizes execution.")
    if document.get("bodyStateId") != manifest.get("bodyStateId"):
        raise ValueError("The avatar-worker body-state identity changed.")
    bridge_path = root / "source-bridge.json"
    bridge = require_object(json.loads(bridge_path.read_text(encoding="utf-8")), "bridge")
    rebuilt = build_input_document(
        bridge,
        sha256_file(bridge_path),
        str(manifest.get("sourceRevisionBundleId")),
    )
    if rebuilt != document:
        raise ValueError("The avatar-worker input no longer matches its source bridge.")
    if source_bundle_directory is not None:
        source_manifest = verify_bundle(source_bundle_directory.resolve(strict=True))
        if source_manifest["bundleId"] != manifest.get("sourceRevisionBundleId"):
            raise ValueError("The supplied revision bundle does not match the avatar input.")
    return manifest


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    create_parser = subparsers.add_parser("create")
    create_parser.add_argument("--bridge", required=True, type=Path)
    create_parser.add_argument("--source-bundle", required=True, type=Path)
    create_parser.add_argument("--output-directory", required=True, type=Path)
    verify_parser = subparsers.add_parser("verify")
    verify_parser.add_argument("--input", required=True, type=Path)
    verify_parser.add_argument("--source-bundle", type=Path)
    return parser.parse_args()


def main() -> int:
    arguments = parse_arguments()
    if arguments.command == "create":
        result = create_input(
            arguments.bridge,
            arguments.source_bundle,
            arguments.output_directory,
        )
    else:
        result = verify_input(arguments.input, arguments.source_bundle)
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
