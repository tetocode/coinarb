from typing import Hashable, Tuple, Any

from . import agent


class Agent(agent.Agent):
    def __init__(self, *args, **kwargs):
        super().__init__('bitbankcc', *args, **kwargs)

    def main(self):
        pass

    def on_data(self, exchange: str, key: Tuple[str, Hashable], on_data: Any):
        super().on_data(exchange, key, on_data)
