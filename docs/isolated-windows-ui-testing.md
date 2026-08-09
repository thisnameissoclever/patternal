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

Request an exact supported guest resolution without opening VMConnect:

```powershell
.\tools\isolated-ui\Invoke-PatternalGuestUiSmoke.ps1 -Mode persistence-only -DisplayWidth 1280 -DisplayHeight 720
.\tools\isolated-ui\Invoke-PatternalGuestUiSmoke.ps1 -Mode persistence-only -DisplayWidth 1600 -DisplayHeight 900
.\tools\isolated-ui\Invoke-PatternalGuestUiSmoke.ps1 -Mode persistence-only -DisplayWidth 1920 -DisplayHeight 1080
.\tools\isolated-ui\Invoke-PatternalGuestUiSmoke.ps1 -Mode persistence-only -DisplayWidth 1920 -DisplayHeight 1080 -TextScalePercent 200
.\tools\isolated-ui\Invoke-PatternalGuestUiSmoke.ps1 -Mode persistence-only -WindowsTheme Dark
.\tools\isolated-ui\Invoke-PatternalGuestUiSmoke.ps1 -Mode full -WindowsTheme HighContrast2
```

The guest rejects the run when Windows does not apply the requested mode exactly. For a text-scale run, it records the current per-user value, requests the selected percentage before launching the packaged app, broadcasts the accessibility setting change, and restores or removes the value in `finally`. Always inspect the screenshot because a registry value alone does not prove the application rendered larger text.

`-WindowsTheme` accepts `Current`, `Light`, `Dark`, `HighContrastBlack`, `HighContrastWhite`, `HighContrast1`, and `HighContrast2`. The guest applies the real built-in Windows `.theme` file before launch, verifies both the active theme path and the `SPI_GETHIGHCONTRAST` state, captures the packaged UI, and restores the exact original theme in `finally`. Always inspect the screenshots. A registry path or high-contrast flag proves configuration, not readable pixels.

3. Inspect `result.json`, both UI trees, and every PNG under:

```text
artifacts\isolated-ui\runs\<run-id>\
```

Do not treat a passing JSON result as camera-orientation or cloth-quality proof by itself. Inspect the front, side, rear, oblique, and fit images. A button can invoke successfully while pointing the camera at the avatar's backside; software has achieved stranger victories.

4. Keep failed evidence. Fix the source, sync a new hash-identified payload, and rerun. Never patch files directly inside `C:\PatternalTest\Payloads`.

## Automated interaction coverage

The current guest suite performs these checks in order:

