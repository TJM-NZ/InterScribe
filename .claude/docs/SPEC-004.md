# SPEC-ai-audio-editor-condensation-20260719

## System

SPEC_LOCKED. This file is a behavioural contract — execute it, do not interpret around it.
Read-only (never modify without explicit user approval): Schemas, Forbidden.
Requires approval before acting: any deviation touching Schemas or hard constraints.
Update Change Protocol during session. Update Session State at session end — mandatory.
Reference Anchors by ID in all decision and deviation logs.

Builds directly on SPEC-ai-audio-editor-phase2-20260714 (spec 3). `Video`, `TranscriptSegment`, `SpeakerRoleMap`, `TranscriptTurn`, `NarrativeCluster`, `NotableMoment`, `Phase2Chunk`, `QuoteCandidate`, and `Quote` are existing, immutable-in-this-spec context — extend, never redefine them.

## Intent

Spec 4 of 5. Covers the headline condensation gate: a new review stage that runs after Phase 2 quote review (phase2_reviewed). For each approved headline-type Quote, Qwen3.5:9b receives the verbatim quote_text (assembled deterministically from segments in spec 3) and condenses it to ≤20 words. A new review gate (Review Gate 3) lets the user approve or edit each condensed headline before finalising.

The core separation of concerns: spec 3 identifies *which passages* to quote (grounded to segment IDs, filtered to interviewee-only); spec 4 distils the approved passages into *final headline form*. The verbatim quote_text is never modified — headline_text is an additive field.

Same constraints: self-hosted, single machine, RTX 1080Ti, overnight/unattended batch processing acceptable, single-command Docker deployability preserved. Correction logging continues here (entity_type "headline_condensation").

## Meta

```xml
<meta>
  <project>InterScribe</project>
  <tier>medium</tier>
  <stack>
    <backend>Python (FastAPI), same service as specs 1-3</backend>
    <frontend>Next.js (React), same service as specs 1-3</frontend>
    <database>PostgreSQL, same instance, extended via migration</database>
    <other>Qwen3.5:9b, same local deployment as specs 2-3. No new models. Condensation is a text-in/text-out task — Qwen receives the full verbatim quote text and outputs condensed prose directly (unlike spec 3 where Qwen output segment ID ranges only).</other>
  </stack>
  <hard_constraints>
    <constraint>Only headline-type Quote rows are condensed — substantive quotes are never passed to Qwen in this spec and headline_text is never set on them</constraint>
    <constraint>quote_text is never modified — it remains the verbatim segment-assembled text from spec 3 for all time; headline_text is strictly additive</constraint>
    <constraint>headline_text must be ≤20 words after condensation — if Qwen returns more than 20 words, truncate to the first 20 words with a warning log; never discard the candidate on length alone</constraint>
    <constraint>Condensation runs exactly once per headline Quote; it is not re-run after user corrections — corrections update headline_text directly via the review UI</constraint>
    <constraint>If a video has no headline-type Quote rows at phase2_reviewed, the condensation stage is skipped and status auto-transitions to condensation_reviewed immediately — no worker run</constraint>
    <constraint>Every edit at Review Gate 3 writes a Correction row with entity_type "headline_condensation" and a reason_category — same Correction table as specs 2-3</constraint>
    <constraint>Qwen condensation calls include the top-N NarrativeCluster representative_labels as context anchors so the condensed headline stays thematically grounded</constraint>
    <constraint>No Qwen call uses the raw segment IDs or transcript structure in this spec — input is only the quote_text string and narrative context</constraint>
  </hard_constraints>
  <soft_defaults>
    <default id="D1" anchor="CONDENSATION_PROMPT" resolved="true">Condensation target: ≤20 words. Qwen instructed to preserve the speaker's voice and the core insight. Narrative cluster labels included as context so the condensation stays thematically grounded. System prompt enforces "return ONLY the condensed text, no explanation, no quotation marks".</default>
    <default id="D2" anchor="CONDENSATION_WORKER" resolved="true">Condensation processes one headline Quote at a time (sequential, not batched) to stay within Qwen's context window and simplify retry logic. Retry on failure: same settings.narrative_chunk_retries pattern as specs 2-3 (default: 3 attempts, exponential backoff).</default>
    <default id="D3" anchor="SKIP_IF_EMPTY" resolved="true">If video has zero headline-type Quote rows at phase2_reviewed, auto-transition condensation_queued → condensation_reviewed at enqueue time — no worker job created. This keeps the status flow consistent without a no-op worker run.</default>
  </soft_defaults>
</meta>
```

