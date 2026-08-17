# Migrating off Render and Streamlit Cloud → Fly.io

**Future Self Formative Study — infrastructure migration guide**
Written for someone who does not write code. Every command is copy-and-paste.

---

## What is changing, and what is not

Your IRB approved Fly.io but not Render or Streamlit Cloud. Three things move:

| Piece | Where it lives today | Where it goes |
|---|---|---|
| Chatbot 1 — `chatbot1_app.py` | Streamlit Cloud | Fly app `fsf-chatbot1` |
| Chatbot 2 — `chatbot2_app.py` | Streamlit Cloud | Fly app `fsf-chatbot2` |
| SMS scheduler — `twilio_scheduler.py` | Render cron job | Fly app `fsf-scheduler` |

Three things **do not move**, and you do not need to tell the IRB anything about them:

- **The check-in webapp** (`check-in/index.html`) is a plain web page hosted on GitHub. It was never on Streamlit or Render.
- **The Apps Script backend** (`Code.gs`, `Monitor.gs`) runs inside Google.
- **Qualtrics, Twilio, Google Sheets, Dropbox** are untouched.

**The Streamlit *library* stays.** Your chatbots are still Streamlit apps and the code is unchanged. What you are dropping is Streamlit *Cloud*, the company's hosting service. This distinction is the thing to make explicit for the IRB — it is the difference between "we changed our software" (you didn't) and "we changed which company's server runs it" (you did).

### What is *not* changing in your code

Nothing. `chatbot1_app.py`, `chatbot2_app.py`, `llm_config.py`, `twilio_scheduler.py`, and both `.toml` config files are byte-for-byte identical. The migration is entirely new files sitting alongside them. That is deliberate: it makes the IRB amendment easy to write and means nothing that was already tested can silently break.

---

## Before you start — a note on how this works

Fly.io does not have a dashboard where you click buttons to deploy. You use a command-line tool called `flyctl`, typed into the **Terminal** app on your Mac.

If you have never used Terminal: open Spotlight (⌘ + Space), type `Terminal`, press Enter. A window with a text prompt appears. You type a command, press Enter, and it prints its output. That is all you will be doing.

Two conventions in this guide:

- Lines starting with `$` are commands to type (do **not** type the `$`).
- Anything in `ANGLE_BRACKETS` you replace with your own value.

If a command fails, stop and read the error — it usually says exactly what is wrong. Do not run the next step on top of a failed one.

---

## Part 1 — One-time setup

### Step 1. Install flyctl

In Terminal, paste this and press Enter:

```
$ curl -L https://fly.io/install.sh | sh
```

It will print a couple of lines at the end telling you to add something to your PATH. Close Terminal, open it again, then confirm it worked:

```
$ fly version
```

You should see a version number. If you instead see `command not found: fly`, the PATH step did not take — run the installer's suggested `export` lines, or restart your Mac.

### Step 2. Log in

```
$ fly auth login
```

This opens your browser. Sign in with the Fly.io account you already have. Come back to Terminal when the browser says you are logged in.

### Step 3. Get to your project folder

You need Terminal to be "inside" the folder containing your code. If your repo is cloned at `~/Documents/Future-Self-Formative`:

```
$ cd ~/Documents/Future-Self-Formative
```

Confirm you are in the right place — this should list `chatbot1_app.py` among others:

```
$ ls
```

> **Shortcut:** in Terminal type `cd ` (with a space), then drag the folder from Finder onto the Terminal window. It fills in the path for you. Press Enter.

### Step 4. Add the new files

Pull the new deployment files into this folder (they are in the bundle delivered with this guide). After copying them in, `ls` should now also show:

```
Dockerfile.chatbot          fly.chatbot1.toml       crontab
Dockerfile.scheduler        fly.chatbot2.toml       .dockerignore
entrypoint-chatbot.sh       fly.scheduler.toml      secrets_example.toml
requirements-scheduler.txt  MIGRATION.md
```

Then commit them to GitHub (from Terminal, or with GitHub Desktop if you prefer):

```
$ git add .
$ git commit -m "Add Fly.io deployment config; migrate off Render and Streamlit Cloud"
$ git push
```

---

## Part 2 — Collect your secrets

Your apps need API keys. Right now those keys live in two places you are about to shut down. **Collect them before you delete anything.**

### Step 5. Copy your Streamlit Cloud secrets

1. Go to <https://share.streamlit.io> and open Chatbot 1's app settings.
2. Click **Secrets**. You will see a block of text starting with `OPENAI_API_KEY = "sk-..."`.
3. Select all of it and copy it.
4. On your Mac, create a new plain-text file on your **Desktop** named `secrets.toml` and paste it in. Save.

> **Important:** put this file on your Desktop, **not** inside the project folder. If it ends up in the project folder it can get pushed to GitHub, and your API keys would become public. The included `.dockerignore` and the naming are set up to make that mistake hard, but the safest thing is to keep the file somewhere else entirely.

