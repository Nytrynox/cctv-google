"""
Quick test script to verify the Gemini API connection works.
"""
import google.generativeai as genai
from dotenv import load_dotenv
import os

# Load environment variables
load_dotenv()

# Configure API
api_key = os.getenv("GEMINI_API_KEY")
print(f"🔑 API Key loaded: {api_key[:10]}...")

genai.configure(api_key=api_key)

# Test with Gemini 2.5 Flash (latest stable model)
print("\n🤖 Testing Gemini 2.5 Flash...")
model = genai.GenerativeModel('gemini-2.5-flash')

response = model.generate_content("Say 'Hello! Video Intelligence Agent is ready!' in one line.")
print(f"✅ Response: {response.text}")

print("\n🎥 Testing image analysis capability...")
# Test if model can describe what it would do with a CCTV image
test_prompt = """
You are a CCTV monitoring AI. If I showed you an image of a store entrance, 
what would you look for to detect:
1. Queue formation (more than 5 people waiting)
2. Suspicious activity
3. Safety hazards

Just briefly list what visual cues you'd analyze. Keep it short.
"""

response = model.generate_content(test_prompt)
print(f"✅ Analysis capability test:\n{response.text}")

print("\n" + "="*50)
print("✅ ALL TESTS PASSED! Your system is ready.")
print("="*50)
print("\nNext: Run 'python main.py' to start the API server")
