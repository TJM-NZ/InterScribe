"""Call Qwen3.5:9b via Ollama to extract narrative context and sub-themes per chunk.

Hard constraints from SPEC-002:
- Never sends raw segments — receives pre-formatted chunk text (turn-grouped)
- Retries per-chunk up to settings.narrative_chunk_retries, then fails the whole video
- Validates theme and notable moment segment IDs are within the chunk's range
"""
import json
import logging
import re
import time

import httpx

from app.config import settings
from app.models.phase1 import ChunkNarrative, ChunkTheme, NotableMoment, TranscriptChunk

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = (
    "You are a narrative analysis assistant. Analyse the interview transcript chunk below "
    "and return ONLY a valid JSON object — no explanation, no markdown fences."
)

_USER_TEMPLATE = """\
Return a JSON object with exactly these keys:
- "domain": string (1-4 word domain label, e.g. "AI research", "healthcare policy")
- "tone": one of: formal, casual, technical, analytical, emotional, neutral
- "themes": array of 2-5 objects. Divide the transcript into coherent thematic segments — \
each theme covers a distinct topic or phase of the conversation. Order themes chronologically \
by start_segment_id. Each theme object has:
    - "topic_focus": string (one sentence describing what this section is about)
    - "topic_tags": array of 2-4 short phrases (key topics in this theme)
    - "start_segment_id": int (first segment ID in this theme, from the brackets)
    - "end_segment_id": int (last segment ID in this theme, from the brackets)
    - "notable_moments": array of objects (each: start_segment_id int, end_segment_id int, \
description string). A notable moment is a passage that is especially insightful, surprising, \
emotionally significant, quotable, or that summarises a key point. Return empty array if none.

Use the segment IDs shown in brackets as references for all boundaries.

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


def _extract_json(text: str) -> dict:
    """Extract JSON from response text, stripping markdown fences or think tags if present."""
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()
    text = re.sub(r"^```(?:json)?\s*", "", text).strip()
    text = re.sub(r"\s*```$", "", text).strip()
    return json.loads(text)


def unload_qwen_model() -> None:
    """Release the Qwen model from Ollama VRAM so WhisperX can use the full GPU."""
    try:
        httpx.post(
            f"{settings.ollama_base_url}/api/chat",
            json={"model": settings.qwen_model, "messages": [], "keep_alive": 0},
            timeout=10,
        )
    except Exception as exc:
        logger.warning("Could not unload Ollama model from VRAM: %s", exc)


def _call_qwen(chunk_text: str) -> dict:
    payload = {
        "model": settings.qwen_model,
        "messages": [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": _USER_TEMPLATE.format(chunk_text=chunk_text)},
        ],
        "stream": False,
        "think": False,
        "options": {"num_ctx": 16384},
    }
    resp = httpx.post(
        f"{settings.ollama_base_url}/api/chat",
        json=payload,
        timeout=1200,
    )
    resp.raise_for_status()
    content = resp.json()["message"]["content"]
    return _extract_json(content)


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


def _validate_themes(raw: list, chunk_start: int, chunk_end: int) -> list[dict]:
    """Validate and clamp theme boundaries; skip themes missing required fields."""
    valid = []
    for item in raw:
        try:
            start = int(item["start_segment_id"])
            end = int(item["end_segment_id"])
            focus = str(item.get("topic_focus", "")).strip()
            tags = [str(t) for t in item.get("topic_tags", []) if t]
        except (KeyError, TypeError, ValueError):
            continue
        if not focus:
            continue
        start = max(chunk_start, min(start, chunk_end))
        end = max(start, min(end, chunk_end))
        moments = _validate_notable_moments(
            item.get("notable_moments") or [], chunk_start, chunk_end
        )
        valid.append({
            "topic_focus": focus,
            "topic_tags": tags,
            "start_segment_id": start,
            "end_segment_id": end,
            "notable_moments": moments,
        })
    return valid


def extract_chunk(
    chunk: TranscriptChunk,
    chunk_text: str,
    db,
) -> tuple["ChunkNarrative", list["ChunkTheme"]]:
    """Call Qwen for one chunk. Returns (ChunkNarrative, list[ChunkTheme])."""
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

    themes_raw = _validate_themes(
        raw.get("themes") or [], chunk.start_segment_id, chunk.end_segment_id
    )

    # Flatten all theme tags for the chunk-level narrative record
    all_tags: list[str] = []
    for t in themes_raw:
        all_tags.extend(t["topic_tags"])

    narrative = ChunkNarrative(
        chunk_id=chunk.id,
        video_id=chunk.video_id,
        domain=domain,
        tone=tone,
        topic_tags=list(dict.fromkeys(all_tags)),  # deduplicated, order-preserving
        narrative_embedding=[0.0] * 384,  # unused; kept for schema compat
        raw_qwen_output=raw,
    )
    db.add(narrative)
    db.flush()

    chunk_themes: list[ChunkTheme] = []
    for idx, theme_data in enumerate(themes_raw):
        theme = ChunkTheme(
            chunk_id=chunk.id,
            video_id=chunk.video_id,
            theme_index=idx,
            topic_focus=theme_data["topic_focus"],
            topic_tags=theme_data["topic_tags"],
            start_segment_id=theme_data["start_segment_id"],
            end_segment_id=theme_data["end_segment_id"],
            theme_embedding=[0.0] * 384,  # filled by clustering
        )
        db.add(theme)
        db.flush()

        for moment in theme_data["notable_moments"]:
            db.add(
                NotableMoment(
                    chunk_id=chunk.id,
                    video_id=chunk.video_id,
                    theme_id=theme.id,
                    start_segment_id=moment["start_segment_id"],
                    end_segment_id=moment["end_segment_id"],
                    description=moment["description"],
                )
            )

        chunk_themes.append(theme)

    return narrative, chunk_themes
