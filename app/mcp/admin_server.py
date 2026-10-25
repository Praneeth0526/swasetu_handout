# -*- coding: utf-8 -*-
"""
Sewa Setu Administrator Model Context Protocol (MCP) Server
Streamable HTTP JSON-RPC 2.0 endpoint for verified department officers and assessors.
Enforces strict bearer token authentication, audit logs, and human-in-the-loop decisions.
"""

import os
import json
import base64
from datetime import datetime, timedelta

SLA_DAYS = 15
BLOCKS = ["Sonapur Sadar", "Kalyanpur", "Durgapur", "Rampur", "Bikramganj"]

def _get_app_helpers():
    try:
        from app import app as portal_app
    except ImportError:
        import app as portal_app
    return portal_app

def get_db():
    return _get_app_helpers().get_db()

def send_sms(mobile, msg):
    return _get_app_helpers().send_sms(mobile, msg)

def get_admin_creds():
    helpers = _get_app_helpers()
    admin_pwd = getattr(helpers, "ADMIN_PASSWORD", "sewasetu@123")
    assessor_pwd = getattr(helpers, "ASSESSOR_PASSWORD", "Purvanchal@Assess2027")
    return admin_pwd, assessor_pwd

from app.scripts.deemed_approval import process_deemed_approvals

ADMIN_TOOLS = [
    {
        "name": "list_pending_applications",
        "description": "List pension applications currently in PENDING review status across Sonapur district, with flags for statutory RTPS SLA overdues (> 15 days). Filterable by administrative block.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "block": {
                    "type": "string",
                    "description": f"Filter by administrative block: {', '.join(BLOCKS)}"
                },
                "overdue_only": {
                    "type": "boolean",
                    "description": "If true, only returns applications pending past the 15-day statutory SLA window."
                },
                "limit": {
                    "type": "integer",
                    "default": 20,
                    "description": "Number of records to return (max 100)"
                },
                "offset": {
                    "type": "integer",
                    "default": 0,
                    "description": "Pagination offset"
                }
            }
        }
    },
    {
        "name": "get_application_details",
        "description": "Retrieve full, unmasked administrative details of an application including KYC data, bank credentials, uploaded documents, and chronological timeline.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "application_id": {
                    "type": "integer",
                    "description": "Internal database application ID"
                },
                "application_no": {
                    "type": "string",
                    "description": "Official application number (e.g. SSP26123456)"
                }
            }
        }
    },
    {
        "name": "review_application",
        "description": "Record an official administrative decision (APPROVED or REJECTED) on a pending pension application. Enforces mandatory human-in-the-loop justification for the state audit log.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "application_id": {
                    "type": "integer",
                    "description": "Application ID to approve or reject"
                },
                "decision": {
                    "type": "string",
                    "enum": ["APPROVED", "REJECTED"],
                    "description": "Decision outcome"
                },
                "justification": {
                    "type": "string",
                    "description": "Statutory audit justification or reason for rejection/approval"
                }
            },
            "required": ["application_id", "decision", "justification"]
        }
    },
    {
        "name": "run_rtps_deemed_approval_batch",
        "description": "Trigger the statutory Right to Public Services Act (RTPS) deemed-approval sweep. Automatically transitions all applications pending > 15 days to DEEMED_APPROVED and dispatches citizen SMS notifications.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "dry_run": {
                    "type": "boolean",
                    "default": False,
                    "description": "If true, reports how many applications would be auto-approved without committing changes."
                }
            }
        }
    },
    {
        "name": "get_district_dashboard_metrics",
        "description": "Retrieve aggregated district-wide operational statistics: total applications, status breakdowns, overdue RTPS cases, and block-by-block distribution.",
        "inputSchema": {
            "type": "object",
            "properties": {}
        }
    }
]


