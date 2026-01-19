"""
Video Stream Handler - Captures CCTV feeds and uploads to Google Cloud Storage.
Supports RTSP, HTTP, and file-based video sources.
"""
import asyncio
import cv2
import tempfile
import os
from datetime import datetime, timedelta
from typing import Optional, AsyncGenerator, List, Dict, Any
from pathlib import Path
import structlog
from google.cloud import storage

from .config import settings
from .models import Camera, VideoFrame, VideoClip, CameraStatus

logger = structlog.get_logger(__name__)


class CloudStorageManager:
    """Manages video storage in Google Cloud Storage."""
    
    def __init__(self):
        self.client = storage.Client(project=settings.google_cloud_project)
        self.bucket = self.client.bucket(settings.gcs_bucket_name)
    
    def upload_frame(self, frame_data: bytes, camera_id: str, timestamp: datetime) -> str:
        """Upload a video frame to GCS."""
        filename = f"{settings.gcs_video_prefix}{camera_id}/frames/{timestamp.strftime('%Y/%m/%d/%H%M%S_%f')}.jpg"
        blob = self.bucket.blob(filename)
        blob.upload_from_string(frame_data, content_type="image/jpeg")
        return f"gs://{settings.gcs_bucket_name}/{filename}"
    
    def upload_video_clip(self, video_path: str, camera_id: str, start_time: datetime) -> str:
        """Upload a video clip to GCS."""
        filename = f"{settings.gcs_clips_prefix}{camera_id}/{start_time.strftime('%Y/%m/%d/%H%M%S')}.mp4"
        blob = self.bucket.blob(filename)
        blob.upload_from_filename(video_path, content_type="video/mp4")
        
        # Make the clip publicly accessible for mobile viewing
        blob.make_public()
        return blob.public_url
    
    def get_signed_url(self, gcs_uri: str, expiration_minutes: int = 60) -> str:
        """Generate a signed URL for temporary access."""
        # Extract blob name from gs:// URI
        blob_name = gcs_uri.replace(f"gs://{settings.gcs_bucket_name}/", "")
        blob = self.bucket.blob(blob_name)
        
        url = blob.generate_signed_url(
            version="v4",
            expiration=timedelta(minutes=expiration_minutes),
            method="GET"
        )
        return url
    
    def list_recent_frames(
        self, camera_id: str, since: datetime, limit: int = 100
    ) -> List[str]:
        """List recent frames for a camera."""
        prefix = f"{settings.gcs_video_prefix}{camera_id}/frames/{since.strftime('%Y/%m/%d')}/"
        blobs = self.bucket.list_blobs(prefix=prefix, max_results=limit)
        return [f"gs://{settings.gcs_bucket_name}/{blob.name}" for blob in blobs]


