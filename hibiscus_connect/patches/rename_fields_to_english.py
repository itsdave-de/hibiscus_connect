"""
Rename German field names to English across regular-table DocTypes.

This patch handles Transaction, Transaction Link, and Bank Account tables.
Settings (Single DocType) and SEPA Mandat are handled in rename_fields_to_english_v2.

The patch is idempotent — it checks if old columns exist before renaming.
"""

import frappe


def execute():
    """Run the field rename migration for regular tables."""
    _rename_transaction_columns()
    _rename_transaction_link_columns()
    _rename_bank_account_columns()

    frappe.db.commit()
    print("Field rename v1 migration completed successfully.")


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
