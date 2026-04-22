frappe.listview_settings['Hibiscus Connect Transaction'] = {
	hide_name_column: true,
    add_fields: ['status', 'name'],

	get_indicator: function (doc) {
		if (doc.status === 'neu') {
			return [__('neu'), 'orange', 'status,=,neu'];
		} else if (doc.status === 'automatisch verbucht') {
			return [__('automatisch verbucht'), 'green', 'status,=,automatisch verbucht'];
        } else if (doc.status === 'manuell verbucht') {
			return [__('manuell verbucht'), 'green', 'status,=,manuell verbucht'];
        }
    },
	onload: function(listview) {
		listview.page.add_button(__('Zahlungen Verbuchen'), function() {
			const default_bis = frappe.datetime.now_date();
			const default_von = frappe.datetime.add_days(default_bis, -60);
			const d = new frappe.ui.Dialog({
				title: __('Zahlungen verbuchen'),
				fields: [
					{ fieldtype: 'Date', fieldname: 'von', label: __('Von'), default: default_von, reqd: 1 },
					{ fieldtype: 'Date', fieldname: 'bis', label: __('Bis'), default: default_bis, reqd: 1 },
					{ fieldtype: 'HTML', fieldname: 'hint', options:
						'<p class="text-muted small">' +
						__('Verarbeitet "neue" Eingangszahlungen im gewählten Zeitraum als Hintergrund-Job. Der Fortschritt wird oben in Frappe angezeigt.') +
						'</p>'
					}
				],
				primary_action_label: __('Starten'),
				primary_action(values) {
					d.hide();
					const done_handler = function(data) {
						frappe.realtime.off('hibiscus_match_all_payments_done', done_handler);
						frappe.hide_progress();
						frappe.msgprint({
							title: __('Verbuchung abgeschlossen'),
							message: (data && data.message) || __('Fertig.'),
							indicator: 'green'
						});
						listview.refresh();
					};
					frappe.realtime.on('hibiscus_match_all_payments_done', done_handler);
					frappe.show_progress(__('Verarbeite Zahlungseingänge...'), 0, 100);
					frappe.call({
						method: 'hibiscus_connect.tools.enqueue_match_all_payments',
						args: { von: values.von, bis: values.bis },
						callback: function(r) {
							if (r && r.message && r.message.status === 'enqueued') {
								frappe.show_alert({ message: __('Job gestartet.'), indicator: 'blue' });
							}
						},
						error: function() {
							frappe.realtime.off('hibiscus_match_all_payments_done', done_handler);
							frappe.hide_progress();
						}
					});
				}
			});
			d.show();
		}, 'Aktionen');

		listview.page.add_button(__('andere Einnahme'), function() {
			let trans_list = [];
			$('.list-row-checkbox:checked').each(function(index, value) {
				trans_list.push($(this).attr('data-name'));
			});
			if (trans_list.length > 0) {
				frappe.call({
					method: 'hibiscus_connect.tools.set_andere_einnahme',
					args: { 'list': trans_list },
					callback: function() {
						listview.refresh();
					}
				});
			}
		}, __("Aktionen"));
	}
};
