import itertools
import logging
import pathlib
import re
import sys
import threading
import time
from pprint import pprint

from docopt import docopt

from coinarb import agents
from coinarb.arbconfig import CONFIG
from coinarb.bot import Bot
from coinarb.dataprovider import DataProvider, FxProvider


def main():
    args = docopt("""
    Usage:
      {f} [options]

    Options:
      --logging_level LEVEL  [default: INFO]
      --debug

    """.format(f=pathlib.Path(sys.argv[0]).name))
    pprint(args)
    params = {}
    for k, v in args.items():
        k = re.sub('^--', '', k)
        if isinstance(v, str):
            if v.isdigit():
                v = int(v)
            else:
                try:
                    v = float(v)
                except ValueError:
                    pass
        params[k] = v
    pprint(params)
    #params['logging_level'] = 'DEBUG'
    logging.basicConfig(level=getattr(logging, params['logging_level']),
                        format='%(asctime)s|%(name)s|%(levelname)s: %(msg)s')
    fx_provider = FxProvider(CONFIG['fx_instruments'])
    data_provider = DataProvider(fx_provider=fx_provider,
                                 order_books=CONFIG['instruments'])
    bitbankcc = agents.bitbankcc.Agent(data_provider, **params)
    quoinex = agents.quoinex.Agent(data_provider, **params)
    agent_list = [bitbankcc, quoinex]
    for a in agent_list:
        for b in agent_list:
            a.register_agent(b)

    try:
        fx_provider.start()
        data_provider.start()
        bitbankcc.start()
        quoinex.start()
        while fx_provider.is_active():
            time.sleep(0.5)
    finally:
        quoinex.stop()
        bitbankcc.stop()
        data_provider.stop()
        fx_provider.stop()
        quoinex.join()
        bitbankcc.join()
        data_provider.join()
        fx_provider.join()
    return
    start_wait_bot(**params)


def start_wait_bot(**params):
    bot = Bot(**params)
    try:
        bot.start().join()
    except KeyboardInterrupt:
        pass
    finally:
        bot.stop()


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        pass
