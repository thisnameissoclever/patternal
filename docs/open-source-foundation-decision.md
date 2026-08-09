# Open-source avatar and cloth foundation decision

Status: active architecture decision, reverified against primary project documentation and release metadata on 2026-08-09. The user approved the pinned MHR and PPF challengers, and both are now installed in separate versioned machine-local runtimes. Neither is promoted to the product path.

## Bottom line

Patterna should use a deliberately boring composition of permissive foundations instead of attempting to invent a human generator, garment simulator, renderer, and pattern system at once.

1. Keep WinUI 3 and the native Patterna document model for the Windows product and interactive 2D authoring.
2. Keep GarmentCode as an interchange and meshing reference, not as the visual or simulation product.
3. Keep CC-BY Antonia only as the current fitted control avatar. Stop spending product time polishing its visible texture seams, bald presentation, or coarse bandeau unless a change is needed to keep the control honest.
4. Keep Newton Style3D as the existing rejected control backend.
5. Evaluate the installed ZOZO PPF Contact Solver as the first cloth challenger.
6. Keep Blender as the offline GLB assembly, rendering, and visual-proof boundary.
7. Evaluate the installed Meta Momentum Human Rig LOD1 runtime as the first avatar challenger. The maintainer confirmed on 2026-06-10 that its assets are Apache 2.0 and updated `assets.zip` to include the license. Patterna now has a hash-locked TorchScript runtime, narrow mesh bridge, measurement fitter, anthropometry helpers, and focused tests. The first visual result is materially more human than Antonia, but its native identity fit is rejected and it is not a product asset yet.
8. Keep Anny 0.5 as a semantic measurement and collision comparator. Its Apache-2.0 code, CC0 MPFB2 data, native shape controls, texture coordinates, and optional Apache-2.0 SOMA topology are useful, but its MakeHuman-derived appearance does not solve the rejected hero-avatar problem.
9. Keep SOMA-X 0.2.1 as a later interoperability layer for shared topology, rigging, pose correctives, and procedural twist joints if MHR wins. Do not add it to the first bake-off because it adds CUDA PyTorch, Warp, Git LFS or auto-downloaded assets, and another mapping layer before the base avatar is accepted.
10. Use Blender Studio's CC0 Human Base Meshes only as sculpted detail, topology, and appearance references. They are not parametric bodies and do not replace measurement fitting.
11. Do not adopt XRTailor as the primary authoring or assembly solver. Its documented custom-garment path starts with Marvelous Designer sewing and draping, then imports a welded template. That does not remove the CLO-class dependency Patterna is trying to replace.

## Decision matrix

