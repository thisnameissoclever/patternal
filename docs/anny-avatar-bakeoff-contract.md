# Anny avatar bakeoff contract

Date: 2026-08-22

Status: dependency installation authorized and executed on 2026-08-28. The pinned Anny 0.6.0 runtime is installed, the complete control map is built, and one immutable worker output exists. Producer acceptance remains false; independent numerical verification and human visual review still own every acceptance decision.

## Purpose

This contract defines one bounded visual and numerical bakeoff for replacing Patternal's rejected procedural and MakeHuman-family display mannequins. It does not declare Anny anatomically accepted. The result must pass the same skeptical six-view review that rejected the current body.

The execution artifact is NAVER's official `anny-0.6.0-py3-none-any.whl`, SHA-256 `050a0b24a3e7fdb89b46dc3581947ea84225305425ac9a1a97b65ea997fb2ad6`, from release tag commit `72104cac8242d1735ec06433b65bec5e26953ce7`. The post-release commit `81ca83e202273b306205c1cc15f33734be31e48c` remains reviewed provenance. It is one commit ahead and changes only the optional keypoint regressor's device placement. The body-generation worker does not use that component, so it must not patch or execute the mutable source checkout.

The wheel contains 1,559 native data files totaling 107,825,068 uncompressed bytes. Its embedded metadata names the Apache-2.0 code license and carries the MPFB2 CC0 license. The pinned post-release source metadata references a nonexistent `LICENSE_THINGS` file, so the source checkout is not the execution artifact. This preserves reproducibility without quietly modifying third-party packaging.

## Allowed code and data path

The worker may use only these declared paths:

1. Anny code under Apache 2.0.
2. The native triangular `anny` topology derived from MPFB2 data under CC0.
3. The compact 104-bone `anny` rig.
4. CC0 facial action units when facial review requires them.
5. Apache 2.0 SOMA data only if a later topology interoperability test explicitly needs it.

The worker must reject all of these:

1. `smpl`, `smplx`, and any other noncommercial topology or model path.
2. Any implicit download, including Anny's documented optional noncommercial bundle.
3. Data from a user cache, Hugging Face cache, Torch cache, browser download directory, or another project.
4. Any asset without a recorded source commit, relative path, byte length, SHA-256, and license identifier.

The installation and run environment must set `ANNY_CACHE_DIR` to a versioned Patterna-only directory. Outbound network access must be disabled during the actual worker run. A missing local asset is a hard failure, not permission to fetch it.

## Worker input

The avatar worker consumes one verified source revision bundle plus one immutable control-map document. The control map must contain:

1. Every live Patternal avatar control name and exact value.
2. The declared Anny phenotype, local-change, facial-action, and pose target for each supported control.
3. Units, sidedness, compound-control rules, clamping policy, and unsupported-control reasons.
4. The fixed topology, rig, pose parameterization, dtype, device, and deterministic seed.
5. The pinned Anny wheel, release tag commit, code, and data hashes.

No worker may infer a control from its display label, silently collapse independent left and right values, or claim that an unsupported control changed the body.

The current packaged source capture is guest run `20260822-234508-9fb94f90`, payload `316273a6a303b35081265b48040d8b0af330676274affaa5c9ad43b14bb0e50b`. Patternal generated bridge SHA-256 `0b36af1806853d4f95671976c50ce78de05ba429327746814e019b972218bee8` with 151 unique built-in measurements, one custom row, balanced posture, feminine body template, and the exact adaptive shirt document.

`tools/avatar_worker_input.py` converted that bridge into immutable input ID `ee261b0a14d74c62c577381859617c1d255967deeec404fe3862047fd381b25b`, body-state ID `2358e3d834dba3c9e06ac8f18e6303b19cdcb6ee5396018402cde25445977894`, bound to source revision bundle `9dbe4507d3e54d4af82dde1f37f7f891fbf00e9d8ae6d3bb8dc3285eec7531e2` and the release wheel above. The input preserves every key, value, label, unit, and manual-versus-estimated origin. It explicitly leaves mapping, execution, avatar, display, collider, and product acceptance false.

