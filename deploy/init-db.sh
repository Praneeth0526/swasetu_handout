#!/usr/bin/env bash
set -e

echo "[init-db] Initializing Sewa Setu database..."

# Create database user and database if needed
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<-EOSQL
    CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
EOSQL

# Execute Schema
if [ -f /docker-entrypoint-initdb.d/01-schema.sql ]; then
    echo "[init-db] Applying schema from 01-schema.sql..."
    psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" -f /docker-entrypoint-initdb.d/01-schema.sql
elif [ -f /app/schema.sql ]; then
    echo "[init-db] Applying schema from /app/schema.sql..."
    psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" -f /app/schema.sql
fi

# Load Seed Data if available
if [ -f /docker-entrypoint-initdb.d/02-seed.sql ]; then
    echo "[init-db] Loading seed data from 02-seed.sql..."
    psql -v ON_ERROR_STOP=0 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" -f /docker-entrypoint-initdb.d/02-seed.sql || echo "[init-db] Seed data partially loaded or skipped."
elif [ -f /seed/seed.sql ]; then
    echo "[init-db] Loading seed data from /seed/seed.sql..."
    psql -v ON_ERROR_STOP=0 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" -f /seed/seed.sql || echo "[init-db] Seed data partially loaded or skipped."
fi

echo "[init-db] Database initialization completed successfully."
