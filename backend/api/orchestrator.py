"""
Query Orchestrator — Intent classification and pipeline routing
Classifies NLQ as: HOW_TO (→ RAG) | ANALYTICS (→ NLQ-SQL) | POLICY (→ RAG)
"""
import re
from enum import Enum
from typing import Tuple
from openai import OpenAI

from rag.pipeline import RAGPipeline
from nlq.sql_pipeline import NLQSQLPipeline
from guardrails.guard import GuardrailsEngine
from observability.logger import AuditLogger

client = OpenAI()

class QueryIntent(Enum):
    HOW_TO   = "how_to"     # "How do I fix X?" → RAG pipeline
    ANALYTICS = "analytics" # "Show trends / SLA breaches" → SQL pipeline
    POLICY   = "policy"     # "What is the policy for X?" → RAG pipeline
    UNKNOWN  = "unknown"

ANALYTICS_PATTERNS = [
    r"\b(how many|count|total|average|trend|top \d|most|least|percent|rate|volume)\b",
    r"\b(this (week|month|year)|last (week|month|year)|yesterday|today)\b",
    r"\b(breach|sla|overdue|resolved|unresolved|open|closed|pending)\b.*(ticket|incident)",
    r"\b(which|what).*(highest|lowest|most|frequently|often)\b",
]

HOW_TO_PATTERNS = [
    r"\bhow (do i|to|can i|should i)\b",
    r"\bsteps (to|for)\b",
    r"\bfix|resolve|troubleshoot|reset|configure\b",
]

class QueryOrchestrator:
    def __init__(self):
        self.rag_pipeline = RAGPipeline()
        self.sql_pipeline = NLQSQLPipeline()
        self.guardrails   = GuardrailsEngine()
        self.logger       = AuditLogger()

    def classify_intent(self, query: str) -> QueryIntent:
        """Fast rule-based classification with LLM fallback."""
        q = query.lower()

        for pattern in ANALYTICS_PATTERNS:
            if re.search(pattern, q):
                return QueryIntent.ANALYTICS

        for pattern in HOW_TO_PATTERNS:
            if re.search(pattern, q):
                return QueryIntent.HOW_TO

        # LLM fallback for ambiguous queries
        try:
            response = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{
                    "role": "system",
                    "content": (
                        "Classify the helpdesk query intent. "
                        "Reply with exactly one word: analytics, how_to, or policy."
                    )
                }, {
                    "role": "user",
                    "content": query
                }],
                max_tokens=10,
                temperature=0
            )
            label = response.choices[0].message.content.strip().lower()
            return {
                "analytics": QueryIntent.ANALYTICS,
                "how_to":    QueryIntent.HOW_TO,
                "policy":    QueryIntent.POLICY,
            }.get(label, QueryIntent.HOW_TO)
        except Exception:
            return QueryIntent.HOW_TO  # safe default

    async def process(self, query: str, user_id: str, session_id: str) -> dict:
        """Main entry point — guard → classify → route → log."""

        # 1. Guardrails check
        guard_result = self.guardrails.check(query)
        if not guard_result["safe"]:
            return {
                "answer":     "I'm unable to process this request.",
                "reason":     guard_result["reason"],
                "intent":     "blocked",
                "citations":  [],
                "confidence": 0.0
            }

        clean_query = guard_result["clean_query"]

        # 2. Classify intent
        intent = self.classify_intent(clean_query)

        # 3. Route to appropriate pipeline
        if intent == QueryIntent.ANALYTICS:
            result = await self.sql_pipeline.run(clean_query)
        else:
            result = await self.rag_pipeline.run(clean_query)

        result["intent"] = intent.value

        # 4. Audit log
        self.logger.log({
            "user_id":    user_id,
            "session_id": session_id,
            "query":      clean_query,
            "intent":     intent.value,
            "result":     result
        })

        return result
