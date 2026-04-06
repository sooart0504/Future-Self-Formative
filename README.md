# Future Self Formative Study — Chatbot System

## Repository Structure

```
future-self-study/
├── chatbot1_app.py           # Streamlit app — Chatbot 1 (Ideal Future Self)
├── chatbot2_app.py           # Streamlit app — Chatbot 2 (Feared Future Self)
├── llm_config.py             # Shared config class (used by both apps)
├── chatbot1_config.toml      # Questions, prompts, personas for Chatbot 1
├── chatbot2_config.toml      # Questions, prompts, personas for Chatbot 2
├── twilio_scheduler.py       # Standalone cron script for daily SMS delivery
├── requirements.txt
└── .streamlit/
    └── secrets_example.toml  # Secrets template (do not commit real secrets)
```

---

## Chatbot 1 — Ideal Future Self

**Entry point:** `chatbot1_app.py`
**URL:** `https://your-streamlit-url.streamlit.app/?pid=FSS_001`

**Flow:**
1. Values → Active Life → Future Self Description → Timeline (Q1–Q5 conversation)
2. Ideal Day (Q1–Q3 conversation)
3. Anchoring Statements (8-stem form)
4. Story generation (3 persona versions)
5. Participant picks one story
6. Story review + anchoring display (read-only)
7. Optional revision (max 2 rounds, story only)
8. Save to Google Sheets Tab 1

**Google Sheets Tab 1 columns:**
PID | timestamp_start | timestamp_end | persona_selected |
values | full_life | health_foundation | future_self_description | timeline |
ideal_day_scene | ideal_day_feeling | ideal_day_reflection |
narrative_ideal |
anchor_ideal | anchor_weather | anchor_busy | anchor_travel |
anchor_physical | anchor_access | anchor_other | anchor_rest |
revision_count | chat_log_t1 | chat_log_t2

---

## Chatbot 2 — Feared Future Self

**Entry point:** `chatbot2_app.py`
**URL:** `https://your-streamlit-url-2.streamlit.app/?pid=FSS_001`

**Flow:**
1. Feared future self questions (Q1–Q4 conversation)
2. Story generation (3 persona versions)
3. Participant picks one story
4. Story review
5. Optional revision (max 2 rounds)
6. Save to Google Sheets Tab 2

**Google Sheets Tab 2 columns:**
PID | timestamp_start | timestamp_end | persona_selected |
fears | values_misalignment | body_health | feared_self_description |
narrative_feared | revision_count | chat_log

---

## Twilio Scheduler

**Entry point:** `twilio_scheduler.py`
**Deployment:** Render or Railway — cron job, runs every minute

**Required environment variables:**
- `TWILIO_ACCOUNT_SID`
- `TWILIO_AUTH_TOKEN`
- `TWILIO_FROM_NUMBER`
- `GOOGLE_SHEET_KEY`
- `GOOGLE_CREDS_JSON` (service account JSON as a string)

**Google Sheets Tab 3 (schedule table) columns:**
PID | phone | wake_time (HH:MM) | timezone (IANA) | active (Y/N)

---

## Google Sheets Setup

The study uses one Google Sheets file with three tabs:
- **Tab 1** (index 0): Chatbot 1 outputs
- **Tab 2** (index 1): Chatbot 2 outputs
- **Tab 3** (index 2): Participant schedule table (read by Twilio scheduler)

Share the sheet with your Google Cloud service account email (edit access).

---

## Streamlit Deployment

Each chatbot is deployed as a separate Streamlit Cloud app pointing to the same repo but a different main file:
- Chatbot 1: main file = `chatbot1_app.py`
- Chatbot 2: main file = `chatbot2_app.py`

Add all secrets from `secrets_example.toml` in the Streamlit Cloud secrets manager.

---

## Qualtrics Links (Placeholder)

All Qualtrics survey links are currently placeholders:
```
https://umich.qualtrics.com/jfe/form/SV_PLACEHOLDER?PID={pid}
```
Replace `SV_PLACEHOLDER` with real survey IDs once surveys are built.
The Twilio scheduler and chatbot completion screens use this template.
