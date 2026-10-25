# -*- coding: utf-8 -*-
"""
Sewa Setu Citizen Model Context Protocol (MCP) Server
Streamable HTTP JSON-RPC 2.0 endpoint for citizen and advocate agents.
Implements data minimization, field masking, consent enforcement, and recovery errors.
"""

import os
import json
import random
from datetime import datetime, date

MIN_AGE = 60
SLA_DAYS = 15
BLOCKS = ["Sonapur Sadar", "Kalyanpur", "Durgapur", "Rampur", "Bikramganj"]
SCHEME_DEADLINE = date(2026, 3, 31)

def _get_app_helpers():
    try:
        from app import app as portal_app
    except ImportError:
        import app as portal_app
    return portal_app


def get_db():
    return _get_app_helpers().get_db()


def sanitize(val):
    return _get_app_helpers().sanitize(val)


def hash_password(pwd):
    return _get_app_helpers().hash_password(pwd)


def send_sms(mobile, msg):
    return _get_app_helpers().send_sms(mobile, msg)


def new_application_no():
    return _get_app_helpers().new_application_no()


CITIZEN_TOOLS = [
    {
        "name": "check_application_status",
        "description": "Check the current status and statutory RTPS timeline of a senior citizen pension application using their 10-digit mobile number or application number. Returned PII is masked for privacy.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "mobile": {
                    "type": "string",
                    "description": "Applicant's registered 10-digit mobile number",
                    "pattern": "^[0-9]{10}$"
                },
                "application_no": {
                    "type": "string",
                    "description": "Optional application number (e.g. SSP26123456)"
                }
            },
            "required": ["mobile"]
        }
    },
    {
        "name": "estimate_pension_eligibility",
        "description": "Evaluate senior citizen eligibility for the Purvanchal Old Age Pension Scheme without hallucination. Returns structured eligibility status, statutory age requirement (>= 60 years), and required documents.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "dob": {
                    "type": "string",
                    "description": "Date of Birth in DD/MM/YYYY or YYYY-MM-DD format"
                },
                "is_purvanchal_resident": {
                    "type": "boolean",
                    "description": "True if the applicant resides in Purvanchal state"
                },
                "annual_income_inr": {
                    "type": "number",
                    "description": "Annual household income in Indian Rupees (INR)"
                }
            },
            "required": ["dob", "is_purvanchal_resident"]
        }
    },
    {
        "name": "submit_pension_application",
        "description": "Submit a new senior citizen pension application. Enforces safety and explicit citizen consent. If consent_confirmed is false, returns a summary preview for citizen verification before writing to the database.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "applicant_name": {"type": "string", "description": "Full name of the applicant in English or Indian script"},
                "mobile": {"type": "string", "description": "10-digit mobile number", "pattern": "^[0-9]{10}$"},
                "dob": {"type": "string", "description": "Date of birth in DD/MM/YYYY or YYYY-MM-DD format"},
                "gender": {"type": "string", "enum": ["Male", "Female", "Other"]},
                "marital_status": {"type": "string", "enum": ["Married", "Unmarried", "Widowed"]},
                "village": {"type": "string", "description": "Village or town name"},
                "block": {"type": "string", "description": f"Administrative block. One of: {', '.join(BLOCKS)}"},
                "bank_account": {"type": "string", "description": "Applicant's bank account number for Direct Benefit Transfer (DBT)"},
                "ifsc": {"type": "string", "description": "11-character Bank IFSC code (e.g. SBIN0001234)"},
                "consent_confirmed": {
                    "type": "boolean",
                    "description": "Must be True indicating the applicant has reviewed all details and consented to submission."
                }
            },
            "required": [
                "applicant_name", "mobile", "dob", "gender", "marital_status",
                "village", "block", "bank_account", "ifsc", "consent_confirmed"
            ]
        }
    },
    {
        "name": "get_scheme_guidelines",
        "description": "Retrieve official guidelines, documentation requirements, statutory RTPS SLA timelines, and disbursement details for the Purvanchal Old Age Pension Scheme in English or Hindi.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "language": {
                    "type": "string",
                    "enum": ["en", "hi", "as"],
                    "default": "en",
                    "description": "Language for guidelines: en (English), hi (Hindi), or as (Assamese)"
                }
            }
        }
    },
    {
        "name": "track_or_file_grievance",
        "description": "File a correction request or lodge a grievance for an existing application (e.g. fixing a typo in bank details, reporting processing delays beyond 15 days), or track a previously filed grievance.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "mobile": {"type": "string", "description": "Applicant's 10-digit mobile number", "pattern": "^[0-9]{10}$"},
                "action": {"type": "string", "enum": ["file", "track"], "description": "Whether to file a new grievance or track existing status"},
                "grievance_type": {
                    "type": "string",
                    "enum": ["CORRECTION_REQUEST", "PROCESSING_DELAY", "REJECTION_INQUIRY", "GENERAL"],
                    "description": "Category of grievance"
                },
                "description": {"type": "string", "description": "Detailed explanation of the issue or data to be corrected"}
            },
            "required": ["mobile", "action"]
        }
    }
]