1. Requests a 1920 by 1080 guest display and rejects anything below 1280 by 720. Optional text-scale and Windows-theme requests are applied and verified before launch, then restored in `finally`.
2. Launches the packaged AUMID and verifies a responsive Patternal window.
3. Captures the startup 2D view and a bounded UI Automation tree.
4. Deliberately changes Height with linked proportions disabled, invokes New through guest-local pointer input, confirms the dialog, and requires the dedicated test profile to return to the 167 cm linked-proportion bundled baseline. This makes persistent guest state deterministic without deleting the app profile behind the product's back.
5. Uses only guest-local keyboard input to prove toolbar focus order, opens and closes the real Save As and Open dialogs with Enter and Escape, round-trips the four primary display toggles with Space, switches between 2D and 3D tabs with arrow keys plus Enter, edits and exactly restores Fabric weight, and captures a visible focus ring. It then audits every keyboard-focusable 2D control and fails on any missing accessible name.
6. Before changing any simulation input, enters 3D and locates the six camera controls by stable automation ID. It audits every keyboard-focusable 3D control for an accessible name, captures Front, Right, Rear, Left, Oblique, and Fit views, then returns to 2D. If the cloth is stale, the files are labeled `3d-stale-avatar` and the freshness gate fails while the remaining 2D interaction coverage continues.
7. Invokes 2D Zoom in, Zoom out, and Fit by stable automation ID. It verifies the visible zoom direction and round trip, then captures a post-Fit screenshot for all-pieces-visible review.
8. Selects and frames `Back Torso`, enters point-edit mode, selects its named start anchor through UI Automation, changes its X coordinate, proves Undo, proves Redo, restores the original coordinate, and captures the inspector plus accessible handles.
9. Fits the full canvas, starts polygon drafting, enters four X/Y coordinate pairs through `RangeValuePattern`, captures the visible closed preview, finishes a new piece, proves the piece count changes from 14 to 15 through Undo and Redo, and restores 14 pieces.
10. Fits the canvas again, starts polygon drafting, resolves four empty-space screen points to the Patternal process, places all four corners with guest-local pointer input, captures the visible preview, clicks the first corner to close the piece, proves the count changes through Undo and Redo, and restores 14 pieces.
11. Opens physical-scale calibration, measures the 320-DIP ruler as a deterministic 10 cm, proves the resulting 800% 1:1 view, leaves it with Fit, reapplies it through the 1:1 command, captures the truthful authored-grid and calibrated-scale UI, then restores the prior calibration state and fitted zoom.
12. Selects `Back Torso`, creates a default precise construction line, proves Undo and Redo, edits its name and purpose to a fold guide, verifies the updated named geometry, captures it, proves the update through Undo and Redo, deletes it, proves the deletion through Undo and Redo, and leaves the piece without the test line.
13. Creates a default two-leg guide dart on `Back Torso`, proves Undo and Redo, edits its name and fold direction, verifies both updated named legs, captures them, proves the update through Undo and Redo, deletes it, proves the deletion through Undo and Redo, and leaves the piece without the test dart.
14. Selects the existing `Left side bust dart`, verifies that it uses the sewn-edge construction mode, renames it, changes its fold direction, applies the edit, proves Undo and Redo, captures the rendered physical legs at working scale, and restores the original dart.
15. Creates a temporary polygon, creates a free-edge physical dart on it, verifies both rendered legs, then enters Assembly mode and requires the permanent-seam count to increase by exactly one. It proves Undo and Redo and removes both the dart and temporary piece even if an intermediate assertion fails.
16. Creates a temporary polygon with piece-qualified endpoint identities, marks two opposite edges, sews them, verifies the permanent-seam count through Undo and Redo, captures Assembly mode, then removes the seam and temporary piece.
17. Round-trips the Pieces panel, Inspector panel, seam allowance, and grainline toggles.
18. Temporarily disables linked proportional estimates, changes Height, enters 3D, proves the preview switches from the fitted Antonia candidate to the editable measurement mesh, activates Fit to force a visible render, captures it, restores Height, and proves the fitted candidate returns. Both captures sample the central WebView region and fail when fewer than 5 percent of sampled pixels are non-white. The product restarts one generation-owned render loop whenever 3D becomes visible and reloads only when WebGL reports a lost context.
19. Round-trips Height, Full bust, Waist, Hip, Shoulder, and Torso sliders, then restores the link state.
20. Round-trips Fabric weight and Fabric stretch.
21. Round-trips the fitted-bra toggle when available, or verifies that it is disabled when no matching fitted asset exists.
22. Enters Assembly mode, changes reverse side B, invokes Undo, and verifies that the visible toggle returns to the original state.
23. Opens the real packaged Windows Save As picker through guest-local pointer input, supplies a unique file name, exports SVG, parses the result, and requires the `patterna.garment/1.1` payload to contain 14 simulation panels and 38 seams.
24. Changes Height, linked proportions, and custom fabric weight, opens the real packaged Windows Save As picker, saves a versioned `.patterna` project, parses its scalar and editable construction payload, disturbs the three values, opens the real Windows Open picker, selects the named project, and requires all three values to restore exactly.
25. Disables linked proportions, changes Height, saves the separate local recovery snapshot, terminates Patternal, relaunches the packaged AUMID, and requires both values to restore. It then restores the baseline values, saves again, relaunches again, and captures the cleaned final state.
26. Writes the result bundle and closes the guest app unless `-KeepAppOpen` was requested.

Expand this list whenever a new user-facing toggle, slider, authoring command, camera, persistence behavior, or acceptance gate is added. UI contracts rot if they are treated as museum pieces.

## Windows Sandbox fallback

Windows Sandbox is suitable for a disposable install or launch smoke test when Hyper-V guest provisioning is unavailable. It is not the standard evidence lane because its state disappears at close, its window appears on the host desktop, and its graphics behavior does not establish final physical-GPU quality. Do not auto-launch Sandbox while the user is actively using the host.

## Current setup status

