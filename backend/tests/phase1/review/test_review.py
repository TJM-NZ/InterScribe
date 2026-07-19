"""Gate 3 — Phase 1 review API endpoints."""
import uuid
from datetime import datetime, timezone

import pytest

from app.models.phase1 import (
    ChunkNarrative,
    NarrativeCluster,
    NotableMoment,
    TranscriptChunk,
)
from app.models.video import JobStatus, MediaType, Video


def _make_video(db, status=JobStatus.phase1_ready_for_review):
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


def _add_cluster(db, video_id, rank=1, label="AI / technical"):
    cluster = NarrativeCluster(
        video_id=video_id,
        representative_label=label,
        cluster_size=2,
        rank=rank,
    )
    db.add(cluster)
    db.flush()
    return cluster


def _add_chunk(db, video_id, chunk_index=0):
    c = TranscriptChunk(
        video_id=video_id,
        chunk_index=chunk_index,
        start_segment_id=0,
        end_segment_id=9,
        token_count=500,
    )
    db.add(c)
    db.flush()
    return c


def _add_moment(db, video_id, chunk_id, start_seg=0, end_seg=2):
    m = NotableMoment(
        chunk_id=chunk_id,
        video_id=video_id,
        start_segment_id=start_seg,
        end_segment_id=end_seg,
        description="A key insight",
    )
    db.add(m)
    db.flush()
    return m


# --- GET /phase1/narrative ---

def test_get_narrative_returns_clusters_and_moments(client, db):
    v = _make_video(db)
    _add_cluster(db, v.id)
    chunk = _add_chunk(db, v.id)
    _add_moment(db, v.id, chunk.id)
    db.commit()

    resp = client.get(f"/api/videos/{v.id}/phase1/narrative")

    assert resp.status_code == 200
    data = resp.json()
    assert len(data["clusters"]) == 1
    assert len(data["notable_moments"]) == 1


def test_get_narrative_clusters_ordered_by_rank(client, db):
    v = _make_video(db)
    _add_cluster(db, v.id, rank=2, label="Second")
    _add_cluster(db, v.id, rank=1, label="First")
    db.commit()

    resp = client.get(f"/api/videos/{v.id}/phase1/narrative")

    assert resp.status_code == 200
    ranks = [c["rank"] for c in resp.json()["clusters"]]
    assert ranks == sorted(ranks)


def test_get_narrative_blocked_before_phase1_ready(client, db):
    v = _make_video(db, status=JobStatus.phase1_processing)
    db.commit()

    resp = client.get(f"/api/videos/{v.id}/phase1/narrative")

    assert resp.status_code == 409
    assert resp.json()["detail"]["code"] == "PHASE1_NOT_READY"


def test_get_narrative_available_after_phase1_reviewed(client, db):
    v = _make_video(db, status=JobStatus.phase1_reviewed)
    _add_cluster(db, v.id)
    db.commit()

    resp = client.get(f"/api/videos/{v.id}/phase1/narrative")

    assert resp.status_code == 200


# --- POST /phase1/corrections ---

def test_correction_logged_on_cluster_edit(client, db):
    v = _make_video(db)
    cluster = _add_cluster(db, v.id)
    db.commit()

    resp = client.post(
        f"/api/videos/{v.id}/phase1/corrections",
        json={
            "entity_type": "narrative_cluster",
            "entity_id": str(cluster.id),
            "field_name": "representative_label",
            "original_value": {"representative_label": "AI / technical"},
            "corrected_value": {"representative_label": "Machine Learning"},
            "reason_category": "model_error",
        },
    )

    assert resp.status_code == 200
    assert "correction_id" in resp.json()


def test_correction_updates_cluster_label(client, db):
    v = _make_video(db)
    cluster = _add_cluster(db, v.id, label="Old Label")
    db.commit()

    client.post(
        f"/api/videos/{v.id}/phase1/corrections",
        json={
            "entity_type": "narrative_cluster",
            "entity_id": str(cluster.id),
            "field_name": "representative_label",
            "original_value": {"representative_label": "Old Label"},
            "corrected_value": {"representative_label": "New Label"},
            "reason_category": "preference",
        },
    )

    db.expire(cluster)
    db.refresh(cluster)
    assert cluster.representative_label == "New Label"


