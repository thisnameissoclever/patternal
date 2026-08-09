# Cloth solver bake-off and common bundle process

Status: active engineering standard. No current cloth candidate is accepted.

This document defines the repeatable process for evaluating cloth backends without changing the garment, body, material, or camera contract between runs. It also records the first Antonia/current-shirt control results so rejected output cannot quietly become a baseline later.

## Standard process

1. Export the exact live bridge garment with `Patternal.UnrealGarmentCompiler --garmentcode-pattern-output`. Do not substitute a nearby fixture or a previously accepted shirt.
2. Bind the export to the exact fitted collision body, body profile, pattern SHA-256, and generated-output license.
3. Generate the stitch-matched material surface at a declared resolution. Preserve panel ownership, two-dimensional material coordinates, seam correspondence, and rest lengths.
4. Apply the common input gate before starting a solver. The initial arrangement needs finite metrics, at least `0.001 cm2` minimum triangle area, no more than `2.0` peak edge strain, no more than `0.25` 95th-percentile edge strain, and at least `0.25 cm` torso clearance. `build_style3d_source.py` now enforces this gate. `--allow-rejected-initial-arrangement` is a research-only override and is recorded in the source report.
5. Prefer rigid source-panel placement plus explicit progressive sewing over a pre-warped or pre-welded shell. A solver must demonstrate assembly instead of inheriting closed seams from preprocessing.
6. Resolve construction semantics before simulation. Identify finishing pieces separately, close internal construction first, close torso sides next, close both anatomical shoulders next, and attach sleeve caps last. Never infer shoulders from stitch count alone.
7. Run the unchanged fabric and acceptance thresholds. Record backend version, adapter hash, GPU, settings, timings, all source hashes, and whether a dressing-body sequence was used.
8. Reject numerically when any required collision, seam, strain, equilibrium, identity, or finite-position gate fails.
9. Render the exact rejected or accepted result from six anatomical cameras. Front must show the face and chest; Back must show the back and seat. Numerical acceptance does not waive visual review.
10. Record the visual decision against the SHA-256 identity of every rendered view. A rerender always requires a fresh review; do not assume Blender will emit byte-identical PNGs across separate processes.
11. Promote only when the exact result passes both the numerical report and reviewed multi-angle appearance. Package only the promoted hashes.

## Current normalized bundle

1. Body: fitted Antonia collision surface, 34,584 vertices and 69,164 faces, exactly 167 cm tall.
2. Body SHA-256: `98fd0f147a62a0143fed6b286e2efae29e73d65d9de20650fe1262ac6dc901ee`.
3. Pattern: exact live 14-piece adaptive shirt export.
4. Pattern SHA-256: `a92f9a87b3b89c4578b2468fcf9b68a04a544512be7ccaee75529c19c7bcf8e8`.
5. Construction: 38 stitch-matched seams, including physical dart splits.
6. Control backend: Newton 1.4.0 with Warp 1.15.0 on the RTX 4090.

## Control results

| Run | Input and assembly | Result |
| --- | --- | --- |
| `newton-stage-1` | 0.25 cm mesh, C# body-aware arrangement, welded components | Rejected. 137 body crossings, 1.705 p99.9 strain, and visibly split or collapsed construction. The arrangement already failed its input gate. |
| `newton-rigid-0_5-explicit` | 0.50 cm rigid source placement, explicit progressive sewing, incorrect legacy shoulder inference | Rejected. Collar joins were treated as shoulders. 137 body crossings, 0.525 cm maximum seam separation, 0.854 p99.9 strain, and no equilibrium. |
| `newton-rigid-0_5-explicit-shoulders` | Same bundle with both live torso shoulder seams identified | Rejected. 147 body crossings, 0.535 cm maximum seam separation, 0.818 p99.9 strain, and no equilibrium. Broad strain improved, but sleeve caps and cuffs remained visibly malformed. |
| `newton-rigid-0_5-explicit-shoulders-dressing` | Same bundle assembled around a topology-identical body at 0.9 radial scale, expanded to exact Antonia, released, and settled for 800 frames | Rejected. 134 body crossings, 0.545 cm maximum seam separation, 0.806 p99.9 strain, 0.002847 high-strain edge fraction, and no equilibrium. Six anatomical views confirm underarm collapse, open or malformed sleeve finishing, and excessive rear folds. |

The 0.50 cm material surface is the current useful control resolution. It reduces the exact surface from 146,874 to 37,287 vertices and clears the minimum-triangle-area gate. It does not make the current pre-warped arrangement acceptable, and it does not make the Newton result production cloth.

## Architecture decision

1. Keep Newton as the reproducible control and regression backend.
2. Keep rigid source placement, explicit sewing, semantic seam phases, and the common bundle as backend-neutral inputs.
3. Do not spend another full control run on the rejected C# initial arrangement.
4. Evaluate ZOZO PPF Contact Solver next in a separate versioned runtime after explicit dependency approval. Give it this same 0.50 cm bundle, body, fabric, seam graph, cameras, and gates.
5. Use IPC Toolkit only as an offline contact oracle if Newton and PPF disagree about a difficult collision case.
6. Treat the current adaptive sleeve-cap and cuff behavior as a possible pattern or seam-contract defect as well as a solver result. A new solver is not allowed to hide malformed construction input.

## Evidence boundary

All named runs and renders are local ignored artifacts under `artifacts/cloth-bakeoff-antonia/control`. They prove the decisions above on this machine. They are not packaged release evidence, and none is accepted cloth. The next promotion attempt must generate a new hash-bound report and a fresh six-view set.

The exact Antonia live-contract render under `artifacts/antonia-live-contract/product-render` adds a separate rejected control. It uses the existing production crew-neck OBJ rather than a new solver output. Bounds-based `patterna.product-registration/2.0` accepted it, but exact six-view review found large breast and abdominal holes, an open rear neckline, detached-looking sleeves, and severe side distortion. The recorded visual rejection proves registration is only a coordinate sanity check. It is not garment-quality acceptance.
