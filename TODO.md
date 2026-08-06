# Patternal product goal and v1.0 roadmap

Last reviewed: 2026-08-06

## North star

Patterna is a Windows-first clothing design and pattern-making application. Its target is the complete working loop of CLO, then a clearer and more body-specific workflow:

1. Draft or import production-capable 2D patterns.
2. Sew and arrange those pieces around a realistic, measurement-driven avatar.
3. Simulate physically meaningful fabric drape, fit, contact, layering, and motion.
4. Edit any body measurement or pattern dimension and see both 2D and 3D update without losing manual work.
5. Produce printable patterns, graded sizes, material layouts, renders, and exchange files.

The product is not complete because it looks like a garment-design application. It is complete only when the pattern, body, sewing, material, and simulation data form one editable and validated model.

## Non-negotiable v1.0 proof

- [ ] A user can create a garment from an empty project using interactive 2D drafting tools, not only a built-in sample.
- [ ] Points, straight segments, Bezier curves, internal lines, darts, pleats, fullness, seam allowance, notches, grainlines, labels, and measurements are directly editable.
- [ ] Undo, redo, snapping, numeric entry, selection, multi-selection, transform, mirror, linked editing, split, join, offset, trace, and layer controls work predictably.
- [ ] Segment sewing, free sewing, seam editing, sewing direction, tension, folds, pins, tacks, and garment layer order are editable in 2D and inspectable in 3D.
- [ ] A production-quality female avatar is the default, while body shape and presentation remain user-controlled.
- [ ] The avatar is driven by a detailed measurement profile with at least the current 151 mapped measurements, independent left and right values, arbitrary custom landmarks, and durable manual overrides.
- [ ] Photo estimation can initialize body shape and appearance locally or with explicit consent, but every estimate remains editable and visibly marked as estimated.
- [ ] The assembled avatar has realistic skin, face, eyes, teeth, hair, hands, feet, posture, and animation, not a preview mesh or disconnected geometric proxy.
- [ ] The garment is generated from the same pattern boundaries and seam graph shown in 2D.
- [ ] Interactive cloth settles under gravity with warp, weft, bias, shear, bend, density, damping, thickness, friction, collision, and self-collision behavior.
- [ ] Collision and layer order remain stable from front, side, rear, and oblique views, including animated poses.
- [ ] Separate simulation and render meshes provide stable physics plus realistic thickness, seams, topstitching, trims, and material detail.
- [ ] Pressure, strain, stress, ease, and collision diagnostics identify the exact pattern area causing a fit problem.
- [ ] Multiple garments and layers can be dressed, simulated, frozen, hidden, reordered, and removed.
- [ ] Fabric presets are backed by calibrated physical test data, with user-defined fabrics and uncertainty shown explicitly.
- [ ] Size grading, points of measure, grading review, print layout, fabric yield, tiled printing, and production export are functional.
- [ ] Projects round-trip without losing measurements, manual origins, pattern geometry, seams, fabrics, trims, avatar state, or simulation settings.
- [ ] A fresh install can complete the core workflow without Unreal Editor or developer tooling visible to the user.

## Current capability ledger

### Working and verified in the WinUI application

