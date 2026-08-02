# Patterna Unreal vertical slice

This project isolates the replacement 3D stack from the working WinUI application. It uses Unreal Engine 5.8, MetaHuman Creator, Chaos Cloth Asset, Dataflow cloth nodes, OpenUSD cloth interchange, DirectX 12, Lumen, virtual shadow maps, and hardware ray tracing.

## Current avatar baseline

`MH_Patterna_Female_Default` is the production avatar baseline. It is a female MetaHuman with a full joints-and-blend-shapes rig, 2K face and body source textures, skin shading, eyes, hands, feet, and a groomed hairstyle. The female shape is only the starting state. The measurement workflow must remain able to replace every estimated dimension and drive the parametric body controls before garment simulation.

The editor project explicitly enables `PythonScriptPlugin` and `EditorScriptingUtilities`. These bundled Unreal plugins are required by the staged measurement scripts in `tools` and must be loaded before a `py` console command is treated as executed.

## Acceptance gate

The Unreal viewport must not replace the WinUI WebGL preview until all of these checks pass:

1. The female default MetaHuman is visible with production skin, eyes, hands, feet, and hair rendering.
2. One garment is constructed from separate 2D-derived panels with explicit named seam pairs.
3. The garment settles under gravity and preserves warp, weft, shear, bend, damping, friction, and density controls.
4. Body collision has no visible penetration from front, side, rear, or oblique acceptance views.
5. The render mesh has thickness and detail while a separate single-sided simulation mesh drives it.
6. The garment can resize or regenerate after body measurements change.
7. A machine-readable adapter can translate the WinUI garment document into the Unreal cloth input format.

The existing WinUI measurement editor and versioned garment document remain authoritative while this gate is incomplete.

## Runtime validation scene

The native `PatternaUnreal` runtime module spawns `APatternaAvatarPreviewActor` through `APatternaPreviewGameMode` when play begins. The preview actor instantiates the measured V2 `BP_MH_Patterna_Female_Default` character with its baked skin, eyes, teeth, face rig, body rig, and groom components. It finds the assembled body component, supplies that component as the imported Chaos Cloth skirt's pose leader, samples live torso cross-sections, and builds a transient garment-only collision asset around the measured waist and seat. The original limb primitives remain available while oversized circular pelvis and lower-torso capsules are removed from the garment collision source. The scene enables cloth simulation and opens on a fixed front inspection view with neutral lighting. `Patterna.ViewAngle 90`, `Patterna.ViewAngle 0`, and `Patterna.ViewAngle 270` select exact front, side, and rear views.

This scene is the visual proof surface for gravity, collision, seam closure, material response, and multi-angle penetration checks. A successful module build proves only that the integration compiles. The garment must still be inspected while the scene is running before the Unreal viewport can replace the WinUI prototype.

Launch with `-PatternaCaptureViews` to let the garment settle and write exact front, right-side, rear, left-side, front-oblique, rear-oblique, and fabric-detail PNG files to `Saved/Patterna/AcceptanceViews`. This mode is suitable for repeatable visual comparison and can run with `-RenderOffscreen`; it does not replace geometric penetration checks or animated-pose validation.

## Patterna bridge input

The WinUI app writes `current.patterna-unreal.json` to its local `UnrealBridge` folder whenever body, pattern, or fabric inputs change. The file uses schema `patterna.unreal-bridge/1.0` and retains all 145 detailed body controls, manual override origin, custom landmarks, the full garment document, and the selected fabric properties.

Generate the Unreal cloth interchange files from that current state and the measured runtime body profile with:

```powershell
.\tools\Generate-PatternaUnrealGarment.ps1 -BridgeDocumentPath '<path-to-current.patterna-unreal.json>' -BodyProfilePath '.\PatternaUnreal\Saved\Patterna\LiveBodyProfile.json'
```

The generator validates both schemas and ranges, rejects implausible or arm-contaminated torso sections, derives the effective garment support height from the closest live body circumference, interpolates angular samples from the evaluated body surface for upper dressing rows, preserves the editable skirt panel's cubic balanced hem, and records both input SHA-256 values in its output manifest. The requested body measurement and two-dimensional pattern rest dimensions remain unchanged. Material conversions remain explicitly uncalibrated until physical swatch tests are available.

The complete wrap-dress lane uses the stricter .NET compiler instead of the skirt-specific PowerShell adapter. It validates every panel's seam participation, seam-length mismatch, structured mesh quality, continuous seam closure, initial strain distribution, and measured body clearance before writing Unreal files. Generate the isolated factory-default proof package with:

```powershell
dotnet run --project .\Patternal.UnrealGarmentCompiler\Patternal.UnrealGarmentCompiler.csproj -- --factory-default --body-profile .\PatternaUnreal\Saved\Patterna\LiveBodyProfile.json --output .\PatternaUnreal\SourceAssets\PatternaWrapDressV1\FullGarmentPreflight.json --bridge-output .\PatternaUnreal\SourceAssets\PatternaWrapDressV1\PatternaWrapDress.bridge.json --usd-output .\PatternaUnreal\SourceAssets\PatternaWrapDressV1\PatternaWrapDress.usda --manifest-output .\PatternaUnreal\SourceAssets\PatternaWrapDressV1\PatternaWrapDress.garment.json
```

The current source contains 8 simulation patterns, 8 render patterns, 11 permanent construction seams, 3 explicit closure relationships, 12,976 source simulation vertices, 24,576 triangles, and 275 combined stitch constraints. The wrap center-front edges remain free except where the tack, waist pin, and tie buckle closures act. The compiler stages exact 2D-rest panels, validates seam and closure direction, and converts Unreal's left-handed coordinates to right-handed OpenUSD by reflecting Y and reversing winding. The latest V8 capture advances 600 solver frames at 12 iterations and 4 substeps. It is rejected because the bodice and waist remain visibly discontinuous and the initial arrangement reaches 40.7 percent peak edge strain.

The isolated shirt lane now uses the body-specific `PatternaFemaleAdaptiveCrewNeck.specification.json` source. Generate or update it against the exact MetaHuman body YAML, export its GarmentCode mesh, run Warp pre-fitting, and then compile the accepted pre-fit surface into `PatternaFemaleShirt.usda`. The current garment has 8 panels, 16 construction seams, 316 stitches, 6,076 simulation vertices, and 11,312 triangles. The manifest records the exact counts that Unreal uses for saved-asset validation, so topology changes no longer require matching hardcoded validator constants.

Use `Patterna.ReimportAndRepairShirtClothBindings` after regenerating the USDA, and launch the runtime with `-PatternaShirtPreview -PatternaCaptureViews` to write seven views under `Saved/Patterna/ShirtAcceptanceViews`. The shirt preview renders the accepted Warp equilibrium by default. Pass `-PatternaEnableChaosRefinement` only to inspect the experimental Chaos handoff, which uses a 0.08 cm collision envelope and bounds motion to 5 cm but still fails the underarm continuity gate. This diagnostic deliberately renders from the final simulation mesh because the generic subdivided proxy produced visibly shredded deformation across sewn panels. A seam-aware detailed render surface and a stable interactive seam handoff are still required before this path is production-ready.

Export the exact posed body used by the runtime with:

```powershell
& 'C:\Program Files\Epic Games\UE_5.8\Engine\Binaries\Win64\UnrealEditor-Cmd.exe' .\PatternaUnreal.uproject -unattended -nosplash -RenderOffscreen -PatternaExportLiveBodyMesh
```

The output is `Saved/Patterna/LiveBodyMesh.obj`. `tools/prepare_metahuman_garmentcode_body.py` converts it into the watertight GarmentCode collider and body-specific segmentation inputs. `tools/prefit_garmentcode_warp.py` writes the pre-fit OBJ and normalized collision report consumed by the .NET compiler.

## Resizable outfit architecture

The project now enables Unreal 5.8 `ChaosOutfitAsset`. The editor command `Patterna.BuildResizableFullDressOutfit` packages the current cloth source with the measured female MetaHuman body and face as one source size and computes a 2,000-point resizing field. The current immutable build is `/Game/Outfits/PatternaWrapDress/PatternaWrapDress/PatternaWrapDress_ResizableV8`.

This asset proves parametric packaging, runtime loading, simulation-driven sewing, and separate closure constraints. It does not yet prove production drape. V8 is blocked by visible bodice continuity and strain failures, not by missing closure representation. See `docs/architecture-v2.md` in the repository root.

The repair command also creates project-local cotton-poplin color and tangent-space normal textures and connects them to the two-sided cloth material in pattern UV space. It restores the authoritative imported render collection after Dataflow regeneration when that collection contains higher-detail geometry. The current LOD 0 keeps 7,934 render vertices and 14,592 faces, including render-only waist, hem, and side-seam ribbons. Imported vertex color darkens those construction ribbons without changing simulation mass or stiffness. The full-body views judge silhouette and drape; `Patterna-07-fabric-detail.png` is the macro evidence for yarn-scale shading and side-seam construction. These procedural maps and thread colors are visual placeholders until scanned or measured material data is available.

Run the bridge contract and deterministic-generation checks with:

```powershell
.\tools\Test-PatternaUnrealBridge.ps1 -BridgeDocumentPath '<path-to-current.patterna-unreal.json>' -BodyProfilePath '.\PatternaUnreal\Saved\Patterna\LiveBodyProfile.json'
```
