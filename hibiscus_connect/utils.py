import frappe

def is_erpnext_installed():
    """Check if ERPNext app is installed"""
    return "erpnext" in frappe.get_installed_apps()


def check_erpnext_required(feature_name="Diese Funktion"):
    """Throw error if ERPNext is not installed"""
    if not is_erpnext_installed():
        frappe.throw(
            f"{feature_name} benötigt ERPNext. "
            "Bitte installieren Sie ERPNext oder deaktivieren Sie diese Funktion."
        )
