# Copyright (c) 2025, itsdave GmbH and contributors
# For license information, please see license.txt

"""
ISO 20022 camt.052 (Bank to Customer Account Report) Generator

This module generates XML files conforming to the camt.052.001.02 standard
for intraday bank account reports. This format is compatible with Proficash
and other German banking software.
"""

import re

from pyiso20022.camt import camt_052_001_02 as camt052
from xsdata.formats.dataclass.serializers import XmlSerializer
from xsdata.formats.dataclass.serializers.config import SerializerConfig
from xsdata.models.datatype import XmlDate, XmlDateTime
from decimal import Decimal
from frappe.utils import getdate, now_datetime
import frappe


# Namespace map for camt.052.001.02 (default namespace without prefix)
CAMT052_NS_MAP = {
    None: "urn:iso:std:iso:20022:tech:xsd:camt.052.001.02",
    "xsi": "http://www.w3.org/2001/XMLSchema-instance"
}

# Schema location for camt.052.001.02
CAMT052_SCHEMA_LOCATION = "urn:iso:std:iso:20022:tech:xsd:camt.052.001.02 camt.052.001.02.xsd"


def generate_camt052(bank_account, transactions, opening_balance, closing_balance,
                     from_date, to_date, statement_id):
    """
    Generate a camt.052.001.02 XML document.

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
    grp_hdr = camt052.GroupHeader42(
        msg_id=f"{statement_id}",
        cre_dt_tm=XmlDateTime.from_string(creation_dt),
        msg_pgntn=camt052.Pagination(
            pg_nb="1",
            last_pg_ind=True
        )
    )

    # Account
    acct = _create_account(bank_account)

    # Balances
    balances = [
        _create_balance(camt052.BalanceType12Code.PRCD, opening_balance,
                       bank_account.currency or "EUR", from_date_str),
        _create_balance(camt052.BalanceType12Code.CLBD, closing_balance,
                       bank_account.currency or "EUR", to_date_str)
    ]

    # Entries
    entries = [_create_entry(trans, bank_account) for trans in transactions]

    # Report
    rpt = camt052.AccountReport11(
        id=statement_id,
        elctrnc_seq_nb=Decimal("0"),
        cre_dt_tm=XmlDateTime.from_string(creation_dt),
        acct=acct,
        bal=balances,
        ntry=entries if entries else None
    )

    # Document
    doc = camt052.Document(
        bk_to_cstmr_acct_rpt=camt052.BankToCustomerAccountReportV02(
            grp_hdr=grp_hdr,
            rpt=[rpt]
        )
    )

    # Serialize to XML (compact format like Proficash)
    config = SerializerConfig(
        pretty_print=False,
        xml_declaration=True,
        encoding="UTF-8",
        schema_location=CAMT052_SCHEMA_LOCATION
    )
    serializer = XmlSerializer(config=config)

    return serializer.render(doc, ns_map=CAMT052_NS_MAP)


def _create_account(bank_account):
    """Create the Account (Acct) element."""
    # Account identification
    if bank_account.iban:
        acct_id = camt052.AccountIdentification4Choice(iban=bank_account.iban)
    else:
        acct_id = camt052.AccountIdentification4Choice(
            othr=camt052.GenericAccountIdentification1(
                id=bank_account.account_number or bank_account.name
            )
        )

    # Servicer (Bank)
    svcr = None
    if bank_account.bic:
        svcr = camt052.BranchAndFinancialInstitutionIdentification4(
            fin_instn_id=camt052.FinancialInstitutionIdentification7(
                bic=bank_account.bic
            )
        )

    return camt052.CashAccount20(
        id=acct_id,
        ccy=bank_account.currency or "EUR",
        svcr=svcr
    )


def _create_balance(balance_type, amount, currency, date_str):
    """Create a Balance (Bal) element."""
    return camt052.CashBalance3(
        tp=camt052.BalanceType12(
            cd_or_prtry=camt052.BalanceType5Choice(cd=balance_type)
        ),
        amt=camt052.ActiveOrHistoricCurrencyAndAmount(
            value=Decimal(str(abs(amount))).quantize(Decimal("0.01")),
            ccy=currency
        ),
        cdt_dbt_ind=camt052.CreditDebitCode.CRDT if amount >= 0 else camt052.CreditDebitCode.DBIT,
        dt=camt052.DateAndDateTimeChoice(dt=XmlDate.from_string(date_str))
    )


def _create_entry(transaction, bank_account):
    """Create an Entry (Ntry) element for a transaction."""
    amount = float(transaction.amount)
    currency = bank_account.currency or "EUR"

    # Transaction date
    tx_date_str = _format_date(transaction.transaction_date)
    val_date_str = _format_date(transaction.value_date or transaction.transaction_date)

    # Transaction details
    tx_dtls = _create_transaction_details(transaction, bank_account, amount > 0)

    # Entry
    return camt052.ReportEntry2(
        amt=camt052.ActiveOrHistoricCurrencyAndAmount(
            value=Decimal(str(abs(amount))).quantize(Decimal("0.01")),
            ccy=currency
        ),
        cdt_dbt_ind=camt052.CreditDebitCode.CRDT if amount > 0 else camt052.CreditDebitCode.DBIT,
        sts=camt052.EntryStatus2Code.BOOK,
        bookg_dt=camt052.DateAndDateTimeChoice(dt=XmlDate.from_string(tx_date_str)),
        val_dt=camt052.DateAndDateTimeChoice(dt=XmlDate.from_string(val_date_str)),
        acct_svcr_ref=transaction.get('customer_ref') or transaction.get('hibiscus_id'),
        bk_tx_cd=camt052.BankTransactionCodeStructure4(),  # Empty as in Proficash
        ntry_dtls=[camt052.EntryDetails1(tx_dtls=[tx_dtls])] if tx_dtls else None,
        addtl_ntry_inf=_sanitize_text(transaction.get('transaction_type') or transaction.get('gvcode'), 500)
    )


def _create_transaction_details(transaction, bank_account, is_credit):
    """Create TransactionDetails (TxDtls) element."""
    # Get End-to-End ID directly from transaction field (preferred)
    # Fall back to extracting from purpose if not available
    end_to_end_id = transaction.get('end_to_end_id') or ""

    if not end_to_end_id or end_to_end_id == "NOTPROVIDED":
        # Try to extract from purpose as fallback
        purpose = transaction.get('purpose') or ""
        if purpose:
            match = re.search(r'EREF[:\s]+(\S+)', purpose)
            if match:
                end_to_end_id = match.group(1)

    # Default to NOTPROVIDED if still empty
    if not end_to_end_id:
        end_to_end_id = "NOTPROVIDED"

    # References
    refs = camt052.TransactionReferences2(
        end_to_end_id=end_to_end_id
    )

    # Bank transaction code (proprietary)
    # First try to get GVCode from transaction, then look up from mapping
    gvcode = transaction.get('gvcode') or ""
    primanota = transaction.get('primanota') or ""
    transaction_type = transaction.get('transaction_type') or ""

    # If no GVCode in transaction, try to look it up from mapping
    if not gvcode and primanota and transaction_type:
        gvcode = _lookup_gvcode(bank_account.bic, transaction_type, primanota) or ""

    prtry_cd = f"NTRF+{primanota}+{gvcode}" if primanota or gvcode else None

    bk_tx_cd = None
    if prtry_cd:
        bk_tx_cd = camt052.BankTransactionCodeStructure4(
            prtry=camt052.ProprietaryBankTransactionCodeStructure1(
                cd=prtry_cd,
                issr="DK"  # Germany
            )
        )

    # Related parties
    rltd_pties = _create_related_parties(transaction, bank_account, is_credit)

    # Related agents (counterparty bank)
    rltd_agts = None
    if transaction.get('counterparty_bic'):
        if is_credit:
            rltd_agts = camt052.TransactionAgents2(
                dbtr_agt=camt052.BranchAndFinancialInstitutionIdentification4(
                    fin_instn_id=camt052.FinancialInstitutionIdentification7(
                        bic=transaction.counterparty_bic
                    )
                )
            )
        else:
            rltd_agts = camt052.TransactionAgents2(
                cdtr_agt=camt052.BranchAndFinancialInstitutionIdentification4(
                    fin_instn_id=camt052.FinancialInstitutionIdentification7(
                        bic=transaction.counterparty_bic
                    )
                )
            )

    # Remittance information (purpose)
    rmt_inf = None
    if transaction.get('purpose'):
        # Split purpose into lines of max 140 chars
        purpose = _sanitize_text(transaction.purpose, 560)
        ustrd_lines = [purpose[i:i+140] for i in range(0, len(purpose), 140)]
        rmt_inf = camt052.RemittanceInformation5(ustrd=ustrd_lines)

    return camt052.EntryTransaction2(
        refs=refs,
        bk_tx_cd=bk_tx_cd,
        rltd_pties=rltd_pties,
        rltd_agts=rltd_agts,
        rmt_inf=rmt_inf
    )


def _create_related_parties(transaction, bank_account, is_credit):
    """Create RelatedParties (RltdPties) element."""
    if not transaction.get('counterparty_name') and not transaction.get('counterparty_iban'):
        return None

    # Counterparty account
    counterparty_acct = None
    if transaction.get('counterparty_iban'):
        counterparty_acct = camt052.CashAccount16(
            id=camt052.AccountIdentification4Choice(iban=transaction.counterparty_iban)
        )

    # Own account
    own_acct = None
    if bank_account.iban:
        own_acct = camt052.CashAccount16(
            id=camt052.AccountIdentification4Choice(iban=bank_account.iban)
        )

    # Own name
    own_name = bank_account.account_holder or bank_account.description or "Account Holder"

    if is_credit:
        # Credit: counterparty is debtor, we are creditor
        return camt052.TransactionParty2(
            dbtr=camt052.PartyIdentification32(
                nm=_sanitize_text(transaction.get('counterparty_name'), 140)
            ) if transaction.get('counterparty_name') else None,
            dbtr_acct=counterparty_acct,
            cdtr=camt052.PartyIdentification32(nm=_sanitize_text(own_name, 140)),
            cdtr_acct=own_acct
        )
    else:
        # Debit: we are debtor, counterparty is creditor
        return camt052.TransactionParty2(
            dbtr=camt052.PartyIdentification32(nm=_sanitize_text(own_name, 140)),
            dbtr_acct=own_acct,
            cdtr=camt052.PartyIdentification32(
                nm=_sanitize_text(transaction.get('counterparty_name'), 140)
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


def _lookup_gvcode(bic, transaction_type, primanota):
    """
    Look up the GVCode for a given combination of BIC, transaction type and primanota.

    First tries to find an exact match for the BIC, then falls back to the
    default mapping (BIC = '*').

    Args:
        bic: Bank Identifier Code (SWIFT)
        transaction_type: Hibiscus transaction type (art)
        primanota: Bank's internal booking reference

    Returns:
        str: The GVCode if found, None otherwise
    """
    if not transaction_type or not primanota:
        return None

    # Try exact BIC match first
    if bic:
        mapping = frappe.db.get_value(
            "GVCode Mapping",
            {
                "bic": bic,
                "transaction_type": transaction_type,
                "primanota": primanota
            },
            "gvcode"
        )
        if mapping:
            return mapping

    # Fall back to default mapping (BIC = '*')
    mapping = frappe.db.get_value(
        "GVCode Mapping",
        {
            "bic": "*",
            "transaction_type": transaction_type,
            "primanota": primanota
        },
        "gvcode"
    )

    return mapping
