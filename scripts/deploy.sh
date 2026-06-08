#!/usr/bin/env bash
# Manual deploy helper for InsurBot to Cloud Run.
# Use this for ad-hoc deployments outside the Cloud Build pipeline.
#
# Usage:
#   ./scripts/deploy.sh <project-id> [region]
#
# Example:
#   ./scripts/deploy.sh my-gcp-project us-central1

set -euo pipefail

PROJECT_ID="${1:?Usage: $0 <project-id> [region]}"
REGION="${2:-us-central1}"
SERVICE_NAME="insurbot-api"
REGISTRY="${REGION}-docker.pkg.dev"
REPO="insurbot"
IMAGE="${REGISTRY}/${PROJECT_ID}/${REPO}/insurbot-api"
TAG=$(git rev-parse --short HEAD)

echo "Building image: ${IMAGE}:${TAG}"
docker build -f deploy/Dockerfile -t "${IMAGE}:${TAG}" -t "${IMAGE}:latest" .

echo "Pushing image to Artifact Registry..."
docker push --all-tags "${IMAGE}"

echo "Deploying to Cloud Run..."
gcloud run deploy "${SERVICE_NAME}" \
  --image="${IMAGE}:${TAG}" \
  --region="${REGION}" \
  --project="${PROJECT_ID}" \
  --platform=managed \
  --no-allow-unauthenticated \
  --service-account="insurbot-sa@${PROJECT_ID}.iam.gserviceaccount.com" \
  --set-env-vars="GCP_PROJECT_ID=${PROJECT_ID},GCP_REGION=${REGION},BQ_DATASET=insurbot,BQ_LOCATION=US,VERTEX_MODEL_ID=gemini-1.5-pro,LOG_LEVEL=INFO" \
  --port=8080 \
  --memory=512Mi \
  --cpu=1 \
  --max-instances=3 \
  --timeout=60

echo "Deployment complete."
gcloud run services describe "${SERVICE_NAME}" --region="${REGION}" --project="${PROJECT_ID}" --format="value(status.url)"
