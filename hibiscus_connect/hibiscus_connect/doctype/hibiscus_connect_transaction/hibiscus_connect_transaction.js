// Copyright (c) 2021, itsdave GmbH and contributors
// For license information, please see license.txt

frappe.ui.form.on('Hibiscus Connect Transaction', {
	setup(frm) {
		frm.set_query("link_doctype", "verknuepfungen", function() {
			return { filters: { istable: 0, issingle: 0 } };
		});
	},

	refresh(frm) {
		// Bestehende Buttons
		frm.add_custom_button('Zahlung verbuchen', function(){
			frappe.call({
				method: 'hibiscus_connect.tools.match_hibiscus_transaction',
				args: {
					hib_trans: frm.doc.name,
				},
				callback:function(r){
					frappe.msgprint({
						title: __('Notification'),
						indicator: 'green',
						message: __(r.message)
					});
					frappe.set_route('List', 'Hibiscus Connect Transaction', {
						'status': 'neu',
						'betrag': ['>', 0]});
				}
			})
		});
		frm.add_custom_button('Bankkonto erstellen', function(){
			frappe.call({
				method: 'hibiscus_connect.tools.create_bank_account_for_customer',
				args: {
					customer: frm.doc.customer,
					bic: frm.doc.empfaenger_blz,
					iban: frm.doc.empfaenger_konto
				},
				callback:function(r){
					frappe.msgprint({
						title: __('Notification'),
						indicator: 'green',
						message: __(r.message)
					});
				}
			})
		});

		// Stornierte/ersetzte Verknüpfungen visuell abgrenzen
		style_inactive_links(frm);
	}
});

frappe.ui.form.on('Hibiscus Connect Transaction Link', {
	link_status(frm) {
		style_inactive_links(frm);
	},
	verknuepfungen_remove(frm) {
		style_inactive_links(frm);
	}
});

function style_inactive_links(frm) {
	setTimeout(function() {
		(frm.doc.verknuepfungen || []).forEach(function(row, idx) {
			let $row = frm.fields_dict.verknuepfungen.grid.grid_rows[idx];
			if (!$row) return;
			let $el = $row.row;
			if (row.link_status === 'storniert' || row.link_status === 'ersetzt') {
				$el.css({ 'opacity': '0.5', 'text-decoration': 'line-through' });
			} else {
				$el.css({ 'opacity': '1', 'text-decoration': 'none' });
			}
		});
	}, 100);
}
