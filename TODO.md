# Patternal product goal and v1.0 roadmap

## Readiness at a glance

Run `tools/Get-PatternalReadiness.ps1`. It reads the newest packaged-asset report, isolated guest run, control sweeps and fabric audit, and splits what is still open into what more work can close and what needs a person or an instrument. It evaluates nothing itself.

As of 2026-08-29 it reports `softwareCanClose` empty, the isolated packaged gate passing 47 of 47 with no host input, all 8 sliders and 29 numeric boxes found and restoring, all 7 camera buttons changing the view, and the fabric physically coherent. The two remaining items are a person accepting the six views and an instrument measuring a fabric swatch.

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

## 2026-08-28 challenger status

Two long-running blockers moved this day, both through installed and hash-pinned open-source runtimes rather than new in-house geometry code.

- [x] Replace the rejected procedural and MakeHuman-family display mannequins. The pinned Anny 0.6.0 runtime (Apache-2.0 code, CC0 MPFB2 data) is installed offline, the complete 152-control map is built, and immutable worker output `49adf707828f7dd24aaa8647e012f4b447069a5d94b56cf805a2910ce25205d2` carries all 21 required artifacts with every producer claim false. Visual review accepts the base anatomy; the body reads as a plausible adult female. The root cause of the previous bodies was semantic: Anny orders its gender anchors male first, so the inherited MakeHuman convention had been building a male body.
- [x] Assemble the exact 14-panel pattern into a worn garment by contact simulation. Arrangement `bf25c9972767fd27e0d8b35770c28e31409177c8fc6b5f65f8ce0eea6f789aea` passes every independent gate: zero body and self intersections, 0.306 cm clearance, 0.668 cm maximum seam separation, and both sleeves worn on the arms. Two clean runs reproduce the acceptance.
- [x] Settle the accepted arrangement under gravity. The settled drape reaches static equilibrium in 384 frames at 0.024 mm final motion and is independently accepted as arrangement `6646046e49aa1017facf7a5532002ba1fe9668bee21af2e11fa54ebedcdc3569` with zero intersections and 0.304 cm clearance. The hem now falls naturally at the hip and the sleeves hang on the arms.
- [x] Remove the dense micro-crumple from the settled surface. It was a wrong number, not a judgement call: the bending coefficient had been carried from the assembly-only calibration at 0.05 while the declared fabric's own flexural rigidity requires about 4523 in this solver. `tools/calibrate_libuipc_bending.py` derives that value from a cantilever experiment against beam theory. The settled garment now shows garment-scale folds and reaches equilibrium in 35 frames.
- [x] Reach a fully accepted settled drape. Arrangement `1a10b3b63cff17217ed833cc67b430d3cbe7e6e5c9e0e235caf7bae067f2ff13` passes all twelve independent gates with zero body and self intersections.
- [ ] Replace the declared cotton-poplin constants with swatch-measured data. The calibration proves the coefficient is consistent with the declared constants; it does not prove those constants describe a real bolt of cloth.
- [ ] Correct the chest ease semantics. On a 112 cm full bust, chest ease 14 yields a measured garment chest of 105.7 cm and only about 73 percent of each increment, because the garment chest is measured at the underarm line while the chest slider carries the apex bust. Waist ease is exact by comparison. See `docs/isolated-windows-ui-testing.md`.
- [ ] Close the remaining avatar measurement gaps. 20 of 73 objectives land within 0.75 cm and 38 within 1.5 cm; waist, hip, and the front-hip arc remain outside tolerance, and neck circumference is bounded by Anny's own range. Every gap is listed in the worker's rejection list.
- [x] Exercise the live application's toggles and numeric controls. The app builds and launches locally, and `tools/Invoke-PatternalLocalUiCheck.ps1` proved every display toggle responds and reverts, the fitted-bra toggle is correctly disabled with its explanation, and each ease box moves the matching readout dimension and reverts.
- [x] Join the Anny body to the cloth lane. Bundle `cbfb873fea536cba8945926f1566f08f9a02ba11ab850586875f9b21b3727f49` carries the fitted Anny body, posed into a declared dressing stance, as its collider, and the shirt assembles and settles on it into accepted arrangement `09a46ccf85376585b76687e7c3715b1f6d398b97e963369201090b9449962d5e` with zero intersections. Staging is now fully body-derived for sleeves, cuffs, torso, and collars.
- [x] Bring the solved cloth into the packaged application and look at it from every fixed angle. `Assets/SolvedDrape` ships the body and garment surfaces, the **Solved cloth** control in the 3D tab loads them, and `tools/Invoke-PatternalDrapeViewCapture.ps1` captures all five camera angles in both viewport states. This is packaged-application evidence, not the isolated guest gate, and it accepts nothing.
- [x] Square the dressing stance. The pose search drove arm elevation only, leaving both arms swung 28 degrees forward; it now solves elevation and azimuth together and the whole arrangement and settle chain was rebuilt on the corrected stance.
- [x] Exercise every slider, numeric box, and toggle in the running application and record what each one did. `tools/Invoke-PatternalControlSweep.ps1` drives all 8 sliders, 29 named numeric boxes, and 11 toggles through their own automation patterns, compares 16 readouts before and after each change, and restores every value. `tools/Invoke-PatternalCanvasEffectProbe.ps1` settles the controls whose effect no readout reports by comparing captures of the pattern canvas.
- [x] Fix the crash that sweep found. A drafting refusal thrown from a value-changed handler ended the process and took unsaved work with it; typing 24 into the sleeve cap height box was enough. Undraftable values are now refused at the point of entry, the previous value is restored, and the user is told which control and which limit.
- [ ] Give the quiet controls a readout. Back neck depth, sleeve cap height, bust projection, dart mouth offset, and shoulder dart share change the pattern but appear in no summary text, so the user has nothing to check their edit against.
- [x] Reach the two seam toggles in the assembly overlay. `tools/Invoke-PatternalWorkspaceSweep.ps1` now opens the overlay and searches the relationships for one that enables each toggle. `ReverseSeamSideBToggle` enables, responds and restores. `ClosureStateToggle` never enables: the crew-neck offers 38 relationships and the wrap dress 14, and all 52 are seams, so no garment the application ships contains a closure.
- [x] Fix `ClosureStateToggle`. It is now shown only while the garment declares a closure, so a control that nothing in the document can enable is no longer presented as a broken one. The sweep reads the overlay's own summary to tell an inapplicable control from a missing one, and reports it absent by design against a garment with zero closures.
- [x] Sweep the 3D camera buttons by looking rather than by clicking. All seven are present and each one visibly changes the rendered viewport, checked by capturing the viewport after each and comparing image hashes, so a button wired to nothing would be caught.
- [ ] Reach the two seam toggles in the assembly overlay. `ReverseSeamSideBToggle` and `ClosureStateToggle` need a seam selected in that overlay before they exist, and the sweep does not yet make that selection, so neither has ever been exercised.
- [x] Fix the grader defect that made re-grading impossible. `MatchConstructionSeamLengths` reconciled the two legs of a bust dart as though they were separate panels and bowed them into each other, self-intersecting the front torso on any body. It now leaves same-piece seams alone and refuses to reshape an edge to close a mismatch already inside sewing tolerance.
- [x] Make `--pattern-only` run the boundary check it was skipping. It now compiles the pattern topology before writing and exits 2 naming the offending piece, instead of emitting a specification that fails much later inside the mesher with no cause attached.
- [x] Reconcile the armhole inputs with the block. Settled by measurement and experiment: the block's own armhole is 19.19 cm tall with a 46.91 cm armscye, the profile bridge records 21.8 cm, and grading succeeds at 19.19 cm across every circumference tried while failing at 21.8 cm. The armhole depth in the bridge is the stale record. It still needs measuring on the body itself; the arm-root envelope in `tools/prepare_anny_garmentcode_body.py` is the right instrument and needs a body segmentation the Anny worker does not yet emit.
- [x] Grade the shirt to this body and see what happens. Done end to end; the result passes all twelve gates twice with zero intersections and looks worse than what it replaced, because the body misses its own hip target by 5.45 cm and the grading carried that into the pattern before adding ease. Kept out of the packaged application; evidence in `artifacts/packaged-drape-views-regraded`.
- [ ] Reconcile the armhole inputs with the block. `armholeDepth 21.8` with `armscyeCirc 45.5` cannot be drafted onto this shirt at any ease, and it fails identically on the original Antonia measurements, so the profile bridge and the base pattern disagree independently of which body is being graded. Find which of the two is authoritative before grading anything.
- [x] Determine whether the avatar's measurement failures are closeable. They are not, by this model. `tools/audit_anny_fit_saturation.py` separates a range limit from a search failure and reports 6 range-limited, 10 contended on a shared control, and 20 that a better search could still close. Twelve of its sixty-five fitted parameters sit on a bound, and four of those drive garment-critical objectives that remain 2.77 to 5.78 cm short with their control at maximum: shoulder breadth, underbust girth, chest depth, and bust projection. Separately, the front and back hip arcs share one control and need it to move in opposite directions. The targets are the Antonia measurement set, so the pipeline has been asking one parametric human model to reproduce a body authored in another.
- [x] Answer whether any body we already have can be driven to the measurements a pattern needs. None can. `tools/audit_avatar_control_coverage.py` measures all three against the seven control groups in `docs/measurement-native-avatar-cage-contract.md`: Anny fails all seven, four of them because its control is at its bound and the target is still missed; MHR has morph parameters for girths and depths only and nothing for vertical landmarks, front and back arcs, bust position and projection, or the neck; Antonia reaches every value only because the targets were measured from her, and has no controls at all. This is independent measured support for the cage contract's premise, and it is also the requirement list any replacement has to satisfy.
- [x] Look outside the three bodies already compared. The capable one was already installed: MPFB2 is vendored, mirrored into the runtime, and live as a Blender 4.5 extension with all 1,258 morph targets, of which Anny's 17 measurement controls are a strict subset. `tools/generate_mpfb_avatar.py` fits a body through them, and the accepted report at `Patternal/Assets/Production/patterna-full-bust-default-fit-report.json` hits all twenty measurements within 0.15 cm with no blocking failures, including the underbust, waist, hip, and neck values Anny misses by 3.4 to 5.5 cm with its controls at maximum. It was demoted for appearance, not capability.
- [ ] Prove the three MPFB control groups its current fit does not exercise: station depths, independent front and back arcs, and bust position and projection. The targets exist in `tools/mpfb_morph_controls.py`; what is missing is a fit that drives them and an evaluator that measures them, which is what the cage contract asks for.
- [x] Show the MPFB pairing in the packaged application. It needed no solving: the body and its accepted Newton Style3D garment were already in `Patternal/Assets/Production`, reachable only through a bundled-baseline path that requires nine exact conditions and so almost never fires. `tools/package_existing_drape_pair.py` packages them into the standard report shape, and they are now what the solved-cloth control shows. It is the best drape in the project and the only one on a body that reaches its measurements.
- [ ] Record a visual review of the MPFB pairing against the six required views, so `visualReview.accepted` and `sixViewManifestSha256` stop being empty. That plus a swatch-measured fabric and an arrangement verification are what now stand between this asset and the product gate; none of them is a fit problem any more.
- [ ] Take the MPFB body through the cloth lane. The pattern is graded to the same 112/82/108 measurement set this body hits to within 0.15 cm, so this is the first pairing where the garment and the body agree by construction rather than by coincidence.
- [ ] Decide what the body should be. Three configurations are now solved, packaged and captured, all passing the twelve gates with zero intersections: Antonia wearing her own pattern (cleanest render, but the bundle recipe records that this display candidate is visually rejected), the Anny body wearing Antonia's pattern (most even realized ease at 7.8 cm spread, currently shipped), and the Anny body wearing a pattern graded to it (worst on both counts). Evidence is in `artifacts/packaged-drape-views-antonia`, `-restored`, and `-regraded`. The choice is between a body whose garment fits and a body that passed its own visual review, which is a product decision.
- [x] Measure whether the garment is the right size for the body, rather than only whether the cloth is valid. `tools/verify_packaged_drape_assets.py` now reports realized ease from nine torso sections through both meshes. It does not yet see shape faults such as drag lines, and its shoulder stations are inflated by sleeve cloth.
- [ ] Decide what the body should be, now that matching Antonia with Anny is ruled out. Either take Anny's own achievable shape as the target set, which makes the avatar acceptable by construction and lets the garment be graded consistently to it, or replace the avatar model with one whose range covers the target. The repository already carries two alternatives: the MHR candidate that ships as the display avatar, and Antonia itself, which reaches these measurements because they were taken from it.
- [ ] Correct the order of work on the body. `tools/prepare_anny_garmentcode_body.py` refuses an avatar fit report that is not accepted, and the current fit has 36 of 73 objectives outside tolerance. The garment cannot be honestly drafted for this body until the body meets its own targets; close the garment-critical failures first, chiefly front-hip arc (+8.14 cm), chest depth (-5.78 cm), hip circumference (+5.45 cm), and neck-base circumference (+5.43 cm).
- [ ] Grade shape, not only girth. `Adapt` takes nine scalars while the body has 73 measured objectives, so the front-to-back split and the bust apex are inherited from the other body whatever the girths are set to. The body needs a 53:47 front-to-back hip split against the block's 48:52, and has a 6.63 cm bust projection against the block's 9.6 cm. Those two are the uneven back hem and the standing sleeve-head ruffles.
- [ ] Re-draft the pattern for the Anny body. The garment worn in that result was graded to the Antonia measurement set; the fit is credible but it is not this body's pattern. The packaged views show what that costs: an uneven back hem with a diagonal drag line, standing ruffles at the sleeve heads, and a hem that sits at high hip.
- [x] Run the isolated packaged gate. It was never blocked: the guest was provisioned and running, and one command executed it. Against a payload built from current source it ran 47 actions in 370 seconds with no host input injected, passing 46 and producing 25 screenshots and both workspace trees. Evidence in `artifacts/isolated-ui/runs/20260829-055334-b8d01e26`.
- [x] Diagnose the one action the isolated gate failed. The out-of-date notice now reports the numbers instead of a list of categories, and they show that ten of the eleven construction values differ between the default pattern and the shipped cloth, with the armscye scoop 2.13 cm against minus 9.11 cm. The bundled cloth was solved from a materially different garment, so the application is correct to refuse to present it as current.
- [x] Find why the default pattern and the shipped cloth never match. The aligner filled the construction controls from the ungraded source block while the checker compared them against the graded document, so no value could satisfy it. The aligner now measures the graded document, which is also what a user should see.
- [x] Find why the application never showed its own accepted cloth. The shipped pattern records how many body measurements drafted it and not their values, so the imported garment had no body reference, so the body could never be recognised as matching, so the construction controls were filled by armscye fitting instead of measurement and could never equal the graded garment's. Supplying the body reference at import fixes the whole chain: the 3D tab now reports accepted Style3D cloth on a fresh document, and the isolated packaged gate passes 47 of 47 with no host input.
- [ ] Decide whether the Solved cloth control is still wanted. It was added while the accepted path could never fire; now that it does, the control shows the same pair without the display avatar, so it is a diagnostic beside a better view rather than the only way to see a solve.

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
- [x] Establish that the shipped fabric is at least physically coherent. `tools/audit_fabric_coherence.py` checks the relations the numbers impose on each other: packing fraction against fibre density, bending length against published ranges per fabric class, membrane stiffness, shear as a fraction of tensile, friction, and warp to weft anisotropy. The shipped jersey passes all six, and the audit doubles as a regression test for the two material bugs this project actually hit.
- [x] Fix the torn avatar. Moving a measurement grew the body while its modesty shells only height-scaled, so the body came through them and the figure rendered with holes at the bust and hips. The shells now follow the body, each vertex borrowing the movement of the body vertex it sits against, so they stay on and stay intact. `tools/Invoke-PatternalAvatarResponseCheck.ps1` moves every body slider and captures the result, and all six now move the body with the figure intact.
- [x] Check that measurement controls move the render, not just their own numbers. All eight body sliders move the body. Of fourteen sampled inspector controls, twelve change the viewport; the two that do not are `Armscye depth` and `Finished armscye ease`, both values the draft guard correctly refuses as undraftable, so the number reverts and nothing should change. Evidence in `artifacts/detailed-response`.
- [x] Extend that check to the detailed body measurements. Opening every measurement group reaches 175 controls, of which 154 are body dimensions rather than garment ease or construction. Of ten sampled, seven were accepted and moved the body, covering thigh circumference, back neck to waist, back hip arc, waist to knee, ear to ear over crown, back neck length and front torso share. Two probes were clamped as out of range, correctly. Evidence in `artifacts/body-measure-response`.
- [x] Fix the avatar preview reporting baseline while the body is not at baseline. The second guess was right: the payload was assembled before the value committed. A WinUI `NumberBox` raises `ValueChanged` from its own value change, before the `Mode=TwoWay` binding writes that value into the `MeasurementParameter` behind it, and every consumer in the handler reads the measurement rather than the event. So the draft, the fit report, the draftability probe and the 3D body were all built from the value the user had just replaced, and each edit pushed the lag forward one step. The handler now commits the committed value to the bound measurement first, and the revert path restores it too. Changing `Total crotch length` now reports "3D unsupported for this revision, 1 unmapped values" within five seconds instead of on the following edit.

