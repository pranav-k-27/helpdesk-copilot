"""
Synthetic Data Generator
Creates realistic helpdesk ticket DB + KB articles for demo/testing
Run: python data/generate.py
"""
import sqlite3
import json
import random
from datetime import datetime, timedelta
from pathlib import Path
from faker import Faker

fake = Faker()
random.seed(42)

DATA_DIR = Path("./data")
DATA_DIR.mkdir(exist_ok=True)

# ─── TICKET DATABASE ──────────────────────────────────────────────────────────

CATEGORIES  = ["VPN", "Email", "Hardware", "Software", "Network", "Access", "Printer", "Database"]
PRIORITIES  = ["P1-Critical", "P2-High", "P3-Medium", "P4-Low"]
STATUSES    = ["Open", "In Progress", "Resolved", "Closed"]
DEPARTMENTS = ["IT", "HR", "Finance", "Operations", "Sales", "Legal"]
AGENTS      = [f"agent_{i:03d}" for i in range(1, 21)]

SLA_HOURS   = {"P1-Critical": 4, "P2-High": 8, "P3-Medium": 24, "P4-Low": 72}

ISSUE_TEMPLATES = {
    "VPN":      ["Cannot connect to VPN", "VPN keeps disconnecting", "Slow VPN speeds", "VPN authentication failed"],
    "Email":    ["Email not syncing", "Cannot send attachments", "Outlook crashes on startup", "Missing emails in inbox"],
    "Hardware": ["Laptop not charging", "Screen flickering", "Keyboard keys stuck", "Mouse not responding"],
    "Software": ["Application crashes", "Software license expired", "Cannot install updates", "Application not launching"],
    "Network":  ["No internet connection", "Slow network speeds", "WiFi dropping frequently", "Cannot access shared drive"],
    "Access":   ["Account locked out", "Password reset required", "Cannot access SharePoint", "Two-factor auth failing"],
    "Printer":  ["Printer offline", "Print jobs stuck in queue", "Poor print quality", "Cannot find printer on network"],
    "Database": ["Database connection timeout", "Query running slow", "Cannot access SQL server", "Database backup failed"],
}

def generate_tickets(n: int = 1000):
    db_path = DATA_DIR / "helpdesk.db"
    conn = sqlite3.connect(db_path)
    conn.execute("DROP TABLE IF EXISTS tickets")
    conn.execute("""
        CREATE TABLE tickets (
            ticket_id           TEXT PRIMARY KEY,
            title               TEXT,
            category            TEXT,
            priority            TEXT,
            status              TEXT,
            created_at          DATETIME,
            resolved_at         DATETIME,
            sla_breach          INTEGER,
            agent_id            TEXT,
            department          TEXT,
            resolution_time_hrs REAL,
            customer_rating     INTEGER
        )
    """)

    tickets = []
    for i in range(1, n + 1):
        category   = random.choice(CATEGORIES)
        priority   = random.choices(PRIORITIES, weights=[5, 20, 50, 25])[0]
        status     = random.choices(STATUSES, weights=[15, 20, 40, 25])[0]
        created_at = fake.date_time_between(start_date="-6M", end_date="now")
        sla_limit  = SLA_HOURS[priority]

        resolved_at         = None
        resolution_time_hrs = None
        sla_breach          = 0
        customer_rating     = None

        if status in ["Resolved", "Closed"]:
            # Resolution time — sometimes breaches SLA
            if random.random() < 0.25:  # 25% breach rate
                res_hours = sla_limit * random.uniform(1.1, 3.0)
                sla_breach = 1
            else:
                res_hours = sla_limit * random.uniform(0.1, 0.9)
            resolved_at         = created_at + timedelta(hours=res_hours)
            resolution_time_hrs = round(res_hours, 2)
            customer_rating     = random.choices([1, 2, 3, 4, 5], weights=[5, 8, 15, 35, 37])[0]

        tickets.append((
            f"TKT-{i:05d}",
            random.choice(ISSUE_TEMPLATES[category]),
            category,
            priority,
            status,
            created_at.isoformat(),
            resolved_at.isoformat() if resolved_at else None,
            sla_breach,
            random.choice(AGENTS),
            random.choice(DEPARTMENTS),
            resolution_time_hrs,
            customer_rating,
        ))

    conn.executemany(
        "INSERT INTO tickets VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
        tickets
    )
    conn.commit()
    conn.close()
    print(f"✅ Generated {n} tickets → {db_path}")

# ─── KB DOCUMENTS ─────────────────────────────────────────────────────────────

