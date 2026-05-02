import inspect

from services.claude_service import (
    CHUNK_MAP_SYSTEM,
    _strip_inline_timestamps,
    _backfill_summary_depth,
    _build_equal_windows_for_span,
    _concept_explanation_budget,
    _extract_key_sections_payload,
    _extract_chunk_bounds,
    _find_split_point,
    _get_chunk_map_system,
    _deep_dive_min_word_count,
    _insight_word_budget,
    _key_sections_polish_prompt,
    _map_chunk_user_prompt,
    _mindmap_from_sections_user_prompt,
    _recommendation_word_budget,
    _reduce_user_prompt,
    _section_description_budget,
    _section_subpoint_budget,
    _target_section_count_for_span,
    _summary_from_sections_user_prompt,
    _sections_only_user_prompt,
    detect_video_type,
    generate_summary_and_mindmap,
    generate_summary_and_mindmap_single_pass,
    split_transcript_for_map,
)


def test_type_from_title_tutorial():
    assert detect_video_type("How to build a REST API", "") == "tutorial"


def test_type_from_title_lecture():
    assert detect_video_type("Introduction to Machine Learning 101", "") == "lecture"


def test_type_from_title_opinion():
    assert detect_video_type("My thoughts on Python vs Go", "") == "opinion"


def test_type_from_title_general_falls_back():
    assert detect_video_type("The Future of Programming", "") == "general"


def test_type_from_transcript_tutorial():
    transcript = "Let me show you. pip install fastapi and then import fastapi"
    assert detect_video_type("Some Video", transcript) == "tutorial"


def test_type_from_transcript_lecture():
    transcript = "In this lecture we will cover the basics. As we can see from the diagram"
    assert detect_video_type("Some Video", transcript) == "lecture"


def test_type_from_transcript_opinion():
    transcript = (
        "I think this is wrong. Personally I believe the framework is bad. "
        "In my opinion we should move on. I feel like the community agrees."
    )
    assert detect_video_type("Some Video", transcript) == "opinion"


def test_type_from_transcript_general():
    transcript = "Welcome to this video. Today we are going to look at something interesting."
    assert detect_video_type("Some Video", transcript) == "general"


def test_title_takes_precedence_over_transcript():
    transcript = "I think this tool is great. Personally I love it. In my opinion best tool ever."
    assert detect_video_type("Complete Tutorial: Building with FastAPI", transcript) == "tutorial"


def test_find_split_point_prefers_timestamp_marker():
    transcript = "A" * 50 + "[1:23] some content here more words"
    assert _find_split_point(transcript, 55) == 50


def test_find_split_point_falls_back_to_punctuation():
    transcript = "Hello world. This is a sentence. " + "X" * 50
    result = _find_split_point(transcript, 40)
    assert transcript[result - 2 : result] in (". ", "? ", "! ") or result == 40


def test_find_split_point_exact_fallback():
    transcript = "abcdefghij" * 20
    assert _find_split_point(transcript, 50) == 50


def test_find_split_point_never_returns_before_min_start():
    transcript = "Hello world. " + "X" * 100
    result = _find_split_point(transcript, 60, min_start=50)
    assert result >= 50


def test_split_transcript_for_map_no_infinite_loop():
    transcript = "abcde" * 20000
    parts = split_transcript_for_map(transcript)
    assert len(parts) >= 1
    assert all(len(part) > 0 for part in parts)


def test_split_transcript_for_map_splits_at_markers():
    chunk = "[0:00] " + "word " * 9000
    transcript = chunk + "[45:00] " + "word " * 9000
    parts = split_transcript_for_map(transcript)
    assert len(parts) >= 2
    marker_index = next(i for i, part in enumerate(parts) if "[45:00]" in part)
    assert marker_index >= 1


def test_split_transcript_for_map_prefers_chapter_boundaries():
    transcript = (
        "[0:00] intro words "
        + ("a " * 12000)
        + "[10:00] middle words "
        + ("b " * 12000)
        + "[20:00] ending words "
        + ("c " * 12000)
    )
    chapters = [
        {"title": "Intro", "start_time": 0, "end_time": 600},
        {"title": "Middle", "start_time": 600, "end_time": 1200},
        {"title": "End", "start_time": 1200, "end_time": 1800},
    ]

    parts = split_transcript_for_map(transcript, chapters, "30:00")

    assert len(parts) == 3
    assert "[10:00]" in parts[1]
    assert "[20:00]" in parts[2]


def test_get_chunk_map_system_tutorial_differs_from_general():
    assert _get_chunk_map_system("tutorial") != CHUNK_MAP_SYSTEM


