# InsurBot: Conversational AI Webhook Service

InsurBot is a production-grade conversational AI assistant designed to answer natural-language queries over insurance policies, claims, and coverage options. 

The system integrates a **Dialogflow CX** conversational agent with a **FastAPI** webhook service running on **GCP Cloud Run**, utilizing **Vertex AI (Gemini 1.5 Pro)** via **LangChain** for context-aware retrieval and prompt-level guardrails.

---

## Architecture Overview

```
      +-----------------------------------------+
      |             Looker Studio               |
      +-----------------------------------------+
                           |
                           v HTTP GET / POST
      +-----------------------------------------+
      |            Dialogflow CX                |
      +-----------------------------------------+
                           |
                           v POST /webhook (Fulfillment)
      +-----------------------------------------+
      |       FastAPI Webhook Service           |
      |          (GCP Cloud Run)                |
      |                                         |
      |   +-------------+     +-------------+   |
      |   | Input Guard |     | Output Guard|   |
      |   +-------------+     +-------------+   |
      |          |                   ^          |
      |          v                   |          |
      |   +-------------+     +-------------+   |
      |   |  Retriever  |---> | LangChain   |   |
      |   +-------------+     +-------------+   |
      +----------|-------------------^----------+
                 |                   | Vertex AI API
                 v SQL Queries       |
        +-----------------+ +-------------------+
        |    BigQuery     | | Vertex AI Gemini  |
        |  (Policy/Claims)| | (GenAI Inference) |
        +-----------------+ +-------------------+
```

1. **User Request**: The user speaks or types to a front-end interface (e.g. Looker Studio dashboard or chat widget).
2. **Intent Matching**: Dialogflow CX matches the query to one of three workflows (`PolicyLookup`, `ClaimsTriage`, `CoverageComparison`) and forwards it to the webhook.
3. **Input Guardrail**: FastAPI validates the incoming query, blocking prompt injections and PII (SSNs, card numbers).
4. **Retrieval**: LangChain custom retriever fetches matching records from BigQuery using parameterized queries.
5. **Generation**: The context documents are formatted into a prompt and sent to Vertex AI's Gemini 1.5 Pro.
6. **Output Guardrail**: The output is validated (length bounds, system leaks) and cross-checked against context documents to ensure cited monetary values are not hallucinated.
7. **Response**: Dialogflow CX receives the structured webhook response to complete the conversation turn.

---

## Directory Structure

```
├── .github/workflows/      # GitHub Actions CI (ruff, mypy, pytest)
├── agent/                  # Dialogflow CX flow & intent JSON exports
├── api/                    # FastAPI webhook application
│   ├── guardrails/         # Input, output, and policy guardrail checkers
│   ├── routers/            # /webhook and /health routers
│   ├── services/           # BigQuery, Vertex AI, and LangChain wrappers
│   ├── config.py           # Typed environment configurations
│   └── main.py             # FastAPI entrypoint
├── data/
│   ├── schema/             # BigQuery Table DDL SQL files
│   └── seed/               # Synthetic data generation and seeding script
├── deploy/                 # Dockerfile, Cloud Build, and Cloud Run manifests
├── scripts/                # Manual deployment shell scripts
└── tests/                  # Unit tests for all routers, services, and guardrails
```

---

## Getting Started

### Prerequisites
- Python 3.11 or higher
- Google Cloud SDK (`gcloud` CLI)
- A GCP Project with BigQuery, Vertex AI, and Artifact Registry enabled
- Docker (optional, for local container builds)

### 1. Local Environment Setup

Clone the repository and install the dependencies:
```bash
# Create and activate virtual environment
python3.11 -m venv .venv
source .venv/bin/activate

# Install package manager 'uv' for fast installation
pip install uv
uv pip install -r requirements.txt
```

Copy the `.env.example` to `.env` and fill in your GCP configuration:
```bash
cp .env.example .env
```

### 2. Database Schema and Seeding

Create your BigQuery tables and seed them with 1,000 synthetic policies and 3,000 claims:
```bash
# Authenticate with Google Cloud
gcloud auth application-default login

# Execute the seed script
python -m data.seed.seed_data --project <your-gcp-project-id> --dataset insurbot --location US
```

### 3. Running and Testing the Webhook Locally

Run the development server:
```bash
source .venv/bin/activate
python -m uvicorn api.main:app --host 0.0.0.0 --port 8080 --reload
```

Use `curl` to smoke test the health and readiness endpoints:
```bash
# Liveness probe
curl http://localhost:8080/health

# Readiness probe (verifies connection to BigQuery and Vertex AI)
curl http://localhost:8080/readiness
```

### 4. Running Unit Tests

Run the full test suite locally:
```bash
source .venv/bin/activate
pytest tests/unit/ -v
```

---

## Dialogflow CX Setup

1. **Create Agent**: Create a new Dialogflow CX agent in your GCP Console.
2. **Import configuration**: Import the JSON definitions from the `agent/` folder using the console's Restore function.
3. **Configure Webhook**:
   - Go to **Webhooks** in the Manage tab.
   - Point your webhook URL to your deployed Cloud Run service endpoint: `https://<service-url>/webhook`.

---

## Deployment

### CI/CD via Cloud Build
The project contains a `cloudbuild.yaml` definition. When a push to the `main` branch occurs, Google Cloud Build triggers a pipeline to:
1. Run unit tests
2. Build the production Docker container
3. Push the container image to Artifact Registry
4. Deploy the new container revision to Cloud Run with active health probes

### Manual Deployment
To deploy manually, configure target project options and run:
```bash
./scripts/deploy.sh <your-gcp-project-id> us-central1
```
