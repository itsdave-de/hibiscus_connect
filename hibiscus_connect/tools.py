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
from pprint import pprint

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
    hib_acc.pop("name1", None)
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

    Field Mapping (Hibiscus API -> Frappe DocType):
    id -> hibiscus_id, konto_id -> hibiscus_account_id, betrag -> amount,
    saldo -> balance, datum -> transaction_date, valuta -> value_date,
    art -> transaction_type, empfaenger_name -> counterparty_name,
    empfaenger_konto -> counterparty_iban, empfaenger_blz -> counterparty_bic,
    zweck -> purpose, kommentar -> hibiscus_comment
    """
    # Build transaction document with explicit field mapping
    transaction_data = {
        "doctype": "Hibiscus Connect Transaction",
        "bank_account": account,

        # Core transaction fields
        "hibiscus_id": hib_trans.get("id"),
        "hibiscus_account_id": hib_trans.get("konto_id"),

        # Amount fields
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

    # Auto-detect chargebacks (GV code 108 = LS RÜCKBELASTUNG)
    amount = transaction_data.get("amount", 0)
    gvcode = transaction_data.get("gvcode", "")
    if str(gvcode) == "108" and amount < 0:
        transaction_data["status"] = "chargeback"

    # Create and save the document
    doc = frappe.get_doc(transaction_data)
    doc.insert(ignore_permissions=True)

    return doc


def _parse_amount(value):
    """Parse amount value from Hibiscus API.

    Hibiscus returns amounts in German locale format (comma as decimal separator,
    dot as thousands separator), e.g. "1.234,56" or "-415,00".
    Saldo values use dot as decimal separator, e.g. "131597.57".
    This function handles both formats.
    """
    if value is None:
        return 0.0
    try:
        s = str(value).strip()
        if "," in s:
            # German format: remove thousands dots, replace decimal comma with dot
            s = s.replace(".", "").replace(",", ".")
        return float(s)
    except (ValueError, TypeError):
        return 0.0


def _parse_purpose(hib_trans, raw=False):
    """Parse purpose field from Hibiscus API."""
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
        if not pe:
            frappe.throw("Payment Entry konnte nicht erstellt werden (keine zuordenbaren Rechnungen).")
        create_bank_account_for_customer(pe.party, hib_trans["counterparty_iban"], hib_trans["counterparty_bic"])
        return "Erfolgreich verbucht strict"
    if result["sinvs_matched_loose"]:
        pe = make_payment_entry(result)
        if not pe:
            frappe.throw("Payment Entry konnte nicht erstellt werden (keine zuordenbaren Rechnungen).")
        create_bank_account_for_customer(pe.party, hib_trans["counterparty_iban"], hib_trans["counterparty_bic"])
        return "Erfolgreich verbucht loose"
    if result["sinvs_matched_cust"]:
        pe = make_payment_entry(result)
        if not pe:
            frappe.throw("Payment Entry konnte nicht erstellt werden (keine zuordenbaren Rechnungen).")
        create_bank_account_for_customer(pe.party, hib_trans["counterparty_iban"], hib_trans["counterparty_bic"])
        return "Erfolgreich verbucht Kunde"
    # Doppelzahlung markieren wenn erkannt
    if result.get("duplicate_warning"):
        hib_trans_doc = result["hib_trans_doc"]
        hib_trans_doc.status = "possible duplicate"
        hib_trans_doc.log = "Mögliche Doppelzahlung erkannt:\n" + "\n".join(result["duplicate_warning"])
        hib_trans_doc.save()
        frappe.throw("Mögliche Doppelzahlung erkannt:<br>" + "<br>".join(result["duplicate_warning"]))

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
    # Keine Stufe hat gematcht — prüfen ob es eine Doppelzahlung sein könnte
    duplicate_details = _check_duplicate_payment(hib_trans_doc)
    if duplicate_details:
        matching_list["duplicate_warning"] = duplicate_details

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
            if pe:
                create_bank_account_for_customer(pe.party, p["counterparty_iban"], p["counterparty_bic"])
        if result["sinvs_matched_loose"]:
            stats["sinvs_matched_loose"] += 1
            pe = make_payment_entry(result)
            if pe:
                create_bank_account_for_customer(pe.party, p["counterparty_iban"], p["counterparty_bic"])
        if result["sinvs_matched_cust"]:
            stats["sinvs_matched_cust"] += 1
            print(result)
            pe = make_payment_entry(result)
            if pe:
                create_bank_account_for_customer(pe.party, p["counterparty_iban"], p["counterparty_bic"])
        if result["totals_matched"]:
            stats["totals_matched"] += 1
        else:
            debug_data(result)
            # Doppelzahlung markieren wenn erkannt
            if result.get("duplicate_warning"):
                hib_trans_doc = result["hib_trans_doc"]
                hib_trans_doc.status = "possible duplicate"
                hib_trans_doc.log = "Mögliche Doppelzahlung erkannt:\n" + "\n".join(result["duplicate_warning"])
                hib_trans_doc.save()

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
                    # Nur unbezahlte Rechnungen matchen
                    if sinvs is not None:
                        sinv_number = str(m).split("-")[1]
                        if sinv_number not in sinvs:
                            print(f"Sales Invoice {m} ist bereits bezahlt und wird übersprungen.")
                            continue
                    sinv_name_list.append(m)
                else:
                    print(f"Sales Invoice {m} does not exist and will be skipped.")
    return sinv_name_list


def _check_duplicate_payment(hib_trans_doc):
    """Prüft ob im Verwendungszweck Rechnungsnummern stehen, die bereits bezahlt sind."""
    all_sinvs_in_purpose = _get_sinv_names(hib_trans_doc.purpose)  # ohne sinvs-Filter → findet auch bezahlte
    if not all_sinvs_in_purpose:
        return None

    duplicate_details = []
    for sinv_name in all_sinvs_in_purpose:
        sinv_doc = frappe.get_doc("Sales Invoice", sinv_name)
        if sinv_doc.outstanding_amount > 0:
            continue
        # Rechnung ist vollständig bezahlt — welcher PE hat sie bezahlt?
        pe_refs = frappe.get_all("Payment Entry Reference",
            filters={
                "reference_name": sinv_name,
                "reference_doctype": "Sales Invoice",
                "docstatus": 1
            },
            fields=["parent", "allocated_amount"])
        pe_detail = ""
        for ref in pe_refs:
            pe_posting_date = frappe.db.get_value("Payment Entry", ref["parent"], "posting_date")
            pe_detail = f" (bezahlt durch {ref['parent']} vom {pe_posting_date}, {ref['allocated_amount']} EUR)"
            break
        duplicate_details.append(f"{sinv_name} wurde im Verwendungszweck gefunden, ist aber bereits vollständig bezahlt{pe_detail}.")

    return duplicate_details if duplicate_details else None


def _get_grand_totals(sinv_list):
    grand_total_sum = 0.0
    for sinv in sinv_list:
        if frappe.db.exists("Sales Invoice", sinv):
            sinv_doc = frappe.get_doc("Sales Invoice", sinv)
            grand_total_sum += sinv_doc.outstanding_amount
        else:
            print(f"Sales Invoice {sinv} does not exist and will be skipped.")
    return round(grand_total_sum, 2)


def make_payment_entry(matching_list, settings=None):
    other_account_sinv = []
    if not settings:
        settings = frappe.get_single("Hibiscus Connect Settings")

    todo = list(matching_list["sinvs"])
    todo.extend(x for x in matching_list["sinvs_loose"] if x not in todo)
    todo.extend(x for x in matching_list["sinvs_cust"] if x not in todo)
    todo.sort()

    if not todo:
        frappe.msgprint("Keine zuordenbaren Rechnungen gefunden für Transaktion " + matching_list["hib_trans_doc"].name)
        return None

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
        matching_list["hib_trans_doc"].add_link("Payment Entry", pe_doc.name, amount=pe_doc.paid_amount, note="Automatisch erstellt")
        matching_list["hib_trans_doc"].save()
        matching_list["Payment Entry"] = pe_doc.name

    if len(other_account_sinv) > 0:
        frappe.msgprint("Zahlung konnte nicht automatisiert verbucht werden. Es wurden verschiedene Konten angesrpochen.<br>" + dict_to_html_ul(matching_list,2))
        return pe_doc

    if settings.auto_submit_payment_entry:
        if not pe_doc.references or len(pe_doc.references) == 0:
            frappe.msgprint("Payment Entry " + pe_doc.name + " hat keine Rechnungszuordnung und wird nicht automatisch gebucht.")
            return pe_doc
        if pe_doc.difference_amount != 0:
            frappe.msgprint("Zahlung konnte nicht automatisiert verbucht werden. Es kamen mehrere identische Beträge in Frage.<br>" + dict_to_html_ul(matching_list,2))
            return pe_doc

        if round(pe_doc.unallocated_amount + pe_doc.total_allocated_amount, 2) != pe_doc.paid_amount:
            frappe.msgprint("Zahlung konnte nicht automatisiert verbucht werden. Es gibt noch unzugeordnete Beträge.<br>" + dict_to_html_ul(matching_list,2))
            return pe_doc

        pe_doc.submit()
        matching_list["hib_trans_doc"].log = pe_doc.remarks
        matching_list["hib_trans_doc"].status = "auto booked"
        for sinv in todo:
            matching_list["hib_trans_doc"].add_link("Sales Invoice", sinv, note="Automatisch zugeordnet")
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


# ── Chargeback Processing ──────────────────────────────────────────────

def _extract_sinv_refs_from_purpose(purpose):
    """Extract SINV references from a transaction's purpose field."""
    if not purpose:
        return []
    return re.findall(r'SINV-\d+', purpose.replace(' ', ''))


