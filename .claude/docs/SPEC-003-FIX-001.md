# SPEC-003-FIX-001 — Quote Type Classification (Headline / Substantive)

## System

SPEC_LOCKED. Behavioural contract — execute it, do not interpret around it.
Amends: SPEC-ai-audio-editor-phase2-20260714 (Spec 3). All anchors from that spec apply here unless explicitly overridden.
Read-only without explicit user approval: Schemas, Algorithm, Forbidden.
Update Change Protocol during session. Update Session State at session end.
Reference ADR-001-QUOTE-TYPE.md for the rationale behind classification design decisions.

## Intent

Spec 3 produces flat `Quote` rows with a single `quote_text` blob. This fix adds a `quote_type` field that classifies each quote as either `headline` or `substantive`:

- **Headline** — self-contained, punchy, front-cover worthy. Can stand alone without surrounding context. Typically ≤ 25 words.
- **Substantive** — longer, contextually rich. Suitable for embedding in a video or article body where surrounding narrative provides framing.

Classification is performed by Qwen at extraction time (alongside the existing segment ID range output), because the model has full narrative context and conversational framing to judge whether a passage is standalone-punchy or context-dependent. See ADR-001-QUOTE-TYPE.md for the full rationale and rejected alternatives.

The `quote_type` field is added to both `QuoteCandidate` (raw per-chunk output) and `Quote` (promoted, deduplicated record). Dedup merge conflict resolution follows the canonical candidate's type. The review UI gains type badges and a type filter. No new model, no new GPU allocation, no second Qwen call.

## Meta

```xml
<meta>
  <project>InterScribe</project>
  <tier>small</tier>
  <amends>SPEC-ai-audio-editor-phase2-20260714</amends>
  <hard_constraints>
    <constraint>quote_type is output by Qwen as a label alongside start_segment_id/end_segment_id — Qwen still never outputs quote text or timestamps; a classification label is not quote content</constraint>
    <constraint>If Qwen omits quote_type or returns an unrecognised value, the candidate defaults to "substantive" — never discarded solely due to a missing type field</constraint>
    <constraint>Schema change via Alembic migration only — migration 007 adds quote_type to both quote_candidates and quotes tables</constraint>
    <constraint>No second Qwen call for type determination — classification happens in the same extraction call as the segment ID range</constraint>
    <constraint>No rule-based word-count fallback replaces Qwen's judgment — the default-to-substantive rule applies only when Qwen's output is structurally absent or invalid, not as a parallel classifier</constraint>
    <constraint>Dedup merge conflict (two candidates with different types): the canonical candidate's type (highest narrative_alignment_score) is used — no additional logic needed</constraint>
    <constraint>Existing Quote rows (migration 007 backfill): set to "substantive" — conservative default preserves existing data without requiring re-extraction</constraint>
    <constraint>No auto-rejection of any quote based on type — type is informational, filtering at query time only</constraint>
  </hard_constraints>
</meta>
```

## Algorithm

```xml
<algorithm id="QUOTE_TYPE_EXTRACTION">
  Context: Runs inside the existing _call_qwen / _validate_candidates flow in extraction.py.
  No new Qwen call — quote_type is added to the existing per-candidate JSON output.

  Step 1: Update _USER_TEMPLATE to require "type": "headline" | "substantive" in each candidate object.
          Definitions injected into the prompt (see Prompt Amendment below).

  Step 2: _validate_candidates parses "type" from each raw Qwen item:
    - If present and value is "headline" or "substantive" → use as-is
    - If absent, null, or unrecognised value → default to "substantive"
    - Validation failure on start/end segment IDs still discards the candidate regardless of type

  Step 3: quote_type flows through into QuoteCandidate rows (stored as-is from step 2).

  Step 4: run_dedup_and_promote: canonical candidate's quote_type copied to the promoted Quote row.
          No merge-conflict resolution needed beyond picking the canonical candidate.

  Step 5: GET /api/videos/{id}/phase2/quotes: quote_type returned in each Quote object.
          Optional query param "type" filters to "headline" | "substantive" when provided.
</algorithm>
```

## Prompt Amendment

The following change is made to `_USER_TEMPLATE` in `extraction.py`. The rules block gains one line and the required object shape gains one field:

**Before:**
```
Return a JSON array of quote candidates. Each object must have exactly:
- "start_segment_id": int (a segment ID shown in brackets in the transcript above)
- "end_segment_id": int (a segment ID shown in brackets in the transcript above)

Rules:
- All segment IDs must fall within a single continuous speaker run
- Prefer passages that are insightful, surprising, quotable, or strongly tied to the themes above
- Aim for 3-8 candidates. Return [] if no strong candidates exist.
- Do NOT include any quote text — segment IDs only.
```

