#!/bin/bash
# scripts/fetch-config.sh — Fetch runtime secrets from Secrets Manager
#
# Writes DB credentials to /opt/pyvar/secrets.env so systemd can load them
# via EnvironmentFile before starting the Celery worker.
#
# Called in two contexts:
#   1. UserData (first boot) — runs directly before systemctl start celery-worker
#   2. systemd ExecStartPre  — runs on every service start/restart to refresh creds
#
# Required env vars (supplied by UserData export or systemd EnvironmentFile):
#   AWS_DEFAULT_REGION  — AWS region for Secrets Manager lookup
#   PYVAR_ENV_NAME      — environment name (dev/staging/prod)

set -euo pipefail

REGION="${AWS_DEFAULT_REGION:-eu-west-1}"
ENV_NAME="${PYVAR_ENV_NAME:-dev}"
SECRETS_FILE="/opt/pyvar/secrets.env"

echo "[fetch-config] Fetching pyvar/${ENV_NAME}/aurora-credentials from ${REGION} ..."

SECRET=$(aws secretsmanager get-secret-value \
    --secret-id "pyvar/${ENV_NAME}/aurora-credentials" \
    --region "${REGION}" \
    --query SecretString \
    --output text)

# Write the JSON to a temp file so Python can safely parse it —
# avoids shell-quoting issues with passwords containing special characters.
_TMP=$(mktemp)
chmod 600 "${_TMP}"
printf '%s' "${SECRET}" > "${_TMP}"

# Parse JSON and write secrets.env; variable substitution of $_TMP and
# $SECRETS_FILE happens in bash before Python sees the heredoc.
python3 << PYEOF
import json, os

with open("${_TMP}") as fh:
    d = json.load(fh)

os.unlink("${_TMP}")

out = "${SECRETS_FILE}"
os.makedirs(os.path.dirname(out), exist_ok=True)
with open(out, "w") as fh:
    fh.write("DB_HOST={}\n".format(d["host"]))
    fh.write("DB_PORT={}\n".format(d.get("port", 5432)))
    fh.write("DB_NAME={}\n".format(d.get("dbname", "pyvar")))
    fh.write("DB_USER={}\n".format(d["username"]))
    fh.write("DB_PASSWORD={}\n".format(d["password"]))
os.chmod(out, 0o600)
PYEOF

echo "[fetch-config] Credentials written to ${SECRETS_FILE}"

# Sentry DSN — optional. setup_sentry() (observability/setup.py) already
# no-ops cleanly on a blank SENTRY_DSN, so a missing/denied secret here must
# degrade to "no Sentry" rather than abort the script under set -e (unlike
# the required aurora-credentials fetch above).
echo "[fetch-config] Fetching pyvar/${ENV_NAME}/sentry-dsn from ${REGION} (optional) ..."
SENTRY_DSN=$(aws secretsmanager get-secret-value \
    --secret-id "pyvar/${ENV_NAME}/sentry-dsn" \
    --region "${REGION}" \
    --query SecretString \
    --output text 2>/dev/null || echo "")

if [ -n "${SENTRY_DSN}" ]; then
    echo "SENTRY_DSN=${SENTRY_DSN}" >> "${SECRETS_FILE}"
    echo "[fetch-config] Sentry DSN appended to ${SECRETS_FILE}"
else
    echo "[fetch-config] No Sentry DSN found for ${ENV_NAME} — continuing without Sentry (optional)"
fi
