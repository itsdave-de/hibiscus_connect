// Copyright (c) 2021, itsdave GmbH and contributors
// For license information, please see license.txt

frappe.ui.form.on('Hibiscus Connect Transaction', {
	setup(frm) {
		frm.set_query("link_doctype", "transaction_links", function() {
			return { filters: { istable: 0, issingle: 0 } };
		});
	},

	refresh(frm) {
		if (frm.doc.status === 'chargeback') {
			// Chargeback transaction — show banner and process button
			_show_chargeback_banner(frm);
			_add_chargeback_button(frm);
		} else if (frm.doc.status === 'chargeback processed') {
			frm.dashboard.set_headline(
				__('Rücklastschrift wurde verarbeitet.'),
				'green'
			);
		} else if (frm.doc.status === 'new') {
			if (frm.doc.amount > 0) {
				// Incoming: auto-matching (existing logic)
				frm.add_custom_button(__('Automatisch verbuchen'), function(){
					frappe.call({
						method: 'hibiscus_connect.tools.match_hibiscus_transaction',
						args: { hib_trans: frm.doc.name },
						callback: function(r){
							frappe.msgprint({
								title: __('Notification'),
								indicator: 'green',
								message: __(r.message)
							});
							frm.reload_doc();
						}
					});
				}, __('Aktionen'));
			}
			frm.add_custom_button(__('Bankkonto erstellen'), function(){
				frappe.call({
					method: 'hibiscus_connect.tools.create_bank_account_for_customer',
					args: {
						customer: frm.doc.customer,
						bic: frm.doc.counterparty_bic,
						iban: frm.doc.counterparty_iban
					},
					callback: function(r){
						frappe.msgprint({
							title: __('Notification'),
							indicator: 'green',
							message: __(r.message)
						});
					}
				});
			}, __('Aktionen'));
		}

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


function _show_chargeback_banner(frm) {
	frappe.call({
		method: 'hibiscus_connect.tools.get_chargeback_details',
		args: { hib_trans: frm.doc.name },
		async: false,
		callback: function(r) {
			if (!r.message) return;
			var d = r.message;
			frm._chargeback_details = d;

			var headline;
			if (d.can_process) {
				headline = __('Rücklastschrift') + ' — '
					+ d.sinv_refs.join(', ') + ' — '
					+ __('Original PE') + ': '
					+ '<a href="/app/payment-entry/' + d.pe_name + '">' + d.pe_name + '</a>';
			} else {
				headline = __('Rücklastschrift') + ' — ' + (d.message || __('Details nicht verfügbar'));
			}
			frm.dashboard.set_headline(headline, 'orange');
		}
	});
}


function _add_chargeback_button(frm) {
	frm.add_custom_button(__('Rücklastschrift verarbeiten'), function() {
		var d = frm._chargeback_details;
		if (!d || !d.can_process) {
			frappe.msgprint({
				title: __('Nicht möglich'),
				indicator: 'red',
				message: d ? d.message : __('Rücklastschrift-Details nicht geladen.')
			});
			return;
		}

		// Build confirmation message
		var msg = '<p><b>' + __('Payment Entry stornieren') + ':</b> '
			+ '<a href="/app/payment-entry/' + d.pe_name + '">' + d.pe_name + '</a>'
			+ ' (' + format_currency(d.pe_amount) + ')</p>';

		msg += '<p><b>' + __('Rechnungen werden wieder offen') + ':</b></p><ul>';
		(d.sinv_details || []).forEach(function(s) {
			msg += '<li><a href="/app/sales-invoice/' + s.sinv + '">' + s.sinv + '</a>'
				+ ' — ' + format_currency(s.amount)
				+ ' (aktuell: ' + s.status + ')</li>';
		});
		msg += '</ul>';

		if (d.fee_amount > 0) {
			msg += '<p style="color: orange;"><b>' + __('Bankgebühr') + ': '
				+ format_currency(d.fee_amount)
				+ '</b> (' + __('manuell verbuchen') + ')</p>';
		} else if (d.fee_amount < 0) {
			msg += '<p style="color: orange;"><b>' + __('Differenz') + ': '
				+ format_currency(d.fee_amount) + '</b></p>';
		}

		frappe.confirm(
			msg,
			function() {
				// Confirmed
				frappe.call({
					method: 'hibiscus_connect.tools.process_chargeback',
					args: { hib_trans: frm.doc.name },
					freeze: true,
					freeze_message: __('Rücklastschrift wird verarbeitet...'),
					callback: function(r) {
						frappe.msgprint({
							title: __('Rücklastschrift verarbeitet'),
							indicator: 'green',
							message: r.message
						});
						frm.reload_doc();
					},
					error: function(r) {
						frappe.msgprint({
							title: __('Fehler'),
							indicator: 'red',
							message: r.message || __('Fehler bei der Verarbeitung')
						});
					}
				});
			}
		);
	}, __('Aktionen'));
}


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
