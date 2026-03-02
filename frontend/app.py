"""
Streamlit Frontend — GenAI Helpdesk Copilot
Professional chat UI with login, citations, and data tables
"""
import time
import requests
import pandas as pd
import streamlit as st

# ── Page config ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Helpdesk Copilot",
    page_icon="🤖",
    layout="wide",
    initial_sidebar_state="expanded",
)

API_BASE = "http://backend:8000/api/v1"

# ── Custom CSS ────────────────────────────────────────────────────────────────
st.markdown("""
<style>
  /* Dark professional theme */
  .stApp { background-color: #0f1117; }
  
  section[data-testid="stSidebar"] {
    background-color: #1a1f2e;
    border-right: 1px solid #2d3748;
  }

  .chat-bubble-user {
    background: #1e3a5f;
    border-radius: 12px 12px 2px 12px;
    padding: 12px 16px;
    margin: 8px 0;
    color: #e2e8f0;
    font-size: 0.92rem;
  }

  .chat-bubble-ai {
    background: #1a2535;
    border: 1px solid #2d4a6e;
    border-radius: 12px 12px 12px 2px;
    padding: 14px 16px;
    margin: 8px 0;
    color: #e2e8f0;
    font-size: 0.92rem;
  }

  .intent-badge {
    display: inline-block;
    padding: 3px 10px;
    border-radius: 12px;
    font-size: 0.72rem;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.5px;
    margin-bottom: 8px;
  }
  .intent-how_to   { background:#1a3a2a; color:#4ade80; border:1px solid #4ade80; }
  .intent-analytics { background:#1a2a3a; color:#63b3ed; border:1px solid #63b3ed; }
  .intent-policy   { background:#2a1a3a; color:#a78bfa; border:1px solid #a78bfa; }
  .intent-blocked  { background:#3a1a1a; color:#f87171; border:1px solid #f87171; }

  .citation-card {
    background: #12192a;
    border: 1px solid #2d3748;
    border-left: 3px solid #3b82f6;
    border-radius: 6px;
    padding: 8px 12px;
    margin: 4px 0;
    font-size: 0.78rem;
    color: #94a3b8;
  }

  .confidence-bar {
    height: 6px;
    border-radius: 3px;
    background: #2d3748;
    margin: 6px 0 12px 0;
  }

  .metric-card {
    background: #1a2035;
    border: 1px solid #2d3748;
    border-radius: 8px;
    padding: 14px;
    text-align: center;
  }

  div[data-testid="stChatInput"] textarea {
    background-color: #1a2035 !important;
    color: #e2e8f0 !important;
    border: 1px solid #3b82f6 !important;
    border-radius: 10px !important;
  }
</style>
""", unsafe_allow_html=True)