Open `secrets_example.toml` in the project folder and compare — your file should contain the same key names, including the `[gcp_service_account]` block at the bottom. If anything is missing, add it now.

### Step 6. Copy your Render environment variables

1. Go to your Render dashboard and open the cron job.
2. Click **Environment**.
3. Write down all six values somewhere safe:

```
TWILIO_ACCOUNT_SID
TWILIO_AUTH_TOKEN
TWILIO_FROM_NUMBER
GOOGLE_SHEET_ID
GOOGLE_CREDENTIALS      ← the long service-account JSON blob
CHECKIN_APP_URL         ← your GitHub Pages check-in URL
```

`GOOGLE_CREDENTIALS` is a very long single line of JSON. Copy it exactly, in full.

---

## Part 3 — Deploy Chatbot 1

### Step 7. Create the app

```
$ fly apps create fsf-chatbot1
```

If it says the name is taken, pick another (e.g. `fsf-chatbot1-um`) and change the `app = ` line at the top of `fly.chatbot1.toml` to match.

### Step 8. Upload the secrets

```
$ fly secrets set STREAMLIT_SECRETS_TOML="$(cat ~/Desktop/secrets.toml)" -a fsf-chatbot1
```

This takes your whole secrets file and stores it in Fly, encrypted. Fly will hand it to the app at startup, and a small startup script recreates the file Streamlit expects. **Your Python code is unchanged** — it still calls `st.secrets` exactly as before.

Confirm it landed (this shows the *name* only, never the value):

```
$ fly secrets list -a fsf-chatbot1
```

### Step 9. Deploy

```
$ fly deploy -c fly.chatbot1.toml
```

This takes 3–8 minutes the first time. You will see a lot of scrolling build output — that is normal. You are looking for a green success message and a URL at the end.

### Step 10. Check it works

```
$ fly open -c fly.chatbot1.toml
```

Your browser opens `https://fsf-chatbot1.fly.dev`. To test properly, add a participant ID exactly as you did on Streamlit Cloud:

```
https://fsf-chatbot1.fly.dev/?pid=TEST01
```

Walk through a short conversation and confirm a row appears in Google Sheets Tab 1.

If the page shows an error, look at the logs:

```
$ fly logs -a fsf-chatbot1
```

---

## Part 4 — Deploy Chatbot 2

Identical, with the name and config file changed:

```
$ fly apps create fsf-chatbot2
$ fly secrets set STREAMLIT_SECRETS_TOML="$(cat ~/Desktop/secrets.toml)" -a fsf-chatbot2
$ fly deploy -c fly.chatbot2.toml
```

Test at `https://fsf-chatbot2.fly.dev/?pid=TEST01` and confirm a row lands in Google Sheets Tab 2.

Both chatbots use the same secrets file — that is expected, they share the same API keys and the same Google Sheet.

---

## Part 5 — Deploy the SMS scheduler

This one replaces the Render cron job.

### Step 11. Create the app

```
$ fly apps create fsf-scheduler
```

### Step 12. Upload the six secrets

Paste this as one block, filling in your real values from Step 6. Keep the quotes.

```
$ fly secrets set \
    TWILIO_ACCOUNT_SID="ACxxxxxxxx" \
    TWILIO_AUTH_TOKEN="xxxxxxxx" \
    TWILIO_FROM_NUMBER="+13135550123" \
    GOOGLE_SHEET_ID="1wxyeAYdKC7f5LcvOxuhtYHg8MQdF41zjOoYgMPhOr2k" \
    GOOGLE_CREDENTIALS='{"type":"service_account", ... }' \
    CHECKIN_APP_URL="https://sooart0504.github.io/Future-Self-Formative/check-in/" \
    -a fsf-scheduler
```

> Note `GOOGLE_CREDENTIALS` uses **single** quotes, not double. The JSON contains double quotes inside it, so single quotes on the outside keep it intact.

### Step 13. Deploy

```
$ fly deploy -c fly.scheduler.toml
```

### Step 14. Confirm exactly one machine is running

**Do not skip this.** The cron runs on every machine. Two machines means every participant gets two identical texts.

```
$ fly scale show -a fsf-scheduler
```

It must report a count of **1**. If it reports anything else:

```
$ fly scale count 1 -a fsf-scheduler
```

### Step 15. Watch it fire

```
$ fly logs -a fsf-scheduler
```

Leave this running until the clock hits the next `:00` or `:30`. You should see:

```
[RUN] Scheduler fired at 2026-08-17T20:30:00 UTC
[DONE] Scheduler run complete.
```

Seeing `[RUN]` and `[DONE]` means the migration worked. With no active participants in Tab 3, nothing is sent between them — that is correct. Press `Control + C` to stop watching.

---

## Part 6 — Update your URLs

Your chatbots now live at new addresses. Update every place the old `*.streamlit.app` URLs appear:

- [ ] **Qualtrics** — the links that send participants into Chatbot 1 and Chatbot 2
- [ ] **README.md** — the placeholder URLs at the top
- [ ] **Operations Manual** — any session scripts that tell staff which link to open
- [ ] **Your own bookmarks**

