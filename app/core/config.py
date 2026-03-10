"""Application configuration from environment variables."""

import os
from pathlib import Path
from typing import Optional

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Load and validate config from environment."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Groq
    groq_api_key: str = ""
    groq_model: str = "llama-3.3-70b-versatile"
    groq_temperature: float = 0.7
    groq_max_tokens: int = 4096

    # App
    app_name: str = "AI Backend"
    debug: bool = False
    knowledge_base_path: Optional[Path] = None
    voice_rich_logs: bool = False  # When True, log voice pipeline with Rich panels/tables (requires rich)

    # Voice: TTS and STT providers.
    tts_provider: str = "deepgram"  # "chatterbox" | "elevenlabs" | "deepgram"
    stt_provider: str = "deepgram"  # "webkit" | "deepgram" (webkit = client-side only; deepgram = server STT for voice agent)
    chatterbox_tts_url: str = "http://localhost:4123"
    # ElevenLabs (when tts_provider=elevenlabs)
    elevenlabs_api_key: str = ""
    elevenlabs_voice_id: str = ""  # e.g. 21m00Tcm4TlvDq8ikWAM (Rachel); leave empty for default
    elevenlabs_model_id: str = "eleven_multilingual_v2"
    # Deepgram (when stt_provider and/or tts_provider=deepgram)
    deepgram_api_key: str = ""
    deepgram_stt_model: str = "nova-2"
    deepgram_tts_model: str = "aura-asteria-en"  # or other Deepgram TTS model

    @field_validator("knowledge_base_path", mode="before")
    @classmethod
    def coerce_kb_path(cls, v):
        if v is None or v == "":
            return None
        return Path(v) if not isinstance(v, Path) else v

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        if self.knowledge_base_path is None:
            # Default: project root / knowledge (e.g. knowledge/medical.md, retail.md, legal.md)
            project_root = Path(__file__).resolve().parent.parent.parent
            self.knowledge_base_path = project_root / "knowledge"

    @property
    def groq_configured(self) -> bool:
        return bool(os.getenv("GROQ_API_KEY") or self.groq_api_key)


settings = Settings()