def verify_admin_token(token):
    """Verify that the provided token matches admin or assessor secret."""
    if not token:
        return False, None
    token = token.strip()
    admin_pwd, assessor_pwd = get_admin_creds()

    if token.startswith("Bearer "):
        token = token[7:].strip()
    elif token.startswith("Basic "):
        try:
            decoded = base64.b64decode(token[6:].strip()).decode("utf-8")
            parts = decoded.split(":", 1)
            if len(parts) == 2:
                user, pwd = parts
                if user == "admin" and pwd == admin_pwd:
                    return True, "admin"
                if user == "assessor_admin" and pwd == assessor_pwd:
                    return True, "assessor_admin"
            token = parts[-1]
        except Exception:
            pass

    valid_tokens = {
        admin_pwd: "admin",
        assessor_pwd: "assessor_admin",
        os.environ.get("ADMIN_BEARER_TOKEN", ""): "bearer_admin"
    }
    # Remove empty string keys
    valid_tokens.pop("", None)

    if token in valid_tokens:
        return True, valid_tokens[token]
    return False, None


# ---------------------------------------------------------------------------
# Tool Handlers
# ---------------------------------------------------------------------------

def handle_list_pending(args):
    block = args.get("block")
    overdue_only = args.get("overdue_only", False)
    limit = min(100, max(1, int(args.get("limit", 20))))
    offset = max(0, int(args.get("offset", 0)))

    conn = get_db()
    cur = conn.cursor()

    query = """
        SELECT id, application_no, applicant_name, mobile, block, village, submitted_at,
               ROUND(EXTRACT(EPOCH FROM (NOW() - submitted_at)) / 86400) as days_pending
        FROM applications
        WHERE status = 'PENDING'
    """
    params = []
    if block:
        query += " AND block = %s"
        params.append(block)
    if overdue_only:
        cutoff = datetime.now() - timedelta(days=SLA_DAYS)
        query += " AND submitted_at < %s"
        params.append(cutoff)

    query += " ORDER BY submitted_at ASC LIMIT %s OFFSET %s"
    params.extend([limit, offset])

    cur.execute(query, tuple(params))
    rows = cur.fetchall()

    results = []
    for r in rows:
        days = int(r[7]) if r[7] is not None else 0
        results.append({
            "id": r[0],
            "application_no": r[1],
            "applicant_name": r[2],
            "mobile": r[3],
            "block": r[4],
            "village": r[5],
            "submitted_at": r[6].strftime("%Y-%m-%d %H:%M:%S") if r[6] else None,
            "days_pending": days,
            "rtps_overdue": days > SLA_DAYS
        })

    cur.close()
    conn.close()

    return {
        "count": len(results),
        "limit": limit,
        "offset": offset,
        "applications": results
    }


def handle_get_details(args):
    app_id = args.get("application_id")
    app_no = args.get("application_no")

    if not app_id and not app_no:
        return {"isError": True, "error": "ARGUMENT_REQUIRED", "message": "Either application_id or application_no must be provided."}

    conn = get_db()
    cur = conn.cursor()
    if app_id:
        cur.execute(
            """SELECT id, application_no, applicant_name, mobile, dob, gender,
                      marital_status, village, block, bank_account, ifsc, doc_path,
                      status, submitted_at, decided_at, decided_by
               FROM applications WHERE id = %s""",
            (app_id,)
        )
    else:
        cur.execute(
            """SELECT id, application_no, applicant_name, mobile, dob, gender,
                      marital_status, village, block, bank_account, ifsc, doc_path,
                      status, submitted_at, decided_at, decided_by
               FROM applications WHERE application_no = %s""",
            (app_no,)
        )
    row = cur.fetchone()
    cur.close()
    conn.close()

    if not row:
        return {"found": False, "message": "Application record not found."}

    days_pending = (datetime.now() - row[13]).days if row[13] else 0
    return {
        "found": True,
        "id": row[0],
        "application_no": row[1],
        "applicant_name": row[2],
        "mobile": row[3],
        "dob": row[4].strftime("%Y-%m-%d") if row[4] else None,
        "gender": row[5],
        "marital_status": row[6],
        "village": row[7],
        "block": row[8],
        "bank_account": row[9],
        "ifsc": row[10],
        "doc_path": row[11],
        "status": row[12],
        "submitted_at": row[13].strftime("%Y-%m-%d %H:%M:%S") if row[13] else None,
        "decided_at": row[14].strftime("%Y-%m-%d %H:%M:%S") if row[14] else None,
        "decided_by": row[15],
        "rtps_status": {
            "days_elapsed": days_pending,
            "statutory_limit_days": SLA_DAYS,
            "overdue": (row[12] == "PENDING" and days_pending > SLA_DAYS)
        }
    }


