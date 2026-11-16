#!/usr/bin/env python3
"""Create and verify immutable Patterna worker input bundles."""

from __future__ import annotations

import argparse
import hashlib
import json
import mimetypes
import os
from pathlib import Path
import shutil
import tempfile
from typing import Any


RECIPE_SCHEMA = "patterna.revision-bundle-recipe/1.2"
MANIFEST_SCHEMA = "patterna.revision-bundle/1.2"
PREVIOUS_MANIFEST_SCHEMA = "patterna.revision-bundle/1.1"
LEGACY_MANIFEST_SCHEMA = "patterna.revision-bundle/1.0"
REQUIRED_CONTRACT_FIELDS = {
    "garmentArchetype",
    "pose",
    "seed",
    "units",
    "supported3dControls",
}
SOURCE_INPUT_ROLES = {
    "sourceDocument",
    "bodyProfile",
    "fittedBodyState",
    "displayBody",
    "collider",
    "colliderReport",
    "panels",
    "panelMesh",
    "panelIndexMap",
    "seams",
    "materialCoordinates",
    "fabric",
    "pose",
}
PREVIOUS_INPUT_ROLES = SOURCE_INPUT_ROLES - {"panelIndexMap"}
LEGACY_INPUT_ROLES = PREVIOUS_INPUT_ROLES | {"arrangement"}


