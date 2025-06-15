# gupf_brain_aws.py - VERSI 8.3 (THE MARKET INTELLIGENCE PROTOCOL)
import numpy as np
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
    print("🚀 Memulai GUPF v8.2 Protokol Pemindaian Futures...")
    scan_list = await get_scan_list()
    
    exchange = ccxt.binance({'options': {'defaultType': 'future'}})
    try:
        tasks = [process_futures_asset(symbol, source, exchange) for symbol, source in scan_list.items()]
        await asyncio.gather(*tasks)
    finally:
        await exchange.close()
    print("✅ Protokol Pemindaian Futures Selesai.")

# GANTI FUNGSI analyze_spot_scalp_asset LAMA DENGAN VERSI v6.1 INI

async def analyze_spot_scalp_asset(symbol, exchange):
    """
    ### EVOLUSI KECERDASAN: v8.3 (Market Intelligence) ###
    Menganalisis dan MENGKATEGORIKAN setiap aset, tidak hanya mencari sinyal.
    Mengembalikan dictionary status yang lebih kaya.
    """
    try:
        macro_bars = await exchange.fetch_ohlcv(symbol, timeframe='15m', limit=110)
        bars = await exchange.fetch_ohlcv(symbol, timeframe='5m', limit=100)
        
        if len(macro_bars) < 101 or len(bars) < 15: return None
        
        df_macro = pd.DataFrame(macro_bars, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        df_macro.ta.ema(length=100, append=True)

        df = pd.DataFrame(bars, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        df.ta.rsi(length=14, append=True)
        df.ta.atr(length=14, append=True)

        if df.isnull().values.any() or df_macro.isnull().values.any(): return None
        
        last = df.iloc[-1]; prev = df.iloc[-2]
        last_macro = df_macro.iloc[-1]
        
        current_price = last_macro['close']
        ema_100 = last_macro.get('EMA_100', 0)
        if ema_100 == 0: return None

        upper_neutral_band = ema_100 * 1.0075
        lower_neutral_band = ema_100 * 0.9925

        # MODE 1: Pasar dalam Tren Naik Kuat -> Cari sinyal "Buy The Dip"
        if current_price > upper_neutral_band:
            if last.get('RSI_14', 100) < 40.0:
                # SINYAL DITEMUKAN
                entry_price, last_atr = last['close'], last.get('ATR_14', 0)
                if last_atr == 0: return {'type': 'status', 'status': 'Uptrend', 'symbol': symbol} # Fallback jika ATR 0
                
                return {
                    "type": "signal",
                    "data": {
                        "protocol": "Adaptive_Hybrid_Pro", "symbol": symbol, "side": "BUY",
                        "entry": f"{entry_price:.{exchange.market(symbol)['precision']['price']}f}",
                        "tp1": f"{entry_price + (last_atr * 2.5):.{exchange.market(symbol)['precision']['price']}f}",
                        "sl": f"{entry_price - (last_atr * 1.5):.{exchange.market(symbol)['precision']['price']}f}",
                        "confidence": 100 - last.get('RSI_14'), "source": f"BuyTheDip v8.3 (RSI: {last.get('RSI_14'):.2f})"
                    }
                }
            else: # Tidak ada sinyal, tapi tetap laporkan status
                return {'type': 'status', 'status': 'Uptrend', 'symbol': symbol}

        # MODE 2: Pasar Ranging/Netral -> Cari sinyal "Buy The Breakout"
        elif current_price > lower_neutral_band:
            if prev.get('RSI_14', 100) < 50.0 and last.get('RSI_14', 0) > 50.0:
                # SINYAL DITEMUKAN
                entry_price, last_atr = last['close'], last.get('ATR_14', 0)
                if last_atr == 0: return {'type': 'status', 'status': 'Ranging', 'symbol': symbol} # Fallback jika ATR 0

                return {
                    "type": "signal",
                    "data": {
                        "protocol": "Adaptive_Hybrid_Pro", "symbol": symbol, "side": "BUY",
                        "entry": f"{entry_price:.{exchange.market(symbol)['precision']['price']}f}",
                        "tp1": f"{entry_price + (last_atr * 2.5):.{exchange.market(symbol)['precision']['price']}f}",
                        "sl": f"{entry_price - (last_atr * 1.5):.{exchange.market(symbol)['precision']['price']}f}",
                        "confidence": last.get('RSI_14'), "source": f"BuyTheBreakout v8.3 (RSI: {last.get('RSI_14'):.2f})"
                    }
                }
            else: # Tidak ada sinyal, tapi tetap laporkan status
                return {'type': 'status', 'status': 'Ranging', 'symbol': symbol}
        
        # MODE 3: Pasar dalam Tren Turun -> Laporkan dan Abaikan
        else:
            return {'type': 'status', 'status': 'Downtrend', 'symbol': symbol}

    except Exception as e:
        print(f"  [Analisis v8.3] Gagal menganalisis {symbol}: {type(e).__name__} - {e}")
        return None

async def execute_scalp_fleet_protocol():
    """
    ### EVOLUSI KECERDASAN: v8.3 ###
    Mengumpulkan status dari semua aset, lalu memutuskan antara mengirim
    sinyal trading atau laporan intelijen pasar.
    """
    print("💡 Memulai Protokol Armada Scalp v8.3...")
    
    scan_list = await get_scan_list()
    print(f"  [Armada Scalp] {len(scan_list)} target teridentifikasi untuk dianalisis.")

    trade_signals = []
    market_statuses = {"Uptrend": [], "Ranging": [], "Downtrend": []}
    
    exchange = ccxt.binance({'options': {'defaultType': 'spot'}})
    try:
        await exchange.load_markets()
        
        tasks = [analyze_spot_scalp_asset(symbol, exchange) for symbol in scan_list.keys()]
        results = await asyncio.gather(*tasks)
        
        # Memilah hasil menjadi sinyal atau status
        for res in results:
            if res is None: continue
            if res['type'] == 'signal':
                trade_signals.append(res['data'])
            elif res['type'] == 'status':
                market_statuses[res['status']].append(res['symbol'])
        
        # LOGIKA KEPUTUSAN UTAMA
        if trade_signals:
            print(f"  [Armada Scalp] {len(trade_signals)} sinyal kandidat ditemukan. Memilih yang terbaik...")
            sorted_signals = sorted(trade_signals, key=lambda x: x['confidence'], reverse=True)
            for signal in sorted_signals[:3]: # Mengirim maksimal 3 sinyal terbaik
                await send_cornix_signal(signal)
        else:
            print("  [Armada Scalp] Tidak ada sinyal trading ditemukan. Menyusun Laporan Intelijen...")
            await send_intelligence_report(market_statuses)
            
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
        message = f"💡 GUPF v7.4 Sinyal Spot Scalp 💡\nAset: #{symbol_plain} (SPOT)\nAksi: {signal_data['side']}\n\nEntry: {signal_data['entry']}\nTake-Profit: {signal_data['tp1']} (Tetap 0.8%)\nStop-Loss: {signal_data['sl']} (Tetap 0.4%)\n\nProtokol: Sub-rutin Efisiensi Modal"
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
    
# FUNGSI BARU v8.3
async def send_intelligence_report(statuses):
    """Menyusun dan mengirim laporan intelijen pasar jika tidak ada sinyal."""
    bot = telegram.Bot(token=TELEGRAM_BOT_TOKEN)
    
    uptrend_assets = statuses.get("Uptrend", [])
    ranging_assets = statuses.get("Ranging", [])
    downtrend_assets = statuses.get("Downtrend", [])
    
    total_assets = len(uptrend_assets) + len(ranging_assets) + len(downtrend_assets)
    
    # Membuat daftar aset yang lebih rapi
    def format_asset_list(asset_list):
        if not asset_list: return "None"
        return ", ".join([s.replace('/USDT', '') for s in asset_list])

    report = (
        f"📊 **GUPF Market Intelligence Report - v8.3** 📊\n\n"
        f"Pemindaian {total_assets} aset selesai. Tidak ada sinyal entri dengan probabilitas tinggi yang ditemukan.\n\n"
        f"**Ikhtisar Pasar Saat Ini:**\n"
        f"🟢 **Uptrend (Watching for Dips):** {len(uptrend_assets)}\n`{format_asset_list(uptrend_assets)}`\n\n"
        f"🟡 **Ranging (Watching for Breakouts):** {len(ranging_assets)}\n`{format_asset_list(ranging_assets)}`\n\n"
        f"🔴 **Downtrend (Ignored):** {len(downtrend_assets)}\n`{format_asset_list(downtrend_assets)}`"
    )
    
    await bot.send_message(chat_id=TELEGRAM_CHANNEL_ID, text=report, parse_mode='Markdown')
    print("✅ Laporan Intelijen Pasar terkirim.")
# --- MASTER LAMBDA HANDLER ---
def handler(event, context):
    """
    ### HANDLER FINAL untuk v8.3 ###
    Papan sirkuit utama GUPF, terhubung ke mesin fisika.
    """
    global FUTURES_SIGNAL_FOUND
    FUTURES_SIGNAL_FOUND = False
    
    # Versi untuk logging yang jelas
    version = "8.3"
    print(f"GUPF v({version}) berjalan dalam mode: {GUPF_OPERATING_MODE}")

    if GUPF_OPERATING_MODE == "SCALP_ONLY":
        # Memanggil protokol armada scalp yang benar (yang sekarang berisi logika fisika)
        asyncio.run(execute_scalp_fleet_protocol())
    else:
        # Mode default: pindai futures, jika tidak ada, pindai spot
        asyncio.run(execute_futures_scan_protocol())
        if not FUTURES_SIGNAL_FOUND:
            print("  [Handler] Sinyal futures tidak ditemukan. Beralih ke Protokol Armada Scalp.")
            asyncio.run(execute_scalp_fleet_protocol())
        else:
            print("✅ Sinyal Futures ditemukan. Melewati Protokol Armada Scalp.")
    
    return {'statusCode': 200, 'body': json.dumps(f'Siklus GUPF v{version} Selesai.')}
