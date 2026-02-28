"""
Rename German field names to English across all Hibiscus Connect DocTypes.

This patch uses RENAME COLUMN (instant DDL in MariaDB >= 10.3, no table rebuild)
and UPDATE with WHERE clause (only affects rows with old values).

The patch is idempotent — it checks if old columns exist before renaming.
"""

import frappe
from frappe.utils import cint


def execute():
    """Run the field rename migration."""
    _rename_transaction_columns()
    _rename_transaction_link_columns()
    _rename_bank_account_columns()
    _rename_settings_columns()
    _rename_sepa_mandat_columns()

    _update_transaction_status_values()
    _update_transaction_link_status_values()

    frappe.db.commit()
    print("Field rename migration completed successfully.")


def _column_exists(table, column):
    """Check if a column exists in a table."""
    result = frappe.db.sql(
        "SHOW COLUMNS FROM `{table}` LIKE %s".format(table=table),
        column
    )
    return len(result) > 0


def _rename_column(table, old_name, new_name):
    """Rename a column if the old name exists and new name doesn't."""
    if _column_exists(table, old_name) and not _column_exists(table, new_name):
        # Get column definition to preserve type
        col_info = frappe.db.sql(
            "SHOW COLUMNS FROM `{table}` LIKE %s".format(table=table),
            old_name,
            as_dict=True
        )
        if col_info:
            col_type = col_info[0]["Type"]
            null_clause = "NULL" if col_info[0]["Null"] == "YES" else "NOT NULL"
            default = col_info[0]["Default"]
            default_clause = ""
            if default is not None:
                default_clause = f"DEFAULT '{default}'"
            elif col_info[0]["Null"] == "YES":
                default_clause = "DEFAULT NULL"

            frappe.db.sql(
                "ALTER TABLE `{table}` CHANGE `{old}` `{new}` {type} {null} {default}".format(
                    table=table,
                    old=old_name,
                    new=new_name,
                    type=col_type,
                    null=null_clause,
                    default=default_clause
                )
            )
            print(f"  Renamed {table}.{old_name} -> {new_name}")
    elif _column_exists(table, new_name):
        print(f"  Skipped {table}.{old_name} (already renamed to {new_name})")
    else:
        print(f"  Skipped {table}.{old_name} (column not found)")


def _rename_transaction_columns():
    """Rename columns in tabHibiscus Connect Transaction."""
    table = "tabHibiscus Connect Transaction"
    print(f"\nRenaming columns in {table}...")

    renames = [
        ("art", "transaction_type"),
        ("betrag", "amount"),
        ("datum", "transaction_date"),
        ("empfaenger_blz", "counterparty_bic"),
        ("empfaenger_konto", "counterparty_iban"),
        ("empfaenger_name", "counterparty_name"),
        ("id", "hibiscus_id"),
        ("kommentar", "hibiscus_comment"),
        ("konto_id", "hibiscus_account_id"),
        ("saldo", "balance"),
        ("valuta", "value_date"),
        ("zweck", "purpose"),
        ("zweck_raw", "purpose_raw"),
        ("protokoll", "log"),
        ("konto", "bank_account"),
    ]

    for old_name, new_name in renames:
        _rename_column(table, old_name, new_name)


def _rename_transaction_link_columns():
    """Rename columns in tabHibiscus Connect Transaction Link."""
    table = "tabHibiscus Connect Transaction Link"
    print(f"\nRenaming columns in {table}...")

    # Check if table exists (it might not on fresh installs)
    tables = frappe.db.sql("SHOW TABLES LIKE %s", table)
    if not tables:
        print(f"  Table {table} does not exist, skipping.")
        return

    renames = [
        ("betrag", "amount"),
        ("bemerkung", "note"),
        ("verknuepft_am", "linked_at"),
    ]

    for old_name, new_name in renames:
        _rename_column(table, old_name, new_name)


