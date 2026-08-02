import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path

import unreal


CHARACTER_PATH = "/Game/MH_Patterna_Female_Default.MH_Patterna_Female_Default"
ASSEMBLED_ROOT_PATH = "/Game/PatternaMeasuredV2"
BACKUP_PATH = (
    Path(unreal.Paths.project_dir())
    / "Backups"
    / "MH_Patterna_Female_Default.before-measurements.uasset"
)
SOURCE_ASSET_PATH = (
    Path(unreal.Paths.project_content_dir()) / "MH_Patterna_Female_Default.uasset"
)
ASSEMBLED_BODY_PATH = (
    Path(unreal.Paths.project_content_dir())
    / "PatternaMeasuredV2"
    / "MH_Patterna_Female_Default"
    / "Body"
    / "SKM_MH_Patterna_Female_Default_BodyMesh.uasset"
)
REPORT_PATH = (
    Path(unreal.Paths.project_saved_dir())
    / "Patterna"
    / "MetaHumanMeasurementApplyReport.json"
)


def find_bridge_document():
    override = os.environ.get("PATTERNA_UNREAL_BRIDGE_PATH")
    if override:
        override_path = Path(override)
        if not override_path.is_file():
            raise RuntimeError(
                f"PATTERNA_UNREAL_BRIDGE_PATH does not exist: {override_path}"
            )
        return override_path

    local_app_data = Path(os.environ["LOCALAPPDATA"])
    candidates = list(
        (local_app_data / "Packages").glob(
            "*/LocalState/UnrealBridge/current.patterna-unreal.json"
        )
    )
    candidates.extend(
        (local_app_data / "Patterna" / "UnrealBridge").glob(
            "current.patterna-unreal.json"
        )
    )
    if not candidates:
        raise RuntimeError("Patterna's current Unreal bridge document was not found.")
    return max(candidates, key=lambda item: item.stat().st_mtime)


def load_measurements(bridge_path):
    bridge = json.loads(bridge_path.read_text(encoding="utf-8"))
    if bridge.get("schemaVersion") != "patterna.unreal-bridge/1.0":
        raise RuntimeError(
            f"Unsupported Patterna Unreal bridge schema: {bridge.get('schemaVersion')}"
        )

    measurements = {}
    for item in bridge.get("body", {}).get("measurements", []):
        key = str(item["key"])
        measurements[key] = {
            "value": float(item["value"]),
            "unit": str(item.get("unit", "cm")),
            "origin": str(item.get("origin", "unknown")),
        }
    return bridge, measurements


def value_of(measurements, key):
    if key not in measurements:
        raise RuntimeError(f"Patterna measurement is missing: {key}")
    return measurements[key]["value"]


def average_of(measurements, *keys):
    return sum(value_of(measurements, key) for key in keys) / len(keys)


