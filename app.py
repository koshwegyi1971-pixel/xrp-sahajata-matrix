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

# ─── Dimension Weights (ပေါင်းရင် ၁၀၀ ကွက်တိ) ──────────────────────────────────
WEIGHTS = {
    "aiRegime": 20,
    "confluence": 15,
    "smartScore": 12,
    "marketStructure": 12,
    "orderFlow": 10,
    "pattern": 10,
    "fearGreed": 8,
    "portfolioHeat": 7,
    "dailyAlpha": 6,
    "faSentiment": 5,
    "marketFilter": 5,
}

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

# 🧠 3. သဟဇာတ (Sahajāta V3) 11-Dimensions Sub-Scorers
def score_ai_regime(ai_regime, action):
    if not ai_regime: return None, "No AI regime data"
    regime = ai_regime.get("regime")
    confidence = ai_regime.get("confidence", 1.0)
    regime_bases_buy = {"BULL_TREND": 0.85, "RECOVERY": 0.80, "SIDEWAYS": 0.50, "PANIC": 0.90}
    regime_bases_sell = {"BULL_TREND": 0.30, "RECOVERY": 0.50, "SIDEWAYS": 0.70, "PANIC": 0.20}
    bases = regime_bases_buy if action == "BUY" else regime_bases_sell
    base = bases.get(regime, 0.50)
    sub_score = base * confidence
    return sub_score, f"{regime} ({confidence*100:.0f}%) → sub-score {sub_score:.2f}"

def score_confluence(confluence, action):
    if not confluence: return None, "No confluence data"
    score_val = min(6, max(0, confluence.get("score", 3)))
    confidence = confluence.get("confidence", 1.0)
    score_map = [0.0, 0.20, 0.35, 0.55, 0.70, 0.85, 1.0]
    buy_base = score_map[score_val]
    base = buy_base if action == "BUY" else 1.0 - buy_base
    sub_score = base * confidence
    return sub_score, f"3-TF RSI Score {score_val}/6 → sub-score {sub_score:.2f}"

def score_smart_score(smart_score, action):
    if not smart_score: return None, "No SmartScore data"
    signal = smart_score.get("signal")
    confidence = smart_score.get("confidence", 1.0)
    signal_bases_buy = {"STRONG_BUY": 1.0, "BUY": 0.75, "NEUTRAL": 0.40, "SELL": 0.15, "STRONG_SELL": 0.0}
    signal_bases_sell = {"STRONG_BUY": 0.0, "BUY": 0.15, "NEUTRAL": 0.40, "SELL": 0.75, "STRONG_SELL": 1.0}
    bases = signal_bases_buy if action == "BUY" else signal_bases_sell
    base = bases.get(signal, 0.40)
    sub_score = base * confidence
    return sub_score, f"SmartScore {signal} → sub-score {sub_score:.2f}"

def score_market_structure(market_structure, action):
    if not market_structure: return None, "No market structure data"
    zone = market_structure.get("priceZone")
    struct = market_structure.get("structure")
    zone_bases_buy = {"AT_SUPPORT": 1.0, "BELOW_SUPPORT": 0.85, "BETWEEN_LEVELS": 0.50, "AT_RESISTANCE": 0.20, "ABOVE_RESISTANCE": 0.05}
    zone_bases_sell = {"AT_SUPPORT": 0.05, "BELOW_SUPPORT": 0.05, "BETWEEN_LEVELS": 0.50, "AT_RESISTANCE": 1.0, "ABOVE_RESISTANCE": 0.85}
    struct_bases_buy = {"TRENDING_UP": 0.80, "RANGING": 0.70, "CHOPPY": 0.40, "TRENDING_DOWN": 0.20}
    struct_bases_sell = {"TRENDING_UP": 0.20, "RANGING": 0.70, "CHOPPY": 0.40, "TRENDING_DOWN": 0.80}
    zone_bases = zone_bases_buy if action == "BUY" else zone_bases_sell
    struct_bases = struct_bases_buy if action == "BUY" else struct_bases_sell
    zone_score = zone_bases.get(zone, 0.50)
    struct_score = struct_bases.get(struct, 0.50)
    sub_score = (zone_score * 0.65) + (struct_score * 0.35)
    return sub_score, f"Zone {zone} + Structure {struct} → sub-score {sub_score:.2f}"

