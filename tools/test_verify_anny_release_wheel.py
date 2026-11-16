from __future__ import annotations

from dataclasses import replace
import hashlib
from pathlib import Path
import tempfile
import unittest
import zipfile

from tools.verify_anny_release_wheel import (
    ReleaseArtifact,
    inspect_wheel,
    verify_wheel,
)


CORE_REQUIREMENTS = (
    "torch>=2.0.0",
    "roma>=1.5.7",
    "numpy",
    "pyyaml",
    "pillow",
    "requests",
    "safetensors",
    "trimesh",
    "warp-lang",
)


class VerifyAnnyReleaseWheelTests(unittest.TestCase):
    def write_wheel(self, path: Path, unsafe_path: str | None = None) -> None:
        metadata = "\n".join(
            [
                "Metadata-Version: 2.4",
                "Name: anny",
                "Version: 0.6.0",
                *[f"Requires-Dist: {item}" for item in CORE_REQUIREMENTS],
                'Requires-Dist: smplx; extra == "smpl"',
                "",
            ]
        )
        with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            archive.writestr("anny-0.6.0.dist-info/METADATA", metadata)
            archive.writestr(
                "anny-0.6.0.dist-info/licenses/LICENSE",
                "Apache License\nVersion 2.0\n",
            )
            archive.writestr(
                "anny/data/mpfb2/LICENSE.md",
                "Creative Commons CC0 1.0 Universal\n",
            )
            archive.writestr("anny/data/cached/anny.pth", b"model")
            archive.writestr("anny/data/mpfb2/3dobjs/base.obj", b"mesh")
            if unsafe_path is not None:
                archive.writestr(unsafe_path, b"unsafe")

    def expected_for(self, path: Path) -> ReleaseArtifact:
        inventory = inspect_wheel(path)
        return ReleaseArtifact(
            filename=path.name,
            version="0.6.0",
            byte_length=path.stat().st_size,
            sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
            data_file_count=inventory["dataFileCount"],
            data_uncompressed_bytes=inventory["dataUncompressedBytes"],
        )

    def test_complete_synthetic_wheel_passes_integrity_scope(self) -> None:
        with tempfile.TemporaryDirectory() as raw_root:
            wheel = Path(raw_root) / "anny-test.whl"
            self.write_wheel(wheel)
            result = verify_wheel(wheel, self.expected_for(wheel))
            self.assertTrue(result["accepted"])
            self.assertEqual(result["scope"], "release-artifact-integrity-only")
            self.assertFalse(result["executionAuthorized"])
            self.assertFalse(result["avatarAccepted"])

    def test_changed_hash_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as raw_root:
            wheel = Path(raw_root) / "anny-test.whl"
            self.write_wheel(wheel)
            expected = replace(self.expected_for(wheel), sha256="0" * 64)
            with self.assertRaisesRegex(ValueError, "sha256 differs"):
                verify_wheel(wheel, expected)

    def test_unsafe_archive_path_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as raw_root:
            wheel = Path(raw_root) / "anny-test.whl"
            self.write_wheel(wheel, "../outside.txt")
            with self.assertRaisesRegex(ValueError, "Unsafe wheel archive path"):
                inspect_wheel(wheel)


if __name__ == "__main__":
    unittest.main()
