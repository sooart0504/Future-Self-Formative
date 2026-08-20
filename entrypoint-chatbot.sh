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
# This script rebuilds the file Streamlit expects from ordinary environment
# variables, so your Python code is never modified.
#
# Every secret it reads is a SINGLE LINE. That is deliberate: Fly's dashboard
# stores each secret in a one-line field, so a multi-line value gets flattened
# and produces invalid TOML. Building the file here from single-line pieces
# removes that whole class of failure.
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail

SECRETS_DIR="/app/.streamlit"
SECRETS_FILE="${SECRETS_DIR}/secrets.toml"

mkdir -p "$SECRETS_DIR"

# ── Check everything required is present before doing anything ───────────────
REQUIRED="OPENAI_API_KEY OPENAI_API_BASE GOOGLE_SHEET_KEY GOOGLE_CREDENTIALS LANGCHAIN_API_KEY LANGCHAIN_PROJECT"
MISSING=""
for var in $REQUIRED; do
  if [ -z "${!var:-}" ]; then
    MISSING="${MISSING} ${var}"
  fi
done

if [ -n "$MISSING" ]; then
  echo "FATAL: these required secrets are not set on this Fly app:" >&2
  for var in $MISSING; do echo "         - ${var}" >&2; done
  echo "" >&2
  echo "       Add them at: fly.io/dashboard -> this app -> Secrets." >&2
  echo "       Names must match exactly: capitals and underscores, no spaces." >&2
  exit 1
fi

# ── Build secrets.toml ────────────────────────────────────────────────────────
# GOOGLE_CREDENTIALS is the service-account JSON on one line — the same value
# the scheduler app uses. It is expanded here into the [gcp_service_account]
# table that chatbot1_app.py and chatbot2_app.py expect.
python3 <<'PYTHON'
import json, os, sys

def toml_value(v):
    # JSON string escaping is compatible with TOML basic strings for the
    # characters that appear in keys and PEM blocks (\n, \", \\).
    return json.dumps(str(v))

lines = []
for key in ("OPENAI_API_KEY", "OPENAI_API_BASE",
            "LANGCHAIN_API_KEY", "LANGCHAIN_PROJECT",
            "GOOGLE_SHEET_KEY",
            "CONFIG_FILE_CB1", "CONFIG_FILE_CB2"):
    value = os.environ.get(key)
    if value:
        lines.append(f"{key} = {toml_value(value)}")

raw = os.environ.get("GOOGLE_CREDENTIALS", "").strip()

# Tolerate a value that was pasted wrapped in single or double quotes.
if len(raw) >= 2 and raw[0] == raw[-1] and raw[0] in ("'", '"'):
    raw = raw[1:-1].strip()

try:
    creds = json.loads(raw)
except Exception as exc:
    print("FATAL: GOOGLE_CREDENTIALS is not valid JSON.", file=sys.stderr)
    print(f"       Parser said: {exc}", file=sys.stderr)
    print("       It must be the service-account key file's contents, starting", file=sys.stderr)
    print('       with {"type": "service_account", ... and ending with }.', file=sys.stderr)
    print("       Paste it with no surrounding quotes.", file=sys.stderr)
    sys.exit(1)

if not isinstance(creds, dict) or "client_email" not in creds:
    print("FATAL: GOOGLE_CREDENTIALS parsed as JSON but does not look like a", file=sys.stderr)
    print("       service-account key (no client_email field).", file=sys.stderr)
    sys.exit(1)

lines.append("")
lines.append("[gcp_service_account]")
for k, v in creds.items():
    lines.append(f"{k} = {toml_value(v)}")

with open("/app/.streamlit/secrets.toml", "w") as fh:
    fh.write("\n".join(lines) + "\n")

# Verify what we just wrote actually parses, so a bad value fails here with a
# clear message rather than deep inside Streamlit.
import tomllib
with open("/app/.streamlit/secrets.toml", "rb") as fh:
    parsed = tomllib.load(fh)

# Log NAMES only — never values.
top = [k for k in parsed if k != "gcp_service_account"]
print(f"secrets.toml written and verified. Keys: {', '.join(sorted(top))}")
print(f"  [gcp_service_account] fields: {len(parsed.get('gcp_service_account', {}))}")
print(f"  service account: {parsed['gcp_service_account'].get('client_email', '?')}")
PYTHON

chmod 600 "$SECRETS_FILE"

# ── Start the app ─────────────────────────────────────────────────────────────
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
