"""Deterministic Patterna measurement controls for MPFB detail targets.

Direct MPFB rulers remain responsible for physically gated dimensions. These
controls map additional local, side-specific, depth, projection, and surface
measurements to named MPFB targets so the corresponding inputs materially
change the revisioned body mesh. The fit report keeps this approximate target
lane separate from the hard ruler lane.
"""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Iterable


# MPFB gender is centered at 0.5. Values below 0.5 are female and values above
# 0.5 are male. Patterna's default source body is explicitly fully female.
FEMALE_GENDER_MACRO = 0.0


@dataclass(frozen=True)
class MorphControlSpec:
    name: str
    source_keys: tuple[str, ...]
    default: float
    minimum: float
    maximum: float
    target_pairs: tuple[tuple[str, str], ...]
    max_weight: float = 0.75


@dataclass(frozen=True)
class EvaluatedMorphControl:
    name: str
    source_keys: tuple[str, ...]
    requested: float
    default: float
    normalized_delta: float
    direction: str
    weight: float
    target_weights: tuple[tuple[str, float], ...]


def _spec(
    name: str,
    source_keys: str | tuple[str, ...],
    default: float,
    minimum: float,
    maximum: float,
    *target_pairs: tuple[str, str],
    max_weight: float = 0.75,
) -> MorphControlSpec:
    keys = (source_keys,) if isinstance(source_keys, str) else source_keys
    return MorphControlSpec(
        name,
        keys,
        default,
        minimum,
        maximum,
        target_pairs,
        max_weight,
    )


