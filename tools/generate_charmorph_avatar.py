#!/usr/bin/env python3
"""Generate a female-specific Patterna avatar from CharMorph controls."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shutil
import sys

import bpy
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from charmorph_character import CharacterDescriptor, load_character
from charmorph_glb import export_glb_candidate
from charmorph_morphs import apply_controls, load_packed_morphs
from charmorph_profile_controls import resolve_fit_control_contract
from generate_mpfb_avatar import write_bra_shell_obj, write_solid_texture


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CHARACTER_DIR = REPO_ROOT / "third_party" / "CharMorph-db" / "characters" / "mb_female"
DEFAULT_PROFILE = REPO_ROOT / "PatternaUnreal" / "SourceAssets" / "Avatar" / "PatternaFullBustDefault.avatar-profile.json"

def blender_arguments() -> list[str]:
    return sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--character-dir", type=Path, default=DEFAULT_CHARACTER_DIR)
    parser.add_argument("--profile", type=Path, default=DEFAULT_PROFILE)
    parser.add_argument("--basis")
    parser.add_argument("--controls", type=Path)
    parser.add_argument(
        "--vertices",
        type=Path,
        help="Optional fitted vertex array produced by fit_charmorph_profile.py.",
    )
    parser.add_argument("--object")
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--render-output-dir", type=Path)
    parser.add_argument("--glb-output", type=Path)
    parser.add_argument("--glb-render-output-dir", type=Path)
    parser.add_argument("--fit-report", type=Path)
    parser.add_argument("--height-cm", type=float)
    return parser.parse_args(blender_arguments())


def resolve(path: Path) -> Path:
    return path.resolve() if path.is_absolute() else (REPO_ROOT / path).resolve()


def load_controls(path: Path | None, raw_morphs: dict[str, object]) -> dict[str, float]:
    controls = dict(resolve_fit_control_contract(raw_morphs).initial_controls)
    if path is not None:
        payload = json.loads(resolve(path).read_text(encoding="utf-8"))
        if payload.get("replaceDefaults", False):
            controls.clear()
        supplied = payload.get("controls", payload)
        if "replaceDefaults" in supplied:
            supplied = {name: value for name, value in supplied.items() if name != "replaceDefaults"}
        controls.update({name: float(value) for name, value in supplied.items()})
    invalid = {name: value for name, value in controls.items() if not -1.0 <= value <= 1.0}
    if invalid:
        raise ValueError(f"CharMorph controls must stay within -1..1: {invalid}")
    return controls


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def export_selected_obj(path: Path) -> None:
    bpy.ops.wm.obj_export(
        filepath=str(path),
        export_selected_objects=True,
        export_materials=False,
        forward_axis="NEGATIVE_Y",
        up_axis="Z",
        apply_modifiers=True,
    )


def obj_geometry_counts(path: Path) -> tuple[int, int, int]:
    vertex_count = 0
    face_count = 0
    uv_count = 0
    with path.open("r", encoding="utf-8") as source:
        for line in source:
            if line.startswith("v "):
                vertex_count += 1
            elif line.startswith("vt "):
                uv_count += 1
            elif line.startswith("f "):
                face_count += 1
    return vertex_count, face_count, uv_count


def build_display_avatar(
    body: bpy.types.Object,
    character: CharacterDescriptor,
    output_dir: Path,
    collision_path: Path,
) -> dict[str, object]:
    output_dir.mkdir(parents=True, exist_ok=True)
    bpy.ops.object.select_all(action="DESELECT")
    body.select_set(True)
    bpy.context.view_layer.objects.active = body
    display_body_path = output_dir / "body.obj"
    subdivision = body.modifiers.new(name="PatternaDisplaySubdivision", type="SUBSURF")
    subdivision.subdivision_type = "CATMULL_CLARK"
    subdivision.levels = 1
    subdivision.render_levels = 1
    try:
        export_selected_obj(display_body_path)
    finally:
        body.modifiers.remove(subdivision)
    display_body_counts = obj_geometry_counts(display_body_path)
    skin_texture = character.single_body_albedo
    if skin_texture is None:
        raise ValueError(
            f"{character.title} uses multiple body materials and requires the GLB display exporter"
        )
    shutil.copy2(skin_texture, output_dir / "body.png")

    body_group = body.vertex_groups.get("body") or body.vertex_groups.new(name="body")
    body_group.add(range(len(body.data.vertices)), 1.0, "REPLACE")
    coordinates = [vertex.co.copy() for vertex in body.data.vertices]
    bra_geometry = write_bra_shell_obj(
        body,
        output_dir / "bra.obj",
        coordinates,
        invert_output_y=True,
        surface_offset_m=0.0020,
        strap_offset_m=0.0022,
        maximum_torso_half_width_m=0.24,
    )
    write_solid_texture(output_dir / "bra.png", (0.035, 0.050, 0.075, 1.0))
    floor_offset_m = min(float(vertex.z) for vertex in coordinates)
    manifest = {
        "schema_version": "patterna.display-avatar/1.0",
        "source": character.title,
        "license": character.license_name,
        "floor_offset_m": floor_offset_m,
        "collision_geometry": f"../{collision_path.name}",
        "assets": {
            "body": {
                "geometry": "body.obj",
                "texture": "body.png",
                "color": [0.16, 0.09, 0.06],
                "vertex_count": display_body_counts[0],
                "face_count": display_body_counts[1],
                "uv_count": display_body_counts[2],
                "subdivision_level": 1,
            },
            "bra": {
                "geometry": "bra.obj",
                "texture": "bra.png",
                "color": [1.0, 1.0, 1.0],
                "vertex_count": bra_geometry[0],
                "face_count": bra_geometry[1],
                "uv_count": bra_geometry[2],
                "display_optional": True,
                "default_visible": False,
                "maximum_surface_offset_m": 0.0022,
            },
        },
    }
    (output_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n",
        encoding="utf-8",
    )
    return manifest


def main() -> None:
    args = parse_args()
    character_dir = resolve(args.character_dir)
    character = load_character(character_dir)
    profile_path = resolve(args.profile)
    if args.output_dir is None and args.output is None:
        raise ValueError("Either --output-dir or --output is required")
    output_path = resolve(args.output) if args.output else resolve(args.output_dir) / "body.obj"
    output_dir = resolve(args.output_dir) if args.output_dir else output_path.parent
    output_dir.mkdir(parents=True, exist_ok=True)

    object_name = args.object or character.object_name
    if object_name not in bpy.data.objects:
        raise RuntimeError(f"CharMorph source object {object_name!r} is not loaded")
    body = bpy.data.objects[object_name]
    if body.type != "MESH":
        raise RuntimeError(f"CharMorph source object {object_name!r} is not a mesh")

    basis_name = args.basis or character.basis_name
    basis_path = character_dir / "morphs" / "L1" / f"{basis_name}.npy"
    if not basis_path.is_file():
        raise FileNotFoundError(f"CharMorph basis not found: {basis_path}")
    pack_path = character.morph_pack_path
    basis = np.load(basis_path).astype(np.float64)
    if basis.shape != (len(body.data.vertices), 3):
        raise ValueError(f"Basis shape {basis.shape} does not match mesh vertex count {len(body.data.vertices)}")
    raw_morphs = load_packed_morphs(pack_path)
    controls = load_controls(args.controls, raw_morphs)
    vertices, weights = apply_controls(basis, raw_morphs, controls)

    profile = json.loads(profile_path.read_text(encoding="utf-8"))
    target_height_cm = float(args.height_cm or profile["measurements"]["height"])
    current_height_m = float(vertices[:, 2].max() - vertices[:, 2].min())
    height_scale = (target_height_cm / 100.0) / current_height_m
    basis_height_m = float(basis[:, 2].max() - basis[:, 2].min())
    uniform_asset_scale = (target_height_cm / 100.0) / basis_height_m
    if args.vertices is not None:
        fitted_vertices_path = resolve(args.vertices)
        vertices = np.load(fitted_vertices_path).astype(np.float64)
        if vertices.shape != basis.shape or not np.isfinite(vertices).all():
            raise ValueError("Fitted CharMorph vertex array is invalid")
        fitted_height_m = float(vertices[:, 2].max() - vertices[:, 2].min())
        if abs(fitted_height_m * 100.0 - target_height_cm) > 0.01:
            raise ValueError("Fitted CharMorph vertex height does not match the profile")
        height_scale = 1.0
    else:
        vertices *= height_scale
    body.data.vertices.foreach_set("co", vertices.reshape(-1))
    body.data.update()

    bpy.ops.object.select_all(action="DESELECT")
    body.select_set(True)
    bpy.context.view_layer.objects.active = body
    export_selected_obj(output_path)
    bpy.ops.wm.save_as_mainfile(filepath=str(output_dir / "avatar.blend"))

    fit_report = None
    fit_report_path = resolve(args.fit_report) if args.fit_report else None
    if fit_report_path is not None:
        fit_report = json.loads(fit_report_path.read_text(encoding="utf-8"))
        if not fit_report.get("accepted"):
            raise ValueError("CharMorph fit report is rejected")
        if fit_report.get("sourceProfileSha256") != sha256(profile_path):
            raise ValueError("CharMorph fit report does not match the avatar profile")
        if args.vertices is None:
            raise ValueError("Accepted CharMorph fit report requires fitted vertices")
        surface = fit_report.get("surfaceConstraint", {})
        if surface.get("verticesSha256") != sha256(resolve(args.vertices)):
            raise ValueError("CharMorph fit report does not match the fitted vertices")

    display_manifest = None
    if args.render_output_dir is not None:
        display_manifest = build_display_avatar(
            body,
            character,
            resolve(args.render_output_dir),
            output_path,
        )

    if args.glb_render_output_dir is not None and args.glb_output is None:
        raise ValueError("GLB render output requires --glb-output")
    glb_manifest = None
    if args.glb_output is not None:
        glb_manifest = export_glb_candidate(
            body,
            character,
            output_path,
            resolve(args.glb_output),
            resolve(args.glb_render_output_dir) if args.glb_render_output_dir else None,
            uniform_asset_scale,
            target_height_cm,
            fit_report,
            fit_report_path,
        )

    report = {
        "schemaVersion": "patterna.charmorph-avatar/1.0",
        "backend": character.title,
        "sourceLicense": character.license_name,
        "sourceLicenseFile": str(character.license_path),
        "sourceLicenseSha256": sha256(character.license_path),
        "sourceObject": object_name,
        "sourceBasis": str(basis_path),
        "sourceBasisName": basis_name,
        "sourcePack": str(pack_path),
        "sourcePackSha256": sha256(pack_path),
        "vertexCount": len(vertices),
        "outputBody": str(output_path),
        "outputBodySha256": sha256(output_path),
        "heightTargetCm": target_height_cm,
        "heightBeforeScaleCm": current_height_m * 100.0,
        "heightScale": height_scale,
        "fittedVertices": str(resolve(args.vertices)) if args.vertices else None,
        "controls": dict(sorted(controls.items())),
        "activeCornerWeights": dict(sorted(weights.items())),
        "profile": str(profile_path),
        "profileSha256": sha256(profile_path),
        "fitReport": str(fit_report_path) if fit_report_path else None,
        "fitReportSha256": sha256(fit_report_path) if fit_report_path else None,
        "displayManifest": display_manifest,
        "glbCandidateManifest": glb_manifest,
        "accepted": bool(fit_report and fit_report.get("accepted")),
        "anatomicalAcceptance": {
            "requiresDistinctBreastRoots": True,
            "requiresInframammaryFold": True,
            "requiresIndependentUpperArmControl": True,
            "status": "accepted-topology-pending-render-review" if fit_report else "pending-render-review",
        },
    }
    (output_dir / "avatar-report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