- [x] Stop counting derived measurements as user changes. Moving the chest slider to 124 and straight back to 112 left the preview permanently claiming 46 dimensions could not be drawn. `ApplyLinkedBaselineMeasurements` derives about fifty measurements from the six primary ones and rounds them, and several do not equal their declared defaults even at rest, so a round trip left them fractionally off and each was counted as a dimension the preview had to represent. The payload now counts a detailed measurement only when the user set it.

- [x] Give the measurement inspector a way back. With 151 measurements and no reset, a profile could only be moved away from its defaults. "Reset measurements to defaults" restores every declared default and clears the manual-override flag so abandoned measurements follow their estimates again. `tools/Reset-PatternalMeasurements.ps1` does the same for automated runs.

- [x] Stop opening a measurement group from re-drafting the pattern once per control. Realising a bound `NumberBox` raises `ValueChanged` as the binding fills in the value the measurement already holds, and the handler treated each as an edit, marking untouched measurements as manually entered and re-drafting each time. Opening the ten groups took 295 seconds; it now takes 3.6.

- [x] Measure what the 3D preview can actually represent, from the declarations rather than from pixels. `tools/audit_preview_dimension_coverage.py` reports 151 editable body dimensions against 13 the shipped basis can move: nothing in the head, nothing in the legs or feet, nothing in posture. The screenshot probe that had suggested otherwise was counting the viewport's own status text, and `tools/Invoke-PatternalAvatarResponseCheck.ps1` now excludes that strip and reports `viewportChanged` rather than claiming the body moved.

