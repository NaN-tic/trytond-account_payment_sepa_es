# coding: utf-8
# This file is part of account_payment_sepa_es module for Tryton.
# The COPYRIGHT file at the top level of this repository contains
# the full copyright notices and license terms.
import os
import genshi
import datetime
from unidecode import unidecode
from itertools import groupby
from dominate.tags import div, footer as footer_tag, p, section
from trytond.model import fields, dualmethod, ModelView
from trytond.pool import Pool, PoolMeta
from trytond.pyson import Eval, If, Bool, Id
from trytond.transaction import Transaction
from trytond.i18n import gettext
from trytond.exceptions import UserError
from trytond.modules.account_payment_sepa.payment import remove_comment
from trytond.modules.html_report.dominate_report import DominateReport
from trytond.modules.html_report.i18n import _
from trytond.tools import file_open

def normalize_text(text):
    # Function create becasuse not all Banks accept the same chars
    # so it's needed to 'normalize' the textto be accepted
    return unidecode(text).replace('_', '-').replace('(', '').replace(')', '')


class Journal(metaclass=PoolMeta):
    __name__ = 'account.payment.journal'

    core58_sequence = fields.Many2One('ir.sequence', 'SEPA CORE 58 Sequence',
        states={
            'invisible': Eval('process_method') != 'sepa',
            },
        domain=[
            ('sequence_type', '=', Id('account_payment_sepa_es',
                    'sequence_type_account_payment_group_sepa_core58')),
            ])

    @classmethod
    def __register__(cls, module_name):
        cursor = Transaction().connection.cursor()
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


class Group(metaclass=PoolMeta):
    __name__ = 'account.payment.group'

    @classmethod
    def __setup__(cls):
        super(Group, cls).__setup__()
        # set generate message button to invisible when has SEPA messages
        button = cls._buttons.get('sepa_generate_message', {})
        domain = button.get('invisible', {})
        depends = button.get('depends', [])
        depends.append('sepa_messages')
        if button:
            cls._buttons.update({
                    'sepa_generate_message': {
                        'invisible': domain | Eval('sepa_messages'),
                        'depends': depends,
                        },
                    })

    @classmethod
    def create(cls, vlist):
        pool = Pool()
        Journal = pool.get('account.payment.journal')

        vlist = [v.copy() for v in vlist]
        for values in vlist:
            if 'journal' in values:
                journal = Journal(values.get('journal'))
                if (journal and journal.core58_sequence and
                        'number' not in values):
                    values['number'] = journal.core58_sequence.get()

        return super(Group, cls).create(vlist)

    @property
    def sepa_initiating_party(self):
        Party = Pool().get('party.party')
        # reload party to calculate sepa_creditor_identifier_used
        # according to context (suffix & kind)
        party_id = (self.journal.party and self.journal.party.id
            or self.company.party.id)
        return Party(party_id)

    def process_sepa(self):
        Date = Pool().get('ir.date')

        today = Date.today()
        if not self.company.party.sepa_creditor_identifier_used:
            raise UserError(gettext(
                'account_payment_sepa_es.no_creditor_identifier',
                party=self.company.party.rec_name))
        if (self.journal.party and not
                self.journal.party.sepa_creditor_identifier_used):
                raise UserError(gettext(
                    'account_payment_sepa_es.no_creditor_identifier',
                    party=self.journal.party.rec_name))
        for payment in self.payments:
            if payment.date < today:
                raise UserError(gettext(
                    'account_payment_sepa_es.invalid_payment_date',
                    payment_date=payment.date, payment=payment.rec_name))

        super(Group, self).process_sepa()

    @dualmethod
    @ModelView.button
    def sepa_generate_message(cls, groups, _save=True):
        # reload groups to calculate sepa_creditor_identifier_used
        # in company and party according to context (suffix & kind)
        # depend group journal and kind
        # Also set True to save SEPA message related to payment group
        pool = Pool()
        Message = pool.get('account.payment.sepa.message')

        def keyfunc(x):
            return (x.journal.suffix, x.kind)

        groups = sorted(groups, key=keyfunc)
        for key, grouped in groupby(groups, keyfunc):
            grouped_groups = list(grouped)
            group = grouped_groups[0]
            suffix = group.journal.suffix
            kind = group.kind
            with Transaction().set_context(suffix=suffix, kind=kind):
                reload_groups = cls.browse(grouped_groups)
                for group in reload_groups:
                    tmpl = group.get_sepa_template()
                    if not tmpl:
                        raise NotImplementedError
                    if not group.sepa_messages:
                        group.sepa_messages = ()
                    message = tmpl.generate(group=group,
                        datetime=datetime, normalize=normalize_text,
                        ).filter(remove_comment).render().encode('utf8')
                    message = Message(message=message, type='out',
                        state='waiting', company=group.company)
                    group.sepa_messages += (message,)
                    cls.save(reload_groups)

    def get_sepa_template(self):
        if self.process_method != 'sepa':
            return

        loader_es = genshi.template.TemplateLoader(
            os.path.join(os.path.dirname(__file__), 'template'),
            auto_reload=True)
        if (self.kind == 'payable' and
                self.journal.sepa_payable_flavor == 'pain.001.001.03'):
            return loader_es.load('%s.xml' % self.journal.sepa_payable_flavor)
        elif (self.kind == 'receivable' and
                self.journal.sepa_receivable_flavor == 'pain.008.001.02'):
            return loader_es.load(
                '%s.xml' % self.journal.sepa_receivable_flavor)
        else:
            super(Group, self).get_sepa_template()


