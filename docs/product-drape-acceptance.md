# Product drape acceptance

`tools/product_drape_acceptance.py` is the fail-closed boundary between diagnostic cloth assets and product-visible accepted drape.

Renderer compatibility is necessary but insufficient. A mesh may parse, carry valid hashes, and sit in the expected coordinate frame while still depicting the wrong garment, the wrong body, unmeasured material, or visibly broken cloth. The product gate therefore requires all of the following at once:

1. The packaged asset and renderer reports use supported schemas and name the same hash-shaped arrangement identifier.
2. Producer, packaged visual quality, calibrated fabric, and correct-body drafting claims are exactly `true`.
3. The packaged report has no open gates.
4. A six-view visual review is accepted and bound by a SHA-256 manifest hash.
5. Renderer acceptance and packaged visual quality claims are exactly `true`.
6. The renderer says the assets load and reports no issues.

The command exits with code `0` only when every requirement passes. A structurally valid but unaccepted asset exits with code `2` and lists every rejection reason.

```powershell
python tools/product_drape_acceptance.py `
  --assets-report Patternal/Assets/AcceptedDrape/packaged-drape-assets.json `
  --renderer-report Patternal/Assets/AcceptedDrape/renderer-contract-verification.json
```

As of August 28, 2026, the assets under `Patternal/Assets/AcceptedDrape` are diagnostic only. Their own reports keep the product claims false, and this gate rejects them. The viewport must not label or expose them as accepted drape until it invokes this gate or enforces the same complete contract.
