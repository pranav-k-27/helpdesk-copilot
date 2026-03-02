"""
RAG Pipeline — Hybrid retrieval (dense + sparse BM25) + cross-encoder reranking
Uses Qdrant as vector store. Answers How-to and Policy queries.
"""
from typing import List, Dict
from openai import OpenAI
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, PointStruct, Filter
from rank_bm25 import BM25Okapi
from sentence_transformers import CrossEncoder

from config import settings

openai_client = OpenAI(api_key=settings.OPENAI_API_KEY)

SYSTEM_PROMPT = """You are an expert helpdesk assistant.
Answer the user's question using ONLY the context provided below.
If the answer is not present in the context, respond with exactly:
"I could not find sufficient information in the knowledge base to answer this accurately."

Always cite the source document name at the end of your answer.
Be concise, accurate, and professional.

Context:
{context}
"""


class RAGPipeline:
    def __init__(self):
        self.qdrant    = QdrantClient(host=settings.QDRANT_HOST, port=settings.QDRANT_PORT)
        self.reranker  = CrossEncoder("cross-encoder/ms-marco-MiniLM-L-6-v2")
        self._bm25     = None
        self._bm25_docs = []
        self._ensure_collection()

    def _ensure_collection(self):
        """Create Qdrant collection if it doesn't exist."""
        existing = [c.name for c in self.qdrant.get_collections().collections]
        if settings.QDRANT_COLLECTION_KB not in existing:
            self.qdrant.create_collection(
                collection_name=settings.QDRANT_COLLECTION_KB,
                vectors_config=VectorParams(size=1536, distance=Distance.COSINE),
            )

    def _get_embedding(self, text: str) -> List[float]:
        response = openai_client.embeddings.create(
            model=settings.OPENAI_EMBEDDING_MODEL,
            input=text
        )
        return response.data[0].embedding

    def _build_bm25(self):
        """Build BM25 index from all docs in Qdrant."""
        results = self.qdrant.scroll(
            collection_name=settings.QDRANT_COLLECTION_KB,
            limit=1000,
            with_payload=True,
            with_vectors=False,
        )
        points = results[0]
        if not points:
            return
        self._bm25_docs = [p.payload.get("text", "") for p in points]
        tokenized = [doc.lower().split() for doc in self._bm25_docs]
        self._bm25 = BM25Okapi(tokenized)

    def _dense_search(self, query: str, top_k: int = 10) -> List[Dict]:
        embedding = self._get_embedding(query)
        results = self.qdrant.search(
            collection_name=settings.QDRANT_COLLECTION_KB,
            query_vector=embedding,
            limit=top_k,
            with_payload=True,
        )
        return [
            {
                "text":     r.payload.get("text", ""),
                "metadata": {k: v for k, v in r.payload.items() if k != "text"},
                "score":    r.score,
            }
            for r in results
        ]

    def _sparse_search(self, query: str, top_k: int = 10) -> List[Dict]:
        if self._bm25 is None:
            self._build_bm25()
        if self._bm25 is None:
            return []
        tokens = query.lower().split()
        scores = self._bm25.get_scores(tokens)
        top_indices = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)[:top_k]
        return [
            {
                "text":     self._bm25_docs[idx],
                "metadata": {},
                "score":    float(scores[idx]),
            }
            for idx in top_indices if scores[idx] > 0
        ]

    def _hybrid_merge(self, dense: List[Dict], sparse: List[Dict]) -> List[Dict]:
        """Reciprocal Rank Fusion."""
        k = 60
        scores = {}
        for rank, doc in enumerate(dense):
            key = doc["text"][:100]
            if key not in scores:
                scores[key] = {"doc": doc, "score": 0}
            scores[key]["score"] += 1 / (rank + k)
        for rank, doc in enumerate(sparse):
            key = doc["text"][:100]
            if key not in scores:
                scores[key] = {"doc": doc, "score": 0}
            scores[key]["score"] += 1 / (rank + k)
        merged = sorted(scores.values(), key=lambda x: x["score"], reverse=True)
        return [item["doc"] for item in merged]

    def _rerank(self, query: str, docs: List[Dict], top_n: int = 3) -> List[Dict]:
        """Cross-encoder reranker: Top-10 → Top-3."""
        if not docs:
            return docs
        pairs  = [(query, doc["text"]) for doc in docs]
        scores = self.reranker.predict(pairs)
        ranked = sorted(zip(docs, scores), key=lambda x: x[1], reverse=True)
        return [doc for doc, _ in ranked[:top_n]]

    async def run(self, query: str) -> dict:
        """Full RAG pipeline: hybrid retrieve → rerank → generate."""
        # Hybrid retrieval
        dense_docs  = self._dense_search(query, top_k=settings.RAG_TOP_K)
        sparse_docs = self._sparse_search(query, top_k=settings.RAG_TOP_K)
        merged_docs = self._hybrid_merge(dense_docs, sparse_docs)

        # Rerank
        top_docs = self._rerank(query, merged_docs, top_n=settings.RAG_TOP_N_RERANK)

        if not top_docs:
            return {
                "answer":     "I could not find sufficient information in the knowledge base.",
                "citations":  [],
                "confidence": 0.0,
            }

        # Build context + citations
        context_parts = []
        citations     = []
        for i, doc in enumerate(top_docs):
            source = doc["metadata"].get("source", f"Document {i+1}")
            context_parts.append(f"[Source {i+1}: {source}]\n{doc['text']}")
            citations.append({
                "source":        source,
                "doc_type":      doc["metadata"].get("doc_type", "unknown"),
                "chunk_preview": doc["text"][:150] + "...",
            })

        context = "\n\n".join(context_parts)

        # Generate answer
        response = openai_client.chat.completions.create(
            model=settings.OPENAI_MODEL,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT.format(context=context)},
                {"role": "user",   "content": query},
            ],
            temperature=0.1,
            max_tokens=600,
        )

        answer = response.choices[0].message.content
        confidence = 0.0 if "could not find" in answer.lower() else round(
            float(top_docs[0].get("score", 0.8)), 2
        )

        return {
            "answer":      answer,
            "citations":   citations,
            "confidence":  confidence,
            "tokens_used": response.usage.total_tokens,
        }

    def ingest_document(self, text: str, metadata: dict, doc_id: str):
        """Add a single document chunk to Qdrant."""
        import uuid
        embedding = self._get_embedding(text)
        self.qdrant.upsert(
            collection_name=settings.QDRANT_COLLECTION_KB,
            points=[PointStruct(
                id=str(uuid.uuid4()),
                vector=embedding,
                payload={"text": text, **metadata},
            )]
        )
        self._bm25 = None  # Reset BM25 index