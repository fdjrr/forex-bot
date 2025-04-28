import csv
import enum
import json
import os
import pathlib
import random
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

import MetaTrader5 as mt5
import pandas as pd
from dotenv import load_dotenv
from google import genai
from google.genai import types
from loguru import logger
from pydantic import BaseModel
from ta.momentum import RSIIndicator, StochasticOscillator
from ta.trend import MACD, EMAIndicator, PSARIndicator
from ta.volatility import BollingerBands
from ta.volume import OnBalanceVolumeIndicator

load_dotenv()

symbol = os.getenv("SYMBOL")
tfs = [
    (mt5.TIMEFRAME_M1, 200),
    # (mt5.TIMEFRAME_M5, 200),
    # (mt5.TIMEFRAME_M15, 200),
    # (mt5.TIMEFRAME_M30, 200),
]
lot = 0.1
distance = 300
deviation = 20
last_analysis = None
loop = 1


class Signal(enum.Enum):
    SELL = "SELL"
    BUY = "BUY"
    WNS = "WAIT & SEE"


class PriceAction(enum.Enum):
    Bullish = "Bullish"
    Bearish = "Bearish"


class Trend(enum.Enum):
    Uptrend = "Uptrend"
    Downtrend = "Downtrend"
    Sideways = "Sideways"


class CandleStickPattern(enum.Enum):
    Hammer = "Hammer"
    InvertedHammer = "Inverted Hammer"
    ShootingStar = "Shooting Star"
    GravestoneDoji = "Gravestone Doji"
    Doji = "Doji"
    DojiStar = "Doji Star"
    DragonflyDoji = "Dragonfly Doji"
    GravestoneDojiStar = "Gravestone Doji Star"
    EveningDojiStar = "Evening Doji Star"
    EveningStar = "Evening Star"


class Analysis(BaseModel):
    support: float
    resistance: float
    confidence: int
    take_profit: float
    stop_loss: float
    reason: str
    signal: Signal
    price_action: PriceAction
    trend: Trend
    candle_stick_pattern: CandleStickPattern


def get_rates(symbol, tf, count=200):
    logger.info(f"Fetching {count} {tf} rates for {symbol}")

    rates = mt5.copy_rates_from_pos(symbol, tf, 0, count)

    df = pd.DataFrame(rates)
    df["time"] = pd.to_datetime(df["time"], unit="s")

    # RSI
    df["RSI_14"] = RSIIndicator(close=df["close"], window=14).rsi()

    # Exponential Moving Average
    df["EMA_9"] = EMAIndicator(close=df["close"], window=9).ema_indicator()
    df["EMA_21"] = EMAIndicator(close=df["close"], window=21).ema_indicator()

    # On Balance Volume
    df["OBV"] = OnBalanceVolumeIndicator(
        close=df["close"], volume=df["real_volume"]
    ).on_balance_volume()

    # Parabolic SAR
    psar_indicator = PSARIndicator(
        high=df["high"], low=df["low"], close=df["close"], step=0.02, max_step=0.2
    )
    df["PSAR"] = psar_indicator.psar()

    # Stochastic Oscillator
    stoch = StochasticOscillator(
        high=df["high"], low=df["low"], close=df["close"], window=5, smooth_window=3
    )
    df["STOCH_%K"] = stoch.stoch()
    df["STOCH_%D"] = stoch.stoch_signal()

    # Bollinger Bands
    bb = BollingerBands(close=df["close"], window=20, window_dev=2)
    df["BB_Lower"] = bb.bollinger_lband()
    df["BB_Middle"] = bb.bollinger_mavg()
    df["BB_Upper"] = bb.bollinger_hband()

    # MACD
    macd = MACD(close=df["close"], window_slow=26, window_fast=12, window_sign=9)
    df["MACD"] = macd.macd()
    df["MACD_Signal"] = macd.macd_signal()
    df["MACD_Hist"] = macd.macd_diff()

    path = f"results/{symbol}_{tf}_rates.csv"
    df.to_csv(path, index=False)

    logger.info(f"Data saved to {path}")

    return df


