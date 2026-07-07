#!/usr/bin/env bash
set -euo pipefail

: "${STORAGE_DIR:?STORAGE_DIR is required}"
: "${BACKUP_DIR:?BACKUP_DIR is required}"

RETENTION_DAYS="${RETENTION_DAYS:-14}"
TIMESTAMP="$(date -u +%Y%m%dT%H%M%SZ)"
OUTPUT_DIR="${BACKUP_DIR%/}/storage"
OUTPUT_FILE="${OUTPUT_DIR}/leafletpilot_storage_${TIMESTAMP}.tar.gz"

if [[ ! -d "${STORAGE_DIR}" ]]; then
  echo "Storage directory does not exist: ${STORAGE_DIR}" >&2
  exit 1
fi

mkdir -p "${OUTPUT_DIR}"

tar -C "$(dirname "${STORAGE_DIR}")" -czf "${OUTPUT_FILE}" "$(basename "${STORAGE_DIR}")"
sha256sum "${OUTPUT_FILE}" > "${OUTPUT_FILE}.sha256"

find "${OUTPUT_DIR}" -type f \( -name '*.tar.gz' -o -name '*.tar.gz.sha256' \) -mtime +"${RETENTION_DAYS}" -delete

echo "Created storage backup: ${OUTPUT_FILE}"
