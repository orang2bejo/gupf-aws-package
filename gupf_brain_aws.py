# gupf_brain_aws.py - VERSI 2.0 (Multi-Dimensional Confidence Engine)

import os
import ccxt
import pandas as pd
import pandas_ta as ta
import telegram
import asyncio
import json
import requests
from datetime import datetime, timedelta

# --- KONFIGURASI ---
# Ambil dari environment variables untuk keamanan
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHANNEL_ID = os.environ.get("TELEGRAM_CHANNEL_ID")
NEWS_API_KEY = os.environ.get("NEWS_API_KEY") # <<< Ganti dengan kunci API Anda saat testing lokal

# --- FUNGSI SKORING: INTI KECERDASAN GUPF ---

def get_sentiment_score(symbol: str) -> float:
    """
    Mengambil berita terkait aset, menganalisis judul, dan memberikan skor sentimen.
    Mengembalikan skor antara -1.0 (sangat negatif) hingga +1.0 (sangat positif).
    """
    try:
        # Daftar kata kunci sederhana untuk sentimen
        POSITIVE_KEYWORDS = ['bullish', 'upgrade', 'rally', 'breakthrough', 'gains', 'profit', 'surges', 'optimistic']
        NEGATIVE_KEYWORDS = ['bearish', 'downgrade', 'crash', 'risk', 'loss', 'plunges', 'fears', 'scam', 'hack']

        # Bersihkan simbol untuk pencarian (e.g., 'BTC/USDT' -> 'bitcoin')
        search_term = symbol.split('/')[0].lower()
        if search_term == 'btc': search_term = 'bitcoin'
        if search_term == 'eth': search_term = 'ethereum'

        # Ambil berita dari 2 hari terakhir
        two_days_ago = (datetime.now() - timedelta(days=2)).strftime('%Y-%m-%d')
        url = (f"https://newsapi.org/v2/everything?q={search_term}&from={two_days_ago}"
               f"&sortBy=relevancy&language=en&apiKey={NEWS_API_KEY}")

        response = requests.get(url)
        response.raise_for_status() # Cek jika ada error HTTP
        articles = response.json().get('articles', [])

        if not articles:
            return 0.0 # Tidak ada berita, sentimen netral

        sentiment_score = 0
        for article in articles[:10]: # Analisis 10 berita teratas
            title = article.get('title', '').lower()
            sentiment_score += sum([1 for word in POSITIVE_KEYWORDS if word in title])
            sentiment_score -= sum([1 for word in NEGATIVE_KEYWORDS if word in title])

        # Normalisasi skor berdasarkan jumlah artikel yang dianalisis
        normalized_score = sentiment_score / len(articles[:10])
        print(f"[{symbol}] Skor Sentimen: {normalized_score:.2f} dari {len(articles[:10])} berita.")
        return max(-1.0, min(1.0, normalized_score))

    except Exception as e:
        print(f"Error saat mengambil sentimen untuk {symbol}: {e}")
        return 0.0 # Gagal mengambil berita, anggap netral


def get_technical_score(df: pd.DataFrame) -> float:
    """Menganalisis DataFrame dan mengembalikan skor teknikal dari -1.0 hingga 1.0."""
    score = 0.0
    last_row = df.iloc[-2]

    # 1. Kontribusi dari RSI (Bobot: 0.3)
    rsi = last_row.get('RSI_14', 50)
    if rsi < 32: score += 0.3
    if rsi > 68: score -= 0.3

    # 2. Kontribusi dari Bollinger Bands (Bobot: 0.3)
    if last_row.get('close', 0) < last_row.get('BBL_20_2.0', 0): score += 0.3
    if last_row.get('close', 0) > last_row.get('BBU_20_2.0', 0): score -= 0.3

    # 3. Kontribusi dari MACD Crossover (Bobot: 0.4)
    if last_row.get('MACDh_12_26_9', 0) > 0 and df.iloc[-3].get('MACDh_12_26_9', 0) <= 0:
        score += 0.4 # Crossover bullish
    if last_row.get('MACDh_12_26_9', 0) < 0 and df.iloc[-3].get('MACDh_12_26_9', 0) >= 0:
        score -= 0.4 # Crossover bearish

    return max(-1.0, min(1.0, score))


def get_chaos_score(df: pd.DataFrame) -> float:
    """Mengukur 'kekacauan' pasar (volatilitas) dan memberikan penyesuaian skor."""
    last_atr = df.iloc[-1].get('ATRr_14', 0)
    avg_atr = df['ATRr_14'].tail(50).mean()

    if last_atr > avg_atr * 1.7: return -0.3 # Volatilitas ekstrim, kurangi konfidensi
    if last_atr > avg_atr * 1.3: return -0.1 # Volatilitas tinggi
    if last_atr < avg_atr * 0.7: return -0.1 # Pasar terlalu sepi
    return 0.1 # Volatilitas sehat, tambah sedikit konfidensi


