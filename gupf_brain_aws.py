# gupf_brain_aws.py - VERSI FINAL DENGAN FIX ASYNC

import ccxt
import pandas as pd
import pandas_ta as ta
import telegram
import asyncio
import json

# --- KONFIGURASI ---
TELEGRAM_BOT_TOKEN = "7390209460:AAGBMDkIrFqfnmMnsQF5URTSufihShqPrYY"
TELEGRAM_CHANNEL_ID = "-1002760009072"

# --- FUNGSI PEMBANTU (Tidak ada perubahan di sini) ---
def analyze_market(symbol='BTC/USDT', timeframe='1h'):
    try:
        print(f"Menganalisis {symbol} pada timeframe {timeframe}...")
        exchange = ccxt.binance()
        bars = exchange.fetch_ohlcv(symbol, timeframe=timeframe, limit=200)
        df = pd.DataFrame(bars, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
        df.ta.bbands(length=20, append=True)
        df.ta.rsi(length=14, append=True)
        last_row = df.iloc[-2]
        current_price = df.iloc[-1]['close']
        signal = None
        if last_row['RSI_14'] < 32 and last_row['close'] < last_row['BBL_20_2.0']:
            print(f"SINYAL DITEMUKAN: {symbol} menunjukkan kondisi Beli.")
            stop_loss = last_row['BBL_20_2.0'] * 0.995
            take_profit_1 = last_row['BBM_20_2.0']
            risk = current_price - stop_loss
            reward = take_profit_1 - current_price
            if reward > risk * 1.5:
                signal = {
                    "symbol": symbol, "side": "BUY", "entry": current_price,
                    "sl": stop_loss, "tp1": take_profit_1
                }
        return signal
    except Exception as e:
        print(f"Error saat analisis: {e}")
        return None

async def send_cornix_signal(signal_data):
    bot = telegram.Bot(token=TELEGRAM_BOT_TOKEN)
    symbol_plain = signal_data['symbol'].replace('/', '')
    message = f"""
Client: GUPF-Cloud-Brain(AWS)
Coin: #{symbol_plain}
Side: {signal_data['side']}

Entry: {signal_data['entry']:.4f}

Take-Profit:
1) {signal_data['tp1']:.4f}

Stop-Loss:
1) {signal_data['sl']:.4f}
"""
    await bot.send_message(chat_id=TELEGRAM_CHANNEL_ID, text=message)
    print("Sinyal berhasil dikirim ke Telegram untuk Cornix.")

# --- FUNGSI ASLI KITA (SEKARANG KITA GANTI NAMANYA) ---
async def async_main_logic():
    print("Memulai GUPF Brain...")
    assets_to_monitor = ['BTC/USDT', 'ETH/USDT', 'SOL/USDT']
    signals_found = 0
    for asset in assets_to_monitor:
        signal = analyze_market(symbol=asset, timeframe='1h')
        if signal:
            await send_cornix_signal(signal)
            signals_found += 1
        else:
            print(f"Tidak ada sinyal valid untuk {asset} saat ini.")
    print("GUPF Brain selesai menjalankan siklus.")
    return {
        'statusCode': 200,
        'body': json.dumps(f'Proses selesai. Ditemukan {signals_found} sinyal.')
    }


# ===================================================================
# --- INI ADALAH "PEMBUNGKUS" HANDLER YANG BARU UNTUK LAMBDA ---
# ===================================================================
def handler(event, context):
    """
    Ini adalah fungsi SINKRON yang akan dipanggil Lambda.
    Tugasnya adalah menjalankan fungsi ASINKRON kita.
    """
    # asyncio.run() akan menjalankan fungsi async_main_logic dan menunggu sampai selesai.
    return asyncio.run(async_main_logic())