## Decision Policy

| Confidence | Action |
|---|---|
| High | Proceed. Log nothing. |
| Medium | Proceed. Log decision and reasoning to Change Protocol. |
| Low | Stop. State ambiguity and options. Wait for user input. |

## Forbidden

- No modification of quote_text — it is the immutable verbatim record
- No condensation of substantive-type quotes — headline_text must be null on all substantive rows
- No second condensation pass after user corrections — corrections write directly to headline_text via the review endpoint
- No Qwen call that receives segment IDs, timestamps, or raw transcript structure — condensation input is quote_text + narrative context labels only
- No Review Gate 3 correction without a reason_category
- No mutation of Phase 1 or Phase 2 entities (NarrativeCluster, NotableMoment, Phase2Chunk, QuoteCandidate) from this spec
- No hardcoded word limit enforcement beyond truncation — never discard a headline quote because Qwen overshot; truncate and log

## Anchors

```xml
<anchors>
  <anchor id="JOB_STATUS" extends="spec3:JOB_STATUS">Extends spec 3's progression. After "phase2_reviewed": phase2_reviewed → condensation_queued → condensation_processing → condensation_ready_for_review → condensation_reviewed. Any failure transitions to failed with error_reason populated. No skipping states. Auto-enqueue: POST /phase2/confirm-review (spec 3) now transitions the DB to condensation_queued immediately as a side effect — same pattern as specs 1 and 3. The response body still returns "phase2_reviewed"; the DB status is condensation_queued. Exception: if no headline Quote rows exist, condensation_queued immediately auto-transitions to condensation_reviewed (see D3).</anchor>
  <anchor id="CONDENSATION_PROMPT">Qwen receives: (a) the full verbatim quote_text string, (b) the top-N NarrativeCluster representative_labels as thematic anchors. Qwen outputs: a single condensed string ≤20 words — no JSON wrapper, no segment IDs, no timestamps, no quotation marks, no explanation. System prompt: "You are an expert at distilling interview quotes into punchy, memorable headlines. Return ONLY the condensed text." User prompt format: narrative context block + "Condense this quote to 20 words or fewer, preserving the speaker's voice:\n\n{quote_text}"</anchor>
  <anchor id="CONDENSATION_WORKER">The condensation worker polls for videos at condensation_queued. For each: load all headline Quote rows for the video → call Qwen once per quote → store headline_text (truncated to 20 words if needed) → after all quotes processed, transition to condensation_ready_for_review. Retry-per-quote: up to narrative_chunk_retries attempts. If any quote exhausts retries, transition to failed with error_reason. Substantive quotes are not loaded, not passed to Qwen, headline_text stays null.</anchor>
  <anchor id="REVIEW_GATE_3">Review Gate 3 UI at /videos/[id]/condensation/. Shows each headline Quote as a card: verbatim quote_text (full, read-only context), headline_text (editable inline, word count indicator). User can: edit headline_text (writes Correction row on save), reject the headline designation (downgrades quote_type to "substantive" via Correction row, clears headline_text). Confirm-review button transitions to condensation_reviewed. Substantive quotes are not shown in this gate.</anchor>
  <anchor id="NAMING_CONVENTION" extends="spec3:NAMING_CONVENTION">snake_case Python, camelCase TypeScript, kebab-case files, snake_case Postgres columns/tables.</anchor>
  <anchor id="ERROR_PATTERN" extends="spec3:ERROR_PATTERN">{ error: string, code: string, trace_id: uuid } — never includes filesystem paths or stack traces.</anchor>
</anchors>
```

## Schemas

```xml
<schemas>
  <model name="Quote" extends="spec3:Quote">
    <field name="headline_text" type="string" nullable="true" notes="Qwen-condensed headline ≤20 words. Null for substantive quotes and for headline quotes that have not yet been condensed. Never set by spec 3 — this field is additive in spec 4 only."/>
  </model>

  <api endpoint="/api/videos/{id}/condensation/headlines" method="GET">
    <request>no params</request>
    <response>{ quotes: Quote[] } — only headline-type quotes, ordered by narrative_alignment_score desc</response>
    <errors>
      <error code="404" reason="video id does not exist"/>
      <error code="409" reason="status earlier than condensation_ready_for_review"/>
    </errors>
  </api>

  <api endpoint="/api/videos/{id}/condensation/corrections" method="POST">
    <request>{ entity_type: "headline_condensation", entity_id: uuid, field_name: string|null, original_value: any, corrected_value: any|null, reason_category: enum, reason_note: string|null }</request>
    <response>{ correction_id: uuid }</response>
    <errors>
      <error code="400" reason="reason_category missing or invalid, or entity_id does not belong to this video or is not a headline quote"/>
      <error code="404" reason="video id does not exist"/>
    </errors>
  </api>

  <api endpoint="/api/videos/{id}/condensation/confirm-review" method="POST">
    <request>none</request>
    <response>{ video_id: uuid, status: "condensation_reviewed" }</response>
    <errors>
      <error code="404" reason="video id does not exist"/>
      <error code="409" reason="status is not condensation_ready_for_review"/>
    </errors>
  </api>
</schemas>
```

