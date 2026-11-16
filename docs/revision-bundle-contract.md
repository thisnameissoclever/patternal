# Revision bundle contract

This document defines the standard boundary between Patterna's authoritative WinUI document and every external avatar, arrangement, cloth, rendering, and review worker.

## Core rule

One worker run consumes one immutable `patterna.revision-bundle/1.2` directory. A worker may translate declared files, but it may not silently regenerate the body, replace panels, weld or reorder topology, rewrite material coordinates, infer a different pose, substitute a cached result, or accept its own output.

The source bundle always begins with `claims.accepted: false`. Acceptance belongs to later, hash-bound worker reports and human review records. A valid bundle proves identity and completeness of the declared files. It does not prove anatomical quality, cloth quality, or product acceptance.

## Required inputs

Revision bundle version 1.2 requires these source roles:

1. `sourceDocument`: the complete authoritative document for the revision.
2. `bodyProfile`: all body values and the declared supported 3D control envelope.
3. `fittedBodyState`: the fitted-state report from which display and collision outputs were produced.
4. `displayBody`: the exact body shown to the user.
5. `collider`: the exact posed collision surface supplied to the solver.
6. `colliderReport`: registration, topology, measurement, and quality evidence for the collider.
7. `panels`: authoritative 2D panel curves and side identity.
8. `panelMesh`: the exact triangulation used by downstream workers.
9. `panelIndexMap`: the total global-vertex to source-panel and local-vertex ownership map.
10. `seams`: stable seam, notch, and panel-side correspondence.
11. `materialCoordinates`: the unmodified material-space reference used for strain.
12. `fabric`: the fixed calibrated material parameters.
13. `pose`: the fixed body and gravity pose.
Every input is copied into `objects/` under a SHA-256-derived name. The manifest stores only relative bundle paths, original filenames, media types, byte lengths, and hashes. Tool executables and adapters are identified by role, version, byte length, and SHA-256 without being copied into the bundle.

Arrangement is deliberately not a source role. An arrangement worker derives 3D starting positions from this closed source and publishes them as a separate immutable artifact. Treating that output as an input made source authority circular and allowed a rejected placement to masquerade as source truth.

## Derived artifact chain

The authoritative chain contains three separately hash-bound facts:

1. `patterna.revision-bundle/1.2`: immutable authored source. It cannot contain an arrangement and must contain the global panel ownership map required to interpret seam links.
2. `patterna.exact-triangle-arrangement/1.0`: worker-produced 3D positions and solver-neutral seam constraints. It must identify the source bundle and begins unaccepted.
3. `patterna.arrangement-verification/1.0`: an independent verifier's recomputed gates. It must identify both the source bundle and arrangement artifact.

A solver adapter requires all three and may proceed only when the independent verification report is accepted. The arrangement worker cannot issue its own accepted verification capability. Diagnostic or rejected geometry remains useful evidence, but its type and manifest cannot be passed to a solver as accepted input.

## Creation and verification

Use the repository-owned tool:

```powershell
python .\tools\revision_bundle.py create `
  --recipe .\artifacts\revision-proof-source-v2\recipe.json `
  --output-directory .\artifacts\revision-proof-source-v2\bundle

python .\tools\revision_bundle.py verify `
  --bundle .\artifacts\revision-proof-source-v2\bundle
```

Creation refuses to overwrite any existing directory. Verification rejects changed bytes, changed manifest identity, missing files, undeclared files, escaped paths, invalid roles, and any source bundle that claims acceptance. Repeated creation from the same recipe and bytes must produce the same bundle ID.

## Worker protocol

1. Verify the closed source bundle before reading any geometry.
2. Write worker output to a new directory. Never write inside the source bundle.
3. Record the source bundle ID, every consumed input hash, worker executable hash, adapter hash, version, parameters, seed, device, runtime, and output hash.
4. Fail closed when an input role, topology mapping, unit, pose, body identity, seam identity, or material coordinate is unsupported.
5. Keep fit, display, collider, arrangement, arrangement verification, solve, GLB assembly, canonical rendering, and human review as separate reports. No worker accepts its own product quality.
6. Allow a downstream stage only when every required upstream report is accepted and names the exact same bundle and output hashes.
7. Treat cache reuse as a verified optimization. A clean-cache rerun remains a promotion gate.

## Arrangement gate

No solver starts until the arrangement report proves all of the following:

1. Zero cloth-to-body intersections.
2. Zero cloth-to-cloth intersections.
3. At least 0.25 cm body clearance.
4. No inverted or degenerate triangles and at least 0.001 cm2 minimum triangle area.
5. Consistent outward panel orientation.
6. Complete panel, seam, notch, side, and material-coordinate identity.
7. Maximum paired-seam separation no greater than 2 cm for the current proof.
8. Maximum initial edge strain no greater than 2.0 and p95 no greater than 0.25.

Solver sewing strength, projection, remeshing, or post-export vertex repair may not compensate for a failed arrangement. A failed arrangement is an input failure, not an invitation to make the solver angrier.

## Current control

The first local control bundle is `8d2f41b6e4bc64d7c65f5e05d998eda60680d2a204418fd34365f69ab39bee0e`. It used the superseded `patterna.revision-bundle/1.0` schema, which included arrangement as a source role. It remains immutable historical rejection evidence and records these limitations:

1. The source lacks the complete 151-value live UI document.
2. The Antonia display candidate is visually rejected.
3. The 14-panel arrangement fails the initial strain gate.
4. No cloth result is accepted.

The input-only Newton diagnostic found 142 body intersections, 4,157 self-intersections, 469 near-degenerate triangles, 703 extreme slivers, 893 triangles below a 5-degree minimum angle, and up to 4.13 cm body penetration before a meaningful solve. This arrangement is frozen as rejection evidence. It must not be tuned or promoted.

## Packaged acceptance boundary

Offline workers must first produce an accepted GLB and the complete hash-bound numerical and visual record. Only then may the isolated VM package load that exact GLB for 2D and 3D interaction, save and reload, invalidation, camera, slider, toggle, keyboard, resize, theme, and accessibility testing. Narrator and physical-GPU acceptance remain separate human-visible gates.

## Rejected challengers

1. XRTailor is not installed. Its official custom-asset workflow requires Marvelous Designer, a manually dressed and welded OBJ, separate manual UV repair, and mesh annotations. That route cannot consume the native revision bundle without a prohibited commercial authoring round trip and topology substitution.
2. The installed Unreal 5.8 project is not a valid runtime sidecar. It loads fixed cooked garment assets. The exact cloth construction and repair path is editor-only, Dataflow-dependent, and package-mutating.
3. C-IPC remains a contact oracle. Adopting it would require Patterna to build the missing seam system, fabric calibration, arrangement engine, and garment authoring integration, which exceeds the bounded proof.

No other free challenger proceeds until it demonstrates native revision-bundle input, stable seam and material identity, supported Windows packaging, compatible licenses, and a materially different solution to arrangement rather than another contact solver attached to the same rejected mesh.
