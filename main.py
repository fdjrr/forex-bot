import csv
import enum
import json
import os
import pathlib
import random
import time
from datetime import datetime

import MetaTrader5 as mt5
import pandas as pd
import pytz
from dotenv import load_dotenv
from google import genai
from google.genai import types
from google.genai.errors import ClientError
from loguru import logger
from pydantic import BaseModel
from ta.momentum import (
    AwesomeOscillatorIndicator,
    ROCIndicator,
    RSIIndicator,
    StochasticOscillator,
    StochRSIIndicator,
    UltimateOscillator,
    WilliamsRIndicator,
)
from ta.trend import MACD, ADXIndicator, CCIIndicator, EMAIndicator, SMAIndicator
from ta.volume import ForceIndexIndicator

load_dotenv()


class Recommendation(enum.Enum):
    SELL = "SELL"
    BUY = "BUY"
    WNS = "WAIT & SEE"
    HOLD = "HOLD"


class Analysis(BaseModel):
    timeframe: str
    support: float
    resistance: float
    volatility: float
    confidence: float
    take_profit: float
    stop_loss: float
    reason: str
    recommendation: Recommendation


def ai_analysis(contents, config, max_retries=3):
    logger.info("Memulai analisa...")

    api_keys = os.getenv("GEMINI_API_KEY").split(",")
    attempt = 0
    current_api_key = None

    while attempt < max_retries:
        api_key = random.choice(api_keys)

        while api_key == current_api_key:
            api_key = random.choice(api_keys)

        try:
            client = genai.Client(api_key=api_key)

            response = client.models.generate_content(
                model=os.getenv("GEMINI_MODEL"),
                config=config,
                contents=contents,
            )

            logger.info(response.text)

            return response.text
        except ClientError as e:
            logger.error(e)

            attempt += 1

            if attempt < max_retries:
                logger.info(
                    f"Mencoba ulang dengan API key lain. Percobaan {attempt}/{max_retries}"
                )
            else:
                logger.error("Gagal mengambil analisis setelah 3 kali percobaan.")


def is_position_open(order_type: int) -> bool:
    symbol = os.getenv("SYMBOL")

    positions = mt5.positions_get(symbol=symbol)
    if positions:
        for pos in positions:
            logger.debug(pos)
            if pos.type == order_type:
                return True
    return False


def open_trade(order_type: int):
    symbol = os.getenv("SYMBOL")
    lot = os.getenv("LOT")

    if order_type == mt5.ORDER_TYPE_BUY:
        price = mt5.symbol_info(symbol).ask
    else:
        price = mt5.symbol_info(symbol).bid

    point = mt5.symbol_info(symbol).point
    deviation = 20

    request = {
        "action": mt5.TRADE_ACTION_DEAL,
        "symbol": symbol,
        "volume": lot,
        "type": order_type,
        "price": price,
        "sl": price - 100 * point,
        "tp": price + 100 * point,
        "deviation": deviation,
        "magic": 123456,
        "comment": "AI Analysis Trade",
        "type_time": mt5.ORDER_TIME_GTC,
        "type_filling": mt5.ORDER_FILLING_IOC,
    }

    logger.debug(request)

    result = mt5.order_send(request)

    logger.debug(result)

    if result is None:
        logger.error("Gagal mengirim order. Cek koneksi ke MT5 dan simbol.")
        return

    if result.retcode != mt5.TRADE_RETCODE_DONE:
        logger.error(f"Order gagal: {result}")
    else:
        logger.success(f"Order berhasil: {result}")


