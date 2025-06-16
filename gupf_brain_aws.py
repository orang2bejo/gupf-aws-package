# gupf_brain_aws.py - VERSI 9.4 (The Precision Protocol)
# TUJUAN: Memperbaiki kesalahan presisi kritis dan mengeraskan logika ATR.

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
GUPF_OPERATING_MODE = os.environ.get('GUPF_OPERATING_MODE', 'DEFAULT')
FUTURES_SIGNAL_FOUND, IS_RUNNING = False, False

# --- 2. FUNGSI PEMBANTU (HELPER FUNCTIONS) ---

# ### FUNGSI BARU UNTUK MEMPERBAIKI MASALAH PRESISI ###
def get_decimal_places(increment_str):
    """Mengubah kenaikan harga (mis. '0.001') menjadi jumlah desimal (mis. 3)."""
    if '.' in str(increment_str):
        return len(str(increment_str).split('.')[-1].rstrip('0'))
    return 0

async def get_scan_list():
    """Mengambil daftar aset berkualitas tinggi dengan 3 lapis filter."""
    print("  [Elite Protocol] Memulai akuisisi target berkualitas tinggi...")
    try:
        exchange = ccxt.binance({'options': {'defaultType': 'spot'}})
        tickers = await exchange.fetch_tickers()
        await exchange.close()
        stablecoin_bases = {'USDC', 'FDUSD', 'TUSD', 'DAI', 'BUSD', 'USDP', 'EUR', 'GBP', 'USD1'}
        high_quality_pairs = {}
        for symbol, data in tickers.items():
            if not symbol.endswith('/USDT'): continue
            base_currency = symbol.split('/')[0]
            if base_currency in stablecoin_bases: continue
            change_24h, last_price = data.get('percentage'), data.get('last')
            if change_24h is None or last_price is None: continue
            if abs(change_24h) > 1.0 and last_price > 0.01:
                high_quality_pairs[symbol] = data
        sorted_pairs = sorted(high_quality_pairs.items(), key=lambda i: i[1].get('quoteVolume', 0), reverse=True)
        top_pairs = dict(sorted_pairs[:30])
        print(f"  [Elite Protocol] {len(top_pairs)} target elite teridentifikasi.")
        return top_pairs
    except Exception as e:
        print(f"🔴 ERROR saat mengambil daftar elite: {e}")
        return {}

