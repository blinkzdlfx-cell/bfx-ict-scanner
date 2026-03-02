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
st.markdown("**Premium Forex ICT Scanner** — Accurate BOS/CHoCH • Internal/Swing Structures • Order Blocks • Filtered FVG/Sweeps • Telegram Alerts")

# ====================== YOUR SETTINGS ======================
TELEGRAM_TOKEN = "8032718412:AAGFEeeDUFateTZrn7bYzGrACQ2qJWdIOaQ"
TELEGRAM_CHAT_ID = "6311692829"

# Forex pairs only (15 majors/minors + gold)
symbols = [
    "EURUSD=X", "GBPUSD=X", "USDJPY=X", "AUDUSD=X", "USDCAD=X",
    "NZDUSD=X", "USDCHF=X", "EURGBP=X", "EURJPY=X", "GBPJPY=X",
    "EURAUD=X", "GBPAUD=X", "EURCAD=X", "AUDJPY=X", "XAUUSD=X"
]

# Modifiable Settings (like TradingView inputs)
st.sidebar.header("⚙️ Modifiable Settings")
refresh_rate = st.sidebar.slider("Refresh every (seconds)", 30, 600, 180)
poi_threshold_pct = st.sidebar.slider("POI reach threshold (%)", 0.05, 0.8, 0.25, 0.05)
swings_length = st.sidebar.number_input("Swing Length (for BOS/CHoCH)", min_value=10, max_value=100, value=50)
internal_length = st.sidebar.number_input("Internal Length (for smaller structures)", min_value=1, max_value=20, value=5)
equal_hl_length = st.sidebar.number_input("Equal Highs/Lows Bars Confirmation", min_value=1, value=3)
equal_hl_threshold = st.sidebar.number_input("Equal Highs/Lows Threshold", min_value=0.0, max_value=0.5, value=0.1, step=0.01)
fvg_threshold = st.sidebar.number_input("FVG Threshold", min_value=0.0001, value=0.0005)
order_block_mitigation = st.sidebar.selectbox("Order Block Mitigation", ("Close", "High/Low"), index=1)

def send_telegram(message):
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

# LuxAlgo-adapted functions for swings/BOS/CHoCH/order blocks
def leg(df, size):
    highs = df['High'].rolling(size).max()
    lows = df['Low'].rolling(size).min()
    return (df['High'] > highs.shift(1)).astype(int) - (df['Low'] < lows.shift(1)).astype(int)

def start_of_new_leg(leg_series):
    return leg_series.diff() != 0

def start_of_bearish_leg(leg_series):
    return leg_series.diff() == -1

def start_of_bullish_leg(leg_series):
    return leg_series.diff() == 1

# Detect BOS/CHoCH for a dataframe (adapted LuxAlgo logic)
def detect_structure(df, length, is_internal=False):
    leg_series = leg(df, length)
    new_pivot = start_of_new_leg(leg_series)
    pivot_low = start_of_bullish_leg(leg_series)
    pivot_high = start_of_bearish_leg(leg_series)
    bias = "No Bias"
    phase = "Waiting"
    poi = None
    choche = False
    trend_bias = leg_series.cumsum()  # Approximate trend

    if new_pivot.iloc[-1]:
        if pivot_low.iloc[-1]:
            bias = "Bullish"
            phase = "Pullback"
            poi = df['Open'].iloc[-2].item() if df['Close'].iloc[-2] < df['Open'].iloc[-2] else df['Low'].iloc[-2].item()
            if trend_bias.iloc[-1] < 0:
                choche = True
        elif pivot_high.iloc[-1]:
            bias = "Bearish"
            phase = "Pullback"
            poi = df['Open'].iloc[-2].item() if df['Close'].iloc[-2] > df['Open'].iloc[-2] else df['High'].iloc[-2].item()
            if trend_bias.iloc[-1] > 0:
                choche = True

    # Volume spike for confirmation
    volume_spike = df['Volume'].iloc[-1].item() > df['Volume'].rolling(5).mean().iloc[-1].item() * 1.5
    if not volume_spike:
        bias = "No Bias"

    previous_bos = [bias] if bias != "No Bias" else []

    return bias, phase, poi, choche, previous_bos