- [x] Move the interactive preview onto the MPFB body. Done, and the preview now moves 97 of the 151 editable dimensions instead of 13: head, face and neck from 0 of 16 to 14, each leg and foot from 0 of 17 to 11, each arm and hand from 1 of 16 to 13. The figure stays intact when a measurement moves it, with eyes, brows, lashes and hair following the head rather than being left behind, and a dimension the basis genuinely cannot represent still reports "3D unsupported for this revision" honestly.

- [x] Get past the body mismatch without regenerating the packaged assets. The obstacle was that a delta is a difference from the body it was measured on, and today's pipeline produces a body 6.94 cm from the packaged one. The way past it was to change what is measured: MPFB targets are additive vertex offsets, so measuring the target contribution alone yields deltas that are a property of the control rather than of the body. That is verified on every run, not assumed. The generator displaces one control before and after the ruler fit has moved the body 8.4 cm and requires the two to agree; they agree to 0.061 cm, a coupling of 0.723%, which is about half a millimetre carried onto the packaged body. The tool refuses to write a basis whose coupling exceeds the declared tolerance, and the packaging step only waives its body-identity check for a basis that declares itself this kind.

- [x] Prove the garment can be re-solved on a body the current pipeline produces. It can, and the solve is accepted. `tools/prepare_style3d_body.py` recovers the missing Z-up to Y-up conversion and reproduces the packaged collision body exactly; `tools/build_style3d_source.py` reproduces the packaged garment topology exactly, 133,870 vertices, 262,814 faces and 1,974 seam links; and the Newton Style3D solve reaches static equilibrium at frame 878 with zero body collisions, zero self intersections, zero seam separation and zero high-strain edges. Evidence in `artifacts/style3d-resolve-v1/style3d-settled`.

