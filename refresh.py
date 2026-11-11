"""
refresh.py - STEP 10
Reads tickers from the sheet, fetches the four metrics for each, and writes
them back WITHOUT touching anything else.

Rules:
  * A field that could not be read is NOT written -> the old value stays.
  * Notes column gets a dated warning; it is cleared when a row is fully OK.
  * "Last Updated" changes only if at least one field was refreshed.
  * Column A (tickers) is never modified.
"""
import json
import os
import re
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

import gspread

from dh_metrics import fetch_ticker_metrics, FIELDS, LABELS

# ---- SETTINGS (change here only) -------------------------------------------
SPREADSHEET_ID = os.environ.get("SPREADSHEET_ID", "178wl9d8P3LaFSL6stuf9LRWRGSpVrvlgJ_JUt59ioxc")
SHEET_NAME = os.environ.get("SHEET_NAME", "Watchlist")
FIRST_DATA_ROW = 2                       # row 1 = headers
COLS = {                                 # which column holds what
    "ticker": "A",
    "price_change_pct": "B",
    "total_return_pct": "C",
    "dividend_amount": "D",
    "current_yield_pct": "E",
    "updated": "F",
    "notes": "G",
}
PERCENT_FIELDS = {"price_change_pct", "total_return_pct", "current_yield_pct"}
MAX_WORKERS = 5                          # tickers fetched in parallel
MAX_NOTE_LEN = 500
# -----------------------------------------------------------------------------


def get_client():
    """Cloud: credentials JSON in an env var. Local: service_account.json file."""
    creds = os.environ.get("GOOGLE_CREDS_JSON")
    if creds:
        return gspread.service_account_from_dict(json.loads(creds))
    return gspread.service_account(filename="service_account.json")


def clean_ticker(raw):
    """'chpy' -> 'CHPY'; also accepts a pasted dividendhistory.org link."""
    raw = raw.strip()
    if "/" in raw:
        m = re.search(r"/payout/([^/?#\s]+)", raw)
        raw = m.group(1) if m else raw.rstrip("/").split("/")[-1]
    return raw.upper()


def refresh():
    ws = get_client().open_by_key(SPREADSHEET_ID).worksheet(SHEET_NAME)
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M")   # UTC

    # 1) Read tickers (skip blank rows, remember each one's row number)
    raw = ws.col_values(1)
    rows = [(i + 1, clean_ticker(v)) for i, v in enumerate(raw)
            if i + 1 >= FIRST_DATA_ROW and v.strip()]

    # 2) Fetch all tickers in parallel
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
        results = list(pool.map(lambda rt: fetch_ticker_metrics(rt[1]), rows))

    # 3) Build cell updates: only fields we actually got
    updates, summary = [], {"ok": 0, "warnings": 0, "tickers": len(rows)}
    for (row, ticker), res in zip(rows, results):
        stale, refreshed = [], 0
        for f in FIELDS:
            v = res["values"][f]
            if v is None:
                stale.append(LABELS[f])          # leave old cell value alone
                continue
            if f in PERCENT_FIELDS:
                v = round(v / 100, 6)            # 41.96 -> 0.4196 (cell shows 41.96%)
            updates.append({"range": f"{COLS[f]}{row}", "values": [[v]]})
            refreshed += 1

        if refreshed:
            updates.append({"range": f"{COLS['updated']}{row}", "values": [[stamp]]})

        # Notes: warning text, or cleared when everything is fine
        if res["warnings"]:
            note = f"{stamp} UTC WARNING: " + "; ".join(res["warnings"])
            if stale:
                note += " | Old value kept for: " + ", ".join(stale)
            note = note[:MAX_NOTE_LEN]
            summary["warnings"] += 1
        else:
            note = ""
            summary["ok"] += 1
        updates.append({"range": f"{COLS['notes']}{row}", "values": [[note]]})

    # 4) One batched write (USER_ENTERED so numbers/dates are real values)
    if updates:
        ws.batch_update(updates, value_input_option="USER_ENTERED")
    return summary


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    s = refresh()
    print(f"Done. {s['tickers']} tickers | {s['ok']} OK | {s['warnings']} with warnings")