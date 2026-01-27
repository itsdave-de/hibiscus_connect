# Copyright (c) 2025, itsdave GmbH and contributors
# For license information, please see license.txt

"""
ISO 20022 camt.053 (Bank to Customer Statement) Generator

This module generates XML files conforming to the camt.053.001.08 standard
for end-of-day bank account statements.
"""

from pyiso20022.camt import camt_053_001_08 as camt053
from xsdata.formats.dataclass.serializers import XmlSerializer
from xsdata.formats.dataclass.serializers.config import SerializerConfig
from xsdata.models.datatype import XmlDate, XmlDateTime
from decimal import Decimal
from frappe.utils import getdate, now_datetime


# Namespace map for camt.053.001.08 (default namespace without prefix)
CAMT053_NS_MAP = {
    None: "urn:iso:std:iso:20022:tech:xsd:camt.053.001.08",
    "xsi": "http://www.w3.org/2001/XMLSchema-instance"
}


def generate_camt053(bank_account, transactions, opening_balance, closing_balance,
                     from_date, to_date, statement_id):
    """
    Generate a camt.053.001.08 XML document.

    Args:
        bank_account: Hibiscus Connect Bank Account document
        transactions: List of Hibiscus Connect Transaction documents
        opening_balance: Opening balance as float
        closing_balance: Closing balance as float
        from_date: Start date of the statement period
        to_date: End date of the statement period
        statement_id: Unique statement identifier

    Returns:
        str: XML content as string
    """
    # Format dates
    creation_dt = _format_datetime(now_datetime())
    from_date_str = _format_date(from_date)
    to_date_str = _format_date(to_date)

    # Group Header
    grp_hdr = camt053.GroupHeader81(
        msg_id=f"{statement_id}",
        cre_dt_tm=XmlDateTime.from_string(creation_dt)
    )

    # Account
    acct = _create_account(bank_account)

    # Balances (OPBD = Opening Booked, CLBD = Closing Booked)
    balances = [
        _create_balance("OPBD", opening_balance,
                       bank_account.currency or "EUR", from_date_str),
        _create_balance("CLBD", closing_balance,
                       bank_account.currency or "EUR", to_date_str)
    ]

    # Transaction Summary
    tx_summry = _create_transaction_summary(transactions)

    # Entries
    entries = [_create_entry(trans, bank_account) for trans in transactions]

    # Statement
    stmt = camt053.AccountStatement9(
        id=statement_id,
        elctrnc_seq_nb=Decimal("1"),
        cre_dt_tm=XmlDateTime.from_string(creation_dt),
        acct=acct,
        bal=balances,
        txs_summry=tx_summry,
        ntry=entries if entries else None
    )

    # Document
    doc = camt053.Document(
        bk_to_cstmr_stmt=camt053.BankToCustomerStatementV08(
            grp_hdr=grp_hdr,
            stmt=[stmt]
        )
    )

    # Serialize to XML
    config = SerializerConfig(
        pretty_print=True,
        xml_declaration=True,
        encoding="UTF-8"
    )
    serializer = XmlSerializer(config=config)

    return serializer.render(doc, ns_map=CAMT053_NS_MAP)


def _create_account(bank_account):
    """Create the Account (Acct) element."""
    # Account identification
    if bank_account.iban:
        acct_id = camt053.AccountIdentification4Choice(iban=bank_account.iban)
    else:
        acct_id = camt053.AccountIdentification4Choice(
            othr=camt053.GenericAccountIdentification1(
                id=bank_account.account_number or bank_account.name
            )
        )

    # Account Owner
    ownr = None
    if bank_account.account_holder:
        ownr = camt053.PartyIdentification135(nm=bank_account.account_holder)

    # Servicer (Bank)
    svcr = None
    if bank_account.bic:
        svcr = camt053.BranchAndFinancialInstitutionIdentification6(
            fin_instn_id=camt053.FinancialInstitutionIdentification18(
                bicfi=bank_account.bic
            )
        )

    return camt053.CashAccount39(
        id=acct_id,
        ccy=bank_account.currency or "EUR",
        nm=bank_account.description or bank_account.account_name_from_bank,
        ownr=ownr,
        svcr=svcr
    )