KB_ARTICLES = [
    {
        "id": "KB-001", "title": "VPN Troubleshooting Guide", "doc_type": "how_to",
        "content": """VPN Troubleshooting Guide

Common Issues and Resolutions:

1. Cannot Connect to VPN
   - Ensure you have a stable internet connection before connecting.
   - Check that the VPN client (Cisco AnyConnect / GlobalProtect) is up to date.
   - Try disconnecting from other VPNs or proxy services.
   - If using MFA, ensure your authenticator app time is synced.
   - Restart the VPN service: Services > Cisco AnyConnect > Restart.

2. VPN Keeps Disconnecting
   - Check network stability — VPN drops often indicate underlying network issues.
   - Set the session timeout in VPN client settings to 8 hours.
   - Disable sleep mode on laptop during VPN sessions.
   - Contact your network team if issue persists beyond 3 reconnect attempts.

3. VPN Authentication Failed
   - Reset your Active Directory password via https://password.internal.com
   - Ensure your account has VPN access rights — check with IT Security.
   - Clear VPN client cache: Settings > Advanced > Clear Cache.

SLA: VPN issues are classified P2-High. Target resolution: 8 hours.
Escalation: If unresolved in 4 hours, escalate to Network Operations team.
"""
    },
    {
        "id": "KB-002", "title": "Password Reset Procedure", "doc_type": "policy",
        "content": """Password Reset Procedure and Policy

Self-Service Reset:
Users can reset their own password via the self-service portal at https://password.internal.com.
Requirements: Must have registered recovery email or phone number.

Helpdesk-Assisted Reset:
1. Verify user identity using employee ID + date of birth.
2. Log the request in the ticketing system with reason code: PASS_RESET.
3. Generate temporary password (8+ chars, mixed case, number, special char).
4. Set "Must change on next login" flag.
5. Notify user via alternate contact channel.

Password Policy:
- Minimum length: 12 characters
- Must include: uppercase, lowercase, number, special character
- Cannot reuse last 10 passwords
- Expires every 90 days
- Lockout threshold: 5 failed attempts → auto-lock for 15 minutes

SLA: Account access issues are P2-High. Resolution within 8 hours.
"""
    },
    {
        "id": "KB-003", "title": "SLA Policy and Escalation Matrix", "doc_type": "policy",
        "content": """Service Level Agreement (SLA) Policy

Priority Definitions and Target Resolution Times:

P1 - Critical: System down, major business impact. Target: 4 hours. Immediate escalation to on-call engineer.
P2 - High: Significant functionality impaired. Target: 8 hours. Escalate if unresolved in 4 hours.
P3 - Medium: Minor functionality issues, workaround available. Target: 24 hours.
P4 - Low: Cosmetic issues, general queries. Target: 72 hours.

Escalation Procedure:
1. At 50% of SLA time: Agent must update ticket with progress note.
2. At 75% of SLA time: Supervisor automatically notified.
3. At 100% of SLA time: Ticket marked SLA_BREACH. Manager alerted.
4. Beyond SLA: Executive report generated daily for all breached tickets.

Customer Communication:
- All tickets must receive initial acknowledgment within 1 hour.
- Status updates every 4 hours for P1, every 8 hours for P2.
- Resolution notification sent within 30 minutes of closure.
"""
    },
    {
        "id": "KB-004", "title": "Email and Outlook Troubleshooting", "doc_type": "how_to",
        "content": """Email and Outlook Troubleshooting Guide

1. Outlook Not Syncing / Emails Not Arriving
   - Check internet connection and Outlook status bar (should show "Connected to Microsoft Exchange").
   - Send/Receive All: Press F9 or go to Send/Receive > Send/Receive All Folders.
   - Clear Outlook cache: File > Account Settings > Data Files > Open File Location > delete .ost file.
   - Restart Outlook in safe mode: Hold Ctrl while opening Outlook.

2. Cannot Send Attachments
   - Check attachment size limit: maximum 25MB per email (internal), 10MB (external).
   - Use SharePoint or OneDrive for large files — share the link instead.
   - Check if the recipient domain is on the blocked list (contact IT Security).

3. Missing Emails
   - Check Junk / Spam folder — emails may be misclassified.
   - Check retention policy: emails older than 3 years may be archived.
   - Search in Outlook All Items: Ctrl+Alt+A to search all folders.
   - Contact IT if email appears to be permanently lost — recovery possible up to 30 days.
"""
    },
    {
        "id": "KB-005", "title": "Hardware Issue Handling Procedure", "doc_type": "policy",
        "content": """Hardware Issue Escalation and Replacement Policy

Laptop and Desktop Issues:
- Software fix attempted first (driver reinstall, OS repair).
- If hardware fault confirmed: issue loaner device within 4 hours for P1/P2.
- Send device to hardware team for repair or replacement within 1 business day.

Screen / Display Issues:
- Check cable connections and display settings before logging hardware fault.
- If screen flickering persists after driver update: escalate to hardware team.

Replacement Policy:
- Devices under 3 years: repaired under warranty.
- Devices 3+ years: replacement evaluated against asset lifecycle policy.
- Approval needed from IT Manager for replacements over $500.

Loaner Device Process:
1. Log ticket with category: Hardware, attach photo of issue if possible.
2. Agent picks up loaner from IT asset room (Cabinet B, Floor 3).
3. Log loaner serial number against employee ID in asset tracker.
4. Return timeline: 5 business days unless device is in repair > 5 days.
"""
    },
    {
    "id": "KB-006",
    "title": "Account Lockout Resolution Guide",
    "doc_type": "how_to",
    "content": """Account Lockout Resolution Guide

Accounts are automatically locked after 5 failed login attempts.

Self-Service Unlock:
- Wait 15 minutes — accounts auto-unlock after the lockout period.
- Use the self-service portal: https://password.internal.com to unlock immediately.

Helpdesk-Assisted Unlock:
1. Verify user identity using employee ID.
2. In Active Directory, go to user account properties.
3. Uncheck 'Account is locked out' checkbox.
4. Ask user to reset password immediately after unlock.
5. Log ticket with reason code: ACCT_UNLOCK.

Common Causes:
- Cached credentials on old device still trying to authenticate.
- Mobile device syncing with old password.
- Shared account being used by multiple people.

Prevention: Enable MFA to reduce lockout risk.
SLA: Account access issues are P2-High, resolved within 8 hours.
"""
},
]

def generate_kb_documents():
    kb_path = DATA_DIR / "kb_articles.json"
    with open(kb_path, "w") as f:
        json.dump(KB_ARTICLES, f, indent=2)
    print(f"✅ Generated {len(KB_ARTICLES)} KB articles → {kb_path}")
    return KB_ARTICLES

if __name__ == "__main__":
    generate_tickets(1000)
    generate_kb_documents()
    print("\n🎉 Synthetic data generation complete!")
    print("   Run 'python data/ingest.py' to embed KB articles into ChromaDB.")
