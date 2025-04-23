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
from ta.volatility import AverageTrueRange
from ta.volume import ForceIndexIndicator

load_dotenv()

symbol = os.getenv("SYMBOL")
tfs = [mt5.TIMEFRAME_M1, mt5.TIMEFRAME_M5]
lot = os.getenv("LOT")
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


def close_positions():
    positions = mt5.positions_get(symbol=symbol)

    for position in positions:
        price = mt5.symbol_info_tick(symbol).ask

        order = (
            mt5.ORDER_TYPE_BUY
            if position.type == mt5.ORDER_TYPE_SELL
            else mt5.ORDER_TYPE_SELL
        )

        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "position": position.ticket,
            "symbol": symbol,
            "volume": position.volume,
            "type": order,
            "price": price,
            "deviation": deviation,
            "magic": 234000,
            "comment": "",
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": mt5.ORDER_FILLING_IOC,
        }

        mt5.order_send(request)


def open_positions(data):
    price = mt5.symbol_info_tick(symbol).ask
    point = mt5.symbol_info(symbol).point
    order = mt5.ORDER_TYPE_BUY if data["price_action"] == "BUY" else mt5.ORDER_TYPE_SELL

    if order == mt5.ORDER_TYPE_BUY:
        sl = price - 2000 * point
        tp = price + 3000 * point
    else:
        sl = price + 2000 * point
        tp = price - 3000 * point

    for x in range(10):
        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": symbol,
            "volume": lot,
            "type": order,
            "price": price,
            "sl": sl,
            "tp": tp,
            "deviation": deviation,
            "magic": 234000,
            "comment": "",
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": mt5.ORDER_FILLING_IOC,
        }

        result = mt5.order_send(request)

        if result.retcode != mt5.TRADE_RETCODE_DONE:
            logger.error(result.comment)
        else:
            logger.info(f"Order {result.order} berhasil dibuat.")

    time.sleep(2)

    close_positions()


