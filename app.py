import os
import time
import telebot
import requests
import threading
import streamlit as st

# 🔐 1. Environment Configurations
BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN") or "YOUR_TELEGRAM_BOT_TOKEN_HERE"
OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY") or "YOUR_OPENROUTER_API_KEY_HERE"

bot = telebot.TeleBot(BOT_TOKEN)
CHAT_IDS_FILE = "chat_ids.txt"

# Page Settings for Streamlit Dashboard
st.set_page_config(page_title="Sahajāta Confluence Matrix", page_icon="☸️", layout="wide")

# 🧮 2. Native Technical Indicators Calculation Engine
def calculate_rsi(prices, period=14):
    if len(prices) < period + 1: return None
    deltas = [prices[i] - prices[i-1] for i in range(1, len(prices))]
    gains = [d if d > 0 else 0 for d in deltas[-period:]]
    losses = [-d if d < 0 else 0 for d in deltas[-period:]]
    avg_gain = sum(gains) / period
    avg_loss = sum(losses) / period
    if avg_loss == 0: return 100.0 if avg_gain > 0 else 50.0
    return 100 - (100 / (1 + (avg_gain / avg_loss)))

def calculate_ema(prices, period):
    if len(prices) < period: return None
    k = 2 / (period + 1)
    ema = sum(prices[:period]) / period
    for price in prices[period:]:
        ema = (price * k) + (ema * (1 - k))
    return ema

def calculate_macd(prices):
    if len(prices) < 35: return None, None, None
    ema12_list, ema26_list = [], []
    k12, k26 = 2 / 13, 2 / 27
    current_ema12 = sum(prices[:12]) / 12
    current_ema26 = sum(prices[:26]) / 26
    ema12_list.append(current_ema12)
    ema26_list.append(current_ema26)
    
    for p in prices[12:]:
        current_ema12 = (p * k12) + (current_ema12 * (1 - k12))
        ema12_list.append(current_ema12)
    for p in prices[26:]:
        current_ema26 = (p * k26) + (current_ema26 * (1 - k26))
        ema26_list.append(current_ema26)
        
    min_len = len(ema26_list)
    macd_line = [ema12_list[-min_len + i] - ema26_list[i] for i in range(min_len)]
    
    if len(macd_line) < 9: return None, None, None
    k_sig = 2 / 10
    signal_line = sum(macd_line[:9]) / 9
    for m in macd_line[9:]:
        signal_line = (m * k_sig) + (signal_line * (1 - k_sig))
        
    return macd_line[-1], signal_line, (macd_line[-1] - signal_line)

# 🧠 3. သဟဇာတ (Sahajāta V2) Scoring Engine
def compute_sahajata_v2_score(price, high, low, rsi, ema20, ema50, macd_data):
    dimensions = []
    if rsi is not None:
        rsi_sub = 1.0 if rsi < 30 else 0.80 if rsi < 40 else 0.60 if rsi < 50 else 0.40 if rsi < 60 else 0.15
        dimensions.append({"weight": 25, "subScore": rsi_sub})
    if ema20 is not None and ema50 is not None:
        ema_sub = 1.0 if (price > ema20 and ema20 > ema50) else 0.20 if (price < ema20 and ema20 < ema50) else 0.60 if price > ema20 else 0.40
        dimensions.append({"weight": 25, "subScore": ema_sub})
    macd_line, signal, histogram = macd_data
    if histogram is not None:
        macd_sub = 1.0 if (histogram > 0 and macd_line > 0) else 0.70 if histogram > 0 else 0.20 if (histogram < 0 and macd_line < 0) else 0.40
        dimensions.append({"weight": 25, "subScore": macd_sub})
    if high > low:
        zone_pct = (price - low) / (high - low)
        dimensions.append({"weight": 25, "subScore": max(0.0, min(1.0, 1.0 - (zone_pct * 0.85)))})

    if not dimensions: return 50, "MODERATE CO-ARISING", 1.00
    total_w = sum(d["weight"] for d in dimensions)
    weighted_sum = sum(d["subScore"] * d["weight"] for d in dimensions)
    score = round((weighted_sum / total_w) * 100)
    
    if score >= 80: return score, "PERFECT CO-ARISING", 1.50, "#00cc66"
    elif score >= 65: return score, "STRONG CO-ARISING", 1.25, "#33cc33"
    elif score >= 50: return score, "MODERATE CO-ARISING", 1.00, "#ffaa00"
    elif score >= 35: return score, "WEAK CO-ARISING", 0.75, "#ff6600"
    else: return score, "NO CO-ARISING", 0.25, "#ff3333"

