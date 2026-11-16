# Measurement-native avatar cage proof contract

Status: proposed architecture and acceptance contract. This document does not authorize asset acquisition, dependency installation, or product integration.

## Purpose

Patterna needs one body identity that remains authoritative from an edited measurement through display, collision, pattern drafting, cloth simulation, and packaged review. The existing MHR and Anny routes cannot provide that identity. MHR required local surface correction after its latent fit, while Anny maps 152 controls onto only 66 fitted parameters, leaves 47 controls unsupported, fails 41 of 76 evaluated objectives, and saturates 11 parameters. Reweighting either fitter does not create the missing anatomical controls.

The replacement proof uses a Patterna-owned anatomical cage for measurement semantics and a separately registered CC0 display shell for surface detail. The cage, display shell, rig, accessories, and collision body are different representations of one fitted-state identity. None may silently substitute measurements or retain geometry from another revision.

## Ownership boundaries

1. WinUI owns the editable document, units, Undo and Redo, persistence, stale-state presentation, and accessible interaction.
2. The cage worker owns measurement constraints, landmark positions, fitted cage vertices, topology validation, and the fitted-state identifier.
3. The display worker deforms one approved CC0 shell from the fitted cage. It owns skin, eyes, teeth, hair anchors, modesty geometry, rig transfer, and display-to-cage registration evidence.
4. The collider worker derives a watertight collision body from that same fitted state and proves regional registration against the display body.
5. The pattern worker consumes the accepted fitted-state measurements and regenerates the exact source pattern. It may not replace requested measurements with values achieved by a rejected body.
6. The cloth worker consumes only an accepted body, collider, pattern, seam graph, arrangement, pose, and calibrated fabric revision.
7. The packaged viewer renders accepted hash-bound assets. It does not decide whether a body or cloth revision is accepted.

## Anatomical cage requirements

The first cage supports one adult feminine body family in a shallow symmetric A-pose. Its control graph must expose independent, named degrees of freedom for:

1. Stature and vertical landmarks at crown, neck base, bust apex, underbust, waist, high hip, full hip, crotch, knee, ankle, and floor.
2. Station-specific chest, underbust, waist, high-hip, and full-hip widths and depths.
3. Independent front and back arcs at bust, waist, high hip, and full hip.
4. Bust-apex height, separation, left projection, right projection, and supported lower-pole shaping.
5. Shoulder breadth, left and right shoulder length, shoulder slope, armhole depth, armscye circumference, upper-arm circumference, and arm segment lengths.
6. Neck-base width and depth rather than one undifferentiated neck scale.
7. Abdomen and seat projection without forcing the same parameter to own circumference, depth, and projection.
8. Left and right asymmetry where the Patterna document already exposes it.

Every advertised 3D control must declare the cage vertices and landmarks it may influence. Every unsupported UI value must fail closed as unsupported for 3D while remaining valid for 2D authoring.

## Proof revisions

The proof uses one baseline and two bounded differential revisions. These are control-isolation tests, not population claims.

1. Baseline revision: the current 167 cm full-bust profile from `artifacts/avatar-worker-input-v1/source-bridge.json`.
2. Bust revision: baseline plus 4 cm full-bust circumference, with left and right bust projection each increased by 1 cm. Waist, hip, shoulder, torso length, and arm measurements remain unchanged.
3. Waist revision: baseline plus 6 cm waist circumference and 1.5 cm waist depth. Bust, underbust, hip, shoulder, torso length, and arm measurements remain unchanged.

The deltas exceed twice the relevant measurement tolerances, so a body that ignores or diffuses an edit cannot pass through numerical noise. Each revision must be built from an empty cache. The worker must reject any requested combination it cannot represent anatomically without changing the request.

## Measurement gates

Each proof revision must satisfy all supported garment-critical objectives without altering the requested profile:

1. Stature, nape-to-waist, and waist-to-hip height: absolute error at most 1.5 cm, except stature at most 1.0 cm.
2. Bust, underbust, waist, hip, neck-base, and left and right upper-arm circumferences: absolute error at most 1.5 cm.
3. Chest, underbust, waist, high-hip, and hip depth: absolute error at most 1.5 cm.
4. Front and back hip arcs: absolute error at most 2.0 cm.
5. Bust-apex projection: absolute error at most 1.0 cm.
6. Bust-apex height, bust separation, across-front distance, shoulder breadth, and shoulder-to-wrist length: absolute error at most 1.5 cm.
7. Left and right armhole depth: absolute error at most 1.0 cm.
8. Left and right armscye circumference: absolute error at most 1.5 cm.

The evaluator must report every requested and predicted value, signed error, tolerance, measuring landmarks, fitted-state hash, and whether the objective passed. Aggregate loss is diagnostic only and cannot override an individual failure.

