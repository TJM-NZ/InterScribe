# InterScribe

AI audio/video editor — ingestion, transcription, narrative extraction. Specs 1–5.

Specs: `.claude/docs/SPEC-001.md` (complete — all 4 gates passed) | `.claude/docs/SPEC-002.md` (complete — all 4 gates passed) | `.claude/docs/SPEC-003.md` (complete — Gates 1-3 passed) | `.claude/docs/SPEC-004.md` (complete — all 3 gates passed)

## Stack

| Layer | Tech |
|-------|------|
| Backend | Python 3.11, FastAPI, SQLAlchemy 2, Alembic |
| Frontend | Next.js 15 (App Router), React 19, TypeScript, Tailwind CSS |
| Database | PostgreSQL 16 + pgvector |
| Migrations | Alembic |
| Transcription | WhisperX 3.1.6 + pyannote-audio + faster-whisper |
| LLM inference | Qwen3.5:9b via Ollama (standalone Docker service) |
| Embeddings | all-MiniLM-L6-v2 via sentence-transformers (CPU only) |
| Deployment | Docker Compose |

## Hardware

Designed for RTX 1080Ti (~11GB VRAM). GPU used by WhisperX (transcription) and Ollama/Qwen (Phase 1 narrative extraction) — sequentially, never simultaneously; both are queued background jobs.

## Project Structure

```
backend/          FastAPI app + Alembic migrations + worker
frontend/         Next.js app
.claude/docs/     Spec files (source of truth)
docker-compose.yml
.env.example      All env vars documented here
```

## Quick Start

```bash
cp .env.example .env
# Edit .env — set POSTGRES_PASSWORD, HUGGINGFACE_TOKEN, WHISPER_DEVICE
docker compose up --build -d

# Pull Qwen model into the ollama_models volume (once; persists across restarts)
docker compose exec ollama ollama pull qwen3.5:9b
```

Backend: http://localhost:8002 | Frontend: http://localhost:3002

## Key Commands

```bash
# Logs
docker compose logs -f worker       # transcription + phase1 jobs
docker compose logs -f backend

# Migrations (auto-run on backend startup; manual if needed)
docker compose exec backend alembic upgrade head
docker compose exec backend alembic revision --autogenerate -m "description"

# Tests
docker compose exec backend pytest tests/ -v
cd frontend && npx vitest run

# Shell access
docker compose exec backend bash
docker compose exec postgres psql -U interscribe interscribe
```

## Architecture

```
Upload (POST /api/videos)
  → stream to temp file → ffprobe duration check → move to permanent storage
  → Video row (status=uploaded) → status=queued

Worker: transcription (polls status=queued)
  → status=transcribing
  → WhisperX: VAD → faster-whisper → align → pyannote diarize
  → insert TranscriptSegment rows → status=ready_for_review

Gate 1 Review UI (Spec 1)
  → transcript view (confidence < 0.7 flagged amber)
  → PATCH /speakers → POST /confirm-review (blocked until all speakers mapped)
  → status=reviewed → auto-enqueues Phase 1 (status=phase1_queued)

Worker: Phase 1 (polls status=phase1_queued)
  → status=phase1_processing
  → group segments → TranscriptTurns → chunk to ~10k tokens
  → Qwen3.5:9b per chunk: domain/tone/topics + notable moments
  → MiniLM embeddings (CPU) → agglomerative clustering → NarrativeCluster rows
  → status=phase1_ready_for_review

Gate 2 Review UI (Spec 2)
  → ranked narrative clusters + notable-moments list
  → edit/reject with reason_category → Correction rows
  → POST /phase1/confirm-review → status=phase1_reviewed
```

## Hard Constraints

- No hardcoded paths or secrets — everything via env vars
- No synchronous/blocking transcription or LLM calls in HTTP handlers
- Uploaded (stored) files never auto-deleted
- N speakers supported — never assume 2
- No speaker role auto-assignment without explicit user confirmation
- Schema changes via Alembic only — no `create_all` in production paths
- API errors: `{error, code, trace_id}` — no internal paths or stack traces
- Embedding inference (MiniLM) runs on CPU — never GPU
- Raw TranscriptSegments never sent to Qwen — assemble into TranscriptTurns first
- Chunk boundaries never split a TranscriptTurn
- Narrative ranking via embedding clustering only — no second Qwen reduce pass
- Notable moments never filtered or deduplicated — pass through unconditionally

## Job Status Flow

`uploaded → queued → transcribing → ready_for_review → reviewed → phase1_queued → phase1_processing → phase1_ready_for_review → phase1_reviewed → phase2_queued → phase2_processing → phase2_ready_for_review → phase2_reviewed → condensation_queued → condensation_processing → condensation_ready_for_review → condensation_reviewed | failed`

