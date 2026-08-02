"""Patterna-specific production blocks built on GarmentCode primitives."""

from __future__ import annotations

import copy
import math

import numpy as np
import pygarment as pyg
from scipy.spatial.transform import Rotation as R

from assets.garment_programs.base_classes import BaseBodicePanel
from assets.garment_programs.sleeves import SleevePanel


def _front_fraction(total: float, back_width: float) -> float:
    return (total - back_width) / (2.0 * total)


def _distributed_half_width(
    circumference: float,
    ease: float,
    fraction: float,
) -> float:
    return fraction * (circumference + ease)


class _PatternaTorsoHalfPanel(BaseBodicePanel):
    """A long shaped torso with independent chest, waist, and hip ease."""

    is_front = False

    def __init__(self, name, body, design) -> None:
        super().__init__(name, body, design)
        shirt = design["shirt"]
        chest_ease = float(shirt["patterna_chest_ease"]["v"])
        waist_ease = float(shirt["patterna_waist_ease"]["v"])
        hip_ease = float(shirt["patterna_hip_ease"]["v"])

        if self.is_front:
            chest_fraction = _front_fraction(body["bust"], body["back_width"])
            waist_fraction = _front_fraction(body["waist"], body["waist_back_width"])
            hip_fraction = _front_fraction(body["hips"], body["hip_back_width"])
        else:
            chest_fraction = body["back_width"] / (2.0 * body["bust"])
            waist_fraction = body["waist_back_width"] / (2.0 * body["waist"])
            hip_fraction = body["hip_back_width"] / (2.0 * body["hips"])

        chest_width = _distributed_half_width(body["bust"], chest_ease, chest_fraction)
        waist_width = _distributed_half_width(body["waist"], waist_ease, waist_fraction)
        hip_width = _distributed_half_width(body["hips"], hip_ease, hip_fraction)
        self.width = chest_width

        shoulder_tangent = np.tan(np.deg2rad(body["_shoulder_incl"]))
        shoulder_inclination = shoulder_tangent * chest_width
        length = float(shirt["length"]["v"]) * body["waist_line"]
        if self.is_front:
            front_back_difference = (
                chest_fraction - (0.5 - chest_fraction)
            ) * body["bust"]
            length -= shoulder_tangent * front_back_difference

        below_waist = max(0.0, length - body["waist_line"])
        hip_progress = min(1.0, below_waist / body["hips_line"])
        hem_width = waist_width + (hip_width - waist_width) * hip_progress
        waist_level = below_waist
        bust_level = below_waist + body["waist_line"] - body["_bust_line"]

        self.edges = pyg.EdgeSeqFactory.from_verts(
            [0, 0],
            [-hem_width, 0],
            [-waist_width, waist_level],
            [-chest_width, bust_level],
            [-chest_width, length],
            [0, length + shoulder_inclination],
            loop=True,
        )
        self.interfaces = {
            "outside": pyg.Interface(self, self.edges[1:4]),
            "inside": pyg.Interface(self, self.edges[-1]),
            "shoulder": pyg.Interface(self, self.edges[-2]),
            "bottom": pyg.Interface(self, self.edges[0]),
            "shoulder_corner": pyg.Interface(self, [self.edges[-3], self.edges[-2]]),
            "collar_corner": pyg.Interface(self, [self.edges[-2], self.edges[-1]]),
        }
        self.translate_by(
            [0, body["height"] - body["head_l"] - length - shoulder_inclination, 0]
        )

    def get_width(self, level):
        return super().get_width(level) + self.width - self.body["shoulder_w"] / 2


class PatternaTorsoFrontHalfPanel(_PatternaTorsoHalfPanel):
    is_front = True


class PatternaTorsoBackHalfPanel(_PatternaTorsoHalfPanel):
    is_front = False


def _bounded(value: float, low: float, high: float, name: str) -> float:
    value = float(value)
    if not math.isfinite(value) or value < low or value > high:
        raise ValueError(f"{name} must be from {low:g} through {high:g} centimeters.")
    return value


def _body_value(body, name: str, default: float) -> float:
    try:
        return body[name]
    except (KeyError, TypeError):
        return default


def _torso_station_profile(body) -> tuple[tuple[float, float, float], ...]:
    count = int(round(float(_body_value(
        body,
        "patterna_torso_station_profile_count",
        0.0,
    ))))
    if count == 0:
        return ()
    if count < 2 or count > 256:
        raise ValueError("Torso station profile count is invalid.")
    stations: list[tuple[float, float, float]] = []
    for index in range(count):
        prefix = f"patterna_torso_station_{index:02d}"
        height = float(_body_value(
            body,
            f"{prefix}_height_from_waist",
            math.nan,
        ))
        circumference = float(_body_value(
            body,
            f"{prefix}_circumference",
            math.nan,
        ))
        back_fraction = float(_body_value(
            body,
            f"{prefix}_back_fraction",
            math.nan,
        ))
        if (
            not all(math.isfinite(value) for value in (
                height,
                circumference,
                back_fraction,
            ))
            or circumference <= 0.0
            or not 0.20 <= back_fraction <= 0.80
        ):
            raise ValueError("Torso station profile contains an invalid sample.")
        stations.append((height, circumference, back_fraction))
    if any(
        stations[index][0] <= stations[index - 1][0]
        for index in range(1, len(stations))
    ):
        raise ValueError("Torso station profile heights must increase strictly.")
    return tuple(stations)


def _interpolate_torso_station(
    profile: tuple[tuple[float, float, float], ...],
    height: float,
) -> tuple[float, float]:
    if not profile:
        raise ValueError("A measured torso station profile is required.")
    if height < profile[0][0] - 1.0e-6 or height > profile[-1][0] + 1.0e-6:
        raise ValueError(
            f"Torso station {height:.3f} cm is outside the measured profile."
        )
    if height <= profile[0][0]:
        return profile[0][1], profile[0][2]
    if height >= profile[-1][0]:
        return profile[-1][1], profile[-1][2]
    for lower, upper in zip(profile, profile[1:]):
        if height > upper[0]:
            continue
        ratio = (height - lower[0]) / (upper[0] - lower[0])
        return (
            lower[1] + (upper[1] - lower[1]) * ratio,
            lower[2] + (upper[2] - lower[2]) * ratio,
        )
    raise RuntimeError("Torso station interpolation did not find a bracket.")


def _target_length_curve(
    start,
    end,
    target_length: float,
    control_t: float,
    normal_sign: float,
    label: str | None = None,
):
    """Build a monotonic princess edge with an exact body-surface seam length."""

    straight_length = float(np.linalg.norm(np.asarray(end) - np.asarray(start)))
    if target_length < straight_length - 1.0e-6:
        raise ValueError(
            f"Target curve length {target_length:.3f} cm is shorter than its "
            f"{straight_length:.3f} cm endpoint distance."
        )

    def curve(normal_offset: float):
        return pyg.CurveEdge(
            start,
            end,
            control_points=[[control_t, normal_sign * normal_offset]],
            relative=True,
            label=label,
        )

    if target_length <= straight_length + 1.0e-6:
        return curve(0.0)

    low = 0.0
    high = 0.125
    while curve(high).length() < target_length and high < 4.0:
        high *= 2.0
    if curve(high).length() < target_length:
        raise ValueError(
            f"Target curve length {target_length:.3f} cm cannot be represented "
            "by the current princess edge."
        )
    for _ in range(48):
        middle = 0.5 * (low + high)
        if curve(middle).length() < target_length:
            low = middle
        else:
            high = middle
    result = curve(0.5 * (low + high))
    if abs(result.length() - target_length) > 1.0e-6:
        raise RuntimeError("Princess curve length solver did not converge.")
    return result


def _c1_target_length_curve_pair(
    start,
    station,
    end,
    first_target_length: float,
    second_target_length: float,
    *,
    normal_sign: float,
    first_label: str,
    second_label: str,
):
    """Build two exact-length curves with one smooth anatomical station.

    A princess line crosses the underbust before reaching the bust point. Two
    independently bowed quadratic edges can satisfy both ruler lengths while
    still making a visible cusp at their join. That cusp concentrates strain
    directly beneath the breast. These cubic edges share the same tangent at
    the station, while one independent normal offset per section preserves the
    two body-surface ruler lengths exactly.
    """

    start_point = np.asarray(start, dtype=float)
    station_point = np.asarray(station, dtype=float)
    end_point = np.asarray(end, dtype=float)
    first_chord = station_point - start_point
    second_chord = end_point - station_point
    first_chord_length = float(np.linalg.norm(first_chord))
    second_chord_length = float(np.linalg.norm(second_chord))
    if min(first_chord_length, second_chord_length) <= 1.0e-8:
        raise ValueError("A station-bound curve pair requires distinct landmarks.")
    if first_target_length < first_chord_length - 1.0e-6:
        raise ValueError(
            "Waist-to-station ruler is shorter than its flat endpoint distance."
        )
    if second_target_length < second_chord_length - 1.0e-6:
        raise ValueError(
            "Station-to-bust ruler is shorter than its flat endpoint distance."
        )

    join_vector = end_point - start_point
    join_length = float(np.linalg.norm(join_vector))
    if join_length <= 1.0e-8:
        raise ValueError("A station-bound curve pair requires a usable join tangent.")
    join_direction = join_vector / join_length

    def unit_normal(chord: np.ndarray) -> np.ndarray:
        return np.asarray([-chord[1], chord[0]], dtype=float) / float(
            np.linalg.norm(chord)
        )

    first_normal = unit_normal(first_chord) * float(normal_sign)
    second_normal = unit_normal(second_chord) * float(normal_sign)
    first_join_handle = min(first_chord_length * 0.28, join_length * 0.22)
    second_join_handle = min(second_chord_length * 0.28, join_length * 0.22)

    def first_curve(offset: float):
        return pyg.CurveEdge(
            start,
            station,
            control_points=[
                (
                    start_point
                    + first_chord * 0.32
                    + first_normal * offset
                ).tolist(),
                (station_point - join_direction * first_join_handle).tolist(),
            ],
            relative=False,
            label=first_label,
        )

    def second_curve(offset: float):
        return pyg.CurveEdge(
            station,
            end,
            control_points=[
                (station_point + join_direction * second_join_handle).tolist(),
                (
                    end_point
                    - second_chord * 0.32
                    + second_normal * offset
                ).tolist(),
            ],
            relative=False,
            label=second_label,
        )

    def fit(curve_factory, target_length: float, label: str):
        base = curve_factory(0.0)
        base_length = float(base.length())
        if target_length < base_length - 1.0e-6:
            raise ValueError(
                f"{label} ruler {target_length:.3f} cm is shorter than the "
                f"smooth station base {base_length:.3f} cm."
            )
        if target_length <= base_length + 1.0e-6:
            return base
        low = 0.0
        high = 0.125
        while curve_factory(high).length() < target_length and high < 64.0:
            high *= 2.0
        if curve_factory(high).length() < target_length:
            raise ValueError(
                f"{label} ruler cannot be represented by the smooth station curve."
            )
        for _ in range(48):
            middle = 0.5 * (low + high)
            if curve_factory(middle).length() < target_length:
                low = middle
            else:
                high = middle
        result = curve_factory(0.5 * (low + high))
        if abs(float(result.length()) - target_length) > 1.0e-6:
            raise RuntimeError(f"{label} smooth curve length solver did not converge.")
        return result

    return (
        fit(first_curve, first_target_length, first_label),
        fit(second_curve, second_target_length, second_label),
    )


def _station_bound_side_seam(
    block: dict[str, float],
    waist,
    underbust,
    upper_torso,
    underarm,
    target_lengths: tuple[float, float, float] | None = None,
):
    """Build three matched side-seam sections at anatomical body stations."""

    points = (waist, underbust, upper_torso, underarm)
    sections = (
        (
            "side_waist_to_underbust_length",
            "side_seam_waist_to_underbust",
        ),
        (
            "side_underbust_to_upper_torso_length",
            "side_seam_underbust_to_upper_torso",
        ),
        (
            "side_upper_torso_to_underarm_length",
            "side_seam_upper_torso_to_underarm",
        ),
    )
    edges = []
    for index, (key, label) in enumerate(sections):
        target = max(
            float(block[key]),
            (
                float(target_lengths[index])
                if target_lengths is not None
                else 0.0
            ),
        )
        chord = float(
            np.linalg.norm(
                np.asarray(points[index + 1], dtype=float)
                - np.asarray(points[index], dtype=float)
            )
        )
        target = max(target, chord + 1.0e-4)
        edges.append(
            _target_length_curve(
                points[index],
                points[index + 1],
                target,
                0.50,
                -1.0,
                label=label,
            )
        )
    return pyg.EdgeSequence(*edges)