def _find_original_payment_entry(sinv_refs, counterparty_name=None):
    """Find the submitted Payment Entry that paid the given Sales Invoices.

    Strategy:
    1. Find submitted PEs that reference the SINVs
    2. If multiple, prefer the one linked to a Hibiscus transaction
    3. Return the PE doc or None
    """
    if not sinv_refs:
        return None

    # Find submitted PEs referencing any of these SINVs
    pe_names = frappe.db.sql("""
        SELECT DISTINCT parent
        FROM `tabPayment Entry Reference`
        WHERE reference_doctype = 'Sales Invoice'
          AND reference_name IN %(sinvs)s
          AND docstatus = 1
    """, {"sinvs": sinv_refs}, as_dict=True)

    if not pe_names:
        return None

    candidates = [row["parent"] for row in pe_names]

    if len(candidates) == 1:
        return frappe.get_doc("Payment Entry", candidates[0])

    # Multiple PEs — prefer one with hibiscus_connect_transaction set
    for pe_name in candidates:
        hct_link = frappe.db.get_value("Payment Entry", pe_name, "hibiscus_connect_transaction")
        if hct_link:
            return frappe.get_doc("Payment Entry", pe_name)

    # Fallback: return the first one
    return frappe.get_doc("Payment Entry", candidates[0])


