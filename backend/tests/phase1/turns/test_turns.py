"""Gate 1 — turn grouping (TURN_GROUPING anchor)."""
from datetime import datetime, timezone

import pytest

from app.models.video import JobStatus, MediaType, TranscriptSegment, Video
from app.worker.phase1.turns import build_turns


def _make_video(db):
    v = Video(
        original_filename="t.wav",
        storage_path="/fake/t.wav",
        media_type=MediaType.audio,
        status=JobStatus.phase1_processing,
        uploaded_at=datetime.now(timezone.utc),
    )
    db.add(v)
    db.flush()
    return v


def _add_segments(db, video_id, specs):
    """specs: list of (speaker_label, text)."""
    for idx, (label, text) in enumerate(specs):
        db.add(TranscriptSegment(
            video_id=video_id,
            segment_id=idx,
            start_ts=float(idx),
            end_ts=float(idx + 1),
            text=text,
            speaker_label=label,
            confidence=0.9,
        ))
    db.flush()


def test_adjacent_same_speaker_merged(db):
    v = _make_video(db)
    _add_segments(db, v.id, [
        ("SPEAKER_00", "Hello"),
        ("SPEAKER_00", "World"),
        ("SPEAKER_01", "Goodbye"),
    ])
    db.commit()

    turns = build_turns(v.id, db)

    assert len(turns) == 2
    assert turns[0].speaker_label == "SPEAKER_00"
    assert turns[0].start_segment_id == 0
    assert turns[0].end_segment_id == 1
    assert "Hello" in turns[0].combined_text
    assert "World" in turns[0].combined_text

    assert turns[1].speaker_label == "SPEAKER_01"
    assert turns[1].start_segment_id == 2
    assert turns[1].end_segment_id == 2


def test_alternating_speakers_produce_one_turn_each(db):
    v = _make_video(db)
    _add_segments(db, v.id, [
        ("SPEAKER_00", "A"),
        ("SPEAKER_01", "B"),
        ("SPEAKER_00", "C"),
        ("SPEAKER_01", "D"),
    ])
    db.commit()

    turns = build_turns(v.id, db)

    assert len(turns) == 4
    for i, turn in enumerate(turns):
        assert turn.turn_index == i
        assert turn.start_segment_id == i
        assert turn.end_segment_id == i


def test_turn_index_sequential(db):
    v = _make_video(db)
    _add_segments(db, v.id, [
        ("A", "x"), ("A", "y"), ("B", "z"), ("A", "w"),
    ])
    db.commit()

    turns = build_turns(v.id, db)

    assert [t.turn_index for t in turns] == [0, 1, 2]


def test_combined_text_concatenates_in_order(db):
    v = _make_video(db)
    _add_segments(db, v.id, [
        ("SPEAKER_00", "First"),
        ("SPEAKER_00", "Second"),
        ("SPEAKER_00", "Third"),
    ])
    db.commit()

    turns = build_turns(v.id, db)

    assert len(turns) == 1
    assert turns[0].combined_text == "First Second Third"


def test_token_count_positive(db):
    v = _make_video(db)
    _add_segments(db, v.id, [("SPEAKER_00", "Hello world")])
    db.commit()

    turns = build_turns(v.id, db)

    assert turns[0].token_count >= 1


def test_empty_segments_returns_empty(db):
    v = _make_video(db)
    db.commit()

    turns = build_turns(v.id, db)

    assert turns == []
