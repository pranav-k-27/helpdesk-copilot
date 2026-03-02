"""
KB Ingestion Script
Reads KB articles from JSON, chunks them, embeds with OpenAI,
and stores in Qdrant vector store.

Run: python data/ingest.py
"""
import json
import os
import sys
import uuid
from pathlib import Path

# Allow running from project root
sys.path.insert(0, "/app")

from openai import OpenAI
from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance, VectorParams, PointStruct, Filter,
    FieldCondition, MatchValue
)

from config import settings

client    = OpenAI(api_key=settings.OPENAI_API_KEY)
qdrant    = QdrantClient(host=settings.QDRANT_HOST, port=settings.QDRANT_PORT)

VECTOR_SIZE = 1536  # text-embedding-3-small output dimension


def ensure_collection(collection_name: str):
    """Create Qdrant collection if it doesn't exist."""
    existing = [c.name for c in qdrant.get_collections().collections]
    if collection_name not in existing:
        qdrant.create_collection(
            collection_name=collection_name,
            vectors_config=VectorParams(size=VECTOR_SIZE, distance=Distance.COSINE),
        )
        print(f"✅ Created Qdrant collection: {collection_name}")
    else:
        print(f"ℹ️  Collection already exists: {collection_name}")


def get_embedding(text: str) -> list[float]:
    response = client.embeddings.create(
        model=settings.OPENAI_EMBEDDING_MODEL,
        input=text
    )
    return response.data[0].embedding


def chunk_text(text: str, chunk_size: int = 600, overlap: int = 60) -> list[str]:
    """Split text into overlapping chunks by word count."""
    words  = text.split()
    chunks = []
    start  = 0
    while start < len(words):
        end   = min(start + chunk_size, len(words))
        chunk = " ".join(words[start:end])
        if len(chunk.strip()) > 50:
            chunks.append(chunk)
        start += chunk_size - overlap
    return chunks


def ingest_kb_articles():
    kb_path = Path(settings.kb_json_path)
    if not kb_path.exists():
        print(f"❌ KB file not found: {kb_path}")
        print("   Run: python data/generate.py first")
        sys.exit(1)

    articles = json.loads(kb_path.read_text())
    ensure_collection(settings.QDRANT_COLLECTION_KB)

    total_chunks = 0
    for article in articles:
        print(f"\n📄 Ingesting: {article['id']} — {article['title']}")
        chunks = chunk_text(
            article["content"],
            chunk_size=settings.CHUNK_SIZE,
            overlap=settings.CHUNK_OVERLAP,
        )

        points = []
        for i, chunk in enumerate(chunks):
            embedding = get_embedding(chunk)
            point = PointStruct(
                id=str(uuid.uuid4()),
                vector=embedding,
                payload={
                    "text":       chunk,
                    "source":     f"{article['id']} — {article['title']}",
                    "doc_type":   article["doc_type"],
                    "article_id": article["id"],
                    "chunk_index": i,
                }
            )
            points.append(point)
            print(f"   Chunk {i+1}/{len(chunks)} embedded ({len(chunk.split())} words)")

        qdrant.upsert(collection_name=settings.QDRANT_COLLECTION_KB, points=points)
        total_chunks += len(chunks)
        print(f"   ✅ {len(chunks)} chunks stored")

    print(f"\n🎉 Ingestion complete! Total chunks: {total_chunks}")
    print(f"   Qdrant dashboard: http://localhost:6333/dashboard")


def ingest_schema_metadata():
    """
    Embed ticket DB schema metadata for NLQ→SQL context retrieval.
    This helps the LLM understand the database structure.
    """
    schema_docs = [
        {
            "id": "schema-tickets",
            "text": """
                Table: tickets
                Columns: ticket_id (TEXT), title (TEXT), category (TEXT: VPN/Email/Hardware/Software/Network/Access/Printer/Database),
                priority (TEXT: P1-Critical/P2-High/P3-Medium/P4-Low), status (TEXT: Open/In Progress/Resolved/Closed),
                created_at (DATETIME), resolved_at (DATETIME nullable), sla_breach (INTEGER: 0 or 1),
                agent_id (TEXT), department (TEXT: IT/HR/Finance/Operations/Sales/Legal),
                resolution_time_hrs (REAL nullable), customer_rating (INTEGER: 1-5 nullable).
                Use strftime('%Y-%m', created_at) for monthly grouping.
            """,
            "doc_type": "schema"
        },
        {
            "id": "schema-analytics-examples",
            "text": """
                Example analytics queries:
                - Count tickets by category: SELECT category, COUNT(*) as total FROM tickets GROUP BY category ORDER BY total DESC
                - SLA breach rate: SELECT category, SUM(sla_breach)*100.0/COUNT(*) as breach_pct FROM tickets GROUP BY category
                - Monthly ticket volume: SELECT strftime('%Y-%m', created_at) as month, COUNT(*) as total FROM tickets GROUP BY month
                - Avg resolution time by priority: SELECT priority, AVG(resolution_time_hrs) as avg_hrs FROM tickets WHERE resolved_at IS NOT NULL GROUP BY priority
                - Top agents by tickets resolved: SELECT agent_id, COUNT(*) as resolved FROM tickets WHERE status='Resolved' GROUP BY agent_id ORDER BY resolved DESC LIMIT 10
            """,
            "doc_type": "schema_examples"
        },
    ]

    ensure_collection(settings.QDRANT_COLLECTION_SCHEMA)
    print("\n📊 Ingesting schema metadata...")

    for doc in schema_docs:
        embedding = get_embedding(doc["text"])
        qdrant.upsert(
            collection_name=settings.QDRANT_COLLECTION_SCHEMA,
            points=[PointStruct(
                id=str(uuid.uuid4()),
                vector=embedding,
                payload={"text": doc["text"], "doc_type": doc["doc_type"]}
            )]
        )
        print(f"   ✅ Stored: {doc['id']}")

    print("   Schema metadata ingestion complete!")


if __name__ == "__main__":
    print("=" * 55)
    print("  GenAI Helpdesk Copilot — KB Ingestion")
    print("=" * 55)
    ingest_kb_articles()
    ingest_schema_metadata()
