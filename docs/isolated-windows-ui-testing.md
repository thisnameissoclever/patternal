# Isolated Windows UI testing

Patternal's standard automated UI lane runs inside a dedicated Windows 11 Hyper-V guest. Host scripts build and transfer files through PowerShell Direct. A scheduled task in the logged-in guest launches the packaged app, uses Windows UI Automation plus narrowly scoped guest-local pointer input in that guest session, captures screenshots, restores changed control values, and writes a JSON result bundle.

This design keeps the user's host mouse, keyboard, focus, and windows untouched. Docker is not the standard because Windows containers do not provide the interactive desktop, AppX registration, WebView2 surface, or graphics stack required by a packaged WinUI 3 application.

## Proof boundary

The isolated lane proves the following:

1. The current source builds as x64 with no stale loose-layout binaries.
2. The AppX payload materialized from `Patternal.build.appxrecipe` is complete and hash-identified.
3. A clean Windows user can install the exact .NET and Windows App Runtime dependencies and register that payload.
4. The packaged AUMID launches a responsive top-level Patternal window.
5. Primary 2D and 3D controls expose usable Windows UI Automation patterns.
6. Toggles and sliders change and restore their values as a user would expect.
7. Front, right, rear, left, oblique, and fit camera commands produce separate screenshot evidence.
8. Every run records the guest OS, display size, actions, failures, UI trees, screenshots, payload identity, and timestamps. A fatal run also records the Patternal process state and relevant Application, AppModel Runtime, and TWinUI events in the same result bundle.

Hyper-V's synthetic display is not proof of RTX 4090 rendering fidelity, frame pacing, or final cloth appearance. CLO-class completion still requires one physical-GPU packaged pass on the target host or an equivalent physical Windows machine. The guest lane removes routine desktop contention; it does not turn virtual graphics into physical graphics through wishful thinking.

## Safety contract

The following rules are mandatory for this workflow:

1. Host scripts must not call `SendInput`, `mouse_event`, `keybd_event`, Windows UI Automation, Computer Use, VMConnect, or Windows Sandbox.
2. Host scripts may build files, manage the named Hyper-V guest, use PowerShell Direct, and send a boot key through the named VM's synthetic keyboard.
3. All Patternal UI interaction originates from `guest/Invoke-PatternalUiSmoke.ps1` inside the guest's interactive user session.
4. VMConnect may be opened only after the user explicitly permits visible manual guest inspection.
5. The test records every original toggle and slider value and restores it before completion.
6. A disabled fitted-bra control passes only when the renderer has reported that no fitted display asset matches the current avatar revision.
7. Evidence must be preserved after failure. A red result with screenshots is useful; deleting it to make the next run greener is not.
8. Generated credentials, virtual disks, ISOs, and evidence remain machine-local and must not be committed.
9. Guest-local pointer input may target only coordinates first resolved by UI Automation to the Patternal process. It must never be moved into a host script or used outside the named guest session.

Run the repository contract check after changing any script or automation name:

```powershell
.\tools\isolated-ui\Test-PatternalIsolatedUiHarness.ps1
```

Inspect the current host, guest, credential, and payload state without changing anything:

```powershell
.\tools\isolated-ui\Get-PatternalIsolatedUiStatus.ps1
```

## One-time host setup

