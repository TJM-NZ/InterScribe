# SPEC-ai-audio-editor-phase2-20260714

## System

SPEC_LOCKED. This file is a behavioural contract — execute it, do not interpret around it.
Read-only (never modify without explicit user approval): Schemas, Forbidden.
Requires approval before acting: any deviation touching Schemas or hard constraints.
Update Change Protocol during session. Update Session State at session end — mandatory.
Reference Anchors by ID in all decision and deviation logs.

Builds directly on SPEC-ai-audio-editor-20260714 (spec 1) and SPEC-ai-audio-editor-phase1-20260714 (spec 2). `Video`, `TranscriptSegment`, `SpeakerRoleMap`, `TranscriptTurn`, `NarrativeCluster`, and `NotableMoment` are existing, immutable-in-this-spec context — extend, never redefine them.

## Intent

Spec 3 of 5. Covers Phase 2: quote search over the transcript, grounded to segment IDs, filtered to interviewee-only content, scored against the Phase 1 narrative ranking and notable moments, and the extended review UI (Review Gate 2) that adds a top-N quotes track alongside the existing notable-moments track from spec 2.

Same constraints as specs 1 and 2: self-hosted, single machine, RTX 1080Ti (~11GB VRAM), overnight/unattended batch processing acceptable, single-command Docker deployability preserved. Correction logging continues here (entity_type extends to include "quote"); retrieval/few-shot learning over corrections remains out of scope until spec 4.

## Meta

