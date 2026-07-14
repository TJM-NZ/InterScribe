# SPEC-ai-audio-editor-20260714

## System

SPEC_LOCKED. This file is a behavioural contract — execute it, do not interpret around it.
Read-only (never modify without explicit user approval): Schemas, Forbidden.
Requires approval before acting: any deviation touching Schemas or hard constraints.
Update Change Protocol during session. Update Session State at session end — mandatory.
Reference Anchors by ID in all decision and deviation logs.

## Intent

Spec 1 of 5 for a fully autonomous AI audio/video editor. This spec covers ingestion (file upload), transcription (WhisperX with diarization), and the Gate 1 review interface (transcript view, low-confidence flagging, speaker role assignment). Optimise for correctness and auditability over speed — this is the foundation every later phase (narrative extraction, quote search, learning loop) depends on; errors here propagate downstream and are expensive to catch later.

This is a solo side project, self-hosted on a single machine with an RTX 1080Ti (~11GB VRAM). Overnight/unattended batch processing is acceptable — there is no real-time or low-latency requirement anywhere in this spec. The project must be fully deployable by a third party from a fresh git clone — assume the person running setup is not the original author and has no prior context beyond a README.

## Meta

```xml
<meta>
  <project>InterScribe</project>
  <tier>medium</tier>
  <stack>
    <backend>Python (FastAPI) — required for faster-whisper/WhisperX compatibility</backend>
    <frontend>Next.js (React) — matches author's existing stack conventions</frontend>
    <database>PostgreSQL</database>
    <other>Docker + docker-compose for full-stack local deployment; Alembic for migrations; faster-whisper + WhisperX (pyannote-audio) for transcription/diarization</other>
  </stack>
  <hard_constraints>
    <constraint>Entire stack (backend, frontend, Postgres) must start via a single documented command (e.g. `docker-compose up`) from a fresh clone, with no manual steps beyond copying an env file</constraint>
    <constraint>All secrets/config (DB credentials, storage paths, model size/device settings) supplied via environment variables, never hardcoded — a committed `.env.example` documents every variable</constraint>
    <constraint>Database schema changes only via migrations — no manual schema edits, no `create_all`-style implicit sync in production paths</constraint>
    <constraint>Uploaded audio/video files are never deleted automatically at any point in this spec's scope</constraint>
    <constraint>Transcription runs as an async background job, never inline in the HTTP request/response cycle</constraint>
    <constraint>GPU device selection (CPU vs CUDA) must be configurable, not hardcoded — deployer's hardware may differ from the author's 1080Ti</constraint>
  </hard_constraints>
  <soft_defaults>
    <default>Job queue mechanism (e.g. simple DB-backed queue vs Celery/RQ) — Claude decides based on minimal added complexity, must log choice</default>
    <default>Upload file size/duration limits — Claude proposes sane defaults (e.g. up to 3 hours / 2GB), must log</default>
    <default>VAD pre-pass library choice (e.g. Silero VAD) — Claude decides, must log</default>
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

- No hardcoded filesystem paths anywhere (upload storage location, model cache dir) — all via env vars with documented defaults
- No hardcoded secrets or credentials in code, config files committed to the repo, or Docker images
- No synchronous/blocking transcription call inside an HTTP request handler
- No automatic deletion or mutation of the original uploaded audio/video file
- No silent assumption of exactly two speakers in diarization output — must support N speakers
- No auto-assignment of speaker role (interviewer/interviewee) without explicit user confirmation at Gate 1 — enrollment/auto-matching is out of scope for this spec
- No skipping the VAD pre-pass before transcription
- No exposing raw internal file paths or stack traces in API error responses
- No manual/non-migration database schema changes
- No requiring a manual step beyond `cp .env.example .env` (with edits) and one startup command for a fresh deployer to get the stack running

## Anchors

```xml
<anchors>
  <anchor id="SEGMENT_SCHEMA">Each transcript segment: {segment_id (sequential int, unique per video), start_ts (float, seconds), end_ts (float, seconds), text (string), speaker_label (string, e.g. SPEAKER_00), confidence (float 0-1, derived from WhisperX/Whisper avg_logprob normalised to 0-1)}. segment_id values are stable once written — later phases reference quotes by segment_id range, never by raw timestamp.</anchor>
  <anchor id="SPEAKER_ROLE_MAP">Per-video mapping: {video_id, speaker_label, role (enum: interviewer | interviewee | unknown)}. Populated at Gate 1. Every distinct speaker_label present in a video's segments must have exactly one row before Gate 1 is considered passed.</anchor>
  <anchor id="JOB_STATUS">Processing job states, linear progression only: uploaded → queued → transcribing → ready_for_review → reviewed. Any failure transitions to failed with an error_reason field populated. No skipping states.</anchor>
  <anchor id="NAMING_CONVENTION">snake_case Python, camelCase TypeScript, kebab-case files, snake_case Postgres columns/tables.</anchor>
  <anchor id="ERROR_PATTERN">{ error: string, code: string, trace_id: uuid } — never includes filesystem paths or stack traces.</anchor>
