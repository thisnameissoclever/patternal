#!/usr/bin/env python3
"""Verify the exact Anny release wheel before installation or execution."""

from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
from email import policy
from email.parser import BytesParser
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import stat
from typing import Any
import zipfile


EXPECTED_CORE_DEPENDENCIES = frozenset(
    {
        "numpy",
        "pillow",
        "pyyaml",
        "requests",
        "roma",
        "safetensors",
        "torch",
        "trimesh",
        "warp-lang",
    }
)
REQUIRED_DATA_PATHS = frozenset(
    {
        "anny/data/cached/anny.pth",
        "anny/data/mpfb2/3dobjs/base.obj",
        "anny/data/mpfb2/LICENSE.md",
    }
)


@dataclass(frozen=True)
class ReleaseArtifact:
    filename: str
    version: str
    byte_length: int
    sha256: str
    data_file_count: int
    data_uncompressed_bytes: int


ANNY_RELEASE = ReleaseArtifact(
    filename="anny-0.6.0-py3-none-any.whl",
    version="0.6.0",
    byte_length=47_705_473,
    sha256="050a0b24a3e7fdb89b46dc3581947ea84225305425ac9a1a97b65ea997fb2ad6",
    data_file_count=1_559,
    data_uncompressed_bytes=107_825_068,
)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def validate_archive_name(raw_name: str) -> PurePosixPath:
    if not raw_name or "\\" in raw_name:
        raise ValueError(f"Unsafe wheel archive path: {raw_name!r}")
    path = PurePosixPath(raw_name)
    if path.is_absolute() or ".." in path.parts:
        raise ValueError(f"Unsafe wheel archive path: {raw_name!r}")
    return path


def dependency_name(requirement: str) -> str:
    match = re.match(r"^[A-Za-z0-9_.-]+", requirement)
    if match is None:
        raise ValueError(f"Cannot parse wheel dependency: {requirement}")
    return match.group(0).lower().replace("_", "-")


def inspect_wheel(path: Path) -> dict[str, Any]:
    path = path.resolve(strict=True)
    if not path.is_file():
        raise ValueError(f"Anny artifact is not a file: {path}")

    with zipfile.ZipFile(path, "r") as archive:
        entries = archive.infolist()
        names = [entry.filename for entry in entries]
        if len(names) != len(set(names)):
            raise ValueError("The Anny wheel contains duplicate archive paths.")
        for entry in entries:
            validate_archive_name(entry.filename)
            unix_mode = entry.external_attr >> 16
            if unix_mode and stat.S_ISLNK(unix_mode):
                raise ValueError(f"The Anny wheel contains a symlink: {entry.filename}")

        metadata_paths = [name for name in names if name.endswith(".dist-info/METADATA")]
        if len(metadata_paths) != 1:
            raise ValueError("The Anny wheel must contain exactly one METADATA file.")
        metadata = BytesParser(policy=policy.default).parsebytes(
            archive.read(metadata_paths[0])
        )
        base_requirements = [
            requirement
            for requirement in metadata.get_all("Requires-Dist", [])
            if "extra ==" not in requirement
        ]
        core_dependencies = sorted(dependency_name(item) for item in base_requirements)

        data_entries = [
            entry
            for entry in entries
            if entry.filename.startswith("anny/data/") and not entry.is_dir()
        ]
        license_paths = sorted(name for name in names if "license" in name.lower())
        root_license_paths = [
            name for name in license_paths if name.endswith(".dist-info/licenses/LICENSE")
        ]
        if len(root_license_paths) != 1:
            raise ValueError("The Anny wheel must contain one embedded code license.")

        code_license = archive.read(root_license_paths[0]).decode(
            encoding="utf-8", errors="strict"
        )
        mpfb_license = archive.read("anny/data/mpfb2/LICENSE.md").decode(
            encoding="utf-8", errors="strict"
        )

    return {
        "filename": path.name,
        "byteLength": path.stat().st_size,
        "sha256": sha256_file(path),
        "archiveFileCount": len(entries),
        "projectName": metadata.get("Name"),
        "version": metadata.get("Version"),
        "coreDependencies": core_dependencies,
        "dataFileCount": len(data_entries),
        "dataUncompressedBytes": sum(entry.file_size for entry in data_entries),
        "requiredDataPathsPresent": sorted(REQUIRED_DATA_PATHS.intersection(names)),
        "licensePaths": license_paths,
        "codeLicenseApache20": "Apache License" in code_license
        and "Version 2.0" in code_license,
        "mpfbLicenseCc0": "Creative Commons CC0 1.0 Universal" in mpfb_license,
    }


def verify_wheel(
    path: Path,
    expected: ReleaseArtifact = ANNY_RELEASE,
) -> dict[str, Any]:
    inventory = inspect_wheel(path)
    exact_fields = {
        "filename": expected.filename,
        "byteLength": expected.byte_length,
        "sha256": expected.sha256,
        "version": expected.version,
        "dataFileCount": expected.data_file_count,
        "dataUncompressedBytes": expected.data_uncompressed_bytes,
    }
    for field, expected_value in exact_fields.items():
        if inventory[field] != expected_value:
            raise ValueError(
                f"Anny wheel {field} differs: expected {expected_value!r}, "
                f"received {inventory[field]!r}."
            )
    if inventory["projectName"] != "anny":
        raise ValueError("The wheel project name is not anny.")
    if frozenset(inventory["coreDependencies"]) != EXPECTED_CORE_DEPENDENCIES:
        raise ValueError("The Anny core dependency set differs from the reviewed release.")
    if set(inventory["requiredDataPathsPresent"]) != REQUIRED_DATA_PATHS:
        raise ValueError("The Anny wheel is missing required native model data.")
    if inventory["codeLicenseApache20"] is not True:
        raise ValueError("The Anny wheel does not carry the reviewed Apache-2.0 license.")
    if inventory["mpfbLicenseCc0"] is not True:
        raise ValueError("The Anny wheel does not carry the reviewed MPFB2 CC0 license.")
    return {
        "schemaVersion": "patterna.anny-release-verification/1.0",
        "accepted": True,
        "scope": "release-artifact-integrity-only",
        "executionAuthorized": False,
        "avatarAccepted": False,
        "expected": asdict(expected),
        "inventory": inventory,
    }


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--wheel", required=True, type=Path)
    return parser.parse_args()


def main() -> int:
    result = verify_wheel(parse_arguments().wheel)
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