- [x] Sweep the 2D authoring workspace, which had no automated check at all. `tools/Invoke-Patternal2DAuthoringSweep.ps1` captures the pattern canvas on its own, so a changed image means the drawing changed rather than some panel's text. Both overlay toggles, seam allowance and grainlines, redraw and restore. Thirteen of fourteen pieces redraw when selected and the fourteenth was already selected. Engaging point editing brings up all eleven point controls: reset, split, convert to curve, convert to line, add notch, the sewing-edge pair, and the four numeric boxes. The canvas itself draws seam allowances, notches, grainlines and bust darts over a calibrated grid.

- [x] Test the Simulate button, which had never been exercised in a session, and fix what it found. It failed every time, at the Style3D source stage, because the body-aware warm start from the Unreal garment compiler has triangles of 0.000095 cm2 against a 0.001 minimum and edge strain of 5.54 against a limit of 2.0. The compiler had already written `"accepted": false` beside those numbers; the pipeline's own check read that file, verified the panel count, stitch count, seam gap and torso clearance, and passed it on regardless. Two gates on the same property, and the earlier one was the weaker.

  The check now applies the same thresholds the solver input gate applies and honours the compiler's verdict, and a rejected warm start no longer ends the run: the panels settle from their drafted layout instead. That is evidenced, not invented. Building the source against the same body with no arrangement passes the gate, and a full solve on such a source reaches static equilibrium with zero body collisions, zero self intersections and zero seam separation. The button now gets past the stage that used to end it and reaches the solver.

