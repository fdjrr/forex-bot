import csv
import os
from datetime import datetime

import MetaTrader5 as mt5
from dotenv import load_dotenv
from loguru import logger

load_dotenv()

symbol = os.getenv("SYMBOL")
deviation = 20
csv_file = "trade_log.csv"

if not os.path.exists(csv_file):
    with open(csv_file, mode="w", newline="") as file:
        writer = csv.writer(file)
        writer.writerow(
            ["order_position", "total_position", "profit", "last_closed_at"]
        )


def main():
    if not mt5.initialize():
        print("initialize() failed, error code =", mt5.last_error())
        quit()

    while True:
        now = datetime.now()

        if now.hour >= 6 and now.hour < 22 and now.second == 0:

            positions = mt5.positions_get(symbol=symbol)

            if positions and len(positions) > 0:
                profit = 0
                total_position = len(positions)
                order_position = ""
                last_closed_at = datetime.now()

                for position in positions:
                    profit += position.profit
                    order_position = (
                        "BUY" if position.type == mt5.ORDER_TYPE_BUY else "SELL"
                    )

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

                    result = mt5.order_send(request)

                    logger.info(result)

                logger.info(f"Profit: {profit}")

                with open(csv_file, mode="a", newline="") as file:
                    writer = csv.writer(file)
                    writer.writerow(
                        [order_position, total_position, profit, last_closed_at]
                    )


if __name__ == "__main__":
    main()
