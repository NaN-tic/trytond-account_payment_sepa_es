## coding: utf-8
# This file is part of account_payment_sepa_es module for Tryton.
# The COPYRIGHT file at the top level of this repository contains
# the full copyright notices and license terms.
from trytond.pool import PoolMeta
from trytond.pyson import Eval

__all__ = ['Journal', 'Group']
__metaclass__ = PoolMeta


class Journal:
    __name__ = 'account.payment.journal'

    @classmethod
    def __setup__(cls):
        super(Journal, cls).__setup__()
        cls.party.states.update({
                'required': ~Eval('process_method').in_(['manual', 'sepa']),
                })
        cls.bank_account.states.update({
                'required': ~Eval('process_method').in_(['manual', 'sepa']),
                'invisible': Eval('process_method') == 'sepa',
                })

    @staticmethod
    def default_suffix():
        return '000'

    @staticmethod
    def default_sepa_payable_flavor():
        return 'pain.001.001.03'

    @staticmethod
    def default_sepa_receivable_flavor():
        return 'pain.008.001.02'


class Group:
    __name__ = 'account.payment.group'

    @classmethod
    def __setup__(cls):
        super(Group, cls).__setup__()
        cls._error_messages.update({
                'no_creditor_identifier': ('No creditor identifier for party'
                    ' "%s".'),
                })

    @property
    def sepa_initiating_party(self):
        return self.journal.party or self.company.party

    def process_sepa(self):
        if not self.company.party.sepa_creditor_identifier:
            self.raise_user_error('no_creditor_identifier',
                self.company.party.rec_name)
        if (self.journal.party and not
                self.journal.party.sepa_creditor_identifier):
            self.raise_user_error('no_creditor_identifier',
                self.journal.party.rec_name)
        super(Group, self).process_sepa()
