# Canonical sewn seed contract

## Purpose

Patterna may support bounded current-revision drape through a versioned canonical sewn garment seed. The seed replaces spread-panel attraction as the arrangement owner. It does not replace the immutable 2D pattern, and it does not authorize arbitrary topology-changing edits.

The first supported proof is the named 14-panel crew-neck shirt on the measurement-matched hidden body in the standard shallow A-pose.

## Ownership split

1. The immutable 2D revision owns panel geometry, seam identity, darts, material coordinates, and user-visible pattern truth.
2. A derived sewn solver mesh owns contact and elastic equilibrium. It may weld or couple authored seam vertices only when an explicit reversible map preserves every source vertex and seam identity.
3. The measurement-matched hidden body owns fit and collision for this proof. Anny owns neither accepted measurements nor accepted collision geometry.
4. A separately registered display body may own render quality only after its own measurement, registration, anatomy, and six-view gates pass.
5. The cloth engine owns equilibrium only. It does not own garment construction, pattern identity, display acceptance, or product promotion.

## Seed artifact

Each canonical seed must bind all of the following by SHA-256:

1. Source revision bundle and exact pattern document.
2. Body collider, pose family, and garment archetype.
3. Sewn solver mesh and its material rest state.
4. Complete source-to-solver map and exact inverse solver-to-source membership lists.
5. Numerical verification report.
6. Six exact product-view renders and their accepted visual-review manifest.

The source-to-solver map may be many-to-one at sewn seams. Every authored source vertex must map to exactly one solver vertex, every solver vertex must name at least one source vertex, and the inverse lists must exactly reproduce the forward map. Mapping a solved position back to the source duplicates a welded solver position onto each authored seam copy; it never mutates the 2D source topology.

## Seed acceptance

A seed is accepted only when all of these gates pass without manual mesh edits after seed publication:

1. Source identity and reversible mapping are complete.
2. Body collisions and garment self-intersections are zero.
3. No triangle is inverted in the body-relative geometric frame.
4. Final active seam separation is at most 0.2 cm.
5. Ninety-fifth-percentile material edge strain is at most 0.25.
6. Maximum material edge strain is at most 2.0.
7. Static equilibrium is reached under calibrated material parameters.
8. Anatomical region gates cover neckline, collar, shoulders, armholes, sleeves, cuffs, bust darts, torso side seams, waist, and hem.
9. Symmetry and fold-frequency gates pass where the design and pose are symmetric.
10. Front, front-oblique, left, back, back-oblique, and right renders receive an unqualified accepted visual review.

Passing numerical gates without the visual gate does not accept the seed. A collision-free wad remains a wad, regardless of how confidently a JSON file describes it.

## Continuation proof

One seed render is insufficient. Before this architecture can enter the product, publish one boundary revision before viewing its output. That revision must combine:

1. One garment-critical, in-envelope body measurement change.
2. One topology-preserving pattern geometry change.
3. The same garment archetype and pose family.

Continuation must interpolate collider shape and material rest metrics while contact and elastic equilibrium remain active. No manual vertex edits, changed weights, or revision-specific repair may occur after the seed and boundary revision are published. Both the seed and boundary revision must pass the complete numerical and six-view gates.

## Explicit unsupported cases

The first proof fails closed for any of the following:

1. Added or removed panels, seams, darts, closures, or holes.
2. A body outside the declared measurement envelope.
3. A pose outside the declared pose family.
4. Mapping loss, collision, inversion, excessive strain, or failed visual review.
5. A result that requires tuning after its rendered output is inspected.
6. Unresolved cloth-engine redistribution or transitive-license obligations.

An unsupported edit must show an honest unavailable status in 3D. Patterna must not deform an old seed harder, fall back to rejected diagnostic clothing, or imply that the current 2D revision was simulated.

## Retired routes

The following routes are retired as arrangement owners for this garment:

1. Spread-panel stitch attraction.
2. Semantic envelope wrapping followed by seam snapping.
3. Seam-anchored Laplacian deformation.
4. ARAP deformation from spread or envelope-wrapped panels.
5. Anny as the accepted fit or collision body.

ARAP may be evaluated later as a local predictor inside a proven continuation method. It may not authorize arrangement or product acceptance by itself.

## Independent verification

`tools/canonical_sewn_seed.py` verifies the artifact without importing a cloth solver or producer. It checks exact file hashes, complete forward and inverse source mapping, physical limits, the no-repair declaration, and all six render hashes in the accepted visual review.

```powershell
python tools/canonical_sewn_seed.py --manifest artifacts/<seed>/manifest.json
```

The command exits with code `0` only for a complete accepted seed. Missing evidence, false claims, mapping loss, hash tampering, physical failure, pending review, or rejected visual quality exits with code `2` and reports every reason.
