# gupf_brain_aws.py - VERSI 4.0 (The Debugger)

import os
import ccxt.async_support as ccxt
import pandas as pd
import pandas_ta as ta
import telegram
import asyncio
import json
import requests
import traceback

# --- KONFIGURASI ---
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHANNEL_ID = os.environ.get("TELEGRAM_CHANNEL_ID")
NEWS_API_KEY = os.environ.get("NEWS_API_KEY")
CONFIDENCE_THRESHOLD = 0.45 # Kita pertahankan ambang batas yang telah disesuaikan

# --- FUNGSI SKORING (Dengan Debugging & Peningkatan) ---

def get_technical_score(df: pd.DataFrame) -> float:
    """
    (DARI V3.5) Menghitung skor teknikal dengan sistem poin kumulatif.
    """
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
        if prev_macd_line is not None and prev_signal_line is not None and macd_line is not None and signal_line is not None:
            if prev_macd_line < prev_signal_line and macd_line > signal_line: score += 0.35
            elif prev_macd_line > prev_signal_line and macd_line < signal_line: score -= 0.35

        lower_band = last_row.get('BBL_20_2.0')
        if lower_band is not None and last_row['close'] < lower_band: score += 0.35

        if 65 <= rsi < 70: score -= 0.15
        elif rsi >= 70: score -= 0.30

        upper_band = last_row.get('BBU_20_2.0')
        if upper_band is not None and last_row['close'] > upper_band: score -= 0.35
        
        return max(min(score, 1.0), -1.0)
    except Exception:
        return 0.0

def get_sentiment_score(symbol: str) -> float:
    """
    (BARU DENGAN DEBUGGING) Mengukur sentimen dari NewsAPI.
    """
    print(f"[{symbol}] Mencoba mendapatkan skor sentimen...")
    if not NEWS_API_KEY:
        print(f"[{symbol}] 🔴 GAGAL: NEWS_API_KEY tidak ditemukan di environment.")
        return 0.0
        
    try:
        search_term = symbol.split('/')[0]
        url = (f"https://newsapi.org/v2/everything?q={search_term}&sortBy=publishedAt&language=en&apiKey={NEWS_API_KEY}")
        
        # Sembunyikan API Key di log untuk keamanan
        print(f"[{symbol}] Menghubungi URL: {url.replace(NEWS_API_KEY, '***REDACTED***')}")
        response = requests.get(url, timeout=15) # Timeout dinaikkan sedikit untuk Lambda
        response.raise_for_status() 

        data = response.json()
        articles = data.get('articles', [])
        
        if not articles:
            print(f"[{symbol}] 🟡 INFO: Panggilan NewsAPI berhasil tetapi tidak ada artikel ditemukan.")
            return 0.0

        score = 0
        positive_keywords = ['bullish', 'upgrade', 'rally', 'partnership', 'launch', 'gains', 'profit', 'surges']
        negative_keywords = ['bearish', 'downgrade', 'crash', 'risk', 'loss', 'hack', 'investigation', 'lawsuit']

        for article in articles[:5]:
            title = article.get('title', '').lower()
            if any(word in title for word in positive_keywords): score += 1
            if any(word in title for word in negative_keywords): score -= 1
        
        final_score = score / 5.0
        print(f"[{symbol}] ✅ SUKSES: Skor sentimen adalah {final_score}")
        return final_score

    except requests.exceptions.HTTPError as e:
        print(f"[{symbol}] 🔴 GAGAL: HTTP Error saat menghubungi NewsAPI. Status: {e.response.status_code}, Body: {e.response.text}")
        return 0.0
    except Exception as e:
        print(f"[{symbol}] 🔴 GAGAL: Terjadi error umum di get_sentiment_score: {type(e).__name__} - {e}")
        return 0.0

def get_chaos_score(df: pd.DataFrame) -> float:
    try:
        if 'ATRr_14' not in df.columns or len(df) < 50: return 0.0
        last_atr = df.iloc[-1]['ATRr_14']
        avg_atr = df['ATRr_14'].tail(50).mean()
        if pd.isna(last_atr) or avg_atr == 0: return 0.0
        if last_atr > avg_atr * 1.8: return -0.3 
        if last_atr < avg_atr * 0.7: return -0.2
        return 0.1
    except Exception:
        return 0.0

async def send_cornix_signal(signal_data):
    bot = telegram.Bot(token=TELEGRAM_BOT_TOKEN)
    symbol_plain = signal_data['symbol'].replace('/', '')
    message = f"""
⚡ GUPF v4.0 Signal ⚡
Coin: #{symbol_plain}
Signal: {signal_data['side']}

Entry: {signal_data['entry']:.8f}
Take-Profit 1: {signal_data['tp1']:.8f}
Stop-Loss: {signal_data['sl']:.8f}

Confidence: {signal_data['confidence']:.2f} (T:{signal_data['tech_score']:.2f}, S:{signal_data['sent_score']:.2f}, C:{signal_data['chaos_score']:.2f})
Source: {signal_data['source']}
"""
    await bot.send_message(chat_id=TELEGRAM_CHANNEL_ID, text=message)
    print(f"✅ [{signal_data['symbol']}] Sinyal {signal_data['side']} berhasil dikirim ke Telegram.")

