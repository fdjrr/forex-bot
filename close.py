import csv
import json
import os
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

import MetaTrader5 as mt5
from loguru import logger

with open("config.json", "r") as f:
    config = json.load(f)

symbol = config["symbol"]
deviation = config["deviation"]

tp = config["close"]["tp"]
summary_tp = config["close"]["summary_tp"]
sl = config["close"]["sl"]
summary_sl = config["close"]["summary_sl"]
sleep = config["close"]["sleep"]
start_hour = config["start_hour"]
end_hour = config["end_hour"]

path = "trade_log.csv"

if not os.path.exists(path):
    with open(path, mode="w", newline="") as file:
        writer = csv.writer(file)
        writer.writerow(["ticket", "order_type", "profit", "last_closed_at"])


def close_position(position):
    symbol_tick = mt5.symbol_info_tick(symbol)

    if position.type == mt5.ORDER_TYPE_BUY:
        order_type = mt5.ORDER_TYPE_SELL
        price = symbol_tick.ask
    else:
        order_type = mt5.ORDER_TYPE_BUY
        price = symbol_tick.bid

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
    logger.add("logs/close_{time}.log")

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
            logger.info("Checking positions...")

            positions = mt5.positions_get(symbol=symbol)

            if positions and len(positions) > 0:
                if summary_tp:
                    profit = sum(pos.profit for pos in positions)

                    logger.info(f"Profit: {profit}")

                    if profit >= tp:
                        with ThreadPoolExecutor() as executor:
                            for position in positions:
                                executor.submit(close_position, position)
                else:
                    for pos in positions:
                        if pos.profit >= tp:
                            logger.info(f"Profit: {pos.profit}")

                            close_position(pos)

                if summary_sl:
                    loss = sum(pos.profit for pos in positions)

                    logger.info(f"Loss: {loss}")

                    if loss >= sl:
                        with ThreadPoolExecutor() as executor:
                            for position in positions:
                                executor.submit(close_position, position)
                else:
                    for pos in positions:
                        if pos.profit >= sl:
                            logger.info(f"Loss: {pos.profit}")

                            close_position(pos)

            else:
                logger.info("No positions found.")

            logger.info(f"Waiting for the {sleep} second...")

            time.sleep(sleep)
        else:
            time.sleep(60 * 60)  # sleep for 1 hour


if __name__ == "__main__":

    main()
