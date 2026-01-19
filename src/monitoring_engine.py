"""
Monitoring Rules Engine - Manages monitoring tasks and schedules analysis.
"""
import asyncio
import uuid
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Any, Callable
import structlog
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from .config import settings
from .models import (
    MonitoringTask, Camera, Alert, AlertSeverity, 
    AnalysisResult, VideoFrame
)
from .video_handler import VideoStreamManager
from .video_intelligence import VideoIntelligenceAgent
from .alert_system import AlertManager

logger = structlog.get_logger(__name__)


class MonitoringEngine:
    """
    Core engine that orchestrates video monitoring tasks.
    Manages the lifecycle of monitoring jobs and coordinates between components.
    """
    
    def __init__(
        self,
        stream_manager: VideoStreamManager,
        ai_agent: VideoIntelligenceAgent,
        alert_manager: AlertManager
    ):
        self.stream_manager = stream_manager
        self.ai_agent = ai_agent
        self.alert_manager = alert_manager
        
        self.scheduler = AsyncIOScheduler()
        self.tasks: Dict[str, MonitoringTask] = {}
        self.cameras: Dict[str, Camera] = {}
        
        # Callbacks for external event handling
        self.on_alert_callback: Optional[Callable[[Alert], None]] = None
        
        self.logger = logger.bind(component="MonitoringEngine")
    
    async def start(self):
        """Start the monitoring engine."""
        self.scheduler.start()
        self.logger.info("Monitoring engine started")
    
    async def stop(self):
        """Stop the monitoring engine."""
        self.scheduler.shutdown(wait=False)
        await self.stream_manager.shutdown()
        await self.alert_manager.close()
        self.logger.info("Monitoring engine stopped")
    
    # Camera Management
    async def register_camera(self, camera: Camera) -> bool:
        """Register a camera for monitoring."""
        if camera.camera_id in self.cameras:
            self.logger.warning("Camera already registered", camera_id=camera.camera_id)
            return False
        
        # Add to stream manager
        success = await self.stream_manager.add_camera(camera)
        
        if success:
            self.cameras[camera.camera_id] = camera
            self.logger.info("Camera registered", camera_id=camera.camera_id)
            return True
        
        return False
    
    async def unregister_camera(self, camera_id: str):
        """Unregister a camera."""
        if camera_id in self.cameras:
            # Remove any tasks using this camera
            tasks_to_remove = [
                task_id for task_id, task in self.tasks.items()
                if camera_id in task.camera_ids
            ]
            for task_id in tasks_to_remove:
                await self.remove_task(task_id)
            
            # Remove from stream manager
            await self.stream_manager.remove_camera(camera_id)
            del self.cameras[camera_id]
            
            self.logger.info("Camera unregistered", camera_id=camera_id)
    
    def get_camera(self, camera_id: str) -> Optional[Camera]:
        """Get camera by ID."""
        return self.cameras.get(camera_id)
    
    def get_all_cameras(self) -> List[Camera]:
        """Get all registered cameras."""
        return list(self.cameras.values())
    
    # Task Management
    async def add_task(self, task: MonitoringTask) -> str:
        """
        Add a monitoring task.
        
        Args:
            task: The monitoring task to add
            
        Returns:
            Task ID
        """
        # Validate cameras exist
        for camera_id in task.camera_ids:
            if camera_id not in self.cameras:
                raise ValueError(f"Camera {camera_id} not registered")
        
        # Generate ID if not provided
        if not task.task_id:
            task.task_id = str(uuid.uuid4())
        
        self.tasks[task.task_id] = task
        
        # Schedule the task
        if task.enabled:
            self._schedule_task(task)
        
        self.logger.info(
            "Monitoring task added",
            task_id=task.task_id,
            name=task.name,
            cameras=task.camera_ids
        )
        
        return task.task_id
    
    async def remove_task(self, task_id: str):
        """Remove a monitoring task."""
        if task_id in self.tasks:
            # Remove scheduled job
            job_id = f"task_{task_id}"
            if self.scheduler.get_job(job_id):
                self.scheduler.remove_job(job_id)
            
            del self.tasks[task_id]
            self.logger.info("Task removed", task_id=task_id)
    
    async def update_task(self, task_id: str, updates: Dict[str, Any]) -> Optional[MonitoringTask]:
        """Update a monitoring task."""
        if task_id not in self.tasks:
            return None
        
        task = self.tasks[task_id]
        
        # Update fields
        for key, value in updates.items():
            if hasattr(task, key):
                setattr(task, key, value)
        
        task.updated_at = datetime.utcnow()
        
        # Reschedule if needed
        job_id = f"task_{task_id}"
        if self.scheduler.get_job(job_id):
            self.scheduler.remove_job(job_id)
        
        if task.enabled:
            self._schedule_task(task)
        
        self.logger.info("Task updated", task_id=task_id)
        return task
    
    def get_task(self, task_id: str) -> Optional[MonitoringTask]:
        """Get task by ID."""
        return self.tasks.get(task_id)
    
    def get_all_tasks(self) -> List[MonitoringTask]:
        """Get all monitoring tasks."""
        return list(self.tasks.values())
    
    def _schedule_task(self, task: MonitoringTask):
        """Schedule a monitoring task."""
        job_id = f"task_{task.task_id}"
        
        if task.schedule:
            # Use cron schedule
            trigger = CronTrigger.from_crontab(task.schedule)
        else:
            # Use interval-based continuous monitoring
            trigger = IntervalTrigger(
                seconds=settings.video_analysis_interval_seconds
            )
        
        self.scheduler.add_job(
            self._execute_task,
            trigger=trigger,
            id=job_id,
            args=[task.task_id],
            max_instances=1,
            replace_existing=True
        )
        
        self.logger.debug("Task scheduled", task_id=task.task_id, schedule=task.schedule)
    
    async def _execute_task(self, task_id: str):
        """Execute a monitoring task."""
        task = self.tasks.get(task_id)
        if not task or not task.enabled:
            return
        
        self.logger.info("Executing monitoring task", task_id=task_id, name=task.name)
        
        for camera_id in task.camera_ids:
            try:
                await self._analyze_camera_for_task(camera_id, task)
            except Exception as e:
                self.logger.error(
                    "Error analyzing camera",
                    camera_id=camera_id,
                    task_id=task_id,
                    error=str(e)
                )
    
    async def _analyze_camera_for_task(self, camera_id: str, task: MonitoringTask):
        """Analyze a camera feed for a specific task."""
        camera = self.cameras.get(camera_id)
        stream = self.stream_manager.get_stream(camera_id)
        
        if not camera or not stream:
            self.logger.warning("Camera or stream not found", camera_id=camera_id)
            return
        
        # Get recent frames for analysis
        frames = stream.get_recent_frames(count=10)
        
        if not frames:
            self.logger.warning("No frames available", camera_id=camera_id)
            return
        
        # Run AI analysis
        result = await self.ai_agent.analyze_frames(
            frames=frames,
            task=task,
            camera_location=camera.location
        )
        
        # Check if event detected with sufficient confidence
        if result.event_detected and result.confidence >= 0.6:
            await self._handle_detection(camera, task, result)
    
    async def _handle_detection(
        self,
        camera: Camera,
        task: MonitoringTask,
        result: AnalysisResult
    ):
        """Handle a detected event."""
        # Check cooldown
        if not self.alert_manager.should_send_alert(
            camera.camera_id, task.task_id, task.cooldown_minutes
        ):
            return
        
        self.logger.info(
            "Event detected",
            camera_id=camera.camera_id,
            task_id=task.task_id,
            confidence=result.confidence
        )
        
        # Create video clip
        stream = self.stream_manager.get_stream(camera.camera_id)
        video_clip = None
        if stream:
            video_clip = await stream.create_video_clip(
                duration_seconds=settings.video_clip_duration_seconds
            )
        
        # Create alert
        alert = Alert(
            alert_id=str(uuid.uuid4()),
            camera_id=camera.camera_id,
            task_id=task.task_id,
            task_name=task.name,
            severity=task.severity,
            title=f"{task.name} - {camera.location}",
            description=result.description,
            location=camera.location,
            confidence=result.confidence,
            video_clip_url=video_clip.gcs_uri if video_clip else None,
            thumbnail_url=result.frame_urls[0] if result.frame_urls else None,
            metadata={
                "details": result.details,
                "analysis_timestamp": result.timestamp.isoformat()
            }
        )
        
        # Send alert
        await self.alert_manager.send_alert(
            alert=alert,
            device_tokens=task.notify_users,
            topic=f"camera_{camera.camera_id}"
        )
        
        # Invoke callback if set
        if self.on_alert_callback:
            self.on_alert_callback(alert)
    
    async def run_manual_analysis(
        self,
        camera_id: str,
        task_id: str
    ) -> Optional[AnalysisResult]:
        """Run manual analysis for a camera and task."""
        camera = self.cameras.get(camera_id)
        task = self.tasks.get(task_id)
        stream = self.stream_manager.get_stream(camera_id)
        
        if not all([camera, task, stream]):
            return None
        
        frames = stream.get_recent_frames(count=10)
        if not frames:
            return None
        
        return await self.ai_agent.analyze_frames(
            frames=frames,
            task=task,
            camera_location=camera.location
        )


