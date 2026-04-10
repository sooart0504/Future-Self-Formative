// ============================================================
// Future Self Formative Study — Check-In App Backend
// Google Apps Script — deploy as Web App
// Access: Anyone (no sign-in required)
// ============================================================

// ── CONFIGURATION ────────────────────────────────────────────
const SHEET_ID   = "1wxyeAYdKC7f5LcvOxuhtYHg8MQdF41zjOoYgMPhOr2k";
const TAB_CONTENT = "Chatbot1";   // Your Tab 1 name — change if different
const TAB_LOG     = "Check-ins";  // Your Tab 4 name — will be auto-created if missing

// ── COLUMNS APPS SCRIPT READS FROM TAB 1 ─────────────────────
// Tab 1 contains MORE columns than this — the chatbot writes:
//   timestamp_start, timestamp_end, persona_selected, values,
//   full_life, health_foundation, future_self_description,
//   timeline, revision_count, chat_log_t1, chat_log_t2
// Those are researcher reference data. Apps Script ignores them.
//
// The 8 image URL columns (image_ideal, image_weather, etc.) are
// NOT written by the chatbot. The PI adds them manually to Tab 1
// after generating images and uploading to Google Drive.
// Format: https://drive.google.com/uc?export=view&id=FILE_ID
const CONTENT_COLS = [
  "PID",
  // Narrative — written by chatbot
  "narrative_ideal",
  // Anchoring statements — written by chatbot
  "anchor_ideal", "anchor_weather", "anchor_busy", "anchor_travel",
  "anchor_physical", "anchor_access", "anchor_other", "anchor_rest",
  // Image URLs — entered manually by PI after Session 1 image generation
  "image_ideal", "image_weather", "image_busy", "image_travel",
  "image_physical", "image_access", "image_other", "image_rest"
];

// Column names for the check-in log tab (auto-created if missing)
const LOG_COLS = [
  "PID", "occasion", "timestamp_utc", "branch",
  "barrier", "diary_useful", "diary_burden", "open_text", "completed"
];

// ── MAIN ENTRY POINTS ─────────────────────────────────────────
function doGet(e) {
  try {
    const action = (e && e.parameter && e.parameter.action) ? e.parameter.action : "";
    const pid    = (e && e.parameter && e.parameter.PID)    ? e.parameter.PID    : "";

    if (action === "getContent") {
      return ContentService
        .createTextOutput(JSON.stringify(getContent(pid)))
        .setMimeType(ContentService.MimeType.JSON);
    }

    // Health check — open the URL with no parameters to confirm it's live
    return ContentService
      .createTextOutput(JSON.stringify({ status: "ok", message: "Future Self check-in API is running." }))
      .setMimeType(ContentService.MimeType.JSON);

  } catch (err) {
    return ContentService
      .createTextOutput(JSON.stringify({ error: err.message }))
      .setMimeType(ContentService.MimeType.JSON);
  }
}

function doPost(e) {
  try {
    const body   = JSON.parse(e.postData.contents);
    const action = body.action || "";

    if (action === "logResponse") {
      return ContentService
        .createTextOutput(JSON.stringify(logResponse(body)))
        .setMimeType(ContentService.MimeType.JSON);
    }

    return ContentService
      .createTextOutput(JSON.stringify({ error: "Unknown action: " + action }))
      .setMimeType(ContentService.MimeType.JSON);

  } catch (err) {
    return ContentService
      .createTextOutput(JSON.stringify({ error: err.message }))
      .setMimeType(ContentService.MimeType.JSON);
  }
}

// ── GET CONTENT ───────────────────────────────────────────────
// Reads a participant's row from Tab 1 and returns their personalized fields
function getContent(pid) {
  if (!pid) throw new Error("PID is required.");

  const ss    = SpreadsheetApp.openById(SHEET_ID);
  const sheet = ss.getSheetByName(TAB_CONTENT);
  if (!sheet) throw new Error("Sheet tab not found: " + TAB_CONTENT);

  const data    = sheet.getDataRange().getValues();
  const headers = data[0].map(function(h) { return h.toString().trim(); });

  // Find the PID column
  const pidCol = headers.indexOf("PID");
  if (pidCol === -1) throw new Error("PID column not found in tab: " + TAB_CONTENT);

  // Find the participant's row
  var row = null;
  for (var i = 1; i < data.length; i++) {
    if (data[i][pidCol].toString().trim() === pid.trim()) {
      row = data[i];
      break;
    }
  }
  if (!row) throw new Error("Participant not found: " + pid);

  // Build the response object using only the columns Apps Script needs
  var result = {};
  CONTENT_COLS.forEach(function(col) {
    var idx = headers.indexOf(col);
    result[col] = idx !== -1 ? row[idx].toString().trim() : "";
  });

  return { status: "ok", data: result };
}

// ── LOG RESPONSE ──────────────────────────────────────────────
// Appends one completed check-in row to the Check-ins tab
function logResponse(body) {
  const ss  = SpreadsheetApp.openById(SHEET_ID);
  var sheet = ss.getSheetByName(TAB_LOG);

  // Auto-create the Check-ins tab with headers if it doesn't exist yet
  if (!sheet) {
    sheet = ss.insertSheet(TAB_LOG);
    sheet.appendRow(LOG_COLS);
  }

  // Add headers if the sheet exists but is empty
  var firstCell = sheet.getRange(1, 1).getValue();
  if (!firstCell) {
    sheet.appendRow(LOG_COLS);
  }

  // Build the row and append it
  var timestamp = new Date().toISOString();
  var newRow = [
    body.PID          || "",
    body.occasion     || "",
    timestamp,
    body.branch       || "",
    body.barrier      || "",
    body.diary_useful !== undefined ? body.diary_useful : "",
    body.diary_burden !== undefined ? body.diary_burden : "",
    body.open_text    || "",
    "true"
  ];

  sheet.appendRow(newRow);

  return { status: "ok", message: "Response logged.", timestamp: timestamp };
}