MORPH_CONTROL_SPECS: tuple[MorphControlSpec, ...] = (
    _spec("head-circumference", "headCirc", 56.2, 45, 70,
          ("head-scale-horiz-decr", "head-scale-horiz-incr")),
    _spec("head-height", ("headHeight", "crownChin"), 22.75, 16, 30,
          ("head-scale-vert-decr", "head-scale-vert-incr")),
    _spec("face-depth", "faceDepth", 18.1, 12, 25,
          ("head-scale-depth-decr", "head-scale-depth-incr")),
    _spec("temple-width", "faceWidth", 14.2, 10, 20,
          ("forehead-temple-decr", "forehead-temple-incr")),
    _spec("cheekbone-width", "bizygomaticWidth", 13.8, 9, 20,
          ("l-cheek-bones-decr", "l-cheek-bones-incr"),
          ("r-cheek-bones-decr", "r-cheek-bones-incr")),
    _spec("ear-to-ear-over-crown", "earToEar", 31.8, 22, 42,
          ("l-ear-scale-decr", "l-ear-scale-incr"),
          ("r-ear-scale-decr", "r-ear-scale-incr"), max_weight=0.5),
    _spec("back-skull-projection", "skullBackProjection", 2.1, 0, 6,
          ("head-back-scale-depth-decr", "head-back-scale-depth-incr")),
    _spec("jaw-width", "jawWidth", 11.2, 7, 18,
          ("chin-width-decr", "chin-width-incr")),
    _spec("jaw-depth", "jawDepth", 10.4, 6, 16,
          ("chin-prognathism-decr", "chin-prognathism-incr")),
    _spec("neck-base-width", "neckBaseCirc", 39.4, 28, 68,
          ("neck-scale-horiz-decr", "neck-scale-horiz-incr")),
    _spec("neck-depth", "neckCirc", 34.5, 24, 58,
          ("neck-scale-depth-decr", "neck-scale-depth-incr"), max_weight=0.55),
    _spec("chin-to-neck", "chinNeck", 9.3, 4, 17,
          ("chin-height-decr", "chin-height-incr"), max_weight=0.5),
    _spec("head-forward-offset", "neckForward", 1.2, -4, 8,
          ("neck-trans-backward", "neck-trans-forward"), max_weight=0.55),
    _spec("chest-depth", "chestDepth", 23.2, 14, 42,
          ("torso-scale-depth-decr", "torso-scale-depth-incr"), max_weight=0.55),
    _spec("high-chest-circumference", "highChestCirc", 88.0, 58, 150,
          ("torso-scale-horiz-decr", "torso-scale-horiz-incr"), max_weight=0.45),
    _spec("back-width", "acrossBack", 36.5, 24, 60,
          ("torso-muscle-dorsi-decr", "torso-muscle-dorsi-incr"), max_weight=0.45),
    _spec("lower-rib-circumference", "ribCirc", 78.4, 50, 145,
          ("torso-muscle-pectoral-decr", "torso-muscle-pectoral-incr"), max_weight=0.4),
    _spec("upper-bust-fullness", "upperBustFullness", 50, 0, 100,
          ("breast-volume-vert-down", "breast-volume-vert-up"), max_weight=0.55),
    _spec("back-waist-length", "backWaistLength", 41.8, 27, 64,
          ("torso-scale-vert-decr", "torso-scale-vert-incr"), max_weight=0.4),
    _spec("bust-separation", "bustSeparation", 18.6, 8, 34,
          ("breast-dist-decr", "breast-dist-incr")),
    _spec("bust-height", ("bustHeightL", "bustHeightR"), 25.7, 14, 42,
          ("breast-trans-up", "breast-trans-down"), max_weight=0.6),
    # The same projection rulers also select MPFB's cup-size macro. Keep this
    # detail target subordinate to that macro so one measurement does not add
    # the full breast projection twice. It refines apex shape only.
    _spec("bust-projection", ("bustProjectionL", "bustProjectionR"), 4.75, 0, 14,
          ("breast-point-decr", "breast-point-incr"), max_weight=0.25),
    _spec("abdomen-projection", "abdomenProjection", 1.7, -4, 12,
          ("stomach-pregnant-decr", "stomach-pregnant-incr"), max_weight=0.55),
    _spec("abdomen-circumference", "abdomenCirc", 82.0, 50, 165,
          ("stomach-tone-decr", "stomach-tone-incr"), max_weight=0.55),
    _spec("abdomen-depth", "abdomenDepth", 20.4, 10, 45,
          ("stomach-navel-in", "stomach-navel-out"), max_weight=0.5),
    _spec("high-hip-circumference", "highHipCirc", 87.4, 58, 155,
          ("pelvis-tone-decr", "pelvis-tone-incr"), max_weight=0.5),
    _spec("pelvis-width", "pelvicWidth", 29.2, 18, 48,
          ("hip-scale-horiz-decr", "hip-scale-horiz-incr"), max_weight=0.55),
    _spec("hip-depth", "hipDepth", 24.8, 14, 46,
          ("hip-scale-depth-decr", "hip-scale-depth-incr"), max_weight=0.55),
    _spec("seat-projection", ("gluteProjectionL", "gluteProjectionR"), 4.15, 0, 13,
          ("buttocks-volume-decr", "buttocks-volume-incr")),
    _spec("body-rise", "bodyRise", 26.7, 18, 42,
          ("hip-scale-vert-decr", "hip-scale-vert-incr"), max_weight=0.45),
    _spec("waist-to-hip-length", ("waistHipLengthL", "waistHipLengthR"), 20.35, 12, 32,
          ("hip-waist-up", "hip-waist-down"), max_weight=0.4),
    _spec("thoracic-curve", "thoracicCurve", 2.2, -2, 8,
          ("torso-trans-backward", "torso-trans-forward"), max_weight=0.2),
    _spec("cervical-curve", "cervicalCurve", 1.3, -2, 6,
          ("neck-back-scale-depth-decr", "neck-back-scale-depth-incr"), max_weight=0.3),
    _spec("left-deltoid-prominence", "deltoidProminenceL", 50, 0, 100,
          ("l-upperarm-shoulder-muscle-decr", "l-upperarm-shoulder-muscle-incr"), max_weight=0.55),
    _spec("right-deltoid-prominence", "deltoidProminenceR", 50, 0, 100,
          ("r-upperarm-shoulder-muscle-decr", "r-upperarm-shoulder-muscle-incr"), max_weight=0.55),
    _spec("left-upper-arm-length", "shoulderElbowL", 31.8, 20, 48,
          ("l-upperarm-scale-vert-decr", "l-upperarm-scale-vert-incr"), max_weight=0.45),
    _spec("right-upper-arm-length", "shoulderElbowR", 31.8, 20, 48,
          ("r-upperarm-scale-vert-decr", "r-upperarm-scale-vert-incr"), max_weight=0.45),
    _spec("left-lower-arm-length", "elbowWristL", 25.5, 16, 40,
          ("l-lowerarm-scale-vert-decr", "l-lowerarm-scale-vert-incr"), max_weight=0.45),
    _spec("right-lower-arm-length", "elbowWristR", 25.5, 16, 40,
          ("r-lowerarm-scale-vert-decr", "r-lowerarm-scale-vert-incr"), max_weight=0.45),
    _spec("left-upper-arm-girth", "upperArmCircL", 29.4, 18, 62,
          ("l-upperarm-scale-horiz-decr", "l-upperarm-scale-horiz-incr"), max_weight=0.4),
    _spec("right-upper-arm-girth", "upperArmCircR", 29.4, 18, 62,
          ("r-upperarm-scale-horiz-decr", "r-upperarm-scale-horiz-incr"), max_weight=0.4),
    _spec("left-upper-arm-depth", "bicepDepthL", 9.2, 5, 20,
          ("l-upperarm-scale-depth-decr", "l-upperarm-scale-depth-incr")),
    _spec("right-upper-arm-depth", "bicepDepthR", 9.2, 5, 20,
          ("r-upperarm-scale-depth-decr", "r-upperarm-scale-depth-incr")),
    _spec("left-elbow-girth", "elbowCircL", 25.1, 17, 44,
          ("l-lowerarm-scale-depth-decr", "l-lowerarm-scale-depth-incr"), max_weight=0.35),
    _spec("right-elbow-girth", "elbowCircR", 25.1, 17, 44,
          ("r-lowerarm-scale-depth-decr", "r-lowerarm-scale-depth-incr"), max_weight=0.35),
    _spec("left-forearm-girth", "forearmCircL", 24.0, 15, 43,
          ("l-lowerarm-scale-horiz-decr", "l-lowerarm-scale-horiz-incr")),
    _spec("right-forearm-girth", "forearmCircR", 24.0, 15, 43,
          ("r-lowerarm-scale-horiz-decr", "r-lowerarm-scale-horiz-incr")),
    _spec("left-wrist-fullness", "wristCircL", 15.8, 11, 28,
          ("l-lowerarm-fat-decr", "l-lowerarm-fat-incr"), max_weight=0.3),
    _spec("right-wrist-fullness", "wristCircR", 15.8, 11, 28,
          ("r-lowerarm-fat-decr", "r-lowerarm-fat-incr"), max_weight=0.3),
    _spec("left-hand-length", "handLengthL", 17.9, 12, 26,
          ("l-hand-fingers-length-decr", "l-hand-fingers-length-incr")),
    _spec("right-hand-length", "handLengthR", 17.9, 12, 26,
          ("r-hand-fingers-length-decr", "r-hand-fingers-length-incr")),
    _spec("left-palm-width", "palmWidthL", 7.7, 5, 13,
          ("l-hand-fingers-distance-decr", "l-hand-fingers-distance-incr")),
    _spec("right-palm-width", "palmWidthR", 7.7, 5, 13,
          ("r-hand-fingers-distance-decr", "r-hand-fingers-distance-incr")),
    _spec("left-palm-girth", "palmCircL", 18.4, 13, 30,
          ("l-hand-scale-decr", "l-hand-scale-incr"), max_weight=0.45),
    _spec("right-palm-girth", "palmCircR", 18.4, 13, 30,
          ("r-hand-scale-decr", "r-hand-scale-incr"), max_weight=0.45),
    _spec("left-thumb-base-girth", "thumbBaseCircL", 6.3, 4, 11,
          ("l-hand-fingers-diameter-decr", "l-hand-fingers-diameter-incr"), max_weight=0.35),
    _spec("right-thumb-base-girth", "thumbBaseCircR", 6.3, 4, 11,
          ("r-hand-fingers-diameter-decr", "r-hand-fingers-diameter-incr"), max_weight=0.35),
    _spec("left-upper-arm-soft-tissue", "upperArmSoftTissueL", 50, 0, 100,
          ("l-upperarm-fat-decr", "l-upperarm-fat-incr"), max_weight=0.35),
    _spec("right-upper-arm-soft-tissue", "upperArmSoftTissueR", 50, 0, 100,
          ("r-upperarm-fat-decr", "r-upperarm-fat-incr"), max_weight=0.35),
    _spec("left-upper-leg-length", "crotchKneeL", 34.8, 20, 53,
          ("l-upperleg-scale-vert-decr", "l-upperleg-scale-vert-incr"), max_weight=0.45),
    _spec("right-upper-leg-length", "crotchKneeR", 34.8, 20, 53,
          ("r-upperleg-scale-vert-decr", "r-upperleg-scale-vert-incr"), max_weight=0.45),
    _spec("left-lower-leg-length", "lowerLegLengthL", 40.8, 25, 58,
          ("l-lowerleg-scale-vert-decr", "l-lowerleg-scale-vert-incr"), max_weight=0.45),
    _spec("right-lower-leg-length", "lowerLegLengthR", 40.8, 25, 58,
          ("r-lowerleg-scale-vert-decr", "r-lowerleg-scale-vert-incr"), max_weight=0.45),
    _spec("left-upper-thigh-girth", "thighUpperCircL", 57.4, 32, 95,
          ("l-upperleg-scale-depth-decr", "l-upperleg-scale-depth-incr"), max_weight=0.4),
    _spec("right-upper-thigh-girth", "thighUpperCircR", 57.4, 32, 95,
          ("r-upperleg-scale-depth-decr", "r-upperleg-scale-depth-incr"), max_weight=0.4),
    _spec("left-mid-thigh-girth", "thighMidCircL", 50.2, 28, 85,
          ("l-upperleg-scale-horiz-decr", "l-upperleg-scale-horiz-incr")),
    _spec("right-mid-thigh-girth", "thighMidCircR", 50.2, 28, 85,
          ("r-upperleg-scale-horiz-decr", "r-upperleg-scale-horiz-incr")),
    _spec("left-knee-fullness", "kneeCircL", 36.8, 24, 62,
          ("l-upperleg-muscle-decr", "l-upperleg-muscle-incr"), max_weight=0.25),
    _spec("right-knee-fullness", "kneeCircR", 36.8, 24, 62,
          ("r-upperleg-muscle-decr", "r-upperleg-muscle-incr"), max_weight=0.25),
    _spec("left-calf-girth", "calfCircL", 36.4, 22, 65,
          ("l-lowerleg-scale-horiz-decr", "l-lowerleg-scale-horiz-incr"), max_weight=0.4),
    _spec("right-calf-girth", "calfCircR", 36.4, 22, 65,
          ("r-lowerleg-scale-horiz-decr", "r-lowerleg-scale-horiz-incr"), max_weight=0.4),
    _spec("left-ankle-girth", "ankleCircL", 22.5, 15, 40,
          ("l-lowerleg-scale-depth-decr", "l-lowerleg-scale-depth-incr"), max_weight=0.3),
    _spec("right-ankle-girth", "ankleCircR", 22.5, 15, 40,
          ("r-lowerleg-scale-depth-decr", "r-lowerleg-scale-depth-incr"), max_weight=0.3),
    _spec("left-knee-alignment", "kneeAngleL", 0, -15, 15,
          ("l-leg-valgus-decr", "l-leg-valgus-incr"), max_weight=0.45),
    _spec("right-knee-alignment", "kneeAngleR", 0, -15, 15,
          ("r-leg-valgus-decr", "r-leg-valgus-incr"), max_weight=0.45),
    _spec("left-foot-length", "footLengthL", 24.1, 18, 34,
          ("l-foot-scale-depth-decr", "l-foot-scale-depth-incr")),
    _spec("right-foot-length", "footLengthR", 24.1, 18, 34,
          ("r-foot-scale-depth-decr", "r-foot-scale-depth-incr")),
    _spec("left-foot-width", "footWidthL", 9.2, 6, 15,
          ("l-foot-scale-horiz-decr", "l-foot-scale-horiz-incr")),
    _spec("right-foot-width", "footWidthR", 9.2, 6, 15,
          ("r-foot-scale-horiz-decr", "r-foot-scale-horiz-incr")),
    _spec("left-ball-girth", "ballGirthL", 22.6, 16, 35,
          ("l-foot-scale-decr", "l-foot-scale-incr"), max_weight=0.35),
    _spec("right-ball-girth", "ballGirthR", 22.6, 16, 35,
          ("r-foot-scale-decr", "r-foot-scale-incr"), max_weight=0.35),
    _spec("left-arch-height", "archHeightL", 2.1, 0, 6,
          ("l-foot-scale-vert-decr", "l-foot-scale-vert-incr"), max_weight=0.45),
    _spec("right-arch-height", "archHeightR", 2.1, 0, 6,
          ("r-foot-scale-vert-decr", "r-foot-scale-vert-incr"), max_weight=0.45),
    _spec("upper-body-distribution", "upperBodyDistribution", 48, 0, 100,
          ("torso-vshape-decr", "torso-vshape-incr"), max_weight=0.5),
    _spec("lower-body-tone", "lowerBodyDistribution", 55, 0, 100,
          ("l-upperleg-fat-decr", "l-upperleg-fat-incr"),
          ("r-upperleg-fat-decr", "r-upperleg-fat-incr"),
          ("l-lowerleg-fat-decr", "l-lowerleg-fat-incr"),
          ("r-lowerleg-fat-decr", "r-lowerleg-fat-incr"), max_weight=0.35),
)


