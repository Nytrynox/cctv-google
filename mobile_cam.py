"""
Mobile Camera CCTV Monitor
Connects to IP Webcam at 192.168.1.9:8080
Run: python mobile_cam.py
"""
from google import genai
from google.genai import types
from dotenv import load_dotenv
import os
import time
import urllib.request
import tempfile
from datetime import datetime

# Load environment variables
load_dotenv()

# Configure client
api_key = os.getenv("GEMINI_API_KEY")
client = genai.Client(api_key=api_key)

MODEL = "gemini-2.5-flash"

# Camera settings
CAMERA_IP = "192.168.1.9"
CAMERA_PORT = "8080"

# Common IP Webcam endpoints
SNAPSHOT_URL = f"http://{CAMERA_IP}:{CAMERA_PORT}/shot.jpg"
VIDEO_URL = f"http://{CAMERA_IP}:{CAMERA_PORT}/video"
PHOTO_URL = f"http://{CAMERA_IP}:{CAMERA_PORT}/photo.jpg"


def capture_frame():
    """Capture a single frame from the camera."""
    urls_to_try = [
        f"http://{CAMERA_IP}:{CAMERA_PORT}/shot.jpg",      # IP Webcam
        f"http://{CAMERA_IP}:{CAMERA_PORT}/photo.jpg",     # IP Webcam alt
        f"http://{CAMERA_IP}:{CAMERA_PORT}/snapshot.jpg",  # Some cameras
        f"http://{CAMERA_IP}:{CAMERA_PORT}/image.jpg",     # Generic
        f"http://{CAMERA_IP}:{CAMERA_PORT}/cam.jpg",       # Generic
        f"http://{CAMERA_IP}:{CAMERA_PORT}/?action=snapshot",  # mjpg-streamer
    ]
    
    for url in urls_to_try:
        try:
            print(f"📷 Trying: {url}")
            response = urllib.request.urlopen(url, timeout=5)
            image_data = response.read()
            if len(image_data) > 1000:  # Valid image should be > 1KB
                print(f"✅ Connected to: {url}")
                return image_data
        except Exception as e:
            continue
    
    return None


def analyze_frame(image_data: bytes, task: str):
    """Analyze a camera frame with AI."""
    
    prompt = f"""You are a CCTV security monitoring AI agent analyzing a LIVE camera feed.
Current Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

MONITORING TASK: {task}

Analyze this frame and respond with JSON:
{{
    "alert": true/false (true if something needs attention),
    "alert_level": "none" | "info" | "warning" | "critical",
    "description": "Brief description of what you see",
    "people_count": number,
    "objects_detected": ["list", "of", "objects"],
    "activity": "What's happening",
    "concerns": ["any concerns or alerts"]
}}

Be concise but thorough."""

    try:
        response = client.models.generate_content(
            model=MODEL,
            contents=[
                types.Part.from_bytes(data=image_data, mime_type="image/jpeg"),
                prompt
            ]
        )
        return response.text
    except Exception as e:
        return f"Error: {e}"


def continuous_monitor(interval: int = 10, task: str = "General security monitoring"):
    """Continuously monitor the camera feed."""
    print("\n" + "="*60)
    print("🎥 LIVE CCTV MONITORING STARTED")
    print("="*60)
    print(f"📍 Camera: http://{CAMERA_IP}:{CAMERA_PORT}")
    print(f"⏱️  Interval: {interval} seconds")
    print(f"📋 Task: {task}")
    print("Press Ctrl+C to stop\n")
    
    frame_count = 0
    alert_count = 0
    
    try:
        while True:
            frame_count += 1
            timestamp = datetime.now().strftime('%H:%M:%S')
            print(f"\n[{timestamp}] Frame #{frame_count}")
            print("-" * 40)
            
            # Capture frame
            image_data = capture_frame()
            
            if image_data:
                print(f"📸 Captured {len(image_data):,} bytes")
                
                # Analyze with AI
                print("🤖 Analyzing...")
                result = analyze_frame(image_data, task)
                print(result)
                
                # Check for alerts
                if '"alert": true' in result.lower() or '"alert":true' in result.lower():
                    alert_count += 1
                    print(f"\n🚨 ALERT #{alert_count} DETECTED!")
                    
                    # Save alert frame
                    alert_file = f"alert_{frame_count}_{timestamp.replace(':', '-')}.jpg"
                    with open(alert_file, 'wb') as f:
                        f.write(image_data)
                    print(f"💾 Saved: {alert_file}")
            else:
                print("❌ Could not capture frame")
            
            # Wait for next interval
            print(f"\n⏳ Next check in {interval} seconds...")
            time.sleep(interval)
            
    except KeyboardInterrupt:
        print(f"\n\n{'='*60}")
        print("📊 MONITORING SESSION SUMMARY")
        print(f"{'='*60}")
        print(f"Total frames analyzed: {frame_count}")
        print(f"Alerts detected: {alert_count}")
        print("👋 Monitoring stopped.")


