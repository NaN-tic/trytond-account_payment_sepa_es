# The COPYRIGHT file at the top level of this repository contains
# the full copyright notices and license terms.
from trytond.model import fields
from trytond.pool import PoolMeta

__all__ = ['BankNumber', 'MoveLine']


class BankNumber:
    __metaclass__ = PoolMeta
    __name__ = 'bank.account.number'
    mandates = fields.One2Many('account.payment.sepa.mandate',
        'account_number', 'Mandates')


class MoveLine:
    __metaclass__ = PoolMeta
    __name__ = 'account.move.line'

    sepa_scheme = fields.Function(fields.Selection([
            ('', ''),
            ('CORE', 'Core'),
            ('B2B', 'Business to Business'),
            ], 'Scheme'),
        'get_sepa_scheme', searcher='search_sepa_scheme')

    def get_sepa_scheme(self, name):
        if self.bank_account:
            for number in self.bank_account.numbers:
                if number.mandates:
                    return number.mandates[0].scheme
        return ''

    @classmethod
    def search_sepa_scheme(cls, name, clause):
        return [tuple(('bank_account.numbers.mandates.scheme',))
            + tuple(clause[1:])]