# --- FUNGSI UTAMA & PEMBANTU ---

async def send_cornix_signal(signal_data):
    """Mengirim sinyal yang sudah diformat ke Telegram."""
    bot = telegram.Bot(token=TELEGRAM_BOT_TOKEN)
    symbol_plain = signal_data['symbol'].replace('/', '')
    message = f"""
Client: GUPF-Cloud-Brain v2.0
Coin: #{symbol_plain}
Signal: {signal_data['side']}

Entry: {signal_data['entry']:.4f}
Take-Profit 1: {signal_data['tp1']:.4f}
Stop-Loss: {signal_data['sl']:.4f}

Confidence Score: {signal_data['confidence']:.2f}
(T:{signal_data['tech_score']:.2f}, S:{signal_data['sent_score']:.2f}, C:{signal_data['chaos_score']:.2f})
"""
    await bot.send_message(chat_id=TELEGRAM_CHANNEL_ID, text=message)
    print(f"[{signal_data['symbol']}] Sinyal {signal_data['side']} berhasil dikirim ke Telegram.")


async def process_asset_analysis(symbol='BTC/USDT', timeframe='1h'):
    """Fungsi utama untuk menganalisis satu aset dan mengirim sinyal jika perlu."""
    try:
        print(f"--- Menganalisis {symbol} pada timeframe {timeframe} ---")
        exchange = ccxt.binance()
        bars = exchange.fetch_ohlcv(symbol, timeframe=timeframe, limit=200)
        df = pd.DataFrame(bars, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')

        # Hitung semua indikator yang diperlukan
        df.ta.bbands(length=20, append=True)
        df.ta.rsi(length=14, append=True)
        df.ta.macd(fast=12, slow=26, append=True)
        df.ta.atr(length=14, append=True)

        # 1. Hitung skor dari berbagai dimensi
        tech_score = get_technical_score(df)
        chaos_score = get_chaos_score(df)
        sentiment_score = get_sentiment_score(symbol)

        # 2. Hitung Skor Konfidensi Final (dengan pembobotan)
        # Bobot: Teknisal 60%, Sentimen 25%, Kekacauan (sebagai penyesuai) 15%
        final_score = (tech_score * 0.60) + (sentiment_score * 0.25) + (chaos_score * 0.15)
        print(f"[{symbol}] Skor Dimensi: Teknisal={tech_score:.2f}, Sentimen={sentiment_score:.2f}, Chaos={chaos_score:.2f}")
        print(f"[{symbol}] SKOR KONFIDENSI FINAL: {final_score:.2f}")

        # 3. Buat keputusan berdasarkan ambang batas (threshold)
        CONFIDENCE_THRESHOLD = 0.55

        if final_score > CONFIDENCE_THRESHOLD:
            side = "BUY"
            entry_price = df.iloc[-1]['close']
            stop_loss = entry_price * (1 - df.iloc[-1]['ATRr_14'] / 100 * 1.5)
            take_profit = entry_price * (1 + df.iloc[-1]['ATRr_14'] / 100 * 2.5)
            
            signal_info = {
                "symbol": symbol, "side": side, "entry": entry_price, "sl": stop_loss, "tp1": take_profit,
                "confidence": final_score, "tech_score": tech_score, "sent_score": sentiment_score, "chaos_score": chaos_score
            }
            await send_cornix_signal(signal_info)

        elif final_score < -CONFIDENCE_THRESHOLD:
            # (Logika untuk sinyal SELL bisa ditambahkan di sini dengan cara yang sama)
            print(f"[{symbol}] Sinyal JUAL terdeteksi, namun logika eksekusi belum diimplementasikan.")
        else:
            print(f"[{symbol}] Tidak ada sinyal dengan konfidensi cukup tinggi.")

    except Exception as e:
        print(f"Error fatal saat memproses {symbol}: {e}")

# --- HANDLER LAMBDA ---
async def async_main_logic():
    print("Memulai GUPF Brain v2.0...")
    assets_to_monitor = ['BTC/USDT', 'ETH/USDT', 'SOL/USDT']
    for asset in assets_to_monitor:
        await process_asset_analysis(symbol=asset, timeframe='1h')
        await asyncio.sleep(2) # Jeda kecil agar tidak membebani API
    print("GUPF Brain v2.0 selesai menjalankan siklus.")
    return {'statusCode': 200, 'body': json.dumps('Proses multi-dimensi selesai.')}

def handler(event, context):
    # Menggunakan environment variables untuk konfigurasi di Lambda
    if not all([TELEGRAM_BOT_TOKEN, TELEGRAM_CHANNEL_ID, NEWS_API_KEY]):
        return {'statusCode': 500, 'body': json.dumps('Error: Missing environment variables!')}
    return asyncio.run(async_main_logic())
