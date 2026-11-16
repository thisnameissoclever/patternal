# Lessons learned

### 2026-08-28: A visual cloth defect can be a derivable number rather than a judgement call

- **What happened:** The first settled garment was covered in dense mesh-scale crumple. The obvious next move was to try bending-stiffness values until the renders looked better, which the challenger contract forbids as parameter fishing. Instead the coefficient was derived: the discrete shell bending energy is linear in its coefficient, so one cantilever experiment in the same solver measures the constant that maps the coefficient to physical flexural rigidity. The declared fabric needed about 4523; the run had used 0.05.
- **Root cause:** The bending coefficient had been copied from an assembly-only calibration whose own documentation said it was not fabric acceptance data, and no one had checked it against the fabric's physical constants. Nothing errored, because any positive value produces a running simulation.
- **Prevention:** When a solver parameter has a continuum meaning, derive it from the declared physical constants and confirm the mapping with one experiment whose answer is known analytically. Wrinkle wavelength is set by bending stiffness, so mesh-scale buckling is evidence of a wrong coefficient rather than a reason to smooth the render.
- **Verification:** Two probes three orders of magnitude apart must agree on the coefficient-times-deflection constant, and the calibrated value must reproduce the analytic cantilever deflection. The settled garment then reaches equilibrium in 27 frames instead of 384 and shows garment-scale folds.

### 2026-08-28: A UI probe must commit the control the way a user does

- **What happened:** A local UI Automation check set the chest, waist, and hip ease boxes through the value pattern and reported that the measured-garment readout never moved, which read as a serious app defect. The controls were fine. A WinUI NumberBox commits on Enter or lost focus, so setting the text alone left the app's value unchanged and no re-draft ever ran.
- **Root cause:** The probe modeled the control's storage rather than the user's interaction. Any commit-on-blur control will look dead to an automation client that never blurs or presses Enter.
- **Prevention:** Drive input controls through the full user gesture: focus, set, then commit with Enter, and prove the probe by confirming a control that is known to work responds. Treat a no-response result from an unproven probe as a probe defect until the probe itself is validated.
- **Verification:** After adding the focus-and-Enter commit, waist ease 6 to 20 moved the readout from 88.0 cm to 102.0 cm and restored exactly, on the same build that had appeared unresponsive.

### 2026-08-28: A derived-data cache must be pinned when a chaotic consumer amplifies its low-order bits

- **What happened:** Two same-seed Anny worker runs produced meshes differing by up to 7 cm. The runs differed only in their `ANNY_CACHE_DIR`: one loaded the existing all-labels model-data cache, the other rebuilt it. Rebuilds produce byte-different safetensors of identical size (summation-order noise in the blend-shape assembly), the model tensors differ in low-order bits, and 420 steps of bounded differentiable fitting amplify that to centimeter-scale parameter divergence.
- **Root cause:** The cache was treated as a transparent performance detail. For the default configuration it is (the install smoke proved identical neutral meshes across fresh caches), but the fit is a chaotic consumer for which any sub-ulp model difference forks the optimization path.
- **Prevention:** Pin one cache build as a content-addressed runtime artifact, record its hashes in the runtime evidence, and define worker determinism as same pinned cache plus same seed. Never compare determinism across cache rebuilds of a chaotic pipeline.
- **Verification:** Two worker runs against the same pinned cache directory must produce identical canonical mesh hashes; two runs against independently built caches are expected to differ and must not be used as a determinism proof.

### 2026-08-28: A borrowed convention scalar must be verified against the target system's anchor order

- **What happened:** The Anny avatar worker set phenotype gender to 0.0, the value that means fully female in the MakeHuman macro convention Patterna's MPFB lane used. Anny orders its gender anchors male-first, so 0.0 built a fully male body. The fit then pressed 151 female measurements onto a male frame, every breast blend shape was multiplied by a zero female weight, cup size and firmness had exactly zero mesh effect, and the optimizer silently satisfied the bust circumference by inflating the ribcage.
- **Root cause:** A same-named scalar was copied across systems that share ancestry without checking the anchor order that gives it meaning. Nothing errored, because 0.0 is a valid value in both systems.
- **Prevention:** When mapping any normalized control between model families, read the target system's anchor or variation table (`PHENOTYPE_VARIATIONS` in anny) and prove the semantic direction with a mesh-derived check, such as evaluating the control at both extremes and measuring the region it should move, before committing the mapping.
- **Verification:** Evaluating cupsize 0.0 and 1.0 on the corrected female base must produce materially different bust projections; on the male base it produced byte-identical meshes.

### 2026-08-28: An isotropic-moduli API silently destroys a split stretch-and-shear calibration

- **What happened:** The libuipc arrangement executor fed the assembly calibration's separate 60 kPa stretch and 600 Pa shear values into `ElasticModuli2D.youngs_shear`. That pair implies a Poisson ratio of 49 and a negative Lame lambda; the toy shell exploded to a 73-meter displacement in thirty frames, and at scale the runaway velocities inflated the contact broad phase to 23 GB of GPU memory before crashing.
- **Root cause:** The calibration lists three constants from a Baraff-Witkin-style parameterization, but the pinned constitution accepts one isotropic pair. Combining constants across parameterizations without checking the implied derived values produced a physically invalid material that no error message reported.
- **Prevention:** When a solver API takes fewer material constants than a calibration declares, derive the implied remaining constants and reject the configuration if any falls outside physical bounds (Poisson within [0, 0.5)). Record the adaptation in the declared schedule instead of quietly dropping a constant.
- **Verification:** A single translated-and-stretched quad under the corrected `youngs_poisson` moduli relaxes toward rest instead of diverging, and the full 14-panel scene initializes and advances without memory growth.

### 2026-08-28: Escape-sensitive file content must come from script files, not inline shell strings

