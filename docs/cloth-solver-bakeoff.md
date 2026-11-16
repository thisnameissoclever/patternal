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

## 2026-08-22 adversarial stop result

The current closed-seam 0.50 cm arrangement is now frozen as rejected input rather than a solver-tuning candidate. A one-frame input diagnostic recorded 142 initial body intersections, 4,157 initial self-intersections, 469 near-degenerate triangles, 703 extreme slivers, 893 triangles below a 5-degree minimum angle, and a 4.128 cm initial penetration before clearance projection. One frame ended with 297 body intersections, 3,258 self-intersections, p95 strain `0.354`, p99.9 strain `2.763`, and high-strain fraction `0.042916`. No second run is permitted on this arrangement.

The PPF adapter also exposed a contract defect during the same diagnostic. `run_ppf_patterna_bundle.py` resolves `physical_mesh_path` and ignores the source report's declared `output_mesh_path`. It therefore reloaded the flat 55.519 cm spread-panel surface instead of the supplied body-aware arrangement. PPF remains rejected and isolated until an adapter consumes the exact declared bundle input without substitution.

The standard replacement boundary is documented in `docs/revision-bundle-contract.md`. Newton remains a frozen regression control. A materially different solver run requires an arrangement that passes every pre-solve gate and preserves the exact bundle identity.

## Contact-aware arrangement challenger

The adversarial review identified garment assembly, not another round of cloth-parameter tuning, as the unresolved boundary. A deterministic no-install libuipc scene plan now exists for source bundle `9dbe4507d3e54d4af82dde1f37f7f891fbf00e9d8ae6d3bb8dc3285eec7531e2`. It preserves all 14 exact panel topologies and 932 authored seam constraints, and its spread-panel staging passes body-intersection, self-intersection, triangle-area, and finite-position gates. Two preparations produced identical plan ID `ffabb770f508976fd7fbaa3e87868d699583540e2aa6de97cb418479455a17dd` and identical file hashes.

This proves only the immutable adapter and clean input state at preparation time. The bounded execution and stop conditions are in `docs/libuipc-arrangement-challenger-contract.md`.

## 2026-08-28 libuipc first executions

Installation and evaluation-only execution were explicitly authorized. The pinned pyuipc 0.0.25 CUDA runtime executed the declared schedule twice (`tools/fixtures/libuipc-arrangement-schedule-v1.json` and the one-change `-v2` resequencing) through `tools/run_libuipc_arrangement.py` against plan `ffabb770f5…`. Results, all still rejected and unwrapped:

1. The 55.519 cm spread torso closed to `0.245 cm` maximum seam separation in 27 frames of zero-gravity IPC assembly. Collar assembly and attachment, cuff assembly and attachment, sleeve-to-torso caps, and the front-torso center seam all closed to at most `0.31 cm`. A full five-phase run takes about five minutes on the RTX 4090.
2. Six-view diagnostics show a genuinely dressed shirt: wrapped torso, seated shoulders, a closed back, and sleeves formed around both arms. This is the first challenger to assemble the exact 14-panel pattern around the body by contact rather than inheriting a pre-warped shell.
3. One defect repeats identically in both schedules: about 15 contiguous vertex pairs of each sleeve-half join seam near the deltoid stay at a dead-constant `7.6-7.7 cm` separation, roughly the arm diameter, whether the sleeve tube joins before or together with its cap attachment. The evidence and per-frame series live in `artifacts/libuipc-arrangement-exec-run1` and `artifacts/libuipc-arrangement-v2-run1`. Per the contract's three-similar-failures rule, a fresh adversarial review of that specific lock is required before any third materially similar attempt.
4. Three scene-construction facts were discovered and are declared in the schedule and execution reports: sewn panel pairs need their mutual contact disabled for rest-length-zero closure; the assembly-only shell moduli must come from the calibration stretch modulus with the calibration Poisson ratio because the isotropic API otherwise produces a destructive implied Poisson 49 material; and the pinned CUDA backend faults above roughly one hundred pairs per stitch geometry, so groups are split at 64 pairs with identical summed energy.

