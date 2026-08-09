# Patternal architecture v3 reassessment

Status: active replacement boundary based on packaged UI evidence and local asset and solver bake-offs begun on 2026-08-08.

This document does not declare the product complete. It records why the present stack cannot honestly meet the CLO-class acceptance target and defines the smallest credible migration for a one-person, non-revenue project.

The detailed candidate, licensing, and one-person integration decision is maintained in `docs/open-source-foundation-decision.md`.

## Bottom line

Keep WinUI 3, the editable 2D document model, GarmentCode pattern exchange, Blender proof rendering, and the current Newton/Warp solver as a comparison backend. Replace the avatar product boundary, make cloth solvers interchangeable, and stop using numerical collision and strain reports as a substitute for visual acceptance.

The recommended target is:

1. CC-BY Antonia retained as the current fitted control, not treated as the production destination.
2. Apache-2.0 Meta Momentum Human Rig LOD1 as the first avatar challenger after dependency approval. Its release assets now include an explicit Apache-2.0 license, and Patterna already contains a narrow mesh bridge and measurement-fitting path.
3. Apache-2.0 and CC0 Anny retained as a semantic measurement and collision comparator, not a hero appearance source.
4. A separately reviewed masculine source. Reom may be a measurement and topology research input, but the vendored copy has no license or attribution artifact and its unsubdivided base is not acceptable as the hero display mesh. Do not redistribute it from Patterna until both problems are resolved.
5. A display mesh and a collision mesh derived from the same fitted body state but allowed to use different topology. Their registration must be proved numerically.
6. ZOZO's Apache-2.0 PPF Contact Solver as the first challenger in a controlled solver bake-off on the local RTX 4090.
7. Newton 1.4.0 with Warp 1.15.0 retained as the current control backend until another solver wins the same garment, body, material, contact, timing, and multi-view gates.
8. Blender as the canonical offline render and comparison boundary. The packaged WinUI/WebView2 viewer remains the interactive surface, but it should consume compact PBR GLB assets rather than giant raw OBJ files and ad hoc material rules.

## Evidence collected

### Packaged application

The isolated Windows 11 guest launched the registered AppX as a real responsive top-level window. Reviewed run `20260809-113435-c2c13a96` used payload `aa0885fc8f1dd486e078c5129a8a0dcc4097d570dacf0ef95a1df5a34e74d013`, ran 42 checks, captured 22 screenshots, passed 41 checks, and correctly failed only the current-cloth freshness gate. It covered the six semantic cameras, the complete current 2D authoring lifecycle, body and fabric sliders, panel and drawing toggles, fitted-bra availability, assembly direction editing, real SVG Save As, named project Save As and Open, and a local snapshot across two full process restarts. Host input injection and VMConnect use remained false.

Focused packaged run `20260809-113015-a9372bba` used payload `aa0885fc8f1dd486e078c5129a8a0dcc4097d570dacf0ef95a1df5a34e74d013` and passed all six persistence checks. It saved a 10,590-byte `patterna.project/1.0` file through the real Windows Save As picker, disturbed Height, linked proportions, and custom fabric weight, opened the named file through the real Windows Open picker, and restored Height 167.5 cm, linked proportions Off, and fabric weight 185 g/m² exactly. The separate local recovery snapshot still passed two process restarts. Host input injection and VMConnect use remained false.

The current package does not have current accepted cloth at startup. Its 3D surface reports that the bundled neckline, shoulder, armscye, sleeve cap, width distribution, or balance differs from the bundled simulation. Hiding that old cloth is correct. Shipping a baseline that immediately hides its only accepted garment is not.

The preserved reviewed run is `artifacts/isolated-ui/runs/20260809-113435-c2c13a96`. It is local evidence and is not a release artifact.

### 2D interface review

The packaged 1920 by 1080 workspace now uses geometry-aware deterministic packing, separate label headers, a scrollable canvas, and visible Zoom out, Zoom in, Fit, and Frame selected controls. Reviewed isolated run `20260809-041233-0852a5fd` shows all 14 exact pieces without overlap or clipping. Its automation sequence proved Zoom in and Fit against committed `ScrollViewer` state, restored the full layout at 89 percent, selected `Back Torso` through UI Automation, and framed that exact piece at 223 percent without host input injection.