def main():
    if not mt5.initialize():
        logger.error("Gagal koneksi ke MetaTrader 5:", mt5.last_error())
        return

    symbol = os.getenv("SYMBOL")
    if not mt5.symbol_select(symbol, True):
        logger.error(f"Symbol {symbol} tidak ditemukan atau tidak bisa dipilih.")
        return

    while True:
        timezone = pytz.timezone("Etc/UTC")
        tick = mt5.symbol_info_tick(symbol)
        if tick:
            logger.info(f"Harga Terakhir: {tick.ask}")

        timeframes = [
            [
                "M1",
                mt5.TIMEFRAME_M1,
                datetime(2025, 4, 21, tzinfo=timezone),
                datetime(2025, 4, 21, hour=23, tzinfo=timezone),
            ],
            [
                "M5",
                mt5.TIMEFRAME_M5,
                datetime(2025, 4, 21, tzinfo=timezone),
                datetime(2025, 4, 21, hour=23, tzinfo=timezone),
            ],
            [
                "M15",
                mt5.TIMEFRAME_M15,
                datetime(2025, 4, 21, tzinfo=timezone),
                datetime(2025, 4, 21, hour=23, tzinfo=timezone),
            ],
            [
                "M30",
                mt5.TIMEFRAME_M30,
                datetime(2025, 4, 14, tzinfo=timezone),
                datetime(2025, 4, 21, hour=23, tzinfo=timezone),
            ],
            [
                "H1",
                mt5.TIMEFRAME_H1,
                datetime(2025, 4, 14, tzinfo=timezone),
                datetime(2025, 4, 21, hour=23, tzinfo=timezone),
            ],
        ]

        result_analysis = ""

        for timeframe in timeframes:
            t = timeframe[0]
            tf = timeframe[1]
            utc_from = timeframe[2]
            utc_to = timeframe[3]

            logger.info(
                f"Mengambil data untuk timeframe {t} dari {utc_from} sampai {utc_to}."
            )
            rates = mt5.copy_rates_range(symbol, tf, utc_from, utc_to)

            if rates is None:
                logger.error(f"Tidak dapat mengambil data untuk timeframe {t}.")
                continue

            logger.info(f"Jumlah data: {len(rates)}")

            df = pd.DataFrame(rates)
            df["time"] = pd.to_datetime(df["time"], unit="s")

            # Indikator Moving Average
            df["MA_5"] = SMAIndicator(close=df["close"], window=5).sma_indicator()
            df["EMA_8"] = EMAIndicator(close=df["close"], window=8).ema_indicator()

            # RSI
            df["RSI_6"] = RSIIndicator(close=df["close"], window=6).rsi()
            df["RSI_14"] = RSIIndicator(close=df["close"], window=14).rsi()

            # Stochastic Oscillator
            stoch = StochasticOscillator(
                high=df["high"],
                low=df["low"],
                close=df["close"],
                window=14,
                smooth_window=3,
            )
            df["Stoch_%K"] = stoch.stoch()
            df["Stoch_%D"] = stoch.stoch_signal()

            # Commodity Channel Index (CCI)
            df["CCI_20"] = CCIIndicator(
                high=df["high"], low=df["low"], close=df["close"], window=20
            ).cci()

            # Average Directional Index (ADX)
            adx = ADXIndicator(
                high=df["high"], low=df["low"], close=df["close"], window=14
            )
            df["ADX"] = adx.adx()
            df["ADX_Pos"] = adx.adx_pos()
            df["ADX_Neg"] = adx.adx_neg()

            # Awesome Oscillator
            df["AO"] = AwesomeOscillatorIndicator(
                high=df["high"], low=df["low"]
            ).awesome_oscillator()

            # Momentum (ROC)
            df["Momentum_10"] = ROCIndicator(close=df["close"], window=10).roc()

            # MACD
            macd = MACD(
                close=df["close"], window_slow=26, window_fast=12, window_sign=9
            )
            df["MACD"] = macd.macd()
            df["MACD_Signal"] = macd.macd_signal()
            df["MACD_Hist"] = macd.macd_diff()

            # Stochastic RSI
            stoch_rsi = StochRSIIndicator(
                close=df["close"], window=14, smooth1=3, smooth2=3
            )
            df["Stoch_RSI"] = stoch_rsi.stochrsi()
            df["Stoch_RSI_K"] = stoch_rsi.stochrsi_k()
            df["Stoch_RSI_D"] = stoch_rsi.stochrsi_d()

            # Williams %R
            df["Williams_%R"] = WilliamsRIndicator(
                high=df["high"], low=df["low"], close=df["close"], lbp=14
            ).williams_r()

            # Bull Bear Power (gunakan Force Index sebagai indikator kekuatan pasar)
            df["Bull_Bear_Power"] = ForceIndexIndicator(
                close=df["close"], volume=df["real_volume"]
            ).force_index()

            # Ultimate Oscillator
            df["Ultimate_Osc"] = UltimateOscillator(
                high=df["high"],
                low=df["low"],
                close=df["close"],
                window1=7,
                window2=14,
                window3=28,
            ).ultimate_oscillator()

            logger.info(f"Menyimpan data untuk timeframe {t}.")

            try:
                with open(f"results/{symbol}/TIMEFRAME_{t}.csv", "w") as f:
                    df.to_csv(f, header=f.tell() == 0, index=False)
            except FileNotFoundError as e:
                logger.error(e)
                os.makedirs(f"results/{symbol}", exist_ok=True)
                with open(f"results/{symbol}/TIMEFRAME_{t}.csv", "w") as f:
                    df.to_csv(f, header=f.tell() == 0, index=False)

            logger.info(f"Data telah disimpan untuk timeframe {t}.")

            contents = []

            try:
                filepath = pathlib.Path(f"results/{symbol}/TIMEFRAME_{t}.csv")
                contents.append(
                    types.Part.from_bytes(
                        data=filepath.read_bytes(),
                        mime_type="text/csv",
                    )
                )

                current_price = mt5.symbol_info(symbol).ask

                prompt = f"""
                    Berikut ini adalah data harga untuk simbol {symbol} untuk timeframe {t}:

                    Harga Sekarang : {current_price}

                    Tugas kamu adalah menganalisa data tersebut. Lakukan hal berikut:

                    1. Tentukan area **support** dan **resistance** berdasarkan data yang tersedia.
                    2. Berikan penilaian tingkat **volatilitas** pasar dalam skala 1 sampai 100.
                    3. Berikan tingkat **confidence** (keyakinan) terhadap hasil analisa tersebut dalam skala 1 sampai 100.
                    4. Rekomendasikan apakah sebaiknya **BUY**, **SELL**, **WAIT & SEE**, atau **HOLD** pada kondisi saat ini.
                    5. Jika kamu merekomendasikan **BUY** atau **SELL** tentukan area **TAKE PROFIT** dan **STOP LOSS**. Jika **WAIT & SEE**, atau **HOLD** tidak perlu menentukan area **TAKE PROFIT** dan **STOP LOSS**.
                    6. Analisa harus **logis** dan **berdasarkan data** yang tersedia.
                    7. Analisa harus memberikan profit minimal 40 point.
                    8. Jangan gunakan kata 'disclaimer', peringatan risiko, atau kalimat yang bersifat umum/ambigu atau frasa yang tidak relevan dengan analisa teknikal.
                    9. Jawaban harus spesifik dan berdasarkan data harga yang diberikan.
                    10. Jawaban hanya dalam format yang sesuai dengan skema response_schema yang telah ditentukan.
                """

                config = types.GenerateContentConfig(
                    system_instruction="Kamu adalah seorang trader profesional yang bekerja di perusahaan Google. Gunakan Bahasa Indonesia.",
                    response_mime_type="application/json",
                    response_schema=Analysis,
                )

                contents.append(prompt)

                result_analysis += ai_analysis(contents, config)
            except FileNotFoundError as e:
                logger.error(e)

        current_price = mt5.symbol_info_tick(symbol).ask
        positions = mt5.positions_get(symbol=symbol)

        print(positions)

        contents = f"""
        ${result_analysis}

        Dari analisa yang kamu berikan ini, Rekomendasikan satu timeframe yang menurutmu paling cocok untuk trading. Berikan penjelasan singkat tentang alasan kamu memilih timeframe tersebut. Analisa harus memberikan profit minimal 40 point. Jika tidak ada timeframe yang cocok, berikan alasan singkat kenapa tidak ada timeframe yang cocok. 

        Harga Sekarang : {current_price}

        Transaksi yang sudah dibuka :

        {positions}

        Note :
        1. Jangan gunakan kata 'disclaimer', peringatan risiko, atau kalimat yang bersifat umum/ambigu atau frasa yang tidak relevan dengan analisa teknikal.
        2. Jawaban harus spesifik dan berdasarkan data harga yang diberikan.
        3. Jawaban hanya dalam format yang sesuai dengan skema response_schema yang telah ditentukan.
        """

        config = types.GenerateContentConfig(
            system_instruction="Kamu adalah seorang trader profesional yang bekerja di perusahaan Google. Gunakan Bahasa Indonesia.",
            response_mime_type="application/json",
            response_schema=Analysis,
        )

        ai_analysis(contents, config)

        logger.info("Menunggu 60 detik sebelum memulai kembali.")
        time.sleep(60)


if __name__ == "__main__":
    main()
