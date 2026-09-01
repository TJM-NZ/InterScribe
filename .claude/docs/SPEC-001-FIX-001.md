# SPEC-001-FIX-001 — Repetition-Loop Hallucination Detection

## System

SPEC_LOCKED. Behavioural contract — execute it, do not interpret around it.
Amends: SPEC-ai-audio-editor-20260714 (Spec 1). All anchors from that spec apply here.
Read-only without explicit user approval: Schemas, Algorithm, Forbidden.
Update Change Protocol during session. Update Session State at session end.

## Intent

WhisperX occasionally produces repetition-loop hallucinations — a word or short phrase repeated many times consecutively within a single segment. This is a distinct failure mode from low-confidence output and is especially observed on low-resource languages (e.g. te reo Māori), though the check is language-agnostic.

This fix adds a deterministic post-processing detector that runs after transcription produces `TranscriptSegment` rows. No model changes, no re-transcription. The result surfaces in the Gate 1 review UI as a distinct tag, separate from the existing low-confidence flag.

## Meta

```xml
<meta>
  <project>InterScribe</project>
  <tier>small</tier>
  <amends>SPEC-ai-audio-editor-20260714</amends>
  <hard_constraints>
    <constraint>Detection is purely deterministic — no model calls, no inference, no per-language configuration</constraint>
    <constraint>repetition_flagged is independent of confidence — a segment may have both set, either, or neither</constraint>
    <constraint>Schema change via Alembic migration only — see SPEC-001 hard constraints</constraint>
    <constraint>The detector runs on the assembled segment text, not on raw WhisperX word-level output</constraint>
    <constraint>No change to WhisperX invocation, VAD pre-pass, or diarization — purely post-processing</constraint>
  </hard_constraints>
</meta>
```

## Algorithm

```xml
<algorithm id="REPETITION_DETECTOR">
  Input: segment.text (string)
  Output: bool — True if a repetition loop is detected

  Step 1: Tokenise by whitespace → tokens (list of strings)
  Step 2: For n in [1, 2, 3] (n-gram size):
    For each start index i from 0 to len(tokens)-n (inclusive):
      ngram = tokens[i : i+n]
      count = 1
      j = i + n
      While j <= len(tokens) - n and tokens[j : j+n] == ngram:
        count += 1
        j += n
      If count >= 4: return True
  Step 3: return False

  Notes:
  - Comparison is case-sensitive and whitespace-normalised (post-split)
  - "Consecutively" means non-overlapping, immediately adjacent repetitions
  - Empty or single-token segments trivially return False
  - MIN_REPETITION_COUNT is hardcoded to 4 — not configurable (not a threshold the operator should tune)
</algorithm>
```

## Schemas

**Schema amendment — `TranscriptSegment` (adds one field):**

```xml
<model name="TranscriptSegment" amends="SPEC-ai-audio-editor-20260714">
  <!-- All existing fields unchanged — see parent spec SEGMENT_SCHEMA anchor -->
  <field name="repetition_flagged" type="boolean" nullable="false" default="false"
         notes="True if REPETITION_DETECTOR fired on this segment's text. Independent of confidence."/>
</model>
```

**Migration:** A single Alembic migration adds `repetition_flagged BOOLEAN NOT NULL DEFAULT FALSE` to the `transcript_segments` table. Existing rows default to `false`.

**API amendment — GET /api/videos/{id}/transcript:**

```xml
<api endpoint="/api/videos/{id}/transcript" method="GET" amends="SPEC-ai-audio-editor-20260714">
  <response>{ segments: TranscriptSegment[] }</response>
  <!-- TranscriptSegment response shape gains: repetition_flagged: boolean -->
  <!-- All other request/response/error behaviour unchanged -->
</api>
```

## Anchors Inherited

| Anchor ID | From | How applied here |
|-----------|------|-----------------|
| `SEGMENT_SCHEMA` | SPEC-001 | `repetition_flagged` is an additive field; `segment_id` and `speaker_label` unchanged |
| `NAMING_CONVENTION` | SPEC-001 | `repetition_flagged` (snake_case Python/Postgres), `repetitionFlagged` (camelCase TypeScript) |
| `ERROR_PATTERN` | SPEC-001 | No new error codes — detection failure (unexpected exception) records `Video.status = failed` per existing pattern |
| `JOB_STATUS` | SPEC-001 | Detection runs inside the existing transcription job, before status transitions to `ready_for_review` |

