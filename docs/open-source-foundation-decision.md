# Open-source avatar and cloth foundation decision

Status: active architecture decision, verified against primary project documentation on 2026-08-08. No dependency is approved or installed by this document.

## Bottom line

Patterna should use a deliberately boring composition of permissive foundations instead of attempting to invent a human generator, garment simulator, renderer, and pattern system at once.

1. Keep WinUI 3 and the native Patterna document model for the Windows product and interactive 2D authoring.
2. Keep GarmentCode as an interchange and meshing reference, not as the visual or simulation product.
3. Keep CC-BY Antonia as the current fitted feminine avatar foundation. Add CC0 MakeHuman appearance assets only when they pass a fresh Antonia fit and visual review; their permissive license does not make a bad fit acceptable.
4. Keep Newton Style3D as the existing rejected control backend.
5. Evaluate ZOZO PPF Contact Solver as the first cloth challenger after explicit dependency approval.
6. Keep Blender as the offline GLB assembly, rendering, and visual-proof boundary.
7. Treat Meta Momentum Human Rig as a future avatar challenger only after its downloadable model assets carry an explicit reviewed license artifact.
8. Do not adopt XRTailor as the primary authoring or assembly solver. Its documented custom-garment path starts with Marvelous Designer sewing and draping, then imports a welded template. That does not remove the CLO-class dependency Patterna is trying to replace.

## Decision matrix

| Foundation | License evidence | What it actually supplies | One-person practicality | Decision |
| --- | --- | --- | --- | --- |
| CharMorph Antonia | Character is CC-BY; the vendored character includes its exact license and attribution | Stable 36,030-vertex feminine body, UVs, material regions, named morphs, underwear, and a Blender source | Already integrated, fitted, exported to GLB, packaged, and hash-bound | Current avatar foundation |
| MakeHuman and MPFB core assets | Core graphical assets are CC0; tool code is GPL or AGPL | Hair, eyes, skin, clothing proxies, targets, rigs, and Blender fitting tools | Assets are already vendored, but topology-specific proxies need a new fit to Antonia | Appearance donor only, never assume cross-body fit |
| Meta Momentum Human Rig | Repository declares Apache 2.0; a closed issue notes that the release asset ZIP lacks its own license or notice | 45 identity parameters, 204 pose parameters, 72 facial controls, pose correctives, detailed face and hands, and seven levels of detail | Technically strong, but adds Python 3.11, PyTorch, PyMomentum or TorchScript, asset download, semantic measurement fitting, and license review | Research-only avatar challenger |
| Newton Style3D | Apache 2.0 Newton and current Apache-2.0 Warp | GPU shell simulation with current Patterna seam adapter | Already owned and reproducible; exact Antonia control renders remain rejected | Keep as control backend |
| ZOZO PPF Contact Solver | Apache 2.0 with explicit proprietary and commercial-use permission | GPU finite-element shells, contact barriers, strain limiting, friction, pins, cross-object soft stitches, Windows executable, Docker service, Blender API, and offline fitting examples | Native Windows package is about 320 MB, needs a modern NVIDIA driver but no local Python or CUDA Toolkit, and can run headlessly without desktop focus | First cloth challenger after approval |
| XRTailor | Codebase declares Apache 2.0 and lists third-party licenses | CUDA cloth, obstacle collision, self-collision, anisotropic quality mode, GLTF animation input, and Alembic or OBJ output | Windows build is non-trivial. Documented custom assets require Marvelous Designer, RizomUV, MeshLab, and an already welded and draped garment template | Do not use as primary assembly solver; possible later animation comparator |
| PositionBasedDynamics | MIT | General XPBD constraints, deformables, collision, signed-distance fields, C++ and Python interfaces | Mature and Windows-capable, but Patterna would still have to build sewing, fabric calibration, contact policy, and garment exchange around it | Reference implementation only |
| IPC Toolkit and C-IPC | MIT project licenses | High-accuracy codimensional continuous contact and friction | Excellent offline oracle; substantial C++ integration and poor interactive-product fit | Difficult-case validator only |
| MB-Lab | GPL/AGPL family data and archived repository | Parametric bodies and Blender character tools | Repository is archived and its own README says development moved to CharMorph | Reject |
| SMPL family | Model licenses differ from the open-source wrappers that consume them | Research-standard body topology and motion ecosystem | License and registration requirements make it a poor default for a freely redistributable personal Windows app | Do not make it the product boundary |

## Why PPF is the first challenger

PPF now exposes the missing garment-specific primitives that generic cloth examples usually hand-wave away:

1. Separate shell objects can be connected by cross-object soft stitches rather than welded before solve.
2. Stitch anchors bind source vertices to target triangles with barycentric evidence and topology counts.
3. Contact gaps remain positive during solve, while an optional exact post-snap makes the fetched render surface read as sewn.
4. Strain limits, finite-element elasticity, friction, pins, static colliders, and penetration-resistant contact exist in the same solver.
5. The current Windows-native distribution can run as a local background service. Patterna can drive it through files and a local API without stealing mouse focus or opening an interactive Blender window.

This is still a challenger, not a foregone conclusion. Its snap workflow expects intended stitch regions to be spatially coincident or close enough to capture. The Patterna adapter must prove that every authored seam pair becomes the intended anchor set without accidentally stitching nearby cuffs, collars, darts, or body surfaces. Soft stitches must also meet the existing closure limit before any exact post-snap; post-processing cannot hide a failed solve.

## PPF evaluation boundary

After explicit dependency approval, install PPF into a separate versioned runtime. Do not alter the accepted Newton runtime in place.

