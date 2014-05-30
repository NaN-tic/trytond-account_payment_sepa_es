## coding: utf-8
# This file is part of account_payment_sepa_es module for Tryton.
# The COPYRIGHT file at the top level of this repository contains
# the full copyright notices and license terms.
import os
import genshi
import genshi.template
from itertools import groupby
from trytond.model import ModelSingleton, ModelView, ModelSQL, fields
from trytond.pool import Pool, PoolMeta
from trytond.pyson import Eval
from trytond.transaction import Transaction

__all__ = ['Journal', 'Group', 'Payment', 'PayLine', 'Mandate',
    'Configuration', 'CompanyConfiguration']
__metaclass__ = PoolMeta


class Journal:
    __name__ = 'account.payment.journal'

    @classmethod
    def __setup__(cls):
        super(Journal, cls).__setup__()
        cls.party.states.update({
                'required': ~Eval('process_method').in_(['manual', 'sepa_core',
                    'sepa_b2b', 'sepa_trf', 'sepa_chk']),
                })
        cls.bank_account.states.update({
                'required': ~Eval('process_method').in_(['manual', 'sepa_core',
                    'sepa_b2b', 'sepa_trf', 'sepa_chk']),
                'invisible': Eval('process_method').in_(['sepa_core',
                    'sepa_b2b', 'sepa_trf', 'sepa_chk']),
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


loader = genshi.template.TemplateLoader(
    os.path.join(os.path.dirname(__file__), 'template'),
    auto_reload=True)


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

    def __getattribute__(self, name):
        if name == 'payments' and Transaction().context.get('join_payments'):
            cache_name = 'payments_used_cache'
            res = getattr(self, cache_name, None)
            if not res:
                res = self.get_payments_used()
                setattr(self, cache_name, res)
            return res
        return super(Group, self).__getattribute__(name)

    def get_payments_used(self):
        def keyfunc(x):
            return (x.currency, x.party, x.sepa_bank_account_number)

        res = []
        with Transaction().set_context(join_payments=False):
            payments = sorted(self.payments, key=keyfunc)
            for key, grouped in groupby(payments, keyfunc):
                amount = 0
                date = None
                end_to_end_id = ''
                for payment in grouped:
                    amount += payment.amount
                    end_to_end_id += payment.sepa_end_to_end_id + ','
                    if not date or payment.date > date:
                        date = payment.date

                payment.amount = amount
                payment.line = None
                payment.description = end_to_end_id[:-1][:35]
                payment.date = date
                res.append(payment)
        return res

    @property
    def sepa_initiating_party(self):
        return self.journal.party or self.company.party

    def get_sepa_template(self):
        '''Use a different SEPA template to group receivable payments with same
           planned date and same sequence type in mandates'''
        if self.kind == 'payable' or not self.planned_date:
            return super(Group, self).get_sepa_template()
        sequence_type = None
        for payment in self.payments:
            if not sequence_type:
                sequence_type = payment.sepa_mandate.sequence_type
            elif sequence_type != payment.sepa_mandate.sequence_type:
                return super(Group, self).get_sepa_template()      
        return loader.load('%s.xml' % self.journal.sepa_receivable_flavor)

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
        with Transaction().set_context(suffix=self.journal.suffix,
                process_method=self.journal.process_method):
            super(Group, self).process_sepa()


class Payment:
    __name__ = 'account.payment'

    @classmethod
    def __setup__(cls):
        super(Payment, cls).__setup__()
        cls.sepa_mandate.domain.append(('state', '=', 'validated'))
        cls.sepa_mandate.domain.append(
            ('account_number.account', '=', Eval('bank_account'))
            )
        cls.sepa_mandate.depends.append('bank_account')
        cls.sepa_mandate.states.update({
                'readonly': Eval('state') != 'draft',
                })
        if 'state' not in cls.sepa_mandate.depends:
            cls.sepa_mandate.depends.append('state')

    @property
    def sepa_bank_account_number(self):
        if self.bank_account:
            for number in self.bank_account.numbers:
                if number.type == 'iban':
                    return number
        return super(Payment, self).sepa_bank_account_number()


class PayLine:
    __name__ = 'account.move.line.pay'

    def get_payment(self, line):
        payment = super(PayLine, self).get_payment(line)
        if not hasattr(line, 'bank_account'):
            return payment
        if not line.party or not line.bank_account:
            return payment
        for account_number in line.bank_account.numbers:
            if account_number.type == 'iban':
                break
        else:
            return payment
        for mandate in line.party.sepa_mandates:
            if mandate.is_valid and mandate.account_number == account_number:
                payment.sepa_mandate = mandate
                break
        return payment


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