Linear only, no skipping. `failed` can occur at any stage; `error_reason` populated.
`reviewed → phase1_queued` is automatic (side effect of POST /confirm-review).
`phase1_reviewed → phase2_queued` is automatic (side effect of POST /phase1/confirm-review).
`phase2_reviewed → condensation_queued` is automatic (side effect of POST /phase2/confirm-review); response body still returns "phase2_reviewed".
Zero-headline shortcut: condensation_queued → condensation_reviewed immediately (no worker run) when video has no headline-type Quote rows.

## Load-Bearing Schema Notes

`segment_id` (sequential int per video) and `speaker_label` in `TranscriptSegment` are grounding keys for all future specs — do not rename.
`SpeakerRoleMap` role enum (`interviewer|interviewee|unknown`) used for filtering in Specs 2+.
`TranscriptTurn` (Spec 2) is the unit fed to Qwen — Spec 3 reuses, does not reimplement turn grouping.
`NarrativeCluster` rank (cluster_size descending) is the fixed anchor injected into every Spec 3 prompt — do not change ranking semantics without flagging Spec 3 impact.
`QuoteCandidate` (Spec 3) is never deleted after dedup — discarded rows preserved for audit/Spec 4 learning loop.
`Quote.source_candidate_ids` is JSONB (not a relational FK) — intentional, preserves audit trail without cascading deletes.
`narrative_alignment_score` uses `ChunkTheme.theme_embedding` vectors (Spec 2) — do not remove these columns.
Qwen never outputs quote text/timestamps — all text/ts resolved deterministically from `TranscriptSegment` rows.

## Environment Variables

See `.env.example` — every variable is documented there.
Key non-obvious ones:
- `HUGGINGFACE_TOKEN` — required for pyannote diarization (accept model licenses at hf.co)
- `WHISPER_COMPUTE_TYPE` — `float16` for GPU, `int8` for CPU
- `HF_HOME` + `WHISPER_MODEL_CACHE` — model cache dirs (pre-populate to avoid re-download)
- `OLLAMA_BASE_URL` — Ollama service URL (default: `http://ollama:11434`)
- `QWEN_MODEL` — model tag (default: `qwen3.5:9b`)
- `PHASE2_OVERLAP_TURNS` — overlap window in whole turns per chunk boundary (default: `2`)
- `PHASE2_DEDUP_OVERLAP_RATIO` — segment range overlap ratio threshold for dedup (default: `0.5`)
- `PHASE2_DEDUP_TEXT_SIMILARITY` — SequenceMatcher ratio threshold for dedup (default: `0.85`)

## Naming Conventions

snake_case Python | camelCase TypeScript | kebab-case files | snake_case Postgres

## Execution Gates

| Spec | Gate | Milestone | Tests |
|------|------|-----------|-------|
| 1 | 1 | Upload + storage + job queue | `pytest tests/upload/` + `vitest run upload.test.ts` |
| 1 | 2 | WhisperX → diarized segments | `pytest tests/transcription/` |
| 1 | 3 | Gate 1 review UI complete | `pytest tests/review/` + `vitest run review-ui.test.ts` |
| 1 | 4 | Fresh-clone deployability | `docker compose up --build -d && curl -f http://localhost:8000/health` |
| 2 | 1 | Turn-grouping + chunking + Qwen extraction | `pytest tests/phase1/turns/ tests/phase1/chunking/ tests/phase1/extraction/ -v` |
| 2 | 2 | Embedding clustering → ranked NarrativeCluster rows | `pytest tests/phase1/clustering/ -v` |
| 2 | 3 | Gate 2 review UI complete | `pytest tests/phase1/review/` + `vitest run phase1-review-ui.test.ts` |
| 2 | 4 | Fresh-clone deployability with Spec 2 migrations | `docker compose up --build -d && curl -f http://localhost:8000/health` |
| 3 | 1 | Phase2Chunk creation + quote candidates grounded to segment IDs | `pytest tests/phase2/chunking/ tests/phase2/extraction/ -v` |
| 3 | 2 | Interviewee-only filtering + rule-based dedup → Quote rows | `pytest tests/phase2/grounding/ tests/phase2/dedup/ -v` |
| 3 | 3 | Gate 3 review UI complete (quotes track + confirm-review) | `pytest tests/phase2/review/` + `vitest run phase2-review-ui.test.ts` |
| 3 | 4 | Fresh-clone deployability with Spec 3 migrations | `docker compose up --build -d && curl -f http://localhost:8000/health` |

Failure at any gate = stop, log to spec Change Protocol, wait for input.