@frappe.whitelist()
def get_chargeback_details(hib_trans):
    """Return details for the chargeback banner and confirmation dialog.

    Returns dict with: sinv_refs, pe_name, pe_amount, fee_amount, customer, sinv_details
    """
    doc = frappe.get_doc("Hibiscus Connect Transaction", hib_trans)

    sinv_refs = _extract_sinv_refs_from_purpose(doc.purpose)
    result = {
        "sinv_refs": sinv_refs,
        "pe_name": None,
        "pe_amount": 0,
        "fee_amount": 0,
        "customer": None,
        "sinv_details": [],
        "can_process": False,
        "message": "",
    }

    if not sinv_refs:
        result["message"] = "Keine Rechnungsnummer im Verwendungszweck gefunden."
        return result

    pe = _find_original_payment_entry(sinv_refs)
    if not pe:
        result["message"] = "Kein zugehöriger Payment Entry gefunden."
        return result

    if pe.docstatus != 1:
        result["message"] = f"Payment Entry {pe.name} ist nicht gebucht (Status: {pe.docstatus})."
        return result

    result["pe_name"] = pe.name
    result["pe_amount"] = pe.paid_amount
    result["customer"] = pe.party
    result["fee_amount"] = round(abs(doc.amount) - pe.paid_amount, 2)

    # Get SINV details for display
    for ref in pe.references:
        if ref.reference_doctype == "Sales Invoice":
            sinv_status = frappe.db.get_value("Sales Invoice", ref.reference_name, "status")
            result["sinv_details"].append({
                "sinv": ref.reference_name,
                "amount": ref.allocated_amount,
                "status": sinv_status,
            })

    result["can_process"] = True
    return result


@frappe.whitelist()
def process_chargeback(hib_trans):
    """Process a chargeback transaction by cancelling the original Payment Entry.

    1. Find the original PE via SINV references in purpose
    2. Cancel the PE (auto-reverses GL entries, reopens SINVs)
    3. Create Transaction Links on the chargeback transaction
    4. Update the original collection transaction
    5. Set chargeback status to 'chargeback processed'
    """
    check_erpnext_required("Rücklastschrift verarbeiten")

    doc = frappe.get_doc("Hibiscus Connect Transaction", hib_trans)

    if doc.status == "chargeback processed":
        frappe.throw("Diese Rücklastschrift wurde bereits verarbeitet.")

    sinv_refs = _extract_sinv_refs_from_purpose(doc.purpose)
    if not sinv_refs:
        frappe.throw("Keine Rechnungsnummer im Verwendungszweck gefunden.")

    pe = _find_original_payment_entry(sinv_refs)
    if not pe:
        frappe.throw("Kein zugehöriger Payment Entry gefunden.")

    if pe.docstatus != 1:
        frappe.throw(f"Payment Entry {pe.name} ist nicht gebucht und kann nicht storniert werden.")

    # Collect info before cancellation
    pe_name = pe.name
    pe_amount = pe.paid_amount
    affected_sinvs = [ref.reference_name for ref in pe.references if ref.reference_doctype == "Sales Invoice"]

    # Cancel the Payment Entry — this automatically:
    # - Reverses all GL entries
    # - Recalculates outstanding_amount on referenced SINVs
    # - Sets SINVs back to "Unpaid"
    pe.cancel()

    # Create Transaction Links on the chargeback transaction
    doc.add_link("Payment Entry", pe_name,
                 amount=pe_amount,
                 note=f"Rücklastschrift — PE {pe_name} storniert")
    for sinv in affected_sinvs:
        doc.add_link("Sales Invoice", sinv,
                     note="Rücklastschrift — Rechnung wieder offen")

    # Update the original collection transaction (if linked via hibiscus_connect_transaction)
    original_hct = frappe.db.get_value("Payment Entry", pe_name, "hibiscus_connect_transaction")
    if original_hct:
        original_doc = frappe.get_doc("Hibiscus Connect Transaction", original_hct)
        original_doc.cancel_link("Payment Entry", pe_name,
                                 note=f"PE storniert wegen Rücklastschrift {doc.name}")
        original_doc.save(ignore_permissions=True)

    # Set final status
    doc.status = "chargeback processed"
    doc.save(ignore_permissions=True)
    frappe.db.commit()

    # Calculate fee for user info
    fee = round(abs(doc.amount) - pe_amount, 2)
    fee_msg = ""
    if fee > 0:
        fee_msg = f"<br>Bankgebühr: {fee} EUR (manuell verbuchen)"
    elif fee < 0:
        fee_msg = f"<br>Differenz: {fee} EUR (Rücklastschrift-Betrag weicht ab)"

    return (
        f"Rücklastschrift verarbeitet:<br>"
        f"PE {pe_name} storniert.<br>"
        f"Rechnungen wieder offen: {', '.join(affected_sinvs)}"
        f"{fee_msg}"
    )



