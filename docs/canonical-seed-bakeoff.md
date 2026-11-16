# Canonical sewn seed bakeoff

## Purpose

Patterna needs one collision-clean, visually credible, sewn garment seed before a
physics solver can perform deterministic continuation. This document records the
seed routes that were tested and the evidence-based stop decision for each route.
It prevents rejected transfer methods from quietly returning under a new filename
or a slightly different set of weights.

The product acceptance contract is defined in
`docs/canonical-sewn-seed-contract.md`. A seed is not accepted merely because it
loads, settles, or produces favorable aggregate numbers. It must preserve the
declared pattern mapping, pass collision and strain gates, and pass a hash-bound
six-view visual review.

## Rejected routes

### 1. Welded continuation from the prior current-pattern solve

The source had 37,287 vertices. Welding its declared seams produced 36,371 solver
vertices and closed all 932 seam pairs. The resulting draft had:

1. 136 body intersections in the formal run.
2. Zero reported self-intersections after welding.
3. 0.0584 p95 strain.
4. 0.783 p99.9 strain.
5. 0.944 p99.99 strain.
6. A 0.003075 high-strain fraction.
7. A starting projection that moved 1,441 welded vertices by as much as 2.14 cm.

The route was rejected because collision cleanup was doing untracked geometric
editing after seam assembly. The favorable p95 statistic concealed local damage
and did not satisfy the seed contract.

Evidence: `artifacts/codex-canonical-seed-draft-v1`.

### 2. Per-panel rigid fit to the prior guide

Rigid Kabsch fitting preserved panel material metric, but the assembled result
had:

1. 18.58 cm maximum seam separation.
2. 1,844 body intersections.
3. 143 self-intersections.

The route was rejected immediately. Panel rigidity alone cannot recover a sewn
garment from an invalid assembly guide.

### 3. Envelope projection and Laplacian variants

Three arrangement variants were tested:

1. A simple wrap on Anny left a 13.787 cm shoulder gap.
2. Seam anchors plus Laplacian smoothing on Anny closed most seams but produced
   1.8449 p95 strain.
3. The same method on Antonia produced 1.7240 p95 strain.

The invariant was clear: projection could close seams only by destroying the
material metric. Further weight tuning was stopped.

### 4. Transfer from the legacy 16-panel production crew neck

The legacy garment is visually coherent and collision-clean on its original body,
but it represents a different 16-panel pattern. The current pattern has 14 panels,
different torso dimensions, and explicit current-pattern semantics. A normalized
material-coordinate nearest-vertex transfer produced:

1. 18.455 cm maximum seam separation.
2. 3.269 cm mean seam separation.
3. 13.113 cm p95 seam separation.
4. 5.543 maximum strain.
5. 0.5007 p95 strain.
6. 0.1136 high-strain fraction.
7. 2,295 self-intersections.
8. 1,537 body intersections on the Antonia target.

The route was rejected. The old accepted mesh remains useful as a visual reference,
not as a seed for the current topology.

Evidence: `artifacts/legacy-production-crew-neck-review` and
`Patternal/Assets/Production/patterna-production-crew-neck.fit.json`.

### 5. CC0 MakeHuman casual top transfer

The MakeHuman `casualsuit01_top` source is a clean, simple crew-neck shirt on its
donor body. Its local license declaration is CC0. The raw placement on Antonia had
213 body edge intersections and no self-intersections.

A single nearest-surface shrinkwrap with 6 mm clearance produced 133 body
intersections and 348 self-intersections, so that route was stopped.

A separate bounded smooth-scale test preserved the source topology and tested 12
predeclared combinations:

1. Horizontal scale: 1.00, 1.05, and 1.10.
2. Depth scale: 1.20, 1.25, 1.30, and 1.35.
3. Best result: horizontal scale 1.10 and depth scale 1.20.
4. Best body intersection count: 220.
5. Best self-intersection count: 7.

No candidate was collision-clean, and larger scales did not monotonically improve
the fit. The donor garment shape is incompatible with the target body. This route
is rejected without adding more projection or shrinkwrap variants.

Evidence: `artifacts/cc0-casual-top-donor-review` and
`artifacts/cc0-casual-top-antonia-seed-candidate`.

## Architecture decision

Existing-garment projection is exhausted as a seed-generation strategy for the
current 14-panel pattern. The observed failures are topological and semantic, not
solver-weight failures. A dynamics solver cannot invent a correct garment assembly
from large seam gaps or repair a foreign garment topology without losing the
source-to-pattern relationship.

The remaining supported route is deliberate construction of one canonical sewn
seed for the exact current pattern and matched hidden body. That construction must:

1. Start from the named 14-panel and 38-stitch topology.
2. Preserve an explicit reversible source-to-solver map.
3. Apply no undeclared manual edits after publication.
4. Pass the collision, strain, equilibrium, region, and symmetry gates.
5. Pass a hash-bound six-view visual review before product integration.
6. Serve as the fixed input to deterministic continuation for any predeclared body
   or pattern revision.

If that seed cannot pass all six views before continuation, the seed is rejected.
The response is to revise the authored construction or select a source asset with
compatible topology, not to tune the physics until the verifier stops
complaining.
