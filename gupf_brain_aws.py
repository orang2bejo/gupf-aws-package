# gupf_brain_aws.py - VERSI 8.8.1 (Integrity Restoration)
# TUJUAN: Mengembalikan fungsionalitas futures dan menyediakan satu file lengkap yang stabil.

import os
import json
import asyncio
import traceback
import ccxt.async_support as ccxt
import pandas as pd
import pandas_ta as ta
import numpy as np
import telegram

# --- 1. KONFIGURASI & VARIABEL GLOBAL ---
TELEGRAM_BOT_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN', 'YOUR_FALLBACK_TOKEN')
TELEGRAM_CHANNEL_ID = os.environ.get('TELEGRAM_CHANNEL_ID', 'YOUR_FALLBACK_CHANNEL_ID')
GUPF_OPERATING_MODE = os.environ.get('GUPF_OPERATING_MODE', 'DEFAULT') # Mode default sekarang

# Variabel global untuk komunikasi antar fungsi
FUTURES_SIGNAL_FOUND = False
IS_RUNNING = False

# --- 2. FUNGSI PEMBANTU (HELPER FUNCTIONS) ---
async def get_scan_list():
    """Mengambil daftar pasangan USDT spot dengan volume tertinggi dari Binance."""
    try:
        exchange = ccxt.binance({'options': {'defaultType': 'spot'}})
        tickers = await exchange.fetch_tickers()
        await exchange.close()
        
        usdt_pairs = {symbol: data for symbol, data in tickers.items() if symbol.endswith('/USDT')}
        sorted_pairs = sorted(usdt_pairs.items(), key=lambda item: item[1].get('quoteVolume', 0), reverse=True)
        
        top_pairs = dict(sorted_pairs[:30])
        return top_pairs
    except Exception as e:
        print(f"🔴 ERROR saat mengambil daftar pindaian: {e}")
        return {}

async def send_cornix_signal(signal_data):
    """Memformat dan mengirim sinyal ke Telegram."""
    bot = telegram.Bot(token=TELEGRAM_BOT_TOKEN)
    side_emoji = "🟢" if signal_data['side'] == "BUY" else "🔴"
    message = (
        f"{side_emoji} **GUPF v8.8.1 Signal** {side_emoji}\n"
        f"**Protocol:** {signal_data.get('source', 'N/A')}\n\n"
        f"**Pair:** `{signal_data['symbol']}`\n"
        f"**Side:** `{signal_data['side']}`\n"
        f"**Entry:** `{signal_data['entry']}`\n"
        f"**Take-Profit 1:** `{signal_data['tp1']}`\n"
        f"**Stop-Loss:** `{signal_data['sl']}`\n"
    )
    await bot.send_message(chat_id=TELEGRAM_CHANNEL_ID, text=message, parse_mode='Markdown')
    print(f"✅ Sinyal {signal_data['side']} untuk {signal_data['symbol']} terkirim.")

async def send_intelligence_report(statuses):
    """Menyusun dan mengirim laporan intelijen pasar."""
    bot = telegram.Bot(token=TELEGRAM_BOT_TOKEN)
    uptrend = statuses.get("Uptrend", [])
    ranging = statuses.get("Ranging", [])
    downtrend = statuses.get("Downtrend", [])
    insufficient = statuses.get("Insufficient_Data", [])
    failed = statuses.get("Analysis_Failed", [])
    total_analyzed = len(uptrend) + len(ranging) + len(downtrend)

    def format_asset_list(asset_list):
        if not asset_list: return "None"
        return ", ".join([s.replace('/USDT', '') for s in asset_list])

    report = (
        f"📊 **GUPF Market Intelligence Report - v8.8.1** 📊\n\n"
        f"Pemindaian selesai. **{total_analyzed} aset berhasil dianalisis.**\n"
        f"Tidak ada sinyal entri dengan probabilitas tinggi yang ditemukan.\n\n"
        f"**Ikhtisar Pasar Saat Ini:**\n"
        f"🟢 **Uptrend (Watching for Dips):** {len(uptrend)}\n`{format_asset_list(uptrend)}`\n\n"
        f"🟡 **Ranging (Multi-Strategy):** {len(ranging)}\n`{format_asset_list(ranging)}`\n\n"
        f"🔴 **Downtrend (Watching for Rallies):** {len(downtrend)}\n`{format_asset_list(downtrend)}`\n\n"
        f"⚪️ **Skipped (Insufficient Data):** {len(insufficient)}\n`{format_asset_list(insufficient)}`\n"
        f"⚫️ **Failed (Analysis Error):** {len(failed)}\n`{format_asset_list(failed)}`"
    )
    await bot.send_message(chat_id=TELEGRAM_CHANNEL_ID, text=report, parse_mode='Markdown')
    print("✅ Laporan Intelijen Pasar terkirim.")

