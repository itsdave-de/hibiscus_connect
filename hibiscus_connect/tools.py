"""
Hibiscus Connect Tools

This module provides functions for synchronizing bank accounts and transactions
between the Hibiscus Payment Server and Frappe/ERPNext.
"""

import frappe
import json
import re
from datetime import datetime as dt
from datetime import date, timedelta
from frappe.model.naming import get_default_naming_series
from frappe.exceptions import DuplicateEntryError

from hibiscus_connect.utils import is_erpnext_installed, check_erpnext_required
from hibiscus_connect.hibclient import Hibiscus

@frappe.whitelist()

def get_accounts_from_hibiscus_server():
    #Liefert ungefiltert alle Konten mit sämmtlichen Paramatern zurück
    settings = frappe.get_single("Hibiscus Connect Settings")
    hib = Hibiscus(settings.server, settings.port, settings.get_password("hibiscus_master_password") , settings.ignore_cert)
    return hib.get_accounts()

@frappe.whitelist()

def get_accounts_from_hibiscus_server_for_dialog():
    #Liefert alle Konten zurück, formatiert für die Anzeige des Dialogs "Konten anlegen"
    accounts = get_accounts_from_hibiscus_server()
    fields = []
    for account in accounts:

        account_dict = {
            "label": str(account["bezeichnung"] + ", " + account["name"] + ", IBAN:" + account["iban"]),
            "fieldname": str(account["iban"]),
            "fieldtype": "Check"
        }
        fields.append(account_dict)
    return fields


@frappe.whitelist()

def create_or_update_accounts(dialog_accounts):
    """Create new accounts or update existing ones with latest data from Hibiscus."""
    hibiscus_accounts = get_accounts_from_hibiscus_server()
    dialog_accounts_dict = json.loads(dialog_accounts)
    created = 0
    updated = 0
    for key in dialog_accounts_dict:
        if dialog_accounts_dict[key] == 1:
            iban = key
            for hib_acc in hibiscus_accounts:
                if hib_acc["iban"] == iban:
                    if frappe.db.exists("Hibiscus Connect Bank Account", iban):
                        # Update existing account
                        update_hibiscus_connect_bank_account(hib_acc)
                        updated += 1
                    else:
                        # Create new account
                        create_hibiscus_connect_bank_account(hib_acc)
                        created += 1
    frappe.db.commit()
    return {"created": created, "updated": updated}


@frappe.whitelist()
def create_accounts(dialog_accounts):
    """Deprecated: Use create_or_update_accounts instead."""
    return create_or_update_accounts(dialog_accounts)

def create_hibiscus_connect_bank_account(hib_acc):
    hib_acc["doctype"] = "Hibiscus Connect Bank Account"
    # Map Hibiscus API fields to DocType fields
    hib_acc["account_holder"] = hib_acc.pop("name", "")
    if "bezeichnung" in hib_acc:
        hib_acc["account_name_from_bank"] = hib_acc.pop("bezeichnung")
    if "kontonummer" in hib_acc:
        hib_acc["account_number"] = hib_acc.pop("kontonummer")
    if "blz" in hib_acc:
        hib_acc["bank_code"] = hib_acc.pop("blz")
    if "unterkonto" in hib_acc:
        hib_acc["sub_account"] = hib_acc.pop("unterkonto")
    if "kundennummer" in hib_acc:
        hib_acc["customer_number"] = hib_acc.pop("kundennummer")
    if "waehrung" in hib_acc:
        hib_acc["currency"] = hib_acc.pop("waehrung")
    if "kommentar" in hib_acc:
        hib_acc["hibiscus_comment"] = hib_acc.pop("kommentar")
    if "id" in hib_acc:
        hib_acc["hibiscus_id"] = hib_acc.pop("id")
    if "saldo_datum" in hib_acc:
        hib_acc["balance_date"] = hib_acc.pop("saldo_datum")
    # Handle empty saldo values
    available_balance = str(hib_acc.get("saldo_available", "0") or "0").replace(".","").replace(",",".")
    balance = str(hib_acc.get("saldo", "0") or "0").replace(".","").replace(",",".")
    hib_acc["available_balance"] = float(available_balance) if available_balance else 0.0
    hib_acc["balance"] = float(balance) if balance else 0.0
    # Remove old keys
    hib_acc.pop("saldo_available", None)
    hib_acc.pop("saldo", None)
    hib_acc.pop("name1", None)  # Remove if present (was secondary name field)
    hib_acc_doc = frappe.get_doc(hib_acc)
    hib_acc_doc.save()


