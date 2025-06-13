# gupf_brain_aws.py - VERSI 4.2 (The Thrifty Engine)

import os
import ccxt.async_support as ccxt
import pandas as pd
import pandas_ta as ta
import telegram
import asyncio
import json
import requests
import traceback
from datetime import datetime, timedelta, timezone # ### BARU ###

# --- KONFIGURASI ---
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHANNEL_ID = os.environ.get("TELEGRAM_CHANNEL_ID")
NEWS_API_KEY = os.environ.get("NEWS_API_KEY")

# ### BARU: KONFIGURASI CACHE ###
CACHE_PATH = '/tmp/gupf_sentiment_cache.json' # Direktori sementara Lambda, aman digunakan
CACHE_MAX_AGE_HOURS = 6 # Simpan hasil sentimen selama 6 jam

# --- MESIN SKORING (Dengan Perbaikan) ---

def get_technical_score(df: pd.DataFrame) -> float:
    # Versi ini sudah bagus, tidak diubah
    score = 0.0
    try:
        if len(df) < 2: return 0.0
        last_row = df.iloc[-1]
        prev_row = df.iloc[-2]

        rsi = last_row.get('RSI_14', 50)
        if 30 <= rsi < 35: score += 0.15
        elif rsi < 30: score += 0.30

        macd_line = last_row.get('MACD_12_26_9')
        signal_line = last_row.get('MACDs_12_26_9')
        prev_macd_line = prev_row.get('MACD_12_26_9')
        prev_signal_line = prev_row.get('MACDs_12_26_9')
        if all(v is not None for v in [prev_macd_line, prev_signal_line, macd_line, signal_line]):
            if prev_macd_line < prev_signal_line and macd_line > signal_line:
                score += 0.35

        lower_band = last_row.get('BBL_20_2.0', 0)
        if lower_band > 0 and last_row['close'] < lower_band:
            score += 0.35

        if 65 <= rsi < 70: score -= 0.15
        elif rsi >= 70: score -= 0.30

        if all(v is not None for v in [prev_macd_line, prev_signal_line, macd_line, signal_line]):
            if prev_macd_line > prev_signal_line and macd_line < signal_line:
                score -= 0.35

        upper_band = last_row.get('BBU_20_2.0', 0)
        if upper_band > 0 and last_row['close'] > upper_band:
            score -= 0.35

        return max(min(score, 1.0), -1.0)
    except Exception:
        return 0.0

