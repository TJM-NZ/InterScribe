"""Extract quote candidates from Phase2Chunk rows via Qwen3.5:9b.

Implements QUOTE_GROUNDING anchor from SPEC-003:
- Qwen outputs segment ID ranges only — never quote text or timestamps
- narrative_alignment_score: max cosine similarity vs stored ChunkTheme embeddings (D3)
- is_notable_moment: rule-based segment range overlap with NotableMoment rows (D6)
- Full conversational context shown to Qwen; output filtering happens at grounding step
"""
import json
import logging
import re
import time

import httpx
import numpy as np
from sentence_transformers import SentenceTransformer

from app.config import settings
from app.models.phase1 import NarrativeCluster, NotableMoment, TranscriptTurn
from app.models.phase2 import Phase2Chunk, QuoteCandidate
from app.models.video import TranscriptSegment
from app.worker.phase1.chunking import chunk_text_for_qwen

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = (
    "You are a quote extraction assistant. Identify the most quotable passages "
    "from this interview transcript. Return ONLY a valid JSON array — no explanation, "
    "no markdown fences."
)

_USER_TEMPLATE = """\
/no_think
INTERVIEW CONTEXT — dominant narrative themes:
{cluster_context}

{notable_moments_context}\
TRANSCRIPT CHUNK:
{chunk_text}

Return a JSON array of quote candidates. Each object must have exactly:
- "start_segment_id": int (a segment ID shown in brackets in the transcript above)
- "end_segment_id": int (a segment ID shown in brackets in the transcript above)
- "type": "headline" | "substantive"
    headline = self-contained, punchy, ≤25 words, could appear on a front cover or social post without context
    substantive = longer, contextually rich, requires surrounding narrative, suitable for embedding in an article or video

Rules:
- All segment IDs must fall within a single continuous speaker run
- Prefer passages that are insightful, surprising, quotable, or strongly tied to the themes above
- Aim for 3-8 candidates. Return [] if no strong candidates exist.
- Do NOT include any quote text — segment IDs only.
"""


def _format_cluster_context(clusters: list[NarrativeCluster]) -> str:
    if not clusters:
        return "(no narrative context available)"
    return "\n".join(f"{c.rank}. {c.representative_label}" for c in clusters)


def _format_notable_moments_context(moments: list[NotableMoment]) -> str:
    if not moments:
        return ""
    lines = ["NOTABLE MOMENTS IN THIS CHUNK:"]
    for m in moments:
        lines.append(f"  [seg {m.start_segment_id}-{m.end_segment_id}]: {m.description}")
    return "\n".join(lines) + "\n\n"


def _extract_json(text: str) -> list:
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()
    text = re.sub(r"^```(?:json)?\s*", "", text).strip()
    text = re.sub(r"\s*```$", "", text).strip()
    result = json.loads(text)
    return result if isinstance(result, list) else []


