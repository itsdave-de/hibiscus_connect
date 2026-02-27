import frappe

def execute():
    """Aktualisiert den SEPA Lastschrift Dashboard Custom HTML Block auf kompaktes Design"""

    if not frappe.db.exists("Custom HTML Block", "SEPA Lastschrift Dashboard"):
        print("Custom HTML Block nicht gefunden.")
        return

    script = """// SEPA Lastschrift Dashboard - Kompakt
frappe.call({
    method: 'hibiscus_connect.hibiscus_connect.doctype.hibiscus_connect_sepa_lastschrift_funktionen.hibiscus_connect_sepa_lastschrift_funktionen.get_dashboard_data',
    callback: function(r) {
        const $loading = root_element.querySelector('.sepa-dashboard-loading');
        const $content = root_element.querySelector('.sepa-dashboard-content');

        if (r.message) {
            const data = r.message;
            const hasOverdue = data.count_faellig > 0;
            const statusClass = hasOverdue ? 'red' : 'green';
            const lastCheck = data.last_check ? frappe.datetime.str_to_user(data.last_check) : '-';

            let html = `
                <div style="display: flex; align-items: center; gap: 15px; padding: 12px 15px; background: var(--card-bg); border: 1px solid var(--border-color); border-radius: 8px; flex-wrap: wrap;">
                    <div style="display: flex; align-items: center; gap: 8px;">
                        <span class="indicator-pill ${statusClass}" style="padding: 3px 6px;">
                            <svg class="icon icon-xs"><use href="#icon-${hasOverdue ? 'alert-circle' : 'check'}"></use></svg>
                        </span>
                        <span style="font-weight: 600; font-size: 13px;">SEPA</span>
                    </div>
                    <div style="border-left: 1px solid var(--border-color); padding-left: 15px;">
                        <span class="text-muted" style="font-size: 11px;">Fällig:</span>
                        <span style="font-weight: 600; margin-left: 4px; ${hasOverdue ? 'color: var(--red-500);' : ''}">${data.count_faellig}</span>
                        <span class="text-muted" style="margin-left: 2px;">(${data.total_faellig_formatted})</span>
                    </div>
                    <div style="border-left: 1px solid var(--border-color); padding-left: 15px;">
                        <span class="text-muted" style="font-size: 11px;">Offen:</span>
                        <span style="font-weight: 600; margin-left: 4px;">${data.count_offen}</span>
                        <span class="text-muted" style="margin-left: 2px;">(${data.total_offen})</span>
                    </div>
                    <div style="margin-left: auto; display: flex; align-items: center; gap: 10px;">
                        <span class="text-muted" style="font-size: 10px;">${lastCheck}</span>
                        <a href="/app/hibiscus-connect-sepa-lastschrift-funktionen" class="btn btn-xs btn-default">Details</a>
                    </div>
                </div>
            `;

            $content.innerHTML = html;
            $loading.style.display = 'none';
            $content.style.display = 'block';
        } else {
            $loading.innerHTML = '<span class="text-muted">Keine Daten</span>';
        }
    },
    error: function() {
        root_element.querySelector('.sepa-dashboard-loading').innerHTML = '<span class="text-danger">Fehler</span>';
    }
});"""

    doc = frappe.get_doc("Custom HTML Block", "SEPA Lastschrift Dashboard")
    doc.script = script
    doc.save(ignore_permissions=True)
    frappe.db.commit()

    print("Custom HTML Block wurde auf kompaktes Design aktualisiert.")
