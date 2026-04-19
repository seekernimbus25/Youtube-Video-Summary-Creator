def test_get_candidate_times_returns_three_times():
    from services.playwright_service import _get_candidate_times

    request = {
        "preferred_seconds": 60,
        "window_start": 50,
        "window_end": 120,
    }
    times = _get_candidate_times(request)
    assert len(times) == 3
    assert all(50 <= time <= 120 for time in times)
    assert 60 in times or any(abs(time - 60) <= 1 for time in times)


def test_get_candidate_times_clamped_to_window():
    from services.playwright_service import _get_candidate_times

    request = {
        "preferred_seconds": 5,
        "window_start": 10,
        "window_end": 30,
    }
    times = _get_candidate_times(request)
    assert all(10 <= time <= 30 for time in times)


def test_playwright_available_flag_is_bool():
    from services.playwright_service import PLAYWRIGHT_AVAILABLE

    assert isinstance(PLAYWRIGHT_AVAILABLE, bool)
