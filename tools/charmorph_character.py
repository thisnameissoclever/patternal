#!/usr/bin/env python3
"""Resolve a CharMorph character's geometry, morph, texture, and license contract."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class CharacterDescriptor:
    directory: Path
    title: str
    author: str
    additional_authors: str
    source_url: str
    object_name: str
    basis_name: str
    license_name: str
    license_path: Path
    blend_path: Path
    basis_path: Path
    faces_path: Path
    morph_pack_path: Path
    material_names: tuple[str, ...]
    underwear_names: tuple[str, ...]
    albedo_paths: tuple[Path, ...]
    texture_paths: tuple[Path, ...]

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


def _optional_text(config: dict[str, object], name: str) -> str:
    value = config.get(name)
    return value.strip() if isinstance(value, str) else ""


def _text_list(config: dict[str, object], name: str, config_path: Path) -> tuple[str, ...]:
    value = config.get(name, [])
    if not isinstance(value, list) or not all(isinstance(item, str) and item.strip() for item in value):
        raise ValueError(f"CharMorph config {config_path} must declare {name} as text values")
    return tuple(item.strip() for item in value)


def _top_level_config(config_path: Path) -> dict[str, object]:
    """Read the scalar and simple-list subset shared by CharMorph character configs."""
    payload: dict[str, object] = {}
    current_list: str | None = None
    for line_number, raw_line in enumerate(
        config_path.read_text(encoding="utf-8").splitlines(),
        start=1,
    ):
        stripped = raw_line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        indentation = len(raw_line) - len(raw_line.lstrip())
        if indentation == 0:
            current_list = None
            if ":" not in stripped:
                raise ValueError(f"CharMorph config {config_path}:{line_number} is malformed")
            key, value = stripped.split(":", 1)
            key = key.strip()
            value = value.strip()
            if not key:
                raise ValueError(f"CharMorph config {config_path}:{line_number} has an empty key")
            if value:
                payload[key] = value.strip("'\"")
            else:
                payload[key] = []
                current_list = key
            continue
        if indentation == 2 and current_list and stripped.startswith("- "):
            item = stripped[2:].strip().strip("'\"")
            if not item:
                raise ValueError(f"CharMorph config {config_path}:{line_number} has an empty list item")
            value = payload[current_list]
            if not isinstance(value, list):
                raise ValueError(f"CharMorph config {config_path}:{line_number} has an invalid list")
            value.append(item)
    return payload


def load_character(character_directory: Path) -> CharacterDescriptor:
    directory = character_directory.resolve()
    config_path = directory / "config.yaml"
    license_path = directory / "license.txt"
    if not config_path.is_file():
        raise FileNotFoundError(f"CharMorph character config not found: {config_path}")
    if not license_path.is_file():
        raise FileNotFoundError(f"CharMorph character license not found: {license_path}")

    payload = _top_level_config(config_path)
    title = _required_text(payload, "title", config_path)
    author = _optional_text(payload, "author")
    additional_authors = _optional_text(payload, "additional_authors")
    source_url = _optional_text(payload, "url")
    object_name = _required_text(payload, "char_obj", config_path)
    basis_name = _required_text(payload, "basis", config_path)
    license_name = _required_text(payload, "license", config_path)
    material_names = _text_list(payload, "materials", config_path)
    underwear_names = _text_list(payload, "underwear", config_path)
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
    texture_paths = tuple(
        sorted(
            (path for path in textures_directory.rglob("*") if path.is_file()),
            key=lambda path: str(path).lower(),
        )
    )
    albedo_paths = tuple(
        path
        for path in texture_paths
        if path.name.lower() == "albedo.png"
        or "albedo" in path.stem.lower()
        or "basecolor" in path.stem.lower()
    )
    if not albedo_paths:
        raise FileNotFoundError(f"CharMorph character has no albedo textures: {directory}")

    return CharacterDescriptor(
        directory=directory,
        title=title,
        author=author,
        additional_authors=additional_authors,
        source_url=source_url,
        object_name=object_name,
        basis_name=basis_name,
        license_name=license_name,
        license_path=license_path,
        blend_path=blend_path,
        basis_path=basis_path,
        faces_path=faces_path,
        morph_pack_path=morph_pack_path,
        material_names=material_names,
        underwear_names=underwear_names,
        albedo_paths=albedo_paths,
        texture_paths=texture_paths,
    )
