# Copyright (c) 2025, itsdave GmbH and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document


class GVCodeMapping(Document):
    def validate(self):
        """Validate the GVCode format."""
        if self.gvcode and not self.gvcode.isdigit():
            frappe.throw("GVCode must contain only digits")

        # Pad GVCode to 5 digits if needed
        if self.gvcode and len(self.gvcode) < 5:
            self.gvcode = self.gvcode.zfill(5)


def get_gvcode(bic, transaction_type, primanota):
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


def get_gvcode_with_description(bic, transaction_type, primanota):
    """
    Look up the GVCode and its description for a given combination.

    Args:
        bic: Bank Identifier Code (SWIFT)
        transaction_type: Hibiscus transaction type (art)
        primanota: Bank's internal booking reference

    Returns:
        tuple: (gvcode, description) if found, (None, None) otherwise
    """
    if not transaction_type or not primanota:
        return None, None

    # Try exact BIC match first
    if bic:
        result = frappe.db.get_value(
            "GVCode Mapping",
            {
                "bic": bic,
                "transaction_type": transaction_type,
                "primanota": primanota
            },
            ["gvcode", "gvcode_description"],
            as_dict=True
        )
        if result:
            return result.gvcode, result.gvcode_description

    # Fall back to default mapping (BIC = '*')
    result = frappe.db.get_value(
        "GVCode Mapping",
        {
            "bic": "*",
            "transaction_type": transaction_type,
            "primanota": primanota
        },
        ["gvcode", "gvcode_description"],
        as_dict=True
    )

    if result:
        return result.gvcode, result.gvcode_description

    return None, None
