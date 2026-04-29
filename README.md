# Multi-Agent Platform

Hub-and-spoke multi-agent system for automated KYC onboarding. Orchestrates document validation, identity verification, sanctions screening, risk scoring, and compliance decisions via Claude-powered agents and RabbitMQ.

## Quick start

```bash
cp .env.example .env   # fill in real credentials
docker compose up -d   # starts Redis, RabbitMQ, PostgreSQL
uvicorn api.webhook_handler:app --reload   # API on :8000
python -m workers.agent_worker              # consumer
```

## Running tests (no infra required)

Tests use in-memory fakes for Redis and PostgreSQL, and stub functions for all agents — no real API calls needed.

```bash
pip install -r requirements.txt
# Set a dummy key so base_agent.py can import without error
ANTHROPIC_API_KEY=test pytest tests/ -v
```

**Note:** `base_agent.py` instantiates `anthropic.Anthropic()` at module level, which reads `ANTHROPIC_API_KEY` from the environment. Set a non-empty dummy value when running tests that don't invoke Claude.

## Architecture

```
Client / API Gateway
        │
        ▼
   Orchestrator  ◄──── Redis (case state)
        │               PostgreSQL (audit log)
        ▼
Message Broker (RabbitMQ)
   ┌────┼────┬──────┬────────┐
   ▼    ▼    ▼      ▼        ▼
 Doc  Ident Sanct  Risk   Decision
Agent Agent  Agent Agent   Agent
   └────┴────┴──────┴────────┘
        │
        ▼
  Notification Agent
```

## Agent models

| Agent | Model |
|---|---|
| Orchestrator | claude-sonnet-4-6 |
| Document | claude-haiku-4-5-20251001 |
| Identity | claude-sonnet-4-6 |
| Sanctions | claude-haiku-4-5-20251001 |
| Risk | claude-sonnet-4-6 |
| Decision | claude-sonnet-4-6 |
| Notification | claude-haiku-4-5-20251001 |

## External integrations required

- **AWS Textract** — OCR for identity documents
- **Onfido** — Liveness / face-match (stub implementation in `tools/liveness_client.py`)
- **ComplyAdvantage** — Sanctions & PEP screening
- **SendGrid** — Email notifications
- **MinIO or S3** — Document storage

See `.env.example` for all required environment variables.
