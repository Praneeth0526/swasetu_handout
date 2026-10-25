# Seva Setu — Deep Architectural, Security & Agentic Analysis

**Target System:** Sewa Setu Old Age Pension Portal (Purvanchal Department of Social Welfare)  
**Handover Status:** Vendor maintenance expired 31/01/2026. Inherited codebase, ~100k production records, 6 months server logs.

---

## 1. System Architecture & Stack

```
+-----------------------------------------------------------------------------------+
|                                 Docker Compose                                    |
|                                                                                   |
|  +------------------------+      +------------------+      +-------------------+  |
|  |       app (Flask)      | <--> |  db (PostgreSQL) | <--> |     scheduler     |  |
|  |  Gunicorn 4 workers    |      |  ~100k records   |      |   cron nightly    |  |
|  |  Port: 8000 (exposed)  |      |  Port: 5432      |      | deemed_approval.py|  |
|  +------------------------+      +------------------+      +-------------------+  |
|              |                                                                    |
|              v (Reverse Proxy: /__gateway/)                                       |
|  +------------------------+                                                       |
|  |       smsgw (Flask)    |                                                       |
|  |  Simulated Telecom     |                                                       |
|  |  Port: 8025 (internal) |                                                       |
|  +------------------------+                                                       |
+-----------------------------------------------------------------------------------+
```

- **Web Application (`app/`)**:
  - Python 3.11-slim, Flask 2.2.5, Gunicorn 20.1.0 (`--workers 4 --timeout 30`).
  - `psycopg2-binary 2.9.9` (Direct connections per request, no connection pool).
  - `fpdf2 2.7.4` (Synchronous PDF rendering).
  - Session storage: Client-side signed cookies (`app.secret_key = "ssp-prod-key-2023-donotshare"`).
- **Database (`db`)**:
  - PostgreSQL 15 (`postgres:15`).
  - Default connection limits (~100 clients).
  - Schema defines tables `applications`, `portal_users`, `otps`.
- **Scheduled Background Services (`scheduler`)**:
  - Crontab runs `/app/scripts/deemed_approval.py` daily at 02:00 IST.
- **SMS Gateway (`smsgw`)**:
  - Flask web service simulating a carrier telecom SMSC with 1–4s latency.
  - Proxied into the main app at `/__gateway/` and `/__gateway/api/...`.

---

## 2. Database Schema & Data Analysis

### 2.1 Table Definitions
```sql
CREATE TABLE applications (
    id               SERIAL PRIMARY KEY,
    application_no   VARCHAR(20),
    applicant_name   VARCHAR(100),
    mobile           VARCHAR(15),
    dob              DATE,
    gender           VARCHAR(10),
    marital_status   VARCHAR(20),
    husband_name     VARCHAR(100),
    husband_employer VARCHAR(100),
    village          VARCHAR(100),
    block            VARCHAR(50),
    bank_account     VARCHAR(30),
    ifsc             VARCHAR(15),
    doc_path         VARCHAR(200),
    status           VARCHAR(20) DEFAULT 'PENDING',
    submitted_at     TIMESTAMP,
    decided_at       TIMESTAMP,
    decided_by       VARCHAR(50)
);

CREATE TABLE portal_users (
    mobile           VARCHAR(15) PRIMARY KEY,
    password_hash    VARCHAR(80)
);

CREATE TABLE otps (
    id               SERIAL PRIMARY KEY,
    mobile           VARCHAR(15),
    code             VARCHAR(6),
    created_at       TIMESTAMP
);
```

### 2.2 Missing Indexes
- **Zero secondary indexes** exist on `applications`.
- Frequent production queries:
  - `SELECT id FROM applications WHERE mobile = %s ORDER BY submitted_at DESC LIMIT 1` -> **Sequential table scan over 100,000 rows**.
  - `SELECT count(*) FROM applications WHERE status = 'PENDING' AND submitted_at < %s` -> **Sequential table scan**.
  - `SELECT status, count(*) FROM applications GROUP BY status` -> **Sequential scan on every admin dashboard refresh**.
  - `SELECT block, count(*) ... GROUP BY block` -> **Sequential scan**.
  - `SELECT code, created_at FROM otps WHERE mobile = %s ORDER BY id DESC LIMIT 1` -> **Sequential scan on `otps`**.

---

## 3. Comprehensive Vulnerability & Bug Audit

### 3.1 Security Vulnerabilities (Ranked by Severity)

