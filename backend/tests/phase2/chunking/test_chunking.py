"""Gate 1 — Phase2Chunk creation with overlapping turn boundaries (PHASE2_CHUNK anchor)."""
from app.models.phase2 import Phase2Chunk
from app.models.video import JobStatus
from tests.conftest import make_video
from tests.phase1.conftest import make_turn
from app.worker.phase2.chunking import build_phase2_chunks


def test_no_turns_returns_empty(db):
    v = make_video(db)
    db.commit()

    chunks, groups = build_phase2_chunks(v.id, [], max_tokens=10_000, overlap_turns=2, db=db)

    assert chunks == []
    assert groups == []


def test_single_chunk_when_all_turns_fit(db):
    v = make_video(db)
    turns = [make_turn(db, v.id, i, i, i, tokens=500) for i in range(5)]
    db.commit()

    chunks, groups = build_phase2_chunks(v.id, turns, max_tokens=10_000, overlap_turns=2, db=db)

    assert len(chunks) == 1
    assert len(groups[0]) == 5
    assert chunks[0].chunk_index == 0
    assert chunks[0].start_segment_id == 0
    assert chunks[0].end_segment_id == 4


def test_overlapping_chunks_share_boundary_turns(db):
    """Adjacent chunks share the last overlap_turns turns of the previous chunk."""
    v = make_video(db)
    # 8 turns × 1500 tokens = 12000 per pair — forces split roughly every 6 turns
    turns = [make_turn(db, v.id, i, i * 2, i * 2 + 1, tokens=1500) for i in range(8)]
    db.commit()

    chunks, groups = build_phase2_chunks(v.id, turns, max_tokens=9_000, overlap_turns=2, db=db)

    assert len(chunks) >= 2
    # Last 2 turns of chunk 0 must appear as first 2 turns of chunk 1
    assert groups[0][-2].turn_index == groups[1][0].turn_index
    assert groups[0][-1].turn_index == groups[1][1].turn_index


def test_chunk_boundaries_align_to_turn_boundaries(db):
    """start_segment_id and end_segment_id are always from whole turns."""
    v = make_video(db)
    turns = [make_turn(db, v.id, i, i * 3, i * 3 + 2, tokens=3_500) for i in range(6)]
    db.commit()

    chunks, groups = build_phase2_chunks(v.id, turns, max_tokens=10_000, overlap_turns=2, db=db)

    for chunk, group in zip(chunks, groups):
        assert chunk.start_segment_id == group[0].start_segment_id
        assert chunk.end_segment_id == group[-1].end_segment_id


def test_chunk_index_is_sequential(db):
    v = make_video(db)
    turns = [make_turn(db, v.id, i, i, i, tokens=6_000) for i in range(6)]
    db.commit()

    chunks, _ = build_phase2_chunks(v.id, turns, max_tokens=10_000, overlap_turns=2, db=db)

    assert [c.chunk_index for c in chunks] == list(range(len(chunks)))


def test_zero_overlap_gives_no_overlap(db):
    """overlap_turns=0 produces non-overlapping chunks like Phase 1."""
    v = make_video(db)
    turns = [make_turn(db, v.id, i, i, i, tokens=4_000) for i in range(6)]
    db.commit()

    chunks, groups = build_phase2_chunks(v.id, turns, max_tokens=10_000, overlap_turns=0, db=db)

    # No turn should appear in two consecutive groups
    for i in range(len(groups) - 1):
        turn_ids_a = {t.turn_index for t in groups[i]}
        turn_ids_b = {t.turn_index for t in groups[i + 1]}
        assert turn_ids_a.isdisjoint(turn_ids_b)


def test_single_oversized_turn_still_gets_a_chunk(db):
    """A turn exceeding max_tokens is not dropped — it gets its own chunk."""
    v = make_video(db)
    big = make_turn(db, v.id, 0, 0, 99, tokens=50_000)
    small = make_turn(db, v.id, 1, 100, 109, tokens=100)
    db.commit()

    chunks, groups = build_phase2_chunks(v.id, [big, small], max_tokens=10_000, overlap_turns=2, db=db)

    assert len(chunks) >= 1
    # The oversized turn must be in the first group
    assert groups[0][0].turn_index == 0


def test_token_count_stored_on_chunk(db):
    v = make_video(db)
    turns = [make_turn(db, v.id, i, i, i, tokens=3_000) for i in range(3)]
    db.commit()

    chunks, groups = build_phase2_chunks(v.id, turns, max_tokens=10_000, overlap_turns=0, db=db)

    for chunk, group in zip(chunks, groups):
        assert chunk.token_count == sum(t.token_count for t in group)


def test_phase2_chunks_persisted_to_db(db):
    v = make_video(db)
    turns = [make_turn(db, v.id, i, i, i, tokens=5_000) for i in range(4)]
    db.commit()

    chunks, _ = build_phase2_chunks(v.id, turns, max_tokens=10_000, overlap_turns=2, db=db)
    db.commit()

    from sqlalchemy import select
    rows = db.execute(
        select(Phase2Chunk).where(Phase2Chunk.video_id == v.id)
    ).scalars().all()
    assert len(rows) == len(chunks)
