"""
twilio_scheduler.py
Future Self Formative Study — Daily SMS Scheduler
 
Runs as a cron job every minute via Render.
For each active participant, checks if their local wake time matches
the current time and sends their personalized Qualtrics check-in link.
 
Each participant has a unique pre-authenticated Qualtrics Personal Link
stored in Google Sheets Tab 3. That link automatically loads their
personalized narrative, anchors, and images — no login required.
 
Required environment variables (set in Render):
  TWILIO_ACCOUNT_SID
  TWILIO_AUTH_TOKEN
  TWILIO_FROM_NUMBER      e.g. +15005550006
  GOOGLE_SHEET_KEY        Google Sheets spreadsheet ID
  GOOGLE_CREDS_JSON       Service account credentials as a JSON string
 
Google Sheets Tab 3 (Schedule) column headers — must match exactly:
  PID | phone | wake_time | timezone | active | checkin_link
"""
 
import os
import json
import logging
from datetime import datetime
 
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
TWILIO_ACCOUNT_SID = os.environ["TWILIO_ACCOUNT_SID"]
TWILIO_AUTH_TOKEN  = os.environ["TWILIO_AUTH_TOKEN"]
TWILIO_FROM_NUMBER = os.environ["TWILIO_FROM_NUMBER"]
GOOGLE_SHEET_KEY   = os.environ["GOOGLE_SHEET_KEY"]
GOOGLE_CREDS_JSON  = os.environ["GOOGLE_CREDS_JSON"]
 
 
# ── Google Sheets ─────────────────────────────────────────────────────────────
def get_schedule_rows():
    """Reads Tab 3 (worksheet index 2). Returns list of dicts keyed by header."""
    creds_info = json.loads(GOOGLE_CREDS_JSON)
    creds = Credentials.from_service_account_info(
        creds_info,
        scopes=["https://www.googleapis.com/auth/spreadsheets"]
    )
    client = gspread.authorize(creds)
    sheet  = client.open_by_key(GOOGLE_SHEET_KEY).get_worksheet(2)
    return sheet.get_all_records()
 
 
# ── Time check ────────────────────────────────────────────────────────────────
def should_send_now(wake_time_str, tz_str):
    """Returns True if the participant's local HH:MM matches the current time."""
    try:
        tz           = pytz.timezone(tz_str)
        now_local    = datetime.now(tz)
        current_hhmm = now_local.strftime("%H:%M")
        return current_hhmm == wake_time_str.strip()
    except Exception as e:
        log.warning(f"Timezone error for '{tz_str}': {e}")
        return False
 
 
# ── SMS sender ────────────────────────────────────────────────────────────────
def send_checkin_sms(pid, phone, checkin_link):
    """Sends the daily check-in SMS with the participant's personal link."""
    body = (
        "Good morning! It's time for your daily Future Self check-in. "
        f"Tap here to begin: {checkin_link}"
    )
    twilio = TwilioClient(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
    msg    = twilio.messages.create(
        body=body,
        from_=TWILIO_FROM_NUMBER,
        to=phone
    )
    log.info(f"SMS sent  PID={pid}  phone={phone}  SID={msg.sid}")
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
 
    for participant in rows:
        pid          = str(participant.get("PID", "")).strip()
        phone        = str(participant.get("phone", "")).strip()
        wake_time    = str(participant.get("wake_time", "")).strip()
        tz_str       = str(participant.get("timezone", "")).strip()
        active       = str(participant.get("active", "")).strip().upper()
        checkin_link = str(participant.get("checkin_link", "")).strip()
 
        if active != "Y":
            continue
        if not all([pid, phone, wake_time, tz_str, checkin_link]):
            log.warning(f"Skipping incomplete row: PID={pid}")
            continue
 
        if should_send_now(wake_time, tz_str):
            try:
                send_checkin_sms(pid, phone, checkin_link)
                sent_count += 1
            except Exception as e:
                log.error(f"Failed to send SMS to {pid}: {e}")
 
    log.info(f"Done. {sent_count} message(s) sent.")
 
 
if __name__ == "__main__":
    main()