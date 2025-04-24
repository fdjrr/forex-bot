import csv
import os
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

import MetaTrader5 as mt5
from dotenv import load_dotenv
from loguru import logger

load_dotenv()

symbol = os.getenv("SYMBOL")
deviation = 20
path = "trade_log.csv"


def close_position(position):
    logger.info(f"Closing position for {symbol}")

    order = (
        mt5.ORDER_TYPE_BUY
        if position.type == mt5.ORDER_TYPE_SELL
        else mt5.ORDER_TYPE_SELL
    )

    price = mt5.symbol_info_tick(symbol).ask

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


def main():
    logger.add("logs/file_{time}.log")

    if not mt5.initialize():
        logger.error("initialize() failed, error code =", mt5.last_error())
        quit()

    if not os.path.exists(path):
        with open(path, mode="w", newline="") as file:
            writer = csv.writer(file)
            writer.writerow(["order_type", "total", "profit", "last_closed_at"])

    while True:
        now = datetime.now()

        if now.second == 0:

            positions = mt5.positions_get(symbol=symbol)

            if len(positions) > 0:
                profit = sum(pos.profit for pos in positions)
                total = len(positions)
                last_closed_at = datetime.now()
                order_type = (
                    "BUY" if positions[0].type == mt5.ORDER_TYPE_BUY else "SELL"
                )

                with ThreadPoolExecutor() as executor:
                    for position in positions:
                        executor.submit(close_position, position)

                logger.info(f"Profit: {profit}")

                with open(path, mode="a", newline="") as file:
                    writer = csv.writer(file)
                    writer.writerow([order_type, total, profit, last_closed_at])


if __name__ == "__main__":
    main()