# ── Session state init ────────────────────────────────────────────────────────
def init_state():
    defaults = {
        "token": None,
        "username": None,
        "role": None,
        "messages": [],
        "session_id": None,
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v

init_state()


# ── API helpers ───────────────────────────────────────────────────────────────
def api_login(username: str, password: str) -> dict | None:
    try:
        r = requests.post(f"{API_BASE}/auth/login",
                          json={"username": username, "password": password},
                          timeout=10)
        if r.status_code == 200:
            return r.json()
        return None
    except Exception as e:
        st.error(f"Connection error: {e}")
        return None


def api_query(query: str, token: str, session_id: str) -> dict | None:
    try:
        r = requests.post(
            f"{API_BASE}/query",
            json={"query": query, "session_id": session_id},
            headers={"Authorization": f"Bearer {token}"},
            timeout=60,
        )
        if r.status_code == 200:
            return r.json()
        st.error(f"API error {r.status_code}: {r.text}")
        return None
    except Exception as e:
        st.error(f"Request failed: {e}")
        return None


def api_stats(token: str) -> dict | None:
    try:
        r = requests.get(f"{API_BASE}/stats",
                         headers={"Authorization": f"Bearer {token}"},
                         timeout=10)
        return r.json() if r.status_code == 200 else None
    except Exception:
        return None


# ── Login screen ──────────────────────────────────────────────────────────────
def show_login():
    col1, col2, col3 = st.columns([1, 1.2, 1])
    with col2:
        st.markdown("<br><br>", unsafe_allow_html=True)
        st.markdown("## 🤖 Helpdesk Copilot")
        st.markdown("*Enterprise GenAI — Powered by RAG*")
        st.markdown("<br>", unsafe_allow_html=True)

        with st.form("login_form"):
            username = st.text_input("Username", placeholder="agent001")
            password = st.text_input("Password", type="password", placeholder="••••••••")
            submitted = st.form_submit_button("Sign In", use_container_width=True, type="primary")

        if submitted:
            with st.spinner("Authenticating..."):
                result = api_login(username, password)
            if result:
                import uuid
                st.session_state.token      = result["access_token"]
                st.session_state.username   = username
                st.session_state.role       = result["role"]
                st.session_state.session_id = str(uuid.uuid4())
                st.rerun()
            else:
                st.error("Invalid credentials. Try: admin/admin123 or agent001/agent123")

        st.markdown("<br>", unsafe_allow_html=True)
        st.caption("Demo credentials — admin / admin123 · agent001 / agent123")


# ── Sidebar ───────────────────────────────────────────────────────────────────
def show_sidebar():
    with st.sidebar:
        st.markdown(f"### 🤖 Helpdesk Copilot")
        st.markdown(f"**User:** {st.session_state.username}")
        st.markdown(f"**Role:** `{st.session_state.role}`")
        st.divider()

        # Sample queries
        st.markdown("**💡 Try these queries:**")
        sample_queries = [
            "How do I fix VPN authentication failures?",
            "What is the SLA for P1 critical tickets?",
            "How many tickets breached SLA this month?",
            "Which category has the most open tickets?",
            "How do I reset a locked account?",
            "Show top 5 ticket categories by volume",
        ]
        for q in sample_queries:
            if st.button(q, use_container_width=True, key=f"sq_{q[:20]}"):
                st.session_state["prefill_query"] = q
                st.rerun()

        st.divider()

        # Stats panel
        if st.session_state.role in ["admin", "agent"]:
            st.markdown("**📊 Live Stats**")
            stats = api_stats(st.session_state.token)
            if stats:
                col1, col2 = st.columns(2)
                col1.metric("Queries", stats.get("total_queries", 0))
                col2.metric("Avg Conf.", f"{stats.get('avg_confidence', 0):.0%}")

                breakdown = stats.get("intent_breakdown", {})
                if breakdown:
                    st.caption("Intent breakdown:")
                    for intent, count in breakdown.items():
                        st.caption(f"  {intent}: {count}")

        st.divider()

        # Admin: KB ingestion
        if st.session_state.role == "admin":
            st.markdown("**⚙️ Admin**")
            if st.button("🔄 Re-ingest KB", use_container_width=True):
                with st.spinner("Ingesting KB articles..."):
                    r = requests.post(
                        f"{API_BASE}/ingest",
                        headers={"Authorization": f"Bearer {st.session_state.token}"},
                        timeout=120,
                    )
                if r.status_code == 200:
                    d = r.json()
                    st.success(f"✅ {d['chunks_ingested']} chunks ingested")
                else:
                    st.error("Ingestion failed")

        st.divider()
        if st.button("🚪 Sign Out", use_container_width=True):
            for key in ["token", "username", "role", "messages", "session_id"]:
                st.session_state[key] = None if key != "messages" else []
            st.rerun()


# ── Chat message renderer ─────────────────────────────────────────────────────
def render_message(msg: dict):
    if msg["role"] == "user":
        st.markdown(f'<div class="chat-bubble-user">👤 {msg["content"]}</div>',
                    unsafe_allow_html=True)
    else:
        result = msg.get("result", {})
        intent = result.get("intent", "unknown")
        confidence = result.get("confidence", 0)

        intent_html = f'<span class="intent-badge intent-{intent}">{intent.replace("_", " ")}</span>'
        conf_color  = "#4ade80" if confidence > 0.7 else "#f59e0b" if confidence > 0.4 else "#f87171"
        conf_width  = int(confidence * 100)

        st.markdown(f"""
        <div class="chat-bubble-ai">
          {intent_html}
          <div style="color:#94a3b8;font-size:0.75rem;margin-bottom:6px;">
            Confidence: <span style="color:{conf_color}">{confidence:.0%}</span>
            <div class="confidence-bar">
              <div style="width:{conf_width}%;height:100%;background:{conf_color};border-radius:3px;"></div>
            </div>
          </div>
          {result.get("answer", "")}
        </div>
        """, unsafe_allow_html=True)

        # Citations
        citations = result.get("citations", [])
        if citations:
            with st.expander(f"📚 Sources ({len(citations)})", expanded=False):
                for c in citations:
                    st.markdown(
                        f'<div class="citation-card">📄 <b>{c.get("source","Unknown")}</b>'
                        f'<br><span style="color:#718096">{c.get("chunk_preview","")}</span></div>',
                        unsafe_allow_html=True
                    )

        # Data table for analytics results
        data = result.get("data", [])
        if data:
            with st.expander(f"📊 Query Data ({len(data)} rows)", expanded=True):
                df = pd.DataFrame(data)
                st.dataframe(df, use_container_width=True)

            # Show SQL if available
            sql = result.get("sql")
            if sql:
                with st.expander("🔍 Generated SQL", expanded=False):
                    st.code(sql, language="sql")


# ── Main chat interface ───────────────────────────────────────────────────────
def show_chat():
    show_sidebar()

    st.markdown("### 💬 Ask your helpdesk question")
    st.caption("Powered by RAG + NLQ→SQL dual pipeline")
    st.divider()

    # Render chat history
    chat_container = st.container()
    with chat_container:
        for msg in st.session_state.messages:
            render_message(msg)

    # Prefill from sidebar sample buttons
    prefill = st.session_state.pop("prefill_query", "")

    # Chat input
    user_input = st.chat_input(
        "Ask a question... e.g. 'How do I reset VPN?' or 'Show SLA breach trends'",
    )
    if prefill and not user_input:
        user_input = prefill

    if user_input:
        # Add user message
        st.session_state.messages.append({"role": "user", "content": user_input})

        # Query API
        with st.spinner("🤔 Thinking..."):
            start = time.time()
            result = api_query(user_input, st.session_state.token, st.session_state.session_id)
            latency = round(time.time() - start, 2)

        if result:
            st.session_state.messages.append({
                "role":    "assistant",
                "content": result.get("answer", ""),
                "result":  result,
                "latency": latency,
            })

        st.rerun()


# ── Entry point ───────────────────────────────────────────────────────────────
def main():
    if not st.session_state.token:
        show_login()
    else:
        show_chat()


if __name__ == "__main__":
    main()
