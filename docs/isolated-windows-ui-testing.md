# Isolated Windows UI testing

Patternal's standard automated UI lane runs inside a dedicated Windows 11 Hyper-V guest. Host scripts build and transfer files through PowerShell Direct. A scheduled task in the logged-in guest launches the packaged app, uses Windows UI Automation in that guest session, captures screenshots, restores changed control values, and writes a JSON result bundle.

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
4. Before changing any simulation input, enters 3D and locates the six camera controls by stable automation ID. It captures Front, Right, Rear, Left, Oblique, and Fit views, then returns to 2D. If the cloth is stale, the files are labeled `3d-stale-avatar` and the freshness gate fails while the remaining 2D interaction coverage continues.
5. Invokes 2D Zoom in, Zoom out, and Fit by stable automation ID. It verifies the visible zoom direction and round trip, then captures a post-Fit screenshot for all-pieces-visible review.
6. Selects and frames `Back Torso`, enters point-edit mode, selects its named start anchor through UI Automation, changes its X coordinate, proves Undo, proves Redo, restores the original coordinate, and captures the inspector plus accessible handles.
7. Fits the full canvas, starts polygon drafting, enters four X/Y coordinate pairs through `RangeValuePattern`, captures the visible closed preview, finishes a new piece, proves the piece count changes from 14 to 15 through Undo and Redo, and restores 14 pieces.
8. Selects `Back Torso`, creates a default precise construction line, verifies the named rendered geometry, captures it, proves Undo and Redo, and restores the piece without the test line.
9. Creates a default two-leg guide dart on `Back Torso`, verifies both named rendered legs, captures them, proves Undo and Redo, and restores the piece without the test dart.
10. Round-trips the Pieces panel, Inspector panel, seam allowance, and grainline toggles.
11. Temporarily disables linked proportional estimates, round-trips Height, Full bust, Waist, Hip, Shoulder, and Torso sliders, then restores the link state.
12. Round-trips Fabric weight and Fabric stretch.
13. Round-trips the fitted-bra toggle when available, or verifies that it is disabled when no matching fitted asset exists.
14. Enters Assembly mode, changes reverse side B, invokes Undo, and verifies that the visible toggle returns to the original state.
15. Writes the result bundle and closes the guest app unless `-KeepAppOpen` was requested.

Expand this list whenever a new user-facing toggle, slider, authoring command, camera, persistence behavior, or acceptance gate is added. UI contracts rot if they are treated as museum pieces.

## Windows Sandbox fallback

Windows Sandbox is suitable for a disposable install or launch smoke test when Hyper-V guest provisioning is unavailable. It is not the standard evidence lane because its state disappears at close, its window appears on the host desktop, and its graphics behavior does not establish final physical-GPU quality. Do not auto-launch Sandbox while the user is actively using the host.

## Current setup status

As of 2026-08-08, the host audit confirms Windows 11 Pro, Hyper-V services, Windows Sandbox, 64 GB RAM, an RTX 4090, and sufficient disk space. The persistent Windows 11 guest launches the registered AppX as a responsive top-level window without taking over the host desktop. Reviewed run `20260809-054140-e91c4318` used payload `2c4762350701360d4bc628d02ad2a7592556c1bf30371761540a0a72d70d4d51`, passed all 31 functional interaction checks, and captured anatomically correct Antonia Front, Rear, Right, Left, Oblique, and Fit views. The packaged 2D Fit view showed all 14 source pieces with separate readable labels at 89 percent. The guest selected `Back Torso` through `SelectionItemPattern`, framed that exact piece at 223 percent, selected its named start anchor, changed X from `-1.98 cm` to `-1.88 cm`, proved Undo and Redo, and restored `-1.98 cm`. It then fitted the canvas, entered a four-corner 10 by 10 cm polygon with accessible coordinate controls, created the fifteenth piece, proved Undo and Redo, and restored 14 pieces. The guest next created a named construction line and a two-leg guide dart on `Back Torso`, proved their rendered geometry through Undo and Redo, and restored the original piece after each check. The reviewed screenshots show all four polygon corners, the visible dashed internal line, and both dart legs without clipping. Host input injection and VMConnect use remained false. The run correctly failed the freshness gate because the current pattern, body, assembly, and fabric revision has no accepted cloth, so CLO-class 3D acceptance remains open. The packaged Antonia display is explicitly a candidate; visible texture transitions, missing hair, the modesty bandeau, and absent cloth remain open visual gates.

The persistent guest and its signed application prerequisites are operational. This proves the isolated packaged interaction lane, not the visual quality of the current product. The current 2D all-pieces layout, zoom controls, accessible piece and anchor selection, precise point and polygon coordinate entry, internal-line and guide-dart creation, structural Undo and Redo, and Frame selected command pass at 1920 by 1080. Pointer polygon placement, internal-line and dart update or deletion, physical dart modes, free sewing, calibrated physical scale, current accepted cloth, physical-GPU rendering, and CLO-class multi-view gates remain open.
