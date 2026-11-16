# libuipc arrangement challenger contract

Date: 2026-08-22

Status: dependency installation and evaluation-only execution were explicitly authorized and started on 2026-08-28. The pinned runtime is installed at `%LOCALAPPDATA%\Patterna\ChallengerRuntimes\LibUIPC\v0.0.25-py312-cuda` with the CUDA engine proven on the RTX 4090 and the license conflict recorded in the runtime manifest. The fixed execution schedule is `tools/fixtures/libuipc-arrangement-schedule-v1.json`, executed by `tools/run_libuipc_arrangement.py` and wrapped by `tools/wrap_libuipc_arrangement.py`. Three scene-construction facts discovered at first execution are declared in the schedule and the execution report: contact is disabled between each distinct sewn panel pair because rest-length-zero stitches must reach zero separation (cloth self-collision and cloth-collider contact stay enabled, with contact offsets declared below the smallest staged separations); the shell moduli use the calibration stretch modulus with the calibration Poisson ratio because the isotropic ElasticModuli2D API cannot also take the separate 600 Pa shear value without producing a destructive Poisson-49 material; and every stitch group is split across SoftVertexStitch geometries of at most 64 pairs because the pinned 0.0.25 CUDA backend faults on larger groups while the summed constraint energy stays identical.

## Decision

libuipc is a bounded challenger for one missing operation: contact-aware assembly of the exact 14-panel shirt around the exact revision-matched collider. It is not the owner of the 2D pattern, avatar, seam semantics, product fabric model, final cloth acceptance, rendering, or packaged UI state.

The worker may run only after explicit dependency approval. Its result remains rejected until the independent arrangement verifier accepts it. A successful arrangement may then enter the existing cloth-solver boundary; it does not become accepted cloth merely because libuipc produced finite output.

## Immutable input

The current input is revision bundle `9dbe4507d3e54d4af82dde1f37f7f891fbf00e9d8ae6d3bb8dc3285eec7531e2`, schema `patterna.revision-bundle/1.2`.

The bundle owns:

1. The exact panel vertices, triangles, material coordinates, and stable source maps.
2. The authoritative seam segmentation and global-to-panel index map.
3. The body profile, visible avatar, collision body, fabric declaration, source placements, and tool identities.
4. Rejected acceptance claims. Source data cannot certify its own derived arrangement.

`tools/prepare_libuipc_arrangement_plan.py` converts this bundle into an immutable solver-neutral staging directory. It writes one initial OBJ and one material-space rest OBJ per panel, the fixed collider, 932 exact vertex-pair constraints in 24 panel-pair groups, and the declarative libuipc scene plan. It does not install or import libuipc and cannot authorize execution.

## Proven no-install result

Two fresh preparations produced the same plan ID:

`ffabb770f508976fd7fbaa3e87868d699583540e2aa6de97cb418479455a17dd`

The complete declared file lists and hashes were identical. The staging preflight recorded:

1. Zero cloth-body intersections.
2. Zero cloth self-intersections.
3. Minimum triangle area `0.04234440173269568 cm2`, above the `0.001 cm2` gate.
4. Finite positions.
5. 932 authoritative stitch constraints.
6. Maximum initial seam separation `55.51948801197949 cm` and p95 separation `55.110233763771824 cm`.

The large seam separation is not an acceptance defect in the spread-panel staging state. It is the operation this challenger must solve through a fixed progressive contact-aware assembly policy. It also forbids pretending that a conventional all-at-once cloth solve should somehow invent a dressing sequence.

`tools/verify_libuipc_arrangement_plan.py` independently verifies the manifest identity, exact file set, byte lengths, hashes, source bundle identity, 14 panel mesh counts and source maps, every stitch range, all 932 constraint identities, and the rejected execution and product claims. Its passing scope is `immutable-plan-integrity-only`.

## Pinned runtime under review

The execution target is `pyuipc==0.0.25`, CPython 3.12, Windows x64, CUDA wheel SHA-256:

`b636a64689e1f63e58cef177dce6edd6cea2d454d534234d1f953d5b8ad5b074`

The exact v0.0.25 source tag contains an Apache-2.0 `LICENSE`. The same tag's Python package metadata names that license file but also declares a GPLv3 classifier. This conflict must remain visible in the runtime inventory. It prevents any claim that the package license is unambiguous, although it does not stop a separately approved local evaluation.

