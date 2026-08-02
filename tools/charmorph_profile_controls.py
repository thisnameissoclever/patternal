#!/usr/bin/env python3
"""Patterna control contract for the CharMorph female avatar backend."""

from __future__ import annotations


PATTERNA_FULL_BUST_CONTROLS: dict[str, float] = {
    "Arms_UpperarmGirth": -0.66,
    "Arms_UpperarmMass": -0.58,
    "Arms_UpperarmSize": -0.44,
    "Arms_UpperarmTone": -0.72,
    "Chest_Girth": 0.00,
    "Chest_SizeX": 0.10,
    "Chest_SizeY": 0.05,
    "Abdomen_Mass": 0.00,
    "Pelvis_Girth": -0.05,
    "Pelvis_GluteusSize": 0.08,
    "Pelvis_SizeX": 0.00,
    "Pelvis_SizeY": 0.00,
    "Shoulders_Length": -0.20,
    "Shoulders_Mass": -0.48,
    "Shoulders_PosZ": -0.10,
    "Shoulders_Size": -0.30,
    "Shoulders_Tone": -0.55,
    "Stomach_LocalFat": 0.10,
    "Stomach_Volume": 0.00,
    "Torso_BreastMass": 0.58,
    "Torso_BreastPosX": -0.50,
    "Torso_BreastPosZ": 0.18,
    "Torso_BreastScaleY": -0.15,
    "Torso_BreastTone": 0.35,
    "Torso_BreastNipple": -0.80,
    "Torso_Mass": 0.05,
    "Torso_SizeX": 0.00,
    "Torso_SizeY": 0.00,
    "Torso_Tone": -0.20,
    "Waist_Size": 0.25,
}


FIT_CONTROL_NAMES = (
    "Abdomen_Mass",
    "Chest_Girth",
    "Chest_SizeX",
    "Chest_SizeY",
    "Pelvis_Girth",
    "Pelvis_SizeX",
    "Pelvis_SizeY",
    "Stomach_LocalFat",
    "Stomach_Volume",
    "Torso_BreastMass",
    "Torso_BreastPosX",
    "Torso_BreastScaleY",
    "Torso_Mass",
    "Torso_SizeX",
    "Torso_SizeY",
    "Waist_Size",
)

FIT_TARGET_NAMES = (
    "hip",
    "abdomen",
    "waist",
    "underbust",
    "bust",
    "bust_separation",
)

FIT_CONTROL_BOUNDS: dict[str, tuple[float, float]] = {
    "Abdomen_Mass": (-0.30, 0.35),
    "Chest_Girth": (-0.35, 0.40),
    "Chest_SizeX": (-0.20, 0.40),
    "Chest_SizeY": (-0.20, 0.40),
    "Pelvis_Girth": (-0.60, 0.35),
    "Pelvis_SizeX": (-0.30, 0.30),
    "Pelvis_SizeY": (-0.30, 0.30),
    "Stomach_LocalFat": (-0.30, 0.35),
    "Stomach_Volume": (-0.30, 0.35),
    "Torso_BreastMass": (0.35, 0.72),
    "Torso_BreastPosX": (-0.65, 0.10),
    "Torso_BreastScaleY": (-0.30, 0.15),
    "Torso_Mass": (-0.20, 0.35),
    "Torso_SizeX": (-0.30, 0.30),
    "Torso_SizeY": (-0.30, 0.30),
    "Waist_Size": (-0.20, 0.85),
}


def clamp_controls(controls: dict[str, float]) -> dict[str, float]:
    return {name: max(-1.0, min(1.0, float(value))) for name, value in controls.items()}


def measurement_targets(profile: dict[str, object]) -> dict[str, float]:
    body = profile.get("body")
    measurements = profile.get("measurements")
    if not isinstance(body, dict) or not isinstance(measurements, dict):
        raise ValueError("CharMorph fitting requires body and measurements objects")
    targets = {
        "hip": float(measurements.get("hip", body["hips"])),
        "abdomen": float(measurements["abdomenCirc"]),
        "waist": float(measurements.get("waist", body["waist"])),
        "underbust": float(measurements["underBust"]),
        "bust": float(measurements.get("chest", body["bust"])),
        "bust_separation": float(
            measurements.get("bustSeparation", body["bust_points"])
        ),
        "high_chest": float(measurements["highChestCirc"]),
    }
    if any(value <= 0.0 for value in targets.values()):
        raise ValueError("CharMorph measurement targets must be positive")
    return targets