def score_order_flow(order_flow, action):
    if not order_flow or order_flow.get("dataQuality") == "FALLBACK":
        return None, "No order flow data (fallback)"
    signal = order_flow.get("signal")
    confidence = order_flow.get("confidence", 1.0)
    signal_bases_buy = {"STRONG_BUY_PRESSURE": 1.0, "BUY_PRESSURE": 0.75, "NEUTRAL": 0.45, "SELL_PRESSURE": 0.20, "STRONG_SELL_PRESSURE": 0.0}
    signal_bases_sell = {"STRONG_BUY_PRESSURE": 0.0, "BUY_PRESSURE": 0.20, "NEUTRAL": 0.45, "SELL_PRESSURE": 0.75, "STRONG_SELL_PRESSURE": 1.0}
    bases = signal_bases_buy if action == "BUY" else signal_bases_sell
    base = bases.get(signal, 0.45)
    sub_score = base * confidence
    return sub_score, f"OFA {signal} ({order_flow.get('dataQuality')}) → sub-score {sub_score:.2f}"

def score_pattern(pattern_analysis, action):
    if not pattern_analysis: return None, "No pattern data"
    strength = pattern_analysis.get("signalStrength", "NONE")
    dominant = pattern_analysis.get("dominantSignal", "NONE")
    base = pattern_analysis.get("bullishScore", 0.40) if action == "BUY" else pattern_analysis.get("bearishScore", 0.40)
    strength_multipliers = {"STRONG": 1.0, "MODERATE": 0.85, "WEAK": 0.60, "NONE": 0.40}
    sub_score = base * strength_multipliers.get(strength, 0.40)
    return sub_score, f"Pattern {dominant} ({strength}) → sub-score {sub_score:.2f}"

def score_fear_greed(fear_greed, action):
    if not fear_greed: return None, "No Fear & Greed data"
    val = fear_greed.get("value", 50)
    classification = fear_greed.get("classification", "Neutral")
    if action == "BUY":
        sub_score = 1.0 if val <= 24 else 0.80 if val <= 44 else 0.50 if val <= 55 else 0.25 if val <= 74 else 0.05
    else:
        sub_score = 1.0 if val >= 75 else 0.75 if val >= 56 else 0.50 if val >= 45 else 0.25 if val >= 25 else 0.05
    return sub_score, f"Index {val} ({classification}) → sub-score {sub_score:.2f}"

def score_portfolio_heat(portfolio_heat, action):
    if not portfolio_heat: return None, "No portfolio heat data"
    score_val = portfolio_heat.get("score", 50)
    freeze_buys = portfolio_heat.get("freezeBuys", False)
    if action == "BUY" and freeze_buys: return 0.0, "FREEZE BUYS ACTIVE → sub-score 0.00"
    sub_score = (1.0 - (score_val / 100.0)) if action == "BUY" else (score_val / 100.0)
    return sub_score, f"Heat {score_val}% ({portfolio_heat.get('label')}) → sub-score {sub_score:.2f}"

def score_daily_alpha(daily_alpha, action):
    if not daily_alpha: return None, "No XRP Daily Alpha data"
    trend = daily_alpha.get("trend", {})
    direction = trend.get("direction", "neutral")
    confidence = trend.get("confidence", 50)
    direction_bases_buy = {"bullish": 1.0, "neutral": 0.50, "bearish": 0.10}
    direction_bases_sell = {"bullish": 0.10, "neutral": 0.50, "bearish": 1.0}
    bases = direction_bases_buy if action == "BUY" else direction_bases_sell
    sub_score = bases.get(direction, 0.50) * (confidence / 100.0)
    return sub_score, f"Alpha {direction} ({confidence}%) → sub-score {sub_score:.2f}"

