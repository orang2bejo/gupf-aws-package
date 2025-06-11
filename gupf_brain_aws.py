import ccxt
import pandas as pd
import pandas_ta as ta
import telegram
import asyncio # Untuk menangani operasi async dengan telegram-bot

# --- KONFIGURASI (GANTI DENGAN NILAI ANDA) ---
TELEGRAM_BOT_TOKEN = "7390209460:AAGBMDkIrFqfnmMnsQF5URTSufihShqPrYY" # Token bot pengirim Anda
TELEGRAM_CHANNEL_ID = "-1002760009072" # ID Channel Pribadi Anda

# --- LOGIKA GUPF-LITE ---
def analyze_market(symbol='BTC/USDT', timeframe='1h'):
    """
    Fungsi ini adalah inti dari otak.
    Menganalisis pasar dan mengembalikan sinyal jika ada.
    """
    try:
        print(f"Menganalisis {symbol} pada timeframe {timeframe}...")
        
        # 1. Ambil Data Harga
        exchange = ccxt.binance()
        bars = exchange.fetch_ohlcv(symbol, timeframe=timeframe, limit=200)
        df = pd.DataFrame(bars, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')

        # 2. Hitung Indikator (Implementasi Sederhana dari Vektor GUPF)
        # Fractal/Chaos Vector -> Bollinger Bands (mewakili volatility channel/attractor)
        df.ta.bbands(length=20, append=True) # Menghasilkan BBL_20_2.0, BBM_20_2.0, BBU_20_2.0

        # Momentum/Consciousness Vector -> RSI
        df.ta.rsi(length=14, append=True) # Menghasilkan RSI_14

        # 3. Logika Sinyal (Contoh Sederhana: RSI Oversold + Bounce dari Lower Bollinger Band)
        last_row = df.iloc[-2] # Menganalisis candle yang sudah selesai
        current_price = df.iloc[-1]['close']

        signal = None
        if last_row['RSI_14'] < 32 and last_row['close'] < last_row['BBL_20_2.0']:
            print(f"SINYAL DITEMUKAN: {symbol} menunjukkan kondisi Beli.")
            
            # Kalkulasi SL & TP (Implementasi dari Logika GUPF)
            # SL: Di bawah Lower Bollinger Band
            stop_loss = last_row['BBL_20_2.0'] * 0.995 # Sedikit di bawah band
            
            # TP: Target adalah Middle Bollinger Band (Mean Reversion)
            take_profit_1 = last_row['BBM_20_2.0']
            
            # Pastikan risk/reward masuk akal
            risk = current_price - stop_loss
            reward = take_profit_1 - current_price
            if reward > risk * 1.5: # Hanya ambil trade dengan R/R ratio > 1.5
                signal = {
                    "symbol": symbol,
                    "side": "BUY",
                    "entry": current_price,
                    "sl": stop_loss,
                    "tp1": take_profit_1
                }

        return signal

    except Exception as e:
        print(f"Error saat analisis: {e}")
        return None

async def send_cornix_signal(signal_data):
    """
    Memformat dan mengirim sinyal ke Telegram dalam format yang dimengerti Cornix.
    """
    bot = telegram.Bot(token=TELEGRAM_BOT_TOKEN)
    
    symbol_plain = signal_data['symbol'].replace('/', '')
    
    # Format Sinyal Cornix yang Paling Umum
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

    await bot.send_message(chat_id=-1002760009072, text=message)
    print("Sinyal berhasil dikirim ke Telegram untuk Cornix.")


# --- FUNGSI UTAMA UNTUK DIJALANKAN ---
async def main():
    print("Memulai GUPF Brain...")
    # Daftar aset yang ingin dipantau
    assets_to_monitor = ['BTC/USDT', 'ETH/USDT', 'SOL/USDT']
    for asset in assets_to_monitor:
        signal = analyze_market(symbol=asset, timeframe='1h')
        if signal:
            await send_cornix_signal(signal)
        else:
            print(f"Tidak ada sinyal valid untuk {asset} saat ini.")
    print("GUPF Brain selesai menjalankan siklus.")


if __name__ == "__main__":
    asyncio.run(main())