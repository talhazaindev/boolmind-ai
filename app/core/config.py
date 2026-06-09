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

    # Groq (GROQ_API_KEY optional if GROQ_API_KEY_1…N are set)
    groq_api_key: str = ""
    groq_api_key_1: str = ""
    groq_api_key_2: str = ""
    groq_api_key_3: str = ""
    groq_api_key_4: str = ""
    groq_api_key_5: str = ""
    groq_api_key_6: str = ""
    groq_api_key_7: str = ""
    groq_api_key_8: str = ""
    groq_api_key_9: str = ""
    groq_api_key_10: str = ""
    # 0 = use every non-empty GROQ_API_KEY_N found; >0 caps numbered slots (1..N)
    groq_key_pool_size: int = 0
    groq_model: str = "llama-3.3-70b-versatile"
    groq_eval_model: str = ""
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

    # Advisor — embeddings (local BGE default; OpenAI optional)
    embedding_provider: str = "local"  # local | openai
    embedding_model: str = "BAAI/bge-small-en-v1.5"
    embedding_dimension: int = 384
    openai_api_key: str = ""
    openai_embedding_model: str = "text-embedding-3-small"

    # Advisor — Pinecone RAG
    pinecone_mode: str = "cloud"  # cloud | local (Pinecone Local / pinecone-index container)
    pinecone_api_key: str = ""
    pinecone_index_name: str = "boolmind-knowledge-bge"
    pinecone_host: str = ""
    pinecone_port: int = 5081

    # Advisor — Redis sessions
    redis_backend: str = "upstash"  # upstash | local
    redis_url: str = ""
    upstash_redis_rest_url: str = ""
    upstash_redis_rest_token: str = ""

    # Advisor — HubSpot (optional until Tier B)
    hubspot_access_token: str = ""
    hubspot_pipeline_id: str = ""
    hubspot_stage_new_lead: str = ""

    # Advisor — security
    chat_api_secret: str = ""
    chat_rate_limit_per_minute: int = 20
    chat_init_rate_limit_per_hour: int = 3

    # Advisor — Supabase (Tier B)
    supabase_url: str = ""
    supabase_service_role_key: str = ""
    supabase_project_ref: str = "jhoiqryisvxvtafvdwcf"

    # Advisor — Cal.com + Resend
    calcom_api_key: str = ""
    calcom_event_type_id: str = ""
    calcom_booking_timezone: str = "UTC"

    resend_api_key: str = ""
    resend_from_email: str = "advisor@boolmind.ai"
    resend_from_name: str = "Boolmind.AI Advisor"

    # Advisor — PostHog + Sentry (Tier C)
    posthog_api_key: str = ""
    posthog_host: str = "https://app.posthog.com"

    sentry_dsn: str = ""

    # Advisor — FIDP image generation (Tier D)
    replicate_api_token: str = ""
    image_gen_provider: str = "mock"  # mock | replicate | local
    image_gen_model: str = "stabilityai/sdxl-turbo"
    image_gen_steps: int = 2
    image_gen_size: int = 512
    fidp_output_dir: str = ""
    hf_home: str = ""

    # Paths
    advisor_knowledge_base_path: Optional[Path] = None
    advisor_tours_path: Optional[Path] = None

    @field_validator("knowledge_base_path", "advisor_knowledge_base_path", "advisor_tours_path", mode="before")
    @classmethod
    def coerce_kb_path(cls, v):
        if v is None or v == "":
            return None
        return Path(v) if not isinstance(v, Path) else v

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        project_root = Path(__file__).resolve().parent.parent.parent
        if self.knowledge_base_path is None:
            self.knowledge_base_path = project_root / "knowledge"
        if self.advisor_knowledge_base_path is None:
            self.advisor_knowledge_base_path = project_root / "knowledge-base"
        if self.advisor_tours_path is None:
            self.advisor_tours_path = project_root / "knowledge-base" / "tours"
        if not self.fidp_output_dir:
            self.fidp_output_dir = str(project_root / "data" / "fidp-output")

    _GROQ_NUMBERED_SLOTS: int = 10

    @property
    def fidp_output_path(self) -> Path:
        return Path(self.fidp_output_dir)

    @property
    def local_image_gen_ready(self) -> bool:
        if self.image_gen_provider.strip().lower() != "local":
            return False
        try:
            import torch

            return torch.cuda.is_available()
        except ImportError:
            return False

    def get_groq_api_keys(self) -> list[str]:
        """Collect GROQ_API_KEY plus GROQ_API_KEY_1…N (deduped, ordered).

        When ``groq_key_pool_size`` > 0, only numbered keys 1..pool_size are used
        (plus primary ``GROQ_API_KEY`` when set). When 0, all non-empty numbered
        keys up to slot 32 are included.
        """
        numbered: dict[int, str] = {}
        scan_through = (
            self.groq_key_pool_size
            if self.groq_key_pool_size > 0
            else self._GROQ_NUMBERED_SLOTS
        )
        for i in range(1, scan_through + 1):
            val = getattr(self, f"groq_api_key_{i}", "").strip()
            if not val:
                val = os.getenv(f"GROQ_API_KEY_{i}", "").strip()
            if val:
                numbered[i] = val

        limit = (
            self.groq_key_pool_size
            if self.groq_key_pool_size > 0
            else max(numbered.keys(), default=0)
        )
        ordered_numbered = [numbered[i] for i in sorted(numbered) if i <= limit]

        candidates: list[str] = []
        primary = self.groq_api_key.strip() or os.getenv("GROQ_API_KEY", "").strip()
        if primary:
            candidates.append(primary)
        candidates.extend(ordered_numbered)

        seen: set[str] = set()
        unique: list[str] = []
        for k in candidates:
            if k and k not in seen:
                seen.add(k)
                unique.append(k)
        return unique

    @property
    def groq_eval_model_resolved(self) -> str:
        return self.groq_eval_model.strip() or self.groq_model

    @property
    def groq_configured(self) -> bool:
        return len(self.get_groq_api_keys()) > 0

    @property
    def openai_configured(self) -> bool:
        return bool(os.getenv("OPENAI_API_KEY") or self.openai_api_key)

    @property
    def embeddings_configured(self) -> bool:
        if self.embedding_provider == "openai":
            return self.openai_configured
        return self.embedding_provider == "local"

    @property
    def pinecone_configured(self) -> bool:
        if self.pinecone_mode.strip().lower() == "local":
            return bool(self.pinecone_host and self.pinecone_index_name)
        return bool(self.pinecone_api_key and self.pinecone_index_name)

    @property
    def upstash_configured(self) -> bool:
        return bool(self.upstash_redis_rest_url and self.upstash_redis_rest_token)

    @property
    def local_redis_configured(self) -> bool:
        return bool(self.redis_url.strip())

    @property
    def redis_configured(self) -> bool:
        backend = self.redis_backend.strip().lower()
        if backend == "local":
            return self.local_redis_configured
        if backend == "upstash":
            return self.upstash_configured
        return False

    @property
    def hubspot_configured(self) -> bool:
        return bool(self.hubspot_access_token)

    @property
    def supabase_configured(self) -> bool:
        return bool(self.supabase_url and self.supabase_service_role_key)

    @property
    def calcom_configured(self) -> bool:
        return bool(self.calcom_api_key and self.calcom_event_type_id)

    @property
    def resend_configured(self) -> bool:
        return bool(self.resend_api_key and self.resend_from_email)

    @property
    def posthog_configured(self) -> bool:
        return bool(self.posthog_api_key)

    @property
    def sentry_configured(self) -> bool:
        return bool(self.sentry_dsn)

    @property
    def replicate_configured(self) -> bool:
        return bool(self.replicate_api_token)

    @property
    def advisor_tier_a_ready(self) -> bool:
        return (
            self.groq_configured
            and self.embeddings_configured
            and self.pinecone_configured
            and self.redis_configured
        )


settings = Settings()
