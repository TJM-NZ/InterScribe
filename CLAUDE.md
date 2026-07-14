# InterScribe

AI audio/video editor — ingestion, transcription, review. Spec 1 of 5.

Full spec: `.claude/docs/SPEC-001.md`

## Stack

| Layer | Tech |
|-------|------|
| Backend | Python 3.11 + FastAPI |
| Frontend | Next.js 15 (App Router) + TypeScript + Tailwind |
| Database | PostgreSQL 16 |
| Migrations | Alembic |
| Transcription | WhisperX (faster-whisper + pyannote-audio) |
| Deployment | Docker Compose |

## Quick Start

```bash
cp .env.example .env
# Edit .env — set POSTGRES_PASSWORD, HUGGINGFACE_TOKEN, WHISPER_DEVICE
docker compose up --build -d
```

Backend: http://localhost:8000 | Frontend: http://localhost:3000

## Key Commands

```bash
# Logs
docker compose logs -f worker       # watch transcription jobs
docker compose logs -f backend

# Migrations (auto-run on backend startup, manual if needed)
docker compose exec backend alembic upgrade head
docker compose exec backend alembic revision --autogenerate -m "description"

# Backend tests
docker compose exec backend pytest tests/ -v
# or locally with test DB:
DATABASE_URL=sqlite:///./test.db pytest tests/ -v

# Frontend tests
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

Worker (polls every 5s, SELECT FOR UPDATE SKIP LOCKED)
  → status=transcribing
  → WhisperX: VAD → faster-whisper → align → pyannote diarize
  → insert TranscriptSegment rows
  → status=ready_for_review

Gate 1 Review UI
  → transcript view (confidence < 0.7 flagged amber)
  → PATCH /speakers (assign interviewer/interviewee/unknown per speaker label)
  → POST /confirm-review (blocked until all speakers mapped)
  → status=reviewed
```

## Hard Constraints

- No hardcoded paths or secrets — everything via env vars
- No synchronous/blocking transcription in HTTP handlers
- Uploaded (stored) files never auto-deleted
- N speakers supported — never assume 2
- No speaker role auto-assignment without explicit user confirmation
- Schema changes via Alembic only — no `create_all` in production paths
- API errors: `{error, code, trace_id}` — no internal paths or stack traces

## Environment Variables

See `.env.example` — every variable is documented there.
Key non-obvious ones:
- `HUGGINGFACE_TOKEN` — required for pyannote diarization (must accept model licenses at hf.co)
- `WHISPER_COMPUTE_TYPE` — use `float16` for GPU, `int8` for CPU
- `HF_HOME` + `WHISPER_MODEL_CACHE` — model cache dirs (pre-populate to avoid re-download)

## Naming Conventions

snake_case Python | camelCase TypeScript | kebab-case files | snake_case Postgres

## Execution Gates

| Gate | Milestone | Tests |
|------|-----------|-------|
| 1 | Upload endpoint + storage + job queue | `pytest tests/upload/` + `vitest run upload.test.ts` |
| 2 | WhisperX pipeline → diarized segments | `pytest tests/transcription/` |
| 3 | Gate 1 review UI complete | `pytest tests/review/` + `vitest run review-ui.test.ts` |
| 4 | Fresh-clone deployability | `docker compose up --build -d && curl -f http://localhost:8000/health` |

Failure at any gate = stop, log to spec Change Protocol, wait for input.

## Load-Bearing Schema Notes

`segment_id` (sequential int per video) and `speaker_label` in `TranscriptSegment` are the grounding keys for all future specs (quote search, learning loop). Do not rename. `SpeakerRoleMap` role enum (`interviewer|interviewee|unknown`) is referenced by Spec 2 onwards for filtering.
