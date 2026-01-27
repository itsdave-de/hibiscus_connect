import frappe
from frappe import _

def get_context(context):
    '''Context für die Matching Dashboard Page'''
    context.no_cache = 1
    context.title = _('Matching Dashboard')

    # Prüfe ob User eingeloggt ist
    if frappe.session.user == 'Guest':
        frappe.throw(_('Sie müssen eingeloggt sein, um diese Seite zu sehen.'))

    # Prüfe Berechtigungen - nur Banking Manager und System Manager
    allowed_roles = ['Banking Manager', 'System Manager']
    user_roles = frappe.get_roles(frappe.session.user)
    
    if not any(role in allowed_roles for role in user_roles):
        frappe.throw(
            _('Sie haben keine Berechtigung, diese Seite zu sehen. Erforderliche Rollen: {0}').format(', '.join(allowed_roles)),
            frappe.PermissionError
        )

    return context