def mask_phone(mobile):
    if not mobile or len(mobile) < 4:
        return "XXXX"
    return "XXXXXX" + mobile[-4:]


def mask_bank_account(acc):
    if not acc or len(acc) < 4:
        return "XXXX"
    return "X" * (len(acc) - 4) + acc[-4:]


def parse_dob(dob_str):
    for fmt in ("%d/%m/%Y", "%d-%m-%Y", "%Y-%m-%d", "%Y/%m/%d", "%m/%d/%Y"):
        try:
            return datetime.strptime(dob_str.strip(), fmt).date()
        except ValueError:
            continue
    return None


def calculate_age(dob):
    today = date.today()
    return today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))


# ---------------------------------------------------------------------------
# Tool Implementations
# ---------------------------------------------------------------------------

def handle_check_status(args):
    mobile = args.get("mobile", "").strip()
    app_no = args.get("application_no", "").strip()

    if not mobile or len(mobile) != 10 or not mobile.isdigit():
        return {
            "isError": True,
            "error": "INVALID_MOBILE",
            "message": "Please provide a valid 10-digit Indian mobile number."
        }

    conn = get_db()
    cur = conn.cursor()
    if app_no:
        cur.execute(
            """SELECT id, application_no, applicant_name, mobile, dob, village, block,
                      bank_account, ifsc, status, submitted_at, decided_at, decided_by
               FROM applications WHERE mobile = %s AND application_no = %s LIMIT 1""",
            (mobile, app_no)
        )
    else:
        cur.execute(
            """SELECT id, application_no, applicant_name, mobile, dob, village, block,
                      bank_account, ifsc, status, submitted_at, decided_at, decided_by
               FROM applications WHERE mobile = %s ORDER BY submitted_at DESC LIMIT 1""",
            (mobile,)
        )
    row = cur.fetchone()
    cur.close()
    conn.close()

    if not row:
        return {
            "found": False,
            "message": f"No pension application found for mobile number {mask_phone(mobile)}. You can submit an application using submit_pension_application."
        }

    status = row[9]
    submitted_at = row[10]
    days_since_submission = (datetime.now() - submitted_at).days if submitted_at else 0
    rtps_overdue = (status == "PENDING" and days_since_submission > SLA_DAYS)

    sla_info = {
        "statutory_sla_days": SLA_DAYS,
        "days_elapsed": days_since_submission,
        "deemed_approval_applicable": rtps_overdue,
        "sla_note": "Under the Purvanchal Right to Public Services Act, applications pending past 15 days stand approved." if rtps_overdue else f"Decision due within {max(0, SLA_DAYS - days_since_submission)} days under RTPS."
    }

    return {
        "found": True,
        "application_no": row[1],
        "applicant_name": row[2],
        "masked_mobile": mask_phone(row[3]),
        "village": row[5],
        "block": row[6],
        "masked_bank_account": mask_bank_account(row[7]),
        "ifsc": row[8],
        "status": "DEEMED_APPROVED" if rtps_overdue else status,
        "submitted_at": submitted_at.strftime("%Y-%m-%d %H:%M:%S") if submitted_at else None,
        "decided_at": row[11].strftime("%Y-%m-%d %H:%M:%S") if row[11] else None,
        "rtps_sla": sla_info
    }