- [x] Native Windows drafting shell with responsive pieces, canvas, viewport, and inspector regions.
- [ ] Complete the isolated packaged UI gate in the persistent Hyper-V guest. The 2026-08-06 host audit and repository implementation establish a no-host-input workflow with recipe-built AppX identity, PowerShell Direct transfer, guest-local UI Automation, toggle and slider restoration, assembly Undo verification, six 3D camera captures, UI trees, and JSON evidence. The current 88-file guest payload builds and hash-round-trips, but no guest has been provisioned because an official Windows ISO and an elevated one-time Hyper-V bootstrap are still required. This is infrastructure readiness, not a passing packaged UI claim. Follow `docs/isolated-windows-ui-testing.md`.
- [ ] Recheck the repaired packaged camera presets and measured-garment readout with GUI control returned. The 2026-08-02 live audit proved that Front and Rear were reversed, front-oblique aimed behind the avatar, and the readout trusted stale legacy body metadata. Source fixes and headless regressions now bind anatomical camera yaw, regenerated body identity, and chest/waist/hem readout to current geometry, but the required post-fix packaged visual pass is intentionally deferred while the user controls the desktop.
- [ ] Recheck assembly history and display-only avatar availability in the packaged app. The live audit found that Undo restored seam direction in the model before the selected ToggleSwitch visibly refreshed, and the fitted-bra toggle gave no feedback after revision-specific display assets became stale. Source now commits assembly state again after the current WinUI input event and disables the bra toggle with an explicit matching-simulation explanation whenever the renderer has no fitted asset. Headless contracts pass; post-fix packaged interaction remains required.
- [x] Versioned garment document shared by 2D rendering, snapshots, SVG export, and the Unreal bridge.
- [x] Replace the rejected cropped and waistband-extended shirt blocks with a measurement-shaped production block that joins GarmentCode's mirrored source halves into one uninterrupted front torso and one uninterrupted back torso before meshing. The accepted garment has 14 panels, 34 construction seams, four sleeve panels, four sewn collar panels, and four sewn cuff panels. Promotion requires a completed collision-driven pose, static equilibrium, 0 body intersections, 0 self intersections, and all three structural-strain gates.
- [x] Prove the complete 151-value route through the avatar-profile bridge, MPFB, prepared watertight collider, GarmentCode, three-stage Newton Style3D CUDA solve, compiler-refined render OBJ, and hash-bound promotion. Revision `0eaa4ca2109efd3540a96b516756186dbe9d5fe0eb9d021be3e5f7e66c7c7e98` reaches equilibrium in 120 frames with 20 substeps, exact seam closure, 0 body collisions, 0 self collisions, 2.817 percent 95th-percentile strain, 11.060 percent 99.9th-percentile strain, and 14.069 percent 99.99th-percentile strain.
- [x] Replace the visibly broken startup garment with a body-family MakeHuman clothing proxy fitted to the exact 167 cm, 92/71/99 cm default body. The packaged avatar uses UV skin, eyes, teeth, brows, lashes, and fitted hair. The fit has 0 final inside-body vertices, at least 0.982 cm clearance, no source-avatar projection spikes, preserved display UVs, and deterministic front, oblique, side, rear, opposite-side, and opposite-oblique proof renders.
- [ ] Refine revision-specific continuous shirts and detailed render construction until neckline, shoulder balance, sleeve junctions, hem, body ease, pattern-space PBR detail, and all packaged multi-angle visual gates pass at CLO-class presentation quality. The clean startup baseline is not a substitute for simulated output from the editable pattern.
- [x] Promote the Newton Style3D backend through the full acceptance contract. The accepted 131,910-particle physical surface drives a compiler-refined 526,636-surface-vertex render mesh with exact pattern UVs and construction lines. Promotion verifies solver, collider, source body, display body, MPFB fit, compiler output, optional bra offset, and six-view visual evidence as one identity chain.
- [x] Replace the one-stage posed-body drape and rigid garment teleport with a two-stage rest equilibrium plus collision-driven body animation. Every live job now preserves the accepted rest cloth, original pattern rest lengths, and box-mesh strain reference while the body moves through 180 smooth kinematic frames into a 12-degree lowered-arm A-pose. Full production proof revision `34a19a674a3a58dbec8d604160f2e494d5d62ee35a6a3d0b568b6d79d83fdff7` reaches equilibrium in 375 frames with 0 body intersections, 0 self intersections, 39.990 percent peak strain, 7.895 percent 95th-percentile strain, and 25.214 percent 99.9th-percentile strain.
- [ ] Generalize collision-driven body animation beyond the proven A-pose. Every interactive avatar pose must have an explicit trajectory, continuous collision handling, and its own contact and strain acceptance proof.
- [x] Five-piece wrap-dress sample with named curves, eight cloth panels, eleven permanent construction seams, and three explicit temporary closure relationships. The overlapping center-front edges correctly remain free.
- [x] Seam allowance, grainline, notch display, piece selection, fit-to-view, and SVG export.
- [x] Stable piece-ID selection, draggable boundary anchors and Bézier controls, exact point and segment entry, and shared geometry undo and redo.
- [x] Native rectangle, ellipse, numeric polygon, and direct canvas polygon piece creation plus exact internal-line and boundary-anchored dart create, edit, and delete workflows, all with stable identities, centimeter snapping, numeric input, live closure preview, undo, redo, snapshot persistence, and deterministic command replay. Darts can remain guide-only, compile an equal-leg mouth on an unsewn free edge into two physical boundary legs and a same-panel closure stitch, or divide a matched one-edge seam around already-drafted intake for topology, simulation, and GarmentCode export.
- [x] Measurement-driven asymmetric bust shaping for the production shirt. Chest, underbust, independent left and right bust projection, independent bust height, and bust-point separation estimate left and right intake. Designers can then override either intake, separation, heights, projections, tip offset, side mouth drop, shoulder mouth distance, and shoulder share numerically. The drafter can place the fullness in real side-seam darts, rotate all of it to real shoulder darts, or distribute each side's total across both positions. It generates equal-leg physical cut legs, divides every matched external seam around the removed mouths, and preserves the complete distribution profile through snapshots, revision hashing, and GarmentCode export/import.
- [x] Add an editable underarm-junction extension to the shirt construction profile. The value moves the four torso underarm anchors symmetrically, survives validation and GarmentCode round trips, participates in revision identity, is available in WinUI and proof automation, and is applied exactly once during width balancing.
- [ ] Promote cup-aware bust construction with compound-seam correspondence, waist darts, princess seams, and dartless knit rules. The prototype reproduces the editable armscye and underbust in final flat geometry and binds the vertical stations to fitted-avatar rulers. Candidate v25 is rejected: it did not reach equilibrium, ended with 5 body intersections and 13 self-intersections, left 0.536 cm maximum seam separation, reached 15.613 percent 95th-percentile strain, and remained visibly folded into a horizontal shelf below the bust. Its v23 source artifact also predates the corrected positive-depth anatomical-front contract. The solver adapter now classifies shoulders from panel ownership and material height, keeps every lower side segment in the side-seam phase, attaches sleeve caps last, gives paired shoulders shared target heights, and supports topology-identical radial body expansion. Restart by building a fresh source from the corrected placement code and proving front/back depth bounds plus zero initial intersections before another expensive solve. Promotion still requires zero final intersections, static equilibrium, seam and strain gates, a real under-bust return, clean sleeves and back, and an accepted six-view silhouette.
- [x] Direct piece-property editing for name, physical seam allowance, cut quantity, mirrored and cut-on-fold instructions, and exact grainline endpoints and locking.
- [x] Deterministic physical-scale SVG export that packs centimeter geometry in millimeters and preserves seam-allowance zones, internal paths, darts, notches, grainlines, cutting instructions, and measurement metadata.
- [x] Assembly mode with source-edge seam overlays, closure overlays, seam direction editing, closure state editing, local persistence, and shared undo and redo.
- [x] 151 mapped anatomical measurements at 0.1 cm precision, with hard MPFB ruler constraints, named morph controls, and bounded local deformation controls for posture, asymmetry, arcs, rises, slopes, landmarks, hands, and feet.
- [x] Independent left and right values, custom measurements, linked estimates, and persistent manual override origin.
- [x] Fabric mass, stretch, bend, shear, friction, thickness, and damping data in the bridge model.
- [x] Local snapshots and a deterministic `patterna.unreal-bridge/1.0` document.
- [x] Remove the browser toy-cloth solver, procedural body deformation, and fake facial overlays from the accepted production state.
- [x] Load the exact MPFB display body, exact prepared collision body, and accepted Style3D startup garment in the embedded WinUI 3D surface, with orbit, zoom, fixed camera views, revision gating, and a production-image fallback. The bundled evidence binds body, cloth, seams, UVs, contacts, equilibrium, strain, compiler refinement, and six rendered views.
- [x] Keep supported bust shape in the body and collider while exposing the fitted bra as a visible display-only toggle. The `Show fitted support bra` option defaults on, updates only the presentation layer, saves and restores with the local project snapshot, and resets on new projects. Cap its body offset at 0.10 mm and prove that hiding it does not alter body or collision identity.
- [x] Split the solver collider from the visual avatar while keeping one exact evaluated body shape. Package a UV-mapped skin body plus fitted eyes, teeth, brows, lashes, and hair for the baseline and every new simulation revision. Reject stale request races and hide old cloth and evidence immediately after a source edit.
- [x] Replace the geometry-only Blender garment handoff with a compiler-native OBJ from the exact accepted welded surface. Preserve 182,316 face-varying pattern UV corners, 34 real construction-seam strips, 10 finished open edges, a hashed renderer artifact, real GarmentCode weave sampling, fabric-specific tangent-space micro-normal relief, and a cache gate that rejects legacy geometry-only render meshes.
- [x] Replace midpoint-only display subdivision with a dedicated high-quality render-surface stage. The compiler now applies boundary-constrained Taubin fairing followed by Loop subdivision, freezes 207 finished-boundary vertices, preserves face-varying pattern UVs, records displacement and topology evidence, and rejects promotion unless the exact refined OBJ has zero independent body-edge crossings. The relaxed production surface moves base vertices by 0.116 cm on average and 0.451 cm at maximum while retaining the accepted Warp simulation as the unmodified physics authority.
- [x] Remove source-checkout discovery from the simulation architecture. The WinUI command and headless runner now share an install-owned, relative-path, SHA-256-gated runtime manifest, exact job-owned bridge snapshot, resumable Style3D stages, compiler handoff, and six-view product-proof validator. Installed-runtime revision `10961a44d0bd788ea7ea873ff4de5fbf43fa3eb97b34aa5ffd83d804c54fee07` reopens as accepted with zero body or self collisions and exact seam closure.
- [ ] Validate accepted non-default revisions through the registered packaged Simulate button and final embedded display. The same-code installed-runtime runner and its exact six-view textured-avatar proof pass end to end without a source checkout, MetaHuman, or Unreal import. A live registered-AppX click and viewport inspection remain separate because computer control was not authorized for this verification pass.
- [x] Preserve untouched GarmentCode source byte-for-byte and retain panel coordinate origins, semantic labels, circular curve definitions, and stable seam identity when edited source must be regenerated.
- [x] Replace fabricated fit-quality labels with revision-specific peak strain, 95th-percentile strain, final body and self intersection counts, equilibrium frames, acceptance limits, and CUDA device provenance from the accepted Warp report.
- [ ] Embed or stream the interactive Unreal renderer inside the WinUI 3D surface without exposing developer tooling.

