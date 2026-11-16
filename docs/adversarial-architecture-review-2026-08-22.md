# Adversarial architecture review

Date: 2026-08-22

Review base: `ae6006d`, including the complete paused working-tree diff

Scope: architecture and evidence only; no product code, assets, dependency installations, application launches, virtual-machine launches, or simulations were performed

## Decision

Patternal should not promote the current MHR morph preview, Newton Style3D route, PPF route, custom WebGL renderer, MetaHuman history, or any installed challenger as its product foundation.

The best architecture under the actual constraints is a bounded native application with versioned external workers. Keep WinUI and the 2D document authoritative. Narrow 3D support to declared garment archetypes and validated body ranges. Generate the fitted display body, fitted collision body, arranged garment, solved cloth, and rendered GLB from one immutable revision bundle. Select the avatar and cloth implementations only after they pass that contract. Use a maintained renderer in the packaged viewer and Blender as a deterministic authoring and review worker, not as the garment engine.

This recommendation is deliberately conditional. There is no open-source garment solver in the inspected evidence that can already be called a proven Patternal engine. XRTailor is the most relevant new challenger because it claims automatic dressing, anisotropic mechanics, collision, Windows support, and GLTF mannequins, but its documented custom-asset workflow begins with a garment already dressed in Marvelous Designer. C-IPC supplies unusually strong contact behavior, but integrating sewing, calibrated textiles, grading, and product controls would amount to building a garment engine. The current Newton and PPF results are rejected. The proof plan below decides whether the bounded worker architecture is viable before another long implementation begins.

If the product contract must instead mean arbitrary patterns, arbitrary anatomy, immediate high-quality drape, and CLO-class output on ordinary Windows hardware, the current one-person, no-revenue, low-cost constraints are incompatible with it. The credible alternatives are a negotiated commercial garment-engine license or a much larger engineering effort. A renderer migration cannot repeal that arithmetic. Physics remains stubbornly immune to enthusiasm.

## Evidence labels and method

This report uses three labels:

1. **Verified repository fact** means the claim is observable in the reviewed documents, current source, acceptance scripts, manifests, generated evidence, or the complete diff from `ae6006d`.
2. **Verified primary-source fact** means the claim comes from an official repository, official documentation, a project license, a first-party API, or the cited technical paper.
3. **Inference** means the conclusion follows from those facts but has not itself been demonstrated in a fresh packaged run.

The repository evidence reviewed includes `docs/architecture-v3-reassessment.md`, `docs/open-source-foundation-decision.md`, `docs/cloth-solver-bakeoff.md`, `docs/challenger-runtime-installation.md`, `docs/isolated-windows-ui-testing.md`, all relevant sections of `docs/lessons-learned.md`, `TODO.md`, the current worktree and diff, renderer and asset manifests, solver adapters, revision checks, proof-recording scripts, and isolated UI acceptance scripts.