Packaged run `20260809-124751-67e8517b` used payload `f260ae82d66f2570db88ca224f5ae656040a5ca586d3d2922e37db874717c126`, ran 46 checks, captured 23 screenshots, passed 45 checks, and failed only the truthful current-cloth freshness gate. Keyboard-only coverage proved toolbar focus order, Enter and Escape behavior in the real Save As and Open dialogs, Space activation for the four primary display toggles, 2D and 3D tab selection, a reversible Fabric weight edit, and visible focus. The UI Automation audit found 126 keyboard-focusable 2D controls and 39 keyboard-focusable 3D controls with zero missing accessible names. Manual review confirmed the complete 2D authoring sequence remained usable. Host input injection and VMConnect use remained false.

Focused packaged runs now cover the actual Windows Light, Dark, High Contrast Black, High Contrast White, High Contrast 1, and High Contrast 2 themes. Each run passed keyboard toggle and slider interaction, accessible-name, SVG export, named-project, and local-recovery checks; manual screenshot review confirmed readable pattern geometry, panels, focus, controls, and status messages. Full High Contrast 2 run `20260809-131811-0ced925b` passed every 2D and 3D interaction check and failed only the independent current-cloth freshness gate. The guest restored its exact original theme after every run. This closes the packaged theme-contrast gate, not the Narrator, avatar-quality, cloth-quality, or physical-GPU gates.

Packaged run `20260809-135415-0bfa3de5` used payload `18e435691da6fa9f0f6892fbbcf5054a3f472f23e0b96b049057b29d0f08ccdf` and proved the replacement stale-cloth presentation in all six semantic cameras. The status is now one accessible, single-line row above the viewport with a fixed regeneration action. Manual review confirmed that it no longer hides the body or floor. The run also reconfirmed that the fitted avatar, editable fallback, pose, anatomy, and placeholder garment remain visually rejected. Its named-project failure was isolated to a harness race against an asynchronous Save As; focused run `20260809-140321-bfcc5128` used the unchanged application payload and passed all 10 persistence actions after the harness required product success plus a complete schema-valid file. Host input injection and VMConnect use remained false.

Remaining accessibility gate:

1. Verify actual screen-reader announcements and task completion with Windows Narrator. UI Automation names are now proven, but that is not evidence of what Narrator speaks or whether its reading order is useful.

### 3D interface review

Observed problems:

1. The package opens to a stale cloth revision, so the six camera buttons only orbit an undressed avatar.
2. The stale notice previously covered a large portion of the lower body and competed with camera inspection. Run `20260809-135415-0bfa3de5` closed this interface defect by moving the state above the viewport.
3. The 130 MB raw garment OBJ makes the mixed XAML and WebView2 accessibility tree slow enough to interfere with UI Automation discovery.
4. The current display avatar is recognizably human but has exaggerated hands, feet, shoulder mass, calf mass, and an awkward presentation pose.
5. Texture and hair help the old body, but they cannot repair its silhouette and anatomy.
6. The camera labels were initially reversed for Front and Rear. Packaged screenshot review caught and corrected the production-avatar yaw mapping; interaction success alone had not proved camera semantics.
7. Existing collision, seam, strain, hash, and equilibrium gates all passed for an asset that still fails an ordinary visual review.
8. Returning to 3D after a long 2D authoring session initially left the WebGL canvas white while XAML state labels continued to update. The packaged renderer now starts one generation-owned render loop whenever 3D becomes visible, invalidates any suspended hidden-tab loop, reloads only after a reported WebGL context loss, and rejects blank late screenshots. Run `20260809-113435-c2c13a96` recorded a 1.0 non-white sample ratio for both edited and restored avatar views.
9. Full High Contrast 2 review proved the native 3D chrome, stale-state message, camera controls, visible focus, and six distinct camera results remain usable under Windows contrast overrides. It also reconfirmed that the fitted Antonia presentation and editable fallback are not production-quality avatars and that no current accepted cloth exists.

Required correction:

1. Do not package any baseline unless its complete current revision has accepted cloth.
2. Keep stale status in the compact non-modal evidence row above the viewport. This correction is implemented and packaged-review proven.
3. Use modest presentation clothing or underwear by default. A nude technical body may remain an explicit inspection mode.
4. Load a compact indexed GLB with PBR textures, normals, and optional level of detail. Keep the collision mesh out of the render payload.
5. Add anatomy, pose, material, silhouette, and fold-quality gates to the same multi-angle evidence required for release.

