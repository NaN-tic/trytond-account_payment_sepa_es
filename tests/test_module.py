
# This file is part of Tryton.  The COPYRIGHT file at the top level of
# this repository contains the full copyright notices and license terms.

from decimal import Decimal

from trytond.modules.account_payment_sepa.tests.test_module import (
    setup_accounts, setup_environment, setup_mandate)
from trytond.modules.company.tests import CompanyTestMixin, set_company
from trytond.pool import Pool
from trytond.tests.test_tryton import ModuleTestCase, with_transaction
from trytond.transaction import Transaction, check_access


class AccountPaymentSepaEsTestCase(CompanyTestMixin, ModuleTestCase):
    'Test AccountPaymentSepaEs module'
    module = 'account_payment_sepa_es'

    @with_transaction()
    def test_sepa_identifier(self):
        'Test sepa indentifier validation'
        pool = Pool()
        Party = pool.get('party.party')
        Identifier = pool.get('party.identifier')

        party = Party(name='test')
        party.save()
        Party.calculate_sepa_creditor_identifier([party])
        self.assertIsNone(party.sepa_creditor_identifier_used)
        sepa = Identifier(party=party, code='ES47690558N', type='eu_at_02')
        sepa.save()
        Party.calculate_sepa_creditor_identifier([party])
        self.assertEqual(party.sepa_creditor_identifier_used,
            'ES47690558N')

    @with_transaction()
    def test_sepa_identifier_used(self):
        'Test sepa creditor identifier used'
        pool = Pool()
        Party = pool.get('party.party')
        Identifier = pool.get('party.identifier')

        party = Party(name='test')
        party.save()
        sepa = Identifier(party=party, code='ES23ZZZ47690558N', type='eu_at_02')
        sepa.save()
        self.assertEqual(party.sepa_creditor_identifier_used,
            'ES23ZZZ47690558N')
        with Transaction().set_context(kind='receivable', suffix='001'):
            party = Party(party.id)
            self.assertEqual(party.sepa_creditor_identifier_used,
                'ES2300147690558N')
        with Transaction().set_context(kind='payable', suffix='001'):
            party = Party(party.id)
            self.assertEqual(party.sepa_creditor_identifier_used,
                '47690558N001')

    @with_transaction()
    def test_payment_copy(self):
        'Test copy payment with SEPA mandate'
        pool = Pool()
        Date = pool.get('ir.date')
        Payment = pool.get('account.payment')
        PaymentJournal = pool.get('account.payment.journal')
        PaymentType = pool.get('account.payment.type')

        environment = setup_environment()
        company = environment['company']
        bank = environment['bank']
        customer = environment['customer']

        with set_company(company):
            company_account, customer_account = setup_accounts(
                bank, company, customer)
            mandate = setup_mandate(company, customer, customer_account)
            payment_type = PaymentType(
                name='SEPA Receivable', kind='receivable', company=company,
                account_bank='party')
            payment_type.save()
            journal = PaymentJournal(
                name='pain.008.001.02', company=company,
                currency=company.currency, process_method='sepa',
                payment_type=payment_type,
                sepa_bank_account_number=company_account.numbers[0],
                sepa_payable_flavor='pain.001.001.03',
                sepa_receivable_flavor='pain.008.001.02')
            journal.save()
            payment, = Payment.create([{
                        'company': company,
                        'party': customer,
                        'journal': journal,
                        'kind': 'receivable',
                        'amount': Decimal('1000.0'),
                        'state': 'submitted',
                        'reference': 'PAYMENT',
                        'date': Date.today(),
                        'sepa_mandate': mandate,
                        }])

            self.assertEqual(payment.sepa_mandate_sequence_type, 'FRST')

            with check_access():
                copied_payment, = Payment.copy([payment])

            self.assertNotEqual(copied_payment.number, payment.number)
            self.assertEqual(copied_payment.state, 'draft')
            self.assertEqual(copied_payment.sepa_mandate, mandate)
            self.assertEqual(
                copied_payment.sepa_mandate_sequence_type, 'RCUR')

    @with_transaction()
    def test_sepa_mandate_report_execute(self):
        'Test sepa mandate dominate report'
        pool = Pool()
        Report = pool.get('account.payment.sepa.mandate.report', type='report')

        environment = setup_environment()
        company = environment['company']
        bank = environment['bank']
        customer = environment['customer']

        with set_company(company):
            _, customer_account = setup_accounts(bank, company, customer)
            mandate = setup_mandate(company, customer, customer_account)

            oext, content, _, _ = Report.execute([mandate.id], {})

            self.assertEqual(oext, 'pdf')
            self.assertTrue(content)


del ModuleTestCase
