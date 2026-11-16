"""Declared Patterna-to-Anny control mapping table.

Every live Patternal avatar control key appears exactly once. A mapped entry
declares one primary Anny target (family plus label) and one transform that the
avatar worker must implement exactly. An unsupported entry declares the precise
reason no Anny target may claim that control. The builder validates every label
against the pinned runtime's discovery inventory before emitting the immutable
``patterna.anny-control-map/1.0`` document.

Transform kinds:

``bounded-differentiable-fit``
    The worker jointly optimizes the declared target scalars, bounded to the
    declared range, until the named mesh objective matches the source value.
    ``pairedKeys`` lists source controls that share the same objective through
    a declared mean policy instead of independent left and right targets.
    ``additionalTargetKeys`` lists further Anny labels in the same family that
    the fit drives together with the primary label.

``linear-direct``
    The worker computes ``value * scale + offset`` and clamps to the declared
    range. No mesh objective is fitted.
"""

from __future__ import annotations


POSTURE_REASON = (
    "Absolute posture angles are owned by the fixed balanced A-stance pose"
    " target in this bounded bakeoff; no calibrated per-bone angle mapping is"
    " declared, so claiming this control would fabricate a body change."
)


def fit(
    family: str,
    target: str,
    measure: str,
    station: str,
    *,
    paired: tuple[str, ...] = (),
    extra: tuple[str, ...] = (),
    bounds: tuple[float, float] = (-1.0, 1.0),
) -> dict:
    return {
        "status": "mapped",
        "target": {
            "family": family,
            "key": target,
            "transform": {
                "kind": "bounded-differentiable-fit",
                "objective": {
                    "measure": measure,
                    "station": station,
                    "pairedKeys": list(paired),
                    "additionalTargetKeys": list(extra),
                },
                "bounds": list(bounds),
            },
        },
    }


def direct(
    family: str,
    target: str,
    scale: float,
    offset: float,
    low: float,
    high: float,
) -> dict:
    return {
        "status": "mapped",
        "target": {
            "family": family,
            "key": target,
            "transform": {
                "kind": "linear-direct",
                "scale": scale,
                "offset": offset,
                "clampLow": low,
                "clampHigh": high,
            },
        },
    }


def unsupported(reason: str) -> dict:
    return {"status": "unsupported", "unsupportedReason": reason}


