"""
Example usage of the Video Intelligence Agent system.
Demonstrates how to set up cameras, create monitoring tasks, and handle alerts.
"""
import asyncio
from datetime import datetime

from src import (
    VideoStreamManager,
    VideoIntelligenceAgent,
    AlertManager,
    MonitoringEngine,
    TaskTemplates,
    Camera,
    AlertSeverity
)


async def main():
    """Main example demonstrating the video intelligence system."""
    
    print("🎥 Video Intelligence Agent - Example Usage")
    print("=" * 50)
    
    # Initialize components
    stream_manager = VideoStreamManager()
    ai_agent = VideoIntelligenceAgent()
    alert_manager = AlertManager()
    
    # Create monitoring engine
    engine = MonitoringEngine(
        stream_manager=stream_manager,
        ai_agent=ai_agent,
        alert_manager=alert_manager
    )
    
    # Set up alert callback
    def on_alert(alert):
        print(f"\n🚨 ALERT: {alert.title}")
        print(f"   Severity: {alert.severity.value}")
        print(f"   Location: {alert.location}")
        print(f"   Description: {alert.description}")
        if alert.video_clip_url:
            print(f"   Video: {alert.video_clip_url}")
    
    engine.on_alert_callback = on_alert
    
    # Start the engine
    await engine.start()
    
    # Example 1: Register a camera
    print("\n📹 Registering camera...")
    entrance_camera = Camera(
        camera_id="cam-entrance-01",
        name="Store Entrance Camera",
        location="Main Entrance, Building A",
        stream_url="rtsp://192.168.1.100:554/stream1",  # Example RTSP URL
        tags=["entrance", "high-traffic", "customer-facing"]
    )
    
    # Note: In production, uncomment this to actually connect
    # await engine.register_camera(entrance_camera)
    print(f"   Camera registered: {entrance_camera.name}")
    
    # Example 2: Create monitoring tasks using templates
    print("\n📋 Creating monitoring tasks...")
    
    # Queue monitoring
    queue_task = TaskTemplates.queue_monitoring(
        name="Customer Queue Alert",
        camera_ids=["cam-entrance-01"],
        max_queue_size=10,
        wait_time_minutes=5,
        notify_users=["device_token_1", "device_token_2"]
    )
    print(f"   Created task: {queue_task.name}")
    print(f"   Prompt: {queue_task.prompt[:100]}...")
    
    # After-hours monitoring
    security_task = TaskTemplates.after_hours_monitoring(
        name="Night Security Watch",
        camera_ids=["cam-entrance-01"],
        start_hour=22,
        end_hour=6,
        notify_users=["security_team_token"]
    )
    print(f"   Created task: {security_task.name}")
    
    # Safety monitoring
    safety_task = TaskTemplates.safety_monitoring(
        name="Workplace Safety Monitor",
        camera_ids=["cam-entrance-01"],
        notify_users=["safety_officer_token"]
    )
    print(f"   Created task: {safety_task.name}")
    
    # Example 3: Create a custom task
    print("\n🎯 Creating custom monitoring task...")
    custom_task = TaskTemplates.custom_task(
        name="VIP Customer Detection",
        description="Detect when VIP customers arrive at the entrance",
        camera_ids=["cam-entrance-01"],
        prompt="""
Monitor for VIP customer arrivals. Alert when you observe:
- Customers arriving with luxury vehicles
- Groups of well-dressed individuals
- People who appear to be waiting for personal assistance
- Anyone displaying VIP membership cards or badges

This is for proactive customer service, not security.
Be respectful and professional in observations.
        """,
        severity=AlertSeverity.LOW,
        notify_users=["concierge_team_token"],
        cooldown_minutes=15
    )
    print(f"   Created task: {custom_task.name}")
    
    # Example 4: API endpoint examples
    print("\n🌐 Example API Calls:")
    print("""
    # Register a camera
    POST /cameras
    {
        "name": "Store Entrance",
        "location": "Main entrance, Building A", 
        "stream_url": "rtsp://camera-ip:554/stream",
        "tags": ["entrance", "high-traffic"]
    }
    
    # Create monitoring task
    POST /tasks
    {
        "name": "Queue Monitoring",
        "description": "Alert when queue exceeds 10 people",
        "camera_ids": ["cam-entrance-01"],
        "prompt": "Monitor for queue > 10 people",
        "severity": "medium",
        "notify_users": ["device_token"],
        "cooldown_minutes": 10
    }
    
    # Use a template
    POST /task-templates/queue_monitoring?name=Queue&camera_ids=cam1&max_queue_size=10
    
    # Manual analysis
    POST /analyze/{camera_id}/{task_id}
    
    # View alerts
    GET /alerts?severity=high
    
    # Acknowledge alert
    PUT /alerts/{alert_id}/status
    {"status": "acknowledged", "user_id": "operator1"}
    """)
    
    # Example 5: Common monitoring scenarios
    print("\n📊 Common Monitoring Scenarios:")
    
    scenarios = [
        {
            "scenario": "Retail - Queue Management",
            "prompt": "Alert if checkout line exceeds 8 customers. Monitor all register areas."
        },
        {
            "scenario": "Warehouse - After Hours Security",
            "prompt": "Flag any human presence between 10PM-6AM. This is a restricted area."
        },
        {
            "scenario": "Office - Meeting Room Usage",
            "prompt": "Track meeting room occupancy. Alert if room is used beyond scheduled time."
        },
        {
            "scenario": "Parking - Unauthorized Access",
            "prompt": "Monitor for vehicles without parking permits in reserved spaces."
        },
        {
            "scenario": "Loading Dock - Safety",
            "prompt": "Alert if forklift operates without required safety lights or horn usage."
        }
    ]
    
    for s in scenarios:
        print(f"\n   📌 {s['scenario']}")
        print(f"      Prompt: {s['prompt']}")
    
    # Cleanup
    await engine.stop()
    
    print("\n" + "=" * 50)
    print("✅ Example complete!")
    print("\nTo run the full system:")
    print("  1. Configure .env with your Google Cloud credentials")
    print("  2. Run: python main.py")
    print("  3. Access API at: http://localhost:8080/docs")


if __name__ == "__main__":
    asyncio.run(main())
