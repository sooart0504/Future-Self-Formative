#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# Future Self Formative Study — chatbot startup script
#
# WHY THIS FILE EXISTS
#
# chatbot1_app.py and chatbot2_app.py read their API keys through st.secrets,
# which is a Streamlit feature that reads a file called .streamlit/secrets.toml.
# Streamlit Cloud created that file for you behind the scenes. Fly.io does not
# have that feature — it hands secrets to your app as environment variables.
#
# Rather than rewrite your Python (which the IRB would want documented), this
# script recreates the file Streamlit expects from a single Fly secret named
# STREAMLIT_SECRETS_TOML, then starts the app. Your Python is untouched.
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail

SECRETS_DIR="/app/.streamlit"
SECRETS_FILE="${SECRETS_DIR}/secrets.toml"

if [ -z "${STREAMLIT_SECRETS_TOML:-}" ]; then
  echo "FATAL: the STREAMLIT_SECRETS_TOML secret is not set on this Fly app." >&2
  echo "       Set it with:  fly secrets set STREAMLIT_SECRETS_TOML=\"\$(cat secrets.toml)\" -a <app-name>" >&2
  exit 1
fi

mkdir -p "$SECRETS_DIR"
printf '%s\n' "$STREAMLIT_SECRETS_TOML" > "$SECRETS_FILE"
chmod 600 "$SECRETS_FILE"

# Never print the contents — only confirm the file was created.
echo "Wrote ${SECRETS_FILE} ($(wc -c < "$SECRETS_FILE") bytes)."

APP_FILE="${APP_FILE:-chatbot1_app.py}"

if [ ! -f "/app/${APP_FILE}" ]; then
  echo "FATAL: APP_FILE is set to '${APP_FILE}' but /app/${APP_FILE} does not exist." >&2
  exit 1
fi

echo "Starting Streamlit: ${APP_FILE} on port ${PORT:-8080}"

exec streamlit run "/app/${APP_FILE}" \
  --server.port="${PORT:-8080}" \
  --server.address=0.0.0.0 \
  --server.headless=true \
  --browser.gatherUsageStats=false