@frappe.whitelist()
def get_banking_dashboard_data():
    """Return dashboard data for chargebacks and unbooked payments."""
    # Chargebacks (status = chargeback, awaiting processing)
    chargeback = frappe.db.sql("""
        SELECT COUNT(*) as cnt, COALESCE(SUM(ABS(amount)), 0) as total
        FROM `tabHibiscus Connect Transaction`
        WHERE status = 'chargeback'
    """, as_dict=True)[0]

    # Unbooked payments (status = new)
    unbooked = frappe.db.sql("""
        SELECT COUNT(*) as cnt, COALESCE(SUM(CASE WHEN amount > 0 THEN amount ELSE 0 END), 0) as total_positive,
               COALESCE(SUM(CASE WHEN amount < 0 THEN ABS(amount) ELSE 0 END), 0) as total_negative,
               SUM(CASE WHEN amount > 0 THEN 1 ELSE 0 END) as cnt_positive,
               SUM(CASE WHEN amount < 0 THEN 1 ELSE 0 END) as cnt_negative
        FROM `tabHibiscus Connect Transaction`
        WHERE status = 'new'
    """, as_dict=True)[0]

    return {
        "chargeback_count": chargeback.cnt or 0,
        "chargeback_total": frappe.utils.fmt_money(chargeback.total, currency="EUR"),
        "unbooked_count": unbooked.cnt or 0,
        "unbooked_count_positive": unbooked.cnt_positive or 0,
        "unbooked_total_positive": frappe.utils.fmt_money(unbooked.total_positive, currency="EUR"),
        "unbooked_count_negative": unbooked.cnt_negative or 0,
        "unbooked_total_negative": frappe.utils.fmt_money(unbooked.total_negative, currency="EUR"),
    }


@frappe.whitelist()
def get_balance_history(account):
    """Return balance time series for the last 12 months.

    For each day with transactions, returns the closing balance (last transaction's balance).
    """
    from collections import OrderedDict

    twelve_months_ago = frappe.utils.add_months(frappe.utils.today(), -12)

    transactions = frappe.db.sql("""
        SELECT transaction_date, balance, name
        FROM `tabHibiscus Connect Transaction`
        WHERE bank_account = %(account)s
          AND transaction_date >= %(start)s
          AND balance != 0
        ORDER BY transaction_date ASC, name ASC
    """, {"account": account, "start": twelve_months_ago}, as_dict=True)

    if not transactions:
        return {"labels": [], "values": []}

    # Group by date, take last balance per day
    daily_balance = OrderedDict()
    for txn in transactions:
        daily_balance[str(txn.transaction_date)] = txn.balance

    labels = list(daily_balance.keys())
    values = list(daily_balance.values())

    return {"labels": labels, "values": values}


# ── Booking Dialog (universal in/out) ────────────────────────────────

@frappe.whitelist()
def create_bank_account_for_supplier(supplier, iban, bic):
    """Create a Bank Account for a supplier (mirror of create_bank_account_for_customer)."""
    if not is_erpnext_installed():
        return "ERPNext nicht installiert."
    if not iban:
        return "Keine IBAN angegeben."
    if frappe.get_all("Bank Account", filters={"iban": iban}):
        return "Bankkonto bereits vorhanden."

    sdoc = frappe.get_doc("Supplier", supplier)
    bank = frappe.get_all("Bank", filters={"swift_number": bic})
    if not bank:
        if bic:
            bank = create_unknown_bank(bic).name
        else:
            bank = frappe.get_all("Bank", limit=1)
            bank = bank[0]["name"] if bank else None
            if not bank:
                return "Keine Bank gefunden."
    else:
        bank = bank[0]["name"]

    str_to = 140 - 6 - len(bank) - len(iban)
    account_name = sdoc.supplier_name[0:str_to] + " | " + iban

    frappe.get_doc({
        "doctype": "Bank Account",
        "account_name": account_name,
        "bank": bank,
        "party_type": "Supplier",
        "party": supplier,
        "iban": iban
    }).save()
    return "Bankkonto erfolgreich erstellt."