### Working foundations in Unreal

- [x] Unreal Engine 5.8 project with MetaHuman Character and Chaos Cloth plugins enabled.
- [x] Enable Chaos Outfit Asset and save a resizable outfit proof with the female MetaHuman body and face as source body parts and 2,000 resizing interpolation points.
- [x] Saved female source MetaHuman plus a verified source-asset backup.
- [x] Assembled MetaHuman runtime Blueprint with skin, eyes, teeth, body, face, and groom assets.
- [x] Runtime validation actor and camera intended for multi-angle drape inspection.
- [x] Deterministic bridge-to-USD garment generator and bridge contract tests.
- [x] Apply all 30 available MetaHuman body constraints, rebuild the assembly, explicitly save generated packages, and hash the saved body asset.
- [x] Regenerate body DNA after constraint edits and prove a 71.21 cm live runtime waist against the requested 71 cm value.
- [x] Derive garment support placement from the live body profile without changing the user measurement or two-dimensional pattern rest size.
- [x] Preserve the editable skirt panel's cubic balanced hem in generated three-dimensional rest geometry and regression-check its center and side lengths.
- [ ] Complete live cross-section verification for the rebuilt measured body and quantify residual error against the Patterna profile.
- [x] Replace the old skirt proof asset with a measured-body Chaos Cloth asset generated from Patterna dimensions and named seams.
- [x] Build a transient garment collision asset from seven live waist and seat cross-sections instead of using the MetaHuman's oversized circular lower-torso capsules.
- [x] Retain angular outer-surface samples in the live body profile and use them for the skirt's held waistband and upper dressing rows.
- [x] Validate 23 torso-filtered live body-surface sections from 95 to 139 cm and use them for measured full-garment torso and skirt arrangement.
- [ ] Extend verified surface coverage above 139 cm or use the assembled MetaHuman collision surface directly for neckline and neck dressing.
- [x] Reject unsewn panels, excessive seam mismatch, malformed structured remeshes, open arranged seams, broad initial strain, and measured-torso penetration before exporting a full garment.
- [x] Export the eight-panel, eleven-seam wrap dress to deterministic OpenUSD with separate simulation and render patterns, 272 explicit stitches, a declared Unreal-to-OpenUSD handedness transform, and a hashed manifest.
- [x] Capture repeatable front, side, rear, and oblique static acceptance views without desktop camera automation.
- [x] Generate saved pattern-UV cotton-poplin color and normal textures and capture a macro material acceptance view.
- [x] Preserve higher-detail render LODs after Dataflow regeneration and add render-only waistband, hem, and side-seam construction with thread tinting.
- [x] Add an isolated eight-panel GarmentCode shirt lane driven by the exact posed MetaHuman surface, a watertight body-specific collider, explicit stitch topology, NVIDIA Warp pre-fitting, normalized collision gates, and an explicit rejected-result boundary.
- [x] Replace the adaptive shirt's rejected 29.241 percent 95th-percentile strain and 540 body intersections with an accepted equilibrium at 5.314 percent 95th-percentile strain and zero body or self collisions.
- [ ] Replace the current pre-fit contact-rate gate with exact signed-distance triangle penetration and continuous collision checks.
- [x] Build the customized GarmentCode Warp fork with CUDA support, prove `cuda:0` on the RTX 4090 in every report, and retain the compiled CPU path as a deterministic fallback.
- [ ] Replace the experimental Chaos seam handoff that opens underarm discontinuities. The product preview now defaults to the continuous Warp equilibrium and requires `-PatternaEnableChaosRefinement` to expose the rejected handoff.
- [ ] Replace the rejected generic render proxy with seam-aware render deformation that stays continuous across sewn boundaries. The simulation-surface diagnostic is visibly smoother but is not the final detailed garment renderer.
- [ ] Verify Unreal 5.8 non-destructive CLO/OpenUSD cloth round-trip and preserve Patterna identifiers through import.

