---
name: memory-hygiene
description: Rules for writing agent memory files (formats, what never to store) and the monthly maintenance that archives past months of logs and compacts MEMORY.md without losing data. Use whenever you write to MEMORY.md or memory/, and on every MEMORY_MAINTENANCE run.
---

# Memory hygiene

Memory is plain Markdown in your workspace: `MEMORY.md` (loaded into every
session, so keep it small) and `memory/*.md` (searched on demand). You can write
files but cannot delete them, so maintenance moves data by **copy → verify →
rewrite**, never by deleting first.

## Everyday writing rules
- Dates ISO (`2026-10-05`), times `HH:MM` in Europe/Warsaw. Notes in English.
- One fact per line or one row per event. Say where a fact came from when it
  matters: `(user)`, `(computed)`, `(SolaX)`.
- Never store: tokens, passwords, API keys, inverter serial numbers, phone numbers,
  raw tool JSON, other people's personal data.
- Logs are monthly files, not one file per day:
  | Agent | Current file | Archive file |
  | --- | --- | --- |
  | dispatcher | `memory/energy-log.md` | `memory/energy-log-YYYY-MM.md` |
  | weather-cast | `memory/alerts.md` | `memory/alerts-YYYY-MM.md` |
  | weather-cast | `memory/weather-events-YYYY-MM.md` (notable events) | — (already monthly) |
  | trader | `memory/prices-YYYY-MM.md` (one row per day: date, min, max, avg, negative hours) | — (already monthly) |
- Single-state files (`memory/tou-proposal.md`) are overwritten, never archived.

## Monthly maintenance (prompt contains `MEMORY_MAINTENANCE`)
Unattended, no delivery. Do only what applies to your own files.

### A. Rotate a log (energy-log.md, alerts.md)
1. Read the current file. Keep the header line(s) exactly.
2. Rows dated before the current month are **past rows**. Group them by month.
3. For `energy-log.md` only: the **last evening row of the previous month** is
   also kept in the current file (the boundary row history analysis needs). It is
   copied to the archive too, so it exists in both.
4. For each past month: if the archive file exists, append only rows not already
   in it; otherwise create it with the header and the rows.
5. **Verify**: re-read each archive file and confirm every past row is present.
6. Only if verification passed: rewrite the current file as header + (boundary row)
   + current-month rows. Re-read and confirm: rows kept = original rows − moved
   rows (+1 if a boundary row was kept).
7. Any mismatch or tool error: do **not** rewrite the current file; record
   `aborted` with the reason (step C) and stop. Archive rows written in step 4 are
   harmless duplicates and will be skipped next month.

### B. Compact MEMORY.md
- Target: under ~150 lines.
- Merge duplicates. When two lines contradict each other on the same topic, keep
  the newer one (by date) and drop the older; if undated, keep both and add
  `(check with user)`.
- Never drop a user preference, a «запам'ятай» item or an installation fact unless a
  newer line clearly replaces it.
- Decisions log entries older than 12 months: append them to
  `memory/decisions-archive.md`, verify, then remove them from `MEMORY.md`.
- Do not reword lines you keep; compaction is removal and merging, not editing style.

### C. Record and reply
Append one row to `memory/maintenance-log.md` (create with header if missing):
`| date | file | action | rows_moved | rows_kept | result |`
Final reply: one short English line, for example
`maintenance 2026-11-01: energy-log 61 moved / 3 kept ok; MEMORY.md 142->118 lines ok`.

## Checks before any rewrite
- Never rewrite a file you have not read in this run.
- Never rewrite `memory/tou-proposal.md` during maintenance.
- If a file is larger than you can read reliably in one go, skip it and record
  `skipped: too large` so the operator can rotate it by hand.
