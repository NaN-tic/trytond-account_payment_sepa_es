# The COPYRIGHT file at the top level of this repository contains the full
# copyright notices and license terms.
from trytond.pool import Pool
from .account import *
from .payment import *
from .party import *


def register():
    Pool.register(
        Journal,
        Group,
        Payment,
        Party,
        Mandate,
        BankNumber,
        MoveLine,
        module='account_payment_sepa_es', type_='model')
    Pool.register(
        PayLine,
        module='account_payment', type_='wizard')