- **What happened:** Two hash-locked pip requirement files were generated through inline heredoc and quoted-string Python, and both times the backslash-newline continuation reached disk as a literal backslash plus the letter n, which pip rejected as an invalid requirement.
- **Root cause:** Bash heredocs and PowerShell quoting each rewrite backslash sequences under their own rules before Python sees the source, so the same escape text produces different bytes depending on the wrapper shell.
- **Prevention:** Write generators that emit escape-sensitive bytes as real script files and run them by path. Never pipe multi-line escape-bearing source through a shell string. Verify emitted continuations by byte inspection before consuming them.
- **Verification:** `od -c` on the generated lock shows `\` followed by a newline character, and `pip install --require-hashes -r` parses every line.

### 2026-08-23: A legacy numerical fit cannot become a new avatar-worker acceptance claim

- **What happened:** The historical Anny 0.5 fitter could apply a custom two-pass torso cage, write `accepted: true` after local measurement and watertightness checks, and feed that Boolean to its GarmentCode body preparer. It had no complete 151-control report, independent display review, collider-registration acceptance, or product acceptance boundary.
- **Root cause:** One Boolean represented local numerical success and looked reusable as broader avatar acceptance. The old report schema did not encode the scope clearly enough to prevent that interpretation.
- **Prevention:** The new immutable output manifest is incompatible with `patterna.anny-profile-fit/1.0`. It requires every output role and every control row, binds them to the exact avatar-worker input, and keeps all producer acceptance claims false. Independent verifiers own later numerical and visual decisions.
- **Verification:** Create two outputs from the same recipe and require identical output IDs. Reject a producer acceptance claim, an incomplete control report, changed artifact bytes, and an Anny 0.5 fit report substituted for the control-application report.

### 2026-08-22: A saved VM can resume an already-initiated guest shutdown

- **What happened:** A packaged UI run restored the dedicated guest from a saved state, opened a PowerShell Direct session, and then hung because Windows completed a shutdown that had been initiated before the VM was saved.
- **Root cause:** The host treated Hyper-V `Saved` as an ordinary stopped state. Saving freezes the guest exactly where it is, including after `shutdown.exe` has already started. The result poll also used an unbounded remote call, so its own 600-second deadline could not run after the guest disappeared.
- **Prevention:** All routine guest entry points now stabilize a resumed saved state and boot once from a clean `Off` state if the resumed guest completes a pending shutdown. UI result polling checks the Hyper-V state and bounds each PowerShell Direct status query to 15 seconds.
- **Verification:** Save a healthy guest and require the normal path to remain running through the stabilization window. Separately save a disposable guest after initiating shutdown, then require one clean reboot or a bounded explicit failure without leaving a host process stranded.

### 2026-08-22: Routine packaged UI checks must not perform an implicit dependency restore

- **What happened:** The isolated guest synchronization command built the application with the .NET default restore behavior even when the intended check needed only already-cached Debug dependencies.
- **Root cause:** Packaging and dependency acquisition were coupled in one normal-path command. A visual regression run could therefore contact package feeds or change the local dependency cache without making that boundary visible.
- **Prevention:** Guest payload synchronization now disables restore by default. A caller must use the explicit `-AllowRestore` switch only after reviewing and authorizing dependency installation.
- **Verification:** Build the x64 Debug package with restore disabled, run the static isolated-harness contract, and require the normal synchronization path to fail with an authorization hint if cached packages are missing.

## Cross-PowerShell directory hashes need ordinal path ordering

### What happened

The host materialized and transferred a 95-file AppX payload, but the guest rejected it because the recomputed directory identity differed. A read-only file inventory proved that every relative path, byte length, and SHA-256 was identical on both sides.

### Root cause

The host used PowerShell 7 and the guest used Windows PowerShell 5.1. Both identity functions sorted absolute file paths through `Sort-Object FullName`, whose culture-sensitive ordering differed for the mixed-case package paths. The hash therefore depended on the shell and machine even though the directory did not.

### Prevention rule

Construct canonical identity lines from normalized relative paths, byte lengths, and lowercase hashes, then sort those complete lines with `StringComparer.Ordinal` before hashing. Never use culture-sensitive shell sorting in a cross-runtime content identity.

### How to verify

Run `Test-PatternalIsolatedUiHarness.ps1` and require both host and guest identity implementations to use ordinal sorting. Prepare and install an AppX containing mixed-case asset paths, and require the host identity, expanded guest identity, file count, and per-file hashes to match exactly.

## A drawn dart is not cloth topology

### What happened

Patterna could create, edit, render, save, and export boundary-anchored dart records, but the topology compiler ignored them. The visible dart legs were annotations on an unchanged panel, so simulation received no wedge, no paired dart legs, and no closure constraint. Calling that first-class dart support overstated what the cloth system could physically do.

### Root cause

The document model mixed construction intent with compiled cloth geometry. Dart metadata described where legs and an apex belonged, but no explicit compilation stage owned cutting the boundary and sewing the resulting legs. The UI and SVG evidence therefore proved authoring metadata, not a physical garment operation.

### Prevention rule

Every construction feature must declare whether it is an annotation, editable source intent, or materialized cloth topology. Simulation and production export may consume a dart only after a deterministic compiler changes the boundary and emits its stitch relationship. Keep the unmaterialized parameters as the editing authority, make materialization idempotent, and reject unsupported seam-integrated cases instead of drawing a plausible symbol and pretending it is sewn.

### How to verify

Create an equal-leg dart on an unsewn rectangle edge. Require the source to remain unmaterialized, require compilation to replace the mouth with two physical boundary legs and one same-panel seam, compile positive-area triangles and less than 1 percent seam mismatch, export and reimport without applying the cut twice, and reject free-edge mode when its mouth edge is already sewn. For existing-seam mode, use a source edge whose remaining spans equal the opposite seam after intake removal, require the original seam to become two matched spans, and reject an otherwise identical block with no drafted intake.

## Seam repair must respect pattern-construction ownership

### What happened

The first construction-profile pass reached the requested neckline, shoulder, armscye, sleeve-cap, width-distribution, and balance dimensions. A generic seam-length repair then tried to shorten a tiny torso armscye connector to the sleeve, which was geometrically impossible without moving its sewn endpoints. When torso side seams were repaired by adding curvature, the repair also changed the measured front/back chest distribution after the construction solver had reached its target.

### Root cause

The seam repair treated both sewn sides as interchangeable. It did not know that the torso block owns neckline and armscye construction while collars and sleeves are dependent pieces. It also treated intentional front/back balance and width distribution as errors to erase instead of construction choices that may create controlled ease or require a later dart/fullness rule.

### Prevention rule

Every seam family must declare an authoritative construction side. For a shirt, preserve torso neckline and armscye anchors, adapt collar and sleeve curves to them, and report front/back side-seam ease without silently changing the requested torso profile. Do not claim full bust shaping until explicit dart, fullness-transfer, or dartless-knit rules absorb that balance.

### How to verify

Run the topology regression with a non-default nine-value construction profile. Measure the resulting pattern, require every requested construction dimension within 0.25 percent or 0.1 cm as appropriate, require collar and sleeve attachments to stay below the seam gate, require controlled torso ease below 4 percent for the tested adjustment, and export then reimport the GarmentCode document without losing the profile.

## Absolute world bounds do not prove anatomical registration

### What happened

The product proof accepted a display avatar translated 20.66 cm above the simulation body's floor. The shirt and avatar both remained inside individually plausible world-space ranges, so absolute height and overlap checks did not identify that the garment occupied the wrong anatomical band.

### Root cause

The registration gate checked each object's world bounds but did not normalize the garment's hem and neckline against the display body's own floor and height.

### Prevention rule

Product presentation gates must express garment coverage in the avatar's anatomical coordinate frame. For an upper-body garment, validate the hem, neckline, and vertical span as fractions of body height after enforcing the shared floor datum. Keep absolute overlap and horizontal centering as additional independent checks.

### Verification

Run the deterministic product registration tests with the accepted bounds and with the historical 20.66 cm MPFB floor translation. The accepted body must pass, and the translated body must fail both the floor and neckline-region checks before any render is promoted.

## WinUI path geometry ownership

### What happened

The first integrated launch crashed with HRESULT `0x80070057` while building layered pattern pieces.

### Root cause

The same mutable `PathGeometry` instance was assigned to both a seam-allowance `Path` and the filled pattern-piece `Path`. WinUI rejected the second `Path.Data` assignment at runtime even though XAML and C# compilation succeeded.

### Prevention rule

Clone mutable WinUI geometry objects before assigning them to more than one visual element. Do not assume WPF-style geometry sharing behavior applies to WinUI 3.

### Verification

Launch the packaged app, confirm the 2D editor shows both dashed seam allowance and filled pattern pieces, and verify the process remains responsive with a nonzero main window handle.

## Visual Studio 2026 WinUI CLI template registration

### What happened

The bundled Visual Studio workload configuration completed, but `dotnet new list winui` still returned no matching template.

### Root cause

Visual Studio 2026 installed Windows App SDK C# support under its current component ID, while the CLI template was not registered in the user template cache.

### Prevention rule

Verify the template separately from Visual Studio workload installation. When the workload is present but the CLI template is absent, use Microsoft's official `Microsoft.WindowsAppSDK.WinUI.CSharp.Templates` package rather than a third-party template.

### Verification

Run `dotnet new list winui`, scaffold a clean project, then build and launch it through the package-aware workflow before adding application code.

## Anatomical fidelity requires visual acceptance criteria

### What happened

The first 3D avatar passed compilation, launch, and interaction checks but rendered as disconnected stretched ellipsoids. It was not recognizably human enough and the six-measurement editor did not satisfy the requested body-customization depth.

### Root cause

Verification covered process health and WebGL rendering, but did not define or inspect a minimum human silhouette, connected anatomy, or measurement-coverage threshold before reporting the implementation as complete.

### Prevention rule

For visual body-model work, set explicit acceptance criteria before implementation: one connected body surface, recognizable head and jaw, neck, shoulders, limb joints, hands, pelvis, knees, calves, ankles, and feet; editable depth and projection controls; independent left and right measurements; and a full screenshot review at the final window size.

### Verification

Inspect the actual 3D tab with the garment both visible and hidden. Confirm a recognizable continuous body, open the grouped measurement editor, edit a side-specific dimension, and verify that the regenerated mesh changes without a crash. A successful build is necessary but is not visual proof.

## Cloth behavior must come from a solver

### What happened

The first garment preview was a procedurally shaped shell with animated shader folds. It looked like a rigid tube around the avatar and did not demonstrate cloth hanging under gravity, which missed a central product requirement.

### Root cause

The implementation treated the final garment silhouette as geometry to generate instead of a result to solve. Visual verification checked that a garment was present, but did not check whether its particles moved, settled, remained attached, or collided with the avatar.

### Prevention rule

A drape preview must have explicit particles or vertices, gravity, time integration, pinned or sewn attachment constraints, stretch resistance, shear resistance, bend resistance, damping, and avatar collision. Shader motion may improve appearance but cannot substitute for geometry changing under simulation.

### Verification

Inspect the running app before and after pressing Simulate. Confirm the pinned neckline remains attached while the hem moves and resettles, the garment does not pass through the torso or legs, changing fabric parameters regenerates solver constraints, and the settled mesh has no invalid positions or collapsed triangles.

## Guard fractional shader powers

### What happened

The cloth mesh appeared to have several black tears even though its topology and solver diagnostics reported no invalid vertices or collapsed triangles.

### Root cause

The rim-light dot product used a slightly non-unit view vector. Values just above one made the base of a fractional `pow` call negative, producing NaN fragment colors that WebGL displayed as black holes.

### Prevention rule

Normalize lighting vectors, clamp dot products to their mathematical range, provide safe fallbacks for near-zero normalization, and clamp color channels before fractional powers.

### Verification

Render the garment with the avatar both visible and hidden, inspect the front and back under rotation, and confirm the entire cloth surface remains shaded without black gaps during and after simulation.

## Constraint seams also need visible surface continuity

### What happened

The first panel-based dress used distance constraints to pull front and back edges together. The particles were numerically close, but the running garment still showed open waist and side gaps from angled views.

### Root cause

Distance constraints describe how vertices move, not how the renderer fills space between two independently indexed panel boundaries. A zero-width analytic collision proxy also underestimated the visible MakeHuman side and seat surfaces.

### Prevention rule

Treat seam construction, collision calibration, and rendering continuity as separate requirements. Add bridge triangles or shared boundary topology for every visible seam, preserve the intended seam-allowance width, and calibrate asymmetric body collision against the actual rendered avatar from front, side, and back views.

### Verification

Let the cloth settle, rotate the avatar through a full turn, and inspect the neckline, armholes, side seams, waist seam, seat, thighs, and hem. Confirm no body surface appears through a closed garment and no seam disappears when viewed obliquely.

## Pattern-derived topology needs offline acceptance tests

### What happened

An arbitrary pattern compiler sampled cubic curves, triangulated the panels, refined the mesh, mapped named edges, and created sewing constraints. It compiled and launched, but the garment twisted, fell apart, and produced invalid surface geometry in the actual viewport.

### Root cause

The generic ear-clipped topology, naive panel placement, and seam direction logic replaced the stable visible solver before orientation, boundary closure, rest-state strain, and edge correspondence were proven independently.

### Prevention rule

Keep experimental geometry compilers isolated until automated checks prove polygon orientation, closed boundaries, nondegenerate triangles, manifold render surfaces, matching seam directions, bounded initial strain, and deterministic panel placement. Do not replace a stable runtime path based only on successful compilation.

### Verification

Run the compiler against convex, concave, curved, mirrored, and asymmetric pieces. Reject the document before simulation if any triangle is degenerate, any boundary is open, seam sample counts or directions disagree, or the initial constraint strain exceeds its defined threshold. Then complete a full-turn visual inspection before selecting the new path in the product viewport.

## Front-view cloth fit is not collision proof

### What happened

The restored six-panel garment looked stable from the front, but rotation exposed body poke-through at the upper back, seat, thigh, and leg. A broader mesh-derived collision envelope then split and distorted the dress, while a deeper analytic envelope destabilized the front drape.

### Root cause

The rendered human mesh and the analytic collision proxy were different shapes. Collision changes were tuned against one camera angle and applied to a solver whose pin and seam constraints were not robust enough to absorb the correction.

### Prevention rule

Use the same validated body surface, or a conservatively generated signed-distance representation of it, for rendering and cloth collision. Treat front, side, rear, and oblique views as mandatory acceptance angles. When local collision corrections destabilize unrelated panels, stop tuning the proxy and replace the simulation foundation.

### Verification

Settle the garment, inspect a full turn at multiple zoom levels, and run automated body-cloth penetration checks over every simulated vertex and triangle. Confirm collision changes do not increase seam strain, invert triangles, separate panels, or expose the body from any acceptance angle.

## Manual measurements must survive later estimation passes

### What happened

Detailed values were editable, but changing a linked baseline measurement later recalculated and replaced those detailed values. Manual entry existed in the interface without being a durable override.

### Root cause

Estimated and user-entered values shared one setter and the saved profile did not record their origin.

### Prevention rule

Track estimated and manual origins independently. Estimation may update only untouched values. Persist the override flag with the snapshot and include it in every downstream avatar or garment bridge document.

### Verification

Edit a detailed measurement, then change height, chest, waist, hip, shoulder, or torso while linked estimation is enabled. Confirm the edited value is unchanged, untouched values update, and the exported Unreal bridge marks the edited value as manual.

## A MetaHuman preview mesh is not a production runtime character

### What happened

The first native Unreal preview loaded exported body and head skeletal meshes directly. The silhouette was human, but the running scene showed a gray segmented body without the MetaHuman skin, eyes, teeth, groom, or assembled animation components.

### Root cause

The runtime integration treated editor preview meshes as the complete character. MetaHuman Character keeps its production materials, baked textures, groom bindings, face rig, body rig, physics asset, and actor component wiring in the generated assembly Blueprint.

### Prevention rule

Assemble the MetaHuman Character before runtime integration, save every generated package, and instantiate the generated Blueprint. Locate the assembled body component for cloth pose and collision instead of rendering an exported preview mesh as the avatar.

### Verification

Confirm the generated Blueprint, baked head and body textures, face and body meshes, physics asset, and groom assets exist on disk. Run the preview and inspect skin, eyes, teeth, hair, hands, feet, body animation, and garment collision from every acceptance angle.

## Measure the live Unreal body before calibrating garment placement

### What happened

The skirt became topologically continuous after its panel-axis correction, but the waistband still sat far outside the avatar from the side. The garment generator had been calibrated as though Unreal X were body depth and Y were body width.

### Root cause

The assembled MetaHuman uses X for body width, Y for forward depth, and Z for height. The stale first assembly measured near 92 cm at the garment's 103 cm support height. After correcting constraint persistence and regenerating body DNA, measured V2 is 80.61 cm at 103 cm and 71.21 cm at its actual 107 cm anatomical waist. The editable 103 cm outseam-derived height and anatomical waist height are related measurements, not interchangeable coordinates. Front-only visual checks hid most of that mismatch.

### Prevention rule

Log live skinned-mesh cross-sections at every garment support height before tuning panel placement or collision. Record the axis convention, center offset, width, depth, and circumference from the actual runtime mesh. Never infer them from a thumbnail, nominal body label, or static bounds.

### Verification

Run the avatar preview and compare logged X and Y extrema, cross-section center, ellipse circumference, and depth-to-width ratio against the Patterna measurements. Inspect the waistband from front, side, rear, and oblique views after every calibration change.

## Customize the source MetaHuman Character, not the assembled body mesh

### What happened

The assembled female body was realistic but did not respond to Patterna's measurements. Runtime inspection found no morph targets on the generated body mesh, so morph-target calls could not produce a custom avatar.

### Root cause

The optimized assembled body is generated output. MetaHuman's measurement-driven parametric state belongs to the source MetaHuman Character and must be changed through the Body Params constraints before the production character is assembled again.

### Prevention rule

Translate Patterna measurements into named MetaHuman body constraints, apply them through `MetaHumanCharacterEditorSubsystem`, commit the body state, save the source Character, and rebuild the optimized MetaHuman. Preserve a source Character backup before the first measurement-driven mutation. Keep Patterna's side-specific and surface controls because MetaHuman's symmetric constraint set represents only a subset of the full avatar specification.

### Verification

Export a Patterna bridge document, apply its body constraints, and inspect the generated constraint report for clamping or missing names. Reassemble the MetaHuman, run the live cross-section diagnostics, and confirm the waist, chest, hip, limb girths, and segment lengths move toward their requested values without losing production materials or rig components.

## Pattern ease and collision clearance must not be stacked blindly

### What happened

Adding radial dressing clearance on top of pattern ease pushed the simulated waistband away from the body and made its apparent fit worse. A broad linear cloth-weight transition also let too much of the support band drift.

### Root cause

Pattern ease, fabric collision thickness, body collision geometry, and radial dressing clearance all increased the same separation. The cloth weight map released vertices too quickly below the pinned edge, so the upper band could not preserve the intended support shape.

### Prevention rule

Let the 2D pattern document own circumference ease. Use calibrated collision thickness for physical separation and reserve dressing clearance for a proven solver need. Hold a shallow waistband zone, then use a steep nonlinear transition into the fully dynamic skirt.

### Verification

Inspect the generated manifest for pattern circumference, held-vertex counts, collision thickness, and weight falloff. Let the cloth settle and confirm the waistband stays close to the measured body while the lower skirt remains free to drape and form folds.

## A logged Unreal console command is not execution proof

### What happened

The editor log recorded a `py` command for the MetaHuman measurement script, but no stage report appeared and the source character did not change.

### Root cause

The project had not enabled Unreal's bundled `PythonScriptPlugin` or `EditorScriptingUtilities`. The console accepted and logged the text even though the Python execution environment was unavailable.

### Prevention rule

Declare editor automation plugins in the `.uproject`, verify their mount and Python initialization messages after startup, and run staged automation through Unreal's documented `-ExecutePythonScript` path when reproducible output and exit status matter.

### Verification

Confirm the log contains `Mounting Engine plugin PythonScriptPlugin`, `Python enabled`, and the script's own completion message. Require the expected machine-readable report on disk before treating a command as executed.

## MetaHuman assembly success is not package persistence

### What happened

The MetaHuman build API logged that assembly succeeded, but the assembled runtime body and Blueprint retained their earlier filesystem timestamps.

### Root cause

The build populated and dirtied generated packages in the editor process. The automation exited without explicitly saving those content packages, so the source Character persisted while the runtime assembly did not.

### Prevention rule

After programmatic MetaHuman assembly, save dirty content packages and verify that the expected assembled body package changed on disk. Preserve the original source backup across reruns and validate its recorded hash instead of requiring the already-customized source to remain byte-identical to its pre-mutation backup.

### Verification

Require `save_dirty_packages` to succeed, verify a newer assembled body modification time, record the assembled body SHA-256 in the report, restart the editor, and inspect the runtime avatar plus live cross-sections.

## Unreal reflected struct array entries must be reassigned

### What happened

The MetaHuman automation reported that 30 body constraints were applied, but reopening the source Character showed inactive default constraints and an unchanged waist.

### Root cause

Unreal Python returned reflected struct entries by value. The script mutated dictionary-held copies but passed the original unmodified array back to `set_body_constraints`.

### Prevention rule

After editing a reflected struct, assign the modified struct back to its array index before submitting the array. Immediately read the constraints back and verify the active flag and target value for every requested entry.

### Verification

Close and reopen the source MetaHuman Character in a new editor process. Require Height, Chest, Waist, High Hip, and Hip to remain active with their requested values before starting assembly.

## Constraint metadata is not geometric proof

### What happened

Constraint readback was correct, but the first optimized runtime assembly still measured roughly 87 cm where the requested waist should have been 71 cm.

### Root cause

The source Character's evaluated parametric mesh had the correct waist, but optimized assembly loaded stale body DNA and used it as the base mesh. Constraint metadata therefore described the intended state while generated body geometry preserved the older shape.

### Prevention rule

Regenerate the MetaHuman body rig and body DNA after body constraint changes, before optimized assembly. Treat a generated runtime cross-section, not constraint metadata or an assembly success message, as the fit proof.

### Verification

Measure the evaluated source body and the newly assembled runtime body at the same height bands. Require both to approach the requested circumference, and record the assembled body asset path and SHA-256 in the report.

## Assemble generated MetaHumans into a clean content root

### What happened

Repeated assembly over a loaded generated MetaHuman tree produced TextureGraph and rooted-object crashes.

### Root cause

The editor retained loaded objects from the previous generated assembly while the build attempted to replace packages at the same paths.

### Prevention rule

Write materially changed generated MetaHumans to a new, clean versioned content root. Preserve the previous root until the new assembly has been saved and validated.

### Verification

Confirm the new Blueprint, body mesh, physics asset, textures, and groom packages exist under the new root. Restart the editor, load only the new runtime Blueprint, and verify the body hash and live cross-sections.

## Physical fabric thickness is not a centimeter-scale collision shell

### What happened

The first correctly placed measured skirt looked like a glossy rubber lampshade with a large triangular tent and faceted highlights.

### Root cause

The repair pipeline forced a 2.0 cm collision shell onto 0.34 mm fabric, held only one waistband row, used large self-collision spheres, and rendered the relatively coarse simulation topology with a satin-like response. Solver logs were valid, but the visible result was physically implausible.

### Prevention rule

Keep collision margins proportional to fabric thickness and solver stability needs. Validate the held-band depth in physical centimeters, use enough simulation resolution for the garment scale, recalculate render normals, and calibrate roughness and specular response to the selected textile.

### Verification

Record the physical thickness, collision shell, held vertex count, simulation resolution, and self-collision radius. Inspect the settled garment for a smooth silhouette, distributed folds, a stable waistband, matte or glossy response appropriate to the fabric, and no body penetration from every acceptance angle.

## Generated cloth must preserve the editable pattern hem

### What happened

The first measured A-line skirt used the correct waist and center-front length but generated a straight horizontal rest hem. The editable Patterna skirt panel already had a balanced cubic hem, so the simulated side seams hung several centimeters below center front and formed implausible pointed corners.

### Root cause

The garment generator reduced the authoritative two-dimensional panel to a few scalar dimensions. It mapped vertical position with a uniform linear interpolation and ignored the panel's existing cubic hem profile.

### Prevention rule

Generate simulation rest geometry from the same named curves used by the two-dimensional editor. When a temporary profile adapter is unavoidable, record the exact curve profile and its dimensional consequences in the manifest, and add a regression check that prevents a straight-line substitute.

### How to verify

Confirm the manifest and verification report preserve the requested center length, the expected shorter side vertical length, and the cubic center, side, and control positions. Let the cloth settle and inspect the hem from front, side, rear, and oblique views for a balanced visual line without artificial side spikes.

## A character physics asset is not automatically a garment-fit collider

### What happened

The measured skirt looked acceptable from the front but the avatar's gray upper-body garment punched through both sides of the upper seat from the rear. The generated MetaHuman physics asset had a single large circular capsule on the pelvis and another on the lower torso, with no fitted boxes or convex surfaces in that region.

### Root cause

The runtime cloth source extracted only simple physics primitives. The oversized circular capsules did not match the avatar's elliptical, asymmetric waist and seat profile, and the visible body mesh used a single material slot, so the gray area could not be hidden as a separate clothing section.

### Prevention rule

Audit the exact primitive types that the runtime cloth collider consumes. Build garment collision from the live evaluated body surface or its measured cross-sections, keep it separate from the source character asset, and do not infer collision quality from an asset name or an editor thumbnail.

### How to verify

Log the source and runtime collision primitives and require the garment-only asset to replace the pelvis and lower-torso capsules with measured geometry while retaining limb collision. Then settle the cloth and inspect exact front, side, rear, and oblique views. The current six static acceptance captures show no visible body breakthrough after replacing the ellipse with an angular mesh-surface proxy. Animated poses and geometric penetration metrics remain separate required checks.

## Cross-section dimensions do not define the full waistband surface

### What happened

The surface-derived collision proxy removed the large body holes, but the held waistband still followed an ellipse. The avatar's tank remained visible below parts of the front edge and the upper rear skirt formed a broad artificial ridge.

### Root cause

Width, depth, center, and approximate circumference preserve useful body dimensions but discard lobes, local curvature, and front-to-back asymmetry. The garment's kinematic top row cannot be corrected by collision after simulation begins, so an intersecting elliptical dressing pose remains intersecting.

### Prevention rule

Retain an angular outer-surface profile at every garment support height. Interpolate those profiles vertically and angularly when constructing held or tightly constrained garment rows. Preserve the two-dimensional rest pattern separately so a realistic dressing pose does not rewrite the user's pattern measurements.

### How to verify

Require a minimum surface-point count per live profile section and record how many garment rows used measured surface geometry. Regenerate and reimport the cloth, then compare repeatable front, side, rear, and oblique captures. Confirm the waistband covers the body continuously and the seat drape no longer inherits an elliptical ridge.

## Full-body views cannot prove fabric microstructure

### What happened

The generated cotton-poplin normal and color textures were saved and connected successfully, but the full-body and first detail captures still looked uniformly smooth.

### Root cause

The first detail camera still framed almost the entire skirt. Physically small yarn variation was correctly removed by texture mip filtering at that distance, so the screenshot could not distinguish a working fabric shader from a flat one.

### Prevention rule

Validate silhouette, drape, and micro-material response at separate camera scales. Keep yarn-scale features physically restrained and improve the acceptance evidence before exaggerating a material merely to make it visible in a distant shot.

### How to verify

Capture a macro view close enough to resolve the woven repeat, while retaining the full-body views for garment shape. Confirm the weave follows the deformed pattern UVs without swimming, moire, or large painted-looking bands. Treat procedural texture evidence as appearance proof only, not physical fabric calibration.

## Regeneration can silently discard a valid detailed render mesh

### What happened

The generated USDA contained a 7,934-vertex render mesh with separate construction ribbons, but the saved cloth asset contained only the 7,154-vertex simulation topology. The repair command had reported success because it deliberately deleted every render LOD and rebuilt it from simulation geometry.

### Root cause

The repair step treated matching simulation and render counts as its validity condition. Unreal also legally collapsed the front and back render meshes into one render pattern while retaining two simulation patterns, so an early preservation check incorrectly rejected the imported render source.

### Prevention rule

Treat the imported Dataflow `ImportedCollection` override as the authoritative render source. Preserve any valid render collection with at least one render pattern and sufficient vertex and face coverage, even when render and simulation pattern counts differ. Use simulation-copy fallback only when the imported or current render data is missing or invalid.

### How to verify

Log simulation and render pattern, vertex, and face counts before and after Dataflow regeneration. Require LOD 0 to retain 7,934 render vertices and 14,592 faces, run the garment at runtime, and inspect full-body and macro views for deformation, floating geometry, tears, and construction-detail continuity.

## A packaged WinUI executable is not a standalone launch target

### What happened

The native project built successfully, but launching `Patterna.exe` directly from `bin` terminated with `REGDB_E_CLASSNOTREG` while activating the Windows App SDK runtime.

### Root cause

Patterna uses the packaged WinUI application model. Direct process launch bypassed the package-aware registration and identity setup performed by the project's WinApp run target.

### Prevention rule

Launch the development build with the documented `dotnet run --project .\Patternal\Patternal.csproj -p:Platform=x64 --no-build` command. Do not treat the executable under `bin` as a self-contained distribution.

### Verification

Confirm the command registers and opens the `Patterna` package window, then inspect that specific window instead of inferring success from a surviving process.

## A topology compiler is not a production cloth solver

### What happened

The document-driven browser path was enabled after its offline polygon and seam tests passed. In the actual 3D tab, the eight panels stretched across the avatar, folded through one another, and produced a visible `mesh integrity warning`.

### Root cause

The tests proved closed boundaries, deterministic sampling, positive triangles, and seam references. They did not prove three-dimensional arrangement, bounded initial strain, collision-safe dressing, seam correspondence under unequal sampling, or stable dynamic cloth. The browser avatar also exposed 145 editable values while only applying a subset through crude regional scaling, which made the presentation imply anatomical accuracy it did not have.

### Prevention rule

Keep the browser topology path diagnostic-only. Product-facing body and drape views must use the measured MetaHuman and Chaos Cloth pipeline. Never promote a solver based on topology tests alone, and never use the number of editable measurements as evidence that the rendered body maps all of them accurately.

### How to verify

Inspect the actual product 3D tab after a package-aware launch. It must not expose the MakeHuman or browser-cloth view. Verify that all seven Unreal acceptance captures are packaged, the view buttons select those captures, and `Open interactive 3D` starts the Patterna Unreal runtime. Continue to require animated-pose and geometric penetration acceptance before calling the Unreal drape production-ready.

## Visible pattern panels are not evidence of a sewable full garment

### What happened

The first complete wrap-dress preview showed giant cloth sheets stretched across unrelated body regions, folded through the avatar, and pulled into implausible spikes. Two waist-tie panels were visible in the pattern list but were not sewn into the garment.

### Root cause

The pipeline counted rendered panels without requiring every panel to participate in the seam graph. It also accepted a 27 percent waist mismatch, triangulated long irregular boundaries into poor ear-clipped triangles, placed panels independently, and handed deeply strained geometry to the dynamic solver.

### Prevention rule

Treat full-garment compilation as a strict gate. Require seam-graph participation, bounded seam-length mismatch, structured remeshing with named-edge preservation, continuous three-dimensional seam targets, initial body clearance, and an offline dressing relaxation before exporting cloth. Keep the result isolated until Unreal import and visual acceptance pass.

### How to verify

The current default wrap dress must compile as 8 panels and 11 named construction seams with explicit rejection when both tie seams are removed. The center-front wrap edges must remain free. Those topology checks are necessary but no longer sufficient. Separately verify Unreal's imported collection counts, closure state, static views, animated poses, and geometric penetration before switching the runtime asset.

## Zero seam gap before simulation can create an invalid garment

### What happened

The full garment compiler repeatedly improved seam-gap, edge-strain, and vertex-clearance numbers, but static Unreal captures still showed a rectangular bodice, crossed back, missing neckline, abdominal opening, and body-shaped hip holes.

### Root cause

The compiler averaged front and back seam positions, spread the displacement across whole panels, and then forced every sewn pair to a shared point before physics. Several shared points were inside the avatar. Radially projecting vertices back outside the torso did not stop triangles from crossing the body or panels from folding over themselves. The tests optimized the wrong proof boundary.

### Prevention rule

Do not pre-weld a garment into a zero-gap shell around a body. Stage separate panels outside the avatar with correct orientation and no intersections, preserve explicit sewing constraints, and let the cloth solver assemble them. Use Chaos Outfit Asset for source-body sizing and target-body resizing instead of a bespoke circumference warp.

### How to verify

Reject the source when any triangle intersects the body, any panel self-intersects, panel orientation flips, a seam correspondence twists, or the silhouette violates garment-specific bounds. Then prove sewing and drape in static and animated multi-angle captures. A saved Outfit Asset proves packaging and resizing metadata only; it does not prove garment quality.

## Interchange handedness can silently swap garment front and back

### What happened

The V5 garment assembled into one continuous dress, but the shallow back neckline appeared on the chest and the wrap opening appeared on the back.

### Root cause

The arrangement and measured body profile use Unreal's left-handed Z-up coordinates. The OpenUSD file declared right-handed Z-up coordinates but wrote Y unchanged. Unreal's USD importer performed its normal handedness conversion, which reflected the garment depth and swapped front with back.

### Prevention rule

Coordinate conversion belongs at the interchange boundary. Reflect Y and reverse triangle winding when exporting Unreal-space geometry to OpenUSD. Record the source, interchange, reflected axis, and winding conversion in the manifest.

### How to verify

Require the manifest to declare `Unreal left-handed Z-up`, `OpenUSD right-handed Z-up`, reflected axis `Y`, and reversed winding. Reimport the asset and confirm the wrap neckline faces the avatar's face while the back panel remains behind the torso.

## A wrap closure is not a construction seam

### What happened

After the permanent seams assembled correctly, the V6 wrap dress remained open and the two waist ties hung independently.

### Root cause

The garment document correctly attaches each tie to its bodice panel, but it has no knot, pin, buckle, hook, or temporary tack connecting the free tie ends. Chaos cannot infer that a designer intends to tie them. Sewing the two front edges together would produce a different garment and repeat the earlier false center-front seam.

### Prevention rule

Model closures as first-class constraints separate from permanent construction seams. A wrap garment must specify its closure state, attachment points, release behavior, and any user-created knot or pin.

### How to verify

Simulate both open and closed states from the same pattern. The open state must leave the wrap edges free. The closed state must retain the intended overlap and waist position without adding a permanent center-front seam.

## Offscreen wall time is not cloth simulation time

### What happened

The full-dress harness waited 12 wall-clock seconds before taking screenshots, but the expensive offscreen renderer produced only 45 game frames. The images showed permanent side seams still moving toward closure.

### Root cause

The harness accumulated frame delta time and treated it as proof that Chaos had received enough solver steps. Large render-frame deltas do not imply an equivalent number of stable cloth steps because Chaos clamps and substeps simulation work.

### Prevention rule

Gate repeatable cloth captures on an explicit minimum simulation-frame count. Record the final frame count, elapsed wall time, solver iterations, and substeps with the first capture.

### How to verify

The full-dress acceptance run must advance at least 600 game frames before its first screenshot. The log must contain `Patterna settled acceptance state` with the measured frame, wall-time, iteration, and substep values.

## Surface wrapping must remain strain-gated

### What happened

A proposed row-wise front-panel wrap reduced sewing distance but produced 293.5 percent peak edge strain and 1.696 cm of body penetration.

### Root cause

Changing the bend radius independently by remesh row created discontinuous motion between adjacent rows. The mapping looked geometrically plausible at individual rows but was not an isometry over the two-dimensional panel.

### Prevention rule

Allow only rigid transforms or globally continuous bends in the initial arrangement unless a deformation method proves bounded in-plane strain and body clearance. Never weaken the strain gate to admit a visually convenient staging shape.

### How to verify

Run the arrangement preflight before USD export. Reject any proposal that violates the existing peak-strain, percentile-strain, or measured-torso-clearance limits, then retain the last accepted geometry.

## Asset counts do not prove a usable cloth surface

### What happened

The fitted dress and the first imported shirt passed panel, triangle, seam, render-mesh, and saved-asset count checks. The fitted dress still tore across open dart geometry, while the shirt's subdivided proxy surface broke into visibly shredded triangular regions.

### Root cause

The validator proved that geometry existed, not that render vertices followed the final simulation particles continuously. The detailed render mesh crossed sewn panel boundaries, while proxy mappings selected different simulation neighborhoods on opposite sides of those boundaries. The fitted dress also entered simulation near 200 percent peak staged strain with unresolved same-panel darts.

### Prevention rule

Treat separate simulation and render meshes as an architectural option, not an automatic quality improvement. Reject garments with unresolved dart semantics or extreme peak strain. Require fresh proxy bindings after simulation remeshing, and use the final simulation surface as the diagnostic renderer until seam-aware render deformation passes visual comparison.

### How to verify

Capture front, side, rear, oblique, and macro views after at least 600 simulation frames. Reject disconnected fragments, triangular shredding, pinholes, and seam discontinuities even when topology counts pass. Compare the proxy-rendered and simulation-rendered versions of the same settled garment before enabling the detailed proxy in the product.

## Imported garments need anatomical landmark alignment before relaxation

### What happened

GarmentCode's authored shirt imported with zero staged seam gap and acceptable strain, but its upper edge entered Chaos near 132.7 cm and settled well below the avatar's shoulders. Moving the finished garment upward after relaxation raised broad strain to 29.5 percent because upper vertices were projected against a body profile that ends at 139 cm.

### Root cause

Source pattern translations are dataset staging coordinates, not Patterna anatomical landmarks. Applying a landmark correction after strain relaxation invalidated the relaxed state and forced neckline geometry against the final sampled torso section.

### Prevention rule

For complete imported upper-body garments, align the source assembly to the measured shoulder landmark before body wrapping, seam-frame alignment, and edge-strain relaxation. Keep the existing waist-landmark path for imported garments that contain skirt panels.

### How to verify

The imported eight-panel shirt must retain all 18 construction seams, place its highest arranged vertex at or above 138 cm after relaxation, keep 95th-percentile edge strain below 25 percent, and pass a fresh multi-angle cloth capture.

## A surrogate body cannot validate a body-specific garment

### What happened

Garment arrangement used measured cross-sections and a generic body while the runtime rendered a posed MetaHuman. The garment could pass clearance and topology checks yet still float, intersect, or deform around the wrong anatomy.

### Root cause

The generator, offline solver, runtime collision, and renderer did not share one evaluated body surface. Cross-sections preserved circumference but discarded local curvature, shoulder shape, breast shape, and front-to-back asymmetry.

### Prevention rule

Export the exact posed and skinned runtime body, repair its orientation, and derive the watertight simulation collider and body-specific segmentation from that same surface. Keep measurement editing upstream so regenerating the MetaHuman also regenerates garment inputs.

### How to verify

Record hashes and vertex counts for the live export, watertight collider, body YAML, segmentation, pattern specification, pre-fit mesh, manifest, and Unreal asset. Reject a run when any stage references a different body revision.

## Normalized cloth weights must be checked in physical units

### What happened

The upper support map appeared numerically soft, but normalized values were interpreted against a 100 cm maximum distance. Large upper panels could travel far enough to balloon, collapse, and look padded.

### Root cause

The code reviewed normalized map values without multiplying them by the Chaos node's physical range. A small normalized weight was not a small displacement.

### Prevention rule

Specify the intended support envelope in centimeters, log held, stabilized, and fully dynamic vertex counts, and inspect the conversion from normalized map value to physical maximum distance. Pre-fitted garments should use a shallow held band and a steep bounded transition rather than broad pseudo-pinning.

### How to verify

Log the top height, held-band depth, support depth, mapping curve, and physical distance represented by representative weights. Capture the same garment before and after simulation and reject large motion in regions intended only for local refinement.

## Garment edge stiffness is not Warp spring stiffness

### What happened

`garment_edge_ke` was temporarily set to 50,000 after confusing it with Warp's generic `spring_ke`. The garment appeared smoother but expanded drastically and reached more than 100 percent broad strain.

### Root cause

Two unrelated configuration fields used stiffness terminology and were treated as equivalent. GarmentCode's official mid and GUI configurations use `garment_edge_ke: 100.0`; 50,000 belongs to a different spring control.

### Prevention rule

Trace every solver parameter to the implementation and an official configuration before tuning it. Never accept visual smoothness when rest-length strain becomes physically impossible.

### How to verify

Record the chosen edge stiffness beside peak and 95th-percentile strain, body-contact rate, self-contact rate, and the rendered silhouette. Reject any tuning pass that improves one screenshot by expanding or shrinking the rest geometry.

## Pattern style selection is part of the physics architecture

### What happened

Several fitted-shirt variants increased body contacts, self contacts, and broad strain even as width was increased. The non-fitted crew-neck block produced the best bounded contact rates against the exact body.

### Root cause

A garment template encodes neckline, armhole, sleeve, ease, and seam relationships. Global width changes cannot correct a block whose construction assumptions do not match the target body and selected fabric.

### Prevention rule

Choose and regenerate a body-appropriate block before solver tuning. Evaluate pattern variants with the same body, material, resolution, and normalized gates. Keep the exact specification so the accepted geometry can be reproduced and edited.

### How to verify

Compare variants on body-contact rate, self-contact rate, peak strain, garment-wide 95th-percentile strain, worst-panel strain, and multi-angle appearance. Do not select a candidate from a front screenshot alone.

## Candidate search must score garment silhouette separately from physics

### What happened

The first accepted MPFB shirt had zero recorded collisions and bounded structural strain, but its torso was visibly boxy and its upper silhouette expanded toward the sleeves. The search ranked only collision and strain metrics, so a numerically stable but badly proportioned block could win.

### Root cause

Solver stability was treated as a proxy for design quality. The search had no target ease, centering, garment-length, or torso-silhouette objective.

### Prevention rule

Isolate torso panel components from sleeves, compare garment and segmented-body width and depth at multiple heights, score centering and length, and require both the physics gate and a visual-fit threshold. Keep rendered multi-angle review as the final independent gate.

### How to verify

Run the metric against the current loose production shirt and confirm it fails the visual-fit threshold despite passing the physics report. Search narrower regular and fitted blocks with a sewn neckline band, then render every physics-and-silhouette finalist from front, side, rear, oblique, and close material views.

## Source-specific seam identifiers need semantic translation

### What happened

Imported pattern seams could be numerically present while the compiler did not know which source interface represented a shoulder, armhole, sleeve, side, or center seam.

### Root cause

The compiler assumed one application's edge naming conventions were universal. GarmentCode stitch IDs and interface membership are source-specific.

### Prevention rule

Translate imported interfaces into Patterna's semantic seam graph at the adapter boundary. Preserve both the source identifier and stable Patterna identifier through remeshing, simulation, interchange, and editing.

### How to verify

Require every garment panel to participate in the expected semantic seam graph. Confirm that seam membership, direction, stitch counts, and source IDs survive a full Patterna-to-USD-to-Unreal round trip.

## Do not let a rejected runtime solver overwrite an accepted equilibrium

### What happened

The Warp pre-fit produced a continuous shirt with recognizable sleeves, neckline, and body drape. After 600 Chaos frames, the same mesh developed shoulder tabs and open underarm fragments. Reducing the Chaos maximum distance from 100 cm to 5 cm limited overall motion but did not repair the seam discontinuity.

### Root cause

The solver boundary preserved the panel and stitch counts but did not preserve a continuous sewn surface through the Chaos runtime handoff. This was a separate defect from the offline garment solve.

### Prevention rule

Treat each solver handoff as a new acceptance boundary. Keep the last visually and geometrically accepted equilibrium as the product default until the downstream solver passes the same seam, collision, and silhouette gates. Expose rejected refinement paths only through explicit diagnostic flags.

### How to verify

Capture the imported equilibrium and the post-refinement state from identical cameras. Reject the handoff when the refined state adds holes, tabs, fragments, penetration, or worse strain. The default shirt preview must remain on the accepted Warp equilibrium until `-PatternaEnableChaosRefinement` also passes.

## Display labels are not pattern-piece identity

### What happened

The point editor appeared to enter edit mode, but no handles were rendered and the numeric inspector remained disabled. The sidebar also listed a sleeve that did not exist in the active wrap-dress document.

### Root cause

Selection compared the display label `Bodice front` with the document name `Wrap bodice front`. Other sidebar rows were handwritten independently from the authoritative garment document. Presentation strings had become accidental primary keys.

### Prevention rule

Use stable document IDs for selection, history, seams, closures, persistence, and cross-view synchronization. Generate visible piece lists from the active garment document and resolve display names only at the UI boundary.

### How to verify

Launch the packaged application, select every listed piece, enter point editing, and confirm its anchors and Bézier controls appear. Select a handle and confirm exact coordinate fields become enabled. Switch garment documents and confirm every sidebar row corresponds to a real piece ID in the active document.

## A 2D and 3D garment mismatch is a product architecture failure

### What happened

The application showed a five-piece wrap dress in 2D while the 3D tab displayed an accepted eight-panel shirt. The shirt looked better than the rejected dress, but the two tabs did not describe one editable object.

### Root cause

The accepted Unreal asset and the WinUI sample document advanced on separate tracks. The viewport selected a fixed preview flag while the drafting canvas always generated a wrap dress. No product-level gate required source identity before presenting the pair.

### Prevention rule

Every accepted preview must record the authoritative garment source revision used to build it. The product should load that same source into the 2D editor by default. When a garment has no accepted equilibrium, block its product-facing 3D view with the failed gates instead of showing another garment or a rejected solve.

### How to verify

Confirm the default 2D document imports the eight pieces and sixteen seams from `PatternaFemaleAdaptiveCrewNeck.specification.json`, while the 3D tab identifies the accepted shirt equilibrium derived from that source. Switch to the wrap-dress prototype and confirm the 3D tab shows the bodice, waist, and strain rejection instead of a shirt image or V8 cloth capture.

## A successful WinUI build does not prove the registered AppX was refreshed

### What happened

The project DLL and resource index rebuilt successfully, but repeated packaged-app launches still showed the previous assembly overlay. The registered AppX directory contained older copies of `Patterna.dll` and `resources.pri`.

### Root cause

`dotnet build` updated the normal output directory but did not restage the already registered debug AppX directory. Launching the AUMID therefore exercised stale packaged binaries even though the compile was current.

### Prevention rule

Use the packaged `dotnet run` path, or an explicit package staging and registration step, before judging a WinUI UI change. Treat the registered AppX payload as a separate verification boundary from compilation.

### How to verify

Compare the timestamps and lengths of `Patterna.dll` and `resources.pri` in the normal output and `AppX` directories. Launch the exact Patterna AUMID only after those payloads match, then inspect the behavior in the real packaged window.

## A numerically similar pattern is not the same simulation source

### What happened

The first live regeneration path exported the visible 2D shirt back to GarmentCode, but Warp produced shifted panels, excessive self-collision, and rejected strain. The 2D round-trip tests passed because the normalized shapes looked equivalent. The actual solve did not.

### Root cause

Import normalized panel coordinates and discarded the original panel origin. The first correction restored the origin but still converted circular edges to cubic approximations. The next correction preserved the curves but dropped semantic `body` and `arm` panel labels. Even after those fixes, serializing negative zero as positive zero changed a triangulation branch by one vertex. That one-vertex topology drift changed the settled self-collision count from the accepted 11 contacts to as many as 108.

### Prevention rule

Treat source coordinate frames, numeric tokens, parametric curve definitions, semantic labels, interfaces, and seam identity as simulation data. Preserve untouched source byte-for-byte. When a user edit requires regeneration, preserve every unchanged source primitive and invalidate the old 3D revision before starting the job. Never infer simulation equivalence from a visually similar 2D round trip.

### How to verify

For untouched source, require identical SHA-256 hashes for the GarmentCode document and seam-aware mesh. For edited source, test origins, labels, curve types, control points, seam mappings, and deterministic export. Then run the actual Warp and compiler gates. The accepted packaged proof must settle 5,766 welded particles with 11 self contacts, pass preflight, write `simulation-job.json`, complete Unreal reimport, and expose only that accepted revision in the product 3D tab.

## Coordinate offsets are not a structural pattern editor

### What happened

The first 2D editor could move anchors and Bezier controls but stored every edit as an offset from generated points. It could not add an edge, split a curve, or preserve assembly references after a topology change.

### Root cause

The editing layer treated the generated boundary as fixed topology. Sewing, pins, closures, history, snapshots, and GarmentCode export all referenced those original edge IDs directly.

### Prevention rule

Represent topology changes as deterministic commands replayed over the current measurement-driven base. A boundary split must preserve the exact line or cubic shape, split a sewn partner at the same normalized arc length, replace every affected edge reference in order, and keep the result exportable to the simulation source.

### How to verify

Compare the original cubic against the two De Casteljau segments at repeated parameters, compile the edited seam chain, export both matched edge pairs to GarmentCode stitches, replay the command, and require an identical structural signature. Then verify undo, redo, save, restore, and later point edits against the structurally edited base.

## Construction anchors require stable boundary IDs across exchange formats

### What happened

The first Patterna construction-geometry extension exported a notch anchored to `seam-edge-a-a`, but GarmentCode reimport regenerated the same boundary as `edge-0`. Geometry validation correctly rejected the now-detached notch.

### Root cause

The extension preserved notch, dart, and internal-path records but omitted the stable boundary ID sequence those records referenced.

### Prevention rule

Any exchange format carrying topology-anchored construction data must carry the stable boundary IDs in boundary order. Restore those IDs before importing seams, notches, darts, or other references.

### How to verify

Export a pattern containing split boundary edges, a double notch, an internal fold path, and a locked grainline. Reimport it, require every original boundary ID and construction anchor to resolve, and run full garment validation.

## A plausible fit score is not fit evidence

### What happened

The inspector displayed a high fit score, chest ease, comfortable waist mobility, and low shoulder tension using formulas based on a few sliders. Those values were unrelated to the solved garment and could look authoritative beside a visibly unacceptable result.

### Root cause

Prototype presentation data survived after the product gained an accepted Warp report with actual collision and material-strain evidence.

### Prevention rule

Never present inferred fit quality as measured simulation evidence. Label unsolved revisions as unsimulated. For accepted revisions, display only values parsed from the exact revision report, including collision counts, peak strain, 95th-percentile strain, equilibrium frames, limits, and solver provenance.

### How to verify

Change any body, pattern, seam, or fabric input and confirm the evidence panel immediately returns to `Not simulated`. Load an accepted revision and confirm every displayed value equals its hashed `patterna_warp_prefit_report.json` value.

## A raw-edge block cannot become a finished garment through rendering

### What happened

The accepted production shirt contained eight torso and sleeve panels, sixteen stitches, no neck band, and no sleeve finishing. It also projected both sleeve ends upward by about 6.3 cm. Material shading could not hide the raw neckline, unfinished openings, or implausible sleeve silhouette.

### Root cause

Candidate selection treated the simplest GarmentCode shirt block as production construction and scored only torso collision and strain. It did not require finishing panels or measure sleeve hang.

### Prevention rule

Production candidates must contain explicit garment construction details before simulation. Require sewn neck and sleeve bands, record panel and stitch counts, measure left and right sleeve drop independently, and reject upward or asymmetric sleeves before visual review.

### How to verify

Generate the fitted finished-shirt configuration and require sixteen panels, 42 stitches, a nonzero neck-band depth, and a nonzero sleeve-band depth. Confirm the old eight-panel source fails the construction gate. Solve candidates and require both sleeve ends to fall toward the configured downward target within the independent sleeve-hang threshold.
## A thin material can look thick when the equilibrium and render surface are invalid

### What happened

The shirt used a 0.34 mm fabric source and a 0.08 cm Unreal collision envelope, yet the result looked heavy, thick, faceted, and anatomically implausible. Asset-count validation passed even though the close capture showed a raw neckline, broken shoulder balance, boxy torso, and shredded-looking sleeve and underarm surfaces. The Warp result contained 540 body intersections, 11 self intersections, 29.241 percent 95th-percentile strain, and 201.9 percent peak strain. A 600-frame Chaos run remained visually equivalent to the rest capture.

### Root cause

The pipeline treated file production and topology counts as stronger evidence than the actual equilibrium and rendered pixels. The detailed render surface used coarse midpoint subdivision and incomplete seam welding, while the source pattern and Warp equilibrium were already invalid. The customized GarmentCode Warp build was CPU-only, so the available RTX 4090 did not accelerate candidate search.

### Prevention rule

Require finite geometry, body and self-collision limits, peak edge strain, and 95th-percentile edge strain in the Warp report, compiler, and product artifact contract. Treat front, side, rear, oblique, and detail captures as a separate acceptance boundary. Do not promote a garment because it has many vertices or because a downstream solver completed. Record the selected compute device in every solve and use the GPU-enabled customized solver for systematic pattern search.

### How to verify

Confirm the current shirt is rejected before Unreal import or product display. A synthetic 100 percent edge stretch must fail both strain gates. Confirm the WinUI build accepts only reports with nonzero evaluated edge counts and finite measured values within their recorded limits. After rebuilding the customized Warp fork, verify that its report names the RTX device. Only promote a replacement shirt after collision, strain, neckline, shoulder, sleeve, silhouette, and multi-angle visual gates all pass.

## One garment pipeline cannot use three different bodies

### What happened

Pattern drafting, offline collision, compiler clearance, and product rendering used different approximations of the same measurement profile. Numeric checks could pass in one coordinate system while the garment floated, intersected, or appeared anatomically unrelated in another.

### Root cause

The application treated a measurement list as proof that independently generated meshes represented the same body. Circumference agreement did not preserve local curvature, front-to-back depth, shoulder shape, breast geometry, or landmark positions.

### Prevention rule

Generate one evaluated body surface and derive every downstream artifact from it. Record the body mesh hash in the body profile, segmentation, Warp report, compiler output, manifest, and product assets. Do not substitute a procedural preview body after simulation acceptance.

### How to verify

Require the MPFB mesh hash and 13,380 vertex topology throughout the pipeline. Confirm the compiler body profile contains 23 sampled sections from that mesh, the Warp report records 26,756 body faces, and the embedded renderer loads the same packaged OBJ.

## Seam constraints must not contaminate structural strain measurement

### What happened

Physically usable candidates were rejected because strain evaluation included edges directly adjacent to sewing constraints. Large seam travel was reported as material stretch even after the structural surface had settled.

### Root cause

The evaluator did not distinguish seam assembly displacement from warp, weft, and bias deformation. A garment could satisfy collision and equilibrium gates but fail a metric that measured a different physical relationship.

### Prevention rule

Evaluate structural strain on material edges while excluding seam-adjacent topology. Report the evaluated and excluded edge counts, and keep seam closure as its own gate.

### How to verify

The accepted report must record 21,711 evaluated structural edges, 1,897 excluded seam-adjacent edges, 21.035 percent peak strain, and 5.314 percent 95th-percentile strain. Synthetic structural stretching must still fail.

## Fabric provenance must be part of acceptance

### What happened

The pattern source declared one physical thickness while an otherwise valid Warp report could be generated from a different solver configuration. Topology and collision evidence alone did not prove the displayed result used the selected fabric.

### Root cause

The report schema recorded geometry metrics but did not bind them to a hashed solver configuration and explicit physical fabric values.

### Prevention rule

Every accepted solve must record the solver configuration path and SHA-256 hash plus thickness, density, friction, bending, area, and shear controls. The compiler must reject a report whose solver thickness differs from the garment source by more than 0.005 mm.

### How to verify

Confirm the production report uses schema `patterna.warp-prefit-report/2.1`, records 0.034 cm thickness, and matches the accepted garment source. Change the report thickness and confirm both the compiler and WinUI acceptance checks reject it.

## A renderer replacement is incomplete until the application calls it

### What happened

The exact MPFB body and accepted welded garment were packaged correctly, but the 3D tab stayed blank because `InitializeDrapeViewportAsync` existed without any caller. A successful build did not exercise the rendering lifecycle.

### Root cause

Asset integration was validated at file and compile boundaries without launching the packaged application and following the accepted baseline into the 3D tab.

### Prevention rule

Treat viewport initialization, accepted-revision selection, asset fetch, and visible pixels as separate integration gates. Provide a truthful production-image fallback until the interactive surface reports ready.

### How to verify

Launch through the packaged `dotnet run` path, confirm Patterna owns an `msedgewebview2` process, reset to the bundled baseline, open 3D, and verify the exact body and garment are visible. Change one measurement and confirm the prior equilibrium is hidden; restore the baseline and confirm it becomes available again without restarting.

## A bundled production result is not a live customization pipeline

### What happened

The app packaged an accepted MPFB body and Warp shirt, but the Simulate command still sent edited measurements through the retired MetaHuman body, a shared output directory, the CPU-oriented Python environment, and a mandatory Unreal import. The showcase improved while the user's core customization path remained architecturally stale.

### Root cause

The accepted baseline integration and the live revision pipeline were reviewed as one feature even though they had separate entry points, body identities, environments, output locations, and render handoffs.

### Prevention rule

Trace every user action from the visible command to its final pixels. A custom-body feature is incomplete unless a changed measurement creates a new body hash, collision surface, segmentation, solver configuration, equilibrium, compiled surface, and displayed revision without falling back to a bundled artifact.

### How to verify

Run one untouched baseline and one visibly different manual measurement profile. Confirm different revision, body, solver-config, cloth, USD, manifest, and render hashes; confirm the second result loads inside Patterna; then restore the first revision and confirm its immutable artifacts still load.

## Fabric controls must generate the solver configuration

### What happened

The UI could select silk, linen, wool, or edited physical values, while the live solver always read the bundled cotton configuration. Compiler thickness matching rejected some fabrics, but a matching default could still hide that most material controls never reached Warp.

### Root cause

The fabric document and solver YAML were parallel sources instead of one generated contract.

### Prevention rule

Generate a revision-specific solver configuration from the garment's thickness, areal mass, stretch, bend, and friction fields. Hash it in the solver report and keep the compiler's source-to-report checks.

### How to verify

Generate cotton and silk configurations in tests. Confirm the physical thickness conversion from millimeters to centimeters, friction, density, and stiffness values differ; run both through Warp and confirm each report records its own configuration hash and fabric values.

## Ease controls must close the loop on drafted geometry

### What happened

The first explicit ease implementation computed plausible chest, waist, and hip scale factors, but the requested 77 cm waist measured 101.26 cm in the resulting pattern. Repeating proportional corrections did not change the waist independently.

### Root cause

The imported shirt used long cubic boundary curves. Their control points did not coincide with the anatomical measurement planes, and the waist control location differed from the waist verification location. Whole-curve scaling therefore could not independently satisfy hip, waist, and chest targets.

### Prevention rule

Treat body plus ease as measured pattern constraints, not labels or assumed scale ratios. Insert exact structural anchors at the hip, waist, and chest planes, preserve the seam graph while splitting curves, and solve coupled drafting controls against measurements of the resulting geometry.

### How to verify

For a 92 cm chest, 71 cm waist, and 99 cm hip with 6 cm ease at each location, require the drafted pattern to measure 98 cm, 77 cm, and 105 cm within 0.2 cm. Change only waist ease to 10 cm and require an 81 cm waist while chest and hip remain unchanged. Validate the full garment document and require the original seam count to survive.

## A single maximum-strain gate is not a reliable cloth acceptance metric

### What happened

Candidate ranking overreacted to a handful of high-strain edges while failing to distinguish isolated local damage from broad garment distortion. Earlier candidates could look unusable despite a tolerable maximum, while a visually clean shirt could be rejected because one edge crossed the threshold.

### Root cause

Maximum strain is one order statistic. It is hypersensitive to a single discretization, seam-neighbor, or collision outlier and says nothing about how much of the garment is distorted.

### Prevention rule

Gate three independent regions of the strain distribution. Keep a peak limit for catastrophic failure, a 95th-percentile limit for broad distortion, and a 99.9th-percentile limit for concentrated local damage. Continue reporting the worst edge and its initial and final midpoint for diagnosis.

### How to verify

Require report schema `patterna.warp-prefit-report/2.2`. The current production candidate must pass 0.40 peak, 0.15 95th-percentile, and 0.29 99.9th-percentile limits with measured values 0.356368, 0.115722, and 0.278037. Change any one metric beyond its limit and confirm both compiler and WinUI acceptance reject the result.

## Packaged baseline validity must compare effective state

### What happened

The new 12-panel source appeared in 2D, but the 3D tab remained stale. A prior package layout still held older assets, old edit records invalidated an otherwise identical pattern, and the previous ease control minimum clamped the source hip ease from -10.68 cm to -6 cm.

### Root cause

The baseline check compared historical UI bookkeeping rather than the effective garment geometry and assembly. Asset-copy policy also allowed the debug AppX layout to preserve stale files, and the valid compression range in the data model did not match the NumberBox range.

### Prevention rule

Always copy production assets into build and publish layouts. Deploy through the packaged launch path before inspection. Compare canonical pattern, seam, closure, and ease signatures instead of edit-record counts. Keep ease validation and editor bounds identical, and migrate only recognized legacy default or clamped-source values.

### How to verify

The packaged 2D view must show 16 panels and 36 construction seams from source revision `fe7bbd68d5e4d01b844671546271701e070dc047438d44307e04015047e6425b`. The baseline must retain finite measured chest, waist, hip, and upper-arm ease from the source geometry, and confirming an unchanged detailed measurement must not invalidate the baseline. A real geometry or assembly edit still must hide the old cloth.

## Renderer asset units must be explicit at the boundary

### What happened

The packaged renderer accepted both OBJ files and showed the exact MPFB avatar, but the garment was invisible. Its coordinates were roughly one hundred times larger than the body and placed the shirt outside the camera frustum.

### Root cause

MPFB exports the body in meters while the Warp equilibrium OBJ is written in centimeters. The shared parser applied the meter conversion to both files, so successful fetch and parse messages falsely implied successful co-location.

### Prevention rule

Declare source units at every asset-loading call. Convert MPFB bodies from meters and Warp garments from centimeters into one scene scale before buffer creation. Do not infer display success from HTTP and syntax checks alone.

### How to verify

The production body must map from a 0 through 1.67 meter Y range to -1.67 through 1.67 scene units. The production garment must map from approximately 98 through 146 cm to 0.29 through 1.26 scene units. Parse the embedded JavaScript, confirm every production parser call supplies explicit units, then inspect the packaged front, side, rear, and oblique views when computer control is available.

## Positional record construction can silently swap physical fields

### What happened

The native pattern-piece factory passed seam allowance into the `ScaleX` constructor position and wrote a constant into `SeamAllowanceCm`. A one-centimeter test case concealed the defect because both values happened to be one, while other seam allowances distorted the drafted piece and were not preserved.

### Root cause

The `PatternPieceDocument` positional constructor contains adjacent `double` fields for scale and seam allowance. The factory call used the intended values in the wrong order, and the original tests checked boundary shape but not the physical-field mapping.

### Prevention rule

Whenever a positional record has adjacent values of the same primitive type, add direct field assertions at the construction boundary. Prefer named factories that expose physical units and keep geometry scale separate from construction metadata.

### How to verify

Create rectangle and ellipse pieces with different seam allowances. Require both geometry scales to remain exactly one, require each seam allowance to equal its requested centimeter value, then replay the piece through structural-command serialization and full garment validation.

## A print export cannot reuse viewport coordinates

### What happened

The original SVG declared a millimeter page but wrote WinUI canvas coordinates into its paths. A twelve-centimeter piece rendered as roughly forty-eight millimeters because the viewport's four-pixels-per-centimeter transform was interpreted as millimeters by the SVG.

### Root cause

The export lived inside `MainPage` and reused drawing helpers designed for screen placement, zoom, and labels. No test compared a known centimeter dimension with the resulting millimeter path coordinates.

### Prevention rule

Keep production exporters independent from viewport transforms. Convert document centimeters directly to physical millimeters, pack pieces in export space, and preserve construction identifiers and metadata in the output.

### How to verify

Export a twelve-by-eighteen-centimeter rectangle. Require its seam-line coordinates to span exactly 120 by 180 millimeters, require the SVG page height to follow the packed geometry, and require seam allowance, internal line, dart, notch, grainline, and metadata records to survive.

## A body can be labeled female while its generator is explicitly male

### What happened

Patterna reported and packaged an MPFB body as female, but the generated torso, shoulders, and overall silhouette read as male in every honest multi-angle render.

### Root cause

The generator hard-coded MPFB gender to 1.0. MPFB centers gender at 0.5, uses values below 0.5 for female, and values above 0.5 for male. The report repeated the intended label instead of recording and validating the effective macro value.

### Prevention rule

Treat generator parameters as evidence, not labels. Define the female macro in one tested constant, record its numeric value in every fit report, and compare front, side, rear, and oblique renders before promoting any avatar or garment pair.

### How to verify

Require the default MPFB gender macro to be below 0.5 and currently equal 0.0. Generate the exact body, require 13,380 vertices, 26,756 triangulated faces, accepted ruler tolerances, and a different body hash from the rejected male-macro artifact. Then inspect deterministic multi-angle renders before resimulating clothing.

## An editable measurement is not customization unless it changes the mesh

### What happened

The inspector exposed 145 detailed values, but most values were persisted only as metadata. Adjusting posture, asymmetry, surface depth, rises, arcs, hands, feet, head, or face controls could leave the generated body unchanged.

### Root cause

The UI measurement catalog and the MPFB fitting implementation evolved independently. The presence of a slider and a serialized number was mistaken for a body-shape capability.

### Prevention rule

Every built-in measurement must own an explicit driver lane: a hard physical ruler, a named anatomical morph target, a bounded local deformation, or a documented combination. Report coverage from the user-measurement section rather than counting internal GarmentCode aliases, and fail automated validation when a built-in key becomes unmapped.

### How to verify

Extract the 145 keys from the current WinUI catalog and require their set difference against all driver lanes to be empty. For every local control, move it away from default on a synthetic body and require nonzero affected vertices and displacement. Run a real non-neutral MPFB profile, require a changed body hash, no unmapped inputs, all hard rulers within 0.15 cm, and an accepted final surface.

## A waistband is not a substitute for a longer shirt block

### What happened

The first attempt to lengthen the cropped fitted shirt attached a fitted waistband below the torso. The solver could settle it, but the horizontal construction join gathered and flared like a peplum instead of continuing the shirt body.

### Root cause

Garment length was treated as an assembly problem instead of a drafting problem. Two separately shaped components with different circumferences were sewn together where a normal T-shirt has one continuous torso panel.

### Prevention rule

Use a continuous torso block for ordinary shirts and distribute chest, waist, and hip ease through that panel geometry. Reserve waistband components for garments that intentionally have a waistband or yoke. Visual candidate gates must evaluate the finished silhouette, not only collision and strain.

### How to verify

Require four continuous torso panels from neckline to hem, independent chest, waist, and hip ease values, a hem from 78 through 88 cm on the default body, and no waistband panel names. Inspect front, side, rear, and oblique renders. The accepted default must reach static equilibrium with zero self-collisions and remain within all three strain gates.

## USD import scale must not leak into the application OBJ contract

### What happened

The compiler authored centimeters in OpenUSD, but Blender imported the stage with an object scale of 0.01 for its meter-valued scene. Exporting that object directly produced meter-sized OBJ coordinates while the embedded renderer interpreted accepted revision garments as centimeters.

### Root cause

The direct Warp OBJ and the compiler-derived welded OBJ entered the same application loader through different unit paths. The exporter did not normalize the USD import transform back to the declared application units.

### Prevention rule

Keep the embedded garment OBJ contract in centimeters for both bundled and live revisions. When Blender imports the centimeter-authored USD stage, clear the import-time 0.01 object scale before OBJ export. Do not multiply the mesh data itself because the vertex values already contain centimeters.

### How to verify

Export a welded shirt and require its vertical coordinates to remain roughly 86 through 143, not 0.86 through 1.43 or 8,600 through 14,300. Load the exact OBJ beside the meter-valued MPFB body in the deterministic acceptance renderer and require the garment to align in all six views.

## Packaged camera labels and overlays are part of garment truth

### What happened

The accepted body and continuous shirt loaded together in the packaged app, but the Front command showed the anatomical rear, the Rear command showed the front, two evidence cards covered the head and upper torso, and a hard-coded label still reported 12 panels and 24 seams for a 16-panel, 36-seam garment. After correcting the view angles, a packaged pass also showed that camera commands could become no-ops when the handler assumed the object-typed XAML `Tag` value was always stored as a string.

### Root cause

The camera presets were named from the renderer's assumed axis instead of the MPFB surface's observed anatomical orientation. The event handler pattern-matched the object-typed `Tag` property to one runtime representation instead of normalizing its value. Product evidence was copied into XAML as presentation text instead of being read from the live garment document. Overlay placement was checked without the final avatar framing and inspector width.

### Prevention rule

Treat fixed cameras, topology labels, and evidence overlays as renderer contract data. Normalize object-typed command parameters before parsing them. Derive panel and seam counts from the displayed garment, define view angles against the anatomical front of the exact production body, and keep evidence cards outside the silhouette at the final packaged window size.

### How to verify

Launch the packaged application and capture Front, Right, Rear, Left, Oblique, and Fit view. Front must show the face and bust, Rear must show the back and seat, side labels must match the body side, and no card may cover the head, neckline, shoulder, sleeve, hem, hand, or foot. The overlay must report 16 pattern panels and 36 construction seams from the current garment document. Compare each packaged capture beside the corresponding deterministic acceptance render.

## Material lighting needs one explicit display-transfer contract

### What happened

A material-aware shader removed the plastic purple highlight but its first packaged pass washed the skin and cotton almost white.

### Root cause

The shader authored base colors in the renderer's existing display-valued convention, then added a tone-mapping curve and a second gamma transfer intended for linear high-dynamic-range input. Those stacked transfers lifted midtones far beyond the intended material colors.

### Prevention rule

Define whether shader inputs and the framebuffer are linear or display-valued before adding tone mapping. Do not add a transfer curve because it is associated with physically based rendering. Keep roughness, diffuse balance, micro-surface response, and color transfer as separate concerns.

### How to verify

Build the packaged app and inspect skin and every fabric preset under the same fixed front-oblique camera. Cotton must retain its authored hue, broad folds must remain readable, skin must retain warm midtone contrast, and neither material may clip toward white across most front-facing triangles. Compare the packaged capture beside the accepted reference before promotion.

## Anatomical ease targets cannot be inferred from fixed panel-height percentages

### What happened

The application reported negative or implausible garment ease even when the authored pattern requested 6 cm chest ease, 6 cm waist ease, and 8 cm hip ease. It sampled fixed vertical fractions of each torso panel, placing the chest sample below the actual chest plane and treating the upper-shirt hem as a full-hip measurement.

### Root cause

The importer discarded GarmentCode's authored design semantics and reconstructed named measurements from geometry with fixed fractional positions. Those fractions were not stable across shirt length, body proportions, or continuous torso shaping.

### Prevention rule

Preserve authored `patterna.design` or `patterna.ease_profile` values in the garment document and use them for named draft targets. Keep direct geometric sampling as a separate calibration tool for grading and solver validation. Never present a geometrically sampled upper-hip section as a semantic full-hip target.

### How to verify

Import the production source and require source ease of 6 cm chest, 6 cm waist, and 8 cm hip. The packaged inspector must show draft targets of 98 cm, 77 cm, and 107 cm for the 92 cm, 71 cm, and 99 cm body. Geometry calibration tests must continue to call the explicitly named geometry-sampling API.

## Bounded body contacts are not acceptable when a garment visibly breaks through skin

### What happened

The prior shirt passed a numeric allowance of several body contacts, but two symmetric upper-torso crossings appeared as skin-colored breakthrough in the packaged view. Small counts still produced a visibly impossible garment.

### Root cause

Candidate acceptance optimized strain and silhouette while permitting a nonzero final body-collision count. The 0.15 cm collision envelope was too thin at the upper torso for the current mesh resolution and equilibrium.

### Prevention rule

Require zero final body intersections for production candidates. Diagnose exact cloth-edge and avatar-triangle crossings, then adjust the collision envelope or pattern architecture and rerun the solver. Do not conceal intersections with material, camera, or renderer changes.

### How to verify

The accepted CUDA report must record 0 body intersections and 0 self intersections with a 0.30 cm collision envelope. Run the independent edge-triangle diagnostic against the final OBJ pair and require zero crossings. Inspect front, rear, side, and oblique renders for skin breakthrough before promotion.

## A bundled accepted surface must carry its exact fit evidence into the product

### What happened

The packaged viewport correctly displayed the accepted zero-contact garment and labeled it as current, while the inspector simultaneously said `Not simulated` and showed `No evidence` for every metric.

### Root cause

The viewport had an explicit bundled-baseline path, but the inspector searched only revision-specific jobs in local application data. The accepted production report was not packaged beside the surface, so two UI paths disagreed about the same displayed artifact.

### Prevention rule

Treat geometry and fit evidence as one accepted product artifact. Package the exact Warp report beside the bundled surface, parse it through the same report validator as live jobs, and expose it only while canonical body, pattern, assembly, ease, and fabric inputs still match the baseline.

### How to verify

Build without resource warnings and require the packaged fit report to contain schema 2.2 evidence with 223 frames, 0 body intersections, and 0 self intersections. Launch the packaged baseline and confirm the viewport says accepted while the inspector reports the same frames, strain metrics, and intersection counts. Change one source input and confirm both cloth and bundled evidence become stale together.

## A collision body is not a complete display avatar

### What happened

The accepted cloth finally fit the correct MPFB surface, but the person still looked synthetic because the packaged body OBJ contained only positions and faces. It had no UV coordinates, skin texture, eyes, teeth, brows, lashes, or hair. Procedural color noise and flat shading could not replace those missing assets.

### Root cause

The first MPFB exporter intentionally stripped the human down to the watertight body group needed by the collision solver. The product renderer then reused that engineering collider as if it were a complete visual character. Simulation identity and presentation detail were treated as the same mesh contract.

### Prevention rule

Keep one exact collision surface as the fit authority, but generate a separate display package from the same evaluated coordinates. Preserve stable body topology and UVs, fit real MakeHuman visual assets to that body, and store every custom revision's display package beside its collider and cloth. Never reuse bundled hair or facial geometry for a different measured body. Hide stale cloth as soon as any source input changes.

### How to verify

Require the display manifest to contain body, eyes, teeth, eyebrows, eyelashes, and hair with valid OBJ vertex and UV references plus PNG textures. Require the display body to retain 13,380 source vertices and 167 cm height. In the packaged app, inspect front and oblique views for textured skin and real facial geometry, then change a body measurement and confirm the old cloth and all accepted evidence disappear immediately.

## A detailed cloth shader cannot recover pattern data discarded by the render handoff

### What happened

The accepted garment was thin and topologically coherent, but it still looked like a flat blue shell. The compiler had valid face-varying pattern UVs in OpenUSD, while the OBJ displayed by the product had no `vt` records and no construction paths. The renderer compensated with world-space sine bands that did not follow panels, grain, or seams.

### Root cause

The runtime exported its garment OBJ through a separate Blender conversion step. That step copied welded positions and faces but discarded the compiler's panel UVs and sewing semantics. The embedded parser also ignored OBJ texture coordinates and line groups. Material tweaking was therefore operating after the required design data had already been lost.

### Prevention rule

Export every product-facing garment representation from the same accepted compiler surface. Preserve face-varying UV corners even when panel seams share welded positions, export real construction seams and finished boundaries as named groups, hash the renderer artifact, and reject accepted caches that predate that contract. A cloth renderer may enhance authoritative data, but it must not invent pattern-space structure after interchange.

### How to verify

Require the accepted baseline OBJ to contain 30,362 surface vertices, 180,936 texture coordinates, 60,312 faces, `g patterna_seams`, and `g patterna_edges`. Require 36 construction-seam strips and 12 open finished edges in the manifest. Launch through the package-aware path, confirm the HUD reports surface vertices and UV corners, then inspect front and oblique views for weave that follows the panels and construction lines that remain attached to the cloth.

## Visual verification must prove the registered AppX payload, not only the build output

### What happened

The rebuilt project passed compilation, but the first live inspection still displayed the previous garment label and geometry. The normal output directory contained the current UV-aware viewport and seven-megabyte OBJ, while the registered debug AppX contained older copies and no fabric image.

### Root cause

The verification launcher activated the registered AUMID directly. A normal `dotnet build` refreshed the output directory but did not invoke the WinApp loose-layout content staging target. The existing AppX registration therefore pointed at a valid but stale payload.

### Prevention rule

Treat compiler output, normal application output, and the registered loose AppX as separate proof boundaries. Use package-aware `dotnet run`, or explicitly invoke `_WinAppCopyContentToLooseLayout`, before visual inspection. Compare hashes for every asset whose pixels matter.

### How to verify

Compare SHA-256 hashes for `avatar3d.html`, the accepted garment OBJ, and the fabric texture between the normal output and `AppX` directories. Require exact matches before AUMID activation. In the live 3D tab, require the current HUD text with both 30,362 surface vertices and 180,936 UV corners instead of accepting a visually similar window as proof.

## A generic WebGL image upload is not a glTF texture loader

### What happened

The fitted Antonia candidate looked coherent in Blender but appeared dark, patchy, and stitched from incompatible skin regions in the packaged application. Anatomical texture details appeared on the wrong surfaces, and hard boundaries were visible between the head, arms, torso, and legs.

### Root cause

The custom WebGL loader applied `UNPACK_FLIP_Y_WEBGL` to every image. glTF defines texture coordinate `(0, 0)` at the upper-left image pixel, so this extra flip vertically inverted every embedded albedo texture. The shader also performed lighting directly on sRGB albedo samples and left browser image color conversion implicit.

### Prevention rule

Keep generic OBJ texture upload and glTF base-color upload as explicit separate contracts. Do not vertically flip glTF images. Ignore embedded image color-profile conversion for glTF, decode base-color samples from sRGB before lighting, and encode the lit result to sRGB exactly once. Do not apply that transfer to procedural display colors or grayscale fabric-relief samples.

### How to verify

Build and register the exact packaged payload, then inspect Front, Right, Rear, Left, Oblique, and Fit views. Facial features, nipples, navel, hands, feet, and limb detail must appear on the correct anatomy; the head, arm, torso, and leg boundaries must remain visually continuous. Run every 2D authoring, camera, toggle, and slider check afterward so the renderer correction does not hide an interaction regression.

## Symmetric drafting helpers are not always valid production cutting pieces

### What happened

The accepted shirt passed collision and strain gates but still showed artificial center-front and center-back construction lines. GarmentCode's shirt helper created four torso halves and stitched the two front halves and two back halves together. That symmetry strategy was convenient for generation, but it did not describe the normal uninterrupted front and back cutting pieces of the displayed tee.

### Root cause

The production pipeline treated the generator's component boundaries as intentional garment construction. Joining the half panels naively also retained redundant center-hem vertices and two circular front-neck arcs whose independent tessellation crossed near center front, producing a 13.75:1 sliver triangle.

### Prevention rule

Separate generator decomposition from production construction semantics. For symmetric tee blocks, join mirrored torso halves before meshing, remove their center stitches, collapse collinear center-hem vertices, remap every surviving stitch edge, and replace the joined front neckline with symmetric cubic segments that preserve the original collar length. Do not weaken mesh-quality limits to accommodate redundant construction.

### How to verify

Require `front_torso` and `back_torso` with no left or right torso-half pieces. Require 14 panels, 34 construction seams, a maximum pattern-mesh triangle aspect ratio below 12:1, and a compiler manifest with 34 seam paths and 10 finished open edges. The collision-driven pose report must record completed body animation, static equilibrium, 0 body intersections, 0 self intersections, and all three strain metrics below their declared limits. The packaged OBJ must contain no artificial center-front or center-back seam strip.

## Product visual proofs must honor each asset's coordinate contract

### What happened

The first exact product turntable rendered a floating shirt while the textured avatar lay horizontally on the studio floor. After correcting the avatar axis, the first registration validator still measured the centimeter garment at one hundred times its rendered size because Blender had not refreshed the object transform matrix before the bounds check.

### Root cause

The display-avatar OBJs use Blender meters with Z up, while the accepted Warp garment uses centimeters with Y up. The proof renderer initially imported every OBJ through one default axis path and then inspected a stale transform matrix.

### Prevention rule

Declare source units and axes at every product-asset boundary. Import display-avatar assets as Z-up Blender meters and the accepted garment as Y-up centimeters, refresh the evaluated scene after applying scale, and require body-to-garment bounds and overlap to pass before producing visual evidence.

### How to verify

Run the deterministic six-view product renderer and require an accepted registration record, at least 0.45 meter vertical body-to-garment overlap, no more than 0.04 meter left-right offset, and no more than 0.25 meter front-back offset. Require six distinct 720 by 900 PNGs whose hashes match the proof manifest and whose asset hashes match the exact packaged avatar, garment, and fabric sources.

## Cloth simulation meshes and product render surfaces need different refinement contracts

### What happened

The CUDA cloth result passed contact, self-contact, strain, and silhouette gates, but its product render retained sharp triangle-frequency underarm pinches and stacked back-waist ridges. Increasing physical bending stiffness by two and four times produced nearly identical six-view results and slightly worse peak strain, so material tuning did not address the visible defect.

### Root cause

The compiler called its output an independent render surface but only split each triangle at linear midpoints. It increased polygon count without changing the simulated vertex positions or filtering mesh-frequency artifacts. The simulation and display meshes therefore had different names but effectively shared the same geometric noise.

### Prevention rule

Keep the accepted simulation mesh immutable and derive a separate display surface through an explicit, bounded refinement contract. Protect finished boundaries and non-manifold topology, preserve face-varying pattern UVs, record every displacement metric, and reject the display surface if independent body-intersection analysis fails. Do not change fabric physics to compensate for a render-handoff defect.

### How to verify

Compare the old midpoint output, Loop-only output, and fairing plus Loop output with the same six cameras. Require all finished-boundary base vertices to remain unchanged, maximum base displacement no greater than 0.75 cm, deterministic OBJ hashes, 34 construction lines, 10 open boundaries, and zero cloth-edge crossings against the exact simulation body. The accepted relaxed production surface should report 207 protected boundary vertices, 0 protected non-manifold vertices, approximately 0.116 cm average displacement, and approximately 0.451 cm maximum displacement.

## A pose validator must measure the entire cloth surface

### What happened

The old dressed-garment pose stage reported effectively zero transfer strain, but the following Warp resettle exploded to 181 body intersections, 2,914 self intersections, and 744.1 percent peak strain. Measuring every edge in the staged garment exposed 1,157.98 percent actual peak transfer strain.

### Root cause

The pose script rigidly rotated complete sleeve panels and then excluded all 2,238 edges touching stitch vertices from its strain check. The exclusion hid the exact seam-adjacent damage created by teleporting an already draped garment into a new body pose.

### Prevention rule

Validate pose transfer across the entire cloth surface, including every seam-adjacent edge. Do not teleport accepted cloth into a posed state. Preserve its exact accepted rest geometry, pattern spring lengths, and strain-reference mesh while moving the collision body smoothly through the cloth, then allow unconstrained resettling.

### How to verify

The legacy rigid transfer must fail whole-surface validation. The collision-driven 12-degree body animation must complete all 180 animation frames and reach static equilibrium. The full production proof completes in 375 frames with 0 body intersections, 0 self intersections, 39.990 percent peak strain, 7.895 percent 95th-percentile strain, and 25.214 percent 99.9th-percentile strain. Cache validation must prove that the staged cloth is byte-identical to the accepted rest garment and that both body endpoints and original strain inputs are hashed.

## Pose the dressed system, not the naked collider alone

### What happened

Lowering the avatar arms before constructing the shirt forced the rest-pose sleeves through the already posed arms. Warp reached equilibrium, but the result still had 76 body intersections, 174.669 percent peak edge strain, and 78.391 percent 99.9th-percentile strain concentrated at a sleeve.

### Root cause

The body pose and garment construction state used different coordinate histories. The body was already relaxed while the sewn garment still began in its wide-arm rest arrangement. Local pattern edits and solver tuning could not remove that initial topological conflict.

### Prevention rule

Dress and accept the garment on the measured rest-pose body first. Keep that accepted cloth fixed while the collision body moves smoothly from its rest pose to the target pose, then resettle the dressed pair. Preserve the original GarmentCode edge-length pickle and box mesh so staging cannot redefine a strained garment as stress-free.

### How to verify

Require whole-surface validation for any diagnostic pose transfer. Require the second Warp report to hash the unchanged staged initial mesh, animation-start body, final body, original rest lengths, and original strain reference, and to record completed kinematic animation. The promoted result must reach static equilibrium with zero body and self intersections and all three strain metrics below their recorded limits. Run the independent refined-surface crossing diagnostic against the posed collision body and require zero crossings.

## Sleeve circumference grading must preserve the cap and distribute spread in material coordinates

### What happened

Scaling sleeve panels as generic body regions widened the cuff but also distorted the cap, broke sewn-edge compatibility, and initialized sharp folds around the armhole. Small coordinate fixes changed isolated symptoms without producing a stable custom-measurement solve.

### Root cause

The grader treated sleeve width as an axis-aligned panel scale. It did not measure the actual sewn sleeve opening, distinguish the cuff from the cap, or distribute the requested circumference change continuously along the sleeve's own axis. Near-straight generated cubics were also subdivided too aggressively, creating weak triangles around the edited boundary.

### Prevention rule

Measure sleeve opening circumference from the current sewn sleeve and cuff geometry. Apply constrained continuous slash-and-spread: give the cuff the full change, ease intermediate points with a smooth material-coordinate function, rotate cap boundary curves rigidly, and explicitly match the front and back sleeve seams. Tessellate cubics from curvature and maximum segment length instead of their generated status. Reject self-intersecting authored boundaries before meshing.

### How to verify

For the 94 cm chest custom profile, require a 34.4 cm sleeve opening within 0.1 cm, cap-arc drift below 0.02 cm, and every material seam longer than 2 cm below 0.5 percent mismatch. Require production grading to commit geometry and reset panel scales to 1. Confirm all authored panels are simple and the topology suite remains accepted.

## Multi-way seam placement must not depend on stitch order

### What happened

Several panels meeting at one sewn junction could receive visibly different initial positions when the same relationships were enumerated in another order. Repeated local changes did not reliably remove the fold because the shared junction itself moved with traversal order.

### Root cause

GarmentCode merged each new stitch endpoint into the existing junction with a repeated 50/50 average. That is not the centroid of all participating vertices, so later endpoints received more influence than earlier endpoints.

### Prevention rule

Track the number of source vertices represented by every merged seam junction and compute a true weighted centroid whenever groups join. Never use repeated pairwise means for a multi-way construction point.

### How to verify

Run the seam-centroid regression with different stitch orders and require identical junction positions equal to the arithmetic mean of every participating local vertex.

## Collision contacts must be refreshed at every integration substep

### What happened

The solver could report late self-intersections even with ten configured substeps. Increasing the number of substeps or constraint iterations without changing collision refresh made some results materially worse.

### Root cause

Warp built body and self-collision contacts once per rendered frame and reused that stale set for every integration substep. Cloth could move through a surface after the contact set was created. Contact capacity was also invisible, so an exhausted buffer could resemble a clean solve.

### Prevention rule

Run collision detection inside every integration substep using the substep duration. Record substeps, observed edge contacts, contact capacity, and saturation in the immutable report. Reject saturated buffers. Do not assume that more substeps or solver iterations improve a system whose contacts are stale.

### How to verify

Use a mocked four-substep solve and require four collision refresh calls. For schema 2.3 product proofs, require at least ten substeps, a positive contact capacity, observed contacts below capacity, no saturation, and zero final body and self-collisions.

## One immutable solver report must govern every downstream acceptance decision

### What happened

Warp accepted an exact equilibrium with zero collisions and 34.0 percent isolated peak strain under its recorded 40 percent limit. The compiler rejected the same positions twice: first through an analytical preview-body clearance heuristic, then through a separately recomputed 29.2 percent strain limit. A later end-to-end attempt still failed because the runtime selected an older Debug compiler merely because it appeared first in a path list.

### Root cause

Downstream preflight duplicated solver policy instead of consuming the exact report contract. The runtime also treated build configuration order as freshness, so source corrections could be bypassed by a stale executable.

### Prevention rule

When schema, hashes, finite-state, equilibrium, collision, strain, and contact-capacity fields validate, treat the immutable Warp report as authoritative for the solved surface. Use its recorded strain limits within fixed compiler safety ceilings. Do not let an analytical preview profile overrule exact zero-collision evidence. When multiple local compiler builds exist, select the assembly with the newest build timestamp.

### How to verify

Run the complete non-default measurement pipeline from a fresh product-proof root. Require Warp, compiler preflight, and product manifest acceptance for the same revision. The accepted proof must emit OpenUSD, welded render OBJ, compiler manifest, and product manifest, and must retain zero body collisions, zero self-collisions, unsaturated contact storage, and all three strain metrics within the report's recorded limits.

## Display avatars and collision bodies must share one floor datum

### What happened

The exact cloth equilibrium was shaped like a recognizable shirt, but the live product view made it look like a giant bib, cape, and skirt around the wrong parts of the body. The revision-specific display avatar stood 20.66 cm above the collision body used by Warp, so every garment comparison was vertically misregistered even though the garment itself was in the correct solver coordinates.

### Root cause

The MPFB display package preserved Blender's source world origin, whose lowest body vertex was at 0.206631556 m. The GarmentCode collision conversion explicitly translated its lowest vertex to height zero. The renderer declared units and axes but did not declare or normalize the origin, so two artifacts derived from the same evaluated body surface still used different floor datums.

### Prevention rule

Record the display body's source floor offset in its manifest. Normalize the body, eyes, teeth, brows, lashes, and hair by that same offset at every loading boundary. For older manifests, derive the offset from the display body instead of assuming zero. Keep body-aware garment staging experimental unless its own preflight passes; a rejected starting shell must never replace an accepted production solve.

### How to verify

Load a custom display package whose body minimum is 0.206631556 m and require the registered display bounds to start at zero while retaining a 1.67 m height. Render the unchanged accepted garment before and after normalization and require the corrected shirt to cover the torso and sleeves instead of the abdomen and legs. Regenerate the six-view product proof, require its current manifest hash, and require the display-avatar and product-acceptance suites to pass.

## Bust-dart intake must exist in the drafted boundary before the dart is closed

### What happened

The physical-dart compiler could close an equal-leg dart and divide an existing side seam, but it correctly rejected a normal production shirt block whose front and back seam lengths were already matched. Cutting a mouth out of that unchanged boundary would shorten the front seam and create a mismatch instead of producing real bust volume.

### Root cause

Dart closure and fullness generation were treated as the same operation. A closure compiler can materialize authored intake, but it cannot create the additional pattern length required by three-dimensional bust projection. The imported GarmentCode panels were also normalized to local origins, so using the sign of a panel coordinate to label left and right selected the wrong seam on some pieces.

### Prevention rule

Generate the measured intake in the editable source boundary before physical-dart materialization. Discover left and right relative to the panel centerline, not the coordinate origin. Locate mouths and matching splits by physical arc length, project the apex onto the mouth perpendicular bisector for equal legs, and require the resulting external seam spans to match before simulation.

### How to verify

Apply asymmetric measured intake to the accepted full-front shirt and require separate left and right source darts. Compile both and require two dart closures plus four divided side-seam spans, every bust-related seam below one percent mismatch, positive front-panel triangles, a changed structural signature when any profile field changes, and exact profile preservation through GarmentCode export/import.

## Explicit exchange mappings must evolve with profile extensions

### What happened

The in-memory bust profile gained shoulder-mouth and multi-dart distribution fields. Revision hashing saw them automatically, but the first GarmentCode round trip silently restored their defaults instead of the edited values.

### Root cause

The exchange bridge writes named JSON properties explicitly. Adding init-only properties to the C# record did not update that separate mapping, so record equality and structural hashing covered fields that the interchange format omitted.

### Prevention rule

When a persisted model gains a field, audit every explicit serializer, importer, saved-settings path, snapshot, structural hash, and UI restore path. New exchange fields should import with documented defaults for older files and reject present but non-finite values.

### How to verify

Use a non-default distributed-dart profile, export it through GarmentCode, import it again, and require complete record equality including shoulder mouth offset and shoulder share. Keep the older side-dart round trip to prove backward-compatible defaults.

## Approximate shell clearance is not exact body-collision proof

### What happened

The body-aware sewn-shell proposal passed its analytical arrangement preflight but began the exact Warp solve with 1,820 body intersections, 1,658 self-intersections, and 3,549 of 8,664 welded garment vertices inside the measured body. The same compiled garment in its authored GarmentCode placement began with 122 body crossings and 307 self-crossings, then reached an accepted zero-intersection equilibrium.

### Root cause

The shell compiler sampled a limited torso profile, extended that profile outside its measured height range, and folded sleeve panels around torso depth instead of registering them to the posed arms. Its approximate clearance score therefore measured a different geometric problem from the exact triangle collider used by Warp.

### Prevention rule

Treat imported GarmentCode panel transforms as authoritative source geometry. A heuristic sewn-shell may be proposed only for generated garments that have no complete source placement, and may enter production only after the exact body collider and self-collision diagnostics validate it. Record initial collision locations by panel in the immutable solver report so a false-positive arranger cannot hide behind one aggregate clearance number.

### How to verify

Run a zero-frame exact collision diagnostic for both the proposed shell and authored source placement. Require the report to include initial body and self-intersection counts plus labeled body-intersection locations. For an imported garment with complete source transforms, require the simulation pipeline to omit the shell override even when the analytical shell preflight reports acceptance.

## Static velocity is not physical equilibrium

### What happened

A source-placement solve reached the solver's velocity threshold at frame 217 while seven self-intersections remained and peak structural strain was 41.21 percent. Stopping at that point rejected an otherwise recoverable simulation. With collision and strain gates included in the stopping condition, the same garment continued settling and accepted at frame 215 in a subsequent deterministic proof run with zero body intersections, zero self-intersections, 38.51 percent peak strain, 5.82 percent 95th-percentile strain, and 21.31 percent 99.9th-percentile strain.

### Root cause

The early-stop condition treated low particle velocity as equivalent to an acceptable cloth state. Collision topology and structural strain can remain outside their limits after visible motion becomes small.

### Prevention rule

Use velocity only as a signal to evaluate a candidate equilibrium. Stop only when the exact body-intersection, self-intersection, peak-strain, 95th-percentile-strain, and 99.9th-percentile-strain gates all pass. If any physical gate fails, continue simulation and log the outstanding reasons.

### How to verify

Unit-test a velocity-static candidate with seven self-intersections, one with 41.2 percent peak strain, and one with all physical metrics under their limits. The first two must continue settling and only the third may set `static_equilibrium_reached`.

## A numerically accepted garment can still have the wrong drape architecture

### What happened

The packaged shirt had valid source hashes, zero Warp body and self intersections, bounded structural strain, and a continuous render surface. It still looked rigid and synthetic because the accepted surface preserved a box-like torso silhouette, bridged the measured bust, and lacked gravity-led folds. Repeated material and renderer changes could not make that geometry behave like cloth.

### Root cause

Simulation acceptance was treated as product visual acceptance. Warp proved that one equilibrium satisfied its numeric contract, but the contract did not require a believable fold field, anatomical contact pattern, hem hang, sleeve hang, or bust silhouette. The pipeline then tried to improve the image downstream without changing the solver authority that produced the rigid shape.

### Prevention rule

Keep physical diagnostics and visual drape review as independent promotion gates. When a mature alternate solver can consume the same measured body and authored garment surface, validate it as a reversible backend candidate instead of continuing renderer-only fixes. The alternate result must preserve pattern correspondence, exact body registration, thin-surface topology, UVs, and seam identity.

### How to verify

Render the original and alternate result with the same avatar, camera, scale, and material. Compare them in one image. Require the alternate result to show materially improved gravity-led folds and silhouette, then independently require zero body crossings, zero self intersections, stable final motion, and strain measured against the authored two-dimensional rest lengths before packaging it.

## UV splits must be welded before cloth self-intersection diagnostics

### What happened

The first standalone self-intersection check reported 3,692 crossings on a Blender cloth result that Blender had simulated with self-collision. The exported OBJ contained separate vertices at UV boundaries, so coincident render vertices were treated as unrelated material particles and tested against one another.

### Root cause

The diagnostic consumed render indexing instead of material-position topology. Face-varying UV and normal corners are valid for rendering, but they do not define separate cloth particles when their positions belong to one welded simulation surface.

### Prevention rule

Preserve the source OBJ for hash and UV evidence, then position-weld coincident vertices before constructing the diagnostic spring graph. Report both the source render vertex count and welded material vertex count. Do not weld explicit sewing boundaries unless the evaluated result is already the accepted welded render surface.

### How to verify

Run the diagnostic on the Blender proof OBJ. Require 31,294 source render vertices to weld to 30,591 material vertices, 91,365 tested structural springs, and zero self intersections. Run the independent body-edge diagnostic on the same thin output and require zero crossings. Keep visual Solidify thickness outside both physical diagnostics.

## Loose sewing springs are not a complete garment seam architecture

### What happened

A direct GarmentCode panel proxy had 14 clean panels, 10,506 regular triangles, 34 authored seams, and 358 corresponding sewing springs. Blender could advance it, but the explicit loose-edge result gathered at the neckline and sleeves, left visible junction gaps, crossed the body, and produced a moving spike. Welding every ordinary seam removed gaps but created 15 cm material edges where distant shoulder and collar panels were averaged together.

### Root cause

The solver was asked to solve both garment arrangement and seam closure from panels whose torso, shoulder, collar, sleeve, and cuff placements were not all close and strain-free. Loose sewing springs supplied positional attraction but not a continuous finished seam surface. Blind welding converted placement distance into invalid rest geometry.

### Prevention rule

Treat panel arrangement, seam constraints, physical topology, and render continuity as separate contracts. Only weld seam samples that are already coincident within a declared threshold. Use body-aware strain-free bends and rigid transforms for every anatomical region before sewing. Keep the accepted collision-free Warp panel surface as the simulation proxy until a direct panel arranger passes initial collision, edge-quality, seam-travel, and strain gates.

### How to verify

Before simulation, require regular physical edges, bounded seam travel, no material edge created by seam welding above the mesh-resolution limit, zero exact body and self crossings, and labeled evidence for every panel arrangement. After simulation, independently require closed seam appearance, zero simulation-body crossings, zero render-body crossings, zero self intersections, bounded authored-rest strain, and stable multi-frame motion.

## A render mesh needs a separate physical proxy

### What happened

Simulating the 31,294-vertex pattern-UV render mesh directly produced softer folds but concentrated extreme strain around UV-split and construction-detail topology. Automatic remeshing either stalled or created microscopic boundary edges. Reusing the accepted 7,698-vertex Warp panel surface as the Blender simulation proxy produced regular 5 to 15 mm physical edges and drove the detailed render surface without adding visual thickness to physics.

### Root cause

The first Blender proof treated render topology and simulation topology as interchangeable. Face-varying UVs, construction lines, seam presentation, and dense subdivision are valuable for appearance but are not a stable cloth discretization.

### Prevention rule

Keep one pattern-correspondent low-resolution physical surface and one detailed render surface. The physical proxy owns mass, stretch, shear, bend, collision, self-collision, and equilibrium. A topology-preserving deformation transfer drives the render surface, and physical thickness remains a render-only modifier. Promotion requires exact contact checks on both thin surfaces.

### How to verify

Require the proxy mesh edge-quality report, source-to-render correspondence, and identical body registration. Run exact CUDA body checks on both exported thin surfaces plus position-welded self-intersection diagnostics. Reject the candidate if either surface crosses the body, if the render transfer changes seam identity, or if final motion and strain fail even when the image looks smoother.

## Mirrored panel yaw must be verified in evaluated three-dimensional space

### What happened

The cup-aware bodice translated its back panels to positive anatomical depth but yawed them in the wrong direction. Their evaluated bounds extended from the back through the torso and into the anatomical front. Correcting the yaw reduced initial body crossings from 188 to 16 on the half-width dressing body, and a 0.2-width dressing body then began with zero body crossings.

### Root cause

The placement test checked only the sign of the panel translation. It did not evaluate the transformed panel vertices after mirroring and rotation, so a positive back translation falsely appeared sufficient.

### Prevention rule

Treat rigid placement as evaluated geometry, not transform metadata. For every mirrored garment, verify the transformed bounds, panel normals, anatomical hemisphere, seam travel, exact body crossings, and exact self-crossings before running a long solve.

### How to verify

Generate the explicit BoxMesh and require front panels to occupy the anatomical front, back panels to occupy the anatomical back, and every detached physical panel to begin outside the chosen dressing body. Record zero-frame collision locations with panel labels so an inverted transform cannot hide in an aggregate count.

## Solver acceptance is not reproducible without mesher topology identity

### What happened

The exact previously accepted side-dart specification, body, body measurements, segmentation, and fabric configuration were replayed through the current pipeline. Their hashes matched the older accepted report, but the old solve contained 8,664 cloth vertices while the current rebuild contained 9,132. The replay ended with 25 body crossings, 15 self-crossings, 0.489 cm seam error, and 111.7 percent peak strain instead of reproducing the accepted equilibrium.

### Root cause

The accepted report did not bind the generated BoxMesh topology or mesher implementation identity strongly enough to make a later rebuild reproducible. Pattern, body, and fabric hashes alone did not prove that the solver received the same physical graph.

### Prevention rule

Persist and hash the exact physical mesh, material rest lengths, panel ownership, seam-link graph, mesher version, and solver implementation for every accepted revision. A later rebuild with a different vertex count or topology hash is a new candidate and must not inherit acceptance.

### How to verify

Replay an accepted artifact and require identical pattern, body, configuration, BoxMesh, rest-length, ownership, and seam-graph hashes before comparing solver output. Fail the replay immediately when vertex count, face connectivity, or seam-link identity differs.

## Pattern proof tools must expose every shaping control used by production

### What happened

The side-dart proof runner exposed intake and ease but silently restored the estimated 0.5 cm dart-mouth drop instead of the accepted 5.0 cm profile value. That moved the generated dart and changed the physical result. The runner now exposes dart tip offset, dart mouth drop, and shoulder-dart mouth offset explicitly.

### Root cause

The proof CLI reconstructed a shaping profile from an estimator and overrode only a subset of the persisted fields. Revision data and the executable proof path therefore described different pattern geometry.

### Prevention rule

When a persisted shaping model gains or already contains a field, expose it in proof automation or preserve the supplied profile value. Never let a verification utility replace a production control with an estimator default without recording that decision.

### How to verify

Generate a pattern with non-default tip, mouth, and shoulder offsets. Require those exact values in the exported Patterna metadata, a changed structural hash for each independent edit, and a successful export/import round trip before simulation.

## Topology mode and strain coverage are independent acceptance inputs

### What happened

An exact side-dart pattern replay produced 9,132 particles instead of the legacy accepted artifact's 8,664 particles. The first diagnosis described this as a generic mesher-topology change. A direct welded-bootstrap rebuild then reproduced the legacy OBJ exactly: 8,664 positions, 17,095 faces, 9,132 pattern-space vertices, zero positional delta, identical connectivity, and the same raw physical-mesh SHA-256. The earlier replay had selected explicit topology while the legacy proof had selected welded topology.

The exact welded replay still failed the current strain gate. The old schema 2.3 report evaluated 23,523 edges and recorded 38.40 percent peak strain. The current full authored rest graph contains 25,761 edges. Reevaluating the old accepted output over that full graph produces 51.35 percent peak strain, essentially the same as the current 215-frame replay. At 650 frames the replay remains collision-free but still has 45.33 percent peak strain.

### Root cause

Pattern, body, and fabric hashes did not bind topology mode, OBJ position-to-pattern mapping, the complete material rest graph, particle ownership, or the solver and mesher implementations. The legacy strain gate also omitted 2,238 seam-adjacent structural edges, so its accepted peak was not a full-surface material measurement.

### Prevention rule

Treat topology selection and strain coverage as separate immutable inputs. Every accepted report must bind the copied pattern, mesh resolution, raw physical mesh, ordered connectivity, pattern-corner mapping, full material rest graph, panel ownership, seam-constraint graph, mesher source, solver source, and final output mesh. A legacy result may not inherit acceptance merely because an exact BoxMesh can be regenerated. Full-surface authored-rest strain must pass independently.

### How to verify

Require schema 2.6 and verify every recorded file hash against the artifact on disk. Require rest and posed passes to match physical-topology, corner-mapping, material-rest, ownership, seam-graph, mesher, and solver hashes. Reevaluate a candidate over every unique structural triangle edge and require the evaluated count to equal material-rest plus declared reference coverage with zero exclusions. Reject the legacy side-dart proof because its full authored-rest peak exceeds the 40 percent limit even though its final collision counts are zero.

## Seam stiffness cannot replace a coupled multi-way junction solve

### What happened

The explicit side-dart shirt reached a collision-free woven equilibrium that passed every full-rest strain gate but left one seam 3.097 mm open. Ten times more seam stiffness reduced the gap by only 0.023 mm. Exact mass-weighted seam-component projection closed every link to zero but raised peak underarm strain from 38.97 to 70.32 percent. A finite seam-allowance patch passed the 2.5 mm seam gate and kept zero body and self crossings, but peak strain remained 45.47 percent. Adding an editable 1.5 mm underarm pattern extension shifted the failure and reduced it only to 44.94 percent. Fivefold material stiffness then worsened the peak to 63.37 percent.

### Root cause

The vendored XPBD integrator evaluates material springs, collision response, and pairwise sewing springs through atomic Jacobi deltas. A high-valence four-panel underarm junction is therefore not solved as one coupled constrained system. Post-step exact projection overloads adjacent material edges, while larger stiffness overcorrects the same singular neighborhood. The drafting pass also reapplied additive armscye changes during front/back width balancing, doubling a requested extension until that shared bug was corrected.

### Prevention rule

Do not treat spring stiffness, solver iterations, remesh resolution, or a post-step weld as substitutes for seam topology. Keep multi-way seam components explicit, preserve a finite simulation seam patch when seam allowance requires it, and solve material, contact, and seam constraints within the same iterative method. Add pattern material through an editable construction parameter only when the fit diagnosis proves it is missing. Additive drafting controls must be applied once even when later passes rebalance width.

### How to verify

Use one schema 2.6 report to require zero initial and final body crossings, zero initial and final self crossings, seam separation at or below 2.5 mm, static equilibrium, and all three full authored-rest strain gates with zero excluded edges. Record the source pattern for every cross-topology drape transfer. Compare the same body, pattern, collision envelope, and fabric while changing one architectural variable at a time. Reject any result that merely moves the maximum to another edge or passes by weakening a gate.

## Source-mismatched garment projection can pass numeric clearance while destroying the silhouette

### What happened

An official Style3D shirt was mapped vertex by vertex from its source avatar onto the Patterna body. The result reached zero reported body penetration, yet the rendered garment had large chest openings, stretched underarms, disconnected-looking folds, and an obviously nonhuman silhouette. Repeated local projection changes moved the defects without producing a credible garment.

### Root cause

The Style3D source avatar and the final MPFB body did not share body topology, landmark correspondence, pose, or local surface parameterization. Nearest-point and guided-ray projection treated those missing correspondences as a geometric cleanup problem. Thousands of independent vertex corrections then changed the garment's material relationships and rest shape. Zero inside-body vertices proved only that sampled points were outside the collider. It did not prove a wearable silhouette, preserved construction, or valid cloth state.

### Prevention rule

Start visual clothing from a proxy authored for the same body family whenever a compatible proxy exists. Preserve that proxy's connected components, face indexing, and UV corners. Transfer only the bounded local correction needed to clear the exact final body. Keep this geometric-fit artifact separate from the editable pattern and physics artifacts, and never display clearance evidence as equilibrium, strain, pressure, or drape evidence.

### How to verify

Fit the MakeHuman upper-garment proxy to the exact 167 cm, 92 cm chest, 71 cm waist, and 99 cm hip body. Require 1,311 garment vertices, 5,048 face-corner UV records, zero final inside-body vertices, at least 0.98 cm minimum clearance, and no more than 1.71 cm maximum correction. Hash the fitted garment and watertight production body into the packaged tests. Render front, both obliques, both sides, and rear, then inspect the same packaged assets in the live WinUI viewport. After any body, pattern, assembly, or fabric edit, require the fitted baseline to disappear until a matching revision-specific simulation is accepted.

## Visual-avatar similarity is not enough for cloth promotion

### What happened

An accepted cloth was first rendered over an earlier full-bust avatar that had nearly the same headline measurements. The shirt showed body breakthrough and implausible dark patches even though the Style3D report proved zero collisions. Regenerating the display avatar from the exact bridged profile used by the simulation removed the defects.

### Root cause

The previous production boundary treated a close measurement profile as equivalent to mesh identity. The 151-value bridge changed secondary values, so the evaluated MPFB surface no longer matched the earlier 95-value body. The cloth, prepared collider, raw MPFB body, and UV display body were derived from different profiles.

### Prevention rule

Promote one explicit identity chain. Require the MPFB fit report output hash to match the prepared collider report source hash, require the prepared collider output hash to match the Style3D body hash, and require the display body's vertex-coordinate digest to match the raw MPFB source body. Similar measurements do not satisfy this contract.

### How to verify

Run `tools/promote_style3d_baseline.py` with the accepted Style3D report, its `simulation-job.json`, the display-avatar directory, and the display fit report. The gate must reject any changed display-body coordinate and must record the source body, prepared body, display manifest, render OBJ, compiler manifest, and report hashes in the production evidence.

## A display-only undergarment can still corrupt the cloth image

### What happened

The first visible bra shell sat 2.5 to 3.0 mm outside the supported body. The cloth was collision-free against the body collider, but the bra intersected it and appeared as large grey patches. Hiding the bra made the accepted cloth render cleanly.

### Root cause

The bra was correctly excluded from physics but its visual offset was larger than the garment-body clearance in several bust regions. Display-only meant the solver ignored it, not that it could safely occupy arbitrary space between body and cloth.

### Prevention rule

Keep supported bust shape in the body and collider. Treat the visible bra as an optional presentation surface only, and cap its fitted offset at 0.10 mm unless a garment is explicitly simulated over the undergarment as a physical layer.

### How to verify

Require `display_optional: true` and `maximum_surface_offset_m <= 0.0001` in the avatar manifest. Render the exact promoted body and cloth with the bra visible and hidden. Both states must preserve the same body and cloth hashes, and the visible state must show no bra or body breakthrough.

## Platform-specific compiler discovery is part of the simulation architecture

### What happened

The expensive Style3D solve completed successfully, but compiler handoff selected a stale non-platform Debug binary because discovery ignored the current `bin/x64/Debug` and `bin/x64/Release` outputs. Retrying would have repeated the solver despite an already accepted equilibrium.

### Root cause

Compiler discovery encoded one .NET output layout and the pipeline had no validated resume boundary between accepted physics and downstream compilation.

### Prevention rule

Search platform-specific and non-platform build layouts explicitly. Treat an accepted solver stage as an immutable, resumable artifact only after rehashing every required source, body, material, topology, warm-start, and final-report file.

### How to verify

Build the compiler for x64, force a downstream compiler failure, and replay the same revision. The log must say that it is reusing the hash-verified accepted Style3D equilibrium, then hand off to the current x64 compiler without running the three solver stages again.

## Packaged cloth acceptance must survive the complete live startup path

### What happened

The production Style3D report and garment were packaged, but the WinUI startup path never called the bundled-evidence loader and the loader still named an obsolete file. Once that was corrected, the baseline gate crashed because the accepted split torso pattern was sent through the legacy one-piece construction measurer. The embedded renderer then failed because a bust-scale variable was referenced before declaration. Finally, the optional bra rendered in front of the otherwise clean shirt because its display pass wrote to the depth buffer.

### Root cause

Static artifact, hash, and topology checks proved each component independently but did not exercise the complete registered-AppX startup path. Runtime code still assumed one-piece front and back construction geometry, JavaScript source order was untested, and the display-only undergarment had no explicit depth-layer contract with the outer cloth.

### Prevention rule

Load and revision-gate bundled fit evidence during every fresh startup. Treat the construction profile as optional when an authoritative split pattern cannot be measured by the legacy drafter. Assert declaration order for bootstrap values used by the renderer. Render presentation-only undergarments without writing depth before the outer garment unless they are represented as real simulated layers.

### How to verify

Build the x64 package, confirm that the normal output and registered AppX contain byte-identical renderer and evidence files, then launch the registered application. The fit panel must report the accepted Style3D revision, the 3D view must open without a startup or script error, the front and rear cloth must remain continuous, and switching the fitted bra on or off must not change body, collider, garment, or fit-evidence identity. With the bra on, the outer cloth must contain no dark overlay patches or undergarment punch-through.

## Install-owned runtimes must not inherit source-checkout metadata or Windows path assumptions

### What happened

The WinUI Simulate command called a real MPFB, GarmentCode, Newton Style3D, and compiler pipeline, but it first searched for the project root. Copied Python environments still pointed at the development checkout, packaged MPFB code expected a `.git` directory, and a correct six-view proof failed when its generated path reached the Windows legacy length boundary.

### Root cause

The development environment was an undeclared part of the runtime contract. Tool locations, editable package pointers, source revision discovery, bridge creation, and proof-directory length were all implicit properties of one working checkout instead of explicit installed inputs owned by one job.

### Prevention rule

Resolve production tools from one install-owned manifest containing only relative contained paths. Hash every required entry point and declared integrity file, record source revisions in a runtime document instead of requiring Git metadata, rewrite copied environment pointers during staging, let each job write its own exact bridge snapshot, and use bounded short artifact names on Windows. Never accept a result merely because an external process exited successfully. Require the compiler surface, display avatar, fabric, registration report, and every fixed-view render to match the job by path and SHA-256.

### How to verify

Resolve the runtime with an application base that is not a source checkout. Reject a changed entry point and a manifest path that escapes the runtime. Run revision `10961a44d0bd788ea7ea873ff4de5fbf43fa3eb97b34aa5ffd83d804c54fee07` through the installed runtime and require 127 equilibrium frames, 20 substeps, 1,974 seam links, zero seam separation, zero body and self collisions, 2.738 percent 95th-percentile strain, and six hash-bound 720 by 900 views. Reopen the job through `TryGetAcceptedResult`, then alter one rear-view byte and require the proof validator to reject it.

## A high-bust woven block needs distributed construction shape

### What happened

The corrected full-bust shirt used the intended 112 cm bust, 84 cm underbust, 82 cm waist, and 98 cm high-hip hem. It followed the upper chest but formed a rigid bridge below the bust, collapsed diagonally at the underarm, and hung away from the back. The numerical solver report passed, but the six-view silhouette did not.

### Root cause

One continuous front panel with side and shoulder darts did not distribute enough contour through the vertical bust-to-waist path for this loose woven block. The cloth hung from the bust and upper back while the waist ease remained mostly unsupported. The earlier fixed anatomical chest plane and full-hip hem target had also hidden this construction problem behind incorrect measurements.

### Prevention rule

Treat visual fit as a construction gate. For large bust projection, evaluate princess seams, waist darts, or another volume-preserving shaping topology before tuning cloth stiffness or collision settings. Derive chest and hem planes from anatomical and garment construction landmarks, and do not use a full-hip girth for a high-hip shirt hem.

### How to verify

Render front, rear, both sides, and both obliques for the same accepted revision. Reject front tenting, diagonal underarm collapse, a cape-like back, or a large body-to-cloth gap even if equilibrium and collision counts pass. Cross-check cloth and body sections at upper chest, full bust, underbust, waist, and hem.

## A warm-start report is one acceptance contract

### What happened

The production pipeline accepted selected fields from a compiler preflight whose overall report was rejected. Its seam closure, panel count, and clearance checks passed, but the same report contained a 0.000018 square-centimeter triangle, 377.8 percent peak edge strain, and 28.1 percent 95th-percentile strain. That invalid shell was then used to initialize Style3D.

### Root cause

The handoff treated the warm start as a bag of independent measurements instead of one validated artifact. It never required the compiler's overall `accepted` decision before consuming the geometry.

### Prevention rule

Never consume a warm-start surface when its own report is rejected. The handoff must verify the overall decision, exact source hashes, topology quality, seam state, collision state, and strain limits as one contract. Do not promote this stricter gate until the replacement arranger can pass it for the current default garment.

### How to verify

Supply a report with valid panel count, clearance, and seam closure but one failed triangle-quality or strain gate. The pipeline must reject it before Style3D starts. Then run the current default and the cup-aware replacement through the same complete gate before changing the production route.

## Diagnose topology at every handoff before blaming the material mesher

### What happened

A six-panel cup-aware princess block was prefitted at 1.0 cm and transferred through panel-space barycentric coordinates to a 0.25 cm physical mesh. The transferred Style3D solve improved some final metrics but still produced body and self intersections, broad strain, and thousands of collapsed or sliver elements. Direct inspection of the material-coordinate archive then proved the fine mesher itself was healthy: 152,076 triangles, zero elements below 0.01 square centimeters, a 28.639 degree minimum angle, and a 3.594 maximum aspect ratio.

### Root cause

The defects were introduced after material meshing. A rounded shell-surface cache collapsed distinct cloth points, harmonic deformation of a closed shell distorted otherwise regular panels, the body depth sign placed front and back on the wrong sides, several equal-direction seams were paired in reverse, an already intersecting coarse state was transferred to fine topology, and the Style3D adapter instantly averaged distant seam vertices through the body. Each individual mistake survived because the pipeline measured the final damaged surface without preserving quality evidence at every handoff.

### Prevention rule

Record and gate material mesh, staged mesh, transferred mesh, and solver input independently. Keep regular panels rigid and separate until a solver with coupled material, contact, and explicit sewing constraints closes them. Never weld or average a seam whose endpoints are still far apart, and never transfer an intersecting coarse state. Preserve sewing-link rest behavior separately from material-edge rest lengths.

### How to verify

Rebuild both coarse and fine material meshes and verify area, minimum angle, aspect ratio, ownership, and seam identity before placement. Require zero body and self intersections after rigid staging. During progressive sewing, record the initial and final seam gaps, exact intersections, static motion, and authored-rest strain. The current coarse princess proof is still rejected despite passing seam and strain gates because one body edge, two self folds, and the static gate remain. Improvement over a worse candidate is not acceptance.

## Generic sewing springs do not extend Newton Style3D

### What happened

The project added generic Newton springs to a cloth model and expected `SolverStyle3D` to close explicit seams. Source inspection showed that Style3D builds and evaluates only its stretch, bend, drag, and collision constraints. Generic `model.spring_*` arrays are not consumed by its projective-dynamics solve.

### Root cause

The cloth helper can optionally create springs because the same model may be consumed by other Newton solvers, but that does not imply every solver evaluates them. Treating model construction support as solver support created an architectural no-op.

### Prevention rule

Trace every proposed constraint from model construction through matrix assembly, force evaluation, and the nonlinear iteration before relying on it. Patterna's project-owned Style3D extension adds each seam to both the positive semidefinite projective-dynamics matrix and the per-iteration internal force, then updates rest lengths through a smooth sewing schedule. Keep the upstream welded mode available until the explicit path passes every promotion gate.

### How to verify

Unit-test the seam matrix diagonal and symmetric negative off-diagonal terms. Run a collision-clean separate-panel source through the explicit mode and require recorded schedule completion, seam closure, exact body and self-intersection counts, authored-rest strain, and static equilibrium. A smaller seam gap alone is not proof.

## Every imported solver extension belongs to the installed runtime contract

### What happened

The Style3D adapter imported Patterna's new explicit-sewing solver from the source tools directory, but the runtime installer and manifest locator still listed only the adapter as a required entry point. Development execution could find the sibling module while a packaged runtime could omit it or accept an unhashed copy.

### Root cause

The impact scan stopped at the Python caller and tests. It did not initially follow the import across the installer payload list, the runtime locator's required-file list, and the independent installed-runtime fixture.

### Prevention rule

Treat every transitive project-owned runtime module as part of the package contract. Add it to the installer payload and integrity set, require it in the runtime locator, represent it in the manifest fixture, and bump the runtime version whenever that required payload changes.

### How to verify

Build the runtime fixture with the complete required script set and require manifest resolution to pass. Remove or alter the sewing module and require resolution to fail. Also assert that the installer, runtime locator, and versioned payload name the same module before building the WinUI application.

## Sewing direction must be verified against anatomical endpoints

### What happened

The six-panel princess block repeatedly produced crossed, inflated, or displaced cloth even after explicit progressive sewing improved some aggregate seam and strain numbers. Direct inspection of the generated BoxMesh links proved that several princess and side seams paired waist vertices with bust or underarm vertices. Nearly every solver experiment on that source was therefore trying to close a physically miswired garment.

### Root cause

The pattern generator marked those stitches `right_wrong` based on an assumption about interface traversal. In GarmentCode's BoxMesh path, that flag disables the default endpoint reversal. Mirroring and panel-edge direction meant the default reversal was the anatomically correct behavior. The existing regression test asserted the flag instead of checking the actual paired endpoint heights.

### Prevention rule

Never infer sewing direction from interface names, mirror state, or edge traversal alone. For every generated seam group, inspect the final discretized link pairs and compare both orientation candidates against named anatomical landmarks. Require waist-to-waist, bust-to-bust, underarm-to-underarm, neckline-to-neckline, and hem-to-hem correspondence before any cloth solve. Aggregate seam distance is not a substitute for endpoint identity.

### How to verify

Generate the exact production pattern, build its explicit BoxMesh, and group links by stable seam identity. Confirm that the default orientation minimizes paired height error for every princess and side seam, that no direction override is present where it would reverse those pairs, and that both left and right halves pass the same invariant. Then require collision-clean staging, bounded authored-rest strain, construction-ordered seam closure, anatomical registration, and accepted views from the front, rear, sides, and obliques before promotion.

## A dressing pose cannot repair incompatible pattern landmarks

### What happened

The corrected princess block reached static equilibrium and substantially improved its strain distribution, but the bodice still looked cropped and grew cap-sleeve-like flaps over both upper arms. The waist hem moved about ten centimeters upward even though its authored source plane was correct. Closing side seams before shoulders reduced the loose flaps. Sewing on a topology-identical raised-arm body and then lowering the arms made the shoulder folds worse and still left the hem at the same height.

### Root cause

The body-pose hypothesis was downstream of an invalid pattern registration. Front shoulder landmarks began 4.6 to 5.2 cm above the matching back landmarks because `frontWaistLength` located the fitted body's nape-to-waist ruler while `backWaistLength` had been reused as an incompatible body-space panel height. Closing the correctly oriented shoulder links forced cloth tension to lift the short back and pull the front waist upward. Arm animation could not repair that dimensional contradiction.

### Prevention rule

Validate anatomical endpoint registration before evaluating a dressing trajectory. Front and back shoulder pairs must share the same body-space neck and armhole landmarks even when measured front and back balance values influence their two-dimensional shaping differently. Only after the pattern passes that gate should a sleeveless bodice or set-in sleeve use a topology-identical raised-arm collider and collision-driven pose trajectory. Do not use body motion, material stiffness, or panel offsets to compensate for mismatched pattern dimensions.

### How to verify

Compare both orientation candidates for every final shoulder link and require paired body-space endpoint heights within one centimeter before simulation. Require a collision-clean initial layout and preserve the measured back balance separately from the anatomical nape-to-waist height. If a raised-arm dressing trajectory is then used, require identical ordered body topology, completed animation before static acceptance, and zero final body and self intersections. Inspect front, rear, side, and oblique views for open armholes, a waist-level hem, and no cloth captured above or outside the upper arm.

## Diagnostic views must bind the solver's exact body and garment

### What happened

Recent six-view diagnostics rendered a custom large-bust garment over the renderer's default MakeHuman body instead of the body used by the cloth solve. The images looked internally plausible enough to review, but the body hash differed from the solver collider and the resulting fit evidence was invalid.

### Root cause

The diagnostic renderer accepted an optional body argument and silently fell back to a repository-wide default. It did not open the solver report or verify the body and garment hashes before rendering. This allowed a custom cloth result and an unrelated mannequin to appear in one image.

### Prevention rule

Never give a body-specific garment renderer an implicit avatar default. Require the exact body, exact garment, and exact solver report together. Verify both source hashes before scene creation, and write a manifest that binds every output view back to those inputs. A visually similar mannequin is not interchangeable with the solver collider.

### How to verify

Render a matching report, body, and garment and require a six-view manifest with all input and image hashes. Replace the body with any topology-compatible or visually similar body whose bytes differ and require the renderer to fail before importing the scene. Review only views whose manifest body and garment hashes equal the solver report.

## A measurement needs both a value and an anatomical landmark

### What happened

The cup-aware block stored the editable armscye circumference without using it to construct the final curves, placed both underarms from full bust, bowed the armhole curves outside the bodice, and did not give underbust its own geometric station. After those defects were corrected, the first underbust station was still placed too high because its vertical location was inferred from cup difference instead of the fitted avatar ruler.

### Root cause

The implementation treated measurement values, curve orientation, and body landmarks as independent metadata. A numerically correct circumference was therefore applied at the wrong height or obtained through the wrong curve direction. Solver tuning could not make that material surface behave like a valid sleeveless bodice.

### Prevention rule

Every editable drafting measurement must drive final panel geometry before meshing. Circumference stations must also bind to an authoritative avatar landmark in the same coordinate system. Audit front and back sibling paths together. For an open edge, verify the signed bend direction as well as its length. Never derive a landmark when the fitted body profile already exposes the measured ruler.

### How to verify

Generate the exact production block and reconstruct the final flat armscye and underbust from its exported curves. Require the armscye and underbust targets within 0.01 cm, require each armhole midpoint to lie inside its straight chord, and require the underbust station to equal the avatar's `vert_bust_line`. Then rebuild and solve the exact material source with unchanged physics. Inspect all six bound views and reject cap flaps, under-bust tunnels, hem lift, body intersections, unfinished equilibrium, seam separation, or strain above the promotion gates.

## Body front and panel front must share one evaluated coordinate contract

### What happened

The cup-aware pattern used an old placement assumption that put front panels at negative GarmentCode depth and back panels at positive depth. The exact MPFB collider and Blender diagnostic renderer put the anatomical front at positive depth. Progressive sewing therefore had to move front and back construction across the body before it could resemble a garment. Aggregate initialization checks did not expose the semantic inversion because the detached panels were still outside the collider.

### Root cause

The project documented a sign convention inferred from transform metadata instead of binding it to evaluated body geometry and the renderer's final OBJ import transform. Tests asserted translation signs and yaw values but did not require every evaluated front vertex and normal to occupy the same anatomical hemisphere as the collider.

### Prevention rule

Define body front once at the collider boundary and carry that axis through pattern placement, meshing, simulation, interchange, and rendering. For every generated panel, test evaluated bounds, outward normal, physical left or right side, and semantic panel name after every mirror and rotation. A collision-free detached layout is insufficient when its construction semantics are front-to-back inverted.

### How to verify

Build the exact six-panel pattern and require both center-front and side-front bounds to lie entirely at positive GarmentCode depth, both back bounds to lie entirely at negative depth, and all panel normals to face away from the body. Require semantic right panels to remain on physical right after mirroring. Then run the exact raised-arm trajectory and inspect the hash-bound front, rear, side, and oblique views. Revision v30 proves the corrected initialization with zero body and self intersections, but remains rejected at 70 final body crossings, so coordinate correction alone is not a promotion result.

## Never rerun a solver from a source artifact that predates the placement contract

### What happened

Candidate v25 reused the v23 material source after shoulder-anchor and seam-order changes. Its six-view diagnostic was still visibly inverted and folded into a horizontal shelf below the bust. The source had front panels at negative depth even though the renderer and fitted body define anatomical front as positive depth. The side-seam scheduler also treated a short three-link lower side segment as a shoulder seam because it inferred seam meaning from link count.

### Root cause

The current staging code, an older source artifact, and the existing lesson disagreed about the depth-axis contract. The solver adapter also received anonymous stitch indices, then guessed anatomy from stitch length instead of panel ownership and material-space height. A new solver binary cannot repair stale or semantically wrong input geometry.

### Prevention rule

Rebuild body-aware source geometry after any placement-contract change. Identify shoulders as the highest front-to-back torso stitch for each matching panel pair, close every lower side-seam segment in the side-seam phase, and attach sleeve caps only after the torso and shoulders close. Bind paired shoulder vertices to one shared height through body expansion. Never spend a full solve on an artifact whose evaluated front and back bounds have not passed the current semantic-axis test.

### How to verify

Run the shell and Style3D adapter unit tests. Build a fresh source and require every front torso panel to have positive depth, every back torso panel to have negative depth, and zero initial body and self intersections. Confirm that the three-link lower side-seam groups are phase 1, true shoulders are phase 2, sleeve caps are phase 3, and paired shoulder anchor targets differ by zero. Only then run the expensive solve and apply the numerical and six-view visual gates.

## Product renames must preserve durable compatibility identifiers

### What happened

The product name changed from Patterna to Patternal after the prototype had already produced saved bridge documents, runtime manifests, Unreal assets, and local simulation state containing the original name.

### Root cause

The prototype used the initial product name both for user-facing branding and for durable technical identities. Unreal binary references and versioned document schemas cannot be safely renamed as if they were ordinary labels.

### Prevention rule

Keep product branding separate from document schema IDs, asset IDs, package identity, local migration keys, and engine module names. A product rename may update visible copy, executable and project names, and repository paths while intentionally retaining old compatibility identifiers. Document every retained identifier so a later cleanup is handled as a migration instead of a search-and-replace operation.

### How to verify

Build every renamed .NET project, run the topology and compiler regressions, launch the packaged Windows app, and verify that the title and package display name say Patternal. Confirm that existing `patterna.*` documents, the `PatternaUnreal` project, and the legacy local runtime path still resolve without rewriting accepted artifacts.

## Verify dependency dirtiness before converting a working folder into submodules

### What happened

The first repository pass represented GarmentCode and NVIDIA Warp GarmentCode as pinned submodules. A clean-tree audit immediately showed that both dependency checkouts contained Patternal-specific source edits, and GarmentCode also contained generated body assets. The initial gitlinks would have omitted those changes from the new repository.

### Root cause

The repository survey captured each nested checkout's origin and current commit but did not inspect its working-tree status before deciding that a gitlink represented the complete dependency state.

### Prevention rule

Before adding any existing checkout as a submodule, inspect its tracked modifications, untracked files, branch, origin, and exact commit. Keep a dependency as a submodule only when its checkout is clean or its required changes already exist in a remote commit that the new repository can fetch. Vendor a modified dependency when the project must preserve local source and asset changes inside one repository.

### How to verify

Run `git submodule foreach --quiet 'git status --short --branch'` and require every retained submodule to be clean. Then clone recursively into an empty directory and verify that the vendored solver edits and generated body assets exist without relying on the original machine.

## Regression tests must not depend on ignored runtime residue

### What happened

The Unreal garment compiler regression passed in the original working folder but failed in the fresh repository clone because its default body profile came from `PatternaUnreal/Saved`. That directory is generated Unreal runtime state and is correctly ignored.

### Root cause

The regression used a machine-produced body profile as an implicit fixture without checking whether a new contributor or CI runner could obtain it from the repository. The original folder masked the missing test input.

### Prevention rule

Every default regression path must be self-contained in tracked source. Generate compact deterministic fixtures in the test or track explicit fixture data outside ignored build and runtime directories. Keep optional arguments for integration tests against real generated artifacts.

### How to verify

Clone the repository recursively into an empty directory, restore and build all projects, and run every regression without supplying local paths. Require the tests to pass while `git status --short` remains empty.

## Regenerated geometry must carry regenerated body-reference metadata

### What happened

The adaptive shirt visibly changed when body sliders moved, but the garment-ease inspector continued reporting the legacy 98/77/107 cm targets. The generated geometry was correctly calibrated to the current body plus ease, while the document still described the legacy 92/71/99 cm source body.

### Root cause

The grader replaced pattern geometry and ease metadata but inherited `BodyReference` from its source document. Readout code correctly trusted the document contract, so stale metadata turned an otherwise correct grade into a misleading product result.

### Prevention rule

Any operation that regenerates measurement-dependent geometry must update the matching body-reference metadata in the same returned document. Use that metadata for source identity and future grading, but measure the finished pattern geometry for the user-visible garment readout. A shirt hem at the high hip is not the same station as the body's full hip.

### How to verify

Grade the production shirt for the 112/82/108 cm body with 6/6/8 cm ease. Require every stored body-reference field to equal the inputs used by the grader. Require the garment inspector to report measurements taken from the resulting chest, waist, and physical hem geometry, including when the hem ends at the high hip.

## Camera labels must be proven against anatomical landmarks

### What happened

The packaged 3D viewport's Front button showed the avatar's back, Rear showed the face and chest, and the front-oblique preset aimed at the rear quarter.

### Root cause

The semantic labels were tested only as strings passed from XAML into JavaScript. No regression asserted the yaw convention against visible anatomy, so internally consistent but reversed angles survived.

### Prevention rule

Bind every named camera preset to one documented anatomical direction. A control label and a renderer method with the same string do not prove that the resulting view is correct.

### How to verify

Require Front to resolve to 0 degrees, Rear to 180 degrees, and front oblique to 35 degrees in the renderer's established coordinate system. In the packaged app, confirm that Front shows the face and chest, Rear shows the back, and Oblique shows the face-side front quarter.

## A display toggle must expose whether its visual asset exists

### What happened

Changing body measurements correctly invalidated the accepted display-avatar stack. The renderer removed the fitted bra mesh with that stale stack, but WinUI left `Show fitted support bra` enabled. The switch changed preference state while producing no visible result or explanation.

### Root cause

Asset availability existed only inside the embedded renderer. The native inspector sent display preferences into WebView2 but received no capability state in return.

### Prevention rule

Treat optional presentation assets as explicit capabilities. When the renderer applies or clears an avatar stack, report whether each user-facing asset exists. Disable unavailable controls, preserve the user's stored preference, and explain the exact action that can make the capability available again.

### How to verify

Load an avatar manifest containing the fitted bra and require the native toggle to enable. Change a body measurement so the accepted display stack becomes stale and require the toggle to disable with a matching-simulation explanation. Restore or simulate a matching avatar and require the toggle to re-enable without changing body or collision identity.

## History restoration must win after control event animations

### What happened

Undo restored a seam-direction override in the garment model, while the selected WinUI ToggleSwitch continued displaying its just-clicked state until assembly mode was refreshed.

### Root cause

The inspector synchronized during the Undo handler, inside the same input cycle in which ToggleSwitch was completing its visual state transition. The model was correct, but the control animation committed after the synchronous refresh.

### Prevention rule

Refresh model-backed controls synchronously for data correctness, then queue one non-recording inspector refresh after history operations when a WinUI control can still be completing the originating event. The deferred refresh must only read restored model state and must not create another undo entry.

### How to verify

In assembly mode, reverse a seam, press Undo, wait for the input event and animation to settle, and require the selected ToggleSwitch to show the restored direction. Press Redo and require the inverse. Confirm that the undo and redo stack depths do not change during either deferred inspector refresh.

## A content staging target is not a complete AppX staging target

### What happened

The isolated guest packager initially invoked `_WinAppCopyContentToLooseLayout` after a clean build, then compared `Patternal.dll` in the normal output and the `AppX` directory. The command returned success while the AppX DLL remained stale.

### Root cause

`Microsoft.Windows.SDK.BuildTools.WinApp.targets` defines `_WinAppCopyContentToLooseLayout` to copy `ContentWithTargetPath` and selected `None` items. It does not copy the current executable, application DLL, framework binaries, manifest, or complete package payload. The WinApp launch flow performs additional staging through its generated package recipe, so invoking the content target alone cannot create a fresh standalone layout.

### Prevention rule

Treat `Patternal.build.appxrecipe` as the authoritative file-to-package mapping for isolated deployment. Materialize a new empty layout from every `AppXManifest` and `AppxPackagedFile` entry, refuse missing sources or conflicting package paths, and compute the payload identity from that clean layout. Do not weaken stale-binary checks because a narrowly named MSBuild target happened to exit zero.

### How to verify

Run `.\tools\isolated-ui\Sync-PatternalGuestPayload.ps1 -PrepareOnly`. It must build successfully, materialize every current recipe entry, prove that `Patternal.dll`, `resources.pri`, `avatar3d.html`, the accepted garment OBJ, and the fabric texture match current output byte-for-byte, then produce a ZIP whose recomputed entry identity equals `payload-manifest.json`.

## Clean Windows guests block copied PowerShell scripts by default

### What happened

The first isolated payload transfer reached the newly provisioned guest, then failed before AppX registration because Windows refused to load `Install-PatternalGuestPayload.ps1`. Host-side tests had parsed the script but had not exercised the clean guest's default execution policy.

### Root cause

The host invoked the copied installer as a script inside a PowerShell Direct session without applying a process-scoped execution-policy override. The scheduled UI task already used `-ExecutionPolicy Bypass`, but the installation path did not share that contract.

### Prevention rule

Before invoking any repository-owned script copied into a clean guest, apply `Bypass` only to that guest PowerShell process or pass it explicitly to a child `powershell.exe`. Do not persistently weaken LocalMachine or CurrentUser policy. Cover both installation and scheduled execution paths in the harness contract.

### How to verify

Provision a fresh Windows guest with its default execution policy, run `Sync-PatternalGuestPayload.ps1`, and require the copied installer to validate the payload, register the AppX, and create the interactive smoke-test task. Confirm that the persistent LocalMachine and CurrentUser execution policies remain unchanged.

## Preserve a direct MSIX fallback for Windows App Runtime deployment

### What happened

After the clean guest accepted the copied payload installer, Microsoft's signed Windows App Runtime 2.3.1 wrapper crashed with status `0xC0000409`. The framework package was still absent, so Patternal could not be registered or launched.

### Root cause

The harness treated the convenience EXE as the only supported runtime deployment path. Microsoft also publishes a redistributable ZIP containing the signed Framework, Main, Singleton, and DDLM MSIX packages, but the guest installer had no path to use them when the wrapper process failed.

### Prevention rule

Verify the wrapper's Microsoft signature and try its quiet installation first. On a nonzero exit, download the exact-version Microsoft redistributable, require all four x64 packages, verify every package's Microsoft signature, and install them directly. Re-query the x64 Framework package before registering Patternal. Do not treat a downloaded or signed installer as proof that it executed successfully.

### How to verify

Run guest installation on a clean Windows image while forcing or reproducing a wrapper failure. Require the direct MSIX path to install Framework, Main, Singleton, and DDLM, record the failed wrapper exit code and fallback mode, register the Patternal package, and proceed to the interactive smoke test.

## A clean packaged-app guest still needs the declared .NET runtime

### What happened

The first registered-AppX smoke run started a responding `Patternal.exe` process but never produced a top-level window. The guest Application log recorded .NET Runtime event 1023: `You must install .NET to run this application.` The package registration and Windows App Runtime deployment had both succeeded, so a process-only check would have lied about startup.

### Root cause

The guest bootstrap installed the Windows App Runtime but omitted `Microsoft.NETCore.App`, even though `Patternal.runtimeconfig.json` declared .NET 10. A development machine concealed the missing prerequisite because its SDK already supplied the runtime.

### Prevention rule

Read the minimum .NET runtime from the materialized AppX runtime configuration and record it in the payload manifest. On the guest, require a compatible major and minor runtime at or above that minimum. If it is absent, install the pinned x64 Microsoft runtime only after verifying its Authenticode signature, then re-query the shared framework before registering and launching Patternal.

### How to verify

Run the packaged payload on a clean guest with no .NET installation. Require the installer result to record the installed runtime version, then require a real Patternal top-level window before any UI Automation step or screenshot can pass.

Preserve the failed run's process snapshot and relevant Windows event records inside `result.json`. Startup failures should be diagnosable from the copied evidence bundle without requiring a second elevated guest query.

## Screenshot geometry must cross PowerShell overload boundaries as integers

### What happened

The first packaged guest run with .NET installed proved a responsive Patternal top-level window, then failed before its first screenshot with `Exception calling .ctor with 2 argument(s): Parameter is not valid.` The runner had derived its window dimensions with `Math.Floor`, which returns `Double`, and passed those values into overloaded `System.Drawing.Bitmap` and `System.Drawing.Size` constructors.

### Root cause

The automation treated a whole-number value as equivalent to an integer-typed pixel coordinate. Windows PowerShell overload binding still saw floating-point arguments, so the constructor boundary was ambiguous and failed inside the guest even though the dimensions were numerically sensible.

### Prevention rule

Convert screenshot left, top, width, and height to explicit `Int32` values before calling any `System.Drawing` constructor or screen-copy API. Preserve the exception type and PowerShell script stack trace in failed evidence so the next defect identifies its exact line instead of leaving only an overloaded-constructor message.

### How to verify

Launch the registered AppX in the interactive guest, maximize its real top-level window, and require a nonempty startup PNG before proceeding to control interaction. Confirm a deliberately thrown runner failure records both `fatalErrorType` and `fatalScriptStackTrace` in `result.json`.

## Capture accepted cloth before exercising simulation-invalidating controls

### What happened

The first complete 2D interaction pass round-tripped body and fabric sliders before opening 3D. Patternal correctly invalidated the old equilibrium while those inputs changed. Restoring the linked-proportions toggle then recomputed detailed body estimates, so restoring only the six primary slider values did not restore the complete 151-value body. The 3D tab truthfully hid the stale cloth and exposed only the measurement avatar.

### Root cause

The test sequence treated numeric control restoration as equivalent to restoring the full model and accepted simulation revision. Linked measurements update a larger dependent state graph, and a valid product must not keep showing cloth solved against an earlier body merely because the visible slider numbers happen to match again.

### Prevention rule

Capture and exercise every accepted-cloth camera before changing body, fabric, pattern, seam, or closure inputs. Return to 2D before running round-trip interaction checks. Close the unsaved test session afterward, and never use a stale-cloth frame as multi-angle acceptance evidence. Preserve the live UI tree whenever a 3D transition fails.

### How to verify

Start from the bundled accepted revision. Require six distinct current-cloth screenshots before the first simulation-invalidating action. Then change and restore the covered controls, require their visible values and toggles to round-trip, and confirm the application hides cloth whenever the complete revision does not match rather than silently reusing it.

## Hidden Windows PowerShell may inherit a PowerShell 7-only module path

### What happened

The non-elevated background validation wrapper failed before guest synchronization because Windows PowerShell 5.1 could not resolve its normally built-in `Get-FileHash` cmdlet.

### Root cause

The child process inherited a module search path that exposed the PowerShell 7 utility module but not the Windows PowerShell utility module. Relying on command auto-loading made a basic identity check depend on the launcher's module-path state.

### Prevention rule

Isolated UI scripts must calculate SHA-256 identities through `System.Security.Cryptography.SHA256`, not through an auto-loaded PowerShell utility cmdlet.

### How to verify

Launch payload synchronization from a hidden Windows PowerShell 5.1 process and confirm it reaches the guest transfer phase without importing `Microsoft.PowerShell.Utility`.

## Slow WebView accessibility traversal can hide sibling XAML controls from broad UIA searches

### What happened

The packaged 3D tab visibly rendered its camera toolbar, and the failure UI tree contained every camera button, but a broad name-based UI Automation descendant search timed out while WebView2 was loading the 130 MB garment surface.

### Root cause

The search traversed the complete mixed XAML and WebView2 accessibility tree. The browser subtree could delay a descendant query long enough that a visible sibling control appeared absent. The buttons also had no stable automation IDs, leaving the runner dependent on a costly name-only scan.

### Prevention rule

Give product-critical XAML controls stable automation IDs and target those IDs from isolated UI tests. Keep a bounded longer first-load allowance for the 3D surface. A stale-cloth state may still exercise the camera interface, but its screenshots must be labeled as stale-avatar evidence and must fail the accepted-cloth gate.

### How to verify

Open the packaged 3D tab in the guest, locate all six camera controls by automation ID, capture all six views, return to 2D, and confirm a stale baseline produces a specific failed freshness action instead of a misleading missing-control timeout.

When the stable IDs are present but `AutomationElement.FindFirst` still returns no match, walk the control view breadth-first and stop at the requested ID. A mixed WinUI and WebView2 descendant query can cross a slow or inconsistent provider boundary; the control-view walker is the same interface used by the evidence tree and keeps the lookup on observable controls.

The stale and accepted 3D states need stable automation IDs too. Never infer accepted cloth merely because a name-based stale-state search returned nothing; require one of the two mutually exclusive native state containers to be observable before recording the freshness action.

Attach those IDs to visible semantic controls such as the state heading `TextBlock`, not layout-only `Border` or `StackPanel` containers. WinUI may omit layout containers from the UI Automation control view even when they have attached IDs.

## Semantic camera labels require screenshot verification

### What happened

The Front, Rear, Oblique, and Fit buttons invoked distinct camera rotations and passed the interaction harness, but the screenshots showed the back of the avatar for Front and the front for Rear. The renderer's source mesh faces the opposite direction from the procedural model assumption encoded in the presets.

### Root cause

The topology test asserted numeric yaw values instead of proving what anatomy appeared in the labeled output. Distinct camera motion was mistaken for correct camera semantics.

### Prevention rule

Define semantic camera presets against the packaged production avatar coordinate system. Review the front, right, rear, left, oblique, and fit screenshots after any avatar or renderer change; a button invocation alone cannot prove that its label is truthful.

### How to verify

Front must show the face and chest, Rear must show the back, right and left must show opposite anatomical profiles, and Oblique and Fit must show the intended front three-quarter presentation. Keep the numeric preset assertions only as regression guards after visual acceptance establishes the correct mapping.

## Character-generator code and generated body assets can have different licenses

### What happened

The architecture review initially treated CharMorph as one reusable open-source avatar option. The current production source actually selects CharMorph's `mb_female` character, whose generated body data is AGPL-3.0, while the same database also contains CC-BY Antonia and Reom characters.

### Root cause

The runtime manifest recorded source revisions and executable hashes but not the selected character backend, the generated-output license, or its license file. Tool licensing and content licensing were collapsed into one vague dependency label.

### Prevention rule

Every versioned simulation runtime and accepted simulation job must name the avatar backend and generated-output license. The relevant license file must be inside the owned runtime and covered by the same SHA-256 integrity boundary as the executable entry points.

### How to verify

Load a fixture runtime whose avatar license file is hash-bound, confirm the resolved runtime exposes its backend and output license, then modify only the license file and confirm manifest validation rejects it.

## License metadata is not a redistributable license artifact

**What happened:** Reom's CharMorph configuration and upstream documentation label the character CC-BY, but the vendored character directory contains no license or attribution file.

**Root cause:** The architecture review initially treated a license name in metadata as equivalent to the actual terms and attribution material required for redistribution.

**Prevention rule:** A character is not eligible for a packaged runtime unless its concrete license and attribution artifact is stored with the character, reviewed, and covered by the runtime manifest's SHA-256 integrity boundary. A metadata-only declaration may support research, but not shipping.

**How to verify:** Resolve every candidate through `charmorph_character.load_character`. Confirm Antonia and `mb_female` resolve their local license files, and confirm Reom is rejected while its license artifact remains absent.

## Avatar backends need explicit control contracts and GLB round-trip review

### What happened

Antonia initially accepted the MakeHuman-style control dictionary without applying a single morph. SciPy reported optimizer success after one evaluation even though bust error remained 26.08 cm and the high-chest section crossed the T-pose arms. After a native Antonia control contract produced a numerically accepted body, the first visual result was still rejected because the optimizer concentrated the target into an excessively spherical breast morph. Separately, the in-memory Blender scene rendered cleanly while a fresh import of the exported GLB showed dark mottling across the body because height-map image nodes were packed ambiguously. Antonia's legacy bra and the existing radial sports-bra shell also failed on the customized non-convex bust.

### Root cause

The pipeline treated all CharMorph characters as if they shared control names, useful bounds, body-shape priors, material-node export behavior, and underwear topology. Optimizer termination, an in-memory render, and an asset name such as `bra` were each mistaken for proof of the corresponding product contract.

### Prevention rule

Resolve a backend-specific fit contract before optimization and reject a backend when its required controls are absent. Bind visually reviewed morph bounds and priors to the fit contract so a tape-perfect but anatomically implausible minimum cannot pass. Export only GLB-safe material graphs, import the GLB into a fresh Blender scene, and review all six canonical views from that imported file. Treat inherited underwear as unfitted after body morphing; use an explicitly labeled modesty layer until a real garment-fit process passes.

### How to verify

Require the Antonia contract to fit the full-bust profile within the documented circuit and landmark tolerances while retaining its constrained mixed-morph solution. Require the generated GLB to import as three mesh objects with ten unique body materials, embedded images, 167.0 cm height, and a body-to-collision vertex distance below 0.00001 m after the recorded OBJ axis transform. Review front, rear, both side, and both oblique round-trip renders. Reject mottled materials, reversed camera semantics, spherical detached anatomy, underwear cutouts, back-facing cups, arm-wing geometry, or any claim that the modesty bandeau is fitted cloth.

## A valid GLB can still violate the packaged camera and status contracts

### What happened

The first packaged Antonia GLB loaded successfully, rendered every embedded material, and passed the existing camera-button automation. The screenshots nevertheless showed the avatar's back under Front and its face under Rear. The packaged HUD also claimed that 151 values were mapped into a fixed fitted candidate, while a large stale-cloth card and a separate status chip obscured each other and much of the lower viewport.

### Root cause

Blender's GLB used Y-up coordinates but retained the source body's opposite anatomical depth direction from the existing packaged display stack. Button invocation proved only that the JavaScript API ran. The HUD derived its count from editable application state instead of the active display-asset capability, and two independent native overlays occupied the same bottom layer.

### Prevention rule

Bind display orientation to the candidate manifest and visually verify semantic camera labels after packaging. Describe fixed fitted assets as fixed fitted assets; do not reuse dynamic measurement-capability labels. Give stale, progress, and accepted states one visible status surface at a time, with bounded text and an unobscured regeneration action.

### How to verify

Install the exact hash-identified AppX payload in the isolated VM. Capture Front, Right, Rear, Left, Oblique, and Fit. Confirm Front shows the face, Rear shows the back, the sides are distinct, and the HUD says `fitted GLB candidate`. Confirm the stale banner has no overlapping status text and does not hide the torso. Require all non-cloth interactions to pass, with the accepted-cloth gate remaining failed until cloth for the exact current revision exists.

## A fitted 2D workspace needs geometry-aware packing and explicit zoom state

### What happened

The packaged 2D view used fixed row spacing and screen-placement offsets. Lower pieces fell outside the visible canvas, long labels collided with geometry, physically small collar and cuff pieces occupied oversized cells, and every piece received decorative slash and notch marks whether or not the source defined them. After replacing that layout, the first zoom test exposed a second defect: rapid Zoom in and Zoom out commands calculated from WinUI's asynchronously committed zoom factor, so the visible percentage could fail to return to the user's starting scale.

### Root cause

Pattern geometry, display decoration, cell placement, and viewport scaling were coupled inside one drawing path. The layout knew neither each piece's actual extents nor a minimum readable label width. Zoom commands treated the ScrollViewer's last committed factor as command intent even though the label and view transition could be ahead of that value.

### Prevention rule

Compute piece extents outside the UI, pack deterministic non-overlapping cells, reserve a separate label header, and draw only source-authored grainlines, notches, darts, and internal paths. Keep the canvas scrollable and expose visible zoom controls. Track the requested zoom target explicitly so sequential commands compose from user intent rather than an asynchronously updated framework property.

### How to verify

Require the 14-piece adaptive shirt to pack inside the bounded canvas with no overlapping placement rectangles. Build the packaged app, capture startup and post-Fit 2D views at 1920 by 1080, and confirm all 14 pieces and labels are visible. Invoke Zoom in, Zoom out, and Fit by stable automation ID; require the visible percentage to increase, return, and then decrease from a zoomed view. Reviewed run `20260809-025650-0625b0e8` demonstrated 89 percent, 109 percent, 89 percent, and a final fitted 89 percent without host input injection.

### 2026-08-22: Fit the occupied pattern bounds, not the drafting paper

**What happened:** The current shelf pack occupied about 506 of the canvas's forced 720 vertical pixels. Fit included the blank drafting area, leaving avoidable vertical whitespace, while collar and cuff geometry remained difficult to inspect until the separate Frame command was invoked.

**Root cause:** Auto layout optimized only whether an item could fit on an existing shelf at a fixed width. Viewport Fit then used the full minimum canvas instead of the union of placed piece cells. The piece list changed selection without bringing the selected geometry into an inspectable view.

**Prevention rule:** Pack piece cells against the target canvas aspect ratio, preserve the larger drafting canvas separately, and calculate Fit from the occupied bounds. Selecting a piece through the accessible list must frame that piece, including small finishing components. Clicking filled pattern geometry must select it without changing the user's current pan or zoom. Queue the first Fit only after both the pattern layout and real viewport dimensions exist; a `SizeChanged` event alone does not prove that rendering has produced layout bounds.

**How to verify:** Require the 14-piece shirt's occupied bounds to have an aspect ratio from 1.15 to 1.55 and at least 500 pixels of content height without overlap. Fit-all must return valid centered offsets from the occupied bounds. Framing the left front collar in an 800 by 600 viewport must reach at least 400 percent zoom while remaining within the 16x product limit. The packaged guest must select a visible piece through guest-local pointer input and prove the zoom label remains unchanged.

## Inspect serialized JSON, not PowerShell's shallow object rendering

### What happened

A shallow `ConvertTo-Json` diagnostic displayed nested cubic controls as the text `System.Object[] System.Object[]`. That display was mistaken for corrupted GarmentCode output. The exporter was changed and tested before exact file hashes proved the original and modified specifications, generated meshes, and arrangements were byte-identical.

### Root cause

PowerShell had already parsed the JSON into nested objects, then a low serialization depth converted deeper arrays into display strings. A presentation artifact was treated as source bytes without checking the file or structural type first.

### Prevention rule

When diagnosing interchange corruption, inspect the raw file, parse the exact property with sufficient depth, and compare hashes of downstream artifacts before changing the serializer. Do not infer stored JSON types from a truncated shell rendering.

### How to verify

Parse every cubic `curvature.params` property from the exact exported specification. Require two nested numeric arrays, zero strings, and deterministic specification, mesh, and arrangement hashes across repeated exports.

## Common cloth inputs must pass before a solver consumes them

### What happened

The first Antonia/current-shirt Newton control spent about 195 seconds solving a body-aware arrangement that already reported a `0.000076 cm2` minimum triangle, 378 percent peak strain, and 36 percent 95th-percentile strain. A second failure showed that the progressive-sewing adapter recognized collar joins as shoulders and missed both live torso shoulders.

### Root cause

The source builder copied arrangement metrics into provenance but did not enforce them. The seam scheduler encoded naming assumptions from an older princess-panel topology and received no explicit construction roles from the live 14-piece adaptive shirt.

### Prevention rule

Reject an initial arrangement before solver launch unless it meets the common minimum-area, peak-strain, broad-strain, and torso-clearance gates. Keep a report-visible research override only for deliberate failure studies. Derive seam phases from panel ownership and finishing roles, support the live front/back naming contract, and allow two spatially distinct shoulders on one front/back torso pair.

### How to verify

Run the source-builder and Newton adapter unit suites. Confirm the exact rejected 0.50 cm C# arrangement fails before solve with both strain reasons. Confirm collar joins are excluded, `seam_link_12` and `seam_link_27` are both phase 2, sleeve caps are phase 3, and all six diagnostic camera names show the matching anatomy.

## Data-bound list rows need explicit automation identities

### What happened

The isolated UI test could see the rendered `Back Torso` text but could not select the row. The WinUI `ListViewItem` exposed the model type name, `Patterna.PatternPieceListItem`, and the editor updated its active piece only through a mouse-style item-click event.

### Root cause

The data template made the visible text correct without defining the container's accessible identity. Selection and activation were treated as the same event even though keyboard and UI Automation selection do not raise `ItemClick`.

### Prevention rule

Give data-bound row models a stable human-readable string identity and drive active selection from `SelectionChanged`. Do not infer accessibility from visible child text.

### How to verify

Inspect the packaged UI Automation tree and require each pattern-piece `ListItem` to expose its piece name. Select `Back Torso` through `SelectionItemPattern`, invoke Frame selected, and require the selected piece to be centered at the calculated zoom without host input injection.

## Viewport labels must follow committed view state

### What happened

The Fit command set its zoom label to 89 percent immediately, so automation accepted the command. The packaged screenshot taken 300 milliseconds later still showed 109 percent because an older `ScrollViewer` view change completed after the optimistic label update.

### Root cause

The command handler treated a requested zoom as committed state. `ScrollViewer.ChangeView` completes asynchronously even when animation is disabled, and the label created a second, premature source of truth.

### Prevention rule

Update viewport labels and control availability only from the final `ViewChanged` event. Tests must wait for that committed property and then inspect the screenshot; a transient requested value is not visual proof.

### How to verify

In the packaged guest, run Zoom in, Zoom out, Zoom in, Fit, and Frame selected in sequence. Require the final label and screenshot to agree after every command, with Fit restoring the full 14-piece layout and Frame selected centering the named piece.

## Bounding-box registration is not visual garment acceptance

### What happened

The exact fitted Antonia GLB and existing production crew-neck OBJ passed `patterna.product-registration/2.0`. The six-view render was nevertheless grotesquely invalid: both breasts and the abdomen protruded through large holes, the rear neckline was open, the sleeves appeared detached, and the underarm and side surfaces were badly distorted. A second render also produced different PNG hashes despite matching geometry, cameras, settings, and visible output.

### Root cause

The product validator treated coordinate bounds, image existence, and source hashes as sufficient visual evidence. Those checks prove registration and identity, not coverage, topology, contact, silhouette, or drape. The review workflow also assumed a separate Blender process would reproduce byte-identical PNGs, which is not a safe contract.

### Prevention rule

Require an explicit human visual decision for the exact front, front-oblique, left, back, back-oblique, and right render hashes. Numerical registration, collision, strain, equilibrium, or image-generation success cannot substitute for that decision. Every rerender resets visual review; never carry a decision to new PNG bytes merely because the scene inputs are unchanged.

### How to verify

Create a six-view proof whose registration is accepted and whose exact image hashes are recorded. Confirm production validation rejects it until `visual_quality.accepted` is true and every reviewed hash equals the current render hash. Confirm a recorded rejection remains rejected. Modify one render and confirm both the review recorder and production validator reject the proof.

## Runtime installers must finish preflight before moving the working runtime

### What happened

The Antonia runtime installer moved `current` to a backup, then discovered that the checkout did not contain the ignored `.venv-garmentcode` directory and stopped. The backup remained intact, but the valid runtime was temporarily absent until it was restored.

### Root cause

Replacement and backup happened before source preflight and staging. The installer also assumed ignored Python environments existed in every checkout even though the owned installed runtime already contained valid copies.

### Prevention rule

Resolve and validate every source first, allow an existing installed runtime to supply ignored Python environments, and build the full staging directory while `current` remains untouched. Move `current` only immediately before promotion. If promoted-runtime validation fails, preserve the failed payload and restore the backup automatically.

### How to verify

Run the installer from a checkout without local virtual environments while a valid runtime exists. Confirm it selects the installed environments, completes staging before printing the backup path, promotes the new version, and passes both Python plus Blender validation. Force a validation failure in a disposable destination and confirm the prior `current` directory is restored.

## Finishing joins are not sleeve caps

### What happened

The semantic seam scheduler put sleeve-to-cuff joins in the same final phase as sleeve-to-torso armhole joins. Both ends of each sleeve tried to close at once. A corrected run closed 130 cuff links one phase earlier and improved maximum seam separation from `0.545 cm` to `0.518 cm`, but the result still failed body-contact, localized-strain, equilibrium, and six-view acceptance.

### Root cause

The scheduler defined a sleeve cap as any seam containing a sleeve panel and another panel that was not also named sleeve. That incorrectly included cuff and band finishing pieces.

### Prevention rule

Classify construction roles on both sides of every seam. Close sleeve internals first, attach cuff or band finishing next, close shoulders after the torso shell, and reserve the final phase for actual torso-to-sleeve armhole joins. Do not promote a semantically cleaner schedule unless the exact numerical and visual gates also pass.

### How to verify

Require a focused unit test in which sleeve-to-sleeve is phase 0, sleeve-to-cuff is phase 1, and sleeve-to-torso is phase 3. Run the exact Antonia control and compare phase counts, seam separation, body crossings, localized strain, equilibrium, and all six anatomical views against the prior hash-bound rejection.

## Visible pattern anchors need a keyboard and automation path

### What happened

Pattern anchors were draggable ellipses with tooltips. They worked with precise pointer input but exposed no stable control identity or invoke behavior, so keyboard users and the isolated Windows test could not select a point and exercise the coordinate editor.

### Root cause

The canvas treated anchor rendering, hit testing, selection, and accessibility as one mouse-only shape. Visible circles do not automatically become usable Windows controls.

### Prevention rule

Render every editable anchor as a named button with a comfortably larger transparent hit target and a visible inner marker. Preserve pointer dragging, but also handle Invoke so selecting the anchor enables the same coordinate and segment inspector without host input injection.

### How to verify

In the packaged guest, frame `Back Torso`, enter point-edit mode, invoke `Back Torso start` by accessible name, change X through `RangeValuePattern`, prove Undo and Redo, and restore the original coordinate. Review the screenshot to confirm the active anchor, surrounding handles, and coordinate inspector are visible and not clipped.

## Structural history must refresh derived workspace metadata

### What happened

Accessible polygon drafting created a fifteenth pattern piece and Undo restored the 14-piece document internally. The canvas changed, but the pieces list and count still claimed 15 pieces. Redo shared the same stale display path.

### Root cause

Undo and Redo restored the structural edit snapshot and rerendered the canvas without rebuilding the derived piece collection and count. Point-coordinate history had hidden the omission because it does not change document structure.

### Prevention rule

After either history direction restores a snapshot, refresh workspace metadata before rendering. Tests for every structural command must assert both geometry behavior and a derived public count or list, then leave the original document restored.

### How to verify

In the packaged guest, enter four coordinate-defined corners, finish the polygon, and require the count to change from 14 to 15. Invoke Undo and require 14, invoke Redo and require 15, then invoke Undo again and require 14. Review the drafting screenshot and confirm the final UI Automation tree also reports 14 pieces.

## Repeated canvas controls need owner-qualified accessible names

### What happened

Every boundary endpoint exposed names such as `edge-1 endpoint`. Those names were locally meaningful but duplicated across nearly every pattern piece, so keyboard automation could not reliably choose an edge on a specific piece for free sewing.

### Root cause

The accessible identity copied the curve ID without its owning piece name. Curve IDs are stable only inside a piece; treating them as garment-wide identities made a valid document ambiguous at the user interface boundary.

### Prevention rule

Accessible names for repeated geometry must include both the human-readable owner and the local stable ID. Apply the same rule to endpoints and Bezier controls, while retaining the local curve ID in the underlying edit handle.

### How to verify

Create `Canvas polygon 15`, enter point-edit mode, and independently invoke `Canvas polygon 15 edge-1 endpoint` and `Canvas polygon 15 edge-3 endpoint`. Sew them, require the Assembly summary to increase from 38 to 39 permanent seams, prove Undo and Redo, and remove the temporary piece. Confirm the final UI Automation tree returns to 14 pieces and 38 seams.

## Stage acceptance must name its scope

**What happened:** The CharMorph avatar report wrote top-level `accepted: true` after a successful numerical measurement fit. The same report embedded a candidate-only GLB manifest and said render review was pending, so a generic reader could reasonably misread stage success as product acceptance.

**Root cause:** One Boolean was doing two jobs: allowing the cloth pipeline to consume a valid exported body and communicating the broader avatar product state.

**Prevention rule:** Keep the pipeline stage Boolean for compatibility, but pair it with an exact `acceptanceScope`, an explicit `productAccepted` value, and a product-status string. Avoid acceptance labels such as `accepted-topology` when any required visual review is still pending.

**How to verify:** Generate an Antonia avatar report and confirm that accepted measurement geometry declares `acceptanceScope: measurement-fit-and-geometry-export`, while `productAccepted` remains false and the product status remains pending render and cloth review.

## A slider round trip does not prove the 3D avatar changed

**What happened:** The isolated UI suite changed and restored every primary body slider, but it stayed in the 2D workspace. That proved the controls accepted values; it did not prove the 3D renderer stopped showing the fixed default Antonia candidate after a measurement edit.

**Root cause:** The renderer's avatar-mode label existed only inside WebView content and was not exposed through the WinUI Automation tree.

**Prevention rule:** Report the renderer's structured avatar state to an accessible WinUI element. For at least one representative body control, test the complete path from slider edit to editable 3D mesh and from value restoration back to the fitted candidate.

**How to verify:** In the isolated guest, change Height with linked proportions disabled, enter 3D, require `DrapeAvatarPreviewState` to name the editable measurement mesh, capture it, restore Height, and require the same element to name the fitted Antonia candidate before returning to 2D.

The first implementation captured immediately after the accessible state changed. WinUI had repainted its label before the WebView compositor visibly replaced the old mesh, producing a contradictory screenshot. Allow the embedded renderer to settle before capture and review the pixels; an event proves internal state, not the frame the user actually saw.

## A torso plane can become an arm-span measurement

**What happened:** CharMorph body preparation measured the `highBustTape` station by intersecting the entire T-pose collision mesh with a horizontal plane. At 133.934 cm the connected section ran through both arms and reported 202.47 cm as a high-bust circuit.

**Root cause:** The generic centered-loop selector reasonably chose the largest centered closed loop, but above the underarm that loop was no longer torso-only. The report made the impossible circuit look like ordinary anatomical evidence and used its front/back split for pattern distribution.

**Prevention rule:** Never infer a high-bust front/back distribution from a horizontal collider section that intersects posed limbs. Use the explicit across-front and across-back measurements, retain the requested tape height and circumference, and record that no horizontal section was used. Apply the same invariant to every avatar backend.

**How to verify:** Prepare the default 167 cm Antonia collider. Require a watertight accepted body, `highBustTapeDistribution.requestedCircumferenceCm` of 96.0, a back fraction of `37.0 / (36.7 + 37.0)`, `horizontalColliderSectionUsed: false`, and no `highBustTape` entry in the measured horizontal `sections` map.

## Acceptance status must be reconciled with the product before adding a duplicate feature

### What happened

The isolated-test status listed internal-line and dart update and deletion as open. Source inspection showed that both dialogs already supported create, edit, delete, Undo, and Redo through stable structural commands. The missing work was packaged interaction proof, not product implementation.

### Root cause

The automated suite stopped after create and a simple Undo and Redo round trip. Its status paragraph was later treated as a feature inventory instead of an acceptance inventory, so an untested workflow was mistaken for an absent workflow.

### Prevention rule

Before implementing a listed UI gap, inspect the active command handler, document model, structural edit commands, and tests. Describe unobserved behavior as unproven, not missing, unless source and packaged inspection both support that conclusion.

### How to verify

In the packaged guest, create an internal line and a guide dart, update their names and semantic fields, prove each update through Undo and Redo, delete each object, prove each deletion through Undo and Redo, and leave the garment with neither test object. Review the resulting line and dart screenshots at 1920 by 1080 and confirm the result bundle records no functional failure beyond the independent current-cloth freshness gate.

## An interactive canvas needs a hit-test surface on empty space

### What happened

The 2D toolbar told the user to click the canvas to place polygon corners, but guest-local pointer clicks on visually empty grid space never reached `OnPatternCanvasPointerPressed`. The cursor moved to the expected coordinate, Windows accepted the click, Patternal was foreground, and UI Automation resolved the point to an unnamed parent pane instead of `PatternCanvas`.

### Root cause

The WinUI `Canvas` had no background. A null background makes visually empty regions transparent to hit testing, so only existing child geometry could receive pointer input. Numeric coordinate entry worked and disguised the broken direct-manipulation path.

### Prevention rule

Every interactive drawing surface must declare an explicit hit-testable background. Use `Transparent` when the parent owns the visible fill, and keep a packaged pointer test that places geometry on empty space rather than over an existing child.

### How to verify

In the isolated guest, fit the 2D canvas, enter pointer polygon mode, and click four empty-space corners. Require each click to advance the accessible corner count, click the first corner again to close the polygon, prove the piece count changes through Undo and Redo, restore the original count, and review the captured preview. The host-input and VMConnect flags must remain false.

## Guest bootstrap code must compile with the guest compiler

### What happened

A guest-local pointer helper compiled under PowerShell 7 on the host but used expression-bodied C# methods that Windows PowerShell 5.1 `Add-Type` rejected. The failure happened before the runner created its evidence directory, so the scheduled task exited with code 1 while the host waited for a `result.json` file that could never appear.

### Root cause

The harness parsed PowerShell syntax and checked automation contracts but did not compile the embedded C# with the same compiler used by the guest scheduled task. The host poller watched only for the result file and ignored the scheduled task state.

### Prevention rule

Compile embedded guest C# through Windows PowerShell 5.1 during the repository harness check. While polling a guest run, observe both `result.json` and scheduled-task state; fail promptly with `LastTaskResult` when a newly started task exits before initializing evidence.

### How to verify

Run `Test-PatternalIsolatedUiHarness.ps1` and require `GuestCSharpCompiler` to report `Windows PowerShell 5.1 passed`. Run the normal guest suite and confirm a valid result bundle is copied. A deliberately invalid guest C# probe must fail the harness before sync, while an early guest task exit must stop the host poller without waiting for its full timeout.

## Viewport pixels are not physical pattern scale

### What happened

The 2D footer claimed `12.5 mm grid`, while the canvas drew minor lines every 40 canvas pixels using four canvas pixels per authored centimeter. The actual document spacing was 10 cm, or 100 mm. The same uncalibrated pixel transform could not truthfully make ordinary 100% zoom mean physical size on an unknown monitor.

### Root cause

An old display label survived after the document-to-canvas transform changed. No invariant bound the grid interval, unit label, zoom semantics, and monitor calibration workflow together.

### Prevention rule

Label authored grid spacing from document units, never from an assumed monitor scale. Keep viewport percentage separate from physical 1:1. Enable actual size only after the user measures a known on-screen ruler, persist display-independent pixels per centimeter, and require recalibration after any monitor, scaling, resolution, or remote-display change.

### How to verify

Require the source grid interval to remain 40 canvas pixels at four pixels per centimeter and the UI to name it as a 10 cm minor and 50 cm major grid. In the packaged guest, enter 10 cm for the 320-DIP calibration ruler, require 32 DIPs per centimeter and 800% actual-size zoom, leave through Fit, return through 1:1, capture the scale UI, clear the test calibration, and restore the original fitted zoom.

## Physical-dart UI proof must include compiled topology and failure cleanup

### What happened

The first packaged physical-dart test checked only that two dart legs appeared after applying a free-edge dart. It then entered Assembly mode before reading the legs, which changed the accessible drawing surface, and a failed assertion left the temporary polygon in the document. The later free-sewing test failed for the wrong reason because it inherited that extra piece.

### Root cause

The test mixed two distinct contracts: visible 2D construction feedback and compiler-owned closure topology. It also assumed the happy-path Undo sequence would always run. A structural authoring test that mutates the document must restore its baseline even when the assertion being investigated fails.

### Prevention rule

Assert rendered dart legs while the 2D construction surface is active. Then enter Assembly mode and require the permanent-seam count to change by exactly the compiler-owned closure seam. Wrap temporary document mutations in bounded cleanup that cancels active drafts, restores the original piece count, and restores the prior assembly state.

### How to verify

In the packaged guest, edit and restore one existing sewn-edge dart. Create a temporary polygon and a free-edge dart, require both rendered legs, require the permanent-seam count to increase from 38 to 39, prove Undo and Redo, and restore 14 pieces and 38 seams. Run the subsequent free-sewing check in the same application session to prove no temporary state leaked forward.

## LocalSettings is not document storage

### What happened

The packaged Save command threw `0x80073DC8` because the serialized garment document exceeded the Windows application-setting value limit. The same handler stored several other JSON collections as independent setting values, so deleting only the largest redundant value would merely postpone the next failure.

### Root cause

Small scalar preferences and expandable document payloads shared one persistence mechanism. `ApplicationData.LocalSettings` is appropriate for numbers, booleans, and short strings; it is not a database wearing a tiny hat.

### Prevention rule

Keep scalar preferences in LocalSettings. Store expandable structured state in a versioned file under the package LocalFolder, write it to a temporary file, and atomically replace the prior snapshot only after serialization succeeds. Read the file first and fall back to legacy setting values so an upgrade does not discard an existing snapshot. Report I/O failure instead of claiming success.

### How to verify

In the packaged guest, change Height with linked proportions disabled, save, terminate the process, relaunch the AUMID, and require both values to restore. Restore the originals, save again, relaunch again, and verify cleanup. Inspect the saved payload path and require the obsolete document-sized LocalSettings value to be removed.

## File pickers must leave the input-synchronous callback

### What happened

Windows Save As and Open initially failed with `An outgoing call cannot be made since the application is dispatching an input-synchronous call` when the toolbar button was activated through UI Automation. The picker worked with ordinary manual timing, which made the failure look like a test-only nuisance even though accessibility activation is a supported product input path.

### Root cause

The async WinUI handler opened a system picker before yielding out of the input-synchronous dispatch. The picker requires an outgoing COM call that Windows forbids in that phase.

### Prevention rule

At the beginning of an async handler that opens a Windows picker, yield once to the dispatcher before constructing or showing the picker. Exercise the command through real guest-local pointer input and UI Automation activation; neither input path gets to be a second-class citizen.

### How to verify

Launch the packaged AUMID, activate Export, require the real Windows Save As dialog, enter a unique file name, and click Save. Parse the SVG and require its embedded `patterna.garment/1.1` document to contain the expected panel and seam counts. Repeat the boundary for photo import without relying on host input.

## Hidden WebView state is not visible 3D proof

### What happened

After a long 2D authoring session, Patterna updated the accessible avatar-state label when Height changed and restored, but both late 3D screenshots contained a white canvas. The automation action passed because it asserted the label and never checked rendered pixels.

### Root cause

WebView2 suspended a requestAnimationFrame loop while its TabView item was hidden. Returning to 3D could leave the old scheduled frame stranded even though JavaScript state and XAML overlays continued to update. A successful camera command did not prove the WebGL surface had repainted.

### Prevention rule

Own render-loop generations explicitly. When 3D becomes visible, invalidate the old generation and schedule a new frame loop after layout. Query `gl.isContextLost()` and reload the renderer only when recovery requires rebuilding GPU resources. Give WebView2 a dark native background, and never accept an avatar-state label as visual proof by itself.

### How to verify

Enter 3D and capture the six semantic cameras, spend a full authoring sequence in 2D, change a measurement, return to 3D, activate Fit, and capture the editable avatar. Restore the measurement and repeat for the fitted candidate. Sample the central WebView region and reject fewer than 5 percent non-white pixels, then manually inspect both images for an actual body, correct state, and usable framing.

## Nested project payloads must retain their serializer contract

### What happened

Patterna saved a valid named `.patterna` project, selected it through the packaged Windows Open picker, and then rejected its own file as invalid measurement, geometry, or assembly state. The custom-measurement payload was valid and retained the casing used by the existing local snapshot format.

### Root cause

The new project validator applied the garment document's camel-case serializer options to every nested JSON string. Custom measurements intentionally used the older default serializer contract. Deserialization silently produced null record fields, so validation rejected data that the established restore path could read.

### Prevention rule

Treat each nested serialized value as a versioned boundary with its own serializer options. A container format does not erase the contracts of payloads embedded inside it. Reuse the exact reader used by restoration, or perform an explicit migration before validation. Never validate with one serializer and restore with another.

### How to verify

Save a named project through the packaged Save As picker with one custom measurement present. Parse the file, disturb scalar state, select the file in the packaged Open picker, and require the project to restore without an error InfoBar. Verify the exact Height, linked-proportion state, and non-preset fabric weight, then inspect the restored 2D workspace screenshot.

## Independent canvas overlays collide at laptop width

### What happened

The 1280 by 720 packaged run passed every persistence action, but its screenshot showed the scale description running underneath the zoom and calibration controls. Both surfaces were independently aligned to the bottom of the same canvas overlay, so neither reserved space for the other.

### Root cause

The wide desktop layout happened to provide enough empty space between two unrelated bottom-aligned borders. That accidental gap was mistaken for responsive layout behavior.

### Prevention rule

Place neighboring overlay controls in one shared layout container with explicit columns and spacing. Give descriptive text the flexible column and enable ellipsis; keep commands in the auto-sized column. Do not rely on opposite alignment inside the same grid to prevent overlap.

### How to verify

Request exact 1280 by 720, 1600 by 900, and 1920 by 1080 guest modes. Run the packaged persistence workflow at each size and inspect the startup and named-project screenshots. Require the footer text and every zoom command to remain distinct and readable, and keep 200 percent text scaling as a separate unproved gate.

## Keyboard focus movement is not tab activation

### What happened

The keyboard test sent an arrow key to the workspace tabs and assumed the newly focused tab had become selected. WinUI moved keyboard focus but did not activate the tab until Enter was pressed.

### Root cause

The test treated focus, selection, and activation as one state. They are separate accessibility contracts, and controls are allowed to require an explicit activation command after focus moves.

### Prevention rule

Assert focus movement first, activate with the control's supported keyboard command, and then assert selection or visible content. Keep a screenshot with a deliberate final focus target so the focus-ring evidence agrees with the recorded control identity.

### How to verify

Focus the 2D tab, press Right Arrow, require keyboard focus on the 3D tab, press Enter, and require 3D content. Repeat with Left Arrow and Enter to restore 2D, then capture a named control with a visible focus ring.

## Coupled measurements are not reversible one-field probes

### What happened

The keyboard workflow changed Height while linked proportions were enabled, then moved Height back and expected the complete avatar revision to match the original. Height drives 151 dependent estimates, so restoring one visible value did not restore the prior body state. A failed assertion also left 3D visible and caused unrelated later checks to fail.

### Root cause

The test chose a value with intentional fan-out as though it were an isolated slider. Its cleanup ran only on the success path, so one local failure poisoned the remaining workflow.

### Prevention rule

Use an independent, exactly reversible value such as Fabric weight for a generic keyboard range probe. Test linked body recalculation separately as a state transition. Put value and workspace restoration in `finally` so every later check starts from its documented precondition.

### How to verify

Record Fabric weight, increase it by one keyboard step, require the visible value to change, decrease it by one step, and require exact restoration. Enter 3D and require the fitted candidate, then restore 2D in `finally` even when any assertion fails.

## Active guest requests must be promoted atomically

### What happened

A host launcher timed out while the scheduled guest smoke task kept running. A second invocation copied a new request over the shared `run-request.json` before checking task state. The first task completed successfully under its original run ID, while the second host process waited for evidence under the overwritten ID.

### Root cause

The launcher published shared mutable state before acquiring the guest task's idle precondition. The running-state guard existed, but it ran one destructive line too late.

### Prevention rule

Copy each request to a run-ID-specific staging path. Inside one guest command, check that the task is idle, delete the staged file on rejection, promote it to the canonical request path, and only then start the task. Never overwrite the canonical request of an active run.

### How to verify

Start one guest smoke task, invoke the host launcher again, and require the second call to reject without changing the canonical run ID. Confirm the first run writes evidence under its original ID and the rejected staging file is removed.

## Theme flags are not visual proof, and guest themes must always be restored

### What happened

Patterna had automation-name and keyboard coverage, but no packaged evidence under the real Windows dark and high-contrast themes. A future test could also leave the persistent guest in a contrast theme if an assertion or app launch failed after changing it.

### Root cause

Theme configuration, rendered contrast, and cleanup are separate contracts. Reading a theme name or a high-contrast Boolean does not prove that pattern geometry, focus, status messages, WebView chrome, toggles, or sliders remain readable. Applying a persistent user setting without unconditional restoration also makes later evidence depend on whichever run failed last.

### Prevention rule

Apply the built-in Windows `.theme` file before packaged launch, verify both the active theme path and `SPI_GETHIGHCONTRAST`, capture real 2D and 3D pixels, and restore the exact original theme in `finally`. Treat Light, Dark, High Contrast Black, High Contrast White, High Contrast 1, and High Contrast 2 as distinct visual gates. Do not infer one from another.

### How to verify

Run the packaged persistence workflow under all six themes and the complete 2D and 3D workflow under at least one high-contrast theme. Inspect every screenshot for readable geometry, text, control state, focus, status, and camera chrome. Require the result bundle to record the requested theme, original theme, restored theme, and restored high-contrast state. Confirm host input injection and VMConnect use remain false.

## File existence is not proof that an asynchronous Save As finished

### What happened

The packaged project round-trip copied its Save As target as soon as Windows created the destination path. On one full run, the picker had created a zero-byte file while Patterna was still serializing the project. The harness copied that empty placeholder into evidence and then reported a missing `schemaVersion` property.

### Root cause

The test treated path creation as transaction completion. Windows pickers may materialize a file before the application finishes writing and closes it. The product had already exposed a `Project saved` completion state, but the harness copied the file before waiting for that state or validating its contents.

### Prevention rule

For asynchronous file workflows, wait for the product's success state and then require a non-empty, parseable file with the expected schema before copying or inspecting evidence. Never use `Test-Path` alone as a write-completion barrier.

### How to verify

Save a uniquely named `.patterna` project through the packaged Windows picker. Require the `Project saved` status, then poll until the file parses and reports `patterna.project/1.0`. Copy it only after both checks pass, disturb the live state, open the saved file, and require the scalar and editable-construction values to restore exactly.

## Avatar registration must survive different display and collision topology

### What happened

The Antonia exporter proved display-to-collider identity by comparing corresponding vertices in order. That was exact for the current full-resolution control, but the gate rejected any simplified collision body before measuring its surface. The architecture explicitly permits separate display and collision topology, so the proof mechanism contradicted the intended product design.

### Root cause

Vertex correspondence was used as both convenient evidence for the current control and the permanent registration contract. A simplified collider changes vertex count and order even when it remains on the same fitted surface. One global maximum also hid which anatomical area had drifted.

### Prevention rule

Measure registration bidirectionally between the actual display and collision surfaces. Report head, torso, arms, and legs separately, enforce maximum and 95th-percentile limits for every applicable region, and enforce a shared floor datum. Retain a direct vertex-order comparison only as extra evidence when topology happens to match. Keep human visual review independent because surface proximity does not prove believable anatomy.

### How to verify

Run the Blender registration tests with a display box and a differently triangulated collision box on the same surface; it must pass despite different vertex counts. Shift the collision box by 2 cm and require a torso-region rejection. Generate the exact 167 cm fitted Antonia through the installed runtime and require `patterna.avatar-surface-registration/1.0`, accepted head, torso, arms, and legs, no issues, floor error below 1 mm, and every regional maximum and 95th percentile within its declared threshold.

## Anatomy gates must not measure pose as proportion

### What happened

Six-view review ranked Antonia above the other local bodies, and its exact fitted display and collision surfaces passed regional registration. The first weighted-rig anatomy audit measured horizontal fingertip width at 0.886443 times stature and upper-arm length at 0.153202 times stature. Diff review caught that the fingertip metric was really measuring Antonia's symmetric arms-up pose. The corrected pose-independent segment-chain estimate is 0.949553 and passes; upper-arm length remains below its deliberately broad human-data rejection envelope.

### Root cause

The bake-off compared candidates against each other, while registration only proved that two meshes described the same fitted surface. Neither proved that the winning surface had credible human segment proportions. The first gate then reused an anthropometric arm-span range with a pose-dependent horizontal extent, conflating two separate defects and producing a false rejection.

### Prevention rule

Resolve semantic landmarks on the exact fitted vertices and evaluate dimensionless ratios before spending time on hair, texture, modesty assets, or cloth. Derive limb lengths from skeletal segment chains so authored pose cannot change the result. Keep surface registration, proportion sanity, pose quality, symmetry, and visual review as separate gates. Use primary anthropometric sources with matching measurement definitions; label broad project-owned guards honestly when a definition-matched population table is unavailable.

### How to verify

Generate the 167 cm fitted avatar through the installed runtime and require `patterna.avatar-anatomy/1.0`. Confirm the report measures pose-independent arm span, arm and upper-arm length, hand and foot length, shoulder breadth, head height, and functional leg length; require all paired landmarks to stay within 1 mm for a symmetric preset. Confirm the exact Antonia control passes arm span at 0.949553, is rejected only for its 0.153202 upper-arm ratio, and passes all 108 paired landmarks. Require product visual proof to reject any missing or non-accepted anatomy report.

## Blender proof commands must fail closed and refresh evidence

### What happened

An installed-runtime avatar proof used repository-relative profile paths. The installed script correctly resolved them against the runtime root and raised `FileNotFoundError`, but Blender returned process exit code 0 because no Python failure exit code was requested. The old manifest remained in the output directory and initially looked like a fresh result.

### Root cause

The proof command trusted Blender's default process status and inspected a pre-existing artifact without first proving that the current invocation rewrote it. Blender treats an unhandled Python exception as console output unless `--python-exit-code` is supplied.

### Prevention rule

Pass absolute paths across repository and installed-runtime boundaries. Invoke Blender automation with `--python-exit-code 1` or another explicit nonzero value. Treat output freshness as part of the proof contract, not as housekeeping.

### How to verify

Run the installed generator with absolute profile, fitted-vertex, and fit-report paths plus `--python-exit-code 1`. Require exit code 0, a manifest write time from the current invocation, matching source, installed, and runtime-manifest hashes for the evaluator, and the expected current anatomy result. Deliberately pass a missing profile once and require a nonzero Blender exit instead of accepting an older manifest.

## Do not type a VM password without proving the guest is at the password field

### What happened

A user-opened VMConnect window appeared to be waiting for guest login. By the time a synthetic Enter, password, and Enter sequence arrived, unattended AutoLogon had already reached the guest desktop. Windows Search received part of the disposable password, remained over the application, and stole focus from the observed run's initial New and keyboard-navigation checks.

### Root cause

The login helper inferred guest UI state from an earlier human observation. PowerShell Direct proved that the guest was reachable but did not prove which interactive control held focus when the synthetic keyboard input arrived.

### Prevention rule

For user-visible VMConnect sessions, give the user the machine-local credential note and let them log in manually. Never send a blind password through the synthetic keyboard. Keep unattended runs on AutoLogon and limit host synthetic-keyboard use to the documented boot Enter key.

### How to verify

Open VMConnect only with explicit user permission, log in manually if required, and confirm the desktop has no Search, Start, sign-in, or other overlay before starting an observed run. Treat any run with an unexpected foreground overlay or manual console connection as informational, not unattended acceptance evidence.

## Symmetric anatomy can still be the wrong garment-inspection pose

### What happened

Antonia's fitted surface and 108 paired rig landmarks are symmetric, yet six-view review still showed an implausible arms-up presentation for clothing inspection. The exact surface endpoints confirmed both arms were elevated 12.452430 degrees above horizontal and swept 16.429742 degrees backward. Symmetry passed because the problem was a symmetric pose choice, not left-right corruption.

### Root cause

The anatomy gate intentionally measured pose-independent segment lengths, and landmark mirroring only proved bilateral consistency. Neither contract constrained the neutral pose used for pattern fit inspection. Perspective in the oblique packaged camera made the symmetric elevation look asymmetric, which further demonstrated why pose must be measured in body coordinates rather than inferred from one screenshot.

### Prevention rule

Keep anatomy, symmetry, inspection pose, and visual review separate. Require the symmetric product preset to use a shallow A-pose with arm elevation between -55 and -10 degrees, no more than 8 degrees left-right elevation or forward-sweep difference, and no more than 3 percent stature endpoint mirror error. Give authored asymmetric poses their own target contract instead of weakening the symmetric preset.

### How to verify

Run the five pose fixtures and require a symmetric shallow A-pose to pass while one raised arm, symmetric overhead arms, excessive forward sweep, and non-finite geometry fail. Generate the exact fitted Antonia and require `patterna.avatar-pose/1.0` to reject only `meanArmElevation` at 12.452430 degrees. Require product visual proof to reject a missing or non-accepted pose report.

## GLB vertex splitting must preserve the exact fitted surface

### What happened

A fresh Antonia GLB import contained 39,330 body vertices even though the fitted source contains 36,030. The extra vertices came from material and attribute splits, not new geometry. Comparing unique rounded positions proved that all 36,030 source positions survived with zero missing or unexpected values.

### Root cause

Vertex count was treated as though it were a surface identity. glTF primitives may duplicate a position at material, normal, tangent, or texture-coordinate boundaries while preserving the exact geometric surface.

### Prevention rule

For round-trip display verification, compare the unique world-space position set and bounds to the exact fitted source instead of requiring equal vertex counts or index order. Keep the GLB hash and six-view render hashes attached to the same verification report.

### How to verify

Import the exact hashed GLB in a fresh Blender scene with the expected fitted vertex array. Require 36,030 expected unique positions, 36,030 round-tripped unique positions, zero missing positions, zero unexpected positions, matching bounds, 167 cm height, and six new renders. Deliberately perturb one GLB position and require verification to fail.

## A partitionable desktop GPU is not a supported Hyper-V GPU product lane

### What happened

The host's `Get-VMHostPartitionableGpu` result exposed the RTX 4090 as a GPU-P device with 32 valid partitions. Earlier discussion compressed the support boundary into wording that sounded like partitioning was impossible. Hyper-V can technically attach a partition on this machine, but Microsoft does not support GPU-P on this Windows 11 Pro desktop host and consumer RTX 4090 combination.

### Root cause

Technical capability, current configuration, and vendor support were treated as one question. They are three separate facts: the host reports a partitionable device, `Patternal-UI` currently has no GPU partition adapter, and the officially supported platform requires Windows Server 2025 with supported server hardware.

### Prevention rule

Report all three boundaries explicitly before making a GPU virtualization recommendation. Do not call an exposed but unsupported GPU-P path impossible. Do not use community driver-copying workarounds as CLO-class release evidence merely because the guest can launch a CUDA process.

### How to verify

Record the host OS and build, `Get-VMHostPartitionableGpu`, and `Get-VMGpuPartitionAdapter -VMName Patternal-UI` separately. Require official Microsoft and GPU-vendor support for the exact host OS, guest OS, and GPU model before treating a partitioned guest as physical-GPU acceptance evidence.

## Observation commands must not masquerade as acceptance runs

### What happened

A request to leave Patternal visible first used a one-shot AppsFolder scheduled task, then reused the persistence acceptance workflow with `KeepAppOpen`. The direct activation created a process without proving a window, while the acceptance workflow correctly refused to run because user-opened VMConnect fixed the guest at 1366 by 768 instead of its required 1920 by 1080 mode.

### Root cause

The guest had a comprehensive one-shot acceptance harness but no durable lifecycle channel for launch, status, screenshot, and close. A simple observation request was forced through tools with different proof contracts.

### Prevention rule

Keep observation and acceptance lanes separate. Use a persistent logged-in-user runner with atomic requests, fresh heartbeat evidence, explicit lifecycle commands, bounded retained files, and hash-verified screenshots. Keep full acceptance on the fixed-resolution one-shot harness and continue rejecting VMConnect or unexpected display modes there.

### How to verify

Install the guest payload, require `Patternal Guest Runner` to remain active under the interactive user, then run status, launch, screenshot, and close from the host wrapper. Require the launch result to contain the real top-level window and primary workspace, require the copied screenshot hash to match, require close to leave no Patternal process, and confirm every result records the interactive session without host input or VMConnect launch.

The interactive runner's PowerShell host must use `-WindowStyle Hidden`. A visible scheduled-task console can sit above the app and invalidate screenshots while every process, heartbeat, and UI Automation assertion remains green. After installing or updating the runner, inspect a fresh screenshot and reject any evidence obscured by harness windows.

## Guest package installers must reuse an identical registered layout

### What happened

A runner-only update rebuilt the same AppX payload identity. The guest installer stopped Patternal and immediately tried to delete the already-registered identical layout. Windows still had `Microsoft.InteractiveExperiences.Projection.dll` mapped, so deletion failed with access denied even though no product binary had changed.

### Root cause

The installer treated every tooling sync as a package replacement. It deleted files before deciding whether the package content or registration differed and before unregistering a changed package.

### Prevention rule

Make payload installation idempotent. Reuse a complete AppX directory whose hash identity and registered install location already match. For a changed payload, stop the exact application with a bounded wait, unregister it before deleting its owned layout, verify the replacement directory identity, and then register the new manifest.

## Validate a bundled interpreter instead of trusting notebook metadata

### What happened

The first PPF challenger installer required Python 3.12 because the bundled fitting notebook recorded Python 3.12.3 in its authoring metadata. The pinned Windows distribution actually ships its own Python 3.11.9 interpreter, so the installer correctly refused promotion even though the runtime itself was intact.

### Root cause

Notebook metadata was treated as distribution identity. It describes the environment that last saved the notebook, not necessarily the self-contained runtime shipped beside it.

### Prevention rule

Execute and record the bundled interpreter during preflight. Pin the version actually present in the hash-pinned distribution, and treat notebook kernels, README examples, and development environments as non-authoritative hints.

### How to verify

Run the embedded `python.exe` directly, require the exact expected version and a successful `frontend` import, then confirm a failed preflight leaves no promoted PPF version or staging residue. Rerun the installer and require the already accepted MHR runtime to be reused unchanged.

## Test Python tools through their documented file entrypoint

### What happened

The MHR fitting unit tests passed when invoked as Python modules, but the documented `python tools\fit_mhr_identity.py` command failed immediately because the script imported `tools.mhr_anthropometry` without adding the repository root to Python's module search path.

### Root cause

Module-mode tests supplied the repository root implicitly. They did not exercise the same import environment as direct file execution.

### Prevention rule

When a repository tool imports through the repository package namespace, make its root bootstrap explicit and cover the documented file invocation in a subprocess test.

### How to verify

Run the tool's `--help` through its exact file path and require exit code zero before starting the expensive model fit. Keep the focused function tests as a separate layer.

## A PPF mesh cache path does not redirect session state

### What happened

The first native PPF smoke supplied an external `cache_dir`, but PPF still wrote application and session state beneath the versioned runtime's `local\share\ppf-cts` directory.

### Root cause

PPF resolves mesh cache and application data through separate paths. `App.create(..., cache_dir=...)` changes only the former; `App.get_data_dirpath()` still selected the distribution-relative Windows data root.

### Prevention rule

For disposable host smoke tests, redirect both paths into the artifact root. Use the process-local, explicitly patchable `App.get_data_dirpath` seam and retain PPF's real GPU and driver checks. Do not set its test-rig environment variable because that deliberately disables those checks.

### How to verify

Run a forced fresh session, require its reported path to live under the selected artifact directory, and assert that no `local` directory appears under the immutable PPF version root. Remove any state created by an earlier invalid run.

## Anatomical deformation membership needs more than one coordinate

### What happened

The first MHR local correction selected upper-arm vertices mainly by absolute X position. Wide hip and thigh vertices occupy the same X range, so the arm shrink also deformed the lower body, drove hip circumference to 149 cm, displaced vertices by more than 21 cm, and flipped 406 triangles. After adding a hard height cutoff, measurements passed but five-view inspection exposed a visible notch at each shoulder root.

### Root cause

One coordinate identified a spatial slab, not an anatomical region. The hard replacement cutoff then fixed membership numerically while introducing a discontinuous deformation field.

### Prevention rule

Combine side, lateral position, and anatomical height for limb membership. Taper deformation smoothly from zero at the shoulder root to full strength at the measured upper-arm plane, and taper distally along the limb centerline. Numerical section targets never waive surface review.

### How to verify

Require lower-body vertices at the same absolute X to receive zero arm weight. Then require all measurement tolerances, finite output, positive triangle areas, zero orientation flips, bounded displacement, and fresh front, rear, both side, and oblique review of the exact output mesh.

### How to verify

Install one payload, leave Patternal open, and sync a guest-tool-only change with the same payload identity. Require `appxReused: true`, `registrationReused: true`, and an uninterrupted app process. Then change one packaged byte in a disposable fixture and require orderly unregister, owned-layout replacement, identity verification, and registration without access-denied retries.

## PPF dynamic timelines can override an explicit frame count

### What happened

The first Patterna garment command requested 20 PPF frames, but the native `param.toml` recorded only 2. Adding release keyframes after setting `frames` let PPF's dynamic timeline derive a new frame count from its last keyframe. The solve completed normally, so counting output files without reading native parameters made the short run look like a wrapper or cache failure.

### Root cause

The adapter treated independent-looking fluent parameter calls as order-independent. PPF's dynamic builder owns timeline duration and can update the session frame count as a side effect.

### Prevention rule

Configure every dynamic parameter first and apply the caller's explicit `frames` value last. Grade the persisted native `param.toml`, not the command line or wrapper's intention. Report simulated frames separately from the initial vertex snapshot.

### How to verify

Run a 20-frame session with a release keyframe, require `param.toml` to contain `frames = 20`, and require 21 vertex snapshots numbered 0 through 20. The collector must report 20 simulated frames and 21 saved snapshots.

## PPF output vertices must be restored through its object map

### What happened

PPF wrote all scene vertices into one solver-owned ordering. Taking the first garment-sized prefix produced the expected array shape but attached positions to the wrong source indices, corrupting seam, strain, and export evidence without an obvious file-format error.

### Root cause

Topology counts were mistaken for vertex correspondence. PPF reorders and combines scene objects for its solver, then records the reverse mapping in `map.pickle`.

### Prevention rule

Decode the versioned object map with the pinned runtime and restore `patterna-garment` source order before every metric, OBJ export, render, or recovery operation. Reject missing, empty, duplicated, or out-of-range mappings.

### How to verify

Use a synthetic three-vertex permutation and require exact source-order restoration. On a real session, require the mapped garment shape to match the source OBJ and bind the vertex-map SHA-256 into the collection report.

## A detailed render body and a cloth collider have different jobs

### What happened

The exact 0.50 cm garment plus the 69,164-face Antonia body took 751.260 seconds for two native PPF frames. The body dominated the contact workload. Replacing it blindly would have improved speed while discarding the registration evidence that makes collision believable.

### Root cause

One mesh was being asked to preserve visible anatomy, materials, camera quality, contact fidelity, and solver throughput. Those constraints do not require identical topology, but they do require measured surface agreement.

### Prevention rule

Keep the detailed fitted body as the display authority and derive a separate hash-bound collision proxy. Require a watertight single component, preserved orientation and floor datum, and bidirectional global plus head, torso, arm, and leg surface gates. Never promote a proxy merely because decimation completed.

### How to verify

Build the 10,000-face Antonia proxy twice and require the same OBJ SHA-256. Confirm global and regional maximum drift below `0.50 cm`, 95th-percentile drift below `0.15 cm`, floor error below `0.10 cm`, and unchanged component and non-manifold counts. Then prove the solver report records both canonical and proxy identities.

## Stronger stitches do not replace seam-aware dressing

### What happened

The 1 cm PPF garment began with authored seam pairs as far as 55.519 cm apart. Default stitches pulled most panels rapidly but plateaued at 9.062 cm maximum separation after 20 frames. Raising stitch stiffness fivefold and the stitch-length factor fivefold still left 7.375 cm separation, took 351.405 seconds for only five frames, and worsened p99.9 strain to 0.692.

### Root cause

The spread-panel source asks global soft stitches to drag front, back, sleeve, cuff, and collar surfaces through a crowded contact field at once. A larger force cap increases solver work and material distortion but does not provide construction order or a collision-safe dressing path.

### Prevention rule

Stop global stitch-force tuning after one bounded comparison. Build a seam-aware dressing stage that preserves each panel's material shape, keeps authored seam identity, orders internal, torso, shoulder, cuff, and sleeve-cap closure, and starts each active stitch phase inside a documented capture distance.

### How to verify

Before another acceptance-length PPF solve, require the staged report to list every panel transform, phase, source hash, initial and per-phase seam distances, body clearance, and zero self-intersections. The raw solve must close every authored seam below `0.25 cm` without post-snap and pass strain, equilibrium, collision, and six-view review.

## A wrapper timeout does not prove its native child failed

### What happened

The first full Patterna PPF wrapper exceeded its shell timeout, but the native solver child continued and wrote a clean finished marker, empty error log, vertex snapshots, object map, and stdout log. Treating the shell result as solver failure would have discarded valid, expensive rejection evidence.

### Root cause

The wrapper and native solver had separate process lifetimes, while grading was coupled to the wrapper's final Python code path.

### Prevention rule

Use a bounded wrapper timeout, but inspect the owned session before declaring failure. Keep a separate collector that verifies runtime and input identities, native parameters, finished and error markers, object mapping, and every output hash. Do not kill a healthy owned child merely because its parent stopped waiting.

### How to verify

Allow a wrapper to end while a disposable native session finishes. Run the collector against that exact session and require an honest accepted, rejected, or pending report whose frame count comes from native `param.toml` and whose final metrics use the last two mapped snapshots.

## Every solver adapter must enforce the common input gate

### What happened

The first PPF adapter verified hashes, topology, garment self-intersection, and native scene construction, then ran the 1 cm source for 20 frames. A later complete adapter preflight found zero body intersections but 17 garment-to-body pairs inside the mandatory `0.25 cm` initial clearance. The source report carried `accepted: false` only because it required a fresh solver evaluation, so checking that Boolean alone would also have rejected the wrong thing for the wrong reason.

### Root cause

The common-bundle gate lived mainly in the source builder and was treated as inherited evidence. A rebuilt resolution could preserve hashes and rest geometry while lacking a complete, solver-specific body-clearance proof.

### Prevention rule

Every backend adapter must independently recompute the input properties it relies on before launching an expensive child process. Require source schema, no research override, finite geometry and material triangle areas, initial strain, panel self-intersection, body intersection, and body clearance. A generic bounded rigid stage may repair clearance only by translating the violating panels, recording every transform, preserving material shape, and rerunning every gate. Write the input report even on rejection and provide no convenience flag that turns a failed production gate into an ordinary run.

### How to verify

Run the exact current 1 cm source through `--preflight-only --maximum-seam-phase 0` and require `patterna.ppf-input-gate/1.0` to record 17 initial clearance violations, rigid translations for only `left_collar_back`, `right_collar_back`, and `right_sleeve_b`, no more than `0.30 cm` maximum shift, zero final intersections, zero final clearance violations, accepted area and strain metrics, 46 active internal-shaping links, and no native solver process. Run the default all-phase preflight separately and require rejection because `55.519 cm` exceeds the `5 cm` direct-capture threshold. Move a disposable panel into the body and require the intersection gate to fail.

## Aggregate seam and strain metrics can hide a fabric grenade

### What happened

The cumulative PPF route closed internal, detached-shell, torso, and cuff phases below `0.38 cm` while keeping p95 edge strain below `0.10`. Those figures looked promising. Fresh front, rear, side, and oblique renders showed a densely crumpled cloth mass around the temporary body, laterally spread sleeves, and no credible shirt silhouette. Neckline experiments then stalled between `5.214 cm` and `10.108 cm` and pushed p99.9 strain as high as `0.486`.

### Root cause

Percentile summaries hid severe localized folding and the semantic arrangement of the cloth. Sequential soft stitches pulled widely separated panels through free space and around a reduced collider, but neither low aggregate strain nor near-closed seams guaranteed that the panels occupied the correct side of the body or formed the intended garment volume.

### Prevention rule

Every cloth phase that materially changes assembly must produce deterministic multi-angle renders before the next architectural promotion. Require semantic panel placement, silhouette, and localized fold review in addition to seam, strain, collision, and motion metrics. Stop a challenger route after one bounded construction-order and collider-shape comparison when the rendered topology remains catastrophically wrong.

### How to verify

Render the exact hash-bound garment and collider from front, rear, both sides, and both obliques. Reject any phase with a crumpled mass, laterally detached sleeve volume, inverted panel region, missing neckline, or body-shaped compression even when p95 strain and most seam links pass. Confirm the solver route remains isolated from the accepted Newton runtime and product asset path.

## Avatar anatomy corrections must move the surface and rig together

### What happened

The first fitted MHR surface looked materially better than the control but failed the existing upper-arm and forward-sweep gates. Its native upper-arm ratio was `0.148714`, below the `0.16` minimum, and its arms swept forward by roughly 28.75 degrees. Stretching only the visible mesh would have left the skeleton inside the wrong anatomy.

### Root cause

Measurement fitting, visible surface correction, and rig landmarks were initially treated as separate proof stages. A numerically plausible surface can still disagree with the joints that will animate it.

### Prevention rule

Do not weaken an anatomy or pose gate to admit a preferred model. Apply smooth symmetric corrections to the affected surface and the exact descendant joint chain together. Preserve topology, skin weights, and joint mapping, then re-run mesh quality, anatomy, pose, registration, and exported-skin checks.

### How to verify

Require a `0.170000` upper-arm ratio, mean forward sweep within 25 degrees, zero orientation flips, one 126-joint GLB skin, zero unweighted vertices, at most four influences per vertex, joint-head error below `0.00001 m`, and exact display-to-collision registration. Review all six views afterward because these checks still do not prove appearance.

## Semantic camera labels require visual review after every avatar swap

### What happened

The first packaged MHR run passed every camera-button interaction, but the Front screenshot showed the avatar's back and Rear showed its face. The GLB used a 0 degree display yaw while the established packaged camera convention required 180 degrees.

### Root cause

Automation proved that each button invoked a camera state, not that the asset's anatomical axes matched the label. Replacing the avatar changed the axis contract without changing the controls.

### Prevention rule

Bind display orientation in the hash-bound avatar manifest and inspect Front, Rear, Left, and Right pixels after every body-family or exporter change. A successful click is not semantic evidence.

### How to verify

Require the manifest's 180 degree display yaw, rerun the packaged six-camera suite, and manually confirm face, back, and profile direction. Preserve the first reversed run as rejected evidence rather than renaming its screenshots.

## A logged-on guest session can be alive but uncapturable

### What happened

The isolated runner launched and controlled Patternal successfully, but every screenshot failed with `The handle is invalid`. Windows reported the disposable user's session as `Disc`, so UI Automation still worked while the screen device context did not.

### Root cause

Logged on, interactive, active, and capturable were treated as one state. Enhanced Session disconnection separates them.

### Prevention rule

Before a screenshot-bearing acceptance run, resolve the single owned Explorer session and require an explicit `Active` state. When it is `Disc`, use Windows' supported `tscon <id> /dest:console` handoff inside the guest and verify `Active` before starting. Do not open VMConnect or inject host input as recovery.

### How to verify

Run the host preflight against both active and disconnected guest states. Require `GuestSession.active: true`, record whether console recovery occurred, capture all expected PNGs, and retain `hostInputInjected: false` plus `vmConnectLaunched: false` in the result.
# 2026-08-22: Pre-solve geometry and complete edit identity must gate avatar and cloth claims

## What happened

The MHR preview represented 11 values while the product exposed 151 numeric avatar values. An unmapped edit could leave the mesh unchanged and still receive exact-candidate wording. Separately, repeated cloth work attempted to compensate for bad assembly with sewing, projection, staged constraints, and solver changes. A fresh input diagnostic found 142 body intersections, 4,157 self-intersections, 469 near-degenerate triangles, 703 extreme slivers, 893 triangles below a 5-degree minimum angle, and 4.128 cm penetration before a meaningful solve. The PPF adapter also ignored `output_mesh_path` and silently reloaded `physical_mesh_path`.

## Root cause

Acceptance status was inferred inside individual subsystems instead of being derived from one complete revision identity. The viewer counted only represented morph changes. Solver adapters owned implicit input selection. The arrangement gate measured some aggregate geometry values but did not hard-gate exact body and self-intersection evidence before simulation.

## Prevention rule

Every avatar and cloth claim must bind the complete current edit set and exact source bundle. Unsupported edits fail closed. Every worker consumes only declared bundle roles and hashes. No solver starts until the exact arrangement proves zero body and self-intersections, minimum clearance, orientation, topology, material-space, seam-proximity, and triangle-quality gates. After one frozen diagnostic confirms a bad input class, stop tuning it.

## Verification

`tools/revision_bundle.py verify` rejects changed, missing, extra, escaped, or acceptance-claiming source bundles. The MHR renderer reports baseline, partial, and unsupported preview modes separately and receives `previewChangedKeys` from WinUI. The current rejected arrangement and one-frame diagnostic remain under `artifacts/revision-proof-day1-control`; their reports preserve the exact hashes and failure counts.

### 2026-08-22: Arrangement cannot be both immutable source and derived worker output

**What happened:** The first revision-bundle contract required `arrangement` as a source input even though the replacement architecture expected the arrangement worker to create it.

**Root cause:** The bundle froze every file used by the old solver invocation without separating authored authority from derived evidence. That produced a circular contract and risked laundering a known-rejected placement into later workers as source truth.

**Prevention rule:** Immutable source bundles contain only authored inputs. Arrangement artifacts and their independent verification reports are separate content-addressed stages. No producer can accept its own output, and no solver can consume diagnostic or rejected geometry.

**Verification:** Current bundle creation rejects an `arrangement` input. The legacy 1.0 and source-only 1.1 verifiers still validate their frozen historical bundles without rewriting them.

### 2026-08-22: Global seam links require an authoritative panel index map

**What happened:** The first exact-topology worker correctly switched from reconstructed edge order to the authoritative seam-link file, then could not map those global vertex IDs back to source panels without guessing.

**Root cause:** Revision bundle 1.1 included the global seam labels and per-panel meshes but omitted the generated global-to-panel index map that relates their two index spaces.

**Prevention rule:** Any source contract that carries global vertex constraints must also carry a complete, reversible ownership map. Never infer ownership from coincident positions, serialization order, or filenames.

**Verification:** Revision bundle 1.2 requires `panelIndexMap`. The worker validates every mapped global vertex against the exact panel and local counts before compiling constraints.
# 2026-08-22: A clean solver plan is not a solver result

## What happened

The new contact-aware arrangement route produced a deterministic, hash-bound libuipc scene plan with clean spread-panel geometry and complete seam constraints. It would have been easy to describe that as the arrangement path "working" before the dependency had even been installed.

## Root cause

Adapter integrity, runtime execution, arrangement acceptance, cloth acceptance, and packaged visual acceptance are different claims. Collapsing them rewards paperwork-shaped evidence while leaving the difficult physics entirely unobserved.

## Prevention rule

Every generated artifact must state its acceptance scope and keep later claims false. A plan verifier may accept immutable plan integrity only. The worker always emits an unaccepted arrangement artifact, and only a separate verifier may accept that arrangement. Cloth and packaged UI gates remain later boundaries.

## Verification

Run `tools/verify_libuipc_arrangement_plan.py` against the immutable scene plan and source bundle. Confirm the result says `scope: immutable-plan-integrity-only`, `executionAuthorized: false`, `arrangementAccepted: false`, and `clothAccepted: false`.

# 2026-08-22: Execute reviewed releases, not convenient source checkouts

## What happened

The first Anny worker contract pinned a post-release repository commit because the v0.6 release was not yet visible during the earlier audit. A later fresh inventory found the official 0.6.0 wheel and tag. The post-release commit was one six-line keypoint-device fix ahead, but its packaging metadata referenced a `LICENSE_THINGS` file absent from the repository tree.

## Root cause

Source review identity and executable dependency identity were treated as the same choice. A commit is excellent provenance, but a mutable checkout with incomplete packaging metadata is a worse runtime artifact than a complete, hashed release wheel when the only later change is outside the worker's path.

## Prevention rule

Bind each third-party worker to a reviewed source identity and a separately verified execution artifact. Prefer a complete official wheel with a fixed hash, embedded data inventory, and embedded licenses. Do not patch installed third-party code to chase an irrelevant post-release fix. If the required fix is relevant, wait for a release or maintain a formally versioned fork with its own provenance.

## How to verify

Require Anny wheel SHA-256 `050a0b24a3e7fdb89b46dc3581947ea84225305425ac9a1a97b65ea997fb2ad6`, 1,559 data files, 107,825,068 uncompressed data bytes, the Apache-2.0 code license, and the MPFB2 CC0 license. Compare tag `72104cac8242d1735ec06433b65bec5e26953ce7` to reviewed commit `81ca83e202273b306205c1cc15f33734be31e48c` and require that the six-line keypoint change remains outside the body worker path.

# 2026-08-22: Proof tools must not depend on an accidental Python environment

## What happened

The continuous body-clearance verifier originally used SciPy's `cKDTree`. It passed in the earlier analysis runtime, then could not even import after the machine's default Python moved to 3.14 and the available Python 3.12 environment lacked SciPy.

## Root cause

A small candidate-selection optimization quietly became an undeclared runtime dependency. The exact distance proof needed NumPy, but it did not require SciPy's broader surface area.

## Prevention rule

Keep independent geometry proof tools on the smallest declared dependency set. Use a conservative repository-owned spatial hash when its completeness is easy to prove. Explicitly select the capable interpreter during verification rather than relying on the current `python` launcher order.

## How to verify

Run `tools.test_triangle_surface_clearance` in the bundled Python 3.12 runtime with NumPy and no SciPy. Require the cross-cell boundary fixture to retain its candidate, the near surfaces to fail, the separated surfaces to prove the threshold, and the far surfaces to require zero exact pair evaluations.

# 2026-08-22: An independent verifier cannot import its producer

## What happened

The libuipc plan verifier imported two schema strings from the plan producer. Importing the producer also imported Warp, so immutable-plan verification failed on a machine without the arrangement runtime even though the verifier did not need Warp.

## Root cause

The artifact contract lived inside the implementation that produced it. Python imports execute the producer's entire dependency surface, accidentally coupling proof to the software under test.

## Prevention rule

Put shared schema identifiers and passive data contracts in dependency-free modules. Producers and independent verifiers may both import the contract, but a verifier must never import a producer or solver adapter.

## How to verify

Run `tools.test_libuipc_arrangement_plan` in a Python environment with no Warp installation. All four immutable-plan tests must pass, including hash tampering, authorization tampering, and undeclared-file rejection.

# 2026-08-28: Asset identity does not imply product acceptance

## What happened

A packaged cloth integration verified the hashes of a diagnostic body and garment, then exposed them through a path and control named `AcceptedDrape`. The same asset report explicitly kept producer acceptance, packaged visual quality, calibrated fabric, and correct-body drafting false. Hash verification proved the files were unchanged, but the viewport path still presented a visibly rejected garment as an accepted solve.

## Root cause

Artifact identity and renderer compatibility were treated as sufficient authorization to display an asset under an acceptance label. Neither check answers whether the garment is correct, physically credible, drafted for the body, made from calibrated material, or approved in exact multi-angle renders.

## Prevention rule

Keep diagnostic assets outside accepted product paths. Product-visible drape must pass one fail-closed gate that checks every acceptance scope, requires no open gates, binds an accepted six-view review by hash, and rejects any missing or false claim. Never infer acceptance from a directory name, a successful parser, equilibrium, or matching file hashes.

## How to verify

Run `python -m unittest tools.test_product_drape_acceptance`, then run `tools/product_drape_acceptance.py` against the packaged asset and renderer reports. The current rejected diagnostic asset must exit with code `2` and enumerate the false claims. A synthetic fixture may exit with code `0` only when every product and visual gate is explicitly true.

# 2026-08-28: Constraining one angle of a pose leaves the other one wherever it was

## What happened

The dressing stance drove each arm's elevation to horizontal and never mentioned azimuth. Both arms came out horizontal and 28 degrees forward of the line through the shoulders, so the body wore the shirt in a stance no garment is drafted for. Every arrangement and settle gate passed, because the sleeves were staged along the collider's own fitted arm axes and the result was internally consistent. Only the packaged side view showed it.

## Root cause

A direction in space needs two angles. The search optimised the one that was written down and left the other at whatever the rest pose happened to hold, and no gate compared the stance against anything outside the run, so a self-consistent wrong stance satisfied all of them.

## Prevention rule

When a solver targets an orientation, name every independent angle of that orientation in the target and in the report, and fail when any of them misses tolerance. Consistency gates confirm that a result agrees with its own inputs; they cannot notice that the inputs describe the wrong pose. Look at the render.

## How to verify

Read `search` in the pose report: each side must carry both `achievedElevationDegrees` and `achievedAzimuthDegrees` within `stanceToleranceDegrees` of their targets. On the exported body, fit the principal axis of the vertices beyond 45 cm from the centreline above 105 cm; its lateral component must dominate and its depth component must be near zero.

# 2026-08-28: A coordinate contract is not the frame the renderer draws in

## What happened

The first packaged export put the body in the revision bundle's own frame, which places the anatomical front along +z. The viewport expects the front along -z: its front camera sits at yaw 180 and its rear camera at yaw 0. Every camera showed the opposite of its label, and the result read as a modelling fault rather than a frame error.

## Root cause

Two correct conventions met with nothing between them. The exporter carried geometry from a frame defined by an artifact contract into a frame defined by a renderer, and assumed they agreed because both were described as Y-up with the floor at zero.

## Prevention rule

Where geometry crosses from one frame's owner to another's, convert explicitly and check the result against the consumer, not the producer. Use a rotation rather than a mirror so winding, surface orientation, and the body's own left and right survive. Gate the facing so the error cannot return silently.

## How to verify

Run `tools/verify_packaged_drape_assets.py`. It reports `body.facesFrontCamera` and fails with a named issue when the head centroid sits at non-negative z. Running it against `artifacts/packaged-drape-assets-v1` must exit with code 1 and name the facing; running it against the current assets must exit 0.

# 2026-08-28: A UI Automation descendants search can silently return a partial tree

## What happened

Two UI Automation faults hid controls that were plainly on screen. A `TreeScope.Descendants` search over the Patternal window returned 93 elements and never reached the camera buttons or the solved-cloth toggle that sit beside the hosted browser control, while a raw tree walk over the same window reached 594 elements and found all of them. Separately, the window element of an exited process stayed in the automation tree with its subtree frozen, so a lookup by window name attached to the corpse of the previous run rather than the app that was actually running.

## Root cause

Both failures return absence rather than an error. A truncated search and a dead window element each answer "not found", which reads as a missing control rather than a broken lookup.

## Prevention rule

Walk the raw tree when a control must be found, and bind to the main window handle of a process that is currently running rather than to the first element with a matching name. Wait for controls that appear only after asynchronous work, with a bounded timeout that fails loudly.

## How to verify

Run `tools/Invoke-PatternalDrapeViewCapture.ps1` against a running app and confirm it finds every camera button and the toggle. Restart the app and run it again without any pause: it must attach to the new window rather than timing out on the old one.

# 2026-08-28: A layout height computed from the page ignores what sits above it

## What happened

The 3D surface took an explicit height of the page height minus the command bar minus a fixed allowance. That allowance covered the tab strip but not the out-of-date notice above the surface, so whenever the notice was showing the surface was taller than its container and the bottom of the 3D view was clipped away, taking the information panel with it.

## Root cause

The height was computed from a distant ancestor and a constant, so it could not follow a sibling whose height changes with visibility. Removing the explicit height is not an option either: the hosted browser control collapses to nothing when it is left to its star-sized row alone.

## Prevention rule

When an explicit size is genuinely required, subtract every sibling that shares the space, measure those siblings rather than assuming them, and recompute from their own size changes, because an element reports a height only after it has been laid out.

## How to verify

Run `tools/Invoke-PatternalDrapeViewCapture.ps1` with the out-of-date notice showing and again with it hidden. The captured viewport must fill the tab in both states, and the panel in the lower left must be complete in every image.

# 2026-08-28: A drafting refusal thrown from a value-changed handler ends the process

## What happened

Typing 24 into the sleeve cap height box closed the application. The box accepts 5 to 30, and 24 is inside that range. The drafter refused the request with `Sleeve attachment left-sleeve-f/edge-1 requires 3.570 cm of endpoint redrafting, outside the 0.75 cm construction limit`, which is the right answer. The refusal was an exception thrown inside a NumberBox ValueChanged handler, nothing caught it, and the process terminated with every unsaved edit in it. Windows recorded it as a fault in the XAML framework, which pointed away from the real cause.

## Root cause

The drafting contract and the interaction contract disagreed about what a refusal is. To the drafter it is a normal outcome for an unsatisfiable request. To the UI framework an exception crossing a control event is fatal. Nothing sat between them, and roughly forty call sites reach the drafter, so no single caller could be made responsible.

## Prevention rule

Validate at the point where unvalidated input enters, not at every point that consumes it. A control that accepts a number the engine can refuse must attempt the work first, and on refusal restore the previous value, leave the model untouched, and name both the control and the reason. A range on a spin box only bounds the number; it says nothing about whether the combination can be built.

## How to verify

Run `tools/Invoke-PatternalControlSweep.ps1` against a running app. Every slider and numeric box must be found and restored, and the application must still be running when the sweep finishes. Then set the sleeve cap height to 24: the value must return to its previous setting and the application must show a message naming the control and quoting the construction limit.

# 2026-08-28: A control with no readout is indistinguishable from a dead control

## What happened

The control sweep flagged six numeric boxes that accepted a value and changed no readout anywhere. Reading the panels showed why: the construction summary reports neck, shoulder, and armscye figures but never back neck depth or sleeve cap height, and the bust summary reports intake and separation but never projection, mouth offset, or shoulder share. Capturing the pattern canvas before and after showed that back neck depth does redraft the pattern, so the control works and only its feedback is missing.

## Root cause

Each section's summary text was written to report a chosen few of its own values rather than to confirm the edit the user just made. A control whose value never appears in any readout gives the user nothing to check against.

## Prevention rule

Every control that changes the model needs an observable that moves with it. Where a summary cannot carry every value, the automated sweep must fall back to the rendered artifact, so "no readout moved" is never mistaken for "the control does nothing".

## How to verify

Run `tools/Invoke-PatternalCanvasEffectProbe.ps1`. It changes each quiet control and compares captures of the pattern canvas, separating controls that redraft the pattern from controls with nothing to show.

# 2026-08-28: A length matcher used as a shape editor folds a dart over itself

## What happened

Re-grading the shirt to a different body produced a front torso panel that would not mesh. GarmentCode reported degenerate triangles, which names a symptom in the mesher and says nothing about the cause. Three attempts chasing the mesher, the hip measurement, and the armhole all failed the same way.

The cause was in the grader. A bust dart is a seam whose two sides are edges of the same piece. `MatchConstructionSeamLengths` treated it as two panels to reconcile, so `MatchCurveLength` bowed one leg toward the other along what it calls the outward normal, which for a self-seam points straight into the opposing leg. The mismatch it was closing was 0.0444 cm over a 21.8 cm seam, two hundredths of one percent. Arc length grows quadratically with the bow near zero, so buying that fraction of a millimetre cost 1.685 cm of sideways travel across a wedge 1.6 cm wide. The dart legs crossed, the boundary self-intersected, and the mesher was handed a bowtie.

## Root cause

Two separate mistakes compounded. The routine did not distinguish a seam joining two panels from a dart closure drafted into one, and it had no floor below which closing a mismatch is not worth any deformation. Neither is visible from the mesher's error.

## Prevention rule

Never reconcile the two sides of a seam that lives on one piece; its geometry was drafted together and is not two independent measurements. Put a relative floor under any length matcher, because a fit that is already inside sewing tolerance must not be bought with shape. And when a routine can only add length by adding curvature, bound the curvature by the clearance to the nearest other boundary edge and fail loudly rather than emitting a crossing.

## How to verify

Run GarmentCode's own per-panel check on a specification before meshing it:

    from pygarment.pattern.core import BasicPattern
    pattern = BasicPattern(path)
    print([name for name in pattern.pattern["panels"] if pattern._is_panel_self_intersecting(name)])

It returns `['front_torso']` for both failing re-grades and `[]` for the original, in about two seconds. That one line settles in seconds what three attempts through the mesher could not.

# 2026-08-28: A tool that skips the pipeline skips the pipeline's checks

## What happened

`Patternal.SimulationPipelineProof --pattern-only` writes a graded specification and returns before the simulation pipeline runs. The repository already had a check that would have named this fault in one line: `PatternTopologyCompiler.ValidateSimpleBoundary` reports "Pattern piece {id} self-intersects between boundary segments". It never ran, because the compiler is inside the pipeline the flag exists to skip. GarmentCode's own self-intersection check also ran and printed a warning rather than raising, so it scrolled past above the traceback.

## Root cause

The fast path was built by removing work rather than by removing only the expensive work. Validation went out with the solver because both lived behind the same return.

## Prevention rule

A shortcut may skip expensive work; it may not skip correctness checks. When adding a flag that returns early, list what the skipped path validated and re-run those checks before the early return. A warning that a downstream stage will crash must raise, not print.

## How to verify

Give `--pattern-only` a garment whose panel boundary crosses itself. It must exit 2 and name the piece, before writing any specification.

# 2026-08-28: Fixing broken geometry can uncover the disagreement it was hiding

## What happened

With the dart fix in place, the re-grade stopped producing a self-intersecting panel and immediately failed somewhere new: `The requested 48.00 cm armscye cannot be drafted at the measured 21.80 cm armhole depth`. Running the same command with the original measurements fails identically, off by 2.39 cm, so this is not a property of the new body at all. The armhole depth and armscye circumference in the profile bridge are not consistent with this block, and they never were.

The refusal was previously unreachable. The self-intersecting panel made the graded garment unmeasurable, `TryMeasureConstructionProfile` returned nothing, and the armscye fit was skipped entirely. A broken panel was standing in for a passing check.

## Root cause

A failure that returns "cannot measure" and a code path that treats "cannot measure" as "nothing to do" combine into a silent skip. The pipeline appeared to work because a defect upstream was suppressing a gate downstream.

## Prevention rule

Distinguish "this does not apply" from "this could not be evaluated". A stage that cannot measure its input must say so and stop, not fall through as though the input needed no work. Expect a real fix to surface further failures, and treat the first one after a fix as evidence rather than as a regression.

## How to verify

Run the re-grade with only `--measurement chest=112`, which reproduces the original grading inputs. It must fail with the armscye refusal, proving the disagreement predates any change of body.

# 2026-08-28: Grading faithfully to a rejected body reproduces its errors in cloth

## What happened

The shirt was graded to the avatar's own measured values, ran the whole pipeline, and passed all twelve gates twice with zero intersections. The renders were worse than the garment it replaced: blousy through the body, a horizontal roll across the waist, a hem that flared and lifted. It was kept out of the packaged application.

The avatar's hip measures 113.45 cm against its 108 cm target, and 36 of its 73 objectives sit outside tolerance. Grading to that hip and adding the pattern's 8 cm hip ease asked for a 121.45 cm garment hip, so the drape showed the avatar's fitting error with ease stacked on top of it.

## Root cause

Two correct-looking stages composed into a wrong result. The avatar fit is producer-rejected and says so, and the grader faithfully reproduces whatever measurements it is given. Neither is wrong on its own, and no gate spans them, because the cloth gates ask whether the garment is physically valid on the body rather than whether the body is the one that was asked for.

## Prevention rule

Do not grade a garment to a body that has not met its own measurement targets. Where a rejected artifact feeds a later stage, make the later stage refuse it rather than relying on judgement; the repository already does this in `tools/prepare_anny_garmentcode_body.py`, which will not read an unaccepted fit report, and the failure here came from reaching for a path that has no such gate. Passing every downstream gate says nothing about whether the upstream input was accepted.

## How to verify

Compare `artifacts/packaged-drape-views-regraded` with `artifacts/packaged-drape-views-restored`. Both are accepted arrangements with zero intersections on the same body; the first is graded to the measured values and is visibly worse. Then confirm the numbers: the avatar measurement report lists hip achieved 113.45 against target 108, and the re-grade resolved a garment hip of 121.45 cm.

# 2026-08-28: The avatar's measurement failures are a range limit, not a fitting failure

## What happened

The Anny fit leaves 36 of 73 measurement objectives outside tolerance, and every downstream problem traces back to it. The obvious reading is that the optimiser needs more steps or better weighting. It does not. Its fitted parameters span exactly minus one to plus one, and twelve of the sixty-five sit on a bound. Four of those twelve are the controls for objectives the garment depends on, and each is pushed to its maximum and still short:

    shoulder breadth      control at +1.0, still 2.77 cm short of target
    underbust girth       control at +1.0, still 3.39 cm short
    chest depth           control at +1.0, still 5.78 cm short
    bust projection       control at +1.0, still 2.87 cm short

No further optimisation can close those. The model has been asked for a body outside the range it can express.

A second failure is structural rather than a range limit. The front hip arc and the back hip arc are driven by one shared control, and they need it to move in opposite directions: the front arc is 8.14 cm too long while the back arc is 2.70 cm too short. One parameter cannot satisfy both, at any value.

The targets themselves explain it. They are the Antonia measurement set, and Antonia is a CharMorph body. The pipeline has been asking one parametric human model to reproduce a body authored in a different one.

## Root cause

A target set was carried across from one avatar family and used as the acceptance criteria for another, and the fit report records a loss without recording that its parameters had run out of room. A saturated control and a control that is simply not converged look identical in a loss curve.

## Prevention rule

Acceptance targets must come from a body the model can actually produce. When a fit misses, check whether its controls are on their bounds before spending effort on the optimiser: a parameter at its limit is a statement about the model's range, not about the search. Report bound saturation in the fit report so this is visible without re-deriving it, and never let two objectives that must move in opposite directions depend on a single shared control.

## How to verify

Run `tools/audit_anny_fit_saturation.py` against the fit report and the measurement report. It sorts every missed objective into a range limit, a contended control, or something a better search could still close, and on the current fit it reports 6 range-limited, 10 contended, and 20 improvable, with 4 of the range-limited ones garment-critical.

By hand: read `fittedParameters` in `artifacts/anny-worker-run-v9/anny-fit-report.json`. Twelve of sixty-five are exactly plus or minus one. Cross-reference them against the `targets` list of each failing objective: `measure-shoulder-dist-incr`, `measure-underbust-circ-incr`, `torso-scale-depth-incr`, and `phenotype:cupsize` are all at plus one while their objectives remain outside tolerance. Confirm the shared-control case by checking that `arc-length|front-hip` and `arc-length|back-hip` both list only `hip-trans-forward`.

# 2026-08-28: The body model that reaches the measurements was already installed

## What happened

Three candidate bodies were compared against the measurements a garment is drafted from, and all three failed: Anny saturates its controls, MHR has parameters for girths and depths only, and Antonia matches the numbers only because they were taken from her and has no controls at all. The conclusion drawn was that a new body model had to be found.

A fourth candidate was sitting in the repository the whole time. MPFB2 is vendored in `third_party/MPFB2`, mirrored into the simulation runtime, and installed as a live Blender 4.5 extension, carrying all 1,258 morph targets including all 40 `measure-*` targets. Anny's 17 named measurement controls are a strict subset of those 40. `tools/generate_mpfb_avatar.py` already fits a body to measurements through them, and its accepted output is shipped at `Patternal/Assets/Production/patterna-full-bust-default-fit-report.json`.

That report hits all twenty of its measurements within a 0.15 cm tolerance, with a largest error of 0.142 cm, no blocking failures, and nothing marked unreachable. It reaches underbust, waist, hip, and neck, the values Anny misses by 3.4 to 5.5 cm with its controls at maximum.

MPFB was not overlooked by accident. It was evaluated, and demoted for appearance rather than capability: the audit records "Useful body controls, but prior MakeHuman-family appearance failed." The most recent reassessment already reverses that and recommends "one CC0 MakeHuman-derived avatar family, evaluated by Patterna-owned morph code."

## Root cause

A rejection was recorded without recording what it was a rejection of. "MakeHuman-family appearance failed" became "MakeHuman is not the answer", and the measurement capability that was never in question went with it. Later work then searched outward for a replacement while the capable option sat vendored, installed, and passing its own acceptance report.

## Prevention rule

Record what a rejection covers and what it leaves standing. An asset rejected on appearance is still a candidate on capability, and the next person to face a capability problem needs to see that. Before searching outward for a replacement component, audit what is already vendored against the requirement, because a repository that has accumulated several attempts probably already contains the answer to at least one of them.

## How to verify

Run `tools/audit_avatar_control_coverage.py` with `--mpfb-fit-report`. It reports MPFB2 as within tolerance on every group its fit exercised, against Anny saturated on four groups and shared on two. Three groups, station depths, front and back arcs, and bust position and projection, are not in that fit report; the targets for them exist in `tools/mpfb_morph_controls.py`, so they are unproven rather than absent.

# 2026-08-28: None of the three bodies on hand can be driven to the measurements a pattern needs

## What happened

The body choice had been argued from renders and from fit losses, and neither settles it. What settles it is whether a model owns an independent control for each quantity a pattern is drafted from, because a missing control cannot be fitted and a control shared between two measurements cannot satisfy both. Measuring all three candidates against the seven control groups the cage contract names gives:

    control group                     Anny        MHR                     Antonia
    vertical landmarks                shared      no parameter            reaches it
    station girths                    saturated   5 quantities            reaches it
    station depths                    saturated   5 quantities            reaches it
    independent front and back arcs   shared      no parameter            reaches it
    bust position and projection      saturated   no parameter            reaches it
    shoulder and armscye              saturated   1 quantity              reaches it
    neck                              missed      no parameter            reaches it

Anny is parametric and fails every group: four by saturation, where its control is at its bound and the target is still missed, two because a single control is shared between measurements that need it to move in opposite directions, and one it simply misses. MHR carries eleven morph parameters covering girths and depths only, with nothing for vertical landmarks, front and back arcs, bust position or projection, or the neck. Antonia reaches every value, because the target set was measured from her, and has no controls at all: she is one authored body and cannot represent anyone else.

So the two models that can be changed cannot reach the targets, and the one that reaches the targets cannot be changed.

## Root cause

Each candidate was adopted for a different strength: Antonia for appearance, MHR for its rig and shell, Anny for differentiable fitting. None was ever checked against the list of measurements a garment is actually drafted from, so the gap only surfaced as a fit that would not converge and a garment that would not hang.

## Prevention rule

Before adopting a body model, enumerate the measurements the product drafts from and require the model to declare an independent control for each. Treat a saturated control and a shared control as failures of the model rather than of the fitter. Appearance, licensing, and rig quality are all necessary and none of them is this check.

## How to verify

Run `tools/audit_avatar_control_coverage.py` against the Anny fit report, the Anny measurement report, and the MHR manifest. It prints the table above and writes the per-objective detail, including which controls are on a bound and which are shared.

# 2026-08-28: A control no garment can enable is dead, not merely disabled

## What happened

Two seam toggles live in the assembly overlay and had never been exercised, because they are hidden until the overlay is opened and a relationship is selected in it. Selecting the first relationship enabled one of them and left the other disabled, which reads like correct behaviour: the first entry is a seam, and the other toggle applies to a closure.

Trying every relationship changes the reading. The crew-neck offers 38 and the wrap dress offers 14, and all 52 are typed as seams. Neither garment the application ships contains a single closure, so `ClosureStateToggle` cannot be enabled by any action a user can take. Two of the crew-neck's entries are even named "Left side bust dart closure" and "Right side bust dart closure" while being typed as seams, which is consistent with the drafting side, where a bust dart is a seam whose two sides belong to one piece.

## Root cause

A test that selects the first item confirms the control responds to the case it happens to land on and says nothing about the others. Disabled is a legitimate state, so a control that is always disabled looks the same as one that is correctly disabled right now, and only trying every case that should enable it tells them apart.

## Prevention rule

For a control that is enabled by a selection, search the selection space for something that enables it, and report the control as unreachable when nothing does. Never conclude from one selection that a disabled control is behaving correctly.

## How to verify

Run `tools/Invoke-PatternalWorkspaceSweep.ps1`. It opens the assembly overlay and walks the relationships until each toggle becomes enabled, recording which relationship did it.

The fix is that the closure control now appears only while the garment declares a closure. The sweep reads the overlay's own summary to separate the two cases, so an inapplicable control is reported as absent by design against a garment with zero closures, and a control that is missing for any other reason still fails.

# 2026-08-28: Coherence is checkable without an instrument; calibration is not

## What happened

The fabric a garment is solved with shipped as fifteen numbers with no provenance: no swatch, no citation, no test method, and an areal density that simply matched a slider preset. The acceptance gate asks for a calibrated fabric, which needs real cloth on a real instrument, so the numbers sat unexamined behind a gate nothing could move.

They were examinable all along, because they are not independent. Areal density and thickness imply a packing fraction against cotton fibre's own density. Flexural rigidity and areal density imply a bending length, the quantity a Peirce cantilever test measures, which has published ranges by fabric class. Shear is always a fraction of tensile in a cloth, never a multiple. On the shipped fabric all six such relations hold: packing 0.234, bending length 1.34 cm inside the 0.8 to 1.8 cm jersey range, membrane stiffness 103 N/m, shear at a tenth of tensile, friction 0.312.

That is not calibration and the audit says so in its own claims. It is the check that comes before it, and this project has already been bitten twice by skipping it: a shear modulus that implied a Poisson ratio of 49 and a negative Lame parameter, and a bending coefficient ninety thousand times too soft. Both are caught by these relations, and both are used as negative tests.

## Root cause

An unreachable gate absorbed a reachable question. Because the fabric could not be certified, it was never asked whether it was even self-consistent, and two material bugs reached the solver that arithmetic would have stopped.

## Prevention rule

When a gate needs evidence you cannot produce, separate what it is really asking from what can still be checked, and check that. Physical parameters constrain each other; verify those relations before simulating anything, and keep coherence and calibration as distinct claims so neither is mistaken for the other.

## How to verify

Run `tools/audit_fabric_coherence.py` against the solver report. The shipped fabric passes all six relations. Perturbing shear above tensile, softening the bending coefficient by five orders of magnitude, or thinning the cloth until its density is impossible each makes it exit non-zero and name the relation that broke.

# 2026-08-28: A blocker was reported for hours without being re-checked

## What happened

The isolated packaged user-interface gate was described, repeatedly and across a whole working session, as unable to run: it needed an official Windows installation image and a one-time elevated Hyper-V bootstrap, so it had never been executed. Every status report repeated that.

It was not true. A Hyper-V guest named `Patternal-UI` existed, was provisioned, carried a clean Windows snapshot from 2026-08-06, and was running at the time the claim was being repeated. `tools/isolated-ui/Get-PatternalIsolatedUiStatus.ps1` reports the host service running, management access granted, the guest running, the guest credential present, a payload staged, and a next step of "Run Invoke-PatternalGuestUiSmoke.ps1". Running it took one command.

The gate then ran to completion in 370 seconds against a payload built from the current source: 47 actions, 46 passed, 25 screenshots, user-interface trees for both workspaces, and a pattern round trip, with no host input injected and no fatal error. One action failed, "Current accepted cloth is available", for the reason this project already understood: the packaged baseline only presents accepted cloth when the document matches nine exact conditions.

## Root cause

A blocker was established once, written down, and then restated from memory instead of from the machine. Nothing re-read the status the repository already published, and the guest was provisioned at some point after the note was written.

## Prevention rule

Re-check a blocker before repeating it, especially one being used to explain why something has not been done. Prefer asking the machine over quoting an earlier answer: a status tool that exists is cheaper to run than a paragraph is to write. Treat "this cannot run" as a claim with a shelf life.

## How to verify

Run `tools/isolated-ui/Get-PatternalIsolatedUiStatus.ps1`. It reports guest state, credential presence, payload identity and the next command, and needs no elevation.

# 2026-08-28: A diagnostic that lists possibilities hides the answer it already has

## What happened

The packaged application has shown "3D cloth is out of date" on a freshly created default pattern for as long as anyone has looked, and the isolated packaged gate fails on exactly one action for the same reason: "the packaged baseline has no accepted cloth for its current pattern, body, assembly, and fabric revision". The message explaining it read "the neckline, shoulder, armscye, sleeve cap, width distribution, or balance differs from the simulated pattern", which names six candidates and commits to none.

The code comparing them had every number in hand. Reporting the differences instead of the categories gives the answer immediately: ten of the eleven construction values differ, and one is not drift at all.

    front width share    51.272 against 48.058
    neckline width       14.207 against 15.823 cm
    front neck depth      9.065 against  9.497 cm
    back neck depth       4.142 against  4.339 cm
    shoulder length      11.640 against 12.970 cm
    shoulder drop         2.370 against  2.483 cm
    armscye depth        19.153 against 20.065 cm
    armscye scoop         2.127 against -9.111 cm
    sleeve cap height    15.193 against 15.657 cm
    front balance         0.032 against  0.034 cm

An armscye scoop of 2.13 cm against minus 9.11 cm is an eleven centimetre difference in one construction value. The shipped cloth was not solved from a slightly older version of the default pattern; it was solved from a materially different garment. The application cannot present it as current, and is right not to.

## Root cause

The message was written to describe a category of failure rather than to report a measurement, so a large and specific divergence was displayed for months as a vague list. Nobody could act on it because nobody could see it.

## Prevention rule

When a check compares numbers, its failure message reports the numbers. Naming the possibilities is the shape of a message written before anyone had the values, and it survives long after they are available. A diagnostic that cannot be acted on is a defect in its own right.

## How to verify

Open the 3D tab on a freshly created pattern and read the out-of-date notice. It now names each differing construction value and both sides of the comparison, so the divergence can be measured rather than guessed at.

# 2026-08-28: Two halves of one check measured different stages of the pipeline

## What happened

With the out-of-date notice finally reporting numbers, the construction comparison could be traced to its two sides, and they were not measuring the same thing.

`MeasurementAwareConstructionProfile` filled the construction controls from `_adaptiveShirtDocument`, the ungraded source block. `GetBundledProductionBaselineMismatch` compared those controls against the construction measured from `BuildBundledProductionGarmentDocument`, which is that same source after `AdaptiveShirtPatternGrader.Adapt` has graded it. Grading moves the construction; that is its job. So the aligner and the checker read opposite ends of one pipeline, and no value the aligner could write would ever satisfy the checker.

The aligner now measures the graded document, which is also the honest number to show a user, because the graded pattern is the one they get. That is a real correction and it stands on its own.

It did not by itself clear the notice. The construction controls hold the same values before and after, so `AlignConstructionControlsToBundledSource` is returning early in this state, through one of its three guards or through `IsBodyAtSourceReference`. That is where the next person should look; the comparison itself is no longer suspect.

## Root cause

Two functions written at different times each picked a reasonable reference document, and nothing required them to pick the same one. The generic failure message hid the disagreement for as long as it existed.

## Prevention rule

When one value is written by one function and checked by another, both must name the same source, and that source should be a single named accessor rather than a document each rebuilds for itself. Where a pipeline has stages, say which stage a measurement belongs to.

## How to verify

Read the out-of-date notice on the 3D tab. It reports each differing construction value with both sides, so the aligner and the checker can be compared directly instead of inferred.

# 2026-08-28: A pattern that does not know what body it was cut to can never match one

## What happened

The packaged application had never once presented its own accepted cloth. Every fresh document showed "3D cloth is out of date", and the isolated packaged gate failed on exactly one action of forty-seven: "Current accepted cloth is available".

The chain runs from a single absent field. `PatternaProductionCrewNeck.specification.json` records `body_parameter_count: 26` and none of the twenty-six values, so the imported garment's `BodyReference` is null. `IsBodyAtSourceReference` returns false on a null reference before comparing anything, so it is false always. `MeasurementAwareConstructionProfile` therefore never takes its measuring branch and fills the construction controls by fitting an armscye instead, giving 51.272, 14.207 and an armscye scoop of 2.127. The baseline check compares those against the graded canonical garment's 48.058, 15.823 and minus 9.111. They can never agree, so `IsBundledProductionBaseline` is permanently false, so the accepted cloth is permanently hidden.

Supplying the body reference at import closes all of it. The application now reports "Accepted Style3D cloth" and shows the Newton Style3D equilibrium on its own default document, and the isolated packaged gate passes 47 of 47 with no host input.

The reference was supplied at import rather than by editing the specification, because that file's hash is declared as its `SourceRevision` and other artifacts reference it; editing it would break provenance across the chain to record a fact the chain already agrees on.

## Root cause

An exporter wrote how many body parameters had been used and dropped their values. Everything downstream needed those values to answer whether the body still matched the pattern, and with them missing the answer defaulted to no, silently and permanently. A count is not a record.

## Prevention rule

When serialising a derived artifact, write the inputs it was derived from, not a count of them. Where a comparison depends on a field that may be absent, distinguish absent from different: `IsBodyAtSourceReference` returning false for a null reference is indistinguishable from a body that genuinely differs, and that ambiguity hid the defect for as long as it existed.

## How to verify

Open the 3D tab on a fresh pattern. The out-of-date notice must be absent and the status must read "Accepted Style3D cloth". Then run `tools/isolated-ui/Invoke-PatternalGuestUiSmoke.ps1`: it must exit zero with 47 of 47 actions passed, including "Current accepted cloth is available".

# 2026-08-29: The fabric gate has an open standard and published readings behind it

## What happened

The calibrated-fabric gate had been treated as a wall: it needs cloth on an instrument, so nothing could be done. Looking outside the repository, which had not been done once, found two things that change what can be said about it.

The field has an open exchange format for exactly this data. Kyosev's 2022 work in the Textile Research Journal defines a JSON and XML structure for the material parameters a drape simulation needs, covering weight and thickness, tensile, shear and bending behaviour, with an MIT-licensed reader and writer at `virtualtextiles/fabrics-drape-data`. It carries no measurements, but it settles what a calibrated fabric record should look like, which had been undefined here.

Published KES-FB2 readings give a range to check against. Bending rigidity for cotton knit fabrics is reported at 0.002 to 0.050 gram-force centimetre squared per centimetre, which converts to 1.96e-07 to 4.90e-06 newton metres. The shipped fabric's 4.21e-06 sits inside it, near the stiff end.

That is not calibration and the audit still reports `calibratedFabric` false, because these are readings of other fabrics of the same class rather than of this cloth. It is a real narrowing all the same: a value outside the range no instrument has reported for this class is a value no swatch would produce either.

## Root cause

A gate that needed a physical measurement was read as a gate nothing could be done about, so the literature behind it went unread for a whole working session even though the user had explicitly asked for open alternatives to be considered.

## Prevention rule

When a requirement needs something you cannot produce, read what the field publishes about it before concluding nothing can be done. A standard defines the shape of the answer, and published measurements bound it, and both are useful long before the measurement itself exists.

## How to verify

Run `tools/audit_fabric_coherence.py`. The seventh relation compares flexural rigidity against the converted published KES-FB2 range and shows the conversion in its working.

# 2026-08-29: The insane bodies were a garment shell that did not follow the body

## What happened

The complaint that started this whole avatar investigation was that the three-dimensional people looked wrong. Nothing in the measurement work explained it, because the measurements were not the cause.

Moving the chest slider to 124 cm tears the figure open. The bust and hips show holes with skin coming through, the shorts have ragged edges, and the body reads as broken geometry. The application says "3D unsupported for this revision, 56 unmapped values, 2D remains authoritative" while rendering it, which is honest about the numbers and says nothing about what is on screen.

The cause is in the display assets, not the morphs. The morph weights are clamped correctly. But the modesty top and briefs are body-conformed shells that receive only height scaling, never the girth morphs, exactly as the asset manifest declares in its own limitations. So the body grows and its clothing does not, and the body comes through it. The shells are valid on one body, the unmorphed one.

They now follow the body instead. Conforming to a surface means moving with it, so each shell vertex borrows the movement of the body vertex it sits against, paired once against the unmorphed body and cached because the pairing does not change when the body does. At chest 124 and hip 122 the shells are intact and sit correctly on the enlarged figure, and the honest unsupported message is unchanged.

Withholding them was the first fix and it removed the tearing, but it left the figure bare while editing, which is worse than it needs to be in an application about clothing. Borrowing the movement keeps them on.

## Root cause

A limitation was written down in the asset manifest and then not enforced anywhere. "Hair, eyes, and modesty assets receive height scaling but not local body fitting" describes a condition under which those assets must not be drawn, and nothing connected the sentence to the renderer.

## Prevention rule

When an asset declares the conditions it is valid under, the code that draws it must read that declaration and honour it. A limitation recorded only in prose is a defect waiting for someone to hit it. And check the visual complaint against the render before assuming it comes from the model that feeds it.

## How to verify

Run `tools/Invoke-PatternalAvatarResponseCheck.ps1`. It moves each body measurement, captures the viewport before and after, and reports whether the body moved. Look at `artifacts/avatar-response/ChestSlider-after.png`: the figure must be intact, with no skin through the modesty shells.

# 2026-08-29: Count what a control sweep cannot reach before trusting its coverage

## What happened

The control sweep reported 29 numeric boxes and the interface inventory said the application has about 151 measurement parameters, and the difference went unexamined. Opening every measurement group first reaches 175 measurement controls, of which 154 are body dimensions rather than garment ease or construction values. The sweep had been exercising a fifth of what exists, and reporting that fifth as though it were the set.

What the wider reach found is mostly reassuring. Of ten sampled body dimensions, seven were accepted and visibly moved the three-dimensional body, spanning the legs, neck, hips, torso and head. Two probes were clamped as out of range, correctly. One, `Total crotch length`, was accepted and moved nothing.

## Root cause

A sweep enumerates what the accessibility tree currently exposes, and a collapsed expander exposes nothing. Coverage was therefore a function of which panels happened to be open when the sweep ran, and nothing compared the count found against the count expected.

## Prevention rule

A coverage number is only meaningful next to the total it is a fraction of. Before sweeping a user interface, open everything that hides controls, count what is reachable, and compare that against what the source declares. A sweep that silently tests a subset is worse than one that fails, because it reports success.

## How to verify

Expand every measurement group and count the spin controls: 175, against 78 with the groups closed.


# 2026-08-29: A two-way binding has not run yet when the control's own event fires

## What happened

Changing `Total crotch length` from 70.4 to 76.4 left the avatar readout saying "MHR baseline preview", as though nothing had been entered. The correct message, "3D unsupported for this revision", did appear, but only after the next edit. Timestamped logging in the message handler and in the value-changed handler showed why: the handler receives `newValue=76.4` while the `MeasurementParameter` behind the box still holds 70.4. A WinUI `NumberBox` raises `ValueChanged` from its own value change, before the `Mode=TwoWay` binding writes that value into the source.

Every consumer in that handler reads the source rather than the event. So the pattern draft, the fit report, the draftability probe and the three-dimensional body were all built from the value the user had just replaced. The readout was not lying about the body; it was describing the previous one, and each edit shifted the lag forward by one.

The draftability probe is the serious part. It calls `BuildCurrentGarmentDocument()` to find out whether the entered value can be drafted, and catches the exception to revert the box. Probing the previous document means it answered a question nobody asked, so for detailed measurements that guard had never tested anything.

The handler now writes the committed value into the bound measurement before any of that work runs, and the revert path restores the measurement as well as the box. The binding's later write matches what is already stored and does nothing, because both measurement models ignore a write inside their own tolerance.

## Root cause

The handler was written as though the binding had already run. Nothing in the type system or the event signature says otherwise, and the defect is invisible on any control that is read by name instead of through its data context, which is why the garment ease and construction boxes on the same page were unaffected.

## Prevention rule

When a control's changed-event handler reads the model the control is bound to, commit the event's value to that model first. Do not infer ordering between a control event and its binding. The tell is a handler that takes `args.NewValue` and then never uses it.

## How to verify

Move `Total crotch length` off its default and read `DrapeAvatarPreviewState`. It must say "3D unsupported for this revision" within a few seconds, not after the following edit. Before the fix the correct message arrived 53 seconds later, on the next change.

# 2026-08-29: Realising a bound control raises its changed event, and a handler cannot tell that from an edit

## What happened

Opening the ten measurement groups took 295 seconds, of which 2 were the probe's own sleeps. Each `NumberBox` inside a newly expanded group starts with no value and raises `ValueChanged` when the binding fills in the value the measurement already holds. The handler treated each of those as an edit: it marked the measurement as manually entered and ran a full re-draft, roughly a second per box, for boxes the user had done nothing to but scroll past.

The cost was the visible symptom. The provenance damage was worse. `IsUserOverride` is exported in the bridge document as "manual" against "estimated", and it gates `SetEstimatedValue`, so measurements the user never touched were recorded as hand-entered and stopped tracking their estimates.

The handler now returns early when the bound measurement already holds the incoming value. Opening the same ten groups takes 3.6 seconds, and a genuine edit still registers and still restores.

## Root cause

`ValueChanged` was read as "the user changed this". It means the control's value changed, which also happens when the control first receives one.

## Prevention rule

A changed-event handler on a templated, bound control must establish that the value is new before treating it as input. Comparing against the bound model is enough and costs nothing. Do not use a null or empty previous value as the test: a user who clears a box and retypes produces exactly that.

## How to verify

Expand every measurement group and time it. It must take seconds, not minutes. Then move one measurement and confirm the avatar readout changes, so the early return has not swallowed real edits.

# 2026-08-29: A screenshot probe measures the window, not the thing you named it after

## What happened

`Invoke-PatternalAvatarResponseCheck.ps1` moved a measurement, hashed the viewport before and after, and reported `avatarChanged`. It reported that every probed dimension moved the body, including dimensions the shipped morph basis has no parameter for. Two separate reasons, found in that order.

The viewport draws its own status panel in the bottom left, and that panel names the current preview mode. Changing a dimension the preview cannot represent switches the text to "3D unsupported for this revision", which rewrites those pixels. The probe recorded the body as having moved when what moved was the label describing the body as unmoved. Excluding the bottom strip removed that.

The second reason has no fix available from the probe side. The viewport draws the body and the garment together, and changing a body measurement re-drafts the pattern, so the garment can account for every changed pixel on its own. The page exposes a `setGarmentVisible` entry point, but nothing in the application calls it, so the garment cannot be hidden through the interface.

The coverage question was answered instead by reading the declarations: `tools/audit_preview_dimension_coverage.py` compares the dimensions the inspector exposes against the parameters the morph basis ships, and needs no running application. The response check kept its narrower, still useful job and its fields were renamed to `viewportChanged` and `changedTheViewport` to say only what it observes.

## Root cause

The probe was named for the conclusion wanted rather than the quantity captured, and the name then stood in for evidence across several sessions. A hash over a rendered window is a fact about the window. Everything drawn in it, including text about the thing being measured, is inside the measurement.

## Prevention rule

Name a probe after what it captures, not what you hope to infer. Before trusting a visual difference, list everything drawn in the captured region and account for each one; if any of them can move independently of the subject, the probe cannot answer the question alone. Prefer reading declarations over rendering when the question is about capability rather than appearance.

## How to verify

Run `python tools/audit_preview_dimension_coverage.py`. It reports 151 editable body dimensions against 13 the preview can move, from source and manifest alone, with no application running and no pixels involved.

# 2026-08-29: A derived value reported as a user change turns a round trip into a permanent complaint

## What happened

Moving the chest slider from 112 to 124 and straight back to 112 left the avatar readout saying "3D unsupported for this revision, 46 unmapped values, 2D remains authoritative", and it stayed there. Nothing the user could see had changed, and no control was left off its starting value.

`ApplyLinkedBaselineMeasurements` derives roughly fifty detailed measurements from the six primary ones, and the payload sent to the viewport counted any detailed measurement more than 0.001 cm from its declared default as a change the preview had to represent. Two things then combine. The derived estimates are rounded to two decimal places, so they do not come back to exactly where they started. And several do not equal their declared defaults even at rest: `headCirc` is derived as `height * 0.337`, which at 167 cm is 56.28 against a declared default of 56.2.

So a slider round trip left dozens of derived values a few hundredths of a centimetre off their declared defaults, each was counted as a dimension the user had asked for, and almost none of them has a morph parameter, so the preview downgraded itself from "MHR baseline preview" to a standing claim that 46 dimensions could not be drawn.

The payload now counts a detailed measurement only when the user actually set it. A derived value carries nothing the six primary measurements do not already carry, and those are reported separately, so counting it again was double counting. The same round trip now reports "MHR partial preview, 11 mapped values", and a measurement the user really does set, such as `crotchLength`, still reports "1 unmapped values" within a few seconds.

## Root cause

Distance from a declared default was used as a proxy for "the user changed this". They are different questions whenever the application can write the value itself, and this application writes about fifty of them.

## Prevention rule

When a field can be set by the user or derived by the application, do not infer which happened from the value. Record it. This model already had `IsUserOverride`; the reporting path simply did not consult it. And when a derived default and a declared default are meant to agree, assert that they do, because here three of them never had.

## How to verify

Press "Reset measurements to defaults", confirm the readout says "MHR baseline preview", move the chest slider to 124 and back to 112, and read it again. It must not claim any unmapped values. Then move `Total crotch length` off its default and confirm it reports exactly one.

# 2026-08-29: A basis built by probing one control at a time must be proven to return to rest

## What happened

The first MPFB morph basis reported that all 85 controls moved the body, which looked like a complete success. The per-control numbers said otherwise. Every control's minimum displacement equalled the previous control's maximum, the figures climbed monotonically through the run, and the count of moved vertices grew from 4,160 to the body's full 13,380 and stayed there. Dozens of unrelated controls, from calf girth to arch height, all reported exactly 12.607 cm.

Each probe was measuring itself plus everything probed before it. `evaluate_morph_controls` skips a control whose source measurements are absent from the profile, and skipping it also means never writing its targets back to rest. Probing such a control set its weight, and nothing ever cleared it, so it stayed in the body for every later probe. The deltas were cumulative sums rather than independent contributions, and a basis like that would have deformed the body into nonsense the moment two measurements were used together.

Each control's targets are now cleared explicitly after its endpoints. The tool also re-measures the body once every probe is done and refuses to write anything if it has not returned to its baseline, which is the check that would have caught this before the numbers had to be read carefully.

## Root cause

The probe loop assumed that setting the inputs for probe N also unset the inputs for probe N-1. That holds only for controls the profile drives, and the profile drives some of them.

## Prevention rule

A basis built by perturbing one input at a time is only valid if every perturbation is undone. Do not infer that from the code that applies the next one; measure the rest state at the end and fail the build if it moved. And read per-item output for shape, not just for success: identical values across items that should differ, or a monotone climb through a loop, is accumulation until proven otherwise.

## How to verify

`tools/generate_mpfb_morph_basis.py` prints "baseline drift after all probes" and exits without writing if that exceeds the displacement floor. In a correct run the per-control maxima vary with the control, and the moved-vertex counts stay local: a bust projection moves far fewer vertices than a body-wide tone control.

# 2026-08-29: A morph basis is anchored to two things, and both have to be the ones that ship

## What happened

The MPFB morph basis loaded, verified, and deformed the body before anything had been edited. The packaged shirt cut through the bust in the first render of it. Two separate anchors were wrong, and each would have been enough on its own.

The first is the value at which a control does nothing. The basis recorded each control's own default, taken from `mpfb_morph_controls`, whose specs were authored around the MakeHuman baseline body. For 29 of the 85 controls that is not what the application ships as the default measurement: `upperBustFullness` rests at 50 where the application ships 85, `deltoidProminence` at 50 where the application ships 0, `chestDepth` at 23.2 where the application ships 31. The preview read the shipped defaults, compared them against those baselines, concluded it was far from rest, and morphed accordingly. Anchoring each parameter to the application's own default fixes it: at the default measurements every weight is zero and the body drawn is the body that ships, while each endpoint still lands exactly on the body measured there.

The second is the body itself. A delta is a difference from the body it was measured on, and it gets added to the body that ships. Those were not the same body. `generate_mpfb_avatar.py` run today produces a display body 7.09 cm away from the packaged `Production/Avatar/body.obj`, so the packaged avatar predates the current pipeline. Nothing in the file formats reveals this: both bodies have 13,380 vertices in the same order, so every count and index check passes.

A third mistake sat underneath: the basis tool ran only the ruler passes of the fit and stopped before the loop that compensates for local deformations, which also re-applies the height. Its baseline body came out 171.7 cm against a requested 167. The fitting sequence is now one shared function that both tools call rather than a full copy and a partial one.

## Root cause

Both anchors were taken from whatever was nearest to hand: the control library's defaults because the control library was already imported, and the packaged body because it was already on disk. Neither was checked against the thing it had to agree with.

## Prevention rule

A basis of differences is defined by where it rests and what it rests on. State both explicitly, and verify both against the artifacts that will actually be used: compare the resting values against the application's declared defaults, and compare the measured body against the packaged body vertex by vertex. Equal vertex counts are not evidence that two meshes are the same mesh.

## How to verify

`tools/package_mpfb_morph_basis.py` prints how many parameters it re-anchored and how far the measured body sits from the packaged one, and refuses to package beyond 0.2 cm of separation. It currently refuses, reporting 7.09 cm, which is correct until the display avatar is regenerated from the current pipeline.

# 2026-08-29: A packaged asset that no tool in the repository can rebuild is a dead end you find late

## What happened

Packaging an MPFB morph basis needs the basis and the body to be the same body. They were not, and chasing why turned into an account of how the packaged avatar was made.

The packaged set is internally coherent. `Production/Avatar/body.obj` and `Production/patterna-mpfb-female.obj` are the same 13,380 vertices in the same order, one with Z up carrying texture coordinates and one with Y up, triangulated, feet on zero, agreeing to within a millionth of a centimetre. The garment was settled on that body. Nothing about the packaged assets is wrong.

What is missing is the ability to rebuild them. Running `generate_mpfb_avatar.py` today produces a body 6.94 cm away from the packaged one after removing any rigid shift, with 85.6% of vertices more than a centimetre out. The garment's own fit report says why: it was produced under `C:\Users\myema\Documents\Codex\2026-07-17\build-a-clothing-pattern-making-windows`, a different working copy, by a version of the pipeline that has since moved on. The conversion between the two body conventions did not exist in this repository at all; it lived in whatever process produced those files.

So the deltas could not be measured against the packaged body, and re-measuring them against a body the current tools produce would need that body packaged, which would need the garment settled on it again.

The conversion step is now `tools/prepare_style3d_body.py`, which reproduces the packaged Y-up triangulated collision body from the packaged Z-up source body exactly, and `tools/build_style3d_source.py` run against a freshly built body reproduces the packaged topology exactly, 133,870 vertices, 262,814 faces and 1,974 seam links.

## Root cause

The packaged assets were promoted as files plus hashes, which proves what they are and not where they came from. Everything needed to re-derive them, the exact tool versions and the steps between them, lived outside the repository, so the assets became a fixed point that later work has to fit around instead of a build product.

## Prevention rule

An asset that cannot be rebuilt from the repository is a constraint on every future change, whether or not anyone notices. When promoting a generated asset, promote the command that generates it too, and prove the claim by rebuilding it and comparing. If a step of the chain only exists in someone's shell history, it does not exist.

## How to verify

`python tools/prepare_style3d_body.py --input Patternal/Assets/Production/patterna-mpfb-female.source.obj --output <temp>` must reproduce `Patternal/Assets/Production/patterna-mpfb-female.obj`: 26,756 triangles and vertices agreeing to 5e-7 cm. Rebuilding the display body itself does not yet reproduce the packaged one, and that gap is the finding.

# 2026-08-29: One application, three different human bodies

## What happened

Chasing why a morph basis could not be packaged ended in an inventory of which body the application is actually using, and the answer is that it depends which part of it you are looking at.

The interactive preview loads the MHR candidate avatar from `Assets/Candidate/MHR/`, a GLB whose morph basis reaches 13 of the 151 measurements a user can edit.

The packaged production assets are MPFB. `Production/patterna-mpfb-female.obj` is the body the shipped garment was settled on, and `Production/Avatar/body.obj` is the same mesh in display form. Their own fit report says they were produced in a different working copy by a version of the pipeline that has since moved on, and running the current tools reproduces neither.

The application's own Simulate flow builds a third body. `SimulationPipeline.cs` runs `generate_charmorph_avatar.py` and requires, in its own words, a "measurement-fitted Antonia display GLB". The MPFB path in that file sits inside `RunLegacyWarpAsync`.

So the body the user edits, the body the packaged cloth was solved on, and the body a fresh simulation would produce are three different models from three different projects. Each pairing inside the application is self-consistent, which is why nothing looks broken from any single view, and why the inconsistency only surfaces when something has to span two of them.

## Root cause

Each body arrived to solve the problem in front of it: MHR for a riggable preview, MPFB because it could hit the measurements, Antonia for appearance. None of the three arrivals removed the one before it, and nothing in the build fails when they disagree, because no artifact is required to be derived from the same body as the artifact next to it.

## Prevention rule

When a project evaluates several implementations of the same thing, adopting one has to include retiring the others, and the build should be able to state which one is in force. A candidate that stays wired in becomes a second answer to a question that can only have one.

## How to verify

`python tools/audit_preview_dimension_coverage.py` reports what the preview's body can represent. `Production/patterna-mpfb-female.obj` names the packaged body. `grep -n "generate_charmorph_avatar\|generate_mpfb_avatar" Patternal/SimulationPipeline.cs` shows which one a fresh simulation would build. Today those are three different bodies.

# 2026-08-29: When two artifacts cannot be made to match, ask whether they need to

## What happened

The interactive preview could only move 13 of the 151 measurements a user can edit. A basis built from MPFB would move 97, and the basis was built, tested and ready. It could not be packaged, because a basis of differences is only valid against the body those differences were measured on, and the body the current tools produce sits 6.94 cm from the body the application ships. Not a rounding difference either: 85.6% of vertices more than a centimetre out.

The obvious way forward was to make them the same body, by regenerating the packaged one. That meant re-solving the garment on it and re-running the six-view acceptance, a pipeline job with several stages that only assemble inside the application. It was the right shape of answer to the question as posed.

The question was wrong. The two artifacts only have to match because of what was being measured. A delta recorded as "how the whole application responds to this measurement" carries local deformations and surface constraints that depend on the positions they start from, so it belongs to one body. A delta recorded as "what this control's MPFB targets contribute" is a sum of additive vertex offsets, so it belongs to the control. Measure the second and the bodies no longer have to match; they only have to share topology, which they do.

That is measured rather than argued. Every run now displaces one control on the unfitted body, again after the ruler fit has moved the body 8.4 cm, and compares. They agree to 0.061 cm, a coupling of 0.723%, which over the 6.94 cm gap is about half a millimetre. The first version of that check used a tolerance of a ten-millionth of a centimetre and failed, correctly, because the coupling is not zero. The fix was to record the real number and defend a tolerance against it, not to widen the threshold until the hypothesis passed.

## Root cause

The constraint was inherited from how the measurement happened to be taken, and then treated as a property of the problem. Nothing had asked what the delta needed to represent for the preview to be right.

## Prevention rule

When two artifacts must agree and cannot be made to, check whether the requirement comes from the problem or from the representation. Changing what is recorded is sometimes cheaper than changing what is recorded about. And when a check you wrote to prove your own idea fails, read the number it gives you before touching the threshold: here it turned an assumption of exact independence into a measured coupling with a stated tolerance, which is a better claim than the one intended.

## How to verify

`tools/generate_mpfb_morph_basis.py` prints the body movement, the disagreement and the coupling on every run, and refuses to write past the tolerance. The report carries `deltaKind`, `bodyCouplingM` and `bodyMovedBetweenMeasurementsM`, and `tools/package_mpfb_morph_basis.py` waives its body-identity check only for a basis declaring `mpfb-target-offsets`. `python tools/audit_preview_dimension_coverage.py` reports 97 of 151.

# 2026-08-29: The 2D authoring surface had never been swept

## What happened

Two sweeps existed, one for the measurement and construction inputs and one for the 3D camera. Neither touched the 2D workspace, which is where a pattern is actually drawn and edited: the piece list, the seam allowance and grainline overlays, the point inspector, and the segment and notch commands. That surface had no automated check at all.

`tools/Invoke-Patternal2DAuthoringSweep.ps1` covers it now, capturing the pattern canvas on its own rather than the whole window so a changed image means the drawing changed rather than some panel's text. Both overlay toggles redraw the canvas and return to the state they were found in. Thirteen of the fourteen pattern pieces redraw when selected, and the fourteenth is the one that was already selected, which the sweep now records rather than reporting as a failure. Engaging point editing brings up all eleven point controls, the reset, split, curve, line and notch commands along with the sewing-edge pair and the four numeric boxes.

The first version of the sweep reported those eleven as missing, because it looked for them before turning point editing on. That is the same mistake as reporting a collapsed measurement group's controls as absent: the tool has to put the interface into the state where the control exists before deciding it does not.

## Root cause

The sweeps were written to chase specific defects, in the measurement inputs and then in the 3D preview, and coverage followed the defects rather than the interface. Nothing had asked which parts of the application no check touched.

## Prevention rule

Coverage should be decided by the interface, not by where the last bug was. Enumerate the surfaces a user works in and check that each has something exercising it, before adding another probe to a surface that already has three.

## How to verify

Run `tools/Invoke-Patternal2DAuthoringSweep.ps1` with the application open. It reports which overlays redraw, which pieces redraw, and which point controls appear once point editing is engaged, and writes the canvas captures beside its report.

# 2026-08-29: Two gates on the same quantity, and the earlier one was the weaker

## What happened

Pressing "Recalculate drape", the application's primary action, failed every time. It died at the Style3D source stage:

```
Initial arrangement failed the common solver input gate:
  minimumTriangleAreaCm2 is 0.000095; expected at least 0.001 cm2
  maximumEdgeStrainRatio is 5.542052; expected at most 2.000
  ninetyFifthPercentileEdgeStrainRatio is 0.396584; expected at most 0.250
