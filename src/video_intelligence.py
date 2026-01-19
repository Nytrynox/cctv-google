"""
Video Intelligence Agent - Uses Vertex AI Gemini for video analysis.
This is the core AI engine that processes video frames and detects events.
"""
import asyncio
import json
import base64
from datetime import datetime
from typing import List, Optional, Dict, Any
import structlog
import vertexai
from vertexai.generative_models import GenerativeModel, Part, GenerationConfig
from google.cloud import storage

from .config import settings
from .models import (
    MonitoringTask, AnalysisResult, VideoFrame, 
    AlertSeverity
)

logger = structlog.get_logger(__name__)


class VideoIntelligenceAgent:
    """
    AI Agent that uses Gemini multimodal model to analyze video feeds.
    Processes frames and detects events based on natural language prompts.
    """
    
    def __init__(self):
        # Initialize Vertex AI
        vertexai.init(
            project=settings.google_cloud_project,
            location=settings.vertex_ai_location
        )
        
        self.model = GenerativeModel(settings.vertex_ai_model)
        self.storage_client = storage.Client(project=settings.google_cloud_project)
        self.bucket = self.storage_client.bucket(settings.gcs_bucket_name)
        
        self.logger = logger.bind(component="VideoIntelligenceAgent")
        
        # System prompt for the agent
        self.system_prompt = """You are a professional security monitoring AI agent analyzing CCTV footage.
Your task is to carefully analyze the provided video frames and determine if specific events are occurring.

IMPORTANT GUIDELINES:
1. Analyze all frames provided to understand the scene context
2. Look for the specific events described in the monitoring task
3. Be precise and avoid false positives - only flag events you are confident about
4. Provide clear descriptions of what you observe
5. Estimate confidence levels accurately

For each analysis, you must respond with a valid JSON object containing:
{
    "event_detected": true/false,
    "confidence": 0.0-1.0,
    "description": "Clear description of what you observed",
    "details": {
        "people_count": number (if relevant),
        "objects_detected": ["list of relevant objects"],
        "activity_type": "description of activity",
        "time_context": "any temporal observations",
        "location_context": "where in frame events occur"
    },
    "reasoning": "Explanation of why you made this determination"
}

Be conservative with event detection - it's better to miss a marginal event than to generate false alarms.
"""
    
    def _download_frame(self, gcs_uri: str) -> bytes:
        """Download a frame from GCS."""
        # Extract blob name from gs:// URI
        blob_name = gcs_uri.replace(f"gs://{settings.gcs_bucket_name}/", "")
        blob = self.bucket.blob(blob_name)
        return blob.download_as_bytes()
    
    def _create_frame_parts(self, frames: List[VideoFrame]) -> List[Part]:
        """Create Gemini Parts from video frames."""
        parts = []
        
        for i, frame in enumerate(frames):
            try:
                frame_data = self._download_frame(frame.gcs_uri)
                
                # Create image part
                parts.append(
                    Part.from_data(frame_data, mime_type="image/jpeg")
                )
                
                # Add timestamp context
                parts.append(
                    Part.from_text(f"[Frame {i+1} - Timestamp: {frame.timestamp.isoformat()}]")
                )
                
            except Exception as e:
                self.logger.error(
                    "Error loading frame", 
                    frame_uri=frame.gcs_uri, 
                    error=str(e)
                )
        
        return parts
    
    async def analyze_frames(
        self,
        frames: List[VideoFrame],
        task: MonitoringTask,
        camera_location: str = "Unknown"
    ) -> AnalysisResult:
        """
        Analyze video frames for a specific monitoring task.
        
        Args:
            frames: List of video frames to analyze
            task: The monitoring task with the detection prompt
            camera_location: Physical location of the camera
            
        Returns:
            AnalysisResult with detection status and details
        """
        if not frames:
            return AnalysisResult(
                camera_id=frames[0].camera_id if frames else "unknown",
                task_id=task.task_id,
                event_detected=False,
                description="No frames provided for analysis"
            )
        
        camera_id = frames[0].camera_id
        
        self.logger.info(
            "Analyzing frames",
            camera_id=camera_id,
            task_id=task.task_id,
            frame_count=len(frames)
        )
        
        try:
            # Build the analysis prompt
            analysis_prompt = f"""
MONITORING TASK: {task.name}
TASK DESCRIPTION: {task.description}
CAMERA LOCATION: {camera_location}

SPECIFIC DETECTION CRITERIA:
{task.prompt}

Analyze the following {len(frames)} video frames captured over the recent period.
Determine if the specified event is occurring and provide your analysis in JSON format.
"""
            
            # Create content parts
            content_parts = [Part.from_text(self.system_prompt)]
            content_parts.extend(self._create_frame_parts(frames))
            content_parts.append(Part.from_text(analysis_prompt))
            
            # Configure generation
            generation_config = GenerationConfig(
                temperature=0.2,  # Low temperature for consistent analysis
                top_p=0.8,
                max_output_tokens=1024,
            )
            
            # Call Gemini
            response = await asyncio.to_thread(
                self.model.generate_content,
                content_parts,
                generation_config=generation_config
            )
            
            # Parse response
            response_text = response.text
            self.logger.debug("Raw AI response", response=response_text)
            
            # Extract JSON from response
            result_data = self._parse_response(response_text)
            
            analysis_result = AnalysisResult(
                camera_id=camera_id,
                task_id=task.task_id,
                timestamp=datetime.utcnow(),
                event_detected=result_data.get("event_detected", False),
                confidence=result_data.get("confidence", 0.0),
                description=result_data.get("description", ""),
                details=result_data.get("details", {}),
                frame_urls=[f.gcs_uri for f in frames],
                raw_response=response_text
            )
            
            self.logger.info(
                "Analysis complete",
                camera_id=camera_id,
                task_id=task.task_id,
                event_detected=analysis_result.event_detected,
                confidence=analysis_result.confidence
            )
            
            return analysis_result
            
        except Exception as e:
            self.logger.error(
                "Error during analysis",
                camera_id=camera_id,
                task_id=task.task_id,
                error=str(e)
            )
            
            return AnalysisResult(
                camera_id=camera_id,
                task_id=task.task_id,
                event_detected=False,
                description=f"Analysis error: {str(e)}"
            )
    
    def _parse_response(self, response_text: str) -> Dict[str, Any]:
        """Parse JSON from the AI response."""
        try:
            # Try to find JSON in the response
            import re
            
            # Look for JSON block
            json_match = re.search(r'\{[\s\S]*\}', response_text)
            if json_match:
                return json.loads(json_match.group())
            
            # If no JSON found, return default
            return {
                "event_detected": False,
                "confidence": 0.0,
                "description": response_text,
                "details": {}
            }
            
        except json.JSONDecodeError as e:
            self.logger.warning("Failed to parse JSON response", error=str(e))
            return {
                "event_detected": False,
                "confidence": 0.0,
                "description": response_text,
                "details": {"parse_error": str(e)}
            }
    
    async def analyze_video_clip(
        self,
        video_gcs_uri: str,
        task: MonitoringTask,
        camera_id: str,
        camera_location: str = "Unknown"
    ) -> AnalysisResult:
        """
        Analyze a video clip directly using Gemini's video understanding.
        
        Args:
            video_gcs_uri: GCS URI of the video clip
            task: The monitoring task
            camera_id: Camera identifier
            camera_location: Physical location
            
        Returns:
            AnalysisResult with detection status
        """
        self.logger.info(
            "Analyzing video clip",
            camera_id=camera_id,
            task_id=task.task_id,
            video_uri=video_gcs_uri
        )
        
        try:
            # Create video part from GCS URI
            video_part = Part.from_uri(video_gcs_uri, mime_type="video/mp4")
            
            analysis_prompt = f"""
{self.system_prompt}

MONITORING TASK: {task.name}
TASK DESCRIPTION: {task.description}
CAMERA LOCATION: {camera_location}

SPECIFIC DETECTION CRITERIA:
{task.prompt}

Analyze this video clip and determine if the specified event is occurring.
Provide your analysis in JSON format.
"""
            
            content_parts = [
                Part.from_text(analysis_prompt),
                video_part
            ]
            
            generation_config = GenerationConfig(
                temperature=0.2,
                top_p=0.8,
                max_output_tokens=1024,
            )
            
            response = await asyncio.to_thread(
                self.model.generate_content,
                content_parts,
                generation_config=generation_config
            )
            
            result_data = self._parse_response(response.text)
            
            return AnalysisResult(
                camera_id=camera_id,
                task_id=task.task_id,
                timestamp=datetime.utcnow(),
                event_detected=result_data.get("event_detected", False),
                confidence=result_data.get("confidence", 0.0),
                description=result_data.get("description", ""),
                details=result_data.get("details", {}),
                video_clip_url=video_gcs_uri,
                raw_response=response.text
            )
            
        except Exception as e:
            self.logger.error(
                "Error analyzing video clip",
                camera_id=camera_id,
                error=str(e)
            )
            
            return AnalysisResult(
                camera_id=camera_id,
                task_id=task.task_id,
                event_detected=False,
                description=f"Video analysis error: {str(e)}"
            )


