"""Condensation pipeline: distil headline Quote rows via Qwen3.5:9b (SPEC-004)."""
import logging
import re
import time

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.models.phase1 import NarrativeCluster
from app.models.phase2 import Quote, QuoteType
from app.models.video import JobStatus, Video

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = (
    "You are an expert at distilling interview quotes into punchy, memorable headlines. "
    "Return ONLY the condensed text."
)

_USER_TEMPLATE = """\
NARRATIVE CONTEXT — dominant themes in this interview:
{cluster_context}

Condense this quote to 20 words or fewer, preserving the speaker's voice:

{quote_text}"""


def _format_cluster_context(clusters: list[NarrativeCluster]) -> str:
    if not clusters:
        return "(no narrative context available)"
    return "\n".join(f"{c.rank}. {c.representative_label}" for c in clusters)


def _strip_think(text: str) -> str:
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL)
    return text.strip()


def _call_qwen(quote_text: str, clusters: list[NarrativeCluster]) -> str:
    user_content = _USER_TEMPLATE.format(
        cluster_context=_format_cluster_context(clusters),
        quote_text=quote_text,
    )
    payload = {
        "model": settings.qwen_model,
        "messages": [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": user_content},
        ],
        "stream": False,
        "think": False,
        "options": {"num_ctx": 4096},
    }
    resp = httpx.post(
        f"{settings.ollama_base_url}/api/chat",
        json=payload,
        timeout=600,
    )
    resp.raise_for_status()
    return _strip_think(resp.json()["message"]["content"])


def _truncate_to_20_words(text: str, quote_id) -> str:
    words = text.split()
    if len(words) > 20:
        logger.warning(
            "Qwen returned %d words for headline quote %s — truncating to 20",
            len(words),
            quote_id,
        )
        return " ".join(words[:20])
    return text


def process_condensation(video: Video, db: Session) -> None:
    clusters = (
        db.execute(
            select(NarrativeCluster)
            .where(NarrativeCluster.video_id == video.id)
            .order_by(NarrativeCluster.rank)
            .limit(settings.narrative_top_n)
        )
        .scalars()
        .all()
    )

    headline_quotes = (
        db.execute(
            select(Quote)
            .where(Quote.video_id == video.id)
            .where(Quote.quote_type == QuoteType.headline)
            .order_by(Quote.narrative_alignment_score.desc())
        )
        .scalars()
        .all()
    )

    for quote in headline_quotes:
        last_exc = None
        for attempt in range(settings.narrative_chunk_retries):
            try:
                condensed = _call_qwen(quote.quote_text, clusters)
                break
            except Exception as exc:
                last_exc = exc
                logger.warning(
                    "Condensation attempt %d failed for quote %s: %s",
                    attempt + 1,
                    quote.id,
                    exc,
                )
                if attempt < settings.narrative_chunk_retries - 1:
                    time.sleep(2 ** attempt)
        else:
            raise RuntimeError(
                f"Condensation failed for quote {quote.id} after "
                f"{settings.narrative_chunk_retries} attempts: {last_exc}"
            )

        quote.headline_text = _truncate_to_20_words(condensed, quote.id)

    db.commit()
    video.status = JobStatus.condensation_ready_for_review
    video.error_reason = None
    db.commit()
    logger.info(
        "Condensation complete for video %s (%d headlines)", video.id, len(headline_quotes)
    )
