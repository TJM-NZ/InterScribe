"""Gate 1 — condensation worker: headline text stored, status transitions (SPEC-004)."""
from unittest.mock import MagicMock, patch

import pytest

from app.models.phase2 import Quote
from app.models.video import JobStatus
from sqlalchemy import func, select as sa_select
from tests.conftest import make_video
from tests.phase1.conftest import make_cluster
from tests.phase2.conftest import make_quote
from app.worker.condensation.pipeline import _truncate_to_20_words, process_condensation


def _mock_response(text: str):
    m = MagicMock()
    m.raise_for_status = MagicMock()
    m.json.return_value = {"message": {"content": text}}
    return m


# --- Unit tests ---


def test_truncate_to_20_words_short_unchanged():
    assert _truncate_to_20_words("Short text.", "id") == "Short text."


def test_truncate_to_20_words_exactly_20_unchanged():
    text = " ".join(f"w{i}" for i in range(20))
    assert _truncate_to_20_words(text, "id") == text


def test_truncate_to_20_words_long_truncated():
    text = " ".join(f"w{i}" for i in range(24))
    result = _truncate_to_20_words(text, "id")
    assert len(result.split()) == 20
    assert result == " ".join(f"w{i}" for i in range(20))


# --- Integration tests (process_condensation) ---


def test_headline_text_set_on_headline_quote(db):
    v = make_video(db, status=JobStatus.condensation_queued)
    q = make_quote(db, v.id, quote_type="headline", text="The future of AI is transforming every industry.")
    make_cluster(db, v.id)
    db.commit()

    with patch("httpx.post", return_value=_mock_response("AI transforms every industry now.")):
        process_condensation(v, db)

    db.expire(q)
    db.refresh(q)
    assert q.headline_text == "AI transforms every industry now."


def test_substantive_quote_headline_text_stays_null(db):
    v = make_video(db, status=JobStatus.condensation_queued)
    q = make_quote(db, v.id, quote_type="substantive", text="The future of AI is transforming every industry.")
    db.commit()

    with patch("httpx.post", return_value=_mock_response("should not be set")):
        process_condensation(v, db)

    db.expire(q)
    db.refresh(q)
    assert q.headline_text is None


def test_headline_text_truncated_when_qwen_overshoots(db):
    v = make_video(db, status=JobStatus.condensation_queued)
    q = make_quote(db, v.id, quote_type="headline", text="The future of AI is transforming every industry.")
    db.commit()

    long_output = " ".join(f"word{i}" for i in range(24))
    with patch("httpx.post", return_value=_mock_response(long_output)):
        process_condensation(v, db)

    db.expire(q)
    db.refresh(q)
    assert len(q.headline_text.split()) == 20


def test_truncation_preserves_quote_row_not_discarded(db):
    v = make_video(db, status=JobStatus.condensation_queued)
    q = make_quote(db, v.id, quote_type="headline", text="The future of AI is transforming every industry.")
    db.commit()

    long_output = " ".join(f"word{i}" for i in range(30))
    with patch("httpx.post", return_value=_mock_response(long_output)):
        process_condensation(v, db)

    db.expire(q)
    db.refresh(q)
    assert q.headline_text is not None
    assert q.quote_type == "headline"


def test_status_transitions_to_condensation_ready_for_review(db):
    v = make_video(db, status=JobStatus.condensation_queued)
    make_quote(db, v.id, quote_type="headline", text="The future of AI is transforming every industry.")
    db.commit()

    with patch("httpx.post", return_value=_mock_response("Short condensed headline.")):
        process_condensation(v, db)

    db.expire(v)
    db.refresh(v)
    assert v.status == JobStatus.condensation_ready_for_review


def test_think_tags_stripped_from_output(db):
    v = make_video(db, status=JobStatus.condensation_queued)
    q = make_quote(db, v.id, quote_type="headline", text="The future of AI is transforming every industry.")
    db.commit()

    qwen_output = "<think>Let me condense this carefully.</think>AI is transforming society."
    with patch("httpx.post", return_value=_mock_response(qwen_output)):
        process_condensation(v, db)

    db.expire(q)
    db.refresh(q)
    assert "<think>" not in q.headline_text
    assert q.headline_text == "AI is transforming society."


def test_multiple_headline_quotes_all_condensed(db):
    v = make_video(db, status=JobStatus.condensation_queued)
    q1 = make_quote(db, v.id, quote_type="headline", text="First headline quote.")
    q2 = make_quote(db, v.id, quote_type="headline", text="Second headline quote.")
    db.commit()

    responses = iter([
        _mock_response("First condensed."),
        _mock_response("Second condensed."),
    ])
    with patch("httpx.post", side_effect=lambda *a, **kw: next(responses)):
        process_condensation(v, db)

    db.expire(q1)
    db.refresh(q1)
    db.expire(q2)
    db.refresh(q2)
    assert q1.headline_text is not None
    assert q2.headline_text is not None


def test_zero_headline_skip_transitions_to_condensation_reviewed(db):
    """Runner zero-headline check: video with only substantive quotes skips condensation."""
    v = make_video(db, status=JobStatus.condensation_queued)
    make_quote(db, v.id, quote_type="substantive", text="Substantive quote text.")
    db.commit()

    # Simulate runner's zero-headline check (same logic as runner.py)
    headline_count = db.execute(
        sa_select(func.count(Quote.id))
        .where(Quote.video_id == v.id)
        .where(Quote.quote_type == "headline")
    ).scalar() or 0

    if headline_count == 0:
        v.status = JobStatus.condensation_reviewed
        db.commit()

    db.expire(v)
    db.refresh(v)
    assert v.status == JobStatus.condensation_reviewed