CONTROL_TABLE: dict[str, dict] = {
    # Core gated dimensions.
    "height": fit("phenotype", "height", "stature", "floor-to-crown", bounds=(0.0, 1.0)),
    "chest": fit("localChange", "measure-bust-circ-incr", "circumference", "bust"),
    "underBust": fit("localChange", "measure-underbust-circ-incr", "circumference", "underbust"),
    "waist": fit("localChange", "measure-waist-circ-incr", "circumference", "waist"),
    "hip": fit("localChange", "measure-hips-circ-incr", "circumference", "hip"),
    "shoulder": fit(
        "localChange", "measure-shoulder-dist-incr", "distance", "shoulder-breadth",
    ),
    "torso": fit(
        "localChange", "measure-napetowaist-dist-incr", "height", "nape-to-waist",
        paired=("backNeckWaist", "backWaistLength"),
    ),
    "backNeckWaist": fit(
        "localChange", "measure-napetowaist-dist-incr", "height", "nape-to-waist",
        paired=("torso", "backWaistLength"),
    ),
    "backWaistLength": fit(
        "localChange", "measure-napetowaist-dist-incr", "height", "nape-to-waist",
        paired=("torso", "backNeckWaist"),
    ),
    "acrossFront": fit("localChange", "measure-frontchest-dist-incr", "distance", "across-front"),
    "acrossBack": unsupported(
        "Anny exposes a front-chest distance target but no independent"
        " across-back target; the across-back width follows the shared torso"
        " and shoulder fits."
    ),
    # Torso stations.
    "chestDepth": fit(
        "localChange", "torso-scale-depth-incr", "depth", "chest",
    ),
    "waistDepth": fit(
        "localChange", "torso-scale-depth-incr", "depth", "waist",
    ),
    "underBustDepth": fit(
        "localChange", "torso-scale-depth-incr", "depth", "underbust",
    ),
    "abdomenCirc": fit(
        "localChange", "stomach-pregnant-incr", "circumference", "abdomen",
        extra=("stomach-tone-incr",),
    ),
    "abdomenDepth": fit(
        "localChange", "stomach-pregnant-incr", "depth", "abdomen",
        extra=("stomach-tone-incr",),
    ),
    "abdomenProjection": fit(
        "localChange", "stomach-pregnant-incr", "projection", "abdomen-front",
        extra=("stomach-tone-incr",),
    ),
    "highChestCirc": unsupported(
        "The shared torso scales cannot express a separate high-chest station"
        " without disturbing the gated bust and underbust circumference fits."
    ),
    "ribCirc": unsupported(
        "The rib station sits between the gated underbust and waist fits and"
        " has no separable Anny target."
    ),
    "sternumWaist": unsupported(
        "The sternum-to-waist tape path has no separable Anny target beyond"
        " the shared torso vertical scale that the nape-to-waist fit owns."
    ),
    "frontWaistLength": unsupported(
        "Anny exposes a back nape-to-waist length target but no independent"
        " front waist length target."
    ),
    # Hip and seat.
    "hipDepth": fit(
        "localChange", "hip-scale-depth-incr", "depth", "hip",
    ),
    "highHipDepth": fit(
        "localChange", "hip-scale-depth-incr", "depth", "high-hip",
    ),
    "highHipCirc": unsupported(
        "The high-hip station lies between the gated waist and hip"
        " circumference fits, which already own that region's shape. Anny's"
        " hip-waist-up target translates the hip mass vertically instead of"
        " changing the high-hip girth, so mapping this control would claim a"
        " body change the target cannot make."
    ),
    "pelvicWidth": fit("localChange", "hip-scale-horiz-incr", "width", "pelvis"),
    "frontHipArc": fit(
        "localChange", "hip-trans-forward", "arc-length", "front-hip",
    ),
    "backHipArc": fit(
        "localChange", "hip-trans-forward", "arc-length", "back-hip",
    ),
    "gluteProjectionL": fit(
        "localChange", "buttocks-volume-incr", "projection", "seat-rear",
        paired=("gluteProjectionR",),
    ),
    "gluteProjectionR": fit(
        "localChange", "buttocks-volume-incr", "projection", "seat-rear",
        paired=("gluteProjectionL",),
    ),
    "hipDipL": unsupported("Anny has no hip-dip depression target."),
    "hipDipR": unsupported("Anny has no hip-dip depression target."),
    "crotchDepth": fit("localChange", "hip-scale-vert-incr", "height", "waist-to-crotch"),
    "waistHipLengthL": fit(
        "localChange", "measure-waisttohip-dist-incr", "height", "waist-to-hip",
        paired=("waistHipLengthR",),
    ),
    "waistHipLengthR": fit(
        "localChange", "measure-waisttohip-dist-incr", "height", "waist-to-hip",
        paired=("waistHipLengthL",),
    ),
    "crotchLength": unsupported(
        "The full front-to-back crotch tape path is a composite surface curve"
        " with no separable Anny target."
    ),
    "bodyRise": unsupported("The seated body-rise measure has no Anny target."),
    "backRise": unsupported(
        "The back-rise tape path is a composite surface curve with no"
        " separable Anny target."
    ),
    "frontRise": unsupported(
        "The front-rise tape path is a composite surface curve with no"
        " separable Anny target."
    ),
    # Bust shape.
    "bustSeparation": fit("localChange", "breast-dist-incr", "distance", "bust-apex-separation"),
    "bustProjectionL": fit(
        "phenotype", "cupsize", "projection", "bust-apex",
        paired=("bustProjectionR",), bounds=(0.0, 1.0),
    ),
    "bustProjectionR": fit(
        "phenotype", "cupsize", "projection", "bust-apex",
        paired=("bustProjectionL",), bounds=(0.0, 1.0),
    ),
    "bustHeightL": fit(
        "localChange", "breast-trans-up", "height", "bust-apex",
        paired=("bustHeightR",),
    ),
    "bustHeightR": fit(
        "localChange", "breast-trans-up", "height", "bust-apex",
        paired=("bustHeightL",),
    ),
    "upperBustFullness": direct("localChange", "breast-volume-vert-up", 0.02, -1.0, -1.0, 1.0),
    "bustSupport": direct("phenotype", "firmness", 0.01, 0.0, 0.0, 1.0),
    # Neck and head.
    "neckCirc": fit("localChange", "measure-neck-circ-incr", "circumference", "mid-neck"),
    "neckBaseCirc": fit(
        "localChange", "neck-scale-horiz-incr", "circumference", "neck-base",
        extra=("neck-scale-depth-incr",),
    ),
    "neckLengthBack": fit(
        "localChange", "measure-neck-height-incr", "height", "neck-span",
        paired=("neckLengthFront",),
    ),
    "neckLengthFront": fit(
        "localChange", "measure-neck-height-incr", "height", "neck-span",
        paired=("neckLengthBack",),
    ),
    "neckForward": fit("localChange", "neck-trans-forward", "projection", "neck-forward"),
    "chinNeck": unsupported(
        "The chin-to-neck distance has no separable Anny target; the"
        " double-chin volume target changes fullness, not that distance."
    ),
    "headCirc": fit(
        "localChange", "head-scale-horiz-incr", "circumference", "head",
        extra=("head-scale-depth-incr",),
    ),
    "headHeight": fit(
        "localChange", "head-scale-vert-incr", "height", "crown-to-chin",
        paired=("crownChin",),
    ),
    "crownChin": fit(
        "localChange", "head-scale-vert-incr", "height", "crown-to-chin",
        paired=("headHeight",),
    ),
    "faceWidth": fit("localChange", "head-scale-horiz-incr", "width", "face"),
    "faceDepth": fit("localChange", "head-scale-depth-incr", "depth", "face"),
    "bizygomaticWidth": fit(
        "localChange", "l-cheek-bones-incr", "width", "cheekbones",
        extra=("r-cheek-bones-incr",),
    ),
    "jawWidth": fit("localChange", "chin-width-incr", "width", "jaw"),
    "jawDepth": unsupported("Anny has no separable jaw-depth target."),
    "skullBackProjection": fit(
        "localChange", "head-back-scale-depth-incr", "projection", "skull-back"
    ),
    "earToEar": unsupported(
        "The over-crown ear-to-ear tape path is not implemented as a mesh"
        " objective in this bounded bakeoff."
    ),
    "cervicalCurve": unsupported("Anny has no spine-curvature depth target."),
    "thoracicCurve": unsupported("Anny has no spine-curvature depth target."),
    "lumbarCurve": unsupported("Anny has no spine-curvature depth target."),
    # Arms.
    "upperArmCircL": fit(
        "localChange", "l-upperarm-scale-horiz-incr", "circumference", "upper-arm",
        extra=("l-upperarm-scale-depth-incr",),
    ),
    "upperArmCircR": fit(
        "localChange", "r-upperarm-scale-horiz-incr", "circumference", "upper-arm",
        extra=("r-upperarm-scale-depth-incr",),
    ),
    "bicepDepthL": fit("localChange", "l-upperarm-scale-depth-incr", "depth", "bicep"),
    "bicepDepthR": fit("localChange", "r-upperarm-scale-depth-incr", "depth", "bicep"),
    "forearmCircL": fit(
        "localChange", "l-lowerarm-scale-horiz-incr", "circumference", "forearm",
        extra=("l-lowerarm-scale-depth-incr",),
    ),
    "forearmCircR": fit(
        "localChange", "r-lowerarm-scale-horiz-incr", "circumference", "forearm",
        extra=("r-lowerarm-scale-depth-incr",),
    ),
    "elbowCircL": unsupported("Anny has no elbow-station target separable from the shared arm scales."),
    "elbowCircR": unsupported("Anny has no elbow-station target separable from the shared arm scales."),
    "wristCircL": fit(
        "localChange", "measure-wrist-circ-incr", "circumference", "wrist",
        paired=("wristCircR",),
    ),
    "wristCircR": fit(
        "localChange", "measure-wrist-circ-incr", "circumference", "wrist",
        paired=("wristCircL",),
    ),
    "shoulderElbowL": fit(
        "localChange", "measure-upperarm-length-incr", "length", "shoulder-to-elbow",
        paired=("shoulderElbowR",),
    ),
    "shoulderElbowR": fit(
        "localChange", "measure-upperarm-length-incr", "length", "shoulder-to-elbow",
        paired=("shoulderElbowL",),
    ),
    "elbowWristL": fit(
        "localChange", "measure-lowerarm-length-incr", "length", "elbow-to-wrist",
        paired=("elbowWristR",),
    ),
    "elbowWristR": fit(
        "localChange", "measure-lowerarm-length-incr", "length", "elbow-to-wrist",
        paired=("elbowWristL",),
    ),
    "armLengthL": fit(
        "localChange", "measure-upperarm-length-incr", "length", "shoulder-to-wrist",
        paired=("armLengthR",), extra=("measure-lowerarm-length-incr",),
    ),
    "armLengthR": fit(
        "localChange", "measure-upperarm-length-incr", "length", "shoulder-to-wrist",
        paired=("armLengthL",), extra=("measure-lowerarm-length-incr",),
    ),
    "armholeDepthL": unsupported(
        "The armhole depth is owned by the garment draft and the shared"
        " torso scales; Anny has no separable armscye target."
    ),
    "armholeDepthR": unsupported(
        "The armhole depth is owned by the garment draft and the shared"
        " torso scales; Anny has no separable armscye target."
    ),
    "armscyeCircL": unsupported("Anny has no armscye-circumference target."),
    "armscyeCircR": unsupported("Anny has no armscye-circumference target."),
    "deltoidProminenceL": direct("localChange", "l-upperarm-shoulder-muscle-incr", 0.01, 0.0, 0.0, 1.0),
    "deltoidProminenceR": direct("localChange", "r-upperarm-shoulder-muscle-incr", 0.01, 0.0, 0.0, 1.0),
    "upperArmSoftTissueL": direct("localChange", "l-upperarm-fat-incr", 0.01, 0.0, 0.0, 1.0),
    "upperArmSoftTissueR": direct("localChange", "r-upperarm-fat-incr", 0.01, 0.0, 0.0, 1.0),
    "scapulaProjectionL": unsupported(
        "Anny's dorsi muscle target changes muscle mass, not skeletal scapula"
        " projection; no honest target exists."
    ),
    "scapulaProjectionR": unsupported(
        "Anny's dorsi muscle target changes muscle mass, not skeletal scapula"
        " projection; no honest target exists."
    ),
    "ribFlareL": unsupported("Anny has no rib-flare target."),
    "ribFlareR": unsupported("Anny has no rib-flare target."),
    # Legs.
    "thighUpperCircL": unsupported(
        "The upper-thigh tape sits at the gluteal fold, where the thigh is"
        " still merged with the pelvis on this topology. No section plane"
        " isolates one thigh loop there: the measured perimeter swings from"
        " 17 to 54 cm with the selection radius, so any fit driven by it"
        " would be reading an unstable quantity. The mid-thigh station owns"
        " the leg circumference fit."
    ),
    "thighUpperCircR": unsupported(
        "The upper-thigh tape sits at the gluteal fold, where the thigh is"
        " still merged with the pelvis on this topology. No section plane"
        " isolates one thigh loop there: the measured perimeter swings from"
        " 17 to 54 cm with the selection radius, so any fit driven by it"
        " would be reading an unstable quantity. The mid-thigh station owns"
        " the leg circumference fit."
    ),
    "thighMidCircL": fit(
        "localChange", "l-upperleg-scale-horiz-incr", "circumference", "mid-thigh",
        extra=("l-upperleg-scale-depth-incr",),
    ),
    "thighMidCircR": fit(
        "localChange", "r-upperleg-scale-horiz-incr", "circumference", "mid-thigh",
        extra=("r-upperleg-scale-depth-incr",),
    ),
    "calfCircL": fit(
        "localChange", "l-lowerleg-scale-horiz-incr", "circumference", "calf",
        extra=("l-lowerleg-scale-depth-incr",),
    ),
    "calfCircR": fit(
        "localChange", "r-lowerleg-scale-horiz-incr", "circumference", "calf",
        extra=("r-lowerleg-scale-depth-incr",),
    ),
    "ankleCircL": fit(
        "localChange", "measure-ankle-circ-incr", "circumference", "ankle",
        paired=("ankleCircR",),
    ),
    "ankleCircR": fit(
        "localChange", "measure-ankle-circ-incr", "circumference", "ankle",
        paired=("ankleCircL",),
    ),
    "kneeCircL": fit(
        "localChange", "measure-knee-circ-incr", "circumference", "knee",
        paired=("kneeCircR",),
    ),
    "kneeCircR": fit(
        "localChange", "measure-knee-circ-incr", "circumference", "knee",
        paired=("kneeCircL",),
    ),
    "kneeHeightL": fit(
        "localChange", "measure-lowerleg-height-incr", "height", "floor-to-knee",
        paired=("kneeHeightR",),
    ),
    "kneeHeightR": fit(
        "localChange", "measure-lowerleg-height-incr", "height", "floor-to-knee",
        paired=("kneeHeightL",),
    ),
    "lowerLegLengthL": fit(
        "localChange", "measure-lowerleg-height-incr", "length", "knee-to-ankle",
        paired=("lowerLegLengthR",),
    ),
    "lowerLegLengthR": fit(
        "localChange", "measure-lowerleg-height-incr", "length", "knee-to-ankle",
        paired=("lowerLegLengthL",),
    ),
    "crotchKneeL": fit(
        "localChange", "measure-upperleg-height-incr", "length", "crotch-to-knee",
        paired=("crotchKneeR",),
    ),
    "crotchKneeR": fit(
        "localChange", "measure-upperleg-height-incr", "length", "crotch-to-knee",
        paired=("crotchKneeL",),
    ),
    "inseamL": fit(
        "localChange", "measure-upperleg-height-incr", "length", "crotch-to-floor",
        paired=("inseamR",), extra=("measure-lowerleg-height-incr",),
    ),
    "inseamR": fit(
        "localChange", "measure-upperleg-height-incr", "length", "crotch-to-floor",
        paired=("inseamL",), extra=("measure-lowerleg-height-incr",),
    ),
    "outseamL": fit(
        "localChange", "measure-waisttohip-dist-incr", "length", "waist-to-floor",
        paired=("outseamR",),
        extra=("measure-upperleg-height-incr", "measure-lowerleg-height-incr"),
    ),
    "outseamR": fit(
        "localChange", "measure-waisttohip-dist-incr", "length", "waist-to-floor",
        paired=("outseamL",),
        extra=("measure-upperleg-height-incr", "measure-lowerleg-height-incr"),
    ),
    "waistKneeL": fit(
        "localChange", "measure-waisttohip-dist-incr", "length", "waist-to-knee",
        paired=("waistKneeR",), extra=("measure-upperleg-height-incr",),
    ),
    "waistKneeR": fit(
        "localChange", "measure-waisttohip-dist-incr", "length", "waist-to-knee",
        paired=("waistKneeL",), extra=("measure-upperleg-height-incr",),
    ),
    "kneeAngleL": direct("localChange", "l-leg-valgus-incr", 1.0 / 15.0, 0.0, -1.0, 1.0),
    "kneeAngleR": direct("localChange", "r-leg-valgus-incr", 1.0 / 15.0, 0.0, -1.0, 1.0),
    "legOffsetL": unsupported(POSTURE_REASON),
    "legOffsetR": unsupported(POSTURE_REASON),
    # Feet.
    "footLengthL": fit("localChange", "l-foot-scale-depth-incr", "length", "foot"),
    "footLengthR": fit("localChange", "r-foot-scale-depth-incr", "length", "foot"),
    "footWidthL": fit("localChange", "l-foot-scale-horiz-incr", "width", "foot"),
    "footWidthR": fit("localChange", "r-foot-scale-horiz-incr", "width", "foot"),
    "ballGirthL": fit(
        "localChange", "l-foot-scale-horiz-incr", "circumference", "foot-ball",
        extra=("l-foot-scale-vert-incr",),
    ),
    "ballGirthR": fit(
        "localChange", "r-foot-scale-horiz-incr", "circumference", "foot-ball",
        extra=("r-foot-scale-vert-incr",),
    ),
    "heelGirthL": fit("localChange", "l-foot-scale-vert-incr", "circumference", "heel-instep"),
    "heelGirthR": fit("localChange", "r-foot-scale-vert-incr", "circumference", "heel-instep"),
    "archHeightL": unsupported("Anny has no foot-arch height target."),
    "archHeightR": unsupported("Anny has no foot-arch height target."),
    "footAngleL": unsupported(POSTURE_REASON),
    "footAngleR": unsupported(POSTURE_REASON),
    # Hands.
    "handLengthL": fit(
        "localChange", "l-hand-scale-incr", "length", "hand",
        extra=("l-hand-fingers-length-incr",),
    ),
    "handLengthR": fit(
        "localChange", "r-hand-scale-incr", "length", "hand",
        extra=("r-hand-fingers-length-incr",),
    ),
    "palmWidthL": fit("localChange", "l-hand-scale-incr", "width", "palm"),
    "palmWidthR": fit("localChange", "r-hand-scale-incr", "width", "palm"),
    "palmCircL": fit("localChange", "l-hand-scale-incr", "circumference", "palm"),
    "palmCircR": fit("localChange", "r-hand-scale-incr", "circumference", "palm"),
    "thumbBaseCircL": unsupported("Anny has no thumb-base target."),
    "thumbBaseCircR": unsupported("Anny has no thumb-base target."),
    # Global composition.
    "softTissue": direct("phenotype", "weight", 0.01, 0.0, 0.0, 1.0),
    "muscleDefinition": direct("phenotype", "muscle", 0.005, 0.5, 0.0, 1.0),
    "lowerBodyDistribution": direct("phenotype", "proportions", 0.01, 0.0, 0.0, 1.0),
    "upperBodyDistribution": unsupported(
        "This value is the declared complement of lowerBodyDistribution; a"
        " single Anny proportions phenotype owns the ratio, so mapping both"
        " would drive one target twice."
    ),
    # Posture angles.
    "shoulderSlopeL": unsupported(POSTURE_REASON),
    "shoulderSlopeR": unsupported(POSTURE_REASON),
    "shoulderRollL": unsupported(POSTURE_REASON),
    "shoulderRollR": unsupported(POSTURE_REASON),
    "pelvicTilt": unsupported(POSTURE_REASON),
    "torsoLean": unsupported(POSTURE_REASON),
    "torsoTwist": unsupported(POSTURE_REASON),
    # Shoulder lengths participate in the shoulder-breadth fit.
    "shoulderLengthL": fit(
        "localChange", "measure-shoulder-dist-incr", "length", "neck-to-shoulder-tip",
        paired=("shoulderLengthR",),
    ),
    "shoulderLengthR": fit(
        "localChange", "measure-shoulder-dist-incr", "length", "neck-to-shoulder-tip",
        paired=("shoulderLengthL",),
    ),
}


CUSTOM_CONTROL_REASON = (
    "User-defined custom measurement with no declared Anny anatomical target;"
    " the bakeoff cannot claim a body change for it."
)