As of 2026-08-09, the host audit confirms Windows 11 Pro, Hyper-V services, Windows Sandbox, 64 GB RAM, an RTX 4090, and sufficient disk space. The persistent Windows 11 guest launches the registered AppX as a responsive top-level window without taking over the host desktop. Reviewed run `20260809-113435-c2c13a96` used payload `aa0885fc8f1dd486e078c5129a8a0dcc4097d570dacf0ef95a1df5a34e74d013`, completed 42 interaction checks, and captured 22 screenshots. Forty-one checks passed. The run correctly failed only the freshness gate because the current pattern, body, assembly, and fabric revision has no accepted cloth. Front, Rear, Right, Left, Oblique, and Fit views retain the corrected glTF image origin and sRGB lighting contracts. The packaged 2D Fit, frame-selected, point-edit, numeric polygon, pointer polygon, calibrated actual-size, updated fold-line, updated guide-dart, sewn-edge physical dart, free-edge physical dart, and free-sewing views remain readable at 1920 by 1080. The scale workflow calibrated a 320-DIP ruler to a deterministic 10 cm measurement, proved the resulting 32 DIPs per centimeter and 800% 1:1 view, left it through Fit, restored it through the 1:1 command, and cleared the test calibration. The pointer workflow placed four corners on empty canvas space and closed the polygon by clicking its first corner, then proved count restoration through Undo and Redo. The internal-line and guide-dart workflows proved create, update, delete, Undo, Redo, and cleanup. The physical-dart workflows edited and restored the existing `Left side bust dart`, then created a free-edge dart on a temporary piece and proved that its compiled closure seam raised the permanent-seam count from 38 to 39. Undo, Redo, and final cleanup restored the original 14-piece document and 38 seams.

The same run exported a real 11,685-byte SVG through Windows Save As and parsed 14 simulation panels plus 38 seams from its embedded `patterna.garment/1.1` document. It saved a 13,481-byte named project with schema `patterna.project/1.0`, disturbed the live state, and restored Height 167.5 cm, linked proportions Off, and custom fabric weight 185 g/m² through the packaged Open picker. It separately saved Height 167.5 cm with linked proportions Off to the local recovery snapshot, terminated the app, restored both values after packaged relaunch, then restored and re-saved the 167 cm linked baseline. Large JSON state now lives in a versioned, atomically replaced file under the package LocalFolder instead of exceeding the per-value `LocalSettings` limit. Legacy settings remain readable. The end-to-end measurement check proved the visible viewport switched to the 151-value editable measurement mesh and returned to the textured fitted Antonia candidate. Both late 3D captures passed a 1.0 non-white sample ratio after the new hidden-tab render-loop recovery, and manual review confirmed that neither image was blank. Visual review still rejects the editable fallback as a product avatar because its anatomy, hands, feet, surface detail, and materials remain far below the fitted candidate. Manual six-view review also rejects Antonia as the final CLO-class avatar because the asymmetric raised-arm pose, bald presentation, modesty assets, and customization depth remain inadequate. Host input injection and VMConnect use remained false. CLO-class completion remains open because accepted cloth, a realistic revision-matched customizable avatar, fitted hair, improved modesty clothing, and physical-GPU proof are still missing.

Focused persistence run `20260809-113015-a9372bba` used payload `aa0885fc8f1dd486e078c5129a8a0dcc4097d570dacf0ef95a1df5a34e74d013`, passed all six actions, and captured three screenshots. It saved a 10,590-byte `.patterna` project through the real Save As picker, required schema `patterna.project/1.0` plus all editable construction payloads, disturbed the live state, opened the file through the real Open picker, and restored Height 167.5 cm, linked proportions Off, and custom fabric weight 185 g/m² exactly. The toolbar remained readable at 1920 by 1080 with distinct New, Open, Save As, and Quick save commands. The independent local recovery snapshot and SVG export checks also passed. Host input injection and VMConnect use remained false.

Responsive focused runs `20260809-114717-6c40d65f`, `20260809-114949-6daea43a`, and `20260809-115049-2d9f1687` used payload `c6a5b159a89c0b89f71efd5bc0dcbb12f9400c0b5332b2f97f7c88816128222e` at exact 1280 by 720, 1600 by 900, and 1920 by 1080 modes. All six actions passed in each run. Manual review confirmed the command bar remained reachable, the pattern workspace remained readable, the named-project confirmation was visible, and the scale footer no longer ran underneath the zoom controls at the minimum size. Host input injection and VMConnect use remained false.

Text-scale run `20260809-115542-513678bc` used payload `a183c6d57a18002148e28162ec18cd3a4563c853aac9fcde4114af259b6f4d3b` at 1920 by 1080 with Windows text scaling requested at 200 percent. All seven actions passed and three screenshots were captured. Manual review confirmed the larger type was visibly applied, command-bar overflow remained available, the 2D canvas and footer controls remained distinct, the inspector remained scrollable, and the named-project confirmation remained readable. The guest registry returned to its original absent `TextScaleFactor` value after the run. Host input injection and VMConnect use remained false.

