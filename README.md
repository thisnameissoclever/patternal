# Patternal

Patternal is a working WinUI 3 prototype for body-specific clothing pattern design. It combines a native Windows drafting workspace with an Unreal Engine 5.8 MetaHuman and Chaos Cloth validation project.

The repository preserves `Patterna` in existing document schemas, generated asset names, local runtime paths, and the Unreal module identity. Those names are compatibility identifiers, not the product name. New user-facing surfaces and the Windows executable use `Patternal`.

GarmentCode and NVIDIA Warp GarmentCode are vendored because Patternal owns project-specific solver, meshing, and body-asset changes in those trees. CharMorph, the CharMorph database, and MPFB2 remain pinned submodules.

The durable product goal, v1.0 acceptance gate, CLO capability ledger, solver strategy, and prioritized backlog are maintained in [`TODO.md`](TODO.md).

## Current vertical slice

1. A versioned garment document is the authoritative source for native 2D display, local snapshots, SVG export, named panel edges, seam metadata, and fabric physics metadata. The default workspace imports the accepted 14-panel GarmentCode crew-neck shirt with one uninterrupted front torso and one uninterrupted back torso. The five-piece wrap-dress document remains available as an explicitly experimental template.
2. Seam allowance, grainline, notch, piece selection, fit-to-view, and SVG export controls are functional. The editor exposes draggable boundary anchors and Bézier controls, exact coordinate and segment entry, stable piece IDs, and shared undo and redo across geometry, seam direction, and closure state. The Assembly mode displays every permanent seam and temporary closure on its actual source edges.
3. The product-facing 3D tab starts with the fitted CC-BY Antonia control avatar. The bundled current body, pattern, assembly, and fabric revision has no accepted cloth, so Patternal hides the stale garment and reports the exact mismatch instead of presenting it as current. The Simulate command exports the edited revision, fits the complete measured Antonia body, rebuilds the seam-aware pattern mesh, runs the current Newton control backend, applies compiler and visual-quality gates, and records one immutable revisioned job. Accepted output must preserve pattern-space UVs, seam and finished-edge groups, exact display-to-collider registration, and reviewed multi-angle evidence. A failed job remains blocked instead of displaying stale or rejected cloth.
4. Fabric presets expose weight, stretch, bend, and friction parameters.
5. The Unreal vertical slice renders the measured-body skirt and a resizable eight-panel wrap dress. V8 contains 11 permanent construction seams plus 3 explicit closure constraints and compiles to 275 combined stitches, but its current bodice continuity and 40.7 percent peak initial edge strain fail the product quality gate.
6. The default editable GarmentCode shirt has 14 pattern pieces and 34 construction seams. The bundled visual shirt contains 1,311 vertices and 5,048 face-corner UVs. Its fit report records 0 final inside-body vertices, 0.982 cm minimum clearance, and 1.703 cm maximum correction against the exact 167 cm, 92/71/99 cm default body. The inspector labels this as a body-aware production fit. Strain and equilibrium metrics appear only after the current editable revision completes the Warp acceptance pipeline.
7. The anatomical editor exposes 145 editable parameters at 0.1 cm precision across head, face, neck, chest, bust, back, waist, abdomen, pelvis, seat, arms, hands, legs, feet, posture, alignment, and surface-shape groups.
8. Left and right measurements remain independent. Linked proportional estimates can be disabled and every estimated value can be manually replaced.
9. User-defined measurement rows support uncommon landmarks outside the built-in profile.
10. Photo selection links local reference images to the avatar draft state without uploading them.
11. The WinUI 3D surface supports orbit, zoom, front, side, rear, oblique, and fit views. It renders a UV-mapped human display body with real skin, eyes, teeth, brows, lashes, and fitted hair while retaining the exact watertight body as the fit authority. Local snapshot persistence, responsive side panels, dark and light theme resources, and accessible control names are implemented.
12. Every viewport update writes a versioned `patterna.unreal-bridge/1.0` document to the app's local `UnrealBridge` folder. The document contains the complete editable body profile, manual-versus-estimated measurement origin, custom landmarks, authoritative garment document, fabric physics, topology diagnostics, and garment-derived generation bounds without assuming every garment contains a skirt piece. Simulation outputs live under a SHA-256 revision directory and are accepted only when their pattern, mesh, pre-fit, compiler report, and Unreal import all describe that same revision.

## Important prototype boundary

The app does not currently contain a trained photo-to-body reconstruction model, AI texture generation from user photos, a medically accurate body scanner, or a production finite-element cloth solver. The photo workflow is deliberately labeled as a local prototype. All 145 built-in measurements have an MPFB ruler, named target, bounded surface-deformation lane, or a combination of those paths, but non-default full-pipeline visual validation is still required.

The browser cloth solver is retained only as unreachable diagnostic code. It is not a product preview and must not be treated as fit evidence. The current Unreal proof simulates the skirt and the wrap-dress construction plus closure constraints, but the dress still fails bodice continuity, strain, and visual silhouette gates. It does not use calibrated physical material tests, support layered garments, provide full continuous-collision body animation, or provide production-grade fit accuracy comparable to CLO.

A production path would require validated body-reconstruction models, explicit consent and biometric-data controls, calibrated cloth-material datasets, sewing-grade geometric constraints, GPU compute, and fit validation against physical garments.

## Selected production path

