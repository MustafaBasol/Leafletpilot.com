#!/usr/bin/env bash
set -euo pipefail

: "${POSTGRES_HOST:?POSTGRES_HOST is required}"
: "${POSTGRES_DB:?POSTGRES_DB is required}"
: "${POSTGRES_USER:?POSTGRES_USER is required}"
: "${BACKUP_DIR:?BACKUP_DIR is required}"

RETENTION_DAYS="${RETENTION_DAYS:-14}"
TIMESTAMP="$(date -u +%Y%m%dT%H%M%SZ)"
OUTPUT_DIR="${BACKUP_DIR%/}/postgres"
OUTPUT_FILE="${OUTPUT_DIR}/${POSTGRES_DB}_${TIMESTAMP}.dump"

mkdir -p "${OUTPUT_DIR}"

pg_dump \
  --host="${POSTGRES_HOST}" \
  --port="${POSTGRES_PORT:-5432}" \
  --username="${POSTGRES_USER}" \
  --dbname="${POSTGRES_DB}" \
  --format=custom \
  --file="${OUTPUT_FILE}"

sha256sum "${OUTPUT_FILE}" > "${OUTPUT_FILE}.sha256"

find "${OUTPUT_DIR}" -type f \( -name '*.dump' -o -name '*.dump.sha256' \) -mtime +"${RETENTION_DAYS}" -delete

echo "Created PostgreSQL backup: ${OUTPUT_FILE}"