# 📊 4. Market Data Aggregator
def get_xrp_advanced_data():
    price, high, low, change, source = 0.0, 0.0, 0.0, 0.0, "Bybit"
    rsi_val, ema20, ema50, funding_rate = None, None, None, "N/A"
    macd_data = (None, None, None)
    try:
        url = "https://api.bybit.com/v5/market/tickers?category=spot&symbol=XRPUSDT"
        data = requests.get(url, timeout=5).json()
        if data.get("retCode") == 0 and data.get("result", {}).get("list"):
            ticker = data["result"]["list"][0]
            price, high, low = float(ticker["lastPrice"]), float(ticker["highPrice24h"]), float(ticker["lowPrice24h"])
            prev = float(ticker["prevPrice24h"])
            change = ((price - prev) / prev) * 100 if prev > 0 else 0.0
    except Exception:
        try:
            url = "https://api.mexc.com/api/v3/ticker/24hr?symbol=XRPUSDT"
            data = requests.get(url, timeout=5).json()
            if "lastPrice" in data:
                price, high, low, change, source = float(data["lastPrice"]), float(data["highPrice"]), float(data["lowPrice"]), float(data["priceChangePercent"]), "MEXC"
        except Exception: return None

    if price == 0.0: return None
    closes = []
    try:
        url = "https://api.bybit.com/v5/market/kline?category=spot&symbol=XRPUSDT&interval=15&limit=100"
        k_data = requests.get(url, timeout=5).json()
        if k_data.get("retCode") == 0 and k_data.get("result", {}).get("list"):
            closes = [float(k[4]) for k in k_data["result"]["list"]]
            closes.reverse()
    except Exception: pass

    if not closes:
        try:
            url = "https://api.mexc.com/api/v3/klines?symbol=XRPUSDT&interval=15m&limit=100"
            k_data = requests.get(url, timeout=5).json()
            if isinstance(k_data, list) and len(k_data) > 0: closes = [float(k[4]) for k in k_data]
        except Exception: pass

    if closes:
        rsi_val = calculate_rsi(closes)
        ema20 = calculate_ema(closes, 20)
        ema50 = calculate_ema(closes, 50)
        macd_data = calculate_macd(closes)

    try:
        url = "https://api.bybit.com/v5/market/tickers?category=linear&symbol=XRPUSDT"
        f_data = requests.get(url, timeout=5).json()
        if f_data.get("retCode") == 0 and f_data.get("result", {}).get("list"):
            f_rate = f_data["result"]["list"][0].get("fundingRate", "0")
            funding_rate = f"{float(f_rate) * 100:.4f}%" if f_rate != "0" else "N/A"
    except Exception: pass

    return price, high, low, change, source, rsi_val, ema20, ema50, macd_data, funding_rate

# 🧠 5. OpenRouter AI Core
def ask_ai_advanced_analysis(price, high, low, change, rsi, ema20, ema50, macd_data, funding, scs, label, mult):
    if OPENROUTER_API_KEY == "YOUR_OPENROUTER_API_KEY_HERE": return "❌ OpenRouter API Key is configuration missing."
    url = "https://openrouter.ai/api/v1/chat/completions"
    headers = {"Authorization": f"Bearer {OPENROUTER_API_KEY}", "Content-Type": "application/json"}
    macd_line, signal, hist = macd_data
    
    market_data_prompt = (
        f"Perform a professional quantitative analysis for XRP/USDT:\n"
        f"Price: ${price:.4f} | 24h Change: {change:+.2f}%\n"
        f"RSI: {rsi:.2f if rsi else 'N/A'} | EMA20: {ema20:.4f if ema20 else 'N/A'} | MACD Hist: {hist:.5f if hist else 'N/A'}\n"
        f"Funding: {funding} | Sahajata Confluence Score: {scs}/100 ({label}) | Multiplier: {mult}x\n\n"
        f"Provide short-term key zones and position modulation strategies in strict professional English using elegant markdown."
    )
    payload = {
        "model": "openai/gpt-4o-mini",
        "messages": [
            {"role": "system", "content": "You are an institutional crypto portfolio allocation strategist. You respond exclusively in markdown English."},
            {"role": "user", "content": market_data_prompt}
        ]
    }
    try:
        return requests.post(url, headers=headers, json=payload, timeout=25).json()["choices"][0]["message"]["content"]
    except Exception as e: return f"❌ AI Analysis Engine Error: {str(e)}"

