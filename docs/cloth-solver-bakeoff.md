# Cloth solver bake-off and common bundle process

Status: active engineering standard. No current cloth candidate is accepted.

This document defines the repeatable process for evaluating cloth backends without changing the garment, body, material, or camera contract between runs. It also records the first Antonia/current-shirt control results so rejected output cannot quietly become a baseline later.

## Standard process

1. Export the exact live bridge garment with `Patternal.UnrealGarmentCompiler --garmentcode-pattern-output`. Do not substitute a nearby fixture or a previously accepted shirt.
2. Bind the export to the exact fitted collision body, body profile, pattern SHA-256, and generated-output license.
3. Generate a solver-specific collision proxy only when the exact display body is impractical. Bind it to the canonical body SHA-256 and require one watertight component, preserved orientation, floor error below `0.10 cm`, and bidirectional maximum and 95th-percentile surface drift below `0.50 cm` and `0.15 cm` globally and for head, torso, arms, and legs. The detailed body remains the render authority.
4. Generate the stitch-matched material surface at a declared resolution. Preserve panel ownership, two-dimensional material coordinates, seam correspondence, and rest lengths.
5. Apply the common input gate before starting a solver. The initial arrangement needs finite metrics, at least `0.001 cm2` minimum triangle area, no more than `2.0` peak edge strain, no more than `0.25` 95th-percentile edge strain, and at least `0.25 cm` torso clearance. `build_style3d_source.py` now enforces this gate. `--allow-rejected-initial-arrangement` is a research-only override and is recorded in the source report.
6. Prefer rigid source-panel placement plus explicit progressive sewing over a pre-warped or pre-welded shell. A solver must demonstrate assembly instead of inheriting closed seams from preprocessing.
7. Resolve construction semantics before simulation. Identify finishing pieces separately, close internal construction first, close torso sides next, close both anatomical shoulders next, and attach sleeve caps last. Never infer shoulders from stitch count alone.
8. Run the unchanged fabric and acceptance thresholds. Record backend version, adapter hash, GPU, settings, timings, all source hashes, and whether a dressing-body sequence was used.
9. Reject numerically when any required collision, seam, strain, equilibrium, identity, or finite-position gate fails.
10. Render the exact rejected or accepted result from six anatomical cameras. Front must show the face and chest; Back must show the back and seat. Numerical acceptance does not waive visual review.
11. Record the visual decision against the SHA-256 identity of every rendered view. A rerender always requires a fresh review; do not assume Blender will emit byte-identical PNGs across separate processes.
12. Promote only when the exact result passes both the numerical report and reviewed multi-angle appearance. Package only the promoted hashes.

## Current normalized bundle

1. Body: fitted Antonia collision surface, 34,584 vertices and 69,164 faces, exactly 167 cm tall.
2. Body SHA-256: `98fd0f147a62a0143fed6b286e2efae29e73d65d9de20650fe1262ac6dc901ee`.
3. Pattern: exact live 14-piece adaptive shirt export.
4. Pattern SHA-256: `a92f9a87b3b89c4578b2468fcf9b68a04a544512be7ccaee75529c19c7bcf8e8`.
5. Construction: 38 stitch-matched seams, including physical dart splits.
6. Control backend: Newton 1.4.0 with Warp 1.15.0 on the RTX 4090.
7. Accepted derived collision proxy: 5,002 vertices and 10,000 faces, SHA-256 `fee0a35515594cd295758237d038069ab4955b0c5ff14c7e42dbedfd191b83fd`. Worst bidirectional drift is `0.142 cm`; every regional maximum is below `0.15 cm`, and every regional 95th percentile is below `0.07 cm`.

## Control results