@frappe.whitelist()
def get_booking_dialog_data(hib_trans):
    """Gather all data needed for the booking dialog."""
    check_erpnext_required("Buchungsdialog")

    doc = frappe.get_doc("Hibiscus Connect Transaction", hib_trans)
    direction = "Incoming" if doc.amount > 0 else "Outgoing"
    abs_amount = abs(doc.amount)

    # Load categories filtered by direction
    categories = frappe.get_all("Booking Category",
        filters={"enabled": 1, "direction": ["in", [direction, "Both"]]},
        fields=["category_name", "direction", "booking_type", "payment_type",
                "party_type", "needs_invoice_matching", "default_account",
                "default_cost_center", "purpose_keywords", "description", "sort_order"],
        order_by="sort_order asc")

    # 1. Check for learned Booking Rule (highest priority, direction-aware)
    booking_rule = _find_booking_rule(doc.counterparty_iban, direction)

    # 2. Auto-classify by keywords (fallback)
    auto_category = _auto_classify_transaction(doc, categories)

    # 3. Try to find party by IBAN
    party_match = _find_party_by_iban(doc.counterparty_iban, direction)

    # Booking Rule overrides both if available
    if booking_rule:
        auto_category = {
            "category": booking_rule["booking_category"],
            "source": "learned",
            "match_count": booking_rule.get("match_count", 0),
        }
        if booking_rule.get("party") and booking_rule.get("party_type"):
            party_match = {
                "party_type": booking_rule["party_type"],
                "party": booking_rule["party"],
                "party_name": "",
                "match_method": "learned",
            }

    # Get bank account info
    bank_account_doc = frappe.get_doc("Hibiscus Connect Bank Account", doc.bank_account)
    erpnext_account = bank_account_doc.erpnext_account if bank_account_doc.erpnext_account else ""

    # If the transaction is already booked, collect the linked booking docs
    # (Payment Entry via reference_no, Journal Entry via the custom
    # `hibiscus_connect_transaction` field) so the UI can show a summary
    # instead of the booking form.
    linked_bookings = _find_linked_bookings(doc.name)

    return {
        "transaction": {
            "name": doc.name,
            "amount": doc.amount,
            "abs_amount": abs_amount,
            "transaction_date": str(doc.transaction_date),
            "counterparty_name": doc.counterparty_name or "",
            "counterparty_iban": doc.counterparty_iban or "",
            "counterparty_bic": doc.counterparty_bic or "",
            "purpose": doc.purpose or "",
            "transaction_type": doc.transaction_type or "",
            "gvcode": doc.gvcode or "",
            "bank_account": doc.bank_account,
            "erpnext_account": erpnext_account,
            "status": doc.status,
        },
        "direction": direction,
        "categories": categories,
        "auto_category": auto_category,
        "party_match": party_match,
        "booking_rule": booking_rule,
        "linked_bookings": linked_bookings,
    }


PAYMENT_TYPE_DE = {
    "Receive": "Zahlungseingang",
    "Pay": "Zahlungsausgang",
    "Internal Transfer": "Interner Transfer",
}


