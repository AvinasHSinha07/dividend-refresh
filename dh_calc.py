"""
dh_calc.py - calculation module

Downloads the chart JSON for a ticker and computes, over ONE chosen window:
  - Price Change %      first close in window -> latest close
  - Total Return %      same window, dividends reinvested
  - Dividends $         total dividends paid per share inside the window
Total return uses the site's own method:
  "Reinvest dividends at the ex-dividend date closing price".
"""
import sys
from bisect import bisect_right
from datetime import datetime, timezone, timedelta
from decimal import Decimal, ROUND_HALF_UP

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


def round_half_up(x, places=2):
    """Round like the site does (12.395 -> 12.40). Python's round() gives 12.39."""
    q = Decimal(1).scaleb(-places)                     # 0.01 for places=2
    return float(Decimal(str(x)).quantize(q, rounding=ROUND_HALF_UP))


def extend_with_last_close(data, updated_date, last_close):
    """
    The chart JSON can lag the page by a day. If the page's 'Updated' date is
    newer than the JSON's last date, append the page's Last Close as one more
    price point, rounded half-up to 2 decimals like every price the site's
    chart uses. Returns True if a point was added.
    """
    if not updated_date or not last_close:
        return False
    y, m, d = (int(x) for x in updated_date.split("-"))
    # JSON timestamps sit at about 04:00 UTC on the trading date
    ts = int(datetime(y, m, d, 4, 0, tzinfo=timezone.utc).timestamp())
    valid = [t for t, c in zip(data["times"], data["closes"]) if c]
    if not valid:
        return False
    if to_date(ts) <= to_date(max(valid)):
        return False
    data["times"].append(ts)
    data["closes"].append(round_half_up(last_close, 2))
    return True


def compute_window(data, start_ts):
    """
    Price change, total return and dividends paid, measured from the last
    close on/before start_ts to the latest close. If the history is shorter
    than the window, we start at the first available close and set
    short_history=True.
    """
    # Drop rows with a missing close so the math never hits None
    pairs = [(t, c) for t, c in zip(data["times"], data["closes"]) if c]
    if not pairs:
        raise ValueError("no price data")
    times = [t for t, _ in pairs]
    closes = [c for _, c in pairs]

    i0 = bisect_right(times, start_ts) - 1
    short_history = i0 < 0
    i0 = max(i0, 0)

    start_price, end_price = closes[i0], closes[-1]
    price_change = end_price / start_price - 1

    # Each dividend inside the window: add to the running total AND buy more
    # shares at that day's close (for total return).
    shares = 1.0
    dividends_total = 0.0
    d = data.get("dividends") or {"exDates": [], "amounts": []}
    for ex, amt in zip(d["exDates"], d["amounts"]):
        if times[i0] < ex <= times[-1]:
            dividends_total += amt
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
        "dividends_total": round(dividends_total, 4),
        "short_history": short_history,
    }


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
    if window == "ytd":   # from Jan 1 of the current year
        return int(datetime(last.year, 1, 1, tzinfo=timezone.utc).timestamp())
    if window == "inception":
        return times[0]
    raise ValueError(f"Unknown window: {window}")


if __name__ == "__main__":
    # Usage: python dh_calc.py CRCO   (raw JSON only, no page-lag fix)
    ticker = sys.argv[1] if len(sys.argv) > 1 else "CHPY"
    data = fetch_chart(ticker)
    print(f"{ticker}\n")
    for w in ("1m", "3m", "1y", "ytd", "inception"):
        r = compute_window(data, window_start(data, w))
        note = "  (history shorter than window)" if r["short_history"] else ""
        print(f"[{w:9}] {r['start_date']} -> {r['end_date']}  "
              f"Price Change {r['price_change_pct']}%  "
              f"Total Return {r['total_return_pct']}%  "
              f"Dividends ${r['dividends_total']}{note}")