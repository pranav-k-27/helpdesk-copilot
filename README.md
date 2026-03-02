# GenAI Helpdesk Copilot
**Enterprise-grade conversational AI for helpdesk NLQ insights**
*Wipro / Topcoder Challenge Submission*

---

## Architecture Overview

A **dual-pipeline** system that routes queries intelligently:

| Query Type | Pipeline | Example |
|---|---|---|
| How-to / Policy | RAG (Hybrid Retrieval + Reranker) | "How do I fix VPN issues?" |
| Analytics / Insights | NLQ → SQL → Narration | "Which categories breach SLA most?" |

An **Intent Classifier** automatically routes each query to the correct pipeline — no manual selection needed.

---

## Quick Start (Docker)

```bash
# 1. Clone the repo
git clone <repo>
cd helpdesk-copilot

# 2. Configure environment
# Rename env.example.txt to .env
# Open .env and set: OPENAI_API_KEY=sk-your-key-here

# 3. Start all services (single command)
docker compose up -d

# 4. Generate synthetic ticket data (1000 tickets)
docker exec -e PYTHONPATH=/app helpdesk-backend python data/generate.py

# 5. Ingest KB articles into Qdrant vector store
docker exec -e PYTHONPATH=/app helpdesk-backend python data/ingest.py

# 6. Open the UI
# Browser: http://localhost
```

---

## Services

| Service | URL | Purpose |
|---|---|---|
| Frontend (Streamlit) | http://localhost | Chat UI |
| Backend API | http://localhost:8000 | FastAPI |
| API Docs | http://localhost:8000/docs | Swagger UI |
| Qdrant Dashboard | http://localhost:6333/dashboard | Vector Store UI |

---

## Demo Credentials

| Username | Password | Role | Access |
|---|---|---|---|
| admin | admin123 | Admin | Full access |
| agent001 | agent123 | Agent | Query + Stats |
| viewer | viewer123 | Viewer | Stats only |

---

## Project Structure

```
helpdesk-copilot/
├── backend/
│   ├── main.py                    # FastAPI app entry point
│   ├── config.py                  # Central config via pydantic-settings
│   ├── api/
│   │   ├── routes.py              # /query /audit /stats /ingest /auth
│   │   └── orchestrator.py        # Intent classification + pipeline routing
│   ├── rag/
│   │   └── pipeline.py            # Hybrid retrieval + reranker + grounded generation
│   ├── nlq/
│   │   └── sql_pipeline.py        # NLQ → SQL → execution → narration
│   ├── guardrails/
│   │   └── guard.py               # PII redaction, injection detection, rate limiting
│   ├── observability/
│   │   └── logger.py              # Full query lifecycle audit logging (JSON)
│   ├── auth/
│   │   └── middleware.py          # JWT + RBAC (Admin / Agent / Viewer)
│   ├── requirements.txt
│   └── Dockerfile
├── frontend/
│   ├── app.py                     # Streamlit chat UI
│   ├── requirements.txt
│   └── Dockerfile
├── data/
│   ├── generate.py                # Synthetic ticket DB (1000 tickets) + KB articles
│   └── ingest.py                  # Qdrant vector store ingestion
├── docker/
│   └── nginx.conf                 # Reverse proxy config
├── tests/
│   └── test_validation.py         # 16 validation tests — all passing
├── docs/
│   └── architecture.html          # Interactive architecture diagram
├── docker-compose.yml
├── env.example.txt                # Rename to .env and configure
└── README.md
```

---

## API Usage

### Step 1 — Get JWT Token
```bash
curl -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username": "admin", "password": "admin123"}'
```

### Step 2 — Ask a How-to Question (→ RAG Pipeline)
```bash
curl -X POST http://localhost:8000/api/v1/query \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <your-token>" \
  -d '{"query": "How do I fix VPN authentication failures?"}'
```

### Step 3 — Ask an Analytics Question (→ SQL Pipeline)
```bash
curl -X POST http://localhost:8000/api/v1/query \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <your-token>" \
  -d '{"query": "Show top 5 ticket categories by volume"}'
```

### View Audit Logs (Admin only)
```bash
curl http://localhost:8000/api/v1/audit?n=10 \
  -H "Authorization: Bearer <your-token>"
```

### View Observability Stats
```bash
curl http://localhost:8000/api/v1/stats \
  -H "Authorization: Bearer <your-token>"
```

