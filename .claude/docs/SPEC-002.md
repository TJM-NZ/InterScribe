# SPEC-ai-audio-editor-phase1-20260714

## System

SPEC_LOCKED. This file is a behavioural contract — execute it, do not interpret around it.
Read-only (never modify without explicit user approval): Schemas, Forbidden.
Requires approval before acting: any deviation touching Schemas or hard constraints.
Update Change Protocol during session. Update Session State at session end — mandatory.
Reference Anchors by ID in all decision and deviation logs.

Builds directly on SPEC-ai-audio-editor-20260714 (spec 1). `Video`, `TranscriptSegment`, and `SpeakerRoleMap` from spec 1 are existing, immutable-in-this-spec context — extend, never redefine them, except where explicitly noted (JOB_STATUS anchor extension below).

## Intent

Spec 2 of 5. Covers Phase 1 of the analysis pipeline: chunking the reviewed transcript, extracting per-chunk narrative context (domain, tone, topics) and notable moments via Qwen3.5:9b, ranking narrative elements across chunks via embedding-based clustering (not a second LLM pass), and the extended review UI (Review Gate 1) where the user reviews ranked narrative + notable moments before Phase 2 (spec 3) can run.

This spec also introduces correction logging (a `Correction` row is written whenever the user edits or rejects a narrative/notable-moment item at Review Gate 1). Correction *retrieval* for few-shot learning is out of scope — that's spec 4, built once real correction data exists from using Gates 1 and 2. This spec only needs to capture that data faithfully.

Same constraints as spec 1: self-hosted, single machine, RTX 1080Ti (~11GB VRAM), overnight/unattended batch processing acceptable, must remain deployable via the same single-command Docker setup.

## Meta

