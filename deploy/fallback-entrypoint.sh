#!/usr/bin/env bash
set -e

PORT="${PORT:-7860}"
echo "=========================================================="
echo " Starting Sewa Setu All-in-One Container on port ${PORT} "
echo " Government of Purvanchal - Department of Social Welfare  "
echo "=========================================================="

mkdir -p /var/sewasetu/uploads /var/log/sewasetu /var/run/postgresql /var/lib/postgresql/data
chown -R postgres:postgres /var/run/postgresql /var/lib/postgresql

# 1. Initialize Postgres if data directory is empty
if [ ! -f "/var/lib/postgresql/data/PG_VERSION" ]; then
    echo "[1/5] Initializing Postgres database cluster..."
    su - postgres -c "/usr/lib/postgresql/*/bin/initdb -D /var/lib/postgresql/data --auth-local=trust --auth-host=trust"
fi

# 2. Start PostgreSQL service
echo "[2/5] Starting PostgreSQL service..."
su - postgres -c "/usr/lib/postgresql/*/bin/pg_ctl -D /var/lib/postgresql/data -w start"

# 3. Create database, user, schema and seed data
echo "[3/5] Setting up database schema and seed data..."
su - postgres -c "psql -c \"CREATE USER sewasetu WITH SUPERUSER PASSWORD 'sewasetu123';\"" 2>/dev/null || true
su - postgres -c "psql -c \"CREATE DATABASE sewasetu OWNER sewasetu;\"" 2>/dev/null || true

if [ -f "/app/schema.sql" ]; then
    echo "  -> Applying schema /app/schema.sql..."
    su - postgres -c "psql -d sewasetu -f /app/schema.sql"
fi

if [ -f "/seed/seed.sql" ]; then
    echo "  -> Loading seed data from /seed/seed.sql..."
    su - postgres -c "psql -d sewasetu -f /seed/seed.sql" 2>/dev/null || echo "Seed loading completed with notices."
fi

# 4. Start SMS Gateway, Background Worker, and Portal App
echo "[4/5] Launching microservices..."

# SMS Gateway on 127.0.0.1:8025
cd /smsgw && python app.py > /var/log/sewasetu/smsgw.log 2>&1 &
echo "  -> SMS Gateway started on PID $!"

# Export Environment for App and Worker
export DB_HOST=localhost
export DB_PORT=5432
export DB_NAME=sewasetu
export DB_USER=sewasetu
export DB_PASSWORD=sewasetu123
export SMS_GATEWAY_URL=http://localhost:8025
export ADMIN_USERNAME="${ADMIN_USERNAME:-admin}"
export ADMIN_PASSWORD="${ADMIN_PASSWORD:-sewasetu@123}"
export ASSESSOR_USERNAME="${ASSESSOR_USERNAME:-assessor_admin}"
export ASSESSOR_PASSWORD="${ASSESSOR_PASSWORD:-Purvanchal@Assess2027}"
export ADMIN_BEARER_TOKEN="${ADMIN_BEARER_TOKEN:-Purvanchal@Assess2027}"
export FLASK_SECRET_KEY="${FLASK_SECRET_KEY:-ssp-prod-secret-key-2027}"
export PYTHONPATH="/app:${PYTHONPATH}"

# Worker daemon (RTPS Deemed Approval)
cd /app && python -m worker --interval 3600 > /var/log/sewasetu/worker.log 2>&1 &
echo "  -> RTPS Deemed Approval worker started on PID $!"

# Main Web Portal (Gunicorn) on 127.0.0.1:8000
cd /app && gunicorn --bind 127.0.0.1:8000 --workers 4 --timeout 60 app:app > /var/log/sewasetu/portal.log 2>&1 &
echo "  -> Gunicorn Portal started on PID $!"

# Wait for portal to respond on health
sleep 3
curl -s -f http://127.0.0.1:8000/health || echo "Portal warming up..."

# 5. Generate Caddyfile and run Caddy in foreground
echo "[5/5] Starting Caddy reverse proxy on port ${PORT}..."
cat <<EOF > /tmp/Caddyfile
{
    admin off
}

:${PORT} {
    header {
        X-Content-Type-Options "nosniff"
        X-Frame-Options "SAMEORIGIN"
        Referrer-Policy "strict-origin-when-cross-origin"
    }

    handle /caddy-health {
        respond "OK" 200
    }

    handle_path /__gateway/* {
        reverse_proxy localhost:8025 {
            header_up Host {host}
            header_up X-Real-IP {remote_host}
            header_up X-Forwarded-For {remote_host}
            header_up X-Forwarded-Proto {scheme}
            header_up X-Forwarded-Prefix /__gateway
        }
    }

    handle /mcp/* {
        reverse_proxy localhost:8000 {
            header_up Host {host}
            header_up X-Real-IP {remote_host}
            header_up X-Forwarded-For {remote_host}
            header_up X-Forwarded-Proto {scheme}
            flush_interval -1
        }
    }

    handle {
        reverse_proxy localhost:8000 {
            header_up Host {host}
            header_up X-Real-IP {remote_host}
            header_up X-Forwarded-For {remote_host}
            header_up X-Forwarded-Proto {scheme}
        }
    }
}
EOF

exec caddy run --config /tmp/Caddyfile --adapter caddyfile
