import streamlit as st
import yfinance as yf
import pandas as pd
import time
import requests
from datetime import datetime

st.set_page_config(page_title="BFX ICT Scanner", layout="wide")

# Brand styling: red & blue theme
st.markdown("""
<style>
    .stApp { background-color: #0E1117; color: #FAFAFA; }
    .sidebar .sidebar-content { background-color: #003087; }
    h1 { color: #E63946 !important; }
    .stDataFrame { background-color: #1E1E1E; }
</style>
""", unsafe_allow_html=True)

st.title("BFX ICT Scanner Dashboard 🚀")
st.markdown("**Premium Forex ICT Scanner** — Accurate BOS • Order Block POI • Filtered FVG • Liquidity Sweeps • Telegram Alerts")

# ====================== YOUR SETTINGS ======================
TELEGRAM_TOKEN = "8032718412:AAGFEeeDUFateTZrn7bYzGrACQ2qJWdIOaQ"   # ← your token
TELEGRAM_CHAT_ID = "6311692829"                         # ← replace with your real chat ID

# Forex pairs only (15 majors/minors + gold)
symbols = [
    "EURUSD=X", "GBPUSD=X", "USDJPY=X", "AUDUSD=X", "USDCAD=X",
    "NZDUSD=X", "USDCHF=X", "EURGBP=X", "EURJPY=X", "GBPJPY=X",
    "EURAUD=X", "GBPAUD=X", "EURCAD=X", "AUDJPY=X", "XAUUSD=X"
]

st.sidebar.header("⚙️ Settings")
refresh_rate = st.sidebar.slider("Refresh every (seconds)", 60, 600, 180)
poi_threshold_pct = st.sidebar.slider("POI reach threshold (%)", 0.05, 0.8, 0.25, 0.05)

def send_telegram(message):
    if "YOUR_CHAT_ID_HERE" in TELEGRAM_CHAT_ID:
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": message, "parse_mode": "HTML"}
    try:
        requests.post(url, json=payload, timeout=5)
    except:
        pass

# Data fetch functions
@st.cache_data(ttl=60)
def get_current_price(symbol):
    try:
        price = yf.Ticker(symbol).history(period="1d")['Close'].iloc[-1]
        if "USD" in symbol and "X" in symbol:
            return price, f"{price:.5f}"
        else:
            return price, f"{price:,.2f}"
    except:
        return None, "Error"

@st.cache_data(ttl=300)
def get_tf_data(symbol, interval, period):
    try:
        df = yf.download(symbol, interval=interval, period=period, progress=False)
        return df[['Open', 'High', 'Low', 'Close']] if not df.empty else None
    except:
        return None

# Main loop
status_data = []
for sym in symbols:
    current_price_num, price_str = get_current_price(sym)
    h4 = get_tf_data(sym, "4h", "60d")
    m15 = get_tf_data(sym, "15m", "7d")
    m1  = get_tf_data(sym, "1m", "1d")

    if h4 is None or len(h4) < 50 or m15 is None or len(m15) < 50:
        status_data.append({
            "Symbol": sym,
            "Current Price": price_str,
            "Bias": "N/A",
            "Phase": "N/A",
            "POI": "-",
            "Status": "Data error",
            "Last Update": datetime.now().strftime("%H:%M:%S")
        })
        continue

    # BOS & POI
    recent_high = h4['High'].rolling(20, center=True).max().shift(1).iloc[-1].item()
    recent_low  = h4['Low'].rolling(20, center=True).min().shift(1).iloc[-1].item()
    current_close = h4['Close'].iloc[-1].item()

    bias = "No Bias"
    phase = "Waiting"
    poi = None

    if current_close > recent_high:
        bias = "Bullish"
        phase = "Pullback"
        poi = h4['Open'].iloc[-2].item() if h4['Close'].iloc[-2] < h4['Open'].iloc[-2] else h4['Low'].iloc[-2].item()
    elif current_close < recent_low:
        bias = "Bearish"
        phase = "Pullback"
        poi = h4['Open'].iloc[-2].item() if h4['Close'].iloc[-2] > h4['Open'].iloc[-2] else h4['High'].iloc[-2].item()

    # POI distance & phase switch
    dist_str = "-"
    if poi is not None and current_price_num is not None:
        dist_pct = abs(current_price_num - poi) / current_price_num * 100
        dist_str = f"{dist_pct:.2f}%"
        if dist_pct <= poi_threshold_pct:
            phase = "Continuation"

    # FVG detection (fixed indentation + .item())
    fvg_signal = ""
    if m15 is not None and len(m15) >= 3:
        last_low   = m15['Low'].iloc[-1].item()
        prev_high  = m15['High'].iloc[-3].item()
        last_high  = m15['High'].iloc[-1].item()
        prev_low   = m15['Low'].iloc[-3].item()

        gap = abs(last_high - prev_low)

        if last_low > prev_high and gap > 0.0005:
            if bias in ["Bullish", "No Bias"] or phase == "Pullback":
                fvg_signal = "Bullish FVG"
        if last_high < prev_low and gap > 0.0005:
            if bias in ["Bearish", "No Bias"] or phase == "Pullback":
                fvg_signal = "Bearish FVG"

    # Sweep detection (example - add your own logic here if needed)
    sweep_signal = ""
    # ... your sweep code ...

    # Build status
    status_parts = []
    if bias != "No Bias":
        status_parts.append(f"{bias} BOS – {phase}")
        if poi is not None:
            status_parts.append(f"POI ~ {poi:.5f} ({dist_str})")
    if fvg_signal:
        status_parts.append(fvg_signal)
    if sweep_signal:
        status_parts.append(sweep_signal)

    raw_status = " | ".join(status_parts) if status_parts else "No recent BOS"
    status = raw_status  # you can add coloring later if wanted

    # Telegram alert
    if any(x in raw_status for x in ["BOS", "FVG", "Sweep", "Continuation"]):
        send_telegram(f"{sym} @ {price_str}\n{raw_status}")

    status_data.append({
        "Symbol": sym,
        "Current Price": price_str,
        "Bias": bias,
        "Phase": phase,
        "POI": f"{poi:.5f}" if poi is not None else "-",
        "Status": status,
        "Last Update": datetime.now().strftime("%H:%M:%S")
    })

df = pd.DataFrame(status_data)
st.dataframe(df, use_container_width=True, hide_index=True)

st.info(f"Scanning {len(symbols)} forex pairs | Refresh: {refresh_rate}s")
st.caption("Telegram alerts active | POI uses order block candle body")

time.sleep(refresh_rate)
st.rerun()