```xml
<meta>
  <project>InterScribe</project>
  <tier>medium</tier>
  <stack>
    <backend>Python (FastAPI), same service as spec 1</backend>
    <frontend>Next.js (React), same service as spec 1</frontend>
    <database>PostgreSQL, same instance as spec 1, extended via migration</database>
    <other>Qwen3.5:9b served locally (Ollama or vLLM, quantized GGUF); sentence-transformers running all-MiniLM-L6-v2 on CPU for narrative embeddings; a clustering library (e.g. scikit-learn agglomerative clustering or HDBSCAN) for cosine-similarity-based narrative grouping</other>
  </stack>
  <hard_constraints>
    <constraint>Narrative ranking across chunks is derived purely from embedding-based clustering — no second Qwen "reduce" call is used to summarise or rank across chunks</constraint>
    <constraint>Notable moments are never filtered, deduplicated, or excluded based on frequency/cluster size — they pass through to the review UI unconditionally</constraint>
    <constraint>Narrative clustering uses semantic similarity (embeddings), never exact-string matching, for deduplication</constraint>
    <constraint>Embedding inference (all-MiniLM-L6-v2) runs on CPU, never competing with Qwen for GPU/VRAM</constraint>
    <constraint>Every edit or rejection the user makes at Review Gate 1 writes a Correction row with a reason_category from the fixed enum — free-text-only corrections without a category are not permitted</constraint>
    <constraint>Chunk size is fixed at 10,000 tokens per chunk, no overlap (chunk-boundary overlap is a Phase 2 concern for quote-level grounding, not needed for chunk-level narrative extraction)</constraint>
    <constraint>Raw TranscriptSegment rows are never sent to Qwen directly as individual units — adjacent same-speaker segments must first be merged into TranscriptTurn rows (see TURN_GROUPING anchor) so Qwen sees coherent conversational turns, not arbitrary WhisperX-length fragments; this applies to any chunk text built in this spec and must be reused, not reimplemented, in spec 3</constraint>
    <constraint>Chunk boundaries (TranscriptChunk.start_segment_id/end_segment_id) must fall on turn boundaries — a chunk may never split a TranscriptTurn across two chunks</constraint>
  </hard_constraints>
  <soft_defaults>
    <default>Clustering algorithm and similarity threshold — Claude proposes a default (e.g. agglomerative clustering, cosine distance threshold ~0.3), must log reasoning; must be configurable, not hardcoded without a config surface</default>
    <default>Top-N narrative elements surfaced/passed to Phase 2 — Claude proposes a default (e.g. N=5), must be configurable per video or globally, must log</default>
    <default>Retry behaviour for a single chunk's Qwen call failing mid-video (retry vs fail whole video) — Claude decides, must log</default>
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

- No second Qwen "reduce" call across chunks to produce a final narrative summary — ranking must come from embedding clustering only
- No exact-string matching for narrative deduplication
- No filtering, capping, or deduplicating notable moments by frequency or cluster size
- No collapsing narrative ranking and notable-moment status into a single field or score — they remain separate concerns, consumed differently downstream
- No mutation of `TranscriptSegment` or `SpeakerRoleMap` rows from spec 1
- No running Phase 1 chunk processing on a video whose spec-1 status is not "reviewed"
- No embedding inference on GPU
- No allowing Review Gate 1 confirmation to log a correction without a reason_category
- No hardcoded top-N value with no config surface
- No sending raw, ungrouped TranscriptSegment text to Qwen — must be assembled into TranscriptTurn rows first
- No chunk whose start/end segment range splits a TranscriptTurn in half
- No starting Phase 2 (spec 3) processing automatically upon Review Gate 1 confirmation — that trigger is explicitly out of this spec's scope and will be wired in spec 3

## Anchors

```xml
<anchors>
  <anchor id="JOB_STATUS" extends="spec1:JOB_STATUS">Extends spec 1's linear status progression. After "reviewed" (spec 1's transcript/speaker review), this spec adds: reviewed → phase1_queued → phase1_processing → phase1_ready_for_review → phase1_reviewed. Any failure at any stage transitions to failed with error_reason populated. No skipping states. Phase 2 (spec 3) will append further states after phase1_reviewed.</anchor>
  <anchor id="TURN_GROUPING">Adjacent TranscriptSegment rows sharing the same speaker_label, with no intervening speaker change, are merged into a single TranscriptTurn before any text is sent to Qwen. This prevents a coherent thought or quote from being fragmented into isolated segments (e.g. a mid-sentence pause WhisperX splits into two segments) losing context the model needs to interpret it correctly. Turns still resolve back to their underlying start_segment_id/end_segment_id range, so all downstream anchoring (chunk boundaries, notable moment ranges, later quote ranges in spec 3) remains segment-ID based, never turn-ID based as the permanent reference.</anchor>
  <anchor id="CHUNK_SCHEMA">A chunk is a contiguous range of whole TranscriptTurn rows for one video, sized to ~10,000 tokens of turn text, no overlap, and never splitting a turn across two chunks (see TURN_GROUPING anchor). Chunks are numbered sequentially (chunk_index, 0-based) per video and reference their segment range via start_segment_id/end_segment_id (inclusive) — derived from the first and last turn's segment range — not raw timestamps.</anchor>
  <anchor id="NARRATIVE_CLUSTER">A cluster groups semantically similar ChunkNarrative rows across a single video's chunks, based on cosine similarity of their MiniLM embeddings. cluster_size = count of member chunks. rank is assigned by cluster_size descending; ties broken by chunk_index ascending (earliest-occurring cluster ranks higher).</anchor>
  <anchor id="CORRECTION_RECORD">Every user edit/rejection at any review gate writes one Correction row: {stage (phase1|phase2), reference to the corrected entity, field_name, original_value, corrected_value, reason_category (model_error|ambiguous_input|edge_case|preference), reason_note (optional free text), created_at}. Only reason_category is queryable/structured; reason_note is for human context only, never parsed by the pipeline. Embedding-based retrieval over this table is out of scope until spec 4.</anchor>
  <anchor id="NAMING_CONVENTION" extends="spec1:NAMING_CONVENTION">snake_case Python, camelCase TypeScript, kebab-case files, snake_case Postgres columns/tables.</anchor>
  <anchor id="ERROR_PATTERN" extends="spec1:ERROR_PATTERN">{ error: string, code: string, trace_id: uuid } — never includes filesystem paths or stack traces.</anchor>
