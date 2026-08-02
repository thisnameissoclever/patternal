from __future__ import annotations

import hashlib
import json
from pathlib import Path
import struct
import unittest


REPO_ROOT = Path(__file__).resolve().parents[1]
PROOF_DIRECTORY = REPO_ROOT / "artifacts" / "product-acceptance" / "current"
PROOF_PATH = PROOF_DIRECTORY / "manifest.json"
AVATAR_DIRECTORY = REPO_ROOT / "Patterna" / "Assets" / "Production" / "Avatar"
GARMENT_PATH = (
    REPO_ROOT
    / "Patterna"
    / "Assets"
    / "Production"
    / "patterna-production-crew-neck.obj"
)
FABRIC_PATH = (
    REPO_ROOT
    / "third_party"
    / "GarmentCode"
    / "assets"
    / "img"
    / "fabric_texture.png"
)
BODY_PATH = (
    REPO_ROOT
    / "Patterna"
    / "Assets"
    / "Production"
    / "patterna-mpfb-female.obj"
)
SOURCE_BODY_PATH = BODY_PATH.with_suffix(".source.obj")
FIT_REPORT_PATH = GARMENT_PATH.with_suffix(".fit.json")
BODY_REPORT_PATH = BODY_PATH.with_suffix(".report.json")
COMPILER_MANIFEST_PATH = GARMENT_PATH.with_suffix(".compile.json")
EXPECTED_VIEWS = {
    "front",
    "front-oblique",
    "left",
    "back",
    "back-oblique",
    "right",
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def png_dimensions(path: Path) -> tuple[int, int]:
    with path.open("rb") as source:
        signature = source.read(8)
        if signature != b"\x89PNG\r\n\x1a\n":
            raise ValueError(f"{path} is not a PNG")
        length = struct.unpack(">I", source.read(4))[0]
        chunk_type = source.read(4)
        if chunk_type != b"IHDR" or length < 8:
            raise ValueError(f"{path} has no leading IHDR chunk")
        width, height = struct.unpack(">II", source.read(8))
        return width, height


class ProductAcceptanceArtifactsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.proof = json.loads(PROOF_PATH.read_text(encoding="utf-8"))
        cls.avatar_manifest = json.loads(
            (AVATAR_DIRECTORY / "manifest.json").read_text(encoding="utf-8")
        )
        cls.fit_report = json.loads(FIT_REPORT_PATH.read_text(encoding="utf-8"))
        cls.body_report = json.loads(BODY_REPORT_PATH.read_text(encoding="utf-8"))
        cls.compiler_manifest = json.loads(
            COMPILER_MANIFEST_PATH.read_text(encoding="utf-8")
        )

    def test_proof_uses_the_current_product_assets(self) -> None:
        self.assertEqual(
            "patterna.product-turntable/1.0",
            self.proof["schema_version"],
        )
        self.assertEqual(7, self.proof["avatar_object_count"])
        self.assertIs(True, self.proof["show_bra"])
        self.assertEqual(sha256(GARMENT_PATH), self.proof["garment_sha256"])
        self.assertEqual(sha256(FABRIC_PATH), self.proof["fabric_sha256"])
        self.assertEqual(
            sha256(AVATAR_DIRECTORY / "manifest.json"),
            self.proof["avatar_hashes"]["manifest"],
        )
        for asset_name, asset in self.avatar_manifest["assets"].items():
            self.assertEqual(
                sha256(AVATAR_DIRECTORY / asset["geometry"]),
                self.proof["avatar_hashes"][f"{asset_name}_geometry"],
            )
            self.assertEqual(
                sha256(AVATAR_DIRECTORY / asset["texture"]),
                self.proof["avatar_hashes"][f"{asset_name}_texture"],
            )

    def test_body_and_garment_registration_is_accepted(self) -> None:
        registration = self.proof["registration"]
        self.assertEqual(
            "patterna.product-registration/2.0",
            registration["schema_version"],
        )
        self.assertTrue(registration["accepted"])
        self.assertEqual([], registration["issues"])
        body_bounds = registration["body_bounds_m"]
        garment_bounds = registration["garment_bounds_m"]
        center_offset = registration["center_offset_m"]
        coverage = registration["anatomical_vertical_coverage"]
        self.assertLessEqual(body_bounds["minimum"][2], 0.001)
        self.assertGreaterEqual(body_bounds["maximum"][2], 1.65)
        self.assertGreaterEqual(garment_bounds["minimum"][2], 0.70)
        self.assertGreaterEqual(garment_bounds["maximum"][2], 1.25)
        self.assertGreaterEqual(registration["vertical_overlap_m"], 0.45)
        self.assertLessEqual(abs(center_offset[0]), 0.04)
        self.assertLessEqual(abs(center_offset[1]), 0.25)
        self.assertGreaterEqual(
            coverage["garment_minimum_body_height_fraction"],
            0.44,
        )
        self.assertLessEqual(
            coverage["garment_minimum_body_height_fraction"],
            0.62,
        )
        self.assertGreaterEqual(
            coverage["garment_maximum_body_height_fraction"],
            0.76,
        )
        self.assertLessEqual(
            coverage["garment_maximum_body_height_fraction"],
            0.93,
        )

    def test_render_surface_is_bound_to_exact_body_clearance_evidence(self) -> None:
        garment_hash = sha256(GARMENT_PATH)
        self.assertEqual(
            "patterna.newton-style3d-report/1.0",
            self.fit_report["schema_version"],
        )
        self.assertTrue(self.fit_report["accepted"])
        self.assertTrue(self.fit_report["finite_positions"])
        self.assertTrue(self.fit_report["static_equilibrium_reached"])
        self.assertEqual([], self.fit_report["rejection_reasons"])
        self.assertEqual(0, self.fit_report["body_collisions"])
        self.assertEqual(0, self.fit_report["self_collisions"])
        self.assertEqual(0.0, self.fit_report["maximum_seam_separation_cm"])
        self.assertGreaterEqual(self.fit_report["completed_frames"], 120)
        self.assertGreaterEqual(self.fit_report["simulation_substeps"], 20)
        self.assertLessEqual(
            self.fit_report["ninety_fifth_percentile_edge_strain_ratio"],
            self.fit_report["max_ninety_fifth_percentile_edge_strain_ratio"],
        )
        self.assertLessEqual(
            self.fit_report["ninety_ninth_point_ninth_percentile_edge_strain_ratio"],
            self.fit_report[
                "max_ninety_ninth_point_ninth_percentile_edge_strain_ratio"
            ],
        )
        self.assertEqual(
            garment_hash,
            self.fit_report["bundled_render_mesh_sha256"],
        )
        self.assertEqual(
            sha256(COMPILER_MANIFEST_PATH),
            self.fit_report["bundled_compiler_manifest_sha256"],
        )
        self.assertEqual(131910, self.fit_report["physical_vertex_count"])
        self.assertEqual(262814, self.fit_report["physical_face_count"])
        self.assertEqual(
            "patterna.full-garment-usd/1.1",
            self.compiler_manifest["schemaVersion"],
        )
        self.assertEqual(526636, self.compiler_manifest["render"]["vertexCount"])
        self.assertEqual(1051256, self.compiler_manifest["render"]["triangleCount"])
        self.assertEqual(
            garment_hash,
            self.compiler_manifest["render"]["objSha256"],
        )
        self.assertEqual(
            sha256(BODY_PATH),
            self.fit_report["body_mesh_sha256"],
        )
        self.assertEqual(
            sha256(BODY_PATH),
            self.body_report["outputBodySha256"],
        )
        self.assertEqual(
            sha256(SOURCE_BODY_PATH),
            self.body_report["sourceBodySha256"],
        )
        self.assertEqual(
            sha256(SOURCE_BODY_PATH),
            self.body_report["bundledSourceBodySha256"],
        )
        self.assertTrue(self.body_report["watertight"])
        self.assertEqual(1, self.body_report["connectedComponents"])

    def test_optional_bra_is_thin_and_does_not_change_body_identity(self) -> None:
        bra = self.avatar_manifest["assets"]["bra"]
        self.assertIs(True, bra["display_optional"])
        self.assertLessEqual(bra["maximum_surface_offset_m"], 0.0001)
        self.assertEqual(
            "../patterna-mpfb-female.obj",
            self.avatar_manifest["collision_geometry"],
        )

    def test_six_current_nonempty_views_are_hashed(self) -> None:
        self.assertEqual(EXPECTED_VIEWS, set(self.proof["views"]))
        self.assertEqual(EXPECTED_VIEWS, set(self.proof["renders"]))
        self.assertEqual([720, 900], self.proof["resolution"])
        hashes: set[str] = set()
        for view_name, render in self.proof["renders"].items():
            path = PROOF_DIRECTORY / render["path"]
            self.assertTrue(path.is_file(), view_name)
            self.assertEqual((720, 900), png_dimensions(path), view_name)
            self.assertGreater(path.stat().st_size, 100_000, view_name)
            self.assertEqual(path.stat().st_size, render["byte_count"], view_name)
            self.assertEqual(sha256(path), render["sha256"], view_name)
            hashes.add(render["sha256"])
        self.assertEqual(6, len(hashes))
        self.assertFalse((PROOF_DIRECTORY / "error.json").exists())


if __name__ == "__main__":
    unittest.main()
