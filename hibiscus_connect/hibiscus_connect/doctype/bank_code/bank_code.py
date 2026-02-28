# Copyright (c) 2025, itsdave GmbH and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document


class BankCode(Document):
    pass


@frappe.whitelist()
def get_bank_by_blz(blz):
    """
    Look up bank information by BLZ.

    Args:
        blz: 8-digit bank code

    Returns:
        dict: Bank information or None if not found
    """
    if not blz:
        return None

    # Pad BLZ to 8 digits if necessary
    blz = str(blz).zfill(8)

    if frappe.db.exists("Bank Code", blz):
        doc = frappe.get_doc("Bank Code", blz)
        return {
            "blz": doc.blz,
            "bic": doc.bic,
            "bank_name": doc.bezeichnung,
            "short_name": doc.kurzbezeichnung,
            "plz": doc.plz,
            "city": doc.ort,
            "country": doc.country
        }
    return None


@frappe.whitelist()
def get_bank_by_bic(bic):
    """
    Look up bank information by BIC.

    Args:
        bic: Bank Identifier Code (SWIFT code)

    Returns:
        list: List of matching banks (BIC may map to multiple BLZ)
    """
    if not bic:
        return []

    banks = frappe.get_all("Bank Code",
        filters={"bic": bic},
        fields=["blz", "bic", "bezeichnung", "kurzbezeichnung", "plz", "ort", "country"]
    )
    return banks
