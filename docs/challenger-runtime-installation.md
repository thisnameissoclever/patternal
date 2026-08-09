# Challenger runtime installation

## Purpose

Patterna evaluates new avatar and cloth engines in machine-local, versioned directories before they can affect the accepted simulation runtime. The standard root is `%LOCALAPPDATA%\Patterna\ChallengerRuntimes`. MHR, PPF, downloads, and the generated catalog have separate owned paths beneath that root. Nothing in this process replaces `%LOCALAPPDATA%\Patterna\SimulationRuntime\current`.

## Supported process

1. Download only the exact release assets recorded in `docs/open-source-foundation-decision.md` into the `downloads` directory. Downloads may resume, but installation rejects the result unless both the expected byte count and SHA-256 match.
2. Keep MHR dependencies in the Python 3.12 lane. The committed requirements lock names every wheel and requires its SHA-256. Installation uses only the verified offline wheel directory, never the host Python 3.14 environment and never a mutable package index.
3. Extract into a new component-owned staging directory. Reject archive entries that resolve outside that staging root.
4. Validate licenses, executable or model entry points, the exact embedded PPF Python 3.11.9 runtime, Python imports, and one neutral MHR TorchScript inference before promotion.
5. Write a hash-bound `runtime-manifest.json`, then atomically rename the staging directory to its immutable version name. A valid installed version is reused. An invalid existing version is never overwritten unless `-Replace` is explicit; replacement preserves the old directory as a timestamped backup.
6. Regenerate `challenger-runtime-catalog.json` from installed manifests. The catalog is discovery metadata; each runtime manifest and entry-point hash remains authoritative.

Install both approved challengers:

```powershell
& .\tools\install_patterna_challenger_runtimes.ps1 -Component All
```

The expected version roots are:

```text
%LOCALAPPDATA%\Patterna\ChallengerRuntimes\MHR\v1.0.1-py312-torch2.12.1-cpu
%LOCALAPPDATA%\Patterna\ChallengerRuntimes\PPF\2026-08-08-03-55-win64
```

## Proof boundary

Successful installation proves archive identity, offline dependency identity, license retention, entry-point integrity, MHR CPU inference, and PPF frontend importability. It does not prove measurement fit, PPF compatibility with the host NVIDIA driver, seam closure, collision quality, drape quality, packaged application integration, or visual acceptance. Those remain bake-off and packaged UI gates.

The installed MHR manifest SHA-256 is `099c2820523f28dd16c7542f0ae47d00f8b3f7d41c5b4da39f8209332af60765`. The installed PPF manifest SHA-256 is `d573eee78e85be5c745de1163201257dd97466e2c19bad1e725c0f6d4a7ba44a`. These values identify the current machine-local installations; rebuilding a manifest at a different installation time will intentionally produce a different manifest hash while retaining the same archive and entry-point hashes.

The repeatable MHR measurement sequence is:

```powershell
$mhr = Join-Path $env:LOCALAPPDATA 'Patterna\ChallengerRuntimes\MHR\v1.0.1-py312-torch2.12.1-cpu'
$python = Join-Path $mhr '.venv\Scripts\python.exe'
$model = Join-Path $mhr 'assets\mhr_model.pt'
$profile = '.\PatternaUnreal\SourceAssets\Avatar\PatternaFullBustDefault.avatar-profile.json'

& $python .\tools\fit_mhr_identity.py `
    --profile $profile `
    --model $model `
    --output-directory .\artifacts\mhr-avatar-fitted-v1

& $python .\tools\fit_mhr_local_profile.py `
    --profile $profile `
    --model $model `
    --identity-json .\artifacts\mhr-avatar-fitted-v1\identity-coefficients.json `
    --output-directory .\artifacts\mhr-avatar-local-fit-v1