def update_hibiscus_connect_bank_account(hib_acc):
    """Update an existing bank account with latest data from Hibiscus."""
    iban = hib_acc.get("iban")
    if not iban or not frappe.db.exists("Hibiscus Connect Bank Account", iban):
        return

    # Parse balance values
    available_balance = str(hib_acc.get("saldo_available", "0") or "0").replace(".","").replace(",",".")
    balance = str(hib_acc.get("saldo", "0") or "0").replace(".","").replace(",",".")

    # Update fields that come from Hibiscus (read-only fields)
    update_values = {
        "account_name_from_bank": hib_acc.get("bezeichnung", ""),
        "account_holder": hib_acc.get("name", ""),
        "account_number": hib_acc.get("kontonummer", ""),
        "bank_code": hib_acc.get("blz", ""),
        "bic": hib_acc.get("bic", ""),
        "sub_account": hib_acc.get("unterkonto", ""),
        "customer_number": hib_acc.get("kundennummer", ""),
        "currency": hib_acc.get("waehrung", ""),
        "hibiscus_comment": hib_acc.get("kommentar", ""),
        "hibiscus_id": hib_acc.get("id", ""),
        "balance_date": hib_acc.get("saldo_datum", ""),
        "available_balance": float(available_balance) if available_balance else 0.0,
        "balance": float(balance) if balance else 0.0,
    }

    for field, value in update_values.items():
        frappe.db.set_value("Hibiscus Connect Bank Account", iban, field, value)


def update_account_balance_from_transactions(account):
    """Update account balance and balance_date from the latest transaction."""
    # Get the latest transaction by value_date (or transaction_date as fallback)
    latest_trans = frappe.db.sql("""
        SELECT balance, value_date, transaction_date
        FROM `tabHibiscus Connect Transaction`
        WHERE bank_account = %s
        ORDER BY COALESCE(value_date, transaction_date) DESC, name DESC
        LIMIT 1
    """, (account,), as_dict=True)

    if latest_trans:
        trans = latest_trans[0]
        balance_date = trans.get("value_date") or trans.get("transaction_date")
        balance = trans.get("balance", 0)

        frappe.db.set_value("Hibiscus Connect Bank Account", account, {
            "balance": balance,
            "balance_date": str(balance_date) if balance_date else ""
        })


@frappe.whitelist()
def get_transactions_for_account(account, von=None, bis=None):
    """
    Fetch transactions from Hibiscus server and import them into Frappe.

    Args:
        account: Name of the Hibiscus Connect Bank Account (IBAN)
        von: Start date as string "YYYY-MM-DD" (default: 30 days ago)
        bis: End date as string "YYYY-MM-DD" (default: today)

    Returns:
        dict: Statistics about the import (new_count, skipped_count, error_count)
    """
    # Set default date range
    if von is None:
        von = str(date.today() - timedelta(30))
    if bis is None:
        bis = str(date.today())

    # Get settings and initialize Hibiscus client
    settings = frappe.get_single("Hibiscus Connect Settings")
    hib = Hibiscus(
        settings.server,
        settings.port,
        settings.get_password("hibiscus_master_password"),
        settings.ignore_cert
    )

    # Validate account
    account_doc = frappe.get_doc("Hibiscus Connect Bank Account", account)
    if is_erpnext_installed() and not account_doc.erpnext_account:
        frappe.throw("Bitte Hibiscus Connect Bank Account mit ERPNext Bankkonto verknüpfen.")

    # Parse dates
    von_dt = dt.strptime(von, "%Y-%m-%d")
    bis_dt = dt.strptime(bis, "%Y-%m-%d")

    # Fetch transactions from Hibiscus
    try:
        transactions = hib.get_transactions(account_doc.hibiscus_id, von_dt, bis_dt)
    except Exception as e:
        frappe.log_error(f"Error fetching transactions from Hibiscus: {e}", "Hibiscus Import")
        frappe.throw(f"Fehler beim Abrufen der Transaktionen: {e}")

    # Import statistics
    stats = {"new_count": 0, "skipped_count": 0, "error_count": 0}

    for hib_trans in transactions:
        # Skip transactions with zero balance (incomplete/pending)
        if hib_trans.get("saldo") == "0.0":
            stats["skipped_count"] += 1
            continue

        hibiscus_id = hib_trans.get("id")

        # Efficient duplicate check using database query
        if frappe.db.exists("Hibiscus Connect Transaction", {"hibiscus_id": hibiscus_id}):
            stats["skipped_count"] += 1
            continue

        # Import the transaction
        try:
            create_hibiscus_connect_transaction(hib_trans, account)
            stats["new_count"] += 1
        except Exception as e:
            stats["error_count"] += 1
            frappe.log_error(
                f"Error importing transaction {hibiscus_id}: {e}\nData: {hib_trans}",
                "Hibiscus Import"
            )

    # Update account balance from the latest transaction
    update_account_balance_from_transactions(account)

    frappe.db.commit()
    return stats

