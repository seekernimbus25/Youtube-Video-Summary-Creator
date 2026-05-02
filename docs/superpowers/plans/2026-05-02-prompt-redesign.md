# Prompt Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give each of the four summary views one exclusive job by rewriting their prompts and budgets in `backend/services/claude_service.py`.

**Architecture:** All changes are prompt-and-budget functions in one file. No schema or API changes. Tests live in `backend/tests/test_claude_quality.py` (existing) and are updated/extended in place.

**Tech Stack:** Python, pytest (run from `backend/` directory)

---

## File Map

| File | What changes |
|---|---|
| `backend/services/claude_service.py` | All 11 function edits |
| `backend/tests/test_claude_quality.py` | Update 3 existing tests + add new assertions |

---

## Task 1: Budget functions — description, subpoint, insight word, deep dive word count

**Files:**
- Modify: `backend/services/claude_service.py:679-727`
- Test: `backend/tests/test_claude_quality.py`

- [ ] **Step 1: Update existing budget tests to assert new behavior (they will fail until implemented)**

  In `test_claude_quality.py`, find `test_section_description_budget_scales_with_duration` and change the 62-min assertion:

  ```python
  def test_section_description_budget_scales_with_duration():
      assert _section_description_budget("4:00") == "60-90 words"
      assert _section_description_budget("12:00") == "80-120 words"
      assert _section_description_budget("30:00") == "110-150 words"
      assert _section_description_budget("50:00") == "150-200 words"   # 50 min: unchanged
      assert _section_description_budget("1:02:00") == "120-165 words"  # 62 min: new tier
  ```

  Find `test_deep_dive_min_word_count_scales_with_duration` and replace:

  ```python
  def test_deep_dive_min_word_count_scales_with_duration():
      assert _deep_dive_min_word_count("5:00") == 350
      assert _deep_dive_min_word_count("12:00") == 450
      assert _deep_dive_min_word_count("25:00") == 650
      assert _deep_dive_min_word_count("55:00") == 800     # 55 min: <=60 min tier
      assert _deep_dive_min_word_count("1:10:00") == 1200  # 70 min: was 800
      assert _deep_dive_min_word_count("2:00:00") == 1800  # 2 hr: was 1200
      assert _deep_dive_min_word_count("4:00:00") == 2200  # 4 hr: was 1500
  ```

- [ ] **Step 2: Add new budget tests (also fail until implemented)**

  Append to `test_claude_quality.py`:

  ```python
  def test_section_subpoint_budget_long_video():
      assert _section_subpoint_budget("50:00") == "4-7"   # 45-60 min: unchanged
      assert _section_subpoint_budget("1:02:00") == "3-5"  # 60+ min: new tier


  def test_insight_word_budget_is_uniform():
      assert _insight_word_budget("10:00") == "30-60 words"
      assert _insight_word_budget("1:02:00") == "30-60 words"
  ```

- [ ] **Step 3: Run tests to confirm they fail**

  ```
  cd backend
  python -m pytest tests/test_claude_quality.py::test_section_description_budget_scales_with_duration tests/test_claude_quality.py::test_deep_dive_min_word_count_scales_with_duration tests/test_claude_quality.py::test_section_subpoint_budget_long_video tests/test_claude_quality.py::test_insight_word_budget_is_uniform -v
  ```

  Expected: 4 FAILED

