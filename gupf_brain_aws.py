# gupf_brain_aws.py - VERSI 5.1 (Genesis Protocol - Sentinel)

import os
import ccxt.async_support as ccxt
import pandas as pd
import pandas_ta as ta
import telegram
import asyncio
import json
import requests
import traceback
from datetime import datetime, timedelta, timezone

# --- GLOBAL STATE & CONFIGURATION ---
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHANNEL_ID = os.environ.get("TELEGRAM_CHANNEL_ID")
NEWS_API_KEY = os.environ.get("NEWS_API_KEY")
FUTURES_SIGNAL_FOUND = False # Global flag to track if a primary signal was found

# Cache Config
CACHE_PATH = '/tmp/gupf_sentiment_cache.json'
CACHE_MAX_AGE_HOURS = 6

# --- DUAL-MODE PROTOCOLS ---

async def execute_futures_scan_protocol():
    """Primary Alpha-Seeking Protocol for Futures Market."""
    global FUTURES_SIGNAL_FOUND
    print("🚀 Initiating GUPF v5.0 Futures Scan Protocol...")
    scan_list = await get_scan_list()
    
    exchange = ccxt.binance({'options': {'defaultType': 'future'}})
    try:
        tasks = [process_futures_asset(symbol, source, exchange) for symbol, source in scan_list.items()]
        await asyncio.gather(*tasks)
    finally:
        await exchange.close()

    print("✅ Futures Scan Protocol Concluded.")

