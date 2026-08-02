from __future__ import annotations

import math
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "third_party" / "GarmentCode" / "pygarment"))
sys.path.insert(0, str(ROOT / "third_party" / "GarmentCode"))
sys.path.insert(0, str(ROOT / "tools"))

from patterna_garment_blocks import (  # noqa: E402
    PatternaPrincessBodice,
    PatternaPrincessBackCenterPanel,
    PatternaPrincessBackSidePanel,
    PatternaPrincessFrontCenterPanel,
    PatternaPrincessFrontSidePanel,
    _curve_point_at_y,
    compute_cup_aware_block_measurements,
)


def _body() -> dict[str, float]:
    return {
        "bust": 98.0,
        "underbust": 79.8,
        "waist": 78.0,
        "back_width": 45.285737179487164,
        "waist_back_width": 38.9242718446602,
        "shoulder_w": 40.0,
        "bust_points": 18.6,
        "waist_over_bust_line": 43.5,
        "waist_line": 41.8,
        "bust_line": 24.2,
        "_bust_line": 22.5,
        "vert_bust_line": 15.1,
        "_armscye_depth": 15.142,
        "armscye_circumference": 36.0,
        "neck_w": 17.7694,
        "_shoulder_incl": 11.75,
        "height": 167.0,
        "head_l": 23.1,
    }


def _design() -> dict:
    return {"shirt": {}}


def _large_bust_body_with_station_profile() -> dict[str, float]:
    body = {
        "bust": 115.0,
        "high_bust": 96.0,
        "underbust": 84.0,
        "waist": 84.0,
        "back_width": 48.86583984590591,
        "waist_back_width": 42.983854768798814,
        "shoulder_w": 37.0,
        "bust_points": 19.0,
        "waist_over_bust_line": 47.0,
        "waist_line": 41.8,
        "bust_line": 24.7,
        "_bust_line": 18.3,
        "vert_bust_line": 15.1,
        "_armscye_depth": 16.1955,
        "armscye_circumference": 45.5,
        "neck_w": 17.7694,
        "_shoulder_incl": 21.75,
        "height": 167.0,
        "head_l": 23.1,
        "patterna_requested_armhole_depth": 21.8,
        "patterna_armhole_depth_is_estimated": 1.0,
        "patterna_armscye_is_estimated": 0.0,
        "patterna_back_bust_fraction": 0.4249203464861383,
        "patterna_back_upper_torso_fraction": 0.4280267285035587,
        "patterna_back_underarm_fraction": 0.4269307604335981,
        "patterna_back_underbust_fraction": 0.5360484464523183,
        "patterna_back_waist_fraction": 0.5117125567714145,
        "patterna_waist_level_world": 95.90748470434784,
        "patterna_side_seam_height_from_waist": 25.349452395652136,
        "patterna_upper_torso_height_from_waist": 24.528927677924884,
        "patterna_high_bust_tape_height_from_waist": 30.891802745652157,
        "patterna_full_bust_horizontal_circumference": 115.45044011181838,
        "patterna_upper_torso_circumference": 115.69643408051064,
        "patterna_underarm_circumference": 113.48886708966103,
    }
    stations = (
        (23.0051, 115.4504, 0.42492),
        (24.5289, 115.6964, 0.42803),
        (25.3495, 113.4889, 0.42693),
        (26.1269, 110.5152, 0.42273),
        (26.9484, 106.7808, 0.42422),
        (28.0986, 102.0280, 0.42949),
        (30.8918, 95.9999, 0.42994),
    )
    body["patterna_torso_station_profile_count"] = float(len(stations))
    for index, (height, circumference, back_fraction) in enumerate(stations):
        prefix = f"patterna_torso_station_{index:02d}"
        body[f"{prefix}_height_from_waist"] = height
        body[f"{prefix}_circumference"] = circumference
        body[f"{prefix}_back_fraction"] = back_fraction
    return body