| ID | Vulnerability | Location | Severity | Description & Exploitability |
| :--- | :--- | :--- | :--- | :--- |
| **SEC-01** | **Privilege Escalation on Workflow Decisions** | `app.py:532-558` | **CRITICAL** | `@app.route("/admin/approve/<int:app_id>", methods=["POST"])` only verifies `if not session.get("logged_in"): abort(403)`. It **fails to check `session.get("admin")`**. Any citizen logged into the status portal has `session["logged_in"] = True` and can approve or reject any citizen's pension application. |
| **SEC-02** | **BOLA / IDOR on Citizen Records** | `app.py:406-420` | **CRITICAL** | `/application/<int:app_id>` only checks `logged_in`, but does not verify whether `app_id` belongs to `session["portal_mobile"]`. An authenticated user can enumerate `app_id` 1 to 100,000 to exfiltrate names, mobiles, DOBs, villages, bank accounts, and IFSC codes. |
| **SEC-03** | **Unauthenticated PII Exfiltration via PDF** | `app.py:423-436` | **CRITICAL** | `/ack/<int:app_id>.pdf` has **zero authentication**. Anyone on the public internet can scrape all 100,000 citizen acknowledgment PDFs containing full bank account and personal details. |
| **SEC-04** | **Mass Telemarketing PII Leak via SMS Gateway** | `app.py:115`, `smsgw/app.py:61-76` | **CRITICAL** | `/__gateway/` is exposed without auth. Calling `/__gateway/api/messages` without parameters returns the complete message history of all OTPs and submissions, exposing citizen phone numbers, application numbers, and plain-text passwords (DOBs). Directly explains the DC's note about unsolicited sales calls. |
| **SEC-05** | **SQL Injection in Password Reset** | `app.py:446-454` | **HIGH** | `reset_password()` executes `cur.execute("SELECT mobile FROM portal_users WHERE mobile = '%s'" % mobile)`. Exploitable via string injection on the mobile input parameter. |
| **SEC-06** | **Default / Hardcoded Credentials & Secret Keys** | `app.py:33-35`, `app.ini` | **HIGH** | Admin login hardcoded as `admin` / `sewasetu@123`. Flask `secret_key` hardcoded as `ssp-prod-key-2023-donotshare` in `app.ini`. Database password hardcoded in compose. |
| **SEC-07** | **Insecure Password Derivation** | `app.py:318` | **MEDIUM** | Citizen password is set to date of birth (`DDMMYYYY`). With public DOB leaks from IDOR, accounts are easily hijacked. |
| **SEC-08** | **Missing CSRF Protection** | All routes | **MEDIUM** | State mutations (`/admin/approve`, `/admin/reject`, `/status/reset`) lack CSRF tokens, allowing cross-site request forgery. |

---

### 3.2 Reliability, Performance & Statutory Compliance Bugs

| ID | Issue | Location | Impact | Description |
| :--- | :--- | :--- | :--- | :--- |
| **REL-01** | **RTPS Statutory Deemed-Approval Halt** | `scripts/deemed_approval.py:23-25` | **CRITICAL** | Nightly cron job looks for `config/settings.ini`, which was moved to `config/app.ini` in March 2026. Every night since March 15, 2026, the cron job crashes with `FileNotFoundError`. Overdue applications (> 15 days) are never approved, violating the Right to Public Services Act. |
| **REL-02** | **Postgres Connection Starvation** | `app.py:58-65`, logs | **CRITICAL** | `get_db()` creates a raw `psycopg2.connect()` per request without pooling. Under concurrent load (month-end), Postgres hits `max_connections` and throws `FATAL: sorry, too many clients already`. |
| **REL-03** | **PDF DoS Loop Inside Request Handlers** | `app.py:355-358` | **CRITICAL** | `generate_acknowledgment()` contains an absurd loop: `for i in range(0, 2000): pdf.line(...)`. Drawing 4,000 line segments consumes CPU and blocks the Gunicorn worker thread while holding database connections open. |
| **REL-04** | **Unindexed Database Scans** | `schema.sql`, `app.py` | **HIGH** | Full table scans on 100,000 records on every status login, admin list view, and dashboard access cause severe database CPU spikes and request timeouts (rt > 5s in Nginx logs). |

---

### 3.3 Citizen Experience & Inclusivity Bugs ("The Bazaar Tout Trap")

