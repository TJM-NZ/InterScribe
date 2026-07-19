"""Gate 2 — condensation review API endpoints (SPEC-004)."""
import uuid
from datetime import datetime, timezone

import pytest

from app.models.phase2 import Phase2Chunk, Quote
from app.models.video import JobStatus, MediaType, Video


def _make_video(db, status=JobStatus.condensation_ready_for_review):
    v = Video(
        original_filename="t.wav",
        storage_path="/fake/t.wav",
        media_type=MediaType.audio,
        status=status,
        uploaded_at=datetime.now(timezone.utc),
    )
    db.add(v)
    db.flush()
    return v


def _make_phase2_chunk(db, video_id):
    c = Phase2Chunk(
        video_id=video_id,
        chunk_index=0,
        start_segment_id=0,
        end_segment_id=9,
        token_count=500,
    )
    db.add(c)
    db.flush()
    return c


def _make_quote(
    db,
    video_id,
    chunk_id,
    quote_type="headline",
    headline_text="AI scales beyond expectations.",
    score=0.8,
):
    q = Quote(
        video_id=video_id,
        start_segment_id=0,
        end_segment_id=2,
        start_ts=0.0,
        end_ts=3.0,
        quote_text="The actual verbatim quote text from the speaker.",
        speaker_label="SPEAKER_01",
        quote_type=quote_type,
        headline_text=headline_text,
        narrative_alignment_score=score,
        is_notable_moment=False,
        source_candidate_ids=[str(uuid.uuid4())],
    )
    db.add(q)
    db.flush()
    return q


# --- GET /condensation/headlines ---


def test_get_headlines_returns_only_headline_quotes(client, db):
    v = _make_video(db)
    chunk = _make_phase2_chunk(db, v.id)
    _make_quote(db, v.id, chunk.id, quote_type="headline", score=0.9)
    _make_quote(db, v.id, chunk.id, quote_type="substantive", headline_text=None, score=0.7)
    db.commit()

    resp = client.get(f"/api/videos/{v.id}/condensation/headlines")

    assert resp.status_code == 200
    quotes = resp.json()["quotes"]
    assert len(quotes) == 1
    assert quotes[0]["quote_type"] == "headline"


def test_get_headlines_ordered_by_score_desc(client, db):
    v = _make_video(db)
    chunk = _make_phase2_chunk(db, v.id)
    _make_quote(db, v.id, chunk.id, quote_type="headline", score=0.5)
    _make_quote(db, v.id, chunk.id, quote_type="headline", score=0.9)
    db.commit()

    resp = client.get(f"/api/videos/{v.id}/condensation/headlines")

    assert resp.status_code == 200
    scores = [q["narrative_alignment_score"] for q in resp.json()["quotes"]]
    assert scores == sorted(scores, reverse=True)


def test_get_headlines_includes_headline_text_field(client, db):
    v = _make_video(db)
    chunk = _make_phase2_chunk(db, v.id)
    _make_quote(db, v.id, chunk.id, headline_text="AI scales beyond all expectations.")
    db.commit()

    resp = client.get(f"/api/videos/{v.id}/condensation/headlines")

    assert resp.status_code == 200
    quote = resp.json()["quotes"][0]
    assert "headline_text" in quote
    assert quote["headline_text"] == "AI scales beyond all expectations."
    assert "quote_text" in quote


def test_get_headlines_status_not_ready_returns_409(client, db):
    v = _make_video(db, status=JobStatus.condensation_processing)
    db.commit()

    resp = client.get(f"/api/videos/{v.id}/condensation/headlines")

    assert resp.status_code == 409
    assert resp.json()["detail"]["code"] == "CONDENSATION_NOT_READY"


def test_get_headlines_available_after_condensation_reviewed(client, db):
    v = _make_video(db, status=JobStatus.condensation_reviewed)
    chunk = _make_phase2_chunk(db, v.id)
    _make_quote(db, v.id, chunk.id)
    db.commit()

    resp = client.get(f"/api/videos/{v.id}/condensation/headlines")

    assert resp.status_code == 200


def test_get_headlines_unknown_video_returns_404(client):
    resp = client.get(f"/api/videos/{uuid.uuid4()}/condensation/headlines")
    assert resp.status_code == 404
    assert resp.json()["detail"]["code"] == "NOT_FOUND"


# --- POST /condensation/corrections ---


