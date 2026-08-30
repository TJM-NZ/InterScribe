import uuid
from datetime import datetime, timezone

import pytest

from app.models.video import (
    JobStatus, MediaType, SpeakerRoleMap, TranscriptSegment, Video,
)


def _seed_video(db, status=JobStatus.ready_for_review, speakers=None) -> Video:
    video = Video(
        original_filename="interview.wav",
        storage_path="/fake/path/interview.wav",
        media_type=MediaType.audio,
        status=status,
        uploaded_at=datetime.now(timezone.utc),
    )
    db.add(video)
    db.flush()

    labels = speakers or ["SPEAKER_00", "SPEAKER_01"]
    for idx, label in enumerate(labels):
        db.add(TranscriptSegment(
            video_id=video.id,
            segment_id=idx,
            start_ts=float(idx),
            end_ts=float(idx + 1),
            text=f"Utterance {idx}",
            speaker_label=label,
            confidence=0.9,
        ))

    db.commit()
    db.refresh(video)
    return video


def test_get_transcript_returns_segments(client, db):
    video = _seed_video(db)

    resp = client.get(f"/api/videos/{video.id}/transcript")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["segments"]) == 2
    assert data["segments"][0]["segment_id"] == 0
    assert data["segments"][1]["segment_id"] == 1


def test_get_transcript_blocked_before_ready(client, db):
    video = _seed_video(db, status=JobStatus.transcribing)

    resp = client.get(f"/api/videos/{video.id}/transcript")
    assert resp.status_code == 409
    assert resp.json()["detail"]["code"] == "TRANSCRIPT_NOT_READY"