```xml
<meta>
  <project>InterScribe</project>
  <tier>medium</tier>
  <stack>
    <backend>Python (FastAPI), same service as specs 1-2</backend>
    <frontend>Next.js (React), same service as specs 1-2</frontend>
    <database>PostgreSQL, same instance, extended via migration</database>
    <other>Qwen3.5:9b, same local deployment as spec 2. No new embedding models introduced in this spec. MiniLM all-MiniLM-L6-v2 (already loaded for spec 2 clustering) reused for narrative_alignment_score computation — no new model pulls.</other>
  </stack>
  <hard_constraints>
    <constraint>Qwen never outputs quote text or timestamps directly — it references TranscriptTurn/segment ID ranges only; quote_text, start_ts, and end_ts are always derived deterministically from stored TranscriptSegment data in a post-processing step, never model-generated</constraint>
    <constraint>A quote candidate is rejected if its referenced segment ID range spans more than one speaker_label, or if the speaker's role (per SpeakerRoleMap) is not "interviewee" — quotes are interviewee-only regardless of what context Qwen was shown</constraint>
    <constraint>Every Phase 2 chunk prompt includes the full transcript context needed to interpret speaker exchanges (interviewer questions are visible to Qwen for context), even though only interviewee segments are eligible to become quote candidates</constraint>
    <constraint>Phase 2 chunk text is built from TranscriptTurn rows (reusing spec 2's turn-grouping), never raw TranscriptSegment text and never reimplemented turn-grouping logic</constraint>
    <constraint>Phase 2 chunk boundaries overlap by a configurable window defined in whole turns (not raw seconds or segments), so a turn is never split by the overlap</constraint>
    <constraint>narrative_alignment_score and is_notable_moment are stored and returned as separate fields — never combined into one score</constraint>
    <constraint>No fixed top-N is applied at generation time — all scored candidates are persisted; top-N/filtering is applied only at query time (presentation layer)</constraint>
    <constraint>Boundary deduplication of overlapping quote candidates is rule-based (segment-range overlap + text similarity), never a second LLM call</constraint>
    <constraint>Every edit or rejection at Review Gate 2 writes a Correction row (entity_type "quote") with a reason_category, same pattern as spec 2</constraint>
    <constraint>narrative_alignment_score is computed deterministically post-hoc from stored ChunkTheme.theme_embedding vectors — Qwen does not generate or output a score</constraint>
    <constraint>is_notable_moment is derived rule-based from segment range overlap with NotableMoment rows — Qwen does not output a boolean flag for this field</constraint>
  </hard_constraints>
  <soft_defaults>
    <default id="D1" anchor="PHASE2_CHUNK" resolved="true">Overlap window = 2 whole turns per boundary (last 2 turns of one chunk repeated as the first 2 turns of the next). Configurable via PHASE2_OVERLAP_TURNS env var.</default>
    <default id="D2" anchor="QUOTE_DEDUP" resolved="true">Rule-based merge: segment range overlap ratio > 0.5 AND difflib.SequenceMatcher text similarity ratio > 0.85. Both thresholds configurable via PHASE2_DEDUP_OVERLAP_RATIO and PHASE2_DEDUP_TEXT_SIMILARITY env vars.</default>
    <default id="D3" anchor="QUOTE_GROUNDING" resolved="true">narrative_alignment_score scale: 0.0–1.0 float. Computed as max cosine similarity between the quote text embedding (MiniLM) and all ChunkTheme.theme_embedding vectors belonging to the top-N NarrativeClusters (by rank). Clipped to [0.0, 1.0]. Consistent with spec 4/5 scoring expectations.</default>
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

- No quote text or timestamps generated/echoed by Qwen — segment ID range references only, text/timestamps resolved deterministically afterward
- No quote candidate crossing more than one speaker_label
- No quote candidate whose speaker's role is not "interviewee"
- No stripping interviewer segments out of the transcript context shown to Qwen — full conversational context stays visible, only the *output* is filtered
- No reimplementing turn-grouping logic in this spec — reuse spec 2's TranscriptTurn table as-is
- No raw-segment or raw-second-based overlap windows — overlap must be defined in whole turns
- No collapsing narrative_alignment_score and is_notable_moment into a single field
- No hardcoded top-N at generation time — over-generate, filter at query time only
- No LLM-based merge/dedup pass for boundary duplicates — rule-based only
- No Review Gate 2 correction submission without a reason_category
- No mutation of Phase 1 entities (NarrativeCluster, NotableMoment) from this spec

## Anchors

```xml
<anchors>
  <anchor id="JOB_STATUS" extends="spec2:JOB_STATUS">Extends spec 2's progression. After "phase1_reviewed": phase1_reviewed → phase2_queued → phase2_processing → phase2_ready_for_review → phase2_reviewed. Any failure transitions to failed with error_reason populated. No skipping states. Auto-enqueue: POST /phase1/confirm-review transitions phase1_reviewed → phase2_queued immediately as a side effect (same pattern as spec 1's reviewed → phase1_queued). The response body returns "phase1_reviewed" (what was confirmed); the DB status is phase2_queued.</anchor>
  <anchor id="PHASE2_CHUNK">A Phase 2 chunk, like a Phase 1 chunk, is built from whole TranscriptTurn rows sized to ~10,000 tokens — but unlike Phase 1 chunks, adjacent Phase 2 chunks overlap by PHASE2_OVERLAP_TURNS whole turns at each boundary (default: 2), so a quote near a boundary is fully visible to at least one chunk's Qwen call without being split.</anchor>
  <anchor id="QUOTE_GROUNDING" extends="spec1:SEGMENT_SCHEMA">Qwen returns a start_segment_id/end_segment_id range per candidate quote (never free text or timestamps). Validity check: the range must resolve to segments belonging to exactly one speaker_label, and that speaker's role in SpeakerRoleMap must be "interviewee" — otherwise the candidate is discarded before storage. quote_text is the concatenation of the referenced segments' text in order; start_ts/end_ts are copied from the first/last segment in the range. narrative_alignment_score = max cosine similarity between MiniLM embedding of quote_text and ChunkTheme.theme_embedding vectors for top-N clusters. is_notable_moment = true if the candidate's segment range overlaps any NotableMoment row; notable_moment_id set to the matching NotableMoment.id (first match if multiple).</anchor>
  <anchor id="QUOTE_DEDUP">A rule-based (non-LLM) pass runs after all Phase 2 chunks are processed: candidate quotes whose segment ranges have overlap_ratio > PHASE2_DEDUP_OVERLAP_RATIO AND whose text has difflib.SequenceMatcher ratio > PHASE2_DEDUP_TEXT_SIMILARITY are merged into one final Quote, retaining the union of source candidate IDs for audit. Merged quote uses the candidate with higher narrative_alignment_score as the canonical record. No LLM call is used in this step.</anchor>
  <anchor id="NAMING_CONVENTION" extends="spec2:NAMING_CONVENTION">snake_case Python, camelCase TypeScript, kebab-case files, snake_case Postgres columns/tables.</anchor>
  <anchor id="ERROR_PATTERN" extends="spec2:ERROR_PATTERN">{ error: string, code: string, trace_id: uuid } — never includes filesystem paths or stack traces.</anchor>
