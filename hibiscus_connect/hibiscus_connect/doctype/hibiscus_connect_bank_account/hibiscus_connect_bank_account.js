// Copyright (c) 2021, itsdave GmbH and contributors
// For license information, please see license.txt

frappe.ui.form.on('Hibiscus Connect Bank Account', {
	refresh: function(frm) {
		frm.add_custom_button('Umsätze abrufen', function(){
			let ua = new frappe.ui.Dialog({
				title: 'Zeitraum auswählen:',
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
	}
});