## Required output

One fresh worker run writes a new immutable directory containing:

1. `avatar-worker-manifest.json` with the source bundle ID, worker hash, Anny release artifact, source provenance, data inventory, configuration, device, runtime, and output hashes.
2. `control-application-report.json` with one row per Patternal control and the exact Anny target that consumed it.
3. A posed display mesh with rig, normals, material slots, and stable vertex identity.
4. A separate watertight collision mesh plus its total display-to-collider source map.
5. Body landmarks, surface regions, anatomical measurements, and collider registration evidence.
6. Front, back, left, right, front three-quarter, rear three-quarter, face, hands, feet, shoulder, bust, waist, and hip renders from fixed cameras.
7. A machine-readable rejection list. The producer begins with `accepted: false` and cannot accept itself.

`tools/avatar_worker_output.py` implements this immutable producer boundary as `patterna.avatar-worker-output-manifest/1.0`. Creation requires every declared artifact and all 13 review renders, verifies one control-application row for every built-in and custom input control, copies files into content-addressed storage, and leaves producer, avatar, display, collider, and product acceptance false. It also requires a complete `patterna.anny-control-map/1.0` document, pins that map to Anny 0.6.0 and the reviewed wheel hash, copies it into the output, and includes its content identity in the output ID. Verification requires the exact immutable input again and rejects changed hashes, escaped paths, undeclared files, incomplete control reports, incomplete or self-accepted maps, implicit-download configurations, and producer acceptance claims.

The historical `patterna.anny-profile-fit/1.0` report from `tools/fit_anny_profile.py` is incompatible by design. That Anny 0.5 diagnostic applied a custom torso cage and could set its own top-level `accepted` Boolean after measurement checks. It carries neither the complete control map nor the independent visual, collider-registration, and product gates required here. Preserve it as historical diagnostic evidence; do not translate its Boolean into this manifest.

After the pinned runtime produces a complete control map and all required artifacts, create and verify the immutable output with:

```powershell
python .\tools\avatar_worker_output.py create `
  --recipe .\artifacts\anny-worker-run\output-recipe.json `
  --input .\artifacts\avatar-worker-input-v2 `
  --output-directory .\artifacts\anny-worker-output

python .\tools\avatar_worker_output.py verify `
  --output .\artifacts\anny-worker-output `
  --input .\artifacts\avatar-worker-input-v2
