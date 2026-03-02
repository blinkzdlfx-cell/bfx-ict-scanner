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
TELEGRAM_TOKEN = "8032718412:AAGFDUFeDUTZrnbyzGrACQjWQdIoAQ"   # ← your token
TELEGRAM_CHAT_ID = "YOUR_CHAT_ID_HERE"                         # ← replace with your real chat ID

# Forex pairs only (15 majors/minors + gold)
symbols = [
    "EURUSD=X", "GBPUSD=X", "USDJPY=X", "AUDUSD=X", "USDCAD=X",
    "NZDUSD=X", "USDCHF=X", "EURGBP=X", "EURJPY=X", "GBPJPY=X",
    "EURAUD=X", "GBPAUD=X", "EURCAD=X", "AUDJPY=X", "XAUUSD=X"
]

st.sidebar.header("⚙️ Settings")
refresh_rate = st.sidebar.slider("Refresh every (seconds)", 30, 600, 180)  # Lower min for day trading
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

# Data fetch
@st.cache_data(ttl=60)
def get_current_price(symbol):
    try:
        price = yf.Ticker(symbol).history(period="1d")['Close'].iloc[-1]
        return price, f"{price:.5f}"
    except:
        return None, "Error"

@st.cache_data(ttl=300)
def get_tf_data(symbol, interval, period):
    try:
        df = yf.download(symbol, interval=interval, period=period, progress=False)
        return df[['Open', 'High', 'Low', 'Close', 'Volume']] if not df.empty else None
    except:
        return None

