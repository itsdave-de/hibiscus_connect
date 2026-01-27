// Copyright (c) 2025, itsdave GmbH and contributors
// For license information, please see license.txt

frappe.ui.form.on("Bank Code", {
    refresh: function(frm) {
        // Set read-only if user only has read permission
        if (!frappe.perm.has_perm("Bank Code", 0, "write")) {
            frm.disable_form();
        }
    }
});
