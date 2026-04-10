// ============================================================
// Future Self Formative Study — Check-In Non-Response Monitor
// Google Apps Script — runs daily via time-based trigger
//
// Add this code to the SAME Apps Script project as Code.gs.
// Then set up a daily time trigger (instructions below).
// ============================================================

// ── CONFIGURATION ─────────────────────────────────────────────
// These should already be defined in Code.gs — if you're adding
// this to a separate file, uncomment and fill them in:
//
// const SHEET_ID = "your-sheet-id-here";

const TAB_SCHEDULE  = "Tab3_Schedule";   // Your Tab 3 name — adjust if different
const TAB_CHECKINS  = "Check-ins";       // Your Tab 4 name — adjust if different
const TAB_MONITOR   = "Monitoring";      // Tab 5 — will be auto-created if missing

const CONSECUTIVE_MISS_THRESHOLD = 4;   // Occasions in a row → NEEDS_REENGAGEMENT
const TOTAL_MISS_THRESHOLD       = 6;   // Total misses → WITHDRAW

// Tab 5 column headers
var MONITOR_COLS = [
  "PID",
  "last_checked",
  "consecutive_misses",
  "total_misses",
  "last_completed_occasion",
  "last_sent_occasion",
  "status"
];

// ── MAIN FUNCTION — run this on a daily trigger ───────────────
function checkNonResponse() {
  var ss = SpreadsheetApp.openById(SHEET_ID);

  // Get or create Tab 5
  var monitorSheet = ss.getSheetByName(TAB_MONITOR);
  if (!monitorSheet) {
    monitorSheet = ss.insertSheet(TAB_MONITOR);
    monitorSheet.appendRow(MONITOR_COLS);
    // Style the header row
    monitorSheet.getRange(1, 1, 1, MONITOR_COLS.length)
      .setBackground("#2E4057")
      .setFontColor("#FFFFFF")
      .setFontWeight("bold");
  }

  // Read Tab 3 (schedule) — get all active participants and how many occasions sent
  var scheduleSheet = ss.getSheetByName(TAB_SCHEDULE);
  if (!scheduleSheet) {
    Logger.log("ERROR: Tab 3 not found: " + TAB_SCHEDULE);
    return;
  }
  var scheduleData    = scheduleSheet.getDataRange().getValues();
  var scheduleHeaders = scheduleData[0].map(function(h) { return h.toString().trim(); });

  var pidCol       = scheduleHeaders.indexOf("PID");
  var activeCol    = scheduleHeaders.indexOf("active");
  var occasionCol  = scheduleHeaders.indexOf("current_occasion");

  if (pidCol === -1 || activeCol === -1 || occasionCol === -1) {
    Logger.log("ERROR: Required columns missing in Tab 3. Need: PID, active, current_occasion");
    return;
  }

  // Build a map of PID → occasions sent so far
  var participantMap = {};
  for (var i = 1; i < scheduleData.length; i++) {
    var row    = scheduleData[i];
    var pid    = row[pidCol].toString().trim();
    var active = row[activeCol].toString().trim().toUpperCase();
    var sent   = parseInt(row[occasionCol]) || 0;

    if (!pid) continue;
    // Include active participants AND recently deactivated ones (to track through end)
    participantMap[pid] = { sent: sent, active: active };
  }

  // Read Tab 4 (check-ins) — get all completed occasions per participant
  var checkinSheet = ss.getSheetByName(TAB_CHECKINS);
  var completedMap = {};  // PID → Set of completed occasion numbers

  if (checkinSheet) {
    var checkinData    = checkinSheet.getDataRange().getValues();
    var checkinHeaders = checkinData[0].map(function(h) { return h.toString().trim(); });
    var cPidCol        = checkinHeaders.indexOf("PID");
    var cOccasionCol   = checkinHeaders.indexOf("occasion");
    var cCompletedCol  = checkinHeaders.indexOf("completed");

    if (cPidCol !== -1 && cOccasionCol !== -1) {
      for (var j = 1; j < checkinData.length; j++) {
        var cRow       = checkinData[j];
        var cPid       = cRow[cPidCol].toString().trim();
        var cOccasion  = parseInt(cRow[cOccasionCol]) || 0;
        var cCompleted = cCompletedCol !== -1 ? cRow[cCompletedCol].toString().trim() : "true";

        if (!cPid || cOccasion === 0) continue;
        if (cCompleted.toLowerCase() !== "true") continue;

        if (!completedMap[cPid]) completedMap[cPid] = [];
        if (completedMap[cPid].indexOf(cOccasion) === -1) {
          completedMap[cPid].push(cOccasion);
        }
      }
    }
  }

  // Read existing Tab 5 data to update in place rather than always appending
  var monitorData    = monitorSheet.getDataRange().getValues();
  var monitorHeaders = monitorData[0].map(function(h) { return h.toString().trim(); });
  var mPidCol        = monitorHeaders.indexOf("PID");

  // Build map of PID → row number in Tab 5 (1-based, accounting for header)
  var existingRows = {};
  for (var k = 1; k < monitorData.length; k++) {
    var mPid = monitorData[k][mPidCol] ? monitorData[k][mPidCol].toString().trim() : "";
    if (mPid) existingRows[mPid] = k + 1; // +1 because sheet rows are 1-based
  }

  // Calculate and write stats for each participant
  var timestamp = new Date().toISOString();

  Object.keys(participantMap).forEach(function(pid) {
    var info       = participantMap[pid];
    var sent       = info.sent;        // total occasions sent so far
    var completed  = completedMap[pid] || [];

    if (sent === 0) return; // No SMS sent yet — skip

    // Which occasions were sent? (1 through sent)
    var sentOccasions = [];
    for (var n = 1; n <= sent; n++) sentOccasions.push(n);

    // Which were missed?
    var missedOccasions = sentOccasions.filter(function(occ) {
      return completed.indexOf(occ) === -1;
    });

    var totalMisses = missedOccasions.length;

    // Find the last completed occasion number
    var lastCompleted = completed.length > 0 ? Math.max.apply(null, completed) : 0;

    // Calculate consecutive misses counting BACKWARDS from the most recent sent occasion
    var consecutiveMisses = 0;
    for (var m = sent; m >= 1; m--) {
      if (completed.indexOf(m) === -1) {
        consecutiveMisses++;
      } else {
        break; // Stop as soon as we hit a completed occasion
      }
    }

    // Determine status
    var status;
    if (totalMisses >= TOTAL_MISS_THRESHOLD) {
      status = "WITHDRAW";
    } else if (consecutiveMisses >= CONSECUTIVE_MISS_THRESHOLD) {
      status = "NEEDS_REENGAGEMENT";
    } else {
      status = "OK";
    }

    // Build the row data in column order
    var newRow = [
      pid,
      timestamp,
      consecutiveMisses,
      totalMisses,
      lastCompleted,
      sent,
      status
    ];

    // Update existing row or append new one
    if (existingRows[pid]) {
      // Overwrite the existing row
      monitorSheet.getRange(existingRows[pid], 1, 1, newRow.length).setValues([newRow]);
    } else {
      // New participant — append a row
      monitorSheet.appendRow(newRow);
    }

    // Color-code the status cell for easy visual scanning
    // Find which column "status" is in
    var statusColIdx = MONITOR_COLS.indexOf("status") + 1; // 1-based
    var rowNum = existingRows[pid] || monitorSheet.getLastRow();
    var statusCell = monitorSheet.getRange(rowNum, statusColIdx);

    if (status === "WITHDRAW") {
      statusCell.setBackground("#F4CCCC").setFontColor("#990000").setFontWeight("bold");
    } else if (status === "NEEDS_REENGAGEMENT") {
      statusCell.setBackground("#FCE5CD").setFontColor("#7F4B00").setFontWeight("bold");
    } else {
      statusCell.setBackground("#D9EAD3").setFontColor("#274E13").setFontWeight("normal");
    }

    Logger.log("PID=" + pid + " | sent=" + sent + " | completed=" + completed.length +
               " | consecutive=" + consecutiveMisses + " | total=" + totalMisses +
               " | status=" + status);
  });

  Logger.log("Non-response check complete. " + Object.keys(participantMap).length + " participant(s) evaluated.");
}