</anchors>
```

## Schemas

```xml
<schemas>
  <model name="Phase2Chunk">
    <field name="id" type="uuid" nullable="false"/>
    <field name="video_id" type="uuid" nullable="false"/>
    <field name="chunk_index" type="integer" nullable="false" notes="0-based, sequential per video, see PHASE2_CHUNK anchor"/>
    <field name="start_segment_id" type="integer" nullable="false"/>
    <field name="end_segment_id" type="integer" nullable="false" notes="overlapping ranges permitted between adjacent chunks"/>
    <field name="token_count" type="integer" nullable="false"/>
  </model>

  <model name="QuoteCandidate">
    <field name="id" type="uuid" nullable="false"/>
    <field name="phase2_chunk_id" type="uuid" nullable="false" notes="FK to Phase2Chunk"/>
    <field name="video_id" type="uuid" nullable="false"/>
    <field name="start_segment_id" type="integer" nullable="false"/>
    <field name="end_segment_id" type="integer" nullable="false"/>
    <field name="speaker_label" type="string" nullable="false"/>
    <field name="narrative_alignment_score" type="float" nullable="false"/>
    <field name="is_notable_moment" type="boolean" nullable="false"/>
    <field name="notable_moment_id" type="uuid" nullable="true" notes="FK to spec 2's NotableMoment, set if this candidate's range overlaps a flagged notable moment"/>
    <field name="raw_qwen_output" type="jsonb" nullable="false" notes="full raw model output, kept for audit/debugging"/>
    <field name="discarded" type="boolean" nullable="false" notes="true if the candidate failed the QUOTE_GROUNDING validity check (multi-speaker range or non-interviewee speaker) and was never promoted to a Quote"/>
    <field name="discard_reason" type="string" nullable="true"/>
  </model>

  <model name="Quote">
    <field name="id" type="uuid" nullable="false"/>
    <field name="video_id" type="uuid" nullable="false"/>
    <field name="start_segment_id" type="integer" nullable="false"/>
    <field name="end_segment_id" type="integer" nullable="false"/>
    <field name="start_ts" type="float" nullable="false" notes="copied from the first referenced segment"/>
    <field name="end_ts" type="float" nullable="false" notes="copied from the last referenced segment"/>
    <field name="quote_text" type="string" nullable="false" notes="deterministically assembled, never model-generated"/>
    <field name="speaker_label" type="string" nullable="false"/>
    <field name="narrative_alignment_score" type="float" nullable="false"/>
    <field name="is_notable_moment" type="boolean" nullable="false"/>
    <field name="notable_moment_id" type="uuid" nullable="true"/>
    <field name="source_candidate_ids" type="jsonb" nullable="false" notes="array of QuoteCandidate ids merged into this final Quote, see QUOTE_DEDUP anchor"/>
    <field name="reviewed" type="boolean" nullable="false" notes="default false, set true on any Gate 2 action touching this row"/>
  </model>

  <api endpoint="/api/videos/{id}/phase2/quotes" method="GET">
    <request>query params: view ("notable"|"top"), limit (integer, optional, default null = all)</request>
    <response>{ quotes: Quote[] }</response>
    <errors>
      <error code="400" reason="view param missing or invalid"/>
      <error code="404" reason="video id does not exist"/>
      <error code="409" reason="status earlier than phase2_ready_for_review"/>
    </errors>
  </api>

  <api endpoint="/api/videos/{id}/phase2/corrections" method="POST">
    <request>{ entity_type: "quote", entity_id: uuid, field_name: string|null, original_value: any, corrected_value: any|null, reason_category: enum, reason_note: string|null }</request>
    <response>{ correction_id: uuid }</response>
    <errors>
      <error code="400" reason="reason_category missing or invalid, or entity_id does not belong to this video"/>
      <error code="404" reason="video id does not exist"/>
    </errors>
  </api>

  <api endpoint="/api/videos/{id}/phase2/confirm-review" method="POST">
    <request>none</request>
    <response>{ video_id: uuid, status: "phase2_reviewed" }</response>
    <errors>
      <error code="404" reason="video id does not exist"/>
      <error code="409" reason="status is not phase2_ready_for_review"/>
    </errors>
  </api>
