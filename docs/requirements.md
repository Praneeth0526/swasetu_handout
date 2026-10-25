# Seva Setu — System Requirements & Ground Truth Matrix

This document maps all explicit requirements, implicit concerns, edge cases, and architectural constraints gathered from:
1. The **Departmental Brief** (`BRIEF.md`)
2. The **Deputy Commissioner's Audio Briefing** (`docs/officer-note.md` / `dc-briefing.mp3`)
3. The **Take-Home Application Specifications & Design Principles** (`<USER_REQUEST>`)

---

## 1. Explicit Requirements

### 1.1 Core Portal Functionality & Fixes
* **Public Deployment & Liveness**:
  > *"Deployed public URL. Our automated assessor completes test applications against it. The SMS gateway is served through your app at `/__gateway/`, so keeping your app reachable is all we need — there is no separate gateway URL or port to expose."* — `BRIEF.md:46-48`
  > *"Liveness — is the app up and serving."* — `BRIEF.md:68`
  - The portal must run with its restored Postgres database (~100,000 citizens) and be accessible via public HTTP.
  - The SMS gateway console and API must remain reverse-proxied at `/__gateway/`.
  - Deployment must remain active and healthy for ~30 days.

* **Top 5 Citizen-Impact Fixes with TDD Commits**:
  > *"Fix as many things as you like — but your reply to the DC (recorded as a Loom) must name your top 5 fixes ranked by citizen impact, with reasons, and their order matters. Each fix needs a test that fails before the fix and passes after it, committed in that order."* — `BRIEF.md:35-38`
  > *"Repository — clones your repo and checks commit history, that tests fail before a fix and pass after..."* — `BRIEF.md:76-77`
  - Exactly 5 primary fixes prioritized by citizen impact.
  - Strict Red-Green TDD commit structure for each fix (test commit failing -> code fix passing).

* **Preserve Production Data**:
  > *"Do not delete or alter existing citizen records except where a fix requires it. This is production data. Treat the people in it accordingly."* — `BRIEF.md:39-40`
  > *"The data — logs in as citizens who existed before you arrived and checks their records are correct now."* — `BRIEF.md:78-79`
  - 100,000 existing records in `applications` and `portal_users` must not be corrupted or wiped.

* **RTPS Statutory Compliance (Right to Public Services Act)**:
  > *"There is the Right to Public Services Act. We call it RTPS. It promises every citizen a decision within a set number of days. And if we stay silent past that window, if we just sit on it, the application is deemed approved... For this scheme, that window is 15 days... Then, around Holi, it just stopped."* — `docs/officer-note.md`
  > *"Under the Purvanchal Right to Public Services Act, an application not processed within the statutory SLA stands approved. This job marks such applications DEEMED_APPROVED and notifies the applicant by SMS."* — `app/scripts/deemed_approval.py:5-7`
  - Overdue applications (> 15 days in `PENDING`) must be transitioned to `DEEMED_APPROVED`.
  - Fix the broken nightly cron execution (which has failed since March 14, 2026 due to `FileNotFoundError: /app/config/settings.ini`).

* **Indian Script & Unicode Integrity**:
  > *"First, an old man walked 2 hours from his village just to show me his acknowledgement slip, and where his name should be, in Assamese, it shows four question marks. Four. He swears he typed it correctly... Others tell me their names come out cut in half..."* — `docs/officer-note.md`
  > *"Data integrity — submits an application (marked with a probe token) with an Indian-language name and reads it back; checks that records are stored faithfully."* — `BRIEF.md:71-72`
  - Portal, database, and PDF generator must correctly ingest, store, display, and render Indic names (Assamese, Bengali, Hindi, Kannada, etc.) without byte truncation or character corruption (`????`).

* **Security & Vulnerability Remediation**:
  > *"Security — attempts the things an attacker would: reading other citizens' data, injection on inputs, default/leaked credentials, acting as staff without authority."* — `BRIEF.md:69-70`
  - Eliminate Broken Object-Level Authorization (BOLA/IDOR) on `/application/<id>` and `/ack/<id>.pdf`.
  - Eliminate SQL Injection on password reset (`/status/reset`).
  - Eliminate unauthorized staff actions / privilege escalation (`/admin/approve/<id>` and `/admin/reject/<id>` only checking `logged_in` rather than `admin`).
  - Eliminate default/leaked admin credentials (`admin / sewasetu@123` and hardcoded secret keys).
  - Stop the massive data leak on `/__gateway/` exposing citizen phone numbers, passwords (DOB), and OTPs.

* **Resilience Under Load**:
  > *"Load — replays a month-end traffic spike and measures whether the service survives."* — `BRIEF.md:75`
  > *"Every month, the two or three days before the disbursement deadline, the whole site crawls to a halt. My staff just shrug. 'Server slowdown hai, sir. Kya karenge?'"* — `docs/officer-note.md`
  - Eradicate connection pool exhaustion (`FATAL: sorry, too many clients already`).
  - Remove synchronous, CPU-intensive loops (2000-line PDF loop inside request handlers).
  - Add missing PostgreSQL indexes on `applications(mobile)`, `applications(status, submitted_at)`, `applications(block)`, etc.

* **Assessor Admin Credentials**:
  > *"Assessor credentials: a working admin login for our assessor. You may rebuild the citizen experience however you like, but keep the admin panel functional — it is how we verify your fixes."* — `BRIEF.md:55-58`
  > *"An assessor admin account (username and password) on the portal. Use a dedicated throwaway credential and document it in a private file."* — `<USER_REQUEST>`

---