MACRO_CONTROL_SOURCES: dict[str, tuple[tuple[str, ...], float, float, float]] = {
    "muscle": (("muscleDefinition",), 35, 0, 100),
    "weight": (("softTissue",), 45, 0, 100),
    "cupsize": (("bustProjectionL", "bustProjectionR"), 4.75, 0, 14),
    "firmness": (("bustSupport",), 50, 0, 100),
}


# These are the Patterna UI measurements that feed an MPFB ruler constraint,
# either directly or through a documented GarmentCode body alias. The ruler
# fit is symmetric where a left and right pair contributes to one measurement;
# side-specific detail targets preserve asymmetry around that physical average.
DIRECT_RULER_SOURCE_KEYS: frozenset[str] = frozenset({
    "height",
    "chest",
    "underBust",
    "waist",
    "hip",
    "shoulder",
    "neckBaseCirc",
    "frontWaistLength",
    "waistHipLengthL",
    "waistHipLengthR",
    "armLengthL",
    "armLengthR",
    "wristCircL",
    "wristCircR",
    "thighUpperCircL",
    "thighUpperCircR",
    "shoulderElbowL",
    "shoulderElbowR",
    "elbowWristL",
    "elbowWristR",
    "neckLengthFront",
    "neckLengthBack",
    "upperArmCircL",
    "upperArmCircR",
    "acrossFront",
    "crotchKneeL",
    "crotchKneeR",
    "lowerLegLengthL",
    "lowerLegLengthR",
    "kneeCircL",
    "kneeCircR",
    "calfCircL",
    "calfCircR",
    "ankleCircL",
    "ankleCircR",
})