## Current stack inventory

| Layer | Current reality | License | Decision |
| --- | --- | --- | --- |
| Windows product shell | WinUI 3 with WebView2 3D surface | Microsoft platform terms | Keep |
| 2D pattern document | Native Patternal model with GarmentCode import and export | Project code plus MIT GarmentCode | Keep and improve UX |
| Bundled display body | MakeHuman and MPFB-derived mesh and CC0 appearance assets | CC0 assets; tool code varies | Retire as hero baseline after replacement proof |
| Current live source avatar path | CharMorph Antonia | Generated body is CC-BY 3.0 with attribution | Keep as the versioned control runtime; production visual gate remains open |
| Available feminine source | CharMorph Antonia | CC-BY 3.0 | Current control candidate, not the production destination |
| Available masculine source | CharMorph Reom | Declared CC-BY; license artifact missing | Research-only candidate; do not redistribute |
| First avatar challenger | Meta Momentum Human Rig LOD1 | Apache-2.0 code and assets; release ZIP now includes the license | Evaluate in a separate versioned CPU TorchScript runtime after approval |
| Measurement comparator | Anny 0.5 default or SOMA topology | Apache-2.0 code and CC0 or Apache-2.0 data | Keep for semantic fitting and collision comparisons, not hero appearance |
| Future topology and rig bridge | SOMA-X 0.1 | Apache-2.0 core; optional identity inputs retain separate terms | Defer until one avatar source wins |
| Appearance reference | Blender Human Base Meshes 1.4.1 | CC0 | Use as sculpt and topology reference only; not a parametric avatar |
| Current accepted cloth backend | Newton 1.4.0 `SolverStyle3D` on Warp 1.15.0 | Apache-2.0 | Keep as bake-off control |
| Legacy GarmentCode Python environment | Customized Warp 1.0.0b6 | Old NVIDIA source license | Isolate, replace, or remove after an import audit |
| Canonical offline rendering | Blender 4.5.11 LTS | GPL application; generated assets remain governed by their inputs | Keep |
| Packaged rendering | Custom WebGL in WebView2 over OBJ and PNG | Project code and bundled assets | Retain shell, replace payload format and material path |
| Unreal experiment | Unreal 5.8 garment target | Epic license | Keep diagnostic only unless it proves a complete handoff |

The two Python environments must not be described as one Warp dependency. Production simulation already uses modern Apache-2.0 Warp. The old restricted Warp exists because the vendored GarmentCode mesh stack imports custom `warp.collision` and `warp.sim` APIs. Removing it requires an import and output-equivalence audit, not a blind package upgrade.

## Avatar bake-off

Local deterministic Blender renders are stored under `artifacts/architecture-avatar-bakeoff`.

| Source | Vertices | Visual result | License result |
| --- | ---: | --- | --- |
| Antonia | 36,030 | Best overall silhouette, hands, and feet of the three local candidates, but the automated gate rejects its 0.1532 upper-arm ratio | Acceptable with attribution |
| `mb_female` | 18,210 | Reproduces oversized hands, feet, shoulders, and calves; extensive morph vocabulary does not repair the base silhouette | Reject for product output because generated meshes are AGPL-3.0 |
| Reom | 8,434 | Useful masculine proportions but visibly faceted torso and limbs at base resolution | The upstream metadata declares CC-BY, but the vendored character lacks a license or attribution file; do not ship it |

This bake-off used flat studio materials to compare geometry rather than flattering one candidate with better textures. It is not proof that Antonia already supports Patternal's 151 editable values. It proves that spending more time polishing `mb_female` would optimize the wrong base asset. The 2026-08-09 source refresh also moves MHR from license-blocked research to the first avatar challenger: its maintainer confirmed that the release assets are Apache 2.0 and added the license to `assets.zip`. That does not constitute a visual pass; it only permits the controlled bake-off described in `docs/open-source-foundation-decision.md`.

## Avatar architecture

### One fitted state, two meshes

The current architecture overvalues coordinate-identical display and collision topology. A professional avatar system needs different concerns:

1. The fitted state stores measurements, morph weights, pose parameters, landmarks, and provenance.
2. The collision body is watertight, stable, moderately dense, and free of fingers, hair, eyelashes, internal mouth surfaces, and other collision hazards.
3. The display body preserves anatomical topology, UVs, facial features, hands, feet, normals, and PBR materials.
4. A deterministic cage, barycentric, or nearest-surface binding maps both meshes to the same fitted state.
5. Registration gates limit landmark error, bidirectional surface distance, floor error, and garment-to-body clearance.

This removes the false choice between a solver-friendly body and a human-looking body.

### Required avatar gates

1. Height error at or below 1 mm.
2. Primary circumference error at or below the existing documented measurement tolerance.
3. Left-right landmark symmetry for a symmetric preset, with an explicit exception list for authored asymmetry.
4. Hand length, foot length, shoulder breadth, head height, arm span, and leg-length ratios inside reviewed human ranges.
5. No non-manifold collision edges, inverted faces, internal body surfaces, or open holes.
6. Display-to-collision surface distance reported by anatomical region, not only as one maximum.
7. Front, rear, left, right, and both oblique display renders approved at the packaged camera and canonical Blender camera.
8. Texture, normal, roughness, eye, hair, and underwear assets present and correctly licensed.

### Antonia migration spike

The first spike must not replace the shipped avatar. It must:

1. Generalize CharMorph character loading from hard-coded `mb_female`, `African`, `L2_packed/__main__.npz`, and `textures/albedo.png` values to the character's `config.yaml`.
2. Map a minimal measurement set to Antonia's named morphs and constrained surface corrections.
3. Export Antonia's multiple material regions, UVs, textures, eyes, mouth, lashes, and underwear to GLB.
4. Derive and validate a simplified collision proxy from the fitted Antonia surface.
5. Run the current production shirt through both the current Newton backend and the challenger backend.
6. Promote nothing until measurement, contact, visual, performance, and license gates pass together.

### Antonia spike result

The local spike now proves that Antonia is a viable replacement foundation, but it does not promote Antonia into the packaged product.

1. The character loader resolves Antonia's object, basis, packed morphs, sixteen configured material slots, texture set, underwear assets, author, source URL, concrete CC-BY 3.0 license file, and license hash without PyYAML or another Blender-side dependency.
2. A dedicated Antonia fit contract uses direct named morphs instead of the MakeHuman-style signed controls. The accepted full-bust fit reaches a 0.0072 cm maximum closed-circuit residual, effectively zero bust-separation residual, 0.8390 cm maximum bounded surface correction, 7.2115 cm inframammary relief, and 2.0410 cm left and right root curvature.
3. The exporter produces a 14.3 MB GLB with the 36,030-vertex fitted source body, ten unique body materials after round-trip import, eight embedded images, a generated modesty bandeau, the licensed Antonia panties, and a separately hashed collision OBJ.
4. Vertex-order comparison after decoding Blender's OBJ `(-x, -y, z)` convention measures a maximum body-to-collision difference below 0.000001 m across all 36,030 source vertices.
5. A fresh Blender process imports the GLB, verifies three mesh objects, the material and image counts, and the 167.0 cm height, then renders front, rear, both sides, and both obliques. Those six round-tripped views were reviewed, not merely generated.
6. The first numerically accepted Antonia fit was visually rejected because unconstrained optimization concentrated the bust target into an excessively spherical `Breast big` solution. The production candidate contract now bounds that morph and requires a mixed classic, hang, implant, diameter, and position solution. Numerical acceptance alone remains insufficient.
7. The first GLB round trip was visually rejected because Blender exported height-map nodes ambiguously and the imported body became dark and mottled. The candidate now exports stable base-color PBR materials and records tangent-space normal conversion as an open gate.
8. Antonia's legacy bra cannot be called fitted after body customization. The candidate uses a clearly identified convex-envelope modesty bandeau for display only. It is intentionally not described as a bra, pattern, cloth solve, or fit proof.

