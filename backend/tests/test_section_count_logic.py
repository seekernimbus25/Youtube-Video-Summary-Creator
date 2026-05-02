from services.claude_service import (
    _build_equal_section_windows,
    _build_sections_from_candidates,
    _normalize_chapter_sections,
    _target_section_count_for_duration,
    _target_section_range_for_duration,
    _target_section_span_seconds,
)


def test_target_section_count_for_six_minutes():
    assert _target_section_count_for_duration("6:00") == 2
    assert _target_section_range_for_duration("6:00") == "2"


def test_target_section_count_for_sixty_two_minutes():
    assert _target_section_count_for_duration("62:00") == 13
    assert _target_section_range_for_duration("62:00") == "13"


def test_target_section_span_seconds_for_sixty_two_minutes():
    assert _target_section_span_seconds("62:00") == 287


def test_equal_section_windows_cover_full_duration_for_six_minutes():
    assert _build_equal_section_windows("6:00") == [(0, 180), (180, 360)]


def test_equal_section_windows_cover_full_duration_for_sixty_two_minutes():
    windows = _build_equal_section_windows("62:00")

    assert len(windows) == 13
    assert windows[0] == (0, 286)
    assert windows[-1] == (3433, 3720)
    assert windows[0][0] == 0
    assert windows[-1][1] == 3720


def test_build_sections_from_candidates_preserves_real_candidate_timestamps():
    candidates = [
        {"title": "A", "timestamp": "00:00", "timestamp_seconds": 0, "description": "a", "steps": [], "sub_points": [], "trade_offs": [], "notable_detail": ""},
        {"title": "B", "timestamp": "04:27", "timestamp_seconds": 267, "description": "b", "steps": [], "sub_points": [], "trade_offs": [], "notable_detail": ""},
        {"title": "C", "timestamp": "08:54", "timestamp_seconds": 534, "description": "c", "steps": [], "sub_points": [], "trade_offs": [], "notable_detail": ""},
        {"title": "D", "timestamp": "13:21", "timestamp_seconds": 801, "description": "d", "steps": [], "sub_points": [], "trade_offs": [], "notable_detail": ""},
        {"title": "E", "timestamp": "17:49", "timestamp_seconds": 1069, "description": "e", "steps": [], "sub_points": [], "trade_offs": [], "notable_detail": ""},
        {"title": "F", "timestamp": "22:16", "timestamp_seconds": 1336, "description": "f", "steps": [], "sub_points": [], "trade_offs": [], "notable_detail": ""},
        {"title": "G", "timestamp": "26:43", "timestamp_seconds": 1603, "description": "g", "steps": [], "sub_points": [], "trade_offs": [], "notable_detail": ""},
        {"title": "H", "timestamp": "31:31", "timestamp_seconds": 1891, "description": "h", "steps": [], "sub_points": [], "trade_offs": [], "notable_detail": ""},
        {"title": "I", "timestamp": "35:55", "timestamp_seconds": 2155, "description": "i", "steps": [], "sub_points": [], "trade_offs": [], "notable_detail": ""},
        {"title": "J", "timestamp": "40:19", "timestamp_seconds": 2419, "description": "j", "steps": [], "sub_points": [], "trade_offs": [], "notable_detail": ""},
        {"title": "K", "timestamp": "44:43", "timestamp_seconds": 2683, "description": "k", "steps": [], "sub_points": [], "trade_offs": [], "notable_detail": ""},
        {"title": "L", "timestamp": "49:08", "timestamp_seconds": 2948, "description": "l", "steps": [], "sub_points": [], "trade_offs": [], "notable_detail": ""},
        {"title": "M", "timestamp": "53:32", "timestamp_seconds": 3212, "description": "m", "steps": [], "sub_points": [], "trade_offs": [], "notable_detail": ""},
        {"title": "N", "timestamp": "57:56", "timestamp_seconds": 3476, "description": "n", "steps": [], "sub_points": [], "trade_offs": [], "notable_detail": ""},
    ]

    sections = _build_sections_from_candidates(candidates, "62:00")

    assert len(sections) == 13
    assert [section["timestamp"] for section in sections] == [
        "00:00", "04:27", "08:54", "13:21", "17:49", "22:16", "26:43",
        "31:31", "35:55", "40:19", "44:43", "49:08", "57:56",
    ]


