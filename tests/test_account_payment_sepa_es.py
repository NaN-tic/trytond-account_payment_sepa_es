# This file is part of the account_payment_sepa_es module for Tryton.
# The COPYRIGHT file at the top level of this repository contains the full
# copyright notices and license terms.
import unittest
import trytond.tests.test_tryton
from trytond.pool import Pool
from trytond.transaction import Transaction
from trytond.tests.test_tryton import ModuleTestCase, with_transaction


class AccountPaymentSepaEsTestCase(ModuleTestCase):
    'Test Account Payment Sepa Es module'
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

def suite():
    suite = trytond.tests.test_tryton.suite()
    suite.addTests(unittest.TestLoader().loadTestsFromTestCase(
        AccountPaymentSepaEsTestCase))
    return suite