Packaged WinUI GLB loading is now proven for the candidate. The application ships the 14.3 MB GLB, a candidate-only manifest, and the exact CC-BY 3.0 license through the AppX recipe. The embedded renderer verifies the geometry and license hashes, rejects unsupported GLB transforms, decodes the known indexed triangle and embedded-image contract, and applies a manifest-bound 180 degree display yaw so the existing semantic cameras remain correct. Isolated run `20260809-041233-0852a5fd` used payload `b3b01e84513736fac6988156b3c93573d3730369a747737a887ea2967cf3ea4e`; 27 functional interactions passed, host input injection and VMConnect use remained false, and all six camera plus both final 2D viewport screenshots were reviewed. The run correctly failed only because no accepted cloth matches the current revision.

The live simulation route now uses the same Antonia character directory and GLB contract as the packaged candidate. Runtime version `2026.08.09-style3d-antonia-v6` binds the Antonia character files, CC-BY 3.0 license, generator, GLB exporter, regional display-to-collider gate, gross-proportion and landmark-symmetry gate, six-view renderer, visual-review recorder, and arm-safe high-bust distribution contract. Pipeline revision 6 rejects an older `mb_female` runtime instead of silently solving against a different body family and gives the anatomy-bearing display manifest a new job identity. Each job writes `display-avatar/avatar.glb`, its local license, and its manifest beside the collision body and fitted-state evidence.

The regional gate no longer requires display and collision meshes to share vertex count, order, or topology. It builds both surfaces in Blender, rejects non-finite input, measures every display vertex against the collision surface and every collision vertex against the display surface, and assigns the comparison to head, torso, arms, and legs through the display material contract. Head and torso require no more than 5 mm maximum and 2.5 mm 95th-percentile separation. Arms and legs require no more than 10 mm maximum and 4 mm 95th-percentile separation. The floor datums must agree within 1 mm. Installed runtime v6 reproduced the exact fitted Antonia control with 36,030 vertices on each surface, a 0.00000082 m worst surface error, a 0.00000033 m floor error, accepted results in all four regions, and no issues. A deliberately different test topology on the same surface passed; a collider shifted by 2 cm failed in the torso region. These geometry gates remain independent of human anatomy and cloth review.

Runtime v6 adds a separate backend-neutral `patterna.avatar-anatomy/1.0` report. It resolves CharMorph's sparse weighted joints on the exact fitted vertices, measures a pose-independent arm-span estimate from the bilateral shoulder-to-elbow-to-wrist-to-fingertip chains plus shoulder-joint breadth, and also measures arm length, upper-arm length, hand length, foot length, shoulder breadth, chin-to-crown height, and functional leg length relative to stature. It reflects every named left landmark across the inferred midline. The limits are deliberately broad rejection envelopes, not a definition of normal bodies. Arm-span and upper-arm limits come from a primary ANSUR II analysis; arm, hand, foot, and bideltoid limits are bounded against NASA RP-1304 applicant tables. Head and functional-leg limits remain explicitly project-owned gross-anatomy guards pending a larger definition-matched population source.

The exact fitted Antonia control fails this gate only because its upper-arm length is 0.153202 times stature against a 0.16 minimum. Its pose-independent skeletal arm-span estimate is 0.949553 times stature and passes; an earlier horizontal fingertip-width metric falsely failed because it measured the asymmetric raised-arm pose instead of anatomy and was removed before commit. Hand, foot, shoulder, head, functional-leg, and full arm-chain checks pass. All 108 left-right landmark pairs pass the 1 mm symmetric-preset limit with a maximum mirror error below 0.00000047 m. This evidence explains part of the uncanny silhouette and keeps Antonia in its intended role as a reproducible rejected control. It does not license quietly stretching the upper arms; the MHR challenger must pass the same report from its own fitted state and then pass six-view review.

The first live-contract six-view render used exact fitted Antonia and the existing production crew-neck OBJ. The numerical registration gate accepted it. Human review rejected it immediately: both breasts and the abdomen protrude through large holes, the rear neckline is open, sleeves appear detached, and the underarm and side surfaces are severely distorted. This is evidence about the existing production garment asset, not a claim that a new Newton result was produced. Product proof now requires an explicit `visual_quality.accepted` decision whose six reviewed hashes match the exact six render hashes. Every rerender resets that decision because Blender output is not assumed byte-deterministic. Numerical registration, collision, strain, or equilibrium evidence cannot promote a visually rejected result.