class ProcessPayment(metaclass=PoolMeta):
    __name__ = 'account.payment.process'

    def do_process(self, action):
        pool = Pool()
        Payment = pool.get('account.payment')

        payments = self.records
        # Before process the payment group check all payments has the correct
        # values and it's domains, like account or Mandate.
        Payment._check_payment(payments)
        return super().do_process(action)


class Payment(metaclass=PoolMeta):
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
        cls.sepa_mandate.depends.add('bank_account')
        cls.sepa_mandate.states.update({
                'readonly': Eval('state') != 'draft',
                })
        if 'state' not in cls.sepa_mandate.depends:
            cls.sepa_mandate.depends.add('state')

    @classmethod
    def join_payment_keyfunc(cls, x):
        # not call super
        return (x.currency, x.party, x.sepa_bank_account_number)

    @property
    def sepa_bank_account_number(self):
        if self.kind == 'receivable' and self.sepa_mandate:
            return self.sepa_mandate.account_number
        elif self.bank_account:
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
                        payment.sepa_mandate.state == 'cancelled'):
                    raise UserError(gettext(
                        'account_payment_sepa_es.canceled_mandate',
                            payment=payment.rec_name,
                            mandate=payment.sepa_mandate.rec_name,
                            ))
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
                raise UserError(gettext(
                    'account_payment_sepa_es.no_mandate_for_party',
                        payment=payment.rec_name,
                        party=payment.party.rec_name,
                        amount=payment.amount))
            elif not payment.bank_account:
                raise UserError(gettext(
                    'account_payment_sepa_es.no_bank_account',
                        payment=payment.rec_name,
                        party=payment.party.rec_name,
                        amount=payment.amount))
            elif mandate.account_number not in payment.bank_account.numbers:
                raise UserError(gettext(
                    'account_payment_sepa_es.'\
                        'bad_relation_mandate_number_vs_bank_account_numbers',
                        mandate=mandate.rec_name,
                        payment=payment.rec_name,
                        party=payment.party.rec_name,
                        amount=payment.amount,
                        bank_account_numbers=("".join(
                                [n.rec_name + " (id: " + str(n.id) + ")"
                                for n in payment.bank_account.numbers]))))
        return mandates

    @property
    def sepa_mandate_required(self):
        if (self.journal.process_method == 'sepa'
                and self.journal.payment_type
                and self.journal.payment_type.kind == 'receivable'
                and self.journal.payment_type.account_bank == 'party'):
            return True
        return False

    @classmethod
    def _check_payment(cls, payments):
        for payment in payments:
            if (payment.journal.payment_type
                    and payment.journal.payment_type.account_bank == 'none'):
                continue

            if (payment.journal.process_method == 'sepa'
                    and not payment.journal.sepa_bank_account_number):
                raise UserError(gettext(
                        'account_payment_sepa_es.msg_missing_sepa_bank_account_number',
                        journal=payment.journal.rec_name,
                        ))

            owners = payment.bank_account and payment.bank_account.owners or []
            if (payment.bank_account is None
                    and payment.journal.payment_type
                    and payment.journal.payment_type.account_bank != 'other'):
                raise UserError(gettext(
                        'account_payment_sepa_es.'
                        'msg_payment_without_bank_account',
                        party=payment.party.rec_name,
                        amount=payment.amount,
                        ))
            elif (payment.journal.payment_type
                    and payment.journal.payment_type.account_bank == 'party'
                    and payment.party not in owners):
                raise UserError(gettext(
                        'account_payment_sepa_es.'
                        'msg_bad_relation_party_bank_account',
                        party=payment.party.rec_name,
                        amount=payment.amount,
                        account=payment.bank_account.rec_name,
                        ))
            elif (payment.journal.payment_type
                    and payment.journal.payment_type.account_bank == 'company'
                    and payment.company.party not in owners):
                raise UserError(gettext(
                        'account_payment_sepa_es.'
                        'msg_bad_relation_party_bank_account',
                        party=payment.company.party.rec_name,
                        amount=payment.amount,
                        account=payment.bank_account.rec_name,
                        ))
            elif (payment.bank_account and payment.journal.payment_type
                    and payment.journal.payment_type.account_bank == 'other'
                    and payment.journal.payment_type.party not in owners):
                raise UserError(gettext(
                        'account_payment_sepa_es.'
                        'msg_bad_relation_party_bank_account',
                        party=payment.journal.payment_type.party.rec_name,
                        amount=payment.amount,
                        account=payment.bank_account.rec_name,
                        ))
            elif (payment.sepa_mandate_required
                    and payment.sepa_mandate is None):
                raise UserError(gettext(
                        'account_payment_sepa_es.msg_payment_without_mandate',
                        party=payment.party.rec_name,
                        amount=payment.amount,
                        account=payment.bank_account.rec_name,
                        ))
            elif (payment.sepa_mandate_required
                    and not payment.sepa_mandate.is_valid):
                raise UserError(gettext(
                        'account_payment_sepa_es.msg_mandate_state_not_valid',
                        party=payment.party.rec_name,
                        amount=payment.amount,
                        account=payment.bank_account.rec_name,
                        mandate=payment.sepa_mandate.rec_name,
                        ))
            elif (payment.sepa_mandate_required
                    and (payment.sepa_mandate.account_number
                        != payment.sepa_bank_account_number)):
                raise UserError(gettext(
                        'account_payment_sepa_es.msg_mandate_not_correct',
                        party=payment.party.rec_name,
                        amount=payment.amount,
                        account=payment.bank_account.rec_name,
                        mandate=payment.sepa_mandate.rec_name,
                        mandate_account=(payment.sepa_mandate.account_number.
                            rec_name),
                        ))