```

The first command keeps the best bounded statistical identity stage and truthfully reports rejection when MHR's native coefficient space misses the measurement tolerances. The second applies smooth section corrections to that exact identity without changing vertex or triangle topology. Its accepted geometry report still does not prove rig preservation, appearance, garment collision, or packaged product quality.

The first separate host-GPU gate is:

```powershell
$ppf = Join-Path $env:LOCALAPPDATA 'Patterna\ChallengerRuntimes\PPF\2026-08-08-03-55-win64'
$python = Join-Path $ppf 'python\python.exe'
& $python .\tools\run_ppf_runtime_smoke.py `
    --runtime-root $ppf `
    --output-directory .\artifacts\ppf-runtime-smoke-v1
```

This smoke redirects both cache and session data into the artifact directory, verifies every manifest entry point before execution, forces a fresh small sheet-versus-sphere scene on the NVIDIA GPU, requires a finished marker, finite output, and at least one nonzero contact count, then records runtime, GPU, timing, bounds, contact counts, logs, and output hashes. The process-local `App.get_data_dirpath` override uses PPF's explicitly patchable data-root seam without disabling its real GPU or driver checks. It proves native solver startup and basic contact execution only; garment seam and visual quality gates remain open.

## Standard Patterna garment evaluation

Build a body proxy through the installed Blender, then pass both its OBJ and its accepted report to the PPF adapter. Never pass an unreported decimation or replace the canonical body path in the source report.

```powershell
$runtime = Join-Path $env:LOCALAPPDATA 'Patterna\SimulationRuntime\current'
$blender = Join-Path $runtime 'blender\blender.exe'
$ppf = Join-Path $env:LOCALAPPDATA 'Patterna\ChallengerRuntimes\PPF\2026-08-08-03-55-win64'
$python = Join-Path $ppf 'python\python.exe'

& $blender --background --factory-startup `
    --python .\tools\build_body_collision_proxy.py -- `
    --input .\artifacts\cloth-bakeoff-antonia\control\antonia-simulation-body.obj `
    --output .\artifacts\ppf-patterna-common-bundle-1cm-v1\collision-proxy\antonia-collision-10000f.obj `
    --report .\artifacts\ppf-patterna-common-bundle-1cm-v1\collision-proxy\antonia-collision-10000f.report.json `
    --target-face-count 10000

& $python .\tools\run_ppf_patterna_bundle.py `
    --runtime-root $ppf `
    --source-report .\artifacts\ppf-patterna-common-bundle-1cm-v1\source\patterna-style3d-source-1.000cm.report.json `
    --body-override .\artifacts\ppf-patterna-common-bundle-1cm-v1\collision-proxy\antonia-collision-10000f.obj `
    --body-override-report .\artifacts\ppf-patterna-common-bundle-1cm-v1\collision-proxy\antonia-collision-10000f.report.json `
    --output-directory .\artifacts\ppf-patterna-common-bundle-1cm-proxy-v1 `
    --frames 20 `
    --preflight-only

& $python .\tools\run_ppf_patterna_bundle.py `
    --runtime-root $ppf `
    --source-report .\artifacts\ppf-patterna-common-bundle-1cm-v1\source\patterna-style3d-source-1.000cm.report.json `
    --body-override .\artifacts\ppf-patterna-common-bundle-1cm-v1\collision-proxy\antonia-collision-10000f.obj `
    --body-override-report .\artifacts\ppf-patterna-common-bundle-1cm-v1\collision-proxy\antonia-collision-10000f.report.json `
    --output-directory .\artifacts\ppf-patterna-common-bundle-1cm-proxy-v1 `
    --frames 20
```

`run_ppf_patterna_bundle.py` verifies the immutable runtime manifest and every input hash. Before launching the native child, it independently recomputes triangle area, initial strain, garment self-intersection, body intersection, and `0.25 cm` body-clearance gates. Its bounded rigid stage may move only violating panels radially outward, records every transform, and must recheck to zero violations without changing material shape. Run `--preflight-only` first; it writes the same gate report without creating a native session. The normal path redirects cache and session state into the artifact, records the native requested frame count after configuring dynamic release parameters, and never labels a completed solve as accepted. If a host wrapper ends before the native child, let the solver finish and use `collect_ppf_patterna_session.py` against the exact session directory. The collector verifies runtime identity, restores PPF's object vertex map, reads the native TOML frame count, grades every saved snapshot, and writes a fresh hash-bound rejection or remaining-acceptance report.
