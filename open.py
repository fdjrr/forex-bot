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
from ta.volatility import AverageTrueRange, BollingerBands
from ta.volume import ForceIndexIndicator, OnBalanceVolumeIndicator

load_dotenv()

symbol = os.getenv("SYMBOL")
tfs = [mt5.TIMEFRAME_M1]
lot = 0.01
deviation = 20


class PriceAction(enum.Enum):
    SELL = "SELL"
    BUY = "BUY"
    WNS = "WAIT & SEE"
    HOLD = "HOLD"


class Analysis(BaseModel):
    support: float
    resistance: float
    volatility: float
    confidence: float
    take_profit: float
    stop_loss: float
    reason: str
    price_action: PriceAction


def open_positions(data):
    price = mt5.symbol_info_tick(symbol).ask
    order = mt5.ORDER_TYPE_BUY if data["price_action"] == "BUY" else mt5.ORDER_TYPE_SELL

    for x in range(10):
        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": symbol,
            "volume": lot,
            "type": order,
            "price": price,
            "deviation": deviation,
            "magic": 234000,
            "comment": "",
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": mt5.ORDER_FILLING_IOC,
        }

        result = mt5.order_send(request)

        logger.info(result)


def get_last_trade():
    import csv

    csv_file = "trade_log.csv"

    with open(csv_file, mode="r") as file:
        reader = list(csv.reader(file))
        if len(reader) > 1:
            last_row = reader[-1]
            return {
                "order_position": last_row[0],
                "total_position": int(last_row[1]),
                "profit": float(last_row[2]),
                "last_closed_at": last_row[3],
            }
        else:
            return None