| ID | Issue | Location | Impact | Description |
| :--- | :--- | :--- | :--- | :--- |
| **UX-01** | **Indic Script Corruption & Byte Truncation** | `app.py:68-75`, `341-372` | **CRITICAL** | `sanitize(value, maxlen=20)` slices UTF-8 bytes (`value.encode("utf-8")[:20]`). Since Indic characters take 3 bytes each, names are sliced at 6 characters or cut mid-character. Furthermore, `FPDF` uses standard `Helvetica`, which cannot render Unicode Indic scripts (Assamese, Bengali, Devanagari), producing `????`. |
| **UX-02** | **False Upload Constraints & Cryptic Error Code** | `app.py:221-225`, `upload.html:6` | **HIGH** | `upload.html` promises: *"Accepted formats: JPG or PDF, maximum size 5 MB"*. But `app.py` rejects non-PDFs and files over 100KB (102,400 bytes) with a cryptic `ERR_VAL_47` flash message. |
| **UX-03** | **Hostile Mandatory Fields for Widows** | `app.py:267-271`, `form_step1.html` | **HIGH** | If `marital_status == "Widowed"`, the server strictly requires `husband_employer` and `husband_name`. If left blank, it flashes "Something went wrong" and redirects to Step 1 without explanation. Bazaar touts charge fees to supply dummy text. |
| **UX-04** | **Fragile / Ambiguous Date Parsing** | `app.py:274-279` | **HIGH** | `for fmt in ("%m/%d/%Y", "%d/%m/%Y"):` checks US format first. An Indian birthdate `05/06/1950` (5 June) is erroneously parsed as 6 May. ISO format `1950-06-05` fails completely. |
| **UX-05** | **Deadlock on Minor Data Entry Errors** | `app.py:297-302` | **HIGH** | `SELECT count(*) FROM applications WHERE mobile = %s` prevents an applicant from editing or re-applying if they made a mistake in their initial submission. |
| **UX-06** | **Low-Literacy Barrier (Math Captcha)** | `app.py:159-163` | **MEDIUM** | Math CAPTCHA creates unnecessary cognitive friction for elderly citizens and impedes automated assistance. |

---

## 4. Agentic Readiness & Deficits

1. **Absence of Machine-Readable APIs**:
   - Zero REST/JSON APIs exist for application submission, status inquiry, or admin operations. The portal is 100% server-side HTML rendering with multi-step session cookies.
2. **Generic Error Messages**:
   - Flashing *"Something went wrong. Please try again."* provides zero structured feedback to an LLM or autonomous agent attempting to rectify invalid inputs.
3. **Cookie-Based Multi-Step Wizard**:
   - 6 sequential POST/redirect steps requiring cookie jar preservation and stateful redirects.
4. **No MCP Protocol Support**:
   - No Model Context Protocol servers exist for either citizens or administrators.
5. **No Idempotency**:
   - Resubmitting a form on network drop risks duplicate errors or inconsistent session state.
6. **No Safety / Consent Mechanism**:
   - No explicit consent / verification envelope before state-changing mutations.

---

## 5. Prioritization Matrix: The Top 5 Citizen-Impact Fixes

Per the briefing and prompt requirements, we must identify and rank our **Top 5 fixes** by citizen impact with test-driven validation:

```
+----------------------------------------------------------------------------------------------------+
| RANK 1: RTPS Statutory Deemed-Approval Restoration & Backlog Clearance (REL-01)                   |
| Why: Restores lawful pensions to thousands of elderly citizens whose applications crossed the      |
| 15-day statutory SLA without action. Directly resolves the DC's greatest legal liability.         |
+----------------------------------------------------------------------------------------------------+
| RANK 2: Indic Script Integrity & UTF-8 Encoding Fix (UX-01)                                        |
| Why: Halts the truncation and '????' corruption of Assamese, Bengali, and Hindi names. Restores    |
| dignity and legal validity to citizen acknowledgment slips and official records.                   |
+----------------------------------------------------------------------------------------------------+
| RANK 3: Privacy Shield & Access Control: Stop PII Leak & Privilege Escalation (SEC-01..04)         |
| Why: Closes the public SMS gateway leak (stopping telemarketing harassment), eliminates BOLA on    |
| /application/<id> and /ack/<id>.pdf, and secures /admin/approve from unauthorized citizen action.  |
+----------------------------------------------------------------------------------------------------+
| RANK 4: Form Inclusivity: Upload Fix, Widow Logic & Lenient Date Validation (UX-02, 03, 04)       |
| Why: Dismantles the 'Bazaar Tout' exploitation: allows 5MB JPG/PDF uploads, removes absurd        |
| deceased-husband employer requirements for widows, and accepts ISO/standard Indian date formats.  |
+----------------------------------------------------------------------------------------------------+
| RANK 5: Performance Optimization: Connection Pooling, DB Indexes & PDF Unblocking (REL-02..04)    |
| Why: Eliminates month-end server crashes ('FATAL: too many clients') and slow response times,     |
| ensuring the portal survives high-concurrency traffic spikes when citizens need it most.          |
+----------------------------------------------------------------------------------------------------+
```
