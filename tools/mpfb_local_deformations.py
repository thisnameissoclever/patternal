"""Bounded local deformations for Patterna measurements without MPFB targets.

MPFB detail targets handle named anatomical shape changes and MPFB rulers gate
the dimensions they can measure exactly. This module supplies a third, explicit
lane for posture, asymmetric surface shape, and redundant garment landmarks.
It deforms only the exported evaluated coordinates, so the original MPFB asset
and stable hm08 topology remain unchanged.
"""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Sequence


@dataclass(frozen=True)
class LocalDeformationSpec:
    name: str
    source_key: str
    default: float
    minimum: float
    maximum: float
    kind: str
    z_center: float
    z_radius: float
    max_amount: float
    side: int = 0
    pivot_z: float = 0.0
    min_abs_x: float = 0.0
    max_abs_x: float = 1.0


@dataclass(frozen=True)
class EvaluatedLocalDeformation:
    name: str
    source_key: str
    requested: float
    normalized_delta: float
    kind: str
    affected_vertex_count: int
    maximum_displacement_cm: float


def _spec(
    name: str,
    source_key: str,
    default: float,
    minimum: float,
    maximum: float,
    kind: str,
    z_center: float,
    z_radius: float,
    max_amount: float,
    *,
    side: int = 0,
    pivot_z: float = 0.0,
    min_abs_x: float = 0.0,
    max_abs_x: float = 1.0,
) -> LocalDeformationSpec:
    return LocalDeformationSpec(
        name,
        source_key,
        default,
        minimum,
        maximum,
        kind,
        z_center,
        z_radius,
        max_amount,
        side,
        pivot_z,
        min_abs_x,
        max_abs_x,
    )


