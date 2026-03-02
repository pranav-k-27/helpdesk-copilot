"""
Observability & Audit Logger
Captures full query lifecycle: prompt → retrieval → response → tokens → latency
"""
import json
import os
import time
from datetime import datetime
from pathlib import Path

LOG_DIR = Path("./data/audit_logs")
LOG_DIR.mkdir(parents=True, exist_ok=True)

class AuditLogger:
    def __init__(self):
        self.log_file = LOG_DIR / f"audit_{datetime.now().strftime('%Y%m%d')}.jsonl"

    def log(self, record: dict):
        """Append a structured audit record to the daily log file."""
        entry = {
            "timestamp":   datetime.utcnow().isoformat() + "Z",
            "session_id":  record.get("session_id", ""),
            "user_id":     record.get("user_id", "anonymous"),
            "query":       record.get("query", ""),
            "intent":      record.get("intent", ""),
            "answer":      record.get("result", {}).get("answer", "")[:500],
            "confidence":  record.get("result", {}).get("confidence", 0),
            "citations":   record.get("result", {}).get("citations", []),
            "tokens_used": record.get("result", {}).get("tokens_used", 0),
            "sql":         record.get("result", {}).get("sql", None),
            "redactions":  record.get("redactions", []),
        }
        try:
            with open(self.log_file, "a") as f:
                f.write(json.dumps(entry) + "\n")
        except Exception as e:
            print(f"[AUDIT ERROR] Failed to write log: {e}")

    def get_recent_logs(self, n: int = 50) -> list:
        """Read the last N audit entries."""
        try:
            with open(self.log_file, "r") as f:
                lines = f.readlines()
            return [json.loads(line) for line in lines[-n:]]
        except FileNotFoundError:
            return []

    def get_stats(self) -> dict:
        """Aggregate stats for monitoring dashboard."""
        logs = self.get_recent_logs(1000)
        if not logs:
            return {}

        total = len(logs)
        avg_confidence = sum(l.get("confidence", 0) for l in logs) / total
        avg_tokens     = sum(l.get("tokens_used", 0) for l in logs) / total
        intents        = {}
        for log in logs:
            intent = log.get("intent", "unknown")
            intents[intent] = intents.get(intent, 0) + 1

        return {
            "total_queries":    total,
            "avg_confidence":   round(avg_confidence, 3),
            "avg_tokens":       round(avg_tokens, 1),
            "intent_breakdown": intents,
            "low_confidence_count": sum(1 for l in logs if l.get("confidence", 1) < 0.5)
        }
