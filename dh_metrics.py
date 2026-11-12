"""
dh_metrics.py - combines dh_calc + dh_scrape

fetch_ticker_metrics("CRCO") returns:
{"ticker": ..., "values": {price_change_pct, total_return_pct,
                           dividend_amount, current_yield_pct},
 "warnings": [...]}      # empty list = everything OK
  price_change_pct, total_return_pct, dividend_amount -> chart JSON, SAME window
  current_yield_pct                                   -> page HTML
A field that could not be read is None (NOT 0), so the sheet step leaves the
old cell value untouched.
"""
import sys

import dh_calc
import dh_scrape

# ---- SETTINGS (change here only) -------------------------------------------
WINDOW = "1y"            # "1m", "3m", "1y", "ytd" or "inception"
YIELD_RANGE = (0, 300)   # sanity limits (%)
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

    # ---- Page first: Current Yield + latest close/date ----------------------
    page = None
    try:
        page = dh_scrape.parse_html(dh_scrape.fetch_html(ticker))
        y = page["current_yield_pct"]
        if y is None:
            warnings.append("Current Yield not found on page (layout may have changed)")
        elif not (YIELD_RANGE[0] <= y <= YIELD_RANGE[1]):
            warnings.append(f"Current Yield {y}% outside sane range; ignored")
        else:
            values["current_yield_pct"] = y
    except Exception as e:
        warnings.append(f"Current Yield unavailable (page: {type(e).__name__}: {e})")

    # ---- Chart JSON: Price Change %, Total Return, Dividends ----------------
    try:
        data = dh_calc.fetch_chart(ticker)
        if page:   # JSON can lag the page by a day: add the page's latest close
            dh_calc.extend_with_last_close(data, page["updated_date"], page["last_close"])
        res = dh_calc.compute_window(data, dh_calc.window_start(data, WINDOW))
        values["price_change_pct"] = res["price_change_pct"]
        values["total_return_pct"] = res["total_return_pct"]
        values["dividend_amount"] = res["dividends_total"]
        if res["short_history"]:
            warnings.append(f"History shorter than '{WINDOW}' window; "
                            f"measured from {res['start_date']}")
    except Exception as e:
        warnings.append("Price Change % / Total Return / Dividend Amount unavailable "
                        f"(chart data: {type(e).__name__}: {e})")

    return {"ticker": ticker, "values": values, "warnings": warnings}


if __name__ == "__main__":
    # Usage: python dh_metrics.py CRCO APLY
    print(f"Window: {WINDOW}")
    for t in (sys.argv[1:] or ["CHPY"]):
        r = fetch_ticker_metrics(t)
        print(f"\n{r['ticker']}")
        for f in FIELDS:
            print(f"  {LABELS[f]:18} {r['values'][f]}")
        print("  warnings:", r["warnings"] or "none")