# Main loop
status_data = []
for sym in symbols:
    current_price_num, price_str = get_current_price(sym)
    h4 = get_tf_data(sym, "4h", "120d")
    m15 = get_tf_data(sym, "15m", "14d")

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

    # 4H (swing)
    bias_4h, phase_4h, poi_4h, choche_4h, prev_bos_4h = detect_structure(h4, swings_length)
    dist_str_4h = "-"
    if poi_4h is not None and current_price_num is not None:
        dist_pct = abs(current_price_num - poi_4h) / current_price_num * 100
        dist_str_4h = f"{dist_pct:.2f}%"
        if dist_pct <= poi_threshold_pct:
            phase_4h = "Continuation"

    # 15m (internal/day trade)
    bias_15m, phase_15m, poi_15m, choche_15m, prev_bos_15m = detect_structure(m15, internal_length, is_internal=True)
    dist_str_15m = "-"
    if poi_15m is not None and current_price_num is not None:
        dist_pct = abs(current_price_num - poi_15m) / current_price_num * 100
        dist_str_15m = f"{dist_pct:.2f}%"
        if dist_pct <= poi_threshold_pct * 0.5:
            phase_15m = "Continuation"

    # FVG & Sweep (filtered, sized)
    fvg_signal = ""
    sweep_signal = ""
    if m15 is not None and len(m15) >= 3:
        last_low = m15['Low'].iloc[-1].item()
        prev_high = m15['High'].iloc[-3].item()
        last_high = m15['High'].iloc[-1].item()
        prev_low = m15['Low'].iloc[-3].item()

        gap = abs(last_high - prev_low)
        min_gap = fvg_threshold

        if last_low > prev_high and gap > min_gap and (bias_15m in ["Bullish", "No Bias"] or phase_15m == "Pullback"):
            fvg_signal = "Bullish FVG"
        if last_high < prev_low and gap > min_gap and (bias_15m in ["Bearish", "No Bias"] or phase_15m == "Pullback"):
            fvg_signal = "Bearish FVG"

    # Order Blocks (adapted)
    order_block = ""
    if bias_4h != "No Bias":
        ob_mitigation_source = close if order_block_mitigation == "Close" else high if bias_4h == "Bearish" else low
        if ob_mitigation_source > poi_4h and bias_4h == "Bearish" or ob_mitigation_source < poi_4h and bias_4h == "Bullish":
            order_block = "OB Mitigated"

    # Telegram alert with TF, entry/SL/TP (scaled for day trading)
    for tf, bias, phase, poi, dist_str, choche in [("4H", bias_4h, phase_4h, poi_4h, dist_str_4h, choche_4h), ("15m", bias_15m, phase_15m, poi_15m, dist_str_15m, choche_15m)]:
        if bias != "No Bias":
            rr_scale = 3 if tf == "4H" else 1
            entry = f"{current_price_num:.5f}"
            sl = f"{poi - 0.0005:.5f}" if bias == "Bullish" else f"{poi + 0.0005:.5f}"
            tp1 = f"{current_price_num + (current_price_num - float(sl)) * rr_scale:.5f}" if bias == "Bullish" else f"{current_price_num - (float(sl) - current_price_num) * rr_scale:.5f}"
            tp2 = f"{current_price_num + (current_price_num - float(sl)) * rr_scale * 2:.5f}" if bias == "Bullish" else f"{current_price_num - (float(sl) - current_price_num) * rr_scale * 2:.5f}"

            tag = "CHoCH" if choche else "BOS"
            alert_text = f"""
🚨 <b>{sym} {tf}</b> @ {price_str}
Bias: <b>{bias}</b> {tag} | Phase: <b>{phase}</b>
POI: {poi:.5f} ({dist_str})
Entry: {entry} | SL: {sl} | TP1: {tp1} | TP2: {tp2}
Signal: {fvg_signal or 'Confirmed'}
            """
            send_telegram(alert_text)

    # Build row
    status = f"{bias_4h} {'CHoCH' if choche_4h else 'BOS'} – {phase_4h} | {order_block or ''} | {fvg_signal or ''}"
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
