# gupf_brain_aws.py - VERSI 4.0 (The Debugger)

import os
import ccxt.async_support as ccxt
import pandas as pd
import pandas_ta as ta
import telegram
import asyncio
import json
import requests
import traceback # ### BARU ### Untuk logging error yang lebih detail

# --- KONFIGURASI ---
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHANNEL_ID = os.environ.get("TELEGRAM_CHANNEL_ID")
NEWS_API_KEY = os.environ.get("NEWS_API_KEY")

# --- MESIN SKORING (Dengan Perbaikan) ---

def get_technical_score(df: pd.DataFrame) -> float:
    # Versi ini sudah bagus dari v3.5, tidak perlu diubah.
    score = 0.0
    try:
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
            if prev_macd_line < prev_signal_line and macd_line > signal_line:
                score += 0.35

        lower_band = last_row.get('BBL_20_2.0', 0)
        if lower_band > 0 and last_row['close'] < lower_band:
            score += 0.35

        if 65 <= rsi < 70: score -= 0.15
        elif rsi >= 70: score -= 0.30

        if prev_macd_line is not None and prev_signal_line is not None and macd_line is not None and signal_line is not None:
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
    ### BARU ### Versi ini memiliki LOGGING DIAGNOSTIK yang jauh lebih baik.
    Ia akan memberitahu kita MENGAPA sentimen gagal.
    """
    print(f"[{symbol}] Mencoba mengambil skor sentimen...")
    if not NEWS_API_KEY:
        print(f"[{symbol}] 🔴 GAGAL: Variabel NEWS_API_KEY tidak ditemukan.")
        return 0.0

    try:
        POSITIVE_KEYWORDS = ['bullish', 'upgrade', 'rally', 'breakthrough', 'gains', 'profit', 'surges', 'optimistic', 'partnership', 'launch', 'integration']
        NEGATIVE_KEYWORDS = ['bearish', 'downgrade', 'crash', 'risk', 'loss', 'plunges', 'fears', 'scam', 'hack', 'vulnerability', 'investigation', 'lawsuit']
        
        search_term = symbol.split('/')[0].lower()
        if search_term == 'btc': search_term = 'bitcoin'
        if search_term == 'eth': search_term = 'ethereum'
        
        # ### BARU ### Menyembunyikan kunci API dari URL log
        url = (f"https://newsapi.org/v2/everything?q={search_term}&from={(pd.Timestamp.now() - pd.Timedelta(days=2)).strftime('%Y-%m-%d')}"
               f"&sortBy=relevancy&language=en&apiKey=***")
        print(f"[{symbol}] Menghubungi URL: {url}")
        
        response = requests.get(url.replace("***", NEWS_API_KEY), timeout=10)
        response.raise_for_status() # ### BARU ### Akan memunculkan error jika status 4xx atau 5xx

        articles = response.json().get('articles', [])
        if not articles:
            print(f"[{symbol}] 🟡 INFO: Tidak ada artikel berita ditemukan.")
            return 0.0

        score = sum(1 for a in articles[:10] if any(w in a.get('title','').lower() for w in POSITIVE_KEYWORDS))
        score -= sum(1 for a in articles[:10] if any(w in a.get('title','').lower() for w in NEGATIVE_KEYWORDS))
        
        final_score = score / 10.0
        print(f"[{symbol}] ✅ SUKSES: Skor sentimen dihitung: {final_score}")
        return final_score

    except requests.exceptions.Timeout:
        print(f"[{symbol}] 🔴 GAGAL: Panggilan NewsAPI timed out.")
        return 0.0
    except requests.exceptions.HTTPError as e:
        # ### BARU ### Memberi tahu kita jika kunci API salah atau ada masalah server
        print(f"[{symbol}] 🔴 GAGAL: HTTP Error saat memanggil NewsAPI. Status: {e.response.status_code}, Response: {e.response.text}")
        return 0.0
    except Exception as e:
        print(f"[{symbol}] 🔴 GAGAL: Terjadi error tak terduga di get_sentiment_score.")
        traceback.print_exc() # ### BARU ### Mencetak detail error lengkap
        return 0.0

def get_chaos_score(df: pd.DataFrame) -> float:
    # Fungsi ini sudah cukup bagus
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

# --- FUNGSI UTAMA & PEMBANTU ---

async def send_cornix_signal(signal_data):
    # Fungsi ini OK
    bot = telegram.Bot(token=TELEGRAM_BOT_TOKEN)
    symbol_plain = signal_data['symbol'].replace('/', '')
    message = f"""
