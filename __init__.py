# The COPYRIGHT file at the top level of this repository contains the full
# copyright notices and license terms.
from trytond.pool import Pool
from . import account
from . import bank
from . import party
from . import payment


def register():
    Pool.register(
        bank.BankAccountNumber,
        party.Party,
        payment.Journal,
        payment.Group,
        payment.Payment,
        payment.Mandate,
        payment.Message,
        module='account_payment_sepa_es', type_='model')
    Pool.register(
        payment.MandateReport,
        module='account_payment_sepa_es', type_='report')
    Pool.register(
        account.PayLine,
        module='account_payment_sepa_es', type_='wizard')
