"""Provenance-aware acceptance policy for fitted MPFB ruler measurements."""

from __future__ import annotations

from typing import Any, Iterable, Mapping


def _casefold_mapping(values: Mapping[str, Any]) -> dict[str, Any]:
    return {
        key.casefold(): value
        for key, value in values.items()
        if isinstance(key, str)
    }


def resolve_source_keys(
    source_keys: Iterable[str],
    measurement_sources: Mapping[str, list[str] | tuple[str, ...]],
) -> list[str]:
    """Resolve internal body aliases back to editable user measurement keys."""

    sources_by_key = _casefold_mapping(measurement_sources)
    resolved: list[str] = []
    for source_key in source_keys:
        mapped = sources_by_key.get(source_key.casefold())
        candidates = mapped if isinstance(mapped, (list, tuple)) and mapped else [source_key]
        for candidate in candidates:
            if isinstance(candidate, str) and candidate not in resolved:
                resolved.append(candidate)
    return resolved


def _source_evidence(
    source_keys: Iterable[str],
    measurement_sources: Mapping[str, list[str] | tuple[str, ...]],
    measurement_origins: Mapping[str, str],
) -> dict[str, Any]:
    resolved_keys = resolve_source_keys(source_keys, measurement_sources)
    origins_by_key = _casefold_mapping(measurement_origins)
    origins = {
        key: origins_by_key.get(key.casefold())
        for key in resolved_keys
    }
    all_estimated = bool(origins) and all(
        isinstance(origin, str) and origin.strip().casefold() == "estimated"
        for origin in origins.values()
    )
    return {
        "source_keys": resolved_keys,
        "source_origins": origins,
        "source_policy": "estimated" if all_estimated else "hard",
    }


def evaluate_fit_acceptance(
    *,
    requested_measurements: Mapping[str, float],
    final_measurements: Mapping[str, float],
    fit_results: Mapping[str, Mapping[str, Any]],
    tolerance_cm: float,
    target_source_keys: Mapping[str, Iterable[str]],
    measurement_sources: Mapping[str, list[str] | tuple[str, ...]],
    measurement_origins: Mapping[str, str],
    height_result: Mapping[str, float] | None,
) -> dict[str, Any]:
    """Accept accurate rulers and disclose unreachable estimated rulers.

    Missing provenance remains hard for backward compatibility. An estimated
    ruler can be non-blocking only when the MPFB direct target explicitly says
    the requested value is outside its reachable morph range.
    """

    if tolerance_cm <= 0:
        raise ValueError("Fit tolerance must be positive.")

    target_evidence: dict[str, Any] = {}
    blocking_failures: list[str] = []
    accepted_estimated_unreachable: list[str] = []

    for name, desired in requested_measurements.items():
        if name not in final_measurements:
            raise KeyError(f"Missing final MPFB ruler measurement: {name}")
        measured = float(final_measurements[name])
        residual = measured - float(desired)
        within_tolerance = abs(residual) <= tolerance_cm
        fit_result = fit_results.get(name, {})
        reachable = fit_result.get("reachable") is not False
        evidence = _source_evidence(
            target_source_keys.get(name, (name,)),
            measurement_sources,
            measurement_origins,
        )

        if within_tolerance:
            disposition = "accepted-within-tolerance"
        elif evidence["source_policy"] == "estimated" and not reachable:
            disposition = "accepted-estimated-unreachable"
            accepted_estimated_unreachable.append(name)
        else:
            disposition = "rejected"
            blocking_failures.append(name)

        target_evidence[name] = {
            **evidence,
            "target_cm": float(desired),
            "measured_cm": measured,
            "residual_cm": residual,
            "reachable": reachable,
            "within_tolerance": within_tolerance,
            "disposition": disposition,
        }

    height_evidence = None
    if height_result is not None:
        height_source = _source_evidence(
            ("height",), measurement_sources, measurement_origins
        )
        height_residual = (
            float(height_result["measured_cm"])
            - float(height_result["target_cm"])
        )
        height_within_tolerance = abs(height_residual) <= tolerance_cm
        height_evidence = {
            **height_source,
            "target_cm": float(height_result["target_cm"]),
            "measured_cm": float(height_result["measured_cm"]),
            "residual_cm": height_residual,
            "within_tolerance": height_within_tolerance,
            "disposition": (
                "accepted-within-tolerance"
                if height_within_tolerance
                else "rejected"
            ),
        }
        if not height_within_tolerance:
            blocking_failures.append("height")

    return {
        "policy": "patterna.provenance-aware-avatar-fit/1.0",
        "accepted": not blocking_failures,
        "tolerance_cm": tolerance_cm,
        "height": height_evidence,
        "targets": target_evidence,
        "blocking_failures": blocking_failures,
        "accepted_estimated_unreachable": accepted_estimated_unreachable,
    }