One naming trap matters. The repository's Newton Style3D path is the open [Newton physics project's Style3D solver](https://github.com/newton-physics/newton/blob/main/docs/solvers/index.rst). It is distinct from the proprietary Style3D Simulator Unreal plugin discussed later. Similar names do not create shared licensing, maturity, or acceptance evidence.

## Current state, without optimistic translation

### What is already valuable

1. **Verified repository fact:** the native WinUI 2D editor, document model, persistence, Undo and Redo, SVG export, keyboard interaction, automation names, layout range, six camera controls, theme coverage, and isolated packaged-UI harness are the strongest part of the product. The recorded full harness ran 47 actions and passed 46. Its one functional failure was the intentionally open current-cloth freshness gate.
2. **Verified repository fact:** accepted cloth is revision-bound in `SimulationPipeline.cs`; stale cloth is hidden when body or pattern identity changes. This is the right behavior.
3. **Verified repository fact:** product visual review is not a vague checkbox. `tools/record_product_visual_review.py` binds a human decision to hashes for front, front-oblique, left, back, back-oblique, and right renders.
4. **Verified repository fact:** solver reports already require explicit seam identity, material-space strain coverage, static equilibrium, collision gates, topology identity, and hash continuity. Those contracts are reusable even if every solver implementation changes.
5. **Verified repository fact:** Narrator acceptance and a physical-GPU packaged run remain open. A virtual machine and source-level tests do not close either gate.
6. **Verified repository fact:** avatar and cloth ownership is currently split across incompatible paths. The production `SimulationPipeline` hard-requires CharMorph Antonia, Legacy Warp uses MPFB, the paused packaged fallback now uses MHR, and `avatar3d.html` retains MakeHuman and procedural fallbacks. Cloth likewise has production Newton Style3D, Legacy Warp, PPF challenger, and Unreal Chaos diagnostic paths.
7. **Verified repository fact:** the current `Patternal.TopologyTests` executable fails its candidate contract at the assertion mapped to `Program.cs:1090`. The checked-in source at that location now expects MHR, while later test fixtures still set `avatarBackend = "CharMorph Antonia"`; the built executable and source contract are not a clean current pair. The Unreal compiler regression passes. This is direct evidence of competing owners and stale build or acceptance contracts, not evidence that Antonia or Unreal should win.

### What the paused MHR work actually proves

1. **Verified repository fact:** MHR's root manifest remains `accepted: false` and `candidateOnly: true`. The display candidate was rejected for visible scalp through the hair, weak hands, jagged display-only modesty shells, insufficient editable anatomy, and no accepted cloth.
2. **Verified repository fact:** the paused diff adds a 5,136,120-byte same-topology additive preview basis for 11 represented values: chest circumference and depth, underbust circumference and depth, waist circumference and depth, abdomen circumference and depth, hip circumference and depth, and mean upper-arm circumference. Height is a global scale.
3. **Verified repository fact:** the product exposes 151 numeric avatar values. `applyMhrMorphPreview()` counts changes only among the 11 basis parameters. The diff removed the old editable-default guard and preserves MHR for every feminine profile. Therefore an edit to any of the other 140 exposed values can leave the mesh unchanged and can leave `changedValues` at zero.
4. **Verified repository fact:** when `changedValues` is zero and height is unchanged, the viewer labels the state as the exact MHR candidate with accepted measurement, rig, anatomy, and pose gates. That label can now be shown after an unmapped body edit. This is a truthfulness defect, not a cosmetic limitation.
5. **Verified repository fact:** `morphBasis.accepted` records baseline and independent minimum or maximum endpoint fits. It records no midpoint holdout, compound-slider holdout, pairwise interaction test, mesh inversion test over combinations, or revised rig and collision proof.
6. **Verified repository fact:** the runtime preview changes body positions and recomputes normals. It does not produce a matching rig, a revision-specific collision surface, locally fitted hair or modesty geometry, or matching cloth. Accessories receive only global height scaling.
7. **Inference:** this basis is useful as a disposable interaction prototype. It cannot be the product's avatar truth because its acceptance surface is smaller than the UI's declared edit surface, and because additive endpoint interpolation is not evidence of anatomically valid compound deformation.

### What the cloth work actually proves

1. **Verified repository fact:** the Newton Style3D control failed on the current exact 14-panel shirt. Recorded outcomes include roughly 134 to 147 body crossings, maximum seam separation around 0.518 to 0.545 cm, no accepted equilibrium, and malformed sleeves and underarms.
2. **Verified repository fact:** the direct PPF route began with seam endpoints as much as 55.519 cm apart. A roughly 10,000-vertex proxy took about 19.5 seconds per frame and plateaued with seams around 9.062 cm apart.
3. **Verified repository fact:** phased PPF closed many numerical seam gaps, but the six-view render showed a catastrophic crumpled mass with spread sleeves and no credible garment silhouette. It was correctly rejected.
4. **Verified repository fact:** stronger sewing constraints did not repair the garment. Earlier Blender and spring routes produced shredded topology, holes, penetration, wrong seams, implausible silhouettes, or invalid warm starts.
5. **Verified repository fact:** the current final Style3D acceptance limits include maximum seam separation of 0.25 cm, maximum edge strain of 0.40, p95 strain of 0.15, p99.9 strain of 0.29, p99.99 strain of 0.55, high-strain edge fraction of 0.0005, zero intersections, and static equilibrium. Initial-drape thresholds are looser by design.
6. **Inference:** the dominant failure is not a missing stiffness value. Solvers are repeatedly being asked to discover garment assembly from semantically weak, widely separated, source-mismatched, or already damaged inputs. A contact solver is not a sewing-pattern interpreter.

## Failure taxonomy

| Failure class | Verified evidence | Invariant across attempts | Architectural consequence |
|---|---|---|---|
| Product truth differs from displayed truth | 151 editable numeric values feed an 11-value morph basis; unmapped changes can still produce the exact-candidate label | Status is inferred from partial state rather than proven from the complete current revision | Every displayed claim must be generated from a complete revision manifest, never from a local change counter |
| Display body differs from fit body | MHR appearance was rejected after numerical fit gates passed; accessories do not follow local preview deformation | Numerical measurement fit does not imply acceptable anatomy, skin, hands, hair, pose, modesty, or silhouette | Separate fit, collision, rig, and display responsibilities, then bind all outputs to one fitted state |
| Collider differs from edited body | Paused MHR preview has no revision-specific collider; prior lessons record registration and pose mismatches | Cloth can pass against a body the user is not seeing | Solver input must hash the exact posed collider derived from the same body revision shown in the UI |
| 2D semantics are lost during 3D handoff | Darts, seams, material coordinates, side identity, and panel correspondence failed in several routes | Geometry survives while drafting meaning does not | The handoff needs stable panel, edge, seam, grain, side, and material-coordinate identities |
| Assembly is delegated to dynamics | PPF started with seams up to 55.519 cm apart; stronger stitches worsened results | A solver cannot reliably invent a dressing sequence from a spread 2D layout | Supported garments require an authored, collision-free 3D arrangement contract before dynamics |
| Aggregate metrics mask local destruction | Some seam statistics improved while the product became a crumpled mass | A mean or percentile can hide one exploding sleeve or inverted region | Numerical gates must include regional maxima and must always be followed by fixed multi-angle visual review |
| Source identity is lost between stages | Repeated source-mismatched projections, warm starts, topology changes, and accepted-artifact confusion appear in lessons learned | Later stages can validate a different mesh than the requested revision | Each stage must verify the exact hashes of every input and preserve material-space correspondence |
| Rendering hides or invents quality | Shader holes, wrong-side surfaces, coarse shells, a 130 MB OBJ, and camera mistakes all produced misleading outcomes | Renderer behavior can disguise both valid and invalid simulation | Canonical DCC renders and packaged renders need separate acceptance against the same GLB hash |
| Installed dependency becomes presumed architecture | PPF, Newton, Blender, MHR, MetaHuman, and Style3D have each been treated as the next likely foundation | Installation effort creates sunk-cost bias without closing product gates | Challengers remain replaceable workers until the unchanged acceptance suite passes |
| Competing owners encode different product truths | Production requires Antonia, Legacy Warp uses MPFB, packaged fallback uses MHR, HTML retains MakeHuman and procedural fallbacks, and tests still assert the old Antonia label | No single layer owns the current avatar, collider, solver, or acceptance identity | One revision manifest must name one implementation per role; all other paths are explicit challengers or removed |
| Packaging evidence is mistaken for product evidence | Static tests and isolated UI automation passed while the avatar and cloth remained visually rejected | A package can launch perfectly and still show the wrong product | Build, package, UI, GPU, physical, visual, and legal acceptance remain separate gates |

The common invariant is a broken proof chain:

`2D document revision -> fitted body state -> display body + rig + collider -> 3D panel arrangement -> solver input -> equilibrium -> render asset -> packaged display`

Every arrow needs exact identity, semantic preservation, and independent acceptance. Patternal currently has good checks around several individual boxes. The failures recur at the arrows.

## Hidden and false assumptions

1. **False assumption: a general human model is a garment-fit model.** [MHR exposes 45 identity parameters, 204 pose parameters, 72 facial controls, and seven levels of detail](https://github.com/facebookresearch/MHR/blob/main/README.md), but latent identity controls are not tape-measurement controls. [Anny](https://github.com/naver/anny/blob/main/README.md), [MPFB](https://github.com/makehumancommunity/mpfb2), and [SOMA-X](https://github.com/NVlabs/SOMA-X/blob/main/README.md) provide other body or topology foundations, but none supplies Patternal's complete measurement semantics, finished appearance, registered collider, and garment validation as one product.
2. **False assumption: all 151 values must deform a photoreal avatar in version one.** The drafting model may legitimately need measurements that are not visually distinguishable on a neutral standing body. Pretending otherwise creates dishonest sliders. The 3D avatar contract should expose only controls with validated geometric meaning; the 2D document may retain the broader set.
3. **False assumption: one surface should be display mesh, collision mesh, fitting target, modesty layer, and rig source.** Those roles have conflicting topology, detail, performance, and legal needs. They can be separate artifacts, but only if registration and revision identity are proven.
4. **False assumption: sewing constraints can replace garment arrangement.** The local PPF evidence refutes this directly. Even [XRTailor, which advertises automatic dressing](https://github.com/openxrlab/xrtailor), documents a custom-asset workflow that starts by building and dressing the garment in Marvelous Designer, then adding simulator-specific annotations in its [own asset-preparation guide](https://xrtailor.readthedocs.io/en/latest/common/preparing_your_own_asset.html). Automatic dressing is a challenger claim, not permission to skip input design.
5. **False assumption: reliable contact is a garment engine.** [C-IPC demonstrates intersection-free codimensional contact, friction, thickness, strain limiting, and detailed garment drapes](https://ipc-sim.github.io/C-IPC/), while [IPC Toolkit explicitly provides collision and barrier components](https://github.com/ipc-sim/ipc-toolkit). [PositionBasedDynamics](https://github.com/InteractiveComputerGraphics/PositionBasedDynamics) supplies MIT-licensed PBD and XPBD constraints, but no pattern-authoring or garment-fit workflow. [Warp](https://github.com/NVIDIA/warp) supplies Apache-2.0 Windows CPU and NVIDIA CUDA compute, not a garment product. [Newton](https://github.com/newton-physics/newton) describes itself as an alpha physics engine, and [PPF](https://github.com/st-tech/ppf-contact-solver) is an Apache-2.0 offline contact solver. Patternal would still own sewing, material calibration, arrangement, grading, body adaptation, convergence policy, Windows packaging, and product evidence for any of them.
6. **False assumption: a real-time engine solves authoring.** [Chaos Panel Cloth](https://dev.epicgames.com/documentation/en-us/unreal-engine/panel-cloth-editor-overview) supports runtime cloth assets, XPBD constraints, separate simulation and render meshes, and Dataflow authoring, but the official workflow builds those assets in Unreal Editor from DCC inputs. It is not an official runtime API for turning arbitrary edited Patternal panels into finished garments.
7. **False assumption: MetaHuman solves clothing anatomy.** [MetaHuman Creator is integrated into Unreal Editor](https://dev.epicgames.com/documentation/en-us/metahuman/metahuman-creator-in-unreal-engine), and its visual quality is attractive. It is not documented as a 151-measurement garment-fit body generator. Runtime MetaHuman Collections and Instances are marked Experimental in Epic's [asset overview](https://dev.epicgames.com/documentation/en-us/metahuman/assets-overview) and [collections documentation](https://dev.epicgames.com/documentation/en-us/metahuman/metahuman-collections-in-unreal-engine).
8. **False assumption: a commercial solver can quietly ship because the project makes no money.** The [Style3D Simulator terms, clause 5.2.2.3](https://simulator.style3d.com/docs/en/terms_of_service.pdf), prohibit using the plugin to create software with apparel-modeling features similar to or competitive with Style3D products. Patternal is plainly such software. The route is unavailable without explicit written contractual permission, regardless of revenue.
9. **False assumption: marketplace avatar assets solve the display problem.** Human Generator's [asset license](https://help.humgen3d.com/FAQ/Human%2BGenerator%2BAsset%2BLicense) separates add-on code from assets and restricts software use and extractability by license tier. Reallusion's [content policy](https://www.reallusion.com/license/content.html) directs character-creator products to enterprise licensing. A packaged raw GLB is not meaningfully protected from extraction. A commissioned asset with explicit redistribution, derivative, source-control, and package-extraction rights is safer than a pile of incompatible store receipts.
10. **False assumption: the current custom WebGL viewer is harmless because it already works.** It owns loading, camera, shading, morphing, status, geometry fallbacks, and product truth in one HTML file. That is too much policy in a renderer. [Babylon.js is Apache-2.0 and maintains WebGL, WebGL2, WebGPU, and glTF support](https://github.com/BabylonJS/Babylon.js); using a maintained renderer would reduce bespoke graphics code, but it would not repair invalid assets.
11. **False assumption: packaging a fixed WebView runtime is free.** Microsoft's [WebView2 distribution guide](https://learn.microsoft.com/en-us/microsoft-edge/webview2/concepts/distribution) says the Fixed Version package adds more than 250 MB. Microsoft's [Evergreen comparison](https://learn.microsoft.com/en-us/microsoft-edge/webview2/concepts/evergreen-vs-fixed-version) recommends Evergreen and explains its automatic updates. Patternal must choose between package mass and runtime drift, then test the chosen policy offline.
12. **False assumption: broad scope now is faster than a narrow honest contract.** Every rejected route expanded the stack before one garment on one fitted body passed the complete visual gate. Narrowing the first supported envelope is not surrender. It is the only way to produce evidence rather than archaeology.

## Kill, retain, and isolate

### Kill as promotion paths

1. Kill the paused additive MHR preview as a candidate product body, collider, or acceptance authority. It may remain a disposable interaction experiment only if the UI labels every mapped and unmapped value honestly.
2. Kill further parameter tuning of the current Newton and PPF setups. Preserve them as frozen controls. A new run is justified only by a materially different, gate-passing arrangement or input contract.
3. Kill the current exact 14-panel shirt's spread-panel warm start as a universal assembly method.
4. Kill MakeHuman, Antonia, and the current MHR package as accepted hero display avatars. Their rejected evidence remains useful.
5. Kill the idea that MetaHuman or Unreal is the default merely because previous assets exist. It gets one bounded challenger spike only if the recommended architecture fails its proof.
6. Kill Style3D Simulator from the shortlist unless Style3D supplies written permission for this competing apparel application and explicit offline redistribution terms.
7. Kill CLO or Marvelous Designer as an embedded low-cost engine assumption. They can be developer-side oracles, not silent redistributable dependencies.
8. Kill the custom HTML renderer as the long-term owner of morph semantics, acceptance labels, and asset fallback decisions.

### Retain

1. Retain the native WinUI 2D editor, document schema, accessibility work, persistence, Undo and Redo, SVG export, keyboard behavior, and responsive shell.
2. Retain strict current-revision invalidation. Stale cloth should remain hidden, not politely displayed with a warning.
3. Retain the immutable seam graph, material-space strain reference, units, topology hashes, solver version, parameter manifest, and source provenance.
4. Retain the isolated packaged-UI harness, but keep Narrator and physical-GPU acceptance explicit.
5. Retain the six-view hash-bound human review and add regional detail crops where the six views cannot show seam and penetration defects.
6. Retain Blender LTS for deterministic authoring, GLB assembly, material baking, and canonical renders. Blender's [license leaves artwork output with the user](https://www.blender.org/about/license/), its [glTF exporter supports PBR, skinning, animation, and shape keys](https://docs.blender.org/manual/en/latest/addons/scene_gltf2.html), and [Blender 4.5 LTS is supported through July 2027](https://www.blender.org/download/lts/). Do not call Blender's spring cloth a production garment engine; its own [cloth documentation](https://docs.blender.org/manual/en/dev/physics/cloth/introduction.html) warns that initial penetration and abrupt motion can break the solve.

### Isolate behind contracts

1. Isolate avatar fitting, collider generation, cloth arrangement, simulation, GLB assembly, and canonical rendering in versioned external workers. The MSIX application should communicate through an immutable directory bundle or narrowly scoped local process protocol, never import Python, CUDA, Blender, or engine internals into UI state.
2. Isolate each worker in a versioned directory with a complete license inventory, exact executable hashes, bounded cache, explicit cleanup, and no writes outside declared application data. No mutable machine-wide runtime is an acceptable hidden dependency.
3. Isolate the viewer to rendering one validated glTF or GLB asset plus camera and selection input. It must not decide whether an avatar or cloth revision is accepted.
4. Isolate solver adapters behind one normalized bundle. The adapter may translate formats; it may not silently recompute patterns, replace the body, weld seams, change material coordinates, or substitute a warm start.
5. Isolate display assets from solver assets while binding both to the same fitted-state hash. A beautiful shell and a low-resolution collider are allowed; an unregistered pair is not.

## Candidate 1: bounded native product with external workers

**Status:** recommended, subject to the 1 to 2 day proof.

### End-to-end shape

1. WinUI remains the product shell and the 2D document remains authoritative.
2. The document creates an immutable `RevisionBundle` containing the complete body profile, declared supported 3D controls, 2D panels and curves, panel-side identity, seam pairs, notches, grain, material coordinates, fabric calibration, pose, garment archetype, revision hash, and deterministic seed.
3. An avatar worker produces one fitted state with a display body, rig, collision body, landmarks, and registration report. MHR, Anny, MPFB, or another legally clean model may implement this role; none is privileged before the bakeoff. [MHR is Apache-2.0](https://github.com/facebookresearch/MHR), [Anny's core is Apache-2.0 and can use CC0 MPFB data](https://github.com/naver/anny), and [MPFB is GPLv3 with separately documented generated-character licensing](https://github.com/makehumancommunity/mpfb2/blob/master/LICENSE.md). Optional SMPL-family assets must be excluded unless their separate license is compatible with redistribution.
4. A licensed or commissioned display package supplies skin, eyes, hair, hands, and modesty geometry. The agreement must explicitly allow derivative fitting, redistribution in an extractable Windows package, source control, backups, and perpetual personal use. It must not be a generic marketplace license interpreted hopefully at 2 a.m.
5. Each supported garment archetype owns a 3D arrangement template tied to stable 2D panel and seam semantics. The template adapts within a validated body and pattern envelope before simulation. Arbitrary 2D patterns remain editable, but the 3D pane must say `3D drape unsupported for this revision` until an arrangement contract exists.
6. A solver worker consumes only the accepted arrangement and exact collider. XRTailor, a C-IPC-based offline worker, and the frozen Newton control compete on the same bundle. [XRTailor is Apache-2.0, supports Windows and Linux with CUDA, exposes anisotropic mechanics, collision and self-collision, quality and swift modes, and GLTF mannequins](https://github.com/openxrlab/xrtailor). Its [Windows build documentation](https://xrtailor.readthedocs.io/en/latest/getting_started/build_from_source.html) records a CUDA and Visual Studio toolchain, so it is NVIDIA-specific and operationally heavy. Its Marvelous Designer-based asset-preparation requirement must be replaced or proven compatible with native Patternal panels before adoption.
7. A Blender worker assembles the accepted display body and cloth into a compact indexed GLB and renders the canonical review set. Blender is an authoring and proof boundary, not the owner of document truth.
8. The packaged viewer loads that GLB. A maintained Babylon.js viewer is preferable to the current custom loader if a focused replacement proof preserves all cameras, accessibility behaviors, offline use, GPU fallback, and exact asset identity.

### Product contract

1. Version one supports one fitted-body family, one neutral pose, and one garment archetype over a declared measurement and edit envelope.
2. The 151-value 2D profile may remain. Only controls with compound-validation evidence are advertised as 3D body controls.
3. Drape is asynchronous and revision-specific. Immediate slider feedback may use an explicitly labeled preview, but it cannot inherit accepted-body or accepted-cloth wording.
4. Every unsupported revision fails closed and preserves 2D authoring. It never reuses a nearby accepted asset while implying a match.

### Tradeoffs

| Concern | Assessment |
|---|---|
| Licensing | Best available route if every code, model, texture, hair, and transitive dependency is inventoried. Blender-linked distributed scripts must be GPL-compatible under Blender's [license guidance](https://www.blender.org/about/license/); generated GLB output remains the user's. |
| Package size | WinUI can remain lean, but a fixed WebView2 runtime alone adds more than 250 MB. Blender's current 4.5 LTS downloads are hundreds of megabytes. Keep heavy workers optional and versioned; measure the actual installed footprint rather than estimating it. |
| GPU | XRTailor requires CUDA-capable Windows or Linux hardware. A C-IPC or CPU path may broaden hardware coverage but is expected to be slower. The product must declare supported GPUs and fail clearly on unsupported hardware. |
| Offline | Achievable if all model data, worker binaries, licenses, and WebView policy are packaged locally. Any auto-download or cloud fitting is disqualifying. |
| Maintenance | Moderate for the shell and contracts; high for the chosen worker. The replaceable boundary prevents a solver upgrade from rewriting the UI and document model. |
| One-person fit | Plausible only with the narrow garment and body envelope. Universal garment assembly or a home-grown full simulator is not plausible. |

### Principal risks

1. XRTailor may not accept Patternal's exact panel and seam representation without reproducing a Marvelous Designer authoring step.
2. No investigated open solver has yet passed the exact current garment, collider, revision, and visual gates.
3. Commissioning or licensing a display package may cost more than expected or fail the extractable-package rights test.
4. Separate display and collision surfaces can drift unless registration is a hard gate on every revision.

## Candidate 2: Unreal sidecar with MetaHuman and Chaos

**Status:** strongest visual reboot; not recommended unless Candidate 1 fails quickly.

### End-to-end shape

1. Keep the WinUI 2D editor and accessibility surface. Launch a separately packaged Unreal process for 3D rather than embedding Unreal internals into the WinUI application.
2. Pass the immutable revision bundle across a file or local-process boundary. Unreal owns 3D display, interaction, Chaos simulation, material rendering, and capture. WinUI remains the only document authority.
3. Use MetaHuman only as the display candidate. Build or import a separately fitted collision body and prove registration. Do not translate MetaHuman sliders into Patternal measurements by assertion.
4. Build Chaos Panel Cloth assets through Dataflow for supported garment templates. Epic's [parametric clothing workflow](https://dev.epicgames.com/documentation/en-us/unreal-engine/getting-started-with-parametric-clothing) warps source clothing to a target body, warns that large source-to-target differences can cause artifacts, encourages multiple source bodies, and does not automatically create a simulation mesh unless one is imported or created. That still implies bounded source garments, not arbitrary runtime drafting.
5. Package a standalone Windows sidecar using Epic's [packaging workflow](https://dev.epicgames.com/documentation/en-us/unreal-engine/packaging-your-project).

### Tradeoffs

| Concern | Assessment |
|---|---|
| Licensing | Unreal is free for this no-revenue project under Epic's current [license terms](https://www.unrealengine.com/license), with royalties applying to qualifying revenue above the stated threshold. MetaHuman content requires exact version and content-license review under Epic's [MetaHuman licensing terms](https://www.unrealengine.com/eula/mhc). |
| Package size | Expected to be much larger than the current viewer because it ships an engine runtime and cooked content. This is an inference; the spike must record exact package and installed sizes. |
| GPU | Epic's [recommended development hardware](https://dev.epicgames.com/documentation/en-us/unreal-engine/hardware-and-software-specifications-for-unreal-engine) includes 32 GB RAM and 8 GB graphics memory. End-user requirements must be measured on the actual packaged scene. |
| Offline | Packaged viewing and simulation can be offline. MetaHuman authoring is not a safe offline assumption; Epic's [getting-started documentation](https://dev.epicgames.com/documentation/en-us/metahuman/getting-started-with-metahuman-creator) describes additional Core Data and online services for parts of creation. Runtime Collections remain experimental. |
| Maintenance | High. Patternal would own two packaged applications, an interprocess protocol, Unreal upgrades, cooked assets, MetaHuman changes, Chaos and Dataflow changes, and duplicate UI-state diagnostics. |
| One-person fit | Poor unless garment scope is narrowed almost as much as Candidate 1. The migration buys visual quality and engine tooling, not a general measurement or sewing engine. |

### Principal risks

1. Official workflows do not demonstrate arbitrary Patternal panel edits becoming runtime Chaos assets in a packaged application.
2. MetaHuman still does not supply the measurement-driven collision contract.
3. Experimental runtime MetaHuman APIs are an unacceptable production foundation until Epic marks them stable and a packaged proof survives a version update.
4. A second UI process can regress focus, keyboard, screen-reader, resize, persistence, and startup behavior already proven in WinUI.

## Candidate 3: licensed garment engine or companion

**Status:** technically credible for garment quality; incompatible with present cost, offline, packaging, and legal constraints unless the owner changes them.

### End-to-end shape

1. Keep WinUI for 2D and document state.
2. Translate the immutable revision bundle into the vendor's exact pattern, seam, avatar, and fabric model.
3. Run CLO as a user-installed companion or a separately negotiated engine, or use Style3D through an explicit bespoke agreement.
4. Import a vendor-produced mesh bearing the original revision identity, then render it in Patternal.

### Verified commercial boundaries

1. CLO's [developer API](https://developer.clo3d.com/) exposes pattern, simulation, rendering, import, and export functions through plugins loaded inside CLO. The public API is an extension surface for an installed CLO application, not evidence of a redistributable simulator library.
2. CLO's official [license information](https://support.clo3d.com/hc/en-us/articles/115012951968-What-kind-of-licenses-do-you-offer) includes individual and business products, and its support material says launch-time [license confirmation requires internet access](https://support.clo3d.com/hc/en-us/community/posts/900002342806-How-to-do-online-offline-authentication). A CLO companion therefore is neither self-contained nor safely offline under the present contract.
3. Style3D Simulator is an Unreal plugin with high-quality real-time cloth claims and packaged-app support on its [official product page](https://simulator.style3d.com/en/home). The same page directs offline and floating-license questions to Style3D. More importantly, clause 5.2.2.3 of its [terms](https://simulator.style3d.com/docs/en/terms_of_service.pdf) forbids using it to create competing apparel-modeling software.

### Tradeoffs

| Concern | Assessment |
|---|---|
| Licensing | Requires a written agreement covering this exact product, redistribution, user machines, offline use, updates, and output ownership. Public terms do not provide that for a self-contained Patternal engine. |
| Package size | CLO companion mode requires a separate full application. A vendor SDK size is unknown until the vendor supplies a redistributable package. |
| GPU | Vendor-specific. CLO's [performance guidance](https://support.clo3d.com/hc/en-us/articles/23390057463577-How-to-Speed-Up-CLO) says GPU simulation is Windows-only on NVIDIA hardware and trades particle distance and accuracy against speed. |
| Offline | Not proven. CLO checks licensing at launch; Style3D's public materials direct offline licensing to sales. |
| Maintenance | Low physics maintenance, high vendor and integration dependency. Version pinning may conflict with subscription updates and user-installed copies. |
| One-person fit | Excellent as a developer-side reference oracle. Poor as the packaged foundation without money and negotiated support. |

### Principal risks

1. The contract may forbid the product outright, as Style3D's public terms currently do.
2. The user may need to buy, install, authenticate, and update another application.
3. Vendor file conversion may silently lose Patternal's drafting semantics or revision identity.
4. A vendor screenshot is not evidence that the packaged Patternal revision matches the 2D document.

## Comparative decision matrix

Scores run from 1, poor, to 5, strong. They are architectural judgments, not measured benchmark results.

| Criterion | Candidate 1: bounded workers | Candidate 2: Unreal sidecar | Candidate 3: licensed engine |
|---|---:|---:|---:|
| Legal fit under current constraints | 4 | 3 | 1 |
| Offline potential | 5 | 3 | 1 |
| Low recurring cost | 4 | 4 | 1 |
| Visual ceiling | 4 | 5 | 5 |
| Cloth quality today | 2 | 3 | 5 |
| Exact Patternal 2D integration | 4 | 2 | 2 |
| GPU breadth | 2 to 4, solver-dependent | 2 | 2 |
| Packaging simplicity | 3 | 1 | 1 |
| Maintenance for one person | 3 with narrow scope | 1 | 2 |
| Replaceability | 5 | 2 | 1 |
| Current evidence strength | 2 | 1 | 3 as an external oracle only |

Candidate 1 wins because it preserves the already-proven product surface and localizes the uncertain work. It does not win because its solver is solved. It wins because it makes that uncertainty testable and replaceable.

## Recommendation

1. Adopt Candidate 1 as the target architecture only if the proof below passes.
2. Change the product contract before writing more code: 2D authoring may remain broad, but 3D drape is supported only for named garment archetypes, named poses, and validated measurement and edit envelopes.
3. Freeze the paused MHR preview and all current cloth tuning. Do not merge or package either as progress toward acceptance.
4. Run a clean avatar shootout behind the narrow contract. Compare current MHR with one materially different open body source such as Anny or MPFB. Judge measurement residuals, compound controls, topology, registration, hands, hair, modesty, pose, and packaged appearance. Do not score parameter count.
5. Pursue a commissioned or explicitly licensed display package if no open body meets the visual gate. Keep the fitted collision body open and replaceable.
6. Give XRTailor one input-compatibility spike because it attacks the recurring assembly problem more directly than PPF or Newton. Do not install it without the owner's dependency approval. Reject it immediately if current native panels cannot enter without a CLO or Marvelous Designer round trip or if its transitive licenses are incompatible.
7. Keep C-IPC as the offline quality reference for contact, not a presumed product engine. Adopt it only if a bounded garment worker can be built without silently expanding into a general simulator project.
8. Use CLO on the developer machine as a visual and fabric oracle if a legitimate personal license is available. Do not make CLO a user dependency.
9. Replace the custom WebGL loader with Babylon.js only after an accepted GLB exists. Renderer work before valid assets would improve the picture frame while the canvas is still on fire.
10. If Candidate 1 fails the stop conditions, perform one Unreal sidecar spike. If that also fails, stop implementation and choose explicitly between commercial licensing, more contributors and budget, or a narrower product goal.

## Falsifiable 1 to 2 day proof

This is a proof plan, not authorization to install dependencies, resume the paused app or virtual machine, or mutate product code.

### Question

Can one exact Patternal revision be transformed from native 2D semantics into a collision-free arranged garment, solved on the exact fitted body, reviewed from fixed angles, and returned with complete revision identity without manual mesh repair between stages?

### Inputs

1. Use the current full-bust feminine baseline and the current exact 14-panel shirt. It is difficult enough to expose the known failure. A four-panel toy can be a smoke test, but it cannot decide the architecture.
2. Freeze one fabric calibration, neutral pose, body revision, pattern revision, seam graph, triangulation, solver seed, and camera set.
3. Use the current MHR fitted body only as the existing control. This does not accept MHR as the product avatar.

### Day 1: arrangement and identity

1. Export a fresh immutable revision bundle from existing authoritative sources. Record SHA-256 for the document, body profile, fitted body, collider, panel mesh, seam graph, material coordinates, fabric, pose, and every tool binary.
2. Produce one authored 3D arrangement for the current 14-panel shirt around the exact collider. The arrangement may be made in Blender for the proof, but no vertex repair, seam reassignment, or panel replacement is allowed after the recorded export.
3. Require zero cloth-body and cloth-cloth intersections, outward-consistent panel orientation, preserved panel and seam IDs, complete material-space correspondence, no inverted or degenerate triangles, and a recorded clearance envelope before simulation.
4. Require every paired seam to be close enough for the solver's declared capture model. Set the threshold before seeing the result. The prior 55.519 cm maximum is an automatic failure; a proposed starting gate is 2 cm maximum for this proof, unless the solver's primary documentation establishes a tighter bound.
5. Run the frozen Newton adapter once as a control on this materially different arrangement. Do not tune it after looking at the result. If dependency installation is separately approved, run XRTailor once on the same semantic input, but reject the route if conversion requires Marvelous Designer or changes topology or seam identity.

### Day 2: revision, drape, and presentation

1. Create two bounded body revisions, one changing bust and one changing waist, plus one bounded pattern revision. Regenerate the complete chain from clean state for each revision.
2. Require the final cloth to satisfy the repository's existing final limits: static equilibrium, zero body and self-intersections, maximum seam separation at most 0.25 cm, maximum edge strain at most 0.40, p95 at most 0.15, p99.9 at most 0.29, p99.99 at most 0.55, and high-strain edge fraction at most 0.0005.
3. Require regional reports for left sleeve, right sleeve, front, back, neckline, hem, underarms, and each seam family. No aggregate metric may hide a local explosion.
4. Produce a compact indexed GLB and six canonical Blender renders. Bind every image and the GLB to the same revision manifest. Human-review the garment silhouette, hang, sleeve shape, neckline, seams, thickness, body clearance, fabric scale, hands, hair, modesty, and pose.
5. Regenerate one revision from an empty cache and compare identities and measurements. Deterministic hashes are preferred; if the solver is nondeterministic, record the allowed metric and image variance before running it twice.
6. Only after the offline chain passes, request separate authorization to resume the packaged UI and physical-GPU tests. Load exactly the accepted GLB, exercise cameras, sliders, toggles, save and reload, stale-cloth invalidation, keyboard paths, Narrator, resize, themes, and offline startup.

### Pass definition

The architecture proof passes only if all three nonbaseline revisions preserve source identity, pass the numerical gates, and receive unqualified human acceptance from every required view without manual repair after bundle creation.

## Stop conditions

1. Stop if an unmapped UI edit can still display accepted-avatar or exact-fit wording.
2. Stop if the 14-panel arrangement cannot reach the declared pre-solve intersection, orientation, semantic, and seam-proximity gates within four focused hours. Do not compensate with stronger sewing.
3. Stop a solver if it changes panel topology, seam correspondence, material coordinates, body identity, or pose without declaring and proving the mapping.
4. Stop after one frozen control run and one documented challenger run if the same failure class recurs. Do not launch a parameter sweep over a bad contract.
5. Stop XRTailor if native Patternal panels require a CLO or Marvelous Designer authoring round trip, unless the owner explicitly accepts that commercial authoring dependency.
6. Stop C-IPC work if the proof requires implementing a new general-purpose seam system, textile-calibration suite, remesher, or garment authoring environment before one revision can run.
7. Stop Unreal if the packaged spike cannot generate or load the exact edited revision without editor-only Dataflow steps, experimental runtime MetaHuman APIs, or a second inaccessible UI path.
8. Stop any licensed-asset route without written rights for derivative fitting, source control, backup, extractable package redistribution, and perpetual use.
9. Stop Style3D work without written contractual permission that overrides the competing-app prohibition and grants offline redistribution.
10. Stop promotion if any required evidence exists only in a source tool, screenshot, development host, cache, previous revision, or different GPU.

## Exact evidence required before promotion

### Legal and supply-chain evidence

1. A bill of materials for every executable, library, model, texture, hair asset, font, sample, and generated dataset, with exact version, source URL, SHA-256, license text, attribution obligations, redistribution rights, and transitive dependencies.
2. Written asset rights covering derivative fitting, extractable package distribution, source control, backup, offline use, and continued use after a vendor or subscription disappears.
3. A clean-machine audit proving no undeclared runtime, online service, personal cache, environment variable, or developer-installed application is required.

### Revision and provenance evidence

1. One signed or hash-bound manifest linking the 2D document, all 151 input values, declared 3D-supported controls, avatar generator, fitted state, rig, display mesh, collider, pose, panels, seams, notches, material coordinates, fabric, arrangement, solver, seed, equilibrium, GLB, and review images.
2. Fail-closed evidence for every unsupported body value, garment operation, pose, GPU, and missing worker.
3. A clean-cache rerun proving that no previous accepted asset or warm start can leak into a new revision.

### Avatar evidence

1. Baseline, midpoint, minimum, maximum, pairwise, and compound holdouts across the declared 3D control envelope. Endpoint-only tests are insufficient.
2. Measurement residuals, surface displacement, triangle inversion, self-intersection, topology, landmark, rig, pose, collider registration, and accessory clearance reports for each holdout.
3. Fixed front, rear, left, right, and oblique DCC renders plus packaged renders for each boundary case, with explicit review of scalp, hair, eyes, mouth, hands, fingers, bust, underbust, abdomen, hip, arms, modesty geometry, posture, and silhouette.
4. Direct proof that an edit outside the supported 3D set produces an honest unsupported or unchanged-preview status, never an accepted-fit label.

### Cloth evidence

1. The existing exact final gates: static equilibrium; zero body and self-intersections; maximum seam separation at most 0.25 cm; maximum edge strain at most 0.40; p95 at most 0.15; p99.9 at most 0.29; p99.99 at most 0.55; high-strain edge fraction at most 0.0005.
2. Initial-arrangement evidence for clearance, orientation, seam proximity, stable panel identity, complete material coordinates, no degeneracy, and no manual repair after export.
3. Region-by-region metrics and images for sleeves, underarms, neckline, bust, waist, back, hem, darts, and every seam family.
4. Multi-angle human acceptance of silhouette, seam continuity, fold plausibility, fabric scale, thickness, no holes, no black interiors, no penetration, correct side, gravity, balance, and correspondence with the exact 2D revision.
5. A side-by-side comparison with the same garment, body, pose, and fabric in a legitimate CLO reference or other accepted garment-quality oracle. Patternal need not match pixels, but material response, silhouette, and defect freedom must be comparable under a documented rubric.

### Renderer and package evidence

1. The compact GLB hash must match in Blender and the packaged viewer. Camera names, framing, near and far planes, color management, materials, normals, winding, transparency, and texture hashes must be recorded.
2. Exact package identity, version, installer size, installed size, worker size, cold start, warm start, body regeneration time, arrangement time, solve time, GLB build time, peak RAM, peak graphics memory, GPU model, driver, CPU, and operating-system build.
3. An offline fresh-install run with network disabled, followed by uninstall evidence showing no undeclared services, global runtimes, user-profile debris, or machine-wide mutations.
4. Packaged checks on a supported physical GPU and on the declared unsupported or fallback hardware path.
5. The existing 2D and 3D toggle, slider, camera, persistence, save and reload, Undo and Redo, accessibility-name, keyboard, resize, text-scale, and theme gates, plus a human Narrator pass.
6. Current-cloth freshness proof after body edits, pattern edits, fabric edits, save and reload, restart, worker failure, and cache deletion.

## Promotion rule

No architecture, dependency, model, solver, renderer, screenshot, or package is promoted because it installs, launches, exports a valid file, passes a subset of metrics, or looks plausible from one angle. Promotion requires the complete revision chain, exact numerical gates, legal audit, offline package proof, physical-GPU proof, accessibility proof, persistence proof, and hash-bound multi-angle human acceptance.

Until that evidence exists, the correct status is simple: Patternal has a strong packaged 2D application, a promising but untruthful and visually rejected avatar preview, and no accepted current cloth engine.

## Post-review execution result

The first execution round confirmed the review rather than weakening it.

1. `tools/revision_bundle.py` now creates and verifies closed, content-addressed, deterministic source bundles. Source bundles cannot claim acceptance or overwrite an existing directory.
2. Control bundle `8d2f41b6e4bc64d7c65f5e05d998eda60680d2a204418fd34365f69ab39bee0e` is explicitly rejected and records its incomplete source document, rejected Antonia display body, rejected arrangement, and absent cloth acceptance.
3. The current 14-panel arrangement begins with 142 body intersections, 4,157 self-intersections, hundreds of degenerate or sliver triangles, and 4.128 cm penetration. The current arrangement, Newton tuning path, and PPF tuning path are frozen.
4. The PPF adapter was proven to ignore the declared `output_mesh_path` and substitute `physical_mesh_path`, reintroducing the 55.519 cm spread-panel surface. This is a contract violation, not solver evidence.
5. The packaged MHR path now receives the complete set of changed UI keys. Baseline and represented edits are labeled as previews with open collider, cloth, and visual gates. Unmapped or out-of-range edits fail closed as unsupported for 3D.
6. Candidate 1 remains the preferred architecture boundary, but its current arrangement implementation has failed. The next solver action is the separately approved XRTailor input-compatibility spike described above. No dependency has been installed by this review or execution round.
7. The XRTailor compatibility audit rejected installation. Its official custom-asset workflow requires Marvelous Designer for pattern design, manual panel positioning, sewing, draping, and welded OBJ export; Unfold3D or RizomUV for manual UV repair; and MeshLab for annotations. Native Patterna panels cannot enter the documented route without the prohibited commercial round trip and topology-changing weld.
8. The installed Unreal 5.8 project also fails the sidecar stop condition. Runtime code selects fixed cooked `/Game/...` garment assets. Cloth construction and repair live in the editor-only module and require Dataflow regeneration and package saving. No packaged runtime path imports the exact current revision bundle. Another Unreal build would extend an editor-dependent authoring system rather than prove the product contract.
9. The remaining decision is now explicit: narrow the product to strong 2D authoring plus honest preview-only 3D, accept a licensed CLO-class application as a developer or user companion, negotiate a redistributable commercial engine, or fund a substantially larger custom garment-engine effort. Continuing to rotate among free solvers without changing those constraints is rejected.

## Continued adversarial result

The next bounded execution produced two more structural corrections and then stopped the custom geometry path.

1. Revision bundle 1.0 incorrectly treated arrangement as an immutable source input. Source-only bundle 1.1 corrected that circular authority boundary. Bundle 1.2 then added the missing global panel index map required to interpret authoritative seam links without guessing ownership. All three historical bundles remain immutable and verifiable.
2. The source, arrangement artifact, and independent verification report are now three separately hash-bound facts. The arrangement producer begins rejected and cannot manufacture the accepted capability required by a solver.
3. A rigid exact-topology candidate preserved source identity, triangle quality, and effectively zero strain, but failed at 672 self-intersecting edges and 7.556 cm worst seam separation after authoritative seam mapping.
4. A global exact-topology ARAP candidate reduced worst seam separation to 1.889 cm and p95 strain to 0.102, but created 1,868 self-intersecting edges, local inversions, and one 11.886 peak-strain edge. It is rejected.
5. A horizontal body-profile mapping was tested once and retired. It treated material-space horizontal fractions as a valid parameterization across darts and compound boundaries. The result had 2,110 body intersections, 2,617 self-intersections, p95 strain of 1.096, and extensive torso inversions. Its premise was false, so no parameter tuning followed.
6. The custom arrangement path has reached its stop condition. The next candidate is a process-isolated contact-aware engine behind the same exact artifact and verifier boundary, not another repository-owned projection heuristic.
7. libuipc v0.0.25 is the strongest current candidate. Its exact release contains an Apache 2.0 license and a signed CPython 3.12 Windows wheel, while its package classifier still incorrectly or ambiguously says GPLv3. Dependency installation remains separately permissioned and must occur in a dedicated Patterna challenger environment.
8. The official Anny 0.6.0 wheel, SHA-256 `050a0b24a3e7fdb89b46dc3581947ea84225305425ac9a1a97b65ea997fb2ad6`, is the next avatar bakeoff artifact. Its contract permits only the Apache 2.0 code, CC0 native data, native triangular topology, and compact rig. It forbids implicit downloads and every SMPL or SMPL-X path. Post-release commit `81ca83e202273b306205c1cc15f33734be31e48c` remains reviewed provenance rather than executable mutable source.
9. `patterna.avatar-worker-output-manifest/1.0` now separates producer evidence from acceptance. It requires all display, collider, mapping, measurement, registration, rejection, and review-render roles; binds all 152 current built-in and custom controls to an explicit mapped or unsupported row; and keeps every acceptance claim false. The historical Anny 0.5 fitter's self-issued numerical `accepted` Boolean cannot satisfy this contract.