```

The stage before it produces a body-aware warm start through the Unreal garment compiler, and the compiler had already written `"accepted": false` into its own preflight report, with those three numbers beside it. The pipeline's check read that file, verified the panel count, the stitch count, the seam gap and the torso clearance, and passed it on. It never read the verdict, and it never looked at the geometry the next stage would measure.

So the compiler said no, the pipeline said yes, and the source builder said no again, at which point the run was over. A user pressing the button saw a failure with no way forward, and the only good drape in the product was the packaged one from an older working copy.

Two things were wrong and both are fixed. The check now applies the same three thresholds the solver input gate applies, and honours the compiler's own `accepted` flag. And a rejected warm start no longer ends the run: the panels settle from their drafted layout instead, which is what the source builder does when given no arrangement at all. That is not a fallback invented to get past the error. Running the source builder against the same body with no arrangement produces a valid source, and a full solve on such a source reaches static equilibrium with zero body collisions, zero self intersections and zero seam separation.

With that, the button gets past the stage that used to end it and reaches the solver.

## Root cause

The same property was gated twice, in two places, with the earlier gate weaker than the later one. A weaker gate upstream of a stronger one is not a safety margin; it is a guarantee that bad work travels further before anyone notices, and that the failure surfaces somewhere that cannot explain it.

## Prevention rule

When a stage hands an artifact to a stage that will check it, check the same things, with the same numbers, from the same place. Better still, read the verdict the producer already wrote rather than forming a second opinion about it. And decide in advance whether a rejected optional input should end the run or simply not be used; here it was optional all along, and treating it as mandatory turned a quality problem into an outage.

## How to verify

Press "Recalculate drape" with the shipped pattern. Before the fix it stopped at `07-style3d-source.log` with the gate message above. Now the compiler's arrangement is dropped, the source builds, and the run reaches `08-style3d-drape.log`.

# 2026-09-13: "The controls work" is not the same claim as "it looks right"

## What happened

Asked directly whether the 3D view looked acceptable, the honest answer was no, and the sweeps that had been reported as verification had never measured appearance at all. They proved that toggles toggle and that measurements move the body. The figure they moved was lit from a 30% flat ambient floor with weak directional terms, so no surface ever had a shadow side; highlights clipped to flat white because nothing tone-mapped them; and the body was lit in linear light while the garment, the grid and every untextured mesh were lit in display space, so they never sat under the same light.

Two further defects only showed once the light had contrast. Morphing the body made it render as flat facets across the torso, because `recalculateIndexedNormals` accumulated per render vertex, and a render vertex is one corner of one UV island, so every copy of a seam vertex saw only its own side. The loader had done it per source vertex; the morph path had not. And after a simulation failed, the status line read "Accepted Style3D cloth · revision 47bf3c0d8f81" with the failed job's own hash on it, because the packaged cloth is shown whenever the body matches the packaged baseline and the label borrowed the current revision's hash to describe it.

The lighting is now computed in linear light for every mesh: hemisphere ambient with a sky above and a warmer ground below, a key light with a wrapped terminator on skin and a hard one on cloth, a small scattering tint at the skin terminator, and a filmic curve before the single conversion to sRGB. Normals are recomputed per source vertex and copied to every render copy. The label names what is on screen.

## Root cause

Verification had been shaped by what was easy to measure. A hash of a canvas answers "did it change", and that is what every probe asked. Nothing asked "does this look like a person in a shirt", and nobody looked at the captures with that question in mind until the user did.

## Prevention rule

When the requirement is visual quality, the evidence has to be a picture, looked at, and the report has to say what was seen. A sweep that proves controls respond is worth keeping and worth stating for what it is; it must not be offered as the answer to a question about appearance. And when lighting gains contrast, re-check every path that computes normals, because flat light hides faceting completely.

## How to verify

`artifacts/preview-look/mpfb-basis-packaged.png` against `artifacts/preview-look/normals-after-production.png` is the same view before and after. `thigh-plus-20.png` against `normals-after-thigh.png` shows the faceting and its absence. The three sweeps still report the same numbers as before the change.

# 2026-09-13: A shading term that cannot be seen is a term with the wrong units

## What happened

The first fold-shading term for the garment compiled, ran, and did nothing: the shirt changed by a mean of 0.16 out of 765 per pixel against the render before it. The term measured curvature as one over the radius in render units, which are metres times two, so a 5 cm fold reads as about 10, and I had scaled it by 0.06 and then applied it only to the ambient light, which is a fifth of the total. It could never have reached one percent of the image. Recalibrated to reach full occlusion at a 2 cm fold and applied to the indirect light, it registers, and the skin, which it must not touch, still measures 0.00.

The packaged six-view capture also failed on its first run after the changes, with "Unsupported Pattern". It found the 3D tab by the name "3D DRAPE", and a text label in the same window now carries that name too, so it tried to select a label. The other sweeps had already moved to the tab's automation id.

## Root cause

A term was judged by whether it compiled and ran rather than by whether it moved the pixels it was written to move, and a control lookup by display name was left in one tool after the others had learned that names collide.

## Prevention rule

When adding a visual term, measure its effect on the region it targets and on a region it must not touch, before looking at the picture; a number of 0.16 out of 765 says more than a glance. Find controls by automation id, and keep the name as a fallback only.

## How to verify

`artifacts/preview-look/normals-after-production.png` against `folds2-after-production.png`: the shirt region differs by a mean of 2.45 and a maximum of 91, the skin region by 0.00. `tools/Invoke-PatternalDrapeViewCapture.ps1` now writes all twelve views into `artifacts/packaged-drape-views-lit`.

# 2026-09-13: Three bodies, and the one a fresh simulation built could never be shipped

## What happened

Pressing "Recalculate drape" ran the simulation on a body the product could not use. `SimulationPipeline.cs` fitted an Antonia body through CharMorph and exported it as a GLB display avatar, while the packaged cloth sat on an MPFB body and the interactive preview had just moved to MPFB as well. `promote_style3d_baseline.py`, the only path from a job to the packaged assets, accepts an MPFB fit report, an MPFB body-preparation report and an OBJ display avatar with seven named parts, and nothing else. So the live path produced jobs that promotion refused by construction, and the two things that could be shipped were the two the live path did not build.

The evidence for which body to keep pointed one way from two directions. Coverage: MPFB maps 93 of the 151 editable measurements, Antonia's named controls are a strict subset of MPFB's measure targets, and the preview already reaches 97 dimensions on MPFB. Physics: the initial drape on the Antonia body left 141 body intersections, and the same solver on the MPFB body left none and settled to an accepted equilibrium.

The live path now runs the MakeHuman recipe the legacy Warp path already held: fit the MPFB body, prepare a rest-pose collider, drape and resolve contact on it, then lower the arms on the fitted body and on the textured display body, prepare the relaxed collider, and let the final settle carry the dressed cloth from the one body to the other through the solver's own start-body animation. That last part is the relaxed stance the packaged figure had been missing.

Two contracts had to move with it. The pipeline refused any runtime whose manifest did not declare the product's backend, and it required a character directory that only Antonia ever had; the installer wrote that declaration, so the declaration, the required-script list and the integrity list changed there. And promotion pinned the fit report to schema 1.2 while the generator had been writing 1.3.

## Root cause

Each body arrived to solve the problem in front of it, and adopting the next one never retired the one before. The live simulation path was the last place the first body survived, and it survived because nothing downstream of it had ever been run to completion.

## Prevention rule

When one artifact is produced by a path and consumed by another, run the pair end to end before calling either finished. A producer whose output has never reached its consumer can be wrong in ways no unit test on either side will show. And when a project adopts an implementation, retire the alternatives in the same change, including the runtime declarations and integrity lists that name them.

## How to verify

`grep -n "generate_charmorph_avatar\|generate_mpfb_avatar" Patternal/SimulationPipeline.cs` shows only the MakeHuman generator in the live path. The runtime manifest at `%LOCALAPPDATA%\Patterna\SimulationRuntime\current\runtime-manifest.json` declares `MakeHuman MPFB2`. Pressing "Recalculate drape" runs stages 01 to 14 and writes `simulation-job.json`.

# 2026-09-13: The last gate is a person, and the message must say so

## What happened

The first end-to-end run on the MakeHuman pipeline went through all sixteen stages. The final Style3D proof was accepted on the relaxed body: static equilibrium at frame 222 after a 180-frame animation from the rest body, zero body collisions, zero self collisions, zero seam separation. The compiler produced the render mesh and Blender rendered the six views. Then the run reported "failed its exact six-view body, garment, and render-hash gate".

Two things were behind that. The render had been invoked with `--hide-bra`, which the Antonia branch of the gate required and the MakeHuman branch forbids, so the proof recorded six avatar objects where seven were expected. And the proof manifest's visual quality was unaccepted with no reviewed render hashes, because that field is written only by `tools/record_product_visual_review.py`, by a person who has looked at the views. That second condition is the human sign-off the product contract calls for, and it is right that software cannot pass it. What was wrong was telling the user the revision had failed, which sends them looking for a defect that does not exist.

The flag is gone, and the pipeline now distinguishes the two cases: when the views exist and only the review is missing, it says so and names the tool.

## Root cause

The render invocation and the gate were written for different avatars, and a single boolean failure hid two unrelated conditions behind one sentence.

## Prevention rule

A gate that a person must pass should say that it is waiting for a person. Report the specific condition that stopped the run, and keep "failed" for the cases where something is actually wrong.

## How to verify

Press "Recalculate drape" with the shipped pattern. The run should end with the message naming `tools/record_product_visual_review.py`, and `proofs/product` in the job directory should hold six views with the bra shell visible.

# 2026-11-16: A resumed job hid a generator that crashed

## What happened

The bra shell on the MakeHuman display avatar rendered as two grey slabs reaching out to the arms. The shell is fitted by casting horizontal rays inward from outside the body, and at the sides those rays hit the raised arms before the torso. The first correction removed every face with any arm-bone weight from the surface the rays are cast onto. The runtime was reinstalled and the simulation run again, and the run reached the six-view render.

That run verified nothing. The job directory for the revision already held an accepted settle, so the pipeline resumed at the compiler stage and rendered the avatar assets written before the correction. The six views still showed the slabs. Run on its own, the corrected generator raised `Could not fit bra shell at theta=0.0000, z=0.7583` and Blender still exited with code 0.

The measurement behind the failure: in `weights.default.json` the summed arm-bone weight is above zero on 4,905 of the 13,380 body vertices, and the innermost of them sits on the chest midline. Within the shell's height band, a weight above 0.5 starts 14.9 cm from the midline of the unfitted base mesh, which is the armpit. Removing every arm-weighted face removed the front of the chest.

The shell now keeps every face in the surface and classifies the hit instead. A ray whose first hit is a face with a mean arm weight above 0.5 walks inward past such faces, stops at the body axis, and keeps the innermost hit when nothing else lies behind, which is the case over the shoulder where the straps run. The regenerated shell spans 18.9 cm either side of the midline where the old one spanned 41.2 cm, and a six-view render of the regenerated avatar shows no slabs. The three Blender stages now pass `--python-exit-code 1`, so a script exception fails the stage.

## Root cause

Three separate things lined up. The correction assumed rig weights are zero away from the arm, without measuring them. Blender reports success when the script it runs raises. And the resume check in `CanResumeAcceptedStyle3DEquilibrium` binds cached stage outputs to the pattern, body and solver reports but not to the runtime scripts that produced them, so changing a generator does not invalidate a job.

## Prevention rule

After changing a runtime script, verify the change by running that script directly and reading its output, before trusting a pipeline run. A pipeline run proves a script change only when the log for that script's stage is newer than the change. Measure a rig weight distribution before using it as a mask.

## How to verify

Compare the timestamp of `01-avatar.log` in the job directory with the time the runtime was installed; the log must be newer. In `display-avatar/bra.obj`, the largest absolute x coordinate should be near the torso half-width, about 0.19 m for the default body, and not near the arm span of 0.41 m.

## Still open

The resume check does not yet compare the runtime's script hashes. Until it does, move the revision's job directory aside before a run that is meant to exercise a changed script.
