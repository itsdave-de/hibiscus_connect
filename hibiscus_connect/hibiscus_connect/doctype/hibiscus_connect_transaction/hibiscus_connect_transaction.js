// Copyright (c) 2021, itsdave GmbH and contributors
// For license information, please see license.txt

frappe.ui.form.on('Hibiscus Connect Transaction', {
	setup(frm) {
		frm.set_query("link_doctype", "transaction_links", function() {
			return { filters: { istable: 0, issingle: 0 } };
		});
	},

	refresh(frm) {
		// Book payment button
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
						'amount': ['>', 0]});
				}
			})
		});
		// Create bank account button
		frm.add_custom_button('Bankkonto erstellen', function(){
			frappe.call({
				method: 'hibiscus_connect.tools.create_bank_account_for_customer',
				args: {
					customer: frm.doc.customer,
					bic: frm.doc.counterparty_bic,
					iban: frm.doc.counterparty_iban
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

		// Visually distinguish cancelled/replaced links
		style_inactive_links(frm);
	}
});

frappe.ui.form.on('Hibiscus Connect Transaction Link', {
	link_status(frm) {
		style_inactive_links(frm);
	},
	transaction_links_remove(frm) {
		style_inactive_links(frm);
	}
});

function style_inactive_links(frm) {
	setTimeout(function() {
		(frm.doc.transaction_links || []).forEach(function(row, idx) {
			let $row = frm.fields_dict.transaction_links.grid.grid_rows[idx];
			if (!$row) return;
			let $el = $row.row;
			if (row.link_status === 'cancelled' || row.link_status === 'replaced') {
				$el.css({ 'opacity': '0.5', 'text-decoration': 'line-through' });
			} else {
				$el.css({ 'opacity': '1', 'text-decoration': 'none' });
			}
		});
	}, 100);
}
