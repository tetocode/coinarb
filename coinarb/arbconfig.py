CONFIG = {
    'bitbankcc': {
        'funds': {
            'JPY': dict(locked=0),
            'XRP': dict(locked=0),
        },
        'precisions': {
            'XRP_JPY': dict(price=3, qty=4)
        }
    },
    'quoinex': {
        'user_id': 0,
        'funds': {
            'JPY': dict(locked=10000000),
            'XRP': dict(locked=5000),
            'QASH': dict(locked=80000),
        },
        'precisions': {
            'XRP_JPY': dict(price=5, qty=6)
        }
    },
    'instruments': [
        ('bitbankcc', 'XRP_JPY'),
        #        ('bitfinex2', 'XRP_USD'),
        #        ('bitfinex2', 'QASH_USD'),
        ('quoinex', 'XRP_JPY'),
        #        ('quoinex', 'QASH_JPY'),
        #        ('quoinex', 'QASH_USD'),
    ],
    'fx_instruments': [
        'USD_JPY',
    ],
    'XRP_JPY': {
        'diff_signal': 1.01,
        'diff_execute': 1,
        'qty_min': 1,
        'qty_max': 1,
    }
}

try:
    from . import arbconfiglocal

    CONFIG.update(arbconfiglocal.CONFIG)
except ImportError:
    pass
