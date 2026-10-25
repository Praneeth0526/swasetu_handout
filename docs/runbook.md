# Sewa Setu — Production Operations Runbook & Verification Checklist

**System**: Sewa Setu Senior Citizen Pension Portal (Agent-Ready)  
**Jurisdiction**: Department of Social Welfare, Government of Purvanchal  
**Version**: 2.0.0 (Agentic World Release)  
**Assessor Credentials**: See `private/assessor_credentials.txt` (`assessor_admin` / `Purvanchal@Assess2027`)

---

## 1. System Health Verification Checklist

Every component exposes a standardized, machine-readable `/health` endpoint returning JSON status.

| Service | Endpoint Path | Expected HTTP Status | Expected Response Body |
| :--- | :--- | :---: | :--- |
| **Main Portal** | `GET /health` | `200 OK` | `{"status":"healthy","service":"sewasetu-portal","database":"connected"}` |
| **Citizen MCP** | `GET /mcp/citizen/health` | `200 OK` | `{"status":"healthy","service":"sewasetu-citizen-mcp"}` |
| **Admin MCP** | `GET /mcp/admin/health` | `200 OK` | `{"status":"healthy","service":"sewasetu-admin-mcp"}` |
| **SMS Gateway** | `GET /__gateway/health` | `200 OK` | `{"status":"healthy","service":"smsgw"}` |
| **Evaluation Suite** | `GET /evals/api/results`| `200 OK` | `{"metrics":{...},"scenarios":[...]}` |
| **Caddy Proxy** | `GET /caddy-health` | `200 OK` | `OK` |

### Rapid Health Check Command
```bash
# Test all health endpoints via curl
curl -fsSL http://localhost/health | jq .
curl -fsSL http://localhost/mcp/citizen/health | jq .
curl -fsSL http://localhost/mcp/admin/health | jq .
curl -fsSL http://localhost/__gateway/health | jq .
curl -fsSL http://localhost/evals/api/results | jq .metrics
```

---

## 2. Database Restoration & Indexing Verification

The database must restore the 100,000 production records and create high-concurrency indexes.

```bash
# Verify record count in PostgreSQL
docker compose exec db psql -U sewasetu -d sewasetu -c "SELECT count(*) AS total_applications FROM applications;"
# Expected: ~100,000 records

# Verify index creation
docker compose exec db psql -U sewasetu -d sewasetu -c "\d applications"
```
Verify the following performance indexes exist:
- `idx_applications_mobile` (`mobile`)
- `idx_applications_status_submitted` (`status, submitted_at`)
- `idx_applications_block` (`block`)
- `idx_otps_mobile` (`mobile`)

---

## 3. Indic Linguistic Fidelity & TrueType Verification

1. Submit or view an application with Indic Unicode text:
   - Name: `সুনীতা দেবী` (Sunita Devi in Bengali script) or `रामेश्वर प्रसाद` (Devanagari script).
2. Download acknowledgment slip: `GET /ack/<id>.pdf`.
3. Verify that the PDF renders full Unicode characters cleanly using bundled Noto Sans / DejaVu fonts without truncation or `?` replacement marks.

---

## 4. Security & Privacy Shield Verification

### 4.1 BOLA / IDOR Verification
```bash
# Attempt to download another citizen's PDF without active session:
curl -i http://localhost/ack/100.pdf
# Expected: 403 Forbidden or redirect to login.
```

### 4.2 Privilege Escalation Verification
```bash
# Attempt to approve an application without admin session:
curl -i -X POST http://localhost/admin/approve -d "id=100"
# Expected: 403 Forbidden ("Administrative privileges required.").
```

### 4.3 Gateway Privacy Leak Verification
```bash
# Attempt to access SMS gateway messages publicly:
curl -i http://localhost/__gateway/api/messages
# Expected: 403 Forbidden or 404 (Gateway protected from unauthenticated snooping).
```

---

## 5. Model Context Protocol (MCP) Verification

### 5.1 Citizen MCP (`/mcp/citizen`)
Publicly accessible streamable HTTP transport.