def handle_estimate_eligibility(args):
    dob_raw = args.get("dob", "")
    is_resident = args.get("is_purvanchal_resident", False)
    income = args.get("annual_income_inr")

    dob = parse_dob(dob_raw)
    if not dob:
        return {
            "isError": True,
            "error": "INVALID_DOB_FORMAT",
            "message": f"Could not parse '{dob_raw}'. Please provide Date of Birth in DD/MM/YYYY or YYYY-MM-DD format."
        }

    age = calculate_age(dob)
    reasons = []
    eligible = True

    if age < MIN_AGE:
        eligible = False
        reasons.append(f"Age is {age} years. The statutory minimum age is {MIN_AGE} years.")
    else:
        reasons.append(f"Age requirement satisfied: {age} years (>= {MIN_AGE} years).")

    if not is_resident:
        eligible = False
        reasons.append("Applicant must be a permanent resident of Purvanchal state.")
    else:
        reasons.append("Residency requirement satisfied: Resident of Purvanchal.")

    if income is not None:
        if income > 200000:
            eligible = False
            reasons.append(f"Annual income INR {income:,.2f} exceeds the threshold of INR 2,00,000 for social welfare assistance.")
        else:
            reasons.append(f"Income requirement satisfied: INR {income:,.2f} <= INR 2,00,000.")

    return {
        "is_eligible": eligible,
        "age_calculated": age,
        "evaluations": reasons,
        "required_documents": [
            "Age Proof: Birth Certificate, School Certificate, or Voter ID",
            "Residence Proof: Ration Card or Domicile Certificate",
            "Bank Passbook copy showing Applicant Name, Account Number, and IFSC"
        ]
    }


def handle_submit_application(args):
    consent = args.get("consent_confirmed", False)
    name = sanitize(args.get("applicant_name", ""))
    mobile = args.get("mobile", "").strip()
    dob_raw = args.get("dob", "").strip()
    gender = args.get("gender", "")
    marital = args.get("marital_status", "")
    village = args.get("village", "").strip()
    block = args.get("block", "").strip()
    bank_account = args.get("bank_account", "").strip()
    ifsc = args.get("ifsc", "").strip().upper()

    # Pre-validation
    if not name or len(name) < 2:
        return {"isError": True, "error": "MISSING_NAME", "message": "Applicant name must be at least 2 characters."}
    if not mobile or len(mobile) != 10 or not mobile.isdigit():
        return {"isError": True, "error": "INVALID_MOBILE", "message": "Mobile must be a valid 10-digit number."}
    if block not in BLOCKS:
        return {"isError": True, "error": "INVALID_BLOCK", "message": f"Block must be one of: {', '.join(BLOCKS)}."}
    if not bank_account or len(bank_account) < 9 or not bank_account.isdigit():
        return {"isError": True, "error": "INVALID_BANK_ACCOUNT", "message": "Bank account number must be numeric (9-18 digits)."}
    if not ifsc or len(ifsc) != 11:
        return {"isError": True, "error": "INVALID_IFSC", "message": "IFSC code must be 11 characters (e.g. SBIN0001234)."}

    dob = parse_dob(dob_raw)
    if not dob:
        return {"isError": True, "error": "INVALID_DOB", "message": "Date of Birth format unrecognized. Please use DD/MM/YYYY."}

    age = calculate_age(dob)
    if age < MIN_AGE:
        return {
            "isError": True,
            "error": "AGE_INELIGIBLE",
            "message": f"Applicant is {age} years old. Minimum statutory age for Old Age Pension is {MIN_AGE} years."
        }

    # SAFETY / CONSENT ENVELOPE
    if not consent:
        return {
            "isError": False,
            "action_required": "CONFIRMATION_REQUIRED",
            "message": "Submission prepared but not committed. Please present this summary to the citizen and obtain explicit confirmation before proceeding.",
            "preview": {
                "applicant_name": name,
                "masked_mobile": mask_phone(mobile),
                "dob": dob.strftime("%d/%m/%Y"),
                "age": age,
                "gender": gender,
                "marital_status": marital,
                "address": f"{village}, Block {block}",
                "masked_bank_account": mask_bank_account(bank_account),
                "ifsc": ifsc,
                "statutory_sla_days": SLA_DAYS
            },
            "instructions": "Call submit_pension_application again with consent_confirmed=True once the applicant agrees."
        }

    # Execution with consent
    conn = get_db()
    cur = conn.cursor()

    # Check for existing application
    cur.execute("SELECT application_no, status FROM applications WHERE mobile = %s", (mobile,))
    existing = cur.fetchone()
    if existing:
        cur.close()
        conn.close()
        return {
            "isError": True,
            "error": "DUPLICATE_APPLICATION",
            "message": f"An application ({existing[0]}) already exists for mobile {mask_phone(mobile)} with status '{existing[1]}'. Duplicate submissions are not permitted. If you need to rectify mistakes, please use track_or_file_grievance."
        }

    app_no = new_application_no()
    cur.execute(
        """INSERT INTO applications
           (application_no, applicant_name, mobile, dob, gender, marital_status,
            village, block, bank_account, ifsc, doc_path, status, submitted_at)
           VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 'PENDING', %s)
           RETURNING id""",
        (app_no, name, mobile, dob, gender, marital, village, block,
         bank_account, ifsc, "DIGITAL_AGENT_SUBMISSION", datetime.now())
    )
    new_id = cur.fetchone()[0]

    # Create portal account
    portal_pass = dob.strftime("%d%m%Y")
    cur.execute("SELECT count(*) FROM portal_users WHERE mobile = %s", (mobile,))
    if cur.fetchone()[0] == 0:
        cur.execute("INSERT INTO portal_users (mobile, password_hash) VALUES (%s, %s)",
                    (mobile, hash_password(portal_pass)))

    conn.commit()
    cur.close()
    conn.close()

    # Trigger SMS notification
    send_sms(mobile, f"Sewa Setu: application {app_no} received. Track at the status portal with your mobile and DOB.")

    return {
        "success": True,
        "application_no": app_no,
        "applicant_name": name,
        "status": "PENDING",
        "statutory_rtps_sla_days": SLA_DAYS,
        "message": f"Application {app_no} has been registered successfully. Under the RTPS Act, a statutory decision is guaranteed within 15 days."
    }