def main():
    if not mt5.initialize():
        logger.error("Gagal koneksi ke MetaTrader 5:", mt5.last_error())
        return

    if not mt5.symbol_select(symbol, True):
        logger.error(f"Symbol {symbol} tidak ditemukan atau tidak bisa dipilih.")
        return

    timezone = pytz.timezone("Etc/UTC")
    utc_from = datetime(2025, 4, 22, tzinfo=timezone)
    utc_to = datetime(2025, 4, 30, tzinfo=timezone)

    while True:
        path = f"results/{symbol}.csv"

        if os.path.exists(path):
            os.remove(path)

        for tf in tfs:
            rates = mt5.copy_rates_range(symbol, tf, utc_from, utc_to)

            df = pd.DataFrame(rates)
            df["time"] = pd.to_datetime(df["time"], unit="s")

            # Moving Average
            df["MA_3"] = SMAIndicator(close=df["close"], window=3).sma_indicator()
            df["EMA_8"] = EMAIndicator(close=df["close"], window=8).ema_indicator()

            # RSI
            df["RSI_3"] = RSIIndicator(close=df["close"], window=3).rsi()

            # Stochastic Oscillator
            stoch = StochasticOscillator(
                high=df["high"],
                low=df["low"],
                close=df["close"],
                window=3,
                smooth_window=2,
            )
            df["Stoch_%K"] = stoch.stoch()
            df["Stoch_%D"] = stoch.stoch_signal()

            df["ATR_5"] = AverageTrueRange(
                high=df["high"], low=df["low"], close=df["close"], window=5
            ).average_true_range()

            # Commodity Channel Index (CCI)
            df["CCI_10"] = CCIIndicator(
                high=df["high"], low=df["low"], close=df["close"], window=10
            ).cci()

            # Average Directional Index (ADX)
            adx = ADXIndicator(
                high=df["high"], low=df["low"], close=df["close"], window=7
            )
            df["ADX"] = adx.adx()
            df["ADX_Pos"] = adx.adx_pos()
            df["ADX_Neg"] = adx.adx_neg()

            # Awesome Oscillator
            df["AO"] = AwesomeOscillatorIndicator(
                high=df["high"], low=df["low"]
            ).awesome_oscillator()

            # Momentum (ROC)
            df["Momentum_5"] = ROCIndicator(close=df["close"], window=5).roc()

            # MACD
            macd = MACD(close=df["close"], window_slow=21, window_fast=8, window_sign=5)
            df["MACD"] = macd.macd()
            df["MACD_Signal"] = macd.macd_signal()
            df["MACD_Hist"] = macd.macd_diff()

            # Stochastic RSI
            stoch_rsi = StochRSIIndicator(
                close=df["close"], window=7, smooth1=2, smooth2=2
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
                window1=3,
                window2=7,
                window3=14,
            ).ultimate_oscillator()

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
                Berikut ini adalah data harga untuk simbol {symbol} untuk timeframe M1 dan M5:

                Indikator yang digunakan :

                df["MA_3"] = SMAIndicator(close=df["close"], window=3).sma_indicator()
                df["EMA_8"] = EMAIndicator(close=df["close"], window=8).ema_indicator()
                df["RSI_3"] = RSIIndicator(close=df["close"], window=3).rsi()
                stoch = StochasticOscillator(
                    high=df["high"],
                    low=df["low"],
                    close=df["close"],
                    window=3,
                    smooth_window=2,
                )
                df["Stoch_%K"] = stoch.stoch()
                df["Stoch_%D"] = stoch.stoch_signal()
                df["ATR_5"] = AverageTrueRange(
                    high=df["high"], low=df["low"], close=df["close"], window=5
                ).average_true_range()
                df["Buy_Signal_ATR"] = (
                    (df["close"] > df["high"].shift(1) + df["ATR_5"].shift(1))
                ).astype(int)
                df["Sell_Signal_ATR"] = (
                    (df["close"] < df["low"].shift(1) - df["ATR_5"].shift(1))
                ).astype(int)
                df["CCI_10"] = CCIIndicator(
                    high=df["high"], low=df["low"], close=df["close"], window=10
                ).cci()
                adx = ADXIndicator(high=df["high"], low=df["low"], close=df["close"], window=7)
                df["ADX"] = adx.adx()
                df["ADX_Pos"] = adx.adx_pos()
                df["ADX_Neg"] = adx.adx_neg()
                df["AO"] = AwesomeOscillatorIndicator(
                    high=df["high"], low=df["low"]
                ).awesome_oscillator()
                df["Momentum_5"] = ROCIndicator(close=df["close"], window=5).roc()
                macd = MACD(close=df["close"], window_slow=21, window_fast=8, window_sign=5)
                df["MACD"] = macd.macd()
                df["MACD_Signal"] = macd.macd_signal()
                df["MACD_Hist"] = macd.macd_diff()
                stoch_rsi = StochRSIIndicator(
                    close=df["close"], window=7, smooth1=2, smooth2=2
                )
                df["Stoch_RSI"] = stoch_rsi.stochrsi()
                df["Stoch_RSI_K"] = stoch_rsi.stochrsi_k()
                df["Stoch_RSI_D"] = stoch_rsi.stochrsi_d()
                df["Williams_%R"] = WilliamsRIndicator(
                    high=df["high"], low=df["low"], close=df["close"], lbp=14
                ).williams_r()
                df["Bull_Bear_Power"] = ForceIndexIndicator(
                    close=df["close"], volume=df["real_volume"], window=2
                ).force_index()
                df["Ultimate_Osc"] = UltimateOscillator(
                    high=df["high"],
                    low=df["low"],
                    close=df["close"],
                    window1=3,
                    window2=7,
                    window3=14,
                ).ultimate_oscillator()

                Tugas kamu adalah menganalisa data tersebut secara mendalam. Lakukan hal berikut:

                1. Tentukan area **support** dan **resistance** berdasarkan data yang tersedia.
                2. Berikan penilaian tingkat **volatilitas** pasar dalam skala 1 sampai 100.
                3. Rekomendasikan apakah sebaiknya **BUY**, **SELL**, **WAIT & SEE**, atau **HOLD** pada kondisi saat ini.
                4. Tentukan area **TAKE PROFIT** dan **STOP LOSS** jika kamu merekomendasikan **BUY** atau **SELL**
                5. Analisa harus **logis** dan **berdasarkan data** yang tersedia.
                6. Berikan tingkat **confidence** (keyakinan) yang kuat terhadap hasil analisa tersebut dalam skala 1 sampai 100.
                7. Jangan gunakan kata 'disclaimer', peringatan risiko, atau kalimat yang bersifat umum/ambigu atau frasa yang tidak relevan dengan analisa teknikal.
                8. Jawaban harus spesifik dan berdasarkan data harga yang diberikan.
                9. Jawaban hanya dalam format yang sesuai dengan skema response_schema yang telah ditentukan.
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

            data = json.loads(response.text)

            if data["confidence"] >= 75 and (
                data["price_action"] == "BUY" or data["price_action"] == "SELL"
            ):

                positions = mt5.positions_get(symbol=symbol)

                if len(positions) < 1:
                    open_positions(data)

        except Exception as e:
            logger.error(e)

        time.sleep(15)


if __name__ == "__main__":
    main()
