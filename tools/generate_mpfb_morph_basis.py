#!/usr/bin/env python3
"""Build a real-time morph basis for the packaged MPFB display body.

The interactive preview deforms its body by blending endpoint meshes: for each
controllable measurement it stores the body at that measurement's minimum and
at its maximum, and interpolates between one of those and the baseline. The
basis shipped today was built from the MHR body by `generate_mhr_morph_basis`,
whose fitter moves horizontal torso cross-sections and so can only express
torso girths and depths. It reaches 13 of the 151 dimensions the application
lets a user edit.

This builds the same kind of basis from MPFB, whose Patterna control layer in
`mpfb_morph_controls` maps 85 controls onto named MakeHuman targets covering
the legs, feet, hands, head and posture curves as well as the torso.

Each endpoint is produced by moving one control to its limit and reading how far
the body moved. By default that reading is the MPFB target contribution alone,
because those offsets are additive and so the displacement belongs to the
control rather than to the body it was measured on, which is what allows the
basis to be applied to a body this tool did not build. That independence is not
assumed: every run measures one control before and after the ruler fit, across
several centimetres of body change, and refuses to write if the two disagree by
more than the declared tolerance. The measured coupling is recorded in the
report.

`--full-response-deltas` measures the application's whole response instead,
local deformations and surface constraints included. Those deltas describe more,
and are only valid against the exact body they were measured on.

The ruler fit is run once for the baseline and then held fixed, because
refitting per endpoint would chase the target measurements back and cancel the
control being measured.

Deltas are stored sparsely. A palm width moves a few hundred vertices out of
13380, and storing every vertex for all 170 endpoints would cost about 30 MB to
say almost nothing.

Run inside Blender, without `--factory-startup`, which would disable the MPFB
extension this depends on:

    blender --background \
        --python tools/generate_mpfb_morph_basis.py -- \
        --output-directory artifacts/mpfb-morph-basis-v1

This writes a candidate basis and its report. It accepts nothing.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib
import json
from pathlib import Path
import struct
import sys
from typing import Any

import bpy
import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "tools"))

import generate_mpfb_avatar as avatar  # noqa: E402
from mpfb_morph_controls import (  # noqa: E402
    FEMALE_GENDER_MACRO,
    MORPH_CONTROL_SPECS,
    _average_available,
    macro_controls,
)

SCHEMA_VERSION = "patterna.mpfb-morph-basis/1.0"
MPFB_MODULE_NAME = "bl_ext.user_default.mpfb"


def blender_arguments() -> list[str]:
    return sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--profile",
        type=Path,
        default=REPO_ROOT
        / "PatternaUnreal/SourceAssets/GarmentCode/PatternaDefaultFemale.body.json",
    )
    parser.add_argument(
        "--output-directory",
        type=Path,
        default=REPO_ROOT / "artifacts/mpfb-morph-basis-v1",
    )
    # Below this a vertex has not meaningfully moved, and keeping it costs
    # twelve bytes to record a rounding difference.
    parser.add_argument("--minimum-displacement-m", type=float, default=0.00002)
    # How far a control's own displacement may drift as the body changes under
    # it, before these deltas stop being safe to apply to a different body.
    parser.add_argument("--maximum-body-coupling-m", type=float, default=0.001)
    parser.add_argument(
        "--full-response-deltas",
        action="store_true",
        help=(
            "Measure the application's whole response, local deformations and "
            "surface constraints included, instead of the MPFB target "
            "contribution alone. Those deltas are only valid against the exact "
            "body they were measured on."
        ),
    )
    parser.add_argument(
        "--baseline-body-only",
        action="store_true",
        help="Write the baseline body and stop, to compare it against the packaged one.",
    )
    parser.add_argument("--fit-passes", type=int, default=30)
    parser.add_argument("--tolerance-cm", type=float, default=0.15)
    parser.add_argument("--max-target-weight", type=float, default=2.0)
    return parser.parse_args(blender_arguments())


def bind_mpfb_services() -> None:
    """Give the shared avatar module the MPFB services its functions expect."""
    if MPFB_MODULE_NAME not in bpy.context.preferences.addons:
        raise RuntimeError(
            "MPFB is not enabled in Blender's user_default extension repository."
        )
    avatar.HumanObjectProperties = importlib.import_module(
        f"{MPFB_MODULE_NAME}.entities.objectproperties"
    ).HumanObjectProperties
    avatar.HumanService = importlib.import_module(
        f"{MPFB_MODULE_NAME}.services.humanservice"
    ).HumanService
    avatar.TargetService = importlib.import_module(
        f"{MPFB_MODULE_NAME}.services.targetservice"
    ).TargetService


def body_vertex_order(basemesh: bpy.types.Object) -> list[int]:
    """The basemesh vertex indices in the order the display body writes them.

    `write_textured_body_obj` emits the vertices of every polygon whose corners
    all carry body weight, sorted by index. A delta array is only meaningful
    against that same order.
    """
    body_group = basemesh.vertex_groups.get("body")
    if body_group is None:
        raise RuntimeError("MPFB basemesh has no body vertex group.")
    index = body_group.index
    body_vertices = {
        vertex.index
        for vertex in basemesh.data.vertices
        if any(group.group == index and group.weight > 0.0 for group in vertex.groups)
    }
    polygons = [
        polygon
        for polygon in basemesh.data.polygons
        if all(corner in body_vertices for corner in polygon.vertices)
    ]
    return sorted({corner for polygon in polygons for corner in polygon.vertices})


def clear_control_targets(basemesh: bpy.types.Object, spec: Any) -> None:
    """Return one control's MPFB targets to rest.

    `evaluate_morph_controls` skips a control whose source measurements are
    absent from the profile, which means it also never writes their targets
    back. Probing such a control leaves its weight standing, and the next
    probe measures that as well as its own, so the deltas accumulate down the
    whole run. Anything the profile does drive is rewritten by the next
    `apply_detail_morph_controls`, so clearing to rest is safe for both kinds.
    """
    for decreasing, increasing in spec.target_pairs:
        for name in (decreasing, increasing):
            if avatar.TargetService.has_target(basemesh, name):
                avatar.TargetService.set_target_value(basemesh, name, 0.0)


def baseline_value(spec: Any, profile: dict[str, float]) -> float:
    """What a control reads on the body its deltas were measured against.

    `evaluate_morph_controls` drives each control from the mean of whichever of
    its source measurements the profile carries, so that mean is the value at
    which this control contributes nothing. A control the profile does not
    mention was never applied, and rests at its own default.
    """
    measured = _average_available(profile, spec.source_keys)
    value = spec.default if measured is None else measured
    if not spec.minimum <= value <= spec.maximum:
        raise SystemExit(
            f"{spec.name} rests at {value}, outside its own range "
            f"[{spec.minimum}, {spec.maximum}]. The preview would extrapolate "
            "past the endpoint it was measured at."
        )
    return value


def control_displacement(
    basemesh: bpy.types.Object,
    profile: dict[str, float],
    order: list[int],
    spec: Any,
    *,
    pure_targets: bool,
) -> np.ndarray:
    """How far one control at its maximum moves each vertex."""
    rest = coordinates_for(basemesh, profile, order, pure_targets=pure_targets)
    probe = dict(profile)
    for key in spec.source_keys:
        probe[key] = float(spec.maximum)
    moved = coordinates_for(basemesh, probe, order, pure_targets=pure_targets)
    clear_control_targets(basemesh, spec)
    avatar.apply_detail_morph_controls(basemesh, profile)
    return moved - rest


def coordinates_for(
    basemesh: bpy.types.Object,
    profile: dict[str, float],
    order: list[int],
    *,
    pure_targets: bool,
) -> np.ndarray:
    """The display body's vertices for one profile, in display order.

    With `pure_targets`, this reads the mesh MPFB itself evaluates and stops
    there. MPFB targets are additive vertex offsets, so the difference between
    two of those readings is the contribution of the targets that changed and
    nothing else, which makes it a property of the control rather than of the
    body it was measured on. That difference can then be applied to any body
    with the same topology.

    Without it, the reading also carries the local deformations and surface
    constraints the application applies on top, which depend on the positions
    they start from. Those deltas describe the application's full response, and
    they are only valid against the exact body they were measured on.
    """
    avatar.apply_detail_morph_controls(basemesh, profile)
    if pure_targets:
        coordinates = avatar.mixed_world_coordinates(basemesh)
    else:
        coordinates, _ = avatar.deformed_world_coordinates(basemesh, profile)
    return np.array(
        [(coordinates[i].x, coordinates[i].y, coordinates[i].z) for i in order],
        dtype=np.float64,
    )


def main() -> int:
    arguments = parse_args()
    output_directory = arguments.output_directory
    output_directory.mkdir(parents=True, exist_ok=True)

    pure_targets = not arguments.full_response_deltas
    internal, user, _, _ = avatar.profile_sections(arguments.profile)
    profile: dict[str, float] = dict(internal)
    profile.update(user)

    bind_mpfb_services()
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)

    macro = avatar.TargetService.get_default_macro_info_dict()
    macro["gender"] = FEMALE_GENDER_MACRO
    macro.update(macro_controls(profile))
    basemesh = avatar.HumanService.create_human(
        mask_helpers=False,
        detailed_helpers=True,
        extra_vertex_groups=True,
        feet_on_ground=True,
        scale=0.1,
        macro_detail_dict=macro,
    )
    basemesh.name = "PatternaMorphBasisAvatar"
    height_result = None
    if "height" in profile:
        height_result = avatar.set_height(
            basemesh, profile["height"], arguments.tolerance_cm
        )

    # A control's displacement measured before the ruler fit, to be compared
    # against the same control after it. The two bodies differ by several
    # centimetres, so agreement is evidence that the deltas belong to the
    # control rather than to the body, which is what lets them be applied to a
    # body this tool did not build.
    probe_order = body_vertex_order(basemesh)
    unfitted_delta = None
    coupling_measurement = None
    coupling_body_movement = None
    if pure_targets:
        unfitted_delta = control_displacement(
            basemesh, profile, probe_order, MORPH_CONTROL_SPECS[0], pure_targets=True
        )
        unfitted_body = coordinates_for(
            basemesh, profile, probe_order, pure_targets=True
        )

    # The whole fit, through the shared function, rather than the first half of
    # it written out again here. An earlier version of this tool ran only the
    # ruler passes and produced a baseline body 4.7 cm taller than the profile
    # asked for, because the compensation for local deformations lives at the
    # end of that sequence.
    #
    # One fit, held fixed from here. Refitting per endpoint would pull each
    # measurement back to its target and erase the control being measured.
    avatar.fit_basemesh_to_profile(
        basemesh,
        profile,
        height_result,
        max_target_weight=arguments.max_target_weight,
        fit_passes=arguments.fit_passes,
        tolerance_cm=arguments.tolerance_cm,
    )
    print("baseline ruler fit complete", flush=True)

    order = body_vertex_order(basemesh)
    baseline = coordinates_for(basemesh, profile, order, pure_targets=pure_targets)
    print(f"display body vertices: {len(order)}", flush=True)

    if unfitted_delta is not None:
        fitted_delta = control_displacement(
            basemesh, profile, order, MORPH_CONTROL_SPECS[0], pure_targets=True
        )
        moved = float(np.linalg.norm(baseline - unfitted_body, axis=1).max())
        disagreement = float(np.abs(fitted_delta - unfitted_delta).max())
        print(
            f"body moved between the two measurements: {moved * 100:.3f} cm",
            flush=True,
        )
        print(
            f"same control's displacement disagreed by: {disagreement * 100:.9f} cm",
            flush=True,
        )
        if moved < 0.005:
            raise SystemExit(
                "The body barely moved between the two measurements, so this "
                "proves nothing about whether the deltas depend on it."
            )
        # Not zero. MPFB target offsets are additive, but some of them are
        # scaled by the macro state, so a control's displacement does drift a
        # little as the body changes underneath it. What matters is the size of
        # that drift relative to the measurements the preview is drawing: 0.06 cm
        # of drift across 8.4 cm of body is a coupling under one percent, so
        # carrying these deltas onto a body a few centimetres away costs well
        # under a millimetre. That is far below the displacement floor at which
        # this basis bothers to record a vertex at all, and this is a preview
        # that already declares itself approximate.
        coupling_measurement = disagreement
        coupling_body_movement = moved
        print(
            f"coupling to the body: {disagreement / moved * 100:.3f}% of its movement",
            flush=True,
        )
        if disagreement > arguments.maximum_body_coupling_m:
            raise SystemExit(
                f"The same control displaced the body differently before and "
                f"after the fit, by {disagreement * 100:.4f} cm across "
                f"{moved * 100:.3f} cm of body change. That is over the "
                f"{arguments.maximum_body_coupling_m * 100:.4f} cm this tool "
                "will carry onto a body it did not measure."
            )

    # The deltas are differences from this body, and they will be applied to
    # whichever body is packaged. Writing it out lets the packaging step check
    # that those are the same body rather than assume it.
    coordinates, _ = avatar.deformed_world_coordinates(basemesh, profile)
    avatar.write_textured_body_obj(
        basemesh, output_directory / "baseline-body.obj", coordinates
    )
    if arguments.baseline_body_only:
        print("baseline body written; stopping before the probes")
        return 0

    index_blocks: list[bytes] = []
    delta_blocks: list[bytes] = []
    byte_offset = 0
    parameters: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []

    for position, spec in enumerate(MORPH_CONTROL_SPECS, start=1):
        endpoints: dict[str, Any] = {}
        moved_any = False
        largest = 0.0
        for label, value in (("minimum", spec.minimum), ("maximum", spec.maximum)):
            probe = dict(profile)
            for key in spec.source_keys:
                probe[key] = float(value)
            displaced = coordinates_for(basemesh, probe, order, pure_targets=pure_targets) - baseline
            magnitude = np.linalg.norm(displaced, axis=1)
            moved = np.flatnonzero(magnitude >= arguments.minimum_displacement_m)
            largest = max(largest, float(magnitude.max()) if magnitude.size else 0.0)
            if moved.size:
                moved_any = True
            indices = moved.astype("<u4")
            deltas = displaced[moved].astype("<f4")
            endpoints[label] = {
                "count": int(moved.size),
                "indexByteOffset": byte_offset,
                "deltaByteOffset": byte_offset + indices.nbytes,
                "maximumDisplacementM": float(magnitude.max()) if magnitude.size else 0.0,
            }
            index_blocks.append(indices.tobytes())
            delta_blocks.append(deltas.tobytes())
            byte_offset += indices.nbytes + deltas.nbytes

        clear_control_targets(basemesh, spec)

        record = {
            "avatarKey": spec.name,
            "avatarSourceKeys": list(spec.source_keys),
            # A control fed by both sides of the body, or by two names for the
            # same span, is driven by their mean, which is how
            # `evaluate_morph_controls` reads them here.
            "aggregation": "mean" if len(spec.source_keys) > 1 else "first",
            "minimum": float(spec.minimum),
            # The value this control holds on the body the deltas were measured
            # against, which is the body built from the application's default
            # profile. It is not the control's own default: 29 of these specs
            # were authored around the MakeHuman baseline body and disagree
            # with what the application ships as the default measurement, one
            # of them by 50 units. Recording the spec default here told the
            # preview it was already far from rest, so it deformed the body
            # before the user touched anything and pushed the bust through the
            # packaged shirt.
            "baseline": float(baseline_value(spec, profile)),
            "maximum": float(spec.maximum),
            "endpoints": endpoints,
        }
        if moved_any:
            parameters.append(record)
        else:
            # A control whose limits move nothing cannot be previewed, and
            # shipping it would claim a capability that is not there.
            skipped.append(
                {
                    "avatarKey": spec.name,
                    "avatarSourceKeys": list(spec.source_keys),
                    "maximumDisplacementM": largest,
                }
            )
        print(
            f"  [{position}/{len(MORPH_CONTROL_SPECS)}] {spec.name} "
            f"moved {'yes' if moved_any else 'NO'} "
            f"max {largest * 100:.3f} cm",
            flush=True,
        )

    # Every probe must leave the body exactly as it found it. When it does not,
    # each delta carries the leftovers of the probes before it and the basis is
    # silently wrong rather than obviously broken, which is what happened on the
    # first run of this tool.
    returned = coordinates_for(basemesh, profile, order, pure_targets=pure_targets)
    drift = float(np.abs(returned - baseline).max())
    print(f"baseline drift after all probes: {drift * 100:.6f} cm", flush=True)
    if drift > arguments.minimum_displacement_m:
        raise SystemExit(
            f"The body did not return to its baseline between probes: {drift * 100:.4f} cm. "
            "The deltas would carry each other's effects, so nothing was written."
        )

    payload = bytearray()
    for indices, deltas in zip(index_blocks, delta_blocks):
        payload.extend(indices)
        payload.extend(deltas)
    basis_path = output_directory / "mpfb-morphs.bin"
    basis_path.write_bytes(bytes(payload))
    digest = hashlib.sha256(bytes(payload)).hexdigest()

    represented = sorted({key for item in parameters for key in item["avatarSourceKeys"]})
    report = {
        "schemaVersion": SCHEMA_VERSION,
        "accepted": False,
        "previewOnly": True,
        "deltaKind": "mpfb-target-offsets" if pure_targets else "application-response",
        "bodyIndependent": pure_targets,
        "bodyCouplingM": coupling_measurement,
        "bodyMovedBetweenMeasurementsM": coupling_body_movement,
        "validationScope": (
            "independent endpoint interpolation for declared measurements only; "
            "compound behaviour is unproven"
        ),
        "source": "MakeHuman Community system assets via MPFB",
        "license": "CC0",
        "file": basis_path.name,
        "bytes": len(payload),
        "sha256": digest,
        "encoding": (
            "per endpoint: little-endian uint32 source vertex indices followed by "
            "little-endian float32 xyz deltas in Blender metres"
        ),
        "sourceVertexCount": len(order),
        "baselineHeightCm": float(profile.get("height", 167.0)),
        "minimumDisplacementM": arguments.minimum_displacement_m,
        "parameters": parameters,
        "parametersWithNoEffect": skipped,
        "representedMeasurementKeys": represented,
        "summary": {
            "controlsDeclared": len(MORPH_CONTROL_SPECS),
            "controlsWithMovement": len(parameters),
            "measurementKeysRepresented": len(represented),
            "basisMegabytes": round(len(payload) / (1024 * 1024), 3),
        },
    }
    report_path = output_directory / "mpfb-morph-basis.json"
    report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")

    print()
    print(f"controls with movement: {len(parameters)}/{len(MORPH_CONTROL_SPECS)}")
    print(f"measurement keys represented: {len(represented)}")
    print(f"basis size: {len(payload) / (1024 * 1024):.2f} MB")
    print(f"written to {report_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