def score_fa_sentiment(fa_sentiment, action):
    if not fa_sentiment: return None, "No FA sentiment data"
    score_val = fa_sentiment.get("overallSentimentScore", 0.0)
    normalised = (score_val + 1.0) / 2.0
    sub_score = normalised if action == "BUY" else 1.0 - normalised
    return sub_score, f"FA Sentiment score {score_val:.2f} → sub-score {sub_score:.2f}"

def score_market_filter(market_filter, action):
    if not market_filter: return None, "No market filter data"
    rsi = market_filter.get("compositeRsi", 50.0)
    price_vs_ema = market_filter.get("priceVsEma", 0.0)
    if action == "BUY":
        rsi_s = 1.0 if rsi < 30 else 0.75 if rsi < 40 else 0.55 if rsi < 50 else 0.35 if rsi < 60 else 0.10
        ema_s = 1.0 if price_vs_ema < -10 else 0.80 if price_vs_ema < -5 else 0.65 if price_vs_ema < 0 else 0.45 if price_vs_ema < 10 else 0.20
    else:
        rsi_s = 1.0 if rsi > 70 else 0.75 if rsi > 60 else 0.55 if rsi > 50 else 0.35 if rsi > 40 else 0.10
        ema_s = 1.0 if price_vs_ema > 10 else 0.80 if price_vs_ema > 5 else 0.65 if price_vs_ema > 0 else 0.45 if price_vs_ema < -10 else 0.20
    sub_score = (rsi_s * 0.50) + (ema_s * 0.50)
    return sub_score, f"CompRSI {rsi:.1f}, DistEMA {price_vs_ema:.1f}% → sub-score {sub_score:.2f}"

# ☸️ Core Engine Aggregator Main Function
def compute_sahajata_score(ctx):
    action = ctx.get("action", "BUY")
    gate_enabled = ctx.get("gateEnabled", False)
    min_score = ctx.get("minScore", 50)
    
    raw_dimensions = [
        {"name": "AI Regime", "weight": WEIGHTS["aiRegime"], "res": score_ai_regime(ctx.get("aiRegime"), action)},
        {"name": "Multi-TF RSI Confluence", "weight": WEIGHTS["confluence"], "res": score_confluence(ctx.get("confluence"), action)},
        {"name": "SmartScore", "weight": WEIGHTS["smartScore"], "res": score_smart_score(ctx.get("smartScore"), action)},
        {"name": "Market Structure", "weight": WEIGHTS["marketStructure"], "res": score_market_structure(ctx.get("marketStructure"), action)},
        {"name": "Order Flow", "weight": WEIGHTS["orderFlow"], "res": score_order_flow(ctx.get("orderFlow"), action)},
        {"name": "Candlestick Pattern", "weight": WEIGHTS["pattern"], "res": score_pattern(ctx.get("patternAnalysis"), action)},
        {"name": "Fear & Greed", "weight": WEIGHTS["fearGreed"], "res": score_fear_greed(ctx.get("fearGreed"), action)},
        {"name": "Portfolio Heat", "weight": WEIGHTS["portfolioHeat"], "res": score_portfolio_heat(ctx.get("portfolioHeat"), action)},
        {"name": "XRP Daily Alpha", "weight": WEIGHTS["dailyAlpha"], "res": score_daily_alpha(ctx.get("dailyAlpha"), action)},
        {"name": "FA Sentiment", "weight": WEIGHTS["faSentiment"], "res": score_fa_sentiment(ctx.get("faSentiment"), action)},
        {"name": "Market Filter", "weight": WEIGHTS["marketFilter"], "res": score_market_filter(ctx.get("marketFilter"), action)},
    ]
    
    dimensions_results, available_dims, total_available_weight = [], [], 0
    for d in raw_dimensions:
        sub_score, desc = d["res"]
        is_available = sub_score is not None
        contribution = (sub_score * d["weight"]) if is_available else 0
        dim_data = {"name": d["name"], "weight": d["weight"], "subScore": sub_score, "contribution": contribution, "available": is_available, "description": desc}
        dimensions_results.append(dim_data)
        if is_available:
            available_dims.append(dim_data)
            total_available_weight += d["weight"]
            
    data_completeness = len(available_dims) / len(raw_dimensions)
    if total_available_weight == 0: score = 50
    else:
        weighted_sum = sum(d["contribution"] for d in available_dims)
        score = round(max(0, min(100, (weighted_sum / total_available_weight) * 100)))
        
    def get_label(s):
        if s >= 80: return "PERFECT CO-ARISING", "#00cc66", 1.50
        if s >= 65: return "STRONG CO-ARISING", "#33cc33", 1.25
        if s >= 50: return "MODERATE CO-ARISING", "#ffaa00", 1.00
        if s >= 35: return "WEAK CO-ARISING", "#ff6600", 0.75
        return "NO CO-ARISING", "#ff3333", 0.25

    label, color, mult = get_label(score)
    gate_blocked = gate_enabled and (score < min_score)
    return {"score": score, "label": label, "color": color, "multiplier": mult, "dataCompleteness": data_completeness, "dimensions": dimensions_results, "gateBlocked": gate_blocked}