The packaged review still rejects several production-quality details. Antonia has visible texture-region transitions on the limbs and crown, no hair geometry, a coarse display-only bandeau, and no accepted cloth. The 2D workspace now packs the exact piece extents into deterministic shelves, keeps labels in dedicated headers, exposes pan through the ScrollViewer, and provides visible Zoom out, Zoom in, Fit, Frame selected, calibrated 1:1, and scale-calibration controls. The ordinary percentage remains explicitly a viewport zoom. A user must measure the on-screen 320-DIP ruler before 1:1 becomes available, and the stored calibration warns that monitor, display-scaling, resolution, or remote-display changes require recalibration. Reviewed run `20260809-084558-a10b550b` proved Fit, calibration, 1:1 restoration, physical darts in both construction modes, topology-owned closure-seam changes, and complete test cleanup at 1920 by 1080. The current candidate is therefore accepted as a packaged architecture foundation and rejected as a production baseline.

## Cloth solver architecture

### Why the current metrics were insufficient

Zero intersections, closed seams, finite positions, bounded strain percentiles, static displacement, and deterministic hashes are necessary. They say nothing about whether folds, weight, silhouette, hems, sleeves, bust shaping, and gravity look like fabric.

The present solver adapter also owns custom warm-start, contact, seam, and projection behavior. A clean report from that adapter is partly a report about its own correction logic. Independent comparison is therefore mandatory.

### Solver candidates

| Candidate | Strength | Cost and risk | Role |
| --- | --- | --- | --- |
| Newton `SolverStyle3D` | Already integrated, GPU accelerated, fast, Apache-2.0, current accepted evidence exists | Research-oriented and changing rapidly; current visuals are unconvincing | Control backend |
| ZOZO PPF Contact Solver | Apache-2.0, Windows native executable, Blender 5 add-on, GPU contact and elasticity, penetration-free focus, fitting example, RTX 4090 explicitly recommended | New integration, CUDA 12.8 requirement, potentially minutes per result, Blender add-on requires Blender 5 | First challenger |
| IPC Toolkit and C-IPC | MIT toolkit, strong intersection-free codimensional contact research, thickness and friction formulation | Integration-heavy C++ research stack; unsuitable as the first interactive backend | Offline oracle and difficult-case validator |
| PositionBasedDynamics | MIT, mature XPBD and deformable examples, Windows build path | General library rather than garment product; would recreate much of the missing sewing and material stack | Reference only |
| XRTailor | Apache-2.0, CUDA, Windows, GLTF bodies, self-collision, anisotropic quality mode | Its documented custom-asset path requires Marvelous Designer sewing and draping plus a welded template; it does not replace Patterna's missing assembly solve | Later animation comparator only |
| Blender built-in cloth | Already available and artist-friendly | Past project evidence showed unstable sewing and collision for this garment | Diagnostic comparison only |

### Antonia control result

The exact live 14-piece adaptive shirt and exact fitted Antonia collision body now have a normalized control bundle and four Newton evaluations documented in `docs/cloth-solver-bakeoff.md`. None is accepted.

1. The original 0.25 cm C# arrangement entered Newton despite already failing minimum triangle area and initial strain gates. It finished with 137 body crossings and 1.705 p99.9 strain.
2. A 0.50 cm rigid source placement reduced the material surface from 146,874 to 37,287 vertices and cleared the minimum-area gate.
3. Explicit progressive sewing exposed a semantic adapter defect: legacy logic selected collar joins as shoulders because it did not understand `front_torso` and `back_torso`. The adapter now identifies both real shoulder seams and excludes finishing pieces.
4. The corrected control and a topology-identical dressing-body variant still failed equilibrium, body contact, seam closure, localized strain, and visual sleeve/cuff quality.
5. The common source builder now rejects an unqualified initial arrangement before solver launch. A research-only override is explicit and report-visible.

These results strengthen the case for the PPF challenger, but they do not prove that switching solvers alone will fix the live sleeve-cap or cuff construction contract.

### Common solver contract

Every backend must consume the same normalized bundle:

1. Authored 2D panel curves and stable edge identities.
2. Triangulated material coordinates and rest lengths.
3. Exact seam correspondence and closure constraints.
4. Fitted collision body with region labels.
5. Fabric density, warp, weft, bias, bend, thickness, friction, damping, and gravity in explicit units.
6. Initial placement and optional prior accepted state.

