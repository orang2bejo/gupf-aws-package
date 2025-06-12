# gupf_brain_aws.py - VERSI 3.4 (Resilient Scanner + Core Assets)

import os
import ccxt.async_support as ccxt
import pandas as pd
import pandas_ta as ta
import telegram
import asyncio
import json
import requests
from datetime import datetime, timedelta

# --- KONFIGURASI ---
# ... (Tidak berubah) ...
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHANNEL_ID = os.environ.get("TELEGRAM_CHANNEL_ID")
NEWS_API_KEY = os.environ.get("NEWS_API_KEY")


# --- FUNGSI SKORING ---
# ... (Tidak berubah, tetap sama seperti sebelumnya) ...
def get_sentiment_score(symbol: str) -> float:
    try:
        POSITIVE_KEYWORDS = ['bullish', 'upgrade', 'rally', 'breakthrough', 'gains', 'profit', 'surges', 'optimistic', 'partnership', 'launch', 'integration']
        NEGATIVE_KEYWORDS = ['bearish', 'downgrade', 'crash', 'risk', 'loss', 'plunges', 'fears', 'scam', 'hack', 'vulnerability', 'investigation', 'lawsuit']
        
        search_term = symbol.split('/')[0].lower()
        if search_term == 'btc': search_term = 'bitcoin'
        if search_term == 'eth': search_term = 'ethereum'
        if search_term == 'sol': search_term = 'solana'

        two_days_ago = (datetime.now() - timedelta(days=2)).strftime('%Y-%m-%d')
        url = (f"https://newsapi.org/v2/everything?q={search_term}&from={two_days_ago}"
               f"&sortBy=relevancy&language=en&apiKey={NEWS_API_KEY}")

        response = requests.get(url, timeout=10)
        response.raise_for_status()
        articles = response.json().get('articles', [])

        if not articles: return 0.0

        sentiment_score = 0
        analyzed_titles = 0
        for article in articles[:10]:
            title = article.get('title', '').lower()
            if not title: continue
            analyzed_titles += 1
            sentiment_score += sum([1 for word in POSITIVE_KEYWORDS if word in title])
            sentiment_score -= sum([1 for word in NEGATIVE_KEYWORDS if word in title])

        if analyzed_titles == 0: return 0.0
        
        normalized_score = sentiment_score / analyzed_titles
        return max(-1.0, min(1.0, normalized_score))
    except Exception as e:
        return 0.0

def get_technical_score(df: pd.DataFrame) -> float:
    score = 0.0
    if len(df) < 20: return 0.0 # Butuh data cukup
    last_row = df.iloc[-2]
    
    rsi = last_row.get('RSI_14', 50)
    if rsi < 32: score += 0.3
    if rsi > 68: score -= 0.3

    if last_row.get('close', 0) < last_row.get('BBL_20_2.0', 0): score += 0.3
    if last_row.get('close', 0) > last_row.get('BBU_20_2.0', 0): score -= 0.3
    
    if last_row.get('MACDh_12_26_9', 0) > 0 and df.iloc[-3].get('MACDh_12_26_9', 0) <= 0: score += 0.4
    if last_row.get('MACDh_12_26_9', 0) < 0 and df.iloc[-3].get('MACDh_12_26_9', 0) >= 0: score -= 0.4
    
    return max(-1.0, min(1.0, score))

def get_chaos_score(df: pd.DataFrame) -> float:
    try:
        if 'ATRr_14' not in df.columns or df['ATRr_14'].isnull().all(): return 0.0
        last_atr = df.iloc[-1].get('ATRr_14', 0)
        avg_atr = df['ATRr_14'].tail(50).mean()
        if avg_atr == 0: return 0.0
        
        if last_atr > avg_atr * 1.7: return -0.3
        if last_atr > avg_atr * 1.3: return -0.1
        if last_atr < avg_atr * 0.7: return -0.1
        return 0.1
    except Exception:
        return 0.0


# --- FUNGSI UTAMA & PEMBANTU ---

async def send_cornix_signal(signal_data):
    bot = telegram.Bot(token=TELEGRAM_BOT_TOKEN)
    symbol_plain = signal_data['symbol'].replace('/', '')
    message = f"""
⚡ GUPF v3.4 Resilient Scanner ⚡
Coin: #{symbol_plain}
Signal: {signal_data['side']}

Entry: {signal_data['entry']:.4f}
Take-Profit 1: {signal_data['tp1']:.4f}
Stop-Loss: {signal_data['sl']:.4f}

Confidence: {signal_data['confidence']:.2f} (T:{signal_data['tech_score']:.2f}, S:{signal_data['sent_score']:.2f}, C:{signal_data['chaos_score']:.2f})
Source: {signal_data['source']}
"""
    await bot.send_message(chat_id=TELEGRAM_CHANNEL_ID, text=message)
    print(f"✅ [{signal_data['symbol']}] Sinyal {signal_data['side']} berhasil dikirim ke Telegram.")

