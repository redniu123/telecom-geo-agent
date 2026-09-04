"""Deterministic simplified BOM calculation for a validated route."""

from __future__ import annotations

import math

from .models import BOMResult, RouteResult


SLACK_RATIO = 0.10


class BOMCalculationError(ValueError):
    """Raised when a route cannot be reconciled into a truthful BOM."""


def calculate_bom(route: RouteResult) -> BOMResult:
    """Calculate lengths from route segments and reject inconsistencies."""

    if route.get("success") is not True:
        raise BOMCalculationError("cannot calculate BOM from an unsuccessful route")
    segments = route.get("segments", [])
    if not segments:
        raise BOMCalculationError("cannot calculate BOM from an empty route")
    segment_edge_ids = [segment.get("edge_id") for segment in segments]
    if route.get("edge_ids") != segment_edge_ids:
        raise BOMCalculationError("route edge_ids must exactly match segment edge_id order")

    existing_length = 0.0
    new_build_length = 0.0
    for segment in segments:
        length = float(segment["length_m"])
        if not math.isfinite(length) or length <= 0:
            raise BOMCalculationError(
                f"segment {segment['edge_id']!r} length must be a positive finite number"
            )
        if segment["asset_type"] == "existing_duct":
            existing_length += length
        elif segment["asset_type"] == "new_build":
            new_build_length += length
        else:
            raise BOMCalculationError(
                f"segment {segment['edge_id']!r} has unsupported asset_type "
                f"{segment['asset_type']!r}"
            )

    segment_total = existing_length + new_build_length
    declared_total = float(route.get("total_length_m", segment_total))
    if abs(segment_total - declared_total) > 0.01:
        raise BOMCalculationError(
            f"route total_length_m {declared_total:.2f} does not match segment sum {segment_total:.2f}"
        )

    total = round(segment_total, 2)
    existing = round(existing_length, 2)
    new_build = round(new_build_length, 2)
    if abs((existing + new_build) - total) > 0.01:
        raise BOMCalculationError("rounded asset length subtotals do not reconcile to total length")
    return {
        "total_length_m": total,
        "existing_duct_length_m": existing,
        "new_build_length_m": new_build,
        "recommended_cable_length_m": round(total * (1.0 + SLACK_RATIO), 2),
        "slack_ratio": SLACK_RATIO,
        "used_edge_ids": [segment["edge_id"] for segment in segments],
    }