The hand-built WebGL solver and custom circumference-shell garment arranger are not part of the production 3D core. The startup visual route uses a MakeHuman clothing proxy from the same body family, isolates its upper-garment component, and transfers only the correction needed to maintain 10 mm clearance from the exact default MPFB body. This prevents source-avatar mismatch from destroying the garment silhouette. It is deliberately separate from the editable physics route. A user-triggered revision uses GarmentCode panel construction, NVIDIA Warp XPBD equilibrium, compiler quality gates, a welded thin render surface with compiler-native face-varying UVs and construction groups, and direct embedded rendering. The renderer uses UV-mapped fabric shading without adding physical shell thickness. A revision-specific result is accepted only when body, pattern, fabric, topology, collision, equilibrium, and peak, broad, and localized strain evidence match one source revision. Unreal remains available for downstream diagnostic and animation research, but it is not on the product-critical display route. The replacement architecture is documented in [`docs/architecture-v2.md`](docs/architecture-v2.md).

The current immutable Outfit Asset is `/Game/Outfits/PatternaWrapDress/PatternaWrapDress/PatternaWrapDress_ResizableV8`. It packages one cloth source with the female MetaHuman body and face as source-body parts and a 2,000-point resizing field. Runtime loads it through `UChaosClothAssetBase` and simulates 8 panels, 11 permanent seams, 3 closure relationships, and 275 combined stitches. The next garment milestone is to repair the bodice and waist construction so those closures can settle a continuous, low-strain dress.

The WinUI 3D tab invalidates stale cloth, regenerates the current source through MPFB, GarmentCode, Warp, and the .NET compiler, and loads the matching body, visual avatar, garment, and evidence into the embedded renderer. Untouched GarmentCode input remains byte-exact so signed-zero coordinates, original circular curves, panel labels, source origins, and triangulation stay stable. Edited input uses the deterministic Patternal exporter. Automatic multi-angle capture refresh, animated-pose validation, layered garments, and geometric continuous-collision metrics remain required.

Detailed values entered by the user are persistent overrides. Linked proportional estimation can continue updating untouched measurements without replacing a manually entered dimension. The override state is included in local snapshots and in the Unreal bridge document.

Run the measurement-origin invariant directly against the application model with:

```powershell
.\tools\Test-PatternaMeasurementOverrides.ps1
```

The Unreal project now contains `MH_Patterna_Female_Default`, a saved female MetaHuman baseline with a full joints-and-blend-shapes rig, 2K face and body texture sources, production skin shading, and groomed hair. Female is the default presentation, not a locked body category. The current bridge applies and validates all 30 available MetaHuman body constraints, regenerates the body DNA, assembles into the clean `/Game/PatternaMeasuredV2` content root, explicitly saves generated packages, and records a SHA-256 hash for the assembled body. Runtime cross-section proof measures 71.21 cm at the avatar's 107 cm anatomical waist for the requested 71 cm waist. This verifies the waist slice only, not all 145 Patternal measurements.

The measured Chaos Cloth skirt now derives its placement from that live runtime body profile. It preserves the user-entered 103 cm outseam-derived height as the requested value, records 107 cm as the geometry-derived effective waist height, preserves the 73 cm two-dimensional waist rest circumference, and uses the same cubic balanced hem as the editable two-dimensional skirt panel instead of substituting a straight hem. The rebuilt runtime profile is now validated at 23 sections every 2 cm from 95 through 139 cm. Each section has at least 76 torso-filtered triangle-plane intersections and 31 retained angular surface points. That measured surface now drives the deterministic full-garment arrangement compiler as well as the skirt support shape. The evaluated body mesh ends near 139 cm, so neckline and neck collision still require the assembled MetaHuman physics surface instead of an extrapolated body section. The current proof asset uses 7,154 generated simulation vertices, 13,824 triangles, three LODs, a 0.35 cm collision shell, a shallow held top seam with a steep release into dynamic cloth, and matte two-sided cloth shading. Its separate LOD 0 render mesh retains 7,934 vertices and 14,592 faces after Dataflow regeneration, including six render-only waist, hem, and side-seam ribbons with restrained darker thread tinting. Its project-local material includes saved, pattern-UV cotton-poplin color and normal textures, with a dedicated macro acceptance image proving that the woven surface and construction detail survive material compilation and cloth deformation. This procedural texture is an appearance proxy, not a calibrated fabric scan. At runtime, a transient garment-only physics asset replaces oversized circular pelvis and lower-torso capsules with 184 overlapping spheres derived from seven live body cross-sections. Automated front, right-side, rear, left-side, and two oblique screenshots show no visible body breakthrough in the current static pose. Animated poses and geometric penetration metrics remain required before this can be called production-quality drape.

## Build and run

```powershell
git submodule update --init --recursive
dotnet build .\Patternal\Patternal.csproj -p:Platform=x64
dotnet run --project .\Patternal\Patternal.csproj -p:Platform=x64 --no-build
```

The project uses the packaged WinUI 3 model and the package-aware `dotnet run` support included by the Microsoft template.

Automated packaged UI interaction must use the isolated Hyper-V guest workflow in [`docs/isolated-windows-ui-testing.md`](docs/isolated-windows-ui-testing.md). The host builds and transfers the AppX payload through PowerShell Direct; all UI Automation and screenshots originate inside the guest so the user's host input and focus remain untouched.

For visual verification, do not launch `Patternal.exe` directly from the output folder. The registered debug AppX is a separate loose-layout payload. `dotnet run` invokes the WinApp staging target before activation. If a verification tool activates the existing AUMID directly, restage content first with:

```powershell
dotnet msbuild .\Patternal\Patternal.csproj -t:_WinAppCopyContentToLooseLayout -p:Configuration=Debug -p:Platform=x64 -p:RuntimeIdentifier=win-x64
```