def _anny_large_bust_body() -> dict[str, float]:
    """Stable regression fixture derived from the accepted Anny body export."""
    return {
        "bust": 112.0,
        "high_bust": 96.0,
        "underbust": 84.0,
        "waist": 82.0,
        "back_width": 50.52661680754175,
        "waist_back_width": 37.592277712425535,
        "shoulder_w": 37.0,
        "bust_points": 19.0,
        "waist_over_bust_line": 47.0,
        "waist_line": 41.8,
        "bust_line": 24.7,
        "_bust_line": 18.9,
        "vert_bust_line": 18.9,
        "_armscye_depth": 13.7,
        "armscye_circumference": 45.5,
        "neck_w": 17.77,
        "_shoulder_incl": 11.75,
        "height": 167.0,
        "head_l": 23.1,
        "patterna_requested_armhole_depth": 21.8,
        "patterna_armhole_depth_is_estimated": 1.0,
        "patterna_armscye_is_estimated": 1.0,
        "patterna_front_armscye_fraction": 0.5163212253482297,
        "patterna_back_bust_fraction": 0.4511305072101942,
        "patterna_back_upper_torso_fraction": 0.46341842327525695,
        "patterna_back_underarm_fraction": 0.4841927660914614,
        "patterna_back_underbust_fraction": 0.5143261845189125,
        "patterna_back_waist_fraction": 0.4584424111271406,
        "patterna_waist_level_world": 101.83780942894325,
        "patterna_side_seam_height_from_waist": 25.2,
        "patterna_upper_torso_height_from_waist": 24.08,
        "patterna_high_bust_tape_height_from_waist": 26.7,
        "patterna_bust_height_from_waist": 22.0,
        "patterna_underbust_height_from_waist": 15.0,
        "patterna_front_princess_contour_length": 25.626192975740906,
        "patterna_front_princess_upper_contour_length": 25.7523980099593,
        "patterna_full_bust_horizontal_circumference": 111.99902783653212,
        "patterna_upper_torso_circumference": 110.21112255471249,
        "patterna_underarm_circumference": 107.86596991045127,
        "patterna_front_depth_sign": -1.0,
        "patterna_front_staging_depth_cm": -31.788072,
        "patterna_back_staging_depth_cm": 3.609632,
    }