### Major missing product capabilities

- [ ] Full interactive 2D CAD geometry editing beyond the current boundary-point and Bézier-handle slice.
- [ ] Pattern construction formulas and parametric blocks/slopers.
- [ ] Full seam graph editing beyond the working user-created free-sewing, relationship inspection, direction, and closure-state slice.
- [ ] Pleats, fullness, fold manipulation, elastic, shirring, gathers, and layer relationships. Exact boundary-anchored dart creation is working, including physical cut-and-sew darts on unsewn free edges and strict one-edge seam-integrated darts when the source block already contains matched intake. Compound-seam darts, automatic intake generation, shoulder and neckline variants, and dart rotation remain.
- [ ] Accurate arbitrary-pattern triangulation and remeshing with topology acceptance tests.
- [ ] Multiple garment types, modular blocks, trims, buttons, buttonholes, zippers, binding, piping, puckering, and topstitching.
- [ ] Grading, size sets, points of measure, nesting, print layout, and production exports.
- [ ] Photo-to-body estimation and texture generation with consent, privacy, confidence, and calibration controls.
- [ ] Calibrated fabric library and a physical swatch-test workflow.
- [ ] Production rendering, colorways, UV editing, graphics, animation, and review tools.
- [ ] Plugin or scripting API plus extensible import and export adapters.