</schemas>
```

## Preconditions

**phase1_reviewed_enqueues_phase2**
- Given: a Video with status "phase1_reviewed"
- When: Phase 2 processing is triggered
- Then: status transitions phase1_reviewed → phase2_queued → phase2_processing; Phase2Chunk rows are created from TranscriptTurn rows, with overlapping boundaries per PHASE2_CHUNK anchor

**quote_candidate_grounded_and_scored**
- Given: a Phase2Chunk being processed, with the top-N NarrativeCluster elements and this chunk's own NotableMoment(s) included in the prompt
- When: Qwen returns candidate quotes as segment ID ranges
- Then: QuoteCandidate rows are created with narrative_alignment_score (MiniLM cosine similarity, deterministic) and is_notable_moment (segment range overlap check, deterministic) populated as separate fields; notable_moment_id set if the range overlaps a NotableMoment

**non_interviewee_candidate_discarded**
- Given: a QuoteCandidate whose segment range resolves to a speaker_label with role "interviewer" or "unknown" in SpeakerRoleMap
- When: the grounding validity check runs
- Then: discarded is set true, discard_reason is populated, and no Quote row is created from it

**multi_speaker_range_discarded**
- Given: a QuoteCandidate whose segment range spans more than one speaker_label
- When: the grounding validity check runs
- Then: discarded is set true, discard_reason is populated, and no Quote row is created from it

**boundary_duplicates_merged_without_llm**
- Given: two QuoteCandidates from adjacent, overlapping Phase2Chunks referencing overlapping segment ranges with highly similar text
- When: the rule-based dedup pass runs after all chunks complete
- Then: a single Quote row is created with source_candidate_ids containing both candidate IDs; no LLM call occurs during this step

**quotes_over_generated_no_fixed_n**
- Given: Phase 2 processing completes for a video
- When: all Phase2Chunks have produced candidates and dedup has run
- Then: all valid (non-discarded) scored Quote rows are persisted regardless of count; no truncation to a fixed N occurs at this stage

**quotes_view_filters_at_query_time**
- Given: a video at phase2_ready_for_review with 40 stored Quote rows, 5 of which have is_notable_moment=true
- When: GET .../phase2/quotes?view=notable is called
- Then: exactly the 5 notable-moment quotes are returned
- When: GET .../phase2/quotes?view=top&limit=10 is called
- Then: the 10 highest narrative_alignment_score quotes are returned, ordered descending

**correction_logged_on_quote_edit**
- Given: a video at phase2_ready_for_review, user rejects a Quote via the review UI
- When: the rejection is submitted
- Then: POST .../phase2/corrections is called with entity_type "quote" and a reason_category; a Correction row is created

**confirm_review_transitions_status**
- Given: a video at phase2_ready_for_review
- When: POST .../phase2/confirm-review is called
- Then: status transitions to phase2_reviewed; further edits against this Phase 2 output return 409

## Execution Gates

```xml
<execution_gates>
  <gate id="1" milestone="Phase2Chunk creation with turn-based overlapping boundaries; quote candidates grounded to segment IDs with narrative_alignment_score and is_notable_moment as separate fields">
    <command lang="python">pytest tests/phase2/chunking/ tests/phase2/extraction/ -v</command>
    <must_pass>true</must_pass>
    <on_failure>Stop. Log to deviations. State what failed and why. Wait for input.</on_failure>
  </gate>
  <gate id="2" milestone="Interviewee-only filtering and multi-speaker rejection correctly discard invalid candidates; rule-based boundary dedup produces final Quote rows with no LLM call">
    <command lang="python">pytest tests/phase2/grounding/ tests/phase2/dedup/ -v</command>
    <must_pass>true</must_pass>
    <on_failure>Stop. Log to deviations. State what failed and why. Wait for input.</on_failure>
  </gate>
  <gate id="3" milestone="Review Gate 2 UI complete: top-N quotes track added alongside spec 2's notable-moments track, synced list, edit/reject with reason_category, confirm-review flow">
    <command lang="typescript">vitest run phase2-review-ui.test.ts</command>
    <command lang="python">pytest tests/phase2/review/ -v</command>
    <must_pass>true</must_pass>
    <on_failure>Stop. Log to deviations. State what failed and why. Wait for input.</on_failure>
  </gate>
  <gate id="4" milestone="Full stack still deployable via single docker-compose command with spec-3 migrations applied">
    <command lang="bash">docker-compose up --build -d && curl -f http://localhost:8000/health</command>
    <must_pass>true</must_pass>
    <on_failure>Stop. Log to deviations. State what failed and why. Wait for input.</on_failure>
  </gate>
