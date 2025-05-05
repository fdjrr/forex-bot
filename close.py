import json
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
sl = config["close"]["sl"]
sleep = config["close"]["sleep"]


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

    logger.info(f"Closing position for {symbol}")

    result = mt5.order_send(request)

    logger.info(result)


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
        logger.info("Checking positions...")

        positions = mt5.positions_get(symbol=symbol)

        if positions and len(positions) > 0:
            profit = sum(pos.profit for pos in positions)

            logger.info(f"Profit/Loss: {profit}")

            if profit >= tp or profit <= -sl:
                with ThreadPoolExecutor() as executor:
                    for position in positions:
                        executor.submit(close_position, position)
        else:
            logger.info("No positions found.")

        logger.info(f"Waiting for the {sleep} second...")

        time.sleep(sleep)


if __name__ == "__main__":

    main()
