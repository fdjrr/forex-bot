import enum
import json
import os
import pathlib
import random
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

import MetaTrader5 as mt5
import pandas as pd
import pytz
from dotenv import load_dotenv
from google import genai
from google.genai import types
from loguru import logger
from pydantic import BaseModel
from ta.momentum import RSIIndicator
from ta.trend import MACD, ADXIndicator, EMAIndicator
from ta.volatility import BollingerBands

load_dotenv()


symbol = os.getenv("SYMBOL")
lot = 0.1
deviation = 20
timeframes = [
    (mt5.TIMEFRAME_M1, 200),
    (mt5.TIMEFRAME_M5, 200),
    (mt5.TIMEFRAME_M15, 200),
    (mt5.TIMEFRAME_M30, 200),
]


class PriceAction(enum.Enum):
    SELL = "SELL"
    BUY = "BUY"
    WNS = "WAIT & SEE"
    HOLD = "HOLD"


class Analysis(BaseModel):
    support: float
    resistance: float
    confidence: int
    take_profit: float
    stop_loss: float
    reason: str
    price_action: PriceAction


def analyze():
    contents = []

    for tf, count in timeframes:
        path = f"results/{symbol}_{tf}_rates.csv"

        filepath = pathlib.Path(path)
        contents.append(
            types.Part.from_bytes(
                data=filepath.read_bytes(),
                mime_type="text/csv",
            )
        )

    prompt = """
        Tugas kamu adalah menganalisa data tersebut secara mendalam dan lakukan hal berikut:

        1. Tentukan area support dan resistance terdekat berdasarkan struktur harga dan volume.
        2. Berikan analisa yang logis, konsisten, berbasis data teknikal, dan hindari narasi spekulatif atau ambigu.
        3. Berikan tingkat confidence (keyakinan) terhadap hasil analisa yang kamu berikan dalam skala 1 sampai 10.
        4. Berikan rekomendasi price action: BUY, SELL, HOLD, atau WAIT & SEE, Jika BUY atau SELL tetapkan level Take Profit dan Stop Loss terbaik.
        5. Jangan rekomendasikan BUY atau SELL jika confidence <= 7.
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

    try:
        response = client.models.generate_content(
            model=os.getenv("GEMINI_MODEL"),
            config=config,
            contents=contents,
        )

        data = json.loads(response.text)

        if data["price_action"] == "BUY" or data["price_action"] == "SELL":

            order = (
                mt5.ORDER_TYPE_BUY
                if data["price_action"] == "BUY"
                else mt5.ORDER_TYPE_SELL
            )

            price = mt5.symbol_info_tick(symbol).ask

            request = {
                "action": mt5.TRADE_ACTION_DEAL,
                "symbol": symbol,
                "volume": lot,
                "type": order,
                "price": price,
                "sl": data["stop_loss"],
                "tp": data["take_profit"],
                "deviation": deviation,
                "magic": 234000,
                "comment": "",
                "type_time": mt5.ORDER_TIME_GTC,
                "type_filling": mt5.ORDER_FILLING_IOC,
            }

            result = mt5.order_send(request)

            logger.info(result)

        logger.info(response.text)
    except Exception as e:
        logger.error(e)


def get_rates(symbol, tf, count=200):
    rates = mt5.copy_rates_from_pos(symbol, tf, 0, count)

    df = pd.DataFrame(rates)
    df["time"] = pd.to_datetime(df["time"], unit="s")

    if tf == mt5.TIMEFRAME_M1 or tf == mt5.TIMEFRAME_M5:
        df["EMA_5"] = EMAIndicator(close=df["close"], window=5).ema_indicator()
        df["EMA_20"] = EMAIndicator(close=df["close"], window=20).ema_indicator()

        df["RSI_7"] = RSIIndicator(close=df["close"], window=7).rsi()
        df["RSI_14"] = RSIIndicator(close=df["close"], window=14).rsi()

        bb = BollingerBands(close=df["close"], window=20, window_dev=2)
        df["BB_Lower"] = bb.bollinger_lband()
        df["BB_Middle"] = bb.bollinger_mavg()
        df["BB_Upper"] = bb.bollinger_hband()
    elif tf == mt5.TIMEFRAME_M15 or tf == mt5.TIMEFRAME_M30:
        macd = MACD(close=df["close"], window_slow=12, window_fast=26, window_sign=9)
        df["MACD_12_26_9"] = macd.macd()
        df["MACD_Signal"] = macd.macd_signal()
        df["MACD_Hist"] = macd.macd_diff()

        df["RSI_14"] = RSIIndicator(close=df["close"], window=14).rsi()

        df["PIVOT"] = (df["high"] + df["low"] + df["close"]) / 3
        df["R1"] = 2 * df["PIVOT"] - df["low"]
        df["S1"] = 2 * df["PIVOT"] - df["high"]

        adx = ADXIndicator(high=df["high"], low=df["low"], close=df["close"], window=14)
        df["ADX_14"] = adx.adx()
        df["ADX_Pos"] = adx.adx_pos()
        df["ADX_Neg"] = adx.adx_neg()
    else:
        logger.error(f"Timeframe {tf} is not supported")
        return

    path = f"results/{symbol}_{tf}_rates.csv"
    df.to_csv(path, index=False)

    logger.info(f"Data saved to {path}")

    return df


def main():
    if not mt5.initialize():
        print("initialize() failed, error code =", mt5.last_error())
        quit()

    while True:
        now = datetime.now()

        if now.second == 0:

            with ThreadPoolExecutor() as executor:
                for tf, count in timeframes:
                    executor.submit(get_rates, symbol, tf, count)

            analyze()


if __name__ == "__main__":
    main()