def _average_available(profile: dict[str, float], keys: Iterable[str]) -> float | None:
    values = [float(profile[key]) for key in keys if key in profile and math.isfinite(float(profile[key]))]
    return sum(values) / len(values) if values else None


def normalized_delta(value: float, default: float, minimum: float, maximum: float) -> float:
    if not all(math.isfinite(item) for item in (value, default, minimum, maximum)):
        raise ValueError("Morph control values must be finite.")
    if not minimum < default < maximum:
        raise ValueError("Morph control range must contain its default.")
    clamped = min(max(value, minimum), maximum)
    denominator = maximum - default if clamped >= default else default - minimum
    return (clamped - default) / denominator


def evaluate_morph_controls(profile: dict[str, float]) -> tuple[EvaluatedMorphControl, ...]:
    evaluated: list[EvaluatedMorphControl] = []
    for spec in MORPH_CONTROL_SPECS:
        requested = _average_available(profile, spec.source_keys)
        if requested is None:
            continue
        delta = normalized_delta(requested, spec.default, spec.minimum, spec.maximum)
        direction_index = 1 if delta >= 0 else 0
        target_weights: list[tuple[str, float]] = []
        for decreasing, increasing in spec.target_pairs:
            target_weights.append((decreasing, abs(delta) * spec.max_weight if direction_index == 0 else 0.0))
            target_weights.append((increasing, abs(delta) * spec.max_weight if direction_index == 1 else 0.0))
        evaluated.append(EvaluatedMorphControl(
            spec.name,
            spec.source_keys,
            requested,
            spec.default,
            delta,
            "increase" if direction_index else "decrease",
            abs(delta) * spec.max_weight,
            tuple(target_weights),
        ))
    return tuple(evaluated)