def compute_cup_aware_block_measurements(body, design) -> dict[str, float]:
    """Resolve the measurements that control the production princess block.

    The GarmentCode dataset bodice infers bust shaping from shoulder balance.
    This block instead treats high bust, full bust, underbust, bust span,
    front length, back length, and armscye depth as independent drafting
    inputs. Every value can therefore be measured or manually overridden.
    """

    shirt = design["shirt"]
    full_bust = _bounded(body["bust"], 45.0, 220.0, "Full bust")
    waist = _bounded(body["waist"], 35.0, 220.0, "Waist")
    underbust = _bounded(
        shirt.get("patterna_underbust", {}).get(
            "v", _body_value(body, "underbust", full_bust * 0.86)
        ),
        35.0,
        220.0,
        "Underbust",
    )
    if underbust >= full_bust:
        raise ValueError("Underbust must be smaller than full bust for a cup-aware block.")

    chest_ease = float(
        shirt.get("patterna_chest_ease", {}).get("v", 0.0)
    )
    if not math.isfinite(chest_ease) or chest_ease < -6.0 or chest_ease > 50.0:
        raise ValueError("Chest ease must be from -6 through 50 centimeters.")

    def station_ease(key: str, default_positive_cap: float, label: str) -> float:
        default = (
            chest_ease
            if chest_ease < 0.0
            else min(chest_ease, default_positive_cap)
        )
        value = float(shirt.get(key, {}).get("v", default))
        if not math.isfinite(value) or value < -6.0 or value > 50.0:
            raise ValueError(f"{label} ease must be from -6 through 50 centimeters.")
        return value

    # A fitted cup-aware block cannot use one circumference increment at every
    # torso height. Full-bust ease supplies breathing room over the breast
    # volume, while the underbust, upper-torso, and underarm circuits need
    # their own controls. Reusing a loose 8 cm bust allowance at all four
    # stations produced an inflated barrel above the bust and an unsupported
    # shelf below it on large-cup bodies.
    underbust_ease = station_ease(
        "patterna_underbust_ease",
        1.0,
        "Underbust",
    )
    upper_torso_ease = station_ease(
        "patterna_upper_torso_ease",
        2.0,
        "Upper-torso",
    )
    underarm_ease = station_ease(
        "patterna_underarm_ease",
        3.0,
        "Underarm",
    )
    measured_full_bust = full_bust - chest_ease
    if measured_full_bust <= underbust:
        raise ValueError(
            "Measured full bust must exceed underbust before garment ease is applied."
        )
    inferred_high_bust = underbust + 0.38 * (measured_full_bust - underbust)
    measured_high_bust = _bounded(
        shirt.get("patterna_high_bust", {}).get("v", inferred_high_bust),
        40.0,
        220.0,
        "High bust",
    )
    if measured_high_bust > measured_full_bust:
        raise ValueError("High bust cannot exceed full bust.")
    drafting_high_bust = measured_high_bust + upper_torso_ease
    full_bust_horizontal_circumference = _bounded(
        _body_value(
            body,
            "patterna_full_bust_horizontal_circumference",
            measured_full_bust,
        ),
        40.0,
        240.0,
        "Full-bust horizontal collider section",
    )
    upper_torso_circumference = _bounded(
        _body_value(
            body,
            "patterna_upper_torso_circumference",
            measured_high_bust,
        ),
        40.0,
        240.0,
        "Upper-torso collider section",
    )
    underarm_circumference = _bounded(
        _body_value(
            body,
            "patterna_underarm_circumference",
            upper_torso_circumference,
        ),
        40.0,
        240.0,
        "Underarm collider section",
    )
    horizontal_section_clearance = (
        full_bust - full_bust_horizontal_circumference
    )
    drafting_upper_torso = max(
        drafting_high_bust,
        upper_torso_circumference + upper_torso_ease,
    )
    drafting_underarm = max(
        drafting_high_bust,
        underarm_circumference + underarm_ease,
    )

    back_width = _bounded(body["back_width"], 20.0, full_bust - 5.0, "Back width")
    waist_back_width = _bounded(
        body["waist_back_width"], 15.0, waist - 5.0, "Back waist width"
    )
    shoulder_width = _bounded(body["shoulder_w"], 20.0, 80.0, "Shoulder width")
    bust_span = _bounded(
        shirt.get("patterna_bust_span", {}).get("v", body["bust_points"]),
        8.0,
        45.0,
        "Bust apex span",
    )
    front_length = _bounded(
        shirt.get("patterna_front_waist_length", {}).get(
            "v", _body_value(body, "waist_over_bust_line", body["waist_line"])
        ),
        25.0,
        80.0,
        "Front waist length",
    )
    measured_back_waist_length = _bounded(
        shirt.get("patterna_back_waist_length", {}).get("v", body["waist_line"]),
        25.0,
        80.0,
        "Back waist length",
    )
    inferred_bust_height_from_waist = body["waist_line"] - body["_bust_line"]
    shoulder_to_bust = _bounded(
        shirt.get("patterna_shoulder_to_bust", {}).get(
            "v",
            _body_value(
                body,
                "bust_line",
                front_length - inferred_bust_height_from_waist,
            ),
        ),
        8.0,
        front_length - 3.0,
        "Shoulder to bust point",
    )
    bust_height_from_waist = _bounded(
        shirt.get("patterna_bust_height_from_waist", {}).get(
            "v",
            _body_value(
                body,
                "patterna_bust_height_from_waist",
                front_length - shoulder_to_bust,
            ),
        ),
        8.0,
        front_length - 8.0,
        "Bust height from waist",
    )
    bust_projection = max(
        0.0,
        shoulder_to_bust - _body_value(body, "vert_bust_line", shoulder_to_bust),
    )
    inferred_front_princess_contour = math.hypot(
        bust_height_from_waist,
        bust_projection,
    )
    front_princess_contour_length = _bounded(
        shirt.get("patterna_front_princess_contour_length", {}).get(
            "v",
            _body_value(
                body,
                "patterna_front_princess_contour_length",
                inferred_front_princess_contour,
            ),
        ),
        bust_height_from_waist,
        front_length - 1.0,
        "Front waist-to-bust princess contour",
    )
    front_princess_waist_to_underbust_length = _body_value(
        body,
        "patterna_front_princess_waist_to_underbust_length",
        math.nan,
    )
    front_princess_underbust_to_bust_length = _body_value(
        body,
        "patterna_front_princess_underbust_to_bust_length",
        math.nan,
    )
    princess_underbust_station_is_bound = all(
        math.isfinite(value) and value > 0.0
        for value in (
            front_princess_waist_to_underbust_length,
            front_princess_underbust_to_bust_length,
        )
    )
    if princess_underbust_station_is_bound:
        segment_total = (
            front_princess_waist_to_underbust_length
            + front_princess_underbust_to_bust_length
        )
        if abs(segment_total - front_princess_contour_length) > 0.05:
            raise ValueError(
                "Segmented front princess rulers must reconstruct the complete "
                "waist-to-bust surface ruler."
            )
    front_princess_upper_contour_length = _bounded(
        shirt.get("patterna_front_princess_upper_contour_length", {}).get(
            "v",
            _body_value(
                body,
                "patterna_front_princess_upper_contour_length",
                shoulder_to_bust,
            ),
        ),
        shoulder_to_bust,
        front_length - 1.0,
        "Front bust-to-shoulder princess contour",
    )
    armscye_depth_was_explicit = "patterna_armscye_depth" in shirt
    armscye_depth = _bounded(
        shirt.get("patterna_armscye_depth", {}).get(
            "v",
            _body_value(
                body,
                "patterna_requested_armhole_depth",
                body["_armscye_depth"],
            ),
        ),
        8.0,
        front_length - 8.0,
        "Armscye depth",
    )
    armscye_depth_is_estimated = (
        not armscye_depth_was_explicit
        and _body_value(body, "patterna_armhole_depth_is_estimated", 0.0) >= 0.5
    )
    armscye_was_explicit = "patterna_armscye_circumference" in shirt
    armscye_circumference = _bounded(
        shirt.get("patterna_armscye_circumference", {}).get(
            "v",
            _body_value(
                body,
                "armscye_circumference",
                armscye_depth / 0.301,
            ),
        ),
        20.0,
        100.0,
        "Armscye circumference",
    )
    armscye_is_estimated = (
        not armscye_was_explicit
        and _body_value(body, "patterna_armscye_is_estimated", 0.0) >= 0.5
    )
    front_armscye_fraction = (
        _bounded(
            _body_value(body, "patterna_front_armscye_fraction", 0.5),
            0.40,
            0.60,
            "Front armscye fraction",
        )
        if "patterna_front_armscye_fraction" in body
        else None
    )
    neck_half_width = _bounded(
        shirt.get("patterna_neck_half_width", {}).get("v", body["neck_w"] * 0.42),
        4.0,
        shoulder_width * 0.36,
        "Neck half width",
    )

    back_bust_fraction = _bounded(
        _body_value(body, "patterna_back_bust_fraction", back_width / full_bust),
        0.25,
        0.70,
        "Back bust fraction",
    )
    back_high_bust_fraction = _bounded(
        _body_value(
            body,
            "patterna_back_high_bust_tape_fraction",
            _body_value(
                body,
                "patterna_back_high_bust_fraction",
                back_bust_fraction,
            ),
        ),
        0.25,
        0.70,
        "Back high-bust tape fraction",
    )
    back_upper_torso_fraction = _bounded(
        _body_value(
            body,
            "patterna_back_upper_torso_fraction",
            _body_value(
                body,
                "patterna_back_high_bust_fraction",
                back_bust_fraction,
            ),
        ),
        0.25,
        0.70,
        "Back upper-torso fraction",
    )
    back_underarm_fraction = _bounded(
        _body_value(
            body,
            "patterna_back_underarm_fraction",
            back_upper_torso_fraction,
        ),
        0.25,
        0.70,
        "Back underarm fraction",
    )
    back_underbust_fraction = _bounded(
        _body_value(
            body,
            "patterna_back_underbust_fraction",
            back_bust_fraction,
        ),
        0.25,
        0.70,
        "Back underbust fraction",
    )
    back_waist_fraction = _bounded(
        _body_value(
            body,
            "patterna_back_waist_fraction",
            waist_back_width / waist,
        ),
        0.25,
        0.70,
        "Back waist fraction",
    )

    front_bust_half = full_bust * (1.0 - back_bust_fraction) / 2.0
    front_waist_half = (waist - waist_back_width) / 2.0
    back_bust_half = full_bust * back_bust_fraction / 2.0
    back_waist_half = waist_back_width / 2.0
    if min(front_bust_half, front_waist_half, back_bust_half, back_waist_half) <= 6.0:
        raise ValueError("Front and back drafting widths must each exceed six centimeters.")

    cup_difference = measured_full_bust - measured_high_bust
    cup_turn_angle = float(np.clip(10.0 + cup_difference * 1.35, 14.0, 34.0))
    back_upper_torso_half = (
        drafting_upper_torso * back_upper_torso_fraction / 2.0
    )
    front_upper_torso_half = (
        drafting_upper_torso - back_upper_torso_half * 2.0
    ) / 2.0
    back_underarm_half = drafting_underarm * back_underarm_fraction / 2.0
    front_underarm_half = (
        drafting_underarm - back_underarm_half * 2.0
    ) / 2.0
    back_high_bust_half = drafting_high_bust * back_high_bust_fraction / 2.0
    front_high_bust_half = (
        drafting_high_bust - back_high_bust_half * 2.0
    ) / 2.0
    back_measured_high_bust_half = (
        measured_high_bust * back_high_bust_fraction / 2.0
    )
    front_measured_high_bust_half = (
        measured_high_bust - back_measured_high_bust_half * 2.0
    ) / 2.0
    drafting_underbust = underbust + underbust_ease
    back_underbust_half = drafting_underbust * back_underbust_fraction / 2.0
    front_underbust_half = (
        drafting_underbust - back_underbust_half * 2.0
    ) / 2.0
    underbust_height_from_waist = _bounded(
        _body_value(
            body,
            "patterna_underbust_height_from_waist",
            _body_value(
                body,
                "vert_bust_line",
                bust_height_from_waist
                - float(np.clip(cup_difference * 0.45, 5.0, 10.0)),
            ),
        ),
        3.0,
        bust_height_from_waist - 1.0,
        "Underbust height from waist",
    )
    # Front and back waist lengths are independent surface rulers. Equalizing
    # them to make detached flat-panel shoulder coordinates line up added the
    # full over-bust balance to the back and created a horizontal compression
    # fold. Body-aware staging and sewing own 3D shoulder registration; the
    # pattern must preserve the entered back measurement.
    anatomical_back_length = measured_back_waist_length
    side_seam_height = _bounded(
        _body_value(
            body,
            "patterna_side_seam_height_from_waist",
            anatomical_back_length - armscye_depth,
        ),
        bust_height_from_waist + 0.5,
        anatomical_back_length - 8.0,
        "Underarm side-seam height",
    )
    upper_torso_height_from_waist = _bounded(
        _body_value(
            body,
            "patterna_upper_torso_height_from_waist",
            bust_height_from_waist
            + 0.65 * (side_seam_height - bust_height_from_waist),
        ),
        bust_height_from_waist + 0.25,
        side_seam_height - 0.25,
        "Upper-torso circuit height",
    )
    high_bust_tape_height_from_waist = _bounded(
        _body_value(
            body,
            "patterna_high_bust_tape_height_from_waist",
            side_seam_height + 4.0,
        ),
        side_seam_height + 0.25,
        front_length - 2.0,
        "High-bust tape height",
    )
    side_waist_to_underbust_length = _body_value(
        body,
        "patterna_side_waist_to_underbust_length",
        math.nan,
    )
    side_underbust_to_upper_torso_length = _body_value(
        body,
        "patterna_side_underbust_to_upper_torso_length",
        math.nan,
    )
    side_upper_torso_to_underarm_length = _body_value(
        body,
        "patterna_side_upper_torso_to_underarm_length",
        math.nan,
    )
    side_seam_stations_are_bound = all(
        math.isfinite(value) and value > 0.0
        for value in (
            side_waist_to_underbust_length,
            side_underbust_to_upper_torso_length,
            side_upper_torso_to_underarm_length,
        )
    )
    if side_seam_stations_are_bound:
        minimum_intervals = (
            underbust_height_from_waist,
            upper_torso_height_from_waist - underbust_height_from_waist,
            side_seam_height - upper_torso_height_from_waist,
        )
        for label, ruler, minimum in zip(
            (
                "Waist-to-underbust side-seam",
                "Underbust-to-upper-torso side-seam",
                "Upper-torso-to-underarm side-seam",
            ),
            (
                side_waist_to_underbust_length,
                side_underbust_to_upper_torso_length,
                side_upper_torso_to_underarm_length,
            ),
            minimum_intervals,
        ):
            if ruler < minimum - 1.0e-6:
                raise ValueError(
                    f"{label} surface ruler {ruler:.3f} cm is shorter than "
                    f"its {minimum:.3f} cm vertical station interval."
                )
    torso_station_profile = _torso_station_profile(body)
    return {
        "full_bust": full_bust,
        "high_bust": measured_high_bust,
        "drafting_high_bust": drafting_high_bust,
        "full_bust_horizontal_circumference": (
            full_bust_horizontal_circumference
        ),
        "upper_torso_circumference": upper_torso_circumference,
        "underarm_circumference": underarm_circumference,
        "horizontal_section_clearance": horizontal_section_clearance,
        "bust_ease_cm": chest_ease,
        "underbust_ease_cm": underbust_ease,
        "upper_torso_ease_cm": upper_torso_ease,
        "underarm_ease_cm": underarm_ease,
        "drafting_upper_torso": drafting_upper_torso,
        "drafting_underarm": drafting_underarm,
        "underbust": underbust,
        "drafting_underbust": drafting_underbust,
        "front_underbust_half": front_underbust_half,
        "back_underbust_half": back_underbust_half,
        "underbust_height_from_waist": underbust_height_from_waist,
        "upper_torso_height_from_waist": upper_torso_height_from_waist,
        "high_bust_height_from_waist": upper_torso_height_from_waist,
        "high_bust_tape_height_from_waist": high_bust_tape_height_from_waist,
        "cup_difference": cup_difference,
        "cup_turn_angle_deg": cup_turn_angle,
        "waist": waist,
        "front_bust_half": front_bust_half,
        "front_waist_half": front_waist_half,
        "back_bust_half": back_bust_half,
        "front_high_bust_half": front_high_bust_half,
        "back_high_bust_half": back_high_bust_half,
        "front_upper_torso_half": front_upper_torso_half,
        "back_upper_torso_half": back_upper_torso_half,
        "front_underarm_half": front_underarm_half,
        "back_underarm_half": back_underarm_half,
        "front_measured_high_bust_half": front_measured_high_bust_half,
        "back_measured_high_bust_half": back_measured_high_bust_half,
        "back_waist_half": back_waist_half,
        "back_bust_fraction": back_bust_fraction,
        "back_high_bust_fraction": back_high_bust_fraction,
        "back_upper_torso_fraction": back_upper_torso_fraction,
        "back_underarm_fraction": back_underarm_fraction,
        "back_underbust_fraction": back_underbust_fraction,
        "back_waist_fraction": back_waist_fraction,
        "shoulder_half": shoulder_width / 2.0,
        "bust_apex_half": bust_span / 2.0,
        "front_length": front_length,
        "back_length": anatomical_back_length,
        "measured_back_waist_length": measured_back_waist_length,
        "back_balance_difference": front_length - measured_back_waist_length,
        "shoulder_to_bust": shoulder_to_bust,
        "bust_height_from_waist": bust_height_from_waist,
        "front_princess_contour_length": front_princess_contour_length,
        "front_princess_waist_to_underbust_length": (
            front_princess_waist_to_underbust_length
        ),
        "front_princess_underbust_to_bust_length": (
            front_princess_underbust_to_bust_length
        ),
        "princess_underbust_station_is_bound": (
            princess_underbust_station_is_bound
        ),
        "inferred_front_princess_contour_length": inferred_front_princess_contour,
        "front_princess_upper_contour_length": (
            front_princess_upper_contour_length
        ),
        "armscye_depth": armscye_depth,
        "requested_armscye_depth": armscye_depth,
        "armscye_depth_is_estimated": armscye_depth_is_estimated,
        "estimated_armscye_depth_adjusted": False,
        "estimated_armscye_depth_adjustment_cm": 0.0,
        "torso_station_profile": torso_station_profile,
        "armscye_circumference": armscye_circumference,
        "requested_armscye_circumference": armscye_circumference,
        "armscye_is_estimated": armscye_is_estimated,
        "front_armscye_fraction": front_armscye_fraction,
        "side_seam_height": side_seam_height,
        "requested_side_seam_height": side_seam_height,
        "side_waist_to_underbust_length": side_waist_to_underbust_length,
        "side_underbust_to_upper_torso_length": (
            side_underbust_to_upper_torso_length
        ),
        "side_upper_torso_to_underarm_length": (
            side_upper_torso_to_underarm_length
        ),
        "side_seam_stations_are_bound": side_seam_stations_are_bound,
        "neck_half_width": neck_half_width,
        "shoulder_drop": math.tan(math.radians(body["_shoulder_incl"]))
        * (shoulder_width / 2.0 - neck_half_width),
        # The prepared MPFB body hard-fits frontWaistLength as its nape-to-waist
        # ruler. backWaistLength controls the back pattern balance, but it does
        # not locate the body's waist plane. Using it here staged the complete
        # garment about five centimeters above the fitted anatomical waist.
        "waist_level_world": _body_value(
            body,
            "patterna_waist_level_world",
            body["height"] - body["head_l"] - front_length,
        ),
        "front_depth_sign": _body_value(
            body,
            "patterna_front_depth_sign",
            1.0,
        ),
        "front_staging_depth_cm": _body_value(
            body,
            "patterna_front_staging_depth_cm",
            20.0,
        ),
        "back_staging_depth_cm": _body_value(
            body,
            "patterna_back_staging_depth_cm",
            -max(
                14.0,
                full_bust_horizontal_circumference / (2.0 * math.pi),
            )
            - 2.0,
        ),
    }