def create_hibiscus_connect_transaction(hib_trans, account):
    """
    Create a Hibiscus Connect Transaction document from Hibiscus API data.

    Field Mapping (Hibiscus API → Frappe DocType):
    ┌─────────────────────┬─────────────────────┬──────────────────────────────────┐
    │ Hibiscus Field      │ DocType Field       │ Description                      │
    ├─────────────────────┼─────────────────────┼──────────────────────────────────┤
    │ id                  │ hibiscus_id         │ Unique ID in Hibiscus            │
    │ konto_id            │ hibiscus_account_id │ Account ID in Hibiscus           │
    │ betrag              │ amount              │ Transaction amount (EUR)         │
    │ saldo               │ balance             │ Balance after transaction        │
    │ datum               │ transaction_date    │ Booking date                     │
    │ valuta              │ value_date          │ Value date (Valuta)              │
    │ art                 │ transaction_type    │ Type (Überweisung, Lastschrift)  │
    │ empfaenger_name     │ counterparty_name   │ Counterparty name                │
    │ empfaenger_konto    │ counterparty_iban   │ Counterparty IBAN                │
    │ empfaenger_blz      │ counterparty_bic    │ Counterparty BIC                 │
    │ zweck / zweck_raw   │ purpose             │ Payment purpose                  │
    │ endtoendid          │ end_to_end_id       │ SEPA End-to-End Reference        │
    │ primanota           │ primanota           │ Bank's internal reference        │
    │ customer_ref        │ customer_ref        │ Customer reference (timestamp)   │
    │ gvcode              │ gvcode              │ German transaction code          │
    │ kommentar           │ hibiscus_comment    │ Comment in Hibiscus              │
    └─────────────────────┴─────────────────────┴──────────────────────────────────┘

    Args:
        hib_trans: Dictionary with transaction data from Hibiscus API
        account: Name of the Hibiscus Connect Bank Account (IBAN)

    Returns:
        The created Hibiscus Connect Transaction document
    """
    # Build transaction document with explicit field mapping
    transaction_data = {
        "doctype": "Hibiscus Connect Transaction",
        "bank_account": account,

        # Core transaction fields
        "hibiscus_id": hib_trans.get("id"),
        "hibiscus_account_id": hib_trans.get("konto_id"),

        # Amount fields - Hibiscus sends decimal format (e.g., "3010.00")
        "amount": _parse_amount(hib_trans.get("betrag", "0")),
        "balance": _parse_amount(hib_trans.get("saldo", "0")),

        # Date fields
        "transaction_date": hib_trans.get("datum"),
        "value_date": hib_trans.get("valuta"),

        # Transaction type
        "transaction_type": hib_trans.get("art"),

        # Counterparty information
        "counterparty_name": hib_trans.get("empfaenger_name"),
        "counterparty_iban": hib_trans.get("empfaenger_konto"),
        "counterparty_bic": hib_trans.get("empfaenger_blz"),

        # Purpose / Reference fields
        "purpose": _parse_purpose(hib_trans),
        "purpose_raw": _parse_purpose(hib_trans, raw=True),
        "end_to_end_id": hib_trans.get("endtoendid"),

        # Bank reference fields
        "primanota": hib_trans.get("primanota"),
        "customer_ref": hib_trans.get("customer_ref"),
        "gvcode": hib_trans.get("gvcode"),

        # Hibiscus metadata
        "hibiscus_comment": hib_trans.get("kommentar"),
    }

    # Remove None values to avoid overwriting defaults
    transaction_data = {k: v for k, v in transaction_data.items() if v is not None}

    # Create and save the document
    doc = frappe.get_doc(transaction_data)
    doc.insert(ignore_permissions=True)

    return doc


def _parse_amount(value):
    """
    Parse amount value from Hibiscus API.

    Hibiscus sends amounts in decimal format with dot separator (e.g., "3010.00").

    Args:
        value: Amount as string or number

    Returns:
        float: Parsed amount value
    """
    if value is None:
        return 0.0
    try:
        return float(str(value))
    except (ValueError, TypeError):
        return 0.0


def _parse_purpose(hib_trans, raw=False):
    """
    Parse purpose field from Hibiscus API.

    Hibiscus provides two purpose fields:
    - zweck: Truncated purpose text
    - zweck_raw: Full purpose text (may be a list of strings)

    Args:
        hib_trans: Transaction data dictionary
        raw: If True, prefer zweck_raw; otherwise use processed purpose

    Returns:
        str: Combined purpose text
    """
    zweck_raw = hib_trans.get("zweck_raw")
    zweck = hib_trans.get("zweck", "")

    if zweck_raw:
        if isinstance(zweck_raw, list):
            return " ".join(zweck_raw)
        return str(zweck_raw)

    return zweck or ""

