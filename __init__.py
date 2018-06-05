# The COPYRIGHT file at the top level of this repository contains the full
# copyright notices and license terms.
from trytond.pool import Pool
from . import payment
from . import party


def register():
    Pool.register(
        payment.Journal,
        payment.Group,
        payment.Payment,
        party.Party,
        payment.Mandate,
        payment.Message,
        module='account_payment_sepa_es', type_='model')
    Pool.register(
        payment.MandateReport,
        module='account_payment_sepa_es', type_='report')