def measurement_targets(measurements):
    return {
        "Height": (value_of(measurements, "height"), ["height"]),
        "Shoulder Height": (
            value_of(measurements, "height")
            - value_of(measurements, "crownChin"),
            ["height", "crownChin"],
        ),
        "Across Shoulder": (
            value_of(measurements, "shoulder"),
            ["shoulder"],
        ),
        "Shoulder to Apex": (
            average_of(measurements, "bustHeightL", "bustHeightR"),
            ["bustHeightL", "bustHeightR"],
        ),
        "Front Interscye Length": (
            value_of(measurements, "acrossFront"),
            ["acrossFront"],
        ),
        "Chest": (value_of(measurements, "chest"), ["chest"]),
        "Bust Span": (
            value_of(measurements, "bustSeparation"),
            ["bustSeparation"],
        ),
        "Underbust": (
            value_of(measurements, "underBust"),
            ["underBust"],
        ),
        "Neck to Waist": (value_of(measurements, "torso"), ["torso"]),
        "Waist": (value_of(measurements, "waist"), ["waist"]),
        "High Hip": (
            value_of(measurements, "highHipCirc"),
            ["highHipCirc"],
        ),
        "Hip": (value_of(measurements, "hip"), ["hip"]),
        "Rise": (
            value_of(measurements, "crotchLength"),
            ["crotchLength"],
        ),
        "Neck": (value_of(measurements, "neckCirc"), ["neckCirc"]),
        "Neck Base": (
            value_of(measurements, "neckBaseCirc"),
            ["neckBaseCirc"],
        ),
        "Neck Length": (
            average_of(measurements, "neckLengthFront", "neckLengthBack"),
            ["neckLengthFront", "neckLengthBack"],
        ),
        "Upper Arm Length": (
            average_of(measurements, "shoulderElbowL", "shoulderElbowR"),
            ["shoulderElbowL", "shoulderElbowR"],
        ),
        "Lower Arm Length": (
            average_of(measurements, "elbowWristL", "elbowWristR"),
            ["elbowWristL", "elbowWristR"],
        ),
        "Forearm": (
            average_of(measurements, "forearmCircL", "forearmCircR"),
            ["forearmCircL", "forearmCircR"],
        ),
        "Bicep": (
            average_of(measurements, "upperArmCircL", "upperArmCircR"),
            ["upperArmCircL", "upperArmCircR"],
        ),
        "Elbow": (
            average_of(measurements, "elbowCircL", "elbowCircR"),
            ["elbowCircL", "elbowCircR"],
        ),
        "Wrist": (
            average_of(measurements, "wristCircL", "wristCircR"),
            ["wristCircL", "wristCircR"],
        ),
        "Hand Circumference": (
            average_of(measurements, "palmCircL", "palmCircR"),
            ["palmCircL", "palmCircR"],
        ),
        "Inseam": (
            average_of(measurements, "inseamL", "inseamR"),
            ["inseamL", "inseamR"],
        ),
        "Thigh": (
            average_of(measurements, "thighUpperCircL", "thighUpperCircR"),
            ["thighUpperCircL", "thighUpperCircR"],
        ),
        "Knee": (
            average_of(measurements, "kneeCircL", "kneeCircR"),
            ["kneeCircL", "kneeCircR"],
        ),
        "Calf": (
            average_of(measurements, "calfCircL", "calfCircR"),
            ["calfCircL", "calfCircR"],
        ),
    }


def clamp(value, minimum, maximum):
    return max(minimum, min(maximum, value))


def target_from_percentage(measurements, key, minimum, maximum):
    percentage = clamp(value_of(measurements, key), 0.0, 100.0)
    return minimum + ((maximum - minimum) * percentage / 100.0)


def sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def verify_source_backup():
    if not SOURCE_ASSET_PATH.is_file():
        raise RuntimeError(f"MetaHuman source asset is missing: {SOURCE_ASSET_PATH}")
    if not BACKUP_PATH.is_file():
        raise RuntimeError(f"MetaHuman source backup is missing: {BACKUP_PATH}")
    source_hash = sha256(SOURCE_ASSET_PATH)
    backup_hash = sha256(BACKUP_PATH)
    prior_backup_hash = None
    if REPORT_PATH.is_file():
        prior_report = json.loads(REPORT_PATH.read_text(encoding="utf-8"))
        prior_backup_hash = prior_report.get("backupSha256")
    if prior_backup_hash:
        if backup_hash != prior_backup_hash:
            raise RuntimeError(
                "MetaHuman source backup changed after the first measurement run."
            )
    elif source_hash != backup_hash:
        raise RuntimeError(
            "The first measurement run requires a byte-identical source backup."
        )
    return backup_hash, source_hash == backup_hash


def write_stage(status, bridge_path, **details):
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    report = {
        "schemaVersion": "patterna.metahuman-measurement-apply/1.0",
        "generatedAtUtc": datetime.now(timezone.utc).isoformat(),
        "status": status,
        "character": CHARACTER_PATH,
        "backup": str(BACKUP_PATH),
        "bridgeDocument": str(bridge_path),
    }
    report.update(details)
    REPORT_PATH.write_text(json.dumps(report, indent=2), encoding="utf-8")
    unreal.log(f"Patterna MetaHuman measurement stage: {status}")