@frappe.whitelist()
def match_hibiscus_transaction(hib_trans):
    check_erpnext_required("Automatisches Verbuchen")
    payments = frappe.get_all("Hibiscus Connect Transaction", filters={
        "name": hib_trans
    }, fields = ["name", "counterparty_bic", "counterparty_iban"])
    hib_trans = payments[0]
    result = match_payment(hib_trans)
    if result["sinvs_matched_strict"]:
        pe = make_payment_entry(result)
        create_bank_account_for_customer(pe.party, hib_trans["counterparty_iban"], hib_trans["counterparty_bic"])
        return "Erfolgreich verbucht strict"
    if result["sinvs_matched_loose"]:
        pe = make_payment_entry(result)
        create_bank_account_for_customer(pe.party, hib_trans["counterparty_iban"], hib_trans["counterparty_bic"])
        return "Erfolgreich verbucht loose"
    if result["sinvs_matched_cust"]:
        pe = make_payment_entry(result)
        create_bank_account_for_customer(pe.party, hib_trans["counterparty_iban"], hib_trans["counterparty_bic"])
        return "Erfolgreich verbucht Kunde"
    frappe.throw("Zahlung konnte nicht automatisiert verbucht werden.<br>" + str(result))


def match_payment(hib_trans, sinvs=None, sinv_names=None):
    hib_trans_doc = frappe.get_doc("Hibiscus Connect Transaction", hib_trans)
    matching_list = {
        "sinvs_matched_strict": False,
        "sinvs_matched_loose": False,
        "sinvs_matched_cust": False,
        "totals_matched": False,
        "amount": hib_trans_doc.amount,
        "purpose": hib_trans_doc.purpose,
        "account": hib_trans_doc.bank_account,
        "erpnext_bank_account": frappe.get_doc("Hibiscus Connect Bank Account", hib_trans_doc.bank_account),
        "hib_trans_doc": hib_trans_doc,
        "sinvs": [],
        "sinvs_loose": [],
        "cust": "", #Zuordnung der Transaktion zu einem Kunden
        "sinvs_cust": []
        }
    if not sinvs:
        sinvs = _get_unpaid_sinv_numbers()
    if not sinv_names:
        sinv_names = _get_unpaid_sinv_names()
    #Kriterien, die zum verbuchen herangezogen werden:
    #1.) Zweck enthällt mindesten eine Rechnungsnummer einer unbezahlten Rechnung im vollständigen format
    matching_list["sinvs"] = _get_sinv_names(hib_trans_doc.purpose, sinvs)
    if matching_list["sinvs"]:
        matching_list["totals"] = _get_grand_totals(matching_list["sinvs"])
        #1.1) Wenn zusätzlich der Betrag übereinstimmt, können wir verbuchen
        if hib_trans_doc.amount == matching_list["totals"]:
            matching_list["sinvs_matched_strict"] = True
            matching_list["totals_matched"] = True
            return matching_list
    #2.) Zweck enthällt mindestens eine Rechnungsnummer einer unbezahlten Rechnung im unvollständigen Format (auch ohne Naming Series Prefix)
    matching_list["sinvs_loose"] = _advanced_si_match(hib_trans_doc.purpose, sinvs)
    if matching_list["sinvs_loose"]:
        matching_list["totals"] = _get_grand_totals(matching_list["sinvs_loose"])
        #2.1) Wenn zusätzlich der Betrag übereinstimmt, können wir verbuchen
        if hib_trans_doc.amount == matching_list["totals"]:
            matching_list["sinvs_matched_loose"] = True
            matching_list["totals_matched"] = True
            return matching_list
    #3.) Transaktion wurde einem Kunden zugeordnet
    if hib_trans_doc.customer:
        if hib_trans_doc.customer != "":
            matching_list["cust"] = hib_trans_doc.customer

    #3.1) Zweck enthällt eine Kundenummer einer unbezahlten Rechnung (auch ohne Naming Series Prefix)
    if matching_list["cust"] == "":
        matching_list["cust"] = _cust_match(hib_trans_doc.purpose, sinv_names)

    #3.2) Die Bankverbindung ist einem Kunden zugeordnet
    if matching_list["cust"] == "" or not matching_list["cust"]:
        acc = frappe.get_all("Bank Account", filters={"iban": hib_trans_doc.counterparty_iban }, fields=["party"])
        if acc:
            matching_list["cust"] = acc[0]["party"]

    if matching_list["cust"] != "":
        #3.3 Rechnunen ermitteln, deren Summe dem Betrag entspricht.
        matching_list["sinvs_cust"] = find_matching_invoices_for_customer_payment(hib_trans_doc, sinv_names, matching_list["cust"])
        print(matching_list["sinvs_cust"])
        if matching_list["sinvs_cust"]:
            matching_list["sinvs_matched_cust"] = True
            matching_list["totals_matched"] = True
            print("183 ", matching_list)
            return matching_list
    return matching_list



