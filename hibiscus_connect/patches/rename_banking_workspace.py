import frappe


def execute():
    """Rename Hibiscus 'Banking' workspace to 'itsBanking' to avoid collision with ERPNext.

    The legacy workspace was named 'Banking', which collided with ERPNext's 'banking'
    Workspace Sidebar at the same /desk/banking route — the ERPNext sidebar would win
    the route and the Hibiscus content was hidden. The corresponding JSON file has
    been moved to workspace/itsbanking/itsbanking.json with name 'itsBanking'.
    """
    if not frappe.db.exists("Workspace", "Banking"):
        return
    module = frappe.db.get_value("Workspace", "Banking", "module")
    if module != "Hibiscus Connect":
        # Not our workspace — leave it alone
        return
    if frappe.db.exists("Workspace", "itsBanking"):
        # Both exist — drop the legacy one
        frappe.delete_doc("Workspace", "Banking", force=True, ignore_permissions=True)
        return
    frappe.rename_doc("Workspace", "Banking", "itsBanking", force=True, ignore_permissions=True)
    # Update legacy desktop icon link if it still points to the old route
    if frappe.db.exists("Desktop Icon", "itsdave Banking"):
        link = frappe.db.get_value("Desktop Icon", "itsdave Banking", "link")
        if link == "/desk/banking":
            frappe.db.set_value("Desktop Icon", "itsdave Banking", "link", "/desk/itsbanking")