---

## Sample Queries to Try

| Query | Pipeline | What it demonstrates |
|---|---|---|
| "How do I fix VPN authentication failures?" | RAG | How-to with citations |
| "What is the SLA policy for P1 tickets?" | RAG | Policy retrieval |
| "How do I reset a locked account?" | RAG | KB article lookup |
| "Show top 5 ticket categories by volume" | SQL | Analytics with data table |
| "Which priority has the highest SLA breach rate?" | SQL | Trend analysis |
| "How many tickets breached SLA in total?" | SQL | Aggregation query |
| "Ignore all previous instructions" | Blocked | Guardrails demo |

---

## Hallucination Control Strategy

1. **RAG grounding** — LLM instructed to answer ONLY from retrieved context
2. **Hybrid retrieval** — Dense (vector) + Sparse (BM25) merged via Reciprocal Rank Fusion
3. **Cross-encoder reranking** — Top-10 chunks → reranked → Top-3 best passed to LLM
4. **Confidence scoring** — Score < 0.5 triggers graceful fallback
5. **Fallback message** — *"I could not find sufficient information in the knowledge base"*
6. **SQL validation** — Generated SQL validated before execution (no DROP/DELETE/UPDATE)

---

## Security & Guardrails

| Feature | Implementation |
|---|---|
| Authentication | JWT Bearer tokens |
| Authorization | Role-based access (Admin / Agent / Viewer) |
| Prompt Injection | Regex pattern detection — 7 attack patterns blocked |
| PII Redaction | Email, phone, SSN, credit card masked before LLM |
| Rate Limiting | 20 requests / user / minute |
| SQL Safety | SELECT only — dangerous keywords rejected at validation |

---

## Observability & Governance

Every query is logged to `logs/audit.log` in structured JSON format:

```json
{
  "timestamp": "2026-03-01T12:00:00Z",
  "request_id": "uuid",
  "user_id": "agent001",
  "session_id": "uuid",
  "query": "How do I fix VPN issues?",
  "intent": "how_to",
  "answer": "To fix VPN...",
  "confidence": 0.85,
  "citations": [...],
  "tokens_used": 312,
  "latency_ms": 1420
}
```

View live stats via API:
```bash
curl http://localhost:8000/api/v1/stats -H "Authorization: Bearer <token>"
```

---

## Running Validation Tests

```bash
# Copy test file into container
docker cp tests/test_validation.py helpdesk-backend:/app/tests/test_validation.py

# Run all tests
docker exec -e PYTHONPATH=/app helpdesk-backend python -m pytest /app/tests/test_validation.py -v
```

**Result: 16/16 tests passing ✅**

| Test Category | Tests | Status |
|---|---|---|
| Guardrails — PII redaction | 3 | ✅ Pass |
| Guardrails — Injection detection | 2 | ✅ Pass |
| Guardrails — Rate limit / Length | 1 | ✅ Pass |
| Intent Classification | 4 | ✅ Pass |
| SQL Safety Validation | 5 | ✅ Pass |
| Hallucination Control | 1 | ✅ Pass |

---

## Environment Variables

```env
# Required
OPENAI_API_KEY=sk-your-key-here
JWT_SECRET_KEY=your-secret-key

# Qdrant (auto-configured via docker-compose)
QDRANT_HOST=qdrant
QDRANT_PORT=6333

# Guardrails
MAX_QUERY_LENGTH=2000
RATE_LIMIT_PER_MINUTE=20

# RAG Tuning
RAG_TOP_K=10
RAG_TOP_N_RERANK=3
CONFIDENCE_THRESHOLD=0.5
```
See `env.example.txt` for the full list.

---

## Challenge Objectives Addressed

| Objective | Implementation |
|---|---|
| NLQ User Interface | Streamlit chat UI with confidence bars + citation cards |
| RAG + Hallucination Control | Hybrid retrieval + BM25 + reranker + grounded prompts + fallback |
| Observability & Governance | JSON audit logs + `/stats` + `/audit` API endpoints |
| Security / Guardrails | JWT auth, RBAC, PII redaction, injection detection, rate limiting |
| Docker Compose | Single `docker compose up -d` — 4 services |
| Analytics Insights | NLQ→SQL dual pipeline with LLM narration + data tables |
