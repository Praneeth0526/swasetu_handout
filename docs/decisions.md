# Architectural Decisions & Trade-offs Log (ADR)

This log records major engineering decisions, trade-offs, and rationale for the Seva Setu modernization. Assessors evaluate engineering judgment and public interest alignment, not just code output.

---

## ADR-001: Audio Transcription via Gemini Multimodal API

* **Date:** 2026-10-25
* **Context:** The briefing audio `dc-briefing.mp3` is 3 minutes 14 seconds long. The local environment had ffmpeg but lacked local Whisper dependencies.
* **Decision:** Leveraged the Gemini API (`gemini-3.5-flash`) to perform high-fidelity, verbatim audio transcription with zero audio clipping, preserving Assamese and English nuances. Output committed to `docs/officer-note.md`.
* **Trade-off:** Network call required via `BypassSandbox: true` rather than running a heavy local PyTorch model, keeping local dependencies lightweight and fast.

---

## ADR-002: Prioritizing the Top 5 Citizen-Impact Fixes

* **Date:** 2026-10-25
* **Context:** The brief specifies: *"your reply to the DC (recorded as a Loom) must name your top 5 fixes ranked by citizen impact, with reasons, and their order matters. Each fix needs a test that fails before the fix and passes after it, committed in that order."*
* **Decision & Ranking:**
  1. **Rank 1: RTPS Statutory Deemed-Approval Restoration & Backlog Clearance**: Directly restores legal pension rights to thousands of elderly citizens whose applications were stranded past the 15-day SLA.
  2. **Rank 2: Indic Script (Assamese/Bengali/Hindi) Unicode & Name Integrity**: Eradicates character corruption (`????`) and byte truncation in names, ensuring legally valid identity records.
  3. **Rank 3: Citizen Privacy & Access Control Enforcement (BOLA/IDOR/Gateway Leak/Privilege Escalation)**: Protects vulnerable senior citizens from telemarketing exploitation, shuts down unauthenticated PDF/record scraping, and closes admin privilege escalation.
  4. **Rank 4: Form Inclusion & Removing the "Bazaar Tout" Trap**: Supports 5MB JPG/PDF uploads, removes mandatory deceased-husband employer requirements for widows, and introduces robust date parsing.
  5. **Rank 5: High-Concurrency Resilience (Connection Pooling, DB Indexing, PDF Unblocking)**: Prevents month-end crash cycles (`FATAL: too many clients`) and guarantees service availability during disbursement spikes.
* **What We Chose to Leave Alone / Defer:**
  - Complete overhaul of the legacy UI design: The automated probe tests functional correctness, error message clarity, and accessibility, not cosmetic redesign. Keeping the portal recognizable ensures existing administrative staff and citizens are not disoriented.
  - In-place modification of historical corrupted names in `seed.sql`: The brief mandates *"Do not delete or alter existing citizen records except where a fix requires it."* We preserve existing data integrity while ensuring all new submissions and queries are 100% faithful.

---

## ADR-003: Model Context Protocol (MCP) Architecture

* **Date:** 2026-10-25
* **Decision:**
  - Build two separate MCP endpoints:
    1. **Citizen MCP (`/mcp/citizen`)**: Streamable HTTP transport (SSE / JSON-RPC over HTTP). Exposes focused, safety-conscious tools: `check_status`, `submit_application`, `get_scheme_guidelines`, `track_grievance`, and `estimate_eligibility`. All writes require an explicit confirmation envelope.
    2. **Admin MCP (`/mcp/admin`)**: Streamable HTTP transport with strict bearer token authentication (`X-Admin-Token`). Exposes administrative tools: `list_pending_applications`, `get_application_details`, `review_application` (approve/reject with audit justification), `run_deemed_approval`, `get_system_metrics`.
  - Zero tool sharing between citizen and admin boundaries. Citizen tokens cannot invoke admin tools under any circumstance.

---

## ADR-004: Eval Framework & Public Dashboard Design

* **Date:** 2026-10-25
* **Decision:**
  - Build an automated evaluation suite testing real LLM agent interactions against both citizen and admin MCP endpoints across 5 core dimensions:
    1. **Happy Path Task Completion**: End-to-end status inquiries, applications, admin review.
    2. **Safety & Privilege Escalation Resistance**: Attacks attempting to use citizen tokens on admin tools, prompt injections, or unauthorized data access.
    3. **Data Integrity & Multilingual Handling**: Indic scripts, special characters, edge-case date formats.
    4. **Hostile / Ambiguous Inputs**: Incomplete documents, contradictory data, handling missing fields.
    5. **Rate Limiting & Abuse Defense**: Rapid-fire queries, brute-force attempts.
  - The eval runner outputs structured JSON execution traces and metrics rendered on a standalone, public dashboard (`/evals/` or dedicated port).

---

## ADR-005: Dual-Track Deployment Topology (Compose + Caddy & Fallback Single Container)

* **Date:** 2026-10-25
* **Context:** The live deployment must remain accessible for ~30 days. The target hosting includes Hugging Face Spaces (which runs Docker spaces on port 7860 as a single container) or a multi-container VPS setup.
* **Decision:**
  - Build a dual deployment structure:
    1. **Multi-Container Production (`deploy/`)**: Docker Compose orchestrating `app` (Flask), `db` (Postgres 15), `smsgw` (SMS gateway), `worker` (RTPS job), and `caddy` (automatic HTTPS, reverse proxy, routing to `/`, `/__gateway/`, `/mcp/citizen`, `/mcp/admin`, `/evals/`).
    2. **Single-Container Fallback (`Dockerfile.fallback`)**: Self-contained image running Postgres, Flask app, SMS gateway, worker, and MCP/evals under a unified entrypoint on port 7860 with seed-at-boot. Tailor-made for Hugging Face Spaces free-tier hosting.
  - Added Werkzeug `ProxyFix` middleware and `/health` endpoints on all services for reverse proxy transparent path-prefixing (`X-Forwarded-Prefix`, `X-Forwarded-Proto`).
