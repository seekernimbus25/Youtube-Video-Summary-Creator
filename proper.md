# Summary Refactor And Cleanup Plan

## Goal

Replace the current fixed summary schema with a smaller, more reliable contract that supports four universal views:

1. `Key Sections`
2. `Insights`
3. `Deep Dive`
4. `Mind Map`

At the same time, remove dead code and keep the app lean. The rule for this refactor is simple:

- keep the output contract small
- keep the render path deterministic
- do not carry legacy structures longer than needed
- prefer a 10-line solution over a 100-line abstraction

---

## Product Structure

### Universal tabs

Every summary should render these four tabs below the video card:

1. `Key Sections`
2. `Insights`
3. `Deep Dive`
4. `Mind Map`

### Tab behavior

- default active tab: `Insights`
- tabs are horizontal and stay in one row on desktop
- on mobile, tabs can wrap or horizontally scroll
- only one tab body renders at a time

### Content responsibilities

#### `Key Sections`

- timestamped chronological breakdown
- keeps the current section data model
- remains the backbone for all later synthesis

#### `Insights`

- short, high-signal summary of the entire video
- always rendered as bullets, not prose
- 4-8 bullets max
- answers:
  - what the video is about
  - what kind of video it is
  - what the viewer should take away
- should feel like an overall synthesis, not the old per-point `key_insights` style

#### `Deep Dive`

- type-aware structured summary
- same tab everywhere, different internal blocks by `video_type`
- not a prose dump

#### `Mind Map`

- visual representation derived from `key_sections`
- stays universal

---

## Backend Contract

### New summary shape

The backend should move toward this contract:

```json
{
  "video_type": "tutorial",
  "key_insights": {
    "bullets": [
      "..."
    ]
  },
  "key_sections": [
    {
      "title": "...",
      "timestamp": "12:34",
      "timestamp_seconds": 754,
      "description": "...",
      "steps": [],
      "sub_points": [],
      "trade_offs": [],
      "notable_detail": ""
    }
  ],
  "deep_dive": {
    "blocks": [
      {
        "block_type": "process",
        "title": "Setup flow",
        "items": []
      }
    ]
  }
}
```

The top-level result payload remains:

```json
{
  "video_id": "...",
  "metadata": { ... },
  "summary": { ...contract above... },
  "mindmap": { ... }
}
```

### Why this contract

- smaller than the current fixed schema
- stable enough for frontend rendering and exports
- flexible enough for different video types
- avoids forcing `concepts`, `recommendations`, `comparison`, and `conclusion` onto every video

---

## JSON Schema Strategy

Use both:

- prompt for meaning and quality
- JSON schema for shape and enforcement

### Keep the schema strict at the top level

Required:

- `video_type`
- `key_insights`
- `key_sections`
- `deep_dive`

### Keep `deep_dive.blocks` controlled, not free-form

Allowed `block_type` values:

- `process`
- `argument`
- `concepts`
- `comparison`
- `timeline`
- `speakers`
- `resources`
- `action_items`
- `verdict`
- `narrative`

### Avoid overfitting phase 1

Do not create hyper-detailed per-type schemas yet. First stabilize:

- block type enum
- required `title`
- required `items`

Then harden block-level fields only after real output review.

---

## Backend Implementation Phases

### Phase 1: Introduce the new summary contract

Files:

- `backend/services/claude_service.py`
- `backend/models.py`
- `backend/main.py`

Tasks:

- add `video_type` to the emitted `summary`
- add `key_insights.bullets`
- add `deep_dive.blocks`
- keep `key_sections` unchanged
- keep `mindmap` outside `summary` as it is now

### Phase 2: Split generation into explicit stages

Current staged flow is already close. Make it explicit:

1. extract `key_sections`
2. synthesize `key_insights` from sections
3. synthesize `deep_dive` from sections + `video_type`
4. synthesize `mindmap` from sections

This keeps each stage simpler and easier to debug.

### Phase 3: Replace fixed universal fields

Deprecate these as primary outputs:

- `important_concepts`
- `practical_recommendations`
- `comparison_table`
- `conclusion`

Map them into `deep_dive.blocks` instead.

### Phase 4: Normalize and validate

- add a summary normalizer for:
  - `key_insights`
  - `deep_dive.blocks`
  - `block_type`
- keep the existing key section normalization logic
- reject or repair malformed block arrays before sending SSE/final result

### Phase 5: Add tests for the new contract

Update or add tests for:

- key-insights generation
- deep-dive block selection
- schema normalization
- partial SSE shapes
- final payload shape

---

## Prompt Refactor

### Replace the current universal summary prompt with smaller prompts

Add these prompt builders:

- `_key_insights_from_sections_user_prompt(...)`
- `_deep_dive_from_sections_user_prompt(...)`
- keep `_sections_only_user_prompt(...)`
- keep `_mindmap_from_sections_user_prompt(...)`

### Prompt requirements

#### Insights prompt

- concise
- bullet-only output
- no filler
- no repetition of full key sections
- do not mimic the old `claim + why + timestamp` pattern item by item
- every bullet should summarize a major takeaway from the whole video, not just one local moment