def main():
    if not mt5.initialize():
        logger.error("Gagal koneksi ke MetaTrader 5:", mt5.last_error())
        return

    if not mt5.symbol_select(symbol, True):
        logger.error(f"Symbol {symbol} tidak ditemukan atau tidak bisa dipilih.")
        return

    last_analysis = None

    while True:
        now = datetime.now()
        if now.hour >= 6 and now.hour < 22 and now.second == 0:

            last_trade = get_last_trade()

            path = f"results/{symbol}.csv"

            if os.path.exists(path):
                os.remove(path)

            for tf in tfs:
                rates = mt5.copy_rates_from_pos(symbol, tf, 0, 200)
                current_price = mt5.symbol_info_tick(symbol).ask

                df = pd.DataFrame(rates)
                df["time"] = pd.to_datetime(df["time"], unit="s")

                # Exponential Moving Average
                df["EMA_50"] = EMAIndicator(
                    close=df["close"], window=50
                ).ema_indicator()
                df["EMA_200"] = EMAIndicator(
                    close=df["close"], window=200
                ).ema_indicator()

                # RSI
                # df["RSI_3"] = RSIIndicator(close=df["close"], window=3).rsi()

                # Stochastic Oscillator
                # stoch = StochasticOscillator(
                #     high=df["high"],
                #     low=df["low"],
                #     close=df["close"],
                #     window=3,
                #     smooth_window=2,
                # )
                # df["Stoch_%K"] = stoch.stoch()
                # df["Stoch_%D"] = stoch.stoch_signal()

                # Average True Range
                # df["ATR_5"] = AverageTrueRange(
                #     high=df["high"], low=df["low"], close=df["close"], window=5
                # ).average_true_range()

                # Commodity Channel Index (CCI)
                # df["CCI_10"] = CCIIndicator(
                #     high=df["high"], low=df["low"], close=df["close"], window=10
                # ).cci()

                # Average Directional Index (ADX)
                # adx = ADXIndicator(
                #     high=df["high"], low=df["low"], close=df["close"], window=7
                # )
                # df["ADX"] = adx.adx()
                # df["ADX_Pos"] = adx.adx_pos()
                # df["ADX_Neg"] = adx.adx_neg()

                # Awesome Oscillator
                # df["AO"] = AwesomeOscillatorIndicator(
                #     high=df["high"], low=df["low"]
                # ).awesome_oscillator()

                # Momentum (ROC)
                # df["Momentum_5"] = ROCIndicator(close=df["close"], window=5).roc()

                # MACD
                # macd = MACD(
                #     close=df["close"], window_slow=21, window_fast=8, window_sign=5
                # )
                # df["MACD"] = macd.macd()
                # df["MACD_Signal"] = macd.macd_signal()
                # df["MACD_Hist"] = macd.macd_diff()

                # Stochastic RSI
                # stoch_rsi = StochRSIIndicator(
                #     close=df["close"], window=7, smooth1=2, smooth2=2
                # )
                # df["Stoch_RSI"] = stoch_rsi.stochrsi()
                # df["Stoch_RSI_K"] = stoch_rsi.stochrsi_k()
                # df["Stoch_RSI_D"] = stoch_rsi.stochrsi_d()

                # Williams %R
                # df["Williams_%R"] = WilliamsRIndicator(
                #     high=df["high"], low=df["low"], close=df["close"], lbp=14
                # ).williams_r()

                # Bull Bear Power (gunakan Force Index sebagai indikator kekuatan pasar)
                # df["Bull_Bear_Power"] = ForceIndexIndicator(
                #     close=df["close"], volume=df["real_volume"]
                # ).force_index()

                # Ultimate Oscillator
                # df["Ultimate_Osc"] = UltimateOscillator(
                #     high=df["high"],
                #     low=df["low"],
                #     close=df["close"],
                #     window1=3,
                #     window2=7,
                #     window3=14,
                # ).ultimate_oscillator()

                # On Balance Volume
                df["OBV"] = OnBalanceVolumeIndicator(
                    close=df["close"], volume=df["real_volume"]
                ).on_balance_volume()

                # Bollinger Bands
                bb = BollingerBands(close=df["close"], window=20, window_dev=2)
                df["BB_Lower"] = bb.bollinger_lband()
                df["BB_Middle"] = bb.bollinger_mavg()
                df["BB_Upper"] = bb.bollinger_hband()

                with open(path, "a") as fp:
                    fp.write(f"Timeframe : M{tf}\n\n")
                    df.to_csv(fp, index=False)

            try:
                contents = []

                filepath = pathlib.Path(path)
                contents.append(
                    types.Part.from_bytes(
                        data=filepath.read_bytes(),
                        mime_type="text/csv",
                    )
                )

                prompt = f"""
                    Berikut ini adalah data harga untuk simbol {symbol}:

                    Harga sekarang : {current_price}
                    Jam sekarang : {now}

                    Analisa sebelumnya : {last_analysis}

                    Posisi yang dibuka sebelumnya : {last_trade} dan sudah selesai.

                    Indikator yang digunakan antara lain:
                    - EMA 50, EMA 200
                    - On Balance Volume
                    - Bollinger Bands (20,2)

                    Tugas kamu adalah menganalisa data tersebut secara mendalam. Lakukan hal berikut:

                    1. Tentukan area support dan resistance terdekat berdasarkan struktur harga dan volume.
                    2. Hitung tingkat volatilitas pasar (skala 1-100) berdasarkan pergerakan harga dalam periode tersebut.
                    3. Berikan rekomendasi aksi: BUY, SELL, HOLD, atau WAIT & SEE, berdasarkan indikator teknikal.
                    4. Jika memberikan rekomendasi BUY atau SELL, tetapkan level Take Profit dan Stop Loss yang logis dan realistis.
                    5. Analisa harus logis, berbasis data teknikal, dan hindari narasi spekulatif atau ambigu.
                    6. Berikan tingkat confidence (keyakinan) terhadap hasil analisa dalam skala 1 sampai 100.
                    7. Jangan rekomendasikan BUY atau SELL jika confidence < 70 atau sinyal teknikal tidak mendukung.
                    8. Tetap melakukan analisa yang konsisten dari analisa sebelumnya.
                    9. Fokus hanya pada analisa teknikal — tidak perlu memberikan penjelasan tambahan di luar kerangka response_schema.
                """

                config = types.GenerateContentConfig(
                    system_instruction="Kamu adalah seorang trader scalper profesional yang bekerja di perusahaan Google. Gunakan Bahasa Indonesia.",
                    response_mime_type="application/json",
                    response_schema=Analysis,
                )

                contents.append(prompt)

                api_keys = os.getenv("GEMINI_API_KEY").split(",")
                api_key = random.choice(api_keys)

                client = genai.Client(api_key=api_key)

                response = client.models.generate_content(
                    model=os.getenv("GEMINI_MODEL"),
                    config=config,
                    contents=contents,
                )

                logger.info(response.text)

                last_analysis = response.text

                data = json.loads(response.text)

                if data["confidence"] >= 70 and (
                    data["price_action"] == "BUY" or data["price_action"] == "SELL"
                ):

                    positions = mt5.positions_get(symbol=symbol)

                    if len(positions) < 1:
                        open_positions(data)

            except Exception as e:
                logger.error(e)


if __name__ == "__main__":
    main()
