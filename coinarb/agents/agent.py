import contextlib
import threading
import time
from collections import deque
from queue import Empty, Queue
from typing import Hashable, Tuple, Dict, Any, Type

import coinlib
from coinlib.coinlib.errors import CoinLibError
from coinlib.utils.mixins import LoggerMixin, ThreadMixin

from coinarb.dataprovider import DataProvider
from ..arbconfig import CONFIG
from ..credentialpool import CredentialPool
from ..fundmanager import Fund, FundManager, InsufficientFund


class TaskEmtpy(Empty):
    pass


class Agent(LoggerMixin, ThreadMixin):
    BALANCE_UPDATE_INTERVAL = 60

    def __init__(self, exchange: str, data_provider: DataProvider, *, interval: float = 0.5, debug: bool = False, **__):
        self.name = exchange
        self._logger = self._make_logger()
        self._thread_data = self._make_thread_data()
        self._data_provider = data_provider
        self.interval = interval
        self.is_debug = debug
        self.order_books = {}
        self.config = CONFIG[exchange]
        self._client_cls = getattr(coinlib, exchange).StreamClient  # type: Type[coinlib.StreamClient]
        self.agents = {}  # type: Dict[str, Agent]
        self.fund_manager = FundManager(exchange)
        self._credential_pool = CredentialPool(self.config['credentials'])
        self._task_q = Queue()
        self._order_q = deque()
        self._is_balance_updated = threading.Event()

        data_provider.register_callback(self.on_data)

        if debug:
            self.logger.info('DEBUG MODE')

    @contextlib.contextmanager
    def get_client(self) -> coinlib.StreamClient:
        with self._credential_pool.get() as credential:
            yield self._client_cls(credential['api_key'], credential['api_secret'])

    def sleep(self, seconds: float):
        _ = self
        time.sleep(seconds)

    def start_interval_task(self, interval: float, func, *args, **kwargs):
        def run():
            while self.is_active():
                try:
                    self.put_task(func, *args, **kwargs)
                except Exception as e:
                    self.logger.exception(e)
                self.sleep(interval)

        threading.Thread(target=run, daemon=True).start()

    def run(self):
        self.update_balances()
        self.init()
        self.activate()
        self.start_interval_task(self.interval, self.main)
        self.start_interval_task(self.BALANCE_UPDATE_INTERVAL, self.update_balances)
        while self.is_active():
            try:
                self.consume_tasks()
            except InsufficientFund as e:
                self.logger.warning(e)
                self._is_balance_updated.clear()
            except TaskEmtpy:
                pass
            except Exception as e:
                self.logger.exception(e)

    def init(self):
        pass

    def main(self):
        pass

    def consume_tasks(self):
        while True:
            try:
                task = self._task_q.get(timeout=0.5)
                task[0](*task[1], **task[2])
            except Empty:
                return

    def put_task(self, func, *args, **kwargs):
        self._task_q.put((func, args, kwargs))

    def get_order_books_snapshot(self):
        return self.order_books.copy()

    def on_data(self, exchange: str, key: Tuple[str, Hashable], data: Any):
        if key[0] == 'order_book':
            self.order_books[(exchange, key[1])] = data

    def register_agent(self, agent: 'Agent'):
        self.agents[agent.name] = agent

    def update_balances(self):
        with self.get_client() as client:
            balances = client.get_balances()
        self.fund_manager.update_balances(balances)
        self._is_balance_updated.set()

    def round_price(self, instrument: str, price: float) -> float:
        precisions = self.config['precisions']
        assert instrument in precisions, (self.name, instrument)
        precision = precisions[instrument]['price']
        return int(price * 10 ** precision) / (10 ** precision)

    def inc_dec_price(self, instrument: str, price: float, inc_dec: int) -> float:
        precisions = self.config['precisions']
        assert instrument in precisions, (self.name, instrument)
        precision = precisions[instrument]['price']
        price += inc_dec / (10 ** precision)
        return self.round_price(instrument, price)

    def round_qty(self, instrument: str, qty: float) -> float:
        precisions = self.config['precisions']
        assert instrument in precisions, (self.name, instrument)
        precision = precisions[instrument]['qty']
        return int(qty * 10 ** precision) / (10 ** precision)

    def inc_dec_qty(self, instrument: str, qty: float, inc_dec: int) -> float:
        precisions = self.config['precisions']
        assert instrument in precisions, (self.name, instrument)
        precision = precisions[instrument]['qty']
        qty += inc_dec / (10 ** precision)
        return self.round_qty(instrument, qty)

    def create_order_fak(self, instrument: str, order_type: str, side: str, price: float, qty: float,
                         *, fund: Fund) -> dict:
        assert self.fund_manager.has(fund), 'fund={} not found'.format(fund)
        assert fund.owner.exchange == self.name, (fund.owner.exchange, self.name)

        price = self.inc_dec_price(instrument, price, 1 if side == 'BUY' else -1)
        qty = self.round_qty(instrument, qty)
        self.logger.info(
            'submit_order instrument={} order_type={} side={} price={} qty={} fund={}'.format(
                instrument, order_type, side, price, qty, fund
            ))
        if self.is_debug:
            order = dict(price_executed_average=price, qty_executed=qty, debug=True)
        else:
            order_type = order_type.lower()
            with self.get_client() as client:
                if order_type == 'market':
                    order = client.create_market_order(instrument, side=side, qty=qty)
                elif order_type == 'limit':
                    order = client.create_limit_order(instrument, side=side, price=price, qty=qty)
                else:
                    assert False, order_type

            order = self.wait_cancel_order(order, timeout=300)
        self.fund_manager.apply_fund(fund)
        self.logger.info('submit_order executed price={price_executed_average} qty={qty_executed}'.format(**order))
        return order

    def wait_cancel_order(self, order: dict, timeout: float) -> dict:
        expired = time.time() + timeout
        while time.time() < expired:
            try:
                with self.get_client() as client:
                    order = client.get_order(**order)
                    self.logger.debug('order={}'.format(order))
                    if order['state'] == 'ACTIVE':
                        self.logger.info('try cancel_order order={}'.format(order))
                        try:
                            client.cancel_order(**order)
                        except CoinLibError:
                            pass
                    else:
                        return order
            except Exception as e:
                self.logger.exception(str(e))
                time.sleep(5)
            time.sleep(0.5)
        raise Exception('order not completed order={}'.format(order))