def single_capture(task: str = "Describe everything you see"):
    """Capture and analyze a single frame."""
    print(f"\n📷 Capturing single frame from http://{CAMERA_IP}:{CAMERA_PORT}")
    
    image_data = capture_frame()
    
    if image_data:
        print(f"✅ Captured {len(image_data):,} bytes")
        
        # Save the frame
        filename = f"capture_{datetime.now().strftime('%H%M%S')}.jpg"
        with open(filename, 'wb') as f:
            f.write(image_data)
        print(f"💾 Saved: {filename}")
        
        # Analyze
        print("\n🤖 Analyzing with AI...")
        result = analyze_frame(image_data, task)
        print("\n" + "="*50)
        print("AI ANALYSIS RESULT:")
        print("="*50)
        print(result)
    else:
        print("❌ Could not connect to camera")
        print("\n💡 Troubleshooting:")
        print("1. Make sure your phone and computer are on the same WiFi")
        print("2. Check IP Webcam app is running and streaming")
        print("3. Try opening in browser: http://192.168.1.9:8080")


def interactive_menu():
    """Interactive menu for camera monitoring."""
    print("\n" + "="*60)
    print("🎥 MOBILE CAMERA MONITOR")
    print("="*60)
    print(f"Camera: http://{CAMERA_IP}:{CAMERA_PORT}")
    
    tasks = {
        "1": ("Security Watch", "Monitor for intruders, suspicious activity, or unauthorized access"),
        "2": ("People Counting", "Count the number of people visible and track movement"),
        "3": ("Safety Monitor", "Look for safety hazards, accidents, or dangerous situations"),
        "4": ("Activity Log", "Describe all activities and movements in detail"),
        "5": ("Custom Task", None),
    }
    
    while True:
        print("\n📋 Menu:")
        print("  1. 📸 Single Capture & Analyze")
        print("  2. 🔄 Continuous Monitoring (every 10s)")
        print("  3. 🔄 Fast Monitoring (every 5s)")
        print("  4. 🔗 Test Camera Connection")
        print("  q. Quit")
        
        choice = input("\nSelect option: ").strip().lower()
        
        if choice == 'q':
            print("👋 Goodbye!")
            break
        elif choice == '1':
            print("\n📋 Select monitoring task:")
            for key, (name, _) in tasks.items():
                print(f"  {key}. {name}")
            
            task_choice = input("Task (1-5): ").strip()
            if task_choice in tasks:
                if task_choice == "5":
                    task = input("Enter custom task: ").strip()
                else:
                    _, task = tasks[task_choice]
            else:
                task = "Describe everything you see in detail"
            
            single_capture(task)
            
        elif choice == '2':
            task = input("Monitoring task (or Enter for general): ").strip()
            task = task or "General security monitoring - alert on any unusual activity"
            continuous_monitor(interval=10, task=task)
            
        elif choice == '3':
            task = input("Monitoring task (or Enter for general): ").strip()
            task = task or "General security monitoring - alert on any unusual activity"
            continuous_monitor(interval=5, task=task)
            
        elif choice == '4':
            print("\n🔗 Testing camera connection...")
            image_data = capture_frame()
            if image_data:
                print(f"✅ SUCCESS! Camera is working ({len(image_data):,} bytes)")
            else:
                print("❌ Could not connect to camera")
                print("\n💡 Make sure:")
                print("   - IP Webcam app is running on your phone")
                print("   - 'Start server' is pressed in the app")
                print("   - Phone and computer are on same WiFi network")
                print(f"   - Try opening http://{CAMERA_IP}:{CAMERA_PORT} in browser")


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1:
        if sys.argv[1] == "--single":
            single_capture()
        elif sys.argv[1] == "--monitor":
            interval = int(sys.argv[2]) if len(sys.argv) > 2 else 10
            continuous_monitor(interval=interval)
        elif sys.argv[1] == "--test":
            print("Testing camera connection...")
            if capture_frame():
                print("✅ Camera connected!")
            else:
                print("❌ Could not connect")
    else:
        interactive_menu()