def _point_from_angle(start, length: float, angle_deg: float) -> list[float]:
    angle = math.radians(angle_deg)
    return [
        float(start[0] + length * math.cos(angle)),
        float(start[1] + length * math.sin(angle)),
    ]


def _curve_point_at_y(edge, target_y: float) -> list[float]:
    """Return the point on a monotonic panel curve at an anatomical Y station."""

    curve = edge.as_curve()
    start_y = float(curve.point(0.0).imag)
    end_y = float(curve.point(1.0).imag)
    lower = min(start_y, end_y)
    upper = max(start_y, end_y)
    if target_y < lower - 1.0e-6 or target_y > upper + 1.0e-6:
        raise ValueError(
            f"Curve does not cross the requested Y station {target_y:.3f} cm."
        )
    increasing = end_y >= start_y
    low_t = 0.0
    high_t = 1.0
    for _ in range(60):
        middle_t = 0.5 * (low_t + high_t)
        middle_y = float(curve.point(middle_t).imag)
        if (middle_y < target_y) == increasing:
            low_t = middle_t
        else:
            high_t = middle_t
    point = curve.point(0.5 * (low_t + high_t))
    return [float(point.real), float(point.imag)]


def _quadratic_curve_through_station(
    start,
    end,
    station,
    *,
    label: str,
):
    """Construct a monotonic quadratic edge that passes through a body station."""

    start_point = np.asarray(start, dtype=float)
    end_point = np.asarray(end, dtype=float)
    station_point = np.asarray(station, dtype=float)
    height = end_point[1] - start_point[1]
    if abs(height) <= 1.0e-8:
        raise ValueError("A measurement station requires a non-horizontal edge.")
    station_t = (station_point[1] - start_point[1]) / height
    if station_t <= 0.02 or station_t >= 0.98:
        raise ValueError("A measurement station must lie inside its boundary edge.")
    denominator = 2.0 * (1.0 - station_t) * station_t
    control = (
        station_point
        - (1.0 - station_t) ** 2 * start_point
        - station_t**2 * end_point
    ) / denominator
    return pyg.CurveEdge(
        start,
        end,
        control_points=[control.tolist()],
        relative=False,
        label=label,
    )


def _cubic_curve_through_station_with_target_length(
    start,
    end,
    station,
    target_length: float,
    *,
    label: str,
    normal_sign: float,
):
    """Lengthen a station-locked boundary without moving its measurements."""

    base = _quadratic_curve_through_station(
        start,
        end,
        station,
        label=label,
    )
    base_length = float(base.length())
    if target_length < base_length - 1.0e-6:
        raise ValueError(
            f"Target station-locked edge length {target_length:.3f} cm is "
            f"shorter than its measured base curve {base_length:.3f} cm."
        )
    if target_length <= base_length + 1.0e-6:
        return base

    start_point = np.asarray(start, dtype=float)
    end_point = np.asarray(end, dtype=float)
    station_point = np.asarray(station, dtype=float)
    station_t = (station_point[1] - start_point[1]) / (
        end_point[1] - start_point[1]
    )
    denominator = 2.0 * (1.0 - station_t) * station_t
    quadratic_control = (
        station_point
        - (1.0 - station_t) ** 2 * start_point
        - station_t**2 * end_point
    ) / denominator
    first_control = start_point + (2.0 / 3.0) * (
        quadratic_control - start_point
    )
    second_control = end_point + (2.0 / 3.0) * (
        quadratic_control - end_point
    )
    first_weight = 3.0 * (1.0 - station_t) ** 2 * station_t
    second_weight = 3.0 * (1.0 - station_t) * station_t**2
    compensation = first_weight / second_weight

    def curve(offset: float):
        first = first_control.copy()
        second = second_control.copy()
        first[0] += normal_sign * offset
        second[0] -= normal_sign * offset * compensation
        return pyg.CurveEdge(
            start,
            end,
            control_points=[first.tolist(), second.tolist()],
            relative=False,
            label=label,
        )

    low = 0.0
    high = 0.125
    while curve(high).length() < target_length and high < 64.0:
        high *= 2.0
    if curve(high).length() < target_length:
        raise ValueError(
            f"Target station-locked edge length {target_length:.3f} cm cannot "
            "be represented without moving a measurement landmark."
        )
    for _ in range(48):
        middle = 0.5 * (low + high)
        if curve(middle).length() < target_length:
            low = middle
        else:
            high = middle
    result = curve(0.5 * (low + high))
    reconstructed_station = _curve_point_at_y(result, station_point[1])
    if np.linalg.norm(np.asarray(reconstructed_station) - station_point) > 1.0e-6:
        raise RuntimeError("Station-locked side seam moved its measurement point.")
    if abs(result.length() - target_length) > 1.0e-6:
        raise RuntimeError("Station-locked side-seam length solver did not converge.")
    return result


class _PrincessPanel(pyg.Panel):
    def _place(self, x: float, y: float, z: float, yaw_deg: float = 0.0):
        self.translate_to([x, y, z])
        if yaw_deg:
            self.rotate_by(R.from_euler("XYZ", [0.0, yaw_deg, 0.0], degrees=True))
        return self