def test_normalize_chapter_sections_preserves_titles_and_boundaries():
    chapters = [
        {"title": "Intro", "start_time": 0, "end_time": 120},
        {"title": "Core Idea", "start_time": 120, "end_time": 360},
    ]
    normalized = _normalize_chapter_sections(chapters, "6:00")

    assert normalized == [
        {"title": "Intro", "start_seconds": 0, "end_seconds": 120, "timestamp": "0:00"},
        {"title": "Core Idea", "start_seconds": 120, "end_seconds": 360, "timestamp": "2:00"},
    ]


def test_build_sections_from_candidates_uses_chapter_titles_when_available():
    chapters = [
        {"title": "Opening Setup", "start_time": 0, "end_time": 180},
        {"title": "Main Walkthrough", "start_time": 180, "end_time": 360},
    ]
    candidates = [
        {"title": "Loose Intro", "timestamp": "00:20", "timestamp_seconds": 20, "description": "Intro detail one.", "steps": [], "sub_points": ["point a"], "trade_offs": [], "notable_detail": "detail a"},
        {"title": "Loose Intro 2", "timestamp": "01:50", "timestamp_seconds": 110, "description": "Intro detail two.", "steps": [], "sub_points": ["point b"], "trade_offs": [], "notable_detail": ""},
        {"title": "Loose Main", "timestamp": "03:20", "timestamp_seconds": 200, "description": "Main detail one.", "steps": ["step 1"], "sub_points": ["point c"], "trade_offs": ["trade c"], "notable_detail": "detail c"},
        {"title": "Loose Main 2", "timestamp": "05:10", "timestamp_seconds": 310, "description": "Main detail two.", "steps": ["step 2"], "sub_points": ["point d"], "trade_offs": [], "notable_detail": ""},
    ]

    sections = _build_sections_from_candidates(candidates, "6:00", chapters)

    assert [section["title"] for section in sections] == ["Opening Setup", "Main Walkthrough"]
    assert [section["timestamp"] for section in sections] == ["0:00", "3:00"]
    assert "Intro detail one" in sections[0]["description"]
    assert "Intro detail two" in sections[0]["description"]
    assert sections[1]["steps"] == ["step 1", "step 2"]


def test_build_sections_from_candidates_merges_chunk_support_into_sections():
    candidates = [
        {"title": "Anchor One", "timestamp": "00:20", "timestamp_seconds": 20, "description": "Candidate detail one.", "steps": [], "sub_points": ["point a"], "trade_offs": [], "notable_detail": ""},
        {"title": "Anchor Two", "timestamp": "03:20", "timestamp_seconds": 200, "description": "Candidate detail two.", "steps": [], "sub_points": ["point b"], "trade_offs": [], "notable_detail": ""},
    ]
    chunk_supports = [
        {
            "chunk_index": 0,
            "start_seconds": 0,
            "end_seconds": 240,
            "summary_paragraph": "Chunk summary adds context and framing.",
            "insight_seeds": ["Insight seed about why the section matters."],
            "recommendation_seeds": ["Recommendation seed tied to this window."],
            "concept_summaries": ["Concept X: explanation from chunk support."],
        }
    ]

    sections = _build_sections_from_candidates(candidates, "4:00", None, chunk_supports)

    assert len(sections) == 1
    assert "Candidate detail one" in sections[0]["description"]
    assert "Chunk summary adds context and framing" in sections[0]["description"]
    assert "Concept X: explanation from chunk support." in sections[0]["sub_points"]
    assert "Insight seed about why the section matters." in sections[0]["sub_points"]
    assert "Recommendation seed tied to this window." in sections[0]["sub_points"]
