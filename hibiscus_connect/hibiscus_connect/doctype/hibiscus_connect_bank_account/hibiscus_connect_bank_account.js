// Copyright (c) 2021, itsdave GmbH and contributors
// For license information, please see license.txt

frappe.ui.form.on('Hibiscus Connect Bank Account', {
	refresh: function(frm) {
		// "Umsaetze abrufen" button
		frm.add_custom_button('Ums\u00e4tze abrufen', function(){
			let ua = new frappe.ui.Dialog({
				title: 'Zeitraum ausw\u00e4hlen:',
				fields: [
					{
						label: 'von',
						fieldname: 'von',
						fieldtype: 'Date'
					},
					{
						label: 'bis',
						fieldname: 'bis',
						fieldtype: 'Date'
					}
				],
				primary_action_label: 'Submit',
				primary_action(values) {
					frappe.call({
						method: 'hibiscus_connect.tools.get_transactions_for_account',
						args: {
							account: frm.doc.name,
							von: values.von,
							bis: values.bis
						 },
						callback:function(r){
							ua.hide();
						}
					})
				}
			});
			ua.show()
		});

		// Balance chart
		if (!frm.is_new()) {
			frm.call({
				method: 'hibiscus_connect.tools.get_balance_history',
				args: { account: frm.doc.name },
				callback: function(r) {
					if (r.message && r.message.labels && r.message.labels.length) {
						render_balance_chart(frm, r.message);
					} else {
						frm.fields_dict.balance_chart.$wrapper.html(
							'<p class="text-muted">Keine Kontoverlaufsdaten verf\u00fcgbar.</p>'
						);
					}
				}
			});
		}
	}
});

function render_balance_chart(frm, data) {
	const wrapper = frm.fields_dict.balance_chart.$wrapper;
	wrapper.empty();

	const chart_container = $('<div>').appendTo(wrapper);

	new frappe.Chart(chart_container[0], {
		type: 'line',
		height: 250,
		colors: [frm.doc.accent_color_1 || '#667eea'],
		data: {
			labels: data.labels,
			datasets: [{
				name: 'Kontostand',
				values: data.values
			}]
		},
		tooltipOptions: {
			formatTooltipY: d => format_currency(d, frm.doc.currency || 'EUR')
		},
		axisOptions: {
			xIsSeries: true,
			shortenYAxisNumbers: true
		},
		lineOptions: {
			hideDots: 1,
			regionFill: 1
		}
	});
}
