# Isolated Windows UI testing

Patternal's standard automated UI lane runs inside a dedicated Windows 11 Hyper-V guest. Host scripts build and transfer files through PowerShell Direct. A scheduled task in the logged-in guest launches the packaged app, uses Windows UI Automation in that guest session, captures screenshots, restores changed control values, and writes a JSON result bundle.

This design keeps the user's host mouse, keyboard, focus, and windows untouched. Docker is not the standard because Windows containers do not provide the interactive desktop, AppX registration, WebView2 surface, or graphics stack required by a packaged WinUI 3 application.

## Proof boundary

The isolated lane proves the following:

1. The current source builds as x64 with no stale loose-layout binaries.
2. The AppX payload materialized from `Patternal.build.appxrecipe` is complete and hash-identified.
3. A clean Windows user can install the exact Windows App Runtime dependency and register that payload.
4. The packaged AUMID launches a responsive top-level Patternal window.
5. Primary 2D and 3D controls expose usable Windows UI Automation patterns.
6. Toggles and sliders change and restore their values as a user would expect.
7. Front, right, rear, left, oblique, and fit camera commands produce separate screenshot evidence.
8. Every run records the guest OS, display size, actions, failures, UI trees, screenshots, payload identity, and timestamps.

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

1. Build the current worktree, materialize a clean AppX layout from the generated recipe, verify identity files, copy the payload into the guest, install the signed Windows App Runtime 2.3.1 if needed, register the payload, and refresh the guest task:

```powershell
.\tools\isolated-ui\Sync-PatternalGuestPayload.ps1
```

To create and verify the guest archive without contacting Hyper-V, use:

```powershell
.\tools\isolated-ui\Sync-PatternalGuestPayload.ps1 -PrepareOnly
```

The matching runtime is downloaded from Microsoft's pinned 2.3.1 x64 installer URL. The guest rejects it unless Authenticode reports a valid Microsoft Corporation signature. Microsoft documents the silent `--quiet` deployment option in the [Windows App SDK deployment guide](https://learn.microsoft.com/windows/apps/windows-app-sdk/deploy-unpackaged-apps).

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
4. Round-trips the Pieces panel, Inspector panel, seam allowance, and grainline toggles.
5. Temporarily disables linked proportional estimates, round-trips Height, Full bust, Waist, Hip, Shoulder, and Torso sliders, then restores the link state.
6. Round-trips Fabric weight and Fabric stretch.
7. Round-trips the fitted-bra toggle when available, or verifies that it is disabled when no matching fitted asset exists.
8. Enters Assembly mode, changes reverse side B, invokes Undo, and verifies that the visible toggle returns to the original state.
9. Enters 3D and captures Front, Right, Rear, Left, Oblique, and Fit views.
10. Returns to 2D, writes the result bundle, and closes the guest app unless `-KeepAppOpen` was requested.

Expand this list whenever a new user-facing toggle, slider, authoring command, camera, persistence behavior, or acceptance gate is added. UI contracts rot if they are treated as museum pieces.

## Windows Sandbox fallback

Windows Sandbox is suitable for a disposable install or launch smoke test when Hyper-V guest provisioning is unavailable. It is not the standard evidence lane because its state disappears at close, its window appears on the host desktop, and its graphics behavior does not establish final physical-GPU quality. Do not auto-launch Sandbox while the user is actively using the host.

## Current setup status

As of 2026-08-06, the host audit confirms Windows 11 Pro, Hyper-V services, Windows Sandbox, 64 GB RAM, an RTX 4090, and sufficient disk space. The repository scripts parse, the unattended data ISO generator passes a create and mount test, and the current 88-file AppX archive round-trips to payload identity `a121d360ea91888e4929712a08b41e51e69c5f2b2d90a664f7bacb2ff156357f`.

The persistent guest has not yet been created because the official evaluation ISO is not present and this Codex process has no elevated Hyper-V management token. Those are setup prerequisites, not evidence that the packaged UI passed. Until the guest run and screenshot review occur, the repaired 2D and 3D interaction gates remain open.