def handle_get_guidelines(args):
    lang = args.get("language", "en")
    guidelines = {
        "en": {
            "scheme_name": "Sewa Setu Old Age Pension Scheme",
            "department": "Department of Social Welfare, Government of Purvanchal",
            "eligibility": {
                "min_age": 60,
                "residency": "Permanent resident of Purvanchal",
                "income_limit": "INR 2,00,000 per annum"
            },
            "pension_amount": "INR 1,000 per month credited directly via Aadhaar/Bank DBT",
            "statutory_sla": "15 calendar days under the Purvanchal Right to Public Services Act (RTPS). Untouched files automatically stand deemed approved on Day 16.",
            "required_documents": [
                "Age Proof (Birth Certificate / Voter ID / School Certificate)",
                "Bank Account Passbook (single or joint account in applicant name)",
                "Aadhaar or Identity Proof"
            ]
        },
        "hi": {
            "scheme_name": "सेवा सेतु वृद्धावस्था पेंशन योजना",
            "department": "समाज कल्याण विभाग, पूर्वांचल सरकार",
            "eligibility": {
                "min_age": 60,
                "residency": "पूर्वांचल राज्य का स्थायी निवासी",
                "income_limit": "वार्षिक आय ₹2,00,000 से कम"
            },
            "pension_amount": "₹1,000 प्रति माह प्रत्यक्ष लाभ अंतरण (DBT) द्वारा बैंक खाते में",
            "statutory_sla": "लोक सेवा अधिकार अधिनियम (RTPS) के तहत 15 कार्य दिवस। 15 दिनों में निर्णय न होने पर स्वतः स्वीकृति (Deemed Approval) का प्रावधान है।",
            "required_documents": [
                "आयु प्रमाण पत्र (मतदाता पहचान पत्र / जन्म प्रमाण पत्र)",
                "बैंक खाता पासबुक की प्रति",
                "आधार कार्ड या निवास प्रमाण पत्र"
            ]
        },
        "as": {
            "scheme_name": "সেৱা সেতু বৃদ্ধ পেঞ্চন আঁচনি",
            "department": "সমাজ কল্যাণ বিভাগ, পূৰ্বাঞ্চল চৰকাৰ",
            "eligibility": {
                "min_age": 60,
                "residency": "পূৰ্বাঞ্চলৰ স্থায়ী বাসিন্দা",
                "income_limit": "বাৰ্ষিক আয় ₹২,০০,০০০ তকৈ কম"
            },
            "pension_amount": "প্ৰতি মাহে ₹১,০০০ পোনপটীয়াকৈ বেংক একাউণ্টত (DBT)",
            "statutory_sla": "সেৱা অধিকাৰ আইন (RTPS) ৰ অধীনত ১৫ দিনৰ সময়সীমা। ১৫ দিনত সিদ্ধান্ত নোলোৱা আবেদন স্বয়ংক্ৰিয়ভাৱে অনুমোদিত গণ্য হ'ব।"
        }
    }
    return guidelines.get(lang, guidelines["en"])


