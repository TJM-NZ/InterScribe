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

    huggingface_token: str = ""
    hf_home: str = "/models/hf"

    max_upload_size_bytes: int = 2_147_483_648
    max_upload_duration_seconds: float = 10_800.0


settings = Settings()
