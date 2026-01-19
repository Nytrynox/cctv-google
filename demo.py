"""
Simple Demo - Test Video Intelligence Agent with images or videos
Run: python demo.py
"""
import google.generativeai as genai
from dotenv import load_dotenv
import os
import sys
from pathlib import Path

# Load environment variables
load_dotenv()

# Configure API
api_key = os.getenv("GEMINI_API_KEY")
genai.configure(api_key=api_key)

# Use Gemini 2.5 Flash
model = genai.GenerativeModel('gemini-2.5-flash')


def analyze_image(image_path: str, prompt: str):
    """Analyze an image with a custom prompt."""
    print(f"\n📸 Analyzing image: {image_path}")
    print(f"📝 Task: {prompt[:100]}...")
    
    # Upload the image
    image_file = genai.upload_file(path=image_path)
    
    # Full analysis prompt
    full_prompt = f"""You are a CCTV security monitoring AI agent.

MONITORING TASK:
{prompt}

Analyze this image and respond with JSON:
{{
    "event_detected": true/false,
    "confidence": 0.0-1.0,
    "description": "What you observe",
    "people_count": number,
    "details": {{}}
}}
"""
    
    response = model.generate_content([image_file, full_prompt])
    
    print("\n🤖 AI Analysis Result:")
    print(response.text)
    
    # Cleanup
    genai.delete_file(image_file.name)
    
    return response.text


def analyze_video(video_path: str, prompt: str):
    """Analyze a video file."""
    print(f"\n🎬 Analyzing video: {video_path}")
    print(f"📝 Task: {prompt[:100]}...")
    
    # Upload the video
    print("⏳ Uploading video...")
    video_file = genai.upload_file(path=video_path)
    
    # Wait for processing
    print("⏳ Processing video...")
    import time
    while video_file.state.name == "PROCESSING":
        time.sleep(2)
        video_file = genai.get_file(video_file.name)
    
    if video_file.state.name == "FAILED":
        print("❌ Video processing failed")
        return None
    
    print("✅ Video ready for analysis")
    
    # Full analysis prompt
    full_prompt = f"""You are a CCTV security monitoring AI agent.

MONITORING TASK:
{prompt}

Analyze this video and respond with JSON:
{{
    "event_detected": true/false,
    "confidence": 0.0-1.0,
    "description": "What you observe throughout the video",
    "key_moments": ["list of important moments with timestamps"],
    "people_count_max": number,
    "details": {{}}
}}
"""
    
    response = model.generate_content([video_file, full_prompt])
    
    print("\n🤖 AI Analysis Result:")
    print(response.text)
    
    # Cleanup
    genai.delete_file(video_file.name)
    
    return response.text


def interactive_mode():
    """Interactive demo mode."""
    print("\n" + "="*60)
    print("🎥 VIDEO INTELLIGENCE AGENT - Interactive Demo")
    print("="*60)
    
    # Pre-built monitoring tasks
    tasks = {
        "1": ("Queue Detection", "Alert if more than 5 people are waiting in line. Count all people who appear to be in a queue formation."),
        "2": ("Crowd Density", "Estimate the number of people visible. Alert if the area appears overcrowded or unsafe."),
        "3": ("Safety Hazards", "Look for safety hazards: blocked exits, spills, fallen objects, unsafe behavior."),
        "4": ("Suspicious Activity", "Monitor for suspicious behavior: loitering, unusual movements, unauthorized access attempts."),
        "5": ("General Analysis", "Describe everything you see in detail. Count people, identify objects, describe activities."),
    }
    
    while True:
        print("\n📋 Available Monitoring Tasks:")
        for key, (name, _) in tasks.items():
            print(f"  {key}. {name}")
        print("  6. Custom prompt")
        print("  q. Quit")
        
        choice = input("\nSelect task (1-6, q): ").strip()
        
        if choice.lower() == 'q':
            print("👋 Goodbye!")
            break
        
        if choice in tasks:
            task_name, prompt = tasks[choice]
        elif choice == "6":
            prompt = input("Enter your custom prompt: ").strip()
            task_name = "Custom"
        else:
            print("❌ Invalid choice")
            continue
        
        # Get file path
        file_path = input("Enter image/video path (or drag & drop file): ").strip().strip("'\"")
        
        if not Path(file_path).exists():
            print(f"❌ File not found: {file_path}")
            continue
        
        # Determine file type
        ext = Path(file_path).suffix.lower()
        
        try:
            if ext in ['.jpg', '.jpeg', '.png', '.gif', '.webp']:
                analyze_image(file_path, prompt)
            elif ext in ['.mp4', '.mov', '.avi', '.mkv', '.webm']:
                analyze_video(file_path, prompt)
            else:
                print(f"❌ Unsupported file type: {ext}")
        except Exception as e:
            print(f"❌ Error: {e}")


def quick_test():
    """Quick test without files - just test the API."""
    print("\n🧪 Quick API Test (no files needed)")
    
    prompt = """Imagine you're looking at a CCTV image of a busy store entrance. 
    There are 8 people waiting in line, and one person appears to be dropping a bag.
    Respond as if you actually see this in JSON format:
    {
        "event_detected": true/false,
        "confidence": 0.0-1.0,
        "description": "What you observe",
        "people_count": number,
        "alerts": ["list of concerns"]
    }"""
    
    response = model.generate_content(prompt)
    print("\n🤖 AI Response:")
    print(response.text)


if __name__ == "__main__":
    if len(sys.argv) > 1:
        # Command line mode
        if sys.argv[1] == "--test":
            quick_test()
        elif sys.argv[1] == "--image" and len(sys.argv) >= 3:
            image_path = sys.argv[2]
            prompt = sys.argv[3] if len(sys.argv) > 3 else "Describe what you see and count any people."
            analyze_image(image_path, prompt)
        elif sys.argv[1] == "--video" and len(sys.argv) >= 3:
            video_path = sys.argv[2]
            prompt = sys.argv[3] if len(sys.argv) > 3 else "Describe what happens in this video."
            analyze_video(video_path, prompt)
        else:
            print("Usage:")
            print("  python demo.py           # Interactive mode")
            print("  python demo.py --test    # Quick API test")
            print("  python demo.py --image <path> [prompt]")
            print("  python demo.py --video <path> [prompt]")
    else:
        interactive_mode()