def get_sentiment_score(symbol: str) -> float:
    """
    ### BARU ### Versi ini menggunakan CACHING untuk menghemat panggilan API.
    """
    # 1. BACA CACHE YANG ADA
    try:
        with open(CACHE_PATH, 'r') as f:
            cache = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        cache = {}

    # 2. PERIKSA APAKAH ADA DATA VALID DI CACHE
    if symbol in cache:
        cached_data = cache[symbol]
        timestamp = datetime.fromisoformat(cached_data['timestamp'])
        age_hours = (datetime.now(timezone.utc) - timestamp).total_seconds() / 3600
        if age_hours < CACHE_MAX_AGE_HOURS:
            print(f"[{symbol}] ✅ CACHED: Menggunakan skor sentimen dari cache (Umur: {age_hours:.1f} jam)")
            return cached_data['score']

    # 3. JIKA TIDAK ADA DI CACHE, LANJUTKAN DENGAN PANGGILAN API
    # print(f"[{symbol}] CACHE MISS: Mengambil skor sentimen baru...") # Bisa diaktifkan untuk debugging
    if not NEWS_API_KEY:
        return 0.0

    try:
        search_term = symbol.split('/')[0].lower()
        url = (f"https://newsapi.org/v2/everything?q={search_term}&from={(datetime.now() - timedelta(days=2)).strftime('%Y-%m-%d')}"
               f"&sortBy=relevancy&language=en&apiKey={NEWS_API_KEY}")
        
        response = requests.get(url, timeout=10)
        response.raise_for_status() 

        articles = response.json().get('articles', [])
        if not articles:
            return 0.0

        POSITIVE_KEYWORDS = ['bullish', 'upgrade', 'rally', 'breakthrough', 'gains', 'profit', 'surges', 'optimistic', 'partnership', 'launch', 'integration']
        NEGATIVE_KEYWORDS = ['bearish', 'downgrade', 'crash', 'risk', 'loss', 'plunges', 'fears', 'scam', 'hack', 'vulnerability', 'investigation', 'lawsuit']
        
        score = sum(1 for a in articles[:10] if any(w in a.get('title','').lower() for w in POSITIVE_KEYWORDS))
        score -= sum(1 for a in articles[:10] if any(w in a.get('title','').lower() for w in NEGATIVE_KEYWORDS))
        
        final_score = score / 10.0
        
        # 4. SIMPAN HASIL BARU KE CACHE
        cache[symbol] = {
            'score': final_score,
            'timestamp': datetime.now(timezone.utc).isoformat()
        }
        with open(CACHE_PATH, 'w') as f:
            json.dump(cache, f)

        print(f"[{symbol}] ✅ FRESH: Skor sentimen baru dihitung dan disimpan ke cache: {final_score}")
        return final_score

    except requests.exceptions.HTTPError as e:
        if e.response.status_code == 429: # Rate Limited
            # Ini bukan error fatal, hanya jatah habis.
            print(f"[{symbol}] 🟡 INFO: Jatah NewsAPI habis untuk sementara.")
        else:
            print(f"[{symbol}] 🔴 GAGAL: HTTP Error saat memanggil NewsAPI. Status: {e.response.status_code}")
        return 0.0
    except Exception:
        # traceback.print_exc()
        return 0.0

# ... (sisa kode seperti get_chaos_score, send_cornix_signal, dll TIDAK BERUBAH) ...
# Cukup ganti seluruh file dengan kode ini, sisa fungsi di bawah ini sudah saya sertakan.
def get_chaos_score(df: pd.DataFrame) -> float:
    try:
        last_atr_percent = df.iloc[-1]['ATRr_14']
        avg_atr_percent = df['ATRr_14'].tail(50).mean()
        if pd.isna(last_atr_percent) or pd.isna(avg_atr_percent) or avg_atr_percent == 0:
            return 0.0
        if last_atr_percent > avg_atr_percent * 1.8: return -0.3
        if last_atr_percent < avg_atr_percent * 0.7: return -0.2
        return 0.1
    except Exception:
        return 0.0

async def send_cornix_signal(signal_data):
    bot = telegram.Bot(token=TELEGRAM_BOT_TOKEN)
    symbol_plain = signal_data['symbol'].replace('/', '')
    message = f"""
🚀 GUPF v4.2 Signal (Thrifty) 🚀
Coin: #{symbol_plain}
Signal: {signal_data['side']}

Entry: {signal_data['entry']}
Take-Profit 1: {signal_data['tp1']}
Stop-Loss: {signal_data['sl']}

Confidence: {signal_data['confidence']:.2f} (T:{signal_data['tech_score']:.2f}, S:{signal_data['sent_score']:.2f}, C:{signal_data['chaos_score']:.2f})
Source: {signal_data['source']}
"""
    await bot.send_message(chat_id=TELEGRAM_CHANNEL_ID, text=message)
    print(f"✅ [{signal_data['symbol']}] Sinyal {signal_data['side']} berhasil dikirim ke Telegram.")

