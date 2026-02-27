import frappe
from hibiscus_connect.tools import get_transactions_for_account


def refresh_lastschrift_cache():
    """Wrapper für den Lastschrift-Cache Refresh Job"""
    from hibiscus_connect.hibiscus_connect.doctype.hibiscus_connect_sepa_lastschrift_funktionen.hibiscus_connect_sepa_lastschrift_funktionen import refresh_lastschrift_cache as do_refresh
    do_refresh()


def refresh_ueberweisung_cache():
    """Wrapper für den Überweisungs-Cache Refresh Job"""
    from hibiscus_connect.hibiscus_connect.doctype.hibiscus_connect_sepa_lastschrift_funktionen.hibiscus_connect_sepa_lastschrift_funktionen import refresh_ueberweisung_cache as do_refresh
    do_refresh()


def fetch_transactions_from_active_accounts():
    print("starte Umsatzabruf")
    accounts = frappe.get_all("Hibiscus Connect Bank Account", filters={
        "fetch_periodically": 1
    })
    if accounts:
        for account in accounts:
            print("verarbeite account " + str(account["name"]))
            get_transactions_for_account(account["name"])
    else:
        print("keine Accounts für Abruf gefunden")

