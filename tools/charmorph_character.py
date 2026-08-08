#!/usr/bin/env python3
"""Resolve a CharMorph character's geometry, morph, texture, and license contract."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml


@dataclass(frozen=True)
class CharacterDescriptor:
    directory: Path
    title: str
    object_name: str
    basis_name: str
    license_name: str
    license_path: Path
    blend_path: Path
    basis_path: Path
    faces_path: Path
    morph_pack_path: Path
    albedo_paths: tuple[Path, ...]

    @property
    def single_body_albedo(self) -> Path | None:
        if len(self.albedo_paths) == 1 and self.albedo_paths[0].name.lower() == "albedo.png":
            return self.albedo_paths[0]
        return None


def _required_text(config: dict[str, object], name: str, config_path: Path) -> str:
    value = config.get(name)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"CharMorph config {config_path} must declare {name}")
    return value.strip()


def load_character(character_directory: Path) -> CharacterDescriptor:
    directory = character_directory.resolve()
    config_path = directory / "config.yaml"
    license_path = directory / "license.txt"
    if not config_path.is_file():
        raise FileNotFoundError(f"CharMorph character config not found: {config_path}")
    if not license_path.is_file():
        raise FileNotFoundError(f"CharMorph character license not found: {license_path}")

    payload = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"CharMorph config must contain an object: {config_path}")
    title = _required_text(payload, "title", config_path)
    object_name = _required_text(payload, "char_obj", config_path)
    basis_name = _required_text(payload, "basis", config_path)
    license_name = _required_text(payload, "license", config_path)
    blend_path = directory / str(payload.get("char_file", "char.blend"))
    basis_path = directory / "morphs" / "L1" / f"{basis_name}.npy"
    faces_path = directory / "faces.npy"
    packed_candidates = (
        directory / "morphs" / "L2_packed" / "__main__.npz",
        directory / "morphs" / "L2.npz",
    )
    morph_pack_path = next((path for path in packed_candidates if path.is_file()), None)
    required_paths = (blend_path, basis_path, faces_path)
    missing = next((path for path in required_paths if not path.is_file()), None)
    if missing is not None:
        raise FileNotFoundError(f"CharMorph character input not found: {missing}")
    if morph_pack_path is None:
        raise FileNotFoundError(
            f"CharMorph character has no supported packed morph file: {directory}"
        )

    textures_directory = directory / "textures"
    albedo_paths = tuple(
        sorted(
            (
                path
                for path in textures_directory.rglob("*")
                if path.is_file()
                and (
                    path.name.lower() == "albedo.png"
                    or "albedo" in path.stem.lower()
                    or "basecolor" in path.stem.lower()
                )
            ),
            key=lambda path: str(path).lower(),
        )
    )
    if not albedo_paths:
        raise FileNotFoundError(f"CharMorph character has no albedo textures: {directory}")

    return CharacterDescriptor(
        directory=directory,
        title=title,
        object_name=object_name,
        basis_name=basis_name,
        license_name=license_name,
        license_path=license_path,
        blend_path=blend_path,
        basis_path=basis_path,
        faces_path=faces_path,
        morph_pack_path=morph_pack_path,
        albedo_paths=albedo_paths,
    )
