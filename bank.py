# coding: utf-8
# This file is part of account_payment_sepa_es module for Tryton.
# The COPYRIGHT file at the top level of this repository contains
# the full copyright notices and license terms.
from trytond.model import fields
from trytond.pool import Pool, PoolMeta

__all__ = ['BankAccountNumber']


class BankAccountNumber(metaclass=PoolMeta):
    __name__ = 'bank.account.number'

    sepa_mandate = fields.Function(fields.Many2One(
        'account.payment.sepa.mandate', 'Mandate'), 'get_sepa_mandate')

    @classmethod
    def get_sepa_mandate(cls, numbers, name):
        pool = Pool()
        Mandate = pool.get('account.payment.sepa.mandate')

        mandates = {}
        for number in numbers:
            mandate = Mandate.search([
                    ('state', '=', 'validated'),
                    ('account_number', '=', number.id),
                    ], order=[('create_date', 'DESC')], limit=1)
            mandates[number.id] = mandate[0] if mandate else None
        return mandates
