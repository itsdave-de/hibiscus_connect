import frappe
from hibiscus_connect.utils import is_erpnext_installed


def after_install():
    """Run after app installation"""
    if is_erpnext_installed():
        create_custom_fields()


def after_migrate():
    """Run after bench migrate"""
    if is_erpnext_installed():
        create_custom_fields()


def create_custom_fields():
    """Create custom fields for ERPNext doctypes"""
    from frappe.custom.doctype.custom_field.custom_field import create_custom_fields as _create_custom_fields

    custom_fields = {
        "Payment Entry": [
            {
                "fieldname": "hibiscus_connect_transaction",
                "fieldtype": "Link",
                "label": "Hibiscus Connect Transaction",
                "options": "Hibiscus Connect Transaction",
                "insert_after": "payment_order",
                "read_only": 0
            }
        ]
    }

    _create_custom_fields(custom_fields, update=True)