def _create_balance(balance_type, amount, currency, date_str):
    """Create a Balance (Bal) element."""
    return camt053.CashBalance8(
        tp=camt053.BalanceType13(
            cd_or_prtry=camt053.BalanceType10Choice(cd=balance_type)
        ),
        amt=camt053.ActiveOrHistoricCurrencyAndAmount(
            value=Decimal(str(abs(amount))).quantize(Decimal("0.01")),
            ccy=currency
        ),
        cdt_dbt_ind=camt053.CreditDebitCode.CRDT if amount >= 0 else camt053.CreditDebitCode.DBIT,
        dt=camt053.DateAndDateTime2Choice(dt=XmlDate.from_string(date_str))
    )


def _create_transaction_summary(transactions):
    """Create the Transaction Summary (TxsSummry) element."""
    if not transactions:
        return None

    # Calculate summary
    credit_count = sum(1 for t in transactions if t.amount > 0)
    debit_count = sum(1 for t in transactions if t.amount < 0)
    total_credits = sum(t.amount for t in transactions if t.amount > 0)
    total_debits = sum(abs(t.amount) for t in transactions if t.amount < 0)

    # Total entries
    ttl_ntries = camt053.NumberAndSumOfTransactions4(
        nb_of_ntries=str(len(transactions))
    )

    # Credit entries
    ttl_cdt_ntries = None
    if credit_count > 0:
        ttl_cdt_ntries = camt053.NumberAndSumOfTransactions1(
            nb_of_ntries=str(credit_count),
            sum=Decimal(str(total_credits)).quantize(Decimal("0.01"))
        )

    # Debit entries
    ttl_dbt_ntries = None
    if debit_count > 0:
        ttl_dbt_ntries = camt053.NumberAndSumOfTransactions1(
            nb_of_ntries=str(debit_count),
            sum=Decimal(str(total_debits)).quantize(Decimal("0.01"))
        )

    return camt053.TotalTransactions6(
        ttl_ntries=ttl_ntries,
        ttl_cdt_ntries=ttl_cdt_ntries,
        ttl_dbt_ntries=ttl_dbt_ntries
    )


def _create_entry(transaction, bank_account):
    """Create an Entry (Ntry) element for a transaction."""
    amount = float(transaction.amount)
    currency = bank_account.currency or "EUR"

    # Transaction date
    tx_date_str = _format_date(transaction.transaction_date)
    val_date_str = _format_date(transaction.value_date or transaction.transaction_date)

    # Entry reference
    ntry_ref = str(transaction.get('hibiscus_id')) if transaction.get('hibiscus_id') else None

    # Bank transaction code
    bk_tx_cd = camt053.BankTransactionCodeStructure4(
        prtry=camt053.ProprietaryBankTransactionCodeStructure1(
            cd=_sanitize_text(transaction.get('gvcode') or transaction.get('transaction_type') or "NTAV", 35)
        )
    )

    # Transaction details
    tx_dtls = _create_transaction_details(transaction, bank_account, amount > 0)

    # Status
    sts = camt053.EntryStatus1Choice(cd="BOOK")

    # Entry
    return camt053.ReportEntry10(
        ntry_ref=ntry_ref,
        amt=camt053.ActiveOrHistoricCurrencyAndAmount(
            value=Decimal(str(abs(amount))).quantize(Decimal("0.01")),
            ccy=currency
        ),
        cdt_dbt_ind=camt053.CreditDebitCode.CRDT if amount > 0 else camt053.CreditDebitCode.DBIT,
        sts=sts,
        bookg_dt=camt053.DateAndDateTime2Choice(dt=XmlDate.from_string(tx_date_str)),
        val_dt=camt053.DateAndDateTime2Choice(dt=XmlDate.from_string(val_date_str)),
        bk_tx_cd=bk_tx_cd,
        ntry_dtls=[camt053.EntryDetails9(tx_dtls=[tx_dtls])] if tx_dtls else None
    )


