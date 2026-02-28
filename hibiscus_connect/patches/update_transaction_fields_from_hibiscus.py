# Copyright (c) 2025, itsdave GmbH and contributors
# For license information, please see license.txt

"""
Patch to update existing transactions with end_to_end_id and full purpose
from Hibiscus database.

This patch:
1. Connects to Hibiscus MariaDB via SSH
2. Fetches end_to_end_id and full zweck for each transaction
3. Updates the Frappe transactions with the missing data
"""

import frappe
import subprocess
import json


def execute():
    """Update transactions with end_to_end_id and full purpose from Hibiscus DB."""

    # Fetch data from Hibiscus database via SSH
    hibiscus_data = fetch_hibiscus_data_via_ssh()

    if not hibiscus_data:
        frappe.log_error("No data fetched from Hibiscus DB", "Migration Warning")
        return

    frappe.log_error(f"Fetched {len(hibiscus_data)} transactions from Hibiscus DB", "Migration Info")

    # Get all Frappe transactions that need updating
    transactions = frappe.get_all(
        "Hibiscus Connect Transaction",
        fields=["name", "hibiscus_id", "end_to_end_id", "purpose"],
        filters={"hibiscus_id": ["is", "set"]}
    )

    updated_count = 0
    for trans in transactions:
        hib_id = trans.hibiscus_id
        if hib_id and hib_id in hibiscus_data:
            data = hibiscus_data[hib_id]
            updates = {}

            # Update end_to_end_id if empty or NOTPROVIDED
            new_e2e = data.get('end_to_end_id', '')
            if new_e2e and new_e2e != 'NOTPROVIDED' and new_e2e != 'NULL':
                current_e2e = trans.end_to_end_id or ''
                if not current_e2e or current_e2e == 'NOTPROVIDED':
                    updates['end_to_end_id'] = new_e2e

            # Update purpose if the new one is longer (more complete)
            new_purpose = data.get('full_zweck', '')
            current_purpose = trans.purpose or ''
            if new_purpose and len(new_purpose) > len(current_purpose):
                updates['purpose'] = new_purpose
                updates['purpose_raw'] = new_purpose

            if updates:
                frappe.db.set_value("Hibiscus Connect Transaction", trans.name, updates)
                updated_count += 1

    frappe.db.commit()
    frappe.log_error(f"Updated {updated_count} transactions with end_to_end_id and purpose", "Migration Complete")


def fetch_hibiscus_data_via_ssh():
    """Fetch transaction data from Hibiscus DB via SSH."""

    # SQL query to get all relevant data
    sql_query = """
    SELECT
        id,
        COALESCE(endtoendid, '') as endtoendid,
        COALESCE(CONCAT_WS(' ', zweck, zweck2, zweck3), zweck, '') as full_zweck
    FROM umsatz;
    """

    # Execute via SSH
    ssh_command = [
        "ssh", "root@hbci.suedsee-camp.de",
        f'mysql -u hibiscus -peOHQfzZXDR4zUcenBWF0g hibiscus -N -e "{sql_query}"'
    ]

    try:
        result = subprocess.run(
            ssh_command,
            capture_output=True,
            text=True,
            timeout=120
        )

        if result.returncode != 0:
            frappe.log_error(f"SSH command failed: {result.stderr}", "Migration Error")
            return {}

        # Parse tab-separated output
        hibiscus_data = {}
        for line in result.stdout.strip().split('\n'):
            if not line:
                continue
            parts = line.split('\t')
            if len(parts) >= 3:
                hib_id = parts[0]
                hibiscus_data[hib_id] = {
                    'end_to_end_id': parts[1] if parts[1] != 'NULL' else '',
                    'full_zweck': parts[2] if parts[2] != 'NULL' else ''
                }

        return hibiscus_data

    except subprocess.TimeoutExpired:
        frappe.log_error("SSH command timed out", "Migration Error")
        return {}
    except Exception as e:
        frappe.log_error(f"Error fetching data via SSH: {e}", "Migration Error")
        return {}