</anchors>
```

## Schemas

```xml
<schemas>
  <model name="TranscriptTurn">
    <field name="id" type="uuid" nullable="false"/>
    <field name="video_id" type="uuid" nullable="false"/>
    <field name="turn_index" type="integer" nullable="false" notes="0-based, sequential per video"/>
    <field name="speaker_label" type="string" nullable="false"/>
    <field name="start_segment_id" type="integer" nullable="false"/>
    <field name="end_segment_id" type="integer" nullable="false" notes="inclusive; may equal start_segment_id if the turn is a single segment"/>
    <field name="combined_text" type="string" nullable="false" notes="concatenated text of all member segments, in order, this is what gets sent to Qwen — never raw individual segment text"/>
    <field name="token_count" type="integer" nullable="false"/>
  </model>

  <model name="TranscriptChunk">
    <field name="id" type="uuid" nullable="false"/>
    <field name="video_id" type="uuid" nullable="false"/>
    <field name="chunk_index" type="integer" nullable="false" notes="0-based, sequential per video, see CHUNK_SCHEMA anchor"/>
    <field name="start_segment_id" type="integer" nullable="false"/>
    <field name="end_segment_id" type="integer" nullable="false"/>
    <field name="token_count" type="integer" nullable="false"/>
  </model>

  <model name="ChunkNarrative">
    <field name="id" type="uuid" nullable="false"/>
    <field name="chunk_id" type="uuid" nullable="false" notes="FK to TranscriptChunk"/>
    <field name="video_id" type="uuid" nullable="false" notes="denormalised for query convenience"/>
    <field name="domain" type="string" nullable="false"/>
    <field name="tone" type="string" nullable="false"/>
    <field name="topic_tags" type="jsonb" nullable="false" notes="array of strings"/>
    <field name="narrative_embedding" type="vector(384)" nullable="false" notes="all-MiniLM-L6-v2 embedding of domain+tone+topic_tags, used for clustering"/>
    <field name="cluster_id" type="uuid" nullable="true" notes="FK to NarrativeCluster, set after clustering runs"/>
    <field name="raw_qwen_output" type="jsonb" nullable="false" notes="full raw model output, kept for audit/debugging"/>
  </model>

  <model name="NarrativeCluster">
    <field name="id" type="uuid" nullable="false"/>
    <field name="video_id" type="uuid" nullable="false"/>
    <field name="representative_label" type="string" nullable="false" notes="human-readable summary derived from member chunks (e.g. most common domain/tone/tags among members)"/>
    <field name="cluster_size" type="integer" nullable="false"/>
    <field name="rank" type="integer" nullable="false" notes="see NARRATIVE_CLUSTER anchor"/>
  </model>

  <model name="NotableMoment">
    <field name="id" type="uuid" nullable="false"/>
    <field name="chunk_id" type="uuid" nullable="false" notes="FK to TranscriptChunk, the chunk this moment was found in"/>
    <field name="video_id" type="uuid" nullable="false"/>
    <field name="start_segment_id" type="integer" nullable="false"/>
    <field name="end_segment_id" type="integer" nullable="false"/>
    <field name="description" type="string" nullable="false" notes="Qwen's description of why this moment is notable"/>
    <field name="reviewed" type="boolean" nullable="false" notes="default false, set true on any Gate 1 action touching this row"/>
  </model>

  <model name="Correction">
    <field name="id" type="uuid" nullable="false"/>
    <field name="video_id" type="uuid" nullable="false"/>
    <field name="stage" type="enum" nullable="false" notes="phase1 | phase2, see CORRECTION_RECORD anchor"/>
    <field name="entity_type" type="enum" nullable="false" notes="narrative_cluster | notable_moment (phase2 entity types added in spec 3)"/>
    <field name="entity_id" type="uuid" nullable="false" notes="id of the NarrativeCluster or NotableMoment row corrected"/>
    <field name="field_name" type="string" nullable="true" notes="null if the correction is a full rejection rather than a field edit"/>
    <field name="original_value" type="jsonb" nullable="true"/>
    <field name="corrected_value" type="jsonb" nullable="true" notes="null if the action was a rejection, not an edit"/>
    <field name="reason_category" type="enum" nullable="false" notes="model_error | ambiguous_input | edge_case | preference"/>
    <field name="reason_note" type="string" nullable="true"/>
    <field name="created_at" type="timestamp" nullable="false"/>
  </model>

  <api endpoint="/api/videos/{id}/phase1/narrative" method="GET">
    <request>none</request>
    <response>{ clusters: NarrativeCluster[] (ordered by rank), notable_moments: NotableMoment[] }</response>
    <errors>
      <error code="404" reason="video id does not exist"/>
      <error code="409" reason="status earlier than phase1_ready_for_review"/>
    </errors>
  </api>

  <api endpoint="/api/videos/{id}/phase1/corrections" method="POST">
    <request>{ entity_type: "narrative_cluster"|"notable_moment", entity_id: uuid, field_name: string|null, original_value: any, corrected_value: any|null, reason_category: enum, reason_note: string|null }</request>
    <response>{ correction_id: uuid }</response>
    <errors>
      <error code="400" reason="reason_category missing or invalid, or entity_id does not belong to this video"/>
      <error code="404" reason="video id does not exist"/>
    </errors>
  </api>

  <api endpoint="/api/videos/{id}/phase1/confirm-review" method="POST">
    <request>none</request>
    <response>{ video_id: uuid, status: "phase1_reviewed" }</response>
    <errors>
      <error code="404" reason="video id does not exist"/>
      <error code="409" reason="status is not phase1_ready_for_review"/>
    </errors>
  </api>
