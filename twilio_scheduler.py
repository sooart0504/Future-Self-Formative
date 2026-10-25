"""
Future Self Formative Study — Twilio SMS Scheduler
===================================================

Runs every 30 minutes on Fly.io (via Supercronic, see crontab).

WHAT CHANGED FROM THE PREVIOUS VERSION
--------------------------------------
Check-in days used to be a fixed list written into this file:
    CHECKIN_DAYS = [1, 3, 5, 7, 8, 11, 14, 17, 21, 28]

They are now randomized per participant and generated once at
enrollment by the Apps Script generator, which writes ten rows per
participant to the "CheckinSchedule" tab. This script no longer
decides WHEN anyone gets a text — it looks it up.

Three other changes:
  * The double-send guard moved from Tab 3's current_occasion to
    the sms_sent_at column on each scheduled row.
  * Send failures are written back to the sheet (status / error)
    rather than only printed, so a suspended Twilio account is
    visible where you are already looking.
  * DRY_RUN mode logs what it would send without calling Twilio
    and without writing anything.

ENVIRONMENT VARIABLES
---------------------
    TWILIO_ACCOUNT_SID
    TWILIO_AUTH_TOKEN
    TWILIO_FROM_NUMBER      e.g. "+13135550123"
    GOOGLE_SHEET_ID
    GOOGLE_CREDENTIALS      service account JSON, one line
    CHECKIN_APP_URL         e.g. "https://sooart0504.github.io/.../check-in/"
    DRY_RUN                 optional. "1" / "true" = log only, send nothing.
"""

import os
import json
from datetime import datetime, date, timedelta

import pytz
import gspread
from google.oauth2.service_account import Credentials
from twilio.rest import Client

# ── CONFIGURATION ─────────────────────────────────────────────

TWILIO_ACCOUNT_SID = os.environ["TWILIO_ACCOUNT_SID"]
TWILIO_AUTH_TOKEN  = os.environ["TWILIO_AUTH_TOKEN"]
TWILIO_FROM_NUMBER = os.environ["TWILIO_FROM_NUMBER"]

GOOGLE_SHEET_ID    = os.environ["GOOGLE_SHEET_ID"]
GOOGLE_CREDENTIALS = os.environ["GOOGLE_CREDENTIALS"]
CHECKIN_APP_URL    = os.environ["CHECKIN_APP_URL"]

DRY_RUN = os.environ.get("DRY_RUN", "").strip().lower() in ("1", "true", "yes")

TAB_SCHEDULE = "Schedule"
TAB_CHECKIN_SCHEDULE = "CheckinSchedule"

# Tab 3 — participant level
COL_PID       = "PID"
COL_PHONE     = "phone"
COL_WAKE_TIME = "wake_time"      # "HH:MM", 24-hour, must end :00 or :30
COL_TIMEZONE  = "timezone"       # IANA, e.g. "America/Detroit"
COL_ACTIVE    = "active"         # "Y" / "N"

# Tab 6 — one row per participant per check-in
COL_CS_PID       = "PID"
COL_CS_OCCASION  = "occasion"
COL_CS_DATE      = "scheduled_date"   # YYYY-MM-DD
COL_CS_SENT_AT   = "sms_sent_at"
COL_CS_STATUS    = "status"           # SENT / FAILED
COL_CS_ERROR     = "error"

SEND_WINDOW_MINUTES = 25   # paired with the 30-minute cron; see is_send_window

SMS_TEMPLATE = (
    "Good morning! It's time for your morning check-in. "
    "Tap the link to get started: {url}"
)


# ── GOOGLE SHEETS ─────────────────────────────────────────────

def open_sheet():
    creds_dict = json.loads(GOOGLE_CREDENTIALS)
    scopes = ["https://www.googleapis.com/auth/spreadsheets"]
    creds = Credentials.from_service_account_info(creds_dict, scopes=scopes)
    return gspread.authorize(creds).open_by_key(GOOGLE_SHEET_ID)


def require_columns(tab_name, headers, needed):
    """Fail loudly and specifically rather than writing to the wrong column."""
    missing = [c for c in needed if c not in headers]
    if missing:
        raise RuntimeError(
            f'Tab "{tab_name}" is missing column(s): {", ".join(missing)}. '
            f'Found: {", ".join(headers)}'
        )


def write_cells(tab, row_number, headers, updates):
    """
    Write {column_name: value} to a row, located BY HEADER NAME.
    row_number is 1-based including the header row.
    """
    for col_name, value in updates.items():
        col_index = headers.index(col_name) + 1
        tab.update_cell(row_number, col_index, value)