If approved, install the pinned wheel into a new Patterna-only challenger runtime. Do not modify the accepted Newton environment, a system Python, the VM, or the application dependency graph. Capture installed-file hashes and all transitive package licenses before execution.

## Fixed assembly experiment

The first execution gets one declared configuration, chosen before reviewing output:

1. Right-handed Y-up coordinates in meters.
2. Zero gravity at `1/120 s` time steps.
3. IPC contact with `dHat = 0.002 m` and friction coefficient `0.35`.
4. `StrainLimitingBaraffWitkinShell` stretch, `DiscreteShellBending`, and `SoftVertexStitch` constraints.
5. Assembly-only cloth constants copied from the official libuipc `cloth_stack` sample. They are not Patterna fabric acceptance values.
6. A static exact collider and the exact 14 source panel topologies.
7. A fixed progressive stitch schedule recorded before the run. Visual retuning is forbidden.
8. One exact source-order output position per vertex, with no welding, remeshing, vertex repair, nearest-neighbor seam inference, or hidden post-snap.

The first run is diagnostic. A second clean run is required to prove determinism before promotion to the independent arrangement gate.

## Independent arrangement gate

The challenger output must be wrapped as `patterna.arrangement-artifact/1.0` with producer acceptance fixed to false. `tools/verify_exact_triangle_arrangement.py` then checks the exact source identity and rejects unless all applicable gates pass, including:

1. Zero cloth-body intersections.
2. Zero cloth self-intersections.
3. No degenerate triangles or local inversions.
4. Complete stable panel, vertex, triangle, material-coordinate, and seam identity.
5. Declared seam proximity and strain limits.
6. At least `0.25 cm` continuous body clearance. The verifier conservatively selects every triangle pair that could violate the threshold, then checks exact vertex-to-face and edge-to-edge distances. A passing report states the proven lower bound instead of inventing a more precise global minimum.

Only a separate accepted verification report may authorize the downstream cloth worker. The libuipc worker cannot mark its own result accepted.

## 2026-08-28 sleeve-lock adversarial review

After two materially similar sleeve-half seam failures, the required fresh adversarial review proved the lock was decided before the first frame: the authored bundle placement stages the sleeve panels about 54 degrees off the collider's near-horizontal arm axes, which put 52 of the 932 seam-constraint chords on straight lines through the arm, and no activation order, spring magnitude, or rest-length ramp has a gradient around a limb. Every constraint whose staged chord missed the body closed; every constraint that failed had a body-blocked chord from frame zero. The sanctioned architecture change is plan v3: the eight sleeve and cuff panels stage in a frame fitted from the collider's own arm axes with the declared policy recorded inside the plan, and the plan preparation now refuses to build any plan whose staged seam chords intersect the collider (`constraintChordClearance` gate). The review also identified that the contact envelope had been declared exactly equal to the 0.25 cm clearance gate, making that gate arithmetically unreachable wherever contact engages, and that the verifier would accept closed-but-wadded sleeves; the verifier now carries a `sleevesWornOnArms` gate, and the contact envelope remains a declared open item pending the plan-v3 measurement.

## Stop conditions

Stop the challenger without parameter fishing when any of these occurs:

1. The reviewed Windows wheel does not install cleanly in the isolated runtime.
2. Its runtime license inventory contradicts the recorded package evidence in a way that makes even local evaluation unacceptable to the owner.
3. The Python API cannot express exact cross-panel stitches, shell strain limiting, bending, and static collision without modifying source topology.
4. The fixed first run loses panel identity, remeshes, welds, produces non-finite state, or violates the immutable output contract.
5. Two clean runs with identical input and parameters produce materially different outputs.
6. The independent verifier rejects, unless one measured defect supports one materially different architecture change. Do not start a force, tolerance, and substep slot machine.
7. Three materially similar failures occur. Preserve evidence, request another fresh adversarial review, and retire the approach unless that review identifies a different foundational contract.

## Product boundary

Even a passing arrangement is not a finished garment. Product promotion still requires calibrated fabric behavior, equilibrium, body and self-contact, seam closure, exact revision identity, six-view Blender evidence, packaged multi-angle review, and live interaction checks in both the 2D and 3D interfaces. The VM remains unnecessary until an offline avatar and cloth candidate clears those gates.
