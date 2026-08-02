#!/usr/bin/env python3
"""Regression test for collision refresh during every cloth substep."""

from __future__ import annotations

import unittest
from unittest.mock import patch

from pygarment.meshgen.garment import (
    Cloth,
    build_seam_components,
    sewing_ramp_progress,
)


class _State:
    def clear_forces(self) -> None:
        pass


class _Integrator:
    def simulate(self, model: object, state_0: object, state_1: object, dt: float) -> None:
        pass


class SubstepCollisionTests(unittest.TestCase):
    def test_seam_links_build_deterministic_disjoint_components(self) -> None:
        self.assertEqual(
            [[2, 4, 7, 9], [12, 13]],
            build_seam_components([(7, 4), (9, 2), (4, 2), (13, 12)]),
        )

    def test_progressive_sewing_uses_smooth_bounded_schedule(self) -> None:
        self.assertEqual(sewing_ramp_progress(0, 10, 100), 0.0)
        self.assertEqual(sewing_ramp_progress(10, 10, 100), 0.0)
        self.assertAlmostEqual(sewing_ramp_progress(60, 10, 100), 0.5)
        self.assertEqual(sewing_ramp_progress(110, 10, 100), 1.0)
        self.assertEqual(sewing_ramp_progress(500, 10, 100), 1.0)
        self.assertEqual(sewing_ramp_progress(0, 0, 0), 1.0)

    def test_contacts_are_rebuilt_for_every_integration_substep(self) -> None:
        cloth = object.__new__(Cloth)
        cloth.sim_substeps = 4
        cloth.sim_dt = 1.0 / 600.0
        cloth.model = object()
        cloth.state_0 = _State()
        cloth.state_1 = _State()
        cloth.integrator = _Integrator()
        cloth.config = type("Config", (), {"enable_seam_projection": False})()
        cloth.seam_component_count = 0

        with patch("pygarment.meshgen.garment.wp.sim.collide") as collide:
            cloth._sim_frame_with_substeps()

        self.assertEqual(collide.call_count, cloth.sim_substeps)
        self.assertTrue(all(call.args[2] == cloth.sim_dt for call in collide.call_args_list))


if __name__ == "__main__":
    unittest.main()