| Old | New |
|---|---|
| `https://<...>.streamlit.app/?pid=FSS_001` | `https://fsf-chatbot1.fly.dev/?pid=FSS_001` |
| `https://<...>-2.streamlit.app/?pid=FSS_001` | `https://fsf-chatbot2.fly.dev/?pid=FSS_001` |

The check-in SMS link does **not** change — that is your GitHub Pages URL, which was never affected.

---

## Part 7 — Shut down Render and Streamlit Cloud

Only after all three Fly apps are confirmed working, and only after you have run at least one real end-to-end test.

- [ ] **Render** — delete the cron job. Two schedulers running at once would double-text participants, so do this *promptly* after the Fly scheduler is confirmed.
- [ ] **Streamlit Cloud** — delete both apps.
- [ ] Take a screenshot of each deletion for your IRB file.
- [ ] Rotate your API keys if you want to be thorough — the old platforms held copies.

> **Order matters.** Delete the Render cron job before running a live participant check-in on Fly. If both are live on the same day, participants receive duplicate texts.

---

## Things to know

### Cost

Roughly **$11–13/month** total: two chatbot machines at 1GB (~$5 each) and one scheduler at 512MB (~$4). Fly bills by the second for what is actually running.

The chatbots are configured to stay awake rather than sleep when idle (`auto_stop_machines = "off"`). This costs a few dollars more per month and is the right call — participants hit these apps live during a Zoom session, and a sleeping machine takes several seconds to wake. Do not "optimize" this setting.

### A landmine in your scheduler worth knowing about

While verifying the migration I simulated a full day of cron runs against every possible wake time. Something to be aware of — **this is pre-existing behavior inherited from Render, not something the migration introduced**:

`twilio_scheduler.py` uses a 25-minute send window paired with a 30-minute schedule. That works perfectly for wake times ending in **:00 or :30** — every one of the 48 possible values gets exactly one text, no duplicates, no misses.

But a wake time like **07:05 or 07:31 gets zero texts.** The participant is silently skipped for the entire trial, with no error anywhere. Nothing in the code prevents that value from being typed into Tab 3.

**What to do:** when filling in the `wake_time` column of Google Sheets Tab 3, the minutes must be exactly `00` or `30`. `07:00` and `07:30` are fine; `07:15` is not. Your protocol already specifies 30-minute increments, so this only matters as a data-entry guardrail. It is worth adding a note to the Operations Manual, and worth spot-checking Tab 3 before each participant's trial begins.

### Making changes later

To change a chatbot prompt, edit the `.toml` file, then:

```
$ fly deploy -c fly.chatbot1.toml
```

There is no auto-deploy from GitHub the way Streamlit Cloud had. You run this command yourself. That is a small inconvenience and a real benefit: nothing reaches participants without you deciding it should.

### Useful commands

```
$ fly logs -a fsf-chatbot1        # see what an app is doing right now
$ fly status -a fsf-scheduler     # is it running?
$ fly apps list                   # all three apps
$ fly secrets list -a fsf-chatbot1  # secret names (never values)
$ fly machine restart -a fsf-scheduler  # kick it if it seems stuck
```

### If something goes wrong

| Symptom | Cause | Fix |
|---|---|---|
| `FATAL: the STREAMLIT_SECRETS_TOML secret is not set` | Step 8 was skipped or failed | Re-run Step 8, then `fly deploy` again |
| Chatbot loads but errors on the first message | Bad or missing `OPENAI_API_KEY` | Check your Desktop `secrets.toml`, re-run Step 8 |
| Chatbot works but nothing reaches Google Sheets | Service account lacks edit access | Share the Sheet with the `client_email` from `[gcp_service_account]` |
| Scheduler logs show `KeyError: 'TWILIO_ACCOUNT_SID'` | A secret from Step 12 is missing | `fly secrets list -a fsf-scheduler`, re-set what's absent |
| Participants get two texts | Two scheduler machines, or Render still live | Step 14, and confirm the Render job is deleted |
| A participant gets no texts at all | Off-grid `wake_time` in Tab 3 | Set minutes to `00` or `30` — see the landmine section |

---

## What still needs doing

The migration itself is covered above. Separately, your study documents describe infrastructure that does not match your code:

**System Architecture, Study Protocol §9.1, and the Operations Manual all describe a "Streamlit lookup app"** that reads Google Sheets by PID and returns personalized content to Qualtrics. That app does not exist. What actually does the job is `check-in/index.html` on GitHub Pages, calling a Google Apps Script web app (`Code.gs`). Google Apps Script is not listed anywhere in your System Architecture document.

This matters more than the Render/Streamlit swap: the IRB is reviewing a data-flow diagram that omits a system which reads participant narratives and writes check-in responses. Those three documents need updating to (a) replace Render and Streamlit Cloud with Fly.io, and (b) describe the check-in webapp and Apps Script backend as they actually work.