## Preconditions

**phase2_confirm_review_enqueues_condensation**
- Given: a Video with status "phase2_ready_for_review"
- When: POST /phase2/confirm-review is called
- Then: status transitions phase2_reviewed → condensation_queued in the DB; response body returns "phase2_reviewed" (same pattern as prior specs)

**no_headline_quotes_skips_condensation**
- Given: a Video that just entered condensation_queued with zero headline-type Quote rows
- When: the worker or enqueue side-effect detects this
- Then: status immediately transitions condensation_queued → condensation_reviewed; no worker job is created

**headline_quote_condensed_and_stored**
- Given: a Video at condensation_queued with one or more headline-type Quote rows
- When: the condensation worker runs
- Then: for each headline Quote, headline_text is set to Qwen's condensation (≤20 words, truncated with warning if Qwen overshot); substantive Quote rows are untouched; status transitions to condensation_ready_for_review after all headlines processed

**headline_text_truncated_not_discarded**
- Given: a headline Quote where Qwen returns 24 words
- When: the condensation worker processes it
- Then: headline_text is set to the first 20 words of Qwen's output; a warning is logged; the Quote row is not discarded or downgraded

**review_gate_3_shows_only_headline_quotes**
- Given: a video at condensation_ready_for_review with 12 Quote rows (4 headline, 8 substantive)
- When: GET .../condensation/headlines is called
- Then: exactly the 4 headline quotes are returned with headline_text populated

**headline_edit_writes_correction**
- Given: a video at condensation_ready_for_review, user edits headline_text inline
- When: the edit is saved
- Then: POST .../condensation/corrections is called with entity_type "headline_condensation", field_name "headline_text", original_value (prior headline_text), corrected_value (new text), and a reason_category; a Correction row is created; headline_text is updated on the Quote row

**headline_downgrade_writes_correction**
- Given: a video at condensation_ready_for_review, user rejects the headline designation for a quote
- When: the rejection is submitted
- Then: POST .../condensation/corrections is called with field_name "quote_type", original_value "headline", corrected_value "substantive", and a reason_category; Quote.quote_type is updated to "substantive" and Quote.headline_text set to null

**confirm_review_transitions_status**
- Given: a video at condensation_ready_for_review
- When: POST .../condensation/confirm-review is called
- Then: status transitions to condensation_reviewed; further edits against this condensation output return 409

## Execution Gates

```xml
<execution_gates>
  <gate id="1" milestone="Condensation worker: headline Quote rows processed by Qwen, headline_text stored (≤20 words, truncated if needed), status transitions condensation_queued → condensation_ready_for_review; zero-headline skip path transitions directly to condensation_reviewed">
    <command lang="python">pytest tests/condensation/worker/ -v</command>
    <must_pass>true</must_pass>
    <on_failure>Stop. Log to deviations. State what failed and why. Wait for input.</on_failure>
  </gate>
  <gate id="2" milestone="Review Gate 3 UI complete: /videos/[id]/condensation/ shows headline quotes with verbatim + condensed view, inline edit, downgrade to substantive, confirm-review flow">
    <command lang="typescript">vitest run condensation-review-ui.test.ts</command>
    <command lang="python">pytest tests/condensation/review/ -v</command>
    <must_pass>true</must_pass>
    <on_failure>Stop. Log to deviations. State what failed and why. Wait for input.</on_failure>
  </gate>
  <gate id="3" milestone="Full stack still deployable via single docker-compose command with spec-4 migration applied">
    <command lang="bash">docker-compose up --build -d && curl -f http://localhost:8000/health</command>
    <must_pass>true</must_pass>
    <on_failure>Stop. Log to deviations. State what failed and why. Wait for input.</on_failure>
  </gate>
</execution_gates>
```