| Run | Input and assembly | Result |
| --- | --- | --- |
| `newton-stage-1` | 0.25 cm mesh, C# body-aware arrangement, welded components | Rejected. 137 body crossings, 1.705 p99.9 strain, and visibly split or collapsed construction. The arrangement already failed its input gate. |
| `newton-rigid-0_5-explicit` | 0.50 cm rigid source placement, explicit progressive sewing, incorrect legacy shoulder inference | Rejected. Collar joins were treated as shoulders. 137 body crossings, 0.525 cm maximum seam separation, 0.854 p99.9 strain, and no equilibrium. |
| `newton-rigid-0_5-explicit-shoulders` | Same bundle with both live torso shoulder seams identified | Rejected. 147 body crossings, 0.535 cm maximum seam separation, 0.818 p99.9 strain, and no equilibrium. Broad strain improved, but sleeve caps and cuffs remained visibly malformed. |
| `newton-rigid-0_5-explicit-shoulders-dressing` | Same bundle assembled around a topology-identical body at 0.9 radial scale, expanded to exact Antonia, released, and settled for 800 frames | Rejected. 134 body crossings, 0.545 cm maximum seam separation, 0.806 p99.9 strain, 0.002847 high-strain edge fraction, and no equilibrium. Six anatomical views confirm underarm collapse, open or malformed sleeve finishing, and excessive rear folds. |
| `newton-rigid-0_5-explicit-finishing-order` | Same dressing-body control with sleeve-to-cuff joins closed before the final sleeve-cap phase | Rejected. Maximum seam separation improved to 0.518 cm and p99.9 strain improved to 0.796, but body crossings rose to 137, 1,320 vertices remained non-static, and six views still show malformed sleeve finishing, underarm collapse, and excessive rear folds. |

The 0.50 cm material surface is the current useful control resolution. It reduces the exact surface from 146,874 to 37,287 vertices and clears the minimum-triangle-area gate. It does not make the current pre-warped arrangement acceptable, and it does not make the Newton result production cloth.

## PPF challenger results

| Run | Input and assembly | Result |
| --- | --- | --- |
| `ppf-patterna-common-bundle-v1` | Exact 0.50 cm garment, full 69,164-face body, 932 authored point stitches | Research-only and rejected after 2 native frames. The solver took 751.260 seconds, or 375.630 seconds per frame. Maximum seam separation was `21.771 cm`, p95 strain was `0.186`, p99.9 strain was `0.597`, and the cloth was nowhere near equilibrium. This establishes the full body as an offline truth input, not an interactive collision mesh. The later adapter-side input gate was not present for this run. |
| `ppf-patterna-common-bundle-1cm-proxy-v1` | Exact 1.00 cm garment, accepted 10,000-face body proxy, 488 authored point stitches, default stitch stiffness `1` and length factor `10` | Research-only and rejected after the correctly configured 20 native frames. Runtime was 390.128 seconds, or 19.506 seconds per frame. Maximum seam separation plateaued at `9.062 cm`, p95 seam separation at `7.319 cm`, p99.9 strain at `0.563`, and final-frame motion at `0.848 cm`. A later strict preflight found 17 garment-to-body pairs inside the required `0.25 cm` initial clearance. |
| `ppf-patterna-common-bundle-1cm-proxy-strong-v1` | Same exact garment and proxy, with a bounded five-frame stitch experiment at stiffness `5` and length factor `50` | Research-only and rejected. Runtime rose to 351.405 seconds, maximum seam separation remained `7.375 cm`, p99.9 strain worsened to `0.692`, and high-strain edge fraction worsened to `0.007749`. Brute-force stitch parameters do not replace a seam-aware dressing stage, and the same 17 initial-clearance violations apply. |
| `ppf-patterna-adapter-preflight-v4` | Exact garment classified into six cumulative construction phases with a `5 cm` direct-capture gate | Rejected before native launch. Internal shaping begins at `3.591 cm`, detached shells at `30.003 cm`, torso shell at `55.519 cm`, finishing bands at `20.533 cm`, neckline at `21.708 cm`, and sleeve caps at `42.512 cm`. Phase 0 alone passes with 46 active links. |
| `ppf-patterna-phase0-native-2f-v1` and `ppf-patterna-phase1-native-5f-free-collar-v1` | Hash-chained free-space internal shaping followed by detached sleeve, cuff, and collar shells | Numerically promising but research-only. Phase 0 closes to `0.215 cm` with `0.0057` p95 strain. The 140-link detached phase closes to `0.217 cm` with `0.0096` p95 strain. It does not prove a dressed garment. |
| `ppf-patterna-phase2-native-6f-dressing035-collar-v1` and `ppf-patterna-phase3-native-3f-dressing035-collar-v1` | Cumulative torso and cuff closure against a hash-bound 35 percent XZ dressing collider | Numerically promising but visually rejected. Torso closure reaches `0.368 cm` with `0.0932` p95 strain; cuff attachment reaches `0.370 cm` with `0.0967` p95 strain. Fresh six-view rendering shows the garment as a densely crumpled mass around the reduced body, with sleeves spread laterally and no credible shirt silhouette. |
| `ppf-patterna-phase4-native-4f-dressing015-v1` and `ppf-patterna-phase4-native-4f-dressing035to010-v1` | Bounded narrow and smooth upper-taper collider comparisons for neckline closure | Rejected. The 15 percent body leaves `5.214 cm` active separation and raises p99.9 strain to `0.461`. The smooth 35-to-10 percent taper leaves `9.542 cm` separation and raises p99.9 strain to `0.486`. A sharper taper was rejected before solve because it flipped 147 collider faces. |