- [ ] **Step 4: Implement the four budget functions**

  In `claude_service.py`, replace lines 679–727:

  ```python
  def _section_description_budget(duration: str) -> str:
      duration_seconds = _parse_duration_to_seconds(duration)
      if duration_seconds >= 60 * 60:
          return "120-165 words"
      if duration_seconds >= 45 * 60:
          return "150-200 words"
      if duration_seconds >= 20 * 60:
          return "110-150 words"
      if duration_seconds >= 8 * 60:
          return "80-120 words"
      return "60-90 words"


  def _section_subpoint_budget(duration: str) -> str:
      duration_seconds = _parse_duration_to_seconds(duration)
      if duration_seconds >= 60 * 60:
          return "3-5"
      return "4-7" if duration_seconds >= 45 * 60 else "3-5"


  def _insight_word_budget(duration: str) -> str:
      return "30-60 words"


  def _concept_explanation_budget(duration: str) -> str:
      duration_seconds = _parse_duration_to_seconds(duration)
      return "90-180 words" if duration_seconds >= 45 * 60 else "60-140 words"


  def _recommendation_word_budget(duration: str) -> str:
      duration_seconds = _parse_duration_to_seconds(duration)
      return "20-60 words" if duration_seconds >= 45 * 60 else "15-45 words"


  def _conclusion_word_budget(duration: str) -> str:
      duration_seconds = _parse_duration_to_seconds(duration)
      return "120-220 words" if duration_seconds >= 45 * 60 else "80-160 words"


  def _deep_dive_min_word_count(duration: str) -> int:
      duration_seconds = _parse_duration_to_seconds(duration)
      if duration_seconds <= 5 * 60:
          return 350
      if duration_seconds <= 20 * 60:
          return 450
      if duration_seconds <= 45 * 60:
          return 650
      if duration_seconds <= 60 * 60:
          return 800
      if duration_seconds <= int(1.5 * 60 * 60):
          return 1200
      if duration_seconds <= 3 * 60 * 60:
          return 1800
      return 2200
  ```

- [ ] **Step 5: Run tests to confirm they pass**

  ```
  cd backend
  python -m pytest tests/test_claude_quality.py::test_section_description_budget_scales_with_duration tests/test_claude_quality.py::test_deep_dive_min_word_count_scales_with_duration tests/test_claude_quality.py::test_section_subpoint_budget_long_video tests/test_claude_quality.py::test_insight_word_budget_is_uniform -v
  ```

  Expected: 4 PASSED

- [ ] **Step 6: Commit**

  ```bash
  git add backend/services/claude_service.py backend/tests/test_claude_quality.py
  git commit -m "feat: add 60-min budget tiers and uniform insight word budget"
  ```

---

## Task 2: Key Sections polish prompt — tighter cap for 60+ min videos

**Files:**
- Modify: `backend/services/claude_service.py:1125-1179`
- Test: `backend/tests/test_claude_quality.py`

- [ ] **Step 1: Add new polish prompt tests (fail until implemented)**

  Append to `test_claude_quality.py`. Add `_key_sections_polish_prompt` to the import block at the top of the file:

  ```python
  from services.claude_service import (
      ...
      _key_sections_polish_prompt,
      ...
  )
  ```

  Then add these two test functions:

  ```python
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
  ```

- [ ] **Step 2: Run tests to confirm they fail**

  ```
  cd backend
  python -m pytest tests/test_claude_quality.py::test_polish_prompt_uses_tighter_cap_for_long_videos tests/test_claude_quality.py::test_polish_prompt_uses_standard_cap_for_short_videos -v
  ```

  Expected: 2 FAILED

- [ ] **Step 3: Implement the duration-aware cap in `_key_sections_polish_prompt`**

  In `claude_service.py`, replace the `_key_sections_polish_prompt` function (lines 1125–1179). The only change is adding a `duration_seconds` local and swapping the rule string:

  ```python
  def _key_sections_polish_prompt(
      title: str,
      channel: str,
      duration: str,
      sections: List[Dict[str, Any]],
      section_materials: List[Dict[str, Any]],
  ) -> str:
      duration_seconds = _parse_duration_to_seconds(duration)
      cap_rule = (
          "at least 30% and at most 55% of that section's source_words count. Aim for roughly 40%-50%"
          if duration_seconds >= 60 * 60
          else "at least 30% and at most 65% of that section's source_words count. Aim for roughly 45%-55%"
      )
      materials_by_ts = {int(item.get("timestamp_seconds", 0)): item for item in section_materials}
      payload = []
      for section in sections:
          material = materials_by_ts.get(int(section.get("timestamp_seconds", 0)), {})
          payload.append(
              {
                  "section": section,
                  "source_words": int(material.get("source_words", 0)),
                  "transcript_excerpt": material.get("transcript_excerpt", ""),
              }
          )

      return f"""
  You are rewriting key sections so they read like rich summaries, not transcript copies.

  Video:
  Title: {title}
  Channel: {channel}
  Duration: {duration}

  Return valid JSON only:
  {{
    "key_sections": [
      {{
        "title": "Same title",
        "timestamp": "Same timestamp",
        "timestamp_seconds": 0,
        "description": "Rich summary",
        "steps": ["rewritten step"],
        "sub_points": ["rewritten detail"],
        "trade_offs": ["rewritten limitation"],
        "notable_detail": "memorable specific detail"
      }}
    ]
  }}

  Section inputs:
  {json.dumps(payload, ensure_ascii=False, indent=2)}

  Rules:
  - Keep the same number of sections.
  - Preserve each section's title, timestamp, and timestamp_seconds exactly.
  - description must be a summary, not a transcript copy.
  - For each section, description length should be {cap_rule}. The cap is a ceiling, not a target — do not pad a short section to reach it.
  - Do not quote or copy long contiguous spans from the transcript excerpt.
  - Do not mention timestamps inside description, steps, sub_points, trade_offs, or notable_detail.
  - Remove repetition across fields.
  """.strip()
  ```

