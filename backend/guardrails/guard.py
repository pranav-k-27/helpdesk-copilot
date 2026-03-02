"""
Guardrails Engine — Input validation, PII masking, injection detection
"""
import re
import time
from collections import defaultdict

# PII patterns
PII_PATTERNS = {
    "email":   r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b',
    "phone":   r'\b(\+?\d{1,3}[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b',
    "ssn":     r'\b\d{3}-\d{2}-\d{4}\b',
    "credit_card": r'\b(?:\d{4}[-\s]?){3}\d{4}\b',
    "ip_addr": r'\b(?:\d{1,3}\.){3}\d{1,3}\b',
}

# Prompt injection patterns
INJECTION_PATTERNS = [
    r'ignore.{0,20}(instructions?|prompts?|rules?|constraints?|previous|above|prior)',
    r'(you are now|act as|pretend to be|roleplay as|simulate being)',
    r'(jailbreak|bypass|override|disable|circumvent).{0,30}(filter|guard|safety|restriction)',
    r'(repeat|say|print|output|write).{0,20}(system prompt|instructions|rules)',
    r'<(script|iframe|img|svg|object|embed)',  # HTML injection
    r'(\{|\[)\s*(system|instruction|override)',  # JSON injection
    r'DAN|do anything now|developer mode',
]

class RateLimiter:
    def __init__(self, max_requests: int = 20, window_seconds: int = 60):
        self.max_requests  = max_requests
        self.window        = window_seconds
        self.user_requests = defaultdict(list)

    def is_allowed(self, user_id: str) -> bool:
        now = time.time()
        window_start = now - self.window
        self.user_requests[user_id] = [
            t for t in self.user_requests[user_id] if t > window_start
        ]
        if len(self.user_requests[user_id]) >= self.max_requests:
            return False
        self.user_requests[user_id].append(now)
        return True

class GuardrailsEngine:
    def __init__(self):
        self.rate_limiter = RateLimiter(max_requests=20, window_seconds=60)

    def detect_injection(self, text: str) -> bool:
        text_lower = text.lower()
        for pattern in INJECTION_PATTERNS:
            if re.search(pattern, text_lower, re.IGNORECASE):
                return True
        return False

    def redact_pii(self, text: str) -> tuple[str, list]:
        """Redact PII from text, return clean text and list of redactions."""
        redactions = []
        clean = text
        for pii_type, pattern in PII_PATTERNS.items():
            matches = re.findall(pattern, clean)
            if matches:
                redactions.extend([(pii_type, m) for m in matches])
                clean = re.sub(pattern, f"[{pii_type.upper()}_REDACTED]", clean)
        return clean, redactions

    def check_length(self, text: str, max_chars: int = 2000) -> bool:
        return len(text) <= max_chars

    def check(self, query: str, user_id: str = "anonymous") -> dict:
        """Run all guardrail checks. Returns {safe, clean_query, reason}."""

        # 1. Length check
        if not self.check_length(query):
            return {"safe": False, "reason": "Query too long (max 2000 chars)", "clean_query": query}

        # 2. Prompt injection detection
        if self.detect_injection(query):
            return {"safe": False, "reason": "Potential prompt injection detected", "clean_query": query}

        # 3. PII redaction (non-blocking — we redact and continue)
        clean_query, redactions = self.redact_pii(query)

        # 4. Rate limiting
        if not self.rate_limiter.is_allowed(user_id):
            return {"safe": False, "reason": "Rate limit exceeded. Please wait.", "clean_query": clean_query}

        return {
            "safe":       True,
            "clean_query": clean_query,
            "redactions": redactions,
            "reason":     None
        }