def get_positions():
    path = "trade_log.csv"

    if not os.path.exists(path):
        with open(path, mode="w", newline="") as file:
            writer = csv.writer(file)
            writer.writerow(["order_type", "total", "profit", "last_closed_at"])

    now = datetime.now()
    positions = mt5.positions_get(symbol=symbol)

    if len(positions) > 0:
        profit = sum(pos.profit for pos in positions)
        total = len(positions)
        last_closed_at = now.strftime("%Y-%m-%d %H:%M:%S")
        order_type = "BUY" if positions[0].type == mt5.ORDER_TYPE_BUY else "SELL"

        with ThreadPoolExecutor() as executor:
            for position in positions:
                executor.submit(close_position, position)

        logger.info(f"Profit: {profit}")

        with open(path, mode="a", newline="") as file:
            writer = csv.writer(file)
            writer.writerow([order_type, total, profit, last_closed_at])

        logger.info(f"Trade log saved to {path}")


def close_position(position):
    logger.info(f"Closing position for {symbol}")

    symbol_tick = mt5.symbol_info_tick(symbol)

    order = (
        mt5.ORDER_TYPE_BUY
        if position.type == mt5.ORDER_TYPE_SELL
        else mt5.ORDER_TYPE_SELL
    )

    price = symbol_tick.ask if order == mt5.ORDER_TYPE_BUY else symbol_tick.bid

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

    result = mt5.order_send(request)

    logger.info(result)


def open_position(order):
    logger.info(f"Opening position for {symbol}")

    symbol_tick = mt5.symbol_info_tick(symbol)

    price = symbol_tick.ask if order == mt5.ORDER_TYPE_BUY else symbol_tick.bid

    if order == mt5.ORDER_TYPE_BUY:
        logger.info(f"Buying {lot} lots of {symbol} at {price}")
    else:
        logger.info(f"Selling {lot} lots of {symbol} at {price}")

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
    global last_analysis

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
Analisa sebelumnya : {last_analysis}

Data candle untuk simbol {symbol}:

Tugas kamu adalah menganalisa data candle tersebut secara mendalam. Lakukan hal berikut:

1. Analisa semua data candle yang ada. Analisa harus logis, berbasis data teknikal, dan hindari narasi spekulatif atau ambigu.
2. Tentukan satu area support dan resistance terdekat berdasarkan struktur candle dan volume dari semua data candle yang ada.
3. Berikan signal: BUY, SELL, atau WAIT & SEE, berdasarkan struktur candle dan volume serta indikator teknikal.
5. Hanya berikan signal jika minimal dua dari tiga indikator menunjukkan sinyal yang kuat dan tidak saling bertentangan.
6. Jika signal BUY atau SELL, tetapkan level Take Profit (0.6%) dan Stop Loss (0.3%) yang logis dan realistis dari semua data candle yang ada.
7. Berikan tingkat confidence (keyakinan) terhadap hasil analisa dalam skala 1 sampai 10.
8. Jangan berikan signal BUY atau SELL jika confidence < 8 atau struktur candle dan volume serta indikator teknikal tidak mendukung.
9. Tetap melakukan analisa yang konsisten dari analisa sebelumnya.
10. Fokus hanya pada analisa — tidak perlu memberikan penjelasan tambahan di luar kerangka response_schema.
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

        last_analysis = response.text

        data = json.loads(response.text)

        confidence = data["confidence"]
        signal = data["signal"]

        if confidence > 7 and (signal == "BUY" or signal == "SELL"):
            order = mt5.ORDER_TYPE_BUY if signal == "BUY" else mt5.ORDER_TYPE_SELL

            with ThreadPoolExecutor() as executor:
                for x in range(loop):
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

    now = time.time()
    start_from = now + (60 * 5)

    logger.info("Starting...")

    while True:
        now = time.time()

        if now > start_from:

            get_positions()

            with ThreadPoolExecutor() as executor:
                for tf, count in tfs:
                    executor.submit(get_rates, symbol, tf, count)

            analyze()

            start_from = start_from + (60 * 5)


if __name__ == "__main__":
    main()
