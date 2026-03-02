"""
API Routes
  POST /api/v1/auth/login    — get JWT token
  POST /api/v1/query         — main NLQ endpoint
  GET  /api/v1/audit         — audit logs (admin only)
  GET  /api/v1/stats         — observability stats (agent+)
  POST /api/v1/ingest        — trigger KB ingestion (admin only)
"""
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from api.orchestrator import QueryOrchestrator
from auth.middleware import (
    LoginRequest, Token, TokenData,
    authenticate_user, create_access_token,
    get_current_user, require_permission,
)
from observability.logger import AuditLogger

router       = APIRouter()
orchestrator = QueryOrchestrator()
audit_logger = AuditLogger()


# ── Request / Response models ─────────────────────────────────────────────────
class QueryRequest(BaseModel):
    query:      str
    session_id: Optional[str] = None


class QueryResponse(BaseModel):
    request_id: str
    answer:     str
    intent:     str
    citations:  list
    confidence: float
    sql:        Optional[str] = None
    data:       Optional[list] = None


# ── Auth ──────────────────────────────────────────────────────────────────────
@router.post("/auth/login", response_model=Token, tags=["Auth"])
def login(body: LoginRequest):
    user = authenticate_user(body.username, body.password)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid username or password")
    return create_access_token(user["username"], user["role"])


# ── Query ─────────────────────────────────────────────────────────────────────
@router.post("/query", response_model=QueryResponse, tags=["Query"])
async def query_endpoint(
    body:         QueryRequest,
    current_user: TokenData = Depends(require_permission("query")),
):
    if not body.query.strip():
        raise HTTPException(status_code=400, detail="Query cannot be empty")

    session_id = body.session_id or str(uuid.uuid4())
    result = await orchestrator.process(
        query=body.query,
        user_id=current_user.username,
        session_id=session_id,
    )

    return QueryResponse(
        request_id = str(uuid.uuid4()),
        answer     = result.get("answer", ""),
        intent     = result.get("intent", "unknown"),
        citations  = result.get("citations", []),
        confidence = result.get("confidence", 0.0),
        sql        = result.get("sql"),
        data       = result.get("data"),
    )


# ── Audit ─────────────────────────────────────────────────────────────────────
@router.get("/audit", tags=["Observability"])
def get_audit_logs(
    n:            int = 50,
    current_user: TokenData = Depends(require_permission("audit")),
):
    return {"logs": audit_logger.get_recent_logs(n)}


# ── Stats ─────────────────────────────────────────────────────────────────────
@router.get("/stats", tags=["Observability"])
def get_stats(
    current_user: TokenData = Depends(require_permission("stats")),
):
    return audit_logger.get_stats()


# ── Ingest ────────────────────────────────────────────────────────────────────
@router.post("/ingest", tags=["Admin"])
def ingest_documents(
    current_user: TokenData = Depends(require_permission("ingest")),
):
    """Trigger KB article ingestion into Qdrant vector store."""
    import json
    from pathlib import Path
    from rag.pipeline import RAGPipeline
    from config import settings

    kb_path = Path(settings.kb_json_path)
    if not kb_path.exists():
        raise HTTPException(
            status_code=404,
            detail=f"KB file not found at {kb_path}. Run data/generate.py first."
        )

    pipeline = RAGPipeline()
    articles = json.loads(kb_path.read_text())

    ingested = 0
    for article in articles:
        paragraphs = [p.strip() for p in article["content"].split("\n\n") if len(p.strip()) > 50]
        for i, chunk in enumerate(paragraphs):
            pipeline.ingest_document(
                text=chunk,
                metadata={
                    "source":     f"{article['id']} — {article['title']}",
                    "doc_type":   article["doc_type"],
                    "article_id": article["id"],
                },
                doc_id=f"{article['id']}-chunk-{i}"
            )
            ingested += 1

    return {"status": "success", "chunks_ingested": ingested, "articles": len(articles)}


# ── Health ────────────────────────────────────────────────────────────────────
@router.get("/health", tags=["System"])
def health():
    return {"status": "healthy"}