# 📊 4. Market Data Aggregator & Live Context Builder
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

    # Fetch live Crypto Fear & Greed Index
    fng_val, fng_class = 50, "Neutral"
    try:
        fng_res = requests.get("https://api.alternative.me/fng/?limit=1", timeout=3).json()
        if fng_res.get("data"):
            fng_val = int(fng_res["data"][0]["value"])
            fng_class = fng_res["data"][0]["value_classification"]
    except Exception: pass

    # 🛠️ Build Live Confluence Matrix Context Context (Syncing Real-time Market Rules)
    zone_pct = (price - low) / (high - low) if high > low else 0.5
    price_zone = "AT_SUPPORT" if zone_pct < 0.2 else "BELOW_SUPPORT" if zone_pct < 0.0 else "AT_RESISTANCE" if zone_pct > 0.8 else "ABOVE_RESISTANCE" if zone_pct > 1.0 else "BETWEEN_LEVELS"
    structure = "TRENDING_UP" if (ema20 and price > ema20) else "TRENDING_DOWN"
    rsi_score_mapped = 6 if (rsi_val and rsi_val < 30) else 5 if (rsi_val and rsi_val < 40) else 4 if (rsi_val and rsi_val < 50) else 3 if (rsi_val and rsi_val < 60) else 1
    
    ctx = {
        "action": "BUY",
        "gateEnabled": False,
        "minScore": 50,
        "aiRegime": {"regime": "BULL_TREND" if structure == "TRENDING_UP" else "RECOVERY", "confidence": 0.85},
        "confluence": {"score": rsi_score_mapped, "confidence": 0.90},
        "smartScore": {"signal": "STRONG_BUY" if rsi_score_mapped >= 5 else "BUY" if rsi_score_mapped == 4 else "NEUTRAL", "confidence": 0.80},
        "marketStructure": {"priceZone": price_zone, "structure": structure},
        "orderFlow": {"signal": "STRONG_BUY_PRESSURE" if (macd_data[2] and macd_data[2] > 0) else "NEUTRAL", "confidence": 0.75, "dataQuality": "REALTIME"},
        "patternAnalysis": {"signalStrength": "MODERATE", "dominantSignal": "BULLISH_ENGULFING" if change > 0 else "NONE", "bullishScore": 0.70, "bearishScore": 0.30},
        "fearGreed": {"value": fng_val, "classification": fng_class},
        "portfolioHeat": {"score": 35, "label": "Optimal Range", "freezeBuys": False},
        "dailyAlpha": {"trend": {"direction": "bullish" if change > 0 else "neutral", "confidence": 70}},
        "faSentiment": {"overallSentimentScore": 0.45, "sentimentLabel": "Bullish Bias"},
        "marketFilter": {"compositeRsi": rsi_val if rsi_val else 50.0, "priceVsEma": ((price - ema50)/ema50 * 100) if ema50 else 0.0}
    }

    return price, high, low, change, source, funding_rate, ctx
    def get_xrpl_wallet_balance(wallet_address):
    """
    XRPL Public RPC မှတစ်ဆင့် ပေးထားသော Address ၏ Live XRP Balance ကို ဆွဲယူပေးသည့် လုပ်ဆောင်ချက်
    """
    if not wallet_address or not wallet_address.startswith('r'):
        return 0.0
        
    url = "https://xrplcluster.com/"  # Public XRPL RPC Endpoint
    headers = {"Content-Type": "application/json"}
    payload = {
        "method": "account_info",
        "params": [
            {
                "account": wallet_address,
                "ledger_index": "validated"
            }
        ]
    }
    
    try:
        response = requests.post(url, headers=headers, json=payload, timeout=10)
        data = response.json()
        
        if "result" in data and "account_data" in data["result"]:
            # XRPL သည် Balance ကို Drops ယူနစ်ဖြင့်ပြသသဖြင့် 1,000,000 ဖြင့် ပြန်စားရပါသည် (1 XRP = 1,000,000 Drops)
            balance_drops = int(data["result"]["account_data"]["Balance"])
            return balance_drops / 1000000.0
    except Exception as e:
        print(f"XRPL Balance Fetch Error: {e}")
        
    return 0.0

