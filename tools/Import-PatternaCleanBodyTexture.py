import pathlib
import unreal


project_dir = pathlib.Path(unreal.Paths.project_dir())
source_path = (
    project_dir
    / "SourceAssets"
    / "PatternaBodyTextures"
    / "T_Body_BC_Clean.png"
)
destination_path = (
    "/Game/PatternaMeasuredGarments/V3/PatternaWrapDress/AvatarMaterials"
)
destination_name = "T_Body_BC_Clean"

if not source_path.is_file():
    raise RuntimeError(f"Clean Patterna body texture does not exist: {source_path}")

task = unreal.AssetImportTask()
task.filename = str(source_path)
task.destination_path = destination_path
task.destination_name = destination_name
task.automated = True
task.replace_existing = True
task.replace_existing_settings = True
task.save = True

unreal.AssetToolsHelpers.get_asset_tools().import_asset_tasks([task])
if not task.imported_object_paths:
    raise RuntimeError("Patterna clean body texture import produced no asset.")

texture_path = task.imported_object_paths[0]
texture = unreal.load_asset(texture_path)
if texture is None:
    raise RuntimeError(f"Imported Patterna clean body texture could not be loaded: {texture_path}")

texture.set_editor_property("srgb", True)
unreal.EditorAssetLibrary.save_loaded_asset(texture, only_if_is_dirty=False)
unreal.log(f"Patterna imported clean body base color: {texture.get_path_name()}")
