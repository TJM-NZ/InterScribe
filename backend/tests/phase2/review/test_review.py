"""Gate 3 — Phase 2 review API endpoints (SPEC-003)."""
import uuid
from datetime import datetime, timezone

import pytest

from app.models.phase1 import NotableMoment, TranscriptChunk
from app.models.phase2 import Phase2Chunk, Quote
from app.models.video import JobStatus, MediaType, Video


def _make_video(db, status=JobStatus.phase2_ready_for_review):
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
    start_seg=0,
    end_seg=2,
    score=0.8,
    is_notable=False,
    notable_moment_id=None,
    text="This is a great quote.",
    speaker="SPEAKER_01",
    quote_type="substantive",
):
    q = Quote(
        video_id=video_id,
        start_segment_id=start_seg,
        end_segment_id=end_seg,
        start_ts=float(start_seg),
        end_ts=float(end_seg + 1),
        quote_text=text,
        speaker_label=speaker,
        quote_type=quote_type,
        narrative_alignment_score=score,
        is_notable_moment=is_notable,
        notable_moment_id=notable_moment_id,
        source_candidate_ids=[str(uuid.uuid4())],
    )
    db.add(q)
    db.flush()
    return q


# --- GET /phase2/quotes ---


def test_get_quotes_notable_returns_only_notable_moment_quotes(client, db):
    v = _make_video(db)
    chunk = _make_phase2_chunk(db, v.id)
    _make_quote(db, v.id, chunk.id, start_seg=0, end_seg=2, score=0.9, is_notable=True)
    _make_quote(db, v.id, chunk.id, start_seg=3, end_seg=5, score=0.7, is_notable=False)
    db.commit()

    resp = client.get(f"/api/videos/{v.id}/phase2/quotes?view=notable")

    assert resp.status_code == 200
    quotes = resp.json()["quotes"]
    assert len(quotes) == 1
    assert quotes[0]["is_notable_moment"] is True


def test_get_quotes_notable_ordered_by_segment_id(client, db):
    v = _make_video(db)
    chunk = _make_phase2_chunk(db, v.id)
    _make_quote(db, v.id, chunk.id, start_seg=10, end_seg=12, score=0.9, is_notable=True)
    _make_quote(db, v.id, chunk.id, start_seg=3, end_seg=5, score=0.5, is_notable=True)
    db.commit()

    resp = client.get(f"/api/videos/{v.id}/phase2/quotes?view=notable")

    assert resp.status_code == 200
    segs = [q["start_segment_id"] for q in resp.json()["quotes"]]
    assert segs == sorted(segs)


def test_get_quotes_top_returns_all_sorted_by_score_desc(client, db):
    v = _make_video(db)
    chunk = _make_phase2_chunk(db, v.id)
    _make_quote(db, v.id, chunk.id, start_seg=0, end_seg=2, score=0.4)
    _make_quote(db, v.id, chunk.id, start_seg=3, end_seg=5, score=0.9)
    _make_quote(db, v.id, chunk.id, start_seg=6, end_seg=8, score=0.7)
    db.commit()

    resp = client.get(f"/api/videos/{v.id}/phase2/quotes?view=top")

    assert resp.status_code == 200
    scores = [q["narrative_alignment_score"] for q in resp.json()["quotes"]]
    assert scores == sorted(scores, reverse=True)
    assert len(scores) == 3


def test_get_quotes_top_with_limit_returns_limited(client, db):
    v = _make_video(db)
    chunk = _make_phase2_chunk(db, v.id)
    for i in range(5):
        _make_quote(db, v.id, chunk.id, start_seg=i * 3, end_seg=i * 3 + 2, score=float(i) / 5)
    db.commit()

    resp = client.get(f"/api/videos/{v.id}/phase2/quotes?view=top&limit=2")

    assert resp.status_code == 200
    assert len(resp.json()["quotes"]) == 2


def test_get_quotes_invalid_view_returns_400(client, db):
    v = _make_video(db)
    db.commit()

    resp = client.get(f"/api/videos/{v.id}/phase2/quotes?view=invalid")

    assert resp.status_code == 400
    assert resp.json()["detail"]["code"] == "INVALID_VIEW"


def test_get_quotes_missing_view_returns_400(client, db):
    v = _make_video(db)
    db.commit()

    resp = client.get(f"/api/videos/{v.id}/phase2/quotes")

    assert resp.status_code == 400
    assert resp.json()["detail"]["code"] == "INVALID_VIEW"


def test_get_quotes_status_not_ready_returns_409(client, db):
    v = _make_video(db, status=JobStatus.phase2_processing)
    db.commit()

    resp = client.get(f"/api/videos/{v.id}/phase2/quotes?view=top")

    assert resp.status_code == 409
    assert resp.json()["detail"]["code"] == "PHASE2_NOT_READY"