## Geometry and registration gates

Each revision must pass before a display shell or garment is promoted:

1. Stable cage topology and vertex order across all revisions.
2. No non-finite vertices, degenerate triangles, orientation flips, self-intersections, disconnected anatomy, or local vertex patches added after fitting.
3. Anatomically continuous shoulders, arms, neck, bust, abdomen, crotch, hips, hands, and feet in all six required views.
4. One display shell, rig, hair-anchor set, and collider derived from the same fitted-state identifier.
5. The existing backend-neutral global and regional display-to-collider registration gates must pass without threshold changes.
6. Cage-to-display correspondence must cover every display vertex and remain stable across baseline, bust, and waist revisions.
7. Rig landmarks must move with the fitted anatomy, and the shallow A-pose report must pass without post-fit manual correction.
8. Hair, eyes, teeth, eyelashes, eyebrows, and modesty geometry must retain clearance and registration on every proof revision.

## Appearance proof

The proposed CC0 shell is a topology and appearance starting point, not automatic acceptance. For every proof revision, Blender and the packaged viewer must produce exactly these six semantic views:

1. Front.
2. Front-oblique.
3. Left.
4. Back.
5. Back-oblique.
6. Right.

Human review must explicitly accept scalp and hair fit, eyes, mouth, hands, fingers, shoulder shape, bust, underbust, abdomen, waist, hip, arms, modesty geometry, posture, skin response, silhouette, and camera framing. A numerical fit cannot overrule a rejected image.

## Pattern and cloth boundary

No cloth simulation may start until one body revision passes measurement, geometry, rig, registration, and six-view appearance gates.

The first garment proof then requires:

1. A fresh exact 14-panel crew-neck pattern generated from the accepted fitted-state measurements.
2. No negative construction dimensions, stale bust shaping, substituted body values, or inherited armhole and armscye values.
3. Stable panel, curve, seam, dart, notch, grain, material-coordinate, and triangulation identities.
4. A collision-free initial arrangement with outward orientation, no degeneracy, no manual mesh repair, and at most 2 cm maximum staged seam separation.
5. Static equilibrium, zero body and self-intersections, maximum final seam separation at most 0.25 cm, maximum edge strain at most 0.40, p95 at most 0.15, p99.9 at most 0.29, p99.99 at most 0.55, and high-strain edge fraction at most 0.0005.
6. Region-specific evidence for sleeves, sleeve heads, underarms, neckline, bust, waist, back, hem, darts, and every seam family.
7. Six-view Blender and packaged visual acceptance of silhouette, hang, sleeve shape, seam continuity, fabric scale, thickness, body clearance, gravity, and defect freedom.

## Packaged interaction contract

The first accepted integration must prove:

1. Every supported avatar slider visibly changes the intended anatomy and updates its numeric readout.
2. Unrelated anatomical regions remain stable within their declared influence envelope.
3. Undo, Redo, save, reload, restart recovery, and stale-cloth invalidation preserve exact values and revision identity.
4. Camera buttons and avatar, hair, modesty, seam, edge, collision, and solved-cloth toggles round-trip and restore correctly.
5. Missing, disabled, or no-effect controls fail the harness instead of being skipped.
6. The 2D pattern remains editable and authoritative while a 3D build is pending, rejected, or unsupported.
7. The 3D viewport never presents stale or mismatched cloth as current.
8. Keyboard navigation, accessible names, focus visibility, resize, text scale, light and dark themes, and a human Narrator pass remain required.

Routine interaction proof runs in the dedicated Windows VM without host input injection. Final visual quality and frame pacing require a coordinated packaged pass on a supported physical GPU.

## Stop conditions

Stop this route before further investment if any of the following occurs:

1. The cage lacks independent controls for front and back arcs, station-specific depths, bust position and projection, armscye, or longitudinal landmarks.
2. A proof revision requires changing requested measurements, weakening tolerances, local vertex patching, sculpting after fit, or manual rig repair.
3. The display shell cannot register across all three proof revisions with stable correspondence.
4. Anatomy or appearance fails any required view after one focused correction round.
5. Exact-body drafting produces negative construction dimensions or needs inherited values from another body.
6. The same arrangement or cloth failure class recurs after one frozen control run and one documented correction.
7. Asset rights do not cover derivative fitting, source control, offline use, package redistribution, backup, and continued use.
8. The packaged application cannot reproduce the accepted asset hashes or honest stale and unsupported states.

If the cage proof fails, preserve the strong 2D product and offer only static, explicitly accepted 3D body and garment presets. Do not return to a polished display body backed by a different measurement or collision body.
