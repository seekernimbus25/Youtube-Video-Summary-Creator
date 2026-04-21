import json
from pathlib import Path


def test_compute_screenshot_metrics_from_fixture_cases():
    from services.screenshot_benchmark import compute_screenshot_metrics

    fixture_path = Path(__file__).parent / "fixtures" / "screenshot_benchmark_cases.json"
    cases = json.loads(fixture_path.read_text(encoding="utf-8"))
    predictions = [
        {"request_id": "sec-0", "section_index": 0, "selected_seconds": 11, "quality_score": 14.2, "latency_ms": 52000},
        {"request_id": "sec-1", "section_index": 1, "selected_seconds": 77, "quality_score": 13.9, "latency_ms": 61000},
        {"request_id": "sec-2", "section_index": 2, "selected_seconds": 182, "quality_score": 12.7, "latency_ms": 70000},
    ]

    metrics = compute_screenshot_metrics(cases, predictions)
    assert metrics["section_match_precision"] == 1.0
    assert metrics["median_timing_error_seconds"] <= 2.0
    assert metrics["frame_quality_pass_rate"] == 1.0
    assert metrics["p95_latency_ms"] <= 90000