### 1.2 Agentic & MCP Deliverables
* **Citizen MCP Server (Streamable Remote HTTP Transport)**:
  > *"Public MCP endpoint for CITIZENS (remote transport, e.g. streamable HTTP, connectable directly by an external agent with no local setup)."* — `<USER_REQUEST>`
  - Must use Remote Streamable HTTP (SSE / Streamable JSON-RPC over HTTP) per standard Model Context Protocol.
  - Accessible publicly over the internet without local dependencies.
  - Strict citizen-level authentication / session scopes.

* **Administrator MCP Server (Streamable Remote HTTP Transport)**:
  > *"Public MCP endpoint for ADMINISTRATORS (same, with admin-level tools)."* — `<USER_REQUEST>`
  - Completely isolated transport endpoint with admin-level authentication.
  - Zero tool leakage between citizen and admin boundaries.

* **Strict Tool Partitioning & Defense-in-Depth**:
  > *"Citizen and admin MCP servers must have strictly separate auth and tool sets. A citizen token must never reach admin tools. Test this explicitly."* — `<USER_REQUEST>`
  > *"Tools should be few, well-named and well-described, with typed inputs, helpful error messages that tell an agent how to recover, and idempotent writes where possible."* — `<USER_REQUEST>`

* **Evaluation Suite & Public Eval Dashboard**:
  > *"Build an eval suite that runs an LLM agent against both MCP endpoints on realistic scenarios: happy paths, ambiguous requests, adversarial and prompt-injection inputs, privilege-escalation attempts, wrong-user data access, and missing or invalid data."* — `<USER_REQUEST>`
  > *"Eval dashboard at a public URL, showing evals I prepared for this project."* — `<USER_REQUEST>`
  - Real evaluations with agent traces, execution graphs, latency, and success/safety metrics.

---

## 2. Implicit Concerns & Ground Realities

### 2.1 Citizen Vulnerability & Intermediary Exploitation
* **Hostile Form Design & "Bazaar Touts"**:
  > *"I keep hearing the new digital form is just not friendly. Some people say they are perfectly eligible, but simply cannot get through it. There are even fellows in the bazaar now who'll fill it out for you for a fee, because only they have figured out how it works."* — `docs/officer-note.md`
  - *Implicit cause*: The form demands `husband_employer` and `husband_name` for all widows (even if deceased decades ago), fails with cryptic errors (`ERR_VAL_47`) if an uploaded document is not a PDF under 100KB (despite the page claiming "JPG or PDF, max 5 MB"), uses rigid/ambiguous date parsing, and returns generic "Something went wrong. Please try again."
  - *Impact*: Vulnerable rural elderly citizens are extorted by CSC / cyber cafe middlemen.

### 2.2 Unsolicited Spam & Telemarketing Calls
* **Privacy Leakage**:
  > *"Meera, my assistant, she says there is a rumor going around that the moment you apply on the portal, you start getting phone calls. Salesmen, people turning up at your door, trying to sell you things. Now, how on earth would that happen?"* — `docs/officer-note.md`
  - *Implicit cause*: `/__gateway/` is completely unauthenticated and streams every SMS broadcast containing citizen names, phone numbers, application IDs, and dates of birth. Furthermore, anyone can query `/ack/<id>.pdf` or `/application/<id>` sequentially.
  - *Requirement*: Restrict `/__gateway/` or protect simulated SMS queries; mask sensitive PII (Aadhaar/phone/bank account); audit log accesses; fix IDORs.

### 2.3 Correction & Grievance Dead-Ends
* **Lock-out on Minor Errors**:
  > *"Then there's my helpdesk overflowing—people writing in begging us to cancel their application because they made one small mistake, realized it only after submitting, and then found there is no way to fix it. No way to go back. We delete requests, and then they submit again."* — `docs/officer-note.md`
  - *Implicit cause*: `SELECT count(*) FROM applications WHERE mobile = %s` creates a permanent deadlock: if a user makes a typo in their bank account or name, they cannot edit the pending application and cannot submit a corrected one.
  - *Requirement*: Allow application editing while in `PENDING` status, withdrawal, or grievance lodging.

### 2.4 Senior-Citizen & Multilingual Accessibility
* **Low-Literacy & Agentic Assistance**:
  > *"Support Indian context: multilingual considerations (at least Hindi and English, plus Kannada if feasible), low-literacy and accessibility."* — `<USER_REQUEST>`
  > *"Citizen safety first: the users are senior citizens, often acting through family or an agent on their behalf. Design for consent, clear confirmation before any state-changing action, and plain language."* — `<USER_REQUEST>`
  - Clear explanations of required documents, intuitive error messages that state *exactly* what is missing, and multi-turn confirmation for any critical mutations.

---

## 3. Constraints & Technical Boundaries

1. **Database Immutability**:
   - Production records (~100,000 citizens) must not be purged, truncated, or modified except where explicit bug remediation or state transitions (such as RTPS deemed approval) require it.
2. **Reverse Proxy & Single Exposed Port**:
   - The entire stack must be accessible through a single public port (or standard 80/443 via reverse proxy). The SMS gateway must remain reachable via `/__gateway/` for the automated probe.
3. **Admin Panel Retention**:
   - The web admin panel must remain fully functional (`/admin`, `/admin/dashboard`, `/admin/applications`, etc.) as the assessment probe uses it to inspect system state.
4. **Git History & Non-Squash Rule**:
   - Every commit must represent an atomic, logical progression. Never squash commits.
   - For the top 5 fixes, tests must be committed failing first, then passing with code fixes.
5. **30-Day Deployment Longevity**:
   - Must be hosted on stable, economical cloud infrastructure with systemd / docker compose autorestart.
6. **No Leaked Secrets**:
   - All API keys, database credentials, and session secrets must reside in environment variables with a clean `.env.example`.
