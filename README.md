# Video Intelligence Agent for CCTV Monitoring

A comprehensive AI-powered video monitoring system that uses Google Cloud's Vertex AI (Gemini) to analyze CCTV feeds in real-time and send intelligent alerts based on natural language monitoring tasks.

![Architecture](https://storage.googleapis.com/gweb-cloudblog-publish/images/97_l4gsDg2.max-2000x2000.png)

## Features

- **Real-time Video Analysis**: Continuously monitors CCTV feeds using Gemini's multimodal capabilities
- **Natural Language Tasks**: Define monitoring tasks using plain English (e.g., "Alert if queue > 10 people")
- **Smart Alerts**: Mobile push notifications via Firebase Cloud Messaging with video clips
- **Multiple Alert Channels**: Push notifications, Slack, Microsoft Teams, webhooks
- **Pre-built Templates**: Common monitoring scenarios ready to use
- **REST API**: Full API for camera management, task configuration, and alert handling
- **Scalable Architecture**: Designed for hundreds of cameras with Cloud Run deployment

## Architecture

```
┌─────────────────────┐
│   CCTV Cameras      │
│  (RTSP/HTTP feeds)  │
└──────────┬──────────┘
           │
           ▼
┌─────────────────────┐
│  Cloud Storage      │
│  (Video frames)     │
└──────────┬──────────┘
           │
           ▼
┌─────────────────────┐
│  Video Intelligence │
│  Agent (Gemini)     │
│                     │
│  • Frame analysis   │
│  • Event detection  │
│  • NL task matching │
└──────────┬──────────┘
           │
           ▼
┌─────────────────────┐
│  Alert System       │
│                     │
│  • FCM Push         │
│  • Slack/Teams      │
│  • Webhooks         │
└─────────────────────┘
```

## Quick Start

### Prerequisites

- Google Cloud Project with billing enabled
- Python 3.11+
- Docker (optional, for containerized deployment)

### 1. Clone and Setup

```bash
# Clone the repository
cd video-intelligence-agent

# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

### 2. Configure Google Cloud

```bash
# Authenticate with Google Cloud
gcloud auth application-default login

# Set your project
gcloud config set project YOUR_PROJECT_ID

# Enable required APIs
gcloud services enable \
    storage.googleapis.com \
    aiplatform.googleapis.com \
    cloudbuild.googleapis.com \
    run.googleapis.com
```

### 3. Configure Environment

```bash
# Copy example environment file
cp .env.example .env

# Edit .env with your configuration
```

Required configuration:

```env
GOOGLE_CLOUD_PROJECT=your-project-id
GCS_BUCKET_NAME=your-cctv-bucket
VERTEX_AI_MODEL=gemini-1.5-pro-vision
```

### 4. Run Locally

```bash
python main.py
```

The API will be available at `http://localhost:8080`

### 5. Deploy to Cloud Run

```bash
chmod +x deploy-cloud-run.sh
./deploy-cloud-run.sh
```

## API Usage

### Register a Camera

```bash
curl -X POST http://localhost:8080/cameras \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Store Entrance",
    "location": "Main entrance, Building A",
    "stream_url": "rtsp://camera-ip:554/stream",
    "tags": ["entrance", "high-traffic"]
  }'
```

### Create a Monitoring Task

```bash
curl -X POST http://localhost:8080/tasks \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Queue Monitoring",
    "description": "Alert when queue exceeds 10 people",
    "camera_ids": ["camera-uuid-here"],
    "prompt": "Monitor for queue formation. Alert if more than 10 people are waiting in line for over 5 minutes.",
    "severity": "medium",
    "notify_users": ["fcm-device-token"],
    "cooldown_minutes": 10
  }'
```

### Use Pre-built Templates

```bash
# Queue monitoring template
curl -X POST "http://localhost:8080/task-templates/queue_monitoring?name=Store%20Queue&camera_ids=cam1&max_queue_size=10"

# After-hours security
curl -X POST "http://localhost:8080/task-templates/after_hours_monitoring?name=Night%20Security&camera_ids=cam1&start_hour=22&end_hour=6"

# Crowd density
curl -X POST "http://localhost:8080/task-templates/crowd_density_monitoring?name=Event%20Space&camera_ids=cam1&max_people=100"
```

### Run Manual Analysis

```bash
curl -X POST http://localhost:8080/analyze/{camera_id}/{task_id}
```

### View Alerts

```bash
# List all alerts
curl http://localhost:8080/alerts

# Filter by severity
curl "http://localhost:8080/alerts?severity=high"

# Acknowledge an alert
curl -X PUT http://localhost:8080/alerts/{alert_id}/status \
  -H "Content-Type: application/json" \
  -d '{"status": "acknowledged", "user_id": "security-team"}'
```

## Monitoring Task Examples

### 1. Queue Detection
```json
{
  "name": "Customer Queue Alert",
  "prompt": "Monitor the checkout area. Alert if more than 10 customers are waiting in line. Look for people standing in queue formation near the registers.",
  "severity": "medium"
}
```

### 2. After-Hours Access
```json
{
  "name": "Warehouse Security",
  "prompt": "This is a restricted area after business hours (10 PM - 6 AM). Alert if any person enters or is present in the warehouse. Flag any movement or door access.",
  "severity": "high",
  "schedule": "*/5 22-23,0-5 * * *"
}
```

### 3. Safety Monitoring
```json
{
  "name": "Workplace Safety",
  "prompt": "Monitor for safety hazards: slips, trips, falls, spills, blocked exits, unsafe behavior. Any observed injury or dangerous condition should trigger an immediate alert.",
  "severity": "critical"
}
```

### 4. Crowd Management
```json
{
  "name": "Event Capacity",
  "prompt": "Monitor crowd density in the venue. Alert if estimated attendance exceeds 500 people or if emergency exits appear blocked. Watch for signs of overcrowding.",
  "severity": "high"
}
```

### 5. Suspicious Activity
```json
{
  "name": "Security Watch",
  "prompt": "Monitor for suspicious activity: loitering for extended periods, unusual behavior, attempts to access restricted areas, unattended packages. Use professional judgment.",
  "severity": "medium"
}
```

## Firebase Setup (Mobile Alerts)

1. Create a Firebase project at [console.firebase.google.com](https://console.firebase.google.com)

2. Generate a service account key:
   - Go to Project Settings → Service Accounts
   - Click "Generate new private key"
   - Save as `firebase-service-account.json`

3. Set in environment:
   ```env
   FIREBASE_CREDENTIALS_PATH=/path/to/firebase-service-account.json
   FIREBASE_PROJECT_ID=your-firebase-project
   ```

4. In your mobile app, implement FCM to receive alerts

## Webhook Integration

### Slack Integration

```bash
curl -X POST http://localhost:8080/alerts/{alert_id}/send \
  -H "Content-Type: application/json" \
  -d '{
    "webhook_url": "https://hooks.slack.com/services/YOUR/SLACK/WEBHOOK",
    "format_type": "slack"
  }'
```

### Microsoft Teams

```bash
curl -X POST http://localhost:8080/alerts/{alert_id}/send \
  -H "Content-Type: application/json" \
  -d '{
    "webhook_url": "https://outlook.office.com/webhook/YOUR/TEAMS/WEBHOOK",
    "format_type": "teams"
  }'
```

## Project Structure

```
video-intelligence-agent/
├── src/
│   ├── __init__.py          # Package exports
│   ├── config.py             # Configuration management
│   ├── models.py             # Data models (Pydantic)
│   ├── video_handler.py      # Video stream capture & storage
│   ├── video_intelligence.py # Gemini AI analysis engine
│   ├── alert_system.py       # Alert distribution (FCM, webhooks)
│   ├── monitoring_engine.py  # Task scheduling & orchestration
│   └── api.py                # FastAPI REST endpoints
├── main.py                   # Application entry point
├── requirements.txt          # Python dependencies
├── Dockerfile               # Container build
├── docker-compose.yml       # Local development
├── deploy-cloud-run.sh      # Cloud Run deployment
├── .env.example             # Environment template
└── README.md                # This file
```

## Cost Considerations

| Component | Pricing Model |
|-----------|--------------|
| Vertex AI (Gemini) | Per 1K tokens (input/output) |
| Cloud Storage | Per GB stored + operations |
| Cloud Run | Per vCPU-second + memory |
| Firebase Cloud Messaging | Free |

**Cost optimization tips:**
- Adjust `VIDEO_ANALYSIS_INTERVAL_SECONDS` (higher = less frequent analysis)
- Use task scheduling for non-critical monitoring
- Set appropriate cooldown periods to reduce duplicate alerts
- Archive old video clips to cheaper storage classes

## API Documentation

Once running, access the interactive API documentation at:
- Swagger UI: `http://localhost:8080/docs`
- ReDoc: `http://localhost:8080/redoc`

## Troubleshooting

### Camera connection fails
- Verify RTSP URL is accessible from your network
- Check firewall rules allow the connection
- Ensure camera credentials are correct

### No events detected
- Review the monitoring task prompt for clarity
- Check if frames are being captured (view logs)
- Lower confidence threshold if too strict
- Ensure adequate lighting for video quality

### Alerts not received
- Verify FCM tokens are valid
- Check Firebase project configuration
- Test webhook URLs independently
- Review alert cooldown settings

## License

MIT License - See LICENSE file for details.

## Support

For issues and feature requests, please open a GitHub issue.
