from __future__ import annotations

import unittest

from tools.build_body_collision_proxy import (
    distance_metrics,
    edge_topology,
    percentile,
    semantic_region,
)


class BuildBodyCollisionProxyTests(unittest.TestCase):
    def test_percentile_uses_nearest_rank(self) -> None:
        self.assertEqual(4.0, percentile([1.0, 4.0, 2.0, 3.0], 0.95))

    def test_distance_metrics_report_centimeters(self) -> None:
        metrics = distance_metrics([0.001, 0.002, 0.003])
        self.assertAlmostEqual(0.3, metrics["maximumDistanceCm"])
        self.assertAlmostEqual(0.2, metrics["meanDistanceCm"])

    def test_edge_topology_distinguishes_boundary_and_manifold_edges(self) -> None:
        open_mesh = edge_topology([(0, 1, 2), (2, 1, 3)])
        tetrahedron = edge_topology(
            [(0, 2, 1), (0, 1, 3), (1, 2, 3), (2, 0, 3)]
        )
        self.assertEqual(4, open_mesh["boundaryEdgeCount"])
        self.assertEqual(4, open_mesh["nonManifoldEdgeCount"])
        self.assertEqual(0, tetrahedron["nonManifoldEdgeCount"])
        self.assertEqual(1, tetrahedron["connectedComponentCount"])

    def test_semantic_regions_use_height_and_lateral_position(self) -> None:
        self.assertEqual("head", semantic_region((0.0, 1.50, 0.0), 0.0, 1.67))
        self.assertEqual("torso", semantic_region((0.1, 1.10, 0.0), 0.0, 1.67))
        self.assertEqual("arms", semantic_region((0.5, 1.10, 0.0), 0.0, 1.67))
        self.assertEqual("legs", semantic_region((0.1, 0.30, 0.0), 0.0, 1.67))


if __name__ == "__main__":
    unittest.main()
