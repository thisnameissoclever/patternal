from __future__ import annotations

import json
from pathlib import Path
import shutil
import tempfile
import unittest

from tools.verify_libuipc_arrangement_plan import verify_plan


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
PLAN_FIXTURE = REPOSITORY_ROOT / "artifacts" / "libuipc-arrangement-plan-v1"
SOURCE_BUNDLE = REPOSITORY_ROOT / "artifacts" / "revision-proof-source-v2" / "bundle"


@unittest.skipUnless(PLAN_FIXTURE.is_dir(), "ignored local plan fixture is unavailable")
class LibuipcArrangementPlanTests(unittest.TestCase):
    def copy_fixture(self, root: Path) -> Path:
        destination = root / "plan"
        shutil.copytree(PLAN_FIXTURE, destination)
        return destination

    def test_frozen_plan_verifies(self) -> None:
        result = verify_plan(PLAN_FIXTURE, SOURCE_BUNDLE)
        self.assertTrue(result["accepted"])
        self.assertFalse(result["executionAuthorized"])
        self.assertFalse(result["arrangementAccepted"])
        self.assertEqual(14, result["panelCount"])
        self.assertEqual(932, result["stitchConstraintCount"])

    def test_tampered_mesh_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as raw_root:
            plan = self.copy_fixture(Path(raw_root))
            mesh = next((plan / "panels").glob("*.initial.obj"))
            mesh.write_text(mesh.read_text(encoding="utf-8") + "# tampered\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "size changed|hash changed"):
                verify_plan(plan)

    def test_execution_authorization_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as raw_root:
            plan = self.copy_fixture(Path(raw_root))
            manifest_path = plan / "scene-plan-manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["claims"]["executionAuthorized"] = True
            manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "must not authorize execution"):
                verify_plan(plan)

    def test_undeclared_file_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as raw_root:
            plan = self.copy_fixture(Path(raw_root))
            (plan / "stale.bin").write_bytes(b"stale")
            with self.assertRaisesRegex(ValueError, "file set changed"):
                verify_plan(plan)


if __name__ == "__main__":
    unittest.main()