class PatternaPrincessFrontCenterPanel(_PrincessPanel):
    def __init__(self, name: str, block: dict[str, float]) -> None:
        super().__init__(name, label="body")
        apex_x = block["bust_apex_half"]
        bust_y = block["bust_height_from_waist"]
        shoulder_y = block["front_length"] - block["shoulder_drop"] * 0.45
        waist_x = max(4.5, apex_x * 0.78)
        shoulder_x = min(block["shoulder_half"] - 2.5, apex_x * 1.23)
        neck_x = block["neck_half_width"]
        neck_y = block["front_length"] - max(6.5, block["front_length"] * 0.18)

        p_cf_waist = [0.0, 0.0]
        p_waist = [waist_x, 0.0]
        p_underbust = [apex_x, block["underbust_height_from_waist"]]
        p_bust = [apex_x, bust_y]
        p_shoulder = [shoulder_x, shoulder_y]
        p_neck_shoulder = [neck_x, block["front_length"]]
        p_cf_neck = [0.0, neck_y]

        self.bottom = pyg.Edge(p_cf_waist, p_waist, label="hem")
        if block["princess_underbust_station_is_bound"]:
            (
                self.princess_waist_to_underbust,
                self.princess_underbust_to_bust,
            ) = _c1_target_length_curve_pair(
                self.bottom.end,
                p_underbust,
                p_bust,
                block["front_princess_waist_to_underbust_length"],
                block["front_princess_underbust_to_bust_length"],
                normal_sign=1.0,
                first_label="princess_front_waist_to_underbust",
                second_label="princess_front_underbust_to_bust",
            )
            self.princess_lower = pyg.EdgeSequence(
                self.princess_waist_to_underbust,
                self.princess_underbust_to_bust,
            )
            lower_end = self.princess_underbust_to_bust.end
            self.underbust_point = self.princess_waist_to_underbust.end
        else:
            legacy_lower = _target_length_curve(
                self.bottom.end,
                p_bust,
                block["front_princess_contour_length"],
                0.42,
                1.0,
                label="princess_front_lower",
            )
            self.princess_lower = pyg.EdgeSequence(legacy_lower)
            self.princess_waist_to_underbust = None
            self.princess_underbust_to_bust = None
            self.underbust_point = _curve_point_at_y(
                legacy_lower,
                block["underbust_height_from_waist"],
            )
            lower_end = legacy_lower.end
        self.princess_upper = _target_length_curve(
            lower_end,
            p_shoulder,
            block["front_princess_upper_contour_length"],
            0.50,
            1.0,
            label="princess_front_upper",
        )
        self.shoulder = pyg.Edge(self.princess_upper.end, p_neck_shoulder, label="shoulder")
        self.neckline = pyg.CurveEdge(
            self.shoulder.end,
            p_cf_neck,
            control_points=[[0.62, 0.22]],
            relative=True,
            label="strapless_top",
        )
        self.center = pyg.Edge(self.neckline.end, p_cf_waist, label="center_front")
        self.edges = pyg.EdgeSequence(
            self.bottom,
            self.princess_lower,
            self.princess_upper,
            self.shoulder,
            self.neckline,
            self.center,
        )
        self.interfaces = {
            "bottom": pyg.Interface(self, self.bottom),
            "princess": pyg.Interface(
                self, pyg.EdgeSequence(self.princess_lower, self.princess_upper)
            ),
            "shoulder": pyg.Interface(self, self.shoulder),
            "neckline": pyg.Interface(self, self.neckline),
            "center": pyg.Interface(self, self.center),
        }
        self.princess_lengths = (
            self.princess_lower.length(),
            self.princess_upper.length(),
        )
        self.princess_segment_lengths = (
            (
                self.princess_waist_to_underbust.length(),
                self.princess_underbust_to_bust.length(),
                self.princess_upper.length(),
            )
            if self.princess_waist_to_underbust is not None
            else self.princess_lengths
        )


