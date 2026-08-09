# Lessons learned

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
