# Migrating to Fly.io — without ever opening Terminal

**Future Self Formative Study — infrastructure migration**
Everything below happens in a web browser. No commands, no Terminal.

---

## How this works

Fly.io has no "Deploy" button on its website. Deploying genuinely does require commands to be typed somewhere.

The trick is that **it doesn't have to be you typing them, on your computer.** GitHub has a feature called Actions: you click a button on GitHub's website, GitHub rents a temporary computer in its own data center, runs the commands there, shows you the output, and throws the computer away. The commands still run — you just never see a Terminal.

I've written that button for you. Your only jobs are uploading some files, copying one token between two websites, and clicking Run.

**What you'll be using:**

| Website | What for |
|---|---|
| github.com | Your code, and the deploy button |
| fly.io/dashboard | Creating a token, and storing your API keys |

---

## Overview

Seven steps, roughly 45 minutes, mostly waiting.

1. Put the new files in your GitHub repo
2. Create a token on Fly
3. Give that token to GitHub
4. Click Run → creates the three apps
5. Add your API keys in the Fly dashboard
6. Click Run again → deploys everything
7. Test, update your links, shut down the old services

---

## Step 1 — Put the new files in your repo

1. Download `fly-migration.zip` and **double-click it** to unzip. You get a folder with 14 files inside.
2. Go to <https://github.com/sooart0504/Future-Self-Formative>
3. Click **Add file** (top right, near the green Code button) → **Upload files**
4. Open the unzipped folder in Finder, select everything (⌘A) **except `deploy-fly.yml`** — that one has to go somewhere specific and is handled in 1b below. Then **drag the rest onto the GitHub page**
5. Scroll down. In the box under "Commit changes," type: `Add Fly.io deployment config`
6. Click **Commit changes**

> **Note:** one of the files is named `.dockerignore`, starting with a dot. Finder sometimes hides dot-files. If you don't see it, press **⌘ + Shift + . (period)** in Finder to reveal hidden files, then include it in the drag.

### 1b. Add the deploy button

This one file has to go in a specific folder, so it's created slightly differently.

1. On your repo page, click **Add file** → **Create new file**
2. In the filename box at the top, type exactly this — **including the slashes**:

   ```
   .github/workflows/deploy-fly.yml
   ```

   As you type each `/`, GitHub turns it into a folder. That's what you want.
3. Open `deploy-fly.yml` from the unzipped folder in TextEdit, select all, copy
4. Paste it into the big editing box on GitHub
5. Click **Commit changes** → **Commit changes** again in the popup

---

## Step 2 — Create a token on Fly

A token is a long password that lets GitHub act on your Fly account.

1. Go to <https://fly.io/dashboard> and sign in
2. In the left sidebar, click **Tokens** (under your organization name)
3. Click **Create org deploy token**
4. Name it `github-actions`, set the expiry to the longest option offered
5. Click **Create**
6. **Copy the entire token.** It's very long and starts with `FlyV1 `.

> Copy all of it, including the `FlyV1` at the front and the space after it. This is shown **once** — if you navigate away without copying, just make another one.

Keep this browser tab open.

---

## Step 3 — Give the token to GitHub

1. Go to <https://github.com/sooart0504/Future-Self-Formative/settings/secrets/actions>
2. Click the green **New repository secret**
3. **Name:** `FLY_API_TOKEN` — exactly that, all capitals, with underscores
4. **Secret:** paste the token from Step 2
5. Click **Add secret**

GitHub now stores it encrypted. Even you can't read it back — that's intended. If you ever think it's wrong, delete it and add a fresh one.

---

## Step 4 — Click Run (first time): create the apps

1. Go to <https://github.com/sooart0504/Future-Self-Formative/actions>
2. In the left sidebar, click **Deploy to Fly.io**
3. On the right, click the **Run workflow** dropdown
4. Leave the choice on **create-apps-only**
5. Click the green **Run workflow**

Wait about 10 seconds, then refresh the page. A run appears with a spinning yellow dot. Click it, then click **deploy**, to watch it work. It takes about a minute.

**Yellow dot** = running. **Green check** = worked. **Red X** = something's wrong — click into it, read the last few red lines, and see the troubleshooting table at the bottom.

When it's green, you'll have three empty apps: `fsf-chatbot1`, `fsf-chatbot2`, `fsf-scheduler`.

---