def _create_transaction_details(transaction, bank_account, is_credit):
    """Create TransactionDetails (TxDtls) element."""
    # References - use end_to_end_id field (SEPA reference) if available
    refs = camt053.TransactionReferences6()

    end_to_end_id = transaction.get('end_to_end_id') or ""
    if not end_to_end_id or end_to_end_id == "NOTPROVIDED":
        # Fall back to customer_ref if no end_to_end_id
        end_to_end_id = transaction.get('customer_ref') or "NOTPROVIDED"

    refs.end_to_end_id = _sanitize_text(end_to_end_id, 35)

    if transaction.get('primanota'):
        refs.prtry = [camt053.ProprietaryReference1(
            tp="PRIM",
            ref=transaction.primanota
        )]

    # Related parties
    rltd_pties = _create_related_parties(transaction, is_credit)

    # Related agents (counterparty bank)
    rltd_agts = None
    if transaction.get('counterparty_bic'):
        fin_instn = camt053.BranchAndFinancialInstitutionIdentification6(
            fin_instn_id=camt053.FinancialInstitutionIdentification18(
                bicfi=transaction.counterparty_bic
            )
        )
        if is_credit:
            rltd_agts = camt053.TransactionAgents5(dbtr_agt=fin_instn)
        else:
            rltd_agts = camt053.TransactionAgents5(cdtr_agt=fin_instn)

    # Remittance information (purpose)
    rmt_inf = None
    if transaction.get('purpose'):
        # Split purpose into lines of max 140 chars
        purpose = _sanitize_text(transaction.purpose, 560)
        ustrd_lines = [purpose[i:i+140] for i in range(0, len(purpose), 140)]
        rmt_inf = camt053.RemittanceInformation16(ustrd=ustrd_lines)

    return camt053.EntryTransaction10(
        refs=refs,
        rltd_pties=rltd_pties,
        rltd_agts=rltd_agts,
        rmt_inf=rmt_inf
    )


def _create_related_parties(transaction, is_credit):
    """Create RelatedParties (RltdPties) element."""
    if not transaction.get('counterparty_name') and not transaction.get('counterparty_iban'):
        return None

    # Counterparty account
    counterparty_acct = None
    if transaction.get('counterparty_iban'):
        counterparty_acct = camt053.CashAccount38(
            id=camt053.AccountIdentification4Choice(iban=transaction.counterparty_iban)
        )

    if is_credit:
        # Credit: counterparty is debtor
        return camt053.TransactionParties6(
            dbtr=camt053.Party40Choice(
                pty=camt053.PartyIdentification135(
                    nm=_sanitize_text(transaction.get('counterparty_name'), 140)
                )
            ) if transaction.get('counterparty_name') else None,
            dbtr_acct=counterparty_acct
        )
    else:
        # Debit: counterparty is creditor
        return camt053.TransactionParties6(
            cdtr=camt053.Party40Choice(
                pty=camt053.PartyIdentification135(
                    nm=_sanitize_text(transaction.get('counterparty_name'), 140)
                )
            ) if transaction.get('counterparty_name') else None,
            cdtr_acct=counterparty_acct
        )


def _format_date(date_val):
    """Format a date as YYYY-MM-DD string."""
    if isinstance(date_val, str):
        date_val = getdate(date_val)
    return date_val.strftime("%Y-%m-%d")


def _format_datetime(dt_val):
    """Format a datetime as ISO 8601 string."""
    if isinstance(dt_val, str):
        from datetime import datetime
        dt_val = datetime.fromisoformat(dt_val)
    return dt_val.strftime("%Y-%m-%dT%H:%M:%S")


def _sanitize_text(text, max_length=None):
    """Sanitize text for XML - remove invalid characters and truncate if needed."""
    if not text:
        return None

    # Remove control characters and normalize whitespace
    text = ''.join(c if c.isprintable() or c in '\n\r\t' else ' ' for c in str(text))
    text = ' '.join(text.split())  # Normalize whitespace

    if max_length and len(text) > max_length:
        text = text[:max_length]

    return text if text else None