async def get_scan_list():
    print("Mendapatkan daftar pasar untuk dipindai...")
    exchange = ccxt.binance()
    core_assets = {'BTC/USDT': 'Core Asset', 'ETH/USDT': 'Core Asset', 'BNB/USDT': 'Core Asset', 'SOL/USDT': 'Core Asset'}
    scan_list = core_assets.copy()
    
    try:
        await exchange.load_markets()
        tickers = await exchange.fetch_tickers()
        
        MIN_VOLUME_USD = 2000000
        filtered_tickers = {
            s: t for s, t in tickers.items()
            if s.endswith('/USDT') and 'UP/' not in s and 'DOWN/' not in s
            and t.get('quoteVolume', 0) > MIN_VOLUME_USD and t.get('percentage') is not None
        }
        
        if not filtered_tickers:
            print("Peringatan: Gagal mendapatkan data ticker yang difilter, hanya menggunakan Core Assets.")
            return core_assets
        
        ticker_list = list(filtered_tickers.values())
        top_gainers = sorted(ticker_list, key=lambda x: x['percentage'], reverse=True)[:10]
        top_losers = sorted(ticker_list, key=lambda x: x['percentage'])[:10]
        top_volume = sorted(ticker_list, key=lambda x: x['quoteVolume'], reverse=True)[:10]

        for t in top_gainers: scan_list[t['symbol']] = "Top Gainer"
        for t in top_losers: scan_list[t['symbol']] = "Top Loser"
        for t in top_volume: scan_list[t['symbol']] = "Top Volume"
        
        print(f"Daftar pemindaian final dibuat: {len(scan_list)} aset unik untuk dianalisis.")
        
    except Exception as e:
        print(f"Error saat membuat daftar pindaian: {e}. Hanya menggunakan Core Assets.")
    finally:
        await exchange.close()
        
    return scan_list

async def process_asset_analysis(symbol, source, exchange):
    try:
        bars = await exchange.fetch_ohlcv(symbol, timeframe='1h', limit=200)
        if len(bars) < 50:
            print(f"[{symbol}] 🟡 INFO: Data tidak cukup ({len(bars)} bar), dilewati.")
            return

        df = pd.DataFrame(bars, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        
        df.ta.bbands(length=20, append=True)
        df.ta.rsi(length=14, append=True)
        df.ta.macd(fast=12, slow=26, append=True)
        df.ta.atr(length=14, append=True)

        required_cols = ['BBL_20_2.0', 'BBU_20_2.0', 'RSI_14', 'MACD_12_26_9', 'MACDs_12_26_9', 'ATRr_14']
        if any(col not in df.columns for col in required_cols) or df[required_cols].iloc[-1].isnull().any():
            print(f"[{symbol}] 🟡 INFO: Gagal menghitung salah satu indikator kunci (kemungkinan data buruk), dilewati.")
            return

        tech_score = get_technical_score(df)
        chaos_score = get_chaos_score(df)
        sentiment_score = get_sentiment_score(symbol)

        final_score = (tech_score * 0.55) + (sentiment_score * 0.30) + (chaos_score * 0.15)
        
        print(f"[{symbol:<12}] Skor: {final_score:.2f} (T:{tech_score:.2f}, S:{sentiment_score:.2f}, C:{chaos_score:.2f}) | Source: {source}")

        if final_score >= CONFIDENCE_THRESHOLD or final_score <= -CONFIDENCE_THRESHOLD:
            last_close = df.iloc[-1]['close']
            atr_val = df.iloc[-1]['ATR_14']
            side = "BUY" if final_score > 0 else "SELL"
            
            if side == "BUY":
                stop_loss = last_close - (atr_val * 2.0)
                take_profit = last_close + (atr_val * 3.5)
            else: # SELL
                stop_loss = last_close + (atr_val * 2.0)
                take_profit = last_close - (atr_val * 3.5)

            await send_cornix_signal({
                "symbol": symbol, "side": side, "entry": last_close, "sl": stop_loss, "tp1": take_profit,
                "confidence": final_score, "tech_score": tech_score, "sent_score": sentiment_score, "chaos_score": chaos_score,
                "source": source
            })

    except ccxt.NetworkError as e:
        print(f"[{symbol}] 🟡 INFO: Network error saat mengambil data OHLCV: {e}, dilewati.")
    except Exception as e:
        print(f"[{symbol}] 🔴 ERROR FATAL: Terjadi error tak terduga dalam process_asset_analysis: {e}")
        traceback.print_exc()

async def async_main_logic():
    print("Memulai GUPF Brain v4.0 - The Debugger...")
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
    return {'statusCode': 200, 'body': json.dumps('Siklus pemindaian Debugger selesai.')}

def handler(event, context):
    return asyncio.run(async_main_logic())