- [ ] **Step 4: Run tests to confirm they pass**

  ```
  cd backend
  python -m pytest tests/test_claude_quality.py::test_polish_prompt_uses_tighter_cap_for_long_videos tests/test_claude_quality.py::test_polish_prompt_uses_standard_cap_for_short_videos -v
  ```

  Expected: 2 PASSED

- [ ] **Step 5: Commit**

  ```bash
  git add backend/services/claude_service.py backend/tests/test_claude_quality.py
  git commit -m "feat: tighten key sections description cap to 55% for 60+ min videos"
  ```

---

## Task 3: Summary prompt — standalone Deep Dive essay + Insights archetypes

**Files:**
- Modify: `backend/services/claude_service.py:1895-1983`
- Test: `backend/tests/test_claude_quality.py`

- [ ] **Step 1: Update the existing summary prompt test to match new content**

  Find `test_summary_from_sections_prompt_includes_length_constraints` and replace it entirely:

  ```python
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
  ```

- [ ] **Step 2: Run test to confirm it fails**

  ```
  cd backend
  python -m pytest tests/test_claude_quality.py::test_summary_from_sections_prompt_includes_length_constraints -v
  ```

  Expected: FAILED

- [ ] **Step 3: Implement the new `_summary_from_sections_user_prompt`**

  In `claude_service.py`, replace the entire `_summary_from_sections_user_prompt` function (lines 1895–1983):

  ```python
  def _summary_from_sections_user_prompt(
      title: str,
      channel: str,
      duration: str,
      sections: List[Dict[str, Any]],
      video_type: str,
  ) -> str:
      sections_json = json.dumps(sections, ensure_ascii=False, indent=2)
      return f"""
  You are writing the final study-note-quality summary for a video using an already-extracted section backbone.

  Video:
  Title: {title}
  Channel: {channel}
  Duration: {duration}

  Section backbone (chronological and authoritative):
  {sections_json}

  Respond with valid JSON only:
  {{
    "video_overview": {{
      "title": "{title}",
      "channel": "{channel}",
      "duration": "{duration}",
      "main_topic": "One precise sentence describing the video's true subject",
      "elevator_pitch": "2-4 sentences covering the overall arc, what the speaker actually does, and what the viewer learns"
    }},
    "key_insights": {{
      "bullets": [
        "The finding — why it matters or what to do about it"
      ]
    }},
    "deep_dive": {{
      "sections": [
        {{
          "heading": "Thematic heading derived from content",
          "paragraphs": [
            "Dense paragraph grounded in the section backbone",
            "Dense paragraph grounded in the section backbone"
          ]
        }}
      ]
    }},
    "important_concepts": [
      {{
        "concept": "Concept name",
        "explanation": "3-5 sentences explaining it in the context of this video",
        "why_it_matters": "1-2 sentences of practical significance",
        "example_from_video": "Specific example or demonstration from the video"
      }}
    ],
    "comparison_table": {{
      "applicable": true,
      "headers": ["Option/Method", "Performance", "Cost", "Best For", "Trade-offs"],
      "rows": [["Option", "detail", "detail", "detail", "detail"]]
    }},
    "practical_recommendations": ["Actionable recommendation tied to a specific condition or use case"],
    "conclusion": "3-5 sentence synthesis of the speaker's real ending and the most important takeaway",
    "keywords": ["specific named entities, tools, methods, or topics"],
    "action_items": ["Immediate action the viewer can take"]
  }}

  Rules:
  - Do not rewrite or merge the sections. Treat them as fixed source material.
  - key_insights.bullets: write as many bullets as the content genuinely supports — no fixed count. Quality over quantity. Do not pad with weak bullets to hit a number.
  - Each bullet must belong to one of these archetypes:
    1. Surprising stat or fact — something the viewer would not expect
    2. Counterintuitive claim — goes against common assumption
    3. Practical implication — what this means for what you should do
    4. Recurring theme — a pattern that surfaces in multiple parts of the video
    5. Memorable quote or moment — something specific the speaker said or demonstrated
  - Format each bullet as: [The finding] — [why it matters or what to do about it]
  - Each bullet should be roughly {_insight_word_budget(duration)} and must stay under 100 words.
  - Do not restate a Key Section title as a bullet.
  - Do not write generic observations like "the speaker discusses X" or "the video explains Y".
  - Do not include timestamp references in bullets.
  - Do not use passive constructions ("it is noted that...").
  - deep_dive.sections: you are writing a self-contained essay about this video. The reader will see ONLY this section — no Key Sections, no timestamps, nothing else. Write it the way you would if asked to summarize this video comprehensively. Cover: what the video argues, how it argues it, the key evidence and examples, what is surprising or counterintuitive, and the practical significance.
  - Use 5-7 headed sections.
  - Each section must contain 2-3 dense paragraphs.
  - Headings must be thematic lenses derived from the content, not topic labels. Good: "Why the Common Approach Fails". Bad: "Section 3" or "Main Discussion".
  - At least one heading must synthesize across multiple parts of the video rather than covering one part in isolation.
  - Infer headings from the actual section backbone — do not force a tutorial/lecture/opinion template.
  - The total deep dive should be at least {_deep_dive_min_word_count(duration)} words.
  - important_concepts: 6-10 items for long videos and each should pull from different parts of the section backbone where possible.
  - Each important_concepts.explanation should be roughly {_concept_explanation_budget(duration)} and should not exceed 220 words.
  - practical_recommendations: 4-8 items, each grounded in something specific from the sections.
  - Each practical recommendation should be roughly {_recommendation_word_budget(duration)} and should not exceed 80 words.
  - conclusion should be roughly {_conclusion_word_budget(duration)} and should not exceed 260 words.
  - video_overview.elevator_pitch should be 70-140 words for long videos and should not exceed 180 words.
  - comparison_table: only set applicable=true if the sections actually support a real comparison.
  - Never use placeholder filler. Everything must trace back to the supplied sections.
  """.strip()
  ```