## Step 5 — Add your API keys in the Fly dashboard

Nothing is deployed yet, on purpose — the apps need their keys first.

### 5a. Collect your keys

**From Streamlit Cloud** (<https://share.streamlit.io> → Chatbot 1 → Settings → Secrets): copy the whole block of text. It starts with `OPENAI_API_KEY` and includes a `[gcp_service_account]` section at the bottom. Paste it into a TextEdit document for now.

**From Render** (your dashboard → the cron job → Environment): write down all six values.

```
TWILIO_ACCOUNT_SID       GOOGLE_SHEET_ID
TWILIO_AUTH_TOKEN        GOOGLE_CREDENTIALS   ← the very long JSON blob
TWILIO_FROM_NUMBER       CHECKIN_APP_URL
```

> Do this **before** cancelling anything. Once those services are deleted the keys are gone, and some can't be recovered.

### 5b. Chatbot 1 and Chatbot 2

For **each** of `fsf-chatbot1` and `fsf-chatbot2`:

1. Go to <https://fly.io/dashboard>, click the app
2. Click **Secrets** in the left sidebar
3. Click **New secret** (or **Set secret**)
4. **Name:** `STREAMLIT_SECRETS_TOML`
5. **Value:** paste the entire Streamlit block from 5a — all of it, in one field, including the `[gcp_service_account]` section
6. Save

Both chatbots get the same value. That's correct — they share the same keys and the same Google Sheet.

> **Why one big secret instead of many?** Your chatbot code reads its keys through `st.secrets`, a Streamlit Cloud feature that reads a file. Fly doesn't have that feature. Rather than rewrite your Python — which you'd then have to re-test and re-document for the IRB — the app rebuilds that file at startup from this one secret. Your code is untouched.

### 5c. The scheduler

Go to `fsf-scheduler` → **Secrets**, and add **six separate secrets**, names exactly as below:

| Name | Value |
|---|---|
| `TWILIO_ACCOUNT_SID` | from Render |
| `TWILIO_AUTH_TOKEN` | from Render |
| `TWILIO_FROM_NUMBER` | e.g. `+13135550123` |
| `GOOGLE_SHEET_ID` | from Render |
| `GOOGLE_CREDENTIALS` | the long JSON blob, pasted whole |
| `CHECKIN_APP_URL` | your GitHub Pages check-in URL |

Names must match exactly — all capitals, underscores, no spaces. A typo here means that app silently can't find its key.

> **Your keys never touch GitHub.** The only thing GitHub holds is the Fly token from Step 3, which lets it deploy but grants no access to your OpenAI, Twilio, or Google credentials. Those live only in Fly. That's a cleaner story for the IRB, and it's worth saying plainly in your amendment.

---

## Step 6 — Click Run (second time): deploy

1. Back to <https://github.com/sooart0504/Future-Self-Formative/actions>
2. **Deploy to Fly.io** → **Run workflow**
3. This time change the dropdown to **all**
4. Click **Run workflow**

This takes 5–10 minutes — it's building all three apps from scratch. Lots of scrolling text is normal.

The last step checks something important automatically: that the scheduler is running **exactly one** machine. Two machines would mean every participant gets two identical check-in texts. If it finds more than one, the run fails on purpose rather than letting that reach a participant.

---

## Step 7 — Test everything

### The chatbots

Open these in your browser:

- `https://fsf-chatbot1.fly.dev/?pid=TEST01`
- `https://fsf-chatbot2.fly.dev/?pid=TEST01`

Walk through a short conversation in each and confirm a new row appears in Google Sheets Tab 1 and Tab 2.

### The scheduler

1. Fly dashboard → `fsf-scheduler` → **Live Logs**
2. Wait until the clock hits the next `:00` or `:30`
3. You should see:

```
[RUN] Scheduler fired at 2026-08-17T20:30:00 UTC
[DONE] Scheduler run complete.
```

Those two lines mean the migration worked. With no active participants in Tab 3, nothing sends in between — that's correct.

### Update your links

Your chatbots have new addresses:

| Old | New |
|---|---|
| `https://<...>.streamlit.app/?pid=FSS_001` | `https://fsf-chatbot1.fly.dev/?pid=FSS_001` |
| `https://<...>-2.streamlit.app/?pid=FSS_001` | `https://fsf-chatbot2.fly.dev/?pid=FSS_001` |

- [ ] Qualtrics — the links sending participants into each chatbot
- [ ] Operations Manual — session scripts telling staff which link to open
- [ ] README.md
- [ ] Your bookmarks

The check-in SMS link does **not** change — that's your GitHub Pages URL, which was never affected.

### Shut down the old services

Only after everything above is confirmed working:

- [ ] **Render** — delete the cron job. Do this promptly: two schedulers running at once means duplicate texts.
- [ ] **Streamlit Cloud** — delete both apps
- [ ] Screenshot each deletion for your IRB file
- [ ] Consider rotating your API keys — the retired platforms held copies

---

## Making changes later

Changing a chatbot prompt, without a terminal:

1. On GitHub, click into `chatbot1_config.toml`
2. Click the **pencil icon** (top right)
3. Edit the text, click **Commit changes**
4. Go to **Actions** → **Deploy to Fly.io** → **Run workflow** → choose **chatbot1** → Run

Editing the file alone changes nothing that participants see. It only ships when you click Run. That's intentional — nothing reaches a participant without you deciding it should.

---

## If something goes wrong

| What you see | What it means | What to do |
|---|---|---|
| Red X, `FLY_API_TOKEN is not set` | Step 3 didn't take | Re-add the secret; the name must be exactly `FLY_API_TOKEN` |
| Red X, `Error: not authorized` | Token wrong or expired | Make a new token (Step 2), replace it in GitHub (Step 3) |
| Red X, `name is already taken` | Someone else has that app name | Tell me and I'll rename all three in the config files |
| Red X on the machine-count check | Scheduler has 2+ machines | Fly dashboard → `fsf-scheduler` → Machines → delete the extras → run again |
| Chatbot page: `FATAL: STREAMLIT_SECRETS_TOML is not set` | Step 5b missing or misnamed | Re-add it; name must match exactly |
| Chatbot loads, errors on first message | Bad `OPENAI_API_KEY` | Check the value inside your secrets block |
| Chatbot works, nothing reaches Sheets | Service account lacks access | Share the Sheet with the `client_email` from `[gcp_service_account]` |
| Scheduler logs: `KeyError: 'TWILIO_ACCOUNT_SID'` | A Step 5c secret is missing | Check all six names in the Fly dashboard |
| A participant gets no texts at all | Off-grid `wake_time` — see below | Set minutes to `00` or `30` |

To see what an app is doing at any time: Fly dashboard → the app → **Live Logs**. That's the same information a terminal would show you.

---

## Two things worth knowing

### The wake-time landmine

**This is pre-existing behavior inherited from Render, not something the migration introduced** — but it can void a participant's entire trial silently.

`twilio_scheduler.py` uses a 25-minute send window on a 30-minute schedule. For wake times ending in `:00` or `:30` this is exact — I simulated all 48 possible values and each gets precisely one text, no duplicates, no misses.

But a wake time of `07:05` or `07:31` gets **zero** texts, for all 28 days. No error is logged. The participant simply never hears from the study.

**What to do:** in Google Sheets Tab 3, the `wake_time` minutes must be exactly `00` or `30`. `07:00` and `07:30` are fine; `07:15` is not. Your protocol already specifies 30-minute increments, so treat this as a data-entry guardrail — worth adding to the Operations Manual and spot-checking before each participant's trial starts.

### Cost

About **$11–13/month**: two chatbot machines at 1GB (~$5 each) and one scheduler at 512MB (~$4).

The chatbots are set to stay awake rather than sleep when idle. That costs a few dollars more and is the right call — participants hit them live during a Zoom session, and a sleeping machine takes several seconds to wake. Please don't "optimize" that setting.

---

## Still outstanding

Your study documents describe infrastructure that doesn't match your code. The **System Architecture**, **Study Protocol §9.1**, and **Operations Manual** all describe a *"Streamlit lookup app"* that reads Google Sheets by PID. That app doesn't exist. The real check-in path is `check-in/index.html` on GitHub Pages calling a **Google Apps Script** web app (`Code.gs`) — and Apps Script appears nowhere in your System Architecture: not in the System Catalog, not in the Data Flows table, not in the Data Separation Rules.

That's a bigger gap than the vendor swap. The IRB is reviewing a data-flow diagram that omits a live system which reads participant narratives and writes check-in responses. Those three documents need updating for both issues together.