class VideoStreamCapture:
    """Captures video from CCTV camera streams."""
    
    def __init__(self, camera: Camera, storage_manager: CloudStorageManager):
        self.camera = camera
        self.storage = storage_manager
        self.capture: Optional[cv2.VideoCapture] = None
        self.is_running = False
        self.frame_buffer: List[VideoFrame] = []
        self.buffer_max_size = 300  # ~5 minutes at 1 FPS
        self.logger = logger.bind(camera_id=camera.camera_id)
    
    async def connect(self) -> bool:
        """Connect to the video stream."""
        try:
            self.capture = cv2.VideoCapture(self.camera.stream_url)
            
            if not self.capture.isOpened():
                self.logger.error("Failed to open video stream")
                self.camera.status = CameraStatus.ERROR
                return False
            
            self.camera.status = CameraStatus.ONLINE
            self.logger.info("Connected to video stream")
            return True
            
        except Exception as e:
            self.logger.error("Error connecting to stream", error=str(e))
            self.camera.status = CameraStatus.ERROR
            return False
    
    def disconnect(self):
        """Disconnect from the video stream."""
        if self.capture:
            self.capture.release()
            self.capture = None
        self.camera.status = CameraStatus.OFFLINE
        self.logger.info("Disconnected from video stream")
    
    async def capture_frame(self) -> Optional[VideoFrame]:
        """Capture a single frame from the stream."""
        if not self.capture or not self.capture.isOpened():
            return None
        
        ret, frame = self.capture.read()
        if not ret:
            self.logger.warning("Failed to capture frame")
            return None
        
        timestamp = datetime.utcnow()
        
        # Encode frame as JPEG
        _, buffer = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
        frame_data = buffer.tobytes()
        
        # Upload to GCS
        gcs_uri = self.storage.upload_frame(
            frame_data, self.camera.camera_id, timestamp
        )
        
        video_frame = VideoFrame(
            camera_id=self.camera.camera_id,
            timestamp=timestamp,
            frame_number=len(self.frame_buffer),
            gcs_uri=gcs_uri,
            width=frame.shape[1],
            height=frame.shape[0]
        )
        
        # Add to buffer
        self.frame_buffer.append(video_frame)
        if len(self.frame_buffer) > self.buffer_max_size:
            self.frame_buffer.pop(0)
        
        return video_frame
    
    async def capture_continuous(
        self, frame_interval_seconds: float = 1.0
    ) -> AsyncGenerator[VideoFrame, None]:
        """Continuously capture frames at the specified interval."""
        self.is_running = True
        
        while self.is_running:
            frame = await self.capture_frame()
            if frame:
                yield frame
            await asyncio.sleep(frame_interval_seconds)
    
    def stop_capture(self):
        """Stop continuous capture."""
        self.is_running = False
    
    async def create_video_clip(
        self, duration_seconds: int = 60
    ) -> Optional[VideoClip]:
        """Create a video clip from recent frames."""
        if len(self.frame_buffer) < 10:
            self.logger.warning("Not enough frames for video clip")
            return None
        
        # Get frames for the clip duration
        frames_needed = min(
            duration_seconds * settings.video_frame_rate,
            len(self.frame_buffer)
        )
        recent_frames = self.frame_buffer[-frames_needed:]
        
        # Create temporary video file
        with tempfile.NamedTemporaryFile(suffix='.mp4', delete=False) as tmp_file:
            tmp_path = tmp_file.name
        
        try:
            # Get first frame dimensions
            first_frame_url = self.storage.get_signed_url(recent_frames[0].gcs_uri)
            
            # Initialize video writer
            fourcc = cv2.VideoWriter_fourcc(*'mp4v')
            width = recent_frames[0].width or 1920
            height = recent_frames[0].height or 1080
            
            out = cv2.VideoWriter(
                tmp_path, fourcc, settings.video_frame_rate, (width, height)
            )
            
            # Download and write frames
            import urllib.request
            for frame_info in recent_frames:
                signed_url = self.storage.get_signed_url(frame_info.gcs_uri)
                
                # Download frame
                with urllib.request.urlopen(signed_url) as response:
                    frame_data = response.read()
                
                # Decode and write
                import numpy as np
                nparr = np.frombuffer(frame_data, np.uint8)
                frame = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
                
                if frame is not None:
                    out.write(frame)
            
            out.release()
            
            # Upload clip to GCS
            start_time = recent_frames[0].timestamp
            clip_url = self.storage.upload_video_clip(
                tmp_path, self.camera.camera_id, start_time
            )
            
            clip = VideoClip(
                camera_id=self.camera.camera_id,
                start_time=start_time,
                end_time=recent_frames[-1].timestamp,
                duration_seconds=(recent_frames[-1].timestamp - start_time).total_seconds(),
                gcs_uri=clip_url,
                size_bytes=os.path.getsize(tmp_path)
            )
            
            self.logger.info("Created video clip", clip_url=clip_url)
            return clip
            
        except Exception as e:
            self.logger.error("Error creating video clip", error=str(e))
            return None
        finally:
            # Cleanup temp file
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)
    
    def get_recent_frames(self, count: int = 10) -> List[VideoFrame]:
        """Get the most recent frames from the buffer."""
        return self.frame_buffer[-count:]


class VideoStreamManager:
    """Manages multiple video streams."""
    
    def __init__(self):
        self.storage = CloudStorageManager()
        self.streams: Dict[str, VideoStreamCapture] = {}
        self.capture_tasks: Dict[str, asyncio.Task] = {}
        self.logger = logger.bind(component="VideoStreamManager")
    
    async def add_camera(self, camera: Camera) -> bool:
        """Add a camera and start capturing."""
        if camera.camera_id in self.streams:
            self.logger.warning("Camera already registered", camera_id=camera.camera_id)
            return False
        
        stream = VideoStreamCapture(camera, self.storage)
        connected = await stream.connect()
        
        if connected:
            self.streams[camera.camera_id] = stream
            
            # Start capture task
            task = asyncio.create_task(
                self._capture_loop(camera.camera_id)
            )
            self.capture_tasks[camera.camera_id] = task
            
            self.logger.info("Camera added and started", camera_id=camera.camera_id)
            return True
        
        return False
    
    async def _capture_loop(self, camera_id: str):
        """Background loop for continuous frame capture."""
        stream = self.streams.get(camera_id)
        if not stream:
            return
        
        async for frame in stream.capture_continuous(
            frame_interval_seconds=1.0 / settings.video_frame_rate
        ):
            # Frame captured and stored
            pass
    
    async def remove_camera(self, camera_id: str):
        """Remove a camera and stop capturing."""
        if camera_id in self.capture_tasks:
            self.capture_tasks[camera_id].cancel()
            del self.capture_tasks[camera_id]
        
        if camera_id in self.streams:
            self.streams[camera_id].stop_capture()
            self.streams[camera_id].disconnect()
            del self.streams[camera_id]
        
        self.logger.info("Camera removed", camera_id=camera_id)
    
    def get_stream(self, camera_id: str) -> Optional[VideoStreamCapture]:
        """Get a video stream by camera ID."""
        return self.streams.get(camera_id)
    
    def get_all_cameras(self) -> List[Camera]:
        """Get all registered cameras."""
        return [stream.camera for stream in self.streams.values()]
    
    async def create_clip_for_camera(
        self, camera_id: str, duration_seconds: int = 60
    ) -> Optional[VideoClip]:
        """Create a video clip for a specific camera."""
        stream = self.streams.get(camera_id)
        if not stream:
            return None
        return await stream.create_video_clip(duration_seconds)
    
    async def shutdown(self):
        """Shutdown all streams."""
        camera_ids = list(self.streams.keys())
        for camera_id in camera_ids:
            await self.remove_camera(camera_id)
        self.logger.info("All streams shutdown")