- [ ] **Step 4: Run test to confirm it passes**

  ```
  cd backend
  python -m pytest tests/test_claude_quality.py::test_summary_from_sections_prompt_includes_length_constraints -v
  ```

  Expected: PASSED

- [ ] **Step 5: Run full test suite to catch regressions**

  ```
  cd backend
  python -m pytest tests/test_claude_quality.py -v
  ```

  Expected: all pass. If `test_backfill_summary_depth_populates_missing_concepts_and_insights` fails, it will be fixed in Task 4.

- [ ] **Step 6: Commit**

  ```bash
  git add backend/services/claude_service.py backend/tests/test_claude_quality.py
  git commit -m "feat: rewrite Deep Dive as standalone essay, add Key Insights archetypes"
  ```

---

## Task 4: Backfill logic — archetype-driven fallback

**Files:**
- Modify: `backend/services/claude_service.py:1258-1272`
- Test: `backend/tests/test_claude_quality.py`

- [ ] **Step 1: Add backfill format test (fails until implemented)**

  Append to `test_claude_quality.py`:

  ```python
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
  ```

- [ ] **Step 2: Run test to confirm it fails**

  ```
  cd backend
  python -m pytest tests/test_claude_quality.py::test_backfill_does_not_produce_mechanical_evidence_text -v
  ```

  Expected: FAILED

- [ ] **Step 3: Implement the archetype-driven backfill**

  In `claude_service.py`, find the block starting at line 1258 (the `if len(insights) < 6:` block) and replace it with:

  ```python
  _BACKFILL_ARCHETYPES = [
      "a surprising stat or fact",
      "a practical implication",
      "a counterintuitive claim",
      "a recurring theme",
      "a memorable moment",
  ]

  if len(insights) < 3:
      backfilled = 0
      for section in sections:
          if backfilled >= 2:
              break
          detail = (section.get("notable_detail") or "").strip()
          if not detail:
              detail = next(
                  (str(sp).strip() for sp in section.get("sub_points", []) if str(sp).strip()),
                  "",
              )
          if not detail:
              continue
          archetype = _BACKFILL_ARCHETYPES[backfilled % len(_BACKFILL_ARCHETYPES)]
          bullet = f"{detail} — {archetype} from the {section['title']} discussion."
          if bullet not in insights:
              insights.append(bullet)
              backfilled += 1
  ```

  Note: `_BACKFILL_ARCHETYPES` should be defined as a module-level constant, placed just before `_backfill_summary_depth` at around line 1230.