1. Prefer the signed or workflow-proven Windows-native release over Docker for the first local evaluation. It is headless, avoids a second Linux and GPU-container layer, and does not require the Blender add-on.
2. Record the release URL, release tag, downloaded SHA-256, license, executable hashes, NVIDIA driver, GPU, and every solver parameter.
3. Convert the existing 0.50 cm common bundle into one shell object per material panel with exact seam vertex identities.
4. Create stitch anchors from the existing seam correspondence, not from unconstrained nearest-neighbor guessing.
5. Use fitted Antonia as a static collider and keep the exact body, pattern, fabric, cameras, and acceptance thresholds used by the Newton control.
6. Reject any run that needs post-snap to conceal seam separation, collision, or strain failure.
7. Render and review the exact six-view result before choosing a backend.

## Avatar path

Antonia is the current rational choice because it is already local, attributable, inspectable, and good enough to expose cloth defects instead of contributing grotesque base anatomy. It still needs work:

1. Add fitted hair from a concrete CC0 or CC-BY asset and record its source and fit report.
2. Convert source height maps into GLB-safe tangent-space normal maps.
3. Improve skin material balance and remove visible texture-region transitions.
4. Derive a simplified watertight collision body and report regional display-to-collision distance.
5. Expand semantic measurement coverage beyond the currently accepted primary fit set.
6. Add a relaxed display pose only after accepted cloth can follow the same skeleton and pose state.

The generated avatar report uses `accepted` only for its measurement-fit and geometry-export stage because the simulation pipeline must consume that exact result before it can construct a collider. The report also carries `acceptanceScope`, `productAccepted: false`, and a pending product status. Numerical body fit must never be presented as packaged visual or cloth acceptance.

### Interactive customization architecture

The packaged default Antonia candidate and the current real-time measurement preview are two different systems. The default candidate is a textured, measurement-fitted Antonia GLB. Editing any body measurement clears it and exposes the older 151-value MakeHuman-derived deformation mesh. Reviewed guest evidence `20260809-065324-3fec2283` proves the switch and restoration work, but rejects the edited mesh visually: its anatomy, hands, feet, surface detail, and material presentation are below the product gate.

The replacement should preserve one body family from editing through simulation instead of switching topology when the user touches a slider:

1. Treat the existing Antonia fitter, fitted vertices, and GLB exporter as one revisioned avatar-build service independent of cloth solving.
2. Debounce measurement edits and build a new Antonia preview in the managed background runtime. Cache it by the same body-profile revision used by simulation.
3. While the fit is running, keep the last fitted body visibly marked as stale or show a neutral measurement envelope. Do not substitute a different human and imply that it reflects the edited anatomy.
4. Load the revision-matched Antonia GLB when its measurement report and multi-angle preview checks pass. The cloth command should consume the same fitted vertices and collider revision.
5. If immediate continuous slider feedback is later required, export Antonia-compatible morph deltas or a deformation cage and apply them to the same topology in WebGL or WebGPU. Do not revive the current MakeHuman fallback as the product avatar.

This architecture costs some debounced background latency, but it removes the present bait-and-switch between a detailed default body and a visibly inferior edited one. A one-person project can own and test this pipeline because it reuses the already vendored fitter, Blender exporter, cache identity, and license evidence instead of introducing another human ecosystem.

Horizontal collider sections are valid only where the plane crosses the torso without posed limbs. The high-bust tape distribution now comes from the explicit `acrossFront` and `acrossBack` measurements across CharMorph, Anny, and MPFB body preparation. The current Antonia report records the requested 96 cm tape, its 0.5020 back fraction, and that no horizontal collider circuit was used; the former 202.47 cm T-pose arm circuit is rejected evidence, not anatomy.

Momentum Human Rig is worth a controlled future bake-off because it addresses detailed hands, face, pose deformation, and levels of detail in one model. It is not eligible for packaging while its downloadable asset archive lacks an explicit license artifact. Even after that is fixed, its statistical identity coefficients are not Patterna measurements. It would need the same constrained measurement fitting, anatomical review, collision derivation, GLB export, and license hashing required of Antonia.

## Rejected shortcuts

1. Do not treat a commercial CLO or Marvelous Designer output as an open-source solver baseline. That proves an import path, not an independent application.
2. Do not ship random downloadable humans, hair, clothing, or VRM avatars without per-asset terms. A repository license does not automatically cover release assets, model weights, or community uploads.
3. Do not call a body realistic because it has high polygon count or photorealistic texture. Silhouette, proportions, landmarks, pose, material response, and packaged cameras all need review.
4. Do not call cloth physically credible because it has wrinkles. It must pass source identity, sewing, contact, strain, equilibrium, material, and multi-angle visual gates together.
5. Do not let Docker become an architectural comfort blanket. Use it when it isolates a difficult dependency; do not add it around a native background executable merely to make the diagram look modern.

## Primary sources

1. ZOZO PPF Contact Solver: <https://github.com/st-tech/ppf-contact-solver>
2. PPF Snap and Merge seam workflow: <https://st-tech.github.io/ppf-contact-solver/blender_addon/workflow/constraints/snap_merge.html>
3. XRTailor: <https://github.com/openxrlab/xrtailor>
4. XRTailor custom-asset workflow: <https://xrtailor.readthedocs.io/en/latest/common/preparing_your_own_asset.html>
5. Momentum Human Rig: <https://github.com/facebookresearch/MHR>
6. MHR release-asset license question: <https://github.com/facebookresearch/MHR/issues/62>
7. MakeHuman and MPFB asset licensing: <https://static.makehumancommunity.org/about/license.html>
8. CharMorph character licensing: <https://blendercharacterproject.org/docs/html/Introduction.html>
9. PositionBasedDynamics: <https://github.com/InteractiveComputerGraphics/PositionBasedDynamics>
10. IPC Toolkit: <https://ipctk.xyz/>