```

The recipe schema is `patterna.avatar-worker-output-recipe/1.0`. It declares the worker executable and version, the complete `patterna.anny-control-map/1.0` file, fixed topology, rig, dtype, device, seed, offline and implicit-download policy, the exact false producer claims, and every required file role. Creation refuses to overwrite an existing output directory.

## Numerical gates

The independent verifier must prove all of the following before visual review:

1. The complete supported control vector round-trips to the exact source values.
2. Every declared supported control moves the intended anatomical region by more than the measurement noise floor and does not move forbidden regions beyond tolerance.
3. Independent left and right controls remain independent.
4. Height, bust, underbust, waist, hip, shoulder breadth, inseam, arm length, and other supported measurements meet the declared tolerances at the neutral and bounded extreme fixtures.
5. The display mesh has finite vertices, valid oriented triangles, no unintended disconnected components, and no self intersections.
6. The collider is watertight, contains no internal face shell, and remains registered to the display body across every fixture.
7. Two clean runs with the same inputs produce identical canonical mesh, report, and render-input hashes.

## Visual gates

The user-visible avatar passes only after current images are inspected at full resolution. Review must reject any of these:

1. Doll-like, cadaveric, inflated, melted, or visibly procedural anatomy.
2. Implausible shoulder girdle, armpit, breast root, rib cage, pelvis, buttock, crotch, knee, ankle, hand, foot, face, or neck transitions.
3. A body that looks acceptable only from the front.
4. Broken pose balance, asymmetry not requested by controls, collapsed joints, or disconnected gaze and expression.
5. A collider or garment silhouette that visibly disagrees with the displayed body.

Passing measurements cannot overrule rejected anatomy. A flattering render cannot overrule failed identity, registration, or control evidence. The history of this project has supplied ample examples of both mistakes.

## Bounded execution sequence

1. Verify the immutable avatar-worker input against its exact source bridge and revision bundle.
2. Create a dedicated Python 3.12 challenger environment outside the application package.
3. Verify the official wheel byte length, SHA-256, embedded file inventory, and licenses before importing Anny.
4. Prove an offline neutral-body run with the native `anny` topology and rig.
5. Discover the exact phenotype, local-change, facial-action, and bone labels from that pinned runtime.
6. Build the explicit Patternal control map and reject unsupported controls.
7. Run neutral, representative, and bounded-extreme fixtures twice from clean caches.
8. Render all required views through the existing fresh-process Blender worker.
9. Perform independent numerical verification and human visual review.
10. Stop after one bounded integration pass if the base anatomy remains structurally implausible. Do not spend another long cycle polishing a rejected topology.

## 2026-08-28 first worker output

Control map `e73b1d4055ab9ac685271a566f80b077abc2a1a6d23879c4d1ee23ffc9aa42cf` covers all 152 input controls: 105 mapped and 47 unsupported with a specific reason each. The unsupported set is deliberate rather than incidental. It names posture angles the fixed stance owns, tape paths with no separable Anny target, and two stations retired after measurement proved them unusable: the upper-thigh tape sits where the thigh is still merged with the pelvis, so its section perimeter swings between 17 and 54 cm with the selection radius, and Anny's hip-waist-up target translates hip mass vertically instead of changing high-hip girth.

`tools/run_anny_avatar_worker.py` produced worker run v9 and `tools/wrap_anny_worker_output.py` wrapped it as immutable output `49adf707828f7dd24aaa8647e012f4b447069a5d94b56cf805a2910ce25205d2` with all 21 required artifacts: display mesh, watertight collision mesh, display-to-collider map, complete control application report, landmarks, measurements, collider registration, rejection list, and all 13 fixed review renders. Every producer claim is false and the immutable verifier re-checked the output against the exact input before promotion.

Measurement evidence, recorded honestly rather than summarized favorably: 20 of 73 objectives land within 0.75 cm and 38 within 1.5 cm. Bust circumference is 0.52 cm high, stature 0.48 cm low, and mid-thigh 2.63 cm low, while waist is 3.61 cm low, hip 5.45 cm high, and the front-hip arc 8.14 cm high. Neck circumference remains about 8 cm under target with `measure-neck-circ-incr`, `neck-scale-horiz-incr`, and `neck-scale-depth-incr` all railed at their bounds, which is an Anny range limit for this body rather than a fitting defect. The rejection list carries every objective outside its declared tolerance.

Worker determinism holds only against a pinned cache: two runs sharing one `ANNY_CACHE_DIR` produce identical canonical mesh hashes, while a run against an independently rebuilt cache diverges by centimeters, because cache rebuilds produce byte-different model tensors and the bounded fit amplifies them.

Visual review of the 13 renders accepts the base anatomy. The body reads as a plausible adult female with credible shoulder girdle, breast shape, waist, hip, knee, ankle, hand, foot, and facial transitions, which is the gate the previous procedural and MakeHuman-family mannequins failed. One review item stands: a slightly angular junction at the lower breast root. The correction that made this possible was a semantic one, not a tuning pass: Anny orders its gender anchors male first, so the inherited MakeHuman convention of gender 0.0 had been building a male body and multiplying every breast blend shape by a zero female weight.

## Product boundary

Anny remains an external offline worker. Patternal's WinUI process consumes only a hash-bound accepted GLB, collider, control report, and provenance manifest. PyTorch, Anny, optional model code, and their caches do not load into the packaged UI process.

The isolated Windows VM receives the accepted GLB only after this offline gate passes. Packaged sliders and toggles must then be exercised against that exact hash before the avatar work can be called complete.
