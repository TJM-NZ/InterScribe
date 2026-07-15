"""Call Qwen3.5:9b via Ollama to extract narrative context and notable moments per chunk.

Hard constraints from SPEC-002:
- Never sends raw segments — receives pre-formatted chunk text (turn-grouped)
- Retries per-chunk up to settings.narrative_chunk_retries, then fails the whole video
- Validates notable moment segment IDs are within the chunk's range
"""
import json
import logging
import time

import httpx

from app.config import settings
from app.models.phase1 import ChunkNarrative, NotableMoment, TranscriptChunk
from app.models.phase1 import TranscriptTurn

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = (
    "You are a narrative analysis assistant. Analyse the interview transcript chunk below "
    "and return ONLY a valid JSON object — no explanation, no markdown fences."
)

_USER_TEMPLATE = """\
Return a JSON object with exactly these keys:
- "domain": string (1-4 word domain label, e.g. "AI research", "healthcare policy")
- "tone": one of: formal, casual, technical, analytical, emotional, neutral
- "topic_tags": array of 3-7 short phrases (key topics in this chunk)
- "notable_moments": array of objects (each: start_segment_id int, end_segment_id int, description string). \
A notable moment is a passage that is especially insightful, surprising, emotionally significant, quotable, \
or that summarises a key point. Return empty array if none.

Use the segment IDs shown in brackets as references for notable moment boundaries.

TRANSCRIPT CHUNK:
{chunk_text}
"""


def _pull_model_if_needed() -> None:
    """Ensure the Qwen model is available in Ollama, pulling it if not."""
    try:
        resp = httpx.get(f"{settings.ollama_base_url}/api/tags", timeout=10)
        if resp.status_code == 200:
            names = [m["name"] for m in resp.json().get("models", [])]
            if any(settings.qwen_model in n for n in names):
                return
        logger.info("Pulling model %s from Ollama…", settings.qwen_model)
        httpx.post(
            f"{settings.ollama_base_url}/api/pull",
            json={"name": settings.qwen_model},
            timeout=3600,
        )
    except Exception as exc:
        logger.warning("Could not verify/pull Ollama model: %s", exc)


def _call_qwen(chunk_text: str) -> dict:
    payload = {
        "model": settings.qwen_model,
        "messages": [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": _USER_TEMPLATE.format(chunk_text=chunk_text)},
        ],
        "stream": False,
        "format": "json",
    }
    resp = httpx.post(
        f"{settings.ollama_base_url}/api/chat",
        json=payload,
        timeout=300,
    )
    resp.raise_for_status()
    content = resp.json()["message"]["content"]
    return json.loads(content)


def _validate_notable_moments(
    raw: list, chunk_start: int, chunk_end: int
) -> list[dict]:
    valid = []
    for item in raw:
        try:
            start = int(item["start_segment_id"])
            end = int(item["end_segment_id"])
            desc = str(item.get("description", "")).strip()
        except (KeyError, TypeError, ValueError):
            continue
        if not desc:
            continue
        start = max(chunk_start, min(start, chunk_end))
        end = max(start, min(end, chunk_end))
        valid.append({"start_segment_id": start, "end_segment_id": end, "description": desc})
    return valid


def extract_chunk(
    chunk: TranscriptChunk,
    chunk_text: str,
    db,
) -> ChunkNarrative:
    """Call Qwen for one chunk. Retries up to settings.narrative_chunk_retries times."""
    last_exc = None
    for attempt in range(settings.narrative_chunk_retries):
        try:
            raw = _call_qwen(chunk_text)
            break
        except Exception as exc:
            last_exc = exc
            logger.warning(
                "Chunk %s attempt %d failed: %s", chunk.chunk_index, attempt + 1, exc
            )
            if attempt < settings.narrative_chunk_retries - 1:
                time.sleep(2 ** attempt)
    else:
        raise RuntimeError(
            f"Chunk {chunk.chunk_index} failed after {settings.narrative_chunk_retries} attempts: {last_exc}"
        )

    domain = str(raw.get("domain", "unknown")).strip() or "unknown"
    tone = str(raw.get("tone", "neutral")).strip() or "neutral"
    topic_tags = [str(t) for t in raw.get("topic_tags", []) if t]

    narrative = ChunkNarrative(
        chunk_id=chunk.id,
        video_id=chunk.video_id,
        domain=domain,
        tone=tone,
        topic_tags=topic_tags,
        narrative_embedding=[0.0] * 384,  # placeholder; clustering.py fills this
        raw_qwen_output=raw,
    )
    db.add(narrative)
    db.flush()

    moments_raw = raw.get("notable_moments") or []
    for moment in _validate_notable_moments(moments_raw, chunk.start_segment_id, chunk.end_segment_id):
        db.add(
            NotableMoment(
                chunk_id=chunk.id,
                video_id=chunk.video_id,
                start_segment_id=moment["start_segment_id"],
                end_segment_id=moment["end_segment_id"],
                description=moment["description"],
            )
        )

    return narrative