Every backend must emit:

1. Physical surface and welded render surface.
2. Per-vertex material coordinates and panel ownership.
3. Contact, self-contact, seam, strain, energy, and equilibrium evidence.
4. Backend version, source revision, executable hashes, device, settings, timing, and determinism evidence.
5. Six registered packaged-view renders and six canonical Blender renders.

### Bake-off decision rule

Use one unchanged shirt, body, fabric, initial placement, and camera set. A challenger wins only if it:

1. Passes every current numerical gate without post-solve geometry projection that hides contact failures.
2. Produces visibly better folds, sleeve fall, hem behavior, bust shaping, seam behavior, and material weight in a blind multi-view comparison.
3. Completes within a documented local interaction budget on the RTX 4090.
4. Can be installed, updated, and removed by the owned runtime installer.
5. Has a license compatible with redistribution and a personal proprietary project.

## Rendering and packaged asset format

The 130 MB production OBJ is an evidence and UX liability. OBJ has no compact scene hierarchy, skinning, modern PBR material model, binary texture packaging, or efficient indexed delivery.

The target payload is GLB with:

1. Indexed meshes and mesh compression only after cross-machine decoder proof.
2. Normals, tangents, UVs, base color, normal, roughness, and optional subsurface approximation inputs.
3. Separate display body, eyes, hair, underwear, and garment nodes.
4. Optional collision proxy excluded from the visual scene or marked non-renderable.
5. Explicit meters, axis convention, floor datum, revision, and source hashes.
6. A low-detail interactive body and a high-detail canonical render body bound to the same fitted state.

WebView2 may remain because it provides an isolated, easily packaged interactive viewport. If GLB loading and PBR parity cannot meet the packaged screenshot gates, replace only the viewport implementation. Replacing the WinUI workflow shell would add risk without fixing the body or cloth.

## Quality gates that must be added

### Anatomy and avatar

1. Reviewed ratio and landmark ranges.
2. Symmetry and pose checks.
3. Regional display-to-collider registration.
4. Texture and material completeness.
5. Six-view packaged and Blender image review.

### Cloth appearance

1. Silhouette difference against an approved reference envelope.
2. Sleeve fall angle and cuff opening plausibility.
3. Neckline, shoulder, armscye, bust, waist, and hem clearance bands.
4. Fold wavelength and amplitude ranges appropriate to the selected material.
5. No rubber-sheet stretching, contact dents, seam ridges, floating hems, or body clipping.
6. A visual rejection remains a rejection even when all numerical metrics pass.

### Product UI

1. Real packaged AppX launch in the isolated Windows guest.
2. 2D toggles, sliders, editing, Undo and Redo, save and load, and export round trips.
3. 3D orbit, zoom, all fixed views, fit view, stale-state handling, and current-cloth proof.
4. Multi-resolution and text-scaling screenshots.
5. Keyboard navigation, focus order, automation names and IDs, and screen-reader labels.
6. No release declaration while accepted cloth, 2D usability, or packaged multi-view evidence is missing.

## Phased implementation

### Phase 0: restore truthfulness

1. Make the isolated runner exercise all controls even when cloth is stale, then fail the freshness gate explicitly.
2. Correct UI and documentation that still call the current body MPFB when the source path is CharMorph.
3. Record the current avatar asset, character directory, and generated-output license in the runtime manifest and every simulation job. Runtime `2026.08.09-style3d-antonia-v6` now declares `CharMorph Antonia`, `CC-BY 3.0`, the concrete license file, the exact character directory, the regional registration gate, the gross-proportion and landmark-symmetry gate, and the arm-safe high-bust distribution contract. Pipeline revision 6 refuses older or undeclared body families.
4. Do not promote the current AGPL `mb_female` source as the replacement baseline.

### Phase 1: Antonia measurement and display spike

1. Generalize CharMorph input discovery from `config.yaml`. Complete for the locally required scalar and list subset.
2. Fit the six primary measurements plus the upper-body measurements required by the shirt. Primary closed-circuit and bust-landmark fit is complete; the remaining upper-body values still need explicit gates.
3. Export a textured GLB and a watertight collision proxy. Textured GLB, exact full-resolution collision pairing, hash-bound AppX packaging, and the narrow packaged loader are complete; simplification remains open.
4. Add regional registration and six-view anatomy gates. Bidirectional regional surface registration, gross-proportion checks, 108-pair symmetric-landmark evidence, fresh-import six-view review, and packaged semantic-camera review are implemented. Antonia fails the new ratio gate. Replacing the broad project-owned head and functional-leg guards with a larger definition-matched population source remains open.