def test_speaker_role_assignment_updates_map(client, db):
    video = _seed_video(db, speakers=["SPEAKER_00", "SPEAKER_01"])

    resp = client.patch(
        f"/api/videos/{video.id}/speakers",
        json={
            "assignments": [
                {"speaker_label": "SPEAKER_00", "role": "interviewer"},
                {"speaker_label": "SPEAKER_01", "role": "interviewee"},
            ]
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["video_id"] == str(video.id)
    roles = {item["speaker_label"]: item["role"] for item in data["speaker_role_map"]}
    assert roles["SPEAKER_00"] == "interviewer"
    assert roles["SPEAKER_01"] == "interviewee"


def test_speaker_assignment_unknown_label_rejected(client, db):
    video = _seed_video(db, speakers=["SPEAKER_00"])

    resp = client.patch(
        f"/api/videos/{video.id}/speakers",
        json={"assignments": [{"speaker_label": "SPEAKER_99", "role": "interviewer"}]},
    )
    assert resp.status_code == 400
    assert resp.json()["detail"]["code"] == "UNKNOWN_SPEAKER_LABEL"


def test_speaker_assignment_blocked_before_ready(client, db):
    video = _seed_video(db, status=JobStatus.queued)

    resp = client.patch(
        f"/api/videos/{video.id}/speakers",
        json={"assignments": [{"speaker_label": "SPEAKER_00", "role": "interviewer"}]},
    )
    assert resp.status_code == 409


def test_confirm_review_blocked_until_all_speakers_mapped(client, db):
    video = _seed_video(db, speakers=["SPEAKER_00", "SPEAKER_01", "SPEAKER_02"])

    client.patch(
        f"/api/videos/{video.id}/speakers",
        json={"assignments": [
            {"speaker_label": "SPEAKER_00", "role": "interviewer"},
            {"speaker_label": "SPEAKER_01", "role": "interviewee"},
        ]},
    )

    resp = client.post(f"/api/videos/{video.id}/confirm-review")
    assert resp.status_code == 409
    assert resp.json()["detail"]["code"] == "SPEAKERS_UNMAPPED"


def test_confirm_review_succeeds_when_all_mapped(client, db):
    video = _seed_video(db, speakers=["SPEAKER_00", "SPEAKER_01"])

    client.patch(
        f"/api/videos/{video.id}/speakers",
        json={"assignments": [
            {"speaker_label": "SPEAKER_00", "role": "interviewer"},
            {"speaker_label": "SPEAKER_01", "role": "interviewee"},
        ]},
    )

    resp = client.post(f"/api/videos/{video.id}/confirm-review")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "phase1_queued"


def test_speaker_role_can_be_updated(client, db):
    video = _seed_video(db, speakers=["SPEAKER_00"])

    client.patch(
        f"/api/videos/{video.id}/speakers",
        json={"assignments": [{"speaker_label": "SPEAKER_00", "role": "interviewer"}]},
    )
    resp = client.patch(
        f"/api/videos/{video.id}/speakers",
        json={"assignments": [{"speaker_label": "SPEAKER_00", "role": "interviewee"}]},
    )
    assert resp.status_code == 200
    roles = {item["speaker_label"]: item["role"] for item in resp.json()["speaker_role_map"]}
    assert roles["SPEAKER_00"] == "interviewee"


def test_confirm_review_not_found(client):
    resp = client.post(f"/api/videos/{uuid.uuid4()}/confirm-review")
    assert resp.status_code == 404


def test_transcript_segments_ordered_by_segment_id(client, db):
    video = _seed_video(db, speakers=["SPEAKER_00", "SPEAKER_01"])

    resp = client.get(f"/api/videos/{video.id}/transcript")
    assert resp.status_code == 200
    seg_ids = [s["segment_id"] for s in resp.json()["segments"]]
    assert seg_ids == sorted(seg_ids)


def _seed_video_multi(db, texts, status=JobStatus.ready_for_review) -> tuple:
    video = Video(
        original_filename="interview.wav",
        storage_path="/fake/path/interview.wav",
        media_type=MediaType.audio,
        status=status,
        uploaded_at=datetime.now(timezone.utc),
    )
    db.add(video)
    db.flush()

    segs = []
    for idx, text in enumerate(texts):
        seg = TranscriptSegment(
            video_id=video.id,
            segment_id=idx,
            start_ts=float(idx * 10),
            end_ts=float(idx * 10 + 10),
            text=text,
            speaker_label="SPEAKER_00",
            confidence=0.9,
        )
        db.add(seg)
        segs.append(seg)

    db.commit()
    for s in segs:
        db.refresh(s)
    db.refresh(video)
    return video, segs


def test_cut_basic(client, db):
    video, segs = _seed_video_multi(db, ["Hello world how are you", "Second segment"])
    seg = segs[0]

    resp = client.post(f"/api/videos/{video.id}/transcript/cut",
                       json={"segment_id": str(seg.id), "cut_at_char": 11})
    assert resp.status_code == 200
    data = resp.json()
    assert data["left_segment"]["text"] == "Hello world"
    assert data["right_segment"]["text"] == "how are you"
    assert data["left_segment"]["segment_id"] == 0
    assert data["right_segment"]["segment_id"] == 1


def test_cut_renumbers_subsequent_segments(client, db):
    video, segs = _seed_video_multi(db, ["First", "Second", "Third"])
    seg = segs[0]

    resp = client.post(f"/api/videos/{video.id}/transcript/cut",
                       json={"segment_id": str(seg.id), "cut_at_char": 3})
    assert resp.status_code == 200

    transcript = client.get(f"/api/videos/{video.id}/transcript").json()
    seg_ids = [s["segment_id"] for s in transcript["segments"]]
    assert seg_ids == sorted(seg_ids)
    assert len(transcript["segments"]) == 4


def test_cut_timestamps_interpolated(client, db):
    video, segs = _seed_video_multi(db, ["Hello world"])
    seg = segs[0]

    resp = client.post(f"/api/videos/{video.id}/transcript/cut",
                       json={"segment_id": str(seg.id), "cut_at_char": 5})
    assert resp.status_code == 200
    data = resp.json()
    left = data["left_segment"]
    right = data["right_segment"]
    assert left["start_ts"] == seg.start_ts
    assert left["end_ts"] == pytest.approx(right["start_ts"])
    assert right["end_ts"] == seg.end_ts
    assert left["start_ts"] < left["end_ts"] < right["end_ts"]


def test_cut_with_text_override(client, db):
    video, segs = _seed_video_multi(db, ["Helo world"])
    seg = segs[0]

    resp = client.post(f"/api/videos/{video.id}/transcript/cut",
                       json={"segment_id": str(seg.id), "cut_at_char": 10, "text": "Hello world"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["left_segment"]["text"] == "Hello world"[:10].rstrip()
    assert data["right_segment"]["text"] == "Hello world"[10:].lstrip()


def test_cut_at_zero_rejected(client, db):
    video, segs = _seed_video_multi(db, ["Hello world"])
    seg = segs[0]

    resp = client.post(f"/api/videos/{video.id}/transcript/cut",
                       json={"segment_id": str(seg.id), "cut_at_char": 0})
    assert resp.status_code == 400
    assert resp.json()["detail"]["code"] == "CUT_POSITION_INVALID"


def test_cut_at_end_rejected(client, db):
    video, segs = _seed_video_multi(db, ["Hello world"])
    seg = segs[0]

    resp = client.post(f"/api/videos/{video.id}/transcript/cut",
                       json={"segment_id": str(seg.id), "cut_at_char": 11})
    assert resp.status_code == 400
    assert resp.json()["detail"]["code"] == "CUT_POSITION_INVALID"


def test_cut_empty_half_rejected(client, db):
    video, segs = _seed_video_multi(db, ["Hello    "])
    seg = segs[0]

    resp = client.post(f"/api/videos/{video.id}/transcript/cut",
                       json={"segment_id": str(seg.id), "cut_at_char": 6})
    assert resp.status_code == 400
    assert resp.json()["detail"]["code"] == "CUT_PRODUCES_EMPTY_SEGMENT"


def test_cut_blocked_when_not_ready_for_review(client, db):
    video, segs = _seed_video_multi(db, ["Hello world"], status=JobStatus.phase1_queued)
    seg = segs[0]

    resp = client.post(f"/api/videos/{video.id}/transcript/cut",
                       json={"segment_id": str(seg.id), "cut_at_char": 5})
    assert resp.status_code == 409
    assert resp.json()["detail"]["code"] == "NOT_READY_FOR_REVIEW"


def test_cut_segment_not_found(client, db):
    video, _ = _seed_video_multi(db, ["Hello world"])

    resp = client.post(f"/api/videos/{video.id}/transcript/cut",
                       json={"segment_id": str(uuid.uuid4()), "cut_at_char": 5})
    assert resp.status_code == 404
