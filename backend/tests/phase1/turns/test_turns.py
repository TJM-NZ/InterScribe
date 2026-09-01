"""Gate 1 — turn grouping (TURN_GROUPING anchor)."""
from tests.conftest import make_video, make_segment
from app.worker.phase1.turns import build_turns


def test_adjacent_same_speaker_merged(db):
    v = make_video(db)
    make_segment(db, v.id, 0, speaker="SPEAKER_00", text="Hello")
    make_segment(db, v.id, 1, speaker="SPEAKER_00", text="World")
    make_segment(db, v.id, 2, speaker="SPEAKER_01", text="Goodbye")
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
    v = make_video(db)
    make_segment(db, v.id, 0, speaker="SPEAKER_00", text="A")
    make_segment(db, v.id, 1, speaker="SPEAKER_01", text="B")
    make_segment(db, v.id, 2, speaker="SPEAKER_00", text="C")
    make_segment(db, v.id, 3, speaker="SPEAKER_01", text="D")
    db.commit()

    turns = build_turns(v.id, db)

    assert len(turns) == 4
    for i, turn in enumerate(turns):
        assert turn.turn_index == i
        assert turn.start_segment_id == i
        assert turn.end_segment_id == i


def test_turn_index_sequential(db):
    v = make_video(db)
    make_segment(db, v.id, 0, speaker="A", text="x")
    make_segment(db, v.id, 1, speaker="A", text="y")
    make_segment(db, v.id, 2, speaker="B", text="z")
    make_segment(db, v.id, 3, speaker="A", text="w")
    db.commit()

    turns = build_turns(v.id, db)

    assert [t.turn_index for t in turns] == [0, 1, 2]


def test_combined_text_concatenates_in_order(db):
    v = make_video(db)
    make_segment(db, v.id, 0, speaker="SPEAKER_00", text="First")
    make_segment(db, v.id, 1, speaker="SPEAKER_00", text="Second")
    make_segment(db, v.id, 2, speaker="SPEAKER_00", text="Third")
    db.commit()

    turns = build_turns(v.id, db)

    assert len(turns) == 1
    assert turns[0].combined_text == "First Second Third"


def test_token_count_positive(db):
    v = make_video(db)
    make_segment(db, v.id, 0, speaker="SPEAKER_00", text="Hello world")
    db.commit()

    turns = build_turns(v.id, db)

    assert turns[0].token_count >= 1


def test_empty_segments_returns_empty(db):
    v = make_video(db)
    db.commit()

    turns = build_turns(v.id, db)

    assert turns == []