The host must run Windows 11 Pro or Enterprise with Hyper-V. Microsoft documents the current requirements in [System requirements for Hyper-V](https://learn.microsoft.com/windows-server/virtualization/hyper-v/host-hardware-requirements).

1. Download a Windows 11 x64 ISO from Microsoft. The no-cost test route is the [90-day Windows 11 Enterprise evaluation](https://www.microsoft.com/evalcenter/evaluate-windows-11-enterprise). Microsoft requires the person downloading it to complete its registration form. Do not fabricate registration data.

2. For the Windows 11 Enterprise 25H2 `Enterprise Eval x64 Eval EN-US DVD9` image, Microsoft's [Windows 11 hash document](https://aka.ms/Win11-Hash-PDF) publishes SHA-256 `A61ADEAB895EF5A4DB436E0A7011C92A2FF17BB0357F58B13BBC4062E535E7B9`. Verify the downloaded file yourself:

```powershell
Get-FileHash -LiteralPath 'D:\Downloads\Windows11Enterprise.iso' -Algorithm SHA256
```

3. Open one elevated PowerShell window. Enable access for the current user without forcing a reboot:

```powershell
Set-Location 'D:\VIBES\patternal'
.\tools\isolated-ui\Initialize-PatternalHyperVHost.ps1
```

4. In the same elevated window, create the guest. Supply the exact hash, not an abbreviated value:

```powershell
.\tools\isolated-ui\New-PatternalHyperVGuest.ps1 `
    -IsoPath 'D:\Downloads\Windows11Enterprise.iso' `
    -ExpectedIsoSha256 'A61ADEAB895EF5A4DB436E0A7011C92A2FF17BB0357F58B13BBC4062E535E7B9'
```

The script creates a Generation 2 VM named `Patternal-UI` under `D:\VMs\Patternal-UI`, with Secure Boot, virtual TPM, dynamic memory, eight virtual processors, a 180 GB dynamic disk, and the Default Switch. It selects the Enterprise image, installs unattended, creates a generated local administrator, enables Developer Mode, keeps the console session awake, verifies PowerShell Direct, detaches installation media, and creates a clean checkpoint.

The generated guest credential is encrypted with Windows Data Protection API for the current host user and stored at:

```text
%LOCALAPPDATA%\Patternal\VirtualMachine\Patternal-UI.credential.xml
```

The temporary answer-media ISO contains the generated password during setup. It is deleted after successful provisioning. If setup fails, the script preserves that media for diagnosis and prints a warning. Delete it after recovery.

5. Sign out and back in once after the host bootstrap adds the account to `Hyper-V Administrators`. This refreshes the access token used by ordinary, non-elevated shells and Codex. A restart also works, but the scripts never impose one.

Microsoft documents PowerShell Direct and its Hyper-V administrator requirement in [Virtual machine automation and management using PowerShell](https://learn.microsoft.com/windows-server/virtualization/hyper-v/powershell-direct).

## Normal development loop

No elevated shell, VMConnect window, or host UI automation is required after one-time setup.

1. Build the current worktree, materialize a clean AppX layout from the generated recipe, verify identity files, copy the payload into the guest, install the signed .NET 10 and Windows App Runtime 2.3.1 prerequisites if needed, register the payload, and refresh the guest task:

```powershell
.\tools\isolated-ui\Sync-PatternalGuestPayload.ps1
```

To create and verify the guest archive without contacting Hyper-V, use:

```powershell
.\tools\isolated-ui\Sync-PatternalGuestPayload.ps1 -PrepareOnly
```

The host applies an execution-policy bypass only to the current PowerShell Direct process before invoking the copied guest installer; it does not weaken the guest's persistent policy. The payload manifest records the minimum `Microsoft.NETCore.App` version from `Patternal.runtimeconfig.json`, and the guest installs Microsoft's pinned .NET 10.0.10 x64 runtime when no compatible patch is present. The matching Windows App Runtime is downloaded from Microsoft's pinned 2.3.1 x64 installer URL. The guest rejects either installer unless Authenticode reports a valid Microsoft Corporation signature. If the signed Windows App Runtime wrapper crashes, the guest downloads Microsoft's matching redistributable ZIP, verifies the Microsoft signature on each x64 MSIX, and directly installs Framework, Main, Singleton, and DDLM. Microsoft documents both supported Windows App SDK deployment choices in the [Windows App SDK deployment guide](https://learn.microsoft.com/windows/apps/windows-app-sdk/deploy-unpackaged-apps).

2. Run the isolated packaged interaction suite:

```powershell
.\tools\isolated-ui\Invoke-PatternalGuestUiSmoke.ps1
```

3. Inspect `result.json`, both UI trees, and every PNG under:

```text
artifacts\isolated-ui\runs\<run-id>\
```

Do not treat a passing JSON result as camera-orientation or cloth-quality proof by itself. Inspect the front, side, rear, oblique, and fit images. A button can invoke successfully while pointing the camera at the avatar's backside; software has achieved stranger victories.

4. Keep failed evidence. Fix the source, sync a new hash-identified payload, and rerun. Never patch files directly inside `C:\PatternalTest\Payloads`.

## Automated interaction coverage

The current guest suite performs these checks in order:

1. Requests a 1920 by 1080 guest display and rejects anything below 1280 by 720.
2. Launches the packaged AUMID and verifies a responsive Patternal window.
3. Captures the startup 2D view and a bounded UI Automation tree.
4. Deliberately changes Height with linked proportions disabled, invokes New through guest-local pointer input, confirms the dialog, and requires the dedicated test profile to return to the 167 cm linked-proportion bundled baseline. This makes persistent guest state deterministic without deleting the app profile behind the product's back.
5. Before changing any simulation input, enters 3D and locates the six camera controls by stable automation ID. It captures Front, Right, Rear, Left, Oblique, and Fit views, then returns to 2D. If the cloth is stale, the files are labeled `3d-stale-avatar` and the freshness gate fails while the remaining 2D interaction coverage continues.
6. Invokes 2D Zoom in, Zoom out, and Fit by stable automation ID. It verifies the visible zoom direction and round trip, then captures a post-Fit screenshot for all-pieces-visible review.
7. Selects and frames `Back Torso`, enters point-edit mode, selects its named start anchor through UI Automation, changes its X coordinate, proves Undo, proves Redo, restores the original coordinate, and captures the inspector plus accessible handles.
8. Fits the full canvas, starts polygon drafting, enters four X/Y coordinate pairs through `RangeValuePattern`, captures the visible closed preview, finishes a new piece, proves the piece count changes from 14 to 15 through Undo and Redo, and restores 14 pieces.
9. Fits the canvas again, starts polygon drafting, resolves four empty-space screen points to the Patternal process, places all four corners with guest-local pointer input, captures the visible preview, clicks the first corner to close the piece, proves the count changes through Undo and Redo, and restores 14 pieces.
10. Opens physical-scale calibration, measures the 320-DIP ruler as a deterministic 10 cm, proves the resulting 800% 1:1 view, leaves it with Fit, reapplies it through the 1:1 command, captures the truthful authored-grid and calibrated-scale UI, then restores the prior calibration state and fitted zoom.
11. Selects `Back Torso`, creates a default precise construction line, proves Undo and Redo, edits its name and purpose to a fold guide, verifies the updated named geometry, captures it, proves the update through Undo and Redo, deletes it, proves the deletion through Undo and Redo, and leaves the piece without the test line.
12. Creates a default two-leg guide dart on `Back Torso`, proves Undo and Redo, edits its name and fold direction, verifies both updated named legs, captures them, proves the update through Undo and Redo, deletes it, proves the deletion through Undo and Redo, and leaves the piece without the test dart.
13. Selects the existing `Left side bust dart`, verifies that it uses the sewn-edge construction mode, renames it, changes its fold direction, applies the edit, proves Undo and Redo, captures the rendered physical legs at working scale, and restores the original dart.
14. Creates a temporary polygon, creates a free-edge physical dart on it, verifies both rendered legs, then enters Assembly mode and requires the permanent-seam count to increase by exactly one. It proves Undo and Redo and removes both the dart and temporary piece even if an intermediate assertion fails.
15. Creates a temporary polygon with piece-qualified endpoint identities, marks two opposite edges, sews them, verifies the permanent-seam count through Undo and Redo, captures Assembly mode, then removes the seam and temporary piece.
16. Round-trips the Pieces panel, Inspector panel, seam allowance, and grainline toggles.
17. Temporarily disables linked proportional estimates, changes Height, enters 3D, proves the preview switches from the fitted Antonia candidate to the editable measurement mesh, activates Fit to force a visible render, captures it, restores Height, and proves the fitted candidate returns. Both captures sample the central WebView region and fail when fewer than 5 percent of sampled pixels are non-white. The product restarts one generation-owned render loop whenever 3D becomes visible and reloads only when WebGL reports a lost context.
18. Round-trips Height, Full bust, Waist, Hip, Shoulder, and Torso sliders, then restores the link state.
19. Round-trips Fabric weight and Fabric stretch.
20. Round-trips the fitted-bra toggle when available, or verifies that it is disabled when no matching fitted asset exists.
21. Enters Assembly mode, changes reverse side B, invokes Undo, and verifies that the visible toggle returns to the original state.
22. Opens the real packaged Windows Save As picker through guest-local pointer input, supplies a unique file name, exports SVG, parses the result, and requires the `patterna.garment/1.1` payload to contain 14 simulation panels and 38 seams.
23. Disables linked proportions, changes Height, saves the local snapshot, terminates Patternal, relaunches the packaged AUMID, and requires both values to restore. It then restores the baseline values, saves again, relaunches again, and captures the cleaned final state.
24. Writes the result bundle and closes the guest app unless `-KeepAppOpen` was requested.

Expand this list whenever a new user-facing toggle, slider, authoring command, camera, persistence behavior, or acceptance gate is added. UI contracts rot if they are treated as museum pieces.

## Windows Sandbox fallback

Windows Sandbox is suitable for a disposable install or launch smoke test when Hyper-V guest provisioning is unavailable. It is not the standard evidence lane because its state disappears at close, its window appears on the host desktop, and its graphics behavior does not establish final physical-GPU quality. Do not auto-launch Sandbox while the user is actively using the host.

## Current setup status

As of 2026-08-09, the host audit confirms Windows 11 Pro, Hyper-V services, Windows Sandbox, 64 GB RAM, an RTX 4090, and sufficient disk space. The persistent Windows 11 guest launches the registered AppX as a responsive top-level window without taking over the host desktop. Reviewed run `20260809-104940-3155254b` used payload `0965eb4d83d85486264006498870a08f1d8c92045da294732692ed044c470bf9`, completed 41 interaction checks, and captured 21 screenshots. Forty checks passed. The run correctly failed only the freshness gate because the current pattern, body, assembly, and fabric revision has no accepted cloth. Front, Rear, Right, Left, Oblique, and Fit views retain the corrected glTF image origin and sRGB lighting contracts. The packaged 2D Fit, frame-selected, point-edit, numeric polygon, pointer polygon, calibrated actual-size, updated fold-line, updated guide-dart, sewn-edge physical dart, free-edge physical dart, and free-sewing views remain readable at 1920 by 1080. The scale workflow calibrated a 320-DIP ruler to a deterministic 10 cm measurement, proved the resulting 32 DIPs per centimeter and 800% 1:1 view, left it through Fit, restored it through the 1:1 command, and cleared the test calibration. The pointer workflow placed four corners on empty canvas space and closed the polygon by clicking its first corner, then proved count restoration through Undo and Redo. The internal-line and guide-dart workflows proved create, update, delete, Undo, Redo, and cleanup. The physical-dart workflows edited and restored the existing `Left side bust dart`, then created a free-edge dart on a temporary piece and proved that its compiled closure seam raised the permanent-seam count from 38 to 39. Undo, Redo, and final cleanup restored the original 14-piece document and 38 seams.

The same run exported a real 11,689-byte SVG through Windows Save As and parsed 14 simulation panels plus 38 seams from its embedded `patterna.garment/1.1` document. It saved Height 167.5 cm with linked proportions Off, terminated the app, restored both values after packaged relaunch, then restored and re-saved the 167 cm linked baseline. Large JSON state now lives in a versioned, atomically replaced file under the package LocalFolder instead of exceeding the per-value `LocalSettings` limit. Legacy settings remain readable. The end-to-end measurement check proved the visible viewport switched to the 151-value editable measurement mesh and returned to the textured fitted Antonia candidate. Both late 3D captures passed a 1.0 non-white sample ratio after the new hidden-tab render-loop recovery, and manual review confirmed that neither image was blank. Visual review still rejects the editable fallback as a product avatar because its anatomy, hands, feet, surface detail, and materials remain far below the fitted candidate. Manual six-view review also rejects Antonia as the final CLO-class avatar because the asymmetric raised-arm pose, bald presentation, modesty assets, and customization depth remain inadequate. Host input injection and VMConnect use remained false. CLO-class completion remains open because accepted cloth, a realistic revision-matched customizable avatar, fitted hair, improved modesty clothing, and physical-GPU proof are still missing.

The persistent guest and its signed application prerequisites are operational. This proves the isolated packaged interaction lane, not the visual quality of the current product. The current 2D all-pieces layout, zoom controls, calibrated 1:1 scale, accessible piece, anchor, and edge selection, precise point entry, numeric and pointer polygon drafting, internal-line and guide-dart create, update, delete, Undo, and Redo workflows, sewn-edge and free-edge physical darts, free sewing, and Frame selected command pass at 1920 by 1080. Current accepted cloth, physical-GPU rendering, and CLO-class multi-view gates remain open.
