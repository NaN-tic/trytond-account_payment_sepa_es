#!/usr/bin/env python3
# This file is part of Tryton.  The COPYRIGHT file at the top level of
# this repository contains the full copyright notices and license terms.
import gettext
import os
import sys
from argparse import ArgumentParser
from datetime import date

try:
    from progressbar import ProgressBar, Bar, ETA, SimpleProgress
except ImportError:
    ProgressBar = None

try:
    from proteus import Model, config
except ImportError:
    prog = os.path.basename(sys.argv[0])
    sys.exit("proteus must be installed to use %s" % prog)

def _progress(iterable):
    if ProgressBar:
        pbar = ProgressBar(
            widgets=[SimpleProgress(), Bar(), ETA()])
    else:
        pbar = iter
    return pbar(iterable)


def create_mandates():
    Mandate = Model.get('account.payment.sepa.mandate')
    BankAccountNumber = Model.get('bank.account.number')

    mandates =dict((x.account_number, x) for x in Mandate.find([]))
    banck_accounts = BankAccountNumber.find([('type', '=', 'iban')])
    for bank_account in _progress(banck_accounts):
        if bank_account in mandates:
            continue
        mandate = Mandate()
        party = bank_account.account.owners and bank_account.account.owners[0]
        mandate.party = party
        mandate.account_number = bank_account
        mandate.type = 'recurrent'
        mandate.sequence_type_rcur = True
        mandate.scheme = 'CORE'
        mandate.state = 'validated'
        mandate.signature_date = date.today().replace(month=1, day=1)
        mandate.save()
        mandate.click('request')
        mandate.click('validate_mandate')



def main(database, config_file=None):
    config.set_trytond(database, config_file=config_file)
    with config.get_config().set_context(active_test=False):
        create_mandates()


def run():
    parser = ArgumentParser()
    parser.add_argument('-d', '--database', dest='database', required=True)
    parser.add_argument('-c', '--config', dest='config_file',
        help='the trytond config file')

    args = parser.parse_args()
    main(args.database, args.config_file)


if __name__ == '__main__':
    run()