| Foundation | License evidence | What it actually supplies | One-person practicality | Decision |
| --- | --- | --- | --- | --- |
| CharMorph Antonia | Character is CC-BY; the vendored character includes its exact license and attribution | Stable 36,030-vertex feminine body, UVs, material regions, named morphs, underwear, and a Blender source | Already integrated, fitted, exported to GLB, packaged, and hash-bound | Current control avatar |
| MakeHuman and MPFB core assets | Core graphical assets are CC0; tool code is GPL or AGPL | Hair, eyes, skin, clothing proxies, targets, rigs, and Blender fitting tools | Assets are already vendored, but topology-specific proxies need a new fit to Antonia | Appearance donor only, never assume cross-body fit |
| Meta Momentum Human Rig | Apache 2.0 code and assets; the maintainer confirmed the asset license and added it to the release ZIP on 2026-06-10 | 45 identity parameters, 204 pose parameters, 72 facial controls, pose correctives, detailed face and hands, seven levels of detail, rigged FBX assets, and a LOD1 TorchScript path | Installed as a hash-locked Python 3.12 and CPU PyTorch 2.12.1 runtime. Neutral geometry and five-view rendering pass; the first full-bust measurement fit is rejected. | Active avatar challenger, not promoted |
| Anny 0.5 | Apache-2.0 code, CC0 MPFB2 data, and optional Apache-2.0 SOMA data; optional SMPL-X topology is separately non-commercial and excluded | Interpretable age and body controls, stable topology, hands and face models, rigging, texture coordinates, differentiable fitting, and SOMA interoperability | Patterna already contains an Anny fitter and garment-collider preparation path, but the current product has already rejected MakeHuman-family appearance. Its own installation notes warn that the free examples extra may download non-commercial assets, so any comparator runtime must disable implicit downloads and admit only hash-pinned MPFB2 and SOMA data. | Measurement and collision comparator, not hero display |
| SOMA-X 0.2.1 | Apache-2.0 code; optional identity backends and downloaded assets retain their own terms | One topology and rig across MHR, Anny, GarmentMeasurement, and separately licensed SMPL-family inputs, with shared pose correctives, procedural twist joints, extra-low level of detail, and Blender and Maya reference tools | Valuable only after one identity source wins; otherwise it adds a second parametric layer, Git LFS assets, CUDA PyTorch, Warp, and another mapping layer | Later interoperability challenger |
| Blender Human Base Meshes 1.4.1 | CC0 asset bundle from Blender Studio | Realistic and stylized closed quad meshes, multi-resolution sculpt detail, UVs, hands, feet, heads, eyes, jaws, and teeth | Excellent reference and donor material, but no measurement model, production rig, or fitted clothing follows automatically | Appearance and topology reference only |
| Newton Style3D | Apache 2.0 Newton and current Apache-2.0 Warp | GPU shell simulation with current Patterna seam adapter | Already owned and reproducible; exact Antonia control renders remain rejected | Keep as control backend |
| ZOZO PPF Contact Solver | Apache 2.0 with explicit proprietary and commercial-use permission | GPU finite-element shells, contact barriers, strain limiting, friction, pins, cross-object soft stitches, Windows executable, Docker service, Blender API, and offline fitting examples | Installed from the 2026-08-08 native Windows archive. A real RTX 4090 headless contact smoke passes without desktop focus; the Patterna garment adapter remains unproven. | Active cloth challenger, not promoted |
| XRTailor | Codebase declares Apache 2.0 and lists third-party licenses | CUDA cloth, obstacle collision, self-collision, anisotropic quality mode, GLTF animation input, and Alembic or OBJ output | Windows build is non-trivial. Documented custom assets require Marvelous Designer, RizomUV, MeshLab, and an already welded and draped garment template | Do not use as primary assembly solver; possible later animation comparator |
| PositionBasedDynamics | MIT | General XPBD constraints, deformables, collision, signed-distance fields, C++ and Python interfaces | Mature and Windows-capable, but Patterna would still have to build sewing, fabric calibration, contact policy, and garment exchange around it | Reference implementation only |
| IPC Toolkit and C-IPC | MIT project licenses | High-accuracy codimensional continuous contact and friction | Excellent offline oracle; substantial C++ integration and poor interactive-product fit | Difficult-case validator only |
| MB-Lab | GPL/AGPL family data and archived repository | Parametric bodies and Blender character tools | Repository is archived and its own README says development moved to CharMorph | Reject |
| SMPL family | Model licenses differ from the open-source wrappers that consume them | Research-standard body topology and motion ecosystem | License and registration requirements make it a poor default for a freely redistributable personal Windows app | Do not make it the product boundary |

## Concrete pinned evaluation inputs

The first evaluation must use exact artifacts, not whichever GitHub asset happens to sort as latest that morning:

1. MHR `v1.0.1` `assets.zip`: 198,943,157 bytes, GitHub-published SHA-256 `e4f4f205cd87c0fa106577ba1de4fc763e4eb197c924461d2ef7e6944e9d6b94`. The release note says the license was added to the assets. This is the only MHR archive eligible for the first bake-off.
2. PPF native solver tag `2026-08-08-03-55`: `ppf-contact-solver-2026-08-08-03-55-win64.zip`, 447,925,491 bytes, GitHub-published SHA-256 `50d84ce0c9bc57d6d72564efa21b66c19c4e5e7e9eddd528c4d9fa050f5cafec`.
3. PPF Blender add-on tag `addon-2026-08-08-0540`: `ppf_contact_solver_2026_08_08_0540.zip`, 3,884,115 bytes, GitHub-published SHA-256 `0254a9d5fb54cd41f3a71d34896a043f938e089977694a7ba8156e54d97c50c2`. This is optional for the first file-driven solver experiment.
4. Do not resolve PPF through GitHub's generic latest-release endpoint. The add-on was published 41 seconds after its matching native engine and currently wins that endpoint despite not containing the engine.
5. The host currently reports an RTX 4090, NVIDIA driver 610.88, 24,564 MiB, compute capability 8.9, and CUDA user-mode driver 13.3. The pinned executable now passes an actual GPU contact smoke on this configuration.

## Installed challenger evidence

