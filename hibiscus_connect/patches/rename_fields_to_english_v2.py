"""
Follow-up patch for field renames that were missed in v1.

v1 only handled regular tables (Transaction, Transaction Link, Bank Account).
This patch handles:
1. Settings field renames via tabSingles UPDATE
2. SEPA Lastschrift Mandat column renames via ALTER TABLE (using sql_ddl)
3. Transaction status value updates (DE -> EN)
4. Transaction Link status value updates (DE -> EN)

The patch is idempotent.
"""

import frappe


def execute():
    """Run the remaining field rename operations."""
    _rename_settings_fields()
    _rename_sepa_mandat_columns()
    _update_transaction_status_values()
    _update_transaction_link_status_values()

    frappe.db.commit()
    print("Field rename v2 migration completed successfully.")


# --- Settings (Single DocType -> tabSingles) ---

def _rename_settings_fields():
    """Rename field names in tabSingles for Hibiscus Connect Settings."""
    print("\nRenaming Settings fields in tabSingles...")

    renames = [
        ("submit_pe", "auto_submit_payment_entry"),
        ("debit_charge_active", "sepa_direct_debit_enabled"),
        ("konto", "creditor_iban"),
        ("konto_id", "creditor_account_id"),
        ("creditorid", "creditor_id"),
    ]

    for old_field, new_field in renames:
        exists = frappe.db.sql(
            "SELECT COUNT(*) FROM tabSingles WHERE doctype='Hibiscus Connect Settings' AND field=%s",
            old_field
        )[0][0]

        if exists:
            new_exists = frappe.db.sql(
                "SELECT COUNT(*) FROM tabSingles WHERE doctype='Hibiscus Connect Settings' AND field=%s",
                new_field
            )[0][0]

            if new_exists:
                frappe.db.sql(
                    "DELETE FROM tabSingles WHERE doctype='Hibiscus Connect Settings' AND field=%s",
                    old_field
                )
                print(f"  Deleted duplicate {old_field} (already has {new_field})")
            else:
                frappe.db.sql(
                    "UPDATE tabSingles SET field=%s WHERE doctype='Hibiscus Connect Settings' AND field=%s",
                    (new_field, old_field)
                )
                print(f"  Renamed {old_field} -> {new_field}")
        else:
            print(f"  Skipped {old_field} (not found or already renamed)")


# --- SEPA Mandat (regular table, uses sql_ddl for ALTER TABLE) ---

def _column_exists(table, column):
    """Check if a column exists in a table."""
    result = frappe.db.sql(
        "SHOW COLUMNS FROM `{table}` LIKE %s".format(table=table),
        column
    )
    return len(result) > 0


def _rename_column(table, old_name, new_name):
    """Rename a column using sql_ddl to handle implicit commit properly."""
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

            frappe.db.sql_ddl(
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


def _rename_sepa_mandat_columns():
    """Rename columns in tabSEPA Lastschrift Mandat."""
    table = "tabSEPA Lastschrift Mandat"
    print(f"\nRenaming columns in {table}...")

    tables = frappe.db.sql("SHOW TABLES LIKE %s", table)
    if not tables:
        print(f"  Table {table} does not exist, skipping.")
        return

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


# --- Status value updates ---

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
        u"m\u00f6gliche Doppelzahlung": "possible duplicate",
    }

    for old_val, new_val in status_mapping.items():
        frappe.db.sql(
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

    tables = frappe.db.sql("SHOW TABLES LIKE %s", table)
    if not tables:
        print(f"  Table {table} does not exist, skipping.")
        return

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