@frappe.whitelist()
def match_all_payments(von = str(date.today()-timedelta(30)), bis = str(date.today())):
    check_erpnext_required("Automatisches Verbuchen")
    stats = {
        "sinvs_matched_strict": 0,
        "sinvs_matched_loose": 0,
        "sinvs_matched_cust": 0,
        "totals_matched": 0,
        "payments_processed": 0
        }
    payments = frappe.get_all("Hibiscus Connect Transaction", filters={
        "status": "new",
        "amount": [">", 0],
    }, fields = ["name", "counterparty_bic", "counterparty_iban"])

    unpaid_sinvs = _get_unpaid_sinv_numbers()
    payments_list = []

    count = 0
    for p in payments:
        count += 1
        payments_list.append(p)
        result = match_payment(p.name, sinvs=unpaid_sinvs)

        stats["payments_processed"] += 1
        if result["sinvs_matched_strict"]:
            stats["sinvs_matched_strict"] += 1
            pe = make_payment_entry(result)
            create_bank_account_for_customer(pe.party, p["counterparty_iban"], p["counterparty_bic"])
        if result["sinvs_matched_loose"]:
            stats["sinvs_matched_loose"] += 1
            pe = make_payment_entry(result)
            create_bank_account_for_customer(pe.party, p["counterparty_iban"], p["counterparty_bic"])
        if result["sinvs_matched_cust"]:
            stats["sinvs_matched_cust"] += 1
            print(result)
            pe = make_payment_entry(result)
            create_bank_account_for_customer(pe.party, p["counterparty_iban"], p["counterparty_bic"])
        if result["totals_matched"]:
            stats["totals_matched"] += 1
        else:
            debug_data(result)

        frappe.publish_progress(
			count * 100 / len(payments),
			title="Verarbeite Zahlungseingänge...",
		)

    pprint(stats)
    return get_text_from_stats(stats)

def debug_data(result):
    print("--------------------")
    print(result["purpose"])
    print(result["amount"])


def _advanced_si_match(purpose, sinvs):
    si_list = []
    regex = "|".join(sinvs)
    purpose = purpose.replace(" ","")
    match_regex_naming_series =re.findall(regex, purpose)
    if match_regex_naming_series:
        for m in match_regex_naming_series:
            sinv_name = "SINV-" + str(m)
            if sinv_name not in si_list:
                si_list.append(sinv_name)
    return si_list

def _cust_match(purpose, sinvs):
    si_list = []
    cust_list = []
    sinv_doc_list = frappe.get_all("Sales Invoice", filters={
        "name": ["in", sinvs]
    }, fields=[
        "name", "customer"
    ])
    for sinv_el in sinv_doc_list:
        if str(sinv_el["customer"]).lower() not in cust_list:
            cust_list.append(str(sinv_el["customer"]).lower())
    regex = "|".join(cust_list)
    purpose = purpose.replace(" ","")
    purpose = str(purpose).lower()
    match_regex_customer =re.findall(regex, purpose)
    if match_regex_customer:
        if len(match_regex_customer) > 1:
            frappe.throw("Mehr als eine Kundenummern im Verwendungszweck gefunden.")
        return match_regex_customer[0]
    else:
        return False


def find_matching_invoices_for_customer_payment(hib_trans_doc, sinv_names, customer):
    sinv_doc_list = frappe.get_all("Sales Invoice", filters={
        "name": ["in", sinv_names],
        "grand_total": ["<=", float(hib_trans_doc.amount)],
        "customer": customer
    }, fields=[
        "name", "customer", "grand_total"
    ], order_by="name asc")
    #Prüfen, ob die offenen Rechungsbeträge in irgendeiner Kombination dem Zahlbetrag entsprechen
    combined_totals = combine_totals(hib_trans_doc.amount, sinv_doc_list)
    matched_sinvs = []
    if combined_totals:
        for ct in combined_totals:
            for sinv in sinv_doc_list:
                if ct == sinv["grand_total"]:
                    if sinv["name"] not in matched_sinvs:
                        matched_sinvs.append(sinv["name"])

    return matched_sinvs


def combine_totals(sum, sinvs): #gibt ggf. eine Liste an Beträgen zurück, die summiert den Zahlbetrag ergeben
    #Summen aller Rechnungen sammeln
    sinv_totals = []
    for sinv in sinvs:
        sinv_totals.append(sinv["grand_total"])

    result = subset_sum(sinv_totals, sum)
    if result:
        return result
    else:
        return None

#stolen from https://stackoverflow.com/questions/34517540/find-all-combinations-of-a-list-of-numbers-with-a-given-sum  and adapted afterwards
def subset_sum(numbers, target, partial=[]): #Ermittelt mögliche Kombinatiinen der Rechnungssummen
    s = sum(partial)
    # check if the partial sum is equals to target
    if round(s,3) == target:
        print("sum(%s)=%s" % (partial, target))
        return partial
    if s > target:
        return # if we reach the number why bother to continue
    for i in range(len(numbers)):
        n = numbers[i]
        remaining = numbers[i + 1:]
        result = subset_sum(remaining, target, partial + [n])
        if result:
            return result

