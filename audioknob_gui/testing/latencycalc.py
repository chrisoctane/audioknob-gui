from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class LatencyParams:
    sample_rate_hz: float
    frames_per_period: int
    periods: int


@dataclass(frozen=True)
class LatencyResult:
    one_way_ms: float
    round_trip_ms: float


def theoretical_latency(params: LatencyParams) -> LatencyResult:
    # Buffer latency ~= (frames_per_period * periods) / sample_rate
    one_way_s = (params.frames_per_period * params.periods) / float(params.sample_rate_hz)
    one_way_ms = one_way_s * 1000.0
    return LatencyResult(one_way_ms=one_way_ms, round_trip_ms=2.0 * one_way_ms)