1. MHR is installed at `%LOCALAPPDATA%\Patterna\ChallengerRuntimes\MHR\v1.0.1-py312-torch2.12.1-cpu`. Runtime manifest SHA-256 is `099c2820523f28dd16c7542f0ae47d00f8b3f7d41c5b4da39f8209332af60765`. Its Python environment is populated only from the committed 11-wheel hash lock.
2. PPF is installed at `%LOCALAPPDATA%\Patterna\ChallengerRuntimes\PPF\2026-08-08-03-55-win64`. Runtime manifest SHA-256 is `d573eee78e85be5c745de1163201257dd97466e2c19bad1e725c0f6d4a7ba44a`. The exact tag's Apache license is retained beside the distribution because the Windows ZIP includes third-party notices but omits the primary repository license.
3. Re-running the installer reuses both validated version roots without deleting or rewriting them. The accepted Antonia/Newton runtime at `%LOCALAPPDATA%\Patterna\SimulationRuntime\current` is untouched.
4. The PPF smoke completed 20 frames on the RTX 4090 in 7.365 seconds, recorded 221 nonzero contact samples and a peak of 118 contacts, produced finite output, and left the immutable runtime tree unchanged. This proves native GPU startup and basic contact only.
5. MHR neutral LOD1 generation produces 18,439 vertices and 36,874 triangles at exactly 167 cm. Five-view Blender inspection shows credible face, hands, feet, and body surfaces compared with the current control, but still lacks production materials, eyes, hair, and modesty clothing.
6. The first bounded full-bust fit is rejected. Best stage 9 has loss `8.561374`, saturates body coefficients 3, 8, 11, 12, and 14, and misses every required measurement tolerance. Largest errors are upper arm `+6.553 cm`, hip `-4.325 cm`, and bust `-2.692 cm`. MHR therefore cannot be promoted as the measured body without an accepted local-deformation or hybrid fitting stage.

## Why PPF is the first challenger

PPF now exposes the missing garment-specific primitives that generic cloth examples usually hand-wave away:

1. Separate shell objects can be connected by cross-object soft stitches rather than welded before solve.
2. Stitch anchors bind source vertices to target triangles with barycentric evidence and topology counts.
3. Contact gaps remain positive during solve, while an optional exact post-snap makes the fetched render surface read as sewn.
4. Strain limits, finite-element elasticity, friction, pins, static colliders, and penetration-resistant contact exist in the same solver.
5. The current Windows-native distribution can run as a local background service. Patterna can drive it through files and a local API without stealing mouse focus or opening an interactive Blender window.

This is still a challenger, not a foregone conclusion. Its snap workflow expects intended stitch regions to be spatially coincident or close enough to capture. The Patterna adapter must prove that every authored seam pair becomes the intended anchor set without accidentally stitching nearby cuffs, collars, darts, or body surfaces. Soft stitches must also meet the existing closure limit before any exact post-snap; post-processing cannot hide a failed solve.

## PPF evaluation boundary

PPF is installed in a separate versioned runtime. Do not alter the accepted Newton runtime in place.

1. Prefer the hash-pinned `2026-08-08-03-55` Windows-native release over Docker for the first local evaluation. It is headless, avoids a second Linux and GPU-container layer, and does not require the Blender add-on.
2. Record the release URL, release tag, downloaded SHA-256, license, executable hashes, NVIDIA driver, GPU, and every solver parameter.
3. Convert the existing 0.50 cm common bundle into one shell object per material panel with exact seam vertex identities.
4. Create stitch anchors from the existing seam correspondence, not from unconstrained nearest-neighbor guessing.
5. Use fitted Antonia as a static collider and keep the exact body, pattern, fabric, cameras, and acceptance thresholds used by the Newton control.
6. Reject any run that needs post-snap to conceal seam separation, collision, or strain failure.
7. Render and review the exact six-view result before choosing a backend.

## Avatar path

Antonia is the current rational control because it is already local, attributable, inspectable, and good enough to expose cloth defects instead of contributing grotesque base anatomy. It is not the rational production destination. The packaged review rejects its texture transitions, bald scalp, coarse modesty shell, and the completely different MakeHuman-derived body shown after measurement edits. Further cosmetic Antonia work would preserve the same two-body architecture that caused the complaint.

MHR LOD1 is now the first production challenger because its license blocker is resolved and it attacks the actual deficits: body-shape range, detailed hands and face, one stable topology, a skeleton, pose correctives, and a compact TorchScript inference path. It still does not provide a finished Patterna character by magic. The first bake-off must add a deliberately neutral PBR material, eyes, fitted CC0 hair, and modesty clothing, then prove measurement fit and all six packaged cameras. A grey research mesh with better fingers is still a grey research mesh.