def apply_measurements():
    bridge_path = find_bridge_document()
    _, measurements = load_measurements(bridge_path)
    targets = measurement_targets(measurements)
    backup_hash, source_matched_backup = verify_source_backup()
    write_stage(
        "loading-character",
        bridge_path,
        backupVerified=True,
        backupSha256=backup_hash,
        sourceMatchedBackupBeforeRun=source_matched_backup,
    )
    character = unreal.load_asset(CHARACTER_PATH)
    if character is None:
        raise RuntimeError(f"Patterna MetaHuman Character was not found: {CHARACTER_PATH}")

    write_stage(
        "registering-character-for-edit",
        bridge_path,
        backupVerified=True,
        backupSha256=backup_hash,
        sourceMatchedBackupBeforeRun=source_matched_backup,
    )
    subsystem = unreal.get_editor_subsystem(unreal.MetaHumanCharacterEditorSubsystem)
    if not subsystem.try_add_object_to_edit(character):
        raise RuntimeError(
            "Patterna MetaHuman Character could not be opened for measurement editing."
        )

    applied = []
    missing_constraints = []
    try:
        write_stage(
            "reading-constraints",
            bridge_path,
            backupVerified=True,
            backupSha256=backup_hash,
            sourceMatchedBackupBeforeRun=source_matched_backup,
        )
        constraints = subsystem.get_body_constraints(character)
        constraint_indices = {
            str(item.name): index for index, item in enumerate(constraints)
        }
        mapped_constraint_names = set(targets) | {
            "Fat",
            "Masculine/Feminine",
            "Muscularity",
        }
        missing_target_constraints = sorted(
            mapped_constraint_names - set(constraint_indices)
        )
        unmapped_character_constraints = sorted(
            set(constraint_indices) - mapped_constraint_names
        )
        if missing_target_constraints or unmapped_character_constraints:
            raise RuntimeError(
                "Patterna's MetaHuman constraint map is incomplete. "
                f"Missing on character: {missing_target_constraints}; "
                f"unmapped on character: {unmapped_character_constraints}"
            )

        # Unreal Python returns copies when a struct is read from a reflected
        # array. Every edited constraint must be assigned back into the array
        # before SetBodyConstraints receives it.
        for index, item in enumerate(constraints):
            item.is_active = False
            constraints[index] = item

        feminine_index = constraint_indices.get("Masculine/Feminine")
        if feminine_index is not None:
            feminine_constraint = constraints[feminine_index]
            feminine_constraint.is_active = True
            constraints[feminine_index] = feminine_constraint
            applied.append(
                {
                    "constraint": "Masculine/Feminine",
                    "requested": float(feminine_constraint.target_measurement),
                    "applied": float(feminine_constraint.target_measurement),
                    "minimum": float(feminine_constraint.min_measurement),
                    "maximum": float(feminine_constraint.max_measurement),
                    "patternaMeasurements": ["female-baseline-preserved"],
                    "clamped": False,
                }
            )

        for constraint_name, percentage_key in (
            ("Muscularity", "muscleDefinition"),
            ("Fat", "softTissue"),
        ):
            constraint_index = constraint_indices.get(constraint_name)
            if constraint_index is None:
                missing_constraints.append(constraint_name)
                continue
            item = constraints[constraint_index]
            requested = target_from_percentage(
                measurements,
                percentage_key,
                float(item.min_measurement),
                float(item.max_measurement),
            )
            item.is_active = True
            item.target_measurement = requested
            constraints[constraint_index] = item
            applied.append(
                {
                    "constraint": constraint_name,
                    "requested": requested,
                    "applied": requested,
                    "minimum": float(item.min_measurement),
                    "maximum": float(item.max_measurement),
                    "patternaMeasurements": [percentage_key],
                    "clamped": False,
                }
            )

        for constraint_name, (requested, source_keys) in targets.items():
            constraint_index = constraint_indices.get(constraint_name)
            if constraint_index is None:
                missing_constraints.append(constraint_name)
                continue
            item = constraints[constraint_index]
            minimum = float(item.min_measurement)
            maximum = float(item.max_measurement)
            applied_value = clamp(requested, minimum, maximum)
            item.is_active = True
            item.target_measurement = applied_value
            constraints[constraint_index] = item
            applied.append(
                {
                    "constraint": constraint_name,
                    "requested": requested,
                    "applied": applied_value,
                    "minimum": minimum,
                    "maximum": maximum,
                    "patternaMeasurements": source_keys,
                    "clamped": applied_value != requested,
                }
            )

        write_stage(
            "fitting-constraints",
            bridge_path,
            backupVerified=True,
            backupSha256=backup_hash,
            sourceMatchedBackupBeforeRun=source_matched_backup,
            bodyConstraintCount=len(constraints),
            appliedConstraintCount=len(applied),
        )
        subsystem.set_body_constraints(character, constraints)
        effective_constraints = subsystem.get_body_constraints(character)
        effective_constraint_map = {
            str(item.name): item for item in effective_constraints
        }
        ineffective_constraints = []
        for applied_item in applied:
            constraint_name = applied_item["constraint"]
            effective_item = effective_constraint_map.get(constraint_name)
            expected_value = float(applied_item["applied"])
            if (
                effective_item is None
                or not bool(effective_item.is_active)
                or abs(float(effective_item.target_measurement) - expected_value) > 0.01
            ):
                ineffective_constraints.append(constraint_name)
        if ineffective_constraints:
            raise RuntimeError(
                "MetaHuman rejected or lost active body constraints before commit: "
                f"{sorted(ineffective_constraints)}"
            )

        diagnostics = unreal.PatternaMetaHumanEditorLibrary.get_body_state_diagnostics(
            character
        )
        global_delta_scale, lod_zero_vertex_count, minimum, maximum = diagnostics
        evaluated_sections = (
            unreal.PatternaMetaHumanEditorLibrary.get_evaluated_body_cross_sections(
                character,
                [97.0, 99.0, 101.0, 103.0, 105.0, 107.0, 109.0],
            )
        )
        source_body_diagnostics = {
            "globalDeltaScale": float(global_delta_scale),
            "lodZeroVertexCount": int(lod_zero_vertex_count),
            "boundsCm": {
                "minimum": [float(minimum.x), float(minimum.y), float(minimum.z)],
                "maximum": [float(maximum.x), float(maximum.y), float(maximum.z)],
            },
            "crossSections": [
                {
                    "heightCm": float(section.x),
                    "widthCm": float(section.y),
                    "depthCm": float(section.z),
                    "ellipseCircumferenceCm": float(section.w),
                }
                for section in evaluated_sections
            ],
        }
        subsystem.commit_body_state(character)
        if not unreal.EditorAssetLibrary.save_loaded_asset(
            character, only_if_is_dirty=False
        ):
            raise RuntimeError(f"Could not save the measured MetaHuman: {CHARACTER_PATH}")

        rig_state_before = unreal.PatternaMetaHumanEditorLibrary.get_body_rig_state(
            character
        )
        write_stage(
            "regenerating-rig-from-measured-body",
            bridge_path,
            backupVerified=True,
            backupSha256=backup_hash,
            sourceMatchedBackupBeforeRun=source_matched_backup,
            bodyConstraintCount=len(constraints),
            appliedConstraintCount=len(applied),
            bodyRigStateBefore=rig_state_before,
        )
        auto_rigging_request = unreal.MetaHumanCharacterAutoRiggingRequestParams()
        auto_rigging_request.blocking = True
        auto_rigging_request.report_progress = False
        auto_rigging_request.rig_type = unreal.MetaHumanRigType.JOINTS_AND_BLEND_SHAPES
        subsystem.request_auto_rigging(character, auto_rigging_request)
        rig_state_after = unreal.PatternaMetaHumanEditorLibrary.get_body_rig_state(
            character
        )
        if (rig_state_after & 1) == 0:
            raise RuntimeError(
                "MetaHuman auto-rigging completed without a body DNA buffer."
            )
        if not unreal.EditorAssetLibrary.save_loaded_asset(
            character, only_if_is_dirty=False
        ):
            raise RuntimeError(
                f"Could not save the regenerated measured rig: {CHARACTER_PATH}"
            )

        REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
        report = {
            "schemaVersion": "patterna.metahuman-measurement-apply/1.0",
            "generatedAtUtc": datetime.now(timezone.utc).isoformat(),
            "status": "measurements-committed",
            "character": CHARACTER_PATH,
            "backup": str(BACKUP_PATH),
            "backupVerified": True,
            "backupSha256": backup_hash,
            "sourceMatchedBackupBeforeRun": source_matched_backup,
            "bridgeDocument": str(bridge_path),
            "bodyConstraintCount": len(constraints),
            "appliedConstraintCount": len(applied),
            "appliedConstraints": applied,
            "missingConstraints": sorted(set(missing_constraints)),
            "sourceBodyDiagnostics": source_body_diagnostics,
            "bodyRigRegenerated": True,
            "bodyRigStateBefore": rig_state_before,
            "bodyRigStateAfter": rig_state_after,
            "assembledBuildPath": ASSEMBLED_ROOT_PATH,
        }
        REPORT_PATH.write_text(json.dumps(report, indent=2), encoding="utf-8")
        unreal.log(
            "Patterna committed the measurement-driven body state. "
            "Starting optimized MetaHuman assembly."
        )

        build_params = unreal.MetaHumanCharacterEditorBuildParameters()
        build_params.pipeline_type = unreal.MetaHumanDefaultPipelineType.OPTIMIZED
        build_params.pipeline_quality = unreal.MetaHumanQualityLevel.MEDIUM
        build_params.absolute_build_path = ASSEMBLED_ROOT_PATH
        build_params.common_folder_path = f"{ASSEMBLED_ROOT_PATH}/Common"
        build_params.enable_wardrobe_item_validation = False

        assembled_body_mtime_before = (
            ASSEMBLED_BODY_PATH.stat().st_mtime_ns
            if ASSEMBLED_BODY_PATH.is_file()
            else None
        )
        if not subsystem.can_build_meta_human(character, True):
            raise RuntimeError("The measured Patterna MetaHuman is not ready for assembly.")
        subsystem.build_meta_human(character=character, params=build_params)
        if not unreal.EditorLoadingAndSavingUtils.save_dirty_packages(False, True):
            raise RuntimeError("Could not save the rebuilt MetaHuman content packages.")
        if not ASSEMBLED_BODY_PATH.is_file():
            raise RuntimeError(
                f"The rebuilt MetaHuman body package is missing: {ASSEMBLED_BODY_PATH}"
            )
        assembled_body_mtime_after = ASSEMBLED_BODY_PATH.stat().st_mtime_ns
        if (
            assembled_body_mtime_before is not None
            and assembled_body_mtime_after <= assembled_body_mtime_before
        ):
            raise RuntimeError(
                "MetaHuman assembly succeeded in memory but the body package did not "
                "change on disk."
            )

        report["generatedAtUtc"] = datetime.now(timezone.utc).isoformat()
        report["status"] = "assembled"
        report["assembledPackagesSaved"] = True
        report["assembledBody"] = str(ASSEMBLED_BODY_PATH)
        report["assembledBodySha256"] = sha256(ASSEMBLED_BODY_PATH)
        REPORT_PATH.write_text(json.dumps(report, indent=2), encoding="utf-8")
        unreal.log(
            "Patterna applied "
            f"{len(applied)} body constraints and rebuilt the MetaHuman. "
            f"Report: {REPORT_PATH}"
        )
    finally:
        if subsystem.is_object_added_for_editing(character):
            subsystem.remove_object_to_edit(character)


apply_measurements()