def test_get_quotes_available_after_phase2_reviewed(client, db):
    v = _make_video(db, status=JobStatus.phase2_reviewed)
    chunk = _make_phase2_chunk(db, v.id)
    _make_quote(db, v.id, chunk.id)
    db.commit()

    resp = client.get(f"/api/videos/{v.id}/phase2/quotes?view=top")

    assert resp.status_code == 200


def test_get_quotes_unknown_video_returns_404(client):
    resp = client.get(f"/api/videos/{uuid.uuid4()}/phase2/quotes?view=top")
    assert resp.status_code == 404
    assert resp.json()["detail"]["code"] == "NOT_FOUND"


def test_get_quotes_response_includes_all_fields(client, db):
    v = _make_video(db)
    chunk = _make_phase2_chunk(db, v.id)
    q = _make_quote(db, v.id, chunk.id, start_seg=2, end_seg=4, score=0.75, text="Great quote.", quote_type="headline")
    db.commit()

    resp = client.get(f"/api/videos/{v.id}/phase2/quotes?view=top")

    assert resp.status_code == 200
    quote = resp.json()["quotes"][0]
    assert quote["id"] == str(q.id)
    assert quote["quote_text"] == "Great quote."
    assert quote["start_segment_id"] == 2
    assert quote["end_segment_id"] == 4
    assert quote["narrative_alignment_score"] == 0.75
    assert quote["quote_type"] == "headline"
    assert quote["is_notable_moment"] is False
    assert quote["notable_moment_id"] is None
    assert quote["reviewed"] is False


# --- quote_type filter (SPEC-003-FIX-001) ---


def test_get_quotes_type_filter_headline(client, db):
    v = _make_video(db)
    chunk = _make_phase2_chunk(db, v.id)
    _make_quote(db, v.id, chunk.id, start_seg=0, end_seg=2, quote_type="headline")
    _make_quote(db, v.id, chunk.id, start_seg=3, end_seg=5, quote_type="substantive")
    db.commit()

    resp = client.get(f"/api/videos/{v.id}/phase2/quotes?view=top&type=headline")

    assert resp.status_code == 200
    quotes = resp.json()["quotes"]
    assert len(quotes) == 1
    assert quotes[0]["quote_type"] == "headline"


def test_get_quotes_type_filter_substantive(client, db):
    v = _make_video(db)
    chunk = _make_phase2_chunk(db, v.id)
    _make_quote(db, v.id, chunk.id, start_seg=0, end_seg=2, quote_type="headline")
    _make_quote(db, v.id, chunk.id, start_seg=3, end_seg=5, quote_type="substantive")
    db.commit()

    resp = client.get(f"/api/videos/{v.id}/phase2/quotes?view=top&type=substantive")

    assert resp.status_code == 200
    quotes = resp.json()["quotes"]
    assert len(quotes) == 1
    assert quotes[0]["quote_type"] == "substantive"


def test_get_quotes_no_type_filter_returns_all(client, db):
    v = _make_video(db)
    chunk = _make_phase2_chunk(db, v.id)
    _make_quote(db, v.id, chunk.id, start_seg=0, end_seg=2, quote_type="headline")
    _make_quote(db, v.id, chunk.id, start_seg=3, end_seg=5, quote_type="substantive")
    db.commit()

    resp = client.get(f"/api/videos/{v.id}/phase2/quotes?view=top")

    assert resp.status_code == 200
    assert len(resp.json()["quotes"]) == 2


def test_get_quotes_notable_with_type_filter(client, db):
    v = _make_video(db)
    chunk = _make_phase2_chunk(db, v.id)
    _make_quote(db, v.id, chunk.id, start_seg=0, end_seg=2, is_notable=True, quote_type="headline")
    _make_quote(db, v.id, chunk.id, start_seg=3, end_seg=5, is_notable=True, quote_type="substantive")
    _make_quote(db, v.id, chunk.id, start_seg=6, end_seg=8, is_notable=False, quote_type="headline")
    db.commit()

    resp = client.get(f"/api/videos/{v.id}/phase2/quotes?view=notable&type=headline")

    assert resp.status_code == 200
    quotes = resp.json()["quotes"]
    assert len(quotes) == 1
    assert quotes[0]["quote_type"] == "headline"
    assert quotes[0]["is_notable_moment"] is True


# --- POST /phase2/corrections ---


def test_correction_logged_on_quote_action(client, db):
    v = _make_video(db)
    chunk = _make_phase2_chunk(db, v.id)
    q = _make_quote(db, v.id, chunk.id, text="Quote text.")
    db.commit()

    resp = client.post(
        f"/api/videos/{v.id}/phase2/corrections",
        json={
            "entity_type": "quote",
            "entity_id": str(q.id),
            "field_name": None,
            "original_value": {"quote_text": "Quote text."},
            "corrected_value": None,
            "reason_category": "model_error",
            "reason_note": None,
        },
    )

    assert resp.status_code == 200
    assert "correction_id" in resp.json()