def get_sinvs_for_matched_totals(totals, sinvs):
    pass


def _get_unpaid_sinv_numbers():
    sinv_numbers = []
    sinvs = frappe.get_all("Sales Invoice", filters={
        "status": ["not in", ["Return", "Paid"]],
        "name": ["not like", "SINV-RET-%"]
        })
    for si in sinvs:
        sinv_numbers.append(str(si["name"]).split("-")[1])
    return sinv_numbers

def _get_unpaid_sinv_names():
    sinv_numbers = []
    sinvs = frappe.get_all("Sales Invoice", filters={
        "status": ["not in", ["Return", "Paid"]],
        "name": ["not like", "SINV-RET-%"]
        })
    for si in sinvs:
        sinv_numbers.append(str(si["name"]))
    return sinv_numbers


def _get_sinv_names(purpose, sinvs=None, extended_matching=True):
    naming_series = get_default_naming_series("Sales Invoice")
    if "#" not in naming_series:
        naming_series += "######"
    regex_naming_series = str(naming_series).replace(".","").replace("#","\\d")
    match_regex_naming_series =re.findall(regex_naming_series, purpose)
    sinv_name_list = []
    if match_regex_naming_series:
        for m in match_regex_naming_series:
            if m not in sinv_name_list:
                if frappe.db.exists("Sales Invoice", m):
                    sinv_name_list.append(m)
                else:
                    print(f"Sales Invoice {m} does not exist and will be skipped.")
    return sinv_name_list


def _get_grand_totals(sinv_list):
    grand_total_sum = 0.0
    for sinv in sinv_list:
        if frappe.db.exists("Sales Invoice", sinv):
            sinv_doc = frappe.get_doc("Sales Invoice", sinv)
            grand_total_sum += sinv_doc.grand_total
        else:
            print(f"Sales Invoice {sinv} does not exist and will be skipped.")
    return round(grand_total_sum, 2)


def make_payment_entry(matching_list, settings=None):
    other_account_sinv = []
    if not settings:
        settings = frappe.get_single("Hibiscus Connect Settings")

    pe_doc = frappe.get_doc({
        "doctype": "Payment Entry",
        "payment_type": "Receive",
        "party_type": "Customer",
        "party": "", #erstmal leer, wird später anhand vorliegender Rechnungen befüllt
        "party_name": "",
        "paid_from": "",
        "paid_to":  matching_list["erpnext_bank_account"].erpnext_account,
        "paid_amount": matching_list["amount"],
        "received_amount": matching_list["amount"],
        "source_exchange_rate": 1,
        "target_exchange_rate": 1,
        "reference_no": matching_list["hib_trans_doc"].name,
        "reference_date": matching_list["hib_trans_doc"].transaction_date,
        "hibiscus_connect_transaction": matching_list["hib_trans_doc"].name,
        "referneces": []
    })

    todo = list(matching_list["sinvs"])
    todo.extend(x for x in matching_list["sinvs_loose"] if x not in todo)
    todo.extend(x for x in matching_list["sinvs_cust"] if x not in todo)

    todo.sort()
    error = ""
    print(todo)
    for sinv in todo:
        print("processing " + sinv)

        reference_doc_response = _get_payment_entry_reference(sinv)

        #Kundennummer setzen wenn bisher leer
        if pe_doc.party == "":
            pe_doc.party = reference_doc_response["sinv_doc"].customer
            pe_doc.party_name = frappe.get_value(doctype="Customer", filters={"name": pe_doc.party}, fieldname="customer_name"),
        #Fehler, wenn eine bereits befüllte Kundenummer verändert werden soll
        if pe_doc.party != reference_doc_response["sinv_doc"].customer:
            error += "Verschiedene Kundenummern in automatisiert zugeordneten Rechnungen.<br>"
            break

        #Debitoren Konte anhand Rechnungskonto setzen
        if pe_doc.paid_from == "":
            pe_doc.paid_from = reference_doc_response["sinv_doc"].debit_to
        #Fehler, wenn mehrere Debitoren Konten in einem PE angesprochen werden würden
        if pe_doc.paid_from != reference_doc_response["sinv_doc"].debit_to:
            other_account_sinv.append(sinv)
            continue
        pe_doc.append("references", reference_doc_response["reference_doc"])
        try:
            pe_doc.save()
            if pe_doc.unallocated_amount == 0:
                print("pe_doc.unallocated_amount = 0")
                break

        except Exception as e:
            error += "<p>" + repr(e) + "</p>"

    if error:
        frappe.msgprint(error + dict_to_html_ul(matching_list,2))
        return pe_doc
    else:
        pe_doc.save()
        print("letztes save")
        print(pe_doc.total_allocated_amount)
        print(pe_doc.unallocated_amount)
        print(pe_doc.difference_amount)
        matching_list["hib_trans_doc"].customer = pe_doc.party
        matching_list["hib_trans_doc"].save()
        matching_list["Payment Entry"] = pe_doc.name

    if len(other_account_sinv) > 0:
        frappe.msgprint("Zahlung konnte nicht automatisiert verbucht werden. Es wurden verschiedene Konten angesrpochen.<br>" + dict_to_html_ul(matching_list,2))
        return pe_doc

    if settings.auto_submit_payment_entry:
        if pe_doc.difference_amount != 0:
            frappe.msgprint("Zahlung konnte nicht automatisiert verbucht werden. Es kamen mehrere identische Beträge in Frage.<br>" + dict_to_html_ul(matching_list,2))
            return pe_doc

        if round(pe_doc.unallocated_amount + pe_doc.total_allocated_amount, 2) != pe_doc.paid_amount:
            frappe.msgprint("Zahlung konnte nicht automatisiert verbucht werden. Es gibt noch unzugeordnete Beträge.<br>" + dict_to_html_ul(matching_list,2))
            return pe_doc

        pe_doc.submit()
        matching_list["hib_trans_doc"].log = pe_doc.remarks
        matching_list["hib_trans_doc"].status = "auto booked"
        matching_list["hib_trans_doc"].save()

    return pe_doc