**After:**
```
Return a JSON array of quote candidates. Each object must have exactly:
- "start_segment_id": int (a segment ID shown in brackets in the transcript above)
- "end_segment_id": int (a segment ID shown in brackets in the transcript above)
- "type": "headline" | "substantive"
    headline = self-contained, punchy, ≤~25 words, could appear on a front cover or social post
    substantive = longer, contextually rich, requires surrounding narrative, suitable for embedding in an article or video

Rules:
- All segment IDs must fall within a single continuous speaker run
- Prefer passages that are insightful, surprising, quotable, or strongly tied to the themes above
- Aim for 3-8 candidates. Return [] if no strong candidates exist.
- Do NOT include any quote text — segment IDs only.
```

## Schemas

**Schema amendment — `QuoteCandidate` (adds one field):**

```xml
<model name="QuoteCandidate" amends="SPEC-ai-audio-editor-phase2-20260714">
  <!-- All existing fields unchanged -->
  <field name="quote_type" type="string" nullable="false" default="substantive"
         notes="'headline' or 'substantive'. Set from Qwen output; defaults to 'substantive' if absent or unrecognised."/>
</model>
```

**Schema amendment — `Quote` (adds one field):**

```xml
<model name="Quote" amends="SPEC-ai-audio-editor-phase2-20260714">
  <!-- All existing fields unchanged -->
  <field name="quote_type" type="string" nullable="false" default="substantive"
         notes="Copied from canonical QuoteCandidate during dedup promotion. 'headline' or 'substantive'."/>
</model>
```

**Migration 007:** Adds `quote_type VARCHAR NOT NULL DEFAULT 'substantive'` to both `quote_candidates` and `quotes` tables. Existing rows backfill to `'substantive'`.

**API amendment — GET /api/videos/{id}/phase2/quotes:**

```xml
<api endpoint="/api/videos/{id}/phase2/quotes" method="GET" amends="SPEC-ai-audio-editor-phase2-20260714">
  <request>
    query params: view ("notable"|"top"), limit (integer, optional, default null = all),
                  type ("headline"|"substantive", optional, default null = both)
  </request>
  <response>{ quotes: Quote[] }</response>
  <!-- Quote response shape gains: quote_type: "headline" | "substantive" -->
  <!-- All other request/response/error behaviour unchanged -->
</api>
```

## Anchors Inherited

| Anchor ID | From | How applied here |
|-----------|------|-----------------|
| `QUOTE_GROUNDING` | SPEC-003 | `quote_type` is a Qwen-output label, not quote text or a timestamp — constraint not violated |
| `QUOTE_DEDUP` | SPEC-003 | Canonical candidate selection unchanged; `quote_type` copied from canonical |
| `NAMING_CONVENTION` | SPEC-003 | `quote_type` (snake_case Python/Postgres), `quoteType` (camelCase TypeScript) |
| `ERROR_PATTERN` | SPEC-003 | No new error codes introduced |

## Preconditions

**qwen_returns_quote_type**
- Given: a Phase2Chunk being processed, _USER_TEMPLATE includes the updated type field definition
- When: Qwen returns candidate objects
- Then: each valid candidate object includes `"type": "headline"` or `"type": "substantive"`; `QuoteCandidate.quote_type` is set accordingly

**missing_type_defaults_to_substantive**
- Given: a Qwen candidate object that is structurally valid (valid start/end segment IDs) but has no `"type"` key, a null value, or an unrecognised string
- When: `_validate_candidates` processes it
- Then: the candidate is retained with `quote_type = "substantive"`; it is not discarded