def macro_controls(profile: dict[str, float]) -> dict[str, float]:
    result: dict[str, float] = {}
    for macro_name, (source_keys, default, minimum, maximum) in MACRO_CONTROL_SOURCES.items():
        requested = _average_available(profile, source_keys)
        if requested is None:
            continue
        delta = normalized_delta(requested, default, minimum, maximum)
        if macro_name == "firmness":
            # bustSupport describes the effect of external support, not the
            # intrinsic stiffness of breast tissue. MPFB's maximum firmness
            # produces a detached hemispherical silhouette on large cups.
            # Support still drives the dedicated evaluated-surface lift, while
            # the macro contributes only a bounded secondary response.
            result[macro_name] = min(max(0.5 + delta * 0.25, 0.25), 0.75)
        else:
            result[macro_name] = min(max(0.5 + delta * 0.5, 0.0), 1.0)
    return result


def mapped_measurement_keys() -> set[str]:
    keys = {key for spec in MORPH_CONTROL_SPECS for key in spec.source_keys}
    for source_keys, _, _, _ in MACRO_CONTROL_SOURCES.values():
        keys.update(source_keys)
    return keys


def validate_control_specs() -> None:
    names: set[str] = set()
    target_names: set[str] = set()
    for spec in MORPH_CONTROL_SPECS:
        if spec.name in names:
            raise ValueError(f"Duplicate morph control name: {spec.name}")
        names.add(spec.name)
        if not spec.source_keys or not spec.target_pairs or not 0 < spec.max_weight <= 2:
            raise ValueError(f"Incomplete morph control specification: {spec.name}")
        normalized_delta(spec.default, spec.default, spec.minimum, spec.maximum)
        for pair in spec.target_pairs:
            if len(pair) != 2 or pair[0] == pair[1]:
                raise ValueError(f"Invalid target pair for {spec.name}")
            for target_name in pair:
                if target_name in target_names:
                    raise ValueError(f"Morph target is controlled more than once: {target_name}")
                target_names.add(target_name)


validate_control_specs()