The first installed-runtime result validates that distinction. The geometry is visibly more credible than Antonia in front, rear, both side, and oblique renders, but the bounded statistical identity cannot reach the exact full-bust and thin-upper-arm profile. The result stays a rejected research candidate until a topology-preserving local fit passes the measurement, registration, anatomy, appearance, and packaged-camera gates.

The minimum Antonia control work is:

1. Keep its exact license, fitted geometry, and collision hashes reproducible as the control.
2. Do not present the display-only bandeau as fitted clothing.
3. Preserve the current visual rejection in six-view evidence.
4. Avoid new Antonia-only hair, material, or pose work unless MHR fails its first controlled bake-off.

The MHR bake-off boundary, after dependency approval, is:

1. Create a separate versioned runtime with Python 3.11 or 3.12, CPU PyTorch, and `mhr_model.pt` extracted from the hash-pinned v1.0.1 asset archive. Do not install into the host's Python 3.14 environment and do not alter the Antonia runtime.
2. Record the release URL, asset ZIP SHA-256, embedded Apache-2.0 license hash, Torch version, runtime lock, and every generated-output hash.
3. Run the existing neutral bridge and focused unit tests before fitting any measurement profile.
4. Fit the same 167 cm full-bust profile using the existing measurement fitter. Bound every identity coefficient, report every circuit and landmark residual, and reject anatomy that only wins numerically.
5. Export one display GLB and one watertight collision body from the same identity and pose revision. Report regional display-to-collision distance and exact floor alignment.
6. Fit one concrete vendored CC0 hair asset and simple modesty clothing to the exact MHR revision. Record per-asset licenses and surface-clearance checks.
7. Render front, rear, both sides, and both obliques in Blender, then package the exact accepted hashes and repeat the six semantic cameras in the VM.
8. Keep Antonia if MHR fails measurement coverage, surface quality, runtime latency, license packaging, or multi-view review. A newer model is a challenger, not an automatic promotion.

The backend-neutral regional registration, gross-anatomy, and symmetric inspection-pose reports are implemented in runtime `2026.08.09-style3d-antonia-v7`. Registration compares display and collision surfaces bidirectionally by head, torso, arms, and legs without requiring identical topology, rejects non-finite input, and enforces a shared floor datum. The anatomy report evaluates proportion ratios plus 108 paired rig landmarks. The pose report requires a symmetric shallow A-pose and keeps pose separate from human proportions. The exact fitted Antonia control remains registered but is rejected because upper-arm length is 0.153202 times stature and its arms rise 12.452430 degrees above horizontal. Fresh GLB import proves that all 36,030 fitted positions survive material-driven vertex splitting with no missing or unexpected surface positions. The MHR bake-off must emit compatible display-material regions and semantic landmarks, then pass all three reports before product visual proof can be accepted. A low-detail collider is not allowed to drift away from the human it claims to represent merely because decimation completed successfully.

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

Momentum Human Rig is eligible for a controlled bake-off now that the asset archive includes an explicit Apache-2.0 license. Its statistical identity coefficients are still not Patterna measurements. It needs the same constrained measurement fitting, anatomical review, collision derivation, GLB export, appearance assembly, and license hashing required of Antonia before it can replace anything.

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
7. Anny: <https://github.com/naver/anny>
8. SOMA-X: <https://github.com/NVlabs/SOMA-X>
9. Blender Human Base Meshes: <https://www.blender.org/download/demo-files/#assets>
10. MakeHuman and MPFB asset licensing: <https://static.makehumancommunity.org/about/license.html>
11. CharMorph character licensing: <https://blendercharacterproject.org/docs/html/Introduction.html>
12. PositionBasedDynamics: <https://github.com/InteractiveComputerGraphics/PositionBasedDynamics>
13. IPC Toolkit: <https://ipctk.xyz/>
14. MHR v1.0.1 release: <https://github.com/facebookresearch/MHR/releases/tag/v1.0.1>
15. PPF 2026-08-08 Windows release: <https://github.com/st-tech/ppf-contact-solver/releases/tag/2026-08-08-03-55>
16. PPF 2026-08-08 Blender add-on release: <https://github.com/st-tech/ppf-contact-solver/releases/tag/addon-2026-08-08-0540>
17. SOMA-X v0.2.1 release: <https://github.com/NVlabs/SOMA-X/releases/tag/v0.2.1>