def test_headline_edit_correction_updates_headline_text(client, db):
    v = _make_video(db)
    chunk = _make_phase2_chunk(db, v.id)
    q = _make_quote(db, v.id, chunk.id, headline_text="Original headline.")
    db.commit()

    resp = client.post(
        f"/api/videos/{v.id}/condensation/corrections",
        json={
            "entity_type": "headline_condensation",
            "entity_id": str(q.id),
            "field_name": "headline_text",
            "original_value": {"headline_text": "Original headline."},
            "corrected_value": {"headline_text": "Updated headline text."},
            "reason_category": "model_error",
            "reason_note": None,
        },
    )

    assert resp.status_code == 200
    assert "correction_id" in resp.json()

    db.expire(q)
    db.refresh(q)
    assert q.headline_text == "Updated headline text."


def test_quote_type_downgrade_clears_headline_text(client, db):
    v = _make_video(db)
    chunk = _make_phase2_chunk(db, v.id)
    q = _make_quote(db, v.id, chunk.id, quote_type="headline", headline_text="Some headline.")
    db.commit()

    resp = client.post(
        f"/api/videos/{v.id}/condensation/corrections",
        json={
            "entity_type": "headline_condensation",
            "entity_id": str(q.id),
            "field_name": "quote_type",
            "original_value": {"quote_type": "headline"},
            "corrected_value": {"quote_type": "substantive"},
            "reason_category": "preference",
            "reason_note": None,
        },
    )

    assert resp.status_code == 200

    db.expire(q)
    db.refresh(q)
    assert q.quote_type == "substantive"
    assert q.headline_text is None


def test_correction_creates_correction_row(client, db):
    from app.models.phase1 import Correction, CorrectionEntityType

    v = _make_video(db)
    chunk = _make_phase2_chunk(db, v.id)
    q = _make_quote(db, v.id, chunk.id)
    db.commit()

    client.post(
        f"/api/videos/{v.id}/condensation/corrections",
        json={
            "entity_type": "headline_condensation",
            "entity_id": str(q.id),
            "field_name": "headline_text",
            "original_value": {"headline_text": "Old headline."},
            "corrected_value": {"headline_text": "New headline."},
            "reason_category": "preference",
            "reason_note": "Better wording",
        },
    )

    from sqlalchemy import select
    corrections = db.execute(
        select(Correction).where(Correction.video_id == v.id)
    ).scalars().all()
    assert len(corrections) == 1
    assert corrections[0].entity_type == CorrectionEntityType.headline_condensation
    assert corrections[0].field_name == "headline_text"


def test_correction_blocked_wrong_entity_type(client, db):
    v = _make_video(db)
    chunk = _make_phase2_chunk(db, v.id)
    q = _make_quote(db, v.id, chunk.id)
    db.commit()

    resp = client.post(
        f"/api/videos/{v.id}/condensation/corrections",
        json={
            "entity_type": "quote",
            "entity_id": str(q.id),
            "field_name": "headline_text",
            "original_value": None,
            "corrected_value": None,
            "reason_category": "model_error",
        },
    )

    assert resp.status_code == 400
    assert resp.json()["detail"]["code"] == "INVALID_ENTITY_TYPE"


def test_correction_blocked_when_entity_not_headline(client, db):
    v = _make_video(db)
    chunk = _make_phase2_chunk(db, v.id)
    q = _make_quote(db, v.id, chunk.id, quote_type="substantive", headline_text=None)
    db.commit()

    resp = client.post(
        f"/api/videos/{v.id}/condensation/corrections",
        json={
            "entity_type": "headline_condensation",
            "entity_id": str(q.id),
            "field_name": "headline_text",
            "original_value": None,
            "corrected_value": {"headline_text": "text"},
            "reason_category": "model_error",
        },
    )

    assert resp.status_code == 400
    assert resp.json()["detail"]["code"] == "INVALID_ENTITY"


def test_correction_blocked_when_entity_not_from_video(client, db):
    v = _make_video(db)
    other_v = _make_video(db)
    chunk = _make_phase2_chunk(db, other_v.id)
    q = _make_quote(db, other_v.id, chunk.id)
    db.commit()

    resp = client.post(
        f"/api/videos/{v.id}/condensation/corrections",
        json={
            "entity_type": "headline_condensation",
            "entity_id": str(q.id),
            "field_name": "headline_text",
            "original_value": None,
            "corrected_value": {"headline_text": "text"},
            "reason_category": "model_error",
        },
    )

    assert resp.status_code == 400
    assert resp.json()["detail"]["code"] == "INVALID_ENTITY"


