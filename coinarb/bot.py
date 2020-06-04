import logging
import threading
import time
from typing import Hashable, Tuple, Dict

import coinlib
import coinlib.utils
from coinlib.utils.config import Config


class Bot:
    def __init__(self, exchange:str):
        config = Config().load()
        self.quoinex = coinlib.quoinex.StreamClient(**config.get_credential('quoinex', 'trade'))
        self.bitbankcc = coinlib.bitbankcc.StreamClient(**config.get_credential('bitbankcc', 'trade'))
        self.order_books = {}  # type: Dict[str, dict]
        self.be_stop = False

    def start(self) -> threading.Thread:
        thread = threading.Thread(target=self.run, daemon=True)
        thread.start()
        return thread

    def stop(self):
        self.be_stop = True

    def run(self):
        with self.quoinex:
            with self.bitbankcc:
                self.run_main_loop()

    def run_main_loop(self):
        self.quoinex.subscribe(order_book='XRP_JPY', on_data=lambda *args: self.on_order_book('quoinex', *args))
        self.bitbankcc.subscribe(order_book='XRP_JPY', on_data=lambda *args: self.on_order_book('bitbankcc', *args))
        while not self.be_stop:
            try:
                self.run_main()
            except Exception as e:
                logging.exception(e)

    def on_order_book(self, exchange: str, key: Tuple[str, Hashable], order_book: dict):
        print(exchange, key, order_book['timestamp'])
        self.order_books[(exchange, key)] = order_book

    def run_main(self):
        time.sleep(1)