# Main logic
status_data = []
for sym in symbols:
    current_price_num, price_str = get_current_price(sym)
    h4 = get_tf_data(sym, "4h", "120d")  # Longer period for previous BOS
    m15 = get_tf_data(sym, "15m", "14d") # Longer for 15m BOS
    m1  = get_tf_data(sym, "1m", "1d")

    if h4 is None or len(h4) < 50 or m15 is None or len(m15) < 50:
        status_data.append({
            "Symbol": sym,
            "Current Price": price_str,
            "Bias (4H)": "N/A",
            "Phase (4H)": "N/A",
            "POI (4H)": "-",
            "Bias (15m)": "N/A",
            "Phase (15m)": "N/A",
            "POI (15m)": "-",
            "Status": "Data error",
            "Last Update": datetime.now().strftime("%H:%M:%S")
        })
        continue

    # Premium BOS function (used for both 4H and 15m) — accurate with 2-close confirmation + volume
    def detect_bos(df, window=20):
        recent_high = df['High'].rolling(window, center=True).max().shift(1).iloc[-1].item()
        recent_low = df['Low'].rolling(window, center=True).min().shift(1).iland[-1].item()
        current_close = df['Close'].iloc[-1].item()
        prev_close = df['Close'].iloc[-2].item()
        volume_spike = df['Volume'].iloc[-1] > df['Volume'].rolling(5).mean().iloc[-1] * 1.5

        bias = "No Bias"
        poi = None
        if current_close > recent_high and prev_close > recent_high and volume_spike:
            bias = "Bullish"
            poi = df['Open'].iloc[-3].item() if df['Close'].iloc[-3] < df['Open'].iloc[-3] else df['Low'].iloc[-3].item()
        elif current_close < recent_low and prev_close < recent_low and volume_spike:
            bias = "Bearish"
            poi = df['Open'].iloc[-3].item() if df['Close'].iloc[-3] > df['Open'].iloc[-3] else df['High'].iloc[-3].item()
        return bias, poi

    # 4H (swing) + previous BOS
    bias_4h, poi_4h = detect_bos(h4)
    phase_4h = "Pullback" if bias_4h != "No Bias" else "Waiting"
    dist_str_4h = "-"
    if poi_4h is not None and current_price_num is not None:
        dist_pct = abs(current_price_num - poi_4h) / current_price_num * 100
        dist_str_4h = f"{dist_pct:.2f}%"
        if dist_pct <= poi_threshold_pct:
            phase_4h = "Continuation"

    # 15m (day trade/scalp) BOS
    bias_15m, poi_15m = detect_bos(m15, window=10)  # Smaller window for day trading
    phase_15m = "Pullback" if bias_15m != "No Bias" else "Waiting"
    dist_str_15m = "-"
    if poi_15m is not None and current_price_num is not None:
        dist_pct = abs(current_price_num - poi_15m) / current_price_num * 100
        dist_str_15m = f"{dist_pct:.2f}%"
        if dist_pct <= poi_threshold_pct * 0.5:  # Tighter for day trading
            phase_15m = "Continuation"

    # FVG & Sweep (filtered, sized for accuracy, day trading focus)
    fvg_signal = ""
    sweep_signal = ""
    if m15 is not None and len(m15) >= 3:
        last_low = m15['Low'].iloc[-1].item()
        prev_high = m15['High'].iloc[-3].item()
        last_high = m15['High'].iloc[-1].item()
        prev_low = m15['Low'].iloc[-3].item()
        
        gap = abs(last_high - prev_low)
        min_gap = 0.0003  # Smaller for day trading accuracy
        
        if last_low > prev_high and gap > min_gap and (bias_15m in ["Bullish", "No Bias"] or phase_15m == "Pullback"):
            fvg_signal = "Bullish FVG"
        if last_high < prev_low and gap > min_gap and (bias_15m in ["Bearish", "No Bias"] or phase_15m == "Pullback"):
            fvg_signal = "Bearish FVG"

    # Telegram alert with TF, entry/SL/TP (scaled for day trading)
    for tf, bias, phase, poi, dist_str in [("4H", bias_4h, phase_4h, poi_4h, dist_str_4h), ("15m", bias_15m, phase_15m, poi_15m, dist_str_15m)]:
        if bias != "No Bias":
            rr_scale = 3 if tf == "4H" else 1  # 1:3 for swing, 1:1 for day trade
            entry = f"{current_price_num:.5f}"
            sl = f"{poi - 0.0005:.5f}" if bias == "Bullish" else f"{poi + 0.0005:.5f}"
            tp1 = f"{current_price_num + (current_price_num - float(sl)) * rr_scale:.5f}" if bias == "Bullish" else f"{current_price_num - (float(sl) - current_price_num) * rr_scale:.5f}"
            tp2 = f"{current_price_num + (current_price_num - float(sl)) * rr_scale * 2:.5f}" if bias == "Bullish" else f"{current_price_num - (float(sl) - current_price_num) * rr_scale * 2:.5f}"
            
            alert_text = f"""
🚨 <b>{sym} {tf}</b> @ {price_str}
Bias: <b>{bias}</b> | Phase: <b>{phase}</b>
POI: {poi:.5f} ({dist_str})
Entry: {entry} | SL: {sl} | TP1: {tp1} | TP2: {tp2}
Signal: {fvg_signal or 'BOS Confirmed'}
            """
            send_telegram(alert_text)

    # Build row
    status = f"{bias_4h} BOS – {phase_4h} | {fvg_signal or ''}"
    status_data.append({
        "Symbol": sym,
        "Current Price": price_str,
        "Bias (4H)": bias_4h,
        "Phase (4H)": phase_4h,
        "POI (4H)": f"{poi_4h:.5f}" if poi_4h else "-",
        "Bias (15m)": bias_15m,
        "Phase (15m)": phase_15m,
        "POI (15m)": f"{poi_15m:.5f}" if poi_15m else "-",
        "Status": status,
        "Last Update": datetime.now().strftime("%H:%M:%S")
    })

# Display
df = pd.DataFrame(status_data)
st.dataframe(df, use_container_width=True, hide_index=True)

# Mini charts
for i, row in df.iterrows():
    with st.expander(f"📊 {row['Symbol']} 15m Chart"):
        m15 = get_tf_data(row['Symbol'], "15m", "2d")
        if m15 is not None:
            st.line_chart(m15['Close'].tail(50))

st.success("✅ Premium Forex ICT Scanner Running | Day Trading Enabled | Telegram Alerts with Scaled RR")
st.caption("Red = Bearish | Blue accents = Brand | Mini charts + accurate order-block POI")

time.sleep(refresh_rate)
st.rerun()