class PatternaPrincessFrontSidePanel(_PrincessPanel):
    def __init__(
        self,
        name: str,
        block: dict[str, float],
        princess_lengths: tuple[float, ...],
        front_center_circuit_x: tuple[float, float],
        target_side_length: float | None = None,
        armhole_scoop_depth: float = 0.22,
        armhole_dart_intake_cm: float = 0.0,
        rotate_armhole_dart_to_princess: bool = True,
        permit_longer_side_seam: bool = False,
        target_side_segment_lengths: tuple[float, float, float] | None = None,
    ) -> None:
        super().__init__(name, label="body")
        segmented_underbust = len(princess_lengths) == 3
        if segmented_underbust:
            waist_to_underbust_len, underbust_to_bust_len, upper_len = (
                princess_lengths
            )
            lower_len = waist_to_underbust_len + underbust_to_bust_len
        else:
            lower_len, upper_len = princess_lengths
            waist_to_underbust_len = math.nan
            underbust_to_bust_len = math.nan
        cup_turn = block["cup_turn_angle_deg"]
        waist_inner = [0.0, 0.0]
        waist_width = block["front_waist_half"] - block["bust_apex_half"] * 0.78
        # This coordinate is a panel width from the local princess seam, not a
        # body-space X coordinate. Coupling it to the absolute underarm X made
        # the waist grow whenever bust projection grew.
        side_waist = [waist_width, 0.0]
        underbust_y = block["underbust_height_from_waist"]
        if segmented_underbust:
            center_underbust = [block["bust_apex_half"], underbust_y]
        else:
            center_lower = _target_length_curve(
                [max(4.5, block["bust_apex_half"] * 0.78), 0.0],
                [block["bust_apex_half"], block["bust_height_from_waist"]],
                lower_len,
                0.42,
                1.0,
            )
            center_underbust = _curve_point_at_y(center_lower, underbust_y)

        def lower_princess_segments(bust_point):
            if not segmented_underbust:
                edge = _target_length_curve(
                    bust_point,
                    waist_inner,
                    lower_len,
                    0.58,
                    -1.0,
                    label="princess_front_lower",
                )
                return pyg.EdgeSequence(edge), _curve_point_at_y(edge, underbust_y)
            bust_y = block["bust_height_from_waist"]
            underbust_inner = [
                bust_point[0] * underbust_y / bust_y,
                underbust_y,
            ]
            waist_edge_ascending, cup_edge_ascending = _c1_target_length_curve_pair(
                waist_inner,
                underbust_inner,
                bust_point,
                waist_to_underbust_len,
                underbust_to_bust_len,
                normal_sign=1.0,
                first_label="princess_front_waist_to_underbust",
                second_label="princess_front_underbust_to_bust",
            )
            cup_edge = cup_edge_ascending.reverse()
            waist_edge = waist_edge_ascending.reverse()
            return pyg.EdgeSequence(cup_edge, waist_edge), underbust_inner

        def geometry(angle_deg: float):
            bust_y = block["bust_height_from_waist"]
            bust_inner = [
                bust_y / math.tan(math.radians(angle_deg)),
                bust_y,
            ]
            shoulder_angle = math.radians(78.0 + cup_turn)
            shoulder_y = (
                block["front_length"] - block["shoulder_drop"] * 0.45
            )
            shoulder_inner = [
                bust_inner[0]
                + (shoulder_y - bust_inner[1]) / math.tan(shoulder_angle),
                shoulder_y,
            ]
            shoulder_outer_x = shoulder_inner[0] + max(
                5.0,
                block["shoulder_half"]
                - block["neck_half_width"]
                - (block["bust_apex_half"] * 1.23 - block["neck_half_width"]),
            )
            shoulder_outer = [
                shoulder_outer_x,
                shoulder_inner[1] - block["shoulder_drop"] * 0.55,
            ]
            side_princess_upper = _target_length_curve(
                shoulder_inner,
                bust_inner,
                upper_len,
                0.50,
                -1.0,
            )
            upper_torso_y = block["upper_torso_height_from_waist"]
            side_princess_upper_torso = _curve_point_at_y(
                side_princess_upper,
                upper_torso_y,
            )
            side_princess_underarm = _curve_point_at_y(
                side_princess_upper,
                block["side_seam_height"],
            )
            high_bust_outer = [
                side_princess_upper_torso[0]
                + block["front_upper_torso_half"]
                - front_center_circuit_x[0],
                upper_torso_y,
            ]
            underarm = [
                side_princess_underarm[0]
                + block["front_underarm_half"]
                - front_center_circuit_x[1],
                block["side_seam_height"],
            ]
            if segmented_underbust:
                side_underbust = [
                    bust_inner[0] * underbust_y / bust_y,
                    underbust_y,
                ]
            else:
                _, side_underbust = lower_princess_segments(bust_inner)
            underbust_outer_x = side_underbust[0] + (
                block["front_underbust_half"] - center_underbust[0]
            )
            side_underbust_outer = [underbust_outer_x, underbust_y]
            if block["side_seam_stations_are_bound"]:
                side_edges = _station_bound_side_seam(
                    block,
                    side_waist,
                    side_underbust_outer,
                    high_bust_outer,
                    underarm,
                    target_side_segment_lengths,
                )
            else:
                side_lower = _quadratic_curve_through_station(
                    side_waist,
                    high_bust_outer,
                    side_underbust_outer,
                    label="side_seam",
                )
                side_upper = pyg.Edge(
                    side_lower.end,
                    underarm,
                    label="side_seam_upper",
                )
                side_edges = pyg.EdgeSequence(side_lower, side_upper)
            return (
                bust_inner,
                shoulder_inner,
                shoulder_outer,
                underarm,
                side_edges,
                side_underbust_outer,
            )

        angle_deg = 88.0
        if target_side_length is not None and not block["side_seam_stations_are_bound"]:
            default_error = (
                geometry(angle_deg)[4].length()
                - target_side_length
            )
            if abs(default_error) > 1.0e-6:
                samples = np.linspace(60.0, 120.0, 241)
                errors: list[float] = []
                for angle in samples:
                    try:
                        error = (
                            geometry(float(angle))[4].length()
                            - target_side_length
                        )
                    except ValueError:
                        error = math.nan
                    errors.append(error)
                bracket = next(
                    (
                        (float(samples[index]), float(samples[index + 1]))
                        for index in range(len(samples) - 1)
                        if math.isfinite(errors[index])
                        and math.isfinite(errors[index + 1])
                        and (
                            errors[index] == 0.0
                            or errors[index] * errors[index + 1] <= 0.0
                        )
                    ),
                    None,
                )
                if bracket is None:
                    finite_indices = [
                        index
                        for index, error in enumerate(errors)
                        if math.isfinite(error)
                    ]
                    if not finite_indices:
                        raise RuntimeError(
                            "No valid princess orientation preserves its contour length."
                        )
                    best_index = min(
                        finite_indices,
                        key=lambda index: abs(errors[index]),
                    )
                    nearest = abs(errors[best_index])
                    if not permit_longer_side_seam or errors[best_index] < 0.0:
                        raise RuntimeError(
                            "No front princess orientation preserves the body-bound "
                            "upper circuits and the matched side seam; nearest "
                            f"side-seam residual is {nearest:.3f} centimeters."
                        )
                    angle_deg = float(samples[best_index])
                else:
                    low, high = bracket
                    low_error = (
                        geometry(low)[4].length()
                        - target_side_length
                    )
                    for _ in range(40):
                        middle = 0.5 * (low + high)
                        middle_error = (
                            geometry(middle)[4].length()
                            - target_side_length
                        )
                        if low_error * middle_error <= 0.0:
                            high = middle
                        else:
                            low = middle
                            low_error = middle_error
                    angle_deg = 0.5 * (low + high)

        (
            bust_inner,
            shoulder_inner,
            shoulder_outer,
            underarm,
            self.side,
            self.side_underbust_point,
        ) = geometry(angle_deg)
        if block["side_seam_stations_are_bound"]:
            self.side_waist_to_underbust = self.side[0]
            self.side_underbust_to_upper_torso = self.side[1]
            self.side_upper_torso_to_underarm = self.side[2]
            self.side_lower = pyg.EdgeSequence(
                self.side_waist_to_underbust,
                self.side_underbust_to_upper_torso,
            )
            self.side_upper = self.side_upper_torso_to_underarm
        else:
            self.side_lower = self.side[0]
            self.side_upper = self.side[1]
            self.side_waist_to_underbust = None
            self.side_underbust_to_upper_torso = None
            self.side_upper_torso_to_underarm = None
        effective_target_side_length = target_side_length
        if target_side_length is not None and not block["side_seam_stations_are_bound"]:
            side_residual = self.side.length() - target_side_length
            if abs(side_residual) > 0.08 and not (
                permit_longer_side_seam and side_residual > 0.0
            ):
                raise RuntimeError(
                    "Front and back side seams cannot be matched without moving "
                    "a body-bound circuit endpoint; residual is "
                    f"{side_residual:.3f} centimeters."
                )
            if permit_longer_side_seam and side_residual > 0.0:
                effective_target_side_length = (
                    self.side.length()
                )

        self.bottom = pyg.Edge(waist_inner, side_waist, label="hem")
        self.high_bust_outer = self.side_upper.start
        self.armhole = pyg.CurveEdge(
            self.side_upper.end,
            shoulder_outer,
            control_points=[
                # For an underarm-to-shoulder edge, positive relative Y bends
                # toward the bodice interior. The previous negative controls
                # bowed outside the torso and produced a literal cap-sleeve
                # flap even when the measured armscye length was exact.
                [0.37, armhole_scoop_depth],
                [0.76, armhole_scoop_depth * 0.45],
            ],
            relative=True,
            label="armhole_front",
        )
        self.armhole_boundary = pyg.EdgeSequence(self.armhole)
        self.armhole_interface_edges = pyg.EdgeSequence(self.armhole)
        self.armhole_dart_intake_cm = float(armhole_dart_intake_cm)
        self.armhole_dart_depth_cm = 0.0
        self.armhole_transfer_depth_cm = 0.0
        self.armhole_dart_offset_cm = 0.0
        self.armhole_dart_rotated_to_princess = False
        if self.armhole_dart_intake_cm > 1.0e-6:
            armhole_length = float(self.armhole.length())
            if self.armhole_dart_intake_cm >= armhole_length * 0.45:
                raise ValueError(
                    "Front armhole dart intake cannot consume nearly half the opening."
                )
            self.armhole_dart_depth_cm = float(
                np.clip(
                    # The dart point must stop before the bust apex. A deeper
                    # fixed proportion crossed the side-front princess seam on
                    # large-cup blocks and produced a self-intersecting panel.
                    block["shoulder_to_bust"] * 0.35,
                    8.0,
                    armhole_length * 0.32,
                )
            )
            self.armhole_dart_offset_cm = float(
                np.clip(
                    armhole_length * 0.44,
                    self.armhole_dart_intake_cm * 0.5 + 1.0,
                    armhole_length - self.armhole_dart_intake_cm * 0.5 - 1.0,
                )
            )
            if rotate_armhole_dart_to_princess:
                (
                    dart_boundary,
                    dart_edges,
                    dart_interface_edges,
                ) = pyg.ops.cut_into_edge(
                    pyg.EdgeSeqFactory.dart_shape(
                        self.armhole_dart_intake_cm,
                        depth=self.armhole_dart_depth_cm,
                    ),
                    self.armhole,
                    offset=self.armhole_dart_offset_cm,
                    right=False,
                )
                if (
                    len(dart_boundary) != 4
                    or len(dart_edges) != 2
                    or len(dart_interface_edges) != 2
                ):
                    raise RuntimeError(
                        "Armhole dart transfer produced unexpected topology."
                    )

                # Close the temporary armhole dart geometrically, then put its
                # suppression into the existing princess boundary. Leaving the
                # dart legs in the physical mesh created a bulky folded tuck
                # under the arm. A shoulder-princess block instead rotates that
                # intake into the princess seam before the fabric is cut.
                lower_armhole = dart_interface_edges[0]
                upper_armhole = dart_interface_edges[1]
                first_base = np.asarray(dart_edges[0].start, dtype=float)
                dart_apex = np.asarray(dart_edges[0].end, dtype=float)
                second_base = np.asarray(dart_edges[1].end, dtype=float)
                first_vector = first_base - dart_apex
                second_vector = second_base - dart_apex
                close_angle = math.atan2(
                    first_vector[1], first_vector[0]
                ) - math.atan2(second_vector[1], second_vector[0])
                cosine = math.cos(close_angle)
                sine = math.sin(close_angle)

                def rotate_about_apex(point) -> None:
                    relative = np.asarray(point, dtype=float) - dart_apex
                    rotated = np.asarray(
                        [
                            cosine * relative[0] - sine * relative[1],
                            sine * relative[0] + cosine * relative[1],
                        ]
                    )
                    point[:] = (dart_apex + rotated).tolist()

                original_shoulder_vector = (
                    np.asarray(shoulder_inner, dtype=float)
                    - np.asarray(shoulder_outer, dtype=float)
                )
                rotate_about_apex(upper_armhole.start)
                rotate_about_apex(upper_armhole.end)
                upper_armhole.start[:] = lower_armhole.end
                shoulder_inner[:] = (
                    np.asarray(upper_armhole.end, dtype=float)
                    + original_shoulder_vector
                ).tolist()
                lower_armhole.label = "armhole_front"
                upper_armhole.label = "armhole_front"
                self.armhole_boundary = pyg.EdgeSequence(
                    lower_armhole,
                    upper_armhole,
                )
                self.armhole_interface_edges = self.armhole_boundary
                self.armhole = self.armhole_boundary
                self.armhole_dart_rotated_to_princess = True
                self.armhole_transfer_depth_cm = self.armhole_dart_depth_cm
                self.armhole_dart_depth_cm = 0.0
            else:
                (
                    self.armhole_boundary,
                    self.armhole_interface_edges,
                ) = self.add_dart(
                    pyg.EdgeSeqFactory.dart_shape(
                        self.armhole_dart_intake_cm,
                        depth=self.armhole_dart_depth_cm,
                    ),
                    self.armhole,
                    offset=self.armhole_dart_offset_cm,
                    right=False,
                )
                interface_edge_ids = {
                    id(edge) for edge in self.armhole_interface_edges
                }
                for edge in self.armhole_boundary:
                    edge.label = (
                        "armhole_front"
                        if id(edge) in interface_edge_ids
                        else "armhole_dart"
                    )
        self.shoulder = pyg.Edge(
            self.armhole_boundary[-1].end,
            shoulder_inner,
            label="shoulder",
        )
        self.princess_upper = _target_length_curve(
            self.shoulder.end,
            bust_inner,
            upper_len,
            0.50,
            -1.0,
            label="princess_front_upper",
        )
        self.princess_lower, self.underbust_point = lower_princess_segments(
            self.princess_upper.end
        )
        if segmented_underbust:
            self.princess_underbust_to_bust = self.princess_lower[0]
            self.princess_waist_to_underbust = self.princess_lower[1]
        else:
            self.princess_underbust_to_bust = None
            self.princess_waist_to_underbust = None
        if self.armhole_dart_rotated_to_princess:
            # Rotating the intake moves the side-panel princess edge. Rebuild
            # the outer circuit from the new princess landmarks so full-bust
            # shaping does not silently add width at upper torso or underarm.
            final_upper_torso_inner = _curve_point_at_y(
                self.princess_upper,
                block["upper_torso_height_from_waist"],
            )
            final_underarm_inner = _curve_point_at_y(
                self.princess_upper,
                block["side_seam_height"],
            )
            final_underbust_inner = self.underbust_point
            final_high_bust_outer = [
                final_upper_torso_inner[0]
                + block["front_upper_torso_half"]
                - front_center_circuit_x[0],
                block["upper_torso_height_from_waist"],
            ]
            final_underarm = [
                final_underarm_inner[0]
                + block["front_underarm_half"]
                - front_center_circuit_x[1],
                block["side_seam_height"],
            ]
            final_underbust_outer = [
                final_underbust_inner[0]
                + block["front_underbust_half"]
                - center_underbust[0],
                underbust_y,
            ]
            self.armhole_boundary[0].start[:] = final_underarm
            if block["side_seam_stations_are_bound"]:
                self.side = _station_bound_side_seam(
                    block,
                    side_waist,
                    final_underbust_outer,
                    final_high_bust_outer,
                    self.armhole_boundary[0].start,
                    target_side_segment_lengths,
                )
                self.side_waist_to_underbust = self.side[0]
                self.side_underbust_to_upper_torso = self.side[1]
                self.side_upper_torso_to_underarm = self.side[2]
                self.side_lower = pyg.EdgeSequence(
                    self.side_waist_to_underbust,
                    self.side_underbust_to_upper_torso,
                )
                self.side_upper = self.side_upper_torso_to_underarm
            else:
                self.side_upper = pyg.Edge(
                    final_high_bust_outer,
                    self.armhole_boundary[0].start,
                    label="side_seam_upper",
                )
                self.side_lower = _quadratic_curve_through_station(
                    side_waist,
                    final_high_bust_outer,
                    final_underbust_outer,
                    label="side_seam",
                )
                if effective_target_side_length is not None:
                    target_lower_length = (
                        effective_target_side_length - self.side_upper.length()
                    )
                    base_lower_length = self.side_lower.length()
                    if target_lower_length >= base_lower_length - 1.0e-6:
                        self.side_lower = (
                            _cubic_curve_through_station_with_target_length(
                                side_waist,
                                final_high_bust_outer,
                                final_underbust_outer,
                                target_lower_length,
                                label="side_seam",
                                normal_sign=-1.0,
                            )
                        )
                    elif not (
                        permit_longer_side_seam
                        and base_lower_length - target_lower_length <= 0.08
                    ):
                        raise ValueError(
                            "Transferred princess shaping cannot preserve the side "
                            "seam within 0.08 centimeters."
                        )
                self.side = pyg.EdgeSequence(self.side_lower, self.side_upper)
            self.side_underbust_point = final_underbust_outer
            self.high_bust_outer = self.side_upper.start
        self.edges = pyg.EdgeSequence(
            self.bottom,
            self.side,
            self.armhole_boundary,
            self.shoulder,
            self.princess_upper,
            self.princess_lower,
        )
        self.interfaces = {
            "bottom": pyg.Interface(self, self.bottom),
            "side": pyg.Interface(self, self.side),
            "armhole": pyg.Interface(self, self.armhole_interface_edges),
            "shoulder": pyg.Interface(self, self.shoulder),
            "princess": pyg.Interface(
                self,
                (
                    pyg.EdgeSequence(
                        self.princess_waist_to_underbust,
                        self.princess_underbust_to_bust,
                        self.princess_upper,
                    )
                    if segmented_underbust
                    else pyg.EdgeSequence(
                        self.princess_lower,
                        self.princess_upper,
                    )
                ),
            ),
        }
        self.princess_segment_lengths = (
            (
                self.princess_waist_to_underbust.length(),
                self.princess_underbust_to_bust.length(),
                self.princess_upper.length(),
            )
            if segmented_underbust
            else (self.princess_lower.length(), self.princess_upper.length())
        )
        self.side_segment_lengths = tuple(
            float(edge.length()) for edge in self.side
        )


class PatternaPrincessBackCenterPanel(_PrincessPanel):
    def __init__(
        self,
        name: str,
        block: dict[str, float],
        center_shoulder_length_cm: float | None = None,
    ) -> None:
        super().__init__(name, label="body")
        waist_x = block["back_waist_half"] * 0.43
        underbust_x = block["back_underbust_half"] * 0.44
        blade_x = block["back_upper_torso_half"] * 0.48
        shoulder_run = block["shoulder_half"] - block["neck_half_width"]
        shoulder_length = math.hypot(shoulder_run, block["shoulder_drop"])
        shoulder_fraction = (
            0.58
            if center_shoulder_length_cm is None
            else float(center_shoulder_length_cm) / shoulder_length
        )
        if shoulder_fraction <= 0.20 or shoulder_fraction >= 0.80:
            raise ValueError(
                "Back princess shoulder split must leave usable center and side seams."
            )
        shoulder_x = block["neck_half_width"] + shoulder_run * shoulder_fraction
        shoulder_y = block["back_length"] - block["shoulder_drop"] * shoulder_fraction
        neck_x = block["neck_half_width"]
        neck_y = block["back_length"] - max(1.8, block["back_length"] * 0.05)
        blade_y = block["upper_torso_height_from_waist"]

        p_cb_waist = [0.0, 0.0]
        p_waist = [waist_x, 0.0]
        p_blade = [blade_x, blade_y]
        p_shoulder = [shoulder_x, shoulder_y]
        p_neck_shoulder = [neck_x, block["back_length"]]
        p_cb_neck = [0.0, neck_y]

        self.bottom = pyg.Edge(p_cb_waist, p_waist, label="hem")
        self.princess_lower = _quadratic_curve_through_station(
            self.bottom.end,
            p_blade,
            [underbust_x, block["underbust_height_from_waist"]],
            label="princess_back_lower",
        )
        self.princess_upper = pyg.CurveEdge(
            self.princess_lower.end,
            p_shoulder,
            control_points=[[0.52, 0.035]],
            relative=True,
            label="princess_back_upper",
        )
        self.shoulder = pyg.Edge(self.princess_upper.end, p_neck_shoulder, label="shoulder")
        self.neckline = pyg.CurveEdge(
            self.shoulder.end,
            p_cb_neck,
            control_points=[[0.52, 0.10]],
            relative=True,
            label="strapless_top",
        )
        self.center = pyg.Edge(self.neckline.end, p_cb_waist, label="center_back")
        self.edges = pyg.EdgeSequence(
            self.bottom,
            self.princess_lower,
            self.princess_upper,
            self.shoulder,
            self.neckline,
            self.center,
        )
        self.interfaces = {
            "bottom": pyg.Interface(self, self.bottom),
            "princess": pyg.Interface(
                self, pyg.EdgeSequence(self.princess_lower, self.princess_upper)
            ),
            "shoulder": pyg.Interface(self, self.shoulder),
            "neckline": pyg.Interface(self, self.neckline),
            "center": pyg.Interface(self, self.center),
        }
        self.princess_lengths = (
            self.princess_lower.length(),
            self.princess_upper.length(),
        )
        self.shoulder_fraction = shoulder_fraction


