import uuid
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from app.models.video import JobStatus, MediaType, TranscriptSegment, Video
from app.worker.transcription import _compute_confidence, transcribe_video


def _make_video(db) -> Video:
    video = Video(
        original_filename="interview.wav",
        storage_path="/fake/path/interview.wav",
        media_type=MediaType.audio,
        status=JobStatus.queued,
        uploaded_at=datetime.now(timezone.utc),
    )
    db.add(video)
    db.commit()
    db.refresh(video)
    return video


def _mock_whisperx_result():
    return {
        "language": "en",
        "segments": [
            {
                "start": 0.0,
                "end": 3.5,
                "text": "Hello, how are you?",
                "speaker": "SPEAKER_00",
                "words": [
                    {"word": "Hello", "score": 0.95},
                    {"word": "how", "score": 0.90},
                    {"word": "are", "score": 0.88},
                    {"word": "you", "score": 0.92},
                ],
            },
            {
                "start": 4.0,
                "end": 7.0,
                "text": "I am doing well, thank you.",
                "speaker": "SPEAKER_01",
                "words": [
                    {"word": "I", "score": 0.75},
                    {"word": "am", "score": 0.80},
                ],
            },
            {
                "start": 8.0,
                "end": 10.0,
                "text": "Mumbled something.",
                "speaker": None,
                "avg_logprob": -0.6,
                "words": [],
            },
        ],
    }


def test_compute_confidence_from_word_scores():
    seg = {"words": [{"score": 0.8}, {"score": 0.6}]}
    assert abs(_compute_confidence(seg) - 0.7) < 0.001


def test_compute_confidence_fallback_avg_logprob():
    seg = {"avg_logprob": -0.3, "words": []}
    assert abs(_compute_confidence(seg) - 0.7) < 0.001


def test_compute_confidence_clamped():
    seg = {"avg_logprob": 5.0, "words": []}
    assert _compute_confidence(seg) == 1.0

    seg2 = {"avg_logprob": -5.0, "words": []}
    assert _compute_confidence(seg2) == 0.0


def test_compute_confidence_default_when_no_data():
    seg = {}
    assert _compute_confidence(seg) == 0.5


def test_transcription_produces_segments(db):
    video = _make_video(db)
    mock_result = _mock_whisperx_result()

    with patch("app.worker.transcription.whisperx") as mock_wx, \
         patch("app.worker.transcription.ffmpeg") as mock_ffmpeg:

        mock_model = MagicMock()
        mock_model.transcribe.return_value = mock_result
        mock_wx.load_model.return_value = mock_model
        mock_wx.load_audio.return_value = MagicMock()
        mock_wx.load_align_model.return_value = (MagicMock(), MagicMock())
        mock_wx.align.return_value = mock_result
        mock_wx.DiarizationPipeline.return_value = MagicMock(return_value=MagicMock())
        mock_wx.assign_word_speakers.return_value = mock_result
        mock_ffmpeg.probe.return_value = {"format": {"duration": "10.5"}}

        transcribe_video(video, db)

    db.refresh(video)
    assert video.status == JobStatus.ready_for_review
    assert video.duration_seconds == pytest.approx(10.5)

    segments = db.query(TranscriptSegment).filter_by(video_id=video.id).order_by(TranscriptSegment.segment_id).all()
    assert len(segments) == 3

    assert segments[0].segment_id == 0
    assert segments[1].segment_id == 1
    assert segments[2].segment_id == 2


def test_transcription_uses_sequential_segment_ids(db):
    video = _make_video(db)
    mock_result = _mock_whisperx_result()

    with patch("app.worker.transcription.whisperx") as mock_wx, \
         patch("app.worker.transcription.ffmpeg") as mock_ffmpeg:

        mock_wx.load_model.return_value = MagicMock(transcribe=MagicMock(return_value=mock_result))
        mock_wx.load_audio.return_value = MagicMock()
        mock_wx.load_align_model.return_value = (MagicMock(), MagicMock())
        mock_wx.align.return_value = mock_result
        mock_wx.DiarizationPipeline.return_value = MagicMock(return_value=MagicMock())
        mock_wx.assign_word_speakers.return_value = mock_result
        mock_ffmpeg.probe.return_value = {"format": {"duration": "10.5"}}

        transcribe_video(video, db)

    segments = db.query(TranscriptSegment).filter_by(video_id=video.id).order_by(TranscriptSegment.segment_id).all()
    ids = [s.segment_id for s in segments]
    assert ids == list(range(len(segments)))


def test_transcription_handles_missing_speaker_label(db):
    video = _make_video(db)
    mock_result = _mock_whisperx_result()

    with patch("app.worker.transcription.whisperx") as mock_wx, \
         patch("app.worker.transcription.ffmpeg") as mock_ffmpeg:

        mock_wx.load_model.return_value = MagicMock(transcribe=MagicMock(return_value=mock_result))
        mock_wx.load_audio.return_value = MagicMock()
        mock_wx.load_align_model.return_value = (MagicMock(), MagicMock())
        mock_wx.align.return_value = mock_result
        mock_wx.DiarizationPipeline.return_value = MagicMock(return_value=MagicMock())
        mock_wx.assign_word_speakers.return_value = mock_result
        mock_ffmpeg.probe.return_value = {"format": {"duration": "10.5"}}

        transcribe_video(video, db)

    segments = db.query(TranscriptSegment).filter_by(video_id=video.id).order_by(TranscriptSegment.segment_id).all()
    unknown_seg = segments[2]
    assert unknown_seg.speaker_label == "SPEAKER_UNKNOWN"


def test_transcription_failure_raises_exception(db):
    video = _make_video(db)

    with patch("app.worker.transcription.whisperx") as mock_wx:
        mock_wx.load_model.side_effect = RuntimeError("CUDA OOM")
        with pytest.raises(RuntimeError, match="CUDA OOM"):
            transcribe_video(video, db)

    db.refresh(video)
    assert video.status == JobStatus.queued
