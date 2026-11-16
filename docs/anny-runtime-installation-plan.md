# Anny runtime installation plan

Date: 2026-08-22

Status: executed 2026-08-28 after explicit authorization. The runtime is installed at `%LOCALAPPDATA%\Patterna\ChallengerRuntimes\Anny\v0.6.0-py312-torch2.13.0-cu126` through `tools/install_patterna_challenger_runtimes.ps1 -Component Anny`; see `docs/challenger-runtime-installation.md` for the installed evidence. One closure amendment was required: `safetensors 0.7.0` imports `packaging` at runtime without declaring it, so the uv.lock-pinned `packaging 26.2` wheel joined the hash-locked wheelhouse.

## Decision

Use the official Anny 0.6.0 wheel in a dedicated Patterna worker environment. Do not install Anny into Patternal, the Windows VM, the global Python environment, Blender, or any existing avatar runtime.

The execution artifact is:

1. Filename: `anny-0.6.0-py3-none-any.whl`
2. Release tag commit: `72104cac8242d1735ec06433b65bec5e26953ce7`
3. Byte length: `47,705,473`
4. SHA-256: `050a0b24a3e7fdb89b46dc3581947ea84225305425ac9a1a97b65ea997fb2ad6`
5. Native data files: `1,559`
6. Native data size after extraction: `107,825,068` bytes
7. Code license: Apache-2.0
8. MPFB2 and face-action data license: CC0-1.0

The reviewed post-release source commit `81ca83e202273b306205c1cc15f33734be31e48c` differs from the tag by one six-line keypoint-device correction. Patterna's body worker does not use the keypoint regressor. Installing the release wheel is more reproducible than patching a checkout, and it avoids the post-release source metadata's reference to a missing `LICENSE_THINGS` file.

## Environment boundary

The runtime lives under a versioned Patterna worker root, separate from application source and existing environments. Its cache lives under the same root through `ANNY_CACHE_DIR`. The app receives only independently accepted GLB, collider, control-map, and provenance artifacts.

The target interpreter is the installed CPython 3.12. The host currently has an RTX 4090 with 24,564 MiB of memory and NVIDIA driver 610.88. The proposed locked runtime uses the Anny release lock's CUDA 12.6 PyTorch route. No CUDA toolkit installation or system PATH change is part of this plan.

## Allowed dependencies

Only the Anny core dependency closure is allowed:

1. `torch`
2. `roma`
3. `numpy`
4. `pyyaml`
5. `pillow`
6. `requests`
7. `safetensors`
8. `trimesh`
9. `warp-lang`
10. Their exact transitive dependencies from a generated, hash-locked CPython 3.12 Windows wheelhouse manifest

Do not install the `examples`, `smpl`, `dev`, or other optional extras. In particular, do not install `smplx`, `chumpy`, `py-soma-x`, Gradio, Jupyter, or notebook tooling.

## Reproducible acquisition

After dependency installation is explicitly authorized:

1. Create a new versioned worker directory and CPython 3.12 virtual environment.
2. Download the exact Anny wheel and exact CPython 3.12 Windows dependency wheels into a Patterna-only wheelhouse.
3. Record the URL, filename, byte length, SHA-256, package name, version, and license for every wheel.
4. Reject source distributions and any wheel absent from the manifest.
5. Run `tools/verify_anny_release_wheel.py` against the downloaded Anny wheel and require acceptance only for release-artifact integrity.
6. Install offline from the wheelhouse with dependency resolution disabled.
7. Set `ANNY_CACHE_DIR` to the versioned worker cache before the first import.
8. Block outbound network access for the actual worker process.
9. Verify that no files appear in the user Anny, Torch, Hugging Face, browser-download, or other project caches.
10. Run one neutral native-topology smoke test and inventory every loaded source data file.
11. Preserve the environment and wheelhouse as a content-addressed research worker until the bakeoff accepts or rejects Anny.

## Hard failures

Stop without retrying around any of these conditions:

1. A wheel hash or byte length differs.
2. Dependency resolution requires an optional extra or source build.
3. Anny attempts an implicit download.
4. The process touches a cache outside the worker root.
5. The runtime loads SMPL, SMPL-X, or another restricted model family.
6. The neutral mesh, rig, topology, or data inventory differs between two clean runs.
7. Base anatomy fails the bounded multi-angle visual gate.

This plan authorizes no installation by itself.
