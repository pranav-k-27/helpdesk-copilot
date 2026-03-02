"""
NLQ → SQL Pipeline — Converts natural language analytics queries to SQL
Grounded in schema metadata retrieved from vector store
"""
import sqlite3
import json
import re
from openai import OpenAI

client = OpenAI()

# Helpdesk ticket DB schema definition (used in prompts + embedded for retrieval)
SCHEMA_DESCRIPTION = """
Database: helpdesk_tickets

Table: tickets
  - ticket_id       TEXT PRIMARY KEY  (e.g. TKT-001)
  - title           TEXT              (short description of the issue)
  - category        TEXT              (VPN, Email, Hardware, Software, Network, Access)
  - priority        TEXT              (P1-Critical, P2-High, P3-Medium, P4-Low)
  - status          TEXT              (Open, In Progress, Resolved, Closed)
  - created_at      DATETIME          (ticket creation timestamp)
  - resolved_at     DATETIME          (resolution timestamp, NULL if unresolved)
  - sla_breach      INTEGER           (1 = SLA breached, 0 = within SLA)
  - agent_id        TEXT              (assigned agent)
  - department      TEXT              (IT, HR, Finance, Operations)
  - resolution_time_hrs REAL          (hours to resolve, NULL if unresolved)
  - customer_rating INTEGER           (1-5, NULL if not rated)

Useful derived expressions:
  - Resolution rate: COUNT(CASE WHEN status='Resolved' THEN 1 END) * 100.0 / COUNT(*)
  - SLA breach rate: SUM(sla_breach) * 100.0 / COUNT(*)
  - Avg resolution: AVG(resolution_time_hrs)
"""

from datetime import datetime
_today = datetime.now().strftime("%Y-%m-%d")
_month = datetime.now().strftime("%Y-%m")

SQL_SYSTEM_PROMPT = f"""You are an expert SQL analyst for a helpdesk system.
Convert the user's natural language question into a valid SQLite SQL query.
Today's date is {_today}. Current month is {_month}.
For "this month" use: strftime('%Y-%m', created_at) = '{_month}'
For "this year" use: strftime('%Y', created_at) = '{datetime.now().strftime("%Y")}'
If data may not exist for current month, remove the date filter and show all-time data instead.

{SCHEMA_DESCRIPTION}

Rules:
1. Output ONLY the SQL query — no explanation, no markdown, no backticks.
2. Use proper SQLite syntax.
3. Always add LIMIT 100 unless the user asks for all records.
4. Never use DROP, DELETE, UPDATE, INSERT, or ALTER statements.
5. For date filtering, use: strftime('%Y-%m', created_at) = '2024-01'
6. If the question cannot be answered with the schema, output: UNSUPPORTED
"""

NARRATION_PROMPT = """You are a helpful analytics assistant for a helpdesk team.
The user asked: "{query}"

Here are the SQL query results:
{results}

Provide a clear, concise summary of these results in 2-4 sentences.
Highlight any notable trends, risks, or actionable insights.
Be specific with numbers from the data.
"""

class NLQSQLPipeline:
    def __init__(self, db_path: str = "./data/helpdesk.db"):
        self.db_path = db_path

    def _generate_sql(self, query: str) -> str:
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": SQL_SYSTEM_PROMPT},
                {"role": "user",   "content": query}
            ],
            temperature=0,
            max_tokens=300
        )
        return response.choices[0].message.content.strip()

    def _validate_sql(self, sql: str) -> tuple[bool, str]:
        """Basic SQL safety validation."""
        if sql == "UNSUPPORTED":
            return False, "Query not supported with available data"

        dangerous = ["DROP", "DELETE", "UPDATE", "INSERT", "ALTER", "EXEC", "--", ";--"]
        sql_upper = sql.upper()
        for keyword in dangerous:
            if keyword in sql_upper:
                return False, f"Dangerous SQL keyword detected: {keyword}"

        if not sql_upper.strip().startswith("SELECT"):
            return False, "Only SELECT queries are permitted"

        return True, "valid"

    def _execute_sql(self, sql: str) -> list[dict]:
        """Execute SQL and return results as list of dicts."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            cursor = conn.execute(sql)
            rows = [dict(row) for row in cursor.fetchall()]
            return rows
        finally:
            conn.close()

    def _narrate_results(self, query: str, sql: str, results: list) -> str:
        """LLM generates a plain-English narrative of query results."""
        if not results:
            return "No data found matching your query criteria."

        # Truncate large result sets for the prompt
        sample = results[:20]
        results_str = json.dumps(sample, indent=2, default=str)

        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[{
                "role": "user",
                "content": NARRATION_PROMPT.format(query=query, results=results_str)
            }],
            temperature=0.3,
            max_tokens=300
        )
        return response.choices[0].message.content

    async def run(self, query: str) -> dict:
        """Full NLQ→SQL pipeline: generate → validate → execute → narrate."""

        # Step 1: Generate SQL
        sql = self._generate_sql(query)

        # Step 2: Validate SQL
        valid, reason = self._validate_sql(sql)
        if not valid:
            return {
                "answer":     f"Unable to process analytics query: {reason}",
                "sql":        sql,
                "data":       [],
                "citations":  [],
                "confidence": 0.0
            }

        # Step 3: Execute SQL
        try:
            results = self._execute_sql(sql)
        except Exception as e:
            return {
                "answer":     f"Database query failed: {str(e)}",
                "sql":        sql,
                "data":       [],
                "citations":  [],
                "confidence": 0.0
            }

        # Step 4: Narrate results
        narrative = self._narrate_results(query, sql, results)

        return {
            "answer":     narrative,
            "sql":        sql,
            "data":       results[:50],  # Return up to 50 rows to frontend
            "row_count":  len(results),
            "citations":  [{"source": "helpdesk_tickets database", "doc_type": "structured_data"}],
            "confidence": 0.95 if results else 0.3
        }