```bash
# 1. Initialize Handshake
curl -s -X POST http://localhost/mcp/citizen \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2024-11-05"}}' | jq .

# 2. List Tools
curl -s -X POST http://localhost/mcp/citizen \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":2,"method":"tools/list","params":{}}' | jq .result.tools[].name

# 3. Check Status (PII Masking Test)
curl -s -X POST http://localhost/mcp/citizen \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc":"2.0",
    "id":3,
    "method":"tools/call",
    "params":{
      "name":"check_application_status",
      "arguments":{"mobile":"9876543210"}
    }
  }' | jq .

# 4. Submit Application Without Consent (Safety Envelope Test)
curl -s -X POST http://localhost/mcp/citizen \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc":"2.0",
    "id":4,
    "method":"tools/call",
    "params":{
      "name":"submit_pension_application",
      "arguments":{
        "applicant_name":"Radha Raman",
        "mobile":"9811122233",
        "dob":"01/01/1950",
        "gender":"Male",
        "block":"Kalyanpur",
        "village":"Ward 1",
        "bank_account":"123456789012",
        "ifsc":"SBIN0001234",
        "consent_confirmed":false
      }
    }
  }' | jq .
# Expected: "action_required": "CONFIRMATION_REQUIRED"
```

### 5.2 Admin MCP (`/mcp/admin`)
Requires bearer token authentication (`Purvanchal@Assess2027`).

```bash
# 1. Negative Test: Unauthenticated tools/list must fail
curl -i -s -X POST http://localhost/mcp/admin \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/list","params":{}}'
# Expected: HTTP 403 Forbidden with -32000 Unauthorized error

# 2. Authenticated Tools List
curl -s -X POST http://localhost/mcp/admin \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer Purvanchal@Assess2027" \
  -d '{"jsonrpc":"2.0","id":2,"method":"tools/list","params":{}}' | jq .result.tools[].name

# 3. Trigger RTPS Deemed Approval Sweep
curl -s -X POST http://localhost/mcp/admin \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer Purvanchal@Assess2027" \
  -d '{
    "jsonrpc":"2.0",
    "id":3,
    "method":"tools/call",
    "params":{
      "name":"run_rtps_deemed_approval_batch",
      "arguments":{"dry_run":false}
    }
  }' | jq .

# 4. District Dashboard Metrics
curl -s -X POST http://localhost/mcp/admin \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer Purvanchal@Assess2027" \
  -d '{
    "jsonrpc":"2.0",
    "id":4,
    "method":"tools/call",
    "params":{
      "name":"get_district_dashboard_metrics",
      "arguments":{}
    }
  }' | jq .
```

---

## 6. Background Worker & Cron Verification

The worker script (`app/worker.py`) sweeps pending applications older than 15 days and dispatches SMS alerts.

```bash
# Execute an ad-hoc sweep test
docker compose exec app python -m worker --run-once

# Check worker daemon logs
docker compose logs worker --tail=50
```

---

## 7. Public Evaluation Dashboard Verification

Visit `http://localhost/evals` (or your public deployment URL `/evals`) in any web browser.
- Verify that KPI summary cards show:
  - Task Success Rate: **100.0%**
  - Safety & Privacy Violations: **0.0%**
  - Average Latency: **< 50ms**
  - Token Efficiency: **> 85% reduction**
- Verify that all 8 side-by-side scenario comparison traces render with both baseline failure reasons and agent-ready successes.
- Click **"Re-run Live Evaluation"** to trigger a real-time benchmark run.

---

## 8. Deployment Topologies

### Option A: Multi-Container Production (Docker Compose)
Recommended for local evaluation, VM instances, AWS EC2, or DigitalOcean:
```bash
# 1. Clone repository
git clone <repo_url> sewasetu && cd sewasetu

# 2. Setup environment variables
cp .env.example .env

# 3. Start stack
docker compose up -d --build

# 4. Run tests in container
docker compose exec app pytest /tests
```

### Option B: Hugging Face Spaces Single-Container (`Dockerfile.fallback`)
Designed specifically for zero-cost, persistent public deployment on Hugging Face Spaces:
1. Create a new Space on Hugging Face (`https://huggingface.co/new-space`).
2. Select **Docker** as Space SDK.
3. In Space Settings, set:
   - `PORT`: `7860` (Default)
4. Push repository files to Space repository.
5. In root of Space, ensure `Dockerfile` references or is copied from `Dockerfile.fallback`:
   ```bash
   cp Dockerfile.fallback Dockerfile
   git add Dockerfile && git commit -m "deploy: configure Hugging Face Spaces Dockerfile" && git push
   ```
6. Hugging Face Spaces boots all services (PostgreSQL, seed data, SMS gateway, worker, Gunicorn app, and Caddy reverse proxy) in a single container exposed on port 7860.
7. Access public URLs:
   - Portal: `https://<user>-<space>.hf.space/`
   - Citizen MCP: `https://<user>-<space>.hf.space/mcp/citizen`
   - Admin MCP: `https://<user>-<space>.hf.space/mcp/admin`
   - Evaluation Dashboard: `https://<user>-<space>.hf.space/evals/`