async def send_cornix_signal(signal_data):
    """Memformat dan mengirim sinyal ke Telegram."""
    bot = telegram.Bot(token=TELEGRAM_BOT_TOKEN)
    side_emoji = "🟢" if signal_data['side'] == "BUY" else "🔴"
    message = (
        f"{side_emoji} **GUPF v9.4 Signal** {side_emoji}\n"
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
    uptrend, ranging, downtrend = statuses.get("Uptrend", []), statuses.get("Ranging", []), statuses.get("Downtrend", [])
    insufficient, failed_fetch, failed_analysis = statuses.get("Insufficient_Data", []), statuses.get("Data_Fetch_Failed", []), statuses.get("Analysis_Failed", [])
    total_analyzed = len(uptrend) + len(ranging) + len(downtrend)

    def format_asset_list(asset_list):
        if not asset_list: return "None"
        return ", ".join([s.replace('/USDT', '') for s in asset_list])

    report = (
        f"📊 **GUPF Market Intelligence Report - v9.4** 📊\n\n"
        f"Pemindaian selesai. **{total_analyzed} aset berhasil dianalisis.**\n"
        f"Tidak ada sinyal entri dengan probabilitas tinggi yang ditemukan.\n\n"
        f"**Ikhtisar Pasar Saat Ini:**\n"
        f"🟢 **Uptrend:** {len(uptrend)}\n`{format_asset_list(uptrend)}`\n\n"
        f"🟡 **Ranging:** {len(ranging)}\n`{format_asset_list(ranging)}`\n\n"
        f"🔴 **Downtrend:** {len(downtrend)}\n`{format_asset_list(downtrend)}`\n\n"
        f"⚪️ **Skipped (Insufficient History):** {len(insufficient)}\n`{format_asset_list(insufficient)}`\n"
        f"🔵 **Skipped (Data Fetch Failed):** {len(failed_fetch)}\n`{format_asset_list(failed_fetch)}`\n"
        f"⚫️ **Failed (Analysis Error):** {len(failed_analysis)}\n`{format_asset_list(failed_analysis)}`"
    )
    await bot.send_message(chat_id=TELEGRAM_CHANNEL_ID, text=report, parse_mode='Markdown')
    print("✅ Laporan Intelijen terkirim.")

# --- 3. FUNGSI INTI (CORE LOGIC) ---
async def analyze_spot_scalp_asset(symbol):
    """v9.4: Menggunakan konverter presisi dan benteng pertahanan ATR."""
    exchange = ccxt.binance({'options': {'defaultType': 'spot'}})
    try:
        await exchange.load_markets()
        macro_bars = await exchange.fetch_ohlcv(symbol, timeframe='15m', limit=110)
        bars = await exchange.fetch_ohlcv(symbol, timeframe='5m', limit=100)
        
        if not macro_bars or len(macro_bars) < 51 or not bars or len(bars) < 21:
            return {'type': 'status', 'status': 'Insufficient_Data', 'symbol': symbol}
        
        df_macro = pd.DataFrame(macro_bars, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        df = pd.DataFrame(bars, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])

        try:
            ema_length = min(100, len(df_macro) - 1)
            ema_column_name = f'EMA_{ema_length}'
            df_macro.ta.ema(length=ema_length, append=True, col_names=(ema_column_name,))
            ema_100 = df_macro.iloc[-1].get(ema_column_name, df_macro.iloc[-1]['close'])
        except Exception:
            ema_100 = df_macro.iloc[-1]['close']

        df.ta.rsi(length=14, append=True)
        df.ta.atr(length=14, append=True)
        df.ta.ema(length=12, append=True)

        critical_cols = ['close', 'open', 'high', 'low']
        if df[critical_cols].isnull().values.any() or df_macro[critical_cols].isnull().values.any():
            return {'type': 'status', 'status': 'Insufficient_Data', 'symbol': symbol}

        last, prev, last_macro = df.iloc[-1], df.iloc[-2], df_macro.iloc[-1]
        current_price = last_macro['close']
        
        upper_neutral_band, lower_neutral_band = ema_100 * 1.0075, ema_100 * 0.9925
        signal_found = None
        market_status = "Downtrend"

        if current_price > upper_neutral_band:
            market_status = "Uptrend"
            if last.get('RSI_14', 100) < 40.0:
                signal_found = {"side": "BUY", "source": f"BuyTheDip v9.4", "confidence": 100 - last.get('RSI_14')}
            elif prev.get('close') < prev.get('EMA_12', float('inf')) and last.get('close') > last.get('EMA_12', 0):
                signal_found = {"side": "BUY", "source": f"MomentumContinuation v9.4", "confidence": 60 + (last.get('RSI_14', 50)-50)}
        elif current_price > lower_neutral_band:
            market_status = "Ranging"
            if prev.get('RSI_14', 100) < 50.0 and last.get('RSI_14', 0) > 50.0:
                signal_found = {"side": "BUY", "source": f"BuyTheBreakout v9.4", "confidence": last.get('RSI_14')}
            elif prev.get('RSI_14', 0) > 50.0 and last.get('RSI_14', 100) < 50.0:
                signal_found = {"side": "SELL", "source": f"SellTheBreakdown v9.4", "confidence": 100 - last.get('RSI_14')}
        else:
            if last.get('RSI_14', 0) > 60.0:
                signal_found = {"side": "SELL", "source": f"SellTheRally v9.4", "confidence": last.get('RSI_14')}

        if signal_found:
            entry_price = last['close']
            
            # ### PERBAIKAN BENTENG PERTAHANAN ATR ###
            last_atr = last.get('ATR_14')
            if pd.isna(last_atr) or last_atr <= 0 or last_atr > (entry_price * 0.1): # Jika ATR > 10% harga, tidak wajar
                last_atr = entry_price * 0.015 # Fallback: 1.5% dari harga saat ini
                print(f"  WARN {symbol}: ATR tidak valid. Menggunakan fallback ATR: {last_atr}")
                
            sl_mult, tp_mult = 1.5, 2.5
            sl = entry_price - (last_atr * sl_mult) if signal_found['side'] == "BUY" else entry_price + (last_atr * sl_mult)
            tp = entry_price + (last_atr * tp_mult) if signal_found['side'] == "BUY" else entry_price - (last_atr * tp_mult)
            
            # ### PERBAIKAN KONVERTER PRESISI CERDAS ###
            price_increment = exchange.market(symbol)['precision']['price']
            prec = get_decimal_places(price_increment)
            
            return {
                "type": "signal", 
                "data": {
                    "protocol": "All_Weather", "symbol": symbol, "side": signal_found['side'], 
                    "entry": f"{entry_price:.{prec}f}", "tp1": f"{tp:.{prec}f}", "sl": f"{sl:.{prec}f}", 
                    "confidence": signal_found['confidence'], "source": signal_found['source']
                }
            }
        else:
            return {'type': 'status', 'status': market_status, 'symbol': symbol}

    except Exception as e:
        print(f"  [Analisis v9.4] Gagal menganalisis {symbol}: {type(e).__name__} - {e}")
        traceback.print_exc()
        return {'type': 'status', 'status': 'Analysis_Failed', 'symbol': symbol}
    finally:
        if exchange:
            await exchange.close()

# --- 4. FUNGSI ORKESTRASI (ORCHESTRATION) ---
async def execute_scalp_fleet_protocol():
    """Loop utama untuk analisis spot."""
    print("💡 Memulai Protokol Armada Spot v9.4 (Mode Precision)...")
    scan_list = await get_scan_list()
    print(f"  [Armada Spot] {len(scan_list)} target elite akan dianalisis.")
    trade_signals, market_statuses = [], {"Uptrend": [], "Ranging": [], "Downtrend": [], "Insufficient_Data": [], "Data_Fetch_Failed": [], "Analysis_Failed": []}
    
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
        print(f"  [Armada Spot] {len(trade_signals)} sinyal kandidat ditemukan. Memilih yang terbaik...")
        sorted_signals = sorted(trade_signals, key=lambda x: x['confidence'], reverse=True)
        for signal in sorted_signals[:3]:
            await send_cornix_signal(signal)
    else:
        print("  [Armada Spot] Tidak ada sinyal trading ditemukan. Menyusun Laporan Intelijen...")
        await send_intelligence_report(market_statuses)
            
    print("✅ Protokol Armada Spot Selesai.")

async def execute_futures_scan_protocol():
    """Placeholder untuk logika futures."""
    global FUTURES_SIGNAL_FOUND
    print("  [Handler] Memindai pasar Futures...")
    print("  [Handler] Protokol Futures belum menemukan sinyal. Melanjutkan ke Spot.")
    FUTURES_SIGNAL_FOUND = False

# --- 5. TITIK MASUK UTAMA (MAIN ENTRY POINT) ---
def handler(event, context):
    """Pintu masuk utama dengan alur kerja futures -> spot."""
    global IS_RUNNING
    if IS_RUNNING:
        print("!! Eksekusi sebelumnya masih berjalan. Melewati siklus ini.")
        return {'statusCode': 429, 'body': json.dumps('Execution already in progress.')}
    
    IS_RUNNING = True
    try:
        version = "9.4"
        print(f"GUPF v({version}) berjalan dalam mode: {GUPF_OPERATING_MODE}")

        if GUPF_OPERATING_MODE == "SCALP_ONLY":
            asyncio.run(execute_scalp_fleet_protocol())
        else:
            global FUTURES_SIGNAL_FOUND
            FUTURES_SIGNAL_FOUND = False
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