The PPF adapter now preserves exact authored point-pair stitches, records material coordinates and rest lengths, rigidly separates only initially intersecting panels, verifies every pinned runtime entry point, restores source vertex order through PPF's exported object map, and grades every saved snapshot. Its mandatory input gate independently recomputes triangle areas, initial strain, garment self-intersection, body intersection, `0.25 cm` body clearance, semantic construction order, and active seam capture. The raw source's geometry and clearance stage pass, but the direct solve now rejects because its active seams exceed the capture gate. Hash-bound phase continuation and temporary collider generation are proven as tooling. The exact phased cloth is rejected by six-view review.

## Architecture decision

1. Keep Newton as the reproducible control and regression backend.
2. Keep rigid source placement, explicit sewing, semantic seam phases, and the common bundle as backend-neutral inputs.
3. Do not spend another full control run on the rejected C# initial arrangement.
4. Keep the installed ZOZO PPF Contact Solver in its separate versioned runtime as a rejected, reproducible research challenger. Its native GPU path, Patterna adapter, collision proxy, phase classifier, hash-chained continuation, and reduced-body gates are proven. Its current Patterna garment route is not a product candidate: cumulative phases close many seams numerically while producing catastrophic localized folding and a visibly unusable shirt. Revisit PPF only if a materially different solver-specific panel placement or dressing representation is designed. Do not spend more runs on global stitch force, body scale, or taper sweeps.
   PPF's current Snap and Merge contract supports cross-object soft stitches with barycentric anchor evidence and an exact fetched-surface post-snap. The adapter creates anchors from authored seam correspondence and must prove raw soft-stitch closure before post-snap; post-processing cannot turn a rejected solve into accepted cloth.
5. Use IPC Toolkit only as an offline contact oracle if Newton and PPF disagree about a difficult collision case.
6. Do not use XRTailor as the first challenger. Its documented custom-garment workflow starts with Marvelous Designer sewing and draping and imports a welded template, so it does not test Patterna's panel-assembly problem independently.
7. Preserve the audited sleeve contract in every challenger. The exact control is left/right symmetric; cap-to-armscye mismatch is below `0.04 cm`, cuff-to-opening mismatch is zero at displayed precision, and the short underarm connector mismatch is below `0.002 cm`. Those measurements rule out a scrambled or materially mismatched sewing graph, but they do not prove a production-quality sleeve silhouette. A new solver is not allowed to hide malformed construction input.

## Evidence boundary

All named runs and renders are local ignored artifacts under `artifacts/cloth-bakeoff-antonia/control`, `artifacts/ppf-runtime-smoke-v1`, and the named `artifacts/ppf-patterna-*` directories. They prove the decisions above on this machine. They are not packaged release evidence, and none is accepted cloth. Product work returns to the accepted Antonia/Newton route. Any future PPF promotion attempt requires a materially different initial placement or dressing representation, a new hash-bound report, and a fresh six-view set.

The exact Antonia live-contract render under `artifacts/antonia-live-contract/product-render` adds a separate rejected control. It uses the existing production crew-neck OBJ rather than a new solver output. Bounds-based `patterna.product-registration/2.0` accepted it, but exact six-view review found large breast and abdominal holes, an open rear neckline, detached-looking sleeves, and severe side distortion. The recorded visual rejection proves registration is only a coordinate sanity check. It is not garment-quality acceptance.
