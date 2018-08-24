# The COPYRIGHT file at the top level of this repository contains the full
# copyright notices and license terms.
from trytond.pool import PoolMeta, Pool
from trytond.model import ModelView
from trytond.pyson import Eval, Bool
from trytond.transaction import Transaction
import stdnum.eu.at_02 as sepa


__all__ = ['Party']


class Party(metaclass=PoolMeta):
    __name__ = 'party.party'

    @classmethod
    def __setup__(cls):
        super(Party, cls).__setup__()
        cls._buttons.update({
                'calculate_sepa_creditor_identifier': {
                    'invisible': (Bool(Eval('sepa_creditor_identifier_used'))
                        | ~(Bool(Eval('tax_identifier')))),
                    }
                })

    @classmethod
    @ModelView.button
    def calculate_sepa_creditor_identifier(cls, parties):
        pool = Pool()
        Identifier = pool.get('party.identifier')
        identifiers = []
        for party in parties:
            if not party.tax_identifier:
                continue
            vat_code = party.tax_identifier.code
            number = vat_code[:2] + '00ZZZ' + vat_code[2:].upper()
            check_sum = sepa.calc_check_digits(number)
            identifier = Identifier()
            identifier.type = 'sepa'
            identifier.code = (vat_code[:2] + check_sum + 'ZZZ' +
                vat_code[2:].upper())
            identifier.party = party
            identifiers.append(identifier)

        Identifier.save(identifiers)

    def get_sepa_creditor_identifier_used(self, name):
        context = Transaction().context

        res = super(Party, self).get_sepa_creditor_identifier_used(name)

        suffix = context.get('suffix', None)
        kind = context.get('kind', None)
        if res and suffix:
            res = (res[:4] + suffix + res[7:]
                if kind == 'receivable' else res[7:] + suffix)
        return res
