from __future__ import annotations

from typing import Dict, List


def compute_screenshot_metrics(cases: List[dict], predictions: List[dict]) -> Dict[str, float]:
    """
    Compute simple benchmark metrics for screenshot selection quality.
    cases: [{request_id, expected_section_index, expected_seconds, max_timing_error_seconds}]
    predictions: [{request_id, section_index, selected_seconds, quality_score, latency_ms}]
    """
    by_id = {str(item.get("request_id", "")): item for item in predictions}
    total = len(cases)
    if total == 0:
        return {
            "section_match_precision": 0.0,
            "median_timing_error_seconds": 0.0,
            "frame_quality_pass_rate": 0.0,
            "p95_latency_ms": 0.0,
        }

    section_matches = 0
    timing_errors = []
    quality_passes = 0
    latencies = []

    for case in cases:
        request_id = str(case.get("request_id", ""))
        prediction = by_id.get(request_id)
        if not prediction:
            continue

        expected_section = int(case.get("expected_section_index", -1))
        expected_seconds = int(case.get("expected_seconds", 0))
        max_error = int(case.get("max_timing_error_seconds", 3))

        section_index = int(prediction.get("section_index", -1))
        selected_seconds = int(prediction.get("selected_seconds", prediction.get("seconds", 0)) or 0)
        quality_score = float(prediction.get("quality_score", 0.0) or 0.0)
        latency_ms = float(prediction.get("latency_ms", 0.0) or 0.0)

        if section_index == expected_section:
            section_matches += 1
        error = abs(selected_seconds - expected_seconds)
        timing_errors.append(float(error))
        if error <= max_error and quality_score > 0.0:
            quality_passes += 1
        if latency_ms > 0:
            latencies.append(latency_ms)

    timing_errors.sort()
    latencies.sort()

    def _median(values: List[float]) -> float:
        if not values:
            return 0.0
        mid = len(values) // 2
        if len(values) % 2:
            return float(values[mid])
        return float((values[mid - 1] + values[mid]) / 2.0)

    def _p95(values: List[float]) -> float:
        if not values:
            return 0.0
        index = int(round(0.95 * (len(values) - 1)))
        return float(values[index])

    return {
        "section_match_precision": section_matches / total,
        "median_timing_error_seconds": _median(timing_errors),
        "frame_quality_pass_rate": quality_passes / total,
        "p95_latency_ms": _p95(latencies),
    }
