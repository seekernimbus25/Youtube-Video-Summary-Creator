---
title: Prompt Redesign — Role-Differentiated Views
date: 2026-05-02
status: approved
---

# Prompt Redesign: Role-Differentiated Views

## Goal

Each of the four summary views currently pulls from the same section backbone without a distinct job. The result: Deep Dive feels like a shallow Key Sections recap, Key Insights are generic, the Mind Map is sparse, and long-video Key Sections are too verbose. This spec redesigns each view around a single exclusive role.

---

## Role Definitions

| View | Job | Explicitly NOT |
|---|---|---|
| Key Sections | Navigation layer — scan to find where things happen | Not an essay, not analysis |
| Deep Dive | Standalone essay — useful even if you read nothing else | Not a recap of Key Sections |
| Key Insights | Aha moments — surprising, non-obvious, quotable | Not a summary of the timeline |
| Mind Map | Concept web — every major idea and how they connect | Not a timeline, not a list |

---

## 1. Key Sections — Trim for 60+ min videos only

**Scope:** Only videos with duration ≥ 60 minutes. Videos under 60 minutes are unchanged.

### Changes to `_section_description_budget`

Add a new tier for 60+ minute videos:

```
< 8 min:    60-90 words      (unchanged)
8-20 min:   80-120 words     (unchanged)
20-45 min:  110-150 words    (unchanged)
45-60 min:  150-200 words    (unchanged — existing 45+ tier applies here)
60+ min:    120-165 words    (NEW — ~15% reduction)
```

Implementation: the function currently uses `45 * 60` as the top threshold. Add a new check for `60 * 60` that returns `"120-165 words"` before falling through to the 45-min tier.

### Changes to `_section_subpoint_budget`

Add a new tier for 60+ minute videos:

```
< 45 min:   3-5 sub_points   (unchanged)
45-60 min:  4-7 sub_points   (unchanged)
60+ min:    3-5 sub_points   (NEW)
```

### Changes to `_key_sections_polish_prompt`

For 60+ minute videos, change the description length rule from:
> "at least 30% and at most 65% of that section's source_words count"

to:
> "at least 30% and at most 55% of that section's source_words count"

Pass the duration into the polish prompt and conditionally apply the tighter cap.

---

## 2. Deep Dive — Standalone essay rewrite

### Prompt framing change

Replace the current framing ("write a strong standalone deep dive with proper headings") with an explicit standalone-essay job:

> "You are writing a self-contained essay about this video. The reader will see ONLY this section — no Key Sections, no timestamps, nothing else. Write it the way Claude or ChatGPT would if asked: 'Summarize this video comprehensively.' Cover: what the video argues, how it argues it, the key evidence and examples, what is surprising or counterintuitive, and the practical significance."

### Structural changes

- **5-7 headed sections** (up from 4-6)
- **2-3 paragraphs per section** (up from 1-2)
- Headings must be **thematic lenses** derived from content, not topic labels. Good: "Why the Common Approach Fails". Bad: "Section 3" or "Main Discussion".
- At least one heading must **synthesize across multiple parts** of the video rather than covering one part in isolation.
- Headings must be inferred from the actual section backbone content — do not force a tutorial/lecture/opinion template.

### Minimum word count changes (in `_deep_dive_min_word_count`)

```
≤ 5 min:   350  (unchanged)
≤ 20 min:  450  (unchanged)
≤ 45 min:  650  (unchanged)
≤ 60 min:  800  (unchanged for this range — previously the 45-90 min range was one tier at 800)
≤ 90 min:  1200 (NEW — 60-90 min videos previously got 800, now get 1200)
≤ 3 hours: 1800 (up from 1200)
> 3 hours: 2200 (up from 1500)
```

---

## 3. Key Insights — Structured archetypes

### Prompt framing change

Replace "high-signal bullet that synthesizes a major takeaway" with:

> "Each bullet must belong to one of these archetypes:
> 1. Surprising stat or fact — something the viewer would not expect
> 2. Counterintuitive claim — goes against common assumption
> 3. Practical implication — what this means for what you should do
> 4. Recurring theme — a pattern that surfaces in multiple parts of the video
> 5. Memorable quote or moment — something specific the speaker said or demonstrated
>
> Format: [The finding] — [why it matters or what to do about it]"

### Explicit bans added to prompt

- Do not restate a Key Section title as a bullet
- Do not write generic observations like "the speaker discusses X" or "the video explains Y"
- Do not include timestamp references
- Do not use passive constructions ("it is noted that...")

### Count and length

- **5-8 bullets** (unchanged)
- **30-60 words per bullet** (tightened from current 35-80 / 25-60 word budgets)

### Backfill logic (`_backfill_summary_depth`)

The current fallback for fewer than 6 insights produces mechanical text like:
> "X. This matters because it is a central point in Y. Evidence: Z."

Replace this fallback with archetype-driven generation: pull `notable_detail` from sections and cast it as an archetype bullet in the `[finding] — [why it matters]` format. Cap backfilled bullets at 2 — if real insights are genuinely sparse, 4 good bullets beat 8 mechanical ones.

---

## 4. Mind Map — Scaled structure

### Structure scales with video length

The required depth and node count depend on video duration.

#### Short videos (< 20 min)
- **3-6 branches**, content-driven — no hard minimum
- **2 levels** sufficient (branch → leaf); sub-branches optional
- No hard node count — "as many as the content naturally supports"
- Only hard rules: branches must map to real content, leaves must be complete sentences, no vague labels ("Key Points", "Main Ideas", "Overview")

#### Medium videos (20-60 min)
- **5-8 branches**
- **2-3 levels** (sub-branches encouraged but not required)
- **Target 25-50 nodes**

#### Long videos (60+ min)
- **7-10 branches**
- **3 levels required**: root → branch → sub-branch → leaf
- **Target 45-80 nodes**
- Branches must span the full video timeline — if all branches come from the first third of the video, that is a failure

### Node structure (all video lengths)

```
root        central thesis of the video (up to 60 chars)
branch      major topic area (up to 65 chars)
sub-branch  sub-topic within a branch (up to 65 chars)
leaf        complete sentence with one specific fact, claim, step, or example
```

Branches with fewer than 3 meaningful sub-topics may skip the sub-branch level and go directly to 3-5 leaf children.

### Changes to `_mindmap_from_sections_user_prompt`

- Remove the existing 40-char root label cap and 55-char branch label cap; replace with 60 and 65 chars respectively
- Remove leaf character cap entirely — leaves must be complete sentences
- Replace "5-9 major branches" rule with the scaled table above (pass duration into the function)
- Add: "Explicitly ban branch names: 'Key Points', 'Main Ideas', 'Overview', 'Introduction', 'Conclusion' unless the transcript itself uses those as chapter names"
- Add the full-video coverage rule for 60+ min videos
- Add target node count per tier

### Reduce prompt

Same structural scaling applies to the `_reduce_user_prompt` mind map rules section (currently just "4-7 main branches, leaves are substantive sentences").

---

## Implementation Scope

### Files changed
- `backend/services/claude_service.py` — all prompt and budget function changes

### Functions touched
1. `_section_description_budget` — add 60-min tier
2. `_section_subpoint_budget` — add 60-min tier
3. `_key_sections_polish_prompt` — tighter cap for 60+ min, add `duration` parameter
4. `_polish_key_sections` — thread `duration` through to the prompt builder (caller of #3)
5. `_insight_word_budget` — tighten to 30-60 words across the board
6. `_deep_dive_min_word_count` — new tiers for 90 min, 3 hours, 3+ hours
7. `_summary_from_sections_user_prompt` — new Deep Dive framing + Insights archetypes
8. `_backfill_summary_depth` — fix mechanical insights fallback
9. `_mindmap_from_sections_user_prompt` — add `duration` parameter, scaled structure, char limit changes
10. `_reduce_user_prompt` — update mind map rules section

### Not changed
- Key Sections prompts for videos < 60 min
- Section backbone extraction logic
- Map/reduce orchestration
- Frontend rendering