### Phase 2: cloth bake-off

1. Keep Newton as the control. The first exact Antonia/current-shirt control series is complete and rejected.
2. Install the PPF native Windows solver in a separate versioned runtime only after dependency approval.
3. Maintain the normalized common bundle and input gate documented in `docs/cloth-solver-bakeoff.md`.
4. Compare numerical evidence, visual evidence, runtime, and integration complexity.
5. Use IPC Toolkit only for cases where both interactive solvers disagree or fail contact.

### Phase 3: packaged viewer and baseline

1. Keep the display avatar on the verified GLB path and replace raw cloth OBJ delivery only after the accepted cloth backend emits an equivalent compact, inspectable payload.
2. Load the winning Antonia body and winning cloth result.
3. Correct the 2D layout and responsive behavior.
4. Rerun the complete isolated UI suite at every required viewport and text scale.
5. Promote a baseline only when the current source revision and bundled evidence hashes agree.

## Dependency approval boundary

This reassessment does not install or upgrade a dependency. The first requested dependency change should be a separate versioned PPF evaluation runtime. The current host has an RTX 4090, which the official project names as an ideal GPU, but driver, CUDA, executable provenance, and Blender 5 compatibility must be verified before installation.

The concrete PPF request is now bounded to native tag `2026-08-08-03-55`, archive size 447,925,491 bytes, and GitHub-published SHA-256 `50d84ce0c9bc57d6d72564efa21b66c19c4e5e7e9eddd528c4d9fa050f5cafec`. The separately tagged Blender add-on is optional and must not be mistaken for the native engine through GitHub's generic latest-release endpoint. The host currently reports NVIDIA driver 610.88 and CUDA user-mode driver 13.3, which exceeds the documented CUDA 12.8 support requirement. Compatibility remains unproved until the pinned native executable runs.

The concrete MHR request is bounded to v1.0.1 `assets.zip`, size 198,943,157 bytes, and GitHub-published SHA-256 `e4f4f205cd87c0fa106577ba1de4fc763e4eb197c924461d2ef7e6944e9d6b94`, plus a separate Python 3.11 or 3.12 CPU PyTorch environment. The current Patterna simulation runtime is already Python 3.12.10 but contains no PyTorch; it must not be mutated in place. MHR's LOD1 TorchScript route remains the smallest honest challenger because it avoids PyMomentum and preserves a narrow runtime boundary.

The old GarmentCode Warp environment should be removed only after proving that the product-critical mesh export can run without its customized collision and simulation modules. Updating it in place would be the traditional dependency-upgrade method of discovering that archaeology is also a branch of applied explosives.

## Primary references

1. CharMorph licensing and character matrix: <https://blendercharacterproject.org/docs/html/Introduction.html>
2. CharMorph source and feature inventory: <https://github.com/Upliner/CharMorph>
3. ZOZO PPF Contact Solver: <https://github.com/st-tech/ppf-contact-solver>
4. Newton physics engine: <https://github.com/newton-physics/newton>
5. NVIDIA Warp license history: <https://github.com/NVIDIA/warp/blob/main/CHANGELOG.md>
6. IPC Toolkit license and project: <https://ipctk.xyz/v1.4.0/about/license.html>
7. C-IPC project: <https://ipc-sim.github.io/C-IPC/>
8. PositionBasedDynamics: <https://github.com/InteractiveComputerGraphics/PositionBasedDynamics>
9. MakeHuman CC0 assets: <https://github.com/makehumancommunity/makehuman-assets>
10. XRTailor: <https://github.com/openxrlab/xrtailor>
11. Momentum Human Rig: <https://github.com/facebookresearch/MHR>
12. MHR asset license resolution: <https://github.com/facebookresearch/MHR/issues/62>
13. Anny: <https://github.com/naver/anny>
14. SOMA-X: <https://github.com/NVlabs/SOMA-X>
15. Blender Human Base Meshes: <https://www.blender.org/download/demo-files/#assets>
