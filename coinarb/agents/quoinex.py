import json
import threading
from typing import Hashable, Tuple, Any

from coinarb import utils
from . import agent
from ..arbconfig import CONFIG


class Agent(agent.Agent):
    def __init__(self, *args, **kwargs):
        super().__init__('quoinex', *args, **kwargs)

        self.user_id = CONFIG['quoinex']['user_id']
        self._order_book_updated = threading.Event()

    def init(self):
        self.client.open()
        subscriptions = [
            ('execution', ('XRP_JPY', self.user_id)),
            ('execution', ('QASH_JPY', self.user_id)),
            ('execution', ('QASH_USD', self.user_id)),
        ]
        self.client.subscribe(*subscriptions, on_data=self.on_execution)

    def main(self):
        pass

    def on_data(self, exchange: str, key: Tuple[str, Hashable], on_data: Any):
        super().on_data(exchange, key, on_data)
        if key[0] == 'order_book':
            if exchange in ('quoinex',):
                if not self._order_book_updated.is_set():
                    self._order_book_updated.set()
                    self.put_task(self.try_arbitrage_xrp_jpy)

    def on_execution(self, key: Tuple[str, Hashable], data: dict):
        pass

    def try_arbitrage_xrp_jpy(self):
        try:
            self._try_arbitrage_xrp_jpy()
        finally:
            self._order_book_updated.clear()

    def _try_arbitrage_xrp_jpy(self):
        snapshot = self.get_order_books_snapshot()
        instrument = 'XRP_JPY'
        if not {('quoinex', instrument), ('bitbankcc', instrument)}.issubset(snapshot):
            return

        config = CONFIG['XRP_JPY']
        qty_min = config['qty_min']
        qty_max = config['qty_max']

        def try_arb(sell_exchange, buy_exchange, my_side):
            sell_order_book = snapshot[(sell_exchange, instrument)]
            buy_order_book = snapshot[(buy_exchange, instrument)]

            diff = config['diff_signal']
            result_signal = utils.calculate_diff(sell_order_book, buy_order_book, diff)
            if not result_signal or result_signal['diff'] < diff:
                return
            self.logger.info('signal={}'.format(json.dumps(result_signal, sort_keys=True)))
            diff = config['diff_execute']
            result = utils.calculate_diff(sell_order_book, buy_order_book, diff)
            if not result or result['diff'] < diff:
                return
            qty = result['qty']
            if qty < qty_min:
                return
            qty = min([qty, qty_max])
            assert {sell_exchange, buy_exchange}.issubset(set(self.agents)), set(self.agents)
            self.logger.info('execute={}'.format(json.dumps(result, sort_keys=True)))

            exchange_map = dict(SELL=sell_exchange, BUY=buy_exchange)
            currency_map = dict(SELL='XRP', BUY='JPY')
            reverse_side_map = dict(SELL='BUY', BUY='SELL')
            other_side = reverse_side_map[my_side]
            my_agent = self.agents[exchange_map[my_side]]
            other_agent = self.agents[exchange_map[other_side]]
            fund_qty_map = {
                'XRP': qty,
                'JPY': qty * result['buy_jpy'],
            }
            my_fund_qty = fund_qty_map[currency_map[my_side]]
            my_fund = my_agent.fund_manager.reserve_fund(currency_map[my_side],
                                                         my_fund_qty * 1.005)
            with my_fund:
                other_fund_qty = fund_qty_map[currency_map[other_side]]
                other_fund = other_agent.fund_manager.reserve_fund(currency_map[other_side],
                                                                   other_fund_qty * 1.02)
                with other_fund:
                    execution = my_agent.submit_order(instrument, 'limit',
                                                      my_side,
                                                      result['{}_price'.format(my_side.lower())],
                                                      qty,
                                                      condition='fak',
                                                      fund=my_fund)
                    if execution['qty'] <= 0:
                        self.logger.warning(
                            'order not filled execution={}'.format(json.dumps(execution, sort_keys=True)))
                        return
                    my_agent.fund_manager.apply_fund(my_fund)

                    other_agent.submit_order(instrument,
                                             'market',
                                             other_side,
                                             result['{}_price'.format(other_side.lower())],
                                             execution['qty'],
                                             fund=other_fund)
            return

        try_arb(sell_exchange='quoinex', buy_exchange='bitbankcc', my_side='SELL')
        try_arb(sell_exchange='bitbankcc', buy_exchange='quoinex', my_side='BUY')
