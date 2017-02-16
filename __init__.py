# The COPYRIGHT file at the top level of this repository contains the full
# copyright notices and license terms.
from trytond.pool import Pool
from . import account
from . import payment
from . import party


def register():
    Pool.register(
        payment.Journal,
        payment.Group,
        payment.Payment,
        party.Party,
        payment.Mandate,
        account.BankNumber,
        account.MoveLine,
        module='account_payment_sepa_es', type_='model')
    Pool.register(
        payment.PayLine,
        module='account_payment', type_='wizard')
    Pool.register(
        payment.MandateReport,
        module='account_payment_sepa_es', type_='report')