</execution_gates>
```

## Pre-Implementation Conflict Register

These conflicts and tech debt items were identified during codebase analysis (2026-07-18) before implementation began. Each must be resolved as part of the gate it blocks.

```xml
<conflicts>
  <conflict id="C1" severity="blocking" gate="1" file="backend/app/routers/videos.py:112-116">
    get_transcript reviewable set stops at phase1_reviewed. Phase 2 statuses (phase2_queued, phase2_processing, phase2_ready_for_review, phase2_reviewed) are not included. Any frontend page loading the transcript while a video is in a phase2 status will receive 409. Fix: add all four phase2 statuses to the reviewable set before building the Phase 2 router.
  </conflict>
  <conflict id="C2" severity="blocking" gate="3" file="frontend/src/app/videos/[id]/phase1/page.tsx:161">
    isReviewed = video?.status === "phase1_reviewed" — false for any phase2 status. Once Phase 2 auto-enqueues (DB → phase2_queued), a user returning to the phase1 review page sees the Confirm button as active, which will 409 on submit. Fix: isReviewed should be true for any status past phase1_ready_for_review.
  </conflict>
  <conflict id="C3" severity="test" gate="1" file="backend/tests/phase1/review/test_review.py:250-257">
    test_confirm_review_transitions_to_phase1_reviewed checks resp.json()["status"] == "phase1_reviewed" — response body test still passes (we return the confirmed status, not the queued state, matching spec 1 pattern). But the test does not assert the DB transitions to phase2_queued. Add a companion assertion / new test mirroring test_phase1_auto_enqueued_after_spec1_confirm_review.
  </conflict>
  <conflict id="C4" severity="blocking" gate="1" file="frontend/src/lib/api.ts:4-13">
    VideoStatus union type missing all four phase2 statuses. TypeScript will not accept phase2 status strings; VideoList and review page logic will be incorrect. Fix before writing any Phase 2 frontend.
  </conflict>
  <conflict id="C5" severity="bug" gate="1" file="backend/app/worker/phase1/chunking.py:16">
    build_chunks return type annotation says list[TranscriptChunk] but the function returns tuple[list[TranscriptChunk], list[list[TranscriptTurn]]]. Misleading for Phase 2 chunking which follows the same signature. Fix the annotation before writing phase2/chunking.py.
  </conflict>
  <conflict id="C6" severity="tech-debt" gate="none" file="backend/migrations/versions/002_phase1_schema.py:68">
    chunk_narratives.cluster_id FK exists in migration 002 but ChunkNarrative model has no cluster_id field. Dead column in DB, never written or read. Cannot remove without a migration — leave for now, document only.
  </conflict>
  <conflict id="C7" severity="tech-debt" gate="1" file="backend/tests/phase1/clustering/test_clustering.py, backend/tests/phase1/extraction/test_extraction.py">
    _make_video and _make_chunk helpers are duplicated identically across both test files. Move shared helpers to tests/phase1/conftest.py before writing Phase 2 tests to prevent the same pattern spreading.
  </conflict>
  <conflict id="C8" severity="usability" gate="2" file="backend/app/routers/phase1.py:159">
    Phase 1 corrections router's else-branch raises INVALID_ENTITY_TYPE for any entity_type not in the Phase 1 set. Once CorrectionEntityType.quote is added to the enum, a Phase 1 corrections call with entity_type="quote" silently hits this branch. Make the error explicit: reject quote with a WRONG_STAGE code so the frontend/caller knows the entity type is valid but belongs to the Phase 2 endpoint.
  </conflict>
