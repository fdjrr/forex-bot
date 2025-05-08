import csv
import enum
import json
import os
import pathlib
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

import MetaTrader5 as mt5
import pandas as pd
import pyautogui
import pygetwindow as gw
from google import genai
from google.genai import types
from loguru import logger
from pydantic import BaseModel
from ta.momentum import RSIIndicator, StochasticOscillator
from ta.trend import EMAIndicator
from ta.volatility import BollingerBands

with open("config.json", "r") as f:
    config = json.load(f)

symbol = config["symbol"]
deviation = config["deviation"]
min_signal_count = config["min_signal_count"]
capture = config["capture"]
capture_path = config["capture_path"]

tfs = []

for timeframe in config["agent"]["timeframes"]:
    if timeframe["tf"] == "M1":
        tfs.append((mt5.TIMEFRAME_M1, timeframe["pos"]))
    elif timeframe["tf"] == "M5":
        tfs.append((mt5.TIMEFRAME_M5, timeframe["pos"]))
    elif timeframe["tf"] == "H1":
        tfs.append((mt5.TIMEFRAME_H1, timeframe["pos"]))
    elif timeframe["tf"] == "H4":
        tfs.append((mt5.TIMEFRAME_H4, timeframe["pos"]))
    elif timeframe["tf"] == "D1":
        tfs.append((mt5.TIMEFRAME_D1, timeframe["pos"]))

initial_lot = config["agent"]["initial_lot"]
martingle_mode = config["agent"]["martingle_mode"]
martingle_multiplier = config["agent"]["martingle_multiplier"]
lot = initial_lot
loop = config["agent"]["loop"]

api_keys = config["agent"]["api_keys"]
gemini_model = config["agent"]["gemini_model"]
system_path = config["agent"]["system_path"]
prompt_path = config["agent"]["prompt_path"]

with open(system_path, "r", encoding="utf-8") as f:
    system_instruction = f.read()

with open(prompt_path, "r", encoding="utf-8") as f:
    prompt = f.read()

sleep = config["agent"]["sleep"]
start_hour = config["start_hour"]
end_hour = config["end_hour"]

path = "trade_log.csv"

if not os.path.exists(path):
    with open(path, mode="w", newline="") as file:
        writer = csv.writer(file)
        writer.writerow(["ticket", "order_type", "profit", "last_closed_at"])


class Signal(enum.Enum):
    SELL = "SELL"
    BUY = "BUY"
    WNS = "WAIT & SEE"


class Trend(enum.Enum):
    BULLISH = "Bullish"
    BEARISH = "Bearish"
    NEUTRAL = "Neutral"


class Momentum(enum.Enum):
    OVERSOLD = "Oversold"
    OVERBOUGHT = "Overbought"
    NEUTRAL = "Neutral"


class Analysis(BaseModel):
    support: float
    resistance: float
    confidence: int
    trend: Trend
    momentum: Momentum
    signal: Signal
    justification: str


def get_rates(tf, pos):
    rates = mt5.copy_rates_from_pos(symbol, tf, 0, pos)

    if rates is None:
        logger.error(
            f"Failed to get rates for {symbol}. Error code: {mt5.last_error()}"
        )
        return None

    df = pd.DataFrame(rates)

    if tf == mt5.TIMEFRAME_M1:
        df["tf"] = "M1"
    elif tf == mt5.TIMEFRAME_M5:
        df["tf"] = "M5"
    elif tf == mt5.TIMEFRAME_H1:
        df["tf"] = "H1"
    elif tf == mt5.TIMEFRAME_H4:
        df["tf"] = "H4"
    elif tf == mt5.TIMEFRAME_D1:
        df["tf"] = "D1"

    df["time"] = pd.to_datetime(df["time"], unit="s")

    ema_8 = EMAIndicator(close=df["close"], window=8)
    ema_21 = EMAIndicator(close=df["close"], window=21)
    df["EMA_8"] = ema_8.ema_indicator()
    df["EMA_21"] = ema_21.ema_indicator()

    rsi = RSIIndicator(close=df["close"], window=7)
    df["RSI"] = rsi.rsi()

    stochastic = StochasticOscillator(
        high=df["high"], low=df["low"], close=df["close"], window=5, smooth_window=3
    )
    df["Stoch_K"] = stochastic.stoch()
    df["Stoch_D"] = stochastic.stoch_signal()

    bb = BollingerBands(close=df["close"], window=10, window_dev=2)
    df["BB_High"] = bb.bollinger_hband()
    df["BB_Low"] = bb.bollinger_lband()
    df["BB_Mid"] = bb.bollinger_mavg()

    df = df.sort_values(by="time", ascending=False)

    path = f"results/{symbol}_{tf}.csv"

    df.to_csv(path, index=False)

    logger.info(f"Rates for {symbol} saved to {path}")

    return df


def generate_response(api_key, contents):
    try:
        client = genai.Client(api_key=api_key)

        config = types.GenerateContentConfig(
            system_instruction=system_instruction,
            response_mime_type="application/json",
            response_schema=Analysis,
        )

        response = client.models.generate_content(
            model=gemini_model,
            config=config,
            contents=contents,
        )

        logger.info(f"Response from GenAI: {response.text}")

        return Analysis.model_validate_json(response.text)
    except Exception as e:
        logger.error(f"Failed to create GenAI client: {e}")
        return None