🚀 GUPF v4.0 Signal 🚀
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
    # Fungsi ini OK
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
        if s.endswith('/USDT') and 'UP/' not in s and 'DOWN/' not in s and 'DOWN/' not in s
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
        
        # Hitung semua indikator
        df.ta.bbands(length=20, append=True)
        df.ta.rsi(length=14, append=True)
        df.ta.macd(fast=12, slow=26, append=True)
        df.ta.atr(length=14, append=True)

        # ### BARU: VALIDASI DATA ###
        # Memeriksa apakah semua kolom yang diperlukan ada dan tidak kosong (NaN)
        required_cols = ['RSI_14', 'MACD_12_26_9', 'MACDs_12_26_9', 'BBL_20_2.0', 'BBU_20_2.0', 'ATRr_14']
        if any(col not in df.columns for col in required_cols) or df[required_cols].iloc[-1].isnull().any():
            print(f"🟡 INFO: Melewati {symbol} karena data indikator tidak lengkap atau buruk.")
            return

        tech_score = get_technical_score(df)
        chaos_score = get_chaos_score(df)
        sentiment_score = get_sentiment_score(symbol)

        final_score = (tech_score * 0.55) + (sentiment_score * 0.30) + (chaos_score * 0.15)
        
        # Turunkan threshold sedikit untuk pengujian awal dengan sentimen yang berfungsi
        CONFIDENCE_THRESHOLD = 0.45 
        
        print(f"[{symbol:<12}] Skor: {final_score:.2f} (T:{tech_score:.2f}, S:{sentiment_score:.2f}, C:{chaos_score:.2f}) | Source: {source}")

        if final_score >= CONFIDENCE_THRESHOLD or final_score <= -CONFIDENCE_THRESHOLD:
            last_close = df.iloc[-1]['close']
            last_atr_percent = df.iloc[-1]['ATRr_14']
            
            sl_multiplier = 2.0
            tp_multiplier = 3.5 # Rasio Risk/Reward yang lebih baik
            
            if final_score > 0:
                side = "BUY"
                stop_loss = last_close * (1 - (last_atr_percent / 100) * sl_multiplier)
                take_profit = last_close * (1 + (last_atr_percent / 100) * tp_multiplier)
            else:
                side = "SELL"
                stop_loss = last_close * (1 + (last_atr_percent / 100) * sl_multiplier)
                take_profit = last_close * (1 - (last_atr_percent / 100) * tp_multiplier)
            
            # Format desimal yang lebih baik
            prec = (await exchange.market(symbol))['precision']['price']
            
            await send_cornix_signal({
                "symbol": symbol, "side": side, "entry": f"{last_close:.{prec}f}", "sl": f"{stop_loss:.{prec}f}", "tp1": f"{take_profit:.{prec}f}",
                "confidence": final_score, "source": source, 
                "tech_score": tech_score, "sent_score": sentiment_score, "chaos_score": chaos_score
            })

    except Exception as e:
        print(f"🔴 GAGAL: Error fatal tak terduga saat memproses {symbol}.")
        traceback.print_exc()

# --- HANDLER LAMBDA (v4.0) ---
async def async_main_logic():
    print("Memulai GUPF Brain v4.0 - The Debugger...") # ### BARU ###
    scan_list = await get_scan_list()
    
    exchange = ccxt.binance()
    try:
        tasks = [process_asset_analysis(symbol, source, exchange) for symbol, source in scan_list.items()]
        await asyncio.gather(*tasks)
    finally:
        await exchange.close()

    print("GUPF Brain v4.0 selesai menjalankan siklus pemindaian.")
    return {'statusCode': 200, 'body': json.dumps('Siklus pemindaian selesai.')}

def handler(event, context):
    return asyncio.run(async_main_logic())