class TaskTemplates:
    """Pre-built monitoring task templates for common use cases."""
    
    @staticmethod
    def queue_monitoring(
        name: str,
        camera_ids: List[str],
        max_queue_size: int = 10,
        wait_time_minutes: int = 5,
        notify_users: List[str] = None
    ) -> MonitoringTask:
        """Create a queue monitoring task."""
        return MonitoringTask(
            task_id=str(uuid.uuid4()),
            name=name,
            description=f"Monitor for queues exceeding {max_queue_size} people waiting more than {wait_time_minutes} minutes",
            camera_ids=camera_ids,
            prompt=f"""Monitor the queue/line in this area. Alert if:
- More than {max_queue_size} people are visibly waiting in line
- The queue appears to have been present for an extended period
- People show signs of frustration or long wait (checking watches, fidgeting)

Count all people who appear to be in a queue formation, not just those at the front.
Look for queue barriers, ropes, or natural line formations.""",
            severity=AlertSeverity.MEDIUM,
            notify_users=notify_users or [],
            cooldown_minutes=10
        )
    
    @staticmethod
    def after_hours_monitoring(
        name: str,
        camera_ids: List[str],
        start_hour: int = 22,  # 10 PM
        end_hour: int = 6,    # 6 AM
        notify_users: List[str] = None
    ) -> MonitoringTask:
        """Create an after-hours access monitoring task."""
        return MonitoringTask(
            task_id=str(uuid.uuid4()),
            name=name,
            description=f"Monitor for any access between {start_hour}:00 and {end_hour}:00",
            camera_ids=camera_ids,
            prompt=f"""This is a restricted area during off-hours ({start_hour}:00 - {end_hour}:00).
Alert if you detect:
- Any person present in the monitored area
- Doors opening or being accessed
- Any movement or activity
- Lights being turned on

This is a high-security monitoring task. Any human presence should trigger an alert.""",
            severity=AlertSeverity.HIGH,
            schedule=f"*/5 {start_hour}-23,0-{end_hour-1} * * *",  # Every 5 min during hours
            notify_users=notify_users or [],
            cooldown_minutes=5
        )
    
    @staticmethod
    def crowd_density_monitoring(
        name: str,
        camera_ids: List[str],
        max_people: int = 50,
        notify_users: List[str] = None
    ) -> MonitoringTask:
        """Create a crowd density monitoring task."""
        return MonitoringTask(
            task_id=str(uuid.uuid4()),
            name=name,
            description=f"Monitor crowd density, alert if more than {max_people} people",
            camera_ids=camera_ids,
            prompt=f"""Monitor the crowd density in this area. Alert if:
- Estimated crowd size exceeds {max_people} people
- The area appears overcrowded relative to its size
- Movement becomes restricted due to density
- Safety exits appear blocked by crowd

Consider the full visible area and estimate total occupancy.""",
            severity=AlertSeverity.HIGH,
            notify_users=notify_users or [],
            cooldown_minutes=15
        )
    
    @staticmethod
    def safety_monitoring(
        name: str,
        camera_ids: List[str],
        notify_users: List[str] = None
    ) -> MonitoringTask:
        """Create a safety hazard monitoring task."""
        return MonitoringTask(
            task_id=str(uuid.uuid4()),
            name=name,
            description="Monitor for safety hazards and incidents",
            camera_ids=camera_ids,
            prompt="""Monitor for safety hazards and incidents:
- Slips, trips, or falls
- Spills or wet floors
- Objects blocking walkways or exits
- Unsafe behavior (running, horseplay)
- Fire hazards or smoke
- Medical emergencies (person collapsed)

Prioritize immediate safety concerns. Any observed injury or dangerous condition
should be flagged with high confidence.""",
            severity=AlertSeverity.CRITICAL,
            notify_users=notify_users or [],
            cooldown_minutes=2  # Short cooldown for safety
        )
    
    @staticmethod
    def loitering_detection(
        name: str,
        camera_ids: List[str],
        duration_minutes: int = 15,
        notify_users: List[str] = None
    ) -> MonitoringTask:
        """Create a loitering detection task."""
        return MonitoringTask(
            task_id=str(uuid.uuid4()),
            name=name,
            description=f"Detect individuals loitering for more than {duration_minutes} minutes",
            camera_ids=camera_ids,
            prompt=f"""Monitor for loitering behavior. Alert if:
- Individual(s) remain in the same area for an extended period (>{duration_minutes} minutes)
- Person appears to have no clear purpose (not shopping, waiting for someone, etc.)
- Suspicious behavior such as watching others, checking surroundings repeatedly
- Person returns to the same location multiple times

Note: Do not flag employees, security personnel, or people clearly waiting for
legitimate reasons (bus stop, meeting point).""",
            severity=AlertSeverity.MEDIUM,
            notify_users=notify_users or [],
            cooldown_minutes=20
        )
    
    @staticmethod
    def custom_task(
        name: str,
        description: str,
        camera_ids: List[str],
        prompt: str,
        severity: AlertSeverity = AlertSeverity.MEDIUM,
        schedule: Optional[str] = None,
        notify_users: List[str] = None,
        cooldown_minutes: int = 5
    ) -> MonitoringTask:
        """Create a custom monitoring task."""
        return MonitoringTask(
            task_id=str(uuid.uuid4()),
            name=name,
            description=description,
            camera_ids=camera_ids,
            prompt=prompt,
            severity=severity,
            schedule=schedule,
            notify_users=notify_users or [],
            cooldown_minutes=cooldown_minutes
        )