def _get_payment_entry_reference(sinv):
    sinv_doc = frappe.get_doc("Sales Invoice", sinv)
    reference_doc = frappe.get_doc({
        "doctype": "Payment Entry Reference",
        "reference_doctype": "Sales Invoice",
        "reference_name": sinv,
        "due_date": sinv_doc.due_date,
        "total_amount": sinv_doc.grand_total,
        "outstanding_amount": sinv_doc.outstanding_amount,
        "allocated_amount": sinv_doc.outstanding_amount
    })
    return {"reference_doc": reference_doc, "sinv_doc": sinv_doc}

### wip

def get_text_from_stats(stats):
    html = (
        f"<h2>Summary of Processed Payments</h2>"
        f"<ul style='list-style-type: disc; padding-left: 20px;'>"
        f"<li><strong>Payments Processed:</strong> {stats['payments_processed']}</li>"
        f"<li><strong>Strictly Matched Invoices:</strong> {stats['sinvs_matched_strict']}</li>"
        f"<li><strong>Loosely Matched Invoices:</strong> {stats['sinvs_matched_loose']}</li>"
        f"<li><strong>Customer Matched Invoices:</strong> {stats['sinvs_matched_cust']}</li>"
        f"<li><strong>Totals Matched:</strong> {stats['totals_matched']}</li>"
        f"</ul>"
    )
    return html

@frappe.whitelist()
def set_andere_einnahme(list):
    print("#####################")
    hbt_list = json.loads(list)
    print(hbt_list)
    for el in hbt_list:
        hbdoc = frappe.get_doc("Hibiscus Connect Transaction", el)
        hbdoc.status = "other income"
        hbdoc.save()

@frappe.whitelist()
def dump_checked(list):
    pprint(list)

