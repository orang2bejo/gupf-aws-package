# gupf_brain_aws.py - VERSI 5.9 The Scalp Fleet Protocol
import math
import os
import ccxt.async_support as ccxt
import pandas as pd
import pandas_ta as ta
import telegram
import asyncio
import json
import requests
import traceback
from datetime import datetime, timezone, timedelta

# --- GLOBAL STATE & KONFIGURASI ---
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHANNEL_ID = os.environ.get("TELEGRAM_CHANNEL_ID")
NEWS_API_KEY = os.environ.get("NEWS_API_KEY")
GUPF_OPERATING_MODE = os.environ.get("GUPF_OPERATING_MODE", "FUTURES") # BARU: 'FUTURES' atau 'SCALP_ONLY'
FUTURES_SIGNAL_FOUND = False

# Konfigurasi Cache
CACHE_PATH = '/tmp/gupf_sentiment_cache.json'
CACHE_MAX_AGE_HOURS = 6

# --- PROTOKOL DUAL-MODE ---

async def execute_futures_scan_protocol():
    """Protokol Utama Pencari Alpha untuk Pasar Futures."""
    global FUTURES_SIGNAL_FOUND
    print("🚀 Memulai GUPF v5.2 Protokol Pemindaian Futures...")
    scan_list = await get_scan_list()
    
    exchange = ccxt.binance({'options': {'defaultType': 'future'}})
    try:
        tasks = [process_futures_asset(symbol, source, exchange) for symbol, source in scan_list.items()]
        await asyncio.gather(*tasks)
    finally:
        await exchange.close()
    print("✅ Protokol Pemindaian Futures Selesai.")

# GANTI FUNGSI LAMA DENGAN YANG INI
# HAPUS FUNGSI execute_spot_scalp_subroutine YANG LAMA
# DAN GANTI DENGAN DUA FUNGSI BARU INI

