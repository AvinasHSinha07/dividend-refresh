"""
app.py - Streamlit page with a Refresh button for the dividend Google Sheet.

Hosted on Streamlit Community Cloud (secrets come from st.secrets) or run
locally with:  streamlit run app.py   (then refresh.py uses service_account.json)
"""
import os
import threading

import pandas as pd
import requests
import streamlit as st
import dh_scrape

# 1) Copy secrets into environment variables BEFORE importing refresh.py,
#    because refresh.py reads them when it is imported.
try:
    for key in ("GOOGLE_CREDS_JSON", "SPREADSHEET_ID", "SHEET_NAME"):
        if key in st.secrets:
            os.environ[key] = str(st.secrets[key])
except Exception:
    pass  # no secrets file locally: that's fine

import dh_calc
import dh_metrics
import refresh

st.set_page_config(page_title="Dividend Refresh", page_icon="💰")

# 2) Optional password (set APP_PASSWORD in secrets to turn it on)
try:
    APP_PASSWORD = st.secrets.get("APP_PASSWORD", "")
except Exception:
    APP_PASSWORD = ""

if APP_PASSWORD:
    if st.session_state.get("authed") is not True:
        pw = st.text_input("Password", type="password")
        if pw:
            if pw == APP_PASSWORD:
                st.session_state["authed"] = True
                st.rerun()
            else:
                st.error("Wrong password.")
        st.stop()

# 3) Page
st.title("💰 Dividend watch-list refresh")
st.caption(f"Price Change / Total Return / Dividends window: **{dh_metrics.WINDOW}**")

# One refresh at a time, even if several people click
_LOCK = st.cache_resource(lambda: threading.Lock())()


def load_sheet():
    ws = refresh.get_client().open_by_key(refresh.SPREADSHEET_ID).worksheet(refresh.SHEET_NAME)
    rows = ws.get_all_values()
    if len(rows) < 2:
        return pd.DataFrame()
    return pd.DataFrame(rows[1:], columns=rows[0])


col1, col2 = st.columns(2)

# ---- Refresh button ---------------------------------------------------------
with col1:
    if st.button("🔄 Refresh now", type="primary"):
        if not _LOCK.acquire(blocking=False):
            st.warning("A refresh is already running. Try again in a minute.")
        else:
            try:
                with st.spinner("Fetching data and updating the sheet..."):
                    s = refresh.refresh()
                if s["warnings"]:
                    st.warning(f"{s['tickers']} tickers | {s['ok']} OK | "
                               f"{s['warnings']} with warnings. See the Notes column below.")
                else:
                    st.success(f"{s['tickers']} tickers refreshed, no warnings.")
            except Exception as e:
                st.error(f"Refresh failed: {type(e).__name__}: {e}")
            finally:
                _LOCK.release()

# ---- Connection test --------------------------------------------------------
with col2:
    if st.button("🔌 Test connection"):
        try:
            r = requests.get("https://dividendhistory.org/chart/usa/CHPY.json",
                             headers=dh_calc.HEADERS, timeout=20)
            if r.status_code == 200:
                st.success("dividendhistory.org is reachable from this host (HTTP 200).")
            else:
                st.error(f"dividendhistory.org answered HTTP {r.status_code}. "
                         "If this is 403, the site blocks this host: run the app on your PC instead.")
        except Exception as e:
            st.error(f"Could not reach dividendhistory.org: {type(e).__name__}: {e}")

# ---- Current sheet contents -------------------------------------------------
st.subheader("Current sheet contents")
try:
    df = load_sheet()
    if df.empty:
        st.info("The sheet has no data rows yet.")
    else:
        st.dataframe(df)
except Exception as e:
    st.error(f"Could not read the sheet: {type(e).__name__}: {e}")


# ---- Debug: what HTML does THIS host receive? -------------------------------
with st.expander("Debug: inspect the page this host receives"):
    dbg_ticker = st.text_input("Ticker to inspect", "CHPY")
    if st.button("Run debug"):
        try:
            import re
            from bs4 import BeautifulSoup
            html = dh_scrape.fetch_html(dbg_ticker.strip().upper())
            soup = BeautifulSoup(html, "lxml")
            text = re.sub(r"\s+", " ", soup.get_text(" ", strip=True))
            st.write(f"HTML length: {len(html)} | title: "
                     f"{soup.title.get_text(strip=True) if soup.title else None}")
            st.write("'Stock Metrics' present:", "Stock Metrics" in text,
                     "| 'Dividend Metrics' present:", "Dividend Metrics" in text)
            st.code(text[600:2000])
            st.write("Parsed:", dh_scrape.parse_html(html))
        except Exception as e:
            st.error(f"{type(e).__name__}: {e}")