## Implementation order

### P0: One truthful end-to-end garment

- [x] Replace the rejected production route with one exact MPFB body, a GarmentCode-compatible pattern contract, CUDA Warp equilibrium, compiler quality gates, and direct embedded rendering. Keep Unreal diagnostic-only. See `docs/architecture-v2.md`.
- [x] Replace the rejected circumference-shell garment arranger with separate collision-free panel staging, strain-free back-panel arcs, fully dynamic particles, and simulation-driven sewing.
- [x] Represent wrap tack, waist pin, and tie buckle closure constraints separately from permanent construction seams through the document, compiler, Unreal package, and 2D assembly editor.
- [ ] Add user-authored tie, knot, button, zipper, hook, buckle, and pin creation tools plus closure-specific behavior.
- [ ] Add triangle-level body penetration, panel self-intersection, orientation, seam-twist, closure, and silhouette acceptance tests. Seam direction is now gated; the other geometric gates remain incomplete.
- [x] Expand the MPFB fitter beyond the 20 hard-gated body rulers to side-specific surface depth, projection, posture, hands, feet, head, and face controls. The fit report separates ruler, named-target, and local-deformation evidence, reports unmapped custom inputs, and compensates local shape changes back through the hard ruler gates.
- [x] Generate one skirt from authoritative 2D panels and named seam pairs.
- [x] Import separate simulation and render meshes into Chaos Cloth.
- [x] Use the live assembled body for pose and collision.
- [ ] Prove drape, seam closure, wrap closure, waist fit, thickness, and no penetration through a full camera turn. V8 contains three closure constraints and 275 combined stitches, but the current capture is rejected for bodice and waist discontinuity plus 40.7 percent peak initial edge strain.
- [ ] Pass the adaptive shirt production visual gate for a newly edited revision. The startup MakeHuman proxy now passes a clean six-angle appearance gate, but it does not own the editable GarmentCode pattern or physics state. The next accepted candidate must come from the current 14-panel pattern, preserve compiler-native pattern UVs and real seam and finished-edge overlays, and pass the same live packaged multi-angle review after Warp equilibrium.
- [ ] Replace the rigid packaged shirt with the validated Blender cloth result only after the Blender report, exact CUDA body diagnostic, exact position-welded self-intersection diagnostic, authored-rest-length strain check, and side-by-side six-view visual review all accept the same hashes. Do not relabel a Warp result as Blender cloth or package a moving candidate.
- [x] Render the exact packaged display avatar, body texture, eyes, teeth, brows, lashes, hair, accepted garment, compiler UVs, and fabric image through a deterministic six-view Blender proof. Hash every input and render, validate body-to-garment registration in physical units, and reject stale or incomplete evidence.
- [x] Replace absolute-height-only product registration with a shared body-relative gate. Require the avatar floor datum plus shirt hem, neckline, and span fractions, and regression-test the exact 20.66 cm MPFB display offset that previously produced a displaced mannequin and garment.
- [x] Normalize every display-avatar asset to the zero-based collision-body floor datum. Revision manifests now record the MPFB source floor offset, older manifests derive it from the body, both app and proof renderers apply it, and the refreshed six-view proof rejects stale hashes.
- [x] Preserve authoritative GarmentCode source placement for every imported garment with complete panel transforms. The body-aware sewn-shell is now a fallback only for generated garments without complete source placement. The exact diagnostic found 1,820 body and 1,658 self-intersections in the analytical shell versus 122 and 307 in the authored placement. The custom asymmetric bust-dart garment then reached accepted equilibrium with zero body intersections, zero self-intersections, 38.51 percent peak strain, 5.82 percent 95th-percentile strain, and 21.31 percent 99.9th-percentile strain.
- [x] Gate the product render handoff separately from simulation. Compare midpoint, Loop-only, and boundary-constrained fairing candidates through the same six cameras, preserve finished edges exactly, cap render displacement, and require zero body crossings before packaging.
- [x] Add body-width-aware torso-region isolation and multi-height width, depth, centering, and garment-length scoring to candidate search. A physics-accepted shirt no longer counts as a search winner when its silhouette exceeds the visual-fit threshold.
- [x] Expand the shirt generator from the raw eight-panel block to a finished 14-panel continuous construction with uninterrupted full-front and full-back torso blocks, sewn neck and sleeve bands, 34 sewing relationships, independent chest, waist, and hip ease, and explicit finished-construction rejection in candidate search.
- [x] Add sleeve-hang scoring and an independent sleeve gate; the rejected production shirt measures roughly 6.3 cm upward at both sleeve ends instead of the 10 cm downward target and can no longer pass on torso metrics alone.
- [ ] Re-run the same proof after changing waist, hip, and skirt dimensions manually.