class PatternaPrincessBackSidePanel(_PrincessPanel):
    def __init__(
        self,
        name: str,
        block: dict[str, float],
        center_panel: PatternaPrincessBackCenterPanel,
        armhole_scoop_depth: float = 0.22,
        target_side_length: float | None = None,
        target_side_segment_lengths: tuple[float, float, float] | None = None,
    ) -> None:
        super().__init__(name, label="body")
        lower_len, upper_len = center_panel.princess_lengths
        waist_inner = [0.0, 0.0]
        blade_y = block["upper_torso_height_from_waist"]
        shoulder_y = (
            block["back_length"]
            - block["shoulder_drop"] * center_panel.shoulder_fraction
        )
        blade_inner = [0.65, blade_y]
        shoulder_inner = [1.20, shoulder_y]
        self.princess_upper = _target_length_curve(
            shoulder_inner,
            blade_inner,
            upper_len,
            0.48,
            -1.0,
            label="princess_back_upper",
        )
        self.princess_lower = _target_length_curve(
            self.princess_upper.end,
            waist_inner,
            lower_len,
            0.52,
            -1.0,
            label="princess_back_lower",
        )

        def center_seam_x(station_y: float) -> float:
            edge = (
                center_panel.princess_lower
                if station_y <= blade_y + 1.0e-6
                else center_panel.princess_upper
            )
            return _curve_point_at_y(edge, station_y)[0]

        def side_seam_x(station_y: float) -> float:
            edge = (
                self.princess_lower
                if station_y <= blade_y + 1.0e-6
                else self.princess_upper
            )
            return _curve_point_at_y(edge, station_y)[0]

        def local_outer_x(station_y: float, back_half_width: float) -> float:
            return side_seam_x(station_y) + back_half_width - center_seam_x(station_y)

        underbust_y = block["underbust_height_from_waist"]
        underarm_y = block["side_seam_height"]
        side_waist = [
            local_outer_x(0.0, block["back_waist_half"]),
            0.0,
        ]
        high_bust_outer = [
            local_outer_x(blade_y, block["back_upper_torso_half"]),
            blade_y,
        ]
        underarm = [
            local_outer_x(underarm_y, block["back_underarm_half"]),
            underarm_y,
        ]
        shoulder_run = block["shoulder_half"] - block["neck_half_width"]
        shoulder_outer = [
            shoulder_inner[0]
            + shoulder_run * (1.0 - center_panel.shoulder_fraction),
            block["back_length"] - block["shoulder_drop"],
        ]

        self.bottom = pyg.Edge(waist_inner, side_waist, label="hem")
        self.side_underbust_point = [
            local_outer_x(underbust_y, block["back_underbust_half"]),
            underbust_y,
        ]
        if block["side_seam_stations_are_bound"]:
            self.side = _station_bound_side_seam(
                block,
                self.bottom.end,
                self.side_underbust_point,
                high_bust_outer,
                underarm,
                target_side_segment_lengths,
            )
            self.side_waist_to_underbust = self.side[0]
            self.side_underbust_to_upper_torso = self.side[1]
            self.side_upper_torso_to_underarm = self.side[2]
            self.side_lower = pyg.EdgeSequence(
                self.side_waist_to_underbust,
                self.side_underbust_to_upper_torso,
            )
            self.side_upper = self.side_upper_torso_to_underarm
        else:
            self.side_lower = _quadratic_curve_through_station(
                self.bottom.end,
                high_bust_outer,
                self.side_underbust_point,
                label="side_seam",
            )
            self.side_upper = pyg.Edge(
                self.side_lower.end,
                underarm,
                label="side_seam_upper",
            )
            if target_side_length is not None:
                target_lower_length = target_side_length - self.side_upper.length()
                self.side_lower = _cubic_curve_through_station_with_target_length(
                    self.bottom.end,
                    high_bust_outer,
                    self.side_underbust_point,
                    target_lower_length,
                    label="side_seam",
                    normal_sign=-1.0,
                )
            self.side = pyg.EdgeSequence(self.side_lower, self.side_upper)
            self.side_waist_to_underbust = None
            self.side_underbust_to_upper_torso = None
            self.side_upper_torso_to_underarm = None
        self.high_bust_outer = self.side_upper.start
        self.armhole = pyg.CurveEdge(
            self.side_upper.end,
            shoulder_outer,
            control_points=[
                [0.36, armhole_scoop_depth],
                [0.78, armhole_scoop_depth * 0.47],
            ],
            relative=True,
            label="armhole_back",
        )
        self.shoulder = pyg.Edge(self.armhole.end, shoulder_inner, label="shoulder")
        self.edges = pyg.EdgeSequence(
            self.bottom,
            self.side,
            self.armhole,
            self.shoulder,
            self.princess_upper,
            self.princess_lower,
        )
        self.interfaces = {
            "bottom": pyg.Interface(self, self.bottom),
            "side": pyg.Interface(self, self.side),
            "armhole": pyg.Interface(self, self.armhole),
            "shoulder": pyg.Interface(self, self.shoulder),
            "princess": pyg.Interface(
                self, pyg.EdgeSequence(self.princess_lower, self.princess_upper)
            ),
        }
        self.side_segment_lengths = tuple(
            float(edge.length()) for edge in self.side
        )


class PatternaPrincessBackHalfPanel(_PrincessPanel):
    """A stable shaped back paired with the cup-aware front princess panels."""

    def __init__(
        self,
        name: str,
        block: dict[str, float],
        armhole_scoop_depth: float = 0.22,
        target_side_length: float | None = None,
        shoulder_dart_intake_cm: float = 0.0,
    ) -> None:
        super().__init__(name, label="body")
        p_cb_waist = [0.0, 0.0]
        p_side_waist = [block["back_waist_half"], 0.0]
        self.shoulder_dart_intake_cm = float(shoulder_dart_intake_cm)
        shoulder_drop = float(block["shoulder_drop"])
        base_shoulder_run = float(
            block["shoulder_half"] - block["neck_half_width"]
        )
        base_shoulder_length = math.hypot(base_shoulder_run, shoulder_drop)
        raw_shoulder_length = base_shoulder_length + self.shoulder_dart_intake_cm
        raw_shoulder_run = math.sqrt(
            max(raw_shoulder_length * raw_shoulder_length - shoulder_drop * shoulder_drop, 0.0)
        )
        p_shoulder = [
            block["neck_half_width"] + raw_shoulder_run,
            block["back_length"] - block["shoulder_drop"],
        ]
        p_neck_shoulder = [block["neck_half_width"], block["back_length"]]
        p_cb_neck = [0.0, block["back_length"] - max(1.8, block["back_length"] * 0.05)]

        self.bottom = pyg.Edge(p_cb_waist, p_side_waist, label="hem")
        p_high_bust = [
            block["back_upper_torso_half"],
            block["upper_torso_height_from_waist"],
        ]
        p_underarm = [
            block["back_underarm_half"],
            block["side_seam_height"],
        ]
        base_side_lower = _quadratic_curve_through_station(
            self.bottom.end,
            p_high_bust,
            [block["back_underbust_half"], block["underbust_height_from_waist"]],
            label="side_seam",
        )
        self.side_upper = pyg.Edge(
            base_side_lower.end,
            p_underarm,
            label="side_seam_upper",
        )
        self.side_lower = base_side_lower
        if target_side_length is not None:
            target_lower_length = target_side_length - self.side_upper.length()
            self.side_lower = _cubic_curve_through_station_with_target_length(
                self.bottom.end,
                p_high_bust,
                [
                    block["back_underbust_half"],
                    block["underbust_height_from_waist"],
                ],
                target_lower_length,
                label="side_seam",
                normal_sign=-1.0,
            )
        self.side = pyg.EdgeSequence(self.side_lower, self.side_upper)
        self.high_bust_outer = self.side_upper.start
        self.armhole = pyg.CurveEdge(
            self.side_upper.end,
            p_shoulder,
            control_points=[
                # This edge also runs from underarm to shoulder, so positive
                # relative Y is the anatomical inward scoop.
                [0.36, armhole_scoop_depth],
                [0.77, armhole_scoop_depth * 0.47],
            ],
            relative=True,
            label="armhole_back",
        )
        self.shoulder = pyg.Edge(self.armhole.end, p_neck_shoulder, label="shoulder")
        self.shoulder_boundary = pyg.EdgeSequence(self.shoulder)
        self.shoulder_interface_edges = pyg.EdgeSequence(self.shoulder)
        self.shoulder_dart_depth_cm = 0.0
        self.shoulder_dart_offset_cm = 0.0
        if self.shoulder_dart_intake_cm > 1.0e-6:
            self.shoulder_dart_depth_cm = float(
                np.clip(block["back_length"] * 0.20, 6.0, 10.0)
            )
            self.shoulder_dart_offset_cm = raw_shoulder_length * 0.56
            (
                self.shoulder_boundary,
                self.shoulder_interface_edges,
            ) = self.add_dart(
                pyg.EdgeSeqFactory.dart_shape(
                    self.shoulder_dart_intake_cm,
                    depth=self.shoulder_dart_depth_cm,
                ),
                self.shoulder,
                offset=self.shoulder_dart_offset_cm,
                right=False,
            )
            interface_edge_ids = {
                id(edge) for edge in self.shoulder_interface_edges
            }
            for edge in self.shoulder_boundary:
                edge.label = (
                    "shoulder"
                    if id(edge) in interface_edge_ids
                    else "back_shoulder_dart"
                )
        self.neckline = pyg.CurveEdge(
            self.shoulder.end,
            p_cb_neck,
            control_points=[[0.52, 0.10]],
            relative=True,
            label="strapless_top",
        )
        self.center = pyg.Edge(self.neckline.end, p_cb_waist, label="center_back")
        self.edges = pyg.EdgeSequence(
            self.bottom,
            self.side_lower,
            self.side_upper,
            self.armhole,
            self.shoulder_boundary,
            self.neckline,
            self.center,
        )
        self.interfaces = {
            "bottom": pyg.Interface(self, self.bottom),
            "side": pyg.Interface(self, self.side),
            "armhole": pyg.Interface(self, self.armhole),
            "shoulder": pyg.Interface(self, self.shoulder_interface_edges),
            "neckline": pyg.Interface(self, self.neckline),
            "center": pyg.Interface(self, self.center),
        }


def _assert_matched_interface(interface_a, interface_b, name: str, tolerance: float = 0.08):
    length_a = float(interface_a.edges.length())
    length_b = float(interface_b.edges.length())
    if abs(length_a - length_b) > tolerance:
        raise RuntimeError(
            f"{name} interfaces differ by {abs(length_a - length_b):.3f} centimeters."
        )


class PatternaFittedShortSleeve(pyg.Component):
    """GarmentCode sleeve panels with caps fitted to the authored armholes."""

    def __init__(
        self,
        prefix: str,
        body,
        design,
        front_armhole_length_cm: float,
        back_armhole_length_cm: float,
    ) -> None:
        super().__init__(f"{prefix}_short_sleeve")
        sleeve_design = design["sleeve"]
        cap_run_cm = 12.0
        cap_width_cm = 15.0

        def cap(target_length: float, label: str):
            return pyg.EdgeSequence(
                _target_length_curve(
                    [0.0, 0.0],
                    [cap_run_cm, cap_width_cm],
                    target_length,
                    0.50,
                    -1.0,
                    label=label,
                )
            )

        self.front = SleevePanel(
            f"{prefix}_sleeve_front",
            body,
            sleeve_design,
            cap(front_armhole_length_cm, "armhole_front"),
        ).translate_by([0.0, 0.0, 15.0])
        self.back = SleevePanel(
            f"{prefix}_sleeve_back",
            body,
            sleeve_design,
            cap(back_armhole_length_cm, "armhole_back"),
        ).translate_by([0.0, 0.0, -15.0])
        self.set_panel_label("arm")
        _assert_matched_interface(
            self.front.interfaces["top"],
            self.back.interfaces["top"],
            "Sleeve upper seam",
        )
        _assert_matched_interface(
            self.front.interfaces["bottom"],
            self.back.interfaces["bottom"],
            "Sleeve underarm seam",
        )
        self.stitching_rules = pyg.Stitches(
            (self.front.interfaces["top"], self.back.interfaces["top"]),
            (self.front.interfaces["bottom"], self.back.interfaces["bottom"]),
        )
        self.interfaces = {
            "front_cap": self.front.interfaces["in"],
            "back_cap": self.back.interfaces["in"],
            "cuff": pyg.Interface.from_multiple(
                self.front.interfaces["out"],
                self.back.interfaces["out"],
            ),
        }


