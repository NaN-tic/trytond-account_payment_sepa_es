## coding: utf-8
# This file is part of account_payment_sepa_es module for Tryton.
# The COPYRIGHT file at the top level of this repository contains
# the full copyright notices and license terms.
from trytond.model import ModelSingleton, ModelView, ModelSQL, fields
from trytond.pool import Pool, PoolMeta
from trytond.pyson import Eval
from trytond.transaction import Transaction

__all__ = ['Journal', 'Group', 'Payment', 'Mandate', 'Configuration',
    'CompanyConfiguration']
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
                'invalid_payment_date': ('Invalid payment date %s for payment'
                    ' "%s". Payment\'s date must be greather or equal than '
                    'today.'),
                })

    @property
    def sepa_initiating_party(self):
        return self.journal.party or self.company.party

    def process_sepa(self):
        pool = Pool()
        Date = pool.get('ir.date')
        today = Date.today()
        if not self.company.party.sepa_creditor_identifier:
            self.raise_user_error('no_creditor_identifier',
                self.company.party.rec_name)
        if (self.journal.party and not
                self.journal.party.sepa_creditor_identifier):
            self.raise_user_error('no_creditor_identifier',
                self.journal.party.rec_name)
        for payment in self.payments:
            if payment.date < today:
                self.raise_user_error('invalid_payment_date', (payment.date,
                        payment.rec_name))
        with Transaction().set_context(suffix=self.journal.suffix):
            super(Group, self).process_sepa()


class Payment:
    __name__ = 'account.payment'

    @classmethod
    def __setup__(cls):
        super(Payment, cls).__setup__()
        if 'state' not in cls.sepa_mandate.depends:
            cls.sepa_mandate.depends.append('state')
        cls.sepa_mandate.states.update({
                'readonly': ~Eval('state').in_(['draft', 'approved']),
                'invisible': Eval('state').in_(['draft', 'approved']),
                })


class Mandate:
    __name__ = 'account.payment.sepa.mandate'

    @classmethod
    def request(cls, mandates):
        pool = Pool()
        Sequence = pool.get('ir.sequence')
        Config = pool.get('account.payment.sepa.configuration')

        super(Mandate, cls).request(mandates)
        config = Config(1)
        if not config.mandate_sequence:
            return
        for mandate in mandates:
            if mandate.identification:
                continue
            identification = Sequence.get_id(config.mandate_sequence.id)
            cls.write([mandate], {
                    'identification': identification,
                    })


class CompanyConfiguration(ModelSQL):
    'Mandate Company Configuration'
    __name__ = 'account.payment.sepa.configuration.company'

    company = fields.Many2One('company.company', 'Company', required=True)
    mandate_sequence = fields.Many2One('ir.sequence', 'Mandate Sequence',
        domain=[
            ('code', '=', 'account.payment.sepa.mandate'),
            ('company', 'in',
                [Eval('context', {}).get('company', -1), None]),
            ],
        required=True)

    @staticmethod
    def default_company():
        return Transaction().context.get('company')


class Configuration(ModelSingleton, ModelSQL, ModelView):
    'Mandate Configuration'
    __name__ = 'account.payment.sepa.configuration'

    mandate_sequence = fields.Function(fields.Many2One('ir.sequence',
            'Mandate Sequence', domain=[
                ('code', '=', 'account.payment.sepa.mandate'),
                ('company', 'in',
                    [Eval('context', {}).get('company', -1), None]),
                ],
        required=True), 'get_configuration', setter='set_configuration')

    @classmethod
    def get_configuration(self, configs, names):
        pool = Pool()
        CompanyConfig = pool.get('account.payment.sepa.configuration.company')
        res = dict.fromkeys(names, [configs[0].id, None])
        company_configs = CompanyConfig.search([], limit=1)
        if len(company_configs) == 1:
            company_config, = company_configs
            for field_name in set(names):
                value = getattr(company_config, field_name, None)
                if value:
                    res[field_name] = {configs[0].id: value.id}
        return res

    @classmethod
    def set_configuration(self, configs, name, value):
        pool = Pool()
        CompanyConfig = pool.get('account.payment.sepa.configuration.company')
        company_configs = CompanyConfig.search([], limit=1)
        if len(company_configs) == 1:
            company_config, = company_configs
        else:
            company_config = CompanyConfig()
            setattr(company_config, name, value)
            company_config.save()