## Pre-Implementation Notes

- **Migration**: add `headline_text TEXT` (nullable) to the `quotes` table. No other schema changes.
- **Worker integration**: condensation worker runs as a new poll loop alongside the existing phase1/phase2 workers in the same worker service — no new Docker service needed.
- **Spec 3 amendment required**: POST /phase2/confirm-review must be updated to auto-enqueue condensation_queued (same side-effect pattern as specs 1 and 3). Update the existing test `test_confirm_review_transitions_to_phase2_reviewed` to assert DB status is condensation_queued post-commit.
- **VideoStatus enum**: add `condensation_queued`, `condensation_processing`, `condensation_ready_for_review`, `condensation_reviewed` to the TypeScript VideoStatus union and Python JobStatus enum.
- **VideoList link**: add navigation link for condensation_ready_for_review status on the video list page (same pattern as phase1/phase2 review links).
- **Reviewable set**: the transcript GET endpoint's reviewable set must include all four condensation statuses so the transcript page remains accessible.

## Change Protocol

```xml
<change_protocol>
  <decisions>
    <decision id="D1" anchor="CONDENSATION_PROMPT" confidence="medium">Condensation target set at ≤20 words (user requirement). Qwen instructed to preserve the speaker's voice — avoids generic paraphrase. Narrative cluster labels included as context to bias the condensed headline toward the video's dominant themes rather than producing a generic sentence.</decision>
    <decision id="D2" anchor="CONDENSATION_WORKER" confidence="high">Sequential per-quote processing (not batched) keeps each Qwen call small and focused, simplifies retry isolation, and avoids context-window pressure. Interview sessions rarely have more than ~10 headline candidates so sequential cost is acceptable.</decision>
    <decision id="D3" anchor="SKIP_IF_EMPTY" confidence="high">Zero-headline auto-skip avoids a no-op worker run and keeps the status flow clean. condensation_reviewed is still reached so downstream spec 5 can unconditionally query for condensation_reviewed without a special-case branch.</decision>
  </decisions>
  <deviations>
    <!-- <deviation id="DEV1" section="[section]" approved="pending">[what, why, impact]</deviation> -->
  </deviations>
  <amendments_pending>
    <!-- <amendment id="A1" targets="[section]">[proposed change — add at session end]</amendment> -->
  </amendments_pending>
</change_protocol>
```

## Session State

```xml
<session_state>
  <last_completed_gate>3</last_completed_gate>
  <current_milestone>All 3 gates passed (2026-07-19). Implementation complete.</current_milestone>
  <open_questions>
    <!-- none -->
  </open_questions>
  <context_carry>
    This is spec 4 of 5 in the autonomous AI audio/video editor project (spec 1: upload/transcription/speaker review; spec 2: Phase 1 narrative extraction; spec 3: Phase 2 quote search; this spec: headline condensation gate; spec 5: correction/learning loop + UI/UX polish).

    The key architectural distinction: spec 3 uses Qwen to identify segment ID ranges (Qwen never generates text); spec 4 uses Qwen to generate condensed prose from approved verbatim text. These are different Qwen tasks with different prompts and different output types. Both run in the same Ollama service.

    quote_text (spec 3) is immutable and verbatim — it is the audit anchor. headline_text (spec 4) is the user-facing distillation. Never conflate them. The Quote row always carries both after spec 4.

    headline_text null on a headline-type Quote is a valid in-progress state (condensation not yet run). headline_text null on a substantive-type Quote is the permanent state (intentional, not a bug).

    Correction rows for this spec use entity_type "headline_condensation" to distinguish them from spec 3's "quote" corrections. Spec 5's correction/learning loop must handle all three entity_types: "narrative_cluster", "quote", "headline_condensation".

    Implementation order: add condensation statuses to JobStatus enum + VideoStatus TypeScript union → add headline_text migration → update POST /phase2/confirm-review to auto-enqueue condensation_queued → add zero-headline skip logic → write condensation worker → write condensation router (GET headlines, POST corrections, POST confirm-review) → update worker runner poll loop → write tests (Gate 1) → write Review Gate 3 frontend → write frontend tests (Gate 2) → Gate 3 deployability check.
  </context_carry>
</session_state>
```

```xml
<skipped_sections tier="medium">
  <section name="dependencies" reason="Linear build order within this spec; cross-spec dependency on specs 1-3 is stated in Intent/System"/>
  <section name="thinking_budget" reason="Standard reasoning depth sufficient throughout"/>
</skipped_sections>
```