def canonical_json(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def require_plain_object(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict) or not value:
        raise ValueError(f"{label} must be a nonempty JSON object.")
    return value


def require_role_name(role: Any, category: str) -> str:
    if not isinstance(role, str) or not role or not role[0].isalpha():
        raise ValueError(f"Every {category} role must start with an ASCII letter.")
    if not all(character.isalnum() or character in {"-", "_"} for character in role):
        raise ValueError(f"Invalid {category} role: {role}")
    return role


def resolve_file(recipe_path: Path, raw_path: Any, label: str) -> Path:
    if not isinstance(raw_path, str) or not raw_path.strip():
        raise ValueError(f"{label} requires a nonempty path.")
    candidate = Path(raw_path)
    if not candidate.is_absolute():
        candidate = recipe_path.parent / candidate
    resolved = candidate.resolve(strict=True)
    if not resolved.is_file():
        raise ValueError(f"{label} is not a file: {resolved}")
    return resolved


def media_type(path: Path) -> str:
    guessed, _ = mimetypes.guess_type(path.name)
    return guessed or "application/octet-stream"


def validate_contract(value: Any) -> dict[str, Any]:
    contract = require_plain_object(value, "contract")
    missing = sorted(REQUIRED_CONTRACT_FIELDS - contract.keys())
    if missing:
        raise ValueError(f"Revision contract is missing fields: {', '.join(missing)}")
    if contract["units"] != "cm":
        raise ValueError("Revision bundle 1.0 requires centimeter units.")
    if not isinstance(contract["seed"], int) or isinstance(contract["seed"], bool):
        raise ValueError("Revision contract seed must be an integer.")
    controls = contract["supported3dControls"]
    if not isinstance(controls, list) or any(not isinstance(item, str) for item in controls):
        raise ValueError("supported3dControls must be a list of names.")
    if len(set(controls)) != len(controls):
        raise ValueError("supported3dControls cannot contain duplicates.")
    for field in ("garmentArchetype", "pose"):
        if not isinstance(contract[field], str) or not contract[field].strip():
            raise ValueError(f"Revision contract {field} must be nonempty.")
    return contract


def declared_entry(
    role: str,
    raw_entry: Any,
    recipe_path: Path,
    category: str,
) -> tuple[dict[str, Any], Path]:
    entry = require_plain_object(raw_entry, f"{category} {role}")
    source = resolve_file(recipe_path, entry.get("path"), f"{category} {role}")
    result: dict[str, Any] = {
        "role": role,
        "fileName": source.name,
        "byteLength": source.stat().st_size,
        "sha256": sha256_file(source),
        "mediaType": media_type(source),
    }
    version = entry.get("version")
    if version is not None:
        if not isinstance(version, str) or not version.strip():
            raise ValueError(f"{category} {role} version must be a nonempty string.")
        result["version"] = version
    return result, source


def build_manifest(recipe_path: Path) -> tuple[dict[str, Any], dict[str, Path]]:
    recipe = json.loads(recipe_path.read_text(encoding="utf-8"))
    if recipe.get("schemaVersion") != RECIPE_SCHEMA:
        raise ValueError(f"Recipe schema must be {RECIPE_SCHEMA}.")
    contract = validate_contract(recipe.get("contract"))
    claims = require_plain_object(recipe.get("claims"), "claims")
    if claims.get("accepted") is not False:
        raise ValueError(
            "Proof bundles must begin rejected. Acceptance belongs to a later signed review manifest."
        )

    raw_inputs = require_plain_object(recipe.get("inputs"), "inputs")
    missing_roles = sorted(SOURCE_INPUT_ROLES - raw_inputs.keys())
    extra_roles = sorted(raw_inputs.keys() - SOURCE_INPUT_ROLES)
    if missing_roles or extra_roles:
        details = []
        if missing_roles:
            details.append(f"missing {', '.join(missing_roles)}")
        if extra_roles:
            details.append(f"unknown {', '.join(extra_roles)}")
        raise ValueError("Revision input roles are invalid: " + "; ".join(details))

    sources: dict[str, Path] = {}
    inputs: list[dict[str, Any]] = []
    for raw_role, raw_entry in sorted(raw_inputs.items()):
        role = require_role_name(raw_role, "input")
        entry, source = declared_entry(role, raw_entry, recipe_path, "input")
        suffix = "".join(source.suffixes).lower()
        object_name = f"{entry['sha256']}{suffix}"
        entry["bundlePath"] = f"objects/{object_name}"
        inputs.append(entry)
        sources[entry["bundlePath"]] = source

    raw_tools = require_plain_object(recipe.get("tools"), "tools")
    tools: list[dict[str, Any]] = []
    for raw_role, raw_entry in sorted(raw_tools.items()):
        role = require_role_name(raw_role, "tool")
        entry, _ = declared_entry(role, raw_entry, recipe_path, "tool")
        tools.append(entry)

    identity = {
        "schemaVersion": MANIFEST_SCHEMA,
        "contract": contract,
        "claims": claims,
        "inputs": inputs,
        "tools": tools,
    }
    bundle_id = sha256_bytes(canonical_json(identity))
    manifest = {
        "schemaVersion": MANIFEST_SCHEMA,
        "bundleId": bundle_id,
        "contract": contract,
        "claims": claims,
        "inputs": inputs,
        "tools": tools,
    }
    return manifest, sources


def create_bundle(recipe_path: Path, output_directory: Path) -> dict[str, Any]:
    recipe_path = recipe_path.resolve(strict=True)
    output_directory = output_directory.resolve()
    if output_directory.exists():
        raise FileExistsError(
            f"Revision bundles are immutable; output already exists: {output_directory}"
        )
    output_directory.parent.mkdir(parents=True, exist_ok=True)
    manifest, sources = build_manifest(recipe_path)

    temporary = Path(
        tempfile.mkdtemp(prefix=f".{output_directory.name}-", dir=output_directory.parent)
    )
    try:
        for relative_path, source in sorted(sources.items()):
            destination = temporary / relative_path
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, destination)
        manifest_path = temporary / "revision-bundle.json"
        manifest_path.write_text(
            json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        verify_bundle(temporary)
        os.replace(temporary, output_directory)
    except BaseException:
        shutil.rmtree(temporary, ignore_errors=True)
        raise
    return manifest


def verify_bundle(bundle_directory: Path) -> dict[str, Any]:
    bundle_directory = bundle_directory.resolve(strict=True)
    manifest_path = bundle_directory / "revision-bundle.json"
    if not manifest_path.is_file():
        raise FileNotFoundError(f"Revision bundle manifest is missing: {manifest_path}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    schema = manifest.get("schemaVersion")
    if schema not in {
        MANIFEST_SCHEMA,
        PREVIOUS_MANIFEST_SCHEMA,
        LEGACY_MANIFEST_SCHEMA,
    }:
        raise ValueError(
            "Manifest schema must be "
            f"{MANIFEST_SCHEMA}, {PREVIOUS_MANIFEST_SCHEMA}, or {LEGACY_MANIFEST_SCHEMA}."
        )
    validate_contract(manifest.get("contract"))
    claims = require_plain_object(manifest.get("claims"), "claims")
    if claims.get("accepted") is not False:
        raise ValueError("A source revision bundle cannot claim acceptance.")
    inputs = manifest.get("inputs")
    tools = manifest.get("tools")
    if not isinstance(inputs, list) or not inputs:
        raise ValueError("Revision manifest inputs must be a nonempty list.")
    if not isinstance(tools, list) or not tools:
        raise ValueError("Revision manifest tools must be a nonempty list.")

    roles = {entry.get("role") for entry in inputs if isinstance(entry, dict)}
    expected_roles = {
        MANIFEST_SCHEMA: SOURCE_INPUT_ROLES,
        PREVIOUS_MANIFEST_SCHEMA: PREVIOUS_INPUT_ROLES,
        LEGACY_MANIFEST_SCHEMA: LEGACY_INPUT_ROLES,
    }[schema]
    if roles != expected_roles:
        raise ValueError(f"Revision manifest input roles do not match the {schema} contract.")

    declared_files = {"revision-bundle.json"}
    for entry in inputs:
        relative = entry.get("bundlePath")
        if not isinstance(relative, str) or Path(relative).is_absolute():
            raise ValueError("Every bundle input requires a relative bundlePath.")
        candidate = (bundle_directory / relative).resolve(strict=True)
        try:
            candidate.relative_to(bundle_directory)
        except ValueError as error:
            raise ValueError(f"Bundle input escapes the bundle directory: {relative}") from error
        if not candidate.is_file():
            raise ValueError(f"Bundle input is not a file: {relative}")
        if candidate.stat().st_size != entry.get("byteLength"):
            raise ValueError(f"Bundle input size changed: {relative}")
        if sha256_file(candidate) != entry.get("sha256"):
            raise ValueError(f"Bundle input hash changed: {relative}")
        declared_files.add(candidate.relative_to(bundle_directory).as_posix())

    actual_files = {
        path.relative_to(bundle_directory).as_posix()
        for path in bundle_directory.rglob("*")
        if path.is_file()
    }
    extras = sorted(actual_files - declared_files)
    missing = sorted(declared_files - actual_files)
    if extras or missing:
        raise ValueError(
            f"Bundle file set changed; extras={extras or []}, missing={missing or []}."
        )

    identity = {
        "schemaVersion": manifest["schemaVersion"],
        "contract": manifest["contract"],
        "claims": claims,
        "inputs": inputs,
        "tools": tools,
    }
    expected_id = sha256_bytes(canonical_json(identity))
    if manifest.get("bundleId") != expected_id:
        raise ValueError("Revision bundle identity does not match its manifest.")
    return manifest


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    create = subparsers.add_parser("create", help="Create one new immutable bundle.")
    create.add_argument("--recipe", required=True, type=Path)
    create.add_argument("--output-directory", required=True, type=Path)
    verify = subparsers.add_parser("verify", help="Verify a closed bundle and all hashes.")
    verify.add_argument("--bundle", required=True, type=Path)
    return parser.parse_args()


def main() -> int:
    arguments = parse_arguments()
    if arguments.command == "create":
        manifest = create_bundle(arguments.recipe, arguments.output_directory)
    else:
        manifest = verify_bundle(arguments.bundle)
    print(
        json.dumps(
            {
                "bundleId": manifest["bundleId"],
                "accepted": manifest["claims"]["accepted"],
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
