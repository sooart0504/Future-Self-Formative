"""
Future Self Formative Study — Twilio SMS Scheduler
Runs via Render cron job every 30 minutes.

Sends check-in SMS to participants on their scheduled check-in days,
at their preferred wake time, with PID + occasion number in the URL.

Check-in schedule (fixed, internal only):
  Week 1: Days 1, 3, 5, 7      (4 check-ins)
  Week 2: Days 8, 11, 14       (3 check-ins)
  Week 3: Days 17, 21          (2 check-ins)
  Week 4: Day 28               (1 check-in)
  Total: 10 check-ins over 28 days
"""

import os
import pytz
from datetime import datetime, timedelta

from twilio.rest import Client
import gspread
from google.oauth2.service_account import Credentials

# ── CONFIGURATION ─────────────────────────────────────────────
# Set these as environment variables in Render — never hardcode

TWILIO_ACCOUNT_SID = os.environ["TWILIO_ACCOUNT_SID"]
TWILIO_AUTH_TOKEN  = os.environ["TWILIO_AUTH_TOKEN"]
TWILIO_FROM_NUMBER = os.environ["TWILIO_FROM_NUMBER"]   # e.g. "+12345678900"

GOOGLE_SHEET_ID    = os.environ["GOOGLE_SHEET_ID"]
GOOGLE_CREDENTIALS = os.environ["GOOGLE_CREDENTIALS"]   # JSON string of service account key

CHECKIN_APP_URL    = os.environ["CHECKIN_APP_URL"]       # e.g. "https://yourname.github.io/future-self-checkin/"

# Tab 3 column names (must match your sheet exactly)
COL_PID        = "PID"
COL_PHONE      = "phone"
COL_WAKE_TIME  = "wake_time"       # HH:MM in 24-hour, e.g. "07:30"
COL_TIMEZONE   = "timezone"        # IANA, e.g. "America/Detroit"
COL_ACTIVE     = "active"          # "Y" or "N"
COL_TRIAL_START= "trial_start"     # Date trial started, e.g. "2026-05-15"
COL_OCCASION   = "current_occasion"# Running count of occasions sent so far (0-indexed)

# Fixed check-in day schedule (days since trial start, 1-indexed)
CHECKIN_DAYS = [1, 3, 5, 7, 8, 11, 14, 17, 21, 28]

# SMS message template
SMS_TEMPLATE = (
    "Good morning! It's time for your morning check-in. "
    "Tap the link to get started: {url}"
)

# ── GOOGLE SHEETS ─────────────────────────────────────────────
def get_sheet_tab3():
    import json
    creds_dict = json.loads(GOOGLE_CREDENTIALS)
    scopes     = ["https://www.googleapis.com/auth/spreadsheets"]
    creds      = Credentials.from_service_account_info(creds_dict, scopes=scopes)
    client     = gspread.authorize(creds)
    sheet      = client.open_by_key(GOOGLE_SHEET_ID)
    return sheet.worksheet("Schedule")  # adjust tab name if needed

def get_participants(tab):
    """Returns list of dicts, one per row, keyed by header names."""
    records = tab.get_all_records()
    return records

def update_occasion(tab, row_index, new_occasion):
    """Increments the current_occasion column for a participant row."""
    # row_index is 1-based; row 1 is headers, so data starts at row 2
    headers = tab.row_values(1)
    col_idx = headers.index(COL_OCCASION) + 1  # 1-based
    tab.update_cell(row_index + 2, col_idx, new_occasion)

# ── SCHEDULING LOGIC ──────────────────────────────────────────
def get_day_of_trial(trial_start_str, participant_tz):
    """
    Returns the current day of the trial (1-indexed) in the participant's timezone.
    trial_start_str: "YYYY-MM-DD" string (the date of the day AFTER Session 2)
    """
    tz            = pytz.timezone(participant_tz)
    now_local     = datetime.now(tz)
    trial_start   = tz.localize(datetime.strptime(trial_start_str, "%Y-%m-%d"))
    delta         = (now_local.date() - trial_start.date()).days + 1  # 1-indexed
    return delta

def is_checkin_day(day_of_trial):
    """Returns True if today is a scheduled check-in day."""
    return day_of_trial in CHECKIN_DAYS

def get_occasion_number(day_of_trial):
    """Returns the 1-indexed occasion number for a given trial day."""
    try:
        return CHECKIN_DAYS.index(day_of_trial) + 1
    except ValueError:
        return None

def is_send_window(wake_time_str, participant_tz, window_minutes=25):
    """
    Returns True if the current time (in participant's timezone) is within
    [wake_time, wake_time + window_minutes].
    The 30-min cron job + 25-min window ensures we catch each wake time
    exactly once without double-sending.
    """
    tz       = pytz.timezone(participant_tz)
    now      = datetime.now(tz)
    hh, mm   = map(int, wake_time_str.split(":"))
    wake_dt  = now.replace(hour=hh, minute=mm, second=0, microsecond=0)
    window_end = wake_dt + timedelta(minutes=window_minutes)
    return wake_dt <= now < window_end

# ── TWILIO ────────────────────────────────────────────────────
def send_sms(to_number, pid, occasion):
    """Sends the check-in SMS with PID and occasion in the URL."""
    url     = f"{CHECKIN_APP_URL}?PID={pid}&occasion={occasion}"
    message = SMS_TEMPLATE.format(url=url)
    client  = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
    client.messages.create(
        body=message,
        from_=TWILIO_FROM_NUMBER,
        to=to_number
    )
    print(f"[SENT] PID={pid} | Occasion={occasion} | To={to_number} | URL={url}")

# ── MAIN ──────────────────────────────────────────────────────
def main():
    print(f"[RUN] Scheduler fired at {datetime.utcnow().isoformat()} UTC")

    try:
        tab          = get_sheet_tab3()
        participants = get_participants(tab)
    except Exception as e:
        print(f"[ERROR] Could not read Google Sheets: {e}")
        return

    for i, p in enumerate(participants):
        pid        = str(p.get(COL_PID, "")).strip()
        phone      = str(p.get(COL_PHONE, "")).strip()
        wake_time  = str(p.get(COL_WAKE_TIME, "")).strip()
        timezone   = str(p.get(COL_TIMEZONE, "")).strip()
        active     = str(p.get(COL_ACTIVE, "")).strip().upper()
        trial_start= str(p.get(COL_TRIAL_START, "")).strip()

        # Skip inactive participants or rows with missing data
        if active != "Y":
            continue
        if not all([pid, phone, wake_time, timezone, trial_start]):
            print(f"[SKIP] PID={pid} — missing required fields")
            continue

        try:
            day        = get_day_of_trial(trial_start, timezone)
            occasion   = get_occasion_number(day)

            if occasion is None:
                # Not a check-in day
                continue

            if not is_send_window(wake_time, timezone):
                # Not in the send window for this participant right now
                continue

            # Check if we've already sent this occasion (prevent double-send)
            sent_so_far = int(p.get(COL_OCCASION, 0) or 0)
            if occasion <= sent_so_far:
                print(f"[SKIP] PID={pid} — Occasion {occasion} already sent")
                continue

            # All checks passed — send SMS and update occasion counter
            send_sms(phone, pid, occasion)
            update_occasion(tab, i, occasion)

        except Exception as e:
            print(f"[ERROR] PID={pid}: {e}")

    print("[DONE] Scheduler run complete.")

if __name__ == "__main__":
    main()