def test_correction_marks_quote_reviewed(client, db):
    v = _make_video(db)
    chunk = _make_phase2_chunk(db, v.id)
    q = _make_quote(db, v.id, chunk.id)
    db.commit()

    assert q.reviewed is False

    client.post(
        f"/api/videos/{v.id}/phase2/corrections",
        json={
            "entity_type": "quote",
            "entity_id": str(q.id),
            "field_name": None,
            "original_value": None,
            "corrected_value": None,
            "reason_category": "preference",
        },
    )

    db.expire(q)
    db.refresh(q)
    assert q.reviewed is True


def test_correction_blocked_when_wrong_entity_type(client, db):
    v = _make_video(db)
    chunk = _make_phase2_chunk(db, v.id)
    q = _make_quote(db, v.id, chunk.id)
    db.commit()

    resp = client.post(
        f"/api/videos/{v.id}/phase2/corrections",
        json={
            "entity_type": "narrative_cluster",
            "entity_id": str(q.id),
            "field_name": None,
            "original_value": None,
            "corrected_value": None,
            "reason_category": "model_error",
        },
    )

    assert resp.status_code == 400
    assert resp.json()["detail"]["code"] == "INVALID_ENTITY_TYPE"


def test_correction_blocked_when_entity_not_from_video(client, db):
    v = _make_video(db)
    other_v = _make_video(db)
    chunk = _make_phase2_chunk(db, other_v.id)
    q = _make_quote(db, other_v.id, chunk.id)
    db.commit()

    resp = client.post(
        f"/api/videos/{v.id}/phase2/corrections",
        json={
            "entity_type": "quote",
            "entity_id": str(q.id),
            "field_name": None,
            "original_value": None,
            "corrected_value": None,
            "reason_category": "model_error",
        },
    )

    assert resp.status_code == 400
    assert resp.json()["detail"]["code"] == "INVALID_ENTITY"


def test_correction_blocked_without_reason_category(client, db):
    v = _make_video(db)
    chunk = _make_phase2_chunk(db, v.id)
    q = _make_quote(db, v.id, chunk.id)
    db.commit()

    resp = client.post(
        f"/api/videos/{v.id}/phase2/corrections",
        json={
            "entity_type": "quote",
            "entity_id": str(q.id),
            "field_name": None,
            "original_value": None,
            "corrected_value": None,
        },
    )

    assert resp.status_code == 422


def test_correction_blocked_after_phase2_reviewed(client, db):
    v = _make_video(db, status=JobStatus.phase2_reviewed)
    chunk = _make_phase2_chunk(db, v.id)
    q = _make_quote(db, v.id, chunk.id)
    db.commit()

    resp = client.post(
        f"/api/videos/{v.id}/phase2/corrections",
        json={
            "entity_type": "quote",
            "entity_id": str(q.id),
            "field_name": None,
            "original_value": None,
            "corrected_value": None,
            "reason_category": "preference",
        },
    )

    assert resp.status_code == 409
    assert resp.json()["detail"]["code"] == "PHASE2_ALREADY_REVIEWED"


def test_correction_blocked_when_not_at_phase2_ready(client, db):
    v = _make_video(db, status=JobStatus.phase2_processing)
    chunk = _make_phase2_chunk(db, v.id)
    q = _make_quote(db, v.id, chunk.id)
    db.commit()

    resp = client.post(
        f"/api/videos/{v.id}/phase2/corrections",
        json={
            "entity_type": "quote",
            "entity_id": str(q.id),
            "field_name": None,
            "original_value": None,
            "corrected_value": None,
            "reason_category": "model_error",
        },
    )

    assert resp.status_code == 409
    assert resp.json()["detail"]["code"] == "PHASE2_NOT_READY"


# --- POST /phase2/confirm-review ---


def test_confirm_review_transitions_to_phase2_reviewed(client, db):
    v = _make_video(db)
    db.commit()

    resp = client.post(f"/api/videos/{v.id}/phase2/confirm-review")

    assert resp.status_code == 200
    assert resp.json()["status"] == "phase2_reviewed"

    db.expire(v)
    db.refresh(v)
    assert v.status == JobStatus.phase2_reviewed


def test_confirm_review_blocked_if_not_phase2_ready(client, db):
    v = _make_video(db, status=JobStatus.phase2_processing)
    db.commit()

    resp = client.post(f"/api/videos/{v.id}/phase2/confirm-review")

    assert resp.status_code == 409
    assert resp.json()["detail"]["code"] == "PHASE2_NOT_READY"


def test_confirm_review_not_found(client):
    resp = client.post(f"/api/videos/{uuid.uuid4()}/phase2/confirm-review")
    assert resp.status_code == 404
    assert resp.json()["detail"]["code"] == "NOT_FOUND"