def _find_linked_bookings(hib_trans_name):
    """Return Payment Entries / Journal Entries that reference this transaction,
    plus all Sales/Purchase Invoices allocated to those entries."""
    bookings = []

    pes = frappe.get_all("Payment Entry",
        filters={"reference_no": hib_trans_name, "docstatus": 1},
        fields=["name", "posting_date", "paid_amount", "payment_type",
                "party_type", "party"])
    for pe in pes:
        pt_de = PAYMENT_TYPE_DE.get(pe.payment_type or "", pe.payment_type or "")
        bookings.append({
            "doctype": "Payment Entry",
            "doctype_label": "Zahlung",
            "name": pe.name,
            "posting_date": str(pe.posting_date) if pe.posting_date else "",
            "amount": pe.paid_amount,
            "extra": f"{pt_de} – {pe.party or ''}".strip(" –"),
        })

        # Referenced invoices on this Payment Entry
        refs = frappe.get_all("Payment Entry Reference",
            filters={"parent": pe.name},
            fields=["reference_doctype", "reference_name", "allocated_amount"])
        for ref in refs:
            bookings.append(_make_invoice_entry(
                ref["reference_doctype"],
                ref["reference_name"],
                ref["allocated_amount"],
            ))

    # Journal Entry — custom field `hibiscus_connect_transaction`
    if frappe.db.has_column("Journal Entry", "hibiscus_connect_transaction"):
        jes = frappe.get_all("Journal Entry",
            filters={"hibiscus_connect_transaction": hib_trans_name, "docstatus": 1},
            fields=["name", "posting_date", "total_debit", "user_remark"])
        for je in jes:
            bookings.append({
                "doctype": "Journal Entry",
                "doctype_label": "Buchungssatz",
                "name": je.name,
                "posting_date": str(je.posting_date) if je.posting_date else "",
                "amount": je.total_debit,
                "extra": (je.user_remark or "")[:80],
            })

            # Referenced invoices on Journal Entry Accounts
            jea = frappe.get_all("Journal Entry Account",
                filters={
                    "parent": je.name,
                    "reference_type": ["in", ("Sales Invoice", "Purchase Invoice")],
                },
                fields=["reference_type", "reference_name", "debit_in_account_currency",
                        "credit_in_account_currency"])
            for ja in jea:
                amount = ja["debit_in_account_currency"] or ja["credit_in_account_currency"] or 0
                bookings.append(_make_invoice_entry(
                    ja["reference_type"],
                    ja["reference_name"],
                    amount,
                ))

    return bookings


INVOICE_LABELS = {
    "Sales Invoice": "Ausgangsrechnung",
    "Purchase Invoice": "Eingangsrechnung",
}


def _make_invoice_entry(doctype, name, allocated_amount):
    """Build a linked-bookings entry for an invoice reference."""
    label = INVOICE_LABELS.get(doctype, doctype)
    extra_parts = []
    if doctype == "Sales Invoice":
        fields = ["customer_name", "grand_total", "outstanding_amount"]
    elif doctype == "Purchase Invoice":
        fields = ["supplier_name", "grand_total", "outstanding_amount", "bill_no"]
    else:
        fields = ["grand_total", "outstanding_amount"]

    inv = frappe.db.get_value(doctype, name, fields, as_dict=True) or {}
    party_name = inv.get("customer_name") or inv.get("supplier_name") or ""
    if party_name:
        extra_parts.append(party_name[:50])
    if inv.get("bill_no"):
        extra_parts.append(f"Ext.Beleg: {inv['bill_no']}")
    outstanding = inv.get("outstanding_amount") or 0
    if outstanding > 0:
        extra_parts.append(f"noch offen: {frappe.utils.fmt_money(outstanding, currency='EUR')}")

    return {
        "doctype": doctype,
        "doctype_label": label,
        "name": name,
        "posting_date": "",
        "amount": allocated_amount or 0,
        "extra": " · ".join(extra_parts),
    }


def _auto_classify_transaction(doc, categories):
    """Rule-based auto-classification using purpose keywords."""
    purpose_lower = (doc.purpose or "").lower()
    tx_type_lower = (doc.transaction_type or "").lower()
    combined = purpose_lower + " " + tx_type_lower

    for cat in categories:
        keywords = cat.get("purpose_keywords") or ""
        if not keywords:
            continue
        for kw in keywords.split(","):
            kw = kw.strip().lower()
            if kw and kw in combined:
                return {
                    "category": cat["category_name"],
                    "matched_keyword": kw,
                }
    return None


def _find_party_by_iban(iban, direction):
    """Find a Supplier or Customer by counterparty IBAN."""
    if not iban:
        return None

    party_type = "Supplier" if direction == "Outgoing" else "Customer"
    accounts = frappe.get_all("Bank Account",
        filters={"iban": iban, "party_type": party_type},
        fields=["party", "party_type"])
    if accounts:
        party = accounts[0]["party"]
        party_name = frappe.db.get_value(party_type, party,
            "supplier_name" if party_type == "Supplier" else "customer_name")
        return {
            "party_type": party_type,
            "party": party,
            "party_name": party_name,
            "match_method": "iban",
        }

    # Also check the other direction for "Both" categories
    other_type = "Customer" if direction == "Outgoing" else "Supplier"
    accounts = frappe.get_all("Bank Account",
        filters={"iban": iban, "party_type": other_type},
        fields=["party", "party_type"])
    if accounts:
        party = accounts[0]["party"]
        name_field = "customer_name" if other_type == "Customer" else "supplier_name"
        party_name = frappe.db.get_value(other_type, party, name_field)
        return {
            "party_type": other_type,
            "party": party,
            "party_name": party_name,
            "match_method": "iban",
        }

    return None