</anchors>
```

## Schemas

```xml
<schemas>
  <model name="Video">
    <field name="id" type="uuid" nullable="false"/>
    <field name="project_id" type="uuid" nullable="true" notes="reserved for future project-management feature, unused this spec"/>
    <field name="original_filename" type="string" nullable="false"/>
    <field name="storage_path" type="string" nullable="false" notes="internal managed storage location, never exposed via API"/>
    <field name="media_type" type="enum" nullable="false" notes="video | audio, derived from MIME type/extension at upload time"/>
    <field name="duration_seconds" type="float" nullable="true" notes="populated after transcription"/>
    <field name="status" type="enum" nullable="false" notes="see JOB_STATUS anchor"/>
    <field name="error_reason" type="string" nullable="true"/>
    <field name="uploaded_at" type="timestamp" nullable="false"/>
  </model>

  <model name="TranscriptSegment">
    <field name="id" type="uuid" nullable="false"/>
    <field name="video_id" type="uuid" nullable="false"/>
    <field name="segment_id" type="integer" nullable="false" notes="sequential per video, see SEGMENT_SCHEMA anchor"/>
    <field name="start_ts" type="float" nullable="false"/>
    <field name="end_ts" type="float" nullable="false"/>
    <field name="text" type="string" nullable="false"/>
    <field name="speaker_label" type="string" nullable="false"/>
    <field name="confidence" type="float" nullable="false"/>
  </model>

  <model name="SpeakerRoleMap">
    <field name="id" type="uuid" nullable="false"/>
    <field name="video_id" type="uuid" nullable="false"/>
    <field name="speaker_label" type="string" nullable="false"/>
    <field name="role" type="enum" nullable="false" notes="interviewer | interviewee | unknown, see SPEAKER_ROLE_MAP anchor"/>
  </model>

  <api endpoint="/api/videos" method="POST">
    <request>multipart/form-data: file (audio/video binary)</request>
    <response>{ id: uuid, status: "uploaded", original_filename: string, media_type: "video"|"audio" }</response>
    <errors>
      <error code="400" reason="unsupported file type or missing file"/>
      <error code="413" reason="file exceeds configured size/duration limit"/>
    </errors>
  </api>

  <api endpoint="/api/videos/{id}" method="GET">
    <request>none</request>
    <response>{ id: uuid, status: enum, error_reason: string|null, duration_seconds: float|null, original_filename: string, media_type: "video"|"audio", uploaded_at: timestamp }</response>
    <errors>
      <error code="404" reason="video id does not exist"/>
    </errors>
  </api>

  <api endpoint="/api/videos/{id}/transcript" method="GET">
    <request>none</request>
    <response>{ segments: TranscriptSegment[] }</response>
    <errors>
      <error code="404" reason="video id does not exist"/>
      <error code="409" reason="status is earlier than ready_for_review — transcript not yet available"/>
    </errors>
  </api>

  <api endpoint="/api/videos/{id}/speakers" method="PATCH">
    <request>{ assignments: [{ speaker_label: string, role: "interviewer"|"interviewee"|"unknown" }] }</request>
    <response>{ video_id: uuid, speaker_role_map: SpeakerRoleMap[] }</response>
    <errors>
      <error code="400" reason="speaker_label not present in this video's segments, or role not a valid enum value"/>
      <error code="404" reason="video id does not exist"/>
      <error code="409" reason="status is earlier than ready_for_review"/>
    </errors>
  </api>

  <api endpoint="/api/videos/{id}/confirm-review" method="POST">
    <request>none</request>
    <response>{ video_id: uuid, status: "reviewed" }</response>
    <errors>
      <error code="404" reason="video id does not exist"/>
      <error code="409" reason="not every distinct speaker_label in this video has a SpeakerRoleMap row yet"/>
    </errors>
  </api>
