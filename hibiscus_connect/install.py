import frappe
from hibiscus_connect.utils import is_erpnext_installed


def after_install():
    """Run after app installation"""
    if is_erpnext_installed():
        create_custom_fields()
    update_quick_export_block()


def after_migrate():
    """Run after bench migrate"""
    if is_erpnext_installed():
        create_custom_fields()
    update_quick_export_block()


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


def update_quick_export_block():
    """Update the Quick Export custom block with file download functionality."""
    if not frappe.db.exists("Custom HTML Block", "Quick Export"):
        return

    html = '''<div id="quick-export-widget">
    <div class="widget-head">
        <div class="widget-label">
            <span class="widget-title"><i class="fa fa-download"></i> Schnellexport</span>
        </div>
    </div>
    <div class="widget-body">
        <div id="quick-export-list">
            <div class="loading-state">
                <i class="fa fa-spinner fa-spin"></i> Lade Exporte...
            </div>
        </div>
    </div>
</div>'''

    script = '''
function getContrastMode(hexcolor) {
    hexcolor = (hexcolor || "#667eea").replace("#", "");
    const r = parseInt(hexcolor.substr(0, 2), 16);
    const g = parseInt(hexcolor.substr(2, 2), 16);
    const b = parseInt(hexcolor.substr(4, 2), 16);
    const luminance = (0.299 * r + 0.587 * g + 0.114 * b) / 255;
    return luminance > 0.5 ? "dark" : "light";
}

function getTextMode(textColorSetting, accentColor1) {
    if (textColorSetting === "Light") return "light";
    if (textColorSetting === "Dark") return "dark";
    return getContrastMode(accentColor1);
}

function formatFileSize(bytes) {
    if (!bytes) return "";
    if (bytes < 1024) return bytes + " B";
    if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + " KB";
    return (bytes / (1024 * 1024)).toFixed(1) + " MB";
}

function formatDate(dateStr) {
    if (!dateStr) return "";
    return frappe.datetime.str_to_user(dateStr);
}

function formatDateTime(datetimeStr) {
    if (!datetimeStr) return "";
    let date = frappe.datetime.str_to_user(datetimeStr.split(" ")[0]);
    let time = datetimeStr.split(" ")[1];
    if (time) {
        time = time.substring(0, 5); // HH:MM
    }
    return date + " " + (time || "");
}

frappe.call({
    method: "hibiscus_connect.hibiscus_connect.doctype.bank_statement_export.bank_statement_export.get_dashboard_exports",
    callback: function(r) {
        let container = root_element.querySelector("#quick-export-list");
        if (!r.message || r.message.length === 0) {
            container.innerHTML = `
                <div class="empty-state">
                    <i class="fa fa-file-o"></i>
                    <div>Keine Exporte für das Dashboard konfiguriert.</div>
                    <div style="font-size: 11px; margin-top: 5px;">
                        Aktivieren Sie "Auf Dashboard anzeigen" bei einem Export.
                    </div>
                </div>
            `;
            return;
        }

        let html = "";
        r.message.forEach(function(exp) {
            let title = exp.description || exp.name;

            let account_info = [];
            if (exp.account_type) account_info.push(exp.account_type);
            if (exp.account_description) account_info.push(exp.account_description);

            let color1 = exp.accent_color_1 || "#667eea";
            let color2 = exp.accent_color_2 || "#764ba2";
            let textMode = getTextMode(exp.text_color, color1);
            let textColor = textMode === "light" ? "#ffffff" : "#333333";

            // Build files list
            let filesHtml = "";
            if (exp.files && exp.files.length > 0) {
                exp.files.forEach(function(file) {
                    let dateStr = "";
                    if (file.from_date) {
                        dateStr = formatDate(file.from_date);
                        if (file.to_date && file.to_date !== file.from_date) {
                            dateStr += " - " + formatDate(file.to_date);
                        }
                    }
                    let fileSize = formatFileSize(file.file_size);
                    let fileName = file.file_name || "";
                    let createdAt = file.creation ? formatDateTime(file.creation) : "";
                    let createdBy = file.owner || "";

                    filesHtml += `
                        <a href="${file.file_url}" target="_blank" class="file-item" title="${fileName}">
                            <div class="file-info">
                                <span class="file-name">${fileName}</span>
                                <span class="file-meta">
                                    ${dateStr ? "Datum: " + dateStr : ""}
                                    ${dateStr && fileSize ? " · " : ""}${fileSize}
                                </span>
                                <span class="file-meta">
                                    ${createdAt ? "Generiert am: " + createdAt : ""}
                                    ${createdAt && createdBy ? " · " : ""}
                                    ${createdBy ? "von: " + createdBy : ""}
                                </span>
                            </div>
                            <i class="fa fa-download"></i>
                        </a>
                    `;
                });
            } else {
                filesHtml = `
                    <div class="no-files">
                        <i class="fa fa-clock-o"></i> Noch keine Dateien vorhanden
                    </div>
                `;
            }

            html += `
                <div class="export-item text-${textMode}" data-name="${exp.name}"
                     style="background: linear-gradient(135deg, ${color1} 0%, ${color2} 100%); color: ${textColor};">
                    <div class="export-header">
                        <div class="export-title">${title}</div>
                        <div class="export-meta">
                            ${exp.iban || ""}
                            ${account_info.length > 0 ? " · " + account_info.join(" · ") : ""}
                        </div>
                        <div class="export-format">${exp.export_format || ""}</div>
                    </div>
                    <div class="export-files">
                        ${filesHtml}
                    </div>
                </div>
            `;
        });
        container.innerHTML = html;
    }
});
'''

    style = '''
.widget-head {
    padding: 12px 15px;
    border-bottom: 1px solid var(--border-color);
}
.widget-title {
    font-weight: 600;
    font-size: 13px;
    color: var(--heading-color);
}
.widget-body {
    padding: 12px 15px;
}
.loading-state {
    text-align: center;
    padding: 20px;
    color: var(--text-muted);
}
.export-item {
    padding: 12px;
    margin-bottom: 10px;
    border-radius: var(--border-radius-lg);
    box-shadow:
        0 4px 16px -2px rgba(0, 0, 0, 0.15),
        0 2px 6px -1px rgba(0, 0, 0, 0.1),
        inset 0 1px 0 rgba(255, 255, 255, 0.15);
    border: 1px solid rgba(255, 255, 255, 0.2);
}
.export-item:last-child {
    margin-bottom: 0;
}
.export-header {
    margin-bottom: 10px;
    padding-bottom: 8px;
    border-bottom: 1px solid rgba(255, 255, 255, 0.2);
}
.export-item.text-dark .export-header {
    border-bottom-color: rgba(0, 0, 0, 0.1);
}
.export-title {
    font-weight: 600;
    font-size: 13px;
    margin-bottom: 3px;
}
.export-meta {
    font-size: 11px;
    opacity: 0.85;
    font-family: monospace;
}
.export-format {
    font-size: 10px;
    opacity: 0.7;
    margin-top: 3px;
}
.export-files {
    display: flex;
    flex-direction: column;
    gap: 6px;
}
.file-item {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 8px 10px;
    border-radius: 6px;
    text-decoration: none;
    transition: all 0.2s ease;
}
.export-item.text-light .file-item {
    background: rgba(255, 255, 255, 0.15);
    color: rgba(255, 255, 255, 0.95);
}
.export-item.text-light .file-item:hover {
    background: rgba(255, 255, 255, 0.25);
}
.export-item.text-dark .file-item {
    background: rgba(0, 0, 0, 0.08);
    color: rgba(0, 0, 0, 0.85);
}
.export-item.text-dark .file-item:hover {
    background: rgba(0, 0, 0, 0.15);
}
.file-info {
    display: flex;
    flex-direction: column;
    gap: 2px;
    overflow: hidden;
}
.file-name {
    font-size: 11px;
    font-weight: 500;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
}
.file-meta {
    font-size: 10px;
    opacity: 0.75;
}
.file-item i {
    font-size: 14px;
    opacity: 0.8;
}
.no-files {
    font-size: 11px;
    opacity: 0.7;
    text-align: center;
    padding: 8px;
}
.empty-state {
    text-align: center;
    padding: 25px 15px;
    color: var(--text-muted);
}
.empty-state i {
    font-size: 28px;
    margin-bottom: 10px;
    display: block;
    opacity: 0.5;
}
'''

    frappe.db.set_value("Custom HTML Block", "Quick Export", {
        "html": html,
        "script": script,
        "style": style
    })
    frappe.db.commit()
