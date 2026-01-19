"""
Video Intelligence Agent - CCTV Monitoring System
"""
from .config import settings, get_settings
from .models import (
    Camera, MonitoringTask, Alert, AlertSeverity, AlertStatus,
    CameraStatus, AnalysisResult, VideoFrame, VideoClip
)
from .video_handler import VideoStreamManager, CloudStorageManager
from .video_intelligence import VideoIntelligenceAgent, TaskPromptBuilder
from .alert_system import AlertManager, FirebaseAlertSender, WebhookAlertSender
from .monitoring_engine import MonitoringEngine, TaskTemplates

__version__ = "1.0.0"
__all__ = [
    "settings",
    "get_settings",
    "Camera",
    "MonitoringTask", 
    "Alert",
    "AlertSeverity",
    "AlertStatus",
    "CameraStatus",
    "AnalysisResult",
    "VideoFrame",
    "VideoClip",
    "VideoStreamManager",
    "CloudStorageManager",
    "VideoIntelligenceAgent",
    "TaskPromptBuilder",
    "AlertManager",
    "FirebaseAlertSender",
    "WebhookAlertSender",
    "MonitoringEngine",
    "TaskTemplates",
]