# z values, pivots, and x limits are fractions of standing height. Translation
# amounts are meters at a normalized delta of one. Rotation amounts are radians
# and vertical scale amounts are dimensionless fractions.
LOCAL_DEFORMATION_SPECS: tuple[LocalDeformationSpec, ...] = (
    _spec("front-hip-arc", "frontHipArc", 47.6, 28, 82, "front_y", 0.54, 0.09, 0.025, max_abs_x=0.18),
    _spec("back-hip-arc", "backHipArc", 51.4, 30, 88, "back_y", 0.54, 0.09, 0.025, max_abs_x=0.18),
    _spec("back-neck-to-waist", "backNeckWaist", 40.6, 25, 62, "vertical_scale", 0.70, 0.18, 0.045, pivot_z=0.54, max_abs_x=0.20),
    _spec("front-rise", "frontRise", 30.8, 19, 48, "front_z", 0.50, 0.10, 0.018, max_abs_x=0.15),
    _spec("back-rise", "backRise", 39.6, 25, 62, "back_z", 0.50, 0.10, 0.018, max_abs_x=0.15),
    _spec("crotch-depth", "crotchDepth", 25.1, 16, 40, "translate_z", 0.47, 0.07, -0.018, max_abs_x=0.14),
    _spec("crotch-length", "crotchLength", 70.4, 48, 105, "radial_y", 0.49, 0.08, 0.018, max_abs_x=0.15),
    _spec("left-foot-angle", "footAngleL", 4.0, -25, 35, "axial_rotate", 0.035, 0.055, math.radians(18), side=-1, pivot_z=0.035),
    _spec("right-foot-angle", "footAngleR", 4.0, -25, 35, "axial_rotate", 0.035, 0.055, math.radians(18), side=1, pivot_z=0.035),
    _spec("left-heel-girth", "heelGirthL", 31.8, 22, 45, "radial_y", 0.045, 0.055, 0.010, side=-1),
    _spec("right-heel-girth", "heelGirthR", 31.8, 22, 45, "radial_y", 0.045, 0.055, 0.010, side=1),
    _spec("high-hip-depth", "highHipDepth", 21.0, 12, 42, "radial_y", 0.59, 0.07, 0.022, max_abs_x=0.18),
    _spec("under-bust-depth", "underBustDepth", 23.0, 12, 38, "radial_y", 0.695, 0.045, 0.015, max_abs_x=0.17),
    # Keep support shaping above the underbust/rib-cage measurement plane. The
    # previous 0.10 radius extended into the underbust ruler and made the
    # requested circumference unreachable even though the bust itself fitted.
    _spec("supported-bust-shaping", "bustSupport", 50.0, 0, 100, "bust_support", 0.765, 0.075, 0.036, max_abs_x=0.19),
    _spec("left-hip-dip", "hipDipL", 0.7, 0, 5, "radial_x", 0.57, 0.055, -0.014, side=-1, max_abs_x=0.19),
    _spec("right-hip-dip", "hipDipR", 0.6, 0, 5, "radial_x", 0.57, 0.055, -0.014, side=1, max_abs_x=0.19),
    _spec("left-inseam", "inseamL", 77.0, 48, 105, "vertical_scale", 0.28, 0.28, 0.035, side=-1, pivot_z=0.04),
    _spec("right-inseam", "inseamR", 77.0, 48, 105, "vertical_scale", 0.28, 0.28, 0.035, side=1, pivot_z=0.04),
    _spec("left-total-arm-length", "armLengthL", 57.3, 38, 82, "arm_scale", 0.66, 0.18, 0.035, side=-1, pivot_z=0.79, min_abs_x=0.14),
    _spec("right-total-arm-length", "armLengthR", 57.3, 38, 82, "arm_scale", 0.66, 0.18, 0.035, side=1, pivot_z=0.79, min_abs_x=0.14),
    _spec("left-shoulder-length", "shoulderLengthL", 12.4, 7, 22, "translate_x", 0.80, 0.065, 0.018, side=-1, min_abs_x=0.10, max_abs_x=0.27),
    _spec("right-shoulder-length", "shoulderLengthR", 12.3, 7, 22, "translate_x", 0.80, 0.065, 0.018, side=1, min_abs_x=0.10, max_abs_x=0.27),
    _spec("left-armhole-depth", "armholeDepthL", 21.8, 13, 34, "translate_z", 0.755, 0.065, -0.012, side=-1, min_abs_x=0.11, max_abs_x=0.24),
    _spec("right-armhole-depth", "armholeDepthR", 21.8, 13, 34, "translate_z", 0.755, 0.065, -0.012, side=1, min_abs_x=0.11, max_abs_x=0.24),
    _spec("left-armscye-circumference", "armscyeCircL", 45.5, 28, 70, "radial_yz", 0.775, 0.075, 0.010, side=-1, min_abs_x=0.11, max_abs_x=0.25),
    _spec("right-armscye-circumference", "armscyeCircR", 45.5, 28, 70, "radial_yz", 0.775, 0.075, 0.010, side=1, min_abs_x=0.11, max_abs_x=0.25),
    _spec("left-knee-height", "kneeHeightL", 48.2, 30, 68, "translate_z", 0.29, 0.055, 0.016, side=-1),
    _spec("right-knee-height", "kneeHeightR", 48.2, 30, 68, "translate_z", 0.29, 0.055, 0.016, side=1),
    _spec("left-leg-offset", "legOffsetL", 0.0, -4, 4, "translate_x", 0.33, 0.30, 0.012, side=-1),
    _spec("right-leg-offset", "legOffsetR", 0.0, -4, 4, "translate_x", 0.33, 0.30, 0.012, side=1),
    _spec("lumbar-curve", "lumbarCurve", 2.4, -2, 8, "back_y", 0.64, 0.07, 0.015, max_abs_x=0.15),
    _spec("left-outseam", "outseamL", 103.0, 70, 135, "vertical_scale", 0.31, 0.31, 0.025, side=-1, pivot_z=0.02),
    _spec("right-outseam", "outseamR", 103.0, 70, 135, "vertical_scale", 0.31, 0.31, 0.025, side=1, pivot_z=0.02),
    _spec("pelvic-tilt", "pelvicTilt", 8.0, -20, 30, "sagittal_rotate", 0.55, 0.10, math.radians(10), pivot_z=0.55, max_abs_x=0.18),
    _spec("left-rib-flare", "ribFlareL", 0.4, -3, 7, "radial_x", 0.70, 0.07, 0.014, side=-1, max_abs_x=0.18),
    _spec("right-rib-flare", "ribFlareR", 0.4, -3, 7, "radial_x", 0.70, 0.07, 0.014, side=1, max_abs_x=0.18),
    _spec("left-scapula-projection", "scapulaProjectionL", 0.7, -2, 6, "back_y", 0.75, 0.065, 0.014, side=-1, max_abs_x=0.18),
    _spec("right-scapula-projection", "scapulaProjectionR", 0.6, -2, 6, "back_y", 0.75, 0.065, 0.014, side=1, max_abs_x=0.18),
    _spec("left-shoulder-roll", "shoulderRollL", 1.0, -20, 25, "translate_y", 0.79, 0.055, 0.016, side=-1),
    _spec("right-shoulder-roll", "shoulderRollR", 0.5, -20, 25, "translate_y", 0.79, 0.055, 0.016, side=1),
    _spec("left-shoulder-slope", "shoulderSlopeL", 12.0, -2, 30, "translate_z", 0.79, 0.055, -0.014, side=-1),
    _spec("right-shoulder-slope", "shoulderSlopeR", 11.5, -2, 30, "translate_z", 0.79, 0.055, -0.014, side=1),
    _spec("sternum-to-waist", "sternumWaist", 30.2, 18, 48, "front_z", 0.67, 0.13, 0.014, max_abs_x=0.13),
    _spec("torso-length", "torso", 42.0, 32, 58, "vertical_scale", 0.69, 0.18, 0.04, pivot_z=0.53, max_abs_x=0.20),
    _spec("torso-lean", "torsoLean", 0.0, -15, 20, "sagittal_rotate", 0.75, 0.24, math.radians(12), pivot_z=0.55, max_abs_x=0.36),
    _spec("torso-twist", "torsoTwist", 0.0, -20, 20, "axial_rotate", 0.72, 0.22, math.radians(14), pivot_z=0.55, max_abs_x=0.36),
    _spec("waist-depth", "waistDepth", 18.5, 10, 38, "radial_y", 0.61, 0.055, 0.022, max_abs_x=0.16),
    _spec("left-waist-to-knee", "waistKneeL", 59.4, 38, 82, "vertical_scale", 0.45, 0.16, 0.025, side=-1, pivot_z=0.28),
    _spec("right-waist-to-knee", "waistKneeR", 59.4, 38, 82, "vertical_scale", 0.45, 0.16, 0.025, side=1, pivot_z=0.28),
)


