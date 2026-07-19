"""Gate 1 — chunking (CHUNK_SCHEMA anchor)."""
from app.models.phase1 import TranscriptTurn
from tests.conftest import make_video
from tests.phase1.conftest import make_turn
from app.worker.phase1.chunking import build_chunks, chunk_text_for_qwen


def test_single_turn_produces_one_chunk(db):
    v = make_video(db)
    t = make_turn(db, v.id, 0, 0, 2, text="Hello world")
    db.commit()

    chunks, groups = build_chunks(v.id, [t], max_tokens=10_000, db=db)

    assert len(chunks) == 1
    assert chunks[0].start_segment_id == 0
    assert chunks[0].end_segment_id == 2
    assert chunks[0].chunk_index == 0


def test_turns_fit_within_max_tokens(db):
    v = make_video(db)
    turns = [make_turn(db, v.id, i, i, i, text=f"text {i}", tokens=3_000) for i in range(4)]
    db.commit()

    chunks, groups = build_chunks(v.id, turns, max_tokens=10_000, db=db)

    # 4 turns × 3000 = 12000 tokens → should produce 2 chunks (3+3 → first 3 fit, 4th starts new)
    # Actually: 3000+3000+3000=9000 fit, adding 4th would be 12000 > 10000 → new chunk
    assert len(chunks) == 2
    assert len(groups[0]) == 3
    assert len(groups[1]) == 1


def test_chunk_boundaries_never_split_turn(db):
    v = make_video(db)
    # Each turn is 6000 tokens — can't pair two
    turns = [make_turn(db, v.id, i, i * 5, i * 5 + 4, text=f"big text {i}", tokens=6_000) for i in range(3)]
    db.commit()

    chunks, groups = build_chunks(v.id, turns, max_tokens=10_000, db=db)

    assert len(chunks) == 3
    for chunk, group in zip(chunks, groups):
        assert len(group) == 1


def test_chunk_start_end_segment_ids(db):
    v = make_video(db)
    t1 = make_turn(db, v.id, 0, 0, 2, text="first")
    t2 = make_turn(db, v.id, 1, 3, 5, text="second")
    t3 = make_turn(db, v.id, 2, 6, 8, text="third", tokens=9_900)  # forces split
    db.commit()

    chunks, groups = build_chunks(v.id, [t1, t2, t3], max_tokens=10_000, db=db)

    assert chunks[0].start_segment_id == 0
    assert chunks[0].end_segment_id == 5
    assert chunks[1].start_segment_id == 6
    assert chunks[1].end_segment_id == 8


def test_chunk_index_sequential(db):
    v = make_video(db)
    turns = [make_turn(db, v.id, i, i, i, tokens=6_000) for i in range(3)]
    db.commit()

    chunks, _ = build_chunks(v.id, turns, max_tokens=10_000, db=db)

    assert [c.chunk_index for c in chunks] == [0, 1, 2]


def test_chunk_text_for_qwen_format():
    turns = [
        TranscriptTurn(
            turn_index=0,
            speaker_label="SPEAKER_00",
            start_segment_id=0,
            end_segment_id=0,
            combined_text="Hello.",
            token_count=2,
        ),
        TranscriptTurn(
            turn_index=1,
            speaker_label="SPEAKER_01",
            start_segment_id=1,
            end_segment_id=3,
            combined_text="World ok yes.",
            token_count=5,
        ),
    ]

    text = chunk_text_for_qwen(turns)

    assert "[seg 0]" in text
    assert "[seg 1-3]" in text
    assert "SPEAKER_00" in text
    assert "Hello." in text