async def get_scan_list():
    """Mengambil daftar koin yang menarik DAN memastikan aset inti selalu ada."""
    print("Mendapatkan daftar pasar untuk dipindai...")
    scan_list = {}
    
    try:
        exchange = ccxt.binance()
        await exchange.load_markets()
        tickers = await exchange.fetch_tickers()
        
        # 1. Filter awal: Hanya ambil pasangan USDT yang relevan
        MIN_VOLUME_USD = 1500000
        filtered_tickers = {
            s: t for s, t in tickers.items()
            if s.endswith('/USDT') and 'UP/' not in s and 'DOWN/' not in s
            and t.get('quoteVolume', 0) > MIN_VOLUME_USD and t.get('percentage') is not None
        }
        
        if filtered_tickers:
            ticker_list = list(filtered_tickers.values())
            top_gainers = sorted(ticker_list, key=lambda x: x['percentage'], reverse=True)[:10]
            top_losers = sorted(ticker_list, key=lambda x: x['percentage'])[:10]
            top_volume = sorted(ticker_list, key=lambda x: x['quoteVolume'], reverse=True)[:10]

            for t in top_gainers: scan_list[t['symbol']] = "Top Gainer"
            for t in top_losers: scan_list[t['symbol']] = "Top Loser"
            for t in top_volume: scan_list[t['symbol']] = "Top Volume"
    
    except Exception as e:
        print(f"Gagal mengambil daftar pasar dinamis: {e}. Melanjutkan dengan aset inti saja.")
    
    finally:
        await exchange.close()

    # 2. LOGIKA FAIL-SAFE: Tambahkan/pastikan aset inti SELALU ada di daftar.
    core_assets = {
        'BTC/USDT': 'Core Asset',
        'ETH/USDT': 'Core Asset',
        'SOL/USDT': 'Core Asset',
        'BNB/USDT': 'Core Asset'
    }
    scan_list.update(core_assets) # Ini akan menambahkan atau menimpa entri yang ada
    
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

        tech_score = get_technical_score(df)
        chaos_score = get_chaos_score(df)
        sentiment_score = get_sentiment_score(symbol)

        final_score = (tech_score * 0.55) + (sentiment_score * 0.30) + (chaos_score * 0.15)
        
        CONFIDENCE_THRESHOLD = 0.48
        last_close = df.iloc[-1]['close']
        last_atr_percent = df.iloc[-1]['ATRr_14']
        
        if pd.isna(last_atr_percent) or last_atr_percent == 0: return

        last_atr = last_atr_percent / 100

        print(f"[{symbol:<12}] Skor: {final_score:.2f} (T:{tech_score:.2f}, S:{sentiment_score:.2f}, C:{chaos_score:.2f}) | Source: {source}")

        # === INILAH SATU-SATUNYA PERBAIKAN YANG ANDA BUTUHKAN ===
        if final_score >= CONFIDENCE_THRESHOLD:
            signal_info = {"symbol": symbol, "side": "BUY", "entry": last_close, "sl": last_close * (1 - last_atr * 2.0), "tp1": last_close * (1 + last_atr * 3.0), "confidence": final_score, "source": source, "tech_score": tech_score, "sent_score": sentiment_score, "chaos_score": chaos_score}
            await send_cornix_signal(signal_info)
        elif final_score <= -CONFIDENCE_THRESHOLD:
            signal_info = {"symbol": symbol, "side": "SELL", "entry": last_close, "sl": last_close * (1 + last_atr * 2.0), "tp1": last_close * (1 - last_atr * 3.0), "confidence": final_score, "source": source, "tech_score": tech_score, "sent_score": sentiment_score, "chaos_score": chaos_score}
            await send_cornix_signal(signal_info)

    except Exception as e:
        print(f"Error fatal saat memproses {symbol}: {e}")

# --- HANDLER LAMBDA (VERSI 3.4) ---
async def async_main_logic():
    print("Memulai GUPF Brain v3.4 - Resilient Scanner + Core Assets...")
    scan_list = await get_scan_list()
    
    if not scan_list:
        print("Daftar pemindaian kosong, tidak ada yang dilakukan.")
        return {'statusCode': 200, 'body': json.dumps('Daftar pemindaian kosong.')}
    
    exchange = ccxt.binance()
    try:
        tasks = [process_asset_analysis(symbol, source, exchange) for symbol, source in scan_list.items()]
        await asyncio.gather(*tasks)
    finally:
        await exchange.close()

    print("GUPF Brain v3.4 selesai menjalankan siklus pemindaian.")
    return {'statusCode': 200, 'body': json.dumps('Siklus pemindaian pasar dinamis selesai.')}

def handler(event, context):
    return asyncio.run(async_main_logic())