</schemas>
```

## Preconditions

**reviewed_video_enqueues_phase1**
- Given: a Video with status "reviewed" (spec 1 complete)
- When: Phase 1 processing is triggered (manually or automatically upon spec-1 confirm — exact trigger mechanism is a medium-confidence decision, log it)
- Then: status transitions reviewed → phase1_queued → phase1_processing; TranscriptChunk rows are created covering the full transcript with no gaps or overlaps

**adjacent_segments_merged_into_turns**
- Given: a video with 3 consecutive TranscriptSegment rows, the first two from SPEAKER_00 and the third from SPEAKER_01
- When: turn-grouping runs (before chunking)
- Then: the first two segments merge into one TranscriptTurn (start_segment_id/end_segment_id spanning both), the third becomes its own TranscriptTurn; combined_text concatenates the merged segments' text in order

**chunk_narrative_extraction**
- Given: a TranscriptChunk in a video currently phase1_processing
- When: the chunk's text is sent to Qwen3.5:9b for narrative extraction
- Then: a ChunkNarrative row is created with domain, tone, topic_tags, and narrative_embedding populated; notable_moment(s), if any are found, produce NotableMoment rows referencing the same chunk

**narrative_clustering_ranks_by_size**
- Given: all ChunkNarrative rows for a video are created (all chunks processed)
- When: clustering runs on narrative_embedding vectors
- Then: each ChunkNarrative gets a cluster_id; NarrativeCluster rows are created with cluster_size and rank (descending by size, ties broken by earliest chunk_index); status transitions to phase1_ready_for_review

**notable_moments_never_filtered**
- Given: a video with 8 chunks, only 1 of which contains a notable moment
- When: Phase 1 processing completes
- Then: that single NotableMoment row is present and returned by GET .../phase1/narrative regardless of its uniqueness/rarity relative to other chunks

**single_chunk_failure_handling**
- Given: one chunk's Qwen call fails (timeout, malformed response) while other chunks in the same video succeed
- When: Phase 1 processing runs
- Then: behaviour follows the logged retry-vs-fail decision (soft default) consistently — either that chunk retries a bounded number of times then fails the whole video with error_reason naming the chunk, or (if retry-per-chunk is chosen) failure is isolated and reported per-chunk without failing chunks that succeeded

**correction_logged_on_edit**
- Given: a video at phase1_ready_for_review, user edits a NarrativeCluster's representative_label via the review UI
- When: the edit is submitted
- Then: POST .../phase1/corrections is called with entity_type "narrative_cluster", the original and corrected values, and a reason_category; a Correction row is created

**correction_rejected_without_reason_category**
- Given: a correction submission missing reason_category
- When: POST .../phase1/corrections is called
- Then: 400 response, no Correction row created

**confirm_review_transitions_status**
- Given: a video at phase1_ready_for_review
- When: POST .../phase1/confirm-review is called
- Then: status transitions to phase1_reviewed; no further edits are accepted against this Phase 1 output (attempting one returns 409)

## Execution Gates

```xml
<execution_gates>
  <gate id="1" milestone="Turn-grouping, chunking, and Qwen narrative extraction produce TranscriptTurn, ChunkNarrative, and NotableMoment rows per TURN_GROUPING and CHUNK_SCHEMA anchors">
    <command lang="python">pytest tests/phase1/turns/ tests/phase1/chunking/ tests/phase1/extraction/ -v</command>
    <must_pass>true</must_pass>
    <on_failure>Stop. Log to deviations. State what failed and why. Wait for input.</on_failure>
  </gate>
  <gate id="2" milestone="Embedding-based clustering produces correctly ranked NarrativeCluster rows; notable moments pass through unfiltered">
    <command lang="python">pytest tests/phase1/clustering/ -v</command>
    <must_pass>true</must_pass>
    <on_failure>Stop. Log to deviations. State what failed and why. Wait for input.</on_failure>
  </gate>
  <gate id="3" milestone="Review Gate 1 UI complete: ranked narrative + notable-moments timeline/list, edit/reject with reason_category, correction logging, confirm-review flow">
    <command lang="typescript">vitest run phase1-review-ui.test.ts</command>
    <command lang="python">pytest tests/phase1/review/ -v</command>
    <must_pass>true</must_pass>
    <on_failure>Stop. Log to deviations. State what failed and why. Wait for input.</on_failure>
  </gate>
  <gate id="4" milestone="Full stack still deployable via single docker-compose command with spec-2 migrations applied">
    <command lang="bash">docker-compose up --build -d && curl -f http://localhost:8000/health</command>
    <must_pass>true</must_pass>
    <on_failure>Stop. Log to deviations. State what failed and why. Wait for input.</on_failure>
  </gate>
