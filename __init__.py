# The COPYRIGHT file at the top level of this repository contains the full
# copyright notices and license terms.
from trytond.pool import Pool
from . import account, payment, party


def register():
    Pool.register(
        payment.Journal,
        payment.Group,
        payment.Payment,
        party.Party,
        payment.Mandate,
        account.BankNumber,
        account.MoveLine,
        payment.Message,
        module='account_payment_sepa_es', type_='model')
    Pool.register(
        payment.PayLine,
        module='account_payment', type_='wizard')