Theme runs `20260809-130609-c8328deb`, `20260809-130911-2fd5a99d`, `20260809-131007-8b197083`, `20260809-131157-b91530a7`, `20260809-133025-9f0724f9`, and `20260809-132449-2c2b51e0` exercised High Contrast Black, High Contrast White, High Contrast 1, High Contrast 2, Dark, and Light respectively at 1920 by 1080. Each focused run passed all 10 actions, captured four screenshots, proved keyboard toggles, a reversible slider edit, SVG export, named project persistence, local snapshot persistence, and 126 named keyboard-focusable 2D controls. Manual review confirmed readable pattern geometry, labels, side panels, status messages, toggle states, and visible keyboard focus in every theme. Each run restored the exact original `aero.theme` state with high contrast disabled. Host input injection and VMConnect use remained false. The final Dark run used the completed exact-path assertion and preserved-result restoration handling.

Full High Contrast 2 run `20260809-131811-0ced925b` used the same hash-identified packaged application payload, completed 47 actions, passed 46, and captured 23 screenshots. It proved the complete 2D authoring sequence, all six 3D camera commands, 126 named 2D controls, 39 named 3D controls, body and fabric edits, display toggles, avatar edit and restore, SVG export, named project persistence, and local snapshot persistence. Manual review confirmed that 2D points, lines, darts, seam graph, focus, XAML 3D chrome, and all six camera views remained readable. The only failure was the truthful current-cloth freshness gate. The avatar and absent cloth remain visually rejected; high-contrast usability does not make them CLO-class assets. The guest restored `aero.theme` with high contrast disabled, and host input injection and VMConnect use remained false.

Compact stale-state run `20260809-135415-0bfa3de5` used payload `18e435691da6fa9f0f6892fbbcf5054a3f472f23e0b96b049057b29d0f08ccdf`, completed 47 actions, passed 45, and captured 23 screenshots. It moved the stale-cloth state into one accessible, single-line row above the viewport with a fixed regeneration action. Manual review of Front, Right, Rear, Left, Oblique, Fit, the edited measurement avatar, the restored fitted avatar, point editing, and free sewing confirmed that the status no longer covers the body or floor and that the 2D workflows remain readable. All 126 keyboard-focusable 2D controls and 40 keyboard-focusable 3D controls had accessible names. One failure was the required current-cloth freshness rejection. The other was a harness race: Windows had created the named-project destination, but the harness copied its zero-byte placeholder before Patterna completed asynchronous serialization. Focused rerun `20260809-140321-bfcc5128` used the same application payload and passed all 10 actions after the harness waited for Patterna's `Project saved` state and required a nonempty, parseable `patterna.project/1.0` file before copying evidence. The product payload did not change between those runs. Host input injection and VMConnect use remained false.

Keyboard and accessibility run `20260809-124751-67e8517b` used payload `f260ae82d66f2570db88ca224f5ae656040a5ca586d3d2922e37db874717c126` at 1920 by 1080. It completed 46 actions, passed 45, captured 23 screenshots, and failed only because no accepted cloth matches the bundled current revision. The keyboard-only workflow proved toolbar focus order, real Windows dialog activation and dismissal, Space activation for Pieces, Inspector, Seam allowance, and Grainlines, 2D and 3D tab selection, an exact Fabric weight edit and restore, and visible focus. All 126 keyboard-focusable 2D controls and all 39 keyboard-focusable 3D controls exposed non-empty accessible names. The full authoring, SVG export, named project, local recovery, late editable-avatar, and late fitted-avatar checks passed. Manual 2D and 3D screenshot review was completed. Actual Narrator speech remains unobserved; automation names do not prove spoken reading order. Host input injection and VMConnect use remained false.

The persistent guest and its signed application prerequisites are operational. This proves the isolated packaged interaction lane, not the visual quality of the current product. The current 2D all-pieces layout, zoom controls, calibrated 1:1 scale, accessible piece, anchor, and edge selection, precise point entry, numeric and pointer polygon drafting, internal-line and guide-dart create, update, delete, Undo, and Redo workflows, sewn-edge and free-edge physical darts, free sewing, and Frame selected command pass at 1920 by 1080. Current accepted cloth, physical-GPU rendering, and CLO-class multi-view gates remain open.