### P1: Interactive pattern editor

- [x] Add piece and boundary-point selection with stable piece, edge, and point identities.
- [x] Add draggable boundary anchors and Bézier controls with 0.1 cm snapping and exact X and Y coordinate entry.
- [x] Add exact length and angle entry for boundary segments through their selected endpoints.
- [x] Add replayable line-to-cubic and cubic-to-line boundary conversion with generated Bezier controls, stable edge identity, sewing-reference preservation, undo, redo, and snapshot persistence.
- [x] Add editable pattern-piece creation from the native 2D command surface with stable piece and panel identities, snapshot persistence, undo, redo, and deterministic JSON round trips.
- [x] Add replayable native piece settings for physical seam allowance, cutting instructions, and exact grainline geometry without conflating construction metadata with geometry scale.
- [x] Add free sewing between user-marked boundary edges with stable seam identity, snapshot persistence, undo, redo, topology validation, and deterministic JSON round trips.
- [x] Add replayable exact line and Bezier segment splitting with sewn-partner synchronization, reference rewriting, undo and redo, snapshot persistence, and compound-seam GarmentCode export.
- [x] Add first-class internal paths, boundary-anchored notches, boundary-anchored darts, and explicit grainlines to the garment document, validation, structural editing, 2D rendering, snapshots, and GarmentCode round trips. Straight internal paths and darts support native exact-input creation, editing, and deletion. A physical-dart compiler now replaces a validated free-edge mouth with two equal sewn legs, preserves editable source parameters separately, and round-trips the compiled topology without applying the cut twice.
- [x] Preserve manual point offsets across measurement-driven pattern regeneration and local snapshots.
- [x] Add a synchronized adaptive-shirt grade for torso width, torso length, sleeve length, and sleeve girth so key body measurements alter the actual exported pattern rather than only its revision hash.
- [x] Replace whole-piece affine torso scaling with editable chest, waist, hip, and upper-arm ease controls that insert structural measurement anchors, reshape the real pattern, preserve seam references, and close the loop by measuring the resulting garment geometry.
- [x] Add a first-class shirt construction profile with separate front and back chest-width distribution, neckline width, independent front and back neckline depth, shoulder length and drop, armscye depth, sleeve-cap height, and front balance. The nine dimensions now reshape actual pattern curves, remain editable in WinUI, participate in revision hashing and snapshots, survive GarmentCode export/import, keep the torso draft authoritative when matching collars and sleeves, and expose controlled side-seam ease instead of silently rewriting the requested construction.
- [ ] Add production bust shaping with automatic intake generation, compound-seam side, waist, shoulder, and neckline darts, dart rotation and fullness transfer, dartless-knit rules, and cup-aware balance rather than treating front-width distribution as a substitute for three-dimensional bust shaping. Physical free-edge darts and one-edge seam-integrated darts are complete, but they validate already-drafted volume instead of solving or distributing bust volume.
- [x] Add undo and redo for point geometry states and synchronize accepted edits to the 3D bridge document.
- [ ] Expand selection to segments, whole curves, internal geometry, and annotations.
- [ ] Add numeric radius, tangent, and curvature controls for curved segments.
- [ ] Add native command surfaces for create, edit, transform, sewing, and view modes.
- [ ] Add snap targets for grid, points, intersections, tangents, perpendiculars, midpoints, and measurement guides.
- [ ] Add canvas-drawn straight-boundary, cubic-boundary, and trace tools. Direct canvas polygon drafting with 0.1 cm snapping, Shift bypass, live closure preview, point undo, finish, cancel, geometry validation, stable IDs, command replay, and persistence is functional alongside numeric rectangle, ellipse, and polygon creation.
- [ ] Add pleat manipulation, fullness, slash-and-spread, dart rotation, join, offset, and unfold tools. Direct seam allowance editing, exact guide darts, physical cut-and-sew free-edge darts, strict one-edge seam-integrated darts, exact internal-path creation, and notch placement at a selected segment midpoint are functional; compound-seam darting, automatic intake generation, canvas-drawn construction geometry, arbitrary notch positioning, and notch-style editing remain.
- [ ] Add mirrored and linked editing with deterministic identity preservation.
- [ ] Expand the current seam editor beyond direction and closure state to segment correspondence, tension, fold, and layer order. The selected permanent seam now reports compiled side A and side B lengths, absolute and percentage mismatch, and whether the relationship is matched, controlled ease, or requires correction.