def capture_window():
    try:
        logger.info("Capturing window...")

        mt5_window = None
        for window in gw.getAllTitles():
            if "Hedge" in window:
                mt5_window = gw.getWindowsWithTitle(window)[0]
                break

        mt5_window.activate()

        time.sleep(2)

        x, y, width, height = (
            mt5_window.left,
            mt5_window.top,
            mt5_window.width,
            mt5_window.height,
        )

        screenshot = pyautogui.screenshot(region=(x, y, width, height))

        screenshot.save(capture_path)

        logger.info(f"Screenshot saved to {capture_path}")
    except Exception as e:
        logger.error(f"Failed to capture window: {e}")


def calculate_lot():
    if not martingle_mode:
        return initial_lot

    losses = 0

    positions = mt5.positions_get(symbol=symbol)

    if positions and len(positions) > 0:
        for pos in positions:
            if pos.profit < 0:
                losses += 1

    if losses == 0:
        return initial_lot

    return initial_lot * (martingle_multiplier**losses)


def open_position(order_type):
    symbol_tick = mt5.symbol_info_tick(symbol)

    price = symbol_tick.ask if order_type == mt5.ORDER_TYPE_BUY else symbol_tick.bid

    request = {
        "action": mt5.TRADE_ACTION_DEAL,
        "symbol": symbol,
        "volume": calculate_lot(),
        "type": order_type,
        "price": price,
        "deviation": deviation,
        "magic": 234000,
        "comment": "",
        "type_time": mt5.ORDER_TIME_GTC,
        "type_filling": mt5.ORDER_FILLING_IOC,
    }

    result = mt5.order_send(request)

    logger.info(result)

    if result.retcode != mt5.TRADE_RETCODE_DONE:
        logger.error(f"Failed to open position. Error code: {result.retcode}")
    else:
        logger.info("Position opened successfully.")


def close_opposite_positions(signal: Signal):
    positions = mt5.positions_get(symbol=symbol)

    if positions and len(positions) > 0:
        for pos in positions:
            if signal == Signal.BUY and pos.type == mt5.ORDER_TYPE_SELL:
                close_position(pos, mt5.ORDER_TYPE_BUY)

            elif signal == Signal.SELL and pos.type == mt5.ORDER_TYPE_BUY:
                close_position(pos, mt5.ORDER_TYPE_SELL)


def close_position(position, order_type):
    symbol_tick = mt5.symbol_info_tick(symbol)

    price = symbol_tick.ask if order_type == mt5.ORDER_TYPE_BUY else symbol_tick.bid

    request = {
        "action": mt5.TRADE_ACTION_DEAL,
        "position": position.ticket,
        "symbol": symbol,
        "volume": position.volume,
        "type": order_type,
        "price": price,
        "deviation": deviation,
        "magic": 234000,
        "comment": "",
        "type_time": mt5.ORDER_TIME_GTC,
        "type_filling": mt5.ORDER_FILLING_IOC,
    }

    result = mt5.order_send(request)

    logger.info(result)

    if result.retcode != mt5.TRADE_RETCODE_DONE:
        logger.error(f"Failed to close position. Error code: {result.retcode}")
    else:
        now = datetime.now()
        last_closed_at = now.strftime("%Y-%m-%d %H:%M:%S")

        with open(path, mode="a", newline="") as file:
            writer = csv.writer(file)
            writer.writerow(
                [position.ticket, position.type, position.profit, last_closed_at]
            )

        logger.info("Position closed successfully.")


def main():
    logger.add("logs/agent_{time}.log")

    if not mt5.initialize():
        logger.error("Failed to initialize MetaTrader 5. Error code:", mt5.last_error())
        return

    logger.info("MetaTrader 5 initialized successfully.")

    account_info = mt5.account_info()

    if account_info is None:
        logger.error("Failed to get account info. Error code:", mt5.last_error())
        return
    else:
        logger.info(f"Account info: {account_info}")

    while True:
        now = datetime.now()

        if now.hour >= start_hour and now.hour <= end_hour:
            logger.info(f"Current time: {now}")

            logger.info("Starting analysis...")

            contents = []

            with ThreadPoolExecutor() as executor:
                for tf, pos in tfs:
                    executor.submit(get_rates, tf, pos)

            for tf, pos in tfs:
                path = f"results/{symbol}_{tf}.csv"
                filepath = pathlib.Path(path)
                contents.append(
                    types.Part.from_bytes(
                        data=filepath.read_bytes(),
                        mime_type="text/csv",
                    )
                )

            if capture:
                capture_window()

                if os.path.exists(capture_path):
                    filepath = pathlib.Path(capture_path)
                    contents.append(
                        types.Part.from_bytes(
                            data=filepath.read_bytes(),
                            mime_type="image/png",
                        )
                    )

            contents.append(prompt)

            with ThreadPoolExecutor() as executor:
                futures = [
                    executor.submit(generate_response, api_key, contents)
                    for api_key in api_keys
                ]

            results = [
                future.result() for future in futures if future.result() is not None
            ]

            signals = [res.signal for res in results]
            signal_count = Counter(signals)

            if signal_count[Signal.BUY] >= min_signal_count:
                order_type = mt5.ORDER_TYPE_BUY

                logger.info("Opening BUY position...")

                close_opposite_positions(Signal.BUY)

                with ThreadPoolExecutor() as executor:
                    for x in range(loop):
                        executor.submit(open_position, order_type)
            elif signal_count[Signal.SELL] >= 3:
                order_type = mt5.ORDER_TYPE_SELL

                logger.info("Opening SELL position...")

                close_opposite_positions(Signal.SELL)

                with ThreadPoolExecutor() as executor:
                    for x in range(loop):
                        executor.submit(open_position, order_type)
            else:
                logger.info("WAIT & SEE. No action taken.")

            logger.info(f"Waiting for the {sleep} second...")

            time.sleep(sleep)
        else:
            time.sleep(60 * 60)  # sleep for 1 hour


if __name__ == "__main__":
    main()