</conflicts>
```

## Change Protocol

```xml
<change_protocol>
  <decisions>
    <decision id="D1" anchor="PHASE2_CHUNK" confidence="medium">Overlap window = 2 whole turns per boundary. Reasoning: 1 turn risks missing a quote that straddles a boundary when speaker changes are rapid; 3+ turns increases prompt size without proportionate benefit for typical interview cadence. Configurable via PHASE2_OVERLAP_TURNS (default: 2).</decision>
    <decision id="D2" anchor="QUOTE_DEDUP" confidence="medium">Merge threshold: segment range overlap_ratio > 0.5 AND difflib.SequenceMatcher ratio > 0.85. Overlap_ratio = intersection_size / union_size over segment ID ranges. SequenceMatcher chosen over edit distance for robustness to minor Qwen paraphrasing of adjacent-turn boundaries. Both thresholds configurable. Canonical record = higher narrative_alignment_score of the two merged candidates.</decision>
    <decision id="D3" anchor="QUOTE_GROUNDING" confidence="high">narrative_alignment_score computed deterministically post-hoc (user confirmed). Method: embed quote_text via MiniLM (same model as spec 2 clustering, CPU-only) → compute cosine similarity against all ChunkTheme.theme_embedding vectors for the top-N NarrativeClusters → take the max → clip to [0.0, 1.0]. Reuses stored embeddings — no re-clustering or new model calls.</decision>
    <decision id="D4" anchor="JOB_STATUS" confidence="high">Phase 2 auto-enqueues from POST /phase1/confirm-review (user confirmed). Implementation: after setting phase1_reviewed, immediately set phase2_queued and commit. Response body returns "phase1_reviewed" (what was confirmed), matching the spec 1 pattern where response returns "reviewed" but DB is phase1_queued.</decision>
    <decision id="D5" anchor="none" confidence="high">Phase 2 review UI lives at /videos/[id]/phase2/ (separate page, user confirmed). Shows quotes (top-N by score + notable-moment flagged) alongside Phase 1 notable moments for cross-reference context. Own confirm-review button transitions to phase2_reviewed.</decision>
    <decision id="D6" anchor="QUOTE_GROUNDING" confidence="medium">is_notable_moment derived rule-based (not Qwen-generated): true when the candidate's segment range overlaps any NotableMoment row for the same video. notable_moment_id set to first matching NotableMoment.id. Reasoning: avoids Qwen hallucinating notable-moment flags; the ground truth is already in the DB from spec 2; rule is deterministic and auditable.</decision>
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
  <current_milestone>Gate 3 passed (2026-07-19) — 20 backend review tests + 13 frontend vitest tests. Phase 2 router (GET quotes, POST corrections, POST confirm-review), Phase 2 review page at /videos/[id]/phase2/, VideoList link for phase2_ready_for_review, Quote/Phase2Correction types in api.ts. phase1/narrative reviewable set extended to include all phase2 statuses. 151 backend + 37 frontend tests all passing.</current_milestone>
  <open_questions>
    <!-- all questions resolved in pre-implementation analysis session -->
  </open_questions>
  <context_carry>
    This is spec 3 of 5 in the autonomous AI audio/video editor project (spec 1: upload/transcription/speaker review; spec 2: Phase 1 narrative extraction + TranscriptTurn grouping; this spec: Phase 2 quote search; spec 4: correction/learning loop; spec 5: UI/UX polish).

    Both QuoteCandidate and Quote tables exist so raw per-chunk output is preserved for audit even after merging — do not collapse them into one table in future specs without preserving that audit trail.

    Corrections logged in this spec (entity_type "quote") join the same Correction table populated in spec 2 — spec 4's embedding-based retrieval will need to handle both entity_types (narrative_cluster, notable_moment, quote) when building few-shot context, since the source content differs in shape (a narrative tag vs. a quote's transcript text).

    The discarded/discard_reason fields on QuoteCandidate exist specifically so a future debugging pass (or spec 4's learning loop) can distinguish "Qwen never proposed this" from "Qwen proposed it but it failed grounding" — don't delete discarded rows.

    narrative_alignment_score uses ChunkTheme.theme_embedding vectors already stored in the DB (spec 2). The MiniLM model is already loaded for spec 2 clustering. No new model pulls or GPU allocation needed for scoring — it's a CPU-only cosine similarity pass over stored vectors.

    The Phase 2 Qwen prompt shows: (a) full transcript chunk in TranscriptTurn format (same format as spec 2, including interviewer turns for context), (b) the top-N NarrativeCluster representative_labels as reference anchors, (c) any NotableMoment descriptions whose segment range falls within the chunk. Qwen outputs a list of objects each containing start_segment_id and end_segment_id only — no quote text, no timestamps, no scores.

    Implementation order within Gate 1: fix C1 (videos.py reviewable set), C4 (api.ts VideoStatus), C5 (chunking.py annotation), C7 (test conftest) → add phase2 job statuses to JobStatus enum → add Phase2Chunk/QuoteCandidate/Quote models → write migration 004 → config settings → phase2/chunking.py → phase2/extraction.py → update runner → tests.
  </context_carry>
</session_state>
```

```xml
<skipped_sections tier="medium">
  <section name="dependencies" reason="Linear build order within this spec (chunk → extract/ground → dedup → review UI); cross-spec dependency on specs 1-2 is stated in Intent/System, not a branching graph"/>
  <section name="thinking_budget" reason="Standard reasoning depth sufficient throughout"/>
</skipped_sections>
```
