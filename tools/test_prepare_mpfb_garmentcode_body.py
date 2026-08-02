from __future__ import annotations

import unittest

import numpy as np

from tools.mpfb_measurements import MEASUREMENT_VERTEX_CHAINS
from tools.prepare_mpfb_garmentcode_body import torso_station_heights_cm


def _landmarked_vertices() -> np.ndarray:
    vertices = np.zeros((13380, 3), dtype=float)
    for name, height_m in (
        ("waist_circumference", 0.95),
        ("underbust_circumference", 1.10),
        ("bust_circumference", 1.18),
        ("front_chest_distance", 1.27),
    ):
        vertices[np.asarray(MEASUREMENT_VERTEX_CHAINS[name]), 1] = height_m
    nape_index = MEASUREMENT_VERTEX_CHAINS["nape_to_waist"][0]
    vertices[nape_index, 1] = 1.44
    return vertices


class TorsoStationContractTests(unittest.TestCase):
    def test_closed_upper_circuit_is_not_the_high_bust_tape_plane(self) -> None:
        stations = torso_station_heights_cm(
            _landmarked_vertices(),
            {
                "measurements": {
                    "armholeDepthL": 21.6,
                    "armholeDepthR": 22.0,
                }
            },
        )

        self.assertAlmostEqual(122.2, stations["underarmCircuit"])
        self.assertAlmostEqual(120.73, stations["upperTorsoCircuit"])
        self.assertAlmostEqual(127.0, stations["highBustTape"])
        self.assertLess(
            stations["upperTorsoCircuit"],
            stations["underarmCircuit"],
        )
        self.assertLess(stations["underarmCircuit"], stations["highBustTape"])

    def test_detailed_armhole_depth_is_required(self) -> None:
        with self.assertRaisesRegex(ValueError, "armholeDepth"):
            torso_station_heights_cm(
                _landmarked_vertices(),
                {"measurements": {}},
            )

    def test_high_bust_tape_must_be_above_underarm(self) -> None:
        vertices = _landmarked_vertices()
        vertices[
            np.asarray(MEASUREMENT_VERTEX_CHAINS["front_chest_distance"]),
            1,
        ] = 1.20

        with self.assertRaisesRegex(ValueError, "high-chest tape"):
            torso_station_heights_cm(
                vertices,
                {
                    "measurements": {
                        "armholeDepthL": 21.8,
                        "armholeDepthR": 21.8,
                    }
                },
            )


if __name__ == "__main__":
    unittest.main()