**dedup_copies_canonical_type**
- Given: two QuoteCandidates from overlapping chunks that pass the merge threshold, one with `quote_type = "headline"` and one with `quote_type = "substantive"`, the headline candidate having the higher `narrative_alignment_score`
- When: `run_dedup_and_promote` runs
- Then: the promoted `Quote` row has `quote_type = "headline"` (canonical candidate's type)

**type_filter_applied_at_query_time**
- Given: a video at phase2_ready_for_review with 10 Quote rows, 3 of which are `quote_type = "headline"` and 7 are `"substantive"`
- When: GET .../phase2/quotes?view=top&type=headline is called
- Then: only the 3 headline quotes are returned
- When: GET .../phase2/quotes?view=top is called (no type param)
- Then: all 10 quotes are returned

**review_ui_shows_type_badge**
- Given: a Quote with `quote_type = "headline"` rendered in the Phase 2 review UI
- When: the QuoteCard renders
- Then: a "Headline" badge is visible, visually distinct from "Substantive"; both types may appear on the same page simultaneously

**existing_rows_backfilled_substantive**
- Given: Quote or QuoteCandidate rows existing in the DB before migration 007 runs
- When: migration 007 applies
- Then: all existing rows have `quote_type = 'substantive'`; no rows are dropped or modified beyond this field

## Execution Gate

```xml
<execution_gates>
  <gate id="1" milestone="quote_type persisted on QuoteCandidate and Quote rows; Qwen prompt updated; missing/invalid type defaults to substantive; dedup copies canonical type; GET quotes type filter works; UI badges render">
    <command lang="python">pytest tests/phase2/extraction/ tests/phase2/dedup/ tests/phase2/review/ -v</command>
    <command lang="typescript">vitest run phase2-review-ui.test.ts</command>
    <must_pass>true</must_pass>
    <on_failure>Stop. Log to deviations. State what failed and why. Wait for input.</on_failure>
  </gate>
</execution_gates>
```

**Test coverage required (additive — extend existing test files, do not replace):**

`tests/phase2/extraction/test_extraction.py`:
- Qwen returns `"type": "headline"` → `QuoteCandidate.quote_type == "headline"`
- Qwen returns `"type": "substantive"` → `QuoteCandidate.quote_type == "substantive"`
- Qwen omits `"type"` key entirely → `QuoteCandidate.quote_type == "substantive"` (default)
- Qwen returns `"type": "invalid_value"` → `QuoteCandidate.quote_type == "substantive"` (default)

`tests/phase2/dedup/test_dedup.py`:
- Two candidates, both `"headline"` → promoted Quote is `"headline"`
- Two candidates, both `"substantive"` → promoted Quote is `"substantive"`
- Two candidates, mixed types, headline has higher score → promoted Quote is `"headline"`
- Two candidates, mixed types, substantive has higher score → promoted Quote is `"substantive"`

`tests/phase2/review/test_review.py`:
- GET quotes?view=top&type=headline returns only headline quotes
- GET quotes?view=top&type=substantive returns only substantive quotes
- GET quotes?view=top (no type param) returns all quotes
- GET quotes?view=notable&type=headline returns only notable headline quotes

`phase2-review-ui.test.ts`:
- QuoteCard with `quoteType: "headline"` renders a "Headline" badge
- QuoteCard with `quoteType: "substantive"` renders a "Substantive" badge
- Both badge types are visually distinguishable (distinct test-id or className)

## Forbidden

- No second Qwen call to determine quote type
- No discarding a candidate solely because `quote_type` is missing or unrecognised — default to `"substantive"`
- No word-count rule used as a parallel or fallback classifier (only as context in the Qwen prompt definition)
- No merging of `quote_type` into `narrative_alignment_score` or any other existing field
- No hardcoded filtering of quote type at generation time — all types persisted, filter at query time only

## Change Protocol

```xml
<change_protocol>
  <decisions>
    <!-- Log medium-confidence decisions here during implementation -->
  </decisions>
  <deviations>
    <!-- <deviation id="DEV1" section="[section]" approved="pending">[what, why, impact]</deviation> -->
  </deviations>
</change_protocol>
```

## Session State

```xml
<session_state>
  <last_completed_gate>1</last_completed_gate>
  <current_milestone>Gate 1 passed 2026-07-19. 71 backend tests (14 new) + 17 frontend tests (4 new) all green. Migration 007 written. Also fixed pre-existing router bug: view param changed from Query(...) to Query(None) so missing view returns 400/INVALID_VIEW instead of 422.</current_milestone>
  <open_questions/>
  <context_carry>
    Amends SPEC-003 only. No impact on SPEC-001 (transcription), SPEC-002 (Phase 1 narrative), or SPEC-001-FIX-001 (repetition detector).
    Migration 007 adds quote_type VARCHAR NOT NULL DEFAULT 'substantive' to quote_candidates and quotes.
    The prior migration is 006_drop_project_id.py — next is 007_quote_type.py.
    Implementation order: migration 007 → model fields → _validate_candidates → dedup.py → phase2 router (type filter) → frontend types → QuoteCard badge → tests.
    ADR-001-QUOTE-TYPE.md (same docs directory) documents the design rationale in full.
  </context_carry>
</session_state>
```
