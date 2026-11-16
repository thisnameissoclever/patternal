#!/usr/bin/env python3
"""Create and verify immutable, producer-rejected Anny worker outputs."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import sys
import tempfile
from typing import Any

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from tools.avatar_worker_input import (
    ANNY_RELEASE_VERSION,
    ANNY_WHEEL_SHA256,
    verify_input,
)
from tools.revision_bundle import canonical_json, media_type, sha256_bytes, sha256_file


RECIPE_SCHEMA = "patterna.avatar-worker-output-recipe/1.0"
MANIFEST_SCHEMA = "patterna.avatar-worker-output-manifest/1.0"
CONTROL_REPORT_SCHEMA = "patterna.avatar-control-application/1.0"
REJECTION_SCHEMA = "patterna.avatar-worker-rejections/1.0"
CONTROL_MAP_SCHEMA = "patterna.anny-control-map/1.0"
PRODUCER_CLAIMS = {
    "producerAccepted": False,
    "avatarAccepted": False,
    "displayAccepted": False,
    "colliderAccepted": False,
    "productAccepted": False,
}
REQUIRED_CONFIGURATION = {
    "topology": "anny",
    "rig": "anny-104-bone",
    "offline": True,
    "implicitDownloadsAllowed": False,
}
REQUIRED_FILE_ROLES = {
    "displayMesh",
    "collisionMesh",
    "displayToColliderMap",
    "controlApplicationReport",
    "landmarks",
    "measurements",
    "colliderRegistration",
    "rejectionList",
    "renderFront",
    "renderBack",
    "renderLeft",
    "renderRight",
    "renderFrontOblique",
    "renderRearOblique",
    "renderFace",
    "renderHands",
    "renderFeet",
    "renderShoulder",
    "renderBust",
    "renderWaist",
    "renderHip",
}
IDENTITY_JSON_ROLES = {
    "displayToColliderMap",
    "controlApplicationReport",
    "landmarks",
    "measurements",
    "colliderRegistration",
    "rejectionList",
}


def require_object(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict) or not value:
        raise ValueError(f"{label} must be a nonempty JSON object.")
    return value


def require_string(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be a nonempty string.")
    return value


def resolve_file(recipe_path: Path, raw_path: Any, label: str) -> Path:
    source = Path(require_string(raw_path, f"{label} path"))
    if not source.is_absolute():
        source = recipe_path.parent / source
    if source.is_symlink():
        raise ValueError(f"{label} must not be a symlink: {source}")
    source = source.resolve(strict=True)
    if not source.is_file():
        raise ValueError(f"{label} must be a regular non-symlink file: {source}")
    return source


def validate_configuration(raw: Any) -> dict[str, Any]:
    configuration = require_object(raw, "configuration")
    for field, expected in REQUIRED_CONFIGURATION.items():
        if configuration.get(field) != expected:
            raise ValueError(f"Avatar worker configuration {field} must be {expected!r}.")
    require_string(configuration.get("dtype"), "configuration dtype")
    require_string(configuration.get("device"), "configuration device")
    seed = configuration.get("seed")
    if isinstance(seed, bool) or not isinstance(seed, int):
        raise ValueError("Avatar worker configuration seed must be an integer.")
    return configuration


def safe_bundle_path(raw: Any) -> PurePosixPath:
    path_text = require_string(raw, "bundlePath")
    path = PurePosixPath(path_text)
    if path.is_absolute() or ".." in path.parts or "\\" in path_text:
        raise ValueError(f"Unsafe avatar output bundle path: {path_text}")
    return path


def load_input(input_directory: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    input_directory = input_directory.resolve(strict=True)
    input_manifest = verify_input(input_directory)
    input_document = require_object(
        json.loads((input_directory / "avatar-worker-input.json").read_text(encoding="utf-8")),
        "avatar worker input",
    )
    return input_manifest, input_document


def input_identity(input_directory: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    input_manifest, input_document = load_input(input_directory)
    return {
        "inputId": input_manifest["inputId"],
        "sourceRevisionBundleId": input_manifest["sourceRevisionBundleId"],
        "bodyStateId": input_manifest["bodyStateId"],
        "manifestSha256": sha256_file(
            input_directory.resolve(strict=True) / "avatar-worker-input-manifest.json"
        ),
    }, input_document


def expected_controls(input_document: dict[str, Any]) -> dict[str, dict[str, Any]]:
    body_state = require_object(input_document.get("bodyState"), "input bodyState")
    result: dict[str, dict[str, Any]] = {}
    for source_kind, field in (("builtIn", "measurements"), ("custom", "customMeasurements")):
        values = body_state.get(field)
        if not isinstance(values, list):
            raise ValueError(f"Input bodyState {field} must be an array.")
        for raw in values:
            value = require_object(raw, f"{source_kind} control")
            key = require_string(value.get("key"), f"{source_kind} control key")
            if key in result:
                raise ValueError(f"Duplicate avatar control key across input sets: {key}")
            result[key] = {
                "sourceKind": source_kind,
                "sourceValue": value.get("value"),
                "sourceUnit": value.get("unit"),
            }
    return result


def validate_control_report(
    report: dict[str, Any],
    identity: dict[str, Any],
    input_document: dict[str, Any],
) -> None:
    if report.get("schemaVersion") != CONTROL_REPORT_SCHEMA:
        raise ValueError("Avatar control report schema is invalid.")
    controls = report.get("controls")
    if not isinstance(controls, list):
        raise ValueError("Avatar control report controls must be an array.")
    expected = expected_controls(input_document)
    seen: set[str] = set()
    for raw in controls:
        control = require_object(raw, "control application row")
        key = require_string(control.get("key"), "control application key")
        if key in seen or key not in expected:
            raise ValueError(f"Avatar control report contains a duplicate or unknown key: {key}")
        seen.add(key)
        source = expected[key]
        for field in ("sourceKind", "sourceValue", "sourceUnit"):
            if control.get(field) != source[field]:
                raise ValueError(f"Avatar control {key} changed {field} from the immutable input.")
        status = control.get("status")
        if status == "mapped":
            require_object(control.get("target"), f"mapped avatar control {key} target")
            if control.get("unsupportedReason") not in (None, ""):
                raise ValueError(f"Mapped avatar control {key} carries an unsupported reason.")
        elif status == "unsupported":
            require_string(control.get("unsupportedReason"), f"unsupported avatar control {key} reason")
            if control.get("target") not in (None, {}):
                raise ValueError(f"Unsupported avatar control {key} carries a target.")
        else:
            raise ValueError(f"Avatar control {key} has invalid status: {status!r}")
    if seen != expected.keys():
        missing = sorted(expected.keys() - seen)
        raise ValueError(f"Avatar control report is incomplete: {', '.join(missing)}")
    if report.get("inputId") != identity["inputId"]:
        raise ValueError("Avatar control report input identity changed.")


def validate_control_map(
    document: dict[str, Any],
    input_document: dict[str, Any],
) -> str:
    if document.get("schemaVersion") != CONTROL_MAP_SCHEMA:
        raise ValueError("Anny control map schema is invalid.")
    candidate = require_object(document.get("candidate"), "control map candidate")
    expected_candidate = {
        "backend": "Anny",
        "releaseVersion": ANNY_RELEASE_VERSION,
        "wheelSha256": ANNY_WHEEL_SHA256,
        "topology": "anny",
        "rig": "anny-104-bone",
    }
    if candidate != expected_candidate:
        raise ValueError("Anny control map candidate identity changed.")
    claims = document.get("claims")
    if claims != {"declaredComplete": True, "accepted": False}:
        raise ValueError("An executable control map must be complete and remain unaccepted.")
    controls = document.get("controls")
    if not isinstance(controls, list):
        raise ValueError("Anny control map controls must be an array.")
    expected = expected_controls(input_document)
    seen: set[str] = set()
    for raw in controls:
        control = require_object(raw, "Anny control map row")
        key = require_string(control.get("key"), "Anny control map key")
        if key in seen or key not in expected:
            raise ValueError(f"Anny control map contains a duplicate or unknown key: {key}")
        seen.add(key)
        source = expected[key]
        for field in ("sourceKind", "sourceUnit"):
            if control.get(field) != source[field]:
                raise ValueError(f"Anny control map {key} changed {field}.")
        status = control.get("status")
        if status == "mapped":
            target = require_object(control.get("target"), f"mapped control {key} target")
            family = target.get("family")
            if family not in {"phenotype", "localChange", "facialAction", "pose", "bone"}:
                raise ValueError(f"Mapped control {key} has invalid target family: {family!r}")
            require_string(target.get("key"), f"mapped control {key} target key")
            require_object(target.get("transform"), f"mapped control {key} transform")
            if control.get("unsupportedReason") not in (None, ""):
                raise ValueError(f"Mapped control {key} carries an unsupported reason.")
        elif status == "unsupported":
            require_string(control.get("unsupportedReason"), f"unsupported control {key} reason")
            if control.get("target") not in (None, {}):
                raise ValueError(f"Unsupported control {key} carries a target.")
        else:
            raise ValueError(f"Anny control map {key} has invalid status: {status!r}")
    if seen != expected.keys():
        missing = sorted(expected.keys() - seen)
        raise ValueError(f"Anny control map is incomplete: {', '.join(missing)}")
    map_identity = {
        "schemaVersion": document["schemaVersion"],
        "candidate": candidate,
        "claims": claims,
        "controls": controls,
    }
    expected_id = sha256_bytes(canonical_json(map_identity))
    if document.get("controlMapId") != expected_id:
        raise ValueError("Anny control map identity does not match its content.")
    return expected_id


def validate_identity_document(
    role: str,
    document: dict[str, Any],
    identity: dict[str, Any],
    input_document: dict[str, Any],
) -> None:
    if role == "controlApplicationReport":
        validate_control_report(document, identity, input_document)
    if role == "rejectionList":
        if document.get("schemaVersion") != REJECTION_SCHEMA:
            raise ValueError("Avatar rejection list schema is invalid.")
        if document.get("producerAccepted") is not False:
            raise ValueError("The avatar producer cannot accept its rejection list.")
        if not isinstance(document.get("rejections"), list):
            raise ValueError("Avatar rejection list rejections must be an array.")
    for field in ("inputId", "sourceRevisionBundleId", "bodyStateId"):
        if document.get(field) != identity[field]:
            raise ValueError(f"Avatar output {role} changed {field}.")


def build_manifest(
    recipe_path: Path,
    input_directory: Path,
) -> tuple[dict[str, Any], dict[str, Path], dict[str, Any]]:
    recipe = require_object(
        json.loads(recipe_path.read_text(encoding="utf-8")),
        "avatar output recipe",
    )
    if recipe.get("schemaVersion") != RECIPE_SCHEMA:
        raise ValueError(f"Avatar output recipe schema must be {RECIPE_SCHEMA}.")
    identity, input_document = input_identity(input_directory)
    configuration = validate_configuration(recipe.get("configuration"))
    if recipe.get("claims") != PRODUCER_CLAIMS:
        raise ValueError("An avatar producer must leave every acceptance claim false.")

    worker_raw = require_object(recipe.get("worker"), "worker")
    worker_path = resolve_file(recipe_path, worker_raw.get("path"), "worker")
    worker = {
        "fileName": worker_path.name,
        "version": require_string(worker_raw.get("version"), "worker version"),
        "byteLength": worker_path.stat().st_size,
        "sha256": sha256_file(worker_path),
    }

    control_map_path = resolve_file(
        recipe_path,
        require_object(recipe.get("controlMap"), "controlMap").get("path"),
        "controlMap",
    )
    control_map_document = require_object(
        json.loads(control_map_path.read_text(encoding="utf-8")),
        "Anny control map",
    )
    control_map_id = validate_control_map(control_map_document, input_document)
    control_map_sha256 = sha256_file(control_map_path)
    control_map_bundle_path = f"inputs/{control_map_sha256}.json"
    control_map = {
        "schemaVersion": CONTROL_MAP_SCHEMA,
        "controlMapId": control_map_id,
        "fileName": control_map_path.name,
        "bundlePath": control_map_bundle_path,
        "byteLength": control_map_path.stat().st_size,
        "sha256": control_map_sha256,
        "mediaType": "application/json",
    }

    raw_files = require_object(recipe.get("files"), "avatar output files")
    roles = set(raw_files)
    if roles != REQUIRED_FILE_ROLES:
        missing = sorted(REQUIRED_FILE_ROLES - roles)
        extra = sorted(roles - REQUIRED_FILE_ROLES)
        raise ValueError(
            "Avatar output roles are invalid: "
            + "; ".join(
                details
                for details in (
                    f"missing {', '.join(missing)}" if missing else "",
                    f"unknown {', '.join(extra)}" if extra else "",
                )
                if details
            )
        )

    sources: dict[str, Path] = {control_map_bundle_path: control_map_path}
    files: list[dict[str, Any]] = []
    for role, raw_entry in sorted(raw_files.items()):
        entry = require_object(raw_entry, f"avatar output {role}")
        source = resolve_file(recipe_path, entry.get("path"), f"avatar output {role}")
        digest = sha256_file(source)
        suffix = "".join(source.suffixes).lower()
        bundle_path = f"objects/{digest}{suffix}"
        declared = {
            "role": role,
            "fileName": source.name,
            "bundlePath": bundle_path,
            "byteLength": source.stat().st_size,
            "sha256": digest,
            "mediaType": media_type(source),
        }
        files.append(declared)
        sources[bundle_path] = source
        if role in IDENTITY_JSON_ROLES:
            document = require_object(
                json.loads(source.read_text(encoding="utf-8")),
                f"avatar output {role}",
            )
            validate_identity_document(role, document, identity, input_document)

    manifest_identity = {
        "schemaVersion": MANIFEST_SCHEMA,
        "acceptanceScope": "producer-evidence-only",
        "input": identity,
        "controlMap": control_map,
        "worker": worker,
        "configuration": configuration,
        "claims": PRODUCER_CLAIMS,
        "files": files,
    }
    return {
        **manifest_identity,
        "outputId": sha256_bytes(canonical_json(manifest_identity)),
    }, sources, input_document


def create_output(
    recipe_path: Path,
    input_directory: Path,
    output_directory: Path,
) -> dict[str, Any]:
    recipe_path = recipe_path.resolve(strict=True)
    input_directory = input_directory.resolve(strict=True)
    output_directory = output_directory.resolve()
    if output_directory.exists():
        raise FileExistsError(f"Avatar worker outputs are immutable: {output_directory}")
    manifest, sources, _ = build_manifest(recipe_path, input_directory)
    output_directory.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(
        tempfile.mkdtemp(prefix=f".{output_directory.name}-", dir=output_directory.parent)
    )
    try:
        for relative, source in sorted(sources.items()):
            destination = temporary / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, destination)
        (temporary / "avatar-worker-output-manifest.json").write_text(
            json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        verify_output(temporary, input_directory)
        os.replace(temporary, output_directory)
    except BaseException:
        shutil.rmtree(temporary, ignore_errors=True)
        raise
    return manifest


def verify_output(output_directory: Path, input_directory: Path) -> dict[str, Any]:
    root = output_directory.resolve(strict=True)
    identity, input_document = input_identity(input_directory.resolve(strict=True))
    manifest_path = root / "avatar-worker-output-manifest.json"
    manifest = require_object(
        json.loads(manifest_path.read_text(encoding="utf-8")),
        "avatar worker output manifest",
    )
    if manifest.get("schemaVersion") != MANIFEST_SCHEMA:
        raise ValueError(f"Avatar output manifest schema must be {MANIFEST_SCHEMA}.")
    if manifest.get("acceptanceScope") != "producer-evidence-only":
        raise ValueError("Avatar output acceptance scope changed.")
    if manifest.get("claims") != PRODUCER_CLAIMS:
        raise ValueError("An avatar output cannot carry an acceptance claim.")
    if manifest.get("input") != identity:
        raise ValueError("Avatar output input identity changed.")
    validate_configuration(manifest.get("configuration"))
    worker = require_object(manifest.get("worker"), "worker")
    for field in ("fileName", "version", "byteLength", "sha256"):
        if field not in worker:
            raise ValueError(f"Avatar output worker is missing {field}.")

    control_map = require_object(manifest.get("controlMap"), "controlMap")
    control_map_relative = safe_bundle_path(control_map.get("bundlePath"))
    control_map_unresolved = root.joinpath(*control_map_relative.parts)
    control_map_current = root
    for part in control_map_relative.parts:
        control_map_current /= part
        if control_map_current.is_symlink():
            raise ValueError(f"Avatar output contains a control-map symlink: {control_map_relative}")
    control_map_path = control_map_unresolved.resolve(strict=True)
    try:
        control_map_path.relative_to(root)
    except ValueError as error:
        raise ValueError("Avatar output control map escapes its directory.") from error
    if control_map_path.stat().st_size != control_map.get("byteLength"):
        raise ValueError("Avatar output control map size changed.")
    if sha256_file(control_map_path) != control_map.get("sha256"):
        raise ValueError("Avatar output control map hash changed.")
    control_map_document = require_object(
        json.loads(control_map_path.read_text(encoding="utf-8")),
        "Anny control map",
    )
    control_map_id = validate_control_map(control_map_document, input_document)
    if control_map.get("schemaVersion") != CONTROL_MAP_SCHEMA or control_map.get("controlMapId") != control_map_id:
        raise ValueError("Avatar output control-map declaration changed.")

    files = manifest.get("files")
    if not isinstance(files, list):
        raise ValueError("Avatar output files must be an array.")
    roles = {entry.get("role") for entry in files if isinstance(entry, dict)}
    if roles != REQUIRED_FILE_ROLES or len(files) != len(REQUIRED_FILE_ROLES):
        raise ValueError("Avatar output file roles are incomplete or duplicated.")
    declared_files = {
        "avatar-worker-output-manifest.json",
        control_map_path.relative_to(root).as_posix(),
    }
    for raw_entry in files:
        entry = require_object(raw_entry, "avatar output file")
        role = require_string(entry.get("role"), "avatar output role")
        relative = safe_bundle_path(entry.get("bundlePath"))
        unresolved = root.joinpath(*relative.parts)
        current = root
        for part in relative.parts:
            current /= part
            if current.is_symlink():
                raise ValueError(f"Avatar output contains a symlink: {relative}")
        candidate = unresolved.resolve(strict=True)
        try:
            candidate.relative_to(root)
        except ValueError as error:
            raise ValueError(f"Avatar output escapes its directory: {relative}") from error
        if not candidate.is_file():
            raise ValueError(f"Avatar output is missing: {relative}")
        if candidate.stat().st_size != entry.get("byteLength"):
            raise ValueError(f"Avatar output size changed: {relative}")
        if sha256_file(candidate) != entry.get("sha256"):
            raise ValueError(f"Avatar output hash changed: {relative}")
        declared_files.add(candidate.relative_to(root).as_posix())
        if role in IDENTITY_JSON_ROLES:
            document = require_object(
                json.loads(candidate.read_text(encoding="utf-8")),
                f"avatar output {role}",
            )
            validate_identity_document(role, document, identity, input_document)

    actual_files = {
        path.relative_to(root).as_posix()
        for path in root.rglob("*")
        if path.is_file()
    }
    if actual_files != declared_files:
        raise ValueError("The immutable avatar output file set changed.")
    manifest_identity = {
        "schemaVersion": manifest["schemaVersion"],
        "acceptanceScope": manifest["acceptanceScope"],
        "input": manifest["input"],
        "controlMap": manifest["controlMap"],
        "worker": manifest["worker"],
        "configuration": manifest["configuration"],
        "claims": manifest["claims"],
        "files": manifest["files"],
    }
    expected_output_id = sha256_bytes(canonical_json(manifest_identity))
    if manifest.get("outputId") != expected_output_id:
        raise ValueError("Avatar output identity does not match its manifest.")
    return manifest


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    create = commands.add_parser("create")
    create.add_argument("--recipe", required=True, type=Path)
    create.add_argument("--input", required=True, type=Path)
    create.add_argument("--output-directory", required=True, type=Path)
    verify = commands.add_parser("verify")
    verify.add_argument("--output", required=True, type=Path)
    verify.add_argument("--input", required=True, type=Path)
    return parser.parse_args()


def main() -> int:
    arguments = parse_arguments()
    if arguments.command == "create":
        result = create_output(
            arguments.recipe,
            arguments.input,
            arguments.output_directory,
        )
    else:
        result = verify_output(arguments.output, arguments.input)
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
