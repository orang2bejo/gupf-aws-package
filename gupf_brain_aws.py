# gupf_brain_aws.py - VERSI 4.0 (The DNA Engine)

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
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHANNEL_ID = os.environ.get("TELEGRAM_CHANNEL_ID")
NEWS_API_KEY = os.environ.get("NEWS_API_KEY")
CACHE_PATH = '/tmp/gupf_sentiment_cache.json' # Menggunakan direktori sementara Lambda

# --- FUNGSI SKORING BARU (INTI DNA ENGINE) ---

def get_contrarian_score(df: pd.DataFrame) -> tuple[float, str]:
    """
    Mengukur tesis inti: Whale vs Retail.
    Mengembalikan skor dan tesis DNA.
    """
    score = 0.0
    thesis = "Neutral"
    if len(df) < 21: return 0.0, thesis

    last_row = df.iloc[-2]
    avg_volume = df['volume'].tail(20).mean()
    
    is_high_volume = last_row['volume'] > avg_volume * 2.5
    is_rsi_oversold = last_row.get('RSI_14', 50) < 32
    is_rsi_overbought = last_row.get('RSI_14', 50) > 68

    if is_high_volume and is_rsi_oversold:
        score = 0.9 # Skor tinggi untuk keyakinan akumulasi
        thesis = "Contrarian Buy (Whale Accumulation vs Retail Panic)"
    elif is_high_volume and is_rsi_overbought:
        score = -0.9 # Skor tinggi untuk keyakinan distribusi
        thesis = "Contrarian Sell (Whale Distribution vs Retail FOMO)"
    
    return score, thesis

def get_narrative_score(symbol: str) -> float:
    """Mengukur perubahan sentimen (momentum naratif)."""
    # Baca cache sentimen lama
    try:
        with open(CACHE_PATH, 'r') as f:
            cache = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        cache = {}

    previous_score = cache.get(symbol, 0.0)
    
    # Hitung sentimen saat ini
    current_score = get_current_sentiment(symbol)

    # Hitung momentum dan simpan skor baru ke cache
    narrative_momentum = current_score - previous_score
    cache[symbol] = current_score
    with open(CACHE_PATH, 'w') as f:
        json.dump(cache, f)

    print(f"[{symbol}] Narasi: {previous_score:.2f} -> {current_score:.2f} (Momentum: {narrative_momentum:.2f})")
    return narrative_momentum

def get_current_sentiment(symbol: str) -> float:
    """Hanya mengambil skor sentimen saat ini (versi sederhana dari v3)."""
    try:
        POSITIVE_KEYWORDS = ['bullish', 'upgrade', 'rally', 'breakthrough', 'gains', 'profit', 'surges', 'optimistic', 'partnership', 'launch', 'integration']
        NEGATIVE_KEYWORDS = ['bearish', 'downgrade', 'crash', 'risk', 'loss', 'plunges', 'fears', 'scam', 'hack', 'vulnerability', 'investigation', 'lawsuit']
        
        search_term = symbol.split('/')[0].lower()
        if search_term == 'btc': search_term = 'bitcoin'
        if search_term == 'eth': search_term = 'ethereum'
        
        url = (f"https://newsapi.org/v2/everything?q={search_term}&from={(datetime.now() - timedelta(days=2)).strftime('%Y-%m-%d')}"
               f"&sortBy=relevancy&language=en&apiKey={NEWS_API_KEY}")
        response = requests.get(url, timeout=10)
        articles = response.json().get('articles', [])
        if not articles: return 0.0

        score = sum(1 for a in articles[:10] if any(w in a.get('title','').lower() for w in POSITIVE_KEYWORDS))
        score -= sum(1 for a in articles[:10] if any(w in a.get('title','').lower() for w in NEGATIVE_KEYWORDS))
        
        return score / 10.0
    except Exception:
        return 0.0

def get_chaos_score(df: pd.DataFrame) -> float:
    """Mengukur volatilitas pasar (tidak berubah)."""
    try:
        last_atr = df.iloc[-1]['ATRr_14']
        avg_atr = df['ATRr_14'].tail(50).mean()
        if avg_atr == 0: return 0.0
        if last_atr > avg_atr * 1.8: return -0.3
        if last_atr < avg_atr * 0.7: return -0.2
        return 0.1
    except Exception:
        return 0.0

# --- FUNGSI UTAMA & PEMBANTU ---