- [ ] **Step 4: Run the new test and both existing backfill tests**

  ```
  cd backend
  python -m pytest tests/test_claude_quality.py::test_backfill_does_not_produce_mechanical_evidence_text tests/test_claude_quality.py::test_backfill_summary_depth_populates_missing_concepts_and_insights tests/test_claude_quality.py::test_backfill_summary_depth_normalizes_structured_insight_objects -v
  ```

  Expected: 3 PASSED

- [ ] **Step 5: Commit**

  ```bash
  git add backend/services/claude_service.py backend/tests/test_claude_quality.py
  git commit -m "feat: replace mechanical backfill with archetype-driven insight fallback"
  ```

---

## Task 5: Mind Map prompt — scaled structure, char limit update, token bump, reduce prompt

**Files:**
- Modify: `backend/services/claude_service.py:1986-2035` (mindmap prompt)
- Modify: `backend/services/claude_service.py:1811` (reduce prompt mindmap rule)
- Modify: `backend/services/claude_service.py:2189` (token bump)
- Test: `backend/tests/test_claude_quality.py`

- [ ] **Step 1: Add scaled mindmap prompt tests (fail until implemented)**

  Add `_mindmap_from_sections_user_prompt` to the imports in `test_claude_quality.py` if not already there.

  Append to `test_claude_quality.py`:

  ```python
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
  ```

- [ ] **Step 2: Run tests to confirm they fail**

  ```
  cd backend
  python -m pytest tests/test_claude_quality.py::test_mindmap_prompt_short_video_is_free_flowing tests/test_claude_quality.py::test_mindmap_prompt_medium_video_uses_mid_tier tests/test_claude_quality.py::test_mindmap_prompt_long_video_uses_deep_tier tests/test_claude_quality.py::test_mindmap_prompt_removes_old_char_caps tests/test_claude_quality.py::test_mindmap_prompt_bans_generic_branch_names -v
  ```

  Expected: 5 FAILED

- [ ] **Step 3: Implement the new `_mindmap_from_sections_user_prompt`**

  In `claude_service.py`, replace the `_mindmap_from_sections_user_prompt` function (lines 1986–2035):

  ```python
  def _mindmap_from_sections_user_prompt(
      title: str,
      channel: str,
      duration: str,
      sections: List[Dict[str, Any]],
  ) -> str:
      duration_seconds = _parse_duration_to_seconds(duration)
      sections_json = json.dumps(sections, ensure_ascii=False, indent=2)

      if duration_seconds < 20 * 60:
          structure_rules = """- Use 3-6 branches, content-driven — only include branches with real content.
  - 2 levels is sufficient (branch -> leaf); sub-branches are optional.
  - No node count target — as many nodes as the content naturally supports.
  - Hard rules: branches must map to real content; leaves must be complete sentences; no vague branch labels (see banned names below)."""
      elif duration_seconds < 60 * 60:
          structure_rules = """- Use 5-8 branches.
  - 2-3 levels (sub-branches encouraged but not required).
  - Target 25-50 nodes total (quality target, not a hard requirement — do not pad with weak nodes).
  - Leaves must be complete sentences with one specific fact, claim, step, or example."""
      else:
          structure_rules = """- Use 7-10 branches.
  - Use 3 levels: root -> branch -> sub-branch -> leaf.
  - Target 45-80 nodes total (quality target — do not pad with weak nodes to hit the number).
  - Branches must cover the video's major content span. If all branches represent ideas from only the first third of the video's content, that is a failure — cover the full range.
  - Leaves must be complete sentences with one specific fact, claim, step, or example.
  - Branches with fewer than 3 meaningful sub-topics may skip sub-branches and go directly to 3-5 leaf children."""

      return f"""
  You are building a mind map tree from a video's extracted sections.

  Video:
  Title: {title}
  Channel: {channel}
  Duration: {duration}

  Section backbone:
  {sections_json}

  Respond with valid JSON only:
  {{
    "mindmap": {{
      "id": "root",
      "label": "Central thesis of the video, up to 60 chars",
      "category": "root",
      "children": [
        {{
          "id": "branch-1",
          "label": "Major topic area, up to 65 chars",
          "category": "concept",
          "children": [
            {{
              "id": "branch-1-1",
              "label": "Sub-topic within branch, up to 65 chars",
              "category": "concept",
              "children": [
                {{
                  "id": "branch-1-1-1",
                  "label": "Complete sentence with one specific fact, claim, step, or example",
                  "category": "data",
                  "children": []
                }}
              ]
            }}
          ]
        }}
      ]
    }}
  }}

  Structure rules:
  {structure_rules}

  Rules for all videos:
  - Branches must map directly to real content in the section backbone, not generic categories.
  - Banned branch names (do not use these unless the transcript itself uses them as chapter names): "Key Points", "Main Ideas", "Overview", "Introduction", "Conclusion".
  - Leaves must be complete sentences. Do not use topic labels as leaves.
  - Prefer one fact, claim, step, or example per leaf.
  - Avoid duplicate branches and duplicate leaves.
  """.strip()
  ```

