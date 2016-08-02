## coding: utf-8
# This file is part of account_payment_sepa_es module for Tryton.
# The COPYRIGHT file at the top level of this repository contains
# the full copyright notices and license terms.
from itertools import groupby
from trytond.pool import Pool, PoolMeta
from trytond.pyson import Eval, If, Bool
from trytond.transaction import Transaction

__all__ = ['Journal', 'Group', 'Payment', 'PayLine', 'Mandate']
__metaclass__ = PoolMeta


class Journal:
    __name__ = 'account.payment.journal'

    @classmethod
    def __register__(cls, module_name):
        cursor = Transaction().cursor
        table = cls.__table__()

        super(Journal, cls).__register__(module_name)

        # Migration from 3.4 Custom process methods removed
        cursor.execute(*table.select(table.process_method,
                where=table.process_method.like('sepa_%')))
        if cursor.fetchone():
            cursor.execute(*table.update(columns=[table.process_method],
                    values=['sepa'],
                    where=table.process_method.like('sepa_%')))

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

    def process_sepa(self):
        pool = Pool()
        Date = pool.get('ir.date')
        today = Date.today()
        # We set context there in order to ensure that the company and the
        # journal party are calculated correctly. As they are cached, they
        # are not properly written in the xml file.
        with Transaction().set_context(suffix=self.journal.suffix,
                kind=self.kind):
            if not self.company.party.sepa_creditor_identifier_used:
                self.raise_user_error('no_creditor_identifier',
                    self.company.party.rec_name)
            if (self.journal.party and not
                    self.journal.party.sepa_creditor_identifier_used):
                self.raise_user_error('no_creditor_identifier',
                    self.journal.party.rec_name)
            for payment in self.payments:
                if payment.date < today:
                    self.raise_user_error('invalid_payment_date',
                        (payment.date, payment.rec_name))
            super(Group, self).process_sepa()


class Payment:
    __name__ = 'account.payment'

    @classmethod
    def __setup__(cls):
        super(Payment, cls).__setup__()
        cls.sepa_mandate.domain.append(('state', '=', 'validated'))
        cls.sepa_mandate.domain.append(
            If(Bool(Eval('bank_account')),
                ('account_number.account', '=', Eval('bank_account')),
                ()),
            )
        cls.sepa_mandate.depends.append('bank_account')
        cls.sepa_mandate.states.update({
                'readonly': Eval('state') != 'draft',
                })
        if 'state' not in cls.sepa_mandate.depends:
            cls.sepa_mandate.depends.append('state')
        cls._error_messages.update({
                'canceled_mandate': ('Payment "%(payment)s" can not be '
                    'modified because its mandate "%(mandate)s" is '
                    'canceled.'),
                'no_mandate_for_party': ('No valid mandate for payment '
                    '"%(payment)s" of party "%(party)s" with amount '
                    '"%(amount)s".'),
                })

    @property
    def sepa_bank_account_number(self):
        if self.bank_account:
            for number in self.bank_account.numbers:
                if number.type == 'iban':
                    return number
        return super(Payment, self).sepa_bank_account_number

    @classmethod
    def write(cls, *args):
        actions = iter(args)
        for payments, _ in zip(actions, actions):
            for payment in payments:
                if (payment.sepa_mandate and
                        payment.sepa_mandate.state == 'canceled'):
                    cls.raise_user_error('canceled_mandate', {
                            'payment': payment.rec_name,
                            'mandate': payment.sepa_mandate.rec_name,
                            })
        return super(Payment, cls).write(*args)

    @classmethod
    def create(cls, vlist):
        pool = Pool()
        Mandate = pool.get('account.payment.sepa.mandate')

        vlist = [v.copy() for v in vlist]
        for values in vlist:
            mandate = values.get('sepa_mandate', None)
            if mandate:
                mandate = Mandate.browse([mandate])[0]
            if not values.get('sepa_mandate_sequence_type') and mandate:
                values['sepa_mandate_sequence_type'] = (mandate.sequence_type
                    or None)
        return super(Payment, cls).create(vlist)

    @classmethod
    def get_sepa_mandates(cls, payments):
        mandates = super(Payment, cls).get_sepa_mandates(payments)
        for payment, mandate in zip(payments, mandates):
            if not mandate:
                cls.raise_user_error('no_mandate_for_party', {
                        'payment': payment.rec_name,
                        'party': payment.party.rec_name,
                        'amount': payment.amount,
                        })
        return mandates


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
                payment.sepa_mandate_sequence_type = mandate.sequence_type
                break
        return payment


class Mandate:
    __name__ = 'account.payment.sepa.mandate'

    @classmethod
    def __setup__(cls):
        super(Mandate, cls).__setup__()
        cls._error_messages.update({
                'cancel_with_processing_payments': ('Mandate "%(mandate)s" can'
                    ' not be canceled because it is linked to payment '
                    '"%(payment)s" which is still in process.'),
                })

    def get_rec_name(self, name):
        return self.identification or unicode(self.id)

    @classmethod
    def search_rec_name(cls, name, clause):
        return [tuple(('identification',)) + tuple(clause[1:])]

    @classmethod
    def cancel(cls, mandates):
        pool = Pool()
        Payment = pool.get('account.payment')
        payments = Payment.search([
                ('state', '=', 'processing'),
                ('sepa_mandate', 'in', [m.id for m in mandates]),
                ], limit=1)
        if payments:
            payment, = payments
            cls.raise_user_error('cancel_with_processing_payments', {
                    'mandate': payment.sepa_mandate.rec_name,
                    'payment': payment.rec_name,
                    })
        super(Mandate, cls).cancel(mandates)
