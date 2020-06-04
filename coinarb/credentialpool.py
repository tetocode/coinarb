import contextlib
import logging
from queue import Queue
from typing import Iterable

from coinlib.utils.mixins import LoggerMixin


class CredentialPool(LoggerMixin):
    def __init__(self, credentials: Iterable[dict] = None, logger: logging.Logger = None):
        self._q = Queue()
        self._logger = self._make_logger(logger)
        self.add_credentials(credentials or [])

    def add_credentials(self, credentials: Iterable[dict]):
        for credential in credentials:
            self._q.put(credential)

    @contextlib.contextmanager
    def get(self) -> dict:
        credential = self._q.get()
        try:
            yield credential
        finally:
            self._q.put(credential)