def local_deformation_keys() -> set[str]:
    return {spec.source_key for spec in LOCAL_DEFORMATION_SPECS}


def _normalized_delta(value: float, spec: LocalDeformationSpec) -> float:
    clamped = min(max(value, spec.minimum), spec.maximum)
    denominator = spec.maximum - spec.default if clamped >= spec.default else spec.default - spec.minimum
    if denominator <= 0:
        raise ValueError(f"Invalid local deformation range for {spec.name}.")
    return (clamped - spec.default) / denominator


def _smooth_weight(distance: float, radius: float) -> float:
    if radius <= 0 or distance >= radius:
        return 0.0
    t = 1.0 - distance / radius
    return t * t * (3.0 - 2.0 * t)


def _apply_spec(
    point: tuple[float, float, float],
    spec: LocalDeformationSpec,
    delta: float,
    height: float,
) -> tuple[float, float, float]:
    # MPFB uses positive Y for the anatomical front and negative Y for back.
    x, y, z = point
    z_ratio = z / height
    weight = _smooth_weight(abs(z_ratio - spec.z_center), spec.z_radius)
    x_ratio = abs(x) / height
    if x_ratio < spec.min_abs_x or x_ratio > spec.max_abs_x:
        return point
    if spec.side and x * spec.side <= 0:
        return point
    if weight <= 0:
        return point

    amount = delta * spec.max_amount * weight
    kind = spec.kind
    if kind == "front_y" and y > 0:
        y += amount
    elif kind == "back_y" and y < 0:
        y -= amount
    elif kind == "radial_y":
        y += math.copysign(amount, y if abs(y) > 1e-8 else -1.0)
    elif kind == "radial_x":
        x += math.copysign(amount, x if abs(x) > 1e-8 else float(spec.side or 1))
    elif kind == "radial_yz":
        center_z = spec.z_center * height
        radial_y = y
        radial_z = z - center_z
        radius = math.hypot(radial_y, radial_z)
        if radius > 1e-8:
            y += amount * radial_y / radius
            z += amount * radial_z / radius
    elif kind == "bust_support" and y > 0.0:
        center_z = spec.z_center * height
        front_weight = min(max((y / height - 0.012) / 0.060, 0.0), 1.0)
        lower_weight = min(max((center_z - z) / (spec.z_radius * height), 0.0), 1.0)
        upper_weight = min(max((z - center_z) / (spec.z_radius * height), 0.0), 1.0)
        # Support is a bounded redistribution around the breast root, not a
        # multi-centimeter translation of the entire bust. The old 3.5 cm
        # maximum lifted every front vertex equally and retracted the lower
        # breast hard enough to create a shelf-like inframammary transition.
        # Lift is distributed through a broad breast-root field, with only a
        # small volume-preserving depth transfer from lower to upper tissue.
        # MPFB tissue firmness remains separately bounded, so this support
        # control can raise a large bust without turning it into rigid spheres.
        z += amount * front_weight * (0.65 + 0.35 * lower_weight)
        y += amount * front_weight * (
            0.08 * upper_weight - 0.12 * lower_weight
        )
    elif kind == "translate_x":
        x += amount * float(spec.side or 1)
    elif kind == "translate_y":
        y += amount
    elif kind == "translate_z":
        z += amount
    elif kind == "front_z" and y > 0:
        z += amount
    elif kind == "back_z" and y < 0:
        z += amount
    elif kind == "vertical_scale":
        pivot = spec.pivot_z * height
        z += (z - pivot) * amount
    elif kind == "arm_scale":
        shoulder_x = float(spec.side) * 0.16 * height
        shoulder_z = spec.pivot_z * height
        x += (x - shoulder_x) * amount
        z += (z - shoulder_z) * amount
    elif kind == "sagittal_rotate":
        pivot = spec.pivot_z * height
        cosine = math.cos(amount)
        sine = math.sin(amount)
        relative_z = z - pivot
        y, z = y * cosine - relative_z * sine, pivot + y * sine + relative_z * cosine
    elif kind == "axial_rotate":
        cosine = math.cos(amount)
        sine = math.sin(amount)
        x, y = x * cosine - y * sine, x * sine + y * cosine
    else:
        return point
    return x, y, z