def _find_booking_rule(iban, direction=None):
    """Look up a learned Booking Rule by counterparty IBAN.

    If `direction` is given (Incoming/Outgoing), the rule is only returned
    when its Booking Category's direction matches the transaction direction
    (or the category direction is "Both"). This prevents an outgoing-only
    category like "Sonstige Ausgabe" from being suggested for an incoming
    transaction.
    """
    if not iban:
        return None
    rule = frappe.db.get_value("Booking Rule",
        filters={"counterparty_iban": iban, "enabled": 1},
        fieldname=["booking_category", "party_type", "party",
                   "expense_account", "cost_center", "match_count",
                   "counterparty_name"],
        as_dict=True)
    if not rule:
        return None
    if direction and rule.get("booking_category"):
        cat_direction = frappe.db.get_value(
            "Booking Category", rule["booking_category"], "direction")
        if cat_direction and cat_direction not in (direction, "Both"):
            return None
    return rule


def _update_booking_rule(doc, booking_data, category):
    """Create or update a Booking Rule after successful booking (learning)."""
    iban = doc.counterparty_iban
    if not iban:
        return

    existing = frappe.db.exists("Booking Rule", {"counterparty_iban": iban})

    if existing:
        rule = frappe.get_doc("Booking Rule", existing)
        rule.match_count = (rule.match_count or 0) + 1
        rule.last_used = date.today()
        rule.counterparty_name = doc.counterparty_name or rule.counterparty_name
        # Update fields if they changed
        rule.booking_category = booking_data.get("category", rule.booking_category)
        if booking_data.get("party"):
            rule.party = booking_data["party"]
            rule.party_type = category.party_type or ""
        if booking_data.get("expense_account"):
            rule.expense_account = booking_data["expense_account"]
        if booking_data.get("cost_center"):
            rule.cost_center = booking_data["cost_center"]
        rule.save(ignore_permissions=True)
    else:
        rule = frappe.get_doc({
            "doctype": "Booking Rule",
            "counterparty_iban": iban,
            "counterparty_name": doc.counterparty_name or "",
            "booking_category": booking_data.get("category", ""),
            "party_type": category.party_type or "",
            "party": booking_data.get("party", ""),
            "expense_account": booking_data.get("expense_account", ""),
            "cost_center": booking_data.get("cost_center", ""),
            "match_count": 1,
            "last_used": date.today(),
            "enabled": 1,
        })
        rule.insert(ignore_permissions=True)


@frappe.whitelist()
def get_open_invoices(party_type, party):
    """Return open invoices for a party (Purchase Invoice or Sales Invoice)."""
    check_erpnext_required("Rechnungen laden")

    if party_type == "Supplier":
        invoices = frappe.get_all("Purchase Invoice",
            filters={
                "supplier": party,
                "docstatus": 1,
                "outstanding_amount": [">", 0],
            },
            fields=["name", "bill_no", "bill_date", "grand_total",
                     "outstanding_amount", "due_date", "posting_date"],
            order_by="due_date asc")
    elif party_type == "Customer":
        invoices = frappe.get_all("Sales Invoice",
            filters={
                "customer": party,
                "docstatus": 1,
                "outstanding_amount": [">", 0],
                "name": ["not like", "SINV-RET-%"],
            },
            fields=["name", "grand_total", "outstanding_amount",
                     "due_date", "posting_date"],
            order_by="due_date asc")
        # Sales Invoices don't have bill_no, use name as reference
        for inv in invoices:
            inv["bill_no"] = inv["name"]
            inv["bill_date"] = inv["posting_date"]
    else:
        return []

    today = date.today()
    for inv in invoices:
        inv["is_overdue"] = bool(inv.get("due_date") and inv["due_date"] < today)

    return invoices


@frappe.whitelist()
def book_transaction(hib_trans, booking_data):
    """Create the appropriate ERPNext booking document for a transaction."""
    check_erpnext_required("Verbuchen")

    if isinstance(booking_data, str):
        booking_data = json.loads(booking_data)

    doc = frappe.get_doc("Hibiscus Connect Transaction", hib_trans)
    category = frappe.get_doc("Booking Category", booking_data["category"])
    bank_account_doc = frappe.get_doc("Hibiscus Connect Bank Account", doc.bank_account)
    erpnext_account = bank_account_doc.erpnext_account
    abs_amount = abs(doc.amount)
    settings = frappe.get_single("Hibiscus Connect Settings")

    if category.booking_type == "Payment Entry":
        result = _create_payment_entry(doc, category, booking_data, erpnext_account, abs_amount, settings)
    else:
        result = _create_journal_entry(doc, category, booking_data, erpnext_account, abs_amount, settings)

    # Update transaction status and links
    doc.status = "manually booked"
    doc.add_link(result["doctype"], result["name"],
                 amount=abs_amount, note="Manuell verbucht")
    doc.save()
    frappe.db.commit()

    # Auto-create supplier bank account for future matching
    if (category.party_type == "Supplier"
            and booking_data.get("party")
            and doc.counterparty_iban):
        create_bank_account_for_supplier(
            booking_data["party"],
            doc.counterparty_iban,
            doc.counterparty_bic or "")

    # Learn: create/update Booking Rule for this IBAN
    _update_booking_rule(doc, booking_data, category)

    return {
        "doctype": result["doctype"],
        "name": result["name"],
        "message": f'{result["doctype"]} {result["name"]} erstellt.'
    }