async def send_cornix_signal(signal_data):
    bot = telegram.Bot(token=TELEGRAM_BOT_TOKEN)
    symbol_plain = signal_data['symbol'].replace('/', '')
    message = f"""
🧬 GUPF v4.0 DNA Engine Signal 🧬
Coin: #{symbol_plain}
Signal: {signal_data['side']}

Entry: {signal_data['entry']:.5f}
Take-Profit 1: {signal_data['tp1']:.5f}
Stop-Loss: {signal_data['sl']:.5f}

Confidence: {signal_data['confidence']:.2f} (Contrarian:{signal_data['c_score']:.1f}, Narrative:{signal_data['n_score']:.1f}, Chaos:{signal_data['chaos_score']:.1f})
DNA Thesis: {signal_data['thesis']}
Source: {signal_data['source']}
"""
    await bot.send_message(chat_id=TELEGRAM_CHANNEL_ID, text=message)
    print(f"✅ [{signal_data['symbol']}] Sinyal {signal_data['side']} berhasil dikirim ke Telegram.")

async def get_scan_list():
    # ... (Kode get_scan_list dari v3.3 tidak berubah, sudah tangguh) ...
    print("Mendapatkan daftar pasar untuk dipindai...")
    exchange = ccxt.binance()
    try:
        await exchange.load_markets()
        tickers = await exchange.fetch_tickers()
    finally:
        await exchange.close()

    MIN_VOLUME_USD = 1500000
    filtered_tickers = {
        s: t for s, t in tickers.items()
        if s.endswith('/USDT') and 'UP/' not in s and 'DOWN/' not in s
        and t.get('quoteVolume', 0) > MIN_VOLUME_USD and t.get('percentage') is not None
    }
    if not filtered_tickers:
        return {'BTC/USDT': 'Fail-Safe', 'ETH/USDT': 'Fail-Safe', 'SOL/USDT': 'Fail-Safe'}
    
    ticker_list = list(filtered_tickers.values())
    top_gainers = sorted(ticker_list, key=lambda x: x['percentage'], reverse=True)[:10]
    top_losers = sorted(ticker_list, key=lambda x: x['percentage'])[:10]
    top_volume = sorted(ticker_list, key=lambda x: x['quoteVolume'], reverse=True)[:10]

    scan_list = {}
    for t in top_gainers: scan_list[t['symbol']] = "Top Gainer"
    for t in top_losers: scan_list[t['symbol']] = "Top Loser"
    for t in top_volume: scan_list[t['symbol']] = "Top Volume"
    
    print(f"Daftar pemindaian dibuat: {len(scan_list)} aset unik untuk dianalisis.")
    return scan_list

async def process_asset_analysis(symbol, source, exchange):
    try:
        bars = await exchange.fetch_ohlcv(symbol, timeframe='1h', limit=200)
        df = pd.DataFrame(bars, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        df.ta.rsi(length=14, append=True)
        df.ta.atr(length=14, append=True)

        # --- MESIN SKOR DNA ---
        contrarian_score, thesis = get_contrarian_score(df)
        narrative_score = get_narrative_score(symbol)
        chaos_score = get_chaos_score(df)

        # Kalkulasi Skor Final
        # Bobot: Niat Kontrarian adalah pendorong utama (80%), Narasi sebagai pendukung (20%)
        base_score = (contrarian_score * 0.8) + (narrative_score * 0.2)
        # Chaos sebagai pengali/filter
        stability_multiplier = 1.0 + chaos_score 
        final_score = base_score * stability_multiplier
        
        print(f"[{symbol:<12}] Skor DNA: {final_score:.2f} (C:{contrarian_score:.1f}, N:{narrative_score:.2f}, Chaos:{chaos_score:.1f}) | Thesis: {thesis}")

        # --- LOGIKA KEPUTUSAN ---
        CONFIDENCE_THRESHOLD = 0.60
        if (final_score > CONFIDENCE_THRESHOLD and "Buy" in thesis) or (final_score < -CONFIDENCE_THRESHOLD and "Sell" in thesis):
            last_close = df.iloc[-1]['close']
            atr_val = df.iloc[-1]['ATR_14']
            
            if pd.isna(atr_val) or atr_val == 0: return

            if final_score > 0: # Sinyal BUY
                side = "BUY"
                stop_loss = last_close - (atr_val * 1.5)
                take_profit = last_close + (atr_val * 2.5) # R/R > 1.5
            else: # Sinyal SELL
                side = "SELL"
                stop_loss = last_close + (atr_val * 1.5)
                take_profit = last_close - (atr_val * 2.5) # R/R > 1.5

            await send_cornix_signal({
                "symbol": symbol, "side": side, "entry": last_close, "sl": stop_loss, "tp1": take_profit,
                "confidence": final_score, "c_score": contrarian_score, "n_score": narrative_score, "chaos_score": chaos_score,
                "thesis": thesis, "source": source
            })

    except Exception as e:
        print(f"Error fatal saat memproses {symbol}: {e}")

# --- HANDLER LAMBDA (v4.0) ---
async def async_main_logic():
    print("Memulai GUPF Brain v4.0 - The DNA Engine...")
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

    print("GUPF Brain v4.0 selesai menjalankan siklus pemindaian.")
    return {'statusCode': 200, 'body': json.dumps('Siklus pemindaian DNA Engine selesai.')}

def handler(event, context):
    return asyncio.run(async_main_logic())
