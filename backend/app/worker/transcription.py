import logging
import statistics

import ffmpeg
import whisperx
from sqlalchemy.orm import Session

from app.config import settings
from app.models.video import JobStatus, TranscriptSegment, Video

logger = logging.getLogger(__name__)


def _compute_confidence(segment: dict) -> float:
    words = segment.get("words") or []
    scores = [w["score"] for w in words if isinstance(w.get("score"), (int, float))]
    if scores:
        return max(0.0, min(1.0, statistics.mean(scores)))
    avg_logprob = segment.get("avg_logprob")
    if avg_logprob is not None:
        return max(0.0, min(1.0, float(avg_logprob) + 1.0))
    return 0.5


def transcribe_video(video: Video, db: Session) -> None:
    """
    Run the full WhisperX pipeline:
      VAD (built-in via pyannote) → transcription → alignment → diarization
    Writes TranscriptSegment rows and updates video.status.
    """
    device = settings.whisper_device
    compute_type = settings.whisper_compute_type
    batch_size = settings.whisper_batch_size
    hf_token = settings.huggingface_token

    model = whisperx.load_model(
        settings.whisper_model_size,
        device=device,
        compute_type=compute_type,
        download_root=settings.whisper_model_cache,
    )

    audio = whisperx.load_audio(video.storage_path)

    result = model.transcribe(audio, batch_size=batch_size)
    language = result.get("language", "en")

    align_model, metadata = whisperx.load_align_model(
        language_code=language, device=device
    )
    result = whisperx.align(
        result["segments"], align_model, metadata, audio, device,
        return_char_alignments=False,
    )

    diarize_model = whisperx.DiarizationPipeline(
        use_auth_token=hf_token, device=device
    )
    diarize_segments = diarize_model(audio)

    result = whisperx.assign_word_speakers(diarize_segments, result)

    segments_data = result.get("segments", [])
    for idx, seg in enumerate(segments_data):
        speaker_label = seg.get("speaker") or "SPEAKER_UNKNOWN"
        confidence = _compute_confidence(seg)

        db.add(
            TranscriptSegment(
                video_id=video.id,
                segment_id=idx,
                start_ts=float(seg["start"]),
                end_ts=float(seg["end"]),
                text=seg.get("text", "").strip(),
                speaker_label=speaker_label,
                confidence=confidence,
            )
        )

    try:
        probe = ffmpeg.probe(video.storage_path)
        video.duration_seconds = float(probe["format"]["duration"])
    except Exception:
        pass

    video.status = JobStatus.ready_for_review
    db.commit()
