from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from tools.collect_ppf_patterna_session import (
    configured_frame_count,
    native_session_parameters,
    sorted_frame_paths,
)


class CollectPpfPatternaSessionTests(unittest.TestCase):
    def test_frame_paths_sort_by_numeric_index(self) -> None:
        with tempfile.TemporaryDirectory() as raw_directory:
            root = Path(raw_directory)
            for name in ("vert_10.bin", "vert_2.bin", "vert_0.bin"):
                (root / name).write_bytes(b"")
            self.assertEqual(
                ["vert_0.bin", "vert_2.bin", "vert_10.bin"],
                [path.name for path in sorted_frame_paths(root)],
            )

    def test_configured_frame_count_comes_from_native_session(self) -> None:
        with tempfile.TemporaryDirectory() as raw_directory:
            root = Path(raw_directory)
            (root / "param.toml").write_text(
                "[param]\nframes = 20\n",
                encoding="utf-8",
            )
            self.assertEqual(20, configured_frame_count(root))
            self.assertEqual(
                {"frames": 20},
                native_session_parameters(root),
            )


if __name__ == "__main__":
    unittest.main()