- [x] Answer honestly whether the 3D view looks acceptable. It did not. The viewer lit everything from a 30% flat floor with no shadow side, clipped highlights with no tone mapping, and lit the body in linear light but the garment and grid in display space. Rewritten in linear light for every mesh: hemisphere ambient, a wrapped key on skin, a scattering tint at the terminator, filmic tone mapping. Morphing had also produced faceting because normals were recomputed per render vertex rather than per source vertex; fixed. The status line no longer labels the packaged cloth with a failed job's revision hash. Before-and-after captures in `artifacts/preview-look`. All three sweeps unchanged.

- [x] Put the textured body, hair and face under the packaged cloth. The solved-drape body is the production collision body vertex for vertex, so the production display avatar belongs on it; the packaged six views showed a bald untextured collider only because the solved-drape path passed no display avatar. All twelve views regenerated under the new lighting into `artifacts/packaged-drape-views-lit`.

- [x] Give the garment fold shading. A screen-space curvature term darkens indirect light in concave folds on cloth only; the first version was scaled for the wrong units and measured as invisible, the recalibrated one measures 2.45 mean and 91 maximum in the shirt region and 0.00 on skin.

- [x] Pose. The rebuilt simulation pipeline lowers the arms on both the fitted and the textured display body after the contact stage, builds a relaxed collider, and lets the final settle animate the dressed cloth from the rest body to the relaxed one over 180 frames. The first end-to-end run accepted that settle: equilibrium at frame 222, zero body collisions, zero self collisions, zero seam separation. The six Blender views show the tee draping with real tension across the bust and folds at the side seams.