### P2: Avatar fidelity and photo estimation

- [x] Preserve all 151 mapped values and provenance in each revisioned avatar profile and hard-fit every ruler supported by the current MPFB measurement topology.
- [x] Define every built-in Patterna value as a hard MPFB ruler source, named MPFB modeling-target source, bounded local deformation source, or a combination of those lanes. Automated coverage fails if any built-in key loses its body-mesh path.
- [x] Preserve asymmetric and surface-shape controls around the symmetric ruler fit with side-specific MPFB targets and an evaluated-coordinate deformation layer that keeps the stable 13,380-vertex hm08 topology.
- [ ] Add landmark visualization and measurement instructions on the avatar.
- [ ] Add posture, pose, soft-tissue, hand, foot, face, and head customization surfaces.
- [ ] Evaluate current photo-to-body models using known-measurement validation sets before product integration.
- [ ] Add multi-view capture quality checks, confidence per measurement, manual correction, and local biometric-data controls.

### P3: Physics accuracy and materials

- [ ] Use Chaos XPBD as the interactive solver and expose physical units where the engine supports them.
- [ ] Replace the vendored Jacobi spring seam solve with a solver that couples anisotropic material, contact, and multi-way seam components within each iteration. The current finite seam-allowance proxy passes the 2.5 mm closure and zero-crossing gates, but the same revision remains rejected at 44.94 percent peak full-rest strain and does not reach the static gate.
- [ ] Add continuous collision, conservative body collision volumes or level sets, self-collision, thickness, friction, and stable multi-layer ordering.
- [ ] Maintain anisotropic warp, weft, bias, shear, and bend behavior from 2D grain direction through the simulation mesh.
- [ ] Add an optional offline validation solver based on C-IPC or an equivalent intersection-free thin-shell method.
- [ ] Build fabric calibration around weight, thickness, tensile tests in warp and weft, bias shear, bending, compression, and static and dynamic friction.
- [ ] Compare simulated swatches and garments against photographed physical tests before labeling any preset accurate.

### P4: Production pattern workflow

- [ ] Import and export DXF-AAMA, DXF-ASTM, PDF, AI, SVG, OBJ, FBX, glTF, and USD where technically appropriate.
- [ ] Add grading rules, nested size groups, avatar-size pairing, and side-by-side grading review.
- [ ] Add point-of-measure definitions, tolerance tables, construction notes, labels, and tech-pack export.
- [ ] Add print layout, rotation and nap constraints, plaid and stripe matching, fabric consumption, tiled pages, and plotter output.
- [ ] Add project recovery, autosave, history, schema migration, asset relinking, and corruption checks.

### P5: Appearance, presentation, and ecosystem

- [ ] PBR fabric scanning, texture editing, normal and displacement maps, fur, knit, and transparency.
- [ ] Graphics, repeats, colorways, UV editing, trims, and realistic seam rendering.
- [ ] Studio lighting, ray-traced stills, turntables, animation caches, and export presets.
- [ ] Modular garment blocks and reusable internal libraries.
- [ ] Documented scripting and plugin API.

## Better-than-CLO usability commitments

- [ ] Keep 2D geometry, seam graph, body measurements, fabric calibration, and 3D diagnostics visibly connected.
- [ ] Selecting a pressure or penetration problem in 3D selects the responsible 2D region and relevant measurement.
- [ ] Explain why a value changed, whether it was estimated, linked, imported, calculated, or manually overridden.
- [ ] Never replace manual body or pattern edits during later estimation or regeneration.
- [ ] Show solver quality, calibration status, and uncertainty instead of presenting visual plausibility as physical accuracy.
- [ ] Provide contextual commands and progressive disclosure so new users can work without hiding advanced controls from experts.
- [ ] Make destructive edits previewable and reversible through document history.
- [ ] Keep common actions keyboard-accessible and preserve native Windows input, theming, and accessibility behavior.

