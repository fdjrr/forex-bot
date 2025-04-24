import enum
import json
import os
import pathlib
import random
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

import MetaTrader5 as mt5
import pandas as pd
from dotenv import load_dotenv
from google import genai
from google.genai import types
from loguru import logger
from pydantic import BaseModel
from ta.trend import EMAIndicator
from ta.volatility import BollingerBands
from ta.volume import OnBalanceVolumeIndicator

load_dotenv()

symbol = os.getenv("SYMBOL")
tfs = [
    (mt5.TIMEFRAME_M1, 200),
    (mt5.TIMEFRAME_M5, 200),
    (mt5.TIMEFRAME_M15, 200),
    (mt5.TIMEFRAME_M30, 200),
]
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
    confidence: int
    take_profit: float
    stop_loss: float
    reason: str
    price_action: PriceAction


def get_rates(symbol, tf, count=200):
    logger.info(f"Fetching {count} {tf} rates for {symbol}")

    rates = mt5.copy_rates_from_pos(symbol, tf, 0, count)

    df = pd.DataFrame(rates)
    df["time"] = pd.to_datetime(df["time"], unit="s")

    # Exponential Moving Average
    df["EMA_50"] = EMAIndicator(close=df["close"], window=50).ema_indicator()
    df["EMA_200"] = EMAIndicator(close=df["close"], window=200).ema_indicator()

    # On Balance Volume
    df["OBV"] = OnBalanceVolumeIndicator(
        close=df["close"], volume=df["real_volume"]
    ).on_balance_volume()

    # Bollinger Bands
    bb = BollingerBands(close=df["close"], window=20, window_dev=2)
    df["BB_Lower"] = bb.bollinger_lband()
    df["BB_Middle"] = bb.bollinger_mavg()
    df["BB_Upper"] = bb.bollinger_hband()

    path = f"results/{symbol}_{tf}_rates.csv"
    df.to_csv(path, index=False)

    logger.info(f"Data saved to {path}")

    return df


def open_position(order):
    logger.info(f"Opening position for {symbol}")

    price = mt5.symbol_info_tick(symbol).ask

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


def analyze():
    logger.info(f"Analyzing {symbol}")

    contents = []

    for tf, count in tfs:
        path = f"results/{symbol}_{tf}_rates.csv"

        filepath = pathlib.Path(path)
        contents.append(
            types.Part.from_bytes(
                data=filepath.read_bytes(),
                mime_type="text/csv",
            )
        )

    prompt = f"""
        Berikut ini adalah data harga untuk simbol {symbol}:

        Indikator yang digunakan antara lain:
        - EMA 50, EMA 200
        - On Balance Volume
        - Bollinger Bands (20,2)

        Tugas kamu adalah menganalisa data tersebut secara mendalam. Lakukan hal berikut:

        1. Tentukan area support dan resistance terdekat berdasarkan struktur harga dan volume.
        3. Berikan rekomendasi aksi: BUY, SELL, HOLD, atau WAIT & SEE, berdasarkan indikator teknikal.
        4. Jika memberikan rekomendasi BUY atau SELL, tetapkan level Take Profit dan Stop Loss yang logis dan realistis.
        5. Analisa harus logis, berbasis data teknikal, dan hindari narasi spekulatif atau ambigu.
        6. Berikan tingkat confidence (keyakinan) terhadap hasil analisa dalam skala 1 sampai 10.
        7. Jangan rekomendasikan BUY atau SELL jika confidence < 8 atau sinyal teknikal tidak mendukung.
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

    try:
        response = client.models.generate_content(
            model=os.getenv("GEMINI_MODEL"),
            config=config,
            contents=contents,
        )

        logger.info(response.text)

        data = json.loads(response.text)

        confidence = data["confidence"]
        price_action = data["price_action"]

        if confidence > 7 and (price_action == "BUY" or price_action == "SELL"):
            order = mt5.ORDER_TYPE_BUY if price_action == "BUY" else mt5.ORDER_TYPE_SELL

            with ThreadPoolExecutor() as executor:
                for x in range(10):
                    executor.submit(open_position, order)

    except Exception as e:
        logger.error(e)


def main():
    logger.add("logs/file_{time}.log")

    if not mt5.initialize():
        logger.error("Gagal koneksi ke MetaTrader 5:", mt5.last_error())
        return

    if not mt5.symbol_select(symbol, True):
        logger.error(f"Symbol {symbol} tidak ditemukan atau tidak bisa dipilih.")
        return

    while True:
        now = datetime.now()
        if now.second == 0:

            with ThreadPoolExecutor() as executor:
                for tf, count in tfs:
                    executor.submit(get_rates, symbol, tf, count)

            analyze()


if __name__ == "__main__":
    main()