def handle_review_application(args, admin_user="admin"):
    app_id = args.get("application_id")
    decision = args.get("decision")
    justification = args.get("justification", "").strip()

    if decision not in ("APPROVED", "REJECTED"):
        return {"isError": True, "error": "INVALID_DECISION", "message": "Decision must be either 'APPROVED' or 'REJECTED'."}
    if not justification or len(justification) < 5:
        return {"isError": True, "error": "JUSTIFICATION_REQUIRED", "message": "State audit trail requires a justification of at least 5 characters."}

    conn = get_db()
    cur = conn.cursor()

    cur.execute("SELECT id, application_no, mobile, status FROM applications WHERE id = %s", (app_id,))
    row = cur.fetchone()
    if not row:
        cur.close(); conn.close()
        return {"isError": True, "error": "NOT_FOUND", "message": f"Application {app_id} does not exist."}

    app_no = row[1]
    mobile = row[2]
    now = datetime.now()

    cur.execute(
        """UPDATE applications
           SET status = %s, decided_at = %s, decided_by = %s
           WHERE id = %s""",
        (decision, now, admin_user, app_id)
    )
    conn.commit()
    cur.close()
    conn.close()

    # Dispatch SMS to citizen
    if decision == "APPROVED":
        send_sms(mobile, f"Sewa Setu: Your pension application {app_no} has been APPROVED by the Department of Social Welfare.")
    else:
        send_sms(mobile, f"Sewa Setu: Your pension application {app_no} could not be approved. Reason: {justification[:60]}")

    return {
        "success": True,
        "application_id": app_id,
        "application_no": app_no,
        "decision": decision,
        "decided_by": admin_user,
        "decided_at": now.strftime("%Y-%m-%d %H:%M:%S"),
        "justification": justification,
        "notification_dispatched": True
    }


def handle_rtps_sweep(args):
    dry_run = args.get("dry_run", False)
    if dry_run:
        conn = get_db()
        cur = conn.cursor()
        cutoff = datetime.now() - timedelta(days=SLA_DAYS)
        cur.execute("SELECT count(*) FROM applications WHERE status = 'PENDING' AND submitted_at < %s", (cutoff,))
        count = cur.fetchone()[0]
        cur.close(); conn.close()
        return {
            "dry_run": True,
            "statutory_sla_days": SLA_DAYS,
            "applications_eligible_for_deemed_approval": count
        }

    count, app_nos = process_deemed_approvals()
    return {
        "success": True,
        "statutory_sla_days": SLA_DAYS,
        "deemed_approved_count": count,
        "processed_applications": app_nos[:50],
        "message": f"RTPS statutory deemed-approval sweep completed. {count} applications transitioned to DEEMED_APPROVED."
    }


def handle_district_metrics(args):
    conn = get_db()
    cur = conn.cursor()

    cur.execute("SELECT status, count(*) FROM applications GROUP BY status")
    by_status = dict(cur.fetchall())

    cutoff = datetime.now() - timedelta(days=SLA_DAYS)
    cur.execute("SELECT count(*) FROM applications WHERE status = 'PENDING' AND submitted_at < %s", (cutoff,))
    overdue_count = cur.fetchone()[0]

    cur.execute("SELECT block, count(*) FROM applications WHERE status = 'PENDING' GROUP BY block ORDER BY count(*) DESC")
    pending_by_block = dict(cur.fetchall())

    cur.close(); conn.close()

    total = sum(by_status.values())
    return {
        "district": "Sonapur",
        "total_applications": total,
        "status_distribution": by_status,
        "rtps_compliance": {
            "statutory_sla_days": SLA_DAYS,
            "pending_overdue_cases": overdue_count,
            "compliance_health": "ACTION_REQUIRED" if overdue_count > 0 else "COMPLIANT"
        },
        "pending_by_block": pending_by_block
    }


