"""
FastAPI REST API for the Video Intelligence Agent system.
"""
from datetime import datetime
from typing import List, Optional
from fastapi import FastAPI, HTTPException, Depends, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import structlog
import uuid

from .config import settings, get_settings
from .models import (
    Camera, MonitoringTask, Alert, AlertSeverity, AlertStatus,
    CreateCameraRequest, CreateMonitoringTaskRequest,
    UpdateAlertStatusRequest, HealthCheckResponse, CameraStatus
)
from .video_handler import VideoStreamManager, CloudStorageManager
from .video_intelligence import VideoIntelligenceAgent, TaskPromptBuilder
from .alert_system import AlertManager
from .monitoring_engine import MonitoringEngine, TaskTemplates

logger = structlog.get_logger(__name__)

# Initialize FastAPI app
app = FastAPI(
    title="Video Intelligence Agent API",
    description="API for CCTV monitoring with AI-powered video analysis",
    version="1.0.0"
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global instances
stream_manager: Optional[VideoStreamManager] = None
ai_agent: Optional[VideoIntelligenceAgent] = None
alert_manager: Optional[AlertManager] = None
monitoring_engine: Optional[MonitoringEngine] = None

# In-memory alert storage (use a database in production)
alerts_db: dict[str, Alert] = {}


@app.on_event("startup")
async def startup_event():
    """Initialize all components on startup."""
    global stream_manager, ai_agent, alert_manager, monitoring_engine
    
    logger.info("Starting Video Intelligence Agent...")
    
    stream_manager = VideoStreamManager()
    ai_agent = VideoIntelligenceAgent()
    alert_manager = AlertManager()
    
    monitoring_engine = MonitoringEngine(
        stream_manager=stream_manager,
        ai_agent=ai_agent,
        alert_manager=alert_manager
    )
    
    # Set up alert callback to store alerts
    monitoring_engine.on_alert_callback = lambda alert: alerts_db.update({alert.alert_id: alert})
    
    await monitoring_engine.start()
    
    logger.info("Video Intelligence Agent started successfully")


@app.on_event("shutdown")
async def shutdown_event():
    """Cleanup on shutdown."""
    global monitoring_engine
    
    if monitoring_engine:
        await monitoring_engine.stop()
    
    logger.info("Video Intelligence Agent shutdown complete")


# Health Check
@app.get("/health", response_model=HealthCheckResponse)
async def health_check():
    """Health check endpoint."""
    return HealthCheckResponse(
        status="healthy",
        version="1.0.0",
        components={
            "stream_manager": "ok" if stream_manager else "not_initialized",
            "ai_agent": "ok" if ai_agent else "not_initialized",
            "monitoring_engine": "ok" if monitoring_engine else "not_initialized"
        }
    )


# Camera Endpoints
@app.post("/cameras", response_model=Camera)
async def create_camera(request: CreateCameraRequest):
    """Register a new camera."""
    camera = Camera(
        camera_id=str(uuid.uuid4()),
        name=request.name,
        location=request.location,
        stream_url=request.stream_url,
        tags=request.tags,
        metadata=request.metadata
    )
    
    success = await monitoring_engine.register_camera(camera)
    
    if not success:
        raise HTTPException(status_code=400, detail="Failed to register camera")
    
    return camera


@app.get("/cameras", response_model=List[Camera])
async def list_cameras():
    """List all registered cameras."""
    return monitoring_engine.get_all_cameras()


@app.get("/cameras/{camera_id}", response_model=Camera)
async def get_camera(camera_id: str):
    """Get a specific camera."""
    camera = monitoring_engine.get_camera(camera_id)
    if not camera:
        raise HTTPException(status_code=404, detail="Camera not found")
    return camera


@app.delete("/cameras/{camera_id}")
async def delete_camera(camera_id: str):
    """Unregister a camera."""
    await monitoring_engine.unregister_camera(camera_id)
    return {"message": "Camera deleted"}


# Monitoring Task Endpoints
@app.post("/tasks", response_model=MonitoringTask)
async def create_task(request: CreateMonitoringTaskRequest):
    """Create a new monitoring task."""
    task = MonitoringTask(
        task_id=str(uuid.uuid4()),
        name=request.name,
        description=request.description,
        camera_ids=request.camera_ids,
        prompt=request.prompt,
        severity=request.severity,
        schedule=request.schedule,
        notify_users=request.notify_users,
        cooldown_minutes=request.cooldown_minutes
    )
    
    try:
        await monitoring_engine.add_task(task)
        return task
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/tasks", response_model=List[MonitoringTask])
async def list_tasks():
    """List all monitoring tasks."""
    return monitoring_engine.get_all_tasks()


@app.get("/tasks/{task_id}", response_model=MonitoringTask)
async def get_task(task_id: str):
    """Get a specific task."""
    task = monitoring_engine.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return task


@app.put("/tasks/{task_id}", response_model=MonitoringTask)
async def update_task(task_id: str, updates: dict):
    """Update a monitoring task."""
    task = await monitoring_engine.update_task(task_id, updates)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return task


@app.delete("/tasks/{task_id}")
async def delete_task(task_id: str):
    """Delete a monitoring task."""
    await monitoring_engine.remove_task(task_id)
    return {"message": "Task deleted"}


@app.post("/tasks/{task_id}/enable")
async def enable_task(task_id: str):
    """Enable a monitoring task."""
    task = await monitoring_engine.update_task(task_id, {"enabled": True})
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return {"message": "Task enabled"}


@app.post("/tasks/{task_id}/disable")
async def disable_task(task_id: str):
    """Disable a monitoring task."""
    task = await monitoring_engine.update_task(task_id, {"enabled": False})
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return {"message": "Task disabled"}


# Task Templates
@app.get("/task-templates")
async def list_task_templates():
    """List available task templates."""
    return {
        "templates": [
            {
                "name": "queue_monitoring",
                "description": "Monitor for queue/line buildup",
                "parameters": ["max_queue_size", "wait_time_minutes"]
            },
            {
                "name": "after_hours_monitoring",
                "description": "Monitor for after-hours access",
                "parameters": ["start_hour", "end_hour"]
            },
            {
                "name": "crowd_density_monitoring",
                "description": "Monitor crowd density levels",
                "parameters": ["max_people"]
            },
            {
                "name": "safety_monitoring",
                "description": "Monitor for safety hazards",
                "parameters": []
            },
            {
                "name": "loitering_detection",
                "description": "Detect loitering behavior",
                "parameters": ["duration_minutes"]
            }
        ]
    }


@app.post("/task-templates/{template_name}")
async def create_task_from_template(
    template_name: str,
    name: str,
    camera_ids: List[str],
    notify_users: List[str] = None,
    **kwargs
):
    """Create a task from a template."""
    template_map = {
        "queue_monitoring": TaskTemplates.queue_monitoring,
        "after_hours_monitoring": TaskTemplates.after_hours_monitoring,
        "crowd_density_monitoring": TaskTemplates.crowd_density_monitoring,
        "safety_monitoring": TaskTemplates.safety_monitoring,
        "loitering_detection": TaskTemplates.loitering_detection
    }
    
    if template_name not in template_map:
        raise HTTPException(status_code=404, detail="Template not found")
    
    try:
        task = template_map[template_name](
            name=name,
            camera_ids=camera_ids,
            notify_users=notify_users or [],
            **kwargs
        )
        await monitoring_engine.add_task(task)
        return task
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


# Manual Analysis
@app.post("/analyze/{camera_id}/{task_id}")
async def run_manual_analysis(camera_id: str, task_id: str):
    """Run manual analysis for a camera and task."""
    result = await monitoring_engine.run_manual_analysis(camera_id, task_id)
    
    if not result:
        raise HTTPException(status_code=404, detail="Camera or task not found")
    
    return {
        "camera_id": result.camera_id,
        "task_id": result.task_id,
        "event_detected": result.event_detected,
        "confidence": result.confidence,
        "description": result.description,
        "details": result.details,
        "timestamp": result.timestamp.isoformat()
    }


# Alert Endpoints
@app.get("/alerts", response_model=List[Alert])
async def list_alerts(
    status: Optional[AlertStatus] = None,
    severity: Optional[AlertSeverity] = None,
    camera_id: Optional[str] = None,
    limit: int = 100
):
    """List alerts with optional filters."""
    alerts = list(alerts_db.values())
    
    if status:
        alerts = [a for a in alerts if a.status == status]
    if severity:
        alerts = [a for a in alerts if a.severity == severity]
    if camera_id:
        alerts = [a for a in alerts if a.camera_id == camera_id]
    
    # Sort by timestamp descending
    alerts.sort(key=lambda a: a.timestamp, reverse=True)
    
    return alerts[:limit]


@app.get("/alerts/{alert_id}", response_model=Alert)
async def get_alert(alert_id: str):
    """Get a specific alert."""
    alert = alerts_db.get(alert_id)
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")
    return alert


@app.put("/alerts/{alert_id}/status")
async def update_alert_status(alert_id: str, request: UpdateAlertStatusRequest):
    """Update an alert's status."""
    alert = alerts_db.get(alert_id)
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")
    
    alert.status = request.status
    
    if request.status == AlertStatus.ACKNOWLEDGED and request.user_id:
        alert.acknowledged_by = request.user_id
        alert.acknowledged_at = datetime.utcnow()
    elif request.status == AlertStatus.RESOLVED:
        alert.resolved_at = datetime.utcnow()
    
    if request.notes:
        alert.metadata["notes"] = request.notes
    
    return alert


# Video Clip Endpoints
@app.post("/cameras/{camera_id}/clip")
async def create_video_clip(camera_id: str, duration_seconds: int = 60):
    """Create a video clip from recent footage."""
    clip = await stream_manager.create_clip_for_camera(camera_id, duration_seconds)
    
    if not clip:
        raise HTTPException(status_code=404, detail="Camera not found or no frames available")
    
    return {
        "camera_id": clip.camera_id,
        "start_time": clip.start_time.isoformat(),
        "end_time": clip.end_time.isoformat(),
        "duration_seconds": clip.duration_seconds,
        "url": clip.gcs_uri
    }


# Prompt Templates
@app.get("/prompt-templates")
async def list_prompt_templates():
    """List available prompt templates."""
    return {
        "templates": TaskPromptBuilder.get_available_templates()
    }


@app.post("/prompt-templates/{template_name}")
async def build_prompt_from_template(template_name: str, parameters: dict):
    """Build a prompt from a template."""
    try:
        prompt = TaskPromptBuilder.build_prompt(template_name, **parameters)
        return {"prompt": prompt}
    except (ValueError, KeyError) as e:
        raise HTTPException(status_code=400, detail=str(e))


# Statistics
@app.get("/stats")
async def get_statistics():
    """Get system statistics."""
    return {
        "cameras": {
            "total": len(monitoring_engine.get_all_cameras()),
            "online": sum(1 for c in monitoring_engine.get_all_cameras() if c.status == CameraStatus.ONLINE)
        },
        "tasks": {
            "total": len(monitoring_engine.get_all_tasks()),
            "enabled": sum(1 for t in monitoring_engine.get_all_tasks() if t.enabled)
        },
        "alerts": {
            "total": len(alerts_db),
            "pending": sum(1 for a in alerts_db.values() if a.status == AlertStatus.PENDING),
            "by_severity": {
                s.value: sum(1 for a in alerts_db.values() if a.severity == s)
                for s in AlertSeverity
            }
        }
    }
