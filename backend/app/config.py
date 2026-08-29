from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str
    upload_storage_path: str = "/data/uploads"

    whisper_device: str = "cuda"
    whisper_model_size: str = "large-v2"
    whisper_compute_type: str = "float16"
    whisper_batch_size: int = 16
    whisper_model_cache: str = "/models/whisper"

    hf_home: str = "/models/hf"

    max_upload_size_bytes: int = 2_147_483_648
    max_upload_duration_seconds: float = 10_800.0

    ollama_base_url: str = "http://ollama:11434"
    qwen_model: str = "qwen3.5:9b"

    narrative_chunk_max_tokens: int = 10_000
    # agglomerative clustering cosine distance threshold
    narrative_cluster_threshold: float = 0.3
    # top-N clusters surfaced to phase 2 (configurable, default 5)
    narrative_top_n: int = 5
    # per-chunk Qwen retry attempts before failing the whole video
    narrative_chunk_retries: int = 3

    # Phase 2 — quote extraction (D1, D2 from SPEC-003 Change Protocol)
    phase2_overlap_turns: int = 2
    phase2_dedup_overlap_ratio: float = 0.5
    phase2_dedup_text_similarity: float = 0.85

    worker_poll_interval: int = 5

    # Auth — generate with: python -c "import secrets; print(secrets.token_hex(32))"
    interscribe_api_key: str = ""


settings = Settings()
