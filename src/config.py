"""
Configuration settings for the Video Intelligence Agent system.
Simplified version using Google AI Studio (free tier).
"""
from pydantic_settings import BaseSettings
from pydantic import Field
from typing import Optional
import os


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""
    
    # Google AI Studio API Key (FREE - no billing required)
    gemini_api_key: str = Field(default="", env="GEMINI_API_KEY")
    
    # Optional: Google Cloud Configuration (only needed if using Cloud Storage)
    google_cloud_project: Optional[str] = Field(default=None, env="GOOGLE_CLOUD_PROJECT")
    google_cloud_region: str = Field(default="us-central1", env="GOOGLE_CLOUD_REGION")
    
    # Local Storage Configuration (no cloud required)
    local_storage_path: str = Field(default="./video_storage", env="LOCAL_STORAGE_PATH")
    local_clips_path: str = Field(default="./video_clips", env="LOCAL_CLIPS_PATH")
    
    # Optional: Cloud Storage Configuration
    gcs_bucket_name: Optional[str] = Field(default=None, env="GCS_BUCKET_NAME")
    gcs_video_prefix: str = Field(default="cctv-feeds/", env="GCS_VIDEO_PREFIX")
    gcs_clips_prefix: str = Field(default="alert-clips/", env="GCS_CLIPS_PREFIX")
    
    # Firebase Configuration (optional - for mobile push notifications)
    firebase_credentials_path: Optional[str] = Field(
        default=None, env="FIREBASE_CREDENTIALS_PATH"
    )
    firebase_project_id: Optional[str] = Field(default=None, env="FIREBASE_PROJECT_ID")
    
    # Alert Configuration
    alert_webhook_url: Optional[str] = Field(default=None, env="ALERT_WEBHOOK_URL")
    alert_email_enabled: bool = Field(default=False, env="ALERT_EMAIL_ENABLED")
    alert_sms_enabled: bool = Field(default=False, env="ALERT_SMS_ENABLED")
    
    # Video Processing Configuration
    video_frame_rate: int = Field(default=1, env="VIDEO_FRAME_RATE")
    video_analysis_interval_seconds: int = Field(
        default=30, env="VIDEO_ANALYSIS_INTERVAL_SECONDS"
    )
    video_clip_duration_seconds: int = Field(
        default=60, env="VIDEO_CLIP_DURATION_SECONDS"
    )
    max_concurrent_streams: int = Field(default=10, env="MAX_CONCURRENT_STREAMS")
    
    # API Configuration
    api_host: str = Field(default="0.0.0.0", env="API_HOST")
    api_port: int = Field(default=8080, env="API_PORT")
    api_secret_key: str = Field(default="change-me-in-production", env="API_SECRET_KEY")
    
    # Logging
    log_level: str = Field(default="INFO", env="LOG_LEVEL")
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False


# Global settings instance
settings = Settings()


def get_settings() -> Settings:
    """Get the application settings."""
    return settings