class Mandate(metaclass=PoolMeta):
    __name__ = 'account.payment.sepa.mandate'

    def get_rec_name(self, name):
        return self.identification or str(self.id)

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
            raise UserError(gettext(
                'account_payment_sepa_es.cancel_with_processing_payments',
                    mandate=payment.sepa_mandate.rec_name,
                    payment=payment.rec_name))
        super(Mandate, cls).cancel(mandates)

    @property
    def is_valid(self):
        is_valid = super().is_valid
        if (not self.account_number or not self.account_number.account
                or not self.account_number.account.active):
            return False
        return is_valid


class MandateReport(DominateReport):
    __name__ = 'account.payment.sepa.mandate.report'
    _single = True
    side_margin = 2

    @classmethod
    def css(cls, action, data, records):
        with file_open('account_payment_sepa_es/mandate.css') as f:
            return f.read()

    @classmethod
    def language(cls, records):
        if records:
            record, = records
            lang = record.raw.party.lang.code if record.raw.party.lang else None
            if lang:
                return lang
        return super().language(records)

    @staticmethod
    def _address(party):
        return party and party.addresses and party.addresses[0] or None

    @staticmethod
    def _value(value):
        return '' if value is None else str(value)

    @classmethod
    def _city_line(cls, postal_code, city, state):
        return ' - '.join(x for x in [
                cls._value(postal_code),
                cls._value(city),
                cls._value(state),
                ] if x)

    @classmethod
    def _field(cls, label, value, value_cls='field-value'):
        node = div(cls='field')
        with node:
            div('%s:' % label, cls='field-label')
            div(cls._value(value), cls=value_cls)
        return node

    @classmethod
    def _section_note(cls, text, extra_cls=None):
        css_class = 'section-note'
        if extra_cls:
            css_class = '%s %s' % (css_class, extra_cls)
        return div(text, cls=css_class)

    @classmethod
    def _creditor_message(cls, record):
        message = _(
            'By signing this mandate form, you authorise (A) the Creditor '
            'to send instructions to your bank to debit your account, and '
            '(B) your bank to debit your account in accordance with the '
            'instructions from the Creditor.')
        if record.raw.scheme == 'CORE':
            extra = _(
                'As part of your rights, you are entitled to a refund from '
                'your bank under the terms and conditions of your agreement '
                'with your bank. A refund must be claimed within 8 weeks '
                'starting from the date on which your account was debited. '
                'Your rights regarding this mandate are explained in a '
                'statement that you can obtain from your bank.')
        else:
            extra = _(
                'This mandate is only intended for business-to-business '
                'transactions. You are not entitled to a refund from your '
                'bank after your account has been debited, but you are '
                'entitled to request your bank not to debit your account in '
                'accordance with the instructions up until the day on which '
                'the payment is due. Please contact your bank for detailed '
                'procedures in such a case.')
        return '%s\n\n%s' % (message, extra)

    @classmethod
    def _creditor_box(cls, record):
        company_party = record.raw.company.party
        address = cls._address(company_party)
        tax_identifier = company_party.tax_identifier
        box = div(cls='mandate-box creditor-box')
        with box:
            box.add(cls._field(_('Mandate reference'), record.raw.identification))
            box.add(cls._field(_('Creditor Identifier'),
                    tax_identifier.code if tax_identifier else ''))
            box.add(cls._field(_("Creditor's name"), company_party.name))
            box.add(cls._field(_('Address'),
                    address and address.street or ''))
            box.add(cls._field(
                    '%s - %s - %s' % (_('Postal Code'), _('City'), _('Town')),
                    cls._city_line(address and address.postal_code,
                        address and address.city,
                        address and address.subdivision and
                        address.subdivision.rec_name or '')))
            box.add(cls._field(_('Country'),
                    address and address.country and address.country.rec_name or ''))
            box.add(cls._section_note(_('To be completed by the creditor')))
        return box

    @classmethod
    def _debtor_box(cls, record):
        party = record.raw.party
        address = cls._address(party)
        tax_identifier = party.tax_identifier
        signature_date = (
            record.raw.signature_date.strftime('%d/%m/%Y')
            if record.raw.signature_date else '')
        signature_place = ' - '.join(x for x in [
                signature_date,
                cls._value(address and address.city),
                ] if x)
        payment_type = (_('Recurrent payment')
            if record.raw.type == 'recurrent'
            else _('One-off payment'))

        box = div(cls='mandate-box debtor-box')
        with box:
            box.add(cls._field(_("Debtor's name"), party.name))
            box.add(cls._field(_('Debtor Identifier'),
                    tax_identifier.code if tax_identifier else ''))
            box.add(cls._field(_("Debtor's address"),
                    address and address.street or ''))
            box.add(cls._field(
                    '%s - %s - %s' % (_('Postal Code'), _('City'), _('Town')),
                    cls._city_line(address and address.postal_code,
                        address and address.city,
                        address and address.subdivision and
                        address.subdivision.rec_name or '')))
            box.add(cls._field(_("Debtor's country"),
                    address and address.country and address.country.rec_name or ''))
            box.add(cls._field(_('Swift BIC'),
                    record.raw.account_number.account.bank.bic
                    if (record.raw.account_number
                        and record.raw.account_number.account
                        and record.raw.account_number.account.bank) else ''))
            box.add(cls._field('%s - %s' % (_('Accont number'), _('IBAN')),
                    record.raw.account_number.rec_name if record.raw.account_number else ''))
            box.add(cls._field(_('Type of payment'),
                    payment_type, value_cls='field-value payment-type'))

            box.add(cls._field(
                    '%s - %s' % (_('Date'),
                        _('Location in which you are signing')),
                    signature_place))
            box.add(cls._field(_("Debtor's signature"), ''))
            box.add(cls._section_note(
                    _('To be completed by the debtor'),
                    extra_cls='debtor-section-note'))
        return box

    @classmethod
    def body(cls, action, data, records):
        container = div()
        for record in records:
            title = _('SEPA Direct Debit Mandate')
            if record.raw.scheme != 'CORE':
                title = '%s B2B' % title
            title_node = div(title, cls='mandate-title')
            creditor_box = cls._creditor_box(record)
            message_node = p(cls._creditor_message(record), cls='message-box')
            debtor_box = cls._debtor_box(record)
            page = section(cls='mandate-page')
            page.add(title_node)
            page.add(creditor_box)
            page.add(message_node)
            page.add(debtor_box)
            container.add(page)
        return container

    @classmethod
    def header(cls, action, data, records):
        pass

    @classmethod
    def footer(cls, action, data, records):
        footer = div()
        with footer:
            with footer_tag(id='footer', align='center'):
                p(_('ONCE THIS MANDATE HAS BEEN SIGNED MUST BE SENT TO '
                'CREDITOR FOR STORAGE'))
        return footer


class Message(metaclass=PoolMeta):
    __name__ = 'account.payment.sepa.message'
    group_number = fields.Function(fields.Char('Number'), 'get_group_field')
    group_planned_date = fields.Function(
        fields.Date('Planned Date'), 'get_group_field')
    group_amount = fields.Function(fields.Numeric('Amount'), 'get_group_field')

    def get_group_field(self, name):
        if (not self.origin or isinstance(self.origin, str)
                or (self.origin.__name__ != 'account.payment.group')):
            return
        if name == 'group_amount':
            return getattr(self.origin, 'payment_amount')
        else:
            return getattr(self.origin, name[6:])
