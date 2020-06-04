import logging
import math
import threading
from collections import defaultdict
from typing import Callable, Set, Dict

from coinarb.arbconfig import CONFIG


class InsufficientFund(Exception):
    pass


class Fund(dict):
    def __init__(self, owner: 'FundManager', currency: str, qty: float, release_method: Callable[['Fund'], None]):
        super().__init__(owner=owner, currency=currency, qty=qty)
        self._release_method = release_method

    @property
    def owner(self) -> 'FundManager':
        return self['owner']

    @property
    def currency(self) -> str:
        return self['currency']

    @property
    def qty(self) -> float:
        return self['qty']

    def release(self):
        self._release_method(self)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.release()

    def __hash__(self):
        return id(self)

    def __eq__(self, other):
        return self is other

    def __str__(self):
        return str(dict(self))


class Balance:
    def __init__(self, total: float = 0, used: float = 0,
                 reserved: float = 0, locked: float = math.inf):
        self.total = total
        self.used = used
        self.reserved = reserved
        self.locked = locked

    @property
    def free(self) -> float:
        return self.total - (self.used + self.reserved + self.locked)


class FundManager:
    def __init__(self, exchange: str):
        self.logger = logging.getLogger(__name__).getChild(exchange)
        self.exchange = exchange
        self._funds_config = CONFIG[exchange]['funds']
        self.balances = defaultdict(Balance)  # type: Dict[str, Balance]
        self._reserved_funds = set()  # type: Set[Fund]
        self._fund_lock = threading.RLock()

        for currency, v in self._funds_config.items():
            self.balances[currency].locked = v['locked']

    def has(self, fund: Fund):
        return fund in self._reserved_funds

    def get_lock(self) -> threading.RLock:
        return self._fund_lock

    def update_balances(self, balances: dict):
        with self.get_lock():
            for currency, balance in balances.items():
                self.balances[currency].total = balance['total']
                used = balance['used']
                if math.isnan(used):
                    used = 0
                self.balances[currency].used = used
                self.log_balance(currency)

    def log_balance(self, currency: str):
        balance = self.balances[currency]
        self.logger.info('balance {} total={} locked={} used={} reserved={} free={}'.format(
            currency, balance.total, balance.locked, balance.used, balance.reserved, balance.free
        ))

    def reserve_fund(self, currency: str, qty: float) -> Fund:
        with self.get_lock():
            free = self.balances[currency].free
            if free < qty:
                raise InsufficientFund('currency={} qty={} > free={}'.format(currency, qty, free))
            self.balances[currency].reserved += qty
            fund = Fund(self, currency, qty, self.release_fund)
            self._reserved_funds.add(fund)
            self.logger.info('reserved {} {}'.format(fund.currency, fund.qty))
            self.log_balance(currency)
            return fund

    def release_fund(self, fund: Fund):
        with self.get_lock():
            if self.has(fund):
                self._reserved_funds.difference_update([fund])
                self.balances[fund.currency].reserved -= fund.qty
                self.logger.info('released {} {}'.format(fund.currency, fund.qty))
                self.log_balance(fund.currency)

    def renew_fund(self, fund: Fund) -> Fund:
        with self.get_lock():
            assert self.has(fund), 'fund={} not in {}'.format(fund, self._reserved_funds)
            self.logger.info('renew fund {} {}'.format(fund.currency, fund.qty))
            fund.release()
            return self.reserve_fund(fund.currency, fund.qty)

    def apply_fund(self, fund: Fund):
        with self.get_lock():
            if self.has(fund):
                self.logger.info('apply fund {} {}'.format(fund.currency, fund.qty))
                fund.release()
                self.balances[fund.currency].total -= fund.qty
                self.log_balance(fund.currency)