</schemas>
```

## Preconditions

**successful_upload_enqueues_job**
- Given: a valid audio/video file under the configured size/duration limit
- When: POST /api/videos with the file
- Then: 201 response with status "uploaded"; a Video row is created; a background transcription job is enqueued, not run inline

**media_type_detected_on_upload**
- Given: a valid file that is either audio-only (e.g. .mp3, .wav) or video (e.g. .mp4, .mov)
- When: POST /api/videos with the file
- Then: Video.media_type is set to "audio" or "video" respectively, based on MIME type/extension, not filename guesswork alone

**unsupported_upload_rejected**
- Given: a file with an unsupported extension or MIME type
- When: POST /api/videos with the file
- Then: 400 response, no Video row created, no job enqueued

**oversized_upload_rejected**
- Given: a file exceeding the configured size/duration limit
- When: POST /api/videos with the file
- Then: 413 response, no Video row created

**transcription_produces_diarized_segments**
- Given: a Video in status "queued"
- When: the background job runs WhisperX (VAD pre-pass → faster-whisper transcription → diarization → alignment)
- Then: TranscriptSegment rows are created per SEGMENT_SCHEMA, each with a non-null speaker_label; Video.status transitions to "ready_for_review"; Video.duration_seconds is populated

**transcription_failure_recorded**
- Given: a Video in status "queued" where WhisperX processing throws (e.g. corrupt file, unreadable audio)
- When: the background job fails
- Then: Video.status transitions to "failed"; Video.error_reason is populated with a human-readable (non-stack-trace) message

**speaker_role_assignment_updates_map**
- Given: a Video in status "ready_for_review" with segments from 2+ distinct speaker_labels
- When: PATCH /api/videos/{id}/speakers with valid role assignments for all distinct speaker_labels
- Then: 200 response; SpeakerRoleMap rows created/updated for each speaker_label

**confirm_review_blocked_until_all_speakers_mapped**
- Given: a Video in status "ready_for_review" with 3 distinct speaker_labels but only 2 mapped
- When: POST /api/videos/{id}/confirm-review
- Then: 409 response; Video.status remains "ready_for_review"

**fresh_clone_deployable**
- Given: a fresh git clone on a machine with Docker installed and no prior project-specific setup
- When: the deployer copies `.env.example` to `.env`, edits required values, and runs the documented single startup command
- Then: backend, frontend, and Postgres (with migrations applied) are running and reachable, with no manual steps beyond editing `.env`

## Execution Gates

```xml
<execution_gates>
  <gate id="1" milestone="Upload endpoint, storage, and job queue functional">
    <command lang="python">pytest tests/upload/ -v</command>
    <command lang="typescript">vitest run upload.test.ts</command>
    <must_pass>true</must_pass>
    <on_failure>Stop. Log to deviations. State what failed and why. Wait for input.</on_failure>
  </gate>
  <gate id="2" milestone="WhisperX transcription pipeline produces diarized, confidence-scored segments matching SEGMENT_SCHEMA">
    <command lang="python">pytest tests/transcription/ -v</command>
    <must_pass>true</must_pass>
    <on_failure>Stop. Log to deviations. State what failed and why. Wait for input.</on_failure>
  </gate>
  <gate id="3" milestone="Gate 1 review UI complete: transcript view with low-confidence flagging, speaker role assignment, confirm-review flow">
    <command lang="typescript">vitest run review-ui.test.ts</command>
    <command lang="python">pytest tests/review/ -v</command>
    <must_pass>true</must_pass>
    <on_failure>Stop. Log to deviations. State what failed and why. Wait for input.</on_failure>
  </gate>
  <gate id="4" milestone="Fresh-clone deployability verified end-to-end">
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
    <decision id="D1" anchor="JOB_STATUS" confidence="medium">DB-backed queue: worker polls SELECT ... WHERE status='queued' ORDER BY uploaded_at ASC LIMIT 1 FOR UPDATE SKIP LOCKED. No Redis/Celery/RQ. Reasoning: zero additional services, batch/overnight processing means queue latency is irrelevant, and the DB is already required — this keeps the deployment surface minimal.</decision>
    <decision id="D2" anchor="JOB_STATUS" confidence="medium">Upload limits: MAX_UPLOAD_SIZE_BYTES=2147483648 (2 GB), MAX_UPLOAD_DURATION_SECONDS=10800 (3 hours). Size checked by streaming bytes; duration checked via ffprobe after streaming to temp file, before moving to permanent storage. Temp file deleted on rejection — not an auto-deletion of a stored file, an explicit pre-acceptance rejection.</decision>
    <decision id="D3" anchor="SEGMENT_SCHEMA" confidence="high">VAD pre-pass: WhisperX's integrated pyannote-audio pipeline satisfies the VAD requirement natively (it runs VAD internally as part of the transcribe() call). No separate Silero VAD step needed. Using an additional VAD library would duplicate work.</decision>
    <decision id="D4" anchor="SEGMENT_SCHEMA" confidence="medium">Default model: WHISPER_MODEL_SIZE=large-v2. Fits 1080Ti 11GB VRAM with float16. Configurable via env var. large-v3 is an alternative if VRAM allows, but large-v2 is the safer default for the stated hardware constraint.</decision>
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
  <current_milestone>SPEC-001 COMPLETE — all 4 gates passed. Stack running on ports 8002 (API) and 3002 (frontend). Ready for Spec 2 (narrative extraction + notable-moments timeline).</current_milestone>
  <open_questions>
    <!-- <question id="Q1" priority="high|medium|low">[question]</question> -->
  </open_questions>
  <context_carry>
    This is spec 1 of a planned 5-spec build (full project context: an autonomous AI audio/video editor). Spec 2 will add Phase 1 narrative extraction (chunking, clustering, notable moments) and extend the review UI with a notable-moments timeline. Spec 3 adds Phase 2 quote search. Spec 4 adds the correction/learning loop. Spec 5 is UI/UX polish. This spec's SPEAKER_ROLE_MAP and SEGMENT_SCHEMA anchors are load-bearing for all later specs — segment_id is the grounding mechanism every future quote references, and speaker role filtering is what restricts quote candidates to interviewee-only content in Phase 2. Do not rename these fields without flagging the downstream impact.
  </context_carry>
</session_state>
```

```xml
<skipped_sections tier="medium">
  <section name="dependencies" reason="Single-module spec — build order is linear (upload → transcription → review UI), no branching dependency graph"/>
  <section name="thinking_budget" reason="Standard reasoning depth sufficient throughout — no unusually high-risk or exploratory subsections"/>
</skipped_sections>
```
