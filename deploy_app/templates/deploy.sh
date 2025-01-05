#!/bin/bash

# Exit on any error
set -e

# Configuration
PROJECT_ID="modassembly"  # Replace with your GCP project ID
REGION="us-central1"  # Changed to US Central (Iowa)
SERVICE_NAME=$1  # Use first argument
INSTANCE_CONNECTION_NAME="modassembly:us-central1:modassembly-sandbox"

# Create database if it doesn't exist
echo "🗄️ Creating database if it doesn't exist..."
if ! gcloud sql databases list \
    --instance=modassembly-sandbox \
    --project=$PROJECT_ID \
    | grep -q "^$SERVICE_NAME "; then
  gcloud sql databases create $SERVICE_NAME \
    --instance=modassembly-sandbox \
    --project=$PROJECT_ID
fi

# Build the Docker image with platform specification
echo "🏗️ Building Docker image..."
docker build --platform linux/amd64 -t gcr.io/$PROJECT_ID/$SERVICE_NAME .

# Push the image to Google Container Registry
echo "⬆️ Pushing image to Container Registry..."
docker push gcr.io/$PROJECT_ID/$SERVICE_NAME

# Deploy to Cloud Run
echo "🚀 Deploying to Cloud Run..."
gcloud run deploy $SERVICE_NAME \
  --image gcr.io/$PROJECT_ID/$SERVICE_NAME \
  --platform managed \
  --region $REGION \
  --project $PROJECT_ID \
  --allow-unauthenticated \
  --port 8000 \
  --add-cloudsql-instances $INSTANCE_CONNECTION_NAME \
  --set-env-vars "DB_URL=postgresql://postgres:postgres@localhost/$SERVICE_NAME?host=/cloudsql/$INSTANCE_CONNECTION_NAME"

echo "✅ Deployment complete!"

# Get and display the Cloud Run URL in specific format
gcloud run services describe $SERVICE_NAME \
  --platform managed \
  --region $REGION \
  --project $PROJECT_ID \
  --format='value(status.url)'