- [ ] **Step 4: Update the mindmap rule in `_reduce_user_prompt`**

  In `claude_service.py`, find line 1811 (inside `_reduce_user_prompt`):

  ```python
  - mindmap: 4-7 main branches, leaves are substantive sentences.
  ```

  Replace it with (this is inside the f-string, so just change the text at that line):

  ```python
  - mindmap: use 7-10 branches for this long video, 3 levels (root -> branch -> sub-branch -> leaf), target 45-80 nodes (quality target — do not pad). Branches must cover the video's major content span, not just the first third of ideas. Sub-branches group related leaves. Leaves are complete sentences with specific facts, claims, or examples. Banned branch names: "Key Points", "Main Ideas", "Overview", "Introduction", "Conclusion".
  ```

- [ ] **Step 5: Bump `max_out_tokens` for mindmap synthesis**

  In `claude_service.py`, find `_synthesize_mindmap_from_sections` (around line 2176). Change:

  ```python
  max_out_tokens=8000,
  ```

  to:

  ```python
  max_out_tokens=10000,
  ```

- [ ] **Step 6: Run the new mindmap tests**

  ```
  cd backend
  python -m pytest tests/test_claude_quality.py::test_mindmap_prompt_short_video_is_free_flowing tests/test_claude_quality.py::test_mindmap_prompt_medium_video_uses_mid_tier tests/test_claude_quality.py::test_mindmap_prompt_long_video_uses_deep_tier tests/test_claude_quality.py::test_mindmap_prompt_removes_old_char_caps tests/test_claude_quality.py::test_mindmap_prompt_bans_generic_branch_names -v
  ```

  Expected: 5 PASSED

- [ ] **Step 7: Run the full test suite**

  ```
  cd backend
  python -m pytest tests/ -v
  ```

  Expected: all tests pass

- [ ] **Step 8: Commit**

  ```bash
  git add backend/services/claude_service.py backend/tests/test_claude_quality.py
  git commit -m "feat: scale mindmap prompt by video length, bump mindmap token budget to 10k"
  ```

---

## Self-Review

**Spec coverage check:**

| Spec requirement | Task |
|---|---|
| `_section_description_budget` 60-min tier | Task 1 |
| `_section_subpoint_budget` 60-min tier | Task 1 |
| `_insight_word_budget` → 30-60 words | Task 1 |
| `_deep_dive_min_word_count` new tiers | Task 1 |
| `_key_sections_polish_prompt` tighter cap | Task 2 |
| `_polish_key_sections` threads duration | n/a — duration was already passed |
| Deep Dive standalone essay framing | Task 3 |
| Key Insights archetypes + bans | Task 3 |
| Remove fixed insight bullet count | Task 3 |
| `_backfill_summary_depth` archetype fix | Task 4 |
| `_mindmap_from_sections_user_prompt` scaled | Task 5 |
| `_reduce_user_prompt` mindmap rules | Task 5 |
| `max_out_tokens` bump to 10000 | Task 5 |

All 11 spec items covered. No gaps.
