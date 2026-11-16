# Open-source stack reassessment, 2026-08-28

## Scope

This reassessment follows the visual rejection of the packaged avatar and cloth.
It asks which existing open-source foundations can credibly own each part of
Patterna without forcing a one-person project to build a human generator, sewing
system, collision solver, renderer, and Windows application from scratch.

This is a research record, not an implementation approval or product-acceptance
claim. Every candidate remains subject to exact local license retention,
dependency approval, reproducible installation, and Patterna's numerical and
six-view visual gates.

## Current failure classification

The two rejected screenshots combine separate failures:

1. The MHR display candidate has distorted proportions, crude appearance assets,
   a visibly poor hair fit, and jagged display-only modesty shells.
2. The packaged garment is a rejected diagnostic cloth result. It has open fit,
   material, and visual gates and is not drafted for the displayed body.
3. Numerical anatomy and solver subreports allowed narrow metrics to pass while
   the product image remained unacceptable.
4. The current UI can expose these rejected assets as a fixed reference. A
   reference label is more truthful than an accepted label, but product-visible
   wreckage still fails the requested CLO-class experience.

Local evidence:

1. `Patternal/Assets/Candidate/MHR/manifest.json` declares `accepted: false` and
   retains pending six-view, collider, cloth, and physical-GPU gates.
2. `Patternal/Assets/SolvedDrape/packaged-drape-assets.json` keeps producer,
   packaged visual quality, calibrated fabric, and correct-body drafting claims
   false.
3. `artifacts/mhr-display-avatar-v1/renders` contains the rejected display views.
4. `docs/canonical-seed-bakeoff.md` records five exhausted garment-transfer
   routes and their collision, seam, and strain failures.

## Candidate foundations

### MakeHuman assets as the authoritative avatar source

The MakeHuman project separates application code from graphical assets. Its
application code is AGPL, while bundled base meshes, proxies, targets, textures,
clothes, poses, and expressions are CC0. The project also states that generated
output is not restricted by the application license. The separate bundled-assets
repository likewise declares its contents CC0.

Sources:

1. [MakeHuman license structure](https://github.com/makehumancommunity/makehuman/blob/master/LICENSE.md)
2. [MakeHuman bundled assets](https://github.com/makehumancommunity/makehuman-assets)

Patterna can therefore evaluate the CC0 meshes and morph targets as data without
embedding the AGPL MakeHuman application. Any third-party community asset still
needs its own exact license check. This route has an important architectural
advantage: the display surface, detailed controls, fitted hair, and collision
surface can be derived from one morph state instead of registering unrelated
bodies after the fact.

MakeHuman assets do not supply a finished Patterna avatar by themselves. Patterna
still needs its own target evaluator, measurement calibration, rig updates,
high-quality skin and eye materials, fitted hair, and packaged visual review.

### MHR as a retired product avatar and retained research comparator

Meta's MHR code and released model are Apache-2.0 and provide detailed parametric
body, face, rig, and pose data. The licensing problem is not the reason for
retirement.

Source:

1. [MHR repository and license statement](https://github.com/facebookresearch/MHR/blob/main/README.md)

Patterna's local statistical fit could not reach the target measurements. The
subsequent local surface correction passed narrow measurement and registration
checks, but the exact six-view output still has unacceptable anatomy,
presentation, hair, hands, and modesty geometry. MHR is retired as Patterna's
product display avatar. Retaining its frozen runtime as research evidence costs
little and prevents the same experiment from being repeated later.

### GarmentCode for pattern semantics and authored assembly

GarmentCode is MIT-licensed and provides panel, edge, interface, stitch, and
parametric garment-program abstractions. Its documented pipeline samples fitted
2D sewing patterns and drapes them over body shapes. This is close to Patterna's
missing construction layer: it knows how a garment is deliberately assembled
before physics begins.

Sources:

1. [GarmentCode repository](https://github.com/maria-korosteleva/GarmentCode)
2. [GarmentCode data-generation and simulation pipeline](https://github.com/maria-korosteleva/GarmentCode/blob/main/docs/Running_data_generation.md)
3. [GarmentCode installation requirements](https://github.com/maria-korosteleva/GarmentCode/blob/main/docs/Installation.md)

The core pattern library is usable as a reference or, after explicit dependency
approval, as an isolated authoring component. Its documented simulation path is
not suitable as Patterna's shipped solver boundary because it requires the
GarmentCode fork of NVIDIA Warp. That fork explicitly permits non-commercial use
only and requires a manual Windows build.

Source:

1. [NvidiaWarp-GarmentCode license and installation statement](https://github.com/maria-korosteleva/NvidiaWarp-GarmentCode)

The supported use is therefore narrow: adopt or reproduce the assembly semantics
that generate a valid initial sewn configuration, then hand the exact Patterna
topology to a separately licensed solver. Do not import the non-commercial Warp
fork into the product.

### libuipc for contact-safe cloth continuation

libuipc is Apache-2.0 and supports Windows, Python and C++ APIs, GPU execution,
Baraff-Witkin cloth, shell bending, frictional contact, sewing-pattern examples,
and vertex stitch constraints. Its incremental potential contact architecture is
designed to keep contact penetration-free during implicit simulation.

Sources:

1. [libuipc repository, capabilities, installation, and license](https://github.com/spiriMirror/libuipc)
2. [libuipc Apache-2.0 license](https://github.com/spiriMirror/libuipc/blob/main/LICENSE)

Patterna already has a reproducible Windows libuipc runtime and has produced
collision-clean numerical solves. The visibly broken results came from invalid
initial garment construction, foreign-body drafting, and weak product gates. A
contact solver cannot infer which sixty-centimeter-separated edges form a shirt.

libuipc should remain the cloth engine candidate, but only after an authored seed
or authored staging system produces a valid current-pattern garment around the
same body that owns the avatar measurements.

### Current NVIDIA Warp as a secondary oracle

Current upstream NVIDIA Warp is Apache-2.0. It is materially different from the
older, non-commercial GarmentCode fork.

Source:

1. [Current NVIDIA Warp repository and license](https://github.com/NVIDIA/warp)

Patterna does not need another primary solver while the construction input is the
proven failure. Current Warp may later serve as a smaller secondary simulation
oracle or regression comparator. Adopting it now would add another solver without
repairing garment assembly.

### Blender as an offline production and review tool

Blender remains appropriate for deterministic asset preparation, high-quality
rendering, and independent six-view evidence. Blender Studio's own realistic
character workflow recommends a clean, correctly scaled A-pose base mesh with
even topology, UVs, and sculpt-friendly structure. That guidance supports using
a polished base as an appearance target, but the published base mesh is not a
measurement system or cloth solver.

Source:

1. [Blender Studio realistic human base-mesh guidance](https://studio.blender.org/training/realistic-human-research/use-of-base-meshes/)

Blender should not become an interactive runtime requirement for Patterna users.
It can remain an offline build and acceptance tool while the packaged app uses
hash-bound GLB and OBJ assets.

## Rejected architecture choices

1. Do not continue MHR local-surface fitting for the product avatar. It has passed
   enough narrow reports while failing the actual image.
2. Do not use a foreign garment mesh and shrinkwrap, project, or Laplacian-fit it
   onto the current body. Five variants have established the same topology and
   collision failure.
3. Do not replace libuipc merely because it received invalid initial geometry.
4. Do not ship the GarmentCode Warp fork. Its non-commercial license and manual
   Windows build make it a poor reusable product boundary.
5. Do not make Blender a required interactive process behind every slider change.
6. Do not permit any numeric subreport to override a rejected six-view product
   review.

## Recommended design direction

The strongest reusable composition is:

1. Keep WinUI and Patterna's document model as the interactive 2D product.
2. Replace the MHR product candidate with one CC0 MakeHuman-derived avatar family,
   evaluated by Patterna-owned morph code so display, hair, rig, measurement
   controls, and collision geometry share one identity.
3. Use GarmentCode's MIT panel and interface model as the reference for deliberate
   garment construction. Re-author the exact current shirt as a valid assembled
   program rather than transferring a foreign solved mesh.
4. Feed the resulting exact, reversible sewn topology to the existing Apache-2.0
   libuipc runtime for contact-safe continuation and calibrated cloth behavior.
5. Use Blender only for offline preparation and six-view acceptance renders.
6. Keep every rejected asset behind a developer-only diagnostic boundary. Product
   mode displays either accepted current-revision cloth or an honest unavailable
   state.

This direction minimizes custom physics work while removing the two failed
ownership splits: one body for appearance and another for measurements, and one
garment for visual reference and another for the editable pattern.

## Approval boundary

No dependency should be added from this research alone. The next implementation
decision needs explicit approval for:

1. A Patterna-owned evaluator over pinned CC0 MakeHuman assets.
2. Either importing PyGarment under MIT in an isolated runtime or reproducing only
   the small assembly model needed by Patterna.
3. Keeping libuipc as the primary solver while replacing its garment-construction
   input.

The first proof should remain bounded to one crew-neck shirt, one shared avatar
identity, one shallow A-pose, and one predeclared measurement and pattern boundary
revision. Broader garment types belong after that proof passes the full visual and
interaction gates.
