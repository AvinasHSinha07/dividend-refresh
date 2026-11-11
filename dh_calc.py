"""
dh_calc.py - calculation module (Step 6)

Downloads the chart JSON for a ticker and computes:
  - Price Change %           over a chosen window
  - Total Return %           over the same window, dividends reinvested
  - Dividend Amount          most recent confirmed payout
Method for total return matches the site's own toggle:
  "Reinvest dividends at the ex-dividend date closing price".
"""
import sys
from bisect import bisect_right
from datetime import datetime, timezone, timedelta

import requests

HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/157.0.0.0 Safari/537.36"),
    "Accept": "application/json,*/*",
}


def fetch_chart(ticker):
    """Download {times, closes, dividends} for a US ticker."""
    url = f"https://dividendhistory.org/chart/usa/{ticker}.json"
    r = requests.get(url, headers={**HEADERS,
                     "Referer": f"https://dividendhistory.org/payout/{ticker}/"}, timeout=30)
    r.raise_for_status()
    return r.json()


def to_date(ts):
    return datetime.fromtimestamp(ts, tz=timezone.utc).date().isoformat()


def compute_window(data, start_ts):
    """
    Price change and total return from the last close on/before start_ts
    to the latest close. If history is shorter than the window, we start at
    the first available close and set short_history=True.
    """
    # Drop any rows with a missing close so the math never hits None
    pairs = [(t, c) for t, c in zip(data["times"], data["closes"]) if c]
    times = [t for t, _ in pairs]
    closes = [c for _, c in pairs]

    i0 = bisect_right(times, start_ts) - 1
    short_history = i0 < 0
    i0 = max(i0, 0)

    start_price, end_price = closes[i0], closes[-1]
    price_change = end_price / start_price - 1

    # Total return: each dividend buys more shares at that day's close
    shares = 1.0
    d = data["dividends"]
    for ex, amt in zip(d["exDates"], d["amounts"]):
        if times[i0] < ex <= times[-1]:
            j = bisect_right(times, ex) - 1       # close on (or just before) ex-date
            if j >= 0:
                shares *= 1 + amt / closes[j]
    total_return = shares * end_price / start_price - 1

    return {
        "start_date": to_date(times[i0]),
        "end_date": to_date(times[-1]),
        "start_price": start_price,
        "end_price": end_price,
        "price_change_pct": round(price_change * 100, 2),
        "total_return_pct": round(total_return * 100, 2),
        "short_history": short_history,
    }


def latest_dividend(data):
    """Most recent confirmed dividend (amount, ex-date)."""
    d = data["dividends"]
    return d["amounts"][-1], to_date(d["exDates"][-1])


def window_start(data, window):
    """Turn a window name into a starting timestamp."""
    times = [t for t, c in zip(data["times"], data["closes"]) if c]
    last = datetime.fromtimestamp(times[-1], tz=timezone.utc)
    if window == "1m":
        return int((last - timedelta(days=30)).timestamp())
    if window == "3m":
        return int((last - timedelta(days=91)).timestamp())
    if window == "1y":
        return int((last - timedelta(days=365)).timestamp())
    if window == "ytd":   # last close of the previous year
        return int(datetime(last.year, 1, 1, tzinfo=timezone.utc).timestamp())
    if window == "inception":
        return times[0]
    raise ValueError(f"Unknown window: {window}")


if __name__ == "__main__":
    ticker = sys.argv[1] if len(sys.argv) > 1 else "CHPY"
    data = fetch_chart(ticker)

    amt, ex = latest_dividend(data)
    print(f"{ticker}  latest confirmed dividend: ${amt}  (ex-date {ex})\n")

    for w in ("1y", "ytd", "inception"):
        r = compute_window(data, window_start(data, w))
        note = "  (history shorter than window)" if r["short_history"] else ""
        print(f"[{w:9}] {r['start_date']} -> {r['end_date']}  "
              f"${r['start_price']} -> ${r['end_price']}  "
              f"Price Change {r['price_change_pct']}%  "
              f"Total Return {r['total_return_pct']}%{note}")
