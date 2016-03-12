#The COPYRIGHT file at the top level of this repository contains the full
#copyright notices and license terms.
from trytond.pool import PoolMeta
from trytond.model import ModelView
from trytond.pyson import Eval, Bool
from trytond.transaction import Transaction
from stdnum.iso7064 import mod_97_10
#at_02 is pending to be included on python-stdnum.
#See: https://github.com/arthurdejong/python-stdnum/pull/5
from .at_02 import is_valid, _to_base10

__metaclass__ = PoolMeta
__all__ = ['Party']


class Party:
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
                    'invisible': Bool(Eval('sepa_creditor_identifier', False)),
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
        for party in parties:
            if not party.vat_code:
                continue
            number = _to_base10(party.vat_code[:2] + '00ZZZ' +
                party.vat_code[2:].upper())
            check_sum = mod_97_10.calc_check_digits(number[:-2])
            party.sepa_creditor_identifier = (party.vat_code[:2] + check_sum +
                'ZZZ' + party.vat_code[2:].upper())
            party.save()