- [ ] Human review of the six views. Everything software can check on the MakeHuman pipeline now passes; the product gate then waits for a person to review `proofs/product` in the job directory and record the decision with `tools/record_product_visual_review.py`. Until that is recorded, the run ends with a message saying exactly that.

- [x] Keep the bra shell on the torso. The shell rays hit the raised arms first, which drew two grey slabs out to the arms in the six views. The fit now walks past arm-driven faces to the torso behind them. Verified on 2026-11-16 by regenerating the display avatar directly and rendering it: the shell spans 18.9 cm either side of the midline, was 41.2 cm, and the views show no slabs. Check views are in `artifacts/preview-look/handoff-2026-11-16/bra-fix-check`.

- [ ] Run the full Simulate flow once on a fresh job directory with the corrected bra shell. The 2026-09-13 run that was meant to prove the shell resumed an older job and rendered stale avatar assets, so no end-to-end run has exercised the corrected generator.

- [ ] Bind job resume to the runtime scripts. `CanResumeAcceptedStyle3DEquilibrium` reuses cached stage outputs when the pattern, body and solver reports match, and does not notice that a generator script changed. Record the runtime version and script hashes in the job and refuse to resume when they differ.

- [ ] The bra shell is fitted on the rest body and is not posed with it. Near the armpit the skin moves a few millimetres when the arms lower 12 degrees and the shell sits 0.08 mm off the skin. No poke-through shows in the check views under the tee; confirm with the garment hidden.

- [ ] The MakeHuman avatar carries a bra shell but no briefs, so the lower body renders nude in the six views. MakeHuman's CC0 clothes library is installed and could supply one.

- [ ] The tee itself reads as a boxy crop top. That is the drafted pattern and its ease, not the rendering.

- [x] Retire the third body. The live simulation path now builds the MakeHuman MPFB body: fit, rest-pose collider, drape, contact, then the arm-lowering pose on both the fitted and the textured display body, a relaxed collider, and a final settle that animates the dressed cloth from the rest body to the relaxed one. The runtime manifest, required-script list, integrity list and installer declare MPFB instead of Antonia, and promotion accepts the generator's current fit-report schema. The pose gap and the promotion gap both ran through this.

- [ ] Make the packaged assets rebuildable. Two of the three stages now are, and the solve above is accepted. What is missing is the promotion stage, which needs an accepted simulation job binding the solved surface to a compiled render mesh, and that assembly happens inside the application's Simulate flow rather than in a callable tool. Retiring the third body is the prerequisite, because that flow is what would produce the job.

- [ ] Human sign-off on the six packaged views and a fabric swatch measurement. Neither can be done by software.
