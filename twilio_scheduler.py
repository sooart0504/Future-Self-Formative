"""
twilio_scheduler.py
Future Self Formative Study — Daily SMS Scheduler

Runs as a cron job (every minute).
For each active participant, checks if their local wake time matches
the current UTC time and sends a Twilio SMS if so.

Required environment variables (set in Render/Railway):
  TWILIO_ACCOUNT_SID
  TWILIO_AUTH_TOKEN
  TWILIO_FROM_NUMBER    e.g. +15005550006
  GOOGLE_SHEET_KEY      Google Sheets spreadsheet ID
  GOOGLE_CREDS_JSON     Service account credentials as a JSON string

Google Sheets schedule table (Tab 3, worksheet index 2):
  Columns: PID | phone | wake_time | timezone | active
  - wake_time: HH:MM in 24-hour format (e.g. 07:30)
  - timezone: IANA format (e.g. America/Detroit)
  - active: Y or N

Qualtrics check-in link (placeholder — replace with real survey link):
  https://umich.qualtrics.com/jfe/form/SV_PLACEHOLDER?PID={pid}
"""

import os
import json
import logging
from datetime import datetime, timezone

import gspread
from google.oauth2.service_account import Credentials
from twilio.rest import Client as TwilioClient
import pytz

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)s  %(message)s"
)
log = logging.getLogger(__name__)

# ── Config ────────────────────────────────────────────────────────────────────
TWILIO_ACCOUNT_SID  = os.environ["TWILIO_ACCOUNT_SID"]
TWILIO_AUTH_TOKEN   = os.environ["TWILIO_AUTH_TOKEN"]
TWILIO_FROM_NUMBER  = os.environ["TWILIO_FROM_NUMBER"]
GOOGLE_SHEET_KEY    = os.environ["GOOGLE_SHEET_KEY"]
GOOGLE_CREDS_JSON   = os.environ["GOOGLE_CREDS_JSON"]   # JSON string of service account

# Qualtrics check-in placeholder link
CHECKIN_URL_TEMPLATE = "https://umich.qualtrics.com/jfe/form/SV_PLACEHOLDER?PID={pid}"

# Column indices in the schedule tab (0-based)
COL_PID       = 0
COL_PHONE     = 1
COL_WAKE_TIME = 2
COL_TIMEZONE  = 3
COL_ACTIVE    = 4


# ── Google Sheets reader ──────────────────────────────────────────────────────
def get_schedule_rows():
    """Reads the participant schedule table from Tab 3 (worksheet index 2)."""
    creds_info = json.loads(GOOGLE_CREDS_JSON)
    creds = Credentials.from_service_account_info(
        creds_info,
        scopes=["https://www.googleapis.com/auth/spreadsheets"]
    )
    client = gspread.authorize(creds)
    sheet  = client.open_by_key(GOOGLE_SHEET_KEY).get_worksheet(2)
    rows   = sheet.get_all_values()

    # Skip header row if present
    if rows and rows[0][COL_ACTIVE].strip().lower() == "active":
        rows = rows[1:]

    return rows


# ── Time matching ─────────────────────────────────────────────────────────────
def should_send_now(wake_time_str, tz_str):
    """
    Returns True if the current UTC time matches the participant's
    local wake time (matched to the minute).

    Args:
        wake_time_str: "HH:MM" in 24-hour format
        tz_str: IANA timezone string (e.g. "America/Detroit")
    """
    try:
        tz           = pytz.timezone(tz_str)
        now_local    = datetime.now(tz)
        current_hhmm = now_local.strftime("%H:%M")
        return current_hhmm == wake_time_str.strip()
    except Exception as e:
        log.warning(f"Timezone error for {tz_str}: {e}")
        return False


# ── SMS sender ────────────────────────────────────────────────────────────────
def send_checkin_sms(pid, phone):
    """Sends the daily check-in SMS to a participant."""
    checkin_url = CHECKIN_URL_TEMPLATE.format(pid=pid)
    message_body = (
        f"Good morning! It's time for your daily check-in. "
        f"Tap the link to get started: {checkin_url}"
    )

    twilio = TwilioClient(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
    msg = twilio.messages.create(
        body=message_body,
        from_=TWILIO_FROM_NUMBER,
        to=phone
    )
    log.info(f"SMS sent to {pid} ({phone}) — SID: {msg.sid}")
    return msg.sid


# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    log.info("Scheduler running...")

    try:
        rows = get_schedule_rows()
    except Exception as e:
        log.error(f"Failed to read schedule sheet: {e}")
        return

    sent_count = 0

    for row in rows:
        # Skip rows with missing data
        if len(row) <= COL_ACTIVE:
            continue

        pid        = row[COL_PID].strip()
        phone      = row[COL_PHONE].strip()
        wake_time  = row[COL_WAKE_TIME].strip()
        tz_str     = row[COL_TIMEZONE].strip()
        active     = row[COL_ACTIVE].strip().upper()

        # Skip inactive or incomplete rows
        if active != "Y":
            continue
        if not pid or not phone or not wake_time or not tz_str:
            log.warning(f"Skipping incomplete row for PID: {pid}")
            continue

        if should_send_now(wake_time, tz_str):
            try:
                send_checkin_sms(pid, phone)
                sent_count += 1
            except Exception as e:
                log.error(f"Failed to send SMS to {pid}: {e}")

    log.info(f"Done. {sent_count} message(s) sent.")


if __name__ == "__main__":
    main()
