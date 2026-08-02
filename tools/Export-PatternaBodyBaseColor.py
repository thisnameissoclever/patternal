import pathlib
import unreal


project_dir = pathlib.Path(unreal.Paths.project_dir())
output_path = project_dir / "Saved" / "Patterna" / "BodyTextureInspection" / "T_Body_BC.png"
output_path.parent.mkdir(parents=True, exist_ok=True)

texture = unreal.load_asset(
    "/Game/PatternaMeasuredV2/MH_Patterna_Female_Default/Body/Baked/T_Body_BC"
)
if texture is None:
    raise RuntimeError("Patterna body base-color texture could not be loaded.")

task = unreal.AssetExportTask()
task.object = texture
task.filename = str(output_path)
task.automated = True
task.prompt = False
task.replace_identical = True

if not unreal.Exporter.run_asset_export_task(task):
    raise RuntimeError("Patterna body base-color texture export failed.")

unreal.log(f"Patterna exported body base color to {output_path}")