# 📩 6. Telegram Persistent Storage & Alert Functions
def load_chat_ids():
    if os.path.exists(CHAT_IDS_FILE):
        with open(CHAT_IDS_FILE, "r") as f: return set(line.strip() for line in f if line.strip())
    return set()

def save_chat_id(chat_id):
    chat_ids = load_chat_ids()
    if str(chat_id) not in chat_ids:
        with open(CHAT_IDS_FILE, "a") as f: f.write(f"{chat_id}\n")

# 🚨 Price Momentum Alert (Every 5 minutes)
def price_alert_monitor():
    last_p = None
    while True:
        time.sleep(300)
        data = get_xrp_advanced_data()
        if data:
            curr_p = data[0]
            if last_p is not None:
                pct = ((curr_p - last_p) / last_p) * 100
                if abs(pct) >= 2.0:
                    emoji = "🚀 PUMP ALERT" if pct > 0 else "🩸 DUMP ALERT"
                    msg = f"⚠️ **XRP MOMENTUM ({emoji})**\n━━━━━━━━━━━━━━\nPrice shifted **{pct:+.2f}%**\n💵 Price: `${curr_p:.4f}`"
                    for cid in load_chat_ids():
                        try: bot.send_message(cid, msg, parse_mode="Markdown")
                        except Exception: pass
            last_p = curr_p

# 🤖 7. Telegram Bot Commands Handlers
@bot.message_handler(commands=['start'])
def send_welcome(message):
    save_chat_id(message.chat.id)
    bot.reply_to(message, "👋 **XRP Extended Sahajāta Bot Active!**\nUse `/indicators` or `/analyze`.", parse_mode="Markdown")

@bot.message_handler(commands=['indicators'])
def telegram_indicators(message):
    save_chat_id(message.chat.id)
    data = get_xrp_advanced_data()
    if data:
        price, high, low, change, source, rsi, ema20, ema50, macd_data, funding = data
        scs, label, mult, _ = compute_sahajata_v2_score(price, high, low, rsi, ema20, ema50, macd_data)
        macd_line, _, hist = macd_data
        msg = (
            f"📊 **XRP/USDT Matrix**\n━━━━━━━━━━━━━━\n"
            f"💵 Price: `${price:.4f}` ({change:+.2f}%)\n"
            f"📈 RSI: `{rsi:.2f if rsi else 'N/A'}`\n"
            f"📉 EMA: `{'🟢 Above' if (ema20 and price > ema20) else '🔴 Below'} EMA20`\n"
            f"📊 MACD Hist: `{(hist if hist else 0.0):.5f}`\n"
            f"⏳ Funding: `{funding}`\n━━━━━━━━━━━━━━\n"
            f"☸️ **Sahajāta Score:** `{scs}/100`\n🏷️ State: `[{label}]`\n⚙️ Multiplier: `{mult}x`"
        )
        bot.reply_to(message, msg, parse_mode="Markdown")

@bot.message_handler(commands=['analyze'])
def telegram_analyze(message):
    save_chat_id(message.chat.id)
    data = get_xrp_advanced_data()
    if not data: return
    price, high, low, change, source, rsi, ema20, ema50, macd_data, funding = data
    scs, label, mult, _ = compute_sahajata_v2_score(price, high, low, rsi, ema20, ema50, macd_data)
    load_msg = bot.reply_to(message, "🤖 _Compiling institutional analysis..._", parse_mode="Markdown")
    ai_report = ask_ai_advanced_analysis(price, high, low, change, rsi, ema20, ema50, macd_data, funding, scs, label, mult)
    try: bot.edit_message_text(ai_report, chat_id=message.chat.id, message_id=load_msg.message_id, parse_mode="Markdown")
    except Exception: bot.reply_to(message, ai_report)

