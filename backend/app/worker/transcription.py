import dataclasses
import logging
import statistics

import ffmpeg

# whisperx 3.1.6 was built against faster-whisper 0.x. faster-whisper 1.0.0
# added `hotwords` as a required NamedTuple field; whisperx doesn't pass it.
# Patch __new__.__defaults__ to make hotwords optional before whisperx imports.
import faster_whisper.transcribe as _fw_transcribe
_opts = _fw_transcribe.TranscriptionOptions
if "hotwords" in _opts._fields:
    _existing = _opts.__new__.__defaults__ or ()
    _hw_idx = _opts._fields.index("hotwords")
    _needed = len(_opts._fields) - _hw_idx   # defaults required to cover hotwords→end
    if len(_existing) < _needed:
        _to_add = _needed - len(_existing)
        _opts.__new__.__defaults__ = (None,) * _to_add + _existing
del _fw_transcribe, _opts

import torch
import whisperx
import whisperx.vad as _vad_module
from sqlalchemy.orm import Session

# whisperx 3.1.6 VAD model URL (whisperx.s3.eu-west-2.amazonaws.com) returns 301
# with no Location header — the S3 bucket is gone. Replace load_vad_model with
# a version that loads the cached pyannote/segmentation-3.0 model directly,
# skipping the download and SHA256 check.
_PYANNOTE_SEG_3_FP = (
    "/models/hf/hub/models--pyannote--segmentation-3.0"
    "/snapshots/e66f3d3b9eb0873085418a7b813d3b369bf160bb/pytorch_model.bin"
)


def _load_vad_local(device, vad_onset=0.500, vad_offset=0.363, use_auth_token=None, model_fp=None):
    if model_fp is None:
        model_fp = _PYANNOTE_SEG_3_FP
    vad_model = _vad_module.Model.from_pretrained(model_fp, use_auth_token=use_auth_token)
    # pyannote/segmentation-3.0 no longer exposes onset/offset — only duration filters
    vad_pipeline = _vad_module.VoiceActivitySegmentation(
        segmentation=vad_model, device=torch.device(device)
    )
    vad_pipeline.instantiate({"min_duration_on": 0.1, "min_duration_off": 0.1})
    return vad_pipeline


_vad_module.load_vad_model = _load_vad_local
# whisperx.asr does `from .vad import load_vad_model` so patch its namespace too
import whisperx.asr as _asr_module
_asr_module.load_vad_model = _load_vad_local

# huggingface_hub 1.23.0 removed `use_auth_token` kwarg (renamed to `token`).
# pyannote.audio 3.1.1 still calls hf_hub_download/snapshot_download with
# use_auth_token. Shim both in huggingface_hub and in every already-imported
# module that holds a direct reference.
import sys as _sys
import huggingface_hub as _hf_hub


def _make_compat(fn):
    def _compat(*args, use_auth_token=None, **kwargs):
        if use_auth_token is not None and "token" not in kwargs:
            kwargs["token"] = use_auth_token
        return fn(*args, **kwargs)
    _compat.__name__ = fn.__name__
    return _compat


for _fn_name in ("hf_hub_download", "snapshot_download"):
    _orig = getattr(_hf_hub, _fn_name, None)
    if _orig is None:
        continue
    _compat_fn = _make_compat(_orig)
    setattr(_hf_hub, _fn_name, _compat_fn)
    for _mod in list(_sys.modules.values()):
        try:
            if getattr(_mod, _fn_name, None) is _orig:
                setattr(_mod, _fn_name, _compat_fn)
        except Exception:
            pass

del _sys, _hf_hub, _fn_name, _orig, _compat_fn, _mod, _make_compat

from app.config import settings
from app.models.video import JobStatus, TranscriptSegment, Video

logger = logging.getLogger(__name__)


def detect_repetition_loop(text: str) -> bool:
    tokens = text.split()
    for n in (1, 2, 3):
        for i in range(len(tokens) - n + 1):
            ngram = tokens[i : i + n]
            count = 1
            j = i + n
            while j <= len(tokens) - n and tokens[j : j + n] == ngram:
                count += 1
                j += n
            if count >= 4:
                return True
    return False


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

    try:
        align_model, metadata = whisperx.load_align_model(
            language_code=language, device=device
        )
        result = whisperx.align(
            result["segments"], align_model, metadata, audio, device,
            return_char_alignments=False,
        )
    except Exception as exc:
        logger.warning(
            "No alignment model for language '%s', using raw transcription segments: %s",
            language, exc,
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
        text = seg.get("text", "").strip()

        db.add(
            TranscriptSegment(
                video_id=video.id,
                segment_id=idx,
                start_ts=float(seg["start"]),
                end_ts=float(seg["end"]),
                text=text,
                speaker_label=speaker_label,
                confidence=confidence,
                repetition_flagged=detect_repetition_loop(text),
            )
        )

    try:
        probe = ffmpeg.probe(video.storage_path)
        video.duration_seconds = float(probe["format"]["duration"])
    except Exception:
        pass

    video.status = JobStatus.ready_for_review
    video.error_reason = None
    db.commit()

    # Release GPU memory before the next job
    if torch.cuda.is_available():
        torch.cuda.empty_cache()
