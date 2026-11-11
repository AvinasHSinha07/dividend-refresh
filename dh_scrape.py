"""
dh_scrape.py - HTML scraping module (Step 7)

Reads from https://dividendhistory.org/payout/<TICKER>/ :
  - Current Yield          (header block, "Dividend Metrics ... Yield 41.96%")
  - Dividend Amount        (newest CONFIRMED row of the dividend table)
Also returns last close and annual dividend as cross-checks.

Each field is returned as None if it can't be found, so the caller can
keep the old sheet value and flag a warning (never silently write junk).
"""
import re
import sys

import requests
from bs4 import BeautifulSoup

HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/157.0.0.0 Safari/537.36"),
    "Accept": "text/html,application/xhtml+xml,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}


def fetch_html(ticker):
    r = requests.get(f"https://dividendhistory.org/payout/{ticker}/",
                     headers=HEADERS, timeout=30)
    r.raise_for_status()
    return r.text


def _num(s):
    """'41.96' or '1,234.5' or '$0.4229' -> float, else None."""
    try:
        return float(re.sub(r"[^\d.\-]", "", s))
    except (ValueError, TypeError):
        return None


def parse_html(html):
    soup = BeautifulSoup(html, "lxml")
    text = re.sub(r"\s+", " ", soup.get_text(" ", strip=True))
    out = {"current_yield_pct": None, "dividend_amount": None,
           "dividend_ex_date": None, "last_close": None, "annual_dividend": None}

    # Header block, e.g. "... Dividend Metrics Yield 41.96% Yield on Cost ..."
    m = re.search(r"Dividend Metrics\s+Yield\s+(-?[\d,.]+)\s*%", text)
    if m:
        out["current_yield_pct"] = _num(m.group(1))

    m = re.search(r"Last Close\s+\$?\s*([\d,.]+)", text)
    if m:
        out["last_close"] = _num(m.group(1))

    m = re.search(r"Annual Dividend\s+\$?\s*([\d,.]+)", text)
    if m:
        out["annual_dividend"] = _num(m.group(1))

    # Dividend table: columns = Ex-Date | Payout Date | Cash Amount | Change/Status
    table = soup.find("table", id="dividend-table")
    if table:
        for tr in table.find_all("tr"):
            cells = [c.get_text(" ", strip=True) for c in tr.find_all("td")]
            if len(cells) < 4:
                continue
            status = cells[3].lower()
            if "unconfirmed" in status or "estimated" in status:
                continue                       # skip projected payouts
            amount = _num(cells[2])
            if amount is not None:
                out["dividend_amount"] = amount
                out["dividend_ex_date"] = cells[0]
                break                          # table is newest-first
    return out


if __name__ == "__main__":
    ticker = sys.argv[1] if len(sys.argv) > 1 else "CHPY"
    for k, v in parse_html(fetch_html(ticker)).items():
        print(f"{k:20} {v}")