# 🌐 8. BACKGROUND CO-RUNNER INITIALIZATION (The Secret Sauce)
@st.cache_resource
def start_global_services():
    # Telegram Multi-threads background loops
    threading.Thread(target=bot.infinity_polling, daemon=True).start()
    threading.Thread(target=price_alert_monitor, daemon=True).start()
    return True

start_global_services()

# 💻 9. STREAMLIT WEB DASHBOARD UI
st.title("☸️ Sahajāta Confluence Matrix Dashboard")
st.caption("Institutional Quantitative Engine for XRP Accumulation Setup")

# Refresh Button
if st.button("🔄 Refresh Live Market Data", type="primary"):
    st.rerun()

market_data = get_xrp_advanced_data()

if market_data:
    price, high, low, change, source, rsi, ema20, ema50, macd_data, funding = market_data
    scs, label, mult, color = compute_sahajata_v2_score(price, high, low, rsi, ema20, ema50, macd_data)
    macd_line, signal, hist = macd_data

    # Main Metrics Grid
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("💵 XRP Price", f"${price:.4f}", f"{change:+.2f}%")
    col2.metric("📈 15m RSI (14)", f"{rsi:.2f}" if rsi else "N/A")
    col3.metric("⏳ Funding Rate", funding)
    col4.metric("⚙️ Data Source", source)

    st.markdown("---")

    # Sahajata Core Matrix Panel
    st.subheader("☸️ Confluence Analysis & Dynamic Sizing")
    
    # Progress Bar representing Score
    st.markdown(f"**Sahajāta Confluence Score (SCS):** `{scs} / 100`")
    st.progress(scs / 100)
    
    # Status Banner styled dynamically with color
            # Status Banner styled dynamically with color
    st.markdown(
        f"<div style='background-color:{color}; padding:15px; border-radius:8px; text-align:center; color:white; font-weight:bold; font-size:20px;'>STATE: {label} ({mult}x Accumulation Factor)</div>", 
        unsafe_allow_html=True
    )

    st.markdown(" ")

    # Detailed Indicators Breakdown Block
    st.subheader("📊 Technical Dimensions Breakdown")
    b1, b2, b3 = st.columns(3)
    
    with b1:
        st.markdown("**📈 Overbought/Oversold Momentum**")
        if rsi:
            if rsi < 30: st.success(f"Oversold ({rsi:.2f}) - High Accumulation Edge")
            elif rsi < 50: st.info(f"Neutral Low ({rsi:.2f}) - Safe Accumulation")
            else: st.warning(f"Overbought Territory ({rsi:.2f}) - Reduce Risk")
            
    with b2:
        st.markdown("**📉 Trend Structural Alignment**")
        if ema20 and ema50:
            if price > ema20 and ema20 > ema50: st.success("Bullish Alignment (Price > EMA20 > EMA50)")
            elif price < ema20 and ema20 < ema50: st.error("Bearish Structure (Price < EMA20 < EMA50)")
            else: st.info("Consolidation / Trend Shift Phase")

    with b3:
        st.markdown("**📊 MACD Wave Acceleration**")
        if hist is not None:
            if hist > 0: st.success(f"🟢 Positive Histogram ({hist:.5f})")
            else: st.error(f"🔴 Negative Histogram ({hist:.5f})")

    st.markdown("---")

    # Executive AI Analysis Block on Website
    st.subheader("🧠 Executive Strategic AI Analysis")
    if st.button("🤖 Generate Real-Time Institutional Report"):
        with st.spinner("Analyzing market data synchronization via AI Engine..."):
            ai_report_web = ask_ai_advanced_analysis(price, high, low, change, rsi, ema20, ema50, macd_data, funding, scs, label, mult)
            st.markdown(ai_report_web)
else:
    st.error("Market Engine Connection Error. Please verify network or API status.")
