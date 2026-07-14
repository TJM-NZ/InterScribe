# InterScribe

AI audio/video transcription editor — Spec 1 of 5 (ingestion, WhisperX transcription, Gate 1 review UI).

## Stack

| Layer | Tech |
|-------|------|
| Backend | Python 3.11, FastAPI, SQLAlchemy 2, Alembic |
| Frontend | Next.js 15 (App Router), React 19, TypeScript, Tailwind CSS |
| Database | PostgreSQL 16 |
| Transcription | WhisperX 3.1.6 + pyannote-audio (diarization) + faster-whisper |
| Deployment | Docker Compose (single `docker compose up`) |

## Project structure

```
backend/          FastAPI app + Alembic migrations + worker
frontend/         Next.js app
.claude/docs/     Spec files (source of truth)
docker-compose.yml
.env.example      All env vars documented here
```

## Key rules (never violate)

- Schema changes only via Alembic migrations — no `create_all`, no manual edits
- Uploaded files are never deleted automatically
- Transcription is always async (background worker) — never inline in HTTP handler
- No hardcoded paths, secrets, or device assumptions — all via env vars
- No stack traces or filesystem paths in API error responses
- `SEGMENT_SCHEMA` and `SPEAKER_ROLE_MAP` field names are load-bearing for Specs 2–5 — do not rename

## Running locally (Docker)

```bash
cp .env.example .env
# Edit .env: set POSTGRES_PASSWORD, HUGGINGFACE_TOKEN, WHISPER_DEVICE
docker compose up --build
```

Backend: http://localhost:8000 | Frontend: http://localhost:3000

## Running tests

```bash
# Backend
cd backend && pip install -r requirements.txt
pytest tests/ -v

# Frontend
cd frontend && npm ci
npm test
```

## Env vars

See `.env.example` — every variable is documented there.
Key: `WHISPER_DEVICE` (cuda/cpu), `WHISPER_MODEL_SIZE` (default: large-v2), `HUGGINGFACE_TOKEN` (required for diarization).

## Spec / change protocol

Active spec: `.claude/docs/SPEC-001.md`
All soft-default decisions must be logged to the Change Protocol section of the spec.
Do not modify Schemas, Forbidden, or Anchors sections without explicit user approval.

## Job status flow

`uploaded → queued → transcribing → ready_for_review → reviewed | failed` (linear only, no skipping)

## Worker

DB-backed queue: `SELECT ... WHERE status='queued' FOR UPDATE SKIP LOCKED`
Polls every 5s. GPU device configurable via `WHISPER_DEVICE`.
Model cache at `WHISPER_MODEL_CACHE` (persisted via Docker volume).