def apply_local_deformations(
    coordinates: Sequence[Sequence[float]],
    profile: dict[str, float],
) -> tuple[list[tuple[float, float, float]], tuple[EvaluatedLocalDeformation, ...]]:
    points = [(float(point[0]), float(point[1]), float(point[2])) for point in coordinates]
    if not points:
        return [], ()
    height = max(point[2] for point in points) - min(point[2] for point in points)
    if height <= 0:
        raise ValueError("Local deformation requires a positive body height.")

    results: list[EvaluatedLocalDeformation] = []
    for spec in LOCAL_DEFORMATION_SPECS:
        raw = profile.get(spec.source_key)
        if raw is None or not math.isfinite(float(raw)):
            continue
        requested = float(raw)
        delta = _normalized_delta(requested, spec)
        if abs(delta) <= 1e-12:
            results.append(EvaluatedLocalDeformation(
                spec.name,
                spec.source_key,
                requested,
                0.0,
                spec.kind,
                0,
                0.0,
            ))
            continue
        before = points
        points = [_apply_spec(point, spec, delta, height) for point in points]
        displacements = [
            math.dist(previous, current)
            for previous, current in zip(before, points)
        ]
        results.append(EvaluatedLocalDeformation(
            spec.name,
            spec.source_key,
            requested,
            delta,
            spec.kind,
            sum(displacement > 1e-10 for displacement in displacements),
            max(displacements, default=0.0) * 100.0,
        ))
    return points, tuple(results)


def validate_local_deformation_specs() -> None:
    names: set[str] = set()
    keys: set[str] = set()
    supported_kinds = {
        "front_y", "back_y", "radial_y", "radial_x", "translate_x",
        "translate_y", "translate_z", "front_z", "back_z",
        "vertical_scale", "arm_scale", "sagittal_rotate", "axial_rotate",
        "radial_yz",
        "bust_support",
    }
    for spec in LOCAL_DEFORMATION_SPECS:
        if spec.name in names or spec.source_key in keys:
            raise ValueError(f"Duplicate local deformation binding: {spec.name}")
        names.add(spec.name)
        keys.add(spec.source_key)
        if spec.kind not in supported_kinds:
            raise ValueError(f"Unsupported local deformation kind: {spec.kind}")
        if not spec.minimum < spec.default < spec.maximum:
            raise ValueError(f"Invalid local deformation range: {spec.name}")
        if (
            spec.side not in (-1, 0, 1)
            or spec.z_radius <= 0
            or not 0 <= spec.min_abs_x < spec.max_abs_x
        ):
            raise ValueError(f"Invalid local deformation region: {spec.name}")


validate_local_deformation_specs()