async def analyze_spot_scalp_asset(symbol, exchange):
    """
    ### EVOLUSI: v6.0 (VWAP Momentum Protocol) ###
    Menganalisis satu aset spot menggunakan logika EMA 5/12 Crossover + VWAP Filter.
    """
    try:
        # --- Analisis Mikro (1m) ---
        bars = await exchange.fetch_ohlcv(symbol, timeframe='1m', limit=100)
        df = pd.DataFrame(bars, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        
        # ### INDIKATOR BARU v6.0 ###
        df.ta.ema(length=5, append=True)
        df.ta.ema(length=12, append=True)
        df.ta.vwap(length=14, append=True) # VWAP harian

        if df.empty or df.isnull().values.any():
            return None

        last = df.iloc[-1]
        prev = df.iloc[-2]
        
        # --- KONDISI ENTRI BARU (VWAP MOMENTUM) ---
        ema_5 = last.get('EMA_5')
        ema_12 = last.get('EMA_12')
        vwap = last.get('VWAP_14')
        prev_ema_5 = prev.get('EMA_5')
        prev_ema_12 = prev.get('EMA_12')

        # Kondisi 1: Terjadi bullish crossover baru saja
        is_bullish_cross = prev_ema_5 < prev_ema_12 and ema_5 > ema_12
        # Kondisi 2: Harga berada di atas VWAP
        is_above_vwap = last['close'] > vwap
        
        if is_bullish_cross and is_above_vwap:
            entry_price = last['close']
            
            # Kita tetap menggunakan ATR untuk Manajemen Risiko Dinamis
            df.ta.atr(length=14, append=True)
            last_atr = df.iloc[-1].get('ATR_14', 0)
            if last_atr == 0: return None

            stop_loss = entry_price - (last_atr * 1.5)
            take_profit = entry_price + (last_atr * 2.5)
            
            market_info = exchange.market(symbol)
            prec = market_info['precision']['price']
            
            # "Keyakinan" sekarang adalah seberapa jauh harga di atas VWAP
            confidence_score = (last['close'] / vwap) 
            
            return {
                "protocol": "VWAP_Momentum", "symbol": symbol, "side": "BUY",
                "entry": f"{entry_price:.{prec}f}", "tp1": f"{take_profit:.{prec}f}", "sl": f"{stop_loss:.{prec}f}",
                "confidence": confidence_score, 
                "source": "VWAP Momentum v6.0"
            }
        
        return None
    except Exception as e:
        print(f"  [Analisis VWAP] Gagal menganalisis {symbol}: {e}")
        return None

async def execute_scalp_fleet_protocol():
    """
    ### EVOLUSI: v5.9 (Scalp Fleet Protocol) ###
    Memindai banyak aset spot dan mengeksekusi 5 sinyal terbaik.
    """
    print("💡 Memulai Protokol Armada Scalp v5.9...")
    
    # 1. Mendapatkan daftar target yang sama dengan futures
    scan_list = await get_scan_list()
    print(f"  [Armada Scalp] {len(scan_list)} target teridentifikasi untuk dianalisis.")

    candidate_signals = []
    exchange = ccxt.binance({'options': {'defaultType': 'spot'}})
    try:
        await exchange.load_markets()
        
        # 2. Menganalisis semua target secara bersamaan
        tasks = [analyze_spot_scalp_asset(symbol, exchange) for symbol in scan_list.keys()]
        results = await asyncio.gather(*tasks)
        
        # 3. Mengumpulkan kandidat yang valid (bukan None)
        candidate_signals = [res for res in results if res is not None]
        
        if not candidate_signals:
            print("  [Armada Scalp] Tidak ada sinyal scalping yang memenuhi syarat ditemukan di seluruh pasar.")
            return

        # 4. Mengurutkan kandidat berdasarkan skor keyakinan (RSI)
        sorted_signals = sorted(candidate_signals, key=lambda x: x['confidence'], reverse=True)
        print(f"  [Armada Scalp] {len(sorted_signals)} sinyal kandidat ditemukan. Memilih 5 terbaik...")
        
        # 5. Mengeksekusi 5 sinyal teratas
        for signal in sorted_signals[:5]:
            await send_cornix_signal(signal)
            
    except Exception as e:
        print(f"🔴 ERROR dalam Protokol Armada Scalp: {e}")
        traceback.print_exc()
    finally:
        await exchange.close()
    print("✅ Protokol Armada Scalp Selesai.")


# --- (Fungsi inti dan pembantu lainnya TIDAK BERUBAH dari v5.1) ---
# Saya sertakan di sini untuk kelengkapan.
async def process_futures_asset(symbol, source, exchange):
    global FUTURES_SIGNAL_FOUND
    try:
        bars = await exchange.fetch_ohlcv(symbol, timeframe='1h', limit=200)
        df = pd.DataFrame(bars, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        df.ta.bbands(length=20, append=True); df.ta.rsi(length=14, append=True); df.ta.macd(fast=12, slow=26, append=True); df.ta.atr(length=14, append=True)
        required_cols = ['RSI_14', 'MACD_12_26_9', 'MACDs_12_26_9', 'BBL_20_2.0', 'BBU_20_2.0', 'ATRr_14']
        if any(col not in df.columns for col in required_cols) or df[required_cols].iloc[-1].isnull().any(): return
        tech_score = get_technical_score(df)
        chaos_score = get_chaos_score(df)
        sentiment_score = get_sentiment_score(symbol)
        final_score = (tech_score * 0.70) + (sentiment_score * 0.15) + (chaos_score * 0.15)
        CONFIDENCE_THRESHOLD = 0.40
        print(f"[{symbol:<12}] Skor Futures: {final_score:.2f} (T:{tech_score:.2f}, S:{sentiment_score:.2f}, C:{chaos_score:.2f}) | Sumber: {source}")
        if abs(final_score) >= CONFIDENCE_THRESHOLD:
            last_close = df.iloc[-1]['close']; last_atr_percent = df.iloc[-1]['ATRr_14']
            side = "BUY" if final_score > 0 else "SELL"
            sl_factor = -1 if side == "BUY" else 1; tp_factor = 1 if side == "BUY" else -1
            stop_loss = last_close * (1 + (sl_factor * (last_atr_percent / 100) * 2.0))
            take_profit = last_close * (1 + (tp_factor * (last_atr_percent / 100) * 3.5))
            prec = (await exchange.market(symbol))['precision']['price']
            signal_data = {"protocol": "Futures", "symbol": symbol, "side": side, "entry": f"{last_close:.{prec}f}", "sl": f"{stop_loss:.{prec}f}", "tp1": f"{take_profit:.{prec}f}", "confidence": final_score, "source": source, "tech_score": tech_score, "sent_score": sentiment_score, "chaos_score": chaos_score}
            await send_cornix_signal(signal_data)
            FUTURES_SIGNAL_FOUND = True
    except Exception: pass

async def send_cornix_signal(signal_data):
    bot = telegram.Bot(token=TELEGRAM_BOT_TOKEN)
    symbol_plain = signal_data['symbol'].replace('/', '')
    if signal_data['protocol'] == "Futures":
        message = f"🚀 GUPF v5.2 Sinyal Futures 🚀\nCoin: #{symbol_plain}\nSinyal: {signal_data['side']}\n\nEntry: {signal_data['entry']}\nTake-Profit 1: {signal_data['tp1']}\nStop-Loss: {signal_data['sl']}\n\nConfidence: {signal_data['confidence']:.2f} (T:{signal_data['tech_score']:.2f}, S:{signal_data['sent_score']:.2f}, C:{signal_data['chaos_score']:.2f})\nSumber: {signal_data['source']}"
    else:
        message = f"💡 GUPF v5.2 Sinyal Spot Scalp 💡\nAset: #{symbol_plain} (SPOT)\nAksi: {signal_data['side']}\n\nEntry: {signal_data['entry']}\nTake-Profit: {signal_data['tp1']} (Tetap 0.8%)\nStop-Loss: {signal_data['sl']} (Tetap 0.4%)\n\nProtokol: Sub-rutin Efisiensi Modal"
    await bot.send_message(chat_id=TELEGRAM_CHANNEL_ID, text=message)
    print(f"✅ [{signal_data['symbol']}] Sinyal {signal_data['protocol']} terkirim.")

def get_technical_score(df: pd.DataFrame) -> float:
    score = 0.0
    try:
        if len(df) < 2: return 0.0
        last_row, prev_row = df.iloc[-1], df.iloc[-2]
        rsi = last_row.get('RSI_14', 50)
        if 30 <= rsi < 35: score += 0.15
        elif rsi < 30: score += 0.30
        macd, signal, prev_macd, prev_signal = last_row.get('MACD_12_26_9'), last_row.get('MACDs_12_26_9'), prev_row.get('MACD_12_26_9'), prev_row.get('MACDs_12_26_9')
        if all(v is not None for v in [prev_macd, prev_signal, macd, signal]):
            if prev_macd < prev_signal and macd > signal: score += 0.35
        lower_band = last_row.get('BBL_20_2.0', 0)
        if lower_band > 0 and last_row['close'] < lower_band: score += 0.35
        if 65 <= rsi < 70: score -= 0.15
        elif rsi >= 70: score -= 0.30
        if all(v is not None for v in [prev_macd, prev_signal, macd, signal]):
            if prev_macd > prev_signal and macd < signal: score -= 0.35
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
        if (datetime.now(timezone.utc) - timestamp).total_seconds() / 3600 < CACHE_MAX_AGE_HOURS: return cached_data['score']
    if not NEWS_API_KEY: return 0.0
    try:
        search_term = symbol.split('/')[0].lower()
        url = (f"https://newsapi.org/v2/everything?q={search_term}&from={(datetime.now() - timedelta(days=2)).strftime('%Y-%m-%d')}&sortBy=relevancy&language=en&apiKey={NEWS_API_KEY}")
        response = requests.get(url, timeout=10); response.raise_for_status()
        articles = response.json().get('articles', [])
        if not articles: return 0.0
        POSITIVE_KEYWORDS = ['bullish', 'upgrade', 'rally', 'breakthrough', 'gains', 'profit', 'surges', 'optimistic', 'partnership', 'launch', 'integration']
        NEGATIVE_KEYWORDS = ['bearish', 'downgrade', 'crash', 'risk', 'loss', 'plunges', 'fears', 'scam', 'hack', 'vulnerability', 'investigation', 'lawsuit']
        score = sum(1 for a in articles[:10] if any(w in a.get('title','').lower() for w in POSITIVE_KEYWORDS)) - sum(1 for a in articles[:10] if any(w in a.get('title','').lower() for w in NEGATIVE_KEYWORDS))
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
        last_atr, avg_atr = df.iloc[-1]['ATRr_14'], df['ATRr_14'].tail(50).mean()
        if pd.isna(last_atr) or pd.isna(avg_atr) or avg_atr == 0: return 0.0
        if last_atr > avg_atr * 1.8: return -0.3
        if last_atr < avg_atr * 0.7: return -0.2
        return 0.1
    except Exception: return 0.0

async def get_scan_list():
    exchange = ccxt.binance(); await exchange.load_markets()
    tickers = await exchange.fetch_tickers(); await exchange.close()
    MIN_VOL_USD, CORE_ASSETS = 10000000, {'BTC/USDT', 'ETH/USDT', 'BNB/USDT', 'SOL/USDT'}
    valid_tickers = {s: t for s, t in tickers.items() if s.endswith('/USDT') and 'UP/' not in s and 'DOWN/' not in s and t.get('quoteVolume', 0) > MIN_VOL_USD and t.get('percentage') is not None}
    ticker_list = list(valid_tickers.values())
    scan_list = {s: "Core Asset" for s in CORE_ASSETS}
    for t in sorted(ticker_list, key=lambda x: x['percentage'], reverse=True)[:10]: scan_list[t['symbol']] = "Top Gainer"
    for t in sorted(ticker_list, key=lambda x: x['percentage'])[:10]: scan_list[t['symbol']] = "Top Loser"
    for t in sorted(ticker_list, key=lambda x: x['quoteVolume'], reverse=True)[:10]: scan_list[t['symbol']] = "Top Volume"
    return scan_list

# --- MASTER LAMBDA HANDLER ---
def handler(event, context):
    """
    ### PERBAIKAN WAJIB (v5.9.1) ###
    Memperbaiki NameError dengan memanggil nama fungsi yang benar.
    """
    global FUTURES_SIGNAL_FOUND
    FUTURES_SIGNAL_FOUND = False
    
    version = "5.9.1"
    print(f"GUPF v({version}) berjalan dalam mode: {GUPF_OPERATING_MODE}")

    if GUPF_OPERATING_MODE == "SCALP_ONLY":
        # Memanggil nama fungsi yang baru dan benar
        asyncio.run(execute_scalp_fleet_protocol())
    else:
        asyncio.run(execute_futures_scan_protocol())
        if not FUTURES_SIGNAL_FOUND:
            # Memanggil nama fungsi yang baru dan benar
            asyncio.run(execute_scalp_fleet_protocol())
        else:
            print("✅ Sinyal Futures ditemukan. Melewati Protokol Armada Scalp.")
    
    return {'statusCode': 200, 'body': json.dumps(f'Siklus GUPF v{version} Selesai.')}