async def execute_spot_scalp_subroutine():
    """
    ### EVOLUTION: v5.1 ###
    Secondary Capital-Efficiency Sub-routine. Now operates as a Sentinel Listener Loop.
    """
    print("💡 No futures signal found. Initiating Sentinel Protocol (Spot Scalp)...")
    
    SCALP_ASSET = 'BNB/USDT'
    TP_PERCENT = 0.008  # 0.8%
    SL_PERCENT = 0.004  # 0.4%
    
    # --- Sentinel Loop Parameters ---
    MAX_DURATION_SECONDS = 270  # Run for 4.5 minutes
    CHECK_INTERVAL_SECONDS = 15   # Check market every 15 seconds
    start_time = asyncio.get_event_loop().time()

    exchange = ccxt.binance({'options': {'defaultType': 'spot'}})
    try:
        while (asyncio.get_event_loop().time() - start_time) < MAX_DURATION_SECONDS:
            # Fetch 1-minute data
            bars = await exchange.fetch_ohlcv(SCALP_ASSET, timeframe='1m', limit=100)
            df = pd.DataFrame(bars, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
            
            # Calculate scalping indicators
            df.ta.ema(length=9, append=True)
            df.ta.rsi(length=14, append=True)

            last = df.iloc[-1]
            prev = df.iloc[-2]

            print(f"  [Sentinel] Checking {SCALP_ASSET}... Close: {last['close']}, EMA_9: {last['EMA_9']:.2f}, RSI: {last['RSI_14']:.2f}")

            # Scalping Buy Logic
            if prev['close'] < prev['EMA_9'] and last['close'] > last['EMA_9'] and 50 < last['RSI_14'] < 70:
                entry_price = last['close']
                take_profit = entry_price * (1 + TP_PERCENT)
                stop_loss = entry_price * (1 - SL_PERCENT)

                prec = (await exchange.market(SCALP_ASSET))['precision']['price']
                
                signal_data = {
                    "protocol": "Scalp", "symbol": SCALP_ASSET, "side": "BUY",
                    "entry": f"{entry_price:.{prec}f}", "tp1": f"{take_profit:.{prec}f}", "sl": f"{stop_loss:.{prec}f}",
                    "confidence": 0.99, "source": "Sentinel Protocol"
                }
                await send_cornix_signal(signal_data)
                print(f"  [Sentinel] Entry condition met! Signal dispatched. Terminating sub-routine.")
                break # Exit the loop after finding a signal

            # Wait for the next check
            await asyncio.sleep(CHECK_INTERVAL_SECONDS)

    except Exception as e:
        print(f"🔴 ERROR in Sentinel Protocol: {e}")
    finally:
        await exchange.close()
    print("✅ Sentinel Protocol Concluded.")


# --- CORE LOGIC & HELPER FUNCTIONS ---

async def process_futures_asset(symbol, source, exchange):
    """Analyzes a single asset for the Futures Protocol."""
    global FUTURES_SIGNAL_FOUND
    try:
        bars = await exchange.fetch_ohlcv(symbol, timeframe='1h', limit=200)
        df = pd.DataFrame(bars, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        
        # Calculate all indicators
        df.ta.bbands(length=20, append=True)
        df.ta.rsi(length=14, append=True)
        df.ta.macd(fast=12, slow=26, append=True)
        df.ta.atr(length=14, append=True)

        # Validate data integrity
        required_cols = ['RSI_14', 'MACD_12_26_9', 'MACDs_12_26_9', 'BBL_20_2.0', 'BBU_20_2.0', 'ATRr_14']
        if any(col not in df.columns for col in required_cols) or df[required_cols].iloc[-1].isnull().any():
            return

        tech_score = get_technical_score(df)
        chaos_score = get_chaos_score(df)
        sentiment_score = get_sentiment_score(symbol)

        # Tuned weighting and threshold
        final_score = (tech_score * 0.70) + (sentiment_score * 0.15) + (chaos_score * 0.15)
        CONFIDENCE_THRESHOLD = 0.40
        
        print(f"[{symbol:<12}] Futures Score: {final_score:.2f} (T:{tech_score:.2f}, S:{sentiment_score:.2f}, C:{chaos_score:.2f}) | Source: {source}")

        if final_score >= CONFIDENCE_THRESHOLD or final_score <= -CONFIDENCE_THRESHOLD:
            last_close = df.iloc[-1]['close']
            last_atr_percent = df.iloc[-1]['ATRr_14']
            
            sl_multiplier = 2.0
            tp_multiplier = 3.5
            
            side = "BUY" if final_score > 0 else "SELL"
            sl_factor = -1 if side == "BUY" else 1
            tp_factor = 1 if side == "BUY" else -1

            stop_loss = last_close * (1 + (sl_factor * (last_atr_percent / 100) * sl_multiplier))
            take_profit = last_close * (1 + (tp_factor * (last_atr_percent / 100) * tp_multiplier))

            prec = (await exchange.market(symbol))['precision']['price']
            
            signal_data = {
                "protocol": "Futures",
                "symbol": symbol, "side": side, "entry": f"{last_close:.{prec}f}", "sl": f"{stop_loss:.{prec}f}", "tp1": f"{take_profit:.{prec}f}",
                "confidence": final_score, "source": source, "tech_score": tech_score, "sent_score": sentiment_score, "chaos_score": chaos_score
            }
            await send_cornix_signal(signal_data)
            FUTURES_SIGNAL_FOUND = True # Set the flag!

    except Exception:
        # traceback.print_exc()
        pass

async def send_cornix_signal(signal_data):
    """Universal Signal Dispatcher."""
    bot = telegram.Bot(token=TELEGRAM_BOT_TOKEN)
    symbol_plain = signal_data['symbol'].replace('/', '')
    
    if signal_data['protocol'] == "Futures":
        message = f"""
        🚀 GUPF v5.0 Futures Signal 🚀
        Coin: #{symbol_plain}
        Signal: {signal_data['side']}

        Entry: {signal_data['entry']}
        Take-Profit 1: {signal_data['tp1']}
        Stop-Loss: {signal_data['sl']}

        Confidence: {signal_data['confidence']:.2f} (T:{signal_data['tech_score']:.2f}, S:{signal_data['sent_score']:.2f}, C:{signal_data['chaos_score']:.2f})
        Source: {signal_data['source']}
        """
    else: # Scalp Protocol
        message = f"""
        💡 GUPF v5.0 Spot Scalp Signal 💡
        Asset: #{symbol_plain} (SPOT)
        Action: {signal_data['side']}

        Entry: {signal_data['entry']}
        Take-Profit: {signal_data['tp1']} (Fixed 0.8%)
        Stop-Loss: {signal_data['sl']} (Fixed 0.4%)

        Protocol: Capital Efficiency Sub-routine
        """
    await bot.send_message(chat_id=TELEGRAM_CHANNEL_ID, text=message)
    print(f"✅ [{signal_data['symbol']}] {signal_data['protocol']} signal dispatched.")

# --- (The rest of the helper functions: get_scan_list, get_technical_score, get_sentiment_score, get_chaos_score remain the same as v4.3) ---
# For brevity, I am including them here without changes.
def get_technical_score(df: pd.DataFrame) -> float:
    score = 0.0
    try:
        if len(df) < 2: return 0.0
        last_row = df.iloc[-1]
        prev_row = df.iloc[-2]
        rsi = last_row.get('RSI_14', 50)
        if 30 <= rsi < 35: score += 0.15
        elif rsi < 30: score += 0.30
        macd_line, signal_line, prev_macd_line, prev_signal_line = last_row.get('MACD_12_26_9'), last_row.get('MACDs_12_26_9'), prev_row.get('MACD_12_26_9'), prev_row.get('MACDs_12_26_9')
        if all(v is not None for v in [prev_macd_line, prev_signal_line, macd_line, signal_line]):
            if prev_macd_line < prev_signal_line and macd_line > signal_line: score += 0.35
        lower_band = last_row.get('BBL_20_2.0', 0)
        if lower_band > 0 and last_row['close'] < lower_band: score += 0.35
        if 65 <= rsi < 70: score -= 0.15
        elif rsi >= 70: score -= 0.30
        if all(v is not None for v in [prev_macd_line, prev_signal_line, macd_line, signal_line]):
            if prev_macd_line > prev_signal_line and macd_line < signal_line: score -= 0.35
        upper_band = last_row.get('BBU_20_2.0', 0)
        if upper_band > 0 and last_row['close'] > upper_band: score -= 0.35
        return max(min(score, 1.0), -1.0)
    except Exception: return 0.0

def get_sentiment_score(symbol: str) -> float:
    try:
        with open(CACHE_PATH, 'r') as f: cache = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError): cache = {}
    if symbol in cache:
        cached_data, timestamp = cache[symbol], datetime.fromisoformat(cache[symbol]['timestamp'])
        age_hours = (datetime.now(timezone.utc) - timestamp).total_seconds() / 3600
        if age_hours < CACHE_MAX_AGE_HOURS: return cached_data['score']
    if not NEWS_API_KEY: return 0.0
    try:
        search_term, score = symbol.split('/')[0].lower(), 0
        url = (f"https://newsapi.org/v2/everything?q={search_term}&from={(datetime.now() - timedelta(days=2)).strftime('%Y-%m-%d')}&sortBy=relevancy&language=en&apiKey={NEWS_API_KEY}")
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        articles = response.json().get('articles', [])
        if not articles: return 0.0
        POSITIVE_KEYWORDS = ['bullish', 'upgrade', 'rally', 'breakthrough', 'gains', 'profit', 'surges', 'optimistic', 'partnership', 'launch', 'integration']
        NEGATIVE_KEYWORDS = ['bearish', 'downgrade', 'crash', 'risk', 'loss', 'plunges', 'fears', 'scam', 'hack', 'vulnerability', 'investigation', 'lawsuit']
        score += sum(1 for a in articles[:10] if any(w in a.get('title','').lower() for w in POSITIVE_KEYWORDS))
        score -= sum(1 for a in articles[:10] if any(w in a.get('title','').lower() for w in NEGATIVE_KEYWORDS))
        final_score = score / 10.0
        cache[symbol] = {'score': final_score, 'timestamp': datetime.now(timezone.utc).isoformat()}
        with open(CACHE_PATH, 'w') as f: json.dump(cache, f)
        return final_score
    except requests.exceptions.HTTPError as e:
        if e.response.status_code == 429: print(f"[{symbol}] 🟡 INFO: Jatah NewsAPI habis.")
        return 0.0
    except Exception: return 0.0

def get_chaos_score(df: pd.DataFrame) -> float:
    try:
        last_atr_percent, avg_atr_percent = df.iloc[-1]['ATRr_14'], df['ATRr_14'].tail(50).mean()
        if pd.isna(last_atr_percent) or pd.isna(avg_atr_percent) or avg_atr_percent == 0: return 0.0
        if last_atr_percent > avg_atr_percent * 1.8: return -0.3
        if last_atr_percent < avg_atr_percent * 0.7: return -0.2
        return 0.1
    except Exception: return 0.0

async def get_scan_list():
    exchange = ccxt.binance()
    try:
        await exchange.load_markets()
        tickers = await exchange.fetch_tickers()
    finally: await exchange.close()
    MIN_VOLUME_USD, CORE_ASSETS = 10000000, {'BTC/USDT', 'ETH/USDT', 'BNB/USDT', 'SOL/USDT'}
    filtered_tickers = {s: t for s, t in tickers.items() if s.endswith('/USDT') and 'UP/' not in s and 'DOWN/' not in s and t.get('quoteVolume', 0) > MIN_VOLUME_USD and t.get('percentage') is not None}
    ticker_list = list(filtered_tickers.values())
    top_gainers = sorted(ticker_list, key=lambda x: x['percentage'], reverse=True)[:10]
    top_losers = sorted(ticker_list, key=lambda x: x['percentage'])[:10]
    top_volume = sorted(ticker_list, key=lambda x: x['quoteVolume'], reverse=True)[:10]
    scan_list = {s: "Core Asset" for s in CORE_ASSETS}
    for t in top_gainers: scan_list[t['symbol']] = "Top Gainer"
    for t in top_losers: scan_list[t['symbol']] = "Top Loser"
    for t in top_volume: scan_list[t['symbol']] = "Top Volume"
    return scan_list

# --- MASTER LAMBDA HANDLER ---
def handler(event, context):
    """The absolute entrypoint of the GUPF system."""
    global FUTURES_SIGNAL_FOUND
    FUTURES_SIGNAL_FOUND = False # Reset flag at the start of each run

    # Using asyncio.run for cleaner top-level execution
    # Run primary protocol
    asyncio.run(execute_futures_scan_protocol())

    # Conditionally execute secondary protocol
    if not FUTURES_SIGNAL_FOUND:
        asyncio.run(execute_spot_scalp_subroutine())
    else:
        print("✅ Futures signal found. Bypassing Sentinel Protocol.")
    
    return {'statusCode': 200, 'body': json.dumps('GUPF v5.1 Cycle Complete.')}