## Solver and geometry architecture

1. `GarmentDocument` remains the authoritative pattern and sewing model.
2. A topology compiler validates closed boundaries, curve sampling, grain direction, seam correspondence, triangle quality, rest strain, and stable identifiers.
3. The compiler emits separate, collision-free panel staging, explicit sewing constraints, a low-resolution single-sided simulation mesh, and a separate detailed render mesh.
4. Unreal Chaos Panel Cloth provides interactive XPBD sewing and simulation. Chaos Outfit Asset provides source-body sizing, target-body resizing, and outfit packaging.
5. A high-accuracy offline mode may use C-IPC for intersection-free validation and difficult contact cases.
6. Fit maps are computed from actual body and cloth surfaces, not an unrelated analytic proxy.
7. All generated assets retain source document, body profile, calibration, and generator hashes for reproducibility.

## Research basis

The feature ledger is grounded in the current CLO manual categories, including 2D pattern creation and editing, darts and pleats, points of measure, grading, sewing, simulation, 3D arrangement and design, fabrics, trims, avatars, rendering, colorways, print layout, review, animation, UV editing, modular garments, fit maps, and scripting:

- https://support.clo3d.com/hc/en-us/categories/115000064648-Manual
- https://support.clo3d.com/hc/en-us/articles/115000297567-Modes
- https://support.clo3d.com/hc/en-us/articles/115008920368-Create-3D-Pen

The selected Unreal foundation follows Epic's current guidance for Chaos Panel Cloth, separate render and simulation meshes, XPBD constraints, collision assets, and parametric outfits that resize from a source body to target body shapes:

- https://dev.epicgames.com/documentation/unreal-engine/panel-cloth-editor-overview
- https://dev.epicgames.com/documentation/unreal-engine/getting-started-with-parametric-clothing
- https://dev.epicgames.com/documentation/unreal-engine/unreal-engine-5-8-release-notes

The high-accuracy research lane is based on IPC and C-IPC. C-IPC specifically addresses thin structures, anisotropic strain limiting, finite thickness offsets, frictional contact, and continuous collision detection:

- https://ipc-sim.github.io/
- https://ipc-sim.github.io/C-IPC/
- https://doi.org/10.1145/2994258.2994272

Open-source parametric pattern references remain useful for document and drafting concepts even though Patterna's editor is native:

- https://wiki.seamly.io/wiki/Main_Page
- https://freesewing.dev/

## Deferred move

- [x] Establish the durable GitHub repository and primary clone at `D:\VIBES\patternal`; keep this original working copy until explicit approval to remove it.

## Clean pause point - 2026-07-23

- [x] Preserve the corrected princess construction: six panels, fourteen stitch groups, exact 45.5 cm armscye, exact underbust reconstruction, separate high-bust, bust, underbust, and waist arc allocations, and independent front princess surface rulers.
- [x] Correct the evaluated body-space placement contract. Anatomical front is positive GarmentCode depth. v30 begins with every front panel and outward normal on the front hemisphere, every back panel and outward normal on the back hemisphere, correct physical left and right naming, zero body intersections, and zero self intersections.
- [x] Capture a source-consistent pause set under `artifacts/cup-aware-princess-correct-placement-v30`: a clean flat six-panel pattern plus bound front, rear, side, and oblique 3D diagnostics.
- [x] Quarantine by documentation only: `artifacts/cup-aware-princess-correct-arcs-v30` came from the disproven negative-front hypothesis and must not be used as a source, baseline, or resume point. It was retained to avoid deleting evidence during wrap-up.
- [ ] Do not promote v30. Its solver report is rejected: no static equilibrium, 70 body intersections, zero self intersections, 0.712 cm maximum seam separation, 18.893 percent 95th-percentile strain, 39.860 percent 99.9th-percentile strain, 71.084 percent 99.99th-percentile strain, and 0.000980 high-strain edge fraction.
- [ ] Resume by defining an authoritative high-bust vertical landmark on the exact fitted MPFB body. The current provisional station is bust height plus 5 cm, where the collider section is 112.42 cm but the drafted eased high bust is only 104.64 cm. Reconcile the value and landmark before changing contact, stiffness, seam force, or render material.
- [ ] After the high-bust contract passes, regenerate one new immutable pattern and repeat the same collision-clean progressive Style3D solve. Require static equilibrium, zero body and self intersections, maximum seam separation at or below 0.25 cm, and every percentile strain gate before producing a new user-facing screenshot set.
