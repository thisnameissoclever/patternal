import copy
import math
from typing import Any


FRONT_PANEL_NAMES = ("right_ftorso", "left_ftorso")
BACK_PANEL_NAMES = ("right_btorso", "left_btorso")


def _assert_equal_transform(
    first: dict[str, Any],
    second: dict[str, Any],
    first_name: str,
    second_name: str,
) -> None:
    for key in ("translation", "rotation"):
        first_values = first.get(key)
        second_values = second.get(key)
        if first_values != second_values:
            raise ValueError(
                f"Cannot merge {first_name} and {second_name}: {key} differs."
            )


def _assert_same_vertex(
    first: list[float],
    second: list[float],
    description: str,
    tolerance: float = 1.0e-7,
) -> None:
    if len(first) != 2 or len(second) != 2:
        raise ValueError(f"{description} must compare two 2D vertices.")
    if math.dist(first, second) > tolerance:
        raise ValueError(f"{description} does not meet at the center line.")


def _copy_edge(edge: dict[str, Any], start: int, end: int) -> dict[str, Any]:
    copied = copy.deepcopy(edge)
    copied["endpoints"] = [start, end]
    return copied


def _minor_arc_delta(
    start: list[float], end: list[float], center: tuple[float, float]
) -> float:
    start_angle = math.atan2(start[1] - center[1], start[0] - center[0])
    end_angle = math.atan2(end[1] - center[1], end[0] - center[0])
    delta = end_angle - start_angle
    while delta <= -math.pi:
        delta += math.tau
    while delta > math.pi:
        delta -= math.tau
    return delta


def _relative_control(
    start: list[float], end: list[float], control: tuple[float, float]
) -> list[float]:
    dx = end[0] - start[0]
    dy = end[1] - start[1]
    length_squared = dx * dx + dy * dy
    point_x = control[0] - start[0]
    point_y = control[1] - start[1]
    return [
        (dx * point_x + dy * point_y) / length_squared,
        (dx * point_y - dy * point_x) / length_squared,
    ]


def _convert_circle_to_cubic(
    edge: dict[str, Any],
    start: list[float],
    end: list[float],
    description: str,
) -> None:
    curvature = edge.get("curvature")
    if not isinstance(curvature, dict) or curvature.get("type") != "circle":
        raise ValueError(f"{description} must remain a circular neckline edge.")
    params = curvature.get("params")
    if not isinstance(params, list) or len(params) != 3:
        raise ValueError(f"{description} has invalid circular-arc parameters.")
    radius = float(params[0])
    large_arc = bool(params[1])
    sweep_positive = bool(params[2])
    if large_arc:
        raise ValueError(f"{description} cannot convert a large circular arc.")

    dx = end[0] - start[0]
    dy = end[1] - start[1]
    chord = math.hypot(dx, dy)
    if radius <= 0 or chord <= 0 or chord > 2 * radius + 1.0e-7:
        raise ValueError(f"{description} has an impossible circular radius.")
    center_offset = math.sqrt(max(0.0, radius * radius - (chord * 0.5) ** 2))
    midpoint = ((start[0] + end[0]) * 0.5, (start[1] + end[1]) * 0.5)
    perpendicular = (-dy / chord, dx / chord)
    centers = (
        (
            midpoint[0] + perpendicular[0] * center_offset,
            midpoint[1] + perpendicular[1] * center_offset,
        ),
        (
            midpoint[0] - perpendicular[0] * center_offset,
            midpoint[1] - perpendicular[1] * center_offset,
        ),
    )
    deltas = tuple(_minor_arc_delta(start, end, center) for center in centers)
    selected = next(
        (
            (center, delta)
            for center, delta in zip(centers, deltas, strict=True)
            if (sweep_positive and delta > 0) or (not sweep_positive and delta < 0)
        ),
        (centers[1], deltas[1]),
    )
    center, delta = selected
    start_angle = math.atan2(start[1] - center[1], start[0] - center[0])
    end_angle = start_angle + delta
    control_scale = 4.0 / 3.0 * math.tan(delta / 4.0) * radius
    control1 = (
        start[0] + control_scale * -math.sin(start_angle),
        start[1] + control_scale * math.cos(start_angle),
    )
    control2 = (
        end[0] - control_scale * -math.sin(end_angle),
        end[1] - control_scale * math.cos(end_angle),
    )
    edge["curvature"] = {
        "type": "cubic",
        "params": [
            _relative_control(start, end, control1),
            _relative_control(start, end, control2),
        ],
    }


def _merge_front_panels(
    right: dict[str, Any], left: dict[str, Any]
) -> tuple[dict[str, Any], dict[tuple[str, int], tuple[str, int]]]:
    _assert_equal_transform(right, left, FRONT_PANEL_NAMES[0], FRONT_PANEL_NAMES[1])
    right_vertices = right["vertices"]
    left_vertices = left["vertices"]
    right_edges = right["edges"]
    left_edges = left["edges"]
    if len(right_vertices) != 9 or len(left_vertices) != 9:
        raise ValueError("The full-front merge requires two nine-vertex torso halves.")
    if len(right_edges) != 9 or len(left_edges) != 9:
        raise ValueError("The full-front merge requires two nine-edge torso halves.")

    _assert_same_vertex(right_vertices[0], left_vertices[0], "Front hem center")
    _assert_same_vertex(right_vertices[1], left_vertices[8], "Front neck center")

    vertices = copy.deepcopy(right_vertices[1:] + left_vertices[1:8])
    source_edges = right_edges[1:8] + [right_edges[8]] + left_edges[1:8]
    edges = [
        _copy_edge(edge, index, (index + 1) % len(vertices))
        for index, edge in enumerate(source_edges)
    ]
    _convert_circle_to_cubic(
        edges[0], vertices[0], vertices[1], "Right front neckline"
    )
    _convert_circle_to_cubic(
        edges[-1], vertices[-1], vertices[0], "Left front neckline"
    )
    panel = copy.deepcopy(right)
    panel["vertices"] = vertices
    panel["edges"] = edges
    panel["label"] = "body"

    remap: dict[tuple[str, int], tuple[str, int]] = {}
    for edge_index in range(1, 8):
        remap[(FRONT_PANEL_NAMES[0], edge_index)] = (
            "front_torso",
            edge_index - 1,
        )
    for edge_index in range(1, 8):
        remap[(FRONT_PANEL_NAMES[1], edge_index)] = (
            "front_torso",
            edge_index + 7,
        )
    return panel, remap