class PatternaPrincessBodiceHalf(pyg.Component):
    def __init__(
        self,
        prefix: str,
        block: dict[str, float],
        body,
        design,
        mirrored: bool = False,
    ) -> None:
        super().__init__(prefix)
        waist_level = block["waist_level_world"]
        # Stage detached panels beyond the fullest supported-bust surface. The
        # previous narrow offset was only collision-clean while the garment
        # was incorrectly placed above that surface. Correct anatomical waist
        # registration puts the side-front panels beside the actual bust, so
        # the rigid dressing pose needs proportional radial clearance.
        staging_offset = float(np.clip(block["full_bust"] * 0.085, 6.0, 12.0))
        # These are pre-rotation depths. The completed symmetric bodice is
        # rotated 180 degrees below to preserve semantic left and right names.
        front_base_depth = -float(block["front_staging_depth_cm"])
        back_base_depth = -float(block["back_staging_depth_cm"])
        front_pre_sign = 1.0 if front_base_depth >= 0.0 else -1.0
        back_pre_sign = 1.0 if back_base_depth >= 0.0 else -1.0
        self.front_center = PatternaPrincessFrontCenterPanel(
            f"{prefix}_front_center", block
        )._place(0.0, waist_level, front_base_depth)
        block["back_shaping_topology"] = "center-and-side-princess-seam"
        block["back_shoulder_dart_intake_cm"] = 0.0

        def armhole_panels(
            front_scoop_depth: float,
            dart_intake_cm: float = 0.0,
            rotate_dart_to_princess: bool = True,
            back_scoop_depth: float | None = None,
        ):
            if back_scoop_depth is None:
                back_scoop_depth = front_scoop_depth
            front_center_circuit_x = (
                _curve_point_at_y(
                    self.front_center.princess_upper,
                    block["upper_torso_height_from_waist"],
                )[0],
                _curve_point_at_y(
                    self.front_center.princess_upper,
                    block["side_seam_height"],
                )[0],
            )
            back_center = PatternaPrincessBackCenterPanel(
                f"{prefix}_back_center",
                block,
                center_shoulder_length_cm=float(
                    self.front_center.interfaces["shoulder"].edges.length()
                ),
            )._place(0.0, waist_level, back_base_depth)
            back_probe = PatternaPrincessBackSidePanel(
                f"{prefix}_back_side",
                block,
                back_center,
                armhole_scoop_depth=back_scoop_depth,
            )._place(0.0, waist_level, back_base_depth, yaw_deg=65.0)
            front_side = PatternaPrincessFrontSidePanel(
                f"{prefix}_front_side",
                block,
                self.front_center.princess_segment_lengths,
                front_center_circuit_x,
                target_side_length=(
                    None
                    if block["side_seam_stations_are_bound"]
                    else back_probe.interfaces["side"].edges.length()
                ),
                armhole_scoop_depth=front_scoop_depth,
                armhole_dart_intake_cm=dart_intake_cm,
                rotate_armhole_dart_to_princess=rotate_dart_to_princess,
                permit_longer_side_seam=True,
                target_side_segment_lengths=(
                    back_probe.side_segment_lengths
                    if block["side_seam_stations_are_bound"]
                    else None
                ),
            )._place(0.0, waist_level, front_base_depth, yaw_deg=-75.0)
            target_side_length = max(
                float(back_probe.interfaces["side"].edges.length()),
                float(front_side.interfaces["side"].edges.length()),
            )
            back_side = PatternaPrincessBackSidePanel(
                f"{prefix}_back_side",
                block,
                back_center,
                armhole_scoop_depth=back_scoop_depth,
                target_side_length=(
                    None
                    if block["side_seam_stations_are_bound"]
                    else target_side_length
                ),
                target_side_segment_lengths=(
                    tuple(
                        max(back_value, front_value)
                        for back_value, front_value in zip(
                            back_probe.side_segment_lengths,
                            front_side.side_segment_lengths,
                        )
                    )
                    if block["side_seam_stations_are_bound"]
                    else None
                ),
            )._place(0.0, waist_level, back_base_depth, yaw_deg=65.0)
            total = float(
                front_side.interfaces["armhole"].edges.length()
                + back_side.interfaces["armhole"].edges.length()
            )
            return back_center, back_side, front_side, total

        body_armscye = float(block["armscye_circumference"])
        mobility_ease_cm = 1.5
        target_armscye = body_armscye + mobility_ease_cm
        # Armhole shape is an anatomical construction constraint, not a spare
        # degree of freedom for forcing body-tape circumference onto the flat
        # pattern. The panel classes use 0.22 as their fitted block shape. A
        # shallower minimum produced a nearly straight opening that stood away
        # from the shoulder blade like a cap sleeve. Preserve the fitted shape
        # and expose any remaining perimeter difference as construction ease.
        minimum_scoop = 0.22
        maximum_scoop = 1.50
        _, _, _, minimum_length = armhole_panels(minimum_scoop)
        _, _, _, maximum_length = armhole_panels(maximum_scoop)
        block["minimum_representable_armscye_circumference"] = minimum_length
        block["maximum_representable_armscye_circumference"] = maximum_length
        block["minimum_anatomical_armhole_scoop"] = minimum_scoop
        block["armscye_mobility_ease_cm"] = mobility_ease_cm
        armhole_dart_intake = 0.0
        rotate_armhole_dart_to_princess = True
        armhole_shaping_method = "anatomical-scoop"
        if (
            block["front_armscye_fraction"] is None
            and target_armscye < minimum_length
        ):
            # A large-cup shoulder-princess block carries bust volume into the
            # side-front panel. Convert the perimeter mismatch into a sewn
            # shaping dart while preserving the anatomical underarm, shoulder,
            # princess contour, and inward armhole. An estimated editable
            # measurement remains a drafting input. Silently enlarging it to
            # the unshaped panel minimum left several centimeters of loose
            # fabric hanging from the axilla.
            def solve_intake(rotate_to_princess: bool) -> float | None:
                low_intake = 0.0
                high_intake = min(8.0, minimum_length - target_armscye + 2.0)
                shortest_length = math.inf
                while high_intake > 0.05:
                    try:
                        _, _, _, shortest_length = armhole_panels(
                            minimum_scoop,
                            high_intake,
                            rotate_to_princess,
                        )
                        break
                    except (RuntimeError, ValueError):
                        # Large princess rotations can make the measured side
                        # circuit impossible. Back off before choosing the
                        # explicit physical-dart construction fallback.
                        high_intake *= 0.90
                if shortest_length > target_armscye + 0.01:
                    return None
                for _ in range(32):
                    middle_intake = 0.5 * (low_intake + high_intake)
                    try:
                        _, _, _, finished_length = armhole_panels(
                            minimum_scoop,
                            middle_intake,
                            rotate_to_princess,
                        )
                    except (RuntimeError, ValueError):
                        high_intake = middle_intake
                        continue
                    if finished_length > target_armscye:
                        low_intake = middle_intake
                    else:
                        high_intake = middle_intake
                return 0.5 * (low_intake + high_intake)

            transferred_intake = solve_intake(True)
            if transferred_intake is not None:
                armhole_dart_intake = transferred_intake
                armhole_shaping_method = "princess-transfer"
            else:
                physical_intake = solve_intake(False)
                if physical_intake is None:
                    raise RuntimeError(
                        "Armscye suppression cannot preserve the measured torso "
                        "circuits as either a princess transfer or a physical "
                        "armhole dart."
                    )
                armhole_dart_intake = physical_intake
                rotate_armhole_dart_to_princess = False
                armhole_shaping_method = "physical-armhole-dart"
        elif (
            block["front_armscye_fraction"] is None
            and target_armscye > maximum_length
        ):
            if not block["armscye_is_estimated"]:
                raise RuntimeError(
                    "Measured armscye cannot be represented by the current fitted "
                    f"block: target {target_armscye:.3f} cm, range "
                    f"{minimum_length:.3f} through {maximum_length:.3f} cm."
                )
            target_armscye = maximum_length
        block["effective_armscye_circumference"] = target_armscye
        block["armscye_measurement_role"] = "body-measurement-with-construction-ease"
        block["armscye_construction_ease_cm"] = mobility_ease_cm
        block["armhole_dart_intake_cm"] = armhole_dart_intake
        block["armhole_shaping_method"] = armhole_shaping_method
        block["underarm_landmark_preserved"] = True
        block["estimated_armscye_adjusted"] = (
            abs(
                target_armscye
                - (
                    block["requested_armscye_circumference"]
                    + mobility_ease_cm
                )
            )
            > 1.0e-6
        )
        armhole_scoop = minimum_scoop
        back_armhole_scoop = minimum_scoop
        if (
            block["front_armscye_fraction"] is None
            and armhole_dart_intake <= 1.0e-6
        ):
            low = minimum_scoop
            high = maximum_scoop
            for _ in range(40):
                middle = 0.5 * (low + high)
                _, _, _, length = armhole_panels(middle)
                if length < target_armscye:
                    low = middle
                else:
                    high = middle
            armhole_scoop = 0.5 * (low + high)
            back_armhole_scoop = armhole_scoop

        front_armscye_fraction = block["front_armscye_fraction"]
        if front_armscye_fraction is not None:
            target_front_armscye = target_armscye * front_armscye_fraction
            target_back_armscye = target_armscye - target_front_armscye

            def panel_lengths(
                front_scoop: float,
                back_scoop: float,
                intake: float = 0.0,
                rotate_to_princess: bool = True,
            ) -> tuple[float, float]:
                _, back_panel, front_panel, _ = armhole_panels(
                    front_scoop,
                    intake,
                    rotate_to_princess,
                    back_scoop,
                )
                return (
                    float(front_panel.interfaces["armhole"].edges.length()),
                    float(back_panel.interfaces["armhole"].edges.length()),
                )

            _, minimum_back_length = panel_lengths(
                minimum_scoop,
                minimum_scoop,
            )
            _, maximum_back_length = panel_lengths(
                minimum_scoop,
                maximum_scoop,
            )
            if not (
                minimum_back_length - 0.01
                <= target_back_armscye
                <= maximum_back_length + 0.01
            ):
                raise RuntimeError(
                    "Mesh-derived back armscye target cannot be represented by "
                    "the current anatomical scoop range."
                )
            low_back = minimum_scoop
            high_back = maximum_scoop
            for _ in range(36):
                middle_back = 0.5 * (low_back + high_back)
                _, back_length = panel_lengths(
                    minimum_scoop,
                    middle_back,
                )
                if back_length < target_back_armscye:
                    low_back = middle_back
                else:
                    high_back = middle_back
            back_armhole_scoop = 0.5 * (low_back + high_back)

            minimum_front_length, _ = panel_lengths(
                minimum_scoop,
                back_armhole_scoop,
            )
            if target_front_armscye <= minimum_front_length + 0.01:
                def solve_front_intake(
                    rotate_to_princess: bool,
                ) -> float | None:
                    low_intake = 0.0
                    high_intake = min(
                        8.0,
                        minimum_front_length - target_front_armscye + 2.0,
                    )
                    shortest_front = math.inf
                    while high_intake > 0.05:
                        try:
                            shortest_front, _ = panel_lengths(
                                minimum_scoop,
                                back_armhole_scoop,
                                high_intake,
                                rotate_to_princess,
                            )
                            break
                        except (RuntimeError, ValueError):
                            high_intake *= 0.90
                    if shortest_front > target_front_armscye + 0.01:
                        return None
                    for _ in range(32):
                        middle_intake = 0.5 * (low_intake + high_intake)
                        try:
                            front_length, _ = panel_lengths(
                                minimum_scoop,
                                back_armhole_scoop,
                                middle_intake,
                                rotate_to_princess,
                            )
                        except (RuntimeError, ValueError):
                            high_intake = middle_intake
                            continue
                        if front_length > target_front_armscye:
                            low_intake = middle_intake
                        else:
                            high_intake = middle_intake
                    return 0.5 * (low_intake + high_intake)

                transferred_intake = solve_front_intake(True)
                if transferred_intake is not None:
                    armhole_dart_intake = transferred_intake
                    armhole_shaping_method = "body-balanced-princess-transfer"
                else:
                    physical_intake = solve_front_intake(False)
                    if physical_intake is None:
                        raise RuntimeError(
                            "Mesh-derived front armscye target cannot be "
                            "constructed as a princess transfer or physical dart."
                        )
                    armhole_dart_intake = physical_intake
                    rotate_armhole_dart_to_princess = False
                    armhole_shaping_method = "body-balanced-physical-armhole-dart"
            else:
                maximum_front_length, _ = panel_lengths(
                    maximum_scoop,
                    back_armhole_scoop,
                )
                if target_front_armscye > maximum_front_length + 0.01:
                    raise RuntimeError(
                        "Mesh-derived front armscye target exceeds the current "
                        "anatomical scoop range."
                    )
                low_front = minimum_scoop
                high_front = maximum_scoop
                for _ in range(36):
                    middle_front = 0.5 * (low_front + high_front)
                    front_length, _ = panel_lengths(
                        middle_front,
                        back_armhole_scoop,
                    )
                    if front_length < target_front_armscye:
                        low_front = middle_front
                    else:
                        high_front = middle_front
                armhole_scoop = 0.5 * (low_front + high_front)
                armhole_shaping_method = "body-balanced-anatomical-scoop"

            block["target_front_armscye_cm"] = target_front_armscye
            block["target_back_armscye_cm"] = target_back_armscye
        block["armhole_dart_intake_cm"] = armhole_dart_intake
        block["armhole_shaping_method"] = armhole_shaping_method
        (
            self.back_center,
            self.back_side,
            self.front_side,
            drafted_armscye,
        ) = armhole_panels(
            armhole_scoop,
            armhole_dart_intake,
            rotate_armhole_dart_to_princess,
            back_armhole_scoop,
        )
        block["armhole_scoop_depth"] = armhole_scoop
        block["back_armhole_scoop_depth"] = back_armhole_scoop
        block["armhole_dart_depth_cm"] = self.front_side.armhole_dart_depth_cm
        block["armhole_transfer_depth_cm"] = (
            self.front_side.armhole_transfer_depth_cm
        )
        block["armhole_dart_offset_cm"] = self.front_side.armhole_dart_offset_cm
        block["armhole_dart_rotated_to_princess"] = (
            self.front_side.armhole_dart_rotated_to_princess
        )
        block["back_shoulder_dart_depth_cm"] = 0.0
        block["back_shoulder_dart_offset_cm"] = 0.0
        block["drafted_armscye_circumference"] = drafted_armscye
        block["drafted_front_armscye_cm"] = float(
            self.front_side.interfaces["armhole"].edges.length()
        )
        block["drafted_back_armscye_cm"] = float(
            self.back_side.interfaces["armhole"].edges.length()
        )
        underbust_y = block["underbust_height_from_waist"]
        center_underbust = self.front_center.underbust_point
        side_princess_underbust = self.front_side.underbust_point
        side_outer_underbust = self.front_side.side_underbust_point
        back_outer_underbust = self.back_side.side_underbust_point
        back_inner_underbust = _curve_point_at_y(
            self.back_side.princess_lower,
            underbust_y,
        )
        back_center_underbust = _curve_point_at_y(
            self.back_center.princess_lower,
            underbust_y,
        )
        drafted_front_underbust_half = center_underbust[0] + abs(
            side_outer_underbust[0] - side_princess_underbust[0]
        )
        drafted_underbust = 2.0 * (
            drafted_front_underbust_half
            + abs(back_center_underbust[0])
            + abs(back_outer_underbust[0] - back_inner_underbust[0])
        )
        block["drafted_front_underbust_half"] = drafted_front_underbust_half
        block["drafted_back_underbust_half"] = (
            abs(back_center_underbust[0])
            + abs(back_outer_underbust[0] - back_inner_underbust[0])
        )
        block["drafted_underbust_circumference"] = drafted_underbust
        if abs(drafted_underbust - block["drafting_underbust"]) > 0.01:
            raise RuntimeError(
                "Drafted underbust does not reproduce the measured station: "
                f"target {block['drafting_underbust']:.3f} cm, got "
                f"{drafted_underbust:.3f} cm."
            )

        def drafted_circuit(
            station_y: float,
            front_outer_edge,
            back_outer_edge,
            back_inner_edge,
            back_center_edge,
        ) -> float:
            center_front_x = _curve_point_at_y(
                self.front_center.princess_upper,
                station_y,
            )[0]
            side_front_inner_x = _curve_point_at_y(
                self.front_side.princess_upper,
                station_y,
            )[0]
            side_front_outer_x = _curve_point_at_y(
                front_outer_edge,
                station_y,
            )[0]
            back_outer_x = _curve_point_at_y(
                back_outer_edge,
                station_y,
            )[0]
            back_inner_x = _curve_point_at_y(
                back_inner_edge,
                station_y,
            )[0]
            back_center_x = _curve_point_at_y(
                back_center_edge,
                station_y,
            )[0]
            front_half = abs(center_front_x) + abs(
                side_front_outer_x - side_front_inner_x
            )
            back_half = abs(back_center_x) + abs(back_outer_x - back_inner_x)
            return 2.0 * (front_half + back_half)

        drafted_upper_torso = drafted_circuit(
            block["upper_torso_height_from_waist"],
            (
                self.front_side.side_underbust_to_upper_torso
                if block["side_seam_stations_are_bound"]
                else self.front_side.side_lower
            ),
            (
                self.back_side.side_underbust_to_upper_torso
                if block["side_seam_stations_are_bound"]
                else self.back_side.side_lower
            ),
            self.back_side.princess_lower,
            self.back_center.princess_lower,
        )
        drafted_underarm = drafted_circuit(
            block["side_seam_height"],
            self.front_side.side_upper,
            self.back_side.side_upper,
            self.back_side.princess_upper,
            self.back_center.princess_upper,
        )
        block["drafted_upper_torso_circumference"] = drafted_upper_torso
        block["drafted_underarm_circumference"] = drafted_underarm
        for label, drafted, target in (
            (
                "upper-torso",
                drafted_upper_torso,
                block["drafting_upper_torso"],
            ),
            ("underarm", drafted_underarm, block["drafting_underarm"]),
        ):
            if abs(drafted - target) > 0.01:
                raise RuntimeError(
                    f"Drafted {label} circuit does not reproduce its collider-bound "
                    f"target: target {target:.3f} cm, got {drafted:.3f} cm."
                )
        self.front_side.place_by_interface(
            self.front_side.interfaces["princess"],
            self.front_center.interfaces["princess"],
            gap=1.5,
            gap_dir=np.array([-1.0, 0.0, 0.25 * front_pre_sign]),
        )
        # Keep the detached side-front panel in the front-side quadrant. A
        # mostly lateral offset placed the anatomically lowered panel inside
        # the avatar's A-pose upper arm even though it cleared the torso.
        front_angle = math.radians(25.0)
        front_bounds = self.front_side.bbox3D()
        front_nearest_signed_depth = (
            float(front_bounds[0][2])
            if front_pre_sign > 0.0
            else -float(front_bounds[1][2])
        )
        front_depth_shift = max(
            staging_offset * math.cos(front_angle),
            abs(front_base_depth) + 2.0 - front_nearest_signed_depth,
        )
        self.front_side.translate_by(
            [
                front_depth_shift * math.tan(front_angle),
                0.0,
                front_pre_sign * front_depth_shift,
            ]
        )
        self.back_side.place_by_interface(
            self.back_side.interfaces["princess"],
            self.back_center.interfaces["princess"],
            gap=1.5,
            gap_dir=np.array([1.0, 0.0, 0.25 * back_pre_sign]),
        )
        back_angle = math.radians(35.0)
        back_bounds = self.back_side.bbox3D()
        back_nearest_signed_depth = (
            float(back_bounds[0][2])
            if back_pre_sign > 0.0
            else -float(back_bounds[1][2])
        )
        back_depth_shift = max(
            staging_offset * math.cos(back_angle),
            abs(back_base_depth) + 2.0 - back_nearest_signed_depth,
        )
        self.back_side.translate_by(
            [
                back_depth_shift * math.tan(back_angle),
                0.0,
                back_pre_sign * back_depth_shift,
            ]
        )

        # BoxMesh reverses an ordinary stitch when it discretizes the two
        # boundaries. The two-section princess interfaces already run in
        # opposite edge order, so another reversal pairs waist to bust. Mark
        # only the princess interfaces right_wrong to preserve their authored
        # waist-to-waist and bust-to-bust correspondence. Side and shoulder
        # interfaces retain GarmentCode's default reversal.
        self.front_center.interfaces["princess"].set_right_wrong(True)
        self.back_center.interfaces["princess"].set_right_wrong(True)

        _assert_matched_interface(
            self.front_center.interfaces["princess"],
            self.front_side.interfaces["princess"],
            "Front princess seam",
        )
        _assert_matched_interface(
            self.back_center.interfaces["princess"],
            self.back_side.interfaces["princess"],
            "Back princess seam",
        )
        _assert_matched_interface(
            self.front_side.interfaces["side"],
            self.back_side.interfaces["side"],
            "Side seam",
        )
        _assert_matched_interface(
            self.front_center.interfaces["shoulder"],
            self.back_center.interfaces["shoulder"],
            "Center shoulder seam",
        )
        _assert_matched_interface(
            self.front_side.interfaces["shoulder"],
            self.back_side.interfaces["shoulder"],
            "Side shoulder seam",
        )

        stitching_rules = [
            (
                self.front_center.interfaces["princess"],
                self.front_side.interfaces["princess"],
            ),
            (
                self.back_center.interfaces["princess"],
                self.back_side.interfaces["princess"],
            ),
            (
                self.front_center.interfaces["shoulder"],
                self.back_center.interfaces["shoulder"],
            ),
            (
                self.front_side.interfaces["shoulder"],
                self.back_side.interfaces["shoulder"],
            ),
            (
                self.front_side.interfaces["side"],
                self.back_side.interfaces["side"],
            ),
        ]
        self.sleeve = None
        if not bool(design["sleeve"]["sleeveless"]["v"]):
            self.sleeve = PatternaFittedShortSleeve(
                prefix,
                body,
                design,
                float(self.front_side.interfaces["armhole"].edges.length()),
                float(self.back_side.interfaces["armhole"].edges.length()),
            )
            _assert_matched_interface(
                self.front_side.interfaces["armhole"],
                self.sleeve.interfaces["front_cap"],
                "Front sleeve cap",
            )
            _assert_matched_interface(
                self.back_side.interfaces["armhole"],
                self.sleeve.interfaces["back_cap"],
                "Back sleeve cap",
            )
            stitching_rules.extend(
                [
                    (
                        self.front_side.interfaces["armhole"],
                        self.sleeve.interfaces["front_cap"],
                    ),
                    (
                        self.back_side.interfaces["armhole"],
                        self.sleeve.interfaces["back_cap"],
                    ),
                ]
            )
            block["sleeve_topology"] = "garmentcode-two-panel-fitted-cap"
            block["sleeve_front_cap_length_cm"] = float(
                self.sleeve.interfaces["front_cap"].edges.length()
            )
            block["sleeve_back_cap_length_cm"] = float(
                self.sleeve.interfaces["back_cap"].edges.length()
            )
        else:
            block["sleeve_topology"] = "sleeveless"
        self.stitching_rules = pyg.Stitches(*stitching_rules)
        self.interfaces = {
            "front_center": self.front_center.interfaces["center"],
            "back_center": self.back_center.interfaces["center"],
            "bottom": pyg.Interface.from_multiple(
                self.front_center.interfaces["bottom"],
                self.front_side.interfaces["bottom"],
                self.back_side.interfaces["bottom"],
                self.back_center.interfaces["bottom"],
            ),
        }
        if mirrored:
            self.mirror()


