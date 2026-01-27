import frappe
from hibiscus_connect.utils import is_erpnext_installed


def execute():
    """Remove ERPNext-dependent dashboard charts and update workspace when ERPNext is not installed"""

    # Always delete the ERPNext-dependent dashboard charts as they're no longer used
    charts_to_delete = [
        "offene Ausgangsrechnungen",
        "Unverbuchte Zahlungseingänge"
    ]

    for chart_name in charts_to_delete:
        if frappe.db.exists("Dashboard Chart", chart_name):
            frappe.delete_doc("Dashboard Chart", chart_name, force=True)
            print(f"Deleted Dashboard Chart: {chart_name}")

    # Update the workspace to remove chart references
    if frappe.db.exists("Workspace", "Banking"):
        workspace = frappe.get_doc("Workspace", "Banking")

        # Clear charts
        workspace.charts = []

        # Update content to remove chart blocks
        import json
        try:
            content = json.loads(workspace.content) if workspace.content else []
            # Filter out chart type blocks
            content = [block for block in content if block.get("type") != "chart"]
            workspace.content = json.dumps(content)
        except (json.JSONDecodeError, TypeError):
            pass

        workspace.save(ignore_permissions=True)
        print("Updated Banking workspace to remove chart references")

    frappe.db.commit()
