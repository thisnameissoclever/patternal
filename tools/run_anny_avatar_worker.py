#!/usr/bin/env python3
"""Execute the declared Anny control map against the immutable avatar input.

Runs inside the installed Anny challenger virtual environment. It verifies the
immutable avatar-worker input and the complete control map, blocks outbound
network access, applies every ``linear-direct`` control exactly, jointly fits
every ``bounded-differentiable-fit`` control with the declared station
objectives, and writes the raw worker artifacts: display mesh, watertight
collision mesh, display-to-collider map, control application report, landmarks,
measurements, collider registration evidence, and a rejection list. The
producer claims nothing; wrapping and verification happen in separate tools.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import sys
from typing import Any

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
for entry in (str(REPOSITORY_ROOT), str(REPOSITORY_ROOT / "tools")):
    if entry not in sys.path:
        sys.path.insert(0, entry)


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--control-map", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--cache-dir", required=True, type=Path)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--stages", type=int, default=4)
    parser.add_argument("--steps-per-stage", type=int, default=60)
    parser.add_argument("--learning-rate", type=float, default=0.03)
    return parser.parse_args()


def install_network_guard() -> None:
    import socket

    def denied(*_args, **_kwargs):
        raise RuntimeError("Outbound network access is disabled for the Anny worker.")

    class DeniedSocket(socket.socket):
        def connect(self, *args, **kwargs):
            return denied()

        def connect_ex(self, *args, **kwargs):
            return denied()

    socket.socket = DeniedSocket
    socket.create_connection = denied
    socket.getaddrinfo = denied


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def main() -> int:
    arguments = parse_arguments()
    cache_dir = arguments.cache_dir.resolve()
    cache_dir.mkdir(parents=True, exist_ok=True)
    os.environ["ANNY_CACHE_DIR"] = str(cache_dir / "anny")
    os.environ["WARP_CACHE_PATH"] = str(cache_dir / "warp")
    install_network_guard()

    import numpy as np
    import torch

    from tools.avatar_worker_input import verify_input
    from tools.avatar_worker_output import validate_control_map
    from anny_worker_measurements import (
        Landmarks,
        LimbSection,
        build_limb_section,
        extract_landmarks,
        horizontal_section,
        maximum_circumference_height,
        minimum_circumference_height,
        section_value,
    )

    input_directory = arguments.input.resolve(strict=True)
    input_manifest = verify_input(input_directory)
    input_document = json.loads(
        (input_directory / "avatar-worker-input.json").read_text(encoding="utf-8")
    )
    control_map = json.loads(arguments.control_map.read_text(encoding="utf-8"))
    control_map_id = validate_control_map(control_map, input_document)

    output = arguments.output.resolve()
    if output.exists():
        raise ValueError(f"Refusing to overwrite an existing worker output: {output}")
    output.mkdir(parents=True)

    torch.manual_seed(arguments.seed)
    torch.use_deterministic_algorithms(True)

    import anny

    model = anny.Anny(
        phenotypes="all", local_changes="all", facial_actions="all"
    ).to(dtype=torch.float64, device="cpu")

    source_values = {}
    for row in input_document["bodyState"]["measurements"]:
        source_values[row["key"]] = float(row["value"])
    for row in input_document["bodyState"]["customMeasurements"]:
        source_values[row["key"]] = float(row["value"])

    map_rows = {row["key"]: row for row in control_map["controls"]}

    # ---- Direct controls -------------------------------------------------
    # Anny's gender anchors are ordered ["male", "female"], so 1.0 is fully
    # female. This is the opposite of the MakeHuman macro convention that the
    # MPFB lane used, where 0.0 was female. The input bodyTemplate "feminine"
    # therefore maps to gender 1.0 here.
    base_phenotype: dict[str, float] = {"gender": 1.0, "age": 0.5}
    direct_phenotype: dict[str, tuple[str, float]] = {}
    direct_local: dict[str, tuple[str, float]] = {}
    for key, row in map_rows.items():
        if row["status"] != "mapped":
            continue
        transform = row["target"]["transform"]
        if transform["kind"] != "linear-direct":
            continue
        value = source_values[key] * transform["scale"] + transform["offset"]
        value = min(max(value, transform["clampLow"]), transform["clampHigh"])
        if row["target"]["family"] == "phenotype":
            direct_phenotype[row["target"]["key"]] = (key, value)
        else:
            direct_local[row["target"]["key"]] = (key, value)

    # ---- Fit controls ----------------------------------------------------
    fit_rows = {
        key: row
        for key, row in map_rows.items()
        if row["status"] == "mapped"
        and row["target"]["transform"]["kind"] == "bounded-differentiable-fit"
    }

    objectives: dict[tuple[str, str], dict[str, Any]] = {}
    for key, row in fit_rows.items():
        transform = row["target"]["transform"]
        objective = transform["objective"]
        identity = (objective["measure"], objective["station"])
        entry = objectives.setdefault(
            identity,
            {
                "measure": objective["measure"],
                "station": objective["station"],
                "sourceKeys": set(),
                "targets": set(),
                "bounds": {},
            },
        )
        entry["sourceKeys"].add(key)
        entry["sourceKeys"].update(objective.get("pairedKeys", []))
        labels = [
            (row["target"]["family"], row["target"]["key"]),
            *(
                (row["target"]["family"], label)
                for label in objective.get("additionalTargetKeys", [])
            ),
        ]
        entry["targets"].update(labels)
        for family, label in labels:
            entry["bounds"][(family, label)] = tuple(transform["bounds"])

    for entry in objectives.values():
        entry["targetValueCm"] = float(
            np.mean([source_values[key] for key in sorted(entry["sourceKeys"])])
        )

    parameters: dict[tuple[str, str], torch.nn.Parameter] = {}
    bounds: dict[tuple[str, str], tuple[float, float]] = {}
    for entry in objectives.values():
        for family, label in sorted(entry["targets"]):
            if (family, label) in parameters:
                bounds[(family, label)] = (
                    max(bounds[(family, label)][0], entry["bounds"][(family, label)][0]),
                    min(bounds[(family, label)][1], entry["bounds"][(family, label)][1]),
                )
                continue
            low, high = entry["bounds"][(family, label)]
            initial = 0.5 if family == "phenotype" else 0.0
            parameters[(family, label)] = torch.nn.Parameter(
                torch.tensor(initial, dtype=torch.float64)
            )
            bounds[(family, label)] = (low, high)

    def model_kwargs() -> dict[str, Any]:
        phenotype: dict[str, Any] = dict(base_phenotype)
        local: dict[str, Any] = {}
        for label, (_, value) in direct_phenotype.items():
            phenotype[label] = value
        for label, (_, value) in direct_local.items():
            local[label] = value
        for (family, label), parameter in parameters.items():
            if family == "phenotype":
                phenotype[label] = parameter
            else:
                local[label] = parameter
        return {"phenotype_kwargs": phenotype, "local_changes_kwargs": local}

    def evaluate_vertices_cm() -> tuple[torch.Tensor, dict[str, Any]]:
        result = model(**model_kwargs())
        vertices = result["vertices"] * 100.0
        return vertices, result

    faces = np.asarray(model.faces, dtype=np.int64)
    bone_labels = [str(label) for label in model.bone_labels]

    # ---- Station catalog -------------------------------------------------
    VERTICAL = 2

    def build_stations(
        vertices_np: np.ndarray,
        heads_cm: np.ndarray,
        apex_override: tuple[int, int] | None = None,
    ):
        marks = extract_landmarks(vertices_np, bone_labels, heads_cm)
        if apex_override is not None:
            from dataclasses import replace

            marks = replace(
                marks,
                left_bust_apex=apex_override[0],
                right_bust_apex=apex_override[1],
            )
        heads = marks.bone_heads_cm
        front = marks.front_sign
        floor = marks.floor_z

        def head_of(name: str) -> np.ndarray:
            return heads[name]

        def mid(a: str, b: str) -> np.ndarray:
            return 0.5 * (heads[a] + heads[b])

        shoulder_z = mid("upperarm01.L", "upperarm01.R")[VERTICAL]
        hip_joint_z = mid("upperleg01.L", "upperleg01.R")[VERTICAL]
        crotch = mid("upperleg01.L", "upperleg01.R")
        neck_z = head_of("neck01")[VERTICAL]
        knee_l = head_of("lowerleg01.L")
        knee_r = head_of("lowerleg01.R")
        ankle_l = head_of("foot.L")
        ankle_r = head_of("foot.R")
        apex_z = 0.5 * (
            vertices_np[marks.left_bust_apex, VERTICAL]
            + vertices_np[marks.right_bust_apex, VERTICAL]
        )
        torso_x_half = abs(head_of("upperarm01.L")[0] - head_of("upperarm01.R")[0]) / 2.0
        torso_window = (-0.72 * 2 * torso_x_half, 0.72 * 2 * torso_x_half)

        underbust_z = minimum_circumference_height(
            vertices_np, faces, low_cm=apex_z - 10.0, high_cm=apex_z - 4.0,
            x_window=torso_window,
        )
        waist_z = minimum_circumference_height(
            vertices_np, faces,
            low_cm=hip_joint_z + 0.45 * (underbust_z - hip_joint_z),
            high_cm=underbust_z - 2.0,
            x_window=torso_window,
        )
        hip_z = maximum_circumference_height(
            vertices_np, faces, low_cm=hip_joint_z - 8.0, high_cm=waist_z - 4.0,
            x_window=torso_window,
        )
        abdomen_z = 0.5 * (waist_z + hip_z) + 2.0
        high_hip_z = waist_z - 0.4 * (waist_z - hip_z)

        stations: dict[str, dict[str, Any]] = {}

        def torso_section(name: str, height: float):
            stations[name] = {
                "section": horizontal_section(
                    vertices_np, faces, name=name, height_cm=height,
                    x_window=torso_window,
                ),
                "heightCm": height,
            }

        torso_section("bust", apex_z)
        torso_section("underbust", underbust_z)
        torso_section("waist", waist_z)
        torso_section("hip", hip_z)
        torso_section("high-hip", high_hip_z)
        torso_section("abdomen", abdomen_z)
        # A horizontal plane above the armpit also cuts both arms, and the
        # largest-perimeter loop then belongs to an arm rather than the torso.
        # The upper-chest stations therefore use a radial window about the
        # torso axis that excludes the arms.
        torso_radius = 1.32 * torso_x_half
        for name, height in (
            ("chest", apex_z + 2.0),
            ("chest-wall", apex_z + 7.0),
        ):
            stations[name] = {
                "section": horizontal_section(
                    vertices_np, faces, name=name, height_cm=height,
                    radial_window=(0.0, float(np.median(vertices_np[:, 1])), torso_radius),
                ),
                "heightCm": height,
            }
        torso_section("pelvis", hip_joint_z)
        torso_section("seat", hip_z)

        head_subset_low = neck_z + 2.0
        eye_level = 0.5 * (
            head_of("eye.L")[VERTICAL] + head_of("eye.R")[VERTICAL]
        )
        skull_center = head_of("head")
        stations["head"] = {
            "section": horizontal_section(
                vertices_np, faces, name="head",
                height_cm=eye_level + 3.0,
                radial_window=(skull_center[0], skull_center[1], 13.0),
            ),
            "heightCm": eye_level + 3.0,
        }
        neck_center = head_of("neck02")
        for name, height, radius in (
            ("mid-neck-plane", 0.5 * (neck_z + head_of("head")[VERTICAL]), 9.0),
            ("neck-base-plane", neck_z + 1.5, 11.0),
        ):
            stations[name] = {
                "section": horizontal_section(
                    vertices_np, faces, name=name,
                    height_cm=height,
                    radial_window=(neck_center[0], neck_center[1], radius),
                ),
                "heightCm": height,
            }

        limb_specs = {
            "upper-arm-L": ("upperarm01.L", "lowerarm01.L", 0.5, 12.0),
            "upper-arm-R": ("upperarm01.R", "lowerarm01.R", 0.5, 12.0),
            "bicep-L": ("upperarm01.L", "lowerarm01.L", 0.4, 12.0),
            "bicep-R": ("upperarm01.R", "lowerarm01.R", 0.4, 12.0),
            "forearm-L": ("lowerarm01.L", "wrist.L", 0.3, 10.0),
            "forearm-R": ("lowerarm01.R", "wrist.R", 0.3, 10.0),
            "wrist-L": ("lowerarm01.L", "wrist.L", 0.97, 7.0),
            "wrist-R": ("lowerarm01.R", "wrist.R", 0.97, 7.0),
            "upper-thigh-L": ("upperleg01.L", "lowerleg01.L", 0.12, 18.0),
            "upper-thigh-R": ("upperleg01.R", "lowerleg01.R", 0.12, 18.0),
            "mid-thigh-L": ("upperleg01.L", "lowerleg01.L", 0.5, 16.0),
            "mid-thigh-R": ("upperleg01.R", "lowerleg01.R", 0.5, 16.0),
            "knee-L": ("upperleg01.L", "lowerleg01.L", 0.98, 12.0),
            "knee-R": ("upperleg01.R", "lowerleg01.R", 0.98, 12.0),
            "calf-L": ("lowerleg01.L", "foot.L", 0.3, 12.0),
            "calf-R": ("lowerleg01.R", "foot.R", 0.3, 12.0),
            "ankle-L": ("lowerleg01.L", "foot.L", 0.93, 8.0),
            "ankle-R": ("lowerleg01.R", "foot.R", 0.93, 8.0),
            "mid-neck": ("neck01", "head", 0.45, 9.0),
            "neck-base": ("neck01", "head", 0.08, 11.0),
            "palm-L": ("wrist.L", "finger3-1.L", 0.55, 7.0),
            "palm-R": ("wrist.R", "finger3-1.R", 0.55, 7.0),
        }
        for name, (origin, target, fraction, radius) in limb_specs.items():
            stations[name] = {
                "section": build_limb_section(
                    vertices_np, faces, name=name,
                    origin_cm=head_of(origin), target_cm=head_of(target),
                    fraction=fraction, radius_cm=radius, front_sign=front,
                ),
                "originCm": head_of(origin),
            }

        for side in ("L", "R"):
            heel = head_of(f"foot.{side}")
            toe = head_of(f"toe3-1.{side}")
            stations[f"foot-ball-{side}"] = {
                "section": build_limb_section(
                    vertices_np, faces, name=f"foot-ball-{side}",
                    origin_cm=heel, target_cm=toe, fraction=0.55, radius_cm=8.0,
                    front_sign=front,
                ),
                "originCm": heel,
            }
            up = np.array([0.0, 0.0, 1.0])
            axis = toe - heel
            axis = axis / np.linalg.norm(axis)
            oblique = 0.36 * axis + 0.933 * up
            stations[f"heel-instep-{side}"] = {
                "section": build_limb_section(
                    vertices_np, faces, name=f"heel-instep-{side}",
                    origin_cm=heel - 5.0 * up, target_cm=heel - 5.0 * up + 22.0 * oblique,
                    fraction=0.35, radius_cm=11.0,
                    front_sign=front,
                ),
                "originCm": heel - 5.0 * up,
            }

        subsets: dict[str, np.ndarray] = {}

        def subset(name: str, mask: np.ndarray) -> None:
            indices = np.flatnonzero(mask)
            if indices.size == 0:
                raise ValueError(f"Station subset {name} is empty.")
            subsets[name] = indices

        z = vertices_np[:, VERTICAL]
        x = vertices_np[:, 0]
        y_front = front * vertices_np[:, 1]
        subset("shoulder-band", (z >= shoulder_z - 2.0) & (z <= shoulder_z + 4.0))
        shoulder_half = abs(heads["upperarm01.L"][0] - heads["upperarm01.R"][0]) / 2.0
        subset(
            "across-front-band",
            (z >= apex_z + 6.0)
            & (z <= apex_z + 12.0)
            & (y_front > 0.0)
            & (np.abs(x) <= 1.05 * shoulder_half),
        )
        skull = heads["head"]
        eye_z = 0.5 * (heads["eye.L"][VERTICAL] + heads["eye.R"][VERTICAL])
        head_xy = np.linalg.norm(vertices_np[:, :2] - skull[None, :2], axis=1)
        subset("head-region", (head_xy <= 15.0) & (z >= skull[VERTICAL] - 6.0))
        subset("face-band", (head_xy <= 15.0) & (z >= eye_z - 5.0) & (z <= eye_z + 2.0))
        subset("cheek-band", (head_xy <= 15.0) & (z >= eye_z - 5.0) & (z <= eye_z - 1.0))
        face_front = float(np.max(y_front[(head_xy <= 15.0) & (z >= skull[VERTICAL] - 8.0)]))
        chin_band = (
            (head_xy <= 9.0)
            & (z >= heads["neck01"][VERTICAL])
            & (z <= skull[VERTICAL] + 2.0)
        )
        chin_candidates = np.zeros_like(chin_band)
        for margin in (5.0, 7.0, 9.0, 12.0):
            chin_candidates = chin_band & (y_front >= face_front - margin)
            if chin_candidates.any():
                break
        if not chin_candidates.any():
            fallback = np.flatnonzero(chin_band)
            chin_candidates[fallback[int(np.argmax(y_front[fallback]))]] = True
        subset("chin-region", chin_candidates)
        hip_center = mid("upperleg01.L", "upperleg01.R")
        crotch_mask = np.zeros(len(vertices_np), dtype=bool)
        for x_margin, y_margin in ((2.5, 6.0), (3.5, 9.0), (5.0, 12.0)):
            crotch_mask = (
                (np.abs(x - hip_center[0]) <= x_margin)
                & (np.abs(vertices_np[:, 1] - hip_center[1]) <= y_margin)
                & (z <= hip_center[VERTICAL] + 2.0)
                & (z >= hip_center[VERTICAL] - 14.0)
            )
            if crotch_mask.any():
                break
        subset("crotch-region", crotch_mask)
        for side, sign in (("L", -1.0), ("R", 1.0)):
            wrist_pos = head_of(f"wrist.{side}")
            hand_mask = (
                np.linalg.norm(vertices_np - wrist_pos[None, :], axis=1) <= 22.0
            ) & (sign * x >= sign * wrist_pos[0] - 2.0) & (
                z <= wrist_pos[VERTICAL] + 3.0
            )
            subset(f"hand-{side}", hand_mask)
            heel = head_of(f"foot.{side}")
            foot_mask = (z <= heel[VERTICAL] + 6.0) & (
                np.abs(x - heel[0]) <= 9.0
            )
            subset(f"foot-{side}", foot_mask)

        context = {
            "marks": marks,
            "front": front,
            "floor": floor,
            "heads": heads,
            "stations": stations,
            "subsets": subsets,
            "waist_z": waist_z,
            "hip_z": hip_z,
            "underbust_z": underbust_z,
            "abdomen_z": abdomen_z,
            "crotch": crotch,
            "apex_left": marks.left_bust_apex,
            "apex_right": marks.right_bust_apex,
        }
        return context

    def bone_heads_cm_tensor(result: dict[str, Any]) -> torch.Tensor:
        return result["rest_bone_heads"][0] * 100.0

    def head_t(result: dict[str, Any], name: str) -> torch.Tensor:
        return bone_heads_cm_tensor(result)[bone_labels.index(name)]

    def evaluate_objective(
        measure: str,
        station: str,
        vertices: torch.Tensor,
        result: dict[str, Any],
        context: dict[str, Any],
    ) -> torch.Tensor:
        front = context["front"]
        subsets = context["subsets"]
        stations = context["stations"]
        z = vertices[0, :, VERTICAL]

        def station_metric(names: list[str], kind: str, axis: int = 1) -> torch.Tensor:
            values = []
            for name in names:
                entry = stations[name]
                values.append(
                    section_value(
                        vertices, entry["section"], kind=kind, axis=axis,
                        front_sign=front,
                    )[0]
                )
            return torch.stack(values).mean()

        def station_z(name: str) -> torch.Tensor:
            """Differentiable station height from the captured section vertices."""
            section = stations[name]["section"]
            if isinstance(section, LimbSection):
                local = np.unique(section.topology.edge_indices)
                indices = section.vertex_indices[local]
            else:
                indices = np.unique(section.edge_indices)
            return vertices[0, indices, VERTICAL].mean()

        def floor_v() -> torch.Tensor:
            return z.amin()

        def crown_v() -> torch.Tensor:
            return z.amax()

        def dist(a: str, b: str) -> torch.Tensor:
            return torch.linalg.vector_norm(head_t(result, a) - head_t(result, b))

        def mean_sides(function) -> torch.Tensor:
            return 0.5 * (function("L") + function("R"))

        key = (measure, station)
        if key == ("stature", "floor-to-crown"):
            return crown_v() - floor_v()
        if key == ("circumference", "bust"):
            return station_metric(["bust"], "circumference")
        if key == ("circumference", "underbust"):
            return station_metric(["underbust"], "circumference")
        if key == ("circumference", "waist"):
            return station_metric(["waist"], "circumference")
        if key == ("circumference", "hip"):
            return station_metric(["hip"], "circumference")
        if key == ("circumference", "high-hip"):
            return station_metric(["high-hip"], "circumference")
        if key == ("circumference", "abdomen"):
            return station_metric(["abdomen"], "circumference")
        if key == ("depth", "abdomen"):
            return station_metric(["abdomen"], "extent", axis=1)
        if key == ("projection", "abdomen-front"):
            abdomen = section_value(
                vertices, stations["abdomen"]["section"], kind="front-projection",
                front_sign=front,
            )[0]
            waist = section_value(
                vertices, stations["waist"]["section"], kind="front-projection",
                front_sign=front,
            )[0]
            return abdomen - waist
        if key == ("depth", "chest"):
            return station_metric(["chest"], "extent", axis=1)
        if key == ("depth", "waist"):
            return station_metric(["waist"], "extent", axis=1)
        if key == ("depth", "underbust"):
            return station_metric(["underbust"], "extent", axis=1)
        if key == ("depth", "hip"):
            return station_metric(["hip"], "extent", axis=1)
        if key == ("depth", "high-hip"):
            return station_metric(["high-hip"], "extent", axis=1)
        if key == ("width", "pelvis"):
            return station_metric(["pelvis"], "extent", axis=0)
        if key == ("arc-length", "front-hip"):
            return station_metric(["hip"], "front-arc")
        if key == ("arc-length", "back-hip"):
            return station_metric(["hip"], "back-arc")
        if key == ("projection", "seat-rear"):
            seat = section_value(
                vertices, stations["seat"]["section"], kind="back-projection",
                front_sign=front,
            )[0]
            waist = section_value(
                vertices, stations["waist"]["section"], kind="back-projection",
                front_sign=front,
            )[0]
            return seat - waist
        if key == ("height", "waist-to-crotch"):
            crotch_z = z[subsets["crotch-region"]].amin()
            return station_z("waist") - crotch_z
        if key == ("height", "waist-to-hip"):
            return station_z("waist") - station_z("hip")
        if key == ("height", "nape-to-waist"):
            nape_z = head_t(result, "neck01")[VERTICAL]
            return nape_z - station_z("waist")
        if key == ("distance", "shoulder-breadth"):
            return torch.linalg.vector_norm(
                head_t(result, "upperarm01.L") - head_t(result, "upperarm01.R")
            )
        if key == ("length", "neck-to-shoulder-tip"):
            half_breadth = 0.5 * torch.linalg.vector_norm(
                head_t(result, "upperarm01.L") - head_t(result, "upperarm01.R")
            )
            neck_half = 0.5 * section_value(
                vertices, stations["neck-base"]["section"], kind="extent", axis=0,
                front_sign=front,
            )[0]
            return half_breadth - neck_half
        if key == ("distance", "across-front"):
            band = subsets["across-front-band"]
            xs = vertices[0, band, 0]
            return xs.amax() - xs.amin()
        if key == ("circumference", "mid-neck"):
            return station_metric(["mid-neck-plane"], "circumference")
        if key == ("circumference", "neck-base"):
            return station_metric(["neck-base-plane"], "circumference")
        if key == ("height", "neck-span"):
            return dist("neck01", "head")
        if key == ("projection", "neck-forward"):
            forward = front * (
                head_t(result, "head")[1] - head_t(result, "neck01")[1]
            )
            return forward
        if key == ("circumference", "head"):
            return station_metric(["head"], "circumference")
        if key == ("height", "crown-to-chin"):
            chin = subsets["chin-region"]
            return crown_v() - z[chin].amin()
        if key == ("width", "face"):
            region = subsets["face-band"]
            xs = vertices[0, region, 0]
            return xs.amax() - xs.amin()
        if key == ("depth", "face"):
            region = subsets["head-region"]
            ys = vertices[0, region, 1]
            return ys.amax() - ys.amin()
        if key == ("width", "cheekbones"):
            region = subsets["cheek-band"]
            xs = vertices[0, region, 0]
            return xs.amax() - xs.amin()
        if key == ("width", "jaw"):
            chin = subsets["chin-region"]
            xs = vertices[0, chin, 0]
            return xs.amax() - xs.amin()
        if key == ("projection", "skull-back"):
            region = subsets["head-region"]
            back = (-front) * vertices[0, region, 1]
            neck_back = section_value(
                vertices, stations["neck-base"]["section"], kind="back-projection",
                front_sign=front,
            )[0]
            return back.amax() - neck_back
        if key == ("projection", "bust-apex"):
            apex = 0.5 * (
                front * vertices[0, context["apex_left"], 1]
                + front * vertices[0, context["apex_right"], 1]
            )
            chest_front = section_value(
                vertices, stations["chest-wall"]["section"], kind="front-projection",
                front_sign=front,
            )[0]
            return apex - chest_front
        if key == ("height", "bust-apex"):
            apex_z_t = 0.5 * (
                vertices[0, context["apex_left"], VERTICAL]
                + vertices[0, context["apex_right"], VERTICAL]
            )
            return head_t(result, "neck01")[VERTICAL] - apex_z_t
        if key == ("distance", "bust-apex-separation"):
            return (
                vertices[0, context["apex_right"], 0]
                - vertices[0, context["apex_left"], 0]
            ).abs()
        if key == ("circumference", "upper-arm"):
            return station_metric(["upper-arm-L", "upper-arm-R"], "circumference")
        if key == ("depth", "bicep"):
            return station_metric(["bicep-L", "bicep-R"], "front-extent")
        if key == ("circumference", "forearm"):
            return station_metric(["forearm-L", "forearm-R"], "circumference")
        if key == ("circumference", "wrist"):
            return station_metric(["wrist-L", "wrist-R"], "circumference")
        if key == ("length", "shoulder-to-elbow"):
            return mean_sides(lambda side: dist(f"upperarm01.{side}", f"lowerarm01.{side}"))
        if key == ("length", "elbow-to-wrist"):
            return mean_sides(lambda side: dist(f"lowerarm01.{side}", f"wrist.{side}"))
        if key == ("length", "shoulder-to-wrist"):
            return mean_sides(
                lambda side: dist(f"upperarm01.{side}", f"lowerarm01.{side}")
                + dist(f"lowerarm01.{side}", f"wrist.{side}")
            )
        if key == ("circumference", "upper-thigh"):
            return station_metric(["upper-thigh-L", "upper-thigh-R"], "circumference")
        if key == ("circumference", "mid-thigh"):
            return station_metric(["mid-thigh-L", "mid-thigh-R"], "circumference")
        if key == ("circumference", "calf"):
            return station_metric(["calf-L", "calf-R"], "circumference")
        if key == ("circumference", "ankle"):
            return station_metric(["ankle-L", "ankle-R"], "circumference")
        if key == ("circumference", "knee"):
            return station_metric(["knee-L", "knee-R"], "circumference")
        if key == ("height", "floor-to-knee"):
            knee_z = 0.5 * (
                head_t(result, "lowerleg01.L")[VERTICAL]
                + head_t(result, "lowerleg01.R")[VERTICAL]
            )
            return knee_z - floor_v()
        if key == ("length", "knee-to-ankle"):
            return mean_sides(lambda side: dist(f"lowerleg01.{side}", f"foot.{side}"))
        if key == ("length", "crotch-to-knee"):
            crotch_z = z[subsets["crotch-region"]].amin()
            knee_z = 0.5 * (
                head_t(result, "lowerleg01.L")[VERTICAL]
                + head_t(result, "lowerleg01.R")[VERTICAL]
            )
            return crotch_z - knee_z
        if key == ("length", "crotch-to-floor"):
            crotch_z = z[subsets["crotch-region"]].amin()
            return crotch_z - floor_v()
        if key == ("length", "waist-to-floor"):
            return station_z("waist") - floor_v()
        if key == ("length", "waist-to-knee"):
            knee_z = 0.5 * (
                head_t(result, "lowerleg01.L")[VERTICAL]
                + head_t(result, "lowerleg01.R")[VERTICAL]
            )
            return station_z("waist") - knee_z
        if key == ("length", "foot"):
            def foot_len(side: str) -> torch.Tensor:
                indices = subsets[f"foot-{side}"]
                axis = context["heads"][f"toe3-1.{side}"] - context["heads"][f"foot.{side}"]
                axis = axis / np.linalg.norm(axis)
                axis_t = torch.as_tensor(axis, dtype=vertices.dtype)
                projected = vertices[0, indices, :] @ axis_t
                return projected.amax() - projected.amin()
            return mean_sides(foot_len)
        if key == ("width", "foot"):
            def foot_width(side: str) -> torch.Tensor:
                indices = subsets[f"foot-{side}"]
                axis = context["heads"][f"toe3-1.{side}"] - context["heads"][f"foot.{side}"]
                axis[2] = 0.0
                axis = axis / np.linalg.norm(axis)
                side_axis = np.array([-axis[1], axis[0], 0.0])
                axis_t = torch.as_tensor(side_axis, dtype=vertices.dtype)
                projected = vertices[0, indices, :] @ axis_t
                return projected.amax() - projected.amin()
            return mean_sides(foot_width)
        if key == ("circumference", "foot-ball"):
            return station_metric(["foot-ball-L", "foot-ball-R"], "circumference")
        if key == ("circumference", "heel-instep"):
            return station_metric(["heel-instep-L", "heel-instep-R"], "circumference")
        if key == ("length", "hand"):
            def hand_len(side: str) -> torch.Tensor:
                indices = subsets[f"hand-{side}"]
                wrist = head_t(result, f"wrist.{side}")
                distances = torch.linalg.vector_norm(
                    vertices[0, indices, :] - wrist, dim=1
                )
                return distances.amax()
            return mean_sides(hand_len)
        if key == ("width", "palm"):
            return station_metric(["palm-L", "palm-R"], "extent", axis=0)
        if key == ("circumference", "palm"):
            return station_metric(["palm-L", "palm-R"], "circumference")
        raise ValueError(f"No station rule implements objective {measure} at {station}.")

    per_side_objectives = {
        ("circumference", "upper-arm"): ("upperArmCircL", "upperArmCircR"),
        ("depth", "bicep"): ("bicepDepthL", "bicepDepthR"),
        ("circumference", "forearm"): ("forearmCircL", "forearmCircR"),
        ("circumference", "upper-thigh"): ("thighUpperCircL", "thighUpperCircR"),
        ("circumference", "mid-thigh"): ("thighMidCircL", "thighMidCircR"),
        ("circumference", "calf"): ("calfCircL", "calfCircR"),
        ("length", "foot"): ("footLengthL", "footLengthR"),
        ("width", "foot"): ("footWidthL", "footWidthR"),
        ("circumference", "foot-ball"): ("ballGirthL", "ballGirthR"),
        ("circumference", "heel-instep"): ("heelGirthL", "heelGirthR"),
        ("length", "hand"): ("handLengthL", "handLengthR"),
        ("width", "palm"): ("palmWidthL", "palmWidthR"),
        ("circumference", "palm"): ("palmCircL", "palmCircR"),
    }

    # Per-side objectives evaluate left and right separately against their own
    # source values when their targets are side-specific.
    expanded: dict[tuple[str, str], dict[str, Any]] = {}
    for identity, entry in objectives.items():
        targets = sorted(entry["targets"])
        side_specific = all(
            label.startswith(("l-", "r-")) for _, label in targets
        ) and identity in per_side_objectives
        if not side_specific:
            expanded[identity] = entry
            continue
        left_key, right_key = per_side_objectives[identity]
        for side, source_key in (("L", left_key), ("R", right_key)):
            prefix = "l-" if side == "L" else "r-"
            side_targets = {
                (family, label)
                for family, label in entry["targets"]
                if label.startswith(prefix)
            }
            expanded[(identity[0], f"{identity[1]}::{side}")] = {
                "measure": identity[0],
                "station": identity[1],
                "side": side,
                "sourceKeys": {source_key},
                "targets": side_targets,
                "bounds": {t: entry["bounds"][t] for t in side_targets},
                "targetValueCm": source_values[source_key],
            }

    objectives = expanded

    def evaluate_expanded(
        entry: dict[str, Any],
        vertices: torch.Tensor,
        result: dict[str, Any],
        context: dict[str, Any],
    ) -> torch.Tensor:
        side = entry.get("side")
        if side is None:
            return evaluate_objective(
                entry["measure"], entry["station"], vertices, result, context
            )
        station = entry["station"]
        stations = context["stations"]
        front = context["front"]
        heads = context["heads"]
        named = f"{station}-{side}"
        if named in stations:
            kind = {
                "circumference": "circumference",
                "depth": "front-extent",
                "width": "extent",
            }.get(entry["measure"], "circumference")
            axis = 1 if entry["measure"] == "depth" else 0
            return section_value(
                vertices, stations[named]["section"], kind=kind, axis=axis,
                front_sign=front,
            )[0]
        if entry["measure"] == "length" and station == "foot":
            indices = context["subsets"][f"foot-{side}"]
            axis = heads[f"toe3-1.{side}"] - heads[f"foot.{side}"]
            axis = axis / np.linalg.norm(axis)
            axis_t = torch.as_tensor(axis, dtype=vertices.dtype)
            projected = vertices[0, indices, :] @ axis_t
            return projected.amax() - projected.amin()
        if entry["measure"] == "width" and station == "foot":
            indices = context["subsets"][f"foot-{side}"]
            axis = heads[f"toe3-1.{side}"] - heads[f"foot.{side}"]
            axis[2] = 0.0
            axis = axis / np.linalg.norm(axis)
            side_axis = np.array([-axis[1], axis[0], 0.0])
            axis_t = torch.as_tensor(side_axis, dtype=vertices.dtype)
            projected = vertices[0, indices, :] @ axis_t
            return projected.amax() - projected.amin()
        if entry["measure"] == "length" and station == "hand":
            indices = context["subsets"][f"hand-{side}"]
            wrist = head_t(result, f"wrist.{side}")
            distances = torch.linalg.vector_norm(vertices[0, indices, :] - wrist, dim=1)
            return distances.amax()
        raise ValueError(f"No per-side rule for {entry['measure']} at {station}.")

    tolerance = {"circumference": 0.75, "stature": 0.25, "projection": 0.4, "default": 0.55}

    optimizer = torch.optim.Adam(parameters.values(), lr=arguments.learning_rate)
    fit_history: list[dict[str, Any]] = []
    for stage in range(arguments.stages):
        with torch.no_grad():
            vertices, result = evaluate_vertices_cm()
            context = build_stations(
                vertices[0].detach().cpu().numpy(),
                (result["rest_bone_heads"][0] * 100.0).detach().cpu().numpy(),
            )
        for _ in range(arguments.steps_per_stage):
            optimizer.zero_grad(set_to_none=True)
            vertices, result = evaluate_vertices_cm()
            losses = []
            for entry in objectives.values():
                predicted = evaluate_expanded(entry, vertices, result, context)
                scale = tolerance.get(entry["measure"], tolerance["default"])
                if entry["station"] == "bust-apex":
                    scale = 0.3
                elif entry["station"] == "abdomen-front":
                    scale = tolerance["projection"]
                losses.append(
                    ((predicted - entry["targetValueCm"]) / scale).square()
                )
            for label, parameter in parameters.items():
                neutral = 0.5 if label[0] == "phenotype" else 0.0
                losses.append(0.01 * (parameter - neutral).square())
            loss = torch.stack(losses).mean()
            loss.backward()
            torch.nn.utils.clip_grad_norm_(parameters.values(), max_norm=25.0)
            optimizer.step()
            with torch.no_grad():
                for label, parameter in parameters.items():
                    low, high = bounds[label]
                    parameter.clamp_(low, high)
        with torch.no_grad():
            vertices, result = evaluate_vertices_cm()
            predictions = {
                f"{entry['measure']}@{objective_key[1]}": float(
                    evaluate_expanded(entry, vertices, result, context)
                )
                for objective_key, entry in objectives.items()
            }
        fit_history.append(
            {
                "stage": stage + 1,
                "loss": float(loss.detach()),
                "predictionsCm": predictions,
            }
        )
        print(
            json.dumps({"stage": stage + 1, "loss": float(loss.detach())}),
            flush=True,
        )

    with torch.no_grad():
        vertices, result = evaluate_vertices_cm()
        context = build_stations(
            vertices[0].detach().cpu().numpy(),
            (result["rest_bone_heads"][0] * 100.0).detach().cpu().numpy(),
        )
        final_predictions = {}
        for objective_key, entry in objectives.items():
            final_predictions["|".join(objective_key)] = {
                "predictedCm": float(
                    evaluate_expanded(entry, vertices, result, context)
                ),
                "targetCm": entry["targetValueCm"],
                "sourceKeys": sorted(entry["sourceKeys"]),
                "targets": sorted(f"{family}:{label}" for family, label in entry["targets"]),
            }

    applied_parameters = {
        f"{family}:{label}": float(parameter.detach())
        for (family, label), parameter in parameters.items()
    }

    vertices_np = vertices[0].detach().cpu().numpy()
    report = {
        "schemaVersion": "patterna.anny-worker-fit/1.0",
        "claims": {"accepted": False},
        "inputId": input_manifest["inputId"],
        "controlMapId": control_map_id,
        "seed": arguments.seed,
        "stages": arguments.stages,
        "stepsPerStage": arguments.steps_per_stage,
        "learningRate": arguments.learning_rate,
        "basePhenotype": base_phenotype,
        "directPhenotype": {k: v[1] for k, v in direct_phenotype.items()},
        "directLocalChanges": {k: v[1] for k, v in direct_local.items()},
        "fittedParameters": applied_parameters,
        "objectives": final_predictions,
        "history": fit_history,
        "meshSha256": sha256_bytes(
            np.ascontiguousarray(vertices_np.astype("<f8")).tobytes()
        ),
        "vertexCount": int(vertices_np.shape[0]),
        "faceCount": int(faces.shape[0]),
    }
    (output / "anny-fit-report.json").write_text(
        json.dumps(report, indent=2) + "\n", encoding="utf-8"
    )
    np.save(output / "fitted-vertices-cm.npy", vertices_np, allow_pickle=False)
    np.save(output / "faces.npy", faces, allow_pickle=False)

    from anny_worker_outputs import produce_outputs

    source_rows: dict[str, dict[str, Any]] = {}
    for row in input_document["bodyState"]["measurements"]:
        source_rows[row["key"]] = {
            "sourceKind": "builtIn",
            "sourceValue": row["value"],
            "sourceUnit": row["unit"],
        }
    for row in input_document["bodyState"]["customMeasurements"]:
        source_rows[row["key"]] = {
            "sourceKind": "custom",
            "sourceValue": row["value"],
            "sourceUnit": row["unit"],
        }
    identity = {
        "inputId": input_manifest["inputId"],
        "sourceRevisionBundleId": input_manifest["sourceRevisionBundleId"],
        "bodyStateId": input_manifest["bodyStateId"],
    }
    blender = (
        Path(os.environ["LOCALAPPDATA"])
        / "Patterna"
        / "SimulationRuntime"
        / "current"
        / "blender"
        / "blender.exe"
    )
    summary = produce_outputs(
        output=output,
        vertices_cm=vertices_np,
        faces=faces,
        bone_labels=bone_labels,
        bone_heads_cm=(result["rest_bone_heads"][0] * 100.0).detach().cpu().numpy(),
        context=context,
        fit_report=report,
        control_map=control_map,
        source_rows=source_rows,
        identity=identity,
        blender_path=blender,
        render_script=Path(__file__).resolve().parent / "render_anny_worker_views.py",
    )
    print(
        json.dumps(
            {
                "meshSha256": report["meshSha256"],
                "objectiveCount": len(final_predictions),
                **summary,
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