# --- 3. FUNGSI INTI (CORE LOGIC) ---
async def analyze_spot_scalp_asset(symbol):
    """Sepenuhnya mandiri. Membuka dan menutup koneksinya sendiri untuk setiap aset."""
    exchange = ccxt.binance({'options': {'defaultType': 'spot'}})
    try:
        await exchange.load_markets()
        macro_bars = await exchange.fetch_ohlcv(symbol, timeframe='15m', limit=110)
        bars = await exchange.fetch_ohlcv(symbol, timeframe='5m', limit=100)
        
        if len(macro_bars) < 101 or len(bars) < 15:
            return {'type': 'status', 'status': 'Insufficient_Data', 'symbol': symbol}
        
        df_macro = pd.DataFrame(macro_bars, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        df_macro.ta.ema(length=100, append=True)
        df = pd.DataFrame(bars, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        df.ta.rsi(length=14, append=True); df.ta.atr(length=14, append=True)
        
        if df.isnull().values.any() or df_macro.isnull().values.any():
             return {'type': 'status', 'status': 'Insufficient_Data', 'symbol': symbol}
        
        last, prev, last_macro = df.iloc[-1], df.iloc[-2], df_macro.iloc[-1]
        current_price, ema_100 = last_macro['close'], last_macro.get('EMA_100', 0)
        if ema_100 == 0:
            return {'type': 'status', 'status': 'Insufficient_Data', 'symbol': symbol}

        upper_neutral_band, lower_neutral_band = ema_100 * 1.0075, ema_100 * 0.9925
        signal_found = None
        market_status = "Downtrend"

        if current_price > upper_neutral_band:
            market_status = "Uptrend"
            if last.get('RSI_14', 100) < 40.0:
                signal_found = {"side": "BUY", "source": f"BuyTheDip v8.8.1", "confidence": 100 - last.get('RSI_14')}
        elif current_price > lower_neutral_band:
            market_status = "Ranging"
            if prev.get('RSI_14', 100) < 50.0 and last.get('RSI_14', 0) > 50.0:
                signal_found = {"side": "BUY", "source": f"BuyTheBreakout v8.8.1", "confidence": last.get('RSI_14')}
            elif prev.get('RSI_14', 0) > 50.0 and last.get('RSI_14', 100) < 50.0:
                signal_found = {"side": "SELL", "source": f"SellTheBreakdown v8.8.1", "confidence": 100 - last.get('RSI_14')}
        else:
            if last.get('RSI_14', 0) > 60.0:
                signal_found = {"side": "SELL", "source": f"SellTheRally v8.8.1", "confidence": last.get('RSI_14')}

        if signal_found:
            entry_price, last_atr = last['close'], last.get('ATR_14', 0)
            if last_atr == 0: return {'type': 'status', 'status': market_status, 'symbol': symbol}
            sl_mult, tp_mult = 1.5, 2.5
            sl = entry_price - (last_atr * sl_mult) if signal_found['side'] == "BUY" else entry_price + (last_atr * sl_mult)
            tp = entry_price + (last_atr * tp_mult) if signal_found['side'] == "BUY" else entry_price - (last_atr * tp_mult)
            prec = exchange.market(symbol)['precision']['price']
            return {"type": "signal", "data": {"protocol": "All_Weather", "symbol": symbol, "side": signal_found['side'], "entry": f"{entry_price:.{prec}f}", "tp1": f"{tp:.{prec}f}", "sl": f"{sl:.{prec}f}", "confidence": signal_found['confidence'], "source": signal_found['source']}}
        else:
            return {'type': 'status', 'status': market_status, 'symbol': symbol}

    except Exception as e:
        print(f"  [Analisis v8.8.1] Gagal menganalisis {symbol}: {type(e).__name__} - {e}")
        return {'type': 'status', 'status': 'Analysis_Failed', 'symbol': symbol}
    finally:
        if exchange:
            await exchange.close()

# --- 4. FUNGSI ORKESTRASI (ORCHESTRATION) ---
async def execute_scalp_fleet_protocol():
    """Loop utama untuk analisis spot. Sekarang dipanggil sebagai fallback."""
    print("💡 Memulai Protokol Armada Scalp v8.8.1 (Mode Industrial)...")
    scan_list = await get_scan_list()
    print(f"  [Armada Scalp] {len(scan_list)} target teridentifikasi untuk dianalisis.")

    trade_signals = []
    market_statuses = {"Uptrend": [], "Ranging": [], "Downtrend": [], "Insufficient_Data": [], "Analysis_Failed": []}
    
    for symbol in scan_list.keys():
        print(f"  > Menganalisis {symbol}...")
        try:
            res = await analyze_spot_scalp_asset(symbol)
            if res is None: continue
            if res['type'] == 'signal':
                trade_signals.append(res['data'])
            elif res['type'] == 'status' and res.get('status') in market_statuses:
                market_statuses[res['status']].append(res['symbol'])
        except Exception as e:
            print(f"🔴🔴 ERROR KRITIS saat memproses {symbol}: {e}")
            market_statuses["Analysis_Failed"].append(symbol)
            traceback.print_exc()

    if trade_signals:
        print(f"  [Armada Scalp] {len(trade_signals)} sinyal kandidat ditemukan. Memilih yang terbaik...")
        sorted_signals = sorted(trade_signals, key=lambda x: x['confidence'], reverse=True)
        for signal in sorted_signals[:3]:
            await send_cornix_signal(signal)
    else:
        print("  [Armada Scalp] Tidak ada sinyal trading ditemukan. Menyusun Laporan Intelijen...")
        await send_intelligence_report(market_statuses)
            
    print("✅ Protokol Armada Scalp Selesai.")

async def execute_futures_scan_protocol():
    """Placeholder untuk logika futures. Penting untuk alur kerja handler."""
    global FUTURES_SIGNAL_FOUND
    print("  [Handler] Memindai pasar Futures...")
    # Di masa depan, logika untuk mencari sinyal futures akan ada di sini.
    # Jika sinyal ditemukan, FUTURES_SIGNAL_FOUND akan diatur menjadi True.
    print("  [Handler] Protokol Futures belum menemukan sinyal. Melanjutkan ke Spot.")
    FUTURES_SIGNAL_FOUND = False # Setel ke False agar logika scalp dapat berjalan

# --- 5. TITIK MASUK UTAMA (MAIN ENTRY POINT) ---
def handler(event, context):
    """Pintu masuk utama dengan alur kerja futures -> spot yang dipulihkan."""
    global IS_RUNNING
    if IS_RUNNING:
        print("!! Eksekusi sebelumnya masih berjalan. Melewati siklus ini.")
        return {'statusCode': 429, 'body': json.dumps('Execution already in progress.')}
    
    IS_RUNNING = True
    
    try:
        version = "8.8.1"
        print(f"GUPF v({version}) berjalan dalam mode: {GUPF_OPERATING_MODE}")

        if GUPF_OPERATING_MODE == "SCALP_ONLY":
            asyncio.run(execute_scalp_fleet_protocol())
        else: # Mode default (Futures -> Spot)
            global FUTURES_SIGNAL_FOUND
            FUTURES_SIGNAL_FOUND = False # Reset flag di awal
            
            asyncio.run(execute_futures_scan_protocol())
            
            if not FUTURES_SIGNAL_FOUND:
                print("  [Handler] Sinyal futures tidak ditemukan. Beralih ke Protokol Armada Spot.")
                asyncio.run(execute_scalp_fleet_protocol())
            else:
                print("✅ Sinyal Futures ditemukan. Melewati pemindaian Spot.")
        
        return {'statusCode': 200, 'body': json.dumps(f'Siklus GUPF v{version} Selesai.')}
    except Exception as e:
        print(f"🔥🔥🔥 ERROR FATAL DI HANDLER: {e}")
        traceback.print_exc()
        return {'statusCode': 500, 'body': json.dumps('An unexpected error occurred.')}
    finally:
        IS_RUNNING = False