def _rename_bank_account_columns():
    """Rename columns in tabHibiscus Connect Bank Account."""
    table = "tabHibiscus Connect Bank Account"
    print(f"\nRenaming columns in {table}...")

    renames = [
        ("name1", "account_holder"),
        ("saldo", "balance"),
        ("saldo_available", "available_balance"),
        ("saldo_datum", "balance_date"),
        ("id", "hibiscus_id"),
        ("kommentar", "hibiscus_comment"),
        ("kontonummer", "account_number"),
        ("blz", "bank_code"),
        ("waehrung", "currency"),
        ("unterkonto", "sub_account"),
        ("kundennummer", "customer_number"),
        ("bezeichnung", "account_name_from_bank"),
        ("fetch_periodically", "auto_fetch"),
        ("erpnext_bankkonto", "erpnext_account"),
    ]

    for old_name, new_name in renames:
        _rename_column(table, old_name, new_name)


def _rename_settings_columns():
    """Rename columns in tabHibiscus Connect Settings."""
    table = "tabHibiscus Connect Settings"
    print(f"\nRenaming columns in {table}...")

    renames = [
        ("submit_pe", "auto_submit_payment_entry"),
        ("debit_charge_active", "sepa_direct_debit_enabled"),
        ("konto", "creditor_iban"),
        ("konto_id", "creditor_account_id"),
        ("creditorid", "creditor_id"),
    ]

    for old_name, new_name in renames:
        _rename_column(table, old_name, new_name)


def _rename_sepa_mandat_columns():
    """Rename columns in tabSEPA Lastschrift Mandat."""
    table = "tabSEPA Lastschrift Mandat"
    print(f"\nRenaming columns in {table}...")

    renames = [
        ("frst", "first_debit_done"),
        ("final", "is_final_debit"),
        ("mandateid", "mandate_reference"),
        ("gegenkonto_name", "debtor_name"),
        ("kontonummer", "debtor_iban"),
        ("blz", "debtor_bic"),
        ("creditorid", "creditor_id"),
        ("sigdate", "signature_date"),
        ("sepatype", "sepa_type"),
        ("konto", "creditor_iban"),
        ("konto_id", "creditor_account_id"),
    ]

    for old_name, new_name in renames:
        _rename_column(table, old_name, new_name)


def _update_transaction_status_values():
    """Update German status values to English in Hibiscus Connect Transaction."""
    table = "tabHibiscus Connect Transaction"
    print(f"\nUpdating status values in {table}...")

    status_mapping = {
        "neu": "new",
        "automatisch verbucht": "auto booked",
        "teilweise automatisch verbucht": "partially auto booked",
        "manuell verbucht": "manually booked",
        "teilweise verbucht": "partially booked",
        "legacy verbucht": "legacy booked",
        "abgebrochen": "cancelled",
        "andere Einnahme": "other income",
        "mögliche Doppelzahlung": "possible duplicate",
    }

    for old_val, new_val in status_mapping.items():
        result = frappe.db.sql(
            "UPDATE `{table}` SET `status` = %s WHERE `status` = %s".format(table=table),
            (new_val, old_val)
        )
        affected = frappe.db.sql("SELECT ROW_COUNT() as cnt")[0][0]
        if affected:
            print(f"  Updated {affected} rows: '{old_val}' -> '{new_val}'")


def _update_transaction_link_status_values():
    """Update German link_status values to English in Hibiscus Connect Transaction Link."""
    table = "tabHibiscus Connect Transaction Link"
    print(f"\nUpdating link_status values in {table}...")

    # Check if table exists
    tables = frappe.db.sql("SHOW TABLES LIKE %s", table)
    if not tables:
        print(f"  Table {table} does not exist, skipping.")
        return

    # Check if link_status column exists
    if not _column_exists(table, "link_status"):
        print(f"  Column link_status not found, skipping.")
        return

    status_mapping = {
        "aktiv": "active",
        "storniert": "cancelled",
        "ersetzt": "replaced",
    }

    for old_val, new_val in status_mapping.items():
        frappe.db.sql(
            "UPDATE `{table}` SET `link_status` = %s WHERE `link_status` = %s".format(table=table),
            (new_val, old_val)
        )
        affected = frappe.db.sql("SELECT ROW_COUNT() as cnt")[0][0]
        if affected:
            print(f"  Updated {affected} rows: '{old_val}' -> '{new_val}'")
