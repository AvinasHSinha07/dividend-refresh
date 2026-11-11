"""
dh_metrics.py - combines dh_calc + dh_scrape (Step 8)

fetch_ticker_metrics("CHPY") returns:
{
  "ticker": "CHPY",
  "values":   {price_change_pct, total_return_pct, dividend_amount, current_yield_pct},
  "warnings": ["...", ...]      # empty list = everything OK
}
A field that could not be read is None (NOT 0, NOT blank text), so the
sheet-writing step knows to leave the old cell value untouched.
"""
import sys

import dh_calc
import dh_scrape

# ---- SETTINGS (change here only) -------------------------------------------
WINDOW = "1m"            # "1y", "ytd" or "inception"
YIELD_RANGE = (0, 300)   # sanity limits (%): outside this = treated as a bad read
# -----------------------------------------------------------------------------

FIELDS = ["price_change_pct", "total_return_pct", "dividend_amount", "current_yield_pct"]
LABELS = {
    "price_change_pct": "Price Change %",
    "total_return_pct": "Total Return",
    "dividend_amount": "Dividend Amount",
    "current_yield_pct": "Current Yield",
}


def fetch_ticker_metrics(ticker):
    ticker = ticker.strip().upper()
    values = {f: None for f in FIELDS}
    warnings = []

    # ---- Source 1: chart JSON -> Price Change % and Total Return ------------
    try:
        data = dh_calc.fetch_chart(ticker)
        res = dh_calc.compute_window(data, dh_calc.window_start(data, WINDOW))
        values["price_change_pct"] = res["price_change_pct"]
        values["total_return_pct"] = res["total_return_pct"]
        if res["short_history"]:
            warnings.append(f"History shorter than '{WINDOW}' window; "
                            f"measured from {res['start_date']}")
    except Exception as e:
        warnings.append(f"Price Change % / Total Return unavailable "
                        f"(chart data: {type(e).__name__}: {e})")

    # ---- Source 2: page HTML -> Current Yield and Dividend Amount -----------
    try:
        page = dh_scrape.parse_html(dh_scrape.fetch_html(ticker))

        y = page["current_yield_pct"]
        if y is None:
            warnings.append("Current Yield not found on page (layout may have changed)")
        elif not (YIELD_RANGE[0] <= y <= YIELD_RANGE[1]):
            warnings.append(f"Current Yield {y}% outside sane range; ignored")
        else:
            values["current_yield_pct"] = y

        a = page["dividend_amount"]
        if a is None:
            warnings.append("Dividend Amount not found in dividend table "
                            "(layout may have changed)")
        else:
            values["dividend_amount"] = a
    except Exception as e:
        warnings.append(f"Current Yield / Dividend Amount unavailable "
                        f"(page: {type(e).__name__}: {e})")

    return {"ticker": ticker, "values": values, "warnings": warnings}


if __name__ == "__main__":
    # Usage: python dh_metrics.py CHPY SCHD NVDY
    for t in (sys.argv[1:] or ["CHPY"]):
        r = fetch_ticker_metrics(t)
        print(f"\n{r['ticker']}")
        for f in FIELDS:
            print(f"  {LABELS[f]:18} {r['values'][f]}")
        print("  warnings:", r["warnings"] or "none")