def _call_qwen(
    chunk_text: str,
    clusters: list[NarrativeCluster],
    chunk_notable_moments: list[NotableMoment],
) -> list[dict]:
    user_content = _USER_TEMPLATE.format(
        cluster_context=_format_cluster_context(clusters),
        notable_moments_context=_format_notable_moments_context(chunk_notable_moments),
        chunk_text=chunk_text,
    )
    payload = {
        "model": settings.qwen_model,
        "messages": [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": user_content},
        ],
        "stream": False,
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


_VALID_QUOTE_TYPES = {"headline", "substantive"}


def _validate_candidates(raw: list, chunk_start: int, chunk_end: int) -> list[dict]:
    """Keep only structurally valid candidates within the chunk's segment range."""
    valid = []
    for item in raw:
        try:
            start = int(item["start_segment_id"])
            end = int(item["end_segment_id"])
        except (KeyError, TypeError, ValueError):
            continue
        if start > end or start < chunk_start or end > chunk_end:
            continue
        raw_type = item.get("type")
        quote_type = raw_type if raw_type in _VALID_QUOTE_TYPES else "substantive"
        valid.append({"start_segment_id": start, "end_segment_id": end, "quote_type": quote_type})
    return valid


def _cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    norm_a = float(np.linalg.norm(a))
    norm_b = float(np.linalg.norm(b))
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return float(np.dot(a, b) / (norm_a * norm_b))


def _compute_narrative_score(
    quote_text: str,
    theme_embeddings: np.ndarray | None,
    embedding_model: SentenceTransformer,
) -> float:
    """Max cosine similarity between quote embedding and stored theme embeddings (D3)."""
    if theme_embeddings is None or len(theme_embeddings) == 0:
        return 0.0
    quote_emb = embedding_model.encode(
        quote_text, convert_to_numpy=True, show_progress_bar=False
    )
    sims = [_cosine_similarity(quote_emb, emb) for emb in theme_embeddings]
    return float(np.clip(max(sims), 0.0, 1.0))


def _find_notable_moment(
    start: int, end: int, notable_moments: list[NotableMoment]
) -> NotableMoment | None:
    """Return the first NotableMoment whose segment range overlaps [start, end] (D6)."""
    for m in notable_moments:
        if m.start_segment_id <= end and m.end_segment_id >= start:
            return m
    return None


def extract_phase2_chunk(
    chunk: Phase2Chunk,
    turn_group: list[TranscriptTurn],
    clusters: list[NarrativeCluster],
    chunk_notable_moments: list[NotableMoment],
    all_notable_moments: list[NotableMoment],
    segments_by_id: dict[int, TranscriptSegment],
    theme_embeddings: np.ndarray | None,
    embedding_model: SentenceTransformer,
    db,
) -> list[QuoteCandidate]:
    """Call Qwen for one Phase2Chunk; create QuoteCandidate rows with scoring."""
    chunk_text = chunk_text_for_qwen(turn_group)

    last_exc = None
    raw_output: list[dict] = []
    for attempt in range(settings.narrative_chunk_retries):
        try:
            raw_output = _call_qwen(chunk_text, clusters, chunk_notable_moments)
            break
        except Exception as exc:
            last_exc = exc
            logger.warning(
                "Phase 2 chunk %s attempt %d failed: %s", chunk.chunk_index, attempt + 1, exc
            )
            if attempt < settings.narrative_chunk_retries - 1:
                time.sleep(2 ** attempt)
    else:
        raise RuntimeError(
            f"Phase 2 chunk {chunk.chunk_index} failed after "
            f"{settings.narrative_chunk_retries} attempts: {last_exc}"
        )

    valid = _validate_candidates(raw_output, chunk.start_segment_id, chunk.end_segment_id)

    candidates: list[QuoteCandidate] = []
    for cand in valid:
        start_sid = cand["start_segment_id"]
        end_sid = cand["end_segment_id"]

        seg_range = [
            segments_by_id[sid]
            for sid in range(start_sid, end_sid + 1)
            if sid in segments_by_id
        ]
        if not seg_range:
            continue

        quote_text = " ".join(s.text for s in seg_range)
        speaker_label = seg_range[0].speaker_label

        score = _compute_narrative_score(quote_text, theme_embeddings, embedding_model)
        matching_moment = _find_notable_moment(start_sid, end_sid, all_notable_moments)

        candidate = QuoteCandidate(
            phase2_chunk_id=chunk.id,
            video_id=chunk.video_id,
            start_segment_id=start_sid,
            end_segment_id=end_sid,
            speaker_label=speaker_label,
            quote_type=cand["quote_type"],
            narrative_alignment_score=score,
            is_notable_moment=matching_moment is not None,
            notable_moment_id=matching_moment.id if matching_moment else None,
            raw_qwen_output={"candidates": raw_output},
            discarded=False,
            discard_reason=None,
        )
        db.add(candidate)
        candidates.append(candidate)

    db.flush()
    return candidates