## Preconditions

**repetition_loop_detected_and_flagged**
- Given: a `TranscriptSegment` whose text contains an n-gram (1-3 tokens) repeated 4+ times consecutively (e.g. "kia kia kia kia ora", "the the the the", "hello world hello world hello world hello world")
- When: the transcription worker runs the `REPETITION_DETECTOR` on the segment after WhisperX produces it
- Then: `TranscriptSegment.repetition_flagged = true`; `Video.status` proceeds to `ready_for_review` as normal (flagging does not halt the job)

**clean_segment_not_flagged**
- Given: a `TranscriptSegment` whose text contains no consecutive n-gram run of 4+ repetitions
- When: the transcription worker runs the `REPETITION_DETECTOR`
- Then: `TranscriptSegment.repetition_flagged = false`

**repetition_flag_independent_of_confidence**
- Given: a `TranscriptSegment` with `confidence >= 0.7` (not low-confidence) but with a detected repetition loop
- When: the segment is returned by GET /api/videos/{id}/transcript
- Then: `repetition_flagged = true`, `confidence >= 0.7` — both fields are set correctly and independently

**review_ui_shows_repetition_tag**
- Given: a `TranscriptSegment` with `repetition_flagged = true`
- When: the Gate 1 review UI renders that segment
- Then: a "repetition detected" tag is visible on the segment, visually distinct from the "low confidence" tag; both tags may appear simultaneously on the same segment

**review_ui_no_tag_when_clean**
- Given: a `TranscriptSegment` with `repetition_flagged = false`
- When: the Gate 1 review UI renders that segment
- Then: no "repetition detected" tag appears

## Execution Gate

```xml
<execution_gates>
  <gate id="1" milestone="Repetition detector, migration, API field, and UI tag all functional">
    <command lang="python">pytest tests/transcription/test_repetition_detector.py -v</command>
    <command lang="typescript">vitest run repetition-flag.test.ts</command>
    <must_pass>true</must_pass>
    <on_failure>Stop. Log to deviations. State what failed and why. Wait for input.</on_failure>
  </gate>
</execution_gates>
```

**Test coverage required:**

`tests/transcription/test_repetition_detector.py`:
- unigram run of exactly 4 → flagged
- unigram run of exactly 3 → not flagged
- bigram run of 4+ → flagged
- trigram run of 4+ → flagged
- mixed text with one embedded run of 4 → flagged
- empty string → not flagged
- single token → not flagged
- normal sentence with no repetition → not flagged
- segment with `confidence >= 0.7` and repetition → both fields set correctly

`repetition-flag.test.ts` (vitest, Gate 1 review UI):
- segment with `repetitionFlagged: true` renders "repetition detected" tag
- segment with `repetitionFlagged: false` renders no repetition tag
- segment with both `repetitionFlagged: true` and `confidence < 0.7` renders both tags simultaneously
- "repetition detected" tag is visually distinguishable from "low confidence" tag (distinct className or test-id)

## Forbidden

- No configurable threshold for `MIN_REPETITION_COUNT` — 4 is hardcoded
- No model call, embedding, or inference inside the detector
- No change to WhisperX invocation parameters
- No merging of `repetition_flagged` into the existing `confidence` field or low-confidence UI tag — they must remain separate
- No auto-rejection or suppression of flagged segments — the flag is informational; the human reviewer decides

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
  <current_milestone>Gate 1 passed 2026-07-19. All 9 backend + 5 frontend tests green.</current_milestone>
  <open_questions/>
  <context_carry>
    Amends SPEC-001 only. No impact on SPEC-002 (Phase 1 narrative extraction) or later specs — TranscriptTurn assembly and Qwen chunking consume segment.text, not repetition_flagged. The field is Gate 1 UI-only beyond this fix.
    Migration 005 adds repetition_flagged BOOLEAN NOT NULL DEFAULT FALSE to transcript_segments.
    detect_repetition_loop() lives in backend/app/worker/transcription.py (exported for tests).
  </context_carry>
</session_state>
```
