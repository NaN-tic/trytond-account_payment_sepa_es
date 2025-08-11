# coding: utf-8
# This file is part of account_payment_sepa_es module for Tryton.
# The COPYRIGHT file at the top level of this repository contains
# the full copyright notices and license terms.
from trytond.model import fields
from trytond.pool import Pool, PoolMeta

__all__ = ['BankAccountNumber']


class BankAccountNumber(metaclass=PoolMeta):
    __name__ = 'bank.account.number'

    sepa_mandates = fields.Function(fields.Many2Many(
            'account.payment.sepa.mandate', None, None, 'Mandate'),
        'get_sepa_mandates')

    @classmethod
    def get_sepa_mandates(cls, numbers, names):
        pool = Pool()
        Mandate = pool.get('account.payment.sepa.mandate')

        sepa_mandates = {
            'sepa_mandates': {}
            }
        for number in numbers:
            mandates = Mandate.search([
                    ('state', '=', 'validated'),
                    ('account_number', '=', number.id),
                    ])
            sepa_mandates['sepa_mandates'][number.id] = ([m.id for m in mandates]
                if mandates else None)
        return sepa_mandates