def test_correction_marks_notable_moment_reviewed(client, db):
    v = _make_video(db)
    chunk = _add_chunk(db, v.id)
    moment = _add_moment(db, v.id, chunk.id)
    db.commit()

    assert moment.reviewed is False

    client.post(
        f"/api/videos/{v.id}/phase1/corrections",
        json={
            "entity_type": "notable_moment",
            "entity_id": str(moment.id),
            "field_name": None,
            "original_value": {"description": "A key insight"},
            "corrected_value": None,
            "reason_category": "edge_case",
        },
    )

    db.expire(moment)
    db.refresh(moment)
    assert moment.reviewed is True


def test_correction_rejected_without_reason_category(client, db):
    v = _make_video(db)
    cluster = _add_cluster(db, v.id)
    db.commit()

    resp = client.post(
        f"/api/videos/{v.id}/phase1/corrections",
        json={
            "entity_type": "narrative_cluster",
            "entity_id": str(cluster.id),
            "field_name": "representative_label",
            "original_value": {"representative_label": "x"},
            "corrected_value": {"representative_label": "y"},
            # reason_category missing
        },
    )

    assert resp.status_code == 422


def test_correction_rejected_with_invalid_entity_id(client, db):
    v = _make_video(db)
    db.commit()

    resp = client.post(
        f"/api/videos/{v.id}/phase1/corrections",
        json={
            "entity_type": "narrative_cluster",
            "entity_id": str(uuid.uuid4()),
            "field_name": "representative_label",
            "original_value": {"representative_label": "x"},
            "corrected_value": {"representative_label": "y"},
            "reason_category": "model_error",
        },
    )

    assert resp.status_code == 400
    assert resp.json()["detail"]["code"] == "INVALID_ENTITY"


def test_correction_blocked_after_phase1_reviewed(client, db):
    v = _make_video(db, status=JobStatus.phase1_reviewed)
    cluster = _add_cluster(db, v.id)
    db.commit()

    resp = client.post(
        f"/api/videos/{v.id}/phase1/corrections",
        json={
            "entity_type": "narrative_cluster",
            "entity_id": str(cluster.id),
            "field_name": "representative_label",
            "original_value": {"representative_label": "x"},
            "corrected_value": {"representative_label": "y"},
            "reason_category": "preference",
        },
    )

    assert resp.status_code == 409
    assert resp.json()["detail"]["code"] == "PHASE1_ALREADY_REVIEWED"


# --- POST /phase1/confirm-review ---

def test_confirm_review_transitions_to_phase1_reviewed(client, db):
    v = _make_video(db)
    db.commit()

    resp = client.post(f"/api/videos/{v.id}/phase1/confirm-review")

    assert resp.status_code == 200
    assert resp.json()["status"] == "phase1_reviewed"  # response body = what was confirmed

    # D4 (SPEC-003): DB must be phase2_queued immediately after confirm
    db.expire(v)
    db.refresh(v)
    assert v.status == JobStatus.phase2_queued


def test_confirm_review_blocked_if_not_phase1_ready(client, db):
    v = _make_video(db, status=JobStatus.phase1_processing)
    db.commit()

    resp = client.post(f"/api/videos/{v.id}/phase1/confirm-review")

    assert resp.status_code == 409


def test_confirm_review_not_found(client):
    resp = client.post(f"/api/videos/{uuid.uuid4()}/phase1/confirm-review")
    assert resp.status_code == 404


def test_phase1_auto_enqueued_after_spec1_confirm_review(client, db):
    """Spec 1 confirm-review triggers phase1_queued as a side effect (D3)."""
    from app.models.video import SpeakerRoleMap, TranscriptSegment

    # Set up reviewed video
    from tests.conftest import seed_video_with_segments
    v = seed_video_with_segments(db, status=JobStatus.ready_for_review)
    db.commit()

    resp = client.post(f"/api/videos/{v.id}/confirm-review")

    assert resp.status_code == 200
    assert resp.json()["status"] == "phase1_queued"

    db.expire(v)
    db.refresh(v)
    assert v.status == JobStatus.phase1_queued
