# Open-source avatar and cloth replacement audit

Date: 2026-08-22

Status: architecture recommendation, not implementation acceptance

## Direct answer

Patternal should not replace its current mannequin and cloth failures with another single monolithic library. No reviewed open-source project supplies all of these at once: an editable realistic human, a legally redistributable parametric model, exact Patterna panel and seam semantics, body-aware garment arrangement, calibrated anisotropic fabric, robust contact, Windows automation, and presentation-quality rendering.

The best defensible architecture is:

1. Keep Patterna's immutable `RevisionBundle` and parametric 2D document authoritative.
2. Use [Anny v0.6](https://github.com/naver/anny) with only its Apache-2.0 and CC0 data path as the first avatar candidate. Treat appearance quality as unproven until its six-view result passes. Exclude the separately licensed SMPL-X option.
3. Add a deterministic garment adapter and body-aware arrangement stage owned by Patterna. This is the missing subsystem. A more powerful solver will not rescue intersecting, degenerate, badly placed panels.
4. Treat [libuipc](https://github.com/spiriMirror/libuipc) as the strongest bounded new cloth candidate, but do not adopt or install it until its Apache-2.0 repository license and GPLv3 Python package metadata conflict is resolved in writing. Its native triangle meshes, stitch constraints, Windows Python route, and GPU intersection-free contact fit Patterna better than the other general solvers.
5. Keep the already installed Blender 4.5 LTS runtime as a fresh-process renderer and evidence worker. Do not treat Blender Cloth as the CLO-class production solver.
6. Keep [STARK](https://github.com/InteractiveComputerGraphics/stark) as the clean-license CPU fallback. Keep BS-Cloth as a physics and spline-surface oracle, not the first product worker. Reject SOFA, MB-Lab, SMPL-X, ARCSim, and learned simulators as product foundations for the reasons below.

The single best no-install proof is a solver-neutral arrangement and exact-triangle adapter dry run against the existing frozen 14-panel shirt bundle. It should construct collision-free body-aware 3D panel starts, exact vertex, edge, and triangle seam constraints, collider input, and a libuipc-compatible scene manifest, then round-trip everything through the existing arrangement gates. It must not run libuipc, mutate the source bundle, or depend on its unresolved license. A successful output can feed libuipc after clarification or STARK without rebuilding the risky arrangement layer.

## Acceptance contract used in this review

Every candidate was judged against the same boundary:

1. Windows desktop is the product platform.
2. A one-person, personal or noncommercial project still needs a repeatable setup, a complete license inventory, and an architecture that can later be packaged without replacing its foundation.
3. Patterna's 2D document remains the source of truth. Derived meshes are disposable products of a named adapter version.
4. One exact `RevisionBundle` must produce the body, fitted collider, arranged panels, sewn simulation, accepted garment mesh, and multi-angle render evidence.
5. Panel geometry, material coordinates, grain, seam identity and order, fabric parameters, body controls, and stable IDs may not be silently changed to make a solver run.
6. Source acceptance, arrangement acceptance, simulation acceptance, and presentation acceptance remain separate gates.
7. Automation must run in a clean, hash-bound working directory without mouse focus, stale caches, implicit downloads, or undocumented manual cleanup.
8. Code license, model license, character asset license, training-data license, and generated-output license are separate questions. An open-source Python package does not magically launder a restricted body model into an open asset.

## Candidate decision table

| Candidate | Code license | Model or data terms | Windows and automation | Contract fit | Decision |
|---|---|---|---|---|---|
| Blender headless | GPL | User output depends on input assets | Strong Windows CLI and Python automation | Excellent render worker; weak final textile model | Keep for rendering and evidence only |
| MPFB / MakeHuman | MPFB GPLv3; MakeHuman application AGPL | Core assets CC0; generated output is user data | Strong Blender scripting route | Useful body controls, but prior MakeHuman-family appearance failed | Secondary avatar baseline |
| Anny v0.6 | Apache-2.0 | MPFB2 CC0, facial units CC0, SOMA path Apache-2.0; optional SMPL-X remains restricted | Python and PyTorch automation; Windows practicality must be proven | Best clean parametric-body candidate | First avatar bakeoff |
| MB-Lab | GPL family | Character data must be checked separately | Blender addon | Officially retired; architecture and support moved elsewhere | Reject |
| CharMorph | AGPL/GPL family by component | Each character asset has its own terms | Blender automation is possible | Useful fitting and topology tools; no guaranteed measurement-complete hero body | Reference or asset adapter only |
| SMPL-X | Restricted research/personal license | Parametric model and data are nonredistributable under the public license; some generated bodies may be CC-BY | Scriptable | Strong body prior, unacceptable portable product boundary | Oracle only; reject for packaging |
| SOMA-X | Apache-2.0 core | Identity inputs retain their own licenses; SMPL inputs remain restricted | Documents Windows setup | Canonical topology and rig adapter, not an identity generator | Optional later adapter |
| libuipc | Root license Apache-2.0; Python package metadata says GPLv3 | No avatar or garment data; CUDA and dependencies need inventory | Official Windows C++ and Python routes; current wheels require CUDA 12.8 | Exact triangle meshes, stitch constraints, shell models, GPU contact | Best bounded candidate after license clarification |
| BS-Cloth | Apache-2.0 repository | Bundled binary dependencies require a separate bill of materials | Documents Visual Studio 2022; renderer can be disabled | Strong B-spline cloth research, but arbitrary panels require an unproven four-sided conversion | Physics oracle only |
| STARK | Apache-2.0 | Bundled third-party components still require inventory | Source build; Windows reproducibility is not yet proven | Robust contact and exact array API, but generic isotropic shell model | Fallback proof |
| SOFA | LGPL-2.1-or-later core; some projects and tutorials GPL | Plugin-specific terms vary | Official Windows builds and Python scenes | Generic finite-element framework; garment layer would be ours | Reject as primary |
| ARCSim | Research code with repository-specific terms | Example and input assets require separate review | No credible maintained Windows route | Proximity merge and topology assumptions conflict with exact seams | Reject |
| ContourCraft | MIT code | Models, datasets, SMPL family inputs, and CUDA stack have separate terms | Linux-oriented research stack | Learned mesh rollout, not deterministic fabric calibration from authoritative 2D | Reject |

## Avatar findings

### Anny v0.6 is the strongest first body candidate

[Anny](https://github.com/naver/anny) is a differentiable PyTorch body model spanning infant through elder with a common topology and parameter space. Its current repository documents a default 104-bone rig, facial action controls, multiple topology choices, and an optional 163-bone MakeHuman rig. The repository's [license](https://github.com/naver/anny/blob/main/LICENSE) is Apache-2.0. Its documented bundled data separates MPFB2-derived CC0 data, CC0 facial units, and Apache-2.0 SOMA data from the optional SMPL-X download.

That separation matters. The proposed production profile must pin Anny's repository commit and local data hashes, select only the Apache-2.0 and CC0 topology path, set a private cache directory inside the versioned runtime, and fail if any asset download is attempted. The convenient installation path that fetches optional data is unsuitable for a deterministic packaged worker.

Anny does not earn a visual pass from its feature list. Its native mesh is still MakeHuman-derived, and Patternal has already seen the family resemblance turn into an uncanny mannequin. The bakeoff must prove all required body controls, compound pairs, sided values, pose, rig, surface continuity, collider registration, and six-view anatomy. A separate display shell may ultimately be required, but it must be registered to the exact fitted body state and carry explicit asset rights. Until such a shell exists and passes, Anny is a promising body-and-collider generator, not a finished hero avatar.

### MPFB and MakeHuman remain useful infrastructure, not the answer by themselves

[MPFB](https://github.com/makehumancommunity/mpfb2) provides Blender-integrated body creation and macro controls for age, gender, muscle, weight, height, proportions, and breasts. Its [license explanation](https://github.com/makehumancommunity/mpfb2/blob/master/LICENSE.md) distinguishes GPLv3 addon code from bundled CC0 assets and says generated output is user data. The MakeHuman community's [licensing page](https://static.makehumancommunity.org/about/license.html) separately identifies MakeHuman application code as AGPL and core assets as CC0.

This is legally workable when invoked as a separate worker and when every non-core asset is inventoried. It is not enough visually. MPFB remains valuable as a comparison body, a source of CC0 topology and morph knowledge, and a compatibility route for Anny. Repeating it as the principal avatar without a fresh appearance gate would repeat the assumption already disproved by screenshots.

### MB-Lab is retired; CharMorph is the active branch of that idea

MB-Lab's maintainer [announced the project's retirement](https://github.com/animate1978/MB-Lab/discussions/410), stating that its codebase needed a major overhaul and directing development toward CharMorph. The [final MB-Lab release page](https://github.com/animate1978/MB-Lab/releases) repeats that development moved to CharMorph. That is a stop sign, not an invitation to adopt abandoned Blender internals because the screenshots looked convenient.

[CharMorph](https://github.com/Upliner/CharMorph) is the better-maintained successor ecosystem. Its repository documents live asset fitting, alternate topology support, and Rigify integration, while also separating addon licensing from the license of each character data set. It remains useful for fitting research and open character assets. It does not supply a measurement-complete, accepted hero avatar by itself, and Patternal's current Antonia result has already failed visual acceptance.

### SMPL-X is a useful oracle with the wrong product boundary

The public [SMPL-X code and model license](https://github.com/vchoutas/smplx/blob/main/LICENSE) allows limited noncommercial scientific, educational, artistic, and personal use, but restricts distribution and transfer of the model and software. The project's separate [body output license](https://smpl-x.is.tue.mpg.de/bodylicense.html) can permit distribution of some generated body meshes under CC-BY 4.0, excluding the parametric model and shape blendshapes.

That distinction makes a static exported comparison mesh possible. It does not make a redistributable editable avatar worker possible. A product that must regenerate bodies from controls needs the restricted parametric model. Patternal should not build its architecture around the hope that a permanently personal installation will never need to be moved, shared, packaged, or reviewed. SMPL-X may be used locally as an anatomy comparison oracle if the owner accepts its terms; it should not cross the packaged application boundary.

### SOMA-X solves topology interoperability, not identity

[SOMA-X](https://github.com/NVlabs/SOMA-X) is Apache-2.0 core code that maps several identity sources, including Anny, MHR, SMPL family bodies, and garment measurements, to a canonical topology and rig. Its official repository documents Windows setup and warns through its dependency and asset paths that identity models retain separate terms.

SOMA-X becomes useful only after a body generator passes. It can reduce downstream topology permutations and keep the collider, skinning, and display registration stable. It cannot rescue an anatomically rejected source body, and its pose correctives are documented as beta. The lean first proof should prefer Anny's supported SOMA topology directly and avoid adding another runtime layer until evidence demands it.

## Cloth and arrangement findings

### Arrangement is the architectural failure to fix first

The current frozen shirt begins with body intersections, self-intersections, degenerate triangles, slivers, and excessive penetration. Those are pre-solver failures. Contact algorithms can prevent new intersections; they are not dry cleaners for corrupt initial geometry.

Patterna needs an explicit arrangement worker between exact 2D authoring and cloth solve:

1. Convert each source panel's ordered cubic boundary and material coordinates into a declared solver parameterization without changing source geometry.
2. Bind panel regions to named body-surface coordinates and offsets, not hard-coded world positions.
3. Generate a collision-free 3D starting surface with declared clearance and preserved grain direction.
4. Convert seams from exact source panel and edge IDs to exact solver parametric coordinates. Never infer seam ownership from spatial proximity.
5. Emit reversible source-to-derived maps and stable IDs.
6. Fail closed for unsupported holes, pockets, darts, non-disk topology, or panel archetypes rather than silently remeshing them into something easier.
7. Pass body intersection, self-intersection, clearance, degeneracy, sliver, inversion, strain, seam capture, and determinism gates before any solver launches.

For the current 14-panel shirt, a deterministic four-boundary-chain transfinite or Coons parameterization is plausible because each source panel is a simple disk. It remains a hypothesis. Panels with 15 or 21 source edges must be partitioned into four semantic boundary chains without losing curve, seam, or grain meaning. That proof is precisely what the no-install experiment tests.

### libuipc is the strongest bounded solver candidate, with one legal stop

[libuipc](https://github.com/spiriMirror/libuipc) is a modern GPU implementation of unified incremental potential contact. Its official repository documents Windows, C++ and Python APIs, finite-element deformables, cloth, penetration-free frictional contact, scene serialization, and multiple patches per cloth object. Its [geometry API](https://spirimirror.github.io/libuipc-doc/tutorial/geometry/) accepts native triangle meshes, which matches Patterna's current derived panel representation without a spline conversion. Its official constitution registry includes vertex-to-vertex, vertex-to-edge, and vertex-to-triangle stitch constraints, plus Baraff-Witkin strain limiting and discrete shell bending. The [release history](https://github.com/spiriMirror/libuipc/releases) shows active work on the stitch system and contact diagnostics. The [Windows instructions](https://spirimirror.github.io/libuipc-doc/build_install/windows/) require CUDA 12.4 or newer for source builds; the current wheel path documents Windows Python support with CUDA 12.8.

That is a better technical fit than BS-Cloth or STARK. Exact Patterna triangle IDs can survive into the scene, exact seam spans can become explicit inter-primitive stitch constraints, and the fitted body can be a static contact mesh. GPU contact is also closer to an interactive product path than an offline CPU research solver.

There is one immediate hard stop. The repository's root [license file](https://github.com/spiriMirror/libuipc/blob/main/LICENSE) says Apache-2.0, while its current [Python package metadata](https://github.com/spiriMirror/libuipc/blob/main/pyproject.toml) classifies the package as GPLv3. That may be stale metadata, a packaging mistake, or an intentional distinction. Guessing would be reckless. Obtain maintainer clarification that explicitly covers the C++ library, Python bindings, binary wheels, bundled dependencies, redistribution, and generated outputs before installation or integration.

The physics gap also remains. The documented [Neo-Hookean shell](https://spirimirror.github.io/libuipc-doc/specification/constitutions/neo_hookean_shell/) is isotropic. A strain-limiting Baraff-Witkin shell is present in the official registry, but the reviewed primary documentation does not prove Patterna's required calibrated warp, weft, bias, shear, and bending response. libuipc earns one exact-bundle spike only after the license is cleared. It does not earn a CLO-class claim from robust contact alone.

### BS-Cloth is a valuable physics oracle, not the first product adapter

[BS-Cloth](https://github.com/Simulation-Intelligence/BS-Cloth) is a SIGGRAPH 2026 B-spline finite-element cloth implementation with intersection-aware contact. Its repository is [Apache-2.0](https://github.com/Simulation-Intelligence/BS-Cloth/blob/main/LICENSE), documents a Visual Studio 2022 build, and supports disabling its renderer for headless use. Its [YAML configuration documentation](https://github.com/Simulation-Intelligence/BS-Cloth/blob/main/yaml-config-doc.md) exposes the concepts Patterna needs:

1. One B-spline surface per patch.
2. Material-space rest control coordinates.
3. Three-dimensional starting control coordinates.
4. Exact seam pairs in patch parameter coordinates.
5. A static triangle collider.
6. Deterministic configuration, step output, and conversion to meshes for external rendering.

This is a strong research match for garments, but its regular tensor-product patches introduce an unnecessary conversion boundary. Patterna already has exact arbitrary curved panels triangulated with stable source maps. Converting every panel to a four-sided spline patch would add approximation and topology risk before contact begins.

The gaps are serious. BS-Cloth's documented material is global and effectively isotropic: stretching stiffness, a shear-to-stretch ratio, bending stiffness, Poisson ratio, thickness, density, and friction. Patterna's acceptance contract requires calibrated warp, weft, bias, shear, and bending response. A solver that closes seams beautifully but cannot represent a woven fabric's directional behavior is not CLO-class. The repository is also young research code with no mature binary release process, and its prebuilt Windows numerical libraries require a full transitive license and provenance inventory.

BS-Cloth should remain a physics oracle for B-spline textile behavior and a fallback experiment only if a future garment class is natively spline-patch based. It should not be the first product adapter.

### STARK is the fallback general solver

[STARK](https://github.com/InteractiveComputerGraphics/stark) is an Apache-2.0 C++20 simulation library with robust intersection-aware frictional contact. Its official documentation covers [deformable surfaces](https://stark.physics-simulation.org/deformables.html), [exact attachment constraints](https://stark.physics-simulation.org/attachments.html), [input and output](https://stark.physics-simulation.org/io.html), and [source setup](https://stark.physics-simulation.org/setup.html). It accepts ordinary arrays, produces VTK output and solver logs, and exposes point-to-point, point-to-edge, and point-to-triangle attachments that can represent exact seams without proximity inference.

STARK is cleaner and more focused than SOFA for a bounded custom worker. It still provides a generic isotropic membrane and bending model, not a garment authoring system or calibrated anisotropic textile model. Patterna would own parameterization, arrangement, sewing semantics, fabric calibration, result mapping, and rendering. Its Windows source-build reproducibility also remains unproven. Use it only if libuipc's license or Windows runtime boundary fails and a small exact-bundle adapter can be demonstrated.

### SOFA is legally workable but architecturally expensive

[SOFA](https://github.com/sofa-framework/sofa) is a mature simulation framework with official [Windows downloads](https://www.sofa-framework.org/download/) and Python scene automation through [SofaPython3](https://sofapython3.readthedocs.io/en/latest/content/UsingThePlugin.html). The core is LGPL-2.1-or-later, while some projects, tutorials, and plugins use GPL or other terms. Every selected component would require its own inventory.

Its cloth examples are generic finite-element triangles and bending springs. SOFA does not supply Patterna's panel parameterization, body-aware arrangement, exact sewing graph, textile calibration, accepted output map, or presentation renderer. Adopting it would mean writing the garment engine inside a large plugin framework. That is the wrong trade for one maintainer unless a tiny source-to-solve experiment proves a unique capability that libuipc and STARK cannot provide.

### Blender remains the deterministic render and evidence worker

Blender provides a stable [background command-line mode](https://docs.blender.org/manual/en/3.0/advanced/command_line/arguments.html) and a versioned [Python API](https://docs.blender.org/api/current/) for scene construction, GLB export, and multi-camera rendering. Its cloth system uses a [spring-based model](https://docs.blender.org/manual/en/dev/physics/cloth/introduction.html), requires clean initial separation, and has cache behavior that must be explicitly controlled. Blender's [license](https://www.blender.org/about/license/) is GPL, while rendered output remains governed by the input assets.

Use Blender as an external executable in a fresh hash-bound working directory. Give it accepted meshes and a declarative scene manifest. It should generate the exact packaged GLB plus front, back, left, right, three-quarter, and detail evidence. Do not reuse a cloth cache across bundle IDs. Do not call Blender Cloth a final solver merely because it can produce one attractive frame after manual tuning.

### Other candidates fail earlier

1. [ARCSim's maintained research fork](https://github.com/kaist-silab/arcsim) expects paired flat and world meshes, near-coincident seam vertices, and a merge operation that changes topology. Its supported build route is not a reliable Windows product route. Proximity-based seam welding conflicts with Patterna's exact seam identity.
2. [ContourCraft](https://github.com/dolorousrtur/ContourCraft) is an MIT learned garment simulator, but its official [installation path](https://github.com/dolorousrtur/ContourCraft/blob/main/INSTALL.md) depends on a Linux-oriented CUDA research stack, external collision code, downloaded models and data, and SMPL-family inputs. Its learned rollout is not deterministic physical calibration from Patterna fabric parameters.
3. Generic IPC libraries remain useful contact research. They are collision foundations, not arrangement, sewing, fabric, avatar, or rendering systems. Adopting one directly means writing most of a garment solver, which is outside the sensible first move for this project.

## Recommended worker architecture

One immutable bundle ID should flow through versioned external workers as follows:

1. `revision-bundle.json` inside the immutable `patterna.revision-bundle/1.2` directory remains the only authoritative manifest and input boundary. Version 1.2 excludes derived arrangement and includes the global panel ownership map required to interpret seam links without inference.
2. `avatar-worker/anny-v0.6` consumes the exact body-control vector, pose, pinned code and data hashes, and produces a fitted body, canonical rig, display mesh, collision mesh, landmarks, and a signed provenance manifest.
3. `panel-adapter/exact-triangle-v1` converts exact source panels and seam identities into solver-neutral material-space triangles, collision-free 3D start positions, explicit vertex, edge, or triangle stitch constraints, collider input, and reversible source maps. It produces an arrangement report and stops unless every arrangement gate passes.
4. `cloth-worker/libuipc-<pinned-release>` consumes only the accepted arrangement plus calibrated fabric data after license clarification. It starts with a clean scene and emits solver logs, convergence data, solved vertices in source-map order, and source-map-preserving garment output. `cloth-worker/stark-<pinned-commit>` is the fallback against the same adapter contract.
5. `render-worker/blender-4.5.11` consumes only accepted body and garment outputs, constructs a deterministic scene, exports the packaged GLB, and renders the required views.
6. `acceptance-manifest.json` binds every input hash, worker version, executable hash, asset license ID, cache policy, output hash, and gate result. A missing or mismatched entry is a failure, not a warning.

Workers should communicate through files and manifests rather than linking Patternal against Blender, PyTorch, or solver internals. That keeps GPL process boundaries reviewable, makes crashes containable, and lets the Windows app display prior accepted results without loading heavyweight runtimes into its UI process.

## Best proof possible without installing dependencies

### Goal

Determine whether a solver-neutral exact-triangle adapter can preserve Patterna's current exact shirt document and produce a collision-free, seam-correct starting state. Do not test a solver yet.

### Inputs already available

1. The existing frozen 14-panel `RevisionBundle`, including cubic panel boundaries, material coordinates, grain, seam IDs and order, fabric parameters, and body-control vector.
2. The current accepted or best-known fitted collider and body landmarks.
3. The repository's existing Python tooling.
4. The already installed Blender 4.5.11 LTS runtime for visualization only.

### Procedure

1. Create a new ignored output directory named by bundle hash and adapter version. Never write into the source bundle.
2. Preserve each panel's existing exact material-space triangulation, source-panel ID, source-edge spans, vertex and triangle IDs, grain coordinates, and fabric region. Do not introduce a new remesher.
3. Construct 3D start positions from named body regions, surface coordinates, panel side, orientation, and declared clearance.
4. Map each stitch span in source order to explicit paired vertex, vertex-to-edge, or vertex-to-triangle constraints. Record interpolation coordinates and the reversible source map. Never select a partner by 3D proximity.
5. Emit a solver-neutral `arranged-panels.json`, triangle buffers, collider, stitch table, units, and material table. Also emit a declarative libuipc scene plan that names the documented mesh, shell, contact, and stitch concepts without importing or executing libuipc.
6. Reconstruct a derived triangular preview from those files and render the required views in a fresh Blender process.
7. Round-trip every derived vertex, triangle, boundary sample, and stitch constraint to source IDs. Measure boundary error, area and grain distortion, stitch ordering, interpolation error, and stable-ID preservation.
8. Run the existing arrangement gates: zero body intersections, zero self-intersections, at least 0.25 cm declared clearance where required, no degenerate, sliver, or inverted cells, bounded pre-solve strain, complete seam capture, and deterministic output hashes on two clean runs.

### Pass condition

The proof passes only if all 14 panels and all 38 stitches preserve exact semantics, every arrangement gate passes twice from clean state, no manual vertex editing occurs, and the generated triangle and constraint files can map directly to both libuipc and STARK concepts without source mutation.

### Time box and consequence

Time-box this to four engineering hours. If the adapter cannot preserve exact triangles, material coordinates, stitches, and collision-free arrangement, stop and redesign arrangement before touching a solver. Do not install or compile libuipc first. The arrangement boundary is the risky assumption; proving a compiler can compile would answer the easier and less useful question.

If it passes, first resolve libuipc's license conflict. Then request explicit dependency approval, pin a release, inventory every transitive code and binary license, build one Windows runtime in a versioned directory, and run one frozen-shirt solve with parameters selected before viewing the result. If the license cannot be cleared, perform the same bounded solve with STARK.

## Stop conditions

### Avatar

1. Stop if Anny attempts any implicit network download or introduces a restricted model into the runtime.
2. Stop if the complete Patterna control vector, compound controls, independent left and right values, pose, rig, collider, and display mesh cannot be regenerated from one exact state.
3. Stop if collider and display surfaces drift out of registration under extreme accepted controls.
4. Stop if six-view anatomy remains uncanny or structurally implausible after one bounded integration pass. Do not spend another long cycle polishing a rejected base topology.
5. Stop if any character, texture, rig, morph, or corrective lacks a redistributable license and recorded source hash.

### Panel adapter and arrangement

1. Stop if a conversion changes source geometry, seam order, grain, material coordinates, topology, or IDs without an explicit reversible map and tolerance report.
2. Stop if any supported panel cannot be parameterized within declared geometric and material tolerances.
3. Stop if holes, pockets, darts, or non-disk panels require a silent topology simplification.
4. Stop before simulation if any existing arrangement gate fails.
5. Stop if a result depends on manually moving vertices or choosing parameters after viewing the output.

### libuipc

1. Stop before installation until the Apache-2.0 root license and GPLv3 package metadata conflict is resolved by the maintainers in writing.
2. Stop if CUDA, wheel, bundled library, or transitive dependency provenance and redistribution terms cannot be fully inventoried.
3. Stop if a clean Windows build or pinned wheel and run cannot be reproduced in a versioned runtime.
4. Stop if exact stitches require proximity inference, topology welding, or source-ID loss.
5. Stop if calibrated warp, weft, bias, shear, and bending response would require building most of a private textile solver rather than a bounded constitution.
6. Stop if more than one predeclared solve configuration is needed to obtain basic seam closure and contact. Repeated visual tuning would be another solver churn loop.

### BS-Cloth

1. Stop if an exact panel must be approximated as a four-sided spline patch without a bounded reversible error report.
2. Stop if bundled SuiteSparse, LAPACK, OpenBLAS, TBB, or other binary provenance and licenses cannot be fully inventoried.
3. Stop if its global material model cannot represent the required fabric calibration.

### STARK or SOFA fallback

1. Stop if Windows builds are not deterministic and automatable.
2. Stop if exact source seams cannot map to explicit constraints.
3. Stop if anisotropic fabric requires building most of a new solver.
4. Stop if the adapter grows beyond one exact bundle surface, seam, collider, solve, and reversible output map before it produces acceptance evidence.

### Rendering and packaging

1. Stop if a cache, bake, or scene from another bundle ID can be reused.
2. Stop if the displayed packaged GLB is not hash-identical to the accepted render input.
3. Stop if any required view is missing, clipped, stale, or rendered from a different body, garment, pose, or material state.

## Final recommendation

Proceed with the no-install solver-neutral exact-triangle arrangement dry run. In parallel only at the planning level, request clarification of libuipc's license metadata and define an Anny v0.6 bakeoff that uses the clean CC0 and Apache-2.0 path and forbids downloads. Do not compile a new solver, adopt SMPL-X, revive MB-Lab, or add SOFA yet.

This recommendation is intentionally less glamorous than choosing a shiny new physics library. The evidence says the first broken boundary is panel representation and arrangement. Prove that exact boundary first. If it passes and its license is clarified, libuipc is the strongest current bounded solver candidate. If licensing fails, STARK receives the same accepted triangles and constraints. If arrangement fails, neither solver should be installed; the failure will be precise enough to fix the missing layer without another month of anatomically dubious mannequins and exploding shirts.

## Addendum, 2026-08-29: what the editable preview body can actually represent

Status: measurement, not a decision. Nothing here has been adopted.

The audit above chose candidates for the packaged render and the cloth solve. It did not ask a narrower question that decides how the application feels to use: of the dimensions a user can type into the measurement inspector, how many can the interactive 3D preview move?

`tools/audit_preview_dimension_coverage.py` answers that from the declarations rather than from a screenshot, and writes `artifacts/preview-coverage/preview-dimension-coverage.json`. The application exposes 151 editable body dimensions plus 6 primary sliders. The morph basis the preview ships with holds 11 parameters covering 13 of those keys.

| Group | Represented | Total |
| --- | --- | --- |
| Head, face and neck | 0 | 16 |
| Shoulders, chest, bust and back | 3 | 22 |
| Waist, abdomen, pelvis and seat | 4 | 21 |
| Posture, alignment and surface shape | 0 | 20 |
| Left arm and hand | 1 | 16 |
| Right arm and hand | 1 | 16 |
| Left leg and foot | 0 | 17 |
| Right leg and foot | 0 | 17 |
| Primary sliders | 4 | 6 |

The application already says so on screen. Moving any of the other 138 switches the readout to "3D unsupported for this revision", and after the 2026-08-29 binding fix it says so within a few seconds rather than one edit late. The gap is a capability limit that is reported honestly, not a silent failure.

### Why the limit is structural

The preview body is fitted by `tools/fit_mhr_local_profile.py`, which deforms horizontal cross-sections of the MHR body directly: `apply_torso_station` takes a station's target circumference and depth and moves vertices near that height plane. That method can express a torso girth or a torso depth and nothing else. There is no construction in it that could move a jaw width, a palm circumference, a knee alignment or a thoracic curve, so the 11 parameters are not an arbitrary stopping point; they are what the method can reach.

### What is already installed that would not have that limit

MPFB2 is installed, along with the Blender 4.5.11 LTS runtime it needs, and it already produced the body used for the packaged cloth solve. Its Patterna control layer in `tools/mpfb_morph_controls.py` maps 93 of the same measurement keys onto named MPFB targets, covering the legs, feet, hands, head and the posture curves that the current preview cannot reach at all. Confirm the count with:

```bash
python -c "import sys; sys.path.insert(0,'.'); from tools.mpfb_morph_controls import mapped_measurement_keys; print(len(mapped_measurement_keys()))"
```

So the application currently runs two different bodies: an MPFB body for the packaged solve, and an MHR body with a 13-dimension morph basis for the interactive preview. Consolidating on the MPFB body would raise interactive coverage from 13 to 93 and would remove that split.

### What was built, and what shipped

The consolidation was attempted rather than left as a proposal, and it is in.

`tools/generate_mpfb_morph_basis.py` builds the basis. It fits the MPFB body to the default profile once, then moves each of the 85 controls to its own limits and records how the body moved, storing only the vertices that actually moved: a palm width moves a few hundred of the body's 13,380, and a dense basis would cost 30 MB to say almost nothing. The result is 2.94 MB, covers 90 measurement keys, and every control moves the body. The tool re-measures the body after every probe and refuses to write a basis if it has not returned to rest, which is what catches probes contaminating each other.

The viewport reads that format. `buildSparseMorphBasis` verifies the basis against its manifest hash and expands one delta per source vertex to every render vertex that came from it, because a vertex on a UV seam exists several times over and moving only the first copy would tear the body along its seams. `tools/test_avatar_sparse_morph_basis.mjs` proves that expansion, the axis mapping and the weighting against a body small enough to check by hand, reading the functions out of `avatar3d.html` so it tests what ships.

`tools/package_mpfb_morph_basis.py` binds a basis to the application. It re-anchors each parameter to the measurement the application ships as its default, which matters because 29 of the 85 controls were authored around the MakeHuman baseline body and disagree with the application, `upperBustFullness` resting at 50 against a shipped 85 and `deltoidProminence` at 50 against a shipped 0. Packaged as authored, the preview believes it is far from rest before anything is edited and deforms the body on load; the visible result was the bust pushed through the packaged shirt.

The interactive preview now moves 97 of the 151 editable dimensions, up from 13. Head, face and neck went from 0 of 16 to 14; each leg and foot from 0 of 17 to 11; each arm and hand from 1 of 16 to 13. Moving a thigh circumference reshapes the thighs, and the figure stays intact, with the eyes, brows, lashes and hair following the head rather than being left behind by it.

### How the body problem was dissolved rather than solved

A delta is a difference from the body it was measured on, and it is added to the body that ships, so those normally have to be the same body. They are not: `tools/generate_mpfb_avatar.py` run today produces a display body 6.94 cm from the packaged `Production/Avatar/body.obj`, because the packaged avatar predates the current pipeline. Regenerating the packaged body would have meant re-solving the garment on it and re-running the six-view acceptance.

The way past it was to change what is measured. MPFB targets are additive vertex offsets, so the displacement a control produces is largely a property of the target rather than of the body underneath it. Measuring the MPFB target contribution alone, instead of the application's whole response, yields deltas that can be carried onto a different body of the same topology.

That is measured rather than asserted. Every run displaces one control on the unfitted body and again after the ruler fit has moved the body 8.4 cm, and compares. They agree to 0.061 cm, a coupling of 0.723%, and the tool refuses to write a basis whose coupling exceeds a declared tolerance. Carried onto a body 6.94 cm away, that is about half a millimetre of error in a preview that already declares itself approximate. The report records `deltaKind`, the measured coupling and the body movement it was measured across, and the packaging step only waives the body-identity check for a basis that declares itself this kind.

`--full-response-deltas` still measures the application's whole response, local deformations and surface constraints included. Those deltas describe more and are only valid against the exact body they were measured on, and the packaging step enforces that.

### What is still open

Two things, and both are about the bodies rather than the basis.

The application is still using three different human bodies. The interactive preview and the packaged production assets are now both the MPFB body, which is the consolidation this audit asked for. But `SimulationPipeline.cs` still builds a third for a fresh simulation: it runs `generate_charmorph_avatar.py` and requires, in its own words, a "measurement-fitted Antonia display GLB", with the MPFB path left inside `RunLegacyWarpAsync`. Pressing Simulate would therefore produce a revision on a body neither of the other two uses.

The packaged assets still cannot be rebuilt from this repository. Two of the three stages now can: `tools/prepare_style3d_body.py` recovers the missing Z-up to Y-up conversion and reproduces the packaged collision body exactly, and `tools/build_style3d_source.py` reproduces the packaged garment topology exactly, 133,870 vertices, 262,814 faces and 1,974 seam links. The Newton Style3D solve on a freshly built body is accepted, reaching static equilibrium at frame 878 with zero body collisions, zero self intersections, zero seam separation and zero high-strain edges, so the physics is reproducible. What is missing is the promotion stage, which needs an accepted simulation job binding the solved surface to a compiled render mesh, and that assembly happens inside the application's Simulate flow.