# ── TIMING ────────────────────────────────────────────────────

def local_today(timezone_name):
    """Today's calendar date in the participant's own timezone."""
    return datetime.now(pytz.timezone(timezone_name)).strftime("%Y-%m-%d")


def normalize_date(value):
    """
    Return YYYY-MM-DD for whatever the sheet hands back.

    This exists because Google Sheets may store scheduled_date either as
    plain text or as a real date value, and when it is a date value the
    text that comes back depends on the spreadsheet's locale — "11/3/2026"
    rather than "2026-11-03". Matching on the raw string would then fail
    silently and nobody would ever be texted.

    The generator formats that column as plain text, so this is a second
    line of defence rather than the main one.
    """
    if value is None:
        return ""
    if isinstance(value, datetime):
        return value.strftime("%Y-%m-%d")
    if isinstance(value, date):
        return value.strftime("%Y-%m-%d")

    text = str(value).strip()
    if not text:
        return ""
    # US ordering first — the study spreadsheet is US-locale. A date like
    # 03/04/2026 is genuinely ambiguous, which is why the column is text.
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%Y/%m/%d", "%m-%d-%Y", "%d/%m/%Y"):
        try:
            return datetime.strptime(text, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return text


def is_send_window(wake_time_str, timezone_name):
    """
    True if we are inside [wake_time, wake_time + 25 minutes] right now,
    in the participant's timezone.

    The 25-minute window is deliberately paired with the 30-minute cron so
    each wake time is caught exactly once.

    IMPORTANT: this only works when wake_time minutes are :00 or :30.
    An off-grid value such as 07:05 or 07:31 falls between windows and the
    participant receives NOTHING, all trial long. The check below catches it.
    """
    tz = pytz.timezone(timezone_name)
    now = datetime.now(tz)
    hh, mm = map(int, wake_time_str.split(":"))
    wake = now.replace(hour=hh, minute=mm, second=0, microsecond=0)
    return wake <= now < wake + timedelta(minutes=SEND_WINDOW_MINUTES)


def wake_time_is_on_grid(wake_time_str):
    try:
        _, mm = wake_time_str.split(":")
        return int(mm) in (0, 30)
    except Exception:
        return False


def normalize_phone(value):
    """
    Return a Twilio-ready E.164 number, or "" if it cannot be worked out.

    Google Sheets treats a leading "+" as the start of a formula, so a
    number typed as +18475551234 comes back as 18475551234 with the plus
    silently removed. Rather than relying on whoever types it to win that
    argument every time, the number is repaired here.

        (847) 555-1234    -> +18475551234
        847-555-1234      -> +18475551234
        18475551234       -> +18475551234
        +44 20 7946 0000  -> +442079460000   (already explicit, left alone)

    Anything that is not a recognisable US 10/11-digit number and does not
    already start with "+" returns "" so the caller can warn and skip,
    rather than handing Twilio something that will be rejected.
    """
    if value is None:
        return ""
    text = str(value).strip()
    if not text:
        return ""

    explicit_plus = text.startswith("+")
    digits = "".join(ch for ch in text if ch.isdigit())
    if not digits:
        return ""

    if explicit_plus:
        return "+" + digits          # trust an explicit country code
    if len(digits) == 10:
        return "+1" + digits         # US, no country code
    if len(digits) == 11 and digits.startswith("1"):
        return "+" + digits          # US, country code but no plus
    return ""                        # not safe to guess


# ── TWILIO ────────────────────────────────────────────────────

_twilio = None

def twilio_client():
    global _twilio
    if _twilio is None:
        _twilio = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
    return _twilio


def send_sms(to_number, pid, occasion):
    url = f"{CHECKIN_APP_URL}?PID={pid}&occasion={occasion}"
    body = SMS_TEMPLATE.format(url=url)
    if DRY_RUN:
        print(f"[DRY-RUN] would text PID={pid} occasion={occasion} to={to_number}")
        print(f"[DRY-RUN]   {body}")
        return url
    twilio_client().messages.create(body=body, from_=TWILIO_FROM_NUMBER, to=to_number)
    print(f"[SENT] PID={pid} occasion={occasion} to={to_number}")
    return url


# ── MAIN ──────────────────────────────────────────────────────

def main():
    started = datetime.utcnow().isoformat()
    print(f"[RUN] Scheduler fired at {started} UTC" + ("  (DRY RUN)" if DRY_RUN else ""))

    try:
        book = open_sheet()
        sched_tab = book.worksheet(TAB_SCHEDULE)
        cs_tab = book.worksheet(TAB_CHECKIN_SCHEDULE)
        participants = sched_tab.get_all_records()
        schedule_rows = cs_tab.get_all_records()
        cs_headers = cs_tab.row_values(1)
    except Exception as e:
        print(f"[FATAL] Could not read the spreadsheet: {e}")
        return

    try:
        require_columns(TAB_SCHEDULE, sched_tab.row_values(1),
                        [COL_PID, COL_PHONE, COL_WAKE_TIME, COL_TIMEZONE, COL_ACTIVE])
        require_columns(TAB_CHECKIN_SCHEDULE, cs_headers,
                        [COL_CS_PID, COL_CS_OCCASION, COL_CS_DATE,
                         COL_CS_SENT_AT, COL_CS_STATUS, COL_CS_ERROR])
    except RuntimeError as e:
        print(f"[FATAL] {e}")
        return

    # Index the schedule rows so we can find one quickly.
    # Value is the row number in the sheet (header is row 1).
    by_key = {}
    for i, row in enumerate(schedule_rows):
        key = (str(row.get(COL_CS_PID, "")).strip(),
               normalize_date(row.get(COL_CS_DATE, "")))
        by_key[key] = (i + 2, row)

    if not by_key:
        print(f"[WARN] The {TAB_CHECKIN_SCHEDULE} tab has no rows. "
              f"No schedules have been generated yet, so nobody can be texted.")

    sent = skipped = failed = 0

    for p in participants:
        pid      = str(p.get(COL_PID, "")).strip()
        phone    = str(p.get(COL_PHONE, "")).strip()
        wake     = str(p.get(COL_WAKE_TIME, "")).strip()
        tzname   = str(p.get(COL_TIMEZONE, "")).strip()
        active   = str(p.get(COL_ACTIVE, "")).strip().upper()

        if not pid or active != "Y":
            continue
        if not all([phone, wake, tzname]):
            print(f"[SKIP] PID={pid} — missing phone, wake_time or timezone")
            skipped += 1
            continue

        e164 = normalize_phone(phone)
        if not e164:
            print(f"[WARN] PID={pid} — phone '{phone}' is not a usable number. "
                  f"Expected 10 or 11 US digits, or an explicit +country number. "
                  f"This participant will receive NO texts.")
            skipped += 1
            continue
        phone = e164
        if not wake_time_is_on_grid(wake):
            print(f"[WARN] PID={pid} — wake_time '{wake}' is not on the :00/:30 grid. "
                  f"This participant will receive NO texts. Fix it in the {TAB_SCHEDULE} tab.")
            skipped += 1
            continue

        try:
            today = local_today(tzname)
        except Exception as e:
            print(f"[SKIP] PID={pid} — bad timezone '{tzname}': {e}")
            skipped += 1
            continue

        hit = by_key.get((pid, today))
        if not hit:
            continue                      # not a check-in day for this participant

        row_number, row = hit
        occasion = row.get(COL_CS_OCCASION, "")

        if str(row.get(COL_CS_SENT_AT, "")).strip():
            continue                      # already sent — the double-send guard

        if not is_send_window(wake, tzname):
            continue                      # right day, wrong half-hour

        try:
            send_sms(phone, pid, occasion)
            if not DRY_RUN:
                write_cells(cs_tab, row_number, cs_headers, {
                    COL_CS_SENT_AT: datetime.now(pytz.timezone(tzname)).strftime("%Y-%m-%d %H:%M"),
                    COL_CS_STATUS:  "SENT",
                    COL_CS_ERROR:   "",
                })
            sent += 1

        except Exception as e:
            message = str(e)[:400]
            print(f"[ERROR] PID={pid} occasion={occasion}: {message}")
            failed += 1
            if not DRY_RUN:
                try:
                    # sms_sent_at stays EMPTY so a later run inside the same
                    # window can retry a transient failure.
                    write_cells(cs_tab, row_number, cs_headers, {
                        COL_CS_STATUS: "FAILED",
                        COL_CS_ERROR:  message,
                    })
                except Exception as e2:
                    print(f"[ERROR] could not record the failure in the sheet: {e2}")

    print(f"[DONE] sent={sent} failed={failed} skipped={skipped}"
          + ("  (DRY RUN — nothing was sent or written)" if DRY_RUN else ""))


if __name__ == "__main__":
    main()