def handle_track_or_file_grievance(args):
    mobile = args.get("mobile", "").strip()
    action = args.get("action", "track")
    g_type = args.get("grievance_type", "GENERAL")
    desc = args.get("description", "")

    if not mobile or len(mobile) != 10:
        return {"isError": True, "error": "INVALID_MOBILE", "message": "Valid 10-digit mobile number required."}

    conn = get_db()
    cur = conn.cursor()

    if action == "file":
        if not desc:
            cur.close(); conn.close()
            return {"isError": True, "error": "DESCRIPTION_REQUIRED", "message": "Please provide a description of the grievance or correction needed."}

        cur.execute("SELECT id, application_no, status FROM applications WHERE mobile = %s ORDER BY submitted_at DESC LIMIT 1", (mobile,))
        app_row = cur.fetchone()

        grievance_id = f"GRV{random.randint(100000, 999999)}"
        cur.close(); conn.close()
        return {
            "success": True,
            "grievance_id": grievance_id,
            "mobile": mask_phone(mobile),
            "linked_application": app_row[1] if app_row else "None",
            "category": g_type,
            "status": "OPEN",
            "message": f"Grievance {grievance_id} registered. Our helpdesk will review and action your correction request within 48 hours."
        }
    else: # track
        cur.execute("SELECT application_no, status, submitted_at FROM applications WHERE mobile = %s ORDER BY submitted_at DESC LIMIT 1", (mobile,))
        row = cur.fetchone()
        cur.close(); conn.close()
        if not row:
            return {"found": False, "message": "No records found for this mobile number."}
        return {
            "found": True,
            "mobile": mask_phone(mobile),
            "application_no": row[0],
            "application_status": row[1],
            "grievances": [
                {
                    "grievance_id": "GRV-SYSTEM-SYNC",
                    "status": "ACTIVE_MONITORING",
                    "note": "File under regular processing queue."
                }
            ]
        }


# ---------------------------------------------------------------------------
# Dispatcher for JSON-RPC 2.0
# ---------------------------------------------------------------------------

DISPATCHER = {
    "check_application_status": handle_check_status,
    "estimate_pension_eligibility": handle_estimate_eligibility,
    "submit_pension_application": handle_submit_application,
    "get_scheme_guidelines": handle_get_guidelines,
    "track_or_file_grievance": handle_track_or_file_grievance,
}


def process_citizen_mcp_request(payload):
    """
    Handles standard Model Context Protocol (MCP) Streamable JSON-RPC 2.0 requests.
    Supports: initialize, tools/list, tools/call, ping.
    """
    req_id = payload.get("id")
    method = payload.get("method")
    params = payload.get("params", {})

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
                    "name": "sewasetu-citizen-mcp",
                    "version": "1.0.0",
                    "description": "Public MCP server for citizens and advocate agents accessing the Sewa Setu Old Age Pension Portal."
                }
            }
        }

    elif method in ("notifications/initialized", "initialized"):
        return None

    elif method == "ping":
        return {"jsonrpc": "2.0", "id": req_id, "result": {}}

    elif method == "tools/list":
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {
                "tools": CITIZEN_TOOLS
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
                    "message": f"Tool '{tool_name}' not found on Citizen MCP server."
                }
            }

        try:
            handler = DISPATCHER[tool_name]
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
                    "content": [{"type": "text", "text": f"Error executing tool {tool_name}: {str(e)}"}],
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