class TaskPromptBuilder:
    """Helper class to build effective monitoring prompts."""
    
    # Pre-built prompt templates for common scenarios
    TEMPLATES = {
        "queue_monitoring": """
Monitor for queue/line formation. Detect if:
- More than {threshold} people are waiting in a queue or line
- The queue has been present for longer than {duration_minutes} minutes
- People appear to be waiting or standing in line formation

Look for: grouped people, organized lines, waiting behavior, queue barriers.
""",
        
        "after_hours_access": """
Monitor for unauthorized access during restricted hours.
Current monitoring period: {start_time} to {end_time}
Detect if:
- Any person enters or is present in the monitored area
- Doors are opened or accessed
- Movement is detected in restricted zones

This is a high-security area - any human presence should be flagged.
""",
        
        "crowd_density": """
Monitor crowd density levels. Alert if:
- The number of people exceeds {max_people}
- The crowd density appears unsafe
- There is potential for overcrowding

Consider: Available space, exit accessibility, crowd movement patterns.
""",
        
        "safety_hazard": """
Monitor for safety hazards including:
- Slips, trips, or falls
- Objects blocking emergency exits or pathways
- Unsafe behavior or activities
- Spills or wet floors
- Obstacles in walking areas

Flag any safety concern that could lead to injury.
""",
        
        "suspicious_activity": """
Monitor for suspicious or concerning activity:
- Loitering in the area for extended periods
- Unusual behavior patterns
- Attempts to access restricted areas
- Unattended packages or bags
- Aggressive or threatening behavior

Use professional judgment - avoid profiling based on appearance.
""",
        
        "vehicle_monitoring": """
Monitor vehicle activity:
- Detect vehicles entering or exiting
- Flag vehicles parked in no-parking zones
- Monitor for vehicles blocking access
- Track vehicle presence duration (flag if over {max_duration_minutes} minutes)

Vehicle types to monitor: {vehicle_types}
""",

        "emergency_detection": """
Monitor for emergency situations:
- Fire or smoke detection
- Medical emergencies (person collapsed, distress signals)
- Violence or physical altercations
- Panic or evacuation behavior
- Property damage in progress

This requires IMMEDIATE alerting - high confidence threshold: 0.7
"""
    }
    
    @classmethod
    def build_prompt(cls, template_name: str, **kwargs) -> str:
        """Build a monitoring prompt from a template."""
        if template_name not in cls.TEMPLATES:
            raise ValueError(f"Unknown template: {template_name}")
        
        template = cls.TEMPLATES[template_name]
        return template.format(**kwargs)
    
    @classmethod
    def get_available_templates(cls) -> List[str]:
        """Get list of available prompt templates."""
        return list(cls.TEMPLATES.keys())