### First accepted arrangement, 2026-08-28

`tools/verify_exact_triangle_arrangement.py` accepts arrangement `bf25c9972767fd27e0d8b35770c28e31409177c8fc6b5f65f8ce0eea6f789aea`, produced by plan `5f5351d5d2f0564572271333462d71c86fa6ae3cdee5f681317996556d72dbfc` under schedule v5. Every gate passes: 0 cloth-body intersections, 0 cloth self-intersections, 0.306 cm minimum vertex clearance and a proven continuous clearance at or above the 0.25 cm threshold, 0.668 cm maximum seam separation with 0.300 cm at the 95th percentile, 0.468 maximum edge strain with 0.082 at the 95th percentile, no degenerate triangles, consistent panel winding, and both sleeves worn on the arms. The exact 14 panel topologies, 932 authored seam constraints, material coordinates, and source maps are unchanged. This is the first time Patterna has assembled its exact pattern into a worn garment by contact simulation rather than by inheriting a pre-warped shell.

Three declared changes produced it, each answering one measured defect. Plan v3 stages the sleeve and cuff panels in a frame fitted from the collider's own arm axes, because the authored placement sat about 54 degrees off those axes and left 52 seam chords passing through the arm before the first frame; the plan tool now refuses to build when any staged chord intersects the collider. Schedule v4 restores contact between sewn panel pairs except the two that stage inside the contact envelope, which removed all 1,494 self-intersections that whole-pair contact disabling had allowed. Schedule v5 raises the contact envelope above the clearance acceptance threshold, since the two had been declared equal and no engaged contact could then satisfy the gate.

Visual review of the six fixed diagnostic views accepts the construction and rejects the surface for product use: the crew neckline seats at the throat, both short sleeves form around both arms with cuffs, the back is closed, and the hem falls at the hip, but the entire surface carries dense micro-crumple because this is a zero-gravity assembly state with no gravity settle or relaxation stage. The contract's product boundary already covers this: an accepted arrangement is not finished cloth.

Two clean runs of schedule v5 reproduce the acceptance exactly: identical frame counts, identical per-phase early stops, and independent acceptance of both wrapped artifacts. Final vertex positions still differ by up to 25.7 mm in the crumple regions, because both available linear solvers are GPU PCG variants with order-dependent reductions and the pinned release documents no deterministic mode. Gate-level reproducibility is proven; bitwise reproducibility is not available from this runtime.

The v2-schedule execution was wrapped as arrangement `22a1909267c9a19ab0857543e23a3029b740f90624461d149c96ab5a1fe7cbd4` and independently verified. The verifier confirms zero cloth-body intersections through the entire contact-aware assembly, 0.267 cm 95th-percentile seam separation, no degenerate triangles, and passing strain gates. It rejects on the known 7.37 cm sleeve segment, on 1,291 garment self-intersections concentrated around the crumpled unclosed sleeve ends and contact-disabled sewn borders, and on continuous body clearance of 0.245 cm against the 0.25 cm gate, a 0.005 cm shortfall. The verifier's panel-orientation gate was corrected from a mean-normal flatness proxy to per-panel winding consistency because a wrapped torso legitimately points half its normals away from the panel mean; the contract's target was always "local inversions", and the corrected gate passes.

Two identical v2 runs also measured the pinned runtime's determinism: control flow reproduces exactly (identical 1,047 frames and early stops, identical per-phase gate metrics), but final vertex positions differ by up to 64 mm in the crumple regions because both available linear solvers are GPU PCG variants with order-dependent reductions and the pinned release documents no deterministic mode. The declared 0.1 mm vertex-determinism gate therefore fails as written; whether gate-level reproducibility with divergent fold micro-state satisfies the contract's "materially different outputs" stop condition is recorded here as an open adjudication rather than silently redefined.

### First settled drape, 2026-08-28