DISPATCHER = {
    "list_pending_applications": handle_list_pending,
    "get_application_details": handle_get_details,
    "review_application": handle_review_application,
    "run_rtps_deemed_approval_batch": handle_rtps_sweep,
    "get_district_dashboard_metrics": handle_district_metrics,
}


def log_admin_audit(admin_user, action, target_id=None, details=None):
    """Record administrative MCP action with timestamp and caller ID in audit trail."""
    try:
        conn = get_db()
        cur = conn.cursor()
        cur.execute("""
            CREATE TABLE IF NOT EXISTS admin_audit_log (
                id SERIAL PRIMARY KEY,
                admin_user VARCHAR(50),
                action VARCHAR(50),
                target_id INT,
                details TEXT,
                created_at TIMESTAMP DEFAULT NOW()
            )
        """)
        details_str = json.dumps(details) if isinstance(details, (dict, list)) else str(details or "")
        cur.execute("""
            INSERT INTO admin_audit_log (admin_user, action, target_id, details)
            VALUES (%s, %s, %s, %s)
        """, (admin_user, action, target_id, details_str))
        conn.commit()
        cur.close()
        conn.close()
    except Exception:
        pass


def process_admin_mcp_request(payload, auth_header=None):
    """
    Handles standard Model Context Protocol (MCP) Streamable JSON-RPC 2.0 requests
    for administrative operations. Enforces bearer authentication.
    """
    req_id = payload.get("id")
    method = payload.get("method")
    params = payload.get("params", {})

    # Method initialize
    if method == "initialize":
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {
                "protocolVersion": "2024-11-05",
                "capabilities": {
                    "tools": {"listChanged": False}
                },
                "serverInfo": {
                    "name": "sewasetu-admin-mcp",
                    "version": "1.0.0",
                    "description": "Administrator MCP server for Department officers, audit inspectors, and automated evaluators."
                }
            }
        }

    elif method in ("notifications/initialized", "initialized"):
        return None

    elif method == "ping":
        return {"jsonrpc": "2.0", "id": req_id, "result": {}}

    # Authentication Enforcement for tool listing & execution
    is_valid, admin_user = verify_admin_token(auth_header)
    if not is_valid:
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "error": {
                "code": -32000,
                "message": "Unauthorized: Valid administrator bearer token required for Administrator MCP tools."
            }
        }

    if method == "tools/list":
        log_admin_audit(admin_user, "tools/list")
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {
                "tools": ADMIN_TOOLS
            }
        }

    elif method == "tools/call":
        tool_name = params.get("name")
        args = params.get("arguments", {})

        if tool_name not in DISPATCHER:
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "error": {
                    "code": -32601,
                    "message": f"Tool '{tool_name}' not found on Administrator MCP server."
                }
            }

        target_id = args.get("application_id")
        log_admin_audit(admin_user, tool_name, target_id=target_id, details=args)

        try:
            handler = DISPATCHER[tool_name]
            if tool_name == "review_application":
                result = handler(args, admin_user=admin_user)
            else:
                result = handler(args)

            is_error = result.get("isError", False) if isinstance(result, dict) else False
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "content": [
                        {
                            "type": "text",
                            "text": json.dumps(result, ensure_ascii=False, indent=2)
                        }
                    ],
                    "isError": is_error
                }
            }
        except Exception as e:
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "content": [{"type": "text", "text": f"Error executing administrative tool {tool_name}: {str(e)}"}],
                    "isError": True
                }
            }

    else:
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "error": {
                "code": -32601,
                "message": f"Method '{method}' not implemented."
            }
        }
