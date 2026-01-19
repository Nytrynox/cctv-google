"""
Data models for the Video Intelligence Agent system.
"""
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from datetime import datetime
from enum import Enum


class AlertSeverity(str, Enum):
    """Alert severity levels."""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class AlertStatus(str, Enum):
    """Alert status."""
    PENDING = "pending"
    SENT = "sent"
    ACKNOWLEDGED = "acknowledged"
    RESOLVED = "resolved"


class CameraStatus(str, Enum):
    """Camera connection status."""
    ONLINE = "online"
    OFFLINE = "offline"
    ERROR = "error"
    MAINTENANCE = "maintenance"


class Camera(BaseModel):
    """CCTV Camera configuration."""
    camera_id: str = Field(..., description="Unique camera identifier")
    name: str = Field(..., description="Human-readable camera name")
    location: str = Field(..., description="Physical location of the camera")
    stream_url: str = Field(..., description="RTSP or HTTP stream URL")
    status: CameraStatus = Field(default=CameraStatus.OFFLINE)
    tags: List[str] = Field(default_factory=list, description="Tags for grouping cameras")
    metadata: Dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class MonitoringTask(BaseModel):
    """A natural language monitoring task for the AI agent."""
    task_id: str = Field(..., description="Unique task identifier")
    name: str = Field(..., description="Human-readable task name")
    description: str = Field(..., description="Natural language task description")
    camera_ids: List[str] = Field(..., description="List of camera IDs to monitor")
    prompt: str = Field(
        ..., 
        description="Natural language prompt for the AI agent"
    )
    severity: AlertSeverity = Field(default=AlertSeverity.MEDIUM)
    enabled: bool = Field(default=True)
    schedule: Optional[str] = Field(
        default=None, 
        description="Cron expression for scheduled monitoring (None = continuous)"
    )
    notify_users: List[str] = Field(
        default_factory=list, 
        description="User IDs or FCM tokens to notify"
    )
    cooldown_minutes: int = Field(
        default=5, 
        description="Minutes to wait before sending another alert for same event"
    )
    metadata: Dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class AnalysisResult(BaseModel):
    """Result from the AI video analysis."""
    camera_id: str
    task_id: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    event_detected: bool = Field(default=False)
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    description: str = Field(default="")
    details: Dict[str, Any] = Field(default_factory=dict)
    frame_urls: List[str] = Field(default_factory=list)
    video_clip_url: Optional[str] = Field(default=None)
    raw_response: Optional[str] = Field(default=None)


class Alert(BaseModel):
    """Alert generated when an event is detected."""
    alert_id: str = Field(..., description="Unique alert identifier")
    camera_id: str
    task_id: str
    task_name: str
    severity: AlertSeverity
    status: AlertStatus = Field(default=AlertStatus.PENDING)
    title: str
    description: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    video_clip_url: Optional[str] = Field(default=None)
    thumbnail_url: Optional[str] = Field(default=None)
    location: str
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    notified_users: List[str] = Field(default_factory=list)
    acknowledged_by: Optional[str] = Field(default=None)
    acknowledged_at: Optional[datetime] = Field(default=None)
    resolved_at: Optional[datetime] = Field(default=None)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class VideoFrame(BaseModel):
    """Represents a video frame for analysis."""
    camera_id: str
    timestamp: datetime
    frame_number: int
    gcs_uri: str
    local_path: Optional[str] = None
    width: Optional[int] = None
    height: Optional[int] = None


class VideoClip(BaseModel):
    """Represents a video clip."""
    camera_id: str
    start_time: datetime
    end_time: datetime
    duration_seconds: float
    gcs_uri: str
    size_bytes: Optional[int] = None
    format: str = "mp4"


# API Request/Response Models
class CreateCameraRequest(BaseModel):
    """Request to create a new camera."""
    name: str
    location: str
    stream_url: str
    tags: List[str] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class CreateMonitoringTaskRequest(BaseModel):
    """Request to create a new monitoring task."""
    name: str
    description: str
    camera_ids: List[str]
    prompt: str
    severity: AlertSeverity = AlertSeverity.MEDIUM
    schedule: Optional[str] = None
    notify_users: List[str] = Field(default_factory=list)
    cooldown_minutes: int = 5


class UpdateAlertStatusRequest(BaseModel):
    """Request to update an alert's status."""
    status: AlertStatus
    user_id: Optional[str] = None
    notes: Optional[str] = None


class HealthCheckResponse(BaseModel):
    """Health check response."""
    status: str
    version: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    components: Dict[str, str] = Field(default_factory=dict)
