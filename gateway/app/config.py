"""Gateway settings. Env vars are prefixed GATEWAY_ (e.g. GATEWAY_TTS_GRPC_TARGET)."""
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="GATEWAY_")

    tts_grpc_target: str = "tts-service:50051"
    request_timeout: float = 120.0
    max_message_mb: int = 64

    # LucyLab-compatible JSON-RPC layer: absolute base for the audio `url` it
    # returns, and where generated files are written/served from.
    public_base_url: str = "http://localhost:8600"
    files_dir: str = "/tmp/tts-files"


settings = Settings()