def create_debit_charge(sinv, method=None):
    if not is_erpnext_installed():
        return
    print(sinv.name)
    settings = frappe.get_single("Hibiscus Connect Settings")
    if settings.sepa_direct_debit_enabled == 0:
        return

    else:
        invoice = frappe.get_doc("Sales Invoice", sinv.name)
        customer = invoice.customer
        #termin = invoice.due_date - timedelta(days=2)
        amount = str(invoice.grand_total).replace(".", ",")
        payment_terms = invoice.payment_terms_template
        print("payment_terms")
        print(payment_terms)
        if payment_terms == "SEPA Einzug 7 Tage" or payment_terms == "SEPA Einzug 14 Tage":
            if invoice.grand_total >0:
                sepa_mandat = frappe.get_all("SEPA Lastschrift Mandat",
                                            filters = {
                                                "status": "active",
                                                "customer":customer
                                                },

                                            )

                print(len(sepa_mandat))
                if len(sepa_mandat) == 1:
                    sepa_mandat_doc = frappe.get_doc("SEPA Lastschrift Mandat", sepa_mandat[0]["name"])
                    print(sepa_mandat_doc.first_debit_done, sepa_mandat_doc.is_final_debit)
                    if sepa_mandat_doc.first_debit_done == 0 and sepa_mandat_doc.is_final_debit == 0:
                        sequencetype = "FRST"
                        sepa_mandat_doc.first_debit_done = 1
                        termin = invoice.due_date - timedelta(days=5)
                        sepa_mandat_doc.save()
                    elif sepa_mandat_doc.first_debit_done == 1 and sepa_mandat_doc.is_final_debit == 0:
                        sequencetype = "RCUR"
                        termin = invoice.due_date - timedelta(days=2)
                    elif sepa_mandat_doc.is_final_debit == 1:
                        sequencetype = "FNAL"
                        sepa_mandat_doc.status = "inactive"
                        sepa_mandat_doc.save()
                    print(sequencetype)
                    params =  {"betrag": str(amount),
                            "termin": str(termin),
                            "konto": str(sepa_mandat_doc.creditor_account_id),
                            "name": str(sepa_mandat_doc.debtor_name),
                            "blz": str(sepa_mandat_doc.debtor_bic),
                            "kontonummer": str(sepa_mandat_doc.debtor_iban),
                            "verwendungszweck": str(invoice.name),
                            "creditorid":str(sepa_mandat_doc.creditor_id),
                            "mandateid":str(sepa_mandat_doc.mandate_reference),
                            "sigdate":str(sepa_mandat_doc.signature_date),
                            "sequencetype":str(sequencetype),
                            "sepatype":str(sepa_mandat_doc.sepa_type),
                            "targetdate": str(invoice.due_date)

                            }
                    print(params)

                    hib = Hibiscus(settings.server, settings.port, settings.get_password("hibiscus_master_password"), settings.ignore_cert)
                    deb = hib.get_debit_charge(params)
                    print(deb)
                    if not deb:
                        frappe.msgprint("Es wurde eine SEPA-Lastschrift erzeugt")
                    else:
                        frappe.msgprint(deb)

                elif len(sepa_mandat) == 0:
                    print("Für den Kunden wurde kein aktives SEPA Mandat gefunden")
                    frappe.msgprint("Für den Kunden wurde kein aktives SEPA Mandat gefunden")
                else:
                    print("Mandat nicht eindeutig, bitte prüfen")
                    frappe.msgprint("Mandat nicht eindeutig, bitte prüfen")



###### einmal-methoden für inbetreibnahme

def set_lagacy_verbucht():
    hib_transactions = frappe.get_all("Hibiscus Connect Transaction", filters={
        "status": "new"
    })
    for ht in hib_transactions:
        ht_doc= frappe.get_doc("Hibiscus Connect Transaction", ht["name"])
        regex = "PE-\\d\\d\\d\\d\\d"
        result = re.findall(regex, ht_doc.hibiscus_comment)

        if result:
            print(ht_doc.hibiscus_comment)
            ht_doc.status = "legacy booked"
            ht_doc.save()
    frappe.db.commit()

@frappe.whitelist()
def create_bank_account_for_customer(customer, iban, bic):
    if not is_erpnext_installed():
        return "ERPNext nicht installiert - Bankkonto nicht erstellt."
    if frappe.get_all("Bank Account", filters={"iban": iban}):
        return "Bankkonto bereits vorhanden."

    cdoc = frappe.get_doc("Customer", customer)
    bank = frappe.get_all("Bank", filters={"swift_number": bic})
    if not bank:
        bank = create_unknown_bank(bic).name
    else:
        bank = bank[0]["name"]
    len_ges = len(bank) + len(cdoc.customer_name) + len(iban) + 6

    str_to = 140 - 6 - len(bank) - len(iban)
    account_name = cdoc.customer_name[0:str_to] + " | " + iban

    badoc = frappe.get_doc({
        "doctype": "Bank Account",
        "account_name": account_name,
        "bank" : bank,
        "party_type": "Customer",
        "party": customer,
        "iban": iban
        })

    badoc.save()
    return "Bankkonto erfolgreich erstellt."

def create_unknown_bank(bic):
    bdoc = frappe.get_doc({
        "doctype": "Bank",
        "bank_name": "unknown "+ bic,
        "swift_number": bic
    })
    bdoc.save()
    return bdoc


def dict_to_html_ul(dd, level=0):
    text = '<ul>'
    import json
    for k, v in dd.items():
        text += '<li><b>%s</b>: %s</li>' % (k, dict_to_html_ul(v, level+1) if isinstance(v, dict) else (json.dumps(v) if isinstance(v, list) else v))
    text += '</ul>'
    return text


def sync_account_names_from_bank():
    """
    Sync the account_name_from_bank field for all existing bank accounts
    by fetching current data from Hibiscus server.
    """
    hibiscus_accounts = get_accounts_from_hibiscus_server()
    updated = 0
    for hib_acc in hibiscus_accounts:
        iban = hib_acc.get("iban")
        bezeichnung = hib_acc.get("bezeichnung", "")
        if iban and frappe.db.exists("Hibiscus Connect Bank Account", iban):
            frappe.db.set_value("Hibiscus Connect Bank Account", iban, "account_name_from_bank", bezeichnung)
            updated += 1
            print(f"Updated {iban}: {bezeichnung}")
    frappe.db.commit()
    print(f"Updated {updated} accounts")

