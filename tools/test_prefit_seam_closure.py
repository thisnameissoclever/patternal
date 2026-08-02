import unittest

import numpy as np

from tools.prefit_garmentcode_warp import evaluate_acceptance, evaluate_seam_closure


class SeamClosureTests(unittest.TestCase):
    def test_measures_every_explicit_seam_link(self):
        vertices = np.asarray(
            [
                [0.0, 0.0, 0.0],
                [0.1, 0.0, 0.0],
                [1.0, 0.0, 0.0],
                [1.0, 0.2, 0.0],
            ],
            dtype=float,
        )

        maximum, mean, percentile, maximum_link = evaluate_seam_closure(
            vertices,
            [(0, 1), (2, 3)],
        )

        self.assertAlmostEqual(maximum, 0.2)
        self.assertAlmostEqual(mean, 0.15)
        self.assertGreater(percentile, 0.19)
        self.assertEqual(maximum_link, [2, 3])

    def test_empty_links_are_not_an_evaluated_gate(self):
        self.assertEqual(
            evaluate_seam_closure(np.zeros((1, 3), dtype=float), []),
            (None, None, None, None),
        )

    def test_acceptance_rejects_open_or_missing_explicit_seams(self):
        shared = dict(
            finite_positions=True,
            equilibrium_gate_evaluated=True,
            static_equilibrium_reached=True,
            edge_contact_buffer_saturated=False,
            maximum_observed_edge_contacts=0,
            edge_contact_capacity=100,
            body_collisions=0,
            self_collisions=0,
            maximum_edge_strain_ratio=0.0,
            ninety_fifth_percentile_edge_strain_ratio=0.0,
            ninety_ninth_point_ninth_percentile_edge_strain_ratio=0.0,
            max_body_collisions=0,
            max_self_collisions=0,
            max_edge_strain_ratio=1.0,
            max_ninety_fifth_percentile_edge_strain_ratio=1.0,
            max_ninety_ninth_point_ninth_percentile_edge_strain_ratio=1.0,
            max_seam_separation_cm=0.25,
        )

        missing_accepted, missing_reasons = evaluate_acceptance(
            seam_link_count=0,
            maximum_seam_separation_cm=None,
            **shared,
        )
        open_accepted, open_reasons = evaluate_acceptance(
            seam_link_count=12,
            maximum_seam_separation_cm=0.26,
            **shared,
        )
        closed_accepted, closed_reasons = evaluate_acceptance(
            seam_link_count=12,
            maximum_seam_separation_cm=0.24,
            **shared,
        )

        self.assertFalse(missing_accepted)
        self.assertIn("explicit seam-closure gate was not evaluated", missing_reasons)
        self.assertFalse(open_accepted)
        self.assertTrue(any("maximum seam separation" in value for value in open_reasons))
        self.assertTrue(closed_accepted)
        self.assertEqual(closed_reasons, [])


if __name__ == "__main__":
    unittest.main()