</execution_gates>
```

## Change Protocol

```xml
<change_protocol>
  <decisions>
    <decision id="D1" anchor="none" confidence="medium">Standalone Ollama service added to docker-compose.yml (image: ollama/ollama:latest, volume: ollama_models, GPU reservation). OLLAMA_BASE_URL=http://ollama:11434, QWEN_MODEL=qwen3.5:9b via env vars. Worker depends_on ollama healthcheck. Reasoning: spec must be self-contained — no dependency on external home-agents Ollama instance, which is bound to 127.0.0.1 and not reachable from Docker containers without a host bridge.</decision>
    <decision id="D2" anchor="CORRECTION_RECORD" confidence="medium">NotableMoment.reviewed is audit-trail only. POST .../phase1/confirm-review does NOT gate on all notable moments having reviewed=true — untouched moments remain reviewed=false after phase1_reviewed. Reasoning: no spec precondition requires explicit user action on every notable moment; Gate 1 only gates on the reviewer having had the opportunity to review, not on every item being touched.</decision>
    <decision id="D3" anchor="JOB_STATUS" confidence="medium">Phase 1 auto-triggers immediately after spec-1 confirm-review. POST /api/videos/{id}/confirm-review (spec-1 handler) transitions reviewed → phase1_queued as a side effect. No separate manual trigger endpoint. Reasoning: no UX benefit to a two-step confirm + trigger; reviewed is the gate, and phase1 processing is the natural next step.</decision>
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
  <last_completed_gate>4</last_completed_gate>
  <current_milestone>SPEC-002 COMPLETE — all 4 gates passed (65 backend tests, 19 frontend tests). Stack running on ports 8002 (API) and 3002 (frontend). Ready for Spec 3 (Phase 2 quote search).</current_milestone>
  <open_questions>
    <!-- <question id="Q1" priority="high|medium|low">[question]</question> -->
  </open_questions>
  <context_carry>
    This is spec 2 of 5 in the autonomous AI audio/video editor project (spec 1: upload/transcription/speaker review; this spec: Phase 1 narrative extraction; spec 3: Phase 2 quote search, extends review UI with a top-N quotes track; spec 4: correction/learning loop using pgvector retrieval over the Correction table populated here and in spec 3; spec 5: UI/UX polish).
    The Correction table's embedding-based retrieval (qwen3-embedding-0.6b, 32K context, summarised via Qwen if a chunk exceeds that limit) is intentionally deferred to spec 4 — do not add embedding columns to Correction in this spec; spec 4 will add them via migration once real correction volume exists to validate against.
    NarrativeCluster rank and top-N selection from it is what spec 3 will use as the fixed "anchor" injected into every Phase 2 chunk prompt — do not change the ranking semantics (cluster_size descending) without flagging the impact on spec 3's prompt design.
    chunk_id/start_segment_id/end_segment_id grounding must remain segment-ID based, matching spec 1's SEGMENT_SCHEMA — never switch to raw timestamps.
    This spec introduces TranscriptTurn (merged adjacent same-speaker segments) specifically to stop Qwen seeing fragmented, context-poor text — a raw WhisperX segment can be sentence-fragment-sized and split a coherent thought/quote across two rows. Spec 3 MUST reuse TranscriptTurn as the unit of text fed to Qwen for quote search, not reimplement its own grouping or fall back to raw segments — the same fragmentation risk applies to quote extraction, arguably more so, since a misinterpreted or truncated quote is a worse failure mode than a misjudged narrative tag. Spec 3's chunk-boundary overlap (30-60s) should also be defined in terms of whole turns, not raw segments or timestamps, for the same reason.
  </context_carry>
</session_state>
```

```xml
<skipped_sections tier="medium">
  <section name="dependencies" reason="Linear build order within this spec (chunk → extract → cluster → review UI); cross-spec dependency on spec 1 is stated in Intent/System, not a branching graph"/>
  <section name="thinking_budget" reason="Standard reasoning depth sufficient throughout"/>
</skipped_sections>
```