def test_get_chunk_map_system_lecture_differs_from_general():
    assert _get_chunk_map_system("lecture") != CHUNK_MAP_SYSTEM


def test_get_chunk_map_system_opinion_differs_from_general():
    assert _get_chunk_map_system("opinion") != CHUNK_MAP_SYSTEM


def test_get_chunk_map_system_general_returns_existing():
    assert _get_chunk_map_system("general") == CHUNK_MAP_SYSTEM


def test_get_chunk_map_system_unknown_returns_general():
    assert _get_chunk_map_system("unknown") == CHUNK_MAP_SYSTEM


def test_all_map_systems_contain_insight_rule():
    for video_type in ("tutorial", "lecture", "opinion", "general"):
        assert "[specific claim]" in _get_chunk_map_system(video_type)


def test_strip_inline_timestamps_removes_time_references():
    text = "[04:27] Main point here. Evidence: 05:10. Timestamp: 06:20."
    assert _strip_inline_timestamps(text) == "Main point here"


def test_extract_chunk_bounds_parses_first_and_last_timestamp():
    chunk = "[2:30] intro content here [5:00] more content [8:15] final bit"
    start, end = _extract_chunk_bounds(chunk)
    assert start == 150
    assert end == 495


def test_extract_chunk_bounds_no_timestamps_returns_zeros():
    assert _extract_chunk_bounds("No timestamps in this chunk at all") == (0, 0)


def test_map_chunk_prompt_uses_chunk_specific_instructions():
    prompt = _map_chunk_user_prompt(
        title="Test",
        channel="Ch",
        duration="1:00:00",
        chunk_index=0,
        num_chunks=2,
        chunk_text="some transcript",
        chunk_start_seconds=0,
        chunk_end_seconds=1800,
    )
    assert "This is PART 1 of 2" in prompt
    assert "\"summary_paragraph\"" in prompt
    assert "return EXACTLY 6 chronological subsection_candidates" in prompt
    assert "0:00 to 5:00" in prompt


def test_target_section_count_for_span_uses_five_minute_windows():
    assert _target_section_count_for_span(0, 180) == 1
    assert _target_section_count_for_span(0, 301) == 2
    assert _target_section_count_for_span(0, 1891) == 7


def test_build_equal_windows_for_span_covers_chunk_range():
    windows = _build_equal_windows_for_span(0, 1800)
    assert len(windows) == 6
    assert windows[0] == (0, 300)
    assert windows[-1] == (1500, 1800)


def test_reduce_prompt_mentions_required_output_structure():
    prompt = _reduce_user_prompt(
        title="T",
        channel="C",
        duration="3:00:00",
        chunk_json_lines="[]",
        num_map_parts=3,
    )
    assert "key_sections" in prompt
    assert "mindmap" in prompt


def test_sections_prompt_includes_depth_budgets():
    prompt = _sections_only_user_prompt(
        title="T",
        channel="C",
        duration="1:02:00",
        transcript="sample transcript",
        video_type="general",
    )
    assert _section_description_budget("1:02:00") in prompt
    assert _section_subpoint_budget("1:02:00") in prompt
    assert "150-200 word range" in prompt


def test_section_description_budget_scales_with_duration():
    assert _section_description_budget("4:00") == "60-90 words"
    assert _section_description_budget("12:00") == "80-120 words"
    assert _section_description_budget("30:00") == "110-150 words"
    assert _section_description_budget("50:00") == "150-200 words"   # 50 min: unchanged
    assert _section_description_budget("1:02:00") == "120-165 words"  # 62 min: new tier


def test_summary_from_sections_prompt_includes_length_constraints():
    prompt = _summary_from_sections_user_prompt(
        title="T",
        channel="C",
        duration="1:02:00",
        sections=[{"title": "A", "timestamp": "0:00", "timestamp_seconds": 0,
                   "description": "x", "steps": [], "sub_points": [],
                   "trade_offs": [], "notable_detail": ""}],
        video_type="general",
    )
    # budget values still in prompt
    assert _insight_word_budget("1:02:00") in prompt
    assert _concept_explanation_budget("1:02:00") in prompt
    assert _recommendation_word_budget("1:02:00") in prompt
    assert str(_deep_dive_min_word_count("1:02:00")) in prompt
    # JSON shape
    assert '"deep_dive": {' in prompt
    assert '"sections": [' in prompt
    # new deep dive framing
    assert "self-contained essay" in prompt
    assert "The reader will see ONLY this section" in prompt
    assert "Use 5-7 headed sections" in prompt
    assert "2-3 dense paragraphs" in prompt
    assert "thematic lenses" in prompt
    assert "do not force a tutorial/lecture/opinion template" in prompt
    # new insights framing
    assert "Surprising stat or fact" in prompt
    assert "Counterintuitive claim" in prompt
    assert "Practical implication" in prompt
    assert "Recurring theme" in prompt
    assert "Memorable quote or moment" in prompt
    assert "[The finding]" in prompt
    assert "Quality over quantity" in prompt


