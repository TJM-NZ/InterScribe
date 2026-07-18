from app.models.video import TranscriptSegment
from app.worker.transcription import detect_repetition_loop


def test_unigram_exactly_4_flagged():
    assert detect_repetition_loop("kia kia kia kia ora") is True


def test_unigram_exactly_3_not_flagged():
    assert detect_repetition_loop("kia kia kia ora") is False


def test_bigram_4_repetitions_flagged():
    assert detect_repetition_loop("hello world hello world hello world hello world") is True


def test_trigram_4_repetitions_flagged():
    assert detect_repetition_loop("one two three one two three one two three one two three") is True


def test_mixed_text_with_embedded_run_flagged():
    assert detect_repetition_loop("and then the the the the speaker said something") is True


def test_empty_string_not_flagged():
    assert detect_repetition_loop("") is False


def test_single_token_not_flagged():
    assert detect_repetition_loop("hello") is False


def test_normal_sentence_not_flagged():
    assert detect_repetition_loop("The quick brown fox jumps over the lazy dog") is False


def test_high_confidence_with_repetition_both_set(db):
    seg = TranscriptSegment(
        video_id=None,
        segment_id=0,
        start_ts=0.0,
        end_ts=1.0,
        text="the the the the",
        speaker_label="SPEAKER_00",
        confidence=0.95,
        repetition_flagged=detect_repetition_loop("the the the the"),
    )
    assert seg.confidence >= 0.7
    assert seg.repetition_flagged is True
