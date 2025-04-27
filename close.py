import os
import time
from concurrent.futures import ThreadPoolExecutor

import MetaTrader5 as mt5
from dotenv import load_dotenv
from loguru import logger

load_dotenv()

symbol = os.getenv("SYMBOL")
deviation = 20
tp = 20


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
        logger.error("Gagal koneksi ke MetaTrader 5:", mt5.last_error())
        return

    if not mt5.symbol_select(symbol, True):
        logger.error(f"Symbol {symbol} tidak ditemukan atau tidak bisa dipilih.")
        return

    now = time.time()
    start_from = now + (60 * 5)

    while True:
        now = time.time()

        if now > start_from:
            positions = mt5.positions_get(symbol=symbol)

            if len(positions) > 0:
                profit = sum(pos.profit for pos in positions)

                if profit >= tp:
                    logger.info(f"Profit mencapai {tp}. Menutup posisi.")

                    with ThreadPoolExecutor() as executor:
                        for position in positions:
                            executor.submit(close_position, position)

            start_from = start_from + (60 * 5)


if __name__ == "__main__":
    main()
