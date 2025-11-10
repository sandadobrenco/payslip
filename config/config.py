from pathlib import Path
from pydantic import ValidationError, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import List, Optional
import dj_database_url
from zoneinfo import available_timezones

ENV_FILE = Path(__file__).resolve().parent.parent / ".env"

class SettingsValidation(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(ENV_FILE),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )
    
    SECRET_KEY: str
    DEBUG: bool = False
    ALLOWED_HOSTS: List[str]
    DATABASE_URL: str 
    TIME_ZONE: str = "Europe/Bucharest"
    
    EMAIL_BACKEND: str = "django.core.mail.backends.smtp.EmailBackend"
    EMAIL_HOST: str
    EMAIL_PORT: int = 587
    EMAIL_USE_TLS: bool = True
    EMAIL_HOST_USER: str
    EMAIL_HOST_PASSWORD: str
    DEFAULT_FROM_EMAIL: str
    EMAIL_TIMEOUT: int = 30
    
    EMAIL_FROM_NAME: Optional[str] = None
    
    MEDIA_ROOT: str = "/app/media"
    MEDIA_URL: str = "/media/"
    
    LOG_LEVEL: str = "INFO"
    
    ENABLE_CELERY : bool
    CELERY_BROKER_URL: str
    CELERY_RESULT_BACKEND: str 
    CELERY_TIMEZONE: str = "Europe/Bucharest"
    
    def django_database(self) -> dict:
        return {"default": dj_database_url.parse(self.DATABASE_URL)}
    
    def get_from_email(self) -> str:
        if self.EMAIL_FROM_NAME:
            return f"{self.EMAIL_FROM_NAME} <{self.DEFAULT_FROM_EMAIL}>"
        return self.DEFAULT_FROM_EMAIL
    
    @field_validator("ALLOWED_HOSTS", mode="before")
    @classmethod
    def split_allowed_hosts(cls, v):
        if isinstance(v, str):
            return [h.strip() for h in v.split(",") if h.strip()]
        return v
    
    @field_validator("TIME_ZONE")
    @classmethod
    def allowed_time_zones(cls, v:str) -> str:
        if v not in available_timezones():
            raise ValueError(f"The time zone {v} is invalid")
        return v
    
    @field_validator("LOG_LEVEL")
    @classmethod
    def validate_log_level(cls, v: str) -> str:
        """Validate log level is one of the allowed values"""
        allowed_levels = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
        v_upper = v.upper()
        if v_upper not in allowed_levels:
            raise ValueError(
                f"LOG_LEVEL must be one of {allowed_levels}, got {v}"
            )
        return v_upper
        
try:
    settings = SettingsValidation()
except ValidationError as e:
    raise RuntimeError(f"Invalid .env file configuration")