def test_correction_blocked_after_condensation_reviewed(client, db):
    v = _make_video(db, status=JobStatus.condensation_reviewed)
    chunk = _make_phase2_chunk(db, v.id)
    q = _make_quote(db, v.id, chunk.id)
    db.commit()

    resp = client.post(
        f"/api/videos/{v.id}/condensation/corrections",
        json={
            "entity_type": "headline_condensation",
            "entity_id": str(q.id),
            "field_name": "headline_text",
            "original_value": None,
            "corrected_value": {"headline_text": "text"},
            "reason_category": "preference",
        },
    )

    assert resp.status_code == 409
    assert resp.json()["detail"]["code"] == "CONDENSATION_ALREADY_REVIEWED"


def test_correction_blocked_when_not_at_condensation_ready(client, db):
    v = _make_video(db, status=JobStatus.condensation_processing)
    chunk = _make_phase2_chunk(db, v.id)
    q = _make_quote(db, v.id, chunk.id)
    db.commit()

    resp = client.post(
        f"/api/videos/{v.id}/condensation/corrections",
        json={
            "entity_type": "headline_condensation",
            "entity_id": str(q.id),
            "field_name": "headline_text",
            "original_value": None,
            "corrected_value": {"headline_text": "text"},
            "reason_category": "preference",
        },
    )

    assert resp.status_code == 409
    assert resp.json()["detail"]["code"] == "CONDENSATION_NOT_READY"


def test_correction_blocked_without_reason_category(client, db):
    v = _make_video(db)
    chunk = _make_phase2_chunk(db, v.id)
    q = _make_quote(db, v.id, chunk.id)
    db.commit()

    resp = client.post(
        f"/api/videos/{v.id}/condensation/corrections",
        json={
            "entity_type": "headline_condensation",
            "entity_id": str(q.id),
            "field_name": "headline_text",
            "original_value": None,
            "corrected_value": {"headline_text": "text"},
        },
    )

    assert resp.status_code == 422


# --- POST /condensation/confirm-review ---


def test_confirm_review_transitions_to_condensation_reviewed(client, db):
    v = _make_video(db)
    db.commit()

    resp = client.post(f"/api/videos/{v.id}/condensation/confirm-review")

    assert resp.status_code == 200
    assert resp.json()["status"] == "condensation_reviewed"

    db.expire(v)
    db.refresh(v)
    assert v.status == JobStatus.condensation_reviewed


def test_confirm_review_blocked_if_not_condensation_ready(client, db):
    v = _make_video(db, status=JobStatus.condensation_processing)
    db.commit()

    resp = client.post(f"/api/videos/{v.id}/condensation/confirm-review")

    assert resp.status_code == 409
    assert resp.json()["detail"]["code"] == "CONDENSATION_NOT_READY"


def test_confirm_review_not_found(client):
    resp = client.post(f"/api/videos/{uuid.uuid4()}/condensation/confirm-review")
    assert resp.status_code == 404
    assert resp.json()["detail"]["code"] == "NOT_FOUND"


def test_confirm_review_blocks_further_corrections(client, db):
    v = _make_video(db)
    chunk = _make_phase2_chunk(db, v.id)
    q = _make_quote(db, v.id, chunk.id)
    db.commit()

    client.post(f"/api/videos/{v.id}/condensation/confirm-review")

    resp = client.post(
        f"/api/videos/{v.id}/condensation/corrections",
        json={
            "entity_type": "headline_condensation",
            "entity_id": str(q.id),
            "field_name": "headline_text",
            "original_value": None,
            "corrected_value": {"headline_text": "text"},
            "reason_category": "preference",
        },
    )

    assert resp.status_code == 409
    assert resp.json()["detail"]["code"] == "CONDENSATION_ALREADY_REVIEWED"


def test_phase2_confirm_review_enqueues_condensation(client, db):
    """confirm_phase2_review transitions DB to condensation_queued, response says phase2_reviewed."""
    v = _make_video(db, status=JobStatus.phase2_ready_for_review)
    db.commit()

    resp = client.post(f"/api/videos/{v.id}/phase2/confirm-review")

    assert resp.status_code == 200
    assert resp.json()["status"] == "phase2_reviewed"

    db.expire(v)
    db.refresh(v)
    assert v.status == JobStatus.condensation_queued