def _create_payment_entry(doc, category, booking_data, erpnext_account, abs_amount, settings):
    """Create a Payment Entry based on category configuration."""
    pe_data = {
        "doctype": "Payment Entry",
        "payment_type": category.payment_type,
        "posting_date": doc.transaction_date,
        "reference_no": doc.name,
        "reference_date": doc.transaction_date,
        "hibiscus_connect_transaction": doc.name,
        "paid_amount": abs_amount,
        "received_amount": abs_amount,
        "source_exchange_rate": 1,
        "target_exchange_rate": 1,
    }

    if category.payment_type == "Pay":
        pe_data["paid_from"] = erpnext_account
        pe_data["party_type"] = category.party_type
        pe_data["party"] = booking_data.get("party", "")

        # Determine paid_to from invoice or party default
        invoices = booking_data.get("invoices", [])
        if invoices and category.party_type == "Supplier":
            first_inv = frappe.get_doc("Purchase Invoice", invoices[0]["name"])
            pe_data["paid_to"] = first_inv.credit_to
        elif category.party_type == "Supplier":
            pe_data["paid_to"] = frappe.db.get_value("Company",
                frappe.defaults.get_defaults().get("company"),
                "default_payable_account")

    elif category.payment_type == "Receive":
        pe_data["paid_to"] = erpnext_account
        pe_data["party_type"] = category.party_type
        pe_data["party"] = booking_data.get("party", "")

        invoices = booking_data.get("invoices", [])
        if invoices and category.party_type == "Customer":
            first_inv = frappe.get_doc("Sales Invoice", invoices[0]["name"])
            pe_data["paid_from"] = first_inv.debit_to
        elif category.party_type == "Customer":
            pe_data["paid_from"] = frappe.db.get_value("Company",
                frappe.defaults.get_defaults().get("company"),
                "default_receivable_account")

    elif category.payment_type == "Internal Transfer":
        pe_data["paid_from"] = erpnext_account
        pe_data["paid_to"] = booking_data.get("target_account", "")

    pe = frappe.get_doc(pe_data)

    # Add invoice references
    invoices = booking_data.get("invoices", [])
    if invoices:
        inv_doctype = "Purchase Invoice" if category.party_type == "Supplier" else "Sales Invoice"
        for inv_ref in invoices:
            inv_doc = frappe.get_doc(inv_doctype, inv_ref["name"])
            pe.append("references", {
                "reference_doctype": inv_doctype,
                "reference_name": inv_ref["name"],
                "due_date": inv_doc.due_date,
                "total_amount": inv_doc.grand_total,
                "outstanding_amount": inv_doc.outstanding_amount,
                "allocated_amount": float(inv_ref.get("allocated_amount", inv_doc.outstanding_amount)),
            })

    pe.save()

    if settings.auto_submit_payment_entry and pe.references:
        if pe.difference_amount == 0:
            pe.submit()

    return {"doctype": "Payment Entry", "name": pe.name}


def _create_journal_entry(doc, category, booking_data, erpnext_account, abs_amount, settings):
    """Create a Journal Entry for expense/income bookings."""
    expense_account = booking_data.get("expense_account") or category.default_account
    cost_center = booking_data.get("cost_center") or category.default_cost_center or ""
    remark = booking_data.get("remark") or doc.purpose or ""

    if not expense_account:
        frappe.throw("Kein Aufwandskonto angegeben.")

    is_outgoing = doc.amount < 0

    accounts = []
    if is_outgoing:
        # Outgoing: debit expense, credit bank
        accounts = [
            {
                "account": expense_account,
                "debit_in_account_currency": abs_amount,
                "credit_in_account_currency": 0,
                "cost_center": cost_center,
            },
            {
                "account": erpnext_account,
                "debit_in_account_currency": 0,
                "credit_in_account_currency": abs_amount,
            }
        ]
    else:
        # Incoming: debit bank, credit income
        accounts = [
            {
                "account": erpnext_account,
                "debit_in_account_currency": abs_amount,
                "credit_in_account_currency": 0,
            },
            {
                "account": expense_account,
                "debit_in_account_currency": 0,
                "credit_in_account_currency": abs_amount,
                "cost_center": cost_center,
            }
        ]

    je = frappe.get_doc({
        "doctype": "Journal Entry",
        "voucher_type": "Bank Entry",
        "posting_date": doc.transaction_date,
        "cheque_no": doc.name,
        "cheque_date": doc.transaction_date,
        "user_remark": remark,
        "hibiscus_connect_transaction": doc.name,
        "accounts": accounts,
    })
    je.save()

    return {"doctype": "Journal Entry", "name": je.name}