def test_deep_dive_min_word_count_scales_with_duration():
    assert _deep_dive_min_word_count("5:00") == 350
    assert _deep_dive_min_word_count("12:00") == 450
    assert _deep_dive_min_word_count("25:00") == 650
    assert _deep_dive_min_word_count("55:00") == 800     # 55 min: <=60 min tier
    assert _deep_dive_min_word_count("1:10:00") == 1200  # 70 min: was 800
    assert _deep_dive_min_word_count("2:00:00") == 1800  # 2 hr: was 1200
    assert _deep_dive_min_word_count("4:00:00") == 2200  # 4 hr: was 1500


def test_single_pass_accepts_new_params():
    params = inspect.signature(generate_summary_and_mindmap_single_pass).parameters
    assert "video_type" in params


def test_backfill_summary_depth_populates_missing_concepts_and_insights():
    payload = {
        "summary": {
            "key_sections": [
                {
                    "title": "Intro to the Problem",
                    "timestamp": "0:00",
                    "timestamp_seconds": 0,
                    "description": "The speaker defines the core problem and frames why it matters.",
                    "steps": [],
                    "sub_points": ["Retention drops when viewers consume long-form content without structure."],
                    "trade_offs": [],
                    "notable_detail": "The presenter claims most viewers forget the middle third of a long video.",
                },
                {
                    "title": "Proposed Method",
                    "timestamp": "28:00",
                    "timestamp_seconds": 1680,
                    "description": "The video lays out a concrete process for extracting useful structure from transcripts.",
                    "steps": ["Segment transcript", "Synthesize chunk notes", "Merge into final summary"],
                    "sub_points": ["The workflow preserves timestamps so evidence can be traced back to the source."],
                    "trade_offs": ["More structure increases latency because the summary is synthesized in stages."],
                    "notable_detail": "",
                },
            ],
            "key_insights": [],
            "important_concepts": [],
        }
    }

    result = _backfill_summary_depth(payload, duration="1:02:00")
    summary = result["summary"]

    assert len(summary["key_insights"]["bullets"]) >= 2
    assert len(summary["important_concepts"]) >= 2
    assert summary["deep_dive"]["sections"]
    assert summary["important_concepts"][0]["concept"]
    assert summary["important_concepts"][0]["explanation"]


def test_backfill_summary_depth_normalizes_structured_insight_objects():
    payload = {
        "summary": {
            "key_sections": [],
            "key_insights": [
                {
                    "claim": "AI product sense is becoming a dedicated interview gate.",
                    "why_it_matters": "it changes how candidates need to prepare",
                    "timestamp_reference": "06:04",
                }
            ],
            "important_concepts": [],
        }
    }

    result = _backfill_summary_depth(payload, duration="1:02:00")
    insight = result["summary"]["key_insights"]["bullets"][0]
    assert "AI product sense is becoming a dedicated interview gate." in insight
    assert "Evidence: 06:04." in insight  # _normalize_insight appends this for LLM-returned structured dicts


def test_extract_key_sections_payload_supports_nested_summary_shape():
    payload = {
        "summary": {
            "key_sections": [
                {
                    "title": "Nested section",
                    "timestamp": "0:42",
                    "timestamp_seconds": 42,
                    "description": "Returned under summary.key_sections",
                }
            ]
        }
    }

    sections = _extract_key_sections_payload(payload)
    assert len(sections) == 1
    assert sections[0]["title"] == "Nested section"


def test_extract_key_sections_payload_supports_sections_alias():
    payload = {
        "data": {
            "summary": {
                "sections": [
                    {
                        "heading": "Aliased section",
                        "time": "1:15",
                        "seconds": 75,
                        "body": "Returned under sections instead of key_sections",
                    }
                ]
            }
        }
    }

    sections = _extract_key_sections_payload(payload)
    assert len(sections) == 1
    assert sections[0]["heading"] == "Aliased section"


def test_generate_summary_and_mindmap_accepts_new_params():
    params = inspect.signature(generate_summary_and_mindmap).parameters
    assert "video_type" in params