class PatternaPrincessBodice(pyg.Component):
    """Cup-aware princess block with fitted GarmentCode sleeve construction."""

    def __init__(self, body, design) -> None:
        super().__init__("PatternaPrincessBodice")
        self.block = compute_cup_aware_block_measurements(body, design)
        # GarmentCode's base half is drawn on positive X. Build the semantic
        # right half on the temporary left side, then rotate the symmetric
        # assembly 180 degrees around the world vertical axis. Signed staging
        # depths supplied by the body adapter determine anatomical front and
        # back without assuming one avatar library's coordinate convention.
        self.right = PatternaPrincessBodiceHalf(
            "right",
            self.block,
            body,
            design,
            mirrored=True,
        )
        self.left = PatternaPrincessBodiceHalf(
            "left",
            self.block,
            body,
            design,
        )
        self.stitching_rules = pyg.Stitches(
            (self.right.interfaces["front_center"], self.left.interfaces["front_center"]),
            (self.right.interfaces["back_center"], self.left.interfaces["back_center"]),
        )
        self.interfaces = {
            "bottom": pyg.Interface.from_multiple(
                self.right.interfaces["bottom"], self.left.interfaces["bottom"]
            )
        }
        world_rotation = R.from_euler("XYZ", [0.0, 180.0, 0.0], degrees=True)
        pivot = np.asarray(self.pivot_3D(), dtype=float)
        self.rotate_by(world_rotation)
        self.translate_by(world_rotation.apply(pivot) - pivot)

    def drafting_metadata(self) -> dict[str, float]:
        return copy.deepcopy(self.block)