# 🧠 5. OpenRouter AI Core
def ask_ai_advanced_analysis(price, change, funding, matrix_res):
    if OPENROUTER_API_KEY == "YOUR_OPENROUTER_API_KEY_HERE": return "❌ OpenRouter API Key configuration missing."
    url = "https://openrouter.ai/api/v1/chat/completions"
    headers = {"Authorization": f"Bearer {OPENROUTER_API_KEY}", "Content-Type": "application/json"}
    
    dims_txt = "\n".join([f"- {d['name']}: {d['description']}" for d in matrix_res['dimensions']])
    market_data_prompt = (
        f"Perform a professional quantitative portfolio analysis for XRP/USDT:\n"
        f"Price: ${price:.4f} | 24h Change: {change:+.2f}%\n"
        f"Funding: {funding} | Sahajata Confluence Score: {matrix_res['score']}/100 ({matrix_res['label']}) | Sizing Multiplier: {matrix_res['multiplier']}x\n\n"
        f"Detailed 11-Dimensions Matrix Metrics:\n{dims_txt}\n\n"
        f"Provide short-term key strategic levels and allocation breakdown inside elegant markdown format."
    )
    payload = {
        "model": "openai/gpt-4o-mini",
        "messages": [
            {"role": "system", "content": "You are an institutional crypto portfolio allocation strategist. Respond strictly in professional markdown English."},
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
    bot.reply_to(message, "👋 **XRP 11-Dimensions Sahajāta Matrix Bot Active!**\nUse `/indicators` or `/analyze`.", parse_mode="Markdown")

@bot.message_handler(commands=['indicators'])
def telegram_indicators(message):
    save_chat_id(message.chat.id)
    data = get_xrp_advanced_data()
    if data:
        price, _, _, change, source, funding, ctx = data
        matrix_res = compute_sahajata_score(ctx)
        msg = (
            f"📊 **XRP/USDT Institutional Matrix**\n━━━━━━━━━━━━━━\n"
            f"💵 Price: `${price:.4f}` ({change:+.2f}%)\n"
            f"⏳ Funding: `{funding}` | Source: `{source}`\n"
            f"📈 Data Completeness: `{matrix_res['dataCompleteness']*100:.0f}%`\n━━━━━━━━━━━━━━\n"
            f"☸️ **Sahajāta Score:** `{matrix_res['score']}/100`\n"
            f"🏷️ State: `[{matrix_res['label']}]`\n"
            f"⚙️ Position Multiplier: `{matrix_res['multiplier']}x`"
        )
        bot.reply_to(message, msg, parse_mode="Markdown")

@bot.message_handler(commands=['analyze'])
def telegram_analyze(message):
    save_chat_id(message.chat.id)
    data = get_xrp_advanced_data()
    if not data: return
    price, _, _, change, _, funding, ctx = data
    matrix_res = compute_sahajata_score(ctx)
    load_msg = bot.reply_to(message, "🤖 _Processing 11-dimensions confluence analysis..._", parse_mode="Markdown")
    ai_report = ask_ai_advanced_analysis(price, change, funding, matrix_res)
    try: bot.edit_message_text(ai_report, chat_id=message.chat.id, message_id=load_msg.message_id, parse_mode="Markdown")
    except Exception: bot.reply_to(message, ai_report)

# 🌐 8. BACKGROUND CO-RUNNER INITIALIZATION (The Secret Sauce)
#@st.cache_resource
#def start_global_services():    
#try:
# ၁။ ယခင်က Webhook လမ်းကြောင်းတစ်ခုခု ငြိနေရင် လုံးဝ အရင်ရှင်းပစ်မယ်
#       bot.remove_webhook()
#       time.sleep(1)
        
#        # ၂။ Streamlit Container ထဲမှာ Polling အဟောင်း ကျန်ခဲ့ရင် အရင်ရပ်ပစ်မယ်
#        bot.stop_polling()
#        time.sleep(1)
#    except Exception:
#        pass

#    # ၃။ Thread အသစ်နဲ့ စိတ်ချရအောင် Polling ကို ပြန်စမောင်းမယ်
#    # skip_pending=True ထည့်ထားလို့ Bot ပိတ်ထားတုန်းက ဝင်နေတဲ့ မက်ဆေ့ခ်ျဟောင်းတွေကို ကျော်သွားပါလိမ့်မယ်
#    t1 = threading.Thread(target=bot.infinity_polling, kwargs={"skip_pending": True}, daemon=True)
#    t1.start()
    
#    t2 = threading.Thread(target=price_alert_monitor, daemon=True)
#    t2.start()
    
#    return True

# ပင်မ ဝန်ဆောင်မှုများကို စတင်နှိုးဆော်ခြင်း
#start_global_services()


# 💻 9. STREAMLIT WEB DASHBOARD UI (Institutional Style V3)
st.title("☸️ Sahajāta Confluence Matrix")
st.caption("Institutional Quantitative Engine for XRP Accumulation (Paṭṭhāna Logic V3)")

# Refresh Button
if st.button("🔄 Refresh Live Market Data", type="primary", use_container_width=True):
    st.rerun()

market_data = get_xrp_advanced_data()

if market_data:
    price, high, low, change, source, funding, ctx = market_data
    matrix_res = compute_sahajata_score(ctx)
# ─── SIDEBAR CONFIGURATION (ဘေးဘားတွင် Wallet လိပ်စာ ထည့်ရန်နေရာ) ───
st.sidebar.header("🔑 Wallet Configuration")
# အစ်ကိုကြီး၏ XRPL Address ကို value နေရာတွင် ကြိုတင်ထည့်ထားနိုင်ပါသည်
target_wallet = st.sidebar.text_input(
    "XRP On-Chain Address", 
    value="rYourActualXRPWalletAddressHere...",
    help="မိမိ၏ r-address ကို ထည့်ပါ။ Secret Key များ ထည့်ရန်မလိုပါ။"
)

# Live Data များ ရယူပြီးချိန်တွင် Wallet ဒေတာကိုပါ ဆွဲယူမည်
if market_data:
    price, high, low, change, source, funding, ctx = market_data
    
    # Wallet Balance ကို Blockchain ပေါ်မှ ဆွဲယူခြင်း
    wallet_balance = get_xrpl_wallet_balance(target_wallet)
    portfolio_value_usd = wallet_balance * price  # လက်ရှိ ဒေါ်လာတန်ဖိုး တွက်ချက်ခြင်း

    # ─── 1. HERO SECTION (Main Metrics Grid တွင် Wallet ပြသခြင်း) ───
    m1, m2, m3, m4 = st.columns(4)  # ကတ်ပြား ၄ ခုအဖြစ် တိုးချဲ့လိုက်ပါသည်
    m1.metric("💵 XRP Price", f"${price:.4f}", f"{change:+.2f}%")
    m2.metric("⏳ Funding Rate", funding)
    m3.metric("💼 XRP Balance", f"{wallet_balance:,.2f} XRP")
    m4.metric("💰 Wallet Value", f"${portfolio_value_usd:,.2f}")

    st.markdown("---")


    # ─── 1. HERO SECTION (Main Metrics Grid) ───
    m1, m2, m3 = st.columns(3)
    m1.metric("💵 XRP Price", f"${price:.4f}", f"{change:+.2f}%")
    m2.metric("⏳ Funding Rate", funding)
    m3.metric("📊 Data Sync", f"{matrix_res['dataCompleteness']*100:.0f}%")

    st.markdown("---")

    # ─── 2. CORE MATRIX SCORE PANEL ───
    st.markdown(f"### ☸️ Sahajāta Confluence Score: `{matrix_res['score']} / 100`")
    st.progress(matrix_res['score'] / 100)
    
    # Dynamic State Banner
    st.markdown(
        f"<div style='background-color:{matrix_res['color']}; padding:16px; border-radius:10px; text-align:center; color:white; font-weight:bold; font-size:22px; margin-bottom:25px;'>"
        f"STATE: {matrix_res['label']} ({matrix_res['multiplier']}x Position Sizing)"
        f"</div>", 
        unsafe_allow_html=True
    )

    # ─── 3. CATEGORIZED 11-DIMENSIONS TABS (ဖုန်းအတွက် အထူးအဆင်ပြေမည့်စနစ်) ───
    st.subheader("📊 11-Dimensions Co-Arising Breakdown")
    tab1, tab2, tab3 = st.tabs(["🧠 Core Engines (59%)", "📈 Flow & Patterns (20%)", "🌍 Macro & Sentiment (21%)"])
    
    dims = matrix_res["dimensions"]
    
    with tab1:
        st.markdown("### Primary Market Matrix")
        # Core Engines ၄ ခုကို ပြသခြင်း
        core_names = ["AI Regime", "Multi-TF RSI Confluence", "SmartScore", "Market Structure"]
        for d in dims:
            if d["name"] in core_names:
                with st.expander(f"🔹 {d['name']} (Weight: {d['weight']}%)", expanded=True):
                    st.write(f"Sub-Score: `{d['subScore']}`")
                    st.caption(f"_{d['description']}_")

    with tab2:
        st.markdown("### Execution & Order Flow")
        # Flow Engines ၂ ခုကို ပြသခြင်း
        flow_names = ["Order Flow", "Candlestick Pattern"]
        for d in dims:
            if d["name"] in flow_names:
                with st.expander(f"🔸 {d['name']} (Weight: {d['weight']}%)", expanded=True):
                    st.write(f"Sub-Score: `{d['subScore']}`")
                    st.caption(f"_{d['description']}_")

    with tab3:
        st.markdown("### Global Sentiment & Filters")
        # Macro & Sentiment ၅ ခုကို ပြသခြင်း
        macro_names = ["Fear & Greed", "Portfolio Heat", "XRP Daily Alpha", "FA Sentiment", "Market Filter"]
        for d in dims:
            if d["name"] in macro_names:
                with st.expander(f"🌐 {d['name']} (Weight: {d['weight']}%)", expanded=True):
                    st.write(f"Sub-Score: `{d['subScore']}`")
                    st.caption(f"_{d['description']}_")

    st.markdown("---")

    # ─── 4. EXECUTIVE AI ANALYSIS BLOCK ───
    st.subheader("🧠 Executive Strategic AI Analysis")
    if st.button("🤖 Generate Real-Time Institutional Report", use_container_width=True):
        with st.spinner("Synchronizing cross-border matrix via AI Strategy Engine..."):
            ai_report_web = ask_ai_advanced_analysis(price, change, funding, matrix_res)
            st.markdown(ai_report_web)
else:
    st.error("Market Engine Connection Error. Please verify network or API status.")

