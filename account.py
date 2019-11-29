# coding: utf-8
# This file is part of account_payment_sepa_es module for Tryton.
# The COPYRIGHT file at the top level of this repository contains
# the full copyright notices and license terms.
from trytond.pool import Pool, PoolMeta

__all__ = ['PayLine']


class PayLine(metaclass=PoolMeta):
    __name__ = 'account.move.line.pay'

    def get_payment(self, line, journals):
        pool = Pool()
        BankAccountNumber = pool.get('bank.account.number') 

        payment = super(PayLine, self).get_payment(line, journals)

        if hasattr(payment, 'bank_account'):
            numbers = BankAccountNumber.search([
                    ('account', '=', payment.bank_account),
                    ], order=[('sequence', 'ASC')], limit=1)
            payment.sepa_mandate = numbers[0].sepa_mandate if numbers else None
        return payment