#### Deep Dive prompt

- choose only relevant block types for `video_type`
- return 2-4 blocks max
- prefer structure over essay-style prose
- every block must trace back to `key_sections`
- do not invent unsupported block types

---

## Frontend Implementation Phases

### Phase 1: New result mapping

File:

- `frontend/app.jsx`

Tasks:

- map `summary.video_type`
- map `summary.key_insights`
- map `summary.deep_dive`
- keep mapping `sections` from `summary.key_sections`
- stop treating old fields as the primary UI source

### Phase 2: Replace the vertical detail stack with tabs

Files:

- `frontend/panels.jsx`
- `frontend/styles.css`

Tasks:

- create a single summary workspace under the video card
- tabs:
  - `Key Sections`
  - `Insights`
  - `Deep Dive`
  - `Mind Map`
- make `Insights` active by default
- render only one tab body at a time

### Phase 3: Deep Dive block renderers

In `frontend/panels.jsx`, add small renderers for:

- `process`
- `argument`
- `concepts`
- `comparison`
- `timeline`
- `speakers`
- `resources`
- `action_items`
- `verdict`
- `narrative`

Also add a generic fallback renderer for unknown block types.

### Phase 4: Move Mind Map into the same workspace

- remove the current `Insights + Mindmap` side-by-side split
- `Mind Map` becomes one tab, not a competing panel

### Phase 5: Update exports

File:

- `frontend/exports.jsx`

Tasks:

- export `Insights`
- export `Deep Dive` by block type
- stop assuming concepts/recommendations/comparison/conclusion always exist

---

## Type-Aware Deep Dive Rules

### Tutorial / walkthrough

- `process`
- `action_items`
- `resources`

### Lecture / explainer

- `concepts`
- `argument`
- `resources`

### Opinion / essay

- `argument`
- `verdict`

### Review / comparison

- `comparison`
- `verdict`
- `action_items`

### Interview / podcast

- `speakers`
- `argument`
- `action_items`

### Documentary / investigative

- `timeline`
- `resources`
- `verdict`

### News / event explainer

- `timeline`
- `speakers`
- `verdict`

### Storytime / narrative

- `narrative`
- `action_items` only if genuinely warranted

---

## Efficiency Rules

### Code rules for this refactor

- do not create a renderer abstraction unless at least 2 tabs use it
- keep each block renderer small and local
- do not preserve legacy fields in frontend once the new contract is stable
- do not add a client-side state machine for tabs beyond a single active-tab state
- do not keep both old and new summary UIs after migration

### Runtime rules

- only render the active tab body
- do not compute mind map export markup until the `Mind Map` tab is active
- avoid re-normalizing the same summary multiple times in different components
- prefer backend normalization once, frontend rendering many times

---

## Cleanup Audit

### Removed during this pass

These were verified as dead and removed or reduced:

- unused imports in `backend/main.py`
  - `logging`
  - `re`
  - unused response-model imports
- dead response-model classes from `backend/models.py`
  - `VideoOverview`
  - `KeySection`
  - `ImportantConcept`
  - `SummaryData`
  - `MindmapNode`
  - `ResultData`
  - `SSEEventResult`
  - `SSEEventError`

These classes were no longer referenced by live code paths and reflected an outdated response shape.

### Verified still in use

Do not remove these:

- `frontend/data.jsx`
  - used for demo mode
- `frontend/hardware.jsx`
  - contains active UI primitives
- `frontend/tweaks.jsx`
  - still mounted by `App`
- `frontend/exports.jsx`
  - active export path
- `api/index.py`
  - deployment entrypoint

### Strong cleanup candidates for the refactor phase

1. Remove old fixed-summary frontend props after migration
   - `concepts`
   - `comparison`
   - `recommendations`
   - `conclusion`

2. Remove old prompt builders that only support the legacy fixed schema

3. Remove dead CSS related to the current split-panel detail layout after tabs land

4. Delete stale docs for removed screenshot/clip pipelines if they are no longer serving as internal references

### Items not removed yet because they need verification during refactor

- `depthKnob` state in `frontend/app.jsx`
  - currently UI-only, may be intentional product chrome
- portfolio demo edit/tweak mode
  - not dead, but optional product surface
- `main.py` `state === "done"` semantics in frontend flow
  - harmless now, but should be simplified if the tab workspace replaces the current staged layout

---

## Execution Order

1. finalize the new summary JSON contract
2. add backend schema + normalizer
3. generate `key_insights`
4. generate `deep_dive`
5. keep `key_sections` and `mindmap` stable
6. migrate frontend to tabs
7. migrate exports
8. delete old fixed-summary rendering paths
9. delete legacy prompt/schema code
10. run targeted tests and manual video checks

---

## Success Criteria

- all videos render exactly four universal tabs
- `Insights` renders by default
- `Insights` is concise, bullet-based, and non-duplicative
- `Deep Dive` changes shape according to `video_type`
- `Mind Map` still works and exports correctly
- frontend no longer depends on old fixed fields as primary UI inputs
- dead code removed as the new flow lands
- no duplicate UI systems for the same summary content
