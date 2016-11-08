# The COPYRIGHT file at the top level of this repository contains the full
# copyright notices and license terms.
from trytond.pool import PoolMeta, Pool
from trytond.model import ModelView
from trytond.pyson import Eval, Bool
from trytond.transaction import Transaction
from stdnum.iso7064 import mod_97_10
# at_02 is pending to be included on python-stdnum.
# See: https://github.com/arthurdejong/python-stdnum/pull/5
from .at_02 import is_valid, _to_base10


__all__ = ['Party']


class Party:
    __metaclass__ = PoolMeta
    __name__ = 'party.party'

    @classmethod
    def __setup__(cls):
        super(Party, cls).__setup__()

        cls._error_messages.update({
                'invalid_creditor_identifier': ('Invalid creditor identifier '
                    '"%(identifier)s" for party "%(party)s".'),
                })
        cls._buttons.update({
                'calculate_sepa_creditor_identifier': {
                    'invisible': (Bool(Eval('sepa_creditor_identifier_used'))
                        | ~(Bool(Eval('tax_identifier')))),
                    }
                })

    @classmethod
    def validate(cls, parties):
        super(Party, cls).validate(parties)
        for party in parties:
            party.check_sepa_creditor_identifier()

    def check_sepa_creditor_identifier(self):
        if not self.sepa_creditor_identifier:
            return
        if not is_valid(self.sepa_creditor_identifier):
            self.raise_user_error('invalid_creditor_identifier', {
                    'identifier': self.sepa_creditor_identifier,
                    'party': self.rec_name,
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
            number = _to_base10(vat_code[:2] + '00ZZZ' + vat_code[2:].upper())
            check_sum = mod_97_10.calc_check_digits(number[:-2])
            identifier = Identifier()
            identifier.type = 'sepa'
            identifier.code = (vat_code[:2] + check_sum + 'ZZZ' +
                vat_code[2:].upper())
            identifier.party = party
            identifiers.append(identifier)

        Identifier.save(identifiers)

    def get_sepa_creditor_identifier_used(self, name):
        res = super(Party, self).get_sepa_creditor_identifier_used(name)
        suffix = Transaction().context.get('suffix', None)
        kind = Transaction().context.get('kind', '')
        if res and suffix:
            if kind == 'receivable':
                res = res[:4] + suffix + res[7:]
            else:
                res = res[7:] + suffix
        return res