async def get_scan_list():
    print("Mendapatkan daftar pasar untuk dipindai...")
    exchange = ccxt.binance()
    try:
        await exchange.load_markets()
        tickers = await exchange.fetch_tickers()
    finally:
        await exchange.close()

    MIN_VOLUME_USD = 10000000
    CORE_ASSETS = {'BTC/USDT', 'ETH/USDT', 'BNB/USDT', 'SOL/USDT'}
    
    filtered_tickers = {
        s: t for s, t in tickers.items()
        if s.endswith('/USDT') and 'UP/' not in s and 'DOWN/' not in s
        and t.get('quoteVolume', 0) > MIN_VOLUME_USD and t.get('percentage') is not None
    }
    ticker_list = list(filtered_tickers.values())
    top_gainers = sorted(ticker_list, key=lambda x: x['percentage'], reverse=True)[:10]
    top_losers = sorted(ticker_list, key=lambda x: x['percentage'])[:10]
    top_volume = sorted(ticker_list, key=lambda x: x['quoteVolume'], reverse=True)[:10]

    scan_list = {s: "Core Asset" for s in CORE_ASSETS}
    for t in top_gainers: scan_list[t['symbol']] = "Top Gainer"
    for t in top_losers: scan_list[t['symbol']] = "Top Loser"
    for t in top_volume: scan_list[t['symbol']] = "Top Volume"
    
    print(f"Daftar pemindaian final dibuat: {len(scan_list)} aset unik untuk dianalisis.")
    return scan_list

async def process_asset_analysis(symbol, source, exchange):
    try:
        bars = await exchange.fetch_ohlcv(symbol, timeframe='1h', limit=200)
        df = pd.DataFrame(bars, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        
        df.ta.bbands(length=20, append=True)
        df.ta.rsi(length=14, append=True)
        df.ta.macd(fast=12, slow=26, append=True)
        df.ta.atr(length=14, append=True)

        required_cols = ['RSI_14', 'MACD_12_26_9', 'MACDs_12_26_9', 'BBL_20_2.0', 'BBU_20_2.0', 'ATRr_14']
        if any(col not in df.columns for col in required_cols) or df[required_cols].iloc[-1].isnull().any():
            print(f"🟡 INFO: Melewati {symbol} karena data indikator tidak lengkap atau buruk.")
            return

        tech_score = get_technical_score(df)
        chaos_score = get_chaos_score(df)
        sentiment_score = get_sentiment_score(symbol)

        final_score = (tech_score * 0.70) + (sentiment_score * 0.15) + (chaos_score * 0.15)
        
        CONFIDENCE_THRESHOLD = 0.40
        
        print(f"[{symbol:<12}] Skor: {final_score:.2f} (T:{tech_score:.2f}, S:{sentiment_score:.2f}, C:{chaos_score:.2f}) | Source: {source}")

        if final_score >= CONFIDENCE_THRESHOLD or final_score <= -CONFIDENCE_THRESHOLD:
            last_close = df.iloc[-1]['close']
            last_atr_percent = df.iloc[-1]['ATRr_14']
            
            sl_multiplier = 2.0
            tp_multiplier = 3.5
            
            if final_score > 0:
                side = "BUY"
                stop_loss = last_close * (1 - (last_atr_percent / 100) * sl_multiplier)
                take_profit = last_close * (1 + (last_atr_percent / 100) * tp_multiplier)
            else:
                side = "SELL"
                stop_loss = last_close * (1 + (last_atr_percent / 100) * sl_multiplier)
                take_profit = last_close * (1 - (last_atr_percent / 100) * tp_multiplier)
            
            prec = (await exchange.market(symbol))['precision']['price']
            
            await send_cornix_signal({
                "symbol": symbol, "side": side, "entry": f"{last_close:.{prec}f}", "sl": f"{stop_loss:.{prec}f}", "tp1": f"{take_profit:.{prec}f}",
                "confidence": final_score, "source": source, 
                "tech_score": tech_score, "sent_score": sentiment_score, "chaos_score": chaos_score
            })

    except Exception:
        # traceback.print_exc()
        pass

async def async_main_logic():
    print("Memulai GUPF Brain v4.2 - The Thrifty Engine...")
    scan_list = await get_scan_list()
    
    exchange = ccxt.binance()
    try:
        tasks = [process_asset_analysis(symbol, source, exchange) for symbol, source in scan_list.items()]
        await asyncio.gather(*tasks)
    finally:
        await exchange.close()

    print("GUPF Brain v4.2 selesai menjalankan siklus pemindaian.")
    return {'statusCode': 200, 'body': json.dumps('Siklus pemindaian selesai.')}

def handler(event, context):
    return asyncio.run(async_main_logic())
