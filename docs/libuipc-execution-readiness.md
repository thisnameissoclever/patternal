# libuipc execution readiness

Date: 2026-08-28

Status: implemented as a fail-closed pre-execution verifier. It is not yet wired into the active arrangement runner because that runner is owned by another live development session.

## Purpose

Plan integrity and execution readiness answer different questions.

1. `tools/verify_libuipc_arrangement_plan.py` proves the immutable plan identity, declared file hashes, exact panel topology, stitch identities, runtime target, and rejected producer claims.
2. `tools/verify_libuipc_execution_readiness.py` first runs that integrity verifier against the exact source bundle, then decides whether the plan may enter the arrangement solver.
3. A plan can pass integrity and fail readiness. This is expected and must stop execution.

The first readiness gate enforces the adversarial architecture review and revision-bundle contract: the maximum initial paired-seam separation for the current proof must be no greater than 2 cm. Solver sewing strength, projection, extra frames, or post-processing may not compensate for a failed input arrangement.

## Command

```powershell
python tools/verify_libuipc_execution_readiness.py `
  --plan artifacts/libuipc-anny-plan-v2 `
  --source-bundle artifacts/revision-anny-source-v2/bundle
```

Exit codes are part of the public boundary:

1. `0` means the immutable plan, exact source bundle, and every readiness gate authorize execution.
2. `2` means the evidence is structurally valid but at least one readiness gate refuses execution.
3. Any other nonzero result means the evidence is missing, malformed, tampered, or otherwise unverifiable.

## Current exact result

Plan `788b7e67a003e58d04b09194eab33015dd3523bbfb3ce2cce83f09975125e240` and source bundle `cbfb873fea536cba8945926f1566f08f9a02ba11ab850586875f9b21b3727f49` both verify successfully. Execution is refused because the staged maximum seam separation is `65.09543638151202 cm`, against the required `<= 2.0 cm`.

The downstream numerical arrangement and settle artifacts remain evidence, but they cannot retroactively authorize this failed warm start. Their exact six-view result is independently hash-bound to a rejected visual review under `artifacts/codex-anny-settle-v1-review/renders/visual-review-manifest.json`.

## Product boundary

Execution authorization is not arrangement, cloth, avatar, or product acceptance. Promotion still requires:

1. A named garment-specific 3D panel arrangement around the exact body envelope.
2. Calibrated material behavior from the first deforming frame.
3. Exact topology, seam, material-coordinate, body, and pose identity.
4. Global and region-specific geometry gates for neckline, shoulders, underarms, sleeves, bust, waist, back, hem, cuffs, and every seam family.
5. Six-angle human visual review of silhouette, seam continuity, fold scale, thickness, balance, penetration, holes, and correspondence with the exact 2D revision.
6. Packaged Windows verification of the 2D and 3D interfaces, controls, cameras, save and reload, resizing, keyboard behavior, and accessibility.

The runner must invoke this verifier before importing libuipc or allocating a solver scene. Until that integration is complete, invoking the runner directly is an evaluation-only path and cannot support a product claim.