def _merge_back_panels(
    right: dict[str, Any], left: dict[str, Any]
) -> tuple[dict[str, Any], dict[tuple[str, int], tuple[str, int]]]:
    _assert_equal_transform(right, left, BACK_PANEL_NAMES[0], BACK_PANEL_NAMES[1])
    right_vertices = right["vertices"]
    left_vertices = left["vertices"]
    right_edges = right["edges"]
    left_edges = left["edges"]
    if len(right_vertices) != 8 or len(left_vertices) != 8:
        raise ValueError("The full-back merge requires two eight-vertex torso halves.")
    if len(right_edges) != 8 or len(left_edges) != 8:
        raise ValueError("The full-back merge requires two eight-edge torso halves.")

    _assert_same_vertex(right_vertices[0], left_vertices[0], "Back hem center")
    _assert_same_vertex(right_vertices[7], left_vertices[1], "Back neck center")

    vertices = copy.deepcopy(right_vertices[1:] + left_vertices[2:])
    source_edges = right_edges[1:7] + left_edges[1:7] + [left_edges[7]]
    edges = [
        _copy_edge(edge, index, (index + 1) % len(vertices))
        for index, edge in enumerate(source_edges)
    ]
    panel = copy.deepcopy(right)
    panel["vertices"] = vertices
    panel["edges"] = edges
    panel["label"] = "body"

    remap: dict[tuple[str, int], tuple[str, int]] = {}
    for edge_index in range(1, 7):
        remap[(BACK_PANEL_NAMES[0], edge_index)] = (
            "back_torso",
            edge_index - 1,
        )
    for edge_index in range(1, 7):
        remap[(BACK_PANEL_NAMES[1], edge_index)] = (
            "back_torso",
            edge_index + 5,
        )
    return panel, remap


def _endpoint_key(endpoint: dict[str, Any]) -> tuple[str, int]:
    return str(endpoint["panel"]), int(endpoint["edge"])


def _is_center_seam(stitch: list[dict[str, Any]]) -> bool:
    endpoints = {_endpoint_key(endpoint) for endpoint in stitch}
    return endpoints in (
        {("right_ftorso", 0), ("left_ftorso", 8)},
        {("right_btorso", 7), ("left_btorso", 0)},
    )


def merge_mirrored_torso_halves(specification: dict[str, Any]) -> dict[str, Any]:
    """Return a GarmentCode specification with uninterrupted front and back bodies."""
    result = copy.deepcopy(specification)
    pattern = result.get("pattern")
    if not isinstance(pattern, dict):
        raise ValueError("GarmentCode specification is missing its pattern object.")
    panels = pattern.get("panels")
    stitches = pattern.get("stitches")
    if not isinstance(panels, dict) or not isinstance(stitches, list):
        raise ValueError("GarmentCode pattern must contain panels and stitches.")
    required_names = {*FRONT_PANEL_NAMES, *BACK_PANEL_NAMES}
    if not required_names.issubset(panels):
        missing = ", ".join(sorted(required_names.difference(panels)))
        raise ValueError(f"Cannot merge mirrored torso panels. Missing: {missing}")

    front_panel, front_remap = _merge_front_panels(
        panels[FRONT_PANEL_NAMES[0]], panels[FRONT_PANEL_NAMES[1]]
    )
    back_panel, back_remap = _merge_back_panels(
        panels[BACK_PANEL_NAMES[0]], panels[BACK_PANEL_NAMES[1]]
    )
    edge_remap = {**front_remap, **back_remap}

    center_seam_count = sum(_is_center_seam(stitch) for stitch in stitches)
    if center_seam_count != 2:
        raise ValueError(
            "Expected exactly two mirrored torso center seams before full-panel merge."
        )

    remapped_stitches: list[list[dict[str, Any]]] = []
    for stitch in stitches:
        if _is_center_seam(stitch):
            continue
        remapped_stitch = copy.deepcopy(stitch)
        for endpoint in remapped_stitch:
            key = _endpoint_key(endpoint)
            if key[0] not in required_names:
                continue
            if key not in edge_remap:
                raise ValueError(
                    f"Stitch references removed torso center edge {key[0]}:{key[1]}."
                )
            endpoint["panel"], endpoint["edge"] = edge_remap[key]
        remapped_stitches.append(remapped_stitch)

    panel_items = list(panels.items())
    rebuilt_panels: dict[str, Any] = {}
    for name, panel in panel_items:
        if name == FRONT_PANEL_NAMES[0]:
            rebuilt_panels["front_torso"] = front_panel
        elif name == BACK_PANEL_NAMES[0]:
            rebuilt_panels["back_torso"] = back_panel
        elif name not in required_names:
            rebuilt_panels[name] = panel

    pattern["panels"] = rebuilt_panels
    pattern["stitches"] = remapped_stitches
    result.setdefault("patterna", {})["torso_construction"] = (
        "uninterrupted-full-front-and-back"
    )
    return result
