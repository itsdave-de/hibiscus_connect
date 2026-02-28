"""
One-time patch to set status='chargeback' on existing unprocessed
SEPA direct debit reversals (GV code 108, negative amount, status 'new').
"""

import frappe


def execute():
    """Flag existing chargeback transactions."""
    updated = frappe.db.sql("""
        UPDATE `tabHibiscus Connect Transaction`
        SET `status` = 'chargeback'
        WHERE `gvcode` = '108'
          AND `amount` < 0
          AND `status` = 'new'
    """)

    count = frappe.db.sql("SELECT ROW_COUNT() as cnt")[0][0]
    frappe.db.commit()
    print(f"Set {count} transactions to 'chargeback' status.")