`tools/run_libuipc_gravity_settle.py` restarts the accepted arrangement with every seam already sewn, switches gravity on, and integrates to rest. It reached static equilibrium in 384 of a 900-frame budget, with a final maximum vertex motion of 0.024 mm against the declared 0.2 mm threshold held for 20 consecutive frames, in 47 seconds on the RTX 4090. The settled result wraps as arrangement `6646046e49aa1017facf7a5532002ba1fe9668bee21af2e11fa54ebedcdc3569` and the independent verifier accepts it: 0 cloth-body intersections, 0 self-intersections, 0.304 cm minimum clearance, 0.562 cm maximum seam separation, 0.498 maximum edge strain, and 0.066 at the 95th percentile.

The fabric is a declared physical estimate for a light cotton poplin (1.0 MPa Young's modulus, 0.3 Poisson ratio, 0.34 mm thickness, 380 kg/m3, 0.05 kPa bending), recorded in `tools/fixtures/libuipc-gravity-settle-v1.json` with its own derivation notes. It is not swatch-calibrated, so no run using it may claim calibrated fabric, and the recipe refuses to execute unless both claims are declared false. Only the source bundle's friction coefficient of 0.35 transferred unchanged; the rest of that document is expressed in the Warp and Style3D solver's own parameterization and has no continuum equivalent.

Visual review of the settled six views splits the verdict. The drape is now credible: gravity pulls the hem down into a natural fall at the hip, the sleeves hang on the arms, the neckline stays seated, and the silhouette reads as a worn t-shirt. The surface is still rejected for product use: dense high-frequency micro-crumple covers the whole garment, consistent with a membrane carrying excess assembled material at a very low bending stiffness. The declared next step is fabric calibration against physical swatch tests, which the roadmap already requires before any preset may be called accurate. Do not tune bending stiffness by eye against these renders.

### Four of the nine acceptance failures are closed, 2026-08-28

The product gate rejected the packaged assets for nine reasons. Four are now closed, each derived from evidence rather than asserted, and the gate still rejects a known-bad asset afterwards, so it has not been loosened.

`patternDraftedForThisBody` is true because the body reaches all six measurements the pattern was drafted to, inside the fit's own tolerance: bust 111.86 against 112, waist 81.96 against 82, hip 107.95 against 108, underbust 84.02 against 84, nape to waist 46.99 against 47, and upper arm 26.003 against 26.

`producerAccepted` is true because the Newton Style3D report declares acceptance with no rejection reasons and names the hashes of these exact two meshes. Its cloth numbers clear every threshold the acceptance contract sets: zero body collisions, zero self-collisions, static equilibrium reached, maximum seam separation 0.0 cm against a 0.25 cm limit, peak edge strain 0.276 against 0.40, p95 0.028 against 0.15, p99.9 0.111 against 0.29, p99.99 0.141 against 0.55, and a high-strain edge fraction of 0.0 against 0.0005.

`sixViewManifestSha256` is present because the six required views can now be captured. The viewport had five cameras and no rear counterpart to the front oblique, so a six-view review was impossible; a rear-oblique view has been added and the capture tool emits the contract's six views in its own order with a hash-bound manifest.

`renderer claims.accepted` is true because the renderer-contract verifier now reports its own result instead of a constant, scoped explicitly to whether the packaged renderer can load and draw these meshes and saying nothing about appearance.

Five remain, and none of them is software's to close. Three are one human decision: somebody has to look at the six images and accept them. One is `calibratedFabric`, which needs real cloth measured on an instrument; the shipped fabric block carries solver values with no provenance, its density matches a user-interface preset, and the project's own bending calibration states in its claims that it is not swatch-calibrated. The fifth, an empty open-gate list, follows from the other four.

### The best drape in the project was already in the assets folder, 2026-08-28

The solved-cloth view now shows the MPFB body wearing the accepted Newton Style3D crew-neck. It is the best result here by a wide margin: a clean neckline, sleeves that hang correctly off the shoulder with even hems, a level hem all the way round, and no drag lines, standing sleeve heads, or flaring. It carries 1,051,256 garment triangles across 526,636 surface vertices, an order of magnitude more than the libuipc results, and it renders on a body that reaches every one of its twenty fitted measurements to within 0.15 cm.

Nothing was solved to produce it. Both meshes have been in `Patternal/Assets/Production` the whole time, reachable only through the bundled-baseline path, which requires the user's document to match nine conditions exactly and therefore almost never fires. `tools/package_existing_drape_pair.py` packages an existing body and garment pair into the same report shape the arrangement exporter writes, so a result that predates the arrangement lane can be shown, measured, and gated alongside one that does not.

Four configurations have now been rendered from the packaged application:

| Body and garment | Triangles | Render |
|---|---|---|
| MPFB body, Newton Style3D crew-neck | 1,051,256 | clean throughout |
| Antonia body, pattern graded to Antonia | 72,313 | clean, minor waist bunching |
| Anny body, pattern graded to Antonia | 72,313 | boxy, sleeve heads stand proud |
| Anny body, pattern graded to Anny | 83,217 | blousy, rolling waist, flaring hem |

The ordering follows the measurement audit exactly. MPFB reaches its targets, Antonia is the body its own pattern was drafted from, and the two Anny rows are the ones whose body cannot reach the measurements the pattern is built around.

The label under the model no longer names a solver. It read "Packaged libuipc cloth solve" regardless of what was loaded, which became false the moment a result from another lane was packaged, so the description and every open gate now travel with the asset and are printed from its own report.

This is still not accepted. `tools/product_drape_acceptance.py` rejects it with the same nine reasons, but they have changed in kind: they are now about evidence that has not been recorded, a visual review and a calibrated fabric and an arrangement verification this pair predates, rather than about a garment that visibly does not fit.

### Three bodies, measured against each other, 2026-08-28

The shirt has now been solved and packaged on three configurations, all accepted by the twelve independent gates with zero body and self intersections. They exist to be compared, and none of them is the answer yet.

| Configuration | Arrangement | Realized ease, cm | Spread |
|---|---|---|---|
| Antonia body, pattern graded to Antonia | `1a10b3b63cff` | 5.7 to 21.0, mean 11.5 | 15.3 |
| Anny body, pattern graded to Antonia | `ee254ffb3c02` | 5.7 to 13.6, mean 9.5 | 7.8 |
| Anny body, pattern graded to Anny | `18b841decbd8` | 6.0 to 22.5, mean 12.8 | 16.5 |

Realized ease is new evidence rather than a restatement. `tools/verify_packaged_drape_assets.py` now cuts nine horizontal sections through both meshes across the garment's own height, takes the convex outline of the torso in each, and reports the gap. It is the first measurement here that asks whether the garment is the right size for the body it is on, rather than whether the cloth is physically valid.

Two honest caveats about it. The sections near the shoulders include sleeve cloth in the torso outline, so the largest numbers in each row are inflated and only the mid-body stations compare cleanly. And it does not separate these three the way the eye does: by ease alone the middle row is the most even, while in the renders the first is plainly the cleanest garment. The visible faults are faults of shape, drag lines and standing sleeve heads, and a girth measurement does not see shape.

An earlier version of this measurement returned numbers like minus 989 cm. It swept the section points by angle about their centroid, and at chest height a horizontal plane cuts both arms as well as the torso, so the sweep threaded a path between three disjoint rings. The convex hull that replaced it cannot do that. The same mistake had already produced a 22 cm armscye from a planar cross-section earlier in the day; a point set is not a curve, and ordering one by angle only works when it is a single convex ring.

The Antonia row is the pattern's own body and produces the cleanest render, and it closes the drafted-for-this-body question by construction. It is not shipped, because the bundle recipe for it records that the Antonia display candidate is visually rejected, which is why the Anny work started. Choosing between a body whose garment fits and a body that passed its own visual review is a product decision, not a solver one, so the packaged application keeps the middle row and the evidence for all three is kept.

### Grading to the measured body made the garment worse, 2026-08-28

The shirt has now been graded to this body's own measured values and taken all the way through the pipeline, and the result is a worse garment than the one it replaced. It is kept out of the packaged application and recorded here as evidence.

The chain ran clean. `Patternal.SimulationPipelineProof --pattern-only` re-graded the block against 27 measurement overrides derived from the avatar worker's own achieved values; the pattern meshed into 42,861 vertices and 83,217 triangles across all 14 panels; bundle `bc9b8daedb31abc77b1b4d5e3dd2912325f6230fc942ce8d1ce0d4f1c27ccc3a` and plan `3f6f5287fbb7ccc34d798151840844f8048d4faee7a87fe89e58f739a9778c36` built; arrangement `bc6886cbdca5aa0e28d9c568222670464406b494767f9dcbe4214128a1f90b04` and settled result `18b841decbd81ae99a36fb852f38b1b2d14ea06afcb040f2c13ddd2afe2dc78d` each passed all twelve independent gates with zero body intersections, zero self-intersections, 0.290 cm minimum clearance and 0.567 cm maximum seam separation.

The renders are the problem. The garment is blousy, carries a heavy horizontal roll across the waist, and its hem flares and lifts. The previous shirt, graded to the other body, reads as a cleaner boxy tee. Twelve passing gates and a worse garment is not a contradiction: the gates ask whether the cloth is physically valid on the body, and it is.

The cause is the body. Its hip measures 113.45 cm against a 108 cm target, one of 36 objectives out of 73 that sit outside their declared tolerance. Grading to that hip and then adding the pattern's 8 cm of hip ease asks for a 121.45 cm garment hip, so the surplus that the drape shows as a rolling, flaring hem is the avatar's own fitting error with ease stacked on top. Grading faithfully to a body that misses its own targets reproduces those misses in cloth.

This settles the order of work with evidence rather than argument, and it agrees with the gate the repository already had: `tools/prepare_anny_garmentcode_body.py` refuses a fit report that is not accepted. The avatar has to meet its measurement targets before a garment graded to it can be better than one graded to something else.

Two defects were found and fixed on the way, both of which stood between any body and any re-grade. `AdaptiveShirtPatternGrader` reconciled the two legs of a bust dart as though they were separate panels and bowed them into each other until the front torso boundary crossed itself, to close a mismatch of two hundredths of one percent. And the armhole record disagreed with the block: the profile bridge carries an armhole depth of 21.8 cm while the block's own armhole measures 19.19 cm tall with a 46.91 cm armscye, and at 21.8 cm the drafter cannot fit any armscye it is asked for. Grading succeeds at the measured 19.19 cm and fails at 21.8 cm across every circumference tried, so the depth is the stale record.

### The solve reaches the packaged application, 2026-08-28

The packaged Windows application now draws the libuipc cloth solve on the body it was solved against. Turning on **Solved cloth** in the 3D tab loads two files that ship inside the package, and the five fixed camera angles can be captured from the running application. Ten images per run are recorded under `artifacts/packaged-drape-views-*`.

Nothing in the renderer changed. It already reads a body surface in Y-up meters and a garment surface in Y-up centimeters carrying texture coordinates and `patterna_seams` and `patterna_edges` line groups, so the work was to produce exactly those two shapes from artifacts the lane already had. `tools/export_packaged_drape_assets.py` reads one arrangement artifact and the revision bundle it was solved against, verifies both by hash, and writes them. Texture coordinates are each panel's own flat material coordinates divided by a declared 10 cm fabric tile, so the weave repeats at a real physical distance instead of being stretched to a unit square. `tools/verify_packaged_drape_assets.py` reimplements the renderer's two parsers and reports what the renderer would actually see, so a malformed export fails as a named issue rather than as an unexplained blank viewport.

Two frame errors surfaced this way and are now gated. Revision bundles put the anatomical front along +z while the viewport expects it along -z, its front camera sitting at yaw 180; the exporter turns both meshes half a turn about the vertical axis, which is a rotation rather than a mirror, so winding, surface orientation, and the body's own left and right all survive, and the garment stays where it settled. The verifier measures the head centroid and refuses any export whose body faces away from the front camera. Run against the first export, that check rejects it and names the reason.

The names carry no acceptance. The assets live in `Assets/SolvedDrape`, the control reads **Solved cloth**, and the label under the model says the arrangement identity, the triangle count, that this is a reference result rather than the pattern being edited, and that the fabric is estimated rather than measured. Every claim in `packaged-drape-assets.json` is false, and `tools/product_drape_acceptance.py` rejects the asset set with exit code 2 and nine named reasons.

### The dressing stance was solved on one angle instead of two, 2026-08-28

Looking at the packaged views is what caught it. From the side, the arms were horizontal but swung about 44 degrees forward of the line through both shoulders, which is not a stance any garment is drafted for. `tools/pose_anny_dressing_body.py` had driven elevation to zero and never constrained azimuth, so each arm stayed at whatever forward swing the rest pose left it, 28 degrees. Every gate still passed, because the sleeves were staged along the collider's own fitted arm axes and the result was internally consistent; only the picture showed it.

The pose search now solves both angles together. Each shoulder rotation is a free axis-angle vector, and Gauss-Newton with a finite-difference Jacobian drives elevation and azimuth to their targets at once; three parameters answer two angles, so the step taken is the minimum-norm one, which is the smallest rotation that satisfies the stance. Both arms reach horizontal and square within 0.03 degrees.

Everything downstream was rebuilt from that stance: bundle `0308b4cb16ee406e696ca9d4cb386eb2c3a2c8f57125db6a1aaa036a8e29efb5`, plan `fb3965794900acfead572b0ec4721e1bf0d85e79afeb3a7b407061a57b961afc`, schedule v8 and settle recipe v5, both identical to their predecessors except for the plan they target. Arrangement `d1b91426814132520df1a41240f331a2568fafbe8d421025ef093bb5d7e261f3` passes all twelve gates, and the settled result `ee254ffb3c024f63f2f031977f86658b053cf68748e1a956fe26766d66991df2` reaches equilibrium in 57 frames and passes all twelve again: zero body intersections, zero self intersections, 0.297 cm minimum clearance, 0.562 cm maximum seam separation, and 0.075 strain at the 95th percentile.

### What the packaged views still show, 2026-08-28

None of this is accepted, and the images say why. The back hem is uneven, with a diagonal drag line across the lower back and the hem rising on the figure's right. The sleeve heads carry small standing ruffles around the armscye. The shirt sits at high hip and reads cropped. All three are fit faults rather than solver faults, and they trace to the same open item: the pattern was graded to the Antonia measurement set and has never been re-drafted for this body.

### The garment is worn by the new avatar, 2026-08-28

The avatar and cloth lanes now share one identity. Revision bundle `cbfb873fea536cba8945926f1566f08f9a02ba11ab850586875f9b21b3727f49` carries the Anny worker's own fitted body as its collider, and the shirt assembles and settles on it: arrangement `09a46ccf85376585b76687e7c3715b1f6d398b97e963369201090b9449962d5e` passes every independent gate with zero body intersections, zero self-intersections, 0.302 cm clearance, 0.556 cm maximum seam separation, and 0.073 strain at the 95th percentile. Gravity equilibrium arrives in 40 frames. The rejected mannequin is no longer anywhere in this chain.

Two things had to be built for it. First, a dressing stance. Anny's rest pose hangs the arms down and forward, straight through the plane where a shirt's front panel must stage, and the plan's own preflight gates refused to build against it: 101 seam chords crossed the body. `tools/pose_anny_dressing_body.py` re-evaluates the same fitted shape, discovers which bone rotation raises each arm by probing the posed bone transforms rather than guessing an axis, and solves the angle that brings each arm axis to horizontal. The shape parameters are untouched; only the pose differs. Rest elevation was 43.2 degrees below horizontal on both sides, and the solved stance reaches horizontal within 0.03 degrees.

Second, staging that follows whatever body it is given. The torso and collar panels had been authored at one body's depth, so they still collided after posing. Staging now places them a declared 8 cm beyond whatever depth the collider actually occupies across each panel's own height band, exactly as the sleeve and cuff panels already followed the collider's fitted arm axes. With that, blocked chords fell from 101 to 0 and the plan builds. Nothing about the panels themselves changed: every placement is still a rigid transform of the exact source geometry.

The honest limits stand. The pattern was graded to the Antonia measurement set and has not been re-drafted for this body, the Anny avatar output remains producer-rejected with measurement objectives outside tolerance, and the fabric constants are still declared estimates.

### Accepted settled drape, 2026-08-28

The current best cloth result is arrangement `1a10b3b63cff17217ed833cc67b430d3cbe7e6e5c9e0e235caf7bae067f2ff13`: the exact 14-panel shirt, assembled by contact simulation on plan `e0d0d92ae43a1a413c83eac77f308578de1aeaef9ab6366949157a9a10a20b9a`, then settled under gravity with the calibrated fabric. The independent verifier passes all twelve gates, including the two that the earlier attempts failed: zero cloth self-intersections and zero body intersections, with 0.303 cm minimum clearance and a proven continuous clearance above the 0.25 cm threshold. Maximum seam separation is 0.567 cm, maximum edge strain 0.499, and 95th-percentile strain 0.072. Gravity equilibrium arrives in 35 frames and 6.2 seconds.

Plan v4 carries one further declared staging change. The two mirror collar front panels are authored coincident at centre front, 0.04 mm apart, which is inside any usable contact envelope and had forced their mutual contact to be disabled. Once the bending coefficient was calibrated the two halves crossed each other four times. Staging each half 0.05 cm onto its own side of centre front puts them 0.96 mm apart, above the 0.6 mm envelope, so no sewn pair needs contact disabled at all and the self-intersection count returns to zero. The first attempt at this moved the halves the wrong way and drove their distance to zero, because anatomical left occupies positive x in this bundle; the plan's chord-clearance gate and the solver's own distance check both refused to run, which is the behavior those gates exist for.

Six-view review accepts the construction and the drape: a symmetric crew neckline seated at the throat, both short sleeves formed on both arms with visible cuff bands, a smooth torso, a closed back, and a hem settled at the hip. Fine surface mottling and a slightly boxy hem flare remain, and the fabric constants are still declared estimates rather than swatch measurements, so this is the best cloth Patterna has produced but it is not a calibrated product claim.

### Bending calibration against beam theory, 2026-08-28

The settled surface's dense micro-crumple was not a fabric-parameter judgement call; it was a wrong number, and it could be derived rather than tuned. `tools/calibrate_libuipc_bending.py` hangs a clamped strip of the declared fabric under gravity in the same solver and compares the tip deflection with the small-deflection cantilever solution for that fabric's own flexural rigidity. The discrete shell bending energy is linear in its coefficient, so a single measured constant maps the coefficient to rigidity; probes at coefficients of 1e6 and 1e8 agreed on that constant to within 0.4 percent.

The declared light cotton poplin has a flexural rigidity of 3.6e-6 N m and a textile bending length of 1.42 cm, which sits inside the usual 1.4 to 2.5 cm range for light shirting and is the quantity a Peirce cantilever test measures. Reproducing that rigidity in this solver requires a bending coefficient of about 4523. The first settle ran at 0.05, roughly ninety thousand times too soft, which is exactly why the cloth buckled at the mesh edge length instead of forming garment-scale folds.

Re-settling with the calibrated coefficient changed both the physics and the picture. Equilibrium arrived in 27 frames instead of 384, and the six diagnostic views show smooth garment-scale drape: a clean sleeve cap, an unbroken chest, a natural diagonal fold from the bust toward the waist, and a settled hem. This is the first Patterna cloth result whose surface reads as fabric rather than as foil.

The calibration produces no fabric acceptance claim. It proves the coefficient is consistent with the declared constants, not that the declared constants describe any real bolt of cloth; swatch measurement still owns that.

That earlier v2 attempt remains rejected and is retained as the evidence trail leading to the accepted plan v3 result above. No cloth claim has changed: acceptance covers the arrangement gate only, and product promotion still requires calibrated fabric behavior, gravity equilibrium, and packaged multi-angle review.
