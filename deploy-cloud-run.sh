#!/bin/bash
# Deploy Video Intelligence Agent to Google Cloud Run

set -e

# Configuration
PROJECT_ID="${GOOGLE_CLOUD_PROJECT:-your-project-id}"
REGION="${GOOGLE_CLOUD_REGION:-us-central1}"
SERVICE_NAME="video-intelligence-agent"
IMAGE_NAME="gcr.io/${PROJECT_ID}/${SERVICE_NAME}"

echo "🚀 Deploying Video Intelligence Agent to Cloud Run"
echo "Project: ${PROJECT_ID}"
echo "Region: ${REGION}"
echo ""

# Check if gcloud is installed
if ! command -v gcloud &> /dev/null; then
    echo "❌ gcloud CLI is not installed. Please install it first."
    exit 1
fi

# Authenticate (if not already)
echo "📝 Checking authentication..."
gcloud auth print-access-token > /dev/null 2>&1 || gcloud auth login

# Set project
gcloud config set project ${PROJECT_ID}

# Enable required APIs
echo "🔧 Enabling required APIs..."
gcloud services enable \
    cloudbuild.googleapis.com \
    run.googleapis.com \
    storage.googleapis.com \
    aiplatform.googleapis.com \
    --quiet

# Create Cloud Storage bucket for video feeds (if not exists)
BUCKET_NAME="${PROJECT_ID}-cctv-feeds"
if ! gsutil ls gs://${BUCKET_NAME} > /dev/null 2>&1; then
    echo "📦 Creating Cloud Storage bucket..."
    gsutil mb -l ${REGION} gs://${BUCKET_NAME}
    gsutil uniformbucketlevelaccess set on gs://${BUCKET_NAME}
fi

# Build and push Docker image
echo "🔨 Building Docker image..."
gcloud builds submit --tag ${IMAGE_NAME} .

# Deploy to Cloud Run
echo "☁️ Deploying to Cloud Run..."
gcloud run deploy ${SERVICE_NAME} \
    --image ${IMAGE_NAME} \
    --platform managed \
    --region ${REGION} \
    --allow-unauthenticated \
    --memory 2Gi \
    --cpu 2 \
    --min-instances 1 \
    --max-instances 10 \
    --set-env-vars "GOOGLE_CLOUD_PROJECT=${PROJECT_ID}" \
    --set-env-vars "GOOGLE_CLOUD_REGION=${REGION}" \
    --set-env-vars "GCS_BUCKET_NAME=${BUCKET_NAME}" \
    --set-env-vars "VERTEX_AI_MODEL=gemini-1.5-pro-vision" \
    --set-env-vars "VERTEX_AI_LOCATION=${REGION}" \
    --set-env-vars "VIDEO_ANALYSIS_INTERVAL_SECONDS=30" \
    --set-env-vars "LOG_LEVEL=INFO"

# Get the service URL
SERVICE_URL=$(gcloud run services describe ${SERVICE_NAME} --region ${REGION} --format 'value(status.url)')

echo ""
echo "✅ Deployment complete!"
echo ""
echo "🌐 Service URL: ${SERVICE_URL}"
echo ""
echo "📋 Next steps:"
echo "  1. Set up Firebase for mobile alerts: https://console.firebase.google.com"
echo "  2. Configure your CCTV cameras to stream to Cloud Storage"
echo "  3. Use the API to register cameras and create monitoring tasks"
echo ""
echo "🔗 API Documentation: ${SERVICE_URL}/docs"
