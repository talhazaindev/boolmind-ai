"""FastAPI dependencies for services and config."""

from typing import Annotated

from fastapi import Depends

from app.core.config import Settings, settings
from app.services.session_manager import SessionManager, get_session_manager


def get_settings() -> Settings:
    """Inject application settings."""
    return settings


SettingsDep = Annotated[Settings, Depends(get_settings)]
SessionManagerDep = Annotated[SessionManager, Depends(get_session_manager)]