def test_section_subpoint_budget_long_video():
    assert _section_subpoint_budget("50:00") == "4-7"   # 45-60 min: unchanged
    assert _section_subpoint_budget("1:02:00") == "3-5"  # 60+ min: new tier


def test_insight_word_budget_is_uniform():
    assert _insight_word_budget("10:00") == "30-60 words"
    assert _insight_word_budget("1:02:00") == "30-60 words"


def test_polish_prompt_uses_tighter_cap_for_long_videos():
    prompt = _key_sections_polish_prompt(
        title="T", channel="C", duration="1:05:00",
        sections=[{"title": "A", "timestamp": "0:00", "timestamp_seconds": 0,
                   "description": "d", "steps": [], "sub_points": [],
                   "trade_offs": [], "notable_detail": ""}],
        section_materials=[{"timestamp_seconds": 0, "source_words": 300,
                             "transcript_excerpt": ""}],
    )
    assert "at most 55%" in prompt
    assert "at most 65%" not in prompt


def test_polish_prompt_uses_standard_cap_for_short_videos():
    prompt = _key_sections_polish_prompt(
        title="T", channel="C", duration="50:00",
        sections=[{"title": "A", "timestamp": "0:00", "timestamp_seconds": 0,
                   "description": "d", "steps": [], "sub_points": [],
                   "trade_offs": [], "notable_detail": ""}],
        section_materials=[{"timestamp_seconds": 0, "source_words": 300,
                             "transcript_excerpt": ""}],
    )
    assert "at most 65%" in prompt
    assert "at most 55%" not in prompt


def test_backfill_does_not_produce_mechanical_evidence_text():
    payload = {
        "summary": {
            "key_sections": [
                {
                    "title": "Core Claim",
                    "timestamp": "5:00",
                    "timestamp_seconds": 300,
                    "description": "The speaker argues against conventional wisdom.",
                    "steps": [],
                    "sub_points": [],
                    "trade_offs": [],
                    "notable_detail": "Conventional A/B testing underestimates long-term retention by 40%.",
                },
                {
                    "title": "Practical Steps",
                    "timestamp": "15:00",
                    "timestamp_seconds": 900,
                    "description": "A three-step framework for implementing the approach.",
                    "steps": ["Segment your audience", "Run a holdout test", "Measure at 90 days"],
                    "sub_points": ["The holdout must be at least 10% of traffic."],
                    "trade_offs": [],
                    "notable_detail": "",
                },
            ],
            "key_insights": [],
            "important_concepts": [],
        }
    }

    result = _backfill_summary_depth(payload, duration="25:00")
    bullets = result["summary"]["key_insights"]["bullets"]

    assert len(bullets) <= 2
    for bullet in bullets:
        assert "This matters because it is a central point in" not in bullet
        assert "Evidence:" not in bullet
        assert " — " in bullet


def test_mindmap_prompt_short_video_is_free_flowing():
    prompt = _mindmap_from_sections_user_prompt(
        title="T", channel="C", duration="10:00",
        sections=[],
    )
    assert "3-6 branches" in prompt
    assert "7-10 branches" not in prompt
    assert "45-80 nodes" not in prompt


def test_mindmap_prompt_medium_video_uses_mid_tier():
    prompt = _mindmap_from_sections_user_prompt(
        title="T", channel="C", duration="35:00",
        sections=[],
    )
    assert "5-8 branches" in prompt
    assert "25-50 nodes" in prompt


def test_mindmap_prompt_long_video_uses_deep_tier():
    prompt = _mindmap_from_sections_user_prompt(
        title="T", channel="C", duration="1:05:00",
        sections=[],
    )
    assert "7-10 branches" in prompt
    assert "45-80 nodes" in prompt
    assert "3 levels" in prompt
    assert "major content span" in prompt


def test_mindmap_prompt_removes_old_char_caps():
    prompt = _mindmap_from_sections_user_prompt(
        title="T", channel="C", duration="35:00",
        sections=[],
    )
    assert "max 40 chars" not in prompt
    assert "max 55 chars" not in prompt
    assert "max 60 chars" in prompt
    assert "max 65 chars" in prompt


def test_mindmap_prompt_bans_generic_branch_names():
    for duration in ["10:00", "35:00", "1:05:00"]:
        prompt = _mindmap_from_sections_user_prompt(
            title="T", channel="C", duration=duration,
            sections=[],
        )
        assert "Key Points" in prompt  # listed as a banned name
        assert "Main Ideas" in prompt