class CupAwarePrincessBlockTests(unittest.TestCase):
    def test_evaluated_surface_landmarks_override_profile_height_heuristics(self) -> None:
        body = _body()
        body["patterna_bust_height_from_waist"] = 22.95
        body["patterna_underbust_height_from_waist"] = 15.67
        body["patterna_front_princess_contour_length"] = 25.4
        body["patterna_front_princess_upper_contour_length"] = 26.1

        block = compute_cup_aware_block_measurements(body, _design())

        self.assertEqual(22.95, block["bust_height_from_waist"])
        self.assertEqual(15.67, block["underbust_height_from_waist"])
        self.assertEqual(25.4, block["front_princess_contour_length"])
        self.assertEqual(26.1, block["front_princess_upper_contour_length"])

    def test_large_cup_station_ease_is_independent_of_full_bust_ease(self) -> None:
        body = _large_bust_body_with_station_profile()
        body["bust"] = 120.0
        design = {
            "shirt": {
                "patterna_chest_ease": {"v": 8.0},
                "patterna_underbust_ease": {"v": 0.75},
                "patterna_upper_torso_ease": {"v": 1.5},
                "patterna_underarm_ease": {"v": 2.25},
            }
        }

        block = compute_cup_aware_block_measurements(body, design)

        self.assertEqual(8.0, block["bust_ease_cm"])
        self.assertEqual(0.75, block["underbust_ease_cm"])
        self.assertEqual(1.5, block["upper_torso_ease_cm"])
        self.assertEqual(2.25, block["underarm_ease_cm"])
        self.assertAlmostEqual(84.75, block["drafting_underbust"])
        self.assertAlmostEqual(
            body["patterna_upper_torso_circumference"] + 1.5,
            block["drafting_upper_torso"],
        )
        self.assertAlmostEqual(
            body["patterna_underarm_circumference"] + 2.25,
            block["drafting_underarm"],
        )

    def test_large_cup_station_ease_defaults_are_fitted_caps(self) -> None:
        body = _large_bust_body_with_station_profile()
        body["bust"] = 120.0
        design = {"shirt": {"patterna_chest_ease": {"v": 8.0}}}

        block = compute_cup_aware_block_measurements(body, design)

        self.assertEqual(1.0, block["underbust_ease_cm"])
        self.assertEqual(2.0, block["upper_torso_ease_cm"])
        self.assertEqual(3.0, block["underarm_ease_cm"])
        self.assertAlmostEqual(85.0, block["drafting_underbust"])

    def test_independent_measurements_drive_cup_geometry(self) -> None:
        design = _design()
        design["shirt"]["patterna_high_bust"] = {"v": 88.0}
        design["shirt"]["patterna_bust_span"] = {"v": 20.0}
        design["shirt"]["patterna_front_princess_upper_contour_length"] = {
            "v": 27.4
        }

        block = compute_cup_aware_block_measurements(_body(), design)

        self.assertEqual(88.0, block["high_bust"])
        self.assertEqual(36.0, block["armscye_circumference"])
        self.assertEqual(10.0, block["cup_difference"])
        self.assertEqual(10.0, block["bust_apex_half"])
        self.assertEqual(_body()["underbust"], block["drafting_underbust"])
        self.assertEqual(
            _body()["vert_bust_line"],
            block["underbust_height_from_waist"],
        )
        self.assertGreater(block["cup_turn_angle_deg"], 20.0)
        self.assertEqual(_body()["waist_line"], block["measured_back_waist_length"])
        self.assertEqual(block["front_length"], block["back_length"])
        self.assertAlmostEqual(19.3, block["bust_height_from_waist"])
        self.assertAlmostEqual(24.2, block["shoulder_to_bust"])
        self.assertGreater(
            block["front_princess_contour_length"],
            block["bust_height_from_waist"],
        )
        self.assertEqual(27.4, block["front_princess_upper_contour_length"])
        self.assertAlmostEqual(
            block["front_length"] - block["armscye_depth"],
            block["side_seam_height"],
        )
        self.assertAlmostEqual(
            _body()["height"]
            - _body()["head_l"]
            - _body()["waist_over_bust_line"],
            block["waist_level_world"],
        )

    def test_princess_seams_are_length_matched_without_dart_junctions(self) -> None:
        block = compute_cup_aware_block_measurements(_body(), _design())
        front_center = PatternaPrincessFrontCenterPanel("front_center", block)
        front_center_circuit_x = (
            _curve_point_at_y(
                front_center.princess_upper,
                block["upper_torso_height_from_waist"],
            )[0],
            _curve_point_at_y(
                front_center.princess_upper,
                block["side_seam_height"],
            )[0],
        )
        front_side = PatternaPrincessFrontSidePanel(
            "front_side",
            block,
            front_center.princess_lengths,
            front_center_circuit_x,
        )
        back_center = PatternaPrincessBackCenterPanel("back_center", block)
        back_side = PatternaPrincessBackSidePanel(
            "back_side", block, back_center
        )

        self.assertLess(
            abs(
                front_center.interfaces["princess"].edges.length()
                - front_side.interfaces["princess"].edges.length()
            ),
            0.08,
        )
        self.assertAlmostEqual(
            block["front_princess_contour_length"],
            front_center.princess_lower.length(),
            places=5,
        )
        self.assertAlmostEqual(
            front_center.princess_lower.length(),
            front_side.princess_lower.length(),
            places=5,
        )
        self.assertAlmostEqual(
            block["front_princess_upper_contour_length"],
            front_center.princess_upper.length(),
            places=5,
        )
        self.assertAlmostEqual(
            front_center.princess_upper.length(),
            front_side.princess_upper.length(),
            places=5,
        )
        self.assertAlmostEqual(
            block["bust_height_from_waist"],
            front_side.princess_lower.start[1],
            places=6,
            msg="A contour-length correction must not move the bust landmark.",
        )
        self.assertAlmostEqual(
            front_center.princess_upper.end[1],
            front_side.princess_upper.start[1],
            places=6,
            msg="Both front panels must register the same shoulder landmark.",
        )
        self.assertIs(
            front_side.princess_lower,
            front_side.interfaces["princess"].edges[0],
        )
        self.assertIs(
            front_side.princess_upper,
            front_side.interfaces["princess"].edges[1],
        )
        upper_y = block["upper_torso_height_from_waist"]
        drafted_front_upper_half = abs(
            _curve_point_at_y(front_center.princess_upper, upper_y)[0]
        ) + abs(
            front_side.high_bust_outer[0]
            - _curve_point_at_y(front_side.princess_upper, upper_y)[0]
        )
        self.assertAlmostEqual(
            block["front_upper_torso_half"],
            drafted_front_upper_half,
            places=6,
            msg=(
                "The front side panel must reproduce the body-bound upper-torso "
                "circuit independently of the high-bust tape measurement."
            ),
        )
        self.assertAlmostEqual(
            block["front_waist_half"] - block["bust_apex_half"] * 0.78,
            front_side.bottom.end[0] - front_side.bottom.start[0],
            places=6,
            msg="Bust projection must not silently enlarge the front waist.",
        )
        self.assertLess(
            abs(
                back_center.interfaces["princess"].edges.length()
                - back_side.interfaces["princess"].edges.length()
            ),
            0.08,
        )
        for panel in (front_center, front_side, back_center, back_side):
            self.assertFalse(panel.is_self_intersecting())
            for vertex in panel.edges.verts():
                self.assertTrue(all(math.isfinite(value) for value in vertex))

    def test_mesh_measured_station_fractions_control_front_back_allocation(self) -> None:
        body = _body()
        body.update(
            {
                "patterna_back_bust_fraction": 0.41,
                "patterna_back_high_bust_fraction": 0.43,
                "patterna_back_underbust_fraction": 0.47,
                "patterna_back_waist_fraction": 0.49,
                "waist_back_width": body["waist"] * 0.49,
            }
        )

        block = compute_cup_aware_block_measurements(body, _design())

        self.assertAlmostEqual(0.41, block["back_bust_fraction"])
        self.assertAlmostEqual(0.43, block["back_high_bust_fraction"])
        self.assertAlmostEqual(0.47, block["back_underbust_fraction"])
        self.assertAlmostEqual(0.49, block["back_waist_fraction"])
        self.assertAlmostEqual(
            block["full_bust"] * 0.41 / 2.0,
            block["back_bust_half"],
        )
        self.assertAlmostEqual(
            block["drafting_high_bust"] * 0.43 / 2.0,
            block["back_high_bust_half"],
        )
        self.assertAlmostEqual(
            block["drafting_underbust"] * 0.47 / 2.0,
            block["back_underbust_half"],
        )

    def test_active_bodice_has_eight_panels_and_balanced_princess_seams(self) -> None:
        bodice = PatternaPrincessBodice(_body(), _design())
        pattern = bodice.assembly().pattern

        self.assertEqual(8, len(pattern["panels"]))
        self.assertEqual(18, len(pattern["stitches"]))
        self.assertGreater(
            pattern["panels"]["right_front_center"]["translation"][2],
            0.0,
        )
        self.assertLess(
            pattern["panels"]["right_back_center"]["translation"][2],
            0.0,
        )
        self.assertGreater(
            pattern["panels"]["right_back_side"]["rotation"][1],
            0.0,
        )
        self.assertLess(
            pattern["panels"]["left_back_side"]["rotation"][1],
            0.0,
        )
        for half in (bodice.right, bodice.left):
            self.assertGreater(
                half.front_center.bbox3D()[0][2],
                0.0,
                "Every center-front vertex must begin on anatomical front.",
            )
            self.assertGreater(
                half.front_side.bbox3D()[0][2],
                0.0,
                "Every side-front vertex must begin on anatomical front.",
            )
            for back_panel in (half.back_center, half.back_side):
                self.assertLess(
                    back_panel.bbox3D()[1][2],
                    0.0,
                    "Every back vertex must begin on anatomical back.",
                )
            self.assertGreater(half.front_center.norm()[2], 0.99)
            self.assertGreater(half.front_side.norm()[2], 0.20)
            self.assertLess(half.back_center.norm()[2], -0.99)
            self.assertLess(half.back_side.norm()[2], -0.40)
        self.assertLess(
            abs(
                bodice.right.front_side.interfaces["side"].edges.length()
                - bodice.right.back_side.interfaces["side"].edges.length()
            ),
            0.08,
            "The front and back side seams must be directly sewable without "
            "using solver strain as controlled ease.",
        )
        self.assertLess(
            abs(
                bodice.right.front_side.interfaces["armhole"].edges.length()
                + bodice.right.back_side.interfaces["armhole"].edges.length()
                - (
                    _body()["armscye_circumference"]
                    + bodice.block["armscye_mobility_ease_cm"]
                )
            ),
            0.001,
            "The finished armhole must equal the editable body armscye plus "
            "declared mobility ease after its shaping dart is closed.",
        )
        self.assertGreaterEqual(bodice.block["armhole_dart_intake_cm"], 0.0)
        self.assertEqual(0.0, bodice.block["back_shoulder_dart_intake_cm"])
        self.assertEqual(0.0, bodice.block["back_shoulder_dart_depth_cm"])
        self.assertEqual(
            "center-and-side-princess-seam",
            bodice.block["back_shaping_topology"],
        )
        self.assertLess(
            abs(
                bodice.right.back_center.interfaces["princess"].edges.length()
                - bodice.right.back_side.interfaces["princess"].edges.length()
            ),
            0.08,
            "Back shaping must be carried by a directly sewable princess seam.",
        )
        self.assertAlmostEqual(
            bodice.block["drafting_underbust"],
            bodice.block["drafted_underbust_circumference"],
            delta=0.01,
            msg="The editable underbust must drive an explicit pattern station.",
        )
        for name, armhole_edges in (
            ("front", bodice.right.front_side.interfaces["armhole"].edges),
            ("back", bodice.right.back_side.interfaces["armhole"].edges),
        ):
            for armhole in armhole_edges:
                straight_midpoint = 0.5 * (armhole.start[1] + armhole.end[1])
                self.assertLess(
                    armhole.midpoint()[1],
                    straight_midpoint,
                    f"{name.title()} armscye must scoop into the bodice instead of "
                    "forming a cap flap.",
                )

        princess_pairs = {
            frozenset(("left_front_center", "left_front_side")),
            frozenset(("right_front_center", "right_front_side")),
            frozenset(("left_back_center", "left_back_side")),
            frozenset(("right_back_center", "right_back_side")),
        }
        anatomically_reversed_pairs = {
            frozenset(("left_front_side", "left_back_side")),
            frozenset(("right_front_side", "right_back_side")),
        }
        princess_stitch_count = 0
        side_stitch_count = 0
        for stitch in pattern["stitches"]:
            pair = frozenset((stitch[0]["panel"], stitch[1]["panel"]))
            if pair in princess_pairs or pair in anatomically_reversed_pairs:
                if pair in princess_pairs:
                    self.assertEqual(
                        "right_wrong",
                        stitch[2],
                        "Princess boundaries must preserve their authored "
                        "waist-to-waist discretization.",
                    )
                    princess_stitch_count += 1
                else:
                    side_stitch_count += 1
                self.assertEqual(
                    3 if pair in princess_pairs else 2,
                    len(stitch),
                )
                edge_heights = []
                for reference in stitch[:2]:
                    panel = pattern["panels"][reference["panel"]]
                    edge = panel["edges"][reference["edge"]]
                    edge_heights.append(
                        [
                            panel["translation"][1]
                            + panel["vertices"][vertex_index][1]
                            for vertex_index in edge["endpoints"]
                        ]
                    )
                same_direction_error = sum(
                    abs(edge_heights[0][index] - edge_heights[1][index])
                    for index in range(2)
                )
                reversed_direction_error = sum(
                    abs(edge_heights[0][1 - index] - edge_heights[1][index])
                    for index in range(2)
                )
                self.assertLess(
                    min(same_direction_error, reversed_direction_error),
                    1.0,
                    "Sewn boundaries must map matching anatomical heights; "
                    "mirroring may reverse the serialized endpoint order.",
                )

        self.assertEqual(8, princess_stitch_count)
        self.assertEqual(6, side_stitch_count)

        shoulder_stitch_count = 0
        for stitch in pattern["stitches"]:
            first_panel = pattern["panels"][stitch[0]["panel"]]
            first_edge = first_panel["edges"][stitch[0]["edge"]]
            if first_edge.get("label") != "shoulder":
                continue
            second_panel = pattern["panels"][stitch[1]["panel"]]
            second_edge = second_panel["edges"][stitch[1]["edge"]]
            first_heights = [
                first_panel["translation"][1] + first_panel["vertices"][index][1]
                for index in first_edge["endpoints"]
            ]
            second_heights = [
                second_panel["translation"][1] + second_panel["vertices"][index][1]
                for index in second_edge["endpoints"]
            ]
            paired_errors = [
                abs(first_heights[index] - second_heights[1 - index])
                for index in range(2)
            ]
            self.assertLess(
                max(paired_errors),
                1.0,
                "Front and back shoulder landmarks must be registered before "
                "sewing instead of using cloth tension to correct body height.",
            )
            shoulder_stitch_count += 1

        self.assertEqual(4, shoulder_stitch_count)

    def test_manual_armscye_preserves_underarm_and_records_construction_ease(self) -> None:
        design = {
            "shirt": {
                "patterna_chest_ease": {"v": 3.0},
                "patterna_waist_ease": {"v": 2.0},
                "patterna_hip_ease": {"v": 4.0},
            }
        }
        bodice = PatternaPrincessBodice(
            _large_bust_body_with_station_profile(),
            design,
        )

        self.assertFalse(bodice.block["estimated_armscye_depth_adjusted"])
        self.assertAlmostEqual(
            bodice.block["requested_armscye_depth"],
            bodice.block["armscye_depth"],
        )
        self.assertEqual(
            bodice.block["requested_side_seam_height"],
            bodice.block["side_seam_height"],
        )
        self.assertAlmostEqual(
            45.5 + bodice.block["armscye_mobility_ease_cm"],
            bodice.block["drafted_armscye_circumference"],
            delta=0.001,
        )
        self.assertAlmostEqual(
            1.5,
            bodice.block["armscye_mobility_ease_cm"],
            delta=0.001,
        )
        self.assertAlmostEqual(
            bodice.block["armscye_mobility_ease_cm"],
            bodice.block["armscye_construction_ease_cm"],
            delta=0.001,
        )
        self.assertGreater(bodice.block["armhole_dart_intake_cm"], 0.0)
        self.assertEqual(
            "physical-armhole-dart",
            bodice.block["armhole_shaping_method"],
        )
        self.assertTrue(bodice.block["underarm_landmark_preserved"])
        self.assertEqual(bodice.block["minimum_anatomical_armhole_scoop"], 0.22)
        self.assertGreaterEqual(bodice.block["armhole_scoop_depth"], 0.22)
        self.assertAlmostEqual(
            bodice.block["drafting_upper_torso"],
            bodice.block["drafted_upper_torso_circumference"],
            delta=0.01,
        )
        self.assertAlmostEqual(
            bodice.block["drafting_underarm"],
            bodice.block["drafted_underarm_circumference"],
            delta=0.01,
        )

    def test_estimated_editable_armscye_is_shaped_instead_of_silently_enlarged(self) -> None:
        body = _anny_large_bust_body()
        bodice = PatternaPrincessBodice(
            body,
            {
                "shirt": {
                    "patterna_chest_ease": {"v": 3.0},
                    "patterna_waist_ease": {"v": 2.0},
                    "patterna_hip_ease": {"v": 4.0},
                }
            },
        )

        self.assertGreater(bodice.block["armhole_dart_intake_cm"], 0.0)
        self.assertEqual(
            "body-balanced-princess-transfer",
            bodice.block["armhole_shaping_method"],
        )
        self.assertTrue(bodice.block["armhole_dart_rotated_to_princess"])
        self.assertEqual(0.0, bodice.block["armhole_dart_depth_cm"])
        self.assertGreater(bodice.block["armhole_transfer_depth_cm"], 0.0)
        self.assertFalse(bodice.block["estimated_armscye_adjusted"])
        self.assertAlmostEqual(
            body["armscye_circumference"]
            + bodice.block["armscye_mobility_ease_cm"],
            bodice.block["drafted_armscye_circumference"],
            delta=0.001,
        )
        pattern = bodice.assembly().pattern
        self.assertFalse(
            any(
                edge.get("label") == "armhole_dart"
                for panel in pattern["panels"].values()
                for edge in panel["edges"]
            )
        )

    def test_manual_armscye_and_depth_remain_distinct_body_measurements(self) -> None:
        design = {
            "shirt": {
                "patterna_chest_ease": {"v": 3.0},
                "patterna_waist_ease": {"v": 2.0},
                "patterna_hip_ease": {"v": 4.0},
                "patterna_armscye_depth": {"v": 21.8},
            }
        }

        bodice = PatternaPrincessBodice(
            _large_bust_body_with_station_profile(),
            design,
        )

        self.assertEqual(21.8, bodice.block["armscye_depth"])
        self.assertEqual(
            "body-measurement-with-construction-ease",
            bodice.block["armscye_measurement_role"],
        )
        self.assertGreater(bodice.block["armscye_construction_ease_cm"], 0.0)

    def test_invalid_high_bust_is_rejected(self) -> None:
        design = _design()
        design["shirt"]["patterna_high_bust"] = {"v": 102.0}

        with self.assertRaisesRegex(ValueError, "cannot exceed"):
            compute_cup_aware_block_measurements(_body(), design)


if __name__ == "__main__":
    unittest.main()
