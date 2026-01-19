"""
Video Intelligence Agent - Uses Google AI Studio (Gemini API) for video analysis.
This is the FREE tier version that doesn't require billing.
"""
import asyncio
import json
import base64
from datetime import datetime
from typing import List, Optional, Dict, Any
from pathlib import Path
import structlog
import google.generativeai as genai

from .config import settings
from .models import (
    MonitoringTask, AnalysisResult, VideoFrame, 
    AlertSeverity
)

logger = structlog.get_logger(__name__)


class VideoIntelligenceAgent:
    """
    AI Agent that uses Gemini multimodal model to analyze video feeds.
    Uses Google AI Studio API (free tier) instead of Vertex AI.
    """
    
    def __init__(self):
        # Initialize Google AI Studio
        genai.configure(api_key=settings.gemini_api_key)
        
        # Use latest stable model (gemini-2.5-flash as of Jan 2026)
        self.model = genai.GenerativeModel('gemini-2.5-flash')
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
    
    def _load_image_as_base64(self, image_path: str) -> Optional[Dict]:
        """Load an image file and convert to base64 for Gemini."""
        try:
            with open(image_path, "rb") as f:
                image_data = f.read()
            
            return {
                "mime_type": "image/jpeg",
                "data": base64.b64encode(image_data).decode("utf-8")
            }
        except Exception as e:
            self.logger.error("Error loading image", path=image_path, error=str(e))
            return None
    
    def _load_image_from_bytes(self, image_bytes: bytes) -> Dict:
        """Convert image bytes to base64 for Gemini."""
        return {
            "mime_type": "image/jpeg",
            "data": base64.b64encode(image_bytes).decode("utf-8")
        }
    
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
                camera_id="unknown",
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
{self.system_prompt}

MONITORING TASK: {task.name}
TASK DESCRIPTION: {task.description}
CAMERA LOCATION: {camera_location}

SPECIFIC DETECTION CRITERIA:
{task.prompt}

Analyze the following {len(frames)} video frames captured over the recent period.
Determine if the specified event is occurring and provide your analysis in JSON format.
"""
            
            # Build content parts with images
            content_parts = [analysis_prompt]
            
            for i, frame in enumerate(frames):
                if frame.local_path and Path(frame.local_path).exists():
                    image_data = self._load_image_as_base64(frame.local_path)
                    if image_data:
                        content_parts.append({
                            "inline_data": image_data
                        })
                        content_parts.append(f"[Frame {i+1} - Timestamp: {frame.timestamp.isoformat()}]")
            
            # Call Gemini API
            response = await asyncio.to_thread(
                self.model.generate_content,
                content_parts
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
                frame_urls=[f.gcs_uri for f in frames if f.gcs_uri],
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
    
    async def analyze_image_directly(
        self,
        image_path: str,
        prompt: str
    ) -> Dict[str, Any]:
        """
        Analyze a single image with a custom prompt.
        Useful for testing and one-off analysis.
        """
        try:
            image_data = self._load_image_as_base64(image_path)
            if not image_data:
                return {"error": "Failed to load image"}
            
            content = [
                prompt,
                {"inline_data": image_data}
            ]
            
            response = await asyncio.to_thread(
                self.model.generate_content,
                content
            )
            
            return self._parse_response(response.text)
            
        except Exception as e:
            return {"error": str(e)}
    
    async def analyze_video_file(
        self,
        video_path: str,
        task: MonitoringTask,
        camera_id: str = "test",
        camera_location: str = "Test Location"
    ) -> AnalysisResult:
        """
        Analyze a video file directly.
        Gemini 1.5 supports video input.
        """
        self.logger.info("Analyzing video file", path=video_path)
        
        try:
            # Upload video to Gemini
            video_file = genai.upload_file(path=video_path)
            
            # Wait for processing
            while video_file.state.name == "PROCESSING":
                await asyncio.sleep(2)
                video_file = genai.get_file(video_file.name)
            
            if video_file.state.name == "FAILED":
                return AnalysisResult(
                    camera_id=camera_id,
                    task_id=task.task_id,
                    event_detected=False,
                    description="Video processing failed"
                )
            
            analysis_prompt = f"""
{self.system_prompt}

MONITORING TASK: {task.name}
TASK DESCRIPTION: {task.description}
CAMERA LOCATION: {camera_location}

SPECIFIC DETECTION CRITERIA:
{task.prompt}

Analyze this video and determine if the specified event is occurring.
Provide your analysis in JSON format.
"""
            
            response = await asyncio.to_thread(
                self.model.generate_content,
                [video_file, analysis_prompt]
            )
            
            result_data = self._parse_response(response.text)
            
            # Cleanup uploaded file
            genai.delete_file(video_file.name)
            
            return AnalysisResult(
                camera_id=camera_id,
                task_id=task.task_id,
                timestamp=datetime.utcnow(),
                event_detected=result_data.get("event_detected", False),
                confidence=result_data.get("confidence", 0.0),
                description=result_data.get("description", ""),
                details=result_data.get("details", {}),
                video_clip_url=video_path,
                raw_response=response.text
            )
            
        except Exception as e:
            self.logger.error("Error analyzing video", error=str(e))
            return AnalysisResult(
                camera_id=camera_id,
                task_id=task.task_id,
                event_detected=False,
                description=f"Video analysis error: {str(e)}"
            )
    
    def _parse_response(self, response_text: str) -> Dict[str, Any]:
        """Parse JSON from the AI response."""
        try:
            import re
            
            # Look for JSON block
            json_match = re.search(r'\{[\s\S]*\}', response_text)
            if json_match:
                return json.loads(json_match.group())
            
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


class TaskPromptBuilder:
    """Helper class to build effective monitoring prompts."""
    
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
